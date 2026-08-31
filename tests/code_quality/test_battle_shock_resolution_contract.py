from __future__ import annotations

import ast
from dataclasses import dataclass
from enum import StrEnum
from pathlib import Path
from typing import cast

ROOT = Path(__file__).resolve().parents[2]
ENGINE_ROOT = ROOT / "src" / "warhammer40k_core" / "engine"

_SHARED_RESOLUTION_FUNCTIONS = frozenset(
    {
        "resolve_battle_shock_test_with_optional_reroll",
        "apply_battle_shock_reroll_resolution_decision",
        "record_battle_shock_result_and_outcome_events",
    }
)


class _Policy(StrEnum):
    BOTH_FIELDS = "both_fields"
    FORWARD_WHOLE_RESULT = "forward_whole_result"
    EXPLICIT_PARENT_PROOF = "explicit_parent_proof"


@dataclass(frozen=True, slots=True)
class _ExpectedCall:
    policy: _Policy
    proof: str = ""


_EXPECTED_CALLS = {
    (
        "battle_shock_test_service.py",
        "resolve_battle_shock_test",
        "resolve_battle_shock_test_with_optional_reroll",
    ): _ExpectedCall(_Policy.FORWARD_WHOLE_RESULT),
    (
        "battle_shock_test_service.py",
        "apply_stratagem_battle_shock_reroll_decision",
        "apply_battle_shock_reroll_resolution_decision",
    ): _ExpectedCall(
        _Policy.EXPLICIT_PARENT_PROOF,
        "A Stratagem Battle-shock occurrence has no sibling-effect parent; the outcome provider "
        "owns any queued request and lifecycle queue dispatch resumes globally.",
    ),
    (
        "catalog_selected_target_battle_shock.py",
        "resolve_selected_target_battle_shock_effect",
        "resolve_battle_shock_test_with_optional_reroll",
    ): _ExpectedCall(_Policy.FORWARD_WHOLE_RESULT),
    (
        "catalog_selected_target_battle_shock_reroll.py",
        "apply_catalog_selected_target_battle_shock_reroll_decision",
        "apply_battle_shock_reroll_resolution_decision",
    ): _ExpectedCall(_Policy.BOTH_FIELDS),
    (
        "unit_move_completed_hooks.py",
        "apply_unit_move_completed_battle_shock_reroll_decision",
        "apply_battle_shock_reroll_resolution_decision",
    ): _ExpectedCall(
        _Policy.EXPLICIT_PARENT_PROOF,
        "Move-completed Battle-shock processing is keyed by resolved event evidence; it has no "
        "later sibling effect, and provider requests re-enter through the event cursor.",
    ),
    (
        "unit_move_completed_hooks.py",
        "_resolve_battle_shock_effect",
        "resolve_battle_shock_test_with_optional_reroll",
    ): _ExpectedCall(_Policy.BOTH_FIELDS),
    (
        "phases/command.py",
        "apply_decision",
        "apply_battle_shock_reroll_resolution_decision",
    ): _ExpectedCall(
        _Policy.EXPLICIT_PARENT_PROOF,
        "The command-start source hook owns its ordered parent state and receives the nested "
        "result through apply_nested_result; provider requests remain the lifecycle queue head.",
    ),
    (
        "phases/command.py",
        "_resolve_battle_shock_step",
        "resolve_battle_shock_test_with_optional_reroll",
    ): _ExpectedCall(_Policy.BOTH_FIELDS),
    (
        "phases/command.py",
        "_resolve_battle_shock_step",
        "record_battle_shock_result_and_outcome_events",
    ): _ExpectedCall(_Policy.BOTH_FIELDS),
    (
        "phases/command_battle_shock_rerolls.py",
        "apply_battle_shock_reroll_decision",
        "apply_battle_shock_reroll_resolution_decision",
    ): _ExpectedCall(
        _Policy.EXPLICIT_PARENT_PROOF,
        "The Command step stores completion by Battle-shock request ID and has no sibling-effect "
        "remainder; provider requests are independently queue-owned.",
    ),
    (
        "phases/movement_options_dice.py",
        "_resolve_forced_desperate_escape_battle_shock",
        "resolve_battle_shock_test_with_optional_reroll",
    ): _ExpectedCall(_Policy.FORWARD_WHOLE_RESULT),
    (
        "phases/movement_resolution_flow.py",
        "_apply_desperate_escape_battle_shock_reroll_decision",
        "apply_battle_shock_reroll_resolution_decision",
    ): _ExpectedCall(_Policy.FORWARD_WHOLE_RESULT),
    (
        "phases/movement_resolution_flow.py",
        "_apply_forced_desperate_escape_battle_shock_reroll_decision",
        "apply_battle_shock_reroll_resolution_decision",
    ): _ExpectedCall(_Policy.FORWARD_WHOLE_RESULT),
}


def test_every_shared_battle_shock_resolution_caller_has_an_explicit_parent_policy() -> None:
    calls = _shared_resolution_calls()

    assert set(calls) == set(_EXPECTED_CALLS)
    for key, node in calls.items():
        expected = _EXPECTED_CALLS[key]
        function = _enclosing_function(node, calls.parents_by_node)
        assert function is not None
        if expected.policy is _Policy.BOTH_FIELDS:
            assigned_name = _assigned_name(node, calls.parents_by_node)
            assert assigned_name is not None, f"{key} must bind the typed resolution result"
            attributes = {
                child.attr
                for child in ast.walk(function)
                if isinstance(child, ast.Attribute)
                and isinstance(child.value, ast.Name)
                and child.value.id == assigned_name
            }
            assert {"resolved_payload", "pending_status"} <= attributes, (
                f"{key} must consume both BattleShockResolutionResult fields"
            )
        elif expected.policy is _Policy.FORWARD_WHOLE_RESULT:
            assert _whole_result_is_forwarded(node, calls.parents_by_node), (
                f"{key} must forward the complete BattleShockResolutionResult"
            )
        else:
            assert len(expected.proof) >= 80, f"{key} lacks a substantive no-local-parent proof"


class _CallInventory(dict[tuple[str, str, str], ast.Call]):
    parents_by_node: dict[ast.AST, ast.AST]


def _shared_resolution_calls() -> _CallInventory:
    inventory = _CallInventory()
    inventory.parents_by_node = {}
    for path in sorted(ENGINE_ROOT.rglob("*.py")):
        if path.name == "battle_shock_resolution.py":
            continue
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        parents = {
            child: parent for parent in ast.walk(tree) for child in ast.iter_child_nodes(parent)
        }
        inventory.parents_by_node.update(parents)
        for node in ast.walk(tree):
            if not isinstance(node, ast.Call):
                continue
            callee = _callee_name(node)
            if callee not in _SHARED_RESOLUTION_FUNCTIONS:
                continue
            function = _enclosing_function(node, parents)
            if function is None or function.name == callee:
                continue
            key = (path.relative_to(ENGINE_ROOT).as_posix(), function.name, callee)
            assert key not in inventory, f"Duplicate shared Battle-shock call policy key: {key}"
            inventory[key] = node
    return inventory


def _callee_name(node: ast.Call) -> str | None:
    if isinstance(node.func, ast.Name):
        return node.func.id
    if isinstance(node.func, ast.Attribute):
        return node.func.attr
    return None


def _enclosing_function(
    node: ast.AST,
    parents: dict[ast.AST, ast.AST],
) -> ast.FunctionDef | ast.AsyncFunctionDef | None:
    current: ast.AST | None = node
    while current is not None:
        if isinstance(current, ast.FunctionDef | ast.AsyncFunctionDef):
            return current
        current = parents.get(current)
    return None


def _assigned_name(node: ast.Call, parents: dict[ast.AST, ast.AST]) -> str | None:
    parent = parents.get(node)
    if not isinstance(parent, ast.Assign) or len(parent.targets) != 1:
        return None
    target = parent.targets[0]
    return target.id if isinstance(target, ast.Name) else None


def _whole_result_is_forwarded(node: ast.Call, parents: dict[ast.AST, ast.AST]) -> bool:
    parent = parents.get(node)
    if isinstance(parent, ast.Return):
        return True
    assigned_name = _assigned_name(node, parents)
    if assigned_name is None:
        return False
    function = _enclosing_function(node, parents)
    if function is None:
        return False
    return any(
        isinstance(child, ast.Name)
        and child.id == assigned_name
        and isinstance(parents.get(child), ast.keyword)
        and cast(ast.keyword, parents[child]).arg == "resolution"
        for child in ast.walk(function)
    )
