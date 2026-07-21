from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from functools import cache
from pathlib import Path
from typing import TYPE_CHECKING, Any, cast

if TYPE_CHECKING or __package__:
    from tools.aeldari_datasheet_semantic_coverage import (
        COVERAGE_PATH,
        AeldariDatasheetAbilitySemanticCoverage,
        AeldariSemanticCoverageArtifact,
        ExactSemanticConsumerEvidence,
        aeldari_datasheet_semantic_coverage,
    )
    from tools.aeldari_datasheet_semantic_coverage import (
        SCHEMA_VERSION as COVERAGE_SCHEMA_VERSION,
    )
else:
    from aeldari_datasheet_semantic_coverage import (
        COVERAGE_PATH,
        AeldariDatasheetAbilitySemanticCoverage,
        AeldariSemanticCoverageArtifact,
        ExactSemanticConsumerEvidence,
        aeldari_datasheet_semantic_coverage,
    )
    from aeldari_datasheet_semantic_coverage import (
        SCHEMA_VERSION as COVERAGE_SCHEMA_VERSION,
    )

from warhammer40k_core.core.datasheet import CatalogAbilitySourceKind, CatalogAbilitySupport
from warhammer40k_core.engine.ability_coverage import AbilityCoverageSupportStage

REPO_ROOT = Path(__file__).resolve().parents[1]
DESCRIPTION_TEXT_PATH = (
    REPO_ROOT / "data" / "source_manifests" / "aeldari_ability_semantic_description_text_v1.json"
)
DESCRIPTION_ARTIFACT_PATH = (
    REPO_ROOT
    / "data"
    / "generated"
    / "ability_coverage"
    / "aeldari_ability_semantic_descriptions.json"
)
SCHEMA_VERSION = "aeldari-ability-semantic-descriptions-v1"
GENERATED_BY = "uv run python tools/generate_aeldari_ability_semantic_descriptions.py"
DOCUMENTATION_BUCKET_SUPPORTED = "supported"
DOCUMENTATION_BUCKET_STILL_NEEDED = "still_needed"
DOCUMENTATION_BUCKETS = frozenset(
    {DOCUMENTATION_BUCKET_SUPPORTED, DOCUMENTATION_BUCKET_STILL_NEEDED}
)

_ROOT_KEYS = frozenset(
    {
        "schema_version",
        "generated_by",
        "coverage_schema_version",
        "coverage_sha256",
        "description_text_sha256",
        "exact_ability_count",
        "descriptions",
    }
)
_DESCRIPTION_KEYS = frozenset(
    {
        "datasheet_id",
        "datasheet_name",
        "ability_id",
        "ability_name",
        "source_kind",
        "source_row_id",
        "source_ids",
        "raw_text_sha256",
        "normalized_text_sha256",
        "catalog_support",
        "support_stage",
        "semantic_consumers",
        "runtime_consumer_ids",
        "diagnostic_reasons",
        "documentation_bucket",
        "description",
    }
)
_SEMANTIC_CONSUMER_KEYS = frozenset({"semantic_id", "semantic_kind", "runtime_consumer_ids"})


@dataclass(frozen=True, slots=True)
class AeldariAbilitySemanticDescription:
    datasheet_id: str
    datasheet_name: str
    ability_id: str
    ability_name: str
    source_kind: CatalogAbilitySourceKind
    source_row_id: str
    source_ids: tuple[str, ...]
    raw_text_sha256: str
    normalized_text_sha256: str
    catalog_support: CatalogAbilitySupport
    support_stage: AbilityCoverageSupportStage
    semantic_consumers: tuple[ExactSemanticConsumerEvidence, ...]
    runtime_consumer_ids: tuple[str, ...]
    diagnostic_reasons: tuple[str, ...]
    documentation_bucket: str
    description: str

    @property
    def identity(self) -> tuple[str, str, str]:
        return (self.datasheet_id, self.source_row_id, self.ability_id)


@dataclass(frozen=True, slots=True)
class AeldariAbilitySemanticDescriptionArtifact:
    rows: tuple[AeldariAbilitySemanticDescription, ...]


@cache
def aeldari_ability_semantic_descriptions() -> AeldariAbilitySemanticDescriptionArtifact:
    return load_aeldari_ability_semantic_descriptions(
        description_path=DESCRIPTION_ARTIFACT_PATH,
        coverage=aeldari_datasheet_semantic_coverage(),
    )


def load_aeldari_ability_semantic_descriptions(
    *,
    description_path: Path,
    coverage: AeldariSemanticCoverageArtifact,
) -> AeldariAbilitySemanticDescriptionArtifact:
    if not isinstance(description_path, Path):
        raise TypeError("Aeldari semantic-description path must be a Path.")
    if type(coverage) is not AeldariSemanticCoverageArtifact:
        raise TypeError("Aeldari semantic descriptions require exact coverage evidence.")
    payload = _load_object(description_path)
    _require_exact_keys(payload, _ROOT_KEYS, "Aeldari semantic-description artifact")
    if payload["schema_version"] != SCHEMA_VERSION:
        raise ValueError("Aeldari semantic-description schema version is unsupported.")
    if payload["generated_by"] != GENERATED_BY:
        raise ValueError("Aeldari semantic-description generator identity drifted.")
    if payload["coverage_schema_version"] != COVERAGE_SCHEMA_VERSION:
        raise ValueError("Aeldari semantic-description coverage schema drifted.")
    if _required_sha256(payload, "coverage_sha256") != _sha256(COVERAGE_PATH):
        raise ValueError("Aeldari semantic-description coverage hash drifted.")
    if _required_sha256(payload, "description_text_sha256") != _sha256(DESCRIPTION_TEXT_PATH):
        raise ValueError("Aeldari semantic-description text hash drifted.")
    rows = tuple(
        _parse_description(raw_description)
        for raw_description in _required_list(payload, "descriptions")
    )
    if type(payload["exact_ability_count"]) is not int:
        raise TypeError("Aeldari semantic-description ability count must be an integer.")
    if payload["exact_ability_count"] != len(rows):
        raise ValueError("Aeldari semantic-description ability count drifted.")
    _validate_exact_partition(rows=rows, coverage=coverage)
    return AeldariAbilitySemanticDescriptionArtifact(rows=rows)


def documentation_bucket_for_stage(stage: AbilityCoverageSupportStage) -> str:
    if type(stage) is not AbilityCoverageSupportStage:
        raise TypeError("Aeldari documentation bucket requires a support stage.")
    if stage is AbilityCoverageSupportStage.ENGINE_CONSUMED:
        return DOCUMENTATION_BUCKET_SUPPORTED
    return DOCUMENTATION_BUCKET_STILL_NEEDED


def _parse_description(raw: object) -> AeldariAbilitySemanticDescription:
    payload = _object(raw, "Aeldari semantic-description row")
    _require_exact_keys(payload, _DESCRIPTION_KEYS, "Aeldari semantic-description row")
    try:
        source_kind = CatalogAbilitySourceKind(_required_text(payload, "source_kind"))
        catalog_support = CatalogAbilitySupport(_required_text(payload, "catalog_support"))
        support_stage = AbilityCoverageSupportStage(_required_text(payload, "support_stage"))
    except ValueError as exc:
        raise ValueError("Aeldari semantic-description classification is invalid.") from exc
    documentation_bucket = _required_text(payload, "documentation_bucket")
    if documentation_bucket not in DOCUMENTATION_BUCKETS:
        raise ValueError("Aeldari semantic-description documentation bucket is invalid.")
    if documentation_bucket != documentation_bucket_for_stage(support_stage):
        raise ValueError("Aeldari semantic-description documentation bucket is stale.")
    return AeldariAbilitySemanticDescription(
        datasheet_id=_required_text(payload, "datasheet_id"),
        datasheet_name=_required_text(payload, "datasheet_name"),
        ability_id=_required_text(payload, "ability_id"),
        ability_name=_required_text(payload, "ability_name"),
        source_kind=source_kind,
        source_row_id=_required_text(payload, "source_row_id"),
        source_ids=_unique_text_tuple(payload, "source_ids", require_non_empty=True),
        raw_text_sha256=_required_sha256(payload, "raw_text_sha256"),
        normalized_text_sha256=_required_sha256(payload, "normalized_text_sha256"),
        catalog_support=catalog_support,
        support_stage=support_stage,
        semantic_consumers=tuple(
            _parse_semantic_consumer(raw_semantic)
            for raw_semantic in _required_list(payload, "semantic_consumers")
        ),
        runtime_consumer_ids=_unique_text_tuple(payload, "runtime_consumer_ids"),
        diagnostic_reasons=_unique_text_tuple(payload, "diagnostic_reasons"),
        documentation_bucket=documentation_bucket,
        description=_required_text(payload, "description"),
    )


def _parse_semantic_consumer(raw: object) -> ExactSemanticConsumerEvidence:
    payload = _object(raw, "Aeldari semantic-description consumer")
    _require_exact_keys(
        payload,
        _SEMANTIC_CONSUMER_KEYS,
        "Aeldari semantic-description consumer",
    )
    return ExactSemanticConsumerEvidence(
        semantic_id=_required_text(payload, "semantic_id"),
        semantic_kind=_required_text(payload, "semantic_kind"),
        runtime_consumer_ids=_unique_text_tuple(payload, "runtime_consumer_ids"),
    )


def _validate_exact_partition(
    *,
    rows: tuple[AeldariAbilitySemanticDescription, ...],
    coverage: AeldariSemanticCoverageArtifact,
) -> None:
    actual_by_identity = {row.identity: row for row in rows}
    if len(actual_by_identity) != len(rows):
        raise ValueError("Aeldari semantic descriptions contain duplicate ability identities.")
    expected_by_identity = {
        (datasheet.datasheet_id, ability.source_row_id, ability.ability_id): (
            datasheet,
            ability,
        )
        for datasheet in coverage.rows
        for ability in datasheet.abilities
    }
    if actual_by_identity.keys() != expected_by_identity.keys():
        raise ValueError(
            "Aeldari semantic descriptions do not exactly partition reviewed abilities."
        )
    for identity, (datasheet, ability) in expected_by_identity.items():
        description = actual_by_identity[identity]
        _validate_evidence(
            description=description,
            datasheet_id=datasheet.datasheet_id,
            datasheet_name=datasheet.datasheet_name,
            ability=ability,
        )


def _validate_evidence(
    *,
    description: AeldariAbilitySemanticDescription,
    datasheet_id: str,
    datasheet_name: str,
    ability: AeldariDatasheetAbilitySemanticCoverage,
) -> None:
    if (
        description.datasheet_id != datasheet_id
        or description.datasheet_name != datasheet_name
        or description.ability_id != ability.ability_id
        or description.ability_name != ability.ability_name
        or description.source_kind is not ability.source_kind
        or description.source_row_id != ability.source_row_id
        or description.source_ids != ability.source_ids
        or description.raw_text_sha256 != ability.raw_text_sha256
        or description.normalized_text_sha256 != ability.normalized_text_sha256
        or description.catalog_support is not ability.catalog_support
        or description.support_stage is not ability.support_stage
        or description.semantic_consumers != ability.semantic_consumers
        or description.runtime_consumer_ids != ability.runtime_consumer_ids
        or description.diagnostic_reasons != ability.diagnostic_reasons
        or description.documentation_bucket != documentation_bucket_for_stage(ability.support_stage)
    ):
        raise ValueError("Aeldari semantic-description prose drifted from exact ability evidence.")


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
    value = payload[key]
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{key!r} must be non-empty text.")
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
    if len(values) != len(set(values)):
        raise ValueError(f"{key!r} must not contain duplicate values.")
    return values


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
