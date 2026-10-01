"""Bind failed ordinary setups to the existing independent lifecycle origin."""

from __future__ import annotations

from contextvars import ContextVar
from typing import TYPE_CHECKING, cast

from warhammer40k_core.engine.event_log import canonical_json
from warhammer40k_core.engine.phase import GameLifecycleError
from warhammer40k_core.engine.transport_cargo_location_history import (
    validate_transport_cargo_location_suffix,
)

if TYPE_CHECKING:
    from warhammer40k_core.engine.lifecycle import GameLifecycle, GameLifecyclePayload
    from warhammer40k_core.engine.modifier_evaluation_history import (
        ModifierEvaluationHistoryOrigin,
    )

_RECONSTRUCTING: ContextVar[bool] = ContextVar("failed_setup_reconstructing", default=False)


def validate_failed_setup_origin(
    *, lifecycle: GameLifecycle, origin: ModifierEvaluationHistoryOrigin | None
) -> None:
    """Replay failed setups and close their prior location through terminal cargo.

    The first accepted decision captures this existing origin even without modifier
    choices. Terminal state loses prior location and diagnostic producer authority
    after later casualties and phase resets. Replaying its exact prefix uses shared
    cargo, casualty, revival, reserve and attached-unit owners at each request.
    """
    if _RECONSTRUCTING.get():
        return
    expected = lifecycle.decision_controller
    failed_result_ids = {
        result_id
        for event in expected.event_log.records
        if event.event_type == "movement_setup_failed"
        and isinstance(event.payload, dict)
        and isinstance((result_id := event.payload.get("result_id")), str)
        and any(
            prior.event_id == event.payload.get("invalid_event_id")
            and prior.event_type
            in {
                "disembark_placement_invalid",
                "combat_disembark_placement_invalid",
                "reinforcement_placement_invalid",
            }
            for prior in expected.event_log.records
        )
    }
    if not failed_result_ids:
        return
    if origin is None:
        raise GameLifecycleError("Failed setup lacks independent prior-location authority.")
    indexes = tuple(
        index
        for index, record in enumerate(expected.records)
        if record.result.result_id in failed_result_ids
    )
    if len(indexes) != len(failed_result_ids):
        raise GameLifecycleError("Failed setup historical decision identity drift.")
    token = _RECONSTRUCTING.set(True)
    try:
        _reconstruct_through_failed_setup(
            lifecycle=lifecycle, origin=origin, last_index=max(indexes)
        )
    finally:
        _RECONSTRUCTING.reset(token)


def _reconstruct_through_failed_setup(
    *, lifecycle: GameLifecycle, origin: ModifierEvaluationHistoryOrigin, last_index: int
) -> None:
    from warhammer40k_core.engine.lifecycle import GameLifecycle
    from warhammer40k_core.engine.replay_continuation import advance_recorded_automatic_progress

    initial = origin.to_payload()
    current = lifecycle.to_payload()
    if (
        canonical_json(initial.get("config")) != canonical_json(current["config"])
        or initial.get("parameterized_movement_proposals")
        != current["parameterized_movement_proposals"]
    ):
        raise GameLifecycleError("Failed setup origin catalog/config authority drift.")
    raw_decisions = initial.get("decisions")
    if not isinstance(raw_decisions, dict):
        raise GameLifecycleError("Failed setup origin requires decisions.")
    raw_events = raw_decisions.get("event_log")
    if not isinstance(raw_events, list) or any(
        not isinstance(event, dict) or event.get("event_type") == "movement_setup_failed"
        for event in raw_events
    ):
        raise GameLifecycleError("Failed setup origin must precede the first failed setup.")
    reproduced = GameLifecycle.from_payload(cast("GameLifecyclePayload", initial))
    actual = reproduced.decision_controller
    expected = lifecycle.decision_controller
    record_count = len(actual.records)
    event_count = len(actual.event_log.records)
    if (
        record_count > last_index
        or actual.records != expected.records[:record_count]
        or actual.event_log.records != expected.event_log.records[:event_count]
    ):
        raise GameLifecycleError("Failed setup origin historical prefix drift.")
    tail = expected.event_log.records[event_count:]
    for index in range(record_count, last_index + 1):
        if len(actual.records) <= index:
            advance_recorded_automatic_progress(
                lifecycle=reproduced,
                expected_events=tail,
                initial_event_count=event_count,
                stop_at_record_count=index + 1,
            )
        if len(actual.records) <= index:
            record = expected.records[index]
            pending = actual.queue.pending_requests
            if not pending or pending[0] != record.request:
                raise GameLifecycleError("Failed setup historical prior-location request drift.")
            reproduced.submit_decision(record.result)
        if (
            len(actual.records) <= index
            or actual.records != expected.records[: len(actual.records)]
            or actual.event_log.records
            != expected.event_log.records[: len(actual.event_log.records)]
        ):
            raise GameLifecycleError("Failed setup historical prior-location reconstruction drift.")
    boundary_state = reproduced.state
    terminal_state = lifecycle.state
    if boundary_state is None or terminal_state is None:
        raise GameLifecycleError("Failed setup requires physical location authority.")
    affected_unit_ids = frozenset(
        unit_id
        for event in expected.event_log.records
        if event.event_type == "movement_setup_failed"
        and isinstance(event.payload, dict)
        and isinstance((unit_id := event.payload.get("unit_instance_id")), str)
    )
    validate_transport_cargo_location_suffix(
        boundary_state=boundary_state,
        state=terminal_state,
        event_records=expected.event_log.records,
        decision_records=expected.records,
        initial_event_count=len(actual.event_log.records),
        affected_unit_instance_ids=affected_unit_ids,
    )
