from __future__ import annotations

import ast
import hashlib
import re
from pathlib import Path

import pytest

from warhammer40k_core.engine.faction_content.warhammer_40000_11th.chaos_daemons import (
    datasheets as chaos_daemons_datasheets,
)
from warhammer40k_core.rules.source_packages.warhammer_40000_11th import (
    chaos_daemons_roster_2026_07,
)

ROOT = Path(__file__).resolve().parents[2]
THIS_FILE = Path(__file__).resolve()
HEX_DIGEST_PATTERN = re.compile(r"\b[0-9a-fA-F]{32,}\b")
RECONCILIATION_ARTIFACT = (
    ROOT
    / "src"
    / "warhammer40k_core"
    / "rules"
    / "source_packages"
    / "warhammer_40000_11th"
    / "chaos_daemons_roster_2026_07"
    / chaos_daemons_roster_2026_07.RECONCILIATION_ARTIFACT_PATH
)
CHAOS_DAEMONS_DATASHEET_RUNTIME = (
    ROOT
    / "src"
    / "warhammer40k_core"
    / "engine"
    / "faction_content"
    / "warhammer_40000_11th"
    / "chaos_daemons"
    / "datasheets.py"
)
GIT_ATTRIBUTES = ROOT / ".gitattributes"
RAW_BYTE_HASHED_JSON_ARTIFACTS = (
    RECONCILIATION_ARTIFACT,
    ROOT
    / "src"
    / "warhammer40k_core"
    / "rules"
    / "source_packages"
    / "warhammer_40000_11th"
    / "event_companion_2026_06_artifacts"
    / "primary-scoring.json",
    ROOT
    / "src"
    / "warhammer40k_core"
    / "rules"
    / "source_packages"
    / "warhammer_40000_11th"
    / "event_companion_layouts_2026_06"
    / "artifacts"
    / "event-companion-battlefields.json",
    ROOT
    / "data"
    / "source_audits"
    / "event_companion_2026_06"
    / "phase17n_event_companion_battlefields_pages_9_53_extraction.json",
    ROOT
    / "data"
    / "source_audits"
    / "event_companion_2026_06"
    / "phase17n_event_companion_stable_runtime_identity_map.json",
    ROOT
    / "src"
    / "warhammer40k_core"
    / "rules"
    / "source_packages"
    / "warhammer_40000_11th"
    / "app_core_rules_hidden_2026_08_09"
    / "artifacts"
    / "hidden.json",
    ROOT
    / "src"
    / "warhammer40k_core"
    / "rules"
    / "source_packages"
    / "warhammer_40000_11th"
    / "july_rules_updates_2026_07"
    / "artifacts"
    / "package.json",
)


def test_active_code_tests_and_docs_do_not_reference_retired_edition_ids() -> None:
    violations: list[str] = []

    for path in _scanned_paths():
        text = _without_hex_digests(path.read_text(encoding="utf-8"))
        relative_path = path.relative_to(ROOT).as_posix()
        for token in _retired_identity_tokens():
            if token in text:
                violations.append(f"{relative_path}: contains {token!r}")

    assert not violations, (
        "Phase 14A requires active runtime, test, and docs identity to be 11th Edition-only:\n"
        + "\n".join(violations)
    )


def test_retired_identity_scanner_folds_concatenated_string_literals() -> None:
    source = 'RETIRED = "warhammer_40000_" + "1" + "0" + "th"'

    assert "warhammer_40000_10th" in _python_constant_strings(source)


def test_chaos_daemons_datasheet_runtime_does_not_construct_retired_source_ids() -> None:
    source = _without_hex_digests(CHAOS_DAEMONS_DATASHEET_RUNTIME.read_text(encoding="utf-8"))
    evaluated_strings = _python_constant_strings(source)

    assert not {
        token
        for token in _retired_identity_tokens()
        if token in source or any(token in value for value in evaluated_strings)
    }


def test_chaos_daemons_runtime_sources_are_stable_ability_ids() -> None:
    contribution = chaos_daemons_datasheets.runtime_contribution()
    source_ids = frozenset(
        (
            *(binding.source_id for binding in contribution.hit_roll_modifier_bindings),
            *(binding.source_id for binding in contribution.movement_budget_modifier_bindings),
            *(binding.source_id for binding in contribution.objective_control_modifier_bindings),
            *(binding.source_id for binding in contribution.weapon_profile_modifier_bindings),
            *(binding.source_id for binding in contribution.hook_bindings),
        )
    )

    assert source_ids == frozenset(
        {
            chaos_daemons_datasheets.BLOODTHIRSTER_DAEMON_LORD_ABILITY_ID,
            chaos_daemons_datasheets.BLOODTHIRSTER_RELENTLESS_CARNAGE_ABILITY_ID,
            chaos_daemons_datasheets.SKARBRAND_RAGE_EMBODIED_ABILITY_ID,
            chaos_daemons_datasheets.LORD_OF_CHANGE_DAEMON_LORD_ABILITY_ID,
            chaos_daemons_datasheets.PLAGUEBEARERS_INFECTED_OUTBREAK_ABILITY_ID,
            chaos_daemons_datasheets.KEEPER_DAEMON_LORD_SLAANESH_ABILITY_ID,
            chaos_daemons_datasheets.ROTIGUS_DELUGE_ABILITY_ID,
            chaos_daemons_datasheets.NURGLINGS_MISCHIEF_MAKERS_ABILITY_ID,
            chaos_daemons_datasheets.POXBRINGER_FECULENT_DESPAIR_ABILITY_ID,
        }
    )
    assert not any(
        retired_token in source_id
        for source_id in source_ids
        for retired_token in _retired_identity_tokens()
    )


def test_exact_roster_reconciliation_is_current_only_hash_and_schema_bounded() -> None:
    raw = RECONCILIATION_ARTIFACT.read_bytes()
    expected_name, expected_hash = (
        chaos_daemons_roster_2026_07.EXPECTED_RECONCILIATION_SOURCE_ARTIFACT
    )
    reconciliation = chaos_daemons_roster_2026_07.reconciliation_manifest()

    assert expected_name == "official-pdf-exact-five-reconciliation.json"
    assert hashlib.sha256(raw).hexdigest() == expected_hash
    assert reconciliation.official_pdf.source_package_id == (
        chaos_daemons_roster_2026_07.EXPECTED_CURRENT_FACTION_SOURCE_PACKAGE_ID
    )
    assert reconciliation.generator_inputs.artifact_hashes == tuple(
        sorted(chaos_daemons_roster_2026_07.EXPECTED_GENERATOR_INPUT_ARTIFACT_HASHES)
    )
    assert set(reconciliation.to_payload()["generator_inputs"]) == {"artifact_hashes"}
    assert tuple(row.datasheet_id for row in reconciliation.datasheets) == (
        chaos_daemons_roster_2026_07.EXPECTED_DATASHEET_IDS
    )


def test_raw_byte_hashed_json_artifacts_have_platform_stable_line_endings() -> None:
    attributes = tuple(
        line.strip()
        for line in GIT_ATTRIBUTES.read_text(encoding="utf-8").splitlines()
        if line.strip() and not line.lstrip().startswith("#")
    )

    assert "*.json text eol=lf" in attributes
    assert {
        path.relative_to(ROOT).as_posix()
        for path in RAW_BYTE_HASHED_JSON_ARTIFACTS
        if b"\r\n" in path.read_bytes()
    } == set()


def test_runtime_reconciliation_loader_rejects_raw_hash_drift(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    raw = RECONCILIATION_ARTIFACT.read_bytes()

    def drifted_artifact_bytes(package_name: str, artifact_path: str) -> bytes:
        assert package_name
        assert artifact_path == chaos_daemons_roster_2026_07.RECONCILIATION_ARTIFACT_PATH
        return raw + b"\n"

    chaos_daemons_roster_2026_07.reconciliation_manifest.cache_clear()
    monkeypatch.setattr(
        chaos_daemons_roster_2026_07,
        "package_artifact_bytes",
        drifted_artifact_bytes,
    )
    with pytest.raises(
        chaos_daemons_roster_2026_07.ChaosDaemonsRosterCatalogError,
        match="raw artifact hash drifted",
    ):
        chaos_daemons_roster_2026_07.reconciliation_manifest()


def _scanned_paths() -> tuple[Path, ...]:
    roots = (
        ROOT / "src",
        ROOT / "tests",
        ROOT / "docs",
        ROOT / "README.md",
        ROOT / "ARCHITECTURE_V2.md",
    )
    paths: list[Path] = []
    for root in roots:
        if root.is_file():
            paths.append(root)
            continue
        paths.extend(path for path in root.rglob("*") if path.is_file())
    return tuple(
        sorted(
            (
                path
                for path in paths
                if path.suffix in {".md", ".py", ".json"}
                and "__pycache__" not in path.parts
                and path != THIS_FILE
            ),
            key=lambda path: path.as_posix(),
        )
    )


def _retired_identity_tokens() -> tuple[str, ...]:
    return (
        "warhammer_40000_" + "10th",
        "gw-" + "10e",
        "1" + "0" + "e",
        "1" + "0" + "th",
        "tenth",
        "Tenth",
        "TENTH",
        "11e" + "_" + "preview",
        "eleventh" + "_" + "preview",
        "ELEVENTH" + "_" + "PREVIEW",
    )


def _without_hex_digests(text: str) -> str:
    return HEX_DIGEST_PATTERN.sub("", text)


def _python_constant_strings(source: str) -> tuple[str, ...]:
    tree = ast.parse(source)
    return tuple(
        value for node in ast.walk(tree) if (value := _static_string_value(node)) is not None
    )


def _static_string_value(node: ast.AST) -> str | None:
    if isinstance(node, ast.Constant) and type(node.value) is str:
        return node.value
    if isinstance(node, ast.BinOp) and isinstance(node.op, ast.Add):
        left = _static_string_value(node.left)
        right = _static_string_value(node.right)
        if left is not None and right is not None:
            return left + right
    return None
