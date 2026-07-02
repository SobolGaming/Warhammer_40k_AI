from __future__ import annotations

import re
from collections.abc import Iterable
from dataclasses import dataclass
from enum import StrEnum
from typing import Literal, Self, TypedDict, cast

from warhammer40k_core.core.attributes import Characteristic, characteristic_from_token
from warhammer40k_core.core.modifiers import (
    RollModifier,
    RollModifierPayload,
    apply_roll_modifiers,
)
from warhammer40k_core.core.validation import IdentifierValidator


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
    reroll_forbidden_rule_ids: list[str]


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


class DiceRollComponentPayload(TypedDict):
    component_id: str
    index: int
    sides: int
    value: int
    rerolled: bool


class DiceRollInstancePayload(TypedDict):
    roll_id: str
    spec: DiceRollSpecPayload
    components: list[DiceRollComponentPayload]
    total: int
    source: DiceRollSource


class D3RollResultPayload(TypedDict):
    source_d6_result: DiceRollResultPayload
    value: int


class RollOffRequestPayload(TypedDict):
    request_id: str
    purpose: str
    player_ids: list[str]
    resolving_decision_id: str


class RollOffPlayerRollPayload(TypedDict):
    player_id: str
    roll_result: DiceRollResultPayload
    value: int


class RollOffRoundPayload(TypedDict):
    round_number: int
    player_rolls: list[RollOffPlayerRollPayload]
    is_tie: bool


class RollOffResultPayload(TypedDict):
    request: RollOffRequestPayload
    rounds: list[RollOffRoundPayload]
    winner_player_id: str


class RerollPermissionPayload(TypedDict):
    source_id: str
    timing_window: str
    owning_player_id: str
    eligible_roll_type: str
    component_selection_policy: str
    allowed_component_selections: list[list[int]] | None


class RerollSelectionPayload(TypedDict):
    indices: list[int]


class RerollDecisionRequestPayload(TypedDict):
    roll_id: str
    roll_type: str
    permission: RerollPermissionPayload
    allowed_selections: list[list[int]]
    current_values: list[int]


class RerollRecordPayload(TypedDict):
    decision_id: str
    request_id: str
    permission: RerollPermissionPayload | None
    selection: RerollSelectionPayload
    original_values: list[int]
    replacement_result: DiceRollResultPayload
    final_values: list[int]
    final_unmodified_value: int


class UnmodifiedRollResultPayload(TypedDict):
    roll_id: str
    roll_type: str
    value: int
    component_values: list[int]


class ModifiedRollResultPayload(TypedDict):
    unmodified: UnmodifiedRollResultPayload
    modifiers: list[RollModifierPayload]
    final_value: int
    applied_modifier_ids: list[str]


class RandomCharacteristicRollPayload(TypedDict):
    characteristic: str
    timing: str
    scope_id: str
    roll_state: DiceRollStatePayload
    value: int


_LABEL_PARTS = re.compile(r"[\s_]+")


class RerollComponentSelectionPolicy(StrEnum):
    WHOLE_ROLL = "whole_roll"
    COMPONENT_SELECTION = "component_selection"


class RandomCharacteristicTiming(StrEnum):
    UNIT_WHEN_SELECTED_TO_MOVE = "unit_when_selected_to_move"
    PER_MODEL = "per_model"
    PER_WEAPON = "per_weapon"
    PER_USE = "per_use"
    PER_ATTACK = "per_attack"


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
class DiceRollExpression(DiceExpression):
    """Explicit Phase 10J name for replay-facing dice expressions."""


@dataclass(frozen=True, slots=True)
class DiceRollSpec:
    expression: DiceExpression
    reason: str
    roll_type: str
    actor_id: str | None = None
    reroll_forbidden_rule_ids: tuple[str, ...] = ()

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
        object.__setattr__(
            self,
            "reroll_forbidden_rule_ids",
            _validate_identifier_tuple(
                "DiceRollSpec reroll_forbidden_rule_ids",
                self.reroll_forbidden_rule_ids,
                min_length=0,
                sort_values=True,
            ),
        )

    def to_payload(self) -> DiceRollSpecPayload:
        return {
            "expression": self.expression.to_payload(),
            "reason": self.reason,
            "roll_type": self.roll_type,
            "actor_id": self.actor_id,
            "reroll_forbidden_rule_ids": list(self.reroll_forbidden_rule_ids),
        }

    @classmethod
    def from_payload(cls, payload: DiceRollSpecPayload) -> Self:
        return cls(
            expression=DiceExpression.from_payload(payload["expression"]),
            reason=payload["reason"],
            roll_type=payload["roll_type"],
            actor_id=payload["actor_id"],
            reroll_forbidden_rule_ids=tuple(payload["reroll_forbidden_rule_ids"]),
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
class DiceRollComponent:
    component_id: str
    index: int
    sides: int
    value: int
    rerolled: bool = False

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "component_id",
            _validate_identifier("DiceRollComponent component_id", self.component_id),
        )
        if type(self.index) is not int:
            raise DiceRollSpecError("DiceRollComponent index must be an integer.")
        if self.index < 0:
            raise DiceRollSpecError("DiceRollComponent index must not be negative.")
        if type(self.sides) is not int:
            raise DiceRollSpecError("DiceRollComponent sides must be an integer.")
        if self.sides < 2:
            raise DiceRollSpecError("DiceRollComponent sides must be at least 2.")
        if type(self.value) is not int:
            raise DiceRollSpecError("DiceRollComponent value must be an integer.")
        if self.value < 1 or self.value > self.sides:
            raise DiceRollSpecError("DiceRollComponent value is outside die bounds.")
        if type(self.rerolled) is not bool:
            raise DiceRollSpecError("DiceRollComponent rerolled must be a bool.")

    def to_payload(self) -> DiceRollComponentPayload:
        return {
            "component_id": self.component_id,
            "index": self.index,
            "sides": self.sides,
            "value": self.value,
            "rerolled": self.rerolled,
        }

    @classmethod
    def from_payload(cls, payload: DiceRollComponentPayload) -> Self:
        return cls(
            component_id=payload["component_id"],
            index=payload["index"],
            sides=payload["sides"],
            value=payload["value"],
            rerolled=payload["rerolled"],
        )


@dataclass(frozen=True, slots=True)
class DiceRollInstance:
    roll_id: str
    spec: DiceRollSpec
    components: tuple[DiceRollComponent, ...]
    total: int
    source: DiceRollSource

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "roll_id",
            _validate_identifier("DiceRollInstance roll_id", self.roll_id),
        )
        if type(self.spec) is not DiceRollSpec:
            raise DiceRollSpecError("DiceRollInstance spec must be a DiceRollSpec.")
        if self.source not in {"rng", "fixed", "injected"}:
            raise DiceRollSpecError("DiceRollInstance source is invalid.")
        components = tuple(self.components)
        if len(components) != self.spec.expression.quantity:
            raise DiceRollSpecError("DiceRollInstance component count must match expression.")
        for expected_index, component in enumerate(components):
            if type(component) is not DiceRollComponent:
                raise DiceRollSpecError(
                    "DiceRollInstance components must contain DiceRollComponent values."
                )
            if component.index != expected_index:
                raise DiceRollSpecError("DiceRollInstance component indexes must be sequential.")
            if component.sides != self.spec.expression.sides:
                raise DiceRollSpecError("DiceRollInstance component sides must match expression.")
        if components != self.components:
            object.__setattr__(self, "components", components)
        expected_total = self.spec.expression.total(component.value for component in components)
        if self.total != expected_total:
            raise DiceRollSpecError("DiceRollInstance total does not match components.")

    @classmethod
    def from_result(cls, result: DiceRollResult) -> Self:
        return cls(
            roll_id=result.roll_id,
            spec=result.spec,
            components=tuple(
                DiceRollComponent(
                    component_id=f"{result.roll_id}:component-{index}",
                    index=index,
                    sides=result.spec.expression.sides,
                    value=value,
                    rerolled=False,
                )
                for index, value in enumerate(result.values)
            ),
            total=result.total,
            source=result.source,
        )

    @classmethod
    def from_state(cls, state: DiceRollState) -> Self:
        rerolled_indices = set(state.rerolled_indices())
        return cls(
            roll_id=state.original_result.roll_id,
            spec=state.original_result.spec,
            components=tuple(
                DiceRollComponent(
                    component_id=f"{state.original_result.roll_id}:component-{index}",
                    index=index,
                    sides=state.original_result.spec.expression.sides,
                    value=value,
                    rerolled=index in rerolled_indices,
                )
                for index, value in enumerate(state.current_values)
            ),
            total=state.current_total,
            source=state.original_result.source,
        )

    def to_payload(self) -> DiceRollInstancePayload:
        return {
            "roll_id": self.roll_id,
            "spec": self.spec.to_payload(),
            "components": [component.to_payload() for component in self.components],
            "total": self.total,
            "source": self.source,
        }

    @classmethod
    def from_payload(cls, payload: DiceRollInstancePayload) -> Self:
        return cls(
            roll_id=payload["roll_id"],
            spec=DiceRollSpec.from_payload(payload["spec"]),
            components=tuple(
                DiceRollComponent.from_payload(component) for component in payload["components"]
            ),
            total=payload["total"],
            source=payload["source"],
        )


@dataclass(frozen=True, slots=True)
class D3RollResult:
    source_d6_result: DiceRollResult
    value: int

    def __post_init__(self) -> None:
        if type(self.source_d6_result) is not DiceRollResult:
            raise DiceRollSpecError("D3RollResult source_d6_result must be a DiceRollResult.")
        expression = self.source_d6_result.spec.expression
        if expression.quantity != 1 or expression.sides != 6 or expression.modifier != 0:
            raise DiceRollSpecError("D3RollResult must be sourced from an unmodified D6 roll.")
        if type(self.value) is not int:
            raise DiceRollSpecError("D3RollResult value must be an integer.")
        expected = (self.source_d6_result.values[0] + 1) // 2
        if self.value != expected:
            raise DiceRollSpecError("D3RollResult value must be rounded up from source D6.")

    @classmethod
    def from_source_d6_result(cls, result: DiceRollResult) -> Self:
        return cls(source_d6_result=result, value=(result.values[0] + 1) // 2)

    def to_payload(self) -> D3RollResultPayload:
        return {
            "source_d6_result": self.source_d6_result.to_payload(),
            "value": self.value,
        }

    @classmethod
    def from_payload(cls, payload: D3RollResultPayload) -> Self:
        return cls(
            source_d6_result=DiceRollResult.from_payload(payload["source_d6_result"]),
            value=payload["value"],
        )


@dataclass(frozen=True, slots=True)
class RollOffRequest:
    request_id: str
    purpose: str
    player_ids: tuple[str, ...]
    resolving_decision_id: str

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "request_id",
            _validate_identifier("RollOffRequest request_id", self.request_id),
        )
        object.__setattr__(
            self,
            "purpose",
            _validate_identifier("RollOffRequest purpose", self.purpose),
        )
        object.__setattr__(
            self,
            "resolving_decision_id",
            _validate_identifier(
                "RollOffRequest resolving_decision_id",
                self.resolving_decision_id,
            ),
        )
        player_ids = _validate_identifier_tuple(
            "RollOffRequest player_ids",
            self.player_ids,
            min_length=2,
            sort_values=False,
        )
        if player_ids != self.player_ids:
            object.__setattr__(self, "player_ids", player_ids)

    def to_payload(self) -> RollOffRequestPayload:
        return {
            "request_id": self.request_id,
            "purpose": self.purpose,
            "player_ids": list(self.player_ids),
            "resolving_decision_id": self.resolving_decision_id,
        }

    @classmethod
    def from_payload(cls, payload: RollOffRequestPayload) -> Self:
        return cls(
            request_id=payload["request_id"],
            purpose=payload["purpose"],
            player_ids=tuple(payload["player_ids"]),
            resolving_decision_id=payload["resolving_decision_id"],
        )


@dataclass(frozen=True, slots=True)
class RollOffPlayerRoll:
    player_id: str
    roll_result: DiceRollResult
    value: int

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "player_id",
            _validate_identifier("RollOffPlayerRoll player_id", self.player_id),
        )
        if type(self.roll_result) is not DiceRollResult:
            raise DiceRollSpecError("RollOffPlayerRoll roll_result must be a DiceRollResult.")
        expression = self.roll_result.spec.expression
        if expression.quantity != 1 or expression.sides != 6 or expression.modifier != 0:
            raise DiceRollSpecError("RollOffPlayerRoll must be one unmodified D6.")
        if self.roll_result.spec.roll_type != "roll_off":
            raise DiceRollSpecError("RollOffPlayerRoll roll_type must be roll_off.")
        if self.roll_result.spec.actor_id != self.player_id:
            raise DiceRollSpecError("RollOffPlayerRoll actor_id must match player_id.")
        if self.value != self.roll_result.total:
            raise DiceRollSpecError("RollOffPlayerRoll value must match roll result total.")

    def to_payload(self) -> RollOffPlayerRollPayload:
        return {
            "player_id": self.player_id,
            "roll_result": self.roll_result.to_payload(),
            "value": self.value,
        }

    @classmethod
    def from_payload(cls, payload: RollOffPlayerRollPayload) -> Self:
        return cls(
            player_id=payload["player_id"],
            roll_result=DiceRollResult.from_payload(payload["roll_result"]),
            value=payload["value"],
        )


@dataclass(frozen=True, slots=True)
class RollOffRound:
    round_number: int
    player_rolls: tuple[RollOffPlayerRoll, ...]

    def __post_init__(self) -> None:
        if type(self.round_number) is not int:
            raise DiceRollSpecError("RollOffRound round_number must be an integer.")
        if self.round_number < 1:
            raise DiceRollSpecError("RollOffRound round_number must be at least 1.")
        rolls = tuple(self.player_rolls)
        if len(rolls) < 2:
            raise DiceRollSpecError("RollOffRound requires at least two player rolls.")
        seen: set[str] = set()
        for roll in rolls:
            if type(roll) is not RollOffPlayerRoll:
                raise DiceRollSpecError(
                    "RollOffRound player_rolls must contain RollOffPlayerRoll values."
                )
            if roll.player_id in seen:
                raise DiceRollSpecError("RollOffRound player_rolls must be unique by player.")
            seen.add(roll.player_id)
        if rolls != self.player_rolls:
            object.__setattr__(self, "player_rolls", rolls)

    @property
    def high_value(self) -> int:
        return max(roll.value for roll in self.player_rolls)

    @property
    def is_tie(self) -> bool:
        return sum(1 for roll in self.player_rolls if roll.value == self.high_value) > 1

    @property
    def winner_player_id(self) -> str | None:
        if self.is_tie:
            return None
        for roll in self.player_rolls:
            if roll.value == self.high_value:
                return roll.player_id
        raise DiceRollSpecError("RollOffRound winner could not be resolved.")

    def to_payload(self) -> RollOffRoundPayload:
        return {
            "round_number": self.round_number,
            "player_rolls": [roll.to_payload() for roll in self.player_rolls],
            "is_tie": self.is_tie,
        }

    @classmethod
    def from_payload(cls, payload: RollOffRoundPayload) -> Self:
        round_result = cls(
            round_number=payload["round_number"],
            player_rolls=tuple(
                RollOffPlayerRoll.from_payload(roll) for roll in payload["player_rolls"]
            ),
        )
        if payload["is_tie"] != round_result.is_tie:
            raise DiceRollSpecError("RollOffRound payload tie status drifted.")
        return round_result


@dataclass(frozen=True, slots=True)
class RollOffResult:
    request: RollOffRequest
    rounds: tuple[RollOffRound, ...]
    winner_player_id: str

    def __post_init__(self) -> None:
        if type(self.request) is not RollOffRequest:
            raise DiceRollSpecError("RollOffResult request must be a RollOffRequest.")
        rounds = tuple(self.rounds)
        if not rounds:
            raise DiceRollSpecError("RollOffResult rounds must not be empty.")
        expected_players = set(self.request.player_ids)
        for expected_round_number, round_result in enumerate(rounds, start=1):
            if type(round_result) is not RollOffRound:
                raise DiceRollSpecError("RollOffResult rounds must contain RollOffRound values.")
            if round_result.round_number != expected_round_number:
                raise DiceRollSpecError("RollOffResult round numbers must be sequential.")
            if {roll.player_id for roll in round_result.player_rolls} != expected_players:
                raise DiceRollSpecError("RollOffResult round player IDs must match request.")
            if round_result is not rounds[-1] and not round_result.is_tie:
                raise DiceRollSpecError("RollOffResult cannot continue after a non-tied round.")
        final_winner = rounds[-1].winner_player_id
        if final_winner is None:
            raise DiceRollSpecError("RollOffResult final round must have a winner.")
        object.__setattr__(
            self,
            "winner_player_id",
            _validate_identifier("RollOffResult winner_player_id", self.winner_player_id),
        )
        if self.winner_player_id != final_winner:
            raise DiceRollSpecError("RollOffResult winner_player_id does not match final round.")
        if rounds != self.rounds:
            object.__setattr__(self, "rounds", rounds)

    def to_payload(self) -> RollOffResultPayload:
        return {
            "request": self.request.to_payload(),
            "rounds": [round_result.to_payload() for round_result in self.rounds],
            "winner_player_id": self.winner_player_id,
        }

    @classmethod
    def from_payload(cls, payload: RollOffResultPayload) -> Self:
        return cls(
            request=RollOffRequest.from_payload(payload["request"]),
            rounds=tuple(
                RollOffRound.from_payload(round_result) for round_result in payload["rounds"]
            ),
            winner_player_id=payload["winner_player_id"],
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
class RerollSelection:
    indices: tuple[int, ...]

    def __post_init__(self) -> None:
        indices = _validate_selected_indices(tuple(self.indices))
        if not indices:
            raise DiceRollSpecError("RerollSelection indices must not be empty.")
        if indices != self.indices:
            object.__setattr__(self, "indices", indices)

    def to_payload(self) -> RerollSelectionPayload:
        return {"indices": list(self.indices)}

    @classmethod
    def from_payload(cls, payload: RerollSelectionPayload) -> Self:
        return cls(indices=tuple(payload["indices"]))


@dataclass(frozen=True, slots=True)
class RerollPermission:
    source_id: str
    timing_window: str
    owning_player_id: str
    eligible_roll_type: str
    component_selection_policy: RerollComponentSelectionPolicy
    allowed_component_selections: tuple[tuple[int, ...], ...] | None = None

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "source_id",
            _validate_identifier("RerollPermission source_id", self.source_id),
        )
        object.__setattr__(
            self,
            "timing_window",
            _validate_identifier("RerollPermission timing_window", self.timing_window),
        )
        object.__setattr__(
            self,
            "owning_player_id",
            _validate_identifier("RerollPermission owning_player_id", self.owning_player_id),
        )
        object.__setattr__(
            self,
            "eligible_roll_type",
            _validate_identifier("RerollPermission eligible_roll_type", self.eligible_roll_type),
        )
        object.__setattr__(
            self,
            "component_selection_policy",
            reroll_component_selection_policy_from_token(self.component_selection_policy),
        )
        selections = None
        if self.allowed_component_selections is not None:
            selections = _validate_selection_tuple(
                self.allowed_component_selections,
                field_name="RerollPermission allowed_component_selections",
            )
        if self.component_selection_policy is RerollComponentSelectionPolicy.WHOLE_ROLL:
            if selections is not None:
                raise DiceRollSpecError(
                    "Whole-roll reroll permissions must not supply component selections."
                )
        elif selections is None:
            raise DiceRollSpecError(
                "Component-selection reroll permissions require explicit selections."
            )
        if selections != self.allowed_component_selections:
            object.__setattr__(self, "allowed_component_selections", selections)

    def legal_selections_for_state(self, state: DiceRollState) -> tuple[tuple[int, ...], ...]:
        if type(state) is not DiceRollState:
            raise DiceRollSpecError("RerollPermission state must be a DiceRollState.")
        if state.original_result.spec.roll_type != self.eligible_roll_type:
            raise DiceRollSpecError("RerollPermission eligible_roll_type does not match roll.")
        already_rerolled = set(state.rerolled_indices())
        if self.component_selection_policy is RerollComponentSelectionPolicy.WHOLE_ROLL:
            selection = tuple(range(len(state.current_values)))
            if any(index in already_rerolled for index in selection):
                raise DiceRollSpecError("RerollPermission cannot reroll a die twice.")
            return (selection,)

        if self.allowed_component_selections is None:
            raise DiceRollSpecError("RerollPermission component selections are missing.")
        validated: list[tuple[int, ...]] = []
        for selection in self.allowed_component_selections:
            for index in selection:
                if index >= len(state.current_values):
                    raise DiceRollSpecError(
                        "RerollPermission component selection index is outside the roll."
                    )
                if index in already_rerolled:
                    raise DiceRollSpecError("RerollPermission cannot reroll a die twice.")
            validated.append(selection)
        return tuple(validated)

    def validate_selection(
        self,
        state: DiceRollState,
        selection: RerollSelection,
    ) -> RerollSelection:
        if type(selection) is not RerollSelection:
            raise DiceRollSpecError("RerollPermission selection must be a RerollSelection.")
        if selection.indices not in self.legal_selections_for_state(state):
            raise DiceRollSpecError("RerollSelection is not legal for this permission.")
        return selection

    def to_payload(self) -> RerollPermissionPayload:
        selections = None
        if self.allowed_component_selections is not None:
            selections = [list(selection) for selection in self.allowed_component_selections]
        return {
            "source_id": self.source_id,
            "timing_window": self.timing_window,
            "owning_player_id": self.owning_player_id,
            "eligible_roll_type": self.eligible_roll_type,
            "component_selection_policy": self.component_selection_policy.value,
            "allowed_component_selections": selections,
        }

    @classmethod
    def from_payload(cls, payload: RerollPermissionPayload) -> Self:
        selections_payload = payload["allowed_component_selections"]
        return cls(
            source_id=payload["source_id"],
            timing_window=payload["timing_window"],
            owning_player_id=payload["owning_player_id"],
            eligible_roll_type=payload["eligible_roll_type"],
            component_selection_policy=reroll_component_selection_policy_from_token(
                payload["component_selection_policy"]
            ),
            allowed_component_selections=(
                None
                if selections_payload is None
                else tuple(tuple(selection) for selection in selections_payload)
            ),
        )


@dataclass(frozen=True, slots=True)
class RerollDecisionRequest:
    roll_id: str
    roll_type: str
    permission: RerollPermission
    allowed_selections: tuple[tuple[int, ...], ...]
    current_values: tuple[int, ...]

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "roll_id",
            _validate_identifier("RerollDecisionRequest roll_id", self.roll_id),
        )
        object.__setattr__(
            self,
            "roll_type",
            _validate_identifier("RerollDecisionRequest roll_type", self.roll_type),
        )
        if type(self.permission) is not RerollPermission:
            raise DiceRollSpecError("RerollDecisionRequest permission must be a RerollPermission.")
        selections = _validate_selection_tuple(
            self.allowed_selections,
            field_name="RerollDecisionRequest allowed_selections",
        )
        if selections != self.allowed_selections:
            object.__setattr__(self, "allowed_selections", selections)
        values = _validate_int_tuple(
            "RerollDecisionRequest current_values",
            self.current_values,
        )
        if values != self.current_values:
            object.__setattr__(self, "current_values", values)

    @classmethod
    def from_state(cls, state: DiceRollState, permission: RerollPermission) -> Self:
        return cls(
            roll_id=state.original_result.roll_id,
            roll_type=state.original_result.spec.roll_type,
            permission=permission,
            allowed_selections=permission.legal_selections_for_state(state),
            current_values=state.current_values,
        )

    def to_payload(self) -> RerollDecisionRequestPayload:
        return {
            "roll_id": self.roll_id,
            "roll_type": self.roll_type,
            "permission": self.permission.to_payload(),
            "allowed_selections": [list(selection) for selection in self.allowed_selections],
            "current_values": list(self.current_values),
        }

    @classmethod
    def from_payload(cls, payload: RerollDecisionRequestPayload) -> Self:
        return cls(
            roll_id=payload["roll_id"],
            roll_type=payload["roll_type"],
            permission=RerollPermission.from_payload(payload["permission"]),
            allowed_selections=tuple(
                tuple(selection) for selection in payload["allowed_selections"]
            ),
            current_values=tuple(payload["current_values"]),
        )


@dataclass(frozen=True, slots=True)
class DiceRollState:
    original_result: DiceRollResult
    current_values: tuple[int, ...]
    current_total: int
    rerolls: tuple[DiceRerollRecord, ...] = ()

    def __post_init__(self) -> None:
        if type(self.original_result) is not DiceRollResult:
            raise DiceRollSpecError("DiceRollState original_result must be a DiceRollResult.")
        rerolls = tuple(self.rerolls)
        for reroll in rerolls:
            if type(reroll) is not DiceRerollRecord:
                raise DiceRollSpecError(
                    "DiceRollState rerolls must contain DiceRerollRecord values."
                )
        if rerolls != self.rerolls:
            object.__setattr__(self, "rerolls", rerolls)
        value_tuple = self.original_result.spec.expression.validate_values(self.current_values)
        if value_tuple != self.current_values:
            object.__setattr__(self, "current_values", value_tuple)
        expected_values = _current_values_after_rerolls(
            self.original_result,
            rerolls,
        )
        if value_tuple != expected_values:
            raise DiceRollSpecError("DiceRollState current_values drifted from reroll records.")
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
        already_rerolled = set(self.rerolled_indices())
        if any(index in already_rerolled for index in indices):
            raise DiceRollSpecError("A die component can be rerolled at most once.")
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

    def rerolled_indices(self) -> tuple[int, ...]:
        rerolled: list[int] = []
        seen: set[int] = set()
        for record in self.rerolls:
            for index in record.selected_indices:
                if index in seen:
                    raise DiceRollSpecError("DiceRollState reroll records contain duplicate dice.")
                seen.add(index)
                rerolled.append(index)
        return tuple(rerolled)

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


@dataclass(frozen=True, slots=True)
class RerollRecord:
    decision_id: str
    request_id: str
    permission: RerollPermission | None
    selection: RerollSelection
    original_values: tuple[int, ...]
    replacement_result: DiceRollResult
    final_values: tuple[int, ...]
    final_unmodified_value: int

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "decision_id",
            _validate_identifier("RerollRecord decision_id", self.decision_id),
        )
        object.__setattr__(
            self,
            "request_id",
            _validate_identifier("RerollRecord request_id", self.request_id),
        )
        if self.permission is not None and type(self.permission) is not RerollPermission:
            raise DiceRollSpecError("RerollRecord permission must be a RerollPermission or None.")
        if type(self.selection) is not RerollSelection:
            raise DiceRollSpecError("RerollRecord selection must be a RerollSelection.")
        original_values = _validate_int_tuple("RerollRecord original_values", self.original_values)
        if original_values != self.original_values:
            object.__setattr__(self, "original_values", original_values)
        final_values = _validate_int_tuple("RerollRecord final_values", self.final_values)
        if final_values != self.final_values:
            object.__setattr__(self, "final_values", final_values)
        if type(self.replacement_result) is not DiceRollResult:
            raise DiceRollSpecError("RerollRecord replacement_result must be a DiceRollResult.")
        if type(self.final_unmodified_value) is not int:
            raise DiceRollSpecError("RerollRecord final_unmodified_value must be an integer.")
        if self.final_unmodified_value != sum(final_values):
            raise DiceRollSpecError(
                "RerollRecord final_unmodified_value must match final value sum."
            )

    def to_payload(self) -> RerollRecordPayload:
        return {
            "decision_id": self.decision_id,
            "request_id": self.request_id,
            "permission": None if self.permission is None else self.permission.to_payload(),
            "selection": self.selection.to_payload(),
            "original_values": list(self.original_values),
            "replacement_result": self.replacement_result.to_payload(),
            "final_values": list(self.final_values),
            "final_unmodified_value": self.final_unmodified_value,
        }

    @classmethod
    def from_payload(cls, payload: RerollRecordPayload) -> Self:
        permission_payload = payload["permission"]
        return cls(
            decision_id=payload["decision_id"],
            request_id=payload["request_id"],
            permission=(
                None
                if permission_payload is None
                else RerollPermission.from_payload(permission_payload)
            ),
            selection=RerollSelection.from_payload(payload["selection"]),
            original_values=tuple(payload["original_values"]),
            replacement_result=DiceRollResult.from_payload(payload["replacement_result"]),
            final_values=tuple(payload["final_values"]),
            final_unmodified_value=payload["final_unmodified_value"],
        )


@dataclass(frozen=True, slots=True)
class UnmodifiedRollResult:
    roll_id: str
    roll_type: str
    value: int
    component_values: tuple[int, ...]

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "roll_id",
            _validate_identifier("UnmodifiedRollResult roll_id", self.roll_id),
        )
        object.__setattr__(
            self,
            "roll_type",
            _validate_identifier("UnmodifiedRollResult roll_type", self.roll_type),
        )
        if type(self.value) is not int:
            raise DiceRollSpecError("UnmodifiedRollResult value must be an integer.")
        component_values = _validate_int_tuple(
            "UnmodifiedRollResult component_values",
            self.component_values,
        )
        if component_values != self.component_values:
            object.__setattr__(self, "component_values", component_values)

    @classmethod
    def from_state(cls, state: DiceRollState) -> Self:
        if type(state) is not DiceRollState:
            raise DiceRollSpecError("UnmodifiedRollResult state must be a DiceRollState.")
        return cls(
            roll_id=state.original_result.roll_id,
            roll_type=state.original_result.spec.roll_type,
            value=state.current_total,
            component_values=state.current_values,
        )

    def to_payload(self) -> UnmodifiedRollResultPayload:
        return {
            "roll_id": self.roll_id,
            "roll_type": self.roll_type,
            "value": self.value,
            "component_values": list(self.component_values),
        }

    @classmethod
    def from_payload(cls, payload: UnmodifiedRollResultPayload) -> Self:
        return cls(
            roll_id=payload["roll_id"],
            roll_type=payload["roll_type"],
            value=payload["value"],
            component_values=tuple(payload["component_values"]),
        )


@dataclass(frozen=True, slots=True)
class ModifiedRollResult:
    unmodified: UnmodifiedRollResult
    modifiers: tuple[RollModifier, ...]
    final_value: int
    applied_modifier_ids: tuple[str, ...]

    def __post_init__(self) -> None:
        if type(self.unmodified) is not UnmodifiedRollResult:
            raise DiceRollSpecError(
                "ModifiedRollResult unmodified must be an UnmodifiedRollResult."
            )
        modifiers = tuple(self.modifiers)
        for modifier in modifiers:
            if type(modifier) is not RollModifier:
                raise DiceRollSpecError("ModifiedRollResult modifiers must contain RollModifier.")
        if modifiers != self.modifiers:
            object.__setattr__(self, "modifiers", modifiers)
        final_value, applied_modifier_ids = apply_roll_modifiers(
            self.unmodified.value,
            modifiers,
        )
        if self.final_value != final_value:
            raise DiceRollSpecError("ModifiedRollResult final_value does not match modifiers.")
        if self.applied_modifier_ids != applied_modifier_ids:
            raise DiceRollSpecError(
                "ModifiedRollResult applied_modifier_ids do not match modifiers."
            )

    @classmethod
    def from_unmodified(
        cls,
        unmodified: UnmodifiedRollResult,
        *,
        modifiers: Iterable[RollModifier] = (),
    ) -> Self:
        modifier_tuple = tuple(modifiers)
        if unmodified.roll_type == "roll_off" and modifier_tuple:
            raise DiceRollSpecError("Roll-off results cannot be modified.")
        final_value, applied_modifier_ids = apply_roll_modifiers(
            unmodified.value,
            modifier_tuple,
        )
        return cls(
            unmodified=unmodified,
            modifiers=modifier_tuple,
            final_value=final_value,
            applied_modifier_ids=applied_modifier_ids,
        )

    def to_payload(self) -> ModifiedRollResultPayload:
        return {
            "unmodified": self.unmodified.to_payload(),
            "modifiers": [modifier.to_payload() for modifier in self.modifiers],
            "final_value": self.final_value,
            "applied_modifier_ids": list(self.applied_modifier_ids),
        }

    @classmethod
    def from_payload(cls, payload: ModifiedRollResultPayload) -> Self:
        return cls(
            unmodified=UnmodifiedRollResult.from_payload(payload["unmodified"]),
            modifiers=tuple(
                RollModifier.from_payload(modifier) for modifier in payload["modifiers"]
            ),
            final_value=payload["final_value"],
            applied_modifier_ids=tuple(payload["applied_modifier_ids"]),
        )


@dataclass(frozen=True, slots=True)
class RandomCharacteristicRoll:
    characteristic: Characteristic
    timing: RandomCharacteristicTiming
    scope_id: str
    roll_state: DiceRollState
    value: int

    def __post_init__(self) -> None:
        object.__setattr__(self, "characteristic", _validate_characteristic(self.characteristic))
        object.__setattr__(self, "timing", random_characteristic_timing_from_token(self.timing))
        object.__setattr__(
            self,
            "scope_id",
            _validate_identifier("RandomCharacteristicRoll scope_id", self.scope_id),
        )
        if type(self.roll_state) is not DiceRollState:
            raise DiceRollSpecError("RandomCharacteristicRoll roll_state must be a DiceRollState.")
        if type(self.value) is not int:
            raise DiceRollSpecError("RandomCharacteristicRoll value must be an integer.")
        if self.value != self.roll_state.current_total:
            raise DiceRollSpecError("RandomCharacteristicRoll value must match roll total.")
        if (
            self.timing is RandomCharacteristicTiming.UNIT_WHEN_SELECTED_TO_MOVE
            and self.characteristic is not Characteristic.MOVEMENT
        ):
            raise DiceRollSpecError("Unit move random timing is only valid for Movement.")

    def to_payload(self) -> RandomCharacteristicRollPayload:
        return {
            "characteristic": self.characteristic.value,
            "timing": self.timing.value,
            "scope_id": self.scope_id,
            "roll_state": self.roll_state.to_payload(),
            "value": self.value,
        }

    @classmethod
    def from_payload(cls, payload: RandomCharacteristicRollPayload) -> Self:
        return cls(
            characteristic=characteristic_from_token(payload["characteristic"]),
            timing=random_characteristic_timing_from_token(payload["timing"]),
            scope_id=payload["scope_id"],
            roll_state=DiceRollState.from_payload(payload["roll_state"]),
            value=payload["value"],
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


def _current_values_after_rerolls(
    original_result: DiceRollResult,
    rerolls: tuple[DiceRerollRecord, ...],
) -> tuple[int, ...]:
    values = list(original_result.values)
    rerolled_indices: set[int] = set()
    expression = original_result.spec.expression
    for record in rerolls:
        indices = _validate_selected_indices(record.selected_indices)
        replacement_expression = record.replacement_result.spec.expression
        if replacement_expression.quantity != len(indices):
            raise DiceRollSpecError("Reroll replacement count does not match selected dice.")
        if replacement_expression.sides != expression.sides:
            raise DiceRollSpecError("Reroll replacement die size does not match original dice.")
        if replacement_expression.modifier != 0:
            raise DiceRollSpecError("Reroll replacement expression must not include a modifier.")
        for replacement_index, selected_index in enumerate(indices):
            if selected_index >= len(values):
                raise DiceRollSpecError("Reroll selected index is outside the current dice.")
            if selected_index in rerolled_indices:
                raise DiceRollSpecError("A die component can be rerolled at most once.")
            values[selected_index] = record.replacement_result.values[replacement_index]
            rerolled_indices.add(selected_index)
    return tuple(values)


def reroll_component_selection_policy_from_token(
    token: object,
) -> RerollComponentSelectionPolicy:
    if type(token) is RerollComponentSelectionPolicy:
        return token
    if type(token) is not str:
        raise DiceRollSpecError("RerollComponentSelectionPolicy token must be a string.")
    try:
        return RerollComponentSelectionPolicy(token)
    except ValueError as exc:
        raise DiceRollSpecError(
            f"Unsupported reroll component selection policy token: {token}."
        ) from exc


def random_characteristic_timing_from_token(token: object) -> RandomCharacteristicTiming:
    if type(token) is RandomCharacteristicTiming:
        return token
    if type(token) is not str:
        raise DiceRollSpecError("RandomCharacteristicTiming token must be a string.")
    try:
        return RandomCharacteristicTiming(token)
    except ValueError as exc:
        raise DiceRollSpecError(
            f"Unsupported random characteristic timing token: {token}."
        ) from exc


def _validate_characteristic(characteristic: object) -> Characteristic:
    if type(characteristic) is not Characteristic:
        raise DiceRollSpecError("Expected a Characteristic.")
    return characteristic


_validate_identifier = IdentifierValidator(DiceRollSpecError)


def _validate_identifier_tuple(
    field_name: str,
    values: object,
    *,
    min_length: int,
    sort_values: bool,
) -> tuple[str, ...]:
    if type(values) is not tuple:
        raise DiceRollSpecError(f"{field_name} must be a tuple.")
    identifiers: list[str] = []
    seen: set[str] = set()
    for value in cast(tuple[object, ...], values):
        identifier = _validate_identifier(f"{field_name} value", value)
        if identifier in seen:
            raise DiceRollSpecError(f"{field_name} must not contain duplicate IDs.")
        seen.add(identifier)
        identifiers.append(identifier)
    if len(identifiers) < min_length:
        raise DiceRollSpecError(f"{field_name} must contain at least {min_length} values.")
    if sort_values:
        return tuple(sorted(identifiers))
    return tuple(identifiers)


def _validate_int_tuple(field_name: str, values: object) -> tuple[int, ...]:
    if type(values) is not tuple:
        raise DiceRollSpecError(f"{field_name} must be a tuple.")
    validated: list[int] = []
    for value in cast(tuple[object, ...], values):
        if type(value) is not int:
            raise DiceRollSpecError(f"{field_name} must contain integers.")
        validated.append(value)
    return tuple(validated)


def _validate_selection_tuple(
    selections: object,
    *,
    field_name: str,
) -> tuple[tuple[int, ...], ...]:
    if type(selections) is not tuple:
        raise DiceRollSpecError(f"{field_name} must be a tuple.")
    validated: list[tuple[int, ...]] = []
    seen: set[tuple[int, ...]] = set()
    for selection in cast(tuple[object, ...], selections):
        if type(selection) is not tuple:
            raise DiceRollSpecError(f"{field_name} must contain tuple selections.")
        indices = _validate_selected_indices(cast(tuple[int, ...], selection))
        if not indices:
            raise DiceRollSpecError(f"{field_name} must not contain empty selections.")
        if indices in seen:
            raise DiceRollSpecError(f"{field_name} must not contain duplicate selections.")
        seen.add(indices)
        validated.append(indices)
    if not validated:
        raise DiceRollSpecError(f"{field_name} must not be empty.")
    return tuple(sorted(validated))
