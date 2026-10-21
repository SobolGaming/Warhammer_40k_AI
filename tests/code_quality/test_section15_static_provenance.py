"""The casualty repair must cover both permanent producers, with no live grant change."""

import ast
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2] / "src/warhammer40k_core/engine"


@pytest.mark.parametrize(
    "filename",
    [
        "catalog_conditional_leader_abilities.py",
        "catalog_static_attack_modifier_runtime.py",
    ],
)
def test_permanent_source_evidence_cannot_depend_on_live_unit_keyword_membership(
    filename: str,
) -> None:
    tree = ast.parse((ROOT / filename).read_text(encoding="utf8"))
    function = next(
        n
        for n in tree.body
        if isinstance(n, ast.FunctionDef) and n.name == "_persisting_effect_for_source"
    )
    values = [
        k.value
        for n in ast.walk(function)
        if isinstance(n, ast.Call)
        for k in n.keywords
        if k.arg == "source_keywords"
    ]
    assert len(values) == 1
    assert not any(
        isinstance(n, ast.Attribute) and n.attr in {"keywords", "faction_keywords"}
        for n in ast.walk(values[0])
    )
    assert isinstance(values[0], ast.Call)
    assert ast.unparse(values[0].func) == "static_rule_source_keywords"
