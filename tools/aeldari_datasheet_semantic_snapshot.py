from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING or __package__:
    from tools.aeldari_datasheet_semantic_coverage import (
        SEMANTIC_BUCKET_ALL_CONSUMED,
        SEMANTIC_BUCKET_BRIDGE_BLOCKED,
        SEMANTIC_BUCKET_HOST_NEEDED,
        SEMANTIC_BUCKET_UNSUPPORTED_IR,
        SEMANTIC_BUCKETS,
        aeldari_datasheet_semantic_coverage,
    )
else:
    from aeldari_datasheet_semantic_coverage import (
        SEMANTIC_BUCKET_ALL_CONSUMED,
        SEMANTIC_BUCKET_BRIDGE_BLOCKED,
        SEMANTIC_BUCKET_HOST_NEEDED,
        SEMANTIC_BUCKET_UNSUPPORTED_IR,
        SEMANTIC_BUCKETS,
        aeldari_datasheet_semantic_coverage,
    )


def aeldari_datasheet_semantic_snapshot_markdown() -> list[str]:
    coverage = aeldari_datasheet_semantic_coverage()
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
    group_names = tuple(dict.fromkeys(row.group for row in coverage.rows))
    for group_name in group_names:
        rows_by_bucket: dict[str, list[str]] = {bucket: [] for bucket in SEMANTIC_BUCKETS}
        for row in coverage.rows:
            if row.group != group_name:
                continue
            rows_by_bucket[row.semantic_bucket].append(
                f"{row.datasheet_name} (`{row.datasheet_id}`)"
            )
        lines.append(
            "| "
            + " | ".join(
                (
                    _markdown_text(group_name),
                    _markdown_line_list(sorted(rows_by_bucket[SEMANTIC_BUCKET_ALL_CONSUMED])),
                    _markdown_line_list(sorted(rows_by_bucket[SEMANTIC_BUCKET_HOST_NEEDED])),
                    _markdown_line_list(sorted(rows_by_bucket[SEMANTIC_BUCKET_UNSUPPORTED_IR])),
                    _markdown_line_list(sorted(rows_by_bucket[SEMANTIC_BUCKET_BRIDGE_BLOCKED])),
                )
            )
            + " |"
        )
    return lines


def _markdown_line_list(values: list[str]) -> str:
    if not values:
        return "None"
    return "<br>".join(_markdown_text(value) for value in values)


def _markdown_text(value: str) -> str:
    return value.replace("|", "\\|")
