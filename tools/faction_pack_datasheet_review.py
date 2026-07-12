from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from enum import StrEnum
from functools import cache
from pathlib import Path
from typing import Any, cast

REPO_ROOT = Path(__file__).resolve().parents[1]
MANIFEST_PATH = REPO_ROOT / "data" / "source_manifests" / "faction_pack_datasheet_review_v1.json"
SOURCE_DATASHEETS_PATH = (
    REPO_ROOT
    / "data"
    / "source_snapshots"
    / "wahapedia"
    / ("1" + "0" + "th-edition")
    / "2026-06-14"
    / "json"
    / "Datasheets.json"
)
RAW_PDF_DIR = REPO_ROOT / "data" / "raw" / "faction_packs"
MANIFEST_SCHEMA_VERSION = "1"


class DatasheetSourceTreatment(StrEnum):
    COMPLETE_PDF = "complete_pdf"
    RULES_UPDATE = "rules_update"
    UNCHANGED_PREDECESSOR = "unchanged_predecessor"


@dataclass(frozen=True, slots=True)
class FactionPackDatasheetReviewRow:
    review_row_id: str
    datasheet_id: str | None
    datasheet_name: str
    group: str
    treatment: DatasheetSourceTreatment
    pdf_page_reference: str | None
    review_note: str


@dataclass(frozen=True, slots=True)
class FactionPackDatasheetReview:
    faction_id: str
    faction_name: str
    source_faction_id: str
    source_id: str
    pdf_filename: str
    pdf_sha256: str
    scope_note: str
    exclusions_note: str
    additional_source_datasheet_ids: tuple[str, ...]
    rows: tuple[FactionPackDatasheetReviewRow, ...]

    def rows_for(
        self, treatment: DatasheetSourceTreatment
    ) -> tuple[FactionPackDatasheetReviewRow, ...]:
        return tuple(row for row in self.rows if row.treatment is treatment)

    def treatment_counts(self) -> dict[DatasheetSourceTreatment, int]:
        return {treatment: len(self.rows_for(treatment)) for treatment in DatasheetSourceTreatment}


@cache
def faction_pack_datasheet_reviews() -> tuple[FactionPackDatasheetReview, ...]:
    payload = _load_json_object(MANIFEST_PATH)
    if payload.get("schema_version") != MANIFEST_SCHEMA_VERSION:
        raise ValueError(
            "Faction Pack datasheet review manifest has an unsupported schema version."
        )
    _validate_source_snapshot(payload)
    raw_factions = _required_list(payload, "factions")
    reviews = tuple(_parse_faction(raw_faction) for raw_faction in raw_factions)
    faction_ids = tuple(review.faction_id for review in reviews)
    if len(faction_ids) != len(set(faction_ids)):
        raise ValueError("Faction Pack datasheet review manifest contains duplicate factions.")
    if "chaos-daemons" in faction_ids:
        raise ValueError(
            "Chaos Daemons must remain outside the generic Faction Pack review manifest."
        )
    _validate_source_partitions(reviews)
    return reviews


def faction_pack_datasheet_review(faction_id: str) -> FactionPackDatasheetReview:
    matches = tuple(
        review for review in faction_pack_datasheet_reviews() if review.faction_id == faction_id
    )
    if len(matches) != 1:
        raise ValueError(f"Expected exactly one Faction Pack datasheet review for {faction_id!r}.")
    return matches[0]


def reviewed_faction_ids() -> frozenset[str]:
    return frozenset(review.faction_id for review in faction_pack_datasheet_reviews())


def faction_pack_datasheet_snapshot_markdown(faction_id: str) -> list[str]:
    review = faction_pack_datasheet_review(faction_id)
    counts = review.treatment_counts()
    total = len(review.rows)
    return [
        "",
        "### Unit Datasheet Source Treatments",
        "",
        "| Review bucket | Count | Source treatment |",
        "| --- | ---: | --- |",
        (
            f"| Complete Faction Pack datasheets | "
            f"{counts[DatasheetSourceTreatment.COMPLETE_PDF]} | "
            "The complete Faction Pack datasheet is authoritative. |"
        ),
        (
            f"| Faction Pack datasheet updates | "
            f"{counts[DatasheetSourceTreatment.RULES_UPDATE]} | "
            "The pinned predecessor row is retained with the cited Rules Update applied. |"
        ),
        (
            f"| Unchanged predecessor datasheets | "
            f"{counts[DatasheetSourceTreatment.UNCHANGED_PREDECESSOR]} | "
            "The pinned predecessor row is retained after explicit PDF review. |"
        ),
        f"| **Datasheets reviewed** | **{total}** | {review.exclusions_note} |",
    ]


def faction_pack_datasheet_review_markdown(faction_id: str) -> list[str]:
    review = faction_pack_datasheet_review(faction_id)
    lines = [
        "### Source scope, provenance, and exclusions",
        "",
        review.scope_note,
        "",
        review.exclusions_note,
        "",
        (
            f"The review is pinned to `{review.pdf_filename}` (SHA-256 "
            f"`{review.pdf_sha256}`) and the versioned predecessor source snapshot recorded "
            "in the review manifest. Every in-scope source ID occurs exactly once, every "
            "source-backed name is checked against that snapshot, and treatment counts are "
            "derived from the validated rows below."
        ),
        "",
        (
            "These rows are source-reviewed only. They do not claim catalog load support or "
            "semantic execution; those statuses require separate generated catalog and runtime "
            "evidence."
        ),
        "",
    ]
    groups = tuple(dict.fromkeys(row.group for row in review.rows))
    for group in groups:
        lines.extend(
            _group_markdown(group, tuple(row for row in review.rows if row.group == group))
        )
    return lines[:-1]


def _group_markdown(group: str, rows: tuple[FactionPackDatasheetReviewRow, ...]) -> list[str]:
    lines = [
        f"### {group}",
        "",
        "| Datasheet | Explicit treatment | PDF reference | Review note |",
        "| --- | --- | --- | --- |",
    ]
    for row in sorted(rows, key=lambda item: (item.datasheet_name.lower(), item.review_row_id)):
        identifier = f" (`{row.datasheet_id}`)" if row.datasheet_id is not None else " (PDF-only)"
        page_reference = row.pdf_page_reference or "Not reprinted or updated"
        lines.append(
            f"| {row.datasheet_name}{identifier} | `{row.treatment.value}` | "
            f"{page_reference} | {row.review_note} |"
        )
    lines.append("")
    return lines


def _parse_faction(raw: object) -> FactionPackDatasheetReview:
    payload = _object(raw, "faction review")
    rows = tuple(_parse_row(raw_row) for raw_row in _required_list(payload, "rows"))
    if not rows:
        raise ValueError("Faction Pack datasheet review factions must contain reviewed rows.")
    review_row_ids = tuple(row.review_row_id for row in rows)
    if len(review_row_ids) != len(set(review_row_ids)):
        raise ValueError("Faction Pack datasheet review contains duplicate review row IDs.")
    datasheet_ids = tuple(row.datasheet_id for row in rows if row.datasheet_id is not None)
    if len(datasheet_ids) != len(set(datasheet_ids)):
        raise ValueError("Faction Pack datasheet review contains duplicate source datasheet IDs.")
    review = FactionPackDatasheetReview(
        faction_id=_required_text(payload, "faction_id"),
        faction_name=_required_text(payload, "faction_name"),
        source_faction_id=_required_text(payload, "source_faction_id"),
        source_id=_required_text(payload, "source_id"),
        pdf_filename=_required_text(payload, "pdf_filename"),
        pdf_sha256=_required_sha256(payload, "pdf_sha256"),
        scope_note=_required_text(payload, "scope_note"),
        exclusions_note=_required_text(payload, "exclusions_note"),
        additional_source_datasheet_ids=tuple(
            _text(item, "additional source datasheet ID")
            for item in _required_list(payload, "additional_source_datasheet_ids")
        ),
        rows=rows,
    )
    pdf_path = RAW_PDF_DIR / review.pdf_filename
    if not pdf_path.is_file():
        raise ValueError(f"Faction Pack PDF is missing: {pdf_path}.")
    if _sha256(pdf_path) != review.pdf_sha256:
        raise ValueError(f"Faction Pack PDF hash drifted for {review.faction_id!r}.")
    return review


def _parse_row(raw: object) -> FactionPackDatasheetReviewRow:
    payload = _object(raw, "datasheet review row")
    datasheet_id_value = payload.get("datasheet_id")
    datasheet_id = None if datasheet_id_value is None else _text(datasheet_id_value, "datasheet_id")
    treatment_text = _required_text(payload, "treatment")
    try:
        treatment = DatasheetSourceTreatment(treatment_text)
    except ValueError as exc:
        raise ValueError(f"Unknown datasheet source treatment {treatment_text!r}.") from exc
    page_value = payload.get("pdf_page_reference")
    page_reference = None if page_value is None else _text(page_value, "pdf_page_reference")
    if treatment is not DatasheetSourceTreatment.UNCHANGED_PREDECESSOR and page_reference is None:
        raise ValueError("Complete and Rules Update rows require a PDF page reference.")
    if datasheet_id is None and treatment is not DatasheetSourceTreatment.COMPLETE_PDF:
        raise ValueError("PDF-only rows must use the complete_pdf treatment.")
    return FactionPackDatasheetReviewRow(
        review_row_id=_required_text(payload, "review_row_id"),
        datasheet_id=datasheet_id,
        datasheet_name=_required_text(payload, "datasheet_name"),
        group=_required_text(payload, "group"),
        treatment=treatment,
        pdf_page_reference=page_reference,
        review_note=_required_text(payload, "review_note"),
    )


def _validate_source_snapshot(payload: dict[str, Any]) -> None:
    source = _object(payload.get("source_snapshot"), "source_snapshot")
    source_payload = _source_payload()
    if _required_text(source, "datasheets_artifact_hash") != source_payload["artifact_hash"]:
        raise ValueError("Faction Pack review source artifact hash does not match Datasheets.json.")
    if _required_sha256(source, "datasheets_sha256") != _sha256(SOURCE_DATASHEETS_PATH):
        raise ValueError("Faction Pack review source file hash does not match Datasheets.json.")
    if source.get("source_package_id") != source_payload["source_package_id"]:
        raise ValueError(
            "Faction Pack review source package identity does not match Datasheets.json."
        )


def _validate_source_partitions(reviews: tuple[FactionPackDatasheetReview, ...]) -> None:
    source_rows = cast(list[dict[str, Any]], _source_payload()["rows"])
    rows_by_id = {cast(str, row["fields"]["id"]): row for row in source_rows}
    for review in reviews:
        expected_ids = {
            cast(str, row["fields"]["id"])
            for row in source_rows
            if row["fields"]["faction_id"] == review.source_faction_id
            and row["fields"]["source_id"] == review.source_id
            and row["fields"]["virtual"] == "false"
        }
        additional_ids = set(review.additional_source_datasheet_ids)
        if len(additional_ids) != len(review.additional_source_datasheet_ids):
            raise ValueError(f"Duplicate additional source ID for {review.faction_id!r}.")
        missing_additions = additional_ids - rows_by_id.keys()
        if missing_additions:
            raise ValueError(
                f"Unknown additional source IDs for {review.faction_id!r}: {missing_additions}."
            )
        expected_ids.update(additional_ids)
        source_backed_rows = tuple(row for row in review.rows if row.datasheet_id is not None)
        actual_ids = {cast(str, row.datasheet_id) for row in source_backed_rows}
        if actual_ids != expected_ids:
            missing_ids = sorted(expected_ids - actual_ids)
            extra_ids = sorted(actual_ids - expected_ids)
            raise ValueError(
                f"Faction Pack review partition drift for {review.faction_id!r}: "
                f"missing={missing_ids!r}, extra={extra_ids!r}."
            )
        for row in source_backed_rows:
            source_row = rows_by_id[cast(str, row.datasheet_id)]
            source_name = cast(str, source_row["fields"]["name"])
            if row.datasheet_name != source_name:
                raise ValueError(
                    f"Faction Pack review name drift for {row.review_row_id!r}: "
                    f"manifest={row.datasheet_name!r}, source={source_name!r}."
                )


@cache
def _source_payload() -> dict[str, Any]:
    return _load_json_object(SOURCE_DATASHEETS_PATH)


def _load_json_object(path: Path) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise ValueError(f"Invalid JSON in {path}.") from exc
    return _object(value, str(path))


def _object(value: object, label: str) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise TypeError(f"{label} must be a JSON object.")
    return cast(dict[str, Any], value)


def _required_list(payload: dict[str, Any], key: str) -> list[object]:
    value = payload.get(key)
    if not isinstance(value, list):
        raise TypeError(f"{key!r} must be a JSON list.")
    return cast(list[object], value)


def _required_text(payload: dict[str, Any], key: str) -> str:
    if key not in payload:
        raise ValueError(f"Missing required field {key!r}.")
    return _text(payload[key], key)


def _text(value: object, label: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{label!r} must be non-empty text.")
    return value


def _required_sha256(payload: dict[str, Any], key: str) -> str:
    value = _required_text(payload, key)
    if len(value) != 64 or any(character not in "0123456789abcdef" for character in value):
        raise ValueError(f"{key!r} must be a lowercase SHA-256 digest.")
    return value


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()
