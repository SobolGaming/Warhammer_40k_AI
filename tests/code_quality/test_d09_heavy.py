"""Keep Heavy's source predicate separate from stationary movement semantics."""

import ast
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


def test_heavy_uses_setup_and_accepted_distance_without_action_label_veto() -> None:
    source = ROOT / "src/warhammer40k_core/engine/phases/shooting_targeting.py"
    tree = ast.parse(source.read_text(encoding="utf-8"))
    heavy = next(
        node
        for node in tree.body
        if isinstance(node, ast.FunctionDef)
        and node.name == "_rules_unit_within_heavy_movement_allowance"
    )
    calls = {
        node.func.id
        for node in ast.walk(heavy)
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Name)
    }
    assert "_rules_unit_set_up_this_turn" in calls
    assert "models_within_turn_distance" in calls
    assert "_rules_unit_has_no_advance_fall_back_or_setup" not in calls
    stationary = next(
        node
        for node in tree.body
        if isinstance(node, ast.FunctionDef) and node.name == "_rules_unit_remained_stationary"
    )
    assert any(
        isinstance(node, ast.Call)
        and isinstance(node.func, ast.Name)
        and node.func.id == "_rules_unit_has_no_advance_fall_back_or_setup"
        for node in ast.walk(stationary)
    )


def test_original_advanced_negative_keeps_every_gameplay_assertion() -> None:
    original = ast.parse(
        (ROOT / "data/source_audits/d09/original-Advance-negative.py.txt").read_text(
            encoding="utf-8"
        )
    )
    current = ast.parse(
        (ROOT / "tests/unit/test_phase13b_shooting_declarations.py").read_text(encoding="utf-8")
    )
    name = "test_phase13d_advanced_unit_allowed_to_shoot_does_not_gain_heavy_modifier"
    function = next(
        node for node in current.body if isinstance(node, ast.FunctionDef) and node.name == name
    )
    before = [
        ast.dump(node, include_attributes=False)
        for node in ast.walk(original)
        if isinstance(node, ast.Assert)
    ]
    after = [
        ast.dump(node, include_attributes=False)
        for node in ast.walk(function)
        if isinstance(node, ast.Assert)
    ]
    assert len(before) == 3
    assert before == after
