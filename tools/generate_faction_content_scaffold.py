from __future__ import annotations

import argparse
import difflib
import keyword
from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path

from warhammer40k_core.rules.source_packages.warhammer_40000_11th import (
    faction_detachments_2026_27,
)

ROOT = Path(__file__).resolve().parents[1]
EDITION_ROOT = (
    ROOT / "src" / "warhammer40k_core" / "engine" / "faction_content" / "warhammer_40000_11th"
)
GENERATED_MANIFEST_PATH = EDITION_ROOT / "generated_manifest.py"
BASE_IMPORT_PATH = "warhammer40k_core.engine.faction_content.warhammer_40000_11th"
GENERATOR_RELATIVE_PATH = "tools/generate_faction_content_scaffold.py"
SCAFFOLD_MODULE_FILENAMES = ("manifest.py", "rule.py", "enhancements.py", "stratagems.py")


@dataclass(frozen=True, slots=True)
class GeneratedFile:
    path: Path
    content: str


def expected_generated_files() -> tuple[GeneratedFile, ...]:
    files: list[GeneratedFile] = [
        GeneratedFile(path=GENERATED_MANIFEST_PATH, content=_generated_manifest_content())
    ]
    for faction_row in faction_detachments_2026_27.faction_rows():
        faction_module = module_name_for_id(faction_row.faction_id)
        faction_dir = EDITION_ROOT / faction_module
        files.extend(
            (
                GeneratedFile(path=faction_dir / "__init__.py", content=_package_init_content()),
                GeneratedFile(
                    path=faction_dir / "manifest.py",
                    content=_runtime_module_content(
                        contribution_id=(
                            f"warhammer_40000_11th:{faction_module}:faction_manifest:scaffold"
                        )
                    ),
                ),
                GeneratedFile(
                    path=faction_dir / "army_rule.py",
                    content=_runtime_module_content(
                        contribution_id=(
                            f"warhammer_40000_11th:{faction_module}:army_rule:scaffold"
                        )
                    ),
                ),
                GeneratedFile(
                    path=faction_dir / "detachments" / "__init__.py",
                    content=_package_init_content(),
                ),
            )
        )
    for detachment_row in faction_detachments_2026_27.detachment_rows():
        faction_module = module_name_for_id(detachment_row.faction_id)
        detachment_module = module_name_for_id(detachment_row.detachment_id)
        detachment_dir = EDITION_ROOT / faction_module / "detachments" / detachment_module
        files.append(
            GeneratedFile(path=detachment_dir / "__init__.py", content=_package_init_content())
        )
        for filename in SCAFFOLD_MODULE_FILENAMES:
            role = filename.removesuffix(".py")
            files.append(
                GeneratedFile(
                    path=detachment_dir / filename,
                    content=_runtime_module_content(
                        contribution_id=(
                            "warhammer_40000_11th:"
                            f"{faction_module}:detachment:{detachment_module}:{role}:scaffold"
                        )
                    ),
                )
            )
    return tuple(sorted(files, key=lambda generated_file: generated_file.path.as_posix()))


def scaffold_runtime_module_paths() -> tuple[str, ...]:
    module_paths: list[str] = []
    for faction_row in faction_detachments_2026_27.faction_rows():
        faction_module = module_name_for_id(faction_row.faction_id)
        module_paths.extend(
            (
                f"{BASE_IMPORT_PATH}.{faction_module}.manifest",
                f"{BASE_IMPORT_PATH}.{faction_module}.army_rule",
            )
        )
    for detachment_row in faction_detachments_2026_27.detachment_rows():
        faction_module = module_name_for_id(detachment_row.faction_id)
        detachment_module = module_name_for_id(detachment_row.detachment_id)
        base = f"{BASE_IMPORT_PATH}.{faction_module}.detachments.{detachment_module}"
        module_paths.extend(
            (
                f"{base}.manifest",
                f"{base}.rule",
                f"{base}.enhancements",
                f"{base}.stratagems",
            )
        )
    return tuple(sorted(module_paths))


def contribution_id_for_module_path(module_path: str) -> str:
    prefix = f"{BASE_IMPORT_PATH}."
    if not module_path.startswith(prefix):
        raise ValueError("Scaffold module path must be inside the 11th Edition runtime package.")
    parts = module_path.removeprefix(prefix).split(".")
    if len(parts) == 2:
        faction_module, role = parts
        if role == "manifest":
            return f"warhammer_40000_11th:{faction_module}:faction_manifest:scaffold"
        if role == "army_rule":
            return f"warhammer_40000_11th:{faction_module}:army_rule:scaffold"
    if len(parts) == 4 and parts[1] == "detachments":
        faction_module, detachment_module, role = parts[0], parts[2], parts[3]
        return (
            f"warhammer_40000_11th:{faction_module}:detachment:{detachment_module}:{role}:scaffold"
        )
    raise ValueError(f"Unrecognized scaffold module path: {module_path}.")


def module_name_for_id(identifier: str) -> str:
    module_name = identifier.replace("-", "_")
    if module_name.isidentifier() and not keyword.iskeyword(module_name):
        return module_name
    return f"content_{module_name}"


def write_expected_files() -> None:
    for generated_file in expected_generated_files():
        generated_file.path.parent.mkdir(parents=True, exist_ok=True)
        generated_file.path.write_text(generated_file.content, encoding="utf-8", newline="\n")


def stale_generated_files() -> tuple[str, ...]:
    stale: list[str] = []
    for generated_file in expected_generated_files():
        current = (
            generated_file.path.read_text(encoding="utf-8") if generated_file.path.exists() else ""
        )
        if current != generated_file.content:
            stale.append(generated_file.path.relative_to(ROOT).as_posix())
    return tuple(stale)


def diff_stale_files() -> str:
    chunks: list[str] = []
    for generated_file in expected_generated_files():
        current = (
            generated_file.path.read_text(encoding="utf-8") if generated_file.path.exists() else ""
        )
        if current == generated_file.content:
            continue
        relative_path = generated_file.path.relative_to(ROOT).as_posix()
        chunks.extend(
            difflib.unified_diff(
                current.splitlines(),
                generated_file.content.splitlines(),
                fromfile=f"{relative_path}:current",
                tofile=f"{relative_path}:expected",
                lineterm="",
            )
        )
    return "\n".join(chunks)


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Generate source-backed 11th Edition faction runtime scaffolds."
    )
    parser.add_argument(
        "--check",
        action="store_true",
        help="Fail if generated scaffold files are stale without writing them.",
    )
    args = parser.parse_args(argv)

    if args.check:
        stale = stale_generated_files()
        if stale:
            print("Generated faction runtime scaffold is stale:")
            for path in stale:
                print(f"- {path}")
            diff = diff_stale_files()
            if diff:
                print(diff)
            return 1
        return 0

    write_expected_files()
    return 0


def _package_init_content() -> str:
    return _generated_header()


def _runtime_module_content(*, contribution_id: str) -> str:
    return (
        f"{_generated_header()}\n"
        "from warhammer40k_core.engine.faction_content.bundle import "
        "RuntimeContentContribution\n"
        "\n"
        f"{_contribution_id_assignment(contribution_id)}\n"
        "\n"
        "\n"
        "def runtime_contribution() -> RuntimeContentContribution:\n"
        '    """Runtime load scaffold only.\n'
        "\n"
        "    Semantic execution must be supplied by source-backed RuleIR,\n"
        "    named handlers, event subscriptions, ability records, or Stratagem\n"
        "    handler bindings in implementation PRs.\n"
        '    """\n'
        "    return RuntimeContentContribution(contribution_id=CONTRIBUTION_ID)\n"
    )


def _generated_manifest_content() -> str:
    return (
        f"{_generated_header()}\n"
        "import keyword\n"
        "\n"
        "from warhammer40k_core.engine.faction_content.manifest import (\n"
        "    RuntimeContentManifestRow,\n"
        "    RuntimeContentModuleFamily,\n"
        "    RuntimeContentSupportStatus,\n"
        ")\n"
        "from warhammer40k_core.rules.source_packages.warhammer_40000_11th import (\n"
        "    faction_detachments_2026_27,\n"
        "    faction_execution_2026_27,\n"
        ")\n"
        "\n"
        f'_BASE = "{BASE_IMPORT_PATH}"\n'
        "_SOURCE_IDENTITY = faction_execution_2026_27.source_package_identity_payload()\n"
        '_SOURCE_PACKAGE_ID = _SOURCE_IDENTITY["source_package_id"]\n'
        '_SOURCE_PACKAGE_HASH = _SOURCE_IDENTITY["source_payload_checksum_sha256"]\n'
        "_EXECUTION_RECORDS = faction_execution_2026_27.execution_records()\n"
        "\n"
        "\n"
        "def generated_runtime_content_rows() -> tuple[RuntimeContentManifestRow, ...]:\n"
        "    return (\n"
        "        *tuple(_faction_row(row) "
        "for row in faction_detachments_2026_27.faction_rows()),\n"
        "        *tuple(_detachment_row(row) "
        "for row in faction_detachments_2026_27.detachment_rows()),\n"
        "        *_pilot_runtime_content_rows(),\n"
        "    )\n"
        "\n"
        "\n"
        "def _faction_row(\n"
        "    row: faction_detachments_2026_27.SourceFactionRow,\n"
        ") -> RuntimeContentManifestRow:\n"
        "    faction_module = _module_name_for_id(row.faction_id)\n"
        "    return _row(\n"
        "        content_id=row.faction_id,\n"
        "        family=RuntimeContentModuleFamily.FACTION,\n"
        "        source_ids=_source_ids_for(faction_id=row.faction_id, detachment_id=None),\n"
        "        owner_faction_id=row.faction_id,\n"
        "        owner_detachment_id=None,\n"
        "        execution_record_ids=_execution_ids_for(\n"
        "            faction_id=row.faction_id,\n"
        "            detachment_id=None,\n"
        "        ),\n"
        '        module_path=f"{_BASE}.{faction_module}.manifest",\n'
        "    )\n"
        "\n"
        "\n"
        "def _detachment_row(\n"
        "    row: faction_detachments_2026_27.SourceDetachmentRow,\n"
        ") -> RuntimeContentManifestRow:\n"
        "    faction_module = _module_name_for_id(row.faction_id)\n"
        "    detachment_module = _module_name_for_id(row.detachment_id)\n"
        "    return _row(\n"
        "        content_id=row.detachment_id,\n"
        "        family=RuntimeContentModuleFamily.DETACHMENT,\n"
        "        source_ids=_source_ids_for(\n"
        "            faction_id=row.faction_id,\n"
        "            detachment_id=row.detachment_id,\n"
        "        ),\n"
        "        owner_faction_id=row.faction_id,\n"
        "        owner_detachment_id=row.detachment_id,\n"
        "        execution_record_ids=_execution_ids_for(\n"
        "            faction_id=row.faction_id,\n"
        "            detachment_id=row.detachment_id,\n"
        "        ),\n"
        '        module_path=(f"{_BASE}.{faction_module}.detachments.'
        '{detachment_module}.manifest"),\n'
        "    )\n"
        "\n"
        "\n"
        "def _pilot_runtime_content_rows() -> tuple[RuntimeContentManifestRow, ...]:\n"
        "    return (\n"
        "        _row(\n"
        '            content_id="plague-marines",\n'
        "            family=RuntimeContentModuleFamily.DATASHEET,\n"
        "            source_ids=_source_ids_for(\n"
        '                faction_id="death-guard",\n'
        "                detachment_id=None,\n"
        "            ),\n"
        '            owner_faction_id="death-guard",\n'
        "            owner_detachment_id=None,\n"
        "            execution_record_ids="
        '_execution_ids_matching("death-guard:datasheet-intake"),\n'
        '            module_path=f"{_BASE}.death_guard.units.plague_marines",\n'
        "        ),\n"
        "        _row(\n"
        '            content_id="typhus",\n'
        "            family=RuntimeContentModuleFamily.DATASHEET,\n"
        "            source_ids=_source_ids_for(\n"
        '                faction_id="death-guard",\n'
        "                detachment_id=None,\n"
        "            ),\n"
        '            owner_faction_id="death-guard",\n'
        "            owner_detachment_id=None,\n"
        "            execution_record_ids="
        '_execution_ids_matching("death-guard:datasheet-intake"),\n'
        '            module_path=f"{_BASE}.death_guard.units.typhus",\n'
        "        ),\n"
        "        _row(\n"
        '            content_id="plague-weapons",\n'
        "            family=RuntimeContentModuleFamily.WARGEAR,\n"
        "            source_ids=_source_ids_for(\n"
        '                faction_id="death-guard",\n'
        "                detachment_id=None,\n"
        "            ),\n"
        '            owner_faction_id="death-guard",\n'
        "            owner_detachment_id=None,\n"
        "            execution_record_ids="
        '_execution_ids_matching("death-guard:datasheet-intake"),\n'
        '            module_path=f"{_BASE}.death_guard.wargear.plague_weapons",\n'
        '            dependency_ids=("plague-weapons:standard",),\n'
        "        ),\n"
        "        _row(\n"
        '            content_id="plague-weapons:standard",\n'
        "            family=RuntimeContentModuleFamily.WEAPON_PROFILE,\n"
        "            source_ids=_source_ids_for(\n"
        '                faction_id="death-guard",\n'
        "                detachment_id=None,\n"
        "            ),\n"
        '            owner_faction_id="death-guard",\n'
        "            owner_detachment_id=None,\n"
        "            execution_record_ids="
        '_execution_ids_matching("death-guard:datasheet-intake"),\n'
        '            module_path=f"{_BASE}.death_guard.wargear.plague_weapons",\n'
        "        ),\n"
        "    )\n"
        "\n"
        "\n"
        "def _row(\n"
        "    *,\n"
        "    content_id: str,\n"
        "    family: RuntimeContentModuleFamily,\n"
        "    source_ids: tuple[str, ...],\n"
        "    owner_faction_id: str | None,\n"
        "    owner_detachment_id: str | None,\n"
        "    execution_record_ids: tuple[str, ...],\n"
        "    module_path: str,\n"
        "    dependency_ids: tuple[str, ...] = (),\n"
        ") -> RuntimeContentManifestRow:\n"
        "    return RuntimeContentManifestRow(\n"
        "        content_id=content_id,\n"
        "        family=family,\n"
        "        source_ids=source_ids,\n"
        "        owner_faction_id=owner_faction_id,\n"
        "        owner_detachment_id=owner_detachment_id,\n"
        "        source_package_id=_SOURCE_PACKAGE_ID,\n"
        "        source_package_hash=_SOURCE_PACKAGE_HASH,\n"
        "        execution_record_ids=execution_record_ids,\n"
        "        module_path=module_path,\n"
        "        support_status=RuntimeContentSupportStatus.SUPPORTED,\n"
        "        dependency_ids=dependency_ids,\n"
        "    )\n"
        "\n"
        "\n"
        "def _execution_ids_for(\n"
        "    *,\n"
        "    faction_id: str,\n"
        "    detachment_id: str | None,\n"
        ") -> tuple[str, ...]:\n"
        "    return tuple(\n"
        "        sorted(\n"
        "            record.execution_id\n"
        "            for record in _EXECUTION_RECORDS\n"
        "            if record.faction_id == faction_id and record.detachment_id == detachment_id\n"
        "        )\n"
        "    )\n"
        "\n"
        "\n"
        "def _execution_ids_matching(token: str) -> tuple[str, ...]:\n"
        "    return tuple(\n"
        "        sorted(record.execution_id "
        "for record in _EXECUTION_RECORDS if token in record.execution_id)\n"
        "    )\n"
        "\n"
        "\n"
        "def _source_ids_for(\n"
        "    *,\n"
        "    faction_id: str,\n"
        "    detachment_id: str | None,\n"
        ") -> tuple[str, ...]:\n"
        "    source_ids = {\n"
        "        source_id\n"
        "        for record in _EXECUTION_RECORDS\n"
        "        if record.faction_id == faction_id and record.detachment_id == detachment_id\n"
        "        for source_id in record.source_ids\n"
        "    }\n"
        "    return tuple(sorted(source_ids))\n"
        "\n"
        "\n"
        "def _module_name_for_id(identifier: str) -> str:\n"
        '    module_name = identifier.replace("-", "_")\n'
        "    if module_name.isidentifier() and not keyword.iskeyword(module_name):\n"
        "        return module_name\n"
        '    return f"content_{module_name}"\n'
    )


def _generated_header() -> str:
    return (
        "# Generated by tools/generate_faction_content_scaffold.py.\n"
        "# Regenerate with `uv run python tools/generate_faction_content_scaffold.py`.\n"
        "from __future__ import annotations\n"
    )


def _contribution_id_assignment(contribution_id: str) -> str:
    single_line = f'CONTRIBUTION_ID = "{contribution_id}"'
    if len(single_line) <= 100:
        return single_line
    parts = "\n".join(f'        "{part}",' for part in contribution_id.split(":"))
    return f'CONTRIBUTION_ID = ":".join(\n    (\n{parts}\n    )\n)'


if __name__ == "__main__":
    raise SystemExit(main())
