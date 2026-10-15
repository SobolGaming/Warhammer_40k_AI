from __future__ import annotations

from tests.shared.category_migration.phase17i_named_handler_budget import (
    Phase17FExecutionBlockReason,
    Phase17FExecutionStatus,
    budget_source,
    execution_source,
    json,
    july_faction_packs_2026_07,
    pytest,
    replace,
)


def test_phase17i_named_handler_budget_payload_is_deterministic_json_safe() -> None:
    report = budget_source.phase17i_named_handler_budget_report()
    payload = report.to_payload()

    encoded = json.dumps(payload, sort_keys=True, separators=(",", ":"))
    assert " object at 0x" not in encoded
    assert (
        payload["source_payload_checksum_sha256"]
        == budget_source.source_package_identity_payload()["source_payload_checksum_sha256"]
    )
    assert (
        payload["upstream_payload_checksum_sha256"]
        == execution_source.source_package_identity_payload()["source_payload_checksum_sha256"]
    )
    assert budget_source.Phase17INamedHandlerBudgetReport.from_payload(payload) == report

    stale_payload = payload.copy()
    stale_payload["source_payload_checksum_sha256"] = "0" * 64
    with pytest.raises(
        budget_source.Phase17INamedHandlerBudgetError,
        match="payload is stale",
    ):
        budget_source.Phase17INamedHandlerBudgetReport.from_payload(stale_payload)

    stale_upstream_payload = payload.copy()
    stale_upstream_payload["upstream_payload_checksum_sha256"] = "0" * 64
    with pytest.raises(
        budget_source.Phase17INamedHandlerBudgetError,
        match="upstream payload checksum",
    ):
        budget_source.Phase17INamedHandlerBudgetReport.from_payload(stale_upstream_payload)


def test_phase17i_named_handler_budget_reports_unapproved_and_stale_entries() -> None:
    report = budget_source.phase17i_named_handler_budget_report()
    approved_ids = report.approved_execution_ids
    first_record = report.named_handler_records[0]
    extra_record = replace(
        first_record,
        execution_id=f"{first_record.execution_id}:new-handler",
    )
    stale_entry = budget_source.Phase17INamedHandlerBudgetEntry(
        execution_id=f"{approved_ids[0]}:stale-entry",
        approved_reason=(
            budget_source.Phase17INamedHandlerApprovalReason.PRE_WS14_EXISTING_RUNTIME_CONSUMER
        ),
    )
    drifted_report = budget_source.Phase17INamedHandlerBudgetReport(
        approved_entries=(*report.approved_entries, stale_entry),
        named_handler_records=(*report.named_handler_records, extra_record),
    )

    assert drifted_report.unapproved_named_handler_execution_ids == (extra_record.execution_id,)
    assert drifted_report.stale_approved_execution_ids == (stale_entry.execution_id,)


def test_phase17i_named_handler_budget_rejects_invalid_shapes() -> None:
    report = budget_source.phase17i_named_handler_budget_report()

    with pytest.raises(budget_source.Phase17INamedHandlerBudgetError, match="must be a tuple"):
        budget_source.Phase17INamedHandlerBudgetReport(
            approved_entries=list(report.approved_entries),  # type: ignore[arg-type]
            named_handler_records=report.named_handler_records,
        )

    with pytest.raises(budget_source.Phase17INamedHandlerBudgetError, match="must be unique"):
        budget_source.Phase17INamedHandlerBudgetReport(
            approved_entries=(report.approved_entries[0], report.approved_entries[0]),
            named_handler_records=report.named_handler_records,
        )

    with pytest.raises(
        budget_source.Phase17INamedHandlerBudgetError,
        match="executable named-handler",
    ):
        budget_source.Phase17INamedHandlerBudgetReport(
            approved_entries=report.approved_entries,
            named_handler_records=(
                replace(
                    report.named_handler_records[0],
                    execution_status=Phase17FExecutionStatus.BLOCKED_STRUCTURED_SEMANTICS_REQUIRED,
                    block_reason=Phase17FExecutionBlockReason.STRUCTURED_RULE_SEMANTICS_REQUIRED,
                ),
            ),
        )


__all__: list[str] = []
__all__ += ["july_faction_packs_2026_07"]
