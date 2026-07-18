from __future__ import annotations

from dataclasses import dataclass
from typing import Self, TypedDict

from warhammer40k_core.core.dice_errors import DiceRollSpecError
from warhammer40k_core.core.dice_validation import validate_identifier, validate_int_tuple


class DiceRollOverrideRecordPayload(TypedDict):
    decision_id: str
    request_id: str
    source_rule_id: str
    previous_values: list[int]
    replacement_value: int


@dataclass(frozen=True, slots=True)
class DiceRollOverrideRecord:
    decision_id: str
    request_id: str
    source_rule_id: str
    previous_values: tuple[int, ...]
    replacement_value: int

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "decision_id",
            validate_identifier("DiceRollOverrideRecord decision_id", self.decision_id),
        )
        object.__setattr__(
            self,
            "request_id",
            validate_identifier("DiceRollOverrideRecord request_id", self.request_id),
        )
        object.__setattr__(
            self,
            "source_rule_id",
            validate_identifier("DiceRollOverrideRecord source_rule_id", self.source_rule_id),
        )
        previous_values = validate_int_tuple(
            "DiceRollOverrideRecord previous_values",
            self.previous_values,
        )
        if len(previous_values) != 1 or not 1 <= previous_values[0] <= 6:
            raise DiceRollSpecError("Dice result override requires one prior D6 value.")
        if type(self.replacement_value) is not int or not 1 <= self.replacement_value <= 6:
            raise DiceRollSpecError("Dice result override replacement must be a D6 value.")
        object.__setattr__(self, "previous_values", previous_values)

    def to_payload(self) -> DiceRollOverrideRecordPayload:
        return {
            "decision_id": self.decision_id,
            "request_id": self.request_id,
            "source_rule_id": self.source_rule_id,
            "previous_values": list(self.previous_values),
            "replacement_value": self.replacement_value,
        }

    @classmethod
    def from_payload(cls, payload: DiceRollOverrideRecordPayload) -> Self:
        return cls(
            decision_id=payload["decision_id"],
            request_id=payload["request_id"],
            source_rule_id=payload["source_rule_id"],
            previous_values=tuple(payload["previous_values"]),
            replacement_value=payload["replacement_value"],
        )
