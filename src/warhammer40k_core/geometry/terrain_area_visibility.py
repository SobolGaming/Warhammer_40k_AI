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
    member_terrain_area_ids: list[str]
    classification: str
    footprint_polygons: list[list[TerrainVisibilityAreaPointPayload]]


@dataclass(frozen=True, slots=True)
class TerrainVisibilityArea:
    terrain_area_id: str
    member_terrain_area_ids: tuple[str, ...]
    classification: TerrainAreaClassification
    footprint_polygons: tuple[tuple[Point2D, ...], ...]

    def __post_init__(self) -> None:
        terrain_area_id = _validate_identifier(
            "TerrainVisibilityArea terrain_area_id",
            self.terrain_area_id,
        )
        object.__setattr__(self, "terrain_area_id", terrain_area_id)
        member_ids = _validate_member_terrain_area_ids(self.member_terrain_area_ids)
        try:
            classification = terrain_area_classification_from_token(self.classification)
        except TerrainClassificationError as exc:
            raise GeometryError("TerrainVisibilityArea classification is invalid.") from exc
        object.__setattr__(self, "classification", classification)
        footprint_polygons = _validate_footprint_polygons(
            "TerrainVisibilityArea footprint_polygons",
            self.footprint_polygons,
        )
        if len(member_ids) != len(footprint_polygons):
            raise GeometryError(
                "TerrainVisibilityArea member IDs and footprint polygons must have equal length."
            )
        if len(member_ids) == 1 and terrain_area_id != member_ids[0]:
            raise GeometryError(
                "A single-member TerrainVisibilityArea must use its physical member ID."
            )
        if len(member_ids) > 1 and terrain_area_id in member_ids:
            raise GeometryError(
                "A grouped TerrainVisibilityArea logical ID must differ from every member ID."
            )
        ordered_members = tuple(
            sorted(
                zip(member_ids, footprint_polygons, strict=True),
                key=lambda member: member[0],
            )
        )
        object.__setattr__(
            self,
            "member_terrain_area_ids",
            tuple(member_id for member_id, _polygon in ordered_members),
        )
        object.__setattr__(
            self,
            "footprint_polygons",
            tuple(polygon for _member_id, polygon in ordered_members),
        )

    def to_payload(self) -> TerrainVisibilityAreaPayload:
        return {
            "terrain_area_id": self.terrain_area_id,
            "member_terrain_area_ids": list(self.member_terrain_area_ids),
            "classification": self.classification.value,
            "footprint_polygons": [
                [{"x_inches": point[0], "y_inches": point[1]} for point in footprint_polygon]
                for footprint_polygon in self.footprint_polygons
            ],
        }

    @classmethod
    def from_payload(cls, payload: object) -> Self:
        if not isinstance(payload, dict):
            raise GeometryError("TerrainVisibilityArea payload must be a mapping.")
        raw_payload = cast(TerrainVisibilityAreaPayload, payload)
        _require_payload_keys(
            "TerrainVisibilityArea payload",
            raw_payload,
            (
                "terrain_area_id",
                "member_terrain_area_ids",
                "classification",
                "footprint_polygons",
            ),
        )
        raw_member_ids = raw_payload["member_terrain_area_ids"]
        if type(raw_member_ids) is not list:
            raise GeometryError("TerrainVisibilityArea payload member IDs must be a list.")
        return cls(
            terrain_area_id=raw_payload["terrain_area_id"],
            member_terrain_area_ids=tuple(raw_member_ids),
            classification=_classification_from_token(raw_payload["classification"]),
            footprint_polygons=_footprint_polygons_from_payload(raw_payload["footprint_polygons"]),
        )


def validate_terrain_visibility_areas(
    field_name: str,
    values: object,
) -> tuple[TerrainVisibilityArea, ...]:
    if type(values) is not tuple:
        raise GeometryError(f"{field_name} must be a tuple.")
    areas: list[TerrainVisibilityArea] = []
    seen: set[str] = set()
    seen_member_ids: set[str] = set()
    for value in cast(tuple[object, ...], values):
        if type(value) is not TerrainVisibilityArea:
            raise GeometryError(f"{field_name} must contain TerrainVisibilityArea values.")
        if value.terrain_area_id in seen:
            raise GeometryError(f"{field_name} must not contain duplicate IDs.")
        duplicate_member_ids = seen_member_ids.intersection(value.member_terrain_area_ids)
        if duplicate_member_ids:
            raise GeometryError(
                f"{field_name} must not assign one physical member to multiple visibility areas."
            )
        seen.add(value.terrain_area_id)
        seen_member_ids.update(value.member_terrain_area_ids)
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
    return shapely_backend.base_footprint_intersects_polygon_union(
        model.base,
        model.pose,
        area.footprint_polygons,
    )


def model_wholly_within_terrain_area(model: Model, area: TerrainVisibilityArea) -> bool:
    _validate_model_and_area(model, area)
    return shapely_backend.base_footprint_within_polygon_union(
        model.base,
        model.pose,
        area.footprint_polygons,
    )


def ray_intersects_terrain_area(
    start: Point3,
    end: Point3,
    area: TerrainVisibilityArea,
) -> bool:
    if type(area) is not TerrainVisibilityArea:
        raise GeometryError("ray terrain area must be TerrainVisibilityArea.")
    return shapely_backend.segment_intersects_polygon_union(start, end, area.footprint_polygons)


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
            shapely_backend.polygon_within_polygon_union(
                feature_footprint,
                area.footprint_polygons,
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


def _classification_from_token(token: object) -> TerrainAreaClassification:
    try:
        return terrain_area_classification_from_token(token)
    except TerrainClassificationError as exc:
        raise GeometryError("TerrainVisibilityArea classification is invalid.") from exc


def _validate_member_terrain_area_ids(value: object) -> tuple[str, ...]:
    if type(value) is not tuple or not value:
        raise GeometryError(
            "TerrainVisibilityArea member_terrain_area_ids must be non-empty tuple."
        )
    member_ids = tuple(
        _validate_identifier("TerrainVisibilityArea member terrain_area_id", raw_member_id)
        for raw_member_id in cast(tuple[object, ...], value)
    )
    if len(set(member_ids)) != len(member_ids):
        raise GeometryError("TerrainVisibilityArea member IDs must not contain duplicates.")
    return member_ids


def _validate_footprint_polygons(
    field_name: str,
    value: object,
) -> tuple[tuple[Point2D, ...], ...]:
    if type(value) is not tuple or not value:
        raise GeometryError(f"{field_name} must be a non-empty tuple.")
    return tuple(
        _validate_polygon(f"{field_name} member {index}", raw_polygon)
        for index, raw_polygon in enumerate(cast(tuple[object, ...], value))
    )


def _footprint_polygons_from_payload(value: object) -> tuple[tuple[Point2D, ...], ...]:
    if type(value) is not list or not value:
        raise GeometryError("TerrainVisibilityArea payload footprint_polygons must be a list.")
    polygons: list[tuple[Point2D, ...]] = []
    for polygon_index, raw_polygon in enumerate(cast(list[object], value)):
        if type(raw_polygon) is not list:
            raise GeometryError(
                "TerrainVisibilityArea payload footprint_polygons members must be lists."
            )
        points: list[Point2D] = []
        for point_index, raw_point in enumerate(cast(list[object], raw_polygon)):
            if not isinstance(raw_point, dict):
                raise GeometryError(
                    "TerrainVisibilityArea payload footprint polygon points must be mappings."
                )
            point_payload = cast(dict[str, object], raw_point)
            _require_payload_keys(
                (
                    "TerrainVisibilityArea payload footprint polygon "
                    f"{polygon_index} point {point_index}"
                ),
                point_payload,
                ("x_inches", "y_inches"),
            )
            points.append(
                (
                    validate_finite_number(
                        "TerrainVisibilityArea payload footprint polygon x_inches",
                        point_payload["x_inches"],
                    ),
                    validate_finite_number(
                        "TerrainVisibilityArea payload footprint polygon y_inches",
                        point_payload["y_inches"],
                    ),
                )
            )
        polygons.append(tuple(points))
    return tuple(polygons)


def _require_payload_keys(
    field_name: str,
    payload: object,
    required_keys: tuple[str, ...],
) -> None:
    if not isinstance(payload, dict):
        raise GeometryError(f"{field_name} must be a mapping.")
    missing_keys = tuple(key for key in required_keys if key not in payload)
    if missing_keys:
        raise GeometryError(f"{field_name} missing required fields: {', '.join(missing_keys)}.")


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
