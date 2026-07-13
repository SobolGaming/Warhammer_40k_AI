from __future__ import annotations

import json
import math
from dataclasses import replace
from datetime import date
from functools import lru_cache
from pathlib import Path
from typing import Any, cast

import pytest
from tools.generate_ability_support_matrix import (
    BLOODLETTERS_HEIGHT_OVERRIDES,
    DATASHEET_SUPPORT_OVERALL_VALUES,
    MUSTERING_SUPPORT_STAGE_VALUES,
    ability_support_matrix_rows,
    datasheet_support_rows,
    datasheet_support_rows_payload,
    faction_support_markdown_files,
    leader_attachment_consumer_evidence_datasheet_ids,
    mustering_support_rows,
    mustering_support_rows_payload,
    runtime_content_semantic_coverage_payload,
    support_matrix_markdown,
)

from warhammer40k_core.adapters.local_session import LocalGameSession
from warhammer40k_core.core.army_catalog import ArmyCatalog
from warhammer40k_core.core.attachment_eligibility import AttachmentRole
from warhammer40k_core.core.attributes import Characteristic, CharacteristicValue
from warhammer40k_core.core.datasheet import (
    MUSTERING_WARLORD_FORBIDDEN,
    MUSTERING_WARLORD_REQUIRED,
    MUSTERING_WARLORD_RULE_KEY,
    BaseSizeKind,
    CatalogAbilitySourceKind,
    CatalogAbilitySupport,
    DamagedEffectKind,
    DamagedWeaponScope,
    DatasheetDefinition,
    DatasheetMusteringOptionEffectKind,
    DatasheetWargearOption,
    DatasheetWargearOptionEffect,
    WargearOptionConditionKind,
    WargearOptionEffectKind,
)
from warhammer40k_core.core.detachment import DetachmentDefinition
from warhammer40k_core.core.dice import DiceRollResult, RerollComponentSelectionPolicy
from warhammer40k_core.core.model_geometry_catalog import (
    GeometryEvidenceKind,
    GeometryMeasurementKind,
    GeometrySourceUnits,
)
from warhammer40k_core.core.ruleset_descriptor import (
    BattlePhaseKind,
    CoverEffect,
    CoverPolicyDescriptor,
    RulesetDescriptor,
)
from warhammer40k_core.core.weapon_profiles import (
    AbilityDescriptor,
    AbilityKind,
    AntiKeywordMatchMode,
    DamageProfile,
    RangeProfile,
    TargetKeywordMatchMode,
    WeaponKeyword,
    WeaponProfile,
)
from warhammer40k_core.engine import army_mustering
from warhammer40k_core.engine import cult_ambush as genestealer_cults_cult_ambush
from warhammer40k_core.engine.abilities import (
    GENERIC_RULE_IR_ABILITY_HANDLER_ID,
    AbilityCatalogIndex,
    AbilityCatalogRecord,
    AbilityDefinition,
    AbilityExecutionContext,
    AbilityResolutionStatus,
    AbilitySourceKind,
    AbilityTimingDescriptor,
    default_ability_handler_registry,
)
from warhammer40k_core.engine.ability_catalog import (
    build_player_ability_index,
    catalog_ability_records_from_catalog,
)
from warhammer40k_core.engine.ability_coverage import (
    CORE_STEALTH_RUNTIME_CONSUMER_ID,
    SUPREME_COMMANDER_MUSTERING_CONSUMER_ID,
    WARLORD_RESTRICTION_MUSTERING_CONSUMER_ID,
    AbilityCoverageAbilityDatasheetPair,
    AbilityCoverageCategoryRow,
    AbilityCoverageRow,
    AbilityCoverageSupportStage,
    ability_coverage_category_rows,
    ability_coverage_category_rows_payload,
    ability_coverage_row_for_descriptor,
    ability_coverage_rows_from_catalog,
    ability_coverage_rows_payload,
)
from warhammer40k_core.engine.advance_eligibility_hooks import (
    AdvanceEligibilityContext,
    AdvanceEligibilityHookRegistry,
)
from warhammer40k_core.engine.army_mustering import ArmyDefinition, ArmyMusterRequest
from warhammer40k_core.engine.attack_sequence import (
    AttackSequence,
    AttackSequenceEvent,
    AttackSequenceStep,
    attack_sequence_hit_roll_spec,
    attack_sequence_wound_roll_spec,
    resolve_attack_sequence_until_blocked,
)
from warhammer40k_core.engine.attack_sequence_completion_hooks import (
    AttackSequenceCompletedContext,
    AttackSequenceCompletedHookRegistry,
    successful_hit_target_unit_ids_for_sequence,
)
from warhammer40k_core.engine.battle_shock import collect_battle_shock_test_requests
from warhammer40k_core.engine.battle_shock_hooks import BattleShockHookRegistry
from warhammer40k_core.engine.battlefield_state import (
    BattlefieldRuntimeState,
    ModelPlacement,
    PlacedArmy,
    UnitPlacement,
)
from warhammer40k_core.engine.catalog_any_phase_once_per_battle import (
    SELECT_CATALOG_ANY_PHASE_ONCE_PER_BATTLE_DECISION_TYPE,
    CatalogAnyPhaseOncePerBattleRuntime,
    apply_any_phase_once_per_battle_result,
    invalid_any_phase_once_per_battle_status,
)
from warhammer40k_core.engine.catalog_command_point_support import (
    CATALOG_IR_COMMAND_POINT_GAIN_CONSUMER_ID,
    CATALOG_IR_STRATAGEM_COST_MODIFIER_CONSUMER_ID,
)
from warhammer40k_core.engine.catalog_datasheet_rule_runtime import CatalogDatasheetRuleRuntime
from warhammer40k_core.engine.catalog_once_per_battle_runtime import CatalogOncePerBattleRuntime
from warhammer40k_core.engine.catalog_rule_consumption import (
    CATALOG_IR_ADVANCE_ROLL_REROLL_CONSUMER_ID,
    CATALOG_IR_BATTLE_SHOCK_FAILED_HEAL_CONSUMER_ID,
    CATALOG_IR_BATTLE_SHOCK_FORCED_TEST_CONSUMER_ID,
    CATALOG_IR_CAN_ADVANCE_AND_CHARGE_CONSUMER_ID,
    CATALOG_IR_CAN_ADVANCE_AND_SHOOT_AND_CHARGE_CONSUMER_ID,
    CATALOG_IR_CAN_BE_PLACED_IN_RESERVES_CONSUMER_ID,
    CATALOG_IR_CAN_FALLBACK_AND_CHARGE_CONSUMER_ID,
    CATALOG_IR_CAN_FALLBACK_AND_SHOOT_CONSUMER_ID,
    CATALOG_IR_CHARGE_ROLL_REROLL_CONSUMER_ID,
    CATALOG_IR_CRITICAL_HIT_VALUE_MODIFIER_CONSUMER_ID,
    CATALOG_IR_CRITICAL_WOUND_VALUE_MODIFIER_CONSUMER_ID,
    CATALOG_IR_DESPERATE_ESCAPE_ROLL_MODIFIER_CONSUMER_ID,
    CATALOG_IR_FEEL_NO_PAIN_ROLL_CONSUMER_ID,
    CATALOG_IR_FEEL_NO_PAIN_SOURCE_CONSUMER_ID,
    CATALOG_IR_FORCE_DESPERATE_ESCAPE_CONSUMER_ID,
    CATALOG_IR_HIT_ROLL_MODIFIER_CONSUMER_ID,
    CATALOG_IR_HIT_ROLL_REROLL_CONSUMER_ID,
    CATALOG_IR_INVULNERABLE_SAVE_ROLL_MODIFIER_CONSUMER_ID,
    CATALOG_IR_NAMED_WEAPON_ABILITY_CHOICE_CONSUMER_ID,
    CATALOG_IR_ONCE_PER_BATTLE_ABILITY_CONSUMER_ID,
    CATALOG_IR_POST_SHOOT_HIT_TARGET_EFFECT_CONSUMER_ID,
    CATALOG_IR_POST_SHOOT_HIT_TARGET_STATUS_CONSUMER_ID,
    CATALOG_IR_SAVE_ROLL_MODIFIER_CONSUMER_ID,
    CATALOG_IR_SHADOW_FORM_CHOICE_CONSUMER_ID,
    CATALOG_IR_SHADOW_OF_CHAOS_AURA_CONSUMER_ID,
    CATALOG_IR_SHOOTING_TARGET_RANGE_RESTRICTION_CONSUMER_ID,
    CATALOG_IR_UNIT_MOVE_COMPLETED_MORTAL_WOUNDS_CONSUMER_ID,
    CATALOG_IR_WEAPON_KEYWORD_GRANT_CONSUMER_ID,
    CATALOG_IR_WOUND_ROLL_MODIFIER_CONSUMER_ID,
    CATALOG_NAMED_WEAPON_ABILITY_CHOICE_EFFECT_KIND,
    CATALOG_NAMED_WEAPON_ABILITY_CHOICE_SELECTED_EVENT,
    CATALOG_POST_SHOOT_HIT_TARGET_STATUS_EFFECT_KIND,
    CATALOG_POST_SHOOT_HIT_TARGET_STATUS_SELECTED_EVENT,
    CATALOG_UNIT_MOVE_COMPLETED_MORTAL_WOUNDS_TARGET_SELECTED_EVENT,
    SELECT_CATALOG_NAMED_WEAPON_ABILITY_CHOICE_SUBMISSION_KIND,
    SELECT_CATALOG_POST_SHOOT_HIT_TARGET_STATUS_DECISION_TYPE,
    SELECT_CATALOG_POST_SHOOT_HIT_TARGET_STATUS_SUBMISSION_KIND,
    SELECT_CATALOG_UNIT_MOVE_COMPLETED_MORTAL_WOUNDS_TARGET_DECISION_TYPE,
    SELECT_CATALOG_UNIT_MOVE_COMPLETED_MORTAL_WOUNDS_TARGET_SUBMISSION_KIND,
    CatalogAdvanceEligibilityRuntime,
    CatalogFallBackEligibilityRuntime,
    CatalogNamedWeaponAbilityChoiceOption,
    CatalogNamedWeaponAbilityChoiceRuntime,
    CatalogPostShootHitTargetStatusRuntime,
    CatalogUnitMoveCompletedMortalWoundsRuntime,
    CatalogWeaponKeywordGrant,
    CatalogWeaponKeywordGrantRuntime,
    _available_catalog_named_weapon_ability_choice_groups,  # pyright: ignore[reportPrivateUsage]
    _available_catalog_post_shoot_hit_target_status_groups,  # pyright: ignore[reportPrivateUsage]
    _catalog_post_shoot_hit_target_status_groups_from_clause,  # pyright: ignore[reportPrivateUsage]
    _catalog_roll_reroll_permission,  # pyright: ignore[reportPrivateUsage]
    _catalog_weapon_keyword_grant_from_effect,  # pyright: ignore[reportPrivateUsage]
    _clause_is_named_weapon_ability_choice,  # pyright: ignore[reportPrivateUsage]
    _clause_is_supported_post_shoot_hit_target_status_denial,  # pyright: ignore[reportPrivateUsage]
    _clause_is_supported_unit_move_completed_mortal_wounds,  # pyright: ignore[reportPrivateUsage]
    _effect_is_named_weapon_ability_choice_option,  # pyright: ignore[reportPrivateUsage]
    _effect_is_roll_reroll_permission,  # pyright: ignore[reportPrivateUsage]
    _effect_is_supported_status_denial,  # pyright: ignore[reportPrivateUsage]
    _named_weapon_ability_choice_option_from_effect,  # pyright: ignore[reportPrivateUsage]
    _optional_named_weapon_names,  # pyright: ignore[reportPrivateUsage]
    _payload_object,  # pyright: ignore[reportPrivateUsage]
    _payload_string,  # pyright: ignore[reportPrivateUsage]
    _payload_string_tuple,  # pyright: ignore[reportPrivateUsage]
    _post_shoot_hit_target_status_attack_sequence_from_payload,  # pyright: ignore[reportPrivateUsage]
    _post_shoot_hit_target_status_option_id,  # pyright: ignore[reportPrivateUsage]
    _post_shoot_hit_target_status_selected_payload,  # pyright: ignore[reportPrivateUsage]
    _post_shoot_status_source_model_ids,  # pyright: ignore[reportPrivateUsage]
    _profile_with_catalog_weapon_keyword_grant,  # pyright: ignore[reportPrivateUsage]
    _record_can_select_catalog_named_weapon_ability,  # pyright: ignore[reportPrivateUsage]
    _record_can_select_catalog_post_shoot_hit_target_status,  # pyright: ignore[reportPrivateUsage]
    _record_can_select_catalog_unit_move_completed_mortal_wounds_target,  # pyright: ignore[reportPrivateUsage]
    _roll_reroll_consumer_id_for_effect,  # pyright: ignore[reportPrivateUsage]
    _selected_catalog_named_weapon_ability_grants,  # pyright: ignore[reportPrivateUsage]
    _validate_named_weapon_choice_option,  # pyright: ignore[reportPrivateUsage]
    _validate_named_weapon_choice_target_scope,  # pyright: ignore[reportPrivateUsage]
    _validate_named_weapon_names,  # pyright: ignore[reportPrivateUsage]
    _validate_non_empty_text,  # pyright: ignore[reportPrivateUsage]
    _validate_post_shoot_hit_target_status_option,  # pyright: ignore[reportPrivateUsage]
    _weapon_ability_choice_has_supported_runtime_shape,  # pyright: ignore[reportPrivateUsage]
    _weapon_ability_descriptor_for_grant,  # pyright: ignore[reportPrivateUsage]
    _weapon_ability_descriptor_for_selected_choice_payload,  # pyright: ignore[reportPrivateUsage]
    _weapon_keyword_grant_consumer_ids_for_effect,  # pyright: ignore[reportPrivateUsage]
    _weapon_names_from_parameters,  # pyright: ignore[reportPrivateUsage]
    _weapon_scope_matches_profile,  # pyright: ignore[reportPrivateUsage]
    apply_catalog_post_shoot_hit_target_status_result,
    apply_catalog_unit_move_completed_mortal_wounds_target_result,
    catalog_advance_roll_reroll_permission_for_unit,
    catalog_charge_roll_modifiers_for_unit,
    catalog_charge_roll_reroll_permission_for_unit,
    catalog_rule_ir_consumers_for_rule,
    catalog_rule_ir_hook_ids_for_rule,
    catalog_rule_ir_registered_hook_ids,
    catalog_weapon_keyword_grants_for_unit,
    catalog_weapon_profile_modifier_bindings,
    invalid_catalog_post_shoot_hit_target_status_status,
    invalid_catalog_unit_move_completed_mortal_wounds_target_status,
    record_catalog_feel_no_pain_sources_for_unit,
)
from warhammer40k_core.engine.catalog_selected_target_effects import (
    CATALOG_POST_SHOOT_HIT_TARGET_EFFECT_SELECTED_EVENT,
    SELECT_CATALOG_POST_SHOOT_HIT_TARGET_EFFECT_DECISION_TYPE,
    SELECT_CATALOG_POST_SHOOT_HIT_TARGET_EFFECT_SUBMISSION_KIND,
    CatalogSelectedTargetEffectRuntime,
    apply_catalog_post_shoot_hit_target_effect_result,
    invalid_catalog_post_shoot_hit_target_effect_status,
)
from warhammer40k_core.engine.catalog_turn_end_reserves import (
    CATALOG_TURN_END_RESERVES_USED_EVENT,
    CatalogTurnEndReserveRuntime,
)
from warhammer40k_core.engine.charge_declaration import ChargeRollRequest, ChargeRollResult
from warhammer40k_core.engine.core_stratagem_effects import SMOKESCREEN_EFFECT_KIND
from warhammer40k_core.engine.damage_allocation import FeelNoPainAttackCondition
from warhammer40k_core.engine.decision_controller import DecisionController
from warhammer40k_core.engine.decision_result import DecisionResult
from warhammer40k_core.engine.dice import DiceRollManager
from warhammer40k_core.engine.effects import (
    GENERIC_RULE_EFFECT_KIND,
    EffectExpiration,
    PersistingEffect,
)
from warhammer40k_core.engine.event_log import JsonValue, validate_json_value
from warhammer40k_core.engine.faction_content.activation import RuntimeContentActivation
from warhammer40k_core.engine.faction_content.events import (
    RuntimeContentEvent,
    RuntimeContentEventHandlerRegistry,
    RuntimeContentEventIndex,
)
from warhammer40k_core.engine.faction_content.warhammer_40000_11th.adepta_sororitas import (
    army_rule as adepta_sororitas_army_rule,
)
from warhammer40k_core.engine.faction_content.warhammer_40000_11th.adeptus_custodes import (
    army_rule as adeptus_custodes_army_rule,
)
from warhammer40k_core.engine.faction_content.warhammer_40000_11th.adeptus_mechanicus import (
    army_rule as adeptus_mechanicus_army_rule,
)
from warhammer40k_core.engine.faction_content.warhammer_40000_11th.chaos_space_marines import (
    army_rule as chaos_space_marines_army_rule,
)
from warhammer40k_core.engine.faction_content.warhammer_40000_11th.death_guard import (
    army_rule as death_guard_army_rule,
)
from warhammer40k_core.engine.faction_content.warhammer_40000_11th.emperors_children import (
    army_rule as emperors_children_army_rule,
)
from warhammer40k_core.engine.faction_content.warhammer_40000_11th.imperial_knights import (
    army_rule as imperial_knights_army_rule,
)
from warhammer40k_core.engine.faction_content.warhammer_40000_11th.orks import (
    army_rule as orks_army_rule,
)
from warhammer40k_core.engine.faction_content.warhammer_40000_11th.thousand_sons import (
    army_rule as thousand_sons_army_rule,
)
from warhammer40k_core.engine.faction_content.warhammer_40000_11th.tyranids import (
    army_rule as tyranids_army_rule,
)
from warhammer40k_core.engine.faction_content.warhammer_40000_11th.world_eaters import (
    army_rule as world_eaters_army_rule,
)
from warhammer40k_core.engine.fall_back_hooks import (
    FallBackEligibilityContext,
    FallBackEligibilityHookRegistry,
)
from warhammer40k_core.engine.fight_phase_start_hooks import (
    FightPhaseStartHookRegistry,
    FightPhaseStartRequestContext,
    FightPhaseStartResultContext,
)
from warhammer40k_core.engine.fight_unit_selected_hooks import (
    DECLINE_FIGHT_UNIT_GRANT_OPTION_ID,
    FightUnitSelectedContext,
    FightUnitSelectedGrant,
    FightUnitSelectedGrantRegistry,
    fight_unit_selected_grant_options,
)
from warhammer40k_core.engine.game_state import GameConfig, GameState
from warhammer40k_core.engine.lifecycle import GameLifecycle
from warhammer40k_core.engine.list_validation import (
    DetachmentSelection,
    ListValidationError,
    ModelProfileSelection,
    MusteringOptionSelection,
    UnitMusterSelection,
    WargearSelection,
    resolve_mustering_option_selections,
    resolve_wargear_selections,
)
from warhammer40k_core.engine.phase import (
    BattlePhase,
    GameLifecycleError,
    GameLifecycleStage,
    LifecycleStatus,
    LifecycleStatusKind,
)
from warhammer40k_core.engine.phases.charge import (
    _charge_reroll_permission_for_unit,  # pyright: ignore[reportPrivateUsage]
)
from warhammer40k_core.engine.phases.movement import (
    _ability_index_for_player,
    _advance_reroll_permission_for_unit,
    _validate_ability_index_mapping,
)
from warhammer40k_core.engine.phases.shooting import ShootingPhaseHandler, ShootingPhaseState
from warhammer40k_core.engine.reaction_queue import ReactionQueue
from warhammer40k_core.engine.runtime_modifiers import (
    HitRollModifierContext,
    MovementBudgetModifierContext,
    RuntimeModifierRegistry,
    SaveOptionModifierContext,
    UnitCharacteristicModifierContext,
    WeaponProfileModifierContext,
)
from warhammer40k_core.engine.saves import (
    SaveKind,
    SaveOption,
    SaveResolutionRule,
    saving_throw_roll_spec,
)
from warhammer40k_core.engine.shooting_phase_start_hooks import (
    SELECT_FACTION_RULE_SHOOTING_PHASE_START_OPTION_DECISION_TYPE,
    ShootingPhaseStartHookRegistry,
    ShootingPhaseStartRequestContext,
    ShootingPhaseStartResultContext,
)
from warhammer40k_core.engine.shooting_types import ShootingType
from warhammer40k_core.engine.stratagems import StratagemCatalogIndex
from warhammer40k_core.engine.target_restriction_hooks import (
    ShootingTargetRestrictionContext,
    ShootingTargetRestrictionHookRegistry,
)
from warhammer40k_core.engine.timing_windows import TimingTriggerKind
from warhammer40k_core.engine.turn_end_hooks import (
    SELECT_FACTION_RULE_TURN_END_OPTION_DECISION_TYPE,
    TurnEndHookRegistry,
    TurnEndRequestContext,
    TurnEndResultContext,
)
from warhammer40k_core.engine.unit_factory import ModelInstance, UnitFactory, UnitInstance
from warhammer40k_core.engine.unit_move_completed_hooks import (
    UNIT_MOVE_COMPLETED_MORTAL_WOUNDS_ROLLED_EVENT,
    UnitMoveCompletedContext,
    UnitMoveCompletedMortalWoundHookRegistry,
    resolve_unit_move_completed_mortal_wound_hooks,
)
from warhammer40k_core.engine.unit_state import StartingStrengthRecord
from warhammer40k_core.engine.weapon_declaration import RangedAttackPool
from warhammer40k_core.geometry.pose import Pose
from warhammer40k_core.rules.catalog_generation import build_canonical_catalog_package
from warhammer40k_core.rules.catalog_package import CanonicalCatalogPackage
from warhammer40k_core.rules.data_package import CatalogVersion, DataPackageId
from warhammer40k_core.rules.parsed_tokens import TextSpan
from warhammer40k_core.rules.rule_compiler import compile_rule_source_text
from warhammer40k_core.rules.rule_ir import (
    RuleClause,
    RuleConditionKind,
    RuleDuration,
    RuleDurationKind,
    RuleEffectKind,
    RuleEffectSpec,
    RuleIR,
    RuleIRPayload,
    RuleParameterValue,
    RuleTargetKind,
    RuleTargetSpec,
    RuleTrigger,
    RuleTriggerKind,
    parameter_payload,
    parameters_from_pairs,
)
from warhammer40k_core.rules.source_data import RuleSourceText
from warhammer40k_core.rules.source_packages.warhammer_40000_11th import (
    datasheet_keyword_lexicon_2026_06_14 as datasheet_keyword_lexicon_source,
)
from warhammer40k_core.rules.source_packages.warhammer_40000_11th import (
    faction_detachments_2026_27 as faction_detachment_source,
)
from warhammer40k_core.rules.source_reference_generation import build_source_reference_catalog
from warhammer40k_core.rules.wahapedia_bridge import (
    EVENT_COMPANION_BASE_SIZE_GUIDE_DOCUMENT_REFERENCE,
    EVENT_COMPANION_BASE_SIZE_GUIDE_SOURCE_ID,
    ModelHeightOverride,
    WahapediaBridgeError,
    build_wahapedia_canonical_bridge_artifacts,
)
from warhammer40k_core.rules.wahapedia_datasheet_ability_bridge import (
    bridge_datasheet_abilities,
)
from warhammer40k_core.rules.wahapedia_schema import (
    NormalizedSourceRow,
    WahapediaCsvTable,
    WahapediaJsonArtifact,
    WahapediaJsonArtifactPayload,
)

SOURCE_KEYWORD_SEQUENCE_PARTS = (
    datasheet_keyword_lexicon_source.canonical_datasheet_keyword_sequence_parts()
)

_WAHAPEDIA_10E_JSON = (
    Path(__file__).resolve().parents[2]
    / "data"
    / "source_snapshots"
    / "wahapedia"
    / ("1" + "0" + "th-edition")
    / "2026-06-14"
    / "json"
)
_REQUIRED_TABLES = (
    "Abilities",
    "Datasheets",
    "Datasheets_abilities",
    "Datasheets_keywords",
    "Datasheets_leader",
    "Datasheets_models",
    "Datasheets_models_cost",
    "Datasheets_options",
    "Datasheets_unit_composition",
    "Datasheets_wargear",
    "Factions",
)


def test_phase17k_bloodcrushers_bridge_generates_pdf_corrected_canonical_catalog() -> None:
    package = build_canonical_catalog_package(
        package_id=_catalog_package_id(),
        catalog_version=_catalog_version(),
        source_artifacts=_bloodcrushers_bridge_artifacts(),
    )
    datasheet = package.army_catalog.datasheet_by_id("000001115")
    profiles_by_id = {profile.model_profile_id: profile for profile in datasheet.model_profiles}
    composition_by_id = {part.model_profile_id: part for part in datasheet.composition}
    wargear_by_id = {wargear.wargear_id: wargear for wargear in package.army_catalog.wargear}
    options_by_id = {option.option_id: option for option in datasheet.wargear_options}
    abilities_by_name = {ability.name: ability for ability in datasheet.abilities}

    assert datasheet.name == "Bloodcrushers"
    assert datasheet.keywords.keywords == (
        "BLOODCRUSHERS",
        "CHAOS",
        "DAEMON",
        "KHORNE",
        "MOUNTED",
    )
    assert "SHADOW LEGION" not in datasheet.keywords.keywords
    assert datasheet.keywords.faction_keywords == ("LEGIONES DAEMONICA",)
    assert composition_by_id["000001115:bloodhunter"].min_models == 1
    assert composition_by_id["000001115:bloodhunter"].max_models == 1
    assert composition_by_id["000001115:bloodcrushers"].min_models == 2
    assert composition_by_id["000001115:bloodcrushers"].max_models == 5

    bloodcrusher = profiles_by_id["000001115:bloodcrushers"]
    assert bloodcrusher.base_size.kind is BaseSizeKind.OVAL
    assert math.isclose(bloodcrusher.base_size.length_mm or 0.0, 90.0)
    assert math.isclose(bloodcrusher.base_size.width_mm or 0.0, 52.5)
    assert bloodcrusher.characteristic(Characteristic.MOVEMENT).raw == 10
    assert bloodcrusher.characteristic(Characteristic.TOUGHNESS).raw == 7
    assert bloodcrusher.characteristic(Characteristic.SAVE).raw == 3
    assert bloodcrusher.characteristic(Characteristic.INVULNERABLE_SAVE).raw == 5
    assert bloodcrusher.characteristic(Characteristic.WOUNDS).raw == 4
    assert bloodcrusher.characteristic(Characteristic.LEADERSHIP).raw == 7
    assert bloodcrusher.characteristic(Characteristic.OBJECTIVE_CONTROL).raw == 2
    assert package.model_geometries[0].height.height_inches == 2.75
    footprint_evidence = next(
        evidence
        for evidence in package.model_geometries[0].evidence
        if evidence.measurement_kind is GeometryMeasurementKind.FOOTPRINT
    )
    assert footprint_evidence.source_id.endswith(":base-size:page-65-chaos-daemons-bloodcrushers")
    assert (
        footprint_evidence.document_reference == EVENT_COMPANION_BASE_SIZE_GUIDE_DOCUMENT_REFERENCE
    )
    assert (
        Path(__file__).resolve().parents[2] / EVENT_COMPANION_BASE_SIZE_GUIDE_DOCUMENT_REFERENCE
    ).is_file()
    assert EVENT_COMPANION_BASE_SIZE_GUIDE_SOURCE_ID in bloodcrusher.source_ids
    assert footprint_evidence.source_id in bloodcrusher.source_ids

    assert wargear_by_id["000001115:hellblade"].weapon_profiles[0].attack_profile.fixed_attacks == 2
    horn = wargear_by_id["000001115:juggernauts-bladed-horn"].weapon_profiles[0]
    assert horn.attack_profile.fixed_attacks == 4
    assert tuple(keyword.value for keyword in horn.keywords) == ("Extra Attacks", "Lance")
    assert wargear_by_id["000001115:daemonic-icon"].weapon_profiles == ()
    assert wargear_by_id["000001115:instrument-of-chaos"].weapon_profiles == ()

    instrument_option = options_by_id["000001115:instrument-of-chaos:option-1"]
    assert instrument_option.model_profile_id == "000001115:bloodcrushers"
    assert instrument_option.allowed_wargear_ids == ("000001115:instrument-of-chaos",)
    assert (
        instrument_option.conditions[0].kind is WargearOptionConditionKind.MODEL_NOT_EQUIPPED_WITH
    )
    assert instrument_option.conditions[0].wargear_ids == ("000001115:daemonic-icon",)
    assert instrument_option.effects[0].kind is WargearOptionEffectKind.ADD_WARGEAR
    assert instrument_option.effects[0].wargear_id == "000001115:instrument-of-chaos"

    assert "Deep Strike" in abilities_by_name
    assert abilities_by_name["Deep Strike"].timing_tags == ("deployment", "reserves")
    assert "The Shadow of Chaos" in abilities_by_name
    assert "Brass Stampede" in abilities_by_name
    assert "Daemonic Icon" in abilities_by_name
    assert "Instrument of Chaos" in abilities_by_name
    daemonic_icon = abilities_by_name["Daemonic Icon"]
    instrument = abilities_by_name["Instrument of Chaos"]
    assert daemonic_icon.source_kind is CatalogAbilitySourceKind.WARGEAR
    assert daemonic_icon.source_wargear_id == "000001115:daemonic-icon"
    assert daemonic_icon.support is CatalogAbilitySupport.GENERIC_RULE_IR
    assert instrument.source_kind is CatalogAbilitySourceKind.WARGEAR
    assert instrument.source_wargear_id == "000001115:instrument-of-chaos"
    assert instrument.support is CatalogAbilitySupport.GENERIC_RULE_IR
    icon_ir = RuleIR.from_payload(cast(RuleIRPayload, daemonic_icon.rule_ir_payload))
    instrument_ir = RuleIR.from_payload(cast(RuleIRPayload, instrument.rule_ir_payload))
    icon_effect = icon_ir.clauses[0].effects[0]
    instrument_effect = instrument_ir.clauses[0].effects[0]
    assert icon_ir.clauses[0].target is not None
    assert icon_ir.clauses[0].target.kind.value == "this_unit"
    assert icon_effect.kind is RuleEffectKind.SET_CHARACTERISTIC
    assert parameter_payload(icon_effect.parameters) == {
        "characteristic": "leadership",
        "value": "6+",
    }
    assert instrument_ir.clauses[0].target is not None
    assert instrument_ir.clauses[0].target.kind.value == "this_unit"
    assert instrument_effect.kind is RuleEffectKind.MODIFY_DICE_ROLL
    assert parameter_payload(instrument_effect.parameters) == {
        "delta": 1,
        "roll_type": "charge",
    }
    assert package.to_payload() == type(package).from_payload(package.to_payload()).to_payload()


def test_phase17k_bridged_title_case_keywords_support_exact_runtime_keyword_gate() -> None:
    source_keywords = tuple(
        row.runtime_fields_payload()["keyword"]
        for row in _artifact_by_table(
            _wahapedia_source_artifacts(),
            "Datasheets_keywords",
        ).rows
        if row.runtime_fields_payload()["datasheet_id"] == "000000004"
    )
    assert "Orks" in source_keywords
    assert "Infantry" in source_keywords

    package = build_canonical_catalog_package(
        package_id=_catalog_package_id(),
        catalog_version=_catalog_version(),
        source_artifacts=_weirdboy_bridge_artifacts(),
    )
    datasheet = package.army_catalog.datasheet_by_id("000000004")
    assert datasheet.keywords.faction_keywords == ("ORKS",)
    assert "INFANTRY" in datasheet.keywords.keywords

    unit = UnitFactory(
        catalog=package.army_catalog,
        model_geometries=package.model_geometries,
    ).instantiate_unit(
        army_id="army-orks",
        selection=UnitMusterSelection(
            unit_selection_id="weirdboy-1",
            datasheet_id=datasheet.datasheet_id,
            model_profile_selections=(
                ModelProfileSelection(
                    model_profile_id="000000004:weirdboy",
                    model_count=1,
                ),
            ),
        ),
        datasheet=datasheet,
    )

    assert unit.faction_keywords == ("ORKS",)
    assert "INFANTRY" in unit.keywords
    assert orks_army_rule._unit_has_waaagh(unit)  # pyright: ignore[reportPrivateUsage]


def test_phase17k_bloodthirster_bridge_supports_replacement_wargear_loadouts() -> None:
    package = build_canonical_catalog_package(
        package_id=_catalog_package_id(),
        catalog_version=_catalog_version(),
        source_artifacts=_bloodthirster_bridge_artifacts(),
    )
    datasheet = package.army_catalog.datasheet_by_id("000002582")
    wargear_by_id = {wargear.wargear_id: wargear for wargear in package.army_catalog.wargear}
    options_by_id = {option.option_id: option for option in datasheet.wargear_options}
    model_profile_id = "000002582:bloodthirster"
    hellfire_breath_id = "000002582:hellfire-breath"
    great_axe_id = "000002582:great-axe-of-khorne"
    axe_id = "000002582:axe-of-khorne"
    bloodflail_id = "000002582:bloodflail"
    lash_id = "000002582:lash-of-khorne"
    bloodflail_option_id = "000002582:axe-of-khorne-bloodflail:option-1"
    lash_option_id = "000002582:axe-of-khorne-lash-of-khorne:option-1"

    assert wargear_by_id[great_axe_id].name == "Great axe of Khorne"
    assert tuple(profile.name for profile in wargear_by_id[great_axe_id].weapon_profiles) == (
        "Great axe of Khorne - strike",
        "Great axe of Khorne - sweep",
    )
    assert tuple(profile.name for profile in wargear_by_id[axe_id].weapon_profiles) == (
        "Axe of Khorne - strike",
        "Axe of Khorne - sweep",
    )
    assert _resolved_bloodthirster_model_wargear(package, requested_selections=()) == (
        hellfire_breath_id,
        great_axe_id,
    )

    bloodflail_option = options_by_id[bloodflail_option_id]
    lash_option = options_by_id[lash_option_id]
    assert bloodflail_option.default_wargear_ids == ()
    assert bloodflail_option.allowed_wargear_ids == (axe_id, bloodflail_id)
    assert bloodflail_option.max_selections == 2
    assert bloodflail_option.effects[0].kind is WargearOptionEffectKind.REPLACE_WARGEAR
    assert bloodflail_option.effects[0].wargear_id == axe_id
    assert bloodflail_option.effects[0].replaced_wargear_id == great_axe_id
    assert bloodflail_option.effects[1].kind is WargearOptionEffectKind.ADD_WARGEAR
    assert bloodflail_option.effects[1].wargear_id == bloodflail_id
    assert (
        bloodflail_option.conditions[0].kind is WargearOptionConditionKind.MODEL_NOT_EQUIPPED_WITH
    )
    assert bloodflail_option.conditions[0].wargear_ids == (lash_id,)

    assert _resolved_bloodthirster_model_wargear(
        package,
        requested_selections=(
            WargearSelection(
                option_id=bloodflail_option_id,
                model_profile_id=model_profile_id,
                wargear_ids=(axe_id, bloodflail_id),
            ),
        ),
    ) == (hellfire_breath_id, axe_id, bloodflail_id)
    assert _resolved_bloodthirster_model_wargear(
        package,
        requested_selections=(
            WargearSelection(
                option_id=lash_option_id,
                model_profile_id=model_profile_id,
                wargear_ids=(axe_id, lash_id),
            ),
        ),
    ) == (hellfire_breath_id, axe_id, lash_id)

    with pytest.raises(ListValidationError, match="replacement count"):
        resolve_wargear_selections(
            catalog=package.army_catalog,
            datasheet=datasheet,
            requested_selections=(
                WargearSelection(
                    option_id=bloodflail_option_id,
                    model_profile_id=model_profile_id,
                    wargear_ids=(bloodflail_id,),
                ),
            ),
        )
    with pytest.raises(ListValidationError, match="structured wargear option condition"):
        resolve_wargear_selections(
            catalog=package.army_catalog,
            datasheet=datasheet,
            requested_selections=(
                WargearSelection(
                    option_id=bloodflail_option_id,
                    model_profile_id=model_profile_id,
                    wargear_ids=(axe_id, bloodflail_id),
                ),
                WargearSelection(
                    option_id=lash_option_id,
                    model_profile_id=model_profile_id,
                    wargear_ids=(axe_id, lash_id),
                ),
            ),
        )
    assert lash_option.allowed_wargear_ids == (axe_id, lash_id)


def test_phase17k_great_unclean_one_bridge_supports_single_replacement_wargear() -> None:
    package = build_canonical_catalog_package(
        package_id=_catalog_package_id(),
        catalog_version=_catalog_version(),
        source_artifacts=_great_unclean_one_bridge_artifacts(),
    )
    datasheet = package.army_catalog.datasheet_by_id("000001130")
    wargear_by_id = {wargear.wargear_id: wargear for wargear in package.army_catalog.wargear}
    options_by_id = {option.option_id: option for option in datasheet.wargear_options}
    abilities_by_name = {ability.name: ability for ability in datasheet.abilities}
    model_profile_id = "000001130:great-unclean-one"
    plague_flail_id = "000001130:plague-flail"
    putrid_vomit_id = "000001130:putrid-vomit"
    bilesword_id = "000001130:bilesword"
    bileblade_id = "000001130:bileblade"
    doomsday_bell_id = "000001130:doomsday-bell"
    bileblade_option_id = "000001130:bileblade:option-1"
    doomsday_bell_option_id = "000001130:doomsday-bell:option-2"

    assert _resolved_great_unclean_one_model_wargear(package, requested_selections=()) == (
        plague_flail_id,
        putrid_vomit_id,
        bilesword_id,
    )

    bileblade_option = options_by_id[bileblade_option_id]
    doomsday_bell_option = options_by_id[doomsday_bell_option_id]
    assert bileblade_option.default_wargear_ids == ()
    assert bileblade_option.allowed_wargear_ids == (bileblade_id,)
    assert bileblade_option.max_selections == 1
    assert bileblade_option.conditions == ()
    assert bileblade_option.effects[0].kind is WargearOptionEffectKind.REPLACE_WARGEAR
    assert bileblade_option.effects[0].wargear_id == bileblade_id
    assert bileblade_option.effects[0].replaced_wargear_id == plague_flail_id
    assert doomsday_bell_option.effects[0].kind is WargearOptionEffectKind.REPLACE_WARGEAR
    assert doomsday_bell_option.effects[0].wargear_id == doomsday_bell_id
    assert doomsday_bell_option.effects[0].replaced_wargear_id == bilesword_id
    assert wargear_by_id[doomsday_bell_id].weapon_profiles[0].keywords == (
        WeaponKeyword.LETHAL_HITS,
    )
    assert "000001130:reverberating-summons" not in wargear_by_id
    reverberating_summons = abilities_by_name["Reverberating Summons"]
    assert reverberating_summons.source_kind is CatalogAbilitySourceKind.WARGEAR
    assert reverberating_summons.source_wargear_id == doomsday_bell_id

    assert _resolved_great_unclean_one_model_wargear(
        package,
        requested_selections=(
            WargearSelection(
                option_id=bileblade_option_id,
                model_profile_id=model_profile_id,
                wargear_ids=(bileblade_id,),
            ),
        ),
    ) == (putrid_vomit_id, bilesword_id, bileblade_id)
    assert _resolved_great_unclean_one_model_wargear(
        package,
        requested_selections=(
            WargearSelection(
                option_id=bileblade_option_id,
                model_profile_id=model_profile_id,
                wargear_ids=(bileblade_id,),
            ),
            WargearSelection(
                option_id=doomsday_bell_option_id,
                model_profile_id=model_profile_id,
                wargear_ids=(doomsday_bell_id,),
            ),
        ),
    ) == (putrid_vomit_id, bileblade_id, doomsday_bell_id)
    reverberating_record = AbilityCatalogRecord(
        record_id="phase17k:test:great-unclean-one:reverberating-summons",
        definition=AbilityDefinition(
            ability_id=reverberating_summons.ability_id,
            name=reverberating_summons.name,
            source_id=reverberating_summons.source_id,
            when_descriptor="Catalog bridge wargear profile source test.",
            effect_descriptor=reverberating_summons.effect_description,
            restrictions_descriptor=(
                f"Selected wargear required: {reverberating_summons.source_wargear_id}."
            ),
            timing=AbilityTimingDescriptor(trigger_kind=TimingTriggerKind.ANY_PHASE),
            replay_payload=validate_json_value(
                {
                    "source_wargear_id": reverberating_summons.source_wargear_id,
                }
            ),
        ),
        source_kind=AbilitySourceKind.WARGEAR,
        datasheet_id=datasheet.datasheet_id,
        wargear_id=reverberating_summons.source_wargear_id,
    )
    default_unit = _great_unclean_one_unit(package=package, requested_selections=())
    doomsday_bell_unit = _great_unclean_one_unit(
        package=package,
        requested_selections=(
            WargearSelection(
                option_id=doomsday_bell_option_id,
                model_profile_id=model_profile_id,
                wargear_ids=(doomsday_bell_id,),
            ),
        ),
    )
    default_records_by_name = {
        record.definition.name: record
        for record in build_player_ability_index(
            (reverberating_record,),
            army=_flesh_hounds_army(
                package=package,
                unit=default_unit,
                army_id="army-nurgle",
                player_id="player-nurgle-default",
            ),
            catalog=package.army_catalog,
        ).all_records()
    }
    doomsday_records_by_name = {
        record.definition.name: record
        for record in build_player_ability_index(
            (reverberating_record,),
            army=_flesh_hounds_army(
                package=package,
                unit=doomsday_bell_unit,
                army_id="army-nurgle",
                player_id="player-nurgle-doomsday",
            ),
            catalog=package.army_catalog,
        ).all_records()
    }
    assert "Reverberating Summons" not in default_records_by_name
    assert doomsday_records_by_name["Reverberating Summons"].wargear_id == doomsday_bell_id


def test_phase17k_keeper_of_secrets_bridge_supports_required_one_of_wargear() -> None:
    package = build_canonical_catalog_package(
        package_id=_catalog_package_id(),
        catalog_version=_catalog_version(),
        source_artifacts=_keeper_of_secrets_bridge_artifacts(),
    )
    datasheet = package.army_catalog.datasheet_by_id("000001137")
    wargear_by_id = {wargear.wargear_id: wargear for wargear in package.army_catalog.wargear}
    abilities_by_name = {ability.name: ability for ability in datasheet.abilities}
    options_by_id = {option.option_id: option for option in datasheet.wargear_options}
    model_profile_id = "000001137:keeper-of-secrets"
    living_whip_id = "000001137:living-whip"
    ritual_knife_id = "000001137:ritual-knife"
    shining_aegis_id = "000001137:shining-aegis"
    option_id = "000001137:equipment-choice:option-1"

    option = options_by_id[option_id]
    assert option.model_profile_id == model_profile_id
    assert option.default_wargear_ids == ()
    assert option.allowed_wargear_ids == (living_whip_id, ritual_knife_id, shining_aegis_id)
    assert option.min_selections == 1
    assert option.max_selections == 1
    assert option.conditions == ()
    assert tuple(effect.kind for effect in option.effects) == (
        WargearOptionEffectKind.ADD_WARGEAR_IF_SELECTED,
        WargearOptionEffectKind.ADD_WARGEAR_IF_SELECTED,
        WargearOptionEffectKind.ADD_WARGEAR_IF_SELECTED,
    )
    assert tuple(effect.wargear_id for effect in option.effects) == option.allowed_wargear_ids
    assert wargear_by_id[shining_aegis_id].weapon_profiles == ()

    shining_aegis = abilities_by_name["Shining Aegis"]
    assert shining_aegis.source_kind is CatalogAbilitySourceKind.WARGEAR
    assert shining_aegis.source_wargear_id == shining_aegis_id
    assert shining_aegis.support is CatalogAbilitySupport.GENERIC_RULE_IR
    shining_aegis_ir = RuleIR.from_payload(cast(RuleIRPayload, shining_aegis.rule_ir_payload))
    shining_aegis_effect = shining_aegis_ir.clauses[0].effects[0]
    assert shining_aegis_effect.kind is RuleEffectKind.SET_CHARACTERISTIC
    assert parameter_payload(shining_aegis_effect.parameters) == {
        "characteristic": "save",
        "value": "3+",
    }

    assert _resolved_keeper_of_secrets_model_wargear(
        package,
        requested_selections=(
            WargearSelection(
                option_id=option_id,
                model_profile_id=model_profile_id,
                wargear_ids=(living_whip_id,),
            ),
        ),
    ) == (
        "000001137:phantasmagoria",
        "000001137:snapping-claws",
        "000001137:witstealer-sword",
        living_whip_id,
    )
    assert _resolved_keeper_of_secrets_model_wargear(
        package,
        requested_selections=(
            WargearSelection(
                option_id=option_id,
                model_profile_id=model_profile_id,
                wargear_ids=(shining_aegis_id,),
            ),
        ),
    ) == (
        "000001137:phantasmagoria",
        "000001137:snapping-claws",
        "000001137:witstealer-sword",
        shining_aegis_id,
    )

    with pytest.raises(ListValidationError, match="minimum selections"):
        resolve_wargear_selections(
            catalog=package.army_catalog,
            datasheet=datasheet,
            requested_selections=(),
        )
    with pytest.raises(ListValidationError, match="minimum selections"):
        resolve_wargear_selections(
            catalog=package.army_catalog,
            datasheet=datasheet,
            requested_selections=(
                WargearSelection(
                    option_id=option_id,
                    model_profile_id=model_profile_id,
                    wargear_ids=(),
                ),
            ),
        )
    with pytest.raises(ListValidationError, match="exceeds maximum selections"):
        resolve_wargear_selections(
            catalog=package.army_catalog,
            datasheet=datasheet,
            requested_selections=(
                WargearSelection(
                    option_id=option_id,
                    model_profile_id=model_profile_id,
                    wargear_ids=(living_whip_id, ritual_knife_id),
                ),
            ),
        )

    whip_unit = _keeper_of_secrets_unit(
        package=package,
        requested_selections=(
            WargearSelection(
                option_id=option_id,
                model_profile_id=model_profile_id,
                wargear_ids=(living_whip_id,),
            ),
        ),
    )
    aegis_unit = _keeper_of_secrets_unit(
        package=package,
        requested_selections=(
            WargearSelection(
                option_id=option_id,
                model_profile_id=model_profile_id,
                wargear_ids=(shining_aegis_id,),
            ),
        ),
    )
    all_records = catalog_ability_records_from_catalog(package.army_catalog)
    whip_records_by_name = {
        record.definition.name: record
        for record in build_player_ability_index(
            all_records,
            army=_flesh_hounds_army(
                package=package,
                unit=whip_unit,
                army_id="army-slaanesh",
                player_id="player-whip",
            ),
            catalog=package.army_catalog,
        ).all_records()
    }
    aegis_records_by_name = {
        record.definition.name: record
        for record in build_player_ability_index(
            all_records,
            army=_flesh_hounds_army(
                package=package,
                unit=aegis_unit,
                army_id="army-slaanesh",
                player_id="player-aegis",
            ),
            catalog=package.army_catalog,
        ).all_records()
    }

    assert "Shining Aegis" not in whip_records_by_name
    assert aegis_records_by_name["Shining Aegis"].wargear_id == shining_aegis_id
    assert package.to_payload() == type(package).from_payload(package.to_payload()).to_payload()


def test_phase17k_keeper_bridge_rejects_non_single_item_equipment_choice() -> None:
    with pytest.raises(WahapediaBridgeError, match="single-item additive choices"):
        build_wahapedia_canonical_bridge_artifacts(
            source_artifacts=_keeper_of_secrets_non_single_item_choice_source_artifacts(),
            bridge_package_id=_bridge_package_id(),
            datasheet_ids=("000001137",),
            height_overrides=(
                ModelHeightOverride(
                    datasheet_id="000001137",
                    model_name="Keeper of Secrets",
                    height=5.6,
                    height_units=GeometrySourceUnits.INCHES,
                    height_source_id="geometry-review:chaos-daemons:keeper-of-secrets:height",
                    height_document_reference="Chaos Daemons Faction Pack p.90-91",
                ),
            ),
        )


def test_phase17k_kairos_bridge_consumes_both_command_point_abilities_and_height() -> None:
    package = build_canonical_catalog_package(
        package_id=_catalog_package_id(),
        catalog_version=_catalog_version(),
        source_artifacts=_kairos_fateweaver_bridge_artifacts(),
    )
    records_by_name = {
        record.definition.name: record
        for record in catalog_ability_records_from_catalog(package.army_catalog)
    }

    looks_forward = records_by_name["One Head Looks Forward"]
    looks_back = records_by_name["One Head Looks Back (Aura)"]
    looks_forward_payload = cast(dict[str, JsonValue], looks_forward.definition.replay_payload)
    looks_back_payload = cast(dict[str, JsonValue], looks_back.definition.replay_payload)
    looks_forward_ir = RuleIR.from_payload(cast(RuleIRPayload, looks_forward_payload["rule_ir"]))
    looks_back_ir = RuleIR.from_payload(cast(RuleIRPayload, looks_back_payload["rule_ir"]))
    assert looks_forward_ir.is_supported
    assert looks_back_ir.is_supported
    assert catalog_rule_ir_consumers_for_rule(looks_forward_ir) == (
        CATALOG_IR_COMMAND_POINT_GAIN_CONSUMER_ID,
    )
    assert catalog_rule_ir_consumers_for_rule(looks_back_ir) == (
        CATALOG_IR_STRATAGEM_COST_MODIFIER_CONSUMER_ID,
    )

    geometry = package.model_geometries[0]
    assert geometry.model_profile_id == "000001117:kairos-fateweaver-epic-hero"
    assert geometry.height.height_inches == 7.0
    height_evidence = next(
        evidence
        for evidence in geometry.evidence
        if evidence.evidence_id == geometry.height.evidence_id
    )
    assert height_evidence.evidence_kind is GeometryEvidenceKind.CROWD_SOURCED_MEASUREMENT
    assert height_evidence.document_reference == (
        "https://www.adeptusars.com/miniatures/kairos-fateweaver"
    )
    assert package.to_payload() == type(package).from_payload(package.to_payload()).to_payload()


def test_phase17k_soul_grinder_bridge_supports_warpclaw_replacement_wargear() -> None:
    package = build_canonical_catalog_package(
        package_id=_catalog_package_id(),
        catalog_version=_catalog_version(),
        source_artifacts=_soul_grinder_bridge_artifacts(),
    )
    datasheet = package.army_catalog.datasheet_by_id("000001151")
    options_by_id = {option.option_id: option for option in datasheet.wargear_options}
    mustering_options_by_id = {option.option_id: option for option in datasheet.mustering_options}
    model_profile_id = "000001151:soul-grinder"
    harvester_cannon_id = "000001151:harvester-cannon"
    iron_claw_id = "000001151:iron-claw"
    warpsword_id = "000001151:warpsword"
    warpclaw_id = "000001151:warpclaw"
    torrent_id = "000001151:torrent-of-burning-blood"
    scream_id = "000001151:scream-of-despair"
    warpclaw_option_id = "000001151:warpclaw:option-1"
    khorne_allegiance_option_id = "000001151:daemonic-allegiance:khorne"
    slaanesh_allegiance_option_id = "000001151:daemonic-allegiance:slaanesh"

    with pytest.raises(ListValidationError, match="required option group"):
        resolve_mustering_option_selections(datasheet=datasheet, requested_selections=())

    khorne_allegiance = mustering_options_by_id[khorne_allegiance_option_id]
    assert khorne_allegiance.required is True
    assert khorne_allegiance.selection_group_id == "000001151:daemonic-allegiance"
    assert khorne_allegiance.effects[0].kind is DatasheetMusteringOptionEffectKind.ADD_KEYWORD
    assert khorne_allegiance.effects[0].keyword == "KHORNE"
    assert khorne_allegiance.effects[1].kind is DatasheetMusteringOptionEffectKind.ADD_WARGEAR
    assert khorne_allegiance.effects[1].wargear_id == torrent_id

    khorne_unit = _soul_grinder_unit(
        package,
        requested_wargear_selections=(),
        mustering_option_selections=(
            MusteringOptionSelection(option_id=khorne_allegiance_option_id),
        ),
    )
    assert "KHORNE" in khorne_unit.keywords
    assert khorne_unit.own_models[0].wargear_ids == (
        harvester_cannon_id,
        iron_claw_id,
        warpsword_id,
        torrent_id,
    )

    warpclaw_option = options_by_id[warpclaw_option_id]
    assert warpclaw_option.default_wargear_ids == ()
    assert warpclaw_option.allowed_wargear_ids == (warpclaw_id,)
    assert warpclaw_option.max_selections == 1
    assert warpclaw_option.conditions == ()
    assert warpclaw_option.effects[0].kind is WargearOptionEffectKind.REPLACE_WARGEAR
    assert warpclaw_option.effects[0].wargear_id == warpclaw_id
    assert warpclaw_option.effects[0].replaced_wargear_id == warpsword_id

    assert _resolved_soul_grinder_model_wargear(
        package,
        requested_wargear_selections=(
            WargearSelection(
                option_id=warpclaw_option_id,
                model_profile_id=model_profile_id,
                wargear_ids=(warpclaw_id,),
            ),
        ),
        mustering_option_selections=(
            MusteringOptionSelection(option_id=slaanesh_allegiance_option_id),
        ),
    ) == (harvester_cannon_id, iron_claw_id, warpclaw_id, scream_id)


def test_phase17k_player_ability_index_uses_mustering_added_wargear() -> None:
    package = build_canonical_catalog_package(
        package_id=_catalog_package_id(),
        catalog_version=_catalog_version(),
        source_artifacts=_soul_grinder_bridge_artifacts(),
    )
    datasheet = package.army_catalog.datasheet_by_id("000001151")
    torrent_id = "000001151:torrent-of-burning-blood"
    khorne_allegiance_option_id = "000001151:daemonic-allegiance:khorne"
    slaanesh_allegiance_option_id = "000001151:daemonic-allegiance:slaanesh"
    torrent_record = AbilityCatalogRecord(
        record_id="phase17k:test:soul-grinder:torrent-of-burning-blood",
        definition=AbilityDefinition(
            ability_id="phase17k:soul-grinder:torrent-of-burning-blood",
            name="Torrent of Burning Blood Gate",
            source_id="phase17k:test:soul-grinder:torrent-of-burning-blood",
            when_descriptor="Catalog bridge mustering-added wargear source test.",
            effect_descriptor="Synthetic wargear-source ability for mustering-added wargear.",
            restrictions_descriptor=f"Selected wargear required: {torrent_id}.",
            timing=AbilityTimingDescriptor(trigger_kind=TimingTriggerKind.ANY_PHASE),
            replay_payload=validate_json_value({"source_wargear_id": torrent_id}),
        ),
        source_kind=AbilitySourceKind.WARGEAR,
        datasheet_id=datasheet.datasheet_id,
        wargear_id=torrent_id,
    )
    khorne_unit = _soul_grinder_unit(
        package,
        requested_wargear_selections=(),
        mustering_option_selections=(
            MusteringOptionSelection(option_id=khorne_allegiance_option_id),
        ),
    )
    slaanesh_unit = _soul_grinder_unit(
        package,
        requested_wargear_selections=(),
        mustering_option_selections=(
            MusteringOptionSelection(option_id=slaanesh_allegiance_option_id),
        ),
    )

    khorne_records_by_name = {
        record.definition.name: record
        for record in build_player_ability_index(
            (torrent_record,),
            army=_flesh_hounds_army(
                package=package,
                unit=khorne_unit,
                player_id="player-khorne-soul-grinder",
            ),
            catalog=package.army_catalog,
        ).all_records()
    }
    slaanesh_records_by_name = {
        record.definition.name: record
        for record in build_player_ability_index(
            (torrent_record,),
            army=_flesh_hounds_army(
                package=package,
                unit=slaanesh_unit,
                player_id="player-slaanesh-soul-grinder",
            ),
            catalog=package.army_catalog,
        ).all_records()
    }

    assert khorne_records_by_name["Torrent of Burning Blood Gate"].wargear_id == torrent_id
    assert "Torrent of Burning Blood Gate" not in slaanesh_records_by_name


def test_phase17k_runtime_content_activation_uses_mustering_added_wargear() -> None:
    package = build_canonical_catalog_package(
        package_id=_catalog_package_id(),
        catalog_version=_catalog_version(),
        source_artifacts=_soul_grinder_bridge_artifacts(),
    )
    torrent_id = "000001151:torrent-of-burning-blood"
    khorne_unit = _soul_grinder_unit(
        package,
        requested_wargear_selections=(),
        mustering_option_selections=(
            MusteringOptionSelection(option_id="000001151:daemonic-allegiance:khorne"),
        ),
    )
    slaanesh_unit = _soul_grinder_unit(
        package,
        requested_wargear_selections=(),
        mustering_option_selections=(
            MusteringOptionSelection(option_id="000001151:daemonic-allegiance:slaanesh"),
        ),
    )

    khorne_activation = RuntimeContentActivation.from_armies(
        armies=(_flesh_hounds_army(package=package, unit=khorne_unit),),
        catalog=package.army_catalog,
    )
    slaanesh_activation = RuntimeContentActivation.from_armies(
        armies=(_flesh_hounds_army(package=package, unit=slaanesh_unit),),
        catalog=package.army_catalog,
    )

    assert torrent_id in khorne_activation.selected_wargear_ids
    assert torrent_id not in slaanesh_activation.selected_wargear_ids


def test_phase17k_daemon_prince_bridge_supports_daemonic_allegiance_choices() -> None:
    package = build_canonical_catalog_package(
        package_id=_catalog_package_id(),
        catalog_version=_catalog_version(),
        source_artifacts=_daemon_prince_bridge_artifacts(),
    )
    for datasheet_id, model_profile_id in (
        ("000001149", "000001149:daemon-prince-of-chaos"),
        ("000002758", "000002758:daemon-prince-of-chaos-with-wings"),
    ):
        datasheet = package.army_catalog.datasheet_by_id(datasheet_id)
        options_by_id = {option.option_id: option for option in datasheet.mustering_options}
        nurgle_option_id = f"{datasheet_id}:daemonic-allegiance:nurgle"
        tzeentch_option_id = f"{datasheet_id}:daemonic-allegiance:tzeentch"
        abilities_by_name = {ability.name: ability for ability in datasheet.abilities}

        with pytest.raises(ListValidationError, match="required option group"):
            resolve_mustering_option_selections(datasheet=datasheet, requested_selections=())
        assert set(options_by_id) == {
            f"{datasheet_id}:daemonic-allegiance:khorne",
            nurgle_option_id,
            f"{datasheet_id}:daemonic-allegiance:slaanesh",
            tzeentch_option_id,
        }
        nurgle_option = options_by_id[nurgle_option_id]
        assert nurgle_option.selection_group_id == f"{datasheet_id}:daemonic-allegiance"
        assert nurgle_option.model_profile_id == model_profile_id
        assert nurgle_option.required is True
        assert tuple(effect.kind for effect in nurgle_option.effects) == (
            DatasheetMusteringOptionEffectKind.ADD_KEYWORD,
        )
        assert nurgle_option.effects[0].keyword == "NURGLE"
        assert "Daemon Prince of Tzeentch" in abilities_by_name
        assert (
            abilities_by_name["Daemon Prince of Tzeentch"].source_kind
            is CatalogAbilitySourceKind.DATASHEET
        )

        unit = UnitFactory(
            catalog=package.army_catalog,
            model_geometries=package.model_geometries,
        ).instantiate_unit(
            army_id="army-daemons",
            selection=UnitMusterSelection(
                unit_selection_id=f"{datasheet_id}-prince-1",
                datasheet_id=datasheet.datasheet_id,
                model_profile_selections=(
                    ModelProfileSelection(
                        model_profile_id=model_profile_id,
                        model_count=1,
                    ),
                ),
                mustering_option_selections=(
                    MusteringOptionSelection(option_id=tzeentch_option_id),
                ),
            ),
            datasheet=datasheet,
        )
        assert "TZEENTCH" in unit.keywords
        assert unit.mustering_option_selections == (
            MusteringOptionSelection(option_id=tzeentch_option_id),
        )
        assert unit.own_models[0].wargear_ids == (
            f"{datasheet_id}:infernal-cannon",
            f"{datasheet_id}:hellforged-weapons",
        )


def test_phase17k_undivided_daemon_datasheet_rule_ir_is_fully_consumed() -> None:
    package = build_canonical_catalog_package(
        package_id=_catalog_package_id(),
        catalog_version=_catalog_version(),
        source_artifacts=_undivided_daemon_bridge_artifacts(),
    )
    expected_consumers_by_ability_name = {
        "DAEMONIC ALLEGIANCE": ("army-mustering:required-datasheet-option",),
        "Daemon Prince of Khorne": ("catalog-ir:strength-characteristic-modifier",),
        "Daemon Prince of Tzeentch": ("catalog-ir:attacks-characteristic-modifier",),
        "Daemon Prince of Nurgle": ("catalog-ir:toughness-characteristic-modifier",),
        "Daemon Prince of Slaanesh": ("catalog-ir:movement-characteristic-modifier",),
        "Daemonic Lord": ("catalog-ir:conditional-ability:lone-operative",),
        "Prince of Darkness (Aura)": ("catalog-ir:aura-ability:stealth",),
        "Unholy Vigour": (CATALOG_IR_ONCE_PER_BATTLE_ABILITY_CONSUMER_ID,),
        "Malefic Destruction": (CATALOG_IR_ONCE_PER_BATTLE_ABILITY_CONSUMER_ID,),
        "Harbinger of Death": (
            "catalog-ir:fight-selected-weapon-ability-choice",
            CATALOG_IR_WEAPON_KEYWORD_GRANT_CONSUMER_ID,
            "catalog-ir:weapon-keyword-grant:lethal-hits",
            "catalog-ir:weapon-keyword-grant:precision",
            "catalog-ir:weapon-keyword-grant:sustained-hits",
        ),
        "Scuttling Walker": ("catalog-ir:movement-transit-permission",),
    }

    for datasheet_id in ("000001149", "000002758", "000001151"):
        datasheet = package.army_catalog.datasheet_by_id(datasheet_id)
        datasheet_abilities = tuple(
            ability
            for ability in datasheet.abilities
            if ability.source_kind is CatalogAbilitySourceKind.DATASHEET
        )
        assert datasheet_abilities
        for ability in datasheet_abilities:
            assert ability.support is CatalogAbilitySupport.GENERIC_RULE_IR
            assert ability.rule_ir_payload is not None
            rule_ir = RuleIR.from_payload(cast(RuleIRPayload, ability.rule_ir_payload))
            assert rule_ir.is_supported
            assert rule_ir.diagnostics == ()
            assert (
                catalog_rule_ir_consumers_for_rule(rule_ir)
                == (expected_consumers_by_ability_name[ability.name])
            )
            if ability.name == "DAEMONIC ALLEGIANCE":
                parameters = parameter_payload(rule_ir.clauses[0].effects[0].parameters)
                assert set(cast(tuple[str, ...], parameters["selection_option_ids"])) == {
                    option.option_id for option in datasheet.mustering_options
                }


def test_phase17k_daemon_prince_allegiance_modifiers_use_generic_runtime_queries() -> None:
    package = _undivided_daemon_package()

    def runtime_for(allegiance: str) -> tuple[UnitInstance, GameState, RuntimeModifierRegistry]:
        unit = _daemon_prince_unit(
            package=package,
            datasheet_id="000001149",
            allegiance=allegiance,
            unit_selection_id=f"daemon-prince-{allegiance.lower()}",
        )
        army = _flesh_hounds_army(package=package, unit=unit)
        state = _battle_state_with_army(
            army=army,
            battlefield=_bloodcrushers_battlefield_state(army=army, unit=unit),
        )
        catalog_runtime = CatalogDatasheetRuleRuntime(
            {army.player_id: _player_ability_index(package=package, army=army)},
            (army,),
        )
        return (
            unit,
            state,
            RuntimeModifierRegistry.from_bindings(
                unit_characteristic_modifier_bindings=(
                    catalog_runtime.unit_characteristic_modifier_bindings()
                ),
                movement_budget_modifier_bindings=(
                    catalog_runtime.movement_budget_modifier_bindings()
                ),
                weapon_profile_modifier_bindings=(
                    catalog_runtime.weapon_profile_modifier_bindings()
                ),
            ),
        )

    hellforged = _datasheet_weapon_profile(
        package.army_catalog,
        datasheet_id="000001149",
        profile_name="Hellforged weapons - strike",
    )
    infernal_cannon = _datasheet_weapon_profile(
        package.army_catalog,
        datasheet_id="000001149",
        profile_name="Infernal cannon",
    )
    khorne_unit, khorne_state, khorne_registry = runtime_for("KHORNE")
    khorne_context = WeaponProfileModifierContext(
        state=khorne_state,
        source_phase=BattlePhase.FIGHT,
        attacking_unit_instance_id=khorne_unit.unit_instance_id,
        attacker_model_instance_id=khorne_unit.own_models[0].model_instance_id,
        target_unit_instance_id="runtime-target",
        weapon_profile=hellforged,
    )
    assert (
        khorne_registry.modified_weapon_profile(khorne_context).strength.final
        == hellforged.strength.final + 2
    )
    assert (
        khorne_registry.modified_weapon_profile(
            replace(khorne_context, weapon_profile=infernal_cannon)
        ).strength.final
        == infernal_cannon.strength.final
    )
    assert khorne_unit.own_models[0].is_alive
    _set_current_model_wounds(
        khorne_state,
        model_instance_id=khorne_unit.own_models[0].model_instance_id,
        wounds_remaining=0,
    )
    assert (
        khorne_registry.modified_weapon_profile(khorne_context).strength.final
        == hellforged.strength.final
    )

    tzeentch_unit, tzeentch_state, tzeentch_registry = runtime_for("TZEENTCH")
    tzeentch_context = replace(
        khorne_context,
        state=tzeentch_state,
        attacking_unit_instance_id=tzeentch_unit.unit_instance_id,
        attacker_model_instance_id=tzeentch_unit.own_models[0].model_instance_id,
    )
    modified_infernal = tzeentch_registry.modified_weapon_profile(
        replace(tzeentch_context, weapon_profile=infernal_cannon)
    )
    assert modified_infernal.attack_profile.fixed_attacks == (
        (infernal_cannon.attack_profile.fixed_attacks or 0) + 3
    )
    assert (
        tzeentch_registry.modified_weapon_profile(tzeentch_context).attack_profile
        == hellforged.attack_profile
    )

    nurgle_unit, nurgle_state, nurgle_registry = runtime_for("NURGLE")
    base_toughness = _model_characteristic(nurgle_unit, Characteristic.TOUGHNESS)
    assert nurgle_registry.modified_unit_characteristic(
        UnitCharacteristicModifierContext(
            state=nurgle_state,
            unit_instance_id=nurgle_unit.unit_instance_id,
            characteristic=Characteristic.TOUGHNESS,
            base_value=base_toughness,
            current_value=base_toughness,
        )
    ) == (base_toughness + 1)

    slaanesh_unit, slaanesh_state, slaanesh_registry = runtime_for("SLAANESH")
    base_movement = float(_model_characteristic(slaanesh_unit, Characteristic.MOVEMENT))
    slaanesh_context = MovementBudgetModifierContext(
        state=slaanesh_state,
        unit_instance_id=slaanesh_unit.unit_instance_id,
        model_instance_id=slaanesh_unit.own_models[0].model_instance_id,
        base_movement_inches=base_movement,
        current_movement_inches=base_movement,
    )
    assert slaanesh_registry.modified_movement_inches(slaanesh_context) == (base_movement + 2.0)
    assert slaanesh_state.battlefield_state is not None
    slaanesh_state.battlefield_state = slaanesh_state.battlefield_state.with_removed_models(
        (slaanesh_unit.own_models[0].model_instance_id,)
    )
    assert slaanesh_unit.own_models[0].is_alive
    assert slaanesh_registry.modified_movement_inches(slaanesh_context) == base_movement


def test_phase17k_malefic_destruction_persists_generic_scoped_attacks_modifier() -> None:
    package = _undivided_daemon_package()
    unit = _daemon_prince_unit(
        package=package,
        datasheet_id="000002758",
        allegiance="KHORNE",
        unit_selection_id="winged-prince-malefic",
    )
    army = _flesh_hounds_army(package=package, unit=unit)
    state = _battle_state_with_army(
        army=army,
        battlefield=_bloodcrushers_battlefield_state(army=army, unit=unit),
    )
    _set_state_battle_phase(state, BattlePhase.FIGHT)
    decisions = DecisionController()
    runtime = CatalogOncePerBattleRuntime(
        ability_indexes_by_player_id={
            army.player_id: _player_ability_index(package=package, army=army)
        },
        armies=(army,),
    )
    registry = FightPhaseStartHookRegistry.from_bindings(runtime.fight_phase_start_bindings())
    destroyed_state = _battle_state_with_army(
        army=army,
        battlefield=_bloodcrushers_battlefield_state(army=army, unit=unit),
    )
    _set_state_battle_phase(destroyed_state, BattlePhase.FIGHT)
    _set_current_model_wounds(
        destroyed_state,
        model_instance_id=unit.own_models[0].model_instance_id,
        wounds_remaining=0,
    )
    assert unit.own_models[0].is_alive
    assert (
        registry.next_request_for(
            FightPhaseStartRequestContext(
                state=destroyed_state,
                decisions=DecisionController(),
            )
        )
        is None
    )
    request = registry.next_request_for(
        FightPhaseStartRequestContext(state=state, decisions=decisions)
    )
    assert request is not None
    use_option = next(
        option
        for option in request.options
        if cast(dict[str, JsonValue], option.payload)["activate"]
    )
    decisions.request_decision(request)
    result = DecisionResult.for_request(
        result_id="winged-prince-malefic-result",
        request=request,
        selected_option_id=use_option.option_id,
    )
    record = decisions.submit_result(result)
    assert (
        registry.apply_result(
            FightPhaseStartResultContext(
                state=state,
                decisions=decisions,
                request=record.request,
                result=record.result,
            )
        )
        is True
    )
    strike = _datasheet_weapon_profile(
        package.army_catalog,
        datasheet_id="000002758",
        profile_name="Hellforged weapons - strike",
    )
    infernal = _datasheet_weapon_profile(
        package.army_catalog,
        datasheet_id="000002758",
        profile_name="Infernal cannon",
    )
    context = WeaponProfileModifierContext(
        state=state,
        source_phase=BattlePhase.FIGHT,
        attacking_unit_instance_id=unit.unit_instance_id,
        attacker_model_instance_id=unit.own_models[0].model_instance_id,
        target_unit_instance_id="runtime-target",
        weapon_profile=strike,
    )
    modifier_registry = RuntimeModifierRegistry.from_bindings()
    assert modifier_registry.modified_weapon_profile(context).attack_profile.fixed_attacks == (
        (strike.attack_profile.fixed_attacks or 0) + 3
    )
    assert (
        modifier_registry.modified_weapon_profile(
            replace(context, weapon_profile=infernal)
        ).attack_profile
        == infernal.attack_profile
    )


def test_phase17k_harbinger_of_death_requires_generic_finite_weapon_choice() -> None:
    package = _undivided_daemon_package()
    unit = _daemon_prince_unit(
        package=package,
        datasheet_id="000002758",
        allegiance="NURGLE",
        unit_selection_id="winged-prince-harbinger",
    )
    army = _flesh_hounds_army(package=package, unit=unit)
    state = _battle_state_with_army(
        army=army,
        battlefield=_bloodcrushers_battlefield_state(army=army, unit=unit),
    )
    _set_state_battle_phase(state, BattlePhase.FIGHT)
    runtime = CatalogDatasheetRuleRuntime(
        {army.player_id: _player_ability_index(package=package, army=army)},
        (army,),
    )
    grant_registry = FightUnitSelectedGrantRegistry.from_bindings(
        runtime.fight_unit_selected_grant_bindings()
    )
    grant_context = FightUnitSelectedContext(
        state=state,
        player_id=army.player_id,
        battle_round=1,
        unit_instance_id=unit.unit_instance_id,
        fight_type="normal",
        ordering_band="remaining_combats",
        request_id="fight-activation-request",
        result_id="fight-activation-result",
    )
    grants = grant_registry.grants_for(grant_context)
    options = fight_unit_selected_grant_options(
        unit_instance_id=unit.unit_instance_id,
        activation_request_id="fight-activation-request",
        activation_result_id="fight-activation-result",
        grants=grants,
    )
    assert tuple(grant.label for grant in grants) == (
        "Lethal Hits",
        "Precision",
        "Sustained Hits",
    )
    assert all(not grant.decline_allowed for grant in grants)
    assert DECLINE_FIGHT_UNIT_GRANT_OPTION_ID not in {option.option_id for option in options}
    assert len(options) == 3
    optional_grant = replace(
        grants[0],
        hook_id="optional-fight-grant",
        label="Optional fight grant",
        decline_allowed=True,
    )
    combined_options = fight_unit_selected_grant_options(
        unit_instance_id=unit.unit_instance_id,
        activation_request_id="fight-activation-request",
        activation_result_id="fight-activation-result",
        grants=(*grants, optional_grant),
    )
    assert len(combined_options) == 6
    combined = next(option for option in combined_options if ":with:" in option.option_id)
    assert (
        len(
            cast(
                list[JsonValue],
                cast(dict[str, JsonValue], combined.payload)["selected_fight_unit_grants"],
            )
        )
        == 2
    )
    sustained = next(grant for grant in grants if grant.label == "Sustained Hits")
    assert FightUnitSelectedGrant.from_payload(sustained.to_payload()) == sustained
    state.record_persisting_effect(
        PersistingEffect(
            effect_id="harbinger-sustained-hits-effect",
            source_rule_id=sustained.source_id,
            owner_player_id=army.player_id,
            target_unit_instance_ids=(unit.unit_instance_id,),
            started_battle_round=1,
            started_phase=BattlePhaseKind.FIGHT,
            expiration=EffectExpiration.end_phase(
                battle_round=1,
                phase=BattlePhaseKind.FIGHT,
                player_id=army.player_id,
            ),
            effect_payload=sustained.unit_effect_payload,
        )
    )
    strike = _datasheet_weapon_profile(
        package.army_catalog,
        datasheet_id="000002758",
        profile_name="Hellforged weapons - strike",
    )
    infernal = _datasheet_weapon_profile(
        package.army_catalog,
        datasheet_id="000002758",
        profile_name="Infernal cannon",
    )
    context = WeaponProfileModifierContext(
        state=state,
        source_phase=BattlePhase.FIGHT,
        attacking_unit_instance_id=unit.unit_instance_id,
        attacker_model_instance_id=unit.own_models[0].model_instance_id,
        target_unit_instance_id="runtime-target",
        weapon_profile=strike,
    )
    modifier_registry = RuntimeModifierRegistry.from_bindings()
    assert (
        WeaponKeyword.SUSTAINED_HITS in modifier_registry.modified_weapon_profile(context).keywords
    )
    assert (
        WeaponKeyword.SUSTAINED_HITS
        not in modifier_registry.modified_weapon_profile(
            replace(context, weapon_profile=infernal)
        ).keywords
    )
    _set_current_model_wounds(
        state,
        model_instance_id=unit.own_models[0].model_instance_id,
        wounds_remaining=0,
    )
    assert unit.own_models[0].is_alive
    assert grant_registry.grants_for(grant_context) == ()


def test_phase17k_unholy_vigour_any_phase_decision_is_replay_safe_and_runtime_consumed() -> None:
    package = _undivided_daemon_package()
    unit = _daemon_prince_unit(
        package=package,
        datasheet_id="000001149",
        allegiance="NURGLE",
        unit_selection_id="daemon-prince-unholy-vigour",
    )
    army = _flesh_hounds_army(package=package, unit=unit)
    state = _battle_state_with_army(
        army=army,
        battlefield=_bloodcrushers_battlefield_state(army=army, unit=unit),
    )
    _set_state_battle_phase(state, BattlePhase.MOVEMENT)
    decisions = DecisionController()
    runtime = CatalogAnyPhaseOncePerBattleRuntime(
        {army.player_id: _player_ability_index(package=package, army=army)},
        (army,),
    )
    handler_registry = RuntimeContentEventHandlerRegistry.from_bindings(
        runtime.event_handler_bindings()
    )
    event_index = RuntimeContentEventIndex.from_subscriptions(
        runtime.event_subscriptions(),
        handler_registry=handler_registry,
    )
    event = RuntimeContentEvent(
        event_id="unholy-vigour-movement-start",
        game_id=state.game_id,
        player_id=army.player_id,
        battle_round=1,
        trigger_kind=TimingTriggerKind.START_PHASE,
        phase=BattlePhaseKind.MOVEMENT,
        active_player_id=army.player_id,
    )
    event_results = event_index.dispatch(
        event,
        state=state,
        decisions=decisions,
        ruleset_descriptor=RulesetDescriptor.warhammer_40000_eleventh(),
        army_catalog=package.army_catalog,
        runtime_modifier_registry=RuntimeModifierRegistry.from_bindings(),
    )
    request = decisions.queue.peek_next()
    assert len(event_results) == 1
    assert request.decision_type == SELECT_CATALOG_ANY_PHASE_ONCE_PER_BATTLE_DECISION_TYPE
    assert type(request).from_payload(request.to_payload()).to_payload() == request.to_payload()
    use_option = next(
        option
        for option in request.options
        if cast(dict[str, JsonValue], option.payload)["activate"]
    )
    result = DecisionResult.for_request(
        result_id="unholy-vigour-use-result",
        request=request,
        selected_option_id=use_option.option_id,
    )
    malformed = invalid_any_phase_once_per_battle_status(
        state=state,
        decisions=decisions,
        request=request,
        result=replace(result, payload={"activate": True}),
    )
    assert malformed is not None
    assert cast(dict[str, JsonValue], malformed.payload)["field"] == "payload"
    assert decisions.queue.peek_next() == request
    assert state.persisting_effects_for_unit(unit.unit_instance_id) == ()
    state.battle_round = 2
    stale = invalid_any_phase_once_per_battle_status(
        state=state,
        decisions=decisions,
        request=request,
        result=result,
    )
    assert stale is not None
    assert cast(dict[str, JsonValue], stale.payload)["field"] == "battle_round"
    state.battle_round = 1
    assert (
        invalid_any_phase_once_per_battle_status(
            state=state,
            decisions=decisions,
            request=request,
            result=result,
        )
        is None
    )
    record = decisions.submit_result(result)
    apply_any_phase_once_per_battle_result(
        state=state,
        decisions=decisions,
        request=record.request,
        result=record.result,
    )
    assert len(state.persisting_effects_for_unit(unit.unit_instance_id)) == 1
    infernal = _datasheet_weapon_profile(
        package.army_catalog,
        datasheet_id="000001149",
        profile_name="Infernal cannon",
    )
    save_options = RuntimeModifierRegistry.from_bindings().modified_save_options(
        SaveOptionModifierContext(
            state=state,
            target_unit_instance_id=unit.unit_instance_id,
            save_options=(
                SaveOption(
                    save_kind=SaveKind.ARMOUR,
                    target_number=3,
                    characteristic_target_number=3,
                    armor_penetration=0,
                ),
                SaveOption(
                    save_kind=SaveKind.INVULNERABLE,
                    target_number=4,
                    characteristic_target_number=4,
                    armor_penetration=0,
                ),
            ),
            source_phase=BattlePhase.MOVEMENT,
            attacking_unit_instance_id="runtime-attacker",
            attacker_model_instance_id="runtime-attacker-model",
            weapon_profile=infernal,
        )
    )
    assert (
        next(
            option for option in save_options if option.save_kind is SaveKind.INVULNERABLE
        ).target_number
        == 3
    )


def test_phase17k_unholy_vigour_submits_through_local_game_session() -> None:
    package = _undivided_daemon_package()
    catalog = replace(
        package.army_catalog,
        detachments=(
            DetachmentDefinition(
                detachment_id="phase17k-daemons",
                name="Phase 17K Daemons",
                faction_id=package.army_catalog.factions[0].faction_id,
                detachment_point_cost=1,
                unit_datasheet_ids=("000001149", "000002758"),
                force_disposition_ids=("phase17k-force",),
                source_ids=("test:phase17k-daemons",),
            ),
        ),
    )
    source_selection = UnitMusterSelection(
        unit_selection_id="facade-daemon-prince",
        datasheet_id="000001149",
        model_profile_selections=(
            ModelProfileSelection(
                model_profile_id="000001149:daemon-prince-of-chaos", model_count=1
            ),
        ),
        mustering_option_selections=(
            MusteringOptionSelection(option_id="000001149:daemonic-allegiance:nurgle"),
        ),
    )
    enemy_selection = UnitMusterSelection(
        unit_selection_id="facade-winged-prince",
        datasheet_id="000002758",
        model_profile_selections=(
            ModelProfileSelection(
                model_profile_id="000002758:daemon-prince-of-chaos-with-wings",
                model_count=1,
            ),
        ),
        mustering_option_selections=(
            MusteringOptionSelection(option_id="000002758:daemonic-allegiance:khorne"),
        ),
    )
    detachment_selection = DetachmentSelection(
        faction_id=catalog.factions[0].faction_id,
        detachment_ids=("phase17k-daemons",),
    )
    muster_requests = (
        ArmyMusterRequest(
            army_id="army-daemons",
            player_id="player-daemons",
            catalog_id=catalog.catalog_id,
            source_package_id=catalog.source_package_id,
            ruleset_id=catalog.ruleset_id,
            detachment_selection=detachment_selection,
            unit_selections=(source_selection,),
        ),
        ArmyMusterRequest(
            army_id="army-enemy",
            player_id="player-enemy",
            catalog_id=catalog.catalog_id,
            source_package_id=catalog.source_package_id,
            ruleset_id=catalog.ruleset_id,
            detachment_selection=detachment_selection,
            unit_selections=(enemy_selection,),
        ),
    )
    source_army, enemy_army = tuple(
        army_mustering.muster_army(catalog=catalog, request=muster_request)
        for muster_request in muster_requests
    )
    source = source_army.units[0]
    enemy = enemy_army.units[0]
    battlefield = BattlefieldRuntimeState(
        battlefield_id="unholy-vigour-facade",
        battlefield_width_inches=60.0,
        battlefield_depth_inches=44.0,
        placed_armies=(
            PlacedArmy(
                army_id=source_army.army_id,
                player_id=source_army.player_id,
                unit_placements=(_single_model_unit_placement(source_army, source, x=12.0),),
            ),
            PlacedArmy(
                army_id=enemy_army.army_id,
                player_id=enemy_army.player_id,
                unit_placements=(_single_model_unit_placement(enemy_army, enemy, x=30.0),),
            ),
        ),
    )
    state = _battle_state_with_armies(
        armies=(source_army, enemy_army),
        battlefield=battlefield,
        phase=BattlePhase.MOVEMENT,
        active_player_id=source_army.player_id,
    )
    descriptor = RulesetDescriptor.warhammer_40000_eleventh()
    config = GameConfig(
        game_id=state.game_id,
        allow_legacy_non_strict_rosters=True,
        ruleset_descriptor=descriptor,
        army_catalog=catalog,
        army_muster_requests=muster_requests,
        player_ids=(source_army.player_id, enemy_army.player_id),
        turn_order=(source_army.player_id, enemy_army.player_id),
        fixed_secondary_mission_ids=("assassination", "bring_it_down"),
    )
    lifecycle = GameLifecycle.from_payload(
        cast(
            Any,
            {
                "config": config.to_payload(),
                "parameterized_movement_proposals": True,
                "state": state.to_payload(),
                "decisions": DecisionController().to_payload(),
                "reaction_queue": ReactionQueue().to_payload(),
            },
        )
    )
    session = LocalGameSession(lifecycle=lifecycle)
    status = session.advance_until_decision_or_terminal()
    request = status.decision_request
    assert status.status_kind is LifecycleStatusKind.WAITING_FOR_DECISION
    assert request is not None
    assert request.decision_type == SELECT_CATALOG_ANY_PHASE_ONCE_PER_BATTLE_DECISION_TYPE
    assert request.actor_id == source_army.player_id
    actor_view = session.view(viewer_player_id=source_army.player_id)
    opponent_view = session.view(viewer_player_id=enemy_army.player_id)
    assert actor_view["pending_decision"] is not None
    assert opponent_view["pending_decision"] is not None
    assert actor_view["pending_decision"]["decision_type"] == request.decision_type
    assert opponent_view["pending_decision"]["decision_type"] == request.decision_type
    use_option = next(
        option
        for option in request.options
        if cast(dict[str, JsonValue], option.payload)["activate"]
    )
    submitted = session.submit_option(
        request_id=request.request_id,
        option_id=use_option.option_id,
        result_id="unholy-vigour-facade-result",
    )
    assert submitted.status_kind is LifecycleStatusKind.WAITING_FOR_DECISION
    assert lifecycle.state is not None
    assert len(lifecycle.state.persisting_effects_for_unit(source.unit_instance_id)) == 1
    assert len(lifecycle.decision_controller.records) == 1
    assert "object at 0x" not in json.dumps(lifecycle.to_payload(), sort_keys=True)


def test_phase17k_daemonic_lord_and_stealth_aura_use_group_aware_generic_queries() -> None:
    package = _undivided_daemon_package()
    source = _daemon_prince_unit(
        package=package,
        datasheet_id="000001149",
        allegiance="NURGLE",
        unit_selection_id="daemon-prince-aura-source",
    )
    support = _soul_grinder_unit(
        package,
        requested_wargear_selections=(),
        mustering_option_selections=(
            MusteringOptionSelection(option_id="000001151:daemonic-allegiance:khorne"),
        ),
    )
    support = replace(support, keywords=tuple(sorted((*support.keywords, "INFANTRY"))))
    attacker = _daemon_prince_unit(
        package=package,
        datasheet_id="000001149",
        allegiance="TZEENTCH",
        unit_selection_id="daemon-prince-attacker",
        army_id="army-enemy",
    )
    friendly_army = replace(
        _flesh_hounds_army(package=package, unit=source),
        units=(source, support),
    )
    enemy_army = _flesh_hounds_army(
        package=package,
        unit=attacker,
        army_id="army-enemy",
        player_id="player-enemy",
    )

    def battlefield(support_x: float) -> BattlefieldRuntimeState:
        return BattlefieldRuntimeState(
            battlefield_id=f"daemon-prince-aura-{support_x}",
            battlefield_width_inches=60.0,
            battlefield_depth_inches=44.0,
            placed_armies=(
                PlacedArmy(
                    army_id=friendly_army.army_id,
                    player_id=friendly_army.player_id,
                    unit_placements=(
                        _single_model_unit_placement(friendly_army, source, x=12.0),
                        _single_model_unit_placement(friendly_army, support, x=support_x),
                    ),
                ),
                PlacedArmy(
                    army_id=enemy_army.army_id,
                    player_id=enemy_army.player_id,
                    unit_placements=(_single_model_unit_placement(enemy_army, attacker, x=40.0),),
                ),
            ),
        )

    state = _battle_state_with_armies(
        armies=(friendly_army, enemy_army),
        battlefield=battlefield(14.0),
        phase=BattlePhase.SHOOTING,
        active_player_id=enemy_army.player_id,
    )
    runtime = CatalogDatasheetRuleRuntime(
        {
            friendly_army.player_id: _player_ability_index(package=package, army=friendly_army),
            enemy_army.player_id: _player_ability_index(package=package, army=enemy_army),
        },
        (friendly_army, enemy_army),
    )
    infernal = _datasheet_weapon_profile(
        package.army_catalog,
        datasheet_id="000001149",
        profile_name="Infernal cannon",
    )
    hit_registry = RuntimeModifierRegistry.from_bindings(
        hit_roll_modifier_bindings=runtime.hit_roll_modifier_bindings()
    )
    hit_context = HitRollModifierContext(
        state=state,
        attacking_unit_instance_id=attacker.unit_instance_id,
        attacker_model_instance_id=attacker.own_models[0].model_instance_id,
        target_unit_instance_id=source.unit_instance_id,
        weapon_profile=infernal,
        source_phase=BattlePhase.SHOOTING,
    )
    restriction_registry = ShootingTargetRestrictionHookRegistry.from_bindings(
        runtime.shooting_target_restriction_bindings()
    )
    restriction_context = ShootingTargetRestrictionContext(
        state=state,
        player_id=enemy_army.player_id,
        battle_round=1,
        attacking_unit_instance_id=attacker.unit_instance_id,
        attacker_model_instance_id=attacker.own_models[0].model_instance_id,
        target_unit_instance_id=source.unit_instance_id,
        shooting_type=ShootingType.NORMAL,
    )
    assert hit_registry.hit_roll_modifier(hit_context) == -1
    support_hit_context = replace(
        hit_context,
        target_unit_instance_id=support.unit_instance_id,
    )
    assert hit_registry.hit_roll_modifier(support_hit_context) == -1
    assert (
        hit_registry.hit_roll_modifier(
            replace(
                hit_context,
                source_phase=BattlePhase.FIGHT,
                weapon_profile=_datasheet_weapon_profile(
                    package.army_catalog,
                    datasheet_id="000001149",
                    profile_name="Hellforged weapons - strike",
                ),
            )
        )
        == 0
    )
    restrictions = restriction_registry.restrictions_for(restriction_context)
    assert len(restrictions) == 1
    assert restrictions[0].violation_code == "conditional_lone_operative_range"

    state.battlefield_state = battlefield(30.0)
    assert restriction_registry.restrictions_for(restriction_context) == ()
    assert hit_registry.hit_roll_modifier(support_hit_context) == 0

    state.battlefield_state = battlefield(14.0)
    _set_current_model_wounds(
        state,
        model_instance_id=source.own_models[0].model_instance_id,
        wounds_remaining=0,
    )
    assert source.own_models[0].is_alive
    assert hit_registry.hit_roll_modifier(support_hit_context) == 0
    assert restriction_registry.restrictions_for(restriction_context) == ()


def test_phase17k_bridge_rejects_unowned_wargear_profile_ability() -> None:
    with pytest.raises(
        WahapediaBridgeError,
        match="Wargear profile ability must map to exactly one wargear item",
    ):
        build_wahapedia_canonical_bridge_artifacts(
            source_artifacts=_unowned_wargear_profile_ability_source_artifacts(),
            bridge_package_id=_bridge_package_id(),
            datasheet_ids=("test-wargear-profile-owner",),
            height_overrides=(
                ModelHeightOverride(
                    datasheet_id="test-wargear-profile-owner",
                    model_name="Profile Bearer",
                    height=1.0,
                    height_units=GeometrySourceUnits.INCHES,
                    height_source_id="test-source:wargear-profile-owner-height",
                    height_document_reference="test-doc:wargear-profile-owner-height",
                ),
            ),
        )


def test_phase17k_bridge_supports_pdf_declared_no_equipment_and_no_wargear_options() -> None:
    artifacts = _no_equipment_daemon_fortification_bridge_artifacts()
    wargear_rows = _optional_artifact_rows(artifacts, "Datasheets_wargear")
    option_rows = _optional_artifact_rows(artifacts, "Datasheets_options")
    model_rows = _artifact_by_table(artifacts, "Datasheets_models").rows
    model_fields_by_datasheet_id = {
        row.runtime_fields_payload()["datasheet_id"]: row.runtime_fields_payload()
        for row in model_rows
    }

    for datasheet_id in ("000001470", "000001588"):
        assert not any(
            row.runtime_fields_payload()["datasheet_id"] == datasheet_id for row in wargear_rows
        )
        assert not any(
            row.runtime_fields_payload()["datasheet_id"] == datasheet_id for row in option_rows
        )
        assert model_fields_by_datasheet_id[datasheet_id]["base_size"] == "Hull"
    assert model_fields_by_datasheet_id["000001588"]["height"] == "6.5"
    assert (
        model_fields_by_datasheet_id["000001588"]["height_document_reference"]
        == "Reddit r/ChaosDaemons40k community measurement; "
        "Battle Foam BFS-4.5 tray storage evidence"
    )


def test_phase17k_bloodcrushers_runtime_instances_manifest_model_wargear_and_abilities() -> None:
    package = build_canonical_catalog_package(
        package_id=_catalog_package_id(),
        catalog_version=_catalog_version(),
        source_artifacts=_bloodcrushers_bridge_artifacts(),
    )
    datasheet = package.army_catalog.datasheet_by_id("000001115")
    unit = UnitFactory(
        catalog=package.army_catalog,
        model_geometries=package.model_geometries,
    ).instantiate_unit(
        army_id="army-khorne",
        selection=UnitMusterSelection(
            unit_selection_id="bloodcrushers-1",
            datasheet_id=datasheet.datasheet_id,
            model_profile_selections=(
                ModelProfileSelection(
                    model_profile_id="000001115:bloodcrushers",
                    model_count=2,
                ),
                ModelProfileSelection(
                    model_profile_id="000001115:bloodhunter",
                    model_count=1,
                ),
            ),
            wargear_selections=(
                WargearSelection(
                    option_id="000001115:instrument-of-chaos:option-1",
                    model_profile_id="000001115:bloodcrushers",
                    wargear_ids=("000001115:instrument-of-chaos",),
                ),
            ),
        ),
        datasheet=datasheet,
    )

    bloodcrushers = tuple(
        model for model in unit.own_models if model.model_profile_id == "000001115:bloodcrushers"
    )
    bearer = bloodcrushers[0]

    assert tuple(ability.name for ability in unit.datasheet_abilities) == (
        "Brass Stampede",
        "Daemonic Icon",
        "Instrument of Chaos",
        "Deep Strike",
        "The Shadow of Chaos",
    )
    assert all(
        model.characteristic(Characteristic.INVULNERABLE_SAVE).raw == 5 for model in unit.own_models
    )
    assert all(
        {
            "000001115:hellblade",
            "000001115:juggernauts-bladed-horn",
        }.issubset(model.wargear_ids)
        for model in unit.own_models
    )
    assert bearer.wargear_ids == (
        "000001115:hellblade",
        "000001115:juggernauts-bladed-horn",
        "000001115:instrument-of-chaos",
    )
    assert "000001115:instrument-of-chaos" not in bloodcrushers[1].wargear_ids
    assert UnitInstance.from_payload(unit.to_payload()).to_payload() == unit.to_payload()


def test_phase17k_selected_optional_wargear_adds_catalog_ir_ability_record() -> None:
    package = build_canonical_catalog_package(
        package_id=_catalog_package_id(),
        catalog_version=_catalog_version(),
        source_artifacts=_bloodcrushers_bridge_artifacts(),
    )
    datasheet = package.army_catalog.datasheet_by_id("000001115")
    unit = UnitFactory(
        catalog=package.army_catalog,
        model_geometries=package.model_geometries,
    ).instantiate_unit(
        army_id="army-khorne",
        selection=UnitMusterSelection(
            unit_selection_id="bloodcrushers-1",
            datasheet_id=datasheet.datasheet_id,
            model_profile_selections=(
                ModelProfileSelection(
                    model_profile_id="000001115:bloodcrushers",
                    model_count=2,
                ),
                ModelProfileSelection(
                    model_profile_id="000001115:bloodhunter",
                    model_count=1,
                ),
            ),
            wargear_selections=(
                WargearSelection(
                    option_id="000001115:instrument-of-chaos:option-1",
                    model_profile_id="000001115:bloodcrushers",
                    wargear_ids=("000001115:instrument-of-chaos",),
                ),
            ),
        ),
        datasheet=datasheet,
    )
    army = ArmyDefinition(
        army_id="army-khorne",
        player_id="player-khorne",
        catalog_id=package.army_catalog.catalog_id,
        source_package_id=package.army_catalog.source_package_id,
        ruleset_id=package.army_catalog.ruleset_id,
        detachment_selection=DetachmentSelection(
            faction_id=package.army_catalog.factions[0].faction_id,
            detachment_ids=("phase17k-daemons",),
        ),
        units=(unit,),
    )

    all_records = catalog_ability_records_from_catalog(package.army_catalog)
    player_index = build_player_ability_index(
        all_records,
        army=army,
        catalog=package.army_catalog,
    )
    player_records_by_name = {
        record.definition.name: record for record in player_index.all_records()
    }
    result = default_ability_handler_registry().execute(
        record=player_records_by_name["Instrument of Chaos"],
        context=AbilityExecutionContext(
            game_id="phase17k-game",
            player_id="player-khorne",
            battle_round=1,
            phase=None,
            active_player_id="player-khorne",
            trigger_kind=TimingTriggerKind.AFTER_DICE_ROLL,
            source_unit_instance_id=unit.unit_instance_id,
            source_keywords=unit.keywords,
            trigger_payload={"roll_type": "charge"},
        ),
    )

    assert "Instrument of Chaos" in player_records_by_name
    assert "Daemonic Icon" not in player_records_by_name
    assert result.status is AbilityResolutionStatus.APPLIED
    assert isinstance(result.replay_payload, dict)
    rule_execution = result.replay_payload["rule_execution"]
    assert isinstance(rule_execution, dict)
    effect_payloads = rule_execution["effect_payloads"]
    assert isinstance(effect_payloads, list)
    effect_payload = effect_payloads[0]
    assert isinstance(effect_payload, dict)
    assert effect_payload["target_unit_instance_ids"] == [unit.unit_instance_id]


def test_phase17k_instrument_of_chaos_catalog_ir_modifies_charge_roll_result() -> None:
    package = _bloodcrushers_package()
    unit = _bloodcrushers_unit(
        package=package,
        selected_wargear_id="000001115:instrument-of-chaos",
    )
    army = _bloodcrushers_army(package=package, unit=unit)
    player_index = _player_ability_index(package=package, army=army)
    battlefield = _bloodcrushers_battlefield_state(army=army, unit=unit)
    destroyed_bearer_battlefield = battlefield.with_removed_models(
        (
            _model_bearing_wargear(
                unit,
                "000001115:instrument-of-chaos",
            ).model_instance_id,
        )
    )
    records_by_name = {record.definition.name: record for record in player_index.all_records()}

    modifiers = catalog_charge_roll_modifiers_for_unit(
        ability_index=player_index,
        unit=unit,
        current_model_instance_ids=_current_model_ids(
            battlefield=battlefield,
            unit=unit,
        ),
    )
    destroyed_bearer_modifiers = catalog_charge_roll_modifiers_for_unit(
        ability_index=player_index,
        unit=unit,
        current_model_instance_ids=_current_model_ids(
            battlefield=destroyed_bearer_battlefield,
            unit=unit,
        ),
    )
    request = ChargeRollRequest(
        request_id="phase17k-charge-roll",
        game_id="phase17k-game",
        battle_round=1,
        player_id=army.player_id,
        unit_instance_id=unit.unit_instance_id,
        source_decision_request_id="phase17k-charge-selection-request",
        source_decision_result_id="phase17k-charge-selection-result",
        roll_modifiers=modifiers,
    )
    roll_state = DiceRollManager("phase17k-game").roll_fixed(request.spec, [3, 4])
    result = ChargeRollResult.from_roll_state(
        request=request,
        roll_state=roll_state,
        reachable_target_distances_inches={},
    )
    destroyed_bearer_request = ChargeRollRequest(
        request_id="phase17k-charge-roll-destroyed-bearer",
        game_id="phase17k-game",
        battle_round=1,
        player_id=army.player_id,
        unit_instance_id=unit.unit_instance_id,
        source_decision_request_id="phase17k-charge-selection-request",
        source_decision_result_id="phase17k-charge-selection-destroyed-bearer-result",
        roll_modifiers=destroyed_bearer_modifiers,
    )
    destroyed_bearer_roll_state = DiceRollManager("phase17k-game").roll_fixed(
        destroyed_bearer_request.spec,
        [3, 4],
    )
    destroyed_bearer_result = ChargeRollResult.from_roll_state(
        request=destroyed_bearer_request,
        roll_state=destroyed_bearer_roll_state,
        reachable_target_distances_inches={},
    )

    assert records_by_name["Instrument of Chaos"].definition.timing.trigger_kind is (
        TimingTriggerKind.AFTER_DICE_ROLL
    )
    assert len(modifiers) == 1
    assert destroyed_bearer_modifiers == ()
    assert modifiers[0].operand == 1
    assert request.spec.expression.modifier == 1
    assert destroyed_bearer_request.spec.expression.modifier == 0
    assert result.value == 8
    assert destroyed_bearer_result.value == 7
    assert result.to_payload()["request"]["roll_modifiers"][0]["operand"] == 1
    with pytest.raises(GameLifecycleError, match="current model evidence must be a tuple"):
        catalog_charge_roll_modifiers_for_unit(
            ability_index=player_index,
            unit=unit,
            current_model_instance_ids=cast(tuple[str, ...], ["not-a-tuple"]),
        )
    with pytest.raises(GameLifecycleError, match="current model evidence must not be empty"):
        catalog_charge_roll_modifiers_for_unit(
            ability_index=player_index,
            unit=unit,
            current_model_instance_ids=(),
        )
    with pytest.raises(GameLifecycleError, match="current model evidence must not duplicate"):
        catalog_charge_roll_modifiers_for_unit(
            ability_index=player_index,
            unit=unit,
            current_model_instance_ids=(
                unit.own_models[0].model_instance_id,
                unit.own_models[0].model_instance_id,
            ),
        )
    with pytest.raises(GameLifecycleError, match="current model evidence contains unknown"):
        catalog_charge_roll_modifiers_for_unit(
            ability_index=player_index,
            unit=unit,
            current_model_instance_ids=("army-khorne:bloodcrushers-1:model:missing",),
        )
    with pytest.raises(GameLifecycleError, match="requires an AbilityCatalogIndex"):
        catalog_charge_roll_modifiers_for_unit(
            ability_index=cast(AbilityCatalogIndex, object()),
            unit=unit,
            current_model_instance_ids=_current_model_ids(
                battlefield=battlefield,
                unit=unit,
            ),
        )
    with pytest.raises(GameLifecycleError, match="requires a UnitInstance"):
        catalog_charge_roll_modifiers_for_unit(
            ability_index=player_index,
            unit=cast(UnitInstance, object()),
            current_model_instance_ids=_current_model_ids(
                battlefield=battlefield,
                unit=unit,
            ),
        )
    with pytest.raises(GameLifecycleError, match="current model evidence must contain IDs"):
        catalog_charge_roll_modifiers_for_unit(
            ability_index=player_index,
            unit=unit,
            current_model_instance_ids=("",),
        )
    with pytest.raises(GameLifecycleError, match="classification requires RuleIR"):
        catalog_rule_ir_consumers_for_rule(cast(RuleIR, object()))
    with pytest.raises(GameLifecycleError, match="classification requires RuleIR"):
        catalog_rule_ir_hook_ids_for_rule(cast(RuleIR, object()))


def test_phase17k_daemonic_icon_catalog_ir_modifies_battle_shock_leadership() -> None:
    package = _bloodcrushers_package()
    unit = _bloodcrushers_unit(
        package=package,
        selected_wargear_id="000001115:daemonic-icon",
    )
    army = _bloodcrushers_army(package=package, unit=unit)
    player_index = _player_ability_index(package=package, army=army)
    battlefield = _bloodcrushers_battlefield_state(army=army, unit=unit)
    bearer = _model_bearing_wargear(unit, "000001115:daemonic-icon")
    alive_bearer_battlefield = battlefield.with_removed_models(
        tuple(model.model_instance_id for model in unit.own_models if model != bearer)
    )
    destroyed_bearer_battlefield = battlefield.with_removed_models(
        (
            bearer.model_instance_id,
            next(model.model_instance_id for model in unit.own_models if model != bearer),
        )
    )
    records_by_name = {record.definition.name: record for record in player_index.all_records()}
    starting_strength = (StartingStrengthRecord.from_unit(player_id=army.player_id, unit=unit),)

    requests_without_index = collect_battle_shock_test_requests(
        game_id="phase17k-game",
        battle_round=1,
        player_id=army.player_id,
        army=army,
        battlefield_state=alive_bearer_battlefield,
        starting_strength_records=starting_strength,
    )
    alive_bearer_requests_with_index = collect_battle_shock_test_requests(
        game_id="phase17k-game",
        battle_round=1,
        player_id=army.player_id,
        army=army,
        battlefield_state=alive_bearer_battlefield,
        starting_strength_records=starting_strength,
        ability_index=player_index,
    )
    destroyed_bearer_requests_with_index = collect_battle_shock_test_requests(
        game_id="phase17k-game",
        battle_round=1,
        player_id=army.player_id,
        army=army,
        battlefield_state=destroyed_bearer_battlefield,
        starting_strength_records=starting_strength,
        ability_index=player_index,
    )

    assert records_by_name["Daemonic Icon"].definition.timing.trigger_kind is (
        TimingTriggerKind.PASSIVE_QUERY
    )
    assert records_by_name["Daemonic Icon"].definition.name == "Daemonic Icon"
    assert len(requests_without_index) == 1
    assert len(alive_bearer_requests_with_index) == 1
    assert len(destroyed_bearer_requests_with_index) == 1
    assert requests_without_index[0].leadership_target == 7
    assert alive_bearer_requests_with_index[0].leadership_target == 6
    assert destroyed_bearer_requests_with_index[0].leadership_target == 7


def test_phase17k_collar_of_khorne_catalog_ir_records_bearer_psychic_fnp_source() -> None:
    package = _flesh_hounds_package()
    unit = _flesh_hounds_unit(package=package)
    army = _flesh_hounds_army(package=package, unit=unit)
    player_index = _player_ability_index(package=package, army=army)
    battlefield = _bloodcrushers_battlefield_state(army=army, unit=unit)
    bearer = _model_bearing_wargear(unit, "test-flesh-hounds:collar-of-khorne")
    destroyed_bearer_battlefield = battlefield.with_removed_models((bearer.model_instance_id,))
    state = _battle_state_with_army(army=army, battlefield=battlefield)
    destroyed_bearer_state = _battle_state_with_army(
        army=army,
        battlefield=destroyed_bearer_battlefield,
    )
    records_by_name = {record.definition.name: record for record in player_index.all_records()}
    collar_record = records_by_name["Collar of Khorne"]
    replay_payload = collar_record.definition.replay_payload
    assert isinstance(replay_payload, dict)
    collar_rule_ir = RuleIR.from_payload(cast(RuleIRPayload, replay_payload["rule_ir"]))

    recorded_sources = record_catalog_feel_no_pain_sources_for_unit(
        state=state,
        ability_index=player_index,
        unit=unit,
        current_model_instance_ids=_current_model_ids(
            battlefield=battlefield,
            unit=unit,
        ),
    )
    duplicate_recorded_sources = record_catalog_feel_no_pain_sources_for_unit(
        state=state,
        ability_index=player_index,
        unit=unit,
        current_model_instance_ids=_current_model_ids(
            battlefield=battlefield,
            unit=unit,
        ),
    )
    destroyed_bearer_sources = record_catalog_feel_no_pain_sources_for_unit(
        state=destroyed_bearer_state,
        ability_index=player_index,
        unit=unit,
        current_model_instance_ids=_current_model_ids(
            battlefield=destroyed_bearer_battlefield,
            unit=unit,
        ),
    )
    stored_sources = state.feel_no_pain_sources_for_model(
        model_instance_id=bearer.model_instance_id
    )

    assert collar_record.definition.timing.trigger_kind is TimingTriggerKind.PASSIVE_QUERY
    assert catalog_rule_ir_consumers_for_rule(collar_rule_ir) == (
        CATALOG_IR_FEEL_NO_PAIN_SOURCE_CONSUMER_ID,
    )
    assert set(catalog_rule_ir_hook_ids_for_rule(collar_rule_ir)) == {
        CATALOG_IR_FEEL_NO_PAIN_SOURCE_CONSUMER_ID,
    }
    assert recorded_sources == duplicate_recorded_sources
    assert len(recorded_sources) == 1
    assert recorded_sources[0][0] == bearer.model_instance_id
    assert stored_sources == (recorded_sources[0][1],)
    assert stored_sources[0].threshold == 3
    assert stored_sources[0].attack_condition is FeelNoPainAttackCondition.PSYCHIC_ATTACK
    assert stored_sources[0].mortal_wounds is True
    assert all(
        state.feel_no_pain_sources_for_model(model_instance_id=model.model_instance_id) == ()
        for model in unit.own_models
        if model.model_instance_id != bearer.model_instance_id
    )
    assert destroyed_bearer_sources == ()
    assert (
        destroyed_bearer_state.feel_no_pain_sources_for_model(
            model_instance_id=bearer.model_instance_id
        )
        == ()
    )


def test_phase17k_flesh_hounds_hunters_from_the_warp_uses_generic_turn_end_reserves() -> None:
    package = _flesh_hounds_package()
    unit = _flesh_hounds_unit(package=package)
    enemy_unit = _flesh_hounds_unit(
        package=package,
        army_id="army-opponent",
        unit_selection_id="enemy-flesh-hounds-1",
    )
    army = _flesh_hounds_army(package=package, unit=unit)
    enemy_army = _flesh_hounds_army(
        package=package,
        unit=enemy_unit,
        army_id="army-opponent",
        player_id="player-opponent",
    )
    player_index = _player_ability_index(package=package, army=army)
    enemy_index = _player_ability_index(package=package, army=enemy_army)
    records_by_name = {record.definition.name: record for record in player_index.all_records()}
    hunters_record = records_by_name["Hunters from the Warp"]
    replay_payload = hunters_record.definition.replay_payload
    assert isinstance(replay_payload, dict)
    hunters_rule_ir = RuleIR.from_payload(cast(RuleIRPayload, replay_payload["rule_ir"]))
    runtime = CatalogTurnEndReserveRuntime(
        ability_indexes_by_player_id={
            army.player_id: player_index,
            enemy_army.player_id: enemy_index,
        },
        armies=(army, enemy_army),
    )
    registry = TurnEndHookRegistry.from_bindings(runtime.bindings())
    engaged_state = _battle_state_with_armies(
        armies=(army, enemy_army),
        battlefield=_flesh_hounds_battlefield_state(
            army=army,
            unit=unit,
            enemy_army=enemy_army,
            enemy_unit=enemy_unit,
            enemy_x=12.0,
        ),
        active_player_id=enemy_army.player_id,
        phase=BattlePhase.FIGHT,
    )

    assert hunters_record.definition.timing.trigger_kind is TimingTriggerKind.END_TURN
    assert catalog_rule_ir_consumers_for_rule(hunters_rule_ir) == (
        CATALOG_IR_CAN_BE_PLACED_IN_RESERVES_CONSUMER_ID,
    )
    assert set(catalog_rule_ir_hook_ids_for_rule(hunters_rule_ir)) == {
        CATALOG_IR_CAN_BE_PLACED_IN_RESERVES_CONSUMER_ID,
    }
    assert (
        registry.next_request_for(
            TurnEndRequestContext(
                state=engaged_state,
                decisions=DecisionController(),
                completed_phase=BattlePhase.FIGHT,
            )
        )
        is None
    )

    state = _battle_state_with_armies(
        armies=(army, enemy_army),
        battlefield=_flesh_hounds_battlefield_state(
            army=army,
            unit=unit,
            enemy_army=enemy_army,
            enemy_unit=enemy_unit,
            enemy_x=30.0,
        ),
        active_player_id=enemy_army.player_id,
        phase=BattlePhase.FIGHT,
    )
    decisions = DecisionController()
    request = registry.next_request_for(
        TurnEndRequestContext(
            state=state,
            decisions=decisions,
            completed_phase=BattlePhase.FIGHT,
        )
    )
    assert request is not None
    use_option = next(option for option in request.options if option.option_id.endswith(":use"))
    result = DecisionResult.for_request(
        result_id="result-flesh-hounds-hunters-use",
        request=request,
        selected_option_id=use_option.option_id,
    )

    handled = registry.apply_result(
        TurnEndResultContext(
            state=state,
            decisions=decisions,
            request=request,
            result=result,
        )
    )

    reserve_state = state.reserve_state_for_unit(unit.unit_instance_id)
    assert request.decision_type == SELECT_FACTION_RULE_TURN_END_OPTION_DECISION_TYPE
    assert request.actor_id == army.player_id
    assert handled is True
    assert reserve_state is not None
    assert reserve_state.source_rule_ids == (hunters_record.definition.source_id,)
    assert state.battlefield_state is not None
    assert all(
        unit_placement.unit_instance_id != unit.unit_instance_id
        for placed_army in state.battlefield_state.placed_armies
        for unit_placement in placed_army.unit_placements
    )
    used_events = tuple(
        record
        for record in decisions.event_log.records
        if record.event_type == CATALOG_TURN_END_RESERVES_USED_EVENT
    )
    assert len(used_events) == 1


def test_phase17k_datasheet_advance_charge_text_uses_generic_advance_eligibility() -> None:
    package = _advance_charge_package()
    unit = _advance_charge_unit(package=package)
    army = _flesh_hounds_army(package=package, unit=unit)
    player_index = _player_ability_index(package=package, army=army)
    records_by_name = {record.definition.name: record for record in player_index.all_records()}
    advance_charge_record = records_by_name["Bounding Advance"]
    replay_payload = advance_charge_record.definition.replay_payload
    assert isinstance(replay_payload, dict)
    rule_ir = RuleIR.from_payload(cast(RuleIRPayload, replay_payload["rule_ir"]))
    runtime = CatalogAdvanceEligibilityRuntime(
        ability_indexes_by_player_id={army.player_id: player_index},
        armies=(army,),
    )
    registry = AdvanceEligibilityHookRegistry.from_bindings(runtime.bindings())
    state = _battle_state_with_army(
        army=army,
        battlefield=_bloodcrushers_battlefield_state(army=army, unit=unit),
    )

    grants = registry.grants_for(
        AdvanceEligibilityContext(
            state=state,
            player_id=army.player_id,
            battle_round=state.battle_round,
            unit_instance_id=unit.unit_instance_id,
            movement_request_id="phase17k-advance-charge-request",
            movement_result_id="phase17k-advance-charge-result",
        )
    )

    assert advance_charge_record.definition.timing.trigger_kind is TimingTriggerKind.PASSIVE_QUERY
    assert rule_ir.is_supported
    assert catalog_rule_ir_consumers_for_rule(rule_ir) == (
        CATALOG_IR_CAN_ADVANCE_AND_CHARGE_CONSUMER_ID,
    )
    assert set(catalog_rule_ir_hook_ids_for_rule(rule_ir)) == {
        CATALOG_IR_CAN_ADVANCE_AND_CHARGE_CONSUMER_ID,
    }
    assert tuple(binding.hook_id for binding in registry.all_bindings()) == (
        CATALOG_IR_CAN_ADVANCE_AND_CHARGE_CONSUMER_ID,
    )
    assert len(grants) == 1
    assert grants[0].hook_id == CATALOG_IR_CAN_ADVANCE_AND_CHARGE_CONSUMER_ID
    assert grants[0].can_declare_charge is True
    assert grants[0].can_shoot is False
    assert grants[0].replay_payload == {
        "ability": "can_advance_and_charge",
        "ability_ids": [advance_charge_record.definition.ability_id],
        "catalog_record_ids": [advance_charge_record.record_id],
        "source_rule_ids": [advance_charge_record.definition.source_id],
    }


def test_phase17k_datasheet_fall_back_shoot_text_uses_generic_fall_back_eligibility() -> None:
    package = _advance_charge_package()
    unit = _advance_charge_unit(package=package)
    army = _flesh_hounds_army(package=package, unit=unit)
    player_index = _player_ability_index(package=package, army=army)
    records_by_name = {record.definition.name: record for record in player_index.all_records()}
    fall_back_shoot_record = records_by_name["Slip Away"]
    replay_payload = fall_back_shoot_record.definition.replay_payload
    assert isinstance(replay_payload, dict)
    rule_ir = RuleIR.from_payload(cast(RuleIRPayload, replay_payload["rule_ir"]))
    runtime = CatalogFallBackEligibilityRuntime(
        ability_indexes_by_player_id={army.player_id: player_index},
        armies=(army,),
    )
    registry = FallBackEligibilityHookRegistry.from_bindings(runtime.bindings())
    state = _battle_state_with_army(
        army=army,
        battlefield=_bloodcrushers_battlefield_state(army=army, unit=unit),
    )

    grants = registry.grants_for(
        FallBackEligibilityContext(
            state=state,
            player_id=army.player_id,
            battle_round=state.battle_round,
            unit_instance_id=unit.unit_instance_id,
            movement_request_id="phase17k-fall-back-shoot-request",
            movement_result_id="phase17k-fall-back-shoot-result",
        )
    )

    assert fall_back_shoot_record.definition.timing.trigger_kind is TimingTriggerKind.PASSIVE_QUERY
    assert rule_ir.is_supported
    assert catalog_rule_ir_consumers_for_rule(rule_ir) == (
        CATALOG_IR_CAN_FALLBACK_AND_SHOOT_CONSUMER_ID,
    )
    assert set(catalog_rule_ir_hook_ids_for_rule(rule_ir)) == {
        CATALOG_IR_CAN_FALLBACK_AND_SHOOT_CONSUMER_ID,
    }
    assert tuple(binding.hook_id for binding in registry.all_bindings()) == (
        CATALOG_IR_CAN_FALLBACK_AND_SHOOT_CONSUMER_ID,
    )
    assert len(grants) == 1
    assert grants[0].hook_id == CATALOG_IR_CAN_FALLBACK_AND_SHOOT_CONSUMER_ID
    assert grants[0].can_shoot is True
    assert grants[0].can_declare_charge is False
    assert grants[0].replay_payload == {
        "ability": "can_fall_back_and_shoot",
        "ability_ids": [fall_back_shoot_record.definition.ability_id],
        "catalog_record_ids": [fall_back_shoot_record.record_id],
        "source_rule_ids": [fall_back_shoot_record.definition.source_id],
    }


def test_phase17k_fall_back_shoot_runtime_uses_scoped_catalog_clause_record() -> None:
    package = _split_fall_back_package()
    unit = _advance_charge_unit(package=package)
    army = _flesh_hounds_army(package=package, unit=unit)
    player_index = _player_ability_index(package=package, army=army)
    split_records = tuple(
        record
        for record in player_index.all_records()
        if record.definition.name == "Split Slip Away"
    )
    unrelated_record = _record_by_runtime_clause_suffix(split_records, suffix=":clause:001")
    fall_back_record = _record_by_runtime_clause_suffix(split_records, suffix=":clause:002")
    runtime = CatalogFallBackEligibilityRuntime(
        ability_indexes_by_player_id={army.player_id: player_index},
        armies=(army,),
    )
    registry = FallBackEligibilityHookRegistry.from_bindings(runtime.bindings())
    state = _battle_state_with_army(
        army=army,
        battlefield=_bloodcrushers_battlefield_state(army=army, unit=unit),
    )

    grants = registry.grants_for(
        FallBackEligibilityContext(
            state=state,
            player_id=army.player_id,
            battle_round=state.battle_round,
            unit_instance_id=unit.unit_instance_id,
            movement_request_id="phase17k-split-fall-back-shoot-request",
            movement_result_id="phase17k-split-fall-back-shoot-result",
        )
    )

    assert len(split_records) == 2
    assert unrelated_record.definition.timing.trigger_kind is TimingTriggerKind.PASSIVE_QUERY
    assert fall_back_record.definition.timing.trigger_kind is TimingTriggerKind.PASSIVE_QUERY
    assert len(grants) == 1
    assert grants[0].hook_id == CATALOG_IR_CAN_FALLBACK_AND_SHOOT_CONSUMER_ID
    grant_payload = grants[0].replay_payload
    assert isinstance(grant_payload, dict)
    catalog_record_ids = grant_payload["catalog_record_ids"]
    assert isinstance(catalog_record_ids, list)
    assert catalog_record_ids == [fall_back_record.record_id]
    assert unrelated_record.record_id not in catalog_record_ids


def test_phase17k_leading_model_reroll_text_uses_generic_advance_charge_rerolls() -> None:
    package = _advance_charge_package()
    unit = _advance_charge_unit(package=package)
    army = _flesh_hounds_army(package=package, unit=unit)
    player_index = _player_ability_index(package=package, army=army)
    records_by_name = {record.definition.name: record for record in player_index.all_records()}
    reroll_record = records_by_name["Lead the Hunt"]
    replay_payload = reroll_record.definition.replay_payload
    assert isinstance(replay_payload, dict)
    rule_ir = RuleIR.from_payload(cast(RuleIRPayload, replay_payload["rule_ir"]))
    battlefield = _bloodcrushers_battlefield_state(army=army, unit=unit)
    state = _battle_state_with_army(army=army, battlefield=battlefield)
    current_model_ids = _current_model_ids(battlefield=battlefield, unit=unit)
    advance_permission = catalog_advance_roll_reroll_permission_for_unit(
        ability_index=player_index,
        unit=unit,
        current_model_instance_ids=current_model_ids,
        player_id=army.player_id,
    )
    charge_permission = catalog_charge_roll_reroll_permission_for_unit(
        ability_index=player_index,
        unit=unit,
        current_model_instance_ids=current_model_ids,
        player_id=army.player_id,
    )
    advance_phase_permission = _advance_reroll_permission_for_unit(
        state=state,
        unit=unit,
        unit_instance_id=unit.unit_instance_id,
        player_id=army.player_id,
        keywords=unit.keywords,
        ability_index=player_index,
        current_model_instance_ids=current_model_ids,
    )
    charge_phase_permission = _charge_reroll_permission_for_unit(
        state=state,
        player_id=army.player_id,
        unit_instance_id=unit.unit_instance_id,
        ability_index=player_index,
    )
    keyword_permission = _advance_reroll_permission_for_unit(
        state=state,
        unit=unit,
        unit_instance_id=unit.unit_instance_id,
        player_id=army.player_id,
        keywords=("ADVANCE_REROLL",),
        ability_index=AbilityCatalogIndex.from_records(()),
        current_model_instance_ids=(),
    )
    empty_index = AbilityCatalogIndex.from_records(())
    duplicate_index = AbilityCatalogIndex.from_records(
        (
            *player_index.all_records(),
            replace(reroll_record, record_id=f"{reroll_record.record_id}:duplicate"),
        )
    )

    assert reroll_record.definition.timing.trigger_kind is TimingTriggerKind.AFTER_DICE_ROLL
    assert rule_ir.is_supported
    assert catalog_rule_ir_consumers_for_rule(rule_ir) == (
        CATALOG_IR_ADVANCE_ROLL_REROLL_CONSUMER_ID,
        CATALOG_IR_CHARGE_ROLL_REROLL_CONSUMER_ID,
    )
    assert set(catalog_rule_ir_hook_ids_for_rule(rule_ir)) == {
        CATALOG_IR_ADVANCE_ROLL_REROLL_CONSUMER_ID,
        CATALOG_IR_CHARGE_ROLL_REROLL_CONSUMER_ID,
    }
    assert advance_permission is not None
    assert advance_permission.eligible_roll_type == "advance_roll"
    assert advance_permission.timing_window == "after_advance_roll"
    assert advance_permission.owning_player_id == army.player_id
    assert (
        advance_permission.component_selection_policy is RerollComponentSelectionPolicy.WHOLE_ROLL
    )
    assert charge_permission is not None
    assert charge_permission.eligible_roll_type == "charge_roll"
    assert charge_permission.timing_window == "after_charge_roll"
    assert charge_permission.owning_player_id == army.player_id
    assert charge_permission.component_selection_policy is RerollComponentSelectionPolicy.WHOLE_ROLL
    assert advance_phase_permission == advance_permission
    assert charge_phase_permission == charge_permission
    assert keyword_permission is not None
    assert keyword_permission.source_id == f"{unit.unit_instance_id}:advance-reroll"
    assert keyword_permission.eligible_roll_type == "advance_roll"
    assert (
        catalog_advance_roll_reroll_permission_for_unit(
            ability_index=empty_index,
            unit=unit,
            current_model_instance_ids=current_model_ids,
            player_id=army.player_id,
        )
        is None
    )
    with pytest.raises(GameLifecycleError, match="Multiple catalog roll reroll permissions"):
        catalog_advance_roll_reroll_permission_for_unit(
            ability_index=duplicate_index,
            unit=unit,
            current_model_instance_ids=current_model_ids,
            player_id=army.player_id,
        )
    with pytest.raises(GameLifecycleError, match="requires an ability record"):
        _catalog_roll_reroll_permission(
            record=cast(AbilityCatalogRecord, object()),
            clause=rule_ir.clauses[0],
            effect_index=0,
            player_id=army.player_id,
            roll_type="advance_roll",
            timing_window="after_advance_roll",
        )
    with pytest.raises(GameLifecycleError, match="requires a rule clause"):
        _catalog_roll_reroll_permission(
            record=reroll_record,
            clause=cast(RuleClause, object()),
            effect_index=0,
            player_id=army.player_id,
            roll_type="advance_roll",
            timing_window="after_advance_roll",
        )
    with pytest.raises(GameLifecycleError, match="effect_index must be non-negative"):
        _catalog_roll_reroll_permission(
            record=reroll_record,
            clause=rule_ir.clauses[0],
            effect_index=-1,
            player_id=army.player_id,
            roll_type="advance_roll",
            timing_window="after_advance_roll",
        )


def test_phase17k_this_model_reroll_text_uses_generic_advance_charge_rerolls() -> None:
    package = _model_reroll_package()
    unit = _advance_charge_unit(package=package)
    army = _flesh_hounds_army(package=package, unit=unit)
    player_index = _player_ability_index(package=package, army=army)
    records_by_name = {record.definition.name: record for record in player_index.all_records()}
    reroll_record = records_by_name["Swift Instincts"]
    replay_payload = reroll_record.definition.replay_payload
    assert isinstance(replay_payload, dict)
    rule_ir = RuleIR.from_payload(cast(RuleIRPayload, replay_payload["rule_ir"]))
    battlefield = _bloodcrushers_battlefield_state(army=army, unit=unit)
    current_model_ids = _current_model_ids(battlefield=battlefield, unit=unit)
    advance_permission = catalog_advance_roll_reroll_permission_for_unit(
        ability_index=player_index,
        unit=unit,
        current_model_instance_ids=current_model_ids,
        player_id=army.player_id,
    )
    charge_permission = catalog_charge_roll_reroll_permission_for_unit(
        ability_index=player_index,
        unit=unit,
        current_model_instance_ids=current_model_ids,
        player_id=army.player_id,
    )
    clause = rule_ir.clauses[0]

    assert reroll_record.definition.timing.trigger_kind is TimingTriggerKind.AFTER_DICE_ROLL
    assert rule_ir.is_supported
    assert clause.target is not None
    assert clause.target.kind is RuleTargetKind.THIS_MODEL
    assert catalog_rule_ir_consumers_for_rule(rule_ir) == (
        CATALOG_IR_ADVANCE_ROLL_REROLL_CONSUMER_ID,
        CATALOG_IR_CHARGE_ROLL_REROLL_CONSUMER_ID,
    )
    assert set(catalog_rule_ir_hook_ids_for_rule(rule_ir)) == {
        CATALOG_IR_ADVANCE_ROLL_REROLL_CONSUMER_ID,
        CATALOG_IR_CHARGE_ROLL_REROLL_CONSUMER_ID,
    }
    assert advance_permission is not None
    assert advance_permission.eligible_roll_type == "advance_roll"
    assert advance_permission.timing_window == "after_advance_roll"
    assert advance_permission.owning_player_id == army.player_id
    assert (
        advance_permission.component_selection_policy is RerollComponentSelectionPolicy.WHOLE_ROLL
    )
    assert charge_permission is not None
    assert charge_permission.eligible_roll_type == "charge_roll"
    assert charge_permission.timing_window == "after_charge_roll"
    assert charge_permission.owning_player_id == army.player_id
    assert charge_permission.component_selection_policy is RerollComponentSelectionPolicy.WHOLE_ROLL


def test_phase17k_model_reroll_runtime_uses_scoped_catalog_clause_record() -> None:
    package = _split_model_reroll_package()
    unit = _advance_charge_unit(package=package)
    army = _flesh_hounds_army(package=package, unit=unit)
    player_index = _player_ability_index(package=package, army=army)
    split_records = tuple(
        record
        for record in player_index.all_records()
        if record.definition.name == "Split Swift Instincts"
    )
    unrelated_record = _record_by_runtime_clause_suffix(split_records, suffix=":clause:001")
    reroll_record = _record_by_runtime_clause_suffix(split_records, suffix=":clause:002")
    battlefield = _bloodcrushers_battlefield_state(army=army, unit=unit)
    current_model_ids = _current_model_ids(battlefield=battlefield, unit=unit)

    advance_permission = catalog_advance_roll_reroll_permission_for_unit(
        ability_index=player_index,
        unit=unit,
        current_model_instance_ids=current_model_ids,
        player_id=army.player_id,
    )
    charge_permission = catalog_charge_roll_reroll_permission_for_unit(
        ability_index=player_index,
        unit=unit,
        current_model_instance_ids=current_model_ids,
        player_id=army.player_id,
    )

    assert len(split_records) == 2
    assert unrelated_record.definition.timing.trigger_kind is TimingTriggerKind.AFTER_DICE_ROLL
    assert reroll_record.definition.timing.trigger_kind is TimingTriggerKind.AFTER_DICE_ROLL
    assert advance_permission is not None
    assert advance_permission.eligible_roll_type == "advance_roll"
    assert advance_permission.source_id.startswith(f"{reroll_record.record_id}:")
    assert not advance_permission.source_id.startswith(f"{unrelated_record.record_id}:")
    assert charge_permission is not None
    assert charge_permission.eligible_roll_type == "charge_roll"
    assert charge_permission.source_id.startswith(f"{reroll_record.record_id}:")
    assert not charge_permission.source_id.startswith(f"{unrelated_record.record_id}:")


def test_phase17k_leading_model_weapon_keyword_text_modifies_scoped_weapon_profiles() -> None:
    package = _advance_charge_package()
    unit = _advance_charge_unit(package=package)
    army = _flesh_hounds_army(package=package, unit=unit)
    player_index = _player_ability_index(package=package, army=army)
    records_by_name = {record.definition.name: record for record in player_index.all_records()}
    weapon_grant_record = records_by_name["Pack Killers"]
    replay_payload = weapon_grant_record.definition.replay_payload
    assert isinstance(replay_payload, dict)
    rule_ir = RuleIR.from_payload(cast(RuleIRPayload, replay_payload["rule_ir"]))
    battlefield = _bloodcrushers_battlefield_state(army=army, unit=unit)
    state = _battle_state_with_army(army=army, battlefield=battlefield)
    current_model_ids = _current_model_ids(battlefield=battlefield, unit=unit)
    swift_claws = next(
        wargear
        for wargear in package.army_catalog.wargear
        if wargear.wargear_id == "test-advance-charge-unit:swift-claws"
    )
    melee_profile = swift_claws.weapon_profiles[0]
    ranged_profile = replace(
        melee_profile,
        profile_id=f"{melee_profile.profile_id}:ranged-copy",
        range_profile=RangeProfile.distance(12),
    )
    grants = catalog_weapon_keyword_grants_for_unit(
        ability_index=player_index,
        unit=unit,
        current_model_instance_ids=current_model_ids,
    )
    bindings = catalog_weapon_profile_modifier_bindings(
        ability_indexes_by_player_id={army.player_id: player_index},
        armies=(army,),
    )
    registry = RuntimeModifierRegistry.from_bindings(
        weapon_profile_modifier_bindings=bindings,
    )
    attacker_model_id = unit.own_models[0].model_instance_id
    melee_context = WeaponProfileModifierContext(
        state=state,
        source_phase=BattlePhase.FIGHT,
        attacking_unit_instance_id=unit.unit_instance_id,
        attacker_model_instance_id=attacker_model_id,
        target_unit_instance_id="phase17k-target-unit",
        weapon_profile=melee_profile,
    )
    ranged_context = replace(melee_context, weapon_profile=ranged_profile)
    modified_melee = registry.modified_weapon_profile(melee_context)
    modified_ranged = registry.modified_weapon_profile(ranged_context)

    assert weapon_grant_record.definition.timing.trigger_kind is TimingTriggerKind.PASSIVE_QUERY
    assert rule_ir.is_supported
    assert catalog_rule_ir_consumers_for_rule(rule_ir) == (
        CATALOG_IR_WEAPON_KEYWORD_GRANT_CONSUMER_ID,
        "catalog-ir:weapon-keyword-grant:lethal-hits",
    )
    assert set(catalog_rule_ir_hook_ids_for_rule(rule_ir)) == {
        CATALOG_IR_WEAPON_KEYWORD_GRANT_CONSUMER_ID,
        "catalog-ir:weapon-keyword-grant:lethal-hits",
    }
    assert tuple(binding.modifier_id for binding in bindings) == (
        CATALOG_IR_WEAPON_KEYWORD_GRANT_CONSUMER_ID,
    )
    assert len(grants) == 1
    assert grants[0].keyword is WeaponKeyword.LETHAL_HITS
    assert grants[0].weapon_scope == "melee"
    assert grants[0].ability is not None
    assert grants[0].ability.ability_kind is AbilityKind.LETHAL_HITS
    assert WeaponKeyword.LETHAL_HITS in modified_melee.keywords
    assert any(
        ability.ability_kind is AbilityKind.LETHAL_HITS for ability in modified_melee.abilities
    )
    assert grants[0].source_id in modified_melee.source_ids
    assert modified_ranged == ranged_profile


def test_phase17k_named_weapon_ability_choice_records_and_modifies_profile() -> None:
    package = _named_weapon_choice_package()
    unit = _named_weapon_choice_unit(package=package)
    army = _flesh_hounds_army(package=package, unit=unit)
    player_index = _player_ability_index(package=package, army=army)
    records_by_name = {record.definition.name: record for record in player_index.all_records()}
    choice_record = records_by_name["Daemonspark"]
    replay_payload = choice_record.definition.replay_payload
    assert isinstance(replay_payload, dict)
    rule_ir = RuleIR.from_payload(cast(RuleIRPayload, replay_payload["rule_ir"]))
    battlefield = _bloodcrushers_battlefield_state(army=army, unit=unit)
    state = _battle_state_with_army(army=army, battlefield=battlefield)
    _set_state_battle_phase(state, BattlePhase.SHOOTING)
    decisions = DecisionController()
    runtime = CatalogNamedWeaponAbilityChoiceRuntime(
        ability_indexes_by_player_id={army.player_id: player_index},
        armies=(army,),
    )
    registry = ShootingPhaseStartHookRegistry.from_bindings(runtime.bindings())
    request_context = _shooting_phase_start_request_context(
        state=state,
        decisions=decisions,
        army_catalog=package.army_catalog,
    )
    request = registry.next_request_for(request_context)

    assert request is not None
    assert catalog_rule_ir_consumers_for_rule(rule_ir) == (
        CATALOG_IR_NAMED_WEAPON_ABILITY_CHOICE_CONSUMER_ID,
        CATALOG_IR_WEAPON_KEYWORD_GRANT_CONSUMER_ID,
        "catalog-ir:weapon-keyword-grant:ignores-cover",
        "catalog-ir:weapon-keyword-grant:lethal-hits",
        "catalog-ir:weapon-keyword-grant:sustained-hits",
    )
    assert set(catalog_rule_ir_hook_ids_for_rule(rule_ir)) == {
        CATALOG_IR_NAMED_WEAPON_ABILITY_CHOICE_CONSUMER_ID,
        CATALOG_IR_WEAPON_KEYWORD_GRANT_CONSUMER_ID,
        "catalog-ir:weapon-keyword-grant:ignores-cover",
        "catalog-ir:weapon-keyword-grant:lethal-hits",
        "catalog-ir:weapon-keyword-grant:sustained-hits",
    }
    assert request.decision_type == SELECT_FACTION_RULE_SHOOTING_PHASE_START_OPTION_DECISION_TYPE
    assert request.actor_id == army.player_id
    assert type(request).from_payload(request.to_payload()).to_payload() == request.to_payload()
    request_payload = cast(dict[str, JsonValue], request.payload)
    assert request_payload["submission_kind"] == (
        SELECT_CATALOG_NAMED_WEAPON_ABILITY_CHOICE_SUBMISSION_KIND
    )
    assert request_payload["weapon_names"] == ["Bolt of Change"]
    assert request_payload["target_model_instance_ids"] == [unit.own_models[0].model_instance_id]
    assert tuple(option.label for option in request.options) == (
        "Ignores Cover for Bolt of Change",
        "Lethal Hits for Bolt of Change",
        "Sustained Hits D3 for Bolt of Change",
    )
    sustained_option = next(
        option
        for option in request.options
        if cast(dict[str, JsonValue], option.payload)["selected_named_weapon_ability_choice"]
        == {
            "option_id": option.option_id,
            "selection_option_id": "option_003_sustained_hits_d3",
            "selection_option_index": 3,
            "selected_weapon_ability": "Sustained Hits",
            "keyword": "Sustained Hits",
            "ability_descriptor": AbilityDescriptor.sustained_hits("D3").to_payload(),
            "weapon_ability_value": "D3",
        }
    )
    result = DecisionResult.for_request(
        result_id="phase17k-named-weapon-choice-sustained-d3",
        request=request,
        selected_option_id=sustained_option.option_id,
    )
    decisions.request_decision(request)
    record = decisions.submit_result(result)
    handled = registry.apply_result(
        ShootingPhaseStartResultContext(
            state=state,
            decisions=decisions,
            request=record.request,
            result=record.result,
            ruleset_descriptor=RulesetDescriptor.warhammer_40000_eleventh(),
            army_catalog=package.army_catalog,
            shooting_target_restriction_hooks=ShootingTargetRestrictionHookRegistry.empty(),
        )
    )
    bolt_profile = _weapon_profile_by_name(package.army_catalog, "Bolt of Change")
    other_profile = replace(
        bolt_profile,
        profile_id=f"{bolt_profile.profile_id}:other",
        name="Infernal Gateway",
    )
    modifier_registry = RuntimeModifierRegistry.from_bindings(
        weapon_profile_modifier_bindings=catalog_weapon_profile_modifier_bindings(
            ability_indexes_by_player_id={army.player_id: player_index},
            armies=(army,),
        )
    )
    shooting_context = WeaponProfileModifierContext(
        state=state,
        source_phase=BattlePhase.SHOOTING,
        attacking_unit_instance_id=unit.unit_instance_id,
        attacker_model_instance_id=unit.own_models[0].model_instance_id,
        target_unit_instance_id="phase17k-target-unit",
        weapon_profile=bolt_profile,
    )
    modified_bolt = modifier_registry.modified_weapon_profile(shooting_context)

    assert handled is True
    effects = state.persisting_effects_for_unit(unit.unit_instance_id)
    assert len(effects) == 1
    effect_payload = cast(dict[str, JsonValue], effects[0].effect_payload)
    assert effect_payload["effect_kind"] == CATALOG_NAMED_WEAPON_ABILITY_CHOICE_EFFECT_KIND
    assert effect_payload["weapon_ability_value"] == "D3"
    assert WeaponKeyword.SUSTAINED_HITS in modified_bolt.keywords
    assert any(
        ability.to_payload() == AbilityDescriptor.sustained_hits("D3").to_payload()
        for ability in modified_bolt.abilities
    )
    assert (
        modifier_registry.modified_weapon_profile(
            replace(shooting_context, source_phase=BattlePhase.FIGHT)
        )
        == bolt_profile
    )
    assert (
        modifier_registry.modified_weapon_profile(
            replace(shooting_context, weapon_profile=other_profile)
        )
        == other_profile
    )
    selected_events = tuple(
        event
        for event in decisions.event_log.records
        if event.event_type == CATALOG_NAMED_WEAPON_ABILITY_CHOICE_SELECTED_EVENT
    )
    assert len(selected_events) == 1
    assert "object at 0x" not in json.dumps(decisions.to_payload(), sort_keys=True)


def test_phase17k_named_weapon_choice_uses_runtime_clause_scoped_records() -> None:
    package = _named_weapon_choice_package()
    unit = _named_weapon_choice_unit(package=package)
    army = _flesh_hounds_army(package=package, unit=unit)
    rule_ir = _multi_clause_named_weapon_choice_rule_ir()
    clause_001_record = _multi_clause_named_weapon_choice_record(
        rule_ir=rule_ir,
        clause_index=0,
        datasheet_id=unit.datasheet_id,
        trigger_kind=TimingTriggerKind.PASSIVE_QUERY,
    )
    clause_002_record = _multi_clause_named_weapon_choice_record(
        rule_ir=rule_ir,
        clause_index=1,
        datasheet_id=unit.datasheet_id,
        trigger_kind=TimingTriggerKind.DURING_PHASE,
    )
    ability_index = AbilityCatalogIndex.from_records((clause_001_record, clause_002_record))
    state = _battle_state_with_army(
        army=army,
        battlefield=_bloodcrushers_battlefield_state(army=army, unit=unit),
    )
    _set_state_battle_phase(state, BattlePhase.SHOOTING)
    request_context = _shooting_phase_start_request_context(
        state=state,
        decisions=DecisionController(),
        army_catalog=package.army_catalog,
    )

    groups = _available_catalog_named_weapon_ability_choice_groups(
        ability_indexes_by_player_id={army.player_id: ability_index},
        armies=(army,),
        context=request_context,
    )
    request = ShootingPhaseStartHookRegistry.from_bindings(
        CatalogNamedWeaponAbilityChoiceRuntime(
            ability_indexes_by_player_id={army.player_id: ability_index},
            armies=(army,),
        ).bindings()
    ).next_request_for(request_context)

    assert not _record_can_select_catalog_named_weapon_ability(clause_001_record)
    assert _record_can_select_catalog_named_weapon_ability(clause_002_record)
    assert len(groups) == 1
    assert groups[0].record.record_id == clause_002_record.record_id
    assert groups[0].clause.clause_id == rule_ir.clauses[1].clause_id
    assert request is not None
    request_payload = cast(dict[str, JsonValue], request.payload)
    assert request_payload["catalog_record_id"] == clause_002_record.record_id
    assert len(request.options) == 2


def test_phase17k_post_shoot_hit_target_cover_denial_records_and_applies_effect() -> None:
    package = _post_shoot_cover_denial_package()
    unit = _named_weapon_choice_unit(package=package)
    target_unit = _named_weapon_choice_unit(
        package=package,
        army_id="army-opponent",
        unit_selection_id="enemy-lord-of-change-1",
    )
    army = _flesh_hounds_army(package=package, unit=unit)
    enemy_army = _flesh_hounds_army(
        package=package,
        unit=target_unit,
        army_id="army-opponent",
        player_id="player-opponent",
    )
    player_index = _player_ability_index(package=package, army=army)
    enemy_player_index = _player_ability_index(package=package, army=enemy_army)
    records_by_name = {record.definition.name: record for record in player_index.all_records()}
    cover_record = records_by_name["Purge and Cleanse"]
    replay_payload = cast(dict[str, JsonValue], cover_record.definition.replay_payload)
    rule_ir = RuleIR.from_payload(cast(RuleIRPayload, replay_payload["rule_ir"]))
    battlefield = _flesh_hounds_battlefield_state(
        army=army,
        unit=unit,
        enemy_army=enemy_army,
        enemy_unit=target_unit,
        enemy_x=24.0,
    )
    state = _battle_state_with_armies(
        armies=(army, enemy_army),
        battlefield=battlefield,
        active_player_id=army.player_id,
        phase=BattlePhase.SHOOTING,
    )
    decisions = DecisionController()
    attack_sequence = _completed_post_shoot_attack_sequence(
        package=package,
        attacker=unit,
        target=target_unit,
    )
    _emit_successful_hit(
        decisions=decisions,
        attack_sequence=attack_sequence,
        successful=True,
    )
    completed_event = decisions.event_log.append(
        "attack_sequence_completed",
        {
            "sequence_id": attack_sequence.sequence_id,
            "attacker_player_id": army.player_id,
            "attacking_unit_instance_id": unit.unit_instance_id,
        },
    )
    context = AttackSequenceCompletedContext(
        state=state,
        decisions=decisions,
        dice_manager=DiceRollManager(state.game_id, event_log=decisions.event_log),
        runtime_modifier_registry=RuntimeModifierRegistry.empty(),
        source_phase=BattlePhase.SHOOTING,
        attack_sequence=attack_sequence,
        attack_sequence_completed_event_id=completed_event.event_id,
    )
    runtime = CatalogPostShootHitTargetStatusRuntime(
        ability_indexes_by_player_id={
            army.player_id: player_index,
            enemy_army.player_id: enemy_player_index,
        },
        armies=(army, enemy_army),
    )

    groups = _available_catalog_post_shoot_hit_target_status_groups(
        ability_indexes_by_player_id={army.player_id: player_index},
        armies=(army, enemy_army),
        context=context,
    )
    status = runtime.request_handler(context)

    assert _record_can_select_catalog_post_shoot_hit_target_status(cover_record)
    assert catalog_rule_ir_consumers_for_rule(rule_ir) == (
        CATALOG_IR_POST_SHOOT_HIT_TARGET_STATUS_CONSUMER_ID,
    )
    assert catalog_rule_ir_hook_ids_for_rule(rule_ir) == (
        CATALOG_IR_POST_SHOOT_HIT_TARGET_STATUS_CONSUMER_ID,
    )
    assert len(groups) == 1
    assert groups[0].record.record_id == cover_record.record_id
    assert groups[0].clause.clause_id == rule_ir.clauses[0].clause_id
    assert status is not None
    assert status.status_kind is LifecycleStatusKind.WAITING_FOR_DECISION
    request = decisions.queue.peek_next()
    assert request is not None
    assert request.decision_type == SELECT_CATALOG_POST_SHOOT_HIT_TARGET_STATUS_DECISION_TYPE
    assert request.actor_id == army.player_id
    assert type(request).from_payload(request.to_payload()).to_payload() == request.to_payload()
    request_payload = cast(dict[str, JsonValue], request.payload)
    assert request_payload["submission_kind"] == (
        SELECT_CATALOG_POST_SHOOT_HIT_TARGET_STATUS_SUBMISSION_KIND
    )
    assert request_payload["catalog_record_id"] == cover_record.record_id
    assert request_payload["status"] == "benefit_of_cover"
    assert request_payload["available_target_unit_instance_ids"] == [target_unit.unit_instance_id]
    assert tuple(option.label for option in request.options) == (
        f"Deny Benefit of Cover to {target_unit.unit_instance_id}",
    )

    result = DecisionResult.for_request(
        result_id="phase17k-post-shoot-cover-denial",
        request=request,
        selected_option_id=request.options[0].option_id,
    )
    assert (
        invalid_catalog_post_shoot_hit_target_status_status(
            state=state,
            request=request,
            result=result,
        )
        is None
    )
    decisions.submit_result(result)
    apply_status = apply_catalog_post_shoot_hit_target_status_result(
        state=state,
        decisions=decisions,
        result=result,
    )
    effects = state.persisting_effects_for_unit(target_unit.unit_instance_id)

    assert apply_status is None
    assert len(effects) == 1
    effect_payload = cast(dict[str, JsonValue], effects[0].effect_payload)
    assert effect_payload["effect_kind"] == CATALOG_POST_SHOOT_HIT_TARGET_STATUS_EFFECT_KIND
    assert effect_payload["benefit_of_cover_denied"] is True
    assert effect_payload["catalog_record_id"] == cover_record.record_id
    assert effect_payload["rule_ir_hash"] == rule_ir.ir_hash()
    assert effects[0].expiration == EffectExpiration.end_phase(
        battle_round=state.battle_round,
        phase=BattlePhase.SHOOTING,
        player_id=army.player_id,
    )
    selected_events = tuple(
        event
        for event in decisions.event_log.records
        if event.event_type == CATALOG_POST_SHOOT_HIT_TARGET_STATUS_SELECTED_EVENT
    )
    assert len(selected_events) == 1
    assert "object at 0x" not in json.dumps(decisions.to_payload(), sort_keys=True)

    stale_state = _battle_state_with_armies(
        armies=(army, enemy_army),
        battlefield=battlefield,
        active_player_id=army.player_id,
        phase=BattlePhase.FIGHT,
    )
    stale_status = invalid_catalog_post_shoot_hit_target_status_status(
        state=stale_state,
        request=request,
        result=result,
    )
    assert stale_status is not None
    stale_payload = cast(dict[str, JsonValue], stale_status.payload)
    assert stale_payload["invalid_reason"] == "phase_drift"

    drifted_payload = dict(cast(dict[str, JsonValue], request.options[0].payload))
    drifted_payload["status"] = "changed"
    drift_status = invalid_catalog_post_shoot_hit_target_status_status(
        state=state,
        request=request,
        result=DecisionResult(
            result_id="phase17k-post-shoot-cover-denial-drift",
            request_id=request.request_id,
            decision_type=request.decision_type,
            actor_id=request.actor_id,
            selected_option_id=request.options[0].option_id,
            payload=drifted_payload,
        ),
    )
    assert drift_status is not None
    drift_payload = cast(dict[str, JsonValue], drift_status.payload)
    assert drift_payload["field"] == "payload"

    malformed_status = invalid_catalog_post_shoot_hit_target_status_status(
        state=state,
        request=request,
        result=DecisionResult(
            result_id="phase17k-post-shoot-cover-denial-malformed",
            request_id=request.request_id,
            decision_type=request.decision_type,
            actor_id=request.actor_id,
            selected_option_id="phase17k-missing-option",
            payload=request.options[0].payload,
        ),
    )
    assert malformed_status is not None
    malformed_payload = cast(dict[str, JsonValue], malformed_status.payload)
    assert malformed_payload["field"] == "selected_option_id"

    base_request_payload = cast(dict[str, JsonValue], request.payload)
    base_option_payload = cast(dict[str, JsonValue], request.options[0].payload)

    def invalid_reason_for_payload(
        *,
        expected_reason: str,
        option_payload: dict[str, JsonValue],
        request_payload: dict[str, JsonValue] | JsonValue | None = None,
    ) -> str:
        updated_request = replace(
            request,
            payload=validate_json_value(
                base_request_payload if request_payload is None else request_payload
            ),
            options=(
                replace(
                    request.options[0],
                    payload=validate_json_value(option_payload),
                ),
            ),
        )
        status = invalid_catalog_post_shoot_hit_target_status_status(
            state=state,
            request=updated_request,
            result=DecisionResult(
                result_id=f"phase17k-post-shoot-cover-denial-{expected_reason}",
                request_id=updated_request.request_id,
                decision_type=updated_request.decision_type,
                actor_id=updated_request.actor_id,
                selected_option_id=updated_request.options[0].option_id,
                payload=validate_json_value(option_payload),
            ),
        )
        assert status is not None
        payload = cast(dict[str, JsonValue], status.payload)
        return cast(str, payload["invalid_reason"])

    for key, value, expected_reason in (
        ("submission_kind", "changed", "submission_kind_drift"),
        ("hook_id", "changed", "hook_id_drift"),
        ("game_id", "changed", "game_id_drift"),
        ("battle_round", 2, "battle_round_drift"),
        ("phase", "fight", "payload_phase_drift"),
        ("active_player_id", enemy_army.player_id, "active_player_drift"),
        ("player_id", enemy_army.player_id, "actor_player_drift"),
    ):
        payload = dict(base_option_payload)
        payload[key] = cast(JsonValue, value)
        assert (
            invalid_reason_for_payload(
                expected_reason=expected_reason,
                option_payload=payload,
            )
            == expected_reason
        )

    for key, value, expected_reason in (
        ("hook_id", "changed", "request_hook_id_drift"),
        ("game_id", "changed", "request_game_id_drift"),
        ("battle_round", 2, "request_battle_round_drift"),
        ("phase", "fight", "request_phase_drift"),
        ("active_player_id", enemy_army.player_id, "request_active_player_drift"),
    ):
        payload = dict(base_request_payload)
        payload[key] = cast(JsonValue, value)
        assert (
            invalid_reason_for_payload(
                expected_reason=expected_reason,
                option_payload=dict(base_option_payload),
                request_payload=payload,
            )
            == expected_reason
        )

    assert (
        invalid_reason_for_payload(
            expected_reason="request_payload_not_object",
            option_payload=dict(base_option_payload),
            request_payload="not-an-object",
        )
        == "request_payload_not_object"
    )

    selected_not_object_payload = dict(base_option_payload)
    selected_not_object_payload["selected_post_shoot_hit_target_status"] = "not-an-object"
    assert (
        invalid_reason_for_payload(
            expected_reason="selected_payload_not_object",
            option_payload=selected_not_object_payload,
        )
        == "selected_payload_not_object"
    )

    selected_option_drift_payload = dict(base_option_payload)
    selected_payload = dict(
        cast(
            dict[str, JsonValue],
            selected_option_drift_payload["selected_post_shoot_hit_target_status"],
        )
    )
    selected_payload["option_id"] = "changed"
    selected_option_drift_payload["selected_post_shoot_hit_target_status"] = selected_payload
    assert (
        invalid_reason_for_payload(
            expected_reason="selected_option_payload_drift",
            option_payload=selected_option_drift_payload,
        )
        == "selected_option_payload_drift"
    )

    selected_target_type_payload = dict(base_option_payload)
    selected_payload = dict(
        cast(
            dict[str, JsonValue],
            selected_target_type_payload["selected_post_shoot_hit_target_status"],
        )
    )
    selected_payload["target_unit_instance_id"] = 1
    selected_target_type_payload["selected_post_shoot_hit_target_status"] = selected_payload
    assert (
        invalid_reason_for_payload(
            expected_reason="selected_target_payload_drift",
            option_payload=selected_target_type_payload,
        )
        == "selected_target_payload_drift"
    )

    target_drift_payload = dict(base_option_payload)
    selected_payload = dict(
        cast(dict[str, JsonValue], target_drift_payload["selected_post_shoot_hit_target_status"])
    )
    selected_payload["target_unit_instance_id"] = unit.unit_instance_id
    target_drift_payload["selected_post_shoot_hit_target_status"] = selected_payload
    assert (
        invalid_reason_for_payload(
            expected_reason="target_drift",
            option_payload=target_drift_payload,
        )
        == "target_drift"
    )

    for key, value, expected_reason in (
        ("source_phase", BattlePhase.FIGHT.value, "attack_sequence_phase_drift"),
        ("sequence_id", "changed-sequence", "attack_sequence_id_drift"),
        ("attacker_player_id", enemy_army.player_id, "attack_sequence_attacker_drift"),
        ("attacking_unit_instance_id", target_unit.unit_instance_id, "attack_sequence_unit_drift"),
    ):
        payload = dict(base_option_payload)
        attack_sequence_payload = dict(cast(dict[str, JsonValue], payload["attack_sequence"]))
        attack_sequence_payload[key] = value
        payload["attack_sequence"] = attack_sequence_payload
        assert (
            invalid_reason_for_payload(
                expected_reason=expected_reason,
                option_payload=payload,
            )
            == expected_reason
        )

    assert successful_hit_target_unit_ids_for_sequence(
        decisions=decisions,
        sequence=attack_sequence,
        attacker_model_instance_id=unit.own_models[0].model_instance_id,
        wargear_ids=(attack_sequence.attack_pools[0].wargear_id,),
        weapon_profile_ids=(attack_sequence.attack_pools[0].weapon_profile_id,),
    ) == (target_unit.unit_instance_id,)
    assert (
        successful_hit_target_unit_ids_for_sequence(
            decisions=decisions,
            sequence=attack_sequence,
            attacker_model_instance_id="phase17k-other-model",
        )
        == ()
    )
    assert (
        successful_hit_target_unit_ids_for_sequence(
            decisions=decisions,
            sequence=attack_sequence,
            wargear_ids=("phase17k-other-wargear",),
        )
        == ()
    )
    assert (
        successful_hit_target_unit_ids_for_sequence(
            decisions=decisions,
            sequence=attack_sequence,
            weapon_profile_ids=("phase17k-other-profile",),
        )
        == ()
    )


def test_phase17k_post_shoot_selected_target_effect_records_generic_rule_effect() -> None:
    package = _post_shoot_selected_target_effect_package()
    unit = _named_weapon_choice_unit(package=package)
    target_unit = _named_weapon_choice_unit(
        package=package,
        army_id="army-opponent",
        unit_selection_id="enemy-lord-of-change-1",
    )
    army = _flesh_hounds_army(package=package, unit=unit)
    enemy_army = _flesh_hounds_army(
        package=package,
        unit=target_unit,
        army_id="army-opponent",
        player_id="player-opponent",
    )
    player_index = _player_ability_index(package=package, army=army)
    enemy_player_index = _player_ability_index(package=package, army=enemy_army)
    record = next(
        record
        for record in player_index.all_records()
        if record.definition.name == "Warpflame Locus" and record.record_id.endswith(":clause:001")
    )
    replay_payload = cast(dict[str, JsonValue], record.definition.replay_payload)
    rule_ir = RuleIR.from_payload(cast(RuleIRPayload, replay_payload["rule_ir"]))
    battlefield = _flesh_hounds_battlefield_state(
        army=army,
        unit=unit,
        enemy_army=enemy_army,
        enemy_unit=target_unit,
        enemy_x=24.0,
    )
    state = _battle_state_with_armies(
        armies=(army, enemy_army),
        battlefield=battlefield,
        active_player_id=army.player_id,
        phase=BattlePhase.SHOOTING,
    )
    decisions = DecisionController()
    attack_sequence = _completed_post_shoot_attack_sequence(
        package=package,
        attacker=unit,
        target=target_unit,
    )
    _emit_successful_hit(
        decisions=decisions,
        attack_sequence=attack_sequence,
        successful=True,
    )
    completed_event = decisions.event_log.append(
        "attack_sequence_completed",
        {
            "sequence_id": attack_sequence.sequence_id,
            "attacker_player_id": army.player_id,
            "attacking_unit_instance_id": unit.unit_instance_id,
        },
    )
    context = AttackSequenceCompletedContext(
        state=state,
        decisions=decisions,
        dice_manager=DiceRollManager(state.game_id, event_log=decisions.event_log),
        runtime_modifier_registry=RuntimeModifierRegistry.empty(),
        source_phase=BattlePhase.SHOOTING,
        attack_sequence=attack_sequence,
        attack_sequence_completed_event_id=completed_event.event_id,
    )
    status = CatalogSelectedTargetEffectRuntime(
        ability_indexes_by_player_id={
            army.player_id: player_index,
            enemy_army.player_id: enemy_player_index,
        },
        armies=(army, enemy_army),
    ).post_shoot_hit_target_request(context)

    assert catalog_rule_ir_consumers_for_rule(rule_ir) == (
        CATALOG_IR_POST_SHOOT_HIT_TARGET_EFFECT_CONSUMER_ID,
    )
    assert CATALOG_IR_POST_SHOOT_HIT_TARGET_EFFECT_CONSUMER_ID in (
        catalog_rule_ir_hook_ids_for_rule(rule_ir)
    )
    assert status is not None
    assert status.status_kind is LifecycleStatusKind.WAITING_FOR_DECISION
    request = decisions.queue.peek_next()
    assert request is not None
    assert request.decision_type == SELECT_CATALOG_POST_SHOOT_HIT_TARGET_EFFECT_DECISION_TYPE
    assert request.actor_id == army.player_id
    request_payload = cast(dict[str, JsonValue], request.payload)
    assert request_payload["submission_kind"] == (
        SELECT_CATALOG_POST_SHOOT_HIT_TARGET_EFFECT_SUBMISSION_KIND
    )
    assert request_payload["catalog_record_id"] == record.record_id
    assert request_payload["available_target_unit_instance_ids"] == [target_unit.unit_instance_id]
    option_payload = cast(dict[str, JsonValue], request.options[0].payload)
    effect_records = cast(list[dict[str, JsonValue]], option_payload["generic_rule_effect_records"])
    assert len(effect_records) == 1
    assert effect_records[0]["target_unit_instance_ids"] == [unit.unit_instance_id]

    result = DecisionResult.for_request(
        result_id="phase17k-post-shoot-selected-target-effect",
        request=request,
        selected_option_id=request.options[0].option_id,
    )
    assert (
        invalid_catalog_post_shoot_hit_target_effect_status(
            state=state,
            request=request,
            result=result,
        )
        is None
    )
    decisions.submit_result(result)
    assert (
        apply_catalog_post_shoot_hit_target_effect_result(
            state=state,
            decisions=decisions,
            result=result,
            battle_shock_hooks=BattleShockHookRegistry.empty(),
            runtime_modifier_registry=RuntimeModifierRegistry.empty(),
            ability_indexes_by_player_id={
                army.player_id: player_index,
                enemy_army.player_id: enemy_player_index,
            },
        )
        is None
    )
    effects = state.persisting_effects_for_unit(unit.unit_instance_id)
    assert len(effects) == 1
    effect_payload = cast(dict[str, JsonValue], effects[0].effect_payload)
    selected_payload = cast(dict[str, JsonValue], effect_payload["catalog_selected_target"])
    effect_spec_payload = cast(dict[str, JsonValue], effect_payload["effect"])
    effect_parameters = {
        cast(str, item["key"]): item["value"]
        for item in cast(list[dict[str, JsonValue]], effect_spec_payload["parameters"])
    }

    assert effect_payload["effect_kind"] == GENERIC_RULE_EFFECT_KIND
    assert effect_payload["rule_ir_hash"] == rule_ir.ir_hash()
    assert selected_payload["selected_target_unit_instance_id"] == target_unit.unit_instance_id
    assert selected_payload["attack_sequence_completed_event_id"] == completed_event.event_id
    assert effect_parameters["characteristic"] == "damage"
    assert effect_parameters["delta"] == 1
    assert effect_parameters["selected_target_unit_instance_id"] == target_unit.unit_instance_id
    assert effects[0].expiration == EffectExpiration.end_phase(
        battle_round=state.battle_round,
        phase=BattlePhase.SHOOTING,
        player_id=army.player_id,
    )
    selected_events = tuple(
        event
        for event in decisions.event_log.records
        if event.event_type == CATALOG_POST_SHOOT_HIT_TARGET_EFFECT_SELECTED_EVENT
    )
    assert len(selected_events) == 1

    stale_state = _battle_state_with_armies(
        armies=(army, enemy_army),
        battlefield=battlefield,
        active_player_id=army.player_id,
        phase=BattlePhase.FIGHT,
    )
    stale_status = invalid_catalog_post_shoot_hit_target_effect_status(
        state=stale_state,
        request=request,
        result=result,
    )
    assert stale_status is not None
    stale_payload = cast(dict[str, JsonValue], stale_status.payload)
    assert stale_payload["field"] == "state_phase"

    drifted_payload = dict(option_payload)
    drifted_payload["hook_id"] = "changed"
    drift_status = invalid_catalog_post_shoot_hit_target_effect_status(
        state=state,
        request=request,
        result=DecisionResult(
            result_id="phase17k-post-shoot-selected-target-effect-drift",
            request_id=request.request_id,
            decision_type=request.decision_type,
            actor_id=request.actor_id,
            selected_option_id=request.options[0].option_id,
            payload=drifted_payload,
        ),
    )
    assert drift_status is not None
    drift_payload = cast(dict[str, JsonValue], drift_status.payload)
    assert drift_payload["field"] == "payload"

    malformed_status = invalid_catalog_post_shoot_hit_target_effect_status(
        state=state,
        request=request,
        result=DecisionResult(
            result_id="phase17k-post-shoot-selected-target-effect-malformed",
            request_id=request.request_id,
            decision_type=request.decision_type,
            actor_id=request.actor_id,
            selected_option_id="phase17k-missing-option",
            payload=request.options[0].payload,
        ),
    )
    assert malformed_status is not None
    malformed_payload = cast(dict[str, JsonValue], malformed_status.payload)
    assert malformed_payload["field"] == "selected_option_id"
    assert "object at 0x" not in json.dumps(decisions.to_payload(), sort_keys=True)


def test_phase17k_datasheet_post_shoot_cover_denial_suppresses_save_cover() -> None:
    package = _post_shoot_cover_denial_package()
    unit = _named_weapon_choice_unit(package=package)
    target_unit_with_invulnerable = _named_weapon_choice_unit(
        package=package,
        army_id="army-opponent",
        unit_selection_id="enemy-lord-of-change-1",
    )
    target_model = replace(
        target_unit_with_invulnerable.own_models[0],
        characteristics=tuple(
            CharacteristicValue.from_raw(Characteristic.SAVE, 2)
            if characteristic.characteristic is Characteristic.SAVE
            else characteristic
            for characteristic in target_unit_with_invulnerable.own_models[0].characteristics
            if characteristic.characteristic is not Characteristic.INVULNERABLE_SAVE
        ),
    )
    target_unit = replace(target_unit_with_invulnerable, own_models=(target_model,))
    army = _flesh_hounds_army(package=package, unit=unit)
    enemy_army = _flesh_hounds_army(
        package=package,
        unit=target_unit,
        army_id="army-opponent",
        player_id="player-opponent",
    )
    player_index = _player_ability_index(package=package, army=army)
    enemy_player_index = _player_ability_index(package=package, army=enemy_army)
    records_by_name = {record.definition.name: record for record in player_index.all_records()}
    cover_record = records_by_name["Purge and Cleanse"]
    replay_payload = cast(dict[str, JsonValue], cover_record.definition.replay_payload)
    rule_ir = RuleIR.from_payload(cast(RuleIRPayload, replay_payload["rule_ir"]))
    battlefield = _flesh_hounds_battlefield_state(
        army=army,
        unit=unit,
        enemy_army=enemy_army,
        enemy_unit=target_unit,
        enemy_x=24.0,
    )
    state = _battle_state_with_armies(
        armies=(army, enemy_army),
        battlefield=battlefield,
        active_player_id=army.player_id,
        phase=BattlePhase.SHOOTING,
    )
    decisions = DecisionController()
    completed_sequence = _completed_post_shoot_attack_sequence(
        package=package,
        attacker=unit,
        target=target_unit,
    )
    _emit_successful_hit(
        decisions=decisions,
        attack_sequence=completed_sequence,
        successful=True,
    )
    completed_event = decisions.event_log.append(
        "attack_sequence_completed",
        {
            "sequence_id": completed_sequence.sequence_id,
            "attacker_player_id": army.player_id,
            "attacking_unit_instance_id": unit.unit_instance_id,
        },
    )
    status = CatalogPostShootHitTargetStatusRuntime(
        ability_indexes_by_player_id={
            army.player_id: player_index,
            enemy_army.player_id: enemy_player_index,
        },
        armies=(army, enemy_army),
    ).request_handler(
        AttackSequenceCompletedContext(
            state=state,
            decisions=decisions,
            dice_manager=DiceRollManager(state.game_id, event_log=decisions.event_log),
            runtime_modifier_registry=RuntimeModifierRegistry.empty(),
            source_phase=BattlePhase.SHOOTING,
            attack_sequence=completed_sequence,
            attack_sequence_completed_event_id=completed_event.event_id,
        )
    )
    assert status is not None
    assert status.status_kind is LifecycleStatusKind.WAITING_FOR_DECISION
    request = decisions.queue.peek_next()
    result = DecisionResult.for_request(
        result_id="phase17k-datasheet-cover-denial-save-consumer",
        request=request,
        selected_option_id=request.options[0].option_id,
    )
    decisions.submit_result(result)
    assert (
        apply_catalog_post_shoot_hit_target_status_result(
            state=state,
            decisions=decisions,
            result=result,
        )
        is None
    )
    denial_effects = state.persisting_effects_for_unit(target_unit.unit_instance_id)
    assert len(denial_effects) == 1
    denial_payload = cast(dict[str, JsonValue], denial_effects[0].effect_payload)
    assert denial_payload["effect_kind"] == CATALOG_POST_SHOOT_HIT_TARGET_STATUS_EFFECT_KIND
    assert denial_payload["benefit_of_cover_denied"] is True
    assert denial_payload["rule_ir_hash"] == rule_ir.ir_hash()

    state.record_persisting_effect(
        PersistingEffect(
            effect_id="phase17k-target-cover-grant",
            source_rule_id=SMOKESCREEN_EFFECT_KIND,
            owner_player_id=enemy_army.player_id,
            target_unit_instance_ids=(target_unit.unit_instance_id,),
            started_battle_round=state.battle_round,
            started_phase=BattlePhase.SHOOTING,
            expiration=EffectExpiration.end_phase(
                battle_round=state.battle_round,
                phase=BattlePhase.SHOOTING,
                player_id=army.player_id,
            ),
            effect_payload=validate_json_value(
                {
                    "effect_kind": SMOKESCREEN_EFFECT_KIND,
                    "benefit_of_cover": True,
                }
            ),
        )
    )
    weapon_profile = replace(
        completed_sequence.attack_pools[0].weapon_profile,
        profile_id="phase17k-cover-denial-save-bolt",
        armor_penetration=CharacteristicValue.from_raw(Characteristic.ARMOR_PENETRATION, -1),
        damage_profile=DamageProfile.fixed(1),
    )
    save_sequence_id = "phase17k-cover-denial-save-consumer"
    attack_context_id = f"{save_sequence_id}:pool-001:attack-001"
    hit_spec = attack_sequence_hit_roll_spec(
        weapon_profile_id=weapon_profile.profile_id,
        attack_context_id=attack_context_id,
        attacker_player_id=army.player_id,
    )
    wound_spec = attack_sequence_wound_roll_spec(
        weapon_profile_id=weapon_profile.profile_id,
        attack_context_id=attack_context_id,
        attacker_player_id=army.player_id,
    )
    save_spec = saving_throw_roll_spec(
        save_kind=SaveKind.ARMOUR,
        player_id=enemy_army.player_id,
        allocated_model_id=target_model.model_instance_id,
        attack_context_id=attack_context_id,
    )
    base_ruleset = RulesetDescriptor.warhammer_40000_eleventh()
    save_bonus_ruleset = replace(
        base_ruleset,
        terrain_visibility_policy=replace(
            base_ruleset.terrain_visibility_policy,
            cover_effect=CoverEffect.SAVE_BONUS,
            cover_policy=CoverPolicyDescriptor(cover_effect=CoverEffect.SAVE_BONUS),
        ),
        descriptor_hash="",
    )

    remaining_sequence, allocated_model_ids, resolve_status = resolve_attack_sequence_until_blocked(
        state=state,
        decisions=decisions,
        ruleset_descriptor=save_bonus_ruleset,
        attack_sequence=AttackSequence.start(
            sequence_id=save_sequence_id,
            attacker_player_id=army.player_id,
            attacking_unit_instance_id=unit.unit_instance_id,
            attack_pools=(
                replace(
                    completed_sequence.attack_pools[0],
                    weapon_profile_id=weapon_profile.profile_id,
                    weapon_profile=weapon_profile,
                ),
            ),
        ),
        already_allocated_model_ids=(),
        dice_manager=DiceRollManager(
            save_sequence_id,
            event_log=decisions.event_log,
            injected_results=(
                DiceRollResult.from_values(
                    roll_id=f"{save_sequence_id}:hit",
                    spec=hit_spec,
                    values=(6,),
                    source="fixed",
                ),
                DiceRollResult.from_values(
                    roll_id=f"{save_sequence_id}:wound",
                    spec=wound_spec,
                    values=(6,),
                    source="fixed",
                ),
                DiceRollResult.from_values(
                    roll_id=f"{save_sequence_id}:save",
                    spec=save_spec,
                    values=(2,),
                    source="fixed",
                ),
            ),
        ),
        runtime_modifier_registry=RuntimeModifierRegistry.empty(),
    )
    save_events = tuple(
        cast(dict[str, object], event.payload)
        for event in decisions.event_log.records
        if event.event_type == "attack_sequence_step"
        and cast(dict[str, object], event.payload).get("sequence_id") == save_sequence_id
        and cast(dict[str, object], event.payload).get("step") == AttackSequenceStep.SAVE.value
    )
    assert len(save_events) == 1
    save_payload = cast(dict[str, object], save_events[0]["payload"])
    save_option = cast(dict[str, object], save_payload["option"])

    assert remaining_sequence is None
    assert allocated_model_ids == (target_model.model_instance_id,)
    assert resolve_status is None
    assert save_payload["save_kind"] == SaveKind.ARMOUR.value
    assert save_payload["target_number"] == 2
    assert save_payload["unmodified_roll"] == 2
    assert save_payload["final_roll"] == 1
    assert save_payload["successful"] is False
    assert save_payload["resolution_rule"] == SaveResolutionRule.FAILED.value
    assert save_option["target_number"] == 3
    assert save_option["cover_result"] is None
    assert save_option["cover_applied"] is False
    assert save_option["source_rule_ids"] == []


def test_phase17k_post_shoot_hit_target_status_requires_successful_hit_not_wound() -> None:
    package = _post_shoot_cover_denial_package()
    unit = _named_weapon_choice_unit(package=package)
    target_unit = _named_weapon_choice_unit(
        package=package,
        army_id="army-opponent",
        unit_selection_id="enemy-lord-of-change-1",
    )
    army = _flesh_hounds_army(package=package, unit=unit)
    enemy_army = _flesh_hounds_army(
        package=package,
        unit=target_unit,
        army_id="army-opponent",
        player_id="player-opponent",
    )
    player_index = _player_ability_index(package=package, army=army)
    enemy_player_index = _player_ability_index(package=package, army=enemy_army)
    battlefield = _flesh_hounds_battlefield_state(
        army=army,
        unit=unit,
        enemy_army=enemy_army,
        enemy_unit=target_unit,
        enemy_x=24.0,
    )
    state = _battle_state_with_armies(
        armies=(army, enemy_army),
        battlefield=battlefield,
        active_player_id=army.player_id,
        phase=BattlePhase.SHOOTING,
    )
    attack_sequence = _completed_post_shoot_attack_sequence(
        package=package,
        attacker=unit,
        target=target_unit,
    )
    runtime = CatalogPostShootHitTargetStatusRuntime(
        ability_indexes_by_player_id={
            army.player_id: player_index,
            enemy_army.player_id: enemy_player_index,
        },
        armies=(army, enemy_army),
    )

    miss_decisions = DecisionController()
    _emit_successful_hit(
        decisions=miss_decisions,
        attack_sequence=attack_sequence,
        successful=False,
    )
    miss_completed_event = miss_decisions.event_log.append(
        "attack_sequence_completed",
        {
            "sequence_id": attack_sequence.sequence_id,
            "attacker_player_id": army.player_id,
            "attacking_unit_instance_id": unit.unit_instance_id,
        },
    )
    miss_context = AttackSequenceCompletedContext(
        state=state,
        decisions=miss_decisions,
        dice_manager=DiceRollManager(state.game_id, event_log=miss_decisions.event_log),
        runtime_modifier_registry=RuntimeModifierRegistry.empty(),
        source_phase=BattlePhase.SHOOTING,
        attack_sequence=attack_sequence,
        attack_sequence_completed_event_id=miss_completed_event.event_id,
    )

    assert (
        successful_hit_target_unit_ids_for_sequence(
            decisions=miss_decisions,
            sequence=attack_sequence,
        )
        == ()
    )
    assert (
        _available_catalog_post_shoot_hit_target_status_groups(
            ability_indexes_by_player_id={army.player_id: player_index},
            armies=(army, enemy_army),
            context=miss_context,
        )
        == ()
    )
    assert runtime.request_handler(miss_context) is None
    assert miss_decisions.queue.pending_requests == ()

    failed_wound_decisions = DecisionController()
    _emit_successful_hit(
        decisions=failed_wound_decisions,
        attack_sequence=attack_sequence,
        successful=True,
    )
    _emit_wound_result(
        decisions=failed_wound_decisions,
        attack_sequence=attack_sequence,
        successful=False,
    )
    failed_wound_completed_event = failed_wound_decisions.event_log.append(
        "attack_sequence_completed",
        {
            "sequence_id": attack_sequence.sequence_id,
            "attacker_player_id": army.player_id,
            "attacking_unit_instance_id": unit.unit_instance_id,
        },
    )
    failed_wound_context = AttackSequenceCompletedContext(
        state=state,
        decisions=failed_wound_decisions,
        dice_manager=DiceRollManager(state.game_id, event_log=failed_wound_decisions.event_log),
        runtime_modifier_registry=RuntimeModifierRegistry.empty(),
        source_phase=BattlePhase.SHOOTING,
        attack_sequence=attack_sequence,
        attack_sequence_completed_event_id=failed_wound_completed_event.event_id,
    )
    failed_wound_groups = _available_catalog_post_shoot_hit_target_status_groups(
        ability_indexes_by_player_id={army.player_id: player_index},
        armies=(army, enemy_army),
        context=failed_wound_context,
    )
    failed_wound_status = runtime.request_handler(failed_wound_context)

    assert successful_hit_target_unit_ids_for_sequence(
        decisions=failed_wound_decisions,
        sequence=attack_sequence,
    ) == (target_unit.unit_instance_id,)
    assert len(failed_wound_groups) == 1
    assert failed_wound_status is not None
    assert failed_wound_status.status_kind is LifecycleStatusKind.WAITING_FOR_DECISION
    assert failed_wound_decisions.queue.peek_next().decision_type == (
        SELECT_CATALOG_POST_SHOOT_HIT_TARGET_STATUS_DECISION_TYPE
    )


def test_phase17k_post_shoot_hit_target_status_processes_all_source_groups() -> None:
    package = _post_shoot_cover_denial_package()
    unit = _named_weapon_choice_unit(package=package, model_count=2)
    target_unit = _named_weapon_choice_unit(
        package=package,
        army_id="army-opponent",
        unit_selection_id="enemy-lord-of-change-1",
    )
    army = _flesh_hounds_army(package=package, unit=unit)
    enemy_army = _flesh_hounds_army(
        package=package,
        unit=target_unit,
        army_id="army-opponent",
        player_id="player-opponent",
    )
    player_index = _player_ability_index(package=package, army=army)
    enemy_player_index = _player_ability_index(package=package, army=enemy_army)
    battlefield = _flesh_hounds_battlefield_state(
        army=army,
        unit=unit,
        enemy_army=enemy_army,
        enemy_unit=target_unit,
        enemy_x=24.0,
    )
    state = _battle_state_with_armies(
        armies=(army, enemy_army),
        battlefield=battlefield,
        active_player_id=army.player_id,
        phase=BattlePhase.SHOOTING,
    )
    decisions = DecisionController()
    attacker_model_ids = tuple(sorted(model.model_instance_id for model in unit.own_models))
    attack_sequence = _completed_post_shoot_attack_sequence(
        package=package,
        attacker=unit,
        target=target_unit,
        attacker_model_instance_ids=attacker_model_ids,
    )
    for pool_index in range(len(attack_sequence.attack_pools)):
        _emit_successful_hit(
            decisions=decisions,
            attack_sequence=attack_sequence,
            successful=True,
            pool_index=pool_index,
        )
    decisions.event_log.append(
        "attack_sequence_completed",
        {
            "sequence_id": attack_sequence.sequence_id,
            "attacker_player_id": army.player_id,
            "attacking_unit_instance_id": unit.unit_instance_id,
        },
    )
    state.shooting_phase_state = ShootingPhaseState(
        battle_round=state.battle_round,
        active_player_id=army.player_id,
        shot_unit_ids=(unit.unit_instance_id,),
        attack_pools=attack_sequence.attack_pools,
        pending_completed_attack_sequence=attack_sequence,
    )
    handler = ShootingPhaseHandler(
        ruleset_descriptor=RulesetDescriptor.warhammer_40000_eleventh(),
        army_catalog=package.army_catalog,
        stratagem_index=StratagemCatalogIndex.from_records(()),
        attack_sequence_completed_hooks=AttackSequenceCompletedHookRegistry.from_bindings(
            CatalogPostShootHitTargetStatusRuntime(
                ability_indexes_by_player_id={
                    army.player_id: player_index,
                    enemy_army.player_id: enemy_player_index,
                },
                armies=(army, enemy_army),
            ).bindings()
        ),
        runtime_modifier_registry=RuntimeModifierRegistry.empty(),
    )

    first_status = handler.begin_phase(state=state, decisions=decisions)
    assert first_status.status_kind is LifecycleStatusKind.WAITING_FOR_DECISION
    first_request = decisions.queue.peek_next()
    first_payload = cast(dict[str, JsonValue], first_request.payload)
    assert first_payload["source_model_instance_id"] == attacker_model_ids[0]
    assert _pending_completed_attack_sequence_for_test(state) == attack_sequence

    first_result = DecisionResult.for_request(
        result_id="phase17k-post-shoot-cover-denial-source-001",
        request=first_request,
        selected_option_id=first_request.options[0].option_id,
    )
    decisions.submit_result(first_result)
    assert handler.apply_decision(state=state, result=first_result, decisions=decisions) is None

    second_status = handler.begin_phase(state=state, decisions=decisions)
    assert second_status.status_kind is LifecycleStatusKind.WAITING_FOR_DECISION
    second_request = decisions.queue.peek_next()
    second_payload = cast(dict[str, JsonValue], second_request.payload)
    assert second_request.request_id != first_request.request_id
    assert second_request.decision_type == SELECT_CATALOG_POST_SHOOT_HIT_TARGET_STATUS_DECISION_TYPE
    assert second_payload["source_model_instance_id"] == attacker_model_ids[1]
    assert _pending_completed_attack_sequence_for_test(state) == attack_sequence

    second_result = DecisionResult.for_request(
        result_id="phase17k-post-shoot-cover-denial-source-002",
        request=second_request,
        selected_option_id=second_request.options[0].option_id,
    )
    decisions.submit_result(second_result)
    assert handler.apply_decision(state=state, result=second_result, decisions=decisions) is None

    completion_status = handler.begin_phase(state=state, decisions=decisions)
    assert completion_status.status_kind is LifecycleStatusKind.ADVANCED
    assert _pending_completed_attack_sequence_for_test(state) is None
    selected_events = tuple(
        event
        for event in decisions.event_log.records
        if event.event_type == CATALOG_POST_SHOOT_HIT_TARGET_STATUS_SELECTED_EVENT
    )
    requested_events = tuple(
        event
        for event in decisions.event_log.records
        if event.event_type == "catalog_post_shoot_hit_target_status_requested"
    )
    effects = state.persisting_effects_for_unit(target_unit.unit_instance_id)

    assert len(requested_events) == 2
    assert len(selected_events) == 2
    assert [
        cast(dict[str, JsonValue], event.payload)["source_model_instance_id"]
        for event in selected_events
    ] == list(attacker_model_ids)
    assert len(effects) == 2
    assert all(
        cast(dict[str, JsonValue], effect.effect_payload)["effect_kind"]
        == CATALOG_POST_SHOOT_HIT_TARGET_STATUS_EFFECT_KIND
        for effect in effects
    )
    assert "object at 0x" not in json.dumps(decisions.to_payload(), sort_keys=True)


def test_phase17k_charge_end_catalog_mortal_wounds_selects_target_and_rolls_per_model() -> None:
    package = _flesh_hounds_package()
    unit = _flesh_hounds_unit(package=package)
    target_unit = _flesh_hounds_unit(
        package=package,
        army_id="army-opponent",
        unit_selection_id="enemy-flesh-hounds-1",
    )
    army = _flesh_hounds_army(package=package, unit=unit)
    enemy_army = _flesh_hounds_army(
        package=package,
        unit=target_unit,
        army_id="army-opponent",
        player_id="player-opponent",
    )
    rule_ir = _charge_end_mortal_wounds_rule_ir()
    clause = rule_ir.clauses[0]
    distance_conditions = tuple(
        condition
        for condition in clause.conditions
        if condition.kind is RuleConditionKind.DISTANCE_PREDICATE
    )
    effect_parameters = parameter_payload(clause.effects[0].parameters)
    record = _charge_end_mortal_wounds_record(rule_ir=rule_ir, datasheet_id=unit.datasheet_id)
    ability_index = AbilityCatalogIndex.from_records((record,))
    enemy_index = AbilityCatalogIndex.from_records(())
    ruleset = RulesetDescriptor.warhammer_40000_eleventh()
    battlefield = _flesh_hounds_battlefield_state(
        army=army,
        unit=unit,
        enemy_army=enemy_army,
        enemy_unit=target_unit,
        enemy_x=13.0,
    )
    state = _battle_state_with_armies(
        armies=(army, enemy_army),
        battlefield=battlefield,
        active_player_id=army.player_id,
        phase=BattlePhase.CHARGE,
    )
    state.game_id = "phase17k-charge-mw-7"
    decisions = DecisionController()
    runtime = CatalogUnitMoveCompletedMortalWoundsRuntime(
        ability_indexes_by_player_id={
            army.player_id: ability_index,
            enemy_army.player_id: enemy_index,
        },
        armies=(army, enemy_army),
    )
    registry = UnitMoveCompletedMortalWoundHookRegistry.from_bindings(runtime.bindings())

    assert rule_ir.is_supported
    assert clause.target is not None
    assert clause.target.kind is RuleTargetKind.ENEMY_UNIT
    assert len(distance_conditions) == 1
    distance_parameters = parameter_payload(distance_conditions[0].parameters)
    assert distance_parameters["negated"] is False
    assert distance_parameters["object_kind"] == "unit"
    assert distance_parameters["object_reference"] == "this"
    assert distance_parameters["predicate"] == "within_engagement_range"
    assert distance_parameters["range_kind"] == "engagement_range"
    assert clause.effects[0].kind is RuleEffectKind.INFLICT_MORTAL_WOUNDS
    assert effect_parameters == {
        "damage_kind": "mortal_wounds",
        "mortal_wounds_expression": "D3",
        "roll_count": 1,
        "roll_count_scope": "each_model_in_this_unit",
        "roll_expression": "D6",
        "success_threshold": 4,
        "target_scope": "selected_enemy_unit",
    }
    assert _clause_is_supported_unit_move_completed_mortal_wounds(clause)
    assert _record_can_select_catalog_unit_move_completed_mortal_wounds_target(record)
    assert catalog_rule_ir_consumers_for_rule(rule_ir) == (
        CATALOG_IR_UNIT_MOVE_COMPLETED_MORTAL_WOUNDS_CONSUMER_ID,
    )
    assert catalog_rule_ir_hook_ids_for_rule(rule_ir) == (
        CATALOG_IR_UNIT_MOVE_COMPLETED_MORTAL_WOUNDS_CONSUMER_ID,
    )

    decisions.event_log.append(
        "charge_move_completed",
        {
            "game_id": state.game_id,
            "battle_round": state.battle_round,
            "phase": BattlePhase.CHARGE.value,
            "active_player_id": army.player_id,
            "unit_instance_id": unit.unit_instance_id,
            "movement_phase_action": "charge_move",
        },
    )
    status = resolve_unit_move_completed_mortal_wound_hooks(
        state=state,
        decisions=decisions,
        registry=registry,
        ruleset_descriptor=ruleset,
        runtime_modifier_registry=RuntimeModifierRegistry.empty(),
        completed_phase=BattlePhase.CHARGE,
        event_type="charge_move_completed",
        movement_actions=("charge_move",),
    )

    assert status is not None
    assert status.status_kind is LifecycleStatusKind.WAITING_FOR_DECISION
    request = status.decision_request
    assert request is not None
    request_payload = cast(dict[str, object], request.payload)
    assert (
        request.decision_type
        == SELECT_CATALOG_UNIT_MOVE_COMPLETED_MORTAL_WOUNDS_TARGET_DECISION_TYPE
    )
    assert request.actor_id == army.player_id
    assert type(request).from_payload(request.to_payload()).to_payload() == request.to_payload()
    assert request_payload["submission_kind"] == (
        SELECT_CATALOG_UNIT_MOVE_COMPLETED_MORTAL_WOUNDS_TARGET_SUBMISSION_KIND
    )
    assert request_payload["roll_model_instance_ids"] == [
        model.model_instance_id for model in unit.own_models
    ]
    assert [option.payload for option in request.options] == [
        {
            **{
                key: value
                for key, value in request_payload.items()
                if key
                not in {
                    "available_target_unit_instance_ids",
                    "available_unit_move_completed_mortal_wounds_target_options",
                }
            },
            "selected_unit_move_completed_mortal_wounds_target": {
                "option_id": request.options[0].option_id,
                "target_unit_instance_id": target_unit.unit_instance_id,
                "target_player_id": enemy_army.player_id,
            },
        }
    ]

    result = DecisionResult.for_request(
        result_id="phase17k-charge-mw-target",
        request=request,
        selected_option_id=request.options[0].option_id,
    )
    stale_state = _battle_state_with_armies(
        armies=(army, enemy_army),
        battlefield=battlefield,
        active_player_id=army.player_id,
        phase=BattlePhase.FIGHT,
    )
    stale_state.game_id = state.game_id
    stale_status = invalid_catalog_unit_move_completed_mortal_wounds_target_status(
        state=stale_state,
        request=request,
        result=result,
        ruleset_descriptor=ruleset,
    )
    assert stale_status is not None
    stale_payload = cast(dict[str, JsonValue], stale_status.payload)
    assert stale_payload["invalid_reason"] == "phase_drift"

    drifted_state = _battle_state_with_armies(
        armies=(army, enemy_army),
        battlefield=_flesh_hounds_battlefield_state(
            army=army,
            unit=unit,
            enemy_army=enemy_army,
            enemy_unit=target_unit,
            enemy_x=30.0,
        ),
        active_player_id=army.player_id,
        phase=BattlePhase.CHARGE,
    )
    drifted_state.game_id = state.game_id
    drift_status = invalid_catalog_unit_move_completed_mortal_wounds_target_status(
        state=drifted_state,
        request=request,
        result=result,
        ruleset_descriptor=ruleset,
    )
    assert drift_status is not None
    drift_payload = cast(dict[str, JsonValue], drift_status.payload)
    assert drift_payload["invalid_reason"] == "target_drift"

    malformed_status = invalid_catalog_unit_move_completed_mortal_wounds_target_status(
        state=state,
        request=request,
        result=DecisionResult(
            result_id="phase17k-charge-mw-target-malformed",
            request_id=request.request_id,
            decision_type=request.decision_type,
            actor_id=request.actor_id,
            selected_option_id="phase17k-missing-option",
            payload=request.options[0].payload,
        ),
        ruleset_descriptor=ruleset,
    )
    assert malformed_status is not None
    malformed_payload = cast(dict[str, JsonValue], malformed_status.payload)
    assert malformed_payload["field"] == "selected_option_id"

    base_request_payload = cast(dict[str, JsonValue], request.payload)
    base_option_payload = cast(dict[str, JsonValue], request.options[0].payload)

    def invalid_reason_for_payload(
        *,
        expected_reason: str,
        option_payload: dict[str, JsonValue],
        request_payload: dict[str, JsonValue] | JsonValue | None = None,
    ) -> str:
        updated_request = replace(
            request,
            payload=validate_json_value(
                base_request_payload if request_payload is None else request_payload
            ),
            options=(
                replace(
                    request.options[0],
                    payload=validate_json_value(option_payload),
                ),
            ),
        )
        status = invalid_catalog_unit_move_completed_mortal_wounds_target_status(
            state=state,
            request=updated_request,
            result=DecisionResult(
                result_id=f"phase17k-charge-mw-target-{expected_reason}",
                request_id=updated_request.request_id,
                decision_type=updated_request.decision_type,
                actor_id=updated_request.actor_id,
                selected_option_id=updated_request.options[0].option_id,
                payload=validate_json_value(option_payload),
            ),
            ruleset_descriptor=ruleset,
        )
        assert status is not None
        payload = cast(dict[str, JsonValue], status.payload)
        return cast(str, payload["invalid_reason"])

    for key, value, expected_reason in (
        ("submission_kind", "changed", "submission_kind_drift"),
        ("hook_id", "changed", "hook_id_drift"),
        ("game_id", "changed", "game_id_drift"),
        ("battle_round", 2, "battle_round_drift"),
        ("phase", BattlePhase.FIGHT.value, "payload_phase_drift"),
        ("active_player_id", enemy_army.player_id, "active_player_drift"),
        ("player_id", enemy_army.player_id, "actor_player_drift"),
    ):
        payload = dict(base_option_payload)
        payload[key] = cast(JsonValue, value)
        assert (
            invalid_reason_for_payload(
                expected_reason=expected_reason,
                option_payload=payload,
            )
            == expected_reason
        )

    for key, value, expected_reason in (
        ("hook_id", "changed", "request_hook_id_drift"),
        ("game_id", "changed", "request_game_id_drift"),
        ("battle_round", 2, "request_battle_round_drift"),
        ("phase", BattlePhase.FIGHT.value, "request_phase_drift"),
        ("active_player_id", enemy_army.player_id, "request_active_player_drift"),
    ):
        payload = dict(base_request_payload)
        payload[key] = cast(JsonValue, value)
        assert (
            invalid_reason_for_payload(
                expected_reason=expected_reason,
                option_payload=dict(base_option_payload),
                request_payload=payload,
            )
            == expected_reason
        )

    selected_not_object_payload = dict(base_option_payload)
    selected_not_object_payload["selected_unit_move_completed_mortal_wounds_target"] = "changed"
    assert (
        invalid_reason_for_payload(
            expected_reason="selected_payload_not_object",
            option_payload=selected_not_object_payload,
        )
        == "selected_payload_not_object"
    )

    selected_option_drift_payload = dict(base_option_payload)
    selected_payload = dict(
        cast(
            dict[str, JsonValue],
            selected_option_drift_payload["selected_unit_move_completed_mortal_wounds_target"],
        )
    )
    selected_payload["option_id"] = "changed"
    selected_option_drift_payload["selected_unit_move_completed_mortal_wounds_target"] = (
        selected_payload
    )
    assert (
        invalid_reason_for_payload(
            expected_reason="selected_option_payload_drift",
            option_payload=selected_option_drift_payload,
        )
        == "selected_option_payload_drift"
    )

    selected_target_type_payload = dict(base_option_payload)
    selected_payload = dict(
        cast(
            dict[str, JsonValue],
            selected_target_type_payload["selected_unit_move_completed_mortal_wounds_target"],
        )
    )
    selected_payload["target_unit_instance_id"] = 1
    selected_target_type_payload["selected_unit_move_completed_mortal_wounds_target"] = (
        selected_payload
    )
    assert (
        invalid_reason_for_payload(
            expected_reason="selected_target_payload_drift",
            option_payload=selected_target_type_payload,
        )
        == "selected_target_payload_drift"
    )

    source_rules_unit_type_payload = dict(base_option_payload)
    source_rules_unit_type_payload["source_rules_unit_instance_id"] = 1
    assert (
        invalid_reason_for_payload(
            expected_reason="source_rules_unit_payload_drift",
            option_payload=source_rules_unit_type_payload,
        )
        == "source_rules_unit_payload_drift"
    )

    source_rules_unit_owner_payload = dict(base_option_payload)
    source_rules_unit_owner_payload["source_rules_unit_instance_id"] = target_unit.unit_instance_id
    assert (
        invalid_reason_for_payload(
            expected_reason="source_rules_unit_owner_drift",
            option_payload=source_rules_unit_owner_payload,
        )
        == "source_rules_unit_owner_drift"
    )

    assert (
        invalid_catalog_unit_move_completed_mortal_wounds_target_status(
            state=state,
            request=request,
            result=result,
            ruleset_descriptor=ruleset,
        )
        is None
    )
    decisions.submit_result(result)
    assert (
        apply_catalog_unit_move_completed_mortal_wounds_target_result(
            state=state,
            decisions=decisions,
            result=result,
            ruleset_descriptor=ruleset,
        )
        is None
    )
    selected_events = tuple(
        event
        for event in decisions.event_log.records
        if event.event_type == CATALOG_UNIT_MOVE_COMPLETED_MORTAL_WOUNDS_TARGET_SELECTED_EVENT
    )
    assert len(selected_events) == 1
    selected_payload = cast(dict[str, JsonValue], selected_events[0].payload)
    assert selected_payload["target_unit_instance_id"] == target_unit.unit_instance_id

    assert (
        resolve_unit_move_completed_mortal_wound_hooks(
            state=state,
            decisions=decisions,
            registry=registry,
            ruleset_descriptor=ruleset,
            runtime_modifier_registry=RuntimeModifierRegistry.empty(),
            completed_phase=BattlePhase.CHARGE,
            event_type="charge_move_completed",
            movement_actions=("charge_move",),
        )
        is None
    )
    rolled_events = tuple(
        event
        for event in decisions.event_log.records
        if event.event_type == UNIT_MOVE_COMPLETED_MORTAL_WOUNDS_ROLLED_EVENT
    )
    assert len(rolled_events) == len(unit.own_models)
    rolled_model_ids: set[str] = set()
    for event in rolled_events:
        payload = cast(dict[str, JsonValue], event.payload)
        assert payload["hook_id"] == CATALOG_IR_UNIT_MOVE_COMPLETED_MORTAL_WOUNDS_CONSUMER_ID
        assert payload["source_rule_id"] == record.definition.source_id
        assert payload["source_rule_id"] != CATALOG_IR_UNIT_MOVE_COMPLETED_MORTAL_WOUNDS_CONSUMER_ID
        replay_payload = cast(
            dict[str, JsonValue],
            payload["replay_payload"],
        )
        assert replay_payload["catalog_source_rule_id"] == record.definition.source_id
        roll_model_id = replay_payload["roll_model_instance_id"]
        assert type(roll_model_id) is str
        rolled_model_ids.add(roll_model_id)
    assert rolled_model_ids == {model.model_instance_id for model in unit.own_models}
    assert "object at 0x" not in json.dumps(decisions.to_payload(), sort_keys=True)


def test_phase17k_charge_end_catalog_mortal_wounds_runtime_noops_and_fail_fast() -> None:
    package = _flesh_hounds_package()
    unit = _flesh_hounds_unit(package=package)
    target_unit = _flesh_hounds_unit(
        package=package,
        army_id="army-opponent",
        unit_selection_id="enemy-flesh-hounds-1",
    )
    army = _flesh_hounds_army(package=package, unit=unit)
    enemy_army = _flesh_hounds_army(
        package=package,
        unit=target_unit,
        army_id="army-opponent",
        player_id="player-opponent",
    )
    rule_ir = _charge_end_mortal_wounds_rule_ir()
    record = _charge_end_mortal_wounds_record(rule_ir=rule_ir, datasheet_id=unit.datasheet_id)
    ability_index = AbilityCatalogIndex.from_records((record,))
    enemy_index = AbilityCatalogIndex.from_records(())
    empty_index = AbilityCatalogIndex.from_records(())
    ruleset = RulesetDescriptor.warhammer_40000_eleventh()
    state = _battle_state_with_armies(
        armies=(army, enemy_army),
        battlefield=_flesh_hounds_battlefield_state(
            army=army,
            unit=unit,
            enemy_army=enemy_army,
            enemy_unit=target_unit,
            enemy_x=30.0,
        ),
        active_player_id=army.player_id,
        phase=BattlePhase.CHARGE,
    )
    decisions = DecisionController()
    context = UnitMoveCompletedContext(
        state=state,
        ruleset_descriptor=ruleset,
        runtime_modifier_registry=RuntimeModifierRegistry.empty(),
        completed_phase=BattlePhase.CHARGE,
        trigger_event_id="charge-move-completed-001",
        trigger_event_payload={
            "unit_instance_id": unit.unit_instance_id,
            "movement_phase_action": "charge_move",
        },
        triggering_unit_instance_id=unit.unit_instance_id,
        triggering_player_id=army.player_id,
        movement_action="charge_move",
        decisions=decisions,
    )

    with pytest.raises(GameLifecycleError, match="missing player ability index"):
        CatalogUnitMoveCompletedMortalWoundsRuntime(
            ability_indexes_by_player_id={army.player_id: ability_index},
            armies=(army, enemy_army),
        )

    empty_runtime = CatalogUnitMoveCompletedMortalWoundsRuntime(
        ability_indexes_by_player_id={
            army.player_id: empty_index,
            enemy_army.player_id: empty_index,
        },
        armies=(army, enemy_army),
    )
    runtime = CatalogUnitMoveCompletedMortalWoundsRuntime(
        ability_indexes_by_player_id={
            army.player_id: ability_index,
            enemy_army.player_id: enemy_index,
        },
        armies=(army, enemy_army),
    )

    assert empty_runtime.bindings() == ()
    with pytest.raises(GameLifecycleError, match="requires context"):
        runtime.request_handler(cast(UnitMoveCompletedContext, object()))
    with pytest.raises(GameLifecycleError, match="requires context"):
        runtime.effect_handler(cast(UnitMoveCompletedContext, object()))
    assert runtime.request_handler(context) is None
    assert runtime.effect_handler(context) == ()


def test_phase17k_post_shoot_hit_target_status_uses_runtime_clause_scoped_records() -> None:
    package = _post_shoot_cover_denial_package()
    unit = _named_weapon_choice_unit(package=package)
    target_unit = _named_weapon_choice_unit(
        package=package,
        army_id="army-opponent",
        unit_selection_id="enemy-lord-of-change-1",
    )
    army = _flesh_hounds_army(package=package, unit=unit)
    enemy_army = _flesh_hounds_army(
        package=package,
        unit=target_unit,
        army_id="army-opponent",
        player_id="player-opponent",
    )
    rule_ir = _multi_clause_post_shoot_cover_denial_rule_ir()
    clause_001_record = _multi_clause_post_shoot_cover_denial_record(
        rule_ir=rule_ir,
        clause_index=0,
        datasheet_id=unit.datasheet_id,
        trigger_kind=TimingTriggerKind.PASSIVE_QUERY,
    )
    clause_002_record = _multi_clause_post_shoot_cover_denial_record(
        rule_ir=rule_ir,
        clause_index=1,
        datasheet_id=unit.datasheet_id,
        trigger_kind=TimingTriggerKind.JUST_AFTER_FRIENDLY_UNIT_HAS_SHOT,
    )
    ability_index = AbilityCatalogIndex.from_records((clause_001_record, clause_002_record))
    enemy_ability_index = AbilityCatalogIndex.from_records(())
    battlefield = _flesh_hounds_battlefield_state(
        army=army,
        unit=unit,
        enemy_army=enemy_army,
        enemy_unit=target_unit,
        enemy_x=24.0,
    )
    state = _battle_state_with_armies(
        armies=(army, enemy_army),
        battlefield=battlefield,
        active_player_id=army.player_id,
        phase=BattlePhase.SHOOTING,
    )
    decisions = DecisionController()
    attack_sequence = _completed_post_shoot_attack_sequence(
        package=package,
        attacker=unit,
        attacker_player_id=army.player_id,
        target=target_unit,
    )
    _emit_successful_hit(
        decisions=decisions,
        attack_sequence=attack_sequence,
        successful=True,
    )
    completed_event = decisions.event_log.append(
        "attack_sequence_completed",
        {
            "sequence_id": attack_sequence.sequence_id,
            "attacker_player_id": army.player_id,
            "attacking_unit_instance_id": unit.unit_instance_id,
        },
    )
    context = AttackSequenceCompletedContext(
        state=state,
        decisions=decisions,
        dice_manager=DiceRollManager(state.game_id, event_log=decisions.event_log),
        runtime_modifier_registry=RuntimeModifierRegistry.empty(),
        source_phase=BattlePhase.SHOOTING,
        attack_sequence=attack_sequence,
        attack_sequence_completed_event_id=completed_event.event_id,
    )

    groups = _available_catalog_post_shoot_hit_target_status_groups(
        ability_indexes_by_player_id={army.player_id: ability_index},
        armies=(army, enemy_army),
        context=context,
    )
    status = CatalogPostShootHitTargetStatusRuntime(
        ability_indexes_by_player_id={
            army.player_id: ability_index,
            enemy_army.player_id: enemy_ability_index,
        },
        armies=(army, enemy_army),
    ).request_handler(context)

    assert not _record_can_select_catalog_post_shoot_hit_target_status(clause_001_record)
    assert _record_can_select_catalog_post_shoot_hit_target_status(clause_002_record)
    assert len(groups) == 1
    assert groups[0].record.record_id == clause_002_record.record_id
    assert groups[0].clause.clause_id == rule_ir.clauses[1].clause_id
    assert status is not None
    assert status.status_kind is LifecycleStatusKind.WAITING_FOR_DECISION
    request = decisions.queue.peek_next()
    assert request is not None
    request_payload = cast(dict[str, JsonValue], request.payload)
    assert request_payload["catalog_record_id"] == clause_002_record.record_id
    assert len(request.options) == 1


def test_phase17k_post_shoot_hit_target_status_fail_fast_validation_paths() -> None:
    package = _post_shoot_cover_denial_package()
    unit = _named_weapon_choice_unit(package=package)
    target_unit = _named_weapon_choice_unit(
        package=package,
        army_id="army-opponent",
        unit_selection_id="enemy-lord-of-change-1",
    )
    army = _flesh_hounds_army(package=package, unit=unit)
    enemy_army = _flesh_hounds_army(
        package=package,
        unit=target_unit,
        army_id="army-opponent",
        player_id="player-opponent",
    )
    player_index = _player_ability_index(package=package, army=army)
    enemy_player_index = _player_ability_index(package=package, army=enemy_army)
    records_by_name = {record.definition.name: record for record in player_index.all_records()}
    cover_record = records_by_name["Purge and Cleanse"]
    replay_payload = cast(dict[str, JsonValue], cover_record.definition.replay_payload)
    rule_ir = RuleIR.from_payload(cast(RuleIRPayload, replay_payload["rule_ir"]))
    clause = rule_ir.clauses[0]
    current_model_ids = (unit.own_models[0].model_instance_id,)
    battlefield = _flesh_hounds_battlefield_state(
        army=army,
        unit=unit,
        enemy_army=enemy_army,
        enemy_unit=target_unit,
        enemy_x=24.0,
    )
    state = _battle_state_with_armies(
        armies=(army, enemy_army),
        battlefield=battlefield,
        active_player_id=army.player_id,
        phase=BattlePhase.SHOOTING,
    )
    decisions = DecisionController()
    attack_sequence = _completed_post_shoot_attack_sequence(
        package=package,
        attacker=unit,
        target=target_unit,
    )
    completed_event = decisions.event_log.append(
        "attack_sequence_completed",
        {
            "sequence_id": attack_sequence.sequence_id,
            "attacker_player_id": army.player_id,
            "attacking_unit_instance_id": unit.unit_instance_id,
        },
    )
    context = AttackSequenceCompletedContext(
        state=state,
        decisions=decisions,
        dice_manager=DiceRollManager(state.game_id, event_log=decisions.event_log),
        runtime_modifier_registry=RuntimeModifierRegistry.empty(),
        source_phase=BattlePhase.SHOOTING,
        attack_sequence=attack_sequence,
        attack_sequence_completed_event_id=completed_event.event_id,
    )

    assert (
        CatalogPostShootHitTargetStatusRuntime(
            ability_indexes_by_player_id={
                army.player_id: player_index,
                enemy_army.player_id: enemy_player_index,
            },
            armies=(army, enemy_army),
        )
        .bindings()[0]
        .hook_id
        == CATALOG_IR_POST_SHOOT_HIT_TARGET_STATUS_CONSUMER_ID
    )
    assert (
        CatalogPostShootHitTargetStatusRuntime(
            ability_indexes_by_player_id={
                army.player_id: AbilityCatalogIndex.from_records(()),
                enemy_army.player_id: AbilityCatalogIndex.from_records(()),
            },
            armies=(army, enemy_army),
        ).bindings()
        == ()
    )
    assert (
        _available_catalog_post_shoot_hit_target_status_groups(
            ability_indexes_by_player_id={army.player_id: player_index},
            armies=(army, enemy_army),
            context=context,
        )
        == ()
    )
    with pytest.raises(GameLifecycleError, match="requires context"):
        _available_catalog_post_shoot_hit_target_status_groups(
            ability_indexes_by_player_id={army.player_id: player_index},
            armies=(army, enemy_army),
            context=cast(Any, object()),
        )
    with pytest.raises(GameLifecycleError, match="index is missing player"):
        _available_catalog_post_shoot_hit_target_status_groups(
            ability_indexes_by_player_id={},
            armies=(army, enemy_army),
            context=context,
        )
    with pytest.raises(GameLifecycleError, match="requires an ability record"):
        _catalog_post_shoot_hit_target_status_groups_from_clause(
            context=context,
            record=cast(Any, object()),
            unit=unit,
            current_model_instance_ids=current_model_ids,
            clause=clause,
        )
    with pytest.raises(GameLifecycleError, match="requires a rule clause"):
        _catalog_post_shoot_hit_target_status_groups_from_clause(
            context=context,
            record=cover_record,
            unit=unit,
            current_model_instance_ids=current_model_ids,
            clause=cast(Any, object()),
        )

    def clause_with_trigger_parameter(key: str, value: RuleParameterValue) -> RuleClause:
        assert clause.trigger is not None
        parameters = dict(parameter_payload(clause.trigger.parameters))
        parameters[key] = value
        return replace(
            clause,
            trigger=replace(
                clause.trigger,
                parameters=parameters_from_pairs(
                    tuple(
                        (parameter_key, parameter_value)
                        for parameter_key, parameter_value in parameters.items()
                    )
                ),
            ),
        )

    this_unit_clause = clause_with_trigger_parameter("subject", "this_unit")
    assert _post_shoot_status_source_model_ids(
        record=cover_record,
        unit=unit,
        current_model_instance_ids=current_model_ids,
        clause=this_unit_clause,
        attack_sequence=attack_sequence,
    ) == (None,)
    with pytest.raises(GameLifecycleError, match="requires an ability record"):
        _post_shoot_status_source_model_ids(
            record=cast(Any, object()),
            unit=unit,
            current_model_instance_ids=current_model_ids,
            clause=clause,
            attack_sequence=attack_sequence,
        )
    with pytest.raises(GameLifecycleError, match="requires a triggered clause"):
        _post_shoot_status_source_model_ids(
            record=cover_record,
            unit=unit,
            current_model_instance_ids=current_model_ids,
            clause=replace(clause, trigger=None),
            attack_sequence=attack_sequence,
        )
    with pytest.raises(GameLifecycleError, match="requires an AttackSequence"):
        _post_shoot_status_source_model_ids(
            record=cover_record,
            unit=unit,
            current_model_instance_ids=current_model_ids,
            clause=clause,
            attack_sequence=cast(Any, object()),
        )
    with pytest.raises(GameLifecycleError, match="unsupported subject"):
        _post_shoot_status_source_model_ids(
            record=cover_record,
            unit=unit,
            current_model_instance_ids=current_model_ids,
            clause=clause_with_trigger_parameter("subject", "unsupported_subject"),
            attack_sequence=attack_sequence,
        )
    with pytest.raises(GameLifecycleError, match="requires an ability record"):
        _post_shoot_hit_target_status_option_id(
            record=cast(Any, object()),
            unit=unit,
            clause=clause,
            effect_index=0,
            status="benefit_of_cover",
            source_model_instance_id=unit.own_models[0].model_instance_id,
            target_unit_instance_id=target_unit.unit_instance_id,
        )
    with pytest.raises(GameLifecycleError, match="requires a rule clause"):
        _post_shoot_hit_target_status_option_id(
            record=cover_record,
            unit=unit,
            clause=cast(Any, object()),
            effect_index=0,
            status="benefit_of_cover",
            source_model_instance_id=unit.own_models[0].model_instance_id,
            target_unit_instance_id=target_unit.unit_instance_id,
        )
    with pytest.raises(GameLifecycleError, match="effect_index must be non-negative"):
        _post_shoot_hit_target_status_option_id(
            record=cover_record,
            unit=unit,
            clause=clause,
            effect_index=-1,
            status="benefit_of_cover",
            source_model_instance_id=unit.own_models[0].model_instance_id,
            target_unit_instance_id=target_unit.unit_instance_id,
        )

    assert not _clause_is_supported_post_shoot_hit_target_status_denial(
        clause_with_trigger_parameter("edge", "during")
    )
    assert not _clause_is_supported_post_shoot_hit_target_status_denial(
        clause_with_trigger_parameter("subject", "unsupported_subject")
    )
    assert not _clause_is_supported_post_shoot_hit_target_status_denial(
        replace(clause, duration=None)
    )
    assert not _clause_is_supported_post_shoot_hit_target_status_denial(
        replace(
            clause,
            target=RuleTargetSpec(kind=RuleTargetKind.THIS_UNIT, source_span=clause.source_span),
        )
    )
    assert not _effect_is_supported_status_denial(
        _effect(RuleEffectKind.GRANT_ABILITY, ability="can_advance_and_charge")
    )
    with pytest.raises(GameLifecycleError, match="requires RuleClause values"):
        _clause_is_supported_post_shoot_hit_target_status_denial(cast(Any, object()))
    with pytest.raises(GameLifecycleError, match="requires RuleEffectSpec values"):
        _effect_is_supported_status_denial(cast(Any, object()))
    with pytest.raises(GameLifecycleError, match="selected payload must be an object"):
        _post_shoot_hit_target_status_selected_payload({})
    with pytest.raises(GameLifecycleError, match="payload requires attack_sequence"):
        _post_shoot_hit_target_status_attack_sequence_from_payload({})
    with pytest.raises(GameLifecycleError, match="requires option values"):
        _validate_post_shoot_hit_target_status_option(cast(Any, object()))
    with pytest.raises(GameLifecycleError, match="requires a field name"):
        _validate_non_empty_text("", "Benefit of Cover")
    with pytest.raises(GameLifecycleError, match="status_label must be a string"):
        _validate_non_empty_text("status_label", 1)
    with pytest.raises(GameLifecycleError, match="status_label must not be empty"):
        _validate_non_empty_text("status_label", " ")

    with pytest.raises(GameLifecycleError, match="wargear_ids must be a tuple"):
        successful_hit_target_unit_ids_for_sequence(
            decisions=decisions,
            sequence=attack_sequence,
            wargear_ids=cast(Any, ["bolt-of-change"]),
        )
    with pytest.raises(GameLifecycleError, match="wargear_ids must not duplicate IDs"):
        successful_hit_target_unit_ids_for_sequence(
            decisions=decisions,
            sequence=attack_sequence,
            wargear_ids=("bolt-of-change", "bolt-of-change"),
        )

    def assert_hit_lookup_raises(payload: JsonValue, match: str) -> None:
        lookup_decisions = DecisionController()
        lookup_decisions.event_log.append("attack_sequence_step", payload)
        with pytest.raises(GameLifecycleError, match=match):
            successful_hit_target_unit_ids_for_sequence(
                decisions=lookup_decisions,
                sequence=attack_sequence,
            )

    assert_hit_lookup_raises("not-an-object", "payload must be an object")
    assert_hit_lookup_raises(
        {
            "sequence_id": attack_sequence.sequence_id,
            "step": AttackSequenceStep.HIT.value,
            "pool_index": 0,
            "payload": "not-an-object",
        },
        "hit payload must be an object",
    )
    assert_hit_lookup_raises(
        {
            "sequence_id": attack_sequence.sequence_id,
            "step": AttackSequenceStep.HIT.value,
            "pool_index": "zero",
            "payload": {"successful": True},
        },
        "pool_index must be an int",
    )
    assert_hit_lookup_raises(
        {
            "sequence_id": attack_sequence.sequence_id,
            "step": AttackSequenceStep.HIT.value,
            "pool_index": 99,
            "payload": {"successful": True},
        },
        "pool_index is out of range",
    )


def test_phase17k_named_weapon_ability_choice_rejects_availability_drift() -> None:
    package = _named_weapon_choice_package()
    unit = _named_weapon_choice_unit(package=package)
    army = _flesh_hounds_army(package=package, unit=unit)
    player_index = _player_ability_index(package=package, army=army)
    battlefield = _bloodcrushers_battlefield_state(army=army, unit=unit)
    state = _battle_state_with_army(army=army, battlefield=battlefield)
    _set_state_battle_phase(state, BattlePhase.SHOOTING)
    decisions = DecisionController()
    registry = ShootingPhaseStartHookRegistry.from_bindings(
        CatalogNamedWeaponAbilityChoiceRuntime(
            ability_indexes_by_player_id={army.player_id: player_index},
            armies=(army,),
        ).bindings()
    )
    request = registry.next_request_for(
        _shooting_phase_start_request_context(
            state=state,
            decisions=decisions,
            army_catalog=package.army_catalog,
        )
    )
    assert request is not None
    result = DecisionResult.for_request(
        result_id="phase17k-named-weapon-choice-drift",
        request=request,
        selected_option_id=request.options[0].option_id,
    )
    decisions.request_decision(request)
    record = decisions.submit_result(result)
    state.battlefield_state = battlefield.with_removed_models(
        (unit.own_models[0].model_instance_id,)
    )

    handled = registry.apply_result(
        ShootingPhaseStartResultContext(
            state=state,
            decisions=decisions,
            request=record.request,
            result=record.result,
            ruleset_descriptor=RulesetDescriptor.warhammer_40000_eleventh(),
            army_catalog=package.army_catalog,
            shooting_target_restriction_hooks=ShootingTargetRestrictionHookRegistry.empty(),
        )
    )

    assert not isinstance(handled, bool)
    assert handled.status_kind is LifecycleStatusKind.INVALID
    invalid_payload = cast(dict[str, JsonValue], handled.payload)
    assert invalid_payload["invalid_reason"] == ("catalog_named_weapon_ability_choice_unavailable")
    assert state.persisting_effects_for_unit(unit.unit_instance_id) == ()


def test_phase17k_named_weapon_ability_choice_rejects_submission_drifts() -> None:
    package = _named_weapon_choice_package()
    unit = _named_weapon_choice_unit(package=package)
    army = _flesh_hounds_army(package=package, unit=unit)
    player_index = _player_ability_index(package=package, army=army)
    state = _battle_state_with_army(
        army=army,
        battlefield=_bloodcrushers_battlefield_state(army=army, unit=unit),
    )
    _set_state_battle_phase(state, BattlePhase.SHOOTING)
    decisions = DecisionController()
    runtime = CatalogNamedWeaponAbilityChoiceRuntime(
        ability_indexes_by_player_id={army.player_id: player_index},
        armies=(army,),
    )
    registry = ShootingPhaseStartHookRegistry.from_bindings(runtime.bindings())
    request = registry.next_request_for(
        _shooting_phase_start_request_context(
            state=state,
            decisions=decisions,
            army_catalog=package.army_catalog,
        )
    )
    assert request is not None
    selected_option = request.options[0]

    def apply(payload: JsonValue, selected_option_id: str = selected_option.option_id) -> object:
        return registry.apply_result(
            ShootingPhaseStartResultContext(
                state=state,
                decisions=decisions,
                request=request,
                result=DecisionResult(
                    result_id=f"phase17k-drift-{len(decisions.event_log.records)}",
                    request_id=request.request_id,
                    decision_type=request.decision_type,
                    actor_id=request.actor_id,
                    selected_option_id=selected_option_id,
                    payload=payload,
                ),
                ruleset_descriptor=RulesetDescriptor.warhammer_40000_eleventh(),
                army_catalog=package.army_catalog,
                shooting_target_restriction_hooks=ShootingTargetRestrictionHookRegistry.empty(),
            )
        )

    wrong_kind_payload = dict(cast(dict[str, JsonValue], selected_option.payload))
    wrong_kind_payload["submission_kind"] = "wrong_named_weapon_choice_submission"

    def invalid_reason(value: object) -> JsonValue:
        assert not isinstance(value, bool)
        status = cast(LifecycleStatus, value)
        assert status.status_kind is LifecycleStatusKind.INVALID
        return cast(dict[str, JsonValue], status.payload)["invalid_reason"]

    wrong_kind = apply(wrong_kind_payload)
    assert invalid_reason(wrong_kind) == (
        "catalog_named_weapon_ability_choice_submission_kind_drift"
    )

    option_drift = apply(
        selected_option.payload,
        selected_option_id=f"{selected_option.option_id}:missing",
    )
    assert invalid_reason(option_drift) == ("catalog_named_weapon_ability_choice_option_drift")

    payload_drift = dict(cast(dict[str, JsonValue], selected_option.payload))
    payload_drift["weapon_names"] = ["Changed Weapon"]
    drifted = apply(payload_drift)
    assert invalid_reason(drifted) == ("catalog_named_weapon_ability_choice_payload_drift")

    wrong_hook_request = replace(
        request,
        payload={
            **cast(dict[str, JsonValue], request.payload),
            "hook_id": "phase17k-other-hook",
        },
    )
    ignored = registry.apply_result(
        ShootingPhaseStartResultContext(
            state=state,
            decisions=decisions,
            request=wrong_hook_request,
            result=DecisionResult.for_request(
                result_id="phase17k-wrong-hook",
                request=request,
                selected_option_id=selected_option.option_id,
            ),
            ruleset_descriptor=RulesetDescriptor.warhammer_40000_eleventh(),
            army_catalog=package.army_catalog,
            shooting_target_restriction_hooks=ShootingTargetRestrictionHookRegistry.empty(),
        )
    )
    assert ignored is False
    assert state.persisting_effects_for_unit(unit.unit_instance_id) == ()


def test_phase17k_named_weapon_ability_choice_helpers_cover_invalid_paths() -> None:
    package = _named_weapon_choice_package()
    unit = _named_weapon_choice_unit(package=package)
    army = _flesh_hounds_army(package=package, unit=unit)
    player_index = _player_ability_index(package=package, army=army)
    record = next(
        record for record in player_index.all_records() if record.definition.name == "Daemonspark"
    )
    replay_payload = record.definition.replay_payload
    assert isinstance(replay_payload, dict)
    rule_ir = RuleIR.from_payload(cast(RuleIRPayload, replay_payload["rule_ir"]))
    clause = rule_ir.clauses[0]
    state = _battle_state_with_army(
        army=army,
        battlefield=_bloodcrushers_battlefield_state(army=army, unit=unit),
    )
    _set_state_battle_phase(state, BattlePhase.SHOOTING)
    request_context = _shooting_phase_start_request_context(
        state=state,
        decisions=DecisionController(),
        army_catalog=package.army_catalog,
    )
    runtime = CatalogNamedWeaponAbilityChoiceRuntime(
        ability_indexes_by_player_id={army.player_id: player_index},
        armies=(army,),
    )

    assert runtime.bindings()
    assert _available_catalog_named_weapon_ability_choice_groups(
        ability_indexes_by_player_id={army.player_id: player_index},
        armies=(army,),
        context=request_context,
    )
    with pytest.raises(GameLifecycleError, match="missing player ability index"):
        CatalogNamedWeaponAbilityChoiceRuntime(ability_indexes_by_player_id={}, armies=(army,))
    with pytest.raises(GameLifecycleError, match="requires context"):
        runtime.request_handler(cast(ShootingPhaseStartRequestContext, object()))
    with pytest.raises(GameLifecycleError, match="requires context"):
        runtime.result_handler(cast(ShootingPhaseStartResultContext, object()))
    with pytest.raises(GameLifecycleError, match="require context"):
        _available_catalog_named_weapon_ability_choice_groups(
            ability_indexes_by_player_id={army.player_id: player_index},
            armies=(army,),
            context=cast(ShootingPhaseStartRequestContext, object()),
        )
    with pytest.raises(GameLifecycleError, match="index is missing player"):
        _available_catalog_named_weapon_ability_choice_groups(
            ability_indexes_by_player_id={},
            armies=(army,),
            context=request_context,
        )

    option = _named_weapon_ability_choice_option_from_effect(
        record=record,
        unit=unit,
        clause=clause,
        effect_index=0,
        effect=clause.effects[0],
    )
    assert option is not None
    assert option.label == "Ignores Cover"
    assert _validate_named_weapon_choice_option(option) is option
    assert _clause_is_named_weapon_ability_choice(clause)
    assert _effect_is_named_weapon_ability_choice_option(clause.effects[0])
    assert (
        _named_weapon_ability_choice_option_from_effect(
            record=record,
            unit=unit,
            clause=clause,
            effect_index=0,
            effect=_effect(RuleEffectKind.MODIFY_DICE_ROLL, roll_type="hit", delta=1),
        )
        is None
    )
    assert (
        _named_weapon_ability_choice_option_from_effect(
            record=record,
            unit=unit,
            clause=clause,
            effect_index=0,
            effect=_effect(RuleEffectKind.GRANT_WEAPON_ABILITY, weapon_scope="all"),
        )
        is None
    )
    assert (
        _named_weapon_ability_choice_option_from_effect(
            record=record,
            unit=unit,
            clause=clause,
            effect_index=0,
            effect=_effect(
                RuleEffectKind.GRANT_WEAPON_ABILITY,
                weapon_ability="Sustained Hits",
                weapon_name="Bolt of Change",
                target_scope="this_model",
                selection_kind="select_one",
                selection_group_id="group",
                selection_option_id="option",
                selection_option_index=1,
            ),
        )
        is None
    )

    with pytest.raises(GameLifecycleError, match="requires an ability record"):
        _named_weapon_ability_choice_option_from_effect(
            record=cast(AbilityCatalogRecord, object()),
            unit=unit,
            clause=clause,
            effect_index=0,
            effect=clause.effects[0],
        )
    with pytest.raises(GameLifecycleError, match="requires a rule clause"):
        _named_weapon_ability_choice_option_from_effect(
            record=record,
            unit=unit,
            clause=cast(RuleClause, object()),
            effect_index=0,
            effect=clause.effects[0],
        )
    with pytest.raises(GameLifecycleError, match="effect_index must be non-negative"):
        _named_weapon_ability_choice_option_from_effect(
            record=record,
            unit=unit,
            clause=clause,
            effect_index=-1,
            effect=clause.effects[0],
        )
    with pytest.raises(GameLifecycleError, match="requires a rule effect"):
        _named_weapon_ability_choice_option_from_effect(
            record=record,
            unit=unit,
            clause=clause,
            effect_index=0,
            effect=cast(RuleEffectSpec, object()),
        )
    with pytest.raises(GameLifecycleError, match="requires RuleClause values"):
        _clause_is_named_weapon_ability_choice(cast(RuleClause, object()))
    with pytest.raises(GameLifecycleError, match="requires RuleEffectSpec values"):
        _effect_is_named_weapon_ability_choice_option(cast(RuleEffectSpec, object()))

    assert _optional_named_weapon_names(
        {"weapon_names": ("Bolt of Change", "Infernal Gateway")}
    ) == (
        "Bolt of Change",
        "Infernal Gateway",
    )
    assert _optional_named_weapon_names({"weapon_name": "Bolt of Change"}) == ("Bolt of Change",)
    with pytest.raises(GameLifecycleError, match="weapon_names must be a tuple"):
        _optional_named_weapon_names({"weapon_names": "Bolt of Change|Infernal Gateway"})
    with pytest.raises(GameLifecycleError, match="requires weapon names"):
        _weapon_names_from_parameters({})
    with pytest.raises(GameLifecycleError, match="must be a tuple"):
        _validate_named_weapon_names(["Bolt of Change"])
    with pytest.raises(GameLifecycleError, match="must contain strings"):
        _validate_named_weapon_names((1,))
    with pytest.raises(GameLifecycleError, match="must not be empty"):
        _validate_named_weapon_names(("  ",))
    with pytest.raises(GameLifecycleError, match="must not duplicate names"):
        _validate_named_weapon_names(("Bolt-of-Change", "bolt of change"))
    with pytest.raises(GameLifecycleError, match="target_scope must be a string"):
        _validate_named_weapon_choice_target_scope(1)
    with pytest.raises(GameLifecycleError, match="Unsupported"):
        _validate_named_weapon_choice_target_scope("selected_unit")
    with pytest.raises(GameLifecycleError, match="requires option values"):
        _validate_named_weapon_choice_option(object())

    base_choice_parameters = {
        "selection_kind": "select_one",
        "selection_group_id": "group",
        "selection_option_id": "option",
        "selection_option_index": 1,
        "target_scope": "this_model",
        "weapon_name": "Bolt of Change",
        "weapon_ability_value": "D3",
    }
    assert _weapon_ability_choice_has_supported_runtime_shape(
        base_choice_parameters,
        keyword=WeaponKeyword.SUSTAINED_HITS,
    )
    for malformed_parameters in (
        {**base_choice_parameters, "selection_kind": "choose_any"},
        {**base_choice_parameters, "selection_group_id": 1},
        {**base_choice_parameters, "selection_option_index": 0},
        {key: value for key, value in base_choice_parameters.items() if key != "weapon_name"},
    ):
        assert not _weapon_ability_choice_has_supported_runtime_shape(
            malformed_parameters,
            keyword=WeaponKeyword.SUSTAINED_HITS,
        )
    with pytest.raises(GameLifecycleError, match="Unsupported"):
        _weapon_ability_choice_has_supported_runtime_shape(
            {**base_choice_parameters, "target_scope": "selected_unit"},
            keyword=WeaponKeyword.SUSTAINED_HITS,
        )
    assert (
        _weapon_ability_descriptor_for_selected_choice_payload(
            payload={"keyword": "Lethal Hits"},
            keyword=WeaponKeyword.LETHAL_HITS,
        )
        == AbilityDescriptor.lethal_hits()
    )

    with pytest.raises(GameLifecycleError, match="payload must be an object"):
        _payload_object([])
    with pytest.raises(GameLifecycleError, match="payload weapon_names must be a string"):
        _payload_string({"weapon_names": ["Bolt of Change"]}, key="weapon_names")
    with pytest.raises(GameLifecycleError, match="payload weapon_names must be a list"):
        _payload_string_tuple({"weapon_names": "Bolt of Change"}, key="weapon_names")
    with pytest.raises(GameLifecycleError, match="payload weapon_names must contain strings"):
        _payload_string_tuple({"weapon_names": [1]}, key="weapon_names")
    with pytest.raises(GameLifecycleError, match="must not duplicate values"):
        _payload_string_tuple({"weapon_names": ["Bolt", "Bolt"]}, key="weapon_names")
    with pytest.raises(GameLifecycleError, match="must not be empty"):
        _payload_string_tuple({"weapon_names": []}, key="weapon_names")

    bolt_profile = _weapon_profile_by_name(package.army_catalog, "Bolt of Change")
    context = WeaponProfileModifierContext(
        state=state,
        source_phase=BattlePhase.SHOOTING,
        attacking_unit_instance_id=unit.unit_instance_id,
        attacker_model_instance_id=unit.own_models[0].model_instance_id,
        target_unit_instance_id="phase17k-target-unit",
        weapon_profile=bolt_profile,
    )
    for effect in (
        _phase17k_named_choice_effect(
            effect_id="phase17k-non-object-payload",
            unit=unit,
            owner_player_id=army.player_id,
            payload=None,
        ),
        _phase17k_named_choice_effect(
            effect_id="phase17k-other-effect-kind",
            unit=unit,
            owner_player_id=army.player_id,
            payload={"effect_kind": "other"},
        ),
        _phase17k_named_choice_effect(
            effect_id="phase17k-other-target-model",
            unit=unit,
            owner_player_id=army.player_id,
            payload={
                "effect_kind": CATALOG_NAMED_WEAPON_ABILITY_CHOICE_EFFECT_KIND,
                "target_model_instance_ids": ["other-model"],
                "weapon_names": ["Bolt of Change"],
                "keyword": "Lethal Hits",
            },
        ),
        _phase17k_named_choice_effect(
            effect_id="phase17k-other-weapon",
            unit=unit,
            owner_player_id=army.player_id,
            payload={
                "effect_kind": CATALOG_NAMED_WEAPON_ABILITY_CHOICE_EFFECT_KIND,
                "target_model_instance_ids": [unit.own_models[0].model_instance_id],
                "weapon_names": ["Other Weapon"],
                "keyword": "Lethal Hits",
            },
        ),
    ):
        state.record_persisting_effect(effect)
    assert _selected_catalog_named_weapon_ability_grants(context) == ()

    with pytest.raises(GameLifecycleError, match="weapon ability value must be positive or D3"):
        CatalogNamedWeaponAbilityChoiceOption(
            option_id="phase17k-bad-value",
            selection_option_id="option",
            selection_option_index=1,
            keyword=WeaponKeyword.SUSTAINED_HITS,
            weapon_ability_value="D6",
            ability=None,
            effect_index=0,
        )
    with pytest.raises(GameLifecycleError, match="must be a positive integer"):
        CatalogNamedWeaponAbilityChoiceOption(
            option_id="phase17k-bad-index",
            selection_option_id="option",
            selection_option_index=0,
            keyword=WeaponKeyword.LETHAL_HITS,
            weapon_ability_value=None,
            ability=None,
            effect_index=0,
        )
    with pytest.raises(GameLifecycleError, match="ability must be a descriptor"):
        CatalogNamedWeaponAbilityChoiceOption(
            option_id="phase17k-bad-ability",
            selection_option_id="option",
            selection_option_index=1,
            keyword=WeaponKeyword.LETHAL_HITS,
            weapon_ability_value=None,
            ability=cast(AbilityDescriptor, object()),
            effect_index=0,
        )
    with pytest.raises(GameLifecycleError, match="effect_index must be non-negative"):
        CatalogNamedWeaponAbilityChoiceOption(
            option_id="phase17k-bad-effect-index",
            selection_option_id="option",
            selection_option_index=1,
            keyword=WeaponKeyword.LETHAL_HITS,
            weapon_ability_value=None,
            ability=None,
            effect_index=-1,
        )


def test_phase17k_catalog_weapon_keyword_grant_helpers_cover_scopes_and_values() -> None:
    package = _advance_charge_package()
    unit = _advance_charge_unit(package=package)
    army = _flesh_hounds_army(package=package, unit=unit)
    player_index = _player_ability_index(package=package, army=army)
    record = {record.definition.name: record for record in player_index.all_records()}[
        "Pack Killers"
    ]
    replay_payload = record.definition.replay_payload
    assert isinstance(replay_payload, dict)
    rule_ir = RuleIR.from_payload(cast(RuleIRPayload, replay_payload["rule_ir"]))
    clause = rule_ir.clauses[0]
    melee_profile = next(
        wargear.weapon_profiles[0]
        for wargear in package.army_catalog.wargear
        if wargear.wargear_id == "test-advance-charge-unit:swift-claws"
    )
    ranged_profile = replace(
        melee_profile,
        profile_id=f"{melee_profile.profile_id}:helper-ranged-copy",
        range_profile=RangeProfile.distance(12),
    )
    grant = CatalogWeaponKeywordGrant(
        source_id="phase17k-helper-grant",
        keyword=cast(WeaponKeyword, "Lance"),
        weapon_scope="all",
    )
    updated_profile = _profile_with_catalog_weapon_keyword_grant(
        profile=melee_profile,
        grant=grant,
    )

    assert _catalog_weapon_keyword_grant_from_effect(
        record=record,
        clause=clause,
        effect_index=0,
        effect=clause.effects[0],
    ) == CatalogWeaponKeywordGrant(
        source_id=f"{record.record_id}:{clause.clause_id}:effect-000:weapon-keyword",
        keyword=WeaponKeyword.LETHAL_HITS,
        weapon_scope="melee",
        ability=AbilityDescriptor.lethal_hits(),
    )
    assert (
        _catalog_weapon_keyword_grant_from_effect(
            record=record,
            clause=clause,
            effect_index=1,
            effect=_effect(RuleEffectKind.MODIFY_DICE_ROLL, roll_type="hit", delta=1),
        )
        is None
    )
    assert (
        _catalog_weapon_keyword_grant_from_effect(
            record=record,
            clause=clause,
            effect_index=1,
            effect=_effect(RuleEffectKind.GRANT_WEAPON_ABILITY, weapon_scope="melee"),
        )
        is None
    )
    assert (
        _catalog_weapon_keyword_grant_from_effect(
            record=record,
            clause=clause,
            effect_index=1,
            effect=_effect(RuleEffectKind.GRANT_WEAPON_ABILITY, weapon_ability="Lethal Hits"),
        )
        is None
    )
    assert (
        _catalog_weapon_keyword_grant_from_effect(
            record=record,
            clause=clause,
            effect_index=1,
            effect=_effect(
                RuleEffectKind.GRANT_WEAPON_ABILITY,
                weapon_ability="Sustained Hits",
                weapon_scope="all",
            ),
        )
        is None
    )
    assert _weapon_keyword_grant_consumer_ids_for_effect(
        _effect(
            RuleEffectKind.GRANT_WEAPON_ABILITY,
            weapon_ability="Sustained Hits",
            weapon_ability_value=1,
            weapon_scope="all",
        )
    ) == (
        CATALOG_IR_WEAPON_KEYWORD_GRANT_CONSUMER_ID,
        "catalog-ir:weapon-keyword-grant:sustained-hits",
    )
    assert (
        _weapon_keyword_grant_consumer_ids_for_effect(
            _effect(
                RuleEffectKind.GRANT_WEAPON_ABILITY,
                weapon_ability="Hunter",
                weapon_scope="all",
            )
        )
        == ()
    )
    assert grant.keyword is WeaponKeyword.LANCE
    assert grant.weapon_scope == "all"
    assert WeaponKeyword.LANCE in updated_profile.keywords
    assert grant.source_id in updated_profile.source_ids
    assert (
        _profile_with_catalog_weapon_keyword_grant(profile=updated_profile, grant=grant)
        is updated_profile
    )
    assert _weapon_scope_matches_profile(weapon_scope="all", profile=melee_profile)
    assert _weapon_scope_matches_profile(weapon_scope="melee", profile=melee_profile)
    assert not _weapon_scope_matches_profile(weapon_scope="ranged", profile=melee_profile)
    assert _weapon_scope_matches_profile(weapon_scope="ranged", profile=ranged_profile)
    assert not _weapon_scope_matches_profile(weapon_scope="melee", profile=ranged_profile)
    for keyword, parameters, expected_kind in (
        (WeaponKeyword.DEVASTATING_WOUNDS, {}, AbilityKind.DEVASTATING_WOUNDS),
        (WeaponKeyword.HEAVY, {}, AbilityKind.HEAVY),
        (WeaponKeyword.SUSTAINED_HITS, {"weapon_ability_value": 1}, AbilityKind.SUSTAINED_HITS),
        (WeaponKeyword.RAPID_FIRE, {"weapon_ability_value": 2}, AbilityKind.RAPID_FIRE),
        (WeaponKeyword.MELTA, {"weapon_ability_value": 3}, AbilityKind.MELTA),
        (WeaponKeyword.CLEAVE, {"weapon_ability_value": 4}, AbilityKind.CLEAVE),
    ):
        descriptor = _weapon_ability_descriptor_for_grant(
            parameters=parameters,
            keyword=keyword,
        )
        assert descriptor is not None
        assert descriptor.ability_kind is expected_kind
    assert _weapon_ability_descriptor_for_grant(parameters={}, keyword=WeaponKeyword.LANCE) is None
    runtime = CatalogWeaponKeywordGrantRuntime(
        ability_indexes_by_player_id={army.player_id: player_index},
        armies=(army,),
    )
    with pytest.raises(GameLifecycleError, match="missing player ability index"):
        CatalogWeaponKeywordGrantRuntime(ability_indexes_by_player_id={}, armies=(army,))
    with pytest.raises(GameLifecycleError, match="requires context"):
        runtime.weapon_profile_modifier(cast(WeaponProfileModifierContext, object()))
    with pytest.raises(GameLifecycleError, match="unit is unknown"):
        runtime.weapon_profile_modifier(
            WeaponProfileModifierContext(
                state=_battle_state_with_army(
                    army=army,
                    battlefield=_bloodcrushers_battlefield_state(army=army, unit=unit),
                ),
                source_phase=BattlePhase.FIGHT,
                attacking_unit_instance_id="phase17k-unknown-unit",
                attacker_model_instance_id=unit.own_models[0].model_instance_id,
                target_unit_instance_id="phase17k-target-unit",
                weapon_profile=melee_profile,
            )
        )
    with pytest.raises(GameLifecycleError, match="ability must be a descriptor"):
        CatalogWeaponKeywordGrant(
            source_id="phase17k-bad-ability-grant",
            keyword=WeaponKeyword.LANCE,
            weapon_scope="all",
            ability=cast(AbilityDescriptor, object()),
        )
    with pytest.raises(GameLifecycleError, match="requires an ability record"):
        _catalog_weapon_keyword_grant_from_effect(
            record=cast(AbilityCatalogRecord, object()),
            clause=clause,
            effect_index=0,
            effect=clause.effects[0],
        )
    with pytest.raises(GameLifecycleError, match="requires a rule clause"):
        _catalog_weapon_keyword_grant_from_effect(
            record=record,
            clause=cast(RuleClause, object()),
            effect_index=0,
            effect=clause.effects[0],
        )
    with pytest.raises(GameLifecycleError, match="effect_index must be non-negative"):
        _catalog_weapon_keyword_grant_from_effect(
            record=record,
            clause=clause,
            effect_index=-1,
            effect=clause.effects[0],
        )
    with pytest.raises(GameLifecycleError, match="requires a rule effect"):
        _catalog_weapon_keyword_grant_from_effect(
            record=record,
            clause=clause,
            effect_index=0,
            effect=cast(RuleEffectSpec, object()),
        )
    with pytest.raises(GameLifecycleError, match="unsupported keyword"):
        _weapon_keyword_grant_consumer_ids_for_effect(
            _effect(
                RuleEffectKind.GRANT_WEAPON_ABILITY,
                weapon_ability="Bad Keyword",
                weapon_scope="all",
            )
        )
    with pytest.raises(GameLifecycleError, match="requires RuleEffectSpec values"):
        _weapon_keyword_grant_consumer_ids_for_effect(cast(RuleEffectSpec, object()))
    with pytest.raises(GameLifecycleError, match="cannot infer Hunter targets"):
        _weapon_ability_descriptor_for_grant(parameters={}, keyword=WeaponKeyword.HUNTER)
    with pytest.raises(GameLifecycleError, match="positive or D3"):
        _weapon_ability_descriptor_for_grant(
            parameters={},
            keyword=WeaponKeyword.SUSTAINED_HITS,
        )
    with pytest.raises(GameLifecycleError, match="positive or D3"):
        _weapon_ability_descriptor_for_grant(
            parameters={"weapon_ability_value": 0},
            keyword=WeaponKeyword.SUSTAINED_HITS,
        )
    with pytest.raises(GameLifecycleError, match="requires a WeaponProfile"):
        _profile_with_catalog_weapon_keyword_grant(
            profile=cast(WeaponProfile, object()),
            grant=grant,
        )
    with pytest.raises(GameLifecycleError, match="requires grant data"):
        _profile_with_catalog_weapon_keyword_grant(
            profile=melee_profile,
            grant=cast(CatalogWeaponKeywordGrant, object()),
        )
    with pytest.raises(GameLifecycleError, match="requires a WeaponProfile"):
        _weapon_scope_matches_profile(
            weapon_scope="all",
            profile=cast(WeaponProfile, object()),
        )
    with pytest.raises(GameLifecycleError, match="Unsupported catalog weapon keyword grant scope"):
        _weapon_scope_matches_profile(weapon_scope="bad scope", profile=melee_profile)
    with pytest.raises(GameLifecycleError, match="Unsupported catalog weapon keyword grant scope"):
        _weapon_scope_matches_profile(weapon_scope="ranged weapons", profile=ranged_profile)


def test_phase17k_catalog_ir_roll_reroll_classification_requires_supported_target() -> None:
    this_unit_rule = _catalog_rule_ir(
        (
            _effect(RuleEffectKind.REROLL_PERMISSION, roll_type="advance"),
            _effect(RuleEffectKind.REROLL_PERMISSION, roll_type="charge"),
        ),
        target_kind=RuleTargetKind.THIS_UNIT,
    )
    selected_unit_without_leader_rule = _catalog_rule_ir(
        (_effect(RuleEffectKind.REROLL_PERMISSION, roll_type="advance"),),
        target_kind=RuleTargetKind.SELECTED_UNIT,
    )
    aura_attack_reroll_rule = _catalog_rule_ir(
        (
            _effect(
                RuleEffectKind.REROLL_PERMISSION,
                roll_type="hit",
                attack_role="attacker",
            ),
            _effect(
                RuleEffectKind.REROLL_PERMISSION,
                roll_type="advance",
                attack_role="attacker",
            ),
        ),
        target_kind=RuleTargetKind.AURA_UNITS,
    )
    unsupported_roll_rule = _catalog_rule_ir(
        (_effect(RuleEffectKind.REROLL_PERMISSION, roll_type="damage"),),
        target_kind=RuleTargetKind.THIS_UNIT,
    )

    assert catalog_rule_ir_consumers_for_rule(this_unit_rule) == (
        CATALOG_IR_ADVANCE_ROLL_REROLL_CONSUMER_ID,
        CATALOG_IR_CHARGE_ROLL_REROLL_CONSUMER_ID,
    )
    assert set(catalog_rule_ir_hook_ids_for_rule(this_unit_rule)) == {
        CATALOG_IR_ADVANCE_ROLL_REROLL_CONSUMER_ID,
        CATALOG_IR_CHARGE_ROLL_REROLL_CONSUMER_ID,
    }
    assert catalog_rule_ir_consumers_for_rule(selected_unit_without_leader_rule) == ()
    assert catalog_rule_ir_consumers_for_rule(aura_attack_reroll_rule) == (
        CATALOG_IR_HIT_ROLL_REROLL_CONSUMER_ID,
    )
    assert catalog_rule_ir_consumers_for_rule(unsupported_roll_rule) == ()
    assert catalog_rule_ir_hook_ids_for_rule(unsupported_roll_rule) == ()


def test_phase17k_catalog_ir_roll_reroll_effect_helpers_are_strict() -> None:
    advance_effect = _effect(RuleEffectKind.REROLL_PERMISSION, roll_type="advance")
    charge_effect = _effect(RuleEffectKind.REROLL_PERMISSION, roll_type="charge")
    non_reroll_effect = _effect(RuleEffectKind.GRANT_ABILITY, ability="can_advance_and_charge")
    malformed_effect = _effect(RuleEffectKind.REROLL_PERMISSION, roll_type=1)

    assert _effect_is_roll_reroll_permission(advance_effect, roll_type="advance_roll")
    assert not _effect_is_roll_reroll_permission(advance_effect, roll_type="charge_roll")
    assert not _effect_is_roll_reroll_permission(non_reroll_effect, roll_type="advance_roll")
    assert not _effect_is_roll_reroll_permission(malformed_effect, roll_type="advance_roll")
    assert (
        _roll_reroll_consumer_id_for_effect(advance_effect)
        == CATALOG_IR_ADVANCE_ROLL_REROLL_CONSUMER_ID
    )
    assert (
        _roll_reroll_consumer_id_for_effect(charge_effect)
        == CATALOG_IR_CHARGE_ROLL_REROLL_CONSUMER_ID
    )
    assert _roll_reroll_consumer_id_for_effect(non_reroll_effect) is None
    assert _roll_reroll_consumer_id_for_effect(malformed_effect) is None
    with pytest.raises(GameLifecycleError, match="requires RuleEffectSpec values"):
        _effect_is_roll_reroll_permission(
            cast(RuleEffectSpec, object()),
            roll_type="advance_roll",
        )
    with pytest.raises(GameLifecycleError, match="requires RuleEffectSpec values"):
        _roll_reroll_consumer_id_for_effect(cast(RuleEffectSpec, object()))


def test_phase17k_catalog_ir_shadow_of_chaos_aura_classifies_contextual_status() -> None:
    rule_ir = compile_rule_source_text(
        RuleSourceText.from_raw(
            source_id="phase17k:test:shadow-of-chaos-aura",
            raw_text=(
                "Daemonic Shadow (Aura): While a friendly Khorne Legiones Daemonica unit "
                'is within 6" of this model, that unit is within your army\u2019s Shadow of Chaos.'
            ),
        ),
        source_keyword_sequence_parts=SOURCE_KEYWORD_SEQUENCE_PARTS,
    ).rule_ir

    assert rule_ir.is_supported
    assert catalog_rule_ir_consumers_for_rule(rule_ir) == (
        CATALOG_IR_SHADOW_OF_CHAOS_AURA_CONSUMER_ID,
    )
    assert set(catalog_rule_ir_hook_ids_for_rule(rule_ir)) == {
        CATALOG_IR_SHADOW_OF_CHAOS_AURA_CONSUMER_ID,
    }
    assert CATALOG_IR_SHADOW_OF_CHAOS_AURA_CONSUMER_ID in set(catalog_rule_ir_registered_hook_ids())


def test_phase17k_movement_phase_ability_index_mapping_is_fail_fast() -> None:
    index = AbilityCatalogIndex.from_records(())
    validated = _validate_ability_index_mapping({"player-a": index})
    present_index = _ability_index_for_player(validated, player_id="player-a")
    missing_index = _ability_index_for_player(validated, player_id="player-b")

    assert validated["player-a"] is index
    assert present_index is index
    assert tuple(missing_index.all_records()) == ()
    with pytest.raises(GameLifecycleError, match="must be a mapping"):
        _validate_ability_index_mapping(("player-a", index))
    with pytest.raises(GameLifecycleError, match="values must be AbilityCatalogIndex"):
        _validate_ability_index_mapping({"player-a": cast(AbilityCatalogIndex, object())})
    with pytest.raises(GameLifecycleError, match="must be a mapping"):
        _ability_index_for_player(("player-a", index), player_id="player-a")
    with pytest.raises(GameLifecycleError, match="contained an invalid value"):
        _ability_index_for_player(
            {"player-a": cast(AbilityCatalogIndex, object())},
            player_id="player-a",
        )


def test_phase17k_daemon_wargear_ability_coverage_snapshot_is_current() -> None:
    rows = ability_support_matrix_rows()
    support_rows = datasheet_support_rows()
    mustering_rows = mustering_support_rows()
    runtime_semantic_payload = runtime_content_semantic_coverage_payload()
    snapshot = json.loads(
        (
            Path(__file__).resolve().parents[2]
            / "data"
            / "generated"
            / "ability_coverage"
            / "ability_coverage_rows.json"
        ).read_text(encoding="utf-8")
    )
    category_rows = ability_coverage_category_rows(rows)
    category_snapshot = json.loads(
        (
            Path(__file__).resolve().parents[2]
            / "data"
            / "generated"
            / "ability_coverage"
            / "ability_support_category_rows.json"
        ).read_text(encoding="utf-8")
    )
    datasheet_support_snapshot = json.loads(
        (
            Path(__file__).resolve().parents[2]
            / "data"
            / "generated"
            / "ability_coverage"
            / "datasheet_support_rows.json"
        ).read_text(encoding="utf-8")
    )
    mustering_support_snapshot = json.loads(
        (
            Path(__file__).resolve().parents[2]
            / "data"
            / "generated"
            / "ability_coverage"
            / "mustering_support_rows.json"
        ).read_text(encoding="utf-8")
    )
    runtime_semantic_snapshot = json.loads(
        (
            Path(__file__).resolve().parents[2]
            / "data"
            / "generated"
            / "ability_coverage"
            / "runtime_content_semantic_coverage.json"
        ).read_text(encoding="utf-8")
    )
    markdown_snapshot = (
        Path(__file__).resolve().parents[2] / "docs" / "ABILITY_SUPPORT_MATRIX_V2.md"
    ).read_text(encoding="utf-8")
    faction_markdown_snapshot = {
        path.name: path.read_text(encoding="utf-8")
        for path in sorted((Path(__file__).resolve().parents[2] / "docs" / "factions").glob("*.md"))
    }
    generated_markdown = support_matrix_markdown(
        ability_coverage_category_rows_payload(category_rows),
        ability_rows=ability_coverage_rows_payload(rows),
        runtime_semantic_coverage=runtime_semantic_payload,
    )
    generated_faction_markdown = faction_support_markdown_files(
        datasheet_support_rows=support_rows,
        ability_rows=rows,
    )
    rows_by_name: dict[str, list[AbilityCoverageRow]] = {}
    for row in rows:
        rows_by_name.setdefault(row.ability_name, []).append(row)
    categories_by_name = {row.category_name: row for row in category_rows}
    cult_ambush_runtime_ids = (
        genestealer_cults_cult_ambush.SOURCE_RULE_ID,
        genestealer_cults_cult_ambush.BATTLE_FORMATION_HOOK_ID,
        genestealer_cults_cult_ambush.UNIT_DESTROYED_HOOK_ID,
        genestealer_cults_cult_ambush.TURN_END_HOOK_ID,
    )
    adepta_sororitas_runtime_ids = (
        adepta_sororitas_army_rule.BATTLE_ROUND_START_HOOK_ID,
        adepta_sororitas_army_rule.UNIT_DESTROYED_HOOK_ID,
    )
    adepta_sororitas_coverage_runtime_ids = (
        *adepta_sororitas_runtime_ids,
        adepta_sororitas_army_rule.TRIUMPH_RELICS_BATTLE_ROUND_START_HOOK_ID,
    )
    adeptus_custodes_runtime_ids = (
        adeptus_custodes_army_rule.DACATARAI_HOOK_ID,
        adeptus_custodes_army_rule.RENDAX_HOOK_ID,
        adeptus_custodes_army_rule.WEAPON_PROFILE_MODIFIER_ID,
    )
    adeptus_mechanicus_runtime_ids = (
        adeptus_mechanicus_army_rule.HOOK_ID,
        adeptus_mechanicus_army_rule.PROTECTOR_HIT_MODIFIER_ID,
        adeptus_mechanicus_army_rule.WEAPON_PROFILE_MODIFIER_ID,
    )

    assert ability_coverage_rows_payload(rows) == snapshot
    assert ability_coverage_category_rows_payload(category_rows) == category_snapshot
    assert datasheet_support_rows_payload(support_rows) == datasheet_support_snapshot
    assert mustering_support_rows_payload(mustering_rows) == mustering_support_snapshot
    assert runtime_semantic_payload == runtime_semantic_snapshot
    assert generated_markdown == markdown_snapshot
    assert generated_faction_markdown == faction_markdown_snapshot
    assert "## Factions" in generated_markdown
    assert "## Runtime Content Semantic Coverage" in generated_markdown
    assert "`data/generated/ability_coverage/runtime_content_semantic_coverage.json`" in (
        generated_markdown
    )
    assert "[aeldari](factions/aeldari.md)" in generated_markdown
    assert "Faction-pack Stratagems" not in generated_markdown
    assert "Faction-pack Enhancements" not in generated_markdown
    assert "| Aeldari | 15 | 2 | 51 | 75 | 16 | [aeldari](factions/aeldari.md) |" in (
        generated_markdown
    )
    assert ("| Orks | 12 | 1 | 44 | 66 | 13 | [orks](factions/orks.md) |") in generated_markdown
    assert (
        "| Chaos Daemons | 9 | 6 | 29 | 46 | 42 | [chaos-daemons](factions/chaos-daemons.md) |"
        in (generated_markdown)
    )
    assert (
        "| Leagues of Votann | 10 | 0 | 28 | 42 | 2 | "
        "[leagues-of-votann](factions/leagues-of-votann.md) |"
    ) in generated_markdown
    assert (
        "| Imperial Knights | 8 | 0 | 24 | 36 | 2 | "
        "[imperial-knights](factions/imperial-knights.md) |"
    ) in generated_markdown
    assert (
        "| Thousand Sons | 9 | 0 | 24 | 36 | 1 | [thousand-sons](factions/thousand-sons.md) |"
    ) in generated_markdown
    assert (
        "| Genestealer Cults | 9 | 0 | 20 | 30 | 3 | "
        "[genestealer-cults](factions/genestealer-cults.md) |"
    ) in generated_markdown
    assert "| Tyranids | 10 | 0 | 32 | 48 | 2 | [tyranids](factions/tyranids.md) |" in (
        generated_markdown
    )
    assert (
        "| Adepta Sororitas | 8 | 0 | 20 | 30 | 1 | "
        "[adepta-sororitas](factions/adepta-sororitas.md) |"
    ) in generated_markdown
    assert (
        "| Adeptus Custodes | 9 | 0 | 24 | 36 | 3 | "
        "[adeptus-custodes](factions/adeptus-custodes.md) |"
    ) in generated_markdown
    assert (
        "| Adeptus Mechanicus | 10 | 0 | 28 | 42 | 1 | "
        "[adeptus-mechanicus](factions/adeptus-mechanicus.md) |"
    ) in generated_markdown
    chaos_daemons_markdown = generated_faction_markdown["chaos-daemons.md"]
    leader_attachment_evidence_ids = leader_attachment_consumer_evidence_datasheet_ids()
    coverage_row_ids = {row.coverage_row_id for row in rows}
    faction_ids = {row.faction_id for row in faction_detachment_source.faction_rows()}
    detachment_ids_by_faction = {
        faction_id: {
            row.detachment_id
            for row in faction_detachment_source.detachment_rows()
            if row.faction_id == faction_id
        }
        for faction_id in faction_ids
    }
    support_rows_by_datasheet_id = {row.datasheet_id: row for row in support_rows}
    flesh_hounds_support = support_rows_by_datasheet_id["000001112"]
    bloodletters_support = support_rows_by_datasheet_id["000001114"]
    bloodcrushers_support = support_rows_by_datasheet_id["000001115"]
    belakor_support = support_rows_by_datasheet_id["000001148"]
    belakor_stealth_rows = tuple(
        row for row in rows if row.datasheet_id == "000001148" and row.ability_name == "Stealth"
    )
    belakor_supreme_commander_rows = tuple(
        row
        for row in rows
        if row.datasheet_id == "000001148" and row.ability_name == "SUPREME COMMANDER"
    )
    known_mustering_source_ids = {
        value
        for name, value in vars(army_mustering).items()
        if name.endswith("_SOURCE_ID") and type(value) is str
    }
    represented_mustering_source_ids = {row.source_id for row in mustering_rows}
    army_mustering_rule_ids = tuple(
        row.rule_id for row in mustering_rows if row.rule_id.startswith("army-mustering:")
    )

    assert "## Datasheet / Unit Support" in chaos_daemons_markdown
    assert "### Khorne" in chaos_daemons_markdown
    assert "### Tzeentch" in chaos_daemons_markdown
    assert "### Nurgle" in chaos_daemons_markdown
    assert "### Slaanesh" in chaos_daemons_markdown
    assert "### Undivided" in chaos_daemons_markdown
    assert "## Semantic Support Snapshot" in chaos_daemons_markdown
    assert "Leader row consumer evidence" not in chaos_daemons_markdown
    chaos_daemons_leader_datasheet_ids = {
        "000001104",
        "000001106",
        "000001126",
        "000001129",
        "000001138",
        "000001455",
        "000001456",
        "000001462",
        "000001463",
        "000001464",
        "000001466",
        "000001467",
        "000001468",
        "000001469",
        "000001589",
        "000001647",
        "000001649",
        "000004100",
    }
    assert chaos_daemons_leader_datasheet_ids <= leader_attachment_evidence_ids
    assert chaos_daemons_markdown.count(
        "Source-backed Leader attachment targets are consumed by generic army mustering."
    ) == len(chaos_daemons_leader_datasheet_ids)
    attachment_support_row = next(
        row
        for row in mustering_rows
        if row.rule_id == army_mustering.ATTACHMENT_DECLARATION_MUSTERING_CONSUMER_ID
    )
    assert attachment_support_row.support_stage == "full"
    assert attachment_support_row.source_id == army_mustering.ATTACHMENT_ELIGIBILITY_SOURCE_ID
    assert (
        "| Blood Legion<br>Cavalcade of Chaos<br>Daemonic Incursion<br>Lords of the Warp"
        "<br>Shadow Legion<br>Warptide | Legion of Excess<br>Plague Legion"
        "<br>Scintillating Legion |"
    ) in chaos_daemons_markdown
    assert "| Lords of the Warp | Swollen with Power Upgrade | None |" in chaos_daemons_markdown
    assert (
        "| Lords of the Warp | Bilious Blessing<br>Call to Murder<br>Carnival of Excess"
        "<br>Skirling Magicks | None |"
    ) in chaos_daemons_markdown
    assert (
        "| Lords of the Warp | `Full` | Loci of Power generic IR Leadership and "
        "Objective Control modifiers | Focused RuleIR, target-filtering, runtime "
        "manifest, and Stratagem targeting tests |"
    ) in chaos_daemons_markdown
    assert (
        "| Shadow Legion | Fade to Darkness<br>Leaping Shadows<br>Malice Made Manifest"
        "<br>Mantle of Gloom (Aura) | None |"
    ) in chaos_daemons_markdown
    assert (
        "| Cavalcade of Chaos | Apocalyptic Steeds Upgrade"
        "<br>Soul Shattering Charge Upgrade | None |"
    ) in chaos_daemons_markdown
    assert (
        "| Cavalcade of Chaos | From Beyond the Veil<br>Inescapable Manifestations"
        "<br>Warp-Riders | None |"
    ) in chaos_daemons_markdown
    assert (
        "| Shadow Legion | BINDING SHADOW<br>CHANNELLED WRATH<br>DEATH DENIED"
        "<br>ENCROACHING DARKNESS<br>SHADE PATH<br>SPITEFUL DEMISE | None |"
    ) in chaos_daemons_markdown
    assert (
        "| Nurgle | Nurglings (`000001133`)<br>Plague Drones (`000001135`)"
        "<br>Plaguebearers (`000001132`)<br>Poxbringer (`000001467`)"
        "<br>Rotigus (`000001465`)<br>Spoilpox Scrivener (`000001469`) | None |"
    ) in chaos_daemons_markdown
    for khorne_datasheet_id in (
        "000001104",
        "000001105",
        "000001106",
        "000001111",
        "000001112",
        "000001114",
        "000001115",
        "000001116",
        "000001455",
        "000001456",
        "000001588",
        "000002582",
    ):
        assert f"(`{khorne_datasheet_id}`)" in chaos_daemons_markdown
    assert (
        "Wahapedia-only discontinued Khorne-labeled rows, including An'ggrath the Unbound "
        "and Chaos Lord On Juggernaut, are excluded"
    ) in chaos_daemons_markdown
    assert "PDF Karanak datasheet supersedes the duplicate Wahapedia Karanak row" in (
        chaos_daemons_markdown
    )
    assert (
        "| Bloodcrushers (`000001115`) | PDF pages 30-31; supersedes Wahapedia. | "
        "All consumed | Deep Strike, Brass Stampede move-completed mortal wounds"
    ) in chaos_daemons_markdown
    assert (
        "| Bloodletters (`000001114`) | PDF pages 28-29; supersedes Wahapedia. | All consumed |"
    ) in chaos_daemons_markdown
    assert (
        "| Bloodmaster (`000001455`) | PDF pages 20-21; supersedes Wahapedia. | All consumed |"
    ) in chaos_daemons_markdown
    assert (
        "| Bloodthirster (`000002582`) | PDF pages 16-17; supersedes Wahapedia. | All consumed |"
    ) in chaos_daemons_markdown
    assert (
        "| Rendmaster On Blood Throne (`000001111`) | PDF pages 24-25; supersedes "
        "Wahapedia. | All consumed |"
    ) in chaos_daemons_markdown
    assert (
        "| Skull Cannon (`000001116`) | PDF pages 34-35; supersedes Wahapedia. | All consumed |"
    ) in chaos_daemons_markdown
    assert (
        "| Skullmaster (`000001456`) | PDF pages 22-23; supersedes Wahapedia. | All consumed |"
    ) in chaos_daemons_markdown
    assert (
        "| Skulltaker (`000001106`) | PDF pages 18-19; supersedes Wahapedia. | All consumed |"
    ) in chaos_daemons_markdown
    assert (
        "| Lord of Change (`000001120`) | PDF pages 40-41; supersedes Wahapedia. | All consumed |"
    ) in chaos_daemons_markdown
    assert (
        "| Plaguebearers (`000001132`) | PDF pages 78-79; supersedes Wahapedia. | All consumed |"
    ) in chaos_daemons_markdown
    assert (
        "| Shalaxi Helbane (`000001648`) | PDF pages 88-89; supersedes Wahapedia. | All consumed |"
    ) in chaos_daemons_markdown
    assert (
        "| Skull Altar (`000001588`) | PDF pages 36-37; supersedes Wahapedia. | "
        "All consumed | Infiltrators, The Shadow of Chaos, Shadow of Khorne "
        "Battle-shock test re-roll permission, and Fortification cover, "
        "target-permission, hit-roll, and Desperate Escape exception semantics are consumed."
    ) in chaos_daemons_markdown
    for pdf_review_datasheet_id in (
        "000001117",
        "000001120",
        "000001118",
        "000001463",
        "000001464",
        "000001119",
        "000001462",
        "000002583",
        "000002584",
        "000001125",
        "000001126",
        "000001127",
        "000001128",
        "000001465",
        "000001130",
        "000001467",
        "000001469",
        "000001129",
        "000001468",
        "000001466",
        "000001132",
        "000001133",
        "000001134",
        "000001135",
        "000001470",
        "000001648",
        "000001137",
        "000001589",
        "000001136",
        "000001649",
        "000001647",
        "000004100",
        "000001144",
        "000001138",
        "000001142",
        "000001143",
        "000001145",
        "000001148",
        "000001151",
        "000001149",
        "000002758",
    ):
        assert f"(`{pdf_review_datasheet_id}`)" in chaos_daemons_markdown
    assert "Faction Pack pages 38-63" in chaos_daemons_markdown
    assert "Faction Pack pages 64-87" in chaos_daemons_markdown
    assert "Faction Pack pages 88-111" in chaos_daemons_markdown
    assert "Faction Pack pages 112-119" in chaos_daemons_markdown
    assert (
        "| Burning Chariot (`000001128`) | PDF pages 62-63; supersedes Wahapedia. | All consumed |"
    ) in chaos_daemons_markdown
    assert (
        "| Great Unclean One (`000001130`) | PDF pages 66-67; supersedes Wahapedia. | "
        "Unsupported IR |"
    ) in chaos_daemons_markdown
    assert (
        "| Tormentbringer (`000004100`) | PDF pages 100-101; supersedes Wahapedia "
        "and older chariot row 000001141. | Unsupported IR |"
    ) in chaos_daemons_markdown
    assert (
        "| Daemon Prince of Chaos (`000001149`) | PDF pages 116-117; supersedes "
        "Wahapedia. | All consumed |"
    ) in chaos_daemons_markdown
    assert "### Wahapedia-only rows excluded from PDF review" not in chaos_daemons_markdown
    assert "### Datasheet Ability Details" not in chaos_daemons_markdown
    assert "## Detachment Rule Coverage Rows" not in chaos_daemons_markdown
    assert "| Datasheet | Overall | Catalog | Models / geometry |" not in chaos_daemons_markdown
    assert "Bloodletters (`000001114`) | `Playable`" not in chaos_daemons_markdown
    assert "Bane of Cowards (`000001114:bane-of-cowards`)" not in chaos_daemons_markdown
    assert flesh_hounds_support.overall == "Playable"
    assert flesh_hounds_support.catalog_status == "Full"
    assert flesh_hounds_support.model_geometry_status == "Full"
    assert flesh_hounds_support.wargear_status == "Full"
    assert flesh_hounds_support.weapon_keyword_status == "Full"
    assert flesh_hounds_support.datasheet_ability_status == "Full"
    assert flesh_hounds_support.faction_interaction_status == "Partial"
    assert bloodletters_support.overall == "Playable"
    assert bloodletters_support.datasheet_ability_status == "Full"
    assert bloodcrushers_support.overall == "Playable"
    assert bloodcrushers_support.datasheet_ability_status == "Full"
    assert belakor_support.overall == "Playable"
    assert belakor_support.datasheet_ability_status == "Full"
    assert belakor_support.faction_interaction_status == "Partial"
    assert "descriptor_only" not in belakor_support.notes
    assert len(belakor_stealth_rows) == 1
    assert belakor_stealth_rows[0].support_stage is AbilityCoverageSupportStage.ENGINE_CONSUMED
    assert belakor_stealth_rows[0].runtime_consumer_ids == (CORE_STEALTH_RUNTIME_CONSUMER_ID,)
    assert belakor_stealth_rows[0].semantic_categories == ("core.stealth",)
    assert len(belakor_supreme_commander_rows) == 1
    assert (
        belakor_supreme_commander_rows[0].support_stage
        is AbilityCoverageSupportStage.ENGINE_CONSUMED
    )
    assert belakor_supreme_commander_rows[0].runtime_consumer_ids == (
        SUPREME_COMMANDER_MUSTERING_CONSUMER_ID,
    )
    assert belakor_supreme_commander_rows[0].semantic_categories == (
        "datasheet.mustering.supreme_commander",
    )
    for support_row in support_rows:
        assert support_row.overall in DATASHEET_SUPPORT_OVERALL_VALUES
        assert support_row.faction_id in faction_ids
        assert set(support_row.ability_coverage_row_ids).issubset(coverage_row_ids)
        assert set(support_row.detachment_ids).issubset(
            detachment_ids_by_faction[support_row.faction_id]
        )
        assert set(support_row.supported_detachment_ids).issubset(set(support_row.detachment_ids))
        if support_row.overall != "Full":
            assert support_row.notes or support_row.ability_coverage_row_ids
    for mustering_row in mustering_rows:
        assert mustering_row.source_id
        assert mustering_row.support_stage in MUSTERING_SUPPORT_STAGE_VALUES
    assert known_mustering_source_ids.issubset(represented_mustering_source_ids)
    assert "army-mustering:drukhari-corsairs-and-travelling-players" in army_mustering_rule_ids
    assert SUPREME_COMMANDER_MUSTERING_CONSUMER_ID in army_mustering_rule_ids
    assert len(army_mustering_rule_ids) > 1
    assert "## Mustering / List Construction Support" in generated_markdown
    assert (
        "| Space Marine Chapters | `army-mustering:space-marine-chapters` | "
        "`phase17g:space-marines:space-marine-chapters` |"
    ) in generated_markdown
    assert generated_markdown.count("army-mustering:drukhari-corsairs-and-travelling-players") == 1
    assert "| Grey Knights - Gate of Infinity | Named army-rule handler |" in generated_markdown
    assert (
        "| Adepta Sororitas - Acts of Faith | "
        "Battle-round-start and unit-destroyed Miracle dice hooks |"
    ) in generated_markdown
    assert (
        "| Adeptus Custodes - Martial Ka'tah | "
        "Selected-to-fight stance grants plus melee weapon-profile modifier | "
        "Adapter contract, decision catalog, source coverage, and generated matrix | "
        "Focused grant, decision, runtime-modifier, source coverage, and fail-fast tests | "
        "Full |"
    ) in generated_markdown
    assert (
        "| Adeptus Mechanicus - Doctrina Imperatives | "
        "Battle-round-start Imperative selection plus weapon-profile and Protector "
        "melee hit-roll modifiers | "
        "Adapter contract, source coverage, generated matrix, and runtime inventory | "
        "Focused battle-round selection, invalid-submission, attached-unit, aura, "
        "and runtime-modifier tests | Full |"
    ) in generated_markdown
    assert (
        "| Leagues of Votann - Prioritised Efficiency | "
        "Named army-rule handler plus faction-resource ledger |"
    ) in generated_markdown
    necrons_reanimation_row_prefix = (
        "| Necrons - Reanimation Protocols | "
        "Named army-rule handler plus shared Healing Wounds resolver |"
    )
    assert necrons_reanimation_row_prefix in generated_markdown
    assert (
        "| Chaos Knights - Harbingers of Dread | Named army-rule handler | "
        "Adapter contract, decision catalog, source coverage, and generated matrix | "
        "Focused Dread selection, forced Battle-shock, mortal-wound, runtime-modifier, "
        "source ID, and fail-fast tests | Full |"
    ) in generated_markdown
    assert (
        "| Imperial Knights - Code Chivalric | "
        "Named army-rule handler plus setup/timing/runtime modifier hosts | "
        "Adapter contract, decision catalog, source coverage, and generated matrix | "
        "Focused oath selection, fulfilment, modifier, reroll, and source coverage tests | "
        "Full |"
    ) in generated_markdown
    assert (
        "| Imperial Knights - Bondsman | "
        "Named Command phase handler plus model-scoped persisting-effect host | "
        "Adapter contract, decision catalog, generated matrix, and runtime inventory | "
        "Focused command-phase selection, range, Armiger, drift, and expiry tests | "
        "Full |"
    ) in generated_markdown
    assert (
        "| Imperial Knights - Freeblades | Shared mustering/list-validation host | "
        "Generated matrix and mustering tests | Focused mustering tests | Full |"
    ) in generated_markdown
    assert (
        "| Thousand Sons - Cabal of Sorcerers | "
        "Shooting-phase-start faction-rule hook plus weapon-profile and mortal-wound "
        "Feel No Pain hooks | "
        "Adapter contract, decision catalog, source coverage, and generated matrix | "
        "Focused ritual, invalid-submission, movement, modifier, and wound tests | Full |"
    ) in generated_markdown
    assert (
        "| Genestealer Cults - Cult Ambush | "
        "Named army-rule handler plus faction-resource ledger, destroyed-unit resurgence, "
        "marker placement, and marker ingress hosts |"
    ) in generated_markdown
    assert (
        "| Tyranids - Shadow in the Warp and Synapse | "
        "Command-phase-start faction-rule hook plus Battle-shock and "
        "weapon-profile modifiers | "
        "README, adapter contract, decision catalog, source coverage, and "
        "generated matrix | "
        "Focused command-phase, Battle-shock, and runtime-modifier tests | Full |"
    ) in generated_markdown
    assert (
        "| Scouts X | Pre-battle Scout Move, Scout reserve setup, and Dedicated "
        "Transport Scout Move hosts | Adapter contract and decision catalog | "
        "Focused pre-battle, setup smoke, and enhancement-grant tests | Full | "
        "Consumes structured Scouts descriptors for distance selection; a SCOUTS keyword "
        "without a descriptor fails fast. |"
    ) in generated_markdown
    aeldari_markdown = generated_faction_markdown["aeldari.md"]
    adepta_sororitas_markdown = generated_faction_markdown["adepta-sororitas.md"]
    adeptus_custodes_markdown = generated_faction_markdown["adeptus-custodes.md"]
    adeptus_mechanicus_markdown = generated_faction_markdown["adeptus-mechanicus.md"]
    chaos_daemons_markdown = generated_faction_markdown["chaos-daemons.md"]
    emperors_children_markdown = generated_faction_markdown["emperors-children.md"]
    genestealer_cults_markdown = generated_faction_markdown["genestealer-cults.md"]
    imperial_knights_markdown = generated_faction_markdown["imperial-knights.md"]
    orks_markdown = generated_faction_markdown["orks.md"]
    tyranids_markdown = generated_faction_markdown["tyranids.md"]
    assert "## Detachment Rule Support" in aeldari_markdown
    assert "## Detachment Rule Support" in chaos_daemons_markdown
    assert "| Supported detachment rules |" in chaos_daemons_markdown
    assert "| 8 | 0 | 20 | 30 | 1 |" in adepta_sororitas_markdown
    assert "| 9 | 0 | 24 | 36 | 3 |" in adeptus_custodes_markdown
    assert "| 10 | 0 | 28 | 42 | 1 |" in adeptus_mechanicus_markdown
    assert "| 10 | 1 | 30 | 45 | 18 |" in emperors_children_markdown
    assert "| 9 | 0 | 20 | 30 | 3 |" in genestealer_cults_markdown
    assert "| 8 | 0 | 24 | 36 | 2 |" in imperial_knights_markdown
    assert "| 12 | 1 | 44 | 66 | 13 |" in orks_markdown
    assert "| 10 | 0 | 32 | 48 | 2 |" in tyranids_markdown
    assert (
        "| Daemonic Incursion | `Full` | Warp Rifts generic IR reserve-arrival distance hook |"
    ) in chaos_daemons_markdown
    assert (
        "| Warptide | `Full` | Shudderblink generic IR advance-move and advance-eligibility hooks |"
    ) in chaos_daemons_markdown
    assert "| Legion of Excess | `None` | Generated scaffold only |" in chaos_daemons_markdown
    assert "## Detachment Rule Coverage Rows" not in chaos_daemons_markdown
    assert "## Semantic Support Snapshot" in aeldari_markdown
    assert "### Exact Ability Semantic Coverage" in aeldari_markdown
    assert (
        "| Aeldari tradition | All exact abilities consumed | "
        "Exact IR parsed; host needed | Exact ability IR unsupported | "
        "Exact ability bridge blocked |"
    ) in aeldari_markdown
    assert "| Craftworlds / Asuryani | None | Crimson Hunter (`000000603`)" in aeldari_markdown
    assert "Eldrad Ulthran (`000000568`)<br>Falcon (`000000609`)" in aeldari_markdown
    assert "Wraithguard (`000000597`)" in aeldari_markdown
    assert "| Anhrathe / Corsairs | None | None | Corsair Skyreavers" in aeldari_markdown
    assert "| Harlequins | None | Skyweavers (`000002539`) |" in aeldari_markdown
    assert "| Ynnari | None | None | The Visarch" in aeldari_markdown
    for group_name in (
        "Craftworlds / Asuryani",
        "Anhrathe / Corsairs",
        "Harlequins",
        "Ynnari",
    ):
        group_row = next(
            line for line in aeldari_markdown.splitlines() if line.startswith(f"| {group_name} |")
        )
        assert group_row.endswith("| None |")
    assert "`generic_supported` / `engine_consumed`" not in aeldari_markdown
    assert "`named_handler_required` / `source_only`" not in aeldari_markdown
    assert (
        "| Detachment | Rule | Rule ID | Timing | Category | Source support | "
        "Execution status | Handler / block | Runtime consumers | Source IDs |"
    ) in orks_markdown
    assert (
        "| More Dakka! | Da Gobshot Thunderbuss | `000009991002` | "
        "army_construction | enhancement | `generic_supported` / `source_only` | "
        "`executable_generic_ir` |  | None |"
    ) in orks_markdown
    orks_get_stuck_in_row = next(
        line
        for line in orks_markdown.splitlines()
        if line.startswith("| More Dakka! | GET STUCK IN, LADZ! | `000009992003` |")
    )
    assert "| `generic_supported` / `source_only` | `executable_generic_ir` |" in (
        orks_get_stuck_in_row
    )
    assert (
        "| Cavalcade of Chaos | Apocalyptic Steeds Upgrade"
        "<br>Soul Shattering Charge Upgrade | None |"
    ) in chaos_daemons_markdown
    assert (
        "| Cavalcade of Chaos | From Beyond the Veil<br>Inescapable Manifestations"
        "<br>Warp-Riders | None |"
    ) in chaos_daemons_markdown
    assert "Current coverage categories:" not in generated_markdown
    assert "## Runtime Hook Inventory" in generated_markdown
    assert "| `catalog-ir:charge-roll-modifier` | Instrument of Chaos |" in generated_markdown
    assert "| `catalog-ir:hit-roll-modifier` | Revel in Desecration |" in generated_markdown
    assert "| `catalog-ir:wound-roll-modifier` | No current generated rows |" in generated_markdown
    assert (
        "| `catalog-ir:invulnerable-save-roll-modifier` | No current generated rows |"
    ) in generated_markdown
    assert "| `catalog-ir:feel-no-pain-source` | Collar of Khorne |" in generated_markdown
    for harbinger_consumer in ("lethal-hits", "precision", "sustained-hits"):
        assert (
            f"| `catalog-ir:weapon-keyword-grant:{harbinger_consumer}` | Harbinger of Death |"
        ) in generated_markdown
    assert (
        "| `catalog-ir:can-advance-and-charge` | No current generated rows |"
    ) in generated_markdown
    assert (
        "| `catalog-ir:can-fallback-and-shoot` | No current generated rows |"
    ) in generated_markdown
    assert (
        "| `catalog-ir:can-be-placed-in-reserves` | Hunters from the Warp |"
    ) in generated_markdown
    assert "| `core:command-reroll` | Command Re-roll |" in generated_markdown
    assert "From Beyond the Veil<br>GET STUCK IN, LADZ!" in generated_markdown
    assert "Casting Back the Veil<br>Cloak and Shadow" in generated_markdown
    assert "Inescapable Manifestations<br>Into the Breach<br>LONG, UNCONTROLLED BURSTS" in (
        generated_markdown
    )
    generic_rule_ir_inventory_row = next(
        line for line in generated_markdown.splitlines() if line.startswith("| `generic:rule-ir` |")
    )
    assert "BINDING SHADOW<br>Bilious Blessing<br>CALL DAT DAKKA?" in generic_rule_ir_inventory_row
    assert "CONTEMPTUOUS DISREGARD<br>Call to Murder<br>Casting Back the Veil" in (
        generic_rule_ir_inventory_row
    )
    assert "SHADE PATH<br>SINGLE-MINDED STRIKE" in generic_rule_ir_inventory_row
    assert (
        "SPESHUL SHELLS<br>SPITEFUL DEMISE<br>Skirling Magicks<br>Soulseeing"
        "<br>The Realm of Chaos<br>Vengeful Sorrow<br>Warp Surge<br>Warp-Riders |"
        in generic_rule_ir_inventory_row
    )
    assert (
        "| `warhammer_40000_11th:aeldari:detachment:corsair_coterie:"
        "relentless_raiders` | Relentless Raiders |"
    ) in generated_markdown
    assert (
        "| `warhammer_40000_11th:chaos_daemons:detachment:cavalcade_of_chaos:"
        "warp_riders` | Warp-Riders |"
    ) not in generated_markdown
    assert (
        "| `warhammer_40000_11th:chaos_daemons:detachment:cavalcade_of_chaos:"
        "soul_shattering_charge_upgrade` | Soul-Shattering Charge Upgrade |"
    ) not in generated_markdown
    assert (
        f"| `{imperial_knights_army_rule.SETUP_HOOK_ID}` | Code Chivalric - Oath Selection |"
    ) in generated_markdown
    for runtime_id in adepta_sororitas_runtime_ids:
        assert f"| `{runtime_id}` | Acts of Faith |" in generated_markdown
    assert (
        f"| `{adepta_sororitas_army_rule.TRIUMPH_RELICS_BATTLE_ROUND_START_HOOK_ID}` | "
        "Relics of the Matriarchs |"
    ) in generated_markdown
    assert (
        f"| `{adeptus_custodes_army_rule.DACATARAI_HOOK_ID}` | Martial Ka'tah - Dacatarai |"
    ) in generated_markdown
    assert (
        f"| `{adeptus_custodes_army_rule.RENDAX_HOOK_ID}` | Martial Ka'tah - Rendax |"
    ) in generated_markdown
    assert (
        f"| `{adeptus_custodes_army_rule.WEAPON_PROFILE_MODIFIER_ID}` | "
        "Martial Ka'tah - Weapon Profile |"
    ) in generated_markdown
    assert (
        f"| `{adeptus_mechanicus_army_rule.HOOK_ID}` | Doctrina Imperatives |"
    ) in generated_markdown
    assert (
        f"| `{adeptus_mechanicus_army_rule.PROTECTOR_HIT_MODIFIER_ID}` | "
        "Doctrina Imperatives - Protector Melee Hit Roll |"
    ) in generated_markdown
    assert (
        f"| `{adeptus_mechanicus_army_rule.WEAPON_PROFILE_MODIFIER_ID}` | "
        "Doctrina Imperatives - Weapon Profile |"
    ) in generated_markdown
    assert f"| `{imperial_knights_army_rule.BONDSMAN_HOOK_ID}` | Bondsman |" in (generated_markdown)
    assert (
        f"| `{imperial_knights_army_rule.END_BATTLE_ROUND_SUBSCRIPTION_ID}` | Code Chivalric |"
    ) in generated_markdown
    assert (
        f"| `{imperial_knights_army_rule.HOOK_ID}:martial-valour:fight` | "
        "Code Chivalric - Martial Valour |"
    ) in generated_markdown
    assert (f"| `{thousand_sons_army_rule.HOOK_ID}` | Cabal of Sorcerers |") in generated_markdown
    assert (
        f"| `{thousand_sons_army_rule.MORTAL_WOUND_FEEL_NO_PAIN_HOOK_ID}` | "
        "Cabal of Sorcerers - Mortal Wound Feel No Pain |"
    ) in generated_markdown
    assert (
        f"| `{thousand_sons_army_rule.WEAPON_PROFILE_MODIFIER_ID}` | "
        "Cabal of Sorcerers - Weapon Profile |"
    ) in generated_markdown
    for runtime_id in cult_ambush_runtime_ids:
        assert f"| `{runtime_id}` | Cult Ambush |" in generated_markdown
    assert (
        f"| `{tyranids_army_rule.HOOK_ID}` | Shadow in the Warp / Synapse |"
    ) in generated_markdown
    assert (
        f"| `{tyranids_army_rule.BATTLE_SHOCK_HOOK_ID}` | "
        "Shadow in the Warp / Synapse - Battle-shock |"
    ) in generated_markdown
    assert (
        f"| `{tyranids_army_rule.WEAPON_PROFILE_MODIFIER_ID}` | "
        "Shadow in the Warp / Synapse - Weapon Profile |"
    ) in generated_markdown
    assert tuple(row.datasheet_name for row in rows_by_name["Instrument of Chaos"]) == (
        "Bloodletters",
        "Bloodcrushers",
    )
    assert tuple(row.datasheet_name for row in rows_by_name["Daemonic Icon"]) == (
        "Bloodletters",
        "Bloodcrushers",
    )
    assert tuple(row.datasheet_name for row in rows_by_name["Deep Strike"]) == (
        "Flesh Hounds",
        "Bloodletters",
        "Bloodcrushers",
        "Be'lakor",
        "Daemon Prince of Chaos",
        "Soul Grinder",
        "Daemon Prince Of Chaos With Wings",
    )
    assert tuple(row.datasheet_name for row in rows_by_name["Collar of Khorne"]) == (
        "Flesh Hounds",
    )
    assert tuple(row.datasheet_name for row in rows_by_name["Hunters from the Warp"]) == (
        "Flesh Hounds",
    )
    assert all(
        row.support_stage is AbilityCoverageSupportStage.ENGINE_CONSUMED
        for row in rows_by_name["Instrument of Chaos"]
    )
    assert all(
        row.support_stage is AbilityCoverageSupportStage.ENGINE_CONSUMED
        for row in rows_by_name["Daemonic Icon"]
    )
    assert all(
        row.support_stage is AbilityCoverageSupportStage.ENGINE_CONSUMED
        for row in rows_by_name["Deep Strike"]
    )
    assert all(
        row.support_stage is AbilityCoverageSupportStage.ENGINE_CONSUMED
        for row in rows_by_name["Collar of Khorne"]
    )
    assert all(
        row.support_stage is AbilityCoverageSupportStage.ENGINE_CONSUMED
        for row in rows_by_name["Hunters from the Warp"]
    )
    assert all(
        row.support_stage is AbilityCoverageSupportStage.ENGINE_CONSUMED
        for row in rows_by_name["The Shadow of Chaos"]
    )
    assert all(
        row.support_stage is AbilityCoverageSupportStage.ENGINE_CONSUMED
        for row in rows_by_name["Dark Pacts"]
    )
    assert all(
        row.support_stage is AbilityCoverageSupportStage.ENGINE_CONSUMED
        for row in rows_by_name["Nurgle's Gift"]
    )
    assert any(
        row.support_stage is AbilityCoverageSupportStage.ENGINE_CONSUMED
        for row in rows_by_name["Blessings of Khorne"]
    )
    assert any(
        row.datasheet_id == "000004207"
        and row.support_stage is AbilityCoverageSupportStage.DESCRIPTOR_ONLY
        for row in rows_by_name["Blessings of Khorne"]
    )
    assert any(
        row.support_stage is AbilityCoverageSupportStage.ENGINE_CONSUMED
        for row in rows_by_name["Thrill Seekers"]
    )
    assert any(
        row.datasheet_id == "000004208"
        and row.support_stage is AbilityCoverageSupportStage.DESCRIPTOR_ONLY
        for row in rows_by_name["Thrill Seekers"]
    )
    assert all(
        row.support_stage is AbilityCoverageSupportStage.ENGINE_CONSUMED
        for row in rows_by_name["Prioritised Efficiency"]
    )
    assert all(
        row.support_stage is AbilityCoverageSupportStage.ENGINE_CONSUMED
        for row in rows_by_name["Cabal of Sorcerers"]
    )
    assert all(
        row.support_stage is AbilityCoverageSupportStage.ENGINE_CONSUMED
        for row in rows_by_name["Cult Ambush"]
    )
    assert all(
        row.support_stage is AbilityCoverageSupportStage.ENGINE_CONSUMED
        for row in rows_by_name["Martial Ka'tah"]
    )
    assert all(
        row.support_stage is AbilityCoverageSupportStage.ENGINE_CONSUMED
        for row in rows_by_name["Doctrina Imperatives"]
    )
    assert all(
        row.support_stage is AbilityCoverageSupportStage.ENGINE_CONSUMED
        for row in rows_by_name["Shadow in the Warp / Synapse"]
    )
    assert all(
        row.support_stage is AbilityCoverageSupportStage.ENGINE_CONSUMED
        for row in rows_by_name["Code Chivalric"]
    )
    assert all(
        row.support_stage is AbilityCoverageSupportStage.ENGINE_CONSUMED
        for row in rows_by_name["Bondsman"]
    )
    assert all(
        row.runtime_consumer_ids
        == ("warhammer_40000_11th:chaos_daemons:army_rule:shadow_of_chaos",)
        for row in rows_by_name["The Shadow of Chaos"]
    )
    assert tuple(row.datasheet_name for row in rows_by_name["Nurgle's Gift"]) == ("Death Guard",)
    assert tuple(row.datasheet_name for row in rows_by_name["Dark Pacts"]) == (
        "Chaos Space Marines",
    )
    assert tuple(row.datasheet_name for row in rows_by_name["Blessings of Khorne"]) == (
        "Defiler",
        "World Eaters",
    )
    assert tuple(row.datasheet_name for row in rows_by_name["Thrill Seekers"]) == (
        "Defiler",
        "Emperor's Children",
    )
    assert tuple(row.datasheet_name for row in rows_by_name["Prioritised Efficiency"]) == (
        "Leagues of Votann",
    )
    assert tuple(row.datasheet_name for row in rows_by_name["Cabal of Sorcerers"]) == (
        "Thousand Sons",
    )
    assert tuple(row.datasheet_name for row in rows_by_name["Cult Ambush"]) == (
        "Genestealer Cults",
    )
    assert tuple(row.datasheet_name for row in rows_by_name["Acts of Faith"]) == (
        "Adepta Sororitas",
    )
    assert tuple(row.datasheet_name for row in rows_by_name["Martial Ka'tah"]) == (
        "Adeptus Custodes",
    )
    assert tuple(row.datasheet_name for row in rows_by_name["Doctrina Imperatives"]) == (
        "Adeptus Mechanicus",
    )
    assert tuple(row.datasheet_name for row in rows_by_name["Shadow in the Warp / Synapse"]) == (
        "Tyranids",
    )
    assert tuple(row.datasheet_name for row in rows_by_name["Code Chivalric"]) == (
        "Imperial Knights",
    )
    assert tuple(row.datasheet_name for row in rows_by_name["Bondsman"]) == ("Imperial Knights",)
    assert set(rows_by_name["Dark Pacts"][0].runtime_consumer_ids) == {
        chaos_space_marines_army_rule.ATTACK_SEQUENCE_COMPLETED_HOOK_ID,
        chaos_space_marines_army_rule.FIGHT_LETHAL_HITS_HOOK_ID,
        chaos_space_marines_army_rule.FIGHT_SUSTAINED_HITS_HOOK_ID,
        chaos_space_marines_army_rule.MORTAL_WOUND_FEEL_NO_PAIN_HOOK_ID,
        chaos_space_marines_army_rule.SHOOTING_LETHAL_HITS_HOOK_ID,
        chaos_space_marines_army_rule.SHOOTING_SUSTAINED_HITS_HOOK_ID,
        chaos_space_marines_army_rule.WEAPON_PROFILE_MODIFIER_ID,
    }
    assert set(rows_by_name["Nurgle's Gift"][0].runtime_consumer_ids) == {
        death_guard_army_rule.HOOK_ID,
        f"{death_guard_army_rule.HOOK_ID}:armour-save-option",
        f"{death_guard_army_rule.HOOK_ID}:leadership",
        f"{death_guard_army_rule.HOOK_ID}:melee-hit-roll",
        f"{death_guard_army_rule.HOOK_ID}:movement-budget",
        f"{death_guard_army_rule.HOOK_ID}:objective-control",
        f"{death_guard_army_rule.HOOK_ID}:toughness",
    }
    blessings_of_khorne_engine_row = next(
        row
        for row in rows_by_name["Blessings of Khorne"]
        if row.support_stage is AbilityCoverageSupportStage.ENGINE_CONSUMED
    )
    thrill_seekers_engine_row = next(
        row
        for row in rows_by_name["Thrill Seekers"]
        if row.support_stage is AbilityCoverageSupportStage.ENGINE_CONSUMED
    )
    assert set(blessings_of_khorne_engine_row.runtime_consumer_ids) == {
        world_eaters_army_rule.HOOK_ID,
        world_eaters_army_rule.RAGE_FUELLED_INVIGORATION_HOOK_ID,
        world_eaters_army_rule.TOTAL_CARNAGE_HOOK_ID,
        world_eaters_army_rule.UNBRIDLED_BLOODLUST_CHARGE_MODIFIER_ID,
        f"{world_eaters_army_rule.HOOK_ID}:weapon-profile-keywords",
    }
    assert set(thrill_seekers_engine_row.runtime_consumer_ids) == {
        emperors_children_army_rule.ADVANCE_ELIGIBILITY_HOOK_ID,
        emperors_children_army_rule.FALL_BACK_ELIGIBILITY_HOOK_ID,
        emperors_children_army_rule.SHOOTING_TARGET_RESTRICTION_HOOK_ID,
        emperors_children_army_rule.CHARGE_TARGET_RESTRICTION_HOOK_ID,
    }
    assert set(rows_by_name["Prioritised Efficiency"][0].runtime_consumer_ids) == {
        "warhammer_40000_11th:leagues_of_votann:army_rule:"
        "prioritised_efficiency:command-phase-start",
        "warhammer_40000_11th:leagues_of_votann:army_rule:prioritised_efficiency:hit-roll",
        "warhammer_40000_11th:leagues_of_votann:army_rule:prioritised_efficiency:wound-roll",
    }
    assert set(rows_by_name["Cabal of Sorcerers"][0].runtime_consumer_ids) == {
        thousand_sons_army_rule.HOOK_ID,
        thousand_sons_army_rule.MORTAL_WOUND_FEEL_NO_PAIN_HOOK_ID,
        thousand_sons_army_rule.WEAPON_PROFILE_MODIFIER_ID,
    }
    assert set(rows_by_name["Cult Ambush"][0].runtime_consumer_ids) == set(cult_ambush_runtime_ids)
    assert set(rows_by_name["Acts of Faith"][0].runtime_consumer_ids) == set(
        adepta_sororitas_coverage_runtime_ids
    )
    assert set(rows_by_name["Martial Ka'tah"][0].runtime_consumer_ids) == set(
        adeptus_custodes_runtime_ids
    )
    assert set(rows_by_name["Doctrina Imperatives"][0].runtime_consumer_ids) == set(
        adeptus_mechanicus_runtime_ids
    )
    assert set(rows_by_name["Shadow in the Warp / Synapse"][0].runtime_consumer_ids) == {
        tyranids_army_rule.HOOK_ID,
        tyranids_army_rule.BATTLE_SHOCK_HOOK_ID,
        tyranids_army_rule.WEAPON_PROFILE_MODIFIER_ID,
    }
    assert any(
        row_payload["ability_id"] == thousand_sons_army_rule.HOOK_ID
        and row_payload["ability_name"] == "Cabal of Sorcerers"
        and row_payload["datasheet_name"] == "Thousand Sons"
        and row_payload["support_stage"] == AbilityCoverageSupportStage.ENGINE_CONSUMED.value
        and set(row_payload["runtime_consumer_ids"])
        == {
            thousand_sons_army_rule.HOOK_ID,
            thousand_sons_army_rule.MORTAL_WOUND_FEEL_NO_PAIN_HOOK_ID,
            thousand_sons_army_rule.WEAPON_PROFILE_MODIFIER_ID,
        }
        for row_payload in snapshot
    )
    assert any(
        row_payload["ability_id"] == genestealer_cults_cult_ambush.SOURCE_RULE_ID
        and row_payload["ability_name"] == "Cult Ambush"
        and row_payload["datasheet_name"] == "Genestealer Cults"
        and row_payload["support_stage"] == AbilityCoverageSupportStage.ENGINE_CONSUMED.value
        and set(row_payload["runtime_consumer_ids"]) == set(cult_ambush_runtime_ids)
        for row_payload in snapshot
    )
    assert any(
        row_payload["ability_id"] == adepta_sororitas_army_rule.HOOK_ID
        and row_payload["ability_name"] == "Acts of Faith"
        and row_payload["datasheet_name"] == "Adepta Sororitas"
        and row_payload["support_stage"] == AbilityCoverageSupportStage.ENGINE_CONSUMED.value
        and set(row_payload["runtime_consumer_ids"]) == set(adepta_sororitas_coverage_runtime_ids)
        for row_payload in snapshot
    )
    assert any(
        row_payload["ability_id"] == adeptus_custodes_army_rule.HOOK_ID
        and row_payload["ability_name"] == "Martial Ka'tah"
        and row_payload["datasheet_name"] == "Adeptus Custodes"
        and row_payload["support_stage"] == AbilityCoverageSupportStage.ENGINE_CONSUMED.value
        and set(row_payload["runtime_consumer_ids"]) == set(adeptus_custodes_runtime_ids)
        for row_payload in snapshot
    )
    assert any(
        row_payload["ability_id"] == adeptus_mechanicus_army_rule.HOOK_ID
        and row_payload["ability_name"] == "Doctrina Imperatives"
        and row_payload["datasheet_name"] == "Adeptus Mechanicus"
        and row_payload["support_stage"] == AbilityCoverageSupportStage.ENGINE_CONSUMED.value
        and set(row_payload["runtime_consumer_ids"]) == set(adeptus_mechanicus_runtime_ids)
        for row_payload in snapshot
    )
    assert any(
        row_payload["ability_id"] == tyranids_army_rule.HOOK_ID
        and row_payload["ability_name"] == "Shadow in the Warp / Synapse"
        and row_payload["datasheet_name"] == "Tyranids"
        and row_payload["support_stage"] == AbilityCoverageSupportStage.ENGINE_CONSUMED.value
        and set(row_payload["runtime_consumer_ids"])
        == {
            tyranids_army_rule.HOOK_ID,
            tyranids_army_rule.BATTLE_SHOCK_HOOK_ID,
            tyranids_army_rule.WEAPON_PROFILE_MODIFIER_ID,
        }
        for row_payload in snapshot
    )
    assert set(rows_by_name["Code Chivalric"][0].runtime_consumer_ids) == {
        imperial_knights_army_rule.HOOK_ID,
        imperial_knights_army_rule.SETUP_HOOK_ID,
        imperial_knights_army_rule.UNIT_DESTROYED_HOOK_ID,
        imperial_knights_army_rule.END_TURN_EVENT_HANDLER_ID,
        imperial_knights_army_rule.END_BATTLE_ROUND_EVENT_HANDLER_ID,
        f"{imperial_knights_army_rule.HOOK_ID}:martial-valour:shooting",
        f"{imperial_knights_army_rule.HOOK_ID}:martial-valour:fight",
        f"{imperial_knights_army_rule.HOOK_ID}:eager:movement-budget",
        f"{imperial_knights_army_rule.HOOK_ID}:eager:charge-roll",
        f"{imperial_knights_army_rule.HOOK_ID}:legacy:objective-control",
        f"{imperial_knights_army_rule.HOOK_ID}:legacy:leadership",
    }
    assert rows_by_name["Bondsman"][0].runtime_consumer_ids == (
        imperial_knights_army_rule.BONDSMAN_HOOK_ID,
    )
    assert categories_by_name["Faction Army Rule Prioritised Efficiency"].support_stages == (
        AbilityCoverageSupportStage.ENGINE_CONSUMED,
    )
    assert categories_by_name["Faction Army Rule Code Chivalric"].support_stages == (
        AbilityCoverageSupportStage.ENGINE_CONSUMED,
    )
    assert categories_by_name["Faction Army Rule Bondsman"].support_stages == (
        AbilityCoverageSupportStage.ENGINE_CONSUMED,
    )
    assert categories_by_name["Faction Army Rule Doctrina Imperatives"].support_stages == (
        AbilityCoverageSupportStage.ENGINE_CONSUMED,
    )
    assert categories_by_name["Faction Army Rule Doctrina Imperatives"].datasheet_names == (
        "Adeptus Mechanicus",
    )
    assert set(
        categories_by_name["Faction Army Rule Doctrina Imperatives"].runtime_consumer_ids
    ) == set(adeptus_mechanicus_runtime_ids)
    assert categories_by_name["Leadership Characteristic"].ability_names == ("Daemonic Icon",)
    assert categories_by_name["Leadership Characteristic"].datasheet_names == (
        "Bloodcrushers",
        "Bloodletters",
    )
    assert categories_by_name["Leadership Characteristic"].coverage_row_count == 2
    assert categories_by_name["Leadership Characteristic"].source_kind_counts == (("wargear", 2),)
    assert tuple(
        (pair.ability_name, pair.datasheet_name)
        for pair in categories_by_name["Leadership Characteristic"].ability_datasheet_pairs
    ) == (
        ("Daemonic Icon", "Bloodcrushers"),
        ("Daemonic Icon", "Bloodletters"),
    )
    assert categories_by_name["Leadership Characteristic"].support_stages == (
        AbilityCoverageSupportStage.ENGINE_CONSUMED,
    )
    assert categories_by_name["Charge Roll Modifier"].ability_names == ("Instrument of Chaos",)
    assert categories_by_name["Charge Roll Modifier"].datasheet_names == (
        "Bloodcrushers",
        "Bloodletters",
    )
    assert categories_by_name["Charge Roll Modifier"].support_stages == (
        AbilityCoverageSupportStage.ENGINE_CONSUMED,
    )
    assert categories_by_name["Deep Strike Reserve Arrival"].ability_names == ("Deep Strike",)
    assert categories_by_name["Deep Strike Reserve Arrival"].runtime_consumer_ids == (
        "descriptor:movement:deep-strike-placement",
        "descriptor:reserve-declaration:deep-strike",
    )
    assert categories_by_name["Deep Strike Reserve Arrival"].support_stages == (
        AbilityCoverageSupportStage.ENGINE_CONSUMED,
    )
    assert categories_by_name["Feel No Pain Source"].ability_names == ("Collar of Khorne",)
    assert categories_by_name["Feel No Pain Source"].datasheet_names == ("Flesh Hounds",)
    assert categories_by_name["Feel No Pain Source"].runtime_consumer_ids == (
        "catalog-ir:feel-no-pain-source",
    )
    assert categories_by_name["Feel No Pain Source"].support_stages == (
        AbilityCoverageSupportStage.ENGINE_CONSUMED,
    )
    assert categories_by_name["Datasheet Rule Ir Placement Permission This Unit"].ability_names == (
        "Hunters from the Warp",
    )
    assert categories_by_name[
        "Datasheet Rule Ir Placement Permission This Unit"
    ].datasheet_names == ("Flesh Hounds",)
    assert categories_by_name[
        "Datasheet Rule Ir Placement Permission This Unit"
    ].runtime_consumer_ids == ("catalog-ir:can-be-placed-in-reserves",)
    assert categories_by_name[
        "Datasheet Rule Ir Placement Permission This Unit"
    ].support_stages == (AbilityCoverageSupportStage.ENGINE_CONSUMED,)
    assert categories_by_name["Chaos Daemons Army Rule"].ability_names == ("The Shadow of Chaos",)
    assert categories_by_name["Chaos Daemons Army Rule"].runtime_consumer_ids == (
        "warhammer_40000_11th:chaos_daemons:army_rule:shadow_of_chaos",
    )
    assert categories_by_name["Chaos Daemons Army Rule"].support_stages == (
        AbilityCoverageSupportStage.ENGINE_CONSUMED,
    )
    assert categories_by_name["Chaos Space Marines Army Rule"].ability_names == ("Dark Pacts",)
    assert categories_by_name["Chaos Space Marines Army Rule"].support_stages == (
        AbilityCoverageSupportStage.ENGINE_CONSUMED,
    )
    assert categories_by_name["Death Guard Army Rule"].ability_names == ("Nurgle's Gift",)
    assert categories_by_name["Death Guard Army Rule"].support_stages == (
        AbilityCoverageSupportStage.ENGINE_CONSUMED,
    )
    assert categories_by_name["World Eaters Army Rule"].ability_names == ("Blessings of Khorne",)
    assert categories_by_name["World Eaters Army Rule"].support_stages == (
        AbilityCoverageSupportStage.ENGINE_CONSUMED,
    )
    assert categories_by_name["Emperor's Children Army Rule"].ability_names == ("Thrill Seekers",)
    assert categories_by_name["Emperor's Children Army Rule"].support_stages == (
        AbilityCoverageSupportStage.ENGINE_CONSUMED,
    )
    assert categories_by_name["Faction Army Rule Cabal Of Sorcerers"].ability_names == (
        "Cabal of Sorcerers",
    )
    assert categories_by_name["Faction Army Rule Cabal Of Sorcerers"].runtime_consumer_ids == (
        thousand_sons_army_rule.HOOK_ID,
        thousand_sons_army_rule.MORTAL_WOUND_FEEL_NO_PAIN_HOOK_ID,
        thousand_sons_army_rule.WEAPON_PROFILE_MODIFIER_ID,
    )
    assert categories_by_name["Faction Army Rule Cabal Of Sorcerers"].support_stages == (
        AbilityCoverageSupportStage.ENGINE_CONSUMED,
    )
    assert categories_by_name["Faction Army Rule Cult Ambush"].ability_names == ("Cult Ambush",)
    assert categories_by_name["Faction Army Rule Cult Ambush"].runtime_consumer_ids == tuple(
        sorted(cult_ambush_runtime_ids)
    )
    assert categories_by_name["Faction Army Rule Cult Ambush"].support_stages == (
        AbilityCoverageSupportStage.ENGINE_CONSUMED,
    )
    assert categories_by_name["Faction Army Rule Acts Of Faith"].ability_names == ("Acts of Faith",)
    assert categories_by_name["Faction Army Rule Acts Of Faith"].runtime_consumer_ids == tuple(
        sorted(adepta_sororitas_coverage_runtime_ids)
    )
    assert categories_by_name["Faction Army Rule Acts Of Faith"].support_stages == (
        AbilityCoverageSupportStage.ENGINE_CONSUMED,
    )
    assert categories_by_name["Faction Army Rule Martial Katah"].ability_names == (
        "Martial Ka'tah",
    )
    assert categories_by_name["Faction Army Rule Martial Katah"].runtime_consumer_ids == tuple(
        sorted(adeptus_custodes_runtime_ids)
    )
    assert categories_by_name["Faction Army Rule Martial Katah"].support_stages == (
        AbilityCoverageSupportStage.ENGINE_CONSUMED,
    )
    assert categories_by_name["Faction Army Rule Shadow In The Warp Synapse"].ability_names == (
        "Shadow in the Warp / Synapse",
    )
    assert categories_by_name[
        "Faction Army Rule Shadow In The Warp Synapse"
    ].runtime_consumer_ids == (
        tyranids_army_rule.HOOK_ID,
        tyranids_army_rule.BATTLE_SHOCK_HOOK_ID,
        tyranids_army_rule.WEAPON_PROFILE_MODIFIER_ID,
    )
    assert categories_by_name["Faction Army Rule Shadow In The Warp Synapse"].support_stages == (
        AbilityCoverageSupportStage.ENGINE_CONSUMED,
    )
    assert any(
        row_payload["category_name"] == "Faction Army Rule Shadow In The Warp Synapse"
        and row_payload["ability_names"] == ["Shadow in the Warp / Synapse"]
        and row_payload["support_stages"] == [AbilityCoverageSupportStage.ENGINE_CONSUMED.value]
        and set(row_payload["runtime_consumer_ids"])
        == {
            tyranids_army_rule.HOOK_ID,
            tyranids_army_rule.BATTLE_SHOCK_HOOK_ID,
            tyranids_army_rule.WEAPON_PROFILE_MODIFIER_ID,
        }
        for row_payload in category_snapshot
    )
    assert any(
        row_payload["category_name"] == "Faction Army Rule Cult Ambush"
        and row_payload["ability_names"] == ["Cult Ambush"]
        and row_payload["support_stages"] == [AbilityCoverageSupportStage.ENGINE_CONSUMED.value]
        and set(row_payload["runtime_consumer_ids"]) == set(cult_ambush_runtime_ids)
        for row_payload in category_snapshot
    )
    assert any(
        row_payload["category_name"] == "Faction Army Rule Acts Of Faith"
        and row_payload["ability_names"] == ["Acts of Faith"]
        and row_payload["support_stages"] == [AbilityCoverageSupportStage.ENGINE_CONSUMED.value]
        and set(row_payload["runtime_consumer_ids"]) == set(adepta_sororitas_coverage_runtime_ids)
        for row_payload in category_snapshot
    )
    assert any(
        row_payload["category_name"] == "Faction Army Rule Martial Katah"
        and row_payload["ability_names"] == ["Martial Ka'tah"]
        and row_payload["support_stages"] == [AbilityCoverageSupportStage.ENGINE_CONSUMED.value]
        and set(row_payload["runtime_consumer_ids"]) == set(adeptus_custodes_runtime_ids)
        for row_payload in category_snapshot
    )
    assert categories_by_name[
        "Datasheet Roll Modifier Desperate Escape Enemy Unit"
    ].ability_names == ("Bane of Cowards",)
    assert categories_by_name[
        "Datasheet Rule Ir Force Desperate Escape Tests Enemy Unit"
    ].ability_names == ("Bane of Cowards",)
    assert categories_by_name[
        "Datasheet Roll Modifier Desperate Escape Enemy Unit"
    ].runtime_consumer_ids == (
        CATALOG_IR_DESPERATE_ESCAPE_ROLL_MODIFIER_CONSUMER_ID,
        CATALOG_IR_FORCE_DESPERATE_ESCAPE_CONSUMER_ID,
    )
    assert categories_by_name[
        "Datasheet Rule Ir Force Desperate Escape Tests Enemy Unit"
    ].runtime_consumer_ids == (
        CATALOG_IR_DESPERATE_ESCAPE_ROLL_MODIFIER_CONSUMER_ID,
        CATALOG_IR_FORCE_DESPERATE_ESCAPE_CONSUMER_ID,
    )
    assert categories_by_name[
        "Datasheet Roll Modifier Desperate Escape Enemy Unit"
    ].support_stages == (AbilityCoverageSupportStage.ENGINE_CONSUMED,)
    assert categories_by_name[
        "Datasheet Rule Ir Force Desperate Escape Tests Enemy Unit"
    ].support_stages == (AbilityCoverageSupportStage.ENGINE_CONSUMED,)
    assert categories_by_name[
        "Datasheet Rule Ir Inflict Mortal Wounds Enemy Unit"
    ].ability_names == ("Brass Stampede",)
    assert categories_by_name[
        "Datasheet Rule Ir Inflict Mortal Wounds Enemy Unit"
    ].runtime_consumer_ids == (CATALOG_IR_UNIT_MOVE_COMPLETED_MORTAL_WOUNDS_CONSUMER_ID,)
    assert categories_by_name[
        "Datasheet Rule Ir Inflict Mortal Wounds Enemy Unit"
    ].support_stages == (AbilityCoverageSupportStage.ENGINE_CONSUMED,)


def test_phase17k_ability_coverage_api_fails_fast_and_classifies_unsupported_ir() -> None:
    package = _bloodcrushers_package()
    unsupported_package = build_canonical_catalog_package(
        package_id=_catalog_package_id(),
        catalog_version=_catalog_version(),
        source_artifacts=build_wahapedia_canonical_bridge_artifacts(
            source_artifacts=_unsupported_wargear_rule_source_artifacts(),
            bridge_package_id=_bridge_package_id(),
            datasheet_ids=("test-unsupported-unit",),
            height_overrides=(
                ModelHeightOverride(
                    datasheet_id="test-unsupported-unit",
                    model_name="Alpha",
                    height=1.0,
                    height_units=GeometrySourceUnits.INCHES,
                    height_source_id="test-source:unsupported-height",
                    height_document_reference="test-doc:unsupported-height",
                ),
            ),
        ),
    )
    unsupported_rows = ability_coverage_rows_from_catalog(
        unsupported_package.army_catalog,
        datasheet_ids=("test-unsupported-unit",),
    )
    rows_by_name = {row.ability_name: row for row in unsupported_rows}
    scatter = rows_by_name["Scatter Icon"]
    broken_instrument = rows_by_name["Broken Instrument"]
    hit_charm = rows_by_name["Hit Charm"]
    tithe_charm = rows_by_name["Tithe Charm"]

    assert (
        ability_coverage_rows_from_catalog(
            package.army_catalog,
            datasheet_ids=("not-a-datasheet",),
        )
        == ()
    )
    assert scatter.support_stage is AbilityCoverageSupportStage.IR_COMPILED_UNSUPPORTED
    assert scatter.diagnostic_reasons == ("unsupported_language",)
    assert scatter.semantic_categories == ("wargear.unsupported.unsupported_language",)
    assert broken_instrument.support_stage is AbilityCoverageSupportStage.IR_COMPILED_UNSUPPORTED
    assert broken_instrument.runtime_consumer_ids == ("catalog-ir:charge-roll-modifier",)
    assert broken_instrument.semantic_categories == (
        "wargear.roll_modifier.charge.this_unit",
        "wargear.unsupported.unsupported_language",
    )
    assert hit_charm.support_stage is AbilityCoverageSupportStage.GENERIC_IR_EXECUTABLE
    assert hit_charm.semantic_categories == ("wargear.roll_modifier.hit.this_unit",)
    assert tithe_charm.support_stage is AbilityCoverageSupportStage.GENERIC_IR_EXECUTABLE
    assert tithe_charm.semantic_categories == ("wargear.rule_ir.modify_command_points.unscoped",)
    with pytest.raises(GameLifecycleError, match="requires an ArmyCatalog"):
        ability_coverage_rows_from_catalog(cast(ArmyCatalog, object()))
    with pytest.raises(GameLifecycleError, match="datasheet_ids must be a tuple"):
        ability_coverage_rows_from_catalog(
            package.army_catalog,
            datasheet_ids=cast(tuple[str, ...], ["000001115"]),
        )
    with pytest.raises(GameLifecycleError, match="rows must be a tuple"):
        ability_coverage_rows_payload(cast(tuple[AbilityCoverageRow, ...], []))
    with pytest.raises(GameLifecycleError, match="rows must be a tuple"):
        ability_coverage_category_rows(cast(tuple[AbilityCoverageRow, ...], []))
    with pytest.raises(GameLifecycleError, match="require coverage rows"):
        ability_coverage_category_rows(cast(tuple[AbilityCoverageRow, ...], (object(),)))
    with pytest.raises(GameLifecycleError, match="category rows must be a tuple"):
        ability_coverage_category_rows_payload(cast(tuple[AbilityCoverageCategoryRow, ...], []))
    with pytest.raises(GameLifecycleError, match="require category rows"):
        ability_coverage_category_rows_payload(
            cast(tuple[AbilityCoverageCategoryRow, ...], (object(),))
        )
    with pytest.raises(GameLifecycleError, match="catalog_id"):
        _ability_coverage_row(catalog_id="")
    with pytest.raises(GameLifecycleError, match="datasheet_id"):
        _ability_coverage_row(datasheet_id="")
    with pytest.raises(GameLifecycleError, match="datasheet_name"):
        _ability_coverage_row(datasheet_name="")
    with pytest.raises(GameLifecycleError, match="ability_id"):
        _ability_coverage_row(ability_id="")
    with pytest.raises(GameLifecycleError, match="ability_name"):
        _ability_coverage_row(ability_name="")
    with pytest.raises(GameLifecycleError, match="source_kind"):
        _ability_coverage_row(source_kind=cast(CatalogAbilitySourceKind, "bad"))
    with pytest.raises(GameLifecycleError, match="source_wargear_id"):
        _ability_coverage_row(source_wargear_id="")
    with pytest.raises(GameLifecycleError, match="catalog_support"):
        _ability_coverage_row(catalog_support=cast(CatalogAbilitySupport, "bad"))
    with pytest.raises(GameLifecycleError, match="support_stage"):
        _ability_coverage_row(support_stage=cast(AbilityCoverageSupportStage, "bad"))
    with pytest.raises(GameLifecycleError, match="semantic_categories"):
        _ability_coverage_row(semantic_categories=("",))
    with pytest.raises(GameLifecycleError, match="runtime_consumer_ids"):
        _ability_coverage_row(runtime_consumer_ids=cast(tuple[str, ...], []))
    with pytest.raises(GameLifecycleError, match="diagnostic_reasons"):
        _ability_coverage_row(diagnostic_reasons=("",))
    with pytest.raises(GameLifecycleError, match="coverage_row_id"):
        _ability_datasheet_pair(coverage_row_id="")
    with pytest.raises(GameLifecycleError, match="ability_id"):
        _ability_datasheet_pair(ability_id="")
    with pytest.raises(GameLifecycleError, match="ability_name"):
        _ability_datasheet_pair(ability_name="")
    with pytest.raises(GameLifecycleError, match="datasheet_id"):
        _ability_datasheet_pair(datasheet_id="")
    with pytest.raises(GameLifecycleError, match="datasheet_name"):
        _ability_datasheet_pair(datasheet_name="")
    with pytest.raises(GameLifecycleError, match="source_kind"):
        _ability_datasheet_pair(source_kind=cast(CatalogAbilitySourceKind, "bad"))
    with pytest.raises(GameLifecycleError, match="category_id"):
        _ability_coverage_category_row(category_id="")
    with pytest.raises(GameLifecycleError, match="category_name"):
        _ability_coverage_category_row(category_name="")
    with pytest.raises(GameLifecycleError, match="coverage_row_count"):
        _ability_coverage_category_row(coverage_row_count=0)
    with pytest.raises(GameLifecycleError, match="coverage_row_ids"):
        _ability_coverage_category_row(coverage_row_ids=())
    with pytest.raises(GameLifecycleError, match="ability_datasheet_pairs must be a tuple"):
        _ability_coverage_category_row(
            ability_datasheet_pairs=cast(tuple[AbilityCoverageAbilityDatasheetPair, ...], [])
        )
    with pytest.raises(GameLifecycleError, match="ability_datasheet_pairs must match"):
        _ability_coverage_category_row(ability_datasheet_pairs=())
    with pytest.raises(GameLifecycleError, match="ability_datasheet_pairs must contain"):
        _ability_coverage_category_row(
            ability_datasheet_pairs=cast(
                tuple[AbilityCoverageAbilityDatasheetPair, ...],
                (object(),),
            )
        )
    with pytest.raises(GameLifecycleError, match="source_kind_counts must be a tuple"):
        _ability_coverage_category_row(source_kind_counts=cast(tuple[tuple[str, int], ...], []))
    with pytest.raises(GameLifecycleError, match="source_kind_counts entries must be pairs"):
        _ability_coverage_category_row(source_kind_counts=cast(tuple[tuple[str, int], ...], ((),)))
    with pytest.raises(GameLifecycleError, match="source_kind_counts keys must be strings"):
        _ability_coverage_category_row(
            source_kind_counts=cast(tuple[tuple[str, int], ...], ((1, 1),))
        )
    with pytest.raises(GameLifecycleError, match="source_kind_counts keys must be unique"):
        _ability_coverage_category_row(
            coverage_row_count=2,
            coverage_row_ids=("test-row-1", "test-row-2"),
            ability_datasheet_pairs=(
                _ability_datasheet_pair(coverage_row_id="test-row-1"),
                _ability_datasheet_pair(coverage_row_id="test-row-2"),
            ),
            source_kind_counts=(("wargear", 1), ("wargear", 1)),
        )
    with pytest.raises(GameLifecycleError, match="source_kind_counts values"):
        _ability_coverage_category_row(source_kind_counts=(("wargear", 0),))
    with pytest.raises(GameLifecycleError, match="source_kind_counts must match"):
        _ability_coverage_category_row(source_kind_counts=(("wargear", 2),))
    with pytest.raises(GameLifecycleError, match="support_stages"):
        _ability_coverage_category_row(
            support_stages=cast(tuple[AbilityCoverageSupportStage, ...], [])
        )
    with pytest.raises(GameLifecycleError, match="support_stages"):
        _ability_coverage_category_row(
            support_stages=cast(tuple[AbilityCoverageSupportStage, ...], ("bad",))
        )


def test_phase17k_catalog_ir_future_hooks_classify_supported_rule_ir_without_consuming() -> None:
    registered_hook_ids = set(catalog_rule_ir_registered_hook_ids())
    rule_ir = _catalog_rule_ir(
        (
            _effect(RuleEffectKind.MODIFY_DICE_ROLL, roll_type="hit", delta=1),
            _effect(RuleEffectKind.MODIFY_DICE_ROLL, roll_type="wound", delta=1),
            _effect(RuleEffectKind.MODIFY_DICE_ROLL, roll_type="invulnerable_save", delta=1),
            _effect(RuleEffectKind.MODIFY_DICE_ROLL, roll_type="critical_hit", delta=-1),
            _effect(RuleEffectKind.REROLL_PERMISSION, roll_type="advance_roll"),
            _effect(RuleEffectKind.REROLL_PERMISSION, roll_type="charge_roll"),
            _effect(
                RuleEffectKind.MODIFY_CHARACTERISTIC,
                characteristic=Characteristic.TOUGHNESS.value,
                delta=-1,
            ),
            _effect(
                RuleEffectKind.MODIFY_CHARACTERISTIC,
                characteristic=Characteristic.OBJECTIVE_CONTROL.value,
                delta=-1,
            ),
            _effect(RuleEffectKind.GRANT_WEAPON_ABILITY, weapon_ability="Lethal Hits"),
            _effect(RuleEffectKind.GRANT_ABILITY, ability="can_advance_and_charge"),
            _effect(RuleEffectKind.GRANT_ABILITY, ability="Feel No Pain", threshold=3),
            _effect(RuleEffectKind.PLACEMENT_PERMISSION, placement_kind="turn_end_reserves"),
        ),
        target_kind=RuleTargetKind.ENEMY_UNIT,
    )

    assert set(catalog_rule_ir_hook_ids_for_rule(rule_ir)) >= {
        CATALOG_IR_HIT_ROLL_MODIFIER_CONSUMER_ID,
        CATALOG_IR_WOUND_ROLL_MODIFIER_CONSUMER_ID,
        CATALOG_IR_INVULNERABLE_SAVE_ROLL_MODIFIER_CONSUMER_ID,
        CATALOG_IR_CRITICAL_HIT_VALUE_MODIFIER_CONSUMER_ID,
        CATALOG_IR_ADVANCE_ROLL_REROLL_CONSUMER_ID,
        CATALOG_IR_CHARGE_ROLL_REROLL_CONSUMER_ID,
        "catalog-ir:toughness-characteristic-modifier",
        "catalog-ir:objective-control-characteristic-modifier",
        CATALOG_IR_WEAPON_KEYWORD_GRANT_CONSUMER_ID,
        "catalog-ir:weapon-keyword-grant:lethal-hits",
        CATALOG_IR_CAN_ADVANCE_AND_CHARGE_CONSUMER_ID,
        CATALOG_IR_CAN_BE_PLACED_IN_RESERVES_CONSUMER_ID,
        CATALOG_IR_FEEL_NO_PAIN_SOURCE_CONSUMER_ID,
    }
    assert registered_hook_ids >= {
        CATALOG_IR_SAVE_ROLL_MODIFIER_CONSUMER_ID,
        CATALOG_IR_FEEL_NO_PAIN_ROLL_CONSUMER_ID,
        CATALOG_IR_FEEL_NO_PAIN_SOURCE_CONSUMER_ID,
        CATALOG_IR_CRITICAL_WOUND_VALUE_MODIFIER_CONSUMER_ID,
        CATALOG_IR_CAN_FALLBACK_AND_CHARGE_CONSUMER_ID,
        CATALOG_IR_CAN_FALLBACK_AND_SHOOT_CONSUMER_ID,
        CATALOG_IR_CAN_ADVANCE_AND_SHOOT_AND_CHARGE_CONSUMER_ID,
        CATALOG_IR_ADVANCE_ROLL_REROLL_CONSUMER_ID,
        CATALOG_IR_CHARGE_ROLL_REROLL_CONSUMER_ID,
        "catalog-ir:movement-characteristic-query",
        "catalog-ir:toughness-characteristic-query",
        "catalog-ir:objective-control-characteristic-query",
        "catalog-ir:wounds-characteristic-query",
        "catalog-ir:attacks-characteristic-query",
        "catalog-ir:armor-penetration-characteristic-query",
        "catalog-ir:ballistic-skill-characteristic-query",
        "catalog-ir:weapon-skill-characteristic-query",
        "catalog-ir:strength-characteristic-query",
        "catalog-ir:damage-characteristic-query",
        "catalog-ir:range-characteristic-query",
        "catalog-ir:weapon-keyword-grant:devastating-wounds",
    }
    assert catalog_rule_ir_consumers_for_rule(rule_ir) == ()


def test_phase17k_bridge_datasheet_source_ids_include_pdf_correction_source_id() -> None:
    artifacts = _bloodcrushers_bridge_artifacts()
    datasheet_row = _row_by_id(_artifact_by_table(artifacts, "Datasheets"), "000001115")
    shadow_legion_row = next(
        row
        for artifact in _wahapedia_source_artifacts()
        if artifact.source_table == "Datasheets_keywords"
        for row in artifact.rows
        if row.runtime_fields_payload()["datasheet_id"] == "000001115"
        and row.runtime_fields_payload()["keyword"] == "Shadow Legion"
    )

    source_ids = _source_ids_from_row(datasheet_row)

    assert shadow_legion_row.stable_source_id() in source_ids
    assert "pdf:chaos-daemons-faction-pack:2026-06-10:p30-p31" in source_ids


@pytest.mark.parametrize(
    ("description", "expected", "expected_wounds_max"),
    [
        (
            (
                "While this model has 1-7 wounds remaining, subtract 4 from this model's "
                "Objective Control characteristic, and each time this model makes an attack, "
                "subtract 1 from the Hit roll."
            ),
            (
                (DamagedEffectKind.OBJECTIVE_CONTROL_MODIFIER, -4, None, (), None, None, None),
                (DamagedEffectKind.HIT_ROLL_MODIFIER, -1, None, (), None, None, None),
            ),
            7,
        ),
        (
            (
                "DAMAGED: 1\N{EN DASH}7 WOUNDS REMAINING\n"
                "While this model has 1\N{EN DASH}7 wounds remaining, "
                "add 2 to the Attacks characteristic of this "
                "model\N{RIGHT SINGLE QUOTATION MARK}s melee weapons."
            ),
            (
                (
                    DamagedEffectKind.WEAPON_ATTACKS_MODIFIER,
                    2,
                    DamagedWeaponScope.MELEE,
                    (),
                    None,
                    None,
                    None,
                ),
            ),
            7,
        ),
        (
            (
                "While this model has 1-8 wounds remaining, subtract 4 from its Objective "
                "Control characteristic and you can only select one of the C'tan Powers "
                "weapons in your Shooting phase, instead of two."
            ),
            (
                (DamagedEffectKind.OBJECTIVE_CONTROL_MODIFIER, -4, None, (), None, None, None),
                (
                    DamagedEffectKind.SHOOTING_WEAPON_SELECTION_LIMIT,
                    None,
                    None,
                    (),
                    1,
                    2,
                    "C'tan Powers weapons",
                ),
            ),
            8,
        ),
        (
            (
                "While this model has 1-6 wounds remaining, the Attacks characteristics of "
                "all of its weapons are halved, and you can only select one ability when "
                "using its Relics of the Matriarchs ability, instead of up to two."
            ),
            (
                (
                    DamagedEffectKind.WEAPON_ATTACKS_HALVE,
                    None,
                    DamagedWeaponScope.ALL,
                    (),
                    None,
                    None,
                    None,
                ),
                (
                    DamagedEffectKind.ABILITY_SELECTION_LIMIT,
                    None,
                    None,
                    (),
                    1,
                    2,
                    "Relics of the Matriarchs ability",
                ),
            ),
            6,
        ),
    ],
)
def test_phase17k_bridge_normalizes_damaged_sections_to_structured_effects(
    description: str,
    expected: tuple[
        tuple[
            DamagedEffectKind,
            int | None,
            DamagedWeaponScope | None,
            tuple[str, ...],
            int | None,
            int | None,
            str | None,
        ],
        ...,
    ],
    expected_wounds_max: int,
) -> None:
    bridge_artifacts = build_wahapedia_canonical_bridge_artifacts(
        source_artifacts=_damaged_source_artifacts(description),
        bridge_package_id=_bridge_package_id(),
        datasheet_ids=("test-damaged",),
        pdf_corrections=(),
        height_overrides=(
            ModelHeightOverride(
                datasheet_id="test-damaged",
                model_name="Damaged Beast",
                height=2.0,
                height_units=GeometrySourceUnits.INCHES,
                height_source_id="geometry-review:test-damaged:height",
                height_document_reference="Test Faction Pack p.1",
            ),
        ),
    )
    package = build_canonical_catalog_package(
        package_id=_catalog_package_id(),
        catalog_version=_catalog_version(),
        source_artifacts=bridge_artifacts,
    )
    datasheet = package.army_catalog.datasheet_by_id("test-damaged")

    assert (
        tuple(
            (
                effect.effect_kind,
                effect.modifier,
                effect.weapon_scope,
                effect.weapon_names,
                effect.max_selections,
                effect.baseline_max_selections,
                effect.selection_group,
            )
            for effect in datasheet.damaged_effects
        )
        == expected
    )
    assert {effect.wounds_min for effect in datasheet.damaged_effects} == {1}
    assert {effect.wounds_max for effect in datasheet.damaged_effects} == {expected_wounds_max}


def test_phase17k_bridge_deduplicates_same_faction_rows_for_multiple_datasheets() -> None:
    artifacts = build_wahapedia_canonical_bridge_artifacts(
        source_artifacts=_same_faction_source_artifacts(),
        bridge_package_id=_bridge_package_id(),
        datasheet_ids=("test-datasheet-a", "test-datasheet-b"),
        pdf_corrections=(),
        height_overrides=(
            ModelHeightOverride(
                datasheet_id="test-datasheet-a",
                model_name="Alpha",
                height=1.0,
                height_units=GeometrySourceUnits.INCHES,
                height_source_id="test-source:alpha-height",
                height_document_reference="test-doc:alpha-height",
            ),
            ModelHeightOverride(
                datasheet_id="test-datasheet-b",
                model_name="Beta",
                height=1.0,
                height_units=GeometrySourceUnits.INCHES,
                height_source_id="test-source:beta-height",
                height_document_reference="test-doc:beta-height",
            ),
        ),
    )
    faction_rows = _artifact_by_table(artifacts, "Factions").rows

    assert tuple(row.source_row_id for row in faction_rows) == ("test-faction",)


def test_phase17k_bridge_normalizes_core_keyword_ability_timing_and_parameters() -> None:
    artifacts = build_wahapedia_canonical_bridge_artifacts(
        source_artifacts=_keyword_ability_source_artifacts(),
        bridge_package_id=_bridge_package_id(),
        datasheet_ids=("test-keyword-unit",),
        height_overrides=(
            ModelHeightOverride(
                datasheet_id="test-keyword-unit",
                model_name="Alpha",
                height=1.0,
                height_units=GeometrySourceUnits.INCHES,
                height_source_id="test-source:keyword-height",
                height_document_reference="test-doc:keyword-height",
            ),
        ),
    )
    ability_rows = _artifact_by_table(artifacts, "Datasheets_abilities").rows
    fields_by_name = {
        row.runtime_fields_payload()["name"]: row.runtime_fields_payload()
        for row in ability_rows
        if row.runtime_fields_payload()["type"] == "Core"
    }

    assert fields_by_name["Deep Strike"]["timing_tags"] == "deployment,reserves"
    assert fields_by_name["Infiltrators"]["timing_tags"] == "deployment"
    assert fields_by_name["Leader"]["timing_tags"] == "declare_battle_formations,attachments"
    assert fields_by_name["Support"]["timing_tags"] == "declare_battle_formations,attachments"
    assert fields_by_name['Scouts 6"']["timing_tags"] == "before_battle,scouts"
    assert fields_by_name['Scouts 6"']["parameter_tokens"] == "6"
    assert fields_by_name["Firing Deck 2"]["timing_tags"] == "shooting"
    assert fields_by_name["Firing Deck 2"]["parameter_tokens"] == "2"
    assert fields_by_name["Deadly Demise D3"]["timing_tags"] == "after_destroyed,deadly_demise"
    assert fields_by_name["Deadly Demise D3"]["parameter_tokens"] == "D3"


def test_phase17k_bridge_normalizes_conditioned_wargear_weapon_keywords() -> None:
    artifacts = _conditioned_weapon_keyword_bridge_artifacts(
        "[LETHAL HITS: non-MONSTER/VEHICLE, RAPID FIRE 1, C'tan Power]"
    )
    wargear_row = _artifact_by_table(artifacts, "Datasheets_wargear").rows[0]
    wargear_fields = wargear_row.runtime_fields_payload()
    package = build_canonical_catalog_package(
        package_id=_catalog_package_id(),
        catalog_version=_catalog_version(),
        source_artifacts=artifacts,
    )
    profile = package.army_catalog.wargear[0].weapon_profiles[0]
    abilities_by_kind = {ability.ability_kind: ability for ability in profile.abilities}
    lethal = abilities_by_kind[AbilityKind.LETHAL_HITS]

    assert wargear_fields["weapon_keywords"] == "C'tan Power,Lethal Hits,Rapid Fire"
    assert wargear_fields["weapon_abilities"]
    assert tuple(keyword.value for keyword in profile.keywords) == (
        WeaponKeyword.CTAN_POWER.value,
        WeaponKeyword.LETHAL_HITS.value,
        WeaponKeyword.RAPID_FIRE.value,
    )
    assert lethal.target_keywords == ("MONSTER", "VEHICLE")
    assert {parameter.name: parameter.value for parameter in lethal.parameters} == {
        "target_keyword_match_mode": TargetKeywordMatchMode.MISSING_KEYWORD.value
    }
    assert abilities_by_kind[AbilityKind.RAPID_FIRE].parameters[0].value == 1


def test_phase17k_bridge_normalizes_conditioned_valued_and_anti_weapon_keywords() -> None:
    artifacts = _conditioned_weapon_keyword_bridge_artifacts(
        "[SUSTAINED HITS 2: non-MONSTER/VEHICLE, MELTA 3: MONSTER, "
        "CLEAVE 4: INFANTRY, DEVASTATING WOUNDS: MONSTER, "
        "HUNTER: non-MONSTER/VEHICLE, ANTI-non-PSYKER 2+]"
    )
    package = build_canonical_catalog_package(
        package_id=_catalog_package_id(),
        catalog_version=_catalog_version(),
        source_artifacts=artifacts,
    )
    profile = package.army_catalog.wargear[0].weapon_profiles[0]
    abilities_by_kind = {ability.ability_kind: ability for ability in profile.abilities}
    sustained = abilities_by_kind[AbilityKind.SUSTAINED_HITS]
    melta = abilities_by_kind[AbilityKind.MELTA]
    cleave = abilities_by_kind[AbilityKind.CLEAVE]
    devastating = abilities_by_kind[AbilityKind.DEVASTATING_WOUNDS]
    hunter = abilities_by_kind[AbilityKind.HUNTER]
    anti = abilities_by_kind[AbilityKind.ANTI_KEYWORD]

    assert tuple(keyword.value for keyword in profile.keywords) == (
        WeaponKeyword.CLEAVE.value,
        WeaponKeyword.DEVASTATING_WOUNDS.value,
        WeaponKeyword.HUNTER.value,
        WeaponKeyword.MELTA.value,
        WeaponKeyword.SUSTAINED_HITS.value,
    )
    assert sustained.target_keywords == ("MONSTER", "VEHICLE")
    assert {parameter.name: parameter.value for parameter in sustained.parameters} == {
        "target_keyword_match_mode": TargetKeywordMatchMode.MISSING_KEYWORD.value,
        "value": 2,
    }
    assert melta.target_keywords == ("MONSTER",)
    assert melta.parameters[0].value == 3
    assert cleave.target_keywords == ("INFANTRY",)
    assert cleave.parameters[0].value == 4
    assert devastating.target_keywords == ("MONSTER",)
    assert hunter.target_keywords == ("MONSTER", "VEHICLE")
    assert {parameter.name: parameter.value for parameter in hunter.parameters} == {
        "target_keyword_match_mode": TargetKeywordMatchMode.MISSING_KEYWORD.value
    }
    assert {parameter.name: parameter.value for parameter in anti.parameters} == {
        "keyword": "PSYKER",
        "match_mode": AntiKeywordMatchMode.MISSING_KEYWORD.value,
        "threshold": 2,
    }


def test_phase17k_bridge_allows_duplicate_anti_weapon_keyword_descriptors() -> None:
    artifacts = _conditioned_weapon_keyword_bridge_artifacts("[ANTI-INFANTRY 2+, ANTI-VEHICLE 4+]")
    package = build_canonical_catalog_package(
        package_id=_catalog_package_id(),
        catalog_version=_catalog_version(),
        source_artifacts=artifacts,
    )
    profile = package.army_catalog.wargear[0].weapon_profiles[0]
    anti_abilities = tuple(
        ability for ability in profile.abilities if ability.ability_kind is AbilityKind.ANTI_KEYWORD
    )

    assert len(anti_abilities) == 2
    assert {
        ability.parameters[0].value
        for ability in anti_abilities
        if ability.parameters[0].name == "keyword"
    } == {"INFANTRY", "VEHICLE"}


@pytest.mark.parametrize(
    ("description", "message"),
    [
        ("[]", "weapon keyword list must not be empty"),
        ("[: MONSTER]", "weapon keyword must not be empty"),
        ("[LETHAL HITS:]", "weapon keyword condition must not be empty"),
        ("[ANTI-INFANTRY 4+: MONSTER]", "Anti weapon keywords do not support target conditions"),
        ("[EXTRA ATTACKS: MONSTER]", "Unsupported conditioned Wahapedia weapon keyword"),
        ("[RAPID FIRE]", "Valued Wahapedia weapon keyword is missing its value"),
        ("[UNKNOWN]", "Unsupported Wahapedia weapon keyword"),
        ("[LETHAL HITS, LETHAL HITS]", "must not duplicate"),
        (
            "[DEVASTATING WOUNDS: INFANTRY, DEVASTATING WOUNDS: MONSTER]",
            "duplicate non-Anti ability kinds",
        ),
        (
            "[MELTA 2: non-MONSTER/VEHICLE, MELTA 4: INFANTRY]",
            "duplicate non-Anti ability kinds",
        ),
        ("[LETHAL HITS: non-]", "Invalid Wahapedia weapon ability descriptor"),
    ],
)
def test_phase17k_bridge_rejects_invalid_conditioned_wargear_weapon_keywords(
    description: str,
    message: str,
) -> None:
    with pytest.raises(WahapediaBridgeError, match=message):
        _conditioned_weapon_keyword_bridge_artifacts(description)


def test_phase17k_bridge_tags_warlord_mustering_datasheet_abilities() -> None:
    artifacts = build_wahapedia_canonical_bridge_artifacts(
        source_artifacts=_warlord_mustering_source_artifacts(),
        bridge_package_id=_bridge_package_id(),
        datasheet_ids=("test-supreme-commander", "test-warlord-forbidden"),
        height_overrides=(
            ModelHeightOverride(
                datasheet_id="test-supreme-commander",
                model_name="Commander",
                height=1.0,
                height_units=GeometrySourceUnits.INCHES,
                height_source_id="test-source:supreme-height",
                height_document_reference="test-doc:supreme-height",
            ),
            ModelHeightOverride(
                datasheet_id="test-warlord-forbidden",
                model_name="Forbidden",
                height=1.0,
                height_units=GeometrySourceUnits.INCHES,
                height_source_id="test-source:forbidden-height",
                height_document_reference="test-doc:forbidden-height",
            ),
        ),
    )
    ability_fields_by_datasheet = {
        row.runtime_fields_payload()["datasheet_id"]: row.runtime_fields_payload()
        for row in _artifact_by_table(artifacts, "Datasheets_abilities").rows
        if row.runtime_fields_payload()["name"] in {"SUPREME COMMANDER", "ENSLAVED STAR GOD"}
    }
    supreme_fields = ability_fields_by_datasheet["test-supreme-commander"]
    forbidden_fields = ability_fields_by_datasheet["test-warlord-forbidden"]
    plain_datasheet_fields = next(
        row.runtime_fields_payload()
        for row in _artifact_by_table(artifacts, "Datasheets_abilities").rows
        if row.runtime_fields_payload()["name"] == "TACTICAL ACUMEN"
    )
    plain_rule_ir_payload = plain_datasheet_fields["rule_ir_payload"]

    assert supreme_fields["source_kind"] == "datasheet"
    assert forbidden_fields["source_kind"] == "datasheet"
    assert plain_datasheet_fields["source_kind"] == "datasheet"
    assert json.loads(supreme_fields["rule_ir_payload"]) == {
        MUSTERING_WARLORD_RULE_KEY: MUSTERING_WARLORD_REQUIRED,
    }
    assert json.loads(forbidden_fields["rule_ir_payload"]) == {
        MUSTERING_WARLORD_RULE_KEY: MUSTERING_WARLORD_FORBIDDEN,
    }
    assert not plain_rule_ir_payload or MUSTERING_WARLORD_RULE_KEY not in json.loads(
        plain_rule_ir_payload
    )
    semantic_rows = bridge_datasheet_abilities(
        source_artifacts=_warlord_mustering_source_artifacts(),
        datasheet_ids=("test-supreme-commander", "test-warlord-forbidden"),
    )
    forbidden_descriptor = next(
        row
        for row in semantic_rows
        if row.datasheet_id == "test-warlord-forbidden"
        and row.descriptor.name == "ENSLAVED STAR GOD"
    ).descriptor
    forbidden_coverage = ability_coverage_row_for_descriptor(
        catalog_id="test-warlord-semantic-bridge",
        datasheet_id="test-warlord-forbidden",
        datasheet_name="Forbidden Warlord",
        ability=forbidden_descriptor,
    )
    assert forbidden_coverage.support_stage is AbilityCoverageSupportStage.ENGINE_CONSUMED
    assert forbidden_coverage.runtime_consumer_ids == (WARLORD_RESTRICTION_MUSTERING_CONSUMER_ID,)


def test_phase17k_bridge_loads_belakor_datasheet_rule_ir_support() -> None:
    artifacts = build_wahapedia_canonical_bridge_artifacts(
        source_artifacts=_wahapedia_source_artifacts(),
        bridge_package_id=_bridge_package_id(),
        datasheet_ids=("000001148",),
        height_overrides=(
            ModelHeightOverride(
                datasheet_id="000001148",
                model_name="Be'lakor - EPIC HERO",
                height=5.0,
                height_units=GeometrySourceUnits.INCHES,
                height_source_id="test-source:belakor-height",
                height_document_reference="test-doc:belakor-height",
            ),
        ),
    )
    ability_rows_by_id = {
        row.source_row_id: row.runtime_fields_payload()
        for row in _artifact_by_table(artifacts, "Datasheets_abilities").rows
    }
    expected_consumers_by_row_id = {
        "000001148:5": {CATALOG_IR_SHADOW_OF_CHAOS_AURA_CONSUMER_ID},
        "000001148:6": {CATALOG_IR_SHADOW_FORM_CHOICE_CONSUMER_ID},
        "000001148:8": {CATALOG_IR_SHOOTING_TARGET_RANGE_RESTRICTION_CONSUMER_ID},
        "000001148:9": {
            CATALOG_IR_BATTLE_SHOCK_FORCED_TEST_CONSUMER_ID,
            CATALOG_IR_BATTLE_SHOCK_FAILED_HEAL_CONSUMER_ID,
        },
        "000001148:10": {CATALOG_IR_HIT_ROLL_REROLL_CONSUMER_ID},
    }

    for row_id, expected_consumers in expected_consumers_by_row_id.items():
        fields = ability_rows_by_id[row_id]
        rule_ir = RuleIR.from_payload(cast(RuleIRPayload, json.loads(fields["rule_ir_payload"])))

        assert fields["support"] == CatalogAbilitySupport.GENERIC_RULE_IR.value
        assert json.loads(fields["rule_ir_diagnostics"]) == []
        assert expected_consumers <= set(catalog_rule_ir_consumers_for_rule(rule_ir))

    supreme_commander_fields = ability_rows_by_id["000001148:7"]
    assert supreme_commander_fields["support"] == CatalogAbilitySupport.DESCRIPTOR_ONLY.value
    assert json.loads(supreme_commander_fields["rule_ir_payload"]) == {
        MUSTERING_WARLORD_RULE_KEY: MUSTERING_WARLORD_REQUIRED,
    }


def test_phase17k_bridge_rejects_unsupported_datasheet_ability_type() -> None:
    with pytest.raises(WahapediaBridgeError, match="Unsupported datasheet ability type"):
        build_wahapedia_canonical_bridge_artifacts(
            source_artifacts=_unsupported_ability_type_source_artifacts(),
            bridge_package_id=_bridge_package_id(),
            datasheet_ids=("test-unsupported-ability-type",),
            height_overrides=(
                ModelHeightOverride(
                    datasheet_id="test-unsupported-ability-type",
                    model_name="Invalid",
                    height=1.0,
                    height_units=GeometrySourceUnits.INCHES,
                    height_source_id="test-source:invalid-height",
                    height_document_reference="test-doc:invalid-height",
                ),
            ),
        )


def test_phase17k_support_ability_marks_attachment_eligibility_role_as_support() -> None:
    bridge_artifacts = build_wahapedia_canonical_bridge_artifacts(
        source_artifacts=_support_attachment_source_artifacts(),
        bridge_package_id=_bridge_package_id(),
        datasheet_ids=("test-support-unit", "test-bodyguard-unit"),
        height_overrides=(
            ModelHeightOverride(
                datasheet_id="test-support-unit",
                model_name="Support",
                height=1.0,
                height_units=GeometrySourceUnits.INCHES,
                height_source_id="test-source:support-height",
                height_document_reference="test-doc:support-height",
            ),
            ModelHeightOverride(
                datasheet_id="test-bodyguard-unit",
                model_name="Bodyguard",
                height=1.0,
                height_units=GeometrySourceUnits.INCHES,
                height_source_id="test-source:bodyguard-height",
                height_document_reference="test-doc:bodyguard-height",
            ),
        ),
    )
    package = build_canonical_catalog_package(
        package_id=_catalog_package_id(),
        catalog_version=_catalog_version(),
        source_artifacts=bridge_artifacts,
    )
    support = package.army_catalog.datasheet_by_id("test-support-unit")

    assert support.attachment_eligibilities[0].role is AttachmentRole.SUPPORT
    assert tuple(
        target.bodyguard_datasheet_id for target in support.attachment_eligibilities[0].targets
    ) == ("test-bodyguard-unit",)
    assert len(support.attachment_eligibilities[0].targets[0].source_ids) == 1
    assert "Datasheets_leader" in support.attachment_eligibilities[0].targets[0].source_ids[0]


def test_phase17k_bridge_omits_attachment_edges_with_an_excluded_bodyguard_endpoint() -> None:
    bridge_artifacts = build_wahapedia_canonical_bridge_artifacts(
        source_artifacts=_support_attachment_source_artifacts(),
        bridge_package_id=_bridge_package_id(),
        datasheet_ids=("test-support-unit",),
        height_overrides=(
            ModelHeightOverride(
                datasheet_id="test-support-unit",
                model_name="Support",
                height=1.0,
                height_units=GeometrySourceUnits.INCHES,
                height_source_id="test-source:support-height",
                height_document_reference="test-doc:support-height",
            ),
        ),
    )
    package = build_canonical_catalog_package(
        package_id=_catalog_package_id(),
        catalog_version=_catalog_version(),
        source_artifacts=bridge_artifacts,
    )

    assert "Datasheets_leader" not in {artifact.source_table for artifact in bridge_artifacts}
    assert package.army_catalog.datasheet_by_id("test-support-unit").attachment_eligibilities == ()


def test_phase17k_bridge_preserves_raw_source_text_for_reference_catalog() -> None:
    source_reference_catalog = build_source_reference_catalog(
        package_id=_bridge_package_id(),
        catalog_version=_catalog_version(),
        target_edition="warhammer-40000-11th",
        source_artifacts=_bloodcrushers_bridge_artifacts(),
    )
    deep_strike_text = source_reference_catalog.source_text_by_id(
        f"{_bridge_package_id().stable_identity()}:Datasheets_abilities:000001115:1:description"
    )
    option_text = source_reference_catalog.source_text_by_id(
        f"{_bridge_package_id().stable_identity()}:Datasheets_options:000001115:1:description"
    )

    assert "<div" in deep_strike_text.raw_text
    assert "<div" not in deep_strike_text.sanitized_text
    assert option_text.raw_text.startswith("1 Bloodcrusher that is not equipped")
    assert (
        source_reference_catalog.to_payload()
        == type(source_reference_catalog)
        .from_payload(source_reference_catalog.to_payload())
        .to_payload()
    )


def test_phase17k_bridge_compiles_rule_ir_spans_from_sanitized_source_text() -> None:
    bridge_artifacts = build_wahapedia_canonical_bridge_artifacts(
        source_artifacts=_wahapedia_source_artifacts(),
        bridge_package_id=_bridge_package_id(),
        datasheet_ids=("000001114",),
        height_overrides=BLOODLETTERS_HEIGHT_OVERRIDES,
    )
    ability_row = _row_by_id(
        _artifact_by_table(bridge_artifacts, "Datasheets_abilities"),
        "000001114:5",
    )
    fields = ability_row.runtime_fields_payload()
    description_text = next(
        text_field
        for text_field in ability_row.text_fields
        if text_field.column_name == "description"
    )
    rule_ir = RuleIR.from_payload(cast(RuleIRPayload, json.loads(fields["rule_ir_payload"])))

    assert fields["support"] == "generic_rule_ir"
    assert "<span" in description_text.raw_text
    assert "<span" not in fields["description"]
    assert rule_ir.normalized_text == fields["description"]
    assert {
        CATALOG_IR_DESPERATE_ESCAPE_ROLL_MODIFIER_CONSUMER_ID,
        CATALOG_IR_FORCE_DESPERATE_ESCAPE_CONSUMER_ID,
    } <= set(catalog_rule_ir_hook_ids_for_rule(rule_ir))
    for clause in rule_ir.clauses:
        assert (
            rule_ir.normalized_text[clause.source_span.start : clause.source_span.end]
            == clause.source_span.text
        )


def test_phase17k_bridge_preserves_unsupported_rule_ir_diagnostics() -> None:
    bridge_artifacts = build_wahapedia_canonical_bridge_artifacts(
        source_artifacts=_unsupported_wargear_rule_source_artifacts(),
        bridge_package_id=_bridge_package_id(),
        datasheet_ids=("test-unsupported-unit",),
        height_overrides=(
            ModelHeightOverride(
                datasheet_id="test-unsupported-unit",
                model_name="Alpha",
                height=1.0,
                height_units=GeometrySourceUnits.INCHES,
                height_source_id="test-source:unsupported-height",
                height_document_reference="test-doc:unsupported-height",
            ),
        ),
    )
    ability_row = next(
        row
        for row in _artifact_by_table(bridge_artifacts, "Datasheets_abilities").rows
        if row.runtime_fields_payload()["name"] == "Scatter Icon"
    )
    fields = ability_row.runtime_fields_payload()
    diagnostics = json.loads(fields["rule_ir_diagnostics"])
    package = build_canonical_catalog_package(
        package_id=_catalog_package_id(),
        catalog_version=_catalog_version(),
        source_artifacts=bridge_artifacts,
    )
    abilities_by_name = {
        ability.name: ability
        for ability in package.army_catalog.datasheet_by_id("test-unsupported-unit").abilities
    }
    ability = abilities_by_name["Scatter Icon"]

    assert fields["support"] == "unsupported"
    assert fields["rule_ir_payload"]
    assert diagnostics[0]["reason"] == "unsupported_language"
    assert diagnostics[0]["source_span"]["text"] == (
        "Roll a scatter die and consult the legacy table."
    )
    assert ability.support is CatalogAbilitySupport.UNSUPPORTED
    assert ability.rule_ir_payload is not None
    assert ability.rule_ir_diagnostics == tuple(diagnostics)


def test_phase17k_structured_wargear_option_semantics_block_icon_and_instrument_together() -> None:
    package = build_canonical_catalog_package(
        package_id=_catalog_package_id(),
        catalog_version=_catalog_version(),
        source_artifacts=_bloodcrushers_bridge_artifacts(),
    )
    datasheet = package.army_catalog.datasheet_by_id("000001115")

    resolved = resolve_wargear_selections(
        catalog=package.army_catalog,
        datasheet=datasheet,
        requested_selections=(
            WargearSelection(
                option_id="000001115:instrument-of-chaos:option-1",
                model_profile_id="000001115:bloodcrushers",
                wargear_ids=("000001115:instrument-of-chaos",),
            ),
        ),
    )

    assert any(
        selection.option_id == "000001115:instrument-of-chaos:option-1" for selection in resolved
    )
    with pytest.raises(ListValidationError, match="structured wargear option condition"):
        resolve_wargear_selections(
            catalog=package.army_catalog,
            datasheet=datasheet,
            requested_selections=(
                WargearSelection(
                    option_id="000001115:instrument-of-chaos:option-1",
                    model_profile_id="000001115:bloodcrushers",
                    wargear_ids=("000001115:instrument-of-chaos",),
                ),
                WargearSelection(
                    option_id="000001115:daemonic-icon:option-2",
                    model_profile_id="000001115:bloodcrushers",
                    wargear_ids=("000001115:daemonic-icon",),
                ),
            ),
        )


def test_phase17k_structured_wargear_option_effects_are_count_aware() -> None:
    package = build_canonical_catalog_package(
        package_id=_catalog_package_id(),
        catalog_version=_catalog_version(),
        source_artifacts=_bloodcrushers_bridge_artifacts(),
    )
    datasheet = package.army_catalog.datasheet_by_id("000001115")
    options: list[DatasheetWargearOption] = []
    for option in datasheet.wargear_options:
        if option.option_id != "000001115:instrument-of-chaos:option-1":
            options.append(option)
            continue
        effect = option.effects[0]
        options.append(
            replace(
                option,
                effects=(
                    DatasheetWargearOptionEffect(
                        kind=effect.kind,
                        wargear_id=effect.wargear_id,
                        model_count=effect.model_count,
                        wargear_count=2,
                    ),
                ),
            )
        )
    counted_datasheet = replace(datasheet, wargear_options=tuple(options))

    with pytest.raises(ListValidationError, match="structured wargear option effect count"):
        resolve_wargear_selections(
            catalog=package.army_catalog,
            datasheet=counted_datasheet,
            requested_selections=(
                WargearSelection(
                    option_id="000001115:instrument-of-chaos:option-1",
                    model_profile_id="000001115:bloodcrushers",
                    wargear_ids=("000001115:instrument-of-chaos",),
                ),
            ),
        )


def test_phase17k_bridge_requires_accepted_height_overrides() -> None:
    with pytest.raises(WahapediaBridgeError, match="height override"):
        build_wahapedia_canonical_bridge_artifacts(
            source_artifacts=_wahapedia_source_artifacts(),
            bridge_package_id=_bridge_package_id(),
            datasheet_ids=("000001115",),
            height_overrides=(),
        )


def test_phase17k_bridge_uses_event_companion_model_qualified_base_sizes() -> None:
    artifacts = _jakhals_bridge_artifacts()
    model_rows = _artifact_by_table(artifacts, "Datasheets_models").rows
    model_fields_by_name = {
        row.runtime_fields_payload()["name"]: row.runtime_fields_payload() for row in model_rows
    }
    dishonoured_row = next(
        row for row in model_rows if row.runtime_fields_payload()["name"] == "Dishonoured"
    )

    assert set(model_fields_by_name) == {"Dishonoured", "Jakhal Pack Leader", "Jakhals"}
    assert model_fields_by_name["Jakhal Pack Leader"]["base_size"] == "28.5mm"
    assert model_fields_by_name["Jakhal Pack Leader"]["min_models"] == "1"
    assert model_fields_by_name["Jakhal Pack Leader"]["max_models"] == "1"
    assert model_fields_by_name["Jakhals"]["base_size"] == "28.5mm"
    assert model_fields_by_name["Jakhals"]["min_models"] == "8"
    assert model_fields_by_name["Jakhals"]["max_models"] == "17"
    assert model_fields_by_name["Dishonoured"]["base_size"] == "40mm"
    assert model_fields_by_name["Dishonoured"]["min_models"] == "1"
    assert model_fields_by_name["Dishonoured"]["max_models"] == "2"
    assert model_fields_by_name["Dishonoured"]["base_size_source_id"].endswith(
        ":base-size:page-93-world-eaters-jakhals-dishonoured"
    )
    assert EVENT_COMPANION_BASE_SIZE_GUIDE_SOURCE_ID in _source_ids_from_row(dishonoured_row)

    package = build_canonical_catalog_package(
        package_id=_catalog_package_id(),
        catalog_version=_catalog_version(),
        source_artifacts=artifacts,
    )
    datasheet = package.army_catalog.datasheet_by_id("test-jakhals")
    profiles_by_id = {profile.model_profile_id: profile for profile in datasheet.model_profiles}
    dishonoured = profiles_by_id["test-jakhals:dishonoured"]
    dishonoured_geometry = next(
        geometry
        for geometry in package.model_geometries
        if geometry.model_profile_id == "test-jakhals:dishonoured"
    )
    dishonoured_footprint_evidence = next(
        evidence
        for evidence in dishonoured_geometry.evidence
        if evidence.measurement_kind is GeometryMeasurementKind.FOOTPRINT
    )

    assert dishonoured.base_size.kind is BaseSizeKind.CIRCULAR
    assert math.isclose(dishonoured.base_size.diameter_mm or 0.0, 40.0)
    assert dishonoured_footprint_evidence.source_id.endswith(
        ":base-size:page-93-world-eaters-jakhals-dishonoured"
    )
    assert package.to_payload() == type(package).from_payload(package.to_payload()).to_payload()


def _bloodcrushers_package() -> CanonicalCatalogPackage:
    return build_canonical_catalog_package(
        package_id=_catalog_package_id(),
        catalog_version=_catalog_version(),
        source_artifacts=_bloodcrushers_bridge_artifacts(),
    )


def _flesh_hounds_package() -> CanonicalCatalogPackage:
    return build_canonical_catalog_package(
        package_id=_catalog_package_id(),
        catalog_version=_catalog_version(),
        source_artifacts=_flesh_hounds_bridge_artifacts(),
    )


def _advance_charge_package() -> CanonicalCatalogPackage:
    return build_canonical_catalog_package(
        package_id=_catalog_package_id(),
        catalog_version=_catalog_version(),
        source_artifacts=_advance_charge_bridge_artifacts(),
    )


def _model_reroll_package() -> CanonicalCatalogPackage:
    return build_canonical_catalog_package(
        package_id=_catalog_package_id(),
        catalog_version=_catalog_version(),
        source_artifacts=_model_reroll_bridge_artifacts(),
    )


def _split_fall_back_package() -> CanonicalCatalogPackage:
    return build_canonical_catalog_package(
        package_id=_catalog_package_id(),
        catalog_version=_catalog_version(),
        source_artifacts=_split_fall_back_bridge_artifacts(),
    )


def _split_model_reroll_package() -> CanonicalCatalogPackage:
    return build_canonical_catalog_package(
        package_id=_catalog_package_id(),
        catalog_version=_catalog_version(),
        source_artifacts=_split_model_reroll_bridge_artifacts(),
    )


def _named_weapon_choice_package() -> CanonicalCatalogPackage:
    return build_canonical_catalog_package(
        package_id=_catalog_package_id(),
        catalog_version=_catalog_version(),
        source_artifacts=_named_weapon_choice_bridge_artifacts(),
    )


def _undivided_daemon_package() -> CanonicalCatalogPackage:
    return build_canonical_catalog_package(
        package_id=_catalog_package_id(),
        catalog_version=_catalog_version(),
        source_artifacts=_undivided_daemon_bridge_artifacts(),
    )


def _post_shoot_cover_denial_package() -> CanonicalCatalogPackage:
    return build_canonical_catalog_package(
        package_id=_catalog_package_id(),
        catalog_version=_catalog_version(),
        source_artifacts=_post_shoot_cover_denial_bridge_artifacts(),
    )


def _post_shoot_selected_target_effect_package() -> CanonicalCatalogPackage:
    return build_canonical_catalog_package(
        package_id=_catalog_package_id(),
        catalog_version=_catalog_version(),
        source_artifacts=_post_shoot_selected_target_effect_bridge_artifacts(),
    )


def _bloodcrushers_unit(
    *,
    package: CanonicalCatalogPackage,
    selected_wargear_id: str,
) -> UnitInstance:
    datasheet = package.army_catalog.datasheet_by_id("000001115")
    option = _wargear_option_for_wargear(datasheet, selected_wargear_id)
    return UnitFactory(
        catalog=package.army_catalog,
        model_geometries=package.model_geometries,
    ).instantiate_unit(
        army_id="army-khorne",
        selection=UnitMusterSelection(
            unit_selection_id="bloodcrushers-1",
            datasheet_id=datasheet.datasheet_id,
            model_profile_selections=(
                ModelProfileSelection(
                    model_profile_id="000001115:bloodcrushers",
                    model_count=2,
                ),
                ModelProfileSelection(
                    model_profile_id="000001115:bloodhunter",
                    model_count=1,
                ),
            ),
            wargear_selections=(
                WargearSelection(
                    option_id=option.option_id,
                    model_profile_id=option.model_profile_id,
                    wargear_ids=(selected_wargear_id,),
                ),
            ),
        ),
        datasheet=datasheet,
    )


def _resolved_bloodthirster_model_wargear(
    package: CanonicalCatalogPackage,
    *,
    requested_selections: tuple[WargearSelection, ...],
) -> tuple[str, ...]:
    datasheet = package.army_catalog.datasheet_by_id("000002582")
    unit = UnitFactory(
        catalog=package.army_catalog,
        model_geometries=package.model_geometries,
    ).instantiate_unit(
        army_id="army-khorne",
        selection=UnitMusterSelection(
            unit_selection_id="bloodthirster-1",
            datasheet_id=datasheet.datasheet_id,
            model_profile_selections=(
                ModelProfileSelection(
                    model_profile_id="000002582:bloodthirster",
                    model_count=1,
                ),
            ),
            wargear_selections=requested_selections,
        ),
        datasheet=datasheet,
    )
    return unit.own_models[0].wargear_ids


def _resolved_great_unclean_one_model_wargear(
    package: CanonicalCatalogPackage,
    *,
    requested_selections: tuple[WargearSelection, ...],
) -> tuple[str, ...]:
    return (
        _great_unclean_one_unit(
            package=package,
            requested_selections=requested_selections,
        )
        .own_models[0]
        .wargear_ids
    )


def _great_unclean_one_unit(
    package: CanonicalCatalogPackage,
    *,
    requested_selections: tuple[WargearSelection, ...],
) -> UnitInstance:
    datasheet = package.army_catalog.datasheet_by_id("000001130")
    return UnitFactory(
        catalog=package.army_catalog,
        model_geometries=package.model_geometries,
    ).instantiate_unit(
        army_id="army-nurgle",
        selection=UnitMusterSelection(
            unit_selection_id="great-unclean-one-1",
            datasheet_id=datasheet.datasheet_id,
            model_profile_selections=(
                ModelProfileSelection(
                    model_profile_id="000001130:great-unclean-one",
                    model_count=1,
                ),
            ),
            wargear_selections=requested_selections,
        ),
        datasheet=datasheet,
    )


def _resolved_keeper_of_secrets_model_wargear(
    package: CanonicalCatalogPackage,
    *,
    requested_selections: tuple[WargearSelection, ...],
) -> tuple[str, ...]:
    return (
        _keeper_of_secrets_unit(
            package=package,
            requested_selections=requested_selections,
        )
        .own_models[0]
        .wargear_ids
    )


def _keeper_of_secrets_unit(
    package: CanonicalCatalogPackage,
    *,
    requested_selections: tuple[WargearSelection, ...],
) -> UnitInstance:
    datasheet = package.army_catalog.datasheet_by_id("000001137")
    return UnitFactory(
        catalog=package.army_catalog,
        model_geometries=package.model_geometries,
    ).instantiate_unit(
        army_id="army-slaanesh",
        selection=UnitMusterSelection(
            unit_selection_id="keeper-of-secrets-1",
            datasheet_id=datasheet.datasheet_id,
            model_profile_selections=(
                ModelProfileSelection(
                    model_profile_id="000001137:keeper-of-secrets",
                    model_count=1,
                ),
            ),
            wargear_selections=requested_selections,
        ),
        datasheet=datasheet,
    )


def _resolved_soul_grinder_model_wargear(
    package: CanonicalCatalogPackage,
    *,
    requested_wargear_selections: tuple[WargearSelection, ...],
    mustering_option_selections: tuple[MusteringOptionSelection, ...],
) -> tuple[str, ...]:
    return (
        _soul_grinder_unit(
            package,
            requested_wargear_selections=requested_wargear_selections,
            mustering_option_selections=mustering_option_selections,
        )
        .own_models[0]
        .wargear_ids
    )


def _soul_grinder_unit(
    package: CanonicalCatalogPackage,
    *,
    requested_wargear_selections: tuple[WargearSelection, ...],
    mustering_option_selections: tuple[MusteringOptionSelection, ...],
) -> UnitInstance:
    datasheet = package.army_catalog.datasheet_by_id("000001151")
    return UnitFactory(
        catalog=package.army_catalog,
        model_geometries=package.model_geometries,
    ).instantiate_unit(
        army_id="army-daemons",
        selection=UnitMusterSelection(
            unit_selection_id="soul-grinder-1",
            datasheet_id=datasheet.datasheet_id,
            model_profile_selections=(
                ModelProfileSelection(
                    model_profile_id="000001151:soul-grinder",
                    model_count=1,
                ),
            ),
            wargear_selections=requested_wargear_selections,
            mustering_option_selections=mustering_option_selections,
        ),
        datasheet=datasheet,
    )


def _daemon_prince_unit(
    *,
    package: CanonicalCatalogPackage,
    datasheet_id: str,
    allegiance: str,
    unit_selection_id: str,
    army_id: str = "army-daemons",
) -> UnitInstance:
    datasheet = package.army_catalog.datasheet_by_id(datasheet_id)
    profile_suffix = (
        "daemon-prince-of-chaos"
        if datasheet_id == "000001149"
        else "daemon-prince-of-chaos-with-wings"
    )
    return UnitFactory(
        catalog=package.army_catalog,
        model_geometries=package.model_geometries,
    ).instantiate_unit(
        army_id=army_id,
        selection=UnitMusterSelection(
            unit_selection_id=unit_selection_id,
            datasheet_id=datasheet_id,
            model_profile_selections=(
                ModelProfileSelection(
                    model_profile_id=f"{datasheet_id}:{profile_suffix}",
                    model_count=1,
                ),
            ),
            mustering_option_selections=(
                MusteringOptionSelection(
                    option_id=f"{datasheet_id}:daemonic-allegiance:{allegiance.lower()}"
                ),
            ),
        ),
        datasheet=datasheet,
    )


def _flesh_hounds_unit(
    *,
    package: CanonicalCatalogPackage,
    army_id: str = "army-daemons",
    unit_selection_id: str = "flesh-hounds-1",
) -> UnitInstance:
    datasheet = package.army_catalog.datasheet_by_id("test-flesh-hounds")
    selected_wargear_id = "test-flesh-hounds:collar-of-khorne"
    option = _wargear_option_for_wargear(datasheet, selected_wargear_id)
    return UnitFactory(
        catalog=package.army_catalog,
        model_geometries=package.model_geometries,
    ).instantiate_unit(
        army_id=army_id,
        selection=UnitMusterSelection(
            unit_selection_id=unit_selection_id,
            datasheet_id=datasheet.datasheet_id,
            model_profile_selections=(
                ModelProfileSelection(
                    model_profile_id="test-flesh-hounds:flesh-hounds",
                    model_count=5,
                ),
            ),
            wargear_selections=(
                WargearSelection(
                    option_id=option.option_id,
                    model_profile_id=option.model_profile_id,
                    wargear_ids=(selected_wargear_id,),
                ),
            ),
        ),
        datasheet=datasheet,
    )


def _advance_charge_unit(
    *,
    package: CanonicalCatalogPackage,
) -> UnitInstance:
    datasheet = package.army_catalog.datasheet_by_id("test-advance-charge-unit")
    return UnitFactory(
        catalog=package.army_catalog,
        model_geometries=package.model_geometries,
    ).instantiate_unit(
        army_id="army-daemons",
        selection=UnitMusterSelection(
            unit_selection_id="advance-charge-unit-1",
            datasheet_id=datasheet.datasheet_id,
            model_profile_selections=(
                ModelProfileSelection(
                    model_profile_id="test-advance-charge-unit:swift-hunter",
                    model_count=1,
                ),
            ),
        ),
        datasheet=datasheet,
    )


def _named_weapon_choice_unit(
    *,
    package: CanonicalCatalogPackage,
    army_id: str = "army-daemons",
    unit_selection_id: str = "lord-of-change-1",
    model_count: int = 1,
) -> UnitInstance:
    datasheet = package.army_catalog.datasheet_by_id("test-lord-of-change")
    return UnitFactory(
        catalog=package.army_catalog,
        model_geometries=package.model_geometries,
    ).instantiate_unit(
        army_id=army_id,
        selection=UnitMusterSelection(
            unit_selection_id=unit_selection_id,
            datasheet_id=datasheet.datasheet_id,
            model_profile_selections=(
                ModelProfileSelection(
                    model_profile_id="test-lord-of-change:lord-of-change",
                    model_count=model_count,
                ),
            ),
        ),
        datasheet=datasheet,
    )


def _wargear_option_for_wargear(
    datasheet: DatasheetDefinition,
    wargear_id: str,
) -> DatasheetWargearOption:
    for option in datasheet.wargear_options:
        if option.allowed_wargear_ids == (wargear_id,):
            return option
    raise AssertionError(f"Missing option for wargear: {wargear_id}.")


def _bloodcrushers_army(
    *,
    package: CanonicalCatalogPackage,
    unit: UnitInstance,
) -> ArmyDefinition:
    return ArmyDefinition(
        army_id="army-khorne",
        player_id="player-khorne",
        catalog_id=package.army_catalog.catalog_id,
        source_package_id=package.army_catalog.source_package_id,
        ruleset_id=package.army_catalog.ruleset_id,
        detachment_selection=DetachmentSelection(
            faction_id=package.army_catalog.factions[0].faction_id,
            detachment_ids=("phase17k-daemons",),
        ),
        units=(unit,),
    )


def _flesh_hounds_army(
    *,
    package: CanonicalCatalogPackage,
    unit: UnitInstance,
    army_id: str = "army-daemons",
    player_id: str = "player-daemons",
) -> ArmyDefinition:
    return ArmyDefinition(
        army_id=army_id,
        player_id=player_id,
        catalog_id=package.army_catalog.catalog_id,
        source_package_id=package.army_catalog.source_package_id,
        ruleset_id=package.army_catalog.ruleset_id,
        detachment_selection=DetachmentSelection(
            faction_id=package.army_catalog.factions[0].faction_id,
            detachment_ids=("phase17k-daemons",),
        ),
        units=(unit,),
    )


def _player_ability_index(
    *,
    package: CanonicalCatalogPackage,
    army: ArmyDefinition,
) -> AbilityCatalogIndex:
    return build_player_ability_index(
        catalog_ability_records_from_catalog(package.army_catalog),
        army=army,
        catalog=package.army_catalog,
    )


def _battle_state_with_army(
    *,
    army: ArmyDefinition,
    battlefield: BattlefieldRuntimeState,
) -> GameState:
    descriptor = RulesetDescriptor.warhammer_40000_eleventh()
    state = GameState(
        game_id="phase17k-game",
        ruleset_descriptor_hash=descriptor.descriptor_hash,
        stage=GameLifecycleStage.BATTLE,
        setup_sequence=tuple(descriptor.setup_sequence.steps),
        battle_phase_sequence=tuple(descriptor.battle_phase_sequence.phases),
        setup_step_index=None,
        battle_phase_index=0,
        battle_round=1,
        active_player_id=army.player_id,
        player_ids=(army.player_id, "player-opponent"),
        turn_order=(army.player_id, "player-opponent"),
        tactical_secondary_draw_count=2,
    )
    state.record_army_definition(army)
    state.battlefield_state = battlefield
    return state


def _battle_state_with_armies(
    *,
    armies: tuple[ArmyDefinition, ...],
    battlefield: BattlefieldRuntimeState,
    active_player_id: str,
    phase: BattlePhase,
) -> GameState:
    descriptor = RulesetDescriptor.warhammer_40000_eleventh()
    battle_phase_sequence = tuple(descriptor.battle_phase_sequence.phases)
    state = GameState(
        game_id="phase17k-game",
        ruleset_descriptor_hash=descriptor.descriptor_hash,
        stage=GameLifecycleStage.BATTLE,
        setup_sequence=tuple(descriptor.setup_sequence.steps),
        battle_phase_sequence=battle_phase_sequence,
        setup_step_index=None,
        battle_phase_index=battle_phase_sequence.index(phase),
        battle_round=1,
        active_player_id=active_player_id,
        player_ids=tuple(army.player_id for army in armies),
        turn_order=tuple(army.player_id for army in armies),
        tactical_secondary_draw_count=2,
    )
    for army in armies:
        state.record_army_definition(army)
    state.battlefield_state = battlefield
    return state


def _bloodcrushers_battlefield_state(
    *,
    army: ArmyDefinition,
    unit: UnitInstance,
) -> BattlefieldRuntimeState:
    placements = tuple(
        ModelPlacement(
            army_id=army.army_id,
            player_id=army.player_id,
            unit_instance_id=unit.unit_instance_id,
            model_instance_id=model.model_instance_id,
            pose=Pose.at(12.0 + (index * 2.0), 12.0),
        )
        for index, model in enumerate(unit.own_models)
    )
    return BattlefieldRuntimeState(
        battlefield_id="phase17k-battlefield",
        battlefield_width_inches=60.0,
        battlefield_depth_inches=44.0,
        placed_armies=(
            PlacedArmy(
                army_id=army.army_id,
                player_id=army.player_id,
                unit_placements=(
                    UnitPlacement(
                        army_id=army.army_id,
                        player_id=army.player_id,
                        unit_instance_id=unit.unit_instance_id,
                        model_placements=placements,
                    ),
                ),
            ),
        ),
    )


def _single_model_unit_placement(
    army: ArmyDefinition, unit: UnitInstance, *, x: float
) -> UnitPlacement:
    model = unit.own_models[0]
    return UnitPlacement(
        army_id=army.army_id,
        player_id=army.player_id,
        unit_instance_id=unit.unit_instance_id,
        model_placements=(
            ModelPlacement(
                army_id=army.army_id,
                player_id=army.player_id,
                unit_instance_id=unit.unit_instance_id,
                model_instance_id=model.model_instance_id,
                pose=Pose.at(x, 12.0),
            ),
        ),
    )


def _flesh_hounds_battlefield_state(
    *,
    army: ArmyDefinition,
    unit: UnitInstance,
    enemy_army: ArmyDefinition,
    enemy_unit: UnitInstance,
    enemy_x: float,
) -> BattlefieldRuntimeState:
    friendly_placements = tuple(
        ModelPlacement(
            army_id=army.army_id,
            player_id=army.player_id,
            unit_instance_id=unit.unit_instance_id,
            model_instance_id=model.model_instance_id,
            pose=Pose.at(12.0 + (index * 2.0), 12.0),
        )
        for index, model in enumerate(unit.own_models)
    )
    enemy_placements = tuple(
        ModelPlacement(
            army_id=enemy_army.army_id,
            player_id=enemy_army.player_id,
            unit_instance_id=enemy_unit.unit_instance_id,
            model_instance_id=model.model_instance_id,
            pose=Pose.at(enemy_x + (index * 2.0), 12.0),
        )
        for index, model in enumerate(enemy_unit.own_models)
    )
    return BattlefieldRuntimeState(
        battlefield_id="phase17k-flesh-hounds-battlefield",
        battlefield_width_inches=60.0,
        battlefield_depth_inches=44.0,
        placed_armies=(
            PlacedArmy(
                army_id=army.army_id,
                player_id=army.player_id,
                unit_placements=(
                    UnitPlacement(
                        army_id=army.army_id,
                        player_id=army.player_id,
                        unit_instance_id=unit.unit_instance_id,
                        model_placements=friendly_placements,
                    ),
                ),
            ),
            PlacedArmy(
                army_id=enemy_army.army_id,
                player_id=enemy_army.player_id,
                unit_placements=(
                    UnitPlacement(
                        army_id=enemy_army.army_id,
                        player_id=enemy_army.player_id,
                        unit_instance_id=enemy_unit.unit_instance_id,
                        model_placements=enemy_placements,
                    ),
                ),
            ),
        ),
    )


def _current_model_ids(
    *,
    battlefield: BattlefieldRuntimeState,
    unit: UnitInstance,
) -> tuple[str, ...]:
    return tuple(
        placement.model_instance_id
        for placement in battlefield.unit_placement_by_id(unit.unit_instance_id).model_placements
    )


def _record_by_runtime_clause_suffix(
    records: tuple[AbilityCatalogRecord, ...],
    *,
    suffix: str,
) -> AbilityCatalogRecord:
    matches = tuple(record for record in records if _runtime_clause_id(record).endswith(suffix))
    assert len(matches) == 1
    return matches[0]


def _runtime_clause_id(record: AbilityCatalogRecord) -> str:
    payload = record.definition.replay_payload
    assert isinstance(payload, dict)
    value = payload.get("runtime_clause_id")
    assert type(value) is str
    return value


def _set_state_battle_phase(state: GameState, phase: BattlePhase) -> None:
    state.battle_phase_index = tuple(state.battle_phase_sequence).index(phase)


def _set_current_model_wounds(
    state: GameState, *, model_instance_id: str, wounds_remaining: int
) -> None:
    armies: list[ArmyDefinition] = []
    updated = False
    for army in state.army_definitions:
        units: list[UnitInstance] = []
        for unit in army.units:
            models = tuple(
                replace(model, wounds_remaining=wounds_remaining)
                if model.model_instance_id == model_instance_id
                else model
                for model in unit.own_models
            )
            if models != unit.own_models:
                updated = True
            units.append(replace(unit, own_models=models))
        armies.append(replace(army, units=tuple(units)))
    if not updated:
        raise AssertionError(f"Missing current model: {model_instance_id}.")
    state.army_definitions = armies


def _pending_completed_attack_sequence_for_test(state: GameState) -> AttackSequence | None:
    shooting_state = state.shooting_phase_state
    assert shooting_state is not None
    return shooting_state.pending_completed_attack_sequence


def _shooting_phase_start_request_context(
    *,
    state: GameState,
    decisions: DecisionController,
    army_catalog: ArmyCatalog,
) -> ShootingPhaseStartRequestContext:
    return ShootingPhaseStartRequestContext(
        state=state,
        decisions=decisions,
        ruleset_descriptor=RulesetDescriptor.warhammer_40000_eleventh(),
        army_catalog=army_catalog,
        shooting_target_restriction_hooks=ShootingTargetRestrictionHookRegistry.empty(),
    )


def _weapon_profile_by_name(catalog: ArmyCatalog, name: str) -> WeaponProfile:
    for wargear in catalog.wargear:
        for profile in wargear.weapon_profiles:
            if profile.name == name:
                return profile
    raise AssertionError(f"Missing weapon profile: {name}.")


def _datasheet_weapon_profile(
    catalog: ArmyCatalog, *, datasheet_id: str, profile_name: str
) -> WeaponProfile:
    wargear_prefix = f"{datasheet_id}:"
    for wargear in catalog.wargear:
        if not wargear.wargear_id.startswith(wargear_prefix):
            continue
        for profile in wargear.weapon_profiles:
            if profile.name == profile_name:
                return profile
    raise AssertionError(f"Missing {datasheet_id} weapon profile: {profile_name}.")


def _model_characteristic(unit: UnitInstance, characteristic: Characteristic) -> int:
    for value in unit.own_models[0].characteristics:
        if value.characteristic is characteristic:
            return value.final
    raise AssertionError(f"Missing model characteristic: {characteristic.value}.")


def _wargear_id_for_weapon_profile(catalog: ArmyCatalog, weapon_profile_id: str) -> str:
    for wargear in catalog.wargear:
        for profile in wargear.weapon_profiles:
            if profile.profile_id == weapon_profile_id:
                return wargear.wargear_id
    raise AssertionError(f"Missing wargear for weapon profile: {weapon_profile_id}.")


def _completed_post_shoot_attack_sequence(
    *,
    package: CanonicalCatalogPackage,
    attacker: UnitInstance,
    attacker_player_id: str = "player-daemons",
    target: UnitInstance,
    attacker_model_instance_ids: tuple[str, ...] | None = None,
) -> AttackSequence:
    bolt_profile = _weapon_profile_by_name(package.army_catalog, "Bolt of Change")
    target_model_ids = tuple(model.model_instance_id for model in target.own_models)
    attacker_model_ids = (
        (attacker.own_models[0].model_instance_id,)
        if attacker_model_instance_ids is None
        else attacker_model_instance_ids
    )
    wargear_id = _wargear_id_for_weapon_profile(package.army_catalog, bolt_profile.profile_id)
    attack_pools = tuple(
        RangedAttackPool(
            attacker_model_instance_id=attacker_model_id,
            wargear_id=wargear_id,
            weapon_profile_id=bolt_profile.profile_id,
            weapon_profile=bolt_profile,
            target_unit_instance_id=target.unit_instance_id,
            shooting_type=ShootingType.NORMAL,
            attacks=1,
            target_visible_model_ids=target_model_ids,
            target_in_range_model_ids=target_model_ids,
        )
        for attacker_model_id in attacker_model_ids
    )
    return AttackSequence(
        sequence_id="phase17k-post-shoot-cover-denial-sequence",
        attacker_player_id=attacker_player_id,
        attacking_unit_instance_id=attacker.unit_instance_id,
        attack_pools=attack_pools,
        source_phase=BattlePhase.SHOOTING,
        used_pool_indices=tuple(range(len(attack_pools))),
        pool_index=len(attack_pools),
    )


def _emit_successful_hit(
    *,
    decisions: DecisionController,
    attack_sequence: AttackSequence,
    successful: bool,
    pool_index: int = 0,
) -> None:
    decisions.event_log.append(
        "attack_sequence_step",
        AttackSequenceEvent(
            step=AttackSequenceStep.HIT,
            sequence_id=attack_sequence.sequence_id,
            attack_context_id=(
                f"{attack_sequence.sequence_id}:pool-{pool_index + 1:03d}:attack-001"
            ),
            pool_index=pool_index,
            attack_index=0,
            payload={"successful": successful},
        ).to_payload(),
    )


def _emit_wound_result(
    *,
    decisions: DecisionController,
    attack_sequence: AttackSequence,
    successful: bool,
    pool_index: int = 0,
) -> None:
    decisions.event_log.append(
        "attack_sequence_step",
        AttackSequenceEvent(
            step=AttackSequenceStep.WOUND,
            sequence_id=attack_sequence.sequence_id,
            attack_context_id=(
                f"{attack_sequence.sequence_id}:pool-{pool_index + 1:03d}:attack-001"
            ),
            pool_index=pool_index,
            attack_index=0,
            payload={"successful": successful},
        ).to_payload(),
    )


def _phase17k_named_choice_effect(
    *,
    effect_id: str,
    unit: UnitInstance,
    owner_player_id: str,
    payload: JsonValue,
) -> PersistingEffect:
    return PersistingEffect(
        effect_id=effect_id,
        source_rule_id="phase17k:named-choice:test",
        owner_player_id=owner_player_id,
        target_unit_instance_ids=(unit.unit_instance_id,),
        started_battle_round=1,
        started_phase=BattlePhaseKind.SHOOTING,
        expiration=EffectExpiration.end_phase(
            battle_round=1,
            phase=BattlePhaseKind.SHOOTING,
            player_id=owner_player_id,
        ),
        effect_payload=payload,
    )


def _model_bearing_wargear(
    unit: UnitInstance,
    wargear_id: str,
) -> ModelInstance:
    for model in unit.own_models:
        if wargear_id in model.wargear_ids:
            return model
    raise AssertionError(f"Missing bearer for wargear: {wargear_id}.")


def _catalog_rule_ir(
    effects: tuple[RuleEffectSpec, ...],
    *,
    target_kind: RuleTargetKind,
) -> RuleIR:
    span = TextSpan(text="catalog hook test", start=0, end=17)
    return RuleIR(
        rule_id="test-catalog-hook-rule",
        source_id="test-catalog-hook-source",
        normalized_text=span.text,
        parser_version="test-catalog-hook-parser",
        clauses=(
            RuleClause(
                clause_id="test-catalog-hook-clause",
                source_span=span,
                target=RuleTargetSpec(kind=target_kind, source_span=span),
                effects=effects,
            ),
        ),
    )


def _multi_clause_named_weapon_choice_rule_ir() -> RuleIR:
    span = TextSpan(text="catalog hook test", start=0, end=17)
    return RuleIR(
        rule_id="phase17k:test:multi-named-choice",
        source_id="phase17k:test:multi-named-choice",
        normalized_text=span.text,
        parser_version="test-catalog-hook-parser",
        clauses=(
            RuleClause(
                clause_id="phase17k:test:multi-named-choice:clause:001",
                source_span=span,
                trigger=RuleTrigger(
                    kind=RuleTriggerKind.TIMING_WINDOW,
                    source_span=span,
                    parameters=parameters_from_pairs(
                        (
                            ("edge", "during"),
                            ("owner", "active_player"),
                            ("phase", "movement"),
                        )
                    ),
                ),
                target=RuleTargetSpec(kind=RuleTargetKind.THIS_UNIT, source_span=span),
                effects=(
                    _effect(
                        RuleEffectKind.GRANT_ABILITY,
                        ability="can_advance_and_charge",
                    ),
                ),
                duration=RuleDuration(
                    kind=RuleDurationKind.PERMANENT,
                    source_span=span,
                ),
            ),
            RuleClause(
                clause_id="phase17k:test:multi-named-choice:clause:002",
                source_span=span,
                trigger=RuleTrigger(
                    kind=RuleTriggerKind.TIMING_WINDOW,
                    source_span=span,
                    parameters=parameters_from_pairs(
                        (
                            ("edge", "during"),
                            ("owner", "active_player"),
                            ("phase", "shooting"),
                        )
                    ),
                ),
                target=RuleTargetSpec(kind=RuleTargetKind.THIS_MODEL, source_span=span),
                effects=(
                    _effect(
                        RuleEffectKind.GRANT_WEAPON_ABILITY,
                        selection_kind="select_one",
                        selection_group_id="multi_clause_named_weapon_choice",
                        selection_option_id="option_001_ignores_cover",
                        selection_option_index=1,
                        target_scope="this_model",
                        weapon_name="Bolt of Change",
                        weapon_ability="Ignores Cover",
                    ),
                    _effect(
                        RuleEffectKind.GRANT_WEAPON_ABILITY,
                        selection_kind="select_one",
                        selection_group_id="multi_clause_named_weapon_choice",
                        selection_option_id="option_002_lethal_hits",
                        selection_option_index=2,
                        target_scope="this_model",
                        weapon_name="Bolt of Change",
                        weapon_ability="Lethal Hits",
                    ),
                ),
                duration=RuleDuration(
                    kind=RuleDurationKind.UNTIL_TIMING_ENDPOINT,
                    source_span=span,
                    parameters=parameters_from_pairs((("endpoint", "phase"),)),
                ),
            ),
        ),
    )


def _multi_clause_named_weapon_choice_record(
    *,
    rule_ir: RuleIR,
    clause_index: int,
    datasheet_id: str,
    trigger_kind: TimingTriggerKind,
) -> AbilityCatalogRecord:
    clause = rule_ir.clauses[clause_index]
    return AbilityCatalogRecord(
        record_id=f"phase17k:test:catalog-ability:{datasheet_id}:multi-daemonspark:{clause.clause_id}",
        definition=AbilityDefinition(
            ability_id="multi-daemonspark",
            name="Multi-Clause Daemonspark",
            source_id="phase17k:test:multi-named-choice",
            when_descriptor="Catalog generic rule IR.",
            effect_descriptor="Multi-clause named weapon ability choice.",
            restrictions_descriptor="Datasheet ability source kind: datasheet.",
            timing=AbilityTimingDescriptor(trigger_kind=trigger_kind),
            handler_id=GENERIC_RULE_IR_ABILITY_HANDLER_ID,
            replay_payload=validate_json_value(
                {
                    "rule_ir": rule_ir.to_payload(),
                    "runtime_clause_id": clause.clause_id,
                }
            ),
        ),
        source_kind=AbilitySourceKind.DATASHEET,
        datasheet_id=datasheet_id,
    )


def _multi_clause_post_shoot_cover_denial_rule_ir() -> RuleIR:
    span = TextSpan(text="catalog hook test", start=0, end=17)
    return RuleIR(
        rule_id="phase17k:test:multi-post-shoot-cover-denial",
        source_id="phase17k:test:multi-post-shoot-cover-denial",
        normalized_text=span.text,
        parser_version="test-catalog-hook-parser",
        clauses=(
            RuleClause(
                clause_id="phase17k:test:multi-post-shoot-cover-denial:clause:001",
                source_span=span,
                trigger=RuleTrigger(
                    kind=RuleTriggerKind.TIMING_WINDOW,
                    source_span=span,
                    parameters=parameters_from_pairs(
                        (
                            ("edge", "during"),
                            ("owner", "active_player"),
                            ("phase", "movement"),
                        )
                    ),
                ),
                target=RuleTargetSpec(kind=RuleTargetKind.THIS_UNIT, source_span=span),
                effects=(
                    _effect(
                        RuleEffectKind.GRANT_ABILITY,
                        ability="can_advance_and_charge",
                    ),
                ),
                duration=RuleDuration(
                    kind=RuleDurationKind.PERMANENT,
                    source_span=span,
                ),
            ),
            RuleClause(
                clause_id="phase17k:test:multi-post-shoot-cover-denial:clause:002",
                source_span=span,
                trigger=RuleTrigger(
                    kind=RuleTriggerKind.TIMING_WINDOW,
                    source_span=span,
                    parameters=parameters_from_pairs(
                        (
                            ("edge", "after"),
                            ("owner", "active_player"),
                            ("phase", "shooting"),
                            ("subject", "this_model"),
                            ("timing_window", "just_after_friendly_unit_has_shot"),
                            ("target_relationship", "hit_by_those_attacks"),
                        )
                    ),
                ),
                target=RuleTargetSpec(kind=RuleTargetKind.ENEMY_UNIT, source_span=span),
                effects=(
                    _effect(
                        RuleEffectKind.SET_CONTEXTUAL_STATUS,
                        status="benefit_of_cover",
                        status_label="Benefit of Cover",
                        operation="deny",
                        target_scope="selected_unit",
                        rules_context="status_denial",
                    ),
                ),
                duration=RuleDuration(
                    kind=RuleDurationKind.UNTIL_TIMING_ENDPOINT,
                    source_span=span,
                    parameters=parameters_from_pairs((("endpoint", "phase"),)),
                ),
            ),
        ),
    )


def _multi_clause_post_shoot_cover_denial_record(
    *,
    rule_ir: RuleIR,
    clause_index: int,
    datasheet_id: str,
    trigger_kind: TimingTriggerKind,
) -> AbilityCatalogRecord:
    clause = rule_ir.clauses[clause_index]
    return AbilityCatalogRecord(
        record_id=(
            f"phase17k:test:catalog-ability:{datasheet_id}:multi-purge-and-cleanse:"
            f"{clause.clause_id}"
        ),
        definition=AbilityDefinition(
            ability_id="multi-purge-and-cleanse",
            name="Multi-Clause Purge and Cleanse",
            source_id="phase17k:test:multi-post-shoot-cover-denial",
            when_descriptor="Catalog generic rule IR.",
            effect_descriptor="Multi-clause post-shoot hit-target status denial.",
            restrictions_descriptor="Datasheet ability source kind: datasheet.",
            timing=AbilityTimingDescriptor(trigger_kind=trigger_kind),
            handler_id=GENERIC_RULE_IR_ABILITY_HANDLER_ID,
            replay_payload=validate_json_value(
                {
                    "rule_ir": rule_ir.to_payload(),
                    "runtime_clause_id": clause.clause_id,
                }
            ),
        ),
        source_kind=AbilitySourceKind.DATASHEET,
        datasheet_id=datasheet_id,
    )


def _charge_end_mortal_wounds_rule_ir() -> RuleIR:
    return compile_rule_source_text(
        RuleSourceText.from_raw(
            source_id="phase17k:test:charge-end-mortal-wounds",
            raw_text=(
                "Each time this unit ends a Charge move, select one enemy unit within "
                "Engagement Range of this unit and roll one D6 for each model in this unit: "
                "for each 4+, that enemy unit suffers D3 mortal wounds."
            ),
        ),
        source_keyword_sequence_parts=SOURCE_KEYWORD_SEQUENCE_PARTS,
    ).rule_ir


def _charge_end_mortal_wounds_record(
    *,
    rule_ir: RuleIR,
    datasheet_id: str,
) -> AbilityCatalogRecord:
    return AbilityCatalogRecord(
        record_id=f"phase17k:test:catalog-ability:{datasheet_id}:charge-end-mortal-wounds",
        definition=AbilityDefinition(
            ability_id="charge-end-mortal-wounds",
            name="Charge-End Mortal Wounds",
            source_id="phase17k:test:charge-end-mortal-wounds",
            when_descriptor="Catalog generic rule IR.",
            effect_descriptor="Charge-end selected target mortal wounds.",
            restrictions_descriptor="Datasheet ability source kind: datasheet.",
            timing=AbilityTimingDescriptor(
                trigger_kind=TimingTriggerKind.AFTER_UNIT_ENDS_CHARGE_MOVE,
                phase=BattlePhaseKind.CHARGE,
            ),
            handler_id=GENERIC_RULE_IR_ABILITY_HANDLER_ID,
            replay_payload=validate_json_value({"rule_ir": rule_ir.to_payload()}),
        ),
        source_kind=AbilitySourceKind.DATASHEET,
        datasheet_id=datasheet_id,
    )


def _effect(kind: RuleEffectKind, **parameters: RuleParameterValue) -> RuleEffectSpec:
    span = TextSpan(text="catalog hook test", start=0, end=17)
    return RuleEffectSpec(
        kind=kind,
        source_span=span,
        parameters=parameters_from_pairs(tuple(parameters.items())),
    )


def _ability_coverage_row(
    *,
    catalog_id: str = "test-catalog",
    datasheet_id: str = "test-datasheet",
    datasheet_name: str = "Test Datasheet",
    ability_id: str = "test-ability",
    ability_name: str = "Test Ability",
    source_kind: CatalogAbilitySourceKind = CatalogAbilitySourceKind.WARGEAR,
    source_wargear_id: str | None = "test-wargear",
    catalog_support: CatalogAbilitySupport = CatalogAbilitySupport.DESCRIPTOR_ONLY,
    support_stage: AbilityCoverageSupportStage = AbilityCoverageSupportStage.DESCRIPTOR_ONLY,
    semantic_categories: tuple[str, ...] = ("wargear.descriptor",),
    runtime_consumer_ids: tuple[str, ...] = (),
    diagnostic_reasons: tuple[str, ...] = (),
) -> AbilityCoverageRow:
    return AbilityCoverageRow(
        catalog_id=catalog_id,
        datasheet_id=datasheet_id,
        datasheet_name=datasheet_name,
        ability_id=ability_id,
        ability_name=ability_name,
        source_kind=source_kind,
        source_wargear_id=source_wargear_id,
        catalog_support=catalog_support,
        support_stage=support_stage,
        semantic_categories=semantic_categories,
        runtime_consumer_ids=runtime_consumer_ids,
        diagnostic_reasons=diagnostic_reasons,
    )


def _ability_datasheet_pair(
    *,
    coverage_row_id: str = "test-row",
    ability_id: str = "test-ability",
    ability_name: str = "Test Ability",
    datasheet_id: str = "test-datasheet",
    datasheet_name: str = "Test Datasheet",
    source_kind: CatalogAbilitySourceKind = CatalogAbilitySourceKind.WARGEAR,
) -> AbilityCoverageAbilityDatasheetPair:
    return AbilityCoverageAbilityDatasheetPair(
        coverage_row_id=coverage_row_id,
        ability_id=ability_id,
        ability_name=ability_name,
        datasheet_id=datasheet_id,
        datasheet_name=datasheet_name,
        source_kind=source_kind,
    )


def _ability_coverage_category_row(
    *,
    category_id: str = "wargear.roll_modifier.charge.this_unit",
    category_name: str = "Charge Roll Modifier",
    coverage_row_count: int = 1,
    coverage_row_ids: tuple[str, ...] = ("test-row",),
    ability_datasheet_pairs: tuple[AbilityCoverageAbilityDatasheetPair, ...] | None = None,
    source_kind_counts: tuple[tuple[str, int], ...] = (("wargear", 1),),
    support_stages: tuple[AbilityCoverageSupportStage, ...] = (
        AbilityCoverageSupportStage.DESCRIPTOR_ONLY,
    ),
    runtime_consumer_ids: tuple[str, ...] = (),
    ability_names: tuple[str, ...] = ("Test Ability",),
    datasheet_names: tuple[str, ...] = ("Test Datasheet",),
) -> AbilityCoverageCategoryRow:
    if ability_datasheet_pairs is None:
        ability_datasheet_pairs = (_ability_datasheet_pair(),)
    return AbilityCoverageCategoryRow(
        category_id=category_id,
        category_name=category_name,
        coverage_row_count=coverage_row_count,
        coverage_row_ids=coverage_row_ids,
        ability_datasheet_pairs=ability_datasheet_pairs,
        source_kind_counts=source_kind_counts,
        support_stages=support_stages,
        runtime_consumer_ids=runtime_consumer_ids,
        ability_names=ability_names,
        datasheet_names=datasheet_names,
    )


def _bloodcrushers_bridge_artifacts() -> tuple[WahapediaJsonArtifact, ...]:
    return build_wahapedia_canonical_bridge_artifacts(
        source_artifacts=_wahapedia_source_artifacts(),
        bridge_package_id=_bridge_package_id(),
        datasheet_ids=("000001115",),
    )


def _weirdboy_bridge_artifacts() -> tuple[WahapediaJsonArtifact, ...]:
    return build_wahapedia_canonical_bridge_artifacts(
        source_artifacts=_wahapedia_source_artifacts(),
        bridge_package_id=_bridge_package_id(),
        datasheet_ids=("000000004",),
        height_overrides=(
            ModelHeightOverride(
                datasheet_id="000000004",
                model_name="Weirdboy",
                height=1.8,
                height_units=GeometrySourceUnits.INCHES,
                height_source_id="geometry-review:orks:weirdboy:height",
                height_document_reference="Phase 17K Orks bridge regression fixture",
            ),
        ),
    )


def _bloodthirster_bridge_artifacts() -> tuple[WahapediaJsonArtifact, ...]:
    return build_wahapedia_canonical_bridge_artifacts(
        source_artifacts=_wahapedia_source_artifacts(),
        bridge_package_id=_bridge_package_id(),
        datasheet_ids=("000002582",),
        height_overrides=(
            ModelHeightOverride(
                datasheet_id="000002582",
                model_name="Bloodthirster",
                height=5.75,
                height_units=GeometrySourceUnits.INCHES,
                height_source_id="geometry-review:chaos-daemons:bloodthirster:height",
                height_document_reference="Chaos Daemons Faction Pack p.16-17",
            ),
        ),
    )


def _kairos_fateweaver_bridge_artifacts() -> tuple[WahapediaJsonArtifact, ...]:
    return build_wahapedia_canonical_bridge_artifacts(
        source_artifacts=_wahapedia_source_artifacts(),
        bridge_package_id=_bridge_package_id(),
        datasheet_ids=("000001117",),
        height_overrides=(
            ModelHeightOverride(
                datasheet_id="000001117",
                model_name="Kairos Fateweaver - EPIC HERO",
                height=7.0,
                height_units=GeometrySourceUnits.INCHES,
                height_source_id="geometry-review:chaos-daemons:kairos-fateweaver:height",
                height_document_reference=(
                    "https://www.adeptusars.com/miniatures/kairos-fateweaver"
                ),
                evidence_kind=GeometryEvidenceKind.CROWD_SOURCED_MEASUREMENT,
            ),
        ),
    )


def _great_unclean_one_bridge_artifacts() -> tuple[WahapediaJsonArtifact, ...]:
    return build_wahapedia_canonical_bridge_artifacts(
        source_artifacts=_wahapedia_source_artifacts(),
        bridge_package_id=_bridge_package_id(),
        datasheet_ids=("000001130",),
        height_overrides=(
            ModelHeightOverride(
                datasheet_id="000001130",
                model_name="Great Unclean One",
                height=5.25,
                height_units=GeometrySourceUnits.INCHES,
                height_source_id="geometry-review:chaos-daemons:great-unclean-one:height",
                height_document_reference="Chaos Daemons Faction Pack p.66-67",
            ),
        ),
    )


def _keeper_of_secrets_bridge_artifacts() -> tuple[WahapediaJsonArtifact, ...]:
    return build_wahapedia_canonical_bridge_artifacts(
        source_artifacts=_wahapedia_source_artifacts(),
        bridge_package_id=_bridge_package_id(),
        datasheet_ids=("000001137",),
        height_overrides=(
            ModelHeightOverride(
                datasheet_id="000001137",
                model_name="Keeper of Secrets",
                height=5.6,
                height_units=GeometrySourceUnits.INCHES,
                height_source_id="geometry-review:chaos-daemons:keeper-of-secrets:height",
                height_document_reference="Chaos Daemons Faction Pack p.90-91",
            ),
        ),
    )


def _keeper_of_secrets_non_single_item_choice_source_artifacts() -> tuple[
    WahapediaJsonArtifact, ...
]:
    return _source_artifacts_with_datasheet_option_description(
        datasheet_id="000001137",
        option_row_id="000001137:1",
        description=(
            "This model can be equipped with one of the following:\n"
            "- 2 Living whips\n"
            "- Ritual knife\n"
            "- Shining aegis"
        ),
    )


def _soul_grinder_bridge_artifacts() -> tuple[WahapediaJsonArtifact, ...]:
    return build_wahapedia_canonical_bridge_artifacts(
        source_artifacts=_wahapedia_source_artifacts(),
        bridge_package_id=_bridge_package_id(),
        datasheet_ids=("000001151",),
        height_overrides=(
            ModelHeightOverride(
                datasheet_id="000001151",
                model_name="Soul Grinder",
                height=6.5,
                height_units=GeometrySourceUnits.INCHES,
                height_source_id="geometry-review:chaos-daemons:soul-grinder:height",
                height_document_reference="Chaos Daemons Faction Pack p.114-115",
            ),
        ),
    )


def _daemon_prince_bridge_artifacts() -> tuple[WahapediaJsonArtifact, ...]:
    return build_wahapedia_canonical_bridge_artifacts(
        source_artifacts=_wahapedia_source_artifacts(),
        bridge_package_id=_bridge_package_id(),
        datasheet_ids=("000001149", "000002758"),
        height_overrides=(
            ModelHeightOverride(
                datasheet_id="000001149",
                model_name="Daemon Prince of Chaos",
                height=4.75,
                height_units=GeometrySourceUnits.INCHES,
                height_source_id="geometry-review:chaos-daemons:daemon-prince:height",
                height_document_reference="Chaos Daemons Faction Pack p.116-117",
            ),
            ModelHeightOverride(
                datasheet_id="000002758",
                model_name="Daemon Prince of Chaos with Wings",
                height=5.5,
                height_units=GeometrySourceUnits.INCHES,
                height_source_id=("geometry-review:chaos-daemons:daemon-prince-with-wings:height"),
                height_document_reference="Chaos Daemons Faction Pack p.118-119",
            ),
        ),
    )


def _undivided_daemon_bridge_artifacts() -> tuple[WahapediaJsonArtifact, ...]:
    return build_wahapedia_canonical_bridge_artifacts(
        source_artifacts=_wahapedia_source_artifacts(),
        bridge_package_id=_bridge_package_id(),
        datasheet_ids=("000001149", "000002758", "000001151"),
        height_overrides=(
            ModelHeightOverride(
                datasheet_id="000001149",
                model_name="Daemon Prince of Chaos",
                height=4.75,
                height_units=GeometrySourceUnits.INCHES,
                height_source_id="geometry-review:chaos-daemons:daemon-prince:height",
                height_document_reference="Chaos Daemons Faction Pack p.116-117",
            ),
            ModelHeightOverride(
                datasheet_id="000002758",
                model_name="Daemon Prince of Chaos with Wings",
                height=5.5,
                height_units=GeometrySourceUnits.INCHES,
                height_source_id=("geometry-review:chaos-daemons:daemon-prince-with-wings:height"),
                height_document_reference="Chaos Daemons Faction Pack p.118-119",
            ),
            ModelHeightOverride(
                datasheet_id="000001151",
                model_name="Soul Grinder",
                height=6.5,
                height_units=GeometrySourceUnits.INCHES,
                height_source_id="geometry-review:chaos-daemons:soul-grinder:height",
                height_document_reference="Chaos Daemons Faction Pack p.114-115",
            ),
        ),
    )


def _no_equipment_daemon_fortification_bridge_artifacts() -> tuple[WahapediaJsonArtifact, ...]:
    return build_wahapedia_canonical_bridge_artifacts(
        source_artifacts=_wahapedia_source_artifacts(),
        bridge_package_id=_bridge_package_id(),
        datasheet_ids=("000001470", "000001588"),
        height_overrides=(
            ModelHeightOverride(
                datasheet_id="000001470",
                model_name="Feculent Gnarlmaw",
                height=5.0,
                height_units=GeometrySourceUnits.INCHES,
                height_source_id="geometry-review:chaos-daemons:feculent-gnarlmaw:height",
                height_document_reference="Chaos Daemons Faction Pack p.86-87",
            ),
            ModelHeightOverride(
                datasheet_id="000001588",
                model_name="Skull Altar",
                height=6.5,
                height_units=GeometrySourceUnits.INCHES,
                height_source_id="geometry-review:chaos-daemons:skull-altar:height",
                height_document_reference=(
                    "Reddit r/ChaosDaemons40k community measurement; "
                    "Battle Foam BFS-4.5 tray storage evidence"
                ),
            ),
        ),
    )


def _jakhals_bridge_artifacts() -> tuple[WahapediaJsonArtifact, ...]:
    return build_wahapedia_canonical_bridge_artifacts(
        source_artifacts=_jakhals_source_artifacts(),
        bridge_package_id=_bridge_package_id(),
        datasheet_ids=("test-jakhals",),
        height_overrides=(
            ModelHeightOverride(
                datasheet_id="test-jakhals",
                model_name="Jakhal Pack Leader",
                height=1.25,
                height_units=GeometrySourceUnits.INCHES,
                height_source_id="geometry-review:world-eaters:jakhals:pack-leader:height",
                height_document_reference="World Eaters Faction Pack p.34",
            ),
            ModelHeightOverride(
                datasheet_id="test-jakhals",
                model_name="Dishonoured",
                height=1.5,
                height_units=GeometrySourceUnits.INCHES,
                height_source_id="geometry-review:world-eaters:jakhals:dishonoured:height",
                height_document_reference="World Eaters Faction Pack p.34",
            ),
            ModelHeightOverride(
                datasheet_id="test-jakhals",
                model_name="Jakhals",
                height=1.25,
                height_units=GeometrySourceUnits.INCHES,
                height_source_id="geometry-review:world-eaters:jakhals:jakhals:height",
                height_document_reference="World Eaters Faction Pack p.34",
            ),
        ),
    )


def _jakhals_source_artifacts() -> tuple[WahapediaJsonArtifact, ...]:
    return (
        _artifact_from_csv(
            "Abilities",
            "\n".join(
                (
                    "id,faction_id,name,description",
                    "test-world-eaters-rule,WE,Blessings of Khorne,Army rule text.",
                )
            ),
        ),
        _artifact_from_csv(
            "Datasheets",
            "\n".join(
                (
                    "id,name,faction_id",
                    "test-jakhals,Jakhals,WE",
                )
            ),
        ),
        _artifact_from_csv(
            "Datasheets_abilities",
            "\n".join(
                (
                    "datasheet_id,line,type,ability_id,name,description,parameter",
                    "test-jakhals,1,Faction,test-world-eaters-rule,,,",
                )
            ),
        ),
        _artifact_from_csv(
            "Datasheets_keywords",
            "\n".join(
                (
                    "datasheet_id,keyword,model,is_faction_keyword",
                    "test-jakhals,Chaos,,false",
                    "test-jakhals,Grenades,,false",
                    "test-jakhals,Infantry,,false",
                    "test-jakhals,Jakhals,,false",
                    "test-jakhals,Khorne,,false",
                    "test-jakhals,World Eaters,,true",
                )
            ),
        ),
        _artifact_from_csv(
            "Datasheets_models",
            "\n".join(
                (
                    "datasheet_id,line,M,T,Sv,inv_sv,W,Ld,OC,base_size",
                    "test-jakhals,1,7,4,6,-,1,7,1,28.5mm",
                )
            ),
        ),
        _artifact_from_csv(
            "Datasheets_wargear",
            "\n".join(
                (
                    "datasheet_id,line,line_in_wargear,name,type,range,A,BS_WS,S,AP,D,description",
                    "test-jakhals,1,1,Autopistol,Ranged,12,1,4,3,0,1,pistol",
                )
            ),
        ),
        _artifact_from_csv(
            "Datasheets_unit_composition",
            "\n".join(
                (
                    "datasheet_id,line,description",
                    'test-jakhals,1,"1 Jakhal Pack Leader, 1 Dishonoured and 8 Jakhals"',
                    "test-jakhals,2,or:",
                    'test-jakhals,3,"1 Jakhal Pack Leader, 2 Dishonoured and 17 Jakhals"',
                )
            ),
        ),
        _artifact_from_csv(
            "Factions",
            "\n".join(("id,name", "WE,World Eaters")),
        ),
    )


def _damaged_source_artifacts(damaged_description: str) -> tuple[WahapediaJsonArtifact, ...]:
    escaped_description = _csv_field(damaged_description)
    return (
        _artifact_from_csv(
            "Abilities",
            "\n".join(
                (
                    "id,faction_id,name,description",
                    "test-faction-rule,TST,Test Rule,Army rule text.",
                )
            ),
        ),
        _artifact_from_csv(
            "Datasheets",
            "\n".join(
                (
                    "id,name,faction_id,damaged_description",
                    f'test-damaged,Damaged Beast,TST,"{escaped_description}"',
                )
            ),
        ),
        _artifact_from_csv(
            "Datasheets_abilities",
            "\n".join(
                (
                    "datasheet_id,line,type,ability_id,name,description,parameter",
                    "test-damaged,1,Faction,test-faction-rule,,,",
                )
            ),
        ),
        _artifact_from_csv(
            "Datasheets_keywords",
            "\n".join(
                (
                    "datasheet_id,keyword,model,is_faction_keyword",
                    "test-damaged,Character,,false",
                    "test-damaged,Monster,,false",
                    "test-damaged,Test Faction,,true",
                )
            ),
        ),
        _artifact_from_csv(
            "Datasheets_models",
            "\n".join(
                (
                    "datasheet_id,line,M,T,Sv,inv_sv,W,Ld,OC,base_size",
                    "test-damaged,1,8,10,4,5,14,6,5,100mm",
                )
            ),
        ),
        _artifact_from_csv(
            "Datasheets_wargear",
            "\n".join(
                (
                    "datasheet_id,line,line_in_wargear,name,type,range,A,BS_WS,S,AP,D,description",
                    "test-damaged,1,1,Claws,Melee,melee,4,2,10,-2,3,",
                )
            ),
        ),
        _artifact_from_csv(
            "Datasheets_unit_composition",
            "\n".join(
                (
                    "datasheet_id,line,description",
                    'test-damaged,1,"1 Damaged Beast"',
                )
            ),
        ),
        _artifact_from_csv(
            "Factions",
            "\n".join(("id,name", "TST,Test Faction")),
        ),
    )


def _flesh_hounds_bridge_artifacts() -> tuple[WahapediaJsonArtifact, ...]:
    return build_wahapedia_canonical_bridge_artifacts(
        source_artifacts=_flesh_hounds_source_artifacts(),
        bridge_package_id=_bridge_package_id(),
        datasheet_ids=("test-flesh-hounds",),
        height_overrides=(
            ModelHeightOverride(
                datasheet_id="test-flesh-hounds",
                model_name="Flesh Hounds",
                height=1.6,
                height_units=GeometrySourceUnits.INCHES,
                height_source_id="geometry-review:chaos-daemons:flesh-hounds:height",
                height_document_reference="Chaos Daemons Faction Pack p.26",
            ),
        ),
    )


def _advance_charge_bridge_artifacts() -> tuple[WahapediaJsonArtifact, ...]:
    return build_wahapedia_canonical_bridge_artifacts(
        source_artifacts=_advance_charge_source_artifacts(),
        bridge_package_id=_bridge_package_id(),
        datasheet_ids=("test-advance-charge-unit",),
        height_overrides=(
            ModelHeightOverride(
                datasheet_id="test-advance-charge-unit",
                model_name="Swift Hunter",
                height=1.4,
                height_units=GeometrySourceUnits.INCHES,
                height_source_id="geometry-review:test:advance-charge:swift-hunter:height",
                height_document_reference="Test Advance Charge Datasheet",
            ),
        ),
    )


def _model_reroll_bridge_artifacts() -> tuple[WahapediaJsonArtifact, ...]:
    return build_wahapedia_canonical_bridge_artifacts(
        source_artifacts=_model_reroll_source_artifacts(),
        bridge_package_id=_bridge_package_id(),
        datasheet_ids=("test-advance-charge-unit",),
        height_overrides=(
            ModelHeightOverride(
                datasheet_id="test-advance-charge-unit",
                model_name="Swift Hunter",
                height=1.4,
                height_units=GeometrySourceUnits.INCHES,
                height_source_id="geometry-review:test:model-reroll:swift-hunter:height",
                height_document_reference="Test Model Reroll Datasheet",
            ),
        ),
    )


def _split_fall_back_bridge_artifacts() -> tuple[WahapediaJsonArtifact, ...]:
    return _single_advance_charge_ability_bridge_artifacts(
        ability_name="Split Slip Away",
        description=(
            "Models in this unit have a Leadership characteristic of 6+. "
            "This unit is eligible to shoot in a turn in which it Fell Back."
        ),
        height_source_id="geometry-review:test:split-fall-back:swift-hunter:height",
        height_document_reference="Test Split Fall Back Datasheet",
    )


def _split_model_reroll_bridge_artifacts() -> tuple[WahapediaJsonArtifact, ...]:
    return _single_advance_charge_ability_bridge_artifacts(
        ability_name="Split Swift Instincts",
        description=(
            "After a Hit roll, re-roll Hit rolls. "
            "You can re\u2011roll Advance and Charge rolls made for this model."
        ),
        height_source_id="geometry-review:test:split-model-reroll:swift-hunter:height",
        height_document_reference="Test Split Model Reroll Datasheet",
    )


def _single_advance_charge_ability_bridge_artifacts(
    *,
    ability_name: str,
    description: str,
    height_source_id: str,
    height_document_reference: str,
) -> tuple[WahapediaJsonArtifact, ...]:
    return build_wahapedia_canonical_bridge_artifacts(
        source_artifacts=_single_advance_charge_ability_source_artifacts(
            ability_name=ability_name,
            description=description,
        ),
        bridge_package_id=_bridge_package_id(),
        datasheet_ids=("test-advance-charge-unit",),
        height_overrides=(
            ModelHeightOverride(
                datasheet_id="test-advance-charge-unit",
                model_name="Swift Hunter",
                height=1.4,
                height_units=GeometrySourceUnits.INCHES,
                height_source_id=height_source_id,
                height_document_reference=height_document_reference,
            ),
        ),
    )


def _named_weapon_choice_bridge_artifacts() -> tuple[WahapediaJsonArtifact, ...]:
    return build_wahapedia_canonical_bridge_artifacts(
        source_artifacts=_named_weapon_choice_source_artifacts(),
        bridge_package_id=_bridge_package_id(),
        datasheet_ids=("test-lord-of-change",),
        height_overrides=(
            ModelHeightOverride(
                datasheet_id="test-lord-of-change",
                model_name="Lord of Change",
                height=5.5,
                height_units=GeometrySourceUnits.INCHES,
                height_source_id="geometry-review:test:lord-of-change:height",
                height_document_reference="Test Lord of Change Datasheet",
            ),
        ),
    )


def _post_shoot_cover_denial_bridge_artifacts() -> tuple[WahapediaJsonArtifact, ...]:
    return build_wahapedia_canonical_bridge_artifacts(
        source_artifacts=_post_shoot_cover_denial_source_artifacts(),
        bridge_package_id=_bridge_package_id(),
        datasheet_ids=("test-lord-of-change",),
        height_overrides=(
            ModelHeightOverride(
                datasheet_id="test-lord-of-change",
                model_name="Lord of Change",
                height=5.5,
                height_units=GeometrySourceUnits.INCHES,
                height_source_id="geometry-review:test:lord-of-change:height",
                height_document_reference="Test Lord of Change Datasheet",
            ),
        ),
    )


def _post_shoot_selected_target_effect_bridge_artifacts() -> tuple[WahapediaJsonArtifact, ...]:
    return build_wahapedia_canonical_bridge_artifacts(
        source_artifacts=_post_shoot_selected_target_effect_source_artifacts(),
        bridge_package_id=_bridge_package_id(),
        datasheet_ids=("test-lord-of-change",),
        height_overrides=(
            ModelHeightOverride(
                datasheet_id="test-lord-of-change",
                model_name="Lord of Change",
                height=5.5,
                height_units=GeometrySourceUnits.INCHES,
                height_source_id="geometry-review:test:lord-of-change:height",
                height_document_reference="Test Lord of Change Datasheet",
            ),
        ),
    )


def _advance_charge_source_artifacts() -> tuple[WahapediaJsonArtifact, ...]:
    return (
        _artifact_from_csv(
            "Abilities",
            "\n".join(
                (
                    "id,faction_id,name,description",
                    "test-army-rule,test-faction,Test Army Rule,Test rule text.",
                )
            ),
        ),
        _artifact_from_csv(
            "Datasheets",
            "\n".join(
                (
                    "id,name,faction_id",
                    "test-advance-charge-unit,Advance Charge Unit,test-faction",
                )
            ),
        ),
        _artifact_from_csv(
            "Datasheets_abilities",
            "\n".join(
                (
                    "datasheet_id,line,type,ability_id,name,description,parameter",
                    (
                        "test-advance-charge-unit,1,Faction,test-army-rule,"
                        "Test Army Rule,Test rule text.,"
                    ),
                    (
                        "test-advance-charge-unit,2,Datasheet,,Bounding Advance,"
                        "This unit is eligible to declare a charge in a turn in  which "
                        "it Advanced.,"
                    ),
                    (
                        "test-advance-charge-unit,3,Datasheet,,Lead the Hunt,"
                        '"While this model is leading a unit, you can re-roll  Advance '
                        'and Charge rolls made for that unit.",'
                    ),
                    (
                        "test-advance-charge-unit,4,Datasheet,,Pack Killers,"
                        '"While this model is leading a unit, melee weapons equipped by '
                        'models in that unit have the  [LETHAL HITS] ability.",'
                    ),
                    (
                        "test-advance-charge-unit,5,Datasheet,,Slip Away,"
                        "This unit is eligible to shoot in a turn in  which it Fell Back.,"
                    ),
                )
            ),
        ),
        _artifact_from_csv(
            "Datasheets_keywords",
            "\n".join(
                (
                    "datasheet_id,keyword,model,is_faction_keyword",
                    "test-advance-charge-unit,Beasts,,false",
                    "test-advance-charge-unit,Test Faction,,true",
                )
            ),
        ),
        _artifact_from_csv(
            "Datasheets_models",
            "\n".join(
                (
                    "datasheet_id,line,M,T,Sv,inv_sv,W,Ld,OC,base_size",
                    "test-advance-charge-unit,1,10,4,6,5,2,7,1,40mm",
                )
            ),
        ),
        _artifact_from_csv(
            "Datasheets_wargear",
            "\n".join(
                (
                    "datasheet_id,line,line_in_wargear,name,type,range,A,BS_WS,S,AP,D,description",
                    "test-advance-charge-unit,1,1,Swift claws,Melee,Melee,4,4,4,0,1,",
                )
            ),
        ),
        _artifact_from_csv(
            "Datasheets_unit_composition",
            "\n".join(
                (
                    "datasheet_id,line,description",
                    "test-advance-charge-unit,1,1 Swift Hunter",
                )
            ),
        ),
        _artifact_from_csv(
            "Factions",
            "\n".join(("id,name", "test-faction,Test Faction")),
        ),
    )


def _model_reroll_source_artifacts() -> tuple[WahapediaJsonArtifact, ...]:
    return _single_advance_charge_ability_source_artifacts(
        ability_name="Swift Instincts",
        description="You can re\u2011roll Advance and Charge rolls made for this model.",
    )


def _single_advance_charge_ability_source_artifacts(
    *,
    ability_name: str,
    description: str,
) -> tuple[WahapediaJsonArtifact, ...]:
    return (
        _artifact_from_csv(
            "Abilities",
            "\n".join(
                (
                    "id,faction_id,name,description",
                    "test-army-rule,test-faction,Test Army Rule,Test rule text.",
                )
            ),
        ),
        _artifact_from_csv(
            "Datasheets",
            "\n".join(
                (
                    "id,name,faction_id",
                    "test-advance-charge-unit,Advance Charge Unit,test-faction",
                )
            ),
        ),
        _artifact_from_csv(
            "Datasheets_abilities",
            "\n".join(
                (
                    "datasheet_id,line,type,ability_id,name,description,parameter",
                    (
                        "test-advance-charge-unit,1,Faction,test-army-rule,"
                        "Test Army Rule,Test rule text.,"
                    ),
                    (
                        "test-advance-charge-unit,2,Datasheet,,"
                        f'{_csv_field(ability_name)},"{_csv_field(description)}",'
                    ),
                )
            ),
        ),
        _artifact_from_csv(
            "Datasheets_keywords",
            "\n".join(
                (
                    "datasheet_id,keyword,model,is_faction_keyword",
                    "test-advance-charge-unit,Beasts,,false",
                    "test-advance-charge-unit,Test Faction,,true",
                )
            ),
        ),
        _artifact_from_csv(
            "Datasheets_models",
            "\n".join(
                (
                    "datasheet_id,line,M,T,Sv,inv_sv,W,Ld,OC,base_size",
                    "test-advance-charge-unit,1,10,4,6,5,2,7,1,40mm",
                )
            ),
        ),
        _artifact_from_csv(
            "Datasheets_wargear",
            "\n".join(
                (
                    "datasheet_id,line,line_in_wargear,name,type,range,A,BS_WS,S,AP,D,description",
                    "test-advance-charge-unit,1,1,Swift claws,Melee,Melee,4,4,4,0,1,",
                )
            ),
        ),
        _artifact_from_csv(
            "Datasheets_unit_composition",
            "\n".join(
                (
                    "datasheet_id,line,description",
                    "test-advance-charge-unit,1,1 Swift Hunter",
                )
            ),
        ),
        _artifact_from_csv(
            "Factions",
            "\n".join(("id,name", "test-faction,Test Faction")),
        ),
    )


def _named_weapon_choice_source_artifacts() -> tuple[WahapediaJsonArtifact, ...]:
    return (
        _artifact_from_csv(
            "Abilities",
            "\n".join(
                (
                    "id,faction_id,name,description",
                    "test-daemons-rule,test-faction,Test Daemons Rule,Test rule text.",
                )
            ),
        ),
        _artifact_from_csv(
            "Datasheets",
            "\n".join(
                (
                    "id,name,faction_id",
                    "test-lord-of-change,Lord of Change,test-faction",
                )
            ),
        ),
        _artifact_from_csv(
            "Datasheets_abilities",
            "\n".join(
                (
                    "datasheet_id,line,type,ability_id,name,description,parameter",
                    (
                        "test-lord-of-change,1,Faction,test-daemons-rule,"
                        "Test Daemons Rule,Test rule text.,"
                    ),
                    (
                        "test-lord-of-change,2,Datasheet,,Daemonspark,"
                        '"In your Shooting phase, select one of the following abilities: '
                        "[IGNORES COVER]; [LETHAL HITS]; [SUSTAINED HITS D3]. "
                        "Until the end of the phase, this model's Bolt of Change has "
                        'that ability.",'
                    ),
                )
            ),
        ),
        _artifact_from_csv(
            "Datasheets_keywords",
            "\n".join(
                (
                    "datasheet_id,keyword,model,is_faction_keyword",
                    "test-lord-of-change,Character,,false",
                    "test-lord-of-change,Monster,,false",
                    "test-lord-of-change,Psyker,,false",
                    "test-lord-of-change,Test Faction,,true",
                )
            ),
        ),
        _artifact_from_csv(
            "Datasheets_models",
            "\n".join(
                (
                    "datasheet_id,line,M,T,Sv,inv_sv,W,Ld,OC,base_size",
                    "test-lord-of-change,1,12,10,6,5,20,6,5,100mm",
                )
            ),
        ),
        _artifact_from_csv(
            "Datasheets_wargear",
            "\n".join(
                (
                    "datasheet_id,line,line_in_wargear,name,type,range,A,BS_WS,S,AP,D,description",
                    "test-lord-of-change,1,1,Bolt of Change,Ranged,18,9,2,9,-2,3,",
                )
            ),
        ),
        _artifact_from_csv(
            "Datasheets_unit_composition",
            "\n".join(
                (
                    "datasheet_id,line,description",
                    "test-lord-of-change,1,1 Lord of Change",
                )
            ),
        ),
        _artifact_from_csv(
            "Factions",
            "\n".join(("id,name", "test-faction,Test Faction")),
        ),
    )


def _post_shoot_cover_denial_source_artifacts() -> tuple[WahapediaJsonArtifact, ...]:
    return (
        _artifact_from_csv(
            "Abilities",
            "\n".join(
                (
                    "id,faction_id,name,description",
                    "test-daemons-rule,test-faction,Test Daemons Rule,Test rule text.",
                )
            ),
        ),
        _artifact_from_csv(
            "Datasheets",
            "\n".join(
                (
                    "id,name,faction_id",
                    "test-lord-of-change,Lord of Change,test-faction",
                )
            ),
        ),
        _artifact_from_csv(
            "Datasheets_abilities",
            "\n".join(
                (
                    "datasheet_id,line,type,ability_id,name,description,parameter",
                    (
                        "test-lord-of-change,1,Faction,test-daemons-rule,"
                        "Test Daemons Rule,Test rule text.,"
                    ),
                    (
                        "test-lord-of-change,2,Datasheet,,Purge and Cleanse,"
                        '"In your Shooting phase, after this model has shot, select one '
                        "enemy unit hit by one or more of those attacks. Until the end "
                        'of the phase, that unit cannot have the Benefit of Cover.",'
                    ),
                )
            ),
        ),
        _artifact_from_csv(
            "Datasheets_keywords",
            "\n".join(
                (
                    "datasheet_id,keyword,model,is_faction_keyword",
                    "test-lord-of-change,Character,,false",
                    "test-lord-of-change,Monster,,false",
                    "test-lord-of-change,Psyker,,false",
                    "test-lord-of-change,Test Faction,,true",
                )
            ),
        ),
        _artifact_from_csv(
            "Datasheets_models",
            "\n".join(
                (
                    "datasheet_id,line,M,T,Sv,inv_sv,W,Ld,OC,base_size",
                    "test-lord-of-change,1,12,10,6,5,20,6,5,100mm",
                )
            ),
        ),
        _artifact_from_csv(
            "Datasheets_wargear",
            "\n".join(
                (
                    "datasheet_id,line,line_in_wargear,name,type,range,A,BS_WS,S,AP,D,description",
                    "test-lord-of-change,1,1,Bolt of Change,Ranged,18,9,2,9,-2,3,",
                )
            ),
        ),
        _artifact_from_csv(
            "Datasheets_unit_composition",
            "\n".join(
                (
                    "datasheet_id,line,description",
                    "test-lord-of-change,1,1-2 Lord of Change",
                )
            ),
        ),
        _artifact_from_csv(
            "Factions",
            "\n".join(("id,name", "test-faction,Test Faction")),
        ),
    )


def _post_shoot_selected_target_effect_source_artifacts() -> tuple[WahapediaJsonArtifact, ...]:
    return (
        _artifact_from_csv(
            "Abilities",
            "\n".join(
                (
                    "id,faction_id,name,description",
                    "test-daemons-rule,test-faction,Test Daemons Rule,Test rule text.",
                )
            ),
        ),
        _artifact_from_csv(
            "Datasheets",
            "\n".join(
                (
                    "id,name,faction_id",
                    "test-lord-of-change,Lord of Change,test-faction",
                )
            ),
        ),
        _artifact_from_csv(
            "Datasheets_abilities",
            "\n".join(
                (
                    "datasheet_id,line,type,ability_id,name,description,parameter",
                    (
                        "test-lord-of-change,1,Faction,test-daemons-rule,"
                        "Test Daemons Rule,Test rule text.,"
                    ),
                    (
                        "test-lord-of-change,2,Datasheet,,Warpflame Locus,"
                        '"In your Shooting phase, after this unit has shot, select one '
                        "enemy unit hit by one or more of those attacks. Until the end "
                        "of the phase, each time this model makes an attack that targets "
                        'that unit, add 1 to the Damage characteristic of that attack.",'
                    ),
                )
            ),
        ),
        _artifact_from_csv(
            "Datasheets_keywords",
            "\n".join(
                (
                    "datasheet_id,keyword,model,is_faction_keyword",
                    "test-lord-of-change,Character,,false",
                    "test-lord-of-change,Monster,,false",
                    "test-lord-of-change,Psyker,,false",
                    "test-lord-of-change,Test Faction,,true",
                )
            ),
        ),
        _artifact_from_csv(
            "Datasheets_models",
            "\n".join(
                (
                    "datasheet_id,line,M,T,Sv,inv_sv,W,Ld,OC,base_size",
                    "test-lord-of-change,1,12,10,6,5,20,6,5,100mm",
                )
            ),
        ),
        _artifact_from_csv(
            "Datasheets_wargear",
            "\n".join(
                (
                    "datasheet_id,line,line_in_wargear,name,type,range,A,BS_WS,S,AP,D,description",
                    "test-lord-of-change,1,1,Bolt of Change,Ranged,18,9,2,9,-2,3,",
                )
            ),
        ),
        _artifact_from_csv(
            "Datasheets_unit_composition",
            "\n".join(
                (
                    "datasheet_id,line,description",
                    "test-lord-of-change,1,1-2 Lord of Change",
                )
            ),
        ),
        _artifact_from_csv(
            "Factions",
            "\n".join(("id,name", "test-faction,Test Faction")),
        ),
    )


def _flesh_hounds_source_artifacts() -> tuple[WahapediaJsonArtifact, ...]:
    return (
        _artifact_from_csv(
            "Abilities",
            "\n".join(
                (
                    "id,faction_id,name,description",
                    "test-shadow,test-faction,The Shadow of Chaos,Army rule text.",
                )
            ),
        ),
        _artifact_from_csv(
            "Datasheets",
            "\n".join(
                (
                    "id,name,faction_id",
                    "test-flesh-hounds,Flesh Hounds,test-faction",
                )
            ),
        ),
        _artifact_from_csv(
            "Datasheets_abilities",
            "\n".join(
                (
                    "datasheet_id,line,type,ability_id,name,description,parameter",
                    "test-flesh-hounds,1,Faction,test-shadow,,,",
                    (
                        "test-flesh-hounds,2,Wargear,,Spare Charm,"
                        "Add 1 to Charge rolls made for the bearer's unit.,"
                    ),
                    (
                        "test-flesh-hounds,3,Wargear,,Collar of Khorne,"
                        "The bearer has the Feel No Pain 3+ ability against Psychic Attacks "
                        "and mortal wounds.,"
                    ),
                    (
                        "test-flesh-hounds,4,Datasheet,,Hunters from the Warp,"
                        "\"At the end of your opponent's turn, if this unit is not within "
                        "Engagement Range of one or more enemy units, you can remove it "
                        'from the battlefield and place it into Strategic Reserves.",'
                    ),
                )
            ),
        ),
        _artifact_from_csv(
            "Datasheets_keywords",
            "\n".join(
                (
                    "datasheet_id,keyword,model,is_faction_keyword",
                    "test-flesh-hounds,Beasts,,false",
                    "test-flesh-hounds,Chaos,,false",
                    "test-flesh-hounds,Daemon,,false",
                    "test-flesh-hounds,Khorne,,false",
                    "test-flesh-hounds,Legiones Daemonica,,true",
                )
            ),
        ),
        _artifact_from_csv(
            "Datasheets_models",
            "\n".join(
                (
                    "datasheet_id,line,M,T,Sv,inv_sv,W,Ld,OC,base_size",
                    "test-flesh-hounds,1,12,4,6,5,2,7,1,60mm",
                )
            ),
        ),
        _artifact_from_csv(
            "Datasheets_options",
            "\n".join(
                (
                    "datasheet_id,line,description",
                    (
                        "test-flesh-hounds,1,1 Flesh Hound that is not equipped with a "
                        "Spare Charm can be equipped with 1 Collar of Khorne."
                    ),
                )
            ),
        ),
        _artifact_from_csv(
            "Datasheets_unit_composition",
            "\n".join(("datasheet_id,line,description", "test-flesh-hounds,1,5 Flesh Hounds")),
        ),
        _artifact_from_csv(
            "Factions",
            "\n".join(("id,name", "test-faction,Test Faction")),
        ),
    )


def _same_faction_source_artifacts() -> tuple[WahapediaJsonArtifact, ...]:
    return (
        _artifact_from_csv(
            "Abilities",
            "\n".join(
                (
                    "id,faction_id,name,description",
                    "test-army-rule,test-faction,Test Army Rule,Test rule text.",
                )
            ),
        ),
        _artifact_from_csv(
            "Datasheets",
            "\n".join(
                (
                    "id,name,faction_id",
                    "test-datasheet-a,Alpha Unit,test-faction",
                    "test-datasheet-b,Beta Unit,test-faction",
                )
            ),
        ),
        _artifact_from_csv(
            "Datasheets_abilities",
            "\n".join(
                (
                    "datasheet_id,line,type,ability_id,name,description,parameter",
                    "test-datasheet-a,1,Faction,test-army-rule,Test Army Rule,Test rule text.,",
                    "test-datasheet-b,1,Faction,test-army-rule,Test Army Rule,Test rule text.,",
                )
            ),
        ),
        _artifact_from_csv(
            "Datasheets_keywords",
            "\n".join(
                (
                    "datasheet_id,keyword,model,is_faction_keyword",
                    "test-datasheet-a,Alpha,,false",
                    "test-datasheet-a,Test Faction,,true",
                    "test-datasheet-b,Beta,,false",
                    "test-datasheet-b,Test Faction,,true",
                )
            ),
        ),
        _artifact_from_csv(
            "Datasheets_models",
            "\n".join(
                (
                    "datasheet_id,line,M,T,Sv,inv_sv,W,Ld,OC,base_size",
                    "test-datasheet-a,1,6,4,3,-,2,7,1,32mm",
                    "test-datasheet-b,1,6,4,3,-,2,7,1,32mm",
                )
            ),
        ),
        _artifact_from_csv(
            "Datasheets_unit_composition",
            "\n".join(
                (
                    "datasheet_id,line,description",
                    "test-datasheet-a,1,1 Alpha",
                    "test-datasheet-b,1,1 Beta",
                )
            ),
        ),
        _artifact_from_csv(
            "Factions",
            "\n".join(("id,name", "test-faction,Test Faction")),
        ),
    )


def _keyword_ability_source_artifacts() -> tuple[WahapediaJsonArtifact, ...]:
    return (
        _artifact_from_csv(
            "Abilities",
            "\n".join(
                (
                    "id,faction_id,name,description",
                    "test-army-rule,test-faction,Test Army Rule,Test rule text.",
                    "core-deep-strike,,Deep Strike,Deep Strike text.",
                    "core-infiltrators,,Infiltrators,Infiltrators text.",
                    "core-leader,,Leader,Leader text.",
                    "core-support,,Support,Support text.",
                    'core-scouts,,"Scouts 6""",Scouts text.',
                    "core-firing-deck,,Firing Deck 2,Firing Deck text.",
                    "core-deadly-demise,,Deadly Demise D3,Deadly Demise text.",
                )
            ),
        ),
        _artifact_from_csv(
            "Datasheets",
            "\n".join(("id,name,faction_id", "test-keyword-unit,Keyword Unit,test-faction")),
        ),
        _artifact_from_csv(
            "Datasheets_abilities",
            "\n".join(
                (
                    "datasheet_id,line,type,ability_id,name,description,parameter",
                    "test-keyword-unit,1,Faction,test-army-rule,Test Army Rule,Test rule text.,",
                    "test-keyword-unit,2,Core,core-deep-strike,,,",
                    "test-keyword-unit,3,Core,core-infiltrators,,,",
                    "test-keyword-unit,4,Core,core-leader,,,",
                    "test-keyword-unit,5,Core,core-support,,,",
                    "test-keyword-unit,6,Core,core-scouts,,,",
                    "test-keyword-unit,7,Core,core-firing-deck,,,",
                    "test-keyword-unit,8,Core,core-deadly-demise,,,",
                )
            ),
        ),
        _artifact_from_csv(
            "Datasheets_keywords",
            "\n".join(
                (
                    "datasheet_id,keyword,model,is_faction_keyword",
                    "test-keyword-unit,Infantry,,false",
                    "test-keyword-unit,Test Faction,,true",
                )
            ),
        ),
        _artifact_from_csv(
            "Datasheets_models",
            "\n".join(
                (
                    "datasheet_id,line,M,T,Sv,inv_sv,W,Ld,OC,base_size",
                    "test-keyword-unit,1,6,4,3,-,2,7,1,32mm",
                )
            ),
        ),
        _artifact_from_csv(
            "Datasheets_unit_composition",
            "\n".join(("datasheet_id,line,description", "test-keyword-unit,1,1 Alpha")),
        ),
        _artifact_from_csv(
            "Factions",
            "\n".join(("id,name", "test-faction,Test Faction")),
        ),
    )


def _conditioned_weapon_keyword_bridge_artifacts(
    description: str,
) -> tuple[WahapediaJsonArtifact, ...]:
    return build_wahapedia_canonical_bridge_artifacts(
        source_artifacts=_conditioned_weapon_keyword_source_artifacts(description),
        bridge_package_id=_bridge_package_id(),
        datasheet_ids=("test-condition-keyword-unit",),
        height_overrides=(
            ModelHeightOverride(
                datasheet_id="test-condition-keyword-unit",
                model_name="Alpha",
                height=1.0,
                height_units=GeometrySourceUnits.INCHES,
                height_source_id="test-source:condition-keyword-height",
                height_document_reference="test-doc:condition-keyword-height",
            ),
        ),
    )


def _conditioned_weapon_keyword_source_artifacts(
    description: str,
) -> tuple[WahapediaJsonArtifact, ...]:
    return (
        _artifact_from_csv(
            "Abilities",
            "\n".join(
                (
                    "id,faction_id,name,description",
                    "test-army-rule,test-faction,Test Army Rule,Test rule text.",
                )
            ),
        ),
        _artifact_from_csv(
            "Datasheets",
            "\n".join(
                (
                    "id,name,faction_id",
                    "test-condition-keyword-unit,Condition Keyword Unit,test-faction",
                )
            ),
        ),
        _artifact_from_csv(
            "Datasheets_abilities",
            "\n".join(
                (
                    "datasheet_id,line,type,ability_id,name,description,parameter",
                    (
                        "test-condition-keyword-unit,1,Faction,test-army-rule,"
                        "Test Army Rule,Test rule text.,"
                    ),
                )
            ),
        ),
        _artifact_from_csv(
            "Datasheets_keywords",
            "\n".join(
                (
                    "datasheet_id,keyword,model,is_faction_keyword",
                    "test-condition-keyword-unit,Infantry,,false",
                    "test-condition-keyword-unit,Test Faction,,true",
                )
            ),
        ),
        _artifact_from_csv(
            "Datasheets_wargear",
            "\n".join(
                (
                    "datasheet_id,line,line_in_wargear,name,type,range,A,BS_WS,S,AP,D,description",
                    (
                        "test-condition-keyword-unit,1,1,Aperture rifle,Ranged,24,2,3,4,-1,1,"
                        f'"{description}"'
                    ),
                )
            ),
        ),
        _artifact_from_csv(
            "Datasheets_models",
            "\n".join(
                (
                    "datasheet_id,line,M,T,Sv,inv_sv,W,Ld,OC,base_size",
                    "test-condition-keyword-unit,1,6,4,3,-,2,7,1,32mm",
                )
            ),
        ),
        _artifact_from_csv(
            "Datasheets_unit_composition",
            "\n".join(("datasheet_id,line,description", "test-condition-keyword-unit,1,1 Alpha")),
        ),
        _artifact_from_csv(
            "Factions",
            "\n".join(("id,name", "test-faction,Test Faction")),
        ),
    )


def _warlord_mustering_source_artifacts() -> tuple[WahapediaJsonArtifact, ...]:
    return (
        _artifact_from_csv(
            "Abilities",
            "\n".join(
                (
                    "id,faction_id,name,description",
                    "test-army-rule,test-faction,Test Army Rule,Test rule text.",
                )
            ),
        ),
        _artifact_from_csv(
            "Datasheets",
            "\n".join(
                (
                    "id,name,faction_id",
                    "test-supreme-commander,Supreme Commander,test-faction",
                    "test-warlord-forbidden,Forbidden Warlord,test-faction",
                )
            ),
        ),
        _artifact_from_csv(
            "Datasheets_abilities",
            "\n".join(
                (
                    "datasheet_id,line,type,ability_id,name,description,parameter",
                    (
                        "test-supreme-commander,1,Faction,test-army-rule,"
                        "Test Army Rule,Test rule text.,"
                    ),
                    (
                        "test-supreme-commander,2,Special (right column),,"
                        'SUPREME COMMANDER,"If this model is in your army, '
                        'it must be your WARLORD.",'
                    ),
                    (
                        "test-supreme-commander,3,Special (right column),,"
                        "TACTICAL ACUMEN,This model can observe tactical options.,"
                    ),
                    (
                        "test-warlord-forbidden,1,Faction,test-army-rule,"
                        "Test Army Rule,Test rule text.,"
                    ),
                    (
                        "test-warlord-forbidden,2,Fortification (left column),,"
                        "ENSLAVED STAR GOD,This model cannot be your WARLORD.,"
                    ),
                )
            ),
        ),
        _artifact_from_csv(
            "Datasheets_keywords",
            "\n".join(
                (
                    "datasheet_id,keyword,model,is_faction_keyword",
                    "test-supreme-commander,Character,,false",
                    "test-supreme-commander,Epic Hero,,false",
                    "test-supreme-commander,Test Faction,,true",
                    "test-warlord-forbidden,Character,,false",
                    "test-warlord-forbidden,Test Faction,,true",
                )
            ),
        ),
        _artifact_from_csv(
            "Datasheets_models",
            "\n".join(
                (
                    "datasheet_id,line,M,T,Sv,inv_sv,W,Ld,OC,base_size",
                    "test-supreme-commander,1,6,4,3,-,4,6,1,32mm",
                    "test-warlord-forbidden,1,6,4,3,-,4,6,1,32mm",
                )
            ),
        ),
        _artifact_from_csv(
            "Datasheets_unit_composition",
            "\n".join(
                (
                    "datasheet_id,line,description",
                    "test-supreme-commander,1,1 Commander",
                    "test-warlord-forbidden,1,1 Forbidden",
                )
            ),
        ),
        _artifact_from_csv(
            "Factions",
            "\n".join(("id,name", "test-faction,Test Faction")),
        ),
    )


def _unsupported_ability_type_source_artifacts() -> tuple[WahapediaJsonArtifact, ...]:
    return (
        _artifact_from_csv(
            "Abilities",
            "\n".join(
                (
                    "id,faction_id,name,description",
                    "test-army-rule,test-faction,Test Army Rule,Test rule text.",
                )
            ),
        ),
        _artifact_from_csv(
            "Datasheets",
            "\n".join(
                (
                    "id,name,faction_id",
                    "test-unsupported-ability-type,Unsupported Ability Type,test-faction",
                )
            ),
        ),
        _artifact_from_csv(
            "Datasheets_abilities",
            "\n".join(
                (
                    "datasheet_id,line,type,ability_id,name,description,parameter",
                    (
                        "test-unsupported-ability-type,1,Faction,test-army-rule,"
                        "Test Army Rule,Test rule text.,"
                    ),
                    ("test-unsupported-ability-type,2,Unmapped,,Bad Ability,Test rule text.,"),
                )
            ),
        ),
        _artifact_from_csv(
            "Datasheets_keywords",
            "\n".join(
                (
                    "datasheet_id,keyword,model,is_faction_keyword",
                    "test-unsupported-ability-type,Character,,false",
                    "test-unsupported-ability-type,Test Faction,,true",
                )
            ),
        ),
        _artifact_from_csv(
            "Datasheets_models",
            "\n".join(
                (
                    "datasheet_id,line,M,T,Sv,inv_sv,W,Ld,OC,base_size",
                    "test-unsupported-ability-type,1,6,4,3,-,4,6,1,32mm",
                )
            ),
        ),
        _artifact_from_csv(
            "Datasheets_unit_composition",
            "\n".join(
                (
                    "datasheet_id,line,description",
                    "test-unsupported-ability-type,1,1 Invalid",
                )
            ),
        ),
        _artifact_from_csv(
            "Factions",
            "\n".join(("id,name", "test-faction,Test Faction")),
        ),
    )


def _support_attachment_source_artifacts() -> tuple[WahapediaJsonArtifact, ...]:
    return (
        _artifact_from_csv(
            "Abilities",
            "\n".join(
                (
                    "id,faction_id,name,description",
                    "test-army-rule,test-faction,Test Army Rule,Test rule text.",
                    "core-support,,Support,Support text.",
                )
            ),
        ),
        _artifact_from_csv(
            "Datasheets",
            "\n".join(
                (
                    "id,name,faction_id",
                    "test-support-unit,Support Unit,test-faction",
                    "test-bodyguard-unit,Bodyguard Unit,test-faction",
                )
            ),
        ),
        _artifact_from_csv(
            "Datasheets_abilities",
            "\n".join(
                (
                    "datasheet_id,line,type,ability_id,name,description,parameter",
                    "test-support-unit,1,Faction,test-army-rule,Test Army Rule,Test rule text.,",
                    "test-support-unit,2,Core,core-support,,,",
                    "test-bodyguard-unit,1,Faction,test-army-rule,Test Army Rule,Test rule text.,",
                )
            ),
        ),
        _artifact_from_csv(
            "Datasheets_keywords",
            "\n".join(
                (
                    "datasheet_id,keyword,model,is_faction_keyword",
                    "test-support-unit,Character,,false",
                    "test-support-unit,Infantry,,false",
                    "test-support-unit,Test Faction,,true",
                    "test-bodyguard-unit,Infantry,,false",
                    "test-bodyguard-unit,Test Faction,,true",
                )
            ),
        ),
        _artifact_from_csv(
            "Datasheets_leader",
            "\n".join(
                (
                    "leader_id,attached_id",
                    "test-support-unit,test-bodyguard-unit",
                )
            ),
        ),
        _artifact_from_csv(
            "Datasheets_wargear",
            "\n".join(
                (
                    "datasheet_id,line,line_in_wargear,name,type,range,A,BS_WS,S,AP,D,description",
                    "test-support-unit,1,1,Support blade,Melee,Melee,1,3,4,0,1,",
                    "test-bodyguard-unit,1,1,Bodyguard blade,Melee,Melee,1,3,4,0,1,",
                )
            ),
        ),
        _artifact_from_csv(
            "Datasheets_models",
            "\n".join(
                (
                    "datasheet_id,line,M,T,Sv,inv_sv,W,Ld,OC,base_size",
                    "test-support-unit,1,6,4,3,-,2,7,1,32mm",
                    "test-bodyguard-unit,1,6,4,3,-,2,7,1,32mm",
                )
            ),
        ),
        _artifact_from_csv(
            "Datasheets_unit_composition",
            "\n".join(
                (
                    "datasheet_id,line,description",
                    "test-support-unit,1,1 Support",
                    "test-bodyguard-unit,1,1 Bodyguard",
                )
            ),
        ),
        _artifact_from_csv(
            "Factions",
            "\n".join(("id,name", "test-faction,Test Faction")),
        ),
    )


def _unsupported_wargear_rule_source_artifacts() -> tuple[WahapediaJsonArtifact, ...]:
    return (
        _artifact_from_csv(
            "Abilities",
            "\n".join(
                (
                    "id,faction_id,name,description",
                    "test-army-rule,test-faction,Test Army Rule,Test rule text.",
                )
            ),
        ),
        _artifact_from_csv(
            "Datasheets",
            "\n".join(
                (
                    "id,name,faction_id",
                    "test-unsupported-unit,Unsupported Unit,test-faction",
                )
            ),
        ),
        _artifact_from_csv(
            "Datasheets_abilities",
            "\n".join(
                (
                    "datasheet_id,line,type,ability_id,name,description,parameter",
                    (
                        "test-unsupported-unit,1,Faction,test-army-rule,"
                        "Test Army Rule,Test rule text.,"
                    ),
                    (
                        "test-unsupported-unit,2,Wargear,,Scatter Icon,"
                        "Roll a scatter die and consult the legacy table.,"
                    ),
                    (
                        "test-unsupported-unit,3,Wargear,,Hit Charm,"
                        "Add 1 to hit rolls for the bearer's unit.,"
                    ),
                    "test-unsupported-unit,4,Wargear,,Tithe Charm,Gain 1CP.,",
                    (
                        "test-unsupported-unit,5,Wargear,,Broken Instrument,"
                        "Add 1 to Charge rolls made for the bearer's unit. "
                        "Roll a scatter die and consult the legacy table.,"
                    ),
                )
            ),
        ),
        _artifact_from_csv(
            "Datasheets_keywords",
            "\n".join(
                (
                    "datasheet_id,keyword,model,is_faction_keyword",
                    "test-unsupported-unit,Infantry,,false",
                    "test-unsupported-unit,Test Faction,,true",
                )
            ),
        ),
        _artifact_from_csv(
            "Datasheets_models",
            "\n".join(
                (
                    "datasheet_id,line,M,T,Sv,inv_sv,W,Ld,OC,base_size",
                    "test-unsupported-unit,1,6,4,3,-,2,7,1,32mm",
                )
            ),
        ),
        _artifact_from_csv(
            "Datasheets_unit_composition",
            "\n".join(("datasheet_id,line,description", "test-unsupported-unit,1,1 Alpha")),
        ),
        _artifact_from_csv(
            "Factions",
            "\n".join(("id,name", "test-faction,Test Faction")),
        ),
    )


def _unowned_wargear_profile_ability_source_artifacts() -> tuple[WahapediaJsonArtifact, ...]:
    return (
        _artifact_from_csv(
            "Abilities",
            "\n".join(
                (
                    "id,faction_id,name,description",
                    "test-army-rule,test-faction,Test Army Rule,Test rule text.",
                )
            ),
        ),
        _artifact_from_csv(
            "Datasheets",
            "\n".join(
                (
                    "id,name,faction_id",
                    "test-wargear-profile-owner,Wargear Profile Owner,test-faction",
                )
            ),
        ),
        _artifact_from_csv(
            "Datasheets_abilities",
            "\n".join(
                (
                    "datasheet_id,line,type,ability_id,name,description,parameter",
                    (
                        "test-wargear-profile-owner,1,Faction,test-army-rule,"
                        "Test Army Rule,Test rule text.,"
                    ),
                    (
                        "test-wargear-profile-owner,2,Wargear profile,,Summoning Horn,"
                        "Return one destroyed model.,"
                    ),
                )
            ),
        ),
        _artifact_from_csv(
            "Datasheets_keywords",
            "\n".join(
                (
                    "datasheet_id,keyword,model,is_faction_keyword",
                    "test-wargear-profile-owner,Infantry,,false",
                    "test-wargear-profile-owner,Test Faction,,true",
                )
            ),
        ),
        _artifact_from_csv(
            "Datasheets_wargear",
            "\n".join(
                (
                    "datasheet_id,line,line_in_wargear,name,type,range,A,BS_WS,S,AP,D,description",
                    "test-wargear-profile-owner,1,1,Rotten bell,Ranged,12,1,3,4,0,1,[Lethal Hits]",
                )
            ),
        ),
        _artifact_from_csv(
            "Datasheets_models",
            "\n".join(
                (
                    "datasheet_id,line,M,T,Sv,inv_sv,W,Ld,OC,base_size",
                    "test-wargear-profile-owner,1,6,4,3,-,2,7,1,32mm",
                )
            ),
        ),
        _artifact_from_csv(
            "Datasheets_unit_composition",
            "\n".join(
                (
                    "datasheet_id,line,description",
                    "test-wargear-profile-owner,1,1 Profile Bearer",
                )
            ),
        ),
        _artifact_from_csv(
            "Factions",
            "\n".join(("id,name", "test-faction,Test Faction")),
        ),
    )


def _artifact_from_csv(table_name: str, csv_text: str) -> WahapediaJsonArtifact:
    return WahapediaJsonArtifact.from_csv_table(
        source_package_id=_bridge_package_id(),
        table=WahapediaCsvTable.from_csv_text(table_name=table_name, csv_text=f"{csv_text}\n"),
    )


def _source_artifacts_with_datasheet_option_description(
    *,
    datasheet_id: str,
    option_row_id: str,
    description: str,
) -> tuple[WahapediaJsonArtifact, ...]:
    artifacts: list[WahapediaJsonArtifact] = []
    patched = False
    for artifact in _wahapedia_source_artifacts():
        if artifact.source_table != "Datasheets_options":
            artifacts.append(artifact)
            continue
        patched_rows: list[NormalizedSourceRow] = []
        for row in artifact.rows:
            fields = row.runtime_fields_payload()
            if fields["datasheet_id"] == datasheet_id and row.source_row_id == option_row_id:
                patched = True
                patched_rows.append(
                    replace(
                        row,
                        fields=tuple(
                            (column, description if column == "description" else value)
                            for column, value in row.fields
                        ),
                    )
                )
                continue
            patched_rows.append(row)
        artifacts.append(replace(artifact, rows=tuple(patched_rows)))
    if not patched:
        raise AssertionError("Missing Datasheets_options row to patch.")
    return tuple(artifacts)


def _csv_field(value: str) -> str:
    return value.replace('"', '""')


@lru_cache(maxsize=1)
def _wahapedia_source_artifacts() -> tuple[WahapediaJsonArtifact, ...]:
    artifacts: list[WahapediaJsonArtifact] = []
    for table_name in _REQUIRED_TABLES:
        payload = json.loads(
            (_WAHAPEDIA_10E_JSON / f"{table_name}.json").read_text(encoding="utf-8")
        )
        artifacts.append(
            WahapediaJsonArtifact.from_payload(cast(WahapediaJsonArtifactPayload, payload))
        )
    return tuple(artifacts)


def _artifact_by_table(
    artifacts: tuple[WahapediaJsonArtifact, ...],
    table_name: str,
) -> WahapediaJsonArtifact:
    for artifact in artifacts:
        if artifact.source_table == table_name:
            return artifact
    raise AssertionError(f"Missing artifact table: {table_name}.")


def _optional_artifact_rows(
    artifacts: tuple[WahapediaJsonArtifact, ...],
    table_name: str,
) -> tuple[NormalizedSourceRow, ...]:
    for artifact in artifacts:
        if artifact.source_table == table_name:
            return artifact.rows
    return ()


def _row_by_id(artifact: WahapediaJsonArtifact, row_id: str) -> NormalizedSourceRow:
    for row in artifact.rows:
        if row.source_row_id == row_id:
            return row
    raise AssertionError(f"Missing source row: {row_id}.")


def _source_ids_from_row(row: NormalizedSourceRow) -> tuple[str, ...]:
    return tuple(
        source_id.strip()
        for source_id in row.runtime_fields_payload()["source_ids"].split(",")
        if source_id.strip()
    )


def _bridge_package_id() -> DataPackageId:
    return DataPackageId(
        namespace="core-v2",
        package_name="wahapedia-" + "1" + "0" + "e-bridge",
        version="phase17k-test",
    )


def _catalog_package_id() -> DataPackageId:
    return DataPackageId(
        namespace="core-v2",
        package_name="chaos-daemons-bridge-catalog",
        version="phase17k-test",
    )


def _catalog_version() -> CatalogVersion:
    return CatalogVersion.dated(
        version_id="warhammer-40000-11th-phase17k",
        source_date=date(2026, 6, 10),
    )
