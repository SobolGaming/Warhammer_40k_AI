from __future__ import annotations

from collections.abc import Callable
from typing import cast

from warhammer40k_core.core.validation import IdentifierValidator
from warhammer40k_core.engine.event_log import JsonValue
from warhammer40k_core.engine.phase import GameLifecycleError

validate_identifier = IdentifierValidator(GameLifecycleError)


def validate_exact_type_tuple[T](
    values: object,
    *,
    item_type: type[T],
    collection_label: str,
) -> tuple[T, ...]:
    if type(values) is not tuple:
        raise GameLifecycleError(f"{collection_label} must be a tuple.")
    validated: list[T] = []
    for value in cast(tuple[object, ...], values):
        if type(value) is not item_type:
            raise GameLifecycleError(
                f"{collection_label} must contain {item_type.__name__} values."
            )
        validated.append(value)
    return tuple(validated)


def validate_unique_sorted_exact_type_tuple[T](
    values: object,
    *,
    item_type: type[T],
    collection_label: str,
    identity: Callable[[T], str],
    duplicate_message: str,
    forbidden_identity: str | None = None,
    forbidden_message: str | None = None,
) -> tuple[T, ...]:
    typed = validate_exact_type_tuple(
        values,
        item_type=item_type,
        collection_label=collection_label,
    )
    identities = tuple(identity(value) for value in typed)
    if len(identities) != len(set(identities)):
        raise GameLifecycleError(duplicate_message)
    if forbidden_identity is not None and forbidden_identity in identities:
        if forbidden_message is None:
            raise GameLifecycleError("Forbidden tuple identity lacks a diagnostic.")
        raise GameLifecycleError(forbidden_message)
    return tuple(sorted(typed, key=identity))


def validate_identifier_tuple(field_name: str, values: object) -> tuple[str, ...]:
    if type(values) is not tuple:
        raise GameLifecycleError(f"{field_name} must be a tuple.")
    identifiers = tuple(
        validate_identifier(f"{field_name} value", value)
        for value in cast(tuple[object, ...], values)
    )
    if len(identifiers) != len(set(identifiers)):
        raise GameLifecycleError(f"{field_name} must not contain duplicates.")
    return tuple(sorted(identifiers))


def validate_ordered_identifier_tuple(field_name: str, values: object) -> tuple[str, ...]:
    identifiers = validate_identifier_tuple(field_name, values)
    if not identifiers:
        raise GameLifecycleError(f"{field_name} must not be empty.")
    requested = cast(tuple[object, ...], values)
    return tuple(validate_identifier(f"{field_name} value", value) for value in requested)


def validate_optional_identifier(field_name: str, value: object | None) -> str | None:
    if value is None:
        return None
    return validate_identifier(field_name, value)


def validate_positive_int(field_name: str, value: object) -> int:
    if type(value) is not int:
        raise GameLifecycleError(f"{field_name} must be an int.")
    if value < 1:
        raise GameLifecycleError(f"{field_name} must be at least 1.")
    return value


def validate_non_negative_int(field_name: str, value: object) -> int:
    if type(value) is not int:
        raise GameLifecycleError(f"{field_name} must be an int.")
    if value < 0:
        raise GameLifecycleError(f"{field_name} must not be negative.")
    return value


def validate_d6_target(field_name: str, value: object) -> int:
    if type(value) is not int:
        raise GameLifecycleError(f"{field_name} must be an int.")
    if value < 2 or value > 6:
        raise GameLifecycleError(f"{field_name} must be between 2 and 6.")
    return value


def validate_optional_save(field_name: str, value: object | None) -> int | None:
    if value is None:
        return None
    return validate_d6_target(field_name, value)


def validate_model_identifier_subset(
    *,
    field_name: str,
    values: tuple[str, ...],
    universe: tuple[str, ...],
) -> None:
    if set(values) - set(universe):
        raise GameLifecycleError(f"{field_name} contains models outside alive_model_ids.")


def decision_payload_object(payload: JsonValue) -> dict[str, JsonValue]:
    if not isinstance(payload, dict):
        raise GameLifecycleError("Decision payload must be an object.")
    return payload


def decision_payload_string(payload: dict[str, JsonValue], *, key: str) -> str:
    if key not in payload:
        raise GameLifecycleError(f"Decision payload missing {key}.")
    value = payload[key]
    if type(value) is not str:
        raise GameLifecycleError(f"Decision payload {key} must be a string.")
    return value


def decision_payload_string_tuple(
    payload: dict[str, JsonValue],
    *,
    key: str,
) -> tuple[str, ...]:
    if key not in payload:
        raise GameLifecycleError(f"Decision payload missing {key}.")
    value = payload[key]
    if not isinstance(value, list):
        raise GameLifecycleError(f"Decision payload {key} must be a list.")
    return validate_ordered_identifier_tuple(key, tuple(value))


__all__ = (
    "decision_payload_object",
    "decision_payload_string",
    "decision_payload_string_tuple",
    "validate_d6_target",
    "validate_exact_type_tuple",
    "validate_identifier",
    "validate_identifier_tuple",
    "validate_model_identifier_subset",
    "validate_non_negative_int",
    "validate_optional_identifier",
    "validate_optional_save",
    "validate_ordered_identifier_tuple",
    "validate_positive_int",
    "validate_unique_sorted_exact_type_tuple",
)
