"""Metadata and isolation controls; no semantic gameplay credit."""

import ast
import hashlib
import json
from pathlib import Path

from tests.support.section02_fixtures import Section02Definitions
from tests.support.section20_fixtures import reserve_scene


def test_every_literal_and_faq_binding_identifies_live_assertions() -> None:
    mapping = json.loads(Path(__file__).with_name("coverage.json").read_text(encoding="utf8"))
    assert mapping["source_rows"] == 7
    assert mapping["table_count"] == mapping["diagram_count"] == 0
    assert mapping["all_current_faqs_screened"] == len(mapping["faq_screen"]) == 64
    assert {row["locator"] for row in mapping["sources"]} == {
        "20.01",
        "20.01.01",
        "20.01.02",
        "20.02",
        "20.03",
        "20.03.01",
        "20.04",
    }
    root = Path(__file__).resolve().parents[3]
    for row in mapping["sources"]:
        assert {b["ordinal"] for b in row["blocks"]} <= {
            b for ob in row["obligations"] for b in ob["source_blocks"]
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


def test_fresh_native_reserve_cases_share_no_mutable_state(
    section20_definitions: Section02Definitions,
) -> None:
    a, b = reserve_scene(section20_definitions), reserve_scene(section20_definitions)
    assert a.state.to_payload() == b.state.to_payload()
    assert a.unit is not b.unit
    assert a.unit.own_models[0] is not b.unit.own_models[0]
    a.state.reserve_states.clear()
    assert b.state.reserve_states
    assert a.state.battlefield_state is not b.state.battlefield_state
