"""AdapterGameSession whose complete authority lives in one Linux executor."""

from __future__ import annotations

from typing import Self, cast

from warhammer40k_core.adapters.access_control import ViewerContext
from warhammer40k_core.adapters.contracts import (
    AdapterGameSession,
    AdapterSessionHistoryPayload,
    AdapterSessionIdentityPayload,
)
from warhammer40k_core.adapters.event_stream import (
    EventStreamCursor,
    EventStreamDeltaPayload,
    EventStreamPagePayload,
)
from warhammer40k_core.adapters.execution_profile import ExecutionProfileError
from warhammer40k_core.adapters.linux_authority_transport import LinuxAuthority
from warhammer40k_core.adapters.numerical_policy import NumericalPolicyConfiguration
from warhammer40k_core.adapters.projection import GameViewPayload, RulesCatalogViewPayload
from warhammer40k_core.adapters.support_profile import SupportProfilePayload
from warhammer40k_core.engine.event_log import JsonValue, validate_json_value
from warhammer40k_core.engine.game_state import GameConfig
from warhammer40k_core.engine.phase import LifecycleStatus, LifecycleStatusPayload
from warhammer40k_core.engine.replay import ReplayArtifactPayload


def viewer_payload(viewer: ViewerContext) -> JsonValue:
    # The caller is the trusted adapter/server, not a network end user. Preserve
    # the complete authenticated role policy, including custom spectator delay.
    from dataclasses import asdict

    return validate_json_value(asdict(viewer))


class LinuxGameSession(AdapterGameSession):
    def __init__(self, authority: LinuxAuthority, session_id: str) -> None:
        self._authority = authority
        self._session_id = session_id
        authority.register_session(session_id, self)

    @classmethod
    def from_authority_result(cls, authority: LinuxAuthority, result: JsonValue) -> Self:
        if not isinstance(result, str) or not result:
            raise ExecutionProfileError("Linux authority did not return a session identity.")
        return cls(authority, result)

    def _call(self, operation: str, **arguments: JsonValue) -> JsonValue:
        return self._authority.call(self._session_id, operation, arguments)

    @property
    def numerical_policy(self) -> NumericalPolicyConfiguration:
        return self._authority.numerical_policy

    def _status(self, operation: str, **arguments: JsonValue) -> LifecycleStatus:
        return LifecycleStatus.from_payload(
            cast(LifecycleStatusPayload, self._call(operation, **arguments))
        )

    def fork(self) -> Self:
        with self._authority.session_transaction():
            return type(self).from_authority_result(self._authority, self._call("fork"))

    def to_persistence_payload(self) -> JsonValue:
        return self._call("to_persistence_payload")

    def authoritative_identity_payload(self) -> AdapterSessionIdentityPayload:
        return cast(AdapterSessionIdentityPayload, self._call("authoritative_identity_payload"))

    def authoritative_history_payload(self) -> AdapterSessionHistoryPayload:
        return cast(AdapterSessionHistoryPayload, self._call("authoritative_history_payload"))

    def start(self, config: GameConfig) -> LifecycleStatus:
        return self._status("start", config=validate_json_value(config.to_payload()))

    def advance_until_decision_or_terminal(self) -> LifecycleStatus:
        return self._status("advance_until_decision_or_terminal")

    def view(self, *, viewer_player_id: str) -> GameViewPayload:
        return cast(GameViewPayload, self._call("view", viewer_player_id=viewer_player_id))

    def view_for_context(self, *, viewer: ViewerContext) -> GameViewPayload:
        return cast(GameViewPayload, self._call("view_for_context", viewer=viewer_payload(viewer)))

    def rules_catalog_view(self) -> RulesCatalogViewPayload:
        return cast(RulesCatalogViewPayload, self._call("rules_catalog_view"))

    def events_since(
        self, cursor: EventStreamCursor, *, viewer_player_id: str
    ) -> EventStreamDeltaPayload:
        return cast(
            EventStreamDeltaPayload,
            self._call("events_since", cursor=cursor.value, viewer_player_id=viewer_player_id),
        )

    def events_since_for_context(
        self, cursor: EventStreamCursor, *, viewer: ViewerContext
    ) -> EventStreamDeltaPayload:
        return cast(
            EventStreamDeltaPayload,
            self._call(
                "events_since_for_context", cursor=cursor.value, viewer=viewer_payload(viewer)
            ),
        )

    def event_page_for_context(
        self, cursor: EventStreamCursor, *, viewer: ViewerContext, visible_limit: int
    ) -> EventStreamPagePayload:
        return cast(
            EventStreamPagePayload,
            self._call(
                "event_page_for_context",
                cursor=cursor.value,
                viewer=viewer_payload(viewer),
                visible_limit=visible_limit,
            ),
        )

    def visible_event_count_for_context(
        self, cursor: EventStreamCursor, *, viewer: ViewerContext
    ) -> int:
        return self._integer(
            "visible_event_count_for_context", cursor=cursor.value, viewer=viewer_payload(viewer)
        )

    def _integer(self, operation: str, **arguments: JsonValue) -> int:
        result = self._call(operation, **arguments)
        if type(result) is not int or result < 0:
            raise ExecutionProfileError("Linux authority returned an invalid count.")
        return result

    def event_record_count(self) -> int:
        return self._integer("event_record_count")

    def authoritative_event_page_for_context(
        self, cursor: EventStreamCursor, *, viewer: ViewerContext, visible_limit: int
    ) -> EventStreamPagePayload:
        return cast(
            EventStreamPagePayload,
            self._call(
                "authoritative_event_page_for_context",
                cursor=cursor.value,
                viewer=viewer_payload(viewer),
                visible_limit=visible_limit,
            ),
        )

    def authoritative_visible_event_prefix_counts(
        self, *, viewer: ViewerContext
    ) -> tuple[int, ...]:
        result = self._call(
            "authoritative_visible_event_prefix_counts", viewer=viewer_payload(viewer)
        )
        if not isinstance(result, list) or any(
            type(item) is not int or item < 0 for item in result
        ):
            raise ExecutionProfileError("Linux authority returned invalid prefix counts.")
        return tuple(cast(list[int], result))

    def status_for_context(self, status: LifecycleStatus, *, viewer: ViewerContext) -> JsonValue:
        return self._call(
            "status_for_context",
            status=validate_json_value(status.to_payload()),
            viewer=viewer_payload(viewer),
        )

    def decision_record_count(self) -> int:
        return self._integer("decision_record_count")

    def submit_option(self, *, request_id: str, option_id: str, result_id: str) -> LifecycleStatus:
        return self._status(
            "submit_option", request_id=request_id, option_id=option_id, result_id=result_id
        )

    def submit_parameterized_payload(
        self, *, request_id: str, payload: JsonValue, result_id: str
    ) -> LifecycleStatus:
        return self._status(
            "submit_parameterized_payload",
            request_id=request_id,
            payload=payload,
            result_id=result_id,
        )

    def submit_viewer_option(
        self, *, viewer: ViewerContext, request_id: str, option_id: str, result_id: str
    ) -> LifecycleStatus:
        return self._status(
            "submit_viewer_option",
            viewer=viewer_payload(viewer),
            request_id=request_id,
            option_id=option_id,
            result_id=result_id,
        )

    def submit_viewer_parameterized_payload(
        self, *, viewer: ViewerContext, request_id: str, payload: JsonValue, result_id: str
    ) -> LifecycleStatus:
        return self._status(
            "submit_viewer_parameterized_payload",
            viewer=viewer_payload(viewer),
            request_id=request_id,
            payload=payload,
            result_id=result_id,
        )

    def replay_artifact(self, *, artifact_id: str) -> ReplayArtifactPayload:
        return cast(ReplayArtifactPayload, self._call("replay_artifact", artifact_id=artifact_id))

    def support_profile(self) -> SupportProfilePayload:
        return cast(SupportProfilePayload, self._call("support_profile"))

    def verify_replay(self, *, artifact_id: str) -> JsonValue:
        """Run the existing exact ReplayRunner inside this same executor."""
        return self._call("verify_replay", artifact_id=artifact_id)

    def profiled_replay_artifact(self, *, artifact_id: str) -> JsonValue:
        return self._call("profiled_replay_artifact", artifact_id=artifact_id)
