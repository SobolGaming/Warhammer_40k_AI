from __future__ import annotations

import math
from dataclasses import dataclass, field
from enum import StrEnum
from itertools import pairwise
from typing import Self, TypedDict, cast

from warhammer40k_core.core.ruleset_descriptor import (
    TerrainEndpointSupportPolicy,
    TerrainFeatureMovementPolicy,
    TerrainMovementPolicy,
    TerrainMovementPolicyPayload,
    TerrainTraversalMode,
    terrain_traversal_mode_from_token,
)
from warhammer40k_core.core.unit_group import UnitGroup, UnitGroupPayload
from warhammer40k_core.geometry import shapely_backend
from warhammer40k_core.geometry.collision import CollisionSet, CollisionSetPayload
from warhammer40k_core.geometry.movement_envelope import (
    MovementDistanceWitness,
    MovementDistanceWitnessPayload,
    MovementEnvelope,
    MovementEnvelopePayload,
    PivotCostPolicy,
    PivotCostPolicyPayload,
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
    ObstacleVolume,
    TerrainFeatureDefinition,
    TerrainFeatureDefinitionPayload,
    TerrainSupportSurface,
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


class TerrainEndpointViolationCode(StrEnum):
    END_ON_FORBIDDEN_TERRAIN = "end_on_forbidden_terrain"
    UPPER_FLOOR_KEYWORD_FORBIDDEN = "upper_floor_keyword_forbidden"
    BASE_OVERHANGS_SUPPORT_SURFACE = "base_overhangs_support_surface"
    MODEL_CANNOT_BE_PLACED_AT_ENDPOINT = "model_cannot_be_placed_at_endpoint"
    ENDS_MID_CLIMB = "ends_mid_climb"
    MANUAL_GEOMETRY_REQUIRED = "manual_geometry_required"


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
    movement_distance_witness: MovementDistanceWitnessPayload | None


class PathValidationContextPayload(TypedDict):
    moving_model: ModelPayload
    witness: PathWitnessPayload
    battlefield_width_inches: float
    battlefield_depth_inches: float
    friendly_models: list[ModelPayload]
    enemy_models: list[ModelPayload]
    terrain: list[TerrainVolumePayload]
    friendly_vehicle_monster_model_ids: list[str]
    aircraft_model_ids: list[str]
    may_transit_enemy_models: bool
    may_transit_enemy_engagement: bool
    may_end_in_enemy_engagement: bool
    enemy_engagement_horizontal_inches: float
    enemy_engagement_vertical_inches: float
    sample_interval_inches: float
    movement_distance_budget_inches: float | None
    pivot_cost_policy: PivotCostPolicyPayload


class TerrainPathSegmentPayload(TypedDict):
    terrain_id: str
    traversal_mode: str
    start_pose: PosePayload
    end_pose: PosePayload
    horizontal_distance_inches: float
    vertical_distance_inches: float
    counted_distance_inches: float
    air_path_measurement_pending: bool


class TerrainTraversalViolationPayload(TypedDict):
    violation_code: str
    message: str
    terrain_id: str | None
    surface_id: str | None


class TerrainPathLegalityResultPayload(TypedDict):
    is_valid: bool
    violations: list[TerrainTraversalViolationPayload]
    segments: list[TerrainPathSegmentPayload]
    sampled_pose_count: int


class TerrainPathLegalityContextPayload(TypedDict):
    moving_model: ModelPayload
    witness: PathWitnessPayload
    terrain: list[TerrainVolumePayload]
    terrain_features: list[TerrainFeatureDefinitionPayload]
    terrain_movement_policy: TerrainMovementPolicyPayload
    movement_keywords: list[str]
    contact_footprint_available: bool
    can_traverse_ruins_walls: bool
    can_move_through_terrain: bool
    has_fly: bool
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
    movement_distance_witness: MovementDistanceWitness | None = None

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
        if (
            self.movement_distance_witness is not None
            and type(self.movement_distance_witness) is not MovementDistanceWitness
        ):
            raise GeometryError(
                "PathValidationResult movement_distance_witness must be a MovementDistanceWitness."
            )

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
        movement_distance_witness: MovementDistanceWitness | None = None,
    ) -> Self:
        return cls(
            sampled_pose_count=sampled_pose_count,
            model_collision_check_count=model_collision_check_count,
            terrain_collision_check_count=terrain_collision_check_count,
            engagement_check_count=engagement_check_count,
            pivot_cost_inches=pivot_cost_inches,
            pivot_cost_pending=pivot_cost_pending,
            movement_distance_witness=movement_distance_witness,
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
        movement_distance_witness: MovementDistanceWitness | None = None,
    ) -> Self:
        return cls(
            violations=(violation,),
            sampled_pose_count=sampled_pose_count,
            model_collision_check_count=model_collision_check_count,
            terrain_collision_check_count=terrain_collision_check_count,
            engagement_check_count=engagement_check_count,
            pivot_cost_inches=pivot_cost_inches,
            pivot_cost_pending=pivot_cost_pending,
            movement_distance_witness=movement_distance_witness,
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
            "movement_distance_witness": (
                None
                if self.movement_distance_witness is None
                else self.movement_distance_witness.to_payload()
            ),
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
            movement_distance_witness=(
                None
                if payload["movement_distance_witness"] is None
                else MovementDistanceWitness.from_payload(payload["movement_distance_witness"])
            ),
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
    aircraft_model_ids: tuple[str, ...] = ()
    may_transit_enemy_models: bool = False
    may_transit_enemy_engagement: bool = False
    may_end_in_enemy_engagement: bool = False
    enemy_engagement_horizontal_inches: float = 1.0
    enemy_engagement_vertical_inches: float = 5.0
    sample_interval_inches: float = 0.5
    movement_distance_budget_inches: float | None = None
    pivot_cost_policy: PivotCostPolicy = field(default_factory=PivotCostPolicy)

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
        aircraft_model_ids = _validate_identifier_tuple(
            "PathValidationContext aircraft_model_ids",
            self.aircraft_model_ids,
        )
        blocker_model_ids = {model.model_id for model in (*friendly_models, *enemy_models)}
        if any(model_id not in blocker_model_ids for model_id in aircraft_model_ids):
            raise GeometryError(
                "PathValidationContext aircraft_model_ids must reference blocker models."
            )
        object.__setattr__(self, "aircraft_model_ids", aircraft_model_ids)
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
        object.__setattr__(
            self,
            "movement_distance_budget_inches",
            _validate_optional_non_negative_number(
                "PathValidationContext movement_distance_budget_inches",
                self.movement_distance_budget_inches,
            ),
        )
        if type(self.pivot_cost_policy) is not PivotCostPolicy:
            raise GeometryError(
                "PathValidationContext pivot_cost_policy must be a PivotCostPolicy."
            )

    def validate(self) -> PathValidationResult:
        path = self.witness.poses_for_model(self.moving_model.model_id)
        movement_distance_witness = MovementDistanceWitness.for_model_path(
            model=self.moving_model,
            poses=path,
            pivot_cost_policy=self.pivot_cost_policy,
            max_distance_inches=self.movement_distance_budget_inches,
        )
        if path[0] != self.moving_model.pose:
            return _invalid_path_validation(
                "starting_pose_mismatch",
                "Path witness must start at the moving model pose.",
                model_id=self.moving_model.model_id,
                metrics=_PathValidationMetricCounts(sampled_pose_count=len(path)),
                movement_distance_witness=movement_distance_witness,
            )

        if not movement_distance_witness.is_within_budget:
            return _invalid_path_validation(
                "movement_distance_exceeded",
                "Path witness exceeds the movement distance budget.",
                model_id=self.moving_model.model_id,
                metrics=_PathValidationMetricCounts(sampled_pose_count=len(path)),
                movement_distance_witness=movement_distance_witness,
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
                    movement_distance_witness=movement_distance_witness,
                )

        for pose in transit_poses:
            sampled_model = _model_at_pose(self.moving_model, pose)
            for enemy_model in self.enemy_models:
                metrics.model_collision_check_count += 1
                if enemy_model.model_id in self.aircraft_model_ids:
                    continue
                if _models_overlap_with_volume(sampled_model, enemy_model):
                    if self.may_transit_enemy_models:
                        continue
                    return _invalid_path_validation(
                        "enemy_model_base_crossed",
                        "Path witness crosses an enemy model base.",
                        model_id=self.moving_model.model_id,
                        blocker_id=enemy_model.model_id,
                        metrics=metrics,
                        movement_distance_witness=movement_distance_witness,
                    )
            for friendly_model in self.friendly_models:
                metrics.model_collision_check_count += 1
                if friendly_model.model_id in self.aircraft_model_ids:
                    continue
                if friendly_model.model_id not in self.friendly_vehicle_monster_model_ids:
                    continue
                if _models_overlap_with_volume(sampled_model, friendly_model):
                    return _invalid_path_validation(
                        "friendly_vehicle_monster_transit_forbidden",
                        "Path witness crosses a friendly VEHICLE/MONSTER blocker.",
                        model_id=self.moving_model.model_id,
                        blocker_id=friendly_model.model_id,
                        metrics=metrics,
                        movement_distance_witness=movement_distance_witness,
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
                        movement_distance_witness=movement_distance_witness,
                    )

        for pose in transit_poses:
            sampled_model = _model_at_pose(self.moving_model, pose)
            for enemy_model in self.enemy_models:
                metrics.engagement_check_count += 1
                if enemy_model.model_id in self.aircraft_model_ids:
                    continue
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
                    movement_distance_witness=movement_distance_witness,
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
                    movement_distance_witness=movement_distance_witness,
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
                movement_distance_witness=movement_distance_witness,
            )

        return PathValidationResult.valid(
            sampled_pose_count=metrics.sampled_pose_count,
            model_collision_check_count=metrics.model_collision_check_count,
            terrain_collision_check_count=metrics.terrain_collision_check_count,
            engagement_check_count=metrics.engagement_check_count,
            pivot_cost_inches=movement_distance_witness.pivot_cost_inches,
            pivot_cost_pending=False,
            movement_distance_witness=movement_distance_witness,
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
            "aircraft_model_ids": list(self.aircraft_model_ids),
            "may_transit_enemy_models": self.may_transit_enemy_models,
            "may_transit_enemy_engagement": self.may_transit_enemy_engagement,
            "may_end_in_enemy_engagement": self.may_end_in_enemy_engagement,
            "enemy_engagement_horizontal_inches": self.enemy_engagement_horizontal_inches,
            "enemy_engagement_vertical_inches": self.enemy_engagement_vertical_inches,
            "sample_interval_inches": self.sample_interval_inches,
            "movement_distance_budget_inches": self.movement_distance_budget_inches,
            "pivot_cost_policy": self.pivot_cost_policy.to_payload(),
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
            aircraft_model_ids=tuple(payload["aircraft_model_ids"]),
            may_transit_enemy_models=payload["may_transit_enemy_models"],
            may_transit_enemy_engagement=payload["may_transit_enemy_engagement"],
            may_end_in_enemy_engagement=payload["may_end_in_enemy_engagement"],
            enemy_engagement_horizontal_inches=payload["enemy_engagement_horizontal_inches"],
            enemy_engagement_vertical_inches=payload["enemy_engagement_vertical_inches"],
            sample_interval_inches=payload["sample_interval_inches"],
            movement_distance_budget_inches=payload["movement_distance_budget_inches"],
            pivot_cost_policy=PivotCostPolicy.from_payload(payload["pivot_cost_policy"]),
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
class TerrainPathSegment:
    terrain_id: str
    traversal_mode: TerrainTraversalMode
    start_pose: Pose
    end_pose: Pose
    horizontal_distance_inches: float
    vertical_distance_inches: float
    counted_distance_inches: float
    air_path_measurement_pending: bool = False

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "terrain_id",
            _validate_identifier("TerrainPathSegment terrain_id", self.terrain_id),
        )
        object.__setattr__(
            self,
            "traversal_mode",
            terrain_traversal_mode_from_token(self.traversal_mode),
        )
        validate_pose("TerrainPathSegment start_pose", self.start_pose)
        validate_pose("TerrainPathSegment end_pose", self.end_pose)
        object.__setattr__(
            self,
            "horizontal_distance_inches",
            _validate_non_negative_number(
                "TerrainPathSegment horizontal_distance_inches",
                self.horizontal_distance_inches,
            ),
        )
        object.__setattr__(
            self,
            "vertical_distance_inches",
            _validate_non_negative_number(
                "TerrainPathSegment vertical_distance_inches",
                self.vertical_distance_inches,
            ),
        )
        object.__setattr__(
            self,
            "counted_distance_inches",
            _validate_non_negative_number(
                "TerrainPathSegment counted_distance_inches",
                self.counted_distance_inches,
            ),
        )
        _validate_bool(
            "TerrainPathSegment air_path_measurement_pending",
            self.air_path_measurement_pending,
        )
        if (
            self.air_path_measurement_pending
            and self.traversal_mode is not TerrainTraversalMode.AIR_PATH
        ):
            raise GeometryError("TerrainPathSegment air-path hook requires AIR_PATH mode.")

    def to_payload(self) -> TerrainPathSegmentPayload:
        return {
            "terrain_id": self.terrain_id,
            "traversal_mode": self.traversal_mode.value,
            "start_pose": self.start_pose.to_payload(),
            "end_pose": self.end_pose.to_payload(),
            "horizontal_distance_inches": self.horizontal_distance_inches,
            "vertical_distance_inches": self.vertical_distance_inches,
            "counted_distance_inches": self.counted_distance_inches,
            "air_path_measurement_pending": self.air_path_measurement_pending,
        }

    @classmethod
    def from_payload(cls, payload: TerrainPathSegmentPayload) -> Self:
        return cls(
            terrain_id=payload["terrain_id"],
            traversal_mode=terrain_traversal_mode_from_token(payload["traversal_mode"]),
            start_pose=Pose.from_payload(payload["start_pose"]),
            end_pose=Pose.from_payload(payload["end_pose"]),
            horizontal_distance_inches=payload["horizontal_distance_inches"],
            vertical_distance_inches=payload["vertical_distance_inches"],
            counted_distance_inches=payload["counted_distance_inches"],
            air_path_measurement_pending=payload["air_path_measurement_pending"],
        )


@dataclass(frozen=True, slots=True)
class TerrainTraversalViolation:
    violation_code: str
    message: str
    terrain_id: str | None = None
    surface_id: str | None = None

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "violation_code",
            _validate_identifier("TerrainTraversalViolation violation_code", self.violation_code),
        )
        object.__setattr__(
            self,
            "message",
            _validate_identifier("TerrainTraversalViolation message", self.message),
        )
        object.__setattr__(
            self,
            "terrain_id",
            _validate_optional_identifier("TerrainTraversalViolation terrain_id", self.terrain_id),
        )
        object.__setattr__(
            self,
            "surface_id",
            _validate_optional_identifier("TerrainTraversalViolation surface_id", self.surface_id),
        )

    def to_payload(self) -> TerrainTraversalViolationPayload:
        return {
            "violation_code": self.violation_code,
            "message": self.message,
            "terrain_id": self.terrain_id,
            "surface_id": self.surface_id,
        }

    @classmethod
    def from_payload(cls, payload: TerrainTraversalViolationPayload) -> Self:
        return cls(
            violation_code=payload["violation_code"],
            message=payload["message"],
            terrain_id=payload["terrain_id"],
            surface_id=payload["surface_id"],
        )


@dataclass(frozen=True, slots=True)
class TerrainPathLegalityResult:
    violations: tuple[TerrainTraversalViolation, ...] = ()
    segments: tuple[TerrainPathSegment, ...] = ()
    sampled_pose_count: int = 0

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "violations",
            _validate_terrain_traversal_violation_tuple(self.violations),
        )
        object.__setattr__(
            self,
            "segments",
            _validate_terrain_path_segment_tuple(self.segments),
        )
        object.__setattr__(
            self,
            "sampled_pose_count",
            _validate_non_negative_int(
                "TerrainPathLegalityResult sampled_pose_count",
                self.sampled_pose_count,
            ),
        )

    @classmethod
    def valid(
        cls,
        *,
        segments: tuple[TerrainPathSegment, ...],
        sampled_pose_count: int,
    ) -> Self:
        return cls(segments=segments, sampled_pose_count=sampled_pose_count)

    @classmethod
    def invalid(
        cls,
        violation: TerrainTraversalViolation,
        *,
        segments: tuple[TerrainPathSegment, ...],
        sampled_pose_count: int,
    ) -> Self:
        return cls(
            violations=(violation,),
            segments=segments,
            sampled_pose_count=sampled_pose_count,
        )

    @property
    def is_valid(self) -> bool:
        return not self.violations

    def to_payload(self) -> TerrainPathLegalityResultPayload:
        return {
            "is_valid": self.is_valid,
            "violations": [violation.to_payload() for violation in self.violations],
            "segments": [segment.to_payload() for segment in self.segments],
            "sampled_pose_count": self.sampled_pose_count,
        }

    @classmethod
    def from_payload(cls, payload: TerrainPathLegalityResultPayload) -> Self:
        result = cls(
            violations=tuple(
                TerrainTraversalViolation.from_payload(violation)
                for violation in payload["violations"]
            ),
            segments=tuple(
                TerrainPathSegment.from_payload(segment) for segment in payload["segments"]
            ),
            sampled_pose_count=payload["sampled_pose_count"],
        )
        if result.is_valid != payload["is_valid"]:
            raise GeometryError(
                "TerrainPathLegalityResult payload validity does not match violations."
            )
        return result


@dataclass(frozen=True, slots=True)
class TerrainPathLegalityContext:
    moving_model: Model
    witness: PathWitness
    terrain: tuple[TerrainVolume, ...]
    terrain_movement_policy: TerrainMovementPolicy
    terrain_features: tuple[TerrainFeatureDefinition, ...] = ()
    movement_keywords: tuple[str, ...] = ()
    contact_footprint_available: bool = True
    can_traverse_ruins_walls: bool = False
    can_move_through_terrain: bool = False
    has_fly: bool = False
    sample_interval_inches: float = 0.5

    def __post_init__(self) -> None:
        if type(self.moving_model) is not Model:
            raise GeometryError("TerrainPathLegalityContext moving_model must be a Model.")
        if type(self.witness) is not PathWitness:
            raise GeometryError("TerrainPathLegalityContext witness must be a PathWitness.")
        if self.witness.model_ids() != (self.moving_model.model_id,):
            raise GeometryError(
                "TerrainPathLegalityContext witness must contain only the moving model."
            )
        object.__setattr__(
            self,
            "terrain",
            _validate_terrain_tuple("TerrainPathLegalityContext terrain", self.terrain),
        )
        if type(self.terrain_movement_policy) is not TerrainMovementPolicy:
            raise GeometryError(
                "TerrainPathLegalityContext terrain_movement_policy must be "
                "a TerrainMovementPolicy."
            )
        object.__setattr__(
            self,
            "terrain_features",
            _validate_terrain_feature_tuple(
                "TerrainPathLegalityContext terrain_features",
                self.terrain_features,
            ),
        )
        object.__setattr__(
            self,
            "movement_keywords",
            _validate_keyword_tuple(
                "TerrainPathLegalityContext movement_keywords",
                self.movement_keywords,
            ),
        )
        _validate_bool(
            "TerrainPathLegalityContext contact_footprint_available",
            self.contact_footprint_available,
        )
        _validate_bool(
            "TerrainPathLegalityContext can_traverse_ruins_walls",
            self.can_traverse_ruins_walls,
        )
        _validate_bool(
            "TerrainPathLegalityContext can_move_through_terrain",
            self.can_move_through_terrain,
        )
        _validate_bool("TerrainPathLegalityContext has_fly", self.has_fly)
        object.__setattr__(
            self,
            "sample_interval_inches",
            _validate_positive_number(
                "TerrainPathLegalityContext sample_interval_inches",
                self.sample_interval_inches,
            ),
        )

    def validate(self) -> TerrainPathLegalityResult:
        path = self.witness.poses_for_model(self.moving_model.model_id)
        sampled_path = _sampled_pose_path(path, sample_interval_inches=self.sample_interval_inches)
        if path[0] != self.moving_model.pose:
            return TerrainPathLegalityResult.invalid(
                TerrainTraversalViolation(
                    violation_code="starting_pose_mismatch",
                    message="Terrain path witness must start at the moving model pose.",
                ),
                segments=(),
                sampled_pose_count=len(sampled_path),
            )
        if len(path) < 3 or not _has_non_endpoint_interior_pose(path):
            return TerrainPathLegalityResult.invalid(
                TerrainTraversalViolation(
                    violation_code="endpoint_only_path",
                    message="Terrain path witness must include non-endpoint path evidence.",
                ),
                segments=(),
                sampled_pose_count=len(sampled_path),
            )

        segments: list[TerrainPathSegment] = []
        for terrain in self.terrain:
            violation = self._append_terrain_volume_segment(
                terrain=terrain,
                feature=None,
                feature_policy=None,
                path=path,
                sampled_path=sampled_path,
                segments=segments,
            )
            if violation is not None:
                return TerrainPathLegalityResult.invalid(
                    violation,
                    segments=tuple(segments),
                    sampled_pose_count=len(sampled_path),
                )

        for feature in self.terrain_features:
            feature_policy = self.terrain_movement_policy.policy_for_feature_kind(
                feature.feature_kind
            )
            for terrain in feature.terrain_volumes():
                violation = self._append_terrain_volume_segment(
                    terrain=terrain,
                    feature=feature,
                    feature_policy=feature_policy,
                    path=path,
                    sampled_path=sampled_path,
                    segments=segments,
                )
                if violation is not None:
                    return TerrainPathLegalityResult.invalid(
                        violation,
                        segments=tuple(segments),
                        sampled_pose_count=len(sampled_path),
                    )
            endpoint_violation = self._endpoint_violation_for_feature(
                feature=feature,
                feature_policy=feature_policy,
                end_pose=path[-1],
            )
            if endpoint_violation is not None:
                return TerrainPathLegalityResult.invalid(
                    endpoint_violation,
                    segments=tuple(segments),
                    sampled_pose_count=len(sampled_path),
                )

        return TerrainPathLegalityResult.valid(
            segments=tuple(segments),
            sampled_pose_count=len(sampled_path),
        )

    def _append_terrain_volume_segment(
        self,
        *,
        terrain: TerrainVolume,
        feature: TerrainFeatureDefinition | None,
        feature_policy: TerrainFeatureMovementPolicy | None,
        path: tuple[Pose, ...],
        sampled_path: tuple[Pose, ...],
        segments: list[TerrainPathSegment],
    ) -> TerrainTraversalViolation | None:
        touching_poses = tuple(
            pose
            for pose in sampled_path
            if _model_horizontally_intersects_terrain(
                _model_at_pose(self.moving_model, pose),
                terrain,
            )
        )
        if not touching_poses:
            return None
        traversal_mode = self._traversal_mode_for_terrain(
            terrain,
            touching_poses,
            feature_policy=feature_policy,
        )
        if traversal_mode is not TerrainTraversalMode.BLOCKED:
            endpoint_intersection_violation = self._endpoint_intersection_violation_for_terrain(
                terrain=terrain,
                feature=feature,
                end_pose=path[-1],
            )
            if endpoint_intersection_violation is not None:
                return endpoint_intersection_violation
        if not self.terrain_movement_policy.may_end_mid_climb and _pose_is_mid_climb(
            path[-1], terrain, self.moving_model
        ):
            return TerrainTraversalViolation(
                violation_code=TerrainEndpointViolationCode.ENDS_MID_CLIMB.value,
                message="Terrain path cannot end mid-climb.",
                terrain_id=terrain.terrain_id,
            )
        if traversal_mode is TerrainTraversalMode.BLOCKED:
            return TerrainTraversalViolation(
                violation_code="terrain_feature_transit_forbidden",
                message="Terrain path crosses terrain without traversal permission.",
                terrain_id=terrain.terrain_id,
            )

        segments.append(
            _terrain_path_segment(
                terrain_id=terrain.terrain_id,
                traversal_mode=traversal_mode,
                path=path,
                touching_poses=touching_poses,
                policy=self.terrain_movement_policy,
            )
        )
        return None

    def _endpoint_intersection_violation_for_terrain(
        self,
        *,
        terrain: TerrainVolume,
        feature: TerrainFeatureDefinition | None,
        end_pose: Pose,
    ) -> TerrainTraversalViolation | None:
        if feature is None:
            return None
        end_model = _model_at_pose(self.moving_model, end_pose)
        if not terrain.intersects_model(end_model):
            return None
        if _endpoint_is_supported_by_feature_surface(
            feature=feature,
            terrain=terrain,
            end_model=end_model,
        ):
            return None
        return TerrainTraversalViolation(
            violation_code=TerrainEndpointViolationCode.MODEL_CANNOT_BE_PLACED_AT_ENDPOINT.value,
            message="Model cannot end within a terrain wall, floor, or other terrain volume.",
            terrain_id=terrain.terrain_id,
        )

    def _traversal_mode_for_terrain(
        self,
        terrain: TerrainVolume,
        touching_poses: tuple[Pose, ...],
        *,
        feature_policy: TerrainFeatureMovementPolicy | None,
    ) -> TerrainTraversalMode:
        if (
            self.has_fly
            and self.terrain_movement_policy.fly_uses_air_path_measurement
            and _path_reaches_or_clears_terrain_top(touching_poses, terrain)
        ):
            return self.terrain_movement_policy.fly_traversal_mode
        free_height = self.terrain_movement_policy.freely_traversable_height_threshold_inches
        if (
            feature_policy is not None
            and feature_policy.freely_moved_over_height_inches is not None
        ):
            free_height = feature_policy.freely_moved_over_height_inches
        if terrain.height <= free_height:
            return TerrainTraversalMode.FREELY_TRAVERSABLE
        if type(terrain) is ObstacleVolume:
            if self._can_move_through_feature(feature_policy):
                return self.terrain_movement_policy.infantry_beast_ruins_wall_traversal_mode
            if (
                feature_policy is None or feature_policy.can_move_over
            ) and _path_reaches_or_clears_terrain_top(touching_poses, terrain):
                return TerrainTraversalMode.CLIMB
            return TerrainTraversalMode.BLOCKED
        if (
            feature_policy is None or feature_policy.can_move_over
        ) and _path_reaches_or_clears_terrain_top(touching_poses, terrain):
            return TerrainTraversalMode.CLIMB
        return TerrainTraversalMode.BLOCKED

    def _can_move_through_feature(
        self,
        feature_policy: TerrainFeatureMovementPolicy | None,
    ) -> bool:
        if feature_policy is None:
            return self.can_move_through_terrain or self.can_traverse_ruins_walls
        if feature_policy.can_move_through:
            return True
        if not self.terrain_movement_policy.requires_permission_to_move_through_features:
            return True
        return bool(
            set(self.movement_keywords) & set(feature_policy.through_terrain_allowed_keywords)
        )

    def _endpoint_violation_for_feature(
        self,
        *,
        feature: TerrainFeatureDefinition,
        feature_policy: TerrainFeatureMovementPolicy,
        end_pose: Pose,
    ) -> TerrainTraversalViolation | None:
        end_model = _model_at_pose(self.moving_model, end_pose)
        surfaces = feature.support_surfaces(
            no_overhang_required=feature_policy.no_overhang_required
        )
        touched_surfaces = tuple(
            surface
            for surface in surfaces
            if _model_endpoint_is_on_support_surface(end_model, surface)
        )
        if not touched_surfaces:
            if (
                end_pose.position.z > 0.0
                and feature_policy.no_overhang_required
                and _model_endpoint_intersects_feature_footprint(end_model, feature)
            ):
                return TerrainTraversalViolation(
                    violation_code=(
                        TerrainEndpointViolationCode.MODEL_CANNOT_BE_PLACED_AT_ENDPOINT.value
                    ),
                    message="Model endpoint has no valid support surface.",
                    terrain_id=feature.feature_id,
                )
            return None

        for surface in touched_surfaces:
            is_elevated_surface = surface.z_inches > 0.0
            if (
                feature_policy.endpoint_support_policy
                is TerrainEndpointSupportPolicy.NOT_ALLOWED_ON_TOP
            ):
                return TerrainTraversalViolation(
                    violation_code=TerrainEndpointViolationCode.END_ON_FORBIDDEN_TERRAIN.value,
                    message="Model cannot end on top of this terrain feature.",
                    terrain_id=feature.feature_id,
                    surface_id=surface.surface_id,
                )
            if (
                feature_policy.endpoint_support_policy
                is TerrainEndpointSupportPolicy.ALLOWED_ON_GROUND_FLOOR_ONLY
                and is_elevated_surface
            ):
                return TerrainTraversalViolation(
                    violation_code=(
                        TerrainEndpointViolationCode.MODEL_CANNOT_BE_PLACED_AT_ENDPOINT.value
                    ),
                    message="Model cannot end on an elevated surface for this terrain feature.",
                    terrain_id=feature.feature_id,
                    surface_id=surface.surface_id,
                )
            if (
                is_elevated_surface
                and feature_policy.ground_floor_only_unless_keyword
                and not (
                    set(self.movement_keywords) & set(feature_policy.upper_floor_allowed_keywords)
                )
            ):
                return TerrainTraversalViolation(
                    violation_code=TerrainEndpointViolationCode.UPPER_FLOOR_KEYWORD_FORBIDDEN.value,
                    message="Model lacks a keyword required to end on this upper floor.",
                    terrain_id=feature.feature_id,
                    surface_id=surface.surface_id,
                )
            support_containment_required = surface.no_overhang_required and (
                is_elevated_surface
                or feature_policy.endpoint_support_policy
                is TerrainEndpointSupportPolicy.ALLOWED_ON_TOP_WITH_NO_OVERHANG
            )
            if support_containment_required and not self.contact_footprint_available:
                return TerrainTraversalViolation(
                    violation_code=TerrainEndpointViolationCode.MANUAL_GEOMETRY_REQUIRED.value,
                    message=(
                        "No-overhang endpoint validation requires explicit contact-footprint "
                        "geometry."
                    ),
                    terrain_id=feature.feature_id,
                    surface_id=surface.surface_id,
                )
            if support_containment_required and not _model_base_is_fully_supported(
                end_model,
                surface,
            ):
                return TerrainTraversalViolation(
                    violation_code=(
                        TerrainEndpointViolationCode.BASE_OVERHANGS_SUPPORT_SURFACE.value
                    ),
                    message="Model base must not overhang the support surface.",
                    terrain_id=feature.feature_id,
                    surface_id=surface.surface_id,
                )
        return None

    def to_payload(self) -> TerrainPathLegalityContextPayload:
        return {
            "moving_model": self.moving_model.to_payload(),
            "witness": self.witness.to_payload(),
            "terrain": [terrain.to_payload() for terrain in self.terrain],
            "terrain_features": [feature.to_payload() for feature in self.terrain_features],
            "terrain_movement_policy": self.terrain_movement_policy.to_payload(),
            "movement_keywords": list(self.movement_keywords),
            "contact_footprint_available": self.contact_footprint_available,
            "can_traverse_ruins_walls": self.can_traverse_ruins_walls,
            "can_move_through_terrain": self.can_move_through_terrain,
            "has_fly": self.has_fly,
            "sample_interval_inches": self.sample_interval_inches,
        }

    @classmethod
    def from_payload(cls, payload: TerrainPathLegalityContextPayload) -> Self:
        return cls(
            moving_model=Model.from_payload(payload["moving_model"]),
            witness=PathWitness.from_payload(payload["witness"]),
            terrain=tuple(terrain_volume_from_payload(terrain) for terrain in payload["terrain"]),
            terrain_movement_policy=TerrainMovementPolicy.from_payload(
                payload["terrain_movement_policy"]
            ),
            terrain_features=tuple(
                TerrainFeatureDefinition.from_payload(feature)
                for feature in payload["terrain_features"]
            ),
            movement_keywords=tuple(payload["movement_keywords"]),
            contact_footprint_available=payload["contact_footprint_available"],
            can_traverse_ruins_walls=payload["can_traverse_ruins_walls"],
            can_move_through_terrain=payload["can_move_through_terrain"],
            has_fly=payload["has_fly"],
            sample_interval_inches=payload["sample_interval_inches"],
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
            movement_distance_witness = self.movement_envelope.movement_distance_witness(
                model=current_model,
                poses=path,
            )
            if not movement_distance_witness.is_within_budget:
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


def _validate_optional_non_negative_number(
    field_name: str,
    value: object | None,
) -> float | None:
    if value is None:
        return None
    return _validate_non_negative_number(field_name, value)


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


def _validate_terrain_feature_tuple(
    field_name: str,
    values: object,
) -> tuple[TerrainFeatureDefinition, ...]:
    if type(values) is not tuple:
        raise GeometryError(f"{field_name} must be a tuple.")
    features = tuple(
        _validate_terrain_feature(f"{field_name} feature", value)
        for value in cast(tuple[object, ...], values)
    )
    seen: set[str] = set()
    for feature in features:
        if feature.feature_id in seen:
            raise GeometryError(f"{field_name} must not contain duplicate feature IDs.")
        seen.add(feature.feature_id)
    return tuple(sorted(features, key=lambda feature: feature.feature_id))


def _validate_terrain_feature(field_name: str, value: object) -> TerrainFeatureDefinition:
    if type(value) is not TerrainFeatureDefinition:
        raise GeometryError(f"{field_name} must be a TerrainFeatureDefinition.")
    return value


def _validate_keyword_tuple(field_name: str, values: object) -> tuple[str, ...]:
    if type(values) is not tuple:
        raise GeometryError(f"{field_name} must be a tuple.")
    keywords: list[str] = []
    seen: set[str] = set()
    for value in cast(tuple[object, ...], values):
        keyword = _validate_identifier(f"{field_name} keyword", value)
        keyword = keyword.upper().replace(" ", "_").replace("-", "_")
        if keyword in seen:
            raise GeometryError(f"{field_name} must not contain duplicate keywords.")
        seen.add(keyword)
        keywords.append(keyword)
    return tuple(sorted(keywords))


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


def _validate_terrain_traversal_violation_tuple(
    values: object,
) -> tuple[TerrainTraversalViolation, ...]:
    if type(values) is not tuple:
        raise GeometryError("TerrainPathLegalityResult violations must be a tuple.")
    return tuple(
        _validate_terrain_traversal_violation("TerrainPathLegalityResult violation", value)
        for value in cast(tuple[object, ...], values)
    )


def _validate_terrain_traversal_violation(
    field_name: str,
    value: object,
) -> TerrainTraversalViolation:
    if type(value) is not TerrainTraversalViolation:
        raise GeometryError(f"{field_name} must be a TerrainTraversalViolation.")
    return value


def _validate_terrain_path_segment_tuple(
    values: object,
) -> tuple[TerrainPathSegment, ...]:
    if type(values) is not tuple:
        raise GeometryError("TerrainPathLegalityResult segments must be a tuple.")
    segments = tuple(
        _validate_terrain_path_segment("TerrainPathLegalityResult segment", value)
        for value in cast(tuple[object, ...], values)
    )
    return tuple(sorted(segments, key=lambda segment: segment.terrain_id))


def _validate_terrain_path_segment(
    field_name: str,
    value: object,
) -> TerrainPathSegment:
    if type(value) is not TerrainPathSegment:
        raise GeometryError(f"{field_name} must be a TerrainPathSegment.")
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


def _terrain_path_segment(
    *,
    terrain_id: str,
    traversal_mode: TerrainTraversalMode,
    path: tuple[Pose, ...],
    touching_poses: tuple[Pose, ...],
    policy: TerrainMovementPolicy,
) -> TerrainPathSegment:
    horizontal_distance = _path_horizontal_distance(path)
    vertical_distance = _path_vertical_distance(path)
    if traversal_mode is TerrainTraversalMode.AIR_PATH:
        counted_distance = _path_3d_distance(path)
        air_path_measurement_pending = policy.fly_uses_air_path_measurement
    elif traversal_mode is TerrainTraversalMode.CLIMB and policy.climb_vertical_distance_counts:
        counted_distance = horizontal_distance + vertical_distance
        air_path_measurement_pending = False
    else:
        counted_distance = horizontal_distance
        air_path_measurement_pending = False
    return TerrainPathSegment(
        terrain_id=terrain_id,
        traversal_mode=traversal_mode,
        start_pose=touching_poses[0],
        end_pose=touching_poses[-1],
        horizontal_distance_inches=horizontal_distance,
        vertical_distance_inches=vertical_distance,
        counted_distance_inches=counted_distance,
        air_path_measurement_pending=air_path_measurement_pending,
    )


def _model_horizontally_intersects_terrain(model: Model, terrain: TerrainVolume) -> bool:
    return shapely_backend.footprint_for_terrain(terrain).intersects(
        shapely_backend.footprint_for_base(model.base, model.pose)
    )


def _model_endpoint_is_on_support_surface(
    model: Model,
    surface: TerrainSupportSurface,
) -> bool:
    if not math.isclose(model.pose.position.z, surface.z_inches):
        return False
    return shapely_backend.base_footprint_within_bounds(
        model.base,
        model.pose,
        surface.bounds(),
    ) or shapely_backend.base_footprint_intersects_bounds(
        model.base,
        model.pose,
        surface.bounds(),
    )


def _endpoint_is_supported_by_feature_surface(
    *,
    feature: TerrainFeatureDefinition,
    terrain: TerrainVolume,
    end_model: Model,
) -> bool:
    for surface in feature.support_surfaces(no_overhang_required=False):
        if terrain.terrain_id != f"{feature.feature_id}:{surface.surface_id}":
            continue
        if _model_endpoint_is_on_support_surface(end_model, surface):
            return True
    return False


def _model_endpoint_intersects_feature_footprint(
    model: Model,
    feature: TerrainFeatureDefinition,
) -> bool:
    return shapely_backend.base_footprint_intersects_bounds(
        model.base,
        model.pose,
        feature.bounds(),
    )


def _model_base_is_fully_supported(
    model: Model,
    surface: TerrainSupportSurface,
) -> bool:
    return shapely_backend.base_footprint_within_bounds(
        model.base,
        model.pose,
        surface.bounds(),
    )


def _pose_is_mid_climb(pose: Pose, terrain: TerrainVolume, model: Model) -> bool:
    model_at_end = _model_at_pose(model, pose)
    if not _model_horizontally_intersects_terrain(model_at_end, terrain):
        return False
    bottom_z = pose.position.z
    terrain_bottom, terrain_top = terrain.vertical_interval()
    return terrain_bottom < bottom_z < terrain_top and not math.isclose(bottom_z, terrain_top)


def _path_reaches_or_clears_terrain_top(
    touching_poses: tuple[Pose, ...],
    terrain: TerrainVolume,
) -> bool:
    terrain_top = terrain.top_z_inches()
    return any(
        pose.position.z > terrain_top or math.isclose(pose.position.z, terrain_top)
        for pose in touching_poses
    )


def _path_horizontal_distance(poses: tuple[Pose, ...]) -> float:
    return sum(
        math.hypot(
            end.position.x - start.position.x,
            end.position.y - start.position.y,
        )
        for start, end in pairwise(poses)
    )


def _path_vertical_distance(poses: tuple[Pose, ...]) -> float:
    return sum(abs(end.position.z - start.position.z) for start, end in pairwise(poses))


def _path_3d_distance(poses: tuple[Pose, ...]) -> float:
    return sum(start.distance_3d_to(end) for start, end in pairwise(poses))


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


def _invalid_path_validation(
    violation_code: str,
    message: str,
    *,
    model_id: str | None,
    blocker_id: str | None = None,
    metrics: _PathValidationMetricCounts,
    movement_distance_witness: MovementDistanceWitness,
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
        pivot_cost_inches=movement_distance_witness.pivot_cost_inches,
        pivot_cost_pending=False,
        movement_distance_witness=movement_distance_witness,
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
