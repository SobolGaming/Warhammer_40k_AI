from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from functools import cache
from pathlib import Path
from typing import TYPE_CHECKING, Any, cast

if TYPE_CHECKING or __package__:
    from tools.faction_pack_datasheet_review import faction_pack_datasheet_review
else:
    from faction_pack_datasheet_review import faction_pack_datasheet_review

from warhammer40k_core.engine.ability_coverage import AbilityCoverageSupportStage
from warhammer40k_core.rules.source_overlay import (
    SourceOverlayPack,
    SourceOverlayPackPayload,
    SourceReleaseManifest,
    SourceReleaseManifestPayload,
)

REPO_ROOT = Path(__file__).resolve().parents[1]
COVERAGE_PATH = (
    REPO_ROOT
    / "data"
    / "generated"
    / "ability_coverage"
    / "aeldari_datasheet_semantic_coverage.json"
)
OVERLAY_DIR = REPO_ROOT / "data" / "source_overlays" / "aeldari_faction_pack_2026_06"
OVERLAY_PACK_PATH = OVERLAY_DIR / "aeldari-faction-pack-datasheet-overlay.overlay-pack.json"
RELEASE_MANIFEST_PATH = OVERLAY_DIR / "source_release_manifest.json"
SOURCE_DATASHEETS_PATH = (
    REPO_ROOT
    / "data"
    / "source_snapshots"
    / "wahapedia"
    / "10th-edition"
    / "2026-06-14"
    / "json"
    / "Datasheets.json"
)
SCHEMA_VERSION = "aeldari-datasheet-semantic-coverage-v1"
SEMANTIC_BUCKET_ALL_CONSUMED = "All consumed"
SEMANTIC_BUCKET_HOST_NEEDED = "IR parsed; host needed"
SEMANTIC_BUCKET_UNSUPPORTED_IR = "Unsupported IR"
SEMANTIC_BUCKET_BRIDGE_BLOCKED = "Bridge/catalog blocked"
SEMANTIC_BUCKETS = (
    SEMANTIC_BUCKET_ALL_CONSUMED,
    SEMANTIC_BUCKET_HOST_NEEDED,
    SEMANTIC_BUCKET_UNSUPPORTED_IR,
    SEMANTIC_BUCKET_BRIDGE_BLOCKED,
)


@dataclass(frozen=True, slots=True)
class AeldariDatasheetAbilitySemanticCoverage:
    ability_id: str
    ability_name: str
    source_kind: str
    source_row_id: str
    raw_text: str
    raw_text_sha256: str
    normalized_text_sha256: str
    catalog_support: str
    support_stage: AbilityCoverageSupportStage
    runtime_consumer_ids: tuple[str, ...]
    diagnostic_reasons: tuple[str, ...]
    source_ids: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class AeldariDatasheetSemanticCoverage:
    datasheet_id: str
    datasheet_name: str
    group: str
    treatment: str
    pdf_page_reference: str | None
    semantic_bucket: str
    abilities: tuple[AeldariDatasheetAbilitySemanticCoverage, ...]


@dataclass(frozen=True, slots=True)
class AeldariSemanticCoverageArtifact:
    overlay_pack_hash: str
    release_hash: str
    rows: tuple[AeldariDatasheetSemanticCoverage, ...]


@cache
def aeldari_datasheet_semantic_coverage() -> AeldariSemanticCoverageArtifact:
    payload = _load_object(COVERAGE_PATH)
    if payload.get("schema_version") != SCHEMA_VERSION:
        raise ValueError("Aeldari datasheet semantic coverage schema version is unsupported.")
    review = faction_pack_datasheet_review("aeldari")
    if payload.get("faction_id") != review.faction_id:
        raise ValueError("Aeldari semantic coverage faction identity drifted.")
    if payload.get("pdf_filename") != review.pdf_filename:
        raise ValueError("Aeldari semantic coverage PDF filename drifted.")
    if payload.get("pdf_sha256") != review.pdf_sha256:
        raise ValueError("Aeldari semantic coverage PDF hash drifted.")
    if payload.get("source_datasheets_sha256") != _sha256_file(SOURCE_DATASHEETS_PATH):
        raise ValueError("Aeldari semantic coverage source snapshot hash drifted.")
    overlay_pack = SourceOverlayPack.from_payload(
        cast(SourceOverlayPackPayload, _load_object(OVERLAY_PACK_PATH))
    )
    release_manifest = SourceReleaseManifest.from_payload(
        cast(SourceReleaseManifestPayload, _load_object(RELEASE_MANIFEST_PATH))
    )
    overlay_pack_hash = _required_sha256(payload, "overlay_pack_hash")
    release_hash = _required_sha256(payload, "release_hash")
    if overlay_pack_hash != overlay_pack.package_hash():
        raise ValueError("Aeldari semantic coverage overlay hash drifted.")
    if release_hash != release_manifest.release_hash():
        raise ValueError("Aeldari semantic coverage release hash drifted.")
    raw_rows = _required_list(payload, "datasheets")
    rows = tuple(_parse_datasheet(row) for row in raw_rows)
    _validate_rows(rows)
    expected_treatment_counts = {
        treatment.value: count for treatment, count in review.treatment_counts().items()
    }
    if payload.get("treatment_counts") != expected_treatment_counts:
        raise ValueError("Aeldari semantic coverage treatment counts drifted.")
    actual_bucket_counts = dict(
        sorted(
            (bucket, sum(1 for row in rows if row.semantic_bucket == bucket))
            for bucket in SEMANTIC_BUCKETS
            if any(row.semantic_bucket == bucket for row in rows)
        )
    )
    if payload.get("semantic_bucket_counts") != actual_bucket_counts:
        raise ValueError("Aeldari semantic coverage bucket counts drifted.")
    if payload.get("datasheet_count") != len(rows):
        raise ValueError("Aeldari semantic coverage datasheet count drifted.")
    if payload.get("exact_ability_count") != sum(len(row.abilities) for row in rows):
        raise ValueError("Aeldari semantic coverage ability count drifted.")
    return AeldariSemanticCoverageArtifact(
        overlay_pack_hash=overlay_pack_hash,
        release_hash=release_hash,
        rows=rows,
    )


def _parse_datasheet(raw: object) -> AeldariDatasheetSemanticCoverage:
    payload = _object(raw, "Aeldari datasheet semantic coverage row")
    abilities = tuple(
        _parse_ability(raw_ability) for raw_ability in _required_list(payload, "abilities")
    )
    if not abilities:
        raise ValueError("Aeldari semantic coverage datasheets require exact abilities.")
    bucket = _required_text(payload, "semantic_bucket")
    if bucket != _semantic_bucket(abilities):
        raise ValueError("Aeldari semantic coverage datasheet bucket is stale.")
    page_value = payload.get("pdf_page_reference")
    page_reference = None if page_value is None else _text(page_value, "pdf_page_reference")
    return AeldariDatasheetSemanticCoverage(
        datasheet_id=_required_text(payload, "datasheet_id"),
        datasheet_name=_required_text(payload, "datasheet_name"),
        group=_required_text(payload, "group"),
        treatment=_required_text(payload, "treatment"),
        pdf_page_reference=page_reference,
        semantic_bucket=bucket,
        abilities=abilities,
    )


def _parse_ability(raw: object) -> AeldariDatasheetAbilitySemanticCoverage:
    payload = _object(raw, "Aeldari datasheet ability semantic coverage row")
    raw_text = _required_text(payload, "raw_text")
    raw_text_sha256 = _required_sha256(payload, "raw_text_sha256")
    if raw_text_sha256 != _sha256_text(raw_text):
        raise ValueError("Aeldari semantic coverage exact ability text hash drifted.")
    try:
        support_stage = AbilityCoverageSupportStage(_required_text(payload, "support_stage"))
    except ValueError as exc:
        raise ValueError("Aeldari semantic coverage support stage is invalid.") from exc
    return AeldariDatasheetAbilitySemanticCoverage(
        ability_id=_required_text(payload, "ability_id"),
        ability_name=_required_text(payload, "ability_name"),
        source_kind=_required_text(payload, "source_kind"),
        source_row_id=_required_text(payload, "source_row_id"),
        raw_text=raw_text,
        raw_text_sha256=raw_text_sha256,
        normalized_text_sha256=_required_sha256(payload, "normalized_text_sha256"),
        catalog_support=_required_text(payload, "catalog_support"),
        support_stage=support_stage,
        runtime_consumer_ids=_text_tuple(payload, "runtime_consumer_ids"),
        diagnostic_reasons=_text_tuple(payload, "diagnostic_reasons"),
        source_ids=_text_tuple(payload, "source_ids"),
    )


def _validate_rows(rows: tuple[AeldariDatasheetSemanticCoverage, ...]) -> None:
    review = faction_pack_datasheet_review("aeldari")
    review_rows_by_id = {
        row.datasheet_id: row for row in review.rows if row.datasheet_id is not None
    }
    rows_by_id = {row.datasheet_id: row for row in rows}
    if len(rows_by_id) != len(rows):
        raise ValueError("Aeldari semantic coverage contains duplicate datasheet IDs.")
    if rows_by_id.keys() != review_rows_by_id.keys():
        raise ValueError("Aeldari semantic coverage does not exhaust the reviewed source IDs.")
    seen_source_rows: set[str] = set()
    for datasheet_id, row in rows_by_id.items():
        review_row = review_rows_by_id[datasheet_id]
        if (
            row.datasheet_name != review_row.datasheet_name
            or row.group != review_row.group
            or row.treatment != review_row.treatment.value
            or row.pdf_page_reference != review_row.pdf_page_reference
        ):
            raise ValueError("Aeldari semantic coverage source review fields drifted.")
        for ability in row.abilities:
            source_key = f"{datasheet_id}:{ability.source_row_id}"
            if source_key in seen_source_rows:
                raise ValueError("Aeldari semantic coverage duplicates an exact ability row.")
            seen_source_rows.add(source_key)
            if not ability.source_ids:
                raise ValueError("Aeldari semantic coverage abilities require provenance IDs.")


def _semantic_bucket(
    abilities: tuple[AeldariDatasheetAbilitySemanticCoverage, ...],
) -> str:
    stages = tuple(ability.support_stage for ability in abilities)
    if any(
        stage
        in {
            AbilityCoverageSupportStage.DESCRIPTOR_ONLY,
            AbilityCoverageSupportStage.IR_COMPILED_UNSUPPORTED,
        }
        for stage in stages
    ):
        return SEMANTIC_BUCKET_UNSUPPORTED_IR
    if any(stage is AbilityCoverageSupportStage.GENERIC_IR_EXECUTABLE for stage in stages):
        return SEMANTIC_BUCKET_HOST_NEEDED
    if all(stage is AbilityCoverageSupportStage.ENGINE_CONSUMED for stage in stages):
        return SEMANTIC_BUCKET_ALL_CONSUMED
    raise ValueError("Aeldari semantic coverage encountered an unclassified datasheet.")


def _load_object(path: Path) -> dict[str, Any]:
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


def _text_tuple(payload: dict[str, Any], key: str) -> tuple[str, ...]:
    return tuple(_text(value, key) for value in _required_list(payload, key))


def _required_sha256(payload: dict[str, Any], key: str) -> str:
    value = _required_text(payload, key)
    if len(value) != 64 or any(character not in "0123456789abcdef" for character in value):
        raise ValueError(f"{key!r} must be a lowercase SHA-256 digest.")
    return value


def _sha256_text(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()
