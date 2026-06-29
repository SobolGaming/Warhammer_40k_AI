from __future__ import annotations

import hashlib
from collections.abc import Callable, Mapping
from typing import cast

from warhammer40k_core.engine.event_log import JsonValue, canonical_json, validate_json_value
from warhammer40k_core.engine.phase import GameLifecycleError


def contribution_values[TContribution, TValue](
    contributions: tuple[TContribution, ...],
    getter: Callable[[TContribution], tuple[TValue, ...]],
) -> tuple[TValue, ...]:
    return tuple(value for contribution in contributions for value in getter(contribution))


def validate_tuple[T](
    field_name: str,
    value: object,
    expected_type: type[T],
) -> tuple[T, ...]:
    if type(value) is not tuple:
        raise GameLifecycleError(f"{field_name} must be a tuple.")
    validated: list[T] = []
    for item in cast(tuple[object, ...], value):
        if type(item) is not expected_type:
            raise GameLifecycleError(f"{field_name} contains invalid values.")
        validated.append(item)
    return tuple(validated)


def validate_identifier(field_name: str, value: object) -> str:
    if type(value) is not str:
        raise GameLifecycleError(f"Runtime content {field_name} must be a string.")
    stripped = value.strip()
    if not stripped:
        raise GameLifecycleError(f"Runtime content {field_name} must not be empty.")
    return stripped


def validate_identifier_tuple(field_name: str, values: object) -> tuple[str, ...]:
    if type(values) is not tuple:
        raise GameLifecycleError(f"Runtime content {field_name} must be a tuple.")
    seen: set[str] = set()
    identifiers: list[str] = []
    for value in cast(tuple[object, ...], values):
        identifier = validate_identifier(f"{field_name} value", value)
        if identifier in seen:
            raise GameLifecycleError(f"Runtime content {field_name} must not contain duplicates.")
        seen.add(identifier)
        identifiers.append(identifier)
    return tuple(sorted(identifiers))


def summary_hash(payload: Mapping[str, JsonValue]) -> str:
    serialized = canonical_json(validate_json_value(dict(payload)))
    return hashlib.sha256(serialized.encode("utf-8")).hexdigest()
