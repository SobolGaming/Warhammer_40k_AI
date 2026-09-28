"""Immutable source operations for fixed characteristics and selected subsets."""

from __future__ import annotations

from dataclasses import dataclass, replace
from typing import TypedDict, cast

from warhammer40k_core.core.attributes import (
    Characteristic,
    CharacteristicBoundPolicy,
    CharacteristicError,
    CharacteristicValue,
)
from warhammer40k_core.core.modifiers import Modifier, ModifierPayload, ModifierStack


class CharacteristicModifierTracePayload(TypedDict):
    characteristic: str
    source_value: int
    modifiers: list[ModifierPayload]
    bounded: bool
    ignored_modifier_ids: list[str]


@dataclass(frozen=True, slots=True)
class CharacteristicModifierTrace:
    characteristic: Characteristic
    source_value: int
    modifiers: tuple[Modifier, ...]
    bounded: bool = True
    ignored_modifier_ids: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        if type(self.characteristic) is not Characteristic or type(self.bounded) is not bool:
            raise CharacteristicError("Characteristic modifier trace requires typed policy.")
        if type(self.modifiers) is not tuple or any(
            type(item) is not Modifier
            or item.source_id is None
            or item.scope.target_ids is not None
            or item.scope.characteristics != frozenset({self.characteristic})
            for item in self.modifiers
        ):
            raise CharacteristicError("Characteristic modifier trace source or scope drift.")
        ModifierStack(self.characteristic, self.source_value, self.modifiers)
        self._validate_selection(self.ignored_modifier_ids)

    def _validate_selection(self, identifiers: tuple[str, ...]) -> None:
        if type(identifiers) is not tuple or any(type(item) is not str for item in identifiers):
            raise CharacteristicError("Characteristic modifier trace selection requires IDs.")
        if len(set(identifiers)) != len(identifiers):
            raise CharacteristicError("Characteristic modifier trace selection IDs are duplicated.")
        if not set(identifiers).issubset(item.modifier_id for item in self.modifiers):
            raise CharacteristicError("Characteristic modifier trace selection has unknown IDs.")

    def resolve(
        self, *, ignored_modifier_ids: tuple[str, ...] | None = None
    ) -> CharacteristicValue:
        identifiers = (
            self.ignored_modifier_ids if ignored_modifier_ids is None else ignored_modifier_ids
        )
        self._validate_selection(identifiers)
        selected = tuple(item for item in self.modifiers if item.modifier_id not in identifiers)
        return ModifierStack(self.characteristic, self.source_value, selected).resolve(
            bound_policy=(
                None if self.bounded else CharacteristicBoundPolicy(self.characteristic, None, None)
            )
        )

    def value(self) -> CharacteristicValue:
        return replace(self.resolve(), modifier_trace=self)

    def to_payload(self) -> CharacteristicModifierTracePayload:
        return {
            "characteristic": self.characteristic.value,
            "source_value": self.source_value,
            "modifiers": [item.to_payload() for item in self.modifiers],
            "bounded": self.bounded,
            "ignored_modifier_ids": list(self.ignored_modifier_ids),
        }

    @classmethod
    def from_payload(
        cls, payload: CharacteristicModifierTracePayload
    ) -> CharacteristicModifierTrace:
        if type(cast(object, payload)) is not dict or set(payload) != {
            "characteristic",
            "source_value",
            "modifiers",
            "bounded",
            "ignored_modifier_ids",
        }:
            raise CharacteristicError("Characteristic modifier trace fields drifted.")
        if (
            type(payload["modifiers"]) is not list
            or type(payload["ignored_modifier_ids"]) is not list
        ):
            raise CharacteristicError(
                "Characteristic modifier trace operations and selection require arrays."
            )
        for item in payload["modifiers"]:
            if type(cast(object, item)) is not dict or set(item) - {"result_floor"} != {
                "modifier_id",
                "source_id",
                "scope",
                "timing",
                "operation",
                "operand",
                "priority",
                "exclusive_group",
            }:
                raise CharacteristicError("Characteristic modifier trace operation fields drifted.")
            scope = item["scope"]
            if type(cast(object, scope)) is not dict or set(scope) != {
                "characteristics",
                "target_ids",
            }:
                raise CharacteristicError("Characteristic modifier trace scope fields drifted.")
        result = cls(
            characteristic=Characteristic(payload["characteristic"]),
            source_value=payload["source_value"],
            modifiers=tuple(Modifier.from_payload(item) for item in payload["modifiers"]),
            bounded=payload["bounded"],
            ignored_modifier_ids=tuple(payload["ignored_modifier_ids"]),
        )
        if result.to_payload() != payload:
            raise CharacteristicError("Characteristic modifier trace payload is not canonical.")
        return result


def validate_characteristic_trace(value: CharacteristicValue) -> None:
    trace = value.modifier_trace
    if trace is None:
        return
    if type(trace) is not CharacteristicModifierTrace:
        raise CharacteristicError("Characteristic modifier trace must be typed.")
    if replace(value, modifier_trace=None) != trace.resolve():
        raise CharacteristicError("Characteristic modifier trace arithmetic or identity drift.")
