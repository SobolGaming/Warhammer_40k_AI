from __future__ import annotations

from pathlib import Path

from warhammer40k_core.rules.source_packages.warhammer_40000_11th import (
    faction_coverage_2026_27 as faction_coverage_source,
)
from warhammer40k_core.rules.source_packages.warhammer_40000_11th import (
    faction_detachments_2026_27 as faction_detachment_source,
)
from warhammer40k_core.rules.source_packages.warhammer_40000_11th import (
    faction_execution_2026_27 as faction_execution_source,
)
from warhammer40k_core.rules.source_packages.warhammer_40000_11th.faction_coverage_2026_27 import (
    Phase17ECoverageKind,
)
from warhammer40k_core.rules.source_packages.warhammer_40000_11th.faction_execution_2026_27 import (
    Phase17FExecutionRecord,
    Phase17FExecutionStatus,
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
    assert "Names in this queue preserve the package's normalized source-row spelling exactly" in (
        document
    )
    assert tau_row.name in document
    assert cult_row.name in document
    assert tau_row.source_id in document
    assert cult_row.source_id in document
    assert "source-linked patch operations" in document
    assert "not silent edits" in document


def test_faction_integration_queue_lists_every_seeded_faction_and_detachment() -> None:
    document = FACTION_INTEGRATION_PATH.read_text(encoding="utf-8")
    normalized_document = " ".join(document.split())

    for faction_row in faction_detachment_source.faction_rows():
        assert f"### Phase {faction_row.name}" in document

    for detachment_row in faction_detachment_source.detachment_rows():
        assert detachment_row.name in normalized_document

    assert "exact Adepta Sororitas detachments" not in document
    assert "exact Astra Militarum detachments" not in document
    assert "plus any official 11th Edition transition detachments" not in document


def test_faction_integration_phase17e_scope_keeps_datasheet_execution_in_phase17g() -> None:
    document = FACTION_INTEGRATION_PATH.read_text(encoding="utf-8")

    assert "## Phase 17E Scope Boundary" in document
    assert "every faction has a source-linked army rule descriptor" in document
    assert "every detachment has a source-linked detachment rule descriptor" in document
    assert "Phase 17E must also intake unit rows" in document
    assert "Broad datasheet, wargear" in document
    assert "weapon ability execution belongs to Phase 17G" in document
    assert "Do not hand-author an exhaustive unit-name list" in document


def test_faction_integration_records_phase17e_completion_gate() -> None:
    document = FACTION_INTEGRATION_PATH.read_text(encoding="utf-8")
    normalized_document = " ".join(document.split())
    identity = faction_coverage_source.source_package_identity_payload()

    assert "## Phase 17E Completion Gate" in document
    assert identity["source_package_id"] in document
    assert (
        "src/warhammer40k_core/rules/source_packages/warhammer_40000_11th/"
        "faction_coverage_2026_27.py"
    ) in document
    assert identity["source_title"] in document
    assert identity["source_version"] in document
    assert identity["source_date"] in document
    assert identity["upstream_identity"] in document
    assert f"source edition: `{identity['source_edition']}`" in document
    assert identity["imported_at_schema_version"] in document
    assert identity["source_payload_checksum_sha256"] in document
    assert "all 28 faction-pack PDF manifest records" in document
    assert "no unapproved unsupported descriptor remains" in normalized_document
    assert "not runtime fallbacks" in document


def test_faction_integration_records_phase17f_execution_gate() -> None:
    document = FACTION_INTEGRATION_PATH.read_text(encoding="utf-8")
    normalized_document = " ".join(document.split())
    identity = faction_execution_source.source_package_identity_payload()
    package = faction_execution_source.phase17f_execution_package()
    status_counts = package.status_counts()

    assert "## Phase 17F Execution Gate" in document
    assert identity["source_package_id"] in document
    assert (
        "src/warhammer40k_core/rules/source_packages/warhammer_40000_11th/"
        "faction_execution_2026_27.py"
    ) in document
    assert "src/warhammer40k_core/engine/faction_rule_execution.py" in document
    assert identity["source_title"] in document
    assert identity["source_version"] in document
    assert identity["source_date"] in document
    assert identity["upstream_identity"] in document
    assert f"source edition: `{identity['source_edition']}`" in document
    assert identity["imported_at_schema_version"] in document
    assert identity["source_payload_checksum_sha256"] in document
    assert identity["upstream_payload_checksum_sha256"] in document
    assert f"emits {len(package.execution_records)} execution records" in normalized_document
    assert (
        f"{status_counts[Phase17FExecutionStatus.BLOCKED_STRUCTURED_SEMANTICS_REQUIRED.value]} "
        "rows are blocked as `structured_rule_semantics_required`"
    ) in normalized_document
    assert (
        f"{status_counts[Phase17FExecutionStatus.BLOCKED_APPROVED_UNSUPPORTED_SOURCE_GAP.value]} "
        "rows are blocked as `approved_phase17e_source_gap`"
    ) in normalized_document
    assert "No Phase 17E row remains a missing handler" in normalized_document


def test_faction_integration_table_of_contents_links_every_execution_section() -> None:
    document = FACTION_INTEGRATION_PATH.read_text(encoding="utf-8")

    assert "## Table of Contents" in document
    assert "- [Faction Execution Status Matrix](#faction-execution-status-matrix)" in document
    for faction_row in faction_detachment_source.faction_rows():
        assert f"- [{faction_row.name} Execution Status](" in document
        assert f"### {faction_row.name} Execution Status" in document


def test_faction_integration_execution_matrix_matches_phase17f_package() -> None:
    document = FACTION_INTEGRATION_PATH.read_text(encoding="utf-8")
    records_by_faction = _execution_records_by_faction()

    assert "## Faction Execution Status Matrix" in document
    for faction_row in faction_detachment_source.faction_rows():
        section = _markdown_section(document, f"### {faction_row.name} Execution Status")
        records_by_family = records_by_faction[faction_row.name]
        for coverage_kind, family_label in _MATRIX_FAMILY_LABELS.items():
            records = records_by_family[coverage_kind]
            assert records
            status_values = {record.execution_status.value for record in records}
            source_blocks = {_source_block(record) for record in records}
            engine_results = {_engine_result(record) for record in records}
            assert len(status_values) == 1
            assert len(source_blocks) == 1
            assert len(engine_results) == 1
            expected_row = (
                f"| {family_label} | {len(records)} | `{status_values.pop()}` | "
                f"`{engine_results.pop()}` | `{source_blocks.pop()}` |"
            )
            assert expected_row in section


def test_faction_integration_requires_explicit_faq_classification_gate() -> None:
    document = FACTION_INTEGRATION_PATH.read_text(encoding="utf-8")

    assert "## FAQ Classification Gate" in document
    assert "`advisory_only`" in document
    assert "`executable_patch`" in document
    assert "`unsupported_executable_change`" in document
    assert "FAQs that change gameplay semantics must not be stored as `advisory_only`" in document
    assert "Plagueburst Crawler FAQ advisory record" in document


_MATRIX_FAMILY_LABELS = {
    Phase17ECoverageKind.FACTION_ARMY_RULE: "Army rule",
    Phase17ECoverageKind.DETACHMENT_RULE: "Detachment rules",
    Phase17ECoverageKind.DETACHMENT_ENHANCEMENT_DESCRIPTORS: "Enhancement descriptors",
    Phase17ECoverageKind.DETACHMENT_STRATAGEM_DESCRIPTORS: "Stratagem descriptors",
    Phase17ECoverageKind.DATASHEET_INTAKE: "Datasheet intake",
}


def _execution_records_by_faction() -> dict[
    str, dict[Phase17ECoverageKind, tuple[Phase17FExecutionRecord, ...]]
]:
    grouped: dict[str, dict[Phase17ECoverageKind, list[Phase17FExecutionRecord]]] = {}
    for record in faction_execution_source.phase17f_execution_package().execution_records:
        grouped.setdefault(record.faction_name, {}).setdefault(record.coverage_kind, []).append(
            record
        )
    return {
        faction_name: {
            coverage_kind: tuple(records) for coverage_kind, records in records_by_kind.items()
        }
        for faction_name, records_by_kind in grouped.items()
    }


def _source_block(record: Phase17FExecutionRecord) -> str:
    if record.execution_status is Phase17FExecutionStatus.BLOCKED_STRUCTURED_SEMANTICS_REQUIRED:
        return "structured_rule_semantics_required"
    if record.execution_status is Phase17FExecutionStatus.BLOCKED_APPROVED_UNSUPPORTED_SOURCE_GAP:
        if record.phase17e_unsupported_reason is None:
            raise AssertionError("Phase17F source-gap record lacks Phase17E reason.")
        return f"approved_phase17e_source_gap:{record.phase17e_unsupported_reason}"
    return "none"


def _engine_result(record: Phase17FExecutionRecord) -> str:
    if record.execution_status in {
        Phase17FExecutionStatus.BLOCKED_STRUCTURED_SEMANTICS_REQUIRED,
        Phase17FExecutionStatus.BLOCKED_APPROVED_UNSUPPORTED_SOURCE_GAP,
    }:
        return "unsupported"
    return "applied"


def _markdown_section(document: str, heading: str) -> str:
    start = document.index(heading)
    next_subheading = document.find("\n### ", start + len(heading))
    next_heading = document.find("\n## ", start + len(heading))
    candidates = [candidate for candidate in (next_subheading, next_heading) if candidate != -1]
    end = min(candidates) if candidates else len(document)
    return document[start:end]
