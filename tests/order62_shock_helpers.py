"""Canonical facade fixture for post-placement Shock Disembark engagements."""

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
from warhammer40k_core.engine.movement_proposals import (
    MovementProposalRequest,
    PlacementProposalPayload,
    ProposalKind,
)
from warhammer40k_core.engine.shock_disembark import shock_disembark_restriction_overrides
from warhammer40k_core.engine.transports import DisembarkModeKind, TransportMovementStatus
from warhammer40k_core.geometry.pose import Pose

ENEMY_ID = "army-beta:enemy-unit"


def shock_session(*, enemy_x: float = 13, other_engagement: bool = False) -> LocalGameSession:
    poses = {ENEMY_ID: tuple(Pose.at(enemy_x, 7.2 + 1.4 * i) for i in range(5))}
    if other_engagement:
        poses["army-alpha:remaining-unit"] = tuple(
            Pose.at(enemy_x + 1.5, 7.2 + 1.4 * i) for i in range(5)
        )
    return disembark_session((DisembarkModeKind.SHOCK_DISEMBARK,), unit_poses=poses)


def shock_proposal(session: LocalGameSession) -> tuple[DecisionRequest, PlacementProposalPayload]:
    request = pending_request(session)
    action = session.submit_option(
        request_id=request.request_id, result_id="order62:unit", option_id=PASSENGER_ID
    )
    assert action.decision_request is not None
    placement = session.submit_option(
        request_id=action.decision_request.request_id,
        result_id="order62:mode",
        option_id="disembark:shock_disembark",
    )
    assert placement.decision_request is not None
    request = placement.decision_request
    state = session.lifecycle.state
    assert state is not None
    passenger = unit_by_id(state=state, unit_instance_id=PASSENGER_ID)
    poses = (
        Pose.at(14.26, 9.2),
        Pose.at(14.26, 10.8),
        Pose.at(12.8, 7.2),
        Pose.at(12.8, 12.8),
        Pose.at(10, 6.8),
    )
    context = MovementProposalRequest.from_decision_request_payload(request.payload).context
    assert context is not None
    start_ids = context["start_engaged_enemy_unit_instance_ids"]
    assert isinstance(start_ids, list)
    assert all(isinstance(value, str) for value in start_ids)
    proposal = PlacementProposalPayload(
        proposal_request_id=request.request_id,
        proposal_kind=ProposalKind.DISEMBARK,
        unit_instance_id=PASSENGER_ID,
        placement_kind=BattlefieldPlacementKind.DISEMBARK,
        attempted_placement=UnitPlacement(
            army_id="army-alpha",
            player_id="player-a",
            unit_instance_id=PASSENGER_ID,
            model_placements=tuple(
                ModelPlacement(
                    army_id="army-alpha",
                    player_id="player-a",
                    unit_instance_id=PASSENGER_ID,
                    model_instance_id=model.model_instance_id,
                    pose=pose,
                )
                for model, pose in zip(passenger.own_models, poses, strict=True)
            ),
        ),
        transport_unit_instance_id=TRANSPORT_ID,
        disembark_mode=DisembarkModeKind.SHOCK_DISEMBARK,
        transport_movement_status=TransportMovementStatus.NOT_MOVED,
        restriction_overrides=shock_disembark_restriction_overrides(
            state=state,
            player_id="player-a",
            battle_round=1,
            rules_unit_instance_id=PASSENGER_ID,
            transport_unit_instance_id=TRANSPORT_ID,
        ),
        start_engaged_enemy_unit_instance_ids=tuple(str(value) for value in start_ids),
    )
    return request, proposal
