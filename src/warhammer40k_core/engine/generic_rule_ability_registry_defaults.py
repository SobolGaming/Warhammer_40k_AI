from __future__ import annotations

from collections.abc import Mapping
from types import MappingProxyType
from typing import Protocol, cast

from warhammer40k_core.core.validation import IdentifierValidator
from warhammer40k_core.core.weapon_profiles import WeaponProfile
from warhammer40k_core.engine.advance_eligibility_hooks import (
    AdvanceEligibilityContext,
    AdvanceEligibilityGrant,
)
from warhammer40k_core.engine.army_mustering import ArmyDefinition
from warhammer40k_core.engine.attack_sequence_completion_hooks import (
    AttackSequenceCompletedContext,
)
from warhammer40k_core.engine.battlefield_state import (
    BattlefieldScenario,
    UnitPlacement,
    geometry_model_for_placement,
)
from warhammer40k_core.engine.decision_request import DecisionRequest
from warhammer40k_core.engine.effects import PersistingEffect
from warhammer40k_core.engine.enhancement_effects import EnhancementEffectContext
from warhammer40k_core.engine.event_log import JsonValue, validate_json_value
from warhammer40k_core.engine.fight_phase_start_hooks import (
    FightPhaseStartRequestContext,
    FightPhaseStartResultContext,
)
from warhammer40k_core.engine.fight_unit_selected_hooks import (
    FightUnitSelectedContext,
    FightUnitSelectedGrant,
)
from warhammer40k_core.engine.game_state import GameState
from warhammer40k_core.engine.generic_rule_ability_effects import (
    generic_rule_ability_effects_for_unit,
    generic_rule_ability_source_context_payload,
    generic_rule_ability_unit_for_player_context,
    generic_rule_advance_context_unit_id,
    generic_rule_army_for_player,
    generic_rule_army_uses_record,
    generic_rule_fight_unit_selected_unit_id,
    generic_rule_persisting_effect_ids,
    generic_rule_shooting_target_restriction_target_unit_id,
    generic_rule_shooting_unit_selected_unit_id,
)
from warhammer40k_core.engine.generic_rule_ability_registry import (
    FightUnitSelectedGrantBuilder,
    GenericRuleAbilityRegistry,
    GenericRuleAbilitySource,
    GenericRuleAdvanceEligibilityAbility,
    GenericRuleAttackSequenceCompletedAbility,
    GenericRuleEnhancementEffectAbility,
    GenericRuleFightPhaseStartAbility,
    GenericRuleFightUnitSelectedGrantAbility,
    GenericRuleHookIdBuilder,
    GenericRuleMortalWoundFeelNoPainAbility,
    GenericRuleMovementEndSurgeAbility,
    GenericRuleObjectiveControlModifierAbility,
    GenericRulePhaseEndObjectiveControlAbility,
    GenericRuleShootingTargetRestrictionAbility,
    GenericRuleShootingUnitSelectedGrantAbility,
    GenericRuleTurnEndAbility,
    GenericRuleUnitDestroyedAbility,
    GenericRuleWeaponProfileModifierAbility,
    ShootingUnitSelectedGrantBuilder,
)
from warhammer40k_core.engine.generic_rule_ability_registry_aeldari_defaults import (
    aeldari_corsair_coterie_battle_formation_abilities,
    aeldari_corsair_coterie_enhancement_effect_abilities,
    aeldari_corsair_coterie_objective_control_modifier_abilities,
    aeldari_corsair_coterie_save_option_modifier_abilities,
    aeldari_corsair_coterie_stratagem_cost_choice_abilities,
    aeldari_corsair_coterie_stratagem_cost_modifier_abilities,
    aeldari_corsair_coterie_turn_end_abilities,
    aeldari_path_of_the_outcast_enhancement_effect_abilities,
)
from warhammer40k_core.engine.generic_rule_ability_registry_emperors_children_defaults import (
    emperors_children_court_of_the_phoenician_stratagem_cost_modifier_abilities,
)
from warhammer40k_core.engine.mortal_wound_feel_no_pain_hooks import (
    MortalWoundFeelNoPainContinuationContext,
)
from warhammer40k_core.engine.movement_end_surge_hooks import (
    MovementEndSurgeContext,
    MovementEndSurgeGrant,
)
from warhammer40k_core.engine.objective_control import (
    ObjectiveControlContext,
    ObjectiveControlRecord,
    ObjectiveControlResult,
    ObjectiveControlTiming,
    resolve_objective_control,
)
from warhammer40k_core.engine.phase import BattlePhase, GameLifecycleError, LifecycleStatus
from warhammer40k_core.engine.runtime_modifiers import (
    ObjectiveControlModifierContext,
    WeaponProfileModifierContext,
)
from warhammer40k_core.engine.shooting_types import ShootingType
from warhammer40k_core.engine.shooting_unit_selected_hooks import (
    ShootingUnitSelectedContext,
    ShootingUnitSelectedGrant,
)
from warhammer40k_core.engine.sticky_objective_control import (
    PhaseEndObjectiveControlContext,
    StickyObjectiveControlState,
)
from warhammer40k_core.engine.target_restriction_hooks import (
    ShootingTargetRestrictionContext,
    TargetRestriction,
)
from warhammer40k_core.engine.turn_end_hooks import TurnEndRequestContext, TurnEndResultContext
from warhammer40k_core.engine.unit_destroyed_hooks import UnitDestroyedContext
from warhammer40k_core.engine.unit_factory import UnitInstance
from warhammer40k_core.rules.source_packages.warhammer_40000_11th import (
    faction_blood_legion_ir_support_2026_27 as blood_legion_ir,
)
from warhammer40k_core.rules.source_packages.warhammer_40000_11th import (
    faction_shadow_legion_ir_support_2026_27 as shadow_legion_ir,
)

_DARK_PACT_LETHAL_HITS = "lethal_hits"
_DARK_PACT_SUSTAINED_HITS_1 = "sustained_hits_1"
_DARK_PACT_EFFECT_KIND = "chaos_space_marines_dark_pact"
_SHADOW_LEGION_SOURCE_RULE_ID = "phase17f:phase17e:chaos-daemons:shadow-legion:rule"
_SHADOW_LEGION_DARK_PACT_MORTAL_WOUNDS_SOURCE_KIND = "chaos_daemons_shadow_legion_dark_pacts"


class _ShadowLegionEnhancementsModule(Protocol):
    LEAPING_SHADOWS_EFFECT_ID: str
    MANTLE_OF_GLOOM_OBJECTIVE_CONTROL_MODIFIER_ID: str
    UNIT_DESTROYED_HOOK_ID: str
    TURN_END_HOOK_ID: str
    MALICE_MADE_MANIFEST_HOOK_ID: str
    MALICE_MADE_MANIFEST_MORTAL_WOUND_FNP_HOOK_ID: str

    def leaping_shadows_effect(
        self,
        context: EnhancementEffectContext,
    ) -> tuple[object, ...]: ...

    def mantle_of_gloom_objective_control_modifier(
        self,
        context: ObjectiveControlModifierContext,
    ) -> int: ...

    def record_fade_to_darkness_destroyed_enemy_unit(
        self,
        context: UnitDestroyedContext,
    ) -> None: ...

    def fade_to_darkness_turn_end_request(
        self,
        context: TurnEndRequestContext,
    ) -> DecisionRequest | None: ...

    def apply_fade_to_darkness_turn_end_result(
        self,
        context: TurnEndResultContext,
    ) -> bool: ...

    def malice_made_manifest_fight_phase_start_request(
        self,
        context: FightPhaseStartRequestContext,
    ) -> DecisionRequest | None: ...

    def apply_malice_made_manifest_fight_phase_start_result(
        self,
        context: FightPhaseStartResultContext,
    ) -> bool | LifecycleStatus: ...

    def apply_malice_made_manifest_mortal_wound_feel_no_pain_decision(
        self,
        context: MortalWoundFeelNoPainContinuationContext,
    ) -> LifecycleStatus | None: ...


def _shadow_legion_advance_context_predicate(
    context: AdvanceEligibilityContext,
    source: GenericRuleAbilitySource,
    matching_effects: tuple[PersistingEffect, ...],
) -> bool:
    if not matching_effects:
        return False
    return (
        generic_rule_ability_unit_for_player_context(
            state=context.state,
            player_id=context.player_id,
            unit_instance_id=context.unit_instance_id,
            source=source,
        )
        is not None
    )


def _shadow_legion_advance_grant(
    context: AdvanceEligibilityContext,
    source: GenericRuleAbilitySource,
    matching_effects: tuple[PersistingEffect, ...],
) -> AdvanceEligibilityGrant:
    return AdvanceEligibilityGrant(
        hook_id=_shadow_legion_advance_hook_id(source),
        source_id=_SHADOW_LEGION_SOURCE_RULE_ID,
        can_shoot=True,
        can_declare_charge=True,
        replay_payload=validate_json_value(
            {
                "effect_kind": "generic_rule_advance_eligibility",
                "coverage_descriptor_id": source.record.coverage_descriptor_id,
                "execution_id": source.record.execution_id,
                "rule_ir_hash": source.rule_ir.ir_hash(),
                "persisting_effect_ids": generic_rule_persisting_effect_ids(matching_effects),
                "unit_instance_id": context.unit_instance_id,
                "movement_request_id": context.movement_request_id,
                "movement_result_id": context.movement_result_id,
            }
        ),
    )


def _shadow_legion_snap_target_context_predicate(
    context: ShootingTargetRestrictionContext,
    source: GenericRuleAbilitySource,
    matching_effects: tuple[PersistingEffect, ...],
) -> bool:
    if not matching_effects:
        return False
    if context.shooting_type is not ShootingType.SNAP:
        return False
    from warhammer40k_core.engine.rules_units import rules_unit_view_by_id

    target_rules_unit = rules_unit_view_by_id(
        state=context.state,
        unit_instance_id=context.target_unit_instance_id,
    )
    target_army = generic_rule_army_for_player(
        state=context.state, player_id=target_rules_unit.owner_player_id
    )
    return generic_rule_army_uses_record(army=target_army, source=source)


def _shadow_legion_snap_target_restriction(
    context: ShootingTargetRestrictionContext,
    source: GenericRuleAbilitySource,
    matching_effects: tuple[PersistingEffect, ...],
) -> TargetRestriction:
    return TargetRestriction(
        hook_id=_shadow_legion_snap_restriction_hook_id(source),
        source_id=_SHADOW_LEGION_SOURCE_RULE_ID,
        violation_code="shadow_legion_shadows_caress_snap_target_forbidden",
        message="Shadow Legion units cannot be targeted by Snap Shooting attacks.",
        replay_payload=validate_json_value(
            {
                "effect_kind": "generic_rule_snap_target_restriction",
                "coverage_descriptor_id": source.record.coverage_descriptor_id,
                "execution_id": source.record.execution_id,
                "rule_ir_hash": source.rule_ir.ir_hash(),
                "persisting_effect_ids": generic_rule_persisting_effect_ids(matching_effects),
                "battle_round": context.battle_round,
                "attacking_unit_instance_id": context.attacking_unit_instance_id,
                "target_unit_instance_id": context.target_unit_instance_id,
                "shooting_type": ShootingType.SNAP.value,
            }
        ),
    )


def _shadow_legion_shooting_dark_pact_context_predicate(
    context: ShootingUnitSelectedContext,
    source: GenericRuleAbilitySource,
    matching_effects: tuple[PersistingEffect, ...],
) -> bool:
    from warhammer40k_core.engine.faction_content.warhammer_40000_11th.chaos_space_marines import (
        army_rule as dark_pacts,
    )

    if not matching_effects:
        return False
    if (
        generic_rule_ability_unit_for_player_context(
            state=context.state,
            player_id=context.player_id,
            unit_instance_id=context.unit_instance_id,
            source=source,
        )
        is None
    ):
        return False
    return (
        dark_pacts.active_dark_pact_for_unit(
            context.state,
            unit_instance_id=context.unit_instance_id,
            phase=BattlePhase.SHOOTING,
        )
        is None
    )


def _shadow_legion_fight_dark_pact_context_predicate(
    context: FightUnitSelectedContext,
    source: GenericRuleAbilitySource,
    matching_effects: tuple[PersistingEffect, ...],
) -> bool:
    from warhammer40k_core.engine.faction_content.warhammer_40000_11th.chaos_space_marines import (
        army_rule as dark_pacts,
    )

    if not matching_effects:
        return False
    if (
        generic_rule_ability_unit_for_player_context(
            state=context.state,
            player_id=context.player_id,
            unit_instance_id=context.unit_instance_id,
            source=source,
        )
        is None
    ):
        return False
    return (
        dark_pacts.active_dark_pact_for_unit(
            context.state,
            unit_instance_id=context.unit_instance_id,
            phase=BattlePhase.FIGHT,
        )
        is None
    )


def _shadow_legion_shooting_dark_pact_grant_builder(
    pact: str,
    label: str,
) -> ShootingUnitSelectedGrantBuilder:
    def builder(
        context: ShootingUnitSelectedContext,
        source: GenericRuleAbilitySource,
        matching_effects: tuple[PersistingEffect, ...],
    ) -> ShootingUnitSelectedGrant:
        from warhammer40k_core.engine.faction_content.warhammer_40000_11th.chaos_space_marines import (  # noqa: E501
            army_rule as dark_pacts,
        )

        target_unit_ids = dark_pacts.dark_pact_target_unit_ids(
            context.state,
            unit_instance_id=context.unit_instance_id,
        )
        selected_pact = dark_pacts.DarkPactKind(pact)
        extra_context: dict[str, JsonValue] = {
            "selection_request_id": context.request_id,
            "selection_result_id": context.result_id,
        }
        return ShootingUnitSelectedGrant(
            hook_id=_shadow_legion_shooting_dark_pact_hook_id(source, pact),
            source_id=_SHADOW_LEGION_SOURCE_RULE_ID,
            label=label,
            replay_payload=_shadow_legion_dark_pact_replay_payload(
                source=source,
                matching_effects=matching_effects,
                pact=pact,
                trigger="selected_to_shoot",
                unit_instance_id=context.unit_instance_id,
                extra_context=extra_context,
            ),
            unit_effect_payload=dark_pacts.dark_pact_effect_payload(
                unit_instance_id=context.unit_instance_id,
                target_unit_instance_ids=target_unit_ids,
                trigger="selected_to_shoot",
                phase=BattlePhase.SHOOTING,
                selected_dark_pact=selected_pact,
                source_context=generic_rule_ability_source_context_payload(
                    source=source,
                    matching_effects=matching_effects,
                    source_rule_id=_SHADOW_LEGION_SOURCE_RULE_ID,
                    extra_context=extra_context,
                ),
                leadership_test_auto_pass=_rules_unit_is_belakor(
                    state=context.state,
                    unit_instance_id=context.unit_instance_id,
                ),
            ),
            unit_effect_expiration="end_phase",
        )

    return builder


def _shadow_legion_fight_dark_pact_grant_builder(
    pact: str,
    label: str,
) -> FightUnitSelectedGrantBuilder:
    def builder(
        context: FightUnitSelectedContext,
        source: GenericRuleAbilitySource,
        matching_effects: tuple[PersistingEffect, ...],
    ) -> FightUnitSelectedGrant:
        from warhammer40k_core.engine.faction_content.warhammer_40000_11th.chaos_space_marines import (  # noqa: E501
            army_rule as dark_pacts,
        )

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
            hook_id=_shadow_legion_fight_dark_pact_hook_id(source, pact),
            source_id=_SHADOW_LEGION_SOURCE_RULE_ID,
            label=label,
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
                source_context=generic_rule_ability_source_context_payload(
                    source=source,
                    matching_effects=matching_effects,
                    source_rule_id=_SHADOW_LEGION_SOURCE_RULE_ID,
                    extra_context=extra_context,
                ),
                leadership_test_auto_pass=_rules_unit_is_belakor(
                    state=context.state,
                    unit_instance_id=context.unit_instance_id,
                ),
            ),
            unit_effect_expiration="end_phase",
        )

    return builder


def _shadow_legion_dark_pact_replay_payload(
    *,
    source: GenericRuleAbilitySource,
    matching_effects: tuple[PersistingEffect, ...],
    pact: str,
    trigger: str,
    unit_instance_id: str,
    extra_context: Mapping[str, JsonValue],
) -> JsonValue:
    return validate_json_value(
        {
            "effect_kind": _DARK_PACT_EFFECT_KIND,
            "selected_dark_pact": _validate_identifier("selected_dark_pact", pact),
            "trigger": _validate_identifier("trigger", trigger),
            "unit_instance_id": _validate_identifier("unit_instance_id", unit_instance_id),
            "source_rule_id": _SHADOW_LEGION_SOURCE_RULE_ID,
            "coverage_descriptor_id": source.record.coverage_descriptor_id,
            "execution_id": source.record.execution_id,
            "rule_ir_source_id": source.rule_ir.source_id,
            "rule_ir_hash": source.rule_ir.ir_hash(),
            "persisting_effect_ids": generic_rule_persisting_effect_ids(matching_effects),
            **dict(extra_context),
        }
    )


def _rules_unit_is_belakor(*, state: GameState, unit_instance_id: str) -> bool:
    if type(state) is not GameState:
        raise GameLifecycleError("Generic RuleIR ability Be'lakor lookup requires GameState.")
    from warhammer40k_core.engine.rules_units import rules_unit_view_by_id

    rules_unit = rules_unit_view_by_id(state=state, unit_instance_id=unit_instance_id)
    return any(_unit_is_belakor(component.unit) for component in rules_unit.components)


def _unit_is_belakor(unit: UnitInstance) -> bool:
    if type(unit) is not UnitInstance:
        raise GameLifecycleError("Generic RuleIR ability Be'lakor lookup requires UnitInstance.")
    return _canonical_name(unit.name) == "BELAKOR"


def _shadow_legion_advance_hook_id(source: GenericRuleAbilitySource) -> str:
    return _validate_identifier(
        "generic Shadow Legion advance hook_id",
        f"{source.record.execution_id}:shadow-legion:advance-eligibility",
    )


def _shadow_legion_snap_restriction_hook_id(source: GenericRuleAbilitySource) -> str:
    return _validate_identifier(
        "generic Shadow Legion snap restriction hook_id",
        f"{source.record.execution_id}:shadow-legion:snap-target-restriction",
    )


def _shadow_legion_shooting_dark_pact_hook_id(
    source: GenericRuleAbilitySource,
    pact: str,
) -> str:
    return _validate_identifier(
        "generic Shadow Legion shooting Dark Pact hook_id",
        f"{source.record.execution_id}:shadow-legion:shooting:{pact}",
    )


def _shadow_legion_fight_dark_pact_hook_id(
    source: GenericRuleAbilitySource,
    pact: str,
) -> str:
    return _validate_identifier(
        "generic Shadow Legion Fight Dark Pact hook_id",
        f"{source.record.execution_id}:shadow-legion:fight:{pact}",
    )


def _shadow_legion_shooting_dark_pact_hook_id_builder(
    pact: str,
) -> GenericRuleHookIdBuilder:
    validated_pact = _validate_identifier("generic Shadow Legion shooting Dark Pact kind", pact)

    def builder(source: GenericRuleAbilitySource) -> str:
        return _shadow_legion_shooting_dark_pact_hook_id(source, validated_pact)

    return builder


def _shadow_legion_fight_dark_pact_hook_id_builder(
    pact: str,
) -> GenericRuleHookIdBuilder:
    validated_pact = _validate_identifier("generic Shadow Legion Fight Dark Pact kind", pact)

    def builder(source: GenericRuleAbilitySource) -> str:
        return _shadow_legion_fight_dark_pact_hook_id(source, validated_pact)

    return builder


def _shadow_legion_dark_pact_completion_hook_id(source: GenericRuleAbilitySource) -> str:
    return _validate_identifier(
        "generic Shadow Legion Dark Pact completion hook_id",
        f"{source.record.execution_id}:shadow-legion:dark-pact-completion",
    )


def _shadow_legion_dark_pact_mortal_wound_fnp_hook_id(
    source: GenericRuleAbilitySource,
) -> str:
    return _validate_identifier(
        "generic Shadow Legion Dark Pact FNP hook_id",
        f"{source.record.execution_id}:shadow-legion:dark-pact-mortal-wound-fnp",
    )


def _shadow_legion_dark_pact_weapon_profile_modifier_id(
    source: GenericRuleAbilitySource,
) -> str:
    return _validate_identifier(
        "generic Shadow Legion Dark Pact weapon profile modifier_id",
        f"{source.record.execution_id}:shadow-legion:dark-pact-weapon-profile",
    )


_DARK_PACT_CHOICE_ABILITY_BY_PACT: Mapping[str, str] = MappingProxyType(
    {
        _DARK_PACT_LETHAL_HITS: (
            shadow_legion_ir.SHADOW_LEGION_DARK_PACT_LETHAL_HITS_CHOICE_ABILITY
        ),
        _DARK_PACT_SUSTAINED_HITS_1: (
            shadow_legion_ir.SHADOW_LEGION_DARK_PACT_SUSTAINED_HITS_1_CHOICE_ABILITY
        ),
    }
)
_DARK_PACT_LABEL_BY_PACT: Mapping[str, str] = MappingProxyType(
    {
        _DARK_PACT_LETHAL_HITS: "Dark Pacts: Lethal Hits",
        _DARK_PACT_SUSTAINED_HITS_1: "Dark Pacts: Sustained Hits 1",
    }
)
_SHADOW_LEGION_DARK_PACT_ABILITY_IDS = tuple(_DARK_PACT_CHOICE_ABILITY_BY_PACT.values())


def _shadow_legion_shooting_dark_pact_abilities() -> tuple[
    GenericRuleShootingUnitSelectedGrantAbility,
    ...,
]:
    return tuple(
        GenericRuleShootingUnitSelectedGrantAbility(
            ability_id=ability,
            coverage_descriptor_id=shadow_legion_ir.SHADOW_LEGION_DETACHMENT_RULE_DESCRIPTOR_ID,
            source_rule_id=_SHADOW_LEGION_SOURCE_RULE_ID,
            hook_id_builder=_shadow_legion_shooting_dark_pact_hook_id_builder(pact),
            target_unit_id_builder=generic_rule_shooting_unit_selected_unit_id,
            context_predicate=_shadow_legion_shooting_dark_pact_context_predicate,
            grant_builder=_shadow_legion_shooting_dark_pact_grant_builder(
                pact,
                _DARK_PACT_LABEL_BY_PACT[pact],
            ),
        )
        for pact, ability in _DARK_PACT_CHOICE_ABILITY_BY_PACT.items()
    )


def _shadow_legion_fight_dark_pact_abilities() -> tuple[
    GenericRuleFightUnitSelectedGrantAbility,
    ...,
]:
    return tuple(
        GenericRuleFightUnitSelectedGrantAbility(
            ability_id=ability,
            coverage_descriptor_id=shadow_legion_ir.SHADOW_LEGION_DETACHMENT_RULE_DESCRIPTOR_ID,
            source_rule_id=_SHADOW_LEGION_SOURCE_RULE_ID,
            hook_id_builder=_shadow_legion_fight_dark_pact_hook_id_builder(pact),
            target_unit_id_builder=generic_rule_fight_unit_selected_unit_id,
            context_predicate=_shadow_legion_fight_dark_pact_context_predicate,
            grant_builder=_shadow_legion_fight_dark_pact_grant_builder(
                pact,
                _DARK_PACT_LABEL_BY_PACT[pact],
            ),
        )
        for pact, ability in _DARK_PACT_CHOICE_ABILITY_BY_PACT.items()
    )


def _resolve_shadow_legion_dark_pact_attack_sequence_completion(
    context: AttackSequenceCompletedContext,
) -> LifecycleStatus | None:
    from warhammer40k_core.engine.faction_content.warhammer_40000_11th.chaos_space_marines import (
        army_rule as dark_pacts,
    )

    return dark_pacts.resolve_dark_pact_attack_sequence_completion(context)


def _apply_shadow_legion_dark_pact_mortal_wound_feel_no_pain_decision(
    context: MortalWoundFeelNoPainContinuationContext,
) -> LifecycleStatus | None:
    from warhammer40k_core.engine.faction_content.warhammer_40000_11th.chaos_space_marines import (
        army_rule as dark_pacts,
    )

    return dark_pacts.apply_dark_pact_mortal_wound_feel_no_pain_decision(context)


def _shadow_legion_dark_pact_weapon_profile_modifier(
    context: WeaponProfileModifierContext,
) -> WeaponProfile:
    from warhammer40k_core.engine.faction_content.warhammer_40000_11th.chaos_space_marines import (
        army_rule as dark_pacts,
    )

    return dark_pacts.dark_pact_weapon_profile_modifier(context)


def _shadow_legion_enhancements() -> _ShadowLegionEnhancementsModule:
    from warhammer40k_core.engine.faction_content.warhammer_40000_11th.chaos_daemons.detachments.shadow_legion import (  # noqa: E501
        enhancements,
    )

    return cast(_ShadowLegionEnhancementsModule, enhancements)


def _shadow_legion_enhancement_context_predicate(
    context: EnhancementEffectContext,
    source: GenericRuleAbilitySource,
) -> bool:
    if type(context) is not EnhancementEffectContext:
        raise GameLifecycleError("Shadow Legion enhancement effect requires context.")
    if type(source) is not GenericRuleAbilitySource:
        raise GameLifecycleError("Shadow Legion enhancement effect requires source.")
    return True


def _shadow_legion_objective_control_context_predicate(
    context: ObjectiveControlModifierContext,
    source: GenericRuleAbilitySource,
) -> bool:
    if type(context) is not ObjectiveControlModifierContext:
        raise GameLifecycleError("Shadow Legion objective-control modifier requires context.")
    if type(source) is not GenericRuleAbilitySource:
        raise GameLifecycleError("Shadow Legion objective-control modifier requires source.")
    return True


def _shadow_legion_leaping_shadows_effect_id(source: GenericRuleAbilitySource) -> str:
    if type(source) is not GenericRuleAbilitySource:
        raise GameLifecycleError("Leaping Shadows effect ID requires source.")
    return _shadow_legion_enhancements().LEAPING_SHADOWS_EFFECT_ID


def _shadow_legion_leaping_shadows_effect(
    context: EnhancementEffectContext,
    source: GenericRuleAbilitySource,
) -> tuple[object, ...]:
    if type(source) is not GenericRuleAbilitySource:
        raise GameLifecycleError("Leaping Shadows effect requires source.")
    return _shadow_legion_enhancements().leaping_shadows_effect(context)


def _shadow_legion_mantle_of_gloom_modifier_id(source: GenericRuleAbilitySource) -> str:
    if type(source) is not GenericRuleAbilitySource:
        raise GameLifecycleError("Mantle of Gloom modifier ID requires source.")
    return _shadow_legion_enhancements().MANTLE_OF_GLOOM_OBJECTIVE_CONTROL_MODIFIER_ID


def _shadow_legion_mantle_of_gloom_modifier(
    context: ObjectiveControlModifierContext,
    source: GenericRuleAbilitySource,
) -> int:
    if type(source) is not GenericRuleAbilitySource:
        raise GameLifecycleError("Mantle of Gloom modifier requires source.")
    return _shadow_legion_enhancements().mantle_of_gloom_objective_control_modifier(context)


def _shadow_legion_fade_to_darkness_unit_destroyed_hook_id(
    source: GenericRuleAbilitySource,
) -> str:
    if type(source) is not GenericRuleAbilitySource:
        raise GameLifecycleError("Fade to Darkness unit-destroyed hook ID requires source.")
    return _shadow_legion_enhancements().UNIT_DESTROYED_HOOK_ID


def _shadow_legion_fade_to_darkness_unit_destroyed(
    context: UnitDestroyedContext,
    source: GenericRuleAbilitySource,
) -> None:
    if type(source) is not GenericRuleAbilitySource:
        raise GameLifecycleError("Fade to Darkness unit-destroyed hook requires source.")
    _shadow_legion_enhancements().record_fade_to_darkness_destroyed_enemy_unit(context)


def _shadow_legion_fade_to_darkness_turn_end_hook_id(
    source: GenericRuleAbilitySource,
) -> str:
    if type(source) is not GenericRuleAbilitySource:
        raise GameLifecycleError("Fade to Darkness turn-end hook ID requires source.")
    return _shadow_legion_enhancements().TURN_END_HOOK_ID


def _shadow_legion_fade_to_darkness_turn_end_request(
    context: TurnEndRequestContext,
    source: GenericRuleAbilitySource,
) -> DecisionRequest | None:
    if type(source) is not GenericRuleAbilitySource:
        raise GameLifecycleError("Fade to Darkness turn-end request requires source.")
    return _shadow_legion_enhancements().fade_to_darkness_turn_end_request(context)


def _shadow_legion_fade_to_darkness_turn_end_result(
    context: TurnEndResultContext,
    source: GenericRuleAbilitySource,
) -> bool:
    if type(source) is not GenericRuleAbilitySource:
        raise GameLifecycleError("Fade to Darkness turn-end result requires source.")
    return _shadow_legion_enhancements().apply_fade_to_darkness_turn_end_result(context)


def _shadow_legion_malice_made_manifest_hook_id(source: GenericRuleAbilitySource) -> str:
    if type(source) is not GenericRuleAbilitySource:
        raise GameLifecycleError("Malice Made Manifest hook ID requires source.")
    return _shadow_legion_enhancements().MALICE_MADE_MANIFEST_HOOK_ID


def _shadow_legion_malice_made_manifest_request(
    context: FightPhaseStartRequestContext,
    source: GenericRuleAbilitySource,
) -> DecisionRequest | None:
    if type(source) is not GenericRuleAbilitySource:
        raise GameLifecycleError("Malice Made Manifest request requires source.")
    return _shadow_legion_enhancements().malice_made_manifest_fight_phase_start_request(context)


def _shadow_legion_malice_made_manifest_result(
    context: FightPhaseStartResultContext,
    source: GenericRuleAbilitySource,
) -> bool | LifecycleStatus:
    if type(source) is not GenericRuleAbilitySource:
        raise GameLifecycleError("Malice Made Manifest result requires source.")
    return _shadow_legion_enhancements().apply_malice_made_manifest_fight_phase_start_result(
        context
    )


def _shadow_legion_malice_made_manifest_fnp_hook_id(
    source: GenericRuleAbilitySource,
) -> str:
    if type(source) is not GenericRuleAbilitySource:
        raise GameLifecycleError("Malice Made Manifest FNP hook ID requires source.")
    return _shadow_legion_enhancements().MALICE_MADE_MANIFEST_MORTAL_WOUND_FNP_HOOK_ID


def _shadow_legion_malice_made_manifest_fnp(
    context: MortalWoundFeelNoPainContinuationContext,
) -> LifecycleStatus | None:
    return (
        _shadow_legion_enhancements().apply_malice_made_manifest_mortal_wound_feel_no_pain_decision(
            context
        )
    )


def _blood_legion_movement_end_surge_context_predicate(
    context: MovementEndSurgeContext,
    source: GenericRuleAbilitySource,
) -> bool:
    army = generic_rule_army_for_player(state=context.state, player_id=context.reacting_player_id)
    if not generic_rule_army_uses_record(army=army, source=source):
        return False
    triggering_unit = _triggering_unit(context)
    return not _unit_has_keyword(triggering_unit, blood_legion_ir.AIRCRAFT_KEYWORD)


def _blood_legion_murdercall_grants(
    context: MovementEndSurgeContext,
    source: GenericRuleAbilitySource,
) -> tuple[MovementEndSurgeGrant, ...]:
    army = generic_rule_army_for_player(state=context.state, player_id=context.reacting_player_id)
    if not generic_rule_army_uses_record(army=army, source=source):
        return ()
    scenario = _battlefield_scenario(context.state)
    triggering_placement = scenario.battlefield_state.unit_placement_by_id(
        context.triggering_unit_instance_id
    )
    triggering_unit = scenario.unit_instance_for_placement(triggering_placement)
    if _unit_has_keyword(triggering_unit, blood_legion_ir.AIRCRAFT_KEYWORD):
        return ()
    grants: list[MovementEndSurgeGrant] = []
    for unit in army.units:
        if unit.unit_instance_id in context.state.battle_shocked_unit_ids:
            continue
        matching_effects = generic_rule_ability_effects_for_unit(
            state=context.state,
            source=source,
            unit_instance_id=unit.unit_instance_id,
            ability=blood_legion_ir.MURDERCALL_SURGE_ABILITY,
        )
        if not matching_effects:
            continue
        unit_placement = _placed_unit_for_army(
            scenario=scenario,
            player_id=context.reacting_player_id,
            unit_instance_id=unit.unit_instance_id,
        )
        if unit_placement is None:
            continue
        if not _unit_placements_within(
            scenario=scenario,
            first=unit_placement,
            second=triggering_placement,
            distance_inches=blood_legion_ir.MURDERCALL_RANGE_INCHES,
        ):
            continue
        grants.append(
            MovementEndSurgeGrant(
                hook_id=blood_legion_ir.MURDERCALL_HOOK_ID,
                source_id=blood_legion_ir.BLOOD_LEGION_SOURCE_RULE_ID,
                unit_instance_id=unit.unit_instance_id,
                replay_payload=_blood_legion_murdercall_replay_payload(
                    context=context,
                    source=source,
                    matching_effects=matching_effects,
                    unit_instance_id=unit.unit_instance_id,
                ),
            )
        )
    return tuple(sorted(grants, key=lambda grant: grant.unit_instance_id))


def _blood_legion_murdercall_replay_payload(
    *,
    context: MovementEndSurgeContext,
    source: GenericRuleAbilitySource,
    matching_effects: tuple[PersistingEffect, ...],
    unit_instance_id: str,
) -> JsonValue:
    return generic_rule_ability_source_context_payload(
        source=source,
        matching_effects=matching_effects,
        source_rule_id=blood_legion_ir.BLOOD_LEGION_SOURCE_RULE_ID,
        extra_context={
            "effect_kind": "murdercall",
            "detachment_id": blood_legion_ir.BLOOD_LEGION_DETACHMENT_ID,
            "unit_instance_id": unit_instance_id,
            "reacting_player_id": context.reacting_player_id,
            "triggering_player_id": context.triggering_player_id,
            "triggering_unit_instance_id": context.triggering_unit_instance_id,
            "trigger_event_id": context.trigger_event_id,
            "movement_phase_action": context.movement_phase_action,
            "range_inches": blood_legion_ir.MURDERCALL_RANGE_INCHES,
            "required_faction_keyword": blood_legion_ir.LEGIONES_DAEMONICA_KEYWORD,
            "required_keyword": blood_legion_ir.KHORNE_KEYWORD,
        },
    )


def _blood_legion_phase_end_objective_context_predicate(
    context: PhaseEndObjectiveControlContext,
    source: GenericRuleAbilitySource,
) -> bool:
    return any(
        generic_rule_army_uses_record(army=army, source=source)
        for army in context.state.army_definitions
    )


def _blood_legion_blood_tainted_sticky_states(
    context: PhaseEndObjectiveControlContext,
    source: GenericRuleAbilitySource,
) -> tuple[StickyObjectiveControlState, ...]:
    states: list[StickyObjectiveControlState] = []
    for army in context.state.army_definitions:
        if not generic_rule_army_uses_record(army=army, source=source):
            continue
        states.extend(_blood_tainted_states_for_army(context=context, source=source, army=army))
    return tuple(sorted(states, key=lambda state: state.state_id))


def _blood_tainted_states_for_army(
    *,
    context: PhaseEndObjectiveControlContext,
    source: GenericRuleAbilitySource,
    army: ArmyDefinition,
) -> tuple[StickyObjectiveControlState, ...]:
    objective_ids_by_unit = _phase_start_objective_ids_by_unit(context)
    if not objective_ids_by_unit:
        return ()
    objective_record = _current_objective_control_record(context)
    states: list[StickyObjectiveControlState] = []
    seen_state_keys: set[tuple[str, str, str]] = set()
    for event_id, payload in _unit_destruction_completion_events_for_phase(context):
        attacking_unit_id = _payload_string(payload, "attacking_unit_instance_id")
        if not _unit_id_is_in_army(army, unit_instance_id=attacking_unit_id):
            continue
        matching_effects = generic_rule_ability_effects_for_unit(
            state=context.state,
            source=source,
            unit_instance_id=attacking_unit_id,
            ability=blood_legion_ir.BLOOD_TAINTED_STICKY_OBJECTIVE_ABILITY,
        )
        if not matching_effects:
            continue
        destroyed_unit_id = _payload_string(payload, "target_unit_instance_id")
        if (
            _army_owner_for_unit(context.state.army_definitions, unit_instance_id=destroyed_unit_id)
            == army.player_id
        ):
            continue
        for objective_id in objective_ids_by_unit.get(destroyed_unit_id, ()):
            state_key = (objective_id, attacking_unit_id, destroyed_unit_id)
            if state_key in seen_state_keys:
                continue
            result = objective_record.result_by_objective_id(objective_id)
            attacking_unit_loc = _unit_level_of_control(
                result=result,
                unit_instance_id=attacking_unit_id,
            )
            opponent_loc = _highest_opponent_level_of_control(
                result=result,
                player_id=army.player_id,
            )
            if attacking_unit_loc <= opponent_loc:
                continue
            seen_state_keys.add(state_key)
            states.append(
                StickyObjectiveControlState(
                    state_id=(
                        f"blood-tainted:{context.state.game_id}:"
                        f"round-{context.state.battle_round:02d}:"
                        f"{context.state.active_player_id}:{context.completed_phase.value}:"
                        f"{objective_id}:{attacking_unit_id}:{destroyed_unit_id}"
                    ),
                    game_id=context.state.game_id,
                    player_id=army.player_id,
                    objective_id=objective_id,
                    source_rule_id=blood_legion_ir.BLOOD_LEGION_SOURCE_RULE_ID,
                    source_event_id=event_id,
                    battle_round=context.state.battle_round,
                    phase=context.completed_phase.value,
                    active_player_id=_active_player_id(context),
                    originating_unit_instance_id=attacking_unit_id,
                    destroyed_unit_instance_id=destroyed_unit_id,
                    replay_payload=_blood_tainted_replay_payload(
                        source=source,
                        matching_effects=matching_effects,
                        attacking_unit_id=attacking_unit_id,
                        destroyed_unit_id=destroyed_unit_id,
                        objective_id=objective_id,
                        attacking_unit_loc=attacking_unit_loc,
                        opponent_loc=opponent_loc,
                        event_id=event_id,
                    ),
                )
            )
    return tuple(sorted(states, key=lambda state: state.state_id))


def _blood_tainted_replay_payload(
    *,
    source: GenericRuleAbilitySource,
    matching_effects: tuple[PersistingEffect, ...],
    attacking_unit_id: str,
    destroyed_unit_id: str,
    objective_id: str,
    attacking_unit_loc: int,
    opponent_loc: int,
    event_id: str,
) -> JsonValue:
    return generic_rule_ability_source_context_payload(
        source=source,
        matching_effects=matching_effects,
        source_rule_id=blood_legion_ir.BLOOD_LEGION_SOURCE_RULE_ID,
        extra_context={
            "effect_kind": "blood_tainted",
            "detachment_id": blood_legion_ir.BLOOD_LEGION_DETACHMENT_ID,
            "attacking_unit_instance_id": attacking_unit_id,
            "destroyed_unit_instance_id": destroyed_unit_id,
            "objective_id": objective_id,
            "attacking_unit_level_of_control": attacking_unit_loc,
            "opponent_level_of_control": opponent_loc,
            "model_destroyed_event_id": event_id,
            "unit_destruction_completion_event_id": event_id,
            "required_faction_keyword": blood_legion_ir.LEGIONES_DAEMONICA_KEYWORD,
            "required_keyword": blood_legion_ir.KHORNE_KEYWORD,
        },
    )


def _current_objective_control_record(
    context: PhaseEndObjectiveControlContext,
) -> ObjectiveControlRecord:
    return resolve_objective_control(
        ObjectiveControlContext.from_game_state(
            context.state,
            timing=ObjectiveControlTiming.PHASE_END,
            phase=context.completed_phase,
            ruleset_descriptor=context.state.runtime_ruleset_descriptor(),
            runtime_modifier_registry=context.runtime_modifier_registry,
        )
    )


def _model_destroyed_events_for_phase(
    context: PhaseEndObjectiveControlContext,
) -> tuple[tuple[str, dict[str, JsonValue]], ...]:
    events: list[tuple[str, dict[str, JsonValue]]] = []
    for record in context.event_log.records:
        if record.event_type != "model_destroyed":
            continue
        payload = record.payload
        if not isinstance(payload, dict):
            continue
        if payload.get("game_id") != context.state.game_id:
            continue
        if payload.get("battle_round") != context.state.battle_round:
            continue
        if payload.get("active_player_id") != context.state.active_player_id:
            continue
        if payload.get("phase") != context.completed_phase.value:
            continue
        events.append((record.event_id, payload))
    return tuple(events)


def _unit_destruction_completion_events_for_phase(
    context: PhaseEndObjectiveControlContext,
) -> tuple[tuple[str, dict[str, JsonValue]], ...]:
    phase_start_removed_model_ids = _phase_start_removed_model_ids(context)
    final_removed_model_ids = _removed_model_ids(context)
    destroyed_model_ids_by_unit: dict[str, set[str]] = {}
    completed_unit_ids: set[str] = set()
    completion_events: list[tuple[str, dict[str, JsonValue]]] = []
    for event_id, payload in _model_destroyed_events_for_phase(context):
        target_unit_id = _payload_string(payload, "target_unit_instance_id")
        target_unit = _unit_by_id(context.state.army_definitions, unit_instance_id=target_unit_id)
        target_model_ids = {model.model_instance_id for model in target_unit.own_models}
        if not target_model_ids <= final_removed_model_ids:
            continue
        if target_unit_id in completed_unit_ids:
            raise GameLifecycleError("Blood Tainted saw destruction after unit completion.")
        model_id = _payload_string(payload, "model_instance_id")
        if model_id not in target_model_ids:
            raise GameLifecycleError("Blood Tainted model-destroyed event target drift.")
        destroyed_model_ids = destroyed_model_ids_by_unit.setdefault(
            target_unit_id,
            set(target_model_ids & phase_start_removed_model_ids),
        )
        if model_id in destroyed_model_ids:
            raise GameLifecycleError("Blood Tainted saw duplicate destroyed-model attribution.")
        destroyed_model_ids.add(model_id)
        if target_model_ids <= destroyed_model_ids:
            completed_unit_ids.add(target_unit_id)
            completion_events.append((event_id, payload))
    return tuple(completion_events)


def _phase_start_objective_ids_by_unit(
    context: PhaseEndObjectiveControlContext,
) -> dict[str, tuple[str, ...]]:
    payload = _phase_start_snapshot_payload(context)
    if payload is None:
        return {}
    raw_mapping = payload.get("objective_ids_by_unit_instance_id")
    if not isinstance(raw_mapping, dict):
        raise GameLifecycleError("Blood Tainted phase-start snapshot is malformed.")
    mapping: dict[str, tuple[str, ...]] = {}
    for raw_unit_id, raw_objective_ids in raw_mapping.items():
        if type(raw_unit_id) is not str or not isinstance(raw_objective_ids, list):
            raise GameLifecycleError("Blood Tainted phase-start snapshot has invalid entries.")
        mapping[raw_unit_id] = tuple(
            _validate_identifier("objective_id", objective_id) for objective_id in raw_objective_ids
        )
    return mapping


def _phase_start_removed_model_ids(context: PhaseEndObjectiveControlContext) -> set[str]:
    payload = _phase_start_snapshot_payload(context)
    if payload is None:
        return set()
    raw_model_ids = payload.get("removed_model_ids")
    if not isinstance(raw_model_ids, list):
        raise GameLifecycleError("Blood Tainted phase-start snapshot missing removed models.")
    return {
        _validate_identifier("removed_model_id", raw_model_id) for raw_model_id in raw_model_ids
    }


def _phase_start_snapshot_payload(
    context: PhaseEndObjectiveControlContext,
) -> dict[str, JsonValue] | None:
    active_player_id = _active_player_id(context)
    snapshot_id = (
        f"objective-proximity:{context.state.game_id}:"
        f"round-{context.state.battle_round:02d}:turn:{active_player_id}:"
        f"phase:{context.completed_phase.value}:start"
    )
    for record in reversed(context.event_log.records):
        if record.event_type != "objective_marker_phase_start_proximity_snapshot":
            continue
        payload = record.payload
        if not isinstance(payload, dict):
            continue
        if payload.get("snapshot_id") != snapshot_id:
            continue
        return payload
    return None


def _removed_model_ids(context: PhaseEndObjectiveControlContext) -> set[str]:
    battlefield_state = context.state.battlefield_state
    if battlefield_state is None:
        raise GameLifecycleError("Blood Tainted requires battlefield_state.")
    return set(battlefield_state.removed_model_ids)


def _triggering_unit(context: MovementEndSurgeContext) -> UnitInstance:
    scenario = _battlefield_scenario(context.state)
    placement = scenario.battlefield_state.unit_placement_by_id(context.triggering_unit_instance_id)
    return scenario.unit_instance_for_placement(placement)


def _unit_placements_within(
    *,
    scenario: BattlefieldScenario,
    first: UnitPlacement,
    second: UnitPlacement,
    distance_inches: float,
) -> bool:
    for first_placement in first.model_placements:
        first_model = geometry_model_for_placement(
            model=scenario.model_instance_for_placement(first_placement),
            placement=first_placement,
        )
        for second_placement in second.model_placements:
            second_model = geometry_model_for_placement(
                model=scenario.model_instance_for_placement(second_placement),
                placement=second_placement,
            )
            if first_model.range_to(second_model) <= distance_inches:
                return True
    return False


def _unit_level_of_control(
    *,
    result: ObjectiveControlResult,
    unit_instance_id: str,
) -> int:
    requested_unit_id = _validate_identifier("unit_instance_id", unit_instance_id)
    return sum(
        contribution.effective_objective_control
        for contribution in result.contributors
        if contribution.unit_instance_id == requested_unit_id
    )


def _highest_opponent_level_of_control(
    *,
    result: ObjectiveControlResult,
    player_id: str,
) -> int:
    requested_player_id = _validate_identifier("player_id", player_id)
    opponent_scores = tuple(
        score.score for score in result.scores if score.player_id != requested_player_id
    )
    return 0 if not opponent_scores else max(opponent_scores)


def _battlefield_scenario(state: object) -> BattlefieldScenario:
    if type(state) is not GameState:
        raise GameLifecycleError("Blood Legion requires GameState.")
    if state.battlefield_state is None:
        raise GameLifecycleError("Blood Legion requires battlefield_state.")
    return BattlefieldScenario(
        armies=tuple(state.army_definitions),
        battlefield_state=state.battlefield_state,
    )


def _placed_unit_for_army(
    *,
    scenario: BattlefieldScenario,
    player_id: str,
    unit_instance_id: str,
) -> UnitPlacement | None:
    requested_player_id = _validate_identifier("player_id", player_id)
    requested_unit_id = _validate_identifier("unit_instance_id", unit_instance_id)
    for placed_army in scenario.battlefield_state.placed_armies:
        if placed_army.player_id != requested_player_id:
            continue
        for placement in placed_army.unit_placements:
            if placement.unit_instance_id == requested_unit_id:
                return placement
    return None


def _unit_id_is_in_army(army: ArmyDefinition, *, unit_instance_id: str) -> bool:
    requested_unit_id = _validate_identifier("unit_instance_id", unit_instance_id)
    return any(unit.unit_instance_id == requested_unit_id for unit in army.units)


def _unit_by_id(
    army_definitions: tuple[ArmyDefinition, ...] | list[ArmyDefinition],
    *,
    unit_instance_id: str,
) -> UnitInstance:
    requested_unit_id = _validate_identifier("unit_instance_id", unit_instance_id)
    for army in army_definitions:
        for unit in army.units:
            if unit.unit_instance_id == requested_unit_id:
                return unit
    raise GameLifecycleError("Blood Legion unit_instance_id was not found.")


def _army_owner_for_unit(
    army_definitions: tuple[ArmyDefinition, ...] | list[ArmyDefinition],
    *,
    unit_instance_id: str,
) -> str:
    requested_unit_id = _validate_identifier("unit_instance_id", unit_instance_id)
    for army in army_definitions:
        for unit in army.units:
            if unit.unit_instance_id == requested_unit_id:
                return army.player_id
    raise GameLifecycleError("Blood Legion unit owner was not found.")


def _unit_has_keyword(unit: UnitInstance, keyword: str) -> bool:
    canonical = _canonical_keyword(keyword)
    return any(_canonical_keyword(stored) == canonical for stored in unit.keywords)


def _active_player_id(context: PhaseEndObjectiveControlContext) -> str:
    active_player_id = context.state.active_player_id
    if active_player_id is None:
        raise GameLifecycleError("Blood Tainted requires active_player_id.")
    return active_player_id


def _payload_string(payload: dict[str, JsonValue], key: str) -> str:
    value = payload.get(key)
    if type(value) is not str:
        raise GameLifecycleError(f"Generic RuleIR Blood Legion payload requires {key}.")
    return _validate_identifier(key, value)


def _canonical_keyword(value: str) -> str:
    return value.strip().upper().replace("_", " ").replace("-", " ")


def _canonical_name(value: str) -> str:
    return "".join(
        character
        for character in _validate_identifier("name", value).upper()
        if character.isalnum()
    )


def _blood_legion_murdercall_hook_id(source: GenericRuleAbilitySource) -> str:
    return _validate_identifier(
        "generic Blood Legion Murdercall hook_id",
        blood_legion_ir.MURDERCALL_HOOK_ID,
    )


def _blood_legion_blood_tainted_hook_id(source: GenericRuleAbilitySource) -> str:
    return _validate_identifier(
        "generic Blood Legion Blood Tainted hook_id",
        blood_legion_ir.BLOOD_TAINTED_HOOK_ID,
    )


_validate_identifier = IdentifierValidator(GameLifecycleError)

DEFAULT_GENERIC_RULE_ABILITY_REGISTRY = GenericRuleAbilityRegistry(
    advance_eligibility_abilities=(
        GenericRuleAdvanceEligibilityAbility(
            ability_id=shadow_legion_ir.CAN_ADVANCE_AND_SHOOT_AND_CHARGE_ABILITY,
            coverage_descriptor_id=shadow_legion_ir.SHADOW_LEGION_DETACHMENT_RULE_DESCRIPTOR_ID,
            source_rule_id=_SHADOW_LEGION_SOURCE_RULE_ID,
            hook_id_builder=_shadow_legion_advance_hook_id,
            target_unit_id_builder=generic_rule_advance_context_unit_id,
            context_predicate=_shadow_legion_advance_context_predicate,
            grant_builder=_shadow_legion_advance_grant,
        ),
    ),
    shooting_target_restriction_abilities=(
        GenericRuleShootingTargetRestrictionAbility(
            ability_id=shadow_legion_ir.SNAP_SHOOTING_TARGET_FORBIDDEN_ABILITY,
            coverage_descriptor_id=shadow_legion_ir.SHADOW_LEGION_DETACHMENT_RULE_DESCRIPTOR_ID,
            source_rule_id=_SHADOW_LEGION_SOURCE_RULE_ID,
            hook_id_builder=_shadow_legion_snap_restriction_hook_id,
            target_unit_id_builder=generic_rule_shooting_target_restriction_target_unit_id,
            context_predicate=_shadow_legion_snap_target_context_predicate,
            restriction_builder=_shadow_legion_snap_target_restriction,
        ),
    ),
    shooting_unit_selected_grant_abilities=_shadow_legion_shooting_dark_pact_abilities(),
    fight_unit_selected_grant_abilities=_shadow_legion_fight_dark_pact_abilities(),
    attack_sequence_completed_abilities=(
        GenericRuleAttackSequenceCompletedAbility(
            ability_ids_value=_SHADOW_LEGION_DARK_PACT_ABILITY_IDS,
            coverage_descriptor_id=shadow_legion_ir.SHADOW_LEGION_DETACHMENT_RULE_DESCRIPTOR_ID,
            source_rule_id=_SHADOW_LEGION_SOURCE_RULE_ID,
            hook_id_builder=_shadow_legion_dark_pact_completion_hook_id,
            handler=_resolve_shadow_legion_dark_pact_attack_sequence_completion,
        ),
    ),
    mortal_wound_feel_no_pain_abilities=(
        GenericRuleMortalWoundFeelNoPainAbility(
            ability_ids_value=_SHADOW_LEGION_DARK_PACT_ABILITY_IDS,
            coverage_descriptor_id=shadow_legion_ir.SHADOW_LEGION_DETACHMENT_RULE_DESCRIPTOR_ID,
            source_rule_id=_SHADOW_LEGION_SOURCE_RULE_ID,
            source_kind=_SHADOW_LEGION_DARK_PACT_MORTAL_WOUNDS_SOURCE_KIND,
            hook_id_builder=_shadow_legion_dark_pact_mortal_wound_fnp_hook_id,
            handler=_apply_shadow_legion_dark_pact_mortal_wound_feel_no_pain_decision,
        ),
        GenericRuleMortalWoundFeelNoPainAbility(
            ability_ids_value=(shadow_legion_ir.MALICE_MADE_MANIFEST_MORTAL_WOUNDS_ABILITY,),
            coverage_descriptor_id=(
                shadow_legion_ir.MALICE_MADE_MANIFEST_ENHANCEMENT_DESCRIPTOR_ID
            ),
            source_rule_id=shadow_legion_ir.MALICE_MADE_MANIFEST_SOURCE_RULE_ID,
            source_kind=shadow_legion_ir.MALICE_MADE_MANIFEST_MORTAL_WOUNDS_SOURCE_KIND,
            hook_id_builder=_shadow_legion_malice_made_manifest_fnp_hook_id,
            handler=_shadow_legion_malice_made_manifest_fnp,
        ),
    ),
    weapon_profile_modifier_abilities=(
        GenericRuleWeaponProfileModifierAbility(
            ability_ids_value=_SHADOW_LEGION_DARK_PACT_ABILITY_IDS,
            coverage_descriptor_id=shadow_legion_ir.SHADOW_LEGION_DETACHMENT_RULE_DESCRIPTOR_ID,
            source_rule_id=_SHADOW_LEGION_SOURCE_RULE_ID,
            modifier_id_builder=_shadow_legion_dark_pact_weapon_profile_modifier_id,
            handler=_shadow_legion_dark_pact_weapon_profile_modifier,
        ),
    ),
    movement_end_surge_abilities=(
        GenericRuleMovementEndSurgeAbility(
            ability_id=blood_legion_ir.MURDERCALL_SURGE_ABILITY,
            coverage_descriptor_id=blood_legion_ir.BLOOD_LEGION_DETACHMENT_RULE_DESCRIPTOR_ID,
            source_rule_id=blood_legion_ir.BLOOD_LEGION_SOURCE_RULE_ID,
            hook_id_builder=_blood_legion_murdercall_hook_id,
            context_predicate=_blood_legion_movement_end_surge_context_predicate,
            grant_builder=_blood_legion_murdercall_grants,
        ),
    ),
    phase_end_objective_control_abilities=(
        GenericRulePhaseEndObjectiveControlAbility(
            ability_id=blood_legion_ir.BLOOD_TAINTED_STICKY_OBJECTIVE_ABILITY,
            coverage_descriptor_id=blood_legion_ir.BLOOD_LEGION_DETACHMENT_RULE_DESCRIPTOR_ID,
            source_rule_id=blood_legion_ir.BLOOD_LEGION_SOURCE_RULE_ID,
            hook_id_builder=_blood_legion_blood_tainted_hook_id,
            context_predicate=_blood_legion_phase_end_objective_context_predicate,
            state_builder=_blood_legion_blood_tainted_sticky_states,
        ),
    ),
    battle_formation_abilities=(*aeldari_corsair_coterie_battle_formation_abilities(),),
    enhancement_effect_abilities=(
        *aeldari_path_of_the_outcast_enhancement_effect_abilities(),
        *aeldari_corsair_coterie_enhancement_effect_abilities(),
        GenericRuleEnhancementEffectAbility(
            ability_id=shadow_legion_ir.LEAPING_SHADOWS_SCOUTS_ABILITY,
            coverage_descriptor_id=shadow_legion_ir.LEAPING_SHADOWS_ENHANCEMENT_DESCRIPTOR_ID,
            source_rule_id=shadow_legion_ir.LEAPING_SHADOWS_SOURCE_RULE_ID,
            enhancement_id=shadow_legion_ir.LEAPING_SHADOWS_ENHANCEMENT_ID,
            effect_id_builder=_shadow_legion_leaping_shadows_effect_id,
            context_predicate=_shadow_legion_enhancement_context_predicate,
            effect_builder=_shadow_legion_leaping_shadows_effect,
        ),
    ),
    objective_control_modifier_abilities=(
        GenericRuleObjectiveControlModifierAbility(
            ability_id=shadow_legion_ir.MANTLE_OF_GLOOM_OBJECTIVE_CONTROL_ABILITY,
            coverage_descriptor_id=shadow_legion_ir.MANTLE_OF_GLOOM_ENHANCEMENT_DESCRIPTOR_ID,
            source_rule_id=shadow_legion_ir.MANTLE_OF_GLOOM_SOURCE_RULE_ID,
            modifier_id_builder=_shadow_legion_mantle_of_gloom_modifier_id,
            context_predicate=_shadow_legion_objective_control_context_predicate,
            modifier_builder=_shadow_legion_mantle_of_gloom_modifier,
        ),
        *aeldari_corsair_coterie_objective_control_modifier_abilities(),
    ),
    stratagem_cost_choice_abilities=(*aeldari_corsair_coterie_stratagem_cost_choice_abilities(),),
    stratagem_cost_modifier_abilities=(
        *aeldari_corsair_coterie_stratagem_cost_modifier_abilities(),
        *emperors_children_court_of_the_phoenician_stratagem_cost_modifier_abilities(),
    ),
    save_option_modifier_abilities=(*aeldari_corsair_coterie_save_option_modifier_abilities(),),
    unit_destroyed_abilities=(
        GenericRuleUnitDestroyedAbility(
            ability_id=shadow_legion_ir.FADE_TO_DARKNESS_RESERVES_ABILITY,
            coverage_descriptor_id=shadow_legion_ir.FADE_TO_DARKNESS_ENHANCEMENT_DESCRIPTOR_ID,
            source_rule_id=shadow_legion_ir.FADE_TO_DARKNESS_SOURCE_RULE_ID,
            hook_id_builder=_shadow_legion_fade_to_darkness_unit_destroyed_hook_id,
            effect_builder=_shadow_legion_fade_to_darkness_unit_destroyed,
        ),
    ),
    turn_end_abilities=(
        GenericRuleTurnEndAbility(
            ability_id=shadow_legion_ir.FADE_TO_DARKNESS_RESERVES_ABILITY,
            coverage_descriptor_id=shadow_legion_ir.FADE_TO_DARKNESS_ENHANCEMENT_DESCRIPTOR_ID,
            source_rule_id=shadow_legion_ir.FADE_TO_DARKNESS_SOURCE_RULE_ID,
            hook_id_builder=_shadow_legion_fade_to_darkness_turn_end_hook_id,
            request_builder=_shadow_legion_fade_to_darkness_turn_end_request,
            result_builder=_shadow_legion_fade_to_darkness_turn_end_result,
        ),
        *aeldari_corsair_coterie_turn_end_abilities(),
    ),
    fight_phase_start_abilities=(
        GenericRuleFightPhaseStartAbility(
            ability_id=shadow_legion_ir.MALICE_MADE_MANIFEST_MORTAL_WOUNDS_ABILITY,
            coverage_descriptor_id=(
                shadow_legion_ir.MALICE_MADE_MANIFEST_ENHANCEMENT_DESCRIPTOR_ID
            ),
            source_rule_id=shadow_legion_ir.MALICE_MADE_MANIFEST_SOURCE_RULE_ID,
            hook_id_builder=_shadow_legion_malice_made_manifest_hook_id,
            request_builder=_shadow_legion_malice_made_manifest_request,
            result_builder=_shadow_legion_malice_made_manifest_result,
        ),
    ),
)
