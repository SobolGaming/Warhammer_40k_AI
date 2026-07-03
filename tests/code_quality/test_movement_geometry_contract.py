from __future__ import annotations

import ast
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
MOVEMENT_PHASE = ROOT / "src" / "warhammer40k_core" / "engine" / "phases" / "movement.py"
MOVEMENT_PHASE_FILES = (
    MOVEMENT_PHASE,
    *sorted(MOVEMENT_PHASE.parent.glob("movement_*.py")),
)
CHARGE_PHASE = ROOT / "src" / "warhammer40k_core" / "engine" / "phases" / "charge.py"
FIGHT_PHASE = ROOT / "src" / "warhammer40k_core" / "engine" / "phases" / "fight.py"
FIGHT_RESOLUTION = ROOT / "src" / "warhammer40k_core" / "engine" / "fight_resolution.py"
STRATAGEMS = ROOT / "src" / "warhammer40k_core" / "engine" / "stratagems.py"
TRIGGERED_MOVEMENT = ROOT / "src" / "warhammer40k_core" / "engine" / "triggered_movement.py"

LIVE_MOVEMENT_CALLS = (
    (MOVEMENT_PHASE, "_apply_movement_proposal_decision", "resolve_normal_move"),
    (MOVEMENT_PHASE, "_apply_movement_proposal_decision", "resolve_advance_move"),
    (MOVEMENT_PHASE, "_apply_movement_proposal_decision", "resolve_fall_back_move"),
    (CHARGE_PHASE, "_apply_charge_move_proposal_decision", "resolve_charge_move"),
    (FIGHT_PHASE, "_apply_fight_movement_proposal", "resolve_fight_movement"),
    (STRATAGEMS, "apply_heroic_intervention_charge_move", "resolve_charge_move"),
    (TRIGGERED_MOVEMENT, "request_from_state", "resolve_triggered_movement"),
    (TRIGGERED_MOVEMENT, "apply_decision", "resolve_triggered_movement"),
    (TRIGGERED_MOVEMENT, "apply_proposal_decision", "resolve_triggered_movement"),
)
GEOMETRY_KEYWORDS = frozenset(
    ("battlefield_width_inches", "battlefield_depth_inches", "terrain_features")
)
RESOLVER_GEOMETRY_READS = (
    (MOVEMENT_PHASE, "resolve_normal_move"),
    (MOVEMENT_PHASE, "resolve_advance_move"),
    (MOVEMENT_PHASE, "resolve_fall_back_move"),
    (CHARGE_PHASE, "resolve_charge_move"),
    (FIGHT_RESOLUTION, "_validate_fight_paths"),
    (TRIGGERED_MOVEMENT, "resolve_triggered_movement"),
)


def test_live_movement_callers_do_not_pass_copied_battlefield_geometry() -> None:
    violations: list[str] = []
    for path, function_name, call_name in LIVE_MOVEMENT_CALLS:
        for source_path, tree in _parsed_sources(path):
            if _module_imports_name(tree, "live_battlefield_geometry_for_state"):
                violations.append(f"{source_path.relative_to(ROOT)} imports live geometry helper")
        source_path, function = _function_by_name(path, function_name)
        for node in ast.walk(function):
            if not isinstance(node, ast.Call):
                continue
            if _call_name(node) != call_name:
                continue
            copied_keywords = {
                keyword.arg
                for keyword in node.keywords
                if keyword.arg is not None and keyword.arg in GEOMETRY_KEYWORDS
            }
            if copied_keywords:
                violations.append(
                    f"{source_path.relative_to(ROOT)}:{node.lineno} {call_name} passes "
                    + ", ".join(sorted(copied_keywords))
                )

    assert not violations, (
        "Live movement-family callers must use the manifested BattlefieldRuntimeState "
        "through the resolver scenario instead of copying geometry into each phase:\n"
        + "\n".join(violations)
    )


def test_movement_resolvers_read_manifested_battlefield_geometry() -> None:
    violations: list[str] = []
    for path, function_name in RESOLVER_GEOMETRY_READS:
        source_path, function = _function_by_name(path, function_name)
        source = ast.unparse(function)
        missing: list[str] = []
        if "scenario.battlefield_state.battlefield_width_inches" not in source:
            missing.append("battlefield_width_inches")
        if "scenario.battlefield_state.battlefield_depth_inches" not in source:
            missing.append("battlefield_depth_inches")
        if "scenario.battlefield_state.terrain_features" not in source:
            missing.append("terrain_features")
        if missing:
            violations.append(
                f"{source_path.relative_to(ROOT)}:{function.lineno} {function_name} missing "
                + ", ".join(missing)
            )

    assert not violations, (
        "Movement-family resolvers must read geometry from scenario.battlefield_state:\n"
        + "\n".join(violations)
    )


def _function_by_name(path: Path, name: str) -> tuple[Path, ast.FunctionDef]:
    for source_path, tree in _parsed_sources(path):
        for node in ast.walk(tree):
            if isinstance(node, ast.FunctionDef) and node.name == name:
                return source_path, node
    raise AssertionError(f"Missing function: {name}")


def _parsed_sources(path: Path) -> tuple[tuple[Path, ast.AST], ...]:
    return tuple(
        (source_path, ast.parse(source_path.read_text(encoding="utf-8"), filename=str(source_path)))
        for source_path in _source_paths(path)
    )


def _source_paths(path: Path) -> tuple[Path, ...]:
    if path == MOVEMENT_PHASE:
        return MOVEMENT_PHASE_FILES
    return (path,)


def _module_imports_name(tree: ast.AST, imported_name: str) -> bool:
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom):
            for alias in node.names:
                if alias.name == imported_name or alias.asname == imported_name:
                    return True
    return False


def _call_name(node: ast.Call) -> str:
    if isinstance(node.func, ast.Name):
        return node.func.id
    if isinstance(node.func, ast.Attribute):
        return node.func.attr
    return ""
