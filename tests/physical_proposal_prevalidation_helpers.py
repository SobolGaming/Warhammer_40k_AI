"""Canonical facade boundaries for physical proposal ingress regression tests."""

from __future__ import annotations

from tests.charge_distance_helpers import request_from, select_targets
from tests.charge_endpoint_helpers import (
    ATTACHED_TARGET,
    attached_charge_session,
    attached_move_payload,
    select_attached_source,
)
from tests.disembark_eligibility_helpers import TRANSPORT_ID
from tests.movement_submission_helpers import straight_line_witness_for_unit
from tests.order63_reserve_transport_helpers import placement, reserve_transport_session
from tests.phase15c_fight_order_helpers import fight_lifecycle
from tests.surge_fixed_target_helpers import (
    fixed_target_surge_payload,
    fixed_target_surge_request,
    fixed_target_surge_session,
)
from warhammer40k_core.adapters.local_session import LocalGameSession
from warhammer40k_core.engine.battlefield_state import BattlefieldPlacementKind
from warhammer40k_core.engine.decision_request import DecisionRequest
from warhammer40k_core.engine.event_log import JsonValue, validate_json_value
from warhammer40k_core.engine.movement_proposals import (
    MovementProposalPayload,
    MovementProposalRequest,
    PlacementProposalPayload,
)
from warhammer40k_core.engine.phase import BattlePhase
from warhammer40k_core.geometry.pose import Pose

FAMILIES = ("surge", "charge", "normal", "placement", "fight")


def proposal_session(family: str) -> tuple[LocalGameSession, DecisionRequest, dict[str, JsonValue]]:
    if family == "surge":
        session = fixed_target_surge_session(attached=True)
        request = fixed_target_surge_request(session)
        payload = fixed_target_surge_payload(session, request)
    elif family == "charge":
        session = attached_charge_session()
        request = select_targets(session, select_attached_source(session), (ATTACHED_TARGET,))
        payload = attached_move_payload(session, request)
    elif family == "placement":
        session = reserve_transport_session()
        request = request_from(session.advance_until_decision_or_terminal())
        request = request_from(
            session.submit_option(
                request_id=request.request_id, option_id=TRANSPORT_ID, result_id="order76-select"
            )
        )
        request = request_from(
            session.submit_option(
                request_id=request.request_id, option_id="ingress", result_id="order76-ingress"
            )
        )
        proposal = MovementProposalRequest.from_decision_request_payload(request.payload)
        payload = validate_json_value(
            PlacementProposalPayload(
                proposal_request_id=request.request_id,
                proposal_kind=proposal.proposal_kind,
                unit_instance_id=TRANSPORT_ID,
                placement_kind=BattlefieldPlacementKind.STRATEGIC_RESERVES,
                attempted_placement=placement(session, TRANSPORT_ID, x=12, y=2),
            ).to_payload()
        )
    elif family in {"normal", "fight"}:
        lifecycle, _ = fight_lifecycle(
            alpha_unit_ids=("source",),
            enemy_unit_ids=("enemy",),
            origins={
                "source": Pose.at(10, 20),
                "enemy": Pose.at(10, 23 if family == "fight" else 35),
            },
            game_id=f"order76-{family}",
            battle_phase=BattlePhase.FIGHT if family == "fight" else BattlePhase.MOVEMENT,
        )
        session = LocalGameSession(lifecycle)
        request = request_from(session.advance_until_decision_or_terminal())
        if family == "normal":
            request = request_from(
                session.submit_option(
                    request_id=request.request_id,
                    option_id="army-alpha:source",
                    result_id="order76-select",
                )
            )
            request = request_from(
                session.submit_option(
                    request_id=request.request_id,
                    option_id="normal_move",
                    result_id="order76-normal",
                )
            )
        proposal = MovementProposalRequest.from_decision_request_payload(request.payload)
        assert proposal.context is not None
        if family == "fight":
            payload = {
                "proposal_request_id": request.request_id,
                "proposal_kind": proposal.proposal_kind.value,
                "unit_instance_id": proposal.unit_instance_id,
                "movement_phase_action": proposal.movement_phase_action,
                "movement_mode": proposal.context["movement_mode"],
            }
        else:
            payload = validate_json_value(
                MovementProposalPayload(
                    proposal_request_id=request.request_id,
                    proposal_kind=proposal.proposal_kind,
                    unit_instance_id=proposal.unit_instance_id,
                    movement_phase_action="normal_move",
                    movement_mode="normal",
                    witness=straight_line_witness_for_unit(
                        lifecycle, unit_instance_id=proposal.unit_instance_id, dx=1
                    ),
                ).to_payload()
            )
    else:
        raise AssertionError(f"Unknown proposal family: {family}")
    assert isinstance(payload, dict)
    return session, request, payload
