"""Nonbehavioral inventory checks; semantic coverage lives in the linked tests."""

import ast
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]


def test_complete_hierarchy_and_owned_faq_account_for_every_adopted_clause() -> None:
    mapping = json.loads(Path(__file__).with_name("coverage.json").read_text(encoding="utf-8"))
    ledger = json.loads(
        (ROOT / "data/source_audits/order97/categories/05.json").read_text(encoding="utf-8")
    )
    expected = {r["requirement_id"] for row in ledger for r in row["requirements"]}
    actual = [r["id"] for row in mapping["sources"] for r in row["requirements"]]
    assert len(actual) == len(set(actual)) == 82
    assert set(actual) == expected
    assert len(mapping["sources"]) == 22
    assert sum(row["source_id"].startswith("faq:") for row in mapping["sources"]) == 7
    assert mapping["unadopted_gaps"] == []


def test_each_mapping_targets_an_actual_semantic_assertion() -> None:
    mapping = json.loads(Path(__file__).with_name("coverage.json").read_text(encoding="utf-8"))
    for source in mapping["sources"]:
        for clause in source["requirements"]:
            assert clause["asserting_tests"]
            assert clause["engine_owners"]
            for evidence in clause["semantic_assertions"]:
                file, name = evidence["node"].split("::")
                assert Path(file).name != Path(__file__).name
                tree = ast.parse((ROOT / file).read_text(encoding="utf-8"))
                function = next(
                    n for n in tree.body if isinstance(n, ast.FunctionDef) and n.name == name
                )
                actual = [
                    ast.unparse(n)
                    for n in ast.walk(function)
                    if isinstance(n, ast.Assert)
                    or (
                        isinstance(n, ast.With)
                        and any("pytest.raises" in ast.unparse(i.context_expr) for i in n.items)
                    )
                ]
                assert actual == evidence["assertions"]
                assert actual


def test_source_hashes_qualifications_and_all_context_blocks_are_preserved() -> None:
    mapping = json.loads(Path(__file__).with_name("coverage.json").read_text(encoding="utf-8"))
    adopted = {
        r["row_id"]: r
        for r in json.loads(
            (ROOT / "data/source_audits/order97/selected-sources.json").read_text(encoding="utf-8")
        )
    }
    ledger = {
        r["requirement_id"]: r
        for row in json.loads(
            (ROOT / "data/source_audits/order97/categories/05.json").read_text(encoding="utf-8")
        )
        for r in row["requirements"]
    }
    for source in mapping["sources"]:
        original = adopted[source["source_id"]]
        assert source["source_sha256"] == original["source_sha256"]
        assert source["blocks"] == original["blocks"]
        accounted = {
            i for r in (*source["requirements"], *source["context"]) for i in r["source_blocks"]
        }
        assert accounted == {b["ordinal"] for b in original["blocks"]}
        for clause in source["requirements"]:
            assert clause["retained_prior_qualifications"] == ledger[clause["id"]]["qualifications"]
