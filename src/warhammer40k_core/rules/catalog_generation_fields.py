from __future__ import annotations

from warhammer40k_core.rules.catalog_generation_errors import CatalogGenerationError
from warhammer40k_core.rules.wahapedia_schema import NormalizedSourceRow


def required_field(*, row: NormalizedSourceRow, column_name: str) -> str:
    fields = row.runtime_fields_payload()
    if column_name not in fields:
        raise CatalogGenerationError(
            f"Required source column {column_name} is missing from {row.stable_source_id()}."
        )
    value = fields[column_name].strip()
    if not value:
        raise CatalogGenerationError(
            f"Required source column {column_name} is empty in {row.stable_source_id()}."
        )
    return value


def optional_field(*, row: NormalizedSourceRow, column_name: str) -> str | None:
    value = row.runtime_fields_payload().get(column_name)
    if value is None:
        return None
    stripped = value.strip()
    return stripped if stripped else None


def split_field_value(value: str) -> tuple[str, ...]:
    items = tuple(item.strip() for item in value.split(",") if item.strip())
    if not items:
        raise CatalogGenerationError("Required list field must not be empty.")
    seen: set[str] = set()
    unique: list[str] = []
    for item in items:
        if item in seen:
            raise CatalogGenerationError("Required list field must not contain duplicates.")
        seen.add(item)
        unique.append(item)
    return tuple(unique)


def required_split_field(row: NormalizedSourceRow, column_name: str) -> tuple[str, ...]:
    return split_field_value(required_field(row=row, column_name=column_name))


def optional_split_field(row: NormalizedSourceRow, column_name: str) -> tuple[str, ...]:
    value = row.runtime_fields_payload().get(column_name)
    if value is None or not value.strip():
        return ()
    return split_field_value(value)


__all__ = (
    "optional_field",
    "optional_split_field",
    "required_field",
    "required_split_field",
    "split_field_value",
)
