from __future__ import annotations

from warhammer40k_core.rules.catalog_generation_errors import CatalogGenerationError
from warhammer40k_core.rules.wahapedia_schema import NormalizedSourceRow


def allows_zero_models_from_row(row: NormalizedSourceRow) -> bool:
    value = row.runtime_fields_payload().get("allows_zero_models")
    if value is None or not value.strip():
        return False
    normalized = value.strip().casefold()
    if normalized == "true":
        return True
    if normalized == "false":
        return False
    raise CatalogGenerationError("Source row allows_zero_models must be true or false.")


def composition_min_models_from_row(row: NormalizedSourceRow) -> int:
    value = row.runtime_fields_payload().get("min_models")
    if value is None or not value.strip():
        raise CatalogGenerationError("Source row requires field: min_models.")
    try:
        minimum = int(value)
    except ValueError as exc:
        raise CatalogGenerationError("Source value must be an integer: min_models.") from exc
    if minimum < 0:
        raise CatalogGenerationError("Source row min_models must not be negative.")
    if minimum == 0 and not allows_zero_models_from_row(row):
        raise CatalogGenerationError("Source row min_models must be at least 1.")
    return minimum
