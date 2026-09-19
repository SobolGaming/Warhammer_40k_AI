"""Pre-pop setup-turn restriction checks for ordinary and reactive decisions."""

from __future__ import annotations

from warhammer40k_core.engine.decision_controller import DecisionController
from warhammer40k_core.engine.decision_request import DecisionRequest
from warhammer40k_core.engine.decision_result import DecisionResult
from warhammer40k_core.engine.game_state import GameState
from warhammer40k_core.engine.large_model_restrictions import large_model_activity_reason
from warhammer40k_core.engine.movement_proposals import (
    MOVEMENT_PROPOSAL_DECISION_TYPE,
    MovementProposalRequest,
    ProposalKind,
)
from warhammer40k_core.engine.phase import LifecycleStatus
from warhammer40k_core.engine.phases.movement_model import SELECT_MOVEMENT_ACTION_DECISION_TYPE
from warhammer40k_core.engine.surge_authority import invalid_surge_authority
from warhammer40k_core.engine.triggered_movement import (
    SELECT_TRIGGERED_MOVEMENT_DECISION_TYPE,
    is_triggered_movement_distance_reroll_request,
)


def invalid_setup_turn_activity(
    *,
    state: GameState,
    decisions: DecisionController,
    request: DecisionRequest,
    result: DecisionResult,
) -> LifecycleStatus | None:
    from warhammer40k_core.engine.transport_embark_prevalidation import invalid_embark_setup

    embark_invalid = invalid_embark_setup(state=state, request=request, result=result)
    if embark_invalid is not None:
        return embark_invalid
    reroll = is_triggered_movement_distance_reroll_request(request)
    if reroll:
        invalid = invalid_surge_authority(
            state=state, decisions=decisions, request=request, result=result
        )
        if invalid is not None:
            return invalid
    if (
        request.decision_type
        not in (
            MOVEMENT_PROPOSAL_DECISION_TYPE,
            SELECT_MOVEMENT_ACTION_DECISION_TYPE,
            SELECT_TRIGGERED_MOVEMENT_DECISION_TYPE,
        )
        and not reroll
    ):
        return None
    payload = result.payload
    if not isinstance(payload, dict) or payload.get("declined") is True:
        return None
    unit_id = payload.get("unit_instance_id")
    context = request.payload if isinstance(request.payload, dict) else {}
    activity: object = "normal"
    if request.decision_type == MOVEMENT_PROPOSAL_DECISION_TYPE:
        proposal = MovementProposalRequest.from_decision_request_payload(request.payload)
        if proposal.proposal_kind not in (
            ProposalKind.NORMAL_MOVE,
            ProposalKind.ADVANCE,
            ProposalKind.FALL_BACK,
            ProposalKind.CHARGE_MOVE,
        ):
            return None
        activity = "charge" if proposal.proposal_kind is ProposalKind.CHARGE_MOVE else "normal"
        context = proposal.context or {}
        unit_id = proposal.unit_instance_id
    if reroll:
        raw_context = context.get("context")
        context = raw_context if isinstance(raw_context, dict) else context
        selected = context.get("selected_unit")
        unit_id = selected.get("unit_instance_id") if isinstance(selected, dict) else unit_id
    descriptor = context.get("descriptor")
    if isinstance(descriptor, dict) and descriptor.get("movement_kind") == "surge":
        return None
    if payload.get("movement_phase_action") == "remain_stationary":
        return None
    if not isinstance(unit_id, str):
        return None
    activity = descriptor.get("movement_mode") if isinstance(descriptor, dict) else activity
    if not isinstance(activity, str):
        return None
    reason = large_model_activity_reason(state, unit_id, activity)
    if reason is not None:
        return LifecycleStatus.invalid(
            stage=state.stage, message=reason, payload={"invalid_reason": reason}
        )
    return None
