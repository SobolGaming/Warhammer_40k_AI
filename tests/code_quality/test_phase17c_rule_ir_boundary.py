from __future__ import annotations

import ast
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
ENGINE = ROOT / "src" / "warhammer40k_core" / "engine"
PHASE17C_TOOLING_MODULES = {
    "warhammer40k_core.rules.rule_compiler",
    "warhammer40k_core.rules.rule_parser",
    "warhammer40k_core.rules.rule_templates",
}
PHASE17C_TOOLING_NAMES = {
    "compile_normalized_rule_text",
    "compile_rule_source_text",
    "compile_rule_source_texts",
    "parse_rule_ir",
}
LLM_OR_NETWORK_MODULE_PREFIXES = ("anthropic", "httpx", "openai", "requests")
RULE_TOOLING = ROOT / "src" / "warhammer40k_core" / "rules"


def test_engine_runtime_does_not_import_phase17c_rule_language_tooling() -> None:
    violations: list[str] = []
    for path in sorted(ENGINE.rglob("*.py")):
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        rel = path.relative_to(ROOT).as_posix()
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                for alias in node.names:
                    if alias.name in PHASE17C_TOOLING_MODULES:
                        violations.append(f"{rel}:{node.lineno}:import {alias.name}")
                continue
            if isinstance(node, ast.ImportFrom):
                if node.module in PHASE17C_TOOLING_MODULES:
                    violations.append(f"{rel}:{node.lineno}:from {node.module}")
                    continue
                for alias in node.names:
                    if alias.name in PHASE17C_TOOLING_NAMES:
                        violations.append(f"{rel}:{node.lineno}:import {alias.name}")
                continue
            if isinstance(node, ast.Call):
                if isinstance(node.func, ast.Name) and node.func.id in PHASE17C_TOOLING_NAMES:
                    violations.append(f"{rel}:{node.lineno}:{node.func.id}()")
                if (
                    isinstance(node.func, ast.Attribute)
                    and node.func.attr in PHASE17C_TOOLING_NAMES
                ):
                    violations.append(f"{rel}:{node.lineno}:{node.func.attr}()")

    assert not violations, "Engine runtime must not parse or compile raw rule text:\n" + "\n".join(
        violations
    )


def test_phase17c_rule_language_tooling_has_no_llm_or_network_imports() -> None:
    violations: list[str] = []
    for path in (
        RULE_TOOLING / "rule_compiler.py",
        RULE_TOOLING / "rule_ir.py",
        RULE_TOOLING / "rule_parser.py",
        RULE_TOOLING / "rule_templates.py",
    ):
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        rel = path.relative_to(ROOT).as_posix()
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                for alias in node.names:
                    if alias.name.startswith(LLM_OR_NETWORK_MODULE_PREFIXES):
                        violations.append(f"{rel}:{node.lineno}:import {alias.name}")
            elif (
                isinstance(node, ast.ImportFrom)
                and node.module is not None
                and node.module.startswith(LLM_OR_NETWORK_MODULE_PREFIXES)
            ):
                violations.append(f"{rel}:{node.lineno}:from {node.module}")

    assert not violations, (
        "Phase 17C parser/compiler must stay deterministic tooling:\n" + "\n".join(violations)
    )


def test_phase17c_rule_parser_keyword_sequence_lexicon_is_injected() -> None:
    path = RULE_TOOLING / "rule_parser.py"
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    hardcoded_keyword_literals: list[str] = []
    source_package_imports: list[str] = []
    parse_rule_ir_requires_keyword_lexicon = False

    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                if alias.name.startswith("warhammer40k_core.rules.source_packages"):
                    source_package_imports.append(
                        f"{path.relative_to(ROOT).as_posix()}:{node.lineno}:import {alias.name}"
                    )
            continue
        if (
            isinstance(node, ast.ImportFrom)
            and node.module is not None
            and node.module.startswith("warhammer40k_core.rules.source_packages")
        ):
            source_package_imports.append(
                f"{path.relative_to(ROOT).as_posix()}:{node.lineno}:from {node.module}"
            )
            continue
        if isinstance(node, ast.Constant) and node.value in {
            "KHORNE",
            "LEGIONES DAEMONICA",
            "WORLD EATERS",
        }:
            hardcoded_keyword_literals.append(f"{path.relative_to(ROOT).as_posix()}:{node.lineno}")
            continue

        if not isinstance(node, ast.FunctionDef) or node.name != "parse_rule_ir":
            continue
        parse_rule_ir_requires_keyword_lexicon = any(
            argument.arg == "source_keyword_sequence_parts" for argument in node.args.kwonlyargs
        )

    assert parse_rule_ir_requires_keyword_lexicon
    assert not source_package_imports, (
        "Generic rule parser must receive source keyword lexicons from edition-aware "
        "compile/build entrypoints instead of importing source packages:\n"
        + "\n".join(source_package_imports)
    )
    assert not hardcoded_keyword_literals, (
        "Parser keyword sequences must come from injected generated source-package lexicons:\n"
        + "\n".join(hardcoded_keyword_literals)
    )


def test_phase17c_rule_parser_regexes_trust_normalized_punctuation() -> None:
    parser_source = (RULE_TOOLING / "rule_parser.py").read_text(encoding="utf-8")
    forbidden_escape_tokens = ("\\u2018", "\\u2019", "\\u201c", "\\u201d", "\\u2013", "\\u2014")
    escaped_violations = [token for token in forbidden_escape_tokens if token in parser_source]
    literal_violations = sorted(
        {
            f"U+{ord(character):04X}"
            for character in parser_source
            if ord(character) in {0x2018, 0x2019, 0x201C, 0x201D, 0x2013, 0x2014}
        }
    )

    assert not escaped_violations
    assert not literal_violations
