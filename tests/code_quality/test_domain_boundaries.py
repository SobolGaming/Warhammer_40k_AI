from __future__ import annotations

import ast
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
MODIFIERS = ROOT / "src" / "warhammer40k_core" / "core" / "modifiers.py"


def test_modifiers_do_not_import_attribute_identifier_validators() -> None:
    tree = ast.parse(MODIFIERS.read_text(encoding="utf-8"), filename=str(MODIFIERS))
    forbidden = {"validate_identifier", "validate_optional_identifier"}
    violations: list[str] = []

    for node in ast.walk(tree):
        if not isinstance(node, ast.ImportFrom):
            continue
        if node.module != "warhammer40k_core.core.attributes":
            continue
        for alias in node.names:
            if alias.name in forbidden:
                violations.append(alias.name)

    assert not violations, "Modifiers must use modifier-domain identifier validators."
