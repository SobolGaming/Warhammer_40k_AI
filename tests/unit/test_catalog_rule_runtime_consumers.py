from __future__ import annotations

import json
import math
from collections.abc import Mapping
from dataclasses import replace
from typing import Any, cast

import pytest

from warhammer40k_core.core.army_catalog import ArmyCatalog
from warhammer40k_core.core.attributes import Characteristic, CharacteristicValue
from warhammer40k_core.core.dice import DiceExpression, RerollComponentSelectionPolicy
from warhammer40k_core.core.ruleset_descriptor import (
    BattlePhaseKind,
    FightEligibilityKind,
    FightOrderingBandKind,
    FightPhaseStepKind,
    FightTypeKind,
    ReserveDestructionTimingKind,
    RulesetDescriptor,
    TerrainFeatureKind,
)
from warhammer40k_core.core.terrain_display import TerrainDisplayGeometry
from warhammer40k_core.core.weapon_profiles import (
    AttackProfile,
    DamageProfile,
    RangeProfile,
    WeaponKeyword,
    WeaponProfile,
)
from warhammer40k_core.engine import catalog_battle_shock_runtime as battle_shock_runtime
from warhammer40k_core.engine import (
    catalog_command_point_runtime as command_point_runtime,
)
from warhammer40k_core.engine.abilities import (
    GENERIC_RULE_IR_ABILITY_HANDLER_ID,
    AbilityCatalogIndex,
    AbilityCatalogRecord,
    AbilityDefinition,
    AbilitySourceKind,
    AbilityTimingDescriptor,
    ability_record_is_active_generic_rule_ir,
)
from warhammer40k_core.engine.advance_eligibility_hooks import AdvanceEligibilityContext
from warhammer40k_core.engine.allocated_attack_damage_modifiers import (
    AllocatedAttackDamageModifierContext,
)
from warhammer40k_core.engine.army_mustering import (
    ArmyDefinition,
    ArmyMusterRequest,
    EnhancementAssignment,
    muster_army,
)
from warhammer40k_core.engine.attack_sequence import AttackSequence, AttackSequenceStep
from warhammer40k_core.engine.attack_sequence_completion_hooks import (
    AttackSequenceCompletedContext,
)
from warhammer40k_core.engine.battle_shock import (
    BattleShockTestReason,
    BattleShockTestRequest,
)
from warhammer40k_core.engine.battle_shock_hooks import (
    BattleShockHookRegistry,
    BattleShockRerollPermissionContext,
)
from warhammer40k_core.engine.battlefield_state import (
    BattlefieldPlacementKind,
    BattlefieldRuntimeState,
    BattlefieldScenario,
    ModelPlacement,
    PlacedArmy,
    UnitPlacement,
    geometry_model_for_placement,
)
from warhammer40k_core.engine.catalog_any_phase_once_per_battle import (
    CatalogAnyPhaseOncePerBattleRuntime,
)
from warhammer40k_core.engine.catalog_attack_condition_classification import (
    clause_effect_is_supported_this_model_attack_roll_modifier,
)
from warhammer40k_core.engine.catalog_battle_shock_runtime import (
    CatalogBattleShockRerollRuntime,
    catalog_battle_shock_hook_bindings,
)
from warhammer40k_core.engine.catalog_charge_roll_modifiers import (
    clause_effect_is_supported_charge_roll_modifier,
)
from warhammer40k_core.engine.catalog_command_point_runtime import (
    CATALOG_IR_COMMAND_POINT_GAIN_EVENT,
    CATALOG_IR_COMMAND_POINT_LEADERSHIP_TEST_EVENT,
    CATALOG_IR_COMMAND_POINT_PHASE_GAIN_EVENT,
    CATALOG_IR_STRATAGEM_COST_CHOICE_EVENT,
    CatalogCommandPointRuntime,
)
from warhammer40k_core.engine.catalog_command_point_support import (
    CATALOG_IR_COMMAND_POINT_GAIN_CONSUMER_ID,
    CATALOG_IR_STRATAGEM_COST_MODIFIER_CONSUMER_ID,
)
from warhammer40k_core.engine.catalog_datasheet_rule_runtime import CatalogDatasheetRuleRuntime
from warhammer40k_core.engine.catalog_desperate_escape import (
    CATALOG_FORCED_DESPERATE_ESCAPE_SOURCE_KIND,
    catalog_forced_desperate_escape_sources_for_unit,
)
from warhammer40k_core.engine.catalog_fight_end_triggered_movement_runtime import (
    CATALOG_FIGHT_END_TRIGGERED_MOVEMENT_ROLL_TYPE,
    CatalogFightEndTriggeredMovementRuntime,
    catalog_fight_end_triggered_movement_hook_bindings,
)
from warhammer40k_core.engine.catalog_fight_end_triggered_movement_support import (
    CATALOG_IR_FIGHT_END_TRIGGERED_MOVEMENT_CONSUMER_ID,
)
from warhammer40k_core.engine.catalog_modifier_ignore import (
    CATALOG_IR_MODIFIER_IGNORE_PERMISSION_CONSUMER_ID,
    CatalogModifierIgnorePermission,
    ModifierIgnoreKind,
    catalog_modifier_ignore_permissions_for_unit,
    clause_is_modifier_ignore_permission,
)
from warhammer40k_core.engine.catalog_movement_end_reactive_normal_move_runtime import (
    CatalogMovementEndReactiveNormalMoveRuntime,
)
from warhammer40k_core.engine.catalog_movement_end_reactive_normal_move_support import (
    CATALOG_IR_MOVEMENT_END_REACTIVE_NORMAL_MOVE_CONSUMER_ID,
)
from warhammer40k_core.engine.catalog_once_per_battle_runtime import (
    CATALOG_ONCE_PER_BATTLE_ABILITY_ACTIVATED_EVENT,
    CATALOG_ONCE_PER_BATTLE_ABILITY_DECLINED_EVENT,
    CatalogOncePerBattleRuntime,
)
from warhammer40k_core.engine.catalog_post_shoot_selected_target_support import (
    post_shoot_selected_target_effect_attack_role,
    post_shoot_selected_target_effect_clause_is_supported,
    post_shoot_selected_target_effect_clauses_after,
    post_shoot_selected_target_pair_is_supported,
)
from warhammer40k_core.engine.catalog_reserve_arrival_restrictions import (
    CatalogReserveArrivalRestrictionRuntime,
)
from warhammer40k_core.engine.catalog_rule_consumption import (
    CATALOG_IR_BATTLE_SHOCK_REROLL_CONSUMER_ID,
    CATALOG_IR_CHARGE_ROLL_CONSUMER_ID,
    CATALOG_IR_POST_SHOOT_HIT_TARGET_EFFECT_CONSUMER_ID,
    CATALOG_IR_SELECTED_TARGET_EFFECT_CONSUMER_ID,
    CatalogAdvanceEligibilityRuntime,
    CatalogFallBackEligibilityRuntime,
    CatalogNamedWeaponAbilityChoiceGroup,
    CatalogNamedWeaponAbilityChoiceOption,
    CatalogPostShootHitTargetStatusGroup,
    CatalogPostShootHitTargetStatusOption,
    CatalogRuleIrHookDefinition,
    CatalogUnitMoveCompletedMortalWoundsGroup,
    CatalogUnitMoveCompletedMortalWoundsTargetOption,
    catalog_charge_roll_modifiers_for_unit,
    catalog_rule_clauses_from_record,
    catalog_rule_ir_consumer_ids_for_effect,
    catalog_rule_ir_consumers_for_rule,
    catalog_rule_ir_hook_ids_for_rule,
)
from warhammer40k_core.engine.catalog_rule_selected_target_classification import (
    fight_start_selected_target_effect_clause_ids,
    post_shoot_hit_target_effect_clause_ids,
)
from warhammer40k_core.engine.catalog_selected_target_effects import (
    CATALOG_POST_SHOOT_HIT_TARGET_EFFECT_SELECTED_EVENT,
    CATALOG_SELECTED_TARGET_EFFECT_SELECTED_EVENT,
    CatalogSelectedTargetEffectRuntime,
    apply_catalog_post_shoot_hit_target_effect_result,
)
from warhammer40k_core.engine.catalog_selected_target_effects_support import (
    active_player_id,
    any_models_satisfy_distance,
    battle_phase_kind,
    catalog_selected_target_clauses_from_record,
    clause_is_fight_start_selection,
    clause_is_post_shoot_hit_target_selection,
    effect_target_unit_ids,
    effect_with_selected_target,
    eligible_selection_target_unit_ids,
    has_fight_start_selected_target_records,
    has_post_shoot_hit_target_effect_records,
    payload_effect_records,
    payload_int,
    payload_object,
    payload_string,
    payload_string_tuple,
    record_has_supported_fight_start_selected_target_effect,
    records_for_timing,
    required_keywords_for_clause,
    runtime_clause_id_from_record,
    selected_effect_clauses_after,
    selected_payload,
    selected_target_status_gate_allows,
    selection_source_model_ids,
    timing_window_id,
    validate_effect_record_tuple,
    validate_identifier_tuple,
)
from warhammer40k_core.engine.catalog_selected_target_pair_support import (
    fight_start_selected_target_selection_is_supported,
    selected_target_persisting_effect_clause_is_supported,
)
from warhammer40k_core.engine.catalog_selected_target_test_modifiers import (
    CATALOG_SELECTED_TARGET_TEST_MODIFIER_HOOK_ID,
)
from warhammer40k_core.engine.catalog_static_attack_modifier_runtime import (
    CatalogStaticAttackModifierRuntime,
)
from warhammer40k_core.engine.catalog_unit_move_completed_battle_shock_runtime import (
    catalog_unit_move_completed_battle_shock_hook_bindings,
)
from warhammer40k_core.engine.catalog_unit_move_completed_battle_shock_support import (
    CATALOG_IR_UNIT_MOVE_COMPLETED_BATTLE_SHOCK_CONSUMER_ID,
)
from warhammer40k_core.engine.decision_controller import DecisionController
from warhammer40k_core.engine.decision_request import DecisionOption, DecisionRequest
from warhammer40k_core.engine.decision_result import DecisionResult
from warhammer40k_core.engine.destruction_provenance import (
    DestructionSourceKind,
    ModelDestructionAttribution,
)
from warhammer40k_core.engine.dice import DiceRollManager
from warhammer40k_core.engine.effects import EffectExpiration, PersistingEffect
from warhammer40k_core.engine.event_log import JsonValue, validate_json_value
from warhammer40k_core.engine.faction_content.activation import RuntimeContentActivation
from warhammer40k_core.engine.faction_content.bundle import RuntimeContentBundle
from warhammer40k_core.engine.faction_content.events import (
    RuntimeContentEvent,
    RuntimeContentEventHandlerRegistry,
    RuntimeContentEventIndex,
    RuntimeContentEventResult,
)
from warhammer40k_core.engine.faction_content.warhammer_40000_11th.chaos_daemons import (
    july_2026_updates as chaos_daemons_july_updates,
)
from warhammer40k_core.engine.fall_back_hooks import FallBackEligibilityContext
from warhammer40k_core.engine.fight_activation_abilities import (
    FIGHT_ACTIVATION_MOVEMENT_DISTANCE_EFFECT_KIND,
    FightActivationAbilityContext,
)
from warhammer40k_core.engine.fight_order import (
    CHARGE_FIGHTS_FIRST_EFFECT_KIND,
    FightActivationSelection,
    FightPhaseState,
    FightsFirstRegistry,
)
from warhammer40k_core.engine.fight_phase_end_hooks import FightPhaseEndRequestContext
from warhammer40k_core.engine.fight_phase_start_hooks import (
    SELECT_FACTION_RULE_FIGHT_PHASE_START_OPTION_DECISION_TYPE,
    FightPhaseStartRequestContext,
    FightPhaseStartResultContext,
)
from warhammer40k_core.engine.game_state import GameState
from warhammer40k_core.engine.list_validation import (
    AttachmentDeclaration,
    DetachmentSelection,
    UnitMusterSelection,
)
from warhammer40k_core.engine.modifier_ignore import (
    ModifierIgnoreSnapshot,
    ignored_modifier_ids_for_context,
    options_with_modifier_ignore_choices,
    record_modifier_ignore_selection,
)
from warhammer40k_core.engine.movement_end_surge_hooks import (
    MovementEndSurgeContext,
    MovementEndSurgeDistanceKind,
    MovementEndSurgeDistanceSpec,
    MovementEndSurgeGrant,
)
from warhammer40k_core.engine.phase import (
    BattlePhase,
    GameLifecycleError,
    GameLifecycleStage,
    LifecycleStatus,
    LifecycleStatusKind,
)
from warhammer40k_core.engine.phases.movement_reactions import (
    _movement_end_surge_event_already_processed,
    _movement_end_surge_grant_groups,  # pyright: ignore[reportPrivateUsage]
    _movement_end_surge_reaction_group_key,  # pyright: ignore[reportPrivateUsage]
    _request_movement_end_surge_if_available,
)
from warhammer40k_core.engine.placement import create_deterministic_battlefield_scenario
from warhammer40k_core.engine.reserve_arrival_hooks import (
    ReserveArrivalRestrictionContext,
    ReserveArrivalRestrictionHookRegistry,
)
from warhammer40k_core.engine.reserve_arrival_restriction_resolution import (
    reserve_arrival_restriction_violations,
)
from warhammer40k_core.engine.reserves import (
    ReserveDestructionTimingPolicy,
    ReserveKind,
    ReserveOrigin,
    ReservePlacementViolationCode,
    ReserveState,
)
from warhammer40k_core.engine.rule_frequency import RULE_FREQUENCY_LIMIT_CONSUMED_EVENT
from warhammer40k_core.engine.rules_unit_geometry import geometry_models_for_rules_unit
from warhammer40k_core.engine.rules_unit_placement import RulesUnitPlacement
from warhammer40k_core.engine.rules_units import rules_unit_view_from_armies
from warhammer40k_core.engine.runtime_modifiers import (
    HitRollModifierContext,
    RuntimeModifierRegistry,
    SaveOptionModifierContext,
    WeaponProfileModifierContext,
    WoundRollModifierContext,
)
from warhammer40k_core.engine.saves import SaveKind, SaveOption
from warhammer40k_core.engine.shooting_types import ShootingType
from warhammer40k_core.engine.source_backed_rerolls import (
    source_backed_reroll_permission_context_for_unit,
)
from warhammer40k_core.engine.stratagem_catalog import (
    eleventh_edition_stratagem_catalog_records,
)
from warhammer40k_core.engine.stratagem_cost_choice_hooks import (
    StratagemCostChoiceRequestContext,
    StratagemCostChoiceResultContext,
)
from warhammer40k_core.engine.stratagem_cost_modifiers import (
    StratagemCostModifierContext,
    StratagemCostModifierRegistry,
)
from warhammer40k_core.engine.stratagems import (
    CORE_GO_TO_GROUND_HANDLER_ID,
    FALL_BACK_UNIT_CONTEXT_KEY,
    FIRE_OVERWATCH_TRIGGER_CONTEXT_KEY,
    GENERIC_FORCE_DESPERATE_ESCAPE_HANDLER_ID,
    GENERIC_INGRESS_MOVE_HANDLER_ID,
    GENERIC_RULE_IR_STRATAGEM_HANDLER_ID,
    STRATAGEM_DECISION_TYPE,
    TARGET_BINDING_UNIT_CONTEXT_KEY,
    VISIBLE_ENEMY_RANGE_INCHES_KEY,
    VISIBLE_ENEMY_SOURCE_UNIT_CONTEXT_KEY,
    VISIBLE_ENEMY_UNIT_CONTEXT_KEY,
    VISIBLE_ENEMY_UNIT_EFFECT_SELECTION_KIND,
    StratagemCategory,
    StratagemDefinition,
    StratagemEligibilityContext,
    StratagemTargetBinding,
    StratagemTargetKind,
    StratagemTargetSpec,
    StratagemTimingDescriptor,
    StratagemUseRecord,
    _handler_unavailable_reason,
)
from warhammer40k_core.engine.stratagems_generic_metadata import (
    EFFECT_SELECTION_KIND_KEY,
    REQUIRED_TRIGGER_CONTEXT_KEYS_KEY,
    TARGET_REQUIRED_REINFORCEMENT_ARRIVAL_THIS_TURN_KEY,
    TARGET_REQUIRED_TRIGGER_CONTEXT_LIST_KEY,
)
from warhammer40k_core.engine.timing_windows import TimingTriggerKind
from warhammer40k_core.engine.triggered_movement import (
    DECLINE_TRIGGERED_MOVEMENT_OPTION_ID,
    SELECT_TRIGGERED_MOVEMENT_DECISION_TYPE,
    TriggeredMovementKind,
)
from warhammer40k_core.engine.unit_destroyed_hooks import UnitDestroyedContext
from warhammer40k_core.engine.unit_factory import UnitInstance
from warhammer40k_core.engine.unit_move_completed_hooks import UnitMoveCompletedContext
from warhammer40k_core.engine.unit_state import (
    BelowHalfStrengthContext,
    starting_strength_records_for_units,
)
from warhammer40k_core.engine.wargear_selections import (
    ModelProfileSelection,
)
from warhammer40k_core.engine.weapon_declaration import RangedAttackPool
from warhammer40k_core.geometry.measurement import DistanceMeasurementContext
from warhammer40k_core.geometry.pose import Pose
from warhammer40k_core.geometry.terrain import (
    TerrainFeatureDefinition,
    TerrainFloorDefinition,
    TerrainWallDefinition,
)
from warhammer40k_core.rules.parsed_tokens import TextSpan
from warhammer40k_core.rules.rule_compiler import compile_rule_source_text
from warhammer40k_core.rules.rule_ir import (
    RuleClause,
    RuleCondition,
    RuleConditionKind,
    RuleDuration,
    RuleDurationKind,
    RuleEffectKind,
    RuleEffectSpec,
    RuleIR,
    RuleParameter,
    RuleParameterValue,
    RuleParseDiagnostic,
    RuleTargetKind,
    RuleTargetSpec,
    RuleTrigger,
    RuleTriggerKind,
    RuleUnsupportedReason,
    parameter_payload,
    parameters_from_pairs,
)
from warhammer40k_core.rules.source_data import RuleSourceText
from warhammer40k_core.rules.source_packages.warhammer_40000_11th import (
    datasheet_keyword_lexicon_2026_06_14 as datasheet_keyword_lexicon_source,
)
from warhammer40k_core.rules.source_packages.warhammer_40000_11th import (
    faction_pack_rule_ir,
)

skyreavers_package = faction_pack_rule_ir.source_package_artifact(
    "gw-11e-aeldari-corsair-skyreavers-datasheet-2026-06-09"
)
kharseth_package = faction_pack_rule_ir.source_package_artifact(
    "gw-11e-aeldari-kharseth-datasheet-2026-06-09"
)

SOURCE_KEYWORD_SEQUENCE_PARTS = (
    datasheet_keyword_lexicon_source.canonical_datasheet_keyword_sequence_parts()
)
ONCE_PER_BATTLE_FIGHT_BOOST_TEXT = (
    "Once per battle, at the start of the Fight phase, this model can use this ability. "
    "If it does, until the end of the phase, add 3 to the Attacks characteristic of melee "
    "weapons equipped by this model and those weapons have the [DEVASTATING WOUNDS] ability."
)
DESTROYED_CHARACTER_COMMAND_POINT_TEXT = (
    "Each time this model makes an attack that targets a Character unit, you can re-roll "
    "the Hit roll and you can re-roll the Wound roll. Each time this model destroys an "
    "enemy Character unit, you gain 1CP."
)
OPPONENT_STRATAGEM_COST_TEXT = (
    'Once per turn, when your opponent targets a unit from their army within 12" of this '
    "model with a stratagem, you can use this ability. If you do, increase the CP cost of "
    "the use of that stratagem by 1CP."
)
OWN_STRATAGEM_COST_TEXT = (
    "Once per battle round, one unit from your army with this ability can use it when its "
    "unit is targeted with a Stratagem. If it does, reduce the CP cost of that use of that "
    "Stratagem by 1CP."
)
UNNAMED_ZERO_CP_STRATAGEM_COST_TEXT = (
    "Once per battle round, you can target a friendly unit with a Stratagem for 0CP."
)
LEGACY_GRENADE_ZERO_CP_STRATAGEM_COST_TEXT = (
    "Once per turn, you can target this unit with the Grenade Stratagem for 0CP."
)
LEADERSHIP_COMMAND_POINT_TEXT = (
    "At the end of your Command phase, if this model is on the battlefield, take a "
    "Leadership test for this model; if that test is passed, you gain 1CP."
)
DIRECT_PHASE_COMMAND_POINT_TEXT = (
    "At the start of your Command phase, if this model is on the battlefield, you gain 1CP."
)
FIXED_ROLL_COMMAND_POINT_TEXT = (
    "At the end of your Command phase, roll one D6: on a 1+, you gain 1CP."
)
SKULL_ALTAR_BATTLE_SHOCK_REROLL_TEXT = (
    'While a friendly Khorne Legiones Daemonica unit is within 6" of this '
    "FORTIFICATION, each time you take a Battle-shock test for that unit, you can "
    "re-roll that test."
)


def test_catalog_desperate_escape_consumer_uses_source_rule_ir_and_state_context() -> None:
    target_army, source_army = _mustered_core_armies()
    target_unit = target_army.units[0]
    source_unit = source_army.units[0]
    battlefield = _battlefield_for_units(
        source_army=source_army,
        source_unit=source_unit,
        source_x=10.4,
        target_army=target_army,
        target_unit=target_unit,
        target_x=10.0,
    )
    state = _state_with_battlefield(
        armies=(target_army, source_army),
        battlefield=battlefield,
        active_player_id=target_army.player_id,
        phase=BattlePhase.MOVEMENT,
    )
    state.battle_shocked_unit_ids = [target_unit.unit_instance_id]
    record = _desperate_escape_record(source_unit=source_unit)

    sources = catalog_forced_desperate_escape_sources_for_unit(
        state=state,
        unit_instance_id=target_unit.unit_instance_id,
        ability_indexes_by_player_id={
            target_army.player_id: AbilityCatalogIndex.from_records(()),
            source_army.player_id: AbilityCatalogIndex.from_records((record,)),
        },
        armies=(target_army, source_army),
    )

    assert len(sources) == 1
    source = sources[0]
    assert source["source_kind"] == CATALOG_FORCED_DESPERATE_ESCAPE_SOURCE_KIND
    assert source["catalog_record_id"] == record.record_id
    assert source["forcing_unit_instance_id"] == source_unit.unit_instance_id
    assert source["fall_back_unit_instance_id"] == target_unit.unit_instance_id
    assert source["required_fall_back_mode"] == "desperate_escape"
    assert source["desperate_escape_roll_modifier"] == -1
    assert source["battle_round"] == 1
    assert source["phase"] == BattlePhase.MOVEMENT.value


def test_catalog_desperate_escape_consumer_filters_keywords_distance_and_shape_drift() -> None:
    target_army, source_army = _mustered_core_armies()
    target_unit = target_army.units[0]
    source_unit = source_army.units[0]
    record = _desperate_escape_record(source_unit=source_unit)
    indexes = {
        target_army.player_id: AbilityCatalogIndex.from_records(()),
        source_army.player_id: AbilityCatalogIndex.from_records((record,)),
    }
    far_state = _state_with_battlefield(
        armies=(target_army, source_army),
        battlefield=_battlefield_for_units(
            source_army=source_army,
            source_unit=source_unit,
            source_x=40.0,
            target_army=target_army,
            target_unit=target_unit,
            target_x=10.0,
        ),
        active_player_id=target_army.player_id,
        phase=BattlePhase.MOVEMENT,
    )

    assert (
        catalog_forced_desperate_escape_sources_for_unit(
            state=far_state,
            unit_instance_id=target_unit.unit_instance_id,
            ability_indexes_by_player_id=indexes,
            armies=(target_army, source_army),
        )
        == ()
    )

    monster_target = replace(
        target_unit,
        keywords=tuple(sorted((*target_unit.keywords, "MONSTER"))),
    )
    monster_target_army = _army_with_unit(target_army, monster_target)
    monster_state = _state_with_battlefield(
        armies=(monster_target_army, source_army),
        battlefield=_battlefield_for_units(
            source_army=source_army,
            source_unit=source_unit,
            source_x=10.4,
            target_army=monster_target_army,
            target_unit=monster_target,
            target_x=10.0,
        ),
        active_player_id=monster_target_army.player_id,
        phase=BattlePhase.MOVEMENT,
    )

    assert (
        catalog_forced_desperate_escape_sources_for_unit(
            state=monster_state,
            unit_instance_id=monster_target.unit_instance_id,
            ability_indexes_by_player_id=indexes,
            armies=(monster_target_army, source_army),
        )
        == ()
    )
    with pytest.raises(GameLifecycleError, match="requires GameState"):
        catalog_forced_desperate_escape_sources_for_unit(
            state=cast(GameState, object()),
            unit_instance_id=target_unit.unit_instance_id,
            ability_indexes_by_player_id=indexes,
            armies=(target_army, source_army),
        )
    with pytest.raises(GameLifecycleError, match="missing ability index"):
        catalog_forced_desperate_escape_sources_for_unit(
            state=far_state,
            unit_instance_id=target_unit.unit_instance_id,
            ability_indexes_by_player_id={target_army.player_id: indexes[target_army.player_id]},
            armies=(target_army, source_army),
        )


def test_catalog_desperate_escape_consumer_ignores_dead_engagement_placements() -> None:
    target_army, source_army = _mustered_core_armies()
    target_unit = target_army.units[0]
    source_unit = source_army.units[0]

    dead_source_unit = _unit_with_dead_model(source_unit, index=0)
    dead_source_army = _army_with_unit(source_army, dead_source_unit)
    dead_source_record = _desperate_escape_record(source_unit=dead_source_unit)
    dead_source_state = _state_with_battlefield(
        armies=(target_army, dead_source_army),
        battlefield=_battlefield_for_units_with_model_xs(
            source_army=dead_source_army,
            source_unit=dead_source_unit,
            source_model_xs=(10.4, 40.0, 42.0, 44.0, 46.0),
            target_army=target_army,
            target_unit=target_unit,
            target_model_xs=(10.0, 50.0, 52.0, 54.0, 56.0),
        ),
        active_player_id=target_army.player_id,
        phase=BattlePhase.MOVEMENT,
    )

    assert (
        catalog_forced_desperate_escape_sources_for_unit(
            state=dead_source_state,
            unit_instance_id=target_unit.unit_instance_id,
            ability_indexes_by_player_id={
                target_army.player_id: AbilityCatalogIndex.from_records(()),
                dead_source_army.player_id: AbilityCatalogIndex.from_records((dead_source_record,)),
            },
            armies=(target_army, dead_source_army),
        )
        == ()
    )

    dead_target_unit = _unit_with_dead_model(target_unit, index=0)
    dead_target_army = _army_with_unit(target_army, dead_target_unit)
    source_record = _desperate_escape_record(source_unit=source_unit)
    dead_target_state = _state_with_battlefield(
        armies=(dead_target_army, source_army),
        battlefield=_battlefield_for_units_with_model_xs(
            source_army=source_army,
            source_unit=source_unit,
            source_model_xs=(10.4, 40.0, 42.0, 44.0, 46.0),
            target_army=dead_target_army,
            target_unit=dead_target_unit,
            target_model_xs=(10.0, 50.0, 52.0, 54.0, 56.0),
        ),
        active_player_id=dead_target_army.player_id,
        phase=BattlePhase.MOVEMENT,
    )

    assert (
        catalog_forced_desperate_escape_sources_for_unit(
            state=dead_target_state,
            unit_instance_id=dead_target_unit.unit_instance_id,
            ability_indexes_by_player_id={
                dead_target_army.player_id: AbilityCatalogIndex.from_records(()),
                source_army.player_id: AbilityCatalogIndex.from_records((source_record,)),
            },
            armies=(dead_target_army, source_army),
        )
        == ()
    )


def test_catalog_battle_shock_reroll_runtime_uses_fortification_aura() -> None:
    catalog = ArmyCatalog.phase9a_canonical_content_pack()
    source_request = replace(
        _muster_request(catalog=catalog, player_id="player-a", army_id="army-alpha"),
        unit_selections=(
            UnitMusterSelection(
                unit_selection_id="skull-altar-source",
                datasheet_id="core-intercessor-like-infantry",
                model_profile_selections=(
                    ModelProfileSelection(
                        model_profile_id="core-intercessor-like",
                        model_count=5,
                    ),
                ),
            ),
            UnitMusterSelection(
                unit_selection_id="khorne-target",
                datasheet_id="core-intercessor-like-infantry",
                model_profile_selections=(
                    ModelProfileSelection(
                        model_profile_id="core-intercessor-like",
                        model_count=5,
                    ),
                ),
            ),
        ),
    )
    army = muster_army(catalog=catalog, request=source_request)
    enemy_army = muster_army(
        catalog=catalog,
        request=_muster_request(catalog=catalog, player_id="player-b", army_id="army-beta"),
    )
    source_unit = next(
        unit for unit in army.units if unit.unit_instance_id.endswith("skull-altar-source")
    )
    target_unit = next(
        unit for unit in army.units if unit.unit_instance_id.endswith("khorne-target")
    )
    source_unit = replace(
        source_unit,
        keywords=tuple(sorted((*source_unit.keywords, "FORTIFICATION"))),
        faction_keywords=("KHORNE", "LEGIONES DAEMONICA"),
    )
    target_unit = replace(
        target_unit,
        faction_keywords=("KHORNE", "LEGIONES DAEMONICA"),
    )
    army = replace(army, units=(source_unit, target_unit))
    battlefield = BattlefieldRuntimeState(
        battlefield_id="catalog-battle-shock-reroll",
        battlefield_width_inches=60.0,
        battlefield_depth_inches=44.0,
        placed_armies=(
            PlacedArmy(
                army_id=army.army_id,
                player_id=army.player_id,
                unit_placements=(
                    _unit_placement_for_test(
                        army=army,
                        unit=source_unit,
                        model_xs=_model_xs_for_unit(unit=source_unit, start_x=10.0),
                    ),
                    _unit_placement_for_test(
                        army=army,
                        unit=target_unit,
                        model_xs=_model_xs_for_unit(unit=target_unit, start_x=14.0),
                    ),
                ),
            ),
        ),
    )
    state = _state_with_battlefield(
        armies=(army, enemy_army),
        battlefield=battlefield,
        active_player_id=army.player_id,
        phase=BattlePhase.COMMAND,
    )
    starting_record = starting_strength_records_for_units(
        player_id=army.player_id,
        units=(target_unit,),
    )[0]
    request = BattleShockTestRequest.for_unit(
        request_id="catalog-battle-shock-reroll-test",
        game_id=state.game_id,
        battle_round=state.battle_round,
        player_id=army.player_id,
        unit_instance_id=target_unit.unit_instance_id,
        reason=BattleShockTestReason.BELOW_HALF_STRENGTH,
        leadership_target=6,
        below_half_strength_context=BelowHalfStrengthContext.from_unit(
            player_id=army.player_id,
            unit=target_unit,
            starting_strength=starting_record,
            current_model_ids=target_unit.own_model_ids(),
        ),
    )
    record = _compiled_record(
        record_id="catalog-skull-altar-battle-shock-reroll",
        raw_text=SKULL_ALTAR_BATTLE_SHOCK_REROLL_TEXT,
        source_unit=source_unit,
        trigger_kind=TimingTriggerKind.AFTER_DICE_ROLL,
    )
    runtime = CatalogBattleShockRerollRuntime(
        ability_indexes_by_player_id={
            army.player_id: AbilityCatalogIndex.from_records((record,)),
            enemy_army.player_id: AbilityCatalogIndex.from_records(()),
        },
        armies=(army, enemy_army),
    )

    context = BattleShockRerollPermissionContext(
        state=state,
        request=request,
        active_player_id=army.player_id,
        phase=BattlePhase.COMMAND,
        phase_start_battle_shocked_unit_ids=(),
    )
    permission = runtime.reroll_permission(context)

    assert permission is not None
    assert permission.eligible_roll_type == "battle_shock_roll"
    assert permission.component_selection_policy is RerollComponentSelectionPolicy.WHOLE_ROLL
    assert runtime.reroll_permission(replace(context, phase=BattlePhase.MOVEMENT)) == permission
    with pytest.raises(GameLifecycleError, match="requires context"):
        runtime.reroll_permission(cast(Any, object()))

    bindings = catalog_battle_shock_hook_bindings(
        ability_indexes_by_player_id={
            army.player_id: AbilityCatalogIndex.from_records((record,)),
            enemy_army.player_id: AbilityCatalogIndex.from_records(()),
        },
        armies=(army, enemy_army),
    )
    assert tuple(binding.hook_id for binding in bindings) == (
        CATALOG_SELECTED_TARGET_TEST_MODIFIER_HOOK_ID,
        CATALOG_IR_BATTLE_SHOCK_REROLL_CONSUMER_ID,
    )
    assert BattleShockHookRegistry.from_bindings(bindings).reroll_permission_for(context) == (
        permission
    )

    missing_index_runtime = CatalogBattleShockRerollRuntime(
        ability_indexes_by_player_id={
            enemy_army.player_id: AbilityCatalogIndex.from_records(()),
        },
        armies=(army, enemy_army),
    )
    with pytest.raises(GameLifecycleError, match="missing ability index"):
        missing_index_runtime.reroll_permission(context)
    with pytest.raises(GameLifecycleError, match="requires battlefield state"):
        battle_shock_runtime._units_within_distance(  # pyright: ignore[reportPrivateUsage]
            context=replace(
                context,
                state=_state_without_battlefield(
                    active_player_id=army.player_id,
                    phase=BattlePhase.COMMAND,
                ),
            ),
            first_unit=source_unit,
            first_model_ids=source_unit.own_model_ids(),
            second_unit=target_unit,
            second_model_ids=target_unit.own_model_ids(),
            distance_inches=6.0,
        )
    scenario = BattlefieldScenario(
        armies=(army, enemy_army),
        battlefield_state=battlefield,
    )
    with pytest.raises(GameLifecycleError, match="placement evidence drifted"):
        battle_shock_runtime._geometry_models_for_unit_ids(  # pyright: ignore[reportPrivateUsage]
            scenario=scenario,
            unit=source_unit,
            model_ids=("missing-model",),
        )
    with pytest.raises(GameLifecycleError, match="unit placement is missing"):
        battle_shock_runtime._geometry_models_for_unit_ids(  # pyright: ignore[reportPrivateUsage]
            scenario=scenario,
            unit=enemy_army.units[0],
            model_ids=enemy_army.units[0].own_model_ids(),
        )


def test_catalog_battle_shock_runtime_helpers_fail_fast_on_contract_drift() -> None:
    source_army, target_army = _mustered_core_armies()
    empty_index = AbilityCatalogIndex.from_records(())

    validated_indexes = battle_shock_runtime._validate_ability_indexes(  # pyright: ignore[reportPrivateUsage]
        {source_army.player_id: empty_index}
    )
    assert validated_indexes[source_army.player_id] is empty_index
    with pytest.raises(GameLifecycleError, match="ability indexes must be a mapping"):
        battle_shock_runtime._validate_ability_indexes(())  # pyright: ignore[reportPrivateUsage]
    with pytest.raises(GameLifecycleError, match="ability index player ID is invalid"):
        battle_shock_runtime._validate_ability_indexes(  # pyright: ignore[reportPrivateUsage]
            {1: empty_index}
        )
    with pytest.raises(GameLifecycleError, match="ability index value is invalid"):
        battle_shock_runtime._validate_ability_indexes(  # pyright: ignore[reportPrivateUsage]
            {source_army.player_id: object()}
        )

    assert battle_shock_runtime._validate_armies(  # pyright: ignore[reportPrivateUsage]
        (source_army, target_army)
    ) == (source_army, target_army)
    with pytest.raises(GameLifecycleError, match="runtime armies must be a tuple"):
        battle_shock_runtime._validate_armies(cast(Any, []))  # pyright: ignore[reportPrivateUsage]
    with pytest.raises(GameLifecycleError, match="runtime armies are invalid"):
        battle_shock_runtime._validate_armies(cast(Any, (object(),)))  # pyright: ignore[reportPrivateUsage]

    assert battle_shock_runtime._validate_identifier_tuple(  # pyright: ignore[reportPrivateUsage]
        "consumer_ids",
        ("one", "two"),
    ) == ("one", "two")
    with pytest.raises(GameLifecycleError, match="consumer_ids must be a tuple"):
        battle_shock_runtime._validate_identifier_tuple(  # pyright: ignore[reportPrivateUsage]
            "consumer_ids",
            cast(Any, ["one"]),
        )
    with pytest.raises(GameLifecycleError, match="consumer_ids value must not be empty"):
        battle_shock_runtime._validate_identifier_tuple(  # pyright: ignore[reportPrivateUsage]
            "consumer_ids",
            (" ",),
        )
    with pytest.raises(GameLifecycleError, match="consumer_ids must not contain duplicates"):
        battle_shock_runtime._validate_identifier_tuple(  # pyright: ignore[reportPrivateUsage]
            "consumer_ids",
            ("one", "one"),
        )
    assert (
        battle_shock_runtime._army_for_player(  # pyright: ignore[reportPrivateUsage]
            (source_army, target_army),
            player_id=source_army.player_id,
        )
        is source_army
    )
    with pytest.raises(GameLifecycleError, match="player army is unknown"):
        battle_shock_runtime._army_for_player(  # pyright: ignore[reportPrivateUsage]
            (source_army,),
            player_id=target_army.player_id,
        )
    assert (
        battle_shock_runtime._unit_in_army(  # pyright: ignore[reportPrivateUsage]
            source_army,
            unit_instance_id=source_army.units[0].unit_instance_id,
        )
        is source_army.units[0]
    )
    with pytest.raises(GameLifecycleError, match="runtime unit is unknown"):
        battle_shock_runtime._unit_in_army(  # pyright: ignore[reportPrivateUsage]
            source_army,
            unit_instance_id=target_army.units[0].unit_instance_id,
        )


def test_catalog_battle_shock_reroll_clause_helpers_are_strict() -> None:
    source_army, _ = _mustered_core_armies()
    fortification_unit = replace(
        source_army.units[0],
        keywords=tuple(sorted((*source_army.units[0].keywords, "FORTIFICATION"))),
        faction_keywords=("LEGIONES", "DAEMONICA", "KHORNE"),
    )
    non_fortification_unit = replace(
        source_army.units[0],
        faction_keywords=("LEGIONES", "DAEMONICA", "KHORNE"),
    )

    def reroll_clause(
        *,
        object_kind: str = "fortification",
        distance: RuleParameterValue = 6,
        effect_kind: RuleEffectKind = RuleEffectKind.REROLL_PERMISSION,
        roll_type: str = "battle_shock",
        timing_window: str = "battle_shock_test",
        extra_conditions: tuple[RuleCondition, ...] = (),
    ) -> RuleClause:
        return RuleClause(
            clause_id="test:catalog-battle-shock-reroll:clause",
            source_span=_span(),
            target=RuleTargetSpec(
                kind=RuleTargetKind.FRIENDLY_UNIT,
                source_span=_span(),
                parameters=_parameters(
                    ("required_keyword", "KHORNE"),
                    ("required_keyword_sequence", ("LEGIONES", "DAEMONICA")),
                ),
            ),
            conditions=(
                _condition(
                    RuleConditionKind.DISTANCE_PREDICATE,
                    ("range_kind", "numeric_range"),
                    ("predicate", "within"),
                    ("object_kind", object_kind),
                    ("object_reference", "this"),
                    ("negated", False),
                    ("distance_inches", distance),
                ),
                _condition(
                    RuleConditionKind.KEYWORD_GATE,
                    ("required_keyword_sequence", ("LEGIONES", "DAEMONICA")),
                ),
                *extra_conditions,
            ),
            effects=(
                _effect(
                    effect_kind,
                    ("roll_type", roll_type),
                    ("timing_window", timing_window),
                ),
            ),
        )

    clause = reroll_clause()

    assert battle_shock_runtime._effect_is_battle_shock_reroll(  # pyright: ignore[reportPrivateUsage]
        clause.effects[0]
    )
    assert not battle_shock_runtime._effect_is_battle_shock_reroll(  # pyright: ignore[reportPrivateUsage]
        reroll_clause(effect_kind=RuleEffectKind.MODIFY_DICE_ROLL).effects[0]
    )
    assert not battle_shock_runtime._effect_is_battle_shock_reroll(  # pyright: ignore[reportPrivateUsage]
        reroll_clause(roll_type="hit", timing_window="battle_shock_test").effects[0]
    )
    with pytest.raises(GameLifecycleError, match="reroll effect is invalid"):
        battle_shock_runtime._effect_is_battle_shock_reroll(  # pyright: ignore[reportPrivateUsage]
            cast(Any, object())
        )

    assert battle_shock_runtime._source_distance_object_kind(clause) == "fortification"  # pyright: ignore[reportPrivateUsage]
    assert battle_shock_runtime._battle_shock_reroll_distance_inches(clause) == 6.0  # pyright: ignore[reportPrivateUsage]
    assert battle_shock_runtime._required_keywords_for_clause(clause) == (  # pyright: ignore[reportPrivateUsage]
        "DAEMONICA",
        "KHORNE",
        "LEGIONES",
    )
    assert battle_shock_runtime._battle_shock_reroll_clause_matches_source(  # pyright: ignore[reportPrivateUsage]
        clause,
        source_unit=fortification_unit,
    )
    assert not battle_shock_runtime._battle_shock_reroll_clause_matches_source(  # pyright: ignore[reportPrivateUsage]
        clause,
        source_unit=non_fortification_unit,
    )
    assert battle_shock_runtime._battle_shock_reroll_clause_matches_target(  # pyright: ignore[reportPrivateUsage]
        clause,
        target_unit=fortification_unit,
    )
    with pytest.raises(GameLifecycleError, match="clause is invalid"):
        battle_shock_runtime._battle_shock_reroll_clause_matches_target(  # pyright: ignore[reportPrivateUsage]
            cast(Any, object()),
            target_unit=fortification_unit,
        )
    with pytest.raises(GameLifecycleError, match="target unit is invalid"):
        battle_shock_runtime._battle_shock_reroll_clause_matches_target(  # pyright: ignore[reportPrivateUsage]
            clause,
            target_unit=cast(Any, object()),
        )

    assert battle_shock_runtime._unit_has_required_keyword(  # pyright: ignore[reportPrivateUsage]
        fortification_unit,
        required_keyword="legiones-daemonica",
    )
    assert not battle_shock_runtime._unit_has_required_keyword(  # pyright: ignore[reportPrivateUsage]
        fortification_unit,
        required_keyword="TZEENTCH",
    )
    assert battle_shock_runtime._keyword_sequence_is_covered(  # pyright: ignore[reportPrivateUsage]
        ("LEGIONES", "DAEMONICA"),
        frozenset(("LEGIONES", "DAEMONICA")),
    )
    assert not battle_shock_runtime._keyword_sequence_is_covered(  # pyright: ignore[reportPrivateUsage]
        ("LEGIONES", "DAEMONICA"),
        frozenset(("LEGIONES", "ASTARTES")),
    )
    with pytest.raises(GameLifecycleError, match="keyword must be a string"):
        battle_shock_runtime._canonical_keyword(cast(Any, 1))  # pyright: ignore[reportPrivateUsage]
    with pytest.raises(GameLifecycleError, match="keyword must be a string"):
        battle_shock_runtime._canonical_keyword(" ")  # pyright: ignore[reportPrivateUsage]

    with pytest.raises(GameLifecycleError, match="source object kind is malformed"):
        battle_shock_runtime._battle_shock_reroll_clause_matches_source(  # pyright: ignore[reportPrivateUsage]
            reroll_clause(object_kind="vehicle"),
            source_unit=fortification_unit,
        )
    with pytest.raises(GameLifecycleError, match="exactly one source object kind"):
        battle_shock_runtime._source_distance_object_kind(  # pyright: ignore[reportPrivateUsage]
            RuleClause(
                clause_id="test:missing-object-kind",
                source_span=_span(),
                effects=(_effect(RuleEffectKind.MODIFY_DICE_ROLL, ("delta", 1)),),
            )
        )
    with pytest.raises(GameLifecycleError, match="distance predicate is malformed"):
        battle_shock_runtime._battle_shock_reroll_distance_inches(  # pyright: ignore[reportPrivateUsage]
            reroll_clause(distance=False)
        )
    with pytest.raises(GameLifecycleError, match="exactly one source distance predicate"):
        battle_shock_runtime._battle_shock_reroll_distance_inches(  # pyright: ignore[reportPrivateUsage]
            reroll_clause(
                extra_conditions=(
                    _condition(
                        RuleConditionKind.DISTANCE_PREDICATE,
                        ("range_kind", "numeric_range"),
                        ("predicate", "within"),
                        ("object_kind", "fortification"),
                        ("object_reference", "this"),
                        ("negated", False),
                        ("distance_inches", 9),
                    ),
                )
            )
        )


def test_catalog_selected_target_support_classifies_selection_and_effect_clauses() -> None:
    fight_selection = _fight_start_selection_clause()
    post_shoot_selection = _post_shoot_hit_selection_clause()
    skipped_effect = _effect_clause(
        clause_id="test:selected-target:effect:skipped",
        duration=None,
        effect_kind=RuleEffectKind.MODIFY_DICE_ROLL,
        roll_type="attack_sequence.hit",
        delta=1,
    )
    selected_effect = _effect_clause(
        clause_id="test:selected-target:effect:applied",
        duration=_duration("phase"),
        effect_kind=RuleEffectKind.MODIFY_DICE_ROLL,
        roll_type="attack_sequence.hit",
        delta=1,
    )
    breaker = _fight_start_selection_clause(clause_id="test:selected-target:selection:next")

    assert clause_is_fight_start_selection(fight_selection)
    assert not clause_is_fight_start_selection(post_shoot_selection)
    assert clause_is_post_shoot_hit_target_selection(post_shoot_selection)
    assert not clause_is_post_shoot_hit_target_selection(fight_selection)
    assert post_shoot_selection.trigger is not None
    unit_trigger_parameters = parameter_payload(post_shoot_selection.trigger.parameters)
    unit_trigger_parameters.pop("attacker_model_reference")
    unit_trigger_parameters.pop("weapon_names")
    unit_trigger_parameters["subject"] = "this_unit"
    unit_selection_clause = replace(
        post_shoot_selection,
        trigger=replace(
            post_shoot_selection.trigger,
            parameters=_parameters(*tuple(unit_trigger_parameters.items())),
        ),
    )
    assert clause_is_post_shoot_hit_target_selection(unit_selection_clause)
    for parameter_name, unsupported_value in (
        ("owner", "opponent"),
        ("phase", "fight"),
        ("edge", "before"),
        ("subject", "friendly_unit"),
        ("attacker_model_reference", "attacking_model"),
    ):
        trigger_parameters = parameter_payload(post_shoot_selection.trigger.parameters)
        trigger_parameters[parameter_name] = unsupported_value
        unsupported_clause = replace(
            post_shoot_selection,
            trigger=replace(
                post_shoot_selection.trigger,
                parameters=_parameters(*tuple(trigger_parameters.items())),
            ),
        )
        assert not clause_is_post_shoot_hit_target_selection(unsupported_clause)
    assert selected_effect_clauses_after(
        (fight_selection, skipped_effect, selected_effect, breaker),
        0,
    ) == (selected_effect,)
    assert post_shoot_selected_target_effect_clause_is_supported(selected_effect)
    assert (
        post_shoot_selected_target_effect_attack_role(
            clause=selected_effect,
            effect=selected_effect.effects[0],
        )
        == "target"
    )
    assert post_shoot_selected_target_effect_clauses_after(
        (post_shoot_selection, skipped_effect, selected_effect, breaker),
        0,
    ) == (selected_effect,)
    for actor, target_kind in (
        ("this_model", RuleTargetKind.THIS_MODEL),
        ("this_unit", RuleTargetKind.THIS_UNIT),
    ):
        actor_scoped_effect = replace(
            selected_effect,
            trigger=_post_shoot_effect_trigger(actor=actor),
            target=RuleTargetSpec(kind=target_kind, source_span=_span()),
        )
        assert post_shoot_selected_target_effect_clause_is_supported(actor_scoped_effect)
        assert (
            post_shoot_selected_target_effect_attack_role(
                clause=actor_scoped_effect,
                effect=actor_scoped_effect.effects[0],
            )
            == "attacker"
        )

    this_model_effect = replace(
        selected_effect,
        trigger=RuleTrigger(
            kind=RuleTriggerKind.DICE_ROLL,
            source_span=_span(),
            parameters=_parameters(
                ("actor", "this_model"),
                ("attack_kind", "melee"),
                ("target_reference", "selected_unit"),
                ("timing_window", "attack_sequence.attack"),
            ),
        ),
        target=RuleTargetSpec(kind=RuleTargetKind.THIS_MODEL, source_span=_span()),
    )
    transformed_this_model_effect = effect_with_selected_target(
        this_model_effect.effects[0],
        selected_target_unit_instance_id="selected-target",
        clause=this_model_effect,
    )
    assert parameter_payload(transformed_this_model_effect.parameters) == {
        "attack_role": "attacker",
        "delta": 1,
        "roll_type": "attack_sequence.hit",
        "selected_target_unit_instance_id": "selected-target",
        "weapon_scope": "melee",
    }

    effect = _effect(
        RuleEffectKind.MODIFY_DICE_ROLL,
        ("roll_type", "attack_sequence.hit"),
        ("delta", 1),
        ("selected_target_unit_instance_id", "old-target"),
    )
    transformed = effect_with_selected_target(
        effect,
        selected_target_unit_instance_id="new-target",
    )

    assert parameter_payload(transformed.parameters) == {
        "delta": 1,
        "roll_type": "attack_sequence.hit",
        "selected_target_unit_instance_id": "new-target",
    }
    with pytest.raises(GameLifecycleError, match="requires RuleClause"):
        clause_is_fight_start_selection(cast(RuleClause, object()))
    with pytest.raises(GameLifecycleError, match="requires RuleClause"):
        clause_is_post_shoot_hit_target_selection(cast(RuleClause, object()))
    with pytest.raises(GameLifecycleError, match="requires RuleClause"):
        post_shoot_selected_target_effect_clause_is_supported(cast(RuleClause, object()))


def test_catalog_post_shoot_selected_target_rejects_unsupported_effect_shapes() -> None:
    selection = _post_shoot_hit_selection_clause()
    supported_effect = _effect_clause(
        clause_id="test:selected-target:selection:post-shoot:supported-effect",
        duration=_duration("phase"),
        effect_kind=RuleEffectKind.MODIFY_DICE_ROLL,
        roll_type="attack_sequence.hit",
        delta=1,
    )
    invalid_shapes = (
        (
            "unsupported-target",
            replace(
                supported_effect,
                target=RuleTargetSpec(kind=RuleTargetKind.PLAYER, source_span=_span()),
            ),
        ),
        (
            "unsupported-duration-kind",
            replace(
                supported_effect,
                duration=RuleDuration(
                    kind=RuleDurationKind.WHILE_CONDITION_TRUE,
                    source_span=_span(),
                ),
            ),
        ),
        (
            "unsupported-duration-endpoint",
            replace(supported_effect, duration=_duration("next_shooting_phase")),
        ),
        (
            "unsupported-condition-relationship",
            replace(
                supported_effect,
                conditions=(
                    _condition(
                        RuleConditionKind.TARGET_CONSTRAINT,
                        ("relationship", "source_unit_can_see_selected_unit"),
                    ),
                ),
            ),
        ),
        (
            "mixed-supported-and-unsupported-effects",
            replace(
                supported_effect,
                effects=(
                    *supported_effect.effects,
                    _effect(RuleEffectKind.ADD_VICTORY_POINTS, ("amount", 1)),
                ),
            ),
        ),
        (
            "unsupported-effect-parameters",
            replace(
                supported_effect,
                effects=(
                    _effect(
                        RuleEffectKind.MODIFY_DICE_ROLL,
                        ("roll_type", "attack_sequence.hit"),
                        ("delta", 1),
                        ("unsupported_mode", "always"),
                    ),
                ),
            ),
        ),
        (
            "selected-unit-trigger-actor",
            replace(
                supported_effect,
                trigger=_post_shoot_effect_trigger(actor="selected_unit"),
                target=RuleTargetSpec(
                    kind=RuleTargetKind.SELECTED_UNIT,
                    source_span=_span(),
                ),
                effects=(
                    _effect(
                        RuleEffectKind.MODIFY_DICE_ROLL,
                        ("roll_type", "attack_sequence.hit"),
                        ("delta", -1),
                    ),
                ),
            ),
        ),
        (
            "this-model-trigger-with-friendly-unit-target",
            replace(
                supported_effect,
                trigger=_post_shoot_effect_trigger(actor="this_model"),
                target=RuleTargetSpec(
                    kind=RuleTargetKind.FRIENDLY_UNIT,
                    source_span=_span(),
                    parameters=_parameters(("allegiance", "friendly")),
                ),
            ),
        ),
        (
            "this-model-trigger-with-target-attack-role",
            replace(
                supported_effect,
                trigger=_post_shoot_effect_trigger(actor="this_model"),
                target=RuleTargetSpec(
                    kind=RuleTargetKind.THIS_MODEL,
                    source_span=_span(),
                ),
                effects=(
                    _effect(
                        RuleEffectKind.MODIFY_DICE_ROLL,
                        ("roll_type", "attack_sequence.hit"),
                        ("delta", -1),
                        ("attack_role", "target"),
                    ),
                ),
            ),
        ),
        (
            "selected-enemy-target-with-attacker-role",
            replace(
                supported_effect,
                effects=(
                    _effect(
                        RuleEffectKind.MODIFY_DICE_ROLL,
                        ("roll_type", "attack_sequence.hit"),
                        ("delta", 1),
                        ("attack_role", "attacker"),
                    ),
                ),
            ),
        ),
    )
    source_army, target_army = _mustered_core_armies()
    empty_index = AbilityCatalogIndex.from_records(())

    for shape_name, invalid_effect in invalid_shapes:
        rule_ir = _rule_ir(
            source_id=f"test:selected-target:post-shoot:{shape_name}",
            clauses=(selection, invalid_effect),
        )
        record = _ability_record(
            record_id=f"record:selected-target:post-shoot:{shape_name}",
            rule_ir=rule_ir,
            trigger_kind=TimingTriggerKind.JUST_AFTER_FRIENDLY_UNIT_HAS_SHOT,
            runtime_clause_id=selection.clause_id,
        )
        index = AbilityCatalogIndex.from_records((record,))

        assert not post_shoot_selected_target_effect_clause_is_supported(invalid_effect), shape_name
        assert (
            post_shoot_selected_target_effect_clauses_after(
                rule_ir.clauses,
                0,
            )
            == ()
        ), shape_name
        assert post_shoot_hit_target_effect_clause_ids(rule_ir) == (), shape_name
        consumer_ids = catalog_rule_ir_consumers_for_rule(rule_ir)
        hook_ids = catalog_rule_ir_hook_ids_for_rule(rule_ir)
        assert consumer_ids == (), shape_name
        assert hook_ids == (), shape_name
        assert CATALOG_IR_POST_SHOOT_HIT_TARGET_EFFECT_CONSUMER_ID not in consumer_ids, shape_name
        assert CATALOG_IR_POST_SHOOT_HIT_TARGET_EFFECT_CONSUMER_ID not in hook_ids, shape_name
        assert not has_post_shoot_hit_target_effect_records({source_army.player_id: index}), (
            shape_name
        )
        runtime = CatalogSelectedTargetEffectRuntime(
            ability_indexes_by_player_id={
                source_army.player_id: index,
                target_army.player_id: empty_index,
            },
            armies=(source_army, target_army),
        )
        assert runtime.attack_sequence_completed_bindings() == (), shape_name


@pytest.mark.parametrize(
    "include_model_condition",
    [pytest.param(False), pytest.param(True)],
    ids=("without-model-condition", "with-model-condition"),
)
def test_catalog_post_shoot_rejects_unit_selection_for_model_scoped_effect(
    include_model_condition: bool,
) -> None:
    model_selection = _post_shoot_hit_selection_clause()
    assert model_selection.trigger is not None
    trigger_parameters = parameter_payload(model_selection.trigger.parameters)
    trigger_parameters.pop("attacker_model_reference")
    trigger_parameters.pop("weapon_names")
    trigger_parameters["subject"] = "this_unit"
    unit_selection = replace(
        model_selection,
        trigger=replace(
            model_selection.trigger,
            parameters=_parameters(*tuple(trigger_parameters.items())),
        ),
    )
    conditions = (
        (
            _condition(
                RuleConditionKind.TARGET_CONSTRAINT,
                ("gate_subject", "attack_target"),
                ("relationship", "this_model_makes_attack"),
                ("target_reference", "selected_unit"),
            ),
        )
        if include_model_condition
        else ()
    )
    effect_clause = RuleClause(
        clause_id="test:selected-target:selection:post-shoot:model-effect",
        source_span=_span(),
        trigger=_post_shoot_effect_trigger(actor="this_model"),
        conditions=conditions,
        target=RuleTargetSpec(kind=RuleTargetKind.THIS_MODEL, source_span=_span()),
        effects=(
            _effect(
                RuleEffectKind.MODIFY_DICE_ROLL,
                ("roll_type", "attack_sequence.hit"),
                ("delta", -1),
            ),
        ),
        duration=_duration("phase"),
    )
    rule_ir = _rule_ir(
        source_id="test:selected-target:post-shoot:unit-selection-model-effect",
        clauses=(unit_selection, effect_clause),
    )
    record = _ability_record(
        record_id="record:selected-target:post-shoot:unit-selection-model-effect",
        rule_ir=rule_ir,
        trigger_kind=TimingTriggerKind.JUST_AFTER_FRIENDLY_UNIT_HAS_SHOT,
        runtime_clause_id=unit_selection.clause_id,
    )
    source_army, target_army = _mustered_core_armies()
    index = AbilityCatalogIndex.from_records((record,))
    empty_index = AbilityCatalogIndex.from_records(())

    assert clause_is_post_shoot_hit_target_selection(unit_selection)
    assert post_shoot_selected_target_effect_clause_is_supported(effect_clause)
    assert not post_shoot_selected_target_pair_is_supported(
        selection_clause=unit_selection,
        effect_clause=effect_clause,
    )
    assert post_shoot_selected_target_effect_clauses_after(rule_ir.clauses, 0) == ()
    assert post_shoot_hit_target_effect_clause_ids(rule_ir) == ()
    assert catalog_rule_ir_consumers_for_rule(rule_ir) == ()
    assert catalog_rule_ir_hook_ids_for_rule(rule_ir) == ()
    assert not has_post_shoot_hit_target_effect_records({source_army.player_id: index})
    runtime = CatalogSelectedTargetEffectRuntime(
        ability_indexes_by_player_id={
            source_army.player_id: index,
            target_army.player_id: empty_index,
        },
        armies=(source_army, target_army),
    )
    assert runtime.attack_sequence_completed_bindings() == ()


def test_catalog_fight_start_rejects_mixed_supported_and_unsupported_effects() -> None:
    selection_clause = _fight_start_selection_clause()
    supported_effect_clause = _effect_clause(
        clause_id="test:selected-target:selection:fight:mixed-effect",
        duration=_duration("phase"),
        effect_kind=RuleEffectKind.REROLL_PERMISSION,
        roll_type="attack_sequence.hit",
    )
    mixed_effect_clause = replace(
        supported_effect_clause,
        effects=(
            *supported_effect_clause.effects,
            _effect(RuleEffectKind.ADD_VICTORY_POINTS, ("amount", 1)),
        ),
    )
    rule_ir = _rule_ir(
        source_id="test:selected-target:fight:mixed-effect",
        clauses=(selection_clause, mixed_effect_clause),
    )
    record = _ability_record(
        record_id="record:selected-target:fight:mixed-effect",
        rule_ir=rule_ir,
        trigger_kind=TimingTriggerKind.START_PHASE,
        runtime_clause_id=selection_clause.clause_id,
    )
    source_army, target_army = _mustered_core_armies()
    index = AbilityCatalogIndex.from_records((record,))
    runtime = CatalogSelectedTargetEffectRuntime(
        ability_indexes_by_player_id={
            source_army.player_id: index,
            target_army.player_id: AbilityCatalogIndex.from_records(()),
        },
        armies=(source_army, target_army),
    )

    assert fight_start_selected_target_effect_clause_ids(rule_ir) == ()
    assert CATALOG_IR_SELECTED_TARGET_EFFECT_CONSUMER_ID not in (
        catalog_rule_ir_consumers_for_rule(rule_ir)
    )
    assert CATALOG_IR_SELECTED_TARGET_EFFECT_CONSUMER_ID not in (
        catalog_rule_ir_hook_ids_for_rule(rule_ir)
    )
    assert not has_fight_start_selected_target_records({source_army.player_id: index})
    assert runtime.fight_phase_start_bindings() == ()


def test_catalog_fight_start_rejects_malformed_recognized_effect_shapes() -> None:
    selection_clause = _fight_start_selection_clause()
    supported_effect_clause = _effect_clause(
        clause_id="test:selected-target:selection:fight:malformed-effect",
        duration=_duration("phase"),
        effect_kind=RuleEffectKind.MODIFY_DICE_ROLL,
        roll_type="attack_sequence.hit",
        delta=1,
    )
    invalid_shapes = (
        (
            "unexpected-effect-parameter",
            replace(
                supported_effect_clause,
                effects=(
                    _effect(
                        RuleEffectKind.MODIFY_DICE_ROLL,
                        ("roll_type", "attack_sequence.hit"),
                        ("delta", 1),
                        ("unsupported_mode", "always"),
                    ),
                ),
            ),
        ),
        (
            "malformed-delta",
            replace(
                supported_effect_clause,
                effects=(
                    _effect(
                        RuleEffectKind.MODIFY_DICE_ROLL,
                        ("roll_type", "attack_sequence.hit"),
                        ("delta", "1"),
                    ),
                ),
            ),
        ),
        (
            "unsupported-trigger",
            replace(
                supported_effect_clause,
                trigger=RuleTrigger(
                    kind=RuleTriggerKind.DICE_ROLL,
                    source_span=_span(),
                    parameters=_parameters(
                        ("actor", "this_unit"),
                        ("target_reference", "selected_unit"),
                        ("timing_window", "attack_sequence.attack"),
                        ("unsupported_mode", "always"),
                    ),
                ),
                target=RuleTargetSpec(kind=RuleTargetKind.THIS_UNIT, source_span=_span()),
            ),
        ),
        (
            "unsupported-condition-relationship",
            replace(
                supported_effect_clause,
                conditions=(
                    _condition(
                        RuleConditionKind.TARGET_CONSTRAINT,
                        ("relationship", "source_unit_can_see_selected_unit"),
                    ),
                ),
            ),
        ),
        (
            "unsupported-target-parameters",
            replace(
                supported_effect_clause,
                target=RuleTargetSpec(
                    kind=RuleTargetKind.SELECTED_TARGET,
                    source_span=_span(),
                    parameters=_parameters(("unsupported_scope", "all")),
                ),
            ),
        ),
        (
            "incompatible-attack-role",
            replace(
                supported_effect_clause,
                effects=(
                    _effect(
                        RuleEffectKind.MODIFY_DICE_ROLL,
                        ("roll_type", "attack_sequence.hit"),
                        ("delta", 1),
                        ("attack_role", "attacker"),
                    ),
                ),
            ),
        ),
    )
    source_army, target_army = _mustered_core_armies()
    empty_index = AbilityCatalogIndex.from_records(())

    for shape_name, invalid_effect_clause in invalid_shapes:
        rule_ir = _rule_ir(
            source_id=f"test:selected-target:fight:{shape_name}",
            clauses=(selection_clause, invalid_effect_clause),
        )
        record = _ability_record(
            record_id=f"record:selected-target:fight:{shape_name}",
            rule_ir=rule_ir,
            trigger_kind=TimingTriggerKind.START_PHASE,
            runtime_clause_id=selection_clause.clause_id,
        )
        index = AbilityCatalogIndex.from_records((record,))
        runtime = CatalogSelectedTargetEffectRuntime(
            ability_indexes_by_player_id={
                source_army.player_id: index,
                target_army.player_id: empty_index,
            },
            armies=(source_army, target_army),
        )

        assert not selected_target_persisting_effect_clause_is_supported(invalid_effect_clause), (
            shape_name
        )
        assert fight_start_selected_target_effect_clause_ids(rule_ir) == (), shape_name
        consumer_ids = catalog_rule_ir_consumers_for_rule(rule_ir)
        hook_ids = catalog_rule_ir_hook_ids_for_rule(rule_ir)
        assert CATALOG_IR_SELECTED_TARGET_EFFECT_CONSUMER_ID not in consumer_ids, shape_name
        assert CATALOG_IR_SELECTED_TARGET_EFFECT_CONSUMER_ID not in hook_ids, shape_name
        assert not has_fight_start_selected_target_records({source_army.player_id: index}), (
            shape_name
        )
        assert runtime.fight_phase_start_bindings() == (), shape_name


def test_catalog_fight_start_rejects_malformed_selection_shapes() -> None:
    selection_clause = _fight_start_selection_clause()
    supported_effect_clause = _effect_clause(
        clause_id="test:selected-target:selection:fight:selection-shape-effect",
        duration=_duration("phase"),
        effect_kind=RuleEffectKind.REROLL_PERMISSION,
        roll_type="attack_sequence.hit",
    )
    distance_parameter_pairs = (
        ("distance_inches", None),
        ("negated", False),
        ("object_kind", "model"),
        ("object_reference", "this"),
        ("predicate", "within_engagement_range"),
        ("qualifier", None),
        ("range_kind", "engagement_range"),
    )
    invalid_shapes = (
        (
            "unsupported-clause",
            replace(
                selection_clause,
                diagnostics=(
                    RuleParseDiagnostic(
                        reason=RuleUnsupportedReason.UNSUPPORTED_LANGUAGE,
                        message="unsupported-selection",
                        source_span=_span(),
                    ),
                ),
            ),
        ),
        (
            "unsupported-condition-kind",
            replace(
                selection_clause,
                conditions=(
                    _condition(RuleConditionKind.KEYWORD_GATE, ("required_keyword", "PSYKER")),
                ),
            ),
        ),
        (
            "unknown-target-parameter",
            replace(
                selection_clause,
                target=RuleTargetSpec(
                    kind=RuleTargetKind.ENEMY_UNIT,
                    source_span=_span(),
                    parameters=_parameters(
                        ("allegiance", "enemy"),
                        ("unsupported_scope", "all"),
                    ),
                ),
            ),
        ),
        (
            "contradictory-target-allegiance",
            replace(
                selection_clause,
                target=RuleTargetSpec(
                    kind=RuleTargetKind.ENEMY_UNIT,
                    source_span=_span(),
                    parameters=_parameters(("allegiance", "friendly")),
                ),
            ),
        ),
        (
            "extra-trigger-parameter",
            replace(
                selection_clause,
                trigger=RuleTrigger(
                    kind=RuleTriggerKind.TIMING_WINDOW,
                    source_span=_span(),
                    parameters=_parameters(
                        ("edge", "start"),
                        ("owner", None),
                        ("phase", BattlePhase.FIGHT.value),
                        ("unsupported_mode", "always"),
                    ),
                ),
            ),
        ),
        (
            "unsupported-trigger-owner",
            replace(
                selection_clause,
                trigger=RuleTrigger(
                    kind=RuleTriggerKind.TIMING_WINDOW,
                    source_span=_span(),
                    parameters=_parameters(
                        ("edge", "start"),
                        ("owner", "opponent"),
                        ("phase", BattlePhase.FIGHT.value),
                    ),
                ),
            ),
        ),
        (
            "malformed-engagement-range",
            replace(
                selection_clause,
                conditions=(
                    _condition(
                        RuleConditionKind.DISTANCE_PREDICATE,
                        *tuple(
                            (key, 1.0) if key == "distance_inches" else (key, value)
                            for key, value in distance_parameter_pairs
                        ),
                    ),
                ),
            ),
        ),
        (
            "malformed-numeric-distance",
            replace(
                selection_clause,
                conditions=(
                    _condition(
                        RuleConditionKind.DISTANCE_PREDICATE,
                        ("distance_inches", "6"),
                        ("negated", False),
                        ("object_kind", "model"),
                        ("object_reference", "this"),
                        ("predicate", "within"),
                        ("qualifier", None),
                        ("range_kind", "numeric_range"),
                    ),
                ),
            ),
        ),
        (
            "malformed-visibility",
            replace(
                selection_clause,
                conditions=(
                    _condition(
                        RuleConditionKind.VISIBILITY_PREDICATE,
                        ("observer", "this_model"),
                        ("predicate", "visible_to"),
                        ("target_reference", "selected_unit"),
                        ("unsupported_mode", "always"),
                    ),
                ),
            ),
        ),
    )
    source_army, target_army = _mustered_core_armies()
    empty_index = AbilityCatalogIndex.from_records(())
    battlefield = _battlefield_for_units(
        source_army=source_army,
        source_unit=source_army.units[0],
        source_x=10.0,
        target_army=target_army,
        target_unit=target_army.units[0],
        target_x=10.4,
    )
    state = _state_with_battlefield(
        armies=(source_army, target_army),
        battlefield=battlefield,
        active_player_id=source_army.player_id,
        phase=BattlePhase.FIGHT,
    )

    for shape_name, invalid_selection_clause in invalid_shapes:
        rule_ir = _rule_ir(
            source_id=f"test:selected-target:fight:selection:{shape_name}",
            clauses=(invalid_selection_clause, supported_effect_clause),
        )
        record = _ability_record(
            record_id=f"record:selected-target:fight:selection:{shape_name}",
            rule_ir=rule_ir,
            trigger_kind=TimingTriggerKind.START_PHASE,
            runtime_clause_id=invalid_selection_clause.clause_id,
        )
        index = AbilityCatalogIndex.from_records((record,))
        runtime = CatalogSelectedTargetEffectRuntime(
            ability_indexes_by_player_id={
                source_army.player_id: index,
                target_army.player_id: empty_index,
            },
            armies=(source_army, target_army),
        )

        assert not fight_start_selected_target_selection_is_supported(invalid_selection_clause), (
            shape_name
        )
        assert fight_start_selected_target_effect_clause_ids(rule_ir) == (), shape_name
        consumer_ids = catalog_rule_ir_consumers_for_rule(rule_ir)
        hook_ids = catalog_rule_ir_hook_ids_for_rule(rule_ir)
        assert CATALOG_IR_SELECTED_TARGET_EFFECT_CONSUMER_ID not in consumer_ids, shape_name
        assert CATALOG_IR_SELECTED_TARGET_EFFECT_CONSUMER_ID not in hook_ids, shape_name
        assert not record_has_supported_fight_start_selected_target_effect(record), shape_name
        assert not has_fight_start_selected_target_records({source_army.player_id: index}), (
            shape_name
        )
        assert runtime.fight_phase_start_bindings() == (), shape_name
        assert (
            runtime.fight_phase_start_request(
                FightPhaseStartRequestContext(state=state, decisions=DecisionController())
            )
            is None
        ), shape_name

    assert (
        eligible_selection_target_unit_ids(
            state=state,
            source_player_id=source_army.player_id,
            source_unit_instance_id=source_army.units[0].unit_instance_id,
            source_model_instance_id=None,
            selection_clause=invalid_shapes[1][1],
            explicit_target_unit_ids=None,
        )
        == ()
    )


def test_catalog_post_shoot_rejects_unsupported_selection_clause() -> None:
    selection_clause = replace(
        _post_shoot_hit_selection_clause(),
        diagnostics=(
            RuleParseDiagnostic(
                reason=RuleUnsupportedReason.UNSUPPORTED_LANGUAGE,
                message="unsupported-selection",
                source_span=_span(),
            ),
        ),
    )
    rule_ir = _rule_ir(
        source_id="test:selected-target:post-shoot:unsupported-selection",
        clauses=(
            selection_clause,
            _effect_clause(
                clause_id="test:selected-target:selection:post-shoot:unsupported-selection:effect",
                duration=_duration("phase"),
                effect_kind=RuleEffectKind.MODIFY_DICE_ROLL,
                roll_type="attack_sequence.hit",
                delta=1,
            ),
        ),
    )
    record = _ability_record(
        record_id="record:selected-target:post-shoot:unsupported-selection",
        rule_ir=rule_ir,
        trigger_kind=TimingTriggerKind.JUST_AFTER_FRIENDLY_UNIT_HAS_SHOT,
        runtime_clause_id=selection_clause.clause_id,
    )
    source_army, target_army = _mustered_core_armies()
    index = AbilityCatalogIndex.from_records((record,))
    runtime = CatalogSelectedTargetEffectRuntime(
        ability_indexes_by_player_id={
            source_army.player_id: index,
            target_army.player_id: AbilityCatalogIndex.from_records(()),
        },
        armies=(source_army, target_army),
    )

    assert not clause_is_post_shoot_hit_target_selection(selection_clause)
    assert post_shoot_hit_target_effect_clause_ids(rule_ir) == ()
    assert CATALOG_IR_POST_SHOOT_HIT_TARGET_EFFECT_CONSUMER_ID not in (
        catalog_rule_ir_consumers_for_rule(rule_ir)
    )
    assert CATALOG_IR_POST_SHOOT_HIT_TARGET_EFFECT_CONSUMER_ID not in (
        catalog_rule_ir_hook_ids_for_rule(rule_ir)
    )
    assert not has_post_shoot_hit_target_effect_records({source_army.player_id: index})
    assert runtime.attack_sequence_completed_bindings() == ()


def test_catalog_selected_target_support_filters_generic_records_by_timing() -> None:
    fight_selection = _fight_start_selection_clause()
    fight_rule_ir = _rule_ir(
        source_id="test:selected-target:fight",
        clauses=(
            fight_selection,
            _effect_clause(
                clause_id="test:selected-target:selection:fight:effect",
                duration=_duration("phase"),
                effect_kind=RuleEffectKind.REROLL_PERMISSION,
                roll_type="attack_sequence.hit",
            ),
        ),
    )
    fight_record = _ability_record(
        record_id="record:selected-target:fight",
        rule_ir=fight_rule_ir,
        trigger_kind=TimingTriggerKind.START_PHASE,
        runtime_clause_id=fight_selection.clause_id,
    )
    any_phase_record = _ability_record(
        record_id="record:selected-target:any-phase",
        rule_ir=fight_rule_ir,
        trigger_kind=TimingTriggerKind.ANY_PHASE,
        runtime_clause_id=fight_selection.clause_id,
    )
    non_generic_record = _ability_record(
        record_id="record:selected-target:non-generic",
        rule_ir=fight_rule_ir,
        trigger_kind=TimingTriggerKind.START_PHASE,
        handler_id="record-only",
    )
    post_shoot_rule_ir = _rule_ir(
        source_id="test:selected-target:post-shoot",
        clauses=(
            _post_shoot_hit_selection_clause(),
            _effect_clause(
                clause_id="test:selected-target:selection:post-shoot:effect",
                duration=_duration("phase"),
                effect_kind=RuleEffectKind.MODIFY_DICE_ROLL,
                roll_type="attack_sequence.hit",
                delta=1,
            ),
        ),
    )
    post_shoot_record = _ability_record(
        record_id="record:selected-target:post-shoot",
        rule_ir=post_shoot_rule_ir,
        trigger_kind=TimingTriggerKind.JUST_AFTER_FRIENDLY_UNIT_HAS_SHOT,
    )
    index = AbilityCatalogIndex.from_records(
        (fight_record, any_phase_record, non_generic_record, post_shoot_record)
    )

    assert records_for_timing(index, TimingTriggerKind.START_PHASE) == (
        any_phase_record,
        fight_record,
    )
    assert has_fight_start_selected_target_records({"player-a": index})
    assert has_post_shoot_hit_target_effect_records({"player-a": index})
    assert catalog_selected_target_clauses_from_record(fight_record) == fight_rule_ir.clauses
    assert runtime_clause_id_from_record(fight_record) == fight_selection.clause_id
    with pytest.raises(GameLifecycleError, match="requires AbilityCatalogRecord"):
        catalog_selected_target_clauses_from_record(cast(AbilityCatalogRecord, object()))
    with pytest.raises(GameLifecycleError, match="requires AbilityCatalogRecord"):
        runtime_clause_id_from_record(cast(AbilityCatalogRecord, object()))


def test_catalog_reserve_arrival_restriction_runtime_enforces_aethersense_rule_ir() -> None:
    source_army, target_army = _mustered_core_armies()
    catalog = ArmyCatalog.phase9a_canonical_content_pack()
    target_request = _muster_request(
        catalog=catalog,
        player_id=target_army.player_id,
        army_id=target_army.army_id,
    )
    target_selection = target_request.unit_selections[0]
    target_army = muster_army(
        catalog=catalog,
        request=replace(
            target_request,
            unit_selections=(
                target_selection,
                replace(target_selection, unit_selection_id="army-beta-reserve-unit"),
            ),
        ),
    )
    source_unit = replace(
        source_army.units[0],
        own_models=(source_army.units[0].own_models[0],),
    )
    source_army = _army_with_unit(source_army, source_unit)
    placed_target_unit, target_unit = target_army.units
    battlefield = BattlefieldRuntimeState(
        battlefield_id="catalog-aethersense-battlefield",
        battlefield_width_inches=60.0,
        battlefield_depth_inches=44.0,
        placed_armies=(
            _placed_army(
                army=source_army,
                unit=source_unit,
                model_xs=_model_xs_for_unit(unit=source_unit, start_x=10.0),
            ),
            _placed_army(
                army=target_army,
                unit=placed_target_unit,
                model_xs=_model_xs_for_unit(unit=placed_target_unit, start_x=45.0),
            ),
        ),
    )
    scenario = BattlefieldScenario(
        armies=(source_army, target_army),
        battlefield_state=battlefield,
    )
    state = _state_with_battlefield(
        armies=(source_army, target_army),
        battlefield=battlefield,
        active_player_id=target_army.player_id,
        phase=BattlePhase.MOVEMENT,
    )
    reserve_state = ReserveState(
        player_id=target_army.player_id,
        unit_instance_id=target_unit.unit_instance_id,
        reserve_origin=ReserveOrigin.DECLARE_BATTLE_FORMATIONS,
        reserve_kind=ReserveKind.STRATEGIC_RESERVES,
        declared_during_step="declare_battle_formations",
        entered_reserves_battle_round=None,
        entered_reserves_phase=None,
        destruction_deadline_policy=ReserveDestructionTimingPolicy(
            timing_kind=ReserveDestructionTimingKind.END_OF_BATTLE,
        ),
    )
    rule_ir_payload = kharseth_package.datasheet_rule_ir_payload_by_source_row_id("000004194:4")
    assert rule_ir_payload is not None
    record = _ability_record(
        record_id="record:aeldari:kharseth:aethersense",
        rule_ir=RuleIR.from_payload(rule_ir_payload),
        trigger_kind=TimingTriggerKind.ANY_PHASE,
        datasheet_id=source_unit.datasheet_id,
    )
    runtime = CatalogReserveArrivalRestrictionRuntime(
        ability_indexes_by_player_id={
            source_army.player_id: AbilityCatalogIndex.from_records((record,)),
            target_army.player_id: AbilityCatalogIndex.from_records(()),
        },
        armies=(source_army, target_army),
    )
    registry = ReserveArrivalRestrictionHookRegistry.from_bindings(runtime.bindings())

    near_placement = _unit_placement_for_test(
        army=target_army,
        unit=target_unit,
        model_xs=_model_xs_for_unit(unit=target_unit, start_x=23.0),
    )
    source_model = source_unit.own_models[0]
    arriving_model = target_unit.own_models[0]
    source_geometry = geometry_model_for_placement(
        model=source_model,
        placement=battlefield.model_placement_by_id(source_model.model_instance_id),
    )
    near_geometry = geometry_model_for_placement(
        model=arriving_model,
        placement=near_placement.model_placements[0],
    )
    assert near_geometry.pose.distance_2d_to(source_geometry.pose) == 13.0
    assert near_geometry.range_to(source_geometry) < 12.0
    context = ReserveArrivalRestrictionContext(
        state=state,
        scenario=scenario,
        reserve_state=reserve_state,
        rules_unit=rules_unit_view_from_armies(
            armies=scenario.armies,
            unit_instance_id=target_unit.unit_instance_id,
        ),
        attempted_rules_unit_placement=RulesUnitPlacement.single(near_placement),
        placement_kind=BattlefieldPlacementKind.STRATEGIC_RESERVES,
    )
    restrictions = registry.restrictions_for(context)

    assert restrictions
    assert {restriction.minimum_distance_inches for restriction in restrictions} == {12.0}
    assert {restriction.catalog_record_id for restriction in restrictions} == {record.record_id}
    assert all(
        restriction.replay_payload
        == {
            "ability_id": record.definition.ability_id,
            "catalog_record_id": record.record_id,
            "catalog_source_rule_id": record.definition.source_id,
            "clause_id": "phase17k:aeldari:kharseth:000004194:4:clause:001",
            "source_unit_instance_id": source_unit.unit_instance_id,
        }
        for restriction in restrictions
    )
    violations = reserve_arrival_restriction_violations(
        state=state,
        scenario=scenario,
        reserve_state=reserve_state,
        rules_unit=context.rules_unit,
        attempted_rules_unit_placement=context.attempted_rules_unit_placement,
        placement_kind=BattlefieldPlacementKind.STRATEGIC_RESERVES,
        registry=registry,
    )
    assert violations
    assert {violation.violation_code for violation in violations} == {
        ReservePlacementViolationCode.RESERVE_ARRIVAL_ABILITY_RESTRICTION
    }

    source_radius = source_geometry.base.max_radius()
    arriving_radius = near_geometry.base.max_radius()
    exact_center_gap = 12.0 + source_radius + arriving_radius
    exact_placement = _unit_placement_for_test(
        army=target_army,
        unit=target_unit,
        model_xs=_model_xs_for_unit(unit=target_unit, start_x=10.0 + exact_center_gap),
    )
    exact_geometry = geometry_model_for_placement(
        model=arriving_model,
        placement=exact_placement.model_placements[0],
    )
    assert exact_geometry.pose.distance_2d_to(source_geometry.pose) == exact_center_gap
    assert math.isclose(exact_geometry.range_to(source_geometry), 12.0, abs_tol=1e-12)
    exact_violations = reserve_arrival_restriction_violations(
        state=state,
        scenario=scenario,
        reserve_state=reserve_state,
        rules_unit=context.rules_unit,
        attempted_rules_unit_placement=RulesUnitPlacement.single(exact_placement),
        placement_kind=BattlefieldPlacementKind.STRATEGIC_RESERVES,
        registry=registry,
    )
    assert {violation.violation_code for violation in exact_violations} == {
        ReservePlacementViolationCode.RESERVE_ARRIVAL_ABILITY_RESTRICTION
    }

    epsilon = 1e-6
    outside_placement = _unit_placement_for_test(
        army=target_army,
        unit=target_unit,
        model_xs=_model_xs_for_unit(
            unit=target_unit,
            start_x=10.0 + exact_center_gap + epsilon,
        ),
    )
    outside_geometry = geometry_model_for_placement(
        model=arriving_model,
        placement=outside_placement.model_placements[0],
    )
    assert outside_geometry.range_to(source_geometry) > 12.0
    assert not registry.restrictions_for(
        replace(
            context,
            attempted_rules_unit_placement=RulesUnitPlacement.single(outside_placement),
        )
    )
    assert not reserve_arrival_restriction_violations(
        state=state,
        scenario=scenario,
        reserve_state=reserve_state,
        rules_unit=context.rules_unit,
        attempted_rules_unit_placement=RulesUnitPlacement.single(outside_placement),
        placement_kind=BattlefieldPlacementKind.STRATEGIC_RESERVES,
        registry=registry,
    )


def test_catalog_post_shoot_runtime_enforces_fury_weapon_filter_and_strength_effect() -> None:
    source_army, target_army = _mustered_core_armies()
    source_unit = replace(
        source_army.units[0],
        own_models=(source_army.units[0].own_models[0],),
        keywords=(*source_army.units[0].keywords, "AELDARI"),
    )
    source_army = _army_with_unit(source_army, source_unit)
    target_unit = target_army.units[0]
    battlefield = _battlefield_for_units(
        source_army=source_army,
        source_unit=source_unit,
        source_x=10.0,
        target_army=target_army,
        target_unit=target_unit,
        target_x=20.0,
    )
    state = _state_with_battlefield(
        armies=(source_army, target_army),
        battlefield=battlefield,
        active_player_id=source_army.player_id,
        phase=BattlePhase.SHOOTING,
    )
    rule_ir_payload = kharseth_package.datasheet_rule_ir_payload_by_source_row_id("000004194:5")
    assert rule_ir_payload is not None
    record = _ability_record(
        record_id="record:aeldari:kharseth:fury-of-the-void",
        rule_ir=RuleIR.from_payload(rule_ir_payload),
        trigger_kind=TimingTriggerKind.JUST_AFTER_FRIENDLY_UNIT_HAS_SHOT,
        datasheet_id=source_unit.datasheet_id,
    )
    ability_indexes_by_player_id = {
        source_army.player_id: AbilityCatalogIndex.from_records((record,)),
        target_army.player_id: AbilityCatalogIndex.from_records(()),
    }
    runtime = CatalogSelectedTargetEffectRuntime(
        ability_indexes_by_player_id=ability_indexes_by_player_id,
        armies=(source_army, target_army),
    )
    base_profile = _first_catalog_weapon_profile()
    dread_profile = replace(base_profile, name="Dread of the Deep Void")
    other_profile = replace(base_profile, profile_id="test:other-profile", name="Other Weapon")
    source_model_id = source_unit.own_models[0].model_instance_id

    def sequence_for(profile: WeaponProfile, *, sequence_id: str) -> AttackSequence:
        return AttackSequence(
            sequence_id=sequence_id,
            attacker_player_id=source_army.player_id,
            attacking_unit_instance_id=source_unit.unit_instance_id,
            source_phase=BattlePhase.SHOOTING,
            attack_pools=(
                RangedAttackPool(
                    attacker_model_instance_id=source_model_id,
                    weapon_instance_id=f"weapon-instance:test:{sequence_id}",
                    wargear_id=f"wargear:{sequence_id}",
                    weapon_profile_id=profile.profile_id,
                    weapon_profile=profile,
                    target_unit_instance_id=target_unit.unit_instance_id,
                    shooting_type=ShootingType.NORMAL,
                    attacks=1,
                    target_visible_model_ids=target_unit.own_model_ids(),
                    target_in_range_model_ids=target_unit.own_model_ids(),
                ),
            ),
        )

    decisions = DecisionController()
    binding = runtime.attack_sequence_completed_bindings()[0]
    wrong_weapon_sequence = sequence_for(
        other_profile,
        sequence_id="attack-sequence:kharseth:fury:wrong-weapon",
    )
    decisions.event_log.append(
        "attack_sequence_step",
        {
            "sequence_id": wrong_weapon_sequence.sequence_id,
            "step": AttackSequenceStep.HIT.value,
            "pool_index": 0,
            "payload": {"successful": True},
        },
    )
    wrong_status = binding.handler(
        AttackSequenceCompletedContext(
            state=state,
            decisions=decisions,
            dice_manager=DiceRollManager(state.game_id, event_log=decisions.event_log),
            runtime_modifier_registry=RuntimeModifierRegistry.empty(),
            source_phase=BattlePhase.SHOOTING,
            attack_sequence=wrong_weapon_sequence,
            attack_sequence_completed_event_id="event:kharseth:fury:wrong-weapon",
        )
    )
    assert wrong_status is None
    assert not decisions.queue.pending_requests

    dread_sequence = sequence_for(
        dread_profile,
        sequence_id="attack-sequence:kharseth:fury:dread",
    )
    non_active_state = _state_with_battlefield(
        armies=(source_army, target_army),
        battlefield=battlefield,
        active_player_id=target_army.player_id,
        phase=BattlePhase.SHOOTING,
    )
    non_active_decisions = DecisionController()
    non_active_decisions.event_log.append(
        "attack_sequence_step",
        {
            "sequence_id": dread_sequence.sequence_id,
            "step": AttackSequenceStep.HIT.value,
            "pool_index": 0,
            "payload": {"successful": True},
        },
    )
    non_active_status = binding.handler(
        AttackSequenceCompletedContext(
            state=non_active_state,
            decisions=non_active_decisions,
            dice_manager=DiceRollManager(
                non_active_state.game_id,
                event_log=non_active_decisions.event_log,
            ),
            runtime_modifier_registry=RuntimeModifierRegistry.empty(),
            source_phase=BattlePhase.SHOOTING,
            attack_sequence=dread_sequence,
            attack_sequence_completed_event_id="event:kharseth:fury:non-active-attacker",
        )
    )
    assert non_active_status is None
    assert not non_active_decisions.queue.pending_requests
    assert not non_active_state.persisting_effects

    decisions.event_log.append(
        "attack_sequence_step",
        {
            "sequence_id": dread_sequence.sequence_id,
            "step": AttackSequenceStep.HIT.value,
            "pool_index": 0,
            "payload": {"successful": True},
        },
    )
    status = binding.handler(
        AttackSequenceCompletedContext(
            state=state,
            decisions=decisions,
            dice_manager=DiceRollManager(state.game_id, event_log=decisions.event_log),
            runtime_modifier_registry=RuntimeModifierRegistry.empty(),
            source_phase=BattlePhase.SHOOTING,
            attack_sequence=dread_sequence,
            attack_sequence_completed_event_id="event:kharseth:fury:dread",
        )
    )
    assert status is not None
    assert status.status_kind is LifecycleStatusKind.WAITING_FOR_DECISION
    request = decisions.queue.peek_next()
    request_payload = cast(dict[str, JsonValue], request.payload)
    assert request_payload["available_target_unit_instance_ids"] == [target_unit.unit_instance_id]
    result = DecisionResult.for_request(
        result_id="result:kharseth:fury",
        request=request,
        selected_option_id=request.options[0].option_id,
    )
    decisions.submit_result(result)
    assert (
        apply_catalog_post_shoot_hit_target_effect_result(
            state=state,
            decisions=decisions,
            result=result,
            battle_shock_hooks=BattleShockHookRegistry.empty(),
            runtime_modifier_registry=RuntimeModifierRegistry.empty(),
            ability_indexes_by_player_id=ability_indexes_by_player_id,
        )
        is None
    )

    assert len(state.persisting_effects) == 1
    effect = state.persisting_effects[0]
    assert effect.target_unit_instance_ids == (source_unit.unit_instance_id,)
    assert effect.expiration == EffectExpiration.end_turn(
        battle_round=state.battle_round,
        player_id=source_army.player_id,
    )
    modifier_context = WeaponProfileModifierContext(
        state=state,
        source_phase=BattlePhase.SHOOTING,
        attacking_unit_instance_id=source_unit.unit_instance_id,
        attacker_model_instance_id=source_model_id,
        target_unit_instance_id=target_unit.unit_instance_id,
        weapon_profile=base_profile,
    )
    modified = RuntimeModifierRegistry.empty().modified_weapon_profile(modifier_context)
    assert modified.strength.final == base_profile.strength.final + 1
    assert modified.source_ids == (
        f"{record.definition.source_id}:"
        "phase17k:aeldari:kharseth:000004194:5:clause:002:modify_characteristic",
    )
    assert (
        RuntimeModifierRegistry.empty().modified_weapon_profile(
            replace(
                modifier_context,
                target_unit_instance_id=source_unit.unit_instance_id,
            )
        )
        == base_profile
    )


def test_catalog_post_shoot_roleless_negative_modifier_is_normalized_to_attacker() -> None:
    source_army, target_army = _mustered_core_armies()
    source_unit = source_army.units[0]
    target_unit = target_army.units[0]
    battlefield = _battlefield_for_units(
        source_army=source_army,
        source_unit=source_unit,
        source_x=10.0,
        target_army=target_army,
        target_unit=target_unit,
        target_x=20.0,
    )
    state = _state_with_battlefield(
        armies=(source_army, target_army),
        battlefield=battlefield,
        active_player_id=source_army.player_id,
        phase=BattlePhase.SHOOTING,
    )
    selection_clause = _post_shoot_hit_selection_clause()
    effect_clause = RuleClause(
        clause_id="test:selected-target:selection:post-shoot:negative-hit-effect",
        source_span=_span(),
        trigger=_post_shoot_effect_trigger(actor="this_model"),
        conditions=(
            _condition(
                RuleConditionKind.TARGET_CONSTRAINT,
                ("gate_subject", "attack_target"),
                ("relationship", "this_model_makes_attack"),
                ("target_reference", "selected_unit"),
            ),
        ),
        target=RuleTargetSpec(
            kind=RuleTargetKind.THIS_MODEL,
            source_span=_span(),
        ),
        effects=(
            _effect(
                RuleEffectKind.MODIFY_DICE_ROLL,
                ("roll_type", "attack_sequence.hit"),
                ("delta", -1),
            ),
        ),
        duration=_duration("phase"),
    )
    rule_ir = _rule_ir(
        source_id="test:selected-target:post-shoot:negative-hit",
        clauses=(selection_clause, effect_clause),
    )
    record = _ability_record(
        record_id="record:selected-target:post-shoot:negative-hit",
        rule_ir=rule_ir,
        trigger_kind=TimingTriggerKind.JUST_AFTER_FRIENDLY_UNIT_HAS_SHOT,
        runtime_clause_id=selection_clause.clause_id,
    )
    ability_indexes_by_player_id = {
        source_army.player_id: AbilityCatalogIndex.from_records((record,)),
        target_army.player_id: AbilityCatalogIndex.from_records(()),
    }
    runtime = CatalogSelectedTargetEffectRuntime(
        ability_indexes_by_player_id=ability_indexes_by_player_id,
        armies=(source_army, target_army),
    )

    assert catalog_rule_ir_consumers_for_rule(rule_ir) == (
        CATALOG_IR_POST_SHOOT_HIT_TARGET_EFFECT_CONSUMER_ID,
    )
    assert post_shoot_hit_target_effect_clause_ids(rule_ir) == (effect_clause.clause_id,)
    assert has_post_shoot_hit_target_effect_records(ability_indexes_by_player_id)
    bindings = runtime.attack_sequence_completed_bindings()
    assert len(bindings) == 1

    profile = replace(_first_catalog_weapon_profile(), name="Dread of the Deep Void")
    source_model_id = source_unit.own_models[0].model_instance_id
    sequence = AttackSequence(
        sequence_id="attack-sequence:post-shoot:negative-hit",
        attacker_player_id=source_army.player_id,
        attacking_unit_instance_id=source_unit.unit_instance_id,
        source_phase=BattlePhase.SHOOTING,
        attack_pools=(
            RangedAttackPool(
                attacker_model_instance_id=source_model_id,
                weapon_instance_id="weapon-instance:test:post-shoot:negative-hit",
                wargear_id="wargear:post-shoot:negative-hit",
                weapon_profile_id=profile.profile_id,
                weapon_profile=profile,
                target_unit_instance_id=target_unit.unit_instance_id,
                shooting_type=ShootingType.NORMAL,
                attacks=1,
                target_visible_model_ids=target_unit.own_model_ids(),
                target_in_range_model_ids=target_unit.own_model_ids(),
            ),
        ),
    )
    decisions = DecisionController()
    decisions.event_log.append(
        "attack_sequence_step",
        {
            "sequence_id": sequence.sequence_id,
            "step": AttackSequenceStep.HIT.value,
            "pool_index": 0,
            "payload": {"successful": True},
        },
    )
    status = bindings[0].handler(
        AttackSequenceCompletedContext(
            state=state,
            decisions=decisions,
            dice_manager=DiceRollManager(state.game_id, event_log=decisions.event_log),
            runtime_modifier_registry=RuntimeModifierRegistry.empty(),
            source_phase=BattlePhase.SHOOTING,
            attack_sequence=sequence,
            attack_sequence_completed_event_id="event:post-shoot:negative-hit",
        )
    )
    assert status is not None
    assert status.status_kind is LifecycleStatusKind.WAITING_FOR_DECISION
    request = decisions.queue.peek_next()
    result = DecisionResult.for_request(
        result_id="result:post-shoot:negative-hit",
        request=request,
        selected_option_id=request.options[0].option_id,
    )
    decisions.submit_result(result)
    assert (
        apply_catalog_post_shoot_hit_target_effect_result(
            state=state,
            decisions=decisions,
            result=result,
            battle_shock_hooks=BattleShockHookRegistry.empty(),
            runtime_modifier_registry=RuntimeModifierRegistry.empty(),
            ability_indexes_by_player_id=ability_indexes_by_player_id,
        )
        is None
    )

    assert len(state.persisting_effects) == 1
    effect = state.persisting_effects[0]
    assert effect.target_unit_instance_ids == (source_unit.unit_instance_id,)
    effect_payload = cast(dict[str, JsonValue], effect.effect_payload)
    effect_spec_payload = cast(dict[str, JsonValue], effect_payload["effect"])
    effect_parameters = {
        cast(str, item["key"]): item["value"]
        for item in cast(list[dict[str, JsonValue]], effect_spec_payload["parameters"])
    }
    assert effect_parameters["attack_role"] == "attacker"
    assert effect_parameters["delta"] == -1
    assert effect_parameters["selected_target_unit_instance_id"] == target_unit.unit_instance_id
    selected_metadata = cast(dict[str, JsonValue], effect_payload["catalog_selected_target"])
    assert selected_metadata["source_model_instance_id"] == source_model_id

    modifier_context = HitRollModifierContext(
        state=state,
        attacking_unit_instance_id=source_unit.unit_instance_id,
        attacker_model_instance_id=source_model_id,
        target_unit_instance_id=target_unit.unit_instance_id,
        weapon_profile=profile,
        source_phase=BattlePhase.SHOOTING,
    )
    assert RuntimeModifierRegistry.empty().hit_roll_modifier(modifier_context) == -1
    other_source_model_id = source_unit.own_models[1].model_instance_id
    assert (
        RuntimeModifierRegistry.empty().hit_roll_modifier(
            replace(modifier_context, attacker_model_instance_id=other_source_model_id)
        )
        == 0
    )
    assert (
        RuntimeModifierRegistry.empty().hit_roll_modifier(
            replace(
                modifier_context,
                attacking_unit_instance_id=target_unit.unit_instance_id,
                attacker_model_instance_id=target_unit.own_models[0].model_instance_id,
                target_unit_instance_id=source_unit.unit_instance_id,
            )
        )
        == 0
    )


def test_july_fluxmaster_passive_defences_use_generic_catalog_runtime() -> None:
    source_army, enemy_army = _mustered_core_armies()
    source_unit = source_army.units[0]
    enemy_unit = enemy_army.units[0]
    battlefield = _battlefield_for_units(
        source_army=source_army,
        source_unit=source_unit,
        source_x=10.0,
        target_army=enemy_army,
        target_unit=enemy_unit,
        target_x=20.0,
    )
    state = _state_with_battlefield(
        armies=(source_army, enemy_army),
        battlefield=battlefield,
        active_player_id=enemy_army.player_id,
        phase=BattlePhase.SHOOTING,
    )
    records = tuple(
        replace(record, datasheet_id=source_unit.datasheet_id)
        for record in chaos_daemons_july_updates.runtime_contribution().ability_records
        if record.datasheet_id == chaos_daemons_july_updates.FLUXMASTER_DATASHEET_ID
    )
    runtime = CatalogDatasheetRuleRuntime(
        {
            source_army.player_id: AbilityCatalogIndex.from_records(records),
            enemy_army.player_id: AbilityCatalogIndex.from_records(()),
        },
        (source_army, enemy_army),
    )
    registry = RuntimeModifierRegistry.from_bindings(
        hit_roll_modifier_bindings=runtime.hit_roll_modifier_bindings(),
    )
    ranged_profile = WeaponProfile(
        profile_id="july-fluxmaster-ranged",
        name="July Fluxmaster ranged test",
        range_profile=RangeProfile.distance(24),
        attack_profile=AttackProfile.fixed(1),
        skill=CharacteristicValue.from_raw(Characteristic.BALLISTIC_SKILL, 3),
        strength=CharacteristicValue.from_raw(Characteristic.STRENGTH, 4),
        armor_penetration=CharacteristicValue.from_raw(
            Characteristic.ARMOR_PENETRATION,
            0,
        ),
        damage_profile=DamageProfile.fixed(1),
    )
    context = HitRollModifierContext(
        state=state,
        attacking_unit_instance_id=enemy_unit.unit_instance_id,
        attacker_model_instance_id=enemy_unit.own_models[0].model_instance_id,
        target_unit_instance_id=source_unit.unit_instance_id,
        weapon_profile=ranged_profile,
        source_phase=BattlePhase.SHOOTING,
    )

    assert registry.hit_roll_modifier(context) == -1
    assert (
        registry.hit_roll_modifier(
            replace(
                context,
                weapon_profile=replace(
                    ranged_profile,
                    profile_id="july-fluxmaster-melee",
                    range_profile=RangeProfile.melee(),
                    skill=CharacteristicValue.from_raw(
                        Characteristic.WEAPON_SKILL,
                        3,
                    ),
                ),
                source_phase=BattlePhase.FIGHT,
            )
        )
        == -1
    )
    assert (
        registry.hit_roll_modifier(
            replace(
                context,
                target_unit_instance_id=enemy_unit.unit_instance_id,
            )
        )
        == 0
    )


def test_catalog_post_shoot_wargear_model_effect_is_limited_to_current_bearer() -> None:
    source_army, target_army = _mustered_core_armies()
    source_army_without_bearer = source_army
    source_unit = source_army.units[0]
    wargear_id = "wargear:post-shoot:model-ability"
    bearer_model = replace(
        source_unit.own_models[0],
        wargear_ids=(*source_unit.own_models[0].wargear_ids, wargear_id),
    )
    source_unit = replace(source_unit, own_models=(bearer_model, *source_unit.own_models[1:]))
    source_army = _army_with_unit(source_army, source_unit)
    target_unit = target_army.units[0]
    battlefield = _battlefield_for_units(
        source_army=source_army,
        source_unit=source_unit,
        source_x=10.0,
        target_army=target_army,
        target_unit=target_unit,
        target_x=20.0,
    )
    state = _state_with_battlefield(
        armies=(source_army, target_army),
        battlefield=battlefield,
        active_player_id=source_army.player_id,
        phase=BattlePhase.SHOOTING,
    )
    selection_clause = _post_shoot_hit_selection_clause()
    effect_clause = RuleClause(
        clause_id="test:selected-target:selection:post-shoot:wargear-model-effect",
        source_span=_span(),
        trigger=_post_shoot_effect_trigger(actor="this_model"),
        target=RuleTargetSpec(kind=RuleTargetKind.THIS_MODEL, source_span=_span()),
        effects=(
            _effect(
                RuleEffectKind.MODIFY_DICE_ROLL,
                ("roll_type", "attack_sequence.hit"),
                ("delta", -1),
            ),
        ),
        duration=_duration("phase"),
    )
    rule_ir = _rule_ir(
        source_id="test:selected-target:post-shoot:wargear-model-effect",
        clauses=(selection_clause, effect_clause),
    )
    record = _ability_record(
        record_id="record:selected-target:post-shoot:wargear-model-effect",
        rule_ir=rule_ir,
        trigger_kind=TimingTriggerKind.JUST_AFTER_FRIENDLY_UNIT_HAS_SHOT,
        runtime_clause_id=selection_clause.clause_id,
        source_kind=AbilitySourceKind.WARGEAR,
        datasheet_id=source_unit.datasheet_id,
        wargear_id=wargear_id,
    )
    ability_indexes_by_player_id = {
        source_army.player_id: AbilityCatalogIndex.from_records((record,)),
        target_army.player_id: AbilityCatalogIndex.from_records(()),
    }
    runtime = CatalogSelectedTargetEffectRuntime(
        ability_indexes_by_player_id=ability_indexes_by_player_id,
        armies=(source_army, target_army),
    )
    no_bearer_runtime = CatalogSelectedTargetEffectRuntime(
        ability_indexes_by_player_id=ability_indexes_by_player_id,
        armies=(source_army_without_bearer, target_army),
    )
    assert no_bearer_runtime.attack_sequence_completed_bindings() == ()
    binding = runtime.attack_sequence_completed_bindings()[0]
    profile = replace(_first_catalog_weapon_profile(), name="Dread of the Deep Void")

    def successful_sequence(
        *,
        source_model_id: str,
        suffix: str,
    ) -> tuple[AttackSequence, DecisionController]:
        sequence = AttackSequence(
            sequence_id=f"attack-sequence:post-shoot:wargear-model-effect:{suffix}",
            attacker_player_id=source_army.player_id,
            attacking_unit_instance_id=source_unit.unit_instance_id,
            source_phase=BattlePhase.SHOOTING,
            attack_pools=(
                RangedAttackPool(
                    attacker_model_instance_id=source_model_id,
                    weapon_instance_id=f"weapon-instance:test:post-shoot:{suffix}",
                    wargear_id="wargear:post-shoot:attack",
                    weapon_profile_id=profile.profile_id,
                    weapon_profile=profile,
                    target_unit_instance_id=target_unit.unit_instance_id,
                    shooting_type=ShootingType.NORMAL,
                    attacks=1,
                    target_visible_model_ids=target_unit.own_model_ids(),
                    target_in_range_model_ids=target_unit.own_model_ids(),
                ),
            ),
        )
        decisions = DecisionController()
        decisions.event_log.append(
            "attack_sequence_step",
            {
                "sequence_id": sequence.sequence_id,
                "step": AttackSequenceStep.HIT.value,
                "pool_index": 0,
                "payload": {"successful": True},
            },
        )
        return sequence, decisions

    non_bearer_model_id = source_unit.own_models[1].model_instance_id
    non_bearer_sequence, non_bearer_decisions = successful_sequence(
        source_model_id=non_bearer_model_id,
        suffix="non-bearer",
    )
    assert (
        binding.handler(
            AttackSequenceCompletedContext(
                state=state,
                decisions=non_bearer_decisions,
                dice_manager=DiceRollManager(
                    state.game_id,
                    event_log=non_bearer_decisions.event_log,
                ),
                runtime_modifier_registry=RuntimeModifierRegistry.empty(),
                source_phase=BattlePhase.SHOOTING,
                attack_sequence=non_bearer_sequence,
                attack_sequence_completed_event_id="event:post-shoot:wargear:non-bearer",
            )
        )
        is None
    )
    assert not non_bearer_decisions.queue.pending_requests

    bearer_model_id = bearer_model.model_instance_id
    bearer_sequence, bearer_decisions = successful_sequence(
        source_model_id=bearer_model_id,
        suffix="bearer",
    )
    status = binding.handler(
        AttackSequenceCompletedContext(
            state=state,
            decisions=bearer_decisions,
            dice_manager=DiceRollManager(state.game_id, event_log=bearer_decisions.event_log),
            runtime_modifier_registry=RuntimeModifierRegistry.empty(),
            source_phase=BattlePhase.SHOOTING,
            attack_sequence=bearer_sequence,
            attack_sequence_completed_event_id="event:post-shoot:wargear:bearer",
        )
    )
    assert status is not None
    assert status.status_kind is LifecycleStatusKind.WAITING_FOR_DECISION
    request = bearer_decisions.queue.peek_next()
    result = DecisionResult.for_request(
        result_id="result:post-shoot:wargear-model-effect",
        request=request,
        selected_option_id=request.options[0].option_id,
    )
    bearer_decisions.submit_result(result)
    assert (
        apply_catalog_post_shoot_hit_target_effect_result(
            state=state,
            decisions=bearer_decisions,
            result=result,
            battle_shock_hooks=BattleShockHookRegistry.empty(),
            runtime_modifier_registry=RuntimeModifierRegistry.empty(),
            ability_indexes_by_player_id=ability_indexes_by_player_id,
        )
        is None
    )
    assert len(state.persisting_effects) == 1
    effect_payload = cast(dict[str, JsonValue], state.persisting_effects[0].effect_payload)
    selected_metadata = cast(dict[str, JsonValue], effect_payload["catalog_selected_target"])
    assert selected_metadata["source_model_instance_id"] == bearer_model_id
    modifier_context = HitRollModifierContext(
        state=state,
        attacking_unit_instance_id=source_unit.unit_instance_id,
        attacker_model_instance_id=bearer_model_id,
        target_unit_instance_id=target_unit.unit_instance_id,
        weapon_profile=profile,
        source_phase=BattlePhase.SHOOTING,
    )
    assert RuntimeModifierRegistry.empty().hit_roll_modifier(modifier_context) == -1
    assert (
        RuntimeModifierRegistry.empty().hit_roll_modifier(
            replace(modifier_context, attacker_model_instance_id=non_bearer_model_id)
        )
        == 0
    )


def test_catalog_selected_target_fight_start_runtime_records_selected_effect() -> None:
    source_army, target_army = _mustered_core_armies()
    source_unit = source_army.units[0]
    target_unit = target_army.units[0]
    battlefield = _battlefield_for_units(
        source_army=source_army,
        source_unit=source_unit,
        source_x=10.0,
        target_army=target_army,
        target_unit=target_unit,
        target_x=10.4,
    )
    state = _state_with_battlefield(
        armies=(source_army, target_army),
        battlefield=battlefield,
        active_player_id=source_army.player_id,
        phase=BattlePhase.FIGHT,
    )
    selection_clause = _fight_start_selection_clause()
    effect_clause = _effect_clause(
        clause_id="test:selected-target:selection:fight:effect",
        duration=_duration("phase"),
        effect_kind=RuleEffectKind.REROLL_PERMISSION,
        roll_type="attack_sequence.hit",
    )
    rule_ir = _rule_ir(
        source_id="test:selected-target:fight-runtime",
        clauses=(selection_clause, effect_clause),
    )
    record = _ability_record(
        record_id="record:selected-target:fight-runtime",
        rule_ir=rule_ir,
        trigger_kind=TimingTriggerKind.START_PHASE,
        runtime_clause_id=selection_clause.clause_id,
    )
    runtime = CatalogSelectedTargetEffectRuntime(
        ability_indexes_by_player_id={
            source_army.player_id: AbilityCatalogIndex.from_records((record,)),
            target_army.player_id: AbilityCatalogIndex.from_records(()),
        },
        armies=(source_army, target_army),
    )
    decisions = DecisionController()

    bindings = runtime.fight_phase_start_bindings()
    request = runtime.fight_phase_start_request(
        FightPhaseStartRequestContext(state=state, decisions=decisions)
    )

    assert len(bindings) == 1
    assert request is not None
    assert request.decision_type == SELECT_FACTION_RULE_FIGHT_PHASE_START_OPTION_DECISION_TYPE
    assert [option.option_id for option in request.options] == sorted(
        option.option_id for option in request.options
    )
    assert len(request.options) == 1
    request_payload = cast(dict[str, JsonValue], request.payload)
    assert request_payload["catalog_record_id"] == record.record_id
    assert request_payload["available_target_unit_instance_ids"] == [target_unit.unit_instance_id]

    queued = decisions.request_decision(request)
    result = DecisionResult.for_request(
        result_id="result:selected-target:fight-runtime",
        request=queued,
        selected_option_id=queued.options[0].option_id,
    )
    decisions.submit_result(result)
    applied = runtime.apply_fight_phase_start_result(
        FightPhaseStartResultContext(
            state=state,
            decisions=decisions,
            request=queued,
            result=result,
        )
    )

    assert applied is True
    assert len(state.persisting_effects) == 1
    effect = state.persisting_effects[0]
    assert effect.owner_player_id == source_army.player_id
    assert effect.target_unit_instance_ids == (target_unit.unit_instance_id,)
    effect_payload = cast(dict[str, JsonValue], effect.effect_payload)
    selected_metadata = cast(dict[str, JsonValue], effect_payload["catalog_selected_target"])
    transformed_effect = cast(dict[str, JsonValue], effect_payload["effect"])
    assert selected_metadata["selected_target_unit_instance_id"] == target_unit.unit_instance_id
    assert selected_metadata["source_unit_instance_id"] == source_unit.unit_instance_id
    assert transformed_effect["kind"] == RuleEffectKind.REROLL_PERMISSION.value
    effect_parameters = cast(list[dict[str, JsonValue]], transformed_effect["parameters"])
    assert {cast(str, parameter["key"]): parameter["value"] for parameter in effect_parameters}[
        "selected_target_unit_instance_id"
    ] == target_unit.unit_instance_id
    assert (
        decisions.event_log.records[-1].event_type == CATALOG_SELECTED_TARGET_EFFECT_SELECTED_EVENT
    )


@pytest.mark.parametrize(
    "include_model_condition",
    [pytest.param(False), pytest.param(True)],
    ids=("without-model-condition", "with-model-condition"),
)
def test_catalog_fight_start_wargear_model_effect_uses_unit_geometry_and_binds_bearer(
    include_model_condition: bool,
) -> None:
    source_army, target_army = _mustered_core_armies()
    source_unit_template = replace(
        source_army.units[0],
        own_models=source_army.units[0].own_models[:2],
    )
    wargear_id = "wargear:fight-start:model-ability"
    bearer_model = replace(
        source_unit_template.own_models[0],
        wargear_ids=(*source_unit_template.own_models[0].wargear_ids, wargear_id),
    )
    source_unit_without_bearer = replace(
        source_unit_template,
        own_models=(
            replace(bearer_model, wounds_remaining=0),
            *source_unit_template.own_models[1:],
        ),
    )
    source_army_without_bearer = _army_with_unit(source_army, source_unit_without_bearer)
    source_unit = replace(
        source_unit_template,
        own_models=(bearer_model, *source_unit_template.own_models[1:]),
    )
    source_army = _army_with_unit(source_army, source_unit)
    target_unit = target_army.units[0]
    selection_clause = replace(
        _fight_start_selection_clause(),
        conditions=(_selection_engagement_range_condition(object_kind="unit"),),
    )
    effect_clause = RuleClause(
        clause_id="test:selected-target:selection:fight:wargear-model-effect",
        source_span=_span(),
        trigger=_post_shoot_effect_trigger(actor="this_model"),
        conditions=(
            (
                _condition(
                    RuleConditionKind.TARGET_CONSTRAINT,
                    ("gate_subject", "attack_target"),
                    ("relationship", "this_model_makes_attack"),
                    ("target_reference", "selected_unit"),
                ),
            )
            if include_model_condition
            else ()
        ),
        target=RuleTargetSpec(kind=RuleTargetKind.THIS_MODEL, source_span=_span()),
        effects=(
            _effect(
                RuleEffectKind.REROLL_PERMISSION,
                ("roll_type", "attack_sequence.hit"),
            ),
        ),
        duration=_duration("phase"),
    )
    rule_ir = _rule_ir(
        source_id="test:selected-target:fight:wargear-model-effect",
        clauses=(selection_clause, effect_clause),
    )
    record = _ability_record(
        record_id="record:selected-target:fight:wargear-model-effect",
        rule_ir=rule_ir,
        trigger_kind=TimingTriggerKind.START_PHASE,
        runtime_clause_id=selection_clause.clause_id,
        source_kind=AbilitySourceKind.WARGEAR,
        datasheet_id=source_unit.datasheet_id,
        wargear_id=wargear_id,
    )
    ability_indexes_by_player_id = {
        source_army.player_id: AbilityCatalogIndex.from_records((record,)),
        target_army.player_id: AbilityCatalogIndex.from_records(()),
    }

    assert fight_start_selected_target_effect_clause_ids(rule_ir) == (effect_clause.clause_id,)
    assert CATALOG_IR_SELECTED_TARGET_EFFECT_CONSUMER_ID in catalog_rule_ir_consumers_for_rule(
        rule_ir
    )
    no_bearer_runtime = CatalogSelectedTargetEffectRuntime(
        ability_indexes_by_player_id=ability_indexes_by_player_id,
        armies=(source_army_without_bearer, target_army),
    )
    no_bearer_state = _state_with_battlefield(
        armies=(source_army_without_bearer, target_army),
        battlefield=_battlefield_for_units_with_model_xs(
            source_army=source_army_without_bearer,
            source_unit=source_unit_without_bearer,
            source_model_xs=(30.0, 10.0),
            target_army=target_army,
            target_unit=target_unit,
            target_model_xs=_model_xs_for_unit(unit=target_unit, start_x=10.4),
        ),
        active_player_id=source_army_without_bearer.player_id,
        phase=BattlePhase.FIGHT,
    )
    assert no_bearer_runtime.fight_phase_start_bindings() == ()
    assert (
        no_bearer_runtime.fight_phase_start_request(
            FightPhaseStartRequestContext(
                state=no_bearer_state,
                decisions=DecisionController(),
            )
        )
        is None
    )

    state = _state_with_battlefield(
        armies=(source_army, target_army),
        battlefield=_battlefield_for_units_with_model_xs(
            source_army=source_army,
            source_unit=source_unit,
            source_model_xs=(30.0, 10.0),
            target_army=target_army,
            target_unit=target_unit,
            target_model_xs=_model_xs_for_unit(unit=target_unit, start_x=10.4),
        ),
        active_player_id=source_army.player_id,
        phase=BattlePhase.FIGHT,
    )
    runtime = CatalogSelectedTargetEffectRuntime(
        ability_indexes_by_player_id=ability_indexes_by_player_id,
        armies=(source_army, target_army),
    )
    assert len(runtime.fight_phase_start_bindings()) == 1
    decisions = DecisionController()
    request = runtime.fight_phase_start_request(
        FightPhaseStartRequestContext(state=state, decisions=decisions)
    )
    assert request is not None
    assert len(request.options) == 1
    queued = decisions.request_decision(request)
    result = DecisionResult.for_request(
        result_id="result:selected-target:fight:wargear-model-effect",
        request=queued,
        selected_option_id=queued.options[0].option_id,
    )
    decisions.submit_result(result)
    assert (
        runtime.apply_fight_phase_start_result(
            FightPhaseStartResultContext(
                state=state,
                decisions=decisions,
                request=queued,
                result=result,
            )
        )
        is True
    )
    assert len(state.persisting_effects) == 1
    effect_payload = cast(dict[str, JsonValue], state.persisting_effects[0].effect_payload)
    selected_metadata = cast(dict[str, JsonValue], effect_payload["catalog_selected_target"])
    bearer_model_id = bearer_model.model_instance_id
    non_bearer_model_id = source_unit.own_models[1].model_instance_id
    assert selected_metadata["source_model_instance_id"] == bearer_model_id
    bearer_permission = source_backed_reroll_permission_context_for_unit(
        state=state,
        player_id=source_army.player_id,
        unit_instance_id=source_unit.unit_instance_id,
        model_instance_id=bearer_model_id,
        roll_type="attack_sequence.hit",
        timing_window="attack_sequence.hit",
        attack_kind="melee",
        target_unit_instance_id=target_unit.unit_instance_id,
    )
    assert bearer_permission is not None
    assert (
        source_backed_reroll_permission_context_for_unit(
            state=state,
            player_id=source_army.player_id,
            unit_instance_id=source_unit.unit_instance_id,
            model_instance_id=non_bearer_model_id,
            roll_type="attack_sequence.hit",
            timing_window="attack_sequence.hit",
            attack_kind="melee",
            target_unit_instance_id=target_unit.unit_instance_id,
        )
        is None
    )


def test_catalog_post_shoot_hit_target_runtime_resolves_immediate_battle_shock() -> None:
    source_army, target_army = _mustered_core_armies()
    source_unit = source_army.units[0]
    target_unit = target_army.units[0]
    state = _state_without_battlefield(
        active_player_id=source_army.player_id,
        phase=BattlePhase.SHOOTING,
    )
    for army in (source_army, target_army):
        state.record_army_definition(army)
    state.battlefield_state = _battlefield_for_units(
        source_army=source_army,
        source_unit=source_unit,
        source_x=10.0,
        target_army=target_army,
        target_unit=target_unit,
        target_x=20.0,
    )
    record = _compiled_record(
        record_id="record:selected-target:post-shoot-battle-shock",
        raw_text=(
            "In your Shooting phase, after this model has shot, select one enemy unit that "
            "was hit by one or more of those attacks. That unit must take a Battle-shock test."
        ),
        source_unit=source_unit,
        trigger_kind=TimingTriggerKind.JUST_AFTER_FRIENDLY_UNIT_HAS_SHOT,
    )
    ability_indexes_by_player_id = {
        source_army.player_id: AbilityCatalogIndex.from_records((record,)),
        target_army.player_id: AbilityCatalogIndex.from_records(()),
    }
    runtime = CatalogSelectedTargetEffectRuntime(
        ability_indexes_by_player_id=ability_indexes_by_player_id,
        armies=(source_army, target_army),
    )
    profile = _first_catalog_weapon_profile()
    sequence = AttackSequence(
        sequence_id="attack-sequence:post-shoot-battle-shock",
        attacker_player_id=source_army.player_id,
        attacking_unit_instance_id=source_unit.unit_instance_id,
        source_phase=BattlePhase.SHOOTING,
        attack_pools=(
            RangedAttackPool(
                attacker_model_instance_id=source_unit.own_models[0].model_instance_id,
                weapon_instance_id="weapon-instance:test:post-shoot-battle-shock",
                wargear_id="catalog-post-shoot-test-wargear",
                weapon_profile_id=profile.profile_id,
                weapon_profile=profile,
                target_unit_instance_id=target_unit.unit_instance_id,
                shooting_type=ShootingType.NORMAL,
                attacks=1,
                target_visible_model_ids=target_unit.own_model_ids(),
                target_in_range_model_ids=target_unit.own_model_ids(),
            ),
        ),
    )
    decisions = DecisionController()
    decisions.event_log.append(
        "attack_sequence_step",
        {
            "sequence_id": sequence.sequence_id,
            "step": AttackSequenceStep.HIT.value,
            "pool_index": 0,
            "payload": {"successful": True},
        },
    )

    bindings = runtime.attack_sequence_completed_bindings()
    status = bindings[0].handler(
        AttackSequenceCompletedContext(
            state=state,
            decisions=decisions,
            dice_manager=DiceRollManager(state.game_id, event_log=decisions.event_log),
            runtime_modifier_registry=RuntimeModifierRegistry.empty(),
            source_phase=BattlePhase.SHOOTING,
            attack_sequence=sequence,
            attack_sequence_completed_event_id="event:post-shoot-battle-shock:completed",
        )
    )

    assert len(bindings) == 1
    assert status is not None
    assert status.status_kind is LifecycleStatusKind.WAITING_FOR_DECISION
    queued = decisions.queue.peek_next()
    queued_payload = cast(dict[str, JsonValue], queued.payload)
    assert queued_payload["available_target_unit_instance_ids"] == [target_unit.unit_instance_id]
    result = DecisionResult.for_request(
        result_id="result:selected-target:post-shoot-battle-shock",
        request=queued,
        selected_option_id=queued.options[0].option_id,
    )
    decisions.submit_result(result)

    apply_status = apply_catalog_post_shoot_hit_target_effect_result(
        state=state,
        decisions=decisions,
        result=result,
        battle_shock_hooks=BattleShockHookRegistry.empty(),
        runtime_modifier_registry=RuntimeModifierRegistry.empty(),
        ability_indexes_by_player_id=ability_indexes_by_player_id,
    )

    assert apply_status is None
    assert state.persisting_effects == []
    event_types = tuple(event.event_type for event in decisions.event_log.records)
    assert "battle_shock_test_requested" in event_types
    assert "battle_shock_test_resolved" in event_types
    assert "catalog_selected_target_battle_shock_resolved" in event_types
    assert CATALOG_POST_SHOOT_HIT_TARGET_EFFECT_SELECTED_EVENT in event_types


def test_catalog_once_per_battle_runtimes_ignore_disabled_records_before_parsing() -> None:
    source_army, target_army = _mustered_once_per_battle_armies()
    source_unit = source_army.units[0]
    target_unit = target_army.units[0]
    active = _once_per_battle_record(source_unit=source_unit)
    disabled = replace(
        active,
        definition=replace(
            active.definition,
            replay_payload={"disabled": True},
        ),
        disabled=True,
    )
    assert ability_record_is_active_generic_rule_ir(active)
    assert not ability_record_is_active_generic_rule_ir(disabled)
    with pytest.raises(GameLifecycleError, match="requires AbilityCatalogRecord"):
        ability_record_is_active_generic_rule_ir(cast(AbilityCatalogRecord, object()))
    indexes = {
        source_army.player_id: AbilityCatalogIndex.from_records((disabled,)),
        target_army.player_id: AbilityCatalogIndex.from_records(()),
    }
    armies = (source_army, target_army)
    once_runtime = CatalogOncePerBattleRuntime(indexes, armies)
    assert once_runtime.fight_phase_start_bindings() == ()
    state = _state_with_battlefield(
        armies=armies,
        battlefield=_battlefield_for_units(
            source_army=source_army,
            source_unit=source_unit,
            source_x=10.0,
            target_army=target_army,
            target_unit=target_unit,
            target_x=20.0,
        ),
        active_player_id=source_army.player_id,
        phase=BattlePhase.FIGHT,
    )
    assert (
        once_runtime.fight_phase_start_request(
            FightPhaseStartRequestContext(state=state, decisions=DecisionController())
        )
        is None
    )
    any_phase_runtime = CatalogAnyPhaseOncePerBattleRuntime(indexes, armies)
    assert any_phase_runtime.event_handler_bindings() == ()
    assert any_phase_runtime.event_subscriptions() == ()


def test_catalog_once_per_battle_runtime_declines_then_activates_once_with_replay() -> None:
    source_army, target_army = _mustered_once_per_battle_armies()
    source_unit = source_army.units[0]
    target_unit = target_army.units[0]
    state = _state_with_battlefield(
        armies=(source_army, target_army),
        battlefield=_battlefield_for_units(
            source_army=source_army,
            source_unit=source_unit,
            source_x=10.0,
            target_army=target_army,
            target_unit=target_unit,
            target_x=20.0,
        ),
        active_player_id=source_army.player_id,
        phase=BattlePhase.FIGHT,
    )
    record = _once_per_battle_record(source_unit=source_unit)
    runtime = CatalogOncePerBattleRuntime(
        ability_indexes_by_player_id={
            source_army.player_id: AbilityCatalogIndex.from_records((record,)),
            target_army.player_id: AbilityCatalogIndex.from_records(()),
        },
        armies=(source_army, target_army),
    )
    decisions = DecisionController()

    request = runtime.fight_phase_start_request(
        FightPhaseStartRequestContext(state=state, decisions=decisions)
    )
    assert request is not None
    assert DecisionRequest.from_payload(request.to_payload()) == request
    assert request.decision_type == SELECT_FACTION_RULE_FIGHT_PHASE_START_OPTION_DECISION_TYPE
    activation_choices = [
        cast(dict[str, JsonValue], option.payload)["activate"] for option in request.options
    ]
    assert activation_choices == [False, True]

    queued = decisions.request_decision(request)
    declined = DecisionResult.for_request(
        result_id="result:once-per-battle:declined",
        request=queued,
        selected_option_id=queued.options[0].option_id,
    )
    decisions.submit_result(declined)
    assert (
        runtime.apply_fight_phase_start_result(
            FightPhaseStartResultContext(
                state=state,
                decisions=decisions,
                request=queued,
                result=declined,
            )
        )
        is True
    )
    assert not state.persisting_effects
    assert decisions.event_log.records[-1].event_type == (
        CATALOG_ONCE_PER_BATTLE_ABILITY_DECLINED_EVENT
    )
    assert (
        runtime.fight_phase_start_request(
            FightPhaseStartRequestContext(state=state, decisions=decisions)
        )
        is None
    )

    state.battle_round = 2
    activation_request = runtime.fight_phase_start_request(
        FightPhaseStartRequestContext(state=state, decisions=decisions)
    )
    assert activation_request is not None
    queued_activation = decisions.request_decision(activation_request)
    activated = DecisionResult.for_request(
        result_id="result:once-per-battle:activated",
        request=queued_activation,
        selected_option_id=queued_activation.options[1].option_id,
    )
    decisions.submit_result(activated)
    assert (
        runtime.apply_fight_phase_start_result(
            FightPhaseStartResultContext(
                state=state,
                decisions=decisions,
                request=queued_activation,
                result=activated,
            )
        )
        is True
    )

    assert len(state.persisting_effects) == 2
    assert any(
        event.event_type == RULE_FREQUENCY_LIMIT_CONSUMED_EVENT
        for event in decisions.event_log.records
    )
    assert decisions.event_log.records[-1].event_type == (
        CATALOG_ONCE_PER_BATTLE_ABILITY_ACTIVATED_EVENT
    )
    assert (
        runtime.fight_phase_start_request(
            FightPhaseStartRequestContext(state=state, decisions=decisions)
        )
        is None
    )
    assert DecisionController.from_payload(decisions.to_payload()).to_payload() == (
        decisions.to_payload()
    )
    restored_state = GameState.from_payload(state.to_payload())
    assert [effect.to_payload() for effect in restored_state.persisting_effects] == [
        effect.to_payload() for effect in state.persisting_effects
    ]


def test_catalog_once_per_battle_runtime_rejects_source_model_drift_without_mutation() -> None:
    source_army, target_army = _mustered_once_per_battle_armies()
    source_unit = source_army.units[0]
    source_model = source_unit.own_models[0]
    state = _state_with_battlefield(
        armies=(source_army, target_army),
        battlefield=_battlefield_for_units(
            source_army=source_army,
            source_unit=source_unit,
            source_x=10.0,
            target_army=target_army,
            target_unit=target_army.units[0],
            target_x=20.0,
        ),
        active_player_id=source_army.player_id,
        phase=BattlePhase.FIGHT,
    )
    runtime = CatalogOncePerBattleRuntime(
        ability_indexes_by_player_id={
            source_army.player_id: AbilityCatalogIndex.from_records(
                (_once_per_battle_record(source_unit=source_unit),)
            ),
            target_army.player_id: AbilityCatalogIndex.from_records(()),
        },
        armies=(source_army, target_army),
    )
    decisions = DecisionController()
    request = runtime.fight_phase_start_request(
        FightPhaseStartRequestContext(state=state, decisions=decisions)
    )
    assert request is not None
    queued = decisions.request_decision(request)
    result = DecisionResult.for_request(
        result_id="result:once-per-battle:drift",
        request=queued,
        selected_option_id=queued.options[1].option_id,
    )
    decisions.submit_result(result)
    assert state.battlefield_state is not None
    state.battlefield_state = state.battlefield_state.with_removed_models(
        (source_model.model_instance_id,)
    )

    status = runtime.apply_fight_phase_start_result(
        FightPhaseStartResultContext(
            state=state,
            decisions=decisions,
            request=queued,
            result=result,
        )
    )

    assert type(status) is LifecycleStatus
    assert status.status_kind is LifecycleStatusKind.INVALID
    assert cast(dict[str, JsonValue], status.payload)["invalid_reason"] == (
        "once_per_battle_activation_drift"
    )
    assert not state.persisting_effects
    assert all(
        event.event_type != RULE_FREQUENCY_LIMIT_CONSUMED_EVENT
        for event in decisions.event_log.records
    )


def test_catalog_once_per_battle_runtime_rejects_actor_drift_without_mutation() -> None:
    source_army, target_army = _mustered_once_per_battle_armies()
    source_unit = source_army.units[0]
    state = _state_with_battlefield(
        armies=(source_army, target_army),
        battlefield=_battlefield_for_units(
            source_army=source_army,
            source_unit=source_unit,
            source_x=10.0,
            target_army=target_army,
            target_unit=target_army.units[0],
            target_x=20.0,
        ),
        active_player_id=source_army.player_id,
        phase=BattlePhase.FIGHT,
    )
    runtime = CatalogOncePerBattleRuntime(
        ability_indexes_by_player_id={
            source_army.player_id: AbilityCatalogIndex.from_records(
                (_once_per_battle_record(source_unit=source_unit),)
            ),
            target_army.player_id: AbilityCatalogIndex.from_records(()),
        },
        armies=(source_army, target_army),
    )
    decisions = DecisionController()
    request = runtime.fight_phase_start_request(
        FightPhaseStartRequestContext(state=state, decisions=decisions)
    )
    assert request is not None
    result = replace(
        DecisionResult.for_request(
            result_id="result:once-per-battle:actor-drift",
            request=request,
            selected_option_id=request.options[1].option_id,
        ),
        actor_id=target_army.player_id,
    )

    status = runtime.apply_fight_phase_start_result(
        FightPhaseStartResultContext(
            state=state,
            decisions=decisions,
            request=request,
            result=result,
        )
    )

    assert type(status) is LifecycleStatus
    assert status.status_kind is LifecycleStatusKind.INVALID
    assert cast(dict[str, JsonValue], status.payload)["invalid_reason"] == (
        "once_per_battle_actor_drift"
    )
    assert not state.persisting_effects
    assert all(
        event.event_type != RULE_FREQUENCY_LIMIT_CONSUMED_EVENT
        for event in decisions.event_log.records
    )


def test_catalog_once_per_battle_runtime_targets_attached_rules_unit_for_leader_model() -> None:
    source_army, target_army = _mustered_attached_once_per_battle_armies()
    source_unit = next(
        unit for unit in source_army.units if unit.datasheet_id == "core-character-leader"
    )
    source_rules_unit_id = source_army.attached_units[0].attached_unit_instance_id
    scenario = create_deterministic_battlefield_scenario(
        battlefield_id="catalog-once-per-battle-attached",
        armies=(source_army, target_army),
    )
    state = _state_without_battlefield(
        active_player_id=source_army.player_id,
        phase=BattlePhase.FIGHT,
    )
    for army in (source_army, target_army):
        state.record_army_definition(army)
    state.battlefield_state = scenario.battlefield_state
    runtime = CatalogOncePerBattleRuntime(
        ability_indexes_by_player_id={
            source_army.player_id: AbilityCatalogIndex.from_records(
                (_once_per_battle_record(source_unit=source_unit),)
            ),
            target_army.player_id: AbilityCatalogIndex.from_records(()),
        },
        armies=(source_army, target_army),
    )
    decisions = DecisionController()

    request = runtime.fight_phase_start_request(
        FightPhaseStartRequestContext(state=state, decisions=decisions)
    )
    assert request is not None
    payload = cast(dict[str, JsonValue], request.payload)
    assert payload["source_unit_instance_id"] == source_unit.unit_instance_id
    assert payload["source_rules_unit_instance_id"] == source_rules_unit_id
    queued = decisions.request_decision(request)
    result = DecisionResult.for_request(
        result_id="result:once-per-battle:attached-leader",
        request=queued,
        selected_option_id=queued.options[1].option_id,
    )
    decisions.submit_result(result)

    assert (
        runtime.apply_fight_phase_start_result(
            FightPhaseStartResultContext(
                state=state,
                decisions=decisions,
                request=queued,
                result=result,
            )
        )
        is True
    )
    assert len(state.persisting_effects) == 2
    assert all(
        effect.target_unit_instance_ids == (source_rules_unit_id,)
        for effect in state.persisting_effects
    )


def test_catalog_datasheet_runtime_applies_leading_unit_wound_roll_modifier() -> None:
    source_army, target_army = _mustered_attached_once_per_battle_armies()
    leader_unit = next(
        unit for unit in source_army.units if unit.datasheet_id == "core-character-leader"
    )
    bodyguard_unit = next(
        unit for unit in source_army.units if unit.datasheet_id == "core-intercessor-like-infantry"
    )
    target_unit = target_army.units[0]
    rules_unit_id = source_army.attached_units[0].attached_unit_instance_id
    scenario = create_deterministic_battlefield_scenario(
        battlefield_id="catalog-leading-wound-attached",
        armies=(source_army, target_army),
    )
    state = _state_without_battlefield(
        active_player_id=source_army.player_id,
        phase=BattlePhase.SHOOTING,
    )
    for army in (source_army, target_army):
        state.record_army_definition(army)
    state.battlefield_state = scenario.battlefield_state
    record = _compiled_record(
        record_id="record:catalog-datasheet:leading-wound",
        raw_text=(
            "While this model is leading a unit, each time a model in that unit makes an "
            "attack, add 1 to the Wound roll."
        ),
        source_unit=leader_unit,
        trigger_kind=TimingTriggerKind.AFTER_DICE_ROLL,
    )
    runtime = CatalogDatasheetRuleRuntime(
        ability_indexes_by_player_id={
            source_army.player_id: AbilityCatalogIndex.from_records((record,)),
            target_army.player_id: AbilityCatalogIndex.from_records(()),
        },
        armies=(source_army, target_army),
    )
    context = WoundRollModifierContext(
        state=state,
        source_phase=BattlePhase.SHOOTING,
        attacking_unit_instance_id=rules_unit_id,
        attacker_model_instance_id=bodyguard_unit.own_models[0].model_instance_id,
        target_unit_instance_id=target_unit.unit_instance_id,
        weapon_profile=_first_catalog_weapon_profile(),
        strength=4,
        toughness=4,
    )

    bindings = runtime.wound_roll_modifier_bindings()

    assert len(bindings) == 1
    assert bindings[0].handler(context) == 1


def test_catalog_datasheet_runtime_ignores_wound_modifier_when_source_not_leading() -> None:
    source_army, target_army = _mustered_once_per_battle_armies()
    leader_unit = source_army.units[0]
    target_unit = target_army.units[0]
    scenario = create_deterministic_battlefield_scenario(
        battlefield_id="catalog-leading-wound-unattached",
        armies=(source_army, target_army),
    )
    state = _state_without_battlefield(
        active_player_id=source_army.player_id,
        phase=BattlePhase.SHOOTING,
    )
    for army in (source_army, target_army):
        state.record_army_definition(army)
    state.battlefield_state = scenario.battlefield_state
    record = _compiled_record(
        record_id="record:catalog-datasheet:leading-wound-unattached",
        raw_text=(
            "While this model is leading a unit, each time a model in that unit makes an "
            "attack, add 1 to the Wound roll."
        ),
        source_unit=leader_unit,
        trigger_kind=TimingTriggerKind.AFTER_DICE_ROLL,
    )
    runtime = CatalogDatasheetRuleRuntime(
        ability_indexes_by_player_id={
            source_army.player_id: AbilityCatalogIndex.from_records((record,)),
            target_army.player_id: AbilityCatalogIndex.from_records(()),
        },
        armies=(source_army, target_army),
    )
    context = WoundRollModifierContext(
        state=state,
        source_phase=BattlePhase.SHOOTING,
        attacking_unit_instance_id=leader_unit.unit_instance_id,
        attacker_model_instance_id=leader_unit.own_models[0].model_instance_id,
        target_unit_instance_id=target_unit.unit_instance_id,
        weapon_profile=_first_catalog_weapon_profile(),
        strength=4,
        toughness=4,
    )

    bindings = runtime.wound_roll_modifier_bindings()

    assert len(bindings) == 1
    assert bindings[0].handler(context) == 0


def test_catalog_datasheet_runtime_executes_scoped_shield_wargear_rule_ir() -> None:
    shield_army, attacking_army = _mustered_core_armies()
    shield_unit = shield_army.units[0]
    attacking_unit = attacking_army.units[0]
    wargear_id = "test:aeldari:shield-wargear"
    bearer = replace(
        shield_unit.own_models[0],
        wargear_ids=(*shield_unit.own_models[0].wargear_ids, wargear_id),
    )
    shield_unit = replace(
        shield_unit,
        own_models=(bearer, *shield_unit.own_models[1:]),
    )
    shield_army = _army_with_unit(shield_army, shield_unit)
    state = _state_with_battlefield(
        armies=(shield_army, attacking_army),
        battlefield=_battlefield_for_units(
            source_army=shield_army,
            source_unit=shield_unit,
            source_x=10.0,
            target_army=attacking_army,
            target_unit=attacking_unit,
            target_x=20.0,
        ),
        active_player_id=attacking_army.player_id,
        phase=BattlePhase.SHOOTING,
    )

    def runtime_for(*, source_id: str, raw_text: str) -> CatalogDatasheetRuleRuntime:
        rule_ir = compile_rule_source_text(
            RuleSourceText.from_raw(source_id=source_id, raw_text=raw_text),
            source_keyword_sequence_parts=SOURCE_KEYWORD_SEQUENCE_PARTS,
        ).rule_ir
        record = _ability_record(
            record_id=f"record:{source_id}",
            rule_ir=rule_ir,
            trigger_kind=TimingTriggerKind.DURING_PHASE,
            datasheet_id=shield_unit.datasheet_id,
            source_kind=AbilitySourceKind.WARGEAR,
            wargear_id=wargear_id,
        )
        return CatalogDatasheetRuleRuntime(
            ability_indexes_by_player_id={
                shield_army.player_id: AbilityCatalogIndex.from_records((record,)),
                attacking_army.player_id: AbilityCatalogIndex.from_records(()),
            },
            armies=(shield_army, attacking_army),
        )

    base_save = SaveOption(
        save_kind=SaveKind.ARMOUR,
        target_number=3,
        characteristic_target_number=3,
        armor_penetration=0,
    )
    save_context = SaveOptionModifierContext(
        state=state,
        source_phase=BattlePhase.SHOOTING,
        attacking_unit_instance_id=attacking_unit.unit_instance_id,
        attacker_model_instance_id=attacking_unit.own_models[0].model_instance_id,
        target_unit_instance_id=shield_unit.unit_instance_id,
        allocated_model_instance_id=bearer.model_instance_id,
        weapon_profile=_first_catalog_weapon_profile(),
        save_options=(base_save,),
    )
    shimmershield = runtime_for(
        source_id="000000593:shimmershield",
        raw_text="The bearer has a 4+ invulnerable save.",
    )
    shimmer_binding = shimmershield.save_option_modifier_bindings()[0]
    shimmer_bearer_options = shimmer_binding.handler(save_context)
    shimmer_other_options = shimmer_binding.handler(
        replace(
            save_context,
            allocated_model_instance_id=shield_unit.own_models[1].model_instance_id,
        )
    )

    assert tuple(
        option.target_number
        for option in shimmer_bearer_options
        if option.save_kind is SaveKind.INVULNERABLE
    ) == (4,)
    assert all(option.save_kind is not SaveKind.INVULNERABLE for option in shimmer_other_options)
    better_invulnerable_save = SaveOption(
        save_kind=SaveKind.INVULNERABLE,
        target_number=3,
        characteristic_target_number=3,
        armor_penetration=0,
        source_rule_ids=("test:better-invulnerable-save",),
    )
    existing_better_options = (base_save, better_invulnerable_save)
    assert (
        shimmer_binding.handler(replace(save_context, save_options=existing_better_options))
        == existing_better_options
    )

    serpent_shield = runtime_for(
        source_id="000000590:serpent-shield",
        raw_text="Models in the bearer's unit have a 5+ invulnerable save.",
    )
    serpent_options = serpent_shield.save_option_modifier_bindings()[0].handler(
        replace(
            save_context,
            allocated_model_instance_id=shield_unit.own_models[1].model_instance_id,
        )
    )
    assert tuple(
        option.target_number
        for option in serpent_options
        if option.save_kind is SaveKind.INVULNERABLE
    ) == (5,)

    scattershield = runtime_for(
        source_id="000003913:scattershield",
        raw_text=(
            "The bearer has a 4+ invulnerable save and each time an attack is allocated "
            "to the bearer, subtract 1 from the Damage characteristic of that attack."
        ),
    )
    scatter_save_bindings = scattershield.save_option_modifier_bindings()
    scatter_damage_bindings = scattershield.allocated_attack_damage_modifier_bindings()
    damage_context = AllocatedAttackDamageModifierContext(
        state=state,
        source_phase=BattlePhase.SHOOTING,
        attacking_unit_instance_id=attacking_unit.unit_instance_id,
        attacker_model_instance_id=attacking_unit.own_models[0].model_instance_id,
        target_unit_instance_id=shield_unit.unit_instance_id,
        allocated_model_instance_id=bearer.model_instance_id,
        weapon_profile=_first_catalog_weapon_profile(),
        current_value=2,
    )

    assert len(scatter_save_bindings) == 1
    assert len(scatter_damage_bindings) == 1
    assert scatter_damage_bindings[0].handler(damage_context) == -1
    assert (
        scatter_damage_bindings[0].handler(
            replace(
                damage_context,
                allocated_model_instance_id=shield_unit.own_models[1].model_instance_id,
            )
        )
        == 0
    )


def test_catalog_bearer_unit_invulnerable_save_includes_attached_leader() -> None:
    shield_army, attacking_army = _mustered_attached_once_per_battle_armies()
    bodyguard = next(
        unit for unit in shield_army.units if unit.datasheet_id == "core-intercessor-like-infantry"
    )
    leader = next(
        unit for unit in shield_army.units if unit.datasheet_id == "core-character-leader"
    )
    attacking_unit = attacking_army.units[0]
    wargear_id = "test:aeldari:attached-serpent-shield"
    bearer = replace(
        bodyguard.own_models[0],
        wargear_ids=(*bodyguard.own_models[0].wargear_ids, wargear_id),
    )
    bodyguard = replace(
        bodyguard,
        own_models=(bearer, *bodyguard.own_models[1:]),
    )
    shield_army = replace(
        shield_army,
        units=tuple(
            bodyguard if unit.unit_instance_id == bodyguard.unit_instance_id else unit
            for unit in shield_army.units
        ),
    )
    scenario = create_deterministic_battlefield_scenario(
        battlefield_id="catalog-attached-serpent-shield",
        armies=(shield_army, attacking_army),
    )
    state = _state_without_battlefield(
        active_player_id=attacking_army.player_id,
        phase=BattlePhase.SHOOTING,
    )
    for army in (shield_army, attacking_army):
        state.record_army_definition(army)
    state.battlefield_state = scenario.battlefield_state
    rule_ir = compile_rule_source_text(
        RuleSourceText.from_raw(
            source_id="000000590:serpent-shield:attached-test",
            raw_text="Models in the bearer's unit have a 5+ invulnerable save.",
        ),
        source_keyword_sequence_parts=SOURCE_KEYWORD_SEQUENCE_PARTS,
    ).rule_ir
    record = _ability_record(
        record_id="record:000000590:serpent-shield:attached-test",
        rule_ir=rule_ir,
        trigger_kind=TimingTriggerKind.DURING_PHASE,
        datasheet_id=bodyguard.datasheet_id,
        source_kind=AbilitySourceKind.WARGEAR,
        wargear_id=wargear_id,
    )
    runtime = CatalogDatasheetRuleRuntime(
        ability_indexes_by_player_id={
            shield_army.player_id: AbilityCatalogIndex.from_records((record,)),
            attacking_army.player_id: AbilityCatalogIndex.from_records(()),
        },
        armies=(shield_army, attacking_army),
    )
    attached_unit_id = shield_army.attached_units[0].attached_unit_instance_id
    options = runtime.save_option_modifier_bindings()[0].handler(
        SaveOptionModifierContext(
            state=state,
            source_phase=BattlePhase.SHOOTING,
            attacking_unit_instance_id=attacking_unit.unit_instance_id,
            attacker_model_instance_id=attacking_unit.own_models[0].model_instance_id,
            target_unit_instance_id=attached_unit_id,
            allocated_model_instance_id=leader.own_models[0].model_instance_id,
            weapon_profile=_first_catalog_weapon_profile(),
            save_options=(),
        )
    )

    assert len(options) == 1
    assert options[0].save_kind is SaveKind.INVULNERABLE
    assert options[0].target_number == 5


def test_catalog_datasheet_runtime_applies_charge_end_leading_weapon_ability_grant() -> None:
    source_army, target_army = _mustered_attached_once_per_battle_armies()
    leader_unit = next(
        unit for unit in source_army.units if unit.datasheet_id == "core-character-leader"
    )
    bodyguard_unit = next(
        unit for unit in source_army.units if unit.datasheet_id == "core-intercessor-like-infantry"
    )
    target_unit = target_army.units[0]
    rules_unit_id = source_army.attached_units[0].attached_unit_instance_id
    scenario = create_deterministic_battlefield_scenario(
        battlefield_id="catalog-charge-end-weapon-grant-attached",
        armies=(source_army, target_army),
    )
    state = _state_without_battlefield(
        active_player_id=source_army.player_id,
        phase=BattlePhase.FIGHT,
    )
    for army in (source_army, target_army):
        state.record_army_definition(army)
    state.battlefield_state = scenario.battlefield_state
    state.record_persisting_effect(
        PersistingEffect(
            effect_id="effect:catalog-charge-end-weapon-grant:charged",
            source_rule_id="core-rules:charge-fights-first",
            owner_player_id=source_army.player_id,
            target_unit_instance_ids=(rules_unit_id,),
            started_battle_round=state.battle_round,
            expiration=EffectExpiration.end_turn(
                battle_round=state.battle_round,
                player_id=source_army.player_id,
            ),
            effect_payload={"effect_kind": CHARGE_FIGHTS_FIRST_EFFECT_KIND},
            started_phase=BattlePhaseKind.CHARGE,
        )
    )
    record = _compiled_record(
        record_id="record:catalog-datasheet:charge-end-weapon-grant",
        raw_text=(
            "While this model is leading a unit, each time that unit ends a Charge move, "
            "until the end of the turn, Juggernaut's bladed horns equipped by models in "
            "that unit have the [DEVASTATING WOUNDS] ability."
        ),
        source_unit=leader_unit,
        trigger_kind=TimingTriggerKind.AFTER_UNIT_ENDS_CHARGE_MOVE,
    )
    runtime = CatalogDatasheetRuleRuntime(
        ability_indexes_by_player_id={
            source_army.player_id: AbilityCatalogIndex.from_records((record,)),
            target_army.player_id: AbilityCatalogIndex.from_records(()),
        },
        armies=(source_army, target_army),
    )
    base_profile = replace(
        _first_catalog_weapon_profile(),
        profile_id="juggernauts-bladed-horns",
        name="Juggernaut's bladed horns",
        keywords=(),
        abilities=(),
        source_ids=(),
    )
    other_profile = replace(
        base_profile,
        profile_id="not-bladed-horns",
        name="Bloodcrusher blade",
    )
    context = WeaponProfileModifierContext(
        state=state,
        source_phase=BattlePhase.FIGHT,
        attacking_unit_instance_id=rules_unit_id,
        attacker_model_instance_id=bodyguard_unit.own_models[0].model_instance_id,
        target_unit_instance_id=target_unit.unit_instance_id,
        weapon_profile=base_profile,
    )

    bindings = runtime.weapon_profile_modifier_bindings()
    modified = bindings[0].handler(context)
    unchanged = bindings[0].handler(replace(context, weapon_profile=other_profile))

    assert len(bindings) == 1
    assert WeaponKeyword.DEVASTATING_WOUNDS in modified.keywords
    assert record.definition.source_id in modified.source_ids
    assert unchanged == other_profile


def test_catalog_datasheet_runtime_exposes_consolidation_distance_fight_activation() -> None:
    source_army, target_army = _mustered_core_armies()
    source_unit = source_army.units[0]
    target_unit = target_army.units[0]
    state = _state_with_battlefield(
        armies=(source_army, target_army),
        battlefield=_battlefield_for_units(
            source_army=source_army,
            source_unit=source_unit,
            source_x=10.0,
            target_army=target_army,
            target_unit=target_unit,
            target_x=10.4,
        ),
        active_player_id=source_army.player_id,
        phase=BattlePhase.FIGHT,
    )
    record = _compiled_record(
        record_id="record:catalog-datasheet:consolidation-distance",
        raw_text=(
            'Each time this model\'s unit Consolidates, it can move up to 6" instead of up to 3".'
        ),
        source_unit=source_unit,
        trigger_kind=TimingTriggerKind.DURING_PHASE,
    )
    runtime = CatalogDatasheetRuleRuntime(
        ability_indexes_by_player_id={
            source_army.player_id: AbilityCatalogIndex.from_records((record,)),
            target_army.player_id: AbilityCatalogIndex.from_records(()),
        },
        armies=(source_army, target_army),
    )
    activation = FightActivationSelection(
        player_id=source_army.player_id,
        battle_round=state.battle_round,
        unit_instance_id=source_unit.unit_instance_id,
        ordering_band=FightOrderingBandKind.REMAINING_COMBATS,
        fight_type=FightTypeKind.NORMAL,
        eligibility_reasons=(FightEligibilityKind.CURRENTLY_ENGAGED,),
        request_id="request:catalog-datasheet:consolidation-distance",
        result_id="result:catalog-datasheet:consolidation-distance",
    )
    context = FightActivationAbilityContext(
        state=state,
        game_id=state.game_id,
        battle_round=state.battle_round,
        active_player_id=source_army.player_id,
        player_id=source_army.player_id,
        unit_instance_id=source_unit.unit_instance_id,
        activation=activation,
        target_unit_instance_ids=(target_unit.unit_instance_id,),
    )

    bindings = runtime.fight_activation_ability_hook_bindings()
    option = bindings[0].handler(context)

    assert len(bindings) == 1
    assert option is not None
    assert option.effect_kind == FIGHT_ACTIVATION_MOVEMENT_DISTANCE_EFFECT_KIND
    assert option.pile_in_distance_inches == 3.0
    assert option.consolidate_distance_inches == 6.0
    replay_payload = cast(dict[str, JsonValue], option.replay_payload)
    assert replay_payload["source_unit_instance_id"] == source_unit.unit_instance_id
    assert replay_payload["rules_unit_instance_id"] == source_unit.unit_instance_id
    assert replay_payload["movement_mode"] == "consolidate"


def test_catalog_unit_move_completed_battle_shock_binding_targets_engaged_enemies() -> None:
    source_army, target_army = _mustered_core_armies()
    source_unit = source_army.units[0]
    target_unit = target_army.units[0]
    state = _state_with_battlefield(
        armies=(source_army, target_army),
        battlefield=_battlefield_for_units(
            source_army=source_army,
            source_unit=source_unit,
            source_x=10.0,
            target_army=target_army,
            target_unit=target_unit,
            target_x=10.4,
        ),
        active_player_id=source_army.player_id,
        phase=BattlePhase.CHARGE,
    )
    record = _compiled_record(
        record_id="record:catalog:charge-end-battle-shock",
        raw_text=(
            "Each time this model's unit ends a Charge move, each enemy unit within "
            "Engagement Range of that unit must take a Battle-shock test."
        ),
        source_unit=source_unit,
        trigger_kind=TimingTriggerKind.AFTER_UNIT_ENDS_CHARGE_MOVE,
    )
    ability_indexes_by_player_id = {
        source_army.player_id: AbilityCatalogIndex.from_records((record,)),
        target_army.player_id: AbilityCatalogIndex.from_records(()),
    }
    bindings = catalog_unit_move_completed_battle_shock_hook_bindings(
        ability_indexes_by_player_id=ability_indexes_by_player_id,
        armies=(source_army, target_army),
    )
    context = UnitMoveCompletedContext(
        state=state,
        ruleset_descriptor=RulesetDescriptor.warhammer_40000_eleventh(),
        runtime_modifier_registry=RuntimeModifierRegistry.empty(),
        completed_phase=BattlePhase.CHARGE,
        trigger_event_id="event:catalog:charge-end-battle-shock",
        trigger_event_payload={
            "game_id": state.game_id,
            "battle_round": state.battle_round,
            "phase": BattlePhase.CHARGE.value,
            "unit_instance_id": source_unit.unit_instance_id,
            "active_player_id": source_army.player_id,
            "movement_phase_action": "charge_move",
        },
        triggering_unit_instance_id=source_unit.unit_instance_id,
        triggering_player_id=source_army.player_id,
        movement_action="charge_move",
        ability_indexes_by_player_id=ability_indexes_by_player_id,
        decisions=DecisionController(),
    )

    assert len(bindings) == 1
    assert bindings[0].hook_id == CATALOG_IR_UNIT_MOVE_COMPLETED_BATTLE_SHOCK_CONSUMER_ID
    effects = bindings[0].handler(context)
    assert len(effects) == 1
    effect = effects[0]
    assert effect.hook_id == CATALOG_IR_UNIT_MOVE_COMPLETED_BATTLE_SHOCK_CONSUMER_ID
    assert effect.source_rule_id == record.definition.source_id
    assert effect.target_unit_instance_id == target_unit.unit_instance_id
    assert effect.target_player_id == target_army.player_id
    assert effect.trigger_event_id == "event:catalog:charge-end-battle-shock"
    replay_payload = cast(dict[str, JsonValue], effect.replay_payload)
    assert replay_payload["source_unit_instance_id"] == source_unit.unit_instance_id
    assert replay_payload["target_unit_instance_id"] == target_unit.unit_instance_id
    assert replay_payload["movement_action"] == "charge_move"


def test_catalog_selected_target_runtime_fail_fast_and_empty_paths() -> None:
    source_army, target_army = _mustered_core_armies()
    source_unit = source_army.units[0]
    selection_clause = _fight_start_selection_clause()
    rule_ir = _rule_ir(
        source_id="test:selected-target:fight-runtime-empty-paths",
        clauses=(
            selection_clause,
            _effect_clause(
                clause_id="test:selected-target:selection:fight:empty-paths-effect",
                duration=_duration("phase"),
                effect_kind=RuleEffectKind.REROLL_PERMISSION,
                roll_type="attack_sequence.hit",
            ),
        ),
    )
    record = _ability_record(
        record_id="record:selected-target:fight-runtime-empty-paths",
        rule_ir=rule_ir,
        trigger_kind=TimingTriggerKind.START_PHASE,
        runtime_clause_id=selection_clause.clause_id,
    )
    empty_index = AbilityCatalogIndex.from_records(())

    with pytest.raises(GameLifecycleError, match="missing ability index"):
        CatalogSelectedTargetEffectRuntime(
            ability_indexes_by_player_id={source_army.player_id: empty_index},
            armies=(source_army, target_army),
        )

    empty_runtime = CatalogSelectedTargetEffectRuntime(
        ability_indexes_by_player_id={
            source_army.player_id: empty_index,
            target_army.player_id: empty_index,
        },
        armies=(source_army, target_army),
    )
    assert empty_runtime.fight_phase_start_bindings() == ()
    assert empty_runtime.attack_sequence_completed_bindings() == ()

    runtime = CatalogSelectedTargetEffectRuntime(
        ability_indexes_by_player_id={
            source_army.player_id: AbilityCatalogIndex.from_records((record,)),
            target_army.player_id: empty_index,
        },
        armies=(source_army, target_army),
    )
    no_battlefield_state = _state_without_battlefield(
        active_player_id=source_army.player_id,
        phase=BattlePhase.FIGHT,
    )
    no_battlefield_state.army_definitions = [source_army, target_army]
    assert (
        runtime.fight_phase_start_request(
            FightPhaseStartRequestContext(
                state=no_battlefield_state,
                decisions=DecisionController(),
            )
        )
        is None
    )
    with pytest.raises(GameLifecycleError, match="Fight-start requires context"):
        runtime.apply_fight_phase_start_result(cast(FightPhaseStartResultContext, object()))

    battlefield = _battlefield_for_units(
        source_army=source_army,
        source_unit=source_unit,
        source_x=10.0,
        target_army=target_army,
        target_unit=target_army.units[0],
        target_x=10.4,
    )
    state = _state_with_battlefield(
        armies=(source_army, target_army),
        battlefield=battlefield,
        active_player_id=source_army.player_id,
        phase=BattlePhase.FIGHT,
    )
    wrong_hook_request = DecisionRequest(
        request_id=state.next_decision_request_id(),
        decision_type=SELECT_FACTION_RULE_FIGHT_PHASE_START_OPTION_DECISION_TYPE,
        actor_id=source_army.player_id,
        payload={"hook_id": "other-hook"},
        options=(
            DecisionOption(
                option_id="wrong-hook-option",
                label="Wrong Hook Option",
                payload={"hook_id": "other-hook"},
            ),
        ),
    )
    wrong_hook_result = DecisionResult.for_request(
        result_id="result:selected-target:wrong-hook",
        request=wrong_hook_request,
        selected_option_id="wrong-hook-option",
    )

    assert (
        runtime.apply_fight_phase_start_result(
            FightPhaseStartResultContext(
                state=state,
                decisions=DecisionController(),
                request=wrong_hook_request,
                result=wrong_hook_result,
            )
        )
        is False
    )
    with pytest.raises(GameLifecycleError, match="apply requires decisions"):
        apply_catalog_post_shoot_hit_target_effect_result(
            state=state,
            decisions=cast(DecisionController, object()),
            result=wrong_hook_result,
            battle_shock_hooks=BattleShockHookRegistry.empty(),
            runtime_modifier_registry=RuntimeModifierRegistry.empty(),
            ability_indexes_by_player_id={
                source_army.player_id: AbilityCatalogIndex.from_records((record,)),
                target_army.player_id: empty_index,
            },
        )
    with pytest.raises(GameLifecycleError, match="apply requires result"):
        apply_catalog_post_shoot_hit_target_effect_result(
            state=state,
            decisions=DecisionController(),
            result=cast(DecisionResult, object()),
            battle_shock_hooks=BattleShockHookRegistry.empty(),
            runtime_modifier_registry=RuntimeModifierRegistry.empty(),
            ability_indexes_by_player_id={
                source_army.player_id: AbilityCatalogIndex.from_records((record,)),
                target_army.player_id: empty_index,
            },
        )


def test_catalog_selected_target_support_validates_payloads_and_status_gates() -> None:
    payload = {
        "id": "payload-id",
        "count": 2,
        "ids": ["target-b", "target-a"],
        "generic_rule_effect_records": [{"source_rule_id": "source-a"}],
        "selected_catalog_target_effect": {
            "option_id": "option-a",
            "target_unit_instance_id": "target-a",
        },
    }
    state = _state_without_battlefield(active_player_id="player-a", phase=BattlePhase.FIGHT)
    status_clause = _effect_clause(
        clause_id="test:selected-target:status-gated",
        duration=_duration("phase"),
        effect_kind=RuleEffectKind.REROLL_PERMISSION,
        roll_type="attack_sequence.hit",
        conditions=(
            _condition(
                RuleConditionKind.TARGET_CONSTRAINT,
                ("relationship", "target_unit_has_status"),
                ("status", "battle_shocked"),
            ),
        ),
    )

    assert payload_object(payload) == payload
    assert payload_string(payload, key="id") == "payload-id"
    assert payload_int(payload, key="count") == 2
    assert payload_string_tuple(payload, key="ids") == ("target-a", "target-b")
    assert payload_effect_records(payload) == ({"source_rule_id": "source-a"},)
    assert selected_payload(payload)["option_id"] == "option-a"
    assert validate_identifier_tuple("ids", ("b", "a")) == ("a", "b")
    assert validate_effect_record_tuple(({"nested": ["value"]},)) == ({"nested": ["value"]},)
    assert active_player_id(state) == "player-a"
    assert battle_phase_kind(BattlePhase.FIGHT) is BattlePhaseKind.FIGHT
    assert battle_phase_kind(BattlePhase.SHOOTING) is BattlePhaseKind.SHOOTING
    assert timing_window_id(BattlePhase.FIGHT) == "fight_phase_start"
    assert timing_window_id(BattlePhase.SHOOTING) == "attack_sequence_completed"
    state.battle_shocked_unit_ids = ["target-a"]
    assert selected_target_status_gate_allows(
        state=state,
        clause=status_clause,
        selected_target_unit_instance_id="target-a",
    )
    state.battle_shocked_unit_ids = []
    assert not selected_target_status_gate_allows(
        state=state,
        clause=status_clause,
        selected_target_unit_instance_id="target-a",
    )

    bad_status_clause = replace(
        status_clause,
        conditions=(
            _condition(
                RuleConditionKind.TARGET_CONSTRAINT,
                ("relationship", "target_unit_has_status"),
                ("status", "poisoned"),
            ),
        ),
    )
    with pytest.raises(GameLifecycleError, match="status is unsupported"):
        selected_target_status_gate_allows(
            state=state,
            clause=bad_status_clause,
            selected_target_unit_instance_id="target-a",
        )
    inactive_state = _state_without_battlefield(
        active_player_id="player-a",
        phase=BattlePhase.FIGHT,
    )
    inactive_state.active_player_id = None
    with pytest.raises(GameLifecycleError, match="requires active_player_id"):
        active_player_id(inactive_state)
    with pytest.raises(GameLifecycleError, match="phase is unsupported"):
        battle_phase_kind(BattlePhase.COMMAND)
    with pytest.raises(GameLifecycleError, match="phase is unsupported"):
        timing_window_id(BattlePhase.COMMAND)
    with pytest.raises(GameLifecycleError, match="must be an object"):
        payload_object(())
    with pytest.raises(GameLifecycleError, match="must be a string"):
        payload_string({"id": 1}, key="id")
    with pytest.raises(GameLifecycleError, match="must be an int"):
        payload_int({"count": True}, key="count")
    with pytest.raises(GameLifecycleError, match="must be a list"):
        payload_string_tuple({"ids": ("a",)}, key="ids")
    with pytest.raises(GameLifecycleError, match="must be strings"):
        payload_string_tuple({"ids": [1]}, key="ids")
    with pytest.raises(GameLifecycleError, match="effect records must be a list"):
        payload_effect_records({"generic_rule_effect_records": ()})
    with pytest.raises(GameLifecycleError, match="effect record must be an object"):
        payload_effect_records({"generic_rule_effect_records": [1]})
    with pytest.raises(GameLifecycleError, match="selected payload must be an object"):
        selected_payload({"selected_catalog_target_effect": ()})
    with pytest.raises(GameLifecycleError, match="effect records must be a tuple"):
        validate_effect_record_tuple([])
    with pytest.raises(GameLifecycleError, match="effect record must be an object"):
        validate_effect_record_tuple((1,))
    with pytest.raises(GameLifecycleError, match="ids must be a tuple"):
        validate_identifier_tuple("ids", ["a"])


def test_catalog_selected_target_support_uses_real_battlefield_target_resolution() -> None:
    source_army, target_army = _mustered_core_armies()
    source_unit = source_army.units[0]
    target_unit = target_army.units[0]
    battlefield = _battlefield_for_units(
        source_army=source_army,
        source_unit=source_unit,
        source_x=10.0,
        target_army=target_army,
        target_unit=target_unit,
        target_x=10.4,
    )
    state = _state_with_battlefield(
        armies=(source_army, target_army),
        battlefield=battlefield,
        active_player_id=source_army.player_id,
        phase=BattlePhase.FIGHT,
    )
    distance_selection = replace(
        _fight_start_selection_clause(),
        conditions=(
            _condition(
                RuleConditionKind.DISTANCE_PREDICATE,
                ("distance_inches", None),
                ("negated", False),
                ("object_kind", "model"),
                ("object_reference", "this"),
                ("predicate", "within_engagement_range"),
                ("qualifier", None),
                ("range_kind", "engagement_range"),
            ),
        ),
    )
    source_model_ids = source_unit.own_model_ids()

    assert eligible_selection_target_unit_ids(
        state=state,
        source_player_id=source_army.player_id,
        source_unit_instance_id=source_unit.unit_instance_id,
        source_model_instance_id=source_model_ids[0],
        selection_clause=distance_selection,
        explicit_target_unit_ids=None,
    ) == (target_unit.unit_instance_id,)
    with pytest.raises(
        GameLifecycleError,
        match="Model-scoped selected-target distance requires a source model",
    ):
        eligible_selection_target_unit_ids(
            state=state,
            source_player_id=source_army.player_id,
            source_unit_instance_id=source_unit.unit_instance_id,
            source_model_instance_id=None,
            selection_clause=distance_selection,
            explicit_target_unit_ids=None,
        )
    with pytest.raises(GameLifecycleError, match="Rules unit_instance_id is unknown"):
        eligible_selection_target_unit_ids(
            state=state,
            source_player_id=source_army.player_id,
            source_unit_instance_id=source_unit.unit_instance_id,
            source_model_instance_id=source_model_ids[0],
            selection_clause=distance_selection,
            explicit_target_unit_ids=("other-target",),
        )
    assert (
        selection_source_model_ids(
            selection_clause=distance_selection,
            current_model_instance_ids=source_model_ids,
        )
        == source_model_ids
    )
    assert effect_target_unit_ids(
        state=state,
        source_player_id=source_army.player_id,
        source_unit=source_unit,
        selected_target_unit_instance_id=target_unit.unit_instance_id,
        clause=replace(
            _effect_clause(
                clause_id="test:selected-target:this-unit",
                duration=_duration("phase"),
                effect_kind=RuleEffectKind.MODIFY_CHARACTERISTIC,
                characteristic="attacks",
                delta=1,
            ),
            target=RuleTargetSpec(kind=RuleTargetKind.THIS_UNIT, source_span=_span()),
        ),
    ) == (source_unit.unit_instance_id,)
    assert effect_target_unit_ids(
        state=state,
        source_player_id=source_army.player_id,
        source_unit=source_unit,
        selected_target_unit_instance_id=target_unit.unit_instance_id,
        clause=replace(
            _effect_clause(
                clause_id="test:selected-target:selected-unit",
                duration=_duration("phase"),
                effect_kind=RuleEffectKind.SET_CONTEXTUAL_STATUS,
                status="benefit_of_cover",
                operation="deny",
            ),
            target=RuleTargetSpec(kind=RuleTargetKind.SELECTED_TARGET, source_span=_span()),
        ),
    ) == (target_unit.unit_instance_id,)

    friendly_clause = replace(
        _effect_clause(
            clause_id="test:selected-target:friendly-unit",
            duration=_duration("phase"),
            effect_kind=RuleEffectKind.MODIFY_CHARACTERISTIC,
            characteristic="objective_control",
            delta=1,
            conditions=(
                _condition(
                    RuleConditionKind.KEYWORD_GATE,
                    ("required_keyword", "INFANTRY"),
                ),
            ),
        ),
        target=RuleTargetSpec(
            kind=RuleTargetKind.FRIENDLY_UNIT,
            source_span=_span(),
            parameters=_parameters(("required_keyword_sequence", ("IMPERIUM",))),
        ),
    )

    assert required_keywords_for_clause(friendly_clause) == ("IMPERIUM", "INFANTRY")
    assert (
        effect_target_unit_ids(
            state=state,
            source_player_id=source_army.player_id,
            source_unit=source_unit,
            selected_target_unit_instance_id=target_unit.unit_instance_id,
            clause=friendly_clause,
        )
        == ()
    )
    with pytest.raises(GameLifecycleError, match="numeric range is malformed"):
        any_models_satisfy_distance(
            source_models=(),
            target_models=(),
            parameters={"range_kind": "numeric_range"},
        )


def test_catalog_selected_target_explicit_component_id_canonicalizes_attached_target() -> None:
    attached_target_army, source_army = _mustered_attached_once_per_battle_armies()
    source_unit = source_army.units[0]
    target_component = attached_target_army.units[0]
    attached_target_id = attached_target_army.attached_units[0].attached_unit_instance_id
    scenario = create_deterministic_battlefield_scenario(
        battlefield_id="catalog-selected-target-explicit-attached-component",
        armies=(source_army, attached_target_army),
    )
    state = _state_with_battlefield(
        armies=(source_army, attached_target_army),
        battlefield=scenario.battlefield_state,
        active_player_id=source_army.player_id,
        phase=BattlePhase.FIGHT,
    )

    assert eligible_selection_target_unit_ids(
        state=state,
        source_player_id=source_army.player_id,
        source_unit_instance_id=source_unit.unit_instance_id,
        source_model_instance_id=None,
        selection_clause=_fight_start_selection_clause(),
        explicit_target_unit_ids=(target_component.unit_instance_id,),
    ) == (attached_target_id,)


def test_catalog_selected_target_visibility_gate_uses_real_line_of_sight() -> None:
    source_army, target_army = _mustered_core_armies()
    source_unit = source_army.units[0]
    target_unit = target_army.units[0]
    battlefield = _battlefield_for_units(
        source_army=source_army,
        source_unit=source_unit,
        source_x=10.0,
        target_army=target_army,
        target_unit=target_unit,
        target_x=20.0,
    )
    visible_state = _state_with_battlefield(
        armies=(source_army, target_army),
        battlefield=battlefield,
        active_player_id=source_army.player_id,
        phase=BattlePhase.FIGHT,
    )
    record = _compiled_record(
        record_id="record:selected-target:visible-gate",
        raw_text=(
            'At the start of the Fight phase, select one enemy unit within 18" of and '
            "visible to this model. Until the end of the phase, each time a friendly "
            "Khorne Legiones Daemonica unit makes an attack that targets that unit, "
            "improve the Strength, Armour Penetration and Damage characteristics of "
            "that attack by 1."
        ),
        source_unit=source_unit,
        trigger_kind=TimingTriggerKind.START_PHASE,
    )
    selection_clause = catalog_selected_target_clauses_from_record(record)[0]
    source_model_id = source_unit.own_model_ids()[0]

    assert eligible_selection_target_unit_ids(
        state=visible_state,
        source_player_id=source_army.player_id,
        source_unit_instance_id=source_unit.unit_instance_id,
        source_model_instance_id=source_model_id,
        selection_clause=selection_clause,
        explicit_target_unit_ids=None,
    ) == (target_unit.unit_instance_id,)

    blocked_state = _state_with_battlefield(
        armies=(source_army, target_army),
        battlefield=replace(battlefield, terrain_features=(_line_blocking_ruin(),)),
        active_player_id=source_army.player_id,
        phase=BattlePhase.FIGHT,
    )

    assert (
        eligible_selection_target_unit_ids(
            state=blocked_state,
            source_player_id=source_army.player_id,
            source_unit_instance_id=source_unit.unit_instance_id,
            source_model_instance_id=source_model_id,
            selection_clause=selection_clause,
            explicit_target_unit_ids=None,
        )
        == ()
    )


def test_catalog_selected_target_conditions_resolve_their_declared_geometry_scope() -> None:
    source_army, target_army = _mustered_core_armies()
    source_unit = replace(
        source_army.units[0],
        own_models=source_army.units[0].own_models[:2],
    )
    source_army = _army_with_unit(source_army, source_unit)
    target_unit = target_army.units[0]
    source_model_id = source_unit.own_models[0].model_instance_id
    selection_clause = replace(
        _fight_start_selection_clause(),
        conditions=(
            _selection_engagement_range_condition(object_kind="unit"),
            _condition(
                RuleConditionKind.VISIBILITY_PREDICATE,
                ("observer", "this_model"),
                ("predicate", "visible_to"),
                ("target_reference", "selected_unit"),
            ),
        ),
    )
    state = _state_with_battlefield(
        armies=(source_army, target_army),
        battlefield=_battlefield_for_units_with_model_xs(
            source_army=source_army,
            source_unit=source_unit,
            source_model_xs=(30.0, 10.0),
            target_army=target_army,
            target_unit=target_unit,
            target_model_xs=_model_xs_for_unit(unit=target_unit, start_x=10.4),
        ),
        active_player_id=source_army.player_id,
        phase=BattlePhase.FIGHT,
    )

    assert fight_start_selected_target_selection_is_supported(selection_clause)
    assert eligible_selection_target_unit_ids(
        state=state,
        source_player_id=source_army.player_id,
        source_unit_instance_id=source_unit.unit_instance_id,
        source_model_instance_id=source_model_id,
        selection_clause=selection_clause,
        explicit_target_unit_ids=None,
    ) == (target_unit.unit_instance_id,)


def test_catalog_selected_target_distance_gate_ignores_dead_placements() -> None:
    source_army, target_army = _mustered_core_armies()
    source_unit = source_army.units[0]
    target_unit = target_army.units[0]
    distance_selection = replace(
        _fight_start_selection_clause(),
        conditions=(
            _condition(
                RuleConditionKind.DISTANCE_PREDICATE,
                ("distance_inches", None),
                ("negated", False),
                ("object_kind", "model"),
                ("object_reference", "this"),
                ("predicate", "within_engagement_range"),
                ("qualifier", None),
                ("range_kind", "engagement_range"),
            ),
        ),
    )

    dead_source_unit = _unit_with_dead_model(source_unit, index=0)
    dead_source_army = _army_with_unit(source_army, dead_source_unit)
    dead_source_state = _state_with_battlefield(
        armies=(dead_source_army, target_army),
        battlefield=_battlefield_for_units_with_model_xs(
            source_army=dead_source_army,
            source_unit=dead_source_unit,
            source_model_xs=(10.0, 30.0, 32.0, 34.0, 36.0),
            target_army=target_army,
            target_unit=target_unit,
            target_model_xs=(10.4, 40.0, 42.0, 44.0, 46.0),
        ),
        active_player_id=dead_source_army.player_id,
        phase=BattlePhase.FIGHT,
    )

    assert (
        eligible_selection_target_unit_ids(
            state=dead_source_state,
            source_player_id=dead_source_army.player_id,
            source_unit_instance_id=dead_source_unit.unit_instance_id,
            source_model_instance_id=dead_source_unit.own_models[0].model_instance_id,
            selection_clause=distance_selection,
            explicit_target_unit_ids=None,
        )
        == ()
    )

    dead_target_unit = _unit_with_dead_model(target_unit, index=0)
    dead_target_army = _army_with_unit(target_army, dead_target_unit)
    dead_target_state = _state_with_battlefield(
        armies=(source_army, dead_target_army),
        battlefield=_battlefield_for_units_with_model_xs(
            source_army=source_army,
            source_unit=source_unit,
            source_model_xs=(10.0, 30.0, 32.0, 34.0, 36.0),
            target_army=dead_target_army,
            target_unit=dead_target_unit,
            target_model_xs=(10.4, 40.0, 42.0, 44.0, 46.0),
        ),
        active_player_id=source_army.player_id,
        phase=BattlePhase.FIGHT,
    )

    assert (
        eligible_selection_target_unit_ids(
            state=dead_target_state,
            source_player_id=source_army.player_id,
            source_unit_instance_id=source_unit.unit_instance_id,
            source_model_instance_id=source_unit.own_models[0].model_instance_id,
            selection_clause=distance_selection,
            explicit_target_unit_ids=None,
        )
        == ()
    )


def test_catalog_command_point_bundle_registers_source_backed_generic_consumers() -> None:
    source_army, target_army = _mustered_once_per_battle_armies()
    source_unit = source_army.units[0]
    target_unit = target_army.units[0]
    destroyed_record = _command_point_record(
        record_id="record:catalog-cp:destroyed-character",
        raw_text=DESTROYED_CHARACTER_COMMAND_POINT_TEXT,
        source_unit=source_unit,
        trigger_kind=TimingTriggerKind.AFTER_UNIT_DESTROYED,
    )
    leadership_record = _command_point_record(
        record_id="record:catalog-cp:leadership",
        raw_text=LEADERSHIP_COMMAND_POINT_TEXT,
        source_unit=source_unit,
        trigger_kind=TimingTriggerKind.END_PHASE,
    )
    opponent_cost_record = _command_point_record(
        record_id="record:catalog-cp:opponent-cost",
        raw_text=OPPONENT_STRATAGEM_COST_TEXT,
        source_unit=source_unit,
        trigger_kind=TimingTriggerKind.ANY_PHASE,
    )
    own_cost_record = _command_point_record(
        record_id="record:catalog-cp:own-cost",
        raw_text=OWN_STRATAGEM_COST_TEXT,
        source_unit=target_unit,
        trigger_kind=TimingTriggerKind.ANY_PHASE,
    )
    catalog = ArmyCatalog.phase9a_canonical_content_pack()

    bundle = RuntimeContentBundle.from_contributions(
        activation=RuntimeContentActivation.from_armies(
            armies=(source_army, target_army),
            catalog=catalog,
        ),
        armies=(source_army, target_army),
        catalog=catalog,
        contributions=(),
        base_ability_records=(
            destroyed_record,
            leadership_record,
            opponent_cost_record,
            own_cost_record,
        ),
    )

    assert CATALOG_IR_COMMAND_POINT_GAIN_CONSUMER_ID in {
        binding.hook_id for binding in bundle.unit_destroyed_hook_registry.all_bindings()
    }
    assert {
        binding.source_id for binding in bundle.stratagem_cost_modifier_registry.all_bindings()
    } == {opponent_cost_record.definition.source_id, own_cost_record.definition.source_id}
    assert {
        binding.source_id for binding in bundle.stratagem_cost_choice_hook_registry.all_bindings()
    } >= {CATALOG_IR_STRATAGEM_COST_MODIFIER_CONSUMER_ID}
    subscriptions = bundle.event_index.subscriptions_for(TimingTriggerKind.END_PHASE)
    assert any(
        subscription.source_rule_id == leadership_record.definition.source_id
        and subscription.filters
        == {
            "phase": BattlePhaseKind.COMMAND.value,
            "player_id": source_army.player_id,
        }
        for subscription in subscriptions
    )


def test_catalog_command_point_destroyed_character_gain_is_scoped_and_idempotent() -> None:
    source_army, target_army = _mustered_once_per_battle_armies()
    source_unit = source_army.units[0]
    character_target = replace(
        target_army.units[0],
        keywords=tuple(sorted((*target_army.units[0].keywords, "CHARACTER"))),
    )
    target_army = _army_with_unit(target_army, character_target)
    state = _state_with_battlefield(
        armies=(source_army, target_army),
        battlefield=_battlefield_for_units(
            source_army=source_army,
            source_unit=source_unit,
            source_x=10.0,
            target_army=target_army,
            target_unit=character_target,
            target_x=20.0,
        ),
        active_player_id=source_army.player_id,
        phase=BattlePhase.SHOOTING,
    )
    record = _command_point_record(
        record_id="record:catalog-cp:destroyed-character-runtime",
        raw_text=DESTROYED_CHARACTER_COMMAND_POINT_TEXT,
        source_unit=source_unit,
        trigger_kind=TimingTriggerKind.AFTER_UNIT_DESTROYED,
    )
    runtime = _command_point_runtime(
        armies=(source_army, target_army),
        records_by_player={source_army.player_id: (record,)},
    )
    decisions = DecisionController()
    attacker_model_id = source_unit.own_models[0].model_instance_id
    non_attack_event = decisions.event_log.append(
        "model_destroyed",
        {
            "game_id": state.game_id,
            "battle_round": state.battle_round,
            "active_player_id": state.active_player_id,
            "phase": BattlePhase.SHOOTING.value,
            **ModelDestructionAttribution.for_non_attack(
                destroying_player_id=source_army.player_id,
                source_kind=DestructionSourceKind.DEADLY_DEMISE,
                source_rules_unit_instance_id=None,
                source_model_instance_id=None,
            ).to_payload(),
            "target_unit_instance_id": character_target.unit_instance_id,
            "model_instance_id": character_target.own_models[0].model_instance_id,
        },
    )
    runtime.resolve_unit_destroyed(
        UnitDestroyedContext(
            state=state,
            decisions=decisions,
            completed_phase=BattlePhase.SHOOTING,
            model_destroyed_event_id=non_attack_event.event_id,
            model_destroyed_payload=cast(dict[str, JsonValue], non_attack_event.payload),
            destroying_player_id=source_army.player_id,
            destroyed_unit_instance_id=character_target.unit_instance_id,
            destroyed_player_id=target_army.player_id,
        )
    )
    assert state.command_point_total(source_army.player_id) == 0

    destroyed_event = decisions.event_log.append(
        "model_destroyed",
        {
            "game_id": state.game_id,
            "battle_round": state.battle_round,
            "active_player_id": state.active_player_id,
            "phase": BattlePhase.SHOOTING.value,
            **ModelDestructionAttribution.for_attack(
                destroying_player_id=source_army.player_id,
                attacking_unit_instance_id=source_unit.unit_instance_id,
                attacking_model_instance_id=attacker_model_id,
                weapon_profile=_first_catalog_weapon_profile(),
                attack_context_id="attack-context:destroyed-character-runtime",
            ).to_payload(),
            "target_unit_instance_id": character_target.unit_instance_id,
            "model_instance_id": character_target.own_models[0].model_instance_id,
        },
    )
    destroyed_payload = cast(dict[str, JsonValue], destroyed_event.payload)
    context = UnitDestroyedContext(
        state=state,
        decisions=decisions,
        completed_phase=BattlePhase.SHOOTING,
        model_destroyed_event_id=destroyed_event.event_id,
        model_destroyed_payload=destroyed_payload,
        destroying_player_id=source_army.player_id,
        destroyed_unit_instance_id=character_target.unit_instance_id,
        destroyed_player_id=target_army.player_id,
    )

    runtime.resolve_unit_destroyed(context)
    runtime.resolve_unit_destroyed(context)

    assert state.command_point_total(source_army.player_id) == 1
    gain_events = tuple(
        event
        for event in decisions.event_log.records
        if event.event_type == CATALOG_IR_COMMAND_POINT_GAIN_EVENT
    )
    assert len(gain_events) == 1
    payload = cast(dict[str, JsonValue], gain_events[0].payload)
    assert payload["source_record_id"] == record.record_id
    assert payload["source_model_instance_id"] == attacker_model_id
    assert payload["destroyed_unit_instance_id"] == character_target.unit_instance_id


def test_catalog_command_point_leadership_gain_dispatches_at_owner_command_phase_end() -> None:
    source_army, target_army = _mustered_once_per_battle_armies()
    source_unit = _unit_with_leadership(source_army.units[0], leadership=2)
    source_army = _army_with_unit(source_army, source_unit)
    state = _state_with_battlefield(
        armies=(source_army, target_army),
        battlefield=_battlefield_for_units(
            source_army=source_army,
            source_unit=source_unit,
            source_x=10.0,
            target_army=target_army,
            target_unit=target_army.units[0],
            target_x=20.0,
        ),
        active_player_id=source_army.player_id,
        phase=BattlePhase.COMMAND,
    )
    record = _command_point_record(
        record_id="record:catalog-cp:leadership-runtime",
        raw_text=LEADERSHIP_COMMAND_POINT_TEXT,
        source_unit=source_unit,
        trigger_kind=TimingTriggerKind.END_PHASE,
    )
    runtime = _command_point_runtime(
        armies=(source_army, target_army),
        records_by_player={source_army.player_id: (record,)},
    )
    handler_registry = RuntimeContentEventHandlerRegistry.from_bindings(
        runtime.event_handler_bindings()
    )
    event_index = RuntimeContentEventIndex.from_subscriptions(
        runtime.event_subscriptions(),
        handler_registry=handler_registry,
    )
    decisions = DecisionController()

    results = event_index.dispatch(
        RuntimeContentEvent(
            event_id="runtime-event:catalog-cp:leadership",
            game_id=state.game_id,
            player_id=source_army.player_id,
            battle_round=state.battle_round,
            trigger_kind=TimingTriggerKind.END_PHASE,
            phase=BattlePhaseKind.COMMAND,
            active_player_id=source_army.player_id,
        ),
        state=state,
        decisions=decisions,
        ruleset_descriptor=RulesetDescriptor.warhammer_40000_eleventh(),
        army_catalog=ArmyCatalog.phase9a_canonical_content_pack(),
        runtime_modifier_registry=RuntimeModifierRegistry.empty(),
    )

    assert len(results) == 1
    assert state.command_point_total(source_army.player_id) == 1
    resolution_events = tuple(
        event
        for event in decisions.event_log.records
        if event.event_type == CATALOG_IR_COMMAND_POINT_LEADERSHIP_TEST_EVENT
    )
    assert len(resolution_events) == 1
    resolution = cast(dict[str, JsonValue], resolution_events[0].payload)
    assert resolution["passed"] is True
    assert resolution["leadership_target"] == 2
    assert resolution["source_record_id"] == record.record_id


@pytest.mark.parametrize(
    ("raw_text", "trigger_kind", "expects_dice_roll"),
    [
        (DIRECT_PHASE_COMMAND_POINT_TEXT, TimingTriggerKind.START_PHASE, False),
        (FIXED_ROLL_COMMAND_POINT_TEXT, TimingTriggerKind.END_PHASE, True),
    ],
)
def test_catalog_command_point_phase_gain_supports_automatic_and_fixed_roll_gates(
    raw_text: str,
    trigger_kind: TimingTriggerKind,
    expects_dice_roll: bool,
) -> None:
    source_army, target_army = _mustered_once_per_battle_armies()
    source_unit = source_army.units[0]
    state = _state_with_battlefield(
        armies=(source_army, target_army),
        battlefield=_battlefield_for_units(
            source_army=source_army,
            source_unit=source_unit,
            source_x=10.0,
            target_army=target_army,
            target_unit=target_army.units[0],
            target_x=20.0,
        ),
        active_player_id=source_army.player_id,
        phase=BattlePhase.COMMAND,
    )
    record = _command_point_record(
        record_id=f"record:catalog-cp:phase-gain:{trigger_kind.value}",
        raw_text=raw_text,
        source_unit=source_unit,
        trigger_kind=trigger_kind,
    )
    runtime = _command_point_runtime(
        armies=(source_army, target_army),
        records_by_player={source_army.player_id: (record,)},
    )
    handler_registry = RuntimeContentEventHandlerRegistry.from_bindings(
        runtime.event_handler_bindings()
    )
    event_index = RuntimeContentEventIndex.from_subscriptions(
        runtime.event_subscriptions(),
        handler_registry=handler_registry,
    )
    decisions = DecisionController()

    results = event_index.dispatch(
        RuntimeContentEvent(
            event_id=f"runtime-event:catalog-cp:{trigger_kind.value}",
            game_id=state.game_id,
            player_id=source_army.player_id,
            battle_round=state.battle_round,
            trigger_kind=trigger_kind,
            phase=BattlePhaseKind.COMMAND,
            active_player_id=source_army.player_id,
        ),
        state=state,
        decisions=decisions,
        ruleset_descriptor=RulesetDescriptor.warhammer_40000_eleventh(),
        army_catalog=ArmyCatalog.phase9a_canonical_content_pack(),
        runtime_modifier_registry=RuntimeModifierRegistry.empty(),
    )

    assert len(results) == 1
    assert state.command_point_total(source_army.player_id) == 1
    assert sum(event.event_type == "dice_rolled" for event in decisions.event_log.records) == int(
        expects_dice_roll
    )
    resolution = next(
        event
        for event in decisions.event_log.records
        if event.event_type == CATALOG_IR_COMMAND_POINT_PHASE_GAIN_EVENT
    )
    payload = cast(dict[str, JsonValue], resolution.payload)
    assert payload["test_kind"] == ("fixed_roll" if expects_dice_roll else "automatic")
    assert payload["passed"] is True


def test_catalog_command_point_phase_gain_records_failure_cap_and_inactive_owner() -> None:
    source_army, target_army = _mustered_once_per_battle_armies()
    source_unit = source_army.units[0]
    state = _state_with_battlefield(
        armies=(source_army, target_army),
        battlefield=_battlefield_for_units(
            source_army=source_army,
            source_unit=source_unit,
            source_x=10.0,
            target_army=target_army,
            target_unit=target_army.units[0],
            target_x=20.0,
        ),
        active_player_id=source_army.player_id,
        phase=BattlePhase.COMMAND,
    )
    automatic_record = _command_point_record(
        record_id="record:catalog-cp:phase-gain:cap",
        raw_text=DIRECT_PHASE_COMMAND_POINT_TEXT,
        source_unit=source_unit,
        trigger_kind=TimingTriggerKind.START_PHASE,
    )
    failed_roll_record = _command_point_record(
        record_id="record:catalog-cp:phase-gain:failed-roll",
        raw_text=("At the end of your Command phase, roll one D6: on a 7+, you gain 1CP."),
        source_unit=source_unit,
        trigger_kind=TimingTriggerKind.END_PHASE,
    )
    runtime = _command_point_runtime(
        armies=(source_army, target_army),
        records_by_player={
            source_army.player_id: (automatic_record, failed_roll_record),
        },
    )
    handler_registry = RuntimeContentEventHandlerRegistry.from_bindings(
        runtime.event_handler_bindings()
    )
    event_index = RuntimeContentEventIndex.from_subscriptions(
        runtime.event_subscriptions(),
        handler_registry=handler_registry,
    )
    decisions = DecisionController()

    def dispatch(
        *, event_id: str, trigger_kind: TimingTriggerKind, active_player_id: str
    ) -> tuple[RuntimeContentEventResult, ...]:
        return event_index.dispatch(
            RuntimeContentEvent(
                event_id=event_id,
                game_id=state.game_id,
                player_id=source_army.player_id,
                battle_round=state.battle_round,
                trigger_kind=trigger_kind,
                phase=BattlePhaseKind.COMMAND,
                active_player_id=active_player_id,
            ),
            state=state,
            decisions=decisions,
            ruleset_descriptor=RulesetDescriptor.warhammer_40000_eleventh(),
            army_catalog=ArmyCatalog.phase9a_canonical_content_pack(),
            runtime_modifier_registry=RuntimeModifierRegistry.empty(),
        )

    inactive_results = dispatch(
        event_id="runtime-event:catalog-cp:inactive-owner",
        trigger_kind=TimingTriggerKind.START_PHASE,
        active_player_id=target_army.player_id,
    )
    dispatch(
        event_id="runtime-event:catalog-cp:gain-applied",
        trigger_kind=TimingTriggerKind.START_PHASE,
        active_player_id=source_army.player_id,
    )
    dispatch(
        event_id="runtime-event:catalog-cp:gain-capped",
        trigger_kind=TimingTriggerKind.START_PHASE,
        active_player_id=source_army.player_id,
    )
    dispatch(
        event_id="runtime-event:catalog-cp:roll-failed",
        trigger_kind=TimingTriggerKind.END_PHASE,
        active_player_id=source_army.player_id,
    )

    assert inactive_results[0].replay_payload == {"resolutions": []}
    assert state.command_point_total(source_army.player_id) == 1
    assert any(
        event.event_type == "command_points_gain_capped" for event in decisions.event_log.records
    )
    failed_resolution = next(
        event.payload
        for event in decisions.event_log.records
        if event.event_type == CATALOG_IR_COMMAND_POINT_PHASE_GAIN_EVENT
        and isinstance(event.payload, dict)
        and event.payload.get("runtime_event_id") == "runtime-event:catalog-cp:roll-failed"
    )
    assert failed_resolution["passed"] is False
    assert failed_resolution["command_point_result"] is None


def test_catalog_command_point_cost_choices_modify_only_the_current_stratagem_use() -> None:
    source_army, target_army = _mustered_once_per_battle_armies()
    source_unit = source_army.units[0]
    target_unit = target_army.units[0]
    state = _state_with_battlefield(
        armies=(source_army, target_army),
        battlefield=_battlefield_for_units(
            source_army=source_army,
            source_unit=source_unit,
            source_x=10.0,
            target_army=target_army,
            target_unit=target_unit,
            target_x=18.0,
        ),
        active_player_id=target_army.player_id,
        phase=BattlePhase.SHOOTING,
    )
    record = _command_point_record(
        record_id="record:catalog-cp:opponent-cost-runtime",
        raw_text=OPPONENT_STRATAGEM_COST_TEXT,
        source_unit=source_unit,
        trigger_kind=TimingTriggerKind.ANY_PHASE,
    )
    second_record = _command_point_record(
        record_id="record:catalog-cp:opponent-cost-runtime-second",
        raw_text=OPPONENT_STRATAGEM_COST_TEXT,
        source_unit=source_unit,
        trigger_kind=TimingTriggerKind.ANY_PHASE,
    )
    runtime = _command_point_runtime(
        armies=(source_army, target_army),
        records_by_player={source_army.player_id: (record, second_record)},
    )
    decisions = DecisionController()
    definition = _test_stratagem_definition(command_point_cost=1)
    eligibility = StratagemEligibilityContext.from_state(
        state=state,
        player_id=target_army.player_id,
        trigger_kind=TimingTriggerKind.START_PHASE,
    )
    target_binding = StratagemTargetBinding(
        target_kind=StratagemTargetKind.FRIENDLY_UNIT,
        target_player_id=target_army.player_id,
        target_unit_instance_id=target_unit.unit_instance_id,
    )
    source_request, source_result = _test_stratagem_source_decision(
        actor_id=target_army.player_id,
        suffix="opponent-cost",
    )
    request_context = StratagemCostChoiceRequestContext(
        state=state,
        decisions=decisions,
        source_request=source_request,
        source_result=source_result,
        definition=definition,
        eligibility_context=eligibility,
        target_binding=target_binding,
        effect_selection=None,
    )

    request = runtime.stratagem_cost_choice_request(request_context)
    assert request is not None
    assert request.actor_id == source_army.player_id
    use_option = next(
        option
        for option in request.options
        if isinstance(option.payload, dict) and option.payload.get("use_ability") is True
    )
    result = DecisionResult.for_request(
        result_id="result:catalog-cp:opponent-cost",
        request=request,
        selected_option_id=use_option.option_id,
    )
    result_payload = cast(dict[str, JsonValue], result.payload)
    request_payload = cast(dict[str, JsonValue], request.payload)
    with pytest.raises(GameLifecycleError, match="cost choice actor drift"):
        runtime.apply_stratagem_cost_choice_result(
            StratagemCostChoiceResultContext(
                state=state,
                decisions=decisions,
                request=request,
                result=replace(result, actor_id=target_army.player_id),
                source_request=source_request,
                source_result=source_result,
                definition=definition,
                eligibility_context=eligibility,
                target_binding=target_binding,
                effect_selection=None,
            )
        )
    with pytest.raises(GameLifecycleError, match="cost choice actor drift"):
        runtime.apply_stratagem_cost_choice_result(
            StratagemCostChoiceResultContext(
                state=state,
                decisions=decisions,
                request=replace(request, actor_id=target_army.player_id),
                result=replace(result, actor_id=target_army.player_id),
                source_request=source_request,
                source_result=source_result,
                definition=definition,
                eligibility_context=eligibility,
                target_binding=target_binding,
                effect_selection=None,
            )
        )
    assert not any(
        event.event_type == CATALOG_IR_STRATAGEM_COST_CHOICE_EVENT
        for event in decisions.event_log.records
    )
    assert not runtime.apply_stratagem_cost_choice_result(
        StratagemCostChoiceResultContext(
            state=state,
            decisions=decisions,
            request=replace(
                request,
                payload={**request_payload, "hook_id": "catalog-ir:unrelated-hook"},
            ),
            result=result,
            source_request=source_request,
            source_result=source_result,
            definition=definition,
            eligibility_context=eligibility,
            target_binding=target_binding,
            effect_selection=None,
        )
    )
    with pytest.raises(GameLifecycleError, match="source_clause_id drift"):
        runtime.apply_stratagem_cost_choice_result(
            StratagemCostChoiceResultContext(
                state=state,
                decisions=decisions,
                request=request,
                result=replace(
                    result,
                    payload={**result_payload, "source_clause_id": "drifted-clause"},
                ),
                source_request=source_request,
                source_result=source_result,
                definition=definition,
                eligibility_context=eligibility,
                target_binding=target_binding,
                effect_selection=None,
            )
        )
    assert not any(
        event.event_type == CATALOG_IR_STRATAGEM_COST_CHOICE_EVENT
        for event in decisions.event_log.records
    )
    assert runtime.apply_stratagem_cost_choice_result(
        StratagemCostChoiceResultContext(
            state=state,
            decisions=decisions,
            request=request,
            result=result,
            source_request=source_request,
            source_result=source_result,
            definition=definition,
            eligibility_context=eligibility,
            target_binding=target_binding,
            effect_selection=None,
        )
    )
    second_request = runtime.stratagem_cost_choice_request(request_context)
    assert second_request is not None
    assert second_request.payload != request.payload
    decline_option = next(
        option
        for option in second_request.options
        if isinstance(option.payload, dict) and option.payload.get("use_ability") is False
    )
    second_result = DecisionResult.for_request(
        result_id="result:catalog-cp:opponent-cost-second",
        request=second_request,
        selected_option_id=decline_option.option_id,
    )
    assert runtime.apply_stratagem_cost_choice_result(
        StratagemCostChoiceResultContext(
            state=state,
            decisions=decisions,
            request=second_request,
            result=second_result,
            source_request=source_request,
            source_result=source_result,
            definition=definition,
            eligibility_context=eligibility,
            target_binding=target_binding,
            effect_selection=None,
        )
    )
    registry = StratagemCostModifierRegistry.from_bindings(
        runtime.stratagem_cost_modifier_bindings()
    )

    applied_cost = registry.modified_command_point_cost(
        _cost_modifier_context(
            state=state,
            decisions=decisions,
            definition=definition,
            eligibility=eligibility,
            target_binding=target_binding,
            source_request_id=source_request.request_id,
            source_result_id=source_result.result_id,
        )
    )
    unrelated_cost = registry.modified_command_point_cost(
        _cost_modifier_context(
            state=state,
            decisions=decisions,
            definition=definition,
            eligibility=eligibility,
            target_binding=target_binding,
            source_request_id="request:unrelated-stratagem",
            source_result_id="result:unrelated-stratagem",
        )
    )
    no_choice_cost = registry.modified_command_point_cost(
        StratagemCostModifierContext(
            state=state,
            definition=definition,
            eligibility_context=eligibility,
            target_binding=target_binding,
            effect_selection=None,
            base_command_point_cost=definition.command_point_cost,
            current_command_point_cost=definition.command_point_cost,
        )
    )

    assert applied_cost == 2
    assert unrelated_cost == 1
    assert no_choice_cost == 1
    assert runtime.stratagem_cost_choice_request(request_context) is None
    assert (
        sum(
            event.event_type == CATALOG_IR_STRATAGEM_COST_CHOICE_EVENT
            for event in decisions.event_log.records
        )
        == 2
    )


def test_catalog_unnamed_zero_cp_rule_reduces_current_use_by_one_in_generic_registry() -> None:
    source_army, target_army = _mustered_core_armies()
    source_unit = source_army.units[0]
    target_unit = target_army.units[0]
    state = _state_with_battlefield(
        armies=(source_army, target_army),
        battlefield=_battlefield_for_units(
            source_army=source_army,
            source_unit=source_unit,
            source_x=10.0,
            target_army=target_army,
            target_unit=target_unit,
            target_x=20.0,
        ),
        active_player_id=source_army.player_id,
        phase=BattlePhase.SHOOTING,
    )
    record = _command_point_record(
        record_id="record:catalog-cp:unnamed-zero-cp-runtime",
        raw_text=UNNAMED_ZERO_CP_STRATAGEM_COST_TEXT,
        source_unit=source_unit,
        trigger_kind=TimingTriggerKind.ANY_PHASE,
    )
    runtime = _command_point_runtime(
        armies=(source_army, target_army),
        records_by_player={source_army.player_id: (record,)},
    )
    decisions = DecisionController()
    definition = _test_stratagem_definition(command_point_cost=1)
    eligibility = StratagemEligibilityContext.from_state(
        state=state,
        player_id=source_army.player_id,
        trigger_kind=TimingTriggerKind.START_PHASE,
    )
    target_binding = StratagemTargetBinding(
        target_kind=StratagemTargetKind.FRIENDLY_UNIT,
        target_player_id=source_army.player_id,
        target_unit_instance_id=source_unit.unit_instance_id,
    )
    source_request, source_result = _test_stratagem_source_decision(
        actor_id=source_army.player_id,
        suffix="own-cost",
    )
    request_context = StratagemCostChoiceRequestContext(
        state=state,
        decisions=decisions,
        source_request=source_request,
        source_result=source_result,
        definition=definition,
        eligibility_context=eligibility,
        target_binding=target_binding,
        effect_selection=None,
    )
    request = runtime.stratagem_cost_choice_request(request_context)
    assert request is not None
    use_option = next(
        option
        for option in request.options
        if isinstance(option.payload, dict) and option.payload.get("use_ability") is True
    )
    result = DecisionResult.for_request(
        result_id="result:catalog-cp:own-cost",
        request=request,
        selected_option_id=use_option.option_id,
    )
    assert runtime.apply_stratagem_cost_choice_result(
        StratagemCostChoiceResultContext(
            state=state,
            decisions=decisions,
            request=request,
            result=result,
            source_request=source_request,
            source_result=source_result,
            definition=definition,
            eligibility_context=eligibility,
            target_binding=target_binding,
            effect_selection=None,
        )
    )

    registry = StratagemCostModifierRegistry.from_bindings(
        runtime.stratagem_cost_modifier_bindings()
    )
    no_choice_cost = registry.modified_command_point_cost(
        StratagemCostModifierContext(
            state=state,
            definition=definition,
            eligibility_context=eligibility,
            target_binding=target_binding,
            effect_selection=None,
            base_command_point_cost=definition.command_point_cost,
            current_command_point_cost=definition.command_point_cost,
        )
    )
    accepted_cost = registry.modified_command_point_cost(
        _cost_modifier_context(
            state=state,
            decisions=decisions,
            definition=definition,
            eligibility=eligibility,
            target_binding=target_binding,
            source_request_id=source_request.request_id,
            source_result_id=source_result.result_id,
        )
    )

    assert no_choice_cost == 1
    assert accepted_cost == 0


def test_catalog_legacy_grenade_cost_rule_only_matches_explosives_stratagem_id() -> None:
    source_army, target_army = _mustered_core_armies()
    source_unit = source_army.units[0]
    target_unit = target_army.units[0]
    state = _state_with_battlefield(
        armies=(source_army, target_army),
        battlefield=_battlefield_for_units(
            source_army=source_army,
            source_unit=source_unit,
            source_x=10.0,
            target_army=target_army,
            target_unit=target_unit,
            target_x=20.0,
        ),
        active_player_id=source_army.player_id,
        phase=BattlePhase.SHOOTING,
    )
    record = _command_point_record(
        record_id="record:catalog-cp:legacy-grenade-zero-cp-runtime",
        raw_text=LEGACY_GRENADE_ZERO_CP_STRATAGEM_COST_TEXT,
        source_unit=source_unit,
        trigger_kind=TimingTriggerKind.ANY_PHASE,
    )
    runtime = _command_point_runtime(
        armies=(source_army, target_army),
        records_by_player={source_army.player_id: (record,)},
    )
    eligibility = StratagemEligibilityContext.from_state(
        state=state,
        player_id=source_army.player_id,
        trigger_kind=TimingTriggerKind.START_PHASE,
    )
    target_binding = StratagemTargetBinding(
        target_kind=StratagemTargetKind.FRIENDLY_UNIT,
        target_player_id=source_army.player_id,
        target_unit_instance_id=source_unit.unit_instance_id,
    )
    source_request, source_result = _test_stratagem_source_decision(
        actor_id=source_army.player_id,
        suffix="legacy-grenade-zero-cp",
    )

    def request_for(stratagem_id: str) -> DecisionRequest | None:
        return runtime.stratagem_cost_choice_request(
            StratagemCostChoiceRequestContext(
                state=state,
                decisions=DecisionController(),
                source_request=source_request,
                source_result=source_result,
                definition=replace(
                    _test_stratagem_definition(command_point_cost=1),
                    stratagem_id=stratagem_id,
                ),
                eligibility_context=eligibility,
                target_binding=target_binding,
                effect_selection=None,
            )
        )

    assert request_for("explosives") is not None
    assert request_for("crushing-impact") is None


def test_catalog_command_point_cost_frequency_is_consumed_from_stratagem_use_record() -> None:
    source_army, target_army = _mustered_once_per_battle_armies()
    source_unit = source_army.units[0]
    target_unit = target_army.units[0]
    state = _state_with_battlefield(
        armies=(source_army, target_army),
        battlefield=_battlefield_for_units(
            source_army=source_army,
            source_unit=source_unit,
            source_x=10.0,
            target_army=target_army,
            target_unit=target_unit,
            target_x=18.0,
        ),
        active_player_id=target_army.player_id,
        phase=BattlePhase.SHOOTING,
    )
    record = _command_point_record(
        record_id="record:catalog-cp:frequency-consumed",
        raw_text=OPPONENT_STRATAGEM_COST_TEXT,
        source_unit=source_unit,
        trigger_kind=TimingTriggerKind.ANY_PHASE,
    )
    runtime = _command_point_runtime(
        armies=(source_army, target_army),
        records_by_player={source_army.player_id: (record,)},
    )
    modifier_binding = runtime.stratagem_cost_modifier_bindings()[0]
    definition = _test_stratagem_definition(command_point_cost=1)
    eligibility = StratagemEligibilityContext.from_state(
        state=state,
        player_id=target_army.player_id,
        trigger_kind=TimingTriggerKind.START_PHASE,
    )
    target_binding = StratagemTargetBinding(
        target_kind=StratagemTargetKind.FRIENDLY_UNIT,
        target_player_id=target_army.player_id,
        target_unit_instance_id=target_unit.unit_instance_id,
    )
    state.record_stratagem_use(
        StratagemUseRecord(
            use_id="stratagem-use:catalog-cp:frequency-consumed",
            player_id=target_army.player_id,
            stratagem_id=definition.stratagem_id,
            source_id=definition.source_id,
            battle_round=state.battle_round,
            phase=BattlePhaseKind.SHOOTING,
            active_player_id=state.active_player_id,
            timing_window_id=None,
            request_id="request:catalog-cp:frequency-consumed:prior",
            result_id="result:catalog-cp:frequency-consumed:prior",
            selected_option_id="option:catalog-cp:frequency-consumed:prior",
            target_binding=target_binding,
            targeted_unit_instance_ids=(target_unit.unit_instance_id,),
            affected_unit_instance_ids=(target_unit.unit_instance_id,),
            command_point_cost=2,
            command_point_transaction_id=None,
            handler_id="record-only:catalog-cp:frequency-consumed",
            command_point_modifier_ids=(modifier_binding.modifier_id,),
            command_point_modifier_source_ids=(modifier_binding.source_id,),
        )
    )
    source_request, source_result = _test_stratagem_source_decision(
        actor_id=target_army.player_id,
        suffix="frequency-consumed",
    )

    assert (
        runtime.stratagem_cost_choice_request(
            StratagemCostChoiceRequestContext(
                state=state,
                decisions=DecisionController(),
                source_request=source_request,
                source_result=source_result,
                definition=definition,
                eligibility_context=eligibility,
                target_binding=target_binding,
                effect_selection=None,
            )
        )
        is None
    )


def test_catalog_command_point_enhancement_cost_source_binds_only_assigned_bearer() -> None:
    source_army, target_army = _mustered_once_per_battle_armies()
    source_unit = source_army.units[0]
    enhancement_id = "catalog-cp-test-enhancement"
    assigned_source_army = replace(
        source_army,
        detachment_selection=replace(
            source_army.detachment_selection,
            enhancement_ids=(enhancement_id,),
        ),
        enhancement_assignments=(
            EnhancementAssignment(
                enhancement_id=enhancement_id,
                target_unit_selection_id=source_unit.unit_instance_id.removeprefix(
                    f"{source_army.army_id}:"
                ),
                source_id="source:catalog-cp-test-enhancement-assignment",
            ),
        ),
    )
    datasheet_record = _command_point_record(
        record_id="record:catalog-cp:enhancement-cost-runtime",
        raw_text=OPPONENT_STRATAGEM_COST_TEXT,
        source_unit=source_unit,
        trigger_kind=TimingTriggerKind.ANY_PHASE,
    )
    enhancement_record = AbilityCatalogRecord(
        record_id=datasheet_record.record_id,
        definition=replace(datasheet_record.definition, ability_id=enhancement_id),
        source_kind=AbilitySourceKind.ENHANCEMENT,
        detachment_id=source_army.detachment_selection.detachment_ids[0],
    )

    assigned_runtime = _command_point_runtime(
        armies=(assigned_source_army, target_army),
        records_by_player={assigned_source_army.player_id: (enhancement_record,)},
    )
    unassigned_runtime = _command_point_runtime(
        armies=(source_army, target_army),
        records_by_player={source_army.player_id: (enhancement_record,)},
    )

    assert len(assigned_runtime.stratagem_cost_modifier_bindings()) == 1
    assert len(assigned_runtime.stratagem_cost_choice_hook_bindings()) == 1
    assert unassigned_runtime.stratagem_cost_modifier_bindings() == ()
    assert unassigned_runtime.stratagem_cost_choice_hook_bindings() == ()


def test_catalog_command_point_runtime_helpers_fail_fast_on_contract_drift() -> None:
    source_army, target_army = _mustered_once_per_battle_armies()
    source_unit = source_army.units[0]
    destroyed_record = _command_point_record(
        record_id="record:catalog-cp:strict-destroyed",
        raw_text=DESTROYED_CHARACTER_COMMAND_POINT_TEXT,
        source_unit=source_unit,
        trigger_kind=TimingTriggerKind.AFTER_UNIT_DESTROYED,
    )
    phase_record = _command_point_record(
        record_id="record:catalog-cp:strict-phase",
        raw_text=DIRECT_PHASE_COMMAND_POINT_TEXT,
        source_unit=source_unit,
        trigger_kind=TimingTriggerKind.START_PHASE,
    )
    cost_record = _command_point_record(
        record_id="record:catalog-cp:strict-cost",
        raw_text=OPPONENT_STRATAGEM_COST_TEXT,
        source_unit=source_unit,
        trigger_kind=TimingTriggerKind.ANY_PHASE,
    )
    destroyed_clause = catalog_rule_clauses_from_record(destroyed_record)[1]
    phase_clause = catalog_rule_clauses_from_record(phase_record)[0]
    cost_clause = catalog_rule_clauses_from_record(cost_record)[0]

    with pytest.raises(GameLifecycleError, match="ability indexes must be a mapping"):
        command_point_runtime._validate_ability_indexes(())  # pyright: ignore[reportPrivateUsage]
    with pytest.raises(GameLifecycleError, match="must contain ability indexes"):
        command_point_runtime._validate_ability_indexes(  # pyright: ignore[reportPrivateUsage]
            {source_army.player_id: object()}
        )
    with pytest.raises(GameLifecycleError, match="armies must be a tuple"):
        command_point_runtime._validate_armies([])  # pyright: ignore[reportPrivateUsage]
    with pytest.raises(GameLifecycleError, match="must contain ArmyDefinition"):
        command_point_runtime._validate_armies((object(),))  # pyright: ignore[reportPrivateUsage]
    with pytest.raises(GameLifecycleError, match="payload must be an object"):
        command_point_runtime._payload_object(None, label="test")  # pyright: ignore[reportPrivateUsage]
    with pytest.raises(GameLifecycleError, match="missing source_id"):
        command_point_runtime._payload_identifier({}, key="source_id")  # pyright: ignore[reportPrivateUsage]
    with pytest.raises(GameLifecycleError, match="must be a boolean"):
        command_point_runtime._payload_bool({}, key="accepted")  # pyright: ignore[reportPrivateUsage]
    with pytest.raises(GameLifecycleError, match="must be an integer"):
        command_point_runtime._mapping_int({}, key="delta")  # pyright: ignore[reportPrivateUsage]
    with pytest.raises(GameLifecycleError, match="must be positive"):
        command_point_runtime._mapping_positive_int(  # pyright: ignore[reportPrivateUsage]
            {"delta": 0}, key="delta"
        )

    with pytest.raises(GameLifecycleError, match="player army is unknown"):
        command_point_runtime._army_for_player(  # pyright: ignore[reportPrivateUsage]
            (source_army, target_army), player_id="unknown-player"
        )
    with pytest.raises(GameLifecycleError, match="runtime unit is unknown"):
        command_point_runtime._unit_in_army(  # pyright: ignore[reportPrivateUsage]
            source_army, unit_instance_id="unknown-unit"
        )
    with pytest.raises(GameLifecycleError, match="runtime unit is unknown"):
        command_point_runtime._unit_by_id(  # pyright: ignore[reportPrivateUsage]
            (source_army, target_army), "unknown-unit"
        )
    with pytest.raises(GameLifecycleError, match="runtime model is unknown"):
        command_point_runtime._model_in_unit(  # pyright: ignore[reportPrivateUsage]
            source_unit, model_instance_id="unknown-model"
        )
    with pytest.raises(GameLifecycleError, match="missing Leadership"):
        command_point_runtime._model_leadership(  # pyright: ignore[reportPrivateUsage]
            replace(
                source_unit.own_models[0],
                characteristics=tuple(
                    value
                    for value in source_unit.own_models[0].characteristics
                    if value.characteristic is not Characteristic.LEADERSHIP
                ),
            )
        )

    assert not command_point_runtime._destroyed_keywords_match(  # pyright: ignore[reportPrivateUsage]
        destroyed_clause, destroyed_keywords={"MONSTER"}
    )
    without_keyword_clause = replace(
        destroyed_clause,
        conditions=tuple(
            condition
            for condition in destroyed_clause.conditions
            if condition.kind is not RuleConditionKind.KEYWORD_GATE
        ),
    )
    with pytest.raises(GameLifecycleError, match="missing keyword gate"):
        command_point_runtime._destroyed_keywords_match(  # pyright: ignore[reportPrivateUsage]
            without_keyword_clause, destroyed_keywords={"CHARACTER"}
        )

    assert (
        command_point_runtime._phase_gain_trigger_kind(  # pyright: ignore[reportPrivateUsage]
            phase_clause
        )
        is TimingTriggerKind.START_PHASE
    )
    assert (
        command_point_runtime._phase_gain_dice_gate(  # pyright: ignore[reportPrivateUsage]
            phase_clause
        )
        is None
    )
    with pytest.raises(GameLifecycleError, match="trigger edge is malformed"):
        command_point_runtime._phase_gain_trigger_kind(  # pyright: ignore[reportPrivateUsage]
            replace(
                phase_clause,
                trigger=replace(
                    cast(RuleTrigger, phase_clause.trigger),
                    parameters=(
                        RuleParameter("edge", "middle"),
                        RuleParameter("owner", "active_player"),
                        RuleParameter("phase", "command"),
                    ),
                ),
            )
        )
    with pytest.raises(GameLifecycleError, match="missing its trigger"):
        command_point_runtime._required_trigger(  # pyright: ignore[reportPrivateUsage]
            replace(phase_clause, trigger=None)
        )

    frequency = next(
        condition
        for condition in cost_clause.conditions
        if condition.kind is RuleConditionKind.FREQUENCY_LIMIT
    )
    malformed_frequency_clause = replace(
        cost_clause,
        conditions=tuple(
            replace(condition, parameters=(RuleParameter("scope", 1),))
            if condition is frequency
            else condition
            for condition in cost_clause.conditions
        ),
    )
    with pytest.raises(GameLifecycleError, match="frequency scope is malformed"):
        command_point_runtime._cost_frequency_scope(  # pyright: ignore[reportPrivateUsage]
            malformed_frequency_clause
        )
    without_distance_clause = replace(
        cost_clause,
        conditions=tuple(
            condition
            for condition in cost_clause.conditions
            if condition.kind is not RuleConditionKind.DISTANCE_PREDICATE
        ),
    )
    with pytest.raises(GameLifecycleError, match="range is missing"):
        command_point_runtime._cost_source_range_inches(  # pyright: ignore[reportPrivateUsage]
            without_distance_clause
        )

    with pytest.raises(GameLifecycleError, match="indexes must match army player IDs"):
        CatalogCommandPointRuntime(
            ability_indexes_by_player_id={
                source_army.player_id: AbilityCatalogIndex.from_records(())
            },
            armies=(source_army, target_army),
        )
    runtime = _command_point_runtime(
        armies=(source_army, target_army),
        records_by_player={},
    )
    with pytest.raises(GameLifecycleError, match="unit-destroyed runtime requires context"):
        runtime.resolve_unit_destroyed(cast(Any, object()))
    with pytest.raises(GameLifecycleError, match="cost choice requires context"):
        runtime.stratagem_cost_choice_request(cast(Any, object()))
    with pytest.raises(GameLifecycleError, match="cost choice result requires context"):
        runtime.apply_stratagem_cost_choice_result(cast(Any, object()))


@pytest.mark.parametrize(
    (
        "stratagem_id",
        "handler_id",
        "trigger_kind",
        "phase",
        "active_player_id",
        "trigger_payload_kind",
        "has_target_binding",
        "expected_reason",
    ),
    [
        (
            "ingress-move",
            GENERIC_INGRESS_MOVE_HANDLER_ID,
            TimingTriggerKind.START_PHASE,
            BattlePhaseKind.MOVEMENT,
            "player-b",
            "none",
            False,
            "ingress_move_requires_end_phase",
        ),
        (
            "ingress-move",
            GENERIC_INGRESS_MOVE_HANDLER_ID,
            TimingTriggerKind.END_PHASE,
            BattlePhaseKind.SHOOTING,
            "player-b",
            "none",
            False,
            "ingress_move_requires_movement_phase",
        ),
        (
            "ingress-move",
            GENERIC_INGRESS_MOVE_HANDLER_ID,
            TimingTriggerKind.END_PHASE,
            BattlePhaseKind.MOVEMENT,
            "player-b",
            "none",
            False,
            "no_eligible_strategic_reserve_unit",
        ),
        (
            "ingress-move",
            GENERIC_INGRESS_MOVE_HANDLER_ID,
            TimingTriggerKind.END_PHASE,
            BattlePhaseKind.MOVEMENT,
            "player-b",
            "none",
            True,
            None,
        ),
        (
            "force-desperate-escape",
            GENERIC_FORCE_DESPERATE_ESCAPE_HANDLER_ID,
            TimingTriggerKind.START_PHASE,
            BattlePhaseKind.MOVEMENT,
            "player-b",
            "fall-back",
            False,
            "force_desperate_escape_requires_fall_back_selection_trigger",
        ),
        (
            "force-desperate-escape",
            GENERIC_FORCE_DESPERATE_ESCAPE_HANDLER_ID,
            TimingTriggerKind.JUST_AFTER_ENEMY_UNIT_SELECTED_TO_FALL_BACK,
            BattlePhaseKind.SHOOTING,
            "player-b",
            "fall-back",
            False,
            "force_desperate_escape_requires_movement_phase",
        ),
        (
            "force-desperate-escape",
            GENERIC_FORCE_DESPERATE_ESCAPE_HANDLER_ID,
            TimingTriggerKind.JUST_AFTER_ENEMY_UNIT_SELECTED_TO_FALL_BACK,
            BattlePhaseKind.MOVEMENT,
            "player-a",
            "fall-back",
            False,
            "force_desperate_escape_requires_opponent_turn",
        ),
        (
            "force-desperate-escape",
            GENERIC_FORCE_DESPERATE_ESCAPE_HANDLER_ID,
            TimingTriggerKind.JUST_AFTER_ENEMY_UNIT_SELECTED_TO_FALL_BACK,
            BattlePhaseKind.MOVEMENT,
            "player-b",
            "none",
            False,
            "missing_fall_back_unit_context",
        ),
        (
            "force-desperate-escape",
            GENERIC_FORCE_DESPERATE_ESCAPE_HANDLER_ID,
            TimingTriggerKind.JUST_AFTER_ENEMY_UNIT_SELECTED_TO_FALL_BACK,
            BattlePhaseKind.MOVEMENT,
            "player-b",
            "fall-back",
            False,
            "no_eligible_engaged_unit",
        ),
        (
            "force-desperate-escape",
            GENERIC_FORCE_DESPERATE_ESCAPE_HANDLER_ID,
            TimingTriggerKind.JUST_AFTER_ENEMY_UNIT_SELECTED_TO_FALL_BACK,
            BattlePhaseKind.MOVEMENT,
            "player-b",
            "fall-back",
            True,
            None,
        ),
        (
            "fire-overwatch",
            None,
            TimingTriggerKind.START_PHASE,
            BattlePhaseKind.MOVEMENT,
            "player-b",
            "fire-overwatch",
            False,
            "fire_overwatch_requires_end_opponent_movement_phase",
        ),
        (
            "fire-overwatch",
            None,
            TimingTriggerKind.END_PHASE,
            BattlePhaseKind.SHOOTING,
            "player-b",
            "fire-overwatch",
            False,
            "fire_overwatch_requires_movement_phase",
        ),
        (
            "fire-overwatch",
            None,
            TimingTriggerKind.END_PHASE,
            BattlePhaseKind.MOVEMENT,
            "player-b",
            "none",
            False,
            "missing_fire_overwatch_trigger_unit",
        ),
        (
            "heroic-intervention",
            None,
            TimingTriggerKind.START_PHASE,
            BattlePhaseKind.CHARGE,
            "player-b",
            "none",
            False,
            "heroic_intervention_requires_end_charge_phase",
        ),
        (
            "heroic-intervention",
            None,
            TimingTriggerKind.END_PHASE,
            BattlePhaseKind.FIGHT,
            "player-b",
            "none",
            False,
            "heroic_intervention_requires_charge_phase",
        ),
        (
            "heroic-intervention",
            None,
            TimingTriggerKind.END_PHASE,
            BattlePhaseKind.CHARGE,
            "player-a",
            "none",
            False,
            "heroic_intervention_requires_opponent_turn",
        ),
        (
            "counteroffensive",
            None,
            TimingTriggerKind.START_PHASE,
            BattlePhaseKind.FIGHT,
            "player-b",
            "none",
            False,
            "counteroffensive_requires_enemy_fought_trigger",
        ),
        (
            "counteroffensive",
            None,
            TimingTriggerKind.JUST_AFTER_ENEMY_UNIT_HAS_FOUGHT,
            BattlePhaseKind.CHARGE,
            "player-b",
            "none",
            False,
            "counteroffensive_requires_fight_phase",
        ),
        (
            "counteroffensive",
            None,
            TimingTriggerKind.JUST_AFTER_ENEMY_UNIT_HAS_FOUGHT,
            BattlePhaseKind.FIGHT,
            None,
            "none",
            False,
            "counteroffensive_requires_active_player",
        ),
        (
            "crushing-impact",
            None,
            TimingTriggerKind.START_PHASE,
            BattlePhaseKind.CHARGE,
            "player-a",
            "none",
            False,
            "crushing_impact_requires_charge_move_trigger",
        ),
        (
            "crushing-impact",
            None,
            TimingTriggerKind.AFTER_UNIT_ENDS_CHARGE_MOVE,
            BattlePhaseKind.FIGHT,
            "player-a",
            "none",
            False,
            "crushing_impact_requires_charge_phase",
        ),
        (
            "crushing-impact",
            None,
            TimingTriggerKind.AFTER_UNIT_ENDS_CHARGE_MOVE,
            BattlePhaseKind.CHARGE,
            "player-b",
            "none",
            False,
            "crushing_impact_requires_own_charge_phase",
        ),
        (
            "epic-challenge",
            None,
            TimingTriggerKind.START_PHASE,
            BattlePhaseKind.FIGHT,
            "player-a",
            "none",
            False,
            "epic_challenge_requires_selected_to_fight_trigger",
        ),
        (
            "epic-challenge",
            None,
            TimingTriggerKind.JUST_AFTER_FRIENDLY_UNIT_SELECTED_TO_FIGHT,
            BattlePhaseKind.CHARGE,
            "player-a",
            "none",
            False,
            "epic_challenge_requires_fight_phase",
        ),
    ],
)
def test_catalog_stratagem_handler_runtime_rejects_wrong_windows(
    stratagem_id: str,
    handler_id: str | None,
    trigger_kind: TimingTriggerKind,
    phase: BattlePhaseKind,
    active_player_id: str | None,
    trigger_payload_kind: str,
    has_target_binding: bool,
    expected_reason: str | None,
) -> None:
    source_army, target_army = _mustered_core_armies()
    source_unit = source_army.units[0]
    target_unit = target_army.units[0]
    battlefield = _battlefield_for_units(
        source_army=source_army,
        source_unit=source_unit,
        source_x=5.0,
        target_army=target_army,
        target_unit=target_unit,
        target_x=35.0,
    )
    state = _state_with_battlefield(
        armies=(source_army, target_army),
        battlefield=battlefield,
        active_player_id="player-a",
        phase=BattlePhase.MOVEMENT,
    )
    trigger_payload: JsonValue = None
    if trigger_payload_kind == "fall-back":
        trigger_payload = {FALL_BACK_UNIT_CONTEXT_KEY: target_unit.unit_instance_id}
    elif trigger_payload_kind == "fire-overwatch":
        trigger_payload = {FIRE_OVERWATCH_TRIGGER_CONTEXT_KEY: target_unit.unit_instance_id}
    context = _catalog_stratagem_context(
        state=state,
        player_id="player-a",
        trigger_kind=trigger_kind,
        phase=phase,
        active_player_id=active_player_id,
        trigger_payload=trigger_payload,
    )
    if handler_id is None:
        definition = _core_stratagem_definition(stratagem_id)
    else:
        definition = replace(
            _test_stratagem_definition(command_point_cost=1),
            stratagem_id=stratagem_id,
            source_id=f"source:{stratagem_id}",
            handler_id=handler_id,
        )
    target_binding = StratagemTargetBinding.none() if has_target_binding else None

    assert (
        _handler_unavailable_reason(
            state=state,
            definition=definition,
            context=context,
            target_binding=target_binding,
            effect_selection=None,
            ruleset_descriptor=RulesetDescriptor.warhammer_40000_eleventh(),
        )
        == expected_reason
    )


def test_catalog_generic_stratagem_runtime_enforces_source_backed_metadata() -> None:
    source_army, target_army = _mustered_core_armies()
    source_unit = source_army.units[0]
    target_unit = target_army.units[0]

    def state_with_target_x(target_x: float) -> GameState:
        return _state_with_battlefield(
            armies=(source_army, target_army),
            battlefield=_battlefield_for_units(
                source_army=source_army,
                source_unit=source_unit,
                source_x=5.0,
                target_army=target_army,
                target_unit=target_unit,
                target_x=target_x,
            ),
            active_player_id="player-a",
            phase=BattlePhase.SHOOTING,
        )

    far_state = state_with_target_x(35.0)
    close_state = state_with_target_x(12.0)
    source_binding = StratagemTargetBinding(
        target_kind=StratagemTargetKind.FRIENDLY_UNIT,
        target_player_id=source_army.player_id,
        target_unit_instance_id=source_unit.unit_instance_id,
    )

    def reason(
        *,
        metadata: dict[str, JsonValue],
        state: GameState = far_state,
        active_player_id: str | None = "player-a",
        trigger_payload: JsonValue = None,
        target_binding: StratagemTargetBinding | None = source_binding,
        effect_selection: JsonValue = None,
    ) -> str | None:
        return _handler_unavailable_reason(
            state=state,
            definition=_generic_stratagem_definition(metadata=metadata),
            context=_catalog_stratagem_context(
                state=state,
                player_id="player-a",
                trigger_kind=TimingTriggerKind.START_PHASE,
                phase=BattlePhaseKind.SHOOTING,
                active_player_id=active_player_id,
                trigger_payload=trigger_payload,
            ),
            target_binding=target_binding,
            effect_selection=effect_selection,
            ruleset_descriptor=RulesetDescriptor.warhammer_40000_eleventh(),
        )

    assert reason(metadata={"requires_own_turn": True}, active_player_id="player-b") == (
        "stratagem_requires_own_turn"
    )
    assert reason(metadata={"requires_opponent_turn": True}) == ("stratagem_requires_opponent_turn")
    with pytest.raises(GameLifecycleError, match="requires_own_turn must be a bool"):
        reason(metadata={"requires_own_turn": 1})

    far_state.battle_shocked_unit_ids = [source_unit.unit_instance_id]
    assert reason(metadata={"target_forbidden_if_battle_shocked": True}) == (
        "target_battle_shocked"
    )
    far_state.battle_shocked_unit_ids = []
    assert (
        reason(
            metadata={"target_forbidden_if_within_engagement_range": True},
            state=close_state,
        )
        == "target_within_engagement_range"
    )

    target_list_metadata: dict[str, JsonValue] = {
        TARGET_REQUIRED_TRIGGER_CONTEXT_LIST_KEY: "eligible_unit_ids"
    }
    assert reason(metadata=target_list_metadata) == "missing_trigger_payload"
    assert (
        reason(
            metadata=target_list_metadata,
            trigger_payload={"eligible_unit_ids": [target_unit.unit_instance_id]},
        )
        == "target_unit_not_in_trigger_context"
    )
    assert (
        reason(
            metadata=target_list_metadata,
            trigger_payload={"eligible_unit_ids": [source_unit.unit_instance_id]},
        )
        is None
    )
    assert (
        reason(metadata={TARGET_REQUIRED_REINFORCEMENT_ARRIVAL_THIS_TURN_KEY: True})
        == "target_unit_not_arrived_from_reserves_this_turn"
    )
    far_state.battle_shocked_unit_ids = [target_unit.unit_instance_id]
    assert (
        reason(
            metadata={"effect_selection_unit_forbidden_if_battle_shocked": "selected_unit_id"},
            effect_selection={"selected_unit_id": target_unit.unit_instance_id},
        )
        == "target_already_battle_shocked"
    )
    assert (
        reason(
            metadata={"effect_selection_unit_forbidden_if_battle_shocked": "selected_unit_id"},
            effect_selection=None,
        )
        is None
    )


def test_catalog_generic_stratagem_required_trigger_context_is_fail_closed() -> None:
    state = _state_without_battlefield(
        active_player_id="player-a",
        phase=BattlePhase.SHOOTING,
    )

    def reason(*, metadata: dict[str, JsonValue], trigger_payload: JsonValue) -> str | None:
        return _handler_unavailable_reason(
            state=state,
            definition=_generic_stratagem_definition(metadata=metadata),
            context=_catalog_stratagem_context(
                state=state,
                player_id="player-a",
                trigger_kind=TimingTriggerKind.START_PHASE,
                phase=BattlePhaseKind.SHOOTING,
                active_player_id="player-a",
                trigger_payload=trigger_payload,
            ),
            target_binding=None,
            effect_selection=None,
            ruleset_descriptor=RulesetDescriptor.warhammer_40000_eleventh(),
        )

    with pytest.raises(GameLifecycleError, match="required trigger context keys must be a list"):
        reason(
            metadata={REQUIRED_TRIGGER_CONTEXT_KEYS_KEY: "required_key"},
            trigger_payload={},
        )
    assert (
        reason(
            metadata={REQUIRED_TRIGGER_CONTEXT_KEYS_KEY: ["required_key"]},
            trigger_payload=None,
        )
        == "missing_trigger_payload"
    )
    with pytest.raises(GameLifecycleError, match="context key must be a string"):
        reason(
            metadata={REQUIRED_TRIGGER_CONTEXT_KEYS_KEY: [1]},
            trigger_payload={},
        )
    assert (
        reason(
            metadata={REQUIRED_TRIGGER_CONTEXT_KEYS_KEY: ["required_key"]},
            trigger_payload={},
        )
        == "required_key_required"
    )
    empty_trigger_values: tuple[JsonValue, ...] = (None, "", [], {})
    for empty_value in empty_trigger_values:
        assert (
            reason(
                metadata={REQUIRED_TRIGGER_CONTEXT_KEYS_KEY: ["required_key"]},
                trigger_payload={"required_key": empty_value},
            )
            == "required_key_required"
        )
    assert (
        reason(
            metadata={REQUIRED_TRIGGER_CONTEXT_KEYS_KEY: ["required_key"]},
            trigger_payload={"required_key": 0},
        )
        is None
    )

    non_empty_key = "required_non_empty_trigger_context_keys"
    with pytest.raises(GameLifecycleError, match="required trigger context keys must be a list"):
        reason(metadata={non_empty_key: "destroyed_unit_ids"}, trigger_payload={})
    assert (
        reason(
            metadata={non_empty_key: ["destroyed_unit_ids"]},
            trigger_payload=None,
        )
        == "missing_trigger_payload"
    )
    with pytest.raises(GameLifecycleError, match="context key must be a string"):
        reason(metadata={non_empty_key: [1]}, trigger_payload={})
    assert (
        reason(
            metadata={non_empty_key: ["destroyed_enemy_unit_instance_ids"]},
            trigger_payload={},
        )
        == "no_enemy_unit_destroyed"
    )
    assert (
        reason(
            metadata={non_empty_key: ["destroyed_target_unit_instance_ids"]},
            trigger_payload={},
        )
        == "target_models_not_destroyed"
    )
    assert (
        reason(
            metadata={non_empty_key: ["selected_unit_ids"]},
            trigger_payload={},
        )
        == "selected_unit_ids_required"
    )
    with pytest.raises(GameLifecycleError, match="must be a list"):
        reason(
            metadata={non_empty_key: ["selected_unit_ids"]},
            trigger_payload={"selected_unit_ids": "army-alpha"},
        )
    with pytest.raises(GameLifecycleError, match="must not contain duplicates"):
        reason(
            metadata={non_empty_key: ["selected_unit_ids"]},
            trigger_payload={"selected_unit_ids": ["unit-a", "unit-a"]},
        )
    assert (
        reason(
            metadata={non_empty_key: ["selected_unit_ids"]},
            trigger_payload={"selected_unit_ids": ["unit-a"]},
        )
        is None
    )


def test_catalog_generic_visible_enemy_selection_uses_real_battlefield_geometry() -> None:
    source_army, target_army = _mustered_core_armies()
    source_unit = source_army.units[0]
    target_unit = target_army.units[0]

    def make_state(target_x: float, *, with_battlefield: bool = True) -> GameState:
        if not with_battlefield:
            state = _state_without_battlefield(
                active_player_id="player-a",
                phase=BattlePhase.SHOOTING,
            )
            state.army_definitions = [source_army, target_army]
            return state
        return _state_with_battlefield(
            armies=(source_army, target_army),
            battlefield=_battlefield_for_units(
                source_army=source_army,
                source_unit=source_unit,
                source_x=5.0,
                target_army=target_army,
                target_unit=target_unit,
                target_x=target_x,
            ),
            active_player_id="player-a",
            phase=BattlePhase.SHOOTING,
        )

    metadata: dict[str, JsonValue] = {
        EFFECT_SELECTION_KIND_KEY: VISIBLE_ENEMY_UNIT_EFFECT_SELECTION_KIND,
        VISIBLE_ENEMY_SOURCE_UNIT_CONTEXT_KEY: TARGET_BINDING_UNIT_CONTEXT_KEY,
        VISIBLE_ENEMY_RANGE_INCHES_KEY: 12,
    }
    source_binding = StratagemTargetBinding(
        target_kind=StratagemTargetKind.FRIENDLY_UNIT,
        target_player_id=source_army.player_id,
        target_unit_instance_id=source_unit.unit_instance_id,
    )

    def reason(
        *,
        state: GameState,
        target_binding: StratagemTargetBinding | None,
        effect_selection: JsonValue,
        metadata_override: dict[str, JsonValue] | None = None,
    ) -> str | None:
        return _handler_unavailable_reason(
            state=state,
            definition=_generic_stratagem_definition(
                metadata=metadata if metadata_override is None else metadata_override
            ),
            context=_catalog_stratagem_context(
                state=state,
                player_id="player-a",
                trigger_kind=TimingTriggerKind.START_PHASE,
                phase=BattlePhaseKind.SHOOTING,
                active_player_id="player-a",
            ),
            target_binding=target_binding,
            effect_selection=effect_selection,
            ruleset_descriptor=RulesetDescriptor.warhammer_40000_eleventh(),
        )

    close_state = make_state(12.0)
    far_state = make_state(35.0)
    with pytest.raises(GameLifecycleError, match="target binding source metadata"):
        reason(
            state=close_state,
            target_binding=source_binding,
            effect_selection=None,
            metadata_override={
                **metadata,
                VISIBLE_ENEMY_SOURCE_UNIT_CONTEXT_KEY: "wrong_source",
            },
        )
    with pytest.raises(GameLifecycleError, match="positive range metadata"):
        reason(
            state=close_state,
            target_binding=source_binding,
            effect_selection=None,
            metadata_override={**metadata, VISIBLE_ENEMY_RANGE_INCHES_KEY: 0},
        )
    assert (
        reason(
            state=close_state,
            target_binding=None,
            effect_selection=None,
        )
        is None
    )
    assert (
        reason(
            state=close_state,
            target_binding=StratagemTargetBinding.none(),
            effect_selection=None,
        )
        == "target_unit_required"
    )
    enemy_binding = StratagemTargetBinding(
        target_kind=StratagemTargetKind.ANY_UNIT,
        target_player_id=target_army.player_id,
        target_unit_instance_id=target_unit.unit_instance_id,
    )
    assert (
        reason(
            state=close_state,
            target_binding=enemy_binding,
            effect_selection=None,
        )
        == "target_not_friendly"
    )
    assert (
        reason(
            state=make_state(12.0, with_battlefield=False),
            target_binding=source_binding,
            effect_selection=None,
        )
        == "visible_enemy_requires_battlefield"
    )
    assert (
        reason(
            state=close_state,
            target_binding=source_binding,
            effect_selection=None,
        )
        == "visible_enemy_unit_required"
    )
    assert (
        reason(
            state=far_state,
            target_binding=source_binding,
            effect_selection=None,
        )
        == "no_visible_enemy_unit"
    )

    def selection(unit_instance_id: str) -> JsonValue:
        return {
            EFFECT_SELECTION_KIND_KEY: VISIBLE_ENEMY_UNIT_EFFECT_SELECTION_KIND,
            VISIBLE_ENEMY_UNIT_CONTEXT_KEY: unit_instance_id,
        }

    assert (
        reason(
            state=close_state,
            target_binding=source_binding,
            effect_selection=selection("unknown-unit"),
        )
        == "unknown_visible_enemy_unit"
    )
    assert (
        reason(
            state=close_state,
            target_binding=source_binding,
            effect_selection=selection(source_unit.unit_instance_id),
        )
        == "visible_enemy_unit_not_enemy"
    )
    assert (
        reason(
            state=far_state,
            target_binding=source_binding,
            effect_selection=selection(target_unit.unit_instance_id),
        )
        == "visible_enemy_unit_not_visible_and_within_range"
    )
    assert (
        reason(
            state=close_state,
            target_binding=source_binding,
            effect_selection=selection(target_unit.unit_instance_id),
        )
        is None
    )


def test_catalog_advance_and_fall_back_runtime_exposes_all_source_backed_permissions() -> None:
    source_army, target_army = _mustered_core_armies()
    source_unit = source_army.units[0]
    target_unit = target_army.units[0]
    state = _state_with_battlefield(
        armies=(source_army, target_army),
        battlefield=_battlefield_for_units(
            source_army=source_army,
            source_unit=source_unit,
            source_x=5.0,
            target_army=target_army,
            target_unit=target_unit,
            target_x=35.0,
        ),
        active_player_id=source_army.player_id,
        phase=BattlePhase.MOVEMENT,
    )
    clause = RuleClause(
        clause_id="test:catalog-movement-permissions:clause",
        source_span=_span(),
        target=RuleTargetSpec(kind=RuleTargetKind.THIS_UNIT, source_span=_span()),
        effects=tuple(
            _effect(RuleEffectKind.GRANT_ABILITY, ("ability", ability))
            for ability in (
                "can_advance_and_charge",
                "can_advance_and_shoot_and_charge",
                "can_fall_back_and_charge",
                "can_fall_back_and_shoot",
            )
        ),
    )
    record = _ability_record(
        record_id="record:catalog-movement-permissions",
        rule_ir=_rule_ir(
            source_id="test:catalog-movement-permissions",
            clauses=(clause,),
        ),
        trigger_kind=TimingTriggerKind.PASSIVE_QUERY,
    )
    indexes = {
        source_army.player_id: AbilityCatalogIndex.from_records((record,)),
        target_army.player_id: AbilityCatalogIndex.from_records(()),
    }
    advance_runtime = CatalogAdvanceEligibilityRuntime(
        ability_indexes_by_player_id=indexes,
        armies=(source_army, target_army),
    )
    fall_back_runtime = CatalogFallBackEligibilityRuntime(
        ability_indexes_by_player_id=indexes,
        armies=(source_army, target_army),
    )
    advance_context = AdvanceEligibilityContext(
        state=state,
        player_id=source_army.player_id,
        battle_round=state.battle_round,
        unit_instance_id=source_unit.unit_instance_id,
        movement_request_id="request:catalog-advance-permissions",
        movement_result_id="result:catalog-advance-permissions",
    )
    fall_back_context = FallBackEligibilityContext(
        state=state,
        player_id=source_army.player_id,
        battle_round=state.battle_round,
        unit_instance_id=source_unit.unit_instance_id,
        movement_request_id="request:catalog-fall-back-permissions",
        movement_result_id="result:catalog-fall-back-permissions",
    )

    advance_grants = (
        advance_runtime.advance_and_charge_handler(advance_context),
        advance_runtime.advance_shoot_and_charge_handler(advance_context),
    )
    fall_back_grants = (
        fall_back_runtime.fall_back_and_charge_handler(fall_back_context),
        fall_back_runtime.fall_back_and_shoot_handler(fall_back_context),
    )

    assert len(advance_runtime.bindings()) == 2
    assert len(fall_back_runtime.bindings()) == 2
    assert tuple(
        (grant.can_shoot, grant.can_declare_charge) for grant in advance_grants if grant
    ) == (
        (False, True),
        (True, True),
    )
    assert tuple(
        (grant.can_shoot, grant.can_declare_charge) for grant in fall_back_grants if grant
    ) == (
        (False, True),
        (True, False),
    )
    assert (
        advance_runtime.advance_and_charge_handler(
            replace(
                advance_context,
                player_id=target_army.player_id,
                unit_instance_id=target_unit.unit_instance_id,
            )
        )
        is None
    )
    assert (
        fall_back_runtime.fall_back_and_charge_handler(
            replace(
                fall_back_context,
                player_id=target_army.player_id,
                unit_instance_id=target_unit.unit_instance_id,
            )
        )
        is None
    )
    with pytest.raises(GameLifecycleError, match="advance eligibility requires context"):
        advance_runtime.advance_and_charge_handler(cast(AdvanceEligibilityContext, object()))
    with pytest.raises(GameLifecycleError, match="Fall Back eligibility requires context"):
        fall_back_runtime.fall_back_and_charge_handler(cast(FallBackEligibilityContext, object()))
    with pytest.raises(GameLifecycleError, match="missing player ability index"):
        CatalogAdvanceEligibilityRuntime(
            ability_indexes_by_player_id={source_army.player_id: indexes[source_army.player_id]},
            armies=(source_army, target_army),
        )
    with pytest.raises(GameLifecycleError, match="missing player ability index"):
        CatalogFallBackEligibilityRuntime(
            ability_indexes_by_player_id={source_army.player_id: indexes[source_army.player_id]},
            armies=(source_army, target_army),
        )


def test_catalog_this_model_advance_eligibility_rejects_multi_model_bearer_widening() -> None:
    source_army, target_army = _mustered_attached_once_per_battle_armies()
    source_unit = next(
        unit for unit in source_army.units if unit.datasheet_id == "core-character-leader"
    )
    wargear_id = "test:catalog-advance-eligibility:bearer-wargear"
    source_unit = replace(
        source_unit,
        own_models=(
            replace(
                source_unit.own_models[0],
                wargear_ids=tuple(sorted((*source_unit.own_models[0].wargear_ids, wargear_id))),
            ),
            *source_unit.own_models[1:],
        ),
    )
    source_army = replace(
        source_army,
        units=tuple(
            source_unit if unit.unit_instance_id == source_unit.unit_instance_id else unit
            for unit in source_army.units
        ),
    )
    state = _state_with_battlefield(
        armies=(source_army, target_army),
        battlefield=create_deterministic_battlefield_scenario(
            battlefield_id="catalog-this-model-advance-eligibility-attached",
            armies=(source_army, target_army),
        ).battlefield_state,
        active_player_id=source_army.player_id,
        phase=BattlePhase.MOVEMENT,
    )
    clause = RuleClause(
        clause_id="test:catalog-this-model-advance-eligibility:clause",
        source_span=_span(),
        target=RuleTargetSpec(kind=RuleTargetKind.THIS_MODEL, source_span=_span()),
        effects=(
            _effect(
                RuleEffectKind.GRANT_ABILITY,
                ("ability", "can_advance_and_charge"),
                ("target_scope", "this_model"),
            ),
        ),
        duration=RuleDuration(
            kind=RuleDurationKind.PERMANENT,
            source_span=_span(),
        ),
    )
    record = _ability_record(
        record_id="record:catalog-this-model-advance-eligibility",
        rule_ir=_rule_ir(
            source_id="test:catalog-this-model-advance-eligibility",
            clauses=(clause,),
        ),
        trigger_kind=TimingTriggerKind.PASSIVE_QUERY,
        datasheet_id=source_unit.datasheet_id,
        source_kind=AbilitySourceKind.WARGEAR,
        wargear_id=wargear_id,
    )
    runtime = CatalogAdvanceEligibilityRuntime(
        ability_indexes_by_player_id={
            source_army.player_id: AbilityCatalogIndex.from_records((record,)),
            target_army.player_id: AbilityCatalogIndex.from_records(()),
        },
        armies=(source_army, target_army),
    )
    context = AdvanceEligibilityContext(
        state=state,
        player_id=source_army.player_id,
        battle_round=state.battle_round,
        unit_instance_id=source_unit.unit_instance_id,
        movement_request_id="request:catalog-this-model-advance-eligibility",
        movement_result_id="result:catalog-this-model-advance-eligibility",
    )

    with pytest.raises(
        GameLifecycleError,
        match="this-model advance eligibility requires a singleton alive rules unit",
    ):
        runtime.advance_and_charge_handler(context)


def test_catalog_static_attack_modifier_classifier_is_fail_closed() -> None:
    supported_condition = _condition(
        RuleConditionKind.TARGET_CONSTRAINT,
        ("gate_subject", "source_unit"),
        ("relationship", "this_model_makes_attack"),
        ("target_constraint", "source_unit_below_starting_strength"),
    )

    def clause_for(
        *,
        trigger_roll_type: str,
        effect_roll_type: str,
        conditions: tuple[RuleCondition, ...] = (supported_condition,),
        delta: RuleParameterValue = 1,
        weapon_scope: str | None = None,
    ) -> RuleClause:
        effect_parameters: tuple[tuple[str, RuleParameterValue], ...] = (
            ("delta", delta),
            ("roll_type", effect_roll_type),
        )
        if weapon_scope is not None:
            effect_parameters = (*effect_parameters, ("weapon_scope", weapon_scope))
        return RuleClause(
            clause_id=f"test:static-attack-modifier:{trigger_roll_type}:{effect_roll_type}",
            source_span=_span(),
            trigger=RuleTrigger(
                kind=RuleTriggerKind.DICE_ROLL,
                source_span=_span(),
                parameters=_parameters(("roll_type", trigger_roll_type)),
            ),
            conditions=conditions,
            target=RuleTargetSpec(kind=RuleTargetKind.THIS_MODEL, source_span=_span()),
            effects=(
                _effect(
                    RuleEffectKind.MODIFY_DICE_ROLL,
                    *effect_parameters,
                ),
            ),
        )

    for roll_type in ("hit", "wound"):
        clause = clause_for(trigger_roll_type=roll_type, effect_roll_type=roll_type)
        assert clause_effect_is_supported_this_model_attack_roll_modifier(
            clause,
            clause.effects[0],
        )
        compiler_authored = replace(
            clause,
            trigger=replace(
                cast(RuleTrigger, clause.trigger),
                parameters=_parameters(
                    ("actor", "this_model"),
                    ("roll_type", roll_type),
                    ("target_allegiance", "enemy"),
                    ("timing_window", f"attack_sequence.{roll_type}"),
                ),
            ),
        )
        assert clause_effect_is_supported_this_model_attack_roll_modifier(
            compiler_authored,
            compiler_authored.effects[0],
        )

    for target_constraint in (
        "target_unit_below_starting_strength",
        "target_unit_below_half_strength",
    ):
        condition = _condition(
            RuleConditionKind.TARGET_CONSTRAINT,
            ("gate_subject", "attack_target"),
            ("relationship", "this_model_makes_attack"),
            ("target_allegiance", "enemy"),
            ("target_constraint", target_constraint),
        )
        clause = clause_for(
            trigger_roll_type="hit",
            effect_roll_type="hit",
            conditions=(condition,),
            weapon_scope="melee",
        )
        assert clause_effect_is_supported_this_model_attack_roll_modifier(
            clause,
            clause.effects[0],
        )

    supported = clause_for(trigger_roll_type="hit", effect_roll_type="hit")
    unsupported_shapes = (
        replace(
            supported,
            duration=RuleDuration(
                kind=RuleDurationKind.WHILE_CONDITION_TRUE,
                source_span=_span(),
            ),
        ),
        replace(
            supported,
            target=replace(
                cast(RuleTargetSpec, supported.target),
                parameters=_parameters(("attack_role", "attacker")),
            ),
        ),
        replace(
            supported,
            trigger=replace(
                cast(RuleTrigger, supported.trigger),
                parameters=_parameters(
                    ("roll_type", "hit"),
                    ("timing_window", "attack_roll"),
                ),
            ),
        ),
        replace(
            supported,
            effects=(supported.effects[0], supported.effects[0]),
        ),
        replace(
            supported,
            effects=(
                replace(
                    supported.effects[0],
                    parameters=(
                        *supported.effects[0].parameters,
                        *_parameters(("scope", "attack")),
                    ),
                ),
            ),
        ),
    )
    for clause in unsupported_shapes:
        assert not clause_effect_is_supported_this_model_attack_roll_modifier(
            clause,
            clause.effects[0],
        )

    for unsupported_roll_type in (
        "attack_sequence.hit",
        "attack_sequence.wound",
        "hit_roll",
        "wound_roll",
        "charge",
    ):
        clause = clause_for(
            trigger_roll_type=unsupported_roll_type,
            effect_roll_type=unsupported_roll_type,
        )
        assert not clause_effect_is_supported_this_model_attack_roll_modifier(
            clause,
            clause.effects[0],
        )

    mismatched = clause_for(trigger_roll_type="hit", effect_roll_type="wound")
    assert not clause_effect_is_supported_this_model_attack_roll_modifier(
        mismatched,
        mismatched.effects[0],
    )
    invalid_delta = clause_for(
        trigger_roll_type="hit",
        effect_roll_type="hit",
        delta="1",
    )
    assert not clause_effect_is_supported_this_model_attack_roll_modifier(
        invalid_delta,
        invalid_delta.effects[0],
    )
    unsupported_condition = _condition(
        RuleConditionKind.TARGET_CONSTRAINT,
        ("gate_subject", "source_unit"),
        ("relationship", "this_model_makes_attack"),
        ("target_constraint", "source_unit_unknown_state"),
    )
    for conditions in (
        (),
        (unsupported_condition,),
        (supported_condition, unsupported_condition),
    ):
        clause = clause_for(
            trigger_roll_type="hit",
            effect_roll_type="hit",
            conditions=conditions,
        )
        assert not clause_effect_is_supported_this_model_attack_roll_modifier(
            clause,
            clause.effects[0],
        )


def test_catalog_modifier_ignore_permission_classifier_and_query_are_fail_closed() -> None:
    source_army, _target_army = _mustered_core_armies()
    source_unit = source_army.units[0]
    clause = _modifier_ignore_permission_clause(
        clause_id="test:modifier-ignore:valid",
        modifier_kinds=(
            ModifierIgnoreKind.MOVEMENT_CHARACTERISTIC.value,
            ModifierIgnoreKind.ADVANCE_ROLL.value,
            ModifierIgnoreKind.CHARGE_ROLL.value,
        ),
    )
    rule_ir = _rule_ir(source_id="test:modifier-ignore", clauses=(clause,))
    record = _ability_record(
        record_id="record:test:modifier-ignore",
        rule_ir=rule_ir,
        trigger_kind=TimingTriggerKind.PASSIVE_QUERY,
        datasheet_id=source_unit.datasheet_id,
    )

    assert clause_is_modifier_ignore_permission(clause)
    assert catalog_rule_ir_consumers_for_rule(rule_ir) == (
        CATALOG_IR_MODIFIER_IGNORE_PERMISSION_CONSUMER_ID,
    )
    assert catalog_rule_ir_hook_ids_for_rule(rule_ir) == (
        CATALOG_IR_MODIFIER_IGNORE_PERMISSION_CONSUMER_ID,
    )
    permissions = catalog_modifier_ignore_permissions_for_unit(
        ability_index=AbilityCatalogIndex.from_records((record,)),
        unit=source_unit,
        current_model_instance_ids=source_unit.own_model_ids(),
    )
    assert tuple(permission.to_payload() for permission in permissions) == (
        {
            "permission_id": ("test:modifier-ignore:test:modifier-ignore:valid:modifier-ignore"),
            "record_id": record.record_id,
            "source_id": rule_ir.source_id,
            "rule_ir_hash": rule_ir.ir_hash(),
            "clause_id": clause.clause_id,
            "modifier_kinds": [
                ModifierIgnoreKind.ADVANCE_ROLL.value,
                ModifierIgnoreKind.CHARGE_ROLL.value,
                ModifierIgnoreKind.MOVEMENT_CHARACTERISTIC.value,
            ],
        },
    )

    base_effect = clause.effects[0]
    base_duration = clause.duration
    assert base_duration is not None
    unsupported_shapes = (
        replace(
            clause,
            trigger=RuleTrigger(
                kind=RuleTriggerKind.DICE_ROLL,
                source_span=_span(),
                parameters=_parameters(("roll_type", "advance")),
            ),
        ),
        replace(
            clause,
            conditions=(
                _condition(
                    RuleConditionKind.TARGET_CONSTRAINT,
                    ("target_constraint", "source_unit_is_visible"),
                ),
            ),
        ),
        replace(
            clause,
            target=RuleTargetSpec(kind=RuleTargetKind.THIS_UNIT, source_span=_span()),
        ),
        replace(clause, duration=replace(base_duration, kind=RuleDurationKind.IMMEDIATE)),
        replace(
            clause,
            effects=(
                replace(
                    base_effect,
                    parameters=_parameters(
                        ("ability", "modifier_ignore_permission"),
                        (
                            "modifier_kinds",
                            (ModifierIgnoreKind.MOVEMENT_CHARACTERISTIC.value,),
                        ),
                        ("selection", "all"),
                    ),
                ),
            ),
        ),
        replace(
            clause,
            effects=(
                replace(
                    base_effect,
                    parameters=_parameters(
                        ("ability", "modifier_ignore_permission"),
                        (
                            "modifier_kinds",
                            (
                                ModifierIgnoreKind.MOVEMENT_CHARACTERISTIC.value,
                                ModifierIgnoreKind.MOVEMENT_CHARACTERISTIC.value,
                            ),
                        ),
                        ("selection", "any_or_all"),
                    ),
                ),
            ),
        ),
        replace(
            clause,
            effects=(
                replace(
                    base_effect,
                    parameters=_parameters(
                        ("ability", "modifier_ignore_permission"),
                        ("modifier_kinds", ("hit_roll",)),
                        ("selection", "any_or_all"),
                    ),
                ),
            ),
        ),
    )
    assert all(not clause_is_modifier_ignore_permission(item) for item in unsupported_shapes)

    disabled_record = replace(record, disabled=True)
    assert (
        catalog_modifier_ignore_permissions_for_unit(
            ability_index=AbilityCatalogIndex.from_records((disabled_record,)),
            unit=source_unit,
            current_model_instance_ids=source_unit.own_model_ids(),
        )
        == ()
    )


def test_modifier_ignore_options_effect_and_records_round_trip_deterministically() -> None:
    source_army, _target_army = _mustered_core_armies()
    source_unit = source_army.units[0]
    unit_id = source_unit.unit_instance_id
    model_id = source_unit.own_models[0].model_instance_id
    permission = CatalogModifierIgnorePermission(
        permission_id="test:modifier-ignore:permission",
        record_id="test:modifier-ignore:record",
        source_id="test:modifier-ignore:source",
        rule_ir_hash="test:modifier-ignore:rule-ir-hash",
        clause_id="test:modifier-ignore:clause",
        modifier_kinds=(
            ModifierIgnoreKind.CHARGE_ROLL,
            ModifierIgnoreKind.MOVEMENT_CHARACTERISTIC,
            ModifierIgnoreKind.ADVANCE_ROLL,
        ),
    )
    snapshots = (
        ModifierIgnoreSnapshot(
            kind=ModifierIgnoreKind.CHARGE_ROLL,
            modifier_id="test:modifier-ignore:charge",
            source_id="test:modifier-ignore:charge-source",
        ),
        ModifierIgnoreSnapshot(
            kind=ModifierIgnoreKind.MOVEMENT_CHARACTERISTIC,
            modifier_id="test:modifier-ignore:movement",
            source_id="test:modifier-ignore:movement-source",
            model_instance_id=model_id,
        ),
        ModifierIgnoreSnapshot(
            kind=ModifierIgnoreKind.ADVANCE_ROLL,
            modifier_id="test:modifier-ignore:advance",
            source_id="test:modifier-ignore:advance-source",
        ),
    )
    base_option = DecisionOption(
        option_id="advance",
        label="Advance",
        payload={"unit_instance_id": unit_id},
    )

    options = options_with_modifier_ignore_choices(
        option=base_option,
        unit_instance_id=unit_id,
        permissions=(permission,),
        available_modifiers=tuple(reversed(snapshots)),
    )
    repeated = options_with_modifier_ignore_choices(
        option=base_option,
        unit_instance_id=unit_id,
        permissions=(permission,),
        available_modifiers=snapshots,
    )
    assert options == repeated
    assert len(options) == 8
    assert len({option.option_id for option in options}) == 8
    assert options[0].option_id == base_option.option_id
    assert all(option.option_id.startswith("advance:ignore:") for option in options[1:])

    request = DecisionRequest(
        request_id="test:modifier-ignore:request",
        decision_type="select_movement_action",
        actor_id=source_army.player_id,
        payload={"unit_instance_id": unit_id},
        options=options,
    )
    request_payload = json.loads(json.dumps(request.to_payload(), sort_keys=True))
    restored_request = DecisionRequest.from_payload(request_payload)
    assert restored_request == request
    selected_option = options[-1]
    assert isinstance(selected_option.payload, dict)
    selected_context = cast(
        dict[str, object],
        selected_option.payload["modifier_ignore_context"],
    )
    assert len(cast(list[object], selected_context["ignored_modifiers"])) == 3
    result = DecisionResult.for_request(
        result_id="test:modifier-ignore:result",
        request=request,
        selected_option_id=selected_option.option_id,
    )
    decisions = DecisionController()
    decisions.request_decision(request)
    decisions.submit_result(result)
    state = _state_without_battlefield(
        active_player_id=source_army.player_id,
        phase=BattlePhase.MOVEMENT,
    )
    state.record_army_definition(source_army)
    effect = record_modifier_ignore_selection(
        state=state,
        result=result,
        unit_instance_id=unit_id,
        phase=BattlePhaseKind.MOVEMENT,
    )
    assert effect is not None
    assert ignored_modifier_ids_for_context(
        state=state,
        unit_instance_id=unit_id,
        kind=ModifierIgnoreKind.MOVEMENT_CHARACTERISTIC,
        model_instance_id=model_id,
    ) == ("test:modifier-ignore:movement",)
    assert ignored_modifier_ids_for_context(
        state=state,
        unit_instance_id=unit_id,
        kind=ModifierIgnoreKind.ADVANCE_ROLL,
    ) == ("test:modifier-ignore:advance",)
    assert ignored_modifier_ids_for_context(
        state=state,
        unit_instance_id=unit_id,
        kind=ModifierIgnoreKind.CHARGE_ROLL,
    ) == ("test:modifier-ignore:charge",)

    controller_payload = json.loads(json.dumps(decisions.to_payload(), sort_keys=True))
    state_payload = json.loads(json.dumps(state.to_payload(), sort_keys=True))
    assert DecisionController.from_payload(controller_payload).to_payload() == controller_payload
    restored_state = GameState.from_payload(state_payload)
    assert restored_state.to_payload() == state_payload
    assert ignored_modifier_ids_for_context(
        state=restored_state,
        unit_instance_id=unit_id,
        kind=ModifierIgnoreKind.CHARGE_ROLL,
    ) == ("test:modifier-ignore:charge",)
    assert "object at 0x" not in json.dumps(
        {"decision": controller_payload, "state": state_payload}, sort_keys=True
    )


def test_modifier_ignore_context_rejects_duplicate_and_unpermitted_replay_shapes() -> None:
    source_army, _target_army = _mustered_core_armies()
    source_unit = source_army.units[0]
    unit_id = source_unit.unit_instance_id
    permission = CatalogModifierIgnorePermission(
        permission_id="test:modifier-ignore:invalid-permission",
        record_id="test:modifier-ignore:invalid-record",
        source_id="test:modifier-ignore:invalid-source",
        rule_ir_hash="test:modifier-ignore:invalid-hash",
        clause_id="test:modifier-ignore:invalid-clause",
        modifier_kinds=(ModifierIgnoreKind.ADVANCE_ROLL,),
    )
    advance_snapshot = ModifierIgnoreSnapshot(
        kind=ModifierIgnoreKind.ADVANCE_ROLL,
        modifier_id="test:modifier-ignore:invalid-advance",
        source_id="test:modifier-ignore:invalid-advance-source",
    )
    base_option = DecisionOption(
        option_id="advance",
        label="Advance",
        payload={"unit_instance_id": unit_id},
    )
    with pytest.raises(GameLifecycleError, match="snapshot identities must be unique"):
        options_with_modifier_ignore_choices(
            option=base_option,
            unit_instance_id=unit_id,
            permissions=(permission,),
            available_modifiers=(advance_snapshot, advance_snapshot),
        )

    option = options_with_modifier_ignore_choices(
        option=base_option,
        unit_instance_id=unit_id,
        permissions=(permission,),
        available_modifiers=(advance_snapshot,),
    )[1]
    assert isinstance(option.payload, dict)
    valid_payload = cast(dict[str, object], option.payload)
    valid_context = cast(dict[str, object], valid_payload["modifier_ignore_context"])
    request = DecisionRequest(
        request_id="test:modifier-ignore:invalid-request",
        decision_type="select_movement_action",
        actor_id="player-a",
        payload={},
        options=(option,),
    )
    valid_result = DecisionResult.for_request(
        result_id="test:modifier-ignore:invalid-result",
        request=request,
        selected_option_id=option.option_id,
    )

    for expected_message, context in (
        (
            "permission IDs are duplicated",
            {
                **valid_context,
                "permissions": [
                    *cast(list[object], valid_context["permissions"]),
                    *cast(list[object], valid_context["permissions"]),
                ],
            },
        ),
        (
            "available modifier kind is not permitted",
            {
                **valid_context,
                "available_modifiers": [
                    ModifierIgnoreSnapshot(
                        kind=ModifierIgnoreKind.CHARGE_ROLL,
                        modifier_id="test:modifier-ignore:unpermitted-charge",
                        source_id="test:modifier-ignore:unpermitted-charge-source",
                    ).to_payload()
                ],
                "ignored_modifiers": [
                    ModifierIgnoreSnapshot(
                        kind=ModifierIgnoreKind.CHARGE_ROLL,
                        modifier_id="test:modifier-ignore:unpermitted-charge",
                        source_id="test:modifier-ignore:unpermitted-charge-source",
                    ).to_payload()
                ],
            },
        ),
        (
            "ignored modifiers are duplicated",
            {
                **valid_context,
                "ignored_modifiers": [
                    *cast(list[object], valid_context["ignored_modifiers"]),
                    *cast(list[object], valid_context["ignored_modifiers"]),
                ],
            },
        ),
    ):
        forged = replace(
            valid_result,
            payload=validate_json_value({**valid_payload, "modifier_ignore_context": context}),
        )
        state = _state_without_battlefield(
            active_player_id="player-a",
            phase=BattlePhase.MOVEMENT,
        )
        with pytest.raises(GameLifecycleError, match=expected_message):
            record_modifier_ignore_selection(
                state=state,
                result=forged,
                unit_instance_id=unit_id,
                phase=BattlePhaseKind.MOVEMENT,
            )
        assert state.persisting_effects == []

    valid_state = _state_without_battlefield(
        active_player_id=source_army.player_id,
        phase=BattlePhase.MOVEMENT,
    )
    valid_state.record_army_definition(source_army)
    valid_effect = record_modifier_ignore_selection(
        state=valid_state,
        result=valid_result,
        unit_instance_id=unit_id,
        phase=BattlePhaseKind.MOVEMENT,
    )
    assert valid_effect is not None
    assert isinstance(valid_effect.effect_payload, dict)
    replay_effect_payload = cast(dict[str, object], valid_effect.effect_payload)
    replay_context = cast(
        dict[str, object],
        replay_effect_payload["modifier_ignore_context"],
    )
    replay_permissions = cast(list[object], replay_context["permissions"])
    malformed_replay_effect = replace(
        valid_effect,
        effect_id="test:modifier-ignore:malformed-replay-effect",
        effect_payload=validate_json_value(
            {
                **replay_effect_payload,
                "modifier_ignore_context": {
                    **replay_context,
                    "permissions": [*replay_permissions, *replay_permissions],
                },
            }
        ),
    )
    replay_state = _state_without_battlefield(
        active_player_id=source_army.player_id,
        phase=BattlePhase.MOVEMENT,
    )
    replay_state.record_army_definition(source_army)
    replay_state.record_persisting_effect(malformed_replay_effect)
    with pytest.raises(GameLifecycleError, match="permission IDs are duplicated"):
        ignored_modifier_ids_for_context(
            state=replay_state,
            unit_instance_id=unit_id,
            kind=ModifierIgnoreKind.ADVANCE_ROLL,
        )


def test_catalog_charge_roll_modifier_classifier_is_fail_closed() -> None:
    below_starting = _charge_strength_modifier_clause(
        clause_id="test:charge-strength:below-starting",
        target_constraint="target_unit_below_starting_strength",
        delta=1,
        modifier_priority=1,
    )
    below_half = _charge_strength_modifier_clause(
        clause_id="test:charge-strength:below-half",
        target_constraint="target_unit_below_half_strength",
        delta=2,
        modifier_priority=2,
    )
    unconditional = RuleClause(
        clause_id="test:charge-strength:unconditional",
        source_span=_span(),
        target=RuleTargetSpec(kind=RuleTargetKind.THIS_UNIT, source_span=_span()),
        effects=(
            _effect(
                RuleEffectKind.MODIFY_DICE_ROLL,
                ("delta", 1),
                ("roll_type", "charge"),
            ),
        ),
    )

    for clause in (unconditional, below_starting, below_half):
        assert clause_effect_is_supported_charge_roll_modifier(
            clause,
            clause.effects[0],
        )

    rule_ir = _rule_ir(
        source_id="test:charge-strength",
        clauses=(below_half, below_starting),
    )
    assert catalog_rule_ir_consumers_for_rule(rule_ir) == (CATALOG_IR_CHARGE_ROLL_CONSUMER_ID,)
    assert catalog_rule_ir_hook_ids_for_rule(rule_ir) == (CATALOG_IR_CHARGE_ROLL_CONSUMER_ID,)

    base_condition = below_starting.conditions[0]
    base_effect = below_starting.effects[0]
    unsupported_shapes = (
        # Target-keyword charge gates require declared-target semantics. Treating
        # this shape as unconditional would over-apply rules such as Sigismund's Heir.
        replace(
            unconditional,
            target=RuleTargetSpec(
                kind=RuleTargetKind.THIS_UNIT,
                source_span=_span(),
                parameters=_parameters(("scope", "this_models_unit")),
            ),
            conditions=(
                _condition(
                    RuleConditionKind.KEYWORD_GATE,
                    ("required_keyword", "CHARACTER"),
                ),
            ),
        ),
        replace(
            below_starting,
            conditions=(
                replace(
                    base_condition,
                    parameters=_parameters(
                        ("distance_inches", 0),
                        ("gate_subject", "nearby_unit"),
                        ("relationship", "any_unit_within_distance_of_this_unit"),
                        ("target_allegiance", "enemy"),
                        ("target_constraint", "target_unit_below_starting_strength"),
                    ),
                ),
            ),
        ),
        replace(
            below_starting,
            conditions=(
                replace(
                    base_condition,
                    parameters=_parameters(
                        ("distance_inches", 9.0),
                        ("gate_subject", "nearby_unit"),
                        ("relationship", "any_unit_within_distance_of_this_unit"),
                        ("target_allegiance", "friendly"),
                        ("target_constraint", "target_unit_below_starting_strength"),
                    ),
                ),
            ),
        ),
        replace(below_starting, conditions=(base_condition, base_condition)),
        replace(
            below_starting,
            effects=(
                replace(
                    base_effect,
                    parameters=_parameters(
                        ("delta", 1),
                        ("modifier_priority", 1),
                        ("roll_type", "charge"),
                    ),
                ),
            ),
        ),
        replace(
            below_starting,
            effects=(
                replace(
                    base_effect,
                    parameters=_parameters(
                        ("delta", 1),
                        ("modifier_exclusive_group", "nearby-enemy-strength"),
                        ("modifier_priority", 0),
                        ("roll_type", "charge"),
                    ),
                ),
            ),
        ),
        replace(
            below_starting,
            target=RuleTargetSpec(
                kind=RuleTargetKind.THIS_UNIT,
                source_span=_span(),
                parameters=_parameters(("scope", "models")),
            ),
        ),
    )
    for clause in unsupported_shapes:
        assert not clause_effect_is_supported_charge_roll_modifier(
            clause,
            clause.effects[0],
        )


def test_catalog_charge_roll_modifiers_use_nearby_enemy_strength_priority() -> None:
    source_army, target_army = _mustered_once_per_battle_armies()
    source_unit = source_army.units[0]
    target_unit = target_army.units[0]
    source_x = 10.0
    probe_target_x = 30.0
    state = _state_without_battlefield(
        active_player_id=source_army.player_id,
        phase=BattlePhase.CHARGE,
    )
    state.record_army_definition(source_army)
    state.record_army_definition(target_army)
    state.battlefield_state = _battlefield_for_units(
        source_army=source_army,
        source_unit=source_unit,
        source_x=source_x,
        target_army=target_army,
        target_unit=target_unit,
        target_x=probe_target_x,
    )

    def closest_distance_inches() -> float:
        source_models = geometry_models_for_rules_unit(
            state=state,
            unit_instance_id=source_unit.unit_instance_id,
        )
        target_models = geometry_models_for_rules_unit(
            state=state,
            unit_instance_id=target_unit.unit_instance_id,
        )
        return min(
            DistanceMeasurementContext.from_models(source, target).closest_distance_inches()
            for source in source_models
            for target in target_models
        )

    target_x = probe_target_x - (closest_distance_inches() - 9.0)
    state.battlefield_state = _battlefield_for_units(
        source_army=source_army,
        source_unit=source_unit,
        source_x=source_x,
        target_army=target_army,
        target_unit=target_unit,
        target_x=target_x,
    )
    assert math.isclose(closest_distance_inches(), 9.0, abs_tol=1e-9)

    below_starting = _charge_strength_modifier_clause(
        clause_id="test:charge-strength-runtime:below-starting",
        target_constraint="target_unit_below_starting_strength",
        delta=1,
        modifier_priority=1,
    )
    below_half = _charge_strength_modifier_clause(
        clause_id="test:charge-strength-runtime:below-half",
        target_constraint="target_unit_below_half_strength",
        delta=2,
        modifier_priority=2,
    )
    rule_ir = _rule_ir(
        source_id="test:charge-strength-runtime",
        clauses=(below_half, below_starting),
    )
    records = tuple(
        _ability_record(
            record_id=f"record:test:charge-strength-runtime:{index}",
            rule_ir=rule_ir,
            trigger_kind=TimingTriggerKind.AFTER_DICE_ROLL,
            runtime_clause_id=clause.clause_id,
            datasheet_id=source_unit.datasheet_id,
        )
        for index, clause in enumerate(rule_ir.clauses, start=1)
    )
    ability_index = AbilityCatalogIndex.from_records(records)

    def modifiers() -> tuple[int, ...]:
        return tuple(
            modifier.operand
            for modifier in catalog_charge_roll_modifiers_for_unit(
                state=state,
                ability_index=ability_index,
                unit=source_unit,
                current_model_instance_ids=source_unit.own_model_ids(),
            )
        )

    assert modifiers() == ()

    target_unit = _unit_with_dead_model(target_unit, index=4)
    state.replace_army_definitions([source_army, _army_with_unit(target_army, target_unit)])
    assert modifiers() == (1,)

    target_unit = _unit_with_dead_model(target_unit, index=3)
    state.replace_army_definitions([source_army, _army_with_unit(target_army, target_unit)])
    assert modifiers() == (1,)

    target_unit = _unit_with_dead_model(target_unit, index=2)
    current_target_army = _army_with_unit(target_army, target_unit)
    state.replace_army_definitions([source_army, current_target_army])
    resolved = catalog_charge_roll_modifiers_for_unit(
        state=state,
        ability_index=ability_index,
        unit=source_unit,
        current_model_instance_ids=source_unit.own_model_ids(),
    )
    assert tuple(modifier.operand for modifier in resolved) == (2,)
    assert tuple(modifier.priority for modifier in resolved) == (2,)

    state.battlefield_state = _battlefield_for_units(
        source_army=source_army,
        source_unit=source_unit,
        source_x=source_x,
        target_army=current_target_army,
        target_unit=target_unit,
        target_x=target_x + 0.001,
    )
    assert modifiers() == ()

    state.battlefield_state = _battlefield_for_units(
        source_army=source_army,
        source_unit=source_unit,
        source_x=source_x,
        target_army=current_target_army,
        target_unit=target_unit,
        target_x=target_x,
    )
    tied_rule_ir = _rule_ir(
        source_id="test:charge-strength-runtime-tie",
        clauses=(
            below_half,
            replace(
                below_half,
                clause_id="test:charge-strength-runtime:below-half-tie",
            ),
        ),
    )
    tied_index = AbilityCatalogIndex.from_records(
        (
            _ability_record(
                record_id="record:test:charge-strength-runtime-tie",
                rule_ir=tied_rule_ir,
                trigger_kind=TimingTriggerKind.AFTER_DICE_ROLL,
                datasheet_id=source_unit.datasheet_id,
            ),
        )
    )
    with pytest.raises(GameLifecycleError, match="ambiguous priority"):
        catalog_charge_roll_modifiers_for_unit(
            state=state,
            ability_index=tied_index,
            unit=source_unit,
            current_model_instance_ids=source_unit.own_model_ids(),
        )


def test_catalog_static_attack_modifiers_ignore_disabled_records() -> None:
    source_army, target_army = _mustered_core_armies()
    source_unit = source_army.units[0]
    armies = (source_army, target_army)
    clause = RuleClause(
        clause_id="test:disabled-static-attack-modifier:clause",
        source_span=_span(),
        trigger=RuleTrigger(
            kind=RuleTriggerKind.DICE_ROLL,
            source_span=_span(),
            parameters=_parameters(("roll_type", "hit")),
        ),
        conditions=(
            _condition(
                RuleConditionKind.TARGET_CONSTRAINT,
                ("gate_subject", "source_unit"),
                ("relationship", "this_model_makes_attack"),
                ("target_constraint", "source_unit_below_starting_strength"),
            ),
        ),
        target=RuleTargetSpec(kind=RuleTargetKind.THIS_MODEL, source_span=_span()),
        effects=(
            _effect(
                RuleEffectKind.MODIFY_DICE_ROLL,
                ("delta", 1),
                ("roll_type", "hit"),
            ),
        ),
    )
    rule_ir = _rule_ir(
        source_id="test:disabled-static-attack-modifier",
        clauses=(clause,),
    )
    active_record = _ability_record(
        record_id="record:disabled-static-attack-modifier",
        rule_ir=rule_ir,
        trigger_kind=TimingTriggerKind.PASSIVE_QUERY,
        datasheet_id=source_unit.datasheet_id,
    )
    disabled_record = replace(
        active_record,
        definition=replace(active_record.definition, replay_payload={"disabled": True}),
        disabled=True,
    )

    def runtime_for(record: AbilityCatalogRecord) -> CatalogStaticAttackModifierRuntime:
        return CatalogStaticAttackModifierRuntime(
            ability_indexes_by_player_id={
                source_army.player_id: AbilityCatalogIndex.from_records((record,)),
                target_army.player_id: AbilityCatalogIndex.from_records(()),
            },
            armies=armies,
        )

    def state_for_armies() -> GameState:
        state = _state_without_battlefield(
            active_player_id=source_army.player_id,
            phase=BattlePhase.SHOOTING,
        )
        for army in armies:
            state.record_army_definition(army)
        return state

    disabled_state = state_for_armies()
    assert runtime_for(disabled_record).record_static_effects(state=disabled_state) == ()
    assert all(
        effect.source_rule_id != rule_ir.source_id for effect in disabled_state.persisting_effects
    )

    active_state = state_for_armies()
    active_effects = runtime_for(active_record).record_static_effects(state=active_state)
    assert len(active_effects) == len(source_unit.own_models)
    assert {effect.source_rule_id for effect in active_effects} == {rule_ir.source_id}


def test_catalog_runtime_choice_descriptors_reject_domain_drift() -> None:
    source_army, target_army = _mustered_core_armies()
    source_unit = source_army.units[0]
    target_unit = target_army.units[0]
    clause = RuleClause(
        clause_id="test:catalog-choice-contracts:clause",
        source_span=_span(),
        target=RuleTargetSpec(kind=RuleTargetKind.THIS_UNIT, source_span=_span()),
        effects=(
            _effect(
                RuleEffectKind.GRANT_WEAPON_ABILITY,
                ("weapon_ability", WeaponKeyword.LETHAL_HITS.value),
            ),
        ),
    )
    record = _ability_record(
        record_id="record:catalog-choice-contracts",
        rule_ir=_rule_ir(
            source_id="test:catalog-choice-contracts",
            clauses=(clause,),
        ),
        trigger_kind=TimingTriggerKind.START_PHASE,
        phase=BattlePhaseKind.SHOOTING,
    )
    named_option = CatalogNamedWeaponAbilityChoiceOption(
        option_id="catalog-choice:lethal-hits",
        selection_option_id="catalog-choice:option-lethal-hits",
        selection_option_index=1,
        keyword=WeaponKeyword.LETHAL_HITS,
        weapon_ability_value=None,
        ability=None,
        effect_index=0,
    )
    named_group = CatalogNamedWeaponAbilityChoiceGroup(
        record=record,
        unit=source_unit,
        clause=clause,
        selection_group_id="catalog-choice:group",
        target_scope="models_in_this_unit",
        weapon_names=("Bolt rifle",),
        target_model_instance_ids=(source_unit.own_models[0].model_instance_id,),
        options=(named_option,),
    )
    profile = _first_catalog_weapon_profile()
    sequence = AttackSequence(
        sequence_id="attack-sequence:catalog-choice-contracts",
        attacker_player_id=source_army.player_id,
        attacking_unit_instance_id=source_unit.unit_instance_id,
        source_phase=BattlePhase.SHOOTING,
        attack_pools=(
            RangedAttackPool(
                attacker_model_instance_id=source_unit.own_models[0].model_instance_id,
                weapon_instance_id="weapon-instance:test:catalog-choice-contracts",
                wargear_id="wargear:catalog-choice-contracts",
                weapon_profile_id=profile.profile_id,
                weapon_profile=profile,
                target_unit_instance_id=target_unit.unit_instance_id,
                shooting_type=ShootingType.NORMAL,
                attacks=1,
                target_visible_model_ids=target_unit.own_model_ids(),
                target_in_range_model_ids=target_unit.own_model_ids(),
            ),
        ),
    )
    status_option = CatalogPostShootHitTargetStatusOption(
        option_id="catalog-choice:status-target",
        target_unit_instance_id=target_unit.unit_instance_id,
    )
    status_group = CatalogPostShootHitTargetStatusGroup(
        record=record,
        unit=source_unit,
        clause=clause,
        effect_index=0,
        status="cannot_target_with_stratagem",
        status_label="cannot be targeted with a Stratagem",
        target_scope="hit_target_unit",
        source_model_instance_id=None,
        attack_sequence=sequence,
        attack_sequence_completed_event_id="event:catalog-choice-contracts",
        options=(status_option,),
    )
    mortal_option = CatalogUnitMoveCompletedMortalWoundsTargetOption(
        option_id="catalog-choice:mortal-target",
        target_unit_instance_id=target_unit.unit_instance_id,
        target_player_id=target_army.player_id,
    )
    mortal_group = CatalogUnitMoveCompletedMortalWoundsGroup(
        record=record,
        source_unit=source_unit,
        source_rules_unit_instance_id=source_unit.unit_instance_id,
        player_id=source_army.player_id,
        clause=clause,
        effect_index=0,
        roll_threshold=4,
        mortal_wounds_expression=DiceExpression(quantity=1, sides=3),
        maximum_mortal_wounds=6,
        optional=True,
        forbidden_stratagem_handler_ids=(CORE_GO_TO_GROUND_HANDLER_ID,),
        target_range_inches=6,
        target_requires_visibility=True,
        roll_model_instance_ids=(source_unit.own_models[0].model_instance_id,),
        trigger_event_id="event:catalog-choice-move-completed",
        movement_action="normal_move",
        options=(mortal_option,),
    )

    assert CatalogRuleIrHookDefinition("catalog-choice:hook").hook_id == "catalog-choice:hook"
    assert named_group.options == (named_option,)
    assert status_group.options == (status_option,)
    assert mortal_group.options == (mortal_option,)
    for invalid_hook_id in ("", " catalog-choice:hook"):
        with pytest.raises(GameLifecycleError, match="hook definition hook_id"):
            CatalogRuleIrHookDefinition(invalid_hook_id)
    with pytest.raises(GameLifecycleError, match="finite options"):
        replace(named_group, options=())
    with pytest.raises(GameLifecycleError, match="must not duplicate IDs"):
        replace(named_group, options=(named_option, named_option))
    with pytest.raises(GameLifecycleError, match="selection options must be unique"):
        replace(
            named_group,
            options=(
                named_option,
                replace(named_option, option_id="catalog-choice:sustained-hits"),
            ),
        )
    with pytest.raises(GameLifecycleError, match="requires finite options"):
        replace(status_group, options=())
    with pytest.raises(GameLifecycleError, match="must not duplicate IDs"):
        replace(status_group, options=(status_option, status_option))
    for field_name, invalid_value, expected in (
        ("effect_index", -1, "effect_index must be non-negative"),
        ("roll_threshold", 1, "roll_threshold must be 2-6"),
        ("mortal_wounds_expression", 0, "positive fixed or dice value"),
        ("maximum_mortal_wounds", 0, "maximum must be positive"),
        ("optional", 1, "optional must be bool"),
        ("target_range_inches", 0, "target range must be positive"),
        ("target_requires_visibility", 1, "visibility flag must be bool"),
        ("options", (), "requires target options"),
    ):
        with pytest.raises(GameLifecycleError, match=expected):
            replace(mortal_group, **cast(Any, {field_name: invalid_value}))
    with pytest.raises(GameLifecycleError, match="must not duplicate IDs"):
        replace(mortal_group, options=(mortal_option, mortal_option))


def test_catalog_rule_effect_consumers_classify_supported_and_fail_closed_shapes() -> None:
    supported_cases = (
        (
            _effect(RuleEffectKind.MATERIALIZE_MODELS),
            ("catalog-ir:model-materialization",),
        ),
        (
            _effect(
                RuleEffectKind.MODIFY_DICE_ROLL,
                ("roll_type", "charge"),
            ),
            ("catalog-ir:charge-roll-modifier",),
        ),
        (
            _effect(
                RuleEffectKind.SET_CHARACTERISTIC,
                ("characteristic", Characteristic.LEADERSHIP.value),
            ),
            ("catalog-ir:leadership-characteristic-query",),
        ),
        (
            _effect(
                RuleEffectKind.MODIFY_CHARACTERISTIC,
                ("characteristic", Characteristic.MOVEMENT.value),
            ),
            ("catalog-ir:movement-characteristic-modifier",),
        ),
        (
            _effect(RuleEffectKind.MOVEMENT_TRANSIT_PERMISSION),
            ("catalog-ir:movement-transit-permission",),
        ),
    )
    unsupported_cases = (
        _effect(
            RuleEffectKind.MODIFY_DICE_ROLL,
            ("roll_type", "unsupported_roll"),
        ),
        _effect(
            RuleEffectKind.REROLL_PERMISSION,
            ("roll_type", "charge"),
            ("target_reference", "selected_unit"),
        ),
        _effect(
            RuleEffectKind.REROLL_PERMISSION,
            ("roll_type", "unsupported_roll"),
        ),
        _effect(RuleEffectKind.OUT_OF_PHASE_ACTION),
        _effect(
            RuleEffectKind.GRANT_ABILITY,
            ("ability", "unsupported_ability"),
        ),
        _effect(
            RuleEffectKind.PLACEMENT_PERMISSION,
            ("placement_kind", 1),
        ),
        _effect(
            RuleEffectKind.PLACEMENT_PERMISSION,
            ("placement_kind", "unsupported_placement"),
        ),
    )

    for effect, expected_consumer_ids in supported_cases:
        assert catalog_rule_ir_consumer_ids_for_effect(effect) == expected_consumer_ids
    for effect in unsupported_cases:
        assert catalog_rule_ir_consumer_ids_for_effect(effect) == ()

    with pytest.raises(GameLifecycleError, match="requires RuleEffectSpec"):
        catalog_rule_ir_consumer_ids_for_effect(cast(RuleEffectSpec, object()))
    for malformed_effect, expected in (
        (
            _effect(RuleEffectKind.MODIFY_DICE_ROLL),
            "roll_type must be a non-empty string",
        ),
        (
            _effect(
                RuleEffectKind.SET_CHARACTERISTIC,
                ("characteristic", "unsupported_characteristic"),
            ),
            "characteristic parameter is invalid",
        ),
        (
            _effect(
                RuleEffectKind.GRANT_WEAPON_ABILITY,
                ("weapon_ability", "unsupported_weapon_keyword"),
                ("weapon_scope", "all"),
            ),
            "unsupported keyword",
        ),
        (
            _effect(RuleEffectKind.GRANT_ABILITY),
            "ability must be a non-empty string",
        ),
    ):
        with pytest.raises(GameLifecycleError, match=expected):
            catalog_rule_ir_consumer_ids_for_effect(malformed_effect)


def _command_point_record(
    *,
    record_id: str,
    raw_text: str,
    source_unit: UnitInstance,
    trigger_kind: TimingTriggerKind,
) -> AbilityCatalogRecord:
    source_text = RuleSourceText.from_raw(
        source_id=f"source:{record_id}",
        raw_text=raw_text,
    )
    rule_ir = compile_rule_source_text(
        source_text,
        source_keyword_sequence_parts=SOURCE_KEYWORD_SEQUENCE_PARTS,
    ).rule_ir
    return _ability_record(
        record_id=record_id,
        rule_ir=rule_ir,
        trigger_kind=trigger_kind,
        datasheet_id=source_unit.datasheet_id,
    )


def _compiled_record(
    *,
    record_id: str,
    raw_text: str,
    source_unit: UnitInstance,
    trigger_kind: TimingTriggerKind,
) -> AbilityCatalogRecord:
    return _command_point_record(
        record_id=record_id,
        raw_text=raw_text,
        source_unit=source_unit,
        trigger_kind=trigger_kind,
    )


def _command_point_runtime(
    *,
    armies: tuple[ArmyDefinition, ...],
    records_by_player: Mapping[str, tuple[AbilityCatalogRecord, ...]],
) -> CatalogCommandPointRuntime:
    return CatalogCommandPointRuntime(
        ability_indexes_by_player_id={
            army.player_id: AbilityCatalogIndex.from_records(
                records_by_player.get(army.player_id, ())
            )
            for army in armies
        },
        armies=armies,
    )


def _unit_with_leadership(unit: UnitInstance, *, leadership: int) -> UnitInstance:
    return replace(
        unit,
        own_models=tuple(
            replace(
                model,
                characteristics=tuple(
                    CharacteristicValue.from_raw(Characteristic.LEADERSHIP, leadership)
                    if value.characteristic is Characteristic.LEADERSHIP
                    else value
                    for value in model.characteristics
                ),
            )
            for model in unit.own_models
        ),
    )


def _first_catalog_weapon_profile() -> WeaponProfile:
    catalog = ArmyCatalog.phase9a_canonical_content_pack()
    for wargear in catalog.wargear:
        if wargear.weapon_profiles:
            return wargear.weapon_profiles[0]
    raise AssertionError("Canonical catalog must contain a weapon profile.")


def _test_stratagem_definition(*, command_point_cost: int) -> StratagemDefinition:
    return StratagemDefinition(
        stratagem_id="catalog-cp-test-stratagem",
        name="Catalog CP Test Stratagem",
        source_id="source:catalog-cp-test-stratagem",
        command_point_cost=command_point_cost,
        category=StratagemCategory.BATTLE_TACTIC,
        when_descriptor="Start of the Shooting phase.",
        target_descriptor="One friendly unit.",
        effect_descriptor="Record-only test effect.",
        restrictions_descriptor="Test Stratagem.",
        timing=StratagemTimingDescriptor(
            trigger_kind=TimingTriggerKind.START_PHASE,
            phase=BattlePhaseKind.SHOOTING,
        ),
    )


def _core_stratagem_definition(stratagem_id: str) -> StratagemDefinition:
    return next(
        record.definition
        for record in eleventh_edition_stratagem_catalog_records()
        if record.definition.stratagem_id == stratagem_id
    )


def _catalog_stratagem_context(
    *,
    state: GameState,
    player_id: str,
    trigger_kind: TimingTriggerKind,
    phase: BattlePhaseKind,
    active_player_id: str | None,
    trigger_payload: JsonValue = None,
) -> StratagemEligibilityContext:
    return StratagemEligibilityContext(
        game_id=state.game_id,
        player_id=player_id,
        battle_round=state.battle_round,
        phase=phase,
        active_player_id=active_player_id,
        trigger_kind=trigger_kind,
        trigger_payload=trigger_payload,
    )


def _generic_stratagem_definition(
    *,
    metadata: dict[str, JsonValue],
) -> StratagemDefinition:
    rule_ir = _rule_ir(
        source_id="test:catalog-generic-stratagem",
        clauses=(
            RuleClause(
                clause_id="test:catalog-generic-stratagem:clause",
                source_span=_span(),
                target=RuleTargetSpec(kind=RuleTargetKind.THIS_UNIT, source_span=_span()),
                effects=(
                    _effect(
                        RuleEffectKind.GRANT_ABILITY,
                        ("ability", "can_fall_back_and_shoot"),
                    ),
                ),
            ),
        ),
    )
    return replace(
        _test_stratagem_definition(command_point_cost=1),
        stratagem_id="catalog-generic-runtime",
        source_id=rule_ir.source_id,
        handler_id=GENERIC_RULE_IR_STRATAGEM_HANDLER_ID,
        target_spec=StratagemTargetSpec(
            target_kind=StratagemTargetKind.FRIENDLY_UNIT,
            target_policy_id="test:catalog-generic-runtime-target",
        ),
        effect_payload=validate_json_value(
            {
                "rule_ir": rule_ir.to_payload(),
                **metadata,
            }
        ),
    )


def _test_stratagem_source_decision(
    *,
    actor_id: str,
    suffix: str,
) -> tuple[DecisionRequest, DecisionResult]:
    request = DecisionRequest(
        request_id=f"request:catalog-cp:{suffix}",
        decision_type=STRATAGEM_DECISION_TYPE,
        actor_id=actor_id,
        payload={"finite": True},
        options=(
            DecisionOption(
                option_id=f"option:catalog-cp:{suffix}",
                label="Use test Stratagem",
                payload={"submission_kind": STRATAGEM_DECISION_TYPE},
            ),
        ),
    )
    return (
        request,
        DecisionResult.for_request(
            result_id=f"result:catalog-cp:{suffix}",
            request=request,
            selected_option_id=request.options[0].option_id,
        ),
    )


def _cost_modifier_context(
    *,
    state: GameState,
    decisions: DecisionController,
    definition: StratagemDefinition,
    eligibility: StratagemEligibilityContext,
    target_binding: StratagemTargetBinding,
    source_request_id: str,
    source_result_id: str,
) -> StratagemCostModifierContext:
    return StratagemCostModifierContext(
        state=state,
        definition=definition,
        eligibility_context=eligibility,
        target_binding=target_binding,
        effect_selection=None,
        base_command_point_cost=definition.command_point_cost,
        current_command_point_cost=definition.command_point_cost,
        decisions=decisions,
        source_decision_request_id=source_request_id,
        source_decision_result_id=source_result_id,
    )


def _desperate_escape_record(*, source_unit: UnitInstance) -> AbilityCatalogRecord:
    source_text = RuleSourceText.from_raw(
        source_id="test:chaos-daemons:desperate-escape",
        raw_text=(
            "Each time an enemy unit (excluding Monsters and Vehicles) that is within "
            "Engagement Range of one or more units from your army with this ability is selected "
            "to Fall Back, models in that enemy unit must take Desperate Escape tests. If that "
            "enemy unit is also Battle-shocked, subtract 1 from each of those Desperate Escape "
            "tests."
        ),
    )
    rule_ir = compile_rule_source_text(
        source_text,
        source_keyword_sequence_parts=SOURCE_KEYWORD_SEQUENCE_PARTS,
    ).rule_ir
    return AbilityCatalogRecord(
        record_id="record:chaos-daemons:desperate-escape",
        definition=AbilityDefinition(
            ability_id="ability:chaos-daemons:desperate-escape",
            name="Forced Desperate Escape",
            source_id=source_text.source_id,
            when_descriptor="Enemy selected to Fall Back.",
            effect_descriptor="Force Desperate Escape tests.",
            restrictions_descriptor="Non-Monster non-Vehicle enemy unit.",
            timing=AbilityTimingDescriptor(
                trigger_kind=TimingTriggerKind.JUST_AFTER_ENEMY_UNIT_SELECTED_TO_FALL_BACK
            ),
            handler_id=GENERIC_RULE_IR_ABILITY_HANDLER_ID,
            replay_payload=validate_json_value({"rule_ir": rule_ir.to_payload()}),
        ),
        source_kind=AbilitySourceKind.DATASHEET,
        datasheet_id=source_unit.datasheet_id,
    )


def _once_per_battle_record(*, source_unit: UnitInstance) -> AbilityCatalogRecord:
    rule_ir = compile_rule_source_text(
        RuleSourceText.from_raw(
            source_id="wahapedia:datasheet-ability:finest-hour",
            raw_text=ONCE_PER_BATTLE_FIGHT_BOOST_TEXT,
        ),
        source_keyword_sequence_parts=SOURCE_KEYWORD_SEQUENCE_PARTS,
    ).rule_ir
    return _ability_record(
        record_id="record:once-per-battle:finest-hour",
        rule_ir=rule_ir,
        trigger_kind=TimingTriggerKind.START_PHASE,
        datasheet_id=source_unit.datasheet_id,
    )


def _fight_start_selection_clause(
    *,
    clause_id: str = "test:selected-target:selection:fight",
) -> RuleClause:
    return RuleClause(
        clause_id=clause_id,
        template_id="phase17c:selected-target-constraint",
        source_span=_span(),
        trigger=RuleTrigger(
            kind=RuleTriggerKind.TIMING_WINDOW,
            source_span=_span(),
            parameters=_parameters(
                ("edge", "start"),
                ("owner", None),
                ("phase", BattlePhase.FIGHT.value),
            ),
        ),
        target=RuleTargetSpec(
            kind=RuleTargetKind.ENEMY_UNIT,
            source_span=_span(),
            parameters=_parameters(("allegiance", "enemy")),
        ),
    )


def _post_shoot_hit_selection_clause() -> RuleClause:
    return RuleClause(
        clause_id="test:selected-target:selection:post-shoot",
        template_id="phase17c:selected-target-constraint",
        source_span=_span(),
        trigger=RuleTrigger(
            kind=RuleTriggerKind.TIMING_WINDOW,
            source_span=_span(),
            parameters=_parameters(
                ("attacker_model_reference", "this_model"),
                ("edge", "after"),
                ("owner", "active_player"),
                ("phase", "shooting"),
                ("subject", "this_model"),
                ("timing_window", "just_after_friendly_unit_has_shot"),
                ("target_relationship", "hit_by_those_attacks"),
                ("weapon_names", ("Dread of the Deep Void",)),
            ),
        ),
        target=RuleTargetSpec(
            kind=RuleTargetKind.ENEMY_UNIT,
            source_span=_span(),
            parameters=_parameters(
                ("allegiance", "enemy"),
                ("target_relationship", "hit_by_those_attacks"),
            ),
        ),
    )


def _post_shoot_effect_trigger(*, actor: str) -> RuleTrigger:
    return RuleTrigger(
        kind=RuleTriggerKind.DICE_ROLL,
        source_span=_span(),
        parameters=_parameters(
            ("actor", actor),
            ("target_reference", "selected_unit"),
            ("timing_window", "attack_sequence.attack"),
        ),
    )


def _effect_clause(
    *,
    clause_id: str,
    duration: RuleDuration | None,
    effect_kind: RuleEffectKind,
    conditions: tuple[RuleCondition, ...] = (),
    **parameters: RuleParameterValue,
) -> RuleClause:
    return RuleClause(
        clause_id=clause_id,
        source_span=_span(),
        conditions=conditions,
        target=RuleTargetSpec(kind=RuleTargetKind.SELECTED_TARGET, source_span=_span()),
        effects=(_effect(effect_kind, *tuple(parameters.items())),),
        duration=duration,
    )


def _effect(
    kind: RuleEffectKind,
    *parameters: tuple[str, RuleParameterValue],
) -> RuleEffectSpec:
    return RuleEffectSpec(
        kind=kind,
        source_span=_span(),
        parameters=_parameters(*parameters),
    )


def _condition(
    kind: RuleConditionKind,
    *parameters: tuple[str, RuleParameterValue],
) -> RuleCondition:
    return RuleCondition(
        kind=kind,
        source_span=_span(),
        parameters=_parameters(*parameters),
    )


def _selection_engagement_range_condition(*, object_kind: str) -> RuleCondition:
    return _condition(
        RuleConditionKind.DISTANCE_PREDICATE,
        ("distance_inches", None),
        ("negated", False),
        ("object_kind", object_kind),
        ("object_reference", "this"),
        ("predicate", "within_engagement_range"),
        ("qualifier", None),
        ("range_kind", "engagement_range"),
    )


def _duration(endpoint: str) -> RuleDuration:
    return RuleDuration(
        kind=RuleDurationKind.UNTIL_TIMING_ENDPOINT,
        source_span=_span(),
        parameters=_parameters(("endpoint", endpoint)),
    )


def _charge_strength_modifier_clause(
    *,
    clause_id: str,
    target_constraint: str,
    delta: int,
    modifier_priority: int,
) -> RuleClause:
    return RuleClause(
        clause_id=clause_id,
        source_span=_span(),
        conditions=(
            _condition(
                RuleConditionKind.TARGET_CONSTRAINT,
                ("distance_inches", 9.0),
                ("gate_subject", "nearby_unit"),
                ("relationship", "any_unit_within_distance_of_this_unit"),
                ("target_allegiance", "enemy"),
                ("target_constraint", target_constraint),
            ),
        ),
        target=RuleTargetSpec(kind=RuleTargetKind.THIS_UNIT, source_span=_span()),
        effects=(
            _effect(
                RuleEffectKind.MODIFY_DICE_ROLL,
                ("delta", delta),
                ("modifier_exclusive_group", "nearby-enemy-strength"),
                ("modifier_priority", modifier_priority),
                ("roll_type", "charge"),
            ),
        ),
    )


def _modifier_ignore_permission_clause(
    *,
    clause_id: str,
    modifier_kinds: tuple[str, ...],
) -> RuleClause:
    return RuleClause(
        clause_id=clause_id,
        source_span=_span(),
        target=RuleTargetSpec(kind=RuleTargetKind.THIS_MODEL, source_span=_span()),
        effects=(
            _effect(
                RuleEffectKind.GRANT_ABILITY,
                ("ability", "modifier_ignore_permission"),
                ("modifier_kinds", modifier_kinds),
                ("selection", "any_or_all"),
            ),
        ),
        duration=RuleDuration(
            kind=RuleDurationKind.WHILE_CONDITION_TRUE,
            source_span=_span(),
        ),
    )


def _rule_ir(*, source_id: str, clauses: tuple[RuleClause, ...]) -> RuleIR:
    return RuleIR(
        rule_id=f"{source_id}:rule",
        source_id=source_id,
        normalized_text=_span().text,
        parser_version="test-catalog-runtime-consumers",
        clauses=clauses,
    )


def _ability_record(
    *,
    record_id: str,
    rule_ir: RuleIR,
    trigger_kind: TimingTriggerKind,
    runtime_clause_id: str | None = None,
    handler_id: str = GENERIC_RULE_IR_ABILITY_HANDLER_ID,
    datasheet_id: str = "core-intercessor-like-infantry",
    source_kind: AbilitySourceKind = AbilitySourceKind.DATASHEET,
    wargear_id: str | None = None,
    phase: BattlePhaseKind | None = None,
) -> AbilityCatalogRecord:
    replay_payload: dict[str, JsonValue] = {"rule_ir": cast(JsonValue, rule_ir.to_payload())}
    if runtime_clause_id is not None:
        replay_payload["runtime_clause_id"] = runtime_clause_id
    return AbilityCatalogRecord(
        record_id=record_id,
        definition=AbilityDefinition(
            ability_id=f"{record_id}:ability",
            name="Selected Target Test",
            source_id=rule_ir.source_id,
            when_descriptor="Selected target timing.",
            effect_descriptor="Selected target effect.",
            restrictions_descriptor="Test-only source-backed RuleIR.",
            timing=AbilityTimingDescriptor(trigger_kind=trigger_kind, phase=phase),
            handler_id=handler_id,
            replay_payload=validate_json_value(replay_payload),
        ),
        source_kind=source_kind,
        datasheet_id=datasheet_id,
        wargear_id=wargear_id,
    )


def _parameters(*parameters: tuple[str, RuleParameterValue]) -> tuple[RuleParameter, ...]:
    return parameters_from_pairs(parameters)


def _span() -> TextSpan:
    text = "catalog support test"
    return TextSpan(text=text, start=0, end=len(text))


@pytest.mark.parametrize(
    ("target_x", "expected_mode", "expected_engaged"),
    [(40.0, "normal", False), (10.4, "fall_back", True)],
)
def test_catalog_fight_end_triggered_movement_runtime_uses_raid_and_run_rule_ir(
    target_x: float,
    expected_mode: str,
    expected_engaged: bool,
) -> None:
    source_army, target_army = _mustered_core_armies()
    source_unit = source_army.units[0]
    target_unit = target_army.units[0]
    battlefield = _battlefield_for_units(
        source_army=source_army,
        source_unit=source_unit,
        source_x=10.0,
        target_army=target_army,
        target_unit=target_unit,
        target_x=target_x,
    )
    state = _state_with_battlefield(
        armies=(source_army, target_army),
        battlefield=battlefield,
        active_player_id=source_army.player_id,
        phase=BattlePhase.FIGHT,
    )
    policy = state.runtime_ruleset_descriptor().fight_policy
    fight_state = FightPhaseState.start(
        battle_round=state.battle_round,
        active_player_id=source_army.player_id,
        policy=policy,
        engaged_at_fight_step_start_unit_ids=(
            (source_unit.unit_instance_id,) if expected_engaged else ()
        ),
        fights_first_registry=FightsFirstRegistry(),
    )
    fight_state = replace(
        fight_state,
        fight_order_state=replace(
            fight_state.fight_order_state,
            selected_to_fight_unit_ids=(source_unit.unit_instance_id,),
        ),
    ).with_current_step(current_step=FightPhaseStepKind.END, policy=policy)
    state.fight_phase_state = fight_state

    rule_ir_payload = skyreavers_package.datasheet_rule_ir_payload_by_source_row_id("000004196:4")
    assert rule_ir_payload is not None
    record = _ability_record(
        record_id=f"record:aeldari:skyreavers:raid-and-run:{expected_mode}",
        rule_ir=RuleIR.from_payload(rule_ir_payload),
        trigger_kind=TimingTriggerKind.END_PHASE,
        datasheet_id=source_unit.datasheet_id,
        phase=BattlePhaseKind.FIGHT,
    )
    decisions = DecisionController()
    runtime = CatalogFightEndTriggeredMovementRuntime(
        ability_indexes_by_player_id={
            source_army.player_id: AbilityCatalogIndex.from_records((record,)),
            target_army.player_id: AbilityCatalogIndex.from_records(()),
        },
        armies=(source_army, target_army),
    )
    bindings = runtime.bindings()
    assert len(bindings) == 1
    assert bindings[0].hook_id == CATALOG_IR_FIGHT_END_TRIGGERED_MOVEMENT_CONSUMER_ID
    assert (
        catalog_fight_end_triggered_movement_hook_bindings(
            ability_indexes_by_player_id=runtime.ability_indexes_by_player_id,
            armies=runtime.armies,
        )[0].hook_id
        == CATALOG_IR_FIGHT_END_TRIGGERED_MOVEMENT_CONSUMER_ID
    )

    request = runtime.next_request(FightPhaseEndRequestContext(state=state, decisions=decisions))

    assert request is not None
    assert request.decision_type == SELECT_TRIGGERED_MOVEMENT_DECISION_TYPE
    assert request.actor_id == source_army.player_id
    payload = cast(dict[str, JsonValue], request.payload)
    assert payload["requires_movement_proposal"] is True
    descriptor = cast(dict[str, JsonValue], payload["descriptor"])
    assert descriptor["movement_kind"] == "triggered"
    assert descriptor["movement_mode"] == expected_mode
    assert descriptor["allow_within_engagement_range"] is expected_engaged
    assert 4.0 <= cast(float, descriptor["max_distance_inches"]) <= 6.0
    eligible_units = cast(list[dict[str, JsonValue]], payload["eligible_units"])
    assert len(eligible_units) == 1
    assert eligible_units[0]["unit_instance_id"] == source_unit.unit_instance_id
    assert eligible_units[0]["hook_id"] == CATALOG_IR_FIGHT_END_TRIGGERED_MOVEMENT_CONSUMER_ID
    replay_payload = cast(dict[str, JsonValue], eligible_units[0]["replay_payload"])
    assert replay_payload["is_engaged"] is expected_engaged
    assert replay_payload["movement_mode"] == expected_mode
    distance_roll = cast(dict[str, JsonValue], replay_payload["distance_roll"])
    assert 1 <= cast(int, distance_roll["value"]) <= 3
    source_d6 = cast(dict[str, JsonValue], distance_roll["source_d6_result"])
    source_spec = cast(dict[str, JsonValue], source_d6["spec"])
    assert source_spec["roll_type"] == (
        f"{CATALOG_FIGHT_END_TRIGGERED_MOVEMENT_ROLL_TYPE}.d3_source"
    )


def test_catalog_fight_end_triggered_movement_runtime_fails_fast_on_invalid_hosts() -> None:
    empty_index = AbilityCatalogIndex.from_records(())
    with pytest.raises(GameLifecycleError, match="indexes must be a mapping"):
        CatalogFightEndTriggeredMovementRuntime(
            ability_indexes_by_player_id=cast(Any, ()),
            armies=(),
        )
    with pytest.raises(GameLifecycleError, match="player id is invalid"):
        CatalogFightEndTriggeredMovementRuntime(
            ability_indexes_by_player_id={" invalid ": empty_index},
            armies=(),
        )
    with pytest.raises(GameLifecycleError, match="index is invalid"):
        CatalogFightEndTriggeredMovementRuntime(
            ability_indexes_by_player_id={"player-a": cast(Any, object())},
            armies=(),
        )
    with pytest.raises(GameLifecycleError, match="armies must be a tuple"):
        CatalogFightEndTriggeredMovementRuntime(
            ability_indexes_by_player_id={},
            armies=cast(Any, []),
        )
    with pytest.raises(GameLifecycleError, match="army is invalid"):
        CatalogFightEndTriggeredMovementRuntime(
            ability_indexes_by_player_id={},
            armies=(cast(Any, object()),),
        )

    source_army, _target_army = _mustered_core_armies()
    with pytest.raises(GameLifecycleError, match="duplicate player ids"):
        CatalogFightEndTriggeredMovementRuntime(
            ability_indexes_by_player_id={},
            armies=(source_army, source_army),
        )

    runtime = CatalogFightEndTriggeredMovementRuntime(
        ability_indexes_by_player_id={source_army.player_id: empty_index},
        armies=(source_army,),
    )
    assert runtime.bindings() == ()
    with pytest.raises(GameLifecycleError, match="requires request context"):
        runtime.next_request(cast(Any, None))


def test_catalog_fight_end_triggered_movement_runtime_does_not_expose_attached_units() -> None:
    source_army, target_army = _mustered_attached_once_per_battle_armies()
    leader_unit = next(
        unit for unit in source_army.units if unit.datasheet_id == "core-character-leader"
    )
    attached_unit_id = source_army.attached_units[0].attached_unit_instance_id
    battlefield = create_deterministic_battlefield_scenario(
        battlefield_id="catalog-fight-end-movement-attached",
        armies=(source_army, target_army),
    ).battlefield_state
    state = _state_with_battlefield(
        armies=(source_army, target_army),
        battlefield=battlefield,
        active_player_id=source_army.player_id,
        phase=BattlePhase.FIGHT,
    )
    policy = state.runtime_ruleset_descriptor().fight_policy
    fight_state = FightPhaseState.start(
        battle_round=state.battle_round,
        active_player_id=source_army.player_id,
        policy=policy,
        engaged_at_fight_step_start_unit_ids=(attached_unit_id,),
        fights_first_registry=FightsFirstRegistry(),
    )
    state.fight_phase_state = replace(
        fight_state,
        fight_order_state=replace(
            fight_state.fight_order_state,
            selected_to_fight_unit_ids=(attached_unit_id,),
        ),
    ).with_current_step(current_step=FightPhaseStepKind.END, policy=policy)
    rule_ir_payload = skyreavers_package.datasheet_rule_ir_payload_by_source_row_id("000004196:4")
    assert rule_ir_payload is not None
    record = _ability_record(
        record_id="record:aeldari:skyreavers:raid-and-run:attached",
        rule_ir=RuleIR.from_payload(rule_ir_payload),
        trigger_kind=TimingTriggerKind.END_PHASE,
        datasheet_id=leader_unit.datasheet_id,
        phase=BattlePhaseKind.FIGHT,
    )
    runtime = CatalogFightEndTriggeredMovementRuntime(
        ability_indexes_by_player_id={
            source_army.player_id: AbilityCatalogIndex.from_records((record,)),
            target_army.player_id: AbilityCatalogIndex.from_records(()),
        },
        armies=(source_army, target_army),
    )
    decisions = DecisionController()

    assert runtime.bindings() == ()
    assert (
        runtime.next_request(FightPhaseEndRequestContext(state=state, decisions=decisions)) is None
    )
    assert not decisions.event_log.records


@pytest.mark.parametrize(
    ("triggering_x", "expected_grant_count"),
    [(19.5, 0), (22.0, 1), (40.0, 0)],
)
def test_catalog_movement_end_reactive_normal_move_runtime_enforces_range(
    triggering_x: float,
    expected_grant_count: int,
) -> None:
    source_army, triggering_army = _mustered_core_armies()
    source_unit = source_army.units[0]
    triggering_unit = triggering_army.units[0]
    battlefield = _battlefield_for_units(
        source_army=source_army,
        source_unit=source_unit,
        source_x=10.0,
        target_army=triggering_army,
        target_unit=triggering_unit,
        target_x=triggering_x,
    )
    state = _state_with_battlefield(
        armies=(source_army, triggering_army),
        battlefield=battlefield,
        active_player_id=triggering_army.player_id,
        phase=BattlePhase.MOVEMENT,
    )
    rule_ir = compile_rule_source_text(
        RuleSourceText.from_raw(
            source_id="test:aeldari:rangers:path-of-the-outcast",
            raw_text=(
                "In your opponent's Movement phase, if an enemy unit ends a move within 8\" "
                "of this unit, if this unit is not within Engagement Range of one or more "
                'enemy units, this unit can make a Normal move of up to D6".'
            ),
        ),
        source_keyword_sequence_parts=SOURCE_KEYWORD_SEQUENCE_PARTS,
    ).rule_ir
    record = _ability_record(
        record_id="record:aeldari:rangers:path-of-the-outcast",
        rule_ir=rule_ir,
        trigger_kind=TimingTriggerKind.AFTER_ENEMY_UNIT_ENDS_MOVE,
        datasheet_id=source_unit.datasheet_id,
        phase=BattlePhaseKind.MOVEMENT,
    )
    runtime = CatalogMovementEndReactiveNormalMoveRuntime(
        ability_indexes_by_player_id={
            source_army.player_id: AbilityCatalogIndex.from_records((record,)),
            triggering_army.player_id: AbilityCatalogIndex.from_records(()),
        },
        armies=(source_army, triggering_army),
    )

    bindings = runtime.bindings()
    assert len(bindings) == 1
    assert bindings[0].hook_id == CATALOG_IR_MOVEMENT_END_REACTIVE_NORMAL_MOVE_CONSUMER_ID
    grants = bindings[0].handler(
        MovementEndSurgeContext(
            state=state,
            ruleset_descriptor=state.runtime_ruleset_descriptor(),
            triggering_unit_instance_id=triggering_unit.unit_instance_id,
            triggering_player_id=triggering_army.player_id,
            reacting_player_id=source_army.player_id,
            trigger_event_id="event:enemy-move-completed",
            movement_phase_action="normal_move",
            trigger_event_payload={"unit_instance_id": triggering_unit.unit_instance_id},
        )
    )

    assert len(grants) == expected_grant_count
    if not grants:
        return
    grant = grants[0]
    assert grant.unit_instance_id == source_unit.unit_instance_id
    assert grant.descriptor_source_rule_id == record.definition.source_id
    assert grant.movement_kind.value == "triggered"
    assert grant.allow_battle_shocked is True
    assert grant.one_per_phase is False
    assert grant.independent_unit_reaction is True
    replay_payload = cast(dict[str, JsonValue], grant.replay_payload)
    assert replay_payload["catalog_record_id"] == record.record_id
    assert cast(float, replay_payload["trigger_distance_inches"]) <= 8.0
    assert replay_payload["trigger_event_id"] == "event:enemy-move-completed"


def test_catalog_movement_end_reactive_runtime_ignores_disabled_records_before_parsing() -> None:
    source_army, triggering_army = _mustered_core_armies()
    source_unit = source_army.units[0]
    rule_ir = compile_rule_source_text(
        RuleSourceText.from_raw(
            source_id="test:movement-end-reactive-normal-move:disabled",
            raw_text=(
                "In your opponent's Movement phase, if an enemy unit ends a move within 8\" "
                "of this unit, if this unit is not within Engagement Range of one or more "
                'enemy units, this unit can make a Normal move of up to 6".'
            ),
        ),
        source_keyword_sequence_parts=SOURCE_KEYWORD_SEQUENCE_PARTS,
    ).rule_ir
    active = _ability_record(
        record_id="record:movement-end-reactive-normal-move:disabled",
        rule_ir=rule_ir,
        trigger_kind=TimingTriggerKind.AFTER_ENEMY_UNIT_ENDS_MOVE,
        datasheet_id=source_unit.datasheet_id,
        phase=BattlePhaseKind.MOVEMENT,
    )
    disabled = replace(
        active,
        definition=replace(active.definition, replay_payload={"disabled": True}),
        disabled=True,
    )
    runtime = CatalogMovementEndReactiveNormalMoveRuntime(
        ability_indexes_by_player_id={
            source_army.player_id: AbilityCatalogIndex.from_records((disabled,)),
            triggering_army.player_id: AbilityCatalogIndex.from_records(()),
        },
        armies=(source_army, triggering_army),
    )

    assert runtime.bindings() == ()


@pytest.mark.parametrize(
    ("distance_expression", "expected_kind", "expected_fixed_distance", "expects_roll"),
    [
        ("D6", "dice", None, True),
        ("6", "fixed", 6.0, False),
    ],
)
def test_catalog_movement_end_reactive_normal_move_bundle_loads_without_manual_binding(
    distance_expression: str,
    expected_kind: str,
    expected_fixed_distance: float | None,
    expects_roll: bool,
) -> None:
    source_army, triggering_army = _mustered_core_armies()
    source_unit = source_army.units[0]
    rule_ir = compile_rule_source_text(
        RuleSourceText.from_raw(
            source_id=f"test:movement-end-reactive-normal-move:bundle:{expected_kind}",
            raw_text=(
                "In your opponent's Movement phase, if an enemy unit ends a move within 8\" "
                "of this unit, if this unit is not within Engagement Range of one or more "
                "enemy units, this unit can make a Normal move of up to "
                f'{distance_expression}".'
            ),
        ),
        source_keyword_sequence_parts=SOURCE_KEYWORD_SEQUENCE_PARTS,
    ).rule_ir
    record = _ability_record(
        record_id=f"record:movement-end-reactive-normal-move:bundle:{expected_kind}",
        rule_ir=rule_ir,
        trigger_kind=TimingTriggerKind.AFTER_ENEMY_UNIT_ENDS_MOVE,
        datasheet_id=source_unit.datasheet_id,
        phase=BattlePhaseKind.MOVEMENT,
    )
    catalog = ArmyCatalog.phase9a_canonical_content_pack()

    bundle = RuntimeContentBundle.from_contributions(
        activation=RuntimeContentActivation.from_armies(
            armies=(source_army, triggering_army),
            catalog=catalog,
        ),
        armies=(source_army, triggering_army),
        catalog=catalog,
        contributions=(),
        base_ability_records=(record,),
    )

    assert CATALOG_IR_MOVEMENT_END_REACTIVE_NORMAL_MOVE_CONSUMER_ID in {
        binding.hook_id for binding in bundle.movement_end_surge_hook_registry.all_bindings()
    }
    triggering_unit = triggering_army.units[0]
    state = _state_with_battlefield(
        armies=(source_army, triggering_army),
        battlefield=_battlefield_for_units(
            source_army=source_army,
            source_unit=source_unit,
            source_x=10.0,
            target_army=triggering_army,
            target_unit=triggering_unit,
            target_x=22.0,
        ),
        active_player_id=triggering_army.player_id,
        phase=BattlePhase.MOVEMENT,
    )
    decisions = DecisionController()
    trigger_event = decisions.event_log.append(
        "movement_activation_completed",
        {
            "game_id": state.game_id,
            "battle_round": state.battle_round,
            "phase": BattlePhase.MOVEMENT.value,
            "active_player_id": triggering_army.player_id,
            "movement_phase_action": "normal_move",
            "unit_instance_id": triggering_unit.unit_instance_id,
        },
    )

    status = _request_movement_end_surge_if_available(
        state=state,
        decisions=decisions,
        registry=bundle.movement_end_surge_hook_registry,
        ruleset_descriptor=state.runtime_ruleset_descriptor(),
    )

    assert status is not None
    assert status.status_kind is LifecycleStatusKind.WAITING_FOR_DECISION
    request = decisions.queue.peek_next()
    assert request.decision_type == SELECT_TRIGGERED_MOVEMENT_DECISION_TYPE
    assert {option.option_id for option in request.options} == {
        DECLINE_TRIGGERED_MOVEMENT_OPTION_ID,
        f"triggered:{source_unit.unit_instance_id}",
    }
    request_payload = cast(dict[str, JsonValue], request.payload)
    descriptor = cast(dict[str, JsonValue], request_payload["descriptor"])
    assert descriptor["source_rule_id"] == record.definition.source_id
    assert descriptor["movement_kind"] == "triggered"
    assert descriptor["movement_mode"] == "normal"
    assert descriptor["allow_battle_shocked"] is True
    assert descriptor["allow_within_engagement_range"] is False
    assert descriptor["one_per_phase"] is False
    if expected_fixed_distance is None:
        assert 1.0 <= cast(float, descriptor["max_distance_inches"]) <= 6.0
    else:
        assert descriptor["max_distance_inches"] == expected_fixed_distance
    assert sum(event.event_type == "dice_rolled" for event in decisions.event_log.records) == int(
        expects_roll
    )
    triggered_event = next(
        event
        for event in decisions.event_log.records
        if event.event_type == "movement_end_surge_triggered"
    )
    triggered_payload = cast(dict[str, JsonValue], triggered_event.payload)
    assert triggered_payload["trigger_event_id"] == trigger_event.event_id
    assert isinstance(triggered_payload["reaction_group_key"], list)
    distance_resolution = cast(
        dict[str, JsonValue],
        triggered_payload["distance_resolution"],
    )
    assert distance_resolution["kind"] == expected_kind
    assert distance_resolution["max_distance_inches"] == descriptor["max_distance_inches"]
    if expects_roll:
        assert isinstance(distance_resolution["roll_state"], dict)
        assert isinstance(triggered_payload["surge_distance_roll"], dict)
    else:
        assert distance_resolution["roll_state"] is None
        assert triggered_payload["surge_distance_roll"] is None
    grants_payload = cast(list[JsonValue], triggered_payload["grants"])
    grant_payload = cast(dict[str, JsonValue], grants_payload[0])
    distance_spec = cast(dict[str, JsonValue], grant_payload["distance_spec"])
    assert distance_spec["kind"] == expected_kind
    assert distance_spec["fixed_distance_inches"] == expected_fixed_distance


def test_movement_end_surge_distance_spec_rejects_mixed_fixed_and_dice_semantics() -> None:
    with pytest.raises(
        GameLifecycleError,
        match="must not include a dice expression",
    ):
        MovementEndSurgeDistanceSpec(
            kind=MovementEndSurgeDistanceKind.FIXED,
            fixed_distance_inches=6.0,
            dice_expression=DiceExpression(quantity=1, sides=6),
        )

    with pytest.raises(GameLifecycleError, match="must not include a distance bonus"):
        MovementEndSurgeGrant(
            hook_id="test:fixed-distance",
            source_id="test:fixed-distance",
            unit_instance_id="test-unit",
            distance_spec=MovementEndSurgeDistanceSpec.fixed(6.0),
            max_distance_bonus_inches=1,
        )


def test_movement_end_reactive_units_have_independent_processed_windows() -> None:
    grants = tuple(
        MovementEndSurgeGrant(
            hook_id=CATALOG_IR_MOVEMENT_END_REACTIVE_NORMAL_MOVE_CONSUMER_ID,
            source_id=CATALOG_IR_MOVEMENT_END_REACTIVE_NORMAL_MOVE_CONSUMER_ID,
            unit_instance_id=unit_instance_id,
            distance_spec=MovementEndSurgeDistanceSpec.dice(quantity=1, sides=6),
            descriptor_source_rule_id="source:aeldari:rangers:path-of-the-outcast",
            movement_kind=TriggeredMovementKind.TRIGGERED,
            allow_battle_shocked=True,
            one_per_phase=False,
            independent_unit_reaction=True,
        )
        for unit_instance_id in ("rangers-alpha", "rangers-beta")
    )

    groups = _movement_end_surge_grant_groups(grants)

    assert tuple(group[0].unit_instance_id for group in groups) == (
        "rangers-alpha",
        "rangers-beta",
    )
    decisions = DecisionController()
    trigger_event_id = "event:enemy-move"
    first_group_key = _movement_end_surge_reaction_group_key(groups[0])
    second_group_key = _movement_end_surge_reaction_group_key(groups[1])
    decisions.event_log.append(
        "movement_end_surge_triggered",
        {
            "trigger_event_id": trigger_event_id,
            "reaction_group_key": list(first_group_key),
        },
    )
    assert _movement_end_surge_event_already_processed(
        decisions=decisions,
        trigger_event_id=trigger_event_id,
        reaction_group_key=first_group_key,
    )
    assert not _movement_end_surge_event_already_processed(
        decisions=decisions,
        trigger_event_id=trigger_event_id,
        reaction_group_key=second_group_key,
    )


def _mustered_core_armies() -> tuple[ArmyDefinition, ArmyDefinition]:
    catalog = ArmyCatalog.phase9a_canonical_content_pack()
    return (
        muster_army(
            catalog=catalog,
            request=_muster_request(catalog=catalog, player_id="player-a", army_id="army-alpha"),
        ),
        muster_army(
            catalog=catalog,
            request=_muster_request(catalog=catalog, player_id="player-b", army_id="army-beta"),
        ),
    )


def _mustered_once_per_battle_armies() -> tuple[ArmyDefinition, ArmyDefinition]:
    catalog = ArmyCatalog.phase9a_canonical_content_pack()
    source_request = replace(
        _muster_request(catalog=catalog, player_id="player-a", army_id="army-alpha"),
        unit_selections=(
            UnitMusterSelection(
                unit_selection_id="army-alpha-character",
                datasheet_id="core-character-leader",
                model_profile_selections=(
                    ModelProfileSelection(
                        model_profile_id="core-character-leader",
                        model_count=1,
                    ),
                ),
            ),
        ),
    )
    return (
        muster_army(catalog=catalog, request=source_request),
        muster_army(
            catalog=catalog,
            request=_muster_request(
                catalog=catalog,
                player_id="player-b",
                army_id="army-beta",
            ),
        ),
    )


def _mustered_attached_once_per_battle_armies() -> tuple[ArmyDefinition, ArmyDefinition]:
    catalog = ArmyCatalog.phase9a_canonical_content_pack()
    source_request = replace(
        _muster_request(catalog=catalog, player_id="player-a", army_id="army-alpha"),
        unit_selections=(
            UnitMusterSelection(
                unit_selection_id="bodyguard",
                datasheet_id="core-intercessor-like-infantry",
                model_profile_selections=(
                    ModelProfileSelection(
                        model_profile_id="core-intercessor-like",
                        model_count=5,
                    ),
                ),
            ),
            UnitMusterSelection(
                unit_selection_id="leader",
                datasheet_id="core-character-leader",
                model_profile_selections=(
                    ModelProfileSelection(
                        model_profile_id="core-character-leader",
                        model_count=1,
                    ),
                ),
            ),
        ),
        attachment_declarations=(
            AttachmentDeclaration(
                source_unit_selection_id="leader",
                bodyguard_unit_selection_id="bodyguard",
            ),
        ),
    )
    return (
        muster_army(catalog=catalog, request=source_request),
        muster_army(
            catalog=catalog,
            request=_muster_request(
                catalog=catalog,
                player_id="player-b",
                army_id="army-beta",
            ),
        ),
    )


def _muster_request(
    *,
    catalog: ArmyCatalog,
    player_id: str,
    army_id: str,
) -> ArmyMusterRequest:
    return ArmyMusterRequest(
        army_id=army_id,
        player_id=player_id,
        catalog_id=catalog.catalog_id,
        source_package_id=catalog.source_package_id,
        ruleset_id=catalog.ruleset_id,
        detachment_selection=DetachmentSelection(
            faction_id="core-marine-force",
            detachment_ids=("core-combined-arms",),
        ),
        force_disposition_id="purge-the-foe",
        unit_selections=(
            UnitMusterSelection(
                unit_selection_id=f"{army_id}-unit",
                datasheet_id="core-intercessor-like-infantry",
                model_profile_selections=(
                    ModelProfileSelection(
                        model_profile_id="core-intercessor-like",
                        model_count=5,
                    ),
                ),
            ),
        ),
    )


def _battlefield_for_units(
    *,
    source_army: ArmyDefinition,
    source_unit: UnitInstance,
    source_x: float,
    target_army: ArmyDefinition,
    target_unit: UnitInstance,
    target_x: float,
) -> BattlefieldRuntimeState:
    return _battlefield_for_units_with_model_xs(
        source_army=source_army,
        source_unit=source_unit,
        source_model_xs=_model_xs_for_unit(unit=source_unit, start_x=source_x),
        target_army=target_army,
        target_unit=target_unit,
        target_model_xs=_model_xs_for_unit(unit=target_unit, start_x=target_x),
    )


def _battlefield_for_units_with_model_xs(
    *,
    source_army: ArmyDefinition,
    source_unit: UnitInstance,
    source_model_xs: tuple[float, ...],
    target_army: ArmyDefinition,
    target_unit: UnitInstance,
    target_model_xs: tuple[float, ...],
) -> BattlefieldRuntimeState:
    return BattlefieldRuntimeState(
        battlefield_id="catalog-runtime-consumers-battlefield",
        battlefield_width_inches=60.0,
        battlefield_depth_inches=44.0,
        placed_armies=(
            _placed_army(army=source_army, unit=source_unit, model_xs=source_model_xs),
            _placed_army(army=target_army, unit=target_unit, model_xs=target_model_xs),
        ),
    )


def _line_blocking_ruin() -> TerrainFeatureDefinition:
    return TerrainFeatureDefinition(
        feature_id="catalog-selected-target-line-blocker",
        feature_kind=TerrainFeatureKind.RUINS,
        footprint_center_x_inches=15.0,
        footprint_center_y_inches=10.0,
        footprint_width_inches=1.0,
        footprint_depth_inches=20.0,
        rules_footprint_polygon=TerrainDisplayGeometry.axis_aligned_rectangle(
            center_x_inches=15.0,
            center_y_inches=10.0,
            width_inches=1.0,
            depth_inches=20.0,
            display_template_id="catalog-selected-target-line-blocker-rules",
        ).footprint_polygon,
        display_geometry=TerrainDisplayGeometry.axis_aligned_rectangle(
            center_x_inches=15.0,
            center_y_inches=10.0,
            width_inches=1.0,
            depth_inches=20.0,
            display_template_id="catalog-selected-target-line-blocker-display",
        ),
        walls=(
            TerrainWallDefinition(
                wall_id="catalog-selected-target-line-blocking-wall",
                center_x_inches=15.0,
                center_y_inches=10.0,
                bottom_z_inches=0.0,
                width_inches=0.2,
                depth_inches=20.0,
                height_inches=6.0,
            ),
        ),
        floors=(
            TerrainFloorDefinition(
                floor_id="catalog-selected-target-line-blocking-floor",
                center_x_inches=15.0,
                center_y_inches=10.0,
                bottom_z_inches=0.0,
                width_inches=1.0,
                depth_inches=20.0,
                thickness_inches=0.1,
            ),
        ),
        source_id="catalog-selected-target-visibility-test",
    )


def _model_xs_for_unit(*, unit: UnitInstance, start_x: float) -> tuple[float, ...]:
    return tuple(start_x + (index * 2.0) for index, _model in enumerate(unit.own_models))


def _placed_army(
    *,
    army: ArmyDefinition,
    unit: UnitInstance,
    model_xs: tuple[float, ...],
) -> PlacedArmy:
    return PlacedArmy(
        army_id=army.army_id,
        player_id=army.player_id,
        unit_placements=(_unit_placement_for_test(army=army, unit=unit, model_xs=model_xs),),
    )


def _unit_placement_for_test(
    *,
    army: ArmyDefinition,
    unit: UnitInstance,
    model_xs: tuple[float, ...],
) -> UnitPlacement:
    if len(model_xs) != len(unit.own_models):
        raise AssertionError("Test battlefield model positions must match unit models.")
    return UnitPlacement(
        army_id=army.army_id,
        player_id=army.player_id,
        unit_instance_id=unit.unit_instance_id,
        model_placements=tuple(
            ModelPlacement(
                army_id=army.army_id,
                player_id=army.player_id,
                unit_instance_id=unit.unit_instance_id,
                model_instance_id=model.model_instance_id,
                pose=Pose.at(x=model_xs[index], y=10.0),
            )
            for index, model in enumerate(unit.own_models)
        ),
    )


def _state_with_battlefield(
    *,
    armies: tuple[ArmyDefinition, ...],
    battlefield: BattlefieldRuntimeState,
    active_player_id: str,
    phase: BattlePhase,
) -> GameState:
    state = _state_without_battlefield(active_player_id=active_player_id, phase=phase)
    state.player_ids = tuple(army.player_id for army in armies)
    state.turn_order = tuple(army.player_id for army in armies)
    state.army_definitions = list(armies)
    state.battlefield_state = battlefield
    return state


def _state_without_battlefield(
    *,
    active_player_id: str | None,
    phase: BattlePhase,
) -> GameState:
    descriptor = RulesetDescriptor.warhammer_40000_eleventh()
    phases = tuple(descriptor.battle_phase_sequence.phases)
    return GameState(
        game_id="catalog-runtime-consumers-game",
        ruleset_descriptor_hash=descriptor.descriptor_hash,
        stage=GameLifecycleStage.BATTLE,
        setup_sequence=tuple(descriptor.setup_sequence.steps),
        battle_phase_sequence=phases,
        setup_step_index=None,
        battle_phase_index=phases.index(phase),
        battle_round=1,
        active_player_id=active_player_id,
        player_ids=("player-a", "player-b"),
        turn_order=("player-a", "player-b"),
        tactical_secondary_draw_count=2,
    )


def _army_with_unit(army: ArmyDefinition, unit: UnitInstance) -> ArmyDefinition:
    return replace(army, units=(unit,))


def _unit_with_dead_model(unit: UnitInstance, *, index: int) -> UnitInstance:
    models = list(unit.own_models)
    model = models[index]
    models[index] = replace(model, wounds_remaining=0)
    return replace(unit, own_models=tuple(models))
