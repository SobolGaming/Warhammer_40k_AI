from __future__ import annotations

import json
import math
from dataclasses import replace
from functools import lru_cache
from pathlib import Path
from typing import Any, cast

import pytest
from tools.generate_ability_support_matrix import (
    _ability_support_catalog_package,  # pyright: ignore[reportPrivateUsage]
)
from tools.generate_emperors_children_fulgrim_rule_ir import (
    OUTPUT_PATH as FULGRIM_RULE_IR_OUTPUT_PATH,
)
from tools.generate_emperors_children_fulgrim_rule_ir import (
    generated_artifact_payload as generated_fulgrim_rule_ir_artifact_payload,
)
from tools.generate_emperors_children_infractors_tormentors_rule_ir import (
    OUTPUT_PATH as INFRACTORS_TORMENTORS_RULE_IR_OUTPUT_PATH,
)
from tools.generate_emperors_children_infractors_tormentors_rule_ir import (
    generated_artifact_payload as generated_infractors_tormentors_rule_ir_artifact_payload,
)

from warhammer40k_core.adapters.local_session import LocalGameSession
from warhammer40k_core.core.army_catalog import ArmyCatalog
from warhammer40k_core.core.attachment_eligibility import (
    AttachmentEligibility,
    AttachmentRole,
    AttachmentTargetEligibility,
)
from warhammer40k_core.core.attributes import Characteristic
from warhammer40k_core.core.detachment import DetachmentDefinition
from warhammer40k_core.core.model_geometry_catalog import GeometrySourceUnits
from warhammer40k_core.core.ruleset_descriptor import BattlePhaseKind, RulesetDescriptor
from warhammer40k_core.core.weapon_profiles import AttackProfile, WeaponKeyword, WeaponProfile
from warhammer40k_core.engine import rule_model_destruction
from warhammer40k_core.engine.abilities import AbilityCatalogIndex
from warhammer40k_core.engine.ability_catalog import (
    build_player_ability_index,
    catalog_ability_records_from_catalog,
)
from warhammer40k_core.engine.actions import (
    MISSION_ACTION_UNIT_DESTROYED_INTERRUPTION_REASON,
    MissionActionState,
    MissionActionStatus,
)
from warhammer40k_core.engine.army_mustering import (
    ArmyDefinition,
    ArmyMusterRequest,
    muster_army,
)
from warhammer40k_core.engine.attached_unit_formation import AttachedUnitFormation
from warhammer40k_core.engine.attack_sequence import AttackSequence, AttackSequenceStep
from warhammer40k_core.engine.attack_sequence_completion_hooks import (
    AttackSequenceCompletedContext,
)
from warhammer40k_core.engine.battle_shock import (
    BattleShockResult,
    BattleShockTestReason,
    BattleShockTestRequest,
)
from warhammer40k_core.engine.battle_shock_hooks import BattleShockHookRegistry
from warhammer40k_core.engine.catalog_battle_shock_runtime import (
    catalog_battle_shock_hook_bindings,
)
from warhammer40k_core.engine.catalog_command_point_runtime import (
    CATALOG_IR_COMMAND_POINT_LEADERSHIP_TEST_EVENT,
    CatalogCommandPointRuntime,
)
from warhammer40k_core.engine.catalog_command_point_support import (
    CATALOG_IR_COMMAND_POINT_GAIN_CONSUMER_ID,
)
from warhammer40k_core.engine.catalog_datasheet_rule_runtime import CatalogDatasheetRuleRuntime
from warhammer40k_core.engine.catalog_datasheet_rule_support import (
    CATALOG_IR_FIGHT_END_FAILED_ACTIVATION_MODEL_DESTRUCTION_CONSUMER_ID,
    CATALOG_IR_FIGHT_SELECTED_CRITICAL_WOUND_CONSUMER_ID,
)
from warhammer40k_core.engine.catalog_poisoned_status_runtime import (
    CATALOG_POISONED_COMMAND_RESOLVED_EVENT,
    catalog_poisoned_command_start_bindings,
)
from warhammer40k_core.engine.catalog_poisoned_status_support import (
    CATALOG_IR_POISONED_COMMAND_MORTAL_WOUNDS_CONSUMER_ID,
)
from warhammer40k_core.engine.catalog_post_fight_selected_target_runtime import (
    SELECT_CATALOG_POST_FIGHT_HIT_TARGET_EFFECT_DECISION_TYPE,
    apply_catalog_post_fight_hit_target_effect_result,
    invalid_catalog_post_fight_hit_target_effect_status,
)
from warhammer40k_core.engine.catalog_rule_consumption import (
    CATALOG_IR_MOVEMENT_TRANSIT_PERMISSION_CONSUMER_ID,
    CATALOG_IR_POST_SHOOT_HIT_TARGET_EFFECT_CONSUMER_ID,
    CatalogWeaponKeywordGrantRuntime,
    catalog_movement_transit_permissions_for_model,
    catalog_rule_ir_consumers_for_rule,
)
from warhammer40k_core.engine.catalog_rule_selected_target_classification import (
    CATALOG_IR_POST_FIGHT_HIT_TARGET_EFFECT_CONSUMER_ID,
)
from warhammer40k_core.engine.catalog_selectable_ability_mode_runtime import (
    CATALOG_FALL_BACK_LEADERSHIP_TEST_EVENT,
    CatalogSelectableAbilityModeRuntime,
    catalog_selectable_ability_mode_hit_roll_bindings,
    resolve_catalog_fall_back_leadership_denial,
)
from warhammer40k_core.engine.catalog_selectable_ability_mode_support import (
    CATALOG_IR_COMMAND_PHASE_ABILITY_MODE_CONSUMER_ID,
)
from warhammer40k_core.engine.catalog_selected_target_decisions import (
    post_shoot_group_participant_id,
    post_shoot_group_participant_payload,
    post_shoot_group_stable_identity_payload,
)
from warhammer40k_core.engine.catalog_selected_target_effects import (
    CatalogSelectedTargetEffectRuntime,
    _post_shoot_hit_target_effect_groups,  # pyright: ignore[reportPrivateUsage]
    apply_catalog_post_shoot_hit_target_effect_result,
)
from warhammer40k_core.engine.catalog_selected_target_mortal_wounds import (
    CATALOG_SELECTED_TARGET_MORTAL_WOUNDS_RESOLVED_EVENT,
    CATALOG_SELECTED_TARGET_MORTAL_WOUNDS_ROLLED_EVENT,
    catalog_selected_target_mortal_wound_feel_no_pain_bindings,
)
from warhammer40k_core.engine.catalog_selected_target_test_modifiers import (
    BATTLE_SHOCK_TEST_ROLL_TYPE,
    LEADERSHIP_TEST_ROLL_TYPE,
    selected_target_test_roll_modifiers,
)
from warhammer40k_core.engine.catalog_sticky_objective_support import (
    CATALOG_IR_COMMAND_END_STICKY_OBJECTIVE_CONSUMER_ID,
)
from warhammer40k_core.engine.command_phase_start_hooks import (
    CommandPhaseStartEffectContext,
    CommandPhaseStartHookRegistry,
    CommandPhaseStartRequestContext,
    CommandPhaseStartResultContext,
)
from warhammer40k_core.engine.command_points import CommandPointSourceKind
from warhammer40k_core.engine.damage_allocation import (
    SELECT_DAMAGE_ALLOCATION_MODEL_DECISION_TYPE,
    DamageKind,
    FeelNoPainSource,
    apply_damage_to_model,
    destroy_model_by_rule,
    is_mortal_wound_feel_no_pain_request,
    mortal_wound_feel_no_pain_source_context,
)
from warhammer40k_core.engine.decision_controller import (
    DecisionController,
    DecisionControllerPayload,
)
from warhammer40k_core.engine.decision_request import DecisionRequest
from warhammer40k_core.engine.decision_result import DecisionResult, DecisionResultPayload
from warhammer40k_core.engine.destruction_provenance import (
    DestructionSourceKind,
    ModelDestructionAttribution,
)
from warhammer40k_core.engine.dice import DICE_REROLL_DECISION_TYPE, DiceRollManager
from warhammer40k_core.engine.effects import (
    EffectExpiration,
    PersistingEffect,
)
from warhammer40k_core.engine.event_log import JsonValue
from warhammer40k_core.engine.faction_content.catalog_runtime_hooks import (
    phase_end_objective_control_hook_bindings,
)
from warhammer40k_core.engine.faction_content.events import (
    RuntimeContentEvent,
    RuntimeContentEventHandlerRegistry,
    RuntimeContentEventIndex,
)
from warhammer40k_core.engine.fight_order import (
    FIGHT_ACTIVATION_DECISION_TYPE,
)
from warhammer40k_core.engine.fight_resolution import (
    SUBMIT_MELEE_DECLARATION_DECISION_TYPE,
    MeleeDeclarationProposalRequest,
)
from warhammer40k_core.engine.fights_first import FightsFirstRegistry
from warhammer40k_core.engine.game_state import (
    GameConfig,
    GameState,
    GameStatePayload,
    SecondaryMissionChoice,
    SecondaryMissionMode,
)
from warhammer40k_core.engine.lifecycle import GameLifecycle, GameLifecyclePayload
from warhammer40k_core.engine.list_validation import (
    AttachmentDeclaration,
    DetachmentSelection,
    UnitMusterSelection,
)
from warhammer40k_core.engine.mission_setup import MissionSetup
from warhammer40k_core.engine.mortal_wound_feel_no_pain_hooks import (
    MortalWoundFeelNoPainContinuationContext,
    MortalWoundFeelNoPainContinuationHookRegistry,
)
from warhammer40k_core.engine.movement_proposals import (
    MOVEMENT_PROPOSAL_DECISION_TYPE,
    MovementProposalRequest,
)
from warhammer40k_core.engine.objective_control import (
    ObjectiveControlContext,
    ObjectiveControlTiming,
    resolve_objective_control,
)
from warhammer40k_core.engine.phase import (
    BattlePhase,
    GameLifecycleStage,
    LifecycleStatus,
    LifecycleStatusKind,
)
from warhammer40k_core.engine.phases.shooting import (
    COMPLETE_SHOOTING_PHASE_OPTION_ID,
    SELECT_SHOOTING_TYPE_DECISION_TYPE,
    SELECT_SHOOTING_UNIT_DECISION_TYPE,
    SUBMIT_SHOOTING_DECLARATION_DECISION_TYPE,
)
from warhammer40k_core.engine.placement import create_deterministic_battlefield_scenario
from warhammer40k_core.engine.reaction_queue import ReactionQueue
from warhammer40k_core.engine.replay import ReplayArtifact, ReplayArtifactPayload, ReplayRunner
from warhammer40k_core.engine.rule_execution import rule_ir_from_execution_payload
from warhammer40k_core.engine.rules_units import rules_unit_view_by_id
from warhammer40k_core.engine.runtime_modifiers import (
    AttackRerollPermissionContext,
    HitRollModifierContext,
    RuntimeModifierRegistry,
    WeaponProfileModifierContext,
)
from warhammer40k_core.engine.sequencing import (
    SEQUENCING_DECISION_TYPE,
    SequencingDecision,
    apply_sequencing_decision_from_request,
)
from warhammer40k_core.engine.shooting_types import ShootingType
from warhammer40k_core.engine.source_backed_rerolls import (
    SourceBackedRerollPermissionContext,
)
from warhammer40k_core.engine.sticky_objective_control import (
    PhaseEndObjectiveControlContext,
    PhaseEndObjectiveControlHookRegistry,
    StickyObjectiveControlState,
    apply_sticky_objective_control,
    sticky_objective_control_state_is_expired,
)
from warhammer40k_core.engine.stratagems import (
    DECLINE_STRATAGEM_WINDOW_OPTION_ID,
    STRATAGEM_DECISION_TYPE,
)
from warhammer40k_core.engine.timing_windows import TimingTriggerKind
from warhammer40k_core.engine.unit_factory import UnitFactory, UnitInstance
from warhammer40k_core.engine.unit_state import BelowHalfStrengthContext
from warhammer40k_core.engine.wargear_selections import (
    ModelProfileSelection,
    WargearSelection,
)
from warhammer40k_core.engine.weapon_declaration import (
    RangedAttackPool,
    ShootingDeclarationProposal,
    WeaponDeclaration,
)
from warhammer40k_core.geometry.pose import Pose
from warhammer40k_core.rules.catalog_package import CanonicalCatalogPackage
from warhammer40k_core.rules.data_package import DataPackageId
from warhammer40k_core.rules.mission_pack_import import chapter_approved_2026_27_mission_pack
from warhammer40k_core.rules.rule_ir import RuleIR
from warhammer40k_core.rules.source_overlay import (
    OverlaySourceArtifact,
    apply_source_release_overlays,
)
from warhammer40k_core.rules.source_packages.warhammer_40000_11th import (
    emperors_children_datasheet_overlay_2026_06 as ec_overlay,
)
from warhammer40k_core.rules.source_packages.warhammer_40000_11th import (
    emperors_children_fulgrim_2026_07 as fulgrim_source_package,
)
from warhammer40k_core.rules.source_packages.warhammer_40000_11th import (
    emperors_children_infractors_tormentors_2026_08 as infractors_tormentors_source_package,
)
from warhammer40k_core.rules.wahapedia_bridge import (
    ModelHeightOverride,
    build_wahapedia_canonical_bridge_artifacts,
)
from warhammer40k_core.rules.wahapedia_schema import (
    NormalizedSourceRow,
    WahapediaJsonArtifact,
    WahapediaJsonArtifactPayload,
)

_WAHAPEDIA_10E_JSON = (
    Path(__file__).resolve().parents[2]
    / "data"
    / "source_snapshots"
    / "wahapedia"
    / ("".join(("1", "0", "th")) + "-edition")
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
_EC_DATASHEET_IDS = (
    "000004077",
    "000004079",
    "000004080",
    "000004081",
    "000004082",
    "000004083",
    "000004084",
    "000004088",
    "000004089",
    "000004090",
    "000004092",
    "000004093",
)
_BRIDGE_SUPPORTED_EC_DATASHEET_IDS = (
    "000004077",
    "000004079",
    "000004080",
    "000004083",
    "000004084",
    "000004088",
    "000004089",
    "000004090",
    "000004092",
)
_FULGRIM_ID = "000004077"
_NIGHT_SPINNER_ID = "000000611"


def test_emperors_children_datasheet_overlay_updates_source_rows() -> None:
    artifacts = _overlay_artifacts()
    abilities = _artifact_by_table(artifacts, "Datasheets_abilities")
    models = _artifact_by_table(artifacts, "Datasheets_models")
    wargear = _artifact_by_table(artifacts, "Datasheets_wargear")
    keywords = _artifact_by_table(artifacts, "Datasheets_keywords")

    assert _fields(abilities, "000004090:3")["description"] == (
        ec_overlay.SCUTTLING_HORRORS_DESCRIPTION
    )
    assert _fields(abilities, "000004081:3")["description"] == (
        ec_overlay.LETHAL_OBSESSION_DESCRIPTION
    )
    assert _fields(abilities, "000004077:6")["description"] == (ec_overlay.SERPENTINE_DESCRIPTION)
    assert _fields(models, "000004092:1")["M"] == '12"'
    assert _fields(models, "000004092:1")["Sv"] == "3+"
    assert _fields(models, "000004092:1")["OC"] == "-"
    assert _fields(wargear, "000004089:2:1:8694")["A"] == "4"
    assert _fields(wargear, "000004079:9:1:8650")["S"] == "5"
    assert _fields(wargear, "000004080:5:1:8656")["S"] == "5"

    aircraft = _fields(keywords, "000004092:Aircraft:global:false:14821")
    land_raider_frame = _fields(keywords, "000004082:Frame:global:false:212")
    rhino_frame = _fields(keywords, "000004093:Frame:global:false:222")

    assert aircraft["core_v2_superseded_by"] == "ec-heldrake-remove-aircraft"
    assert land_raider_frame["keyword"] == "Frame"
    assert rhino_frame["keyword"] == "Frame"


def test_emperors_children_overlay_feeds_active_bridge_rows() -> None:
    bridge_artifacts = build_wahapedia_canonical_bridge_artifacts(
        source_artifacts=_overlay_artifacts(),
        bridge_package_id=DataPackageId(
            namespace="core-v2",
            package_name="emperors-children-11e-bridge-test",
            version="2026-06-10",
        ),
        datasheet_ids=_BRIDGE_SUPPORTED_EC_DATASHEET_IDS,
        height_overrides=_ec_height_overrides(),
    )
    datasheets = _artifact_by_table(bridge_artifacts, "Datasheets")
    abilities = _artifact_by_table(bridge_artifacts, "Datasheets_abilities")
    models = _artifact_by_table(bridge_artifacts, "Datasheets_models")
    wargear = _artifact_by_table(bridge_artifacts, "Datasheets_wargear")
    heldrake_keywords = _keyword_set(_fields(datasheets, "000004092")["keywords"])

    assert "Aircraft" not in heldrake_keywords
    assert _model_fields(models, datasheet_id="000004092", name="Heldrake")["m"] == '12"'
    assert _model_fields(models, datasheet_id="000004092", name="Heldrake")["sv"] == "3+"
    assert _model_fields(models, datasheet_id="000004092", name="Heldrake")["oc"] == "-"
    assert _wargear_fields(wargear, datasheet_id="000004089", name="Blissblade")["a"] == "4"
    assert (
        _ability_fields(abilities, datasheet_id="000004090", name="Scuttling Horrors")[
            "description"
        ]
        == ec_overlay.SCUTTLING_HORRORS_DESCRIPTION
    )
    assert (
        _ability_fields(abilities, datasheet_id="000004077", name="Serpentine")["description"]
        == ec_overlay.SERPENTINE_DESCRIPTION
    )


def test_flawless_blades_catalog_is_complete_and_daemonic_patrons_is_consumed() -> None:
    package = _catalog_package()
    datasheet = package.army_catalog.datasheet_by_id("000004089")
    profile = datasheet.model_profiles[0]
    characteristics = {value.characteristic: value.final for value in profile.characteristics}
    assert (
        characteristics[Characteristic.MOVEMENT],
        characteristics[Characteristic.TOUGHNESS],
        characteristics[Characteristic.SAVE],
        characteristics[Characteristic.WOUNDS],
        characteristics[Characteristic.LEADERSHIP],
        characteristics[Characteristic.OBJECTIVE_CONTROL],
        characteristics[Characteristic.INVULNERABLE_SAVE],
    ) == (8, 5, 3, 3, 6, 1, 5)
    assert (datasheet.composition[0].min_models, datasheet.composition[0].max_models) == (3, 6)
    unit = _instantiate_unit(
        factory=UnitFactory(
            catalog=package.army_catalog, model_geometries=package.model_geometries
        ),
        army_id="army-flawless-blades",
        datasheet_id=datasheet.datasheet_id,
        selection_id="flawless-blades",
        model_count=3,
    )
    assert len(unit.own_models) == 3
    assert profile.base_size.diameter_mm == 40.0
    geometry = next(
        record
        for record in package.model_geometries
        if record.model_profile_id == profile.model_profile_id
    )
    assert geometry.height.height_inches == 2.0
    blissblade = _weapon_profile("000004089", "Blissblade")
    assert (blissblade.attack_profile.fixed_attacks, blissblade.strength.final) == (4, 6)
    records = tuple(
        record
        for record in catalog_ability_records_from_catalog(package.army_catalog)
        if record.datasheet_id == datasheet.datasheet_id
        and record.definition.name == "Daemonic Patrons"
    )
    assert len(records) == 2
    rule_irs = tuple(
        rule_ir_from_execution_payload(record.definition.replay_payload) for record in records
    )
    assert rule_irs[0] == rule_irs[1]
    assert len(rule_irs[0].clauses) == 2
    assert all(clause.is_supported for clause in rule_irs[0].clauses)
    assert set(catalog_rule_ir_consumers_for_rule(rule_irs[0])) == {
        CATALOG_IR_FIGHT_SELECTED_CRITICAL_WOUND_CONSUMER_ID,
        CATALOG_IR_FIGHT_END_FAILED_ACTIVATION_MODEL_DESTRUCTION_CONSUMER_ID,
    }


def test_lord_kakophonist_and_noise_marines_catalog_rule_ir_is_complete() -> None:
    package = _catalog_package()
    expected_geometry = {
        "000004084": {"Lord Kakophonist": 2.5},
        "000004088": {"Disharmonist": 2.0, "Noise Marines": 2.0},
    }
    expected_ability_consumers = {
        ("000004084", "Obsessive Annunciation"): {
            "catalog-ir:weapon-keyword-grant",
            "catalog-ir:weapon-keyword-grant:sustained-hits",
        },
        ("000004084", "Doom Siren"): {
            CATALOG_IR_POST_SHOOT_HIT_TARGET_EFFECT_CONSUMER_ID,
        },
        ("000004088", "Terrifying Crescendo"): {
            CATALOG_IR_POST_SHOOT_HIT_TARGET_EFFECT_CONSUMER_ID,
        },
    }

    for datasheet_id, expected_profiles in expected_geometry.items():
        datasheet = package.army_catalog.datasheet_by_id(datasheet_id)
        assert {profile.name for profile in datasheet.model_profiles} == expected_profiles.keys()
        for profile in datasheet.model_profiles:
            assert profile.base_size.diameter_mm == 40.0
            geometry = next(
                record
                for record in package.model_geometries
                if record.model_profile_id == profile.model_profile_id
            )
            assert geometry.height.height_inches == expected_profiles[profile.name]

    records_by_ability = {
        (record.datasheet_id, record.definition.name): record
        for record in catalog_ability_records_from_catalog(package.army_catalog)
        if (record.datasheet_id, record.definition.name) in expected_ability_consumers
    }
    assert records_by_ability.keys() == expected_ability_consumers.keys()
    for identity, expected_consumers in expected_ability_consumers.items():
        rule_ir = rule_ir_from_execution_payload(
            records_by_ability[identity].definition.replay_payload
        )
        assert rule_ir.is_supported
        assert not rule_ir.diagnostics
        assert set(catalog_rule_ir_consumers_for_rule(rule_ir)) == expected_consumers


@pytest.mark.parametrize(
    ("ability_order", "expected_same_window_modifiers"),
    [
        (("Terrifying Crescendo", "Doom Siren"), [-1]),
        (("Doom Siren", "Terrifying Crescendo"), []),
    ],
)
def test_lord_kakophonist_and_noise_marines_post_shoot_rules_use_chosen_order(
    ability_order: tuple[str, str],
    expected_same_window_modifiers: list[int],
) -> None:
    armies, state, indexes, source_noise_marines, target, attached_id = (
        _kakophonist_runtime_fixture()
    )
    state.game_id = "kakophonist-order-1"
    decisions = DecisionController()
    runtime = CatalogSelectedTargetEffectRuntime(indexes, armies)
    battle_shock_hooks = BattleShockHookRegistry.from_bindings(
        catalog_battle_shock_hook_bindings(
            ability_indexes_by_player_id=indexes,
            armies=armies,
        )
    )
    sonic_blaster = _weapon_profile("000004088", "Sonic blaster")
    modified_sonic_blaster = CatalogWeaponKeywordGrantRuntime(
        indexes,
        armies,
    ).weapon_profile_modifier(
        WeaponProfileModifierContext(
            state=state,
            source_phase=BattlePhase.SHOOTING,
            attacking_unit_instance_id=attached_id,
            attacker_model_instance_id=(source_noise_marines.own_models[0].model_instance_id),
            target_unit_instance_id=target.unit_instance_id,
            weapon_profile=sonic_blaster,
        )
    )
    assert WeaponKeyword.SUSTAINED_HITS in modified_sonic_blaster.keywords
    assert "sustained-hits:1" in {
        ability.ability_id for ability in modified_sonic_blaster.abilities
    }

    resolved_names = _resolve_kakophonist_post_shoot_effects(
        runtime=runtime,
        state=state,
        decisions=decisions,
        indexes=indexes,
        source_noise_marines=source_noise_marines,
        source_rules_unit_id=attached_id,
        target=target,
        sequence_suffix=ability_order[0].casefold().replace(" ", "-"),
        battle_shock_hooks=battle_shock_hooks,
        ability_order=ability_order,
    )
    assert resolved_names == ability_order
    mortal_event = next(
        event
        for event in decisions.event_log.records
        if event.event_type == CATALOG_SELECTED_TARGET_MORTAL_WOUNDS_ROLLED_EVENT
    )
    mortal_payload = cast(dict[str, Any], mortal_event.payload)
    assert cast(int, mortal_payload["mortal_wounds"]) > 0
    battle_shock_payload = cast(
        dict[str, Any],
        next(
            event.payload
            for event in decisions.event_log.records
            if event.event_type == "catalog_selected_target_battle_shock_resolved"
        ),
    )
    assert [
        modifier["operand"]
        for modifier in cast(
            list[dict[str, Any]],
            cast(dict[str, Any], battle_shock_payload["battle_shock_result"])["modified_roll"][
                "modifiers"
            ],
        )
    ] == expected_same_window_modifiers

    for roll_type in (BATTLE_SHOCK_TEST_ROLL_TYPE, LEADERSHIP_TEST_ROLL_TYPE):
        modifiers = selected_target_test_roll_modifiers(
            state=state,
            unit_instance_id=target.unit_instance_id,
            roll_type=roll_type,
        )
        assert [modifier.operand for modifier in modifiers] == [-1]
    assert len(state.persisting_effects_for_unit(target.unit_instance_id)) == 2
    assert all(
        effect.expiration.expiration_kind.value == "start_phase"
        and effect.expiration.battle_round == 2
        and effect.expiration.phase is BattlePhaseKind.SHOOTING
        and effect.expiration.player_id == "player-a"
        for effect in state.persisting_effects_for_unit(target.unit_instance_id)
    )

    roundtripped_state = GameState.from_payload(
        cast(GameStatePayload, json.loads(json.dumps(state.to_payload(), sort_keys=True)))
    )
    assert roundtripped_state.to_payload() == state.to_payload()
    roundtripped_decisions = DecisionController.from_payload(
        cast(
            DecisionControllerPayload,
            json.loads(json.dumps(decisions.to_payload(), sort_keys=True)),
        )
    )
    assert roundtripped_decisions.to_payload() == decisions.to_payload()
    sequencing_payload = cast(
        dict[str, Any],
        next(
            event.payload
            for event in decisions.event_log.records
            if event.event_type == "sequencing_order_resolved"
        ),
    )
    assert (
        SequencingDecision.from_payload(cast(Any, sequencing_payload)).to_payload()
        == sequencing_payload
    )


def test_post_shoot_order_survives_one_of_multiple_hit_targets_being_destroyed() -> None:
    (
        _config,
        armies,
        state,
        indexes,
        source_noise_marines,
        target_a,
        target_b,
        source_attached_id,
    ) = _configured_kakophonist_multi_target_fixture()
    _leave_one_wound_on_unit(state=state, unit=target_a)
    decisions = DecisionController()
    runtime = CatalogSelectedTargetEffectRuntime(indexes, armies)
    battle_shock_hooks = BattleShockHookRegistry.from_bindings(
        catalog_battle_shock_hook_bindings(
            ability_indexes_by_player_id=indexes,
            armies=armies,
        )
    )
    context = _kakophonist_post_shoot_context(
        state=state,
        decisions=decisions,
        source_noise_marines=source_noise_marines,
        source_rules_unit_id=source_attached_id,
        targets=((target_a, None), (target_b, None)),
        sequence_suffix="mutable-target-set",
    )

    assert runtime.post_shoot_hit_target_request(context) is not None
    sequencing_request = decisions.queue.peek_next()
    sequencing_decision = _submit_post_shoot_sequencing_order(
        decisions=decisions,
        request=sequencing_request,
        ability_order=("Doom Siren", "Terrifying Crescendo"),
        result_id="mutable-target-set-sequencing-result",
    )
    assert runtime.post_shoot_hit_target_request(context) is not None
    doom_request = decisions.queue.peek_next()
    doom_status = _submit_catalog_post_shoot_target(
        state=state,
        decisions=decisions,
        request=doom_request,
        target_unit_instance_id=target_a.unit_instance_id,
        result_id="mutable-target-set-doom-siren-result",
        battle_shock_hooks=battle_shock_hooks,
        indexes=indexes,
    )
    assert doom_status is None
    assert all(
        not model.is_alive
        for model in _unit_from_state(state, target_a.unit_instance_id).own_models
    )

    assert runtime.post_shoot_hit_target_request(context) is not None
    crescendo_request = decisions.queue.peek_next()
    crescendo_payload = cast(dict[str, Any], crescendo_request.payload)
    assert crescendo_payload["ability_name"] == "Terrifying Crescendo"
    assert crescendo_payload["available_target_unit_instance_ids"] == [target_b.unit_instance_id]
    roundtripped_request = DecisionRequest.from_payload(
        json.loads(json.dumps(crescendo_request.to_payload(), sort_keys=True))
    )
    assert roundtripped_request == crescendo_request
    assert (
        SequencingDecision.from_payload(
            json.loads(json.dumps(sequencing_decision.to_payload(), sort_keys=True))
        )
        == sequencing_decision
    )
    assert (
        GameState.from_payload(
            cast(GameStatePayload, json.loads(json.dumps(state.to_payload(), sort_keys=True)))
        ).to_payload()
        == state.to_payload()
    )
    assert (
        DecisionController.from_payload(
            cast(
                DecisionControllerPayload,
                json.loads(json.dumps(decisions.to_payload(), sort_keys=True)),
            )
        ).to_payload()
        == decisions.to_payload()
    )


def test_post_shoot_pending_decision_after_target_set_change_replays() -> None:
    (
        config,
        armies,
        state,
        indexes,
        source_noise_marines,
        target_a,
        target_b,
        source_attached_id,
    ) = _configured_kakophonist_multi_target_fixture()
    decisions = DecisionController()
    runtime = CatalogSelectedTargetEffectRuntime(indexes, armies)
    battle_shock_hooks = BattleShockHookRegistry.from_bindings(
        catalog_battle_shock_hook_bindings(
            ability_indexes_by_player_id=indexes,
            armies=armies,
        )
    )
    context = _kakophonist_post_shoot_context(
        state=state,
        decisions=decisions,
        source_noise_marines=source_noise_marines,
        source_rules_unit_id=source_attached_id,
        targets=((target_a, None), (target_b, None)),
        sequence_suffix="target-set-replay",
    )

    assert runtime.post_shoot_hit_target_request(context) is not None
    _submit_post_shoot_sequencing_order(
        decisions=decisions,
        request=decisions.queue.peek_next(),
        ability_order=("Terrifying Crescendo", "Doom Siren"),
        result_id="target-set-replay-sequencing-result",
    )
    assert runtime.post_shoot_hit_target_request(context) is not None
    assert (
        _submit_catalog_post_shoot_target(
            state=state,
            decisions=decisions,
            request=decisions.queue.peek_next(),
            target_unit_instance_id=target_a.unit_instance_id,
            result_id="target-set-replay-crescendo-result",
            battle_shock_hooks=battle_shock_hooks,
            indexes=indexes,
        )
        is None
    )
    battlefield = state.battlefield_state
    assert battlefield is not None
    state.replace_battlefield_state(battlefield.with_removed_models(target_a.own_model_ids()))

    assert runtime.post_shoot_hit_target_request(context) is not None
    doom_request = decisions.queue.peek_next()
    doom_payload = cast(dict[str, Any], doom_request.payload)
    assert doom_payload["ability_name"] == "Doom Siren"
    assert doom_payload["available_target_unit_instance_ids"] == [target_b.unit_instance_id]
    pending_lifecycle_payload = cast(
        GameLifecyclePayload,
        {
            "config": config.to_payload(),
            "parameterized_movement_proposals": True,
            "state": state.to_payload(),
            "decisions": decisions.to_payload(),
            "reaction_queue": ReactionQueue().to_payload(),
        },
    )
    lifecycle = GameLifecycle.from_payload(pending_lifecycle_payload)
    pending_lifecycle_payload = lifecycle.to_payload()
    assert GameLifecycle.from_payload(pending_lifecycle_payload).to_payload() == (
        pending_lifecycle_payload
    )
    session = LocalGameSession(lifecycle=lifecycle)
    submitted = session.submit_option(
        request_id=doom_request.request_id,
        option_id=doom_request.options[0].option_id,
        result_id="target-set-replay-doom-result",
    )
    assert submitted.status_kind not in {
        LifecycleStatusKind.INVALID,
        LifecycleStatusKind.UNSUPPORTED,
    }
    replay_payload = cast(
        ReplayArtifactPayload,
        json.loads(
            json.dumps(
                ReplayArtifact.capture(
                    artifact_id="post-shoot-target-set-change",
                    initial_lifecycle_payload=pending_lifecycle_payload,
                    final_lifecycle=session.lifecycle,
                ).to_payload(),
                sort_keys=True,
            )
        ),
    )
    replay_result = ReplayRunner.from_payload(replay_payload).run()
    assert replay_result.reproduced_exactly, replay_result.to_payload()


def test_post_shoot_order_survives_target_set_change_after_feel_no_pain() -> None:
    (
        _config,
        armies,
        state,
        indexes,
        source_noise_marines,
        target_a,
        target_b,
        source_attached_id,
    ) = _configured_kakophonist_multi_target_fixture()
    state.game_id = "kakophonist-runtime-test"
    survivor_id = _leave_one_wound_on_unit(state=state, unit=target_a)
    source_a = FeelNoPainSource(source_id="mutable-target-fnp-a", threshold=5)
    source_b = FeelNoPainSource(source_id="mutable-target-fnp-b", threshold=6)
    state.record_model_feel_no_pain_sources(
        model_instance_id=survivor_id,
        sources=(source_a, source_b),
    )
    decisions = DecisionController()
    runtime = CatalogSelectedTargetEffectRuntime(indexes, armies)
    battle_shock_hooks = BattleShockHookRegistry.from_bindings(
        catalog_battle_shock_hook_bindings(
            ability_indexes_by_player_id=indexes,
            armies=armies,
        )
    )
    context = _kakophonist_post_shoot_context(
        state=state,
        decisions=decisions,
        source_noise_marines=source_noise_marines,
        source_rules_unit_id=source_attached_id,
        targets=((target_a, None), (target_b, None)),
        sequence_suffix="mutable-target-set-fnp",
    )

    assert runtime.post_shoot_hit_target_request(context) is not None
    _submit_post_shoot_sequencing_order(
        decisions=decisions,
        request=decisions.queue.peek_next(),
        ability_order=("Doom Siren", "Terrifying Crescendo"),
        result_id="mutable-target-set-fnp-sequencing-result",
    )
    assert runtime.post_shoot_hit_target_request(context) is not None
    status = _submit_catalog_post_shoot_target(
        state=state,
        decisions=decisions,
        request=decisions.queue.peek_next(),
        target_unit_instance_id=target_a.unit_instance_id,
        result_id="mutable-target-set-fnp-doom-siren-result",
        battle_shock_hooks=battle_shock_hooks,
        indexes=indexes,
    )
    assert status is not None
    continuation_registry = MortalWoundFeelNoPainContinuationHookRegistry.from_bindings(
        catalog_selected_target_mortal_wound_feel_no_pain_bindings(
            ability_indexes_by_player_id=indexes,
        )
    )
    while status is not None:
        fnp_request = cast(DecisionRequest, status.decision_request)
        source_context = mortal_wound_feel_no_pain_source_context(fnp_request)
        fnp_result = DecisionResult.for_request(
            result_id=f"mutable-target-set-fnp-{fnp_request.request_id}",
            request=fnp_request,
            selected_option_id=source_a.source_id,
        )
        decisions.submit_result(fnp_result)
        status = continuation_registry.apply_decision(
            MortalWoundFeelNoPainContinuationContext(
                state=state,
                decisions=decisions,
                request=fnp_request,
                result=fnp_result,
                source_context=source_context,
                dice_manager=DiceRollManager(state.game_id, event_log=decisions.event_log),
                runtime_modifier_registry=RuntimeModifierRegistry.empty(),
                battle_shock_hooks=battle_shock_hooks,
                ability_indexes_by_player_id=indexes,
            )
        )
    assert all(
        not model.is_alive
        for model in _unit_from_state(state, target_a.unit_instance_id).own_models
    )

    assert runtime.post_shoot_hit_target_request(context) is not None
    crescendo_request = decisions.queue.peek_next()
    crescendo_payload = cast(dict[str, Any], crescendo_request.payload)
    assert crescendo_payload["ability_name"] == "Terrifying Crescendo"
    assert crescendo_payload["available_target_unit_instance_ids"] == [target_b.unit_instance_id]
    assert (
        DecisionController.from_payload(
            cast(
                DecisionControllerPayload,
                json.loads(json.dumps(decisions.to_payload(), sort_keys=True)),
            )
        ).to_payload()
        == decisions.to_payload()
    )


@pytest.mark.parametrize("use_feel_no_pain", [False, True])
def test_post_shoot_order_survives_attached_target_splitting_after_first_effect(
    use_feel_no_pain: bool,
) -> None:
    (
        _config,
        armies,
        state,
        indexes,
        source_noise_marines,
        target_noise_marines,
        target_lord,
        source_attached_id,
        target_attached_id,
    ) = _configured_kakophonist_attached_target_fixture()
    survivor_id = _leave_one_wound_on_unit(state=state, unit=target_noise_marines)
    feel_no_pain_source = FeelNoPainSource(
        source_id="attached-target-split-fnp-a",
        threshold=5,
    )
    if use_feel_no_pain:
        state.game_id = "kakophonist-attached-target-fnp-destruction"
        state.record_model_feel_no_pain_sources(
            model_instance_id=survivor_id,
            sources=(
                feel_no_pain_source,
                FeelNoPainSource(
                    source_id="attached-target-split-fnp-b",
                    threshold=6,
                ),
            ),
        )
    decisions = DecisionController()
    runtime = CatalogSelectedTargetEffectRuntime(indexes, armies)
    battle_shock_hooks = BattleShockHookRegistry.from_bindings(
        catalog_battle_shock_hook_bindings(
            ability_indexes_by_player_id=indexes,
            armies=armies,
        )
    )
    context = _kakophonist_post_shoot_context(
        state=state,
        decisions=decisions,
        source_noise_marines=source_noise_marines,
        source_rules_unit_id=source_attached_id,
        targets=((target_noise_marines, target_attached_id),),
        sequence_suffix="attached-target-splits",
    )

    assert runtime.post_shoot_hit_target_request(context) is not None
    _submit_post_shoot_sequencing_order(
        decisions=decisions,
        request=decisions.queue.peek_next(),
        ability_order=("Doom Siren", "Terrifying Crescendo"),
        result_id="attached-target-splits-sequencing-result",
    )
    assert runtime.post_shoot_hit_target_request(context) is not None
    status = _submit_catalog_post_shoot_target(
        state=state,
        decisions=decisions,
        request=decisions.queue.peek_next(),
        target_unit_instance_id=target_attached_id,
        result_id="attached-target-splits-doom-siren-result",
        battle_shock_hooks=battle_shock_hooks,
        indexes=indexes,
    )
    if use_feel_no_pain:
        assert status is not None
        continuation_registry = MortalWoundFeelNoPainContinuationHookRegistry.from_bindings(
            catalog_selected_target_mortal_wound_feel_no_pain_bindings(
                ability_indexes_by_player_id=indexes,
            )
        )
        while status is not None:
            fnp_request = cast(DecisionRequest, status.decision_request)
            assert is_mortal_wound_feel_no_pain_request(fnp_request)
            source_context = mortal_wound_feel_no_pain_source_context(fnp_request)
            fnp_result = DecisionResult.for_request(
                result_id=f"attached-target-splits-fnp-{fnp_request.request_id}",
                request=fnp_request,
                selected_option_id=feel_no_pain_source.source_id,
            )
            decisions.submit_result(fnp_result)
            status = continuation_registry.apply_decision(
                MortalWoundFeelNoPainContinuationContext(
                    state=state,
                    decisions=decisions,
                    request=fnp_request,
                    result=fnp_result,
                    source_context=source_context,
                    dice_manager=DiceRollManager(
                        state.game_id,
                        event_log=decisions.event_log,
                    ),
                    runtime_modifier_registry=RuntimeModifierRegistry.empty(),
                    battle_shock_hooks=battle_shock_hooks,
                    ability_indexes_by_player_id=indexes,
                )
            )
    else:
        assert status is None
    assert all(
        not model.is_alive
        for model in _unit_from_state(state, target_noise_marines.unit_instance_id).own_models
    )
    assert any(
        model.is_alive for model in _unit_from_state(state, target_lord.unit_instance_id).own_models
    )
    assert all(
        formation.attached_unit_instance_id != target_attached_id
        for army in state.army_definitions
        for formation in army.attached_units
    )
    assert target_attached_id not in {
        record.unit_instance_id for record in state.starting_strength_records
    }
    assert state.starting_strength_record_for_unit(
        target_noise_marines.unit_instance_id
    ).starting_model_count == len(target_noise_marines.own_models)
    assert state.starting_strength_record_for_unit(
        target_lord.unit_instance_id
    ).starting_model_count == len(target_lord.own_models)
    battle_shock_payload = cast(
        dict[str, Any],
        next(
            event.payload
            for event in decisions.event_log.records
            if event.event_type == "battle_shock_test_requested"
            and cast(dict[str, Any], event.payload).get("source_kind")
            == "catalog_selected_target_effect"
        ),
    )
    battle_shock_request = cast(
        dict[str, Any],
        battle_shock_payload["battle_shock_test_request"],
    )
    assert battle_shock_request["unit_instance_id"] == target_attached_id
    assert battle_shock_payload["target_identity_resolution"] == "unchanged"
    assert target_attached_id not in state.battle_shocked_unit_ids

    assert runtime.post_shoot_hit_target_request(context) is not None
    crescendo_request = decisions.queue.peek_next()
    crescendo_payload = cast(dict[str, Any], crescendo_request.payload)
    assert crescendo_payload["ability_name"] == "Terrifying Crescendo"
    assert crescendo_payload["available_target_unit_instance_ids"] == [target_lord.unit_instance_id]
    assert target_attached_id not in crescendo_payload["available_target_unit_instance_ids"]
    assert (
        GameState.from_payload(
            cast(GameStatePayload, json.loads(json.dumps(state.to_payload(), sort_keys=True)))
        ).to_payload()
        == state.to_payload()
    )
    assert (
        DecisionController.from_payload(
            cast(
                DecisionControllerPayload,
                json.loads(json.dumps(decisions.to_payload(), sort_keys=True)),
            )
        ).to_payload()
        == decisions.to_payload()
    )


@pytest.mark.parametrize("use_feel_no_pain", [False, True])
def test_doom_siren_splits_bodyguard_from_surviving_leader_and_support_after_chain(
    use_feel_no_pain: bool,
) -> None:
    (
        _config,
        armies,
        state,
        indexes,
        source_noise_marines,
        target_bodyguard,
        target_leader,
        target_support,
        source_attached_id,
        target_attached_id,
    ) = _configured_kakophonist_leader_support_target_fixture()
    state.game_id = "kakophonist-leader-support-split-fnp-destruction"
    final_bodyguard_model_id = _leave_one_wound_on_unit(state=state, unit=target_bodyguard)
    survivor_ids = tuple(sorted((target_leader.unit_instance_id, target_support.unit_instance_id)))
    _record_attached_split_authoritative_state(
        state=state,
        target_attached_id=target_attached_id,
    )
    feel_no_pain_source = FeelNoPainSource(
        source_id="leader-support-split-fnp-a",
        threshold=6,
    )
    if use_feel_no_pain:
        state.record_model_feel_no_pain_sources(
            model_instance_id=final_bodyguard_model_id,
            sources=(
                feel_no_pain_source,
                FeelNoPainSource(
                    source_id="leader-support-split-fnp-b",
                    threshold=5,
                ),
            ),
        )
    decisions = DecisionController()
    runtime = CatalogSelectedTargetEffectRuntime(indexes, armies)
    battle_shock_hooks = BattleShockHookRegistry.from_bindings(
        catalog_battle_shock_hook_bindings(
            ability_indexes_by_player_id=indexes,
            armies=armies,
        )
    )
    context = _kakophonist_post_shoot_context(
        state=state,
        decisions=decisions,
        source_noise_marines=source_noise_marines,
        source_rules_unit_id=source_attached_id,
        targets=((target_bodyguard, target_attached_id),),
        sequence_suffix=f"leader-support-split-fnp-{use_feel_no_pain}",
    )

    assert runtime.post_shoot_hit_target_request(context) is not None
    _submit_post_shoot_sequencing_order(
        decisions=decisions,
        request=decisions.queue.peek_next(),
        ability_order=("Doom Siren", "Terrifying Crescendo"),
        result_id=f"leader-support-split-sequencing-{use_feel_no_pain}",
    )
    assert runtime.post_shoot_hit_target_request(context) is not None
    status = _submit_catalog_post_shoot_target(
        state=state,
        decisions=decisions,
        request=decisions.queue.peek_next(),
        target_unit_instance_id=target_attached_id,
        result_id=f"leader-support-split-doom-{use_feel_no_pain}",
        battle_shock_hooks=battle_shock_hooks,
        indexes=indexes,
    )
    if use_feel_no_pain:
        assert status is not None
        continuation_registry = MortalWoundFeelNoPainContinuationHookRegistry.from_bindings(
            catalog_selected_target_mortal_wound_feel_no_pain_bindings(
                ability_indexes_by_player_id=indexes,
            )
        )
        while status is not None:
            fnp_request = cast(DecisionRequest, status.decision_request)
            assert is_mortal_wound_feel_no_pain_request(fnp_request)
            source_context = mortal_wound_feel_no_pain_source_context(fnp_request)
            fnp_result = DecisionResult.for_request(
                result_id=f"leader-support-split-fnp-{fnp_request.request_id}",
                request=fnp_request,
                selected_option_id=feel_no_pain_source.source_id,
            )
            decisions.submit_result(fnp_result)
            status = continuation_registry.apply_decision(
                MortalWoundFeelNoPainContinuationContext(
                    state=state,
                    decisions=decisions,
                    request=fnp_request,
                    result=fnp_result,
                    source_context=source_context,
                    dice_manager=DiceRollManager(
                        state.game_id,
                        event_log=decisions.event_log,
                    ),
                    runtime_modifier_registry=RuntimeModifierRegistry.empty(),
                    battle_shock_hooks=battle_shock_hooks,
                    ability_indexes_by_player_id=indexes,
                )
            )
    else:
        assert status is None

    assert all(
        not model.is_alive
        for model in _unit_from_state(state, target_bodyguard.unit_instance_id).own_models
    )
    battle_shock_payload = cast(
        dict[str, Any],
        next(
            event.payload
            for event in decisions.event_log.records
            if event.event_type == "catalog_selected_target_battle_shock_resolved"
        ),
    )
    battle_shock_result = cast(dict[str, Any], battle_shock_payload["battle_shock_result"])
    battle_shock_request = cast(dict[str, Any], battle_shock_result["request"])
    assert battle_shock_request["unit_instance_id"] == target_attached_id
    assert battle_shock_payload["target_identity_resolution"] == "unchanged"
    expected_shocked_ids = () if battle_shock_result["passed"] else survivor_ids
    assert (
        tuple(unit_id for unit_id in state.battle_shocked_unit_ids if unit_id in survivor_ids)
        == expected_shocked_ids
    )
    assert target_attached_id not in state.battle_shocked_unit_ids
    if expected_shocked_ids:
        shocked_states = tuple(
            shocked_state
            for shocked_state in state.battle_shocked_unit_states
            if shocked_state.unit_instance_id in survivor_ids
        )
        assert tuple(shocked_state.unit_instance_id for shocked_state in shocked_states) == (
            survivor_ids
        )
        assert tuple(shocked_state.model_instance_ids for shocked_state in shocked_states) == tuple(
            tuple(model.model_instance_id for model in unit.own_models)
            for unit in sorted(
                (target_leader, target_support),
                key=lambda unit: unit.unit_instance_id,
            )
        )
    _assert_attached_split_authoritative_state(
        state=state,
        decisions=decisions,
        target_attached_id=target_attached_id,
        component_units=(target_bodyguard, target_leader, target_support),
        survivor_ids=survivor_ids,
    )

    assert runtime.post_shoot_hit_target_request(context) is not None
    crescendo_payload = cast(dict[str, Any], decisions.queue.peek_next().payload)
    assert crescendo_payload["ability_name"] == "Terrifying Crescendo"
    assert crescendo_payload["available_target_unit_instance_ids"] == list(survivor_ids)
    assert target_attached_id not in crescendo_payload["available_target_unit_instance_ids"]
    state_payload = cast(
        GameStatePayload,
        json.loads(json.dumps(state.to_payload(), sort_keys=True)),
    )
    decision_payload = cast(
        DecisionControllerPayload,
        json.loads(json.dumps(decisions.to_payload(), sort_keys=True)),
    )
    assert GameState.from_payload(state_payload).to_payload() == state.to_payload()
    assert DecisionController.from_payload(decision_payload).to_payload() == decisions.to_payload()


def test_selected_target_attached_split_lifecycle_and_replay_round_trip() -> None:
    (
        config,
        armies,
        state,
        indexes,
        source_noise_marines,
        target_noise_marines,
        target_lord,
        source_attached_id,
        target_attached_id,
    ) = _configured_kakophonist_attached_target_fixture(
        single_wound_noise_marines=True,
    )
    assert len(target_noise_marines.own_models) == 1
    assert target_noise_marines.own_models[0].wounds_remaining == 1
    decisions = DecisionController()
    runtime = CatalogSelectedTargetEffectRuntime(indexes, armies)
    context = _kakophonist_post_shoot_context(
        state=state,
        decisions=decisions,
        source_noise_marines=source_noise_marines,
        source_rules_unit_id=source_attached_id,
        targets=((target_noise_marines, target_attached_id),),
        sequence_suffix="attached-split-replay",
    )

    assert runtime.post_shoot_hit_target_request(context) is not None
    _submit_post_shoot_sequencing_order(
        decisions=decisions,
        request=decisions.queue.peek_next(),
        ability_order=("Doom Siren", "Terrifying Crescendo"),
        result_id="attached-split-replay-sequencing-result",
    )
    assert runtime.post_shoot_hit_target_request(context) is not None
    doom_request = decisions.queue.peek_next()
    doom_option = next(
        option
        for option in doom_request.options
        if cast(
            dict[str, Any],
            cast(dict[str, Any], option.payload)["selected_catalog_target_effect"],
        )["target_unit_instance_id"]
        == target_attached_id
    )
    initial_lifecycle_payload = cast(
        GameLifecyclePayload,
        {
            "config": config.to_payload(),
            "parameterized_movement_proposals": True,
            "state": state.to_payload(),
            "decisions": decisions.to_payload(),
            "reaction_queue": ReactionQueue().to_payload(),
        },
    )
    lifecycle = GameLifecycle.from_payload(initial_lifecycle_payload)
    initial_lifecycle_payload = lifecycle.to_payload()
    assert GameLifecycle.from_payload(initial_lifecycle_payload).to_payload() == (
        initial_lifecycle_payload
    )

    session = LocalGameSession(lifecycle=lifecycle)
    submitted = session.submit_option(
        request_id=doom_request.request_id,
        option_id=doom_option.option_id,
        result_id="attached-split-replay-doom-result",
    )
    assert submitted.status_kind not in {
        LifecycleStatusKind.INVALID,
        LifecycleStatusKind.UNSUPPORTED,
    }
    final_state = session.lifecycle.state
    assert final_state is not None
    assert all(
        formation.attached_unit_instance_id != target_attached_id
        for army in final_state.army_definitions
        for formation in army.attached_units
    )
    assert (
        final_state.starting_strength_record_for_unit(
            target_noise_marines.unit_instance_id
        ).starting_model_count
        == 1
    )
    assert (
        final_state.starting_strength_record_for_unit(
            target_lord.unit_instance_id
        ).starting_model_count
        == 1
    )
    battle_shock_request_payload = cast(
        dict[str, Any],
        next(
            cast(dict[str, Any], event.payload)["battle_shock_test_request"]
            for event in session.lifecycle.decision_controller.event_log.records
            if event.event_type == "battle_shock_test_requested"
            and cast(dict[str, Any], event.payload).get("source_kind")
            == "catalog_selected_target_effect"
        ),
    )
    assert battle_shock_request_payload["unit_instance_id"] == target_attached_id
    final_payload = session.lifecycle.to_payload()
    assert GameLifecycle.from_payload(final_payload).to_payload() == final_payload
    replay_payload = cast(
        ReplayArtifactPayload,
        json.loads(
            json.dumps(
                ReplayArtifact.capture(
                    artifact_id="selected-target-attached-unit-split",
                    initial_lifecycle_payload=initial_lifecycle_payload,
                    final_lifecycle=session.lifecycle,
                ).to_payload(),
                sort_keys=True,
            )
        ),
    )
    replay_result = ReplayRunner.from_payload(replay_payload).run()
    assert replay_result.reproduced_exactly, replay_result.to_payload()


@pytest.mark.parametrize("use_feel_no_pain", [False, True])
def test_leader_support_split_lifecycle_and_replay_round_trip(
    use_feel_no_pain: bool,
) -> None:
    (
        config,
        armies,
        state,
        indexes,
        source_noise_marines,
        target_bodyguard,
        target_leader,
        target_support,
        source_attached_id,
        target_attached_id,
    ) = _configured_kakophonist_leader_support_target_fixture(
        single_wound_bodyguard=True,
    )
    assert len(target_bodyguard.own_models) == 1
    assert target_bodyguard.own_models[0].wounds_remaining == 1
    survivor_ids = tuple(sorted((target_leader.unit_instance_id, target_support.unit_instance_id)))
    _record_attached_split_authoritative_state(
        state=state,
        target_attached_id=target_attached_id,
    )
    feel_no_pain_source = FeelNoPainSource(
        source_id="leader-support-replay-fnp-a",
        threshold=6,
    )
    if use_feel_no_pain:
        state.record_model_feel_no_pain_sources(
            model_instance_id=target_bodyguard.own_models[0].model_instance_id,
            sources=(
                feel_no_pain_source,
                FeelNoPainSource(
                    source_id="leader-support-replay-fnp-b",
                    threshold=5,
                ),
            ),
        )
    decisions = DecisionController()
    runtime = CatalogSelectedTargetEffectRuntime(indexes, armies)
    context = _kakophonist_post_shoot_context(
        state=state,
        decisions=decisions,
        source_noise_marines=source_noise_marines,
        source_rules_unit_id=source_attached_id,
        targets=((target_bodyguard, target_attached_id),),
        sequence_suffix=f"leader-support-replay-{use_feel_no_pain}",
    )

    assert runtime.post_shoot_hit_target_request(context) is not None
    _submit_post_shoot_sequencing_order(
        decisions=decisions,
        request=decisions.queue.peek_next(),
        ability_order=("Doom Siren", "Terrifying Crescendo"),
        result_id=f"leader-support-replay-sequencing-{use_feel_no_pain}",
    )
    assert runtime.post_shoot_hit_target_request(context) is not None
    doom_request = decisions.queue.peek_next()
    doom_option = next(
        option
        for option in doom_request.options
        if cast(
            dict[str, Any],
            cast(dict[str, Any], option.payload)["selected_catalog_target_effect"],
        )["target_unit_instance_id"]
        == target_attached_id
    )
    initial_lifecycle_payload = cast(
        GameLifecyclePayload,
        {
            "config": config.to_payload(),
            "parameterized_movement_proposals": True,
            "state": state.to_payload(),
            "decisions": decisions.to_payload(),
            "reaction_queue": ReactionQueue().to_payload(),
        },
    )
    lifecycle = GameLifecycle.from_payload(initial_lifecycle_payload)
    initial_lifecycle_payload = lifecycle.to_payload()
    assert GameLifecycle.from_payload(initial_lifecycle_payload).to_payload() == (
        initial_lifecycle_payload
    )

    session = LocalGameSession(lifecycle=lifecycle)
    status = session.submit_option(
        request_id=doom_request.request_id,
        option_id=doom_option.option_id,
        result_id=f"leader-support-replay-doom-{use_feel_no_pain}",
    )
    if use_feel_no_pain:
        while (
            status.status_kind is LifecycleStatusKind.WAITING_FOR_DECISION
            and status.decision_request is not None
            and is_mortal_wound_feel_no_pain_request(status.decision_request)
        ):
            fnp_request = status.decision_request
            status = session.submit_option(
                request_id=fnp_request.request_id,
                option_id=feel_no_pain_source.source_id,
                result_id=f"leader-support-replay-fnp-{fnp_request.request_id}",
            )
    assert status.status_kind not in {
        LifecycleStatusKind.INVALID,
        LifecycleStatusKind.UNSUPPORTED,
    }
    final_state = session.lifecycle.state
    assert final_state is not None
    assert all(
        not model.is_alive
        for model in _unit_from_state(
            final_state,
            target_bodyguard.unit_instance_id,
        ).own_models
    )
    _assert_attached_split_authoritative_state(
        state=final_state,
        decisions=session.lifecycle.decision_controller,
        target_attached_id=target_attached_id,
        component_units=(target_bodyguard, target_leader, target_support),
        survivor_ids=survivor_ids,
    )
    battle_shock_payload = cast(
        dict[str, Any],
        next(
            event.payload
            for event in session.lifecycle.decision_controller.event_log.records
            if event.event_type == "catalog_selected_target_battle_shock_resolved"
        ),
    )
    battle_shock_result = cast(dict[str, Any], battle_shock_payload["battle_shock_result"])
    assert (
        cast(dict[str, Any], battle_shock_result["request"])["unit_instance_id"]
        == target_attached_id
    )
    expected_shocked_ids = () if battle_shock_result["passed"] else survivor_ids
    assert (
        tuple(unit_id for unit_id in final_state.battle_shocked_unit_ids if unit_id in survivor_ids)
        == expected_shocked_ids
    )
    final_payload = session.lifecycle.to_payload()
    assert GameLifecycle.from_payload(final_payload).to_payload() == final_payload
    replay_payload = cast(
        ReplayArtifactPayload,
        json.loads(
            json.dumps(
                ReplayArtifact.capture(
                    artifact_id=f"selected-target-leader-support-split-{use_feel_no_pain}",
                    initial_lifecycle_payload=initial_lifecycle_payload,
                    final_lifecycle=session.lifecycle,
                ).to_payload(),
                sort_keys=True,
            )
        ),
    )
    replay_result = ReplayRunner.from_payload(replay_payload).run()
    assert replay_result.reproduced_exactly, replay_result.to_payload()


def test_post_shoot_participant_identity_ignores_ability_display_name() -> None:
    (
        _config,
        armies,
        state,
        indexes,
        source_noise_marines,
        target_a,
        target_b,
        source_attached_id,
    ) = _configured_kakophonist_multi_target_fixture()
    decisions = DecisionController()
    runtime = CatalogSelectedTargetEffectRuntime(indexes, armies)
    context = _kakophonist_post_shoot_context(
        state=state,
        decisions=decisions,
        source_noise_marines=source_noise_marines,
        source_rules_unit_id=source_attached_id,
        targets=((target_a, None), (target_b, None)),
        sequence_suffix="localized-display-name",
    )

    assert runtime.post_shoot_hit_target_request(context) is not None
    sequencing_request = decisions.queue.peek_next()
    request_participants = cast(
        list[dict[str, Any]],
        cast(dict[str, Any], sequencing_request.payload)["participants"],
    )
    original_participant_id_by_record = {
        cast(str, cast(dict[str, Any], participant["payload"])["catalog_record_id"]): cast(
            str, participant["participant_id"]
        )
        for participant in request_participants
    }
    _submit_post_shoot_sequencing_order(
        decisions=decisions,
        request=sequencing_request,
        ability_order=("Doom Siren", "Terrifying Crescendo"),
        result_id="localized-display-name-sequencing-result",
    )
    renamed_records = tuple(
        replace(
            record,
            definition=replace(record.definition, name="Sirène du destin localisée"),
        )
        if record.definition.name == "Doom Siren"
        else record
        for record in indexes["player-a"].all_records()
    )
    renamed_indexes = {
        **indexes,
        "player-a": AbilityCatalogIndex.from_records(renamed_records),
    }
    renamed_groups = _post_shoot_hit_target_effect_groups(
        ability_indexes_by_player_id=renamed_indexes,
        armies=armies,
        context=context,
    )
    renamed_doom_group = next(
        group
        for group in renamed_groups
        if group.record.definition.name == "Sirène du destin localisée"
    )
    stable_identity = post_shoot_group_stable_identity_payload(renamed_doom_group)
    assert set(stable_identity) == {
        "attack_sequence_completed_event_id",
        "attack_sequence_id",
        "catalog_record_id",
        "source_rule_id",
        "source_unit_instance_id",
        "source_model_instance_id",
        "selection_clause_id",
        "effect_clause_ids",
    }
    participant_payload = post_shoot_group_participant_payload(renamed_doom_group)
    assert participant_payload["ability_name"] == "Sirène du destin localisée"
    assert participant_payload["target_option_ids"] == [
        option.option_id for option in renamed_doom_group.options
    ]
    assert (
        post_shoot_group_participant_id(renamed_doom_group)
        == (original_participant_id_by_record[renamed_doom_group.record.record_id])
    )

    renamed_runtime = CatalogSelectedTargetEffectRuntime(renamed_indexes, armies)
    assert renamed_runtime.post_shoot_hit_target_request(context) is not None
    selected_request = decisions.queue.peek_next()
    selected_payload = cast(dict[str, Any], selected_request.payload)
    assert selected_payload["ability_name"] == "Sirène du destin localisée"
    assert selected_payload["catalog_record_id"] == renamed_doom_group.record.record_id


@pytest.mark.parametrize("lethal_continuation", [False, True])
def test_lord_kakophonist_doom_siren_resumes_after_feel_no_pain_choice(
    lethal_continuation: bool,
) -> None:
    armies, state, indexes, source_noise_marines, target, attached_id = (
        _kakophonist_runtime_fixture()
    )
    if lethal_continuation:
        state.game_id = "kakophonist-doom-siren-lethal-fnp-continuation"
    source_a = FeelNoPainSource(source_id="doom-siren-fnp-a", threshold=5)
    source_b = FeelNoPainSource(source_id="doom-siren-fnp-b", threshold=6)
    feel_no_pain_model_id = (
        _leave_one_wound_on_unit(state=state, unit=target)
        if lethal_continuation
        else target.own_models[0].model_instance_id
    )
    state.record_model_feel_no_pain_sources(
        model_instance_id=feel_no_pain_model_id,
        sources=(source_a, source_b),
    )
    decisions = DecisionController()
    runtime = CatalogSelectedTargetEffectRuntime(indexes, armies)
    battle_shock_hooks = BattleShockHookRegistry.from_bindings(
        catalog_battle_shock_hook_bindings(
            ability_indexes_by_player_id=indexes,
            armies=armies,
        )
    )
    sequence = AttackSequence(
        sequence_id="kakophonist-doom-siren-fnp",
        attacker_player_id="player-a",
        attacking_unit_instance_id=attached_id,
        source_phase=BattlePhase.SHOOTING,
        attack_pools=(
            _attack_pool(
                source_noise_marines,
                target,
                _weapon_profile("000004088", "Sonic blaster"),
            ),
        ),
    )
    decisions.event_log.append(
        "attack_sequence_step",
        {
            "sequence_id": sequence.sequence_id,
            "step": AttackSequenceStep.HIT.value,
            "pool_index": 0,
            "payload": {"successful": True},
        },
    )
    context = AttackSequenceCompletedContext(
        state=state,
        decisions=decisions,
        dice_manager=DiceRollManager(state.game_id, event_log=decisions.event_log),
        runtime_modifier_registry=RuntimeModifierRegistry.empty(),
        source_phase=BattlePhase.SHOOTING,
        attack_sequence=sequence,
        attack_sequence_completed_event_id="kakophonist-doom-siren-fnp-completed",
    )

    status: LifecycleStatus | None = None
    while runtime.post_shoot_hit_target_request(context) is not None:
        request = decisions.queue.peek_next()
        if request.decision_type == SEQUENCING_DECISION_TYPE:
            _submit_post_shoot_sequencing_order(
                decisions=decisions,
                request=request,
                ability_order=("Doom Siren", "Terrifying Crescendo"),
                result_id="doom-siren-fnp-sequencing-result",
            )
            continue
        request_payload = cast(dict[str, Any], request.payload)
        result = DecisionResult.for_request(
            result_id=f"doom-siren-fnp-{request_payload['ability_name']}",
            request=request,
            selected_option_id=request.options[0].option_id,
        )
        decisions.submit_result(result)
        status = apply_catalog_post_shoot_hit_target_effect_result(
            state=state,
            decisions=decisions,
            result=result,
            battle_shock_hooks=battle_shock_hooks,
            runtime_modifier_registry=RuntimeModifierRegistry.empty(),
            ability_indexes_by_player_id=indexes,
        )
        if status is not None:
            break

    assert status is not None
    assert status.status_kind is LifecycleStatusKind.WAITING_FOR_DECISION
    continuation_registry = MortalWoundFeelNoPainContinuationHookRegistry.from_bindings(
        catalog_selected_target_mortal_wound_feel_no_pain_bindings(
            ability_indexes_by_player_id=indexes,
        )
    )
    while status is not None:
        fnp_request = cast(DecisionRequest, status.decision_request)
        assert is_mortal_wound_feel_no_pain_request(fnp_request)
        source_context = mortal_wound_feel_no_pain_source_context(fnp_request)
        fnp_result = DecisionResult.for_request(
            result_id=f"doom-siren-fnp-result-{fnp_request.request_id}",
            request=fnp_request,
            selected_option_id=source_a.source_id,
        )
        decisions.submit_result(fnp_result)
        status = continuation_registry.apply_decision(
            MortalWoundFeelNoPainContinuationContext(
                state=state,
                decisions=decisions,
                request=fnp_request,
                result=fnp_result,
                source_context=source_context,
                dice_manager=DiceRollManager(
                    state.game_id,
                    event_log=decisions.event_log,
                ),
                runtime_modifier_registry=RuntimeModifierRegistry.empty(),
                battle_shock_hooks=battle_shock_hooks,
                ability_indexes_by_player_id=indexes,
            )
        )

    assert any(
        event.event_type == CATALOG_SELECTED_TARGET_MORTAL_WOUNDS_RESOLVED_EVENT
        for event in decisions.event_log.records
    )
    expected_battle_shock_event = (
        "catalog_selected_target_battle_shock_skipped"
        if lethal_continuation
        else "catalog_selected_target_battle_shock_resolved"
    )
    assert any(
        event.event_type == expected_battle_shock_event for event in decisions.event_log.records
    )
    if lethal_continuation:
        assert target.unit_instance_id not in state.battle_shocked_unit_ids
        assert runtime.post_shoot_hit_target_request(context) is None
        assert (
            GameState.from_payload(
                cast(GameStatePayload, json.loads(json.dumps(state.to_payload(), sort_keys=True)))
            ).to_payload()
            == state.to_payload()
        )
        assert (
            DecisionController.from_payload(
                cast(
                    DecisionControllerPayload,
                    json.loads(json.dumps(decisions.to_payload(), sort_keys=True)),
                )
            ).to_payload()
            == decisions.to_payload()
        )
        return
    next_status = runtime.post_shoot_hit_target_request(context)
    assert next_status is not None
    crescendo_request = decisions.queue.peek_next()
    crescendo_payload = cast(dict[str, Any], crescendo_request.payload)
    assert crescendo_payload["ability_name"] == "Terrifying Crescendo"
    crescendo_result = DecisionResult.for_request(
        result_id="doom-siren-fnp-terrifying-crescendo-result",
        request=crescendo_request,
        selected_option_id=crescendo_request.options[0].option_id,
    )
    decisions.submit_result(crescendo_result)
    assert (
        apply_catalog_post_shoot_hit_target_effect_result(
            state=state,
            decisions=decisions,
            result=crescendo_result,
            battle_shock_hooks=battle_shock_hooks,
            runtime_modifier_registry=RuntimeModifierRegistry.empty(),
            ability_indexes_by_player_id=indexes,
        )
        is None
    )
    assert runtime.post_shoot_hit_target_request(context) is None
    assert (
        GameState.from_payload(
            cast(GameStatePayload, json.loads(json.dumps(state.to_payload(), sort_keys=True)))
        ).to_payload()
        == state.to_payload()
    )
    assert (
        DecisionController.from_payload(
            cast(
                DecisionControllerPayload,
                json.loads(json.dumps(decisions.to_payload(), sort_keys=True)),
            )
        ).to_payload()
        == decisions.to_payload()
    )


def test_lord_kakophonist_doom_siren_targets_intact_attached_rules_unit() -> None:
    (
        armies,
        state,
        indexes,
        source_noise_marines,
        target_noise_marines,
        target_lord,
        source_attached_id,
        target_attached_id,
    ) = _kakophonist_attached_target_runtime_fixture()
    state.game_id = "kakophonist-attached-0"
    decisions = DecisionController()
    runtime = CatalogSelectedTargetEffectRuntime(indexes, armies)
    battle_shock_hooks = BattleShockHookRegistry.from_bindings(
        catalog_battle_shock_hook_bindings(
            ability_indexes_by_player_id=indexes,
            armies=armies,
        )
    )

    resolved_names = _resolve_kakophonist_post_shoot_effects(
        runtime=runtime,
        state=state,
        decisions=decisions,
        indexes=indexes,
        source_noise_marines=source_noise_marines,
        source_rules_unit_id=source_attached_id,
        target=target_noise_marines,
        target_rules_unit_id=target_attached_id,
        sequence_suffix="intact-attached-target",
        battle_shock_hooks=battle_shock_hooks,
        ability_order=("Doom Siren", "Terrifying Crescendo"),
    )

    assert resolved_names == ("Doom Siren", "Terrifying Crescendo")
    resolved_payload = cast(
        dict[str, Any],
        next(
            event.payload
            for event in decisions.event_log.records
            if event.event_type == "catalog_selected_target_battle_shock_resolved"
        ),
    )
    battle_shock_result = cast(dict[str, Any], resolved_payload["battle_shock_result"])
    request_payload = cast(dict[str, Any], battle_shock_result["request"])
    assert request_payload["unit_instance_id"] == target_attached_id
    assert request_payload["below_half_strength_context"]["starting_model_count"] == (
        len(target_noise_marines.own_models) + len(target_lord.own_models)
    )
    assert resolved_payload["target_identity_resolution"] == "unchanged"
    assert (
        GameState.from_payload(
            cast(GameStatePayload, json.loads(json.dumps(state.to_payload(), sort_keys=True)))
        ).to_payload()
        == state.to_payload()
    )


def test_attached_battle_shock_state_transfers_to_split_survivor() -> None:
    (
        _armies,
        state,
        _indexes,
        _source_noise_marines,
        target_noise_marines,
        target_lord,
        _source_attached_id,
        target_attached_id,
    ) = _kakophonist_attached_target_runtime_fixture()
    rules_unit = rules_unit_view_by_id(
        state=state,
        unit_instance_id=target_attached_id,
    )
    current_model_ids = tuple(model.model_instance_id for model in rules_unit.alive_models())
    below_half_context = BelowHalfStrengthContext.from_rules_unit(
        rules_unit=rules_unit,
        starting_strength=state.starting_strength_record_for_unit(target_attached_id),
        current_model_ids=current_model_ids,
    )
    request = BattleShockTestRequest.for_unit(
        request_id="attached-battle-shock-before-split",
        game_id=state.game_id,
        battle_round=state.battle_round,
        player_id="player-b",
        unit_instance_id=target_attached_id,
        reason=BattleShockTestReason.FORCED_BY_ARMY_RULE,
        leadership_target=6,
        below_half_strength_context=below_half_context,
    )
    failed = BattleShockResult.from_roll_state(
        result_id="attached-battle-shock-before-split-result",
        request=request,
        roll_state=DiceRollManager(state.game_id).roll_fixed(request.spec, (1, 1)),
    )
    state.record_battle_shock_result(failed)
    assert state.battle_shocked_unit_ids == [target_attached_id]

    for model in target_noise_marines.own_models:
        destroy_model_by_rule(state=state, model_instance_id=model.model_instance_id)
    state.recover_starting_strength_after_attached_unit_split(
        player_id="player-b",
        attached_unit_instance_id=target_attached_id,
        surviving_unit_instance_ids=(target_lord.unit_instance_id,),
        event_log=DecisionController().event_log,
    )

    assert state.battle_shocked_unit_ids == [target_lord.unit_instance_id]
    assert [record.unit_instance_id for record in state.battle_shocked_unit_states] == [
        target_lord.unit_instance_id
    ]
    assert state.battle_shocked_unit_states[0].model_instance_ids == (
        target_lord.own_models[0].model_instance_id,
    )
    assert (
        GameState.from_payload(
            cast(GameStatePayload, json.loads(json.dumps(state.to_payload(), sort_keys=True)))
        ).to_payload()
        == state.to_payload()
    )
    assert state.clear_battle_shock_for_player("player-b") == (target_lord.unit_instance_id,)


def test_lord_kakophonist_doom_siren_resolves_stale_attached_target_to_survivor() -> None:
    (
        armies,
        state,
        indexes,
        source_noise_marines,
        target_noise_marines,
        target_lord,
        source_attached_id,
        target_attached_id,
    ) = _kakophonist_attached_target_runtime_fixture()
    state.game_id = "kakophonist-split-target-0"
    decisions = DecisionController()
    for model in target_noise_marines.own_models:
        destroy_model_by_rule(state=state, model_instance_id=model.model_instance_id)
    state.recover_starting_strength_after_attached_unit_split(
        player_id="player-b",
        attached_unit_instance_id=target_attached_id,
        surviving_unit_instance_ids=(target_lord.unit_instance_id,),
        event_log=decisions.event_log,
    )
    runtime = CatalogSelectedTargetEffectRuntime(indexes, armies)
    battle_shock_hooks = BattleShockHookRegistry.from_bindings(
        catalog_battle_shock_hook_bindings(
            ability_indexes_by_player_id=indexes,
            armies=armies,
        )
    )

    resolved_names = _resolve_kakophonist_post_shoot_effects(
        runtime=runtime,
        state=state,
        decisions=decisions,
        indexes=indexes,
        source_noise_marines=source_noise_marines,
        source_rules_unit_id=source_attached_id,
        target=target_noise_marines,
        target_rules_unit_id=target_attached_id,
        sequence_suffix="split-attached-target",
        battle_shock_hooks=battle_shock_hooks,
        ability_order=("Doom Siren", "Terrifying Crescendo"),
    )

    assert resolved_names == ("Doom Siren", "Terrifying Crescendo")
    resolved_payload = cast(
        dict[str, Any],
        next(
            event.payload
            for event in decisions.event_log.records
            if event.event_type == "catalog_selected_target_battle_shock_resolved"
        ),
    )
    result_payload = cast(dict[str, Any], resolved_payload["battle_shock_result"])
    request_payload = cast(dict[str, Any], result_payload["request"])
    assert resolved_payload["selected_target_unit_instance_id"] == target_lord.unit_instance_id
    assert resolved_payload["target_unit_instance_id"] == target_lord.unit_instance_id
    assert resolved_payload["target_identity_resolution"] == "unchanged"
    assert request_payload["unit_instance_id"] == target_lord.unit_instance_id
    assert target_attached_id not in state.battle_shocked_unit_ids
    assert (
        GameState.from_payload(
            cast(GameStatePayload, json.loads(json.dumps(state.to_payload(), sort_keys=True)))
        ).to_payload()
        == state.to_payload()
    )


def test_lord_kakophonist_doom_siren_skips_battle_shock_when_target_is_destroyed() -> None:
    armies, state, indexes, source_noise_marines, target, attached_id = (
        _kakophonist_runtime_fixture()
    )
    _leave_one_wound_on_unit(state=state, unit=target)
    decisions = DecisionController()
    runtime = CatalogSelectedTargetEffectRuntime(indexes, armies)
    battle_shock_hooks = BattleShockHookRegistry.from_bindings(
        catalog_battle_shock_hook_bindings(
            ability_indexes_by_player_id=indexes,
            armies=armies,
        )
    )

    resolved_names = _resolve_kakophonist_post_shoot_effects(
        runtime=runtime,
        state=state,
        decisions=decisions,
        indexes=indexes,
        source_noise_marines=source_noise_marines,
        source_rules_unit_id=attached_id,
        target=target,
        sequence_suffix="destroyed-target",
        battle_shock_hooks=battle_shock_hooks,
        ability_order=("Doom Siren", "Terrifying Crescendo"),
    )

    assert resolved_names == ("Doom Siren",)
    skipped_payload = cast(
        dict[str, Any],
        next(
            event.payload
            for event in decisions.event_log.records
            if event.event_type == "catalog_selected_target_battle_shock_skipped"
        ),
    )
    assert skipped_payload["skip_reason"] == "no_surviving_target_models"
    assert skipped_payload["battle_shock_result"] is None
    assert target.unit_instance_id not in state.battle_shocked_unit_ids
    assert not any(
        event.event_type == "catalog_selected_target_battle_shock_resolved"
        for event in decisions.event_log.records
    )
    assert (
        DecisionController.from_payload(
            cast(
                DecisionControllerPayload,
                json.loads(json.dumps(decisions.to_payload(), sort_keys=True)),
            )
        ).to_payload()
        == decisions.to_payload()
    )


def test_lord_kakophonist_and_noise_marines_alternative_loadouts_instantiate() -> None:
    package = _catalog_package()
    factory = UnitFactory(
        catalog=package.army_catalog,
        model_geometries=package.model_geometries,
    )
    lord_datasheet = package.army_catalog.datasheet_by_id("000004084")
    lord_option = next(
        option
        for option in lord_datasheet.wargear_options
        if "screamer-pistol-close-combat-weapon" in option.option_id
    )
    lord = factory.instantiate_unit(
        army_id="army-loadout",
        datasheet=lord_datasheet,
        selection=UnitMusterSelection(
            unit_selection_id="lord-kakophonist-alternative",
            datasheet_id=lord_datasheet.datasheet_id,
            model_profile_selections=(
                ModelProfileSelection(lord_datasheet.model_profiles[0].model_profile_id, 1),
            ),
            wargear_selections=(
                WargearSelection(
                    option_id=lord_option.option_id,
                    model_profile_id=lord_option.model_profile_id,
                    wargear_ids=lord_option.allowed_wargear_ids,
                ),
            ),
        ),
    )
    assert {
        "000004084:screamer-pistol",
        "000004084:close-combat-weapon",
    }.issubset(lord.own_models[0].wargear_ids)
    assert "000004084:power-sword" not in lord.own_models[0].wargear_ids

    noise_datasheet = package.army_catalog.datasheet_by_id("000004088")
    disharmonist_option = next(
        option
        for option in noise_datasheet.wargear_options
        if "screamer-pistol-power-sword" in option.option_id
    )
    blastmaster_option = next(
        option
        for option in noise_datasheet.wargear_options
        if "sonic-blaster-blastmaster" in option.option_id
    )
    noise_marines = factory.instantiate_unit(
        army_id="army-loadout",
        datasheet=noise_datasheet,
        selection=UnitMusterSelection(
            unit_selection_id="noise-marines-alternative",
            datasheet_id=noise_datasheet.datasheet_id,
            model_profile_selections=tuple(
                ModelProfileSelection(entry.model_profile_id, entry.min_models)
                for entry in noise_datasheet.composition
            ),
            wargear_selections=(
                WargearSelection(
                    option_id=disharmonist_option.option_id,
                    model_profile_id=disharmonist_option.model_profile_id,
                    wargear_ids=disharmonist_option.allowed_wargear_ids,
                ),
                WargearSelection(
                    option_id=blastmaster_option.option_id,
                    model_profile_id=blastmaster_option.model_profile_id,
                    wargear_ids=blastmaster_option.allowed_wargear_ids,
                    selection_count=2,
                ),
            ),
        ),
    )
    disharmonist = next(model for model in noise_marines.own_models if model.name == "Disharmonist")
    assert {
        "000004088:screamer-pistol",
        "000004088:power-sword",
    }.issubset(disharmonist.wargear_ids)
    assert "000004088:sonic-blaster" not in disharmonist.wargear_ids
    assert (
        sum("000004088:blastmaster" in model.wargear_ids for model in noise_marines.own_models) == 2
    )


def test_fulgrim_generated_rule_ir_and_catalog_are_complete_and_source_bound() -> None:
    committed = cast(
        dict[str, Any],
        json.loads(FULGRIM_RULE_IR_OUTPUT_PATH.read_text(encoding="utf-8")),
    )

    assert committed == generated_fulgrim_rule_ir_artifact_payload()
    assert fulgrim_source_package.supported_datasheet_source_row_ids() == tuple(
        f"{_FULGRIM_ID}:{line}" for line in range(4, 10)
    )
    assert committed["package_hash"] == fulgrim_source_package.PACKAGE_HASH
    assert committed["official_document_pages"] == [8, 9]

    committed["package_hash"] = "0" * 64
    with pytest.raises(fulgrim_source_package.FulgrimRuleIrArtifactError, match="hash is stale"):
        fulgrim_source_package.validate_generated_artifact_bytes(json.dumps(committed).encode())

    package = _catalog_package()
    datasheet = package.army_catalog.datasheet_by_id(_FULGRIM_ID)
    characteristics = {
        value.characteristic: value.final for value in datasheet.model_profiles[0].characteristics
    }
    assert (
        characteristics[Characteristic.MOVEMENT],
        characteristics[Characteristic.TOUGHNESS],
        characteristics[Characteristic.SAVE],
        characteristics[Characteristic.WOUNDS],
        characteristics[Characteristic.LEADERSHIP],
        characteristics[Characteristic.OBJECTIVE_CONTROL],
        characteristics[Characteristic.INVULNERABLE_SAVE],
    ) == (16, 11, 2, 16, 5, 6, 4)
    assert datasheet.model_profiles[0].base_size.diameter_mm == 130.0
    geometry = next(
        record
        for record in package.model_geometries
        if record.model_profile_id == datasheet.model_profiles[0].model_profile_id
    )
    assert geometry.height.height_inches == 5.5
    assert {ability.name for ability in datasheet.abilities} == {
        "Beguiling Form",
        "Daemon Primarch of Slaanesh",
        "Daemonic Poisons",
        "Daemonic Speed",
        "Deadly Demise",
        "Deep Strike",
        "Enthralling Hypnosis (Aura)",
        "Serpentine",
        "SUPREME COMMANDER",
        "Thrill Seekers",
    }
    expected_consumers = {
        f"{_FULGRIM_ID}:4": {
            CATALOG_IR_POISONED_COMMAND_MORTAL_WOUNDS_CONSUMER_ID,
            CATALOG_IR_POST_FIGHT_HIT_TARGET_EFFECT_CONSUMER_ID,
            CATALOG_IR_POST_SHOOT_HIT_TARGET_EFFECT_CONSUMER_ID,
        },
        f"{_FULGRIM_ID}:5": {CATALOG_IR_COMMAND_PHASE_ABILITY_MODE_CONSUMER_ID},
        f"{_FULGRIM_ID}:6": {CATALOG_IR_MOVEMENT_TRANSIT_PERMISSION_CONSUMER_ID},
        f"{_FULGRIM_ID}:7": {CATALOG_IR_COMMAND_PHASE_ABILITY_MODE_CONSUMER_ID},
        f"{_FULGRIM_ID}:8": {CATALOG_IR_COMMAND_PHASE_ABILITY_MODE_CONSUMER_ID},
        f"{_FULGRIM_ID}:9": {CATALOG_IR_COMMAND_PHASE_ABILITY_MODE_CONSUMER_ID},
    }
    for source_row_id, consumer_ids in expected_consumers.items():
        assert set(catalog_rule_ir_consumers_for_rule(_fulgrim_rule_ir(source_row_id))) == (
            consumer_ids
        )


def test_infractors_tormentors_generated_rule_ir_and_catalog_are_complete() -> None:
    committed = cast(
        dict[str, Any],
        json.loads(INFRACTORS_TORMENTORS_RULE_IR_OUTPUT_PATH.read_text(encoding="utf-8")),
    )
    assert committed == generated_infractors_tormentors_rule_ir_artifact_payload()
    assert infractors_tormentors_source_package.supported_datasheet_source_row_ids() == (
        "000004079:3",
        "000004079:4",
        "000004080:3",
        "000004080:4",
    )
    assert committed["package_hash"] == infractors_tormentors_source_package.PACKAGE_HASH
    assert committed["official_document_pages"] == [9]

    committed["package_hash"] = "0" * 64
    with pytest.raises(
        infractors_tormentors_source_package.InfractorsTormentorsRuleIrArtifactError,
        match="hash is stale",
    ):
        infractors_tormentors_source_package.validate_generated_artifact_bytes(
            json.dumps(committed).encode()
        )

    package = _catalog_package()
    expected_consumers = {
        ("000004079", "Objective Defiled"): {CATALOG_IR_COMMAND_END_STICKY_OBJECTIVE_CONSUMER_ID},
        ("000004079", "Icon of Excess"): {CATALOG_IR_COMMAND_POINT_GAIN_CONSUMER_ID},
        ("000004080", "Excessive Assault"): {"catalog-ir:wound-roll-reroll"},
        ("000004080", "Icon of Excess"): {CATALOG_IR_COMMAND_POINT_GAIN_CONSUMER_ID},
    }
    records_by_identity: dict[tuple[str, str], list[Any]] = {}
    for record in catalog_ability_records_from_catalog(package.army_catalog):
        if record.datasheet_id is None:
            continue
        identity = (record.datasheet_id, record.definition.name)
        if identity in expected_consumers:
            records_by_identity.setdefault(identity, []).append(record)
    assert records_by_identity.keys() == expected_consumers.keys()
    assert len(records_by_identity[("000004079", "Icon of Excess")]) == 2
    assert len(records_by_identity[("000004080", "Icon of Excess")]) == 2
    for identity, records in records_by_identity.items():
        for record in records:
            rule_ir = rule_ir_from_execution_payload(record.definition.replay_payload)
            assert rule_ir.is_supported
            assert not rule_ir.diagnostics
            assert set(catalog_rule_ir_consumers_for_rule(rule_ir)) == expected_consumers[identity]

    for datasheet_id in ("000004079", "000004080"):
        datasheet = package.army_catalog.datasheet_by_id(datasheet_id)
        assert {(entry.min_models, entry.max_models) for entry in datasheet.composition} == {
            (1, 1),
            (4, 9),
        }
        for profile in datasheet.model_profiles:
            characteristics = {
                value.characteristic: value.final for value in profile.characteristics
            }
            assert (
                characteristics[Characteristic.MOVEMENT],
                characteristics[Characteristic.TOUGHNESS],
                characteristics[Characteristic.SAVE],
                characteristics[Characteristic.WOUNDS],
                characteristics[Characteristic.LEADERSHIP],
                characteristics[Characteristic.OBJECTIVE_CONTROL],
            ) == (7, 4, 3, 2, 6, 2)
            assert profile.base_size.diameter_mm is not None
            assert math.isclose(profile.base_size.diameter_mm, 32.0)
            geometry = next(
                record
                for record in package.model_geometries
                if record.model_profile_id == profile.model_profile_id
            )
            assert geometry.height.height_inches == 1.75
        icon_option = next(
            option for option in datasheet.wargear_options if "icon-of-excess" in option.option_id
        )
        assert icon_option.max_selections == 1
        assert icon_option.allowed_wargear_ids == (f"{datasheet_id}:icon-of-excess",)
        power_sword = _weapon_profile(datasheet_id, "Power sword")
        assert power_sword.strength.final == 5


def test_infractors_excessive_assault_grants_only_melee_wound_rerolls() -> None:
    armies, state, indexes, infractors, target = _battleline_runtime_fixture(
        source_datasheet_id="000004080",
        phase=BattlePhase.FIGHT,
        with_icon=False,
        game_id="infractors-excessive-assault",
    )
    runtime = CatalogDatasheetRuleRuntime(indexes, armies)

    def permission_for(phase: BattlePhase) -> SourceBackedRerollPermissionContext | None:
        context = AttackRerollPermissionContext(
            state=state,
            player_id="player-a",
            attacking_unit_instance_id=infractors.unit_instance_id,
            attacker_model_instance_id=infractors.own_models[0].model_instance_id,
            target_unit_instance_id=target.unit_instance_id,
            source_phase=phase,
            roll_type="attack_sequence.wound",
            timing_window="attack_sequence.wound",
        )
        return next(
            (
                resolved
                for binding in runtime.attack_reroll_permission_bindings()
                if (resolved := binding.handler(context)) is not None
            ),
            None,
        )

    permission = permission_for(BattlePhase.FIGHT)
    assert permission is not None
    assert permission.source_payload["conditional_wound_reroll"] == {
        "reroll_unmodified_values": [1],
        "full_reroll_if_target_within_objective_range": True,
    }
    assert permission_for(BattlePhase.SHOOTING) is None


@pytest.mark.parametrize(
    ("within_objective_range", "game_id", "expected_wound_value"),
    [
        (True, "phase18j-excessive-inside-0010", 4),
        (False, "phase18j-excessive-outside-0001", 1),
    ],
)
def test_infractors_excessive_assault_uses_fight_lifecycle_decision_and_replays(
    within_objective_range: bool,
    game_id: str,
    expected_wound_value: int,
) -> None:
    session, infractors, target = _battleline_lifecycle_session(
        source_datasheet_id="000004080",
        phase=BattlePhase.FIGHT,
        with_icon=False,
        game_id=game_id,
    )
    state = session.lifecycle.state
    assert state is not None
    marker = state.mission_setup.objective_markers[0] if state.mission_setup else None
    assert marker is not None
    if within_objective_range:
        _move_unit(state, target.unit_instance_id, x=marker.x_inches, y=marker.y_inches)
        _move_unit(
            state,
            infractors.unit_instance_id,
            x=marker.x_inches - 2.0,
            y=marker.y_inches,
        )
    else:
        _move_unit(state, target.unit_instance_id, x=12.0, y=10.0)
        _move_unit(state, infractors.unit_instance_id, x=10.0, y=10.0)
    status = session.advance_until_decision_or_terminal()
    status = _advance_battleline_fight_to_source_reroll(
        session=session,
        source=infractors,
        status=status,
    )
    request = _decision_request(status)
    payload = cast(dict[str, JsonValue], request.payload)

    assert request.decision_type == DICE_REROLL_DECISION_TYPE
    assert payload["current_values"] == [expected_wound_value]
    assert (expected_wound_value != 1) is within_objective_range
    assert cast(dict[str, JsonValue], payload["attack_context"])["unit_instance_id"] == (
        infractors.unit_instance_id
    )
    source_payload = cast(
        dict[str, JsonValue],
        cast(dict[str, JsonValue], payload["attack_context"])["source_payload"],
    )
    assert source_payload["conditional_wound_reroll"] == {
        "reroll_unmodified_values": [1],
        "full_reroll_if_target_within_objective_range": True,
    }
    initial_lifecycle_payload = cast(
        GameLifecyclePayload,
        json.loads(json.dumps(session.lifecycle.to_payload(), sort_keys=True)),
    )
    reroll_option = next(option for option in request.options if option.option_id != "decline")
    submitted = session.submit_option(
        request_id=request.request_id,
        option_id=reroll_option.option_id,
        result_id="infractors-excessive-assault-reroll",
    )
    assert submitted.status_kind is LifecycleStatusKind.WAITING_FOR_DECISION
    assert session.lifecycle.decision_controller.records[-1].request.decision_type == (
        DICE_REROLL_DECISION_TYPE
    )
    replay_payload = cast(
        ReplayArtifactPayload,
        json.loads(
            json.dumps(
                ReplayArtifact.capture(
                    artifact_id=game_id,
                    initial_lifecycle_payload=initial_lifecycle_payload,
                    final_lifecycle=session.lifecycle,
                ).to_payload(),
                sort_keys=True,
            )
        ),
    )
    replay_result = ReplayRunner.from_payload(replay_payload).run()
    assert replay_result.reproduced_exactly, replay_result.to_payload()


def test_infractors_excessive_assault_does_not_enter_ranged_reroll_path() -> None:
    session, infractors, target = _battleline_lifecycle_session(
        source_datasheet_id="000004080",
        phase=BattlePhase.SHOOTING,
        with_icon=False,
        game_id="infractors-excessive-assault-ranged-lifecycle",
    )
    state = session.lifecycle.state
    assert state is not None
    _move_unit(state, infractors.unit_instance_id, x=10.0, y=10.0)
    _move_unit(state, target.unit_instance_id, x=18.0, y=10.0)

    status = _advance_battleline_shooting_to_damage_allocation_request(
        session=session,
        source=infractors,
        target=target,
        status=session.advance_until_decision_or_terminal(),
        weapon_name="Bolt pistol",
    )

    assert _decision_request(status).decision_type == SELECT_DAMAGE_ALLOCATION_MODEL_DECISION_TYPE
    assert not any(
        record.request.decision_type == DICE_REROLL_DECISION_TYPE
        and isinstance(record.request.payload, dict)
        and record.request.payload.get("source_rule_id") is not None
        for record in session.lifecycle.decision_controller.records
    )


def test_icon_of_excess_requires_enemy_destruction_then_resolves_unit_leadership() -> None:
    armies, state, indexes, tormentors, target = _battleline_runtime_fixture(
        source_datasheet_id="000004079",
        phase=BattlePhase.SHOOTING,
        with_icon=True,
        game_id="icon-of-excess-pass-1",
    )
    decisions = DecisionController()
    runtime = CatalogCommandPointRuntime(indexes, armies)
    event_index = RuntimeContentEventIndex.from_subscriptions(
        runtime.event_subscriptions(),
        handler_registry=RuntimeContentEventHandlerRegistry.from_bindings(
            runtime.event_handler_bindings()
        ),
    )

    def dispatch(event_id: str) -> tuple[Any, ...]:
        return event_index.dispatch(
            RuntimeContentEvent(
                event_id=event_id,
                game_id=state.game_id,
                player_id="player-a",
                battle_round=state.battle_round,
                trigger_kind=TimingTriggerKind.END_PHASE,
                phase=BattlePhaseKind.SHOOTING,
                active_player_id="player-a",
            ),
            state=state,
            decisions=decisions,
            ruleset_descriptor=RulesetDescriptor.warhammer_40000_eleventh(),
            army_catalog=_catalog_package().army_catalog,
            runtime_modifier_registry=RuntimeModifierRegistry.empty(),
        )

    assert len(dispatch("runtime-event:icon-of-excess:no-destruction")) == 1
    assert not any(
        record.event_type == CATALOG_IR_COMMAND_POINT_LEADERSHIP_TEST_EVENT
        for record in decisions.event_log.records
    )
    assert state.command_point_total("player-a") == 0

    for model in target.own_models:
        destroy_model_by_rule(state=state, model_instance_id=model.model_instance_id)
        decisions.event_log.append(
            "model_destroyed",
            {
                "game_id": state.game_id,
                "battle_round": state.battle_round,
                "active_player_id": "player-a",
                "phase": BattlePhase.SHOOTING.value,
                **ModelDestructionAttribution.for_attack(
                    destroying_player_id="player-a",
                    attacking_unit_instance_id=tormentors.unit_instance_id,
                    attacking_model_instance_id=(tormentors.own_models[0].model_instance_id),
                    weapon_profile=_weapon_profile("000004079", "Bolt pistol"),
                    attack_context_id="attack-context:icon-of-excess",
                ).to_payload(),
                "target_unit_instance_id": target.unit_instance_id,
                "model_instance_id": model.model_instance_id,
            },
        )
    results = dispatch("runtime-event:icon-of-excess:shooting-end")

    assert len(results) == 1
    leadership_event = next(
        record
        for record in decisions.event_log.records
        if record.event_type == CATALOG_IR_COMMAND_POINT_LEADERSHIP_TEST_EVENT
    )
    payload = cast(dict[str, JsonValue], leadership_event.payload)
    assert payload["source_unit_instance_id"] == tormentors.unit_instance_id
    assert payload["leadership_target"] == 6
    assert payload["passed"] is True
    assert state.command_point_total("player-a") == 1


@pytest.mark.parametrize(
    (
        "game_id",
        "prefill_non_command_cap",
        "expected_passed",
        "expected_gain_status",
    ),
    [
        ("icon-lifecycle-outcome-0", False, True, "applied"),
        ("icon-lifecycle-outcome-5", False, False, None),
        ("icon-cap-outcome-0", True, True, "capped"),
    ],
)
def test_icon_of_excess_uses_shooting_lifecycle_destruction_and_replays(
    game_id: str,
    prefill_non_command_cap: bool,
    expected_passed: bool,
    expected_gain_status: str | None,
) -> None:
    session, tormentors, target = _battleline_lifecycle_session(
        source_datasheet_id="000004079",
        phase=BattlePhase.SHOOTING,
        with_icon=True,
        game_id=game_id,
    )
    state = session.lifecycle.state
    assert state is not None
    if prefill_non_command_cap:
        state.gain_command_points(
            player_id="player-a",
            amount=1,
            source_id="test:icon-of-excess:prior-non-command-gain",
            source_kind=CommandPointSourceKind.OTHER,
        )
    _move_unit(state, tormentors.unit_instance_id, x=10.0, y=10.0)
    _move_unit(state, target.unit_instance_id, x=18.0, y=10.0)
    status = _advance_battleline_shooting_to_damage_allocation_request(
        session=session,
        source=tormentors,
        target=target,
        status=session.advance_until_decision_or_terminal(),
    )
    request = _decision_request(status)
    assert request.decision_type == SELECT_DAMAGE_ALLOCATION_MODEL_DECISION_TYPE
    initial_lifecycle_payload = cast(
        GameLifecyclePayload,
        json.loads(json.dumps(session.lifecycle.to_payload(), sort_keys=True)),
    )

    submitted = session.submit_option(
        request_id=request.request_id,
        option_id=request.options[0].option_id,
        result_id="icon-of-excess-damage-allocation",
    )
    assert submitted.status_kind is LifecycleStatusKind.WAITING_FOR_DECISION
    assert state.current_battle_phase is not BattlePhase.SHOOTING
    destroyed_payloads = tuple(
        cast(dict[str, JsonValue], record.payload)
        for record in session.lifecycle.decision_controller.event_log.records
        if record.event_type == "model_destroyed"
    )
    assert len(destroyed_payloads) == len(target.own_models)
    for destroyed_payload in destroyed_payloads:
        attribution = ModelDestructionAttribution.from_model_destroyed_payload(destroyed_payload)
        assert attribution.source_rules_unit_instance_id == tormentors.unit_instance_id
        assert attribution.attacking_unit_instance_id == tormentors.unit_instance_id
        assert attribution.attacking_model_instance_id is not None
        assert (
            attribution.destruction_provenance.destruction_source_kind
            is DestructionSourceKind.ATTACK
        )
    leadership_events = tuple(
        cast(dict[str, JsonValue], record.payload)
        for record in session.lifecycle.decision_controller.event_log.records
        if record.event_type == CATALOG_IR_COMMAND_POINT_LEADERSHIP_TEST_EVENT
    )
    assert len(leadership_events) == 1
    assert leadership_events[0]["source_unit_instance_id"] == tormentors.unit_instance_id
    assert leadership_events[0]["leadership_target"] == 6
    assert leadership_events[0]["passed"] is expected_passed
    command_point_result_value = leadership_events[0]["command_point_result"]
    if expected_gain_status is None:
        assert command_point_result_value is None
    else:
        command_point_result = cast(dict[str, JsonValue], command_point_result_value)
        assert command_point_result["status"] == expected_gain_status
        assert command_point_result["applied_amount"] == int(expected_gain_status == "applied")
    replay_payload = cast(
        ReplayArtifactPayload,
        json.loads(
            json.dumps(
                ReplayArtifact.capture(
                    artifact_id=game_id,
                    initial_lifecycle_payload=initial_lifecycle_payload,
                    final_lifecycle=session.lifecycle,
                ).to_payload(),
                sort_keys=True,
            )
        ),
    )
    replay_result = ReplayRunner.from_payload(replay_payload).run()
    assert replay_result.reproduced_exactly, replay_result.to_payload()


def test_icon_of_excess_uses_fight_lifecycle_destruction_and_replays() -> None:
    game_id = "icon-of-excess-fight-lifecycle"
    session, tormentors, target = _battleline_lifecycle_session(
        source_datasheet_id="000004079",
        phase=BattlePhase.FIGHT,
        with_icon=True,
        game_id=game_id,
        single_source_model=True,
        single_target_model=True,
    )
    state = session.lifecycle.state
    assert state is not None
    _move_unit(state, tormentors.unit_instance_id, x=10.0, y=10.0)
    _move_unit(state, target.unit_instance_id, x=12.0, y=10.0)
    status = _advance_battleline_fight_through_phase(
        session=session,
        source=tormentors,
        status=session.advance_until_decision_or_terminal(),
        stop_at_movement_proposal_kind="consolidate",
    )
    pending_consolidation = MovementProposalRequest.from_decision_request_payload(
        _decision_request(status).payload
    )
    assert pending_consolidation.proposal_kind.value == "consolidate"
    initial_lifecycle_payload = cast(
        GameLifecyclePayload,
        json.loads(json.dumps(session.lifecycle.to_payload(), sort_keys=True)),
    )

    status = _advance_battleline_fight_through_phase(
        session=session,
        source=tormentors,
        status=status,
    )

    assert state.current_battle_phase is not BattlePhase.FIGHT
    destroyed_payloads = tuple(
        cast(dict[str, JsonValue], record.payload)
        for record in session.lifecycle.decision_controller.event_log.records
        if record.event_type == "model_destroyed"
    )
    assert destroyed_payloads
    for destroyed_payload in destroyed_payloads:
        attribution = ModelDestructionAttribution.from_model_destroyed_payload(destroyed_payload)
        assert (
            attribution.destruction_provenance.destruction_source_kind
            is DestructionSourceKind.ATTACK
        )
        assert attribution.source_rules_unit_instance_id == tormentors.unit_instance_id
    leadership_events = tuple(
        record
        for record in session.lifecycle.decision_controller.event_log.records
        if record.event_type == CATALOG_IR_COMMAND_POINT_LEADERSHIP_TEST_EVENT
    )
    assert len(leadership_events) == 1
    replay_payload = cast(
        ReplayArtifactPayload,
        json.loads(
            json.dumps(
                ReplayArtifact.capture(
                    artifact_id=game_id,
                    initial_lifecycle_payload=initial_lifecycle_payload,
                    final_lifecycle=session.lifecycle,
                ).to_payload(),
                sort_keys=True,
            )
        ),
    )
    replay_result = ReplayRunner.from_payload(replay_payload).run()
    assert replay_result.reproduced_exactly, replay_result.to_payload()


def test_icon_of_excess_uses_attached_rules_unit_identity_and_leadership() -> None:
    game_id = "icon-of-excess-attached-lifecycle"
    session, tormentors, target = _battleline_lifecycle_session(
        source_datasheet_id="000004079",
        phase=BattlePhase.SHOOTING,
        with_icon=True,
        game_id=game_id,
        attached_source=True,
        extra_target=True,
    )
    state = session.lifecycle.state
    assert state is not None
    attached_view = rules_unit_view_by_id(
        state=state,
        unit_instance_id=tormentors.unit_instance_id,
    )
    assert attached_view.is_attached_rules_unit
    leader = next(
        component.unit for component in attached_view.components if component.role == "leader"
    )
    extra_target = next(
        unit
        for army in state.army_definitions
        if army.player_id == "player-b"
        for unit in army.units
        if unit.unit_instance_id == "army-b:extra-target-battleline"
    )
    _move_unit(state, tormentors.unit_instance_id, x=10.0, y=10.0)
    _move_unit(state, leader.unit_instance_id, x=9.0, y=10.0)
    _move_unit(state, target.unit_instance_id, x=18.0, y=10.0)
    _move_unit(state, extra_target.unit_instance_id, x=20.0, y=10.0)
    status = _advance_battleline_shooting_to_damage_allocation_request(
        session=session,
        source=tormentors,
        target=target,
        status=session.advance_until_decision_or_terminal(),
    )
    request = _decision_request(status)
    initial_lifecycle_payload = cast(
        GameLifecyclePayload,
        json.loads(json.dumps(session.lifecycle.to_payload(), sort_keys=True)),
    )

    session.submit_option(
        request_id=request.request_id,
        option_id=request.options[0].option_id,
        result_id="icon-of-excess-attached-allocation",
    )

    destroyed_payloads = tuple(
        cast(dict[str, JsonValue], record.payload)
        for record in session.lifecycle.decision_controller.event_log.records
        if record.event_type == "model_destroyed"
    )
    assert destroyed_payloads
    for payload in destroyed_payloads:
        attribution = ModelDestructionAttribution.from_model_destroyed_payload(payload)
        assert attribution.source_rules_unit_instance_id == attached_view.unit_instance_id
    leadership_payload = next(
        cast(dict[str, JsonValue], record.payload)
        for record in session.lifecycle.decision_controller.event_log.records
        if record.event_type == CATALOG_IR_COMMAND_POINT_LEADERSHIP_TEST_EVENT
    )
    assert leadership_payload["source_unit_instance_id"] == tormentors.unit_instance_id
    assert leadership_payload["leadership_target"] == 5
    replay_payload = cast(
        ReplayArtifactPayload,
        json.loads(
            json.dumps(
                ReplayArtifact.capture(
                    artifact_id=game_id,
                    initial_lifecycle_payload=initial_lifecycle_payload,
                    final_lifecycle=session.lifecycle,
                ).to_payload(),
                sort_keys=True,
            )
        ),
    )
    replay_result = ReplayRunner.from_payload(replay_payload).run()
    assert replay_result.reproduced_exactly, replay_result.to_payload()


def test_icon_of_excess_ignores_rule_destruction_through_phase_end_lifecycle() -> None:
    game_id = "icon-of-excess-rule-destruction-lifecycle"
    session, _tormentors, target = _battleline_lifecycle_session(
        source_datasheet_id="000004079",
        phase=BattlePhase.SHOOTING,
        with_icon=True,
        game_id=game_id,
        extra_target=True,
    )
    state = session.lifecycle.state
    assert state is not None
    decisions = session.lifecycle.decision_controller
    for index, model in enumerate(target.own_models):
        liability_effect_id = f"test:icon-of-excess:unattributed-effect:{index}"
        state.record_persisting_effect(
            PersistingEffect(
                effect_id=liability_effect_id,
                source_rule_id="test:icon-of-excess:unattributed-ability",
                owner_player_id="player-a",
                target_unit_instance_ids=(target.unit_instance_id,),
                started_battle_round=state.battle_round,
                started_phase=BattlePhase.SHOOTING,
                expiration=EffectExpiration.end_phase(
                    battle_round=state.battle_round,
                    phase=BattlePhase.SHOOTING,
                    player_id="player-a",
                ),
                effect_payload={"effect_kind": "test_rule_destruction_liability"},
            )
        )
        destruction = rule_model_destruction.destroy_model_with_rule_reactions(
            state=state,
            decisions=decisions,
            model_instance_id=model.model_instance_id,
            rules_unit_instance_id=target.unit_instance_id,
            destroying_player_id="player-a",
            source_rule_id="test:icon-of-excess:unattributed-ability",
            source_effect_ids=(liability_effect_id,),
            source_phase=BattlePhase.SHOOTING,
            source_step="shooting_test_ability",
            source_result_id=f"test:icon-of-excess:unattributed-result:{index}",
            completion_event_type="test_icon_unattributed_destruction_completed",
            completion_event_payload={"destroyed_model_instance_id": model.model_instance_id},
        )
        assert destruction.status is None
    destroyed_payloads = tuple(
        cast(dict[str, JsonValue], record.payload)
        for record in decisions.event_log.records
        if record.event_type == "model_destroyed"
    )
    assert len(destroyed_payloads) == len(target.own_models)
    for payload in destroyed_payloads:
        attribution = ModelDestructionAttribution.from_model_destroyed_payload(payload)
        assert attribution.source_rules_unit_instance_id is None
        assert attribution.attacking_unit_instance_id is None
        assert attribution.attacking_model_instance_id is None
        assert (
            attribution.destruction_provenance.destruction_source_kind
            is DestructionSourceKind.ABILITY
        )
    status = session.advance_until_decision_or_terminal()

    assert status.status_kind in {
        LifecycleStatusKind.WAITING_FOR_DECISION,
        LifecycleStatusKind.TERMINAL,
    }
    assert not any(
        record.event_type == CATALOG_IR_COMMAND_POINT_LEADERSHIP_TEST_EVENT
        for record in decisions.event_log.records
    )


def test_icon_of_excess_matches_historical_attached_attack_identity_after_split() -> None:
    session, tormentors, target = _battleline_lifecycle_session(
        source_datasheet_id="000004079",
        phase=BattlePhase.SHOOTING,
        with_icon=True,
        game_id="icon-of-excess-attached-split",
        attached_source=True,
        extra_target=True,
    )
    state = session.lifecycle.state
    assert state is not None
    decisions = session.lifecycle.decision_controller
    attached_view = rules_unit_view_by_id(
        state=state,
        unit_instance_id=tormentors.unit_instance_id,
    )
    leader = next(
        component.unit for component in attached_view.components if component.role == "leader"
    )
    extra_target = next(
        unit
        for army in state.army_definitions
        if army.player_id == "player-b"
        for unit in army.units
        if unit.unit_instance_id == "army-b:extra-target-battleline"
    )
    _move_unit(state, tormentors.unit_instance_id, x=10.0, y=10.0)
    _move_unit(state, extra_target.unit_instance_id, x=20.0, y=10.0)
    for index, model in enumerate(target.own_models):
        destroy_model_by_rule(state=state, model_instance_id=model.model_instance_id)
        decisions.event_log.append(
            "model_destroyed",
            {
                "game_id": state.game_id,
                "battle_round": state.battle_round,
                "active_player_id": "player-a",
                "phase": BattlePhase.SHOOTING.value,
                **ModelDestructionAttribution.for_attack(
                    destroying_player_id="player-a",
                    attacking_unit_instance_id=attached_view.unit_instance_id,
                    attacking_model_instance_id=(tormentors.own_models[0].model_instance_id),
                    weapon_profile=_weapon_profile("000004079", "Boltgun"),
                    attack_context_id=f"attack-context:icon-attached-split:{index}",
                ).to_payload(),
                "target_unit_instance_id": target.unit_instance_id,
                "model_instance_id": model.model_instance_id,
            },
        )
    for model in leader.own_models:
        destroy_model_by_rule(state=state, model_instance_id=model.model_instance_id)
    state.recover_starting_strength_after_attached_unit_split(
        player_id="player-a",
        attached_unit_instance_id=attached_view.unit_instance_id,
        surviving_unit_instance_ids=(tormentors.unit_instance_id,),
        event_log=decisions.event_log,
    )
    assert (
        rules_unit_view_by_id(
            state=state,
            unit_instance_id=tormentors.unit_instance_id,
        ).unit_instance_id
        == tormentors.unit_instance_id
    )

    _advance_battleline_without_actions_to_phase(
        session=session,
        status=session.advance_until_decision_or_terminal(),
        target_phase=BattlePhase.CHARGE,
    )

    leadership_payload = next(
        cast(dict[str, JsonValue], record.payload)
        for record in decisions.event_log.records
        if record.event_type == CATALOG_IR_COMMAND_POINT_LEADERSHIP_TEST_EVENT
    )
    assert leadership_payload["source_unit_instance_id"] == tormentors.unit_instance_id
    assert leadership_payload["leadership_target"] == 6


@pytest.mark.parametrize(
    ("source_rules_unit_instance_id", "expected_leadership_tests"),
    [(None, 0), ("source", 1)],
)
def test_icon_of_excess_uses_typed_non_attack_source_attribution(
    source_rules_unit_instance_id: str | None,
    expected_leadership_tests: int,
) -> None:
    armies, state, indexes, tormentors, target = _battleline_runtime_fixture(
        source_datasheet_id="000004079",
        phase=BattlePhase.SHOOTING,
        with_icon=True,
        game_id=f"icon-of-excess-non-attack-{expected_leadership_tests}",
    )
    decisions = DecisionController()
    runtime = CatalogCommandPointRuntime(indexes, armies)
    event_index = RuntimeContentEventIndex.from_subscriptions(
        runtime.event_subscriptions(),
        handler_registry=RuntimeContentEventHandlerRegistry.from_bindings(
            runtime.event_handler_bindings()
        ),
    )
    attributed_source_id = (
        tormentors.unit_instance_id if source_rules_unit_instance_id == "source" else None
    )
    for model in target.own_models:
        destroy_model_by_rule(state=state, model_instance_id=model.model_instance_id)
        decisions.event_log.append(
            "model_destroyed",
            {
                "game_id": state.game_id,
                "battle_round": state.battle_round,
                "active_player_id": "player-a",
                "phase": BattlePhase.SHOOTING.value,
                **ModelDestructionAttribution.for_non_attack(
                    destroying_player_id="player-a",
                    source_kind=DestructionSourceKind.DEADLY_DEMISE,
                    source_rules_unit_instance_id=attributed_source_id,
                ).to_payload(),
                "target_unit_instance_id": target.unit_instance_id,
                "model_instance_id": model.model_instance_id,
            },
        )

    results = event_index.dispatch(
        RuntimeContentEvent(
            event_id=f"runtime-event:icon-of-excess:non-attack:{expected_leadership_tests}",
            game_id=state.game_id,
            player_id="player-a",
            battle_round=state.battle_round,
            trigger_kind=TimingTriggerKind.END_PHASE,
            phase=BattlePhaseKind.SHOOTING,
            active_player_id="player-a",
        ),
        state=state,
        decisions=decisions,
        ruleset_descriptor=RulesetDescriptor.warhammer_40000_eleventh(),
        army_catalog=_catalog_package().army_catalog,
        runtime_modifier_registry=RuntimeModifierRegistry.empty(),
    )

    assert len(results) == 1
    assert (
        sum(
            record.event_type == CATALOG_IR_COMMAND_POINT_LEADERSHIP_TEST_EVENT
            for record in decisions.event_log.records
        )
        == expected_leadership_tests
    )


def test_tormentors_objective_defiled_persists_and_expires_on_higher_control() -> None:
    armies, state, indexes, tormentors, target = _battleline_runtime_fixture(
        source_datasheet_id="000004079",
        phase=BattlePhase.COMMAND,
        with_icon=False,
        game_id="tormentors-objective-defiled",
    )
    marker = state.mission_setup.objective_markers[0] if state.mission_setup else None
    assert marker is not None
    _move_unit(state, tormentors.unit_instance_id, x=marker.x_inches, y=marker.y_inches)
    _move_unit(state, target.unit_instance_id, x=marker.x_inches + 20.0, y=marker.y_inches)
    bindings = phase_end_objective_control_hook_bindings(
        ability_indexes_by_player_id=indexes,
        armies=armies,
    )
    assert any(
        binding.hook_id.startswith(CATALOG_IR_COMMAND_END_STICKY_OBJECTIVE_CONSUMER_ID)
        for binding in bindings
    )
    states = PhaseEndObjectiveControlHookRegistry.from_bindings(bindings).states_for(
        PhaseEndObjectiveControlContext(
            state=state,
            event_log=DecisionController().event_log,
            completed_phase=BattlePhase.COMMAND,
            runtime_modifier_registry=RuntimeModifierRegistry.empty(),
        )
    )
    sticky = next(state for state in states if state.objective_id == marker.objective_marker_id)
    assert StickyObjectiveControlState.from_payload(sticky.to_payload()) == sticky
    state.record_sticky_objective_control_state(sticky)

    _move_unit(state, tormentors.unit_instance_id, x=marker.x_inches + 20.0, y=marker.y_inches)
    empty_record = resolve_objective_control(
        ObjectiveControlContext.from_game_state(
            state,
            timing=ObjectiveControlTiming.PHASE_END,
            phase=BattlePhase.COMMAND,
            ruleset_descriptor=state.runtime_ruleset_descriptor(),
            runtime_modifier_registry=RuntimeModifierRegistry.empty(),
        )
    )
    retained = apply_sticky_objective_control(record=empty_record, states=(sticky,))
    retained_result = retained.result_by_objective_id(marker.objective_marker_id)
    assert retained_result.controlled_by_player_id == "player-a"
    assert retained_result.retained_control_source_id == sticky.source_rule_id

    _move_unit(state, target.unit_instance_id, x=marker.x_inches, y=marker.y_inches)
    enemy_record = resolve_objective_control(
        ObjectiveControlContext.from_game_state(
            state,
            timing=ObjectiveControlTiming.PHASE_END,
            phase=BattlePhase.COMMAND,
            ruleset_descriptor=state.runtime_ruleset_descriptor(),
            runtime_modifier_registry=RuntimeModifierRegistry.empty(),
        )
    )
    assert sticky_objective_control_state_is_expired(
        state=sticky,
        record=enemy_record,
        player_ids=state.player_ids,
    )
    assert (
        apply_sticky_objective_control(record=enemy_record, states=(sticky,))
        .result_by_objective_id(marker.objective_marker_id)
        .controlled_by_player_id
        == "player-b"
    )


def test_tormentors_objective_defiled_records_through_lifecycle_and_replays() -> None:
    session, tormentors, target = _battleline_lifecycle_session(
        source_datasheet_id="000004079",
        phase=BattlePhase.COMMAND,
        with_icon=False,
        game_id="tormentors-objective-defiled-lifecycle",
    )
    state = session.lifecycle.state
    assert state is not None
    marker = state.mission_setup.objective_markers[0] if state.mission_setup else None
    assert marker is not None
    _move_unit(state, tormentors.unit_instance_id, x=marker.x_inches, y=marker.y_inches)
    _move_unit(state, target.unit_instance_id, x=marker.x_inches + 20.0, y=marker.y_inches)

    status = session.advance_until_decision_or_terminal()
    for index in range(32):
        if state.current_battle_phase is BattlePhase.MOVEMENT:
            break
        request = _decision_request(status)
        option_id = (
            DECLINE_STRATAGEM_WINDOW_OPTION_ID
            if request.decision_type == STRATAGEM_DECISION_TYPE
            else request.options[0].option_id
        )
        status = session.submit_option(
            request_id=request.request_id,
            option_id=option_id,
            result_id=f"objective-defiled-lifecycle-{index:03d}",
        )
    else:
        raise AssertionError("Command phase did not advance to Movement.")

    assert state.current_battle_phase is BattlePhase.MOVEMENT
    sticky = next(
        sticky_state
        for sticky_state in state.sticky_objective_control_states
        if sticky_state.objective_id == marker.objective_marker_id
    )
    assert sticky.player_id == "player-a"
    recorded_events = tuple(
        record
        for record in session.lifecycle.decision_controller.event_log.records
        if record.event_type == "sticky_objective_control_state_recorded"
    )
    assert len(recorded_events) == 1
    assert (
        cast(dict[str, JsonValue], recorded_events[0].payload)["sticky_objective_control_state"]
        == sticky.to_payload()
    )
    _move_unit(
        state,
        tormentors.unit_instance_id,
        x=marker.x_inches + 20.0,
        y=marker.y_inches,
    )
    status = _advance_battleline_without_actions_to_phase(
        session=session,
        status=status,
        target_phase=BattlePhase.SHOOTING,
    )
    movement_record = next(
        record
        for record in state.objective_control_records
        if record.phase == BattlePhase.MOVEMENT.value
        and record.timing is ObjectiveControlTiming.PHASE_END
    )
    retained = movement_record.result_by_objective_id(marker.objective_marker_id)
    assert retained.controlled_by_player_id == "player-a"
    assert retained.retained_control_source_id == sticky.source_rule_id
    assert sticky in state.sticky_objective_control_states

    _move_unit(state, target.unit_instance_id, x=marker.x_inches, y=marker.y_inches)
    initial_lifecycle_payload = cast(
        GameLifecyclePayload,
        json.loads(json.dumps(session.lifecycle.to_payload(), sort_keys=True)),
    )
    status = _advance_battleline_without_actions_to_phase(
        session=session,
        status=status,
        target_phase=BattlePhase.CHARGE,
    )
    assert status.status_kind in {
        LifecycleStatusKind.WAITING_FOR_DECISION,
        LifecycleStatusKind.TERMINAL,
    }
    assert all(
        stored.objective_id != marker.objective_marker_id
        for stored in state.sticky_objective_control_states
    )
    shooting_record = next(
        record
        for record in state.objective_control_records
        if record.phase == BattlePhase.SHOOTING.value
        and record.timing is ObjectiveControlTiming.PHASE_END
    )
    assert (
        shooting_record.result_by_objective_id(marker.objective_marker_id).controlled_by_player_id
        == "player-b"
    )
    replay_payload = cast(
        ReplayArtifactPayload,
        json.loads(
            json.dumps(
                ReplayArtifact.capture(
                    artifact_id="tormentors-objective-defiled-lifecycle",
                    initial_lifecycle_payload=initial_lifecycle_payload,
                    final_lifecycle=session.lifecycle,
                ).to_payload(),
                sort_keys=True,
            )
        ),
    )
    replay_result = ReplayRunner.from_payload(replay_payload).run()
    assert replay_result.reproduced_exactly, replay_result.to_payload()


def test_tormentors_objective_defiled_uses_attached_unit_objective_contribution() -> None:
    session, tormentors, target = _battleline_lifecycle_session(
        source_datasheet_id="000004079",
        phase=BattlePhase.COMMAND,
        with_icon=False,
        game_id="tormentors-objective-defiled-attached",
        attached_source=True,
    )
    state = session.lifecycle.state
    assert state is not None
    marker = state.mission_setup.objective_markers[0] if state.mission_setup else None
    assert marker is not None
    attached_view = rules_unit_view_by_id(
        state=state,
        unit_instance_id=tormentors.unit_instance_id,
    )
    leader = next(
        component.unit for component in attached_view.components if component.role == "leader"
    )
    _move_unit(
        state,
        tormentors.unit_instance_id,
        x=marker.x_inches + 20.0,
        y=marker.y_inches,
    )
    _move_unit(state, leader.unit_instance_id, x=marker.x_inches, y=marker.y_inches)
    _move_unit(
        state,
        target.unit_instance_id,
        x=marker.x_inches - 20.0,
        y=marker.y_inches,
    )

    status = session.advance_until_decision_or_terminal()

    assert status.status_kind is LifecycleStatusKind.WAITING_FOR_DECISION
    assert state.current_battle_phase is BattlePhase.MOVEMENT
    sticky = next(
        stored
        for stored in state.sticky_objective_control_states
        if stored.objective_id == marker.objective_marker_id
    )
    assert sticky.player_id == "player-a"
    command_record = next(
        record
        for record in state.objective_control_records
        if record.phase == BattlePhase.COMMAND.value
        and record.timing is ObjectiveControlTiming.PHASE_END
    )
    assert (
        command_record.result_by_objective_id(marker.objective_marker_id).controlled_by_player_id
        == "player-a"
    )


@pytest.mark.parametrize("movement_mode", ["normal", "advance", "fall_back"])
def test_fulgrim_serpentine_grants_exact_terrain_transit_modes(movement_mode: str) -> None:
    _, _, indexes, fulgrim, _ = _fulgrim_runtime_fixture(
        phase=BattlePhase.MOVEMENT,
        active_player_id="player-a",
    )
    model = fulgrim.own_models[0]

    permissions = catalog_movement_transit_permissions_for_model(
        ability_index=indexes["player-a"],
        unit=fulgrim,
        model_instance_id=model.model_instance_id,
        current_model_instance_ids=(model.model_instance_id,),
        movement_mode=movement_mode,
    )

    assert len(permissions) == 1
    assert permissions[0].movement_modes == ("advance", "fall_back", "normal")
    assert permissions[0].terrain_height_max_inches == 4.0
    assert permissions[0].permission == "move_over_as_if_not_there"
    assert (
        catalog_movement_transit_permissions_for_model(
            ability_index=indexes["player-a"],
            unit=fulgrim,
            model_instance_id=model.model_instance_id,
            current_model_instance_ids=(model.model_instance_id,),
            movement_mode="charge",
        )
        == ()
    )


@pytest.mark.parametrize(
    "mode_name",
    ["Beguiling Form", "Daemonic Speed", "Enthralling Hypnosis (Aura)"],
)
def test_fulgrim_daemon_primarch_modes_use_one_replay_safe_command_decision(
    mode_name: str,
) -> None:
    armies, state, indexes, fulgrim, enemy = _fulgrim_runtime_fixture(
        phase=BattlePhase.COMMAND,
        active_player_id="player-b",
        game_id="fulgrim-command-test-2",
    )
    runtime = CatalogSelectableAbilityModeRuntime(indexes, armies)
    decisions = DecisionController()
    request = runtime.request(
        CommandPhaseStartRequestContext(
            state=state,
            decisions=decisions,
            active_player_id="player-b",
        )
    )
    assert request is not None
    assert request.actor_id == "player-a"
    assert tuple(option.label for option in request.options) == (
        "Beguiling Form",
        "Daemonic Speed",
        "Enthralling Hypnosis (Aura)",
    )
    decisions.request_decision(request)
    option = next(option for option in request.options if option.label == mode_name)
    mode_token = mode_name.casefold().replace(" ", "-").replace("(", "").replace(")", "")
    result = DecisionResult.for_request(
        result_id=f"fulgrim-mode-{mode_token}",
        request=request,
        selected_option_id=option.option_id,
    )
    result = DecisionResult.from_payload(
        cast(DecisionResultPayload, json.loads(json.dumps(result.to_payload())))
    )
    decisions.submit_result(result)
    registry = CommandPhaseStartHookRegistry.from_bindings(runtime.bindings())
    assert registry.apply_result(
        CommandPhaseStartResultContext(
            state=state,
            decisions=decisions,
            request=request,
            result=result,
            active_player_id="player-b",
            ability_indexes_by_player_id=indexes,
        )
    )
    assert (
        DecisionController.from_payload(json.loads(json.dumps(decisions.to_payload()))).records
        == decisions.records
    )

    state = GameState.from_payload(
        cast(GameStatePayload, json.loads(json.dumps(state.to_payload())))
    )
    assert len(state.persisting_effects) == 1
    payload = cast(dict[str, Any], state.persisting_effects[0].effect_payload)
    assert payload["selected_mode_name"] == mode_name
    assert state.persisting_effects[0].expiration.battle_round == 2
    assert state.persisting_effects[0].expiration.player_id == "player-b"

    if mode_name == "Beguiling Form":
        modifiers = RuntimeModifierRegistry.from_bindings(
            hit_roll_modifier_bindings=catalog_selectable_ability_mode_hit_roll_bindings(
                ability_indexes_by_player_id=indexes
            )
        )
        assert (
            modifiers.hit_roll_modifier(
                HitRollModifierContext(
                    state=state,
                    attacking_unit_instance_id=enemy.unit_instance_id,
                    attacker_model_instance_id=enemy.own_models[0].model_instance_id,
                    target_unit_instance_id=fulgrim.unit_instance_id,
                    weapon_profile=_weapon_profile(_NIGHT_SPINNER_ID, "Doomweaver"),
                    source_phase=BattlePhase.SHOOTING,
                )
            )
            == -1
        )
    elif mode_name == "Daemonic Speed":
        assert FightsFirstRegistry.from_state(state).has_unit(fulgrim.unit_instance_id)
    else:
        _move_unit(state, fulgrim.unit_instance_id, x=10.0, y=10.0)
        _move_unit(state, enemy.unit_instance_id, x=19.5, y=10.0)
        state.battle_phase_index = state.battle_phase_sequence.index(BattlePhase.MOVEMENT)
        denied = resolve_catalog_fall_back_leadership_denial(
            state=state,
            decisions=decisions,
            target_unit_instance_id=enemy.unit_instance_id,
            ability_indexes_by_player_id=indexes,
            runtime_modifier_registry=RuntimeModifierRegistry.empty(),
        )
        assert denied
        event = next(
            record
            for record in decisions.event_log.records
            if record.event_type == CATALOG_FALL_BACK_LEADERSHIP_TEST_EVENT
        )
        event_payload = cast(dict[str, Any], event.payload)
        assert event_payload["leadership_target"] == 7
        assert event_payload["fall_back_denied"] is True


def test_fulgrim_daemonic_poisons_routes_shooting_and_fight_hits_then_ticks_once() -> None:
    armies, state, indexes, fulgrim, enemy = _fulgrim_runtime_fixture(
        phase=BattlePhase.SHOOTING,
        active_player_id="player-a",
        game_id="fulgrim-runtime-test",
    )
    decisions = DecisionController()
    runtime = CatalogSelectedTargetEffectRuntime(indexes, armies)

    _select_poisoned_target(
        phase=BattlePhase.SHOOTING,
        runtime=runtime,
        state=state,
        decisions=decisions,
        indexes=indexes,
        fulgrim=fulgrim,
        enemy=enemy,
        profile=_weapon_profile(_FULGRIM_ID, "Malefic lash"),
    )
    assert len(state.persisting_effects) == 1

    state.battle_phase_index = state.battle_phase_sequence.index(BattlePhase.FIGHT)
    _select_poisoned_target(
        phase=BattlePhase.FIGHT,
        runtime=runtime,
        state=state,
        decisions=decisions,
        indexes=indexes,
        fulgrim=fulgrim,
        enemy=enemy,
        profile=_weapon_profile(_FULGRIM_ID, "Daemonic blades - strike"),
    )
    assert len(state.persisting_effects) == 2
    assert {effect.target_unit_instance_ids for effect in state.persisting_effects} == {
        (enemy.unit_instance_id,)
    }

    state.battle_phase_index = state.battle_phase_sequence.index(BattlePhase.COMMAND)
    poison_registry = CommandPhaseStartHookRegistry.from_bindings(
        catalog_poisoned_command_start_bindings(ability_indexes_by_player_id=indexes)
    )
    assert (
        poison_registry.resolve_effects(
            CommandPhaseStartEffectContext(
                state=state,
                decisions=decisions,
                active_player_id="player-a",
            )
        )
        is None
    )
    resolved_events = tuple(
        record
        for record in decisions.event_log.records
        if record.event_type == CATALOG_POISONED_COMMAND_RESOLVED_EVENT
    )
    assert len(resolved_events) == 1
    resolved_payload = cast(dict[str, Any], resolved_events[0].payload)
    assert resolved_payload["poison_effect_ids"] == sorted(
        effect.effect_id for effect in state.persisting_effects
    )
    assert resolved_payload["mortal_wounds"] == 3
    updated_enemy = _unit_from_state(state, enemy.unit_instance_id)
    assert updated_enemy.own_models[0].wounds_remaining == 9


def test_fulgrim_opponent_turn_fight_poison_uses_lifecycle_dispatch_and_replays() -> None:
    session, fulgrim, enemy = _fulgrim_opponent_turn_fight_session()
    status = _advance_fight_session_to_poison_request(
        session=session,
        fulgrim=fulgrim,
    )
    request = _decision_request(status)

    assert request.decision_type == SELECT_CATALOG_POST_FIGHT_HIT_TARGET_EFFECT_DECISION_TYPE
    assert request.actor_id == "player-a"
    assert session.lifecycle.state is not None
    assert session.lifecycle.state.active_player_id == "player-b"
    option_payload = cast(dict[str, JsonValue], request.options[0].payload)
    selected_target_payload = cast(
        dict[str, JsonValue],
        option_payload["selected_catalog_target_effect"],
    )
    assert selected_target_payload["target_unit_instance_id"] == enemy.unit_instance_id
    pending_poison_payload = cast(
        GameLifecyclePayload,
        json.loads(json.dumps(session.lifecycle.to_payload(), sort_keys=True)),
    )
    assert GameLifecycle.from_payload(pending_poison_payload).to_payload() == pending_poison_payload

    submitted = session.submit_option(
        request_id=request.request_id,
        option_id=request.options[0].option_id,
        result_id="fulgrim-opponent-turn-poison-selection",
    )
    assert submitted.status_kind is LifecycleStatusKind.WAITING_FOR_DECISION
    assert session.lifecycle.state is not None
    poison_effects = session.lifecycle.state.persisting_effects_for_unit(enemy.unit_instance_id)
    assert len(poison_effects) == 1
    assert session.lifecycle.decision_controller.records[-1].request.decision_type == (
        SELECT_CATALOG_POST_FIGHT_HIT_TARGET_EFFECT_DECISION_TYPE
    )

    lifecycle_payload = cast(
        GameLifecyclePayload,
        json.loads(json.dumps(session.lifecycle.to_payload(), sort_keys=True)),
    )
    assert GameLifecycle.from_payload(lifecycle_payload).to_payload() == lifecycle_payload
    replay_payload = cast(
        ReplayArtifactPayload,
        json.loads(
            json.dumps(
                ReplayArtifact.capture(
                    artifact_id="fulgrim-opponent-turn-fight-poison",
                    initial_lifecycle_payload=pending_poison_payload,
                    final_lifecycle=session.lifecycle,
                ).to_payload(),
                sort_keys=True,
            )
        ),
    )
    replay_result = ReplayRunner.from_payload(replay_payload).run()
    assert replay_result.reproduced_exactly, replay_result.to_payload()


def test_fulgrim_poison_survives_attached_unit_split_and_deduplicates_each_survivor() -> None:
    package = _catalog_package()
    factory = UnitFactory(
        catalog=package.army_catalog,
        model_geometries=package.model_geometries,
    )
    fulgrim = _instantiate_unit(
        factory=factory,
        army_id="army-a",
        datasheet_id=_FULGRIM_ID,
        selection_id="fulgrim",
    )
    bodyguard = _instantiate_unit(
        factory=factory,
        army_id="army-b",
        datasheet_id=_NIGHT_SPINNER_ID,
        selection_id="poisoned-bodyguard",
    )
    leader = _instantiate_unit(
        factory=factory,
        army_id="army-b",
        datasheet_id=_NIGHT_SPINNER_ID,
        selection_id="poisoned-leader",
    )
    attached_id = "attached-unit:army-b:poisoned-formation"
    formation = AttachedUnitFormation(
        attached_unit_instance_id=attached_id,
        bodyguard_unit_instance_id=bodyguard.unit_instance_id,
        leader_unit_instance_ids=(leader.unit_instance_id,),
        component_unit_instance_ids=tuple(
            sorted((bodyguard.unit_instance_id, leader.unit_instance_id))
        ),
        source_id="test:fulgrim-poisoned-attached-unit",
        attachment_source_ids=("test:fulgrim-poisoned-attached-unit:eligibility",),
    )
    armies = (
        _army(
            catalog=package.army_catalog,
            army_id="army-a",
            player_id="player-a",
            faction_id="emperors-children",
            units=(fulgrim,),
        ),
        _army(
            catalog=package.army_catalog,
            army_id="army-b",
            player_id="player-b",
            faction_id="aeldari",
            units=(bodyguard, leader),
            attached_units=(formation,),
        ),
    )
    state = _battle_state(
        armies=armies,
        phase=BattlePhase.SHOOTING,
        active_player_id="player-a",
        game_id="fulgrim-attached-poison-replay",
    )
    records = catalog_ability_records_from_catalog(package.army_catalog)
    indexes = {
        army.player_id: build_player_ability_index(
            records,
            army=army,
            catalog=package.army_catalog,
        )
        for army in armies
    }
    decisions = DecisionController()
    runtime = CatalogSelectedTargetEffectRuntime(indexes, armies)
    for suffix in ("first", "duplicate"):
        _select_poisoned_target(
            phase=BattlePhase.SHOOTING,
            runtime=runtime,
            state=state,
            decisions=decisions,
            indexes=indexes,
            fulgrim=fulgrim,
            enemy=bodyguard,
            profile=_weapon_profile(_FULGRIM_ID, "Malefic lash"),
            sequence_suffix=suffix,
        )

    assert len(state.persisting_effects) == 2
    assert {effect.target_unit_instance_ids for effect in state.persisting_effects} == {
        (attached_id,)
    }
    state.recover_starting_strength_after_attached_unit_split(
        player_id="player-b",
        attached_unit_instance_id=attached_id,
        surviving_unit_instance_ids=(bodyguard.unit_instance_id, leader.unit_instance_id),
        event_log=decisions.event_log,
    )
    expected_survivor_ids = tuple(sorted((bodyguard.unit_instance_id, leader.unit_instance_id)))
    assert {effect.target_unit_instance_ids for effect in state.persisting_effects} == {
        expected_survivor_ids
    }
    for effect in state.persisting_effects:
        effect_payload = cast(dict[str, Any], effect.effect_payload)
        rule_effect = cast(dict[str, Any], effect_payload["effect"])
        parameters = {
            parameter["key"]: parameter["value"]
            for parameter in cast(list[dict[str, Any]], rule_effect["parameters"])
        }
        assert parameters["selected_target_unit_instance_id"] == attached_id

    state.battle_phase_index = state.battle_phase_sequence.index(BattlePhase.COMMAND)
    state_payload = cast(
        GameStatePayload,
        json.loads(json.dumps(state.to_payload(), sort_keys=True)),
    )
    decisions_payload = json.loads(json.dumps(decisions.to_payload(), sort_keys=True))
    resolved_state, resolved_decisions = _resolve_poisoned_snapshot(
        state_payload=state_payload,
        decisions_payload=decisions_payload,
        indexes=indexes,
    )
    replayed_state, replayed_decisions = _resolve_poisoned_snapshot(
        state_payload=state_payload,
        decisions_payload=decisions_payload,
        indexes=indexes,
    )

    resolved_events = tuple(
        cast(dict[str, Any], event.payload)
        for event in resolved_decisions.event_log.records
        if event.event_type == CATALOG_POISONED_COMMAND_RESOLVED_EVENT
    )
    assert {payload["target_unit_instance_id"] for payload in resolved_events} == set(
        expected_survivor_ids
    )
    assert len(resolved_events) == 2
    expected_effect_ids = sorted(effect.effect_id for effect in state.persisting_effects)
    assert all(payload["poison_effect_ids"] == expected_effect_ids for payload in resolved_events)
    assert replayed_state.to_payload() == resolved_state.to_payload()
    assert replayed_decisions.to_payload() == resolved_decisions.to_payload()


def _select_poisoned_target(
    *,
    phase: BattlePhase,
    runtime: CatalogSelectedTargetEffectRuntime,
    state: GameState,
    decisions: DecisionController,
    indexes: dict[str, AbilityCatalogIndex],
    fulgrim: UnitInstance,
    enemy: UnitInstance,
    profile: WeaponProfile,
    sequence_suffix: str | None = None,
) -> None:
    sequence_token = phase.value if sequence_suffix is None else sequence_suffix
    sequence = AttackSequence(
        sequence_id=f"fulgrim-poison-{sequence_token}",
        attacker_player_id="player-a",
        attacking_unit_instance_id=fulgrim.unit_instance_id,
        source_phase=phase,
        attack_pools=(_attack_pool(fulgrim, enemy, profile),),
    )
    decisions.event_log.append(
        "attack_sequence_step",
        {
            "sequence_id": sequence.sequence_id,
            "step": AttackSequenceStep.HIT.value,
            "pool_index": 0,
            "payload": {"successful": True},
        },
    )
    context = AttackSequenceCompletedContext(
        state=state,
        decisions=decisions,
        dice_manager=DiceRollManager(state.game_id, event_log=decisions.event_log),
        runtime_modifier_registry=RuntimeModifierRegistry.empty(),
        source_phase=phase,
        attack_sequence=sequence,
        attack_sequence_completed_event_id=f"fulgrim-poison-completed-{sequence_token}",
    )
    status = (
        runtime.post_shoot_hit_target_request(context)
        if phase is BattlePhase.SHOOTING
        else runtime.post_fight_hit_target_request(context)
    )
    assert status is not None
    request = decisions.queue.peek_next()
    assert len(request.options) == 1
    result = DecisionResult.for_request(
        result_id=f"fulgrim-poison-result-{sequence_token}",
        request=request,
        selected_option_id=request.options[0].option_id,
    )
    if phase is BattlePhase.FIGHT:
        drifted_payload = cast(dict[str, Any], result.payload).copy()
        drifted_payload["battle_round"] = 2
        invalid_status = invalid_catalog_post_fight_hit_target_effect_status(
            state=state,
            request=request,
            result=replace(result, payload=drifted_payload),
        )
        assert invalid_status is not None
        assert not state.persisting_effects or len(state.persisting_effects) == 1
    result = DecisionResult.from_payload(
        cast(DecisionResultPayload, json.loads(json.dumps(result.to_payload())))
    )
    decisions.submit_result(result)
    if phase is BattlePhase.SHOOTING:
        assert (
            apply_catalog_post_shoot_hit_target_effect_result(
                state=state,
                decisions=decisions,
                result=result,
                battle_shock_hooks=BattleShockHookRegistry.empty(),
                runtime_modifier_registry=RuntimeModifierRegistry.empty(),
                ability_indexes_by_player_id=indexes,
            )
            is None
        )
    else:
        assert (
            apply_catalog_post_fight_hit_target_effect_result(
                state=state,
                decisions=decisions,
                result=result,
            )
            is None
        )


def _fulgrim_opponent_turn_fight_session(
    *, game_id: str = "fulgrim-opponent-turn-fight-lifecycle-007"
) -> tuple[
    LocalGameSession,
    UnitInstance,
    UnitInstance,
]:
    package = _catalog_package()
    catalog = replace(
        package.army_catalog,
        detachments=(
            DetachmentDefinition(
                detachment_id="fulgrim-lifecycle-test",
                name="Fulgrim lifecycle test",
                faction_id="EC",
                detachment_point_cost=1,
                unit_datasheet_ids=(_FULGRIM_ID,),
                force_disposition_ids=("purge-the-foe",),
                source_ids=("test:fulgrim-lifecycle:detachment:emperors-children",),
            ),
            DetachmentDefinition(
                detachment_id="night-spinner-lifecycle-test",
                name="Night Spinner lifecycle test",
                faction_id="AE",
                detachment_point_cost=1,
                unit_datasheet_ids=(_NIGHT_SPINNER_ID,),
                force_disposition_ids=("purge-the-foe",),
                source_ids=("test:fulgrim-lifecycle:detachment:aeldari",),
            ),
        ),
    )
    descriptor = RulesetDescriptor.warhammer_40000_eleventh()
    muster_requests = (
        ArmyMusterRequest(
            army_id="army-a",
            player_id="player-a",
            catalog_id=catalog.catalog_id,
            source_package_id=catalog.source_package_id,
            ruleset_id=catalog.ruleset_id,
            detachment_selection=DetachmentSelection(
                faction_id="EC",
                detachment_ids=("fulgrim-lifecycle-test",),
            ),
            force_disposition_id="purge-the-foe",
            unit_selections=(
                _unit_muster_selection(
                    catalog=catalog,
                    datasheet_id=_FULGRIM_ID,
                    unit_selection_id="fulgrim",
                ),
            ),
        ),
        ArmyMusterRequest(
            army_id="army-b",
            player_id="player-b",
            catalog_id=catalog.catalog_id,
            source_package_id=catalog.source_package_id,
            ruleset_id=catalog.ruleset_id,
            detachment_selection=DetachmentSelection(
                faction_id="AE",
                detachment_ids=("night-spinner-lifecycle-test",),
            ),
            force_disposition_id="purge-the-foe",
            unit_selections=(
                _unit_muster_selection(
                    catalog=catalog,
                    datasheet_id=_NIGHT_SPINNER_ID,
                    unit_selection_id="night-spinner",
                ),
            ),
        ),
    )
    config = GameConfig(
        game_id=game_id,
        allow_legacy_non_strict_rosters=True,
        ruleset_descriptor=descriptor,
        army_catalog=catalog,
        army_muster_requests=muster_requests,
        player_ids=("player-a", "player-b"),
        turn_order=("player-a", "player-b"),
        fixed_secondary_mission_ids=("assassination", "bring_it_down"),
        mission_setup=_mission_setup(),
    )
    armies = tuple(
        muster_army(
            catalog=catalog,
            request=request,
        )
        for request in muster_requests
    )
    fulgrim = armies[0].units[0]
    enemy = armies[1].units[0]
    state = GameState.from_config(config)
    for army in armies:
        state.record_army_definition(army)
    state.record_battlefield_state(
        create_deterministic_battlefield_scenario(
            battlefield_id="fulgrim-opponent-turn-fight-battlefield",
            armies=armies,
        ).battlefield_state
    )
    state.stage = GameLifecycleStage.BATTLE
    state.setup_step_index = None
    state.battle_phase_index = state.battle_phase_sequence.index(BattlePhase.FIGHT)
    state.battle_round = 1
    state.active_player_id = "player-b"
    for player_id in state.player_ids:
        state.record_secondary_mission_choice(
            SecondaryMissionChoice(
                player_id=player_id,
                mode=SecondaryMissionMode.FIXED,
                fixed_mission_ids=("assassination", "bring_it_down"),
            )
        )
    _move_unit(state, fulgrim.unit_instance_id, x=10.0, y=10.0)
    _move_unit(state, enemy.unit_instance_id, x=15.5, y=10.0)
    lifecycle = GameLifecycle.from_payload(
        cast(
            GameLifecyclePayload,
            {
                "config": config.to_payload(),
                "parameterized_movement_proposals": True,
                "state": state.to_payload(),
                "decisions": DecisionController().to_payload(),
                "reaction_queue": ReactionQueue().to_payload(),
            },
        )
    )
    return LocalGameSession(lifecycle=lifecycle), fulgrim, enemy


def _advance_fight_session_to_poison_request(
    *,
    session: LocalGameSession,
    fulgrim: UnitInstance,
) -> LifecycleStatus:
    status = session.advance_until_decision_or_terminal()
    for index in range(256):
        request = _decision_request(status)
        if request.decision_type == SELECT_CATALOG_POST_FIGHT_HIT_TARGET_EFFECT_DECISION_TYPE:
            return status
        result_id = f"fulgrim-opponent-turn-auto-{index:03d}"
        if request.decision_type == MOVEMENT_PROPOSAL_DECISION_TYPE:
            movement_request = MovementProposalRequest.from_decision_request_payload(
                request.payload
            )
            context = cast(dict[str, JsonValue], movement_request.context)
            status = session.submit_parameterized_payload(
                request_id=request.request_id,
                result_id=result_id,
                payload=cast(
                    JsonValue,
                    {
                        "proposal_request_id": movement_request.request_id,
                        "proposal_kind": movement_request.proposal_kind.value,
                        "unit_instance_id": movement_request.unit_instance_id,
                        "movement_phase_action": movement_request.movement_phase_action,
                        "movement_mode": context["movement_mode"],
                    },
                ),
            )
            continue
        if request.decision_type == FIGHT_ACTIVATION_DECISION_TYPE:
            if request.actor_id == "player-a":
                option_id = next(
                    option.option_id
                    for option in request.options
                    if cast(dict[str, JsonValue], option.payload).get("unit_instance_id")
                    == fulgrim.unit_instance_id
                )
            else:
                option_id = request.options[0].option_id
            status = session.submit_option(
                request_id=request.request_id,
                option_id=option_id,
                result_id=result_id,
            )
            continue
        if request.decision_type == SUBMIT_MELEE_DECLARATION_DECISION_TYPE:
            melee_request = MeleeDeclarationProposalRequest.from_decision_request(request)
            weapon = (
                next(
                    cast(dict[str, Any], value)
                    for value in melee_request.available_weapons
                    if cast(dict[str, Any], value)["weapon_profile_id"]
                    == _weapon_profile(_FULGRIM_ID, "Daemonic blades - sweep").profile_id
                )
                if melee_request.actor_id == "player-a"
                else cast(dict[str, Any], melee_request.available_weapons[0])
            )
            target_ids = cast(list[str], weapon["engaged_target_unit_instance_ids"])
            status = session.submit_parameterized_payload(
                request_id=request.request_id,
                result_id=result_id,
                payload=cast(
                    JsonValue,
                    {
                        "proposal_request_id": melee_request.request_id,
                        "proposal_kind": melee_request.proposal_kind,
                        "player_id": melee_request.actor_id,
                        "battle_round": melee_request.battle_round,
                        "unit_instance_id": melee_request.unit_instance_id,
                        "source_decision_request_id": melee_request.source_decision_request_id,
                        "source_decision_result_id": melee_request.source_decision_result_id,
                        "declarations": [
                            {
                                "attacker_model_instance_id": weapon["model_instance_id"],
                                "wargear_id": weapon["wargear_id"],
                                "weapon_profile_id": weapon["weapon_profile_id"],
                                "target_allocations": [{"target_unit_instance_id": target_ids[0]}],
                            }
                        ],
                    },
                ),
            )
            continue
        if request.decision_type == STRATAGEM_DECISION_TYPE:
            option_id = DECLINE_STRATAGEM_WINDOW_OPTION_ID
        else:
            if request.is_parameterized_submission_request():
                raise AssertionError(
                    f"Unexpected parameterized Fight decision {request.decision_type}."
                )
            option_id = request.options[0].option_id
        status = session.submit_option(
            request_id=request.request_id,
            option_id=option_id,
            result_id=result_id,
        )
    raise AssertionError("Fulgrim Fight did not reach the poison target decision.")


def _resolve_poisoned_snapshot(
    *,
    state_payload: GameStatePayload,
    decisions_payload: object,
    indexes: dict[str, AbilityCatalogIndex],
) -> tuple[GameState, DecisionController]:
    state = GameState.from_payload(state_payload)
    decisions = DecisionController.from_payload(cast(DecisionControllerPayload, decisions_payload))
    registry = CommandPhaseStartHookRegistry.from_bindings(
        catalog_poisoned_command_start_bindings(ability_indexes_by_player_id=indexes)
    )
    assert (
        registry.resolve_effects(
            CommandPhaseStartEffectContext(
                state=state,
                decisions=decisions,
                active_player_id="player-a",
            )
        )
        is None
    )
    return state, decisions


def _unit_muster_selection(
    *,
    catalog: Any,
    datasheet_id: str,
    unit_selection_id: str,
) -> UnitMusterSelection:
    datasheet = catalog.datasheet_by_id(datasheet_id)
    return UnitMusterSelection(
        unit_selection_id=unit_selection_id,
        datasheet_id=datasheet_id,
        model_profile_selections=(
            ModelProfileSelection(datasheet.model_profiles[0].model_profile_id, 1),
        ),
    )


def _decision_request(status: LifecycleStatus) -> DecisionRequest:
    assert status.status_kind is LifecycleStatusKind.WAITING_FOR_DECISION
    assert status.decision_request is not None
    return status.decision_request


@lru_cache(maxsize=1)
def _catalog_package() -> CanonicalCatalogPackage:
    return _ability_support_catalog_package()


def _kakophonist_runtime_fixture() -> tuple[
    tuple[ArmyDefinition, ...],
    GameState,
    dict[str, AbilityCatalogIndex],
    UnitInstance,
    UnitInstance,
    str,
]:
    package = _catalog_package()
    catalog = package.army_catalog
    factory = UnitFactory(catalog=catalog, model_geometries=package.model_geometries)
    lord = _instantiate_minimum_composition_unit(
        factory=factory,
        army_id="army-a",
        datasheet_id="000004084",
        selection_id="lord-kakophonist",
    )
    source_noise_marines = _instantiate_minimum_composition_unit(
        factory=factory,
        army_id="army-a",
        datasheet_id="000004088",
        selection_id="source-noise-marines",
    )
    target = _instantiate_minimum_composition_unit(
        factory=factory,
        army_id="army-b",
        datasheet_id="000004088",
        selection_id="target-noise-marines",
    )
    attached_id = "attached-unit:army-a:kakophonist-noise-marines"
    formation = AttachedUnitFormation(
        attached_unit_instance_id=attached_id,
        bodyguard_unit_instance_id=source_noise_marines.unit_instance_id,
        leader_unit_instance_ids=(lord.unit_instance_id,),
        component_unit_instance_ids=tuple(
            sorted((source_noise_marines.unit_instance_id, lord.unit_instance_id))
        ),
        source_id="test:lord-kakophonist-noise-marines:formation",
        attachment_source_ids=("test:lord-kakophonist-noise-marines:leader-eligibility",),
    )
    armies = (
        _army(
            catalog=catalog,
            army_id="army-a",
            player_id="player-a",
            faction_id="emperors-children",
            units=(lord, source_noise_marines),
            attached_units=(formation,),
        ),
        _army(
            catalog=catalog,
            army_id="army-b",
            player_id="player-b",
            faction_id="emperors-children",
            units=(target,),
        ),
    )
    state = _battle_state(
        armies=armies,
        phase=BattlePhase.SHOOTING,
        active_player_id="player-a",
        game_id="kakophonist-runtime-test",
    )
    records = catalog_ability_records_from_catalog(catalog)
    indexes = {
        army.player_id: build_player_ability_index(records, army=army, catalog=catalog)
        for army in armies
    }
    return armies, state, indexes, source_noise_marines, target, attached_id


def _kakophonist_attached_target_runtime_fixture() -> tuple[
    tuple[ArmyDefinition, ...],
    GameState,
    dict[str, AbilityCatalogIndex],
    UnitInstance,
    UnitInstance,
    UnitInstance,
    str,
    str,
]:
    package = _catalog_package()
    catalog = package.army_catalog
    factory = UnitFactory(catalog=catalog, model_geometries=package.model_geometries)
    source_lord = _instantiate_minimum_composition_unit(
        factory=factory,
        army_id="army-a",
        datasheet_id="000004084",
        selection_id="source-lord-kakophonist",
    )
    source_noise_marines = _instantiate_minimum_composition_unit(
        factory=factory,
        army_id="army-a",
        datasheet_id="000004088",
        selection_id="source-noise-marines-attached-target",
    )
    target_lord = _instantiate_minimum_composition_unit(
        factory=factory,
        army_id="army-b",
        datasheet_id="000004084",
        selection_id="target-lord-kakophonist",
    )
    target_noise_marines = _instantiate_minimum_composition_unit(
        factory=factory,
        army_id="army-b",
        datasheet_id="000004088",
        selection_id="target-noise-marines-attached",
    )
    source_attached_id = "attached-unit:army-a:kakophonist-noise-marines"
    target_attached_id = "attached-unit:army-b:kakophonist-noise-marines"

    def formation(
        *,
        attached_id: str,
        bodyguard: UnitInstance,
        leader: UnitInstance,
    ) -> AttachedUnitFormation:
        return AttachedUnitFormation(
            attached_unit_instance_id=attached_id,
            bodyguard_unit_instance_id=bodyguard.unit_instance_id,
            leader_unit_instance_ids=(leader.unit_instance_id,),
            component_unit_instance_ids=tuple(
                sorted((bodyguard.unit_instance_id, leader.unit_instance_id))
            ),
            source_id=f"test:{attached_id}:formation",
            attachment_source_ids=(f"test:{attached_id}:leader-eligibility",),
        )

    armies = (
        _army(
            catalog=catalog,
            army_id="army-a",
            player_id="player-a",
            faction_id="emperors-children",
            units=(source_lord, source_noise_marines),
            attached_units=(
                formation(
                    attached_id=source_attached_id,
                    bodyguard=source_noise_marines,
                    leader=source_lord,
                ),
            ),
        ),
        _army(
            catalog=catalog,
            army_id="army-b",
            player_id="player-b",
            faction_id="emperors-children",
            units=(target_lord, target_noise_marines),
            attached_units=(
                formation(
                    attached_id=target_attached_id,
                    bodyguard=target_noise_marines,
                    leader=target_lord,
                ),
            ),
        ),
    )
    state = _battle_state(
        armies=armies,
        phase=BattlePhase.SHOOTING,
        active_player_id="player-a",
        game_id="kakophonist-attached-target-runtime-test",
    )
    records = catalog_ability_records_from_catalog(catalog)
    indexes = {
        army.player_id: build_player_ability_index(records, army=army, catalog=catalog)
        for army in armies
    }
    return (
        armies,
        state,
        indexes,
        source_noise_marines,
        target_noise_marines,
        target_lord,
        source_attached_id,
        target_attached_id,
    )


def _configured_kakophonist_multi_target_fixture() -> tuple[
    GameConfig,
    tuple[ArmyDefinition, ...],
    GameState,
    dict[str, AbilityCatalogIndex],
    UnitInstance,
    UnitInstance,
    UnitInstance,
    str,
]:
    config, armies, state, indexes = _configured_kakophonist_fixture(
        attached_target=False,
    )
    source_noise_marines = _unit_from_state(state, "army-a:source-noise-marines")
    target_a = _unit_from_state(state, "army-b:target-noise-marines-a")
    target_b = _unit_from_state(state, "army-b:target-noise-marines-b")
    return (
        config,
        armies,
        state,
        indexes,
        source_noise_marines,
        target_a,
        target_b,
        armies[0].attached_units[0].attached_unit_instance_id,
    )


def _configured_kakophonist_attached_target_fixture(
    *,
    single_wound_noise_marines: bool = False,
) -> tuple[
    GameConfig,
    tuple[ArmyDefinition, ...],
    GameState,
    dict[str, AbilityCatalogIndex],
    UnitInstance,
    UnitInstance,
    UnitInstance,
    str,
    str,
]:
    config, armies, state, indexes = _configured_kakophonist_fixture(
        attached_target=True,
        single_wound_noise_marines=single_wound_noise_marines,
    )
    source_noise_marines = _unit_from_state(state, "army-a:source-noise-marines")
    target_noise_marines = _unit_from_state(state, "army-b:target-noise-marines")
    target_lord = _unit_from_state(state, "army-b:target-lord-kakophonist")
    return (
        config,
        armies,
        state,
        indexes,
        source_noise_marines,
        target_noise_marines,
        target_lord,
        armies[0].attached_units[0].attached_unit_instance_id,
        armies[1].attached_units[0].attached_unit_instance_id,
    )


def _configured_kakophonist_leader_support_target_fixture(
    *,
    single_wound_bodyguard: bool = False,
) -> tuple[
    GameConfig,
    tuple[ArmyDefinition, ...],
    GameState,
    dict[str, AbilityCatalogIndex],
    UnitInstance,
    UnitInstance,
    UnitInstance,
    UnitInstance,
    str,
    str,
]:
    config, armies, state, indexes = _configured_kakophonist_fixture(
        attached_target=True,
        leader_support_target=True,
        single_wound_core_bodyguard=single_wound_bodyguard,
    )
    source_noise_marines = _unit_from_state(state, "army-a:source-noise-marines")
    target_bodyguard = _unit_from_state(state, "army-b:target-bodyguard")
    target_leader = _unit_from_state(state, "army-b:target-leader")
    target_support = _unit_from_state(state, "army-b:target-support")
    return (
        config,
        armies,
        state,
        indexes,
        source_noise_marines,
        target_bodyguard,
        target_leader,
        target_support,
        armies[0].attached_units[0].attached_unit_instance_id,
        armies[1].attached_units[0].attached_unit_instance_id,
    )


def _record_attached_split_authoritative_state(
    *,
    state: GameState,
    target_attached_id: str,
) -> None:
    state.record_persisting_effect(
        PersistingEffect(
            effect_id="test:leader-support-split:persisting-effect",
            source_rule_id="test:leader-support-split:source-rule",
            owner_player_id="player-a",
            target_unit_instance_ids=(target_attached_id,),
            started_battle_round=state.battle_round,
            started_phase=BattlePhaseKind.SHOOTING,
            expiration=EffectExpiration.end_of_battle(),
            effect_payload={
                "effect_kind": "test_attached_target_marker",
            },
        )
    )
    state.record_mission_action_state(
        MissionActionState.start(
            action_id="test:leader-support-split:mission-action",
            player_id="player-b",
            unit_instance_id=target_attached_id,
            target_id="test:leader-support-split:action-target",
            mission_id="test:leader-support-split:mission",
            battle_round=state.battle_round,
            phase=BattlePhase.SHOOTING.value,
            start_timing="shooting_phase",
            completion_timing="end_turn",
            eligible_unit_instance_ids=(target_attached_id,),
            interruption_conditions=(MISSION_ACTION_UNIT_DESTROYED_INTERRUPTION_REASON,),
            scoring_source_id="test:leader-support-split:scoring-source",
            victory_points=0,
        )
    )


def _assert_attached_split_authoritative_state(
    *,
    state: GameState,
    decisions: DecisionController,
    target_attached_id: str,
    component_units: tuple[UnitInstance, ...],
    survivor_ids: tuple[str, ...],
) -> None:
    assert all(
        formation.attached_unit_instance_id != target_attached_id
        for army in state.army_definitions
        for formation in army.attached_units
    )
    assert target_attached_id not in {
        record.unit_instance_id for record in state.starting_strength_records
    }
    assert tuple(
        state.starting_strength_record_for_unit(unit.unit_instance_id).starting_model_count
        for unit in component_units
    ) == tuple(len(unit.own_models) for unit in component_units)
    persisting_effect = next(
        effect
        for effect in state.persisting_effects
        if effect.effect_id == "test:leader-support-split:persisting-effect"
    )
    assert persisting_effect.target_unit_instance_ids == survivor_ids
    action_state = state.mission_action_state_by_id("test:leader-support-split:mission-action")
    assert action_state.status is MissionActionStatus.INTERRUPTED
    assert action_state.interrupted_reason == MISSION_ACTION_UNIT_DESTROYED_INTERRUPTION_REASON
    interrupted_payload = cast(
        dict[str, Any],
        next(
            event.payload
            for event in decisions.event_log.records
            if event.event_type == "mission_action_interrupted"
            and cast(dict[str, Any], event.payload).get("action_id") == action_state.action_id
        ),
    )
    assert interrupted_payload["unit_instance_id"] == target_attached_id
    assert interrupted_payload["surviving_unit_instance_ids"] == list(survivor_ids)


def _configured_kakophonist_fixture(
    *,
    attached_target: bool,
    single_wound_noise_marines: bool = False,
    leader_support_target: bool = False,
    single_wound_core_bodyguard: bool = False,
) -> tuple[
    GameConfig,
    tuple[ArmyDefinition, ...],
    GameState,
    dict[str, AbilityCatalogIndex],
]:
    if leader_support_target and not attached_target:
        raise AssertionError("Leader-and-Support target must be an Attached Unit.")
    if single_wound_core_bodyguard and not leader_support_target:
        raise AssertionError("Single-wound core Bodyguard requires the Leader-and-Support target.")
    package = _catalog_package()
    base_catalog = package.army_catalog
    if leader_support_target:
        core_catalog = ArmyCatalog.phase9a_canonical_content_pack()
        core_datasheet_ids = {
            "core-intercessor-like-infantry",
            "core-character-leader",
            "core-character-support",
        }
        core_wargear_ids = {"core-bolt-rifle", "core-leader-blade"}
        base_catalog = replace(
            base_catalog,
            datasheets=(
                *base_catalog.datasheets,
                *(
                    replace(
                        datasheet,
                        keywords=replace(
                            datasheet.keywords,
                            faction_keywords=("EMPEROR'S CHILDREN",),
                        ),
                    )
                    for datasheet in core_catalog.datasheets
                    if datasheet.datasheet_id in core_datasheet_ids
                ),
            ),
            wargear=(
                *base_catalog.wargear,
                *(
                    wargear
                    for wargear in core_catalog.wargear
                    if wargear.wargear_id in core_wargear_ids
                ),
            ),
            source_ids=tuple(sorted({*base_catalog.source_ids, *core_catalog.source_ids})),
        )
    if single_wound_core_bodyguard:
        core_bodyguard = base_catalog.datasheet_by_id("core-intercessor-like-infantry")
        core_bodyguard_profile = core_bodyguard.model_profiles[0]
        core_bodyguard = replace(
            core_bodyguard,
            model_profiles=(
                replace(
                    core_bodyguard_profile,
                    characteristics=tuple(
                        replace(characteristic, raw=1, base=1, final=1)
                        if characteristic.characteristic is Characteristic.WOUNDS
                        else characteristic
                        for characteristic in core_bodyguard_profile.characteristics
                    ),
                ),
            ),
            composition=(replace(core_bodyguard.composition[0], min_models=1, max_models=1),),
            max_unit_models=1,
        )
        base_catalog = replace(
            base_catalog,
            datasheets=tuple(
                core_bodyguard
                if datasheet.datasheet_id == core_bodyguard.datasheet_id
                else datasheet
                for datasheet in base_catalog.datasheets
            ),
        )
    if single_wound_noise_marines:
        noise_marines = base_catalog.datasheet_by_id("000004088")
        disharmonist = noise_marines.model_profiles[0]
        single_wound_disharmonist = replace(
            disharmonist,
            characteristics=tuple(
                replace(characteristic, raw=1, base=1, final=1)
                if characteristic.characteristic is Characteristic.WOUNDS
                else characteristic
                for characteristic in disharmonist.characteristics
            ),
        )
        noise_marines = replace(
            noise_marines,
            model_profiles=(
                single_wound_disharmonist,
                *noise_marines.model_profiles[1:],
            ),
            composition=(replace(noise_marines.composition[0], min_models=1, max_models=1),),
            max_unit_models=1,
        )
        base_catalog = replace(
            base_catalog,
            datasheets=tuple(
                noise_marines if datasheet.datasheet_id == noise_marines.datasheet_id else datasheet
                for datasheet in base_catalog.datasheets
            ),
        )
    catalog = replace(
        base_catalog,
        detachments=(
            DetachmentDefinition(
                detachment_id="kakophonist-sequencing-test",
                name="Kakophonist sequencing test",
                faction_id="EC",
                detachment_point_cost=1,
                unit_datasheet_ids=(
                    "000004084",
                    "000004088",
                    *(
                        (
                            "core-intercessor-like-infantry",
                            "core-character-leader",
                            "core-character-support",
                        )
                        if leader_support_target
                        else ()
                    ),
                ),
                force_disposition_ids=("purge-the-foe",),
                source_ids=("test:kakophonist-sequencing:detachment",),
            ),
        ),
    )
    source_selections = (
        _minimum_unit_muster_selection(
            catalog=catalog,
            datasheet_id="000004084",
            unit_selection_id="source-lord-kakophonist",
        ),
        _minimum_unit_muster_selection(
            catalog=catalog,
            datasheet_id="000004088",
            unit_selection_id="source-noise-marines",
        ),
    )
    target_selections = (
        (
            _minimum_unit_muster_selection(
                catalog=catalog,
                datasheet_id="core-intercessor-like-infantry",
                unit_selection_id="target-bodyguard",
            ),
            _minimum_unit_muster_selection(
                catalog=catalog,
                datasheet_id="core-character-leader",
                unit_selection_id="target-leader",
            ),
            _minimum_unit_muster_selection(
                catalog=catalog,
                datasheet_id="core-character-support",
                unit_selection_id="target-support",
            ),
        )
        if leader_support_target
        else (
            _minimum_unit_muster_selection(
                catalog=catalog,
                datasheet_id="000004084",
                unit_selection_id="target-lord-kakophonist",
            ),
            _minimum_unit_muster_selection(
                catalog=catalog,
                datasheet_id="000004088",
                unit_selection_id="target-noise-marines",
            ),
        )
        if attached_target
        else (
            _minimum_unit_muster_selection(
                catalog=catalog,
                datasheet_id="000004088",
                unit_selection_id="target-noise-marines-a",
            ),
            _minimum_unit_muster_selection(
                catalog=catalog,
                datasheet_id="000004088",
                unit_selection_id="target-noise-marines-b",
            ),
        )
    )
    muster_requests = (
        ArmyMusterRequest(
            army_id="army-a",
            player_id="player-a",
            catalog_id=catalog.catalog_id,
            source_package_id=catalog.source_package_id,
            ruleset_id=catalog.ruleset_id,
            detachment_selection=DetachmentSelection(
                faction_id="EC",
                detachment_ids=("kakophonist-sequencing-test",),
            ),
            force_disposition_id="purge-the-foe",
            unit_selections=source_selections,
            attachment_declarations=(
                AttachmentDeclaration(
                    source_unit_selection_id="source-lord-kakophonist",
                    bodyguard_unit_selection_id="source-noise-marines",
                ),
            ),
        ),
        ArmyMusterRequest(
            army_id="army-b",
            player_id="player-b",
            catalog_id=catalog.catalog_id,
            source_package_id=catalog.source_package_id,
            ruleset_id=catalog.ruleset_id,
            detachment_selection=DetachmentSelection(
                faction_id="EC",
                detachment_ids=("kakophonist-sequencing-test",),
            ),
            force_disposition_id="purge-the-foe",
            unit_selections=target_selections,
            attachment_declarations=(
                (
                    *(
                        (
                            AttachmentDeclaration(
                                source_unit_selection_id="target-leader",
                                bodyguard_unit_selection_id="target-bodyguard",
                            ),
                            AttachmentDeclaration(
                                source_unit_selection_id="target-support",
                                bodyguard_unit_selection_id="target-bodyguard",
                            ),
                        )
                        if leader_support_target
                        else (
                            AttachmentDeclaration(
                                source_unit_selection_id="target-lord-kakophonist",
                                bodyguard_unit_selection_id="target-noise-marines",
                            ),
                        )
                    ),
                )
                if attached_target
                else ()
            ),
        ),
    )
    descriptor = RulesetDescriptor.warhammer_40000_eleventh()
    config = GameConfig(
        game_id=(
            "kakophonist-runtime-test"
            if leader_support_target
            else "kakophonist-attached-target-sequencing"
            if attached_target
            else "kakophonist-multi-target-sequencing"
        ),
        allow_legacy_non_strict_rosters=True,
        ruleset_descriptor=descriptor,
        army_catalog=catalog,
        army_muster_requests=muster_requests,
        player_ids=("player-a", "player-b"),
        turn_order=("player-a", "player-b"),
        fixed_secondary_mission_ids=("assassination", "bring_it_down"),
        mission_setup=_mission_setup(),
    )
    armies = tuple(muster_army(catalog=catalog, request=request) for request in muster_requests)
    state = GameState.from_config(config)
    for army in armies:
        state.record_army_definition(army)
    state.record_battlefield_state(
        create_deterministic_battlefield_scenario(
            battlefield_id=f"{config.game_id}-battlefield",
            armies=armies,
        ).battlefield_state
    )
    state.stage = GameLifecycleStage.BATTLE
    state.setup_step_index = None
    state.battle_phase_index = state.battle_phase_sequence.index(BattlePhase.SHOOTING)
    state.battle_round = 1
    state.active_player_id = "player-a"
    for player_id in state.player_ids:
        state.record_secondary_mission_choice(
            SecondaryMissionChoice(
                player_id=player_id,
                mode=SecondaryMissionMode.FIXED,
                fixed_mission_ids=("assassination", "bring_it_down"),
            )
        )
    records = catalog_ability_records_from_catalog(catalog)
    indexes = {
        army.player_id: build_player_ability_index(records, army=army, catalog=catalog)
        for army in armies
    }
    return config, armies, state, indexes


def _minimum_unit_muster_selection(
    *,
    catalog: Any,
    datasheet_id: str,
    unit_selection_id: str,
) -> UnitMusterSelection:
    datasheet = catalog.datasheet_by_id(datasheet_id)
    return UnitMusterSelection(
        unit_selection_id=unit_selection_id,
        datasheet_id=datasheet_id,
        model_profile_selections=tuple(
            ModelProfileSelection(entry.model_profile_id, entry.min_models)
            for entry in datasheet.composition
        ),
    )


def _kakophonist_post_shoot_context(
    *,
    state: GameState,
    decisions: DecisionController,
    source_noise_marines: UnitInstance,
    source_rules_unit_id: str,
    targets: tuple[tuple[UnitInstance, str | None], ...],
    sequence_suffix: str,
) -> AttackSequenceCompletedContext:
    sequence = AttackSequence(
        sequence_id=f"kakophonist-noise-marines-{sequence_suffix}",
        attacker_player_id="player-a",
        attacking_unit_instance_id=source_rules_unit_id,
        source_phase=BattlePhase.SHOOTING,
        attack_pools=tuple(
            _attack_pool(
                source_noise_marines,
                target,
                _weapon_profile("000004088", "Sonic blaster"),
                target_unit_instance_id=target_rules_unit_id,
            )
            for target, target_rules_unit_id in targets
        ),
    )
    for pool_index in range(len(sequence.attack_pools)):
        decisions.event_log.append(
            "attack_sequence_step",
            {
                "sequence_id": sequence.sequence_id,
                "step": AttackSequenceStep.HIT.value,
                "pool_index": pool_index,
                "payload": {"successful": True},
            },
        )
    return AttackSequenceCompletedContext(
        state=state,
        decisions=decisions,
        dice_manager=DiceRollManager(state.game_id, event_log=decisions.event_log),
        runtime_modifier_registry=RuntimeModifierRegistry.empty(),
        source_phase=BattlePhase.SHOOTING,
        attack_sequence=sequence,
        attack_sequence_completed_event_id=f"kakophonist-completed-{sequence_suffix}",
    )


def _submit_catalog_post_shoot_target(
    *,
    state: GameState,
    decisions: DecisionController,
    request: DecisionRequest,
    target_unit_instance_id: str,
    result_id: str,
    battle_shock_hooks: BattleShockHookRegistry,
    indexes: dict[str, AbilityCatalogIndex],
) -> LifecycleStatus | None:
    option = next(
        option
        for option in request.options
        if cast(
            dict[str, Any],
            cast(dict[str, Any], option.payload)["selected_catalog_target_effect"],
        )["target_unit_instance_id"]
        == target_unit_instance_id
    )
    result = DecisionResult.for_request(
        result_id=result_id,
        request=request,
        selected_option_id=option.option_id,
    )
    decisions.submit_result(result)
    return apply_catalog_post_shoot_hit_target_effect_result(
        state=state,
        decisions=decisions,
        result=result,
        battle_shock_hooks=battle_shock_hooks,
        runtime_modifier_registry=RuntimeModifierRegistry.empty(),
        ability_indexes_by_player_id=indexes,
    )


def _resolve_kakophonist_post_shoot_effects(
    *,
    runtime: CatalogSelectedTargetEffectRuntime,
    state: GameState,
    decisions: DecisionController,
    indexes: dict[str, AbilityCatalogIndex],
    source_noise_marines: UnitInstance,
    source_rules_unit_id: str,
    target: UnitInstance,
    sequence_suffix: str,
    battle_shock_hooks: BattleShockHookRegistry,
    ability_order: tuple[str, str],
    target_rules_unit_id: str | None = None,
) -> tuple[str, ...]:
    sequence = AttackSequence(
        sequence_id=f"kakophonist-noise-marines-{sequence_suffix}",
        attacker_player_id="player-a",
        attacking_unit_instance_id=source_rules_unit_id,
        source_phase=BattlePhase.SHOOTING,
        attack_pools=(
            _attack_pool(
                source_noise_marines,
                target,
                _weapon_profile("000004088", "Sonic blaster"),
                target_unit_instance_id=target_rules_unit_id,
            ),
        ),
    )
    decisions.event_log.append(
        "attack_sequence_step",
        {
            "sequence_id": sequence.sequence_id,
            "step": AttackSequenceStep.HIT.value,
            "pool_index": 0,
            "payload": {"successful": True},
        },
    )
    context = AttackSequenceCompletedContext(
        state=state,
        decisions=decisions,
        dice_manager=DiceRollManager(state.game_id, event_log=decisions.event_log),
        runtime_modifier_registry=RuntimeModifierRegistry.empty(),
        source_phase=BattlePhase.SHOOTING,
        attack_sequence=sequence,
        attack_sequence_completed_event_id=f"kakophonist-completed-{sequence_suffix}",
    )
    resolved_names: list[str] = []
    while runtime.post_shoot_hit_target_request(context) is not None:
        request = decisions.queue.peek_next()
        if request.decision_type == SEQUENCING_DECISION_TYPE:
            _submit_post_shoot_sequencing_order(
                decisions=decisions,
                request=request,
                ability_order=ability_order,
                result_id=f"kakophonist-{sequence_suffix}-sequencing-result",
            )
            continue
        request_payload = cast(dict[str, Any], request.payload)
        ability_name = cast(str, request_payload["ability_name"])
        result = DecisionResult.for_request(
            result_id=(
                f"kakophonist-{sequence_suffix}-{ability_name.casefold().replace(' ', '-')}-result"
            ),
            request=request,
            selected_option_id=request.options[0].option_id,
        )
        decisions.submit_result(result)
        pending_status = apply_catalog_post_shoot_hit_target_effect_result(
            state=state,
            decisions=decisions,
            result=result,
            battle_shock_hooks=battle_shock_hooks,
            runtime_modifier_registry=RuntimeModifierRegistry.empty(),
            ability_indexes_by_player_id=indexes,
        )
        assert pending_status is None
        resolved_names.append(ability_name)
    return tuple(resolved_names)


def _submit_post_shoot_sequencing_order(
    *,
    decisions: DecisionController,
    request: DecisionRequest,
    ability_order: tuple[str, str],
    result_id: str,
) -> SequencingDecision:
    assert request.decision_type == SEQUENCING_DECISION_TYPE
    roundtripped_request = DecisionRequest.from_payload(
        json.loads(json.dumps(request.to_payload(), sort_keys=True))
    )
    assert roundtripped_request == request
    pending_snapshot = DecisionController.from_payload(
        cast(
            DecisionControllerPayload,
            json.loads(json.dumps(decisions.to_payload(), sort_keys=True)),
        )
    )
    assert pending_snapshot.queue.peek_next() == request
    request_payload = cast(dict[str, Any], request.payload)
    participants = cast(list[dict[str, Any]], request_payload["participants"])
    participant_id_by_name = {
        cast(str, cast(dict[str, Any], participant["payload"])["ability_name"]): cast(
            str, participant["participant_id"]
        )
        for participant in participants
    }
    ordered_participant_ids = tuple(
        participant_id_by_name[ability_name] for ability_name in ability_order
    )
    option = next(
        candidate
        for candidate in request.options
        if tuple(cast(dict[str, Any], candidate.payload)["ordered_participant_ids"])
        == ordered_participant_ids
    )
    result = DecisionResult.for_request(
        result_id=result_id,
        request=request,
        selected_option_id=option.option_id,
    )
    roundtripped_result = DecisionResult.from_payload(
        cast(
            DecisionResultPayload,
            json.loads(json.dumps(result.to_payload(), sort_keys=True)),
        )
    )
    assert roundtripped_result == result
    decisions.submit_result(result)
    sequencing_decision = apply_sequencing_decision_from_request(
        request=request,
        result=result,
    )
    decisions.event_log.append(
        "sequencing_order_resolved",
        sequencing_decision.to_payload(),
    )
    return sequencing_decision


def _fulgrim_runtime_fixture(
    *,
    phase: BattlePhase,
    active_player_id: str,
    game_id: str = "fulgrim-runtime-fixture",
) -> tuple[
    tuple[ArmyDefinition, ...],
    GameState,
    dict[str, AbilityCatalogIndex],
    UnitInstance,
    UnitInstance,
]:
    package = _catalog_package()
    catalog = package.army_catalog
    factory = UnitFactory(catalog=catalog, model_geometries=package.model_geometries)
    fulgrim = _instantiate_unit(
        factory=factory,
        army_id="army-a",
        datasheet_id=_FULGRIM_ID,
        selection_id="fulgrim",
    )
    enemy = _instantiate_unit(
        factory=factory,
        army_id="army-b",
        datasheet_id=_NIGHT_SPINNER_ID,
        selection_id="night-spinner",
    )
    armies = (
        _army(
            catalog=catalog,
            army_id="army-a",
            player_id="player-a",
            faction_id="emperors-children",
            units=(fulgrim,),
        ),
        _army(
            catalog=catalog,
            army_id="army-b",
            player_id="player-b",
            faction_id="aeldari",
            units=(enemy,),
        ),
    )
    state = _battle_state(
        armies=armies,
        phase=phase,
        active_player_id=active_player_id,
        game_id=game_id,
    )
    records = catalog_ability_records_from_catalog(catalog)
    indexes = {
        army.player_id: build_player_ability_index(records, army=army, catalog=catalog)
        for army in armies
    }
    return armies, state, indexes, fulgrim, enemy


def _battleline_runtime_fixture(
    *,
    source_datasheet_id: str,
    phase: BattlePhase,
    with_icon: bool,
    game_id: str,
) -> tuple[
    tuple[ArmyDefinition, ...],
    GameState,
    dict[str, AbilityCatalogIndex],
    UnitInstance,
    UnitInstance,
]:
    package = _catalog_package()
    catalog = package.army_catalog
    factory = UnitFactory(catalog=catalog, model_geometries=package.model_geometries)
    source = _instantiate_battleline_unit(
        factory=factory,
        army_id="army-a",
        datasheet_id=source_datasheet_id,
        selection_id=f"source-{source_datasheet_id}",
        with_icon=with_icon,
    )
    target_datasheet_id = "000004080" if source_datasheet_id == "000004079" else "000004079"
    target = _instantiate_battleline_unit(
        factory=factory,
        army_id="army-b",
        datasheet_id=target_datasheet_id,
        selection_id=f"target-{target_datasheet_id}",
        with_icon=False,
    )
    armies = (
        _army(
            catalog=catalog,
            army_id="army-a",
            player_id="player-a",
            faction_id="emperors-children",
            units=(source,),
        ),
        _army(
            catalog=catalog,
            army_id="army-b",
            player_id="player-b",
            faction_id="emperors-children",
            units=(target,),
        ),
    )
    state = _battle_state(
        armies=armies,
        phase=phase,
        active_player_id="player-a",
        game_id=game_id,
    )
    records = catalog_ability_records_from_catalog(catalog)
    indexes = {
        army.player_id: build_player_ability_index(records, army=army, catalog=catalog)
        for army in armies
    }
    return armies, state, indexes, source, target


def _battleline_lifecycle_session(
    *,
    source_datasheet_id: str,
    phase: BattlePhase,
    with_icon: bool,
    game_id: str,
    single_source_model: bool = False,
    single_target_model: bool = False,
    extra_target: bool = False,
    attached_source: bool = False,
) -> tuple[LocalGameSession, UnitInstance, UnitInstance]:
    package = _catalog_package()
    base_catalog = package.army_catalog
    target_datasheet_id = "000004080" if source_datasheet_id == "000004079" else "000004079"
    target_datasheet = base_catalog.datasheet_by_id(target_datasheet_id)
    single_wound_target_profiles = tuple(
        replace(
            target_profile,
            characteristics=tuple(
                replace(
                    characteristic,
                    raw=(6 if characteristic.characteristic is Characteristic.SAVE else 1),
                    base=(6 if characteristic.characteristic is Characteristic.SAVE else 1),
                    final=(6 if characteristic.characteristic is Characteristic.SAVE else 1),
                )
                if characteristic.characteristic
                in {
                    Characteristic.TOUGHNESS,
                    Characteristic.SAVE,
                    Characteristic.WOUNDS,
                }
                else characteristic
                for characteristic in target_profile.characteristics
            ),
        )
        for target_profile in target_datasheet.model_profiles
    )
    target_composition = (
        (replace(target_datasheet.composition[0], min_models=1, max_models=1),)
        if single_target_model
        else tuple(
            replace(composition, min_models=1, max_models=1)
            for composition in target_datasheet.composition
        )
    )
    target_datasheet = replace(
        target_datasheet,
        model_profiles=single_wound_target_profiles,
        composition=target_composition,
        max_unit_models=len(target_composition),
    )
    catalog = replace(
        base_catalog,
        datasheets=tuple(
            target_datasheet if datasheet.datasheet_id == target_datasheet_id else datasheet
            for datasheet in base_catalog.datasheets
        ),
        detachments=(
            DetachmentDefinition(
                detachment_id="battleline-lifecycle-test",
                name="Battleline lifecycle test",
                faction_id="EC",
                detachment_point_cost=1,
                unit_datasheet_ids=(
                    "000004079",
                    "000004080",
                    *(("000004083",) if attached_source else ()),
                ),
                force_disposition_ids=("purge-the-foe",),
                source_ids=("test:emperors-children:battleline-lifecycle",),
            ),
        ),
    )
    if single_source_model:
        source_datasheet = catalog.datasheet_by_id(source_datasheet_id)
        icon_model_profile_id = next(
            option.model_profile_id
            for option in source_datasheet.wargear_options
            if "icon-of-excess" in option.option_id
        )
        source_composition = next(
            composition
            for composition in source_datasheet.composition
            if composition.model_profile_id == icon_model_profile_id
        )
        source_datasheet = replace(
            source_datasheet,
            composition=(replace(source_composition, min_models=1, max_models=1),),
            max_unit_models=1,
        )
        catalog = replace(
            catalog,
            datasheets=tuple(
                source_datasheet if datasheet.datasheet_id == source_datasheet_id else datasheet
                for datasheet in catalog.datasheets
            ),
        )
    if attached_source:
        leader_datasheet = catalog.datasheet_by_id("000004083")
        leader_datasheet = replace(
            leader_datasheet,
            model_profiles=tuple(
                replace(
                    profile,
                    characteristics=tuple(
                        replace(characteristic, raw=5, base=5, final=5)
                        if characteristic.characteristic is Characteristic.LEADERSHIP
                        else characteristic
                        for characteristic in profile.characteristics
                    ),
                )
                for profile in leader_datasheet.model_profiles
            ),
            attachment_eligibilities=(
                AttachmentEligibility(
                    role=AttachmentRole.LEADER,
                    targets=(
                        AttachmentTargetEligibility(
                            bodyguard_datasheet_id=source_datasheet_id,
                            source_ids=("test:emperors-children:battleline-attached-source",),
                        ),
                    ),
                ),
            ),
        )
        catalog = replace(
            catalog,
            datasheets=tuple(
                leader_datasheet
                if datasheet.datasheet_id == leader_datasheet.datasheet_id
                else datasheet
                for datasheet in catalog.datasheets
            ),
        )
    if source_datasheet_id == "000004079":
        boltgun = next(
            wargear for wargear in catalog.wargear if wargear.wargear_id == "000004079:boltgun"
        )
        boltgun_profile = boltgun.weapon_profiles[0]
        deterministic_lifecycle_profile = replace(
            boltgun_profile,
            attack_profile=AttackProfile.fixed(12),
            skill=replace(boltgun_profile.skill, raw=2, base=2, final=2),
            strength=replace(boltgun_profile.strength, raw=12, base=12, final=12),
            armor_penetration=replace(
                boltgun_profile.armor_penetration,
                raw=-6,
                base=-6,
                final=-6,
            ),
        )
        catalog = replace(
            catalog,
            wargear=tuple(
                replace(boltgun, weapon_profiles=(deterministic_lifecycle_profile,))
                if wargear.wargear_id == boltgun.wargear_id
                else wargear
                for wargear in catalog.wargear
            ),
        )
    source_selection = _minimum_unit_muster_selection(
        catalog=catalog,
        datasheet_id=source_datasheet_id,
        unit_selection_id="source-battleline",
    )
    if with_icon:
        source_datasheet = catalog.datasheet_by_id(source_datasheet_id)
        icon_option = next(
            option
            for option in source_datasheet.wargear_options
            if "icon-of-excess" in option.option_id
        )
        source_selection = replace(
            source_selection,
            wargear_selections=(
                WargearSelection(
                    option_id=icon_option.option_id,
                    model_profile_id=icon_option.model_profile_id,
                    wargear_ids=icon_option.allowed_wargear_ids,
                ),
            ),
        )
    muster_requests = (
        ArmyMusterRequest(
            army_id="army-a",
            player_id="player-a",
            catalog_id=catalog.catalog_id,
            source_package_id=catalog.source_package_id,
            ruleset_id=catalog.ruleset_id,
            detachment_selection=DetachmentSelection(
                faction_id="EC",
                detachment_ids=("battleline-lifecycle-test",),
            ),
            force_disposition_id="purge-the-foe",
            unit_selections=(
                source_selection,
                *(
                    (
                        _minimum_unit_muster_selection(
                            catalog=catalog,
                            datasheet_id="000004083",
                            unit_selection_id="source-attached-leader",
                        ),
                    )
                    if attached_source
                    else ()
                ),
            ),
            attachment_declarations=(
                (
                    AttachmentDeclaration(
                        source_unit_selection_id="source-attached-leader",
                        bodyguard_unit_selection_id="source-battleline",
                    ),
                )
                if attached_source
                else ()
            ),
        ),
        ArmyMusterRequest(
            army_id="army-b",
            player_id="player-b",
            catalog_id=catalog.catalog_id,
            source_package_id=catalog.source_package_id,
            ruleset_id=catalog.ruleset_id,
            detachment_selection=DetachmentSelection(
                faction_id="EC",
                detachment_ids=("battleline-lifecycle-test",),
            ),
            force_disposition_id="purge-the-foe",
            unit_selections=(
                _minimum_unit_muster_selection(
                    catalog=catalog,
                    datasheet_id=target_datasheet_id,
                    unit_selection_id="target-battleline",
                ),
                *(
                    (
                        _minimum_unit_muster_selection(
                            catalog=catalog,
                            datasheet_id=target_datasheet_id,
                            unit_selection_id="extra-target-battleline",
                        ),
                    )
                    if extra_target
                    else ()
                ),
            ),
        ),
    )
    descriptor = RulesetDescriptor.warhammer_40000_eleventh()
    config = GameConfig(
        game_id=game_id,
        allow_legacy_non_strict_rosters=True,
        ruleset_descriptor=descriptor,
        army_catalog=catalog,
        army_muster_requests=muster_requests,
        player_ids=("player-a", "player-b"),
        turn_order=("player-a", "player-b"),
        fixed_secondary_mission_ids=("assassination", "bring_it_down"),
        mission_setup=_mission_setup(),
    )
    armies = tuple(muster_army(catalog=catalog, request=request) for request in muster_requests)
    source = next(
        unit for unit in armies[0].units if unit.unit_instance_id == "army-a:source-battleline"
    )
    target = next(
        unit for unit in armies[1].units if unit.unit_instance_id == "army-b:target-battleline"
    )
    state = GameState.from_config(config)
    for army in armies:
        state.record_army_definition(army)
    state.record_battlefield_state(
        create_deterministic_battlefield_scenario(
            battlefield_id=f"{game_id}-battlefield",
            armies=armies,
        ).battlefield_state
    )
    state.stage = GameLifecycleStage.BATTLE
    state.setup_step_index = None
    state.battle_phase_index = state.battle_phase_sequence.index(phase)
    state.battle_round = 1
    state.active_player_id = "player-a"
    for player_id in state.player_ids:
        state.record_secondary_mission_choice(
            SecondaryMissionChoice(
                player_id=player_id,
                mode=SecondaryMissionMode.FIXED,
                fixed_mission_ids=("assassination", "bring_it_down"),
            )
        )
    lifecycle = GameLifecycle.from_payload(
        cast(
            GameLifecyclePayload,
            {
                "config": config.to_payload(),
                "parameterized_movement_proposals": True,
                "state": state.to_payload(),
                "decisions": DecisionController().to_payload(),
                "reaction_queue": ReactionQueue().to_payload(),
            },
        )
    )
    return LocalGameSession(lifecycle=lifecycle), source, target


def _advance_battleline_fight_to_source_reroll(
    *,
    session: LocalGameSession,
    source: UnitInstance,
    status: LifecycleStatus,
) -> LifecycleStatus:
    for index in range(128):
        request = _decision_request(status)
        if (
            request.decision_type == DICE_REROLL_DECISION_TYPE
            and isinstance(request.payload, dict)
            and "source_rule_id" in request.payload
        ):
            return status
        result_id = f"battleline-fight-auto-{index:03d}"
        if request.decision_type == MOVEMENT_PROPOSAL_DECISION_TYPE:
            movement_request = MovementProposalRequest.from_decision_request_payload(
                request.payload
            )
            context = cast(dict[str, JsonValue], movement_request.context)
            status = session.submit_parameterized_payload(
                request_id=request.request_id,
                result_id=result_id,
                payload=cast(
                    JsonValue,
                    {
                        "proposal_request_id": movement_request.request_id,
                        "proposal_kind": movement_request.proposal_kind.value,
                        "unit_instance_id": movement_request.unit_instance_id,
                        "movement_phase_action": movement_request.movement_phase_action,
                        "movement_mode": context["movement_mode"],
                    },
                ),
            )
            continue
        if request.decision_type == FIGHT_ACTIVATION_DECISION_TYPE:
            option_id = next(
                option.option_id
                for option in request.options
                if source.unit_instance_id in option.option_id
            )
            status = session.submit_option(
                request_id=request.request_id,
                option_id=option_id,
                result_id=result_id,
            )
            continue
        if request.decision_type == SUBMIT_MELEE_DECLARATION_DECISION_TYPE:
            status = _submit_battleline_melee_declaration(
                session=session,
                request=request,
                result_id=result_id,
            )
            continue
        if request.decision_type == STRATAGEM_DECISION_TYPE:
            option_id = DECLINE_STRATAGEM_WINDOW_OPTION_ID
        elif request.decision_type == DICE_REROLL_DECISION_TYPE:
            option_id = "decline"
        else:
            if request.is_parameterized_submission_request():
                raise AssertionError(
                    f"Unexpected parameterized Fight decision {request.decision_type}."
                )
            option_id = request.options[0].option_id
        status = session.submit_option(
            request_id=request.request_id,
            option_id=option_id,
            result_id=result_id,
        )
    raise AssertionError("Fight lifecycle did not reach the source-backed wound reroll.")


def _submit_battleline_melee_declaration(
    *,
    session: LocalGameSession,
    request: DecisionRequest,
    result_id: str,
    single_declaration: bool = False,
) -> LifecycleStatus:
    melee_request = MeleeDeclarationProposalRequest.from_decision_request(request)
    declarations: list[dict[str, JsonValue]] = []
    for raw_weapon in melee_request.available_weapons:
        weapon = cast(dict[str, JsonValue], raw_weapon)
        engaged_target_ids = cast(
            list[str],
            weapon["engaged_target_unit_instance_ids"],
        )
        if not engaged_target_ids:
            continue
        declarations.append(
            {
                "attacker_model_instance_id": weapon["model_instance_id"],
                "wargear_id": weapon["wargear_id"],
                "weapon_profile_id": weapon["weapon_profile_id"],
                "target_allocations": [{"target_unit_instance_id": engaged_target_ids[0]}],
            }
        )
    assert declarations
    submitted_declarations = declarations[:1] if single_declaration else declarations
    return session.submit_parameterized_payload(
        request_id=request.request_id,
        result_id=result_id,
        payload=cast(
            JsonValue,
            {
                "proposal_request_id": melee_request.request_id,
                "proposal_kind": melee_request.proposal_kind,
                "player_id": melee_request.actor_id,
                "battle_round": melee_request.battle_round,
                "unit_instance_id": melee_request.unit_instance_id,
                "source_decision_request_id": melee_request.source_decision_request_id,
                "source_decision_result_id": melee_request.source_decision_result_id,
                "declarations": submitted_declarations,
            },
        ),
    )


def _advance_battleline_fight_through_phase(
    *,
    session: LocalGameSession,
    source: UnitInstance,
    status: LifecycleStatus,
    stop_at_movement_proposal_kind: str | None = None,
) -> LifecycleStatus:
    state = session.lifecycle.state
    assert state is not None
    source_rules_unit_id = rules_unit_view_by_id(
        state=state,
        unit_instance_id=source.unit_instance_id,
    ).unit_instance_id
    for index in range(256):
        if state.current_battle_phase is not BattlePhase.FIGHT:
            return status
        request = _decision_request(status)
        result_id = f"battleline-fight-complete-{index:03d}"
        if request.decision_type == FIGHT_ACTIVATION_DECISION_TYPE:
            option_id = next(
                (
                    option.option_id
                    for option in request.options
                    if source_rules_unit_id in option.option_id
                ),
                request.options[0].option_id,
            )
        elif request.decision_type == MOVEMENT_PROPOSAL_DECISION_TYPE:
            movement_request = MovementProposalRequest.from_decision_request_payload(
                request.payload
            )
            if movement_request.proposal_kind.value == stop_at_movement_proposal_kind:
                return status
            context = cast(dict[str, JsonValue], movement_request.context)
            status = session.submit_parameterized_payload(
                request_id=request.request_id,
                result_id=result_id,
                payload=cast(
                    JsonValue,
                    {
                        "proposal_request_id": movement_request.request_id,
                        "proposal_kind": movement_request.proposal_kind.value,
                        "unit_instance_id": movement_request.unit_instance_id,
                        "movement_phase_action": movement_request.movement_phase_action,
                        "movement_mode": context["movement_mode"],
                    },
                ),
            )
            continue
        elif request.decision_type == SUBMIT_MELEE_DECLARATION_DECISION_TYPE:
            status = _submit_battleline_melee_declaration(
                session=session,
                request=request,
                result_id=result_id,
                single_declaration=True,
            )
            continue
        elif request.decision_type == STRATAGEM_DECISION_TYPE:
            option_id = DECLINE_STRATAGEM_WINDOW_OPTION_ID
        elif request.decision_type == DICE_REROLL_DECISION_TYPE:
            option_id = "decline"
        else:
            if request.is_parameterized_submission_request():
                raise AssertionError(
                    f"Unexpected parameterized Fight decision {request.decision_type}."
                )
            option_id = request.options[0].option_id
        status = session.submit_option(
            request_id=request.request_id,
            option_id=option_id,
            result_id=result_id,
        )
    raise AssertionError("Fight lifecycle did not complete.")


def _advance_battleline_without_actions_to_phase(
    *,
    session: LocalGameSession,
    status: LifecycleStatus,
    target_phase: BattlePhase,
) -> LifecycleStatus:
    state = session.lifecycle.state
    assert state is not None
    for index in range(128):
        if status.status_kind is LifecycleStatusKind.TERMINAL:
            return status
        if state.current_battle_phase is target_phase:
            return status
        request = _decision_request(status)
        result_id = f"battleline-no-actions-{index:03d}"
        option_ids = {option.option_id for option in request.options}
        if request.decision_type == STRATAGEM_DECISION_TYPE:
            option_id = DECLINE_STRATAGEM_WINDOW_OPTION_ID
        elif request.decision_type == SELECT_SHOOTING_UNIT_DECISION_TYPE:
            option_id = COMPLETE_SHOOTING_PHASE_OPTION_ID
        elif request.decision_type == "select_movement_action":
            option_id = "remain_stationary"
        elif request.decision_type == DICE_REROLL_DECISION_TYPE:
            option_id = "decline"
        else:
            if request.is_parameterized_submission_request():
                raise AssertionError(
                    f"Unexpected parameterized phase decision {request.decision_type}."
                )
            option_id = request.options[0].option_id
        assert option_id in option_ids
        status = session.submit_option(
            request_id=request.request_id,
            option_id=option_id,
            result_id=result_id,
        )
    raise AssertionError(f"Lifecycle did not advance to {target_phase.value}.")


def _advance_battleline_shooting_to_damage_allocation_request(
    *,
    session: LocalGameSession,
    source: UnitInstance,
    target: UnitInstance,
    status: LifecycleStatus,
    weapon_name: str = "Boltgun",
) -> LifecycleStatus:
    source_selected = False
    state = session.lifecycle.state
    assert state is not None
    source_rules_unit_id = rules_unit_view_by_id(
        state=state,
        unit_instance_id=source.unit_instance_id,
    ).unit_instance_id
    for index in range(128):
        request = _decision_request(status)
        if request.decision_type == SELECT_DAMAGE_ALLOCATION_MODEL_DECISION_TYPE:
            return status
        result_id = f"battleline-shooting-auto-{index:03d}"
        if request.decision_type == SELECT_SHOOTING_UNIT_DECISION_TYPE:
            option_ids = {option.option_id for option in request.options}
            if source_selected:
                assert option_ids == {COMPLETE_SHOOTING_PHASE_OPTION_ID}
                return status
            assert source_rules_unit_id in option_ids
            source_selected = True
            option_id = source_rules_unit_id
        elif request.decision_type == SELECT_SHOOTING_TYPE_DECISION_TYPE:
            option_id = ShootingType.NORMAL.value
        elif request.decision_type == SUBMIT_SHOOTING_DECLARATION_DECISION_TYPE:
            payload = cast(dict[str, JsonValue], request.payload)
            proposal_request = cast(
                dict[str, JsonValue],
                payload["proposal_request"],
            )
            available_weapons = cast(
                list[dict[str, JsonValue]],
                proposal_request["available_weapons"],
            )
            declarations = tuple(
                WeaponDeclaration(
                    attacker_model_instance_id=cast(str, weapon["model_instance_id"]),
                    wargear_id=cast(str, weapon["wargear_id"]),
                    weapon_profile_id=cast(str, weapon["weapon_profile_id"]),
                    target_unit_instance_id=target.unit_instance_id,
                    shooting_type=ShootingType.NORMAL,
                )
                for weapon in available_weapons
                if cast(dict[str, JsonValue], weapon["weapon_profile"])["name"] == weapon_name
            )[:1]
            assert declarations
            proposal = ShootingDeclarationProposal(
                proposal_request_id=cast(str, proposal_request["request_id"]),
                proposal_kind=cast(str, proposal_request["proposal_kind"]),
                player_id=cast(str, proposal_request["active_player_id"]),
                battle_round=cast(int, proposal_request["battle_round"]),
                unit_instance_id=cast(str, proposal_request["unit_instance_id"]),
                source_decision_request_id=cast(
                    str,
                    proposal_request["source_decision_request_id"],
                ),
                source_decision_result_id=cast(
                    str,
                    proposal_request["source_decision_result_id"],
                ),
                declarations=declarations,
                firing_deck_selection=None,
                visibility_cache_key=cast(
                    str,
                    proposal_request["visibility_cache_key"],
                ),
            )
            status = session.submit_parameterized_payload(
                request_id=request.request_id,
                result_id=result_id,
                payload=cast(JsonValue, proposal.to_payload()),
            )
            continue
        elif request.decision_type == STRATAGEM_DECISION_TYPE:
            option_id = DECLINE_STRATAGEM_WINDOW_OPTION_ID
        elif request.decision_type == DICE_REROLL_DECISION_TYPE:
            option_id = "decline"
        else:
            if request.is_parameterized_submission_request():
                raise AssertionError(
                    f"Unexpected parameterized Shooting decision {request.decision_type}."
                )
            option_id = request.options[0].option_id
        status = session.submit_option(
            request_id=request.request_id,
            option_id=option_id,
            result_id=result_id,
        )
    raise AssertionError("Shooting lifecycle did not reach damage allocation.")


def _instantiate_battleline_unit(
    *,
    factory: UnitFactory,
    army_id: str,
    datasheet_id: str,
    selection_id: str,
    with_icon: bool,
) -> UnitInstance:
    datasheet = factory.catalog.datasheet_by_id(datasheet_id)
    wargear_selections: tuple[WargearSelection, ...] = ()
    if with_icon:
        icon_option = next(
            option for option in datasheet.wargear_options if "icon-of-excess" in option.option_id
        )
        wargear_selections = (
            WargearSelection(
                option_id=icon_option.option_id,
                model_profile_id=icon_option.model_profile_id,
                wargear_ids=icon_option.allowed_wargear_ids,
            ),
        )
    return factory.instantiate_unit(
        army_id=army_id,
        datasheet=datasheet,
        selection=UnitMusterSelection(
            unit_selection_id=selection_id,
            datasheet_id=datasheet_id,
            model_profile_selections=tuple(
                ModelProfileSelection(entry.model_profile_id, entry.min_models)
                for entry in datasheet.composition
            ),
            wargear_selections=wargear_selections,
        ),
    )


def _instantiate_unit(
    *,
    factory: UnitFactory,
    army_id: str,
    datasheet_id: str,
    selection_id: str,
    model_count: int = 1,
) -> UnitInstance:
    datasheet = factory.catalog.datasheet_by_id(datasheet_id)
    model_profile = datasheet.model_profiles[0]
    return factory.instantiate_unit(
        army_id=army_id,
        datasheet=datasheet,
        selection=UnitMusterSelection(
            unit_selection_id=selection_id,
            datasheet_id=datasheet_id,
            model_profile_selections=(
                ModelProfileSelection(model_profile.model_profile_id, model_count),
            ),
        ),
    )


def _instantiate_minimum_composition_unit(
    *,
    factory: UnitFactory,
    army_id: str,
    datasheet_id: str,
    selection_id: str,
) -> UnitInstance:
    datasheet = factory.catalog.datasheet_by_id(datasheet_id)
    return factory.instantiate_unit(
        army_id=army_id,
        datasheet=datasheet,
        selection=UnitMusterSelection(
            unit_selection_id=selection_id,
            datasheet_id=datasheet_id,
            model_profile_selections=tuple(
                ModelProfileSelection(entry.model_profile_id, entry.min_models)
                for entry in datasheet.composition
            ),
        ),
    )


def _army(
    *,
    catalog: Any,
    army_id: str,
    player_id: str,
    faction_id: str,
    units: tuple[UnitInstance, ...],
    attached_units: tuple[AttachedUnitFormation, ...] = (),
) -> ArmyDefinition:
    return ArmyDefinition(
        army_id=army_id,
        player_id=player_id,
        catalog_id=catalog.catalog_id,
        source_package_id=catalog.source_package_id,
        ruleset_id=catalog.ruleset_id,
        detachment_selection=DetachmentSelection(
            faction_id=faction_id,
            detachment_ids=(f"{faction_id}-fulgrim-test",),
        ),
        force_disposition_id="purge-the-foe",
        units=units,
        attached_units=attached_units,
    )


def _battle_state(
    *,
    armies: tuple[ArmyDefinition, ...],
    phase: BattlePhase,
    active_player_id: str,
    game_id: str,
) -> GameState:
    descriptor = RulesetDescriptor.warhammer_40000_eleventh()
    phases = tuple(descriptor.battle_phase_sequence.phases)
    state = GameState(
        game_id=game_id,
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
        mission_setup=_mission_setup(),
    )
    for army in armies:
        state.record_army_definition(army)
    state.battlefield_state = create_deterministic_battlefield_scenario(
        battlefield_id=f"{game_id}-battlefield",
        armies=armies,
    ).battlefield_state
    return state


def _mission_setup() -> MissionSetup:
    return MissionSetup.from_mission_pack(
        mission_pack=chapter_approved_2026_27_mission_pack(),
        mission_pool_entry_id="mission-take-and-hold-vs-purge-the-foe-layout-3",
        terrain_layout_id="take-and-hold-vs-purge-the-foe-layout-3",
        attacker_player_id="player-a",
        defender_player_id="player-b",
    )


def _weapon_profile(datasheet_id: str, profile_name: str) -> WeaponProfile:
    return next(
        profile
        for wargear in _catalog_package().army_catalog.wargear
        if wargear.wargear_id.startswith(f"{datasheet_id}:")
        for profile in wargear.weapon_profiles
        if profile.name == profile_name
    )


def _attack_pool(
    attacker: UnitInstance,
    target: UnitInstance,
    profile: WeaponProfile,
    *,
    target_unit_instance_id: str | None = None,
) -> RangedAttackPool:
    target_model_ids = target.own_model_ids()
    return RangedAttackPool(
        attacker_model_instance_id=attacker.own_models[0].model_instance_id,
        wargear_id=profile.profile_id.rsplit(":", 1)[0],
        weapon_profile_id=profile.profile_id,
        weapon_profile=profile,
        target_unit_instance_id=(
            target.unit_instance_id if target_unit_instance_id is None else target_unit_instance_id
        ),
        shooting_type=ShootingType.NORMAL,
        attacks=1,
        target_visible_model_ids=target_model_ids,
        target_in_range_model_ids=target_model_ids,
    )


def _leave_one_wound_on_unit(*, state: GameState, unit: UnitInstance) -> str:
    survivor_id = unit.own_models[-1].model_instance_id
    for model in unit.own_models[:-1]:
        destroy_model_by_rule(state=state, model_instance_id=model.model_instance_id)
    survivor = next(
        model
        for model in _unit_from_state(state, unit.unit_instance_id).own_models
        if model.model_instance_id == survivor_id
    )
    if survivor.wounds_remaining > 1:
        apply_damage_to_model(
            state=state,
            target_unit_instance_id=unit.unit_instance_id,
            model_instance_id=survivor_id,
            damage=survivor.wounds_remaining - 1,
            damage_kind=DamageKind.NORMAL,
        )
    assert (
        next(
            model
            for model in _unit_from_state(state, unit.unit_instance_id).own_models
            if model.model_instance_id == survivor_id
        ).wounds_remaining
        == 1
    )
    return survivor_id


def _move_unit(state: GameState, unit_instance_id: str, *, x: float, y: float) -> None:
    battlefield = state.battlefield_state
    assert battlefield is not None
    placement = battlefield.unit_placement_by_id(unit_instance_id)
    moved = replace(
        placement,
        model_placements=tuple(
            replace(model, pose=Pose.at(x=x, y=y + index * 1.5))
            for index, model in enumerate(placement.model_placements)
        ),
    )
    state.replace_battlefield_state(battlefield.with_unit_placement(moved))


def _unit_from_state(state: GameState, unit_instance_id: str) -> UnitInstance:
    return next(
        unit
        for army in state.army_definitions
        for unit in army.units
        if unit.unit_instance_id == unit_instance_id
    )


def _fulgrim_rule_ir(source_row_id: str) -> RuleIR:
    payload = fulgrim_source_package.datasheet_rule_ir_payload_by_source_row_id(source_row_id)
    assert payload is not None
    return RuleIR.from_payload(payload)


@lru_cache(maxsize=1)
def _overlay_artifacts() -> tuple[OverlaySourceArtifact, ...]:
    return apply_source_release_overlays(
        source_artifacts=_wahapedia_source_artifacts(),
        release_manifest=ec_overlay.source_release_manifest(),
        overlay_packs=(ec_overlay.overlay_pack(),),
    )


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
    artifacts: tuple[WahapediaJsonArtifact | OverlaySourceArtifact, ...],
    table_name: str,
) -> WahapediaJsonArtifact | OverlaySourceArtifact:
    for artifact in artifacts:
        if artifact.source_table == table_name:
            return artifact
    raise AssertionError(f"Missing artifact table: {table_name}.")


def _fields(
    artifact: WahapediaJsonArtifact | OverlaySourceArtifact,
    row_id: str,
) -> dict[str, str]:
    return _row_by_id(artifact, row_id).runtime_fields_payload()


def _row_by_id(
    artifact: WahapediaJsonArtifact | OverlaySourceArtifact,
    row_id: str,
) -> NormalizedSourceRow:
    for row in artifact.rows:
        if row.source_row_id == row_id:
            return row
    raise AssertionError(f"Missing source row: {row_id}.")


def _model_fields(
    artifact: WahapediaJsonArtifact | OverlaySourceArtifact,
    *,
    datasheet_id: str,
    name: str,
) -> dict[str, str]:
    return _row_fields_by_values(artifact, {"datasheet_id": datasheet_id, "name": name})


def _wargear_fields(
    artifact: WahapediaJsonArtifact | OverlaySourceArtifact,
    *,
    datasheet_id: str,
    name: str,
) -> dict[str, str]:
    return _row_fields_by_values(artifact, {"datasheet_id": datasheet_id, "name": name})


def _ability_fields(
    artifact: WahapediaJsonArtifact | OverlaySourceArtifact,
    *,
    datasheet_id: str,
    name: str,
) -> dict[str, str]:
    return _row_fields_by_values(artifact, {"datasheet_id": datasheet_id, "name": name})


def _row_fields_by_values(
    artifact: WahapediaJsonArtifact | OverlaySourceArtifact,
    expected: dict[str, str],
) -> dict[str, str]:
    for row in artifact.rows:
        fields = row.runtime_fields_payload()
        if all(fields.get(key) == value for key, value in expected.items()):
            return fields
    raise AssertionError(f"Missing row matching: {expected}.")


def _keyword_set(value: str) -> set[str]:
    return {keyword.strip() for keyword in value.split(",") if keyword.strip()}


def _ec_height_overrides() -> tuple[ModelHeightOverride, ...]:
    return (
        _height_override("000004077", "Fulgrim - EPIC HERO", 5.5),
        _height_override("000004083", "Lucius the Eternal - EPIC HERO", 2.25),
        _height_override("000004084", "Lord Kakophonist", 2.5),
        _height_override("000004088", "Disharmonist", 2.0),
        _height_override("000004088", "Noise Marines", 2.0),
        _height_override("000004079", "Obsessionist", 1.75),
        _height_override("000004079", "Tormentors", 1.75),
        _height_override("000004080", "Obsessionist", 1.75),
        _height_override("000004080", "Infractors", 1.75),
        _height_override("000004081", "Terminator Champion", 2.0),
        _height_override("000004081", "Chaos Terminators", 2.0),
        _height_override("000004082", "Chaos Land Raider", 3.0),
        _height_override("000004089", "Flawless Blades", 2.0),
        _height_override("000004090", "Chaos Spawn", 2.25),
        _height_override("000004092", "Heldrake", 6.0),
        _height_override("000004093", "Chaos Rhino", 2.5),
    )


def _height_override(datasheet_id: str, model_name: str, height: float) -> ModelHeightOverride:
    return ModelHeightOverride(
        datasheet_id=datasheet_id,
        model_name=model_name,
        height=height,
        height_units=GeometrySourceUnits.INCHES,
        height_source_id=f"geometry-review:emperors-children:{datasheet_id}:height",
        height_document_reference="Emperor's Children datasheet overlay bridge regression fixture",
    )
