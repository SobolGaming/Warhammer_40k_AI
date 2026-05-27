from __future__ import annotations

from dataclasses import dataclass, field
from enum import StrEnum
from typing import Self, TypedDict, cast

from warhammer40k_core.core.unit_group import UnitGroup, UnitGroupPayload
from warhammer40k_core.geometry.collision import CollisionSet, CollisionSetPayload
from warhammer40k_core.geometry.movement_envelope import (
    MovementEnvelope,
    MovementEnvelopePayload,
)
from warhammer40k_core.geometry.pose import GeometryError, Pose, PosePayload, validate_pose
from warhammer40k_core.geometry.spatial_index import SpatialIndex, SpatialIndexPayload
from warhammer40k_core.geometry.volume import Model

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


def _model_at_pose(model: Model, pose: Pose) -> Model:
    return Model(
        model_id=model.model_id,
        pose=pose,
        base=model.base,
        volume=model.volume,
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
