from __future__ import annotations

import ast
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
ENGINE_ROOT = ROOT / "src" / "warhammer40k_core" / "engine"
CATALOG_DATASHEET_RUNTIME = ENGINE_ROOT / "catalog_datasheet_rule_runtime.py"

RULE_NAME_NORMALIZER_NAMES = frozenset(
    {
        "_canonical_rule_token",
        "_normalise_rule_token",
        "_normalize_rule_token",
        "_normalize_pain_ability_name",
    }
)


def test_engine_runtime_does_not_split_pipe_delimited_descriptor_parameters() -> None:
    violations: list[str] = []

    for path, tree in _engine_trees():
        for node in ast.walk(tree):
            if not isinstance(node, ast.Call) or not _is_pipe_split_call(node):
                continue
            violations.append(f"{path.relative_to(ROOT).as_posix()}:{node.lineno}")

    assert not violations, (
        "Engine runtime must consume typed descriptor parameters, not split pipe strings:\n"
        + "\n".join(violations)
    )


def test_engine_runtime_does_not_reintroduce_rule_name_normalizers() -> None:
    violations: list[str] = []

    for path, tree in _engine_trees():
        for node in ast.walk(tree):
            if isinstance(node, ast.FunctionDef) and node.name in RULE_NAME_NORMALIZER_NAMES:
                violations.append(f"{path.relative_to(ROOT).as_posix()}:{node.lineno}")
                continue
            if isinstance(node, ast.Call) and _call_name(node) in RULE_NAME_NORMALIZER_NAMES:
                violations.append(f"{path.relative_to(ROOT).as_posix()}:{node.lineno}")

    assert not violations, (
        "Engine runtime must gate behavior by source IDs, descriptor IDs, or catalog tokens; "
        "rule-name normalizers are forbidden:\n" + "\n".join(violations)
    )


def test_engine_runtime_does_not_compare_ability_display_names() -> None:
    violations: list[str] = []

    for path, tree in _engine_trees():
        for node in ast.walk(tree):
            if not isinstance(node, ast.Compare):
                continue
            if not _contains_loop_ability_name(node):
                continue
            violations.append(f"{path.relative_to(ROOT).as_posix()}:{node.lineno}")

    assert not violations, (
        "Engine runtime must not gate behavior on DatasheetAbilityDescriptor.name:\n"
        + "\n".join(violations)
    )


def test_catalog_datasheet_runtime_does_not_renormalize_keyword_tokens() -> None:
    tree = ast.parse(
        CATALOG_DATASHEET_RUNTIME.read_text(encoding="utf-8"),
        filename=str(CATALOG_DATASHEET_RUNTIME),
    )

    assert not any(
        isinstance(node, ast.FunctionDef) and node.name == "_canonical_keyword"
        for node in ast.walk(tree)
    ), "Catalog runtime must compare canonical catalog keyword tokens directly."


def _engine_trees() -> tuple[tuple[Path, ast.Module], ...]:
    return tuple(
        (path, ast.parse(path.read_text(encoding="utf-8"), filename=str(path)))
        for path in sorted(ENGINE_ROOT.rglob("*.py"))
    )


def _is_pipe_split_call(node: ast.Call) -> bool:
    return (
        isinstance(node.func, ast.Attribute)
        and node.func.attr == "split"
        and len(node.args) == 1
        and isinstance(node.args[0], ast.Constant)
        and node.args[0].value == "|"
    )


def _call_name(node: ast.Call) -> str | None:
    if isinstance(node.func, ast.Name):
        return node.func.id
    if isinstance(node.func, ast.Attribute):
        return node.func.attr
    return None


def _contains_loop_ability_name(node: ast.AST) -> bool:
    return any(
        isinstance(child, ast.Attribute)
        and child.attr == "name"
        and isinstance(child.value, ast.Name)
        and child.value.id == "ability"
        for child in ast.walk(node)
    )
