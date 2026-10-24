"""Inventory integrity only. These checks are not semantic rule coverage."""

import ast
import hashlib
import json
from pathlib import Path

from tests.shared.repository_root import REPOSITORY_ROOT


def test_every_retained_section02_clause_has_one_explicit_disposition() -> None:
    coverage = json.loads(Path(__file__).with_name("coverage.json").read_text(encoding="utf-8"))
    ledger = json.loads(
        (REPOSITORY_ROOT / "data/source_audits/order97/categories/02.json").read_text(
            encoding="utf-8"
        )
    )
    expected = {r["requirement_id"] for s in ledger for r in s["requirements"]}
    actual = [r["id"] for s in coverage["sources"] for r in s["requirements"]]
    assert len(actual) == len(set(actual)) == 100
    assert set(actual) == expected
    assert {s["source_id"] for s in coverage["sources"]} == {s["row_id"] for s in ledger}
    for source in coverage["sources"]:
        old = next(row for row in ledger if row["row_id"] == source["source_id"])
        assert source["context"] == old["nonoperative_blocks"]
        for requirement in source["requirements"]:
            assert requirement["engine_owners"]
            assert requirement["status"] in coverage["status_meanings"]
            if requirement["status"] != "behavior":
                assert requirement["remaining"]


def test_source_blocks_are_authenticated_and_faq_has_a_section_owner() -> None:
    coverage = json.loads(Path(__file__).with_name("coverage.json").read_text(encoding="utf-8"))
    sources = json.loads(
        (REPOSITORY_ROOT / "data/source_audits/order97/selected-sources.json").read_text(
            encoding="utf-8"
        )
    )
    indexed = {row["row_id"]: row for row in sources}
    for source in coverage["sources"]:
        original = indexed[source["source_id"]]
        assert source["source_sha256"] == original["source_sha256"]
        for block in original["blocks"]:
            canonical = json.dumps(
                block["value"], ensure_ascii=False, sort_keys=True, separators=(",", ":")
            )
            assert (
                hashlib.sha256(canonical.encode()).hexdigest()
                == source["block_sha256"][str(block["ordinal"])]
            )
        assert source["section"].startswith("02.")
    unadopted = [
        link for link in coverage["cross_section_links"] if link["status"] == "unadopted-v981"
    ]
    assert len(unadopted) == 3
    assert {link["owner"] for link in unadopted} == {"18"}
    assert {link["distinct_obligation"] for link in unadopted} == {"V981-Q03"}


def test_mapped_new_assertions_resolve_to_discoverable_test_functions() -> None:
    coverage = json.loads(Path(__file__).with_name("coverage.json").read_text(encoding="utf-8"))
    for source in coverage["sources"]:
        for requirement in source["requirements"]:
            for node in requirement["tests"]:
                relative, name = node.split("::")
                path = REPOSITORY_ROOT / relative
                assert path.name.startswith("test_")
                functions = {
                    n.name
                    for n in ast.parse(path.read_text()).body
                    if isinstance(n, ast.FunctionDef)
                }
                assert name.startswith("test_")
                assert name in functions
