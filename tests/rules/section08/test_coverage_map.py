"""Authentication checks are metadata checks, separate from semantic assertions."""

import ast
import hashlib
import json
from pathlib import Path

import pytest
from tools.core_rules_order84_capture import capture_literals, source_inventory

ROOT = Path(__file__).resolve().parents[3]
MAP = Path(__file__).with_name("coverage.json")


@pytest.mark.parametrize(
    "locator", ["08.00", "08.01", "08.02", "08.02.01", "08.03", "08.03.01", "08.04", "08.05"]
)
def test_each_source_node_matches_raw_capture_and_accounts_for_all_blocks(locator: str) -> None:
    mapping = json.loads(MAP.read_text(encoding="utf-8"))
    source = next(s for s in mapping["sources"] if s["locator"] == locator)
    raw = capture_literals(
        (ROOT / "data/source_audits/v963_shock/captures/core-page.js").read_text(encoding="utf-8")
    )
    row = next(r for r in source_inventory(raw) if r["row_id"] == source["source_id"])
    assert row["source_sha256"] == source["source_sha256"]
    assert row["blocks"] == [
        {key: value for key, value in block.items() if key != "value"} for block in source["blocks"]
    ]
    for block in source["blocks"]:
        value = json.dumps(
            block["value"], sort_keys=True, separators=(",", ":"), ensure_ascii=False
        )
        assert hashlib.sha256(value.encode()).hexdigest() == block["sha256"]
    accounted = {i for r in source["requirements"] + source["context"] for i in r["source_blocks"]}
    assert accounted == {b["ordinal"] for b in source["blocks"]}


def test_current_hierarchy_faq_owner_and_all_live_assertion_bindings() -> None:
    mapping = json.loads(MAP.read_text(encoding="utf-8"))
    current = json.loads(
        (ROOT / "data/source_audits/order135/retained-current-sources.json").read_text(
            encoding="utf-8"
        )
    )
    current_rows = [
        r for r in source_inventory(current["full_current_core_capture"]) if r["category"] == "08"
    ]
    assert {r["row_id"] for r in current_rows} == {r["source_id"] for r in mapping["sources"]}
    requirements = [q for s in mapping["sources"] for q in s["requirements"]]
    assert len(requirements) == len({q["id"] for q in requirements}) == 20
    for q in requirements:
        assert q["engine_owners"]
        for e in q["semantic_assertions"]:
            file, name = e["node"].split("::")
            tree = ast.parse((ROOT / file).read_text(encoding="utf-8"))
            f = next(n for n in tree.body if isinstance(n, ast.FunctionDef) and n.name == name)
            assert (
                hashlib.sha256(ast.dump(f, include_attributes=False).encode()).hexdigest()
                == e["function_ast_sha256"]
            )
            assert [ast.unparse(n) for n in ast.walk(f) if isinstance(n, ast.Assert)] == e[
                "assertions"
            ]
            assert e["assertions"]
    for name, expected in mapping["authenticated_inputs"].items():
        assert hashlib.sha256((ROOT / name).read_bytes()).hexdigest() == expected
    faq = mapping["faq_ownership"]
    assert faq["locally_owned"] == []
    assert (
        faq["reviewed_current_faq_count"] == len(current["full_current_core_capture"]["faqs"]) == 64
    )
    assert (
        faq["cross_references"][0]["id"] == current["full_current_core_capture"]["faqs"][49]["id"]
    )
    assert faq["cross_references"][0]["owner"] == "01"
