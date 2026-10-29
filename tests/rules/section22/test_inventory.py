"""Inventory and isolation diagnostics receive no gameplay credit."""

import ast
import hashlib
import json
from pathlib import Path

from tools.core_rules_order84_capture import capture_literals, fingerprint

from tests.support.section02_fixtures import Section02Definitions
from tests.support.section22_fixtures import pair


def test_inventory_matches_complete_retained_hierarchy_and_every_faq() -> None:
    root = Path(__file__).resolve().parents[3]
    inventory = json.loads(Path(__file__).with_name("coverage.json").read_text(encoding="utf8"))
    capture = capture_literals(
        (root / "data/source_audits/v963_shock/captures/core-page.js").read_text(encoding="utf8")
    )
    assert inventory["category_hierarchy"] in capture["categories"]
    assert [entry["id"] for entry in inventory["faq_screen"]] == [
        entry["id"] for entry in capture["faqs"]
    ]
    assert len(inventory["faq_screen"]) == 64
    for actual, selected in zip(capture["faqs"], inventory["faq_screen"], strict=True):
        assert selected["source_sha256"] == fingerprint(actual)
    assert [row["locator"] for row in inventory["sources"]] == [
        "22.01",
        "22.02",
        "22.03",
        "22.03.01",
        "22.04",
        "22.05",
    ]
    for row in inventory["sources"]:
        assert {b["ordinal"] for b in row["blocks"]} == {
            n for ob in row["obligations"] for n in ob["source_blocks"]
        }
        for ob in row["obligations"]:
            for binding in ob["semantic_assertions"]:
                path, name = binding["node"].split("::")
                function = next(
                    n
                    for n in ast.parse((root / path).read_text(encoding="utf8")).body
                    if isinstance(n, ast.FunctionDef) and n.name == name
                )
                assert (
                    hashlib.sha256(
                        ast.dump(function, include_attributes=False).encode()
                    ).hexdigest()
                    == binding["function_ast_sha256"]
                )
                assert binding["assertions"] or binding["expected_exceptions"]


def test_native_cases_have_fresh_models_state_and_geometry(
    section22_definitions: Section02Definitions,
) -> None:
    left, a, _ = pair(section22_definitions, psychic=True)
    right, b, _ = pair(section22_definitions, psychic=True)
    assert left.to_payload() == right.to_payload()
    assert a.own_models[0] is not b.own_models[0]
    assert left.battlefield_state is not right.battlefield_state
    left.battle_shocked_unit_ids.append(a.unit_instance_id)
    assert not right.battle_shocked_unit_ids
