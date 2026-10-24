"""Authentication/AST tests; counted separately from semantic behavior."""

import ast
import hashlib
import json
from pathlib import Path

import pytest
from tools.core_rules_order84_capture import capture_literals, source_inventory

ROOT = Path(__file__).resolve().parents[3]
MAP = Path(__file__).with_name("coverage.json")


@pytest.mark.parametrize(
    "locator",
    [
        "12.00",
        "12.01",
        "12.02",
        "12.03",
        "12.04",
        "12.04.01",
        "12.05",
        "12.06",
        "12.07",
        "12.08",
        "12.09",
    ],
)
def test_every_adopted_hierarchy_and_block_matches_both_retained_sources(locator: str) -> None:
    mapping = json.loads(MAP.read_text(encoding="utf-8"))
    current = json.loads(
        (ROOT / "data/source_audits/order135/retained-current-sources.json").read_text(
            encoding="utf-8"
        )
    )
    raw = capture_literals(
        (ROOT / "data/source_audits/v963_shock/captures/core-page.js").read_text(encoding="utf-8")
    )
    id_ = f"rule:12:{locator}:1"
    row = next(r for r in source_inventory(raw) if r["row_id"] == id_)
    assert row == next(
        r for r in source_inventory(current["full_current_core_capture"]) if r["row_id"] == id_
    )
    adopted = next(s for s in mapping["sources"] if s["source_id"] == id_)
    assert adopted["source_sha256"] == row["source_sha256"]
    assert [{k: v for k, v in b.items() if k != "value"} for b in adopted["blocks"]] == row[
        "blocks"
    ]
    for b in adopted["blocks"]:
        assert (
            hashlib.sha256(
                json.dumps(
                    b["value"], sort_keys=True, ensure_ascii=False, separators=(",", ":")
                ).encode()
            ).hexdigest()
            == b["sha256"]
        )
    assert {
        i for q in adopted["requirements"] + adopted["context"] for i in q["source_blocks"]
    } == {b["ordinal"] for b in adopted["blocks"]}


def test_complete_nested_inventory_faq_owners_and_live_assertion_bindings() -> None:
    mapping = json.loads(MAP.read_text(encoding="utf-8"))
    current = json.loads(
        (ROOT / "data/source_audits/order135/retained-current-sources.json").read_text(
            encoding="utf-8"
        )
    )
    capture = current["full_current_core_capture"]
    assert {r["row_id"] for r in source_inventory(capture) if r["category"] == "12"} == {
        s["source_id"] for s in mapping["sources"]
    }
    assert len(mapping["sources"]) == 11
    assert mapping["observed_at"] == current["observed_at"]
    assert mapping["faq_ownership"]["reviewed_current_faq_count"] == len(capture["faqs"]) == 64
    for f in mapping["faq_ownership"]["locally_owned"]:
        assert {k: f[k] for k in ("id", "question", "answer")} == capture["faqs"][f["ordinal"] - 1]
        assert f["source_sha256"] == next(
            r["source_sha256"] for r in source_inventory(capture) if r["row_id"] == "faq:" + f["id"]
        )
    for f in mapping["faq_ownership"]["cross_references"]:
        if "source_sha256" in f:
            assert {k: f[k] for k in ("id", "question", "answer")} == capture["faqs"][
                f["faq_ordinal"] - 1
            ]
            assert f["source_sha256"] == next(
                r["source_sha256"]
                for r in source_inventory(capture)
                if r["row_id"] == "faq:" + f["id"]
            )
    for source in [
        *mapping["sources"],
        {"requirements": mapping["faq_ownership"]["locally_owned"]},
        {
            "requirements": [
                f
                for f in mapping["faq_ownership"]["cross_references"]
                if "semantic_assertions" in f
            ]
        },
    ]:
        for q in source["requirements"]:
            assert q["engine_owners"]
            assert q["semantic_assertions"]
            for binding in q["semantic_assertions"]:
                file, name = binding["node"].split("::")
                tree = ast.parse((ROOT / file).read_text(encoding="utf-8"))
                node = next(
                    n for n in tree.body if isinstance(n, ast.FunctionDef) and n.name == name
                )
                assert (
                    hashlib.sha256(ast.dump(node, include_attributes=False).encode()).hexdigest()
                    == binding["function_ast_sha256"]
                )
                assert [
                    ast.unparse(n) for n in ast.walk(node) if isinstance(n, ast.Assert)
                ] == binding["assertions"]
                assert binding["assertions"]
    for file, expected in mapping["authenticated_inputs"].items():
        assert hashlib.sha256((ROOT / file).read_bytes()).hexdigest() == expected
