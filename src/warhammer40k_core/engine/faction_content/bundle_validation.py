from __future__ import annotations

import hashlib
from collections.abc import Callable, Mapping
from types import MappingProxyType
from typing import cast

from warhammer40k_core.engine.event_log import JsonValue, canonical_json, validate_json_value
from warhammer40k_core.engine.phase import GameLifecycleError
from warhammer40k_core.engine.reserve_arrival_hooks import (
    ReserveArrivalDistanceHookRegistry,
    ReserveArrivalRestrictionHookRegistry,
)


def contribution_values[TContribution, TValue](
    contributions: tuple[TContribution, ...],
    getter: Callable[[TContribution], tuple[TValue, ...]],
) -> tuple[TValue, ...]:
    return tuple(value for contribution in contributions for value in getter(contribution))


def combine_unique_values[T](
    field_name: str,
    values: tuple[T, ...],
    identifier_for: Callable[[T], str],
) -> tuple[T, ...]:
    seen: set[str] = set()
    combined: list[T] = []
    for value in values:
        identifier = validate_identifier(f"{field_name} id", identifier_for(value))
        if identifier in seen:
            raise GameLifecycleError(f"Runtime content {field_name} IDs must be unique.")
        seen.add(identifier)
        combined.append(value)
    return tuple(combined)


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


def validate_contribution_tuple[T](
    field_name: str,
    value: object,
    expected_type: type[T],
) -> tuple[T, ...]:
    return validate_tuple(
        f"RuntimeContentContribution {field_name}",
        value,
        expected_type,
    )


def validate_runtime_content_contributions[T](
    value: object,
    expected_type: type[T],
) -> tuple[T, ...]:
    if type(value) is not tuple:
        raise GameLifecycleError("Runtime content contributions must be a tuple.")
    validated: list[T] = []
    for item in cast(tuple[object, ...], value):
        if type(item) is not expected_type:
            raise GameLifecycleError(
                "Runtime content contributions must contain RuntimeContentContribution values."
            )
        validated.append(item)
    return tuple(validated)


def validate_index_mapping[T](
    field_name: str,
    value: object,
    expected_type: type[T],
) -> Mapping[str, T]:
    if not isinstance(value, Mapping):
        raise GameLifecycleError(f"Runtime content {field_name} must be a mapping.")
    validated: dict[str, T] = {}
    for raw_player_id, index in cast(Mapping[object, object], value).items():
        player_id = validate_identifier("player_id", raw_player_id)
        if type(index) is not expected_type:
            raise GameLifecycleError(f"Runtime content {field_name} contains invalid index.")
        validated[player_id] = index
    return MappingProxyType(dict(sorted(validated.items())))


def merge_records[T](
    field_name: str,
    base_records: object,
    contribution_records: tuple[T, ...],
    expected_type: type[T],
) -> tuple[T, ...]:
    return (
        *validate_tuple(f"base {field_name}", base_records, expected_type),
        *validate_tuple(f"contribution {field_name}", contribution_records, expected_type),
    )


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


def validate_reserve_arrival_hook_registries(
    distance_registry: object,
    restriction_registry: object,
) -> None:
    if type(distance_registry) is not ReserveArrivalDistanceHookRegistry:
        raise GameLifecycleError(
            "RuntimeContentBundle requires ReserveArrivalDistanceHookRegistry."
        )
    if type(restriction_registry) is not ReserveArrivalRestrictionHookRegistry:
        raise GameLifecycleError(
            "RuntimeContentBundle requires ReserveArrivalRestrictionHookRegistry."
        )
