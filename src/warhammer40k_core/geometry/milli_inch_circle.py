"""Inactive canonical disks: exact topology and final-only surface-gap rounding.

Tick-grid centres are input geometry, not a contact-placement solution. In
particular, circles with different diameter parity cannot be externally tangent
on this grid. No gameplay, solver or backend consumes this representation yet.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from enum import StrEnum
from fractions import Fraction
from math import isqrt
from typing import Self, TypedDict, cast

from warhammer40k_core.geometry.milli_inch import (
    DISTANCE_POLICY_ID,
    DistancePrecisionError,
    DistanceSource,
    inches_to_ticks,
    millimeters_to_ticks,
    radius_inches_from_diameter_ticks,
)

CIRCLE_SCHEMA = "milli-inch-circle-v1"
MIN_CENTER_TICKS = -(2**63)
MAX_CENTER_TICKS = 2**63 - 1
MAX_DIAMETER_TICKS = 2**63 - 1


class CanonicalCircleError(DistancePrecisionError):
    """The circle input or serialized representation is invalid."""


class CircleRelation(StrEnum):
    SEPARATED = "separated"
    EXTERNAL_CONTACT = "external_contact"
    INTERIOR_OVERLAP = "interior_overlap"


class CanonicalCirclePayload(TypedDict):
    schema_version: str
    numerical_policy_id: str
    center: list[int]
    diameter_ticks: int


@dataclass(frozen=True, slots=True)
class CanonicalCircle:
    center: tuple[int, int]
    diameter_ticks: int

    def __post_init__(self) -> None:
        if (
            type(self.center) is not tuple
            or len(self.center) != 2
            or any(type(coordinate) is not int for coordinate in self.center)
        ):
            raise CanonicalCircleError(
                "A canonical center requires an immutable integer tick pair."
            )
        if any(not MIN_CENTER_TICKS <= value <= MAX_CENTER_TICKS for value in self.center):
            raise CanonicalCircleError("Canonical center coordinates must fit signed 64-bit ticks.")
        if (
            type(self.diameter_ticks) is not int
            or not 1 <= self.diameter_ticks <= MAX_DIAMETER_TICKS
        ):
            raise CanonicalCircleError(
                "A canonical diameter requires positive signed 64-bit ticks."
            )

    @classmethod
    def from_inches(cls, *, x: DistanceSource, y: DistanceSource, diameter: DistanceSource) -> Self:
        return cls((inches_to_ticks(x), inches_to_ticks(y)), inches_to_ticks(diameter))

    @classmethod
    def from_millimeters(
        cls, *, x: DistanceSource, y: DistanceSource, diameter: DistanceSource
    ) -> Self:
        return cls(
            (millimeters_to_ticks(x), millimeters_to_ticks(y)), millimeters_to_ticks(diameter)
        )

    @property
    def radius_inches(self) -> Fraction:
        """Derive the radius from the full diameter without a second quantization."""
        return radius_inches_from_diameter_ticks(self.diameter_ticks)

    def relation_to(self, other: CanonicalCircle) -> CircleRelation:
        """Classify closed disks; containment and internal tangency overlap interiors."""
        squared_distance = self._squared_center_distance(other)
        diameter_sum = self.diameter_ticks + other.diameter_ticks
        difference = 4 * squared_distance - diameter_sum**2
        if difference > 0:
            return CircleRelation.SEPARATED
        if difference == 0:
            return CircleRelation.EXTERNAL_CONTACT
        return CircleRelation.INTERIOR_OVERLAP

    def surface_gap_ticks(self, other: CanonicalCircle) -> int:
        """Quantize max(0, centre distance - radii sum) once, using exact squares.

        A zero result does not establish contact or exclude overlap. For disjoint
        disks, integer square root locates the gap's floor even for half-tick
        radii, then a squared midpoint comparison implements half-away rounding.
        No centre distance or radius is rounded before the final gap.
        """
        squared_distance = self._squared_center_distance(other)
        diameter_sum = self.diameter_ticks + other.diameter_ticks
        if 4 * squared_distance <= diameter_sum**2:
            return 0
        lower = (isqrt(4 * squared_distance) - diameter_sum) // 2
        return lower + int(4 * squared_distance >= (diameter_sum + 2 * lower + 1) ** 2)

    def _squared_center_distance(self, other: CanonicalCircle) -> int:
        if not isinstance(cast(object, other), CanonicalCircle):
            raise CanonicalCircleError("Circle queries require a canonical circle.")
        return (self.center[0] - other.center[0]) ** 2 + (self.center[1] - other.center[1]) ** 2

    def to_payload(self) -> CanonicalCirclePayload:
        return {
            "schema_version": CIRCLE_SCHEMA,
            "numerical_policy_id": DISTANCE_POLICY_ID,
            "center": list(self.center),
            "diameter_ticks": self.diameter_ticks,
        }

    @classmethod
    def from_payload(cls, payload: object) -> Self:
        if type(payload) is not dict:
            raise CanonicalCircleError("A canonical circle payload must be an object.")
        value = cast(dict[object, object], payload)
        if (
            set(value) != {"schema_version", "numerical_policy_id", "center", "diameter_ticks"}
            or type(value["schema_version"]) is not str
            or type(value["numerical_policy_id"]) is not str
            or value["schema_version"] != CIRCLE_SCHEMA
            or value["numerical_policy_id"] != DISTANCE_POLICY_ID
        ):
            raise CanonicalCircleError("Canonical circle schema or numerical policy drifted.")
        center = value["center"]
        if type(center) is not list:
            raise CanonicalCircleError("A canonical center payload requires an integer tick pair.")
        pair = cast(list[object], center)
        if len(pair) != 2 or any(type(coordinate) is not int for coordinate in pair):
            raise CanonicalCircleError("A canonical center payload requires an integer tick pair.")
        diameter = value["diameter_ticks"]
        if type(diameter) is not int:
            raise CanonicalCircleError("A canonical diameter payload requires integer ticks.")
        return cls((cast(int, pair[0]), cast(int, pair[1])), diameter)

    @property
    def content_hash(self) -> str:
        raw = json.dumps(self.to_payload(), sort_keys=True, separators=(",", ":")).encode()
        return hashlib.sha256(raw).hexdigest()
