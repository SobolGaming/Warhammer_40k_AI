from __future__ import annotations

import ast
from pathlib import Path

from warhammer40k_core.engine.lifecycle import GameLifecycle
from warhammer40k_core.engine.weapon_abilities import WEAPON_ABILITY_SELECTION_DECISION_TYPE

ROOT = Path(__file__).resolve().parents[2]
ENGINE_ROOT = ROOT / "src" / "warhammer40k_core" / "engine"
ADAPTER_CONTRACT = ROOT / "docs" / "ADAPTER_DECISION_CONTRACT.md"

_NESTED_DECISION_TYPE_ALLOWLIST = {
    WEAPON_ABILITY_SELECTION_DECISION_TYPE: (
        "Nested under shooting declaration required_weapon_ability_selections; keep the token for "
        "future Necrons Tesseract Vault DAMAGED profile support."
    ),
}


def test_engine_decision_type_constants_are_registered_or_documented_nested() -> None:
    decision_types = _engine_decision_type_constants()
    registered = set(
        GameLifecycle()._decision_dispatch_registry.registered_decision_types()  # pyright: ignore[reportPrivateUsage]
    )
    nested = set(_NESTED_DECISION_TYPE_ALLOWLIST)

    assert nested == {WEAPON_ABILITY_SELECTION_DECISION_TYPE}
    assert nested <= decision_types
    assert registered <= decision_types
    assert decision_types - registered == nested


def test_nested_weapon_ability_allowlist_is_documented_in_adapter_contract() -> None:
    contract = ADAPTER_CONTRACT.read_text(encoding="utf-8")

    assert WEAPON_ABILITY_SELECTION_DECISION_TYPE in contract
    assert "nested-decision allowlist" in contract
    assert "Tesseract Vault" in contract


def _engine_decision_type_constants() -> set[str]:
    values: set[str] = set()
    for path in sorted(ENGINE_ROOT.rglob("*.py")):
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        for node in tree.body:
            if not isinstance(node, ast.Assign):
                continue
            value = _string_constant(node.value)
            if value is None:
                continue
            for target in node.targets:
                if isinstance(target, ast.Name) and target.id.endswith("DECISION_TYPE"):
                    values.add(value)
    return values


def _string_constant(node: ast.expr) -> str | None:
    if not isinstance(node, ast.Constant):
        return None
    if type(node.value) is not str:
        return None
    return node.value
