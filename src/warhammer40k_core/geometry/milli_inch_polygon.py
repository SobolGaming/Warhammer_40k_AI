"""Inactive exact simple-ring input boundary; no gameplay or contact admission.

Source and snapped rings must both be simple. Vertex order, winding and starting
vertex are retained as identity, never repaired or normalized. Holes, rotations,
backend conversion and off-grid contact placements are outside this representation.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from fractions import Fraction
from typing import Self, TypedDict, cast

from warhammer40k_core.geometry.milli_inch import (
    DISTANCE_POLICY_ID,
    DistancePrecisionError,
    DistanceSource,
    _exact_value,  # pyright: ignore[reportPrivateUsage]
    inches_to_ticks,
    millimeters_to_ticks,
)

POLYGON_SCHEMA = "milli-inch-simple-ring-v1"
MIN_COORDINATE_TICKS = -(2**63)
MAX_COORDINATE_TICKS = 2**63 - 1
type TickVertex = tuple[int, int]
type ExactVertex = tuple[Fraction, Fraction]
type SourceRing = tuple[tuple[DistanceSource, DistanceSource], ...]


class CanonicalPolygonError(DistancePrecisionError):
    """A source, canonical ring or serialized representation is invalid."""


class CanonicalPolygonPayload(TypedDict):
    schema_version: str
    numerical_policy_id: str
    vertices: list[list[int]]


@dataclass(frozen=True, slots=True)
class CanonicalPolygon:
    vertices: tuple[TickVertex, ...]

    def __post_init__(self) -> None:
        if type(self.vertices) is not tuple or any(
            type(vertex) is not tuple
            or len(vertex) != 2
            or any(type(coordinate) is not int for coordinate in vertex)
            for vertex in self.vertices
        ):
            raise CanonicalPolygonError("Canonical vertices require immutable integer tick pairs.")
        if any(
            not MIN_COORDINATE_TICKS <= coordinate <= MAX_COORDINATE_TICKS
            for vertex in self.vertices
            for coordinate in vertex
        ):
            raise CanonicalPolygonError("Canonical coordinates must fit signed 64-bit ticks.")
        _validate_ring(tuple((Fraction(x), Fraction(y)) for x, y in self.vertices))

    @classmethod
    def from_inches(cls, vertices: SourceRing) -> Self:
        return cls._from_source(vertices, millimeters=False)

    @classmethod
    def from_millimeters(cls, vertices: SourceRing) -> Self:
        return cls._from_source(vertices, millimeters=True)

    @classmethod
    def _from_source(cls, vertices: SourceRing, *, millimeters: bool) -> Self:
        if type(vertices) is not tuple or any(
            type(vertex) is not tuple or len(vertex) != 2 for vertex in vertices
        ):
            raise CanonicalPolygonError("Source ring requires a tuple of coordinate pairs.")
        source = tuple((_exact_value(x), _exact_value(y)) for x, y in vertices)
        source_area = _validate_ring(source)
        quantize = millimeters_to_ticks if millimeters else inches_to_ticks
        result = cls(tuple((quantize(x), quantize(y)) for x, y in source))
        canonical_area = _signed_area(tuple((Fraction(x), Fraction(y)) for x, y in result.vertices))
        if (source_area > 0) != (canonical_area > 0):
            raise CanonicalPolygonError("Canonicalization reversed the source ring winding.")
        return result

    def to_payload(self) -> CanonicalPolygonPayload:
        return {
            "schema_version": POLYGON_SCHEMA,
            "numerical_policy_id": DISTANCE_POLICY_ID,
            "vertices": [[x, y] for x, y in self.vertices],
        }

    @classmethod
    def from_payload(cls, payload: object) -> Self:
        if type(payload) is not dict:
            raise CanonicalPolygonError("Canonical polygon payload must be an object.")
        value = cast(dict[object, object], payload)
        if (
            set(value) != {"schema_version", "numerical_policy_id", "vertices"}
            or type(value["schema_version"]) is not str
            or type(value["numerical_policy_id"]) is not str
            or value["schema_version"] != POLYGON_SCHEMA
            or value["numerical_policy_id"] != DISTANCE_POLICY_ID
        ):
            raise CanonicalPolygonError("Canonical polygon schema or numerical policy drifted.")
        vertices = value["vertices"]
        if type(vertices) is not list:
            raise CanonicalPolygonError("Canonical payload requires integer tick pairs.")
        decoded: list[TickVertex] = []
        for vertex in cast(list[object], vertices):
            if type(vertex) is not list:
                raise CanonicalPolygonError("Canonical payload requires integer tick pairs.")
            pair = cast(list[object], vertex)
            if len(pair) != 2 or any(type(coordinate) is not int for coordinate in pair):
                raise CanonicalPolygonError("Canonical payload requires integer tick pairs.")
            decoded.append((cast(int, pair[0]), cast(int, pair[1])))
        return cls(tuple(decoded))

    @property
    def content_hash(self) -> str:
        """Policy/version-bound identity; ring start and winding remain significant."""
        raw = json.dumps(self.to_payload(), sort_keys=True, separators=(",", ":")).encode()
        return hashlib.sha256(raw).hexdigest()


def _cross(a: ExactVertex, b: ExactVertex, c: ExactVertex) -> Fraction:
    return (b[0] - a[0]) * (c[1] - a[1]) - (b[1] - a[1]) * (c[0] - a[0])


def _signed_area(vertices: tuple[ExactVertex, ...]) -> Fraction:
    return sum(
        (
            a[0] * b[1] - a[1] * b[0]
            for a, b in zip(vertices, (*vertices[1:], vertices[0]), strict=True)
        ),
        Fraction(0),
    )


def _on_segment(a: ExactVertex, b: ExactVertex, point: ExactVertex) -> bool:
    return (
        _cross(a, b, point) == 0
        and min(a[0], b[0]) <= point[0] <= max(a[0], b[0])
        and min(a[1], b[1]) <= point[1] <= max(a[1], b[1])
    )


def _intersects(a: ExactVertex, b: ExactVertex, c: ExactVertex, d: ExactVertex) -> bool:
    return (
        (_cross(a, b, c) * _cross(a, b, d) < 0 and _cross(c, d, a) * _cross(c, d, b) < 0)
        or _on_segment(a, b, c)
        or _on_segment(a, b, d)
        or _on_segment(c, d, a)
        or _on_segment(c, d, b)
    )


def _validate_ring(vertices: tuple[ExactVertex, ...]) -> Fraction:
    if len(vertices) < 3 or len(set(vertices)) != len(vertices):
        raise CanonicalPolygonError("A simple ring needs at least three distinct vertices.")
    area = _signed_area(vertices)
    if area == 0:
        raise CanonicalPolygonError("A simple ring must have nonzero signed area.")
    count = len(vertices)
    for index, current in enumerate(vertices):
        previous, following = vertices[index - 1], vertices[(index + 1) % count]
        if _cross(previous, current, following) == 0 and (
            (current[0] - previous[0]) * (following[0] - current[0])
            + (current[1] - previous[1]) * (following[1] - current[1])
            < 0
        ):
            raise CanonicalPolygonError("Adjacent ring edges must not backtrack or overlap.")
        for other in range(index + 1, count):
            if other == index + 1 or (index == 0 and other == count - 1):
                continue
            if _intersects(current, following, vertices[other], vertices[(other + 1) % count]):
                raise CanonicalPolygonError("Nonadjacent ring edges must not intersect or touch.")
    return area
