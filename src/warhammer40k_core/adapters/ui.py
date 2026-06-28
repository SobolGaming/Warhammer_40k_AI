from __future__ import annotations

from typing import TypedDict

from warhammer40k_core.adapters.contracts import AdapterGameSession
from warhammer40k_core.adapters.event_stream import EventStreamCursor, EventStreamDeltaPayload
from warhammer40k_core.adapters.projection import GameViewPayload, RulesCatalogViewPayload
from warhammer40k_core.engine.event_log import JsonValue
from warhammer40k_core.engine.phase import LifecycleStatus


class UiFiniteSubmissionPayload(TypedDict):
    request_id: str
    option_id: str
    result_id: str


class UiParameterizedSubmissionPayload(TypedDict):
    request_id: str
    payload: JsonValue
    result_id: str


def ui_view(
    session: AdapterGameSession,
    *,
    viewer_player_id: str,
) -> GameViewPayload:
    return session.view(viewer_player_id=viewer_player_id)


def ui_rules_catalog_view(session: AdapterGameSession) -> RulesCatalogViewPayload:
    return session.rules_catalog_view()


def ui_events_since(
    session: AdapterGameSession,
    cursor: EventStreamCursor,
    *,
    viewer_player_id: str,
) -> EventStreamDeltaPayload:
    return session.events_since(cursor, viewer_player_id=viewer_player_id)


def submit_ui_option(
    session: AdapterGameSession,
    submission: UiFiniteSubmissionPayload,
) -> LifecycleStatus:
    return session.submit_option(
        request_id=submission["request_id"],
        option_id=submission["option_id"],
        result_id=submission["result_id"],
    )


def submit_ui_parameterized_payload(
    session: AdapterGameSession,
    submission: UiParameterizedSubmissionPayload,
) -> LifecycleStatus:
    return session.submit_parameterized_payload(
        request_id=submission["request_id"],
        payload=submission["payload"],
        result_id=submission["result_id"],
    )
