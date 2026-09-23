from __future__ import annotations

import json
from dataclasses import replace

import pytest
from tests.fire_overwatch_helpers import choose_shooter, pending_overwatch
from tests.order78_helpers import ALTERNATE, SHOOTER, TARGET, candidate_for_scene, scene, shared_los
from tests.phase13b_shooting_declaration_helpers import (
    _decision_request,
    _display_geometry,
    _proposal_from_request,
    _scenario_with_unit_pose,
)
from tests.psychic_modifier_helpers import pending_request
from tests.setup_completion_helpers import record_primary_turn_start_evidence_for_fixture

from warhammer40k_core.adapters.event_stream import EventStreamCursor
from warhammer40k_core.adapters.local_session import LocalGameSession
from warhammer40k_core.core.terrain_areas import TerrainAreaClassification
from warhammer40k_core.core.visibility import VisibilityBlockerKind
from warhammer40k_core.engine.battlefield_presence import battlefield_scenario_for_state
from warhammer40k_core.engine.command_points import CommandPointSourceKind
from warhammer40k_core.engine.event_log import validate_json_value
from warhammer40k_core.engine.game_state import RangedAttackHistoryRecord
from warhammer40k_core.engine.lifecycle import GameLifecycle
from warhammer40k_core.engine.mission_setup import MissionSetup
from warhammer40k_core.engine.phase import BattlePhase, LifecycleStatusKind
from warhammer40k_core.engine.phases.movement import MovementPhaseState
from warhammer40k_core.engine.replay import ReplayArtifact, ReplayRunner, ReplayRunStatus
from warhammer40k_core.engine.rules_units import rules_unit_view_by_id
from warhammer40k_core.engine.shooting_targets import ShootingTargetViolationCode
from warhammer40k_core.engine.terrain_hidden import terrain_hidden_model_ids
from warhammer40k_core.geometry.pose import Pose
from warhammer40k_core.rules.mission_pack_import import (
    warhammer_event_companion_2026_07_mission_pack,
)


@pytest.mark.parametrize("inside", [False, True])
@pytest.mark.parametrize("attached", [False, True])
def test_hidden_target_concealed_by_intervening_dense_feature(inside: bool, attached: bool) -> None:
    lifecycle, units = scene(dense_occupancy=inside, attached_target=attached)
    candidate = candidate_for_scene(lifecycle, units)
    assert candidate.violation_code is ShootingTargetViolationCode.OUTSIDE_DETECTION_RANGE
    assert not shared_los(lifecycle, units)


@pytest.mark.parametrize("hidden", [False, True])
def test_light_feature_does_not_reduce_detection(hidden: bool) -> None:
    lifecycle, units = scene(hidden=hidden, classification=TerrainAreaClassification.LIGHT)
    candidate = candidate_for_scene(lifecycle, units)
    assert candidate.is_legal
    assert candidate.line_of_sight_witness is not None
    assert not candidate.line_of_sight_witness.unit_fully_visible
    assert shared_los(lifecycle, units)


def test_dense_feature_does_not_hide_an_unhidden_target() -> None:
    lifecycle, units = scene(hidden=False)
    assert candidate_for_scene(lifecycle, units).is_legal
    assert shared_los(lifecycle, units)


@pytest.mark.parametrize("turn", ["current", "previous", "old", "first"])
@pytest.mark.parametrize("attached", [False, True])
def test_shooting_history_blocks_gone_to_ground_even_when_hidden_is_retained(
    turn: str, attached: bool
) -> None:
    lifecycle, units = scene(attached_target=attached)
    state = lifecycle.state
    assert state is not None
    target = rules_unit_view_by_id(state=state, unit_instance_id=TARGET)
    if turn != "first":
        state.battle_round = 2
        state.record_ranged_attack_history(
            RangedAttackHistoryRecord(
                player_id="player-b",
                unit_instance_id=target.unit_instance_id,
                battle_round=2 if turn == "current" else 1,
                active_player_id="player-a" if turn in ("current", "old") else "player-b",
                phase=BattlePhase.SHOOTING,
                request_id="order78:history-request",
                result_id="order78:history-result",
            )
        )
    expected = turn in ("current", "previous")
    assert candidate_for_scene(lifecycle, units).is_legal is expected
    assert shared_los(lifecycle, units) is expected


def test_full_visibility_and_cache_reuse_do_not_imply_dense_concealment() -> None:
    protected, protected_units = scene()
    visible, visible_units = scene(wall_y=40.0)
    for _ in range(2):
        assert not candidate_for_scene(protected, protected_units).is_legal
        candidate = candidate_for_scene(visible, visible_units)
        assert candidate.is_legal
        assert candidate.line_of_sight_witness is not None
        assert candidate.line_of_sight_witness.unit_fully_visible
        assert shared_los(visible, visible_units)


@pytest.mark.parametrize(("distance", "legal"), [(11.99, True), (12.01, False), (14.99, False)])
def test_detection_reduction_uses_model_base_distance(distance: float, legal: bool) -> None:
    # The models have 32mm bases; the witness and detection query share geometry.
    lifecycle, units = scene()
    state = lifecycle.state
    assert state is not None
    scenario = _scenario_with_unit_pose(
        scenario=battlefield_scenario_for_state(state=state),
        unit=units["shooter"],
        army_id="army-alpha",
        player_id="player-a",
        poses=(Pose.at(24.3 - 32 / 25.4 - distance, 35.0),),
    )
    state.battlefield_state = scenario.battlefield_state
    assert candidate_for_scene(lifecycle, units).is_legal is legal
    assert shared_los(lifecycle, units) is legal


@pytest.mark.parametrize("host", ["ordinary", "overwatch"])
@pytest.mark.parametrize("attached", [False, True])
def test_facade_rejects_protected_target_then_accepts_retry_with_persistence_and_replay(
    host: str, attached: bool
) -> None:
    lifecycle, _ = scene(attached_target=attached)
    session = LocalGameSession(lifecycle=GameLifecycle.from_payload(lifecycle.to_payload()))
    state = session.lifecycle.state
    assert state is not None
    if host == "overwatch":
        state.battle_phase_index = state.battle_phase_sequence.index(BattlePhase.MOVEMENT)
        state.active_player_id = "player-b"
        state.movement_phase_state = MovementPhaseState(
            battle_round=state.battle_round,
            active_player_id="player-b",
            move_units_completed=True,
        )
        state.gain_command_points(
            player_id="player-a",
            amount=1,
            source_id="order78:cp",
            source_kind=CommandPointSourceKind.OTHER,
            cap_exempt=True,
        )
        record_primary_turn_start_evidence_for_fixture(
            state, decisions=session.lifecycle.decision_controller
        )
        session = LocalGameSession(
            lifecycle=GameLifecycle.from_payload(session.lifecycle.to_payload())
        )
    initial = session.lifecycle.to_payload()
    if host == "ordinary":
        request = pending_request(session)
        status = session.submit_option(
            request_id=request.request_id, option_id=SHOOTER, result_id="order78:select"
        )
        assert status.status_kind is not LifecycleStatusKind.INVALID
        request = pending_request(session)
        status = session.submit_option(
            request_id=request.request_id, option_id="normal", result_id="order78:mode"
        )
        assert status.status_kind is not LifecycleStatusKind.INVALID
        request = pending_request(session)
    else:
        request = _decision_request(choose_shooter(session, pending_overwatch(session)))
    proposal = _proposal_from_request(request=request, target_unit_id=ALTERNATE)
    checkpoint = session.to_persistence_payload()
    restored = LocalGameSession.from_persistence_payload(json.loads(json.dumps(checkpoint)))
    for current in (session, restored):
        for result_id, payload in (
            ("malformed", {"bad": True}),
            ("stale", {**proposal.to_payload(), "proposal_request_id": "old"}),
        ):
            invalid = current.submit_parameterized_payload(
                request_id=request.request_id,
                result_id=f"order78:{result_id}",
                payload=validate_json_value(payload),
            )
            assert invalid.status_kind is LifecycleStatusKind.INVALID
            assert current.to_persistence_payload() == checkpoint
        forbidden = proposal.to_payload()
        forbidden["declarations"][0]["target_unit_instance_id"] = rules_unit_view_by_id(
            state=state, unit_instance_id=TARGET
        ).unit_instance_id
        invalid = current.submit_parameterized_payload(
            request_id=request.request_id,
            result_id="order78:protected",
            payload=validate_json_value(forbidden),
        )
        assert invalid.status_kind is LifecycleStatusKind.INVALID
        assert "outside_detection_range" in json.dumps(invalid.payload)
        assert current.to_persistence_payload() == checkpoint
        accepted = current.submit_parameterized_payload(
            request_id=request.request_id,
            result_id="order78:retry",
            payload=validate_json_value(proposal.to_payload()),
        )
        assert accepted.status_kind is not LifecycleStatusKind.INVALID
    assert session.lifecycle.to_payload() == restored.lifecycle.to_payload()
    for viewer in ("player-a", "player-b"):
        assert session.view(viewer_player_id=viewer) == restored.view(viewer_player_id=viewer)
        assert session.events_since(EventStreamCursor(), viewer_player_id=viewer) == (
            restored.events_since(EventStreamCursor(), viewer_player_id=viewer)
        )
    records = session.lifecycle.to_payload()
    validate_json_value(records)
    assert "object at 0x" not in json.dumps(records)
    result = ReplayRunner.from_payload(
        ReplayArtifact.capture(
            artifact_id="order78:replay",
            initial_lifecycle_payload=initial,
            final_lifecycle=session.lifecycle,
        ).to_payload()
    ).run()
    assert result.status is ReplayRunStatus.REPRODUCED, result


def test_light_area_can_grant_hidden_without_dense_occupancy() -> None:
    lifecycle, units = scene(hidden=False)
    state = lifecycle.state
    assert state is not None
    assert state.mission_setup is not None
    setup = MissionSetup.from_mission_pack(
        mission_pack=warhammer_event_companion_2026_07_mission_pack(),
        mission_pool_entry_id="mission-purge-the-foe-vs-purge-the-foe-layout-1",
        attacker_player_id="player-a",
        attacker_force_disposition_id="purge-the-foe",
        defender_player_id="player-b",
        defender_force_disposition_id="purge-the-foe",
    )
    area = next(
        a for a in setup.terrain_areas if a.classification is TerrainAreaClassification.LIGHT
    )
    # A real typed source area placed at the scene target; this tests the shared
    # query, not mission-layout validation or a faction's Hidden grant.
    area = replace(
        area,
        logical_terrain_area_id=area.terrain_area_id,
        center_x_inches=24.3,
        center_y_inches=35.0,
        footprint_polygon=_display_geometry(
            center_x_inches=24.3, center_y_inches=35.0, width_inches=1.4, depth_inches=1.4
        ).footprint_polygon,
    )
    state.mission_setup = replace(
        setup,
        terrain_features=state.mission_setup.terrain_features,
        terrain_areas=(area,),
        objective_terrain_areas=(),
    )
    assert terrain_hidden_model_ids(
        state=state, ruleset_descriptor=lifecycle.config.ruleset_descriptor, unit_instance_id=TARGET
    ) == (units["enemy"].own_models[0].model_instance_id,)
    assert not candidate_for_scene(lifecycle, units).is_legal
    assert not shared_los(lifecycle, units)
    # Removing the intervening feature restores the base detection range; the
    # target remains Hidden within Light terrain.
    state.mission_setup = replace(state.mission_setup, terrain_features=())
    assert candidate_for_scene(lifecycle, units).is_legal
    assert shared_los(lifecycle, units)


def test_area_only_obstruction_is_not_a_dense_feature() -> None:
    lifecycle, units = scene(dense_occupancy=True)
    state = lifecycle.state
    assert state is not None
    assert state.mission_setup is not None
    setup = MissionSetup.from_mission_pack(
        mission_pack=warhammer_event_companion_2026_07_mission_pack(),
        mission_pool_entry_id="mission-purge-the-foe-vs-purge-the-foe-layout-1",
        attacker_player_id="player-a",
        attacker_force_disposition_id="purge-the-foe",
        defender_player_id="player-b",
        defender_force_disposition_id="purge-the-foe",
    )
    area = next(
        a for a in setup.terrain_areas if a.classification is TerrainAreaClassification.DENSE
    )
    area = replace(
        area,
        logical_terrain_area_id=area.terrain_area_id,
        center_x_inches=23.0,
        center_y_inches=35.0,
        footprint_polygon=_display_geometry(
            center_x_inches=23.0, center_y_inches=35.0, width_inches=0.2, depth_inches=0.6
        ).footprint_polygon,
    )
    state.mission_setup = replace(
        setup, terrain_features=(), terrain_areas=(area,), objective_terrain_areas=()
    )
    candidate = candidate_for_scene(lifecycle, units)
    assert candidate.is_legal
    witness = candidate.line_of_sight_witness
    assert witness is not None
    assert not witness.unit_fully_visible
    assert witness.all_blocker_records()
    assert all(record.terrain_area_id is not None for record in witness.all_blocker_records())
    assert shared_los(lifecycle, units)


def test_non_terrain_model_obstruction_does_not_reduce_detection() -> None:
    lifecycle, units = scene(wall_y=40.0)
    state = lifecycle.state
    assert state is not None
    scenario = _scenario_with_unit_pose(
        scenario=battlefield_scenario_for_state(state=state),
        unit=units["alternate"],
        army_id="army-beta",
        player_id="player-b",
        poses=(Pose.at(23.0, 35.8),),
    )
    state.battlefield_state = scenario.battlefield_state
    candidate = candidate_for_scene(lifecycle, units)
    assert candidate.is_legal
    witness = candidate.line_of_sight_witness
    assert witness is not None
    assert not witness.unit_fully_visible
    assert any(
        record.blocker_kind is VisibilityBlockerKind.MODEL
        for record in witness.all_blocker_records()
    )
    assert shared_los(lifecycle, units)


@pytest.mark.parametrize(
    ("base_range", "distance", "eligible"),
    [(10.0, 8.99, True), (10.0, 9.01, False), (40.0, 29.99, True), (40.0, 30.01, False)],
)
def test_gone_to_ground_composes_with_detection_floor_and_ceiling(
    base_range: float, distance: float, eligible: bool
) -> None:
    from warhammer40k_core.engine.hidden_detection import hidden_detection_eligible_target_model_ids
    from warhammer40k_core.engine.shooting_terrain_visibility import shooting_visibility_cache_key

    lifecycle, units = scene()
    state = lifecycle.state
    assert state is not None
    assert state.mission_setup is not None
    scenario = _scenario_with_unit_pose(
        scenario=battlefield_scenario_for_state(state=state),
        unit=units["shooter"],
        army_id="army-alpha",
        player_id="player-a",
        poses=(Pose.at(24.3 - 32 / 25.4 - distance, 35.0),),
    )
    descriptor = lifecycle.config.ruleset_descriptor
    descriptor = replace(
        descriptor,
        descriptor_hash="",
        terrain_visibility_policy=replace(
            descriptor.terrain_visibility_policy,
            hidden_detection_range_inches=base_range,
        ),
    )
    models = {m.model_id: m for m in scenario.placed_geometry_models()}
    target = units["enemy"].own_models[0].model_instance_id
    result = hidden_detection_eligible_target_model_ids(
        scenario=scenario,
        ruleset_descriptor=descriptor,
        attacker_unit=units["shooter"],
        attacker_models=(models[units["shooter"].own_models[0].model_instance_id],),
        target_rules_unit=rules_unit_view_by_id(state=state, unit_instance_id=TARGET),
        target_models=(models[target],),
        visibility_cache_key=shooting_visibility_cache_key(
            scenario=scenario, terrain_features=state.mission_setup.terrain_features
        ),
        terrain_features=state.mission_setup.terrain_features,
        terrain_areas=(),
        hidden_target_model_ids=(target,),
        target_unit_ids_with_recent_ranged_attacks=(),
        target_detection_range_bonus_inches=0,
    )
    assert result == ((target,) if eligible else ())


def test_attached_unit_only_qualifying_model_gains_reduction() -> None:
    lifecycle, units = scene(attached_target=True)
    state = lifecycle.state
    assert state is not None
    # The bodyguard is protected; the leader is visible beside it and within 15.
    scenario = _scenario_with_unit_pose(
        scenario=battlefield_scenario_for_state(state=state),
        unit=units["leader"],
        army_id="army-beta",
        player_id="player-b",
        poses=(Pose.at(24.3, 36.6),),
    )
    state.battlefield_state = scenario.battlefield_state
    candidate = candidate_for_scene(lifecycle, units)
    assert candidate.is_legal
    assert candidate.target_visible_model_ids == (units["leader"].own_models[0].model_instance_id,)
    assert shared_los(lifecycle, units)


def test_gone_to_ground_source_is_loaded_with_registered_provenance() -> None:
    from warhammer40k_core.rules.source_packages.artifact_loader import package_artifact_bytes
    from warhammer40k_core.rules.source_packages.warhammer_40000_11th import (
        core_gone_to_ground_2026_09 as source,
    )

    package = source.source_package()
    assert package.source_catalog.documents
    (rule,) = source.source_rules()
    assert rule.section_id == "13.11.01"
    assert rule.load_support_status == "loaded"
    assert rule.semantic_execution_status == "executable_engine_runtime"
    assert (
        rule.transcription_sha256
        == "97063c88c0146126f288170f1cd6fc4f6ecc291c8f4b33bb6075f209716a2c8c"
    )
    raw = package_artifact_bytes(source.__name__, "artifacts/package.json")
    assert source.validate_source_artifact_bytes(raw).rules == (rule,)
    with pytest.raises(source.GoneToGroundSourceError, match="reviewed pin"):
        source.validate_source_artifact_bytes(raw + b" ")


def test_dense_concealment_cached_and_uncached_witnesses_agree() -> None:
    from warhammer40k_core.core.visibility import TerrainVisibilityContext
    from warhammer40k_core.engine.shooting_terrain_visibility import (
        blocker_record_is_dense_feature,
        shooting_visibility_cache_key,
    )

    lifecycle, units = scene()
    state = lifecycle.state
    assert state is not None
    assert state.mission_setup is not None
    scenario = battlefield_scenario_for_state(state=state)
    models = {m.model_id: m for m in scenario.placed_geometry_models()}
    target = models[units["enemy"].own_models[0].model_instance_id]
    context = TerrainVisibilityContext.from_ruleset_descriptor(
        ruleset_descriptor=lifecycle.config.ruleset_descriptor,
        los_cache_key=shooting_visibility_cache_key(
            scenario=scenario,
            terrain_features=state.mission_setup.terrain_features,
        ),
        observer_model=models[units["shooter"].own_models[0].model_instance_id],
        target_models=(target,),
        target_model_keywords=((target.model_id, units["enemy"].own_models[0].keywords),),
        observer_keywords=units["shooter"].own_models[0].keywords,
        terrain_features=state.mission_setup.terrain_features,
    )
    witness = context.resolve_line_of_sight_uncached()
    assert witness == context.resolve_line_of_sight()
    sources = tuple(
        record
        for record in witness.all_blocker_records()
        if record.blocks_full_visibility
        and blocker_record_is_dense_feature(
            ruleset_descriptor=lifecycle.config.ruleset_descriptor,
            record=record,
            terrain_features=state.mission_setup.terrain_features,
        )
    )
    assert sources
    assert context.not_fully_visible_because_of(
        witness, target_model_id=target.model_id, sources=sources
    )


@pytest.mark.parametrize(("bonus", "legal"), [(0, False), (3, True), (6, True)])
def test_detection_bonus_composes_with_gone_to_ground(bonus: int, legal: bool) -> None:
    lifecycle, units = scene()
    assert candidate_for_scene(lifecycle, units, detection_bonus=bonus).is_legal is legal
