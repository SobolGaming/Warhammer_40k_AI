"""Source integrity and case isolation; no semantic gameplay credit."""

import ast
import hashlib
import json
from pathlib import Path

from tools.core_rules_order84_capture import capture_literals, source_inventory

from tests.support.section02_fixtures import Section02Definitions
from tests.support.section21_fixtures import surge_scene


def test_complete_adopted_hierarchy_literals_and_bindings_are_live() -> None:
    root = Path(__file__).resolve().parents[3]
    mapping = json.loads(Path(__file__).with_name("coverage.json").read_text(encoding="utf8"))
    capture = capture_literals(
        (root / "data/source_audits/v963_shock/captures/core-page.js").read_text(encoding="utf8")
    )
    assert mapping["category_hierarchy"] == next(
        c for c in capture["categories"] if c["number"] == "21"
    )
    actual = [r for r in source_inventory(capture) if r["category"] == "21"]
    assert len(actual) == mapping["source_rows"] == 3
    assert sum(len(r["blocks"]) for r in actual) == mapping["literal_blocks"] == 33
    assert mapping["table_count"] == mapping["diagram_count"] == 0
    assert len(capture["faqs"]) == mapping["all_current_faqs_screened"] == 64
    for row in mapping["sources"]:
        assert {b["ordinal"] for b in row["blocks"]} == {
            b for ob in row["obligations"] for b in ob["source_blocks"]
        }
    obligations = [ob for r in mapping["sources"] for ob in r["obligations"]] + mapping[
        "locally_owned_faqs"
    ]
    for ob in obligations:
        for b in ob["semantic_assertions"]:
            path, name = b["node"].split("::")
            fn = next(
                n
                for n in ast.parse((root / path).read_text(encoding="utf8")).body
                if isinstance(n, ast.FunctionDef) and n.name == name
            )
            assert (
                hashlib.sha256(ast.dump(fn, include_attributes=False).encode()).hexdigest()
                == b["function_ast_sha256"]
            )
            assert b["assertions"] or b["expected_exceptions"]


def test_cached_native_definitions_do_not_share_mutable_case_graphs(
    section21_definitions: Section02Definitions,
) -> None:
    left = surge_scene(section21_definitions, multi=True)
    right = surge_scene(section21_definitions, multi=True)
    assert left.state.to_payload() == right.state.to_payload()
    assert left.unit is not right.unit
    assert left.unit.own_models[0] is not right.unit.own_models[0]
    left.state.battle_shocked_unit_ids.append(left.unit.unit_instance_id)
    assert not right.state.battle_shocked_unit_ids
    assert left.state.battlefield_state is not right.state.battlefield_state
