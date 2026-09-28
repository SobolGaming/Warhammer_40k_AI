"""Keep source operation inventories at modifier-choice consumer boundaries."""

import ast
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
ENGINE = ROOT / "src/warhammer40k_core/engine"


def test_attack_consumers_do_not_use_lossy_scalar_modifier_apis() -> None:
    scalar_queries = {
        "wound_roll_modifier",
        "damage_roll_modifier",
        "allocated_attack_damage_modifier",
    }
    violations: list[str] = []
    for path in sorted(ENGINE.glob("attack_*.py")):
        tree = ast.parse(path.read_text())
        for node in ast.walk(tree):
            if (
                isinstance(node, ast.Call)
                and isinstance(node.func, ast.Attribute)
                and node.func.attr in scalar_queries
            ):
                violations.append(f"{path.name}:{node.lineno}: {node.func.attr}")
    assert not violations, "Modifier choices require individual operations: " + ", ".join(
        violations
    )


def test_general_modifier_options_do_not_enumerate_power_sets() -> None:
    path = ENGINE / "modifier_evaluation.py"
    tree = ast.parse(path.read_text())
    combinator_names = {"combinations", "combinations_with_replacement", "product", "powerset"}
    offenders = [
        node.lineno
        for node in ast.walk(tree)
        if isinstance(node, ast.Call)
        and (
            (isinstance(node.func, ast.Name) and node.func.id in combinator_names)
            or (isinstance(node.func, ast.Attribute) and node.func.attr in combinator_names)
        )
    ]
    assert not offenders, f"Subset choices must keep bounded option width, lines: {offenders}"


def test_attack_permission_consumers_supply_occurrence_context() -> None:
    for name in (
        "attack_modifier_evaluation.py",
        "attack_save_modifier_selection.py",
        "attack_damage_modifier_selection.py",
    ):
        calls = [
            node
            for node in ast.walk(ast.parse((ENGINE / name).read_text()))
            if isinstance(node, ast.Call)
            and isinstance(node.func, ast.Name)
            and node.func.id == "select_modifiers"
        ]
        assert calls, name
        assert all("attack_context" in {key.arg for key in call.keywords} for call in calls), name
    for name in ("modifier_evaluation.py", "modifier_evaluation_dispatch.py"):
        calls = [
            node
            for node in ast.walk(ast.parse((ENGINE / name).read_text()))
            if isinstance(node, ast.Call)
            and isinstance(node.func, ast.Name)
            and node.func.id == "modifier_ignore_permissions_for_subject"
        ]
        assert len(calls) == 1, name
        assert "attack_context" in {key.arg for key in calls[0].keywords}, name


def test_nonattack_selection_owners_do_not_collapse_profile_or_catalog_operations() -> None:
    scalar_queries = {
        "resolved_profile_characteristic",
        "catalog_leadership_characteristic_for_unit",
    }
    violations: list[str] = []
    for name in ("nonattack_modifier_evaluation.py", "objective_control_modifier_evaluation.py"):
        tree = ast.parse((ENGINE / name).read_text())
        for node in ast.walk(tree):
            if not isinstance(node, ast.Call):
                continue
            called = (
                node.func.id
                if isinstance(node.func, ast.Name)
                else node.func.attr
                if isinstance(node.func, ast.Attribute)
                else None
            )
            if called in scalar_queries:
                violations.append(f"{name}:{node.lineno}: {called}")
    assert not violations, "Nonattack choices require original source operations: " + ", ".join(
        violations
    )
