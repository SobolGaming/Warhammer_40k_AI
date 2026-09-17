"""Bind move-scoped grants to their finite decisions before queue pop and restore."""

from __future__ import annotations

from typing import TYPE_CHECKING, cast

from warhammer40k_core.engine.decision_request import DecisionError, DecisionRequest
from warhammer40k_core.engine.decision_result import DecisionResult
from warhammer40k_core.engine.event_log import JsonValue
from warhammer40k_core.engine.move_ability_choices import (
    CHOICE_KEY,
    choice_descriptor,
    choice_fields,
    descriptors_for_move,
    keyword_choice_context,
    movement_ability_keywords,
    recorded_choice_fields,
)
from warhammer40k_core.engine.movement_proposals import (
    MOVEMENT_PROPOSAL_DECISION_TYPE,
    MovementProposalRequest,
    ProposalKind,
)
from warhammer40k_core.engine.phase import GameLifecycleError, LifecycleStatus
from warhammer40k_core.engine.rules_units import rules_unit_view_by_id

if TYPE_CHECKING:
    from warhammer40k_core.engine.decision_controller import DecisionController
    from warhammer40k_core.engine.game_state import GameState


def validate_move_keyword_selection(*, state: GameState, payload: JsonValue) -> None:
    if not isinstance(payload, dict):
        raise GameLifecycleError("Movement keyword selection must be an object.")
    mode = payload.get("movement_mode")
    descriptor = payload.get("descriptor")
    if isinstance(descriptor, dict):
        mode = descriptor.get("movement_mode")
    if payload.get("declined"):
        if CHOICE_KEY in payload:
            raise GameLifecycleError("Declined movement cannot grant movement keywords.")
        return
    if mode is None and payload.get("movement_phase_action") in {
        "remain_stationary",
        "ingress",
        "disembark",
    }:
        if CHOICE_KEY in payload:
            raise GameLifecycleError("Placement or stationary actions cannot grant move keywords.")
        return
    unit_id = payload.get("unit_instance_id")
    if not isinstance(unit_id, str):
        raise GameLifecycleError("Movement keyword selection requires its moving unit.")
    unit = rules_unit_view_by_id(state=state, unit_instance_id=unit_id)
    available = descriptors_for_move(
        movement_ability_keywords(unit),
        str(mode),
        is_surge=isinstance(descriptor, dict) and descriptor.get("movement_kind") == "surge",
    )
    if not available:
        if CHOICE_KEY in payload:
            raise GameLifecycleError("Movement keyword source is no longer available.")
        return
    choice = payload.get(CHOICE_KEY)
    selected_descriptor = choice_descriptor(choice)
    if (
        not isinstance(choice, dict)
        or selected_descriptor not in available
        or choice
        != keyword_choice_context(
            descriptor=selected_descriptor,
            unit=unit,
            selected=cast(bool, choice["selected"]),
        )
    ):
        raise GameLifecycleError("Movement keyword model membership or source drift.")


def validate_move_keyword_request(
    *,
    state: GameState,
    decisions: DecisionController,
    request: DecisionRequest,
) -> None:
    context = request.payload
    requires_selection = False
    if request.decision_type == MOVEMENT_PROPOSAL_DECISION_TYPE:
        proposal = MovementProposalRequest.from_decision_request_payload(request.payload)
        requires_selection = proposal.proposal_kind in {
            ProposalKind.NORMAL_MOVE,
            ProposalKind.ADVANCE,
            ProposalKind.FALL_BACK,
            ProposalKind.SURGE_MOVE,
        }
        context = proposal.context
        if not isinstance(context, dict):
            if requires_selection:
                raise GameLifecycleError("Movement keyword proposal lost its selection context.")
            return
        if context.get("context_kind") == "triggered_movement":
            request_id, result_id = (
                context.get("selection_request_id"),
                context.get("selection_result_id"),
            )
        else:
            request_id, result_id = (
                proposal.source_decision_request_id,
                proposal.source_decision_result_id,
            )
        if request_id is None or result_id is None:
            if requires_selection or CHOICE_KEY in context:
                raise GameLifecycleError("Movement keyword proposal lost its finite choice.")
            return
    elif (
        isinstance(context, dict)
        and context.get("context_kind") == "triggered_movement_distance_reroll"
    ):
        requires_selection = True
        request_id, result_id = (
            context.get("selection_request_id"),
            context.get("selection_result_id"),
        )
    else:
        return
    if not isinstance(request_id, str) or not isinstance(result_id, str):
        raise GameLifecycleError("Movement keyword proposal source identity is missing.")
    records = tuple(
        r
        for r in decisions.records
        if r.request.request_id == request_id and r.result.result_id == result_id
    )
    if len(records) != 1:
        # Other proposal families retain their own source contract.
        if requires_selection or CHOICE_KEY in context:
            raise GameLifecycleError("Movement keyword proposal source was not recorded.")
        return
    record = records[0]
    record.result.validate_for_request(record.request)
    expected = recorded_choice_fields(
        decisions=decisions, request_id=request_id, result_id=result_id
    )
    if choice_fields(context) != expected:
        raise GameLifecycleError(
            "Movement keyword proposal differs from its original finite choice."
        )
    if requires_selection or expected:
        validate_move_keyword_selection(state=state, payload=record.result.payload)
    if not expected:
        return
    choice = expected[CHOICE_KEY]
    if not isinstance(choice, dict):
        raise GameLifecycleError("Movement keyword choice must be an object.")
    if request.decision_type == MOVEMENT_PROPOSAL_DECISION_TYPE:
        proposal = MovementProposalRequest.from_decision_request_payload(request.payload)
        if (
            proposal.unit_instance_id != choice["unit_instance_id"]
            or proposal.actor_id != record.result.actor_id
        ):
            raise GameLifecycleError("Movement keyword proposal moving unit or owner drift.")


def invalid_move_keyword_authority(
    *,
    state: GameState,
    decisions: DecisionController,
    request: DecisionRequest,
    result: DecisionResult,
) -> LifecycleStatus | None:
    from warhammer40k_core.engine.phases.movement_model import SELECT_MOVEMENT_ACTION_DECISION_TYPE
    from warhammer40k_core.engine.triggered_movement import SELECT_TRIGGERED_MOVEMENT_DECISION_TYPE

    try:
        if request.decision_type in {
            SELECT_MOVEMENT_ACTION_DECISION_TYPE,
            SELECT_TRIGGERED_MOVEMENT_DECISION_TYPE,
        }:
            result.validate_for_request(request)
            validate_move_keyword_selection(state=state, payload=result.payload)
        else:
            validate_move_keyword_request(state=state, decisions=decisions, request=request)
    except (DecisionError, GameLifecycleError) as exc:
        return LifecycleStatus.invalid(
            stage=state.stage,
            message=str(exc),
            payload={"invalid_reason": "move_keyword_authority_drift"},
        )
    return None


def validate_restored_move_keywords(*, state: GameState, decisions: DecisionController) -> None:
    for request in decisions.queue.pending_requests:
        validate_move_keyword_request(state=state, decisions=decisions, request=request)
