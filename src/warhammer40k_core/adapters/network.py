from __future__ import annotations

from typing import TypedDict

from warhammer40k_core.adapters.contracts import AdapterGameSession
from warhammer40k_core.adapters.event_stream import EventStreamCursor, EventStreamDeltaPayload
from warhammer40k_core.adapters.projection import GameViewPayload, RulesCatalogViewPayload
from warhammer40k_core.engine.event_log import JsonValue
from warhammer40k_core.engine.phase import LifecycleStatus, LifecycleStatusPayload


class NetworkFiniteSubmissionPayload(TypedDict):
    request_id: str
    option_id: str
    result_id: str


class NetworkParameterizedSubmissionPayload(TypedDict):
    request_id: str
    payload: JsonValue
    result_id: str


def network_status_payload(status: LifecycleStatus) -> LifecycleStatusPayload:
    return status.to_payload()


def network_view_payload(
    session: AdapterGameSession,
    *,
    viewer_player_id: str,
) -> GameViewPayload:
    return session.view(viewer_player_id=viewer_player_id)


def network_rules_catalog_view_payload(session: AdapterGameSession) -> RulesCatalogViewPayload:
    return session.rules_catalog_view()


def network_events_since_payload(
    session: AdapterGameSession,
    cursor: EventStreamCursor,
    *,
    viewer_player_id: str,
) -> EventStreamDeltaPayload:
    return session.events_since(cursor, viewer_player_id=viewer_player_id)


def submit_network_option(
    session: AdapterGameSession,
    submission: NetworkFiniteSubmissionPayload,
) -> LifecycleStatus:
    return session.submit_option(
        request_id=submission["request_id"],
        option_id=submission["option_id"],
        result_id=submission["result_id"],
    )


def submit_network_parameterized_payload(
    session: AdapterGameSession,
    submission: NetworkParameterizedSubmissionPayload,
) -> LifecycleStatus:
    return session.submit_parameterized_payload(
        request_id=submission["request_id"],
        payload=submission["payload"],
        result_id=submission["result_id"],
    )
