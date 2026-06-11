from __future__ import annotations

from pathlib import Path

from warhammer40k_core.rules.source_packages.warhammer_40000_11th import (
    faction_detachments_2026_27 as faction_detachment_source,
)

ROOT = Path(__file__).resolve().parents[2]
FACTION_INTEGRATION_PATH = ROOT / "FACTION_INTEGRATION.md"


def test_faction_integration_queue_source_matches_seed_package_metadata() -> None:
    document = FACTION_INTEGRATION_PATH.read_text(encoding="utf-8")
    identity = faction_detachment_source.source_package_identity_payload()

    assert "## Queue Source" in document
    assert identity["source_package_id"] in document
    assert (
        "src/warhammer40k_core/rules/source_packages/warhammer_40000_11th/"
        "faction_detachments_2026_27.py"
    ) in document
    assert identity["source_title"] in document
    assert identity["source_version"] in document
    assert identity["source_date"] in document
    assert identity["upstream_identity"] in document
    assert f"source edition: `{identity['source_edition']}`" in document
    assert identity["imported_at_schema_version"] in document
    assert identity["source_payload_checksum_sha256"] in document
    assert "source_package_identity_payload()" in document
    assert "Queue refreshes must be generated from this package" in document


def test_faction_integration_preserves_verified_upstream_spelling_drift() -> None:
    document = FACTION_INTEGRATION_PATH.read_text(encoding="utf-8")
    rows_by_source_id = {row.source_id: row for row in faction_detachment_source.detachment_rows()}

    tau_row = rows_by_source_id[
        "gw-11e-faction-detachments-2026-27:detachment:tau-empire:auxillary-cadre"
    ]
    cult_row = rows_by_source_id[
        "gw-11e-faction-detachments-2026-27:detachment:genestealer-cults:brood-brothers-auxillia"
    ]

    assert tau_row.name == "Auxillary Cadre"
    assert cult_row.name == "Brood Brothers Auxillia"
    assert "Names in this queue preserve upstream source-row spelling exactly" in document
    assert tau_row.name in document
    assert cult_row.name in document
    assert tau_row.source_id in document
    assert cult_row.source_id in document
    assert "source-linked patch operations" in document
    assert "not silent edits" in document


def test_faction_integration_requires_explicit_faq_classification_gate() -> None:
    document = FACTION_INTEGRATION_PATH.read_text(encoding="utf-8")

    assert "## FAQ Classification Gate" in document
    assert "`advisory_only`" in document
    assert "`executable_patch`" in document
    assert "`unsupported_executable_change`" in document
    assert "FAQs that change gameplay semantics must not be stored as `advisory_only`" in document
    assert "Plagueburst Crawler FAQ advisory record" in document
