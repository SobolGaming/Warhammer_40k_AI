from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from warhammer40k_core.rules.source_packages.warhammer_40000_11th import (
    faction_blocked_row_classification_2026_27 as blocked_classification_source,
)
from warhammer40k_core.rules.source_packages.warhammer_40000_11th import (
    faction_coverage_2026_27 as faction_coverage_source,
)
from warhammer40k_core.rules.source_packages.warhammer_40000_11th import (
    faction_detachments_2026_27 as faction_detachment_source,
)
from warhammer40k_core.rules.source_packages.warhammer_40000_11th import (
    faction_execution_2026_27 as faction_execution_source,
)
from warhammer40k_core.rules.source_packages.warhammer_40000_11th import (
    faction_named_handler_budget_2026_27 as named_handler_budget_source,
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


def test_faction_integration_phase17e_scope_defers_datasheet_execution_to_phase17h() -> None:
    document = FACTION_INTEGRATION_PATH.read_text(encoding="utf-8")

    assert "## Phase 17E Scope Boundary" in document
    assert "every faction has a source-linked army rule descriptor" in document
    assert "every detachment has a source-linked detachment rule descriptor" in document
    assert "Phase 17E must also intake unit rows" in document
    assert "Broad datasheet, wargear" in document
    assert "weapon ability execution belongs to Phase 17H" in document
    assert "Phase 17G semantic execution" in document
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
    assert "unregistered executable statuses return typed `unsupported`" in normalized_document
    assert "cannot emit `applied` by status alone" in normalized_document
    assert "not semantic execution" in normalized_document
    assert "checksum-covered static RuleIR payloads" in document
    assert "does not compile raw source prose" in normalized_document
    assert "read raw source snapshot JSON" in normalized_document


def test_faction_integration_records_phase17g_17h_17i_roadmap_split() -> None:
    document = FACTION_INTEGRATION_PATH.read_text(encoding="utf-8")
    normalized_document = " ".join(document.split())

    assert "## Phase 17G Runtime Scaffold Gate" in document
    assert "tools/generate_faction_content_scaffold.py" in document
    assert "generated_manifest.py" in document
    assert "The generator owns `generated_manifest.py`" in document
    assert "Generated faction `manifest.py` files aggregate" in document
    assert "placeholder scaffold contributions are empty and use stable IDs" in document
    assert "orphaned generated placeholder" in document
    assert "supported` in the runtime manifest means" in normalized_document
    assert "CI fails when generator-owned files are stale" in document
    assert "CI fails when agent-owned files are missing required exports" in document
    assert (
        "must not generate broad datasheet, wargear, or weapon-profile files" in normalized_document
    )

    assert "## Phase 17G Semantic Execution Gate" in document
    assert "army rules" in document
    assert "detachment rules" in document
    assert "enhancement effects" in document
    assert "Stratagem timing, targeting, validation, and effects" in document
    assert "source-linked Battle-shock hook bindings" in normalized_document
    assert "Battle-shock modifier or outcome resolution" in normalized_document
    assert "source-linked Fall Back eligibility hook bindings" in normalized_document
    assert "completed Fall Back move does not prevent later Shooting or Charge" in (
        normalized_document
    )
    assert "execution-status overlay" in normalized_document
    assert "faction army rules load and execute for every faction" in normalized_document
    assert "detachment rules load and execute for every detachment" in normalized_document

    assert "## Phase 17H Datasheet, Wargear, and Weapon Execution Gate" in document
    assert (
        "datasheet abilities, selected wargear abilities, weapon abilities" in normalized_document
    )
    assert "wargear abilities apply only when that wargear is selected" in document

    assert "## Phase 17I Coverage and Unsupported Audit Gate" in document
    assert "execution-status report for every covered item" in document
    assert "unsupported descriptors grouped by reason" in document


def test_faction_integration_records_phase17i_blocked_row_classification_report() -> None:
    document = FACTION_INTEGRATION_PATH.read_text(encoding="utf-8")
    normalized_document = " ".join(document.split())
    identity = blocked_classification_source.source_package_identity_payload()
    report = blocked_classification_source.phase17i_blocked_row_classification_report()

    assert "## Phase 17I Blocked Row Classification Report" in document
    assert identity["source_package_id"] in document
    assert (
        "src/warhammer40k_core/rules/source_packages/warhammer_40000_11th/"
        "faction_blocked_row_classification_2026_27.py"
    ) in document
    assert identity["source_title"] in document
    assert identity["source_version"] in document
    assert identity["source_date"] in document
    assert identity["upstream_identity"] in document
    assert f"source edition: `{identity['source_edition']}`" in document
    assert identity["imported_at_schema_version"] in document
    assert identity["source_payload_checksum_sha256"] in document
    assert identity["upstream_payload_checksum_sha256"] in document
    assert identity["wahapedia_source_version"] in document
    bridge_edition_dir, bridge_year, bridge_month, bridge_day = identity[
        "wahapedia_source_version"
    ].rsplit("-", maxsplit=3)
    bridge_source_path = (
        "data/source_snapshots/wahapedia/"
        f"{bridge_edition_dir}/{bridge_year}-{bridge_month}-{bridge_day}/json"
    )
    assert bridge_source_path in document
    assert f"emits {report.structured_blocked_count} classification rows" in (normalized_document)
    assert f"compiles {report.source_text_matched_count} rows" in normalized_document
    assert f"marks {report.source_text_missing_count} rows as" in normalized_document
    assert "`source_text_not_available` metadata-only rows" in document
    assert "existing Phase 17C template IDs and template families" in normalized_document
    assert "`generic_ir_execution_binding`" in document
    assert "`unrepresented_rule_language`" in document
    assert "The payload does not emit raw rule text" in document


def test_faction_integration_records_phase17i_named_handler_budget() -> None:
    document = FACTION_INTEGRATION_PATH.read_text(encoding="utf-8")
    normalized_document = " ".join(document.split())
    identity = named_handler_budget_source.source_package_identity_payload()
    report = named_handler_budget_source.phase17i_named_handler_budget_report()

    assert "## Phase 17I Named Handler Budget" in document
    assert "- [Phase 17I Named Handler Budget](#phase-17i-named-handler-budget)" in document
    assert identity["source_package_id"] in document
    assert (
        "src/warhammer40k_core/rules/source_packages/warhammer_40000_11th/"
        "faction_named_handler_budget_2026_27.py"
    ) in document
    assert identity["source_title"] in document
    assert identity["source_version"] in document
    assert identity["source_date"] in document
    assert identity["upstream_identity"] in document
    assert f"source edition: `{identity['source_edition']}`" in document
    assert identity["imported_at_schema_version"] in document
    assert identity["source_payload_checksum_sha256"] in document
    assert identity["upstream_payload_checksum_sha256"] in document
    assert f"tracks {len(report.named_handler_records)} executable named-handler" in (
        normalized_document
    )
    assert f"and {len(report.approved_entries)} approved entries" in normalized_document
    assert "`pre_ws14_existing_runtime_consumer`" in document
    assert "new named handler appears without an approved entry" in normalized_document
    assert "leaves a stale approval behind" in normalized_document


def test_faction_integration_records_ws14_ir_first_content_drop_runbook() -> None:
    document = FACTION_INTEGRATION_PATH.read_text(encoding="utf-8")
    normalized_document = " ".join(document.split())

    assert "## WS14 IR-First Content-Drop Runbook" in document
    assert "- [WS14 IR-First Content-Drop Runbook](#ws14-ir-first-content-drop-runbook)" in document
    assert "Ingest the new official PDF, dataslate, MFM, FAQ, or codex source package" in document
    assert "Apply source-linked patch operations" in document
    assert "Recompile RuleIR at the source boundary" in document
    assert "Diff the Phase 17F execution report and Phase 17I classification report" in document
    assert "registered `RuleExecutionRegistry` executor" in document
    assert "approved named handlers, approved source gaps, or new Phase 17C template families" in (
        normalized_document
    )
    assert "Run the WS15 policy-evaluation gate" in document
    assert "typical monthly dataslate requires zero new Python" in document


def test_faction_integration_table_of_contents_links_every_execution_section() -> None:
    document = FACTION_INTEGRATION_PATH.read_text(encoding="utf-8")

    assert "## Table of Contents" in document
    assert "- [Phase 17G Runtime Scaffold Gate](#phase-17g-runtime-scaffold-gate)" in document
    assert "- [Phase 17G Semantic Execution Gate](#phase-17g-semantic-execution-gate)" in document
    assert (
        "- [Phase 17H Datasheet, Wargear, and Weapon Execution Gate]"
        "(#phase-17h-datasheet-wargear-and-weapon-execution-gate)"
    ) in document
    assert (
        "- [Phase 17I Coverage and Unsupported Audit Gate]"
        "(#phase-17i-coverage-and-unsupported-audit-gate)"
    ) in document
    assert (
        "- [Phase 17I Blocked Row Classification Report]"
        "(#phase-17i-blocked-row-classification-report)"
    ) in document
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
            records = records_by_family.get(coverage_kind, ())
            for group in _execution_matrix_groups(records):
                expected_row = (
                    f"| {family_label} | {len(group.records)} | "
                    f"`{group.execution_status}` | `{group.engine_result}` | "
                    f"`{group.source_block}` |"
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


def test_faction_integration_links_agent_implementation_contract() -> None:
    document = FACTION_INTEGRATION_PATH.read_text(encoding="utf-8")
    normalized_document = " ".join(document.split())
    contract_path = ROOT / "docs" / "FACTION_AGENT_IMPLEMENTATION_CONTRACT.md"
    contract = contract_path.read_text(encoding="utf-8")

    assert "## Agent Implementation Contract" in document
    assert "docs/FACTION_AGENT_IMPLEMENTATION_CONTRACT.md" in document
    assert "Task packets must name the faction or detachment" in document
    assert "remove the generated placeholder marker from implemented files" in normalized_document
    assert "Use existing `RuntimeContentContribution` surfaces" in contract
    assert "Battle-shock hook bindings" in contract
    assert "Enhancement effect bindings" in contract
    assert "generated Phase 17F execution rows" in contract
    assert "Generated `manifest.py` files are stable aggregators" in contract
    assert "Remove the marker when the file implements source-backed semantics" in contract
    assert "Do not parse raw rule text" in contract
    assert "Return typed unsupported results with source-linked reasons" in contract


_MATRIX_FAMILY_LABELS = {
    Phase17ECoverageKind.FACTION_ARMY_RULE: "Army rule",
    Phase17ECoverageKind.DETACHMENT_RULE: "Detachment rules",
    Phase17ECoverageKind.DETACHMENT_ENHANCEMENT: "Enhancements",
    Phase17ECoverageKind.DETACHMENT_STRATAGEM: "Stratagems",
    Phase17ECoverageKind.DATASHEET_INTAKE: "Datasheet intake",
}


@dataclass(frozen=True, slots=True)
class ExecutionMatrixGroup:
    execution_status: str
    engine_result: str
    source_block: str
    records: tuple[Phase17FExecutionRecord, ...]


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


def _execution_matrix_groups(
    records: tuple[Phase17FExecutionRecord, ...],
) -> tuple[ExecutionMatrixGroup, ...]:
    grouped: dict[tuple[str, str, str], list[Phase17FExecutionRecord]] = {}
    for record in records:
        key = (record.execution_status.value, _engine_result(record), _source_block(record))
        grouped.setdefault(key, []).append(record)
    return tuple(
        ExecutionMatrixGroup(
            execution_status=execution_status,
            engine_result=engine_result,
            source_block=source_block,
            records=tuple(records),
        )
        for (execution_status, engine_result, source_block), records in sorted(grouped.items())
    )


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
