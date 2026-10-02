"""Immutable negative Core audit, with offline evidence and optional capture checks.

Source row/block coverage is deliberately distinct from operative-clause
certification. Historical evidence is pinned to the reviewed commit, not relabeled
when a later implementation changes the runtime tree.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
from pathlib import Path
from typing import Any

from tools.core_rules_40k_app_audit import roadmap_rows
from tools.core_rules_order84_capture import capture_literals, fingerprint, source_inventory

ROOT = Path(__file__).resolve().parents[1]
AUDIT = ROOT / "data/source_audits/order95/audit.json"
REPORT = ROOT / "docs/ORDER_95_AUDIT_REPORT.md"
REVIEW_SHA256 = "ad82717ccea80ea9e1315dbdeb03607aa5d760ae0d3842bf7e7b9f700a03e0fa"
FINDING_OWNERS = {"C04-06": "P04E", "C24-11": "P24K", "CAUDIT-02": "PEVIDENCE"}
# Explicit retirement proof for C24-11; the immutable negative observation stays
# pinned to its reviewed commit. Both replacement owners must remain present.
RETIRED_REFERENCE_SUCCESSORS = {
    "src/warhammer40k_core/engine/attack_sequence_hit_wound.py:"
    "_reroll_wound_for_twin_linked_if_needed": (
        "src/warhammer40k_core/engine/intrinsic_attack_rerolls.py:intrinsic_wound_reroll_contexts",
        "src/warhammer40k_core/engine/attack_sequence_dice_rerolls.py:"
        "build_source_backed_wound_reroll_request",
    ),
    # V963-SHOCK supersedes 18.07's former forced-Fight producer. The original
    # test remains in the exact-base V963 historical snapshot, while these live
    # successors check current legal setup and reject passenger engagement.
    "tests/unit/test_phase10q_transports.py::"
    "test_shock_disembark_routes_opponent_through_canonical_fight_activation_and_replay": (
        "tests/unit/test_v963_shock_disembark.py::"
        "test_v963_shock_unengaged_setup_has_no_queue_and_restores_exactly",
        "tests/unit/test_v963_shock_disembark.py::"
        "test_v963_shock_rejects_passenger_engagement_without_mutation",
    ),
}


class AuditError(ValueError):
    """The retained Order 95 evidence or its negative disposition changed."""


def validate_owner_reference(reference: str, root: Path) -> None:
    path, _, symbol = reference.replace("::", ":").partition(":")
    target = root / path
    present = target.is_file() and (not symbol or f"def {symbol}(" in target.read_text())
    if reference in RETIRED_REFERENCE_SUCCESSORS:
        if present:
            raise AuditError(f"Order 95 retired owner was reintroduced: {reference}.")
        for successor in RETIRED_REFERENCE_SUCCESSORS[reference]:
            validate_owner_reference(successor, root)
    elif not present:
        raise AuditError(f"Order 95 owner/regression reference is absent: {reference}.")


def _verified_file(evidence: dict[str, Any], root: Path) -> bytes:
    relative = Path(evidence["path"])
    if relative.is_absolute() or ".." in relative.parts:
        raise AuditError("Order 95 evidence path escapes the repository.")
    try:
        raw = (root / relative).read_bytes()
    except OSError as exc:
        raise AuditError(f"Order 95 evidence unavailable: {relative}.") from exc
    if hashlib.sha256(raw).hexdigest() != evidence["sha256"]:
        raise AuditError(f"Order 95 evidence hash drifted: {relative}.")
    return raw


def load_audit(*, payload: object | None = None) -> dict[str, Any]:
    if payload is None:
        try:
            payload = json.loads(AUDIT.read_text(encoding="utf-8"))
        except (OSError, ValueError) as exc:
            raise AuditError("Order 95 audit is unavailable or malformed.") from exc
    if not isinstance(payload, dict):
        raise AuditError("Order 95 audit must be an object.")
    validate_audit(payload)
    return payload


def validate_audit(audit: dict[str, Any], *, root: Path = ROOT, roadmap: str | None = None) -> None:
    # Independent pin covers every nested observation, limit, status and reference.
    # Updating a nested self-reported hash cannot silently upgrade this audit.
    if fingerprint(audit) != REVIEW_SHA256:
        raise AuditError("Order 95 immutable review identity changed.")
    if (
        audit["outcome"] != "gaps_found_not_certified"
        or audit["runtime_input"]
        or audit["operative_clause_certification_complete"]
        or audit["caudit_01_closed"]
    ):
        raise AuditError("Order 95 is a negative survey, not a certificate.")
    selected = audit["source_selection"]
    observation = {key: value for key, value in selected.items() if key != "observation_sha256"}
    if fingerprint(observation) != selected["observation_sha256"]:
        raise AuditError("Order 95 source observation identity drifted.")
    history = json.loads(_verified_file(selected["historical_inventory"], root))
    inventory = history["source_inventory"]
    if fingerprint(inventory) != selected["source_inventory_sha256"]:
        raise AuditError("Order 95 source inventory identity drifted.")
    if len(inventory) != 345 or sum(len(row["blocks"]) for row in inventory) != 1424:
        raise AuditError("Order 95 source row/block inventory is incomplete.")
    source_rows = {row["row_id"]: row for row in inventory}
    reviews = audit["row_reviews"]
    if len(reviews) != len(source_rows) or {row["row_id"] for row in reviews} != set(source_rows):
        raise AuditError("Order 95 must disposition every source row and FAQ.")
    for row in reviews:
        if (
            row["source_row_sha256"] != fingerprint(source_rows[row["row_id"]])
            or row["clause_certification"] != "open"
        ):
            raise AuditError("Order 95 row evidence cannot become a clause certificate.")
    override = json.loads(
        _verified_file(selected["heroic_intervention_override"]["evidence"], root)
    )
    if override["audit_id"] != "order94-2026-09-28" or override["caudit_01_closed"]:
        raise AuditError("Order 95 Heroic Intervention selection drifted.")
    _verified_file(audit["probe_results"], root)
    categories = {row["category"]: row for row in audit["category_reviews"]}
    if set(categories) != {f"{i:02d}" for i in range(1, 26)}:
        raise AuditError("Order 95 category survey is incomplete.")
    evidence_ids = {"category:" + category for category in categories}
    evidence_ids.update(row["evidence_id"] for row in audit["cross_category_reviews"])
    for row in (*reviews, *audit["changelog_reviews"]):
        if row["evidence_id"] is not None and row["evidence_id"] not in evidence_ids:
            raise AuditError("Order 95 review references an unknown evidence owner.")
    expected_entries = {
        f"{version['version']}:{kind}:{i}"
        for version in audit["version_inventory"]
        for kind in ("change", "note")
        for i in range(1, version[f"{kind}_count"] + 1)
    }
    changelog = audit["changelog_reviews"]
    if len(changelog) != 91 or {row["entry_id"] for row in changelog} != expected_entries:
        raise AuditError("Order 95 older changelog disposition inventory is incomplete.")
    for row in changelog:
        if not set(row["source_rows"]) <= set(source_rows):
            raise AuditError("Order 95 changelog points to an unknown source row.")
    # Preserve hashes of the reviewed tree, but do not demand future source files
    # keep those historical contents after a repair. References must resolve to
    # their current owner or an explicitly recorded retirement and its successors.
    references = [row["path"] for row in audit["evidence_files"]]
    references.extend(ref for row in audit["cross_category_reviews"] for ref in row["regressions"])
    references.extend(ref for row in audit["findings"] for ref in row["owners"])
    if not set(RETIRED_REFERENCE_SUCCESSORS) <= set(references):
        raise AuditError("Order 95 retirement mapping has no historical reference.")
    for reference in references:
        validate_owner_reference(reference, root)
    document = (
        (root / "docs/CORE_RULES_REMEDIATION_ROADMAP.md").read_text()
        if roadmap is None
        else roadmap
    )
    try:
        planned = roadmap_rows(document)
    except ValueError as exc:
        raise AuditError("Order 95 roadmap is incomplete or malformed.") from exc
    owners = {finding: row for row in planned for finding in row.finding_ids}
    for finding, pr_id in FINDING_OWNERS.items():
        if finding not in owners or owners[finding].pr_id != pr_id:
            raise AuditError(f"Order 95 repair owner is missing: {finding}.")
        if pr_id not in planned[-1].prerequisites:
            raise AuditError(f"Order 95 repair must precede PFINAL: {pr_id}.")


def changelog_versions(html: str) -> list[dict[str, Any]]:
    """Read public server-rendered JSON literals; never execute downloaded code."""
    chunks = re.findall(r'self\.__next_f\.push\((\[1,"(?:[^"\\]|\\.)*"\])\)', html)
    flight = "".join(json.loads(chunk)[1] for chunk in chunks)
    marker = '"versions":'
    if flight.count(marker) != 1:
        raise AuditError("Order 95 changelog versions marker drifted.")
    try:
        value, _ = json.JSONDecoder().raw_decode(flight.split(marker, 1)[1])
    except ValueError as exc:
        raise AuditError("Order 95 changelog version data is malformed.") from exc
    if not isinstance(value, list) or not all(isinstance(item, dict) for item in value):
        raise AuditError("Order 95 changelog versions must be objects.")
    return value


def verify_captures(
    audit: dict[str, Any], *, core: Path | None = None, changelog: Path | None = None
) -> None:
    if core is not None:
        raw = core.read_bytes()
        selected = audit["source_selection"]
        if hashlib.sha256(raw).hexdigest() != selected["asset_sha256"]:
            raise AuditError("Order 95 Core capture hash differs from the observed asset.")
        rows = source_inventory(capture_literals(raw.decode("utf-8")))
        if fingerprint(rows) != selected["source_inventory_sha256"]:
            raise AuditError("Order 95 Core capture does not reproduce the source inventory.")
    if changelog is not None:
        raw = changelog.read_bytes()
        observed = audit["changelog_observation"]
        if hashlib.sha256(raw).hexdigest() != observed["html_sha256"]:
            raise AuditError("Order 95 changelog capture hash differs from the observation.")
        versions = changelog_versions(raw.decode("utf-8"))
        if fingerprint(versions) != observed["parsed_versions_sha256"]:
            raise AuditError("Order 95 changelog capture does not reproduce the version inventory.")
        entries = {
            f"{version['version']}:{kind}:{i}": fingerprint(value)
            for version in versions
            for kind, field in (("change", "changes"), ("note", "notes"))
            for i, value in enumerate(version.get(field, []), 1)
        }
        if entries != {row["entry_id"]: row["entry_sha256"] for row in audit["changelog_reviews"]}:
            raise AuditError("Order 95 changelog entry fingerprints differ.")


def markdown(audit: dict[str, Any]) -> str:
    selected = audit["source_selection"]
    lines = [
        "# Order 95 — negative Core Rules audit",
        "",
        "Generated by `uv run python -m tools.core_rules_order95_audit`; use `--check` to verify.",
        "",
        f"Reviewed runtime: `{audit['reviewed_commit']}` (merged Order 94).",
        "**Gaps found; CAUDIT-01 remains open.** P04E, P24K and PEVIDENCE precede PFINAL.",
        "The owner authorized completing the survey and scheduling repairs instead of "
        "changing gameplay in this PR.",
        "",
        "## Source identity and coverage",
        "",
        f"Game Datamissions Core observation: `{selected['observed_at']}`. "
        f"Asset SHA-256: `{selected['asset_sha256']}`.",
        "The live body is unversioned. The 345 rule/update/FAQ rows and 1,424 rendered "
        "blocks exactly reproduce the historical inventory; these are not counts of "
        "operative clauses.",
        "The known-truncated GDM 15.11 row is retained but not selected: the complete "
        "[Order 94 observation](ORDER_94_SOURCE_REVIEW.md) remains authoritative for "
        "that section.",
        "",
        "The [machine-readable inventory](../data/source_audits/order95/audit.json) "
        "gives every source row its immutable block-set identity, selected observation, "
        "current category owner/evidence and open certification status. It also pins "
        "all 52 current Core packages with separate load/execution statuses, 20 "
        "September 10 dispositions and all 11 prior audit repairs.",
        "No source package is upgraded to gameplay certification by loading, merging or "
        "passing tests.",
        "",
        "## Findings",
        "",
    ]
    for finding in audit["findings"]:
        lines += [
            f"### {finding['finding_id']} / {finding['pr_id']}",
            "",
            finding["summary"],
            "",
            f"Violated invariant: {finding['invariant']}",
            "",
            f"Required repair: {finding['required_repair']}",
            "",
            f"Evidence limit: {finding['evidence_limit']}",
            "",
        ]
    lines += [
        "## Category dispositions",
        "",
        "Every category remains open for an individual-clause facade certificate.",
        "",
        "| Category | Current survey disposition |",
        "|---|---|",
    ]
    for row in audit["category_reviews"]:
        lines.append(f"| {row['category']} {row['title']} | {row['assessment']} |")
    lines += [
        "",
        "## Explicit cross-category checks",
        "",
        "| Evidence | Review and limits |",
        "|---|---|",
    ]
    for row in audit["cross_category_reviews"]:
        lines.append(f"| {row['evidence_id']} | {row['assessment']} |")
    lines += [
        "",
        "Exact regression node IDs and inspected file hashes are in the JSON inventory. "
        "[Validation and reproduction](ORDER_95_AUDIT_NOTES.md) distinguish passing "
        "checks from certification.",
        "",
        "## Complete changelog disposition inventory",
        "",
        "All 12 observed version records, including empty versions, are fingerprinted. "
        "There are 85 changes and six provider notes. v931's splitting rule and "
        "duplicate erratum remain separate observations of one obligation; its Ongoing "
        "erratum remains superseded by the owner's v946 resolution. Mission-document "
        "and translation-only entries are explicitly classified, not silently dropped. "
        "FAQ numbers preserve observed inventory order; exact provider IDs remain in the JSON.",
        "",
        "| Entry | Selected current source row(s) | Disposition / evidence |",
        "|---|---|---|",
    ]
    faq_labels = {
        row["row_id"]: f"FAQ {number:02d}"
        for number, row in enumerate(
            (row for row in audit["row_reviews"] if row["row_id"].startswith("faq:")), 1
        )
    }
    for row in audit["changelog_reviews"]:
        sources = (
            ", ".join(
                faq_labels[source] if source.startswith("faq:") else f"`{source}`"
                for source in row["source_rows"]
            )
            or "—"
        )
        evidence = row["evidence_id"] or "no Core engine obligation"
        lines.append(f"| {row['entry_id']} | {sources} | {row['disposition']}; {evidence} |")
    lines += ["", "## Remaining certification work", ""]
    lines += [f"- {limit}" for limit in audit["limits"]]
    lines += [
        "",
        "Complete-game performance is separately **uncertified**: zero full-game "
        "samples, unknown mean and maximum. No runtime algorithm changed and no "
        "performance budget is claimed passed.",
        "",
    ]
    return "\n".join(lines)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--check", action="store_true")
    parser.add_argument("--verify-core-capture", type=Path)
    parser.add_argument("--verify-changelog-capture", type=Path)
    args = parser.parse_args()
    audit = load_audit()
    verify_captures(audit, core=args.verify_core_capture, changelog=args.verify_changelog_capture)
    expected = markdown(audit)
    if args.check:
        if REPORT.read_text(encoding="utf-8") != expected:
            raise AuditError("Order 95 generated report is stale.")
    else:
        REPORT.write_text(expected, encoding="utf-8")
    print("Order 95 negative audit verified; CAUDIT-01 remains open.")


if __name__ == "__main__":
    main()
