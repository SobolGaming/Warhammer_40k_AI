from __future__ import annotations

from dataclasses import dataclass

from warhammer40k_core.engine.decision_request import (
    PARAMETERIZED_DECISION_OPTION_ID,
    DecisionRequest,
)
from warhammer40k_core.engine.decision_result import DecisionResult
from warhammer40k_core.engine.event_log import JsonValue, validate_json_value
from warhammer40k_core.engine.phase import GameLifecycleError


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


def _validate_identifier(field_name: str, value: object) -> str:
    if type(value) is not str:
        raise GameLifecycleError(f"{field_name} must be a string.")
    stripped = value.strip()
    if not stripped:
        raise GameLifecycleError(f"{field_name} must not be empty.")
    return stripped
