from __future__ import annotations

import ast
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
TEST_ROOT = ROOT / "tests"


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
        violations.extend(_test_module_import_violations(path=path, tree=tree))

    assert not violations, (
        "Shared test setup must live in named helper modules, not imported test modules:\n"
        + "\n".join(violations)
    )


def test_ws13_audits_detect_assignment_and_test_module_imports() -> None:
    tree = ast.parse(
        """
from tests.unit.test_example import _helper
import tests.unit.test_example as example

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
    import_modules = _test_module_import_modules(tree)

    assert len(assignment_targets) == 1
    assert import_modules == ["tests.unit.test_example", "tests.unit.test_example"]


def _test_paths() -> tuple[Path, ...]:
    return tuple(sorted(path for path in TEST_ROOT.rglob("*.py") if path.is_file()))


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


def _test_module_import_violations(*, path: Path, tree: ast.AST) -> list[str]:
    return [
        f"{path.relative_to(ROOT)}:{lineno} imports {module}"
        for module, lineno in _test_module_imports(tree)
    ]


def _test_module_import_modules(tree: ast.AST) -> list[str]:
    return [module for module, _lineno in _test_module_imports(tree)]


def _test_module_imports(tree: ast.AST) -> list[tuple[str, int]]:
    imports: list[tuple[str, int]] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom):
            if node.module is not None and _module_path_contains_test_module(node.module):
                imports.append((node.module, node.lineno))
            continue
        if isinstance(node, ast.Import):
            imports.extend(
                (alias.name, node.lineno)
                for alias in node.names
                if _module_path_contains_test_module(alias.name)
            )
    return imports
