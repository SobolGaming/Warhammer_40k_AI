from __future__ import annotations

import json
from dataclasses import dataclass, replace
from functools import cache
from typing import Any, cast

import pytest
from tools.generate_ability_support_matrix import (
    _ability_support_catalog_package,  # pyright: ignore[reportPrivateUsage]
)
from tools.generate_aeldari_wave_serpent_shining_spears_eldrad_dire_avengers_rule_ir import (
    BLADESTORM_ROW_ID,
    DIRE_AVENGERS_DATASHEET_ID,
    DOOM_ROW_ID,
    ELDRAD_ULTHRAN_DATASHEET_ID,
    EXTREME_MOBILITY_ROW_ID,
    OUTPUT_PATH,
    SHINING_SPEARS_DATASHEET_ID,
    WAVE_SERPENT_DATASHEET_ID,
    WAVE_SERPENT_SHIELD_ROW_ID,
    generated_artifact_payload,
)

from warhammer40k_core.adapters.event_stream import EventStreamCursor
from warhammer40k_core.adapters.local_session import LocalGameSession
from warhammer40k_core.core.army_catalog import ArmyCatalog
from warhammer40k_core.core.detachment import DetachmentDefinition
from warhammer40k_core.core.ruleset_descriptor import (
    BattlePhaseKind,
    MovementMode,
    RulesetDescriptor,
)
from warhammer40k_core.core.weapon_profiles import WeaponKeyword
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
from warhammer40k_core.engine.battlefield_state import (
    ModelDisplacementKind,
    geometry_model_for_placement,
)
from warhammer40k_core.engine.catalog_datasheet_rule_runtime import CatalogDatasheetRuleRuntime
from warhammer40k_core.engine.catalog_movement_end_selected_target_effects import (
    CATALOG_MOVEMENT_END_SELECTED_TARGET_EFFECT_SELECTED_EVENT,
    SELECT_CATALOG_MOVEMENT_END_TARGET_EFFECT_DECISION_TYPE,
)
from warhammer40k_core.engine.catalog_rule_consumption import (
    CATALOG_IR_MOVEMENT_END_SELECTED_TARGET_EFFECT_CONSUMER_ID,
    CATALOG_IR_WEAPON_KEYWORD_GRANT_CONSUMER_ID,
    CATALOG_IR_WOUND_ROLL_MODIFIER_CONSUMER_ID,
    catalog_rule_ir_consumers_for_rule,
)
from warhammer40k_core.engine.decision_controller import DecisionController
from warhammer40k_core.engine.decision_result import DecisionResult
from warhammer40k_core.engine.effects import EffectExpirationBoundary
from warhammer40k_core.engine.game_state import GameConfig, GameState
from warhammer40k_core.engine.lifecycle import GameLifecycle
from warhammer40k_core.engine.list_validation import (
    DetachmentSelection,
    UnitMusterSelection,
)
from warhammer40k_core.engine.mission_setup import MissionSetup
from warhammer40k_core.engine.movement_legality import MovementLegalityContext
from warhammer40k_core.engine.phase import (
    BattlePhase,
    GameLifecycleStage,
    LifecycleStatusKind,
)
from warhammer40k_core.engine.phases.movement import (
    MovementPhaseActionKind,
    MovementPhaseState,
)
from warhammer40k_core.engine.placement import create_deterministic_battlefield_scenario
from warhammer40k_core.engine.replay import ReplayRunner, ReplayRunStatus
from warhammer40k_core.engine.runtime_modifiers import (
    RuntimeModifierRegistry,
    WeaponProfileModifierContext,
    WoundRollModifierContext,
)
from warhammer40k_core.engine.unit_factory import UnitFactory, UnitFactoryError, UnitInstance
from warhammer40k_core.engine.wargear_selections import (
    ModelProfileSelection,
    WargearSelection,
)
from warhammer40k_core.geometry.pathing import PathWitness
from warhammer40k_core.geometry.pose import Pose
from warhammer40k_core.rules.mission_pack_import import chapter_approved_2026_27_mission_pack
from warhammer40k_core.rules.rule_ir import RuleIR
from warhammer40k_core.rules.source_packages.warhammer_40000_11th import (
    aeldari_wave_serpent_shining_spears_eldrad_dire_avengers_2026_06 as source_package,
)
from warhammer40k_core.rules.wahapedia_bridge_defaults import (
    AELDARI_WAVE_SERPENT_SHINING_SPEARS_ELDRAD_DIRE_AVENGERS_HEIGHT_OVERRIDES,
)

TEST_DETACHMENT_ID = "aeldari-four-datasheets-test"
ELDRAD_DIRE_AVENGERS_ATTACHED_ID = "attached-unit:army-a:eldrad-dire-avengers"


@dataclass(frozen=True, slots=True)
class _RuntimeFixture:
    catalog: Any
    armies: tuple[ArmyDefinition, ...]
    state: GameState
    indexes: dict[str, Any]
    eldrad: UnitInstance
    dire_avengers: UnitInstance
    wave_serpent: UnitInstance
    shining_spears: UnitInstance
    enemy_one: UnitInstance
    enemy_two: UnitInstance


def test_generated_rule_ir_artifact_is_current_hashed_and_exactly_consumed() -> None:
    committed = cast(dict[str, Any], json.loads(OUTPUT_PATH.read_text(encoding="utf-8")))

    assert committed == generated_artifact_payload()
    assert committed["package_hash"] == source_package.PACKAGE_HASH
    assert source_package.supported_datasheet_source_row_ids() == (
        DOOM_ROW_ID,
        BLADESTORM_ROW_ID,
        WAVE_SERPENT_SHIELD_ROW_ID,
        EXTREME_MOBILITY_ROW_ID,
    )
    assert catalog_rule_ir_consumers_for_rule(_rule_ir(DOOM_ROW_ID)) == (
        CATALOG_IR_MOVEMENT_END_SELECTED_TARGET_EFFECT_CONSUMER_ID,
    )
    assert catalog_rule_ir_consumers_for_rule(_rule_ir(BLADESTORM_ROW_ID)) == (
        CATALOG_IR_WEAPON_KEYWORD_GRANT_CONSUMER_ID,
        f"{CATALOG_IR_WEAPON_KEYWORD_GRANT_CONSUMER_ID}:sustained-hits",
    )
    assert catalog_rule_ir_consumers_for_rule(_rule_ir(WAVE_SERPENT_SHIELD_ROW_ID)) == (
        CATALOG_IR_WOUND_ROLL_MODIFIER_CONSUMER_ID,
    )
    assert catalog_rule_ir_consumers_for_rule(_rule_ir(EXTREME_MOBILITY_ROW_ID)) == (
        "catalog-ir:movement-transit-permission",
    )


def test_generated_rule_ir_loader_rejects_hash_and_source_identity_drift() -> None:
    payload = cast(dict[str, Any], json.loads(OUTPUT_PATH.read_text(encoding="utf-8")))
    payload["package_hash"] = "0" * 64
    with pytest.raises(source_package.AeldariFourDatasheetsRuleIrArtifactError, match="stale"):
        source_package.validate_generated_artifact_bytes(json.dumps(payload).encode())

    payload = cast(dict[str, Any], json.loads(OUTPUT_PATH.read_text(encoding="utf-8")))
    payload["source_package_id"] = "source:drift"
    payload["package_hash"] = _package_hash(payload)
    with pytest.raises(
        source_package.AeldariFourDatasheetsRuleIrArtifactError,
        match="source package identity drifted",
    ):
        source_package.validate_generated_artifact_bytes(json.dumps(payload).encode())


def test_catalog_is_full_with_geometry_profiles_and_typed_dire_avenger_options() -> None:
    package = _package()
    catalog = package.army_catalog
    expected_profiles = {
        ELDRAD_ULTHRAN_DATASHEET_ID: {"Eldrad Ulthran - EPIC HERO"},
        DIRE_AVENGERS_DATASHEET_ID: {"Dire Avenger Exarch", "Dire Avengers"},
        WAVE_SERPENT_DATASHEET_ID: {"Wave Serpent"},
        SHINING_SPEARS_DATASHEET_ID: {"Shining Spear Exarch", "Shining Spears"},
    }
    for datasheet_id, profile_names in expected_profiles.items():
        datasheet = catalog.datasheet_by_id(datasheet_id)
        assert {profile.name for profile in datasheet.model_profiles} == profile_names
        assert all(ability.support.value != "unsupported" for ability in datasheet.abilities)

    assert {
        (row.datasheet_id, row.model_name, row.height)
        for row in AELDARI_WAVE_SERPENT_SHINING_SPEARS_ELDRAD_DIRE_AVENGERS_HEIGHT_OVERRIDES
    } == {
        (ELDRAD_ULTHRAN_DATASHEET_ID, "Eldrad Ulthran - EPIC HERO", 2.25),
        (DIRE_AVENGERS_DATASHEET_ID, "Dire Avenger Exarch", 2.0),
        (DIRE_AVENGERS_DATASHEET_ID, "Dire Avengers", 2.0),
        (WAVE_SERPENT_DATASHEET_ID, "Wave Serpent", 2.75),
        (SHINING_SPEARS_DATASHEET_ID, "Shining Spear Exarch", 3.25),
        (SHINING_SPEARS_DATASHEET_ID, "Shining Spears", 3.25),
    }

    factory = UnitFactory(catalog=catalog, model_geometries=package.model_geometries)
    paired = _dire_avenger_selection(
        selection_id="dire-paired",
        wargear_selections=(
            WargearSelection(
                option_id=(
                    f"{DIRE_AVENGERS_DATASHEET_ID}:dire-avenger-exarch-replacement-"
                    "shuriken-pistol-diresword:option-1"
                ),
                model_profile_id=f"{DIRE_AVENGERS_DATASHEET_ID}:dire-avenger-exarch",
                wargear_ids=(
                    f"{DIRE_AVENGERS_DATASHEET_ID}:shuriken-pistol",
                    f"{DIRE_AVENGERS_DATASHEET_ID}:diresword",
                ),
            ),
            WargearSelection(
                option_id=(
                    f"{DIRE_AVENGERS_DATASHEET_ID}:dire-avenger-exarch-shimmershield:option-3"
                ),
                model_profile_id=f"{DIRE_AVENGERS_DATASHEET_ID}:dire-avenger-exarch",
                wargear_ids=(f"{DIRE_AVENGERS_DATASHEET_ID}:shimmershield",),
            ),
        ),
    )
    unit = factory.instantiate_unit(
        army_id="army-options",
        datasheet=catalog.datasheet_by_id(DIRE_AVENGERS_DATASHEET_ID),
        selection=paired,
    )
    exarch = next(
        model for model in unit.own_models if model.model_profile_id.endswith("dire-avenger-exarch")
    )
    assert f"{DIRE_AVENGERS_DATASHEET_ID}:avenger-shuriken-catapult" not in exarch.wargear_ids
    assert f"{DIRE_AVENGERS_DATASHEET_ID}:shuriken-pistol" not in exarch.wargear_ids
    assert {
        f"{DIRE_AVENGERS_DATASHEET_ID}:diresword",
        f"{DIRE_AVENGERS_DATASHEET_ID}:shimmershield",
    }.issubset(exarch.wargear_ids)

    dual = factory.instantiate_unit(
        army_id="army-options",
        datasheet=catalog.datasheet_by_id(DIRE_AVENGERS_DATASHEET_ID),
        selection=_dire_avenger_selection(
            selection_id="dire-dual",
            wargear_selections=(
                WargearSelection(
                    option_id=(f"{DIRE_AVENGERS_DATASHEET_ID}:avenger-shuriken-catapult:option-2"),
                    model_profile_id=f"{DIRE_AVENGERS_DATASHEET_ID}:dire-avenger-exarch",
                    wargear_ids=(f"{DIRE_AVENGERS_DATASHEET_ID}:avenger-shuriken-catapult",),
                ),
            ),
        ),
    )
    dual_exarch = next(
        model for model in dual.own_models if model.model_profile_id.endswith("dire-avenger-exarch")
    )
    assert (
        dual_exarch.wargear_ids.count(f"{DIRE_AVENGERS_DATASHEET_ID}:avenger-shuriken-catapult")
        == 2
    )

    with pytest.raises(UnitFactoryError, match="fewer eligible model bearers"):
        UnitFactory(catalog=catalog, model_geometries=package.model_geometries).instantiate_unit(
            army_id="army-options",
            datasheet=catalog.datasheet_by_id(DIRE_AVENGERS_DATASHEET_ID),
            selection=replace(
                paired,
                unit_selection_id="dire-invalid",
                wargear_selections=(
                    paired.wargear_selections[0],
                    WargearSelection(
                        option_id=(
                            f"{DIRE_AVENGERS_DATASHEET_ID}:dire-avenger-exarch-replacement-"
                            "shuriken-pistol-power-glaive:option-1"
                        ),
                        model_profile_id=f"{DIRE_AVENGERS_DATASHEET_ID}:dire-avenger-exarch",
                        wargear_ids=(
                            f"{DIRE_AVENGERS_DATASHEET_ID}:shuriken-pistol",
                            f"{DIRE_AVENGERS_DATASHEET_ID}:power-glaive",
                        ),
                    ),
                ),
            ),
        )


def test_bladestorm_and_wave_serpent_shield_use_live_attack_context() -> None:
    fixture = _runtime_fixture()
    runtime = CatalogDatasheetRuleRuntime(fixture.indexes, fixture.armies)

    bladestorm_source = _rule_ir(BLADESTORM_ROW_ID).source_id
    bladestorm = next(
        binding
        for binding in runtime.weapon_profile_modifier_bindings()
        if binding.source_id == bladestorm_source
    )
    catapult = _weapon_profile(DIRE_AVENGERS_DATASHEET_ID, "Avenger shuriken catapult")
    dire_model = fixture.dire_avengers.own_models[0]
    within = WeaponProfileModifierContext(
        state=fixture.state,
        source_phase=BattlePhase.SHOOTING,
        attacking_unit_instance_id=fixture.dire_avengers.unit_instance_id,
        attacker_model_instance_id=dire_model.model_instance_id,
        target_unit_instance_id=fixture.enemy_one.unit_instance_id,
        weapon_profile=catapult,
    )
    modified = bladestorm.handler(within)
    assert WeaponKeyword.SUSTAINED_HITS in modified.keywords
    assert "sustained-hits:1" in {ability.ability_id for ability in modified.abilities}
    assert (
        bladestorm.handler(
            replace(within, target_unit_instance_id=fixture.enemy_two.unit_instance_id)
        )
        == catapult
    )
    assert (
        bladestorm.handler(
            replace(within, weapon_profile=_weapon_profile(DIRE_AVENGERS_DATASHEET_ID, "Diresword"))
        ).keywords
        == _weapon_profile(DIRE_AVENGERS_DATASHEET_ID, "Diresword").keywords
    )
    assert (
        bladestorm.handler(
            replace(
                within,
                attacking_unit_instance_id=fixture.eldrad.unit_instance_id,
                attacker_model_instance_id=fixture.eldrad.own_models[0].model_instance_id,
            )
        )
        == catapult
    )

    registry = RuntimeModifierRegistry.from_bindings(
        wound_roll_modifier_bindings=runtime.wound_roll_modifier_bindings()
    )
    bright_lance = _weapon_profile(WAVE_SERPENT_DATASHEET_ID, "Twin bright lance")
    wound = WoundRollModifierContext(
        state=fixture.state,
        source_phase=BattlePhase.SHOOTING,
        attacking_unit_instance_id=fixture.wave_serpent.unit_instance_id,
        attacker_model_instance_id=fixture.wave_serpent.own_models[0].model_instance_id,
        target_unit_instance_id=fixture.enemy_one.unit_instance_id,
        weapon_profile=bright_lance,
        strength=12,
        toughness=9,
    )
    assert registry.wound_roll_modifier(wound) == -1
    assert registry.wound_roll_modifier(replace(wound, strength=9)) == 0
    assert (
        registry.wound_roll_modifier(
            replace(
                wound,
                weapon_profile=_weapon_profile(WAVE_SERPENT_DATASHEET_ID, "Wraithbone hull"),
            )
        )
        == 0
    )
    assert (
        registry.wound_roll_modifier(
            replace(wound, target_unit_instance_id=fixture.dire_avengers.unit_instance_id)
        )
        == 0
    )


def test_bladestorm_this_unit_scope_includes_attached_leader_models() -> None:
    fixture = _runtime_fixture(attach_eldrad_to_dire_avengers=True)
    _move_unit_to(
        fixture.state,
        unit_instance_id=fixture.eldrad.unit_instance_id,
        x=4.0,
        y=4.0,
    )
    runtime = CatalogDatasheetRuleRuntime(fixture.indexes, fixture.armies)
    bladestorm = next(
        binding
        for binding in runtime.weapon_profile_modifier_bindings()
        if binding.source_id == _rule_ir(BLADESTORM_ROW_ID).source_id
    )
    catapult = _weapon_profile(DIRE_AVENGERS_DATASHEET_ID, "Avenger shuriken catapult")

    modified = bladestorm.handler(
        WeaponProfileModifierContext(
            state=fixture.state,
            source_phase=BattlePhase.SHOOTING,
            attacking_unit_instance_id=ELDRAD_DIRE_AVENGERS_ATTACHED_ID,
            attacker_model_instance_id=fixture.eldrad.own_models[0].model_instance_id,
            target_unit_instance_id=fixture.enemy_one.unit_instance_id,
            weapon_profile=catapult,
        )
    )

    assert WeaponKeyword.SUSTAINED_HITS in modified.keywords
    assert "sustained-hits:1" in {ability.ability_id for ability in modified.abilities}


@pytest.mark.parametrize(
    "movement_mode",
    [MovementMode.NORMAL, MovementMode.ADVANCE, MovementMode.FALL_BACK, MovementMode.CHARGE],
)
def test_extreme_mobility_ignores_vertical_distance_with_path_evidence(
    movement_mode: MovementMode,
) -> None:
    fixture = _runtime_fixture()
    descriptor = RulesetDescriptor.warhammer_40000_eleventh()
    descriptor = replace(
        descriptor,
        fly_policy=replace(descriptor.fly_policy, ignores_vertical_distance=False),
        descriptor_hash="",
    )
    model = fixture.shining_spears.own_models[0]
    legality = MovementLegalityContext.from_keywords(
        keywords=(*fixture.shining_spears.keywords, *fixture.shining_spears.faction_keywords),
        ruleset_descriptor=descriptor,
        movement_mode=movement_mode,
        movement_phase_action=(
            None
            if movement_mode is MovementMode.CHARGE
            else {
                MovementMode.NORMAL: MovementPhaseActionKind.NORMAL_MOVE.value,
                MovementMode.ADVANCE: MovementPhaseActionKind.ADVANCE.value,
                MovementMode.FALL_BACK: MovementPhaseActionKind.FALL_BACK.value,
            }[movement_mode]
        ),
        displacement_kind={
            MovementMode.NORMAL: ModelDisplacementKind.NORMAL_MOVE,
            MovementMode.ADVANCE: ModelDisplacementKind.ADVANCE,
            MovementMode.FALL_BACK: ModelDisplacementKind.FALL_BACK,
            MovementMode.CHARGE: ModelDisplacementKind.CHARGE_MOVE,
        }[movement_mode],
        ability_index=fixture.indexes["player-a"],
        unit=fixture.shining_spears,
        model_instance_id=model.model_instance_id,
        current_model_instance_ids=tuple(
            current.model_instance_id for current in fixture.shining_spears.own_models
        ),
        owner_player_id="player-a",
    )
    assert legality.capabilities.ignores_vertical_distance

    battlefield = fixture.state.battlefield_state
    assert battlefield is not None
    placement = battlefield.unit_placement_by_id(fixture.shining_spears.unit_instance_id)
    model_placement = next(
        current
        for current in placement.model_placements
        if current.model_instance_id == model.model_instance_id
    )
    start = model_placement.pose
    witness = PathWitness.for_paths(
        (
            (
                model.model_instance_id,
                (
                    start,
                    Pose.at(
                        x=start.position.x + 3.0,
                        y=start.position.y,
                        z=start.position.z + 10.0,
                    ),
                    Pose.at(
                        x=start.position.x + 6.0,
                        y=start.position.y,
                        z=start.position.z + 20.0,
                    ),
                ),
            ),
        )
    )
    path_context = legality.to_path_validation_context(
        moving_model=geometry_model_for_placement(model=model, placement=model_placement),
        witness=witness,
        battlefield_width_inches=battlefield.battlefield_width_inches,
        battlefield_depth_inches=battlefield.battlefield_depth_inches,
        movement_distance_budget_inches=7.0,
    )
    assert path_context.ignores_vertical_distance
    validation = path_context.validate()
    assert validation.is_valid
    assert validation.movement_distance_witness is not None
    assert validation.movement_distance_witness.budget is not None
    assert validation.movement_distance_witness.total_distance_inches == 6.0
    assert validation.movement_distance_witness.budget.max_distance_inches == 7.0
    assert (
        witness.poses_for_model(model.model_instance_id)[-1].position.z == start.position.z + 20.0
    )
    assert (
        not replace(
            path_context,
            ignores_vertical_distance=False,
        )
        .validate()
        .is_valid
    )
    assert path_context.to_payload()["ignores_vertical_distance"] is True


def test_doom_submits_through_local_session_rejects_drift_replays_and_expires() -> None:
    fixture = _runtime_fixture()
    lifecycle = _lifecycle_for_fixture(fixture)
    state = lifecycle.state
    assert state is not None
    session = LocalGameSession(lifecycle=lifecycle)
    pending = session.advance_until_decision_or_terminal()
    request = pending.decision_request
    assert request is not None
    assert request.decision_type == SELECT_CATALOG_MOVEMENT_END_TARGET_EFFECT_DECISION_TYPE
    assert request.actor_id == "player-a"
    request_payload = cast(dict[str, Any], request.payload)
    assert request_payload["available_target_unit_instance_ids"] == [
        fixture.enemy_one.unit_instance_id,
        fixture.enemy_two.unit_instance_id,
    ]
    assert session.view(viewer_player_id="player-a")["pending_decision"] is not None
    opponent_view = session.view(viewer_player_id="player-b")["pending_decision"]
    assert opponent_view is not None
    assert opponent_view["actor_id"] == "player-a"

    option = next(
        option
        for option in request.options
        if cast(dict[str, Any], option.payload)["selected_catalog_target_effect"][
            "target_unit_instance_id"
        ]
        == fixture.enemy_one.unit_instance_id
    )
    drifted_payload = cast(dict[str, Any], json.loads(json.dumps(option.payload)))
    selected = cast(dict[str, Any], drifted_payload["selected_catalog_target_effect"])
    selected["target_unit_instance_id"] = fixture.enemy_two.unit_instance_id
    invalid = session.lifecycle.submit_decision(
        replace(
            DecisionResult.for_request(
                result_id="result:doom-drift",
                request=request,
                selected_option_id=option.option_id,
            ),
            payload=drifted_payload,
        )
    )
    assert invalid.status_kind is LifecycleStatusKind.INVALID
    assert lifecycle.pending_decision_request() == request
    assert not state.persisting_effects

    submitted = session.submit_option(
        request_id=request.request_id,
        option_id=option.option_id,
        result_id="result:doom:enemy-one",
    )
    assert submitted.status_kind is LifecycleStatusKind.WAITING_FOR_DECISION
    state = cast(GameState, lifecycle.state)
    assert state.persisting_effects
    doom_effects = tuple(
        effect
        for effect in state.persisting_effects
        if effect.source_rule_id == request_payload["source_rule_id"]
    )
    assert len(doom_effects) == 1
    assert (
        cast(dict[str, Any], doom_effects[0].effect_payload)["rule_id"]
        == _rule_ir(DOOM_ROW_ID).rule_id
    )
    assert doom_effects[0].expiration.battle_round == 2
    assert doom_effects[0].expiration.phase is BattlePhaseKind.COMMAND
    assert doom_effects[0].expiration.player_id == "player-a"

    registry = RuntimeModifierRegistry.empty()
    catapult = _weapon_profile(DIRE_AVENGERS_DATASHEET_ID, "Avenger shuriken catapult")
    wound = WoundRollModifierContext(
        state=state,
        source_phase=BattlePhase.SHOOTING,
        attacking_unit_instance_id=fixture.dire_avengers.unit_instance_id,
        attacker_model_instance_id=fixture.dire_avengers.own_models[0].model_instance_id,
        target_unit_instance_id=fixture.enemy_one.unit_instance_id,
        weapon_profile=catapult,
        strength=4,
        toughness=9,
    )
    assert registry.wound_roll_modifier(wound) == 1
    assert (
        registry.wound_roll_modifier(
            replace(wound, target_unit_instance_id=fixture.enemy_two.unit_instance_id)
        )
        == 0
    )

    record_payload = session.lifecycle.decision_controller.records[-1].to_payload()
    record_json = json.dumps(record_payload, sort_keys=True)
    assert "object at 0x" not in record_json
    player_a_events = session.events_since(EventStreamCursor(), viewer_player_id="player-a")
    player_b_events = session.events_since(EventStreamCursor(), viewer_player_id="player-b")
    assert [
        event
        for event in player_a_events["events"]
        if event["event_type"] == CATALOG_MOVEMENT_END_SELECTED_TARGET_EFFECT_SELECTED_EVENT
    ] == [
        event
        for event in player_b_events["events"]
        if event["event_type"] == CATALOG_MOVEMENT_END_SELECTED_TARGET_EFFECT_SELECTED_EVENT
    ]
    replay = ReplayRunner.from_payload(
        session.replay_artifact(artifact_id="replay:aeldari:doom")
    ).run()
    assert replay.status is ReplayRunStatus.REPRODUCED

    state.expire_persisting_effects_at_boundary(
        EffectExpirationBoundary.phase_start(
            battle_round=2,
            phase=BattlePhaseKind.COMMAND,
            player_id="player-a",
        )
    )
    assert registry.wound_roll_modifier(wound) == 0


def test_doom_benefits_known_aeldari_unit_placed_after_target_selection() -> None:
    fixture = _runtime_fixture()
    lifecycle = _lifecycle_for_fixture(fixture)
    state = cast(GameState, lifecycle.state)
    battlefield = state.battlefield_state
    assert battlefield is not None
    arriving_placement = battlefield.unit_placement_by_id(fixture.shining_spears.unit_instance_id)
    reserve_state = state.reposition_unit_to_strategic_reserves(
        player_id="player-a",
        unit_instance_id=fixture.shining_spears.unit_instance_id,
        source_rule_ids=("test:doom:later-placed-beneficiary",),
    )
    session = LocalGameSession(lifecycle=lifecycle)
    pending = session.advance_until_decision_or_terminal()
    request = pending.decision_request
    assert request is not None
    option = next(
        option
        for option in request.options
        if cast(dict[str, Any], option.payload)["selected_catalog_target_effect"][
            "target_unit_instance_id"
        ]
        == fixture.enemy_one.unit_instance_id
    )

    session.submit_option(
        request_id=request.request_id,
        option_id=option.option_id,
        result_id="result:doom:later-placed-shining-spears",
    )

    doom_effect = next(
        effect
        for effect in state.persisting_effects
        if effect.source_rule_id == cast(dict[str, Any], request.payload)["source_rule_id"]
    )
    assert fixture.shining_spears.unit_instance_id in doom_effect.target_unit_instance_ids
    current_battlefield = state.battlefield_state
    assert current_battlefield is not None
    state.replace_battlefield_state(
        current_battlefield.with_added_unit_placement(arriving_placement)
    )
    state.replace_reserve_state(
        reserve_state.mark_arrived(
            battle_round=state.battle_round,
            phase=BattlePhase.MOVEMENT,
            large_model_exception_used=False,
            post_arrival_restrictions=(),
        )
    )
    wound = WoundRollModifierContext(
        state=state,
        source_phase=BattlePhase.SHOOTING,
        attacking_unit_instance_id=fixture.shining_spears.unit_instance_id,
        attacker_model_instance_id=fixture.shining_spears.own_models[0].model_instance_id,
        target_unit_instance_id=fixture.enemy_one.unit_instance_id,
        weapon_profile=_weapon_profile(DIRE_AVENGERS_DATASHEET_ID, "Avenger shuriken catapult"),
        strength=4,
        toughness=9,
    )

    assert RuntimeModifierRegistry.empty().wound_roll_modifier(wound) == 1


@cache
def _package() -> Any:
    generated = _ability_support_catalog_package()
    catalog = generated.army_catalog
    aeldari_datasheet_ids = tuple(
        datasheet.datasheet_id
        for datasheet in catalog.datasheets
        if "ASURYANI" in datasheet.keywords.faction_keywords
    )
    return replace(
        generated,
        army_catalog=ArmyCatalog(
            catalog_id="aeldari-four-datasheets-test-catalog",
            ruleset_id=catalog.ruleset_id,
            source_package_id=catalog.source_package_id,
            datasheets=catalog.datasheets,
            wargear=catalog.wargear,
            factions=catalog.factions,
            army_rules=catalog.army_rules,
            detachments=(
                DetachmentDefinition(
                    detachment_id=TEST_DETACHMENT_ID,
                    name="Aeldari Four Datasheets Test",
                    faction_id="AE",
                    detachment_point_cost=1,
                    unit_datasheet_ids=aeldari_datasheet_ids,
                    force_disposition_ids=("purge-the-foe",),
                    source_ids=("test:aeldari-four-datasheets-detachment",),
                ),
            ),
            source_ids=catalog.source_ids,
        ),
    )


def _rule_ir(source_row_id: str) -> RuleIR:
    payload = source_package.datasheet_rule_ir_payload_by_source_row_id(source_row_id)
    assert payload is not None
    return RuleIR.from_payload(payload)


def _package_hash(payload: dict[str, Any]) -> str:
    import hashlib

    normalized = dict(payload)
    normalized["package_hash"] = ""
    return hashlib.sha256(
        json.dumps(normalized, sort_keys=True, separators=(",", ":")).encode()
    ).hexdigest()


def _dire_avenger_selection(
    *,
    selection_id: str,
    wargear_selections: tuple[WargearSelection, ...] = (),
) -> UnitMusterSelection:
    return UnitMusterSelection(
        unit_selection_id=selection_id,
        datasheet_id=DIRE_AVENGERS_DATASHEET_ID,
        model_profile_selections=(
            ModelProfileSelection(f"{DIRE_AVENGERS_DATASHEET_ID}:dire-avenger-exarch", 1),
            ModelProfileSelection(f"{DIRE_AVENGERS_DATASHEET_ID}:dire-avengers", 4),
        ),
        wargear_selections=wargear_selections,
    )


def _minimum_selection(datasheet_id: str, *, selection_id: str) -> UnitMusterSelection:
    datasheet = _package().army_catalog.datasheet_by_id(datasheet_id)
    return UnitMusterSelection(
        unit_selection_id=selection_id,
        datasheet_id=datasheet_id,
        model_profile_selections=tuple(
            ModelProfileSelection(entry.model_profile_id, entry.min_models)
            for entry in datasheet.composition
        ),
    )


def _wave_serpent_selection(
    *, selection_id: str, twin_bright_lance: bool = False
) -> UnitMusterSelection:
    base = _minimum_selection(WAVE_SERPENT_DATASHEET_ID, selection_id=selection_id)
    if not twin_bright_lance:
        return base
    return replace(
        base,
        wargear_selections=(
            WargearSelection(
                option_id=(
                    f"{WAVE_SERPENT_DATASHEET_ID}:twin-shuriken-cannon-twin-bright-lance:option-1"
                ),
                model_profile_id=f"{WAVE_SERPENT_DATASHEET_ID}:wave-serpent",
                wargear_ids=(f"{WAVE_SERPENT_DATASHEET_ID}:twin-bright-lance",),
            ),
        ),
    )


def _muster_request(
    *, army_id: str, player_id: str, selections: tuple[UnitMusterSelection, ...]
) -> ArmyMusterRequest:
    catalog = _package().army_catalog
    return ArmyMusterRequest(
        army_id=army_id,
        player_id=player_id,
        catalog_id=catalog.catalog_id,
        source_package_id=catalog.source_package_id,
        ruleset_id=catalog.ruleset_id,
        detachment_selection=DetachmentSelection(
            faction_id="AE",
            detachment_ids=(TEST_DETACHMENT_ID,),
        ),
        force_disposition_id="purge-the-foe",
        unit_selections=selections,
    )


def _runtime_fixture(*, attach_eldrad_to_dire_avengers: bool = False) -> _RuntimeFixture:
    package = _package()
    catalog = package.army_catalog
    player_a_request = _muster_request(
        army_id="army-a",
        player_id="player-a",
        selections=(
            _minimum_selection(ELDRAD_ULTHRAN_DATASHEET_ID, selection_id="eldrad"),
            _dire_avenger_selection(selection_id="dire-avengers"),
            _wave_serpent_selection(selection_id="wave-serpent", twin_bright_lance=True),
            _minimum_selection(SHINING_SPEARS_DATASHEET_ID, selection_id="shining-spears"),
        ),
    )
    player_b_request = _muster_request(
        army_id="army-b",
        player_id="player-b",
        selections=(
            _wave_serpent_selection(selection_id="enemy-one"),
            _wave_serpent_selection(selection_id="enemy-two"),
        ),
    )
    armies = (
        muster_army(catalog=catalog, request=player_a_request),
        muster_army(catalog=catalog, request=player_b_request),
    )
    if attach_eldrad_to_dire_avengers:
        player_a_units = {unit.unit_instance_id: unit for unit in armies[0].units}
        eldrad = player_a_units["army-a:eldrad"]
        dire_avengers = player_a_units["army-a:dire-avengers"]
        formation = AttachedUnitFormation(
            attached_unit_instance_id=ELDRAD_DIRE_AVENGERS_ATTACHED_ID,
            bodyguard_unit_instance_id=dire_avengers.unit_instance_id,
            leader_unit_instance_ids=(eldrad.unit_instance_id,),
            component_unit_instance_ids=tuple(
                sorted((dire_avengers.unit_instance_id, eldrad.unit_instance_id))
            ),
            source_id="test:bladestorm:attached-unit",
            attachment_source_ids=("test:bladestorm:leader-eligibility",),
        )
        armies = (replace(armies[0], attached_units=(formation,)), armies[1])
    state = _state_for_armies(armies)
    units = {unit.unit_instance_id: unit for army in armies for unit in army.units}
    eldrad = units["army-a:eldrad"]
    dire_avengers = units["army-a:dire-avengers"]
    wave_serpent = units["army-a:wave-serpent"]
    shining_spears = units["army-a:shining-spears"]
    enemy_one = units["army-b:enemy-one"]
    enemy_two = units["army-b:enemy-two"]
    for unit, x, y in (
        (eldrad, 2.0, 2.0),
        (dire_avengers, 2.0, 10.0),
        (shining_spears, 2.0, 30.0),
        (wave_serpent, 2.0, 42.0),
        (enemy_one, 8.0, 10.0),
        (enemy_two, 15.0, 10.0),
    ):
        _move_unit_to(state, unit_instance_id=unit.unit_instance_id, x=x, y=y)
    records = catalog_ability_records_from_catalog(package.army_catalog)
    indexes = {
        army.player_id: build_player_ability_index(
            records,
            army=army,
            catalog=package.army_catalog,
        )
        for army in armies
    }
    return _RuntimeFixture(
        catalog=catalog,
        armies=armies,
        state=state,
        indexes=indexes,
        eldrad=eldrad,
        dire_avengers=dire_avengers,
        wave_serpent=wave_serpent,
        shining_spears=shining_spears,
        enemy_one=enemy_one,
        enemy_two=enemy_two,
    )


def _state_for_armies(armies: tuple[ArmyDefinition, ...]) -> GameState:
    descriptor = RulesetDescriptor.warhammer_40000_eleventh()
    phases = tuple(descriptor.battle_phase_sequence.phases)
    state = GameState(
        game_id="aeldari-four-datasheets-test",
        ruleset_descriptor_hash=descriptor.descriptor_hash,
        stage=GameLifecycleStage.BATTLE,
        setup_sequence=tuple(descriptor.setup_sequence.steps),
        battle_phase_sequence=phases,
        setup_step_index=None,
        battle_phase_index=phases.index(BattlePhase.MOVEMENT),
        battle_round=1,
        active_player_id="player-a",
        player_ids=("player-a", "player-b"),
        turn_order=("player-a", "player-b"),
        tactical_secondary_draw_count=2,
        mission_setup=_mission_setup(),
    )
    for army in armies:
        state.record_army_definition(army)
    state.battlefield_state = create_deterministic_battlefield_scenario(
        battlefield_id="aeldari-four-datasheets-battlefield",
        armies=armies,
    ).battlefield_state
    return state


def _move_unit_to(
    state: GameState,
    *,
    unit_instance_id: str,
    x: float,
    y: float,
) -> None:
    battlefield = state.battlefield_state
    assert battlefield is not None
    placement = battlefield.unit_placement_by_id(unit_instance_id)
    moved = replace(
        placement,
        model_placements=tuple(
            replace(model, pose=Pose.at(x=x, y=y + (2.5 * index)))
            for index, model in enumerate(placement.model_placements)
        ),
    )
    state.replace_battlefield_state(battlefield.with_unit_placement(moved))


def _weapon_profile(datasheet_id: str, name: str) -> Any:
    return next(
        profile
        for wargear in _package().army_catalog.wargear
        if wargear.wargear_id.startswith(f"{datasheet_id}:")
        for profile in wargear.weapon_profiles
        if profile.name == name
    )


def _lifecycle_for_fixture(fixture: _RuntimeFixture) -> GameLifecycle:
    player_a_request = _muster_request(
        army_id="army-a",
        player_id="player-a",
        selections=(
            _minimum_selection(ELDRAD_ULTHRAN_DATASHEET_ID, selection_id="eldrad"),
            _dire_avenger_selection(selection_id="dire-avengers"),
            _wave_serpent_selection(selection_id="wave-serpent", twin_bright_lance=True),
            _minimum_selection(SHINING_SPEARS_DATASHEET_ID, selection_id="shining-spears"),
        ),
    )
    player_b_request = _muster_request(
        army_id="army-b",
        player_id="player-b",
        selections=(
            _wave_serpent_selection(selection_id="enemy-one"),
            _wave_serpent_selection(selection_id="enemy-two"),
        ),
    )
    config = GameConfig(
        game_id=fixture.state.game_id,
        allow_legacy_non_strict_rosters=True,
        ruleset_descriptor=RulesetDescriptor.warhammer_40000_eleventh(),
        army_catalog=fixture.catalog,
        army_muster_requests=(player_a_request, player_b_request),
        player_ids=("player-a", "player-b"),
        turn_order=("player-a", "player-b"),
        fixed_secondary_mission_ids=("assassination", "bring_it_down"),
        mission_setup=_mission_setup(),
    )
    fixture.state.movement_phase_state = MovementPhaseState(
        battle_round=1,
        active_player_id="player-a",
        reinforcements_completed=True,
        selected_unit_ids=tuple(unit.unit_instance_id for unit in fixture.armies[0].units),
        moved_unit_ids=tuple(unit.unit_instance_id for unit in fixture.armies[0].units),
    )
    return GameLifecycle.from_payload(
        cast(
            Any,
            {
                "config": config.to_payload(),
                "parameterized_movement_proposals": True,
                "state": fixture.state.to_payload(),
                "decisions": DecisionController().to_payload(),
                "reaction_queue": {"frames": []},
            },
        )
    )


def _mission_setup() -> MissionSetup:
    return MissionSetup.from_mission_pack(
        mission_pack=chapter_approved_2026_27_mission_pack(),
        mission_pool_entry_id="mission-take-and-hold-vs-purge-the-foe-layout-3",
        terrain_layout_id="take-and-hold-vs-purge-the-foe-layout-3",
        attacker_player_id="player-a",
        defender_player_id="player-b",
    )
