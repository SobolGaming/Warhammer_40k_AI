from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
RUNTIME_GENERIC_IR_BOUNDARY_FILES = (
    ROOT / "src" / "warhammer40k_core" / "engine" / "faction_rule_execution.py",
    ROOT
    / "src"
    / "warhammer40k_core"
    / "rules"
    / "source_packages"
    / "warhammer_40000_11th"
    / "faction_generic_ir_support_2026_27.py",
    ROOT / "src" / "warhammer40k_core" / "engine" / "faction_content" / "stratagem_activation.py",
    ROOT
    / "src"
    / "warhammer40k_core"
    / "rules"
    / "source_packages"
    / "warhammer_40000_11th"
    / "faction_stratagem_activation_2026_27.py",
)
FORBIDDEN_RUNTIME_GENERIC_IR_TOKENS = (
    "compile_rule_source_text",
    "RuleSourceText",
    "rule_compiler",
    "source_snapshots",
    "wahapedia",
    "json.loads",
)


def test_ws14_generic_ir_runtime_path_does_not_compile_or_read_raw_source_text() -> None:
    offenders: list[tuple[str, str]] = []
    for path in RUNTIME_GENERIC_IR_BOUNDARY_FILES:
        text = path.read_text(encoding="utf-8")
        for token in FORBIDDEN_RUNTIME_GENERIC_IR_TOKENS:
            if token in text:
                offenders.append((path.relative_to(ROOT).as_posix(), token))

    assert offenders == []
