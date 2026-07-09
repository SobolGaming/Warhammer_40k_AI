from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
RUNTIME_GENERIC_IR_BOUNDARY_FILES = (
    ROOT / "src" / "warhammer40k_core" / "engine" / "generic_rule_lifecycle_hooks.py",
    ROOT / "src" / "warhammer40k_core" / "engine" / "generic_rule_ability_registry.py",
    ROOT / "src" / "warhammer40k_core" / "engine" / "faction_rule_execution.py",
    ROOT / "src" / "warhammer40k_core" / "engine" / "catalog_command_point_runtime.py",
    ROOT / "src" / "warhammer40k_core" / "engine" / "catalog_command_point_support.py",
    ROOT
    / "src"
    / "warhammer40k_core"
    / "rules"
    / "source_packages"
    / "warhammer_40000_11th"
    / "faction_generic_ir_support_2026_27.py",
    ROOT
    / "src"
    / "warhammer40k_core"
    / "rules"
    / "source_packages"
    / "warhammer_40000_11th"
    / "faction_generic_ir_static_payloads_2026_27.py",
    ROOT
    / "src"
    / "warhammer40k_core"
    / "rules"
    / "source_packages"
    / "warhammer_40000_11th"
    / "faction_cavalcade_of_chaos_ir_static_payloads_2026_27.py",
    ROOT
    / "src"
    / "warhammer40k_core"
    / "rules"
    / "source_packages"
    / "warhammer_40000_11th"
    / "faction_court_of_the_phoenician_ir_support_2026_27.py",
    ROOT
    / "src"
    / "warhammer40k_core"
    / "rules"
    / "source_packages"
    / "warhammer_40000_11th"
    / "faction_spectacle_of_slaughter_ir_support_2026_27.py",
    ROOT / "src" / "warhammer40k_core" / "engine" / "faction_content" / "stratagem_activation.py",
    ROOT
    / "src"
    / "warhammer40k_core"
    / "rules"
    / "source_packages"
    / "warhammer_40000_11th"
    / "faction_stratagem_activation_2026_27.py",
)
GENERIC_RULE_LIFECYCLE_HOOKS = (
    ROOT / "src" / "warhammer40k_core" / "engine" / "generic_rule_lifecycle_hooks.py"
)
FORBIDDEN_RUNTIME_GENERIC_IR_TOKENS = (
    "compile_rule_source_text",
    "RuleSourceText",
    "rule_compiler",
    "source_snapshots",
    "wahapedia",
    "json.loads",
)
FORBIDDEN_GENERIC_RULE_LIFECYCLE_DETACHMENT_TOKENS = (
    "shadow_legion",
    "Shadow Legion",
    "SHADOW_LEGION",
    "shadow-legion",
    "chaos-daemons",
)
CATALOG_COMMAND_POINT_RUNTIME_FILES = (
    ROOT / "src" / "warhammer40k_core" / "engine" / "catalog_command_point_runtime.py",
    ROOT / "src" / "warhammer40k_core" / "engine" / "catalog_command_point_support.py",
)
FORBIDDEN_CATALOG_COMMAND_POINT_TOKENS = (
    "definition.name",
    "normalized_text",
    "source_span.text",
)


def test_ws14_generic_ir_runtime_path_does_not_compile_or_read_raw_source_text() -> None:
    offenders: list[tuple[str, str]] = []
    for path in RUNTIME_GENERIC_IR_BOUNDARY_FILES:
        text = path.read_text(encoding="utf-8")
        for token in FORBIDDEN_RUNTIME_GENERIC_IR_TOKENS:
            if token in text:
                offenders.append((path.relative_to(ROOT).as_posix(), token))

    assert offenders == []


def test_ws14_generic_rule_lifecycle_hooks_use_ability_registry_for_detachment_grants() -> None:
    text = GENERIC_RULE_LIFECYCLE_HOOKS.read_text(encoding="utf-8")
    offenders = [
        token for token in FORBIDDEN_GENERIC_RULE_LIFECYCLE_DETACHMENT_TOKENS if token in text
    ]

    assert offenders == []


def test_catalog_command_point_runtime_uses_structured_ids_not_names_or_rule_text() -> None:
    offenders: list[tuple[str, str]] = []
    for path in CATALOG_COMMAND_POINT_RUNTIME_FILES:
        text = path.read_text(encoding="utf-8")
        for token in FORBIDDEN_CATALOG_COMMAND_POINT_TOKENS:
            if token in text:
                offenders.append((path.relative_to(ROOT).as_posix(), token))

    assert offenders == []
