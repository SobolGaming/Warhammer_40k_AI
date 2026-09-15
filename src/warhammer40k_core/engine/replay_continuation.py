"""Replay deterministic engine progress between recorded player choices."""

from __future__ import annotations

# Shared replay implementation; diagnostics and hashing remain owned by replay.
# pyright: reportPrivateUsage=false
from typing import TYPE_CHECKING

from warhammer40k_core.engine.phase import LifecycleStatusKind

if TYPE_CHECKING:
    from warhammer40k_core.engine.decision_record import DecisionRecord
    from warhammer40k_core.engine.event_log import EventRecord
    from warhammer40k_core.engine.lifecycle import GameLifecycle
    from warhammer40k_core.engine.replay import ReplayDriftDiagnostic


def advance_recorded_automatic_progress(
    *,
    lifecycle: GameLifecycle,
    expected_events: tuple[EventRecord, ...],
    initial_event_count: int,
) -> None:
    """Follow recorded automatic progress only while history is an exact prefix.

    A completed reaction can return ADVANCED without a pending choice. Each
    advance must add events, and the recorded tail bounds how far replay goes.
    Choices remain exclusively owned by the recorded DecisionResults.
    """
    while not lifecycle.decision_controller.queue.pending_requests:
        actual = lifecycle.decision_controller.event_log.records[initial_event_count:]
        if len(actual) >= len(expected_events) or actual != expected_events[: len(actual)]:
            return
        status = lifecycle.advance_until_decision_or_terminal()
        if status.status_kind in {
            LifecycleStatusKind.INVALID,
            LifecycleStatusKind.UNSUPPORTED,
        }:
            return
        if len(lifecycle.decision_controller.event_log.records) <= initial_event_count + len(
            actual
        ):
            return


def request_drift_diagnostic(
    *,
    lifecycle: GameLifecycle,
    expected_record: DecisionRecord,
    decision_record_index: int,
) -> ReplayDriftDiagnostic | None:
    from warhammer40k_core.engine.replay import (
        ReplayDiagnosticCode,
        ReplayDriftDiagnostic,
        _json_payload,
        decision_request_options_fingerprint,
        decision_request_payload_hash,
    )

    pending_requests = lifecycle.decision_controller.queue.pending_requests
    if not pending_requests:
        return ReplayDriftDiagnostic(
            diagnostic_code=ReplayDiagnosticCode.NO_PENDING_REQUEST,
            message="Replay expected a pending DecisionRequest.",
            decision_record_index=decision_record_index,
            record_id=expected_record.record_id,
            expected=_json_payload(expected_record.request.to_payload()),
            actual=None,
        )
    actual_request = pending_requests[0]
    expected_request = expected_record.request
    if actual_request.request_id != expected_request.request_id:
        return ReplayDriftDiagnostic(
            diagnostic_code=ReplayDiagnosticCode.REQUEST_ID_DRIFT,
            message="Replayed DecisionRequest ID drifted.",
            decision_record_index=decision_record_index,
            record_id=expected_record.record_id,
            expected={"request_id": expected_request.request_id},
            actual={"request_id": actual_request.request_id},
        )
    if actual_request.decision_type != expected_request.decision_type:
        return ReplayDriftDiagnostic(
            diagnostic_code=ReplayDiagnosticCode.DECISION_TYPE_DRIFT,
            message="Replayed DecisionRequest type drifted.",
            decision_record_index=decision_record_index,
            record_id=expected_record.record_id,
            expected={"decision_type": expected_request.decision_type},
            actual={"decision_type": actual_request.decision_type},
        )
    if actual_request.actor_id != expected_request.actor_id:
        return ReplayDriftDiagnostic(
            diagnostic_code=ReplayDiagnosticCode.ACTOR_DRIFT,
            message="Replayed DecisionRequest actor drifted.",
            decision_record_index=decision_record_index,
            record_id=expected_record.record_id,
            expected={"actor_id": expected_request.actor_id},
            actual={"actor_id": actual_request.actor_id},
        )
    expected_payload_hash = decision_request_payload_hash(expected_request)
    actual_payload_hash = decision_request_payload_hash(actual_request)
    if actual_payload_hash != expected_payload_hash:
        return ReplayDriftDiagnostic(
            diagnostic_code=ReplayDiagnosticCode.REQUEST_PAYLOAD_HASH_DRIFT,
            message="Replayed DecisionRequest payload hash drifted.",
            decision_record_index=decision_record_index,
            record_id=expected_record.record_id,
            expected={"payload_hash": expected_payload_hash},
            actual={"payload_hash": actual_payload_hash},
        )
    expected_option_hash = decision_request_options_fingerprint(expected_request)
    actual_option_hash = decision_request_options_fingerprint(actual_request)
    if actual_option_hash != expected_option_hash:
        return ReplayDriftDiagnostic(
            diagnostic_code=ReplayDiagnosticCode.LEGAL_OPTION_FINGERPRINT_DRIFT,
            message="Replayed legal option fingerprint drifted.",
            decision_record_index=decision_record_index,
            record_id=expected_record.record_id,
            expected={"legal_option_fingerprint": expected_option_hash},
            actual={"legal_option_fingerprint": actual_option_hash},
        )
    return None
