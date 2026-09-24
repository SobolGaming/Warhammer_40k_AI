"""Fail-closed inventory/report for the completed Order 84 category survey.

An immutable negative audit is not a runtime source package or a certificate.
Future clean audits must create new observations, not relabel this one.
"""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
from typing import Any

from tools.core_rules_40k_app_audit import roadmap_rows
from tools.core_rules_order84_capture import capture_literals, fingerprint, source_inventory

ROOT = Path(__file__).resolve().parents[1]
AUDIT = ROOT / "data/source_audits/order84/audit.json"
REPORT = ROOT / "docs/ORDER_84_AUDIT_REPORT.md"
INVENTORY_SHA256 = "9405274f48551a2431857c94d9004b779877f89345dc88955c9b72a74dd72921"
ASSET_SHA256 = "6f4d27c5670489e9b6310bb8f43e837d8abaf2d5f7a8c8938f56690190edad0e"
FINDING_OWNERS = {
    "C01-07": "P01G",
    "C01-08": "P01H",
    "C01-09": "P01I",
    "C02-06": "P02F",
    "C02-07": "P02G",
    "C02-08": "P02H",
    "C01-10": "P01J",
    "C04-04": "P04C",
    "C04-05": "P04D",
    "C02-09": "P02I",
    "C15-10": "P15J",
}


def load_audit() -> dict[str, Any]:
    value: dict[str, Any] = json.loads(AUDIT.read_text(encoding="utf-8"))
    return value


def validate_audit(audit: dict[str, Any], *, roadmap: str | None = None) -> None:
    if (
        audit["schema"] != "core-v2-order84-audit-v1"
        or audit["reviewed_commit"] != "557803404b549023b2d0271b52a2c8d19f5b994b"
        or audit["outcome"] != "gaps_found_not_certified"
        or audit["category_survey_complete"] is not True
        or audit["operative_clause_certification_complete"] is not False
        or audit["caudit_01_closed"] is not False
    ):
        raise ValueError("Order 84 is an immutable negative audit, not a certificate.")
    observation = audit["observation"]
    if (
        observation["asset_sha256"] != ASSET_SHA256
        or observation["source_inventory_sha256"] != INVENTORY_SHA256
        or observation["app_data_version"] is not None
        or observation["complete_for_certification"] is not False
    ):
        raise ValueError("Order 84 source identity or completeness claim drifted.")
    inventory = audit["source_inventory"]
    if fingerprint(inventory) != INVENTORY_SHA256:
        raise ValueError("Order 84 source inventory omitted or changed an observed block.")
    source_ids = {row["row_id"] for row in inventory}
    if len(source_ids) != 345 or sum(len(row["blocks"]) for row in inventory) != 1424:
        raise ValueError("Order 84 source row/block inventory is incomplete.")
    reviews = audit["row_reviews"]
    if len(reviews) != len(source_ids) or {row["row_id"] for row in reviews} != source_ids:
        raise ValueError("Order 84 requires one disposition for every source row and FAQ.")
    categories = {f"{n:02d}" for n in range(1, 26)}
    category_reviews = audit["category_reviews"]
    if len(category_reviews) != 25 or {row["category"] for row in category_reviews} != categories:
        raise ValueError("Order 84 must review all 25 categories.")
    for row in reviews:
        if row["review_category"] not in categories or row["clause_certification"] != "open":
            raise ValueError("Order 84 family evidence cannot certify individual clauses.")
    for row in category_reviews:
        if not row["engine_owners"] or not row["regression_files"] or not row["assessment"]:
            raise ValueError("Order 84 category must identify its owners and evidence limits.")
        for path in (*row["engine_owners"], *row["regression_files"]):
            if not (ROOT / path).is_file():
                raise ValueError(f"Order 84 evidence path is missing: {path}.")
    findings = audit["findings"]
    if (
        len(findings) != len(FINDING_OWNERS)
        or {row["finding_id"]: row["pr_id"] for row in findings} != FINDING_OWNERS
    ):
        raise ValueError("Order 84 finding ownership is incomplete or ambiguous.")
    for finding in findings:
        if finding["status"] != "open" or not finding["source_rows"]:
            raise ValueError("Order 84 finding cannot be closed by this diagnostic audit.")
        if not set(finding["source_rows"]) <= source_ids:
            raise ValueError("Order 84 finding references an unknown source row.")
    for row in reviews:
        expected = [f["finding_id"] for f in findings if row["row_id"] in f["source_rows"]]
        if row["finding_ids"] != expected:
            raise ValueError("Order 84 source/finding links disagree.")
    obligations = audit["obligation_reviews"]
    if (
        len(obligations) != 19
        or len({row["obligation_id"] for row in obligations}) != 19
        or sum(row["obligation_id"].startswith("v931-") for row in obligations) != 18
        or obligations[-1]["obligation_id"] != "v946-rapid-disembark"
    ):
        raise ValueError("Order 84 must retain 18 v931 obligations and v946 Rapid Disembark.")
    for review in audit["cross_category_reviews"]:
        for path in review["evidence"]:
            if not (ROOT / path).is_file():
                raise ValueError(f"Order 84 cross-category evidence path is missing: {path}.")
    performance = audit["complete_game_performance"]
    if (
        performance["status"] != "unavailable_not_certified"
        or performance["completed_games"] != 0
        or performance["mean_seconds"] is not None
        or performance["max_seconds"] is not None
        or not performance["missing_prerequisites"]
    ):
        raise ValueError("Order 84 has no complete-game timing evidence.")
    probes = ROOT / audit["probe_results_path"]
    if hashlib.sha256(probes.read_bytes()).hexdigest() != audit["probe_results_sha256"]:
        raise ValueError("Order 84 retained probe results drifted.")
    probe_results = json.loads(probes.read_text(encoding="utf-8"))
    if any(probe not in probe_results for f in findings for probe in f["probes"]):
        raise ValueError("Order 84 finding references an unknown probe.")
    if roadmap is not None:
        rows = roadmap_rows(roadmap)
        owners = {finding: row.pr_id for row in rows for finding in row.finding_ids}
        if any(owners.get(f) != owner for f, owner in FINDING_OWNERS.items()):
            raise ValueError("Order 84 findings require canonical roadmap owners before PFINAL.")
        for row in (*obligations, *audit["september10_reviews"]):
            if row["finding_id"] not in owners:
                raise ValueError("Order 84 prior-review obligation lost its roadmap owner.")


def markdown(audit: dict[str, Any]) -> str:
    observation = audit["observation"]
    lines = [
        "# Order 84 complete category survey — outstanding gaps",
        "",
        "Generated with `python -m tools.core_rules_order84_audit`; do not edit by hand.",
        "",
        f"Reviewed runtime: `{audit['reviewed_commit']}` (PR #503).",
        "**Core Rules are not certified.**",
        "The survey continued through all 25 categories and all 59 FAQs after finding defects.",
        "It retains 286 rule/update rows and 1,424 rendered source blocks, including examples,",
        "supplemental Stratagem bodies, tables and callouts. These are inventory counts, not",
        "counts of independent rules or proven gameplay behaviors.",
        "",
        "The [audit JSON](../data/source_audits/order84/audit.json) maps every observed",
        "row to category owners, regression files and explicit open clause-certification",
        "status. Family regressions do not prove every individual operative clause. Exact retained",
        "source equivalence and clause-specific facade/replay/visibility proof remain open.",
        "The [audit notes](ORDER_84_AUDIT_NOTES.md) describe reproduction, scope and validation.",
        "",
        "## Selected candidate observation",
        "",
        f"Provider: [{observation['provider']}]({observation['url']}).",
        "This is a non-affiliated maintained mirror.",
        f"Observed: `{observation['observed_at']}`. App-data version: **not exposed**.",
        f"Public asset SHA-256: `{observation['asset_sha256']}`.",
        f"Source inventory SHA-256: `{observation['source_inventory_sha256']}`.",
        "",
        observation["comparison"],
        "This candidate is incomplete for certification (C15-10). The retained metadata and",
        "block fingerprints are not a runtime source package or a complete verbatim archive.",
        "The two distinct 09.07.01 entries and untitled 24.37.01 remain separate inventory rows.",
        "",
        "## Findings requiring scoped follow-ups",
        "",
    ]
    for finding in audit["findings"]:
        lines.extend(
            [
                f"### {finding['finding_id']} / {finding['pr_id']} — {finding['title']}",
                "",
                f"Evidence class: `{finding['kind']}`. {finding['observed']}",
                "",
                f"Required closure: {finding['required']}",
                "",
                "Source rows: " + ", ".join(f"`{row}`" for row in finding["source_rows"]) + ".",
                "",
            ]
        )
    lines.extend(
        [
            "## All-category dispositions",
            "",
            "| Category | Survey assessment | Regression families |",
            "|---|---|---|",
        ]
    )
    for category in audit["category_reviews"]:
        evidence = ", ".join(f"[{Path(p).stem}](../{p})" for p in category["regression_files"])
        lines.append(
            f"| {category['category']} {category['title']} | "
            f"{category['assessment']} | {evidence} |"
        )
    lines.extend(
        [
            "",
            "## Prior obligations and cross-category checks",
            "",
            "All 18 distinct v931 obligations and the v946 obligation are retained below.",
            "These are rechecked implementation links, not new final-certification claims.",
            "",
            "| Obligation | Existing owner finding | Category |",
            "|---|---|---|",
        ]
    )
    for row in audit["obligation_reviews"]:
        lines.append(f"| {row['obligation_id']} | {row['finding_id']} | {row['review_category']} |")
    lines.extend(
        [
            "",
            "The split erratum duplicates the Splitting Units obligation. The v931 Ongoing erratum",
            "is historical: C12-04's owner-confirmed v946 Engaging-only resolution controls.",
            "The September 10 review's repeated B7 labels are retained with their topic suffixes",
            "in the JSON, including acceptance omissions repaired by Orders 77-80.",
            "",
        ]
    )
    for review in audit["cross_category_reviews"]:
        links = ", ".join(f"[{Path(p).name}](../{p})" for p in dict.fromkeys(review["evidence"]))
        lines.append(f"- {review['topic']}: {links}.")
    lines.extend(
        [
            "",
            "## Complete-game performance",
            "",
            "**Unavailable and uncertified: zero complete-game samples.** Mean and maximum are",
            "unknown, not zero. No claim is made against the <60-second mean and ≤300-second",
            "maximum targets. Diagnostic probes and ordinary test durations are not games.",
            "",
        ]
    )
    lines.extend(
        f"- {item}" for item in audit["complete_game_performance"]["missing_prerequisites"]
    )
    lines.extend(["", "## Limits", ""])
    lines.extend(f"- {item}" for item in audit["limitations"])
    return "\n".join(lines) + "\n"


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--check", action="store_true")
    parser.add_argument("--verify-capture", type=Path)
    args = parser.parse_args()
    audit = load_audit()
    validate_audit(audit, roadmap=(ROOT / "docs/CORE_RULES_REMEDIATION_ROADMAP.md").read_text())
    if args.verify_capture is not None:
        data = args.verify_capture.read_bytes()
        if hashlib.sha256(data).hexdigest() != ASSET_SHA256:
            raise ValueError("Order 84 capture is not the observed public asset.")
        if source_inventory(capture_literals(data.decode("utf-8"))) != audit["source_inventory"]:
            raise ValueError("Order 84 capture and committed inventory differ.")
    report = markdown(audit)
    if args.check:
        if REPORT.read_text(encoding="utf-8") != report:
            raise ValueError("Order 84 generated report is stale.")
    else:
        REPORT.write_text(report, encoding="utf-8")
    print("Order 84 inventory checked: 25 categories, 345 rows, 1424 blocks; NOT CERTIFIED.")


if __name__ == "__main__":
    main()
