"""Source/AST authentication only; these cases do not count as semantic proof."""

import ast
import hashlib
import json
from pathlib import Path

import pytest
from tools.core_rules_order84_capture import capture_literals, source_inventory

ROOT = Path(__file__).resolve().parents[3]
MAP = Path(__file__).with_name("coverage.json")


@pytest.mark.parametrize("locator", [f"10.{i:02d}" for i in range(8)])
def test_exact_hierarchy_entry_and_every_block_match_retained_body(locator: str) -> None:
    mapping = json.loads(MAP.read_text(encoding="utf-8"))
    raw = capture_literals(
        (ROOT / "data/source_audits/v963_shock/captures/core-page.js").read_text(encoding="utf-8")
    )
    row = next(r for r in source_inventory(raw) if r["row_id"] == f"rule:10:{locator}:1")
    source = next(r for r in mapping["sources"] if r["source_id"] == row["row_id"])
    assert source["source_sha256"] == row["source_sha256"]
    assert [{k: v for k, v in b.items() if k != "value"} for b in source["blocks"]] == row["blocks"]
    for block in source["blocks"]:
        assert (
            hashlib.sha256(
                json.dumps(
                    block["value"], sort_keys=True, separators=(",", ":"), ensure_ascii=False
                ).encode()
            ).hexdigest()
            == block["sha256"]
        )
    assert {i for q in source["requirements"] + source["context"] for i in q["source_blocks"]} == {
        b["ordinal"] for b in source["blocks"]
    }


def test_complete_hierarchy_faq_owner_and_live_assertion_bindings() -> None:
    mapping = json.loads(MAP.read_text(encoding="utf-8"))
    current = json.loads(
        (ROOT / "data/source_audits/order135/retained-current-sources.json").read_text(
            encoding="utf-8"
        )
    )
    rows = [
        r for r in source_inventory(current["full_current_core_capture"]) if r["category"] == "10"
    ]
    assert {r["row_id"] for r in rows} == {r["source_id"] for r in mapping["sources"]}
    assert len(rows) == 8
    assert mapping["observed_at"] == current["observed_at"]
    owned = mapping["faq_ownership"]["locally_owned"][0]
    assert {k: owned[k] for k in ("id", "question", "answer")} == current[
        "full_current_core_capture"
    ]["faqs"][1]
    assert mapping["faq_ownership"]["reviewed_current_faq_count"] == 64
    assert owned["source_sha256"] == next(
        r["source_sha256"]
        for r in source_inventory(current["full_current_core_capture"])
        if r["row_id"] == "faq:" + owned["id"]
    )
    ids: list[str] = []
    for source in [
        *mapping["sources"],
        {"requirements": mapping["faq_ownership"]["locally_owned"]},
    ]:
        for requirement in source["requirements"]:
            ids.append(requirement["id"])
            assert requirement["engine_owners"]
            for binding in requirement["semantic_assertions"]:
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
    assert len(ids) == len(set(ids))
    for file, expected in mapping["authenticated_inputs"].items():
        assert hashlib.sha256((ROOT / file).read_bytes()).hexdigest() == expected
