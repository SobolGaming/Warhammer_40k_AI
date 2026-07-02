from __future__ import annotations

from collections.abc import Callable, Iterable
from dataclasses import dataclass

from warhammer40k_core.engine.decision_record import DecisionRecord
from warhammer40k_core.engine.decision_request import DecisionRequest
from warhammer40k_core.engine.decision_result import DecisionResult
from warhammer40k_core.engine.phase import GameLifecycleError, LifecycleStatus

DecisionPreValidator = Callable[[DecisionRequest, DecisionResult], LifecycleStatus | None]
DecisionApplier = Callable[[DecisionRecord, DecisionResult], LifecycleStatus]


@dataclass(frozen=True, slots=True)
class DecisionDispatchHandler:
    decision_type: str
    pre_validator: DecisionPreValidator
    applier: DecisionApplier

    def __post_init__(self) -> None:
        if type(self.decision_type) is not str or not self.decision_type:
            raise GameLifecycleError("Decision dispatch handler requires a decision type.")
        if not callable(self.pre_validator):
            raise GameLifecycleError("Decision dispatch handler requires a pre-validator.")
        if not callable(self.applier):
            raise GameLifecycleError("Decision dispatch handler requires an applier.")


@dataclass(frozen=True, slots=True)
class DecisionDispatchRegistry:
    _handlers_by_decision_type: dict[str, DecisionDispatchHandler]

    @classmethod
    def from_handlers(cls, handlers: Iterable[DecisionDispatchHandler]) -> DecisionDispatchRegistry:
        handlers_by_decision_type: dict[str, DecisionDispatchHandler] = {}
        for handler in handlers:
            if type(handler) is not DecisionDispatchHandler:
                raise GameLifecycleError("Decision dispatch registry requires handlers.")
            if handler.decision_type in handlers_by_decision_type:
                raise GameLifecycleError("Decision dispatch registry has duplicate decision types.")
            handlers_by_decision_type[handler.decision_type] = handler
        return cls(_handlers_by_decision_type=handlers_by_decision_type)

    def handler_for(self, decision_type: str) -> DecisionDispatchHandler:
        if type(decision_type) is not str:
            raise GameLifecycleError("Decision dispatch lookup requires a decision type.")
        handler = self._handlers_by_decision_type.get(decision_type)
        if handler is None:
            raise GameLifecycleError("GameLifecycle received an unsupported decision_type.")
        return handler

    def registered_decision_types(self) -> tuple[str, ...]:
        return tuple(sorted(self._handlers_by_decision_type))
