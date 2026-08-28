from __future__ import annotations

from typing import TYPE_CHECKING, cast

from warhammer40k_core.engine.battle_shock import (
    BattleShockTestRequest,
)
from warhammer40k_core.engine.command_battle_shock_candidates import (
    CommandBattleShockCandidate,
    command_battle_shock_request_id,
)
from warhammer40k_core.engine.command_points import CommandStepState
from warhammer40k_core.engine.decision_record import DecisionRecord
from warhammer40k_core.engine.decision_request import DecisionRequest
from warhammer40k_core.engine.event_log import EventRecord, JsonValue, validate_json_value
from warhammer40k_core.engine.phase import BattlePhase, GameLifecycleError
from warhammer40k_core.engine.sequencing import (
    SEQUENCING_DECISION_TYPE,
    SequencingConflictContext,
    SequencingConflictContextPayload,
    SequencingDecision,
    SequencingDecisionPayload,
    SequencingParticipant,
    apply_sequencing_decision_from_request,
    create_sequencing_decision_request,
)

if TYPE_CHECKING:
    from warhammer40k_core.engine.game_state import GameState


def validate_request_against_candidate(
    *,
    request: BattleShockTestRequest,
    candidate: CommandBattleShockCandidate,
) -> None:
    if (
        request.unit_instance_id != candidate.unit_instance_id
        or candidate.test_reason is None
        or request.reason is not candidate.test_reason
    ):
        raise GameLifecycleError("Command Battle-shock request eligibility snapshot drifted.")


def validate_historical_request_context(
    *,
    state: GameState,
    request: BattleShockTestRequest,
    battle_round: int,
    active_player_id: str,
    candidate: CommandBattleShockCandidate,
) -> None:
    validate_request_against_candidate(request=request, candidate=candidate)
    if (
        request.game_id != state.game_id
        or request.battle_round != battle_round
        or request.player_id != active_player_id
        or request.request_id
        != command_battle_shock_request_id(
            battle_round=battle_round,
            active_player_id=active_player_id,
            unit_instance_id=request.unit_instance_id,
            reason=request.reason,
        )
    ):
        raise GameLifecycleError("Historical Command Battle-shock request context drifted.")


def candidate_by_id(
    candidates: tuple[CommandBattleShockCandidate, ...],
    unit_instance_id: str,
) -> CommandBattleShockCandidate:
    matching = tuple(
        candidate for candidate in candidates if candidate.unit_instance_id == unit_instance_id
    )
    if len(matching) != 1:
        raise GameLifecycleError("Command Battle-shock candidate identity is ambiguous.")
    return matching[0]


def ordered_candidates_by_request_id(
    command_state: object,
) -> dict[str, CommandBattleShockCandidate]:
    if type(command_state) is not CommandStepState:
        raise GameLifecycleError("Command Battle-shock history requires CommandStepState.")
    candidates_by_id = {
        candidate.unit_instance_id: candidate
        for candidate in command_state.battle_shock_candidate_inventory
        if candidate.test_reason is not None
    }
    ordered: dict[str, CommandBattleShockCandidate] = {}
    for unit_id in command_state.battle_shock_candidate_order_unit_ids:
        candidate = candidates_by_id[unit_id]
        reason = candidate.test_reason
        if reason is None:
            raise GameLifecycleError("Command Battle-shock ordered candidate is not eligible.")
        request_id = command_battle_shock_request_id(
            battle_round=command_state.battle_round,
            active_player_id=command_state.active_player_id,
            unit_instance_id=unit_id,
            reason=reason,
        )
        ordered[request_id] = candidate
    return ordered


def validate_historical_candidate_order(
    *,
    state: GameState,
    event_records: tuple[EventRecord, ...],
    decision_records: tuple[DecisionRecord, ...],
    snapshot_index: int,
    completion_index: int,
    battle_round: int,
    active_player_id: str,
    candidates: tuple[CommandBattleShockCandidate, ...],
    ordered_unit_ids: tuple[str, ...],
) -> None:
    conflict_id = (
        f"command-battle-shock-order:{state.game_id}:round-{battle_round:02d}:{active_player_id}"
    )
    matching_events: list[tuple[int, SequencingDecision]] = []
    for event_index, event in enumerate(event_records):
        if event.event_type != "sequencing_order_resolved":
            continue
        if not isinstance(event.payload, dict):
            raise GameLifecycleError("Historical Battle-shock sequencing payload is malformed.")
        if event.payload.get("conflict_id") != conflict_id:
            continue
        matching_events.append(
            (
                event_index,
                SequencingDecision.from_payload(cast(SequencingDecisionPayload, event.payload)),
            )
        )
    expected_unit_ids = {candidate.unit_instance_id for candidate in candidates}
    if len(candidates) < 2:
        expected_trivial_order = tuple(candidate.unit_instance_id for candidate in candidates)
        if matching_events or ordered_unit_ids != expected_trivial_order:
            raise GameLifecycleError("Historical Battle-shock trivial order drifted.")
        return
    if len(matching_events) != 1:
        raise GameLifecycleError("Historical Battle-shock sequencing authority is ambiguous.")
    event_index, sequencing_decision = matching_events[0]
    if not snapshot_index < event_index < completion_index:
        raise GameLifecycleError("Historical Battle-shock sequencing escaped its step.")
    records = tuple(
        record
        for record in decision_records
        if record.request.request_id == sequencing_decision.request_id
        and record.result.result_id == sequencing_decision.result_id
    )
    if len(records) != 1:
        raise GameLifecycleError("Historical Battle-shock sequencing lacks a decision record.")
    record = records[0]
    validate_historical_sequencing_request(
        state=state,
        request=record.request,
        battle_round=battle_round,
        active_player_id=active_player_id,
        candidates=candidates,
    )
    if (
        apply_sequencing_decision_from_request(
            request=record.request,
            result=record.result,
        )
        != sequencing_decision
    ):
        raise GameLifecycleError("Historical Battle-shock sequencing decision drifted.")
    unit_id_by_participant = {
        f"command-battle-shock-test:{candidate.unit_instance_id}": candidate.unit_instance_id
        for candidate in candidates
    }
    if (
        tuple(
            unit_id_by_participant.get(participant_id, "")
            for participant_id in sequencing_decision.ordered_participant_ids
        )
        != ordered_unit_ids
        or set(ordered_unit_ids) != expected_unit_ids
    ):
        raise GameLifecycleError("Historical Battle-shock sequencing order drifted.")


def validate_historical_sequencing_request(
    *,
    state: GameState,
    request: DecisionRequest,
    battle_round: int,
    active_player_id: str,
    candidates: tuple[CommandBattleShockCandidate, ...],
) -> None:
    if request.decision_type != SEQUENCING_DECISION_TYPE or request.actor_id != active_player_id:
        raise GameLifecycleError("Historical Battle-shock sequencing request drifted.")
    conflict_id = (
        f"command-battle-shock-order:{state.game_id}:round-{battle_round:02d}:{active_player_id}"
    )
    request_payload = payload_object(request.payload)
    conflict = payload_object(request_payload.get("sequencing_conflict"))
    timing_window = payload_object(conflict.get("timing_window"))
    descriptor = payload_object(timing_window.get("descriptor"))
    if (
        conflict.get("conflict_id") != conflict_id
        or conflict.get("game_id") != state.game_id
        or conflict.get("player_ids") != list(state.player_ids)
        or conflict.get("active_player_id") != active_player_id
        or timing_window.get("window_id") != f"timing-window:{conflict_id}"
        or timing_window.get("game_id") != state.game_id
        or timing_window.get("battle_round") != battle_round
        or timing_window.get("active_player_id") != active_player_id
        or timing_window.get("phase") != BattlePhase.COMMAND.value
        or descriptor.get("descriptor_id") != "command-battle-shock-test-order"
        or descriptor.get("trigger_kind") != "during_phase"
        or descriptor.get("source_rule_id") != "gw-11e-core-rules:command-phase:battle-shock"
        or descriptor.get("phase") != BattlePhase.COMMAND.value
        or descriptor.get("source_step") != "battle_shock"
        or descriptor.get("metadata") != {"candidate_scope": "required_command_battle_shock_tests"}
    ):
        raise GameLifecycleError("Historical Battle-shock sequencing context drifted.")
    participants = tuple(
        SequencingParticipant(
            participant_id=f"command-battle-shock-test:{candidate.unit_instance_id}",
            player_id=active_player_id,
            source_rule_id="gw-11e-core-rules:command-phase:battle-shock",
            payload=validate_json_value(candidate.to_payload()),
        )
        for candidate in candidates
    )
    if request_payload.get("participants") != [
        participant.to_payload() for participant in participants
    ]:
        raise GameLifecycleError("Historical Battle-shock sequencing participants drifted.")
    try:
        context = SequencingConflictContext.from_payload(
            cast(SequencingConflictContextPayload, conflict)
        )
    except KeyError as exc:
        raise GameLifecycleError(
            "Historical Battle-shock sequencing context is incomplete."
        ) from exc
    expected_request = create_sequencing_decision_request(
        request_id=request.request_id,
        context=context,
        participants=participants,
    )
    if request != expected_request:
        raise GameLifecycleError("Historical Battle-shock sequencing request payload drifted.")


def validate_pending_order_restore_authority(
    *,
    state: GameState,
    pending_decision_requests: tuple[DecisionRequest, ...],
) -> None:
    command_state = state.command_step_state
    if (
        command_state is None
        or command_state.current_step.value != "battle_shock"
        or command_state.battle_shock_step_resolved
    ):
        return
    candidates = tuple(
        candidate
        for candidate in command_state.battle_shock_candidate_inventory
        if candidate.test_reason is not None
    )
    conflict_id = (
        f"command-battle-shock-order:{state.game_id}:"
        f"round-{command_state.battle_round:02d}:{command_state.active_player_id}"
    )
    matching = tuple(
        request
        for request in pending_decision_requests
        if request.decision_type == SEQUENCING_DECISION_TYPE
        and sequencing_request_conflict_id(request) == conflict_id
    )
    if command_state.battle_shock_candidate_order_unit_ids or len(candidates) < 2:
        if matching:
            raise GameLifecycleError("Command Battle-shock has an excess sequencing request.")
        return
    if len(matching) != 1 or len(pending_decision_requests) != 1:
        raise GameLifecycleError("Command Battle-shock pending sequencing authority drifted.")
    validate_historical_sequencing_request(
        state=state,
        request=matching[0],
        battle_round=command_state.battle_round,
        active_player_id=command_state.active_player_id,
        candidates=candidates,
    )


def sequencing_request_conflict_id(request: DecisionRequest) -> str | None:
    payload = request.payload
    if not isinstance(payload, dict):
        return None
    conflict = payload.get("sequencing_conflict")
    if not isinstance(conflict, dict):
        return None
    conflict_id = conflict.get("conflict_id")
    return conflict_id if type(conflict_id) is str else None


def payload_object(value: JsonValue) -> dict[str, JsonValue]:
    if not isinstance(value, dict):
        raise GameLifecycleError("Command Battle-shock event payload must be an object.")
    return value


def raw_result_request_id(value: JsonValue) -> str | None:
    if not isinstance(value, dict):
        return None
    raw_result = value.get("battle_shock_result")
    if not isinstance(raw_result, dict):
        return None
    raw_request = raw_result.get("request")
    if not isinstance(raw_request, dict):
        return None
    request_id = raw_request.get("request_id")
    return request_id if type(request_id) is str and request_id else None


def payload_string(payload: dict[str, JsonValue], key: str) -> str:
    value = payload.get(key)
    if type(value) is not str or not value:
        raise GameLifecycleError(f"Command Battle-shock payload {key} is invalid.")
    return value


def payload_int(payload: dict[str, JsonValue], key: str) -> int:
    value = payload.get(key)
    if type(value) is not int:
        raise GameLifecycleError(f"Command Battle-shock payload {key} is invalid.")
    return value
