"""Inventory authentication only; none of these checks count as semantic coverage."""

import ast
import hashlib
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]


def test_complete_adopted_hierarchy_includes_current_visibility_faq() -> None:
    mapping = json.loads(Path(__file__).with_name("coverage.json").read_text(encoding="utf-8"))
    ledger = json.loads(
        (ROOT / "data/source_audits/order97/categories/06.json").read_text(encoding="utf-8")
    )
    original = {r["requirement_id"] for row in ledger for r in row["requirements"]}
    current = {f"faq-9638115f-b94b-4d05-ba62-df9fba2805ac-obligation-{i:02d}" for i in (1, 2)}
    ids = [r["id"] for row in mapping["sources"] for r in row["requirements"]]
    assert len(ids) == len(set(ids)) == 36
    assert set(ids) == original | current
    assert len(mapping["sources"]) == 12
    assert mapping["unadopted_gaps"] == []


def test_map_points_to_actual_assertions_and_preserves_qualifications() -> None:
    mapping = json.loads(Path(__file__).with_name("coverage.json").read_text(encoding="utf-8"))
    ledger = json.loads(
        (ROOT / "data/source_audits/order97/categories/06.json").read_text(encoding="utf-8")
    )
    old = {r["requirement_id"]: r for row in ledger for r in row["requirements"]}
    for source in mapping["sources"]:
        accounted = {
            i for r in (*source["requirements"], *source["context"]) for i in r["source_blocks"]
        }
        assert accounted == {b["ordinal"] for b in source["blocks"]}
        for r in source["requirements"]:
            if r["id"] in old:
                assert r["retained_prior_qualifications"] == old[r["id"]]["qualifications"]
            assert r["engine_owners"]
            assert r["asserting_tests"]
            for evidence in r["semantic_assertions"]:
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


def test_retained_blocks_and_current_faq_authority_match() -> None:
    mapping = json.loads(Path(__file__).with_name("coverage.json").read_text(encoding="utf-8"))
    adopted = {
        r["row_id"]: r
        for r in json.loads(
            (ROOT / "data/source_audits/order97/selected-sources.json").read_text(encoding="utf-8")
        )
    }
    audit = json.loads(
        (ROOT / "data/source_audits/order135/visibility-source.audit.json").read_text(
            encoding="utf-8"
        )
    )
    bindings = json.loads(
        (ROOT / "data/source_audits/order135/current-bindings.json").read_text(encoding="utf-8")
    )
    for source in mapping["sources"]:
        if source["source_id"] in adopted:
            assert source["blocks"] == adopted[source["source_id"]]["blocks"]
            assert source["source_sha256"] == adopted[source["source_id"]]["source_sha256"]
        else:
            assert source["source_id"] == "faq:9638115f-b94b-4d05-ba62-df9fba2805ac"
            assert bindings["current_new_faqs"][audit["selected_record"]["id"]]["category"] == "06"
            assert [b["value"] for b in source["blocks"]] == [
                audit["selected_record"]["question"],
                audit["selected_record"]["answer"],
            ]
        for block in source["blocks"]:
            assert (
                hashlib.sha256(
                    json.dumps(
                        block["value"], sort_keys=True, separators=(",", ":"), ensure_ascii=False
                    ).encode()
                ).hexdigest()
                == block["sha256"]
            )
