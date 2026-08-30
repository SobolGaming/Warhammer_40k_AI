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
from warhammer40k_core.engine.mutation_decision_authority import (
    validate_mutation_decision_closure,
)
from warhammer40k_core.engine.phase import BattlePhase, GameLifecycleError
from warhammer40k_core.engine.sequencing import (
    SEQUENCING_DECISION_TYPE,
    SequencingConflictContext,
    SequencingConflictContextPayload,
    SequencingNextParticipantDecision,
    SequencingNextParticipantDecisionPayload,
    SequencingParticipant,
    apply_select_next_sequencing_participant_from_request,
    create_select_next_sequencing_participant_request,
    is_select_next_sequencing_participant_request,
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
    matching_events: list[tuple[int, SequencingNextParticipantDecision]] = []
    for event_index, event in enumerate(event_records):
        if event.event_type != "sequencing_next_participant_selected":
            continue
        if not isinstance(event.payload, dict):
            raise GameLifecycleError("Historical Battle-shock sequencing payload is malformed.")
        if event.payload.get("conflict_id") != conflict_id:
            continue
        matching_events.append(
            (
                event_index,
                SequencingNextParticipantDecision.from_payload(
                    cast(SequencingNextParticipantDecisionPayload, event.payload)
                ),
            )
        )
    expected_unit_ids = {candidate.unit_instance_id for candidate in candidates}
    if len(candidates) < 2:
        expected_trivial_order = tuple(candidate.unit_instance_id for candidate in candidates)
        if matching_events or ordered_unit_ids != expected_trivial_order:
            raise GameLifecycleError("Historical Battle-shock trivial order drifted.")
        return
    participant_by_id = {
        f"command-battle-shock-test:{candidate.unit_instance_id}": SequencingParticipant(
            participant_id=f"command-battle-shock-test:{candidate.unit_instance_id}",
            player_id=active_player_id,
            source_rule_id="gw-11e-core-rules:command-phase:battle-shock",
            payload=validate_json_value(candidate.to_payload()),
        )
        for candidate in candidates
    }
    unit_id_by_participant = {
        f"command-battle-shock-test:{candidate.unit_instance_id}": candidate.unit_instance_id
        for candidate in candidates
    }
    selected_participant_ids: list[str] = []
    remaining_participant_ids = list(participant_by_id)
    context: SequencingConflictContext | None = None
    previous_selection_event_index = snapshot_index
    for event_index, sequencing_decision in matching_events:
        if not snapshot_index < event_index < completion_index:
            raise GameLifecycleError("Historical Battle-shock sequencing escaped its step.")
        try:
            record = validate_mutation_decision_closure(
                event_records=event_records,
                decision_records=decision_records,
                mutation_index=event_index,
                request_id=sequencing_decision.request_id,
                result_id=sequencing_decision.result_id,
            )
        except GameLifecycleError as exc:
            raise GameLifecycleError(
                "Historical Battle-shock sequencing lacks a decision record."
            ) from exc
        request_event_indices = tuple(
            index
            for index, event in enumerate(event_records[:event_index])
            if event.event_type == "decision_requested"
            and event.payload == record.request.to_payload()
        )
        if len(request_event_indices) != 1:
            raise GameLifecycleError("Historical Battle-shock sequencing lacks a request event.")
        request_event_index = request_event_indices[0]
        if selected_participant_ids:
            previous_unit_id = unit_id_by_participant[selected_participant_ids[-1]]
            previous_candidate = candidate_by_id(candidates, previous_unit_id)
            previous_reason = previous_candidate.test_reason
            if previous_reason is None:
                raise GameLifecycleError(
                    "Historical Battle-shock preceding candidate is not eligible."
                )
            previous_request_id = command_battle_shock_request_id(
                battle_round=battle_round,
                active_player_id=active_player_id,
                unit_instance_id=previous_unit_id,
                reason=previous_reason,
            )
            resolved_indices = tuple(
                index
                for index, event in enumerate(
                    event_records[previous_selection_event_index + 1 : request_event_index],
                    start=previous_selection_event_index + 1,
                )
                if event.event_type == "battle_shock_test_resolved"
                and raw_result_request_id(event.payload) == previous_request_id
            )
            if len(resolved_indices) != 1:
                raise GameLifecycleError(
                    "Historical Battle-shock sequencing advanced before the preceding test "
                    "resolved."
                )
            _validate_intervening_decisions_closed(
                event_records=event_records,
                decision_records=decision_records,
                start_index=resolved_indices[0] + 1,
                end_index=request_event_index,
            )
        context = validate_historical_sequencing_request(
            state=state,
            request=record.request,
            battle_round=battle_round,
            active_player_id=active_player_id,
            candidates=tuple(
                candidate_by_id(candidates, unit_id_by_participant[participant_id])
                for participant_id in remaining_participant_ids
            ),
            previously_selected_participant_ids=tuple(selected_participant_ids),
        )
        if (
            sequencing_decision.previously_selected_participant_ids
            != tuple(selected_participant_ids)
            or sequencing_decision.remaining_participant_ids != tuple(remaining_participant_ids)
            or apply_select_next_sequencing_participant_from_request(
                request=record.request,
                result=record.result,
            )
            != sequencing_decision
        ):
            raise GameLifecycleError("Historical Battle-shock sequencing decision drifted.")
        selected_participant_ids.append(sequencing_decision.selected_participant_id)
        remaining_participant_ids.remove(sequencing_decision.selected_participant_id)
        previous_selection_event_index = event_index
    if context is None and matching_events:
        raise GameLifecycleError("Historical Battle-shock sequencing context is missing.")
    reconstructed_order = tuple(
        unit_id_by_participant[participant_id] for participant_id in selected_participant_ids
    )
    if len(remaining_participant_ids) == 1 and len(ordered_unit_ids) > len(reconstructed_order):
        reconstructed_order = (
            *reconstructed_order,
            unit_id_by_participant[remaining_participant_ids[0]],
        )
    if reconstructed_order != ordered_unit_ids or not set(ordered_unit_ids).issubset(
        expected_unit_ids
    ):
        raise GameLifecycleError("Historical Battle-shock sequencing order drifted.")
    if set(ordered_unit_ids) == expected_unit_ids and len(matching_events) != len(candidates) - 1:
        raise GameLifecycleError("Historical Battle-shock sequencing selection count drifted.")


def validate_historical_sequencing_request(
    *,
    state: GameState,
    request: DecisionRequest,
    battle_round: int,
    active_player_id: str,
    candidates: tuple[CommandBattleShockCandidate, ...],
    previously_selected_participant_ids: tuple[str, ...] = (),
) -> SequencingConflictContext:
    if (
        request.decision_type != SEQUENCING_DECISION_TYPE
        or request.actor_id != active_player_id
        or not is_select_next_sequencing_participant_request(request)
    ):
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
    expected_request = create_select_next_sequencing_participant_request(
        request_id=request.request_id,
        context=context,
        previously_selected_participant_ids=previously_selected_participant_ids,
        remaining_participants=participants,
    )
    if request != expected_request:
        raise GameLifecycleError("Historical Battle-shock sequencing request payload drifted.")
    return context


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
    completed_count = len(command_state.completed_battle_shock_test_request_ids)
    selected_unit_ids = command_state.battle_shock_candidate_order_unit_ids
    if len(selected_unit_ids) == completed_count + 1 and (
        command_state.battle_shock_in_flight_test_request is None
    ):
        raise GameLifecycleError(
            "Command Battle-shock selected candidate lacks its in-flight test authority."
        )
    remaining_candidates = tuple(
        candidate for candidate in candidates if candidate.unit_instance_id not in selected_unit_ids
    )
    expects_selection = (
        len(candidates) >= 2
        and completed_count == len(selected_unit_ids)
        and len(remaining_candidates) > 1
    )
    if not expects_selection:
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
        candidates=remaining_candidates,
        previously_selected_participant_ids=tuple(
            f"command-battle-shock-test:{unit_id}" for unit_id in selected_unit_ids
        ),
    )


def _validate_intervening_decisions_closed(
    *,
    event_records: tuple[EventRecord, ...],
    decision_records: tuple[DecisionRecord, ...],
    start_index: int,
    end_index: int,
) -> None:
    for request_index, event in enumerate(
        event_records[start_index:end_index],
        start=start_index,
    ):
        if event.event_type != "decision_requested":
            continue
        matches = tuple(
            record for record in decision_records if event.payload == record.request.to_payload()
        )
        if len(matches) != 1:
            raise GameLifecycleError(
                "Historical Battle-shock sequencing advanced with an unauthorised pending decision."
            )
        recorded_indices = tuple(
            index
            for index, recorded in enumerate(
                event_records[request_index + 1 : end_index],
                start=request_index + 1,
            )
            if recorded.event_type == "decision_recorded"
            and recorded.payload == matches[0].to_payload()
        )
        if len(recorded_indices) != 1:
            raise GameLifecycleError(
                "Historical Battle-shock sequencing advanced before a nested decision closed."
            )
        next_request_index = next(
            (
                index
                for index, later in enumerate(
                    event_records[recorded_indices[0] + 1 : end_index],
                    start=recorded_indices[0] + 1,
                )
                if later.event_type == "decision_requested"
            ),
            end_index,
        )
        if not any(
            mutation.event_type not in {"decision_requested", "decision_recorded"}
            for mutation in event_records[recorded_indices[0] + 1 : next_request_index]
        ):
            raise GameLifecycleError(
                "Historical Battle-shock sequencing advanced before a nested mutation closed."
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
