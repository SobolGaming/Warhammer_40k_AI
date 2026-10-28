"""Complete literal inventory and partial live-binding diagnostics; no gameplay case credit."""

import ast
import hashlib
import json
from pathlib import Path

from tools.core_rules_order84_capture import capture_literals, fingerprint, source_inventory

from tests.support.section02_fixtures import Section02Definitions
from tests.support.section03_fixtures import native_state
from tests.support.section24_fixtures import LORD


def test_entire_retained_hierarchy_blocks_and_all_faqs_have_live_assertion_bindings() -> None:
    root = Path(__file__).resolve().parents[3]
    inventory = json.loads(Path(__file__).with_name("coverage.json").read_text(encoding="utf8"))
    raw = (root / inventory["capture_path"]).read_bytes()
    assert hashlib.sha256(raw).hexdigest() == inventory["capture_sha256"]
    capture = capture_literals(raw.decode("utf8"))
    assert inventory["category_hierarchy"] == next(
        c for c in capture["categories"] if c["number"] == "24"
    )
    expected = [r for r in source_inventory(capture) if r["category"] == "24"]
    assert len(expected) == inventory["source_rows"] == 45
    assert sum(len(r["blocks"]) for r in expected) == inventory["literal_blocks"] == 101
    assert len(inventory["faq_screen"]) == 64
    for a, b in zip(capture["faqs"], inventory["faq_screen"], strict=True):
        assert a["id"] == b["id"]
        assert fingerprint(a) == b["source_sha256"]
        assert b["rationale"]
    functions: dict[str, tuple[str, list[str]]] = {}
    for actual, row in zip(expected, inventory["sources"], strict=True):
        assert all(row[k] == value for k, value in actual.items())
        assert {b["ordinal"] for b in row["blocks"]} == {
            n for ob in row["obligations"] for n in ob["source_blocks"]
        }
        for ob in row["obligations"] + row["colocated_faq_clarifications"]:
            if not ob["semantic_assertions"]:
                assert ob["coverage_status"] == "gap"
                gaps = ob["coverage_gaps"]
                assert isinstance(gaps, list)
                assert gaps
                assert all(isinstance(gap, dict) and gap["reason"] and gap["nodes"] for gap in gaps)
                assert ob["historical_nonselected_evidence"]
                continue
            assert ob["semantic_assertions"]
            for binding in ob["semantic_assertions"]:
                node = binding["node"]
                if node not in functions:
                    path, name = node.split("::")
                    function = next(
                        f
                        for f in ast.parse((root / path).read_text(encoding="utf8")).body
                        if isinstance(f, ast.FunctionDef) and f.name == name
                    )
                    functions[node] = (
                        hashlib.sha256(
                            ast.dump(function, include_attributes=False).encode()
                        ).hexdigest(),
                        [ast.unparse(n) for n in ast.walk(function) if isinstance(n, ast.Assert)],
                    )
                digest, assertions = functions[node]
                assert digest == binding["function_ast_sha256"]
                assert assertions == binding["assertions"]
                assert binding["assertions"] or binding["expected_exceptions"]


def test_fresh_states_and_models_share_only_immutable_native_definitions(
    section24_definitions: Section02Definitions,
) -> None:
    d = section24_definitions
    left = d.unit(LORD)
    right = d.unit(LORD)
    a, b = native_state(d, left), native_state(d, right)
    assert a.to_payload() == b.to_payload()
    assert a.battlefield_state is not b.battlefield_state
    assert left.own_models[0] is not right.own_models[0]
    a.battle_shocked_unit_ids.append(left.unit_instance_id)
    assert b.battle_shocked_unit_ids == []
