from __future__ import annotations

from typing import TYPE_CHECKING, cast

from warhammer40k_core.engine import command_phase_start_authority as authority
from warhammer40k_core.engine.command_phase_start_hooks import CommandPhaseStartHookRegistry
from warhammer40k_core.engine.command_phase_start_sequencing import command_start_timing_context
from warhammer40k_core.engine.decision_controller import DecisionController
from warhammer40k_core.engine.event_log import EventRecord
from warhammer40k_core.engine.phase import GameLifecycleError
from warhammer40k_core.engine.timing_batch_decisions import request_for_timing_batch
from warhammer40k_core.engine.timing_batch_runtime import (
    TIMING_BATCH_EVENT_TYPE,
    timing_batches_for_context,
)
from warhammer40k_core.engine.timing_batch_state import TimingBatch, TimingBatchPayload

if TYPE_CHECKING:
    from warhammer40k_core.engine.faction_content.bundle import RuntimeContentBundle
    from warhammer40k_core.engine.game_state import GameState


def validate_occurrence(
    *,
    state: GameState,
    decisions: DecisionController,
    registry: CommandPhaseStartHookRegistry,
    key: tuple[int, str],
    occurrence_events: tuple[tuple[int, EventRecord], ...],
    completed: bool,
    runtime_content_bundle: RuntimeContentBundle | None,
) -> None:
    by_type = {
        kind: tuple(row for row in occurrence_events if row[1].event_type == kind)
        for kind in authority.AUTHORITY_EVENT_TYPES
    }
    command_state = (
        state.command_step_state if key == authority.current_command_key(state) else None
    )
    boundary_required = completed or (
        command_state is not None and command_state.command_phase_start_boundary_resolved
    )
    synchronous_required = completed or (
        command_state is not None and command_state.command_phase_start_synchronous_hooks_resolved
    )
    discoveries = by_type[authority.COMMAND_START_DISCOVERED_EVENT]
    boundaries = by_type[authority.COMMAND_START_BOUNDARY_COMPLETED_EVENT]
    synchronous = by_type[authority.COMMAND_START_SYNCHRONOUS_COMPLETED_EVENT]
    passes = by_type[authority.COMMAND_START_EFFECT_PASS_COMPLETED_EVENT]
    if (
        len(boundaries) != int(boundary_required)
        or len(synchronous) != int(synchronous_required)
        or synchronous_required != boundary_required
        or len(passes) != int(boundary_required)
    ):
        raise GameLifecycleError("Command-start completion authority drifted.")
    if not discoveries:
        if (
            occurrence_events
            or boundary_required
            or (command_state is not None and decisions.queue.pending_requests)
        ):
            raise GameLifecycleError("Command-start progress lacks candidate discovery authority.")
        return
    if len(discoveries) != 1 or discoveries[0] != occurrence_events[0]:
        raise GameLifecycleError("Command-start discovery authority is duplicated or reordered.")
    discovery_index = discoveries[0][0]
    authority.validate_provider_dispositions(
        payload=authority.event_payload(discoveries[0][1]),
        registry=registry,
        events=decisions.event_log.records,
        authority_event_index=discovery_index,
        expected_bindings=(),
    )
    context = command_start_timing_context(state, battle_round=key[0], active_player_id=key[1])
    batches = timing_batches_for_context(decisions, context)
    snapshots = _snapshots(decisions, context.conflict_id)
    if snapshots and snapshots[0][0] <= discovery_index:
        raise GameLifecycleError("Command-start timing batch precedes candidate discovery.")
    for _index, snapshot in snapshots:
        for participant in (*snapshot.participants, *snapshot.deferred_participants):
            if not isinstance(participant.payload, dict):
                raise GameLifecycleError(
                    "Command-start timing participant lacks provider authority."
                )
            binding = authority.binding_from_payload(payload=participant.payload, registry=registry)
            if binding.candidate_handler is None:
                raise GameLifecycleError("Command-start timing provider lacks candidate authority.")

    requests = authority.validate_finite_requests(
        decisions=decisions,
        registry=registry,
        synchronous_index=discovery_index,
        rows=by_type[authority.COMMAND_START_FINITE_REQUESTED_EVENT],
    )
    results = authority.validate_finite_results(
        decisions=decisions,
        registry=registry,
        request_rows=requests,
        rows=by_type[authority.COMMAND_START_FINITE_RESULT_EVENT],
    )
    activation_kinds = {
        authority.COMMAND_START_FINITE_REQUESTED_EVENT,
        authority.COMMAND_START_FINITE_RESULT_EVENT,
        authority.COMMAND_START_EFFECT_PAUSED_EVENT,
        authority.COMMAND_START_RULE_COMPLETED_EVENT,
    }
    for index, event in occurrence_events:
        if event.event_type not in activation_kinds:
            continue
        batch = _batch_before(snapshots, index)
        if batch is None or batch.selected_participant_id is None:
            raise GameLifecycleError("Command-start provider output lacks a selected timing rule.")
        participant = next(
            item
            for item in batch.participants
            if item.participant_id == batch.selected_participant_id
        )
        payload = authority.event_payload(event)
        if not isinstance(participant.payload, dict) or any(
            payload[field] != participant.payload[field]
            for field in ("provider_hook_id", "provider_source_id")
        ):
            raise GameLifecycleError("Command-start provider output changed the selected source.")
        if event.event_type == authority.COMMAND_START_RULE_COMPLETED_EVENT:
            if payload["participant_id"] != participant.participant_id:
                raise GameLifecycleError("Command-start completed participant authority drifted.")
            authority.validate_provider_dispositions(
                payload=payload,
                registry=registry,
                events=decisions.event_log.records,
                authority_event_index=index,
                expected_bindings=(
                    authority.binding_from_payload(payload=payload, registry=registry),
                ),
            )

    unresolved_orders = _validate_orders(
        decisions=decisions,
        snapshots=snapshots,
        rows=by_type[authority.COMMAND_START_ORDER_REQUESTED_EVENT],
    )
    pauses = by_type[authority.COMMAND_START_EFFECT_PAUSED_EVENT]
    later_progress = tuple(
        index
        for index, event in occurrence_events
        if event.event_type != authority.COMMAND_START_EFFECT_PAUSED_EVENT
    )
    unresolved_effects = authority.validate_effect_pauses(
        decisions=decisions,
        registry=registry,
        synchronous_index=discovery_index,
        later_progress_indexes=later_progress,
        pauses=pauses,
    )
    unresolved = tuple(row for row in requests if row[2] is None)
    expected_pending = (
        *(row[1].request_id for row in unresolved),
        *unresolved_effects,
        *unresolved_orders,
    )
    if len(expected_pending) > 1:
        raise GameLifecycleError("Command-start rule continuations overlap.")
    for position, (request_index, _request, _record, _binding) in enumerate(requests):
        if position:
            previous_result = results.get(requests[position - 1][1].request_id)
            if previous_result is None or previous_result >= request_index:
                raise GameLifecycleError("Command-start finite providers overlap or reorder.")
    if boundary_required:
        if expected_pending or (
            batches
            and (not batches[-1].current_batch_complete or batches[-1].deferred_participants)
        ):
            raise GameLifecycleError("Command-start boundary retained an unfinished timing batch.")
        if not (synchronous[0][0] < passes[0][0] < boundaries[0][0]):
            raise GameLifecycleError("Command-start completion event order drifted.")
        if occurrence_events[-1] != boundaries[0]:
            raise GameLifecycleError("Command-start progress followed boundary completion.")
        if snapshots and snapshots[-1][0] >= synchronous[0][0]:
            raise GameLifecycleError("Command-start completion precedes its timing batch.")
        for index, event in (*synchronous, *passes, *boundaries):
            authority.validate_provider_dispositions(
                payload=authority.event_payload(event),
                registry=registry,
                events=decisions.event_log.records,
                authority_event_index=index,
                expected_bindings=(),
            )
        if authority.event_payload(passes[0][1])["effect_pass_index"] != 1:
            raise GameLifecycleError("Command-start effect completion count drifted.")
        _validate_boundary_queue_and_core_cp(
            state=state,
            decisions=decisions,
            key=key,
            completed=completed,
            boundary_index=boundaries[0][0],
        )
    elif command_state is not None:
        pending = tuple(request.request_id for request in decisions.queue.pending_requests)
        if expected_pending:
            if pending != expected_pending:
                raise GameLifecycleError("Pending Command-start provider inventory drifted.")
        elif pending:
            authority.validate_nested_finite_provider_pending_request(
                state=state,
                decisions=decisions,
                registry=registry,
                effect_pauses=pauses,
                request_rows=requests,
                result_index_by_request_id=results,
                runtime_content_bundle=runtime_content_bundle,
            )


def _snapshots(
    decisions: DecisionController, conflict_id: str
) -> tuple[tuple[int, TimingBatch], ...]:
    snapshots: list[tuple[int, TimingBatch]] = []
    for index, event in enumerate(decisions.event_log.records):
        if event.event_type != TIMING_BATCH_EVENT_TYPE:
            continue
        payload = event.payload
        if not isinstance(payload, dict) or not isinstance(payload.get("batch"), dict):
            raise GameLifecycleError("Command-start timing snapshot is malformed.")
        batch = TimingBatch.from_payload(cast(TimingBatchPayload, payload["batch"]))
        if batch.context.conflict_id == conflict_id:
            snapshots.append((index, batch))
    return tuple(snapshots)


def _batch_before(
    snapshots: tuple[tuple[int, TimingBatch], ...], event_index: int
) -> TimingBatch | None:
    preceding = tuple(batch for index, batch in snapshots if index < event_index)
    return preceding[-1] if preceding else None


def _validate_orders(
    *,
    decisions: DecisionController,
    snapshots: tuple[tuple[int, TimingBatch], ...],
    rows: tuple[tuple[int, EventRecord], ...],
) -> tuple[str, ...]:
    seen: set[str] = set()
    unresolved: list[str] = []
    for index, event in rows:
        payload = authority.event_payload(event)
        request_id = authority.payload_string(payload, "request_id")
        request = authority.request_by_id(decisions=decisions, request_id=request_id)
        batch = _batch_before(snapshots, index)
        if request_id in seen or request is None or batch is None:
            raise GameLifecycleError("Command-start ordering request lacks unique batch authority.")
        seen.add(request_id)
        if request != request_for_timing_batch(batch, request_id=request_id) or payload[
            "request_payload_hash"
        ] != authority.payload_hash(request.to_payload()):
            raise GameLifecycleError("Command-start ordering request source or tier drifted.")
        requested = authority.exact_event_index(
            decisions.event_log.records,
            event_type="decision_requested",
            payload=request.to_payload(),
        )
        if requested >= index:
            raise GameLifecycleError("Command-start ordering request event sequence drifted.")
        record = authority.decision_record_by_request_id(decisions.records, request_id=request_id)
        if record is None:
            unresolved.append(request_id)
        else:
            recorded = authority.exact_event_index(
                decisions.event_log.records,
                event_type="decision_recorded",
                payload=record.to_payload(),
            )
            if recorded <= index:
                raise GameLifecycleError("Command-start ordering result precedes its request.")
    return tuple(unresolved)


def _validate_boundary_queue_and_core_cp(
    *,
    state: GameState,
    decisions: DecisionController,
    key: tuple[int, str],
    completed: bool,
    boundary_index: int,
) -> None:
    command_state = (
        state.command_step_state if key == authority.current_command_key(state) else None
    )
    if completed or (command_state is not None and command_state.command_points_granted):
        anchor = authority.command_step_anchor_index(
            decisions.event_log.records, battle_round=key[0], active_player_id=key[1]
        )
        if (
            anchor < 3
            or boundary_index != anchor - 3
            or tuple(event.event_type for event in decisions.event_log.records[anchor - 3 : anchor])
            != (
                authority.COMMAND_START_BOUNDARY_COMPLETED_EVENT,
                "command_points_gained",
                "command_points_gained",
            )
        ):
            raise GameLifecycleError("Command-start Core CP event prefix drifted.")
    for request in decisions.queue.pending_requests:
        index = authority.exact_event_index(
            decisions.event_log.records,
            event_type="decision_requested",
            payload=request.to_payload(),
        )
        if index <= boundary_index:
            raise GameLifecycleError(
                "Command-start boundary retained an unrelated pending request."
            )
    if (
        command_state is not None
        and decisions.queue.pending_requests
        and not command_state.command_points_granted
    ):
        raise GameLifecycleError(
            "Command-start boundary cannot retain a pending request before Core CP."
        )
