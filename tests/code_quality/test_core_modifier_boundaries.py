from __future__ import annotations

import ast
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
PACKAGE = ROOT / "src/warhammer40k_core"


def _calls(relative_path: str, function_name: str, *, class_name: str | None = None) -> set[str]:
    tree = ast.parse((PACKAGE / relative_path).read_text(encoding="utf-8"))
    scope: ast.AST = tree
    if class_name is not None:
        scope = next(
            node for node in tree.body if isinstance(node, ast.ClassDef) and node.name == class_name
        )
    function = next(
        node
        for node in ast.walk(scope)
        if isinstance(node, ast.FunctionDef) and node.name == function_name
    )
    return {
        node.func.id if isinstance(node.func, ast.Name) else node.func.attr
        for node in ast.walk(function)
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Name | ast.Attribute)
    }


def test_modified_dice_and_targeting_ranges_use_the_shared_limits() -> None:
    assert "resolve_roll_modifiers" in _calls("core/modified_dice.py", "from_unmodified")
    assert "resolve_roll_modifiers" in _calls(
        "core/modified_dice.py",
        "__post_init__",
        class_name="ModifiedRollResult",
    )
    assert "resolve_targeting_range" in _calls(
        "engine/hidden_detection.py",
        "hidden_detection_eligible_target_model_ids",
    )
    assert "resolve_targeting_range" in _calls(
        "engine/lone_operative.py", "lone_operative_target_allowed"
    )
    for name in ("_roll_hit", "_roll_wound", "_reroll_wound_for_twin_linked_if_needed"):
        assert "bound_modified_roll" in _calls("engine/attack_sequence_hit_wound.py", name)
    assert "bound_modified_roll" in _calls("engine/saves.py", "_final_roll_for_save_option")


def test_advance_and_charge_never_embed_modifiers_in_raw_dice() -> None:
    for relative_path in ("engine/advance_roll.py", "engine/charge_declaration.py"):
        tree = ast.parse((PACKAGE / relative_path).read_text(encoding="utf-8"))
        expressions = [
            node
            for node in ast.walk(tree)
            if isinstance(node, ast.Call)
            and isinstance(node.func, ast.Name)
            and node.func.id == "DiceExpression"
        ]
        assert expressions
        for expression in expressions:
            for keyword in expression.keywords:
                if keyword.arg == "modifier":
                    assert isinstance(keyword.value, ast.Constant)
                    assert keyword.value.value == 0
