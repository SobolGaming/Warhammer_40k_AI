from __future__ import annotations

import ast
from pathlib import Path

ENGINE = Path(__file__).resolve().parents[2] / "src" / "warhammer40k_core" / "engine"


def test_materialization_runtime_and_restore_share_destruction_history_validation() -> None:
    for filename in (
        "catalog_model_materialization_runtime.py",
        "catalog_materialization_integrity.py",
    ):
        tree = ast.parse((ENGINE / filename).read_text(encoding="utf-8"))
        assert any(
            isinstance(node, ast.Call)
            and isinstance(node.func, ast.Name)
            and node.func.id == "validate_materialization_destruction_history"
            for node in ast.walk(tree)
        ), filename


def test_completed_casualty_consumers_do_not_require_current_model_membership() -> None:
    for filename, function_name in (
        ("catalog_model_materialization_runtime.py", "model_state_changed_unit_ids_for_sequence"),
        (
            "model_destruction_cause_completion_restore.py",
            "validate_mortal_wound_application_inventory",
        ),
        ("mortal_wound_application_authority.py", "validate_for_state"),
    ):
        tree = ast.parse((ENGINE / filename).read_text(encoding="utf-8"))
        functions = tuple(
            node
            for node in ast.walk(tree)
            if isinstance(node, ast.FunctionDef) and node.name == function_name
        )
        assert functions, filename
        assert not any(
            isinstance(node, ast.Call)
            and isinstance(node.func, ast.Attribute)
            and node.func.attr == "unit_instance_id_for_model"
            for function in functions
            for node in ast.walk(function)
        ), filename


def test_trigger_consumers_preserve_blocked_roots_through_the_shared_owner() -> None:
    for filename in (
        "attack_completion_triggers.py",
        "move_completion_triggers.py",
        "battle_shock_outcome_triggers.py",
        "model_destruction_triggers.py",
    ):
        tree = ast.parse((ENGINE / filename).read_text(encoding="utf-8"))
        release_guards = [
            node
            for node in ast.walk(tree)
            if isinstance(node, ast.If)
            and isinstance(node.test, ast.UnaryOp)
            and isinstance(node.test.op, ast.Not)
            and isinstance(node.test.operand, ast.Call)
            and isinstance(node.test.operand.func, ast.Name)
            and node.test.operand.func.id == "release_rule_trigger"
        ]
        assert len(release_guards) == 1, filename
        assert any(
            isinstance(node, ast.Return)
            and isinstance(node.value, ast.Call)
            and isinstance(node.value.func, ast.Name)
            and node.value.func.id == "unreleased_rule_trigger_status"
            for statement in release_guards[0].body
            for node in ast.walk(statement)
        ), filename


def test_marker_history_uses_the_mutation_boundary_instead_of_the_deferred_trigger() -> None:
    """A removal source event can precede actual mutation by a whole timing batch."""
    for filename in (
        "primary_mission_action_lifecycle_policy.py",
        "primary_mission_action_integrity.py",
        "primary_mission_sensor_integrity.py",
        "primary_mission_marker_integrity.py",
    ):
        tree = ast.parse((ENGINE / filename).read_text(encoding="utf-8"))
        assert not any(
            isinstance(node, ast.Call)
            and isinstance(node.func, ast.Attribute)
            and node.func.attr == "get"
            and any(
                isinstance(argument, ast.Attribute) and argument.attr == "removal_event_id"
                for argument in node.args
            )
            for node in ast.walk(tree)
        ), filename
        assert any(
            isinstance(node, ast.Call)
            and isinstance(node.func, ast.Name)
            and node.func.id == "primary_marker_removal_event_index"
            for node in ast.walk(tree)
        ), filename
