"""Literal and assertion authentication; bookkeeping is not semantic coverage."""

import ast
import hashlib
import json
from pathlib import Path

import pytest
from tools.core_rules_order84_capture import capture_literals, fingerprint, source_inventory

ROOT = Path(__file__).resolve().parents[3]
MAP = Path(__file__).with_name("coverage.json")


@pytest.mark.parametrize("locator", ["17.01", "17.02", "17.03", "17.03.01"])
def test_exact_literal_rows_and_each_block_are_bound_to_semantic_assertions(locator: str) -> None:
    mapping = json.loads(MAP.read_text(encoding="utf8"))
    adopted = json.loads(
        (ROOT / "data/source_audits/order135/retained-current-sources.json").read_text(
            encoding="utf8"
        )
    )["full_current_core_capture"]
    literal = capture_literals(
        (ROOT / "data/source_audits/v963_shock/captures/core-page.js").read_text(encoding="utf8")
    )
    identity = f"rule:17:{locator}:1"
    row = next(r for r in source_inventory(adopted) if r["row_id"] == identity)
    assert row == next(r for r in source_inventory(literal) if r["row_id"] == identity)
    item = next(s for s in mapping["sources"] if s["source_id"] == identity)
    assert item["source_sha256"] == row["source_sha256"]
    assert [{k: v for k, v in b.items() if k != "value"} for b in item["blocks"]] == row["blocks"]
    assert {b["ordinal"] for b in item["blocks"]} == {
        b for q in item["obligations"] for b in q["source_blocks"]
    }
    for block in item["blocks"]:
        assert fingerprint(block["value"]) == block["sha256"]


def test_full_hierarchy_faq_screen_and_live_function_assertions_authenticate() -> None:
    mapping = json.loads(MAP.read_text(encoding="utf8"))
    capture = json.loads(
        (ROOT / "data/source_audits/order135/retained-current-sources.json").read_text(
            encoding="utf8"
        )
    )["full_current_core_capture"]
    assert mapping["category_hierarchy"] == next(
        c for c in capture["categories"] if c["number"] == "17"
    )
    assert len(mapping["sources"]) == 4
    assert sum(len(s["blocks"]) for s in mapping["sources"]) == 11
    assert (
        len(mapping["faq_screen"])
        == mapping["all_current_faqs_screened"]
        == len(capture["faqs"])
        == 64
    )
    assert {f["ordinal"] for f in mapping["locally_owned_faqs"]} == {5, 34, 39, 51, 53, 63}
    bindings = [
        b for s in mapping["sources"] for q in s["obligations"] for b in q["semantic_assertions"]
    ]
    for faq in mapping["faq_screen"]:
        source = capture["faqs"][faq["ordinal"] - 1]
        assert {k: faq[k] for k in ("id", "question", "answer")} == source
        assert faq["source_sha256"] == fingerprint(source)
        assert faq["reason"]
    for faq in mapping["locally_owned_faqs"]:
        assert faq["source_sha256"] == fingerprint(capture["faqs"][faq["ordinal"] - 1])
        bindings.extend(faq["semantic_assertions"])
    for binding in bindings:
        path, name = binding["node"].split("::")
        fn = next(
            n
            for n in ast.parse((ROOT / path).read_text(encoding="utf8")).body
            if isinstance(n, ast.FunctionDef) and n.name == name
        )
        assert (
            hashlib.sha256(ast.dump(fn, include_attributes=False).encode()).hexdigest()
            == binding["function_ast_sha256"]
        )
        assert [ast.unparse(n) for n in ast.walk(fn) if isinstance(n, ast.Assert)] == binding[
            "assertions"
        ]
        assert binding["assertions"]
    for path, digest in mapping["authenticated_inputs"].items():
        assert hashlib.sha256((ROOT / path).read_bytes()).hexdigest() == digest
    assert mapping["metadata_is_not_semantic_coverage"]
    assert not mapping["unresolved_source_interpretations"]


def test_runtime_keyword_records_and_physical_scope_have_one_owner() -> None:
    runtime = ast.parse(
        (ROOT / "src/warhammer40k_core/engine/faction_content/runtime.py").read_text(
            encoding="utf8"
        )
    )
    builder = next(
        n
        for n in runtime.body
        if isinstance(n, ast.FunctionDef) and n.name == "build_runtime_content_bundle_for_armies"
    )
    calls = {
        n.func.id
        for n in ast.walk(builder)
        if isinstance(n, ast.Call) and isinstance(n.func, ast.Name)
    }
    assert {
        "eleventh_edition_core_ability_catalog_records",
        "catalog_ability_records_from_catalog",
    } <= calls
    movement = ast.parse(
        (ROOT / "src/warhammer40k_core/engine/movement_legality.py").read_text(encoding="utf8")
    )
    capability = next(
        n
        for n in movement.body
        if isinstance(n, ast.ClassDef) and n.name == "MovementCapabilitySet"
    )
    constructor = next(
        n for n in capability.body if isinstance(n, ast.FunctionDef) and n.name == "from_keywords"
    )
    body = ast.unparse(constructor)
    assert "unit.own_model_by_id(model_instance_id).keywords" in body
    assert "'is_monster' in flags and 'MONSTER' in model_keywords" in body
    assert "'is_vehicle' in flags and 'VEHICLE' in model_keywords" in body
