"""Shared accepted movement choices, proposal provenance and capability commitments."""

from __future__ import annotations

from typing import TYPE_CHECKING, cast

from warhammer40k_core.engine.decision_record import DecisionRecord
from warhammer40k_core.engine.decision_request import DecisionRequest
from warhammer40k_core.engine.decision_result import DecisionResult
from warhammer40k_core.engine.event_log import EventRecord, JsonValue
from warhammer40k_core.engine.flight_decision_authority import (
    invalid_flight_authority,
    validate_restored_flight,
)
from warhammer40k_core.engine.move_keyword_authority import (
    invalid_move_keyword_authority,
    validate_restored_move_keywords,
)
from warhammer40k_core.engine.movement_proposals import (
    MOVEMENT_PROPOSAL_DECISION_TYPE,
    MovementProposalPayload,
    MovementProposalPayloadPayload,
    MovementProposalRequest,
    ProposalKind,
)
from warhammer40k_core.engine.mutation_decision_authority import (
    authoritative_decision_records,
    validate_mutation_decision_closure,
    validate_record_event_closure,
)
from warhammer40k_core.engine.phase import BattlePhase, GameLifecycleError, LifecycleStatus
from warhammer40k_core.engine.phases.movement_model import SELECT_MOVEMENT_ACTION_DECISION_TYPE

if TYPE_CHECKING:
    from warhammer40k_core.engine.decision_controller import DecisionController
    from warhammer40k_core.engine.game_state import GameState


def invalid_movement_authority(
    *,
    state: GameState,
    decisions: DecisionController,
    request: DecisionRequest,
    result: DecisionResult,
) -> LifecycleStatus | None:
    return invalid_flight_authority(
        state=state, decisions=decisions, request=request, result=result
    ) or invalid_move_keyword_authority(
        state=state,
        decisions=decisions,
        request=request,
        result=result,
    )


def validate_restored_movement(*, state: GameState, decisions: DecisionController) -> None:
    validate_restored_flight(state=state, decisions=decisions)
    validate_restored_move_keywords(state=state, decisions=decisions)
    from warhammer40k_core.engine.move_keyword_completion import validate_move_keyword_history

    validate_move_keyword_history(state=state, decisions=decisions)


_MOVING_ACTION_KINDS = frozenset({"normal_move", "advance", "fall_back"})


def validate_movement_completion_decision_authority(
    *,
    event_records: tuple[EventRecord, ...],
    decision_records: tuple[DecisionRecord, ...],
    mutation_index: int,
    payload: dict[str, JsonValue],
) -> MovementProposalPayload | None:
    """Authenticate ordinary movement classification and its accepted proposal chain."""
    action_record = validate_mutation_decision_closure(
        event_records=event_records,
        decision_records=decision_records,
        mutation_index=mutation_index,
        request_id=_payload_string(payload, "request_id"),
        result_id=_payload_string(payload, "result_id"),
    )
    action = _payload_string(payload, "movement_phase_action")
    unit_id = _payload_string(payload, "unit_instance_id")
    _validate_action_record(record=action_record, payload=payload, action=action, unit_id=unit_id)
    if action not in _MOVING_ACTION_KINDS:
        if payload.get("witness") is not None or payload.get("transition_batch") is not None:
            raise GameLifecycleError("Primary mission stationary movement mutation drifted.")
        return None

    proposal_records = tuple(
        record
        for record in authoritative_decision_records(decision_records)
        if record.request.decision_type == MOVEMENT_PROPOSAL_DECISION_TYPE
        and (
            record.request.request_id == payload.get("proposal_request_id")
            if action == "normal_move"
            else _movement_proposal_request_sources(record)
            == (action_record.request.request_id, action_record.result.result_id)
        )
    )
    if len(proposal_records) != 1:
        raise GameLifecycleError("Primary mission movement proposal authority drifted.")
    proposal_record = proposal_records[0]
    validate_record_event_closure(
        event_records=event_records,
        mutation_index=mutation_index,
        record=proposal_record,
    )
    if proposal_record.request.decision_type != MOVEMENT_PROPOSAL_DECISION_TYPE:
        raise GameLifecycleError("Primary mission movement proposal type drifted.")
    proposal_request = MovementProposalRequest.from_decision_request_payload(
        proposal_record.request.payload
    )
    if _movement_proposal_request_sources(proposal_record) != (
        action_record.request.request_id,
        action_record.result.result_id,
    ) or (
        action == "normal_move"
        and (
            proposal_request.proposal_kind is not ProposalKind.NORMAL_MOVE
            or proposal_request.context is None
            or proposal_request.context.get("source_selected_option_id")
            != action_record.result.selected_option_id
        )
    ):
        raise GameLifecycleError("Normal Move proposal source action authority drifted.")
    if action == "normal_move":
        proposal_request_index = next(
            index
            for index, event in enumerate(event_records[:mutation_index])
            if event.event_type == "decision_requested"
            and event.payload == proposal_record.request.to_payload()
        )
        validate_record_event_closure(
            event_records=event_records, mutation_index=proposal_request_index, record=action_record
        )
    result_payload = proposal_record.result.payload
    if not isinstance(result_payload, dict):
        raise GameLifecycleError("Primary mission movement proposal result is invalid.")
    proposal = MovementProposalPayload.from_payload(
        cast(MovementProposalPayloadPayload, result_payload)
    )
    validation = proposal.validation_result_for_request(proposal_request)
    if not validation.is_valid:
        raise GameLifecycleError("Primary mission movement proposal/result authority drifted.")
    if (
        proposal_record.request.actor_id != payload.get("active_player_id")
        or proposal_record.result.actor_id != payload.get("active_player_id")
        or proposal_request.game_id != payload.get("game_id")
        or proposal_request.battle_round != payload.get("battle_round")
        or proposal_request.phase != payload.get("phase")
        or proposal_request.actor_id != payload.get("active_player_id")
        or proposal_request.unit_instance_id != unit_id
        or proposal_request.movement_phase_action != action
        or proposal.unit_instance_id != unit_id
        or proposal.movement_phase_action != action
        or payload.get("witness") != proposal.witness.to_payload()
    ):
        raise GameLifecycleError("Primary mission movement proposal semantics drifted.")
    return proposal


def _movement_proposal_request_sources(record: DecisionRecord) -> tuple[str, str]:
    proposal_request = MovementProposalRequest.from_decision_request_payload(record.request.payload)
    return (
        proposal_request.source_decision_request_id,
        proposal_request.source_decision_result_id,
    )


def _validate_action_record(
    *,
    record: DecisionRecord,
    payload: dict[str, JsonValue],
    action: str,
    unit_id: str,
) -> None:
    request_payload = record.request.payload
    result_payload = record.result.payload
    if not isinstance(request_payload, dict) or not isinstance(result_payload, dict):
        raise GameLifecycleError("Primary mission movement action decision payload is invalid.")
    selected = record.request.option_by_id(record.result.selected_option_id)
    if (
        record.request.decision_type != SELECT_MOVEMENT_ACTION_DECISION_TYPE
        or record.result.decision_type != SELECT_MOVEMENT_ACTION_DECISION_TYPE
        or record.request.actor_id != payload.get("active_player_id")
        or record.result.actor_id != payload.get("active_player_id")
        or request_payload.get("game_id") != payload.get("game_id")
        or request_payload.get("battle_round") != payload.get("battle_round")
        or payload.get("phase") != BattlePhase.MOVEMENT.value
        or request_payload.get("phase") != BattlePhase.MOVEMENT.value
        or request_payload.get("active_player_id") != payload.get("active_player_id")
        or request_payload.get("unit_instance_id") != unit_id
        or result_payload.get("unit_instance_id") != unit_id
        or result_payload.get("movement_phase_action") != action
        or selected.payload != result_payload
    ):
        raise GameLifecycleError("Primary mission movement action decision semantics drifted.")


def _payload_string(payload: dict[str, JsonValue], key: str) -> str:
    value = payload.get(key)
    if type(value) is not str or not value:
        raise GameLifecycleError(f"Movement completion {key} is invalid.")
    return value
