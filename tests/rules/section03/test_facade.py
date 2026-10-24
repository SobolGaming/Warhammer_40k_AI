"""Small movement facade integration: no setup phases or game startup."""

from dataclasses import replace

import pytest

from tests.support.section02_fixtures import CHAOS_SPAWN, Section02Definitions
from tests.support.section03_fixtures import grid, native_state, paths, placement
from tests.support.section03_session import movement_session
from warhammer40k_core.engine.event_log import validate_json_value
from warhammer40k_core.engine.mission_setup import MissionSetup
from warhammer40k_core.engine.movement_proposals import (
    MovementProposalPayload,
    MovementProposalRequest,
)
from warhammer40k_core.engine.phase import LifecycleStatusKind
from warhammer40k_core.engine.phases.movement_handler import MovementPhaseHandler
from warhammer40k_core.geometry.pose import Pose


@pytest.mark.parametrize("action", ["normal_move", "fall_back"])
def test_native_facade_rejects_swap_then_applies_legal_witness(
    section03_definitions: Section02Definitions, section03_setup_mission: MissionSetup, action: str
) -> None:
    unit = section03_definitions.unit(CHAOS_SPAWN)
    starts = (Pose.at(10, 10), Pose.at(12.5, 10))
    enemy = section03_definitions.unit(CHAOS_SPAWN, identity="enemy", army_id="enemy")
    state = native_state(
        section03_definitions,
        unit,
        starts,
        enemy=enemy,
        enemy_poses=(Pose.at(10, 13.8), Pose.at(12.5, 13.8)) if action == "fall_back" else None,
    )
    state.mission_setup = section03_setup_mission
    # A second eligible native unit keeps the facade at this movement boundary.
    spare = section03_definitions.unit(CHAOS_SPAWN, identity="spare")
    owner = next(a for a in state.army_definitions if a.player_id == "owner")
    state.army_definitions = [
        replace(a, units=(*a.units, spare)) if a == owner else a for a in state.army_definitions
    ]
    assert state.battlefield_state is not None
    state.replace_battlefield_state(
        replace(
            state.battlefield_state,
            placed_armies=tuple(
                replace(
                    a, unit_placements=(*a.unit_placements, placement(spare, grid(spare, 10, 25)))
                )
                if a.player_id == "owner"
                else a
                for a in state.battlefield_state.placed_armies
            ),
        )
    )
    handler = MovementPhaseHandler(
        ruleset_descriptor=state.runtime_ruleset_descriptor(),
        army_catalog=section03_definitions.package.army_catalog,
    )
    session = movement_session(section03_definitions, state)
    lifecycle = session.lifecycle
    status = handler.begin_phase(state=state, decisions=lifecycle.decision_controller)
    request = status.decision_request
    assert request is not None
    status = session.submit_option(
        request_id=request.request_id, option_id=unit.unit_instance_id, result_id="select"
    )
    request = status.decision_request
    assert request is not None
    option = next(
        o
        for o in request.options
        if isinstance(o.payload, dict)
        and o.payload.get("movement_phase_action") == action
        and o.payload.get("fall_back_mode", "ordered_retreat") == "ordered_retreat"
    )
    assert isinstance(option.payload, dict)
    movement_mode = option.payload["movement_mode"]
    assert isinstance(movement_mode, str)
    status = session.submit_option(
        request_id=request.request_id, option_id=option.option_id, result_id="action"
    )
    request = status.decision_request
    assert request is not None
    before = state.battlefield_state
    legal = (
        (Pose.at(10, 6), Pose.at(12.5, 6))
        if action == "fall_back"
        else (Pose.at(10, 11), Pose.at(12.5, 11))
    )
    for index, ends in enumerate((tuple(reversed(starts)), legal)):
        proposal = MovementProposalRequest.from_decision_request_payload(request.payload)
        status = session.submit_parameterized_payload(
            request_id=request.request_id,
            result_id=f"path-{index}",
            payload=validate_json_value(
                MovementProposalPayload(
                    proposal_request_id=request.request_id,
                    proposal_kind=proposal.proposal_kind,
                    unit_instance_id=unit.unit_instance_id,
                    movement_phase_action=action,
                    movement_mode=movement_mode,
                    fall_back_mode="ordered_retreat" if action == "fall_back" else None,
                    witness=paths(unit, starts, ends),
                ).to_payload()
            ),
        )
        if index == 0:
            assert status.status_kind is LifecycleStatusKind.INVALID
            assert state.battlefield_state == before
            request = lifecycle.decision_controller.queue.pending_requests[0]
        else:
            assert status.status_kind is not LifecycleStatusKind.INVALID
            assert state.battlefield_state is not None
            assert (
                tuple(
                    p.pose
                    for p in state.battlefield_state.unit_placement_by_id(
                        unit.unit_instance_id
                    ).model_placements
                )
                == ends
            )
    assert len(lifecycle.decision_controller.records) == 4
    assert state.movement_phase_state is not None
    assert unit.unit_instance_id in state.movement_phase_state.moved_unit_ids
    if action == "fall_back":
        # The selected move's After Moving restrictions exist when activation ends.
        restriction = next(
            r for r in state.fell_back_unit_states if r.unit_instance_id == unit.unit_instance_id
        )
        assert not restriction.can_shoot
        assert not restriction.can_declare_charge
        assert restriction.cleanup_point == "end_of_turn"
