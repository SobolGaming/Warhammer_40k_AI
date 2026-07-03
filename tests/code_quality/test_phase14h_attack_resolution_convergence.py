from __future__ import annotations

import ast
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SRC_ROOT = ROOT / "src" / "warhammer40k_core"
ATTACK_SEQUENCE_PATH = ROOT / "src" / "warhammer40k_core" / "engine" / "attack_sequence.py"
ATTACK_SEQUENCE_SPLIT_PATHS = tuple(sorted(ATTACK_SEQUENCE_PATH.parent.glob("attack_sequence*.py")))


def _attack_sequence_module_sources() -> tuple[str, ...]:
    return tuple(path.read_text(encoding="utf-8") for path in ATTACK_SEQUENCE_SPLIT_PATHS)


def test_phase14h_single_save_resolution_entry_point() -> None:
    trees = tuple(ast.parse(source) for source in _attack_sequence_module_sources())
    function_names = {
        node.name for tree in trees for node in ast.walk(tree) if isinstance(node, ast.FunctionDef)
    }

    retired_symbols = {
        "_resolve_save_and_damage",
        "_resolve_allocation_stage",
        "_continue_after_allocation_group",
        "_attack_pool_can_use_grouped_allocation_host",
        "_allocation_group_has_interrupting_damage_choices",
    }
    assert function_names.isdisjoint(retired_symbols)
    assert "_resolve_grouped_damage_from" in function_names

    saving_throw_callers: list[str] = []
    for tree in trees:
        for node in ast.walk(tree):
            if not isinstance(node, ast.FunctionDef):
                continue
            if any(
                isinstance(child, ast.Call)
                and isinstance(child.func, ast.Name)
                and child.func.id == "resolve_saving_throw"
                for child in ast.walk(node)
            ):
                saving_throw_callers.append(node.name)

    assert saving_throw_callers == ["_resolve_grouped_damage_from"]


def test_phase14h_retired_attack_allocation_surface_is_absent() -> None:
    retired_text = (
        "select_attack_allocation",
        "SELECT_ATTACK_ALLOCATION_DECISION_TYPE",
        "AttackAllocationDecision",
        "build_attack_allocation_request",
    )
    offenders: list[str] = []
    for path in SRC_ROOT.rglob("*.py"):
        text = path.read_text(encoding="utf-8")
        if any(symbol in text for symbol in retired_text):
            offenders.append(str(path.relative_to(ROOT)))

    assert offenders == []
