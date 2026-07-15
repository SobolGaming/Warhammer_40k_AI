from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from types import MappingProxyType
from typing import TYPE_CHECKING, cast

from warhammer40k_core.core.army_catalog import ArmyCatalog
from warhammer40k_core.core.attributes import Characteristic
from warhammer40k_core.core.dice import (
    DiceExpression,
    RerollComponentSelectionPolicy,
    RerollPermission,
)
from warhammer40k_core.core.modifiers import RollModifier
from warhammer40k_core.core.ruleset_descriptor import BattlePhaseKind, RulesetDescriptor
from warhammer40k_core.core.wargear import Wargear
from warhammer40k_core.core.weapon_profiles import (
    AbilityDescriptor,
    RangeProfileKind,
    WeaponKeyword,
    WeaponProfile,
    WeaponProfileError,
    canonical_weapon_keyword_tokens,
    weapon_keyword_from_token,
)
from warhammer40k_core.engine import catalog_command_point_support as _command_points
from warhammer40k_core.engine import catalog_contextual_status_consumption as _contextual
from warhammer40k_core.engine import catalog_datasheet_rule_support as _datasheet
from warhammer40k_core.engine import catalog_fight_end_triggered_movement_support as _fight_end_move
from warhammer40k_core.engine import catalog_movement_transit as _t
from warhammer40k_core.engine import catalog_once_per_battle_support as _frequency
from warhammer40k_core.engine import catalog_prebattle_redeploy as _prebattle_redeploy
from warhammer40k_core.engine import (
    catalog_reserve_arrival_restriction_classification as _reserve_restriction,
)
from warhammer40k_core.engine import catalog_rule_selected_target_classification as _st
from warhammer40k_core.engine import catalog_unit_move_completed_battle_shock_support as _ucbs
from warhammer40k_core.engine import rules_units as _rules_units
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
from warhammer40k_core.engine.attack_sequence import AttackSequence, AttackSequencePayload
from warhammer40k_core.engine.attack_sequence_completion_hooks import (
    AttackSequenceCompletedContext,
    AttackSequenceCompletedHookBinding,
    successful_hit_target_unit_ids_for_sequence,
)
from warhammer40k_core.engine.battlefield_state import (
    BattlefieldScenario,
    PlacementError,
    geometry_model_for_placement,
)
from warhammer40k_core.engine.catalog_tracked_target_weapon_grants import (
    CatalogWeaponKeywordGrant as CatalogWeaponKeywordGrant,
)
from warhammer40k_core.engine.catalog_tracked_target_weapon_grants import (
    catalog_weapon_grant_source_index_and_rules_unit,
    clause_is_tracked_target_weapon_grant,
    profile_with_catalog_weapon_keyword_grant,
    tracked_target_weapon_grant_applies,
    tracked_target_weapon_grant_from_clause,
)
from warhammer40k_core.engine.damage_allocation import (
    DestructionReactionKind,
    DestructionReactionSource,
    FeelNoPainAttackCondition,
    FeelNoPainSource,
    feel_no_pain_attack_condition_from_token,
)
from warhammer40k_core.engine.decision_controller import DecisionController
from warhammer40k_core.engine.decision_request import DecisionOption, DecisionRequest
from warhammer40k_core.engine.decision_result import DecisionResult
from warhammer40k_core.engine.effects import EffectExpiration, PersistingEffect
from warhammer40k_core.engine.event_log import JsonValue, validate_json_value
from warhammer40k_core.engine.faction_content.bundle_validation import (
    validate_identifier as _validate_identifier,
)
from warhammer40k_core.engine.fall_back_hooks import (
    FallBackEligibilityContext,
    FallBackEligibilityGrant,
    FallBackEligibilityHookBinding,
)
from warhammer40k_core.engine.phase import (
    BattlePhase,
    GameLifecycleError,
    GameLifecycleStage,
    LifecycleStatus,
)
from warhammer40k_core.engine.rules_units import RulesUnitView, rules_unit_view_by_id
from warhammer40k_core.engine.runtime_modifiers import (
    WeaponProfileModifierBinding,
    WeaponProfileModifierContext,
)
from warhammer40k_core.engine.shooting_phase_start_hooks import (
    SELECT_FACTION_RULE_SHOOTING_PHASE_START_OPTION_DECISION_TYPE,
    ShootingPhaseStartHookBinding,
    ShootingPhaseStartRequestContext,
    ShootingPhaseStartResultContext,
)
from warhammer40k_core.engine.timing_windows import TimingTriggerKind
from warhammer40k_core.engine.unit_abilities import (
    DeadlyDemiseAbilityProfile,
    FeelNoPainAbilityProfile,
    deadly_demise_profile_for_unit,
    feel_no_pain_profile_for_unit,
    fights_first_source_id_for_unit,
)
from warhammer40k_core.engine.unit_factory import ModelInstance, UnitInstance
from warhammer40k_core.engine.unit_move_completed_hooks import (
    UnitMoveCompletedContext,
    UnitMoveCompletedMortalWoundEffect,
    UnitMoveCompletedMortalWoundHookBinding,
)
from warhammer40k_core.geometry.volume import Model as GeometryModel
from warhammer40k_core.rules.rule_ir import (
    RuleClause,
    RuleCondition,
    RuleConditionKind,
    RuleDurationKind,
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

CatalogMovementTransitPermission = _t.CatalogMovementTransitPermission
_is_movement_transit = _t.clause_is_supported_movement_transit_permission
_movement_mode_token = _t.movement_mode_token
_movement_transit_permissions_from_clause = _t.movement_transit_permissions_from_clause

CATALOG_IR_CHARGE_ROLL_CONSUMER_ID = "catalog-ir:charge-roll-modifier"
CATALOG_IR_LEADERSHIP_QUERY_CONSUMER_ID = "catalog-ir:leadership-characteristic-query"
CATALOG_IR_HIT_ROLL_MODIFIER_CONSUMER_ID = "catalog-ir:hit-roll-modifier"
CATALOG_IR_MINIMUM_UNMODIFIED_HIT_SUCCESS_CONSUMER_ID = "catalog-ir:minimum-unmodified-hit-success"
CATALOG_IR_WOUND_ROLL_MODIFIER_CONSUMER_ID = "catalog-ir:wound-roll-modifier"
CATALOG_IR_SAVE_ROLL_MODIFIER_CONSUMER_ID = "catalog-ir:save-roll-modifier"
CATALOG_IR_INVULNERABLE_SAVE_ROLL_MODIFIER_CONSUMER_ID = (
    "catalog-ir:invulnerable-save-roll-modifier"
)
CATALOG_IR_DESPERATE_ESCAPE_ROLL_MODIFIER_CONSUMER_ID = "catalog-ir:desperate-escape-roll-modifier"
CATALOG_IR_FORCE_DESPERATE_ESCAPE_CONSUMER_ID = "catalog-ir:force-desperate-escape"
CATALOG_IR_ADVANCE_ROLL_REROLL_CONSUMER_ID = "catalog-ir:advance-roll-reroll"
CATALOG_IR_CHARGE_ROLL_REROLL_CONSUMER_ID = "catalog-ir:charge-roll-reroll"
CATALOG_IR_BATTLE_SHOCK_REROLL_CONSUMER_ID = _contextual.CATALOG_IR_BATTLE_SHOCK_REROLL_CONSUMER_ID
CATALOG_IR_HIT_ROLL_REROLL_CONSUMER_ID = _contextual.CATALOG_IR_HIT_ROLL_REROLL_CONSUMER_ID
CATALOG_IR_WOUND_ROLL_REROLL_CONSUMER_ID = _contextual.CATALOG_IR_WOUND_ROLL_REROLL_CONSUMER_ID
CATALOG_IR_DESTROYED_UNIT_RESTORE_LOST_WOUNDS_CONSUMER_ID = (
    "catalog-ir:destroyed-unit-restore-lost-wounds"
)
CATALOG_IR_TRACKED_TARGET_SELECTION_CONSUMER_ID = "catalog-ir:tracked-target-selection"
CATALOG_IR_TRACKED_TARGET_REROLL_CONSUMER_ID = "catalog-ir:tracked-target-reroll"
CATALOG_IR_TRACKED_TARGET_DESTROYED_RESELECT_CONSUMER_ID = (
    "catalog-ir:tracked-target-destroyed-reselect"
)
CATALOG_IR_FIRST_DEATH_RETURN_CONSUMER_ID = "catalog-ir:first-death-return"
CATALOG_IR_FIRST_DEATH_RETURN_PHASE_END_CONSUMER_ID = "catalog-ir:first-death-return-phase-end"
CATALOG_IR_FEEL_NO_PAIN_ROLL_CONSUMER_ID = "catalog-ir:feel-no-pain-roll"
CATALOG_IR_FEEL_NO_PAIN_SOURCE_CONSUMER_ID = "catalog-ir:feel-no-pain-source"
CATALOG_IR_CRITICAL_HIT_VALUE_MODIFIER_CONSUMER_ID = "catalog-ir:critical-hit-value-modifier"
CATALOG_IR_CRITICAL_WOUND_VALUE_MODIFIER_CONSUMER_ID = "catalog-ir:critical-wound-value-modifier"
CATALOG_IR_WEAPON_KEYWORD_GRANT_CONSUMER_ID = "catalog-ir:weapon-keyword-grant"
CATALOG_IR_NAMED_WEAPON_ABILITY_CHOICE_CONSUMER_ID = "catalog-ir:named-weapon-ability-choice"
CATALOG_IR_POST_SHOOT_HIT_TARGET_STATUS_CONSUMER_ID = "catalog-ir:post-shoot-hit-target-status"
CATALOG_IR_SELECTED_TARGET_EFFECT_CONSUMER_ID = "catalog-ir:selected-target-effect"
CATALOG_IR_ONCE_PER_BATTLE_ABILITY_CONSUMER_ID = "catalog-ir:once-per-battle-ability"
CATALOG_IR_POST_SHOOT_HIT_TARGET_EFFECT_CONSUMER_ID = "catalog-ir:post-shoot-hit-target-effect"
CATALOG_IR_SHOOTING_START_SELECTED_TARGET_EFFECT_CONSUMER_ID = (
    _st.CATALOG_IR_SHOOTING_START_SELECTED_TARGET_EFFECT_CONSUMER_ID
)
CATALOG_IR_PREBATTLE_REDEPLOY_PERMISSION_CONSUMER_ID = (
    _prebattle_redeploy.CATALOG_IR_PREBATTLE_REDEPLOY_PERMISSION_CONSUMER_ID
)
CATALOG_IR_UNIT_MOVE_COMPLETED_MORTAL_WOUNDS_CONSUMER_ID = (
    "catalog-ir:unit-move-completed-mortal-wounds"
)
CATALOG_IR_MOVEMENT_TRANSIT_PERMISSION_CONSUMER_ID = "catalog-ir:movement-transit-permission"
CATALOG_IR_SETUP_REACTIVE_SHOOT_CHARGE_CONSUMER_ID = "catalog-ir:setup-reactive-shoot-charge"
CATALOG_IR_CAN_ADVANCE_AND_CHARGE_CONSUMER_ID = "catalog-ir:can-advance-and-charge"
CATALOG_IR_CAN_FALLBACK_AND_CHARGE_CONSUMER_ID = "catalog-ir:can-fallback-and-charge"
CATALOG_IR_CAN_FALLBACK_AND_SHOOT_CONSUMER_ID = "catalog-ir:can-fallback-and-shoot"
CATALOG_IR_CAN_ADVANCE_AND_SHOOT_AND_CHARGE_CONSUMER_ID = (
    "catalog-ir:can-advance-and-shoot-and-charge"
)
CATALOG_IR_CAN_BE_PLACED_IN_RESERVES_CONSUMER_ID = "catalog-ir:can-be-placed-in-reserves"
CATALOG_IR_RESERVE_ARRIVAL_RESTRICTION_CONSUMER_ID = (
    _reserve_restriction.CATALOG_IR_RESERVE_ARRIVAL_RESTRICTION_CONSUMER_ID
)
CATALOG_IR_SHADOW_OF_CHAOS_AURA_CONSUMER_ID = (
    _contextual.CATALOG_IR_SHADOW_OF_CHAOS_AURA_CONSUMER_ID
)
CATALOG_IR_SHADOW_FORM_CHOICE_CONSUMER_ID = _contextual.CATALOG_IR_SHADOW_FORM_CHOICE_CONSUMER_ID
CATALOG_IR_SHOOTING_TARGET_RANGE_RESTRICTION_CONSUMER_ID = (
    _contextual.CATALOG_IR_SHOOTING_TARGET_RANGE_RESTRICTION_CONSUMER_ID
)
CATALOG_IR_BATTLE_SHOCK_FORCED_TEST_CONSUMER_ID = (
    _contextual.CATALOG_IR_BATTLE_SHOCK_FORCED_TEST_CONSUMER_ID
)
CATALOG_IR_BATTLE_SHOCK_FAILED_HEAL_CONSUMER_ID = (
    _contextual.CATALOG_IR_BATTLE_SHOCK_FAILED_HEAL_CONSUMER_ID
)
CATALOG_NAMED_WEAPON_ABILITY_CHOICE_EFFECT_KIND = "catalog_named_weapon_ability_choice"
CATALOG_NAMED_WEAPON_ABILITY_CHOICE_SELECTED_EVENT = "catalog_named_weapon_ability_choice_selected"
CATALOG_POST_SHOOT_HIT_TARGET_STATUS_EFFECT_KIND = "catalog_post_shoot_hit_target_status"
CATALOG_POST_SHOOT_HIT_TARGET_STATUS_SELECTED_EVENT = (
    "catalog_post_shoot_hit_target_status_selected"
)
CATALOG_UNIT_MOVE_COMPLETED_MORTAL_WOUNDS_TARGET_SELECTED_EVENT = (
    "catalog_unit_move_completed_mortal_wounds_target_selected"
)
SELECT_CATALOG_NAMED_WEAPON_ABILITY_CHOICE_SUBMISSION_KIND = (
    "select_catalog_named_weapon_ability_choice"
)
SELECT_CATALOG_POST_SHOOT_HIT_TARGET_STATUS_DECISION_TYPE = (
    "select_catalog_post_shoot_hit_target_status"
)
SELECT_CATALOG_POST_SHOOT_HIT_TARGET_STATUS_SUBMISSION_KIND = (
    "select_catalog_post_shoot_hit_target_status"
)
SELECT_CATALOG_UNIT_MOVE_COMPLETED_MORTAL_WOUNDS_TARGET_DECISION_TYPE = (
    "select_catalog_unit_move_completed_mortal_wounds_target"
)
SELECT_CATALOG_UNIT_MOVE_COMPLETED_MORTAL_WOUNDS_TARGET_SUBMISSION_KIND = (
    "select_catalog_unit_move_completed_mortal_wounds_target"
)
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
        "battle_shock": CATALOG_IR_BATTLE_SHOCK_REROLL_CONSUMER_ID,
        "battle_shock_roll": CATALOG_IR_BATTLE_SHOCK_REROLL_CONSUMER_ID,
        "battle_shock_test": CATALOG_IR_BATTLE_SHOCK_REROLL_CONSUMER_ID,
        "hit": CATALOG_IR_HIT_ROLL_REROLL_CONSUMER_ID,
        "hit_roll": CATALOG_IR_HIT_ROLL_REROLL_CONSUMER_ID,
        "attack_sequence_hit": CATALOG_IR_HIT_ROLL_REROLL_CONSUMER_ID,
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
        "can_fallback_and_shoot": CATALOG_IR_CAN_FALLBACK_AND_SHOOT_CONSUMER_ID,
        "can_fall_back_and_shoot": CATALOG_IR_CAN_FALLBACK_AND_SHOOT_CONSUMER_ID,
        "can_advance_and_shoot_and_charge": (
            CATALOG_IR_CAN_ADVANCE_AND_SHOOT_AND_CHARGE_CONSUMER_ID
        ),
        "can_be_placed_in_reserves": CATALOG_IR_CAN_BE_PLACED_IN_RESERVES_CONSUMER_ID,
        "turn_end_reserves": CATALOG_IR_CAN_BE_PLACED_IN_RESERVES_CONSUMER_ID,
        "stealth": _datasheet.CATALOG_IR_GRANTED_STEALTH_CONSUMER_ID,
    }
)
_CATALOG_IR_FALL_BACK_ELIGIBILITY_GRANT_CONSUMER_IDS: Mapping[str, str] = MappingProxyType(
    {
        "can_fallback_and_charge": CATALOG_IR_CAN_FALLBACK_AND_CHARGE_CONSUMER_ID,
        "can_fall_back_and_charge": CATALOG_IR_CAN_FALLBACK_AND_CHARGE_CONSUMER_ID,
        "can_fallback_and_shoot": CATALOG_IR_CAN_FALLBACK_AND_SHOOT_CONSUMER_ID,
        "can_fall_back_and_shoot": CATALOG_IR_CAN_FALLBACK_AND_SHOOT_CONSUMER_ID,
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
class CatalogFallBackEligibilityRuntime:
    ability_indexes_by_player_id: Mapping[str, AbilityCatalogIndex]
    armies: tuple[ArmyDefinition, ...]

    def __post_init__(self) -> None:
        indexes = _validate_ability_index_mapping(self.ability_indexes_by_player_id)
        armies = _validate_armies(self.armies)
        missing_ids = {army.player_id for army in armies} - set(indexes)
        if missing_ids:
            raise GameLifecycleError("Catalog Fall Back eligibility missing player ability index.")
        object.__setattr__(self, "ability_indexes_by_player_id", MappingProxyType(dict(indexes)))
        object.__setattr__(self, "armies", armies)

    def bindings(self) -> tuple[FallBackEligibilityHookBinding, ...]:
        bindings: list[FallBackEligibilityHookBinding] = []
        if _has_fall_back_eligibility_records(
            self.ability_indexes_by_player_id,
            ability="can_fall_back_and_charge",
        ):
            bindings.append(
                FallBackEligibilityHookBinding(
                    hook_id=CATALOG_IR_CAN_FALLBACK_AND_CHARGE_CONSUMER_ID,
                    source_id=CATALOG_IR_CAN_FALLBACK_AND_CHARGE_CONSUMER_ID,
                    handler=self.fall_back_and_charge_handler,
                )
            )
        if _has_fall_back_eligibility_records(
            self.ability_indexes_by_player_id,
            ability="can_fall_back_and_shoot",
        ):
            bindings.append(
                FallBackEligibilityHookBinding(
                    hook_id=CATALOG_IR_CAN_FALLBACK_AND_SHOOT_CONSUMER_ID,
                    source_id=CATALOG_IR_CAN_FALLBACK_AND_SHOOT_CONSUMER_ID,
                    handler=self.fall_back_and_shoot_handler,
                )
            )
        return tuple(bindings)

    def fall_back_and_charge_handler(
        self,
        context: FallBackEligibilityContext,
    ) -> FallBackEligibilityGrant | None:
        return self._grant_for(
            context=context,
            ability="can_fall_back_and_charge",
            hook_id=CATALOG_IR_CAN_FALLBACK_AND_CHARGE_CONSUMER_ID,
            can_shoot=False,
            can_declare_charge=True,
        )

    def fall_back_and_shoot_handler(
        self,
        context: FallBackEligibilityContext,
    ) -> FallBackEligibilityGrant | None:
        return self._grant_for(
            context=context,
            ability="can_fall_back_and_shoot",
            hook_id=CATALOG_IR_CAN_FALLBACK_AND_SHOOT_CONSUMER_ID,
            can_shoot=True,
            can_declare_charge=False,
        )

    def _grant_for(
        self,
        *,
        context: FallBackEligibilityContext,
        ability: str,
        hook_id: str,
        can_shoot: bool,
        can_declare_charge: bool,
    ) -> FallBackEligibilityGrant | None:
        if type(context) is not FallBackEligibilityContext:
            raise GameLifecycleError("Catalog Fall Back eligibility requires context.")
        matching_records = _matching_fall_back_eligibility_records(
            ability_indexes_by_player_id=self.ability_indexes_by_player_id,
            armies=self.armies,
            context=context,
            ability=ability,
        )
        if not matching_records:
            return None
        return FallBackEligibilityGrant(
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
class CatalogNamedWeaponAbilityChoiceOption:
    option_id: str
    selection_option_id: str
    selection_option_index: int
    keyword: WeaponKeyword
    weapon_ability_value: int | str | None
    ability: AbilityDescriptor | None
    effect_index: int

    def __post_init__(self) -> None:
        object.__setattr__(self, "option_id", _validate_identifier("option_id", self.option_id))
        object.__setattr__(
            self,
            "selection_option_id",
            _validate_identifier("selection_option_id", self.selection_option_id),
        )
        object.__setattr__(
            self,
            "selection_option_index",
            _validate_positive_int("selection_option_index", self.selection_option_index),
        )
        object.__setattr__(self, "keyword", _weapon_keyword_from_value(self.keyword))
        if self.weapon_ability_value is not None:
            _validate_weapon_ability_choice_value(self.weapon_ability_value)
        if self.ability is not None and type(self.ability) is not AbilityDescriptor:
            raise GameLifecycleError(
                "Catalog named weapon ability choice ability must be a descriptor."
            )
        if type(self.effect_index) is not int or self.effect_index < 0:
            raise GameLifecycleError(
                "Catalog named weapon ability choice effect_index must be non-negative."
            )

    @property
    def label(self) -> str:
        if self.weapon_ability_value is None:
            return self.keyword.value
        return f"{self.keyword.value} {self.weapon_ability_value}"


@dataclass(frozen=True, slots=True)
class CatalogNamedWeaponAbilityChoiceGroup:
    record: AbilityCatalogRecord
    unit: UnitInstance
    clause: RuleClause
    selection_group_id: str
    target_scope: str
    weapon_names: tuple[str, ...]
    target_model_instance_ids: tuple[str, ...]
    options: tuple[CatalogNamedWeaponAbilityChoiceOption, ...]

    def __post_init__(self) -> None:
        if type(self.record) is not AbilityCatalogRecord:
            raise GameLifecycleError(
                "Catalog named weapon ability choice requires an ability record."
            )
        _validate_unit(self.unit)
        if type(self.clause) is not RuleClause:
            raise GameLifecycleError("Catalog named weapon ability choice requires a rule clause.")
        object.__setattr__(
            self,
            "selection_group_id",
            _validate_identifier("selection_group_id", self.selection_group_id),
        )
        object.__setattr__(
            self,
            "target_scope",
            _validate_named_weapon_choice_target_scope(self.target_scope),
        )
        object.__setattr__(
            self,
            "weapon_names",
            _validate_named_weapon_names(self.weapon_names),
        )
        object.__setattr__(
            self,
            "target_model_instance_ids",
            _validate_current_model_instance_ids(self.target_model_instance_ids),
        )
        if type(self.options) is not tuple or not self.options:
            raise GameLifecycleError("Catalog named weapon ability choice requires finite options.")
        option_values = tuple(
            _validate_named_weapon_choice_option(option) for option in self.options
        )
        if len({option.option_id for option in option_values}) != len(option_values):
            raise GameLifecycleError(
                "Catalog named weapon ability choice options must not duplicate IDs."
            )
        group_ids = {option.selection_option_id for option in option_values}
        if len(group_ids) != len(option_values):
            raise GameLifecycleError(
                "Catalog named weapon ability choice selection options must be unique."
            )
        object.__setattr__(
            self,
            "options",
            tuple(sorted(option_values, key=lambda option: option.option_id)),
        )

    @property
    def sort_key(self) -> tuple[str, str, str, str]:
        return (
            self.unit.unit_instance_id,
            self.record.record_id,
            self.clause.clause_id,
            self.selection_group_id,
        )


@dataclass(frozen=True, slots=True)
class CatalogPostShootHitTargetStatusOption:
    option_id: str
    target_unit_instance_id: str

    def __post_init__(self) -> None:
        object.__setattr__(self, "option_id", _validate_identifier("option_id", self.option_id))
        object.__setattr__(
            self,
            "target_unit_instance_id",
            _validate_identifier("target_unit_instance_id", self.target_unit_instance_id),
        )


@dataclass(frozen=True, slots=True)
class CatalogPostShootHitTargetStatusGroup:
    record: AbilityCatalogRecord
    unit: UnitInstance
    clause: RuleClause
    effect_index: int
    status: str
    status_label: str
    target_scope: str
    source_model_instance_id: str | None
    attack_sequence: AttackSequence
    attack_sequence_completed_event_id: str
    options: tuple[CatalogPostShootHitTargetStatusOption, ...]

    def __post_init__(self) -> None:
        if type(self.record) is not AbilityCatalogRecord:
            raise GameLifecycleError("Catalog post-shoot status requires an ability record.")
        _validate_unit(self.unit)
        if type(self.clause) is not RuleClause:
            raise GameLifecycleError("Catalog post-shoot status requires a rule clause.")
        if type(self.effect_index) is not int or self.effect_index < 0:
            raise GameLifecycleError("Catalog post-shoot status effect_index must be non-negative.")
        object.__setattr__(self, "status", _validate_identifier("status", self.status))
        object.__setattr__(
            self,
            "status_label",
            _validate_non_empty_text("status_label", self.status_label),
        )
        object.__setattr__(
            self,
            "target_scope",
            _validate_identifier("target_scope", self.target_scope),
        )
        if self.source_model_instance_id is not None:
            object.__setattr__(
                self,
                "source_model_instance_id",
                _validate_identifier("source_model_instance_id", self.source_model_instance_id),
            )
        if type(self.attack_sequence) is not AttackSequence:
            raise GameLifecycleError("Catalog post-shoot status requires an AttackSequence.")
        object.__setattr__(
            self,
            "attack_sequence_completed_event_id",
            _validate_identifier(
                "attack_sequence_completed_event_id",
                self.attack_sequence_completed_event_id,
            ),
        )
        if type(self.options) is not tuple or not self.options:
            raise GameLifecycleError("Catalog post-shoot status requires finite options.")
        option_values = tuple(
            _validate_post_shoot_hit_target_status_option(option) for option in self.options
        )
        if len({option.option_id for option in option_values}) != len(option_values):
            raise GameLifecycleError("Catalog post-shoot status options must not duplicate IDs.")
        object.__setattr__(
            self,
            "options",
            tuple(sorted(option_values, key=lambda option: option.option_id)),
        )

    @property
    def sort_key(self) -> tuple[str, str, str, str]:
        return (
            self.unit.unit_instance_id,
            self.record.record_id,
            self.clause.clause_id,
            "" if self.source_model_instance_id is None else self.source_model_instance_id,
        )


@dataclass(frozen=True, slots=True)
class CatalogUnitMoveCompletedMortalWoundsTargetOption:
    option_id: str
    target_unit_instance_id: str
    target_player_id: str

    def __post_init__(self) -> None:
        object.__setattr__(self, "option_id", _validate_identifier("option_id", self.option_id))
        object.__setattr__(
            self,
            "target_unit_instance_id",
            _validate_identifier("target_unit_instance_id", self.target_unit_instance_id),
        )
        object.__setattr__(
            self,
            "target_player_id",
            _validate_identifier("target_player_id", self.target_player_id),
        )


@dataclass(frozen=True, slots=True)
class CatalogUnitMoveCompletedMortalWoundsGroup:
    record: AbilityCatalogRecord
    source_unit: UnitInstance
    source_rules_unit_instance_id: str
    player_id: str
    clause: RuleClause
    effect_index: int
    roll_threshold: int
    mortal_wounds_expression: DiceExpression
    roll_model_instance_ids: tuple[str, ...]
    trigger_event_id: str
    movement_action: str
    options: tuple[CatalogUnitMoveCompletedMortalWoundsTargetOption, ...]

    def __post_init__(self) -> None:
        if type(self.record) is not AbilityCatalogRecord:
            raise GameLifecycleError("Catalog move-completed mortal wounds requires a record.")
        _validate_unit(self.source_unit)
        object.__setattr__(
            self,
            "source_rules_unit_instance_id",
            _validate_identifier(
                "source_rules_unit_instance_id",
                self.source_rules_unit_instance_id,
            ),
        )
        object.__setattr__(self, "player_id", _validate_identifier("player_id", self.player_id))
        if type(self.clause) is not RuleClause:
            raise GameLifecycleError("Catalog move-completed mortal wounds requires a clause.")
        if type(self.effect_index) is not int or self.effect_index < 0:
            raise GameLifecycleError(
                "Catalog move-completed mortal wounds effect_index must be non-negative."
            )
        if (
            type(self.roll_threshold) is not int
            or self.roll_threshold < 2
            or self.roll_threshold > 6
        ):
            raise GameLifecycleError(
                "Catalog move-completed mortal wounds roll_threshold must be 2-6."
            )
        if type(self.mortal_wounds_expression) is not DiceExpression:
            raise GameLifecycleError(
                "Catalog move-completed mortal wounds requires DiceExpression."
            )
        object.__setattr__(
            self,
            "roll_model_instance_ids",
            _validate_current_model_instance_ids(self.roll_model_instance_ids),
        )
        object.__setattr__(
            self,
            "trigger_event_id",
            _validate_identifier("trigger_event_id", self.trigger_event_id),
        )
        object.__setattr__(
            self,
            "movement_action",
            _validate_identifier("movement_action", self.movement_action),
        )
        if type(self.options) is not tuple or not self.options:
            raise GameLifecycleError(
                "Catalog move-completed mortal wounds requires target options."
            )
        options = tuple(
            _validate_unit_move_completed_mortal_wounds_target_option(option)
            for option in self.options
        )
        if len({option.option_id for option in options}) != len(options):
            raise GameLifecycleError(
                "Catalog move-completed mortal wounds options must not duplicate IDs."
            )
        object.__setattr__(
            self,
            "options",
            tuple(sorted(options, key=lambda option: option.option_id)),
        )

    @property
    def sort_key(self) -> tuple[str, str, str, int, str]:
        return (
            self.source_rules_unit_instance_id,
            self.record.record_id,
            self.clause.clause_id,
            self.effect_index,
            self.trigger_event_id,
        )


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
        if not (
            _has_catalog_weapon_keyword_grant_records(self.ability_indexes_by_player_id)
            or _has_catalog_named_weapon_ability_choice_records(self.ability_indexes_by_player_id)
        ):
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
        index, rules_unit = catalog_weapon_grant_source_index_and_rules_unit(
            ability_indexes_by_player_id=self.ability_indexes_by_player_id,
            armies=self.armies,
            context=context,
        )
        grants: list[CatalogWeaponKeywordGrant] = []
        for component in rules_unit.components:
            current_model_ids = _current_placed_alive_model_instance_ids_for_unit(
                state=context.state, unit=component.unit
            )
            if not current_model_ids:
                continue
            grants.extend(
                catalog_weapon_keyword_grants_for_unit(
                    ability_index=index,
                    unit=component.unit,
                    current_model_instance_ids=current_model_ids,
                )
            )
        profile = context.weapon_profile
        for grant in grants:
            if not tracked_target_weapon_grant_applies(context=context, grant=grant):
                continue
            if not _weapon_scope_matches_profile(
                weapon_scope=grant.weapon_scope,
                profile=profile,
            ):
                continue
            profile = profile_with_catalog_weapon_keyword_grant(profile=profile, grant=grant)
        for grant in _selected_catalog_named_weapon_ability_grants(context):
            profile = profile_with_catalog_weapon_keyword_grant(profile=profile, grant=grant)
        return profile


@dataclass(frozen=True, slots=True)
class CatalogNamedWeaponAbilityChoiceRuntime:
    ability_indexes_by_player_id: Mapping[str, AbilityCatalogIndex]
    armies: tuple[ArmyDefinition, ...]

    def __post_init__(self) -> None:
        indexes = _validate_ability_index_mapping(self.ability_indexes_by_player_id)
        armies = _validate_armies(self.armies)
        missing_ids = {army.player_id for army in armies} - set(indexes)
        if missing_ids:
            raise GameLifecycleError(
                "Catalog named weapon ability choices missing player ability index."
            )
        object.__setattr__(self, "ability_indexes_by_player_id", MappingProxyType(dict(indexes)))
        object.__setattr__(self, "armies", armies)

    def bindings(self) -> tuple[ShootingPhaseStartHookBinding, ...]:
        if not _has_catalog_named_weapon_ability_choice_records(self.ability_indexes_by_player_id):
            return ()
        return (
            ShootingPhaseStartHookBinding(
                hook_id=CATALOG_IR_NAMED_WEAPON_ABILITY_CHOICE_CONSUMER_ID,
                source_id=CATALOG_IR_NAMED_WEAPON_ABILITY_CHOICE_CONSUMER_ID,
                request_handler=self.request_handler,
                result_handler=self.result_handler,
            ),
        )

    def request_handler(self, context: ShootingPhaseStartRequestContext) -> DecisionRequest | None:
        if type(context) is not ShootingPhaseStartRequestContext:
            raise GameLifecycleError("Catalog named weapon ability choice requires context.")
        groups = _available_catalog_named_weapon_ability_choice_groups(
            ability_indexes_by_player_id=self.ability_indexes_by_player_id,
            armies=self.armies,
            context=context,
        )
        if not groups:
            return None
        group = groups[0]
        common_payload = _named_weapon_ability_choice_request_payload(
            state=context.state,
            group=group,
        )
        return DecisionRequest(
            request_id=context.state.next_decision_request_id(),
            decision_type=SELECT_FACTION_RULE_SHOOTING_PHASE_START_OPTION_DECISION_TYPE,
            actor_id=context.state.active_player_id,
            payload=validate_json_value(common_payload),
            options=tuple(
                DecisionOption(
                    option_id=option.option_id,
                    label=_named_weapon_ability_choice_option_label(
                        group=group,
                        option=option,
                    ),
                    payload=validate_json_value(
                        _named_weapon_ability_choice_option_payload(
                            state=context.state,
                            group=group,
                            option=option,
                        )
                    ),
                )
                for option in group.options
            ),
        )

    def result_handler(
        self,
        context: ShootingPhaseStartResultContext,
    ) -> bool | LifecycleStatus:
        if type(context) is not ShootingPhaseStartResultContext:
            raise GameLifecycleError("Catalog named weapon ability choice requires context.")
        request_payload = _payload_object(context.request.payload)
        if request_payload.get("hook_id") != CATALOG_IR_NAMED_WEAPON_ABILITY_CHOICE_CONSUMER_ID:
            return False
        result_payload = _payload_object(context.result.payload)
        if (
            result_payload.get("submission_kind")
            != SELECT_CATALOG_NAMED_WEAPON_ABILITY_CHOICE_SUBMISSION_KIND
        ):
            return _catalog_named_weapon_ability_choice_invalid_status(
                state=context.state,
                actor_id=context.result.actor_id,
                invalid_reason="catalog_named_weapon_ability_choice_submission_kind_drift",
            )
        groups = _available_catalog_named_weapon_ability_choice_groups(
            ability_indexes_by_player_id=self.ability_indexes_by_player_id,
            armies=self.armies,
            context=ShootingPhaseStartRequestContext(
                state=context.state,
                decisions=context.decisions,
                ruleset_descriptor=context.ruleset_descriptor,
                army_catalog=context.army_catalog,
                shooting_target_restriction_hooks=context.shooting_target_restriction_hooks,
            ),
        )
        if not groups:
            return _catalog_named_weapon_ability_choice_invalid_status(
                state=context.state,
                actor_id=context.result.actor_id,
                invalid_reason="catalog_named_weapon_ability_choice_unavailable",
            )
        group = groups[0]
        option_by_id = {option.option_id: option for option in group.options}
        option = option_by_id.get(context.result.selected_option_id)
        if option is None:
            return _catalog_named_weapon_ability_choice_invalid_status(
                state=context.state,
                actor_id=context.result.actor_id,
                invalid_reason="catalog_named_weapon_ability_choice_option_drift",
            )
        expected_payload = _named_weapon_ability_choice_option_payload(
            state=context.state,
            group=group,
            option=option,
        )
        if result_payload != expected_payload:
            return _catalog_named_weapon_ability_choice_invalid_status(
                state=context.state,
                actor_id=context.result.actor_id,
                invalid_reason="catalog_named_weapon_ability_choice_payload_drift",
            )
        effect = _named_weapon_ability_choice_persisting_effect(
            state=context.state,
            result_id=context.result.result_id,
            group=group,
            option=option,
        )
        context.state.record_persisting_effect(effect)
        context.decisions.event_log.append(
            CATALOG_NAMED_WEAPON_ABILITY_CHOICE_SELECTED_EVENT,
            validate_json_value(
                {
                    "game_id": context.state.game_id,
                    "battle_round": context.state.battle_round,
                    "phase": BattlePhase.SHOOTING.value,
                    "active_player_id": context.state.active_player_id,
                    "request_id": context.request.request_id,
                    "result_id": context.result.result_id,
                    "selected_option_id": context.result.selected_option_id,
                    "persisting_effect_id": effect.effect_id,
                    "catalog_record_id": group.record.record_id,
                    "source_rule_id": group.record.definition.source_id,
                    "unit_instance_id": group.unit.unit_instance_id,
                    "selection_group_id": group.selection_group_id,
                    "selected_weapon_ability": option.keyword.value,
                    "weapon_names": list(group.weapon_names),
                    "target_model_instance_ids": list(group.target_model_instance_ids),
                }
            ),
        )
        return True


@dataclass(frozen=True, slots=True)
class CatalogPostShootHitTargetStatusRuntime:
    ability_indexes_by_player_id: Mapping[str, AbilityCatalogIndex]
    armies: tuple[ArmyDefinition, ...]

    def __post_init__(self) -> None:
        indexes = _validate_ability_index_mapping(self.ability_indexes_by_player_id)
        armies = _validate_armies(self.armies)
        missing_ids = {army.player_id for army in armies} - set(indexes)
        if missing_ids:
            raise GameLifecycleError("Catalog post-shoot status missing player ability index.")
        object.__setattr__(self, "ability_indexes_by_player_id", MappingProxyType(dict(indexes)))
        object.__setattr__(self, "armies", armies)

    def bindings(self) -> tuple[AttackSequenceCompletedHookBinding, ...]:
        if not _has_catalog_post_shoot_hit_target_status_records(self.ability_indexes_by_player_id):
            return ()
        return (
            AttackSequenceCompletedHookBinding(
                hook_id=CATALOG_IR_POST_SHOOT_HIT_TARGET_STATUS_CONSUMER_ID,
                source_id=CATALOG_IR_POST_SHOOT_HIT_TARGET_STATUS_CONSUMER_ID,
                handler=self.request_handler,
            ),
        )

    def request_handler(self, context: AttackSequenceCompletedContext) -> LifecycleStatus | None:
        if type(context) is not AttackSequenceCompletedContext:
            raise GameLifecycleError("Catalog post-shoot status requires context.")
        groups = _available_catalog_post_shoot_hit_target_status_groups(
            ability_indexes_by_player_id=self.ability_indexes_by_player_id,
            armies=self.armies,
            context=context,
        )
        if not groups:
            return None
        resolved_group_keys = _resolved_post_shoot_hit_target_status_group_keys(context.decisions)
        unresolved_groups = tuple(
            group
            for group in groups
            if _post_shoot_hit_target_status_group_key(group) not in resolved_group_keys
        )
        if not unresolved_groups:
            return None
        group = unresolved_groups[0]
        common_payload = _post_shoot_hit_target_status_request_payload(
            state=context.state,
            group=group,
        )
        request = DecisionRequest(
            request_id=context.state.next_decision_request_id(),
            decision_type=SELECT_CATALOG_POST_SHOOT_HIT_TARGET_STATUS_DECISION_TYPE,
            actor_id=context.attack_sequence.attacker_player_id,
            payload=validate_json_value(common_payload),
            options=tuple(
                DecisionOption(
                    option_id=option.option_id,
                    label=_post_shoot_hit_target_status_option_label(
                        group=group,
                        option=option,
                    ),
                    payload=validate_json_value(
                        _post_shoot_hit_target_status_option_payload(
                            state=context.state,
                            group=group,
                            option=option,
                        )
                    ),
                )
                for option in group.options
            ),
        )
        context.decisions.request_decision(request)
        context.decisions.event_log.append(
            "catalog_post_shoot_hit_target_status_requested",
            validate_json_value(
                {
                    "game_id": context.state.game_id,
                    "battle_round": context.state.battle_round,
                    "phase": BattlePhase.SHOOTING.value,
                    "active_player_id": context.state.active_player_id,
                    "player_id": context.attack_sequence.attacker_player_id,
                    "hook_id": CATALOG_IR_POST_SHOOT_HIT_TARGET_STATUS_CONSUMER_ID,
                    "request_id": request.request_id,
                    "catalog_record_id": group.record.record_id,
                    "source_rule_id": group.record.definition.source_id,
                    "clause_id": group.clause.clause_id,
                    "status": group.status,
                    "source_model_instance_id": group.source_model_instance_id,
                    "attack_sequence_id": group.attack_sequence.sequence_id,
                    "attack_sequence_completed_event_id": (
                        group.attack_sequence_completed_event_id
                    ),
                    "available_target_unit_instance_ids": [
                        option.target_unit_instance_id for option in group.options
                    ],
                    "phase_body_status": "catalog_post_shoot_hit_target_status_pending",
                }
            ),
        )
        return LifecycleStatus.waiting_for_decision(
            stage=GameLifecycleStage.BATTLE,
            decision_request=request,
            payload=validate_json_value(
                {
                    "phase": BattlePhase.SHOOTING.value,
                    "battle_round": context.state.battle_round,
                    "active_player_id": context.state.active_player_id,
                    "player_id": context.attack_sequence.attacker_player_id,
                    "pending_request_id": request.request_id,
                    "phase_body_status": "catalog_post_shoot_hit_target_status_pending",
                }
            ),
        )


@dataclass(frozen=True, slots=True)
class CatalogUnitMoveCompletedMortalWoundsRuntime:
    ability_indexes_by_player_id: Mapping[str, AbilityCatalogIndex]
    armies: tuple[ArmyDefinition, ...]

    def __post_init__(self) -> None:
        indexes = _validate_ability_index_mapping(self.ability_indexes_by_player_id)
        armies = _validate_armies(self.armies)
        missing_ids = {army.player_id for army in armies} - set(indexes)
        if missing_ids:
            raise GameLifecycleError(
                "Catalog move-completed mortal wounds missing player ability index."
            )
        object.__setattr__(self, "ability_indexes_by_player_id", MappingProxyType(dict(indexes)))
        object.__setattr__(self, "armies", armies)

    def bindings(self) -> tuple[UnitMoveCompletedMortalWoundHookBinding, ...]:
        if not _has_catalog_unit_move_completed_mortal_wounds_records(
            self.ability_indexes_by_player_id
        ):
            return ()
        return (
            UnitMoveCompletedMortalWoundHookBinding(
                hook_id=CATALOG_IR_UNIT_MOVE_COMPLETED_MORTAL_WOUNDS_CONSUMER_ID,
                source_id=CATALOG_IR_UNIT_MOVE_COMPLETED_MORTAL_WOUNDS_CONSUMER_ID,
                handler=self.effect_handler,
                request_handler=self.request_handler,
            ),
        )

    def request_handler(self, context: UnitMoveCompletedContext) -> LifecycleStatus | None:
        if type(context) is not UnitMoveCompletedContext:
            raise GameLifecycleError("Catalog move-completed mortal wounds requires context.")
        decisions = _unit_move_completed_decisions(context)
        groups = _available_catalog_unit_move_completed_mortal_wounds_groups(
            ability_indexes_by_player_id=self.ability_indexes_by_player_id,
            armies=self.armies,
            context=context,
        )
        if not groups:
            return None
        selected_group_keys = _selected_unit_move_completed_mortal_wounds_group_keys(decisions)
        unresolved_groups = tuple(
            group
            for group in groups
            if _unit_move_completed_mortal_wounds_group_key(group) not in selected_group_keys
        )
        if not unresolved_groups:
            return None
        group = unresolved_groups[0]
        request = DecisionRequest(
            request_id=context.state.next_decision_request_id(),
            decision_type=SELECT_CATALOG_UNIT_MOVE_COMPLETED_MORTAL_WOUNDS_TARGET_DECISION_TYPE,
            actor_id=context.triggering_player_id,
            payload=validate_json_value(
                _unit_move_completed_mortal_wounds_target_request_payload(
                    state=context.state,
                    group=group,
                )
            ),
            options=tuple(
                DecisionOption(
                    option_id=option.option_id,
                    label=_unit_move_completed_mortal_wounds_target_option_label(option),
                    payload=validate_json_value(
                        _unit_move_completed_mortal_wounds_target_option_payload(
                            state=context.state,
                            group=group,
                            option=option,
                        )
                    ),
                )
                for option in group.options
            ),
        )
        decisions.request_decision(request)
        decisions.event_log.append(
            "catalog_unit_move_completed_mortal_wounds_target_requested",
            validate_json_value(
                {
                    "game_id": context.state.game_id,
                    "battle_round": context.state.battle_round,
                    "phase": BattlePhase.CHARGE.value,
                    "active_player_id": context.state.active_player_id,
                    "player_id": context.triggering_player_id,
                    "hook_id": CATALOG_IR_UNIT_MOVE_COMPLETED_MORTAL_WOUNDS_CONSUMER_ID,
                    "request_id": request.request_id,
                    "catalog_record_id": group.record.record_id,
                    "source_rule_id": group.record.definition.source_id,
                    "source_rules_unit_instance_id": group.source_rules_unit_instance_id,
                    "source_unit_instance_id": group.source_unit.unit_instance_id,
                    "clause_id": group.clause.clause_id,
                    "effect_index": group.effect_index,
                    "trigger_event_id": group.trigger_event_id,
                    "movement_action": group.movement_action,
                    "available_target_unit_instance_ids": [
                        option.target_unit_instance_id for option in group.options
                    ],
                    "phase_body_status": (
                        "catalog_unit_move_completed_mortal_wounds_target_pending"
                    ),
                }
            ),
        )
        return LifecycleStatus.waiting_for_decision(
            stage=GameLifecycleStage.BATTLE,
            decision_request=request,
            payload=validate_json_value(
                {
                    "phase": BattlePhase.CHARGE.value,
                    "battle_round": context.state.battle_round,
                    "active_player_id": context.state.active_player_id,
                    "player_id": context.triggering_player_id,
                    "pending_request_id": request.request_id,
                    "phase_body_status": (
                        "catalog_unit_move_completed_mortal_wounds_target_pending"
                    ),
                }
            ),
        )

    def effect_handler(
        self,
        context: UnitMoveCompletedContext,
    ) -> tuple[UnitMoveCompletedMortalWoundEffect, ...]:
        if type(context) is not UnitMoveCompletedContext:
            raise GameLifecycleError("Catalog move-completed mortal wounds requires context.")
        decisions = _unit_move_completed_decisions(context)
        selected_targets = _selected_unit_move_completed_mortal_wounds_targets(decisions)
        if not selected_targets:
            return ()
        effects: list[UnitMoveCompletedMortalWoundEffect] = []
        for group in _available_catalog_unit_move_completed_mortal_wounds_groups(
            ability_indexes_by_player_id=self.ability_indexes_by_player_id,
            armies=self.armies,
            context=context,
        ):
            selected = selected_targets.get(_unit_move_completed_mortal_wounds_group_key(group))
            if selected is None:
                continue
            option_by_target = {option.target_unit_instance_id: option for option in group.options}
            option = option_by_target.get(selected.target_unit_instance_id)
            if option is None:
                raise GameLifecycleError(
                    "Catalog move-completed mortal wounds selected target drifted."
                )
            for roll_model_id in group.roll_model_instance_ids:
                effects.append(
                    UnitMoveCompletedMortalWoundEffect(
                        hook_id=CATALOG_IR_UNIT_MOVE_COMPLETED_MORTAL_WOUNDS_CONSUMER_ID,
                        source_id=CATALOG_IR_UNIT_MOVE_COMPLETED_MORTAL_WOUNDS_CONSUMER_ID,
                        source_rule_id=group.record.definition.source_id,
                        target_unit_instance_id=option.target_unit_instance_id,
                        target_player_id=option.target_player_id,
                        rolling_player_id=context.triggering_player_id,
                        trigger_event_id=context.trigger_event_id,
                        roll_threshold=group.roll_threshold,
                        mortal_wounds_expression=group.mortal_wounds_expression,
                        replay_payload=_unit_move_completed_mortal_wounds_effect_payload(
                            group=group,
                            option=option,
                            roll_model_instance_id=roll_model_id,
                        ),
                    )
                )
        return tuple(effects)


def catalog_advance_eligibility_hook_bindings(
    *,
    ability_indexes_by_player_id: Mapping[str, AbilityCatalogIndex],
    armies: tuple[ArmyDefinition, ...],
) -> tuple[AdvanceEligibilityHookBinding, ...]:
    return CatalogAdvanceEligibilityRuntime(
        ability_indexes_by_player_id=ability_indexes_by_player_id,
        armies=armies,
    ).bindings()


def catalog_fall_back_eligibility_hook_bindings(
    *,
    ability_indexes_by_player_id: Mapping[str, AbilityCatalogIndex],
    armies: tuple[ArmyDefinition, ...],
) -> tuple[FallBackEligibilityHookBinding, ...]:
    return CatalogFallBackEligibilityRuntime(
        ability_indexes_by_player_id=ability_indexes_by_player_id,
        armies=armies,
    ).bindings()


def catalog_named_weapon_ability_choice_hook_bindings(
    *,
    ability_indexes_by_player_id: Mapping[str, AbilityCatalogIndex],
    armies: tuple[ArmyDefinition, ...],
) -> tuple[ShootingPhaseStartHookBinding, ...]:
    return CatalogNamedWeaponAbilityChoiceRuntime(
        ability_indexes_by_player_id=ability_indexes_by_player_id,
        armies=armies,
    ).bindings()


def catalog_post_shoot_hit_target_status_hook_bindings(
    *,
    ability_indexes_by_player_id: Mapping[str, AbilityCatalogIndex],
    armies: tuple[ArmyDefinition, ...],
) -> tuple[AttackSequenceCompletedHookBinding, ...]:
    return CatalogPostShootHitTargetStatusRuntime(
        ability_indexes_by_player_id=ability_indexes_by_player_id,
        armies=armies,
    ).bindings()


def catalog_unit_move_completed_mortal_wound_hook_bindings(
    *,
    ability_indexes_by_player_id: Mapping[str, AbilityCatalogIndex],
    armies: tuple[ArmyDefinition, ...],
) -> tuple[UnitMoveCompletedMortalWoundHookBinding, ...]:
    return CatalogUnitMoveCompletedMortalWoundsRuntime(
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
        *_datasheet.registered_consumer_ids(),
        *_CATALOG_IR_ROLL_MODIFIER_CONSUMER_IDS.values(),
        *_CATALOG_IR_ROLL_REROLL_CONSUMER_IDS.values(),
        *_CATALOG_IR_RULE_EXCEPTION_CONSUMER_IDS.values(),
        CATALOG_IR_DESTROYED_UNIT_RESTORE_LOST_WOUNDS_CONSUMER_ID,
        CATALOG_IR_TRACKED_TARGET_SELECTION_CONSUMER_ID,
        CATALOG_IR_TRACKED_TARGET_REROLL_CONSUMER_ID,
        CATALOG_IR_TRACKED_TARGET_DESTROYED_RESELECT_CONSUMER_ID,
        CATALOG_IR_FIRST_DEATH_RETURN_CONSUMER_ID,
        CATALOG_IR_FIRST_DEATH_RETURN_PHASE_END_CONSUMER_ID,
        CATALOG_IR_FORCE_DESPERATE_ESCAPE_CONSUMER_ID,
        CATALOG_IR_FEEL_NO_PAIN_SOURCE_CONSUMER_ID,
        *_contextual.registered_hook_ids(),
        CATALOG_IR_WEAPON_KEYWORD_GRANT_CONSUMER_ID,
        CATALOG_IR_NAMED_WEAPON_ABILITY_CHOICE_CONSUMER_ID,
        CATALOG_IR_MINIMUM_UNMODIFIED_HIT_SUCCESS_CONSUMER_ID,
        CATALOG_IR_POST_SHOOT_HIT_TARGET_STATUS_CONSUMER_ID,
        CATALOG_IR_SELECTED_TARGET_EFFECT_CONSUMER_ID,
        CATALOG_IR_ONCE_PER_BATTLE_ABILITY_CONSUMER_ID,
        CATALOG_IR_POST_SHOOT_HIT_TARGET_EFFECT_CONSUMER_ID,
        CATALOG_IR_SHOOTING_START_SELECTED_TARGET_EFFECT_CONSUMER_ID,
        CATALOG_IR_PREBATTLE_REDEPLOY_PERMISSION_CONSUMER_ID,
        CATALOG_IR_UNIT_MOVE_COMPLETED_MORTAL_WOUNDS_CONSUMER_ID,
        *_ucbs.registered_hook_ids(),
        CATALOG_IR_MOVEMENT_TRANSIT_PERMISSION_CONSUMER_ID,
        CATALOG_IR_SETUP_REACTIVE_SHOOT_CHARGE_CONSUMER_ID,
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
                    unit=unit,
                    clause=clause,
                    effect_index=effect_index,
                    effect=effect,
                )
                if grant is None:
                    continue
                grants.append(grant)
    return tuple(sorted(grants, key=lambda grant: grant.source_id))


def _available_catalog_named_weapon_ability_choice_groups(
    *,
    ability_indexes_by_player_id: Mapping[str, AbilityCatalogIndex],
    armies: tuple[ArmyDefinition, ...],
    context: ShootingPhaseStartRequestContext,
) -> tuple[CatalogNamedWeaponAbilityChoiceGroup, ...]:
    if type(context) is not ShootingPhaseStartRequestContext:
        raise GameLifecycleError("Catalog named weapon ability choices require context.")
    active_player_id = _validate_identifier("active_player_id", context.state.active_player_id)
    army = _army_for_player(armies, player_id=active_player_id)
    index = ability_indexes_by_player_id.get(active_player_id)
    if index is None:
        raise GameLifecycleError("Catalog named weapon ability choice index is missing player.")
    groups: list[CatalogNamedWeaponAbilityChoiceGroup] = []
    for unit in army.units:
        current_model_ids = _current_placed_alive_model_instance_ids_for_unit(
            state=context.state,
            unit=unit,
        )
        if not current_model_ids:
            continue
        for record in _unit_scoped_generic_records_for_all_timings(
            ability_index=index,
            unit=unit,
            current_model_instance_ids=current_model_ids,
        ):
            for clause in _clauses_from_record(record):
                group = _catalog_named_weapon_ability_choice_group_from_clause(
                    state=context.state,
                    army_catalog=context.army_catalog,
                    record=record,
                    unit=unit,
                    current_model_instance_ids=current_model_ids,
                    clause=clause,
                )
                if group is not None:
                    groups.append(group)
    return tuple(sorted(groups, key=lambda group: group.sort_key))


def _catalog_named_weapon_ability_choice_group_from_clause(
    *,
    state: GameState,
    army_catalog: ArmyCatalog,
    record: AbilityCatalogRecord,
    unit: UnitInstance,
    current_model_instance_ids: tuple[str, ...],
    clause: RuleClause,
) -> CatalogNamedWeaponAbilityChoiceGroup | None:
    _validate_game_state(state)
    if type(army_catalog) is not ArmyCatalog:
        raise GameLifecycleError("Catalog named weapon ability choice requires an ArmyCatalog.")
    if type(record) is not AbilityCatalogRecord:
        raise GameLifecycleError("Catalog named weapon ability choice requires an ability record.")
    _validate_unit(unit)
    current_ids = _validate_current_model_instance_ids(current_model_instance_ids)
    if type(clause) is not RuleClause:
        raise GameLifecycleError("Catalog named weapon ability choice requires a rule clause.")
    if not _clause_is_named_weapon_ability_choice(clause):
        return None
    options: list[CatalogNamedWeaponAbilityChoiceOption] = []
    selection_group_id: str | None = None
    target_scope: str | None = None
    weapon_names: tuple[str, ...] | None = None
    for effect_index, effect in enumerate(clause.effects):
        option = _named_weapon_ability_choice_option_from_effect(
            record=record,
            unit=unit,
            clause=clause,
            effect_index=effect_index,
            effect=effect,
        )
        if option is None:
            return None
        parameters = parameter_payload(effect.parameters)
        effect_group_id = _required_string_parameter(parameters, key="selection_group_id")
        effect_target_scope = _validate_named_weapon_choice_target_scope(
            _required_string_parameter(parameters, key="target_scope")
        )
        effect_weapon_names = _weapon_names_from_parameters(parameters)
        if selection_group_id is None:
            selection_group_id = effect_group_id
            target_scope = effect_target_scope
            weapon_names = effect_weapon_names
        elif (
            selection_group_id != effect_group_id
            or target_scope != effect_target_scope
            or weapon_names != effect_weapon_names
        ):
            raise GameLifecycleError(
                "Catalog named weapon ability choice option group shape drift."
            )
        options.append(option)
    if selection_group_id is None or target_scope is None or weapon_names is None:
        return None
    target_model_ids = _named_weapon_ability_choice_target_model_ids(
        army_catalog=army_catalog,
        record=record,
        unit=unit,
        current_model_instance_ids=current_ids,
        target_scope=target_scope,
        weapon_names=weapon_names,
    )
    if not target_model_ids:
        return None
    if _catalog_named_weapon_ability_choice_group_resolved(
        state=state,
        unit_instance_id=unit.unit_instance_id,
        catalog_record_id=record.record_id,
        clause_id=clause.clause_id,
        selection_group_id=selection_group_id,
    ):
        return None
    return CatalogNamedWeaponAbilityChoiceGroup(
        record=record,
        unit=unit,
        clause=clause,
        selection_group_id=selection_group_id,
        target_scope=target_scope,
        weapon_names=weapon_names,
        target_model_instance_ids=target_model_ids,
        options=tuple(options),
    )


def _available_catalog_post_shoot_hit_target_status_groups(
    *,
    ability_indexes_by_player_id: Mapping[str, AbilityCatalogIndex],
    armies: tuple[ArmyDefinition, ...],
    context: AttackSequenceCompletedContext,
) -> tuple[CatalogPostShootHitTargetStatusGroup, ...]:
    if type(context) is not AttackSequenceCompletedContext:
        raise GameLifecycleError("Catalog post-shoot status requires context.")
    if context.source_phase is not BattlePhase.SHOOTING:
        return ()
    player_id = _validate_identifier("player_id", context.attack_sequence.attacker_player_id)
    army = _army_for_player(armies, player_id=player_id)
    unit = _unit_in_army_by_id(
        army,
        unit_instance_id=context.attack_sequence.attacking_unit_instance_id,
    )
    index = ability_indexes_by_player_id.get(player_id)
    if index is None:
        raise GameLifecycleError("Catalog post-shoot status index is missing player.")
    current_model_ids = _current_placed_alive_model_instance_ids_for_unit(
        state=context.state,
        unit=unit,
    )
    if not current_model_ids:
        return ()
    groups: list[CatalogPostShootHitTargetStatusGroup] = []
    for record in _unit_scoped_generic_records(
        ability_index=index,
        unit=unit,
        current_model_instance_ids=current_model_ids,
        trigger_kind=TimingTriggerKind.JUST_AFTER_FRIENDLY_UNIT_HAS_SHOT,
    ):
        for clause in _clauses_from_record(record):
            groups.extend(
                _catalog_post_shoot_hit_target_status_groups_from_clause(
                    context=context,
                    record=record,
                    unit=unit,
                    current_model_instance_ids=current_model_ids,
                    clause=clause,
                )
            )
    return tuple(sorted(groups, key=lambda group: group.sort_key))


def _available_catalog_unit_move_completed_mortal_wounds_groups(
    *,
    ability_indexes_by_player_id: Mapping[str, AbilityCatalogIndex],
    armies: tuple[ArmyDefinition, ...],
    context: UnitMoveCompletedContext,
) -> tuple[CatalogUnitMoveCompletedMortalWoundsGroup, ...]:
    if type(context) is not UnitMoveCompletedContext:
        raise GameLifecycleError("Catalog move-completed mortal wounds requires context.")
    if (
        context.completed_phase is not BattlePhase.CHARGE
        or context.movement_action != "charge_move"
    ):
        return ()
    source_rules_unit = rules_unit_view_by_id(
        state=context.state,
        unit_instance_id=context.triggering_unit_instance_id,
    )
    if source_rules_unit.owner_player_id != context.triggering_player_id:
        raise GameLifecycleError("Catalog move-completed mortal wounds source owner drifted.")
    index = ability_indexes_by_player_id.get(context.triggering_player_id)
    if index is None:
        raise GameLifecycleError("Catalog move-completed mortal wounds index is missing player.")
    source_roll_model_ids = _placed_alive_model_instance_ids_for_rules_unit(
        state=context.state,
        rules_unit_instance_id=source_rules_unit.unit_instance_id,
    )
    if not source_roll_model_ids:
        return ()
    target_candidates = _unit_move_completed_mortal_wounds_target_candidates(
        state=context.state,
        ruleset_descriptor=context.ruleset_descriptor,
        source_rules_unit_instance_id=source_rules_unit.unit_instance_id,
    )
    if not target_candidates:
        return ()
    source_roll_model_id_set = frozenset(source_roll_model_ids)
    groups: list[CatalogUnitMoveCompletedMortalWoundsGroup] = []
    for component in source_rules_unit.components:
        component_model_ids = tuple(
            sorted(
                model.model_instance_id
                for model in component.unit.own_models
                if model.is_alive and model.model_instance_id in source_roll_model_id_set
            )
        )
        if not component_model_ids:
            continue
        for record in _unit_scoped_generic_records(
            ability_index=index,
            unit=component.unit,
            current_model_instance_ids=component_model_ids,
            trigger_kind=TimingTriggerKind.AFTER_UNIT_ENDS_CHARGE_MOVE,
        ):
            for clause in _clauses_from_record(record):
                group = _catalog_unit_move_completed_mortal_wounds_group_from_clause(
                    context=context,
                    record=record,
                    source_unit=component.unit,
                    source_rules_unit_instance_id=source_rules_unit.unit_instance_id,
                    roll_model_instance_ids=source_roll_model_ids,
                    target_candidates=target_candidates,
                    clause=clause,
                )
                if group is not None:
                    groups.append(group)
    return tuple(sorted(groups, key=lambda group: group.sort_key))


def _catalog_unit_move_completed_mortal_wounds_group_from_clause(
    *,
    context: UnitMoveCompletedContext,
    record: AbilityCatalogRecord,
    source_unit: UnitInstance,
    source_rules_unit_instance_id: str,
    roll_model_instance_ids: tuple[str, ...],
    target_candidates: tuple[tuple[str, str], ...],
    clause: RuleClause,
) -> CatalogUnitMoveCompletedMortalWoundsGroup | None:
    if type(context) is not UnitMoveCompletedContext:
        raise GameLifecycleError("Catalog move-completed mortal wounds requires context.")
    if type(record) is not AbilityCatalogRecord:
        raise GameLifecycleError("Catalog move-completed mortal wounds requires a record.")
    _validate_unit(source_unit)
    source_rules_unit_id = _validate_identifier(
        "source_rules_unit_instance_id",
        source_rules_unit_instance_id,
    )
    roll_model_ids = _validate_current_model_instance_ids(roll_model_instance_ids)
    if type(target_candidates) is not tuple:
        raise GameLifecycleError("Catalog move-completed mortal wounds targets must be a tuple.")
    if type(clause) is not RuleClause:
        raise GameLifecycleError("Catalog move-completed mortal wounds requires a clause.")
    if not _clause_is_supported_unit_move_completed_mortal_wounds(clause):
        return None
    supported_effects = tuple(
        (effect_index, effect)
        for effect_index, effect in enumerate(clause.effects)
        if _effect_is_supported_unit_move_completed_mortal_wounds(effect)
    )
    if len(supported_effects) != 1:
        raise GameLifecycleError(
            "Catalog move-completed mortal wounds requires one supported effect."
        )
    effect_index, effect = supported_effects[0]
    parameters = parameter_payload(effect.parameters)
    return CatalogUnitMoveCompletedMortalWoundsGroup(
        record=record,
        source_unit=source_unit,
        source_rules_unit_instance_id=source_rules_unit_id,
        player_id=context.triggering_player_id,
        clause=clause,
        effect_index=effect_index,
        roll_threshold=_int_parameter(parameters, key="success_threshold"),
        mortal_wounds_expression=_catalog_mortal_wounds_dice_expression(
            _string_parameter(parameters, key="mortal_wounds_expression")
        ),
        roll_model_instance_ids=roll_model_ids,
        trigger_event_id=context.trigger_event_id,
        movement_action=context.movement_action,
        options=tuple(
            CatalogUnitMoveCompletedMortalWoundsTargetOption(
                option_id=_unit_move_completed_mortal_wounds_target_option_id(
                    record=record,
                    source_rules_unit_instance_id=source_rules_unit_id,
                    clause=clause,
                    effect_index=effect_index,
                    target_unit_instance_id=target_unit_id,
                ),
                target_unit_instance_id=target_unit_id,
                target_player_id=target_player_id,
            )
            for target_unit_id, target_player_id in target_candidates
        ),
    )


def _catalog_post_shoot_hit_target_status_groups_from_clause(
    *,
    context: AttackSequenceCompletedContext,
    record: AbilityCatalogRecord,
    unit: UnitInstance,
    current_model_instance_ids: tuple[str, ...],
    clause: RuleClause,
) -> tuple[CatalogPostShootHitTargetStatusGroup, ...]:
    _validate_game_state(context.state)
    if type(record) is not AbilityCatalogRecord:
        raise GameLifecycleError("Catalog post-shoot status requires an ability record.")
    _validate_unit(unit)
    current_ids = _validate_current_model_instance_ids(current_model_instance_ids)
    if type(clause) is not RuleClause:
        raise GameLifecycleError("Catalog post-shoot status requires a rule clause.")
    if not _clause_is_supported_post_shoot_hit_target_status_denial(clause):
        return ()
    supported_effects = tuple(
        (effect_index, effect)
        for effect_index, effect in enumerate(clause.effects)
        if _effect_is_supported_status_denial(effect)
    )
    if len(supported_effects) != 1:
        raise GameLifecycleError("Catalog post-shoot status requires one supported effect.")
    effect_index, effect = supported_effects[0]
    parameters = parameter_payload(effect.parameters)
    status = _required_string_parameter(parameters, key="status")
    status_label = _required_string_parameter(parameters, key="status_label")
    target_scope = _required_string_parameter(parameters, key="target_scope")
    source_model_ids = _post_shoot_status_source_model_ids(
        record=record,
        unit=unit,
        current_model_instance_ids=current_ids,
        clause=clause,
        attack_sequence=context.attack_sequence,
    )
    groups: list[CatalogPostShootHitTargetStatusGroup] = []
    for source_model_id in source_model_ids:
        hit_target_ids = successful_hit_target_unit_ids_for_sequence(
            decisions=context.decisions,
            sequence=context.attack_sequence,
            attacker_model_instance_id=source_model_id,
        )
        options = tuple(
            CatalogPostShootHitTargetStatusOption(
                option_id=_post_shoot_hit_target_status_option_id(
                    record=record,
                    unit=unit,
                    clause=clause,
                    effect_index=effect_index,
                    status=status,
                    source_model_instance_id=source_model_id,
                    target_unit_instance_id=target_unit_id,
                ),
                target_unit_instance_id=target_unit_id,
            )
            for target_unit_id in hit_target_ids
            if _post_shoot_hit_target_status_target_is_eligible(
                state=context.state,
                attacker_player_id=context.attack_sequence.attacker_player_id,
                target_unit_instance_id=target_unit_id,
            )
        )
        if not options:
            continue
        groups.append(
            CatalogPostShootHitTargetStatusGroup(
                record=record,
                unit=unit,
                clause=clause,
                effect_index=effect_index,
                status=status,
                status_label=status_label,
                target_scope=target_scope,
                source_model_instance_id=source_model_id,
                attack_sequence=context.attack_sequence,
                attack_sequence_completed_event_id=context.attack_sequence_completed_event_id,
                options=options,
            )
        )
    return tuple(sorted(groups, key=lambda group: group.sort_key))


def _named_weapon_ability_choice_option_from_effect(
    *,
    record: AbilityCatalogRecord,
    unit: UnitInstance,
    clause: RuleClause,
    effect_index: int,
    effect: RuleEffectSpec,
) -> CatalogNamedWeaponAbilityChoiceOption | None:
    if type(record) is not AbilityCatalogRecord:
        raise GameLifecycleError("Catalog named weapon ability choice requires an ability record.")
    _validate_unit(unit)
    if type(clause) is not RuleClause:
        raise GameLifecycleError("Catalog named weapon ability choice requires a rule clause.")
    if type(effect_index) is not int or effect_index < 0:
        raise GameLifecycleError(
            "Catalog named weapon ability choice effect_index must be non-negative."
        )
    if type(effect) is not RuleEffectSpec:
        raise GameLifecycleError("Catalog named weapon ability choice requires a rule effect.")
    if effect.kind is not RuleEffectKind.GRANT_WEAPON_ABILITY:
        return None
    parameters = parameter_payload(effect.parameters)
    keyword = _weapon_keyword_from_parameters(parameters)
    if keyword is None:
        return None
    if not _weapon_ability_choice_has_supported_runtime_shape(parameters, keyword=keyword):
        return None
    selection_group_id = _required_string_parameter(parameters, key="selection_group_id")
    selection_option_id = _required_string_parameter(parameters, key="selection_option_id")
    return CatalogNamedWeaponAbilityChoiceOption(
        option_id=(
            f"{CATALOG_IR_NAMED_WEAPON_ABILITY_CHOICE_CONSUMER_ID}:"
            f"{unit.unit_instance_id}:{record.record_id}:{clause.clause_id}:"
            f"{selection_group_id}:{selection_option_id}"
        ),
        selection_option_id=selection_option_id,
        selection_option_index=_required_positive_int_parameter(
            parameters,
            key="selection_option_index",
        ),
        keyword=keyword,
        weapon_ability_value=_optional_weapon_ability_choice_value_parameter(parameters),
        ability=_weapon_ability_descriptor_for_grant(parameters=parameters, keyword=keyword),
        effect_index=effect_index,
    )


def _post_shoot_status_source_model_ids(
    *,
    record: AbilityCatalogRecord,
    unit: UnitInstance,
    current_model_instance_ids: tuple[str, ...],
    clause: RuleClause,
    attack_sequence: AttackSequence,
) -> tuple[str | None, ...]:
    if type(record) is not AbilityCatalogRecord:
        raise GameLifecycleError("Catalog post-shoot status requires an ability record.")
    _validate_unit(unit)
    current_ids = _validate_current_model_instance_ids(current_model_instance_ids)
    if type(clause) is not RuleClause or clause.trigger is None:
        raise GameLifecycleError("Catalog post-shoot status requires a triggered clause.")
    if type(attack_sequence) is not AttackSequence:
        raise GameLifecycleError("Catalog post-shoot status requires an AttackSequence.")
    trigger_parameters = parameter_payload(clause.trigger.parameters)
    subject = _required_string_parameter(trigger_parameters, key="subject")
    if subject == "this_unit":
        return (None,)
    if subject not in {"this_model", "bearer"}:
        raise GameLifecycleError("Catalog post-shoot status has unsupported subject.")
    candidate_ids = (
        _record_current_wargear_bearer_model_ids(
            record=record,
            unit=unit,
            current_model_instance_ids=current_ids,
        )
        if record.source_kind is AbilitySourceKind.WARGEAR
        else current_ids
    )
    shot_model_ids = {pool.attacker_model_instance_id for pool in attack_sequence.attack_pools}
    return tuple(model_id for model_id in candidate_ids if model_id in shot_model_ids)


def _post_shoot_hit_target_status_target_is_eligible(
    *,
    state: GameState,
    attacker_player_id: str,
    target_unit_instance_id: str,
) -> bool:
    attacker_id = _validate_identifier("attacker_player_id", attacker_player_id)
    target_id = _validate_identifier("target_unit_instance_id", target_unit_instance_id)
    target = rules_unit_view_by_id(state=state, unit_instance_id=target_id)
    return target.owner_player_id != attacker_id and bool(target.alive_models())


def _unit_move_completed_mortal_wounds_target_candidates(
    *,
    state: GameState,
    ruleset_descriptor: RulesetDescriptor,
    source_rules_unit_instance_id: str,
) -> tuple[tuple[str, str], ...]:
    _validate_game_state(state)
    if type(ruleset_descriptor) is not RulesetDescriptor:
        raise GameLifecycleError("Catalog move-completed mortal wounds requires ruleset.")
    source_rules_unit_id = _validate_identifier(
        "source_rules_unit_instance_id",
        source_rules_unit_instance_id,
    )
    source_rules_unit = rules_unit_view_by_id(
        state=state,
        unit_instance_id=source_rules_unit_id,
    )
    source_models = _placed_alive_geometry_models_for_rules_unit(
        state=state,
        rules_unit_instance_id=source_rules_unit.unit_instance_id,
    )
    if not source_models:
        return ()
    candidates: list[tuple[str, str]] = []
    for target_rules_unit in _rules_unit_views_for_other_players(
        state=state,
        player_id=source_rules_unit.owner_player_id,
    ):
        target_models = _placed_alive_geometry_models_for_rules_unit(
            state=state,
            rules_unit_instance_id=target_rules_unit.unit_instance_id,
        )
        if not target_models:
            continue
        if any(
            source_model.is_within_engagement_range(
                target_model,
                horizontal_inches=ruleset_descriptor.engagement_policy.horizontal_inches,
                vertical_inches=ruleset_descriptor.engagement_policy.vertical_inches,
            )
            for source_model in source_models
            for target_model in target_models
        ):
            candidates.append(
                (
                    target_rules_unit.unit_instance_id,
                    target_rules_unit.owner_player_id,
                )
            )
    return tuple(sorted(candidates))


def _unit_move_completed_mortal_wounds_target_is_eligible(
    *,
    state: GameState,
    ruleset_descriptor: RulesetDescriptor,
    source_rules_unit_instance_id: str,
    target_unit_instance_id: str,
    target_player_id: str,
) -> bool:
    target_unit_id = _validate_identifier("target_unit_instance_id", target_unit_instance_id)
    target_player = _validate_identifier("target_player_id", target_player_id)
    return (
        target_unit_id,
        target_player,
    ) in _unit_move_completed_mortal_wounds_target_candidates(
        state=state,
        ruleset_descriptor=ruleset_descriptor,
        source_rules_unit_instance_id=source_rules_unit_instance_id,
    )


def _unit_move_completed_mortal_wounds_target_option_id(
    *,
    record: AbilityCatalogRecord,
    source_rules_unit_instance_id: str,
    clause: RuleClause,
    effect_index: int,
    target_unit_instance_id: str,
) -> str:
    if type(record) is not AbilityCatalogRecord:
        raise GameLifecycleError("Catalog move-completed mortal wounds requires a record.")
    source_rules_unit_id = _validate_identifier(
        "source_rules_unit_instance_id",
        source_rules_unit_instance_id,
    )
    if type(clause) is not RuleClause:
        raise GameLifecycleError("Catalog move-completed mortal wounds requires a clause.")
    if type(effect_index) is not int or effect_index < 0:
        raise GameLifecycleError(
            "Catalog move-completed mortal wounds effect_index must be non-negative."
        )
    target_unit_id = _validate_identifier("target_unit_instance_id", target_unit_instance_id)
    return (
        f"{CATALOG_IR_UNIT_MOVE_COMPLETED_MORTAL_WOUNDS_CONSUMER_ID}:"
        f"{source_rules_unit_id}:{record.record_id}:{clause.clause_id}:"
        f"effect-{effect_index:03d}:target-{target_unit_id}"
    )


def _post_shoot_hit_target_status_option_id(
    *,
    record: AbilityCatalogRecord,
    unit: UnitInstance,
    clause: RuleClause,
    effect_index: int,
    status: str,
    source_model_instance_id: str | None,
    target_unit_instance_id: str,
) -> str:
    if type(record) is not AbilityCatalogRecord:
        raise GameLifecycleError("Catalog post-shoot status requires an ability record.")
    _validate_unit(unit)
    if type(clause) is not RuleClause:
        raise GameLifecycleError("Catalog post-shoot status requires a rule clause.")
    if type(effect_index) is not int or effect_index < 0:
        raise GameLifecycleError("Catalog post-shoot status effect_index must be non-negative.")
    source_token = (
        "unit"
        if source_model_instance_id is None
        else _validate_identifier("source_model_instance_id", source_model_instance_id)
    )
    target_token = _validate_identifier("target_unit_instance_id", target_unit_instance_id)
    return (
        f"{CATALOG_IR_POST_SHOOT_HIT_TARGET_STATUS_CONSUMER_ID}:{unit.unit_instance_id}:"
        f"{record.record_id}:{clause.clause_id}:effect-{effect_index:03d}:"
        f"source-{source_token}:target-{target_token}:"
        f"{_validate_identifier('status', status)}"
    )


def _named_weapon_ability_choice_target_model_ids(
    *,
    army_catalog: ArmyCatalog,
    record: AbilityCatalogRecord,
    unit: UnitInstance,
    current_model_instance_ids: tuple[str, ...],
    target_scope: str,
    weapon_names: tuple[str, ...],
) -> tuple[str, ...]:
    current_ids = _validate_current_model_instance_ids(current_model_instance_ids)
    target_scope = _validate_named_weapon_choice_target_scope(target_scope)
    names = _validate_named_weapon_names(weapon_names)
    if target_scope == "this_model" and record.source_kind is AbilitySourceKind.WARGEAR:
        candidate_ids = _record_current_wargear_bearer_model_ids(
            record=record,
            unit=unit,
            current_model_instance_ids=current_ids,
        )
    else:
        candidate_ids = current_ids
    if not candidate_ids:
        return ()
    target_ids = tuple(
        sorted(
            model.model_instance_id
            for model in unit.own_models
            if model.model_instance_id in candidate_ids
            and model.is_alive
            and _model_has_named_weapon(
                army_catalog=army_catalog,
                model=model,
                weapon_names=names,
            )
        )
    )
    if not target_ids:
        raise GameLifecycleError(
            "Catalog named weapon ability choice target models lack the named weapon."
        )
    return target_ids


def _model_has_named_weapon(
    *,
    army_catalog: ArmyCatalog,
    model: ModelInstance,
    weapon_names: tuple[str, ...],
) -> bool:
    if type(army_catalog) is not ArmyCatalog:
        raise GameLifecycleError("Catalog named weapon lookup requires an ArmyCatalog.")
    if type(model) is not ModelInstance:
        raise GameLifecycleError("Catalog named weapon lookup requires a model instance.")
    requested_tokens = {_weapon_name_match_token(name) for name in weapon_names}
    for wargear_id in model.wargear_ids:
        wargear = _catalog_wargear_by_id(army_catalog, wargear_id=wargear_id)
        for profile in wargear.weapon_profiles:
            if _weapon_name_match_token(profile.name) in requested_tokens:
                return True
    return False


def _catalog_wargear_by_id(army_catalog: ArmyCatalog, *, wargear_id: str) -> Wargear:
    requested_wargear_id = _validate_identifier("wargear_id", wargear_id)
    for wargear in army_catalog.wargear:
        if wargear.wargear_id == requested_wargear_id:
            return wargear
    raise GameLifecycleError("Catalog named weapon lookup found unknown wargear.")


def _current_placed_alive_model_instance_ids_for_unit(
    *,
    state: GameState,
    unit: UnitInstance,
) -> tuple[str, ...]:
    _validate_game_state(state)
    _validate_unit(unit)
    return tuple(
        model.model_instance_id
        for model in _rules_units.placed_alive_models_for_component_unit(
            state=state,
            unit_instance_id=unit.unit_instance_id,
        )
    )


def _placed_alive_model_instance_ids_for_rules_unit(
    *,
    state: GameState,
    rules_unit_instance_id: str,
) -> tuple[str, ...]:
    _validate_game_state(state)
    rules_unit_id = _validate_identifier("rules_unit_instance_id", rules_unit_instance_id)
    if state.battlefield_state is None:
        return ()
    placed_model_ids = frozenset(state.battlefield_state.placed_model_ids())
    rules_unit = rules_unit_view_by_id(state=state, unit_instance_id=rules_unit_id)
    return tuple(
        sorted(
            model.model_instance_id
            for model in rules_unit.alive_models()
            if model.model_instance_id in placed_model_ids
        )
    )


def _placed_alive_geometry_models_for_rules_unit(
    *,
    state: GameState,
    rules_unit_instance_id: str,
) -> tuple[GeometryModel, ...]:
    _validate_game_state(state)
    rules_unit_id = _validate_identifier("rules_unit_instance_id", rules_unit_instance_id)
    if state.battlefield_state is None:
        return ()
    scenario = BattlefieldScenario(
        armies=tuple(state.army_definitions),
        battlefield_state=state.battlefield_state,
    )
    model_by_id = {
        model.model_instance_id: model
        for model in rules_unit_view_by_id(
            state=state,
            unit_instance_id=rules_unit_id,
        ).alive_models()
    }
    models: list[GeometryModel] = []
    for model_id in _placed_alive_model_instance_ids_for_rules_unit(
        state=state,
        rules_unit_instance_id=rules_unit_id,
    ):
        placement = state.battlefield_state.model_placement_by_id(model_id)
        model = model_by_id.get(model_id)
        if model is None:
            raise GameLifecycleError(
                "Catalog move-completed mortal wounds model placement drifted."
            )
        if scenario.model_instance_for_placement(placement).model_instance_id != model_id:
            raise GameLifecycleError(
                "Catalog move-completed mortal wounds placement references wrong model."
            )
        models.append(geometry_model_for_placement(model=model, placement=placement))
    return tuple(models)


def _rules_unit_views_for_other_players(
    *,
    state: GameState,
    player_id: str,
) -> tuple[RulesUnitView, ...]:
    _validate_game_state(state)
    owning_player_id = _validate_identifier("player_id", player_id)
    views: list[RulesUnitView] = []
    for army in state.army_definitions:
        if army.player_id == owning_player_id:
            continue
        attached_component_ids: set[str] = set()
        for attached_unit in army.attached_units:
            views.append(
                rules_unit_view_by_id(
                    state=state,
                    unit_instance_id=attached_unit.attached_unit_instance_id,
                )
            )
            attached_component_ids.update(attached_unit.component_unit_instance_ids)
        for unit in army.units:
            if unit.unit_instance_id in attached_component_ids:
                continue
            views.append(rules_unit_view_by_id(state=state, unit_instance_id=unit.unit_instance_id))
    return tuple(sorted(views, key=lambda view: view.unit_instance_id))


def _catalog_named_weapon_ability_choice_group_resolved(
    *,
    state: GameState,
    unit_instance_id: str,
    catalog_record_id: str,
    clause_id: str,
    selection_group_id: str,
) -> bool:
    requested_unit_id = _validate_identifier("unit_instance_id", unit_instance_id)
    requested_record_id = _validate_identifier("catalog_record_id", catalog_record_id)
    requested_clause_id = _validate_identifier("clause_id", clause_id)
    requested_group_id = _validate_identifier("selection_group_id", selection_group_id)
    for effect in state.persisting_effects_for_unit(requested_unit_id):
        if not isinstance(effect.effect_payload, dict):
            continue
        payload = cast(dict[str, object], effect.effect_payload)
        if payload.get("effect_kind") != CATALOG_NAMED_WEAPON_ABILITY_CHOICE_EFFECT_KIND:
            continue
        if (
            payload.get("catalog_record_id") == requested_record_id
            and payload.get("clause_id") == requested_clause_id
            and payload.get("selection_group_id") == requested_group_id
        ):
            return True
    return False


def _named_weapon_ability_choice_request_payload(
    *,
    state: GameState,
    group: CatalogNamedWeaponAbilityChoiceGroup,
) -> dict[str, object]:
    return {
        **_named_weapon_ability_choice_base_payload(state=state, group=group),
        "available_named_weapon_ability_option_ids": [option.option_id for option in group.options],
        "available_named_weapon_ability_choices": [
            _named_weapon_ability_choice_selection_payload(option) for option in group.options
        ],
    }


def _named_weapon_ability_choice_option_payload(
    *,
    state: GameState,
    group: CatalogNamedWeaponAbilityChoiceGroup,
    option: CatalogNamedWeaponAbilityChoiceOption,
) -> dict[str, object]:
    return {
        **_named_weapon_ability_choice_base_payload(state=state, group=group),
        "selected_named_weapon_ability_choice": (
            _named_weapon_ability_choice_selection_payload(option)
        ),
    }


def _named_weapon_ability_choice_base_payload(
    *,
    state: GameState,
    group: CatalogNamedWeaponAbilityChoiceGroup,
) -> dict[str, object]:
    return {
        "submission_kind": SELECT_CATALOG_NAMED_WEAPON_ABILITY_CHOICE_SUBMISSION_KIND,
        "hook_id": CATALOG_IR_NAMED_WEAPON_ABILITY_CHOICE_CONSUMER_ID,
        "game_id": state.game_id,
        "battle_round": state.battle_round,
        "phase": BattlePhase.SHOOTING.value,
        "active_player_id": state.active_player_id,
        "catalog_record_id": group.record.record_id,
        "ability_id": group.record.definition.ability_id,
        "ability_name": group.record.definition.name,
        "source_rule_id": group.record.definition.source_id,
        "unit_instance_id": group.unit.unit_instance_id,
        "clause_id": group.clause.clause_id,
        "selection_group_id": group.selection_group_id,
        "target_scope": group.target_scope,
        "weapon_names": list(group.weapon_names),
        "target_model_instance_ids": list(group.target_model_instance_ids),
    }


def _post_shoot_hit_target_status_request_payload(
    *,
    state: GameState,
    group: CatalogPostShootHitTargetStatusGroup,
) -> dict[str, object]:
    return {
        **_post_shoot_hit_target_status_base_payload(state=state, group=group),
        "available_target_unit_instance_ids": [
            option.target_unit_instance_id for option in group.options
        ],
        "available_post_shoot_hit_target_status_options": [
            _post_shoot_hit_target_status_selection_payload(option) for option in group.options
        ],
    }


def _post_shoot_hit_target_status_option_payload(
    *,
    state: GameState,
    group: CatalogPostShootHitTargetStatusGroup,
    option: CatalogPostShootHitTargetStatusOption,
) -> dict[str, object]:
    return {
        **_post_shoot_hit_target_status_base_payload(state=state, group=group),
        "selected_post_shoot_hit_target_status": (
            _post_shoot_hit_target_status_selection_payload(option)
        ),
    }


def _post_shoot_hit_target_status_base_payload(
    *,
    state: GameState,
    group: CatalogPostShootHitTargetStatusGroup,
) -> dict[str, object]:
    return {
        "submission_kind": SELECT_CATALOG_POST_SHOOT_HIT_TARGET_STATUS_SUBMISSION_KIND,
        "hook_id": CATALOG_IR_POST_SHOOT_HIT_TARGET_STATUS_CONSUMER_ID,
        "game_id": state.game_id,
        "battle_round": state.battle_round,
        "phase": BattlePhase.SHOOTING.value,
        "active_player_id": state.active_player_id,
        "player_id": group.attack_sequence.attacker_player_id,
        "catalog_record_id": group.record.record_id,
        "ability_id": group.record.definition.ability_id,
        "ability_name": group.record.definition.name,
        "source_rule_id": group.record.definition.source_id,
        "rule_ir_hash": _rule_ir_from_record(group.record).ir_hash(),
        "unit_instance_id": group.unit.unit_instance_id,
        "source_model_instance_id": group.source_model_instance_id,
        "clause_id": group.clause.clause_id,
        "effect_index": group.effect_index,
        "status": group.status,
        "status_label": group.status_label,
        "operation": "deny",
        "target_scope": group.target_scope,
        "attack_sequence_id": group.attack_sequence.sequence_id,
        "attack_sequence_completed_event_id": group.attack_sequence_completed_event_id,
        "attack_sequence": group.attack_sequence.to_payload(),
    }


def _post_shoot_hit_target_status_selection_payload(
    option: CatalogPostShootHitTargetStatusOption,
) -> dict[str, object]:
    return {
        "option_id": option.option_id,
        "target_unit_instance_id": option.target_unit_instance_id,
    }


def _post_shoot_hit_target_status_option_label(
    *,
    group: CatalogPostShootHitTargetStatusGroup,
    option: CatalogPostShootHitTargetStatusOption,
) -> str:
    return f"Deny {group.status_label} to {option.target_unit_instance_id}"


def _unit_move_completed_mortal_wounds_target_request_payload(
    *,
    state: GameState,
    group: CatalogUnitMoveCompletedMortalWoundsGroup,
) -> dict[str, object]:
    return {
        **_unit_move_completed_mortal_wounds_target_base_payload(state=state, group=group),
        "available_target_unit_instance_ids": [
            option.target_unit_instance_id for option in group.options
        ],
        "available_unit_move_completed_mortal_wounds_target_options": [
            _unit_move_completed_mortal_wounds_target_selection_payload(option)
            for option in group.options
        ],
    }


def _unit_move_completed_mortal_wounds_target_option_payload(
    *,
    state: GameState,
    group: CatalogUnitMoveCompletedMortalWoundsGroup,
    option: CatalogUnitMoveCompletedMortalWoundsTargetOption,
) -> dict[str, object]:
    return {
        **_unit_move_completed_mortal_wounds_target_base_payload(state=state, group=group),
        "selected_unit_move_completed_mortal_wounds_target": (
            _unit_move_completed_mortal_wounds_target_selection_payload(option)
        ),
    }


def _unit_move_completed_mortal_wounds_target_base_payload(
    *,
    state: GameState,
    group: CatalogUnitMoveCompletedMortalWoundsGroup,
) -> dict[str, object]:
    return {
        "submission_kind": (
            SELECT_CATALOG_UNIT_MOVE_COMPLETED_MORTAL_WOUNDS_TARGET_SUBMISSION_KIND
        ),
        "hook_id": CATALOG_IR_UNIT_MOVE_COMPLETED_MORTAL_WOUNDS_CONSUMER_ID,
        "game_id": state.game_id,
        "battle_round": state.battle_round,
        "phase": BattlePhase.CHARGE.value,
        "active_player_id": state.active_player_id,
        "player_id": group.player_id,
        "catalog_record_id": group.record.record_id,
        "ability_id": group.record.definition.ability_id,
        "ability_name": group.record.definition.name,
        "source_rule_id": group.record.definition.source_id,
        "source_rules_unit_instance_id": group.source_rules_unit_instance_id,
        "source_unit_instance_id": group.source_unit.unit_instance_id,
        "clause_id": group.clause.clause_id,
        "effect_index": group.effect_index,
        "roll_threshold": group.roll_threshold,
        "roll_expression": "D6",
        "roll_count_scope": "each_model_in_this_unit",
        "mortal_wounds_expression": group.mortal_wounds_expression.canonical(),
        "roll_model_instance_ids": list(group.roll_model_instance_ids),
        "trigger_event_id": group.trigger_event_id,
        "movement_action": group.movement_action,
    }


def _unit_move_completed_mortal_wounds_target_selection_payload(
    option: CatalogUnitMoveCompletedMortalWoundsTargetOption,
) -> dict[str, object]:
    return {
        "option_id": option.option_id,
        "target_unit_instance_id": option.target_unit_instance_id,
        "target_player_id": option.target_player_id,
    }


def _unit_move_completed_mortal_wounds_target_option_label(
    option: CatalogUnitMoveCompletedMortalWoundsTargetOption,
) -> str:
    return f"Inflict mortal wounds on {option.target_unit_instance_id}"


def _unit_move_completed_mortal_wounds_effect_payload(
    *,
    group: CatalogUnitMoveCompletedMortalWoundsGroup,
    option: CatalogUnitMoveCompletedMortalWoundsTargetOption,
    roll_model_instance_id: str,
) -> JsonValue:
    roll_model_id = _validate_identifier("roll_model_instance_id", roll_model_instance_id)
    return validate_json_value(
        {
            "effect_kind": "catalog_unit_move_completed_mortal_wounds",
            "catalog_record_id": group.record.record_id,
            "ability_id": group.record.definition.ability_id,
            "ability_name": group.record.definition.name,
            "catalog_source_rule_id": group.record.definition.source_id,
            "player_id": group.player_id,
            "source_rules_unit_instance_id": group.source_rules_unit_instance_id,
            "source_unit_instance_id": group.source_unit.unit_instance_id,
            "clause_id": group.clause.clause_id,
            "effect_index": group.effect_index,
            "roll_model_instance_id": roll_model_id,
            "roll_threshold": group.roll_threshold,
            "roll_expression": "D6",
            "mortal_wounds_expression": group.mortal_wounds_expression.canonical(),
            "target_unit_instance_id": option.target_unit_instance_id,
            "target_player_id": option.target_player_id,
            "trigger_event_id": group.trigger_event_id,
            "movement_action": group.movement_action,
        }
    )


type _PostShootHitTargetStatusGroupKey = tuple[str, str, str, str, int, str, str, str]
type _UnitMoveCompletedMortalWoundsGroupKey = tuple[str, str, str, str, int, str]


def _post_shoot_hit_target_status_group_key(
    group: CatalogPostShootHitTargetStatusGroup,
) -> _PostShootHitTargetStatusGroupKey:
    if type(group) is not CatalogPostShootHitTargetStatusGroup:
        raise GameLifecycleError("Catalog post-shoot status requires a group.")
    return (
        group.attack_sequence_completed_event_id,
        group.attack_sequence.sequence_id,
        group.record.record_id,
        group.clause.clause_id,
        group.effect_index,
        group.status,
        group.unit.unit_instance_id,
        "" if group.source_model_instance_id is None else group.source_model_instance_id,
    )


def _resolved_post_shoot_hit_target_status_group_keys(
    decisions: DecisionController,
) -> frozenset[_PostShootHitTargetStatusGroupKey]:
    if type(decisions) is not DecisionController:
        raise GameLifecycleError("Catalog post-shoot status resolution lookup requires decisions.")
    keys: set[_PostShootHitTargetStatusGroupKey] = set()
    for event in decisions.event_log.records:
        if event.event_type != CATALOG_POST_SHOOT_HIT_TARGET_STATUS_SELECTED_EVENT:
            continue
        payload = event.payload
        if not isinstance(payload, dict):
            raise GameLifecycleError(
                "Catalog post-shoot status selected event payload must be an object."
            )
        payload_object = cast(dict[str, object], payload)
        source_model_id = payload_object.get("source_model_instance_id")
        if source_model_id is not None and type(source_model_id) is not str:
            raise GameLifecycleError(
                "Catalog post-shoot status selected event source_model_instance_id is invalid."
            )
        keys.add(
            (
                _payload_string(payload_object, key="attack_sequence_completed_event_id"),
                _payload_string(payload_object, key="attack_sequence_id"),
                _payload_string(payload_object, key="catalog_record_id"),
                _payload_string(payload_object, key="clause_id"),
                _payload_int(payload_object, key="effect_index"),
                _payload_string(payload_object, key="status"),
                _payload_string(payload_object, key="unit_instance_id"),
                "" if source_model_id is None else source_model_id,
            )
        )
    return frozenset(keys)


def _unit_move_completed_mortal_wounds_group_key(
    group: CatalogUnitMoveCompletedMortalWoundsGroup,
) -> _UnitMoveCompletedMortalWoundsGroupKey:
    if type(group) is not CatalogUnitMoveCompletedMortalWoundsGroup:
        raise GameLifecycleError("Catalog move-completed mortal wounds requires a group.")
    return (
        group.trigger_event_id,
        group.source_rules_unit_instance_id,
        group.record.record_id,
        group.clause.clause_id,
        group.effect_index,
        group.movement_action,
    )


def _selected_unit_move_completed_mortal_wounds_group_keys(
    decisions: DecisionController,
) -> frozenset[_UnitMoveCompletedMortalWoundsGroupKey]:
    return frozenset(_selected_unit_move_completed_mortal_wounds_targets(decisions))


def _selected_unit_move_completed_mortal_wounds_targets(
    decisions: DecisionController,
) -> Mapping[
    _UnitMoveCompletedMortalWoundsGroupKey,
    CatalogUnitMoveCompletedMortalWoundsTargetOption,
]:
    if type(decisions) is not DecisionController:
        raise GameLifecycleError(
            "Catalog move-completed mortal wounds selected lookup requires decisions."
        )
    selected: dict[
        _UnitMoveCompletedMortalWoundsGroupKey,
        CatalogUnitMoveCompletedMortalWoundsTargetOption,
    ] = {}
    for event in decisions.event_log.records:
        if event.event_type != CATALOG_UNIT_MOVE_COMPLETED_MORTAL_WOUNDS_TARGET_SELECTED_EVENT:
            continue
        payload = event.payload
        if not isinstance(payload, dict):
            raise GameLifecycleError(
                "Catalog move-completed mortal wounds selected event payload must be an object."
            )
        payload_object = cast(dict[str, object], payload)
        selected[
            (
                _payload_string(payload_object, key="trigger_event_id"),
                _payload_string(payload_object, key="source_rules_unit_instance_id"),
                _payload_string(payload_object, key="catalog_record_id"),
                _payload_string(payload_object, key="clause_id"),
                _payload_int(payload_object, key="effect_index"),
                _payload_string(payload_object, key="movement_action"),
            )
        ] = CatalogUnitMoveCompletedMortalWoundsTargetOption(
            option_id=_payload_string(payload_object, key="selected_option_id"),
            target_unit_instance_id=_payload_string(
                payload_object,
                key="target_unit_instance_id",
            ),
            target_player_id=_payload_string(payload_object, key="target_player_id"),
        )
    return MappingProxyType(selected)


def _named_weapon_ability_choice_selection_payload(
    option: CatalogNamedWeaponAbilityChoiceOption,
) -> dict[str, object]:
    payload: dict[str, object] = {
        "option_id": option.option_id,
        "selection_option_id": option.selection_option_id,
        "selection_option_index": option.selection_option_index,
        "selected_weapon_ability": option.keyword.value,
        "keyword": option.keyword.value,
        "ability_descriptor": None if option.ability is None else option.ability.to_payload(),
    }
    if option.weapon_ability_value is not None:
        payload["weapon_ability_value"] = option.weapon_ability_value
    return payload


def _named_weapon_ability_choice_option_label(
    *,
    group: CatalogNamedWeaponAbilityChoiceGroup,
    option: CatalogNamedWeaponAbilityChoiceOption,
) -> str:
    weapon_label = ", ".join(group.weapon_names)
    return f"{option.label} for {weapon_label}"


def _named_weapon_ability_choice_persisting_effect(
    *,
    state: GameState,
    result_id: str,
    group: CatalogNamedWeaponAbilityChoiceGroup,
    option: CatalogNamedWeaponAbilityChoiceOption,
) -> PersistingEffect:
    result = _validate_identifier("result_id", result_id)
    selected_payload = _named_weapon_ability_choice_selection_payload(option)
    payload = {
        **_named_weapon_ability_choice_option_payload(
            state=state,
            group=group,
            option=option,
        ),
        **selected_payload,
        "effect_kind": CATALOG_NAMED_WEAPON_ABILITY_CHOICE_EFFECT_KIND,
    }
    return PersistingEffect(
        effect_id=f"{result}:catalog-named-weapon-ability-choice",
        source_rule_id=group.record.definition.source_id,
        owner_player_id=_validate_identifier("active_player_id", state.active_player_id),
        target_unit_instance_ids=(group.unit.unit_instance_id,),
        started_battle_round=state.battle_round,
        started_phase=BattlePhaseKind.SHOOTING,
        expiration=EffectExpiration.end_phase(
            battle_round=state.battle_round,
            phase=BattlePhaseKind.SHOOTING,
            player_id=_validate_identifier("active_player_id", state.active_player_id),
        ),
        effect_payload=validate_json_value(payload),
    )


def invalid_catalog_post_shoot_hit_target_status_status(
    *,
    state: GameState,
    request: DecisionRequest,
    result: DecisionResult,
) -> LifecycleStatus | None:
    invalid_status = _catalog_post_shoot_hit_target_status_finite_invalid_status(
        state=state,
        request=request,
        result=result,
        invalid_reason="invalid_catalog_post_shoot_hit_target_status_result",
    )
    if invalid_status is not None:
        return invalid_status
    drift_reason = _catalog_post_shoot_hit_target_status_drift_reason(
        state=state,
        request=request,
        result=result,
    )
    if drift_reason is None:
        return None
    return _catalog_post_shoot_hit_target_status_invalid_status(
        state=state,
        actor_id=result.actor_id,
        invalid_reason=drift_reason,
    )


def apply_catalog_post_shoot_hit_target_status_result(
    *,
    state: GameState,
    decisions: DecisionController,
    result: DecisionResult,
) -> LifecycleStatus | None:
    if type(decisions) is not DecisionController:
        raise GameLifecycleError("Catalog post-shoot status apply requires decisions.")
    if type(result) is not DecisionResult:
        raise GameLifecycleError("Catalog post-shoot status apply requires DecisionResult.")
    record = decisions.record_for_result(result)
    invalid_status = invalid_catalog_post_shoot_hit_target_status_status(
        state=state,
        request=record.request,
        result=record.result,
    )
    if invalid_status is not None:
        return invalid_status
    payload = _payload_object(record.result.payload)
    _post_shoot_hit_target_status_attack_sequence_from_payload(payload)
    selected_payload = _post_shoot_hit_target_status_selected_payload(payload)
    effect = _post_shoot_hit_target_status_persisting_effect(
        state=state,
        result_id=record.result.result_id,
        payload=payload,
        selected_payload=selected_payload,
    )
    state.record_persisting_effect(effect)
    decisions.event_log.append(
        CATALOG_POST_SHOOT_HIT_TARGET_STATUS_SELECTED_EVENT,
        validate_json_value(
            {
                "game_id": state.game_id,
                "battle_round": state.battle_round,
                "phase": BattlePhase.SHOOTING.value,
                "active_player_id": state.active_player_id,
                "player_id": record.result.actor_id,
                "request_id": record.request.request_id,
                "result_id": record.result.result_id,
                "selected_option_id": record.result.selected_option_id,
                "persisting_effect_id": effect.effect_id,
                "catalog_record_id": _payload_string(payload, key="catalog_record_id"),
                "source_rule_id": _payload_string(payload, key="source_rule_id"),
                "unit_instance_id": _payload_string(payload, key="unit_instance_id"),
                "source_model_instance_id": payload.get("source_model_instance_id"),
                "clause_id": _payload_string(payload, key="clause_id"),
                "effect_index": _payload_int(payload, key="effect_index"),
                "status": _payload_string(payload, key="status"),
                "target_unit_instance_id": _payload_string(
                    selected_payload,
                    key="target_unit_instance_id",
                ),
                "attack_sequence_id": _payload_string(payload, key="attack_sequence_id"),
                "attack_sequence_completed_event_id": _payload_string(
                    payload,
                    key="attack_sequence_completed_event_id",
                ),
            }
        ),
    )
    return None


def invalid_catalog_unit_move_completed_mortal_wounds_target_status(
    *,
    state: GameState,
    request: DecisionRequest,
    result: DecisionResult,
    ruleset_descriptor: RulesetDescriptor,
) -> LifecycleStatus | None:
    invalid_status = _catalog_unit_move_completed_mortal_wounds_target_finite_invalid_status(
        state=state,
        request=request,
        result=result,
        invalid_reason="invalid_catalog_unit_move_completed_mortal_wounds_target_result",
    )
    if invalid_status is not None:
        return invalid_status
    drift_reason = _catalog_unit_move_completed_mortal_wounds_target_drift_reason(
        state=state,
        request=request,
        result=result,
        ruleset_descriptor=ruleset_descriptor,
    )
    if drift_reason is None:
        return None
    return _catalog_unit_move_completed_mortal_wounds_target_invalid_status(
        state=state,
        actor_id=result.actor_id,
        invalid_reason=drift_reason,
    )


def apply_catalog_unit_move_completed_mortal_wounds_target_result(
    *,
    state: GameState,
    decisions: DecisionController,
    result: DecisionResult,
    ruleset_descriptor: RulesetDescriptor,
) -> LifecycleStatus | None:
    if type(decisions) is not DecisionController:
        raise GameLifecycleError("Catalog move-completed mortal wounds apply requires decisions.")
    if type(result) is not DecisionResult:
        raise GameLifecycleError("Catalog move-completed mortal wounds apply requires result.")
    record = decisions.record_for_result(result)
    invalid_status = invalid_catalog_unit_move_completed_mortal_wounds_target_status(
        state=state,
        request=record.request,
        result=record.result,
        ruleset_descriptor=ruleset_descriptor,
    )
    if invalid_status is not None:
        return invalid_status
    payload = _payload_object(record.result.payload)
    selected_payload = _unit_move_completed_mortal_wounds_selected_payload(payload)
    decisions.event_log.append(
        CATALOG_UNIT_MOVE_COMPLETED_MORTAL_WOUNDS_TARGET_SELECTED_EVENT,
        validate_json_value(
            {
                "game_id": state.game_id,
                "battle_round": state.battle_round,
                "phase": BattlePhase.CHARGE.value,
                "active_player_id": state.active_player_id,
                "player_id": record.result.actor_id,
                "request_id": record.request.request_id,
                "result_id": record.result.result_id,
                "selected_option_id": record.result.selected_option_id,
                "hook_id": CATALOG_IR_UNIT_MOVE_COMPLETED_MORTAL_WOUNDS_CONSUMER_ID,
                "catalog_record_id": _payload_string(payload, key="catalog_record_id"),
                "source_rule_id": _payload_string(payload, key="source_rule_id"),
                "source_rules_unit_instance_id": _payload_string(
                    payload,
                    key="source_rules_unit_instance_id",
                ),
                "source_unit_instance_id": _payload_string(
                    payload,
                    key="source_unit_instance_id",
                ),
                "clause_id": _payload_string(payload, key="clause_id"),
                "effect_index": _payload_int(payload, key="effect_index"),
                "trigger_event_id": _payload_string(payload, key="trigger_event_id"),
                "movement_action": _payload_string(payload, key="movement_action"),
                "target_unit_instance_id": _payload_string(
                    selected_payload,
                    key="target_unit_instance_id",
                ),
                "target_player_id": _payload_string(selected_payload, key="target_player_id"),
            }
        ),
    )
    return None


def _post_shoot_hit_target_status_persisting_effect(
    *,
    state: GameState,
    result_id: str,
    payload: Mapping[str, object],
    selected_payload: Mapping[str, object],
) -> PersistingEffect:
    result = _validate_identifier("result_id", result_id)
    status = _payload_string(payload, key="status")
    target_unit_id = _payload_string(selected_payload, key="target_unit_instance_id")
    owner_player_id = _payload_string(payload, key="player_id")
    effect_payload = {
        "effect_kind": CATALOG_POST_SHOOT_HIT_TARGET_STATUS_EFFECT_KIND,
        "catalog_record_id": _payload_string(payload, key="catalog_record_id"),
        "ability_id": _payload_string(payload, key="ability_id"),
        "ability_name": _payload_string(payload, key="ability_name"),
        "source_rule_id": _payload_string(payload, key="source_rule_id"),
        "rule_ir_hash": _payload_string(payload, key="rule_ir_hash"),
        "unit_instance_id": _payload_string(payload, key="unit_instance_id"),
        "source_model_instance_id": payload.get("source_model_instance_id"),
        "clause_id": _payload_string(payload, key="clause_id"),
        "effect_index": _payload_int(payload, key="effect_index"),
        "status": status,
        "status_label": _payload_string(payload, key="status_label"),
        "operation": _payload_string(payload, key="operation"),
        "target_scope": _payload_string(payload, key="target_scope"),
        "target_unit_instance_id": target_unit_id,
        "attack_sequence_id": _payload_string(payload, key="attack_sequence_id"),
        "attack_sequence_completed_event_id": _payload_string(
            payload,
            key="attack_sequence_completed_event_id",
        ),
        "benefit_of_cover_denied": status == "benefit_of_cover",
    }
    return PersistingEffect(
        effect_id=f"{result}:catalog-post-shoot-hit-target-status:{target_unit_id}:{status}",
        source_rule_id=_payload_string(payload, key="source_rule_id"),
        owner_player_id=owner_player_id,
        target_unit_instance_ids=(target_unit_id,),
        started_battle_round=state.battle_round,
        started_phase=BattlePhaseKind.SHOOTING,
        expiration=EffectExpiration.end_phase(
            battle_round=state.battle_round,
            phase=BattlePhaseKind.SHOOTING,
            player_id=_validate_identifier("active_player_id", state.active_player_id),
        ),
        effect_payload=validate_json_value(effect_payload),
    )


def _selected_catalog_named_weapon_ability_grants(
    context: WeaponProfileModifierContext,
) -> tuple[CatalogWeaponKeywordGrant, ...]:
    if type(context) is not WeaponProfileModifierContext:
        raise GameLifecycleError("Catalog named weapon ability grants require context.")
    if context.source_phase is not BattlePhase.SHOOTING:
        return ()
    profile_token = _weapon_name_match_token(context.weapon_profile.name)
    grants: list[CatalogWeaponKeywordGrant] = []
    for effect in context.state.persisting_effects_for_unit(context.attacking_unit_instance_id):
        if not isinstance(effect.effect_payload, dict):
            continue
        payload = cast(dict[str, object], effect.effect_payload)
        if payload.get("effect_kind") != CATALOG_NAMED_WEAPON_ABILITY_CHOICE_EFFECT_KIND:
            continue
        target_model_ids = _payload_string_tuple(payload, key="target_model_instance_ids")
        if context.attacker_model_instance_id not in target_model_ids:
            continue
        weapon_names = _payload_string_tuple(payload, key="weapon_names")
        if profile_token not in {_weapon_name_match_token(name) for name in weapon_names}:
            continue
        keyword = _weapon_keyword_from_value(_payload_string(payload, key="keyword"))
        ability = _weapon_ability_descriptor_for_selected_choice_payload(
            payload=payload,
            keyword=keyword,
        )
        grants.append(
            CatalogWeaponKeywordGrant(
                source_id=f"{effect.effect_id}:{keyword.value}",
                keyword=keyword,
                weapon_scope="all",
                ability=ability,
            )
        )
    return tuple(sorted(grants, key=lambda grant: grant.source_id))


def _weapon_ability_descriptor_for_selected_choice_payload(
    *,
    payload: Mapping[str, object],
    keyword: WeaponKeyword,
) -> AbilityDescriptor | None:
    parameters: dict[str, object] = {"weapon_ability": keyword.value}
    if "weapon_ability_value" in payload:
        parameters["weapon_ability_value"] = payload["weapon_ability_value"]
    return _weapon_ability_descriptor_for_grant(parameters=parameters, keyword=keyword)


def _catalog_named_weapon_ability_choice_invalid_status(
    *,
    state: GameState,
    actor_id: str | None,
    invalid_reason: str,
) -> LifecycleStatus:
    return LifecycleStatus.invalid(
        stage=GameLifecycleStage.BATTLE,
        message="Catalog named weapon ability choice is no longer valid.",
        payload=validate_json_value(
            {
                "game_id": state.game_id,
                "player_id": actor_id,
                "battle_round": state.battle_round,
                "phase": BattlePhase.SHOOTING.value,
                "invalid_reason": _validate_identifier("invalid_reason", invalid_reason),
            }
        ),
    )


def _catalog_post_shoot_hit_target_status_invalid_status(
    *,
    state: GameState,
    actor_id: str | None,
    invalid_reason: str,
) -> LifecycleStatus:
    return LifecycleStatus.invalid(
        stage=GameLifecycleStage.BATTLE,
        message="Catalog post-shoot hit target status choice is no longer valid.",
        payload=validate_json_value(
            {
                "game_id": state.game_id,
                "player_id": actor_id,
                "battle_round": state.battle_round,
                "phase": (
                    None if state.current_battle_phase is None else state.current_battle_phase.value
                ),
                "invalid_reason": _validate_identifier("invalid_reason", invalid_reason),
            }
        ),
    )


def _catalog_post_shoot_hit_target_status_finite_invalid_status(
    *,
    state: GameState,
    request: DecisionRequest,
    result: DecisionResult,
    invalid_reason: str,
) -> LifecycleStatus | None:
    if result.request_id != request.request_id:
        return _catalog_post_shoot_hit_target_status_invalid_field_status(
            state=state,
            invalid_reason=invalid_reason,
            field="request_id",
        )
    if result.decision_type != request.decision_type:
        return _catalog_post_shoot_hit_target_status_invalid_field_status(
            state=state,
            invalid_reason=invalid_reason,
            field="decision_type",
        )
    if result.actor_id != request.actor_id:
        return _catalog_post_shoot_hit_target_status_invalid_field_status(
            state=state,
            invalid_reason=invalid_reason,
            field="actor_id",
        )
    selected_option = next(
        (option for option in request.options if option.option_id == result.selected_option_id),
        None,
    )
    if selected_option is None:
        return _catalog_post_shoot_hit_target_status_invalid_field_status(
            state=state,
            invalid_reason=invalid_reason,
            field="selected_option_id",
        )
    if result.payload != selected_option.payload:
        return _catalog_post_shoot_hit_target_status_invalid_field_status(
            state=state,
            invalid_reason=invalid_reason,
            field="payload",
        )
    return None


def _catalog_post_shoot_hit_target_status_invalid_field_status(
    *,
    state: GameState,
    invalid_reason: str,
    field: str,
) -> LifecycleStatus:
    return LifecycleStatus.invalid(
        stage=state.stage,
        message="Catalog post-shoot hit target status result is invalid.",
        payload=validate_json_value(
            {
                "invalid_reason": _validate_identifier("invalid_reason", invalid_reason),
                "field": _validate_identifier("field", field),
            }
        ),
    )


def _catalog_post_shoot_hit_target_status_drift_reason(
    *,
    state: GameState,
    request: DecisionRequest,
    result: DecisionResult,
) -> str | None:
    if request.decision_type != SELECT_CATALOG_POST_SHOOT_HIT_TARGET_STATUS_DECISION_TYPE:
        return "request_decision_type_drift"
    if result.decision_type != SELECT_CATALOG_POST_SHOOT_HIT_TARGET_STATUS_DECISION_TYPE:
        return "result_decision_type_drift"
    request_payload = _optional_payload_object(request.payload)
    if request_payload is None:
        return "request_payload_not_object"
    result_payload = _optional_payload_object(result.payload)
    if result_payload is None:
        return "payload_not_object"
    if result_payload.get("submission_kind") != (
        SELECT_CATALOG_POST_SHOOT_HIT_TARGET_STATUS_SUBMISSION_KIND
    ):
        return "submission_kind_drift"
    if result_payload.get("hook_id") != CATALOG_IR_POST_SHOOT_HIT_TARGET_STATUS_CONSUMER_ID:
        return "hook_id_drift"
    if request_payload.get("hook_id") != CATALOG_IR_POST_SHOOT_HIT_TARGET_STATUS_CONSUMER_ID:
        return "request_hook_id_drift"
    if state.current_battle_phase is not BattlePhase.SHOOTING:
        return "phase_drift"
    if result_payload.get("game_id") != state.game_id:
        return "game_id_drift"
    if request_payload.get("game_id") != state.game_id:
        return "request_game_id_drift"
    if result_payload.get("battle_round") != state.battle_round:
        return "battle_round_drift"
    if request_payload.get("battle_round") != state.battle_round:
        return "request_battle_round_drift"
    if result_payload.get("phase") != BattlePhase.SHOOTING.value:
        return "payload_phase_drift"
    if request_payload.get("phase") != BattlePhase.SHOOTING.value:
        return "request_phase_drift"
    if result_payload.get("active_player_id") != state.active_player_id:
        return "active_player_drift"
    if request_payload.get("active_player_id") != state.active_player_id:
        return "request_active_player_drift"
    actor_id = _validate_identifier("actor_id", result.actor_id)
    if result_payload.get("player_id") != actor_id:
        return "actor_player_drift"
    selected_payload = result_payload.get("selected_post_shoot_hit_target_status")
    if not isinstance(selected_payload, dict):
        return "selected_payload_not_object"
    selected_payload_object = cast(dict[str, object], selected_payload)
    if selected_payload_object.get("option_id") != result.selected_option_id:
        return "selected_option_payload_drift"
    selected_target_id = selected_payload_object.get("target_unit_instance_id")
    if type(selected_target_id) is not str:
        return "selected_target_payload_drift"
    if not _post_shoot_hit_target_status_target_is_eligible(
        state=state,
        attacker_player_id=actor_id,
        target_unit_instance_id=selected_target_id,
    ):
        return "target_drift"
    attack_sequence = _post_shoot_hit_target_status_attack_sequence_from_payload(result_payload)
    if attack_sequence.source_phase is not BattlePhase.SHOOTING:
        return "attack_sequence_phase_drift"
    if attack_sequence.sequence_id != result_payload.get("attack_sequence_id"):
        return "attack_sequence_id_drift"
    if attack_sequence.attacker_player_id != actor_id:
        return "attack_sequence_attacker_drift"
    if attack_sequence.attacking_unit_instance_id != result_payload.get("unit_instance_id"):
        return "attack_sequence_unit_drift"
    return None


def _catalog_unit_move_completed_mortal_wounds_target_invalid_status(
    *,
    state: GameState,
    actor_id: str | None,
    invalid_reason: str,
) -> LifecycleStatus:
    return LifecycleStatus.invalid(
        stage=GameLifecycleStage.BATTLE,
        message="Catalog move-completed mortal wounds target choice is no longer valid.",
        payload=validate_json_value(
            {
                "game_id": state.game_id,
                "player_id": actor_id,
                "battle_round": state.battle_round,
                "phase": (
                    None if state.current_battle_phase is None else state.current_battle_phase.value
                ),
                "invalid_reason": _validate_identifier("invalid_reason", invalid_reason),
            }
        ),
    )


def _catalog_unit_move_completed_mortal_wounds_target_finite_invalid_status(
    *,
    state: GameState,
    request: DecisionRequest,
    result: DecisionResult,
    invalid_reason: str,
) -> LifecycleStatus | None:
    if result.request_id != request.request_id:
        return _catalog_unit_move_completed_mortal_wounds_target_invalid_field_status(
            state=state,
            invalid_reason=invalid_reason,
            field="request_id",
        )
    if result.decision_type != request.decision_type:
        return _catalog_unit_move_completed_mortal_wounds_target_invalid_field_status(
            state=state,
            invalid_reason=invalid_reason,
            field="decision_type",
        )
    if result.actor_id != request.actor_id:
        return _catalog_unit_move_completed_mortal_wounds_target_invalid_field_status(
            state=state,
            invalid_reason=invalid_reason,
            field="actor_id",
        )
    selected_option = next(
        (option for option in request.options if option.option_id == result.selected_option_id),
        None,
    )
    if selected_option is None:
        return _catalog_unit_move_completed_mortal_wounds_target_invalid_field_status(
            state=state,
            invalid_reason=invalid_reason,
            field="selected_option_id",
        )
    if result.payload != selected_option.payload:
        return _catalog_unit_move_completed_mortal_wounds_target_invalid_field_status(
            state=state,
            invalid_reason=invalid_reason,
            field="payload",
        )
    return None


def _catalog_unit_move_completed_mortal_wounds_target_invalid_field_status(
    *,
    state: GameState,
    invalid_reason: str,
    field: str,
) -> LifecycleStatus:
    return LifecycleStatus.invalid(
        stage=state.stage,
        message="Catalog move-completed mortal wounds target result is invalid.",
        payload=validate_json_value(
            {
                "invalid_reason": _validate_identifier("invalid_reason", invalid_reason),
                "field": _validate_identifier("field", field),
            }
        ),
    )


def _catalog_unit_move_completed_mortal_wounds_target_drift_reason(
    *,
    state: GameState,
    request: DecisionRequest,
    result: DecisionResult,
    ruleset_descriptor: RulesetDescriptor,
) -> str | None:
    if (
        request.decision_type
        != SELECT_CATALOG_UNIT_MOVE_COMPLETED_MORTAL_WOUNDS_TARGET_DECISION_TYPE
    ):
        return "request_decision_type_drift"
    if (
        result.decision_type
        != SELECT_CATALOG_UNIT_MOVE_COMPLETED_MORTAL_WOUNDS_TARGET_DECISION_TYPE
    ):
        return "result_decision_type_drift"
    if type(ruleset_descriptor) is not RulesetDescriptor:
        raise GameLifecycleError("Catalog move-completed mortal wounds requires ruleset.")
    request_payload = _optional_payload_object(request.payload)
    if request_payload is None:
        return "request_payload_not_object"
    result_payload = _optional_payload_object(result.payload)
    if result_payload is None:
        return "payload_not_object"
    if result_payload.get("submission_kind") != (
        SELECT_CATALOG_UNIT_MOVE_COMPLETED_MORTAL_WOUNDS_TARGET_SUBMISSION_KIND
    ):
        return "submission_kind_drift"
    if result_payload.get("hook_id") != CATALOG_IR_UNIT_MOVE_COMPLETED_MORTAL_WOUNDS_CONSUMER_ID:
        return "hook_id_drift"
    if request_payload.get("hook_id") != CATALOG_IR_UNIT_MOVE_COMPLETED_MORTAL_WOUNDS_CONSUMER_ID:
        return "request_hook_id_drift"
    if state.current_battle_phase is not BattlePhase.CHARGE:
        return "phase_drift"
    if result_payload.get("game_id") != state.game_id:
        return "game_id_drift"
    if request_payload.get("game_id") != state.game_id:
        return "request_game_id_drift"
    if result_payload.get("battle_round") != state.battle_round:
        return "battle_round_drift"
    if request_payload.get("battle_round") != state.battle_round:
        return "request_battle_round_drift"
    if result_payload.get("phase") != BattlePhase.CHARGE.value:
        return "payload_phase_drift"
    if request_payload.get("phase") != BattlePhase.CHARGE.value:
        return "request_phase_drift"
    if result_payload.get("active_player_id") != state.active_player_id:
        return "active_player_drift"
    if request_payload.get("active_player_id") != state.active_player_id:
        return "request_active_player_drift"
    actor_id = _validate_identifier("actor_id", result.actor_id)
    if result_payload.get("player_id") != actor_id:
        return "actor_player_drift"
    selected_payload = result_payload.get("selected_unit_move_completed_mortal_wounds_target")
    if not isinstance(selected_payload, dict):
        return "selected_payload_not_object"
    selected_payload_object = cast(dict[str, object], selected_payload)
    if selected_payload_object.get("option_id") != result.selected_option_id:
        return "selected_option_payload_drift"
    selected_target_id = selected_payload_object.get("target_unit_instance_id")
    selected_target_player_id = selected_payload_object.get("target_player_id")
    if type(selected_target_id) is not str or type(selected_target_player_id) is not str:
        return "selected_target_payload_drift"
    source_rules_unit_id = result_payload.get("source_rules_unit_instance_id")
    if type(source_rules_unit_id) is not str:
        return "source_rules_unit_payload_drift"
    source_rules_unit = rules_unit_view_by_id(
        state=state,
        unit_instance_id=source_rules_unit_id,
    )
    if source_rules_unit.owner_player_id != actor_id:
        return "source_rules_unit_owner_drift"
    if not _unit_move_completed_mortal_wounds_target_is_eligible(
        state=state,
        ruleset_descriptor=ruleset_descriptor,
        source_rules_unit_instance_id=source_rules_unit_id,
        target_unit_instance_id=selected_target_id,
        target_player_id=selected_target_player_id,
    ):
        return "target_drift"
    return None


def _payload_object(payload: object) -> dict[str, object]:
    if not isinstance(payload, dict):
        raise GameLifecycleError("Catalog named weapon ability choice payload must be an object.")
    return cast(dict[str, object], payload)


def _optional_payload_object(payload: object) -> dict[str, object] | None:
    if not isinstance(payload, dict):
        return None
    return cast(dict[str, object], payload)


def _payload_string(payload: Mapping[str, object], *, key: str) -> str:
    value = payload.get(key)
    if type(value) is not str:
        raise GameLifecycleError(f"Catalog named weapon payload {key} must be a string.")
    return _validate_identifier(key, value)


def _payload_int(payload: Mapping[str, object], *, key: str) -> int:
    value = payload.get(key)
    if type(value) is not int:
        raise GameLifecycleError(f"Catalog named weapon payload {key} must be an integer.")
    return value


def _post_shoot_hit_target_status_selected_payload(
    payload: Mapping[str, object],
) -> dict[str, object]:
    selected_payload = payload.get("selected_post_shoot_hit_target_status")
    if not isinstance(selected_payload, dict):
        raise GameLifecycleError("Catalog post-shoot status selected payload must be an object.")
    return cast(dict[str, object], selected_payload)


def _unit_move_completed_mortal_wounds_selected_payload(
    payload: Mapping[str, object],
) -> dict[str, object]:
    selected_payload = payload.get("selected_unit_move_completed_mortal_wounds_target")
    if not isinstance(selected_payload, dict):
        raise GameLifecycleError(
            "Catalog move-completed mortal wounds selected payload must be an object."
        )
    return cast(dict[str, object], selected_payload)


def _post_shoot_hit_target_status_attack_sequence_from_payload(
    payload: Mapping[str, object],
) -> AttackSequence:
    attack_sequence_payload = payload.get("attack_sequence")
    if not isinstance(attack_sequence_payload, dict):
        raise GameLifecycleError("Catalog post-shoot status payload requires attack_sequence.")
    return AttackSequence.from_payload(cast(AttackSequencePayload, attack_sequence_payload))


def _payload_string_tuple(payload: Mapping[str, object], *, key: str) -> tuple[str, ...]:
    value = payload.get(key)
    if type(value) is not list:
        raise GameLifecycleError(f"Catalog named weapon payload {key} must be a list.")
    items = cast(list[object], value)
    values: list[str] = []
    seen: set[str] = set()
    for item in items:
        if type(item) is not str:
            raise GameLifecycleError(f"Catalog named weapon payload {key} must contain strings.")
        resolved = _validate_identifier(key, item)
        if resolved in seen:
            raise GameLifecycleError(
                f"Catalog named weapon payload {key} must not duplicate values."
            )
        seen.add(resolved)
        values.append(resolved)
    if not values:
        raise GameLifecycleError(f"Catalog named weapon payload {key} must not be empty.")
    return tuple(values)


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
        for clause in _clauses_from_record(record):
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
    if _st.rule_has_fight_start_selected_target_effect(rule_ir):
        consumer_ids.add(CATALOG_IR_SELECTED_TARGET_EFFECT_CONSUMER_ID)
    if _st.rule_has_post_shoot_hit_target_effect(rule_ir):
        consumer_ids.add(CATALOG_IR_POST_SHOOT_HIT_TARGET_EFFECT_CONSUMER_ID)
    if _st.rule_has_shooting_start_selected_target_effect(rule_ir):
        consumer_ids.add(CATALOG_IR_SHOOTING_START_SELECTED_TARGET_EFFECT_CONSUMER_ID)
    return tuple(sorted(consumer_ids))


def catalog_rule_ir_consumers_for_clause(clause: RuleClause) -> tuple[str, ...]:
    if type(clause) is not RuleClause:
        raise GameLifecycleError("Catalog rule consumer classification requires RuleClause.")
    if _frequency.clause_has_unconsumed_once_per_battle_activation(clause):
        return ()
    if _datasheet.clause_has_invalid_exact_datasheet_runtime_shape(clause):
        return ()
    consumer_ids = set(_command_points.command_point_consumer_ids_for_clause(clause))
    consumer_ids.update(_datasheet.consumer_ids_for_clause(clause))
    if _frequency.clause_is_runtime_once_per_battle_activation(clause):
        consumer_ids.add(CATALOG_IR_ONCE_PER_BATTLE_ABILITY_CONSUMER_ID)
    if _clause_targets_this_model(clause):
        for effect in clause.effects:
            if _effect_is_feel_no_pain_grant(effect):
                consumer_ids.add(CATALOG_IR_FEEL_NO_PAIN_SOURCE_CONSUMER_ID)
            if _clause_is_supported_this_model_attack_roll_modifier(clause, effect):
                modifier_consumer_id = _roll_modifier_consumer_id_for_effect(effect)
                if modifier_consumer_id is not None:
                    consumer_ids.add(modifier_consumer_id)
    consumer_ids.update(_contextual.consumer_ids_for_clause(clause))
    if _clause_targets_attacker_status_unit(clause):
        for effect in clause.effects:
            if _effect_is_minimum_unmodified_hit_success(effect):
                consumer_ids.add(CATALOG_IR_MINIMUM_UNMODIFIED_HIT_SUCCESS_CONSUMER_ID)
    if _clause_is_named_weapon_ability_choice(clause):
        for effect in clause.effects:
            consumer_ids.update(_weapon_keyword_grant_consumer_ids_for_effect(effect))
    if _clause_is_supported_post_shoot_hit_target_status_denial(clause):
        consumer_ids.add(CATALOG_IR_POST_SHOOT_HIT_TARGET_STATUS_CONSUMER_ID)
    if _clause_is_supported_unit_move_completed_mortal_wounds(clause):
        consumer_ids.add(CATALOG_IR_UNIT_MOVE_COMPLETED_MORTAL_WOUNDS_CONSUMER_ID)
    consumer_ids.update(_ucbs.consumer_ids_for_clause(clause))
    if _is_movement_transit(clause):
        consumer_ids.add(CATALOG_IR_MOVEMENT_TRANSIT_PERMISSION_CONSUMER_ID)
    if _clause_is_supported_setup_reactive_shoot_charge(clause):
        consumer_ids.add(CATALOG_IR_SETUP_REACTIVE_SHOOT_CHARGE_CONSUMER_ID)
    if _reserve_restriction.clause_is_reserve_arrival_restriction(clause):
        consumer_ids.add(CATALOG_IR_RESERVE_ARRIVAL_RESTRICTION_CONSUMER_ID)
    if _prebattle_redeploy.clause_is_prebattle_redeploy_permission(clause):
        consumer_ids.add(CATALOG_IR_PREBATTLE_REDEPLOY_PERMISSION_CONSUMER_ID)
    if _fight_end_move.clause_is_fight_end_triggered_movement(clause):
        consumer_ids.add(_fight_end_move.CATALOG_IR_FIGHT_END_TRIGGERED_MOVEMENT_CONSUMER_ID)
    if _clause_is_structured_wound_reroll_clause(clause):
        consumer_ids.add(CATALOG_IR_WOUND_ROLL_REROLL_CONSUMER_ID)
    if _clause_is_structured_destroyed_unit_restore_clause(clause):
        consumer_ids.add(CATALOG_IR_DESTROYED_UNIT_RESTORE_LOST_WOUNDS_CONSUMER_ID)
    if _clause_is_supported_tracked_target_selection(clause):
        consumer_ids.add(CATALOG_IR_TRACKED_TARGET_SELECTION_CONSUMER_ID)
    if _clause_is_supported_tracked_target_reroll(clause):
        consumer_ids.add(CATALOG_IR_TRACKED_TARGET_REROLL_CONSUMER_ID)
    if _clause_is_supported_tracked_target_destroyed_reselect(clause):
        consumer_ids.add(CATALOG_IR_TRACKED_TARGET_DESTROYED_RESELECT_CONSUMER_ID)
    if _clause_is_supported_first_death_return(clause):
        consumer_ids.add(CATALOG_IR_FIRST_DEATH_RETURN_CONSUMER_ID)
    for effect in clause.effects:
        if effect.kind is RuleEffectKind.FORCE_DESPERATE_ESCAPE_TESTS:
            consumer_ids.add(CATALOG_IR_FORCE_DESPERATE_ESCAPE_CONSUMER_ID)
        elif effect.kind is RuleEffectKind.MODIFY_DICE_ROLL:
            modifier_consumer_id = _roll_modifier_consumer_id_for_effect(effect)
            if modifier_consumer_id == CATALOG_IR_DESPERATE_ESCAPE_ROLL_MODIFIER_CONSUMER_ID:
                consumer_ids.add(modifier_consumer_id)
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
        fall_back_consumer_id = _fall_back_eligibility_consumer_id_for_effect(effect)
        if fall_back_consumer_id is not None:
            consumer_ids.add(fall_back_consumer_id)
    return tuple(sorted(consumer_ids))


def catalog_rule_ir_hook_ids_for_rule(rule_ir: RuleIR) -> tuple[str, ...]:
    if type(rule_ir) is not RuleIR:
        raise GameLifecycleError("Catalog rule consumer classification requires RuleIR.")
    hook_ids: set[str] = set()
    for clause in rule_ir.clauses:
        if _frequency.clause_has_unconsumed_once_per_battle_activation(clause):
            continue
        if _datasheet.clause_has_invalid_exact_datasheet_runtime_shape(clause):
            continue
        hook_ids.update(_catalog_ir_hook_ids_for_clause(clause))
        if _prebattle_redeploy.clause_is_prebattle_redeploy_permission(clause):
            continue
        for effect in clause.effects:
            if _effect_is_charge_roll_modifier(effect):
                hook_ids.add(CATALOG_IR_CHARGE_ROLL_CONSUMER_ID)
            hook_ids.update(_catalog_ir_hook_ids_for_effect(effect))
    if _st.rule_has_fight_start_selected_target_effect(rule_ir):
        hook_ids.add(CATALOG_IR_SELECTED_TARGET_EFFECT_CONSUMER_ID)
    if _st.rule_has_post_shoot_hit_target_effect(rule_ir):
        hook_ids.add(CATALOG_IR_POST_SHOOT_HIT_TARGET_EFFECT_CONSUMER_ID)
    if _st.rule_has_shooting_start_selected_target_effect(rule_ir):
        hook_ids.add(CATALOG_IR_SHOOTING_START_SELECTED_TARGET_EFFECT_CONSUMER_ID)
    return tuple(sorted(hook_ids))


def _catalog_ir_hook_ids_for_clause(clause: RuleClause) -> tuple[str, ...]:
    hook_ids = set(_command_points.command_point_consumer_ids_for_clause(clause))
    hook_ids.update(_datasheet.consumer_ids_for_clause(clause))
    if _frequency.clause_is_runtime_once_per_battle_activation(clause):
        hook_ids.add(CATALOG_IR_ONCE_PER_BATTLE_ABILITY_CONSUMER_ID)
    if _clause_is_supported_tracked_target_selection(clause):
        hook_ids.add(CATALOG_IR_TRACKED_TARGET_SELECTION_CONSUMER_ID)
    if _clause_is_supported_tracked_target_reroll(clause):
        hook_ids.add(CATALOG_IR_TRACKED_TARGET_REROLL_CONSUMER_ID)
    if _clause_is_supported_tracked_target_destroyed_reselect(clause):
        hook_ids.add(CATALOG_IR_TRACKED_TARGET_DESTROYED_RESELECT_CONSUMER_ID)
    if _clause_is_supported_first_death_return(clause):
        hook_ids.add(CATALOG_IR_FIRST_DEATH_RETURN_CONSUMER_ID)
        hook_ids.add(CATALOG_IR_FIRST_DEATH_RETURN_PHASE_END_CONSUMER_ID)
    if _is_movement_transit(clause):
        hook_ids.add(CATALOG_IR_MOVEMENT_TRANSIT_PERMISSION_CONSUMER_ID)
    if _clause_is_supported_post_shoot_hit_target_status_denial(clause):
        hook_ids.add(CATALOG_IR_POST_SHOOT_HIT_TARGET_STATUS_CONSUMER_ID)
    if _clause_is_supported_unit_move_completed_mortal_wounds(clause):
        hook_ids.add(CATALOG_IR_UNIT_MOVE_COMPLETED_MORTAL_WOUNDS_CONSUMER_ID)
    hook_ids.update(_ucbs.consumer_ids_for_clause(clause))
    if _clause_is_supported_setup_reactive_shoot_charge(clause):
        hook_ids.add(CATALOG_IR_SETUP_REACTIVE_SHOOT_CHARGE_CONSUMER_ID)
    if _reserve_restriction.clause_is_reserve_arrival_restriction(clause):
        hook_ids.add(CATALOG_IR_RESERVE_ARRIVAL_RESTRICTION_CONSUMER_ID)
    if _prebattle_redeploy.clause_is_prebattle_redeploy_permission(clause):
        hook_ids.add(CATALOG_IR_PREBATTLE_REDEPLOY_PERMISSION_CONSUMER_ID)
    if _fight_end_move.clause_is_fight_end_triggered_movement(clause):
        hook_ids.add(_fight_end_move.CATALOG_IR_FIGHT_END_TRIGGERED_MOVEMENT_CONSUMER_ID)
    hook_ids.update(_contextual.consumer_ids_for_clause(clause))
    return tuple(sorted(hook_ids))


def catalog_rule_clauses_from_record(record: AbilityCatalogRecord) -> tuple[RuleClause, ...]:
    return _clauses_from_record(record)


def catalog_rule_record_source_matches_unit(
    *,
    record: AbilityCatalogRecord,
    unit: UnitInstance,
    current_model_instance_ids: tuple[str, ...],
) -> bool:
    return _record_source_matches_unit(
        record=record,
        unit=unit,
        current_model_instance_ids=current_model_instance_ids,
    )


def catalog_rule_current_placed_alive_model_instance_ids_for_unit(
    *,
    state: GameState,
    unit: UnitInstance,
) -> tuple[str, ...]:
    return _current_placed_alive_model_instance_ids_for_unit(state=state, unit=unit)


def catalog_rule_record_current_wargear_bearer_model_ids(
    *,
    record: AbilityCatalogRecord,
    unit: UnitInstance,
    current_model_instance_ids: tuple[str, ...],
) -> tuple[str, ...]:
    return _record_current_wargear_bearer_model_ids(
        record=record,
        unit=unit,
        current_model_instance_ids=current_model_instance_ids,
    )


def catalog_rule_unit_scoped_generic_records(
    *,
    ability_index: AbilityCatalogIndex,
    unit: UnitInstance,
    current_model_instance_ids: tuple[str, ...],
    trigger_kind: TimingTriggerKind,
) -> tuple[AbilityCatalogRecord, ...]:
    return _unit_scoped_generic_records(
        ability_index=ability_index,
        unit=unit,
        current_model_instance_ids=current_model_instance_ids,
        trigger_kind=trigger_kind,
    )


def catalog_movement_transit_permissions_for_model(
    *,
    ability_index: AbilityCatalogIndex,
    unit: UnitInstance,
    model_instance_id: str,
    current_model_instance_ids: tuple[str, ...],
    movement_mode: str,
) -> tuple[CatalogMovementTransitPermission, ...]:
    _validate_ability_index(ability_index)
    _validate_unit(unit)
    moving_model_id = _validate_identifier("model_instance_id", model_instance_id)
    current_ids = _validate_current_model_instance_ids(current_model_instance_ids)
    if moving_model_id not in current_ids:
        raise GameLifecycleError("Catalog movement transit model must be current evidence.")
    requested_mode = _movement_mode_token(movement_mode)
    permissions: list[CatalogMovementTransitPermission] = []
    for record in _unit_scoped_generic_records(
        ability_index=ability_index,
        unit=unit,
        current_model_instance_ids=current_ids,
        trigger_kind=TimingTriggerKind.PASSIVE_QUERY,
    ):
        if record.source_kind is AbilitySourceKind.WARGEAR and moving_model_id not in set(
            _record_current_wargear_bearer_model_ids(
                record=record,
                unit=unit,
                current_model_instance_ids=current_ids,
            )
        ):
            continue
        for clause in _clauses_from_record(record):
            for permission in _movement_transit_permissions_from_clause(
                record=record,
                clause=clause,
            ):
                if permission.applies_to_movement_mode(requested_mode):
                    permissions.append(permission)
    return tuple(
        sorted(
            permissions,
            key=lambda permission: (
                permission.record_id,
                permission.clause_id,
                permission.source_rule_id,
                permission.permission,
            ),
        )
    )


def catalog_rule_clause_is_supported_tracked_target_selection(clause: RuleClause) -> bool:
    return _clause_is_supported_tracked_target_selection(clause)


def catalog_rule_clause_is_supported_tracked_target_destroyed_reselect(
    clause: RuleClause,
) -> bool:
    return _clause_is_supported_tracked_target_destroyed_reselect(clause)


def catalog_rule_tracked_target_supported_attack_roll_pairs_for_clause(
    clause: RuleClause,
) -> tuple[tuple[str, str], ...]:
    return _tracked_target_supported_attack_roll_pairs_for_clause(clause)


def catalog_rule_clause_is_supported_first_death_return(clause: RuleClause) -> bool:
    return _clause_is_supported_first_death_return(clause)


def _clause_is_supported_tracked_target_selection(clause: RuleClause) -> bool:
    if type(clause) is not RuleClause:
        raise GameLifecycleError("Tracked-target consumer classification requires RuleClause.")
    if _datasheet.clause_has_invalid_exact_datasheet_runtime_shape(clause):
        return False
    if not clause.is_supported:
        return False
    if clause.target is None or clause.target.kind not in {
        RuleTargetKind.ENEMY_UNIT,
        RuleTargetKind.FRIENDLY_UNIT,
    }:
        return False
    selection_effects = tuple(
        effect for effect in clause.effects if effect.kind is RuleEffectKind.SELECT_TRACKED_TARGET
    )
    if len(selection_effects) != 1:
        return False
    parameters = parameter_payload(selection_effects[0].parameters)
    return (
        parameters.get("selection_kind") == "select_one"
        and parameters.get("target_lifecycle") == "until_destroyed"
        and parameters.get("target_scope") in {"enemy_unit", "friendly_unit"}
        and parameters.get("target_allegiance") in {"enemy", "friendly"}
        and parameters.get("tracked_target_owner") in {"this_model", "this_unit"}
        and parameters.get("tracked_target_role") in {"prey", "quarry"}
        and type(parameters.get("replacement")) is bool
        and (
            (clause.target.kind is RuleTargetKind.ENEMY_UNIT)
            == (parameters.get("target_allegiance") == "enemy")
        )
        and (
            (clause.target.kind is RuleTargetKind.ENEMY_UNIT)
            == (parameters.get("target_scope") == "enemy_unit")
        )
    )


def _clause_is_supported_tracked_target_reroll(clause: RuleClause) -> bool:
    if type(clause) is not RuleClause:
        raise GameLifecycleError("Tracked-target consumer classification requires RuleClause.")
    if not clause.is_supported:
        return False
    trigger = clause.trigger
    if trigger is None or trigger.kind is not RuleTriggerKind.DICE_ROLL:
        return False
    trigger_parameters = parameter_payload(trigger.parameters)
    if trigger_parameters.get("target_reference") != "tracked_target":
        return False
    if trigger_parameters.get("tracked_target_owner") not in {"this_model", "this_unit"}:
        return False
    if trigger_parameters.get("tracked_target_role") not in {"prey", "quarry"}:
        return False
    if trigger_parameters.get("attack_kind") not in {"melee", "ranged"}:
        return False
    if trigger_parameters.get("actor") not in {"this_model", "model_in_this_models_unit"}:
        return False
    if not any(
        _condition_is_tracked_target_attack_constraint(
            condition,
            trigger_parameters=trigger_parameters,
        )
        for condition in clause.conditions
    ):
        return False
    reroll_effects = tuple(
        effect for effect in clause.effects if effect.kind is RuleEffectKind.REROLL_PERMISSION
    )
    if not reroll_effects or len(reroll_effects) != len(clause.effects):
        return False
    return all(
        _effect_is_supported_tracked_target_reroll(effect, trigger_parameters=trigger_parameters)
        for effect in reroll_effects
    )


def _condition_is_tracked_target_attack_constraint(
    condition: RuleCondition,
    *,
    trigger_parameters: Mapping[str, object],
) -> bool:
    if condition.kind is not RuleConditionKind.TARGET_CONSTRAINT:
        return False
    parameters = parameter_payload(condition.parameters)
    return (
        parameters.get("relationship") == "attack_targets_tracked_target"
        and parameters.get("target_reference") == "tracked_target"
        and parameters.get("tracked_target_owner") == trigger_parameters.get("tracked_target_owner")
        and parameters.get("tracked_target_role") == trigger_parameters.get("tracked_target_role")
        and parameters.get("gate_subject") == "attack_target"
        and parameters.get("attack_kind") == trigger_parameters.get("attack_kind")
        and parameters.get("actor") == trigger_parameters.get("actor")
    )


def _effect_is_supported_tracked_target_reroll(
    effect: RuleEffectSpec,
    *,
    trigger_parameters: Mapping[str, object],
) -> bool:
    parameters = parameter_payload(effect.parameters)
    roll_type = parameters.get("roll_type")
    return (
        parameters.get("target_reference") == "tracked_target"
        and parameters.get("tracked_target_owner") == trigger_parameters.get("tracked_target_owner")
        and parameters.get("tracked_target_role") == trigger_parameters.get("tracked_target_role")
        and roll_type in {"hit", "wound"}
        and _trigger_supports_tracked_target_roll_type(
            trigger_parameters=trigger_parameters,
            roll_type=roll_type,
        )
    )


def _trigger_supports_tracked_target_roll_type(
    *,
    trigger_parameters: Mapping[str, object],
    roll_type: object,
) -> bool:
    if type(roll_type) is not str:
        return False
    single_roll_type = trigger_parameters.get("roll_type")
    if single_roll_type == roll_type:
        return True
    roll_types = trigger_parameters.get("roll_types")
    if roll_types is None:
        return False
    if type(roll_types) is not tuple:
        raise GameLifecycleError("Catalog tracked-target roll_types must be a tuple.")
    return roll_type in roll_types


def _tracked_target_supported_attack_roll_pairs_for_clause(
    clause: RuleClause,
) -> tuple[tuple[str, str], ...]:
    if type(clause) is not RuleClause:
        raise GameLifecycleError("Tracked-target attack-roll pair derivation requires RuleClause.")
    if clause_is_tracked_target_weapon_grant(clause):
        weapon_scope = _weapon_scope_parameter(parameter_payload(clause.effects[0].parameters))
        return tuple(
            (attack_kind, "attack_sequence.hit")
            for attack_kind in ("melee", "ranged")
            if weapon_scope in {"all", attack_kind}
        )
    if not _clause_is_supported_tracked_target_reroll(clause):
        return ()
    trigger = clause.trigger
    if trigger is None or trigger.kind is not RuleTriggerKind.DICE_ROLL:
        return ()
    trigger_parameters = parameter_payload(trigger.parameters)
    attack_kind = trigger_parameters.get("attack_kind")
    if attack_kind not in {"melee", "ranged"}:
        return ()
    supported: set[tuple[str, str]] = set()
    for effect in clause.effects:
        if effect.kind is not RuleEffectKind.REROLL_PERMISSION:
            continue
        if not _effect_is_supported_tracked_target_reroll(
            effect,
            trigger_parameters=trigger_parameters,
        ):
            continue
        roll_type = parameter_payload(effect.parameters).get("roll_type")
        if roll_type == "hit":
            supported.add((str(attack_kind), "attack_sequence.hit"))
        elif roll_type == "wound":
            supported.add((str(attack_kind), "attack_sequence.wound"))
    return tuple(
        (candidate_attack_kind, candidate_roll_type)
        for candidate_attack_kind in ("melee", "ranged")
        for candidate_roll_type in ("attack_sequence.hit", "attack_sequence.wound")
        if (candidate_attack_kind, candidate_roll_type) in supported
    )


def _clause_is_supported_tracked_target_destroyed_reselect(clause: RuleClause) -> bool:
    if type(clause) is not RuleClause:
        raise GameLifecycleError("Tracked-target consumer classification requires RuleClause.")
    if not clause.is_supported:
        return False
    trigger = clause.trigger
    if trigger is None or trigger.kind is not RuleTriggerKind.UNIT_DESTROYED:
        return False
    trigger_parameters = parameter_payload(trigger.parameters)
    if trigger_parameters.get("timing_window") != "tracked_target_destroyed":
        return False
    if trigger_parameters.get("tracked_target_owner") not in {"this_model", "this_unit"}:
        return False
    if trigger_parameters.get("tracked_target_role") not in {"prey", "quarry"}:
        return False
    if not any(
        _condition_is_tracked_target_destroyed_constraint(condition)
        for condition in clause.conditions
    ):
        return False
    if not _clause_is_supported_tracked_target_selection(clause):
        return False
    selection_effect = next(
        effect for effect in clause.effects if effect.kind is RuleEffectKind.SELECT_TRACKED_TARGET
    )
    parameters = parameter_payload(selection_effect.parameters)
    return (
        parameters.get("replacement") is True
        and parameters.get("tracked_target_owner") == trigger_parameters.get("tracked_target_owner")
        and parameters.get("tracked_target_role") == trigger_parameters.get("tracked_target_role")
    )


def _condition_is_tracked_target_destroyed_constraint(condition: RuleCondition) -> bool:
    if condition.kind is not RuleConditionKind.TARGET_CONSTRAINT:
        return False
    parameters = parameter_payload(condition.parameters)
    return (
        parameters.get("relationship") == "tracked_target_destroyed"
        and parameters.get("target_reference") == "tracked_target"
        and parameters.get("tracked_target_owner") in {"this_model", "this_unit"}
        and parameters.get("tracked_target_role") in {"prey", "quarry"}
        and parameters.get("gate_subject") == "destroyed_unit"
    )


def _clause_is_supported_first_death_return(clause: RuleClause) -> bool:
    if type(clause) is not RuleClause:
        raise GameLifecycleError("First-death return classification requires RuleClause.")
    if not clause.is_supported:
        return False
    trigger = clause.trigger
    if trigger is None or trigger.kind not in {
        RuleTriggerKind.MODEL_DESTROYED,
        RuleTriggerKind.UNIT_DESTROYED,
    }:
        return False
    trigger_parameters = parameter_payload(trigger.parameters)
    if trigger_parameters.get("event_order") != "first":
        return False
    if trigger_parameters.get("resolution_timing") != "phase_end":
        return False
    if trigger_parameters.get("timing_window") != "phase_end_after_destroyed":
        return False
    if not _clause_has_supported_first_death_frequency_limit(clause):
        return False
    if not _clause_has_supported_first_death_roll_gate(clause):
        return False
    if not _clause_has_engagement_range_return_restriction(clause):
        return False
    return_effects = tuple(
        effect for effect in clause.effects if effect.kind is RuleEffectKind.RETURN_DESTROYED_TARGET
    )
    if len(return_effects) != 1 or len(clause.effects) != 1:
        return False
    return _first_death_return_target_shape_matches(
        clause=clause,
        effect=return_effects[0],
        trigger_parameters=trigger_parameters,
    ) and _effect_is_supported_first_death_return(return_effects[0])


def _clause_has_supported_first_death_frequency_limit(clause: RuleClause) -> bool:
    for condition in clause.conditions:
        if condition.kind is not RuleConditionKind.FREQUENCY_LIMIT:
            continue
        parameters = parameter_payload(condition.parameters)
        if (
            parameters.get("event") == "target_destroyed"
            and parameters.get("event_order") == "first"
            and parameters.get("scope") == "battle"
        ):
            return True
    return False


def _clause_has_supported_first_death_roll_gate(clause: RuleClause) -> bool:
    for condition in clause.conditions:
        if condition.kind is not RuleConditionKind.DICE_ROLL_GATE:
            continue
        parameters = parameter_payload(condition.parameters)
        roll_count = parameters.get("roll_count")
        success_threshold = parameters.get("success_threshold")
        if (
            parameters.get("comparison") == "greater_or_equal"
            and parameters.get("roll_expression") == "D6"
            and type(roll_count) is int
            and roll_count == 1
            and type(success_threshold) is int
            and 2 <= success_threshold <= 6
        ):
            return True
    return False


def _clause_has_engagement_range_return_restriction(clause: RuleClause) -> bool:
    for condition in clause.conditions:
        if condition.kind is not RuleConditionKind.DISTANCE_PREDICATE:
            continue
        parameters = parameter_payload(condition.parameters)
        if (
            parameters.get("predicate") == "within_engagement_range"
            and parameters.get("range_kind") == "engagement_range"
            and parameters.get("negated") is True
            and parameters.get("object_allegiance") == "enemy"
            and parameters.get("object_kind") == "unit"
            and parameters.get("object_quantity") == "one_or_more"
        ):
            return True
    return False


def _effect_is_supported_first_death_return(effect: RuleEffectSpec) -> bool:
    parameters = parameter_payload(effect.parameters)
    restore_mode = parameters.get("restore_wounds_mode")
    wounds_remaining = parameters.get("wounds_remaining")
    if (
        parameters.get("action") != "set_back_up"
        or parameters.get("placement_kind") != "battlefield_set_up"
        or parameters.get("placement_anchor") != "destroyed_position"
        or parameters.get("placement_preference") != "as_close_as_possible"
        or parameters.get("target_lifecycle") != "destroyed"
        or parameters.get("target_scope") not in {"destroyed_model", "destroyed_unit"}
    ):
        return False
    if restore_mode == "fixed_remaining":
        return type(wounds_remaining) is int and wounds_remaining > 0
    if restore_mode == "full_health":
        return wounds_remaining is None
    return False


def _first_death_return_target_shape_matches(
    *,
    clause: RuleClause,
    effect: RuleEffectSpec,
    trigger_parameters: Mapping[str, object],
) -> bool:
    if clause.trigger is None or clause.target is None:
        return False
    parameters = parameter_payload(effect.parameters)
    if clause.trigger.kind is RuleTriggerKind.MODEL_DESTROYED:
        return (
            trigger_parameters.get("destroyed_target") == "this_model"
            and clause.target.kind is RuleTargetKind.THIS_MODEL
            and parameters.get("target") == "this_model"
            and parameters.get("target_scope") == "destroyed_model"
        )
    if clause.trigger.kind is RuleTriggerKind.UNIT_DESTROYED:
        return (
            trigger_parameters.get("destroyed_target") == "this_unit"
            and clause.target.kind is RuleTargetKind.THIS_UNIT
            and parameters.get("target") == "this_unit"
            and parameters.get("target_scope") == "destroyed_unit"
        )
    return False


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
        if any(
            _clause_grants_advance_eligibility(clause, ability=requested_ability)
            for clause in _clauses_from_record(record)
        ):
            matching_records.append(record)
    return tuple(sorted(matching_records, key=lambda record: record.record_id))


def _matching_fall_back_eligibility_records(
    *,
    ability_indexes_by_player_id: Mapping[str, AbilityCatalogIndex],
    armies: tuple[ArmyDefinition, ...],
    context: FallBackEligibilityContext,
    ability: str,
) -> tuple[AbilityCatalogRecord, ...]:
    requested_ability = _validate_identifier("ability", ability)
    army = _army_for_player(armies, player_id=context.player_id)
    unit = _unit_in_army_by_id(army, unit_instance_id=context.unit_instance_id)
    index = ability_indexes_by_player_id.get(context.player_id)
    if index is None:
        raise GameLifecycleError("Catalog Fall Back eligibility index is missing player.")
    current_model_ids = _current_model_instance_ids_for_unit(state=context.state, unit=unit)
    matching_records: list[AbilityCatalogRecord] = []
    for record in _unit_scoped_generic_records(
        ability_index=index,
        unit=unit,
        current_model_instance_ids=current_model_ids,
        trigger_kind=TimingTriggerKind.PASSIVE_QUERY,
    ):
        if any(
            _clause_grants_fall_back_eligibility(clause, ability=requested_ability)
            for clause in _clauses_from_record(record)
        ):
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


def _clause_targets_attacker_status_unit(clause: RuleClause) -> bool:
    if type(clause) is not RuleClause:
        raise GameLifecycleError("Catalog rule consumer requires RuleClause values.")
    return clause.target is not None and clause.target.kind in {
        RuleTargetKind.FRIENDLY_UNIT,
        RuleTargetKind.SELECTED_UNIT,
        RuleTargetKind.THIS_MODEL,
        RuleTargetKind.THIS_UNIT,
    }


def _clause_targets_roll_reroll_unit(clause: RuleClause) -> bool:
    if _clause_targets_this_unit(clause):
        return True
    if type(clause) is not RuleClause:
        raise GameLifecycleError("Catalog rule consumer requires RuleClause values.")
    if _clause_targets_this_model(clause):
        return True
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


def _clause_is_supported_setup_reactive_shoot_charge(clause: RuleClause) -> bool:
    if type(clause) is not RuleClause:
        raise GameLifecycleError("Catalog rule consumer requires RuleClause values.")
    if clause.target is None or clause.target.kind is not RuleTargetKind.ENEMY_UNIT:
        return False
    trigger = clause.trigger
    if trigger is None or trigger.kind is not RuleTriggerKind.TIMING_WINDOW:
        return False
    trigger_parameters = parameter_payload(trigger.parameters)
    if trigger_parameters != {
        "edge": "end",
        "owner": "opponent",
        "phase": "movement",
        "timing_window": "end_opponent_movement_phase",
    }:
        return False
    if not _clause_has_selected_unit_setup_constraint(clause):
        return False
    if not _clause_has_selected_unit_this_model_distance(clause):
        return False
    actions = {
        _setup_reactive_action_token(effect): parameter_payload(effect.parameters)
        for effect in clause.effects
        if effect.kind is RuleEffectKind.OUT_OF_PHASE_ACTION
    }
    shoot = actions.get("shoot")
    charge = actions.get("charge")
    return (
        shoot is not None
        and shoot.get("action_group") == "setup_reactive_shoot_charge"
        and shoot.get("action_source") == "this_model"
        and shoot.get("target_reference") == "selected_unit"
        and shoot.get("eligible_target_required") is True
        and charge is not None
        and charge.get("action_group") == "setup_reactive_shoot_charge"
        and charge.get("action_source") == "this_model"
        and charge.get("target_reference") == "selected_unit"
        and charge.get("must_end_engaged_with_selected_unit") is True
        and charge.get("suppress_charge_bonus") is True
        and charge.get("suppressed_charge_bonus") == "fights_first"
    )


def _clause_has_selected_unit_setup_constraint(clause: RuleClause) -> bool:
    return any(
        condition.kind is RuleConditionKind.TARGET_CONSTRAINT
        and parameter_payload(condition.parameters)
        == {
            "relationship": "selected_unit_set_up_on_battlefield_this_phase",
            "gate_subject": "selected_unit",
        }
        for condition in clause.conditions
    )


def _clause_has_selected_unit_this_model_distance(clause: RuleClause) -> bool:
    for condition in clause.conditions:
        if condition.kind is not RuleConditionKind.DISTANCE_PREDICATE:
            continue
        parameters = parameter_payload(condition.parameters)
        if (
            parameters.get("predicate") == "within"
            and parameters.get("range_kind") == "numeric_range"
            and parameters.get("object_kind") == "model"
            and parameters.get("object_reference") == "this"
            and parameters.get("subject") == "selected_unit"
        ):
            distance = parameters.get("distance_inches")
            return (type(distance) is int or type(distance) is float) and distance > 0
    return False


def _setup_reactive_action_token(effect: RuleEffectSpec) -> str:
    parameters = parameter_payload(effect.parameters)
    action = parameters.get("action")
    return "" if type(action) is not str else _catalog_ir_lookup_token(action)


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


def _clause_is_supported_this_model_attack_roll_modifier(
    clause: RuleClause,
    effect: RuleEffectSpec,
) -> bool:
    if type(clause) is not RuleClause:
        raise GameLifecycleError("Catalog rule consumer classification requires RuleClause.")
    if type(effect) is not RuleEffectSpec:
        raise GameLifecycleError("Catalog rule consumer requires RuleEffectSpec values.")
    if not clause.is_supported:
        return False
    if clause.target is None or clause.target.kind is not RuleTargetKind.THIS_MODEL:
        return False
    if effect.kind is not RuleEffectKind.MODIFY_DICE_ROLL:
        return False
    parameters = parameter_payload(effect.parameters)
    roll_type = parameters.get("roll_type")
    if type(roll_type) is not str:
        return False
    if not _clause_has_roll_trigger(clause, roll_type=roll_type):
        return False
    return any(
        _condition_is_supported_this_model_attack_half_strength_gate(condition)
        for condition in clause.conditions
    )


def _condition_is_supported_this_model_attack_half_strength_gate(
    condition: RuleCondition,
) -> bool:
    if type(condition) is not RuleCondition:
        raise GameLifecycleError("Catalog rule consumer requires RuleCondition values.")
    if condition.kind is not RuleConditionKind.TARGET_CONSTRAINT:
        return False
    parameters = parameter_payload(condition.parameters)
    return (
        parameters.get("relationship") == "this_model_makes_attack"
        and parameters.get("gate_subject") == "attack_target"
        and parameters.get("target_allegiance") == "enemy"
        and parameters.get("target_constraint") == "target_not_below_half_strength"
    )


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
        if value is None:
            continue
        if type(value) is not tuple:
            raise GameLifecycleError("Catalog keyword-any condition must be a tuple.")
        required_keywords.extend(_keyword_tuple_from_any_parameter(value))
    return tuple(dict.fromkeys(required_keywords))


def _keyword_tuple_from_any_parameter(value: tuple[object, ...]) -> tuple[str, ...]:
    keywords = _validate_keyword_tokens("required_keyword_any", value)
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
    if clause.trigger is not None or _datasheet.clause_has_invalid_exact_datasheet_runtime_shape(
        clause
    ):
        return False
    return _clause_targets_this_unit(clause) or (
        clause.target is not None
        and clause.target.kind is RuleTargetKind.SELECTED_UNIT
        and _clause_has_leading_unit_relationship(clause)
    )


def _clause_is_named_weapon_ability_choice(clause: RuleClause) -> bool:
    if type(clause) is not RuleClause:
        raise GameLifecycleError("Catalog rule consumer requires RuleClause values.")
    if clause.trigger is None or clause.trigger.kind is not RuleTriggerKind.TIMING_WINDOW:
        return False
    trigger_parameters = parameter_payload(clause.trigger.parameters)
    if (
        trigger_parameters.get("edge") != "during"
        or trigger_parameters.get("owner") != "active_player"
        or trigger_parameters.get("phase") != BattlePhase.SHOOTING.value
    ):
        return False
    if (
        clause.duration is None
        or clause.duration.kind is not RuleDurationKind.UNTIL_TIMING_ENDPOINT
        or parameter_payload(clause.duration.parameters).get("endpoint") != "phase"
    ):
        return False
    if clause.target is None or clause.target.kind not in {
        RuleTargetKind.THIS_MODEL,
        RuleTargetKind.THIS_UNIT,
    }:
        return False
    if len(clause.effects) < 2:
        return False
    return all(_effect_is_named_weapon_ability_choice_option(effect) for effect in clause.effects)


def _effect_is_named_weapon_ability_choice_option(effect: RuleEffectSpec) -> bool:
    if type(effect) is not RuleEffectSpec:
        raise GameLifecycleError("Catalog rule consumer requires RuleEffectSpec values.")
    if effect.kind is not RuleEffectKind.GRANT_WEAPON_ABILITY:
        return False
    parameters = parameter_payload(effect.parameters)
    keyword = _weapon_keyword_from_parameters(parameters)
    return keyword is not None and _weapon_ability_choice_has_supported_runtime_shape(
        parameters,
        keyword=keyword,
    )


def _clause_is_supported_post_shoot_hit_target_status_denial(clause: RuleClause) -> bool:
    if type(clause) is not RuleClause:
        raise GameLifecycleError("Catalog rule consumer requires RuleClause values.")
    if clause.trigger is None or clause.trigger.kind is not RuleTriggerKind.TIMING_WINDOW:
        return False
    trigger_parameters = parameter_payload(clause.trigger.parameters)
    if (
        trigger_parameters.get("edge") != "after"
        or trigger_parameters.get("owner") != "active_player"
        or trigger_parameters.get("phase") != BattlePhase.SHOOTING.value
        or trigger_parameters.get("timing_window") != "just_after_friendly_unit_has_shot"
        or trigger_parameters.get("target_relationship") != "hit_by_those_attacks"
    ):
        return False
    if trigger_parameters.get("subject") not in {"this_model", "this_unit", "bearer"}:
        return False
    if (
        clause.duration is None
        or clause.duration.kind is not RuleDurationKind.UNTIL_TIMING_ENDPOINT
        or parameter_payload(clause.duration.parameters).get("endpoint") != "phase"
    ):
        return False
    if clause.target is None or clause.target.kind is not RuleTargetKind.ENEMY_UNIT:
        return False
    return sum(1 for effect in clause.effects if _effect_is_supported_status_denial(effect)) == 1


def _effect_is_supported_status_denial(effect: RuleEffectSpec) -> bool:
    if type(effect) is not RuleEffectSpec:
        raise GameLifecycleError("Catalog rule consumer requires RuleEffectSpec values.")
    if effect.kind is not RuleEffectKind.SET_CONTEXTUAL_STATUS:
        return False
    parameters = parameter_payload(effect.parameters)
    return (
        parameters.get("rules_context") == "status_denial"
        and parameters.get("operation") == "deny"
        and parameters.get("status") == "benefit_of_cover"
        and parameters.get("target_scope") in {"selected_unit", "models_in_selected_unit"}
    )


def _clause_is_supported_unit_move_completed_mortal_wounds(clause: RuleClause) -> bool:
    if type(clause) is not RuleClause:
        raise GameLifecycleError("Catalog rule consumer requires RuleClause values.")
    if not clause.is_supported:
        return False
    trigger = clause.trigger
    if trigger is None or trigger.kind is not RuleTriggerKind.TIMING_WINDOW:
        return False
    trigger_parameters = parameter_payload(trigger.parameters)
    if (
        trigger_parameters.get("edge") != "after"
        or trigger_parameters.get("phase") != BattlePhase.CHARGE.value
        or trigger_parameters.get("timing_window") != "charge_move_end"
        or trigger_parameters.get("subject") != "this_unit"
    ):
        return False
    if clause.target is None or clause.target.kind is not RuleTargetKind.ENEMY_UNIT:
        return False
    if not _clause_has_selected_enemy_unit_engagement_range_target(clause):
        return False
    return (
        len(clause.effects) == 1
        and len(
            tuple(
                effect
                for effect in clause.effects
                if _effect_is_supported_unit_move_completed_mortal_wounds(effect)
            )
        )
        == 1
    )


def _clause_has_selected_enemy_unit_engagement_range_target(clause: RuleClause) -> bool:
    if type(clause) is not RuleClause:
        raise GameLifecycleError("Catalog rule consumer requires RuleClause values.")
    for condition in clause.conditions:
        if condition.kind is not RuleConditionKind.DISTANCE_PREDICATE:
            continue
        parameters = parameter_payload(condition.parameters)
        if (
            parameters.get("predicate") == "within_engagement_range"
            and parameters.get("range_kind") == "engagement_range"
            and parameters.get("negated") is False
            and parameters.get("object_kind") == "unit"
            and parameters.get("object_reference") == "this"
        ):
            return True
    return False


def _effect_is_supported_unit_move_completed_mortal_wounds(effect: RuleEffectSpec) -> bool:
    if type(effect) is not RuleEffectSpec:
        raise GameLifecycleError("Catalog rule consumer requires RuleEffectSpec values.")
    if effect.kind is not RuleEffectKind.INFLICT_MORTAL_WOUNDS:
        return False
    parameters = parameter_payload(effect.parameters)
    success_threshold = parameters.get("success_threshold")
    return (
        parameters.get("damage_kind") == "mortal_wounds"
        and parameters.get("mortal_wounds_expression") == "D3"
        and parameters.get("roll_count") == 1
        and parameters.get("roll_count_scope") == "each_model_in_this_unit"
        and parameters.get("roll_expression") == "D6"
        and type(success_threshold) is int
        and 2 <= success_threshold <= 6
        and parameters.get("target_scope") == "selected_enemy_unit"
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
    if parameters.get("target_reference") == "tracked_target":
        return False
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
    if parameters.get("target_reference") == "tracked_target":
        return None
    roll_type = parameters.get("roll_type")
    if type(roll_type) is not str:
        return None
    return _CATALOG_IR_ROLL_REROLL_CONSUMER_IDS.get(_catalog_ir_lookup_token(roll_type))


def _roll_modifier_consumer_id_for_effect(effect: RuleEffectSpec) -> str | None:
    if type(effect) is not RuleEffectSpec:
        raise GameLifecycleError("Catalog rule consumer requires RuleEffectSpec values.")
    if effect.kind is not RuleEffectKind.MODIFY_DICE_ROLL:
        return None
    parameters = parameter_payload(effect.parameters)
    roll_type = parameters.get("roll_type")
    if type(roll_type) is not str:
        return None
    return _CATALOG_IR_ROLL_MODIFIER_CONSUMER_IDS.get(_catalog_ir_lookup_token(roll_type))


def _weapon_keyword_grant_consumer_ids_for_effect(effect: RuleEffectSpec) -> tuple[str, ...]:
    if type(effect) is not RuleEffectSpec:
        raise GameLifecycleError("Catalog rule consumer requires RuleEffectSpec values.")
    if effect.kind is not RuleEffectKind.GRANT_WEAPON_ABILITY:
        return ()
    parameters = parameter_payload(effect.parameters)
    keyword = _weapon_keyword_from_parameters(parameters)
    if keyword is None:
        return ()
    if _weapon_ability_choice_has_supported_runtime_shape(parameters, keyword=keyword):
        return (
            CATALOG_IR_NAMED_WEAPON_ABILITY_CHOICE_CONSUMER_ID,
            CATALOG_IR_WEAPON_KEYWORD_GRANT_CONSUMER_ID,
            _catalog_ir_weapon_keyword_grant_consumer_id(keyword.value),
        )
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


def _effect_is_minimum_unmodified_hit_success(effect: RuleEffectSpec) -> bool:
    if type(effect) is not RuleEffectSpec:
        raise GameLifecycleError("Catalog rule consumer requires RuleEffectSpec values.")
    if effect.kind is not RuleEffectKind.SET_CONTEXTUAL_STATUS:
        return False
    parameters = parameter_payload(effect.parameters)
    threshold = parameters.get("minimum_unmodified_success")
    return (
        parameters.get("status") == "minimum_unmodified_hit_success"
        and parameters.get("roll_type") == "hit"
        and parameters.get("attack_role") == "attacker"
        and type(threshold) is int
        and 2 <= threshold <= 6
    )


def _clause_grants_advance_eligibility(clause: RuleClause, *, ability: str) -> bool:
    if type(clause) is not RuleClause:
        raise GameLifecycleError("Catalog advance eligibility requires RuleClause.")
    requested_ability = _validate_identifier("ability", ability)
    return _clause_targets_this_unit(clause) and any(
        _effect_grants_ability(effect, ability=requested_ability) for effect in clause.effects
    )


def _clause_grants_fall_back_eligibility(clause: RuleClause, *, ability: str) -> bool:
    if type(clause) is not RuleClause:
        raise GameLifecycleError("Catalog Fall Back eligibility requires RuleClause.")
    requested_ability = _validate_identifier("ability", ability)
    return _clause_targets_this_unit(clause) and any(
        _effect_grants_ability(effect, ability=requested_ability) for effect in clause.effects
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


def _fall_back_eligibility_consumer_id_for_effect(effect: RuleEffectSpec) -> str | None:
    if type(effect) is not RuleEffectSpec:
        raise GameLifecycleError("Catalog rule consumer requires RuleEffectSpec values.")
    if effect.kind is not RuleEffectKind.GRANT_ABILITY:
        return None
    parameters = parameter_payload(effect.parameters)
    ability = parameters.get("ability")
    if type(ability) is not str:
        return None
    return _CATALOG_IR_FALL_BACK_ELIGIBILITY_GRANT_CONSUMER_IDS.get(
        _catalog_ir_lookup_token(ability)
    )


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
        mortal_wounds=_optional_bool_parameter(parameters, key="mortal_wounds"),
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
    unit: UnitInstance,
    clause: RuleClause,
    effect_index: int,
    effect: RuleEffectSpec,
) -> CatalogWeaponKeywordGrant | None:
    if type(record) is not AbilityCatalogRecord:
        raise GameLifecycleError("Catalog weapon keyword grant requires an ability record.")
    _validate_unit(unit)
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
        tracked_target=tracked_target_weapon_grant_from_clause(
            clause=clause,
            source_rule_id=record.definition.source_id,
        ),
        source_unit_instance_id=unit.unit_instance_id,
        requires_source_leading=_clause_has_leading_unit_relationship(clause),
    )


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


def _weapon_ability_choice_has_supported_runtime_shape(
    parameters: Mapping[str, object],
    *,
    keyword: WeaponKeyword,
) -> bool:
    if parameters.get("selection_kind") != "select_one":
        return False
    for key in ("selection_group_id", "selection_option_id", "target_scope"):
        if type(parameters.get(key)) is not str:
            return False
    selection_index = parameters.get("selection_option_index")
    if type(selection_index) is not int or selection_index < 1:
        return False
    if _optional_named_weapon_names(parameters) is None:
        return False
    if _optional_named_weapon_choice_target_scope(parameters) is None:
        return False
    if keyword in _VALUE_REQUIRED_WEAPON_KEYWORDS:
        if keyword is WeaponKeyword.SUSTAINED_HITS:
            return _optional_weapon_ability_choice_value_parameter(parameters) is not None
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
            _required_weapon_ability_choice_value_parameter(
                parameters,
                key="weapon_ability_value",
            )
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
    return None


def _weapon_scope_from_token(value: object) -> str:
    if type(value) is not str:
        raise GameLifecycleError("Catalog weapon keyword grant weapon_scope must be a string.")
    if value not in {"all", "melee", "ranged"}:
        raise GameLifecycleError("Unsupported catalog weapon keyword grant scope.")
    return value


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


def _validate_positive_int(field_name: str, value: object) -> int:
    if type(value) is not int or value < 1:
        raise GameLifecycleError(f"Catalog rule parameter {field_name} must be a positive integer.")
    return value


def _optional_positive_int_parameter(parameters: Mapping[str, object], *, key: str) -> int | None:
    value = parameters.get(key)
    if value is None:
        return None
    if type(value) is not int or value < 1:
        raise GameLifecycleError(f"Catalog rule parameter {key} must be a positive integer.")
    return value


def _optional_bool_parameter(parameters: Mapping[str, object], *, key: str) -> bool:
    value = parameters.get(key)
    if value is None:
        return False
    if type(value) is not bool:
        raise GameLifecycleError(f"Catalog rule parameter {key} must be a bool.")
    return value


def _required_string_parameter(parameters: Mapping[str, object], *, key: str) -> str:
    value = parameters.get(key)
    if type(value) is not str:
        raise GameLifecycleError(f"Catalog rule parameter {key} must be a string.")
    return _validate_identifier(key, value)


def _required_weapon_ability_choice_value_parameter(
    parameters: Mapping[str, object],
    *,
    key: str,
) -> int | str:
    value = _optional_weapon_ability_choice_value_parameter(parameters)
    if value is None:
        raise GameLifecycleError(f"Catalog rule parameter {key} must be positive or D3.")
    return value


def _optional_weapon_ability_choice_value_parameter(
    parameters: Mapping[str, object],
) -> int | str | None:
    value = parameters.get("weapon_ability_value")
    if value is None:
        return None
    return _validate_weapon_ability_choice_value(value)


def _validate_weapon_ability_choice_value(value: object) -> int | str:
    if type(value) is int and value >= 1:
        return value
    if type(value) is str and value == "D3":
        return value
    raise GameLifecycleError("Catalog rule weapon ability value must be positive or D3.")


def _optional_named_weapon_names(parameters: Mapping[str, object]) -> tuple[str, ...] | None:
    names = parameters.get("weapon_names")
    if type(names) is tuple:
        return _validate_named_weapon_names(cast(tuple[object, ...], names))
    if names is not None:
        raise GameLifecycleError(
            "Catalog named weapon ability choice weapon_names must be a tuple."
        )
    name = parameters.get("weapon_name")
    if type(name) is str:
        return _validate_named_weapon_names((name,))
    return None


def _weapon_names_from_parameters(parameters: Mapping[str, object]) -> tuple[str, ...]:
    names = _optional_named_weapon_names(parameters)
    if names is None:
        raise GameLifecycleError("Catalog named weapon ability choice requires weapon names.")
    return names


def _validate_named_weapon_names(values: object) -> tuple[str, ...]:
    if type(values) is not tuple:
        raise GameLifecycleError("Catalog named weapon names must be a tuple.")
    names: list[str] = []
    seen: set[str] = set()
    for value in cast(tuple[object, ...], values):
        if type(value) is not str:
            raise GameLifecycleError("Catalog named weapon names must contain strings.")
        name = value.strip()
        if not name:
            raise GameLifecycleError("Catalog named weapon names must not be empty.")
        token = _weapon_name_match_token(name)
        if token in seen:
            raise GameLifecycleError("Catalog named weapon names must not duplicate names.")
        seen.add(token)
        names.append(name)
    if not names:
        raise GameLifecycleError("Catalog named weapon names must not be empty.")
    return tuple(names)


def _optional_named_weapon_choice_target_scope(
    parameters: Mapping[str, object],
) -> str | None:
    value = parameters.get("target_scope")
    if type(value) is not str:
        return None
    return _validate_named_weapon_choice_target_scope(value)


def _validate_named_weapon_choice_target_scope(value: object) -> str:
    if type(value) is not str:
        raise GameLifecycleError(
            "Catalog named weapon ability choice target_scope must be a string."
        )
    scope = value.strip()
    if scope in {"this_model", "models_in_this_unit"}:
        return scope
    raise GameLifecycleError("Unsupported catalog named weapon ability choice target scope.")


def _validate_named_weapon_choice_option(
    option: object,
) -> CatalogNamedWeaponAbilityChoiceOption:
    if type(option) is not CatalogNamedWeaponAbilityChoiceOption:
        raise GameLifecycleError("Catalog named weapon ability choice requires option values.")
    return option


def _validate_post_shoot_hit_target_status_option(
    option: object,
) -> CatalogPostShootHitTargetStatusOption:
    if type(option) is not CatalogPostShootHitTargetStatusOption:
        raise GameLifecycleError("Catalog post-shoot status requires option values.")
    return option


def _validate_unit_move_completed_mortal_wounds_target_option(
    option: object,
) -> CatalogUnitMoveCompletedMortalWoundsTargetOption:
    if type(option) is not CatalogUnitMoveCompletedMortalWoundsTargetOption:
        raise GameLifecycleError(
            "Catalog move-completed mortal wounds requires target option values."
        )
    return option


def _unit_move_completed_decisions(context: UnitMoveCompletedContext) -> DecisionController:
    if type(context) is not UnitMoveCompletedContext:
        raise GameLifecycleError("Catalog move-completed mortal wounds requires context.")
    if context.decisions is None:
        raise GameLifecycleError(
            "Catalog move-completed mortal wounds requires DecisionController context."
        )
    return context.decisions


def _catalog_mortal_wounds_dice_expression(token: str) -> DiceExpression:
    normalized = _string_identifier("mortal_wounds_expression", token).upper()
    if normalized == "D3":
        return DiceExpression(quantity=1, sides=3)
    raise GameLifecycleError("Unsupported catalog move-completed mortal wounds expression.")


def _weapon_name_match_token(value: str) -> str:
    if type(value) is not str:
        raise GameLifecycleError("Catalog named weapon name must be a string.")
    stripped = value.strip()
    if not stripped:
        raise GameLifecycleError("Catalog named weapon name must not be empty.")
    return " ".join(stripped.casefold().replace("-", " ").split())


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
        if (
            parameters.get("movement_mode") == "consolidate"
            and parameters.get("operation") == "set_maximum"
        ):
            return (_datasheet.CATALOG_IR_FIGHT_ACTIVATION_MOVEMENT_DISTANCE_CONSUMER_ID,)
        return (_catalog_ir_characteristic_modifier_consumer_id(Characteristic.MOVEMENT),)
    if effect.kind is RuleEffectKind.OUT_OF_PHASE_ACTION:
        parameters = parameter_payload(effect.parameters)
        if _fight_end_move.effect_is_fight_end_triggered_movement(effect):
            return (_fight_end_move.CATALOG_IR_FIGHT_END_TRIGGERED_MOVEMENT_CONSUMER_ID,)
        if parameters.get("action_group") == "setup_reactive_shoot_charge" and parameters.get(
            "action"
        ) in {"shoot", "charge"}:
            return (CATALOG_IR_SETUP_REACTIVE_SHOOT_CHARGE_CONSUMER_ID,)
        return ()
    if (
        effect.kind is RuleEffectKind.PLACEMENT_PERMISSION
        and _prebattle_redeploy.effect_is_prebattle_redeploy_permission(effect)
    ):
        return (CATALOG_IR_PREBATTLE_REDEPLOY_PERMISSION_CONSUMER_ID,)
    if effect.kind is RuleEffectKind.GRANT_WEAPON_ABILITY:
        consumer_ids = _weapon_keyword_grant_consumer_ids_for_effect(effect)
        if consumer_ids:
            return consumer_ids
        keyword = _string_parameter(parameters, key="weapon_ability")
        return (
            CATALOG_IR_WEAPON_KEYWORD_GRANT_CONSUMER_ID,
            _catalog_ir_weapon_keyword_grant_consumer_id(keyword),
        )
    if effect.kind is RuleEffectKind.GRANT_ABILITY and _effect_is_feel_no_pain_grant(effect):
        return (CATALOG_IR_FEEL_NO_PAIN_SOURCE_CONSUMER_ID,)
    contextual_hook_ids = _contextual.hook_ids_for_effect(effect)
    if contextual_hook_ids:
        return contextual_hook_ids
    if _effect_is_minimum_unmodified_hit_success(effect):
        return (CATALOG_IR_MINIMUM_UNMODIFIED_HIT_SUCCESS_CONSUMER_ID,)
    if effect.kind is RuleEffectKind.RESTORE_LOST_WOUNDS:
        return (CATALOG_IR_DESTROYED_UNIT_RESTORE_LOST_WOUNDS_CONSUMER_ID,)
    if effect.kind in {
        RuleEffectKind.GRANT_ABILITY,
        RuleEffectKind.PLACEMENT_PERMISSION,
    }:
        return _catalog_ir_rule_exception_hook_ids(effect.kind, parameters)
    return ()


def catalog_rule_ir_consumer_ids_for_effect(
    effect: RuleEffectSpec,
) -> tuple[str, ...]:
    """Return stable consumer identities capable of hosting one effect."""
    if type(effect) is not RuleEffectSpec:
        raise GameLifecycleError("Catalog rule effect consumption requires RuleEffectSpec.")
    if effect.kind is RuleEffectKind.MOVEMENT_TRANSIT_PERMISSION:
        return (CATALOG_IR_MOVEMENT_TRANSIT_PERMISSION_CONSUMER_ID,)
    return _catalog_ir_hook_ids_for_effect(effect)


def _catalog_ir_roll_modifier_hook_ids(parameters: Mapping[str, object]) -> tuple[str, ...]:
    roll_type = _string_parameter(parameters, key="roll_type")
    consumer_id = _CATALOG_IR_ROLL_MODIFIER_CONSUMER_IDS.get(_catalog_ir_lookup_token(roll_type))
    if consumer_id is None:
        return ()
    return (consumer_id,)


def _catalog_ir_roll_reroll_hook_ids(parameters: Mapping[str, object]) -> tuple[str, ...]:
    if parameters.get("target_reference") == "tracked_target":
        return ()
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


def _validate_non_empty_text(field_name: str, value: object) -> str:
    if type(field_name) is not str or not field_name:
        raise GameLifecycleError("Catalog rule text validation requires a field name.")
    if type(value) is not str:
        raise GameLifecycleError(f"Catalog rule {field_name} must be a string.")
    stripped = value.strip()
    if not stripped:
        raise GameLifecycleError(f"Catalog rule {field_name} must not be empty.")
    return stripped


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


def _has_fall_back_eligibility_records(
    ability_indexes_by_player_id: Mapping[str, AbilityCatalogIndex],
    *,
    ability: str,
) -> bool:
    requested_ability = _validate_identifier("ability", ability)
    return any(
        _record_can_grant_fall_back_eligibility(record, ability=requested_ability)
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


def _has_catalog_named_weapon_ability_choice_records(
    ability_indexes_by_player_id: Mapping[str, AbilityCatalogIndex],
) -> bool:
    return any(
        _record_can_select_catalog_named_weapon_ability(record)
        for index in ability_indexes_by_player_id.values()
        for record in index.all_records()
    )


def _has_catalog_post_shoot_hit_target_status_records(
    ability_indexes_by_player_id: Mapping[str, AbilityCatalogIndex],
) -> bool:
    return any(
        _record_can_select_catalog_post_shoot_hit_target_status(record)
        for index in ability_indexes_by_player_id.values()
        for record in index.all_records()
    )


def _has_catalog_unit_move_completed_mortal_wounds_records(
    ability_indexes_by_player_id: Mapping[str, AbilityCatalogIndex],
) -> bool:
    return any(
        _record_can_select_catalog_unit_move_completed_mortal_wounds_target(record)
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


def _record_can_select_catalog_named_weapon_ability(record: AbilityCatalogRecord) -> bool:
    if type(record) is not AbilityCatalogRecord:
        raise GameLifecycleError("Catalog named weapon ability choices require ability records.")
    if record.definition.handler_id != GENERIC_RULE_IR_ABILITY_HANDLER_ID:
        return False
    return any(
        _clause_is_named_weapon_ability_choice(clause) for clause in _clauses_from_record(record)
    )


def _record_can_select_catalog_post_shoot_hit_target_status(
    record: AbilityCatalogRecord,
) -> bool:
    if type(record) is not AbilityCatalogRecord:
        raise GameLifecycleError("Catalog post-shoot status choices require ability records.")
    if record.definition.handler_id != GENERIC_RULE_IR_ABILITY_HANDLER_ID:
        return False
    return any(
        _clause_is_supported_post_shoot_hit_target_status_denial(clause)
        for clause in _clauses_from_record(record)
    )


def _record_can_select_catalog_unit_move_completed_mortal_wounds_target(
    record: AbilityCatalogRecord,
) -> bool:
    if type(record) is not AbilityCatalogRecord:
        raise GameLifecycleError(
            "Catalog move-completed mortal wounds choices require ability records."
        )
    if record.definition.handler_id != GENERIC_RULE_IR_ABILITY_HANDLER_ID:
        return False
    return any(
        _clause_is_supported_unit_move_completed_mortal_wounds(clause)
        for clause in _clauses_from_record(record)
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
    return any(
        _clause_grants_advance_eligibility(clause, ability=ability)
        for clause in _clauses_from_record(record)
    )


def _record_can_grant_fall_back_eligibility(
    record: AbilityCatalogRecord,
    *,
    ability: str,
) -> bool:
    if type(record) is not AbilityCatalogRecord:
        raise GameLifecycleError("Catalog Fall Back eligibility requires ability records.")
    if record.definition.handler_id != GENERIC_RULE_IR_ABILITY_HANDLER_ID:
        return False
    return any(
        _clause_grants_fall_back_eligibility(clause, ability=ability)
        for clause in _clauses_from_record(record)
    )


def _army_for_player(armies: tuple[ArmyDefinition, ...], *, player_id: str) -> ArmyDefinition:
    requested_player_id = _validate_identifier("player_id", player_id)
    for army in armies:
        if army.player_id == requested_player_id:
            return army
    raise GameLifecycleError("Catalog advance eligibility player army is unknown.")


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
