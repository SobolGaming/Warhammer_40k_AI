"""Source-linked unresolved profile values; dice are evaluated by the engine."""

from __future__ import annotations

from dataclasses import dataclass, replace
from typing import NotRequired, Self, TypedDict, cast

from warhammer40k_core.core.attributes import (
    Characteristic,
    CharacteristicError,
    CharacteristicValue,
    CharacteristicValueKind,
    CharacteristicValuePayload,
    characteristic_from_token,
    validate_identifier,
)
from warhammer40k_core.core.dice import DiceExpression, DiceExpressionPayload
from warhammer40k_core.core.modifiers import (
    Modifier,
    ModifierOperation,
    ModifierPayload,
    ModifierTerm,
    resolve_characteristic_value,
)


class RandomProfileValuePayload(TypedDict):
    characteristic: str
    value_kind: str
    expression: DiceExpressionPayload
    source_id: str
    modifiers: NotRequired[list[ModifierPayload]]
    ignored_modifier_ids: NotRequired[list[str]]
    evaluation: NotRequired[CharacteristicValuePayload]
    evaluation_id: NotRequired[str]
    evaluation_raw: NotRequired[int]


@dataclass(frozen=True, slots=True)
class RandomProfileValue:
    characteristic: Characteristic
    expression: DiceExpression
    source_id: str
    modifiers: tuple[Modifier, ...] = ()
    evaluation: CharacteristicValue | None = None
    evaluation_id: str | None = None
    ignored_modifier_ids: tuple[str, ...] = ()
    evaluation_raw: int | None = None

    def __post_init__(self) -> None:
        if type(self.characteristic) is not Characteristic:
            raise CharacteristicError("Random profile requires a Characteristic.")
        if type(self.expression) is not DiceExpression or any(
            type(value) is not int
            for value in (self.expression.quantity, self.expression.sides, self.expression.modifier)
        ):
            raise CharacteristicError("Random profile requires an integral DiceExpression.")
        minimum = self.expression.quantity + self.expression.modifier
        maximum = self.expression.quantity * self.expression.sides + self.expression.modifier
        if self.characteristic is Characteristic.ARMOR_PENETRATION:
            if maximum > 0:
                raise CharacteristicError("Random Armour Penetration cannot be positive.")
        elif self.characteristic is Characteristic.OBJECTIVE_CONTROL:
            if minimum < 0:
                raise CharacteristicError("Random Objective Control cannot be negative.")
        elif minimum < 1:
            raise CharacteristicError("Random profile outcomes must be positive.")
        object.__setattr__(self, "source_id", validate_identifier("source_id", self.source_id))
        if type(self.modifiers) is not tuple or any(
            type(m) is not Modifier for m in self.modifiers
        ):
            raise CharacteristicError("Random profile modifiers must be typed operations.")
        if len({m.modifier_id for m in self.modifiers}) != len(self.modifiers):
            raise CharacteristicError("Random profile modifier IDs must be unique.")
        if (
            type(self.ignored_modifier_ids) is not tuple
            or any(type(item) is not str for item in self.ignored_modifier_ids)
            or len(set(self.ignored_modifier_ids)) != len(self.ignored_modifier_ids)
            or not set(self.ignored_modifier_ids).issubset(m.modifier_id for m in self.modifiers)
        ):
            raise CharacteristicError("Random profile ignored modifier identities drifted.")
        if (
            len({self.evaluation is None, self.evaluation_id is None, self.evaluation_raw is None})
            != 1
        ):
            raise CharacteristicError(
                "Random profile evaluation requires its identity and raw roll."
            )
        if self.evaluation is not None:
            if (
                type(self.evaluation) is not CharacteristicValue
                or self.evaluation.characteristic is not self.characteristic
            ):
                raise CharacteristicError("Random profile evaluation characteristic drifted.")
            if (
                type(self.evaluation_raw) is not int
                or not minimum <= self.evaluation_raw <= maximum
            ):
                raise CharacteristicError("Random profile evaluation is outside expression bounds.")
            if self.evaluation.is_numeric and self.evaluation.raw != self.evaluation_raw:
                raise CharacteristicError("Random profile evaluation raw roll drifted.")
            if self.evaluation_id is None:
                raise CharacteristicError("Random profile evaluation identity is absent.")
            validate_identifier("evaluation_id", self.evaluation_id)

    @property
    def value_kind(self) -> CharacteristicValueKind:
        return CharacteristicValueKind.RANDOM

    @property
    def is_numeric(self) -> bool:
        return self.evaluation is not None and self.evaluation.is_numeric

    @property
    def is_dash(self) -> bool:
        return self.evaluation is not None and self.evaluation.is_dash

    @property
    def applied_modifier_ids(self) -> tuple[str, ...]:
        return tuple(m.modifier_id for m in self.modifiers)

    @property
    def raw(self) -> int:
        if self.evaluation_raw is None:
            raise CharacteristicError("Random profile value is unresolved.")
        return self.evaluation_raw

    @property
    def base(self) -> int:
        return self.resolved_value().base

    @property
    def final(self) -> int:
        return self.resolved_value().final

    def resolved_value(self) -> CharacteristicValue:
        if self.evaluation is None:
            raise CharacteristicError("Random profile value is unresolved.")
        return self.evaluation

    def without_evaluation(self) -> Self:
        """Clear the evaluated result, occurrence ID, and physical source roll."""
        return replace(self, evaluation=None, evaluation_id=None, evaluation_raw=None)

    def evaluate(
        self,
        *,
        raw: int,
        evaluation_id: str,
        target_id: str,
        ignored_modifier_ids: tuple[str, ...] | None = None,
    ) -> Self:
        ignored = (
            self.ignored_modifier_ids if ignored_modifier_ids is None else ignored_modifier_ids
        )
        value = resolve_characteristic_value(
            CharacteristicValue.from_raw(self.characteristic, raw),
            tuple(item for item in self.modifiers if item.modifier_id not in ignored),
            target_id=target_id,
        )
        return replace(
            self,
            evaluation=value,
            evaluation_id=evaluation_id,
            evaluation_raw=raw,
            ignored_modifier_ids=ignored,
        )

    def to_payload(self) -> RandomProfileValuePayload:
        payload: RandomProfileValuePayload = {
            "characteristic": self.characteristic.value,
            "value_kind": self.value_kind.value,
            "expression": self.expression.to_payload(),
            "source_id": self.source_id,
        }
        if self.modifiers:
            payload["modifiers"] = [m.to_payload() for m in self.modifiers]
        if self.ignored_modifier_ids:
            payload["ignored_modifier_ids"] = list(self.ignored_modifier_ids)
        if self.evaluation is not None:
            if self.evaluation_id is None:
                raise CharacteristicError("Random profile evaluation identity is absent.")
            payload["evaluation"] = self.evaluation.to_payload()
            payload["evaluation_id"] = self.evaluation_id
            payload["evaluation_raw"] = self.raw
        return payload

    @classmethod
    def from_payload(cls, payload: RandomProfileValuePayload) -> Self:
        if type(cast(object, payload)) is not dict:
            raise CharacteristicError("Random profile payload must be an object.")
        required = {"characteristic", "value_kind", "expression", "source_id"}
        if not required <= set(payload) or set(payload) - required - {
            "modifiers",
            "ignored_modifier_ids",
            "evaluation",
            "evaluation_id",
            "evaluation_raw",
        }:
            raise CharacteristicError("Random profile payload fields are invalid.")
        if payload["value_kind"] != CharacteristicValueKind.RANDOM.value:
            raise CharacteristicError("Random profile value_kind is invalid.")
        if type(cast(object, payload["expression"])) is not dict or set(payload["expression"]) != {
            "quantity",
            "sides",
            "modifier",
        }:
            raise CharacteristicError("Random profile expression fields are invalid.")
        if "modifiers" in payload and type(payload["modifiers"]) is not list:
            raise CharacteristicError("Random profile modifiers must be an array.")
        if "ignored_modifier_ids" in payload and type(payload["ignored_modifier_ids"]) is not list:
            raise CharacteristicError("Random profile modifier selection must be an array.")
        if "evaluation" in payload and type(cast(object, payload["evaluation"])) is not dict:
            raise CharacteristicError("Random profile evaluation must be an object.")
        if "evaluation_raw" in payload and type(payload["evaluation_raw"]) is not int:
            raise CharacteristicError("Random profile evaluation raw roll must be an integer.")
        if "evaluation" in payload and set(payload["evaluation"]) - {"modifier_trace"} != {
            "characteristic",
            "value_kind",
            "raw",
            "base",
            "final",
            "applied_modifier_ids",
        }:
            raise CharacteristicError("Random profile evaluation fields are invalid.")
        for modifier in payload.get("modifiers", []):
            if type(cast(object, modifier)) is not dict or set(modifier) - {"result_floor"} != {
                "modifier_id",
                "source_id",
                "scope",
                "timing",
                "operation",
                "operand",
                "priority",
                "exclusive_group",
            }:
                raise CharacteristicError("Random profile modifier fields are invalid.")
            if type(cast(object, modifier["scope"])) is not dict or set(modifier["scope"]) != {
                "characteristics",
                "target_ids",
            }:
                raise CharacteristicError("Random profile modifier scope fields are invalid.")
        return cls(
            characteristic=characteristic_from_token(payload["characteristic"]),
            expression=DiceExpression.from_payload(payload["expression"]),
            source_id=payload["source_id"],
            modifiers=tuple(Modifier.from_payload(m) for m in payload.get("modifiers", [])),
            ignored_modifier_ids=tuple(payload.get("ignored_modifier_ids", [])),
            evaluation=CharacteristicValue.from_payload(payload["evaluation"])
            if "evaluation" in payload
            else None,
            evaluation_id=payload.get("evaluation_id"),
            evaluation_raw=payload.get("evaluation_raw"),
        )


type ProfileCharacteristicValue = CharacteristicValue | RandomProfileValue
type ProfileCharacteristicValuePayload = CharacteristicValuePayload | RandomProfileValuePayload


def profile_characteristic_from_payload(
    payload: ProfileCharacteristicValuePayload,
) -> ProfileCharacteristicValue:
    if type(cast(object, payload)) is not dict or "value_kind" not in payload:
        raise CharacteristicError("Profile characteristic payload requires value_kind.")
    if payload["value_kind"] == CharacteristicValueKind.RANDOM.value:
        return RandomProfileValue.from_payload(cast(RandomProfileValuePayload, payload))
    return CharacteristicValue.from_payload(cast(CharacteristicValuePayload, payload))


def canonical_profile_characteristics(
    values: tuple[ProfileCharacteristicValue, ...],
) -> tuple[ProfileCharacteristicValue, ...]:
    if type(values) is not tuple:
        raise CharacteristicError("Profile characteristics must be a tuple.")
    if any(type(value) not in {CharacteristicValue, RandomProfileValue} for value in values):
        raise CharacteristicError("Profile characteristics require typed values.")
    if len({value.characteristic for value in values}) != len(values):
        raise CharacteristicError("Profile characteristics must not contain duplicates.")
    return tuple(sorted(values, key=lambda value: value.characteristic.value))


def resolved_profile_characteristic(value: ProfileCharacteristicValue) -> CharacteristicValue:
    return value.resolved_value() if isinstance(value, RandomProfileValue) else value


def validate_catalog_random_values(
    values: tuple[ProfileCharacteristicValue, ...], *, source_ids: tuple[str, ...]
) -> None:
    """A catalog carries source expressions; runtime evaluations never belong in it."""
    for value in values:
        if not isinstance(value, RandomProfileValue):
            continue
        if value.source_id not in source_ids:
            raise CharacteristicError("Random profile source_id is not owned by its profile.")
        if value.evaluation is not None or value.modifiers:
            raise CharacteristicError(
                "Catalog random characteristics must be unresolved and unmodified."
            )


def with_random_profile_delta(
    value: RandomProfileValue, *, delta: int, source_id: str, modifier_id: str
) -> RandomProfileValue:
    """Bind a source operation before rolling, keeping intrinsic dice offsets distinct."""
    modifier = ModifierTerm(ModifierOperation.ADD, delta).bind(
        modifier_id=modifier_id, source_id=source_id, characteristic=value.characteristic
    )
    if modifier_id in value.applied_modifier_ids:
        if modifier not in value.modifiers:
            raise CharacteristicError("Random profile modifier identity drifted.")
        return value
    return replace(value.without_evaluation(), modifiers=(*value.modifiers, modifier))
