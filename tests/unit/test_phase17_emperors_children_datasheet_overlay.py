from __future__ import annotations

import json
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

from warhammer40k_core.adapters.local_session import LocalGameSession
from warhammer40k_core.core.attributes import Characteristic
from warhammer40k_core.core.detachment import DetachmentDefinition
from warhammer40k_core.core.model_geometry_catalog import GeometrySourceUnits
from warhammer40k_core.core.ruleset_descriptor import RulesetDescriptor
from warhammer40k_core.core.weapon_profiles import WeaponProfile
from warhammer40k_core.engine.abilities import AbilityCatalogIndex
from warhammer40k_core.engine.ability_catalog import (
    build_player_ability_index,
    catalog_ability_records_from_catalog,
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
from warhammer40k_core.engine.battle_shock_hooks import BattleShockHookRegistry
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
from warhammer40k_core.engine.catalog_selected_target_effects import (
    CatalogSelectedTargetEffectRuntime,
    apply_catalog_post_shoot_hit_target_effect_result,
)
from warhammer40k_core.engine.command_phase_start_hooks import (
    CommandPhaseStartEffectContext,
    CommandPhaseStartHookRegistry,
    CommandPhaseStartRequestContext,
    CommandPhaseStartResultContext,
)
from warhammer40k_core.engine.decision_controller import (
    DecisionController,
    DecisionControllerPayload,
)
from warhammer40k_core.engine.decision_request import DecisionRequest
from warhammer40k_core.engine.decision_result import DecisionResult, DecisionResultPayload
from warhammer40k_core.engine.dice import DiceRollManager
from warhammer40k_core.engine.event_log import JsonValue
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
from warhammer40k_core.engine.list_validation import DetachmentSelection, UnitMusterSelection
from warhammer40k_core.engine.mission_setup import MissionSetup
from warhammer40k_core.engine.movement_proposals import (
    MOVEMENT_PROPOSAL_DECISION_TYPE,
    MovementProposalRequest,
)
from warhammer40k_core.engine.phase import (
    BattlePhase,
    GameLifecycleStage,
    LifecycleStatus,
    LifecycleStatusKind,
)
from warhammer40k_core.engine.placement import create_deterministic_battlefield_scenario
from warhammer40k_core.engine.reaction_queue import ReactionQueue
from warhammer40k_core.engine.replay import ReplayArtifact, ReplayArtifactPayload, ReplayRunner
from warhammer40k_core.engine.rule_execution import rule_ir_from_execution_payload
from warhammer40k_core.engine.runtime_modifiers import (
    HitRollModifierContext,
    RuntimeModifierRegistry,
)
from warhammer40k_core.engine.shooting_types import ShootingType
from warhammer40k_core.engine.stratagems import (
    DECLINE_STRATAGEM_WINDOW_OPTION_ID,
    STRATAGEM_DECISION_TYPE,
)
from warhammer40k_core.engine.unit_factory import UnitFactory, UnitInstance
from warhammer40k_core.engine.wargear_selections import ModelProfileSelection
from warhammer40k_core.engine.weapon_declaration import RangedAttackPool
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
    "000004089",
    "000004090",
    "000004092",
    "000004093",
)
_BRIDGE_SUPPORTED_EC_DATASHEET_IDS = (
    "000004077",
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
) -> RangedAttackPool:
    target_model_ids = target.own_model_ids()
    return RangedAttackPool(
        attacker_model_instance_id=attacker.own_models[0].model_instance_id,
        wargear_id=profile.profile_id.rsplit(":", 1)[0],
        weapon_profile_id=profile.profile_id,
        weapon_profile=profile,
        target_unit_instance_id=target.unit_instance_id,
        shooting_type=ShootingType.NORMAL,
        attacks=1,
        target_visible_model_ids=target_model_ids,
        target_in_range_model_ids=target_model_ids,
    )


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
