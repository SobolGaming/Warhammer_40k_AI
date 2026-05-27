from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
from typing import TYPE_CHECKING, Protocol, Self, TypedDict

from warhammer40k_core.core.ruleset_descriptor import (
    BattlePhaseKind,
    SetupStepKind,
)
from warhammer40k_core.engine.decision_controller import DecisionController
from warhammer40k_core.engine.decision_request import DecisionRequest, DecisionRequestPayload
from warhammer40k_core.engine.event_log import JsonValue, validate_json_value

if TYPE_CHECKING:
    from warhammer40k_core.engine.game_state import GameState

SetupStep = SetupStepKind
BattlePhase = BattlePhaseKind


class GameLifecycleError(ValueError):
    """Raised when lifecycle state or transitions violate CORE V2 invariants."""


class GameLifecycleStage(StrEnum):
    SETUP = "setup"
    BATTLE = "battle"
    COMPLETE = "complete"


class LifecycleStatusKind(StrEnum):
    ADVANCED = "advanced"
    WAITING_FOR_DECISION = "waiting_for_decision"
    TERMINAL = "terminal"
    UNSUPPORTED = "unsupported"


class LifecycleStatusPayload(TypedDict):
    stage: str
    status_kind: str
    decision_request: DecisionRequestPayload | None
    message: str | None
    payload: JsonValue


@dataclass(frozen=True, slots=True)
class LifecycleStatus:
    stage: GameLifecycleStage
    status_kind: LifecycleStatusKind
    decision_request: DecisionRequest | None = None
    message: str | None = None
    payload: JsonValue = None

    def __post_init__(self) -> None:
        object.__setattr__(self, "stage", game_lifecycle_stage_from_token(self.stage))
        object.__setattr__(
            self,
            "status_kind",
            lifecycle_status_kind_from_token(self.status_kind),
        )
        if self.decision_request is not None and type(self.decision_request) is not DecisionRequest:
            raise GameLifecycleError("LifecycleStatus decision_request must be a DecisionRequest.")
        if self.decision_request is not None and (
            self.status_kind is not LifecycleStatusKind.WAITING_FOR_DECISION
        ):
            raise GameLifecycleError(
                "LifecycleStatus decision_request requires waiting_for_decision status."
            )
        if (
            self.status_kind is LifecycleStatusKind.WAITING_FOR_DECISION
            and self.decision_request is None
        ):
            raise GameLifecycleError(
                "LifecycleStatus waiting_for_decision requires a decision_request."
            )
        object.__setattr__(
            self,
            "message",
            _validate_optional_message("LifecycleStatus message", self.message),
        )
        object.__setattr__(self, "payload", validate_json_value(self.payload))

    @classmethod
    def advanced(cls, *, stage: GameLifecycleStage, payload: JsonValue = None) -> Self:
        return cls(stage=stage, status_kind=LifecycleStatusKind.ADVANCED, payload=payload)

    @classmethod
    def waiting_for_decision(
        cls,
        *,
        stage: GameLifecycleStage,
        decision_request: DecisionRequest,
        payload: JsonValue = None,
    ) -> Self:
        return cls(
            stage=stage,
            status_kind=LifecycleStatusKind.WAITING_FOR_DECISION,
            decision_request=decision_request,
            payload=payload,
        )

    @classmethod
    def terminal(
        cls,
        *,
        stage: GameLifecycleStage,
        message: str,
        payload: JsonValue = None,
    ) -> Self:
        return cls(
            stage=stage,
            status_kind=LifecycleStatusKind.TERMINAL,
            message=message,
            payload=payload,
        )

    @classmethod
    def unsupported(
        cls,
        *,
        stage: GameLifecycleStage,
        message: str,
        payload: JsonValue = None,
    ) -> Self:
        return cls(
            stage=stage,
            status_kind=LifecycleStatusKind.UNSUPPORTED,
            message=message,
            payload=payload,
        )

    def to_payload(self) -> LifecycleStatusPayload:
        decision_request = (
            None if self.decision_request is None else self.decision_request.to_payload()
        )
        return {
            "stage": self.stage.value,
            "status_kind": self.status_kind.value,
            "decision_request": decision_request,
            "message": self.message,
            "payload": self.payload,
        }

    @classmethod
    def from_payload(cls, payload: LifecycleStatusPayload) -> Self:
        decision_request_payload = payload["decision_request"]
        decision_request = (
            None
            if decision_request_payload is None
            else DecisionRequest.from_payload(decision_request_payload)
        )
        return cls(
            stage=game_lifecycle_stage_from_token(payload["stage"]),
            status_kind=lifecycle_status_kind_from_token(payload["status_kind"]),
            decision_request=decision_request,
            message=payload["message"],
            payload=payload["payload"],
        )


class PhaseHandler(Protocol):
    @property
    def phase(self) -> BattlePhase:
        """Battle phase handled by this object."""
        ...

    def begin_phase(
        self,
        *,
        state: GameState,
        decisions: DecisionController,
    ) -> LifecycleStatus:
        """Run deterministic phase-start work until a decision or boundary is reached."""
        ...


def game_lifecycle_stage_from_token(token: object) -> GameLifecycleStage:
    if type(token) is GameLifecycleStage:
        return token
    if type(token) is not str:
        raise GameLifecycleError("GameLifecycleStage token must be a string.")
    try:
        return GameLifecycleStage(token)
    except ValueError as exc:
        raise GameLifecycleError(f"Unsupported GameLifecycleStage token: {token}.") from exc


def lifecycle_status_kind_from_token(token: object) -> LifecycleStatusKind:
    if type(token) is LifecycleStatusKind:
        return token
    if type(token) is not str:
        raise GameLifecycleError("LifecycleStatusKind token must be a string.")
    try:
        return LifecycleStatusKind(token)
    except ValueError as exc:
        raise GameLifecycleError(f"Unsupported LifecycleStatusKind token: {token}.") from exc


def _validate_optional_message(field_name: str, value: object | None) -> str | None:
    if value is None:
        return None
    if type(value) is not str:
        raise GameLifecycleError(f"{field_name} must be a string.")
    stripped = value.strip()
    if not stripped:
        raise GameLifecycleError(f"{field_name} must not be empty.")
    return stripped
