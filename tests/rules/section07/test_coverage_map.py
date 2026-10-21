"""Source and assertion authentication only; these are not semantic coverage."""

import ast
import hashlib
import json
from pathlib import Path

from tools.core_rules_order84_capture import capture_literals, source_inventory

ROOT = Path(__file__).resolve().parents[3]


def test_complete_hierarchy_blocks_and_current_raw_capture_are_authenticated() -> None:
    mapping = json.loads(Path(__file__).with_name("coverage.json").read_text(encoding="utf-8"))
    selected = json.loads(
        (ROOT / "data/source_audits/order97/selected-sources.json").read_text(encoding="utf-8")
    )
    current = json.loads(
        (ROOT / "data/source_audits/order135/retained-current-sources.json").read_text(
            encoding="utf-8"
        )
    )
    raw = capture_literals(
        (ROOT / "data/source_audits/v963_shock/captures/core-page.js").read_text(encoding="utf-8")
    )
    raw_rows = {r["row_id"]: r for r in source_inventory(raw)}
    rows = {r["row_id"]: r for r in selected if r["category"] == "07"}
    assert {s["source_id"] for s in mapping["sources"]} == set(rows)
    assert len(rows) == 6
    assert [s["locator"] for s in mapping["sources"]] == [
        "07.00",
        "07.01",
        "07.02",
        "07.02.01",
        "07.02.02",
        "07.03",
    ]
    for source in mapping["sources"]:
        row = rows[source["source_id"]]
        assert source["blocks"] == row["blocks"]
        assert source["source_sha256"] == raw_rows[source["source_id"]]["source_sha256"]
        accounted = {
            ordinal
            for r in (*source["requirements"], *source["context"])
            for ordinal in r["source_blocks"]
        }
        assert accounted == {block["ordinal"] for block in source["blocks"]}
    assert (
        len(current["full_current_core_capture"]["faqs"])
        == mapping["faq_ownership"]["reviewed_current_faq_count"]
        == 64
    )
    assert mapping["faq_ownership"]["locally_owned"] == []
    assert mapping["unadopted_gaps"] == []
    for filename, expected in mapping["authenticated_inputs"].items():
        assert hashlib.sha256((ROOT / filename).read_bytes()).hexdigest() == expected


def test_all_original_obligations_keep_qualifications_and_real_assertion_bodies() -> None:
    mapping = json.loads(Path(__file__).with_name("coverage.json").read_text(encoding="utf-8"))
    ledger = json.loads(
        (ROOT / "data/source_audits/order97/categories/07.json").read_text(encoding="utf-8")
    )
    original = {r["requirement_id"]: r for row in ledger for r in row["requirements"]}
    requirements = [r for row in mapping["sources"] for r in row["requirements"]]
    assert len(requirements) == len({r["id"] for r in requirements}) == 22
    assert {r["id"] for r in requirements} == set(original)
    for requirement in requirements:
        assert (
            requirement["retained_prior_qualifications"]
            == original[requirement["id"]]["qualifications"]
        )
        assert requirement["engine_owners"]
        for evidence in requirement["semantic_assertions"]:
            file, name = evidence["node"].split("::")
            assert Path(file).name != Path(__file__).name
            tree = ast.parse((ROOT / file).read_text(encoding="utf-8"))
            function = next(
                f for f in tree.body if isinstance(f, ast.FunctionDef) and f.name == name
            )
            assert (
                hashlib.sha256(ast.dump(function, include_attributes=False).encode()).hexdigest()
                == evidence["function_ast_sha256"]
            )
            assertions = [
                ast.unparse(n)
                for n in ast.walk(function)
                if isinstance(n, ast.Assert)
                or (
                    isinstance(n, ast.With)
                    and any("pytest.raises" in ast.unparse(i.context_expr) for i in n.items)
                )
            ]
            assert assertions == evidence["assertions"]
            assert assertions
