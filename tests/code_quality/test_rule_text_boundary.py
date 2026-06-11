from __future__ import annotations

import ast
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
ENGINE = ROOT / "src" / "warhammer40k_core" / "engine"

_FORBIDDEN_IMPORT_MODULES = {
    "warhammer40k_core.rules.html_sanitizer",
    "warhammer40k_core.rules.text_normalization",
    "warhammer40k_core.rules.source_data",
    "warhammer40k_core.rules.source_patch",
    "warhammer40k_core.rules.wahapedia_schema",
}
_FORBIDDEN_IMPORT_NAMES = {
    "NormalizedRuleText",
    "RuleSourceText",
    "WahapediaJsonArtifact",
    "normalize_rule_text",
    "parse_normalized_tokens",
}
_FORBIDDEN_CALL_NAMES = {"normalize_rule_text", "parse_normalized_tokens"}
_FORBIDDEN_FROM_RAW_TYPES = {"NormalizedRuleText", "RuleSourceText"}


def test_engine_modules_do_not_normalize_raw_rule_text() -> None:
    violations: list[str] = []

    for path in sorted(ENGINE.rglob("*.py")):
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        rel = path.relative_to(ROOT).as_posix()
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                for alias in node.names:
                    if alias.name in _FORBIDDEN_IMPORT_MODULES:
                        violations.append(f"{rel}:{node.lineno}:import {alias.name}")
                continue

            if isinstance(node, ast.ImportFrom):
                if node.module in _FORBIDDEN_IMPORT_MODULES:
                    violations.append(f"{rel}:{node.lineno}:from {node.module}")
                    continue
                for alias in node.names:
                    if alias.name in _FORBIDDEN_IMPORT_NAMES:
                        violations.append(f"{rel}:{node.lineno}:import {alias.name}")
                continue

            if not isinstance(node, ast.Call):
                continue
            if isinstance(node.func, ast.Name) and node.func.id in _FORBIDDEN_CALL_NAMES:
                violations.append(f"{rel}:{node.lineno}:{node.func.id}()")
                continue
            if not isinstance(node.func, ast.Attribute):
                continue
            if node.func.attr in _FORBIDDEN_CALL_NAMES:
                violations.append(f"{rel}:{node.lineno}:{node.func.attr}()")
                continue
            if node.func.attr != "from_raw":
                continue
            if (
                isinstance(node.func.value, ast.Name)
                and node.func.value.id in _FORBIDDEN_FROM_RAW_TYPES
            ):
                violations.append(f"{rel}:{node.lineno}:{node.func.value.id}.from_raw()")

    assert not violations, "Engine runtime must consume normalized rule descriptors:\n" + "\n".join(
        violations
    )
