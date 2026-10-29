"""Metadata integrity only: these checks receive no gameplay coverage credit."""

import ast
import hashlib
import json
from pathlib import Path


def test_complete_hierarchy_literal_table_and_faq_inventory_is_preserved() -> None:
    root = Path(__file__).resolve().parents[3]
    mapping = json.loads((Path(__file__).with_name("coverage.json")).read_text(encoding="utf8"))
    assert {s["locator"] for s in mapping["sources"]} == {
        "19.01",
        "19.01.01",
        "19.02",
        "19.03",
        "19.04",
        "19.04.01",
    }
    assert mapping["source_rows"] == 6
    assert mapping["text_blocks"] == 12
    assert mapping["table_count"] == 1
    assert mapping["table_cells"] == 8
    assert mapping["table_semantic_rows"] == 3
    assert mapping["diagram_count"] == 0
    assert mapping["all_current_faqs_screened"] == 64
    for source in mapping["sources"]:
        for obligation in source["obligations"]:
            for binding in obligation["semantic_assertions"]:
                path, name = binding["node"].split("::")
                fn = next(
                    n
                    for n in ast.parse((root / path).read_text(encoding="utf8")).body
                    if isinstance(n, ast.FunctionDef) and n.name == name
                )
                assert (
                    binding["function_ast_sha256"]
                    == hashlib.sha256(ast.dump(fn, include_attributes=False).encode()).hexdigest()
                )
                assert binding["assertions"] or binding["expected_exceptions"]
