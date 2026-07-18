from __future__ import annotations

import re
from typing import cast

from warhammer40k_core.core.attributes import Characteristic
from warhammer40k_core.core.dice_errors import DiceRollSpecError
from warhammer40k_core.core.validation import IdentifierValidator

validate_identifier = IdentifierValidator(DiceRollSpecError)
_LABEL_PARTS = re.compile(r"[\s_]+")


def validate_replay_label(field_name: str, label: str, expression_label: str) -> str:
    stripped = label.strip()
    if not stripped:
        raise DiceRollSpecError(f"DiceRollSpec {field_name} must not be empty.")
    normalized = _LABEL_PARTS.sub("", stripped.casefold())
    canonical_expression = expression_label.casefold()
    generic_labels = {
        canonical_expression,
        f"roll{canonical_expression}",
        f"getroll{canonical_expression}",
        f"getroll({canonical_expression})",
    }
    if normalized in generic_labels:
        raise DiceRollSpecError(
            f"DiceRollSpec {field_name} must describe the rule reason, not a generic dice label."
        )
    return stripped


def validate_characteristic(characteristic: object) -> Characteristic:
    if type(characteristic) is not Characteristic:
        raise DiceRollSpecError("Expected a Characteristic.")
    return characteristic


def validate_identifier_tuple(
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
        identifier = validate_identifier(f"{field_name} value", value)
        if identifier in seen:
            raise DiceRollSpecError(f"{field_name} must not contain duplicate IDs.")
        seen.add(identifier)
        identifiers.append(identifier)
    if len(identifiers) < min_length:
        raise DiceRollSpecError(f"{field_name} must contain at least {min_length} values.")
    if sort_values:
        return tuple(sorted(identifiers))
    return tuple(identifiers)


def validate_int_tuple(field_name: str, values: object) -> tuple[int, ...]:
    if type(values) is not tuple:
        raise DiceRollSpecError(f"{field_name} must be a tuple.")
    validated: list[int] = []
    for value in cast(tuple[object, ...], values):
        if type(value) is not int:
            raise DiceRollSpecError(f"{field_name} must contain integers.")
        validated.append(value)
    return tuple(validated)
