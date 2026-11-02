"""Model profile collection validation, shared by typed catalog definitions."""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from warhammer40k_core.core.datasheet import ModelProfileDefinition


def validate_model_profile_tuple(
    field_name: str,
    values: tuple[ModelProfileDefinition, ...],
) -> tuple[ModelProfileDefinition, ...]:
    from warhammer40k_core.core.datasheet import DatasheetCatalogError, ModelProfileDefinition

    if type(values) is not tuple:
        raise DatasheetCatalogError(f"{field_name} must be a tuple.")
    if not values:
        raise DatasheetCatalogError(f"{field_name} must not be empty.")
    seen: set[str] = set()
    validated: list[ModelProfileDefinition] = []
    for value in values:
        if type(value) is not ModelProfileDefinition:
            raise DatasheetCatalogError(f"{field_name} must contain model profile definitions.")
        if value.model_profile_id in seen:
            raise DatasheetCatalogError(f"{field_name} must not contain duplicate IDs.")
        seen.add(value.model_profile_id)
        validated.append(value)
    return tuple(validated)
