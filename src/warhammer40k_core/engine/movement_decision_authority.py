"""Shared accepted movement choices, proposal provenance and capability commitments."""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, cast

from warhammer40k_core.engine.battlefield_state import BattlefieldTransitionBatch
from warhammer40k_core.engine.battlefield_transition_history import (
    authoritative_battlefield_transition_batch_or_none,
    prior_fall_back_applied_transition_or_none,
)
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


@dataclass(frozen=True, slots=True)
class EmbarkMovementCompletion:
    """An accepted pre-Embark move and its later completion report."""

    embark_event_id: str
    completion_event_id: str
    transition_before_embark: BattlefieldTransitionBatch | None


def validated_embark_movement_completions(
    *,
    event_records: tuple[EventRecord, ...],
    decision_records: tuple[DecisionRecord, ...],
) -> tuple[EmbarkMovementCompletion, ...]:
    """Bind each Embark's accepted movement context to its exact delayed report."""
    completed: set[int] = set()
    bindings: list[EmbarkMovementCompletion] = []
    for index, event in enumerate(event_records):
        if event.event_type != "unit_embarked":
            continue
        payload = event.payload
        if not isinstance(payload, dict):
            raise GameLifecycleError("Embark event payload is invalid.")
        record = validate_mutation_decision_closure(
            event_records=event_records,
            decision_records=decision_records,
            mutation_index=index,
            request_id=_payload_string(payload, "request_id"),
            result_id=_payload_string(payload, "result_id"),
        )
        request_payload = record.request.payload
        if (
            record.request.decision_type != "select_embark_transport"
            or record.result.selected_option_id != payload.get("transport_unit_instance_id")
            or record.request.actor_id != payload.get("active_player_id")
            or not isinstance(request_payload, dict)
        ):
            raise GameLifecycleError("Embark decision authority drift.")
        context = request_payload.get("movement_context")
        if not isinstance(context, dict):
            raise GameLifecycleError("Embark movement context is invalid.")
        movement_payload = context.get("movement_payload")
        if not isinstance(movement_payload, dict):
            raise GameLifecycleError("Embark movement context is invalid.")
        for key in ("game_id", "battle_round", "active_player_id", "phase", "unit_instance_id"):
            if request_payload.get(key) != payload.get(key):
                raise GameLifecycleError("Embark request context drift.")
        expected = {
            **{
                key: payload[key]
                for key in (
                    "game_id",
                    "battle_round",
                    "active_player_id",
                    "phase",
                    "unit_instance_id",
                )
            },
            "request_id": _payload_string(context, "action_request_id"),
            "result_id": _payload_string(context, "action_result_id"),
            "movement_phase_action": context.get("movement_phase_action"),
            "witness": context.get("witness"),
            "displacement_kind": context.get("displacement_kind"),
            "transition_batch": context.get("transition_batch"),
            **movement_payload,
        }
        matches = tuple(
            (terminal_index, terminal)
            for terminal_index, terminal in enumerate(event_records)
            if terminal.event_type == "movement_activation_completed"
            and isinstance(terminal.payload, dict)
            and terminal.payload.get("request_id") == expected["request_id"]
            and terminal.payload.get("result_id") == expected["result_id"]
        )
        if len(matches) != 1 or matches[0][0] <= index or matches[0][0] in completed:
            raise GameLifecycleError("Embark completion identity drift.")
        terminal_index, terminal = matches[0]
        terminal_payload = terminal.payload
        if not isinstance(terminal_payload, dict):
            raise GameLifecycleError("Embark movement completion payload is invalid.")
        if any(terminal_payload.get(key) != value for key, value in expected.items()):
            raise GameLifecycleError("Embark completion context drift.")
        validate_movement_completion_decision_authority(
            event_records=event_records,
            decision_records=decision_records,
            mutation_index=index,
            payload=terminal_payload,
        )
        transition = authoritative_battlefield_transition_batch_or_none(event=terminal)
        if transition is None:
            raise GameLifecycleError("Embark movement transition authority is missing.")
        if (
            prior_fall_back_applied_transition_or_none(
                event_records=event_records,
                event_index=terminal_index,
                event=terminal,
            )
            is not None
        ):
            transition = None
        bindings.append(EmbarkMovementCompletion(event.event_id, terminal.event_id, transition))
        completed.add(terminal_index)
    return tuple(bindings)


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
