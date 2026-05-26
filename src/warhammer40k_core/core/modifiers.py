from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass
from enum import StrEnum
from typing import Self, TypedDict

from warhammer40k_core.core.attributes import (
    Characteristic,
    CharacteristicValue,
    characteristic_from_token,
    validate_characteristic_value,
    validate_identifier,
    validate_optional_identifier,
)


class ModifierError(ValueError):
    """Raised when modifier domain data is invalid."""


class ModifierStackingError(ModifierError):
    """Raised when modifier stacking semantics are unsupported."""


class ModifierTiming(StrEnum):
    BASE = "base"
    MULTIPLICATIVE = "multiplicative"
    ADDITIVE = "additive"
    FINAL = "final"

    @property
    def order(self) -> int:
        return _MODIFIER_TIMING_ORDER[self]

    @classmethod
    def ordered(cls) -> tuple[ModifierTiming, ...]:
        return tuple(sorted(cls, key=lambda timing: timing.order))


class ModifierOperation(StrEnum):
    SET = "set"
    ADD = "add"
    MULTIPLY = "multiply"
    FLOOR = "floor"
    CEILING = "ceiling"


class ModifierScopePayload(TypedDict):
    characteristics: list[str] | None
    target_ids: list[str] | None


class ModifierPayload(TypedDict):
    modifier_id: str
    source_id: str | None
    scope: ModifierScopePayload
    timing: str
    operation: str
    operand: int
    priority: int
    exclusive_group: str | None


class ModifierStackPayload(TypedDict):
    characteristic: str
    raw_value: int
    target_id: str | None
    modifiers: list[ModifierPayload]


_MODIFIER_TIMING_ORDER = {
    ModifierTiming.BASE: 0,
    ModifierTiming.MULTIPLICATIVE: 1,
    ModifierTiming.ADDITIVE: 2,
    ModifierTiming.FINAL: 3,
}

_OPERATION_TIMINGS = {
    ModifierOperation.SET: frozenset({ModifierTiming.BASE}),
    ModifierOperation.MULTIPLY: frozenset({ModifierTiming.MULTIPLICATIVE}),
    ModifierOperation.ADD: frozenset({ModifierTiming.ADDITIVE, ModifierTiming.FINAL}),
    ModifierOperation.FLOOR: frozenset({ModifierTiming.FINAL}),
    ModifierOperation.CEILING: frozenset({ModifierTiming.FINAL}),
}


@dataclass(frozen=True, slots=True)
class ModifierScope:
    characteristics: frozenset[Characteristic] | None = None
    target_ids: frozenset[str] | None = None

    def __post_init__(self) -> None:
        if self.characteristics is not None:
            if not self.characteristics:
                raise ModifierError(
                    "ModifierScope characteristics must not be empty when supplied."
                )
            characteristic_set = frozenset(
                _validate_characteristic(item) for item in self.characteristics
            )
            if characteristic_set != self.characteristics:
                object.__setattr__(self, "characteristics", characteristic_set)

        if self.target_ids is not None:
            if not self.target_ids:
                raise ModifierError("ModifierScope target_ids must not be empty when supplied.")
            target_ids = frozenset(
                validate_identifier("ModifierScope target_ids", target_id)
                for target_id in self.target_ids
            )
            if target_ids != self.target_ids:
                object.__setattr__(self, "target_ids", target_ids)

    @classmethod
    def any(cls) -> Self:
        return cls()

    @classmethod
    def for_characteristics(cls, characteristics: Iterable[Characteristic]) -> Self:
        return cls(characteristics=frozenset(characteristics))

    @classmethod
    def for_targets(
        cls,
        target_ids: Iterable[str],
        *,
        characteristics: Iterable[Characteristic] | None = None,
    ) -> Self:
        characteristic_set = None if characteristics is None else frozenset(characteristics)
        return cls(characteristics=characteristic_set, target_ids=frozenset(target_ids))

    def matches(self, characteristic: Characteristic, *, target_id: str | None = None) -> bool:
        _validate_characteristic(characteristic)
        validated_target_id = validate_optional_identifier("target_id", target_id)

        if self.characteristics is not None and characteristic not in self.characteristics:
            return False
        if self.target_ids is not None:
            return validated_target_id in self.target_ids
        return True

    def to_payload(self) -> ModifierScopePayload:
        characteristics = None
        if self.characteristics is not None:
            characteristics = sorted(
                characteristic.value for characteristic in self.characteristics
            )

        target_ids = None
        if self.target_ids is not None:
            target_ids = sorted(self.target_ids)

        return {
            "characteristics": characteristics,
            "target_ids": target_ids,
        }

    @classmethod
    def from_payload(cls, payload: ModifierScopePayload) -> Self:
        characteristic_tokens = payload["characteristics"]
        target_id_tokens = payload["target_ids"]
        characteristics = (
            None
            if characteristic_tokens is None
            else frozenset(characteristic_from_token(token) for token in characteristic_tokens)
        )
        target_ids = (
            None
            if target_id_tokens is None
            else frozenset(
                validate_identifier("ModifierScope target_ids", target_id)
                for target_id in target_id_tokens
            )
        )
        return cls(characteristics=characteristics, target_ids=target_ids)


@dataclass(frozen=True, slots=True)
class Modifier:
    modifier_id: str
    scope: ModifierScope
    timing: ModifierTiming
    operation: ModifierOperation
    operand: int
    priority: int = 0
    source_id: str | None = None
    exclusive_group: str | None = None

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "modifier_id",
            validate_identifier("Modifier modifier_id", self.modifier_id),
        )
        object.__setattr__(
            self,
            "source_id",
            validate_optional_identifier("Modifier source_id", self.source_id),
        )
        object.__setattr__(
            self,
            "exclusive_group",
            validate_optional_identifier("Modifier exclusive_group", self.exclusive_group),
        )

        scope = _validate_modifier_scope(self.scope)
        timing = _validate_modifier_timing(self.timing)
        operation = _validate_modifier_operation(self.operation)

        if scope != self.scope:
            object.__setattr__(self, "scope", scope)
        if timing != self.timing:
            object.__setattr__(self, "timing", timing)
        if operation != self.operation:
            object.__setattr__(self, "operation", operation)

        if type(self.operand) is not int:
            raise ModifierError("Modifier operand must be an integer.")
        if type(self.priority) is not int:
            raise ModifierError("Modifier priority must be an integer.")
        if self.operand == 0 and operation is ModifierOperation.MULTIPLY:
            raise ModifierError("Modifier multiply operand must not be zero.")
        if timing not in _OPERATION_TIMINGS[operation]:
            raise ModifierError("Modifier operation is not supported at the supplied timing.")

    def applies_to(self, characteristic: Characteristic, *, target_id: str | None = None) -> bool:
        return self.scope.matches(characteristic, target_id=target_id)

    def to_payload(self) -> ModifierPayload:
        return {
            "modifier_id": self.modifier_id,
            "source_id": self.source_id,
            "scope": self.scope.to_payload(),
            "timing": self.timing.value,
            "operation": self.operation.value,
            "operand": self.operand,
            "priority": self.priority,
            "exclusive_group": self.exclusive_group,
        }

    @classmethod
    def from_payload(cls, payload: ModifierPayload) -> Self:
        return cls(
            modifier_id=payload["modifier_id"],
            source_id=payload["source_id"],
            scope=ModifierScope.from_payload(payload["scope"]),
            timing=modifier_timing_from_token(payload["timing"]),
            operation=modifier_operation_from_token(payload["operation"]),
            operand=payload["operand"],
            priority=payload["priority"],
            exclusive_group=payload["exclusive_group"],
        )


@dataclass(frozen=True, slots=True)
class ModifierStack:
    characteristic: Characteristic
    raw_value: int
    modifiers: tuple[Modifier, ...] = ()
    target_id: str | None = None

    def __post_init__(self) -> None:
        _validate_characteristic(self.characteristic)
        validate_characteristic_value(self.characteristic, "raw", self.raw_value)
        object.__setattr__(
            self,
            "target_id",
            validate_optional_identifier("ModifierStack target_id", self.target_id),
        )

        modifier_tuple = tuple(self.modifiers)
        for modifier in modifier_tuple:
            _validate_modifier(modifier)
        _validate_unique_modifier_ids(modifier_tuple)
        if modifier_tuple != self.modifiers:
            object.__setattr__(self, "modifiers", modifier_tuple)

    def with_modifier(self, modifier: Modifier) -> ModifierStack:
        return self.with_modifiers((modifier,))

    def with_modifiers(self, modifiers: Iterable[Modifier]) -> ModifierStack:
        return ModifierStack(
            characteristic=self.characteristic,
            raw_value=self.raw_value,
            modifiers=(*self.modifiers, *tuple(modifiers)),
            target_id=self.target_id,
        )

    def applicable_modifiers(self) -> tuple[Modifier, ...]:
        applicable = tuple(
            modifier
            for modifier in self.modifiers
            if modifier.applies_to(self.characteristic, target_id=self.target_id)
        )
        _validate_supported_stacking(applicable)
        return tuple(sorted(applicable, key=_modifier_order_key))

    def resolve(self) -> CharacteristicValue:
        base = self.raw_value
        final = self.raw_value
        applied_modifier_ids: list[str] = []

        for modifier in self.applicable_modifiers():
            if modifier.operation is ModifierOperation.SET:
                base = modifier.operand
                final = modifier.operand
            elif modifier.operation is ModifierOperation.MULTIPLY:
                final *= modifier.operand
            elif modifier.operation is ModifierOperation.ADD:
                final += modifier.operand
            elif modifier.operation is ModifierOperation.FLOOR:
                final = max(final, modifier.operand)
            elif modifier.operation is ModifierOperation.CEILING:
                final = min(final, modifier.operand)
            else:
                raise ModifierError("Unsupported modifier operation.")

            applied_modifier_ids.append(modifier.modifier_id)

        return CharacteristicValue(
            characteristic=self.characteristic,
            raw=self.raw_value,
            base=base,
            final=final,
            applied_modifier_ids=tuple(applied_modifier_ids),
        )

    def to_payload(self) -> ModifierStackPayload:
        return {
            "characteristic": self.characteristic.value,
            "raw_value": self.raw_value,
            "target_id": self.target_id,
            "modifiers": [modifier.to_payload() for modifier in self.modifiers],
        }

    @classmethod
    def from_payload(cls, payload: ModifierStackPayload) -> Self:
        return cls(
            characteristic=characteristic_from_token(payload["characteristic"]),
            raw_value=payload["raw_value"],
            target_id=payload["target_id"],
            modifiers=tuple(Modifier.from_payload(modifier) for modifier in payload["modifiers"]),
        )


def modifier_timing_from_token(token: object) -> ModifierTiming:
    if type(token) is not str:
        raise ModifierError("ModifierTiming token must be a string.")
    try:
        return ModifierTiming(token)
    except ValueError as exc:
        raise ModifierError(f"Unsupported modifier timing token: {token}.") from exc


def modifier_operation_from_token(token: object) -> ModifierOperation:
    if type(token) is not str:
        raise ModifierError("ModifierOperation token must be a string.")
    try:
        return ModifierOperation(token)
    except ValueError as exc:
        raise ModifierError(f"Unsupported modifier operation token: {token}.") from exc


def _validate_characteristic(characteristic: object) -> Characteristic:
    if type(characteristic) is not Characteristic:
        raise ModifierError("Expected a Characteristic.")
    return characteristic


def _validate_modifier_scope(scope: object) -> ModifierScope:
    if type(scope) is not ModifierScope:
        raise ModifierError("Modifier scope must be a ModifierScope.")
    return scope


def _validate_modifier_timing(timing: object) -> ModifierTiming:
    if type(timing) is not ModifierTiming:
        raise ModifierError("Modifier timing must be a ModifierTiming.")
    return timing


def _validate_modifier_operation(operation: object) -> ModifierOperation:
    if type(operation) is not ModifierOperation:
        raise ModifierError("Modifier operation must be a ModifierOperation.")
    return operation


def _validate_modifier(modifier: object) -> Modifier:
    if type(modifier) is not Modifier:
        raise ModifierError("ModifierStack modifiers must contain Modifier instances.")
    return modifier


def _validate_unique_modifier_ids(modifiers: tuple[Modifier, ...]) -> None:
    seen: set[str] = set()
    for modifier in modifiers:
        if modifier.modifier_id in seen:
            raise ModifierStackingError("ModifierStack modifier IDs must be unique.")
        seen.add(modifier.modifier_id)


def _validate_supported_stacking(modifiers: tuple[Modifier, ...]) -> None:
    base_setters = [
        modifier
        for modifier in modifiers
        if modifier.timing is ModifierTiming.BASE and modifier.operation is ModifierOperation.SET
    ]
    if len(base_setters) > 1:
        raise ModifierStackingError("Multiple base-setting modifiers are unsupported.")

    exclusive_groups: set[str] = set()
    for modifier in modifiers:
        if modifier.exclusive_group is None:
            continue
        if modifier.exclusive_group in exclusive_groups:
            raise ModifierStackingError(
                "Multiple modifiers in the same exclusive group are unsupported."
            )
        exclusive_groups.add(modifier.exclusive_group)


def _modifier_order_key(modifier: Modifier) -> tuple[int, int, str]:
    return (modifier.timing.order, modifier.priority, modifier.modifier_id)
