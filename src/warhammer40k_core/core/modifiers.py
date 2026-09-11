from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass
from enum import StrEnum
from fractions import Fraction
from math import ceil, isfinite
from typing import Self, TypedDict, cast

from warhammer40k_core.core.attributes import (
    TARGETING_RANGE_MAXIMUM,
    TARGETING_RANGE_MINIMUM,
    BoundedCharacteristicValue,
    Characteristic,
    CharacteristicBoundPolicy,
    CharacteristicValue,
    CharacteristicValueKind,
    characteristic_from_token,
    characteristic_value_kind_from_token,
    validate_characteristic_value,
)
from warhammer40k_core.core.validation import IdentifierValidator


class ModifierError(ValueError):
    """Raised when modifier domain data is invalid."""


class ModifierStackingError(ModifierError):
    """Raised when modifier stacking semantics are unsupported."""


class ModifierTiming(StrEnum):
    BASE = "base"
    MULTIPLICATIVE = "multiplicative"
    ADDITIVE = "additive"
    DIVISIVE = "divisive"
    SUBTRACTIVE = "subtractive"
    FINAL = "final"

    @property
    def order(self) -> int:
        return _MODIFIER_TIMING_ORDER[self]

    @classmethod
    def ordered(cls) -> tuple[ModifierTiming, ...]:
        return tuple(sorted(cls, key=lambda timing: timing.order))


class ModifierOperation(StrEnum):
    SET = "set"
    SET_DASH = "set_dash"
    SET_STAR = "set_star"
    ADD = "add"
    MULTIPLY = "multiply"
    DIVIDE = "divide"
    SUBTRACT = "subtract"
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


class DamageCharacteristicResolutionPayload(TypedDict):
    characteristic: str
    value_kind: str
    raw: int
    base: int
    modifier_final: int
    final: int
    applied_modifier_ids: list[str]


class RollModifierPayload(TypedDict):
    modifier_id: str
    source_id: str | None
    operation: str
    operand: int
    priority: int


_MODIFIER_TIMING_ORDER = {
    ModifierTiming.BASE: 0,
    ModifierTiming.MULTIPLICATIVE: 1,
    ModifierTiming.ADDITIVE: 2,
    ModifierTiming.DIVISIVE: 3,
    ModifierTiming.SUBTRACTIVE: 4,
    ModifierTiming.FINAL: 5,
}

_OPERATION_TIMINGS = {
    ModifierOperation.SET: frozenset({ModifierTiming.BASE}),
    ModifierOperation.SET_DASH: frozenset({ModifierTiming.BASE}),
    ModifierOperation.SET_STAR: frozenset({ModifierTiming.BASE}),
    ModifierOperation.MULTIPLY: frozenset({ModifierTiming.MULTIPLICATIVE}),
    ModifierOperation.ADD: frozenset({ModifierTiming.ADDITIVE, ModifierTiming.FINAL}),
    ModifierOperation.DIVIDE: frozenset({ModifierTiming.DIVISIVE}),
    ModifierOperation.SUBTRACT: frozenset({ModifierTiming.SUBTRACTIVE}),
    ModifierOperation.FLOOR: frozenset({ModifierTiming.FINAL}),
    ModifierOperation.CEILING: frozenset({ModifierTiming.FINAL}),
}


class RollModifierOperation(StrEnum):
    ADD = "add"
    SET = "set"
    MULTIPLY = "multiply"
    DIVIDE = "divide"
    SUBTRACT = "subtract"
    FLOOR = "floor"
    CEILING = "ceiling"


@dataclass(frozen=True, slots=True)
class ModifierTerm:
    """An unevaluated operation; its runtime binding supplies source identity."""

    operation: ModifierOperation
    operand: int

    def bind(
        self, *, modifier_id: str, source_id: str, characteristic: Characteristic | None = None
    ) -> Modifier:
        timings = _OPERATION_TIMINGS[self.operation]
        return Modifier(
            modifier_id=modifier_id,
            source_id=source_id,
            scope=(
                ModifierScope.any()
                if characteristic is None
                else ModifierScope.for_characteristics((characteristic,))
            ),
            timing=min(timings, key=lambda timing: timing.order),
            operation=self.operation,
            operand=self.operand,
        )

    def __post_init__(self) -> None:
        _validate_modifier_operation(self.operation)
        # Reuse the complete operation/operand validation without evaluating it.
        self.bind(
            modifier_id="modifier-term-validation",
            source_id="modifier-term-validation",
            characteristic=Characteristic.TOUGHNESS,
        )


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
                _validate_identifier("ModifierScope target_ids", target_id)
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
        validated_target_id = _validate_optional_identifier("target_id", target_id)

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
                _validate_identifier("ModifierScope target_ids", target_id)
                for target_id in target_id_tokens
            )
        )
        return cls(characteristics=characteristics, target_ids=target_ids)


@dataclass(frozen=True, slots=True)
class RollModifier:
    modifier_id: str
    operand: int
    source_id: str | None = None
    operation: RollModifierOperation = RollModifierOperation.ADD
    priority: int = 0

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "modifier_id",
            _validate_identifier("RollModifier modifier_id", self.modifier_id),
        )
        object.__setattr__(
            self,
            "source_id",
            _validate_optional_identifier("RollModifier source_id", self.source_id),
        )
        object.__setattr__(self, "operation", roll_modifier_operation_from_token(self.operation))
        if type(self.operand) is not int:
            raise ModifierError("RollModifier operand must be an integer.")
        if type(self.priority) is not int:
            raise ModifierError("RollModifier priority must be an integer.")
        if self.operation is RollModifierOperation.DIVIDE and self.operand <= 0:
            raise ModifierError("Roll division requires a positive divisor.")

    def apply(self, value: int | Fraction) -> Fraction:
        if type(value) not in {int, Fraction}:
            raise ModifierError("RollModifier value must be exact numeric data.")
        return _apply_numeric_operation(self.operation.value, self.operand, Fraction(value))

    def to_payload(self) -> RollModifierPayload:
        return {
            "modifier_id": self.modifier_id,
            "source_id": self.source_id,
            "operation": self.operation.value,
            "operand": self.operand,
            "priority": self.priority,
        }

    @classmethod
    def from_payload(cls, payload: RollModifierPayload) -> Self:
        return cls(
            modifier_id=payload["modifier_id"],
            source_id=payload["source_id"],
            operation=roll_modifier_operation_from_token(payload["operation"]),
            operand=payload["operand"],
            priority=payload["priority"],
        )


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
            _validate_identifier("Modifier modifier_id", self.modifier_id),
        )
        object.__setattr__(
            self,
            "source_id",
            _validate_optional_identifier("Modifier source_id", self.source_id),
        )
        object.__setattr__(
            self,
            "exclusive_group",
            _validate_optional_identifier("Modifier exclusive_group", self.exclusive_group),
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
        if operation is ModifierOperation.DIVIDE and self.operand <= 0:
            raise ModifierError("Modifier division requires a positive divisor.")
        if operation in {ModifierOperation.SET_DASH, ModifierOperation.SET_STAR} and self.operand:
            raise ModifierError("Symbolic replacement modifiers require a zero numeric operand.")
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
class ModifierArithmeticStep:
    modifier: Modifier
    before: Fraction
    after: Fraction


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
            _validate_optional_identifier("ModifierStack target_id", self.target_id),
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

    def resolve(
        self,
        *,
        bound_policy: CharacteristicBoundPolicy | None = None,
    ) -> CharacteristicValue:
        applicable = self.applicable_modifiers()
        if applicable and applicable[0].operation in {
            ModifierOperation.SET_DASH,
            ModifierOperation.SET_STAR,
        }:
            if self.characteristic is Characteristic.DETECTION_RANGE:
                raise ModifierError("Detection Range cannot have a symbolic replacement.")
            replacement = applicable[0]
            return CharacteristicValue(
                self.characteristic,
                0,
                0,
                0,
                (replacement.modifier_id,),
                CharacteristicValueKind.REPLACEMENT_DASH
                if replacement.operation is ModifierOperation.SET_DASH
                else CharacteristicValueKind.REPLACEMENT_STAR,
            )
        if (
            applicable
            and self.characteristic is not Characteristic.DETECTION_RANGE
            and applicable[0].operation is ModifierOperation.SET
            and not applicable[0].operand
        ):
            return CharacteristicValue(
                self.characteristic,
                self.raw_value,
                0,
                0,
                (applicable[0].modifier_id,),
                CharacteristicValueKind.REPLACEMENT_ZERO,
            )
        return self.resolve_bounded(bound_policy=bound_policy).to_characteristic_value()

    def resolve_bounded(
        self,
        *,
        bound_policy: CharacteristicBoundPolicy | None = None,
    ) -> BoundedCharacteristicValue:
        base = self.raw_value
        final = Fraction(self.raw_value)
        applied_modifier_ids: list[str] = []

        for step in self.arithmetic_steps():
            modifier = step.modifier
            if modifier.operation is ModifierOperation.SET:
                base = modifier.operand
                final = Fraction(modifier.operand)
                if (
                    not modifier.operand
                    and self.characteristic is not Characteristic.DETECTION_RANGE
                ):
                    return BoundedCharacteristicValue.from_values(
                        characteristic=self.characteristic,
                        raw=self.raw_value,
                        base=0,
                        unbounded_final=0,
                        applied_modifier_ids=(modifier.modifier_id,),
                        bound_policy=CharacteristicBoundPolicy(self.characteristic, 0, 0),
                        value_kind=CharacteristicValueKind.REPLACEMENT_ZERO,
                    )
            final = step.after

            applied_modifier_ids.append(modifier.modifier_id)

        policy = (
            CharacteristicBoundPolicy.for_characteristic(self.characteristic)
            if bound_policy is None
            else bound_policy
        )
        return BoundedCharacteristicValue.from_values(
            characteristic=self.characteristic,
            raw=self.raw_value,
            base=base,
            unbounded_final=ceil(final),
            applied_modifier_ids=tuple(applied_modifier_ids),
            bound_policy=policy,
        )

    def arithmetic_steps(self) -> tuple[ModifierArithmeticStep, ...]:
        """Exact ordered intermediate values; these are not bounded characteristics."""
        value = Fraction(self.raw_value)
        steps: list[ModifierArithmeticStep] = []
        for modifier in self.applicable_modifiers():
            if modifier.operation in {ModifierOperation.SET_DASH, ModifierOperation.SET_STAR}:
                raise ModifierError("Symbolic replacement requires characteristic resolution.")
            modified = _apply_numeric_operation(modifier.operation.value, modifier.operand, value)
            steps.append(ModifierArithmeticStep(modifier, value, modified))
            value = modified
            if (
                modifier.operation is ModifierOperation.SET
                and not modifier.operand
                and self.characteristic is not Characteristic.DETECTION_RANGE
            ):
                break
        return tuple(steps)

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


@dataclass(frozen=True, slots=True)
class DamageCharacteristicResolution:
    raw: int
    base: int
    modifier_final: int
    final: int
    applied_modifier_ids: tuple[str, ...]
    characteristic: Characteristic = Characteristic.DAMAGE
    value_kind: CharacteristicValueKind = CharacteristicValueKind.NUMERIC

    def __post_init__(self) -> None:
        if self.characteristic is not Characteristic.DAMAGE:
            raise ModifierError("DamageCharacteristicResolution characteristic must be Damage.")
        for field_name, value in (
            ("raw", self.raw),
            ("base", self.base),
            ("modifier_final", self.modifier_final),
            ("final", self.final),
        ):
            validate_characteristic_value(
                Characteristic.DAMAGE,
                f"DamageCharacteristicResolution {field_name}",
                value,
            )
        ids = _validate_identifier_tuple(
            "DamageCharacteristicResolution applied_modifier_ids",
            self.applied_modifier_ids,
        )
        if ids != self.applied_modifier_ids:
            object.__setattr__(self, "applied_modifier_ids", ids)
        if self.final != self.modifier_final:
            raise ModifierError("DamageCharacteristicResolution final drift.")
        if not self.to_characteristic_value().is_numeric:
            raise ModifierError("Damage resolution requires a numeric characteristic.")

    def to_characteristic_value(self) -> CharacteristicValue:
        return CharacteristicValue(
            characteristic=Characteristic.DAMAGE,
            raw=self.raw,
            base=self.base,
            final=self.final,
            applied_modifier_ids=self.applied_modifier_ids,
            value_kind=self.value_kind,
        )

    def to_payload(self) -> DamageCharacteristicResolutionPayload:
        return {
            "characteristic": self.characteristic.value,
            "value_kind": self.value_kind.value,
            "raw": self.raw,
            "base": self.base,
            "modifier_final": self.modifier_final,
            "final": self.final,
            "applied_modifier_ids": list(self.applied_modifier_ids),
        }

    @classmethod
    def from_payload(cls, payload: DamageCharacteristicResolutionPayload) -> Self:
        return cls(
            characteristic=characteristic_from_token(payload["characteristic"]),
            value_kind=characteristic_value_kind_from_token(payload["value_kind"]),
            raw=payload["raw"],
            base=payload["base"],
            modifier_final=payload["modifier_final"],
            final=payload["final"],
            applied_modifier_ids=tuple(payload["applied_modifier_ids"]),
        )


def resolve_characteristic_value(
    value: CharacteristicValue,
    modifiers: Iterable[Modifier],
    *,
    target_id: str | None = None,
    bound_policy: CharacteristicBoundPolicy | None = None,
) -> CharacteristicValue:
    if type(value) is not CharacteristicValue:
        raise ModifierError("resolve_characteristic_value requires a CharacteristicValue.")
    modifier_tuple = tuple(modifiers)
    for modifier in modifier_tuple:
        _validate_modifier(modifier)
    if not value.is_numeric or value.value_kind is CharacteristicValueKind.REPLACEMENT_ZERO:
        if value.value_kind is CharacteristicValueKind.SOURCE_DASH and any(
            modifier.applies_to(value.characteristic, target_id=target_id)
            for modifier in modifier_tuple
        ):
            raise ModifierError("Numeric modifiers cannot change dash characteristic values.")
        return value
    return ModifierStack(
        characteristic=value.characteristic,
        raw_value=value.raw,
        modifiers=modifier_tuple,
        target_id=target_id,
    ).resolve(bound_policy=bound_policy)


def resolve_damage_characteristic(
    value: CharacteristicValue,
    modifiers: Iterable[Modifier],
    *,
    target_id: str | None = None,
    damage_zero_permitted: bool = False,
) -> DamageCharacteristicResolution:
    if type(value) is not CharacteristicValue:
        raise ModifierError("resolve_damage_characteristic requires a CharacteristicValue.")
    if value.characteristic is not Characteristic.DAMAGE:
        raise ModifierError("resolve_damage_characteristic requires a Damage value.")
    if not value.is_numeric:
        raise ModifierError("Damage cannot be resolved from a dash characteristic value.")
    bounded = resolve_characteristic_value(
        value,
        modifiers,
        target_id=target_id,
        bound_policy=CharacteristicBoundPolicy.for_characteristic(
            Characteristic.DAMAGE,
            damage_zero_permitted=damage_zero_permitted,
        ),
    )
    if not bounded.is_numeric:
        raise ModifierError("Damage resolution requires a numeric characteristic.")
    final = bounded.final
    return DamageCharacteristicResolution(
        raw=bounded.raw,
        base=bounded.base,
        modifier_final=bounded.final,
        final=final,
        applied_modifier_ids=bounded.applied_modifier_ids,
        value_kind=bounded.value_kind,
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


def roll_modifier_operation_from_token(token: object) -> RollModifierOperation:
    if type(token) is RollModifierOperation:
        return token
    if type(token) is not str:
        raise ModifierError("RollModifierOperation token must be a string.")
    try:
        return RollModifierOperation(token)
    except ValueError as exc:
        raise ModifierError(f"Unsupported roll modifier operation token: {token}.") from exc


def apply_roll_modifiers(
    value: int,
    modifiers: Iterable[RollModifier],
) -> tuple[int, tuple[str, ...]]:
    resolution = resolve_roll_modifiers(value, modifiers)
    return resolution.final, resolution.applied_modifier_ids


@dataclass(frozen=True, slots=True)
class RollModifierResolution:
    unbounded: int
    modified: int
    final: int
    applied_modifier_ids: tuple[str, ...]


def resolve_roll_modifiers(
    value: int,
    modifiers: Iterable[RollModifier],
    *,
    maximum: int | None = None,
    maximum_modifier: int | None = None,
) -> RollModifierResolution:
    if type(value) is not int:
        raise ModifierError("Roll modifier input value must be an integer.")
    modifier_tuple = tuple(modifiers)
    for modifier in modifier_tuple:
        if type(modifier) is not RollModifier:
            raise ModifierError("Roll modifiers must contain RollModifier instances.")
    _validate_unique_roll_modifier_ids(modifier_tuple)
    if sum(m.operation is RollModifierOperation.SET for m in modifier_tuple) > 1:
        raise ModifierStackingError("Multiple roll replacements require explicit selection.")

    if maximum is not None and (type(maximum) is not int or maximum < 1):
        raise ModifierError("Roll maximum must be a positive integer.")
    if maximum_modifier is not None and (type(maximum_modifier) is not int or maximum_modifier < 0):
        raise ModifierError("Roll modifier limit must be a non-negative integer.")
    final = Fraction(value)
    applied_modifier_ids: list[str] = []
    for modifier in sorted(modifier_tuple, key=_roll_modifier_order_key):
        final = modifier.apply(final)
        applied_modifier_ids.append(modifier.modifier_id)
    unbounded = ceil(final)
    modified = bound_modified_roll(unbounded)
    limited = unbounded
    if maximum_modifier is not None:
        limited = value + max(-maximum_modifier, min(maximum_modifier, unbounded - value))
    return RollModifierResolution(
        unbounded,
        modified,
        bound_modified_roll(limited, maximum=maximum),
        tuple(applied_modifier_ids),
    )


def resolve_stratagem_cost(
    base_cost: int, modifiers: tuple[Modifier, ...]
) -> tuple[int, tuple[ModifierArithmeticStep, ...]]:
    """02.02.01: exact cumulative operations, then the final 0/base+1 limits."""
    if type(base_cost) is not int or base_cost < 0:
        raise ModifierError("Stratagem base cost must be a nonnegative integer.")
    for modifier in modifiers:
        _validate_modifier(modifier)
        if modifier.scope != ModifierScope.any():
            raise ModifierError("Stratagem operations must already be selected for this use.")
    _validate_unique_modifier_ids(modifiers)
    _validate_supported_stacking(modifiers)
    current = Fraction(base_cost)
    steps: list[ModifierArithmeticStep] = []
    for modifier in sorted(modifiers, key=_modifier_order_key):
        if modifier.operation in {ModifierOperation.SET_DASH, ModifierOperation.SET_STAR}:
            raise ModifierError("Stratagem cost requires numeric operations.")
        modified = _apply_numeric_operation(modifier.operation.value, modifier.operand, current)
        steps.append(ModifierArithmeticStep(modifier, current, modified))
        current = modified
    return max(0, min(base_cost + 1, ceil(current))), tuple(steps)


def resolve_targeting_range(value: float) -> float:
    """Apply the common Detection/Lone Operative limit after all range effects."""
    if type(value) not in {int, float} or not isfinite(value):
        raise ModifierError("Targeting range must be a finite number.")
    return max(float(TARGETING_RANGE_MINIMUM), min(float(TARGETING_RANGE_MAXIMUM), float(value)))


def resolve_distance_deltas(
    value: float, deltas: tuple[tuple[str, float], ...]
) -> tuple[float, tuple[tuple[str, float, float], ...]]:
    """Resolve subsequent distance additions exactly, with one final nonnegative bound."""
    if type(value) not in {int, float} or not isfinite(value) or value < 0:
        raise ModifierError("Distance must be finite and nonnegative.")
    ids: set[str] = set()
    for modifier_id, delta in deltas:
        _validate_identifier("Distance modifier ID", modifier_id)
        if modifier_id in ids:
            raise ModifierStackingError("Distance modifier IDs must be unique.")
        ids.add(modifier_id)
        if type(delta) not in {int, float} or not isfinite(delta):
            raise ModifierError("Distance modifier must be finite numeric data.")
    current = Fraction(str(value))
    steps: list[tuple[str, float, float]] = []
    for modifier_id, delta in sorted(deltas, key=lambda item: (item[1] < 0, item[0])):
        modified = _apply_numeric_operation("add", Fraction(str(delta)), current)
        if modified != current:
            steps.append((modifier_id, float(current), float(modified)))
        current = modified
    return float(max(Fraction(0), current)), tuple(steps)


def _validate_characteristic(characteristic: object) -> Characteristic:
    if type(characteristic) is not Characteristic:
        raise ModifierError("Expected a Characteristic.")
    return characteristic


_validate_identifier = IdentifierValidator(ModifierError)


def _validate_optional_identifier(field_name: str, value: object | None) -> str | None:
    if value is None:
        return None
    return _validate_identifier(field_name, value)


def _validate_identifier_tuple(field_name: str, values: object) -> tuple[str, ...]:
    if type(values) is not tuple:
        raise ModifierError(f"{field_name} must be a tuple.")
    identifiers: list[str] = []
    seen: set[str] = set()
    for value in cast(tuple[object, ...], values):
        identifier = _validate_identifier(f"{field_name} value", value)
        if identifier in seen:
            raise ModifierError(f"{field_name} must not contain duplicates.")
        seen.add(identifier)
        identifiers.append(identifier)
    return tuple(identifiers)


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


def _validate_unique_roll_modifier_ids(modifiers: tuple[RollModifier, ...]) -> None:
    seen: set[str] = set()
    for modifier in modifiers:
        if modifier.modifier_id in seen:
            raise ModifierStackingError("RollModifier IDs must be unique.")
        seen.add(modifier.modifier_id)


def _validate_supported_stacking(modifiers: tuple[Modifier, ...]) -> None:
    base_setters = [modifier for modifier in modifiers if modifier.timing is ModifierTiming.BASE]
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
    return (
        _operation_order(modifier.operation.value, modifier.operand),
        modifier.priority,
        modifier.modifier_id,
    )


def _roll_modifier_order_key(modifier: RollModifier) -> tuple[int, int, str]:
    return (
        _operation_order(modifier.operation.value, modifier.operand),
        modifier.priority,
        modifier.modifier_id,
    )


def _operation_order(operation: str, operand: int) -> int:
    if operation in {"set", "set_dash", "set_star"}:
        return 0
    if operation == "multiply":
        return 1
    if operation == "add":
        return 2 if operand >= 0 else 4
    if operation == "divide":
        return 3
    if operation == "subtract":
        return 4 if operand >= 0 else 2
    if operation in {"floor", "ceiling"}:
        return 5
    raise ModifierError("Unsupported ordered operation.")


def bound_modified_roll(value: int, *, maximum: int | None = None) -> int:
    """The terminal dice minimum, followed by a source-defined result cap."""
    if type(value) is not int:
        raise ModifierError("Modified dice value must be an integer.")
    if maximum is not None and (type(maximum) is not int or maximum < 1):
        raise ModifierError("Modified dice maximum must be a positive integer.")
    modified = max(1, value)
    return modified if maximum is None else min(modified, maximum)


def _apply_numeric_operation(operation: str, operand: int | Fraction, value: Fraction) -> Fraction:
    if operation == "set":
        return Fraction(operand)
    if operation == "multiply":
        return value * operand
    if operation == "add":
        return value + operand
    if operation == "divide":
        return value / operand
    if operation == "subtract":
        return value - operand
    if operation == "floor":
        return max(value, Fraction(operand))
    if operation == "ceiling":
        return min(value, Fraction(operand))
    raise ModifierError("Unsupported numeric modifier operation.")
