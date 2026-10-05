"""Catalog identity and effective consumers retain selected immutable authority."""

from __future__ import annotations

import ast
import hashlib
import json
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]


def test_name_keyword_permission_preserves_exact_source_and_official_admission() -> None:
    audit = json.loads((ROOT / "data/source_audits/order123/source.audit.json").read_bytes())
    raw = (ROOT / audit["selected_sources_path"]).read_bytes()
    selected = {row["row_id"]: row for row in json.loads(raw)}
    assert audit["selected_sources_sha256"] == hashlib.sha256(raw).hexdigest()
    assert audit["selected_core_rows"] == [selected["rule:02:02.01.01:1"]]
    assert audit["requirements"] == ["02.01.01-obligation-01"]
    assert audit["current_faction_admission"] is False
    assert audit["source_admission_unchanged"] is True
    official = audit["official_provider_trace"]
    for kind in ("catalog", "reconciliation"):
        assert (
            hashlib.sha256((ROOT / official[kind + "_path"]).read_bytes()).hexdigest()
            == (official[kind + "_sha256"])
        )


@pytest.mark.parametrize(
    ("path", "function"),
    [
        ("engine/army_mustering.py", "_datasheet_keyword_set"),
        ("engine/army_mustering.py", "_datasheet_has_any_keyword"),
        ("engine/army_mustering.py", "_transport_capacity_allows_datasheet"),
        ("engine/list_validation.py", "_datasheet_has_any_keyword"),
        ("engine/roster_unit_limits.py", "datasheet_unit_limit"),
    ],
)
def test_catalog_name_queries_consume_shared_effective_identity(path: str, function: str) -> None:
    tree = ast.parse((ROOT / "src/warhammer40k_core" / path).read_text(encoding="utf-8"))
    owner = next(
        node for node in tree.body if isinstance(node, ast.FunctionDef) and node.name == function
    )
    attributes = {ast.unparse(node) for node in ast.walk(owner) if isinstance(node, ast.Attribute)}
    assert "datasheet.effective_keywords" in attributes
    assert "datasheet.keywords.keywords" not in attributes


def test_runtime_keyword_owners_do_not_derive_identity_from_display_labels() -> None:
    for path in ("unit_keyword_queries.py", "catalog_model_scope.py", "rule_target_resolution.py"):
        tree = ast.parse((ROOT / "src/warhammer40k_core/engine" / path).read_text(encoding="utf-8"))
        assert not any(
            isinstance(node, ast.Attribute) and node.attr == "name" for node in ast.walk(tree)
        )
