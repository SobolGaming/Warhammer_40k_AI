from __future__ import annotations

import json
import multiprocessing
from math import isclose

import pytest

from tests import phase15a_charge_declaration_helpers as charge_fixtures
from tests.charge_distance_helpers import add_modifier, select_source, select_targets
from warhammer40k_core.adapters.access_control import ViewerContext
from warhammer40k_core.adapters.local_session import LocalGameSession
from warhammer40k_core.ai.ground_charge_candidates import (
    ChargeSearchStop,
    GroundChargeExhaustedError,
    generate_ground_charge_candidates,
)
from warhammer40k_core.ai.ground_charge_policy import prepare_ground_charge_policy
from warhammer40k_core.ai.player_policy import PlayerDecisionContext
from warhammer40k_core.core.ruleset_descriptor import MovementMode
from warhammer40k_core.engine.event_log import validate_json_value
from warhammer40k_core.engine.movement_proposals import ProposalKind
from warhammer40k_core.engine.phase import LifecycleStatusKind
from warhammer40k_core.engine.phases.charge import ChargeMoveProposal
from warhammer40k_core.geometry.pathing import PathWitness
from warhammer40k_core.geometry.pose import Pose

ACTOR = "player-a"
SOURCE = "army-alpha:source"
TARGET = "army-beta:enemy"
SOURCE_Y = (15.0, 16.8, 18.6, 20.4, 22.2)
TARGET_Y = (33.0, 34.8, 36.6, 38.4, 40.2)


@pytest.fixture
def mixed_charge(monkeypatch: pytest.MonkeyPatch) -> LocalGameSession:
    source_column = tuple(Pose.at(1, y, facing_degrees=180) for y in SOURCE_Y)

    def source_poses(*, origin: Pose, model_count: int) -> tuple[Pose, ...]:
        assert origin == source_column[0]
        assert model_count == len(source_column)
        return source_column

    # Only select the input poses during fixture construction. Decisions and
    # geometry validation below run through the unmodified native lifecycle.
    with monkeypatch.context() as fixture:
        fixture.setattr(charge_fixtures, "compact_test_unit_poses", source_poses)
        lifecycle, _ = charge_fixtures.charge_lifecycle(
            game_id="mixed-ground-charge",
            battle_round=2,
            alpha_unit_ids=("source",),
            alpha_origins={"source": source_column[0]},
            enemy_model_poses=tuple(Pose.at(1, y) for y in TARGET_Y),
        )
    assert lifecycle.state is not None
    add_modifier(lifecycle.state, effect_id="fixture", kind="modify_dice_roll", delta=5)
    session = LocalGameSession(lifecycle)
    pending = select_targets(session, select_source(session), (TARGET,))
    assert isinstance(pending.payload, dict)
    proposal = pending.payload["proposal_request"]
    assert isinstance(proposal, dict)
    details = proposal["context"]
    assert isinstance(details, dict)
    assert details["maximum_distance_inches"] == 10
    distances = details["reachable_target_distances_inches"]
    assert isinstance(distances, dict)
    assert set(distances) == {TARGET}
    gap = distances[TARGET]
    assert isinstance(gap, float)
    assert isclose(gap, 9.54015748)
    return session


def _context(session: LocalGameSession) -> PlayerDecisionContext:
    return PlayerDecisionContext.from_view(session.view(viewer_player_id=ACTOR), choice_seed=0)


@pytest.mark.skipif(
    "fork" not in multiprocessing.get_all_start_methods(),
    reason="Native ground charge preparation requires a fork-capable host.",
)
def test_rigid_group_charge_certifies_the_exact_mixed_endpoint_witness(
    mixed_charge: LocalGameSession,
) -> None:
    context = _context(mixed_charge)
    # Even on this unobstructed column, four of five models cannot get within
    # one inch, so the old all-close grid has four necessarily empty banks.
    radius_inches = 16 / 25.4
    distances_for_old_cutoff = [TARGET_Y[0] - y - 2 * radius_inches - 1 for y in SOURCE_Y]
    assert sum(distance > 10 for distance in distances_for_old_cutoff) == 4

    generated = generate_ground_charge_candidates(context, raw_limit=4)
    assert generated.stop is ChargeSearchStop.COMPLETE
    (candidate,) = generated.candidates
    assert candidate.longest_path_inches == 9.5
    assert candidate.waypoint_count == 0
    proposal_json = candidate.action.proposal_json
    assert proposal_json is not None
    proposal = json.loads(proposal_json)
    witness = PathWitness.from_payload(proposal["witness"])
    assert tuple(poses[0].position.y for _, poses in witness.model_paths) == SOURCE_Y[::-1]
    for _, (start, end) in witness.model_paths:
        assert end == Pose.at(1, start.position.y + 9.5, facing_degrees=180)

    limited = generate_ground_charge_candidates(context, raw_limit=1)
    assert limited.candidates == (candidate,)
    assert limited.stop is ChargeSearchStop.RAW_LIMIT
    with pytest.raises(GroundChargeExhaustedError) as caught:
        generate_ground_charge_candidates(
            context, raw_limit=4, geometry_limit=generated.geometry_work - 1
        )
    assert caught.value.reason is ChargeSearchStop.GEOMETRY_LIMIT
    assert caught.value.counts.geometry_work == generated.geometry_work - 1

    prepared = prepare_ground_charge_policy(
        mixed_charge, context, raw_limit=4, validation_limit=1, accepted_limit=1
    )
    assert prepared.counts.raw == prepared.counts.accepted == 1
    assert prepared.counts.rejected == prepared.counts.timed_out == 0
    action = prepared.registration.policy.choose(context)
    assert action == candidate.action
    result = mixed_charge.submit_viewer_parameterized_payload(
        viewer=ViewerContext.for_player(ACTOR),
        request_id=action.request_id,
        result_id="mixed-ground-charge:accepted",
        payload=proposal,
    )
    assert result.status_kind is LifecycleStatusKind.WAITING_FOR_DECISION
    (completed,) = (
        event
        for event in mixed_charge.lifecycle.decision_controller.event_log.records
        if event.event_type == "charge_move_completed"
    )
    assert isinstance(completed.payload, dict)
    endpoints = completed.payload["endpoint_witness"]
    assert isinstance(endpoints, dict)
    rows = endpoints["model_endpoints"]
    assert isinstance(rows, list)
    assert len(rows) == 5
    models = [row for row in rows if isinstance(row, dict)]
    assert len(models) == len(rows)
    assert (
        sum(row["preferred_distance_target_unit_instance_ids"] == [TARGET] for row in models) == 1
    )
    assert sum(row["engaged_target_unit_instance_ids"] == [TARGET] for row in models) == 2


def test_rigid_group_charge_native_rejects_a_column_that_stops_outside_engagement(
    mixed_charge: LocalGameSession,
) -> None:
    context = _context(mixed_charge)
    state = mixed_charge.lifecycle.state
    assert state is not None
    assert state.battlefield_state is not None
    placement = state.battlefield_state.unit_placement_by_id(SOURCE)
    movers = sorted(placement.model_placements, key=lambda model: -model.pose.position.y)
    short_witness = PathWitness.for_paths(
        tuple(
            (
                model.model_instance_id,
                (model.pose, Pose.at(1, model.pose.position.y + 7.5, facing_degrees=180)),
            )
            for model in movers
        )
    )
    proposal = ChargeMoveProposal(
        context.request["request_id"],
        ProposalKind.CHARGE_MOVE,
        SOURCE,
        "charge_move",
        MovementMode.CHARGE,
        (TARGET,),
        short_witness,
    )
    action = context.propose(validate_json_value(proposal.to_payload()))
    assert action.proposal_json is not None
    result = mixed_charge.submit_viewer_parameterized_payload(
        viewer=ViewerContext.for_player(ACTOR),
        request_id=action.request_id,
        result_id="mixed-ground-charge:outside-engagement",
        payload=json.loads(action.proposal_json),
    )
    assert result.status_kind is LifecycleStatusKind.INVALID
    assert isinstance(result.payload, dict)
    assert result.payload["violation_code"] == "charge_target_not_engaged"
    events = mixed_charge.lifecycle.decision_controller.event_log.records
    assert all(event.event_type != "charge_move_completed" for event in events)
    current = mixed_charge.lifecycle.state
    assert current is not None
    assert current.battlefield_state is not None
    assert current.battlefield_state.unit_placement_by_id(SOURCE) == placement
