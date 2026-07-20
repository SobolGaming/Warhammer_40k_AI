from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from functools import cache
from pathlib import Path
from typing import TYPE_CHECKING, Any, cast

if TYPE_CHECKING or __package__:
    from tools.aeldari_datasheet_semantic_evidence import (
        SourceDerivedAeldariAbilityEvidence,
        source_derived_aeldari_exact_ability_evidence,
    )
    from tools.faction_pack_datasheet_review import faction_pack_datasheet_review
else:
    from aeldari_datasheet_semantic_evidence import (
        SourceDerivedAeldariAbilityEvidence,
        source_derived_aeldari_exact_ability_evidence,
    )
    from faction_pack_datasheet_review import faction_pack_datasheet_review

from warhammer40k_core.core.datasheet import (
    CatalogAbilitySourceKind,
    CatalogAbilitySupport,
)
from warhammer40k_core.engine.ability_coverage import AbilityCoverageSupportStage
from warhammer40k_core.rules.source_overlay import (
    SourceOverlayPack,
    SourceOverlayPackPayload,
    SourceReleaseManifest,
    SourceReleaseManifestPayload,
    apply_source_release_overlays,
)
from warhammer40k_core.rules.text_normalization import (
    normalize_rule_text,
    normalize_structured_source_text,
)
from warhammer40k_core.rules.wahapedia_schema import (
    WahapediaJsonArtifact,
    WahapediaJsonArtifactPayload,
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
TACOMA_OVERLAY_PACK_PATH = (
    REPO_ROOT
    / "data"
    / "source_overlays"
    / "tacoma_open_2026"
    / "aeldari-frame-keyword.overlay-pack.json"
)
SOURCE_SNAPSHOT_RELATIVE_PATH = (
    Path("data") / "source_snapshots" / "wahapedia" / "10th-edition" / "2026-06-14" / "json"
)
SOURCE_JSON_DIR = REPO_ROOT / SOURCE_SNAPSHOT_RELATIVE_PATH
SOURCE_ARTIFACT_TABLES = (
    "Abilities",
    "Datasheets",
    "Datasheets_abilities",
    "Datasheets_keywords",
    "Datasheets_leader",
    "Datasheets_models",
    "Datasheets_models_cost",
    "Datasheets_options",
    "Datasheets_unit_composition",
    "Datasheets_wargear",
    "Factions",
)
SCHEMA_VERSION = "aeldari-datasheet-semantic-coverage-v4"
GENERATED_BY = "uv run python tools/generate_aeldari_datasheet_semantic_coverage.py"
SEMANTIC_BUCKET_ALL_CONSUMED = "All exact abilities consumed"
SEMANTIC_BUCKET_HOST_NEEDED = "Exact IR parsed; host needed"
SEMANTIC_BUCKET_UNSUPPORTED_IR = "Exact ability IR unsupported"
SEMANTIC_BUCKET_BRIDGE_BLOCKED = "Exact ability bridge blocked"
SEMANTIC_BUCKETS = (
    SEMANTIC_BUCKET_ALL_CONSUMED,
    SEMANTIC_BUCKET_HOST_NEEDED,
    SEMANTIC_BUCKET_UNSUPPORTED_IR,
    SEMANTIC_BUCKET_BRIDGE_BLOCKED,
)

_ROOT_KEYS = frozenset(
    {
        "schema_version",
        "generated_by",
        "faction_id",
        "faction_name",
        "pdf_filename",
        "pdf_sha256",
        "source_snapshot_path",
        "source_artifact_hashes",
        "overlay_pack_hashes",
        "release_hash",
        "treatment_counts",
        "semantic_bucket_counts",
        "datasheet_count",
        "exact_ability_count",
        "datasheets",
    }
)
_DATASHEET_KEYS = frozenset(
    {
        "datasheet_id",
        "datasheet_name",
        "group",
        "treatment",
        "pdf_page_reference",
        "semantic_bucket",
        "abilities",
    }
)
_ABILITY_KEYS = frozenset(
    {
        "ability_id",
        "ability_name",
        "source_kind",
        "source_row_id",
        "source_ids",
        "raw_text",
        "raw_text_sha256",
        "normalized_text_sha256",
        "catalog_support",
        "support_stage",
        "semantic_consumers",
        "runtime_consumer_ids",
        "diagnostic_reasons",
    }
)
_SEMANTIC_CONSUMER_KEYS = frozenset(
    {
        "semantic_id",
        "semantic_kind",
        "runtime_consumer_ids",
    }
)


@dataclass(frozen=True, slots=True)
class ExactSemanticConsumerEvidence:
    semantic_id: str
    semantic_kind: str
    runtime_consumer_ids: tuple[str, ...]

    def __post_init__(self) -> None:
        object.__setattr__(self, "semantic_id", _text(self.semantic_id, "semantic_id"))
        object.__setattr__(self, "semantic_kind", _text(self.semantic_kind, "semantic_kind"))
        object.__setattr__(
            self,
            "runtime_consumer_ids",
            _validated_unique_text_tuple("runtime_consumer_ids", self.runtime_consumer_ids),
        )

    def to_payload(self) -> dict[str, object]:
        return {
            "semantic_id": self.semantic_id,
            "semantic_kind": self.semantic_kind,
            "runtime_consumer_ids": list(self.runtime_consumer_ids),
        }


@dataclass(frozen=True, slots=True)
class ExactAbilitySemanticEvidence:
    support_stage: AbilityCoverageSupportStage
    semantic_consumers: tuple[ExactSemanticConsumerEvidence, ...]
    runtime_consumer_ids: tuple[str, ...]
    diagnostic_reasons: tuple[str, ...]

    def __post_init__(self) -> None:
        if type(self.support_stage) is not AbilityCoverageSupportStage:
            raise TypeError("Exact ability evidence requires an ability coverage support stage.")
        consumers = _validated_unique_text_tuple("runtime_consumer_ids", self.runtime_consumer_ids)
        diagnostics = _validated_unique_text_tuple("diagnostic_reasons", self.diagnostic_reasons)
        if type(self.semantic_consumers) is not tuple or any(
            type(semantic) is not ExactSemanticConsumerEvidence
            for semantic in self.semantic_consumers
        ):
            raise TypeError("Exact ability semantic consumers must be an evidence tuple.")
        semantic_ids = tuple(semantic.semantic_id for semantic in self.semantic_consumers)
        if len(set(semantic_ids)) != len(semantic_ids):
            raise ValueError("Exact ability semantic consumer IDs must be unique.")
        represented_consumer_ids = {
            consumer_id
            for semantic in self.semantic_consumers
            for consumer_id in semantic.runtime_consumer_ids
        }
        if not represented_consumer_ids.issubset(consumers):
            raise ValueError(
                "Exact ability semantic consumers must be present in runtime consumers."
            )
        object.__setattr__(self, "runtime_consumer_ids", consumers)
        object.__setattr__(self, "diagnostic_reasons", diagnostics)
        if self.support_stage is AbilityCoverageSupportStage.ENGINE_CONSUMED:
            if not consumers:
                raise ValueError(
                    "Engine-consumed exact ability evidence requires runtime consumers."
                )
            if not self.semantic_consumers or any(
                not semantic.runtime_consumer_ids for semantic in self.semantic_consumers
            ):
                raise ValueError(
                    "Engine-consumed exact ability evidence requires every semantic to have "
                    "runtime consumers."
                )
            if diagnostics:
                raise ValueError(
                    "Engine-consumed exact ability evidence must not contain diagnostics."
                )
        if self.support_stage is AbilityCoverageSupportStage.GENERIC_IR_EXECUTABLE and diagnostics:
            raise ValueError("Executable exact ability IR must not contain blocking diagnostics.")
        if (
            self.support_stage is AbilityCoverageSupportStage.IR_COMPILED_UNSUPPORTED
            and not diagnostics
        ):
            raise ValueError("Unsupported exact ability IR requires explicit diagnostic evidence.")


@dataclass(frozen=True, slots=True)
class AeldariDatasheetAbilitySemanticCoverage:
    ability_id: str
    ability_name: str
    source_kind: CatalogAbilitySourceKind
    source_row_id: str
    raw_text: str
    raw_text_sha256: str
    normalized_text_sha256: str
    catalog_support: CatalogAbilitySupport
    support_stage: AbilityCoverageSupportStage
    semantic_consumers: tuple[ExactSemanticConsumerEvidence, ...]
    runtime_consumer_ids: tuple[str, ...]
    diagnostic_reasons: tuple[str, ...]
    source_ids: tuple[str, ...]

    def semantic_evidence(self) -> ExactAbilitySemanticEvidence:
        return ExactAbilitySemanticEvidence(
            support_stage=self.support_stage,
            semantic_consumers=self.semantic_consumers,
            runtime_consumer_ids=self.runtime_consumer_ids,
            diagnostic_reasons=self.diagnostic_reasons,
        )


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
    overlay_pack_hashes: tuple[tuple[str, str], ...]
    release_hash: str
    source_artifact_hashes: tuple[tuple[str, str], ...]
    rows: tuple[AeldariDatasheetSemanticCoverage, ...]


@cache
def aeldari_datasheet_semantic_coverage() -> AeldariSemanticCoverageArtifact:
    return load_aeldari_datasheet_semantic_coverage(coverage_path=COVERAGE_PATH)


def load_aeldari_datasheet_semantic_coverage(
    *,
    coverage_path: Path,
) -> AeldariSemanticCoverageArtifact:
    if not isinstance(coverage_path, Path):
        raise TypeError("Aeldari semantic coverage path must be a Path.")
    payload = _load_object(coverage_path)
    _require_exact_keys(payload, _ROOT_KEYS, "Aeldari semantic coverage artifact")
    if payload["schema_version"] != SCHEMA_VERSION:
        raise ValueError("Aeldari datasheet semantic coverage schema version is unsupported.")
    if payload["generated_by"] != GENERATED_BY:
        raise ValueError("Aeldari semantic coverage generator identity drifted.")
    review = faction_pack_datasheet_review("aeldari")
    if payload["faction_id"] != review.faction_id:
        raise ValueError("Aeldari semantic coverage faction identity drifted.")
    if payload["faction_name"] != review.faction_name:
        raise ValueError("Aeldari semantic coverage faction name drifted.")
    if payload["pdf_filename"] != review.pdf_filename:
        raise ValueError("Aeldari semantic coverage PDF filename drifted.")
    if payload["pdf_sha256"] != review.pdf_sha256:
        raise ValueError("Aeldari semantic coverage PDF hash drifted.")
    if payload["source_snapshot_path"] != SOURCE_SNAPSHOT_RELATIVE_PATH.as_posix():
        raise ValueError("Aeldari semantic coverage source snapshot path drifted.")
    (
        overlay_pack_hashes,
        release_hash,
        actual_source_hashes,
        expected_ability_evidence,
    ) = _canonical_source_provenance()
    recorded_source_hashes = _required_sha256_map(payload, "source_artifact_hashes")
    if recorded_source_hashes != dict(actual_source_hashes):
        raise ValueError("Aeldari semantic coverage source artifact hashes drifted.")
    recorded_overlay_hashes = _required_digest_map(payload, "overlay_pack_hashes")
    if recorded_overlay_hashes != dict(overlay_pack_hashes):
        raise ValueError("Aeldari semantic coverage overlay hashes drifted.")
    if _required_sha256(payload, "release_hash") != release_hash:
        raise ValueError("Aeldari semantic coverage release hash drifted.")
    rows = tuple(_parse_datasheet(row) for row in _required_list(payload, "datasheets"))
    _validate_rows(rows)
    _validate_source_derived_ability_evidence(
        rows=rows,
        expected=expected_ability_evidence,
    )
    expected_treatment_counts = {
        treatment.value: count for treatment, count in review.treatment_counts().items()
    }
    if payload["treatment_counts"] != expected_treatment_counts:
        raise ValueError("Aeldari semantic coverage treatment counts drifted.")
    actual_bucket_counts = dict(
        sorted(
            (bucket, sum(1 for row in rows if row.semantic_bucket == bucket))
            for bucket in SEMANTIC_BUCKETS
            if any(row.semantic_bucket == bucket for row in rows)
        )
    )
    if payload["semantic_bucket_counts"] != actual_bucket_counts:
        raise ValueError("Aeldari semantic coverage bucket counts drifted.")
    if type(payload["datasheet_count"]) is not int or payload["datasheet_count"] != len(rows):
        raise ValueError("Aeldari semantic coverage datasheet count drifted.")
    exact_ability_count = sum(len(row.abilities) for row in rows)
    if (
        type(payload["exact_ability_count"]) is not int
        or payload["exact_ability_count"] != exact_ability_count
    ):
        raise ValueError("Aeldari semantic coverage ability count drifted.")
    return AeldariSemanticCoverageArtifact(
        overlay_pack_hashes=overlay_pack_hashes,
        release_hash=release_hash,
        source_artifact_hashes=actual_source_hashes,
        rows=rows,
    )


def exact_ability_semantic_bucket(
    abilities: tuple[ExactAbilitySemanticEvidence, ...],
) -> str:
    if type(abilities) is not tuple:
        raise TypeError("Exact ability semantic rollup requires a tuple.")
    if not abilities:
        return SEMANTIC_BUCKET_BRIDGE_BLOCKED
    for ability in abilities:
        if type(ability) is not ExactAbilitySemanticEvidence:
            raise TypeError("Exact ability semantic rollup requires evidence values.")
    if any(
        ability.support_stage
        in {
            AbilityCoverageSupportStage.DESCRIPTOR_ONLY,
            AbilityCoverageSupportStage.IR_COMPILED_UNSUPPORTED,
        }
        for ability in abilities
    ):
        return SEMANTIC_BUCKET_UNSUPPORTED_IR
    if any(
        ability.support_stage is AbilityCoverageSupportStage.GENERIC_IR_EXECUTABLE
        for ability in abilities
    ):
        return SEMANTIC_BUCKET_HOST_NEEDED
    if all(
        ability.support_stage is AbilityCoverageSupportStage.ENGINE_CONSUMED
        and ability.semantic_consumers
        and all(semantic.runtime_consumer_ids for semantic in ability.semantic_consumers)
        and ability.runtime_consumer_ids
        and not ability.diagnostic_reasons
        for ability in abilities
    ):
        return SEMANTIC_BUCKET_ALL_CONSUMED
    raise ValueError("Aeldari exact ability coverage encountered an unclassified datasheet.")


def _parse_datasheet(raw: object) -> AeldariDatasheetSemanticCoverage:
    payload = _object(raw, "Aeldari datasheet semantic coverage row")
    _require_exact_keys(payload, _DATASHEET_KEYS, "Aeldari datasheet semantic coverage row")
    abilities = tuple(
        _parse_ability(raw_ability) for raw_ability in _required_list(payload, "abilities")
    )
    if not abilities:
        raise ValueError("Aeldari semantic coverage datasheets require exact abilities.")
    bucket = _required_text(payload, "semantic_bucket")
    if bucket != exact_ability_semantic_bucket(
        tuple(ability.semantic_evidence() for ability in abilities)
    ):
        raise ValueError("Aeldari semantic coverage datasheet bucket is stale.")
    page_value = payload["pdf_page_reference"]
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
    _require_exact_keys(payload, _ABILITY_KEYS, "Aeldari datasheet ability coverage row")
    raw_text = _required_text(payload, "raw_text")
    raw_text_sha256 = _required_sha256(payload, "raw_text_sha256")
    if raw_text_sha256 != _sha256_text(raw_text):
        raise ValueError("Aeldari semantic coverage exact ability text hash drifted.")
    normalized_text_sha256 = _required_sha256(payload, "normalized_text_sha256")
    normalized_text = (
        normalize_structured_source_text(raw_text)
        if "\n" in raw_text
        else normalize_rule_text(raw_text)
    )
    if normalized_text_sha256 != _sha256_text(normalized_text):
        raise ValueError("Aeldari semantic coverage normalized ability text hash drifted.")
    try:
        source_kind = CatalogAbilitySourceKind(_required_text(payload, "source_kind"))
        catalog_support = CatalogAbilitySupport(_required_text(payload, "catalog_support"))
        support_stage = AbilityCoverageSupportStage(_required_text(payload, "support_stage"))
    except ValueError as exc:
        raise ValueError("Aeldari semantic coverage ability classification is invalid.") from exc
    evidence = ExactAbilitySemanticEvidence(
        support_stage=support_stage,
        semantic_consumers=tuple(
            _parse_semantic_consumer(raw_semantic)
            for raw_semantic in _required_list(payload, "semantic_consumers")
        ),
        runtime_consumer_ids=_unique_text_tuple(payload, "runtime_consumer_ids"),
        diagnostic_reasons=_unique_text_tuple(payload, "diagnostic_reasons"),
    )
    if (
        support_stage is AbilityCoverageSupportStage.IR_COMPILED_UNSUPPORTED
        and catalog_support is not CatalogAbilitySupport.UNSUPPORTED
    ):
        raise ValueError("Unsupported exact ability IR requires unsupported catalog evidence.")
    if (
        support_stage is AbilityCoverageSupportStage.DESCRIPTOR_ONLY
        and catalog_support is not CatalogAbilitySupport.DESCRIPTOR_ONLY
    ):
        raise ValueError("Descriptor-only exact ability evidence has inconsistent catalog support.")
    return AeldariDatasheetAbilitySemanticCoverage(
        ability_id=_required_text(payload, "ability_id"),
        ability_name=_required_text(payload, "ability_name"),
        source_kind=source_kind,
        source_row_id=_required_text(payload, "source_row_id"),
        raw_text=raw_text,
        raw_text_sha256=raw_text_sha256,
        normalized_text_sha256=normalized_text_sha256,
        catalog_support=catalog_support,
        support_stage=evidence.support_stage,
        semantic_consumers=evidence.semantic_consumers,
        runtime_consumer_ids=evidence.runtime_consumer_ids,
        diagnostic_reasons=evidence.diagnostic_reasons,
        source_ids=_unique_text_tuple(payload, "source_ids", require_non_empty=True),
    )


def _parse_semantic_consumer(raw: object) -> ExactSemanticConsumerEvidence:
    payload = _object(raw, "Aeldari exact ability semantic consumer evidence")
    _require_exact_keys(
        payload,
        _SEMANTIC_CONSUMER_KEYS,
        "Aeldari exact ability semantic consumer evidence",
    )
    return ExactSemanticConsumerEvidence(
        semantic_id=_required_text(payload, "semantic_id"),
        semantic_kind=_required_text(payload, "semantic_kind"),
        runtime_consumer_ids=_unique_text_tuple(payload, "runtime_consumer_ids"),
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


def _validate_source_derived_ability_evidence(
    *,
    rows: tuple[AeldariDatasheetSemanticCoverage, ...],
    expected: tuple[SourceDerivedAeldariAbilityEvidence, ...],
) -> None:
    actual_by_identity = {
        (row.datasheet_id, ability.source_row_id, ability.ability_id): (
            row.datasheet_name,
            ability,
        )
        for row in rows
        for ability in row.abilities
    }
    expected_by_identity = {ability.source_identity: ability for ability in expected}
    if actual_by_identity.keys() != expected_by_identity.keys():
        raise ValueError("Aeldari semantic coverage source-derived ability identity drifted.")
    for identity, expected_ability in expected_by_identity.items():
        datasheet_name, actual_ability = actual_by_identity[identity]
        actual_inventory = tuple(
            (semantic.semantic_id, semantic.semantic_kind)
            for semantic in actual_ability.semantic_consumers
        )
        if actual_inventory != expected_ability.semantic_inventory:
            raise ValueError("Aeldari semantic coverage effect inventory drifted.")
        actual_semantic_consumers = tuple(
            (
                semantic.semantic_id,
                semantic.semantic_kind,
                semantic.runtime_consumer_ids,
            )
            for semantic in actual_ability.semantic_consumers
        )
        expected_semantic_consumers = tuple(
            (
                semantic.semantic_id,
                semantic.semantic_kind,
                semantic.runtime_consumer_ids,
            )
            for semantic in expected_ability.semantic_consumers
        )
        if actual_semantic_consumers != expected_semantic_consumers:
            raise ValueError("Aeldari semantic coverage per-effect consumers drifted.")
        if (
            actual_ability.runtime_consumer_ids != expected_ability.runtime_consumer_ids
            or actual_ability.support_stage is not expected_ability.support_stage
            or actual_ability.diagnostic_reasons != expected_ability.diagnostic_reasons
        ):
            raise ValueError("Aeldari semantic coverage ability execution evidence drifted.")
        if (
            datasheet_name != expected_ability.datasheet_name
            or actual_ability.ability_name != expected_ability.ability_name
            or actual_ability.source_kind is not expected_ability.source_kind
            or actual_ability.source_ids != expected_ability.source_ids
            or actual_ability.raw_text != expected_ability.raw_text
            or actual_ability.raw_text_sha256 != expected_ability.raw_text_sha256
            or actual_ability.normalized_text_sha256 != expected_ability.normalized_text_sha256
            or actual_ability.catalog_support is not expected_ability.catalog_support
        ):
            raise ValueError("Aeldari semantic coverage source-derived ability evidence drifted.")


@cache
def _canonical_source_provenance() -> tuple[
    tuple[tuple[str, str], ...],
    str,
    tuple[tuple[str, str], ...],
    tuple[SourceDerivedAeldariAbilityEvidence, ...],
]:
    overlay_pack = SourceOverlayPack.from_payload(
        cast(SourceOverlayPackPayload, _load_object(OVERLAY_PACK_PATH))
    )
    tacoma_overlay_pack = SourceOverlayPack.from_payload(
        cast(SourceOverlayPackPayload, _load_object(TACOMA_OVERLAY_PACK_PATH))
    )
    release_manifest = SourceReleaseManifest.from_payload(
        cast(SourceReleaseManifestPayload, _load_object(RELEASE_MANIFEST_PATH))
    )
    source_artifacts = tuple(
        _load_source_artifact(table_name) for table_name in SOURCE_ARTIFACT_TABLES
    )
    effective_artifacts = apply_source_release_overlays(
        source_artifacts=source_artifacts,
        release_manifest=release_manifest,
        overlay_packs=(overlay_pack, tacoma_overlay_pack),
    )
    source_hashes = tuple(
        sorted(
            (artifact.source_table, artifact.artifact_hash()) for artifact in effective_artifacts
        )
    )
    if tuple(table_name for table_name, _ in source_hashes) != tuple(
        sorted(SOURCE_ARTIFACT_TABLES)
    ):
        raise ValueError("Aeldari semantic coverage source artifact scope drifted.")
    review = faction_pack_datasheet_review("aeldari")
    datasheet_id_names = tuple(
        (row.datasheet_id, row.datasheet_name)
        for row in review.rows
        if row.datasheet_id is not None
    )
    expected_ability_evidence = source_derived_aeldari_exact_ability_evidence(
        effective_artifacts=effective_artifacts,
        datasheet_id_names=datasheet_id_names,
    )
    return (
        tuple(
            (pack.package_id.stable_identity(), pack.package_hash())
            for pack in (overlay_pack, tacoma_overlay_pack)
        ),
        release_manifest.release_hash(),
        source_hashes,
        expected_ability_evidence,
    )


def _load_source_artifact(table_name: str) -> WahapediaJsonArtifact:
    payload = _load_object(SOURCE_JSON_DIR / f"{table_name}.json")
    artifact = WahapediaJsonArtifact.from_payload(cast(WahapediaJsonArtifactPayload, payload))
    if artifact.source_table != table_name:
        raise ValueError("Aeldari semantic coverage source artifact table drifted.")
    return artifact


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


def _require_exact_keys(payload: dict[str, Any], expected: frozenset[str], label: str) -> None:
    actual = frozenset(payload)
    if actual != expected:
        raise ValueError(
            f"{label} keys drifted; missing={sorted(expected - actual)!r}, "
            f"unexpected={sorted(actual - expected)!r}."
        )


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


def _unique_text_tuple(
    payload: dict[str, Any],
    key: str,
    *,
    require_non_empty: bool = False,
) -> tuple[str, ...]:
    values = tuple(_text(value, key) for value in _required_list(payload, key))
    if require_non_empty and not values:
        raise ValueError(f"{key!r} must not be empty.")
    return _validated_unique_text_tuple(key, values)


def _validated_unique_text_tuple(key: str, values: tuple[str, ...]) -> tuple[str, ...]:
    if type(values) is not tuple:
        raise TypeError(f"{key!r} must be a tuple.")
    validated = tuple(_text(value, key) for value in values)
    if len(validated) != len(set(validated)):
        raise ValueError(f"{key!r} must not contain duplicate values.")
    return validated


def _required_sha256(payload: dict[str, Any], key: str) -> str:
    value = _required_text(payload, key)
    if len(value) != 64 or any(character not in "0123456789abcdef" for character in value):
        raise ValueError(f"{key!r} must be a lowercase SHA-256 digest.")
    return value


def _required_sha256_map(payload: dict[str, Any], key: str) -> dict[str, str]:
    raw = _object(payload.get(key), key)
    expected_keys = frozenset(SOURCE_ARTIFACT_TABLES)
    _require_exact_keys(raw, expected_keys, key)
    return {table_name: _required_sha256(raw, table_name) for table_name in sorted(raw)}


def _required_digest_map(payload: dict[str, Any], key: str) -> dict[str, str]:
    raw = _object(payload.get(key), key)
    if not raw:
        raise ValueError(f"{key!r} must not be empty.")
    return {identity: _required_sha256(raw, identity) for identity in sorted(raw)}


def _sha256_text(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()
