from __future__ import annotations

import math
from dataclasses import dataclass, field
from enum import StrEnum
from typing import Self, TypedDict, cast

from warhammer40k_core.core.unit_group import UnitGroup, UnitGroupPayload
from warhammer40k_core.geometry import shapely_backend
from warhammer40k_core.geometry.base import CircularBase
from warhammer40k_core.geometry.collision import CollisionSet, CollisionSetPayload
from warhammer40k_core.geometry.movement_envelope import (
    MovementEnvelope,
    MovementEnvelopePayload,
)
from warhammer40k_core.geometry.pose import (
    Facing,
    GeometryError,
    Point3,
    Pose,
    PosePayload,
    validate_pose,
)
from warhammer40k_core.geometry.spatial_index import SpatialIndex, SpatialIndexPayload
from warhammer40k_core.geometry.terrain import (
    TerrainVolume,
    TerrainVolumePayload,
    terrain_volume_from_payload,
)
from warhammer40k_core.geometry.volume import Model, ModelPayload

type ModelPath = tuple[str, tuple[Pose, ...]]
type ModelPathEndpoint = tuple[str, Pose, Pose]


class PathFailureReason(StrEnum):
    GROUP_MISMATCH = "group_mismatch"
    MISSING_MODEL = "missing_model"
    STARTING_POSE_MISMATCH = "starting_pose_mismatch"
    ENDPOINT_ONLY_PATH = "endpoint_only_path"
    MOVEMENT_DISTANCE_EXCEEDED = "movement_distance_exceeded"
    MODEL_COLLISION = "model_collision"
    SELF_COLLISION = "self_collision"
    TERRAIN_COLLISION = "terrain_collision"
    ENGAGEMENT_RANGE = "engagement_range"
    COHERENCY = "coherency"


class ModelPathPayload(TypedDict):
    model_id: str
    poses: list[PosePayload]


class PathWitnessPayload(TypedDict):
    model_paths: list[ModelPathPayload]


class PathFailurePayload(TypedDict):
    reason: str
    message: str
    model_id: str | None
    blocker_id: str | None


class PathResultPayload(TypedDict):
    is_valid: bool
    witness: PathWitnessPayload | None
    failure: PathFailurePayload | None
    metrics: PathMetricsPayload


class PathMetricsPayload(TypedDict):
    sampled_pose_count: int
    model_collision_check_count: int
    terrain_collision_check_count: int
    engagement_check_count: int


class PathQueryPayload(TypedDict):
    unit_group: UnitGroupPayload
    spatial_index: SpatialIndexPayload
    witness: PathWitnessPayload
    movement_envelope: MovementEnvelopePayload
    collision_set: CollisionSetPayload


class PathConstraintViolationPayload(TypedDict):
    violation_code: str
    message: str
    model_id: str | None
    blocker_id: str | None


class PathValidationResultPayload(TypedDict):
    is_valid: bool
    violations: list[PathConstraintViolationPayload]
    sampled_pose_count: int
    model_collision_check_count: int
    terrain_collision_check_count: int
    engagement_check_count: int
    pivot_cost_inches: float
    pivot_cost_pending: bool


class PathValidationContextPayload(TypedDict):
    moving_model: ModelPayload
    witness: PathWitnessPayload
    battlefield_width_inches: float
    battlefield_depth_inches: float
    friendly_models: list[ModelPayload]
    enemy_models: list[ModelPayload]
    terrain: list[TerrainVolumePayload]
    friendly_vehicle_monster_model_ids: list[str]
    may_transit_enemy_models: bool
    may_transit_enemy_engagement: bool
    may_end_in_enemy_engagement: bool
    enemy_engagement_horizontal_inches: float
    enemy_engagement_vertical_inches: float
    sample_interval_inches: float


@dataclass(frozen=True, slots=True)
class PathConstraintViolation:
    violation_code: str
    message: str
    model_id: str | None = None
    blocker_id: str | None = None

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "violation_code",
            _validate_identifier("PathConstraintViolation violation_code", self.violation_code),
        )
        object.__setattr__(
            self,
            "message",
            _validate_identifier("PathConstraintViolation message", self.message),
        )
        object.__setattr__(
            self,
            "model_id",
            _validate_optional_identifier("PathConstraintViolation model_id", self.model_id),
        )
        object.__setattr__(
            self,
            "blocker_id",
            _validate_optional_identifier("PathConstraintViolation blocker_id", self.blocker_id),
        )

    def to_payload(self) -> PathConstraintViolationPayload:
        return {
            "violation_code": self.violation_code,
            "message": self.message,
            "model_id": self.model_id,
            "blocker_id": self.blocker_id,
        }

    @classmethod
    def from_payload(cls, payload: PathConstraintViolationPayload) -> Self:
        return cls(
            violation_code=payload["violation_code"],
            message=payload["message"],
            model_id=payload["model_id"],
            blocker_id=payload["blocker_id"],
        )


@dataclass(frozen=True, slots=True)
class PathValidationResult:
    violations: tuple[PathConstraintViolation, ...] = ()
    sampled_pose_count: int = 0
    model_collision_check_count: int = 0
    terrain_collision_check_count: int = 0
    engagement_check_count: int = 0
    pivot_cost_inches: float = 0.0
    pivot_cost_pending: bool = False

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "violations",
            _validate_path_constraint_violations(self.violations),
        )
        object.__setattr__(
            self,
            "sampled_pose_count",
            _validate_non_negative_int(
                "PathValidationResult sampled_pose_count",
                self.sampled_pose_count,
            ),
        )
        object.__setattr__(
            self,
            "model_collision_check_count",
            _validate_non_negative_int(
                "PathValidationResult model_collision_check_count",
                self.model_collision_check_count,
            ),
        )
        object.__setattr__(
            self,
            "terrain_collision_check_count",
            _validate_non_negative_int(
                "PathValidationResult terrain_collision_check_count",
                self.terrain_collision_check_count,
            ),
        )
        object.__setattr__(
            self,
            "engagement_check_count",
            _validate_non_negative_int(
                "PathValidationResult engagement_check_count",
                self.engagement_check_count,
            ),
        )
        object.__setattr__(
            self,
            "pivot_cost_inches",
            _validate_non_negative_number(
                "PathValidationResult pivot_cost_inches",
                self.pivot_cost_inches,
            ),
        )
        _validate_bool("PathValidationResult pivot_cost_pending", self.pivot_cost_pending)

    @classmethod
    def valid(
        cls,
        *,
        sampled_pose_count: int,
        model_collision_check_count: int,
        terrain_collision_check_count: int,
        engagement_check_count: int,
        pivot_cost_inches: float = 0.0,
        pivot_cost_pending: bool = False,
    ) -> Self:
        return cls(
            sampled_pose_count=sampled_pose_count,
            model_collision_check_count=model_collision_check_count,
            terrain_collision_check_count=terrain_collision_check_count,
            engagement_check_count=engagement_check_count,
            pivot_cost_inches=pivot_cost_inches,
            pivot_cost_pending=pivot_cost_pending,
        )

    @classmethod
    def invalid(
        cls,
        violation: PathConstraintViolation,
        *,
        sampled_pose_count: int,
        model_collision_check_count: int,
        terrain_collision_check_count: int,
        engagement_check_count: int,
        pivot_cost_inches: float = 0.0,
        pivot_cost_pending: bool = False,
    ) -> Self:
        return cls(
            violations=(violation,),
            sampled_pose_count=sampled_pose_count,
            model_collision_check_count=model_collision_check_count,
            terrain_collision_check_count=terrain_collision_check_count,
            engagement_check_count=engagement_check_count,
            pivot_cost_inches=pivot_cost_inches,
            pivot_cost_pending=pivot_cost_pending,
        )

    @property
    def is_valid(self) -> bool:
        return not self.violations

    def to_payload(self) -> PathValidationResultPayload:
        return {
            "is_valid": self.is_valid,
            "violations": [violation.to_payload() for violation in self.violations],
            "sampled_pose_count": self.sampled_pose_count,
            "model_collision_check_count": self.model_collision_check_count,
            "terrain_collision_check_count": self.terrain_collision_check_count,
            "engagement_check_count": self.engagement_check_count,
            "pivot_cost_inches": self.pivot_cost_inches,
            "pivot_cost_pending": self.pivot_cost_pending,
        }

    @classmethod
    def from_payload(cls, payload: PathValidationResultPayload) -> Self:
        result = cls(
            violations=tuple(
                PathConstraintViolation.from_payload(violation)
                for violation in payload["violations"]
            ),
            sampled_pose_count=payload["sampled_pose_count"],
            model_collision_check_count=payload["model_collision_check_count"],
            terrain_collision_check_count=payload["terrain_collision_check_count"],
            engagement_check_count=payload["engagement_check_count"],
            pivot_cost_inches=payload["pivot_cost_inches"],
            pivot_cost_pending=payload["pivot_cost_pending"],
        )
        if result.is_valid != payload["is_valid"]:
            raise GeometryError("PathValidationResult payload validity does not match violations.")
        return result


@dataclass(frozen=True, slots=True)
class PathValidationContext:
    moving_model: Model
    witness: PathWitness
    battlefield_width_inches: float
    battlefield_depth_inches: float
    friendly_models: tuple[Model, ...] = ()
    enemy_models: tuple[Model, ...] = ()
    terrain: tuple[TerrainVolume, ...] = ()
    friendly_vehicle_monster_model_ids: tuple[str, ...] = ()
    may_transit_enemy_models: bool = False
    may_transit_enemy_engagement: bool = False
    may_end_in_enemy_engagement: bool = False
    enemy_engagement_horizontal_inches: float = 1.0
    enemy_engagement_vertical_inches: float = 5.0
    sample_interval_inches: float = 0.5

    def __post_init__(self) -> None:
        if type(self.moving_model) is not Model:
            raise GeometryError("PathValidationContext moving_model must be a Model.")
        if type(self.witness) is not PathWitness:
            raise GeometryError("PathValidationContext witness must be a PathWitness.")
        if self.witness.model_ids() != (self.moving_model.model_id,):
            raise GeometryError("PathValidationContext witness must contain only the moving model.")
        object.__setattr__(
            self,
            "battlefield_width_inches",
            _validate_positive_number(
                "PathValidationContext battlefield_width_inches",
                self.battlefield_width_inches,
            ),
        )
        object.__setattr__(
            self,
            "battlefield_depth_inches",
            _validate_positive_number(
                "PathValidationContext battlefield_depth_inches",
                self.battlefield_depth_inches,
            ),
        )
        friendly_models = _validate_model_tuple(
            "PathValidationContext friendly_models",
            self.friendly_models,
        )
        enemy_models = _validate_model_tuple(
            "PathValidationContext enemy_models",
            self.enemy_models,
        )
        _validate_disjoint_model_ids(
            moving_model=self.moving_model,
            friendly_models=friendly_models,
            enemy_models=enemy_models,
        )
        object.__setattr__(self, "friendly_models", friendly_models)
        object.__setattr__(self, "enemy_models", enemy_models)
        object.__setattr__(
            self,
            "terrain",
            _validate_terrain_tuple("PathValidationContext terrain", self.terrain),
        )
        friendly_vehicle_monster_model_ids = _validate_identifier_tuple(
            "PathValidationContext friendly_vehicle_monster_model_ids",
            self.friendly_vehicle_monster_model_ids,
        )
        friendly_model_ids = {model.model_id for model in friendly_models}
        if any(
            model_id not in friendly_model_ids for model_id in friendly_vehicle_monster_model_ids
        ):
            raise GeometryError(
                "PathValidationContext friendly_vehicle_monster_model_ids must reference "
                "friendly models."
            )
        object.__setattr__(
            self,
            "friendly_vehicle_monster_model_ids",
            friendly_vehicle_monster_model_ids,
        )
        _validate_bool(
            "PathValidationContext may_transit_enemy_models",
            self.may_transit_enemy_models,
        )
        _validate_bool(
            "PathValidationContext may_transit_enemy_engagement",
            self.may_transit_enemy_engagement,
        )
        _validate_bool(
            "PathValidationContext may_end_in_enemy_engagement",
            self.may_end_in_enemy_engagement,
        )
        object.__setattr__(
            self,
            "enemy_engagement_horizontal_inches",
            _validate_non_negative_number(
                "PathValidationContext enemy_engagement_horizontal_inches",
                self.enemy_engagement_horizontal_inches,
            ),
        )
        object.__setattr__(
            self,
            "enemy_engagement_vertical_inches",
            _validate_non_negative_number(
                "PathValidationContext enemy_engagement_vertical_inches",
                self.enemy_engagement_vertical_inches,
            ),
        )
        object.__setattr__(
            self,
            "sample_interval_inches",
            _validate_positive_number(
                "PathValidationContext sample_interval_inches",
                self.sample_interval_inches,
            ),
        )

    def validate(self) -> PathValidationResult:
        path = self.witness.poses_for_model(self.moving_model.model_id)
        pivot_cost_pending = _path_requires_pivot_cost_placeholder(self.moving_model, path)
        if path[0] != self.moving_model.pose:
            return _invalid_path_validation(
                "starting_pose_mismatch",
                "Path witness must start at the moving model pose.",
                model_id=self.moving_model.model_id,
                metrics=_PathValidationMetricCounts(sampled_pose_count=len(path)),
                pivot_cost_pending=pivot_cost_pending,
            )

        metrics = _PathValidationMetricCounts()
        sampled_path = _sampled_pose_path(path, sample_interval_inches=self.sample_interval_inches)
        metrics.sampled_pose_count = len(sampled_path)
        transit_poses = sampled_path[1:-1]

        for pose in sampled_path:
            sampled_model = _model_at_pose(self.moving_model, pose)
            if not _model_is_within_battlefield(
                sampled_model,
                battlefield_width_inches=self.battlefield_width_inches,
                battlefield_depth_inches=self.battlefield_depth_inches,
            ):
                return _invalid_path_validation(
                    "battlefield_edge_crossed",
                    "Path witness crosses the battlefield edge.",
                    model_id=self.moving_model.model_id,
                    metrics=metrics,
                    pivot_cost_pending=pivot_cost_pending,
                )

        for pose in transit_poses:
            sampled_model = _model_at_pose(self.moving_model, pose)
            for enemy_model in self.enemy_models:
                metrics.model_collision_check_count += 1
                if _models_overlap_with_volume(sampled_model, enemy_model):
                    if self.may_transit_enemy_models:
                        continue
                    return _invalid_path_validation(
                        "enemy_model_base_crossed",
                        "Path witness crosses an enemy model base.",
                        model_id=self.moving_model.model_id,
                        blocker_id=enemy_model.model_id,
                        metrics=metrics,
                        pivot_cost_pending=pivot_cost_pending,
                    )
            for friendly_model in self.friendly_models:
                metrics.model_collision_check_count += 1
                if friendly_model.model_id not in self.friendly_vehicle_monster_model_ids:
                    continue
                if _models_overlap_with_volume(sampled_model, friendly_model):
                    return _invalid_path_validation(
                        "friendly_vehicle_monster_transit_forbidden",
                        "Path witness crosses a friendly VEHICLE/MONSTER blocker.",
                        model_id=self.moving_model.model_id,
                        blocker_id=friendly_model.model_id,
                        metrics=metrics,
                        pivot_cost_pending=pivot_cost_pending,
                    )

        for pose in sampled_path:
            sampled_model = _model_at_pose(self.moving_model, pose)
            for terrain in self.terrain:
                metrics.terrain_collision_check_count += 1
                if terrain.intersects_model(sampled_model):
                    return _invalid_path_validation(
                        "terrain_collision",
                        "Path witness intersects terrain.",
                        model_id=self.moving_model.model_id,
                        blocker_id=terrain.terrain_id,
                        metrics=metrics,
                        pivot_cost_pending=pivot_cost_pending,
                    )

        for pose in transit_poses:
            sampled_model = _model_at_pose(self.moving_model, pose)
            for enemy_model in self.enemy_models:
                metrics.engagement_check_count += 1
                if not _models_are_in_enemy_engagement_range(
                    sampled_model,
                    enemy_model,
                    horizontal_inches=self.enemy_engagement_horizontal_inches,
                    vertical_inches=self.enemy_engagement_vertical_inches,
                ):
                    continue
                if self.may_transit_enemy_engagement:
                    continue
                return _invalid_path_validation(
                    "enemy_engagement_range_transit_forbidden",
                    "Path witness enters enemy Engagement Range during transit.",
                    model_id=self.moving_model.model_id,
                    blocker_id=enemy_model.model_id,
                    metrics=metrics,
                    pivot_cost_pending=pivot_cost_pending,
                )

        final_model = _model_at_pose(self.moving_model, path[-1])
        for blocker in (*self.friendly_models, *self.enemy_models):
            metrics.model_collision_check_count += 1
            if _models_overlap_with_volume(final_model, blocker):
                return _invalid_path_validation(
                    "end_on_model_overlap",
                    "Path witness final pose overlaps another model.",
                    model_id=self.moving_model.model_id,
                    blocker_id=blocker.model_id,
                    metrics=metrics,
                    pivot_cost_pending=pivot_cost_pending,
                )

        for enemy_model in self.enemy_models:
            metrics.engagement_check_count += 1
            if not _models_are_in_enemy_engagement_range(
                final_model,
                enemy_model,
                horizontal_inches=self.enemy_engagement_horizontal_inches,
                vertical_inches=self.enemy_engagement_vertical_inches,
            ):
                continue
            if self.may_end_in_enemy_engagement:
                continue
            return _invalid_path_validation(
                "enemy_engagement_range_end_forbidden",
                "Path witness final pose is within enemy Engagement Range.",
                model_id=self.moving_model.model_id,
                blocker_id=enemy_model.model_id,
                metrics=metrics,
                pivot_cost_pending=pivot_cost_pending,
            )

        return PathValidationResult.valid(
            sampled_pose_count=metrics.sampled_pose_count,
            model_collision_check_count=metrics.model_collision_check_count,
            terrain_collision_check_count=metrics.terrain_collision_check_count,
            engagement_check_count=metrics.engagement_check_count,
            pivot_cost_inches=0.0,
            pivot_cost_pending=pivot_cost_pending,
        )

    def to_payload(self) -> PathValidationContextPayload:
        return {
            "moving_model": self.moving_model.to_payload(),
            "witness": self.witness.to_payload(),
            "battlefield_width_inches": self.battlefield_width_inches,
            "battlefield_depth_inches": self.battlefield_depth_inches,
            "friendly_models": [model.to_payload() for model in self.friendly_models],
            "enemy_models": [model.to_payload() for model in self.enemy_models],
            "terrain": [terrain.to_payload() for terrain in self.terrain],
            "friendly_vehicle_monster_model_ids": list(self.friendly_vehicle_monster_model_ids),
            "may_transit_enemy_models": self.may_transit_enemy_models,
            "may_transit_enemy_engagement": self.may_transit_enemy_engagement,
            "may_end_in_enemy_engagement": self.may_end_in_enemy_engagement,
            "enemy_engagement_horizontal_inches": self.enemy_engagement_horizontal_inches,
            "enemy_engagement_vertical_inches": self.enemy_engagement_vertical_inches,
            "sample_interval_inches": self.sample_interval_inches,
        }

    @classmethod
    def from_payload(cls, payload: PathValidationContextPayload) -> Self:
        return cls(
            moving_model=Model.from_payload(payload["moving_model"]),
            witness=PathWitness.from_payload(payload["witness"]),
            battlefield_width_inches=payload["battlefield_width_inches"],
            battlefield_depth_inches=payload["battlefield_depth_inches"],
            friendly_models=tuple(
                Model.from_payload(model) for model in payload["friendly_models"]
            ),
            enemy_models=tuple(Model.from_payload(model) for model in payload["enemy_models"]),
            terrain=tuple(terrain_volume_from_payload(terrain) for terrain in payload["terrain"]),
            friendly_vehicle_monster_model_ids=tuple(payload["friendly_vehicle_monster_model_ids"]),
            may_transit_enemy_models=payload["may_transit_enemy_models"],
            may_transit_enemy_engagement=payload["may_transit_enemy_engagement"],
            may_end_in_enemy_engagement=payload["may_end_in_enemy_engagement"],
            enemy_engagement_horizontal_inches=payload["enemy_engagement_horizontal_inches"],
            enemy_engagement_vertical_inches=payload["enemy_engagement_vertical_inches"],
            sample_interval_inches=payload["sample_interval_inches"],
        )


@dataclass(frozen=True, slots=True)
class PathWitness:
    model_paths: tuple[ModelPath, ...]

    def __post_init__(self) -> None:
        if type(self.model_paths) is not tuple:
            raise GeometryError("PathWitness model_paths must be a tuple.")
        if not self.model_paths:
            raise GeometryError("PathWitness model_paths must not be empty.")
        model_paths = tuple(_validate_model_path(path) for path in self.model_paths)
        _validate_unique_model_path_ids(model_paths)
        object.__setattr__(
            self,
            "model_paths",
            tuple(sorted(model_paths, key=lambda path: path[0])),
        )

    @classmethod
    def for_paths(cls, model_paths: tuple[ModelPath, ...]) -> Self:
        return cls(model_paths=model_paths)

    @classmethod
    def for_straight_line_endpoints(cls, endpoints: tuple[ModelPathEndpoint, ...]) -> Self:
        if type(endpoints) is not tuple:
            raise GeometryError("PathWitness straight-line endpoints must be a tuple.")
        if not endpoints:
            raise GeometryError("PathWitness straight-line endpoints must not be empty.")
        return cls(
            model_paths=tuple(
                (
                    _validate_identifier("PathWitness endpoint model_id", model_id),
                    _straight_line_pose_path(start_pose=start_pose, end_pose=end_pose),
                )
                for model_id, start_pose, end_pose in endpoints
            )
        )

    def model_ids(self) -> tuple[str, ...]:
        return tuple(model_id for model_id, _poses in self.model_paths)

    def poses_for_model(self, model_id: str) -> tuple[Pose, ...]:
        requested_model_id = _validate_identifier("model_id", model_id)
        for path_model_id, poses in self.model_paths:
            if path_model_id == requested_model_id:
                return poses
        raise GeometryError("PathWitness does not contain the requested model_id.")

    def final_pose_for_model(self, model_id: str) -> Pose:
        return self.poses_for_model(model_id)[-1]

    def to_payload(self) -> PathWitnessPayload:
        return {
            "model_paths": [
                {
                    "model_id": model_id,
                    "poses": [pose.to_payload() for pose in poses],
                }
                for model_id, poses in self.model_paths
            ]
        }

    @classmethod
    def from_payload(cls, payload: PathWitnessPayload) -> Self:
        return cls(
            model_paths=tuple(
                (
                    path["model_id"],
                    tuple(Pose.from_payload(pose) for pose in path["poses"]),
                )
                for path in payload["model_paths"]
            )
        )


@dataclass(frozen=True, slots=True)
class PathFailure:
    reason: PathFailureReason
    message: str
    model_id: str | None = None
    blocker_id: str | None = None

    def __post_init__(self) -> None:
        object.__setattr__(self, "reason", path_failure_reason_from_token(self.reason))
        object.__setattr__(
            self, "message", _validate_identifier("PathFailure message", self.message)
        )
        object.__setattr__(
            self,
            "model_id",
            _validate_optional_identifier("PathFailure model_id", self.model_id),
        )
        object.__setattr__(
            self,
            "blocker_id",
            _validate_optional_identifier("PathFailure blocker_id", self.blocker_id),
        )

    def to_payload(self) -> PathFailurePayload:
        return {
            "reason": self.reason.value,
            "message": self.message,
            "model_id": self.model_id,
            "blocker_id": self.blocker_id,
        }

    @classmethod
    def from_payload(cls, payload: PathFailurePayload) -> Self:
        return cls(
            reason=path_failure_reason_from_token(payload["reason"]),
            message=payload["message"],
            model_id=payload["model_id"],
            blocker_id=payload["blocker_id"],
        )


@dataclass(frozen=True, slots=True)
class PathMetrics:
    sampled_pose_count: int = 0
    model_collision_check_count: int = 0
    terrain_collision_check_count: int = 0
    engagement_check_count: int = 0

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "sampled_pose_count",
            _validate_non_negative_int("PathMetrics sampled_pose_count", self.sampled_pose_count),
        )
        object.__setattr__(
            self,
            "model_collision_check_count",
            _validate_non_negative_int(
                "PathMetrics model_collision_check_count",
                self.model_collision_check_count,
            ),
        )
        object.__setattr__(
            self,
            "terrain_collision_check_count",
            _validate_non_negative_int(
                "PathMetrics terrain_collision_check_count",
                self.terrain_collision_check_count,
            ),
        )
        object.__setattr__(
            self,
            "engagement_check_count",
            _validate_non_negative_int(
                "PathMetrics engagement_check_count",
                self.engagement_check_count,
            ),
        )

    def to_payload(self) -> PathMetricsPayload:
        return {
            "sampled_pose_count": self.sampled_pose_count,
            "model_collision_check_count": self.model_collision_check_count,
            "terrain_collision_check_count": self.terrain_collision_check_count,
            "engagement_check_count": self.engagement_check_count,
        }

    @classmethod
    def from_payload(cls, payload: PathMetricsPayload) -> Self:
        return cls(
            sampled_pose_count=payload["sampled_pose_count"],
            model_collision_check_count=payload["model_collision_check_count"],
            terrain_collision_check_count=payload["terrain_collision_check_count"],
            engagement_check_count=payload["engagement_check_count"],
        )


@dataclass(frozen=True, slots=True)
class PathResult:
    witness: PathWitness | None = None
    failure: PathFailure | None = None
    metrics: PathMetrics = field(default_factory=PathMetrics)

    def __post_init__(self) -> None:
        if (self.witness is None) == (self.failure is None):
            raise GeometryError("PathResult must contain exactly one witness or failure.")
        if self.witness is not None and type(self.witness) is not PathWitness:
            raise GeometryError("PathResult witness must be a PathWitness.")
        if self.failure is not None and type(self.failure) is not PathFailure:
            raise GeometryError("PathResult failure must be a PathFailure.")
        if type(self.metrics) is not PathMetrics:
            raise GeometryError("PathResult metrics must be PathMetrics.")

    @classmethod
    def valid(cls, witness: PathWitness, metrics: PathMetrics | None = None) -> Self:
        return cls(witness=witness, metrics=PathMetrics() if metrics is None else metrics)

    @classmethod
    def invalid(cls, failure: PathFailure, metrics: PathMetrics | None = None) -> Self:
        return cls(failure=failure, metrics=PathMetrics() if metrics is None else metrics)

    @property
    def is_valid(self) -> bool:
        return self.witness is not None

    def to_payload(self) -> PathResultPayload:
        return {
            "is_valid": self.is_valid,
            "witness": None if self.witness is None else self.witness.to_payload(),
            "failure": None if self.failure is None else self.failure.to_payload(),
            "metrics": self.metrics.to_payload(),
        }

    @classmethod
    def from_payload(cls, payload: PathResultPayload) -> Self:
        witness_payload = payload["witness"]
        failure_payload = payload["failure"]
        if payload["is_valid"]:
            if witness_payload is None or failure_payload is not None:
                raise GeometryError("Valid PathResult payload must include only witness.")
            return cls.valid(
                PathWitness.from_payload(witness_payload),
                metrics=PathMetrics.from_payload(payload["metrics"]),
            )
        if failure_payload is None or witness_payload is not None:
            raise GeometryError("Invalid PathResult payload must include only failure.")
        return cls.invalid(
            PathFailure.from_payload(failure_payload),
            metrics=PathMetrics.from_payload(payload["metrics"]),
        )


@dataclass(frozen=True, slots=True)
class PathQuery:
    unit_group: UnitGroup
    spatial_index: SpatialIndex
    witness: PathWitness
    movement_envelope: MovementEnvelope
    collision_set: CollisionSet

    def __post_init__(self) -> None:
        if type(self.unit_group) is not UnitGroup:
            raise GeometryError("PathQuery unit_group must be a UnitGroup.")
        if type(self.spatial_index) is not SpatialIndex:
            raise GeometryError("PathQuery spatial_index must be a SpatialIndex.")
        if type(self.witness) is not PathWitness:
            raise GeometryError("PathQuery witness must be a PathWitness.")
        if type(self.movement_envelope) is not MovementEnvelope:
            raise GeometryError("PathQuery movement_envelope must be a MovementEnvelope.")
        if type(self.collision_set) is not CollisionSet:
            raise GeometryError("PathQuery collision_set must be a CollisionSet.")

    def evaluate(self) -> PathResult:
        expected_model_ids = self.unit_group.model_ids_for_movement()
        if tuple(sorted(self.witness.model_ids())) != tuple(sorted(expected_model_ids)):
            return _invalid(
                PathFailureReason.GROUP_MISMATCH,
                "PathWitness model IDs must match the moving UnitGroup alive model IDs.",
            )

        indexed_models = {model.model_id: model for model in self.spatial_index.models}
        final_models: list[Model] = []
        metrics = _PathMetricCounts()

        for model_id in expected_model_ids:
            current_model = indexed_models.get(model_id)
            if current_model is None:
                return _invalid(
                    PathFailureReason.MISSING_MODEL,
                    "PathWitness references a model missing from the spatial index.",
                    model_id=model_id,
                    metrics=metrics.to_metrics(),
                )

            path = self.witness.poses_for_model(model_id)
            if path[0] != current_model.pose:
                return _invalid(
                    PathFailureReason.STARTING_POSE_MISMATCH,
                    "PathWitness must start at the current model pose.",
                    model_id=model_id,
                    metrics=metrics.to_metrics(),
                )
            if len(path) < 3 or not _has_non_endpoint_interior_pose(path):
                return _invalid(
                    PathFailureReason.ENDPOINT_ONLY_PATH,
                    "PathWitness must include path evidence beyond start and end poses.",
                    model_id=model_id,
                    metrics=metrics.to_metrics(),
                )
            if (
                self.movement_envelope.path_distance(path)
                > self.movement_envelope.max_distance_inches
            ):
                return _invalid(
                    PathFailureReason.MOVEMENT_DISTANCE_EXCEEDED,
                    "PathWitness exceeds the movement envelope distance.",
                    model_id=model_id,
                    metrics=metrics.to_metrics(),
                )

            sampled_path = self.movement_envelope.sampled_path(path)
            metrics.sampled_pose_count += len(sampled_path)
            for sampled_pose in sampled_path:
                sampled_model = _model_at_pose(current_model, sampled_pose)
                metrics.model_collision_check_count += len(self.collision_set.model_blockers)
                model_collisions = self.collision_set.colliding_model_ids(sampled_model)
                if model_collisions:
                    return _invalid(
                        PathFailureReason.MODEL_COLLISION,
                        "PathWitness collides with a model blocker.",
                        model_id=model_id,
                        blocker_id=model_collisions[0],
                        metrics=metrics.to_metrics(),
                    )
                metrics.terrain_collision_check_count += len(self.collision_set.terrain_blockers)
                terrain_collisions = self.collision_set.colliding_terrain_ids(sampled_model)
                if terrain_collisions:
                    return _invalid(
                        PathFailureReason.TERRAIN_COLLISION,
                        "PathWitness collides with terrain.",
                        model_id=model_id,
                        blocker_id=terrain_collisions[0],
                        metrics=metrics.to_metrics(),
                    )
                metrics.engagement_check_count += len(self.collision_set.engagement_blockers)
                engagement_blockers = self.collision_set.engagement_model_ids(
                    sampled_model,
                    horizontal_inches=self.movement_envelope.engagement_horizontal_inches,
                    vertical_inches=self.movement_envelope.engagement_vertical_inches,
                )
                if engagement_blockers:
                    return _invalid(
                        PathFailureReason.ENGAGEMENT_RANGE,
                        "PathWitness enters engagement range.",
                        model_id=model_id,
                        blocker_id=engagement_blockers[0],
                        metrics=metrics.to_metrics(),
                    )

            final_models.append(_model_at_pose(current_model, path[-1]))

        moving_overlap = _moving_models_overlap(tuple(final_models))
        if moving_overlap is not None:
            first_model_id, second_model_id = moving_overlap
            return _invalid(
                PathFailureReason.SELF_COLLISION,
                "PathWitness final poses overlap moving models.",
                model_id=first_model_id,
                blocker_id=second_model_id,
                metrics=metrics.to_metrics(),
            )

        if not self.movement_envelope.models_are_coherent(tuple(final_models)):
            return _invalid(
                PathFailureReason.COHERENCY,
                "PathWitness final poses fail model coherency.",
                metrics=metrics.to_metrics(),
            )

        return PathResult.valid(self.witness, metrics=metrics.to_metrics())

    def to_payload(self) -> PathQueryPayload:
        return {
            "unit_group": self.unit_group.to_payload(),
            "spatial_index": self.spatial_index.to_payload(),
            "witness": self.witness.to_payload(),
            "movement_envelope": self.movement_envelope.to_payload(),
            "collision_set": self.collision_set.to_payload(),
        }

    @classmethod
    def from_payload(cls, payload: PathQueryPayload) -> Self:
        return cls(
            unit_group=UnitGroup.from_payload(payload["unit_group"]),
            spatial_index=SpatialIndex.from_payload(payload["spatial_index"]),
            witness=PathWitness.from_payload(payload["witness"]),
            movement_envelope=MovementEnvelope.from_payload(payload["movement_envelope"]),
            collision_set=CollisionSet.from_payload(payload["collision_set"]),
        )


def path_failure_reason_from_token(token: object) -> PathFailureReason:
    if type(token) is PathFailureReason:
        return token
    if type(token) is not str:
        raise GeometryError("PathFailure reason token must be a string.")
    try:
        return PathFailureReason(token)
    except ValueError as exc:
        raise GeometryError(f"Unsupported PathFailure reason token: {token}.") from exc


def _validate_model_path(value: object) -> ModelPath:
    if type(value) is not tuple:
        raise GeometryError("PathWitness model_paths must contain model_id/path pairs.")
    path = cast(tuple[object, object], value)
    if len(path) != 2:
        raise GeometryError("PathWitness model_paths must contain model_id/path pairs.")
    model_id, poses = path
    return (_validate_identifier("PathWitness model_id", model_id), _validate_pose_tuple(poses))


def _validate_pose_tuple(value: object) -> tuple[Pose, ...]:
    if type(value) is not tuple:
        raise GeometryError("PathWitness poses must be a tuple.")
    pose_values = cast(tuple[object, ...], value)
    poses = tuple(validate_pose("PathWitness pose", pose) for pose in pose_values)
    if len(poses) < 2:
        raise GeometryError("PathWitness poses must contain at least two poses.")
    return poses


def _validate_unique_model_path_ids(paths: tuple[ModelPath, ...]) -> None:
    seen: set[str] = set()
    for model_id, _poses in paths:
        if model_id in seen:
            raise GeometryError("PathWitness model_paths must not contain duplicate model IDs.")
        seen.add(model_id)


def _straight_line_pose_path(*, start_pose: Pose, end_pose: Pose) -> tuple[Pose, Pose, Pose]:
    start = validate_pose("PathWitness start_pose", start_pose)
    end = validate_pose("PathWitness end_pose", end_pose)
    if start == end:
        raise GeometryError("PathWitness straight-line endpoints must not match.")
    midpoint = Pose.at(
        x=(start.position.x + end.position.x) / 2.0,
        y=(start.position.y + end.position.y) / 2.0,
        z=(start.position.z + end.position.z) / 2.0,
        facing_degrees=(start.facing.degrees + end.facing.degrees) / 2.0,
    )
    return (start, midpoint, end)


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


def _validate_non_negative_int(field_name: str, value: object) -> int:
    if type(value) is not int:
        raise GeometryError(f"{field_name} must be an integer.")
    if value < 0:
        raise GeometryError(f"{field_name} must not be negative.")
    return value


def _validate_positive_number(field_name: str, value: object) -> float:
    number = _validate_finite_number(field_name, value)
    if number <= 0.0:
        raise GeometryError(f"{field_name} must be greater than 0.")
    return number


def _validate_non_negative_number(field_name: str, value: object) -> float:
    number = _validate_finite_number(field_name, value)
    if number < 0.0:
        raise GeometryError(f"{field_name} must not be negative.")
    return number


def _validate_finite_number(field_name: str, value: object) -> float:
    if not isinstance(value, int | float) or type(value) is bool:
        raise GeometryError(f"{field_name} must be a number.")
    number = float(value)
    if not math.isfinite(number):
        raise GeometryError(f"{field_name} must be finite.")
    return number


def _validate_bool(field_name: str, value: object) -> None:
    if type(value) is not bool:
        raise GeometryError(f"{field_name} must be a bool.")


def _validate_model_tuple(field_name: str, values: object) -> tuple[Model, ...]:
    if type(values) is not tuple:
        raise GeometryError(f"{field_name} must be a tuple.")
    models = tuple(
        _validate_model(f"{field_name} model", value) for value in cast(tuple[object, ...], values)
    )
    _validate_unique_model_ids_for_path_validation(field_name, models)
    return tuple(sorted(models, key=lambda model: model.model_id))


def _validate_terrain_tuple(field_name: str, values: object) -> tuple[TerrainVolume, ...]:
    if type(values) is not tuple:
        raise GeometryError(f"{field_name} must be a tuple.")
    terrain_values = tuple(
        _validate_terrain(f"{field_name} terrain", value)
        for value in cast(tuple[object, ...], values)
    )
    seen: set[str] = set()
    for terrain in terrain_values:
        if terrain.terrain_id in seen:
            raise GeometryError(f"{field_name} must not contain duplicate terrain IDs.")
        seen.add(terrain.terrain_id)
    return tuple(sorted(terrain_values, key=lambda terrain: terrain.terrain_id))


def _validate_identifier_tuple(field_name: str, values: object) -> tuple[str, ...]:
    if type(values) is not tuple:
        raise GeometryError(f"{field_name} must be a tuple.")
    identifiers: list[str] = []
    seen: set[str] = set()
    for value in cast(tuple[object, ...], values):
        identifier = _validate_identifier(f"{field_name} value", value)
        if identifier in seen:
            raise GeometryError(f"{field_name} must not contain duplicate identifiers.")
        seen.add(identifier)
        identifiers.append(identifier)
    return tuple(sorted(identifiers))


def _validate_unique_model_ids_for_path_validation(
    field_name: str,
    models: tuple[Model, ...],
) -> None:
    seen: set[str] = set()
    for model in models:
        if model.model_id in seen:
            raise GeometryError(f"{field_name} must not contain duplicate model IDs.")
        seen.add(model.model_id)


def _validate_disjoint_model_ids(
    *,
    moving_model: Model,
    friendly_models: tuple[Model, ...],
    enemy_models: tuple[Model, ...],
) -> None:
    blocker_ids = {model.model_id for model in (*friendly_models, *enemy_models)}
    if moving_model.model_id in blocker_ids:
        raise GeometryError("PathValidationContext blockers must not include the moving model.")
    if {model.model_id for model in friendly_models} & {model.model_id for model in enemy_models}:
        raise GeometryError("PathValidationContext friendly and enemy models must be disjoint.")


def _validate_path_constraint_violations(
    values: object,
) -> tuple[PathConstraintViolation, ...]:
    if type(values) is not tuple:
        raise GeometryError("PathValidationResult violations must be a tuple.")
    return tuple(
        _validate_path_constraint_violation("PathValidationResult violation", value)
        for value in cast(tuple[object, ...], values)
    )


def _validate_path_constraint_violation(
    field_name: str,
    value: object,
) -> PathConstraintViolation:
    if type(value) is not PathConstraintViolation:
        raise GeometryError(f"{field_name} must be a PathConstraintViolation.")
    return value


def _validate_model(field_name: str, value: object) -> Model:
    if type(value) is not Model:
        raise GeometryError(f"{field_name} must be a Model.")
    return value


def _validate_terrain(field_name: str, value: object) -> TerrainVolume:
    if not isinstance(value, TerrainVolume):
        raise GeometryError(f"{field_name} must be a TerrainVolume.")
    return value


@dataclass(slots=True)
class _PathMetricCounts:
    sampled_pose_count: int = 0
    model_collision_check_count: int = 0
    terrain_collision_check_count: int = 0
    engagement_check_count: int = 0

    def to_metrics(self) -> PathMetrics:
        return PathMetrics(
            sampled_pose_count=self.sampled_pose_count,
            model_collision_check_count=self.model_collision_check_count,
            terrain_collision_check_count=self.terrain_collision_check_count,
            engagement_check_count=self.engagement_check_count,
        )


@dataclass(slots=True)
class _PathValidationMetricCounts:
    sampled_pose_count: int = 0
    model_collision_check_count: int = 0
    terrain_collision_check_count: int = 0
    engagement_check_count: int = 0


def _model_at_pose(model: Model, pose: Pose) -> Model:
    return Model(
        model_id=model.model_id,
        pose=pose,
        base=model.base,
        volume=model.volume,
    )


def _sampled_pose_path(
    poses: tuple[Pose, ...],
    *,
    sample_interval_inches: float,
) -> tuple[Pose, ...]:
    path = _validate_pose_tuple(poses)
    interval = _validate_positive_number("sample_interval_inches", sample_interval_inches)
    sampled: list[Pose] = [path[0]]
    previous = path[0]
    for pose in path[1:]:
        distance = previous.distance_3d_to(pose)
        steps = max(1, math.ceil(distance / interval))
        for step in range(1, steps + 1):
            sampled.append(_interpolate_pose(previous, pose, step / steps))
        previous = pose
    return tuple(sampled)


def _interpolate_pose(start: Pose, end: Pose, t: float) -> Pose:
    return Pose(
        position=Point3(
            x=_interpolate(start.position.x, end.position.x, t),
            y=_interpolate(start.position.y, end.position.y, t),
            z=_interpolate(start.position.z, end.position.z, t),
        ),
        facing=Facing(_interpolate(start.facing.degrees, end.facing.degrees, t)),
    )


def _interpolate(start: float, end: float, t: float) -> float:
    return start + ((end - start) * t)


def _model_is_within_battlefield(
    model: Model,
    *,
    battlefield_width_inches: float,
    battlefield_depth_inches: float,
) -> bool:
    footprint_bounds = shapely_backend.footprint_for_base(model.base, model.pose).bounds
    min_x, min_y, max_x, max_y = footprint_bounds
    return (
        min_x >= 0.0
        and min_y >= 0.0
        and max_x <= battlefield_width_inches
        and max_y <= battlefield_depth_inches
    )


def _models_overlap_with_volume(first: Model, second: Model) -> bool:
    return (
        first.base_overlaps(second)
        and first.volume.vertical_gap_to(first.pose, second.volume, second.pose) == 0.0
    )


def _models_are_in_enemy_engagement_range(
    first: Model,
    second: Model,
    *,
    horizontal_inches: float,
    vertical_inches: float,
) -> bool:
    return first.is_within_engagement_range(
        second,
        horizontal_inches=horizontal_inches,
        vertical_inches=vertical_inches,
    )


def _path_requires_pivot_cost_placeholder(model: Model, poses: tuple[Pose, ...]) -> bool:
    if type(model.base) is CircularBase:
        return False
    starting_facing = poses[0].facing
    return any(pose.facing != starting_facing for pose in poses[1:])


def _invalid_path_validation(
    violation_code: str,
    message: str,
    *,
    model_id: str | None,
    blocker_id: str | None = None,
    metrics: _PathValidationMetricCounts,
    pivot_cost_pending: bool,
) -> PathValidationResult:
    return PathValidationResult.invalid(
        PathConstraintViolation(
            violation_code=violation_code,
            message=message,
            model_id=model_id,
            blocker_id=blocker_id,
        ),
        sampled_pose_count=metrics.sampled_pose_count,
        model_collision_check_count=metrics.model_collision_check_count,
        terrain_collision_check_count=metrics.terrain_collision_check_count,
        engagement_check_count=metrics.engagement_check_count,
        pivot_cost_pending=pivot_cost_pending,
    )


def _has_non_endpoint_interior_pose(path: tuple[Pose, ...]) -> bool:
    start = path[0]
    end = path[-1]
    return any(pose != start and pose != end for pose in path[1:-1])


def _moving_models_overlap(models: tuple[Model, ...]) -> tuple[str, str] | None:
    for index, first in enumerate(models):
        for second in models[index + 1 :]:
            if (
                first.base_overlaps(second)
                and first.volume.vertical_gap_to(first.pose, second.volume, second.pose) == 0.0
            ):
                return (first.model_id, second.model_id)
    return None


def _invalid(
    reason: PathFailureReason,
    message: str,
    model_id: str | None = None,
    blocker_id: str | None = None,
    metrics: PathMetrics | None = None,
) -> PathResult:
    return PathResult.invalid(
        PathFailure(
            reason=reason,
            message=message,
            model_id=model_id,
            blocker_id=blocker_id,
        ),
        metrics=metrics,
    )
