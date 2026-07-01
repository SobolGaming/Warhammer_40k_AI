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
SESSION_PRODUCER_PATHS = (
    ROOT / "src" / "warhammer40k_core" / "interfaces" / "cli.py",
    ROOT / "src" / "warhammer40k_core" / "adapters" / "ui.py",
    ROOT / "src" / "warhammer40k_core" / "adapters" / "network.py",
    ROOT / "src" / "warhammer40k_core" / "adapters" / "headless.py",
    ROOT / "src" / "warhammer40k_core" / "adapters" / "replay.py",
)
SESSION_PROTOCOL_PATH = ROOT / "src" / "warhammer40k_core" / "adapters" / "contracts.py"

ADAPTER_FACING_NAMES = frozenset(
    (
        "AdapterGameSession",
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
SESSION_PROTOCOL_METHODS = frozenset(
    (
        "advance_until_decision_or_terminal",
        "events_since",
        "replay_artifact",
        "rules_catalog_view",
        "start",
        "submit_option",
        "submit_parameterized_payload",
        "support_profile",
        "view",
    )
)
SESSION_PRODUCER_FORBIDDEN_NAMES = frozenset(("GameLifecycle",))
SESSION_PRODUCER_FORBIDDEN_IMPORT_MODULES = frozenset(("warhammer40k_core.engine.lifecycle",))
SESSION_PRODUCER_FORBIDDEN_IMPORT_NAMES = frozenset(("GameLifecycle",))
SESSION_PRODUCER_FORBIDDEN_ATTRIBUTES = frozenset(
    (
        "decision_controller",
        "lifecycle",
        "submit_decision",
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


def test_shared_adapter_session_protocol_exposes_required_facade_methods() -> None:
    tree = ast.parse(SESSION_PROTOCOL_PATH.read_text(encoding="utf-8"))
    protocol_node = _class_node(tree=tree, class_name="AdapterGameSession")
    method_names = {node.name for node in protocol_node.body if isinstance(node, ast.FunctionDef)}

    assert method_names == SESSION_PROTOCOL_METHODS


def test_thin_adapter_producers_use_session_protocol_not_lifecycle_bypass() -> None:
    violations: list[str] = []

    for path in SESSION_PRODUCER_PATHS:
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        violations.extend(_session_producer_bypass_violations(path=path, tree=tree))

    assert not violations, (
        "Thin adapter producers must depend on AdapterGameSession and must not bypass "
        "the shared session facade:\n" + "\n".join(violations)
    )


def test_thin_adapter_producer_audit_catches_import_and_lifecycle_attribute_bypass() -> None:
    tree = ast.parse(
        """
import warhammer40k_core.engine.lifecycle
from warhammer40k_core.engine.lifecycle import GameLifecycle

def bypass(session: object) -> None:
    session.lifecycle.config
    session.lifecycle.advance_until_decision_or_terminal()
    session.lifecycle._pending_decision_request()
    session.decision_controller
    session.submit_decision(None)
"""
    )

    violations = _session_producer_bypass_violations(
        path=ROOT / "src" / "warhammer40k_core" / "adapters" / "bad_producer.py",
        tree=tree,
    )

    assert len(violations) == 8
    assert any("warhammer40k_core.engine.lifecycle" in violation for violation in violations)
    assert any("GameLifecycle" in violation for violation in violations)
    assert sum("lifecycle" in violation for violation in violations) == 5
    assert any("decision_controller" in violation for violation in violations)
    assert any("submit_decision" in violation for violation in violations)


def _test_paths() -> tuple[Path, ...]:
    paths: list[Path] = []
    for root in TEST_ROOTS:
        paths.extend(path for path in root.rglob("test_*.py") if path.is_file())
    return tuple(sorted(paths))


def _class_node(*, tree: ast.Module, class_name: str) -> ast.ClassDef:
    for node in tree.body:
        if isinstance(node, ast.ClassDef) and node.name == class_name:
            return node
    raise AssertionError(f"Expected class {class_name}.")


def _session_producer_bypass_violations(*, path: Path, tree: ast.Module) -> list[str]:
    violations: list[str] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom):
            if node.module in SESSION_PRODUCER_FORBIDDEN_IMPORT_MODULES:
                violations.append(
                    _format_violation(
                        path=path,
                        line_number=node.lineno,
                        call_name=node.module,
                    )
                )
            for alias in node.names:
                if alias.name in SESSION_PRODUCER_FORBIDDEN_IMPORT_NAMES:
                    violations.append(
                        _format_violation(
                            path=path,
                            line_number=node.lineno,
                            call_name=alias.name,
                        )
                    )
        if isinstance(node, ast.Import):
            for alias in node.names:
                if alias.name in SESSION_PRODUCER_FORBIDDEN_IMPORT_MODULES:
                    violations.append(
                        _format_violation(
                            path=path,
                            line_number=node.lineno,
                            call_name=alias.name,
                        )
                    )
        if isinstance(node, ast.Name) and node.id in SESSION_PRODUCER_FORBIDDEN_NAMES:
            violations.append(
                _format_violation(path=path, line_number=node.lineno, call_name=node.id)
            )
        if isinstance(node, ast.Attribute) and node.attr in SESSION_PRODUCER_FORBIDDEN_ATTRIBUTES:
            violations.append(
                _format_violation(path=path, line_number=node.lineno, call_name=node.attr)
            )
    return violations


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
            violations.append(
                _format_violation(path=path, line_number=child.lineno, call_name=function.attr)
            )
        if (
            isinstance(function, ast.Attribute)
            and function.attr in FORBIDDEN_QUEUE_MUTATION_METHODS
        ):
            violations.append(
                _format_violation(path=path, line_number=child.lineno, call_name=function.attr)
            )
        if (
            isinstance(function, ast.Attribute)
            and function.attr in FORBIDDEN_QUEUE_ATTRIBUTE_MUTATION_METHODS
            and _is_pending_queue_expression(function.value)
        ):
            violations.append(
                _format_violation(path=path, line_number=child.lineno, call_name=function.attr)
            )
        if isinstance(function, ast.Name) and function.id in FORBIDDEN_BYPASS_HELPERS:
            violations.append(
                _format_violation(path=path, line_number=child.lineno, call_name=function.id)
            )
    return violations


def _is_pending_queue_expression(node: ast.expr) -> bool:
    if isinstance(node, ast.Name):
        return node.id in {"pending_requests", "queue"}
    if isinstance(node, ast.Attribute):
        return node.attr in {"_pending_requests", "pending_requests", "queue"} or (
            _is_pending_queue_expression(node.value)
        )
    return False


def _format_violation(*, path: Path, line_number: int, call_name: str) -> str:
    return f"{path.relative_to(ROOT)}:{line_number} uses {call_name}"
