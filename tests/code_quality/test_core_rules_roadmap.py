from __future__ import annotations

from pathlib import Path

import pytest
from tools.core_rules_40k_app_audit import (
    category_pr_ids,
    core_rules_forty_k_app_audit_markdown,
    roadmap_rows,
)

ROOT = Path(__file__).resolve().parents[2]
ROADMAP = ROOT / "docs" / "CORE_RULES_REMEDIATION_ROADMAP.md"


def test_core_roadmap_gives_review_findings_unique_owners_before_certification() -> None:
    document = ROADMAP.read_text(encoding="utf-8")
    rows = roadmap_rows(document)
    owners = {finding: row.pr_id for row in rows for finding in row.finding_ids}
    assert (
        owners.items()
        >= {
            "C01-04": "P01D",
            "C02-05": "P02E",
            "C11-04": "P11B",
            "C12-04": "P12B",
            "C17-01": "P17",
            "C18-07": "P18F",
            "C18-08": "P18G",
            "C18-09": "P18H",
            "C20-02": "P20B",
            "C24-10": "P24J",
        }.items()
    )
    assert rows[-1].pr_id == "PFINAL"
    assert f"All {len(rows) - 2} implementation PRs; S-MIRRORS" in document
    by_pr = {row.pr_id: row for row in rows}
    assert by_pr["P18G"].gate == "APP-DRIFT"
    assert by_pr["P18F"].gate == "EXCEPTION-PAUSE"
    assert by_pr["P12B"].gate == "EXCEPTION-PAUSE"
    transport = ("P18A", "P18C", "P18D", "P18E", "P18F", "P18G", "P18H", "P18B")
    for row in rows[:-1]:
        for dependency in row.prerequisites:
            for prerequisite in transport if dependency == "T-TRANSPORT" else (dependency,):
                assert by_pr[prerequisite].order < row.order, (row.pr_id, prerequisite)


def test_comparison_uses_current_roadmap_without_rewriting_historical_observations() -> None:
    inventory = category_pr_ids(roadmap_rows(ROADMAP.read_text(encoding="utf-8")))
    assert inventory["17"] == ("P17",)
    assert "P18G" in inventory["18"]
    assert "P22B" in inventory["22"]
    assert "P24J" in inventory["24"]
    report = core_rules_forty_k_app_audit_markdown()
    for category, planned in inventory.items():
        line = next(line for line in report.splitlines() if line.startswith(f"| {category} "))
        assert line.endswith(f"| {', '.join(planned) if planned else 'PFINAL'} |")
    assert "Historical source and provider findings" in report
    assert report == (ROOT / "docs" / "CORE_RULES_40K_APP_COMPARISON.md").read_text(
        encoding="utf-8"
    )


@pytest.mark.parametrize("change", ["duplicate_finding", "duplicate_pr", "missing_order"])
def test_roadmap_parser_rejects_ambiguous_closure_inventory(change: str) -> None:
    document = ROADMAP.read_text(encoding="utf-8")
    if change == "duplicate_finding":
        document = document.replace("| C18-08 |", "| C18-07 |", 1)
    elif change == "duplicate_pr":
        document = document.replace("| P18G |", "| P18F |", 1)
    else:
        document = document.replace("| 2 | P08A |", "| 3 | P08A |", 1)
    with pytest.raises(ValueError, match="Core roadmap"):
        roadmap_rows(document)
