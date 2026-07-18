from __future__ import annotations

from collections.abc import Callable, Iterable, Mapping
from dataclasses import dataclass
from enum import StrEnum
from types import MappingProxyType

from warhammer40k_core.engine.decision_record import DecisionRecord
from warhammer40k_core.engine.decision_request import DecisionRequest
from warhammer40k_core.engine.decision_result import DecisionResult
from warhammer40k_core.engine.phase import GameLifecycleError, LifecycleStatus

DecisionPreValidator = Callable[[DecisionRequest, DecisionResult], LifecycleStatus | None]
DecisionApplier = Callable[[DecisionRecord, DecisionResult], LifecycleStatus]


class DecisionSubmissionKind(StrEnum):
    FINITE = "finite"
    PARAMETERIZED = "parameterized"


@dataclass(frozen=True, slots=True)
class DecisionDispatchContract:
    decision_type: str
    submission_kind: DecisionSubmissionKind

    def __post_init__(self) -> None:
        if type(self.decision_type) is not str or not self.decision_type:
            raise GameLifecycleError("Decision dispatch contract requires a decision type.")
        if type(self.submission_kind) is not DecisionSubmissionKind:
            raise GameLifecycleError("Decision dispatch contract requires a submission kind.")


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
    _handlers_by_decision_type: Mapping[str, DecisionDispatchHandler]
    _submission_kinds_by_decision_type: Mapping[str, DecisionSubmissionKind]

    @classmethod
    def from_handlers(
        cls,
        handlers: Iterable[DecisionDispatchHandler],
        *,
        submission_kinds_by_decision_type: Mapping[str, DecisionSubmissionKind],
    ) -> DecisionDispatchRegistry:
        handlers_by_decision_type: dict[str, DecisionDispatchHandler] = {}
        for handler in handlers:
            if type(handler) is not DecisionDispatchHandler:
                raise GameLifecycleError("Decision dispatch registry requires handlers.")
            if handler.decision_type in handlers_by_decision_type:
                raise GameLifecycleError("Decision dispatch registry has duplicate decision types.")
            handlers_by_decision_type[handler.decision_type] = handler
        submission_kind_keys = set(submission_kinds_by_decision_type)
        if submission_kind_keys != set(handlers_by_decision_type):
            raise GameLifecycleError(
                "Decision dispatch submission metadata must exactly cover registered types."
            )
        validated_submission_kinds: dict[str, DecisionSubmissionKind] = {}
        for decision_type, submission_kind in submission_kinds_by_decision_type.items():
            if type(decision_type) is not str or not decision_type:
                raise GameLifecycleError(
                    "Decision dispatch submission metadata requires decision types."
                )
            if type(submission_kind) is not DecisionSubmissionKind:
                raise GameLifecycleError(
                    "Decision dispatch submission metadata requires typed kinds."
                )
            validated_submission_kinds[decision_type] = submission_kind
        return cls(
            _handlers_by_decision_type=MappingProxyType(handlers_by_decision_type),
            _submission_kinds_by_decision_type=MappingProxyType(validated_submission_kinds),
        )

    def handler_for(self, decision_type: str) -> DecisionDispatchHandler:
        if type(decision_type) is not str:
            raise GameLifecycleError("Decision dispatch lookup requires a decision type.")
        handler = self._handlers_by_decision_type.get(decision_type)
        if handler is None:
            raise GameLifecycleError("GameLifecycle received an unsupported decision_type.")
        return handler

    def registered_decision_types(self) -> tuple[str, ...]:
        return tuple(sorted(self._handlers_by_decision_type))

    def registered_contracts(self) -> tuple[DecisionDispatchContract, ...]:
        return tuple(
            DecisionDispatchContract(
                decision_type=decision_type,
                submission_kind=self._submission_kinds_by_decision_type[decision_type],
            )
            for decision_type in self.registered_decision_types()
        )

    def validate_request_submission_kind(self, request: DecisionRequest) -> None:
        if type(request) is not DecisionRequest:
            raise GameLifecycleError("Decision dispatch request validation requires a request.")
        expected = self._submission_kinds_by_decision_type.get(request.decision_type)
        if expected is None:
            raise GameLifecycleError("Decision dispatch request type is not registered.")
        actual = (
            DecisionSubmissionKind.PARAMETERIZED
            if request.is_parameterized_submission_request()
            else DecisionSubmissionKind.FINITE
        )
        if actual is not expected:
            raise GameLifecycleError(
                "Decision request submission kind drifted from registered dispatch metadata."
            )


def build_decision_dispatch_registry(
    handlers: Iterable[DecisionDispatchHandler],
    *,
    parameterized_decision_types: frozenset[str],
) -> DecisionDispatchRegistry:
    handler_tuple = tuple(handlers)
    if type(parameterized_decision_types) is not frozenset or any(
        type(decision_type) is not str or not decision_type
        for decision_type in parameterized_decision_types
    ):
        raise GameLifecycleError("Parameterized dispatch metadata must contain decision types.")
    registered_decision_types = {handler.decision_type for handler in handler_tuple}
    if not parameterized_decision_types.issubset(registered_decision_types):
        raise GameLifecycleError("Parameterized dispatch metadata contains unregistered types.")
    return DecisionDispatchRegistry.from_handlers(
        handler_tuple,
        submission_kinds_by_decision_type={
            handler.decision_type: (
                DecisionSubmissionKind.PARAMETERIZED
                if handler.decision_type in parameterized_decision_types
                else DecisionSubmissionKind.FINITE
            )
            for handler in handler_tuple
        },
    )
