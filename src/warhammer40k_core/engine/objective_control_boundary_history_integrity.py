from __future__ import annotations

from typing import TYPE_CHECKING

from warhammer40k_core.core.descriptor_hash import canonical_payload_sha256
from warhammer40k_core.engine.event_log import EventRecord, JsonValue
from warhammer40k_core.engine.objective_control import (
    ObjectiveControlRecord,
    ObjectiveControlTiming,
)
from warhammer40k_core.engine.phase import BattlePhase, GameLifecycleError

if TYPE_CHECKING:
    from warhammer40k_core.engine.game_state import GameState
    from warhammer40k_core.engine.objective_control_record_authority import (
        ObjectiveControlRecordAuthority,
    )


_OBJECTIVE_CONTROL_BOUNDARY_EVENT_TYPE = "end_boundary_objective_control_determined"
_OBJECTIVE_CONTROL_BOUNDARY_SOURCE_RULE_ID = (
    "gw-11e-rules-and-event-updates-2026-07-22:app-core-rules:14.02.01-control-first"
)
_LIFECYCLE_TIMING_SOURCE_RULE_ID = "core-rules-lifecycle-timing"


def validate_objective_control_boundary_history_integrity(
    *,
    state: GameState,
    event_records: tuple[EventRecord, ...],
    records: tuple[ObjectiveControlRecord, ...],
    authorities: tuple[ObjectiveControlRecordAuthority, ...],
) -> None:
    """Bind canonical lifecycle boundaries to exact stored OC history."""
    _validate_objective_control_boundary_event_inventory(
        event_records=event_records,
        records=records,
        authorities=authorities,
    )
    _validate_noninitial_phase_start_transition_history(
        state=state,
        event_records=event_records,
        records=records,
        authorities=authorities,
    )
    _validate_phase_end_objective_control_history(
        state=state,
        event_records=event_records,
        records=records,
        authorities=authorities,
    )


def _validate_noninitial_phase_start_transition_history(
    *,
    state: GameState,
    event_records: tuple[EventRecord, ...],
    records: tuple[ObjectiveControlRecord, ...],
    authorities: tuple[ObjectiveControlRecordAuthority, ...],
) -> None:
    """Require the current later phase start to retain its prior completion chain."""
    phase_values = tuple(phase.value for phase in state.battle_phase_sequence)
    current_phase = state.current_battle_phase
    active_player_id = state.active_player_id
    if current_phase is None or active_player_id is None:
        return
    phase_index = phase_values.index(current_phase.value)
    if phase_index == 0:
        return
    current_context = (state.battle_round, active_player_id, current_phase.value)
    start_indices: list[int] = []
    for event_index, event in enumerate(event_records):
        context = _canonical_phase_start_context_or_none(state=state, event=event)
        if context == current_context:
            start_indices.append(event_index)
    if len(start_indices) > 1:
        raise GameLifecycleError(
            "ObjectiveControlRecord current phase-start history duplicates a phase context."
        )
    if not start_indices and current_phase is BattlePhase.MOVEMENT:
        start_indices.extend(
            index
            for index, event in enumerate(event_records)
            if event.event_type == "movement_phase_entered"
            and event.payload
            == {
                "game_id": state.game_id,
                "battle_round": state.battle_round,
                "active_player_id": active_player_id,
                "phase": BattlePhase.MOVEMENT.value,
            }
        )
        if len(start_indices) > 1:
            raise GameLifecycleError(
                "ObjectiveControlRecord current Movement history duplicates phase entry."
            )
    if not start_indices:
        return

    start_index = start_indices[0]
    battle_round = state.battle_round
    prior_phase = phase_values[phase_index - 1]
    prior_context = (battle_round, active_player_id, prior_phase)
    prior_start_indices = tuple(
        index
        for index, event in enumerate(event_records)
        if _canonical_phase_start_context_or_none(state=state, event=event) == prior_context
    )
    if not prior_start_indices:
        return
    if len(prior_start_indices) != 1 or prior_start_indices[0] >= start_index:
        raise GameLifecycleError(
            "ObjectiveControlRecord phase-start history prior phase start is duplicated or "
            "out of order."
        )
    completed_matches = tuple(
        (index, event)
        for index, event in enumerate(event_records)
        if event.event_type == "battle_phase_completed"
        and _completed_phase_objective_control_context(state=state, event=event) == prior_context
    )
    if len(completed_matches) != 1 or completed_matches[0][0] >= start_index:
        raise GameLifecycleError(
            "ObjectiveControlRecord phase-start history lacks exactly one prior completed "
            "phase event."
        )
    completed_index = completed_matches[0][0]
    opened_matches = _canonical_phase_timing_event_matches(
        event_records=event_records,
        event_type="timing_window_opened",
        trigger_kind="end_phase",
        game_id=state.game_id,
        battle_round=battle_round,
        active_player_id=active_player_id,
        phase=prior_phase,
    )
    resolved_matches = _canonical_phase_timing_event_matches(
        event_records=event_records,
        event_type="timing_window_resolved",
        trigger_kind="end_phase",
        game_id=state.game_id,
        battle_round=battle_round,
        active_player_id=active_player_id,
        phase=prior_phase,
    )
    if (
        len(opened_matches) != 1
        or len(resolved_matches) != 1
        or event_records[opened_matches[0]].payload != event_records[resolved_matches[0]].payload
        or not opened_matches[0] < resolved_matches[0] < completed_index < start_index
    ):
        raise GameLifecycleError(
            "ObjectiveControlRecord phase-start history lacks one ordered prior phase-end "
            "timing chain."
        )
    record = _require_objective_control_record_authority_and_event(
        history_label="phase-start history",
        game_id=state.game_id,
        battle_round=battle_round,
        active_player_id=active_player_id,
        phase=prior_phase,
        timing=ObjectiveControlTiming.PHASE_END,
        event_records=event_records,
        records=records,
        authorities=authorities,
    )
    boundary_index = _objective_control_boundary_event_index(
        event_records=event_records,
        record=record,
    )
    if boundary_index >= opened_matches[0]:
        raise GameLifecycleError(
            "ObjectiveControlRecord phase-start history boundary event is out of order."
        )


def _canonical_phase_start_context_or_none(
    *,
    state: GameState,
    event: EventRecord,
) -> tuple[int, str, str] | None:
    if event.event_type != "timing_window_opened" or not isinstance(event.payload, dict):
        return None
    timing_window = event.payload.get("timing_window")
    if not isinstance(timing_window, dict):
        return None
    descriptor = timing_window.get("descriptor")
    if (
        not isinstance(descriptor, dict)
        or descriptor.get("trigger_kind") != "start_phase"
        or descriptor.get("source_rule_id") != _LIFECYCLE_TIMING_SOURCE_RULE_ID
    ):
        return None
    game_id = timing_window.get("game_id")
    battle_round = timing_window.get("battle_round")
    active_player_id = timing_window.get("active_player_id")
    phase = timing_window.get("phase")
    phase_values = tuple(value.value for value in state.battle_phase_sequence)
    if (
        type(game_id) is not str
        or game_id != state.game_id
        or type(battle_round) is not int
        or battle_round < 1
        or type(active_player_id) is not str
        or active_player_id not in state.turn_order
        or type(phase) is not str
        or phase not in phase_values
        or descriptor.get("phase") != phase
        or descriptor.get("source_step") != phase
    ):
        raise GameLifecycleError(
            "ObjectiveControlRecord phase-start timing history context is invalid."
        )
    return battle_round, active_player_id, phase


def _canonical_phase_timing_event_matches(
    *,
    event_records: tuple[EventRecord, ...],
    event_type: str,
    trigger_kind: str,
    game_id: str,
    battle_round: int,
    active_player_id: str,
    phase: str,
) -> tuple[int, ...]:
    matches: list[int] = []
    for index, event in enumerate(event_records):
        if event.event_type != event_type or not isinstance(event.payload, dict):
            continue
        timing_window = event.payload.get("timing_window")
        if not isinstance(timing_window, dict):
            continue
        descriptor = timing_window.get("descriptor")
        if (
            not isinstance(descriptor, dict)
            or descriptor.get("trigger_kind") != trigger_kind
            or descriptor.get("source_rule_id") != _LIFECYCLE_TIMING_SOURCE_RULE_ID
            or descriptor.get("phase") != phase
            or descriptor.get("source_step") != phase
        ):
            continue
        if (
            timing_window.get("game_id") == game_id
            and timing_window.get("battle_round") == battle_round
            and timing_window.get("active_player_id") == active_player_id
            and timing_window.get("phase") == phase
        ):
            matches.append(index)
    return tuple(matches)


def _validate_objective_control_boundary_event_inventory(
    *,
    event_records: tuple[EventRecord, ...],
    records: tuple[ObjectiveControlRecord, ...],
    authorities: tuple[ObjectiveControlRecordAuthority, ...],
) -> None:
    """Require every canonical boundary event to bind one stored record and authority."""
    canonical_events = tuple(
        event
        for event in event_records
        if event.event_type == _OBJECTIVE_CONTROL_BOUNDARY_EVENT_TYPE
    )
    for event in canonical_events:
        matching_records = tuple(
            record
            for record in records
            if event.payload
            == {
                "game_id": record.game_id,
                "battle_round": record.battle_round,
                "phase": record.phase,
                "record_ids": [record.record_id],
                "source_rule_id": _OBJECTIVE_CONTROL_BOUNDARY_SOURCE_RULE_ID,
            }
        )
        if len(matching_records) != 1:
            raise GameLifecycleError(
                "ObjectiveControlRecord canonical boundary event does not identify exactly "
                "one stored record."
            )
        record = matching_records[0]
        matching_authorities = tuple(
            authority
            for authority in authorities
            if authority.objective_control_record_id == record.record_id
            and authority.objective_control_record_hash == _objective_control_record_hash(record)
        )
        if len(matching_authorities) != 1:
            raise GameLifecycleError(
                "ObjectiveControlRecord canonical boundary event does not identify exactly "
                "one hash-bound authority."
            )


def _validate_phase_end_objective_control_history(
    *,
    state: GameState,
    event_records: tuple[EventRecord, ...],
    records: tuple[ObjectiveControlRecord, ...],
    authorities: tuple[ObjectiveControlRecordAuthority, ...],
) -> None:
    """Bind canonical completed phases and phase-end windows to OC checkpoints."""
    completed_contexts: set[tuple[int, str, str]] = set()
    completed_turn_contexts: set[tuple[int, str, str]] = set()
    final_phase = state.battle_phase_sequence[-1].value
    for event in event_records:
        if event.event_type != "battle_phase_completed":
            continue
        context = _completed_phase_objective_control_context(state=state, event=event)
        if context in completed_contexts:
            raise GameLifecycleError(
                "ObjectiveControlRecord completed phase history duplicates a phase context."
            )
        completed_contexts.add(context)
        battle_round, active_player_id, phase = context
        _require_objective_control_record_authority_and_event(
            history_label="completed phase history",
            game_id=state.game_id,
            battle_round=battle_round,
            active_player_id=active_player_id,
            phase=phase,
            timing=ObjectiveControlTiming.PHASE_END,
            event_records=event_records,
            records=records,
            authorities=authorities,
        )
        if phase == final_phase:
            completed_turn_contexts.add(context)

    _validate_completed_turn_end_objective_control_history(
        state=state,
        completed_turn_contexts=completed_turn_contexts,
        event_records=event_records,
        records=records,
        authorities=authorities,
    )

    matched_record_ids: set[str] = set()
    for event in event_records:
        if event.event_type != "timing_window_opened" or not isinstance(event.payload, dict):
            continue
        timing_window = event.payload.get("timing_window")
        if not isinstance(timing_window, dict):
            continue
        descriptor = timing_window.get("descriptor")
        if (
            not isinstance(descriptor, dict)
            or descriptor.get("trigger_kind") != "end_phase"
            or descriptor.get("source_rule_id") != _LIFECYCLE_TIMING_SOURCE_RULE_ID
        ):
            continue
        timing_game_id = timing_window.get("game_id")
        timing_battle_round = timing_window.get("battle_round")
        timing_active_player_id = timing_window.get("active_player_id")
        timing_phase = timing_window.get("phase")
        if (
            type(timing_game_id) is not str
            or type(timing_battle_round) is not int
            or type(timing_active_player_id) is not str
            or type(timing_phase) is not str
        ):
            raise GameLifecycleError(
                "ObjectiveControlRecord phase-end timing history context is invalid."
            )
        record = _require_objective_control_record_authority_and_event(
            history_label="phase-end timing history",
            game_id=timing_game_id,
            battle_round=timing_battle_round,
            active_player_id=timing_active_player_id,
            phase=timing_phase,
            timing=ObjectiveControlTiming.PHASE_END,
            event_records=event_records,
            records=records,
            authorities=authorities,
        )
        if record.record_id in matched_record_ids:
            raise GameLifecycleError(
                "ObjectiveControlRecord phase-end timing history reuses a phase-end record."
            )
        matched_record_ids.add(record.record_id)


def _validate_completed_turn_end_objective_control_history(
    *,
    state: GameState,
    completed_turn_contexts: set[tuple[int, str, str]],
    event_records: tuple[EventRecord, ...],
    records: tuple[ObjectiveControlRecord, ...],
    authorities: tuple[ObjectiveControlRecordAuthority, ...],
) -> None:
    final_phase = state.battle_phase_sequence[-1].value
    timing_contexts: set[tuple[int, str, str]] = set()
    for event in event_records:
        if event.event_type != "timing_window_opened" or not isinstance(event.payload, dict):
            continue
        timing_window = event.payload.get("timing_window")
        if not isinstance(timing_window, dict):
            continue
        descriptor = timing_window.get("descriptor")
        if (
            not isinstance(descriptor, dict)
            or descriptor.get("trigger_kind") != "end_turn"
            or descriptor.get("source_rule_id") != _LIFECYCLE_TIMING_SOURCE_RULE_ID
        ):
            continue
        game_id = timing_window.get("game_id")
        battle_round = timing_window.get("battle_round")
        active_player_id = timing_window.get("active_player_id")
        if (
            type(game_id) is not str
            or game_id != state.game_id
            or type(battle_round) is not int
            or battle_round < 1
            or type(active_player_id) is not str
            or active_player_id not in state.turn_order
            or timing_window.get("phase") is not None
        ):
            raise GameLifecycleError(
                "ObjectiveControlRecord turn-end timing history context is invalid."
            )
        context = (battle_round, active_player_id, final_phase)
        if context in timing_contexts:
            raise GameLifecycleError(
                "ObjectiveControlRecord turn-end timing history duplicates a turn context."
            )
        timing_contexts.add(context)

    for battle_round, active_player_id, phase in completed_turn_contexts:
        if (battle_round, active_player_id, phase) not in timing_contexts:
            raise GameLifecycleError(
                "ObjectiveControlRecord completed turn history lacks exactly one canonical "
                "turn-end timing window."
            )
        _require_objective_control_record_authority_and_event(
            history_label="completed turn history",
            game_id=state.game_id,
            battle_round=battle_round,
            active_player_id=active_player_id,
            phase=phase,
            timing=ObjectiveControlTiming.TURN_END,
            event_records=event_records,
            records=records,
            authorities=authorities,
        )


def _completed_phase_objective_control_context(
    *,
    state: GameState,
    event: EventRecord,
) -> tuple[int, str, str]:
    payload = event.payload
    if not isinstance(payload, dict) or payload.get("game_id") != state.game_id:
        raise GameLifecycleError(
            "ObjectiveControlRecord completed phase history context is invalid."
        )
    completed_phase = payload.get("completed_phase")
    post_battle_round = payload.get("battle_round")
    post_active_player_id = payload.get("active_player_id")
    phase_values = tuple(phase.value for phase in state.battle_phase_sequence)
    if (
        type(completed_phase) is not str
        or completed_phase not in phase_values
        or type(post_battle_round) is not int
        or post_battle_round < 1
    ):
        raise GameLifecycleError(
            "ObjectiveControlRecord completed phase history context is invalid."
        )
    if completed_phase != phase_values[-1]:
        if type(post_active_player_id) is not str:
            raise GameLifecycleError(
                "ObjectiveControlRecord completed phase history player context is invalid."
            )
        return post_battle_round, post_active_player_id, completed_phase
    if post_active_player_id is None:
        return post_battle_round, state.turn_order[-1], completed_phase
    if type(post_active_player_id) is not str or post_active_player_id not in state.turn_order:
        raise GameLifecycleError(
            "ObjectiveControlRecord completed phase history player context is invalid."
        )
    post_player_index = state.turn_order.index(post_active_player_id)
    if post_player_index > 0:
        return (
            post_battle_round,
            state.turn_order[post_player_index - 1],
            completed_phase,
        )
    if post_battle_round == 1:
        raise GameLifecycleError(
            "ObjectiveControlRecord completed phase history round context is invalid."
        )
    return post_battle_round - 1, state.turn_order[-1], completed_phase


def _require_objective_control_record_authority_and_event(
    *,
    history_label: str,
    game_id: str,
    battle_round: int,
    active_player_id: str,
    phase: str,
    timing: ObjectiveControlTiming,
    event_records: tuple[EventRecord, ...],
    records: tuple[ObjectiveControlRecord, ...],
    authorities: tuple[ObjectiveControlRecordAuthority, ...],
) -> ObjectiveControlRecord:
    matching_records = tuple(
        record
        for record in records
        if record.game_id == game_id
        and record.battle_round == battle_round
        and record.active_player_id == active_player_id
        and record.phase == phase
        and record.timing is timing
    )
    if len(matching_records) != 1:
        timing_label = timing.value.replace("_", "-")
        raise GameLifecycleError(
            f"ObjectiveControlRecord {history_label} lacks exactly one {timing_label} record."
        )
    record = matching_records[0]
    matching_authorities = tuple(
        authority
        for authority in authorities
        if authority.objective_control_record_id == record.record_id
        and authority.objective_control_record_hash == _objective_control_record_hash(record)
    )
    if len(matching_authorities) != 1:
        raise GameLifecycleError(
            f"ObjectiveControlRecord {history_label} lacks exactly one hash-bound authority."
        )
    _objective_control_boundary_event_index(
        event_records=event_records,
        record=record,
    )
    return record


def _objective_control_record_hash(record: ObjectiveControlRecord) -> str:
    return canonical_payload_sha256(record.to_payload())


def _objective_control_boundary_event_index(
    *,
    event_records: tuple[EventRecord, ...],
    record: ObjectiveControlRecord,
) -> int:
    expected_payload: dict[str, JsonValue] = {
        "game_id": record.game_id,
        "battle_round": record.battle_round,
        "phase": record.phase,
        "record_ids": [record.record_id],
        "source_rule_id": _OBJECTIVE_CONTROL_BOUNDARY_SOURCE_RULE_ID,
    }
    matches = tuple(
        index
        for index, event in enumerate(event_records)
        if event.event_type == _OBJECTIVE_CONTROL_BOUNDARY_EVENT_TYPE
        and event.payload == expected_payload
    )
    if len(matches) != 1:
        raise GameLifecycleError("ObjectiveControlRecord authority lacks an exact boundary event.")
    return matches[0]


__all__ = ("validate_objective_control_boundary_history_integrity",)
