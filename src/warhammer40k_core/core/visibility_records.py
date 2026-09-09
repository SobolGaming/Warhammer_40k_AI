from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
from typing import Self, TypedDict, TypeGuard, cast

from warhammer40k_core.core.ruleset_descriptor import (
    CoverEffect,
    LineOfSightPolicy,
    RulesetDescriptorError,
    TerrainFeatureKind,
    TerrainFeatureVisibilityPolicy,
    TerrainVisibilityPolicyDescriptor,
    cover_effect_from_token,
    line_of_sight_policy_from_token,
    terrain_feature_kind_from_token,
)
from warhammer40k_core.core.validation import IdentifierValidator
from warhammer40k_core.geometry.continuous_visibility import (
    ContinuousVisibilityEvidence,
    ContinuousVisibilityPayload,
)
from warhammer40k_core.geometry.pose import (
    GeometryError,
)
from warhammer40k_core.geometry.terrain_classification import (
    TerrainAreaClassification,
    TerrainClassificationError,
    terrain_area_classification_from_token,
)
from warhammer40k_core.geometry.visibility_query import (
    VisibilityMetrics as VisibilityMetrics,
)
from warhammer40k_core.geometry.visibility_query import (
    VisibilityMetricsPayload as VisibilityMetricsPayload,
)
from warhammer40k_core.geometry.visibility_query import VisibilityQuery as VisibilityQuery
from warhammer40k_core.geometry.visibility_query import (
    VisibilityQueryPayload as VisibilityQueryPayload,
)
from warhammer40k_core.geometry.visibility_query import VisibilityRay as VisibilityRay
from warhammer40k_core.geometry.visibility_query import (
    VisibilityRayPayload as VisibilityRayPayload,
)
from warhammer40k_core.geometry.visibility_query import VisibilityResult as VisibilityResult
from warhammer40k_core.geometry.visibility_query import (
    VisibilityResultPayload as VisibilityResultPayload,
)


class VisibilityBlockerKind(StrEnum):
    TERRAIN_FEATURE = "terrain_feature"
    TERRAIN_AREA = "terrain_area"
    TERRAIN_VOLUME = "terrain_volume"
    MODEL = "model"


class CoverSourceReason(StrEnum):
    WHOLLY_WITHIN_FEATURE = "wholly_within_feature"
    NOT_FULLY_VISIBLE_BECAUSE_OF_FEATURE = "not_fully_visible_because_of_feature"
    WITHIN_TERRAIN_AREA = "within_terrain_area"
    NOT_FULLY_VISIBLE_BECAUSE_OF_TERRAIN_AREA = "not_fully_visible_because_of_terrain_area"


class VisibilityBlockerRecordPayload(TypedDict):
    blocker_kind: str
    blocker_id: str
    terrain_feature_id: str | None
    terrain_feature_kind: str | None
    terrain_area_id: str | None
    terrain_area_classification: str | None
    line_of_sight_policy: str
    blocks_model_visibility: bool
    blocks_full_visibility: bool
    exception_applied: str | None


class CoverSourceRecordPayload(TypedDict):
    feature_id: str
    feature_kind: str
    policy_kind: str
    reason: str


class TerrainAreaCoverSourceRecordPayload(TypedDict):
    terrain_area_id: str
    classification: str
    policy_kind: str
    reason: str


@dataclass(frozen=True, slots=True)
class VisibilityBlockerRecord:
    blocker_kind: VisibilityBlockerKind
    blocker_id: str
    line_of_sight_policy: LineOfSightPolicy
    blocks_model_visibility: bool
    blocks_full_visibility: bool
    terrain_feature_id: str | None = None
    terrain_feature_kind: TerrainFeatureKind | None = None
    terrain_area_id: str | None = None
    terrain_area_classification: TerrainAreaClassification | None = None
    exception_applied: str | None = None

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "blocker_kind",
            visibility_blocker_kind_from_token(self.blocker_kind),
        )
        object.__setattr__(
            self,
            "blocker_id",
            validate_visibility_identifier("VisibilityBlockerRecord blocker_id", self.blocker_id),
        )
        object.__setattr__(
            self,
            "line_of_sight_policy",
            _line_of_sight_policy_from_token_for_visibility(self.line_of_sight_policy),
        )
        if type(self.blocks_model_visibility) is not bool:
            raise GeometryError("VisibilityBlockerRecord blocks_model_visibility must be a bool.")
        if type(self.blocks_full_visibility) is not bool:
            raise GeometryError("VisibilityBlockerRecord blocks_full_visibility must be a bool.")
        if self.blocks_model_visibility and not self.blocks_full_visibility:
            raise GeometryError(
                "VisibilityBlockerRecord model-visibility blockers must block full visibility."
            )
        object.__setattr__(
            self,
            "terrain_feature_id",
            _validate_optional_identifier(
                "VisibilityBlockerRecord terrain_feature_id", self.terrain_feature_id
            ),
        )
        feature_kind = self.terrain_feature_kind
        if feature_kind is not None:
            feature_kind = _terrain_feature_kind_from_token_for_visibility(feature_kind)
        object.__setattr__(self, "terrain_feature_kind", feature_kind)
        object.__setattr__(
            self,
            "terrain_area_id",
            _validate_optional_identifier(
                "VisibilityBlockerRecord terrain_area_id", self.terrain_area_id
            ),
        )
        classification = self.terrain_area_classification
        if classification is not None:
            classification = _terrain_area_classification_from_token_for_visibility(classification)
        object.__setattr__(self, "terrain_area_classification", classification)
        object.__setattr__(
            self,
            "exception_applied",
            _validate_optional_identifier(
                "VisibilityBlockerRecord exception_applied", self.exception_applied
            ),
        )
        self._validate_source_fields()

    def _validate_source_fields(self) -> None:
        if self.blocker_kind is VisibilityBlockerKind.TERRAIN_FEATURE:
            if self.terrain_feature_id != self.blocker_id:
                raise GeometryError(
                    "Terrain-feature VisibilityBlockerRecord must use matching feature ID."
                )
            if self.terrain_feature_kind is None:
                raise GeometryError(
                    "Terrain-feature VisibilityBlockerRecord requires terrain_feature_kind."
                )
            if self.terrain_area_id is not None or self.terrain_area_classification is not None:
                raise GeometryError(
                    "Terrain-feature VisibilityBlockerRecord must not include terrain-area data."
                )
        if self.blocker_kind is VisibilityBlockerKind.TERRAIN_AREA:
            if self.terrain_area_id != self.blocker_id:
                raise GeometryError(
                    "Terrain-area VisibilityBlockerRecord must use matching terrain area ID."
                )
            if self.terrain_area_classification is None:
                raise GeometryError(
                    "Terrain-area VisibilityBlockerRecord requires terrain_area_classification."
                )
            if self.terrain_feature_id is not None or self.terrain_feature_kind is not None:
                raise GeometryError(
                    "Terrain-area VisibilityBlockerRecord must not include terrain-feature data."
                )
        if self.blocker_kind is not VisibilityBlockerKind.TERRAIN_AREA and (
            self.terrain_area_id is not None or self.terrain_area_classification is not None
        ):
            raise GeometryError(
                "Non-terrain-area VisibilityBlockerRecord must not include terrain-area data."
            )
        if (
            self.blocker_kind
            not in (
                VisibilityBlockerKind.TERRAIN_FEATURE,
                VisibilityBlockerKind.TERRAIN_AREA,
            )
            and self.exception_applied is not None
        ):
            raise GeometryError(
                "Only terrain feature or area records may preserve visibility exceptions."
            )

    def to_payload(self) -> VisibilityBlockerRecordPayload:
        return {
            "blocker_kind": self.blocker_kind.value,
            "blocker_id": self.blocker_id,
            "terrain_feature_id": self.terrain_feature_id,
            "terrain_feature_kind": (
                None if self.terrain_feature_kind is None else self.terrain_feature_kind.value
            ),
            "terrain_area_id": self.terrain_area_id,
            "terrain_area_classification": (
                None
                if self.terrain_area_classification is None
                else self.terrain_area_classification.value
            ),
            "line_of_sight_policy": self.line_of_sight_policy.value,
            "blocks_model_visibility": self.blocks_model_visibility,
            "blocks_full_visibility": self.blocks_full_visibility,
            "exception_applied": self.exception_applied,
        }

    @classmethod
    def from_payload(cls, payload: VisibilityBlockerRecordPayload) -> Self:
        feature_kind = payload["terrain_feature_kind"]
        classification = payload["terrain_area_classification"]
        return cls(
            blocker_kind=visibility_blocker_kind_from_token(payload["blocker_kind"]),
            blocker_id=payload["blocker_id"],
            terrain_feature_id=payload["terrain_feature_id"],
            terrain_feature_kind=(
                None
                if feature_kind is None
                else _terrain_feature_kind_from_token_for_visibility(feature_kind)
            ),
            terrain_area_id=payload["terrain_area_id"],
            terrain_area_classification=(
                None
                if classification is None
                else _terrain_area_classification_from_token_for_visibility(classification)
            ),
            line_of_sight_policy=_line_of_sight_policy_from_token_for_visibility(
                payload["line_of_sight_policy"]
            ),
            blocks_model_visibility=payload["blocks_model_visibility"],
            blocks_full_visibility=payload["blocks_full_visibility"],
            exception_applied=payload["exception_applied"],
        )


@dataclass(frozen=True, slots=True)
class CoverSourceRecord:
    feature_id: str
    feature_kind: TerrainFeatureKind
    policy_kind: LineOfSightPolicy
    reason: CoverSourceReason

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "feature_id",
            validate_visibility_identifier("CoverSourceRecord feature_id", self.feature_id),
        )
        object.__setattr__(
            self,
            "feature_kind",
            _terrain_feature_kind_from_token_for_visibility(self.feature_kind),
        )
        object.__setattr__(
            self,
            "policy_kind",
            _line_of_sight_policy_from_token_for_visibility(self.policy_kind),
        )
        object.__setattr__(self, "reason", cover_source_reason_from_token(self.reason))
        if self.reason not in (
            CoverSourceReason.WHOLLY_WITHIN_FEATURE,
            CoverSourceReason.NOT_FULLY_VISIBLE_BECAUSE_OF_FEATURE,
        ):
            raise GeometryError("Feature cover source requires a terrain-feature reason.")

    def to_payload(self) -> CoverSourceRecordPayload:
        return {
            "feature_id": self.feature_id,
            "feature_kind": self.feature_kind.value,
            "policy_kind": self.policy_kind.value,
            "reason": self.reason.value,
        }

    @classmethod
    def from_payload(cls, payload: CoverSourceRecordPayload) -> Self:
        return cls(
            feature_id=payload["feature_id"],
            feature_kind=_terrain_feature_kind_from_token_for_visibility(payload["feature_kind"]),
            policy_kind=_line_of_sight_policy_from_token_for_visibility(payload["policy_kind"]),
            reason=cover_source_reason_from_token(payload["reason"]),
        )


@dataclass(frozen=True, slots=True)
class TerrainAreaCoverSourceRecord:
    terrain_area_id: str
    classification: TerrainAreaClassification
    policy_kind: LineOfSightPolicy
    reason: CoverSourceReason

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "terrain_area_id",
            validate_visibility_identifier(
                "TerrainAreaCoverSourceRecord terrain_area_id", self.terrain_area_id
            ),
        )
        object.__setattr__(
            self,
            "classification",
            _terrain_area_classification_from_token_for_visibility(self.classification),
        )
        object.__setattr__(
            self,
            "policy_kind",
            _line_of_sight_policy_from_token_for_visibility(self.policy_kind),
        )
        object.__setattr__(self, "reason", cover_source_reason_from_token(self.reason))
        if self.reason not in (
            CoverSourceReason.WITHIN_TERRAIN_AREA,
            CoverSourceReason.NOT_FULLY_VISIBLE_BECAUSE_OF_TERRAIN_AREA,
        ):
            raise GeometryError("Terrain-area cover source requires a terrain-area reason.")

    def to_payload(self) -> TerrainAreaCoverSourceRecordPayload:
        return {
            "terrain_area_id": self.terrain_area_id,
            "classification": self.classification.value,
            "policy_kind": self.policy_kind.value,
            "reason": self.reason.value,
        }

    @classmethod
    def from_payload(cls, payload: TerrainAreaCoverSourceRecordPayload) -> Self:
        return cls(
            terrain_area_id=payload["terrain_area_id"],
            classification=_terrain_area_classification_from_token_for_visibility(
                payload["classification"]
            ),
            policy_kind=_line_of_sight_policy_from_token_for_visibility(payload["policy_kind"]),
            reason=cover_source_reason_from_token(payload["reason"]),
        )


type CoverEvidenceRecord = CoverSourceRecord | TerrainAreaCoverSourceRecord


def visibility_blocker_kind_from_token(token: object) -> VisibilityBlockerKind:
    if type(token) is VisibilityBlockerKind:
        return token
    if type(token) is not str:
        raise GeometryError("VisibilityBlockerKind token must be a string.")
    try:
        return VisibilityBlockerKind(token)
    except ValueError as exc:
        raise GeometryError("Unsupported VisibilityBlockerKind token.") from exc


def cover_source_reason_from_token(token: object) -> CoverSourceReason:
    if type(token) is CoverSourceReason:
        return token
    if type(token) is not str:
        raise GeometryError("CoverSourceReason token must be a string.")
    try:
        return CoverSourceReason(token)
    except ValueError as exc:
        raise GeometryError("Unsupported CoverSourceReason token.") from exc


def _validate_cover_source_records(
    field_name: str,
    values: object,
) -> tuple[CoverEvidenceRecord, ...]:
    if type(values) is not tuple:
        raise GeometryError(f"{field_name} must be a tuple.")
    records: list[CoverEvidenceRecord] = []
    seen: set[tuple[str, str, str, str]] = set()
    for value in cast(tuple[object, ...], values):
        if type(value) is CoverSourceRecord:
            key = ("feature", value.feature_id, value.policy_kind.value, value.reason.value)
        elif type(value) is TerrainAreaCoverSourceRecord:
            key = (
                "terrain_area",
                value.terrain_area_id,
                value.policy_kind.value,
                value.reason.value,
            )
        else:
            raise GeometryError(f"{field_name} must contain typed cover source records.")
        if key in seen:
            raise GeometryError(f"{field_name} must not contain duplicate records.")
        seen.add(key)
        records.append(value)
    return tuple(sorted(records, key=cover_source_record_sort_key))


def cover_source_record_sort_key(
    record: CoverEvidenceRecord,
) -> tuple[str, str, str, str]:
    if type(record) is CoverSourceRecord:
        return ("feature", record.feature_id, record.policy_kind.value, record.reason.value)
    if type(record) is TerrainAreaCoverSourceRecord:
        return (
            "terrain_area",
            record.terrain_area_id,
            record.policy_kind.value,
            record.reason.value,
        )
    raise GeometryError("Unsupported typed cover source record.")


def _cover_source_record_from_payload(
    payload: CoverSourceRecordPayload | TerrainAreaCoverSourceRecordPayload,
) -> CoverEvidenceRecord:
    if _is_terrain_area_cover_source_payload(payload):
        return TerrainAreaCoverSourceRecord.from_payload(payload)
    if _is_feature_cover_source_payload(payload):
        return CoverSourceRecord.from_payload(payload)
    raise GeometryError("Cover source payload must identify its typed source.")


def _is_terrain_area_cover_source_payload(
    payload: CoverSourceRecordPayload | TerrainAreaCoverSourceRecordPayload,
) -> TypeGuard[TerrainAreaCoverSourceRecordPayload]:
    return "terrain_area_id" in payload


def _is_feature_cover_source_payload(
    payload: CoverSourceRecordPayload | TerrainAreaCoverSourceRecordPayload,
) -> TypeGuard[CoverSourceRecordPayload]:
    return "feature_id" in payload


class ModelLineOfSightRecordPayload(TypedDict):
    target_model_id: str
    model_visible: bool
    model_fully_visible: bool
    evidence: ContinuousVisibilityPayload
    blocker_records: list[VisibilityBlockerRecordPayload]


class LineOfSightWitnessPayload(TypedDict):
    context_fingerprint: str
    ruleset_descriptor_hash: str
    los_cache_key: str
    observer_model_id: str
    target_model_ids: list[str]
    visible_model_ids: list[str]
    fully_visible_model_ids: list[str]
    unit_visible: bool
    unit_fully_visible: bool
    model_records: list[ModelLineOfSightRecordPayload]


class BenefitOfCoverResultPayload(TypedDict):
    has_benefit: bool
    cover_effect: str
    source_feature_ids: list[str]
    source_terrain_area_ids: list[str]
    source_policy_kinds: list[str]
    source_records: list[CoverSourceRecordPayload | TerrainAreaCoverSourceRecordPayload]
    los_cache_key: str
    target_unit_visible: bool
    target_unit_fully_visible: bool
    non_stacking: bool
    ap_zero_save_bonus_excluded_for_save_3_plus_or_better: bool


@dataclass(frozen=True, slots=True)
class ModelLineOfSightRecord:
    target_model_id: str
    model_visible: bool
    model_fully_visible: bool
    evidence: ContinuousVisibilityEvidence
    blocker_records: tuple[VisibilityBlockerRecord, ...] = ()

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "target_model_id",
            validate_visibility_identifier(
                "ModelLineOfSightRecord target_model_id", self.target_model_id
            ),
        )
        if type(self.evidence) is not ContinuousVisibilityEvidence:
            raise GeometryError("ModelLineOfSightRecord requires continuous visibility evidence.")
        if (
            type(self.model_visible) is not bool
            or type(self.model_fully_visible) is not bool
            or self.model_visible != self.evidence.model_visible
            or self.model_fully_visible != self.evidence.model_fully_visible
        ):
            raise GeometryError("ModelLineOfSightRecord predicates must match continuous evidence.")
        object.__setattr__(
            self,
            "blocker_records",
            _validate_blocker_record_tuple(
                "ModelLineOfSightRecord blocker_records", self.blocker_records
            ),
        )

    def to_payload(self) -> ModelLineOfSightRecordPayload:
        return {
            "target_model_id": self.target_model_id,
            "model_visible": self.model_visible,
            "model_fully_visible": self.model_fully_visible,
            "evidence": self.evidence.to_payload(),
            "blocker_records": [record.to_payload() for record in self.blocker_records],
        }

    @classmethod
    def from_payload(cls, payload: ModelLineOfSightRecordPayload) -> Self:
        return cls(
            target_model_id=payload["target_model_id"],
            model_visible=payload["model_visible"],
            model_fully_visible=payload["model_fully_visible"],
            evidence=ContinuousVisibilityEvidence.from_payload(payload["evidence"]),
            blocker_records=tuple(
                VisibilityBlockerRecord.from_payload(record)
                for record in payload["blocker_records"]
            ),
        )


@dataclass(frozen=True, slots=True)
class LineOfSightWitness:
    context_fingerprint: str
    ruleset_descriptor_hash: str
    los_cache_key: str
    observer_model_id: str
    target_model_ids: tuple[str, ...]
    visible_model_ids: tuple[str, ...]
    fully_visible_model_ids: tuple[str, ...]
    unit_visible: bool
    unit_fully_visible: bool
    model_records: tuple[ModelLineOfSightRecord, ...]

    def __post_init__(self) -> None:
        if (
            type(self.context_fingerprint) is not str
            or len(self.context_fingerprint) != 64
            or any(c not in "0123456789abcdef" for c in self.context_fingerprint)
        ):
            raise GeometryError("LineOfSightWitness requires its complete context fingerprint.")
        object.__setattr__(
            self,
            "ruleset_descriptor_hash",
            validate_visibility_identifier(
                "LineOfSightWitness ruleset_descriptor_hash",
                self.ruleset_descriptor_hash,
            ),
        )
        object.__setattr__(
            self,
            "los_cache_key",
            validate_visibility_identifier("LineOfSightWitness los_cache_key", self.los_cache_key),
        )
        object.__setattr__(
            self,
            "observer_model_id",
            validate_visibility_identifier(
                "LineOfSightWitness observer_model_id", self.observer_model_id
            ),
        )
        object.__setattr__(
            self,
            "target_model_ids",
            validate_visibility_identifier_tuple(
                "LineOfSightWitness target_model_ids",
                self.target_model_ids,
            ),
        )
        object.__setattr__(
            self,
            "visible_model_ids",
            validate_visibility_identifier_tuple(
                "LineOfSightWitness visible_model_ids",
                self.visible_model_ids,
            ),
        )
        object.__setattr__(
            self,
            "fully_visible_model_ids",
            validate_visibility_identifier_tuple(
                "LineOfSightWitness fully_visible_model_ids",
                self.fully_visible_model_ids,
            ),
        )
        if type(self.unit_visible) is not bool:
            raise GeometryError("LineOfSightWitness unit_visible must be a bool.")
        if type(self.unit_fully_visible) is not bool:
            raise GeometryError("LineOfSightWitness unit_fully_visible must be a bool.")
        records = _validate_model_los_record_tuple(
            "LineOfSightWitness model_records",
            self.model_records,
        )
        object.__setattr__(self, "model_records", records)
        record_target_ids = tuple(record.target_model_id for record in records)
        if record_target_ids != self.target_model_ids:
            raise GeometryError("LineOfSightWitness model_records must match target_model_ids.")
        visible_ids = tuple(record.target_model_id for record in records if record.model_visible)
        fully_visible_ids = tuple(
            record.target_model_id for record in records if record.model_fully_visible
        )
        if self.visible_model_ids != visible_ids:
            raise GeometryError("LineOfSightWitness visible_model_ids must match model_records.")
        if self.fully_visible_model_ids != fully_visible_ids:
            raise GeometryError(
                "LineOfSightWitness fully_visible_model_ids must match model_records."
            )
        if self.unit_visible != bool(visible_ids):
            raise GeometryError("LineOfSightWitness unit_visible must match model_records.")
        if self.unit_fully_visible != (len(fully_visible_ids) == len(records)):
            raise GeometryError("LineOfSightWitness unit_fully_visible must match model_records.")

    @classmethod
    def from_records(
        cls,
        *,
        context_fingerprint: str,
        ruleset_descriptor_hash: str,
        los_cache_key: str,
        observer_model_id: str,
        model_records: tuple[ModelLineOfSightRecord, ...],
    ) -> Self:
        records = _validate_model_los_record_tuple(
            "LineOfSightWitness model_records",
            model_records,
        )
        return cls(
            context_fingerprint=context_fingerprint,
            ruleset_descriptor_hash=ruleset_descriptor_hash,
            los_cache_key=los_cache_key,
            observer_model_id=observer_model_id,
            target_model_ids=tuple(record.target_model_id for record in records),
            visible_model_ids=tuple(
                record.target_model_id for record in records if record.model_visible
            ),
            fully_visible_model_ids=tuple(
                record.target_model_id for record in records if record.model_fully_visible
            ),
            unit_visible=any(record.model_visible for record in records),
            unit_fully_visible=all(record.model_fully_visible for record in records),
            model_records=records,
        )

    def all_blocker_records(self) -> tuple[VisibilityBlockerRecord, ...]:
        return tuple(
            record for model_record in self.model_records for record in model_record.blocker_records
        )

    def to_payload(self) -> LineOfSightWitnessPayload:
        return {
            "context_fingerprint": self.context_fingerprint,
            "ruleset_descriptor_hash": self.ruleset_descriptor_hash,
            "los_cache_key": self.los_cache_key,
            "observer_model_id": self.observer_model_id,
            "target_model_ids": list(self.target_model_ids),
            "visible_model_ids": list(self.visible_model_ids),
            "fully_visible_model_ids": list(self.fully_visible_model_ids),
            "unit_visible": self.unit_visible,
            "unit_fully_visible": self.unit_fully_visible,
            "model_records": [record.to_payload() for record in self.model_records],
        }

    @classmethod
    def from_payload(cls, payload: LineOfSightWitnessPayload) -> Self:
        return cls(
            context_fingerprint=payload["context_fingerprint"],
            ruleset_descriptor_hash=payload["ruleset_descriptor_hash"],
            los_cache_key=payload["los_cache_key"],
            observer_model_id=payload["observer_model_id"],
            target_model_ids=tuple(payload["target_model_ids"]),
            visible_model_ids=tuple(payload["visible_model_ids"]),
            fully_visible_model_ids=tuple(payload["fully_visible_model_ids"]),
            unit_visible=payload["unit_visible"],
            unit_fully_visible=payload["unit_fully_visible"],
            model_records=tuple(
                ModelLineOfSightRecord.from_payload(record) for record in payload["model_records"]
            ),
        )


@dataclass(frozen=True, slots=True)
class BenefitOfCoverResult:
    has_benefit: bool
    cover_effect: CoverEffect
    source_feature_ids: tuple[str, ...]
    source_policy_kinds: tuple[LineOfSightPolicy, ...]
    source_records: tuple[CoverEvidenceRecord, ...]
    los_cache_key: str
    target_unit_visible: bool
    target_unit_fully_visible: bool
    non_stacking: bool
    ap_zero_save_bonus_excluded_for_save_3_plus_or_better: bool
    source_terrain_area_ids: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        if type(self.has_benefit) is not bool:
            raise GeometryError("BenefitOfCoverResult has_benefit must be a bool.")
        object.__setattr__(
            self,
            "cover_effect",
            _cover_effect_from_token_for_visibility(self.cover_effect),
        )
        object.__setattr__(
            self,
            "source_feature_ids",
            validate_visibility_identifier_tuple(
                "BenefitOfCoverResult source_feature_ids",
                self.source_feature_ids,
            ),
        )
        object.__setattr__(
            self,
            "source_terrain_area_ids",
            validate_visibility_identifier_tuple(
                "BenefitOfCoverResult source_terrain_area_ids",
                self.source_terrain_area_ids,
            ),
        )
        if type(self.source_policy_kinds) is not tuple:
            raise GeometryError("BenefitOfCoverResult source_policy_kinds must be a tuple.")
        source_policy_kinds = tuple(
            _line_of_sight_policy_from_token_for_visibility(policy)
            for policy in self.source_policy_kinds
        )
        if len(set(source_policy_kinds)) != len(source_policy_kinds):
            raise GeometryError(
                "BenefitOfCoverResult source_policy_kinds must not contain duplicates."
            )
        object.__setattr__(
            self,
            "source_policy_kinds",
            tuple(sorted(source_policy_kinds, key=lambda policy: policy.value)),
        )
        source_records = _validate_cover_source_records(
            "BenefitOfCoverResult source_records",
            self.source_records,
        )
        object.__setattr__(self, "source_records", source_records)
        object.__setattr__(
            self,
            "los_cache_key",
            validate_visibility_identifier(
                "BenefitOfCoverResult los_cache_key", self.los_cache_key
            ),
        )
        if type(self.target_unit_visible) is not bool:
            raise GeometryError("BenefitOfCoverResult target_unit_visible must be a bool.")
        if type(self.target_unit_fully_visible) is not bool:
            raise GeometryError("BenefitOfCoverResult target_unit_fully_visible must be a bool.")
        if type(self.non_stacking) is not bool:
            raise GeometryError("BenefitOfCoverResult non_stacking must be a bool.")
        if type(self.ap_zero_save_bonus_excluded_for_save_3_plus_or_better) is not bool:
            raise GeometryError(
                "BenefitOfCoverResult ap_zero_save_bonus_excluded_for_save_3_plus_or_better "
                "must be a bool."
            )
        if self.has_benefit and not (self.source_feature_ids or self.source_terrain_area_ids):
            raise GeometryError(
                "BenefitOfCoverResult with benefit requires source_feature_ids or "
                "source_terrain_area_ids."
            )
        if self.has_benefit and not self.source_records:
            raise GeometryError("BenefitOfCoverResult with benefit requires source_records.")
        if not self.has_benefit and self.source_feature_ids:
            raise GeometryError(
                "BenefitOfCoverResult without benefit must not include source_feature_ids."
            )
        if not self.has_benefit and self.source_terrain_area_ids:
            raise GeometryError(
                "BenefitOfCoverResult without benefit must not include source_terrain_area_ids."
            )
        if not self.has_benefit and self.source_records:
            raise GeometryError(
                "BenefitOfCoverResult without benefit must not include source_records."
            )
        record_feature_ids = tuple(
            sorted(
                {
                    record.feature_id
                    for record in source_records
                    if type(record) is CoverSourceRecord
                }
            )
        )
        if self.source_feature_ids != record_feature_ids:
            raise GeometryError(
                "BenefitOfCoverResult source_feature_ids must match source_records."
            )
        record_terrain_area_ids = tuple(
            sorted(
                {
                    record.terrain_area_id
                    for record in source_records
                    if type(record) is TerrainAreaCoverSourceRecord
                }
            )
        )
        if self.source_terrain_area_ids != record_terrain_area_ids:
            raise GeometryError(
                "BenefitOfCoverResult source_terrain_area_ids must match source_records."
            )
        record_policy_kinds = tuple(
            sorted(
                {record.policy_kind for record in source_records},
                key=lambda policy: policy.value,
            )
        )
        if self.source_policy_kinds != record_policy_kinds:
            raise GeometryError(
                "BenefitOfCoverResult source_policy_kinds must match source_records."
            )

    @classmethod
    def from_cover_sources(
        cls,
        *,
        witness: LineOfSightWitness,
        terrain_visibility_policy: TerrainVisibilityPolicyDescriptor,
        source_records: tuple[CoverEvidenceRecord, ...],
    ) -> Self:
        if type(witness) is not LineOfSightWitness:
            raise GeometryError("Benefit of Cover requires a LineOfSightWitness.")
        if type(terrain_visibility_policy) is not TerrainVisibilityPolicyDescriptor:
            raise GeometryError("Benefit of Cover requires a TerrainVisibilityPolicyDescriptor.")
        records = _validate_cover_source_records(
            "Benefit of Cover source_records",
            source_records,
        )
        cover_policy = terrain_visibility_policy.cover_policy
        eligible_records: set[CoverEvidenceRecord] = set()
        cover_effects: set[CoverEffect] = set()
        for record in records:
            if type(record) is TerrainAreaCoverSourceRecord:
                if not cover_policy.grants_benefit_of_cover:
                    continue
                if (
                    record.reason is CoverSourceReason.NOT_FULLY_VISIBLE_BECAUSE_OF_TERRAIN_AREA
                    and cover_policy.requires_not_fully_visible
                    and witness.unit_fully_visible
                ):
                    continue
                eligible_records.add(record)
                cover_effects.add(cover_policy.cover_effect)
                continue
            if type(record) is not CoverSourceRecord:
                raise GeometryError("Unsupported typed cover source record.")
            feature_policy = feature_visibility_policy(
                terrain_visibility_policy,
                record.feature_kind,
            )
            if not feature_policy.cover_policy.grants_benefit_of_cover:
                continue
            if (
                record.reason is CoverSourceReason.NOT_FULLY_VISIBLE_BECAUSE_OF_FEATURE
                and feature_policy.cover_policy.requires_not_fully_visible
                and witness.unit_fully_visible
            ):
                continue
            eligible_records.add(record)
            cover_effects.add(feature_policy.cover_policy.cover_effect)
        has_benefit = bool(eligible_records)
        if cover_policy.requires_visible_target and not witness.unit_visible:
            has_benefit = False
        if not has_benefit:
            eligible_records = set()
        if len(cover_effects) > 1:
            raise GeometryError("Benefit of Cover source policies disagree on cover effect.")
        cover_effect = next(iter(cover_effects)) if cover_effects else cover_policy.cover_effect
        sorted_records = tuple(sorted(eligible_records, key=cover_source_record_sort_key))
        return cls(
            has_benefit=has_benefit,
            cover_effect=cover_effect,
            source_feature_ids=tuple(
                sorted(
                    {
                        record.feature_id
                        for record in sorted_records
                        if type(record) is CoverSourceRecord
                    }
                )
            ),
            source_terrain_area_ids=tuple(
                sorted(
                    {
                        record.terrain_area_id
                        for record in sorted_records
                        if type(record) is TerrainAreaCoverSourceRecord
                    }
                )
            ),
            source_policy_kinds=tuple(
                sorted(
                    {record.policy_kind for record in sorted_records},
                    key=lambda policy: policy.value,
                )
            ),
            source_records=sorted_records,
            los_cache_key=witness.los_cache_key,
            target_unit_visible=witness.unit_visible,
            target_unit_fully_visible=witness.unit_fully_visible,
            non_stacking=cover_policy.non_stacking,
            ap_zero_save_bonus_excluded_for_save_3_plus_or_better=(
                cover_policy.ap_zero_save_bonus_excluded_for_save_3_plus_or_better
            ),
        )

    def to_payload(self) -> BenefitOfCoverResultPayload:
        return {
            "has_benefit": self.has_benefit,
            "cover_effect": self.cover_effect.value,
            "source_feature_ids": list(self.source_feature_ids),
            "source_terrain_area_ids": list(self.source_terrain_area_ids),
            "source_policy_kinds": [policy.value for policy in self.source_policy_kinds],
            "source_records": [record.to_payload() for record in self.source_records],
            "los_cache_key": self.los_cache_key,
            "target_unit_visible": self.target_unit_visible,
            "target_unit_fully_visible": self.target_unit_fully_visible,
            "non_stacking": self.non_stacking,
            "ap_zero_save_bonus_excluded_for_save_3_plus_or_better": (
                self.ap_zero_save_bonus_excluded_for_save_3_plus_or_better
            ),
        }

    @classmethod
    def from_payload(cls, payload: BenefitOfCoverResultPayload) -> Self:
        return cls(
            has_benefit=payload["has_benefit"],
            cover_effect=_cover_effect_from_token_for_visibility(payload["cover_effect"]),
            source_feature_ids=tuple(payload["source_feature_ids"]),
            source_terrain_area_ids=tuple(payload["source_terrain_area_ids"]),
            source_policy_kinds=tuple(
                _line_of_sight_policy_from_token_for_visibility(policy)
                for policy in payload["source_policy_kinds"]
            ),
            source_records=tuple(
                _cover_source_record_from_payload(record) for record in payload["source_records"]
            ),
            los_cache_key=payload["los_cache_key"],
            target_unit_visible=payload["target_unit_visible"],
            target_unit_fully_visible=payload["target_unit_fully_visible"],
            non_stacking=payload["non_stacking"],
            ap_zero_save_bonus_excluded_for_save_3_plus_or_better=payload[
                "ap_zero_save_bonus_excluded_for_save_3_plus_or_better"
            ],
        )


def _cover_effect_from_token_for_visibility(token: object) -> CoverEffect:
    try:
        return cover_effect_from_token(token)
    except RulesetDescriptorError as exc:
        raise GeometryError("Unsupported CoverEffect token.") from exc


def _line_of_sight_policy_from_token_for_visibility(token: object) -> LineOfSightPolicy:
    try:
        return line_of_sight_policy_from_token(token)
    except RulesetDescriptorError as exc:
        raise GeometryError("Unsupported LineOfSightPolicy token.") from exc


def _terrain_feature_kind_from_token_for_visibility(token: object) -> TerrainFeatureKind:
    try:
        return terrain_feature_kind_from_token(token)
    except RulesetDescriptorError as exc:
        raise GeometryError("Unsupported TerrainFeatureKind token.") from exc


def _terrain_area_classification_from_token_for_visibility(
    token: object,
) -> TerrainAreaClassification:
    try:
        return terrain_area_classification_from_token(token)
    except TerrainClassificationError as exc:
        raise GeometryError("Unsupported TerrainAreaClassification token.") from exc


def feature_visibility_policy(
    terrain_visibility_policy: TerrainVisibilityPolicyDescriptor,
    terrain_feature_kind: TerrainFeatureKind,
) -> TerrainFeatureVisibilityPolicy:
    try:
        return terrain_visibility_policy.policy_for_feature_kind(terrain_feature_kind)
    except RulesetDescriptorError as exc:
        raise GeometryError("Terrain visibility policy does not cover terrain feature.") from exc


validate_visibility_identifier = IdentifierValidator(GeometryError)


def _validate_optional_identifier(field_name: str, value: object | None) -> str | None:
    if value is None:
        return None
    return validate_visibility_identifier(field_name, value)


def validate_visibility_identifier_tuple(
    field_name: str, values: tuple[str, ...]
) -> tuple[str, ...]:
    if type(values) is not tuple:
        raise GeometryError(f"{field_name} must be a tuple.")
    validated: list[str] = []
    seen: set[str] = set()
    for value in values:
        if type(value) is not str:
            raise GeometryError(f"{field_name} values must be strings.")
        stripped = value.strip()
        if not stripped:
            raise GeometryError(f"{field_name} values must not be empty.")
        if stripped in seen:
            raise GeometryError(f"{field_name} must not contain duplicate IDs.")
        seen.add(stripped)
        validated.append(stripped)
    return tuple(sorted(validated))


def _validate_blocker_record_tuple(
    field_name: str,
    values: object,
) -> tuple[VisibilityBlockerRecord, ...]:
    if type(values) is not tuple:
        raise GeometryError(f"{field_name} must be a tuple.")
    records: list[VisibilityBlockerRecord] = []
    seen: set[tuple[str, str, bool, bool, str | None]] = set()
    for value in cast(tuple[object, ...], values):
        if type(value) is not VisibilityBlockerRecord:
            raise GeometryError(f"{field_name} must contain VisibilityBlockerRecord values.")
        key = (
            value.blocker_kind.value,
            value.blocker_id,
            value.blocks_model_visibility,
            value.blocks_full_visibility,
            value.exception_applied,
        )
        if key in seen:
            raise GeometryError(f"{field_name} must not contain duplicate records.")
        seen.add(key)
        records.append(value)
    return tuple(sorted(records, key=visibility_blocker_record_sort_key))


def _validate_model_los_record_tuple(
    field_name: str,
    values: object,
) -> tuple[ModelLineOfSightRecord, ...]:
    if type(values) is not tuple:
        raise GeometryError(f"{field_name} must be a tuple.")
    records: list[ModelLineOfSightRecord] = []
    seen: set[str] = set()
    for value in cast(tuple[object, ...], values):
        if type(value) is not ModelLineOfSightRecord:
            raise GeometryError(f"{field_name} must contain ModelLineOfSightRecord values.")
        if value.target_model_id in seen:
            raise GeometryError(f"{field_name} must not contain duplicate target model IDs.")
        seen.add(value.target_model_id)
        records.append(value)
    if not records:
        raise GeometryError(f"{field_name} must not be empty.")
    return tuple(sorted(records, key=lambda record: record.target_model_id))


def visibility_blocker_record_sort_key(
    record: VisibilityBlockerRecord,
) -> tuple[str, str, str | None]:
    return (
        record.blocker_kind.value,
        record.blocker_id,
        record.exception_applied,
    )
