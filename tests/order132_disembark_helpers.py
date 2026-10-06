"""Recorded Movement choices and circular setup placements for Order132."""

from tests.disembark_eligibility_helpers import PASSENGER_ID, TRANSPORT_ID, disembark_session
from tests.movement_submission_helpers import straight_line_witness_for_state
from tests.order60_emergency_disembark_helpers import emergency_disembark_poses_around
from tests.phase13b_shooting_declaration_helpers import _unit_placement_at
from tests.psychic_modifier_helpers import pending_request
from warhammer40k_core.adapters.local_session import LocalGameSession
from warhammer40k_core.core.ruleset_descriptor import MovementMode
from warhammer40k_core.engine.battlefield_state import BattlefieldPlacementKind, UnitPlacement
from warhammer40k_core.engine.damage_allocation import unit_by_id
from warhammer40k_core.engine.event_log import validate_json_value
from warhammer40k_core.engine.movement_proposals import (
    MovementProposalPayload,
    PlacementProposalPayload,
    ProposalKind,
)
from warhammer40k_core.engine.phase import LifecycleStatusKind
from warhammer40k_core.engine.transports import DisembarkModeKind, TransportMovementStatus
from warhammer40k_core.geometry.pose import Pose


def boundary_session(*, rapid: bool) -> LocalGameSession:
    session = disembark_session(
        unit_poses={"army-alpha:remaining-unit": tuple(Pose.at(30 + i * 1.5, 10) for i in range(5))}
    )
    if rapid:
        move_transport(session)
    return session


def move_transport(session: LocalGameSession) -> None:
    select_options(session, (TRANSPORT_ID, "normal_move"), prefix="order132:transport")
    move_unit(session, unit_id=TRANSPORT_ID, prefix="order132:transport", dy=1)


def move_unit(session: LocalGameSession, *, unit_id: str, prefix: str, dy: float) -> None:
    state = session.lifecycle.state
    assert state is not None
    request = pending_request(session)
    result = session.submit_parameterized_payload(
        request_id=request.request_id,
        result_id=f"{prefix}:moved",
        payload=validate_json_value(
            MovementProposalPayload(
                proposal_request_id=request.request_id,
                proposal_kind=ProposalKind.NORMAL_MOVE,
                unit_instance_id=unit_id,
                movement_phase_action="normal_move",
                movement_mode=MovementMode.NORMAL,
                witness=straight_line_witness_for_state(state, unit_instance_id=unit_id, dy=dy),
            ).to_payload()
        ),
    )
    assert result.status_kind is not LifecycleStatusKind.INVALID, result


def select_options(session: LocalGameSession, options: tuple[str, ...], *, prefix: str) -> None:
    for index, option in enumerate(options):
        request = pending_request(session)
        result = session.submit_option(
            request_id=request.request_id, result_id=f"{prefix}:{index}", option_id=option
        )
        assert result.status_kind is not LifecycleStatusKind.INVALID, result


def boundary_placement(session: LocalGameSession, *, distance: float) -> UnitPlacement:
    state = session.lifecycle.state
    assert state is not None
    assert state.battlefield_state is not None
    passenger = unit_by_id(state=state, unit_instance_id=PASSENGER_ID)
    transport = unit_by_id(state=state, unit_instance_id=TRANSPORT_ID)
    passenger_diameter = passenger.own_models[0].base_size.diameter_mm
    transport_diameter = transport.own_models[0].base_size.diameter_mm
    assert passenger_diameter is not None
    assert transport_diameter is not None
    center = state.battlefield_state.unit_placement_by_id(TRANSPORT_ID).model_placements[0].pose
    return _unit_placement_at(
        passenger,
        army_id="army-alpha",
        player_id="player-a",
        poses=emergency_disembark_poses_around(
            center_x=center.position.x,
            center_y=center.position.y,
            count=len(passenger.own_models),
            radius_inches=transport_diameter / 50.8 + distance - passenger_diameter / 50.8,
            step_degrees=30,
        ),
    )


def boundary_proposal(
    session: LocalGameSession, *, distance: float, rapid: bool
) -> PlacementProposalPayload:
    request = pending_request(session)
    assert request.decision_type == "submit_placement_proposal"
    return PlacementProposalPayload(
        proposal_request_id=request.request_id,
        proposal_kind=ProposalKind.DISEMBARK,
        unit_instance_id=PASSENGER_ID,
        placement_kind=BattlefieldPlacementKind.DISEMBARK,
        attempted_placement=boundary_placement(session, distance=distance),
        transport_unit_instance_id=TRANSPORT_ID,
        disembark_mode=DisembarkModeKind.RAPID_DISEMBARK
        if rapid
        else DisembarkModeKind.TACTICAL_DISEMBARK,
        transport_movement_status=TransportMovementStatus.NORMAL_MOVE
        if rapid
        else TransportMovementStatus.NOT_MOVED,
        restriction_overrides=(),
    )
