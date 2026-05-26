from __future__ import annotations

import re
from collections.abc import Iterable
from dataclasses import dataclass
from typing import Literal, Self, TypedDict


class DiceError(ValueError):
    """Base error for invalid dice domain data."""


class DiceRollSpecError(DiceError):
    """Raised when a dice roll request violates replay-facing invariants."""


type DiceRollSource = Literal["rng", "fixed", "injected"]


class DiceExpressionPayload(TypedDict):
    quantity: int
    sides: int
    modifier: int


class DiceRollSpecPayload(TypedDict):
    expression: DiceExpressionPayload
    reason: str
    roll_type: str
    actor_id: str | None


class DiceRollResultPayload(TypedDict):
    roll_id: str
    spec: DiceRollSpecPayload
    values: list[int]
    total: int
    source: DiceRollSource


class DiceRerollRecordPayload(TypedDict):
    decision_id: str
    request_id: str
    selected_indices: list[int]
    replacement_result: DiceRollResultPayload


class DiceRollStatePayload(TypedDict):
    original_result: DiceRollResultPayload
    current_values: list[int]
    current_total: int
    rerolls: list[DiceRerollRecordPayload]


_LABEL_PARTS = re.compile(r"[\s_]+")


@dataclass(frozen=True, slots=True)
class DiceExpression:
    quantity: int
    sides: int
    modifier: int = 0

    def __post_init__(self) -> None:
        if self.quantity < 1:
            raise DiceRollSpecError("DiceExpression quantity must be at least 1.")
        if self.sides < 2:
            raise DiceRollSpecError("DiceExpression sides must be at least 2.")

    def canonical(self) -> str:
        base = f"{self.quantity}D{self.sides}" if self.quantity != 1 else f"D{self.sides}"
        if self.modifier > 0:
            return f"{base}+{self.modifier}"
        if self.modifier < 0:
            return f"{base}{self.modifier}"
        return base

    def validate_values(self, values: Iterable[int]) -> tuple[int, ...]:
        value_tuple = tuple(values)
        if len(value_tuple) != self.quantity:
            raise DiceRollSpecError("Dice roll value count does not match the expression.")
        for value in value_tuple:
            if type(value) is not int:
                raise DiceRollSpecError("Dice roll values must be integers.")
            if value < 1 or value > self.sides:
                raise DiceRollSpecError("Dice roll value is outside the expression bounds.")
        return value_tuple

    def total(self, values: Iterable[int]) -> int:
        value_tuple = self.validate_values(values)
        return sum(value_tuple) + self.modifier

    def to_payload(self) -> DiceExpressionPayload:
        return {
            "quantity": self.quantity,
            "sides": self.sides,
            "modifier": self.modifier,
        }

    @classmethod
    def from_payload(cls, payload: DiceExpressionPayload) -> Self:
        return cls(
            quantity=payload["quantity"],
            sides=payload["sides"],
            modifier=payload["modifier"],
        )


@dataclass(frozen=True, slots=True)
class DiceRollSpec:
    expression: DiceExpression
    reason: str
    roll_type: str
    actor_id: str | None = None

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "reason",
            _validated_replay_label("reason", self.reason, self.expression),
        )
        object.__setattr__(
            self,
            "roll_type",
            _validated_replay_label("roll_type", self.roll_type, self.expression),
        )
        if self.actor_id is not None and not self.actor_id.strip():
            raise DiceRollSpecError("DiceRollSpec actor_id must not be empty when supplied.")

    def to_payload(self) -> DiceRollSpecPayload:
        return {
            "expression": self.expression.to_payload(),
            "reason": self.reason,
            "roll_type": self.roll_type,
            "actor_id": self.actor_id,
        }

    @classmethod
    def from_payload(cls, payload: DiceRollSpecPayload) -> Self:
        return cls(
            expression=DiceExpression.from_payload(payload["expression"]),
            reason=payload["reason"],
            roll_type=payload["roll_type"],
            actor_id=payload["actor_id"],
        )


@dataclass(frozen=True, slots=True)
class DiceRollResult:
    roll_id: str
    spec: DiceRollSpec
    values: tuple[int, ...]
    total: int
    source: DiceRollSource

    def __post_init__(self) -> None:
        if not self.roll_id.strip():
            raise DiceRollSpecError("DiceRollResult roll_id must not be empty.")
        if self.source not in {"rng", "fixed", "injected"}:
            raise DiceRollSpecError("DiceRollResult source is invalid.")
        value_tuple = self.spec.expression.validate_values(self.values)
        if value_tuple != self.values:
            object.__setattr__(self, "values", value_tuple)
        expected_total = self.spec.expression.total(value_tuple)
        if self.total != expected_total:
            raise DiceRollSpecError("DiceRollResult total does not match values and expression.")

    @classmethod
    def from_values(
        cls,
        *,
        roll_id: str,
        spec: DiceRollSpec,
        values: Iterable[int],
        source: DiceRollSource,
    ) -> Self:
        value_tuple = spec.expression.validate_values(values)
        return cls(
            roll_id=roll_id,
            spec=spec,
            values=value_tuple,
            total=spec.expression.total(value_tuple),
            source=source,
        )

    def to_payload(self) -> DiceRollResultPayload:
        return {
            "roll_id": self.roll_id,
            "spec": self.spec.to_payload(),
            "values": list(self.values),
            "total": self.total,
            "source": self.source,
        }

    @classmethod
    def from_payload(cls, payload: DiceRollResultPayload) -> Self:
        return cls(
            roll_id=payload["roll_id"],
            spec=DiceRollSpec.from_payload(payload["spec"]),
            values=tuple(payload["values"]),
            total=payload["total"],
            source=payload["source"],
        )


@dataclass(frozen=True, slots=True)
class DiceRerollRecord:
    decision_id: str
    request_id: str
    selected_indices: tuple[int, ...]
    replacement_result: DiceRollResult

    def __post_init__(self) -> None:
        if not self.decision_id.strip():
            raise DiceRollSpecError("DiceRerollRecord decision_id must not be empty.")
        if not self.request_id.strip():
            raise DiceRollSpecError("DiceRerollRecord request_id must not be empty.")
        _validate_selected_indices(self.selected_indices)

    def to_payload(self) -> DiceRerollRecordPayload:
        return {
            "decision_id": self.decision_id,
            "request_id": self.request_id,
            "selected_indices": list(self.selected_indices),
            "replacement_result": self.replacement_result.to_payload(),
        }

    @classmethod
    def from_payload(cls, payload: DiceRerollRecordPayload) -> Self:
        return cls(
            decision_id=payload["decision_id"],
            request_id=payload["request_id"],
            selected_indices=tuple(payload["selected_indices"]),
            replacement_result=DiceRollResult.from_payload(payload["replacement_result"]),
        )


@dataclass(frozen=True, slots=True)
class DiceRollState:
    original_result: DiceRollResult
    current_values: tuple[int, ...]
    current_total: int
    rerolls: tuple[DiceRerollRecord, ...] = ()

    def __post_init__(self) -> None:
        value_tuple = self.original_result.spec.expression.validate_values(self.current_values)
        if value_tuple != self.current_values:
            object.__setattr__(self, "current_values", value_tuple)
        expected_total = self.original_result.spec.expression.total(value_tuple)
        if self.current_total != expected_total:
            raise DiceRollSpecError("DiceRollState current_total does not match current_values.")

    @classmethod
    def from_result(cls, result: DiceRollResult) -> Self:
        return cls(
            original_result=result,
            current_values=result.values,
            current_total=result.total,
        )

    def with_reroll(
        self,
        *,
        decision_id: str,
        request_id: str,
        selected_indices: Iterable[int],
        replacement_result: DiceRollResult,
    ) -> DiceRollState:
        indices = _validate_selected_indices(tuple(selected_indices))
        expression = self.original_result.spec.expression
        if replacement_result.spec.expression.quantity != len(indices):
            raise DiceRollSpecError("Reroll replacement count does not match selected dice.")
        if replacement_result.spec.expression.sides != expression.sides:
            raise DiceRollSpecError("Reroll replacement die size does not match original dice.")
        if replacement_result.spec.expression.modifier != 0:
            raise DiceRollSpecError("Reroll replacement expression must not include a modifier.")

        values = list(self.current_values)
        for replacement_index, selected_index in enumerate(indices):
            if selected_index >= len(values):
                raise DiceRollSpecError("Reroll selected index is outside the current dice.")
            values[selected_index] = replacement_result.values[replacement_index]

        current_values = tuple(values)
        record = DiceRerollRecord(
            decision_id=decision_id,
            request_id=request_id,
            selected_indices=indices,
            replacement_result=replacement_result,
        )
        return DiceRollState(
            original_result=self.original_result,
            current_values=current_values,
            current_total=expression.total(current_values),
            rerolls=(*self.rerolls, record),
        )

    def to_payload(self) -> DiceRollStatePayload:
        return {
            "original_result": self.original_result.to_payload(),
            "current_values": list(self.current_values),
            "current_total": self.current_total,
            "rerolls": [record.to_payload() for record in self.rerolls],
        }

    @classmethod
    def from_payload(cls, payload: DiceRollStatePayload) -> Self:
        return cls(
            original_result=DiceRollResult.from_payload(payload["original_result"]),
            current_values=tuple(payload["current_values"]),
            current_total=payload["current_total"],
            rerolls=tuple(DiceRerollRecord.from_payload(record) for record in payload["rerolls"]),
        )


def _validated_replay_label(
    field_name: str,
    label: str,
    expression: DiceExpression,
) -> str:
    stripped = label.strip()
    if not stripped:
        raise DiceRollSpecError(f"DiceRollSpec {field_name} must not be empty.")

    normalized = _LABEL_PARTS.sub("", stripped.casefold())
    expression_label = expression.canonical().casefold()
    generic_labels = {
        expression_label,
        f"roll{expression_label}",
        f"getroll{expression_label}",
        f"getroll({expression_label})",
    }
    if normalized in generic_labels:
        raise DiceRollSpecError(
            f"DiceRollSpec {field_name} must describe the rule reason, not a generic dice label."
        )
    return stripped


def _validate_selected_indices(indices: tuple[int, ...]) -> tuple[int, ...]:
    previous = -1
    for index in indices:
        if type(index) is not int:
            raise DiceRollSpecError("Reroll selected indices must be integers.")
        if index < 0:
            raise DiceRollSpecError("Reroll selected indices must not be negative.")
        if index <= previous:
            raise DiceRollSpecError("Reroll selected indices must be unique and ascending.")
        previous = index
    return indices
