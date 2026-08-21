from __future__ import annotations

from http import HTTPStatus
from typing import cast

from warhammer40k_core.adapters.access_control import ViewerContext
from warhammer40k_core.adapters.contracts import AdapterGameSession
from warhammer40k_core.adapters.redaction import redacted_lifecycle_status
from warhammer40k_core.adapters.server_sync import (
    session_checkpoint,
    session_metadata_payload,
)
from warhammer40k_core.adapters.server_types import ServerApiError, ServerResponse
from warhammer40k_core.adapters.session_events import SessionCursorCodec
from warhammer40k_core.adapters.session_protocol import (
    AuthoritativeSession,
    SessionProtocolError,
    session_command_result_payload,
)
from warhammer40k_core.adapters.session_revision import (
    SessionRevisionCursorCommitment,
    SessionRevisionOrigin,
)
from warhammer40k_core.engine.event_log import JsonValue, validate_json_value
from warhammer40k_core.engine.phase import LifecycleStatus, LifecycleStatusKind

type SessionCommandResponse = tuple[
    ServerResponse,
    SessionRevisionCursorCommitment,
    SessionRevisionCursorCommitment,
]


def session_command_response(
    *,
    record: AuthoritativeSession,
    operation: str,
    committed: bool,
    accepted: bool,
    viewer: ViewerContext,
    cursor_codec: SessionCursorCodec,
    from_cursor: str,
    attempt_status: LifecycleStatus | None = None,
    status_code: HTTPStatus = HTTPStatus.OK,
) -> SessionCommandResponse:
    committed_from_cursor = SessionRevisionCursorCommitment(
        token=from_cursor,
        cursor=cursor_codec.committed_cursor(from_cursor),
    )
    checkpoint = session_checkpoint(
        record=record,
        viewer=viewer,
        cursor_codec=cursor_codec,
    )
    to_cursor = checkpoint["event_cursor"]
    committed_to_cursor = SessionRevisionCursorCommitment(
        token=to_cursor,
        cursor=cursor_codec.committed_cursor(to_cursor),
    )
    metadata = session_metadata_payload(
        record=record,
        viewer=viewer,
        cursor_codec=cursor_codec,
    )
    if attempt_status is not None:
        metadata["lifecycle_status"] = validate_json_value(
            cast(JsonValue, redacted_lifecycle_status(attempt_status, viewer=viewer))
        )
    payload = session_command_result_payload(
        operation=operation,
        committed=committed,
        accepted=accepted,
        session=metadata,
        checkpoint=checkpoint,
        from_cursor=from_cursor,
    )
    return (
        ServerResponse(
            status_code=int(status_code),
            payload=validate_json_value(cast(JsonValue, payload)),
        ),
        committed_from_cursor,
        committed_to_cursor,
    )


def commit_submission_status(
    *,
    record: AuthoritativeSession,
    session: AdapterGameSession,
    status: LifecycleStatus,
    record_count_before: int,
    timestamp: str,
    revision_origin: SessionRevisionOrigin,
) -> tuple[LifecycleStatus, bool, bool]:
    committed = _decision_history_advanced(
        record=record,
        record_count_before=record_count_before,
    )
    accepted = _submission_was_applied(status=status, committed=committed)
    committed_status = (
        _drain_after_submission(session=session, status=status) if accepted else status
    )
    if committed:
        record.commit_status(
            committed_status,
            timestamp=timestamp,
            origin=revision_origin,
        )
    return committed_status, committed, accepted


def decision_record_count(record: AuthoritativeSession) -> int:
    count = record.adapter_session.decision_record_count()
    if type(count) is not int or count < 0:
        raise SessionProtocolError("Session decision record count is invalid.")
    return count


def _drain_after_submission(
    *,
    session: AdapterGameSession,
    status: LifecycleStatus,
) -> LifecycleStatus:
    if status.status_kind is not LifecycleStatusKind.ADVANCED:
        return status
    drained = session.advance_until_decision_or_terminal()
    if drained.status_kind is LifecycleStatusKind.ADVANCED:
        raise ServerApiError(
            status_code=HTTPStatus.INTERNAL_SERVER_ERROR,
            code="drain_boundary_missing",
            message="Session drain did not reach an adapter-visible boundary.",
        )
    return drained


def _submission_was_applied(*, status: LifecycleStatus, committed: bool) -> bool:
    if status.status_kind is LifecycleStatusKind.INVALID:
        return False
    if status.status_kind is LifecycleStatusKind.UNSUPPORTED:
        return committed and _is_transition_budget_boundary(status)
    if not committed:
        raise SessionProtocolError("Accepted session submission was not recorded.")
    return True


def _is_transition_budget_boundary(status: LifecycleStatus) -> bool:
    payload = status.payload
    if not isinstance(payload, dict) or "unsupported_reason" not in payload:
        return False
    return payload["unsupported_reason"] == "transition_budget_exhausted"


def _decision_history_advanced(
    *,
    record: AuthoritativeSession,
    record_count_before: int,
) -> bool:
    record_count_after = decision_record_count(record)
    if record_count_after < record_count_before:
        raise SessionProtocolError("Session decision history moved backwards.")
    return record_count_after > record_count_before


__all__ = [
    "SessionCommandResponse",
    "commit_submission_status",
    "decision_record_count",
    "session_command_response",
]
