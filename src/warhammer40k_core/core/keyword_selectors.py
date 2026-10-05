"""Validate explicit native selectors without classifying runtime inventories."""

from collections.abc import Iterable
from typing import cast


def native_keyword_selectors(
    values: object, *, allowed: Iterable[str], error_type: type[ValueError]
) -> tuple[str, ...]:
    if type(values) is not tuple:
        raise error_type("Native keyword selectors must be a tuple.")
    result: list[str] = []
    for value in cast(tuple[object, ...], values):
        if type(value) is not str or not value.strip():
            raise error_type("Native keyword selectors must contain keyword strings.")
        token = value.strip().upper()
        if token in result:
            raise error_type("Native keyword selectors must not contain duplicates.")
        result.append(token)
    if not set(result).issubset(allowed):
        raise error_type("Native keyword selectors must occur in the selector inventory.")
    return tuple(sorted(result))


def native_selectors_from_payload(
    value: object, *, error_type: type[ValueError]
) -> tuple[str, ...]:
    if type(value) is not list or any(type(item) is not str for item in cast(list[object], value)):
        raise error_type("Native keyword selector payload must be a string list.")
    return tuple(cast(list[str], value))
