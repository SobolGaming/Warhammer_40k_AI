from __future__ import annotations

import math
from dataclasses import dataclass
from enum import StrEnum
from typing import Self, TypedDict, cast

from warhammer40k_core.core.terrain_display import (
    TerrainDisplayPoint,
    TerrainDisplayPointPayload,
)
from warhammer40k_core.core.validation import IdentifierValidator

_AREA_EPSILON = 1e-9
_GEOMETRY_EPSILON = 1e-6


class TerrainAreaError(ValueError):
    """Raised when terrain-area footprint data violates CORE V2 invariants."""


class TerrainAreaClassification(StrEnum):
    DENSE = "dense"
    LIGHT = "light"
    UNKNOWN = "unknown"


class SymmetryAxis(StrEnum):
    NONE = "none"
    X_MIDLINE = "x_midline"
    Y_MIDLINE = "y_midline"
    POINT_CENTER = "point_center"


class TerrainAreaLocalTransform(StrEnum):
    IDENTITY = "identity"
    MIRROR_Y_AXIS = "mirror_y_axis"


class TerrainAreaFootprintTemplatePayload(TypedDict):
    footprint_template_id: str
    name: str
    bounding_width_inches: float
    bounding_depth_inches: float
    polygon_vertices_inches: list[TerrainDisplayPointPayload]
    source_id: str


class PlacedTerrainAreaPayload(TypedDict):
    terrain_area_id: str
    footprint_template_id: str
    terrain_feature_kind: str
    classification: str
    center_x_inches: float
    center_y_inches: float
    rotation_degrees: float
    local_transform: str
    footprint_polygon: list[TerrainDisplayPointPayload]
    source_layout_id: str
    source_id: str
    source_transform: str
    symmetry_axis: str


@dataclass(frozen=True, slots=True)
class TerrainAreaFootprintTemplate:
    footprint_template_id: str
    name: str
    bounding_width_inches: float
    bounding_depth_inches: float
    polygon_vertices_inches: tuple[TerrainDisplayPoint, ...]
    source_id: str

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "footprint_template_id",
            _validate_unprefixed_identifier(
                "TerrainAreaFootprintTemplate footprint_template_id",
                self.footprint_template_id,
                reserved_prefix="terrain-area-footprint-template:",
            ),
        )
        object.__setattr__(
            self,
            "name",
            _validate_identifier("TerrainAreaFootprintTemplate name", self.name),
        )
        width = _validate_positive_number(
            "TerrainAreaFootprintTemplate bounding_width_inches",
            self.bounding_width_inches,
        )
        depth = _validate_positive_number(
            "TerrainAreaFootprintTemplate bounding_depth_inches",
            self.bounding_depth_inches,
        )
        polygon = _validate_polygon(
            "TerrainAreaFootprintTemplate polygon_vertices_inches",
            self.polygon_vertices_inches,
        )
        _validate_polygon_matches_centered_bounds(
            field_name="TerrainAreaFootprintTemplate polygon_vertices_inches",
            polygon=polygon,
            width=width,
            depth=depth,
        )
        object.__setattr__(self, "bounding_width_inches", width)
        object.__setattr__(self, "bounding_depth_inches", depth)
        object.__setattr__(self, "polygon_vertices_inches", polygon)
        object.__setattr__(
            self,
            "source_id",
            _validate_identifier("TerrainAreaFootprintTemplate source_id", self.source_id),
        )

    def to_payload(self) -> TerrainAreaFootprintTemplatePayload:
        return {
            "footprint_template_id": self.footprint_template_id,
            "name": self.name,
            "bounding_width_inches": self.bounding_width_inches,
            "bounding_depth_inches": self.bounding_depth_inches,
            "polygon_vertices_inches": [
                point.to_payload() for point in self.polygon_vertices_inches
            ],
            "source_id": self.source_id,
        }

    @classmethod
    def from_payload(cls, payload: object) -> Self:
        if not isinstance(payload, dict):
            raise TerrainAreaError("Terrain area footprint template payload must be a mapping.")
        raw_payload = cast(TerrainAreaFootprintTemplatePayload, payload)
        _require_payload_keys(
            "Terrain area footprint template payload",
            raw_payload,
            (
                "footprint_template_id",
                "name",
                "bounding_width_inches",
                "bounding_depth_inches",
                "polygon_vertices_inches",
                "source_id",
            ),
        )
        return cls(
            footprint_template_id=raw_payload["footprint_template_id"],
            name=raw_payload["name"],
            bounding_width_inches=raw_payload["bounding_width_inches"],
            bounding_depth_inches=raw_payload["bounding_depth_inches"],
            polygon_vertices_inches=tuple(
                TerrainDisplayPoint.from_payload(point_payload)
                for point_payload in raw_payload["polygon_vertices_inches"]
            ),
            source_id=raw_payload["source_id"],
        )


@dataclass(frozen=True, slots=True)
class PlacedTerrainArea:
    terrain_area_id: str
    footprint_template_id: str
    terrain_feature_kind: str
    classification: TerrainAreaClassification
    center_x_inches: float
    center_y_inches: float
    rotation_degrees: float
    local_transform: TerrainAreaLocalTransform
    footprint_polygon: tuple[TerrainDisplayPoint, ...]
    source_layout_id: str
    source_id: str
    source_transform: str
    symmetry_axis: SymmetryAxis

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "terrain_area_id",
            _validate_unprefixed_identifier(
                "PlacedTerrainArea terrain_area_id",
                self.terrain_area_id,
                reserved_prefix="terrain-area:",
            ),
        )
        object.__setattr__(
            self,
            "footprint_template_id",
            _validate_identifier(
                "PlacedTerrainArea footprint_template_id",
                self.footprint_template_id,
            ),
        )
        object.__setattr__(
            self,
            "terrain_feature_kind",
            _validate_identifier(
                "PlacedTerrainArea terrain_feature_kind",
                self.terrain_feature_kind,
            ),
        )
        object.__setattr__(
            self,
            "classification",
            terrain_area_classification_from_token(self.classification),
        )
        object.__setattr__(
            self,
            "center_x_inches",
            _validate_finite_number("PlacedTerrainArea center_x_inches", self.center_x_inches),
        )
        object.__setattr__(
            self,
            "center_y_inches",
            _validate_finite_number("PlacedTerrainArea center_y_inches", self.center_y_inches),
        )
        object.__setattr__(
            self,
            "rotation_degrees",
            _validate_finite_number("PlacedTerrainArea rotation_degrees", self.rotation_degrees),
        )
        object.__setattr__(
            self,
            "local_transform",
            terrain_area_local_transform_from_token(self.local_transform),
        )
        object.__setattr__(
            self,
            "footprint_polygon",
            _validate_polygon("PlacedTerrainArea footprint_polygon", self.footprint_polygon),
        )
        object.__setattr__(
            self,
            "source_layout_id",
            _validate_identifier("PlacedTerrainArea source_layout_id", self.source_layout_id),
        )
        object.__setattr__(
            self,
            "source_id",
            _validate_identifier("PlacedTerrainArea source_id", self.source_id),
        )
        object.__setattr__(
            self,
            "source_transform",
            _validate_identifier("PlacedTerrainArea source_transform", self.source_transform),
        )
        object.__setattr__(
            self,
            "symmetry_axis",
            symmetry_axis_from_token(self.symmetry_axis),
        )

    @classmethod
    def from_template(
        cls,
        *,
        terrain_area_id: str,
        template: TerrainAreaFootprintTemplate,
        terrain_feature_kind: str,
        classification: TerrainAreaClassification,
        center_x_inches: float,
        center_y_inches: float,
        rotation_degrees: float,
        source_layout_id: str,
        source_id: str,
        local_transform: TerrainAreaLocalTransform = TerrainAreaLocalTransform.IDENTITY,
        source_transform: str = "explicit",
        symmetry_axis: SymmetryAxis = SymmetryAxis.NONE,
    ) -> Self:
        if type(template) is not TerrainAreaFootprintTemplate:
            raise TerrainAreaError("PlacedTerrainArea template must be a footprint template.")
        return cls(
            terrain_area_id=terrain_area_id,
            footprint_template_id=template.footprint_template_id,
            terrain_feature_kind=terrain_feature_kind,
            classification=classification,
            center_x_inches=center_x_inches,
            center_y_inches=center_y_inches,
            rotation_degrees=rotation_degrees,
            local_transform=local_transform,
            footprint_polygon=transform_polygon(
                template.polygon_vertices_inches,
                center_x_inches=center_x_inches,
                center_y_inches=center_y_inches,
                rotation_degrees=rotation_degrees,
                local_transform=local_transform,
            ),
            source_layout_id=source_layout_id,
            source_id=source_id,
            source_transform=source_transform,
            symmetry_axis=symmetry_axis,
        )

    def bounds(self) -> tuple[float, float, float, float]:
        return polygon_bounds(self.footprint_polygon)

    def is_within_battlefield(self, *, width: float, depth: float) -> bool:
        battlefield_width = _validate_positive_number("battlefield width", width)
        battlefield_depth = _validate_positive_number("battlefield depth", depth)
        return all(
            0.0 <= point.x_inches <= battlefield_width
            and 0.0 <= point.y_inches <= battlefield_depth
            for point in self.footprint_polygon
        )

    def to_payload(self) -> PlacedTerrainAreaPayload:
        return {
            "terrain_area_id": self.terrain_area_id,
            "footprint_template_id": self.footprint_template_id,
            "terrain_feature_kind": self.terrain_feature_kind,
            "classification": self.classification.value,
            "center_x_inches": self.center_x_inches,
            "center_y_inches": self.center_y_inches,
            "rotation_degrees": self.rotation_degrees,
            "local_transform": self.local_transform.value,
            "footprint_polygon": [point.to_payload() for point in self.footprint_polygon],
            "source_layout_id": self.source_layout_id,
            "source_id": self.source_id,
            "source_transform": self.source_transform,
            "symmetry_axis": self.symmetry_axis.value,
        }

    @classmethod
    def from_payload(cls, payload: object) -> Self:
        if not isinstance(payload, dict):
            raise TerrainAreaError("Placed terrain area payload must be a mapping.")
        raw_payload = cast(PlacedTerrainAreaPayload, payload)
        _require_payload_keys(
            "Placed terrain area payload",
            raw_payload,
            (
                "terrain_area_id",
                "footprint_template_id",
                "terrain_feature_kind",
                "classification",
                "center_x_inches",
                "center_y_inches",
                "rotation_degrees",
                "local_transform",
                "footprint_polygon",
                "source_layout_id",
                "source_id",
                "source_transform",
                "symmetry_axis",
            ),
        )
        return cls(
            terrain_area_id=raw_payload["terrain_area_id"],
            footprint_template_id=raw_payload["footprint_template_id"],
            terrain_feature_kind=raw_payload["terrain_feature_kind"],
            classification=terrain_area_classification_from_token(raw_payload["classification"]),
            center_x_inches=raw_payload["center_x_inches"],
            center_y_inches=raw_payload["center_y_inches"],
            rotation_degrees=raw_payload["rotation_degrees"],
            local_transform=terrain_area_local_transform_from_token(raw_payload["local_transform"]),
            footprint_polygon=tuple(
                TerrainDisplayPoint.from_payload(point_payload)
                for point_payload in raw_payload["footprint_polygon"]
            ),
            source_layout_id=raw_payload["source_layout_id"],
            source_id=raw_payload["source_id"],
            source_transform=raw_payload["source_transform"],
            symmetry_axis=symmetry_axis_from_token(raw_payload["symmetry_axis"]),
        )


def terrain_area_classification_from_token(token: object) -> TerrainAreaClassification:
    if type(token) is TerrainAreaClassification:
        return token
    if type(token) is not str:
        raise TerrainAreaError("TerrainAreaClassification token must be a string.")
    try:
        return TerrainAreaClassification(token)
    except ValueError as exc:
        raise TerrainAreaError(f"Unsupported TerrainAreaClassification token: {token}.") from exc


def symmetry_axis_from_token(token: object) -> SymmetryAxis:
    if type(token) is SymmetryAxis:
        return token
    if type(token) is not str:
        raise TerrainAreaError("SymmetryAxis token must be a string.")
    try:
        return SymmetryAxis(token)
    except ValueError as exc:
        raise TerrainAreaError(f"Unsupported SymmetryAxis token: {token}.") from exc


def terrain_area_local_transform_from_token(token: object) -> TerrainAreaLocalTransform:
    if type(token) is TerrainAreaLocalTransform:
        return token
    if type(token) is not str:
        raise TerrainAreaError("TerrainAreaLocalTransform token must be a string.")
    try:
        return TerrainAreaLocalTransform(token)
    except ValueError as exc:
        raise TerrainAreaError(f"Unsupported TerrainAreaLocalTransform token: {token}.") from exc


def rotate_point(point: TerrainDisplayPoint, degrees: float) -> TerrainDisplayPoint:
    if type(point) is not TerrainDisplayPoint:
        raise TerrainAreaError("rotate_point point must be a TerrainDisplayPoint.")
    rotation_degrees = _validate_finite_number("rotation degrees", degrees)
    radians = math.radians(rotation_degrees)
    cosine = math.cos(radians)
    sine = math.sin(radians)
    return TerrainDisplayPoint(
        x_inches=(point.x_inches * cosine) - (point.y_inches * sine),
        y_inches=(point.x_inches * sine) + (point.y_inches * cosine),
    )


def translate_point(
    point: TerrainDisplayPoint,
    *,
    dx_inches: float,
    dy_inches: float,
) -> TerrainDisplayPoint:
    if type(point) is not TerrainDisplayPoint:
        raise TerrainAreaError("translate_point point must be a TerrainDisplayPoint.")
    dx = _validate_finite_number("dx_inches", dx_inches)
    dy = _validate_finite_number("dy_inches", dy_inches)
    return TerrainDisplayPoint(x_inches=point.x_inches + dx, y_inches=point.y_inches + dy)


def transform_polygon(
    points: tuple[TerrainDisplayPoint, ...],
    *,
    center_x_inches: float,
    center_y_inches: float,
    rotation_degrees: float,
    local_transform: TerrainAreaLocalTransform = TerrainAreaLocalTransform.IDENTITY,
) -> tuple[TerrainDisplayPoint, ...]:
    polygon = _validate_polygon("transform_polygon points", points)
    center_x = _validate_finite_number("center_x_inches", center_x_inches)
    center_y = _validate_finite_number("center_y_inches", center_y_inches)
    rotation = _validate_finite_number("rotation_degrees", rotation_degrees)
    transformed_polygon = _apply_local_transform(
        polygon,
        terrain_area_local_transform_from_token(local_transform),
    )
    return tuple(
        translate_point(
            rotate_point(point, rotation),
            dx_inches=center_x,
            dy_inches=center_y,
        )
        for point in transformed_polygon
    )


def mirror_placed_terrain_area(
    area: PlacedTerrainArea,
    *,
    battlefield_width_inches: float,
    battlefield_depth_inches: float,
    terrain_area_id: str,
    source_id: str,
    symmetry_axis: SymmetryAxis,
) -> PlacedTerrainArea:
    if type(area) is not PlacedTerrainArea:
        raise TerrainAreaError("mirror_placed_terrain_area area must be a PlacedTerrainArea.")
    width = _validate_positive_number("battlefield_width_inches", battlefield_width_inches)
    depth = _validate_positive_number("battlefield_depth_inches", battlefield_depth_inches)
    axis = symmetry_axis_from_token(symmetry_axis)
    if axis is SymmetryAxis.NONE:
        raise TerrainAreaError("mirror_placed_terrain_area requires a real symmetry axis.")
    center_x, center_y, rotation = _mirrored_center_and_rotation(
        center_x=area.center_x_inches,
        center_y=area.center_y_inches,
        rotation_degrees=area.rotation_degrees,
        battlefield_width=width,
        battlefield_depth=depth,
        symmetry_axis=axis,
    )
    return PlacedTerrainArea(
        terrain_area_id=terrain_area_id,
        footprint_template_id=area.footprint_template_id,
        terrain_feature_kind=area.terrain_feature_kind,
        classification=area.classification,
        center_x_inches=center_x,
        center_y_inches=center_y,
        rotation_degrees=rotation,
        local_transform=area.local_transform,
        footprint_polygon=tuple(
            _mirror_point(
                point,
                battlefield_width=width,
                battlefield_depth=depth,
                symmetry_axis=axis,
            )
            for point in area.footprint_polygon
        ),
        source_layout_id=area.source_layout_id,
        source_id=source_id,
        source_transform=f"mirrored_from:{area.terrain_area_id}",
        symmetry_axis=axis,
    )


def polygon_bounds(points: tuple[TerrainDisplayPoint, ...]) -> tuple[float, float, float, float]:
    polygon = _validate_polygon("polygon_bounds points", points)
    x_values = tuple(point.x_inches for point in polygon)
    y_values = tuple(point.y_inches for point in polygon)
    return (min(x_values), min(y_values), max(x_values), max(y_values))


def _mirrored_center_and_rotation(
    *,
    center_x: float,
    center_y: float,
    rotation_degrees: float,
    battlefield_width: float,
    battlefield_depth: float,
    symmetry_axis: SymmetryAxis,
) -> tuple[float, float, float]:
    if symmetry_axis is SymmetryAxis.X_MIDLINE:
        return (
            battlefield_width - center_x,
            center_y,
            _generated_rotation(180.0 - rotation_degrees),
        )
    if symmetry_axis is SymmetryAxis.Y_MIDLINE:
        return (center_x, battlefield_depth - center_y, _generated_rotation(-rotation_degrees))
    if symmetry_axis is SymmetryAxis.POINT_CENTER:
        return (
            battlefield_width - center_x,
            battlefield_depth - center_y,
            _generated_rotation(rotation_degrees + 180.0),
        )
    raise TerrainAreaError("Unsupported mirror symmetry axis.")


def _mirror_point(
    point: TerrainDisplayPoint,
    *,
    battlefield_width: float,
    battlefield_depth: float,
    symmetry_axis: SymmetryAxis,
) -> TerrainDisplayPoint:
    if symmetry_axis is SymmetryAxis.X_MIDLINE:
        return TerrainDisplayPoint(
            x_inches=battlefield_width - point.x_inches,
            y_inches=point.y_inches,
        )
    if symmetry_axis is SymmetryAxis.Y_MIDLINE:
        return TerrainDisplayPoint(
            x_inches=point.x_inches,
            y_inches=battlefield_depth - point.y_inches,
        )
    if symmetry_axis is SymmetryAxis.POINT_CENTER:
        return TerrainDisplayPoint(
            x_inches=battlefield_width - point.x_inches,
            y_inches=battlefield_depth - point.y_inches,
        )
    raise TerrainAreaError("Unsupported mirror symmetry axis.")


def _apply_local_transform(
    points: tuple[TerrainDisplayPoint, ...],
    local_transform: TerrainAreaLocalTransform,
) -> tuple[TerrainDisplayPoint, ...]:
    polygon = _validate_polygon("_apply_local_transform points", points)
    transform = terrain_area_local_transform_from_token(local_transform)
    if transform is TerrainAreaLocalTransform.IDENTITY:
        return polygon
    if transform is TerrainAreaLocalTransform.MIRROR_Y_AXIS:
        anchor = polygon[0]
        return _validate_polygon(
            "_apply_local_transform mirrored polygon",
            tuple(
                TerrainDisplayPoint(
                    x_inches=(2.0 * anchor.x_inches) - point.x_inches,
                    y_inches=point.y_inches,
                )
                for point in polygon
            ),
        )
    raise TerrainAreaError("Unsupported TerrainAreaLocalTransform.")


def _generated_rotation(value: float) -> float:
    return value % 360.0


def _validate_polygon(
    field_name: str,
    values: object,
) -> tuple[TerrainDisplayPoint, ...]:
    if type(values) is not tuple:
        raise TerrainAreaError(f"{field_name} must be a tuple.")
    points: list[TerrainDisplayPoint] = []
    for value in cast(tuple[object, ...], values):
        if type(value) is not TerrainDisplayPoint:
            raise TerrainAreaError(f"{field_name} must contain TerrainDisplayPoint values.")
        points.append(value)
    if len(points) < 3:
        raise TerrainAreaError(f"{field_name} must contain at least three points.")
    if points[0] == points[-1]:
        raise TerrainAreaError(f"{field_name} must be unclosed.")
    polygon = tuple(points)
    if abs(_polygon_area(polygon)) <= _AREA_EPSILON:
        raise TerrainAreaError(f"{field_name} must have non-zero area.")
    if _polygon_self_intersects(polygon):
        raise TerrainAreaError(f"{field_name} must not self-intersect.")
    return polygon


def _require_payload_keys(
    field_name: str,
    payload: object,
    required_keys: tuple[str, ...],
) -> None:
    if not isinstance(payload, dict):
        raise TerrainAreaError(f"{field_name} must be a mapping.")
    missing_keys = tuple(key for key in required_keys if key not in payload)
    if missing_keys:
        raise TerrainAreaError(f"{field_name} missing required fields: {', '.join(missing_keys)}.")


def _validate_polygon_matches_centered_bounds(
    *,
    field_name: str,
    polygon: tuple[TerrainDisplayPoint, ...],
    width: float,
    depth: float,
) -> None:
    min_x, min_y, max_x, max_y = polygon_bounds(polygon)
    expected = (-width / 2.0, -depth / 2.0, width / 2.0, depth / 2.0)
    actual = (min_x, min_y, max_x, max_y)
    if any(
        not math.isclose(actual_value, expected_value, rel_tol=0.0, abs_tol=_GEOMETRY_EPSILON)
        for actual_value, expected_value in zip(actual, expected, strict=True)
    ):
        raise TerrainAreaError(f"{field_name} bounds must match the template bounding box.")


def _polygon_area(points: tuple[TerrainDisplayPoint, ...]) -> float:
    total = 0.0
    for index, point in enumerate(points):
        next_point = points[(index + 1) % len(points)]
        total += (point.x_inches * next_point.y_inches) - (next_point.x_inches * point.y_inches)
    return total / 2.0


def _polygon_self_intersects(points: tuple[TerrainDisplayPoint, ...]) -> bool:
    segment_count = len(points)
    for first_index in range(segment_count):
        first_start = points[first_index]
        first_end = points[(first_index + 1) % segment_count]
        for second_index in range(first_index + 1, segment_count):
            if _segments_are_adjacent(first_index, second_index, segment_count):
                continue
            second_start = points[second_index]
            second_end = points[(second_index + 1) % segment_count]
            if _segments_intersect(first_start, first_end, second_start, second_end):
                return True
    return False


def _segments_are_adjacent(first_index: int, second_index: int, segment_count: int) -> bool:
    return (
        first_index == second_index
        or (first_index + 1) % segment_count == second_index
        or (second_index + 1) % segment_count == first_index
    )


def _segments_intersect(
    first_start: TerrainDisplayPoint,
    first_end: TerrainDisplayPoint,
    second_start: TerrainDisplayPoint,
    second_end: TerrainDisplayPoint,
) -> bool:
    first_orientation = _orientation(first_start, first_end, second_start)
    second_orientation = _orientation(first_start, first_end, second_end)
    third_orientation = _orientation(second_start, second_end, first_start)
    fourth_orientation = _orientation(second_start, second_end, first_end)
    if (
        first_orientation * second_orientation < -_GEOMETRY_EPSILON
        and third_orientation * fourth_orientation < -_GEOMETRY_EPSILON
    ):
        return True
    return (
        _point_on_segment(second_start, first_start, first_end)
        or _point_on_segment(second_end, first_start, first_end)
        or _point_on_segment(first_start, second_start, second_end)
        or _point_on_segment(first_end, second_start, second_end)
    )


def _orientation(
    first: TerrainDisplayPoint,
    second: TerrainDisplayPoint,
    third: TerrainDisplayPoint,
) -> float:
    return (second.x_inches - first.x_inches) * (third.y_inches - first.y_inches) - (
        second.y_inches - first.y_inches
    ) * (third.x_inches - first.x_inches)


def _point_on_segment(
    point: TerrainDisplayPoint,
    start: TerrainDisplayPoint,
    end: TerrainDisplayPoint,
) -> bool:
    orientation = _orientation(start, end, point)
    if not math.isclose(orientation, 0.0, rel_tol=0.0, abs_tol=_GEOMETRY_EPSILON):
        return False
    return (
        min(start.x_inches, end.x_inches) - _GEOMETRY_EPSILON
        <= point.x_inches
        <= max(start.x_inches, end.x_inches) + _GEOMETRY_EPSILON
        and min(start.y_inches, end.y_inches) - _GEOMETRY_EPSILON
        <= point.y_inches
        <= max(start.y_inches, end.y_inches) + _GEOMETRY_EPSILON
    )


def _validate_unprefixed_identifier(
    field_name: str,
    value: object,
    *,
    reserved_prefix: str,
) -> str:
    identifier = _validate_identifier(field_name, value)
    if identifier.startswith(reserved_prefix):
        raise TerrainAreaError(f"{field_name} must not include the stable identity prefix.")
    return identifier


_validate_identifier = IdentifierValidator(TerrainAreaError)


def _validate_finite_number(field_name: str, value: object) -> float:
    if not isinstance(value, int | float) or type(value) is bool:
        raise TerrainAreaError(f"{field_name} must be a number.")
    number = float(value)
    if not math.isfinite(number):
        raise TerrainAreaError(f"{field_name} must be finite.")
    return number


def _validate_positive_number(field_name: str, value: object) -> float:
    number = _validate_finite_number(field_name, value)
    if number <= 0.0:
        raise TerrainAreaError(f"{field_name} must be greater than 0.")
    return number
