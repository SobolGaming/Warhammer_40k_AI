from __future__ import annotations

from typing import cast

from warhammer40k_core.core.mission_errors import MissionPackError
from warhammer40k_core.core.validation import IdentifierValidator

_validate_identifier = IdentifierValidator(MissionPackError)


def validate_identifier_tuple(
    field_name: str,
    values: object,
    *,
    min_length: int,
    sort_values: bool,
) -> tuple[str, ...]:
    """Validate the ordered identifier collections used by mission definitions."""
    if type(values) is not tuple:
        raise MissionPackError(f"{field_name} must be a tuple.")
    validated: list[str] = []
    seen: set[str] = set()
    for value in cast(tuple[object, ...], values):
        identifier = _validate_identifier(f"{field_name} value", value)
        if identifier in seen:
            raise MissionPackError(f"{field_name} must not contain duplicates.")
        seen.add(identifier)
        validated.append(identifier)
    if len(validated) < min_length:
        raise MissionPackError(f"{field_name} must contain at least {min_length} values.")
    if sort_values:
        return tuple(sorted(validated))
    return tuple(validated)


__all__ = ("validate_identifier_tuple",)
