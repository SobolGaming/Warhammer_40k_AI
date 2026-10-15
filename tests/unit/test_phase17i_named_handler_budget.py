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


def test_phase17i_named_handler_budget_covers_current_phase17f_named_handlers() -> None:
    report = budget_source.phase17i_named_handler_budget_report()
    named_handler_records = tuple(
        record
        for record in execution_source.phase17f_execution_package().execution_records
        if record.execution_status is Phase17FExecutionStatus.EXECUTABLE_NAMED_HANDLER
    )

    assert report.named_handler_records == named_handler_records
    assert len(report.named_handler_records) == 23
    assert len(report.approved_entries) == 23
    assert report.unapproved_named_handler_execution_ids == ()
    assert report.stale_approved_execution_ids == ()
    daemonic_manifestation = july_faction_packs_2026_07.daemonic_manifestation()
    assert daemonic_manifestation.phase17f_execution_id in report.named_handler_execution_ids
    assert (
        daemonic_manifestation.predecessor_source_rule_id not in report.named_handler_execution_ids
    )
    assert daemonic_manifestation.named_handler_budget_execution_id in report.approved_execution_ids
    pre_ws14_reason = (
        budget_source.Phase17INamedHandlerApprovalReason.PRE_WS14_EXISTING_RUNTIME_CONSUMER.value
    )
    assert report.approval_reason_counts() == {pre_ws14_reason: 23}


__all__: list[str] = []
__all__ += ["Phase17FExecutionBlockReason", "json", "pytest", "replace"]
