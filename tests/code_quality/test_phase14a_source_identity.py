from __future__ import annotations

import ast
import hashlib
import json
import re
from pathlib import Path
from typing import Any

import pytest
from tools.source_scope_provenance import registered_provenance_text

from warhammer40k_core.engine.faction_content.warhammer_40000_11th.chaos_daemons import (
    datasheets as chaos_daemons_datasheets,
)
from warhammer40k_core.rules.source_packages.warhammer_40000_11th import (
    chaos_daemons_roster_2026_07,
)

ROOT = Path(__file__).resolve().parents[2]
THIS_FILE = Path(__file__).resolve()
HEX_DIGEST_PATTERN = re.compile(r"\b[0-9a-fA-F]{32,}\b")
UUID_PATTERN = re.compile(r"\b[0-9a-fA-F]{8}-(?:[0-9a-fA-F]{4}-){3}[0-9a-fA-F]{12}\b")
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
    ROOT / "src" / "warhammer40k_core" / "rules" / "source_authority_registry.json",
    ROOT / "data" / "source_audits" / "maintained_app_mirrors" / "core_rules_2026_09_02.audit.json",
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
    / "core_stratagems_2026_08"
    / "artifacts"
    / "package.json",
    ROOT
    / "src"
    / "warhammer40k_core"
    / "rules"
    / "source_packages"
    / "warhammer_40000_11th"
    / "core_command_phase_2026_08"
    / "artifacts"
    / "package.json",
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
IMMUTABLE_LEGACY_OBSERVATION_IDS = frozenset(
    {
        "40k-app-attached-units-2026-09-01:bodyguard-unit-destroyed",
        "40k-app-attack-sequence-2026-09-01:destroyed",
        "40k-app-command-phase-search-index-2026-08-26:battle-shock",
        "40k-app-command-phase-search-index-2026-08-26:gain-core-cp",
        "40k-app-command-phase-search-index-2026-08-26:start-of-command-phase",
        "40k-app-core-rules-2026-08-25:01.02.03-embarked-model-return",
        "40k-app-core-rules-2026-08-25:05.03.02-post-roll-attack-profiles",
        "40k-app-core-rules-2026-08-25:05.04.05-fight-on-death",
        "40k-app-core-rules-2026-08-25:09-normal-move-one-per-phase",
        "40k-app-core-rules-2026-08-25:09.07.01-desperate-escape-definition",
        "40k-app-core-rules-2026-08-25:09.07.01-forced-desperate-escape",
        "40k-app-core-rules-2026-08-25:12.08-objective-consolidation",
        "40k-app-core-rules-2026-08-25:13.09-hidden",
        "40k-app-core-rules-2026-08-25:14.02.01-control-first",
        "40k-app-core-rules-2026-08-25:18.01-dedicated-transport",
        "40k-app-core-rules-2026-08-25:20.01.02-strategic-reserves",
        "40k-app-core-rules-2026-08-25:24.28.01-precision-devastating-wounds",
        "40k-app-core-rules-2026-08-25:24.37.01-torrent",
        "40k-app-core-rules-2026-08-25:25.04-epic-hero-enhancements",
        "40k-app-core-rules-2026-08-25:25.04-incursion-detachment",
        "40k-app-core-rules-2026-08-25:faq-hazardous-mixed-unit-keywords",
        "40k-app-core-rules-2026-08-25:faq-heavy-fly-horizontal-distance",
        "40k-app-core-stratagems-2026-08-26:crushing-impact",
        "40k-app-core-stratagems-2026-08-26:explosives",
        "40k-app-core-stratagems-2026-08-26:fire-overwatch",
        "40k-app-core-stratagems-2026-08-26:rapid-ingress",
        "40k-app-core-stratagems-2026-08-26:snap-shooting",
        "40k-app-movement-phase-2026-08-30:fall-back-move",
        "40k-app-movement-phase-2026-08-30:move-units-step",
        "40k-app-movement-phase-2026-08-30:selecting-modes",
        "40k-app-other-concepts-2026-08-31:mortal-wounds",
        "40k-app-other-concepts-2026-08-31:visibility",
        "40k-app-transports-2026-09-01:emergency-disembark-move",
    }
)
IMMUTABLE_LEGACY_OBSERVATION_INVENTORY_SHA256 = (
    "19a15062c806e2776dec3d7e71d165a62a1348162b8b42f7c9c1cab89338170a"
)


def test_s_mirrors_policy_and_static_provider_inventory_remain_complete() -> None:
    policy = (ROOT / "docs" / "CORE_RULES_SOURCE_POLICY.md").read_text(encoding="utf-8")
    source_evidence = (
        ROOT / "src" / "warhammer40k_core" / "rules" / "source_evidence.py"
    ).read_text(encoding="utf-8")
    source_authority_registry = (
        ROOT / "src" / "warhammer40k_core" / "rules" / "source_authority_registry.py"
    ).read_text(encoding="utf-8")
    authority_registry_payload = json.loads(
        (ROOT / "src" / "warhammer40k_core" / "rules" / "source_authority_registry.json").read_text(
            encoding="utf-8"
        )
    )
    audit = json.loads(
        (
            ROOT
            / "data"
            / "source_audits"
            / "maintained_app_mirrors"
            / "core_rules_2026_09_02.audit.json"
        ).read_text(encoding="utf-8")
    )

    current_policy_id = "core-rules-source-policy:maintained-direct-app-data-mirrors:2026-09-02"
    assert current_policy_id in policy
    assert "co-versioned 40k.app and Game Datamissions observations disagree" in policy
    assert "provider wins by preference" in policy
    assert {provider["provider_name"] for provider in audit["providers"]} == {
        "40k.app",
        "Game Datamissions",
    }
    assert all(not provider["owned_by_games_workshop"] for provider in audit["providers"])
    assert current_policy_id in source_authority_registry
    assert "authorize_audit_reference" in source_evidence
    assert "authorize_source_package" in source_evidence
    assert "supplied_source_ids == registered_source_ids" in source_authority_registry
    assert "Co-versioned maintained App mirrors disagree" in source_evidence
    scope = authority_registry_payload["scopes"][0]
    assert scope["scope_id"] == "warhammer_40000_11th_core_rules"
    assert scope["edition"] == "warhammer_40000_11th"
    assert scope["corpus"] == "core_rules_categories_01_25"
    assert set(scope["policy_ids"]) == {
        current_policy_id,
        "core-rules-source-policy:40k-app-verbatim-official-app-mirror:2026-08-26",
    }
    assert len(scope["legacy_observations"]) == 33
    assert len(scope["source_packages"]) == 54


def test_superseded_mirror_policy_legacy_observation_inventory_is_immutable() -> None:
    authority_registry_payload = json.loads(
        (ROOT / "src" / "warhammer40k_core" / "rules" / "source_authority_registry.json").read_text(
            encoding="utf-8"
        )
    )
    scope = authority_registry_payload["scopes"][0]
    legacy_observation_ids = frozenset(
        observation["evidence_id"] for observation in scope["legacy_observations"]
    )
    legacy_observation_inventory = tuple(
        sorted(
            (
                observation["evidence_id"],
                observation["rule_source_id"],
                observation["observation_sha256"],
            )
            for observation in scope["legacy_observations"]
        )
    )
    inventory_sha256 = hashlib.sha256(
        json.dumps(legacy_observation_inventory, separators=(",", ":")).encode()
    ).hexdigest()

    assert legacy_observation_ids == IMMUTABLE_LEGACY_OBSERVATION_IDS
    assert inventory_sha256 == IMMUTABLE_LEGACY_OBSERVATION_INVENTORY_SHA256
    assert all(evidence_id.startswith("40k-app-") for evidence_id in legacy_observation_ids)


@pytest.mark.parametrize(
    "identity",
    [
        "aab10e23-6433-42ca-86e7-ddc829f16c47",
        "c2df3e97-f21e-4fc9-943e-37072c08c10e",
        "AAB10E23-6433-42CA-86E7-DDC829F16C47",
        "aab10e23643342ca86e7ddc829f16c47",
    ],
)
def test_edition_audit_ignores_opaque_hex_identity_but_preserves_real_tokens(
    identity: str,
) -> None:
    tokens = _retired_identity_tokens()
    text = f"faq:{identity}-obligation-01 " + " ".join(tokens)
    sanitized = _without_hex_identities(text)
    assert identity not in sanitized
    assert "faq:-obligation-01" in sanitized
    assert all(token in sanitized for token in tokens)


def test_edition_audit_does_not_exempt_malformed_uuid() -> None:
    text = "faq:aab10e23-6433-42ca-86e7-ddc829f16c4z"
    assert _without_hex_identities(text) == text
    assert "10e" in _without_hex_identities(text)


def test_edition_audit_recognizes_the_exact_quoted_phase_test_filename() -> None:
    reference = "tests/unit/test_phase10e_model_geometry.py"
    assert (ROOT / reference).is_file()
    tokens = _retired_identity_tokens()
    text = json.dumps(reference) + " " + " ".join(tokens)

    sanitized = _without_non_edition_references(text)

    assert json.dumps(reference) not in sanitized
    assert all(token in sanitized for token in tokens)


@pytest.mark.parametrize(
    "reference",
    [
        '"prefix/tests/unit/test_phase10e_model_geometry.py"',
        '"tests/unit/test_phase10e_model_geometry.py.extra"',
        '"tests/unit/test_phase10e_other_geometry.py"',
        '"src/unit/test_phase10e_model_geometry.py"',
        "tests/unit/test_phase10e_model_geometry.py",
    ],
)
def test_edition_audit_does_not_exempt_near_miss_phase_references(reference: str) -> None:
    assert _without_non_edition_references(reference) == reference
    assert "10e" in _without_non_edition_references(reference)


def test_active_code_tests_and_docs_do_not_reference_retired_edition_ids() -> None:
    violations: list[str] = []

    for path in _scanned_paths():
        text = _without_non_edition_references(_active_identity_text(path))
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
    source = _without_hex_identities(CHAOS_DAEMONS_DATASHEET_RUNTIME.read_text(encoding="utf-8"))
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


def _without_hex_identities(text: str) -> str:
    return HEX_DIGEST_PATTERN.sub("", UUID_PATTERN.sub("", text))


def _without_non_edition_references(text: str) -> str:
    # This existing Phase10E test path is provenance, not an edition identifier.
    # Only its complete quoted spelling is recognized; adjacent tokens stay visible.
    phase_reference = '"tests/unit/test_phase10e_model_geometry.py"'
    return _without_hex_identities(text).replace(phase_reference, '""')


VYPER_CURRENT_COMPARISON = "docs/performance/current/vyper-source-bc9-v4.json"
VYPER_ARCHIVED_COMPARISON = "docs/performance/evidence/vyper-source-c58420d7-comparison.json"
VYPER_ROLE_SPEC = "docs/performance/policy-v3/vyper-source-input-roles-v4.json"
VYPER_OVERLAY = (
    "src/warhammer40k_core/rules/source_packages/warhammer_40000_11th/"
    "aeldari_vyper_title_2026_10.overlay-pack.json"
)
VYPER_BEHAVIORAL_TEST = "tests/rules/section25/test_mfm.py"
VYPER_PROVENANCE_DOCUMENT_SHA256 = {
    VYPER_ARCHIVED_COMPARISON: "36ae186f7dd74899ce437f90aceb5e7940d0797d23a1cc621a39e8e8183fac3b",
    VYPER_ROLE_SPEC: "76d0e3bc6cd71c5205cabf30c990f16bf190632953d5fec2978ac660abb7c37f",
    VYPER_OVERLAY: "ae4416a45ddddbcf9784123ee25c60113e71249eae699431b36655fbd9e663f3",
    VYPER_BEHAVIORAL_TEST: "6d2758590363c16f2f72048780631028cf67cc59e297740ca96b5f5c93e5696a",
}
HISTORICAL_SNAPSHOT_PATHS = (
    "data/source_snapshots/wahapedia/10th-edition/2026-06-14/json/Abilities.json",
    "data/source_snapshots/wahapedia/10th-edition/2026-06-14/json/Datasheets.json",
    "data/source_snapshots/wahapedia/10th-edition/2026-06-14/json/Datasheets_abilities.json",
    "data/source_snapshots/wahapedia/10th-edition/2026-06-14/json/Datasheets_detachment_abilities.json",
    "data/source_snapshots/wahapedia/10th-edition/2026-06-14/json/Datasheets_enhancements.json",
    "data/source_snapshots/wahapedia/10th-edition/2026-06-14/json/Datasheets_keywords.json",
    "data/source_snapshots/wahapedia/10th-edition/2026-06-14/json/Datasheets_leader.json",
    "data/source_snapshots/wahapedia/10th-edition/2026-06-14/json/Datasheets_models.json",
    "data/source_snapshots/wahapedia/10th-edition/2026-06-14/json/Datasheets_models_cost.json",
    "data/source_snapshots/wahapedia/10th-edition/2026-06-14/json/Datasheets_options.json",
    "data/source_snapshots/wahapedia/10th-edition/2026-06-14/json/Datasheets_stratagems.json",
    "data/source_snapshots/wahapedia/10th-edition/2026-06-14/json/Datasheets_unit_composition.json",
    "data/source_snapshots/wahapedia/10th-edition/2026-06-14/json/Datasheets_wargear.json",
    "data/source_snapshots/wahapedia/10th-edition/2026-06-14/json/Detachment_abilities.json",
    "data/source_snapshots/wahapedia/10th-edition/2026-06-14/json/Detachments.json",
    "data/source_snapshots/wahapedia/10th-edition/2026-06-14/json/Enhancements.json",
    "data/source_snapshots/wahapedia/10th-edition/2026-06-14/json/Factions.json",
    "data/source_snapshots/wahapedia/10th-edition/2026-06-14/json/Last_update.json",
    "data/source_snapshots/wahapedia/10th-edition/2026-06-14/json/Source.json",
    "data/source_snapshots/wahapedia/10th-edition/2026-06-14/json/Stratagems.json",
    "data/source_snapshots/wahapedia/10th-edition/2026-06-14/json/source_package_manifest.json",
    "data/source_snapshots/wahapedia/10th-edition/2026-06-14/raw/source_snapshot.json",
)
HISTORICAL_SNAPSHOT_INVENTORY_SHA256 = (
    "b877588db3f751f764fb74e9b9d5a1e3c3ab2525480e2954d2598520492b3557"
)
HISTORICAL_VYPER_SOURCE_ID = (
    "data-package:wahapedia:source-mirror:10th-edition-2026-06-14:Datasheets:000000605"
)


def _historical_snapshot_inputs() -> dict[str, str]:
    """Authenticate the closed original source inventory before exempting its keys."""
    observed = {
        relative: hashlib.sha256((ROOT / relative).read_bytes()).hexdigest()
        for relative in HISTORICAL_SNAPSHOT_PATHS
    }
    digest = hashlib.sha256(
        json.dumps(observed, sort_keys=True, separators=(",", ":")).encode()
    ).hexdigest()
    assert digest == HISTORICAL_SNAPSHOT_INVENTORY_SHA256, "Historical snapshot bytes drifted."
    return observed


def _unique_provenance_object(pairs: list[tuple[str, object]]) -> dict[str, object]:
    result: dict[str, object] = {}
    for key, value in pairs:
        assert key not in result, "Duplicate provenance JSON member."
        result[key] = value
    return result


def _v4_provenance_text(report: dict[str, Any], historical: dict[str, str]) -> str:
    """Remove authenticated inventory keys only; every other value remains scanned."""
    assert report["policy"] == "rules-engine-performance-v3"
    assert report["family"] == "external_contract_source_reuse"
    assert report["base_revision"] == "bc9acd8419e7b97a2c1260c7e932d2cb9c3fc370"
    binding = report["input_binding"]
    assert binding["schema"] == "tool-input-roles-v4"
    assert binding["family"] == "external_contract_source_reuse"
    assert binding["sides"]["base"]["revision"] == report["base_revision"]
    for inventory in (
        binding["common"],
        binding["sides"]["base"]["inventory"],
        binding["sides"]["head"]["inventory"],
    ):
        for relative, expected in historical.items():
            assert inventory.get(relative) == expected, "Historical inventory path/hash drifted."
            del inventory[relative]
    return json.dumps(report)


def _vyper_provenance_text(path: Path, raw: bytes) -> str:
    relative = path.relative_to(ROOT).as_posix()
    if relative != VYPER_CURRENT_COMPARISON:
        assert hashlib.sha256(raw).hexdigest() == VYPER_PROVENANCE_DOCUMENT_SHA256[relative], (
            "Vyper provenance document requires its exact reviewed bytes."
        )
    if relative == VYPER_BEHAVIORAL_TEST:
        # The complete test is pinned. Only its one historical source-membership
        # assertion literal is removed; all active source identities stay visible.
        literal = json.dumps(HISTORICAL_VYPER_SOURCE_ID)
        text = raw.decode("utf-8")
        assert text.count(literal) == 1
        return text.replace(literal, '""')
    value = json.loads(raw, object_pairs_hook=_unique_provenance_object)
    if relative in {VYPER_CURRENT_COMPARISON, VYPER_ARCHIVED_COMPARISON}:
        return _v4_provenance_text(value, _historical_snapshot_inputs())
    if relative == VYPER_ROLE_SPEC:
        assert value["schema"] == "tool-input-roles-v4"
        required = value["required_dependencies"]
        historical = _historical_snapshot_inputs()
        for name in (
            "Abilities.json",
            "Datasheets.json",
            "Datasheets_abilities.json",
            "Datasheets_keywords.json",
            "Datasheets_leader.json",
        ):
            reference = "data/source_snapshots/wahapedia/10th-edition/2026-06-14/json/" + name
            assert reference in historical
            assert required.count(reference) == 1
            required.remove(reference)
    else:
        assert relative == VYPER_OVERLAY
        assert value["schema_version"] == "phase17-source-overlay-v1"
        assert value["target_edition"] == "warhammer-40000-11th"
        package = value["base_source_package_id"]
        assert package == {
            "namespace": "wahapedia",
            "package_name": "source-mirror",
            "version": "10th-edition-2026-06-14",
        }
        del package["version"]
    return json.dumps(value)


def _active_identity_text(path: Path) -> str:
    """Keep exact historical hash-map keys distinct from active edition identities."""
    raw = path.read_bytes()
    registered = registered_provenance_text(ROOT, path, raw, _historical_snapshot_inputs)
    if registered is not None:
        return registered
    if path in {
        ROOT / VYPER_CURRENT_COMPARISON,
        *(ROOT / relative for relative in VYPER_PROVENANCE_DOCUMENT_SHA256),
    }:
        return _vyper_provenance_text(path, raw)
    if path != ROOT / "docs/performance/current/source-token-reuse-v2.json":
        return raw.decode("utf-8")
    assert hashlib.sha256(raw).hexdigest() == (
        "8cad88b88cac094de6b8bffc2c6a365b36e9c17c86705fe7621edcc8c4240fdc"
    ), "The historical input-hash report requires its exact reviewed bytes."
    report = json.loads(raw)
    common = report["input_binding"]["common"]
    prefix = "data/source_snapshots/wahapedia/10th-edition/2026-06-14/json/"
    historical = {
        "Abilities.json": "ad836ea16f2e2e1b5ab64a03e6731ad99a2d27994ab01c0df01ec267c71ea39c",
        "Datasheets.json": "f99c8ac2d4dcfcaf809689d1dac6dc277fa74f0e52efb0e0efd5093aef823b32",
        "Datasheets_abilities.json": (
            "45e1eb1fb71438d1e2a9d4d916184083a3e5f397b1e3a2d1c1ff1eb77ddd4a01"
        ),
        "Datasheets_keywords.json": (
            "697a2656222bf4dfd1f933f2e8bfd4dff0b37ed19abdd3f8e345b3afe2540531"
        ),
        "Datasheets_leader.json": (
            "6dcc73d4706fa32675fe77b83532cc573cd96e8196e9c7b7e8097b96e3c2fc68"
        ),
    }
    for name, digest in historical.items():
        assert common.pop(prefix + name) == digest
    # Only those five keys in the authenticated common inventory are removed.
    # Every other field and occurrence is still checked; the report is never rewritten.
    return json.dumps(report)


def test_historical_report_keys_are_scoped_to_exact_reviewed_document() -> None:
    path = ROOT / "docs/performance/current/source-token-reuse-v2.json"
    before = path.read_bytes()
    observed = _active_identity_text(path)
    assert not any(
        token in _without_non_edition_references(observed) for token in _retired_identity_tokens()
    )
    assert path.read_bytes() == before


@pytest.mark.parametrize("mutation", ["key", "digest", "adjacent_identity"])
def test_historical_report_identity_exception_rejects_any_byte_drift(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, mutation: str
) -> None:
    relative = "docs/performance/current/source-token-reuse-v2.json"
    report = json.loads((ROOT / relative).read_bytes())
    key = next(k for k in report["input_binding"]["common"] if "10th-edition" in k)
    if mutation == "key":
        value = report["input_binding"]["common"].pop(key)
        report["input_binding"]["common"][key + ".extra"] = value
    elif mutation == "digest":
        report["input_binding"]["common"][key] = "f" * 64
    else:
        report["new_runtime_edition"] = _retired_identity_tokens()[0]
    path = tmp_path / relative
    path.parent.mkdir(parents=True)
    path.write_text(json.dumps(report), encoding="utf-8")
    monkeypatch.setattr(f"{__name__}.ROOT", tmp_path)
    with pytest.raises(AssertionError, match="exact reviewed bytes"):
        _active_identity_text(path)


def test_historical_report_does_not_exempt_other_active_documents(tmp_path: Path) -> None:
    path = tmp_path / "other.json"
    raw = (ROOT / "docs/performance/current/source-token-reuse-v2.json").read_bytes()
    path.write_bytes(raw)
    assert _active_identity_text(path) == raw.decode("utf-8")
    assert "10th" in _active_identity_text(path)


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


@pytest.mark.parametrize(
    "relative",
    [
        VYPER_CURRENT_COMPARISON,
        VYPER_ARCHIVED_COMPARISON,
        VYPER_ROLE_SPEC,
        VYPER_OVERLAY,
        VYPER_BEHAVIORAL_TEST,
    ],
)
def test_vyper_provenance_preserves_exact_historical_bytes_and_active_identity(
    relative: str,
) -> None:
    path = ROOT / relative
    raw = path.read_bytes()
    text = _without_non_edition_references(_active_identity_text(path))
    assert not any(token in text for token in _retired_identity_tokens())
    assert path.read_bytes() == raw


@pytest.mark.parametrize("relative", list(VYPER_PROVENANCE_DOCUMENT_SHA256))
@pytest.mark.parametrize("mutation", ["byte_drift", "active_identity"])
def test_vyper_pinned_provenance_rejects_any_document_drift(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, relative: str, mutation: str
) -> None:
    raw = (ROOT / relative).read_bytes()
    raw += b"\n" if mutation == "byte_drift" else b"\nwarhammer_40000_10th\n"
    path = tmp_path / relative
    path.parent.mkdir(parents=True)
    path.write_bytes(raw)
    monkeypatch.setattr(f"{__name__}.ROOT", tmp_path)
    with pytest.raises(AssertionError, match="exact reviewed bytes"):
        _active_identity_text(path)


@pytest.mark.parametrize("context", ["common", "base", "head"])
@pytest.mark.parametrize("mutation", ["path", "digest", "missing"])
def test_v4_historical_inventory_authenticates_every_allowed_context(
    context: str, mutation: str
) -> None:
    report = json.loads((ROOT / VYPER_CURRENT_COMPARISON).read_bytes())
    historical = _historical_snapshot_inputs()
    binding = report["input_binding"]
    inventory = binding["common"] if context == "common" else binding["sides"][context]["inventory"]
    key = next(iter(historical))
    if mutation == "digest":
        inventory[key] = "f" * 64
    else:
        value = inventory.pop(key)
        if mutation == "path":
            inventory[key + ".extra"] = value
    with pytest.raises(AssertionError, match="Historical inventory path/hash drifted"):
        _v4_provenance_text(report, historical)


@pytest.mark.parametrize(
    "context", ["top", "binding", "side", "wrong_slot", "near_path", "adjacent"]
)
def test_v4_provenance_does_not_hide_active_or_unknown_contexts(context: str) -> None:
    report = json.loads((ROOT / VYPER_CURRENT_COMPARISON).read_bytes())
    historical = _historical_snapshot_inputs()
    binding = report["input_binding"]
    key = next(iter(historical))
    token = "warhammer_40000_10th"
    if context == "top":
        report["active_edition"] = token
    elif context == "binding":
        binding["active_edition"] = token
    elif context == "side":
        binding["sides"]["head"]["active_edition"] = token
    elif context == "wrong_slot":
        report["active_source"] = key
    elif context == "near_path":
        binding["common"][key + ".extra"] = historical[key]
    else:
        report["description"] = key + " " + token
    text = _without_non_edition_references(_v4_provenance_text(report, historical))
    assert "10th" in text


@pytest.mark.parametrize("member", ["policy", "family", "base_revision", "schema"])
def test_v4_provenance_rejects_different_report_identity(member: str) -> None:
    report = json.loads((ROOT / VYPER_CURRENT_COMPARISON).read_bytes())
    if member == "schema":
        report["input_binding"][member] = "arbitrary-schema"
    else:
        report[member] = "arbitrary-identity"
    with pytest.raises(AssertionError):
        _v4_provenance_text(report, _historical_snapshot_inputs())


def test_v4_provenance_rejects_duplicate_json_members() -> None:
    raw = '{"active_edition":"warhammer_40000_10th","active_edition":"warhammer_40000_11th"}'
    with pytest.raises(AssertionError, match="Duplicate provenance JSON member"):
        json.loads(raw, object_pairs_hook=_unique_provenance_object)


def test_vyper_provenance_does_not_exempt_another_document(tmp_path: Path) -> None:
    path = tmp_path / "other.json"
    raw = (ROOT / VYPER_CURRENT_COMPARISON).read_bytes()
    path.write_bytes(raw)
    assert _active_identity_text(path) == raw.decode()
    assert "10th" in _active_identity_text(path)


def test_vyper_provenance_requires_immutable_snapshot_bytes(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    for relative in HISTORICAL_SNAPSHOT_PATHS:
        path = tmp_path / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(b"changed historical source")
    monkeypatch.setattr(f"{__name__}.ROOT", tmp_path)
    with pytest.raises(AssertionError, match="Historical snapshot bytes drifted"):
        _historical_snapshot_inputs()
