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
    component_index: int | None


@dataclass(frozen=True, slots=True)
class DiceRollOverrideRecord:
    decision_id: str
    request_id: str
    source_rule_id: str
    previous_values: tuple[int, ...]
    replacement_value: int
    component_index: int | None = 0

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
        if not previous_values or any(value < 1 for value in previous_values):
            raise DiceRollSpecError("Dice result override requires positive prior values.")
        if type(self.replacement_value) is not int or self.replacement_value < 1:
            raise DiceRollSpecError("Dice result override replacement must be a positive integer.")
        if self.component_index is not None and (
            type(self.component_index) is not int
            or not 0 <= self.component_index < len(previous_values)
        ):
            raise DiceRollSpecError("Dice result override component index is outside the roll.")
        object.__setattr__(self, "previous_values", previous_values)

    def assigned_values(self) -> tuple[int, ...]:
        values = list(self.previous_values)
        if self.component_index is not None:
            values[self.component_index] = self.replacement_value
        return tuple(values)

    def assigned_unmodified_total(self) -> int:
        if self.component_index is None:
            return self.replacement_value
        return sum(self.assigned_values())

    def to_payload(self) -> DiceRollOverrideRecordPayload:
        return {
            "decision_id": self.decision_id,
            "request_id": self.request_id,
            "source_rule_id": self.source_rule_id,
            "previous_values": list(self.previous_values),
            "replacement_value": self.replacement_value,
            "component_index": self.component_index,
        }

    @classmethod
    def from_payload(cls, payload: DiceRollOverrideRecordPayload) -> Self:
        return cls(
            decision_id=payload["decision_id"],
            request_id=payload["request_id"],
            source_rule_id=payload["source_rule_id"],
            previous_values=tuple(payload["previous_values"]),
            replacement_value=payload["replacement_value"],
            component_index=payload["component_index"],
        )
