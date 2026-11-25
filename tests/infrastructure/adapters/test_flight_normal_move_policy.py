"""Fixed destinations and full flight/ground paths through the ordinary viewer route."""

from __future__ import annotations

import json
from collections.abc import Callable
from dataclasses import replace
from math import hypot
from typing import cast

import pytest

from tests.phase15c_fight_order_helpers import fight_config, unit_placement_at
from tests.setup_completion_helpers import (
    record_current_battlefield_placements_for_fixture,
    record_primary_turn_start_evidence_for_fixture,
)
from warhammer40k_core.adapters.access_control import ViewerContext
from warhammer40k_core.adapters.local_session import LocalGameSession
from warhammer40k_core.ai.flight_normal_move_policy import (
    FlightNormalMoveGap,
    FlightNormalMoveGapReason,
    PreparedFlightNormalMove,
    prepare_flight_normal_move,
)
from warhammer40k_core.ai.player_policy import PlayerDecisionContext, PolicyRouter, payload_digest
from warhammer40k_core.ai.runner import (
    BoundedPolicyRunner,
    PolicyCheckpointGap,
    RunLimits,
    RunnerError,
)
from warhammer40k_core.core.ruleset_descriptor import (
    MovementMode,
    RulesetDescriptor,
    TerrainFeatureKind,
)
from warhammer40k_core.core.terrain_display import TerrainDisplayGeometry
from warhammer40k_core.engine.army_mustering import muster_army
from warhammer40k_core.engine.decision_controller import DecisionController
from warhammer40k_core.engine.event_log import validate_json_value
from warhammer40k_core.engine.game_state import (
    GameState,
    SecondaryMissionChoice,
    SecondaryMissionMode,
)
from warhammer40k_core.engine.lifecycle import GameLifecycle
from warhammer40k_core.engine.movement_proposals import (
    MovementProposalPayload,
    MovementProposalRequest,
)
from warhammer40k_core.engine.phase import (
    BattlePhase,
    GameLifecycleStage,
    LifecycleStatus,
    LifecycleStatusKind,
)
from warhammer40k_core.engine.placement import create_deterministic_battlefield_scenario
from warhammer40k_core.engine.replay import ReplayRunner
from warhammer40k_core.geometry.pathing import PathWitness
from warhammer40k_core.geometry.pose import Pose
from warhammer40k_core.geometry.terrain import TerrainFeatureDefinition, TerrainFloorDefinition
from warhammer40k_core.geometry.terrain_classification import TerrainAreaClassification
from warhammer40k_core.rules.source_packages.warhammer_40000_11th import (
    chaos_daemons_cavalcade_2026_11,
)

ACTOR = "player-a"
VIEWER = ViewerContext.for_player(ACTOR)
BLOODTHIRSTER = "000002582"
START = Pose.at(10, 20)
GROUND = MovementMode.NORMAL
FLIGHT = MovementMode.FLY_TAKE_TO_SKIES


def _terrain(roof: bool) -> tuple[TerrainFeatureDefinition, ...]:
    if not roof:
        return ()
    display = TerrainDisplayGeometry.axis_aligned_rectangle(
        center_x_inches=20,
        center_y_inches=20,
        width_inches=8,
        depth_inches=20,
        display_template_id=None,
    )
    return (
        TerrainFeatureDefinition(
            "stage3-flight:sealed-roof",
            TerrainFeatureKind.SEALED_BUILDINGS,
            20,
            20,
            8,
            20,
            display.footprint_polygon,
            display,
            floors=(TerrainFloorDefinition("roof", 20, 20, 12, 8, 20, 0.125),),
            classification=TerrainAreaClassification.DENSE,
        ),
    )


def _prefix(*, roof: bool, private_seed: int = 3) -> tuple[LocalGameSession, str, str]:
    package = chaos_daemons_cavalcade_2026_11.catalog_package()
    game_id = f"stage3-flight-{roof}"
    config = fight_config(
        game_id=game_id,
        alpha_unit_ids=("mover", "spare"),
        enemy_unit_ids=("observer",),
        datasheet_id=BLOODTHIRSTER,
        model_profile_id=f"{BLOODTHIRSTER}:bloodthirster",
        model_count=1,
        alpha_faction_id="chaos-daemons",
        enemy_faction_id="chaos-daemons",
        alpha_detachment_ids=("cavalcade-of-chaos", "shadow-legion"),
        enemy_detachment_ids=("cavalcade-of-chaos", "shadow-legion"),
        catalog=package.army_catalog,
    )
    assert config.mission_setup is not None
    terrain = _terrain(roof)
    mission = replace(config.mission_setup, terrain_features=terrain)
    config = replace(
        config,
        private_rng_seed=f"{private_seed:064x}",
        mission_setup=mission,
        model_geometries=package.model_geometries,
        ruleset_descriptor=RulesetDescriptor.warhammer_40000_eleventh_chapter_approved_2026_27(
            descriptor_version="stage3-flight-fixture",
        ),
    )
    armies = tuple(
        muster_army(
            catalog=config.army_catalog, request=muster, model_geometries=config.model_geometries
        )
        for muster in config.army_muster_requests
    )
    battlefield = create_deterministic_battlefield_scenario(
        battlefield_id=f"{game_id}-board",
        armies=armies,
        battlefield_width_inches=mission.battlefield_width_inches,
        battlefield_depth_inches=mission.battlefield_depth_inches,
    ).battlefield_state
    battlefield = replace(battlefield, terrain_features=terrain)
    state = GameState.from_config(config)
    for army, poses in zip(armies, ((START, Pose.at(10, 35)), (Pose.at(45, 30),)), strict=True):
        state.record_army_definition(army)
        for unit, pose in zip(army.units, poses, strict=True):
            battlefield = battlefield.with_unit_placement(
                unit_placement_at(
                    unit, army_id=army.army_id, player_id=army.player_id, poses=(pose,)
                )
            )
    state.record_battlefield_state(battlefield)
    state.stage = GameLifecycleStage.BATTLE
    state.setup_step_index = None
    state.battle_phase_index = state.battle_phase_sequence.index(BattlePhase.MOVEMENT)
    state.battle_round = 1
    state.active_player_id = ACTOR
    for player in state.player_ids:
        state.record_secondary_mission_choice(
            SecondaryMissionChoice(
                player, SecondaryMissionMode.FIXED, ("assassination", "bring-it-down")
            )
        )
    decisions = DecisionController()
    record_current_battlefield_placements_for_fixture(state, decisions=decisions)
    record_primary_turn_start_evidence_for_fixture(state, decisions=decisions)
    lifecycle = GameLifecycle.from_payload(
        {
            "config": config.to_payload(),
            "parameterized_movement_proposals": True,
            "state": state.to_payload(),
            "decisions": decisions.to_payload(),
            "reaction_queue": {"frames": []},
        }
    )
    session = LocalGameSession(lifecycle)
    session.advance_until_decision_or_terminal()
    mover = armies[0].units[0]
    request = _context(session).request
    assert request["decision_type"] == "select_movement_unit"
    session.submit_viewer_option(
        viewer=VIEWER,
        request_id=request["request_id"],
        result_id="stage3-flight-select",
        option_id=mover.unit_instance_id,
    )
    return session, mover.unit_instance_id, mover.own_model_ids()[0]


def _context(session: LocalGameSession) -> PlayerDecisionContext:
    return PlayerDecisionContext.from_view(session.view(viewer_player_id=ACTOR), choice_seed=0)


def _submit_path(
    session: LocalGameSession,
    *,
    unit_id: str,
    mode: MovementMode,
    path: PathWitness,
) -> LifecycleStatus:
    request = _context(session).request
    proposal = MovementProposalRequest.from_decision_request_payload(request["payload"])
    assert proposal.context is not None
    assert proposal.context["movement_mode"] == mode
    assert proposal.context["selected_movement_action_grant_hook_ids"] == []
    assert proposal.movement_phase_action == "normal_move"
    payload = MovementProposalPayload(
        request["request_id"],
        proposal.proposal_kind,
        unit_id,
        "normal_move",
        path,
        movement_mode=mode.value,
    )
    return session.submit_viewer_parameterized_payload(
        viewer=VIEWER,
        request_id=request["request_id"],
        result_id="stage3-flight-path",
        payload=validate_json_value(payload.to_payload()),
    )


def _move(
    session: LocalGameSession,
    context: PlayerDecisionContext,
    *,
    unit_id: str,
    mode: MovementMode,
    path: PathWitness,
) -> tuple[LocalGameSession, LifecycleStatus]:
    fork = session.fork()
    assert _context(fork) == context
    request = context.request
    options = [
        option["option_id"]
        for option in request["options"]
        if isinstance(option["payload"], dict)
        and option["payload"].get("movement_phase_action") == "normal_move"
        and option["payload"].get("movement_mode") == mode
    ]
    (option_id,) = options
    fork.submit_viewer_option(
        viewer=VIEWER,
        request_id=request["request_id"],
        result_id="stage3-flight-mode",
        option_id=option_id,
    )
    return fork, _submit_path(fork, unit_id=unit_id, mode=mode, path=path)


def _completed(
    session: LocalGameSession,
    *,
    mode: MovementMode,
    witness: PathWitness,
    distance: float,
) -> float:
    (event,) = [
        event
        for event in session.lifecycle.decision_controller.event_log.records
        if event.event_type == "movement_activation_completed"
    ]
    payload = event.payload
    assert isinstance(payload, dict)
    assert payload["movement_mode"] == mode
    assert payload["witness"] == witness.to_payload()
    movements = payload["model_movements"]
    assert isinstance(movements, list)
    (movement,) = movements
    assert isinstance(movement, dict)
    assert movement["movement_distance_modifier_inches"] == (0 if mode is GROUND else -2)
    distance_witness = movement["movement_distance_witness"]
    assert isinstance(distance_witness, dict)
    budget = distance_witness["budget"]
    assert isinstance(budget, dict)
    assert budget["total_distance_inches"] == distance
    limit = budget["max_distance_inches"]
    assert isinstance(limit, float)
    return limit


def _reproduces(session: LocalGameSession) -> None:
    artifact = session.replay_artifact(artifact_id="stage3-flight-native")
    replay = ReplayRunner.from_payload(artifact).run()
    assert replay.reproduced_exactly, replay.to_payload()


@pytest.mark.parametrize("roof", [False, True], ids=["open", "roof"])
def test_fixed_destination_flight_policy_and_native_comparison(roof: bool) -> None:
    session, unit_id, model_id = _prefix(roof=roof)
    context = _context(session)
    original = session.to_persistence_payload()
    original_hash = payload_digest(original)
    destination = Pose.at(20, 20, 12 if roof else 0)
    ground = PathWitness.for_paths(((model_id, (START, destination)),))
    flight = PathWitness.for_paths(
        ((model_id, (START, Pose.at(10, 20, 12), destination) if roof else (START, destination)),)
    )

    ground_arm, ground_status = _move(session, context, unit_id=unit_id, mode=GROUND, path=ground)
    flight_arm, flight_status = _move(session, context, unit_id=unit_id, mode=FLIGHT, path=flight)
    assert flight_status.status_kind is LifecycleStatusKind.WAITING_FOR_DECISION
    flight_budget = _completed(flight_arm, mode=FLIGHT, witness=flight, distance=10)
    if roof:
        assert ground_status.status_kind is LifecycleStatusKind.INVALID
        assert isinstance(ground_status.payload, dict)
        assert ground_status.payload["violation_code"] == "movement_distance_exceeded"
        assert hypot(10, 12) > 12.001
    else:
        assert ground_status.status_kind is LifecycleStatusKind.WAITING_FOR_DECISION
        assert _completed(ground_arm, mode=GROUND, witness=ground, distance=10) == 12
    assert flight_budget == 10

    # On the roof, a real rejected path is supplied as the ground candidate.
    # Only a native receipt can determine whether it qualifies as an accepted route.
    prepared = prepare_flight_normal_move(
        session, context, destination=destination, ground_path=ground, flight_path=flight
    )
    choice, entry = prepared.choice, prepared.registration
    assert (choice.mode, choice.witness) == ((FLIGHT, flight) if roof else (GROUND, ground))
    config = json.loads(entry.configuration_json)
    assert config["ground_budget_inches"] == 12
    assert config["flight_budget_inches"] == flight_budget == 10
    assert entry.required_checkpoint_hash == original_hash
    assert session.to_persistence_payload() == original
    assert original_hash not in entry.configuration_json
    qualification_prefix = session.fork() if roof else session
    limits = RunLimits(policy_seed=0, max_decisions=1, max_seconds=90)
    runner = BoundedPolicyRunner(session=session, router=PolicyRouter((entry,)), limits=limits)
    with pytest.raises(RunnerError) as stop:
        runner.run()
    assert stop.value.report.failure_reason == "decision_limit"
    (attempt,) = stop.value.report.decisions
    assert attempt.submission_outcome == "accepted"
    assert attempt.observation_hash == context.observation_hash
    status = _submit_path(session, unit_id=unit_id, mode=choice.mode, path=choice.witness)
    assert status.status_kind is LifecycleStatusKind.WAITING_FOR_DECISION
    _completed(session, mode=choice.mode, witness=choice.witness, distance=10)
    for endpoint in (ground_arm, flight_arm, session):
        _reproduces(endpoint)

    if roof:
        with pytest.raises(FlightNormalMoveGap) as gap:
            prepare_flight_normal_move(
                ground_arm, context, destination=destination, ground_path=ground, flight_path=flight
            )
        assert gap.value.reason is FlightNormalMoveGapReason.OBSERVATION

        # A supplied scalar must never substitute for the native 10-inch penalty-adjusted budget.
        unsupported_arguments = cast(
            Callable[..., PreparedFlightNormalMove], prepare_flight_normal_move
        )
        with pytest.raises(TypeError, match="flight_budget_inches"):
            unsupported_arguments(
                qualification_prefix,
                context,
                destination=destination,
                ground_path=ground,
                flight_path=flight,
                flight_budget_inches=1,
            )
        with pytest.raises(FlightNormalMoveGap) as gap:
            prepare_flight_normal_move(
                qualification_prefix,
                context,
                destination=destination,
                ground_path=ground,
                flight_path=None,
            )
        assert gap.value.reason is FlightNormalMoveGapReason.FLIGHT_UNWITNESSED

        # A rejected detour cannot supply the qualified direct 3D ground receipt.
        detour = PathWitness.for_paths(((model_id, (START, Pose.at(14, 35), destination)),))
        with pytest.raises(FlightNormalMoveGap) as gap:
            prepare_flight_normal_move(
                qualification_prefix,
                context,
                destination=destination,
                ground_path=detour,
                flight_path=flight,
            )
        assert gap.value.reason is FlightNormalMoveGapReason.GROUND_UNRESOLVED
    else:
        private_fork, _, _ = _prefix(roof=False, private_seed=4)
        assert _context(private_fork) == context
        private_checkpoint_hash = payload_digest(private_fork.to_persistence_payload())
        assert private_checkpoint_hash != original_hash
        with pytest.raises(FlightNormalMoveGap) as rebind:
            replace(entry, required_checkpoint_hash=private_checkpoint_hash)
        assert rebind.value.reason is FlightNormalMoveGapReason.CHECKPOINT

        with pytest.raises(RunnerError) as stale:
            BoundedPolicyRunner(
                session=private_fork, router=PolicyRouter((entry,)), limits=limits
            ).run()
        assert isinstance(stale.value.__cause__, PolicyCheckpointGap)
        (blocked,) = stale.value.report.decisions
        assert blocked.submission_outcome == "not_submitted"
        assert blocked.choice_seconds == 0
