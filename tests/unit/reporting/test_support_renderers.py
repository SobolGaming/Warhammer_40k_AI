# pyright: reportPrivateUsage=false
from __future__ import annotations

from tools.generate_ability_support_matrix import (
    _ability_datasheet_pairs_text,
    _inline_code_list,
    _markdown_text,
    ability_support_matrix_rows,
    faction_support_markdown_files,
    runtime_content_semantic_coverage_payload,
    support_matrix_markdown,
)

from warhammer40k_core.engine.ability_coverage import (
    ability_coverage_category_rows,
    ability_coverage_category_rows_payload,
    ability_coverage_rows_payload,
)


def test_global_support_renderer_preserves_section_order_and_runtime_inventory() -> None:
    ability_rows = ability_support_matrix_rows()
    category_rows = ability_coverage_category_rows(ability_rows)
    markdown = support_matrix_markdown(
        ability_coverage_category_rows_payload(category_rows),
        ability_rows=ability_coverage_rows_payload(ability_rows),
        runtime_semantic_coverage=runtime_content_semantic_coverage_payload(),
    )

    headings = (
        "## Runtime Content Semantic Coverage",
        "## Mustering / List Construction Support",
        "## Factions",
        "## Runtime Hook Inventory",
    )
    assert all(heading in markdown for heading in headings)
    assert tuple(markdown.index(heading) for heading in headings) == tuple(
        sorted(markdown.index(heading) for heading in headings)
    )

    represented_consumer_ids = {
        consumer_id for row in ability_rows for consumer_id in row.runtime_consumer_ids
    }
    assert represented_consumer_ids
    assert all(f"`{consumer_id}`" in markdown for consumer_id in represented_consumer_ids)


def test_faction_support_renderer_preserves_section_order() -> None:
    aeldari = faction_support_markdown_files()["aeldari.md"]

    assert aeldari.startswith("# Aeldari Support Matrix\n")
    assert aeldari.index("## Detachment Rule Support") < aeldari.index(
        "## Datasheet / Unit Support"
    )


def test_support_renderer_escapes_tables_and_renders_empty_cells() -> None:
    assert _markdown_text("Alpha | Beta") == "Alpha \\| Beta"
    assert _inline_code_list(()) == "None"
    assert _ability_datasheet_pairs_text([]) == "None"
