"""Source completeness and fixture isolation; these are not gameplay cases."""

import ast
import hashlib
import json
from pathlib import Path

from tools.core_rules_order84_capture import capture_literals, fingerprint

from tests.support.section02_fixtures import Section02Definitions
from tests.support.section23_fixtures import scene


def test_complete_literal_inventory_faq_screen_and_assertion_bindings() -> None:
    root = Path(__file__).resolve().parents[3]
    inventory = json.loads(Path(__file__).with_name("coverage.json").read_text(encoding="utf8"))
    capture = capture_literals(
        (root / "data/source_audits/v963_shock/captures/core-page.js").read_text(encoding="utf8")
    )
    assert inventory["category_hierarchy"] in capture["categories"]
    assert len(inventory["faq_screen"]) == 64
    assert inventory["literal_blocks"] == 9
    assert inventory["table_count"] == inventory["diagram_count"] == 0
    for actual, selected in zip(capture["faqs"], inventory["faq_screen"], strict=True):
        assert actual["id"] == selected["id"]
        assert fingerprint(actual) == selected["source_sha256"]
        assert selected["rationale"]
    assert [r["locator"] for r in inventory["sources"]] == ["23.01", "23.02", "23.03", "23.04"]
    for row in inventory["sources"]:
        assert {b["ordinal"] for b in row["blocks"]} == {
            n for ob in row["obligations"] for n in ob["source_blocks"]
        }
        for ob in row["obligations"]:
            for binding in ob["semantic_assertions"]:
                path, name = binding["node"].split("::")
                fn = next(
                    n
                    for n in ast.parse((root / path).read_text(encoding="utf8")).body
                    if isinstance(n, ast.FunctionDef) and n.name == name
                )
                assert (
                    hashlib.sha256(ast.dump(fn, include_attributes=False).encode()).hexdigest()
                    == binding["function_ast_sha256"]
                )
                assert binding["assertions"] or binding["expected_exceptions"]


def test_native_cases_keep_fresh_mutable_graphs_and_immutable_selected_definitions(
    section23_definitions: Section02Definitions,
) -> None:
    left, own, _ = scene(section23_definitions, aircraft_attacker=True)
    right, other, _ = scene(section23_definitions, aircraft_attacker=True)
    assert left.to_payload() == right.to_payload()
    assert own.own_models[0] is not other.own_models[0]
    assert left.battlefield_state is not right.battlefield_state
    left.battle_shocked_unit_ids.append(own.unit_instance_id)
    assert not right.battle_shocked_unit_ids
    plain = section23_definitions.unit()
    assert "AIRCRAFT" not in plain.keywords
