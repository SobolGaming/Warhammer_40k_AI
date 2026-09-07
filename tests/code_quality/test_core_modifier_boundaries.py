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


def test_runtime_characteristic_owners_collect_operations_without_local_clamps() -> None:
    owners = (
        (
            "engine/generic_rule_attack_hooks.py",
            "generic_rule_modified_unit_characteristic",
            "resolve_runtime_characteristic",
        ),
        (
            "engine/runtime_characteristic_modifiers.py",
            "resolve_runtime_characteristic",
            "ModifierStack",
        ),
        (
            "engine/runtime_modifiers.py",
            "modified_unit_characteristic",
            "resolve_runtime_characteristic",
        ),
        ("engine/runtime_modifiers.py", "modified_objective_control", "resolve_objective_control"),
        (
            "engine/generic_rule_objective_control.py",
            "generic_rule_objective_control_trace",
            "resolve_runtime_objective_control",
        ),
        (
            "engine/movement_budget_modifiers.py",
            "_resolve_movement",
            "resolve_characteristic_value",
        ),
        (
            "engine/primary_mission_objective_control_authority.py",
            "resolve_checkpoint_objective_control",
            "resolve_objective_control",
        ),
    )
    for path, function, owner in owners:
        calls = _calls(path, function)
        assert owner in calls
        assert not calls.intersection({"max", "min", "ceil", "round"}), (path, function)


def test_typed_runtime_characteristic_producers_do_not_resolve_numeric_results() -> None:
    producers = 0
    for path in (PACKAGE / "engine").rglob("*.py"):
        tree = ast.parse(path.read_text(encoding="utf-8"))
        for function in ast.walk(tree):
            if not isinstance(function, ast.FunctionDef) or function.returns is None:
                continue
            if ast.unparse(function.returns) != "tuple[ModifierTerm, ...]":
                continue
            producers += 1
            for statement in ast.walk(function):
                if not isinstance(statement, ast.Return) or statement.value is None:
                    continue
                assert not isinstance(statement.value, ast.BinOp | ast.Constant), (
                    path,
                    function.name,
                )
                if isinstance(statement.value, ast.Call) and isinstance(
                    statement.value.func, ast.Name
                ):
                    assert statement.value.func.id not in {"max", "min", "ceil", "round"}, (
                        path,
                        function.name,
                    )
    assert producers >= 20


def test_checkpoint_authority_reconstructs_the_complete_resolved_characteristic() -> None:
    calls = _calls(
        "engine/primary_mission_boundary_checkpoint.py",
        "_validate_current_checkpoint_oc_resolutions",
    )
    assert {"resolve_checkpoint_objective_control", "canonical_json", "to_payload"} <= calls
