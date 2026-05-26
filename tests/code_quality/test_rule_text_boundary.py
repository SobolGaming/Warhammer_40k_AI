from __future__ import annotations

import ast
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
ENGINE = ROOT / "src" / "warhammer40k_core" / "engine"

_FORBIDDEN_STRING_NORMALIZERS = {"lower", "casefold", "replace"}


def test_engine_modules_do_not_normalize_raw_rule_text() -> None:
    violations: list[str] = []

    for path in sorted(ENGINE.rglob("*.py")):
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        rel = path.relative_to(ROOT).as_posix()
        for node in ast.walk(tree):
            if not isinstance(node, ast.Call):
                continue
            if not isinstance(node.func, ast.Attribute):
                continue
            if node.func.attr in _FORBIDDEN_STRING_NORMALIZERS:
                violations.append(f"{rel}:{node.lineno}:{node.func.attr}")

    assert not violations, "Engine runtime must consume normalized rule descriptors:\n" + "\n".join(
        violations
    )
