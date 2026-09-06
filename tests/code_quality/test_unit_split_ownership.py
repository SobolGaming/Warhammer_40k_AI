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


def test_enhancement_live_ownership_is_not_derived_from_roster_selection_locally() -> None:
    violations: list[str] = []
    for path in ENGINE.rglob("*.py"):
        if path.name == "enhancement_bearers.py":
            continue
        for node in ast.walk(ast.parse(path.read_text(encoding="utf-8"))):
            if isinstance(node, ast.JoinedStr):
                expression = ast.unparse(node)
                if (
                    "army.army_id" in expression
                    and "assignment.target_unit_selection_id" in expression
                    and sum(isinstance(value, ast.FormattedValue) for value in node.values) == 2
                ):
                    violations.append(f"{path.relative_to(ENGINE)}:{node.lineno}")
            if isinstance(node, ast.Compare):
                operands = (node.left, *node.comparators)
                if any(
                    isinstance(value, ast.Attribute) and value.attr == "bearer_unit_instance_id"
                    for value in operands
                ) and any(
                    isinstance(value, ast.Attribute) and value.attr == "unit_instance_id"
                    for value in operands
                ):
                    violations.append(f"{path.relative_to(ENGINE)}:{node.lineno}")
    assert not violations, "Enhancement live lookup bypasses authenticated ownership: " + repr(
        violations
    )


def test_generic_effect_target_gates_use_current_applications() -> None:
    path = ENGINE / "generic_rule_effect_targets.py"
    tree = ast.parse(path.read_text(encoding="utf-8"))
    violations = [
        node.lineno
        for node in ast.walk(tree)
        if isinstance(node, ast.Attribute) and node.attr == "target_unit_instance_ids"
    ]
    assert not violations, "Generic target gates recheck historical targets: " + repr(violations)
