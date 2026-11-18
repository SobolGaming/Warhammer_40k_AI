"""Complete exact paths for a single disk translating on a flat board."""

from __future__ import annotations

from dataclasses import dataclass, field
from fractions import Fraction
from itertools import pairwise
from typing import Self, TypedDict, cast

from warhammer40k_core.geometry.exact_contact import (
    ExactDisk,
    squared_exact_inches_to_ticks,
)
from warhammer40k_core.geometry.exact_coordinate import (
    COORDINATE_REPRESENTATION_ID,
    ExactCoordinate,
    ExactCoordinateError,
    UnsupportedExactCoordinateError,
    rational_coordinate,
)
from warhammer40k_core.geometry.exact_pose import ExactPose, ExactPosePayload
from warhammer40k_core.geometry.milli_inch import DISTANCE_POLICY_ID
from warhammer40k_core.geometry.milli_inch_circle import CircleRelation
from warhammer40k_core.geometry.milli_inch_symbolic import symbolic_squared_path_inches_to_ticks
from warhammer40k_core.geometry.validation import validate_identifier

EXACT_PATH_WITNESS_VERSION = "exact-path-witness-v1"


class ExactPathWitnessPayload(TypedDict):
    version: str
    numerical_policy_id: str
    coordinate_representation_id: str
    source_state_hash: str
    model_instance_id: str
    waypoints: list[ExactPosePayload]


@dataclass(frozen=True, slots=True)
class ExactDiskSweep:
    """A continuous linear translation of a disk between exact centers."""

    start: ExactDisk
    end: ExactDisk
    dx: ExactCoordinate = field(init=False)
    dy: ExactCoordinate = field(init=False)
    length_squared: ExactCoordinate = field(init=False)

    def __post_init__(self) -> None:
        if (
            type(self.start) is not ExactDisk
            or type(self.end) is not ExactDisk
            or self.start.diameter_ticks != self.end.diameter_ticks
        ):
            raise ExactCoordinateError("An exact disk sweep requires matching moving diameters.")
        dx = self.end.center[0] - self.start.center[0]
        dy = self.end.center[1] - self.start.center[1]
        object.__setattr__(self, "dx", dx)
        object.__setattr__(self, "dy", dy)
        object.__setattr__(self, "length_squared", dx * dx + dy * dy)

    def clears(self, obstacle: ExactDisk) -> bool:
        """Prove that the disk's interior never overlaps the stationary disk."""
        if type(obstacle) is not ExactDisk:
            raise ExactCoordinateError("Exact disk sweeps require exact stationary disks.")
        if self.length_squared.sign() == 0:
            return self.start.relation_to(obstacle) is not CircleRelation.INTERIOR_OVERLAP
        dx = self.start.center[0] - obstacle.center[0]
        dy = self.start.center[1] - obstacle.center[1]
        projection = -(dx * self.dx + dy * self.dy)
        if projection.sign() <= 0:
            return self.start.relation_to(obstacle) is not CircleRelation.INTERIOR_OVERLAP
        if (projection - self.length_squared).sign() >= 0:
            return self.end.relation_to(obstacle) is not CircleRelation.INTERIOR_OVERLAP
        # The closest point is in the interior. Compare squared perpendicular
        # distance after multiplying both sides by the squared segment length.
        cross = dx * self.dy - dy * self.dx
        radius_sum = Fraction(self.start.diameter_ticks + obstacle.diameter_ticks, 2000)
        scaled_radius = self.length_squared * rational_coordinate(radius_sum**2)
        return (cross * cross - scaled_radius).sign() >= 0


@dataclass(frozen=True, slots=True)
class ExactPathWitness:
    """The ordered vertices of a piecewise-linear path from a specific state."""

    source_state_hash: str
    model_instance_id: str
    waypoints: tuple[ExactPose, ...]

    def __post_init__(self) -> None:
        if (
            type(self.source_state_hash) is not str
            or len(self.source_state_hash) != 64
            or any(character not in "0123456789abcdef" for character in self.source_state_hash)
        ):
            raise ExactCoordinateError("Exact path witness requires a canonical source state hash.")
        if self.model_instance_id != validate_identifier(
            "Exact path model_instance_id",
            self.model_instance_id,
            error_factory=ExactCoordinateError,
            reject_object_repr=True,
        ):
            raise ExactCoordinateError("Exact path requires a canonical model identifier.")
        if (
            type(self.waypoints) is not tuple
            or len(self.waypoints) < 2
            or any(type(pose) is not ExactPose for pose in self.waypoints)
        ):
            raise ExactCoordinateError("Exact path witness requires at least two exact waypoints.")
        start = self.waypoints[0]
        if any(
            pose.z != start.z or pose.facing_degrees != start.facing_degrees
            for pose in self.waypoints[1:]
        ):
            raise UnsupportedExactCoordinateError("Exact paths require fixed elevation and facing.")

    def to_payload(self) -> ExactPathWitnessPayload:
        return {
            "version": EXACT_PATH_WITNESS_VERSION,
            "numerical_policy_id": DISTANCE_POLICY_ID,
            "coordinate_representation_id": COORDINATE_REPRESENTATION_ID,
            "source_state_hash": self.source_state_hash,
            "model_instance_id": self.model_instance_id,
            "waypoints": [pose.to_payload() for pose in self.waypoints],
        }

    @classmethod
    def from_payload(cls, payload: object) -> Self:
        if type(payload) is not dict:
            raise ExactCoordinateError("An exact path witness must be an object.")
        data = cast(dict[str, object], payload)
        if (
            set(data)
            != {
                "version",
                "numerical_policy_id",
                "coordinate_representation_id",
                "source_state_hash",
                "model_instance_id",
                "waypoints",
            }
            or data["version"] != EXACT_PATH_WITNESS_VERSION
            or data["numerical_policy_id"] != DISTANCE_POLICY_ID
            or data["coordinate_representation_id"] != COORDINATE_REPRESENTATION_ID
            or type(data["source_state_hash"]) is not str
            or type(data["model_instance_id"]) is not str
            or type(data["waypoints"]) is not list
        ):
            raise ExactCoordinateError("Missing or incompatible exact path identity or fields.")
        return cls(
            source_state_hash=data["source_state_hash"],
            model_instance_id=data["model_instance_id"],
            waypoints=tuple(
                ExactPose.from_payload(pose) for pose in cast(list[object], data["waypoints"])
            ),
        )

    def sweeps(self, diameter_ticks: int) -> tuple[ExactDiskSweep, ...]:
        disks = tuple(ExactDisk((pose.x, pose.y), diameter_ticks) for pose in self.waypoints)
        return tuple(ExactDiskSweep(start, end) for start, end in pairwise(disks))


def exact_path_travel_ticks(sweeps: tuple[ExactDiskSweep, ...]) -> int:
    """Round the full path once, with exact straight quadratic and rational-square support."""
    if (
        type(sweeps) is not tuple
        or not sweeps
        or any(type(segment) is not ExactDiskSweep for segment in sweeps)
    ):
        raise ExactCoordinateError("Exact travel requires a nonempty immutable tuple of sweeps.")
    if any(first.end != second.start for first, second in pairwise(sweeps)):
        raise ExactCoordinateError("Exact travel requires connected sweeps.")
    if len(sweeps) == 1:
        return squared_exact_inches_to_ticks(sweeps[0].length_squared)
    if all(segment.length_squared.root_sign == 0 for segment in sweeps):
        return symbolic_squared_path_inches_to_ticks(
            segment.length_squared.rational for segment in sweeps
        )

    # A forward subdivision of one segment has exactly the length of its
    # chord. Test every leg, so backtracking cannot be turned into a shortcut.
    whole = ExactDiskSweep(sweeps[0].start, sweeps[-1].end)
    if whole.length_squared.sign() > 0 and all(
        (whole.dx * segment.dy - whole.dy * segment.dx).sign() == 0
        and (whole.dx * segment.dx + whole.dy * segment.dy).sign() >= 0
        for segment in sweeps
    ):
        return squared_exact_inches_to_ticks(whole.length_squared)
    raise UnsupportedExactCoordinateError(
        "Bent paths with quadratic squared lengths are unsupported."
    )
