from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import Literal, Self, TypedDict, cast


class DeploymentZoneError(ValueError):
    """Raised when deployment-zone data violates CORE V2 invariants."""


class DeploymentZonePointPayload(TypedDict):
    x: float
    y: float


class DeploymentZonePolygonPayload(TypedDict):
    vertices: list[DeploymentZonePointPayload]


class DeploymentZoneCircleCutoutPayload(TypedDict):
    kind: Literal["circle"]
    center_x: float
    center_y: float
    radius: float


class DeploymentZonePolygonCutoutPayload(TypedDict):
    kind: Literal["polygon"]
    vertices: list[DeploymentZonePointPayload]


type DeploymentZoneCutoutPayload = (
    DeploymentZoneCircleCutoutPayload | DeploymentZonePolygonCutoutPayload
)


class DeploymentZoneShapePayload(TypedDict):
    polygons: list[DeploymentZonePolygonPayload]
    cutouts: list[DeploymentZoneCutoutPayload]


_EPSILON = 1e-9


@dataclass(frozen=True, slots=True)
class DeploymentZonePoint:
    x: float
    y: float

    def __post_init__(self) -> None:
        object.__setattr__(self, "x", _validate_finite_number("DeploymentZonePoint x", self.x))
        object.__setattr__(self, "y", _validate_finite_number("DeploymentZonePoint y", self.y))

    def to_payload(self) -> DeploymentZonePointPayload:
        return {"x": self.x, "y": self.y}

    @classmethod
    def from_payload(cls, payload: DeploymentZonePointPayload) -> Self:
        return cls(x=payload["x"], y=payload["y"])


@dataclass(frozen=True, slots=True)
class DeploymentZonePolygon:
    vertices: tuple[DeploymentZonePoint, ...]

    def __post_init__(self) -> None:
        if type(self.vertices) is not tuple:
            raise DeploymentZoneError("DeploymentZonePolygon vertices must be a tuple.")
        vertices = tuple(self.vertices)
        if len(vertices) < 3:
            raise DeploymentZoneError("DeploymentZonePolygon must have at least three vertices.")
        for vertex in vertices:
            if type(vertex) is not DeploymentZonePoint:
                raise DeploymentZoneError(
                    "DeploymentZonePolygon vertices must be DeploymentZonePoint values."
                )
        if _polygon_area(vertices) <= _EPSILON:
            raise DeploymentZoneError("DeploymentZonePolygon area must be greater than zero.")
        object.__setattr__(self, "vertices", vertices)

    def bounds(self) -> tuple[float, float, float, float]:
        x_values = tuple(vertex.x for vertex in self.vertices)
        y_values = tuple(vertex.y for vertex in self.vertices)
        return min(x_values), min(y_values), max(x_values), max(y_values)

    def contains_point(
        self,
        x: float,
        y: float,
        *,
        include_boundary: bool,
    ) -> bool:
        target_x = _validate_finite_number("x", x)
        target_y = _validate_finite_number("y", y)
        previous = self.vertices[-1]
        inside = False
        for current in self.vertices:
            if _point_on_segment(target_x, target_y, previous, current):
                return include_boundary
            crosses_ray = (current.y > target_y) != (previous.y > target_y)
            if crosses_ray:
                intersection_x = (previous.x - current.x) * (target_y - current.y) / (
                    previous.y - current.y
                ) + current.x
                if target_x < intersection_x:
                    inside = not inside
            previous = current
        return inside

    def to_payload(self) -> DeploymentZonePolygonPayload:
        return {"vertices": [vertex.to_payload() for vertex in self.vertices]}

    @classmethod
    def from_payload(cls, payload: DeploymentZonePolygonPayload) -> Self:
        return cls(
            vertices=tuple(
                DeploymentZonePoint.from_payload(vertex) for vertex in payload["vertices"]
            )
        )


@dataclass(frozen=True, slots=True)
class DeploymentZoneCircleCutout:
    center_x: float
    center_y: float
    radius: float

    def __post_init__(self) -> None:
        center_x = _validate_finite_number("DeploymentZoneCircleCutout center_x", self.center_x)
        center_y = _validate_finite_number("DeploymentZoneCircleCutout center_y", self.center_y)
        radius = _validate_finite_number("DeploymentZoneCircleCutout radius", self.radius)
        if radius <= 0.0:
            raise DeploymentZoneError(
                "DeploymentZoneCircleCutout radius must be greater than zero."
            )
        object.__setattr__(self, "center_x", center_x)
        object.__setattr__(self, "center_y", center_y)
        object.__setattr__(self, "radius", radius)

    def contains_point(
        self,
        x: float,
        y: float,
        *,
        include_boundary: bool,
    ) -> bool:
        target_x = _validate_finite_number("x", x)
        target_y = _validate_finite_number("y", y)
        distance_squared = (target_x - self.center_x) ** 2 + (target_y - self.center_y) ** 2
        radius_squared = self.radius**2
        if include_boundary:
            return distance_squared <= radius_squared + _EPSILON
        return distance_squared < radius_squared - _EPSILON

    def to_payload(self) -> DeploymentZoneCircleCutoutPayload:
        return {
            "kind": "circle",
            "center_x": self.center_x,
            "center_y": self.center_y,
            "radius": self.radius,
        }

    @classmethod
    def from_payload(cls, payload: DeploymentZoneCircleCutoutPayload) -> Self:
        return cls(
            center_x=payload["center_x"],
            center_y=payload["center_y"],
            radius=payload["radius"],
        )


@dataclass(frozen=True, slots=True)
class DeploymentZonePolygonCutout:
    vertices: tuple[DeploymentZonePoint, ...]
    _polygon: DeploymentZonePolygon = field(init=False, repr=False)

    def __post_init__(self) -> None:
        polygon = DeploymentZonePolygon(vertices=self.vertices)
        object.__setattr__(self, "vertices", polygon.vertices)
        object.__setattr__(self, "_polygon", polygon)

    def contains_point(
        self,
        x: float,
        y: float,
        *,
        include_boundary: bool,
    ) -> bool:
        return self._polygon.contains_point(x, y, include_boundary=include_boundary)

    def to_payload(self) -> DeploymentZonePolygonCutoutPayload:
        return {
            "kind": "polygon",
            "vertices": [vertex.to_payload() for vertex in self.vertices],
        }

    @classmethod
    def from_payload(cls, payload: DeploymentZonePolygonCutoutPayload) -> Self:
        return cls(
            vertices=tuple(
                DeploymentZonePoint.from_payload(vertex) for vertex in payload["vertices"]
            )
        )


type DeploymentZoneCutout = DeploymentZoneCircleCutout | DeploymentZonePolygonCutout


class DeploymentZonePayload(TypedDict):
    deployment_zone_id: str
    player_id: str
    shape: DeploymentZoneShapePayload


@dataclass(frozen=True, slots=True)
class DeploymentZoneShape:
    polygons: tuple[DeploymentZonePolygon, ...]
    cutouts: tuple[DeploymentZoneCutout, ...] = ()

    def __post_init__(self) -> None:
        if type(self.polygons) is not tuple:
            raise DeploymentZoneError("DeploymentZoneShape polygons must be a tuple.")
        if type(self.cutouts) is not tuple:
            raise DeploymentZoneError("DeploymentZoneShape cutouts must be a tuple.")
        polygons = tuple(self.polygons)
        cutouts = tuple(self.cutouts)
        if not polygons:
            raise DeploymentZoneError("DeploymentZoneShape must include at least one polygon.")
        for polygon in polygons:
            if type(polygon) is not DeploymentZonePolygon:
                raise DeploymentZoneError(
                    "DeploymentZoneShape polygons must be DeploymentZonePolygon values."
                )
        for cutout in cutouts:
            if type(cutout) not in (DeploymentZoneCircleCutout, DeploymentZonePolygonCutout):
                raise DeploymentZoneError(
                    "DeploymentZoneShape cutouts must be deployment-zone cutout values."
                )
        object.__setattr__(self, "polygons", polygons)
        object.__setattr__(self, "cutouts", cutouts)

    @classmethod
    def rectangle(
        cls,
        *,
        min_x: float,
        min_y: float,
        max_x: float,
        max_y: float,
    ) -> Self:
        valid_min_x = _validate_finite_number("DeploymentZone rectangle min_x", min_x)
        valid_min_y = _validate_finite_number("DeploymentZone rectangle min_y", min_y)
        valid_max_x = _validate_finite_number("DeploymentZone rectangle max_x", max_x)
        valid_max_y = _validate_finite_number("DeploymentZone rectangle max_y", max_y)
        if valid_min_x >= valid_max_x:
            raise DeploymentZoneError("DeploymentZone rectangle min_x must be less than max_x.")
        if valid_min_y >= valid_max_y:
            raise DeploymentZoneError("DeploymentZone rectangle min_y must be less than max_y.")
        return cls(
            polygons=(
                DeploymentZonePolygon(
                    vertices=(
                        DeploymentZonePoint(valid_min_x, valid_min_y),
                        DeploymentZonePoint(valid_max_x, valid_min_y),
                        DeploymentZonePoint(valid_max_x, valid_max_y),
                        DeploymentZonePoint(valid_min_x, valid_max_y),
                    )
                ),
            )
        )

    def bounds(self) -> tuple[float, float, float, float]:
        polygon_bounds = tuple(polygon.bounds() for polygon in self.polygons)
        return (
            min(bounds[0] for bounds in polygon_bounds),
            min(bounds[1] for bounds in polygon_bounds),
            max(bounds[2] for bounds in polygon_bounds),
            max(bounds[3] for bounds in polygon_bounds),
        )

    def contains_point(self, x: float, y: float) -> bool:
        target_x = _validate_finite_number("x", x)
        target_y = _validate_finite_number("y", y)
        if not any(
            polygon.contains_point(target_x, target_y, include_boundary=True)
            for polygon in self.polygons
        ):
            return False
        return not any(
            cutout.contains_point(target_x, target_y, include_boundary=False)
            for cutout in self.cutouts
        )

    def to_payload(self) -> DeploymentZoneShapePayload:
        return {
            "polygons": [polygon.to_payload() for polygon in self.polygons],
            "cutouts": [_cutout_to_payload(cutout) for cutout in self.cutouts],
        }

    @classmethod
    def from_payload(cls, payload: DeploymentZoneShapePayload) -> Self:
        return cls(
            polygons=tuple(
                DeploymentZonePolygon.from_payload(polygon) for polygon in payload["polygons"]
            ),
            cutouts=tuple(_cutout_from_payload(cutout) for cutout in payload["cutouts"]),
        )


@dataclass(frozen=True, slots=True)
class DeploymentZone:
    deployment_zone_id: str
    player_id: str
    shape: DeploymentZoneShape
    min_x: float = field(init=False)
    min_y: float = field(init=False)
    max_x: float = field(init=False)
    max_y: float = field(init=False)

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "deployment_zone_id",
            _validate_deployment_zone_id(self.deployment_zone_id),
        )
        object.__setattr__(self, "player_id", _validate_identifier("player_id", self.player_id))
        if type(self.shape) is not DeploymentZoneShape:
            raise DeploymentZoneError("DeploymentZone shape must be a DeploymentZoneShape.")
        min_x, min_y, max_x, max_y = self.shape.bounds()
        if min_x >= max_x:
            raise DeploymentZoneError("DeploymentZone shape min_x must be less than max_x.")
        if min_y >= max_y:
            raise DeploymentZoneError("DeploymentZone shape min_y must be less than max_y.")
        object.__setattr__(self, "min_x", min_x)
        object.__setattr__(self, "min_y", min_y)
        object.__setattr__(self, "max_x", max_x)
        object.__setattr__(self, "max_y", max_y)

    @classmethod
    def rectangle(
        cls,
        deployment_zone_id: str,
        player_id: str,
        *,
        min_x: float,
        min_y: float,
        max_x: float,
        max_y: float,
    ) -> Self:
        return cls(
            deployment_zone_id=deployment_zone_id,
            player_id=player_id,
            shape=DeploymentZoneShape.rectangle(
                min_x=min_x,
                min_y=min_y,
                max_x=max_x,
                max_y=max_y,
            ),
        )

    def stable_identity(self) -> str:
        return f"deployment-zone:{self.deployment_zone_id}"

    def contains_point(self, x: float, y: float) -> bool:
        return self.shape.contains_point(x, y)

    def with_player_id(self, player_id: str) -> Self:
        return type(self)(
            deployment_zone_id=self.deployment_zone_id,
            player_id=player_id,
            shape=self.shape,
        )

    def to_payload(self) -> DeploymentZonePayload:
        return {
            "deployment_zone_id": self.deployment_zone_id,
            "player_id": self.player_id,
            "shape": self.shape.to_payload(),
        }

    @classmethod
    def from_payload(cls, payload: DeploymentZonePayload) -> Self:
        return cls(
            deployment_zone_id=payload["deployment_zone_id"],
            player_id=payload["player_id"],
            shape=DeploymentZoneShape.from_payload(payload["shape"]),
        )


def _cutout_to_payload(cutout: DeploymentZoneCutout) -> DeploymentZoneCutoutPayload:
    if type(cutout) is DeploymentZoneCircleCutout:
        return cutout.to_payload()
    if type(cutout) is DeploymentZonePolygonCutout:
        return cutout.to_payload()
    raise DeploymentZoneError("Unsupported deployment-zone cutout type.")


def _cutout_from_payload(payload: DeploymentZoneCutoutPayload) -> DeploymentZoneCutout:
    kind = payload["kind"]
    if kind == "circle":
        return DeploymentZoneCircleCutout.from_payload(
            cast(DeploymentZoneCircleCutoutPayload, payload)
        )
    if kind == "polygon":
        return DeploymentZonePolygonCutout.from_payload(
            cast(DeploymentZonePolygonCutoutPayload, payload)
        )
    raise DeploymentZoneError(f"Unsupported deployment-zone cutout kind: {kind}.")


def _polygon_area(vertices: tuple[DeploymentZonePoint, ...]) -> float:
    previous = vertices[-1]
    area = 0.0
    for current in vertices:
        area += previous.x * current.y - current.x * previous.y
        previous = current
    return abs(area) / 2.0


def _point_on_segment(
    target_x: float,
    target_y: float,
    first: DeploymentZonePoint,
    second: DeploymentZonePoint,
) -> bool:
    cross_product = (target_y - first.y) * (second.x - first.x) - (target_x - first.x) * (
        second.y - first.y
    )
    if not math.isclose(cross_product, 0.0, rel_tol=0.0, abs_tol=_EPSILON):
        return False
    min_x = min(first.x, second.x) - _EPSILON
    max_x = max(first.x, second.x) + _EPSILON
    min_y = min(first.y, second.y) - _EPSILON
    max_y = max(first.y, second.y) + _EPSILON
    return min_x <= target_x <= max_x and min_y <= target_y <= max_y


def _validate_identifier(field_name: str, value: object) -> str:
    if type(value) is not str:
        raise DeploymentZoneError(f"{field_name} must be a string.")
    stripped = value.strip()
    if not stripped:
        raise DeploymentZoneError(f"{field_name} must not be empty.")
    return stripped


def _validate_deployment_zone_id(value: object) -> str:
    identifier = _validate_identifier("DeploymentZone deployment_zone_id", value)
    if identifier.startswith("deployment-zone:"):
        raise DeploymentZoneError(
            "DeploymentZone deployment_zone_id must not include the stable identity prefix."
        )
    return identifier


def _validate_finite_number(field_name: str, value: object) -> float:
    if not isinstance(value, int | float) or type(value) is bool:
        raise DeploymentZoneError(f"{field_name} must be a number.")
    number = float(value)
    if not math.isfinite(number):
        raise DeploymentZoneError(f"{field_name} must be finite.")
    return number
