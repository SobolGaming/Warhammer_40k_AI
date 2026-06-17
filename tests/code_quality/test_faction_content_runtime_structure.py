from __future__ import annotations

import importlib
from pathlib import Path

import pytest
from tools import generate_faction_content_scaffold

from warhammer40k_core.engine.abilities import (
    AbilityCatalogRecord,
    AbilityDefinition,
    AbilitySourceKind,
    AbilityTimingDescriptor,
)
from warhammer40k_core.engine.faction_content.bundle import RuntimeContentContribution
from warhammer40k_core.engine.faction_content.manifest import (
    RuntimeContentModuleFamily,
    RuntimeContentSupportStatus,
)
from warhammer40k_core.engine.faction_content.warhammer_40000_11th import generated_manifest
from warhammer40k_core.engine.timing_windows import TimingTriggerKind
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


def test_agent_owned_scaffold_check_allows_implemented_file(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    implemented_path = tmp_path / "rule.py"
    implemented_path.write_text(
        "\n".join(
            (
                "from __future__ import annotations",
                "",
                "from warhammer40k_core.engine.faction_content.bundle import "
                "RuntimeContentContribution",
                "",
                'CONTRIBUTION_ID = "implemented:rule"',
                "",
                "",
                "def runtime_contribution() -> RuntimeContentContribution:",
                "    return RuntimeContentContribution(contribution_id=CONTRIBUTION_ID)",
            )
        ),
        encoding="utf-8",
    )
    expected_file = generate_faction_content_scaffold.GeneratedFile(
        path=implemented_path,
        content="placeholder content",
    )

    monkeypatch.setattr(generate_faction_content_scaffold, "expected_generator_owned_files", tuple)
    monkeypatch.setattr(
        generate_faction_content_scaffold,
        "expected_agent_owned_files",
        lambda: (expected_file,),
    )
    monkeypatch.setattr(
        generate_faction_content_scaffold,
        "orphaned_generated_placeholder_files",
        tuple,
    )

    assert generate_faction_content_scaffold.stale_generated_files() == ()


def test_write_expected_files_preserves_implemented_agent_file(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    implemented_path = tmp_path / "army_rule.py"
    implemented_content = "\n".join(
        (
            "from __future__ import annotations",
            "",
            'CONTRIBUTION_ID = "implemented:army-rule"',
            "",
            "",
            "def runtime_contribution() -> object:",
            "    return CONTRIBUTION_ID",
        )
    )
    placeholder_content = "\n".join(
        (
            generate_faction_content_scaffold.PLACEHOLDER_MARKER,
            'CONTRIBUTION_ID = "placeholder:army-rule"',
            "",
            "",
            "def runtime_contribution() -> object:",
            "    return CONTRIBUTION_ID",
        )
    )
    implemented_path.write_text(implemented_content, encoding="utf-8")
    expected_file = generate_faction_content_scaffold.GeneratedFile(
        path=implemented_path,
        content=placeholder_content,
    )

    monkeypatch.setattr(generate_faction_content_scaffold, "expected_generator_owned_files", tuple)
    monkeypatch.setattr(
        generate_faction_content_scaffold,
        "expected_agent_owned_files",
        lambda: (expected_file,),
    )

    generate_faction_content_scaffold.write_expected_files()
    assert implemented_path.read_text(encoding="utf-8") == implemented_content

    generate_faction_content_scaffold.write_expected_files(force=True)
    assert implemented_path.read_text(encoding="utf-8") == placeholder_content


def test_orphaned_generated_placeholder_files_are_stale(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    orphan_path = tmp_path / "old_generated" / "rule.py"
    orphan_path.parent.mkdir()
    orphan_path.write_text(
        f"{generate_faction_content_scaffold.PLACEHOLDER_MARKER}\n",
        encoding="utf-8",
    )

    monkeypatch.setattr(generate_faction_content_scaffold, "EDITION_ROOT", tmp_path)
    monkeypatch.setattr(generate_faction_content_scaffold, "ROOT", tmp_path)
    monkeypatch.setattr(generate_faction_content_scaffold, "expected_agent_owned_files", tuple)

    assert generate_faction_content_scaffold.orphaned_generated_placeholder_files() == (
        "old_generated/rule.py",
    )


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


def test_scaffold_contributions_have_stable_ids_and_placeholders_are_empty() -> None:
    invalid_modules: list[str] = []
    for module_path in generate_faction_content_scaffold.scaffold_runtime_module_paths():
        module = importlib.import_module(module_path)
        contribution = module.runtime_contribution()
        expected_id = generate_faction_content_scaffold.contribution_id_for_module_path(module_path)
        if contribution.contribution_id != expected_id:
            invalid_modules.append(module_path)
            continue
        module_file = Path(module.__file__ or "")
        if generate_faction_content_scaffold.PLACEHOLDER_MARKER not in module_file.read_text(
            encoding="utf-8"
        ):
            continue
        if (
            contribution.ability_records
            or contribution.stratagem_records
            or contribution.ability_handler_bindings
            or contribution.stratagem_handler_bindings
            or contribution.rule_runtime_bindings
            or contribution.event_subscriptions
            or contribution.event_handler_bindings
            or contribution.battle_formation_hook_bindings
            or contribution.battle_shock_hook_bindings
            or contribution.fall_back_hook_bindings
            or contribution.movement_end_surge_hook_bindings
            or contribution.enhancement_effect_bindings
            or contribution.fight_activation_ability_hook_bindings
            or contribution.phase_end_objective_control_hook_bindings
            or contribution.faction_named_handlers
        ):
            invalid_modules.append(module_path)

    assert invalid_modules == []


def test_generated_detachment_manifest_aggregates_agent_owned_rule_module(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    manifest_module_path = (
        "warhammer40k_core.engine.faction_content.warhammer_40000_11th."
        "orks.detachments.war_horde.manifest"
    )
    rule_module_path = (
        "warhammer40k_core.engine.faction_content.warhammer_40000_11th."
        "orks.detachments.war_horde.rule"
    )
    manifest_module = importlib.import_module(manifest_module_path)
    rule_module = importlib.import_module(rule_module_path)
    sentinel_record = _sentinel_detachment_ability_record()

    def sentinel_runtime_contribution() -> RuntimeContentContribution:
        return RuntimeContentContribution(
            contribution_id="sentinel:war-horde-rule",
            ability_records=(sentinel_record,),
        )

    with monkeypatch.context() as patch:
        patch.setattr(rule_module, "runtime_contribution", sentinel_runtime_contribution)
        manifest_module = importlib.reload(manifest_module)
        contribution = manifest_module.runtime_contribution()

    importlib.reload(manifest_module)

    assert contribution.contribution_id == (
        "warhammer_40000_11th:orks:detachment:war_horde:manifest:scaffold"
    )
    assert contribution.ability_records == (sentinel_record,)


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


def _sentinel_detachment_ability_record() -> AbilityCatalogRecord:
    return AbilityCatalogRecord(
        record_id="record:war-horde-sentinel",
        definition=AbilityDefinition(
            ability_id="ability:war-horde-sentinel",
            name="War Horde Sentinel",
            source_id="source:war-horde-sentinel",
            when_descriptor="test timing",
            effect_descriptor="test effect",
            restrictions_descriptor="test restrictions",
            timing=AbilityTimingDescriptor(trigger_kind=TimingTriggerKind.START_PHASE),
        ),
        source_kind=AbilitySourceKind.DETACHMENT,
        detachment_id="war-horde",
    )
