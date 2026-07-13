from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from typing import TYPE_CHECKING

if TYPE_CHECKING or __package__:
    from tools.faction_pack_datasheet_review import faction_pack_datasheet_review
else:
    from faction_pack_datasheet_review import faction_pack_datasheet_review
from warhammer40k_core.engine.ability_coverage import (
    AbilityCoverageRow,
    AbilityCoverageSupportStage,
)

AELDARI_FACTION_ID = "aeldari"
DATASHEET_SNAPSHOT_ALL_CONSUMED = "All consumed"
DATASHEET_SNAPSHOT_HOST_NEEDED = "IR parsed; host needed"
DATASHEET_SNAPSHOT_UNSUPPORTED_IR = "Unsupported IR"
DATASHEET_SNAPSHOT_BRIDGE_BLOCKED = "Bridge/catalog blocked"
DATASHEET_SNAPSHOT_BUCKETS = (
    DATASHEET_SNAPSHOT_ALL_CONSUMED,
    DATASHEET_SNAPSHOT_HOST_NEEDED,
    DATASHEET_SNAPSHOT_UNSUPPORTED_IR,
    DATASHEET_SNAPSHOT_BRIDGE_BLOCKED,
)


@dataclass(frozen=True, slots=True)
class DatasheetSemanticSnapshotSupportRow:
    datasheet_id: str
    datasheet_name: str
    catalog_blocked: bool
    ability_coverage_row_ids: tuple[str, ...]


def aeldari_datasheet_semantic_snapshot_markdown(
    *,
    datasheet_support_rows: tuple[DatasheetSemanticSnapshotSupportRow, ...],
    ability_rows_by_id: Mapping[str, AbilityCoverageRow],
) -> list[str]:
    review = faction_pack_datasheet_review(AELDARI_FACTION_ID)
    support_rows_by_id: dict[str, DatasheetSemanticSnapshotSupportRow] = {}
    for current_support_row in datasheet_support_rows:
        if current_support_row.datasheet_id in support_rows_by_id:
            raise ValueError("Aeldari datasheet semantic snapshot contains duplicate support rows.")
        support_rows_by_id[current_support_row.datasheet_id] = current_support_row
    reviewed_ids = {row.datasheet_id for row in review.rows if row.datasheet_id is not None}
    extra_support_ids = support_rows_by_id.keys() - reviewed_ids
    if extra_support_ids:
        raise ValueError(
            "Aeldari datasheet semantic snapshot contains support rows outside the reviewed "
            f"source scope: {sorted(extra_support_ids)!r}."
        )

    lines = [
        "",
        "### Unit Datasheets",
        "",
        (
            "| Aeldari tradition | Fully supported (`All consumed`) | "
            "IR parsed; host needed | Unsupported IR | Bridge/catalog blocked |"
        ),
        "| --- | --- | --- | --- | --- |",
    ]
    group_names = tuple(dict.fromkeys(row.group for row in review.rows))
    for group_name in group_names:
        rows_by_bucket: dict[str, list[str]] = {bucket: [] for bucket in DATASHEET_SNAPSHOT_BUCKETS}
        for review_row in review.rows:
            if review_row.group != group_name:
                continue
            support_row = (
                None
                if review_row.datasheet_id is None
                else support_rows_by_id.get(review_row.datasheet_id)
            )
            if support_row is not None and support_row.datasheet_name != review_row.datasheet_name:
                raise ValueError(
                    "Aeldari datasheet semantic snapshot support/source names do not match."
                )
            bucket = datasheet_semantic_snapshot_bucket(
                support_row=support_row,
                ability_rows_by_id=ability_rows_by_id,
            )
            identifier = (
                "PDF-only" if review_row.datasheet_id is None else f"`{review_row.datasheet_id}`"
            )
            rows_by_bucket[bucket].append(f"{review_row.datasheet_name} ({identifier})")
        lines.append(
            "| "
            + " | ".join(
                (
                    _markdown_text(group_name),
                    _markdown_line_list(sorted(rows_by_bucket[DATASHEET_SNAPSHOT_ALL_CONSUMED])),
                    _markdown_line_list(sorted(rows_by_bucket[DATASHEET_SNAPSHOT_HOST_NEEDED])),
                    _markdown_line_list(sorted(rows_by_bucket[DATASHEET_SNAPSHOT_UNSUPPORTED_IR])),
                    _markdown_line_list(sorted(rows_by_bucket[DATASHEET_SNAPSHOT_BRIDGE_BLOCKED])),
                )
            )
            + " |"
        )
    return lines


def datasheet_semantic_snapshot_bucket(
    *,
    support_row: DatasheetSemanticSnapshotSupportRow | None,
    ability_rows_by_id: Mapping[str, AbilityCoverageRow],
) -> str:
    if support_row is None or support_row.catalog_blocked:
        return DATASHEET_SNAPSHOT_BRIDGE_BLOCKED
    if not support_row.ability_coverage_row_ids:
        return DATASHEET_SNAPSHOT_BRIDGE_BLOCKED
    ability_rows: list[AbilityCoverageRow] = []
    for coverage_row_id in support_row.ability_coverage_row_ids:
        ability_row = ability_rows_by_id.get(coverage_row_id)
        if ability_row is None:
            raise ValueError(
                "Aeldari datasheet semantic snapshot references unknown ability coverage."
            )
        ability_rows.append(ability_row)
    if any(
        row.diagnostic_reasons
        or row.support_stage
        in {
            AbilityCoverageSupportStage.DESCRIPTOR_ONLY,
            AbilityCoverageSupportStage.IR_COMPILED_UNSUPPORTED,
        }
        for row in ability_rows
    ):
        return DATASHEET_SNAPSHOT_UNSUPPORTED_IR
    if any(
        row.support_stage is AbilityCoverageSupportStage.GENERIC_IR_EXECUTABLE
        for row in ability_rows
    ):
        return DATASHEET_SNAPSHOT_HOST_NEEDED
    if all(
        row.support_stage is AbilityCoverageSupportStage.ENGINE_CONSUMED
        and row.runtime_consumer_ids
        for row in ability_rows
    ):
        return DATASHEET_SNAPSHOT_ALL_CONSUMED
    raise ValueError("Aeldari datasheet semantic snapshot encountered an unclassified row.")


def _markdown_line_list(values: list[str]) -> str:
    if not values:
        return "None"
    return "<br>".join(_markdown_text(value) for value in values)


def _markdown_text(value: str) -> str:
    return value.replace("|", "\\|")
