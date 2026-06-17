from __future__ import annotations

import ast
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
MOVEMENT_PHASE = ROOT / "src" / "warhammer40k_core" / "engine" / "phases" / "movement.py"
CHARGE_PHASE = ROOT / "src" / "warhammer40k_core" / "engine" / "phases" / "charge.py"
FIGHT_PHASE = ROOT / "src" / "warhammer40k_core" / "engine" / "phases" / "fight.py"
STRATAGEMS = ROOT / "src" / "warhammer40k_core" / "engine" / "stratagems.py"
TRIGGERED_MOVEMENT = ROOT / "src" / "warhammer40k_core" / "engine" / "triggered_movement.py"

REQUIRED_GEOMETRY_KEYWORDS = {
    "resolve_normal_move": frozenset(
        ("battlefield_width_inches", "battlefield_depth_inches", "terrain_features")
    ),
    "resolve_advance_move": frozenset(
        ("battlefield_width_inches", "battlefield_depth_inches", "terrain_features")
    ),
    "resolve_fall_back_move": frozenset(
        ("battlefield_width_inches", "battlefield_depth_inches", "terrain_features")
    ),
    "_aircraft_reserve_transition_reason_for_normal_move": frozenset(
        ("battlefield_width_inches", "battlefield_depth_inches")
    ),
}
LIVE_MOVEMENT_FAMILY_CALLS = (
    (
        CHARGE_PHASE,
        "resolve_charge_move",
        frozenset(("battlefield_width_inches", "battlefield_depth_inches", "terrain_features")),
    ),
    (
        FIGHT_PHASE,
        "resolve_fight_movement",
        frozenset(("battlefield_width_inches", "battlefield_depth_inches", "terrain_features")),
    ),
    (
        STRATAGEMS,
        "resolve_charge_move",
        frozenset(("battlefield_width_inches", "battlefield_depth_inches", "terrain_features")),
    ),
    (
        TRIGGERED_MOVEMENT,
        "resolve_triggered_movement",
        frozenset(("battlefield_width_inches", "battlefield_depth_inches", "terrain_features")),
    ),
)


def test_live_movement_proposals_pass_mission_geometry_to_resolvers() -> None:
    tree = ast.parse(MOVEMENT_PHASE.read_text(encoding="utf-8"), filename=str(MOVEMENT_PHASE))
    handler = _function_by_name(tree, "_apply_movement_proposal_decision")

    assert _function_calls(handler, "live_battlefield_geometry_for_state")

    violations: list[str] = []
    for node in ast.walk(handler):
        if not isinstance(node, ast.Call):
            continue
        call_name = _call_name(node)
        if call_name not in REQUIRED_GEOMETRY_KEYWORDS:
            continue
        keyword_names = {keyword.arg for keyword in node.keywords if keyword.arg is not None}
        missing = REQUIRED_GEOMETRY_KEYWORDS[call_name] - keyword_names
        if missing:
            violations.append(f"{call_name} missing {', '.join(sorted(missing))}")

    assert not violations, (
        "Live movement proposal resolution must pass active battlefield geometry:\n"
        + "\n".join(violations)
    )


def test_live_movement_family_calls_pass_battlefield_geometry() -> None:
    violations: list[str] = []
    for path, call_name, required_keywords in LIVE_MOVEMENT_FAMILY_CALLS:
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        if not _module_calls(tree, "live_battlefield_geometry_for_state"):
            violations.append(f"{path.relative_to(ROOT)} does not call live geometry helper")
        for node in ast.walk(tree):
            if not isinstance(node, ast.Call):
                continue
            if _call_name(node) != call_name:
                continue
            keyword_names = {keyword.arg for keyword in node.keywords if keyword.arg is not None}
            missing = required_keywords - keyword_names
            if missing:
                violations.append(
                    f"{path.relative_to(ROOT)}:{node.lineno} {call_name} missing "
                    + ", ".join(sorted(missing))
                )

    assert not violations, (
        "Live movement-family calls must pass active battlefield geometry:\n"
        + "\n".join(violations)
    )


def _function_by_name(tree: ast.AST, name: str) -> ast.FunctionDef:
    for node in ast.walk(tree):
        if isinstance(node, ast.FunctionDef) and node.name == name:
            return node
    raise AssertionError(f"Missing function: {name}")


def _function_calls(node: ast.FunctionDef, function_name: str) -> bool:
    for child in ast.walk(node):
        if not isinstance(child, ast.Call):
            continue
        if _call_name(child) == function_name:
            return True
    return False


def _module_calls(tree: ast.AST, function_name: str) -> bool:
    for child in ast.walk(tree):
        if not isinstance(child, ast.Call):
            continue
        if _call_name(child) == function_name:
            return True
    return False


def _call_name(node: ast.Call) -> str:
    if isinstance(node.func, ast.Name):
        return node.func.id
    if isinstance(node.func, ast.Attribute):
        return node.func.attr
    return ""
