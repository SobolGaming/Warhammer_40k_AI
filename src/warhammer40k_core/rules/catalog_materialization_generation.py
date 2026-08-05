from __future__ import annotations

from warhammer40k_core.rules.wahapedia_schema import NormalizedSourceRow


def mustering_rows(
    rows: tuple[NormalizedSourceRow, ...], error_type: type[ValueError]
) -> tuple[NormalizedSourceRow, ...]:
    return tuple(row for row in rows if not _is_materialization_only(row, error_type))


def _is_materialization_only(row: NormalizedSourceRow, error_type: type[ValueError]) -> bool:
    value = row.runtime_fields_payload().get("materialization_only")
    if value is None or not value.strip():
        return False
    normalized = value.strip().casefold()
    if normalized == "true":
        return True
    if normalized == "false":
        return False
    raise error_type("Source row materialization_only must be true or false.")


__all__ = ("mustering_rows",)
