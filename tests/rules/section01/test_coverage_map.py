"""Inventory integrity only: these checks do not count as behavioral coverage."""

import ast
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]


def test_adopted_hierarchy_clauses_and_faq_are_accounted_once() -> None:
    coverage = json.loads(Path(__file__).with_name("coverage.json").read_text(encoding="utf-8"))
    ledger = json.loads(
        (ROOT / "data/source_audits/order97/categories/01.json").read_text(encoding="utf-8")
    )
    expected = {r["requirement_id"] for row in ledger for r in row["requirements"]}
    actual = [r["id"] for row in coverage["sources"] for r in row["requirements"]]
    assert len(actual) == len(set(actual)) == 143
    assert set(actual) == expected
    assert len(coverage["sources"]) == 38
    assert (
        sum(
            r["status"] == "external_owner"
            for row in coverage["sources"]
            for r in row["requirements"]
        )
        == 1
    )


def test_asserting_nodes_exist_without_using_metadata_as_behavior() -> None:
    coverage = json.loads(Path(__file__).with_name("coverage.json").read_text(encoding="utf-8"))
    for row in coverage["sources"]:
        for requirement in row["requirements"]:
            assert requirement["engine_owners"]
            if requirement["status"] == "external_owner":
                assert requirement["owner_section"] == "18"
                continue
            assert requirement["asserting_tests"]
            for node in requirement["asserting_tests"]:
                path, name = node.split("::")
                assert Path(path).name != Path(__file__).name
                tree = ast.parse((ROOT / path).read_text(encoding="utf-8"))
                assert name in {f.name for f in tree.body if isinstance(f, ast.FunctionDef)}


def test_source_fingerprints_and_nonoperative_blocks_are_explicit() -> None:
    coverage = json.loads(Path(__file__).with_name("coverage.json").read_text(encoding="utf-8"))
    sources = {
        r["row_id"]: r
        for r in json.loads(
            (ROOT / "data/source_audits/order97/selected-sources.json").read_text(encoding="utf-8")
        )
    }
    for row in coverage["sources"]:
        original = sources[row["source_id"]]
        assert row["source_sha256"] == original["source_sha256"]
        accounted = {i for r in row["requirements"] for i in r["source_blocks"]}
        accounted.update(i for r in row["context"] for i in r["source_blocks"])
        assert accounted == {block["ordinal"] for block in original["blocks"]}
    assert {r["section"] for r in coverage["unadopted_gaps"]} == {
        "01.02.12",
        "01.04.06",
    }
