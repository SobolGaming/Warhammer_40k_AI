from __future__ import annotations

import importlib
from pathlib import Path

from tools import generate_faction_content_scaffold

from warhammer40k_core.engine.faction_content.bundle import RuntimeContentContribution
from warhammer40k_core.engine.faction_content.manifest import (
    RuntimeContentModuleFamily,
    RuntimeContentSupportStatus,
)
from warhammer40k_core.engine.faction_content.warhammer_40000_11th import generated_manifest
from warhammer40k_core.rules.source_packages.warhammer_40000_11th import (
    faction_detachments_2026_27,
)

ROOT = Path(__file__).resolve().parents[2]
FACTION_CONTENT_ROOT = ROOT / "src" / "warhammer40k_core" / "engine" / "faction_content"
EDITION_ROOT = FACTION_CONTENT_ROOT / "warhammer_40000_11th"
MAX_FACTION_CONTENT_FILE_LINES = 2000
FORBIDDEN_RUNTIME_IMPORT_TOKENS = (
    "html_sanitizer",
    "rule_compiler",
    "rule_parser",
    "wahapedia",
)


def test_faction_content_runtime_files_stay_below_line_limit() -> None:
    oversized: list[tuple[str, int]] = []
    for path in sorted(FACTION_CONTENT_ROOT.rglob("*.py")):
        line_count = len(path.read_text(encoding="utf-8").splitlines())
        if line_count > MAX_FACTION_CONTENT_FILE_LINES:
            oversized.append((path.relative_to(ROOT).as_posix(), line_count))

    assert oversized == []


def test_faction_content_runtime_does_not_import_raw_source_or_parser_tooling() -> None:
    offenders: list[tuple[str, str]] = []
    for path in sorted(FACTION_CONTENT_ROOT.rglob("*.py")):
        text = path.read_text(encoding="utf-8")
        for token in FORBIDDEN_RUNTIME_IMPORT_TOKENS:
            if token in text:
                offenders.append((path.relative_to(ROOT).as_posix(), token))

    assert offenders == []


def test_generated_faction_runtime_scaffold_is_current() -> None:
    assert generate_faction_content_scaffold.stale_generated_files() == ()


def test_all_generated_factions_have_package_roots() -> None:
    missing: list[str] = []
    for row in faction_detachments_2026_27.faction_rows():
        faction_dir = EDITION_ROOT / generate_faction_content_scaffold.module_name_for_id(
            row.faction_id
        )
        for path in (
            faction_dir / "__init__.py",
            faction_dir / "manifest.py",
            faction_dir / "army_rule.py",
            faction_dir / "detachments" / "__init__.py",
        ):
            if not path.exists():
                missing.append(path.relative_to(ROOT).as_posix())

    assert missing == []


def test_all_generated_detachments_have_required_files() -> None:
    missing: list[str] = []
    for row in faction_detachments_2026_27.detachment_rows():
        faction_module = generate_faction_content_scaffold.module_name_for_id(row.faction_id)
        detachment_module = generate_faction_content_scaffold.module_name_for_id(row.detachment_id)
        detachment_dir = EDITION_ROOT / faction_module / "detachments" / detachment_module
        for filename in (
            "__init__.py",
            "manifest.py",
            "rule.py",
            "enhancements.py",
            "stratagems.py",
        ):
            path = detachment_dir / filename
            if not path.exists():
                missing.append(path.relative_to(ROOT).as_posix())

    assert missing == []


def test_all_scaffold_modules_export_runtime_contribution() -> None:
    invalid_modules: list[str] = []
    for module_path in generate_faction_content_scaffold.scaffold_runtime_module_paths():
        module = importlib.import_module(module_path)
        factory = getattr(module, "runtime_contribution", None)
        if not callable(factory):
            invalid_modules.append(module_path)
            continue
        contribution = factory()
        if type(contribution) is not RuntimeContentContribution:
            invalid_modules.append(module_path)

    assert invalid_modules == []


def test_scaffold_contributions_are_empty_and_have_stable_ids() -> None:
    invalid_modules: list[str] = []
    for module_path in generate_faction_content_scaffold.scaffold_runtime_module_paths():
        module = importlib.import_module(module_path)
        contribution = module.runtime_contribution()
        expected_id = generate_faction_content_scaffold.contribution_id_for_module_path(module_path)
        if contribution.contribution_id != expected_id:
            invalid_modules.append(module_path)
            continue
        if (
            contribution.ability_records
            or contribution.stratagem_records
            or contribution.ability_handler_bindings
            or contribution.stratagem_handler_bindings
            or contribution.rule_runtime_bindings
            or contribution.event_subscriptions
            or contribution.event_handler_bindings
            or contribution.faction_named_handlers
        ):
            invalid_modules.append(module_path)

    assert invalid_modules == []


def test_generated_manifest_module_paths_match_scaffold_files() -> None:
    rows_by_content_id = {
        row.content_id: row for row in generated_manifest.generated_runtime_content_rows()
    }

    for faction_row in faction_detachments_2026_27.faction_rows():
        faction_module = generate_faction_content_scaffold.module_name_for_id(
            faction_row.faction_id
        )
        expected_module_path = (
            "warhammer40k_core.engine.faction_content.warhammer_40000_11th"
            f".{faction_module}.manifest"
        )
        row = rows_by_content_id[faction_row.faction_id]
        assert row.family is RuntimeContentModuleFamily.FACTION
        assert row.support_status is RuntimeContentSupportStatus.SUPPORTED
        assert row.module_path == expected_module_path
        assert row.source_ids
        assert row.execution_record_ids

    for detachment_row in faction_detachments_2026_27.detachment_rows():
        faction_module = generate_faction_content_scaffold.module_name_for_id(
            detachment_row.faction_id
        )
        detachment_module = generate_faction_content_scaffold.module_name_for_id(
            detachment_row.detachment_id
        )
        expected_module_path = (
            "warhammer40k_core.engine.faction_content.warhammer_40000_11th"
            f".{faction_module}.detachments.{detachment_module}.manifest"
        )
        row = rows_by_content_id[detachment_row.detachment_id]
        assert row.family is RuntimeContentModuleFamily.DETACHMENT
        assert row.support_status is RuntimeContentSupportStatus.SUPPORTED
        assert row.module_path == expected_module_path
        assert row.owner_faction_id == detachment_row.faction_id
        assert row.owner_detachment_id == detachment_row.detachment_id
        assert row.source_ids
        assert row.execution_record_ids
