"""Source-linked fixed or random weapon Attacks and Damage profiles."""

from __future__ import annotations

from dataclasses import dataclass, replace
from typing import NotRequired, Self, TypedDict, cast

from warhammer40k_core.core.attributes import Characteristic
from warhammer40k_core.core.dice import DiceExpression, DiceExpressionPayload, DiceRollSpecError
from warhammer40k_core.core.modifiers import Modifier, ModifierPayload
from warhammer40k_core.core.profile_modifier_trace import CharacteristicModifierTrace
from warhammer40k_core.core.weapon_profile_errors import WeaponProfileError


class AttackProfilePayload(TypedDict):
    fixed_attacks: int | None
    dice_expression: DiceExpressionPayload | None
    source_fixed_value: NotRequired[int | None]
    modifiers: NotRequired[list[ModifierPayload]]
    ignored_modifier_ids: NotRequired[list[str]]


class DamageProfilePayload(TypedDict):
    fixed_damage: int | None
    dice_expression: DiceExpressionPayload | None
    source_fixed_value: NotRequired[int | None]
    modifiers: NotRequired[list[ModifierPayload]]
    ignored_modifier_ids: NotRequired[list[str]]


@dataclass(frozen=True, slots=True)
class AttackProfile:
    fixed_attacks: int | None = None
    dice_expression: DiceExpression | None = None
    source_fixed_value: int | None = None
    modifiers: tuple[Modifier, ...] = ()
    ignored_modifier_ids: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        if type(self.modifiers) is not tuple or type(self.ignored_modifier_ids) is not tuple:
            raise WeaponProfileError("Count profile operations and selections must be tuples.")
        _validate_exactly_one_expression(
            "AttackProfile",
            self.fixed_attacks,
            self.dice_expression,
        )
        if self.fixed_attacks is not None:
            _validate_positive_int("AttackProfile fixed_attacks", self.fixed_attacks)
        if self.dice_expression is not None:
            _validate_dice_expression("AttackProfile dice_expression", self.dice_expression)

        if self.modifiers:
            trace = CharacteristicModifierTrace(
                Characteristic.ATTACKS,
                1 if self.source_fixed_value is None else self.source_fixed_value,
                self.modifiers,
                ignored_modifier_ids=self.ignored_modifier_ids,
            )
            if self.fixed_attacks is not None and (
                self.source_fixed_value is None or trace.resolve().final != self.fixed_attacks
            ):
                raise WeaponProfileError("AttackProfile modifier arithmetic or source drift.")
            if self.dice_expression is not None and self.source_fixed_value is not None:
                raise WeaponProfileError("Random AttackProfile must not have a fixed source.")
        elif self.source_fixed_value is not None or self.ignored_modifier_ids:
            raise WeaponProfileError("AttackProfile modifier metadata requires operations.")

    def with_modifier(self, modifier: Modifier) -> Self:
        source = self.source_fixed_value if self.modifiers else self.fixed_attacks
        modifiers = (*self.modifiers, modifier)
        trace = CharacteristicModifierTrace(
            Characteristic.ATTACKS,
            1 if source is None else source,
            modifiers,
            ignored_modifier_ids=self.ignored_modifier_ids,
        )
        return replace(
            self,
            source_fixed_value=source,
            modifiers=modifiers,
            fixed_attacks=None if source is None else trace.resolve().final,
        )

    def resolve_value(
        self, raw: int, *, ignored_modifier_ids: tuple[str, ...] | None = None
    ) -> int:
        return (
            CharacteristicModifierTrace(
                Characteristic.ATTACKS,
                self.source_fixed_value if self.source_fixed_value is not None else raw,
                self.modifiers,
                ignored_modifier_ids=(
                    self.ignored_modifier_ids
                    if ignored_modifier_ids is None
                    else ignored_modifier_ids
                ),
            )
            .resolve()
            .final
        )

    @classmethod
    def fixed(cls, attacks: int) -> Self:
        return cls(fixed_attacks=attacks)

    @classmethod
    def dice(cls, expression: DiceExpression) -> Self:
        return cls(dice_expression=expression)

    def to_payload(self) -> AttackProfilePayload:
        dice_payload = None
        if self.dice_expression is not None:
            dice_payload = self.dice_expression.to_payload()
        payload: AttackProfilePayload = {
            "fixed_attacks": self.fixed_attacks,
            "dice_expression": dice_payload,
        }
        if self.modifiers:
            payload["source_fixed_value"] = self.source_fixed_value
            payload["modifiers"] = [item.to_payload() for item in self.modifiers]
            payload["ignored_modifier_ids"] = list(self.ignored_modifier_ids)
        return payload

    @classmethod
    def from_payload(cls, payload: AttackProfilePayload) -> Self:
        _validate_payload(cast(dict[str, object], payload), fixed_key="fixed_attacks")
        dice_payload = payload["dice_expression"]
        try:
            return cls(
                fixed_attacks=payload["fixed_attacks"],
                source_fixed_value=payload.get("source_fixed_value"),
                modifiers=tuple(
                    Modifier.from_payload(item) for item in payload.get("modifiers", [])
                ),
                ignored_modifier_ids=tuple(payload.get("ignored_modifier_ids", [])),
                dice_expression=(
                    None if dice_payload is None else DiceExpression.from_payload(dice_payload)
                ),
            )
        except DiceRollSpecError as exc:
            raise WeaponProfileError("AttackProfile dice_expression payload is invalid.") from exc


@dataclass(frozen=True, slots=True)
class DamageProfile:
    fixed_damage: int | None = None
    dice_expression: DiceExpression | None = None
    source_fixed_value: int | None = None
    modifiers: tuple[Modifier, ...] = ()
    ignored_modifier_ids: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        if type(self.modifiers) is not tuple or type(self.ignored_modifier_ids) is not tuple:
            raise WeaponProfileError("Count profile operations and selections must be tuples.")
        _validate_exactly_one_expression(
            "DamageProfile",
            self.fixed_damage,
            self.dice_expression,
        )
        if self.fixed_damage is not None:
            _validate_positive_int("DamageProfile fixed_damage", self.fixed_damage)
        if self.dice_expression is not None:
            _validate_dice_expression("DamageProfile dice_expression", self.dice_expression)

        if self.modifiers:
            trace = CharacteristicModifierTrace(
                Characteristic.DAMAGE,
                1 if self.source_fixed_value is None else self.source_fixed_value,
                self.modifiers,
                ignored_modifier_ids=self.ignored_modifier_ids,
            )
            if self.fixed_damage is not None and (
                self.source_fixed_value is None or trace.resolve().final != self.fixed_damage
            ):
                raise WeaponProfileError("DamageProfile modifier arithmetic or source drift.")
            if self.dice_expression is not None and self.source_fixed_value is not None:
                raise WeaponProfileError("Random DamageProfile must not have a fixed source.")
        elif self.source_fixed_value is not None or self.ignored_modifier_ids:
            raise WeaponProfileError("DamageProfile modifier metadata requires operations.")

    def with_modifier(self, modifier: Modifier) -> Self:
        source = self.source_fixed_value if self.modifiers else self.fixed_damage
        modifiers = (*self.modifiers, modifier)
        trace = CharacteristicModifierTrace(
            Characteristic.DAMAGE,
            1 if source is None else source,
            modifiers,
            ignored_modifier_ids=self.ignored_modifier_ids,
        )
        return replace(
            self,
            source_fixed_value=source,
            modifiers=modifiers,
            fixed_damage=None if source is None else trace.resolve().final,
        )

    def resolve_value(
        self, raw: int, *, ignored_modifier_ids: tuple[str, ...] | None = None
    ) -> int:
        return (
            CharacteristicModifierTrace(
                Characteristic.DAMAGE,
                self.source_fixed_value if self.source_fixed_value is not None else raw,
                self.modifiers,
                ignored_modifier_ids=(
                    self.ignored_modifier_ids
                    if ignored_modifier_ids is None
                    else ignored_modifier_ids
                ),
            )
            .resolve()
            .final
        )

    @classmethod
    def fixed(cls, damage: int) -> Self:
        return cls(fixed_damage=damage)

    @classmethod
    def dice(cls, expression: DiceExpression) -> Self:
        return cls(dice_expression=expression)

    def to_payload(self) -> DamageProfilePayload:
        dice_payload = None
        if self.dice_expression is not None:
            dice_payload = self.dice_expression.to_payload()
        payload: DamageProfilePayload = {
            "fixed_damage": self.fixed_damage,
            "dice_expression": dice_payload,
        }
        if self.modifiers:
            payload["source_fixed_value"] = self.source_fixed_value
            payload["modifiers"] = [item.to_payload() for item in self.modifiers]
            payload["ignored_modifier_ids"] = list(self.ignored_modifier_ids)
        return payload

    @classmethod
    def from_payload(cls, payload: DamageProfilePayload) -> Self:
        _validate_payload(cast(dict[str, object], payload), fixed_key="fixed_damage")
        dice_payload = payload["dice_expression"]
        try:
            return cls(
                fixed_damage=payload["fixed_damage"],
                source_fixed_value=payload.get("source_fixed_value"),
                modifiers=tuple(
                    Modifier.from_payload(item) for item in payload.get("modifiers", [])
                ),
                ignored_modifier_ids=tuple(payload.get("ignored_modifier_ids", [])),
                dice_expression=(
                    None if dice_payload is None else DiceExpression.from_payload(dice_payload)
                ),
            )
        except DiceRollSpecError as exc:
            raise WeaponProfileError("DamageProfile dice_expression payload is invalid.") from exc


def _validate_positive_int(field_name: str, value: object) -> int:
    if type(value) is not int:
        raise WeaponProfileError(f"{field_name} must be an integer.")
    if value < 1:
        raise WeaponProfileError(f"{field_name} must be at least 1.")
    return value


def _validate_exactly_one_expression(
    field_name: str,
    fixed_value: object | None,
    dice_expression: object | None,
) -> None:
    if fixed_value is None and dice_expression is None:
        raise WeaponProfileError(f"{field_name} must include a parsed value.")
    if fixed_value is not None and dice_expression is not None:
        raise WeaponProfileError(f"{field_name} must not mix fixed and dice values.")


def _validate_dice_expression(field_name: str, expression: object) -> DiceExpression:
    if type(expression) is not DiceExpression:
        raise WeaponProfileError(f"{field_name} must be a DiceExpression.")
    return expression


def _validate_payload(payload: dict[str, object], *, fixed_key: str) -> None:
    required = {fixed_key, "dice_expression"}
    extra = {"source_fixed_value", "modifiers", "ignored_modifier_ids"}
    if type(payload) is not dict or set(payload) not in (required, required | extra):
        raise WeaponProfileError("Count profile fields or modifier evidence are invalid.")
    if "modifiers" in payload:
        if type(payload["modifiers"]) is not list or not payload["modifiers"]:
            raise WeaponProfileError("Count profile modifier evidence requires source operations.")
        if type(payload["ignored_modifier_ids"]) is not list:
            raise WeaponProfileError("Count profile modifier selection requires an array.")
        CharacteristicModifierTrace.from_payload(
            {
                "characteristic": (
                    Characteristic.ATTACKS.value
                    if fixed_key == "fixed_attacks"
                    else Characteristic.DAMAGE.value
                ),
                "source_value": (
                    1
                    if payload["source_fixed_value"] is None
                    else cast(int, payload["source_fixed_value"])
                ),
                "modifiers": cast(list[ModifierPayload], payload["modifiers"]),
                "bounded": True,
                "ignored_modifier_ids": cast(list[str], payload["ignored_modifier_ids"]),
            }
        )
    dice = payload["dice_expression"]
    if dice is not None and (
        type(dice) is not dict
        or set(cast(dict[str, object], dice)) != {"quantity", "sides", "modifier"}
    ):
        raise WeaponProfileError("Count profile dice expression fields are invalid.")
