from __future__ import annotations

import ast
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
TEST_ROOTS = (
    ROOT / "tests" / "unit",
    ROOT / "tests" / "integration",
    ROOT / "tests" / "replay",
)
ADAPTER_HELPER_PATHS = (ROOT / "tests" / "deployment_submission_helpers.py",)

ADAPTER_FACING_NAMES = frozenset(
    (
        "EventStreamCursor",
        "FiniteOptionSubmission",
        "LocalGameSession",
        "ParameterizedSubmission",
        "project_game_view",
        "result_for_option",
        "result_for_parameterized_payload",
        "submit_option",
        "submit_parameterized_payload",
    )
)
ADAPTER_FACING_METHODS = frozenset(
    (
        "events_since",
        "submit_option",
        "submit_parameterized_payload",
        "view",
    )
)
FORBIDDEN_BYPASS_METHODS = frozenset(
    (
        "apply_decision",
        "submit_result",
    )
)
FORBIDDEN_QUEUE_MUTATION_METHODS = frozenset(
    (
        "pop_next",
        "remove_by_id",
    )
)
FORBIDDEN_QUEUE_ATTRIBUTE_MUTATION_METHODS = frozenset(
    (
        "append",
        "clear",
        "extend",
        "insert",
        "pop",
        "remove",
    )
)
FORBIDDEN_BYPASS_HELPERS = frozenset(
    (
        "_submit_handler_decision",
        "_submit_parameterized_handler_payload",
    )
)
FORBIDDEN_PARAMETERIZED_HELPER_TOKENS = frozenset(
    (
        "PARAMETERIZED_DECISION_OPTION_ID",
        "DecisionResult(",
    )
)


def test_adapter_facing_tests_submit_choices_through_lifecycle() -> None:
    violations: list[str] = []

    for path in _test_paths():
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        for node in tree.body:
            if not isinstance(node, ast.FunctionDef):
                continue
            if not node.name.startswith("test_"):
                continue
            if not _is_adapter_facing_test(node):
                continue
            violations.extend(_decision_bypass_violations(path=path, node=node))

    assert not violations, (
        "Adapter-facing tests must submit player choices through "
        "GameLifecycle.submit_decision(...):\n" + "\n".join(violations)
    )


def test_adapter_submission_helpers_do_not_construct_parameterized_results_directly() -> None:
    violations: list[str] = []

    for path in ADAPTER_HELPER_PATHS:
        text = path.read_text(encoding="utf-8")
        for token in FORBIDDEN_PARAMETERIZED_HELPER_TOKENS:
            if token in text:
                violations.append(f"{path.relative_to(ROOT)} contains {token}")

    assert not violations, (
        "Adapter submission helpers must use generic submission helpers instead of "
        "constructing parameterized DecisionResult values directly:\n" + "\n".join(violations)
    )


def _test_paths() -> tuple[Path, ...]:
    paths: list[Path] = []
    for root in TEST_ROOTS:
        paths.extend(path for path in root.rglob("test_*.py") if path.is_file())
    return tuple(sorted(paths))


def _is_adapter_facing_test(node: ast.FunctionDef) -> bool:
    for child in ast.walk(node):
        if isinstance(child, ast.Name) and child.id in ADAPTER_FACING_NAMES:
            return True
        if isinstance(child, ast.Attribute) and child.attr in ADAPTER_FACING_METHODS:
            return True
    return False


def _decision_bypass_violations(*, path: Path, node: ast.FunctionDef) -> list[str]:
    violations: list[str] = []
    for child in ast.walk(node):
        if not isinstance(child, ast.Call):
            continue
        function = child.func
        if isinstance(function, ast.Attribute) and function.attr in FORBIDDEN_BYPASS_METHODS:
            violations.append(_format_violation(path=path, node=child, call_name=function.attr))
        if (
            isinstance(function, ast.Attribute)
            and function.attr in FORBIDDEN_QUEUE_MUTATION_METHODS
        ):
            violations.append(_format_violation(path=path, node=child, call_name=function.attr))
        if (
            isinstance(function, ast.Attribute)
            and function.attr in FORBIDDEN_QUEUE_ATTRIBUTE_MUTATION_METHODS
            and _is_pending_queue_expression(function.value)
        ):
            violations.append(_format_violation(path=path, node=child, call_name=function.attr))
        if isinstance(function, ast.Name) and function.id in FORBIDDEN_BYPASS_HELPERS:
            violations.append(_format_violation(path=path, node=child, call_name=function.id))
    return violations


def _is_pending_queue_expression(node: ast.expr) -> bool:
    if isinstance(node, ast.Name):
        return node.id in {"pending_requests", "queue"}
    if isinstance(node, ast.Attribute):
        return node.attr in {"_pending_requests", "pending_requests", "queue"} or (
            _is_pending_queue_expression(node.value)
        )
    return False


def _format_violation(*, path: Path, node: ast.Call, call_name: str) -> str:
    return f"{path.relative_to(ROOT)}:{node.lineno} calls {call_name}"
