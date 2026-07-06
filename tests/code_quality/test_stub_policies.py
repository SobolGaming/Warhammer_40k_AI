from __future__ import annotations

import ast
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]

FORBIDDEN_STUB_CALLS = frozenset(("MagicMock", "Mock", "SimpleNamespace"))


def test_no_stubs_in_integration_tests() -> None:
    integration_dirs = [
        ROOT / "tests" / "integration",
        ROOT / "tests" / "replay",
    ]

    violations: list[str] = []

    for directory in integration_dirs:
        if not directory.exists():
            continue
        for path in sorted(directory.rglob("*.py")):
            tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
            for node in ast.walk(tree):
                if not isinstance(node, ast.Call):
                    continue
                call_name = _call_name(node.func)
                if call_name in FORBIDDEN_STUB_CALLS:
                    violations.append(f"{path.relative_to(ROOT)}:{node.lineno} uses {call_name}")

    assert not violations, "Integration/replay tests must use real fixtures:\n" + "\n".join(
        violations
    )


def test_stub_policy_ast_audit_detects_real_calls_not_substrings() -> None:
    tree = ast.parse(
        """
text = "SimpleNamespace("
value = SimpleNamespace()
mock = unittest.mock.Mock()
"""
    )

    calls = [
        _call_name(node.func)
        for node in ast.walk(tree)
        if isinstance(node, ast.Call) and _call_name(node.func) in FORBIDDEN_STUB_CALLS
    ]

    assert calls == ["SimpleNamespace", "Mock"]


def _call_name(node: ast.expr) -> str | None:
    if isinstance(node, ast.Name):
        return node.id
    if isinstance(node, ast.Attribute):
        return node.attr
    return None
