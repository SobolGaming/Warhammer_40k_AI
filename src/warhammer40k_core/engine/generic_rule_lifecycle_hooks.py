from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from types import MappingProxyType
from typing import cast

from warhammer40k_core.core.validation import IdentifierValidator
from warhammer40k_core.engine.advance_eligibility_hooks import (
    AdvanceEligibilityContext,
    AdvanceEligibilityGrant,
    AdvanceEligibilityHandler,
    AdvanceEligibilityHookBinding,
)
from warhammer40k_core.engine.army_mustering import ArmyDefinition
from warhammer40k_core.engine.attack_sequence_completion_hooks import (
    AttackSequenceCompletedHookBinding,
)
from warhammer40k_core.engine.effects import GENERIC_RULE_EFFECT_KIND, PersistingEffect
from warhammer40k_core.engine.event_log import JsonValue, validate_json_value
from warhammer40k_core.engine.faction_content.activation import (
    RuntimeContentActivation,
    RuntimeEnhancementAssignment,
)
from warhammer40k_core.engine.fall_back_hooks import (
    FallBackEligibilityContext,
    FallBackEligibilityGrant,
    FallBackEligibilityHandler,
    FallBackEligibilityHookBinding,
)
from warhammer40k_core.engine.fight_activation_abilities import (
    FIGHT_ACTIVATION_MELEE_TARGETING_EFFECT_KIND,
    FightActivationAbilityContext,
    FightActivationAbilityHandler,
    FightActivationAbilityHookBinding,
    FightActivationAbilityOption,
)
from warhammer40k_core.engine.fight_order import CHARGE_FIGHTS_FIRST_EFFECT_KIND
from warhammer40k_core.engine.fight_unit_selected_hooks import (
    FightUnitSelectedContext,
    FightUnitSelectedGrant,
    FightUnitSelectedGrantBinding,
    FightUnitSelectedGrantHandler,
)
from warhammer40k_core.engine.game_state import GameState
from warhammer40k_core.engine.generic_rule_effect_payloads import (
    generic_rule_effect_payload_grants_ability,
)
from warhammer40k_core.engine.mortal_wound_feel_no_pain_hooks import (
    MortalWoundFeelNoPainContinuationHookBinding,
)
from warhammer40k_core.engine.phase import BattlePhase, GameLifecycleError
from warhammer40k_core.engine.rule_execution import (
    RuleExecutionContext,
    RuleExecutionStatus,
    execute_rule_ir,
)
from warhammer40k_core.engine.rules_units import RulesUnitView, rules_unit_view_by_id
from warhammer40k_core.engine.runtime_modifiers import WeaponProfileModifierBinding
from warhammer40k_core.engine.shooting_types import ShootingType
from warhammer40k_core.engine.shooting_unit_selected_hooks import (
    ShootingUnitSelectedContext,
    ShootingUnitSelectedGrant,
    ShootingUnitSelectedGrantBinding,
    ShootingUnitSelectedGrantHandler,
)
from warhammer40k_core.engine.target_restriction_hooks import (
    ShootingTargetRestrictionContext,
    ShootingTargetRestrictionHandler,
    ShootingTargetRestrictionHookBinding,
    TargetRestriction,
)
from warhammer40k_core.engine.unit_factory import UnitInstance
from warhammer40k_core.rules.rule_ir import (
    RuleEffectKind,
    RuleIR,
    RuleTargetKind,
    parameter_payload,
)
from warhammer40k_core.rules.source_packages.warhammer_40000_11th import (
    faction_coverage_2026_27,
    faction_execution_2026_27,
    faction_generic_ir_support_2026_27,
)
from warhammer40k_core.rules.source_packages.warhammer_40000_11th import (
    faction_shadow_legion_ir_support_2026_27 as shadow_legion_ir,
)

_Phase17FExecutionRecord = faction_execution_2026_27.Phase17FExecutionRecord

_FALL_BACK_SHOOT_ABILITY = "can_fall_back_and_shoot"
_FALL_BACK_CHARGE_ABILITY = "can_fall_back_and_charge"
_FIGHT_ACTIVATION_TARGETING_ABILITY = "fight_activation_melee_targeting_distance"
_ADVANCE_SHOOT_CHARGE_ABILITY = shadow_legion_ir.CAN_ADVANCE_AND_SHOOT_AND_CHARGE_ABILITY
_SNAP_SHOOTING_TARGET_FORBIDDEN_ABILITY = shadow_legion_ir.SNAP_SHOOTING_TARGET_FORBIDDEN_ABILITY
_DARK_PACT_LETHAL_HITS = "lethal_hits"
_DARK_PACT_SUSTAINED_HITS_1 = "sustained_hits_1"
_DARK_PACT_EFFECT_KIND = "chaos_space_marines_dark_pact"
_SHADOW_LEGION_DARK_PACT_SOURCE_RULE_ID = "phase17f:phase17e:chaos-daemons:shadow-legion:rule"
_SHADOW_LEGION_DARK_PACT_MORTAL_WOUNDS_SOURCE_KIND = "chaos_daemons_shadow_legion_dark_pacts"
_DARK_PACT_CHOICE_ABILITIES_BY_PACT = {
    _DARK_PACT_LETHAL_HITS: (shadow_legion_ir.SHADOW_LEGION_DARK_PACT_LETHAL_HITS_CHOICE_ABILITY),
    _DARK_PACT_SUSTAINED_HITS_1: (
        shadow_legion_ir.SHADOW_LEGION_DARK_PACT_SUSTAINED_HITS_1_CHOICE_ABILITY
    ),
}
_DARK_PACT_LABELS_BY_PACT = {
    _DARK_PACT_LETHAL_HITS: "Dark Pacts: Lethal Hits",
    _DARK_PACT_SUSTAINED_HITS_1: "Dark Pacts: Sustained Hits 1",
}


@dataclass(frozen=True, slots=True)
class _GenericFallBackEligibilitySource:
    record: _Phase17FExecutionRecord
    rule_ir: RuleIR

    def __post_init__(self) -> None:
        if type(self.record) is not _Phase17FExecutionRecord:
            raise GameLifecycleError("Generic Fall Back source requires execution record.")
        if type(self.rule_ir) is not RuleIR:
            raise GameLifecycleError("Generic Fall Back source requires RuleIR.")
        _validate_record_rule_ir_hash(record=self.record, rule_ir=self.rule_ir)


@dataclass(frozen=True, slots=True)
class _GenericFightActivationAbilitySource:
    record: _Phase17FExecutionRecord
    rule_ir: RuleIR
    assignments_by_bearer_unit_id: Mapping[str, RuntimeEnhancementAssignment]

    def __post_init__(self) -> None:
        if type(self.record) is not _Phase17FExecutionRecord:
            raise GameLifecycleError("Generic fight activation source requires execution record.")
        if type(self.rule_ir) is not RuleIR:
            raise GameLifecycleError("Generic fight activation source requires RuleIR.")
        if self.record.rule_id is None:
            raise GameLifecycleError("Generic fight activation source requires rule_id.")
        _validate_record_rule_ir_hash(record=self.record, rule_ir=self.rule_ir)
        object.__setattr__(
            self,
            "assignments_by_bearer_unit_id",
            _validate_assignment_mapping(self.assignments_by_bearer_unit_id),
        )


@dataclass(frozen=True, slots=True)
class _GenericShadowLegionSource:
    record: _Phase17FExecutionRecord
    rule_ir: RuleIR

    def __post_init__(self) -> None:
        if type(self.record) is not _Phase17FExecutionRecord:
            raise GameLifecycleError("Generic Shadow Legion source requires execution record.")
        if type(self.rule_ir) is not RuleIR:
            raise GameLifecycleError("Generic Shadow Legion source requires RuleIR.")
        _validate_record_rule_ir_hash(record=self.record, rule_ir=self.rule_ir)
        if (
            self.record.coverage_descriptor_id
            != shadow_legion_ir.SHADOW_LEGION_DETACHMENT_RULE_DESCRIPTOR_ID
        ):
            raise GameLifecycleError("Generic Shadow Legion source received wrong descriptor.")


def advance_eligibility_hook_bindings(
    *,
    activation: RuntimeContentActivation,
    execution_records: tuple[_Phase17FExecutionRecord, ...],
) -> tuple[AdvanceEligibilityHookBinding, ...]:
    sources = _shadow_legion_sources(activation=activation, execution_records=execution_records)
    return tuple(
        AdvanceEligibilityHookBinding(
            hook_id=_shadow_legion_advance_hook_id(source.record),
            source_id=_SHADOW_LEGION_DARK_PACT_SOURCE_RULE_ID,
            handler=_shadow_legion_advance_handler_for_source(source),
        )
        for source in sources
        if _rule_ir_grants_any_ability(source.rule_ir, abilities=(_ADVANCE_SHOOT_CHARGE_ABILITY,))
    )


def fall_back_eligibility_hook_bindings(
    *,
    activation: RuntimeContentActivation,
    execution_records: tuple[_Phase17FExecutionRecord, ...],
) -> tuple[FallBackEligibilityHookBinding, ...]:
    if type(activation) is not RuntimeContentActivation:
        raise GameLifecycleError("Generic Fall Back bindings require activation.")
    if type(execution_records) is not tuple:
        raise GameLifecycleError("Generic Fall Back bindings require execution records.")
    selected_detachment_ids = set(activation.selected_detachment_ids)
    bindings: list[FallBackEligibilityHookBinding] = []
    for record in execution_records:
        if type(record) is not _Phase17FExecutionRecord:
            raise GameLifecycleError("Generic Fall Back bindings require execution records.")
        if not _record_is_generic_detachment_rule(record):
            continue
        if record.detachment_id not in selected_detachment_ids:
            continue
        rule_ir = _rule_ir_for_record(record)
        if not _rule_ir_grants_any_ability(
            rule_ir,
            abilities=(_FALL_BACK_SHOOT_ABILITY, _FALL_BACK_CHARGE_ABILITY),
        ):
            continue
        source = _GenericFallBackEligibilitySource(record=record, rule_ir=rule_ir)
        bindings.append(
            FallBackEligibilityHookBinding(
                hook_id=_fall_back_hook_id(record),
                source_id=rule_ir.source_id,
                handler=_fall_back_handler_for_source(source),
            )
        )
    return tuple(sorted(bindings, key=lambda binding: binding.hook_id))


def fight_activation_ability_hook_bindings(
    *,
    activation: RuntimeContentActivation,
    execution_records: tuple[_Phase17FExecutionRecord, ...],
) -> tuple[FightActivationAbilityHookBinding, ...]:
    if type(activation) is not RuntimeContentActivation:
        raise GameLifecycleError("Generic fight activation bindings require activation.")
    if type(execution_records) is not tuple:
        raise GameLifecycleError("Generic fight activation bindings require execution records.")
    assignments_by_enhancement_id = _assignments_by_enhancement_id(activation)
    bindings: list[FightActivationAbilityHookBinding] = []
    for record in execution_records:
        if type(record) is not _Phase17FExecutionRecord:
            raise GameLifecycleError("Generic fight activation bindings require execution records.")
        if not _record_is_generic_enhancement(record):
            continue
        enhancement_id = _record_rule_id(record)
        assignments = assignments_by_enhancement_id.get(enhancement_id)
        if assignments is None:
            continue
        rule_ir = _rule_ir_for_record(record)
        if not _rule_ir_grants_any_ability(
            rule_ir,
            abilities=(_FIGHT_ACTIVATION_TARGETING_ABILITY,),
        ):
            continue
        source = _GenericFightActivationAbilitySource(
            record=record,
            rule_ir=rule_ir,
            assignments_by_bearer_unit_id=assignments,
        )
        bindings.append(
            FightActivationAbilityHookBinding(
                hook_id=_fight_activation_hook_id(record),
                source_id=rule_ir.source_id,
                handler=_fight_activation_handler_for_source(source),
            )
        )
    return tuple(sorted(bindings, key=lambda binding: binding.hook_id))


def shooting_target_restriction_hook_bindings(
    *,
    activation: RuntimeContentActivation,
    execution_records: tuple[_Phase17FExecutionRecord, ...],
) -> tuple[ShootingTargetRestrictionHookBinding, ...]:
    sources = _shadow_legion_sources(activation=activation, execution_records=execution_records)
    return tuple(
        ShootingTargetRestrictionHookBinding(
            hook_id=_shadow_legion_snap_restriction_hook_id(source.record),
            source_id=_SHADOW_LEGION_DARK_PACT_SOURCE_RULE_ID,
            handler=_shadow_legion_snap_restriction_handler_for_source(source),
        )
        for source in sources
        if _rule_ir_grants_any_ability(
            source.rule_ir,
            abilities=(_SNAP_SHOOTING_TARGET_FORBIDDEN_ABILITY,),
        )
    )


def shooting_unit_selected_grant_hook_bindings(
    *,
    activation: RuntimeContentActivation,
    execution_records: tuple[_Phase17FExecutionRecord, ...],
) -> tuple[ShootingUnitSelectedGrantBinding, ...]:
    bindings: list[ShootingUnitSelectedGrantBinding] = []
    for source in _shadow_legion_sources(
        activation=activation,
        execution_records=execution_records,
    ):
        for pact, ability in _DARK_PACT_CHOICE_ABILITIES_BY_PACT.items():
            if not _rule_ir_grants_any_ability(source.rule_ir, abilities=(ability,)):
                continue
            bindings.append(
                ShootingUnitSelectedGrantBinding(
                    hook_id=_shadow_legion_shooting_dark_pact_hook_id(source.record, pact),
                    source_id=_SHADOW_LEGION_DARK_PACT_SOURCE_RULE_ID,
                    handler=_shadow_legion_shooting_dark_pact_handler_for_source(source, pact),
                )
            )
    return tuple(sorted(bindings, key=lambda binding: binding.hook_id))


def fight_unit_selected_grant_hook_bindings(
    *,
    activation: RuntimeContentActivation,
    execution_records: tuple[_Phase17FExecutionRecord, ...],
) -> tuple[FightUnitSelectedGrantBinding, ...]:
    bindings: list[FightUnitSelectedGrantBinding] = []
    for source in _shadow_legion_sources(
        activation=activation,
        execution_records=execution_records,
    ):
        for pact, ability in _DARK_PACT_CHOICE_ABILITIES_BY_PACT.items():
            if not _rule_ir_grants_any_ability(source.rule_ir, abilities=(ability,)):
                continue
            bindings.append(
                FightUnitSelectedGrantBinding(
                    hook_id=_shadow_legion_fight_dark_pact_hook_id(source.record, pact),
                    source_id=_SHADOW_LEGION_DARK_PACT_SOURCE_RULE_ID,
                    handler=_shadow_legion_fight_dark_pact_handler_for_source(source, pact),
                )
            )
    return tuple(sorted(bindings, key=lambda binding: binding.hook_id))


def attack_sequence_completed_hook_bindings(
    *,
    activation: RuntimeContentActivation,
    execution_records: tuple[_Phase17FExecutionRecord, ...],
) -> tuple[AttackSequenceCompletedHookBinding, ...]:
    from warhammer40k_core.engine.faction_content.warhammer_40000_11th.chaos_space_marines import (
        army_rule as dark_pacts,
    )

    return tuple(
        AttackSequenceCompletedHookBinding(
            hook_id=_shadow_legion_dark_pact_completion_hook_id(source.record),
            source_id=_SHADOW_LEGION_DARK_PACT_SOURCE_RULE_ID,
            handler=dark_pacts.resolve_dark_pact_attack_sequence_completion,
        )
        for source in _shadow_legion_sources(
            activation=activation,
            execution_records=execution_records,
        )
        if _rule_ir_grants_any_ability(
            source.rule_ir,
            abilities=tuple(_DARK_PACT_CHOICE_ABILITIES_BY_PACT.values()),
        )
    )


def mortal_wound_feel_no_pain_hook_bindings(
    *,
    activation: RuntimeContentActivation,
    execution_records: tuple[_Phase17FExecutionRecord, ...],
) -> tuple[MortalWoundFeelNoPainContinuationHookBinding, ...]:
    from warhammer40k_core.engine.faction_content.warhammer_40000_11th.chaos_space_marines import (
        army_rule as dark_pacts,
    )

    return tuple(
        MortalWoundFeelNoPainContinuationHookBinding(
            hook_id=_shadow_legion_dark_pact_mortal_wound_fnp_hook_id(source.record),
            source_id=_SHADOW_LEGION_DARK_PACT_SOURCE_RULE_ID,
            source_kind=_SHADOW_LEGION_DARK_PACT_MORTAL_WOUNDS_SOURCE_KIND,
            handler=dark_pacts.apply_dark_pact_mortal_wound_feel_no_pain_decision,
        )
        for source in _shadow_legion_sources(
            activation=activation,
            execution_records=execution_records,
        )
        if _rule_ir_grants_any_ability(
            source.rule_ir,
            abilities=tuple(_DARK_PACT_CHOICE_ABILITIES_BY_PACT.values()),
        )
    )


def weapon_profile_modifier_bindings(
    *,
    activation: RuntimeContentActivation,
    execution_records: tuple[_Phase17FExecutionRecord, ...],
) -> tuple[WeaponProfileModifierBinding, ...]:
    from warhammer40k_core.engine.faction_content.warhammer_40000_11th.chaos_space_marines import (
        army_rule as dark_pacts,
    )

    return tuple(
        WeaponProfileModifierBinding(
            modifier_id=_shadow_legion_dark_pact_weapon_profile_modifier_id(source.record),
            source_id=_SHADOW_LEGION_DARK_PACT_SOURCE_RULE_ID,
            handler=dark_pacts.dark_pact_weapon_profile_modifier,
        )
        for source in _shadow_legion_sources(
            activation=activation,
            execution_records=execution_records,
        )
        if _rule_ir_grants_any_ability(
            source.rule_ir,
            abilities=tuple(_DARK_PACT_CHOICE_ABILITIES_BY_PACT.values()),
        )
    )


def _fall_back_handler_for_source(
    source: _GenericFallBackEligibilitySource,
) -> FallBackEligibilityHandler:
    def handler(context: FallBackEligibilityContext) -> FallBackEligibilityGrant | None:
        return _fall_back_grant_for_context(context=context, source=source)

    return handler


def _shadow_legion_advance_handler_for_source(
    source: _GenericShadowLegionSource,
) -> AdvanceEligibilityHandler:
    def handler(context: AdvanceEligibilityContext) -> AdvanceEligibilityGrant | None:
        return _shadow_legion_advance_grant_for_context(context=context, source=source)

    return handler


def _shadow_legion_snap_restriction_handler_for_source(
    source: _GenericShadowLegionSource,
) -> ShootingTargetRestrictionHandler:
    def handler(context: ShootingTargetRestrictionContext) -> TargetRestriction | None:
        return _shadow_legion_snap_restriction_for_context(context=context, source=source)

    return handler


def _shadow_legion_shooting_dark_pact_handler_for_source(
    source: _GenericShadowLegionSource,
    pact: str,
) -> ShootingUnitSelectedGrantHandler:
    def handler(context: ShootingUnitSelectedContext) -> ShootingUnitSelectedGrant | None:
        return _shadow_legion_shooting_dark_pact_grant(
            context=context,
            source=source,
            pact=pact,
        )

    return handler


def _shadow_legion_fight_dark_pact_handler_for_source(
    source: _GenericShadowLegionSource,
    pact: str,
) -> FightUnitSelectedGrantHandler:
    def handler(context: FightUnitSelectedContext) -> FightUnitSelectedGrant | None:
        return _shadow_legion_fight_dark_pact_grant(context=context, source=source, pact=pact)

    return handler


def _shadow_legion_advance_grant_for_context(
    *,
    context: AdvanceEligibilityContext,
    source: _GenericShadowLegionSource,
) -> AdvanceEligibilityGrant | None:
    if type(context) is not AdvanceEligibilityContext:
        raise GameLifecycleError("Generic Shadow Legion Advance eligibility requires context.")
    if (
        _shadow_legion_unit_for_player_context(
            state=context.state,
            player_id=context.player_id,
            unit_instance_id=context.unit_instance_id,
            source=source,
        )
        is None
    ):
        return None
    matching_effects = _matching_shadow_legion_grant_ability_effects(
        state=context.state,
        unit_instance_id=context.unit_instance_id,
        ability=_ADVANCE_SHOOT_CHARGE_ABILITY,
    )
    if not matching_effects:
        return None
    return AdvanceEligibilityGrant(
        hook_id=_shadow_legion_advance_hook_id(source.record),
        source_id=_SHADOW_LEGION_DARK_PACT_SOURCE_RULE_ID,
        can_shoot=True,
        can_declare_charge=True,
        replay_payload=validate_json_value(
            {
                "effect_kind": "generic_rule_advance_eligibility",
                "coverage_descriptor_id": source.record.coverage_descriptor_id,
                "execution_id": source.record.execution_id,
                "rule_ir_hash": source.rule_ir.ir_hash(),
                "persisting_effect_ids": [effect.effect_id for effect in matching_effects],
                "unit_instance_id": context.unit_instance_id,
                "movement_request_id": context.movement_request_id,
                "movement_result_id": context.movement_result_id,
            }
        ),
    )


def _shadow_legion_snap_restriction_for_context(
    *,
    context: ShootingTargetRestrictionContext,
    source: _GenericShadowLegionSource,
) -> TargetRestriction | None:
    if type(context) is not ShootingTargetRestrictionContext:
        raise GameLifecycleError("Generic Shadow Legion target restriction requires context.")
    if context.shooting_type is not ShootingType.SNAP:
        return None
    target_rules_unit = rules_unit_view_by_id(
        state=context.state,
        unit_instance_id=context.target_unit_instance_id,
    )
    target_army = _army_for_player(state=context.state, player_id=target_rules_unit.owner_player_id)
    if not _army_uses_detachment_record(army=target_army, record=source.record):
        return None
    matching_effects = _matching_shadow_legion_grant_ability_effects(
        state=context.state,
        unit_instance_id=target_rules_unit.unit_instance_id,
        ability=_SNAP_SHOOTING_TARGET_FORBIDDEN_ABILITY,
    )
    if not matching_effects:
        return None
    return TargetRestriction(
        hook_id=_shadow_legion_snap_restriction_hook_id(source.record),
        source_id=_SHADOW_LEGION_DARK_PACT_SOURCE_RULE_ID,
        violation_code="shadow_legion_shadows_caress_snap_target_forbidden",
        message="Shadow Legion units cannot be targeted by Snap Shooting attacks.",
        replay_payload=validate_json_value(
            {
                "effect_kind": "generic_rule_snap_target_restriction",
                "coverage_descriptor_id": source.record.coverage_descriptor_id,
                "execution_id": source.record.execution_id,
                "rule_ir_hash": source.rule_ir.ir_hash(),
                "persisting_effect_ids": [effect.effect_id for effect in matching_effects],
                "battle_round": context.battle_round,
                "attacking_unit_instance_id": context.attacking_unit_instance_id,
                "target_unit_instance_id": context.target_unit_instance_id,
                "shooting_type": ShootingType.SNAP.value,
            }
        ),
    )


def _shadow_legion_shooting_dark_pact_grant(
    *,
    context: ShootingUnitSelectedContext,
    source: _GenericShadowLegionSource,
    pact: str,
) -> ShootingUnitSelectedGrant | None:
    from warhammer40k_core.engine.faction_content.warhammer_40000_11th.chaos_space_marines import (
        army_rule as dark_pacts,
    )

    if type(context) is not ShootingUnitSelectedContext:
        raise GameLifecycleError("Generic Shadow Legion shooting Dark Pact requires context.")
    if (
        _shadow_legion_unit_for_player_context(
            state=context.state,
            player_id=context.player_id,
            unit_instance_id=context.unit_instance_id,
            source=source,
        )
        is None
    ):
        return None
    matching_effects = _matching_shadow_legion_grant_ability_effects(
        state=context.state,
        unit_instance_id=context.unit_instance_id,
        ability=_DARK_PACT_CHOICE_ABILITIES_BY_PACT[pact],
    )
    if not matching_effects:
        return None
    if (
        dark_pacts.active_dark_pact_for_unit(
            context.state,
            unit_instance_id=context.unit_instance_id,
            phase=BattlePhase.SHOOTING,
        )
        is not None
    ):
        return None
    target_unit_ids = dark_pacts.dark_pact_target_unit_ids(
        context.state,
        unit_instance_id=context.unit_instance_id,
    )
    selected_pact = dark_pacts.DarkPactKind(pact)
    return ShootingUnitSelectedGrant(
        hook_id=_shadow_legion_shooting_dark_pact_hook_id(source.record, pact),
        source_id=_SHADOW_LEGION_DARK_PACT_SOURCE_RULE_ID,
        label=_DARK_PACT_LABELS_BY_PACT[pact],
        replay_payload=_shadow_legion_dark_pact_replay_payload(
            source=source,
            matching_effects=matching_effects,
            pact=pact,
            trigger="selected_to_shoot",
            unit_instance_id=context.unit_instance_id,
            extra_context={
                "selection_request_id": context.request_id,
                "selection_result_id": context.result_id,
            },
        ),
        unit_effect_payload=dark_pacts.dark_pact_effect_payload(
            unit_instance_id=context.unit_instance_id,
            target_unit_instance_ids=target_unit_ids,
            trigger="selected_to_shoot",
            phase=BattlePhase.SHOOTING,
            selected_dark_pact=selected_pact,
            source_context=_shadow_legion_dark_pact_source_context(
                source=source,
                matching_effects=matching_effects,
                extra_context={
                    "selection_request_id": context.request_id,
                    "selection_result_id": context.result_id,
                },
            ),
            leadership_test_auto_pass=_rules_unit_is_belakor(
                state=context.state,
                unit_instance_id=context.unit_instance_id,
            ),
        ),
        unit_effect_expiration="end_phase",
    )


def _shadow_legion_fight_dark_pact_grant(
    *,
    context: FightUnitSelectedContext,
    source: _GenericShadowLegionSource,
    pact: str,
) -> FightUnitSelectedGrant | None:
    from warhammer40k_core.engine.faction_content.warhammer_40000_11th.chaos_space_marines import (
        army_rule as dark_pacts,
    )

    if type(context) is not FightUnitSelectedContext:
        raise GameLifecycleError("Generic Shadow Legion Fight Dark Pact requires context.")
    if (
        _shadow_legion_unit_for_player_context(
            state=context.state,
            player_id=context.player_id,
            unit_instance_id=context.unit_instance_id,
            source=source,
        )
        is None
    ):
        return None
    matching_effects = _matching_shadow_legion_grant_ability_effects(
        state=context.state,
        unit_instance_id=context.unit_instance_id,
        ability=_DARK_PACT_CHOICE_ABILITIES_BY_PACT[pact],
    )
    if not matching_effects:
        return None
    if (
        dark_pacts.active_dark_pact_for_unit(
            context.state,
            unit_instance_id=context.unit_instance_id,
            phase=BattlePhase.FIGHT,
        )
        is not None
    ):
        return None
    target_unit_ids = dark_pacts.dark_pact_target_unit_ids(
        context.state,
        unit_instance_id=context.unit_instance_id,
    )
    selected_pact = dark_pacts.DarkPactKind(pact)
    extra_context: dict[str, JsonValue] = {
        "activation_request_id": context.request_id,
        "activation_result_id": context.result_id,
        "fight_type": context.fight_type,
        "ordering_band": context.ordering_band,
    }
    return FightUnitSelectedGrant(
        hook_id=_shadow_legion_fight_dark_pact_hook_id(source.record, pact),
        source_id=_SHADOW_LEGION_DARK_PACT_SOURCE_RULE_ID,
        label=_DARK_PACT_LABELS_BY_PACT[pact],
        replay_payload=_shadow_legion_dark_pact_replay_payload(
            source=source,
            matching_effects=matching_effects,
            pact=pact,
            trigger="selected_to_fight",
            unit_instance_id=context.unit_instance_id,
            extra_context=extra_context,
        ),
        unit_effect_payload=dark_pacts.dark_pact_effect_payload(
            unit_instance_id=context.unit_instance_id,
            target_unit_instance_ids=target_unit_ids,
            trigger="selected_to_fight",
            phase=BattlePhase.FIGHT,
            selected_dark_pact=selected_pact,
            source_context=_shadow_legion_dark_pact_source_context(
                source=source,
                matching_effects=matching_effects,
                extra_context=extra_context,
            ),
            leadership_test_auto_pass=_rules_unit_is_belakor(
                state=context.state,
                unit_instance_id=context.unit_instance_id,
            ),
        ),
        unit_effect_expiration="end_phase",
    )


def _fall_back_grant_for_context(
    *,
    context: FallBackEligibilityContext,
    source: _GenericFallBackEligibilitySource,
) -> FallBackEligibilityGrant | None:
    if type(context) is not FallBackEligibilityContext:
        raise GameLifecycleError("Generic Fall Back grant requires context.")
    if type(source) is not _GenericFallBackEligibilitySource:
        raise GameLifecycleError("Generic Fall Back grant requires source.")
    army = _army_for_player(state=context.state, player_id=context.player_id)
    if not _army_uses_detachment_record(army=army, record=source.record):
        return None
    unit = _unit_in_army(army=army, unit_instance_id=context.unit_instance_id)
    result = execute_rule_ir(
        rule_ir=source.rule_ir,
        context=RuleExecutionContext(
            game_id=context.state.game_id,
            player_id=context.player_id,
            battle_round=context.battle_round,
            phase=context.state.current_battle_phase,
            active_player_id=context.state.active_player_id,
            source_unit_instance_id=unit.unit_instance_id,
            target_unit_instance_ids=(unit.unit_instance_id,),
            target_player_id=context.player_id,
            trigger_payload={
                "event": "fall_back_eligibility",
                "movement_request_id": context.movement_request_id,
                "movement_result_id": context.movement_result_id,
                "coverage_descriptor_id": source.record.coverage_descriptor_id,
            },
            state=context.state,
            record_persisting_effects=False,
        ),
    )
    if (
        result.status is RuleExecutionStatus.INVALID
        and result.reason == "unit_missing_required_keyword"
    ):
        return None
    if result.status is not RuleExecutionStatus.APPLIED:
        if result.reason is None:
            raise GameLifecycleError("Generic Fall Back RuleIR failed without reason.")
        raise GameLifecycleError(f"Generic Fall Back RuleIR failed: {result.reason}.")
    can_shoot = _effect_payloads_grant_ability(
        result.effect_payloads,
        ability=_FALL_BACK_SHOOT_ABILITY,
    )
    can_declare_charge = _effect_payloads_grant_ability(
        result.effect_payloads,
        ability=_FALL_BACK_CHARGE_ABILITY,
    )
    if not can_shoot and not can_declare_charge:
        return None
    return FallBackEligibilityGrant(
        hook_id=_fall_back_hook_id(source.record),
        source_id=source.rule_ir.source_id,
        can_shoot=can_shoot,
        can_declare_charge=can_declare_charge,
        replay_payload=validate_json_value(
            {
                "effect_kind": "generic_rule_fall_back_eligibility",
                "execution_id": source.record.execution_id,
                "coverage_descriptor_id": source.record.coverage_descriptor_id,
                "unit_instance_id": unit.unit_instance_id,
                "movement_request_id": context.movement_request_id,
                "movement_result_id": context.movement_result_id,
                "rule_execution_result": result.to_payload(),
            }
        ),
    )


def _fight_activation_handler_for_source(
    source: _GenericFightActivationAbilitySource,
) -> FightActivationAbilityHandler:
    def handler(context: FightActivationAbilityContext) -> FightActivationAbilityOption | None:
        return _fight_activation_option_for_context(context=context, source=source)

    return handler


def _fight_activation_option_for_context(
    *,
    context: FightActivationAbilityContext,
    source: _GenericFightActivationAbilitySource,
) -> FightActivationAbilityOption | None:
    if type(context) is not FightActivationAbilityContext:
        raise GameLifecycleError("Generic fight activation option requires context.")
    if type(source) is not _GenericFightActivationAbilitySource:
        raise GameLifecycleError("Generic fight activation option requires source.")
    assignment = source.assignments_by_bearer_unit_id.get(context.unit_instance_id)
    if assignment is None:
        return None
    if assignment.player_id != context.player_id:
        raise GameLifecycleError("Generic fight activation assignment player drift.")
    if not context.target_unit_instance_ids:
        return None
    result = execute_rule_ir(
        rule_ir=source.rule_ir,
        context=RuleExecutionContext(
            game_id=context.game_id,
            player_id=context.player_id,
            battle_round=context.battle_round,
            phase=context.state.current_battle_phase,
            active_player_id=context.active_player_id,
            source_unit_instance_id=context.unit_instance_id,
            target_unit_instance_ids=(context.unit_instance_id,),
            target_player_id=context.player_id,
            trigger_payload={
                "event": "fight_activation_ability",
                "activation": validate_json_value(context.activation.to_payload()),
                "target_unit_instance_ids": list(context.target_unit_instance_ids),
                "coverage_descriptor_id": source.record.coverage_descriptor_id,
                "enhancement_assignment": validate_json_value(assignment.to_payload()),
            },
            state=context.state,
            record_persisting_effects=False,
        ),
    )
    if result.status is not RuleExecutionStatus.APPLIED:
        if result.reason is None:
            raise GameLifecycleError("Generic fight activation RuleIR failed without reason.")
        raise GameLifecycleError(f"Generic fight activation RuleIR failed: {result.reason}.")
    effect_payload = _single_grant_ability_payload(
        result.effect_payloads,
        ability=_FIGHT_ACTIVATION_TARGETING_ABILITY,
    )
    parameters = _effect_parameters(effect_payload)
    if _optional_bool_parameter(parameters, "requires_charge_move") and not _unit_made_charge_move(
        state=context.state,
        unit_instance_id=context.unit_instance_id,
    ):
        return None
    return FightActivationAbilityOption(
        hook_id=_fight_activation_hook_id(source.record),
        source_id=source.rule_ir.source_id,
        ability_id=_record_rule_id(source.record),
        enhancement_id=_record_rule_id(source.record),
        effect_kind=FIGHT_ACTIVATION_MELEE_TARGETING_EFFECT_KIND,
        model_proximity_inches=_positive_float_parameter(parameters, "model_proximity_inches"),
        replay_payload=validate_json_value(
            {
                "effect_kind": "generic_rule_fight_activation_ability",
                "execution_id": source.record.execution_id,
                "coverage_descriptor_id": source.record.coverage_descriptor_id,
                "enhancement_assignment": assignment.to_payload(),
                "target_unit_instance_ids": list(context.target_unit_instance_ids),
                "rule_execution_result": result.to_payload(),
            }
        ),
    )


def _shadow_legion_sources(
    *,
    activation: RuntimeContentActivation,
    execution_records: tuple[_Phase17FExecutionRecord, ...],
) -> tuple[_GenericShadowLegionSource, ...]:
    if type(activation) is not RuntimeContentActivation:
        raise GameLifecycleError("Generic Shadow Legion bindings require activation.")
    if type(execution_records) is not tuple:
        raise GameLifecycleError("Generic Shadow Legion bindings require execution records.")
    selected_detachment_ids = set(activation.selected_detachment_ids)
    sources: list[_GenericShadowLegionSource] = []
    for record in execution_records:
        if type(record) is not _Phase17FExecutionRecord:
            raise GameLifecycleError("Generic Shadow Legion bindings require execution records.")
        if not _record_is_generic_detachment_rule(record):
            continue
        if (
            record.coverage_descriptor_id
            != shadow_legion_ir.SHADOW_LEGION_DETACHMENT_RULE_DESCRIPTOR_ID
        ):
            continue
        if record.detachment_id not in selected_detachment_ids:
            continue
        sources.append(
            _GenericShadowLegionSource(record=record, rule_ir=_rule_ir_for_record(record))
        )
    return tuple(sorted(sources, key=lambda source: source.record.execution_id))


def _shadow_legion_unit_for_player_context(
    *,
    state: GameState,
    player_id: str,
    unit_instance_id: str,
    source: _GenericShadowLegionSource,
) -> RulesUnitView | None:
    army = _army_for_player(state=state, player_id=player_id)
    if not _army_uses_detachment_record(army=army, record=source.record):
        return None
    rules_unit = rules_unit_view_by_id(state=state, unit_instance_id=unit_instance_id)
    if rules_unit.owner_player_id != player_id:
        raise GameLifecycleError("Generic Shadow Legion unit owner drift.")
    return rules_unit


def _matching_shadow_legion_grant_ability_effects(
    *,
    state: GameState,
    unit_instance_id: str,
    ability: str,
) -> tuple[PersistingEffect, ...]:
    if type(state) is not GameState:
        raise GameLifecycleError("Generic Shadow Legion effects require GameState.")
    requested_ability = _validate_identifier("ability", ability)
    rules_unit = rules_unit_view_by_id(state=state, unit_instance_id=unit_instance_id)
    matches: list[PersistingEffect] = []
    for effect in state.persisting_effects_for_unit(rules_unit.unit_instance_id):
        if not _shadow_legion_effect_grants_ability(
            effect=effect,
            rules_unit=rules_unit,
            ability=requested_ability,
        ):
            continue
        matches.append(effect)
    return tuple(sorted(matches, key=lambda effect: effect.effect_id))


def _shadow_legion_effect_grants_ability(
    *,
    effect: PersistingEffect,
    rules_unit: RulesUnitView,
    ability: str,
) -> bool:
    payload = _shadow_legion_generic_effect_payload_or_none(effect)
    if payload is None:
        return False
    rule_effect = _payload_object(payload, key="effect")
    if rule_effect.get("kind") != RuleEffectKind.GRANT_ABILITY.value:
        return False
    parameters = _shadow_legion_effect_parameters(rule_effect)
    if parameters.get("ability") != ability:
        return False
    return _required_keywords_apply(parameters=parameters, rules_unit=rules_unit)


def _shadow_legion_generic_effect_payload_or_none(
    effect: PersistingEffect,
) -> dict[str, JsonValue] | None:
    if type(effect) is not PersistingEffect:
        raise GameLifecycleError("Generic Shadow Legion effect lookup requires PersistingEffect.")
    payload = effect.effect_payload
    if not isinstance(payload, dict):
        return None
    if payload.get("effect_kind") != GENERIC_RULE_EFFECT_KIND:
        return None
    if (
        payload.get("coverage_descriptor_id")
        != shadow_legion_ir.SHADOW_LEGION_DETACHMENT_RULE_DESCRIPTOR_ID
    ):
        return None
    target_payload = payload.get("target")
    if target_payload is not None:
        if not isinstance(target_payload, dict):
            raise GameLifecycleError("Generic Shadow Legion target payload is malformed.")
        if target_payload.get("kind") != RuleTargetKind.THIS_UNIT.value:
            raise GameLifecycleError("Generic Shadow Legion effect target drift.")
    return dict(payload)


def _shadow_legion_effect_parameters(
    effect_payload: Mapping[str, JsonValue],
) -> dict[str, JsonValue]:
    raw_parameters = effect_payload.get("parameters")
    if not isinstance(raw_parameters, list):
        raise GameLifecycleError("Generic Shadow Legion effect parameters must be a list.")
    parameters: dict[str, JsonValue] = {}
    for raw_parameter in raw_parameters:
        if not isinstance(raw_parameter, dict):
            raise GameLifecycleError("Generic Shadow Legion effect parameter must be an object.")
        key = raw_parameter.get("key")
        if type(key) is not str:
            raise GameLifecycleError("Generic Shadow Legion effect parameter requires key.")
        resolved_key = _validate_identifier("parameter key", key)
        if resolved_key in parameters:
            raise GameLifecycleError("Generic Shadow Legion effect parameters must be unique.")
        parameters[resolved_key] = validate_json_value(raw_parameter.get("value"))
    return parameters


def _required_keywords_apply(
    *,
    parameters: Mapping[str, JsonValue],
    rules_unit: RulesUnitView,
) -> bool:
    required_keywords: list[str] = []
    required_keyword = parameters.get("required_keyword")
    if required_keyword is not None:
        if type(required_keyword) is not str:
            raise GameLifecycleError("Generic Shadow Legion required_keyword must be a string.")
        required_keywords.append(required_keyword)
    required_sequence = parameters.get("required_keyword_sequence")
    if required_sequence is not None:
        if not isinstance(required_sequence, list):
            raise GameLifecycleError(
                "Generic Shadow Legion required_keyword_sequence must be a list."
            )
        for item in required_sequence:
            if type(item) is not str:
                raise GameLifecycleError(
                    "Generic Shadow Legion required_keyword_sequence must contain strings."
                )
            required_keywords.append(item)
    if not required_keywords:
        return True
    return all(_rules_unit_has_keyword(rules_unit, keyword) for keyword in required_keywords)


def _rules_unit_has_keyword(rules_unit: RulesUnitView, keyword: str) -> bool:
    if type(rules_unit) is not RulesUnitView:
        raise GameLifecycleError("Generic Shadow Legion keyword lookup requires RulesUnitView.")
    requested_keyword = _canonical_keyword(_validate_identifier("keyword", keyword))
    return requested_keyword in {_canonical_keyword(stored) for stored in rules_unit.keywords}


def _rules_unit_is_belakor(*, state: GameState, unit_instance_id: str) -> bool:
    if type(state) is not GameState:
        raise GameLifecycleError("Generic Shadow Legion Be'lakor lookup requires GameState.")
    rules_unit = rules_unit_view_by_id(state=state, unit_instance_id=unit_instance_id)
    return any(_unit_is_belakor(component.unit) for component in rules_unit.components)


def _unit_is_belakor(unit: UnitInstance) -> bool:
    if type(unit) is not UnitInstance:
        raise GameLifecycleError("Generic Shadow Legion Be'lakor lookup requires UnitInstance.")
    return _canonical_name(unit.name) == "BELAKOR"


def _shadow_legion_dark_pact_source_context(
    *,
    source: _GenericShadowLegionSource,
    matching_effects: tuple[PersistingEffect, ...],
    extra_context: dict[str, JsonValue],
) -> JsonValue:
    return validate_json_value(
        {
            "source_rule_id": _SHADOW_LEGION_DARK_PACT_SOURCE_RULE_ID,
            "coverage_descriptor_id": source.record.coverage_descriptor_id,
            "execution_id": source.record.execution_id,
            "rule_ir_source_id": source.rule_ir.source_id,
            "rule_ir_hash": source.rule_ir.ir_hash(),
            "persisting_effect_ids": [effect.effect_id for effect in matching_effects],
            **extra_context,
        }
    )


def _shadow_legion_dark_pact_replay_payload(
    *,
    source: _GenericShadowLegionSource,
    matching_effects: tuple[PersistingEffect, ...],
    pact: str,
    trigger: str,
    unit_instance_id: str,
    extra_context: dict[str, JsonValue],
) -> JsonValue:
    return validate_json_value(
        {
            "effect_kind": _DARK_PACT_EFFECT_KIND,
            "selected_dark_pact": _validate_identifier("selected_dark_pact", pact),
            "trigger": _validate_identifier("trigger", trigger),
            "unit_instance_id": _validate_identifier("unit_instance_id", unit_instance_id),
            "source_rule_id": _SHADOW_LEGION_DARK_PACT_SOURCE_RULE_ID,
            "coverage_descriptor_id": source.record.coverage_descriptor_id,
            "execution_id": source.record.execution_id,
            "rule_ir_source_id": source.rule_ir.source_id,
            "rule_ir_hash": source.rule_ir.ir_hash(),
            "persisting_effect_ids": [effect.effect_id for effect in matching_effects],
            **extra_context,
        }
    )


def _payload_object(payload: Mapping[str, JsonValue], *, key: str) -> dict[str, JsonValue]:
    value = payload.get(key)
    if not isinstance(value, dict):
        raise GameLifecycleError(f"Generic Shadow Legion payload requires {key}.")
    return dict(value)


def _record_is_generic_detachment_rule(record: _Phase17FExecutionRecord) -> bool:
    return (
        record.coverage_kind is faction_coverage_2026_27.Phase17ECoverageKind.DETACHMENT_RULE
        and record.execution_status
        is faction_execution_2026_27.Phase17FExecutionStatus.EXECUTABLE_GENERIC_IR
    )


def _record_is_generic_enhancement(record: _Phase17FExecutionRecord) -> bool:
    return (
        record.coverage_kind is faction_coverage_2026_27.Phase17ECoverageKind.DETACHMENT_ENHANCEMENT
        and record.execution_status
        is faction_execution_2026_27.Phase17FExecutionStatus.EXECUTABLE_GENERIC_IR
    )


def _record_rule_id(record: _Phase17FExecutionRecord) -> str:
    if record.rule_id is None:
        raise GameLifecycleError("Generic lifecycle execution record requires rule_id.")
    return record.rule_id


def _rule_ir_for_record(record: _Phase17FExecutionRecord) -> RuleIR:
    rule_ir = faction_generic_ir_support_2026_27.generic_rule_ir_by_coverage_descriptor_id(
        record.coverage_descriptor_id
    )
    _validate_record_rule_ir_hash(record=record, rule_ir=rule_ir)
    return rule_ir


def _validate_record_rule_ir_hash(*, record: _Phase17FExecutionRecord, rule_ir: RuleIR) -> None:
    if record.rule_ir_hash is None:
        raise GameLifecycleError("Generic lifecycle execution record requires rule_ir_hash.")
    if rule_ir.ir_hash() != record.rule_ir_hash:
        raise GameLifecycleError("Generic lifecycle execution record has stale RuleIR hash.")


def _rule_ir_grants_any_ability(rule_ir: RuleIR, *, abilities: tuple[str, ...]) -> bool:
    expected = set(_validate_identifier_tuple("generic ability", abilities))
    for clause in rule_ir.clauses:
        for effect in clause.effects:
            if effect.kind is not RuleEffectKind.GRANT_ABILITY:
                continue
            ability = parameter_payload(effect.parameters).get("ability")
            if type(ability) is str and ability in expected:
                return True
    return False


def _effect_payloads_grant_ability(
    effect_payloads: tuple[dict[str, JsonValue], ...],
    *,
    ability: str,
) -> bool:
    requested_ability = _validate_identifier("ability", ability)
    return any(
        generic_rule_effect_payload_grants_ability(payload, ability=requested_ability)
        for payload in effect_payloads
    )


def _single_grant_ability_payload(
    effect_payloads: tuple[dict[str, JsonValue], ...],
    *,
    ability: str,
) -> dict[str, JsonValue]:
    matching = tuple(
        payload
        for payload in effect_payloads
        if generic_rule_effect_payload_grants_ability(payload, ability=ability)
    )
    if len(matching) != 1:
        raise GameLifecycleError("Generic fight activation RuleIR must grant exactly one ability.")
    return matching[0]


def _effect_parameters(effect_payload: Mapping[str, JsonValue]) -> dict[str, JsonValue]:
    raw_effect = effect_payload.get("effect")
    if not isinstance(raw_effect, dict):
        raise GameLifecycleError("Generic lifecycle effect payload requires effect object.")
    raw_parameters = raw_effect.get("parameters")
    if not isinstance(raw_parameters, list):
        raise GameLifecycleError("Generic lifecycle effect payload requires parameters.")
    parameters: dict[str, JsonValue] = {}
    for raw_parameter in raw_parameters:
        if not isinstance(raw_parameter, dict):
            raise GameLifecycleError("Generic lifecycle effect parameter must be an object.")
        key = raw_parameter.get("key")
        if type(key) is not str:
            raise GameLifecycleError("Generic lifecycle effect parameter requires key.")
        if key in parameters:
            raise GameLifecycleError("Generic lifecycle effect parameters must be unique.")
        parameters[key] = validate_json_value(raw_parameter.get("value"))
    return parameters


def _optional_bool_parameter(parameters: Mapping[str, JsonValue], key: str) -> bool:
    value = parameters.get(key)
    if value is None:
        return False
    if type(value) is not bool:
        raise GameLifecycleError(f"Generic lifecycle parameter {key} must be a bool.")
    return value


def _positive_float_parameter(parameters: Mapping[str, JsonValue], key: str) -> float:
    value = parameters.get(key)
    if type(value) is int:
        converted = float(value)
    elif type(value) is float:
        converted = value
    else:
        raise GameLifecycleError(f"Generic lifecycle parameter {key} must be numeric.")
    if converted <= 0.0:
        raise GameLifecycleError(f"Generic lifecycle parameter {key} must be positive.")
    return converted


def _unit_made_charge_move(*, state: GameState, unit_instance_id: str) -> bool:
    requested_unit_id = _validate_identifier("unit_instance_id", unit_instance_id)
    for effect in state.persisting_effects:
        if requested_unit_id not in effect.target_unit_instance_ids:
            continue
        effect_payload = effect.effect_payload
        if not isinstance(effect_payload, dict):
            continue
        if effect_payload.get("effect_kind") == CHARGE_FIGHTS_FIRST_EFFECT_KIND:
            return True
    return False


def _army_for_player(*, state: GameState, player_id: str) -> ArmyDefinition:
    requested_player_id = _validate_identifier("player_id", player_id)
    for army in state.army_definitions:
        if army.player_id == requested_player_id:
            return army
    raise GameLifecycleError("Generic lifecycle player army is unknown.")


def _army_uses_detachment_record(
    *,
    army: ArmyDefinition,
    record: _Phase17FExecutionRecord,
) -> bool:
    if record.detachment_id is None:
        raise GameLifecycleError("Generic lifecycle detachment record requires detachment_id.")
    return (
        army.detachment_selection.faction_id == record.faction_id
        and record.detachment_id in army.detachment_selection.detachment_ids
    )


def _unit_in_army(*, army: ArmyDefinition, unit_instance_id: str) -> UnitInstance:
    requested_unit_id = _validate_identifier("unit_instance_id", unit_instance_id)
    for unit in army.units:
        if unit.unit_instance_id == requested_unit_id:
            return unit
    raise GameLifecycleError("Generic lifecycle target unit is not in the selected player army.")


def _assignments_by_enhancement_id(
    activation: RuntimeContentActivation,
) -> Mapping[str, Mapping[str, RuntimeEnhancementAssignment]]:
    assignments_by_enhancement_id: dict[str, dict[str, RuntimeEnhancementAssignment]] = {}
    for assignment in activation.selected_enhancement_assignments:
        assignments_by_bearer = assignments_by_enhancement_id.setdefault(
            assignment.enhancement_id,
            {},
        )
        existing = assignments_by_bearer.get(assignment.bearer_unit_instance_id)
        if existing is not None:
            raise GameLifecycleError("Generic lifecycle enhancement assignment is duplicated.")
        assignments_by_bearer[assignment.bearer_unit_instance_id] = assignment
    return MappingProxyType(
        {
            enhancement_id: MappingProxyType(assignments)
            for enhancement_id, assignments in assignments_by_enhancement_id.items()
        }
    )


def _validate_assignment_mapping(
    value: object,
) -> Mapping[str, RuntimeEnhancementAssignment]:
    if not isinstance(value, Mapping):
        raise GameLifecycleError("Generic lifecycle assignments must be a mapping.")
    validated: dict[str, RuntimeEnhancementAssignment] = {}
    for unit_id, assignment in cast(Mapping[object, object], value).items():
        resolved_unit_id = _validate_identifier("bearer_unit_instance_id", unit_id)
        if type(assignment) is not RuntimeEnhancementAssignment:
            raise GameLifecycleError(
                "Generic lifecycle assignment mapping requires runtime assignments."
            )
        if assignment.bearer_unit_instance_id != resolved_unit_id:
            raise GameLifecycleError("Generic lifecycle assignment bearer drift.")
        validated[resolved_unit_id] = assignment
    return MappingProxyType(dict(sorted(validated.items())))


def _fall_back_hook_id(record: _Phase17FExecutionRecord) -> str:
    return _validate_identifier(
        "generic fall back hook_id",
        f"{record.execution_id}:fall-back-eligibility",
    )


def _fight_activation_hook_id(record: _Phase17FExecutionRecord) -> str:
    return _validate_identifier(
        "generic fight activation hook_id",
        f"{record.execution_id}:fight-activation-ability",
    )


def _shadow_legion_advance_hook_id(record: _Phase17FExecutionRecord) -> str:
    return _validate_identifier(
        "generic Shadow Legion advance hook_id",
        f"{record.execution_id}:shadow-legion:advance-eligibility",
    )


def _shadow_legion_snap_restriction_hook_id(record: _Phase17FExecutionRecord) -> str:
    return _validate_identifier(
        "generic Shadow Legion snap restriction hook_id",
        f"{record.execution_id}:shadow-legion:snap-target-restriction",
    )


def _shadow_legion_shooting_dark_pact_hook_id(
    record: _Phase17FExecutionRecord,
    pact: str,
) -> str:
    return _validate_identifier(
        "generic Shadow Legion shooting Dark Pact hook_id",
        f"{record.execution_id}:shadow-legion:shooting:{pact}",
    )


def _shadow_legion_fight_dark_pact_hook_id(
    record: _Phase17FExecutionRecord,
    pact: str,
) -> str:
    return _validate_identifier(
        "generic Shadow Legion Fight Dark Pact hook_id",
        f"{record.execution_id}:shadow-legion:fight:{pact}",
    )


def _shadow_legion_dark_pact_completion_hook_id(record: _Phase17FExecutionRecord) -> str:
    return _validate_identifier(
        "generic Shadow Legion Dark Pact completion hook_id",
        f"{record.execution_id}:shadow-legion:dark-pact-completion",
    )


def _shadow_legion_dark_pact_mortal_wound_fnp_hook_id(
    record: _Phase17FExecutionRecord,
) -> str:
    return _validate_identifier(
        "generic Shadow Legion Dark Pact FNP hook_id",
        f"{record.execution_id}:shadow-legion:dark-pact-mortal-wound-fnp",
    )


def _shadow_legion_dark_pact_weapon_profile_modifier_id(
    record: _Phase17FExecutionRecord,
) -> str:
    return _validate_identifier(
        "generic Shadow Legion Dark Pact weapon profile modifier_id",
        f"{record.execution_id}:shadow-legion:dark-pact-weapon-profile",
    )


def _canonical_keyword(value: str) -> str:
    return value.strip().upper().replace("_", " ").replace("-", " ")


def _canonical_name(value: str) -> str:
    return "".join(
        character
        for character in _validate_identifier("name", value).upper()
        if character.isalnum()
    )


def _validate_identifier_tuple(field_name: str, values: object) -> tuple[str, ...]:
    if type(values) is not tuple:
        raise GameLifecycleError(f"{field_name} must be a tuple.")
    raw_values = cast(tuple[object, ...], values)
    return tuple(_validate_identifier(f"{field_name} value", value) for value in raw_values)


_validate_identifier = IdentifierValidator(GameLifecycleError)
