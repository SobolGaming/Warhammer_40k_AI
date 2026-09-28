"""Offline, immutable P15J source review; never a runtime rule-text parser."""

from __future__ import annotations

import argparse
import hashlib
import json
from collections.abc import Mapping
from html.parser import HTMLParser
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, ConfigDict

from tools.core_rules_order84_capture import fingerprint

ROOT = Path(__file__).resolve().parents[1]
AUDIT = ROOT / "data/source_audits/order94/audit.json"
REPORT = ROOT / "docs/ORDER_94_SOURCE_REVIEW.md"
REVIEW_SHA256 = "f9df7b7c917b2fd17e11f8eed5afdb185ad74a3a7666572ed26ebd03f503f215"


class SourceReviewError(ValueError):
    """Retained Order 94 evidence is incomplete, changed or misrepresented."""


class ReviewRecord(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True, frozen=True)


class FileEvidence(ReviewRecord):
    path: str
    sha256: str


class Observation(ReviewRecord):
    provider_name: Literal["40k.app"]
    provider_non_affiliation_recorded: Literal[True]
    source_url: str
    observed_at: str
    app_data_version: None
    app_build: None
    policy_id: str
    rule_source_id: str
    capture: FileEvidence
    capture_method: str
    transcription: str
    transcription_sha256: str
    source_observation_sha256: str
    load_support_status: Literal["not_loaded_review_artifact"]
    semantic_execution_status: Literal["not_reassessed"]


class HistoricalGdm(ReviewRecord):
    audit_path: str
    audit_sha256: str
    audit_id: str
    row_id: str
    observation: dict[str, object]
    source_row_sha256: str
    blocks: list[str]
    completeness: Literal["truncated_not_selected"]
    retrieval_note: str


class OfficialEvidence(FileEvidence):
    source_id: str
    page: Literal[57]
    locator: Literal["15.11"]
    review_method: str
    app_data_version: None
    comparison: Literal["operative_wording_matches_not_version_equivalence"]


class ClauseReview(ReviewRecord):
    clause_id: str
    description: str
    selected_text: str
    official_pdf_review: Literal["matches_selected_operative_wording"]
    gdm_block_ordinals: list[int]
    gdm_disposition: Literal["present", "partial", "omitted"]
    difference: str
    engine_owner: str
    regression: str


class SourceReview(ReviewRecord):
    schema_id: Literal["core-v2-order94-source-review-v1"]
    audit_id: Literal["order94-2026-09-28"]
    finding_id: Literal["C15-10"]
    pr_id: Literal["P15J"]
    reviewed_commit: str
    runtime_input: Literal[False]
    caudit_01_closed: Literal[False]
    outcome: Literal["complete_selected_observation_reconciled"]
    comparison_status: Literal["unversioned_observations_not_co_versioned"]
    selected_observation: Observation
    historical_gdm: HistoricalGdm
    official_evidence: OfficialEvidence
    prior_implementation_review: FileEvidence
    clause_reviews: list[ClauseReview]
    limits: list[str]


class _SectionText(HTMLParser):
    """Preserve inline text; separate block boundaries in the retained DOM fragment."""

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.parts: list[str] = []

    def handle_data(self, data: str) -> None:
        self.parts.append(data)

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag in {"div", "p", "h2", "ul", "li"}:
            self.parts.append("\n")

    def handle_endtag(self, tag: str) -> None:
        if tag in {"div", "p", "h2", "ul", "li"}:
            self.parts.append("\n")


def transcribe_capture(html: str) -> str:
    parser = _SectionText()
    parser.feed(html)
    parser.close()
    lines = (" ".join(line.split()) for line in "".join(parser.parts).splitlines())
    return "\n".join(line for line in lines if line)


def _sha256(raw: bytes) -> str:
    return hashlib.sha256(raw).hexdigest()


def source_observation_fingerprint(metadata: Mapping[str, object]) -> str:
    excluded = {"source_observation_sha256", "load_support_status", "semantic_execution_status"}
    return fingerprint({key: value for key, value in metadata.items() if key not in excluded})


def _verified_file(evidence: FileEvidence, root: Path, label: str) -> bytes:
    path = root / evidence.path
    if not path.is_relative_to(root) or ".." in Path(evidence.path).parts:
        raise SourceReviewError(f"Order 94 {label} path escapes the review root.")
    try:
        raw = path.read_bytes()
    except OSError as exc:
        raise SourceReviewError(f"Order 94 {label} is unavailable: {evidence.path}.") from exc
    if _sha256(raw) != evidence.sha256:
        raise SourceReviewError(f"Order 94 {label} hash differs from retained evidence.")
    return raw


def load_audit(*, payload: object | None = None) -> SourceReview:
    try:
        if payload is None:
            payload = json.loads(AUDIT.read_text(encoding="utf-8"))
        audit = SourceReview.model_validate(payload)
    except (OSError, ValueError) as exc:
        raise SourceReviewError("Order 94 source review is malformed or unavailable.") from exc
    validate_audit(audit)
    return audit


def validate_audit(audit: SourceReview, *, root: Path = ROOT) -> None:
    if fingerprint(audit.model_dump()) != REVIEW_SHA256:
        raise SourceReviewError("Order 94 immutable review identity changed.")
    observation = audit.selected_observation
    raw = _verified_file(observation.capture, root, "capture")
    if transcribe_capture(raw.decode("utf-8")) != observation.transcription:
        raise SourceReviewError("Order 94 transcription does not reproduce the capture.")
    if _sha256(observation.transcription.encode()) != observation.transcription_sha256:
        raise SourceReviewError("Order 94 transcription hash drifted.")
    if (
        source_observation_fingerprint(observation.model_dump())
        != observation.source_observation_sha256
    ):
        raise SourceReviewError("Order 94 source observation fingerprint drifted.")
    history = audit.historical_gdm
    historical_raw = _verified_file(
        FileEvidence(path=history.audit_path, sha256=history.audit_sha256), root, "historical audit"
    )
    historical = json.loads(historical_raw)
    if (
        historical["observation"] != history.observation
        or historical["audit_id"] != history.audit_id
    ):
        raise SourceReviewError("Order 94 historical observation identity differs.")
    rows = [row for row in historical["source_inventory"] if row["row_id"] == history.row_id]
    if len(rows) != 1 or fingerprint(rows[0]) != history.source_row_sha256:
        raise SourceReviewError("Order 94 historical source row differs.")
    expected_blocks = [
        {"ordinal": i, "kind": "stratagem", "sha256": fingerprint(text)}
        for i, text in enumerate(history.blocks, 1)
    ]
    if rows[0]["blocks"] != expected_blocks:
        raise SourceReviewError("Order 94 GDM blocks do not reproduce the historical fingerprints.")
    _verified_file(audit.official_evidence, root, "official PDF")
    _verified_file(audit.prior_implementation_review, root, "Order 50 review")
    for clause in audit.clause_reviews:
        if clause.selected_text not in observation.transcription:
            raise SourceReviewError(f"Order 94 selected clause is absent: {clause.clause_id}.")
        if any(not 1 <= ordinal <= len(history.blocks) for ordinal in clause.gdm_block_ordinals):
            raise SourceReviewError("Order 94 clause points outside the GDM block inventory.")
        for reference in (clause.engine_owner, clause.regression):
            path, symbol = reference.split(":", 1)
            if not (root / path).is_file() or symbol not in (root / path).read_text():
                raise SourceReviewError(
                    f"Order 94 owner/regression reference is absent: {reference}."
                )


def markdown(audit: SourceReview) -> str:
    observation = audit.selected_observation
    lines = [
        "# Order 94 / P15J — Heroic Intervention source review",
        "",
        "Generated by `uv run python -m tools.core_rules_order94_audit`; "
        "append `--check` to verify.",
        "",
        "C15-10 source-evidence closure: complete selected observation retained and reconciled.",
        "CAUDIT-01 / PFINAL remains open. No new gameplay certification is asserted.",
        "",
        f"Selected provider: [{observation.provider_name}]({observation.source_url}), "
        f"observed `{observation.observed_at}`. Non-affiliated maintained App-data mirror.",
        "App-data version and App build: **not exposed**. No v931/v946 identity is inferred.",
        f"Stable rule ID: `{observation.rule_source_id}`.",
        f"Policy: `{observation.policy_id}`.",
        "",
        f"- [Retained DOM section](../{observation.capture.path}); SHA-256 "
        f"`{observation.capture.sha256}`.",
        f"- Exact derived transcription SHA-256: `{observation.transcription_sha256}`.",
        f"- Source-observation fingerprint: `{observation.source_observation_sha256}`.",
        "- [Typed review inventory](../data/source_audits/order94/audit.json) includes all "
        "ten operative comparisons and the eight historical GDM blocks.",
        "",
        "## Reconciliation",
        "",
        "The retained official PDF, page 57 / 15.11, agrees on every operative clause below.",
        f"Its SHA-256 is `{audit.official_evidence.sha256}`. "
        "This is wording corroboration, not an assertion that a June PDF and an unversioned "
        "September mirror share an App version.",
        "",
        "The GDM comparison uses the immutable September 24 observation from the "
        "[Order 84 negative audit](ORDER_84_AUDIT_NOTES.md). The exact pinned public asset "
        "was retrieved again and its eight blocks reproduced the historical hashes. "
        "Retrieval does not redate or version that observation.",
        "",
        "| Operative requirement | Historical GDM | Reconciliation |",
        "|---|---|---|",
    ]
    for clause in audit.clause_reviews:
        lines.append(f"| {clause.description} | {clause.gdm_disposition} | {clause.difference} |")
    lines.extend(["", "## Boundaries", ""])
    lines.extend(f"- {limit}" for limit in audit.limits)
    lines.extend(
        ["", "See [scope and validation](ORDER_94_SCOPE_PLAN.md) for the delivery record.", ""]
    )
    return "\n".join(lines)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--check", action="store_true")
    args = parser.parse_args()
    audit = load_audit()
    report = markdown(audit)
    if args.check:
        if not REPORT.is_file() or REPORT.read_text(encoding="utf-8") != report:
            raise SourceReviewError("Order 94 report is stale; regenerate the reviewed report.")
    else:
        REPORT.write_text(report, encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
