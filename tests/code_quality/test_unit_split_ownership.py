"""Physical ownership must have one shared validator after model-preserving splits."""

from __future__ import annotations

import ast
from pathlib import Path

ENGINE = Path(__file__).resolve().parents[2] / "src/warhammer40k_core/engine"


def test_model_id_prefix_ownership_checks_live_only_in_shared_owner() -> None:
    violations: list[str] = []
    for path in ENGINE.rglob("*.py"):
        if path.name == "unit_ownership.py":
            continue
        for node in ast.walk(ast.parse(path.read_text(encoding="utf-8"))):
            if not isinstance(node, ast.Call) or not isinstance(node.func, ast.Attribute):
                continue
            if node.func.attr == "startswith" and "model_instance_id" in ast.unparse(
                node.func.value
            ):
                violations.append(f"{path.relative_to(ENGINE)}:{node.lineno}")
    assert not violations, "Local model-prefix ownership checks bypass split lineage: " + repr(
        violations
    )
