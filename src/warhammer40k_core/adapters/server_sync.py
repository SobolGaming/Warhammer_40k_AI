from __future__ import annotations

from typing import cast

from warhammer40k_core.adapters.access_control import ViewerContext
from warhammer40k_core.adapters.event_stream import EventStreamCursor
from warhammer40k_core.adapters.external_contract import (
    EVENT_STREAM_DELTA_SCHEMA_VERSION,
    SESSION_PROJECTION_SCHEMA_VERSION,
)
from warhammer40k_core.adapters.redaction import redacted_lifecycle_status
from warhammer40k_core.adapters.session_events import (
    CursorResyncReason,
    CursorValidationError,
    SessionCursor,
    SessionCursorCodec,
    SessionEventDeltaPayload,
    SessionEventProtocolError,
    SessionProjectionPayload,
    retention_floor,
    sequenced_events,
    validate_page_limit,
    validate_retention_limit,
)
from warhammer40k_core.adapters.session_protocol import (
    AuthoritativeSession,
    SessionCheckpointPayload,
    SessionMetadataPayload,
    SessionProtocolError,
    SessionRevisionSnapshot,
)
from warhammer40k_core.engine.event_log import JsonValue, validate_json_value

REDACTED_INVALID_CURSOR = "invalid-cursor"


def session_projection_payload(
    *,
    record: AuthoritativeSession,
    viewer: ViewerContext,
    cursor_codec: SessionCursorCodec,
    retention_limit: int,
) -> SessionProjectionPayload:
    snapshot = record.snapshot_for_viewer(viewer)
    view = snapshot.adapter_session.view_for_context(viewer=viewer)
    projection_hash = view["projection_state_hash"]
    cursor = cursor_codec.issue(
        session_id=record.session_id,
        viewer=viewer,
        offset=snapshot.event_count,
        visible_sequence=_visible_event_count(snapshot, viewer=viewer),
        session_revision=snapshot.session_revision,
        projection_state_hash=projection_hash,
    )
    payload: SessionProjectionPayload = {
        "schema_version": SESSION_PROJECTION_SCHEMA_VERSION,
        "session_id": record.session_id,
        "game_id": record.game_id,
        "session_revision": snapshot.session_revision,
        "visibility_role": viewer.role.value,
        "projection_state_hash": projection_hash,
        "event_cursor": cursor,
        "retention_limit": validate_retention_limit(retention_limit),
        "projection": validate_json_value(cast(JsonValue, view)),
    }
    validate_json_value(cast(JsonValue, payload))
    return payload


def session_checkpoint(
    *,
    record: AuthoritativeSession,
    viewer: ViewerContext,
    cursor_codec: SessionCursorCodec,
) -> SessionCheckpointPayload:
    snapshot = record.snapshot_for_viewer(viewer)
    view = snapshot.adapter_session.view_for_context(viewer=viewer)
    projection_hash = view["projection_state_hash"]
    return {
        "visibility_role": viewer.role.value,
        "viewer_player_id": viewer.viewer_player_id,
        "session_revision": snapshot.session_revision,
        "projection_state_hash": projection_hash,
        "event_cursor": cursor_codec.issue(
            session_id=record.session_id,
            viewer=viewer,
            offset=snapshot.event_count,
            visible_sequence=_visible_event_count(snapshot, viewer=viewer),
            session_revision=snapshot.session_revision,
            projection_state_hash=projection_hash,
        ),
    }


def session_metadata_payload(
    *,
    record: AuthoritativeSession,
    viewer: ViewerContext,
    cursor_codec: SessionCursorCodec,
) -> SessionMetadataPayload:
    snapshot = record.snapshot_for_viewer(viewer)
    checkpoint = session_checkpoint(record=record, viewer=viewer, cursor_codec=cursor_codec)
    return record.metadata_payload(
        snapshot=snapshot,
        viewer=viewer,
        lifecycle_status=cast(
            JsonValue,
            redacted_lifecycle_status(snapshot.lifecycle_status, viewer=viewer),
        ),
        projection_state_hash=checkpoint["projection_state_hash"],
        event_cursor=checkpoint["event_cursor"],
    )


def session_event_delta_payload(
    *,
    record: AuthoritativeSession,
    viewer: ViewerContext,
    supplied_cursor: str,
    page_limit: int,
    cursor_codec: SessionCursorCodec,
    retention_limit: int,
) -> SessionEventDeltaPayload:
    limit = validate_page_limit(page_limit)
    retained = validate_retention_limit(retention_limit)
    target = record.snapshot_for_viewer(viewer)
    target_view = target.adapter_session.view_for_context(viewer=viewer)
    target_hash = target_view["projection_state_hash"]
    try:
        cursor = cursor_codec.decode(supplied_cursor)
        cursor_codec.validate_binding(cursor, session_id=record.session_id, viewer=viewer)
        _validate_cursor_position(
            record=record,
            viewer=viewer,
            cursor=cursor,
            target=target,
            retention_limit=retained,
        )
    except CursorValidationError as exc:
        return _resync_payload(
            record=record,
            viewer=viewer,
            target=target,
            target_hash=target_hash,
            supplied_cursor=supplied_cursor,
            reason=exc.reason,
            cursor_codec=cursor_codec,
            retention_limit=retained,
        )
    if cursor.offset == target.event_count:
        if cursor.session_revision != target.session_revision:
            return _resync_payload(
                record=record,
                viewer=viewer,
                target=target,
                target_hash=target_hash,
                supplied_cursor=supplied_cursor,
                reason=CursorResyncReason.REVISION_MISMATCH,
                cursor_codec=cursor_codec,
                retention_limit=retained,
            )
        if cursor.projection_state_hash != target_hash:
            return _resync_payload(
                record=record,
                viewer=viewer,
                target=target,
                target_hash=target_hash,
                supplied_cursor=supplied_cursor,
                reason=CursorResyncReason.PROJECTION_HASH_MISMATCH,
                cursor_codec=cursor_codec,
                retention_limit=retained,
            )
    internal_delta = target.adapter_session.event_page_for_context(
        EventStreamCursor(cursor.offset),
        viewer=viewer,
        visible_limit=limit,
    )
    page_records = internal_delta["events"]
    next_offset = internal_delta["next_cursor"]
    boundary = record.snapshot_at_event_offset(
        offset=next_offset,
        maximum_revision=target.session_revision,
    )
    boundary_view = boundary.adapter_session.view_for_context(viewer=viewer)
    boundary_hash = boundary_view["projection_state_hash"]
    next_cursor = cursor_codec.issue(
        session_id=record.session_id,
        viewer=viewer,
        offset=next_offset,
        visible_sequence=cursor.visible_sequence + len(page_records),
        session_revision=boundary.session_revision,
        projection_state_hash=boundary_hash,
    )
    payload: SessionEventDeltaPayload = {
        "schema_version": EVENT_STREAM_DELTA_SCHEMA_VERSION,
        "session_id": record.session_id,
        "game_id": record.game_id,
        "visibility_role": viewer.role.value,
        "from_revision": cursor.session_revision,
        "to_revision": boundary.session_revision,
        "projection_state_hash": boundary_hash,
        "supplied_cursor": supplied_cursor,
        "next_cursor": next_cursor,
        "has_more": internal_delta["has_more"],
        "resync_required": False,
        "resync_reason": None,
        "command_id": None,
        "retention_limit": retained,
        "events": sequenced_events(
            page_records,
            first_sequence_number=cursor.visible_sequence + 1,
        ),
    }
    validate_json_value(cast(JsonValue, payload))
    return payload


def _validate_cursor_position(
    *,
    record: AuthoritativeSession,
    viewer: ViewerContext,
    cursor: SessionCursor,
    target: SessionRevisionSnapshot,
    retention_limit: int,
) -> None:
    floor = retention_floor(
        event_count=target.event_count,
        retention_limit=retention_limit,
    )
    if cursor.offset < floor:
        raise CursorValidationError(CursorResyncReason.EXPIRED)
    if cursor.offset > target.event_count or cursor.session_revision > target.session_revision:
        raise CursorValidationError(CursorResyncReason.AHEAD)
    visible_sequence = target.adapter_session.visible_event_count_for_context(
        EventStreamCursor(cursor.offset),
        viewer=viewer,
    )
    if cursor.visible_sequence != visible_sequence:
        raise CursorValidationError(CursorResyncReason.PROJECTION_HASH_MISMATCH)
    try:
        cursor_snapshot = record.snapshot(cursor.session_revision)
    except SessionProtocolError as exc:
        raise CursorValidationError(CursorResyncReason.EXPIRED) from exc
    cursor_view = cursor_snapshot.adapter_session.view_for_context(viewer=viewer)
    if cursor.projection_state_hash != cursor_view["projection_state_hash"]:
        raise CursorValidationError(CursorResyncReason.PROJECTION_HASH_MISMATCH)


def _resync_payload(
    *,
    record: AuthoritativeSession,
    viewer: ViewerContext,
    target: SessionRevisionSnapshot,
    target_hash: str,
    supplied_cursor: str,
    reason: CursorResyncReason,
    cursor_codec: SessionCursorCodec,
    retention_limit: int,
) -> SessionEventDeltaPayload:
    next_cursor = cursor_codec.issue(
        session_id=record.session_id,
        viewer=viewer,
        offset=target.event_count,
        visible_sequence=_visible_event_count(target, viewer=viewer),
        session_revision=target.session_revision,
        projection_state_hash=target_hash,
    )
    payload: SessionEventDeltaPayload = {
        "schema_version": EVENT_STREAM_DELTA_SCHEMA_VERSION,
        "session_id": record.session_id,
        "game_id": record.game_id,
        "visibility_role": viewer.role.value,
        "from_revision": target.session_revision,
        "to_revision": target.session_revision,
        "projection_state_hash": target_hash,
        "supplied_cursor": (
            REDACTED_INVALID_CURSOR if reason is CursorResyncReason.MALFORMED else supplied_cursor
        ),
        "next_cursor": next_cursor,
        "has_more": False,
        "resync_required": True,
        "resync_reason": reason.value,
        "command_id": None,
        "retention_limit": retention_limit,
        "events": [],
    }
    validate_json_value(cast(JsonValue, payload))
    return payload


def _visible_event_count(
    snapshot: SessionRevisionSnapshot,
    *,
    viewer: ViewerContext,
) -> int:
    return snapshot.adapter_session.visible_event_count_for_context(
        EventStreamCursor(snapshot.event_count),
        viewer=viewer,
    )


def initial_cursor_for_viewer(
    *,
    record: AuthoritativeSession,
    viewer: ViewerContext,
    cursor_codec: SessionCursorCodec,
) -> str:
    return session_checkpoint(
        record=record,
        viewer=viewer,
        cursor_codec=cursor_codec,
    )["event_cursor"]


__all__ = [
    "SessionEventProtocolError",
    "initial_cursor_for_viewer",
    "session_checkpoint",
    "session_event_delta_payload",
    "session_metadata_payload",
    "session_projection_payload",
]
