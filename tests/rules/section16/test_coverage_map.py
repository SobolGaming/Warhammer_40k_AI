"""Inventory authentication is bookkeeping, distinct from semantic coverage."""

import ast
import hashlib
import json
from pathlib import Path

import pytest
from tools.core_rules_order84_capture import capture_literals, fingerprint, source_inventory

ROOT = Path(__file__).resolve().parents[3]
MAP = Path(__file__).with_name("coverage.json")


@pytest.mark.parametrize("locator", ["16.01"])
def test_every_adopted_row_nested_clause_and_card_block_is_authenticated(locator: str) -> None:
    mapping = json.loads(MAP.read_text(encoding="utf8"))
    capture = json.loads(
        (ROOT / "data/source_audits/order135/retained-current-sources.json").read_text(
            encoding="utf8"
        )
    )["full_current_core_capture"]
    raw = capture_literals(
        (ROOT / "data/source_audits/v963_shock/captures/core-page.js").read_text(encoding="utf8")
    )
    identity = f"rule:16:{locator}:1"
    row = next(r for r in source_inventory(capture) if r["row_id"] == identity)
    assert row == next(r for r in source_inventory(raw) if r["row_id"] == identity)
    adopted = next(r for r in mapping["sources"] if r["source_id"] == identity)
    assert adopted["source_sha256"] == row["source_sha256"]
    assert [{k: v for k, v in b.items() if k != "value"} for b in adopted["blocks"]] == row[
        "blocks"
    ]
    assert {i for q in adopted["obligations"] for i in q["source_blocks"]} == {
        b["ordinal"] for b in adopted["blocks"]
    }
    for b in adopted["blocks"]:
        assert fingerprint(b["value"]) == b["sha256"]


def test_hierarchy_faq_screening_and_live_assertions_have_complete_exact_bindings() -> None:
    mapping = json.loads(MAP.read_text(encoding="utf8"))
    current = json.loads(
        (ROOT / "data/source_audits/order135/retained-current-sources.json").read_text(
            encoding="utf8"
        )
    )["full_current_core_capture"]
    assert mapping["category_hierarchy"] == next(
        c for c in current["categories"] if c["number"] == "16"
    )
    assert {r["row_id"] for r in source_inventory(current) if r["category"] == "16"} == {
        s["source_id"] for s in mapping["sources"]
    }
    assert len(mapping["sources"]) == 1
    assert mapping["all_current_faqs_screened"] == len(current["faqs"]) == 64
    assert {f["ordinal"] for f in mapping["locally_owned_faqs"]} == {16, 17, 62}
    bindings = [
        b for s in mapping["sources"] for q in s["obligations"] for b in q["semantic_assertions"]
    ]
    for f in mapping["locally_owned_faqs"]:
        assert {k: f[k] for k in ("id", "question", "answer")} == current["faqs"][f["ordinal"] - 1]
        assert f["source_sha256"] == fingerprint(current["faqs"][f["ordinal"] - 1])
        bindings.extend(f["semantic_assertions"])
    for b in bindings:
        path, name = b["node"].split("::")
        function = next(
            n
            for n in ast.parse((ROOT / path).read_text(encoding="utf8")).body
            if isinstance(n, ast.FunctionDef) and n.name == name
        )
        assert (
            hashlib.sha256(ast.dump(function, include_attributes=False).encode()).hexdigest()
            == b["function_ast_sha256"]
        )
        assert [ast.unparse(n) for n in ast.walk(function) if isinstance(n, ast.Assert)] == b[
            "assertions"
        ]
        assert b["assertions"]
    for path, sha in mapping["authenticated_inputs"].items():
        assert hashlib.sha256((ROOT / path).read_bytes()).hexdigest() == sha
    assert mapping["metadata_is_not_semantic_coverage"]
    assert mapping["unresolved_source_interpretations"] == []
