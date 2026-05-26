from __future__ import annotations

from dataclasses import dataclass
from typing import Self, TypedDict

from warhammer40k_core.engine.decision_request import DecisionError, DecisionRequest
from warhammer40k_core.engine.event_log import JsonValue, canonical_json, validate_json_value


class DecisionResultPayload(TypedDict):
    result_id: str
    request_id: str
    decision_type: str
    actor_id: str | None
    selected_option_id: str
    payload: JsonValue


@dataclass(frozen=True, slots=True)
class DecisionResult:
    result_id: str
    request_id: str
    decision_type: str
    actor_id: str | None
    selected_option_id: str
    payload: JsonValue

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "result_id",
            _validate_identifier("DecisionResult result_id", self.result_id),
        )
        object.__setattr__(
            self,
            "request_id",
            _validate_identifier("DecisionResult request_id", self.request_id),
        )
        object.__setattr__(
            self,
            "decision_type",
            _validate_identifier("DecisionResult decision_type", self.decision_type),
        )
        object.__setattr__(
            self,
            "actor_id",
            _validate_optional_identifier("DecisionResult actor_id", self.actor_id),
        )
        object.__setattr__(
            self,
            "selected_option_id",
            _validate_identifier("DecisionResult selected_option_id", self.selected_option_id),
        )
        object.__setattr__(self, "payload", validate_json_value(self.payload))

    @classmethod
    def for_request(
        cls,
        *,
        result_id: str,
        request: DecisionRequest,
        selected_option_id: str,
    ) -> Self:
        option = request.option_by_id(selected_option_id)
        return cls(
            result_id=result_id,
            request_id=request.request_id,
            decision_type=request.decision_type,
            actor_id=request.actor_id,
            selected_option_id=option.option_id,
            payload=option.payload,
        )

    def validate_for_request(self, request: DecisionRequest) -> None:
        if self.request_id != request.request_id:
            raise DecisionError("DecisionResult request_id does not match request.")
        if self.decision_type != request.decision_type:
            raise DecisionError("DecisionResult decision_type does not match request.")
        if self.actor_id != request.actor_id:
            raise DecisionError("DecisionResult actor_id does not match request.")
        selected_option = request.option_by_id(self.selected_option_id)
        if self.payload != selected_option.payload:
            raise DecisionError("DecisionResult payload must match the selected option payload.")

    def history_token(self) -> str:
        return canonical_json(self.to_payload())

    def to_payload(self) -> DecisionResultPayload:
        return {
            "result_id": self.result_id,
            "request_id": self.request_id,
            "decision_type": self.decision_type,
            "actor_id": self.actor_id,
            "selected_option_id": self.selected_option_id,
            "payload": self.payload,
        }

    @classmethod
    def from_payload(cls, payload: DecisionResultPayload) -> Self:
        return cls(
            result_id=payload["result_id"],
            request_id=payload["request_id"],
            decision_type=payload["decision_type"],
            actor_id=payload["actor_id"],
            selected_option_id=payload["selected_option_id"],
            payload=payload["payload"],
        )


def _validate_identifier(field_name: str, value: object) -> str:
    if type(value) is not str:
        raise DecisionError(f"{field_name} must be a string.")
    stripped = value.strip()
    if not stripped:
        raise DecisionError(f"{field_name} must not be empty.")
    return stripped


def _validate_optional_identifier(field_name: str, value: object | None) -> str | None:
    if value is None:
        return None
    return _validate_identifier(field_name, value)
