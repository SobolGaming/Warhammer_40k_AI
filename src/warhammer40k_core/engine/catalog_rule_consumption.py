from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, replace
from types import MappingProxyType
from typing import TYPE_CHECKING, cast

from warhammer40k_core.core.attributes import Characteristic
from warhammer40k_core.core.dice import RerollComponentSelectionPolicy, RerollPermission
from warhammer40k_core.core.modifiers import RollModifier
from warhammer40k_core.core.ruleset_descriptor import RulesetDescriptor
from warhammer40k_core.core.weapon_profiles import (
    AbilityDescriptor,
    RangeProfileKind,
    WeaponKeyword,
    WeaponProfile,
    WeaponProfileError,
    canonical_weapon_keyword_tokens,
    weapon_keyword_from_token,
)
from warhammer40k_core.engine.abilities import (
    GENERIC_RULE_IR_ABILITY_HANDLER_ID,
    AbilityCatalogIndex,
    AbilityCatalogRecord,
    AbilitySourceKind,
)
from warhammer40k_core.engine.advance_eligibility_hooks import (
    AdvanceEligibilityContext,
    AdvanceEligibilityGrant,
    AdvanceEligibilityHookBinding,
)
from warhammer40k_core.engine.army_mustering import ArmyDefinition
from warhammer40k_core.engine.battlefield_state import PlacementError
from warhammer40k_core.engine.damage_allocation import (
    DestructionReactionKind,
    DestructionReactionSource,
    FeelNoPainAttackCondition,
    FeelNoPainSource,
    feel_no_pain_attack_condition_from_token,
)
from warhammer40k_core.engine.decision_controller import DecisionController
from warhammer40k_core.engine.decision_request import DecisionRequest
from warhammer40k_core.engine.effects import EffectExpiration, PersistingEffect
from warhammer40k_core.engine.event_log import JsonValue
from warhammer40k_core.engine.faction_content.bundle_validation import (
    validate_identifier as _validate_identifier,
)
from warhammer40k_core.engine.phase import GameLifecycleError
from warhammer40k_core.engine.runtime_modifiers import (
    WeaponProfileModifierBinding,
    WeaponProfileModifierContext,
)
from warhammer40k_core.engine.timing_windows import TimingTriggerKind
from warhammer40k_core.engine.unit_abilities import (
    DeadlyDemiseAbilityProfile,
    FeelNoPainAbilityProfile,
    deadly_demise_profile_for_unit,
    feel_no_pain_profile_for_unit,
    fights_first_source_id_for_unit,
)
from warhammer40k_core.engine.unit_factory import UnitInstance
from warhammer40k_core.rules.rule_ir import (
    RuleClause,
    RuleConditionKind,
    RuleEffectKind,
    RuleEffectSpec,
    RuleIR,
    RuleTargetKind,
    RuleTriggerKind,
    parameter_payload,
)

if TYPE_CHECKING:
    from warhammer40k_core.engine.game_state import GameState
    from warhammer40k_core.engine.healing import HealingEffect

CATALOG_IR_CHARGE_ROLL_CONSUMER_ID = "catalog-ir:charge-roll-modifier"
CATALOG_IR_LEADERSHIP_QUERY_CONSUMER_ID = "catalog-ir:leadership-characteristic-query"
CATALOG_IR_HIT_ROLL_MODIFIER_CONSUMER_ID = "catalog-ir:hit-roll-modifier"
CATALOG_IR_WOUND_ROLL_MODIFIER_CONSUMER_ID = "catalog-ir:wound-roll-modifier"
CATALOG_IR_SAVE_ROLL_MODIFIER_CONSUMER_ID = "catalog-ir:save-roll-modifier"
CATALOG_IR_INVULNERABLE_SAVE_ROLL_MODIFIER_CONSUMER_ID = (
    "catalog-ir:invulnerable-save-roll-modifier"
)
CATALOG_IR_DESPERATE_ESCAPE_ROLL_MODIFIER_CONSUMER_ID = "catalog-ir:desperate-escape-roll-modifier"
CATALOG_IR_FORCE_DESPERATE_ESCAPE_CONSUMER_ID = "catalog-ir:force-desperate-escape"
CATALOG_IR_ADVANCE_ROLL_REROLL_CONSUMER_ID = "catalog-ir:advance-roll-reroll"
CATALOG_IR_CHARGE_ROLL_REROLL_CONSUMER_ID = "catalog-ir:charge-roll-reroll"
CATALOG_IR_WOUND_ROLL_REROLL_CONSUMER_ID = "catalog-ir:wound-roll-reroll"
CATALOG_IR_DESTROYED_UNIT_RESTORE_LOST_WOUNDS_CONSUMER_ID = (
    "catalog-ir:destroyed-unit-restore-lost-wounds"
)
CATALOG_IR_FEEL_NO_PAIN_ROLL_CONSUMER_ID = "catalog-ir:feel-no-pain-roll"
CATALOG_IR_FEEL_NO_PAIN_SOURCE_CONSUMER_ID = "catalog-ir:feel-no-pain-source"
CATALOG_IR_CRITICAL_HIT_VALUE_MODIFIER_CONSUMER_ID = "catalog-ir:critical-hit-value-modifier"
CATALOG_IR_CRITICAL_WOUND_VALUE_MODIFIER_CONSUMER_ID = "catalog-ir:critical-wound-value-modifier"
CATALOG_IR_WEAPON_KEYWORD_GRANT_CONSUMER_ID = "catalog-ir:weapon-keyword-grant"
CATALOG_IR_CAN_ADVANCE_AND_CHARGE_CONSUMER_ID = "catalog-ir:can-advance-and-charge"
CATALOG_IR_CAN_FALLBACK_AND_CHARGE_CONSUMER_ID = "catalog-ir:can-fallback-and-charge"
CATALOG_IR_CAN_ADVANCE_AND_SHOOT_AND_CHARGE_CONSUMER_ID = (
    "catalog-ir:can-advance-and-shoot-and-charge"
)
CATALOG_IR_CAN_BE_PLACED_IN_RESERVES_CONSUMER_ID = "catalog-ir:can-be-placed-in-reserves"
CATALOG_IR_SHADOW_OF_CHAOS_AURA_CONSUMER_ID = "catalog-ir:shadow-of-chaos-aura"
DEADLY_DEMISE_TRIGGER_ROLL_THRESHOLD = 6
DEADLY_DEMISE_RANGE_INCHES = 6.0
CORE_FIGHTS_FIRST_SOURCE_ID = "gw-11e-core-abilities:core:fights-first"
CORE_FIGHTS_FIRST_EFFECT_KIND = "fights_first"

_CATALOG_IR_ROLL_MODIFIER_CONSUMER_IDS: Mapping[str, str] = MappingProxyType(
    {
        "charge": CATALOG_IR_CHARGE_ROLL_CONSUMER_ID,
        "charge_roll": CATALOG_IR_CHARGE_ROLL_CONSUMER_ID,
        "hit": CATALOG_IR_HIT_ROLL_MODIFIER_CONSUMER_ID,
        "hit_roll": CATALOG_IR_HIT_ROLL_MODIFIER_CONSUMER_ID,
        "wound": CATALOG_IR_WOUND_ROLL_MODIFIER_CONSUMER_ID,
        "wound_roll": CATALOG_IR_WOUND_ROLL_MODIFIER_CONSUMER_ID,
        "save": CATALOG_IR_SAVE_ROLL_MODIFIER_CONSUMER_ID,
        "save_roll": CATALOG_IR_SAVE_ROLL_MODIFIER_CONSUMER_ID,
        "invulnerable_save": CATALOG_IR_INVULNERABLE_SAVE_ROLL_MODIFIER_CONSUMER_ID,
        "invulnerable_save_roll": CATALOG_IR_INVULNERABLE_SAVE_ROLL_MODIFIER_CONSUMER_ID,
        "feel_no_pain": CATALOG_IR_FEEL_NO_PAIN_ROLL_CONSUMER_ID,
        "feel_no_pain_roll": CATALOG_IR_FEEL_NO_PAIN_ROLL_CONSUMER_ID,
        "critical_hit": CATALOG_IR_CRITICAL_HIT_VALUE_MODIFIER_CONSUMER_ID,
        "critical_hit_value": CATALOG_IR_CRITICAL_HIT_VALUE_MODIFIER_CONSUMER_ID,
        "critical_wound": CATALOG_IR_CRITICAL_WOUND_VALUE_MODIFIER_CONSUMER_ID,
        "critical_wound_value": CATALOG_IR_CRITICAL_WOUND_VALUE_MODIFIER_CONSUMER_ID,
        "desperate_escape": CATALOG_IR_DESPERATE_ESCAPE_ROLL_MODIFIER_CONSUMER_ID,
        "desperate_escape_roll": CATALOG_IR_DESPERATE_ESCAPE_ROLL_MODIFIER_CONSUMER_ID,
    }
)
_CATALOG_IR_ROLL_REROLL_CONSUMER_IDS: Mapping[str, str] = MappingProxyType(
    {
        "advance": CATALOG_IR_ADVANCE_ROLL_REROLL_CONSUMER_ID,
        "advance_roll": CATALOG_IR_ADVANCE_ROLL_REROLL_CONSUMER_ID,
        "charge": CATALOG_IR_CHARGE_ROLL_REROLL_CONSUMER_ID,
        "charge_roll": CATALOG_IR_CHARGE_ROLL_REROLL_CONSUMER_ID,
        "wound": CATALOG_IR_WOUND_ROLL_REROLL_CONSUMER_ID,
        "wound_roll": CATALOG_IR_WOUND_ROLL_REROLL_CONSUMER_ID,
        "attack_sequence_wound": CATALOG_IR_WOUND_ROLL_REROLL_CONSUMER_ID,
    }
)
_CATALOG_IR_RULE_EXCEPTION_CONSUMER_IDS: Mapping[str, str] = MappingProxyType(
    {
        "can_advance_and_charge": CATALOG_IR_CAN_ADVANCE_AND_CHARGE_CONSUMER_ID,
        "can_fallback_and_charge": CATALOG_IR_CAN_FALLBACK_AND_CHARGE_CONSUMER_ID,
        "can_fall_back_and_charge": CATALOG_IR_CAN_FALLBACK_AND_CHARGE_CONSUMER_ID,
        "can_advance_and_shoot_and_charge": (
            CATALOG_IR_CAN_ADVANCE_AND_SHOOT_AND_CHARGE_CONSUMER_ID
        ),
        "can_be_placed_in_reserves": CATALOG_IR_CAN_BE_PLACED_IN_RESERVES_CONSUMER_ID,
        "turn_end_reserves": CATALOG_IR_CAN_BE_PLACED_IN_RESERVES_CONSUMER_ID,
    }
)
_CATALOG_IR_ADVANCE_ELIGIBILITY_GRANT_CONSUMER_IDS: Mapping[str, str] = MappingProxyType(
    {
        "can_advance_and_charge": CATALOG_IR_CAN_ADVANCE_AND_CHARGE_CONSUMER_ID,
        "can_advance_and_shoot_and_charge": (
            CATALOG_IR_CAN_ADVANCE_AND_SHOOT_AND_CHARGE_CONSUMER_ID
        ),
    }
)


@dataclass(frozen=True, slots=True)
class CatalogRuleIrHookDefinition:
    hook_id: str

    def __post_init__(self) -> None:
        if type(self.hook_id) is not str or not self.hook_id.strip():
            raise GameLifecycleError("Catalog IR hook definition hook_id must be a non-empty str.")
        if self.hook_id != self.hook_id.strip():
            raise GameLifecycleError("Catalog IR hook definition hook_id must be stripped.")


@dataclass(frozen=True, slots=True)
class CatalogAdvanceEligibilityRuntime:
    ability_indexes_by_player_id: Mapping[str, AbilityCatalogIndex]
    armies: tuple[ArmyDefinition, ...]

    def __post_init__(self) -> None:
        indexes = _validate_ability_index_mapping(self.ability_indexes_by_player_id)
        armies = _validate_armies(self.armies)
        missing_ids = {army.player_id for army in armies} - set(indexes)
        if missing_ids:
            raise GameLifecycleError("Catalog advance eligibility missing player ability index.")
        object.__setattr__(self, "ability_indexes_by_player_id", MappingProxyType(dict(indexes)))
        object.__setattr__(self, "armies", armies)

    def bindings(self) -> tuple[AdvanceEligibilityHookBinding, ...]:
        bindings: list[AdvanceEligibilityHookBinding] = []
        if _has_advance_eligibility_records(
            self.ability_indexes_by_player_id,
            ability="can_advance_and_charge",
        ):
            bindings.append(
                AdvanceEligibilityHookBinding(
                    hook_id=CATALOG_IR_CAN_ADVANCE_AND_CHARGE_CONSUMER_ID,
                    source_id=CATALOG_IR_CAN_ADVANCE_AND_CHARGE_CONSUMER_ID,
                    handler=self.advance_and_charge_handler,
                )
            )
        if _has_advance_eligibility_records(
            self.ability_indexes_by_player_id,
            ability="can_advance_and_shoot_and_charge",
        ):
            bindings.append(
                AdvanceEligibilityHookBinding(
                    hook_id=CATALOG_IR_CAN_ADVANCE_AND_SHOOT_AND_CHARGE_CONSUMER_ID,
                    source_id=CATALOG_IR_CAN_ADVANCE_AND_SHOOT_AND_CHARGE_CONSUMER_ID,
                    handler=self.advance_shoot_and_charge_handler,
                )
            )
        return tuple(bindings)

    def advance_and_charge_handler(
        self,
        context: AdvanceEligibilityContext,
    ) -> AdvanceEligibilityGrant | None:
        return self._grant_for(
            context=context,
            ability="can_advance_and_charge",
            hook_id=CATALOG_IR_CAN_ADVANCE_AND_CHARGE_CONSUMER_ID,
            can_shoot=False,
            can_declare_charge=True,
        )

    def advance_shoot_and_charge_handler(
        self,
        context: AdvanceEligibilityContext,
    ) -> AdvanceEligibilityGrant | None:
        return self._grant_for(
            context=context,
            ability="can_advance_and_shoot_and_charge",
            hook_id=CATALOG_IR_CAN_ADVANCE_AND_SHOOT_AND_CHARGE_CONSUMER_ID,
            can_shoot=True,
            can_declare_charge=True,
        )

    def _grant_for(
        self,
        *,
        context: AdvanceEligibilityContext,
        ability: str,
        hook_id: str,
        can_shoot: bool,
        can_declare_charge: bool,
    ) -> AdvanceEligibilityGrant | None:
        if type(context) is not AdvanceEligibilityContext:
            raise GameLifecycleError("Catalog advance eligibility requires context.")
        matching_records = _matching_advance_eligibility_records(
            ability_indexes_by_player_id=self.ability_indexes_by_player_id,
            armies=self.armies,
            context=context,
            ability=ability,
        )
        if not matching_records:
            return None
        return AdvanceEligibilityGrant(
            hook_id=hook_id,
            source_id=hook_id,
            can_shoot=can_shoot,
            can_declare_charge=can_declare_charge,
            replay_payload={
                "catalog_record_ids": [record.record_id for record in matching_records],
                "source_rule_ids": [record.definition.source_id for record in matching_records],
                "ability_ids": [record.definition.ability_id for record in matching_records],
                "ability": ability,
            },
        )


@dataclass(frozen=True, slots=True)
class CatalogWeaponKeywordGrant:
    source_id: str
    keyword: WeaponKeyword
    weapon_scope: str
    ability: AbilityDescriptor | None = None

    def __post_init__(self) -> None:
        object.__setattr__(self, "source_id", _validate_identifier("source_id", self.source_id))
        object.__setattr__(self, "keyword", _weapon_keyword_from_value(self.keyword))
        object.__setattr__(
            self,
            "weapon_scope",
            _weapon_scope_from_token(self.weapon_scope),
        )
        if self.ability is not None and type(self.ability) is not AbilityDescriptor:
            raise GameLifecycleError("Catalog weapon keyword grant ability must be a descriptor.")


@dataclass(frozen=True, slots=True)
class CatalogWeaponKeywordGrantRuntime:
    ability_indexes_by_player_id: Mapping[str, AbilityCatalogIndex]
    armies: tuple[ArmyDefinition, ...]

    def __post_init__(self) -> None:
        indexes = _validate_ability_index_mapping(self.ability_indexes_by_player_id)
        armies = _validate_armies(self.armies)
        missing_ids = {army.player_id for army in armies} - set(indexes)
        if missing_ids:
            raise GameLifecycleError("Catalog weapon keyword grants missing player ability index.")
        object.__setattr__(self, "ability_indexes_by_player_id", MappingProxyType(dict(indexes)))
        object.__setattr__(self, "armies", armies)

    def bindings(self) -> tuple[WeaponProfileModifierBinding, ...]:
        if not _has_catalog_weapon_keyword_grant_records(self.ability_indexes_by_player_id):
            return ()
        return (
            WeaponProfileModifierBinding(
                modifier_id=CATALOG_IR_WEAPON_KEYWORD_GRANT_CONSUMER_ID,
                source_id=CATALOG_IR_WEAPON_KEYWORD_GRANT_CONSUMER_ID,
                handler=self.weapon_profile_modifier,
            ),
        )

    def weapon_profile_modifier(self, context: WeaponProfileModifierContext) -> WeaponProfile:
        if type(context) is not WeaponProfileModifierContext:
            raise GameLifecycleError("Catalog weapon keyword grant requires context.")
        army, unit = _army_and_unit_for_unit_id(
            armies=self.armies,
            unit_instance_id=context.attacking_unit_instance_id,
        )
        index = self.ability_indexes_by_player_id.get(army.player_id)
        if index is None:
            raise GameLifecycleError("Catalog weapon keyword grant index is missing player.")
        current_model_ids = _current_model_instance_ids_for_unit(state=context.state, unit=unit)
        grants = catalog_weapon_keyword_grants_for_unit(
            ability_index=index,
            unit=unit,
            current_model_instance_ids=current_model_ids,
        )
        profile = context.weapon_profile
        for grant in grants:
            if not _weapon_scope_matches_profile(
                weapon_scope=grant.weapon_scope,
                profile=profile,
            ):
                continue
            profile = _profile_with_catalog_weapon_keyword_grant(profile=profile, grant=grant)
        return profile


def catalog_advance_eligibility_hook_bindings(
    *,
    ability_indexes_by_player_id: Mapping[str, AbilityCatalogIndex],
    armies: tuple[ArmyDefinition, ...],
) -> tuple[AdvanceEligibilityHookBinding, ...]:
    return CatalogAdvanceEligibilityRuntime(
        ability_indexes_by_player_id=ability_indexes_by_player_id,
        armies=armies,
    ).bindings()


def catalog_weapon_profile_modifier_bindings(
    *,
    ability_indexes_by_player_id: Mapping[str, AbilityCatalogIndex],
    armies: tuple[ArmyDefinition, ...],
) -> tuple[WeaponProfileModifierBinding, ...]:
    return CatalogWeaponKeywordGrantRuntime(
        ability_indexes_by_player_id=ability_indexes_by_player_id,
        armies=armies,
    ).bindings()


def catalog_rule_ir_registered_hook_definitions() -> tuple[CatalogRuleIrHookDefinition, ...]:
    hook_ids = {
        *_CATALOG_IR_ROLL_MODIFIER_CONSUMER_IDS.values(),
        *_CATALOG_IR_ROLL_REROLL_CONSUMER_IDS.values(),
        *_CATALOG_IR_RULE_EXCEPTION_CONSUMER_IDS.values(),
        CATALOG_IR_DESTROYED_UNIT_RESTORE_LOST_WOUNDS_CONSUMER_ID,
        CATALOG_IR_FORCE_DESPERATE_ESCAPE_CONSUMER_ID,
        CATALOG_IR_FEEL_NO_PAIN_SOURCE_CONSUMER_ID,
        CATALOG_IR_SHADOW_OF_CHAOS_AURA_CONSUMER_ID,
        CATALOG_IR_WEAPON_KEYWORD_GRANT_CONSUMER_ID,
    }
    for characteristic in Characteristic:
        hook_ids.add(_catalog_ir_characteristic_query_consumer_id(characteristic))
        hook_ids.add(_catalog_ir_characteristic_modifier_consumer_id(characteristic))
    for keyword in canonical_weapon_keyword_tokens():
        hook_ids.add(_catalog_ir_weapon_keyword_grant_consumer_id(keyword))
    return tuple(CatalogRuleIrHookDefinition(hook_id=hook_id) for hook_id in sorted(hook_ids))


def catalog_rule_ir_registered_hook_ids() -> tuple[str, ...]:
    return tuple(definition.hook_id for definition in catalog_rule_ir_registered_hook_definitions())


def catalog_charge_roll_modifiers_for_unit(
    *,
    ability_index: AbilityCatalogIndex,
    unit: UnitInstance,
    current_model_instance_ids: tuple[str, ...],
) -> tuple[RollModifier, ...]:
    _validate_ability_index(ability_index)
    _validate_unit(unit)
    current_ids = _validate_current_model_instance_ids(current_model_instance_ids)
    modifiers: list[RollModifier] = []
    for record in _unit_scoped_generic_records(
        ability_index=ability_index,
        unit=unit,
        current_model_instance_ids=current_ids,
        trigger_kind=TimingTriggerKind.AFTER_DICE_ROLL,
    ):
        rule_ir = _rule_ir_from_record(record)
        for clause in rule_ir.clauses:
            if not _clause_targets_this_unit(clause):
                continue
            for effect_index, effect in enumerate(clause.effects):
                if not _effect_is_charge_roll_modifier(effect):
                    continue
                parameters = parameter_payload(effect.parameters)
                delta = _int_parameter(parameters, key="delta")
                modifiers.append(
                    RollModifier(
                        modifier_id=(
                            f"{record.record_id}:{clause.clause_id}:effect-{effect_index:03d}"
                        ),
                        source_id=record.definition.source_id,
                        operand=delta,
                    )
                )
    return tuple(sorted(modifiers, key=lambda modifier: modifier.modifier_id))


def catalog_advance_roll_reroll_permission_for_unit(
    *,
    ability_index: AbilityCatalogIndex,
    unit: UnitInstance,
    current_model_instance_ids: tuple[str, ...],
    player_id: str,
) -> RerollPermission | None:
    return _catalog_roll_reroll_permission_for_unit(
        ability_index=ability_index,
        unit=unit,
        current_model_instance_ids=current_model_instance_ids,
        player_id=player_id,
        roll_type="advance_roll",
        timing_window="after_advance_roll",
    )


def catalog_charge_roll_reroll_permission_for_unit(
    *,
    ability_index: AbilityCatalogIndex,
    unit: UnitInstance,
    current_model_instance_ids: tuple[str, ...],
    player_id: str,
) -> RerollPermission | None:
    return _catalog_roll_reroll_permission_for_unit(
        ability_index=ability_index,
        unit=unit,
        current_model_instance_ids=current_model_instance_ids,
        player_id=player_id,
        roll_type="charge_roll",
        timing_window="after_charge_roll",
    )


def catalog_wound_roll_reroll_permission_for_attack(
    *,
    ability_index: AbilityCatalogIndex,
    unit: UnitInstance,
    current_model_instance_ids: tuple[str, ...],
    player_id: str,
    attack_kind: str,
    target_keywords: tuple[str, ...],
) -> RerollPermission | None:
    _validate_ability_index(ability_index)
    _validate_unit(unit)
    current_ids = _validate_current_model_instance_ids(current_model_instance_ids)
    _validate_this_model_source_id(unit=unit, current_model_instance_ids=current_ids)
    owning_player_id = _validate_identifier("player_id", player_id)
    resolved_attack_kind = _catalog_ir_lookup_token(
        _validate_identifier("attack_kind", attack_kind)
    )
    resolved_target_keywords = _validate_keyword_tokens("target_keywords", target_keywords)
    permissions: list[RerollPermission] = []
    for record in _unit_scoped_generic_records(
        ability_index=ability_index,
        unit=unit,
        current_model_instance_ids=current_ids,
        trigger_kind=TimingTriggerKind.AFTER_DICE_ROLL,
    ):
        for clause in _clauses_from_record(record):
            if not clause.is_supported:
                continue
            if not _clause_is_melee_wound_reroll_against_target_keywords(
                clause=clause,
                attack_kind=resolved_attack_kind,
                target_keywords=resolved_target_keywords,
            ):
                continue
            for effect_index, effect in enumerate(clause.effects):
                if not _effect_is_roll_reroll_permission(effect, roll_type="wound_roll"):
                    continue
                permissions.append(
                    _catalog_roll_reroll_permission(
                        record=record,
                        clause=clause,
                        effect_index=effect_index,
                        player_id=owning_player_id,
                        roll_type="attack_sequence.wound",
                        timing_window="attack_sequence.wound",
                    )
                )
    if len(permissions) > 1:
        raise GameLifecycleError("Multiple catalog wound reroll permissions are available.")
    return permissions[0] if permissions else None


def catalog_restore_lost_wounds_after_destroying_unit(
    *,
    state: GameState,
    decisions: DecisionController,
    ruleset_descriptor: RulesetDescriptor,
    ability_index: AbilityCatalogIndex,
    unit: UnitInstance,
    current_model_instance_ids: tuple[str, ...],
    player_id: str,
    destroyed_player_id: str,
    destroyed_unit_keywords: tuple[str, ...],
    healing_amount: int,
    source_event_id: str,
) -> tuple[HealingEffect, DecisionRequest | None] | None:
    _validate_game_state(state)
    if type(decisions) is not DecisionController:
        raise GameLifecycleError("Catalog restore lost wounds requires DecisionController.")
    if type(ruleset_descriptor) is not RulesetDescriptor:
        raise GameLifecycleError("Catalog restore lost wounds requires RulesetDescriptor.")
    _validate_ability_index(ability_index)
    _validate_unit(unit)
    from warhammer40k_core.engine.healing import HealingEffect, resolve_healing_until_blocked

    current_ids = _validate_current_model_instance_ids(current_model_instance_ids)
    source_model_id = _validate_this_model_source_id(
        unit=unit,
        current_model_instance_ids=current_ids,
    )
    owning_player_id = _validate_identifier("player_id", player_id)
    opposing_player_id = _validate_identifier("destroyed_player_id", destroyed_player_id)
    source_event = _validate_identifier("source_event_id", source_event_id)
    if opposing_player_id == owning_player_id:
        return None
    resolved_destroyed_keywords = _validate_keyword_tokens(
        "destroyed_unit_keywords",
        destroyed_unit_keywords,
    )
    amount = _validate_healing_amount(healing_amount)
    matches: list[tuple[AbilityCatalogRecord, RuleClause, int, RuleEffectSpec]] = []
    for record in _unit_scoped_generic_records(
        ability_index=ability_index,
        unit=unit,
        current_model_instance_ids=current_ids,
        trigger_kind=TimingTriggerKind.AFTER_UNIT_DESTROYED,
    ):
        for clause in _clauses_from_record(record):
            if not clause.is_supported:
                continue
            if not _clause_is_destroyed_enemy_keyword_restore_lost_wounds(
                clause=clause,
                destroyed_unit_keywords=resolved_destroyed_keywords,
            ):
                continue
            for effect_index, effect in enumerate(clause.effects):
                if effect.kind is RuleEffectKind.RESTORE_LOST_WOUNDS:
                    matches.append((record, clause, effect_index, effect))
    if len(matches) > 1:
        raise GameLifecycleError("Multiple catalog restore-lost-wounds effects are available.")
    if not matches:
        return None
    record, clause, effect_index, effect = matches[0]
    effect_parameters = parameter_payload(effect.parameters)
    if effect_parameters.get("amount") != "D6":
        raise GameLifecycleError("Catalog restore lost wounds requires a D6 amount.")
    missing_wounds = _this_model_restore_missing_wounds(
        unit=unit,
        source_model_id=source_model_id,
    )
    if missing_wounds == 0:
        return None
    amount = min(amount, missing_wounds)
    healing_effect = HealingEffect(
        effect_id=f"{record.record_id}:{clause.clause_id}:effect-{effect_index:03d}:heal",
        target_unit_instance_id=unit.unit_instance_id,
        amount=amount,
        opposing_player_id=opposing_player_id,
        source_rule_id=record.definition.source_id,
        source_context={
            "catalog_record_id": record.record_id,
            "clause_id": clause.clause_id,
            "source_event_id": source_event,
            "destroyed_unit_keywords": list(resolved_destroyed_keywords),
            "effect_kind": RuleEffectKind.RESTORE_LOST_WOUNDS.value,
            "source_model_instance_id": source_model_id,
        },
        phase_start_model_ids=unit.own_model_ids(),
    )
    return resolve_healing_until_blocked(
        state=state,
        decisions=decisions,
        ruleset_descriptor=ruleset_descriptor,
        effect=healing_effect,
    )


def catalog_weapon_keyword_grants_for_unit(
    *,
    ability_index: AbilityCatalogIndex,
    unit: UnitInstance,
    current_model_instance_ids: tuple[str, ...],
) -> tuple[CatalogWeaponKeywordGrant, ...]:
    _validate_ability_index(ability_index)
    _validate_unit(unit)
    current_ids = _validate_current_model_instance_ids(current_model_instance_ids)
    grants: list[CatalogWeaponKeywordGrant] = []
    for record in _unit_scoped_generic_records_for_all_timings(
        ability_index=ability_index,
        unit=unit,
        current_model_instance_ids=current_ids,
    ):
        rule_ir = _rule_ir_from_record(record)
        if not rule_ir.is_supported:
            continue
        for clause in rule_ir.clauses:
            if not _clause_targets_weapon_keyword_grant_unit(clause):
                continue
            for effect_index, effect in enumerate(clause.effects):
                grant = _catalog_weapon_keyword_grant_from_effect(
                    record=record,
                    clause=clause,
                    effect_index=effect_index,
                    effect=effect,
                )
                if grant is None:
                    continue
                grants.append(grant)
    return tuple(sorted(grants, key=lambda grant: grant.source_id))


def _catalog_roll_reroll_permission_for_unit(
    *,
    ability_index: AbilityCatalogIndex,
    unit: UnitInstance,
    current_model_instance_ids: tuple[str, ...],
    player_id: str,
    roll_type: str,
    timing_window: str,
) -> RerollPermission | None:
    _validate_ability_index(ability_index)
    _validate_unit(unit)
    current_ids = _validate_current_model_instance_ids(current_model_instance_ids)
    owning_player_id = _validate_identifier("player_id", player_id)
    requested_roll_type = _validate_identifier("roll_type", roll_type)
    requested_timing_window = _validate_identifier("timing_window", timing_window)
    permissions: list[RerollPermission] = []
    for record in _unit_scoped_generic_records(
        ability_index=ability_index,
        unit=unit,
        current_model_instance_ids=current_ids,
        trigger_kind=TimingTriggerKind.AFTER_DICE_ROLL,
    ):
        rule_ir = _rule_ir_from_record(record)
        if not rule_ir.is_supported:
            continue
        for clause in rule_ir.clauses:
            if not _clause_targets_roll_reroll_unit(clause):
                continue
            for effect_index, effect in enumerate(clause.effects):
                if not _effect_is_roll_reroll_permission(
                    effect,
                    roll_type=requested_roll_type,
                ):
                    continue
                permissions.append(
                    _catalog_roll_reroll_permission(
                        record=record,
                        clause=clause,
                        effect_index=effect_index,
                        player_id=owning_player_id,
                        roll_type=requested_roll_type,
                        timing_window=requested_timing_window,
                    )
                )
    if len(permissions) > 1:
        raise GameLifecycleError("Multiple catalog roll reroll permissions are available.")
    return permissions[0] if permissions else None


def catalog_leadership_characteristic_for_unit(
    *,
    ability_index: AbilityCatalogIndex,
    unit: UnitInstance,
    current_model_instance_ids: tuple[str, ...],
) -> int | None:
    _validate_ability_index(ability_index)
    _validate_unit(unit)
    current_ids = _validate_current_model_instance_ids(current_model_instance_ids)
    resolved_value: int | None = None
    resolved_source_id: str | None = None
    for record in _unit_scoped_generic_records(
        ability_index=ability_index,
        unit=unit,
        current_model_instance_ids=current_ids,
        trigger_kind=TimingTriggerKind.PASSIVE_QUERY,
    ):
        rule_ir = _rule_ir_from_record(record)
        for clause in rule_ir.clauses:
            if not _clause_targets_this_unit(clause):
                continue
            for effect in clause.effects:
                if not _effect_is_leadership_set(effect):
                    continue
                value = _leadership_value(parameter_payload(effect.parameters).get("value"))
                if resolved_value is not None and resolved_value != value:
                    raise GameLifecycleError(
                        "Catalog Leadership query found conflicting set-characteristic effects."
                    )
                resolved_value = value
                resolved_source_id = record.definition.source_id
    if resolved_value is not None and resolved_source_id is None:
        raise GameLifecycleError("Catalog Leadership query resolved without a source.")
    return resolved_value


def record_catalog_feel_no_pain_sources_for_unit(
    *,
    state: GameState,
    ability_index: AbilityCatalogIndex,
    unit: UnitInstance,
    current_model_instance_ids: tuple[str, ...],
) -> tuple[tuple[str, FeelNoPainSource], ...]:
    _validate_game_state(state)
    _validate_ability_index(ability_index)
    _validate_unit(unit)
    current_ids = _validate_current_model_instance_ids(current_model_instance_ids)
    recorded_sources: list[tuple[str, FeelNoPainSource]] = []
    for record in _unit_scoped_generic_records(
        ability_index=ability_index,
        unit=unit,
        current_model_instance_ids=current_ids,
        trigger_kind=TimingTriggerKind.PASSIVE_QUERY,
    ):
        if record.source_kind is not AbilitySourceKind.WARGEAR:
            continue
        bearer_ids = _record_current_wargear_bearer_model_ids(
            record=record,
            unit=unit,
            current_model_instance_ids=current_ids,
        )
        if not bearer_ids:
            continue
        rule_ir = _rule_ir_from_record(record)
        for clause in rule_ir.clauses:
            if not _clause_targets_this_model(clause):
                continue
            for effect_index, effect in enumerate(clause.effects):
                if not _effect_is_feel_no_pain_grant(effect):
                    continue
                source = _feel_no_pain_source_from_effect(
                    record=record,
                    clause=clause,
                    effect_index=effect_index,
                    effect=effect,
                )
                for bearer_id in bearer_ids:
                    _record_model_feel_no_pain_source(
                        state=state,
                        model_instance_id=bearer_id,
                        source=source,
                    )
                    recorded_sources.append((bearer_id, source))
    return tuple(sorted(recorded_sources, key=lambda binding: (binding[0], binding[1].source_id)))


def record_core_deadly_demise_sources_for_unit(
    *,
    state: GameState,
    unit: UnitInstance,
) -> tuple[tuple[str, DestructionReactionSource], ...]:
    _validate_game_state(state)
    _validate_unit(unit)
    profile = deadly_demise_profile_for_unit(unit)
    if profile is None:
        return ()
    recorded_sources: list[tuple[str, DestructionReactionSource]] = []
    for model in unit.own_models:
        source = _deadly_demise_source_for_model(
            profile=profile,
            model_instance_id=model.model_instance_id,
        )
        _record_model_destruction_reaction_source(
            state=state,
            model_instance_id=model.model_instance_id,
            source=source,
        )
        recorded_sources.append((model.model_instance_id, source))
    return tuple(sorted(recorded_sources, key=lambda binding: (binding[0], binding[1].source_id)))


def record_core_feel_no_pain_sources_for_unit(
    *,
    state: GameState,
    unit: UnitInstance,
) -> tuple[tuple[str, FeelNoPainSource], ...]:
    _validate_game_state(state)
    _validate_unit(unit)
    profile = feel_no_pain_profile_for_unit(unit)
    if profile is None:
        return ()
    recorded_sources: list[tuple[str, FeelNoPainSource]] = []
    for model in unit.own_models:
        source = _feel_no_pain_source_for_model(
            profile=profile,
            model_instance_id=model.model_instance_id,
        )
        _record_model_feel_no_pain_source(
            state=state,
            model_instance_id=model.model_instance_id,
            source=source,
        )
        recorded_sources.append((model.model_instance_id, source))
    return tuple(sorted(recorded_sources, key=lambda binding: (binding[0], binding[1].source_id)))


def record_core_fights_first_source_for_unit(
    *,
    state: GameState,
    unit: UnitInstance,
) -> PersistingEffect | None:
    _validate_game_state(state)
    _validate_unit(unit)
    source_id = fights_first_source_id_for_unit(
        unit,
        fallback_source_id=CORE_FIGHTS_FIRST_SOURCE_ID,
    )
    if source_id is None:
        return None
    effect = _fights_first_effect_for_unit(
        state=state,
        unit=unit,
        source_id=source_id,
    )
    _record_static_persisting_effect(state=state, effect=effect)
    return effect


def catalog_rule_ir_consumers_for_rule(rule_ir: RuleIR) -> tuple[str, ...]:
    if type(rule_ir) is not RuleIR:
        raise GameLifecycleError("Catalog rule consumer classification requires RuleIR.")
    consumer_ids: set[str] = set()
    for clause in rule_ir.clauses:
        consumer_ids.update(catalog_rule_ir_consumers_for_clause(clause))
    return tuple(sorted(consumer_ids))


def catalog_rule_ir_consumers_for_clause(clause: RuleClause) -> tuple[str, ...]:
    if type(clause) is not RuleClause:
        raise GameLifecycleError("Catalog rule consumer classification requires RuleClause.")
    consumer_ids: set[str] = set()
    if _clause_targets_this_model(clause):
        for effect in clause.effects:
            if _effect_is_feel_no_pain_grant(effect):
                consumer_ids.add(CATALOG_IR_FEEL_NO_PAIN_SOURCE_CONSUMER_ID)
    if _clause_targets_shadow_of_chaos_aura(clause):
        consumer_ids.add(CATALOG_IR_SHADOW_OF_CHAOS_AURA_CONSUMER_ID)
    if _clause_is_structured_wound_reroll_clause(clause):
        consumer_ids.add(CATALOG_IR_WOUND_ROLL_REROLL_CONSUMER_ID)
    if _clause_is_structured_destroyed_unit_restore_clause(clause):
        consumer_ids.add(CATALOG_IR_DESTROYED_UNIT_RESTORE_LOST_WOUNDS_CONSUMER_ID)
    if not _clause_targets_this_unit(clause):
        if _clause_targets_roll_reroll_unit(clause):
            for effect in clause.effects:
                reroll_consumer_id = _roll_reroll_consumer_id_for_effect(effect)
                if reroll_consumer_id is not None:
                    consumer_ids.add(reroll_consumer_id)
        if _clause_targets_weapon_keyword_grant_unit(clause):
            for effect in clause.effects:
                consumer_ids.update(_weapon_keyword_grant_consumer_ids_for_effect(effect))
        return tuple(sorted(consumer_ids))
    for effect in clause.effects:
        if _effect_is_charge_roll_modifier(effect):
            consumer_ids.add(CATALOG_IR_CHARGE_ROLL_CONSUMER_ID)
        reroll_consumer_id = _roll_reroll_consumer_id_for_effect(effect)
        if reroll_consumer_id is not None:
            consumer_ids.add(reroll_consumer_id)
        consumer_ids.update(_weapon_keyword_grant_consumer_ids_for_effect(effect))
        if _effect_is_leadership_set(effect):
            consumer_ids.add(CATALOG_IR_LEADERSHIP_QUERY_CONSUMER_ID)
        if _effect_is_turn_end_reserve_permission(effect):
            consumer_ids.add(CATALOG_IR_CAN_BE_PLACED_IN_RESERVES_CONSUMER_ID)
        advance_consumer_id = _advance_eligibility_consumer_id_for_effect(effect)
        if advance_consumer_id is not None:
            consumer_ids.add(advance_consumer_id)
    return tuple(sorted(consumer_ids))


def catalog_rule_ir_hook_ids_for_rule(rule_ir: RuleIR) -> tuple[str, ...]:
    if type(rule_ir) is not RuleIR:
        raise GameLifecycleError("Catalog rule consumer classification requires RuleIR.")
    hook_ids: set[str] = set()
    for clause in rule_ir.clauses:
        for effect in clause.effects:
            if _effect_is_charge_roll_modifier(effect):
                hook_ids.add(CATALOG_IR_CHARGE_ROLL_CONSUMER_ID)
            hook_ids.update(_catalog_ir_hook_ids_for_effect(effect))
    return tuple(sorted(hook_ids))


def _unit_scoped_generic_records(
    *,
    ability_index: AbilityCatalogIndex,
    unit: UnitInstance,
    current_model_instance_ids: tuple[str, ...],
    trigger_kind: TimingTriggerKind,
) -> tuple[AbilityCatalogRecord, ...]:
    if type(trigger_kind) is not TimingTriggerKind:
        raise GameLifecycleError("Catalog rule consumer trigger kind must be TimingTriggerKind.")
    return tuple(
        record
        for record in ability_index.records_for(trigger_kind)
        if record.definition.handler_id == GENERIC_RULE_IR_ABILITY_HANDLER_ID
        and _record_source_matches_unit(
            record=record,
            unit=unit,
            current_model_instance_ids=current_model_instance_ids,
        )
    )


def _unit_scoped_generic_records_for_all_timings(
    *,
    ability_index: AbilityCatalogIndex,
    unit: UnitInstance,
    current_model_instance_ids: tuple[str, ...],
) -> tuple[AbilityCatalogRecord, ...]:
    return tuple(
        record
        for record in ability_index.all_records()
        if record.definition.handler_id == GENERIC_RULE_IR_ABILITY_HANDLER_ID
        and _record_source_matches_unit(
            record=record,
            unit=unit,
            current_model_instance_ids=current_model_instance_ids,
        )
    )


def _matching_advance_eligibility_records(
    *,
    ability_indexes_by_player_id: Mapping[str, AbilityCatalogIndex],
    armies: tuple[ArmyDefinition, ...],
    context: AdvanceEligibilityContext,
    ability: str,
) -> tuple[AbilityCatalogRecord, ...]:
    requested_ability = _validate_identifier("ability", ability)
    army = _army_for_player(armies, player_id=context.player_id)
    unit = _unit_in_army_by_id(army, unit_instance_id=context.unit_instance_id)
    index = ability_indexes_by_player_id.get(context.player_id)
    if index is None:
        raise GameLifecycleError("Catalog advance eligibility index is missing player.")
    current_model_ids = _current_model_instance_ids_for_unit(state=context.state, unit=unit)
    matching_records: list[AbilityCatalogRecord] = []
    for record in _unit_scoped_generic_records(
        ability_index=index,
        unit=unit,
        current_model_instance_ids=current_model_ids,
        trigger_kind=TimingTriggerKind.PASSIVE_QUERY,
    ):
        rule_ir = _rule_ir_from_record(record)
        if _rule_ir_grants_advance_eligibility(rule_ir, ability=requested_ability):
            matching_records.append(record)
    return tuple(sorted(matching_records, key=lambda record: record.record_id))


def _rule_ir_from_record(record: AbilityCatalogRecord) -> RuleIR:
    if type(record) is not AbilityCatalogRecord:
        raise GameLifecycleError("Catalog rule consumer requires an AbilityCatalogRecord.")
    from warhammer40k_core.engine.rule_execution import rule_ir_from_execution_payload

    return rule_ir_from_execution_payload(record.definition.replay_payload)


def _clauses_from_record(record: AbilityCatalogRecord) -> tuple[RuleClause, ...]:
    if type(record) is not AbilityCatalogRecord:
        raise GameLifecycleError("Catalog rule consumer requires an AbilityCatalogRecord.")
    from warhammer40k_core.engine.rule_execution import scoped_rule_ir_from_execution_payload

    return scoped_rule_ir_from_execution_payload(record.definition.replay_payload).clauses


def _record_source_matches_unit(
    *,
    record: AbilityCatalogRecord,
    unit: UnitInstance,
    current_model_instance_ids: tuple[str, ...],
) -> bool:
    if record.source_kind is AbilitySourceKind.DATASHEET:
        return record.datasheet_id == unit.datasheet_id
    if record.source_kind is AbilitySourceKind.WARGEAR:
        return (
            record.datasheet_id == unit.datasheet_id
            and record.wargear_id is not None
            and _unit_has_current_wargear_bearer(
                unit=unit,
                current_model_instance_ids=current_model_instance_ids,
                wargear_id=record.wargear_id,
            )
        )
    return False


def _unit_has_current_wargear_bearer(
    *,
    unit: UnitInstance,
    current_model_instance_ids: tuple[str, ...],
    wargear_id: str,
) -> bool:
    return bool(
        _current_wargear_bearer_model_ids(
            unit=unit,
            current_model_instance_ids=current_model_instance_ids,
            wargear_id=wargear_id,
        )
    )


def _record_current_wargear_bearer_model_ids(
    *,
    record: AbilityCatalogRecord,
    unit: UnitInstance,
    current_model_instance_ids: tuple[str, ...],
) -> tuple[str, ...]:
    if type(record) is not AbilityCatalogRecord:
        raise GameLifecycleError("Catalog rule consumer requires an AbilityCatalogRecord.")
    if record.source_kind is not AbilitySourceKind.WARGEAR:
        return ()
    if record.wargear_id is None:
        raise GameLifecycleError("Catalog wargear Feel No Pain source is missing wargear_id.")
    return _current_wargear_bearer_model_ids(
        unit=unit,
        current_model_instance_ids=current_model_instance_ids,
        wargear_id=record.wargear_id,
    )


def _current_wargear_bearer_model_ids(
    *,
    unit: UnitInstance,
    current_model_instance_ids: tuple[str, ...],
    wargear_id: str,
) -> tuple[str, ...]:
    current_ids = frozenset(current_model_instance_ids)
    known_model_ids = {model.model_instance_id for model in unit.own_models}
    unknown_ids = current_ids - known_model_ids
    if unknown_ids:
        raise GameLifecycleError("Catalog rule current model evidence contains unknown models.")
    return tuple(
        sorted(
            model.model_instance_id
            for model in unit.own_models
            if model.model_instance_id in current_ids
            and model.is_alive
            and wargear_id in model.wargear_ids
        )
    )


def _validate_this_model_source_id(
    *,
    unit: UnitInstance,
    current_model_instance_ids: tuple[str, ...],
) -> str:
    if len(current_model_instance_ids) != 1:
        raise GameLifecycleError("Catalog this-model rule requires exactly one source model.")
    source_model_id = current_model_instance_ids[0]
    for model in unit.own_models:
        if model.model_instance_id != source_model_id:
            continue
        if not model.is_alive:
            raise GameLifecycleError("Catalog this-model source must be alive.")
        return source_model_id
    raise GameLifecycleError("Catalog this-model source is not owned by the unit.")


def _this_model_restore_missing_wounds(
    *,
    unit: UnitInstance,
    source_model_id: str,
) -> int:
    source_missing_wounds: int | None = None
    wounded_model_ids = tuple(
        model.model_instance_id
        for model in unit.own_models
        if model.is_alive and model.wounds_remaining < model.starting_wounds
    )
    if not wounded_model_ids:
        return 0
    for model in unit.own_models:
        if model.model_instance_id != source_model_id:
            continue
        source_missing_wounds = model.starting_wounds - model.wounds_remaining
        break
    if source_missing_wounds is None:
        raise GameLifecycleError("Catalog this-model healing source model is missing.")
    if source_missing_wounds <= 0:
        return 0
    if wounded_model_ids == (source_model_id,):
        return source_missing_wounds
    if source_model_id not in wounded_model_ids:
        return 0
    raise GameLifecycleError("Catalog this-model healing cannot target multiple wounded models.")


def _clause_targets_this_unit(clause: RuleClause) -> bool:
    if type(clause) is not RuleClause:
        raise GameLifecycleError("Catalog rule consumer requires RuleClause values.")
    return clause.target is not None and clause.target.kind is RuleTargetKind.THIS_UNIT


def _clause_targets_this_model(clause: RuleClause) -> bool:
    if type(clause) is not RuleClause:
        raise GameLifecycleError("Catalog rule consumer requires RuleClause values.")
    return clause.target is not None and clause.target.kind is RuleTargetKind.THIS_MODEL


def _clause_targets_roll_reroll_unit(clause: RuleClause) -> bool:
    if _clause_targets_this_unit(clause):
        return True
    if type(clause) is not RuleClause:
        raise GameLifecycleError("Catalog rule consumer requires RuleClause values.")
    return (
        clause.target is not None
        and clause.target.kind is RuleTargetKind.SELECTED_UNIT
        and _clause_has_leading_unit_relationship(clause)
    )


def _clause_has_leading_unit_relationship(clause: RuleClause) -> bool:
    if type(clause) is not RuleClause:
        raise GameLifecycleError("Catalog rule consumer requires RuleClause values.")
    return any(
        condition.kind is RuleConditionKind.TARGET_CONSTRAINT
        and parameter_payload(condition.parameters).get("relationship") == "this_model_leading_unit"
        for condition in clause.conditions
    )


def _clause_is_structured_wound_reroll_clause(clause: RuleClause) -> bool:
    if type(clause) is not RuleClause:
        raise GameLifecycleError("Catalog rule consumer requires RuleClause values.")
    return (
        _clause_targets_this_model(clause)
        and _clause_has_melee_attack_target_gate(clause)
        and _clause_has_roll_trigger(clause, roll_type="wound", attack_kind="melee")
        and any(
            _effect_is_roll_reroll_permission(effect, roll_type="wound_roll")
            for effect in clause.effects
        )
    )


def _clause_is_structured_destroyed_unit_restore_clause(clause: RuleClause) -> bool:
    if type(clause) is not RuleClause:
        raise GameLifecycleError("Catalog rule consumer requires RuleClause values.")
    return (
        _clause_targets_this_model(clause)
        and _clause_has_destroyed_enemy_unit_gate(clause)
        and clause.trigger is not None
        and clause.trigger.kind is RuleTriggerKind.UNIT_DESTROYED
        and any(effect.kind is RuleEffectKind.RESTORE_LOST_WOUNDS for effect in clause.effects)
    )


def _clause_is_melee_wound_reroll_against_target_keywords(
    *,
    clause: RuleClause,
    attack_kind: str,
    target_keywords: tuple[str, ...],
) -> bool:
    if attack_kind != "melee":
        return False
    if not _clause_is_structured_wound_reroll_clause(clause):
        return False
    required_keywords = _clause_required_keyword_any(
        clause=clause,
        gate_subject="attack_target",
    )
    return _keywords_match_any(
        target_keywords=target_keywords,
        required_keywords=required_keywords,
    )


def _clause_is_destroyed_enemy_keyword_restore_lost_wounds(
    *,
    clause: RuleClause,
    destroyed_unit_keywords: tuple[str, ...],
) -> bool:
    if not _clause_is_structured_destroyed_unit_restore_clause(clause):
        return False
    required_keywords = _clause_required_keyword_any(
        clause=clause,
        gate_subject="destroyed_unit",
    )
    return _keywords_match_any(
        target_keywords=destroyed_unit_keywords,
        required_keywords=required_keywords,
    )


def _clause_has_roll_trigger(
    clause: RuleClause,
    *,
    roll_type: str,
    attack_kind: str | None = None,
) -> bool:
    trigger = clause.trigger
    if trigger is None or trigger.kind is not RuleTriggerKind.DICE_ROLL:
        return False
    parameters = parameter_payload(trigger.parameters)
    return parameters.get("roll_type") == roll_type and (
        attack_kind is None or parameters.get("attack_kind") == attack_kind
    )


def _clause_has_melee_attack_target_gate(clause: RuleClause) -> bool:
    return any(
        condition.kind is RuleConditionKind.TARGET_CONSTRAINT
        and parameter_payload(condition.parameters).get("relationship") == "this_model_makes_attack"
        and parameter_payload(condition.parameters).get("attack_kind") == "melee"
        and parameter_payload(condition.parameters).get("gate_subject") == "attack_target"
        for condition in clause.conditions
    ) and bool(_clause_required_keyword_any(clause=clause, gate_subject="attack_target"))


def _clause_has_destroyed_enemy_unit_gate(clause: RuleClause) -> bool:
    return any(
        condition.kind is RuleConditionKind.TARGET_CONSTRAINT
        and parameter_payload(condition.parameters).get("relationship")
        == "this_model_destroyed_unit"
        and parameter_payload(condition.parameters).get("destroyed_allegiance") == "enemy"
        and parameter_payload(condition.parameters).get("gate_subject") == "destroyed_unit"
        for condition in clause.conditions
    ) and bool(_clause_required_keyword_any(clause=clause, gate_subject="destroyed_unit"))


def _clause_required_keyword_any(
    *,
    clause: RuleClause,
    gate_subject: str,
) -> tuple[str, ...]:
    required_keywords: list[str] = []
    for condition in clause.conditions:
        if condition.kind is not RuleConditionKind.KEYWORD_GATE:
            continue
        parameters = parameter_payload(condition.parameters)
        if parameters.get("gate_subject") != gate_subject:
            continue
        value = parameters.get("required_keyword_any")
        if type(value) is not str:
            continue
        required_keywords.extend(_keyword_tuple_from_any_parameter(value))
    return tuple(dict.fromkeys(required_keywords))


def _keyword_tuple_from_any_parameter(value: str) -> tuple[str, ...]:
    keywords = tuple(keyword for keyword in value.split("|") if keyword)
    if not keywords:
        raise GameLifecycleError("Catalog keyword-any condition is empty.")
    return keywords


def _keywords_match_any(
    *,
    target_keywords: tuple[str, ...],
    required_keywords: tuple[str, ...],
) -> bool:
    if not required_keywords:
        return False
    target_keyword_set = {_catalog_keyword_token(keyword) for keyword in target_keywords}
    return any(
        _catalog_keyword_token(keyword) in target_keyword_set for keyword in required_keywords
    )


def _clause_targets_weapon_keyword_grant_unit(clause: RuleClause) -> bool:
    if type(clause) is not RuleClause:
        raise GameLifecycleError("Catalog rule consumer requires RuleClause values.")
    if clause.trigger is not None:
        return False
    return _clause_targets_this_unit(clause) or (
        clause.target is not None
        and clause.target.kind is RuleTargetKind.SELECTED_UNIT
        and _clause_has_leading_unit_relationship(clause)
    )


def _effect_is_charge_roll_modifier(effect: RuleEffectSpec) -> bool:
    if type(effect) is not RuleEffectSpec:
        raise GameLifecycleError("Catalog rule consumer requires RuleEffectSpec values.")
    if effect.kind is not RuleEffectKind.MODIFY_DICE_ROLL:
        return False
    parameters = parameter_payload(effect.parameters)
    roll_type = parameters.get("roll_type")
    return roll_type in {"charge", "charge_roll"}


def _effect_is_roll_reroll_permission(effect: RuleEffectSpec, *, roll_type: str) -> bool:
    if type(effect) is not RuleEffectSpec:
        raise GameLifecycleError("Catalog rule consumer requires RuleEffectSpec values.")
    if effect.kind is not RuleEffectKind.REROLL_PERMISSION:
        return False
    parameters = parameter_payload(effect.parameters)
    value = parameters.get("roll_type")
    if type(value) is not str:
        return False
    return _CATALOG_IR_ROLL_REROLL_CONSUMER_IDS.get(
        _catalog_ir_lookup_token(value)
    ) == _CATALOG_IR_ROLL_REROLL_CONSUMER_IDS.get(_catalog_ir_lookup_token(roll_type))


def _roll_reroll_consumer_id_for_effect(effect: RuleEffectSpec) -> str | None:
    if type(effect) is not RuleEffectSpec:
        raise GameLifecycleError("Catalog rule consumer requires RuleEffectSpec values.")
    if effect.kind is not RuleEffectKind.REROLL_PERMISSION:
        return None
    parameters = parameter_payload(effect.parameters)
    roll_type = parameters.get("roll_type")
    if type(roll_type) is not str:
        return None
    return _CATALOG_IR_ROLL_REROLL_CONSUMER_IDS.get(_catalog_ir_lookup_token(roll_type))


def _weapon_keyword_grant_consumer_ids_for_effect(effect: RuleEffectSpec) -> tuple[str, ...]:
    if type(effect) is not RuleEffectSpec:
        raise GameLifecycleError("Catalog rule consumer requires RuleEffectSpec values.")
    if effect.kind is not RuleEffectKind.GRANT_WEAPON_ABILITY:
        return ()
    parameters = parameter_payload(effect.parameters)
    keyword = _weapon_keyword_from_parameters(parameters)
    if keyword is None:
        return ()
    if not _weapon_keyword_grant_has_supported_runtime_shape(parameters, keyword=keyword):
        return ()
    return (
        CATALOG_IR_WEAPON_KEYWORD_GRANT_CONSUMER_ID,
        _catalog_ir_weapon_keyword_grant_consumer_id(keyword.value),
    )


def _effect_is_leadership_set(effect: RuleEffectSpec) -> bool:
    if type(effect) is not RuleEffectSpec:
        raise GameLifecycleError("Catalog rule consumer requires RuleEffectSpec values.")
    if effect.kind is not RuleEffectKind.SET_CHARACTERISTIC:
        return False
    parameters = parameter_payload(effect.parameters)
    return parameters.get("characteristic") == Characteristic.LEADERSHIP.value


def _effect_is_feel_no_pain_grant(effect: RuleEffectSpec) -> bool:
    if type(effect) is not RuleEffectSpec:
        raise GameLifecycleError("Catalog rule consumer requires RuleEffectSpec values.")
    if effect.kind is not RuleEffectKind.GRANT_ABILITY:
        return False
    parameters = parameter_payload(effect.parameters)
    return parameters.get("ability") == "Feel No Pain"


def _effect_is_turn_end_reserve_permission(effect: RuleEffectSpec) -> bool:
    if type(effect) is not RuleEffectSpec:
        raise GameLifecycleError("Catalog rule consumer requires RuleEffectSpec values.")
    if effect.kind is not RuleEffectKind.PLACEMENT_PERMISSION:
        return False
    parameters = parameter_payload(effect.parameters)
    return (
        parameters.get("placement_kind") == "turn_end_reserves"
        and parameters.get("reserve_kind") == "strategic_reserves"
        and parameters.get("action") == "remove_from_battlefield_to_strategic_reserves"
    )


def _clause_targets_shadow_of_chaos_aura(clause: RuleClause) -> bool:
    if type(clause) is not RuleClause:
        raise GameLifecycleError("Catalog rule consumer requires RuleClause values.")
    return (
        clause.target is not None
        and clause.target.kind is RuleTargetKind.AURA_UNITS
        and any(condition.kind is RuleConditionKind.AURA for condition in clause.conditions)
        and any(_effect_is_shadow_of_chaos_status(effect) for effect in clause.effects)
    )


def _effect_is_shadow_of_chaos_status(effect: RuleEffectSpec) -> bool:
    if type(effect) is not RuleEffectSpec:
        raise GameLifecycleError("Catalog rule consumer requires RuleEffectSpec values.")
    if effect.kind is not RuleEffectKind.SET_CONTEXTUAL_STATUS:
        return False
    parameters = parameter_payload(effect.parameters)
    return (
        parameters.get("status") == "within_shadow_of_chaos"
        and parameters.get("rules_context") == "shadow_of_chaos"
        and parameters.get("owner") == "your_army"
    )


def _rule_ir_grants_advance_eligibility(rule_ir: RuleIR, *, ability: str) -> bool:
    if type(rule_ir) is not RuleIR:
        raise GameLifecycleError("Catalog advance eligibility requires RuleIR.")
    if not rule_ir.is_supported:
        return False
    requested_ability = _validate_identifier("ability", ability)
    return any(
        _clause_targets_this_unit(clause)
        and any(
            _effect_grants_ability(effect, ability=requested_ability) for effect in clause.effects
        )
        for clause in rule_ir.clauses
    )


def _advance_eligibility_consumer_id_for_effect(effect: RuleEffectSpec) -> str | None:
    if type(effect) is not RuleEffectSpec:
        raise GameLifecycleError("Catalog rule consumer requires RuleEffectSpec values.")
    if effect.kind is not RuleEffectKind.GRANT_ABILITY:
        return None
    parameters = parameter_payload(effect.parameters)
    ability = parameters.get("ability")
    if type(ability) is not str:
        return None
    return _CATALOG_IR_ADVANCE_ELIGIBILITY_GRANT_CONSUMER_IDS.get(_catalog_ir_lookup_token(ability))


def _effect_grants_ability(effect: RuleEffectSpec, *, ability: str) -> bool:
    if type(effect) is not RuleEffectSpec:
        raise GameLifecycleError("Catalog rule consumer requires RuleEffectSpec values.")
    if effect.kind is not RuleEffectKind.GRANT_ABILITY:
        return False
    parameters = parameter_payload(effect.parameters)
    value = parameters.get("ability")
    return type(value) is str and _catalog_ir_lookup_token(value) == _catalog_ir_lookup_token(
        ability
    )


def _feel_no_pain_source_from_effect(
    *,
    record: AbilityCatalogRecord,
    clause: RuleClause,
    effect_index: int,
    effect: RuleEffectSpec,
) -> FeelNoPainSource:
    if type(record) is not AbilityCatalogRecord:
        raise GameLifecycleError("Catalog Feel No Pain source requires an ability record.")
    if type(clause) is not RuleClause:
        raise GameLifecycleError("Catalog Feel No Pain source requires a rule clause.")
    if type(effect_index) is not int or effect_index < 0:
        raise GameLifecycleError("Catalog Feel No Pain effect_index must be non-negative.")
    if not _effect_is_feel_no_pain_grant(effect):
        raise GameLifecycleError("Catalog Feel No Pain source requires a Feel No Pain grant.")
    parameters = parameter_payload(effect.parameters)
    return FeelNoPainSource(
        source_id=f"{record.record_id}:{clause.clause_id}:effect-{effect_index:03d}",
        threshold=_int_parameter(parameters, key="threshold"),
        attack_condition=_feel_no_pain_attack_condition_parameter(parameters),
    )


def _catalog_roll_reroll_permission(
    *,
    record: AbilityCatalogRecord,
    clause: RuleClause,
    effect_index: int,
    player_id: str,
    roll_type: str,
    timing_window: str,
) -> RerollPermission:
    if type(record) is not AbilityCatalogRecord:
        raise GameLifecycleError("Catalog reroll permission requires an ability record.")
    if type(clause) is not RuleClause:
        raise GameLifecycleError("Catalog reroll permission requires a rule clause.")
    if type(effect_index) is not int or effect_index < 0:
        raise GameLifecycleError("Catalog reroll permission effect_index must be non-negative.")
    return RerollPermission(
        source_id=f"{record.record_id}:{clause.clause_id}:effect-{effect_index:03d}:reroll",
        timing_window=_validate_identifier("timing_window", timing_window),
        owning_player_id=_validate_identifier("player_id", player_id),
        eligible_roll_type=_validate_identifier("roll_type", roll_type),
        component_selection_policy=RerollComponentSelectionPolicy.WHOLE_ROLL,
    )


def _catalog_weapon_keyword_grant_from_effect(
    *,
    record: AbilityCatalogRecord,
    clause: RuleClause,
    effect_index: int,
    effect: RuleEffectSpec,
) -> CatalogWeaponKeywordGrant | None:
    if type(record) is not AbilityCatalogRecord:
        raise GameLifecycleError("Catalog weapon keyword grant requires an ability record.")
    if type(clause) is not RuleClause:
        raise GameLifecycleError("Catalog weapon keyword grant requires a rule clause.")
    if type(effect_index) is not int or effect_index < 0:
        raise GameLifecycleError("Catalog weapon keyword grant effect_index must be non-negative.")
    if type(effect) is not RuleEffectSpec:
        raise GameLifecycleError("Catalog weapon keyword grant requires a rule effect.")
    if effect.kind is not RuleEffectKind.GRANT_WEAPON_ABILITY:
        return None
    parameters = parameter_payload(effect.parameters)
    keyword = _weapon_keyword_from_parameters(parameters)
    if keyword is None:
        return None
    if not _weapon_keyword_grant_has_supported_runtime_shape(parameters, keyword=keyword):
        return None
    return CatalogWeaponKeywordGrant(
        source_id=f"{record.record_id}:{clause.clause_id}:effect-{effect_index:03d}:weapon-keyword",
        keyword=keyword,
        weapon_scope=_weapon_scope_parameter(parameters),
        ability=_weapon_ability_descriptor_for_grant(parameters=parameters, keyword=keyword),
    )


def _profile_with_catalog_weapon_keyword_grant(
    *,
    profile: WeaponProfile,
    grant: CatalogWeaponKeywordGrant,
) -> WeaponProfile:
    if type(profile) is not WeaponProfile:
        raise GameLifecycleError("Catalog weapon keyword grant requires a WeaponProfile.")
    if type(grant) is not CatalogWeaponKeywordGrant:
        raise GameLifecycleError("Catalog weapon keyword grant requires grant data.")
    keywords = profile.keywords
    if grant.keyword not in keywords:
        keywords = tuple(sorted((*keywords, grant.keyword), key=lambda keyword: keyword.value))
    abilities = profile.abilities
    if grant.ability is not None and all(
        ability.ability_id != grant.ability.ability_id for ability in abilities
    ):
        abilities = tuple(
            sorted((*abilities, grant.ability), key=lambda ability: ability.ability_id)
        )
    source_ids = profile.source_ids
    if grant.source_id not in source_ids:
        source_ids = tuple(sorted((*source_ids, grant.source_id)))
    if (
        keywords == profile.keywords
        and abilities == profile.abilities
        and source_ids == profile.source_ids
    ):
        return profile
    return replace(profile, keywords=keywords, abilities=abilities, source_ids=source_ids)


def _weapon_keyword_from_parameters(parameters: Mapping[str, object]) -> WeaponKeyword | None:
    value = parameters.get("weapon_ability")
    if type(value) is not str:
        return None
    try:
        return weapon_keyword_from_token(value)
    except WeaponProfileError as exc:
        raise GameLifecycleError("Catalog weapon keyword grant has unsupported keyword.") from exc


def _weapon_keyword_grant_has_supported_runtime_shape(
    parameters: Mapping[str, object],
    *,
    keyword: WeaponKeyword,
) -> bool:
    if _optional_weapon_scope_parameter(parameters) is None:
        return False
    if keyword in _VALUE_REQUIRED_WEAPON_KEYWORDS:
        return _optional_positive_int_parameter(parameters, key="weapon_ability_value") is not None
    return keyword is not WeaponKeyword.HUNTER


def _weapon_ability_descriptor_for_grant(
    *,
    parameters: Mapping[str, object],
    keyword: WeaponKeyword,
) -> AbilityDescriptor | None:
    if keyword is WeaponKeyword.LETHAL_HITS:
        return AbilityDescriptor.lethal_hits()
    if keyword is WeaponKeyword.DEVASTATING_WOUNDS:
        return AbilityDescriptor.devastating_wounds()
    if keyword is WeaponKeyword.HEAVY:
        return AbilityDescriptor.heavy()
    if keyword is WeaponKeyword.SUSTAINED_HITS:
        return AbilityDescriptor.sustained_hits(
            _required_positive_int_parameter(parameters, key="weapon_ability_value")
        )
    if keyword is WeaponKeyword.RAPID_FIRE:
        return AbilityDescriptor.rapid_fire(
            _required_positive_int_parameter(parameters, key="weapon_ability_value")
        )
    if keyword is WeaponKeyword.MELTA:
        return AbilityDescriptor.melta(
            _required_positive_int_parameter(parameters, key="weapon_ability_value")
        )
    if keyword is WeaponKeyword.CLEAVE:
        return AbilityDescriptor.cleave(
            _required_positive_int_parameter(parameters, key="weapon_ability_value")
        )
    if keyword is WeaponKeyword.HUNTER:
        raise GameLifecycleError("Catalog weapon keyword grant cannot infer Hunter targets.")
    return None


_VALUE_REQUIRED_WEAPON_KEYWORDS = frozenset(
    {
        WeaponKeyword.CLEAVE,
        WeaponKeyword.MELTA,
        WeaponKeyword.RAPID_FIRE,
        WeaponKeyword.SUSTAINED_HITS,
    }
)


def _weapon_scope_parameter(parameters: Mapping[str, object]) -> str:
    scope = _optional_weapon_scope_parameter(parameters)
    if scope is None:
        raise GameLifecycleError("Catalog weapon keyword grant requires a generic weapon scope.")
    return scope


def _optional_weapon_scope_parameter(parameters: Mapping[str, object]) -> str | None:
    value = parameters.get("weapon_scope")
    if value is not None:
        return _weapon_scope_from_token(value)
    weapon_name = parameters.get("weapon_name")
    if type(weapon_name) is str:
        return _generic_weapon_scope_from_token(weapon_name)
    return None


def _weapon_scope_from_token(value: object) -> str:
    if type(value) is not str:
        raise GameLifecycleError("Catalog weapon keyword grant weapon_scope must be a string.")
    scope = _generic_weapon_scope_from_token(value)
    if scope is None:
        raise GameLifecycleError("Unsupported catalog weapon keyword grant scope.")
    return scope


def _generic_weapon_scope_from_token(value: str) -> str | None:
    normalized = " ".join(value.strip().lower().replace("-", " ").split())
    if normalized in {"melee", "melee weapon", "melee weapons"}:
        return "melee"
    if normalized in {"ranged", "ranged weapon", "ranged weapons"}:
        return "ranged"
    if normalized in {"all", "weapon", "weapons", "all weapon", "all weapons"}:
        return "all"
    return None


def _weapon_keyword_from_value(value: object) -> WeaponKeyword:
    if type(value) is WeaponKeyword:
        return value
    if type(value) is str:
        try:
            return weapon_keyword_from_token(value)
        except WeaponProfileError as exc:
            raise GameLifecycleError(
                "Catalog weapon keyword grant keyword is unsupported."
            ) from exc
    raise GameLifecycleError("Catalog weapon keyword grant keyword must be a WeaponKeyword.")


def _required_positive_int_parameter(parameters: Mapping[str, object], *, key: str) -> int:
    value = _optional_positive_int_parameter(parameters, key=key)
    if value is None:
        raise GameLifecycleError(f"Catalog rule parameter {key} must be a positive integer.")
    return value


def _optional_positive_int_parameter(parameters: Mapping[str, object], *, key: str) -> int | None:
    value = parameters.get(key)
    if value is None:
        return None
    if type(value) is not int or value < 1:
        raise GameLifecycleError(f"Catalog rule parameter {key} must be a positive integer.")
    return value


def _weapon_scope_matches_profile(*, weapon_scope: str, profile: WeaponProfile) -> bool:
    if type(profile) is not WeaponProfile:
        raise GameLifecycleError("Catalog weapon keyword grant requires a WeaponProfile.")
    scope = _weapon_scope_from_token(weapon_scope)
    if scope == "all":
        return True
    if scope == "melee":
        return profile.range_profile.kind is RangeProfileKind.MELEE
    if scope == "ranged":
        return profile.range_profile.kind is RangeProfileKind.DISTANCE
    raise GameLifecycleError("Unsupported catalog weapon keyword grant scope.")


def _feel_no_pain_attack_condition_parameter(
    parameters: Mapping[str, object],
) -> FeelNoPainAttackCondition | None:
    value = parameters.get("attack_condition")
    if value is None:
        return None
    if type(value) is not str or not value.strip():
        raise GameLifecycleError(
            "Catalog rule parameter attack_condition must be a non-empty string."
        )
    return feel_no_pain_attack_condition_from_token(value.strip())


def _deadly_demise_source_for_model(
    *,
    profile: DeadlyDemiseAbilityProfile,
    model_instance_id: str,
) -> DestructionReactionSource:
    if type(profile) is not DeadlyDemiseAbilityProfile:
        raise GameLifecycleError("Deadly Demise source registration requires an ability profile.")
    model_id = _string_identifier("Deadly Demise source model_instance_id", model_instance_id)
    return DestructionReactionSource(
        source_id=f"{profile.source_id}:{model_id}:deadly-demise",
        reaction_kind=DestructionReactionKind.DEADLY_DEMISE,
        source_rule_id=profile.source_id,
        payload=_deadly_demise_source_payload(profile.mortal_wounds_token),
        optional=False,
    )


def _deadly_demise_source_payload(token: str) -> dict[str, JsonValue]:
    mortal_wounds = _deadly_demise_mortal_wounds_payload(token)
    return {
        "trigger_roll_threshold": DEADLY_DEMISE_TRIGGER_ROLL_THRESHOLD,
        "range_inches": DEADLY_DEMISE_RANGE_INCHES,
        "mortal_wounds": mortal_wounds,
    }


def _deadly_demise_mortal_wounds_payload(token: str) -> dict[str, JsonValue]:
    normalized = _string_identifier("Deadly Demise mortal wounds token", token).upper()
    if normalized == "D3":
        return {"kind": "d3"}
    if normalized == "D6":
        return {"kind": "d6"}
    try:
        value = int(normalized)
    except ValueError as exc:
        raise GameLifecycleError("Unsupported Deadly Demise mortal-wound token.") from exc
    if value < 1:
        raise GameLifecycleError("Deadly Demise fixed mortal wounds must be positive.")
    return {"kind": "fixed", "value": value}


def _feel_no_pain_source_for_model(
    *,
    profile: FeelNoPainAbilityProfile,
    model_instance_id: str,
) -> FeelNoPainSource:
    if type(profile) is not FeelNoPainAbilityProfile:
        raise GameLifecycleError("Feel No Pain source registration requires an ability profile.")
    model_id = _string_identifier("Feel No Pain source model_instance_id", model_instance_id)
    return FeelNoPainSource(
        source_id=f"{profile.source_id}:{model_id}:feel-no-pain",
        threshold=profile.threshold,
    )


def _fights_first_effect_for_unit(
    *,
    state: GameState,
    unit: UnitInstance,
    source_id: str,
) -> PersistingEffect:
    unit_id = _string_identifier("Fights First unit_instance_id", unit.unit_instance_id)
    source = _string_identifier("Fights First source_id", source_id)
    owner = _owner_player_id_for_unit(state=state, unit=unit)
    return PersistingEffect(
        effect_id=f"{source}:{unit_id}:fights-first",
        source_rule_id=source,
        owner_player_id=owner,
        target_unit_instance_ids=(unit_id,),
        started_battle_round=_static_ability_started_battle_round(state),
        expiration=EffectExpiration.end_of_battle(),
        effect_payload={
            "effect_kind": CORE_FIGHTS_FIRST_EFFECT_KIND,
            "source_rule_id": source,
        },
    )


def _record_model_feel_no_pain_source(
    *,
    state: GameState,
    model_instance_id: str,
    source: FeelNoPainSource,
) -> None:
    existing_sources = state.feel_no_pain_sources_for_model(model_instance_id=model_instance_id)
    for existing_source in existing_sources:
        if existing_source.source_id != source.source_id:
            continue
        if existing_source != source:
            raise GameLifecycleError("Catalog Feel No Pain source conflicts with existing state.")
        return
    state.record_model_feel_no_pain_sources(
        model_instance_id=model_instance_id,
        sources=(*existing_sources, source),
        decline_allowed=state.feel_no_pain_decline_allowed_for_model(
            model_instance_id=model_instance_id
        ),
    )


def _record_static_persisting_effect(
    *,
    state: GameState,
    effect: PersistingEffect,
) -> None:
    for existing_effect in state.persisting_effects:
        if existing_effect.effect_id != effect.effect_id:
            continue
        if existing_effect != effect:
            raise GameLifecycleError("Core static persisting effect conflicts with existing state.")
        return
    state.record_persisting_effect(effect)


def _record_model_destruction_reaction_source(
    *,
    state: GameState,
    model_instance_id: str,
    source: DestructionReactionSource,
) -> None:
    existing_sources = state.destruction_reaction_sources_for_model(
        model_instance_id=model_instance_id
    )
    for existing_source in existing_sources:
        if existing_source.source_id != source.source_id:
            continue
        if existing_source != source:
            raise GameLifecycleError("Core Deadly Demise source conflicts with existing state.")
        return
    state.record_model_destruction_reaction_sources(
        model_instance_id=model_instance_id,
        sources=(*existing_sources, source),
    )


def _owner_player_id_for_unit(*, state: GameState, unit: UnitInstance) -> str:
    for army in state.army_definitions:
        if any(stored.unit_instance_id == unit.unit_instance_id for stored in army.units):
            return army.player_id
    raise GameLifecycleError("Core ability source registration requires a mustered unit.")


def _static_ability_started_battle_round(state: GameState) -> int:
    if type(state.battle_round) is not int:
        raise GameLifecycleError("Core static ability source requires an integer battle round.")
    if state.battle_round < 0:
        raise GameLifecycleError("Core static ability source requires a non-negative battle round.")
    return 1


def _catalog_ir_hook_ids_for_effect(effect: RuleEffectSpec) -> tuple[str, ...]:
    if type(effect) is not RuleEffectSpec:
        raise GameLifecycleError("Catalog rule consumer requires RuleEffectSpec values.")
    parameters = parameter_payload(effect.parameters)
    if effect.kind is RuleEffectKind.MODIFY_DICE_ROLL:
        return _catalog_ir_roll_modifier_hook_ids(parameters)
    if effect.kind is RuleEffectKind.FORCE_DESPERATE_ESCAPE_TESTS:
        return (CATALOG_IR_FORCE_DESPERATE_ESCAPE_CONSUMER_ID,)
    if effect.kind is RuleEffectKind.REROLL_PERMISSION:
        return _catalog_ir_roll_reroll_hook_ids(parameters)
    if effect.kind is RuleEffectKind.SET_CHARACTERISTIC:
        characteristic = _characteristic_parameter(parameters, key="characteristic")
        return (_catalog_ir_characteristic_query_consumer_id(characteristic),)
    if effect.kind is RuleEffectKind.MODIFY_CHARACTERISTIC:
        characteristic = _characteristic_parameter(parameters, key="characteristic")
        return (_catalog_ir_characteristic_modifier_consumer_id(characteristic),)
    if effect.kind is RuleEffectKind.MODIFY_MOVE_DISTANCE:
        return (_catalog_ir_characteristic_modifier_consumer_id(Characteristic.MOVEMENT),)
    if effect.kind is RuleEffectKind.GRANT_WEAPON_ABILITY:
        keyword = _string_parameter(parameters, key="weapon_ability")
        return (
            CATALOG_IR_WEAPON_KEYWORD_GRANT_CONSUMER_ID,
            _catalog_ir_weapon_keyword_grant_consumer_id(keyword),
        )
    if effect.kind is RuleEffectKind.GRANT_ABILITY and _effect_is_feel_no_pain_grant(effect):
        return (CATALOG_IR_FEEL_NO_PAIN_SOURCE_CONSUMER_ID,)
    if _effect_is_shadow_of_chaos_status(effect):
        return (CATALOG_IR_SHADOW_OF_CHAOS_AURA_CONSUMER_ID,)
    if effect.kind is RuleEffectKind.RESTORE_LOST_WOUNDS:
        return (CATALOG_IR_DESTROYED_UNIT_RESTORE_LOST_WOUNDS_CONSUMER_ID,)
    if effect.kind in {
        RuleEffectKind.GRANT_ABILITY,
        RuleEffectKind.PLACEMENT_PERMISSION,
    }:
        return _catalog_ir_rule_exception_hook_ids(effect.kind, parameters)
    return ()


def _catalog_ir_roll_modifier_hook_ids(parameters: Mapping[str, object]) -> tuple[str, ...]:
    roll_type = _string_parameter(parameters, key="roll_type")
    consumer_id = _CATALOG_IR_ROLL_MODIFIER_CONSUMER_IDS.get(_catalog_ir_lookup_token(roll_type))
    if consumer_id is None:
        return ()
    return (consumer_id,)


def _catalog_ir_roll_reroll_hook_ids(parameters: Mapping[str, object]) -> tuple[str, ...]:
    roll_type = _string_parameter(parameters, key="roll_type")
    consumer_id = _CATALOG_IR_ROLL_REROLL_CONSUMER_IDS.get(_catalog_ir_lookup_token(roll_type))
    if consumer_id is None:
        return ()
    return (consumer_id,)


def _catalog_ir_rule_exception_hook_ids(
    effect_kind: RuleEffectKind,
    parameters: Mapping[str, object],
) -> tuple[str, ...]:
    if effect_kind is RuleEffectKind.GRANT_ABILITY:
        ability = _string_parameter(parameters, key="ability")
        consumer_id = _CATALOG_IR_RULE_EXCEPTION_CONSUMER_IDS.get(_catalog_ir_lookup_token(ability))
        if consumer_id is None:
            return ()
        return (consumer_id,)
    placement_kind = parameters.get("placement_kind")
    if type(placement_kind) is not str:
        return ()
    consumer_id = _CATALOG_IR_RULE_EXCEPTION_CONSUMER_IDS.get(
        _catalog_ir_lookup_token(placement_kind)
    )
    if consumer_id is None:
        return ()
    return (consumer_id,)


def _catalog_ir_characteristic_query_consumer_id(characteristic: Characteristic) -> str:
    return f"catalog-ir:{_catalog_ir_token(characteristic.value)}-characteristic-query"


def _catalog_ir_characteristic_modifier_consumer_id(characteristic: Characteristic) -> str:
    return f"catalog-ir:{_catalog_ir_token(characteristic.value)}-characteristic-modifier"


def _catalog_ir_weapon_keyword_grant_consumer_id(keyword: str) -> str:
    return f"catalog-ir:weapon-keyword-grant:{_catalog_ir_token(keyword)}"


def _characteristic_parameter(
    parameters: Mapping[str, object],
    *,
    key: str,
) -> Characteristic:
    value = _string_parameter(parameters, key=key)
    try:
        return Characteristic(value)
    except ValueError as exc:
        raise GameLifecycleError("Catalog rule characteristic parameter is invalid.") from exc


def _string_parameter(parameters: Mapping[str, object], *, key: str) -> str:
    value = parameters.get(key)
    if type(value) is not str or not value.strip():
        raise GameLifecycleError(f"Catalog rule parameter {key} must be a non-empty string.")
    return value.strip()


def _string_identifier(label: str, value: object) -> str:
    if type(value) is not str or not value.strip():
        raise GameLifecycleError(f"{label} must be a non-empty string.")
    return value.strip()


def _catalog_ir_token(value: str) -> str:
    return value.strip().lower().replace("_", "-").replace(" ", "-")


def _catalog_ir_lookup_token(value: str) -> str:
    return value.strip().lower().replace("-", "_").replace(" ", "_")


def _catalog_keyword_token(value: str) -> str:
    return value.strip().upper().replace("-", "_").replace(" ", "_")


def _int_parameter(parameters: Mapping[str, object], *, key: str) -> int:
    value = parameters.get(key)
    if type(value) is not int:
        raise GameLifecycleError(f"Catalog rule parameter {key} must be an integer.")
    return value


def _leadership_value(value: object) -> int:
    if type(value) is int:
        return value
    if type(value) is str:
        stripped = value.strip()
        if stripped.endswith("+"):
            stripped = stripped[:-1]
        if stripped.isdecimal():
            return int(stripped)
    raise GameLifecycleError("Catalog Leadership set-characteristic value is invalid.")


def _validate_ability_index(ability_index: object) -> AbilityCatalogIndex:
    if type(ability_index) is not AbilityCatalogIndex:
        raise GameLifecycleError("Catalog rule consumer requires an AbilityCatalogIndex.")
    return ability_index


def _validate_game_state(state: GameState) -> GameState:
    from warhammer40k_core.engine.game_state import GameState as GameStateType

    if type(state) is not GameStateType:
        raise GameLifecycleError("Catalog rule consumer requires a GameState.")
    return state


def _validate_unit(unit: UnitInstance) -> UnitInstance:
    if type(unit) is not UnitInstance:
        raise GameLifecycleError("Catalog rule consumer requires a UnitInstance.")
    return unit


def _validate_current_model_instance_ids(values: object) -> tuple[str, ...]:
    if type(values) is not tuple:
        raise GameLifecycleError("Catalog rule current model evidence must be a tuple.")
    validated: list[str] = []
    seen: set[str] = set()
    for value in cast(tuple[object, ...], values):
        if type(value) is not str or not value.strip():
            raise GameLifecycleError("Catalog rule current model evidence must contain IDs.")
        stripped = value.strip()
        if stripped in seen:
            raise GameLifecycleError("Catalog rule current model evidence must not duplicate IDs.")
        seen.add(stripped)
        validated.append(stripped)
    if not validated:
        raise GameLifecycleError("Catalog rule current model evidence must not be empty.")
    return tuple(sorted(validated))


def _validate_keyword_tokens(field_name: str, values: object) -> tuple[str, ...]:
    if type(field_name) is not str or not field_name:
        raise GameLifecycleError("Catalog rule keyword validation requires a field name.")
    if type(values) is not tuple:
        raise GameLifecycleError(f"Catalog rule {field_name} must be a tuple.")
    validated: list[str] = []
    seen: set[str] = set()
    for value in cast(tuple[object, ...], values):
        if type(value) is not str or not value.strip():
            raise GameLifecycleError(f"Catalog rule {field_name} must contain keyword strings.")
        token = _catalog_keyword_token(value)
        if token in seen:
            raise GameLifecycleError(f"Catalog rule {field_name} must not duplicate keywords.")
        seen.add(token)
        validated.append(token)
    return tuple(validated)


def _validate_healing_amount(value: object) -> int:
    if type(value) is not int or value < 1 or value > 6:
        raise GameLifecycleError("Catalog restore lost wounds D6 result must be between 1 and 6.")
    return value


def _current_model_instance_ids_for_unit(
    *,
    state: GameState,
    unit: UnitInstance,
) -> tuple[str, ...]:
    _validate_game_state(state)
    _validate_unit(unit)
    if state.battlefield_state is None:
        raise GameLifecycleError("Catalog advance eligibility requires battlefield_state.")
    try:
        placement = state.battlefield_state.unit_placement_by_id(unit.unit_instance_id)
    except PlacementError as exc:
        raise GameLifecycleError("Catalog advance eligibility unit is not placed.") from exc
    return tuple(
        sorted(model_placement.model_instance_id for model_placement in placement.model_placements)
    )


def _has_advance_eligibility_records(
    ability_indexes_by_player_id: Mapping[str, AbilityCatalogIndex],
    *,
    ability: str,
) -> bool:
    requested_ability = _validate_identifier("ability", ability)
    return any(
        _record_can_grant_advance_eligibility(record, ability=requested_ability)
        for index in ability_indexes_by_player_id.values()
        for record in index.all_records()
    )


def _has_catalog_weapon_keyword_grant_records(
    ability_indexes_by_player_id: Mapping[str, AbilityCatalogIndex],
) -> bool:
    return any(
        _record_can_grant_catalog_weapon_keyword(record)
        for index in ability_indexes_by_player_id.values()
        for record in index.all_records()
    )


def _record_can_grant_catalog_weapon_keyword(record: AbilityCatalogRecord) -> bool:
    if type(record) is not AbilityCatalogRecord:
        raise GameLifecycleError("Catalog weapon keyword grants require ability records.")
    if record.definition.handler_id != GENERIC_RULE_IR_ABILITY_HANDLER_ID:
        return False
    rule_ir = _rule_ir_from_record(record)
    if not rule_ir.is_supported:
        return False
    return any(
        _clause_targets_weapon_keyword_grant_unit(clause)
        and any(_weapon_keyword_grant_consumer_ids_for_effect(effect) for effect in clause.effects)
        for clause in rule_ir.clauses
    )


def _record_can_grant_advance_eligibility(
    record: AbilityCatalogRecord,
    *,
    ability: str,
) -> bool:
    if type(record) is not AbilityCatalogRecord:
        raise GameLifecycleError("Catalog advance eligibility requires ability records.")
    if record.definition.handler_id != GENERIC_RULE_IR_ABILITY_HANDLER_ID:
        return False
    return _rule_ir_grants_advance_eligibility(_rule_ir_from_record(record), ability=ability)


def _army_for_player(armies: tuple[ArmyDefinition, ...], *, player_id: str) -> ArmyDefinition:
    requested_player_id = _validate_identifier("player_id", player_id)
    for army in armies:
        if army.player_id == requested_player_id:
            return army
    raise GameLifecycleError("Catalog advance eligibility player army is unknown.")


def _army_and_unit_for_unit_id(
    *,
    armies: tuple[ArmyDefinition, ...],
    unit_instance_id: str,
) -> tuple[ArmyDefinition, UnitInstance]:
    requested_unit_id = _validate_identifier("unit_instance_id", unit_instance_id)
    for army in armies:
        for unit in army.units:
            if unit.unit_instance_id == requested_unit_id:
                return army, unit
    raise GameLifecycleError("Catalog weapon keyword grant unit is unknown.")


def _unit_in_army_by_id(army: ArmyDefinition, *, unit_instance_id: str) -> UnitInstance:
    requested_unit_id = _validate_identifier("unit_instance_id", unit_instance_id)
    for unit in army.units:
        if unit.unit_instance_id == requested_unit_id:
            return unit
    raise GameLifecycleError("Catalog advance eligibility unit is unknown.")


def _validate_ability_index_mapping(
    value: object,
) -> Mapping[str, AbilityCatalogIndex]:
    if not isinstance(value, Mapping):
        raise GameLifecycleError("Catalog advance eligibility requires ability indexes.")
    mapping = cast(Mapping[object, object], value)
    validated: dict[str, AbilityCatalogIndex] = {}
    for player_id, index in mapping.items():
        validated[_validate_identifier("player_id", player_id)] = _validate_ability_index(index)
    return MappingProxyType(validated)


def _validate_armies(value: object) -> tuple[ArmyDefinition, ...]:
    if type(value) is not tuple:
        raise GameLifecycleError("Catalog advance eligibility requires army tuple.")
    armies: list[ArmyDefinition] = []
    seen: set[str] = set()
    for army in cast(tuple[object, ...], value):
        if type(army) is not ArmyDefinition:
            raise GameLifecycleError("Catalog advance eligibility requires ArmyDefinition values.")
        if army.player_id in seen:
            raise GameLifecycleError("Catalog advance eligibility duplicate player army.")
        seen.add(army.player_id)
        armies.append(army)
    return tuple(sorted(armies, key=lambda army: army.player_id))
