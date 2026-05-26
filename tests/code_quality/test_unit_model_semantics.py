from __future__ import annotations

import ast
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
CORE = ROOT / "src" / "warhammer40k_core" / "core"
PATHING = ROOT / "src" / "warhammer40k_core" / "geometry" / "pathing.py"
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


def test_pathing_uses_alive_group_model_ids_for_movement() -> None:
    tree = ast.parse(PATHING.read_text(encoding="utf-8"), filename=str(PATHING))
    forbidden: list[str] = []
    uses_group_movement_ids = False

    for node in ast.walk(tree):
        if not isinstance(node, ast.Attribute):
            continue
        if node.attr == "model_ids_for_movement":
            uses_group_movement_ids = True
        if node.attr in {"all_model_ids", "all_models"}:
            forbidden.append(f"{PATHING.relative_to(ROOT)} uses {node.attr}")

    assert uses_group_movement_ids, "Pathing must use UnitGroup.model_ids_for_movement()."
    assert not forbidden, "Pathing must not move destroyed/all models:\n" + "\n".join(forbidden)
