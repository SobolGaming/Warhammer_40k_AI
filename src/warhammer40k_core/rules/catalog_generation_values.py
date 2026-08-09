from __future__ import annotations

import re

from warhammer40k_core.core.attributes import Characteristic, CharacteristicValue
from warhammer40k_core.core.dice import DiceExpression, DiceRollSpecError
from warhammer40k_core.core.weapon_profiles import AttackProfile, DamageProfile, RangeProfile
from warhammer40k_core.rules.catalog_generation_errors import CatalogGenerationError
from warhammer40k_core.rules.catalog_generation_fields import optional_field, required_field
from warhammer40k_core.rules.wahapedia_schema import NormalizedSourceRow

_DICE_CHARACTERISTIC_RE = re.compile(
    r"^(?P<quantity>\d*)D(?P<sides>\d+)(?P<modifier>[+-]\d+)?$",
    re.IGNORECASE,
)
_INTEGER_CHARACTERISTIC_RE = re.compile(r"^[+-]?\d+$")


def characteristic_from_row(
    *,
    row: NormalizedSourceRow,
    column_name: str,
    characteristic: Characteristic,
) -> CharacteristicValue:
    return characteristic_value_from_raw_text(
        characteristic=characteristic,
        raw_text=required_field(row=row, column_name=column_name),
    )


def optional_characteristic_from_row(
    *,
    row: NormalizedSourceRow,
    column_name: str,
    characteristic: Characteristic,
) -> CharacteristicValue:
    return characteristic_value_from_raw_text(
        characteristic=characteristic,
        raw_text=optional_field(row=row, column_name=column_name) or "-",
    )


def characteristic_value_from_raw_text(
    *,
    characteristic: Characteristic,
    raw_text: str,
) -> CharacteristicValue:
    text = raw_text.strip()
    if text == "-":
        return CharacteristicValue.source_dash(characteristic)
    return CharacteristicValue.from_raw(characteristic, _int_from_text(text))


def characteristic_token_from_field(value: str) -> Characteristic:
    if value == Characteristic.BALLISTIC_SKILL.value:
        return Characteristic.BALLISTIC_SKILL
    if value == Characteristic.WEAPON_SKILL.value:
        return Characteristic.WEAPON_SKILL
    raise CatalogGenerationError(
        "Weapon skill_characteristic must be weapon_skill or ballistic_skill."
    )


def range_profile_from_token(value: str) -> RangeProfile:
    if value.strip().lower() == "melee":
        return RangeProfile.melee()
    return RangeProfile.distance(_int_from_text(value))


def attack_profile_from_raw_text(value: str) -> AttackProfile:
    fixed = _optional_int_from_text(value)
    if fixed is not None:
        if fixed < 1:
            raise CatalogGenerationError("Attack profile fixed attacks must be at least 1.")
        return AttackProfile.fixed(fixed)
    return AttackProfile.dice(_dice_expression_from_text(value))


def damage_profile_from_raw_text(value: str) -> DamageProfile:
    fixed = _optional_int_from_text(value)
    if fixed is not None:
        if fixed < 1:
            raise CatalogGenerationError("Damage profile fixed damage must be at least 1.")
        return DamageProfile.fixed(fixed)
    return DamageProfile.dice(_dice_expression_from_text(value))


def required_positive_int(row: NormalizedSourceRow, column_name: str) -> int:
    value = _required_int(row=row, column_name=column_name)
    if value < 1:
        raise CatalogGenerationError(f"Source row {column_name} must be at least 1.")
    return value


def required_non_negative_int(row: NormalizedSourceRow, column_name: str) -> int:
    value = _required_int(row=row, column_name=column_name)
    if value < 0:
        raise CatalogGenerationError(f"Source row {column_name} must not be negative.")
    return value


def optional_positive_int(row: NormalizedSourceRow, column_name: str) -> int | None:
    value = optional_field(row=row, column_name=column_name)
    if value is None:
        return None
    integer = _int_from_text(value)
    if integer < 1:
        raise CatalogGenerationError(f"Source row {column_name} must be at least 1.")
    return integer


def required_bool(row: NormalizedSourceRow, column_name: str) -> bool:
    value = required_field(row=row, column_name=column_name).casefold()
    if value == "true":
        return True
    if value == "false":
        return False
    raise CatalogGenerationError(f"Source row {column_name} must be true or false.")


def required_number(row: NormalizedSourceRow, column_name: str) -> float:
    value = required_field(row=row, column_name=column_name)
    try:
        return float(value)
    except ValueError as exc:
        raise CatalogGenerationError(f"Source row {column_name} must be numeric.") from exc


def _required_int(row: NormalizedSourceRow, column_name: str) -> int:
    return _int_from_text(required_field(row=row, column_name=column_name))


def _dice_expression_from_text(value: str) -> DiceExpression:
    match = _DICE_CHARACTERISTIC_RE.fullmatch(value.strip().replace(" ", ""))
    if match is None:
        raise CatalogGenerationError(
            f"Source value must be fixed integer or dice expression: {value}."
        )
    quantity_token = match.group("quantity")
    quantity = 1 if not quantity_token else _int_from_text(quantity_token)
    sides = _int_from_text(match.group("sides"))
    modifier_token = match.group("modifier")
    modifier = 0 if modifier_token is None else _int_from_text(modifier_token)
    try:
        return DiceExpression(quantity=quantity, sides=sides, modifier=modifier)
    except DiceRollSpecError as exc:
        raise CatalogGenerationError("Source dice expression is invalid.") from exc


def _int_from_text(value: str) -> int:
    normalized = value.strip().removesuffix('"').removesuffix("+")
    try:
        return int(normalized)
    except ValueError as exc:
        raise CatalogGenerationError(f"Source value must be an integer: {value}.") from exc


def _optional_int_from_text(value: str) -> int | None:
    normalized = value.strip().removesuffix('"').removesuffix("+")
    if _INTEGER_CHARACTERISTIC_RE.fullmatch(normalized) is None:
        return None
    return int(normalized)


__all__ = (
    "attack_profile_from_raw_text",
    "characteristic_from_row",
    "characteristic_token_from_field",
    "characteristic_value_from_raw_text",
    "damage_profile_from_raw_text",
    "optional_characteristic_from_row",
    "optional_positive_int",
    "range_profile_from_token",
    "required_bool",
    "required_non_negative_int",
    "required_number",
    "required_positive_int",
)
