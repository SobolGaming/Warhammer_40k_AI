from __future__ import annotations

import ast
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
ENGINE = ROOT / "src" / "warhammer40k_core" / "engine"
SOURCE = ROOT / "src" / "warhammer40k_core"
_DAMAGED_DESCRIPTION_BOUNDARY_FILES = {
    "src/warhammer40k_core/rules/wahapedia_bridge.py",
    "src/warhammer40k_core/rules/wahapedia_bridge_columns.py",
    "src/warhammer40k_core/rules/wahapedia_schema.py",
}

_FORBIDDEN_IMPORT_MODULES = {
    "warhammer40k_core.rules.html_sanitizer",
    "warhammer40k_core.rules.text_normalization",
    "warhammer40k_core.rules.source_data",
    "warhammer40k_core.rules.source_overlay",
    "warhammer40k_core.rules.source_patch",
    "warhammer40k_core.rules.source_reference_generation",
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


def test_damaged_descriptions_are_normalized_only_at_source_boundary() -> None:
    violations: list[str] = []

    for path in sorted(SOURCE.rglob("*.py")):
        rel = path.relative_to(ROOT).as_posix()
        if rel in _DAMAGED_DESCRIPTION_BOUNDARY_FILES:
            continue
        if "damaged_description" in path.read_text(encoding="utf-8"):
            violations.append(rel)

    assert not violations, (
        "DAMAGED raw text must become structured descriptors at the source boundary:\n"
        + "\n".join(violations)
    )


def test_damaged_bridge_parser_uses_normalized_punctuation() -> None:
    source = (SOURCE / "rules" / "wahapedia_bridge.py").read_text(encoding="utf-8")
    forbidden_fragments = (
        "RIGHT SINGLE QUOTATION MARK",
        "LEFT SINGLE QUOTATION MARK",
        "EN DASH",
        "EM DASH",
        "\\u2018",
        "\\u2019",
        "\\u2013",
        "\\u2014",
    )

    violations = [fragment for fragment in forbidden_fragments if fragment in source]

    assert not violations, (
        "DAMAGED bridge parsing must consume SourceTextField.normalized_text; "
        "smart punctuation belongs in source normalization:\n" + "\n".join(violations)
    )
