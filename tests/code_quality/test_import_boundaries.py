from __future__ import annotations

import ast
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SRC = ROOT / "src" / "warhammer40k_core"


def _imports(path: Path) -> list[str]:
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    found: list[str] = []

    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            found.extend(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            found.append(node.module)

    return found


def test_engine_does_not_import_adapters() -> None:
    engine = SRC / "engine"
    if not engine.exists():
        return

    violations: list[str] = []
    for path in sorted(engine.rglob("*.py")):
        for module in _imports(path):
            if module.startswith("warhammer40k_core.adapters"):
                violations.append(f"{path.relative_to(ROOT)} imports {module}")

    assert not violations, "Engine must not import adapters:\n" + "\n".join(violations)


def test_core_does_not_import_engine_or_adapters() -> None:
    core = SRC / "core"
    if not core.exists():
        return

    violations: list[str] = []
    forbidden = (
        "warhammer40k_core.engine",
        "warhammer40k_core.adapters",
        "warhammer40k_core.geometry",
        "warhammer40k_core.rules",
    )

    for path in sorted(core.rglob("*.py")):
        for module in _imports(path):
            if module.startswith(forbidden):
                violations.append(f"{path.relative_to(ROOT)} imports {module}")

    assert not violations, "Core import boundary violations:\n" + "\n".join(violations)
