from __future__ import annotations

import hashlib
from typing import TYPE_CHECKING

from warhammer40k_core.engine.command_core_cp_history import (
    expected_core_command_occurrence_keys,
    expected_restored_core_command_occurrence_keys,
)
from warhammer40k_core.engine.command_phase_start_hooks import (
    COMMAND_PHASE_START_BATTLE_SHOCK_SOURCE_KIND,
    SELECT_FACTION_RULE_COMMAND_PHASE_START_OPTION_DECISION_TYPE,
    CommandPhaseStartContext,
    CommandPhaseStartEffectContext,
    CommandPhaseStartHookBinding,
    CommandPhaseStartHookRegistry,
    CommandPhaseStartNestedPendingAuthorityContext,
    CommandPhaseStartProviderDisposition,
    CommandPhaseStartRequestContext,
    CommandPhaseStartResultContext,
)
from warhammer40k_core.engine.command_points import CommandStepState
from warhammer40k_core.engine.decision_controller import DecisionController
from warhammer40k_core.engine.decision_record import DecisionRecord
from warhammer40k_core.engine.decision_request import DecisionRequest
from warhammer40k_core.engine.event_log import (
    EventRecord,
    JsonValue,
    canonical_json,
    validate_json_value,
)
from warhammer40k_core.engine.phase import (
    BattlePhase,
    GameLifecycleError,
    GameLifecycleStage,
    LifecycleStatus,
    LifecycleStatusKind,
)
from warhammer40k_core.engine.runtime_modifiers import RuntimeModifierRegistry

if TYPE_CHECKING:
    from warhammer40k_core.engine.faction_content.bundle import RuntimeContentBundle
    from warhammer40k_core.engine.game_state import GameState


COMMAND_START_SYNCHRONOUS_COMPLETED_EVENT = "command_phase_start_synchronous_hooks_completed"
COMMAND_START_EFFECT_PAUSED_EVENT = "command_phase_start_effect_hook_paused"
COMMAND_START_EFFECT_PASS_COMPLETED_EVENT = "command_phase_start_effect_pass_completed"
COMMAND_START_FINITE_REQUESTED_EVENT = "command_phase_start_faction_rule_requested"
COMMAND_START_FINITE_RESULT_EVENT = "command_phase_start_finite_provider_result_applied"
COMMAND_START_BOUNDARY_COMPLETED_EVENT = "command_phase_start_boundary_completed"

_AUTHORITY_EVENT_TYPES = frozenset(
    {
        COMMAND_START_SYNCHRONOUS_COMPLETED_EVENT,
        COMMAND_START_EFFECT_PAUSED_EVENT,
        COMMAND_START_EFFECT_PASS_COMPLETED_EVENT,
        COMMAND_START_FINITE_REQUESTED_EVENT,
        COMMAND_START_FINITE_RESULT_EVENT,
        COMMAND_START_BOUNDARY_COMPLETED_EVENT,
    }
)

_COMMON_PAYLOAD_KEYS = frozenset(
    {
        "game_id",
        "battle_round",
        "active_player_id",
        "phase",
        "provider_registry_fingerprint",
    }
)
_COMPLETION_PAYLOAD_KEYS = _COMMON_PAYLOAD_KEYS | {
    "provider_binding_inventory",
    "provider_dispositions",
}
_EFFECT_PAUSE_PAYLOAD_KEYS = _COMMON_PAYLOAD_KEYS | {
    "provider_hook_id",
    "provider_source_id",
    "status_kind",
    "pending_request_id",
    "pending_request_payload_hash",
    "provider_dispositions",
}
_EFFECT_PASS_PAYLOAD_KEYS = _COMMON_PAYLOAD_KEYS | {
    "effect_pass_index",
    "provider_dispositions",
}
_FINITE_REQUEST_PAYLOAD_KEYS = _COMMON_PAYLOAD_KEYS | {
    "decision_type",
    "request_id",
    "request_payload_hash",
    "provider_hook_id",
    "provider_source_id",
}
_FINITE_RESULT_PAYLOAD_KEYS = _FINITE_REQUEST_PAYLOAD_KEYS | {
    "result_id",
    "result_payload_hash",
    "provider_dispositions",
}

_PROVIDER_DISPOSITION_KEYS = frozenset(
    {
        "provider_hook_id",
        "provider_source_id",
        "state_changed",
        "emitted_event_ids",
        "emitted_events_hash",
    }
)
_PAYLOAD_KEYS_BY_EVENT_TYPE = {
    COMMAND_START_SYNCHRONOUS_COMPLETED_EVENT: _COMPLETION_PAYLOAD_KEYS,
    COMMAND_START_EFFECT_PAUSED_EVENT: _EFFECT_PAUSE_PAYLOAD_KEYS,
    COMMAND_START_EFFECT_PASS_COMPLETED_EVENT: _EFFECT_PASS_PAYLOAD_KEYS,
    COMMAND_START_FINITE_REQUESTED_EVENT: _FINITE_REQUEST_PAYLOAD_KEYS,
    COMMAND_START_FINITE_RESULT_EVENT: _FINITE_RESULT_PAYLOAD_KEYS,
    COMMAND_START_BOUNDARY_COMPLETED_EVENT: _COMPLETION_PAYLOAD_KEYS,
}


def resolve_command_phase_start_boundary(
    *,
    state: GameState,
    decisions: DecisionController,
    command_phase_start_hooks: CommandPhaseStartHookRegistry,
    runtime_modifier_registry: RuntimeModifierRegistry,
) -> LifecycleStatus | None:
    """Resolve the pre-Core-CP boundary while retaining exact restore evidence."""
    _validate_runtime_inputs(
        state=state,
        decisions=decisions,
        registry=command_phase_start_hooks,
        runtime_modifier_registry=runtime_modifier_registry,
    )
    command_state = state.command_step_state
    if command_state is None:
        raise GameLifecycleError("Command-start boundary requires CommandStepState.")
    if command_state.command_points_granted:
        raise GameLifecycleError("Command-start boundary cannot run after Core CP is granted.")
    _require_empty_pending_queue(
        decisions=decisions,
        context="Command-start boundary cannot run with a pending decision",
    )
    active_player_id = _active_player_id(state)
    if not command_state.command_phase_start_synchronous_hooks_resolved:
        synchronous_dispositions = command_phase_start_hooks.resolve_with_provider_dispositions(
            CommandPhaseStartContext(
                state=state,
                decisions=decisions,
                active_player_id=active_player_id,
            )
        )
        _require_empty_pending_queue(
            decisions=decisions,
            context="Command-start synchronous hooks cannot enqueue decisions",
        )
        _append_completion_event(
            state=state,
            decisions=decisions,
            registry=command_phase_start_hooks,
            event_type=COMMAND_START_SYNCHRONOUS_COMPLETED_EVENT,
            dispositions=synchronous_dispositions,
        )
        state.replace_command_step_state(
            _require_command_state(state).with_command_phase_start_synchronous_hooks_resolved()
        )
        command_state = _require_command_state(state)
    if command_state.command_phase_start_boundary_resolved:
        return None

    (
        effect_status,
        effect_binding,
        effect_dispositions,
    ) = command_phase_start_hooks.resolve_effects_with_provider_dispositions(
        CommandPhaseStartEffectContext(
            state=state,
            decisions=decisions,
            active_player_id=active_player_id,
            runtime_modifier_registry=runtime_modifier_registry,
        )
    )
    if effect_status is not None:
        if effect_binding is None:
            raise GameLifecycleError("Command-start effect pause lacks a provider binding.")
        _record_effect_pause(
            state=state,
            decisions=decisions,
            registry=command_phase_start_hooks,
            binding=effect_binding,
            status=effect_status,
            dispositions=effect_dispositions,
        )
        return effect_status

    _require_empty_pending_queue(
        decisions=decisions,
        context="Command-start effect hooks must return their pending decision status",
    )

    _record_effect_pass_completion(
        state=state,
        decisions=decisions,
        registry=command_phase_start_hooks,
        dispositions=effect_dispositions,
    )
    emission = command_phase_start_hooks.next_request_with_provider(
        CommandPhaseStartRequestContext(
            state=state,
            decisions=decisions,
            active_player_id=active_player_id,
        )
    )
    if emission is not None:
        request, binding = emission
        decisions.request_decision(request)
        if decisions.queue.pending_requests != (request,):
            raise GameLifecycleError(
                "Command-start finite provider did not enqueue exactly one request."
            )
        decisions.event_log.append(
            COMMAND_START_FINITE_REQUESTED_EVENT,
            {
                **_authority_common_payload(state=state, registry=command_phase_start_hooks),
                "decision_type": request.decision_type,
                "request_id": request.request_id,
                "request_payload_hash": _payload_hash(request.to_payload()),
                "provider_hook_id": binding.hook_id,
                "provider_source_id": binding.source_id,
            },
        )
        return LifecycleStatus.waiting_for_decision(
            stage=GameLifecycleStage.BATTLE,
            decision_request=request,
            payload={
                "phase": BattlePhase.COMMAND.value,
                "active_player_id": active_player_id,
                "phase_body_status": "command_phase_start_faction_rule_pending",
            },
        )

    _append_completion_event(
        state=state,
        decisions=decisions,
        registry=command_phase_start_hooks,
        event_type=COMMAND_START_BOUNDARY_COMPLETED_EVENT,
        dispositions=(),
    )
    state.replace_command_step_state(
        _require_command_state(state).with_command_phase_start_boundary_resolved()
    )
    return None


def record_command_phase_start_finite_result(
    *,
    context: CommandPhaseStartResultContext,
    registry: CommandPhaseStartHookRegistry,
    disposition: CommandPhaseStartProviderDisposition,
) -> None:
    if type(context) is not CommandPhaseStartResultContext:
        raise GameLifecycleError("Command-start result authority requires result context.")
    if type(registry) is not CommandPhaseStartHookRegistry:
        raise GameLifecycleError("Command-start result authority requires a registry.")
    if type(disposition) is not CommandPhaseStartProviderDisposition:
        raise GameLifecycleError("Command-start result authority requires a disposition.")
    binding = disposition.binding
    _require_registry_binding(registry=registry, binding=binding, requires_result=True)
    context.decisions.event_log.append(
        COMMAND_START_FINITE_RESULT_EVENT,
        {
            **_authority_common_payload(state=context.state, registry=registry),
            "decision_type": context.request.decision_type,
            "request_id": context.request.request_id,
            "request_payload_hash": _payload_hash(context.request.to_payload()),
            "result_id": context.result.result_id,
            "result_payload_hash": _payload_hash(context.result.to_payload()),
            "provider_hook_id": binding.hook_id,
            "provider_source_id": binding.source_id,
            "provider_dispositions": _provider_dispositions_payload((disposition,)),
        },
    )


def validate_command_phase_start_restore_authority(
    *,
    state: GameState,
    decisions: DecisionController,
    registry: CommandPhaseStartHookRegistry,
    runtime_content_bundle: RuntimeContentBundle | None = None,
) -> None:
    """Authenticate Command-start progress against the loaded provider registry."""
    if type(decisions) is not DecisionController:
        raise GameLifecycleError("Command-start restore authority requires DecisionController.")
    if type(registry) is not CommandPhaseStartHookRegistry:
        raise GameLifecycleError("Command-start restore authority requires a hook registry.")
    completed_keys = expected_restored_core_command_occurrence_keys(
        state,
        event_records=decisions.event_log.records,
    )
    if len(set(completed_keys)) != len(completed_keys):
        raise GameLifecycleError("Command-start completed occurrence authority drifted.")
    current_key = _current_incomplete_command_key(state)
    allowed_keys = set(completed_keys)
    if current_key is not None:
        allowed_keys.add(current_key)

    events_by_key: dict[tuple[int, str], list[tuple[int, EventRecord]]] = {}
    for event_index, event in enumerate(decisions.event_log.records):
        if event.event_type not in _AUTHORITY_EVENT_TYPES:
            continue
        payload = _event_payload(event)
        _validate_exact_payload_shape(event_type=event.event_type, payload=payload)
        key = _validate_authority_common_payload(
            payload=payload,
            state=state,
            registry=registry,
        )
        if key not in allowed_keys:
            raise GameLifecycleError("Command-start authority contains an unexpected occurrence.")
        events_by_key.setdefault(key, []).append((event_index, event))

    for key in completed_keys:
        _validate_occurrence(
            state=state,
            decisions=decisions,
            registry=registry,
            key=key,
            occurrence_events=tuple(events_by_key.get(key, ())),
            completed=True,
            runtime_content_bundle=runtime_content_bundle,
        )
    if current_key is not None:
        _validate_occurrence(
            state=state,
            decisions=decisions,
            registry=registry,
            key=current_key,
            occurrence_events=tuple(events_by_key.get(current_key, ())),
            completed=False,
            runtime_content_bundle=runtime_content_bundle,
        )


def _validate_occurrence(
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
        event_type: tuple(
            (event_index, event)
            for event_index, event in occurrence_events
            if event.event_type == event_type
        )
        for event_type in _AUTHORITY_EVENT_TYPES
    }
    command_state = state.command_step_state if key == _current_command_key(state) else None
    synchronous_required = completed or (
        command_state is not None and command_state.command_phase_start_synchronous_hooks_resolved
    )
    boundary_required = completed or (
        command_state is not None and command_state.command_phase_start_boundary_resolved
    )
    synchronous = by_type[COMMAND_START_SYNCHRONOUS_COMPLETED_EVENT]
    boundaries = by_type[COMMAND_START_BOUNDARY_COMPLETED_EVENT]
    if len(synchronous) != int(synchronous_required):
        raise GameLifecycleError("Command-start synchronous completion authority drifted.")
    if len(boundaries) != int(boundary_required):
        raise GameLifecycleError("Command-start boundary completion authority drifted.")
    if not synchronous_required:
        if occurrence_events:
            raise GameLifecycleError("Command-start authority exists before synchronous progress.")
        if command_state is not None and decisions.queue.pending_requests:
            raise GameLifecycleError(
                "Command-start cannot retain a pending request before synchronous progress."
            )
        return

    synchronous_index = synchronous[0][0]
    _validate_provider_dispositions(
        payload=_event_payload(synchronous[0][1]),
        registry=registry,
        events=decisions.event_log.records,
        authority_event_index=synchronous_index,
        expected_bindings=tuple(
            binding for binding in registry.all_bindings() if binding.handler is not None
        ),
    )
    effect_passes = by_type[COMMAND_START_EFFECT_PASS_COMPLETED_EVENT]
    for expected_pass_index, (event_index, event) in enumerate(effect_passes, start=1):
        if event_index <= synchronous_index:
            raise GameLifecycleError("Command-start effect pass precedes synchronous completion.")
        payload = _event_payload(event)
        if payload.get("effect_pass_index") != expected_pass_index:
            raise GameLifecycleError("Command-start effect pass sequence drifted.")
        _validate_provider_dispositions(
            payload=payload,
            registry=registry,
            events=decisions.event_log.records,
            authority_event_index=event_index,
            expected_bindings=tuple(
                binding for binding in registry.all_bindings() if binding.effect_handler is not None
            ),
        )
    request_rows = _validate_finite_requests(
        decisions=decisions,
        registry=registry,
        synchronous_index=synchronous_index,
        rows=by_type[COMMAND_START_FINITE_REQUESTED_EVENT],
    )
    result_index_by_request_id = _validate_finite_results(
        decisions=decisions,
        registry=registry,
        request_rows=request_rows,
        rows=by_type[COMMAND_START_FINITE_RESULT_EVENT],
    )
    boundary_index = None if not boundaries else boundaries[0][0]
    unresolved_effect_request_ids = _validate_effect_pauses(
        decisions=decisions,
        registry=registry,
        synchronous_index=synchronous_index,
        later_progress_indexes=tuple(
            sorted(
                (
                    *(event_index for event_index, _event in effect_passes),
                    *(
                        event_index
                        for event_index, _event in by_type[COMMAND_START_FINITE_REQUESTED_EVENT]
                    ),
                    *(
                        event_index
                        for event_index, _event in by_type[COMMAND_START_FINITE_RESULT_EVENT]
                    ),
                    *((boundary_index,) if boundary_index is not None else ()),
                )
            )
        ),
        pauses=by_type[COMMAND_START_EFFECT_PAUSED_EVENT],
    )
    expected_effect_pass_count = len(request_rows) + int(boundary_required)
    if len(effect_passes) != expected_effect_pass_count:
        raise GameLifecycleError("Command-start effect-pass/finite-provider chain drifted.")
    unresolved_request_indexes = tuple(
        index for index, row in enumerate(request_rows) if row[2] is None
    )
    if unresolved_request_indexes not in ((), (len(request_rows) - 1,)):
        raise GameLifecycleError("Command-start finite provider progress overlaps.")
    for request_position, (request_index, request, record, _binding) in enumerate(request_rows):
        pass_index = effect_passes[request_position][0]
        if pass_index >= request_index:
            raise GameLifecycleError("Command-start finite request precedes its effect pass.")
        if request_position > 0:
            previous_request = request_rows[request_position - 1][1]
            previous_result_index = result_index_by_request_id.get(previous_request.request_id)
            if previous_result_index is None or previous_result_index >= pass_index:
                raise GameLifecycleError("Command-start finite providers overlap or reorder.")
        if record is not None:
            result_index = result_index_by_request_id[request.request_id]
            next_pass_position = request_position + 1
            if (
                next_pass_position < len(effect_passes)
                and result_index >= effect_passes[next_pass_position][0]
            ):
                raise GameLifecycleError(
                    "Command-start finite result does not precede the next effect pass."
                )

    if boundary_required:
        if not effect_passes:
            raise GameLifecycleError("Command-start boundary lacks an effect completion pass.")
        if boundary_index is None:
            raise GameLifecycleError("Command-start boundary authority is absent.")
        _validate_provider_dispositions(
            payload=_event_payload(boundaries[0][1]),
            registry=registry,
            events=decisions.event_log.records,
            authority_event_index=boundary_index,
            expected_bindings=(),
        )
        if effect_passes[-1][0] >= boundary_index:
            raise GameLifecycleError("Command-start boundary precedes its final effect pass.")
        if request_rows and request_rows[-1][0] >= boundary_index:
            raise GameLifecycleError("Command-start boundary precedes finite provider progress.")
        unresolved = tuple(row for row in request_rows if row[2] is None)
        if unresolved:
            raise GameLifecycleError("Completed Command-start boundary has a pending provider.")
        if completed or (command_state is not None and command_state.command_points_granted):
            anchor_index = _command_step_anchor_index(
                decisions.event_log.records,
                battle_round=key[0],
                active_player_id=key[1],
            )
            if anchor_index < 3 or tuple(
                event.event_type
                for event in decisions.event_log.records[anchor_index - 3 : anchor_index]
            ) != (
                COMMAND_START_BOUNDARY_COMPLETED_EVENT,
                "command_points_gained",
                "command_points_gained",
            ):
                raise GameLifecycleError("Command-start Core CP event prefix drifted.")
            if boundary_index != anchor_index - 3:
                raise GameLifecycleError(
                    "Command-start boundary is not adjacent to both Core CP gains."
                )
        for pending_request in decisions.queue.pending_requests:
            requested_index = _exact_event_index(
                decisions.event_log.records,
                event_type="decision_requested",
                payload=pending_request.to_payload(),
            )
            if requested_index <= boundary_index:
                raise GameLifecycleError(
                    "Command-start boundary retained an unrelated pending request."
                )
    elif boundaries:
        raise GameLifecycleError("Incomplete Command-start occurrence has boundary authority.")

    if command_state is not None:
        unresolved = tuple(row for row in request_rows if row[2] is None)
        expected_pending_request_ids = (
            *(row[1].request_id for row in unresolved),
            *unresolved_effect_request_ids,
        )
        pending_request_ids = tuple(
            request.request_id for request in decisions.queue.pending_requests
        )
        if expected_pending_request_ids:
            if pending_request_ids != expected_pending_request_ids:
                raise GameLifecycleError("Pending Command-start provider inventory drifted.")
        elif not boundary_required and decisions.queue.pending_requests:
            _validate_nested_finite_provider_pending_request(
                state=state,
                decisions=decisions,
                registry=registry,
                effect_pauses=by_type[COMMAND_START_EFFECT_PAUSED_EVENT],
                request_rows=request_rows,
                result_index_by_request_id=result_index_by_request_id,
                runtime_content_bundle=runtime_content_bundle,
            )
        elif boundary_required and decisions.queue.pending_requests:
            if boundary_index is None:
                raise GameLifecycleError("Command-start completed queue lacks a boundary.")
            if not command_state.command_points_granted:
                raise GameLifecycleError(
                    "Command-start boundary cannot retain a pending request before Core CP."
                )


def _validate_effect_pauses(
    *,
    decisions: DecisionController,
    registry: CommandPhaseStartHookRegistry,
    synchronous_index: int,
    later_progress_indexes: tuple[int, ...],
    pauses: tuple[tuple[int, EventRecord], ...],
) -> tuple[str, ...]:
    seen_request_ids: set[str] = set()
    unresolved_request_ids: list[str] = []
    for event_index, event in pauses:
        if event_index <= synchronous_index:
            raise GameLifecycleError("Command-start effect pause precedes synchronous completion.")
        payload = _event_payload(event)
        binding = _binding_from_payload(payload=payload, registry=registry)
        if binding.effect_handler is None:
            raise GameLifecycleError("Command-start effect pause provider lacks an effect handler.")
        request_id = _optional_payload_string(payload, "pending_request_id")
        request_hash = payload.get("pending_request_payload_hash")
        if payload.get("status_kind") != "waiting_for_decision" or request_id is None:
            raise GameLifecycleError("Command-start effect pause lacks a waiting decision.")
        if request_id in seen_request_ids:
            raise GameLifecycleError("Command-start effect pause request is duplicated.")
        seen_request_ids.add(request_id)
        request = _request_by_id(decisions=decisions, request_id=request_id)
        if request is None or request_hash != _payload_hash(request.to_payload()):
            raise GameLifecycleError("Command-start effect pause request authority drifted.")
        requested_index = _exact_event_index(
            decisions.event_log.records,
            event_type="decision_requested",
            payload=request.to_payload(),
        )
        if requested_index >= event_index:
            raise GameLifecycleError("Command-start effect pause precedes its decision request.")
        effect_bindings = tuple(
            candidate
            for candidate in registry.all_bindings()
            if candidate.effect_handler is not None
        )
        try:
            binding_position = effect_bindings.index(binding)
        except ValueError as exc:
            raise GameLifecycleError(
                "Command-start effect pause provider capability drifted."
            ) from exc
        _validate_provider_dispositions(
            payload=payload,
            registry=registry,
            events=decisions.event_log.records,
            authority_event_index=event_index,
            expected_bindings=effect_bindings[: binding_position + 1],
        )
        record = _decision_record_by_request_id(decisions.records, request_id=request_id)
        if record is None:
            if (
                sum(
                    pending.request_id == request_id for pending in decisions.queue.pending_requests
                )
                != 1
            ):
                raise GameLifecycleError("Command-start effect pause lacks a live disposition.")
            if any(index > event_index for index in later_progress_indexes):
                raise GameLifecycleError(
                    "Pending Command-start effect pause has later boundary progress."
                )
            unresolved_request_ids.append(request_id)
            continue
        recorded_index = _exact_event_index(
            decisions.event_log.records,
            event_type="decision_recorded",
            payload=record.to_payload(),
        )
        if not event_index < recorded_index:
            raise GameLifecycleError("Command-start effect pause disposition ordering drifted.")
        has_later_boundary_progress = any(
            index > recorded_index for index in later_progress_indexes
        )
        if not has_later_boundary_progress and not _has_pending_continuation_for_request(
            decisions=decisions,
            source_request=request,
            recorded_index=recorded_index,
        ):
            raise GameLifecycleError("Command-start effect pause disposition lacks later progress.")
    return tuple(unresolved_request_ids)


def _validate_finite_requests(
    *,
    decisions: DecisionController,
    registry: CommandPhaseStartHookRegistry,
    synchronous_index: int,
    rows: tuple[tuple[int, EventRecord], ...],
) -> tuple[tuple[int, DecisionRequest, DecisionRecord | None, CommandPhaseStartHookBinding], ...]:
    validated: list[
        tuple[int, DecisionRequest, DecisionRecord | None, CommandPhaseStartHookBinding]
    ] = []
    seen_request_ids: set[str] = set()
    for event_index, event in rows:
        if event_index <= synchronous_index:
            raise GameLifecycleError(
                "Command-start finite request precedes synchronous completion."
            )
        payload = _event_payload(event)
        request_id = _payload_string(payload, "request_id")
        if request_id in seen_request_ids:
            raise GameLifecycleError("Command-start finite request authority is duplicated.")
        seen_request_ids.add(request_id)
        request = _request_by_id(decisions=decisions, request_id=request_id)
        if request is None:
            raise GameLifecycleError("Command-start finite request is absent from decisions.")
        if (
            request.decision_type != SELECT_FACTION_RULE_COMMAND_PHASE_START_OPTION_DECISION_TYPE
            or payload.get("decision_type") != request.decision_type
            or payload.get("request_payload_hash") != _payload_hash(request.to_payload())
        ):
            raise GameLifecycleError("Command-start finite request payload authority drifted.")
        binding = _binding_from_payload(payload=payload, registry=registry)
        if binding.request_handler is None or binding.result_handler is None:
            raise GameLifecycleError("Command-start finite request provider capability drifted.")
        requested_index = _exact_event_index(
            decisions.event_log.records,
            event_type="decision_requested",
            payload=request.to_payload(),
        )
        if requested_index >= event_index:
            raise GameLifecycleError("Command-start provider event precedes its decision request.")
        record = _decision_record_by_request_id(
            decisions.records,
            request_id=request.request_id,
        )
        validated.append((event_index, request, record, binding))
    return tuple(validated)


def _validate_finite_results(
    *,
    decisions: DecisionController,
    registry: CommandPhaseStartHookRegistry,
    request_rows: tuple[
        tuple[int, DecisionRequest, DecisionRecord | None, CommandPhaseStartHookBinding], ...
    ],
    rows: tuple[tuple[int, EventRecord], ...],
) -> dict[str, int]:
    result_by_request_id: dict[str, tuple[int, EventRecord]] = {}
    for event_index, event in rows:
        payload = _event_payload(event)
        request_id = _payload_string(payload, "request_id")
        if request_id in result_by_request_id:
            raise GameLifecycleError("Command-start finite result authority is duplicated.")
        result_by_request_id[request_id] = (event_index, event)
    if set(result_by_request_id) != {
        request.request_id
        for _index, request, record, _binding in request_rows
        if record is not None
    }:
        raise GameLifecycleError("Command-start finite result inventory drifted.")
    for request_index, request, record, request_binding in request_rows:
        if record is None:
            continue
        result_index, result_event = result_by_request_id[request.request_id]
        payload = _event_payload(result_event)
        binding = _binding_from_payload(payload=payload, registry=registry)
        if binding != request_binding:
            raise GameLifecycleError("Command-start finite result provider drifted.")
        if (
            payload.get("decision_type") != request.decision_type
            or payload.get("request_payload_hash") != _payload_hash(request.to_payload())
            or payload.get("result_id") != record.result.result_id
            or payload.get("result_payload_hash") != _payload_hash(record.result.to_payload())
        ):
            raise GameLifecycleError("Command-start finite result payload authority drifted.")
        recorded_index = _exact_event_index(
            decisions.event_log.records,
            event_type="decision_recorded",
            payload=record.to_payload(),
        )
        if not request_index < recorded_index < result_index:
            raise GameLifecycleError("Command-start finite result ordering drifted.")
        disposition_start_index = _validate_provider_dispositions(
            payload=payload,
            registry=registry,
            events=decisions.event_log.records,
            authority_event_index=result_index,
            expected_bindings=(binding,),
        )
        if disposition_start_index != recorded_index + 1:
            raise GameLifecycleError("Command-start finite provider output span drifted.")
    return {
        request_id: event_index
        for request_id, (event_index, _event) in result_by_request_id.items()
    }


def _validate_nested_finite_provider_pending_request(
    *,
    state: GameState,
    decisions: DecisionController,
    registry: CommandPhaseStartHookRegistry,
    effect_pauses: tuple[tuple[int, EventRecord], ...],
    request_rows: tuple[
        tuple[int, DecisionRequest, DecisionRecord | None, CommandPhaseStartHookBinding], ...
    ],
    result_index_by_request_id: dict[str, int],
    runtime_content_bundle: RuntimeContentBundle | None,
) -> None:
    pending = decisions.queue.pending_requests
    if len(pending) != 1:
        raise GameLifecycleError("Pending Command-start provider progress is ambiguous.")
    if runtime_content_bundle is None:
        raise GameLifecycleError(
            "Pending Command-start provider progress requires loaded runtime authority."
        )
    pending_request = pending[0]
    pending_index = _exact_event_index(
        decisions.event_log.records,
        event_type="decision_requested",
        payload=pending_request.to_payload(),
    )
    if any(record.request == pending_request for record in decisions.records):
        raise GameLifecycleError("Pending Command-start provider decision is already resolved.")

    completed_rows: list[
        tuple[DecisionRequest, DecisionRecord, CommandPhaseStartHookBinding, int, int]
    ] = []
    for _request_index, request, record, binding in request_rows:
        if record is None:
            continue
        recorded_index = _exact_event_index(
            decisions.event_log.records,
            event_type="decision_recorded",
            payload=record.to_payload(),
        )
        result_index = result_index_by_request_id.get(request.request_id)
        if result_index is None or recorded_index >= result_index:
            raise GameLifecycleError("Pending Command-start provider result ordering drifted.")
        completed_rows.append((request, record, binding, recorded_index, result_index))

    immediate_rows = tuple(row for row in completed_rows if row[3] < pending_index < row[4])
    nested_context = CommandPhaseStartNestedPendingAuthorityContext(
        state=state,
        decisions=decisions,
        request=pending_request,
        active_player_id=_active_player_id(state),
        battle_shock_hooks=runtime_content_bundle.battle_shock_hook_registry,
        runtime_modifier_registry=runtime_content_bundle.runtime_modifier_registry,
        ability_indexes_by_player_id=runtime_content_bundle.ability_indexes_by_player_id,
    )
    continued_effect_bindings: list[CommandPhaseStartHookBinding] = []
    for _pause_index, pause_event in effect_pauses:
        pause_payload = _event_payload(pause_event)
        source_request_id = _payload_string(pause_payload, "pending_request_id")
        source_request = _request_by_id(decisions=decisions, request_id=source_request_id)
        source_record = _decision_record_by_request_id(
            decisions.records,
            request_id=source_request_id,
        )
        if source_request is None or source_record is None:
            continue
        source_recorded_index = _exact_event_index(
            decisions.event_log.records,
            event_type="decision_recorded",
            payload=source_record.to_payload(),
        )
        if _has_pending_continuation_for_request(
            decisions=decisions,
            source_request=source_request,
            recorded_index=source_recorded_index,
        ):
            continued_effect_bindings.append(
                _binding_from_payload(payload=pause_payload, registry=registry)
            )
    if continued_effect_bindings:
        if len(continued_effect_bindings) != 1:
            raise GameLifecycleError("Pending Command-start effect continuation is ambiguous.")
        claimed_binding = registry.binding_for_nested_pending_authority(nested_context)
        if claimed_binding != continued_effect_bindings[0]:
            raise GameLifecycleError(
                "Pending Command-start effect continuation source binding drifted."
            )
        return
    if len(immediate_rows) == 1:
        outer_request, outer_record, binding, recorded_index, result_index = immediate_rows[0]
        if binding.nested_pending_authority_validator is not None:
            claimed_binding = registry.binding_for_nested_pending_authority(nested_context)
            if claimed_binding != binding:
                raise GameLifecycleError("Pending Command-start provider source binding drifted.")
    elif not immediate_rows:
        binding = registry.binding_for_nested_pending_authority(nested_context)
        matching_rows = tuple(row for row in completed_rows if row[2] == binding)
        if len(matching_rows) != 1:
            raise GameLifecycleError("Pending Command-start provider occurrence is ambiguous.")
        outer_request, outer_record, binding, recorded_index, result_index = matching_rows[0]
        if pending_index <= recorded_index:
            raise GameLifecycleError("Pending Command-start provider ordering drifted.")
    else:
        raise GameLifecycleError("Pending Command-start provider output span is ambiguous.")

    request_payload = pending_request.payload
    if isinstance(request_payload, dict) and "battle_shock_context" in request_payload:
        from warhammer40k_core.engine.battle_shock_pending_authority import (
            validate_live_pending_battle_shock_reroll_authority,
        )

        authority = validate_live_pending_battle_shock_reroll_authority(
            state=state,
            event_records=decisions.event_log.records,
            decision_records=decisions.records,
            pending_request=pending_request,
            runtime_content_bundle=runtime_content_bundle,
        )
        if authority.source_kind != COMMAND_PHASE_START_BATTLE_SHOCK_SOURCE_KIND:
            raise GameLifecycleError("Pending Command-start provider source kind drifted.")
        source_state_payload = authority.base_payload.get("source_faction_rule_state")
        if not isinstance(source_state_payload, dict):
            raise GameLifecycleError("Pending Command-start Battle-shock lacks source state.")
        matching_states = tuple(
            source_state
            for source_state in state.faction_rule_states
            if source_state.to_payload() == source_state_payload
        )
        if len(matching_states) != 1:
            raise GameLifecycleError("Pending Command-start Battle-shock source state drifted.")
        source_state = matching_states[0]
        state_payload = source_state.payload
        if (
            source_state.request_id != outer_request.request_id
            or source_state.result_id != outer_record.result.result_id
            or source_state.source_rule_id != binding.source_id
            or not isinstance(state_payload, dict)
            or state_payload.get("hook_id") != binding.hook_id
        ):
            raise GameLifecycleError("Pending Command-start Battle-shock provider drifted.")
    recorded_index = _exact_event_index(
        decisions.event_log.records,
        event_type="decision_recorded",
        payload=outer_record.to_payload(),
    )
    if recorded_index >= result_index or pending_index <= recorded_index:
        raise GameLifecycleError("Pending Command-start provider ordering drifted.")


def _record_effect_pause(
    *,
    state: GameState,
    decisions: DecisionController,
    registry: CommandPhaseStartHookRegistry,
    binding: CommandPhaseStartHookBinding,
    status: LifecycleStatus,
    dispositions: tuple[CommandPhaseStartProviderDisposition, ...],
) -> None:
    _require_registry_binding(registry=registry, binding=binding, requires_effect=True)
    if status.status_kind is not LifecycleStatusKind.WAITING_FOR_DECISION:
        raise GameLifecycleError(
            "Command-start effect providers must pause with waiting_for_decision."
        )
    if status.stage is not GameLifecycleStage.BATTLE:
        raise GameLifecycleError("Command-start effect provider status stage drifted.")
    request = status.decision_request
    if request is None:
        raise GameLifecycleError("Command-start effect pause lacks a decision request.")
    if decisions.queue.pending_requests != (request,):
        raise GameLifecycleError(
            "Command-start effect provider must enqueue exactly its returned request."
        )
    _exact_event_index(
        decisions.event_log.records,
        event_type="decision_requested",
        payload=request.to_payload(),
    )
    decisions.event_log.append(
        COMMAND_START_EFFECT_PAUSED_EVENT,
        {
            **_authority_common_payload(state=state, registry=registry),
            "provider_hook_id": binding.hook_id,
            "provider_source_id": binding.source_id,
            "status_kind": status.status_kind.value,
            "pending_request_id": request.request_id,
            "pending_request_payload_hash": _payload_hash(request.to_payload()),
            "provider_dispositions": _provider_dispositions_payload(dispositions),
        },
    )


def _record_effect_pass_completion(
    *,
    state: GameState,
    decisions: DecisionController,
    registry: CommandPhaseStartHookRegistry,
    dispositions: tuple[CommandPhaseStartProviderDisposition, ...],
) -> None:
    key = (state.battle_round, _active_player_id(state))
    pass_count = sum(
        event.event_type == COMMAND_START_EFFECT_PASS_COMPLETED_EVENT
        and isinstance(event.payload, dict)
        and event.payload.get("battle_round") == key[0]
        and event.payload.get("active_player_id") == key[1]
        for event in decisions.event_log.records
    )
    decisions.event_log.append(
        COMMAND_START_EFFECT_PASS_COMPLETED_EVENT,
        {
            **_authority_common_payload(state=state, registry=registry),
            "effect_pass_index": pass_count + 1,
            "provider_dispositions": _provider_dispositions_payload(dispositions),
        },
    )


def _append_completion_event(
    *,
    state: GameState,
    decisions: DecisionController,
    registry: CommandPhaseStartHookRegistry,
    event_type: str,
    dispositions: tuple[CommandPhaseStartProviderDisposition, ...],
) -> None:
    decisions.event_log.append(
        event_type,
        {
            **_authority_common_payload(state=state, registry=registry),
            "provider_binding_inventory": _registry_inventory(registry),
            "provider_dispositions": _provider_dispositions_payload(dispositions),
        },
    )


def _authority_common_payload(
    *,
    state: GameState,
    registry: CommandPhaseStartHookRegistry,
) -> dict[str, JsonValue]:
    return {
        "game_id": state.game_id,
        "battle_round": state.battle_round,
        "active_player_id": _active_player_id(state),
        "phase": BattlePhase.COMMAND.value,
        "provider_registry_fingerprint": _registry_fingerprint(registry),
    }


def _validate_authority_common_payload(
    *,
    payload: dict[str, JsonValue],
    state: GameState,
    registry: CommandPhaseStartHookRegistry,
) -> tuple[int, str]:
    if payload.get("game_id") != state.game_id:
        raise GameLifecycleError("Command-start authority game identity drifted.")
    battle_round = payload.get("battle_round")
    active_player_id = payload.get("active_player_id")
    if type(battle_round) is not int or battle_round <= 0:
        raise GameLifecycleError("Command-start authority battle round is invalid.")
    if type(active_player_id) is not str or not active_player_id.strip():
        raise GameLifecycleError("Command-start authority active player is invalid.")
    if active_player_id not in state.player_ids:
        raise GameLifecycleError("Command-start authority active player is unknown.")
    if payload.get("phase") != BattlePhase.COMMAND.value:
        raise GameLifecycleError("Command-start authority phase drifted.")
    if payload.get("provider_registry_fingerprint") != _registry_fingerprint(registry):
        raise GameLifecycleError("Command-start loaded provider registry drifted.")
    inventory = payload.get("provider_binding_inventory")
    if "provider_binding_inventory" in payload and inventory != _registry_inventory(registry):
        raise GameLifecycleError("Command-start provider binding inventory drifted.")
    return battle_round, active_player_id


def _validate_exact_payload_shape(
    *,
    event_type: str,
    payload: dict[str, JsonValue],
) -> None:
    expected_keys = _PAYLOAD_KEYS_BY_EVENT_TYPE.get(event_type)
    if expected_keys is None or frozenset(payload) != expected_keys:
        raise GameLifecycleError(f"Command-start {event_type} payload shape drifted.")


def _registry_inventory(registry: CommandPhaseStartHookRegistry) -> list[JsonValue]:
    return [
        {
            "hook_id": binding.hook_id,
            "source_id": binding.source_id,
            "has_synchronous_handler": binding.handler is not None,
            "has_effect_handler": binding.effect_handler is not None,
            "has_request_handler": binding.request_handler is not None,
            "has_result_handler": binding.result_handler is not None,
            "has_nested_result_handler": binding.nested_result_handler is not None,
            "has_nested_pending_authority_validator": (
                binding.nested_pending_authority_validator is not None
            ),
        }
        for binding in registry.all_bindings()
    ]


def _registry_fingerprint(registry: CommandPhaseStartHookRegistry) -> str:
    return _payload_hash(_registry_inventory(registry))


def _provider_dispositions_payload(
    dispositions: tuple[CommandPhaseStartProviderDisposition, ...],
) -> list[JsonValue]:
    if type(dispositions) is not tuple or any(
        type(disposition) is not CommandPhaseStartProviderDisposition
        for disposition in dispositions
    ):
        raise GameLifecycleError("Command-start provider dispositions must be typed.")
    payloads: list[JsonValue] = []
    for disposition in dispositions:
        if any(event.event_type in _AUTHORITY_EVENT_TYPES for event in disposition.emitted_events):
            raise GameLifecycleError("Command-start provider emitted reserved authority events.")
        payloads.append(
            {
                "provider_hook_id": disposition.binding.hook_id,
                "provider_source_id": disposition.binding.source_id,
                "state_changed": disposition.state_changed,
                "emitted_event_ids": [event.event_id for event in disposition.emitted_events],
                "emitted_events_hash": _payload_hash(
                    [event.to_payload() for event in disposition.emitted_events]
                ),
            }
        )
    return payloads


def _validate_provider_dispositions(
    *,
    payload: dict[str, JsonValue],
    registry: CommandPhaseStartHookRegistry,
    events: tuple[EventRecord, ...],
    authority_event_index: int,
    expected_bindings: tuple[CommandPhaseStartHookBinding, ...],
) -> int:
    raw_rows = payload.get("provider_dispositions")
    if not isinstance(raw_rows, list) or len(raw_rows) != len(expected_bindings):
        raise GameLifecycleError("Command-start provider disposition inventory drifted.")
    rows: list[tuple[CommandPhaseStartHookBinding, bool, tuple[str, ...], str]] = []
    for raw_row, expected_binding in zip(raw_rows, expected_bindings, strict=True):
        if not isinstance(raw_row, dict) or frozenset(raw_row) != _PROVIDER_DISPOSITION_KEYS:
            raise GameLifecycleError("Command-start provider disposition shape drifted.")
        row = raw_row
        binding = _binding_from_payload(payload=row, registry=registry)
        state_changed = row.get("state_changed")
        raw_event_ids = row.get("emitted_event_ids")
        events_hash = row.get("emitted_events_hash")
        if (
            binding != expected_binding
            or type(state_changed) is not bool
            or not isinstance(raw_event_ids, list)
            or type(events_hash) is not str
            or not events_hash.strip()
        ):
            raise GameLifecycleError("Command-start provider disposition drifted.")
        parsed_event_ids: list[str] = []
        for raw_event_id in raw_event_ids:
            if type(raw_event_id) is not str or not raw_event_id.strip():
                raise GameLifecycleError("Command-start provider disposition drifted.")
            parsed_event_ids.append(raw_event_id)
        if len(set(parsed_event_ids)) != len(parsed_event_ids) or (
            state_changed and not parsed_event_ids
        ):
            raise GameLifecycleError("Command-start provider disposition drifted.")
        rows.append((binding, state_changed, tuple(parsed_event_ids), events_hash))

    cursor = authority_event_index
    for _binding, _state_changed, event_ids, events_hash in reversed(rows):
        start = cursor - len(event_ids)
        if start < 0:
            raise GameLifecycleError("Command-start provider output span underflowed.")
        emitted = events[start:cursor]
        if (
            tuple(event.event_id for event in emitted) != event_ids
            or any(event.event_type in _AUTHORITY_EVENT_TYPES for event in emitted)
            or _payload_hash([event.to_payload() for event in emitted]) != events_hash
        ):
            raise GameLifecycleError("Command-start provider output evidence drifted.")
        cursor = start
    return cursor


def _payload_hash(payload: object) -> str:
    return hashlib.sha256(canonical_json(payload).encode("utf-8")).hexdigest()


def _binding_from_payload(
    *,
    payload: dict[str, JsonValue],
    registry: CommandPhaseStartHookRegistry,
) -> CommandPhaseStartHookBinding:
    hook_id = _payload_string(payload, "provider_hook_id")
    source_id = _payload_string(payload, "provider_source_id")
    matches = tuple(
        binding
        for binding in registry.all_bindings()
        if binding.hook_id == hook_id and binding.source_id == source_id
    )
    if len(matches) != 1:
        raise GameLifecycleError("Command-start provider binding identity drifted.")
    return matches[0]


def _require_registry_binding(
    *,
    registry: CommandPhaseStartHookRegistry,
    binding: CommandPhaseStartHookBinding,
    requires_effect: bool = False,
    requires_result: bool = False,
) -> None:
    if type(binding) is not CommandPhaseStartHookBinding:
        raise GameLifecycleError("Command-start authority requires a provider binding.")
    if sum(stored == binding for stored in registry.all_bindings()) != 1:
        raise GameLifecycleError("Command-start authority provider is not loaded exactly once.")
    if requires_effect and binding.effect_handler is None:
        raise GameLifecycleError("Command-start authority provider lacks an effect handler.")
    if requires_result and binding.result_handler is None:
        raise GameLifecycleError("Command-start authority provider lacks a result handler.")


def _event_payload(event: EventRecord) -> dict[str, JsonValue]:
    if not isinstance(event.payload, dict):
        raise GameLifecycleError("Command-start authority event payload must be an object.")
    return event.payload


def _payload_string(payload: dict[str, JsonValue], key: str) -> str:
    value = payload.get(key)
    if type(value) is not str or not value.strip():
        raise GameLifecycleError(f"Command-start authority {key} must be a string.")
    return value


def _optional_payload_string(payload: dict[str, JsonValue], key: str) -> str | None:
    value = payload.get(key)
    if value is None:
        return None
    if type(value) is not str or not value.strip():
        raise GameLifecycleError(f"Command-start authority {key} must be a string or null.")
    return value


def _request_by_id(
    *,
    decisions: DecisionController,
    request_id: str,
) -> DecisionRequest | None:
    matches = tuple(
        request for request in decisions.queue.pending_requests if request.request_id == request_id
    ) + tuple(
        record.request for record in decisions.records if record.request.request_id == request_id
    )
    if len(matches) > 1:
        raise GameLifecycleError("Command-start request identity is duplicated.")
    return None if not matches else matches[0]


def _has_pending_continuation_for_request(
    *,
    decisions: DecisionController,
    source_request: DecisionRequest,
    recorded_index: int,
) -> bool:
    from warhammer40k_core.engine.mortal_wound_model_allocation import (
        is_mortal_wound_resolution_request,
        mortal_wound_resolution_progress,
    )

    if not is_mortal_wound_resolution_request(source_request):
        return False
    pending = decisions.queue.pending_requests
    if len(pending) != 1 or not is_mortal_wound_resolution_request(pending[0]):
        return False
    source_progress = mortal_wound_resolution_progress(source_request)
    pending_progress = mortal_wound_resolution_progress(pending[0])
    if (
        source_progress.application_id != pending_progress.application_id
        or source_progress.source_rule_id != pending_progress.source_rule_id
        or source_progress.source_context != pending_progress.source_context
    ):
        return False
    pending_index = _exact_event_index(
        decisions.event_log.records,
        event_type="decision_requested",
        payload=pending[0].to_payload(),
    )
    return pending_index > recorded_index and not any(
        record.request == pending[0] for record in decisions.records
    )


def _decision_record_by_request_id(
    records: tuple[DecisionRecord, ...],
    *,
    request_id: str,
) -> DecisionRecord | None:
    matches = tuple(record for record in records if record.request.request_id == request_id)
    if len(matches) > 1:
        raise GameLifecycleError("Command-start decision record identity is duplicated.")
    return None if not matches else matches[0]


def _exact_event_index(
    events: tuple[EventRecord, ...],
    *,
    event_type: str,
    payload: object,
) -> int:
    validated_payload = validate_json_value(payload)
    indexes = tuple(
        index
        for index, event in enumerate(events)
        if event.event_type == event_type and event.payload == validated_payload
    )
    if len(indexes) != 1:
        raise GameLifecycleError(f"Command-start requires one exact {event_type} event.")
    return indexes[0]


def _command_step_anchor_index(
    events: tuple[EventRecord, ...],
    *,
    battle_round: int,
    active_player_id: str,
) -> int:
    indexes = tuple(
        index
        for index, event in enumerate(events)
        if event.event_type == "command_step_started"
        and isinstance(event.payload, dict)
        and event.payload.get("battle_round") == battle_round
        and event.payload.get("active_player_id") == active_player_id
    )
    if len(indexes) != 1:
        raise GameLifecycleError("Command-start completion requires one exact Core CP anchor.")
    return indexes[0]


def _current_command_key(state: GameState) -> tuple[int, str] | None:
    if state.stage is not GameLifecycleStage.BATTLE:
        return None
    if state.current_battle_phase is not BattlePhase.COMMAND:
        return None
    if state.active_player_id is None:
        raise GameLifecycleError("Command-start authority requires an active player.")
    return state.battle_round, state.active_player_id


def _current_incomplete_command_key(state: GameState) -> tuple[int, str] | None:
    key = _current_command_key(state)
    if key is None or key in expected_core_command_occurrence_keys(state):
        return None
    return key


def _active_player_id(state: GameState) -> str:
    active_player_id = state.active_player_id
    if active_player_id is None:
        raise GameLifecycleError("Command-start boundary requires an active player.")
    return active_player_id


def _require_empty_pending_queue(
    *,
    decisions: DecisionController,
    context: str,
) -> None:
    if decisions.queue.pending_requests:
        raise GameLifecycleError(f"{context}.")


def _require_command_state(state: GameState) -> CommandStepState:
    command_state = state.command_step_state
    if command_state is None:
        raise GameLifecycleError("Command-start boundary requires CommandStepState.")
    return command_state


def _validate_runtime_inputs(
    *,
    state: GameState,
    decisions: DecisionController,
    registry: CommandPhaseStartHookRegistry,
    runtime_modifier_registry: RuntimeModifierRegistry,
) -> None:
    from warhammer40k_core.engine.game_state import GameState

    if type(state) is not GameState:
        raise GameLifecycleError("Command-start boundary requires GameState.")
    if type(decisions) is not DecisionController:
        raise GameLifecycleError("Command-start boundary requires DecisionController.")
    if type(registry) is not CommandPhaseStartHookRegistry:
        raise GameLifecycleError("Command-start boundary requires a hook registry.")
    if type(runtime_modifier_registry) is not RuntimeModifierRegistry:
        raise GameLifecycleError("Command-start boundary requires a modifier registry.")
    if state.stage is not GameLifecycleStage.BATTLE:
        raise GameLifecycleError("Command-start boundary requires battle stage.")
    if state.current_battle_phase is not BattlePhase.COMMAND:
        raise GameLifecycleError("Command-start boundary requires Command phase.")


__all__ = (
    "COMMAND_START_BOUNDARY_COMPLETED_EVENT",
    "COMMAND_START_EFFECT_PASS_COMPLETED_EVENT",
    "COMMAND_START_EFFECT_PAUSED_EVENT",
    "COMMAND_START_FINITE_REQUESTED_EVENT",
    "COMMAND_START_FINITE_RESULT_EVENT",
    "COMMAND_START_SYNCHRONOUS_COMPLETED_EVENT",
    "record_command_phase_start_finite_result",
    "resolve_command_phase_start_boundary",
    "validate_command_phase_start_restore_authority",
)
