"""Authenticate every adopted transport row and live assertion binding.

This bookkeeping receives no behavioral pass credit by itself.
"""

import ast
import hashlib
import json
from pathlib import Path

import pytest
from tools.core_rules_order84_capture import capture_literals, fingerprint, source_inventory

ROOT = Path(__file__).resolve().parents[3]
MAP = Path(__file__).with_name("coverage.json")


@pytest.mark.parametrize(
    "locator",
    ["18.01", "18.02", "18.02.01", "18.03", "18.04", "18.04.01", "18.05", "18.06", "18.07"],
)
def test_adopted_literal_row_blocks_and_entire_hierarchy_are_complete(locator: str) -> None:
    mapping = json.loads(MAP.read_text(encoding="utf8"))
    capture = json.loads(
        (ROOT / "data/source_audits/order135/retained-current-sources.json").read_text(
            encoding="utf8"
        )
    )["full_current_core_capture"]
    literal = capture_literals(
        (ROOT / "data/source_audits/v963_shock/captures/core-page.js").read_text(encoding="utf8")
    )
    identity = f"rule:18:{locator}:1"
    row = next(r for r in source_inventory(capture) if r["row_id"] == identity)
    assert row == next(r for r in source_inventory(literal) if r["row_id"] == identity)
    item = next(s for s in mapping["sources"] if s["source_id"] == identity)
    assert item["source_sha256"] == row["source_sha256"]
    assert [{k: v for k, v in b.items() if k != "value"} for b in item["blocks"]] == row["blocks"]
    assert {b["ordinal"] for b in item["blocks"]} == {
        i for clause in item["obligations"] for i in clause["source_blocks"]
    }
    assert all(fingerprint(b["value"]) == b["sha256"] for b in item["blocks"])
    assert mapping["category_hierarchy"] == next(
        c for c in capture["categories"] if c["number"] == "18"
    )
    assert mapping["source_rows"] == 9
    assert mapping["text_blocks"] == 74
    assert mapping["diagram_count"] == 0


def test_all_faqs_are_screened_and_every_semantic_binding_matches_live_assertions() -> None:
    mapping = json.loads(MAP.read_text(encoding="utf8"))
    capture = json.loads(
        (ROOT / "data/source_audits/order135/retained-current-sources.json").read_text(
            encoding="utf8"
        )
    )["full_current_core_capture"]
    assert (
        len(mapping["faq_screen"])
        == len(capture["faqs"])
        == mapping["all_current_faqs_screened"]
        == 64
    )
    for item in mapping["faq_screen"]:
        faq = capture["faqs"][item["ordinal"] - 1]
        assert {k: item[k] for k in ("id", "question", "answer")} == faq
        assert item["source_sha256"] == fingerprint(faq)
        assert item["reason"]
    bindings = [
        b
        for source in mapping["sources"]
        for clause in source["obligations"]
        for b in clause["semantic_assertions"]
    ]
    assert mapping["semantic_obligations"] == 51
    for item in mapping["locally_owned_faqs"]:
        assert item["source_sha256"] == fingerprint(capture["faqs"][item["ordinal"] - 1])
        bindings.extend(item["semantic_assertions"])
    for binding in bindings:
        file, name = binding["node"].split("::")
        fn = next(
            n
            for n in ast.parse((ROOT / file).read_text(encoding="utf8")).body
            if isinstance(n, ast.FunctionDef) and n.name == name
        )
        assert (
            hashlib.sha256(ast.dump(fn, include_attributes=False).encode()).hexdigest()
            == binding["function_ast_sha256"]
        )
        assert [ast.unparse(n) for n in ast.walk(fn) if isinstance(n, ast.Assert)] == binding[
            "assertions"
        ]
        expected_exceptions = [
            ast.unparse(n)
            for n in ast.walk(fn)
            if isinstance(n, ast.With)
            and any(
                isinstance(i.context_expr, ast.Call)
                and isinstance(i.context_expr.func, ast.Attribute)
                and isinstance(i.context_expr.func.value, ast.Name)
                and i.context_expr.func.value.id == "pytest"
                and i.context_expr.func.attr == "raises"
                for i in n.items
            )
        ]
        assert expected_exceptions == binding["expected_exceptions"]
        assert binding["assertions"] or binding["expected_exceptions"]
    for file, digest in mapping["authenticated_inputs"].items():
        assert hashlib.sha256((ROOT / file).read_bytes()).hexdigest() == digest
    assert mapping["metadata_is_not_semantic_coverage"]
    assert not mapping["unresolved_source_interpretations"]


def test_emergency_status_has_one_shared_completion_and_mutation_owner() -> None:
    engine = ROOT / "src/warhammer40k_core/engine"
    recorder = ast.parse((engine / "move_completion_triggers.py").read_text(encoding="utf8"))
    calls = [
        n
        for n in ast.walk(recorder)
        if isinstance(n, ast.Call)
        and isinstance(n.func, ast.Name)
        and n.func.id == "apply_emergency_disembark_battle_shock"
    ]
    assert len(calls) == 1
    owner = ast.parse((engine / "emergency_disembark_battle_shock.py").read_text(encoding="utf8"))
    apply = next(
        n
        for n in owner.body
        if isinstance(n, ast.FunctionDef) and n.name == "apply_emergency_disembark_battle_shock"
    )
    assert any(
        isinstance(n, ast.Call)
        and isinstance(n.func, ast.Name)
        and n.func.id == "apply_direct_battle_shock_state"
        for n in ast.walk(apply)
    )
    assert not any(
        isinstance(n, ast.Assign)
        and any(
            isinstance(t, ast.Attribute)
            and t.attr in {"battle_shocked_unit_ids", "battle_shocked_unit_states"}
            for t in n.targets
        )
        for n in ast.walk(apply)
    )
    history = (engine / "battle_shock_state_history.py").read_text(encoding="utf8")
    assert "replay_emergency_disembark_battle_shock(" in history
    assert "validate_mutation_decision_closure(" in ast.unparse(owner)
    assert "physical_model_authority_before_event" not in ast.unparse(owner)
