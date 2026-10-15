from __future__ import annotations

from tests.shared.category_migration.phase17i_blocked_row_classification import (
    Phase17FExecutionStatus,
    RuleTemplateFamily,
    _payload_checksum,
    classification_source,
    execution_source,
    hashlib,
    json,
    pytest,
    replace,
    rule_template_by_id,
)


def test_phase17i_classification_covers_every_phase17f_structured_blocked_row() -> None:
    report = classification_source.phase17i_blocked_row_classification_report()
    structured_blocked_records = tuple(
        record
        for record in execution_source.phase17f_execution_package().execution_records
        if record.execution_status is Phase17FExecutionStatus.BLOCKED_STRUCTURED_SEMANTICS_REQUIRED
    )
    rows_by_execution_id = {row.execution_id: row for row in report.classification_rows}

    assert report.structured_blocked_count == 1889
    assert set(rows_by_execution_id) == {
        record.execution_id for record in structured_blocked_records
    }
    for record in structured_blocked_records:
        row = rows_by_execution_id[record.execution_id]
        assert row.coverage_descriptor_id == record.coverage_descriptor_id
        assert row.coverage_kind is record.coverage_kind
        assert row.faction_id == record.faction_id
        assert row.faction_name == record.faction_name
        assert row.detachment_id == record.detachment_id
        assert row.detachment_name == record.detachment_name
        assert row.rule_name == record.rule_name
        assert row.rule_id == record.rule_id
        assert row.source_ids == record.source_ids
        assert row.missing_capability_families


def test_phase17i_recognizes_structured_stratagem_cost_runtime_support() -> None:
    report = classification_source.phase17i_blocked_row_classification_report()
    row = next(
        row
        for row in report.classification_rows
        if row.execution_id
        == "phase17f:phase17e:enhancement:space-marines:vanguard-spearhead:000008490005"
    )

    assert row.existing_template_families == ("aura", "keyword_gate")
    assert set(row.missing_capability_families) == {
        classification_source.Phase17IMissingCapabilityFamily.ENHANCEMENT_ASSIGNMENT_EFFECT,
        classification_source.Phase17IMissingCapabilityFamily.GENERIC_IR_EXECUTION_BINDING,
        classification_source.Phase17IMissingCapabilityFamily.UNREPRESENTED_RULE_LANGUAGE,
    }

    mixed_row = next(
        row
        for row in report.classification_rows
        if row.execution_id
        == "phase17f:phase17e:enhancement:chaos-knights:lords-of-dread:000010308006"
    )
    assert {
        classification_source.Phase17IMissingCapabilityFamily.FACTION_RESOURCE_LEDGER,
        classification_source.Phase17IMissingCapabilityFamily.STRATAGEM_COST_MODIFIER_RUNTIME,
    } <= set(mixed_row.missing_capability_families)


__all__: list[str] = []
__all__ += ["RuleTemplateFamily", "_payload_checksum", "hashlib", "json", "pytest", "replace"]
__all__ += ["rule_template_by_id"]
