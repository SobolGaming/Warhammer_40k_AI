from __future__ import annotations

import ast
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
PATHING = ROOT / "src" / "warhammer40k_core" / "geometry" / "pathing.py"


def test_degenerate_endpoint_only_path_checks_are_two_point_and_zero_displacement_aware() -> None:
    tree = ast.parse(PATHING.read_text(encoding="utf-8"), filename=str(PATHING))
    evidence_call_owners = {
        node.name
        for node in ast.walk(tree)
        if isinstance(node, ast.FunctionDef)
        and _function_calls(node, "_has_non_endpoint_interior_pose")
    }
    assert evidence_call_owners == {"is_degenerate_endpoint_only_real_movement_path"}

    endpoint_helper = _function_by_name(tree, "is_degenerate_endpoint_only_real_movement_path")
    assert _function_calls(endpoint_helper, "_is_zero_displacement_path")
    assert _function_has_len_comparison(endpoint_helper, 2)


def _function_by_name(tree: ast.AST, name: str) -> ast.FunctionDef:
    for node in ast.walk(tree):
        if isinstance(node, ast.FunctionDef) and node.name == name:
            return node
    raise AssertionError(f"Missing function: {name}")


def _function_calls(node: ast.FunctionDef, function_name: str) -> bool:
    for child in ast.walk(node):
        if not isinstance(child, ast.Call):
            continue
        if isinstance(child.func, ast.Name) and child.func.id == function_name:
            return True
    return False


def _function_has_len_comparison(node: ast.FunctionDef, value: int) -> bool:
    for child in ast.walk(node):
        if not isinstance(child, ast.Compare):
            continue
        if len(child.ops) != 1 or not isinstance(child.ops[0], ast.Eq):
            continue
        if len(child.comparators) != 1:
            continue
        comparator = child.comparators[0]
        if not isinstance(comparator, ast.Constant) or comparator.value != value:
            continue
        left = child.left
        if not isinstance(left, ast.Call):
            continue
        if isinstance(left.func, ast.Name) and left.func.id == "len":
            return True
    return False
