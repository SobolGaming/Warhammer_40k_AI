from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass
from typing import Self, TypedDict

from warhammer40k_core.core import dice_validation as _dice_validation
from warhammer40k_core.core.dice import DiceRollState
from warhammer40k_core.core.dice_errors import DiceRollSpecError
from warhammer40k_core.core.modifiers import (
    RollModifier,
    RollModifierPayload,
    resolve_roll_modifiers,
)


class UnmodifiedRollResultPayload(TypedDict):
    roll_id: str
    roll_type: str
    value: int
    component_values: list[int]


class ModifiedRollResultPayload(TypedDict):
    unmodified: UnmodifiedRollResultPayload
    intrinsic_offset: int
    modifiers: list[RollModifierPayload]
    unbounded_value: int
    modified_value: int
    final_value: int
    applied_modifier_ids: list[str]


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
            _dice_validation.validate_identifier("UnmodifiedRollResult roll_id", self.roll_id),
        )
        object.__setattr__(
            self,
            "roll_type",
            _dice_validation.validate_identifier("UnmodifiedRollResult roll_type", self.roll_type),
        )
        if type(self.value) is not int:
            raise DiceRollSpecError("UnmodifiedRollResult value must be an integer.")
        component_values = _dice_validation.validate_int_tuple(
            "UnmodifiedRollResult component_values",
            self.component_values,
        )
        if component_values != self.component_values:
            object.__setattr__(self, "component_values", component_values)
        if not component_values or self.value != sum(component_values):
            raise DiceRollSpecError("Unmodified result must match its post-reroll components.")

    @classmethod
    def from_state(cls, state: DiceRollState) -> Self:
        if type(state) is not DiceRollState:
            raise DiceRollSpecError("UnmodifiedRollResult state must be a DiceRollState.")
        return cls(
            roll_id=state.original_result.roll_id,
            roll_type=state.original_result.spec.roll_type,
            value=sum(state.current_values),
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
    intrinsic_offset: int
    modifiers: tuple[RollModifier, ...]
    unbounded_value: int
    modified_value: int
    final_value: int
    applied_modifier_ids: tuple[str, ...]

    def __post_init__(self) -> None:
        if any(
            type(value) is not int
            for value in (
                self.intrinsic_offset,
                self.unbounded_value,
                self.modified_value,
                self.final_value,
            )
        ):
            raise DiceRollSpecError("Modified roll stages must be integers.")
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
        resolution = resolve_roll_modifiers(
            self.unmodified.value + self.intrinsic_offset,
            modifiers,
            maximum=12 if self.unmodified.roll_type == "charge_roll" else None,
            maximum_modifier=1 if self.unmodified.roll_type in {"hit_roll", "wound_roll"} else None,
        )
        if self.unmodified.roll_type == "roll_off" and (modifiers or self.intrinsic_offset):
            raise DiceRollSpecError("Roll-off results cannot be modified.")
        if (self.unbounded_value, self.modified_value, self.final_value) != (
            resolution.unbounded,
            resolution.modified,
            resolution.final,
        ):
            raise DiceRollSpecError("ModifiedRollResult final_value does not match modifiers.")
        if self.applied_modifier_ids != resolution.applied_modifier_ids:
            raise DiceRollSpecError(
                "ModifiedRollResult applied_modifier_ids do not match modifiers."
            )

    @classmethod
    def from_unmodified(
        cls,
        unmodified: UnmodifiedRollResult,
        *,
        modifiers: Iterable[RollModifier] = (),
        intrinsic_offset: int = 0,
    ) -> Self:
        if type(unmodified) is not UnmodifiedRollResult or type(intrinsic_offset) is not int:
            raise DiceRollSpecError(
                "Modified roll requires a typed unmodified result and integer offset."
            )
        modifier_tuple = tuple(modifiers)
        if unmodified.roll_type == "roll_off" and (modifier_tuple or intrinsic_offset):
            raise DiceRollSpecError("Roll-off results cannot be modified.")
        resolution = resolve_roll_modifiers(
            unmodified.value + intrinsic_offset,
            modifier_tuple,
            maximum=12 if unmodified.roll_type == "charge_roll" else None,
            maximum_modifier=1 if unmodified.roll_type in {"hit_roll", "wound_roll"} else None,
        )
        return cls(
            unmodified=unmodified,
            intrinsic_offset=intrinsic_offset,
            modifiers=modifier_tuple,
            unbounded_value=resolution.unbounded,
            modified_value=resolution.modified,
            final_value=resolution.final,
            applied_modifier_ids=resolution.applied_modifier_ids,
        )

    def to_payload(self) -> ModifiedRollResultPayload:
        return {
            "unmodified": self.unmodified.to_payload(),
            "intrinsic_offset": self.intrinsic_offset,
            "modifiers": [modifier.to_payload() for modifier in self.modifiers],
            "unbounded_value": self.unbounded_value,
            "modified_value": self.modified_value,
            "final_value": self.final_value,
            "applied_modifier_ids": list(self.applied_modifier_ids),
        }

    @classmethod
    def from_payload(cls, payload: ModifiedRollResultPayload) -> Self:
        return cls(
            unmodified=UnmodifiedRollResult.from_payload(payload["unmodified"]),
            intrinsic_offset=payload["intrinsic_offset"],
            modifiers=tuple(
                RollModifier.from_payload(modifier) for modifier in payload["modifiers"]
            ),
            unbounded_value=payload["unbounded_value"],
            modified_value=payload["modified_value"],
            final_value=payload["final_value"],
            applied_modifier_ids=tuple(payload["applied_modifier_ids"]),
        )
