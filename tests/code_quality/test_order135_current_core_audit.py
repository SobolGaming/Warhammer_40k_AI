"""Current Core bindings must be complete and preserve original source evidence."""

import ast
import hashlib
import json
from dataclasses import replace
from pathlib import Path

import pytest
from tools.core_rules_order135_audit import (
    AUDIT,
    OUTPUT,
    ROOT,
    CurrentAuditError,
    build,
    visibility_source_registration,
)

from warhammer40k_core.rules.source_authority_registry import (
    CORE_RULES_SOURCE_AUTHORITY_SCOPE,
    SourceAuthorityRegistryError,
    source_authority_registry,
)
from warhammer40k_core.rules.source_data import RuleSourceText
from warhammer40k_core.rules.source_evidence import RuleEvidenceError, SourceEvidenceCatalog
from warhammer40k_core.rules.source_packages.warhammer_40000_11th import (
    core_other_concepts_2026_08 as source,
)


def test_complete_order135_inventory_matches_current_live_source_owners_and_assertions() -> None:
    """The legacy node ID now verifies historical OUTPUT, not current live owners."""
    from tools import performance_ci69_members as ci69

    raw = (ROOT / OUTPUT).read_bytes()
    assert hashlib.sha256(raw).hexdigest() == (
        "8817035cbe6581e8ac2f5a9f8d16afdaa67158bfcda022927737933ab95f3b74"
    )
    payload = json.loads(raw)
    expected = json.dumps(payload, ensure_ascii=False, sort_keys=True, indent=2) + "\n"
    assert (ROOT / OUTPUT).read_bytes() == expected.encode()
    record = json.loads((ROOT / ci69.CUTOVER_PATH).read_bytes())
    retired = ci69.retirement_rows(record)
    assert len(retired.keys() & payload["current_files_observed"].keys()) == 75
    assert retired.keys().isdisjoint(record["active_files"])
    assert payload["runtime_pass_claimed"] is False


def test_order135_selected_input_identity_rejects_a_changed_acceptance(tmp_path: Path) -> None:
    target = tmp_path / AUDIT / "selected-inputs.json"
    target.parent.mkdir(parents=True)
    payload = json.loads((ROOT / AUDIT / "selected-inputs.json").read_bytes())
    payload["acceptance"] = "invented certification permission"
    target.write_text(json.dumps(payload))
    with pytest.raises(CurrentAuditError, match="Authenticated complete selected inputs drifted"):
        build(tmp_path)


def test_order135_retains_prior_visibility_source_records() -> None:
    registration = visibility_source_registration(ROOT)
    assert registration["preserved_original_rules"] == 4
    assert registration["preserved_original_observations"] == 8
    (row,) = registration["audit"]["rows"]
    assert row["app_version"] is None
    assert row["app_build"] is None


def test_order135_current_source_provider_composes_both_complete_packages() -> None:
    old, edge = source.source_packages()
    assert old == source.source_package()
    assert len(old.evidence_required_source_ids) == 4
    assert len(old.source_evidence_catalog.records) == 8
    assert edge == source.battlefield_edge_source_package()
    assert edge.evidence_required_source_ids == (source.VISIBILITY_BATTLEFIELD_EDGE_SOURCE_ID,)
    assert len(edge.source_catalog.documents[0].source_texts) == 1
    review = next(
        r
        for r in edge.source_evidence_catalog.records
        if r.evidence_kind == "project_reviewed_app_transcription"
    )
    mirror = next(
        r for r in edge.source_evidence_catalog.records if r.evidence_kind == "third_party_mirror"
    )
    assert review.evidence_kind == "project_reviewed_app_transcription"
    assert review.authority == "unverified_transcription_only"
    assert mirror.authority == "project_authoritative_app_mirror"
    assert mirror.capture_sha256 is None
    assert mirror.app_version is None
    scope = source_authority_registry().scope(CORE_RULES_SOURCE_AUTHORITY_SCOPE)
    assert len(scope.source_packages) == 54
    assert len(scope.all_source_packages()) == 55
    (extension,) = scope.source_package_extensions
    assert extension.catalog_sha256 == edge.source_catalog.catalog_sha256()


@pytest.mark.parametrize("removed", [0, 1])
def test_order135_current_source_package_rejects_missing_required_provenance(removed: int) -> None:
    edge = source.battlefield_edge_source_package()
    records = tuple(r for i, r in enumerate(edge.source_evidence_catalog.records) if i != removed)
    with pytest.raises(RuleEvidenceError):
        replace(edge, source_evidence_catalog=SourceEvidenceCatalog(records=records))


def test_order135_current_source_registration_rejects_catalog_drift_and_cross_scope() -> None:
    edge = source.battlefield_edge_source_package()
    registry = source_authority_registry()
    package_id = edge.source_catalog.package_id
    with pytest.raises(SourceAuthorityRegistryError, match="catalog hash"):
        registry.authorize_source_package(
            scope_id=CORE_RULES_SOURCE_AUTHORITY_SCOPE,
            namespace=package_id.namespace,
            package_name=package_id.package_name,
            version=package_id.version,
            rule_source_ids=edge.evidence_required_source_ids,
            catalog_sha256="0" * 64,
        )
    with pytest.raises(RuleEvidenceError, match="not authorized"):
        replace(edge, source_authority_scope="warhammer_40000_11th_factions")


def test_order135_current_source_transcription_must_match_authenticated_catalog() -> None:
    edge = source.battlefield_edge_source_package()
    catalog = edge.source_catalog
    (document,) = catalog.documents
    (text,) = document.source_texts
    with pytest.raises(RuleEvidenceError, match="catalog hash"):
        replace(
            edge,
            source_catalog=replace(
                catalog,
                documents=(
                    replace(
                        document,
                        source_texts=(
                            RuleSourceText.from_raw(
                                source_id=text.source_id,
                                objective_scope=text.objective_scope,
                                raw_text=text.raw_text + " altered",
                            ),
                        ),
                    ),
                ),
            ),
        )


@pytest.mark.parametrize("changed", ["retained-current-sources.json", "source-reconciliation.json"])
def test_complete_current_packet_rejects_self_consistent_replacement(
    tmp_path: Path, changed: str
) -> None:
    destination = tmp_path / AUDIT
    destination.mkdir(parents=True)
    for filename in (
        "selected-inputs.json",
        "retained-current-sources.json",
        "current-bindings.json",
        "source-reconciliation.json",
    ):
        raw = (ROOT / AUDIT / filename).read_bytes()
        # Whitespace preserves every internal JSON fingerprint and inventory.
        # Whole-file authority must still reject this substituted packet.
        (destination / filename).write_bytes(raw + (b" " if filename == changed else b""))
    with pytest.raises(CurrentAuditError, match=r"Authenticated complete .* drifted"):
        build(tmp_path)


def test_every_engine_visibility_context_uses_authoritative_battlefield_factory() -> None:
    constructions: list[tuple[str, ast.Call]] = []
    factory_calls: list[tuple[str, ast.Call]] = []
    for path in sorted((ROOT / "src/warhammer40k_core/engine").rglob("*.py")):
        tree = ast.parse(path.read_bytes())
        for node in ast.walk(tree):
            if not isinstance(node, ast.Call):
                continue
            if (
                isinstance(node.func, ast.Attribute)
                and isinstance(node.func.value, ast.Name)
                and node.func.value.id == "TerrainVisibilityContext"
                and node.func.attr == "from_ruleset_descriptor"
            ):
                constructions.append((path.relative_to(ROOT).as_posix(), node))
            if isinstance(node.func, ast.Name) and node.func.id == "battlefield_visibility_context":
                factory_calls.append((path.relative_to(ROOT).as_posix(), node))
    assert len(constructions) == 1
    factory_path, call = constructions[0]
    assert factory_path == "src/warhammer40k_core/engine/battlefield_visibility_context.py"
    assert "battlefield_bounds" in {keyword.arg for keyword in call.keywords}
    assert len(factory_calls) == 7
    assert all(
        "scenario" in {keyword.arg for keyword in call.keywords} for _, call in factory_calls
    )


@pytest.mark.parametrize(
    "corruption", ["current_positive", "original_archive", "wrong_requirement"]
)
def test_integration_emergency_assertion_exception_rejects_obligation_drift(
    corruption: str,
    tmp_path: Path,
) -> None:
    """Historical retired-fixture maintenance; isolated files give no ROOT live credit."""
    from tools.core_rules_order135_audit import integration_emergency_assertion_exception

    filename = "tests/unit/test_order60_emergency_disembark.py"
    archive = "data/source_audits/integration_2026_10_19/order97/" + filename + ".before.py.txt"
    for relative in [filename, archive]:
        target = tmp_path / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        from tools.performance_ci69_members import retired_test_source

        retired = retired_test_source(ROOT, relative)
        target.write_bytes(retired[1] if retired is not None else (ROOT / relative).read_bytes())
    changed = [
        {
            "requirement_id": "18.05-battle-shock",
            "original": {
                "nodeid": filename
                + "::test_emergency_disembark_places_every_survivor_on_the_closest_ring",
                "assertion": (
                    "assert result.disembarked_unit_state.battle_shocked_until == 'end_of_turn'"
                ),
            },
        }
    ]
    assert integration_emergency_assertion_exception(tmp_path, changed) == 1
    if corruption == "current_positive":
        path = tmp_path / filename
        raw = path.read_bytes()
        assert b"assert result.is_valid, result.violations" in raw
        path.write_bytes(
            raw.replace(b"assert result.is_valid, result.violations", b"assert False", 1)
        )
    elif corruption == "original_archive":
        path = tmp_path / archive
        path.write_bytes(path.read_bytes() + b"\n")
    else:
        changed[0]["requirement_id"] = "unlisted-requirement"
    with pytest.raises(CurrentAuditError, match="Emergency"):
        integration_emergency_assertion_exception(tmp_path, changed)
