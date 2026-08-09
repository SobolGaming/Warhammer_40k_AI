from __future__ import annotations

from dataclasses import dataclass
from typing import Self, TypedDict, cast

from warhammer40k_core.geometry import shapely_backend
from warhammer40k_core.geometry.polygons import (
    Point2D,
    polygon_self_intersects,
    signed_polygon_area,
)
from warhammer40k_core.geometry.pose import GeometryError, Point3, validate_finite_number
from warhammer40k_core.geometry.terrain import TerrainFeatureDefinition
from warhammer40k_core.geometry.terrain_classification import (
    TerrainAreaClassification,
    TerrainClassificationError,
    terrain_area_classification_from_token,
)
from warhammer40k_core.geometry.validation import IdentifierValidator
from warhammer40k_core.geometry.volume import Model


class TerrainVisibilityAreaPointPayload(TypedDict):
    x_inches: float
    y_inches: float


class TerrainVisibilityAreaPayload(TypedDict):
    terrain_area_id: str
    classification: str
    footprint_polygon: list[TerrainVisibilityAreaPointPayload]


@dataclass(frozen=True, slots=True)
class TerrainVisibilityArea:
    terrain_area_id: str
    classification: TerrainAreaClassification
    footprint_polygon: tuple[Point2D, ...]

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "terrain_area_id",
            _validate_identifier("TerrainVisibilityArea terrain_area_id", self.terrain_area_id),
        )
        try:
            classification = terrain_area_classification_from_token(self.classification)
        except TerrainClassificationError as exc:
            raise GeometryError("TerrainVisibilityArea classification is invalid.") from exc
        object.__setattr__(self, "classification", classification)
        object.__setattr__(
            self,
            "footprint_polygon",
            _validate_polygon(
                "TerrainVisibilityArea footprint_polygon",
                self.footprint_polygon,
            ),
        )

    def to_payload(self) -> TerrainVisibilityAreaPayload:
        return {
            "terrain_area_id": self.terrain_area_id,
            "classification": self.classification.value,
            "footprint_polygon": [
                {"x_inches": point[0], "y_inches": point[1]} for point in self.footprint_polygon
            ],
        }

    @classmethod
    def from_payload(cls, payload: TerrainVisibilityAreaPayload) -> Self:
        return cls(
            terrain_area_id=payload["terrain_area_id"],
            classification=terrain_area_classification_from_token(payload["classification"]),
            footprint_polygon=tuple(
                (point["x_inches"], point["y_inches"]) for point in payload["footprint_polygon"]
            ),
        )


def validate_terrain_visibility_areas(
    field_name: str,
    values: object,
) -> tuple[TerrainVisibilityArea, ...]:
    if type(values) is not tuple:
        raise GeometryError(f"{field_name} must be a tuple.")
    areas: list[TerrainVisibilityArea] = []
    seen: set[str] = set()
    for value in cast(tuple[object, ...], values):
        if type(value) is not TerrainVisibilityArea:
            raise GeometryError(f"{field_name} must contain TerrainVisibilityArea values.")
        if value.terrain_area_id in seen:
            raise GeometryError(f"{field_name} must not contain duplicate IDs.")
        seen.add(value.terrain_area_id)
        areas.append(value)
    return tuple(sorted(areas, key=lambda area: area.terrain_area_id))


def classification_has_visibility_semantics(
    classification: TerrainAreaClassification,
) -> bool:
    return classification in (
        TerrainAreaClassification.DENSE,
        TerrainAreaClassification.LIGHT,
        TerrainAreaClassification.MIXED,
    )


def classification_is_solid(classification: TerrainAreaClassification) -> bool:
    return classification in (
        TerrainAreaClassification.DENSE,
        TerrainAreaClassification.MIXED,
    )


def model_intersects_terrain_area(model: Model, area: TerrainVisibilityArea) -> bool:
    _validate_model_and_area(model, area)
    return shapely_backend.base_footprint_intersects_polygon(
        model.base,
        model.pose,
        area.footprint_polygon,
    )


def model_wholly_within_terrain_area(model: Model, area: TerrainVisibilityArea) -> bool:
    _validate_model_and_area(model, area)
    return shapely_backend.base_footprint_within_polygon(
        model.base,
        model.pose,
        area.footprint_polygon,
    )


def ray_intersects_terrain_area(
    start: Point3,
    end: Point3,
    area: TerrainVisibilityArea,
) -> bool:
    if type(area) is not TerrainVisibilityArea:
        raise GeometryError("ray terrain area must be TerrainVisibilityArea.")
    return shapely_backend.segment_intersects_polygon(start, end, area.footprint_polygon)


def feature_is_associated_with_terrain_area(
    feature: TerrainFeatureDefinition,
    areas: tuple[TerrainVisibilityArea, ...],
) -> bool:
    if type(feature) is not TerrainFeatureDefinition:
        raise GeometryError("terrain-area feature must be TerrainFeatureDefinition.")
    return feature.feature_id in feature_ids_associated_with_terrain_areas((feature,), areas)


def feature_ids_associated_with_terrain_areas(
    features: tuple[TerrainFeatureDefinition, ...],
    areas: tuple[TerrainVisibilityArea, ...],
) -> frozenset[str]:
    if type(features) is not tuple:
        raise GeometryError("terrain-area features must be a tuple.")
    validated_areas = validate_terrain_visibility_areas("terrain feature areas", areas)
    associated_feature_ids: set[str] = set()
    for feature in cast(tuple[object, ...], features):
        if type(feature) is not TerrainFeatureDefinition:
            raise GeometryError(
                "terrain-area features must contain TerrainFeatureDefinition values."
            )
        feature_footprint = feature.rules_footprint_points()
        if any(
            shapely_backend.polygon_within_polygon(
                feature_footprint,
                area.footprint_polygon,
            )
            for area in validated_areas
        ):
            associated_feature_ids.add(feature.feature_id)
    return frozenset(associated_feature_ids)


def _validate_model_and_area(model: Model, area: TerrainVisibilityArea) -> None:
    if type(model) is not Model:
        raise GeometryError("terrain-area visibility model must be Model.")
    if type(area) is not TerrainVisibilityArea:
        raise GeometryError("terrain-area visibility area must be TerrainVisibilityArea.")


_validate_identifier = IdentifierValidator(GeometryError)


def _validate_polygon(field_name: str, value: object) -> tuple[Point2D, ...]:
    if type(value) is not tuple:
        raise GeometryError(f"{field_name} must be a tuple.")
    points: list[Point2D] = []
    for index, raw_point in enumerate(cast(tuple[object, ...], value)):
        if type(raw_point) is not tuple:
            raise GeometryError(f"{field_name} values must be Point2D tuples.")
        raw_point_tuple = cast(tuple[object, ...], raw_point)
        if len(raw_point_tuple) != 2:
            raise GeometryError(f"{field_name} values must be Point2D tuples.")
        x, y = raw_point_tuple
        points.append(
            (
                validate_finite_number(f"{field_name} point {index} x", x),
                validate_finite_number(f"{field_name} point {index} y", y),
            )
        )
    polygon = tuple(points)
    if len(polygon) < 3:
        raise GeometryError(f"{field_name} must contain at least three points.")
    if len(set(polygon)) != len(polygon):
        raise GeometryError(f"{field_name} must not contain duplicate points.")
    if polygon_self_intersects(polygon):
        raise GeometryError(f"{field_name} must be a simple polygon.")
    if abs(signed_polygon_area(polygon)) <= 1e-9:
        raise GeometryError(f"{field_name} must have positive area.")
    return polygon
