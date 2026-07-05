from __future__ import annotations

from warhammer40k_core.rules.source_overlay import OverlaySourceArtifact
from warhammer40k_core.rules.wahapedia_schema import NormalizedSourceRow, WahapediaJsonArtifact

BridgeSourceArtifact = WahapediaJsonArtifact | OverlaySourceArtifact


def bridge_rows_by_table(
    source_artifacts: tuple[BridgeSourceArtifact, ...],
    *,
    error_type: type[ValueError],
) -> dict[str, tuple[NormalizedSourceRow, ...]]:
    rows_by_table: dict[str, tuple[NormalizedSourceRow, ...]] = {}
    for artifact in source_artifacts:
        if type(artifact) not in {WahapediaJsonArtifact, OverlaySourceArtifact}:
            raise error_type(
                "source_artifacts must contain WahapediaJsonArtifact or OverlaySourceArtifact "
                "values."
            )
        existing = rows_by_table.get(artifact.source_table, ())
        rows_by_table[artifact.source_table] = (
            *existing,
            *(row for row in artifact.rows if not _row_is_superseded(row)),
        )
    return rows_by_table


def resolve_bridge_ability_source_row(
    *,
    rows_by_table: dict[str, tuple[NormalizedSourceRow, ...]],
    ability_row: NormalizedSourceRow,
    error_type: type[ValueError],
) -> NormalizedSourceRow:
    ability_id = _required_field(ability_row, "ability_id", error_type=error_type)
    candidate_rows = tuple(
        row
        for row in rows_by_table.get("Abilities", ())
        if _required_field(row, "id", error_type=error_type) == ability_id
    )
    if not candidate_rows:
        raise error_type("Datasheet ability link references a missing ability row.")
    if len(candidate_rows) == 1:
        return candidate_rows[0]
    datasheet_faction_id = _datasheet_faction_id_for_ability_row(
        rows_by_table=rows_by_table,
        ability_row=ability_row,
        error_type=error_type,
    )
    matching_faction_rows = tuple(
        row
        for row in candidate_rows
        if _required_field(row, "faction_id", error_type=error_type) == datasheet_faction_id
    )
    if len(matching_faction_rows) == 1:
        return matching_faction_rows[0]
    if len(matching_faction_rows) > 1:
        raise error_type("Datasheet ability link has duplicate faction ability rows.")
    for row in candidate_rows:
        if not _required_field(row, "faction_id", error_type=error_type):
            return row
    raise error_type("Datasheet ability link is ambiguous.")


def _datasheet_faction_id_for_ability_row(
    *,
    rows_by_table: dict[str, tuple[NormalizedSourceRow, ...]],
    ability_row: NormalizedSourceRow,
    error_type: type[ValueError],
) -> str:
    datasheet_id = _required_field(ability_row, "datasheet_id", error_type=error_type)
    for row in rows_by_table.get("Datasheets", ()):
        if row.source_row_id == datasheet_id:
            return _required_field(row, "faction_id", error_type=error_type)
    raise error_type("Datasheet ability link references a missing datasheet row.")


def _row_is_superseded(row: NormalizedSourceRow) -> bool:
    return bool(row.runtime_fields_payload().get("core_v2_superseded_by", "").strip())


def _required_field(
    row: NormalizedSourceRow,
    column_name: str,
    *,
    error_type: type[ValueError],
) -> str:
    fields = row.runtime_fields_payload()
    if column_name not in fields:
        raise error_type(f"Required source column is missing: {column_name}.")
    value = fields[column_name].strip()
    if not value and column_name not in {"ability_id", "description", "parameter", "faction_id"}:
        raise error_type(f"Required source column is empty: {column_name}.")
    return value
