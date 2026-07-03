from __future__ import annotations

from warhammer40k_core.rules.source_packages.warhammer_40000_11th import (
    faction_named_handler_budget_2026_27 as budget_source,
)


def test_ws14_named_handler_budget_has_no_unapproved_or_stale_entries() -> None:
    report = budget_source.phase17i_named_handler_budget_report()

    assert report.unapproved_named_handler_execution_ids == ()
    assert report.stale_approved_execution_ids == ()
    assert report.to_payload()["unapproved_named_handler_count"] == 0
    assert report.to_payload()["stale_approval_count"] == 0
