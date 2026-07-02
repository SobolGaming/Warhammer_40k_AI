from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Self, TypedDict, cast

from warhammer40k_core.core.objectives import ObjectiveMarker
from warhammer40k_core.core.ruleset_descriptor import (
    RulesetDescriptor,
    TerrainEndpointSupportPolicy,
)
from warhammer40k_core.core.validation import IdentifierValidator
from warhammer40k_core.engine.phase import GameLifecycleError
from warhammer40k_core.engine.unit_factory import UnitInstance
from warhammer40k_core.geometry import shapely_backend
from warhammer40k_core.geometry.measurement import objective_marker_endpoint_is_clear
from warhammer40k_core.geometry.pose import Pose
from warhammer40k_core.geometry.terrain import TerrainFeatureDefinition, TerrainSupportSurface
from warhammer40k_core.geometry.volume import Model


class TerrainEndpointPlacementViolationPayload(TypedDict):
    violation_code: str
    message: str
    model_instance_id: str
    blocker_id: str


class ObjectiveMarkerEndpointPlacementViolationPayload(TypedDict):
    violation_code: str
    message: str
    model_instance_id: str
    blocker_id: str


_EPSILON = 1e-9


@dataclass(frozen=True, slots=True)
class TerrainEndpointPlacementViolation:
    violation_code: str
    message: str
    model_instance_id: str
    blocker_id: str

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "violation_code",
            _validate_identifier(
                "TerrainEndpointPlacementViolation violation_code",
                self.violation_code,
            ),
        )
        object.__setattr__(
            self,
            "message",
            _validate_identifier("TerrainEndpointPlacementViolation message", self.message),
        )
        object.__setattr__(
            self,
            "model_instance_id",
            _validate_identifier(
                "TerrainEndpointPlacementViolation model_instance_id",
                self.model_instance_id,
            ),
        )
        object.__setattr__(
            self,
            "blocker_id",
            _validate_identifier("TerrainEndpointPlacementViolation blocker_id", self.blocker_id),
        )

    def to_payload(self) -> TerrainEndpointPlacementViolationPayload:
        return {
            "violation_code": self.violation_code,
            "message": self.message,
            "model_instance_id": self.model_instance_id,
            "blocker_id": self.blocker_id,
        }

    @classmethod
    def from_payload(cls, payload: TerrainEndpointPlacementViolationPayload) -> Self:
        return cls(
            violation_code=payload["violation_code"],
            message=payload["message"],
            model_instance_id=payload["model_instance_id"],
            blocker_id=payload["blocker_id"],
        )


@dataclass(frozen=True, slots=True)
class ObjectiveMarkerEndpointPlacementViolation:
    violation_code: str
    message: str
    model_instance_id: str
    blocker_id: str

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "violation_code",
            _validate_identifier(
                "ObjectiveMarkerEndpointPlacementViolation violation_code",
                self.violation_code,
            ),
        )
        object.__setattr__(
            self,
            "message",
            _validate_identifier(
                "ObjectiveMarkerEndpointPlacementViolation message",
                self.message,
            ),
        )
        object.__setattr__(
            self,
            "model_instance_id",
            _validate_identifier(
                "ObjectiveMarkerEndpointPlacementViolation model_instance_id",
                self.model_instance_id,
            ),
        )
        object.__setattr__(
            self,
            "blocker_id",
            _validate_identifier(
                "ObjectiveMarkerEndpointPlacementViolation blocker_id",
                self.blocker_id,
            ),
        )

    def to_payload(self) -> ObjectiveMarkerEndpointPlacementViolationPayload:
        return {
            "violation_code": self.violation_code,
            "message": self.message,
            "model_instance_id": self.model_instance_id,
            "blocker_id": self.blocker_id,
        }

    @classmethod
    def from_payload(cls, payload: ObjectiveMarkerEndpointPlacementViolationPayload) -> Self:
        return cls(
            violation_code=payload["violation_code"],
            message=payload["message"],
            model_instance_id=payload["model_instance_id"],
            blocker_id=payload["blocker_id"],
        )


def terrain_endpoint_placement_violation(
    *,
    model: Model,
    unit: UnitInstance,
    ruleset_descriptor: RulesetDescriptor,
    terrain_features: tuple[TerrainFeatureDefinition, ...],
    violation_code: str,
    placement_label: str,
) -> TerrainEndpointPlacementViolation | None:
    if type(model) is not Model:
        raise GameLifecycleError("terrain endpoint placement requires a geometry Model.")
    if type(unit) is not UnitInstance:
        raise GameLifecycleError("terrain endpoint placement requires a UnitInstance.")
    if type(ruleset_descriptor) is not RulesetDescriptor:
        raise GameLifecycleError("terrain endpoint placement requires a RulesetDescriptor.")
    features = _validate_terrain_feature_tuple("terrain_features", terrain_features)
    code = _validate_identifier("violation_code", violation_code)
    label = _validate_identifier("placement_label", placement_label)
    movement_keywords = {_canonical_keyword(keyword) for keyword in unit.keywords}
    for feature in features:
        feature_policy = ruleset_descriptor.terrain_movement_policy.policy_for_feature_kind(
            feature.feature_kind
        )
        support_surfaces = feature.support_surfaces(
            no_overhang_required=feature_policy.no_overhang_required
        )
        touched_surfaces = tuple(
            surface
            for surface in support_surfaces
            if _model_endpoint_is_on_support_surface(model, surface)
        )
        for terrain in feature.terrain_volumes():
            if terrain.intersects_model(model) and not touched_surfaces:
                return TerrainEndpointPlacementViolation(
                    violation_code=code,
                    message=f"{label} endpoint intersects terrain.",
                    model_instance_id=model.model_id,
                    blocker_id=terrain.terrain_id,
                )
        if not touched_surfaces:
            if (
                model.pose.position.z > 0.0
                and feature_policy.no_overhang_required
                and shapely_backend.base_footprint_intersects_bounds(
                    model.base,
                    model.pose,
                    feature.bounds(),
                )
            ):
                return TerrainEndpointPlacementViolation(
                    violation_code=code,
                    message=f"{label} endpoint has no support surface.",
                    model_instance_id=model.model_id,
                    blocker_id=feature.feature_id,
                )
            continue
        for surface in touched_surfaces:
            elevated = surface.z_inches > 0.0
            if (
                feature_policy.endpoint_support_policy
                is TerrainEndpointSupportPolicy.NOT_ALLOWED_ON_TOP
            ):
                return TerrainEndpointPlacementViolation(
                    violation_code=code,
                    message=f"{label} cannot end on this terrain feature.",
                    model_instance_id=model.model_id,
                    blocker_id=surface.surface_id,
                )
            if (
                feature_policy.endpoint_support_policy
                is TerrainEndpointSupportPolicy.ALLOWED_ON_GROUND_FLOOR_ONLY
                and elevated
            ):
                return TerrainEndpointPlacementViolation(
                    violation_code=code,
                    message=f"{label} cannot end on an elevated surface.",
                    model_instance_id=model.model_id,
                    blocker_id=surface.surface_id,
                )
            if (
                elevated
                and feature_policy.ground_floor_only_unless_keyword
                and not movement_keywords.intersection(feature_policy.upper_floor_allowed_keywords)
            ):
                return TerrainEndpointPlacementViolation(
                    violation_code=code,
                    message=f"{label} lacks a keyword for the upper floor.",
                    model_instance_id=model.model_id,
                    blocker_id=surface.surface_id,
                )
            support_containment_required = surface.no_overhang_required and (
                elevated
                or feature_policy.endpoint_support_policy
                is TerrainEndpointSupportPolicy.ALLOWED_ON_TOP_WITH_NO_OVERHANG
            )
            if support_containment_required and not shapely_backend.base_footprint_within_bounds(
                model.base,
                model.pose,
                surface.bounds(),
            ):
                return TerrainEndpointPlacementViolation(
                    violation_code=code,
                    message=f"{label} base overhangs support surface.",
                    model_instance_id=model.model_id,
                    blocker_id=surface.surface_id,
                )
    return None


def objective_marker_endpoint_placement_violation(
    *,
    model: Model,
    objective_markers: tuple[ObjectiveMarker, ...],
    violation_code: str,
    placement_label: str,
) -> ObjectiveMarkerEndpointPlacementViolation | None:
    if type(model) is not Model:
        raise GameLifecycleError("objective marker endpoint placement requires a geometry Model.")
    markers = _validate_objective_marker_tuple("objective_markers", objective_markers)
    code = _validate_identifier("violation_code", violation_code)
    label = _validate_identifier("placement_label", placement_label)
    for marker in markers:
        if not marker.blocks_placement:
            continue
        marker_pose = Pose.at(marker.x_inches, marker.y_inches, marker.z_inches)
        if objective_marker_endpoint_is_clear(
            marker_pose,
            model,
            marker_id=marker.objective_marker_id,
            marker_diameter_inches=marker.marker_diameter_inches,
        ):
            continue
        return ObjectiveMarkerEndpointPlacementViolation(
            violation_code=code,
            message=f"{label} cannot end on an objective marker.",
            model_instance_id=model.model_id,
            blocker_id=marker.objective_marker_id,
        )
    return None


def _model_endpoint_is_on_support_surface(
    model: Model,
    surface: TerrainSupportSurface,
) -> bool:
    return math.isclose(
        model.pose.position.z,
        surface.z_inches,
        rel_tol=0.0,
        abs_tol=_EPSILON,
    ) and shapely_backend.base_footprint_intersects_bounds(
        model.base,
        model.pose,
        surface.bounds(),
    )


def _validate_terrain_feature_tuple(
    field_name: str,
    values: object,
) -> tuple[TerrainFeatureDefinition, ...]:
    if type(values) is not tuple:
        raise GameLifecycleError(f"{field_name} must be a tuple.")
    features: list[TerrainFeatureDefinition] = []
    for value in cast(tuple[object, ...], values):
        if type(value) is not TerrainFeatureDefinition:
            raise GameLifecycleError(f"{field_name} must contain TerrainFeatureDefinition values.")
        features.append(value)
    return tuple(sorted(features, key=lambda feature: feature.feature_id))


def _validate_objective_marker_tuple(
    field_name: str,
    values: object,
) -> tuple[ObjectiveMarker, ...]:
    if type(values) is not tuple:
        raise GameLifecycleError(f"{field_name} must be a tuple.")
    markers: list[ObjectiveMarker] = []
    seen: set[str] = set()
    for value in cast(tuple[object, ...], values):
        if type(value) is not ObjectiveMarker:
            raise GameLifecycleError(f"{field_name} must contain ObjectiveMarker values.")
        if value.objective_marker_id in seen:
            raise GameLifecycleError(f"{field_name} must not contain duplicate markers.")
        seen.add(value.objective_marker_id)
        markers.append(value)
    return tuple(sorted(markers, key=lambda marker: marker.objective_marker_id))


def _canonical_keyword(value: str) -> str:
    return _validate_identifier("keyword", value).upper().replace(" ", "_").replace("-", "_")


_validate_identifier = IdentifierValidator(GameLifecycleError)
