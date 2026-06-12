from __future__ import annotations

from collections.abc import Callable, Mapping
from dataclasses import dataclass
from enum import StrEnum
from types import MappingProxyType
from typing import Self, TypedDict, cast

from warhammer40k_core.core.army_catalog import ArmyCatalog
from warhammer40k_core.core.ruleset_descriptor import RulesetDescriptor
from warhammer40k_core.engine.decision_controller import DecisionController
from warhammer40k_core.engine.decision_result import DecisionResult
from warhammer40k_core.engine.event_log import JsonValue, validate_json_value
from warhammer40k_core.engine.game_state import GameState
from warhammer40k_core.engine.phase import GameLifecycleError
from warhammer40k_core.engine.stratagems import (
    StratagemDefinition,
    StratagemEligibilityContext,
    StratagemTargetBinding,
    StratagemUseRecord,
)

UNSUPPORTED_STRATAGEM_HANDLER_PREFIX = "unsupported:"


class StratagemHandlerExecutionStatus(StrEnum):
    APPLIED = "applied"
    INVALID = "invalid"
    UNSUPPORTED = "unsupported"


class StratagemHandlerExecutionResultPayload(TypedDict):
    handler_id: str
    status: str
    reason: str | None
    replay_payload: JsonValue


StratagemHandler = Callable[["StratagemHandlerContext"], "StratagemHandlerExecutionResult"]


@dataclass(frozen=True, slots=True)
class StratagemHandlerContext:
    state: GameState
    decisions: DecisionController
    result: DecisionResult
    eligibility_context: StratagemEligibilityContext
    definition: StratagemDefinition
    target_binding: StratagemTargetBinding
    use_record: StratagemUseRecord
    ruleset_descriptor: RulesetDescriptor
    army_catalog: ArmyCatalog

    def __post_init__(self) -> None:
        if type(self.state) is not GameState:
            raise GameLifecycleError("Stratagem handler context requires GameState.")
        if type(self.decisions) is not DecisionController:
            raise GameLifecycleError("Stratagem handler context requires DecisionController.")
        if type(self.result) is not DecisionResult:
            raise GameLifecycleError("Stratagem handler context requires DecisionResult.")
        if type(self.eligibility_context) is not StratagemEligibilityContext:
            raise GameLifecycleError(
                "Stratagem handler context requires StratagemEligibilityContext."
            )
        if type(self.definition) is not StratagemDefinition:
            raise GameLifecycleError("Stratagem handler context requires StratagemDefinition.")
        if type(self.target_binding) is not StratagemTargetBinding:
            raise GameLifecycleError("Stratagem handler context requires StratagemTargetBinding.")
        if type(self.use_record) is not StratagemUseRecord:
            raise GameLifecycleError("Stratagem handler context requires StratagemUseRecord.")
        if type(self.ruleset_descriptor) is not RulesetDescriptor:
            raise GameLifecycleError("Stratagem handler context requires RulesetDescriptor.")
        if type(self.army_catalog) is not ArmyCatalog:
            raise GameLifecycleError("Stratagem handler context requires ArmyCatalog.")


@dataclass(frozen=True, slots=True)
class StratagemHandlerExecutionResult:
    handler_id: str
    status: StratagemHandlerExecutionStatus
    reason: str | None = None
    replay_payload: JsonValue = None

    def __post_init__(self) -> None:
        object.__setattr__(self, "handler_id", _validate_identifier("handler_id", self.handler_id))
        object.__setattr__(
            self,
            "status",
            _stratagem_handler_execution_status_from_token(self.status),
        )
        object.__setattr__(
            self,
            "reason",
            _validate_optional_identifier("reason", self.reason),
        )
        object.__setattr__(self, "replay_payload", validate_json_value(self.replay_payload))
        if self.status is StratagemHandlerExecutionStatus.APPLIED and self.reason is not None:
            raise GameLifecycleError("Applied Stratagem handler result cannot include reason.")
        if self.status is not StratagemHandlerExecutionStatus.APPLIED and self.reason is None:
            raise GameLifecycleError("Non-applied Stratagem handler result requires reason.")

    @classmethod
    def applied(cls, *, handler_id: str, replay_payload: JsonValue = None) -> Self:
        return cls(
            handler_id=handler_id,
            status=StratagemHandlerExecutionStatus.APPLIED,
            replay_payload=replay_payload,
        )

    @classmethod
    def invalid(cls, *, handler_id: str, reason: str, replay_payload: JsonValue = None) -> Self:
        return cls(
            handler_id=handler_id,
            status=StratagemHandlerExecutionStatus.INVALID,
            reason=reason,
            replay_payload=replay_payload,
        )

    @classmethod
    def unsupported(
        cls,
        *,
        handler_id: str,
        reason: str,
        replay_payload: JsonValue = None,
    ) -> Self:
        return cls(
            handler_id=handler_id,
            status=StratagemHandlerExecutionStatus.UNSUPPORTED,
            reason=reason,
            replay_payload=replay_payload,
        )

    def to_payload(self) -> StratagemHandlerExecutionResultPayload:
        return {
            "handler_id": self.handler_id,
            "status": self.status.value,
            "reason": self.reason,
            "replay_payload": self.replay_payload,
        }

    @classmethod
    def from_payload(cls, payload: StratagemHandlerExecutionResultPayload) -> Self:
        return cls(
            handler_id=payload["handler_id"],
            status=_stratagem_handler_execution_status_from_token(payload["status"]),
            reason=payload["reason"],
            replay_payload=payload["replay_payload"],
        )


@dataclass(frozen=True, slots=True)
class StratagemHandlerBinding:
    handler_id: str
    handler: StratagemHandler
    validator: StratagemHandler | None = None

    def __post_init__(self) -> None:
        object.__setattr__(self, "handler_id", _validate_identifier("handler_id", self.handler_id))
        if self.handler_id.startswith(UNSUPPORTED_STRATAGEM_HANDLER_PREFIX):
            raise GameLifecycleError(
                "StratagemHandlerBinding cannot register unsupported handlers."
            )
        if not callable(self.handler):
            raise GameLifecycleError("StratagemHandlerBinding handler must be callable.")
        if self.validator is not None and not callable(self.validator):
            raise GameLifecycleError("StratagemHandlerBinding validator must be callable.")

    def to_summary_payload(self) -> dict[str, JsonValue]:
        return {"handler_id": self.handler_id}


@dataclass(frozen=True, slots=True)
class StratagemHandlerRegistry:
    _handlers: Mapping[str, StratagemHandlerBinding]

    @classmethod
    def from_bindings(cls, bindings: tuple[StratagemHandlerBinding, ...]) -> Self:
        if type(bindings) is not tuple:
            raise GameLifecycleError("StratagemHandlerRegistry bindings must be a tuple.")
        handlers: dict[str, StratagemHandlerBinding] = {}
        for binding in cast(tuple[object, ...], bindings):
            if type(binding) is not StratagemHandlerBinding:
                raise GameLifecycleError(
                    "StratagemHandlerRegistry bindings must contain StratagemHandlerBinding."
                )
            if binding.handler_id in handlers:
                raise GameLifecycleError("StratagemHandlerRegistry handler IDs must be unique.")
            handlers[binding.handler_id] = binding
        return cls(_handlers=MappingProxyType(handlers))

    @classmethod
    def empty(cls) -> Self:
        return cls.from_bindings(())

    def with_handler(
        self,
        *,
        handler_id: str,
        handler: StratagemHandler,
        validator: StratagemHandler | None = None,
    ) -> Self:
        binding = StratagemHandlerBinding(
            handler_id=handler_id,
            handler=handler,
            validator=validator,
        )
        return self.from_bindings((*tuple(self._handlers.values()), binding))

    def has_handler(self, handler_id: str) -> bool:
        return _validate_identifier("handler_id", handler_id) in self._handlers

    def execute(
        self,
        *,
        handler_id: str,
        context: StratagemHandlerContext,
    ) -> StratagemHandlerExecutionResult:
        requested_id = _validate_identifier("handler_id", handler_id)
        if type(context) is not StratagemHandlerContext:
            raise GameLifecycleError("Stratagem handler execution requires a context.")
        binding = self._handlers.get(requested_id)
        if binding is None:
            return StratagemHandlerExecutionResult.unsupported(
                handler_id=requested_id,
                reason="missing_handler",
            )
        result = binding.handler(context)
        if type(result) is not StratagemHandlerExecutionResult:
            raise GameLifecycleError(
                "Stratagem handler must return StratagemHandlerExecutionResult."
            )
        if result.handler_id != requested_id:
            raise GameLifecycleError("Stratagem handler returned handler_id drift.")
        return result

    def validate(
        self,
        *,
        handler_id: str,
        context: StratagemHandlerContext,
    ) -> StratagemHandlerExecutionResult:
        requested_id = _validate_identifier("handler_id", handler_id)
        if type(context) is not StratagemHandlerContext:
            raise GameLifecycleError("Stratagem handler validation requires a context.")
        binding = self._handlers.get(requested_id)
        if binding is None:
            return StratagemHandlerExecutionResult.unsupported(
                handler_id=requested_id,
                reason="missing_handler",
            )
        if binding.validator is None:
            return StratagemHandlerExecutionResult.applied(handler_id=requested_id)
        result = binding.validator(context)
        if type(result) is not StratagemHandlerExecutionResult:
            raise GameLifecycleError(
                "Stratagem handler validator must return StratagemHandlerExecutionResult."
            )
        if result.handler_id != requested_id:
            raise GameLifecycleError("Stratagem handler validator returned handler_id drift.")
        return result

    def all_bindings(self) -> tuple[StratagemHandlerBinding, ...]:
        return tuple(sorted(self._handlers.values(), key=lambda binding: binding.handler_id))

    def to_summary_payload(self) -> list[dict[str, JsonValue]]:
        return [binding.to_summary_payload() for binding in self.all_bindings()]


def _stratagem_handler_execution_status_from_token(
    token: object,
) -> StratagemHandlerExecutionStatus:
    if type(token) is StratagemHandlerExecutionStatus:
        return token
    if type(token) is not str:
        raise GameLifecycleError("StratagemHandlerExecutionStatus token must be a string.")
    try:
        return StratagemHandlerExecutionStatus(token)
    except ValueError as exc:
        raise GameLifecycleError(
            f"Unsupported StratagemHandlerExecutionStatus token: {token}."
        ) from exc


def _validate_identifier(field_name: str, value: object) -> str:
    if type(value) is not str:
        raise GameLifecycleError(f"Stratagem handler {field_name} must be a string.")
    stripped = value.strip()
    if not stripped:
        raise GameLifecycleError(f"Stratagem handler {field_name} must not be empty.")
    return stripped


def _validate_optional_identifier(field_name: str, value: object | None) -> str | None:
    if value is None:
        return None
    return _validate_identifier(field_name, value)
