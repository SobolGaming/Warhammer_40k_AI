from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
from typing import Self, TypedDict, cast

from warhammer40k_core.core.datasheet import BaseSizeDefinition, BaseSizeKind
from warhammer40k_core.geometry.base import BaseShape, CircularBase, OvalBase, RectangularBase
from warhammer40k_core.geometry.measurement import millimeters_to_inches
from warhammer40k_core.geometry.pose import GeometryError, validate_finite_number


class BaseFootprintKind(StrEnum):
    CIRCULAR = "circular"
    OVAL = "oval"
    RECTANGULAR = "rectangular"
    HULL = "hull"


class GeometrySourceKind(StrEnum):
    CATALOG_BASE_SIZE = "catalog_base_size"
    MANUAL_OVERRIDE = "manual_override"
    MANUAL_OVERRIDE_REQUIRED = "manual_override_required"


class HeightSourceKind(StrEnum):
    KEYWORD_HEURISTIC = "keyword_heuristic"
    FALLBACK_BASE_MINOR_DIAMETER = "fallback_base_minor_diameter"
    MANUAL_OVERRIDE = "manual_override"


class FootprintPartPayload(TypedDict):
    part_id: str
    footprint_kind: str
    radius_x_inches: float
    radius_y_inches: float
    offset_x_inches: float
    offset_y_inches: float


class ModelGeometryPayload(TypedDict):
    footprint_kind: str
    parts: list[FootprintPartPayload]
    height_inches: float
    geometry_source_kind: str
    geometry_source_id: str | None
    height_source_kind: str
    height_source_id: str | None


@dataclass(frozen=True, slots=True)
class FootprintPart:
    part_id: str
    footprint_kind: BaseFootprintKind
    radius_x_inches: float
    radius_y_inches: float
    offset_x_inches: float = 0.0
    offset_y_inches: float = 0.0

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "part_id",
            _validate_non_empty_string("FootprintPart part_id", self.part_id),
        )
        object.__setattr__(
            self,
            "footprint_kind",
            base_footprint_kind_from_token(self.footprint_kind),
        )
        object.__setattr__(
            self,
            "radius_x_inches",
            _validate_positive_inches("FootprintPart radius_x_inches", self.radius_x_inches),
        )
        object.__setattr__(
            self,
            "radius_y_inches",
            _validate_positive_inches("FootprintPart radius_y_inches", self.radius_y_inches),
        )
        object.__setattr__(
            self,
            "offset_x_inches",
            validate_finite_number("FootprintPart offset_x_inches", self.offset_x_inches),
        )
        object.__setattr__(
            self,
            "offset_y_inches",
            validate_finite_number("FootprintPart offset_y_inches", self.offset_y_inches),
        )
        if self.footprint_kind is BaseFootprintKind.CIRCULAR and (
            self.radius_x_inches != self.radius_y_inches
        ):
            raise GeometryError("Circular FootprintPart radii must match.")
        if self.footprint_kind is BaseFootprintKind.OVAL and (
            self.radius_x_inches < self.radius_y_inches
        ):
            raise GeometryError(
                "Oval FootprintPart radius_x_inches must be at least radius_y_inches."
            )

    def to_payload(self) -> FootprintPartPayload:
        return {
            "part_id": self.part_id,
            "footprint_kind": self.footprint_kind.value,
            "radius_x_inches": self.radius_x_inches,
            "radius_y_inches": self.radius_y_inches,
            "offset_x_inches": self.offset_x_inches,
            "offset_y_inches": self.offset_y_inches,
        }

    @classmethod
    def from_payload(cls, payload: FootprintPartPayload) -> Self:
        return cls(
            part_id=payload["part_id"],
            footprint_kind=base_footprint_kind_from_token(payload["footprint_kind"]),
            radius_x_inches=payload["radius_x_inches"],
            radius_y_inches=payload["radius_y_inches"],
            offset_x_inches=payload["offset_x_inches"],
            offset_y_inches=payload["offset_y_inches"],
        )


@dataclass(frozen=True, slots=True)
class ModelGeometry:
    footprint_kind: BaseFootprintKind
    parts: tuple[FootprintPart, ...]
    height_inches: float
    geometry_source_kind: GeometrySourceKind
    geometry_source_id: str | None
    height_source_kind: HeightSourceKind
    height_source_id: str | None

    def __post_init__(self) -> None:
        footprint_kind = base_footprint_kind_from_token(self.footprint_kind)
        object.__setattr__(self, "footprint_kind", footprint_kind)
        parts = _validate_footprint_parts(self.parts)
        if any(part.footprint_kind is not footprint_kind for part in parts):
            raise GeometryError("ModelGeometry parts must match footprint_kind.")
        object.__setattr__(self, "parts", parts)
        object.__setattr__(
            self,
            "height_inches",
            _validate_positive_inches("ModelGeometry height_inches", self.height_inches),
        )
        geometry_source_kind = geometry_source_kind_from_token(self.geometry_source_kind)
        geometry_source_id = _validate_optional_source_id(
            "ModelGeometry geometry_source_id",
            self.geometry_source_id,
        )
        if (
            geometry_source_kind is GeometrySourceKind.CATALOG_BASE_SIZE
            and geometry_source_id is None
        ):
            raise GeometryError("Catalog-derived geometry requires geometry_source_id.")
        object.__setattr__(
            self,
            "geometry_source_kind",
            geometry_source_kind,
        )
        object.__setattr__(self, "geometry_source_id", geometry_source_id)
        height_source_kind = height_source_kind_from_token(self.height_source_kind)
        height_source_id = _validate_optional_source_id(
            "ModelGeometry height_source_id",
            self.height_source_id,
        )
        if (
            height_source_kind
            in {
                HeightSourceKind.KEYWORD_HEURISTIC,
                HeightSourceKind.FALLBACK_BASE_MINOR_DIAMETER,
            }
            and height_source_id is None
        ):
            raise GeometryError("Resolved model height requires height_source_id.")
        object.__setattr__(
            self,
            "height_source_kind",
            height_source_kind,
        )
        object.__setattr__(self, "height_source_id", height_source_id)

    @classmethod
    def from_base_size(
        cls,
        base_size: BaseSizeDefinition,
        *,
        geometry_source_id: str,
        keywords: tuple[str, ...] = (),
    ) -> Self:
        if type(base_size) is not BaseSizeDefinition:
            raise GeometryError("base_size must be a BaseSizeDefinition.")
        part = _footprint_part_from_base_size(base_size)
        height_inches, height_source_kind, height_source_id = _resolve_height_from_keywords(
            keywords=keywords,
            minor_diameter_inches=part.radius_y_inches * 2.0,
        )
        return cls(
            footprint_kind=part.footprint_kind,
            parts=(part,),
            height_inches=height_inches,
            geometry_source_kind=GeometrySourceKind.CATALOG_BASE_SIZE,
            geometry_source_id=geometry_source_id,
            height_source_kind=height_source_kind,
            height_source_id=height_source_id,
        )

    def primary_part(self) -> FootprintPart:
        return self.parts[0]

    def base_shape(self) -> BaseShape:
        part = self.primary_part()
        if part.offset_x_inches != 0.0 or part.offset_y_inches != 0.0:
            raise GeometryError("Offset footprint parts do not have a single BaseShape.")
        if part.footprint_kind is BaseFootprintKind.CIRCULAR:
            return CircularBase(radius=part.radius_x_inches)
        if part.footprint_kind is BaseFootprintKind.OVAL:
            return OvalBase(length=part.radius_x_inches * 2.0, width=part.radius_y_inches * 2.0)
        return RectangularBase(length=part.radius_x_inches * 2.0, width=part.radius_y_inches * 2.0)

    def to_payload(self) -> ModelGeometryPayload:
        return {
            "footprint_kind": self.footprint_kind.value,
            "parts": [part.to_payload() for part in self.parts],
            "height_inches": self.height_inches,
            "geometry_source_kind": self.geometry_source_kind.value,
            "geometry_source_id": self.geometry_source_id,
            "height_source_kind": self.height_source_kind.value,
            "height_source_id": self.height_source_id,
        }

    @classmethod
    def from_payload(cls, payload: ModelGeometryPayload) -> Self:
        return cls(
            footprint_kind=base_footprint_kind_from_token(payload["footprint_kind"]),
            parts=tuple(FootprintPart.from_payload(part) for part in payload["parts"]),
            height_inches=payload["height_inches"],
            geometry_source_kind=geometry_source_kind_from_token(payload["geometry_source_kind"]),
            geometry_source_id=payload["geometry_source_id"],
            height_source_kind=height_source_kind_from_token(payload["height_source_kind"]),
            height_source_id=payload["height_source_id"],
        )


def base_footprint_kind_from_token(token: object) -> BaseFootprintKind:
    if type(token) is BaseFootprintKind:
        return token
    if type(token) is not str:
        raise GeometryError("BaseFootprintKind token must be a string.")
    try:
        return BaseFootprintKind(token)
    except ValueError as exc:
        raise GeometryError(f"Unsupported BaseFootprintKind token: {token}.") from exc


def geometry_source_kind_from_token(token: object) -> GeometrySourceKind:
    if type(token) is GeometrySourceKind:
        return token
    if type(token) is not str:
        raise GeometryError("GeometrySourceKind token must be a string.")
    try:
        return GeometrySourceKind(token)
    except ValueError as exc:
        raise GeometryError(f"Unsupported GeometrySourceKind token: {token}.") from exc


def height_source_kind_from_token(token: object) -> HeightSourceKind:
    if type(token) is HeightSourceKind:
        return token
    if type(token) is not str:
        raise GeometryError("HeightSourceKind token must be a string.")
    try:
        return HeightSourceKind(token)
    except ValueError as exc:
        raise GeometryError(f"Unsupported HeightSourceKind token: {token}.") from exc


def _footprint_part_from_base_size(base_size: BaseSizeDefinition) -> FootprintPart:
    if base_size.kind is BaseSizeKind.CIRCULAR:
        if base_size.diameter_mm is None:
            raise GeometryError("Circular BaseSizeDefinition must include diameter_mm.")
        radius_inches = millimeters_to_inches(base_size.diameter_mm) / 2.0
        return FootprintPart(
            part_id="base",
            footprint_kind=BaseFootprintKind.CIRCULAR,
            radius_x_inches=radius_inches,
            radius_y_inches=radius_inches,
        )
    if base_size.length_mm is None or base_size.width_mm is None:
        raise GeometryError("Non-circular BaseSizeDefinition must include length_mm and width_mm.")
    radius_x_inches = millimeters_to_inches(base_size.length_mm) / 2.0
    radius_y_inches = millimeters_to_inches(base_size.width_mm) / 2.0
    if base_size.kind is BaseSizeKind.OVAL:
        return FootprintPart(
            part_id="base",
            footprint_kind=BaseFootprintKind.OVAL,
            radius_x_inches=radius_x_inches,
            radius_y_inches=radius_y_inches,
        )
    return FootprintPart(
        part_id="base",
        footprint_kind=BaseFootprintKind.RECTANGULAR,
        radius_x_inches=radius_x_inches,
        radius_y_inches=radius_y_inches,
    )


def _resolve_height_from_keywords(
    *,
    keywords: tuple[str, ...],
    minor_diameter_inches: float,
) -> tuple[float, HeightSourceKind, str]:
    normalized_keywords = _normalize_keywords(keywords)
    if "aircraft" in normalized_keywords:
        return (
            minor_diameter_inches * 0.6,
            HeightSourceKind.KEYWORD_HEURISTIC,
            "keyword:aircraft",
        )
    if "monster" in normalized_keywords or "walker" in normalized_keywords:
        return (
            minor_diameter_inches * 1.55,
            HeightSourceKind.KEYWORD_HEURISTIC,
            "keyword:monster_or_walker",
        )
    if "vehicle" in normalized_keywords:
        return (
            minor_diameter_inches * 0.8,
            HeightSourceKind.KEYWORD_HEURISTIC,
            "keyword:vehicle",
        )
    if "beast" in normalized_keywords or "cavalry" in normalized_keywords:
        return (
            minor_diameter_inches * 1.1,
            HeightSourceKind.KEYWORD_HEURISTIC,
            "keyword:beast_or_cavalry",
        )
    if "infantry" in normalized_keywords or "character" in normalized_keywords:
        return (
            minor_diameter_inches * 1.4,
            HeightSourceKind.KEYWORD_HEURISTIC,
            "keyword:infantry_or_character",
        )
    return (
        minor_diameter_inches,
        HeightSourceKind.FALLBACK_BASE_MINOR_DIAMETER,
        "base_minor_diameter",
    )


def _normalize_keywords(keywords: object) -> frozenset[str]:
    if type(keywords) is not tuple:
        raise GeometryError("keywords must be a tuple.")
    normalized: set[str] = set()
    for keyword in cast(tuple[object, ...], keywords):
        normalized.add(_validate_non_empty_string("keyword", keyword).strip().lower())
    return frozenset(normalized)


def _validate_footprint_parts(parts: object) -> tuple[FootprintPart, ...]:
    if type(parts) is not tuple:
        raise GeometryError("ModelGeometry parts must be a tuple.")
    if not parts:
        raise GeometryError("ModelGeometry parts must not be empty.")
    validated: list[FootprintPart] = []
    seen: set[str] = set()
    for part in cast(tuple[object, ...], parts):
        if type(part) is not FootprintPart:
            raise GeometryError("ModelGeometry parts must contain FootprintPart values.")
        if part.part_id in seen:
            raise GeometryError("ModelGeometry parts must not contain duplicate part IDs.")
        seen.add(part.part_id)
        validated.append(part)
    return tuple(validated)


def _validate_positive_inches(field_name: str, value: object) -> float:
    inches = validate_finite_number(field_name, value)
    if inches <= 0.0:
        raise GeometryError(f"{field_name} must be greater than 0.")
    return inches


def _validate_optional_source_id(field_name: str, value: object) -> str | None:
    if value is None:
        return None
    return _validate_non_empty_string(field_name, value)


def _validate_non_empty_string(field_name: str, value: object) -> str:
    if type(value) is not str:
        raise GeometryError(f"{field_name} must be a string.")
    stripped = value.strip()
    if not stripped:
        raise GeometryError(f"{field_name} must not be empty.")
    return stripped
