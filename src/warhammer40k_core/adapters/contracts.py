from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, Protocol, Self, runtime_checkable

from warhammer40k_core.core.validation import IdentifierValidator
from warhammer40k_core.engine.decision_request import (
    PARAMETERIZED_DECISION_OPTION_ID,
    DecisionRequest,
)
from warhammer40k_core.engine.decision_result import DecisionResult
from warhammer40k_core.engine.event_log import JsonValue, validate_json_value
from warhammer40k_core.engine.phase import GameLifecycleError

if TYPE_CHECKING:
    from warhammer40k_core.adapters.access_control import ViewerContext
    from warhammer40k_core.adapters.event_stream import (
        EventStreamCursor,
        EventStreamDeltaPayload,
    )
    from warhammer40k_core.adapters.projection import GameViewPayload, RulesCatalogViewPayload
    from warhammer40k_core.adapters.support_profile import SupportProfilePayload
    from warhammer40k_core.engine.game_state import GameConfig
    from warhammer40k_core.engine.phase import LifecycleStatus
    from warhammer40k_core.engine.replay import ReplayArtifactPayload


@runtime_checkable
class AdapterGameSession(Protocol):
    def fork(self) -> Self:
        """Return an isolated copy for an atomic transport transaction."""
        ...

    def start(self, config: GameConfig) -> LifecycleStatus:
        """Start the authoritative lifecycle for one game."""
        ...

    def advance_until_decision_or_terminal(self) -> LifecycleStatus:
        """Advance deterministic engine work until an adapter-visible boundary."""
        ...

    def view(self, *, viewer_player_id: str) -> GameViewPayload:
        """Project a viewer-safe live game view."""
        ...

    def view_for_context(self, *, viewer: ViewerContext) -> GameViewPayload:
        """Project a live view from server-owned authenticated visibility context."""
        ...

    def rules_catalog_view(self) -> RulesCatalogViewPayload:
        """Return the source-hashed static catalog display projection."""
        ...

    def events_since(
        self,
        cursor: EventStreamCursor,
        *,
        viewer_player_id: str,
    ) -> EventStreamDeltaPayload:
        """Return viewer-filtered event records after the supplied cursor."""
        ...

    def events_since_for_context(
        self,
        cursor: EventStreamCursor,
        *,
        viewer: ViewerContext,
    ) -> EventStreamDeltaPayload:
        """Return redacted events from server-owned authenticated visibility context."""
        ...

    def decision_record_count(self) -> int:
        """Return the monotonic count of authoritative decision records."""
        ...

    def submit_option(
        self,
        *,
        request_id: str,
        option_id: str,
        result_id: str,
    ) -> LifecycleStatus:
        """Submit one finite engine-emitted option."""
        ...

    def submit_parameterized_payload(
        self,
        *,
        request_id: str,
        payload: JsonValue,
        result_id: str,
    ) -> LifecycleStatus:
        """Submit a JSON-safe parameterized proposal payload."""
        ...

    def replay_artifact(self, *, artifact_id: str) -> ReplayArtifactPayload:
        """Export a deterministic replay artifact for this session."""
        ...

    def support_profile(self) -> SupportProfilePayload:
        """Describe selected roster/catalog/runtime support for this session."""
        ...


@dataclass(frozen=True, slots=True)
class FiniteOptionSubmission:
    request_id: str
    selected_option_id: str
    result_id: str

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "request_id",
            _validate_identifier("FiniteOptionSubmission request_id", self.request_id),
        )
        object.__setattr__(
            self,
            "selected_option_id",
            _validate_identifier(
                "FiniteOptionSubmission selected_option_id",
                self.selected_option_id,
            ),
        )
        object.__setattr__(
            self,
            "result_id",
            _validate_identifier("FiniteOptionSubmission result_id", self.result_id),
        )

    def to_result(self, request: DecisionRequest) -> DecisionResult:
        if type(request) is not DecisionRequest:
            raise GameLifecycleError("FiniteOptionSubmission requires a DecisionRequest.")
        if request.is_parameterized_submission_request():
            raise GameLifecycleError(
                "FiniteOptionSubmission cannot answer a parameterized request."
            )
        if request.request_id != self.request_id:
            raise GameLifecycleError("FiniteOptionSubmission request_id drift.")
        return DecisionResult.for_request(
            result_id=self.result_id,
            request=request,
            selected_option_id=self.selected_option_id,
        )


@dataclass(frozen=True, slots=True)
class ParameterizedSubmission:
    request_id: str
    payload: JsonValue
    result_id: str

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "request_id",
            _validate_identifier("ParameterizedSubmission request_id", self.request_id),
        )
        object.__setattr__(
            self,
            "payload",
            validate_json_value(self.payload),
        )
        object.__setattr__(
            self,
            "result_id",
            _validate_identifier("ParameterizedSubmission result_id", self.result_id),
        )

    def to_result(self, request: DecisionRequest) -> DecisionResult:
        if type(request) is not DecisionRequest:
            raise GameLifecycleError("ParameterizedSubmission requires a DecisionRequest.")
        if not request.is_parameterized_submission_request():
            raise GameLifecycleError("ParameterizedSubmission requires a parameterized request.")
        if request.request_id != self.request_id:
            raise GameLifecycleError("ParameterizedSubmission request_id drift.")
        return DecisionResult(
            result_id=self.result_id,
            request_id=request.request_id,
            decision_type=request.decision_type,
            actor_id=request.actor_id,
            selected_option_id=PARAMETERIZED_DECISION_OPTION_ID,
            payload=self.payload,
        )


type DecisionSubmission = FiniteOptionSubmission | ParameterizedSubmission


_validate_identifier = IdentifierValidator(GameLifecycleError)
