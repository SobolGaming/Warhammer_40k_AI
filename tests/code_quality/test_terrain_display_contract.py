from __future__ import annotations

import ast
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SRC_ROOT = ROOT / "src" / "warhammer40k_core"
SOURCE_ID_STRING_PARSE_METHODS = frozenset(
    (
        "partition",
        "removeprefix",
        "removesuffix",
        "rpartition",
        "split",
    )
)


def test_terrain_display_contract_forbids_source_id_string_parsing() -> None:
    violations: list[str] = []
    for path in sorted(SRC_ROOT.rglob("*.py")):
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        for node in ast.walk(tree):
            if not isinstance(node, ast.Call):
                continue
            function = node.func
            if not isinstance(function, ast.Attribute):
                continue
            if function.attr not in SOURCE_ID_STRING_PARSE_METHODS:
                continue
            if _is_source_id_expression(function.value):
                violations.append(
                    f"{path.relative_to(ROOT)}:{node.lineno} parses source_id with {function.attr}"
                )

    assert not violations, (
        "Terrain display geometry must be first-class structured data; "
        "production code must not parse source_id strings for rendering details:\n"
        + "\n".join(violations)
    )


def _is_source_id_expression(node: ast.expr) -> bool:
    if isinstance(node, ast.Name):
        return node.id == "source_id"
    if isinstance(node, ast.Attribute):
        return node.attr == "source_id"
    if isinstance(node, ast.Subscript):
        return _is_source_id_key(node.slice)
    return False


def _is_source_id_key(node: ast.expr) -> bool:
    if isinstance(node, ast.Constant):
        return node.value == "source_id"
    return False
