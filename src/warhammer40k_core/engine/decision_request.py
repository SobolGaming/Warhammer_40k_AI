from __future__ import annotations

from dataclasses import dataclass
from typing import Self, TypedDict, cast

from warhammer40k_core.engine.event_log import JsonValue, canonical_json, validate_json_value


class DecisionError(ValueError):
    """Raised when a decision request, result, queue, controller, or record is invalid."""


PARAMETERIZED_DECISION_OPTION_ID = "submit_parameterized_payload"
PARAMETERIZED_DECISION_OPTION_PAYLOAD: JsonValue = {"submission_kind": "parameterized"}


class DecisionOptionPayload(TypedDict):
    option_id: str
    label: str
    payload: JsonValue


class DecisionRequestPayload(TypedDict):
    request_id: str
    decision_type: str
    actor_id: str | None
    payload: JsonValue
    options: list[DecisionOptionPayload]


@dataclass(frozen=True, slots=True)
class DecisionOption:
    option_id: str
    label: str
    payload: JsonValue = None

    def __post_init__(self) -> None:
        object.__setattr__(
            self, "option_id", _validate_identifier("DecisionOption option_id", self.option_id)
        )
        object.__setattr__(self, "label", _validate_identifier("DecisionOption label", self.label))
        object.__setattr__(self, "payload", validate_json_value(self.payload))

    def to_payload(self) -> DecisionOptionPayload:
        return {
            "option_id": self.option_id,
            "label": self.label,
            "payload": self.payload,
        }

    @classmethod
    def from_payload(cls, payload: DecisionOptionPayload) -> Self:
        return cls(
            option_id=payload["option_id"],
            label=payload["label"],
            payload=payload["payload"],
        )


@dataclass(frozen=True, slots=True)
class DecisionRequest:
    request_id: str
    decision_type: str
    actor_id: str | None
    payload: JsonValue
    options: tuple[DecisionOption, ...]

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "request_id",
            _validate_identifier("DecisionRequest request_id", self.request_id),
        )
        object.__setattr__(
            self,
            "decision_type",
            _validate_identifier("DecisionRequest decision_type", self.decision_type),
        )
        object.__setattr__(
            self,
            "actor_id",
            _validate_optional_identifier("DecisionRequest actor_id", self.actor_id),
        )
        object.__setattr__(self, "payload", validate_json_value(self.payload))
        options = _validate_decision_options(self.options)
        if options != self.options:
            object.__setattr__(self, "options", options)

    def history_token(self) -> str:
        return canonical_json(self.to_payload())

    def is_parameterized_submission_request(self) -> bool:
        return self.options == (parameterized_decision_option(),)

    def option_by_id(self, option_id: object) -> DecisionOption:
        requested_id = _validate_identifier("DecisionRequest option_id", option_id)
        for option in self.options:
            if option.option_id == requested_id:
                return option
        raise DecisionError("DecisionRequest option_id is not in the finite action space.")

    def to_payload(self) -> DecisionRequestPayload:
        return {
            "request_id": self.request_id,
            "decision_type": self.decision_type,
            "actor_id": self.actor_id,
            "payload": self.payload,
            "options": [option.to_payload() for option in self.options],
        }

    @classmethod
    def from_payload(cls, payload: DecisionRequestPayload) -> Self:
        return cls(
            request_id=payload["request_id"],
            decision_type=payload["decision_type"],
            actor_id=payload["actor_id"],
            payload=payload["payload"],
            options=tuple(DecisionOption.from_payload(option) for option in payload["options"]),
        )


def parameterized_decision_option() -> DecisionOption:
    return DecisionOption(
        option_id=PARAMETERIZED_DECISION_OPTION_ID,
        label="Submit Parameterized Payload",
        payload=PARAMETERIZED_DECISION_OPTION_PAYLOAD,
    )


def _validate_decision_options(options: object) -> tuple[DecisionOption, ...]:
    if type(options) is not tuple:
        raise DecisionError("DecisionRequest options must be a tuple.")
    if not options:
        raise DecisionError("DecisionRequest options must not be empty.")

    option_values = cast(tuple[object, ...], options)
    validated = tuple(_validate_decision_option(option) for option in option_values)
    seen: set[str] = set()
    for option in validated:
        if option.option_id in seen:
            raise DecisionError("DecisionRequest options must not contain duplicate IDs.")
        seen.add(option.option_id)
    return tuple(sorted(validated, key=lambda option: option.option_id))


def _validate_decision_option(option: object) -> DecisionOption:
    if type(option) is not DecisionOption:
        raise DecisionError("DecisionRequest options must contain DecisionOption values.")
    return option


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
