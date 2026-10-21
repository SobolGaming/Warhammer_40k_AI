"""Source and assertion binding integrity; these checks earn no gameplay credit."""

import ast
import hashlib
import json
from pathlib import Path

from tools.core_rules_order84_capture import capture_literals, fingerprint, source_inventory


def test_section00_complete_literals_owners_assertions_and_faq_screen() -> None:
    root = Path(__file__).resolve().parents[3]
    inventory = json.loads(Path(__file__).with_name("coverage.json").read_text(encoding="utf8"))
    raw = (root / inventory["capture_path"]).read_bytes()
    assert hashlib.sha256(raw).hexdigest() == inventory["capture_sha256"]
    capture = capture_literals(raw.decode("utf8"))
    assert inventory["category_hierarchy"] == next(
        c for c in capture["categories"] if c["number"] == "00"
    )
    expected = [r for r in source_inventory(capture) if r["category"] == "00"]
    assert len(expected) == inventory["source_rows"] == 1
    assert sum(len(r["blocks"]) for r in expected) == inventory["literal_blocks"] == 2
    assert len(inventory["faq_screen"]) == len(capture["faqs"]) == 64
    for original, screened in zip(capture["faqs"], inventory["faq_screen"], strict=True):
        assert original["id"] == screened["id"]
        assert fingerprint(original) == screened["source_sha256"]
        assert screened["rationale"]
    assert {
        q["faq_number"] for row in inventory["sources"] for q in row["colocated_faq_clarifications"]
    } == {18}
    for actual, row in zip(expected, inventory["sources"], strict=True):
        assert all(row[k] == value for k, value in actual.items())
        assert {b["ordinal"] for b in row["blocks"]} == {
            n for ob in row["obligations"] for n in ob["source_blocks"]
        }
        for ob in row["obligations"] + row["colocated_faq_clarifications"]:
            if ob.get("kind") == "nonoperative":
                assert ob["classification"] in {"metadata", "context"}
                assert ob["reason"]
                continue
            assert ob["owners"]
            assert ob["semantic_assertions"]
            for owner in ob["owners"]:
                path, symbol = owner.split(":")
                tree = ast.parse((root / path).read_text(encoding="utf8"))
                assert any(
                    isinstance(n, ast.FunctionDef | ast.ClassDef) and n.name == symbol.split(".")[0]
                    for n in tree.body
                )
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
                assert [
                    ast.unparse(n) for n in ast.walk(function) if isinstance(n, ast.Assert)
                ] == binding["assertions"]
                assert binding["assertions"] or binding["expected_exceptions"]
                assert binding["native_provider_or_roster_admission"] is False
