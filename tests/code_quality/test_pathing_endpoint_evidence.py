from __future__ import annotations

import ast
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
PATHING = ROOT / "src" / "warhammer40k_core" / "geometry" / "pathing.py"


def test_endpoint_only_path_checks_are_zero_displacement_aware() -> None:
    tree = ast.parse(PATHING.read_text(encoding="utf-8"), filename=str(PATHING))
    evidence_call_owners = {
        node.name
        for node in ast.walk(tree)
        if isinstance(node, ast.FunctionDef)
        and _function_calls(node, "_has_non_endpoint_interior_pose")
    }
    assert evidence_call_owners == {"_is_endpoint_only_real_movement_path"}

    endpoint_helper = _function_by_name(tree, "_is_endpoint_only_real_movement_path")
    assert _function_calls(endpoint_helper, "_is_zero_displacement_path")


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
