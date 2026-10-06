"""Public facade accepts real source-directed objective movement and retries legal failures."""

from __future__ import annotations

import json
import math

import pytest
from tests.order129_helpers import assert_flight_checkpoint
from tests.order131_helpers import MOVER, objective_session, request_objective_move
from tests.psychic_modifier_helpers import pending_request

from warhammer40k_core.adapters.local_session import LocalGameSession
from warhammer40k_core.engine.battlefield_state import (
    BattlefieldScenario,
    geometry_model_for_placement,
)
from warhammer40k_core.engine.event_log import validate_json_value
from warhammer40k_core.engine.movement_proposals import (
    MovementProposalPayload,
    MovementProposalRequest,
)
from warhammer40k_core.engine.phase import LifecycleStatus, LifecycleStatusKind
from warhammer40k_core.engine.replay import ReplayRunner, ReplayRunStatus
from warhammer40k_core.geometry.pathing import PathWitness
from warhammer40k_core.geometry.pose import Pose


def _submit(
    session: LocalGameSession,
    distance: float,
    *,
    radial: bool,
    result_id: str,
    packed_wall: bool = False,
) -> LifecycleStatus:
    request = pending_request(session)
    context = MovementProposalRequest.from_decision_request_payload(request.payload)
    state = session.lifecycle.state
    assert state is not None
    assert state.battlefield_state is not None
    placement = state.battlefield_state.unit_placement_by_id(MOVER)
    paths: list[tuple[str, tuple[Pose, ...]]] = []
    for index, row in enumerate(placement.model_placements):
        x, y = row.pose.position.x, row.pose.position.y
        dx, dy = 1.0, 0.0
        if radial:
            length = math.hypot(80 - x, 23 - y)
            dx, dy = (80 - x) / length, (23 - y) / length
        end = Pose.at(x + dx * distance, y + dy * distance)
        middle = Pose.at((x + end.position.x) / 2, (y + end.position.y) / 2)
        if packed_wall:
            scenario = BattlefieldScenario(
                armies=tuple(state.army_definitions), battlefield_state=state.battlefield_state
            )
            radius = geometry_model_for_placement(
                model=scenario.model_instance_for_placement(row), placement=row
            ).base.max_radius()
            end = Pose.at(14.5 - radius - 1e-9, 23 + (index - 2) * (2 * radius + 1e-9))
            middle = Pose.at(end.position.x, end.position.y + 2 * radius)
        paths.append(
            (
                row.model_instance_id,
                (
                    row.pose,
                    middle,
                    end,
                ),
            )
        )
    return session.submit_parameterized_payload(
        request_id=request.request_id,
        result_id=result_id,
        payload=validate_json_value(
            MovementProposalPayload(
                proposal_request_id=request.request_id,
                proposal_kind=context.proposal_kind,
                unit_instance_id=MOVER,
                movement_phase_action="surge_move",
                witness=PathWitness.for_paths(tuple(paths)),
            ).to_payload()
        ),
    )


@pytest.mark.parametrize("control", ["reachable", "unreachable", "already-in-range", "wall"])
def test_source_consumer_facade_retry_persistence_fork_views_events_replay(control: str) -> None:
    radial = control == "unreachable"
    session = objective_session(
        objective_x={"reachable": 17, "unreachable": 80, "already-in-range": 13, "wall": 30}[
            control
        ],
        objective_y=23,
        wall=control == "wall",
    )
    assert_flight_checkpoint(session)
    request_objective_move(session)
    state = session.lifecycle.state
    assert state is not None
    assert state.command_point_total("player-b") == 0
    assert len(state.stratagem_use_records) == 1
    assert_flight_checkpoint(session)
    request = pending_request(session)
    choice = next(option for option in request.options if "objective:" in option.option_id)
    session.submit_option(
        request_id=request.request_id, option_id=choice.option_id, result_id="objective-choice"
    )
    assert_flight_checkpoint(session)
    state = session.lifecycle.state
    assert state is not None
    assert state.battlefield_state is not None
    before = state.battlefield_state.to_payload()
    invalid = _submit(
        session,
        -5 if control == "already-in-range" else 5 if radial else 1,
        radial=radial,
        result_id="insufficient",
    )
    assert invalid.status_kind is LifecycleStatusKind.INVALID, invalid
    assert isinstance(invalid.payload, dict)
    assert invalid.payload["violation_code"] == (
        "objective_approach_closest_endpoint_not_reached"
        if control in {"unreachable", "wall"}
        else "objective_approach_range_not_reached"
    ), invalid
    assert state.battlefield_state.to_payload() == before
    if control == "wall":
        inside_wall = _submit(session, 5, radial=False, result_id="inside-wall")
        assert inside_wall.status_kind is LifecycleStatusKind.INVALID, inside_wall
        assert isinstance(inside_wall.payload, dict)
        terrain_results = inside_wall.payload["terrain_path_legality_results"]
        assert isinstance(terrain_results, list)
        assert any(isinstance(row, dict) and row["is_valid"] is False for row in terrain_results)
        assert state.battlefield_state.to_payload() == before
    assert_flight_checkpoint(session)
    checkpoint = json.loads(json.dumps(session.to_persistence_payload()))
    continuations = (session, session.fork(), LocalGameSession.from_persistence_payload(checkpoint))
    for resumed in continuations:
        accepted = _submit(
            resumed,
            1 if control == "already-in-range" else 6 if radial else 5,
            radial=radial,
            result_id="legal-approach",
            packed_wall=control == "wall",
        )
        assert accepted.status_kind is not LifecycleStatusKind.INVALID, accepted
        assert_flight_checkpoint(resumed)
        replay = ReplayRunner.from_payload(
            resumed.replay_artifact(artifact_id="order131-approach")
        ).run()
        assert replay.status is ReplayRunStatus.REPRODUCED, replay
    assert continuations[0].to_persistence_payload() == continuations[1].to_persistence_payload()
    assert continuations[0].to_persistence_payload() == continuations[2].to_persistence_payload()
