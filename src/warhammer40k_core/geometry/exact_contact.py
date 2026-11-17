"""Inactive finite disk-contact and full straight-segment clearance proofs.

Coordinates are exact inches; full diameters retain canonical integer ticks.
These geometric certificates are not engine PathWitness or gameplay admission.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from fractions import Fraction
from typing import Self, TypedDict, cast

from warhammer40k_core.geometry.exact_coordinate import (
    COORDINATE_REPRESENTATION_ID,
    CoordinatePayload,
    ExactCoordinate,
    ExactCoordinateError,
    UnsupportedExactCoordinateError,
    rational_coordinate,
)
from warhammer40k_core.geometry.milli_inch import DISTANCE_POLICY_ID
from warhammer40k_core.geometry.milli_inch_circle import MAX_DIAMETER_TICKS, CircleRelation

EXACT_DISK_SCHEMA = "exact-quadratic-disk-v1"
type ExactPoint = tuple[ExactCoordinate, ExactCoordinate]


class ExactDiskPayload(TypedDict):
    schema_version: str
    numerical_policy_id: str
    coordinate_representation_id: str
    center: list[CoordinatePayload]
    diameter_ticks: int


def _point(value: ExactPoint) -> None:
    if (
        type(value) is not tuple
        or len(value) != 2
        or any(type(v) is not ExactCoordinate for v in value)
    ):
        raise ExactCoordinateError("An exact point requires an immutable exact coordinate pair.")


def _squared(first: ExactPoint, second: ExactPoint) -> ExactCoordinate:
    x, y = first[0] - second[0], first[1] - second[1]
    return x * x + y * y


@dataclass(frozen=True, slots=True)
class ExactDisk:
    center: ExactPoint
    diameter_ticks: int

    def __post_init__(self) -> None:
        _point(self.center)
        if (
            type(self.diameter_ticks) is not int
            or not 1 <= self.diameter_ticks <= MAX_DIAMETER_TICKS
        ):
            raise ExactCoordinateError("A full diameter requires positive signed 64-bit ticks.")

    def relation_to(self, other: ExactDisk) -> CircleRelation:
        if type(other) is not ExactDisk:
            raise ExactCoordinateError("Exact disk queries require exact disks.")
        radius_sum = Fraction(self.diameter_ticks + other.diameter_ticks, 2000)
        sign = (_squared(self.center, other.center) - rational_coordinate(radius_sum**2)).sign()
        if sign > 0:
            return CircleRelation.SEPARATED
        if sign < 0:
            return CircleRelation.INTERIOR_OVERLAP
        return CircleRelation.EXTERNAL_CONTACT

    def to_payload(self) -> ExactDiskPayload:
        return {
            "schema_version": EXACT_DISK_SCHEMA,
            "numerical_policy_id": DISTANCE_POLICY_ID,
            "coordinate_representation_id": COORDINATE_REPRESENTATION_ID,
            "center": [coordinate.to_payload() for coordinate in self.center],
            "diameter_ticks": self.diameter_ticks,
        }

    @classmethod
    def from_payload(cls, payload: object) -> Self:
        if type(payload) is not dict:
            raise ExactCoordinateError("An exact disk payload must be an object.")
        data = cast(dict[str, object], payload)
        if set(data) != {
            "schema_version",
            "numerical_policy_id",
            "coordinate_representation_id",
            "center",
            "diameter_ticks",
        }:
            raise ExactCoordinateError("An exact disk payload requires the exact declared keys.")
        canonical = cast(ExactDiskPayload, data)
        if (
            canonical["schema_version"] != EXACT_DISK_SCHEMA
            or canonical["numerical_policy_id"] != DISTANCE_POLICY_ID
            or canonical["coordinate_representation_id"] != COORDINATE_REPRESENTATION_ID
            or type(canonical["center"]) is not list
            or len(canonical["center"]) != 2
        ):
            raise ExactCoordinateError("Unknown exact disk profile or malformed center.")
        return cls(
            (
                ExactCoordinate.from_payload(canonical["center"][0]),
                ExactCoordinate.from_payload(canonical["center"][1]),
            ),
            canonical["diameter_ticks"],
        )

    @property
    def content_hash(self) -> str:
        return hashlib.sha256(
            json.dumps(self.to_payload(), sort_keys=True, separators=(",", ":")).encode()
        ).hexdigest()


def squared_exact_inches_to_ticks(squared: ExactCoordinate) -> int:
    """Round a nonnegative exact squared length once using exact midpoint tests."""
    if type(squared) is not ExactCoordinate or squared.sign() < 0:
        raise ExactCoordinateError("A squared length must be a nonnegative exact coordinate value.")
    # The 256-bit component contract bounds this search; there is no solver or
    # unresolved result converted into an approximate length.
    low, high = 0, 1
    while squared.compare_rational(Fraction(2 * high + 1, 2000) ** 2) >= 0:
        high *= 2
    while low < high:
        middle = (low + high) // 2
        if squared.compare_rational(Fraction(2 * middle + 1, 2000) ** 2) >= 0:
            low = middle + 1
        else:
            high = middle
    return low


@dataclass(frozen=True, slots=True)
class StraightContactCertificate:
    start_hash: str
    end_hash: str
    coordinate_representation_id: str
    numerical_policy_id: str
    travel_ticks: int
    contacts: tuple[str, ...]


def rational_anchor_contact_centers(
    first: ExactDisk, second: ExactDisk, moving_diameter_ticks: int
) -> tuple[ExactDisk, ...]:
    """Construct zero, one or two exact simultaneous-contact centers.

    Anchors must have rational centers. Solutions are ordered by the positive
    then negative perpendicular to the first-to-second vector. Coincident
    anchors and nonrational anchors exceed this finite construction domain.
    Returned contacts still require full-path and every other legality proof.
    """
    if type(first) is not ExactDisk or type(second) is not ExactDisk:
        raise ExactCoordinateError("Contact construction requires exact anchor disks.")
    # Validate the moving dimension with the owning disk contract.
    ExactDisk(first.center, moving_diameter_ticks)
    if any(coordinate.root_sign for anchor in (first, second) for coordinate in anchor.center):
        raise UnsupportedExactCoordinateError(
            "Contact construction requires rational anchor centers."
        )
    ax, ay = (coordinate.rational for coordinate in first.center)
    bx, by = (coordinate.rational for coordinate in second.center)
    dx, dy = bx - ax, by - ay
    distance_squared = dx * dx + dy * dy
    if distance_squared == 0:
        raise UnsupportedExactCoordinateError("Coincident anchors are unsupported.")
    first_radius = Fraction(first.diameter_ticks + moving_diameter_ticks, 2000)
    second_radius = Fraction(second.diameter_ticks + moving_diameter_ticks, 2000)
    along = (first_radius**2 - second_radius**2 + distance_squared) / (2 * distance_squared)
    height_squared = first_radius**2 / distance_squared - along**2
    if height_squared < 0:
        return ()
    result: list[ExactDisk] = []
    for sign in (1,) if height_squared == 0 else (1, -1):
        result.append(
            ExactDisk(
                (
                    ExactCoordinate.from_root(ax + along * dx, -sign * dy, height_squared),
                    ExactCoordinate.from_root(ay + along * dy, sign * dx, height_squared),
                ),
                moving_diameter_ticks,
            )
        )
    return tuple(result)


def certify_straight_contact(
    start: ExactDisk, end: ExactDisk, obstacles: tuple[ExactDisk, ...]
) -> StraightContactCertificate:
    """Prove endpoint contacts and nonoverlap for *every* point of one segment.

    The minimum squared center distance to each stationary disk occurs at an
    endpoint or the exact projection parameter. Reject overlap anywhere, even
    when both endpoints are legal. All listed obstacles must be contacted at end.
    No terrain, phase, other models, or engine decision legality is established.
    """
    if (
        type(start) is not ExactDisk
        or type(end) is not ExactDisk
        or start.diameter_ticks != end.diameter_ticks
    ):
        raise ExactCoordinateError(
            "A straight certificate requires matching moving full diameters."
        )
    if (
        type(obstacles) is not tuple
        or not obstacles
        or any(type(v) is not ExactDisk for v in obstacles)
    ):
        raise ExactCoordinateError(
            "A straight certificate requires a nonempty immutable disk tuple."
        )
    vx, vy = end.center[0] - start.center[0], end.center[1] - start.center[1]
    length_squared = vx * vx + vy * vy
    zero, one = rational_coordinate(Fraction(0)), rational_coordinate(Fraction(1))
    for obstacle in obstacles:
        if end.relation_to(obstacle) is not CircleRelation.EXTERNAL_CONTACT:
            raise ExactCoordinateError(
                "The final disk must externally contact each stationary disk."
            )
        minimum = _squared(start.center, obstacle.center)
        if length_squared.sign() > 0:
            dx, dy = start.center[0] - obstacle.center[0], start.center[1] - obstacle.center[1]
            parameter = -(dx * vx + dy * vy) / length_squared
            if parameter.sign() <= 0:
                parameter = zero
            elif (parameter - one).sign() >= 0:
                parameter = one
            nearest = (start.center[0] + parameter * vx, start.center[1] + parameter * vy)
            minimum = _squared(nearest, obstacle.center)
        radius_sum = Fraction(start.diameter_ticks + obstacle.diameter_ticks, 2000)
        if (minimum - rational_coordinate(radius_sum**2)).sign() < 0:
            raise ExactCoordinateError("The straight segment overlaps a stationary disk.")
    return StraightContactCertificate(
        start.content_hash,
        end.content_hash,
        COORDINATE_REPRESENTATION_ID,
        DISTANCE_POLICY_ID,
        squared_exact_inches_to_ticks(length_squared),
        tuple(sorted(obstacle.content_hash for obstacle in obstacles)),
    )
