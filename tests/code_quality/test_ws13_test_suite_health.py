from __future__ import annotations

import ast
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
TEST_ROOTS = (
    ROOT / "tests" / "unit",
    ROOT / "tests" / "integration",
    ROOT / "tests" / "replay",
    ROOT / "tests" / "code_quality",
)


def test_tests_do_not_replace_lifecycle_decision_controller() -> None:
    violations: list[str] = []

    for path in _test_paths():
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        for node in ast.walk(tree):
            target_nodes = _assignment_targets(node)
            for target in target_nodes:
                if isinstance(target, ast.Attribute) and target.attr == "decision_controller":
                    violations.append(
                        f"{path.relative_to(ROOT)}:{target.lineno} assigns decision_controller"
                    )

    assert not violations, (
        "Tests must not replace lifecycle.decision_controller directly:\n" + "\n".join(violations)
    )


def test_tests_do_not_import_from_other_test_modules() -> None:
    violations: list[str] = []

    for path in _test_paths():
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        for node in ast.walk(tree):
            if not isinstance(node, ast.ImportFrom):
                continue
            if node.module is None:
                continue
            if _module_path_contains_test_module(node.module):
                violations.append(f"{path.relative_to(ROOT)}:{node.lineno} imports {node.module}")

    assert not violations, (
        "Shared test setup must live in named helper modules, not imported test modules:\n"
        + "\n".join(violations)
    )


def test_ws13_audits_detect_assignment_and_test_module_imports() -> None:
    tree = ast.parse(
        """
from tests.unit.test_example import _helper

def test_bad(lifecycle):
    lifecycle.decision_controller = object()
"""
    )

    assignment_targets = [
        target
        for node in ast.walk(tree)
        for target in _assignment_targets(node)
        if isinstance(target, ast.Attribute) and target.attr == "decision_controller"
    ]
    import_modules = [
        node.module
        for node in ast.walk(tree)
        if isinstance(node, ast.ImportFrom)
        and node.module is not None
        and _module_path_contains_test_module(node.module)
    ]

    assert len(assignment_targets) == 1
    assert import_modules == ["tests.unit.test_example"]


def _test_paths() -> tuple[Path, ...]:
    paths: list[Path] = []
    for root in TEST_ROOTS:
        paths.extend(path for path in root.rglob("test_*.py") if path.is_file())
    return tuple(sorted(paths))


def _assignment_targets(node: ast.AST) -> tuple[ast.expr, ...]:
    if isinstance(node, ast.Assign):
        return tuple(node.targets)
    if isinstance(node, ast.AnnAssign):
        return (node.target,)
    if isinstance(node, ast.AugAssign):
        return (node.target,)
    return ()


def _module_path_contains_test_module(module: str) -> bool:
    return any(part.startswith("test_") for part in module.split("."))
