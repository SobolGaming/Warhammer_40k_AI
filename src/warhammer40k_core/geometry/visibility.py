from __future__ import annotations

from dataclasses import dataclass, field
from enum import StrEnum
from typing import Self, TypedDict, cast

from warhammer40k_core.core.ruleset_descriptor import (
    CoverEffect,
    LineOfSightPolicy,
    RulesetDescriptor,
    RulesetDescriptorError,
    TerrainFeatureKind,
    TerrainFeatureVisibilityPolicy,
    TerrainVisibilityPolicyDescriptor,
    TerrainVisibilityPolicyDescriptorPayload,
    cover_effect_from_token,
    line_of_sight_policy_from_token,
    terrain_feature_kind_from_token,
)
from warhammer40k_core.geometry import shapely_backend
from warhammer40k_core.geometry.pose import (
    GeometryError,
    Point3,
    Point3Payload,
    validate_point3,
)
from warhammer40k_core.geometry.terrain import (
    TerrainFeatureDefinition,
    TerrainFeatureDefinitionPayload,
    TerrainVolume,
    TerrainVolumePayload,
    terrain_volume_from_payload,
)
from warhammer40k_core.geometry.volume import Model, ModelPayload

type VisibilityRay = tuple[Point3, Point3]


class VisibilityRayPayload(TypedDict):
    start: Point3Payload
    end: Point3Payload


class VisibilityQueryPayload(TypedDict):
    rays: list[VisibilityRayPayload]
    static_terrain: list[TerrainVolumePayload]
    dynamic_model_blockers: list[ModelPayload]


class VisibilityResultPayload(TypedDict):
    has_line_of_sight: bool
    checked_ray_count: int
    clear_ray_index: int | None
    blocking_terrain_ids: list[str]
    blocking_model_ids: list[str]
    checked_terrain_ids: list[str]
    checked_model_ids: list[str]
    metrics: VisibilityMetricsPayload


class VisibilityMetricsPayload(TypedDict):
    terrain_candidate_count: int
    model_candidate_count: int
    exact_terrain_check_count: int
    exact_model_check_count: int


class VisibilityBlockerKind(StrEnum):
    TERRAIN_FEATURE = "terrain_feature"
    TERRAIN_VOLUME = "terrain_volume"
    MODEL = "model"


class CoverSourceReason(StrEnum):
    WHOLLY_WITHIN_FEATURE = "wholly_within_feature"
    NOT_FULLY_VISIBLE_BECAUSE_OF_FEATURE = "not_fully_visible_because_of_feature"


class VisibilityBlockerRecordPayload(TypedDict):
    blocker_kind: str
    blocker_id: str
    ray_index: int
    terrain_feature_id: str | None
    terrain_feature_kind: str | None
    line_of_sight_policy: str
    blocks_model_visibility: bool
    blocks_full_visibility: bool
    exception_applied: str | None


class CoverSourceRecordPayload(TypedDict):
    feature_id: str
    feature_kind: str
    policy_kind: str
    reason: str


class ModelLineOfSightRecordPayload(TypedDict):
    target_model_id: str
    model_visible: bool
    model_fully_visible: bool
    checked_ray_count: int
    clear_ray_indices: list[int]
    blocker_records: list[VisibilityBlockerRecordPayload]


class LineOfSightWitnessPayload(TypedDict):
    ruleset_descriptor_hash: str
    los_cache_key: str
    observer_model_id: str
    target_model_ids: list[str]
    visible_model_ids: list[str]
    fully_visible_model_ids: list[str]
    unit_visible: bool
    unit_fully_visible: bool
    model_records: list[ModelLineOfSightRecordPayload]


class TerrainVisibilityContextPayload(TypedDict):
    ruleset_descriptor_hash: str
    los_cache_key: str
    observer_model: ModelPayload
    target_models: list[ModelPayload]
    terrain_features: list[TerrainFeatureDefinitionPayload]
    terrain_volumes: list[TerrainVolumePayload]
    dynamic_model_blockers: list[ModelPayload]
    observer_keywords: list[str]
    target_keywords: list[str]
    terrain_visibility_policy: TerrainVisibilityPolicyDescriptorPayload


class BenefitOfCoverResultPayload(TypedDict):
    has_benefit: bool
    cover_effect: str
    source_feature_ids: list[str]
    source_policy_kinds: list[str]
    source_records: list[CoverSourceRecordPayload]
    los_cache_key: str
    target_unit_visible: bool
    target_unit_fully_visible: bool
    non_stacking: bool
    ap_zero_save_bonus_excluded_for_save_3_plus_or_better: bool


@dataclass(frozen=True, slots=True)
class VisibilityQuery:
    rays: tuple[VisibilityRay, ...]
    static_terrain: tuple[TerrainVolume, ...] = ()
    dynamic_model_blockers: tuple[Model, ...] = ()

    def __post_init__(self) -> None:
        if type(self.rays) is not tuple:
            raise GeometryError("VisibilityQuery rays must be a tuple.")
        if not self.rays:
            raise GeometryError("VisibilityQuery rays must not be empty.")
        if type(self.static_terrain) is not tuple:
            raise GeometryError("VisibilityQuery static_terrain must be a tuple.")
        if type(self.dynamic_model_blockers) is not tuple:
            raise GeometryError("VisibilityQuery dynamic_model_blockers must be a tuple.")

        rays = tuple(_validate_ray(ray) for ray in self.rays)
        terrain = tuple(
            _validate_terrain("VisibilityQuery static terrain", volume)
            for volume in self.static_terrain
        )
        models = tuple(
            _validate_model("VisibilityQuery dynamic model blocker", model)
            for model in self.dynamic_model_blockers
        )
        _validate_unique_terrain_ids(terrain)
        _validate_unique_model_ids(models)
        object.__setattr__(self, "rays", rays)
        object.__setattr__(
            self,
            "static_terrain",
            tuple(sorted(terrain, key=lambda volume: volume.terrain_id)),
        )
        object.__setattr__(
            self,
            "dynamic_model_blockers",
            tuple(sorted(models, key=lambda model: model.model_id)),
        )

    @classmethod
    def from_segment(
        cls,
        start: Point3,
        end: Point3,
        static_terrain: tuple[TerrainVolume, ...] = (),
        dynamic_model_blockers: tuple[Model, ...] = (),
    ) -> Self:
        return cls(
            rays=((start, end),),
            static_terrain=static_terrain,
            dynamic_model_blockers=dynamic_model_blockers,
        )

    def resolve(self) -> VisibilityResult:
        checked_terrain_ids: set[str] = set()
        checked_model_ids: set[str] = set()
        blocking_terrain_ids: set[str] = set()
        blocking_model_ids: set[str] = set()
        terrain_candidate_count = 0
        model_candidate_count = 0
        exact_terrain_check_count = 0
        exact_model_check_count = 0

        for ray_index, ray in enumerate(self.rays):
            start, end = ray
            terrain_candidates = tuple(
                terrain
                for terrain in self.static_terrain
                if terrain.blocks_line_of_sight and _terrain_broad_phase_intersects(ray, terrain)
            )
            model_candidates = tuple(
                model
                for model in self.dynamic_model_blockers
                if _model_broad_phase_intersects(ray, model)
            )
            terrain_candidate_count += len(terrain_candidates)
            model_candidate_count += len(model_candidates)

            checked_terrain_ids.update(terrain.terrain_id for terrain in terrain_candidates)
            checked_model_ids.update(model.model_id for model in model_candidates)

            exact_terrain_check_count += len(terrain_candidates)
            terrain_blockers = tuple(
                terrain.terrain_id
                for terrain in terrain_candidates
                if terrain.blocks_line_segment(start, end)
            )
            exact_model_check_count += len(model_candidates)
            model_blockers = tuple(
                model.model_id
                for model in model_candidates
                if shapely_backend.segment_intersects_model_footprint(start, end, model)
            )
            if not terrain_blockers and not model_blockers:
                return VisibilityResult(
                    has_line_of_sight=True,
                    checked_ray_count=ray_index + 1,
                    clear_ray_index=ray_index,
                    checked_terrain_ids=tuple(sorted(checked_terrain_ids)),
                    checked_model_ids=tuple(sorted(checked_model_ids)),
                    metrics=VisibilityMetrics(
                        terrain_candidate_count=terrain_candidate_count,
                        model_candidate_count=model_candidate_count,
                        exact_terrain_check_count=exact_terrain_check_count,
                        exact_model_check_count=exact_model_check_count,
                    ),
                )

            blocking_terrain_ids.update(terrain_blockers)
            blocking_model_ids.update(model_blockers)

        return VisibilityResult(
            has_line_of_sight=False,
            checked_ray_count=len(self.rays),
            clear_ray_index=None,
            blocking_terrain_ids=tuple(sorted(blocking_terrain_ids)),
            blocking_model_ids=tuple(sorted(blocking_model_ids)),
            checked_terrain_ids=tuple(sorted(checked_terrain_ids)),
            checked_model_ids=tuple(sorted(checked_model_ids)),
            metrics=VisibilityMetrics(
                terrain_candidate_count=terrain_candidate_count,
                model_candidate_count=model_candidate_count,
                exact_terrain_check_count=exact_terrain_check_count,
                exact_model_check_count=exact_model_check_count,
            ),
        )

    def to_payload(self) -> VisibilityQueryPayload:
        return {
            "rays": [
                {"start": start.to_payload(), "end": end.to_payload()} for start, end in self.rays
            ],
            "static_terrain": [terrain.to_payload() for terrain in self.static_terrain],
            "dynamic_model_blockers": [model.to_payload() for model in self.dynamic_model_blockers],
        }

    @classmethod
    def from_payload(cls, payload: VisibilityQueryPayload) -> Self:
        return cls(
            rays=tuple(
                (
                    Point3.from_payload(ray["start"]),
                    Point3.from_payload(ray["end"]),
                )
                for ray in payload["rays"]
            ),
            static_terrain=tuple(
                terrain_volume_from_payload(terrain) for terrain in payload["static_terrain"]
            ),
            dynamic_model_blockers=tuple(
                Model.from_payload(model) for model in payload["dynamic_model_blockers"]
            ),
        )


@dataclass(frozen=True, slots=True)
class VisibilityMetrics:
    terrain_candidate_count: int = 0
    model_candidate_count: int = 0
    exact_terrain_check_count: int = 0
    exact_model_check_count: int = 0

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "terrain_candidate_count",
            _validate_non_negative_int(
                "VisibilityMetrics terrain_candidate_count",
                self.terrain_candidate_count,
            ),
        )
        object.__setattr__(
            self,
            "model_candidate_count",
            _validate_non_negative_int(
                "VisibilityMetrics model_candidate_count",
                self.model_candidate_count,
            ),
        )
        object.__setattr__(
            self,
            "exact_terrain_check_count",
            _validate_non_negative_int(
                "VisibilityMetrics exact_terrain_check_count",
                self.exact_terrain_check_count,
            ),
        )
        object.__setattr__(
            self,
            "exact_model_check_count",
            _validate_non_negative_int(
                "VisibilityMetrics exact_model_check_count",
                self.exact_model_check_count,
            ),
        )

    def to_payload(self) -> VisibilityMetricsPayload:
        return {
            "terrain_candidate_count": self.terrain_candidate_count,
            "model_candidate_count": self.model_candidate_count,
            "exact_terrain_check_count": self.exact_terrain_check_count,
            "exact_model_check_count": self.exact_model_check_count,
        }

    @classmethod
    def from_payload(cls, payload: VisibilityMetricsPayload) -> Self:
        return cls(
            terrain_candidate_count=payload["terrain_candidate_count"],
            model_candidate_count=payload["model_candidate_count"],
            exact_terrain_check_count=payload["exact_terrain_check_count"],
            exact_model_check_count=payload["exact_model_check_count"],
        )


@dataclass(frozen=True, slots=True)
class VisibilityBlockerRecord:
    blocker_kind: VisibilityBlockerKind
    blocker_id: str
    ray_index: int
    line_of_sight_policy: LineOfSightPolicy
    blocks_model_visibility: bool
    blocks_full_visibility: bool
    terrain_feature_id: str | None = None
    terrain_feature_kind: TerrainFeatureKind | None = None
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
            _validate_identifier("VisibilityBlockerRecord blocker_id", self.blocker_id),
        )
        object.__setattr__(
            self,
            "ray_index",
            _validate_non_negative_int("VisibilityBlockerRecord ray_index", self.ray_index),
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
                "VisibilityBlockerRecord terrain_feature_id",
                self.terrain_feature_id,
            ),
        )
        terrain_feature_kind = self.terrain_feature_kind
        if terrain_feature_kind is not None:
            terrain_feature_kind = _terrain_feature_kind_from_token_for_visibility(
                terrain_feature_kind
            )
        object.__setattr__(self, "terrain_feature_kind", terrain_feature_kind)
        object.__setattr__(
            self,
            "exception_applied",
            _validate_optional_identifier(
                "VisibilityBlockerRecord exception_applied",
                self.exception_applied,
            ),
        )
        if self.blocker_kind is VisibilityBlockerKind.TERRAIN_FEATURE:
            if self.terrain_feature_id != self.blocker_id:
                raise GeometryError(
                    "Terrain-feature VisibilityBlockerRecord must use matching feature ID."
                )
            if self.terrain_feature_kind is None:
                raise GeometryError(
                    "Terrain-feature VisibilityBlockerRecord requires terrain_feature_kind."
                )
        if self.blocker_kind is not VisibilityBlockerKind.TERRAIN_FEATURE and (
            self.exception_applied is not None
            and not self.blocks_model_visibility
            and not self.blocks_full_visibility
        ):
            raise GeometryError(
                "Only terrain-feature records may preserve non-blocking visibility exceptions."
            )

    def to_payload(self) -> VisibilityBlockerRecordPayload:
        return {
            "blocker_kind": self.blocker_kind.value,
            "blocker_id": self.blocker_id,
            "ray_index": self.ray_index,
            "terrain_feature_id": self.terrain_feature_id,
            "terrain_feature_kind": (
                None if self.terrain_feature_kind is None else self.terrain_feature_kind.value
            ),
            "line_of_sight_policy": self.line_of_sight_policy.value,
            "blocks_model_visibility": self.blocks_model_visibility,
            "blocks_full_visibility": self.blocks_full_visibility,
            "exception_applied": self.exception_applied,
        }

    @classmethod
    def from_payload(cls, payload: VisibilityBlockerRecordPayload) -> Self:
        terrain_feature_kind = payload["terrain_feature_kind"]
        return cls(
            blocker_kind=visibility_blocker_kind_from_token(payload["blocker_kind"]),
            blocker_id=payload["blocker_id"],
            ray_index=payload["ray_index"],
            terrain_feature_id=payload["terrain_feature_id"],
            terrain_feature_kind=(
                None
                if terrain_feature_kind is None
                else _terrain_feature_kind_from_token_for_visibility(terrain_feature_kind)
            ),
            line_of_sight_policy=_line_of_sight_policy_from_token_for_visibility(
                payload["line_of_sight_policy"]
            ),
            blocks_model_visibility=payload["blocks_model_visibility"],
            blocks_full_visibility=payload["blocks_full_visibility"],
            exception_applied=payload["exception_applied"],
        )


@dataclass(frozen=True, slots=True)
class ModelLineOfSightRecord:
    target_model_id: str
    model_visible: bool
    model_fully_visible: bool
    checked_ray_count: int
    clear_ray_indices: tuple[int, ...]
    blocker_records: tuple[VisibilityBlockerRecord, ...] = ()

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "target_model_id",
            _validate_identifier("ModelLineOfSightRecord target_model_id", self.target_model_id),
        )
        if type(self.model_visible) is not bool:
            raise GeometryError("ModelLineOfSightRecord model_visible must be a bool.")
        if type(self.model_fully_visible) is not bool:
            raise GeometryError("ModelLineOfSightRecord model_fully_visible must be a bool.")
        checked_ray_count = _validate_positive_int(
            "ModelLineOfSightRecord checked_ray_count",
            self.checked_ray_count,
        )
        object.__setattr__(self, "checked_ray_count", checked_ray_count)
        clear_ray_indices = _validate_ray_index_tuple(
            "ModelLineOfSightRecord clear_ray_indices",
            self.clear_ray_indices,
            checked_ray_count=checked_ray_count,
        )
        object.__setattr__(self, "clear_ray_indices", clear_ray_indices)
        blocker_records = _validate_blocker_record_tuple(
            "ModelLineOfSightRecord blocker_records",
            self.blocker_records,
        )
        object.__setattr__(self, "blocker_records", blocker_records)
        if self.model_visible != bool(clear_ray_indices):
            raise GeometryError(
                "ModelLineOfSightRecord model_visible must match clear_ray_indices."
            )
        if self.model_fully_visible:
            if len(clear_ray_indices) != checked_ray_count:
                raise GeometryError(
                    "Fully visible ModelLineOfSightRecord requires every ray to be clear."
                )
            if any(record.blocks_full_visibility for record in blocker_records):
                raise GeometryError(
                    "Fully visible ModelLineOfSightRecord must not include full blockers."
                )
        if self.model_fully_visible and not self.model_visible:
            raise GeometryError(
                "ModelLineOfSightRecord model_fully_visible requires model_visible."
            )

    def to_payload(self) -> ModelLineOfSightRecordPayload:
        return {
            "target_model_id": self.target_model_id,
            "model_visible": self.model_visible,
            "model_fully_visible": self.model_fully_visible,
            "checked_ray_count": self.checked_ray_count,
            "clear_ray_indices": list(self.clear_ray_indices),
            "blocker_records": [record.to_payload() for record in self.blocker_records],
        }

    @classmethod
    def from_payload(cls, payload: ModelLineOfSightRecordPayload) -> Self:
        return cls(
            target_model_id=payload["target_model_id"],
            model_visible=payload["model_visible"],
            model_fully_visible=payload["model_fully_visible"],
            checked_ray_count=payload["checked_ray_count"],
            clear_ray_indices=tuple(payload["clear_ray_indices"]),
            blocker_records=tuple(
                VisibilityBlockerRecord.from_payload(record)
                for record in payload["blocker_records"]
            ),
        )


@dataclass(frozen=True, slots=True)
class LineOfSightWitness:
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
        object.__setattr__(
            self,
            "ruleset_descriptor_hash",
            _validate_identifier(
                "LineOfSightWitness ruleset_descriptor_hash",
                self.ruleset_descriptor_hash,
            ),
        )
        object.__setattr__(
            self,
            "los_cache_key",
            _validate_identifier("LineOfSightWitness los_cache_key", self.los_cache_key),
        )
        object.__setattr__(
            self,
            "observer_model_id",
            _validate_identifier("LineOfSightWitness observer_model_id", self.observer_model_id),
        )
        object.__setattr__(
            self,
            "target_model_ids",
            _validate_identifier_tuple(
                "LineOfSightWitness target_model_ids",
                self.target_model_ids,
            ),
        )
        object.__setattr__(
            self,
            "visible_model_ids",
            _validate_identifier_tuple(
                "LineOfSightWitness visible_model_ids",
                self.visible_model_ids,
            ),
        )
        object.__setattr__(
            self,
            "fully_visible_model_ids",
            _validate_identifier_tuple(
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
class CoverSourceRecord:
    feature_id: str
    feature_kind: TerrainFeatureKind
    policy_kind: LineOfSightPolicy
    reason: CoverSourceReason

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "feature_id",
            _validate_identifier("CoverSourceRecord feature_id", self.feature_id),
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
        object.__setattr__(
            self,
            "reason",
            cover_source_reason_from_token(self.reason),
        )

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
class BenefitOfCoverResult:
    has_benefit: bool
    cover_effect: CoverEffect
    source_feature_ids: tuple[str, ...]
    source_policy_kinds: tuple[LineOfSightPolicy, ...]
    source_records: tuple[CoverSourceRecord, ...]
    los_cache_key: str
    target_unit_visible: bool
    target_unit_fully_visible: bool
    non_stacking: bool
    ap_zero_save_bonus_excluded_for_save_3_plus_or_better: bool

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
            _validate_identifier_tuple(
                "BenefitOfCoverResult source_feature_ids",
                self.source_feature_ids,
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
        source_records = _validate_cover_source_record_tuple(
            "BenefitOfCoverResult source_records",
            self.source_records,
        )
        object.__setattr__(self, "source_records", source_records)
        object.__setattr__(
            self,
            "los_cache_key",
            _validate_identifier("BenefitOfCoverResult los_cache_key", self.los_cache_key),
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
        if self.has_benefit and not self.source_feature_ids:
            raise GeometryError("BenefitOfCoverResult with benefit requires source_feature_ids.")
        if self.has_benefit and not self.source_records:
            raise GeometryError("BenefitOfCoverResult with benefit requires source_records.")
        if not self.has_benefit and self.source_feature_ids:
            raise GeometryError(
                "BenefitOfCoverResult without benefit must not include source_feature_ids."
            )
        if not self.has_benefit and self.source_records:
            raise GeometryError(
                "BenefitOfCoverResult without benefit must not include source_records."
            )
        record_feature_ids = tuple(sorted({record.feature_id for record in source_records}))
        if self.source_feature_ids != record_feature_ids:
            raise GeometryError(
                "BenefitOfCoverResult source_feature_ids must match source_records."
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
        source_records: tuple[CoverSourceRecord, ...],
    ) -> Self:
        if type(witness) is not LineOfSightWitness:
            raise GeometryError("Benefit of Cover requires a LineOfSightWitness.")
        if type(terrain_visibility_policy) is not TerrainVisibilityPolicyDescriptor:
            raise GeometryError("Benefit of Cover requires a TerrainVisibilityPolicyDescriptor.")
        records = _validate_cover_source_record_tuple(
            "Benefit of Cover source_records",
            source_records,
        )
        cover_policy = terrain_visibility_policy.cover_policy
        eligible_records: set[CoverSourceRecord] = set()
        cover_effects: set[CoverEffect] = set()
        for record in records:
            feature_policy = _feature_visibility_policy(
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
        sorted_records = tuple(sorted(eligible_records, key=_cover_source_record_sort_key))
        return cls(
            has_benefit=has_benefit,
            cover_effect=cover_effect,
            source_feature_ids=tuple(sorted({record.feature_id for record in sorted_records})),
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
            source_policy_kinds=tuple(
                _line_of_sight_policy_from_token_for_visibility(policy)
                for policy in payload["source_policy_kinds"]
            ),
            source_records=tuple(
                CoverSourceRecord.from_payload(record) for record in payload["source_records"]
            ),
            los_cache_key=payload["los_cache_key"],
            target_unit_visible=payload["target_unit_visible"],
            target_unit_fully_visible=payload["target_unit_fully_visible"],
            non_stacking=payload["non_stacking"],
            ap_zero_save_bonus_excluded_for_save_3_plus_or_better=payload[
                "ap_zero_save_bonus_excluded_for_save_3_plus_or_better"
            ],
        )


@dataclass(frozen=True, slots=True)
class TerrainVisibilityContext:
    ruleset_descriptor_hash: str
    los_cache_key: str
    terrain_visibility_policy: TerrainVisibilityPolicyDescriptor
    observer_model: Model
    target_models: tuple[Model, ...]
    terrain_features: tuple[TerrainFeatureDefinition, ...] = ()
    terrain_volumes: tuple[TerrainVolume, ...] = ()
    dynamic_model_blockers: tuple[Model, ...] = ()
    observer_keywords: tuple[str, ...] = ()
    target_keywords: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "ruleset_descriptor_hash",
            _validate_identifier(
                "TerrainVisibilityContext ruleset_descriptor_hash",
                self.ruleset_descriptor_hash,
            ),
        )
        object.__setattr__(
            self,
            "los_cache_key",
            _validate_identifier("TerrainVisibilityContext los_cache_key", self.los_cache_key),
        )
        if type(self.terrain_visibility_policy) is not TerrainVisibilityPolicyDescriptor:
            raise GeometryError(
                "TerrainVisibilityContext terrain_visibility_policy must be "
                "TerrainVisibilityPolicyDescriptor."
            )
        observer_model = _validate_model(
            "TerrainVisibilityContext observer_model",
            self.observer_model,
        )
        object.__setattr__(self, "observer_model", observer_model)
        target_models = _validate_model_tuple(
            "TerrainVisibilityContext target_models",
            self.target_models,
            allow_empty=False,
        )
        if any(target.model_id == observer_model.model_id for target in target_models):
            raise GeometryError("TerrainVisibilityContext target_models must not include observer.")
        object.__setattr__(self, "target_models", target_models)
        terrain_features = _validate_terrain_feature_tuple(
            "TerrainVisibilityContext terrain_features",
            self.terrain_features,
        )
        object.__setattr__(self, "terrain_features", terrain_features)
        terrain_volumes = self.terrain_volumes
        if not terrain_volumes:
            terrain_volumes = tuple(
                volume for feature in terrain_features for volume in feature.terrain_volumes()
            )
        object.__setattr__(
            self,
            "terrain_volumes",
            _validate_terrain_volume_tuple(
                "TerrainVisibilityContext terrain_volumes",
                terrain_volumes,
            ),
        )
        blocker_models = _validate_model_tuple(
            "TerrainVisibilityContext dynamic_model_blockers",
            self.dynamic_model_blockers,
            allow_empty=True,
        )
        target_model_ids = {target.model_id for target in target_models}
        if any(
            blocker.model_id == observer_model.model_id or blocker.model_id in target_model_ids
            for blocker in blocker_models
        ):
            raise GeometryError(
                "TerrainVisibilityContext dynamic_model_blockers must exclude observer and target."
            )
        object.__setattr__(self, "dynamic_model_blockers", blocker_models)
        object.__setattr__(
            self,
            "observer_keywords",
            _validate_keyword_tuple(
                "TerrainVisibilityContext observer_keywords",
                self.observer_keywords,
            ),
        )
        object.__setattr__(
            self,
            "target_keywords",
            _validate_keyword_tuple(
                "TerrainVisibilityContext target_keywords",
                self.target_keywords,
            ),
        )

    @classmethod
    def from_ruleset_descriptor(
        cls,
        *,
        ruleset_descriptor: RulesetDescriptor,
        los_cache_key: str,
        observer_model: Model,
        target_models: tuple[Model, ...],
        terrain_features: tuple[TerrainFeatureDefinition, ...] = (),
        terrain_volumes: tuple[TerrainVolume, ...] = (),
        dynamic_model_blockers: tuple[Model, ...] = (),
        observer_keywords: tuple[str, ...] = (),
        target_keywords: tuple[str, ...] = (),
    ) -> Self:
        descriptor = _validate_ruleset_descriptor(ruleset_descriptor)
        return cls(
            ruleset_descriptor_hash=descriptor.descriptor_hash,
            los_cache_key=los_cache_key,
            terrain_visibility_policy=descriptor.terrain_visibility_policy,
            observer_model=observer_model,
            target_models=target_models,
            terrain_features=terrain_features,
            terrain_volumes=terrain_volumes,
            dynamic_model_blockers=dynamic_model_blockers,
            observer_keywords=observer_keywords,
            target_keywords=target_keywords,
        )

    def resolve_line_of_sight(self) -> LineOfSightWitness:
        records = tuple(
            self._resolve_model_line_of_sight(target_model) for target_model in self.target_models
        )
        return LineOfSightWitness.from_records(
            ruleset_descriptor_hash=self.ruleset_descriptor_hash,
            los_cache_key=self.los_cache_key,
            observer_model_id=self.observer_model.model_id,
            model_records=records,
        )

    def benefit_of_cover(self, witness: LineOfSightWitness) -> BenefitOfCoverResult:
        if type(witness) is not LineOfSightWitness:
            raise GeometryError("benefit_of_cover requires a LineOfSightWitness.")
        if witness.ruleset_descriptor_hash != self.ruleset_descriptor_hash:
            raise GeometryError("LineOfSightWitness ruleset hash does not match context.")
        if witness.los_cache_key != self.los_cache_key:
            raise GeometryError("LineOfSightWitness los_cache_key does not match context.")
        if witness.observer_model_id != self.observer_model.model_id:
            raise GeometryError("LineOfSightWitness observer does not match context.")
        target_model_ids = tuple(target_model.model_id for target_model in self.target_models)
        if witness.target_model_ids != target_model_ids:
            raise GeometryError("LineOfSightWitness targets do not match context.")
        return BenefitOfCoverResult.from_cover_sources(
            witness=witness,
            terrain_visibility_policy=self.terrain_visibility_policy,
            source_records=self._cover_source_records(witness),
        )

    def to_payload(self) -> TerrainVisibilityContextPayload:
        return {
            "ruleset_descriptor_hash": self.ruleset_descriptor_hash,
            "los_cache_key": self.los_cache_key,
            "observer_model": self.observer_model.to_payload(),
            "target_models": [model.to_payload() for model in self.target_models],
            "terrain_features": [feature.to_payload() for feature in self.terrain_features],
            "terrain_volumes": [volume.to_payload() for volume in self.terrain_volumes],
            "dynamic_model_blockers": [model.to_payload() for model in self.dynamic_model_blockers],
            "observer_keywords": list(self.observer_keywords),
            "target_keywords": list(self.target_keywords),
            "terrain_visibility_policy": self.terrain_visibility_policy.to_payload(),
        }

    @classmethod
    def from_payload(cls, payload: TerrainVisibilityContextPayload) -> Self:
        return cls(
            ruleset_descriptor_hash=payload["ruleset_descriptor_hash"],
            los_cache_key=payload["los_cache_key"],
            terrain_visibility_policy=TerrainVisibilityPolicyDescriptor.from_payload(
                payload["terrain_visibility_policy"]
            ),
            observer_model=Model.from_payload(payload["observer_model"]),
            target_models=tuple(Model.from_payload(model) for model in payload["target_models"]),
            terrain_features=tuple(
                TerrainFeatureDefinition.from_payload(feature)
                for feature in payload["terrain_features"]
            ),
            terrain_volumes=tuple(
                terrain_volume_from_payload(volume) for volume in payload["terrain_volumes"]
            ),
            dynamic_model_blockers=tuple(
                Model.from_payload(model) for model in payload["dynamic_model_blockers"]
            ),
            observer_keywords=tuple(payload["observer_keywords"]),
            target_keywords=tuple(payload["target_keywords"]),
        )

    def _resolve_model_line_of_sight(self, target_model: Model) -> ModelLineOfSightRecord:
        rays = _volume_sample_rays(self.observer_model, target_model)
        clear_ray_indices: list[int] = []
        blocker_records: list[VisibilityBlockerRecord] = []
        volume_feature_index = _terrain_volume_feature_index(self.terrain_features)
        for ray_index, ray in enumerate(rays):
            ray_blockers = self._blockers_for_ray(
                ray=ray,
                ray_index=ray_index,
                target_model=target_model,
                volume_feature_index=volume_feature_index,
            )
            blocker_records.extend(ray_blockers)
            if not any(record.blocks_model_visibility for record in ray_blockers):
                clear_ray_indices.append(ray_index)
        return ModelLineOfSightRecord(
            target_model_id=target_model.model_id,
            model_visible=bool(clear_ray_indices),
            model_fully_visible=(
                len(clear_ray_indices) == len(rays)
                and not any(record.blocks_full_visibility for record in blocker_records)
            ),
            checked_ray_count=len(rays),
            clear_ray_indices=tuple(clear_ray_indices),
            blocker_records=tuple(sorted(blocker_records, key=_visibility_blocker_record_sort_key)),
        )

    def _blockers_for_ray(
        self,
        *,
        ray: VisibilityRay,
        ray_index: int,
        target_model: Model,
        volume_feature_index: dict[str, TerrainFeatureDefinition],
    ) -> tuple[VisibilityBlockerRecord, ...]:
        physical_result = VisibilityQuery(
            rays=(ray,),
            static_terrain=self.terrain_volumes,
            dynamic_model_blockers=self.dynamic_model_blockers,
        ).resolve()
        records: list[VisibilityBlockerRecord] = []
        records.extend(
            _terrain_volume_blocker_record(
                terrain_id=terrain_id,
                ray_index=ray_index,
                volume_feature_index=volume_feature_index,
            )
            for terrain_id in physical_result.blocking_terrain_ids
        )
        records.extend(
            VisibilityBlockerRecord(
                blocker_kind=VisibilityBlockerKind.MODEL,
                blocker_id=model_id,
                ray_index=ray_index,
                terrain_feature_id=None,
                terrain_feature_kind=None,
                line_of_sight_policy=LineOfSightPolicy.TRUE_LINE_OF_SIGHT,
                blocks_model_visibility=True,
                blocks_full_visibility=True,
            )
            for model_id in physical_result.blocking_model_ids
        )
        records.extend(
            self._terrain_feature_policy_records_for_ray(
                ray=ray,
                ray_index=ray_index,
                target_model=target_model,
            )
        )
        return tuple(sorted(records, key=_visibility_blocker_record_sort_key))

    def _cover_source_records(self, witness: LineOfSightWitness) -> tuple[CoverSourceRecord, ...]:
        records: set[CoverSourceRecord] = set()
        for feature in self.terrain_features:
            feature_policy = _feature_visibility_policy(
                self.terrain_visibility_policy,
                feature.feature_kind,
            )
            if not feature_policy.cover_policy.grants_benefit_of_cover:
                continue
            if any(
                _model_footprint_wholly_within_feature(target_model, feature)
                for target_model in self.target_models
            ):
                records.add(
                    CoverSourceRecord(
                        feature_id=feature.feature_id,
                        feature_kind=feature.feature_kind,
                        policy_kind=feature_policy.line_of_sight_policy,
                        reason=CoverSourceReason.WHOLLY_WITHIN_FEATURE,
                    )
                )

        for blocker_record in witness.all_blocker_records():
            if not blocker_record.blocks_full_visibility:
                continue
            if (
                blocker_record.terrain_feature_id is None
                or blocker_record.terrain_feature_kind is None
            ):
                continue
            feature_policy = _feature_visibility_policy(
                self.terrain_visibility_policy,
                blocker_record.terrain_feature_kind,
            )
            if not feature_policy.cover_policy.grants_benefit_of_cover:
                continue
            records.add(
                CoverSourceRecord(
                    feature_id=blocker_record.terrain_feature_id,
                    feature_kind=blocker_record.terrain_feature_kind,
                    policy_kind=feature_policy.line_of_sight_policy,
                    reason=CoverSourceReason.NOT_FULLY_VISIBLE_BECAUSE_OF_FEATURE,
                )
            )
        return tuple(sorted(records, key=_cover_source_record_sort_key))

    def _terrain_feature_policy_records_for_ray(
        self,
        *,
        ray: VisibilityRay,
        ray_index: int,
        target_model: Model,
    ) -> tuple[VisibilityBlockerRecord, ...]:
        records: list[VisibilityBlockerRecord] = []
        for feature in self.terrain_features:
            policy = _feature_visibility_policy(
                self.terrain_visibility_policy,
                feature.feature_kind,
            )
            if (
                not policy.blocks_model_visibility_through_footprint
                and not policy.blocks_full_visibility_through_footprint
            ):
                continue
            if not _ray_crosses_feature_footprint_between_observer_and_target(ray, feature):
                continue
            exception = _terrain_feature_visibility_exception(
                policy=policy,
                feature=feature,
                observer_model=self.observer_model,
                target_model=target_model,
                observer_keywords=self.observer_keywords,
                target_keywords=self.target_keywords,
            )
            records.append(
                VisibilityBlockerRecord(
                    blocker_kind=VisibilityBlockerKind.TERRAIN_FEATURE,
                    blocker_id=feature.feature_id,
                    ray_index=ray_index,
                    terrain_feature_id=feature.feature_id,
                    terrain_feature_kind=feature.feature_kind,
                    line_of_sight_policy=policy.line_of_sight_policy,
                    blocks_model_visibility=(
                        False
                        if exception is not None
                        else policy.blocks_model_visibility_through_footprint
                    ),
                    blocks_full_visibility=(
                        False
                        if exception is not None
                        else policy.blocks_full_visibility_through_footprint
                    ),
                    exception_applied=exception,
                )
            )
        return tuple(sorted(records, key=_visibility_blocker_record_sort_key))


@dataclass(frozen=True, slots=True)
class VisibilityResult:
    has_line_of_sight: bool
    checked_ray_count: int
    clear_ray_index: int | None
    blocking_terrain_ids: tuple[str, ...] = ()
    blocking_model_ids: tuple[str, ...] = ()
    checked_terrain_ids: tuple[str, ...] = ()
    checked_model_ids: tuple[str, ...] = ()
    metrics: VisibilityMetrics = field(default_factory=VisibilityMetrics)

    def __post_init__(self) -> None:
        if type(self.has_line_of_sight) is not bool:
            raise GeometryError("VisibilityResult has_line_of_sight must be a bool.")
        if type(self.checked_ray_count) is not int or self.checked_ray_count < 1:
            raise GeometryError("VisibilityResult checked_ray_count must be a positive integer.")
        if self.clear_ray_index is not None:
            if type(self.clear_ray_index) is not int:
                raise GeometryError("VisibilityResult clear_ray_index must be an integer.")
            if self.clear_ray_index < 0 or self.clear_ray_index >= self.checked_ray_count:
                raise GeometryError("VisibilityResult clear_ray_index is outside checked rays.")
        if self.has_line_of_sight and self.clear_ray_index is None:
            raise GeometryError("Visible VisibilityResult must include clear_ray_index.")
        if not self.has_line_of_sight and self.clear_ray_index is not None:
            raise GeometryError("Blocked VisibilityResult must not include clear_ray_index.")

        object.__setattr__(
            self,
            "blocking_terrain_ids",
            _validate_identifier_tuple(
                "VisibilityResult blocking_terrain_ids", self.blocking_terrain_ids
            ),
        )
        object.__setattr__(
            self,
            "blocking_model_ids",
            _validate_identifier_tuple(
                "VisibilityResult blocking_model_ids", self.blocking_model_ids
            ),
        )
        object.__setattr__(
            self,
            "checked_terrain_ids",
            _validate_identifier_tuple(
                "VisibilityResult checked_terrain_ids", self.checked_terrain_ids
            ),
        )
        object.__setattr__(
            self,
            "checked_model_ids",
            _validate_identifier_tuple(
                "VisibilityResult checked_model_ids", self.checked_model_ids
            ),
        )
        if type(self.metrics) is not VisibilityMetrics:
            raise GeometryError("VisibilityResult metrics must be VisibilityMetrics.")

    def to_payload(self) -> VisibilityResultPayload:
        return {
            "has_line_of_sight": self.has_line_of_sight,
            "checked_ray_count": self.checked_ray_count,
            "clear_ray_index": self.clear_ray_index,
            "blocking_terrain_ids": list(self.blocking_terrain_ids),
            "blocking_model_ids": list(self.blocking_model_ids),
            "checked_terrain_ids": list(self.checked_terrain_ids),
            "checked_model_ids": list(self.checked_model_ids),
            "metrics": self.metrics.to_payload(),
        }

    @classmethod
    def from_payload(cls, payload: VisibilityResultPayload) -> Self:
        return cls(
            has_line_of_sight=payload["has_line_of_sight"],
            checked_ray_count=payload["checked_ray_count"],
            clear_ray_index=payload["clear_ray_index"],
            blocking_terrain_ids=tuple(payload["blocking_terrain_ids"]),
            blocking_model_ids=tuple(payload["blocking_model_ids"]),
            checked_terrain_ids=tuple(payload["checked_terrain_ids"]),
            checked_model_ids=tuple(payload["checked_model_ids"]),
            metrics=VisibilityMetrics.from_payload(payload["metrics"]),
        )


def visibility_blocker_kind_from_token(token: object) -> VisibilityBlockerKind:
    if type(token) is VisibilityBlockerKind:
        return token
    if type(token) is not str:
        raise GeometryError("VisibilityBlockerKind token must be a string.")
    try:
        return VisibilityBlockerKind(token)
    except ValueError as exc:
        raise GeometryError(f"Unsupported VisibilityBlockerKind token: {token}.") from exc


def cover_source_reason_from_token(token: object) -> CoverSourceReason:
    if type(token) is CoverSourceReason:
        return token
    if type(token) is not str:
        raise GeometryError("CoverSourceReason token must be a string.")
    try:
        return CoverSourceReason(token)
    except ValueError as exc:
        raise GeometryError(f"Unsupported CoverSourceReason token: {token}.") from exc


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


def _feature_visibility_policy(
    terrain_visibility_policy: TerrainVisibilityPolicyDescriptor,
    terrain_feature_kind: TerrainFeatureKind,
) -> TerrainFeatureVisibilityPolicy:
    try:
        return terrain_visibility_policy.policy_for_feature_kind(terrain_feature_kind)
    except RulesetDescriptorError as exc:
        raise GeometryError("Terrain visibility policy does not cover terrain feature.") from exc


def _validate_ruleset_descriptor(value: object) -> RulesetDescriptor:
    if type(value) is not RulesetDescriptor:
        raise GeometryError("Terrain visibility requires an explicit RulesetDescriptor.")
    return value


def _validate_ray(value: object) -> VisibilityRay:
    if type(value) is not tuple:
        raise GeometryError("VisibilityQuery rays must contain Point3 pairs.")
    ray = cast(tuple[object, object], value)
    if len(ray) != 2:
        raise GeometryError("VisibilityQuery rays must contain Point3 pairs.")
    start, end = ray
    return (
        validate_point3("VisibilityQuery ray start", start),
        validate_point3("VisibilityQuery ray end", end),
    )


def _validate_terrain(field_name: str, value: object) -> TerrainVolume:
    if not isinstance(value, TerrainVolume):
        raise GeometryError(f"{field_name} must be a TerrainVolume.")
    return value


def _validate_model(field_name: str, value: object) -> Model:
    if type(value) is not Model:
        raise GeometryError(f"{field_name} must be a Model.")
    return value


def _validate_model_tuple(
    field_name: str,
    values: object,
    *,
    allow_empty: bool,
) -> tuple[Model, ...]:
    if type(values) is not tuple:
        raise GeometryError(f"{field_name} must be a tuple.")
    raw_values = cast(tuple[object, ...], values)
    models = tuple(_validate_model(f"{field_name} value", value) for value in raw_values)
    if not allow_empty and not models:
        raise GeometryError(f"{field_name} must not be empty.")
    _validate_unique_model_ids(models)
    return tuple(sorted(models, key=lambda model: model.model_id))


def _validate_terrain_feature_tuple(
    field_name: str,
    values: object,
) -> tuple[TerrainFeatureDefinition, ...]:
    if type(values) is not tuple:
        raise GeometryError(f"{field_name} must be a tuple.")
    features: list[TerrainFeatureDefinition] = []
    seen: set[str] = set()
    for value in cast(tuple[object, ...], values):
        if type(value) is not TerrainFeatureDefinition:
            raise GeometryError(f"{field_name} must contain TerrainFeatureDefinition values.")
        if value.feature_id in seen:
            raise GeometryError(f"{field_name} must not contain duplicate IDs.")
        seen.add(value.feature_id)
        features.append(value)
    return tuple(sorted(features, key=lambda feature: feature.feature_id))


def _validate_terrain_volume_tuple(
    field_name: str,
    values: object,
) -> tuple[TerrainVolume, ...]:
    if type(values) is not tuple:
        raise GeometryError(f"{field_name} must be a tuple.")
    raw_values = cast(tuple[object, ...], values)
    terrain = tuple(_validate_terrain(f"{field_name} value", value) for value in raw_values)
    _validate_unique_terrain_ids(terrain)
    return tuple(sorted(terrain, key=lambda volume: volume.terrain_id))


def _validate_unique_terrain_ids(terrain: tuple[TerrainVolume, ...]) -> None:
    seen: set[str] = set()
    for volume in terrain:
        if volume.terrain_id in seen:
            raise GeometryError("VisibilityQuery static_terrain must not contain duplicate IDs.")
        seen.add(volume.terrain_id)


def _validate_unique_model_ids(models: tuple[Model, ...]) -> None:
    seen: set[str] = set()
    for model in models:
        if model.model_id in seen:
            raise GeometryError(
                "VisibilityQuery dynamic_model_blockers must not contain duplicate IDs."
            )
        seen.add(model.model_id)


def _validate_positive_int(field_name: str, value: object) -> int:
    if type(value) is not int:
        raise GeometryError(f"{field_name} must be an integer.")
    if value < 1:
        raise GeometryError(f"{field_name} must be positive.")
    return value


def _validate_identifier(field_name: str, value: object) -> str:
    if type(value) is not str:
        raise GeometryError(f"{field_name} must be a string.")
    stripped = value.strip()
    if not stripped:
        raise GeometryError(f"{field_name} must not be empty.")
    return stripped


def _validate_optional_identifier(field_name: str, value: object | None) -> str | None:
    if value is None:
        return None
    return _validate_identifier(field_name, value)


def _validate_identifier_tuple(field_name: str, values: tuple[str, ...]) -> tuple[str, ...]:
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


def _validate_keyword_tuple(field_name: str, values: object) -> tuple[str, ...]:
    if type(values) is not tuple:
        raise GeometryError(f"{field_name} must be a tuple.")
    keywords: list[str] = []
    seen: set[str] = set()
    for value in cast(tuple[object, ...], values):
        keyword = _validate_identifier(f"{field_name} value", value)
        keyword = keyword.upper().replace(" ", "_").replace("-", "_")
        if keyword in seen:
            raise GeometryError(f"{field_name} must not contain duplicate keywords.")
        seen.add(keyword)
        keywords.append(keyword)
    return tuple(sorted(keywords))


def _validate_ray_index_tuple(
    field_name: str,
    values: object,
    *,
    checked_ray_count: int,
) -> tuple[int, ...]:
    if type(values) is not tuple:
        raise GeometryError(f"{field_name} must be a tuple.")
    indices: list[int] = []
    seen: set[int] = set()
    for value in cast(tuple[object, ...], values):
        if type(value) is not int:
            raise GeometryError(f"{field_name} values must be integers.")
        if value < 0 or value >= checked_ray_count:
            raise GeometryError(f"{field_name} value is outside checked rays.")
        if value in seen:
            raise GeometryError(f"{field_name} must not contain duplicate indices.")
        seen.add(value)
        indices.append(value)
    return tuple(sorted(indices))


def _validate_blocker_record_tuple(
    field_name: str,
    values: object,
) -> tuple[VisibilityBlockerRecord, ...]:
    if type(values) is not tuple:
        raise GeometryError(f"{field_name} must be a tuple.")
    records: list[VisibilityBlockerRecord] = []
    seen: set[tuple[str, str, int, bool, bool, str | None]] = set()
    for value in cast(tuple[object, ...], values):
        if type(value) is not VisibilityBlockerRecord:
            raise GeometryError(f"{field_name} must contain VisibilityBlockerRecord values.")
        key = (
            value.blocker_kind.value,
            value.blocker_id,
            value.ray_index,
            value.blocks_model_visibility,
            value.blocks_full_visibility,
            value.exception_applied,
        )
        if key in seen:
            raise GeometryError(f"{field_name} must not contain duplicate records.")
        seen.add(key)
        records.append(value)
    return tuple(sorted(records, key=_visibility_blocker_record_sort_key))


def _validate_cover_source_record_tuple(
    field_name: str,
    values: object,
) -> tuple[CoverSourceRecord, ...]:
    if type(values) is not tuple:
        raise GeometryError(f"{field_name} must be a tuple.")
    records: list[CoverSourceRecord] = []
    seen: set[tuple[str, str, str, str]] = set()
    for value in cast(tuple[object, ...], values):
        if type(value) is not CoverSourceRecord:
            raise GeometryError(f"{field_name} must contain CoverSourceRecord values.")
        key = (
            value.feature_id,
            value.feature_kind.value,
            value.policy_kind.value,
            value.reason.value,
        )
        if key in seen:
            raise GeometryError(f"{field_name} must not contain duplicate records.")
        seen.add(key)
        records.append(value)
    return tuple(sorted(records, key=_cover_source_record_sort_key))


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


def _validate_non_negative_int(field_name: str, value: object) -> int:
    if type(value) is not int:
        raise GeometryError(f"{field_name} must be an integer.")
    if value < 0:
        raise GeometryError(f"{field_name} must not be negative.")
    return value


def _terrain_volume_feature_index(
    features: tuple[TerrainFeatureDefinition, ...],
) -> dict[str, TerrainFeatureDefinition]:
    index: dict[str, TerrainFeatureDefinition] = {}
    for feature in features:
        for volume in feature.terrain_volumes():
            if volume.terrain_id in index:
                raise GeometryError("Terrain feature volumes must not contain duplicate IDs.")
            index[volume.terrain_id] = feature
    return index


def _terrain_volume_blocker_record(
    *,
    terrain_id: str,
    ray_index: int,
    volume_feature_index: dict[str, TerrainFeatureDefinition],
) -> VisibilityBlockerRecord:
    feature = volume_feature_index.get(terrain_id)
    return VisibilityBlockerRecord(
        blocker_kind=VisibilityBlockerKind.TERRAIN_VOLUME,
        blocker_id=terrain_id,
        ray_index=ray_index,
        terrain_feature_id=None if feature is None else feature.feature_id,
        terrain_feature_kind=None if feature is None else feature.feature_kind,
        line_of_sight_policy=LineOfSightPolicy.TRUE_LINE_OF_SIGHT,
        blocks_model_visibility=True,
        blocks_full_visibility=True,
    )


def _visibility_blocker_record_sort_key(
    record: VisibilityBlockerRecord,
) -> tuple[int, str, str, str | None]:
    return (
        record.ray_index,
        record.blocker_kind.value,
        record.blocker_id,
        record.exception_applied,
    )


def _cover_source_record_sort_key(
    record: CoverSourceRecord,
) -> tuple[str, str, str, str]:
    return (
        record.feature_id,
        record.feature_kind.value,
        record.policy_kind.value,
        record.reason.value,
    )


def _volume_sample_rays(observer: Model, target: Model) -> tuple[VisibilityRay, ...]:
    observer_points = _model_visibility_points(observer)
    target_points = _model_visibility_points(target)
    return tuple((start, end) for start in observer_points for end in target_points)


def _model_visibility_points(model: Model) -> tuple[Point3, ...]:
    valid_model = _validate_model("model", model)
    position = valid_model.pose.position
    radius = valid_model.base.max_radius()
    bottom_z, top_z = valid_model.volume.vertical_interval(valid_model.pose)
    mid_z = bottom_z + ((top_z - bottom_z) / 2.0)
    return (
        Point3(position.x, position.y, bottom_z),
        Point3(position.x, position.y, mid_z),
        Point3(position.x, position.y, top_z),
        Point3(position.x - radius, position.y, mid_z),
        Point3(position.x + radius, position.y, mid_z),
        Point3(position.x, position.y - radius, mid_z),
        Point3(position.x, position.y + radius, mid_z),
    )


def _terrain_feature_visibility_exception(
    *,
    policy: TerrainFeatureVisibilityPolicy,
    feature: TerrainFeatureDefinition,
    observer_model: Model,
    target_model: Model,
    observer_keywords: tuple[str, ...],
    target_keywords: tuple[str, ...],
) -> str | None:
    observer_wholly_within = _model_footprint_wholly_within_feature(observer_model, feature)
    target_wholly_within = _model_footprint_wholly_within_feature(target_model, feature)
    observer_keyword_set = set(observer_keywords)
    target_keyword_set = set(target_keywords)
    if policy.aircraft_uses_true_los_through_feature and (
        "AIRCRAFT" in observer_keyword_set or "AIRCRAFT" in target_keyword_set
    ):
        return "aircraft"
    if policy.towering_uses_true_los_when_wholly_within_feature and (
        ("TOWERING" in observer_keyword_set and observer_wholly_within)
        or ("TOWERING" in target_keyword_set and target_wholly_within)
    ):
        return "towering_wholly_within"
    if policy.uses_true_los_when_observer_wholly_within_feature and observer_wholly_within:
        return "observer_wholly_within"
    if policy.uses_true_los_when_target_wholly_within_feature and target_wholly_within:
        return "target_wholly_within"
    return None


def _model_footprint_intersects_feature(
    model: Model,
    feature: TerrainFeatureDefinition,
) -> bool:
    valid_model = _validate_model("model", model)
    if type(feature) is not TerrainFeatureDefinition:
        raise GeometryError("feature must be a TerrainFeatureDefinition.")
    return shapely_backend.base_footprint_intersects_bounds(
        valid_model.base,
        valid_model.pose,
        feature.bounds(),
    )


def _model_footprint_wholly_within_feature(
    model: Model,
    feature: TerrainFeatureDefinition,
) -> bool:
    valid_model = _validate_model("model", model)
    if type(feature) is not TerrainFeatureDefinition:
        raise GeometryError("feature must be a TerrainFeatureDefinition.")
    if not _model_footprint_intersects_feature(valid_model, feature):
        return False
    return shapely_backend.base_footprint_within_bounds(
        valid_model.base,
        valid_model.pose,
        feature.bounds(),
    )


def _ray_crosses_feature_footprint_between_observer_and_target(
    ray: VisibilityRay,
    feature: TerrainFeatureDefinition,
) -> bool:
    if type(feature) is not TerrainFeatureDefinition:
        raise GeometryError("feature must be a TerrainFeatureDefinition.")
    return _segment_intersects_bounds(ray, feature.bounds())


def _segment_intersects_bounds(
    ray: VisibilityRay,
    bounds: tuple[float, float, float, float],
) -> bool:
    start, end = ray
    min_x, min_y, max_x, max_y = bounds
    dx = end.x - start.x
    dy = end.y - start.y
    start_t = 0.0
    end_t = 1.0

    for edge_delta, edge_distance in (
        (-dx, start.x - min_x),
        (dx, max_x - start.x),
        (-dy, start.y - min_y),
        (dy, max_y - start.y),
    ):
        if edge_delta == 0.0:
            if edge_distance < 0.0:
                return False
            continue
        edge_t = edge_distance / edge_delta
        if edge_delta < 0.0:
            if edge_t > end_t:
                return False
            start_t = max(start_t, edge_t)
        else:
            if edge_t < start_t:
                return False
            end_t = min(end_t, edge_t)
    return True


def _terrain_broad_phase_intersects(ray: VisibilityRay, terrain: TerrainVolume) -> bool:
    start, end = ray
    return _bounds_overlap(
        _segment_bounds(start, end), (*terrain.horizontal_bounds(), *terrain.vertical_interval())
    )


def _model_broad_phase_intersects(ray: VisibilityRay, model: Model) -> bool:
    radius = model.base.max_radius()
    model_bounds = (
        model.pose.position.x - radius,
        model.pose.position.y - radius,
        model.pose.position.x + radius,
        model.pose.position.y + radius,
        *model.volume.vertical_interval(model.pose),
    )
    return _bounds_overlap(_segment_bounds(ray[0], ray[1]), model_bounds)


def _segment_bounds(start: Point3, end: Point3) -> tuple[float, float, float, float, float, float]:
    return (
        min(start.x, end.x),
        min(start.y, end.y),
        max(start.x, end.x),
        max(start.y, end.y),
        min(start.z, end.z),
        max(start.z, end.z),
    )


def _bounds_overlap(
    segment_bounds: tuple[float, float, float, float, float, float],
    obstacle_bounds: tuple[float, float, float, float, float, float],
) -> bool:
    min_x, min_y, max_x, max_y, min_z, max_z = segment_bounds
    (
        obstacle_min_x,
        obstacle_min_y,
        obstacle_max_x,
        obstacle_max_y,
        obstacle_min_z,
        obstacle_max_z,
    ) = obstacle_bounds
    return (
        max_x >= obstacle_min_x
        and min_x <= obstacle_max_x
        and max_y >= obstacle_min_y
        and min_y <= obstacle_max_y
        and max_z >= obstacle_min_z
        and min_z <= obstacle_max_z
    )
