"""Canonical poses for the staged rational/quadratic coordinate representation."""

from __future__ import annotations

from dataclasses import dataclass
from fractions import Fraction
from typing import Self, TypedDict, cast

from warhammer40k_core.geometry.exact_coordinate import (
    COORDINATE_REPRESENTATION_ID,
    CoordinatePayload,
    ExactCoordinate,
    ExactCoordinateError,
    rational_coordinate,
)
from warhammer40k_core.geometry.milli_inch import DISTANCE_POLICY_ID

EXACT_POSE_VERSION = "exact-pose-v1"
_ZERO = rational_coordinate(Fraction(0))


class ExactPosePayload(TypedDict):
    version: str
    numerical_policy_id: str
    coordinate_representation_id: str
    x: CoordinatePayload
    y: CoordinatePayload
    z: CoordinatePayload
    facing_degrees: CoordinatePayload


@dataclass(frozen=True, slots=True)
class ExactPose:
    """Store authoritative coordinates in inches and a canonical rational facing."""

    x: ExactCoordinate
    y: ExactCoordinate
    z: ExactCoordinate = _ZERO
    facing_degrees: ExactCoordinate = _ZERO

    def __post_init__(self) -> None:
        if any(
            type(value) is not ExactCoordinate
            for value in (self.x, self.y, self.z, self.facing_degrees)
        ):
            raise ExactCoordinateError("An exact pose requires exact coordinates and facing.")
        if self.facing_degrees.root_sign or not 0 <= self.facing_degrees.rational < 360:
            raise ExactCoordinateError("Exact facing must be rational degrees in [0, 360).")

    def to_payload(self) -> ExactPosePayload:
        return {
            "version": EXACT_POSE_VERSION,
            "numerical_policy_id": DISTANCE_POLICY_ID,
            "coordinate_representation_id": COORDINATE_REPRESENTATION_ID,
            "x": self.x.to_payload(),
            "y": self.y.to_payload(),
            "z": self.z.to_payload(),
            "facing_degrees": self.facing_degrees.to_payload(),
        }

    @classmethod
    def from_payload(cls, payload: object) -> Self:
        if type(payload) is not dict:
            raise ExactCoordinateError("An exact pose payload must be an object.")
        data = cast(dict[str, object], payload)
        if (
            set(data)
            != {
                "version",
                "numerical_policy_id",
                "coordinate_representation_id",
                "x",
                "y",
                "z",
                "facing_degrees",
            }
            or data["version"] != EXACT_POSE_VERSION
            or data["numerical_policy_id"] != DISTANCE_POLICY_ID
            or data["coordinate_representation_id"] != COORDINATE_REPRESENTATION_ID
        ):
            raise ExactCoordinateError("Missing or incompatible exact pose identity or fields.")
        return cls(
            x=ExactCoordinate.from_payload(data["x"]),
            y=ExactCoordinate.from_payload(data["y"]),
            z=ExactCoordinate.from_payload(data["z"]),
            facing_degrees=ExactCoordinate.from_payload(data["facing_degrees"]),
        )
