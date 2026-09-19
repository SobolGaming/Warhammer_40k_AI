"""Canonical carrier/cargo ingress fixtures for Order 63."""

from dataclasses import replace
from typing import cast

from tests.disembark_eligibility_helpers import PASSENGER_ID, TRANSPORT_ID, disembark_session
from tests.psychic_modifier_helpers import pending_request
from warhammer40k_core.adapters.local_session import LocalGameSession
from warhammer40k_core.engine.battlefield_state import (
    BattlefieldPlacementKind,
    ModelPlacement,
    UnitPlacement,
)
from warhammer40k_core.engine.damage_allocation import unit_by_id
from warhammer40k_core.engine.decision_request import DecisionRequest
from warhammer40k_core.engine.event_log import validate_json_value
from warhammer40k_core.engine.movement_proposals import (
    MovementProposalRequest,
    MovementProposalRequestPayload,
    PlacementProposalPayload,
)
from warhammer40k_core.engine.phase import LifecycleStatus, LifecycleStatusKind
from warhammer40k_core.geometry.pose import Pose


def reserve_transport_session(
    *, loaded: bool = True, deep_strike: bool = False
) -> LocalGameSession:
    unit_poses = None
    if deep_strike:
        unit_poses = {
            "army-alpha:remaining-unit": tuple(Pose.at(30 + i * 1.3, 30) for i in range(5)),
            "army-beta:enemy-unit": tuple(Pose.at(45 + i * 1.3, 30) for i in range(5)),
        }
    return disembark_session(
        reserve_transport=True,
        embarked_passenger=loaded,
        deep_strike_transport=deep_strike,
        unit_poses=unit_poses,
    )


def placement(session: LocalGameSession, unit_id: str, *, x: float, y: float) -> UnitPlacement:
    state = session.lifecycle.state
    assert state is not None
    unit = unit_by_id(state=state, unit_instance_id=unit_id)
    return UnitPlacement(
        army_id="army-alpha",
        player_id="player-a",
        unit_instance_id=unit_id,
        model_placements=tuple(
            ModelPlacement(
                army_id="army-alpha",
                player_id="player-a",
                unit_instance_id=unit_id,
                model_instance_id=m.model_instance_id,
                pose=Pose.at(x + i * 1.5, y),
            )
            for i, m in enumerate(unit.own_models)
            if m.is_alive
        ),
    )


def submit_ingress(session: LocalGameSession, *, deep_strike: bool = False) -> None:
    request = pending_request(session)
    outcome = session.submit_option(
        request_id=request.request_id, result_id="order63:select", option_id=TRANSPORT_ID
    )
    assert outcome.decision_request is not None
    outcome = session.submit_option(
        request_id=outcome.decision_request.request_id,
        result_id="order63:ingress",
        option_id="ingress",
    )
    assert outcome.decision_request is not None
    request = outcome.decision_request
    assert isinstance(request.payload, dict)
    context = MovementProposalRequest.from_payload(
        cast(MovementProposalRequestPayload, request.payload["proposal_request"])
    )
    proposal = PlacementProposalPayload(
        proposal_request_id=context.request_id,
        proposal_kind=context.proposal_kind,
        unit_instance_id=TRANSPORT_ID,
        placement_kind=BattlefieldPlacementKind.DEEP_STRIKE
        if deep_strike
        else BattlefieldPlacementKind.STRATEGIC_RESERVES,
        attempted_placement=placement(session, TRANSPORT_ID, x=12, y=12 if deep_strike else 2),
    )
    outcome = session.submit_parameterized_payload(
        request_id=request.request_id,
        result_id="order63:arrive",
        payload=validate_json_value(proposal.to_payload()),
    )
    assert outcome.status_kind is not LifecycleStatusKind.INVALID, outcome


def rapid_disembark_proposal(
    session: LocalGameSession, *, y: float
) -> tuple[DecisionRequest, PlacementProposalPayload]:
    from warhammer40k_core.engine.movement_proposals import ProposalKind
    from warhammer40k_core.engine.transports import DisembarkModeKind, TransportMovementStatus

    request = pending_request(session)
    outcome = session.submit_option(
        request_id=request.request_id, result_id="order63:cargo", option_id=PASSENGER_ID
    )
    assert outcome.decision_request is not None
    outcome = session.submit_option(
        request_id=outcome.decision_request.request_id,
        result_id="order63:rapid",
        option_id="disembark",
    )
    assert outcome.decision_request is not None
    request = outcome.decision_request
    attempted = placement(session, PASSENGER_ID, x=10.7, y=y)
    attempted = replace(
        attempted,
        model_placements=tuple(
            replace(row, pose=Pose.at(9.4 + i * 1.3, y))
            for i, row in enumerate(attempted.model_placements)
        ),
    )
    proposal = PlacementProposalPayload(
        proposal_request_id=request.request_id,
        proposal_kind=ProposalKind.DISEMBARK,
        unit_instance_id=PASSENGER_ID,
        placement_kind=BattlefieldPlacementKind.DISEMBARK,
        attempted_placement=attempted,
        transport_unit_instance_id=TRANSPORT_ID,
        disembark_mode=DisembarkModeKind.RAPID_DISEMBARK,
        transport_movement_status=TransportMovementStatus.INGRESS_MOVE,
    )
    return request, proposal


def rapid_disembark(session: LocalGameSession, *, y: float) -> LifecycleStatus:
    request, proposal = rapid_disembark_proposal(session, y=y)
    return session.submit_parameterized_payload(
        request_id=request.request_id,
        result_id="order63:disembark",
        payload=validate_json_value(proposal.to_payload()),
    )
