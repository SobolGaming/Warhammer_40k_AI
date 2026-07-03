from __future__ import annotations

import ast
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
CORE = ROOT / "src" / "warhammer40k_core" / "core"
MOVEMENT_LEGALITY = ROOT / "src" / "warhammer40k_core" / "engine" / "movement_legality.py"
MOVEMENT_PHASE = ROOT / "src" / "warhammer40k_core" / "engine" / "phases" / "movement.py"
MOVEMENT_PHASE_FILES = (
    MOVEMENT_PHASE,
    *sorted(MOVEMENT_PHASE.parent.glob("movement_*.py")),
)
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


def test_movement_legality_gates_friendly_vehicle_monster_blockers_by_mover() -> None:
    tree = ast.parse(
        MOVEMENT_LEGALITY.read_text(encoding="utf-8"),
        filename=str(MOVEMENT_LEGALITY),
    )
    contexts = [
        node
        for node in ast.walk(tree)
        if isinstance(node, ast.FunctionDef) and node.name == "to_path_validation_context"
    ]
    assert len(contexts) == 1, "MovementLegalityContext must own pathing-context conversion."
    context = contexts[0]

    gates_on_mover_keyword = any(
        isinstance(node, ast.Attribute)
        and node.attr == "blocks_friendly_vehicle_monster_pass_through"
        for node in ast.walk(context)
    )
    passes_filtered_blockers = False
    passes_enemy_blockers = False
    for node in ast.walk(context):
        if not isinstance(node, ast.Call):
            continue
        if not isinstance(node.func, ast.Name) or node.func.id != "PathValidationContext":
            continue
        for keyword in node.keywords:
            if keyword.arg != "friendly_vehicle_monster_model_ids":
                continue
            if (
                isinstance(keyword.value, ast.Name)
                and keyword.value.id == "friendly_vehicle_monster_blockers"
            ):
                passes_filtered_blockers = True
        for keyword in node.keywords:
            if keyword.arg != "enemy_vehicle_monster_model_ids":
                continue
            if (
                isinstance(keyword.value, ast.Name)
                and keyword.value.id == "enemy_vehicle_monster_blockers"
            ):
                passes_enemy_blockers = True

    assert gates_on_mover_keyword, "Friendly VEHICLE/MONSTER transit blockers must gate on mover."
    assert passes_filtered_blockers, "Pathing must receive the filtered blocker set."
    assert passes_enemy_blockers, "Pathing must receive the filtered enemy blocker set."


def test_movement_phase_has_no_public_reinforcements_step_tokens() -> None:
    source = "\n".join(path.read_text(encoding="utf-8") for path in MOVEMENT_PHASE_FILES)
    forbidden_tokens = (
        "reinforcements_step_completed",
        "reinforcements_waiting_for_arrival_choice",
        '"reinforcements_complete"',
        "reinforcements_step_entered",
        '"step": MovementPhaseStepKind.REINFORCEMENTS.value',
    )
    violations = [token for token in forbidden_tokens if token in source]

    assert not violations, "Reserve arrivals must stay inside Move Units:\n" + "\n".join(violations)
