from __future__ import annotations

import ast
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
CORE = ROOT / "src" / "warhammer40k_core" / "core"
UNIT_MODULES = (
    CORE / "unit.py",
    CORE / "attached_unit.py",
    CORE / "unit_group.py",
)


def test_core_unit_modules_do_not_use_ambiguous_models_attribute() -> None:
    violations: list[str] = []

    for path in UNIT_MODULES:
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        for node in ast.walk(tree):
            if isinstance(node, ast.Attribute) and node.attr == "models":
                violations.append(f"{path.relative_to(ROOT)} uses .models")
            if isinstance(node, ast.FunctionDef) and node.name == "models":
                violations.append(f"{path.relative_to(ROOT)} defines models()")
            if (
                isinstance(node, ast.AnnAssign)
                and isinstance(node.target, ast.Name)
                and node.target.id == "models"
            ):
                violations.append(f"{path.relative_to(ROOT)} defines models")

    assert not violations, "Use unit.own_models and unit_group.all_models():\n" + "\n".join(
        violations
    )
