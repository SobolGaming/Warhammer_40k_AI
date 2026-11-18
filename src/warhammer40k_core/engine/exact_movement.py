"""Engine-owned exact placement and movement on the staged flat disk battlefield.

Live lifecycle sessions still use the admitted legacy battlefield state.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, replace
from fractions import Fraction
from itertools import combinations
from typing import Self, TypedDict, cast

from warhammer40k_core.core.validation import validate_identifier
from warhammer40k_core.geometry.exact_contact import ExactDisk
from warhammer40k_core.geometry.exact_coordinate import (
    COORDINATE_REPRESENTATION_ID,
    ExactCoordinateError,
    UnsupportedExactCoordinateError,
)
from warhammer40k_core.geometry.exact_path import ExactPathWitness, exact_path_travel_ticks
from warhammer40k_core.geometry.exact_pose import ExactPose, ExactPosePayload
from warhammer40k_core.geometry.milli_inch import DISTANCE_POLICY_ID
from warhammer40k_core.geometry.milli_inch_circle import MAX_DIAMETER_TICKS, CircleRelation

EXACT_BATTLEFIELD_VERSION = "exact-disk-battlefield-v1"


class ExactMovementError(ExactCoordinateError):
    """The supplied witness does not authorize an exact state transition."""


class ExactModelPlacementPayload(TypedDict):
    model_instance_id: str
    diameter_ticks: int
    pose: ExactPosePayload


class ExactBattlefieldPayload(TypedDict):
    version: str
    numerical_policy_id: str
    coordinate_representation_id: str
    width_ticks: int
    depth_ticks: int
    placements: list[ExactModelPlacementPayload]


@dataclass(frozen=True, slots=True)
class ExactModelPlacement:
    model_instance_id: str
    diameter_ticks: int
    pose: ExactPose

    def __post_init__(self) -> None:
        if self.model_instance_id != validate_identifier(
            "Exact placement model_instance_id",
            self.model_instance_id,
            error_factory=ExactMovementError,
            reject_object_repr=True,
        ):
            raise ExactMovementError("Exact placement requires a canonical model identifier.")
        if type(self.pose) is not ExactPose:
            raise ExactMovementError("Exact placement requires an ExactPose.")
        if self.pose.z.sign():
            raise UnsupportedExactCoordinateError("The exact disk battlefield requires z = 0.")
        if (
            type(self.diameter_ticks) is not int
            or not 1 <= self.diameter_ticks <= MAX_DIAMETER_TICKS
        ):
            raise ExactMovementError("A full diameter requires positive signed 64-bit ticks.")

    @property
    def disk(self) -> ExactDisk:
        return ExactDisk((self.pose.x, self.pose.y), self.diameter_ticks)

    def to_payload(self) -> ExactModelPlacementPayload:
        return {
            "model_instance_id": self.model_instance_id,
            "diameter_ticks": self.diameter_ticks,
            "pose": self.pose.to_payload(),
        }

    @classmethod
    def from_payload(cls, payload: object) -> Self:
        if type(payload) is not dict:
            raise ExactMovementError("An exact placement must be an object.")
        data = cast(dict[str, object], payload)
        if (
            set(data) != {"model_instance_id", "diameter_ticks", "pose"}
            or type(data["model_instance_id"]) is not str
            or type(data["diameter_ticks"]) is not int
        ):
            raise ExactMovementError("Malformed exact placement fields.")
        return cls(
            model_instance_id=data["model_instance_id"],
            diameter_ticks=data["diameter_ticks"],
            pose=ExactPose.from_payload(data["pose"]),
        )


def _check_board_footprint(disk: ExactDisk, width_ticks: int, depth_ticks: int) -> None:
    radius = Fraction(disk.diameter_ticks, 2000)
    for coordinate, limit in zip(disk.center, (width_ticks, depth_ticks), strict=True):
        if (
            coordinate.compare_rational(radius) < 0
            or coordinate.compare_rational(Fraction(limit, 1000) - radius) > 0
        ):
            raise ExactMovementError("An exact disk footprint leaves the battlefield.")


@dataclass(frozen=True, slots=True)
class ExactBattlefieldState:
    """Authoritative exact poses ordered by unique physical model identifier."""

    width_ticks: int
    depth_ticks: int
    placements: tuple[ExactModelPlacement, ...]

    def __post_init__(self) -> None:
        if any(
            type(extent) is not int or not 1 <= extent <= MAX_DIAMETER_TICKS
            for extent in (self.width_ticks, self.depth_ticks)
        ):
            raise ExactMovementError(
                "Exact battlefield extents require positive signed 64-bit ticks."
            )
        if type(self.placements) is not tuple or any(
            type(placement) is not ExactModelPlacement for placement in self.placements
        ):
            raise ExactMovementError("Exact battlefield requires immutable exact placements.")
        identifiers = tuple(placement.model_instance_id for placement in self.placements)
        if identifiers != tuple(sorted(set(identifiers))):
            raise ExactMovementError("Exact placements must have unique model IDs in sorted order.")
        disks = tuple(placement.disk for placement in self.placements)
        for disk in disks:
            _check_board_footprint(disk, self.width_ticks, self.depth_ticks)
        if any(
            first.relation_to(second) is CircleRelation.INTERIOR_OVERLAP
            for first, second in combinations(disks, 2)
        ):
            raise ExactMovementError("The exact battlefield contains overlapping disk interiors.")

    def to_payload(self) -> ExactBattlefieldPayload:
        return {
            "version": EXACT_BATTLEFIELD_VERSION,
            "numerical_policy_id": DISTANCE_POLICY_ID,
            "coordinate_representation_id": COORDINATE_REPRESENTATION_ID,
            "width_ticks": self.width_ticks,
            "depth_ticks": self.depth_ticks,
            "placements": [placement.to_payload() for placement in self.placements],
        }

    @classmethod
    def from_payload(cls, payload: object) -> Self:
        if type(payload) is not dict:
            raise ExactMovementError("An exact battlefield payload must be an object.")
        data = cast(dict[str, object], payload)
        if (
            set(data)
            != {
                "version",
                "numerical_policy_id",
                "coordinate_representation_id",
                "width_ticks",
                "depth_ticks",
                "placements",
            }
            or data["version"] != EXACT_BATTLEFIELD_VERSION
            or data["numerical_policy_id"] != DISTANCE_POLICY_ID
            or data["coordinate_representation_id"] != COORDINATE_REPRESENTATION_ID
            or type(data["width_ticks"]) is not int
            or type(data["depth_ticks"]) is not int
            or type(data["placements"]) is not list
        ):
            raise ExactMovementError(
                "Missing or incompatible exact battlefield identity or fields."
            )
        return cls(
            width_ticks=data["width_ticks"],
            depth_ticks=data["depth_ticks"],
            placements=tuple(
                ExactModelPlacement.from_payload(item)
                for item in cast(list[object], data["placements"])
            ),
        )

    @property
    def content_hash(self) -> str:
        return hashlib.sha256(
            json.dumps(self.to_payload(), sort_keys=True, separators=(",", ":")).encode()
        ).hexdigest()


@dataclass(frozen=True, slots=True)
class ExactMovementResult:
    state: ExactBattlefieldState
    witness: ExactPathWitness
    travel_ticks: int


def apply_exact_movement(
    state: ExactBattlefieldState,
    *,
    model_instance_id: str,
    witness: ExactPathWitness,
    budget_ticks: int,
    required_contact_ids: tuple[str, ...] = (),
) -> ExactMovementResult:
    """Apply a full-path witness with mover, budget, and contacts set by the engine."""
    if type(state) is not ExactBattlefieldState or type(witness) is not ExactPathWitness:
        raise ExactMovementError(
            "Exact movement requires an exact battlefield and full path witness."
        )
    if type(budget_ticks) is not int or budget_ticks < 0:
        raise ExactMovementError("Exact movement requires a nonnegative integer tick budget.")
    if witness.source_state_hash != state.content_hash:
        raise ExactMovementError("Exact path witness has stale battlefield state.")
    if type(model_instance_id) is not str or witness.model_instance_id != model_instance_id:
        raise ExactMovementError("Exact path witness belongs to a different moving model.")

    placements = {placement.model_instance_id: placement for placement in state.placements}
    mover = placements.pop(model_instance_id, None)
    if mover is None or witness.waypoints[0] != mover.pose:
        raise ExactMovementError("Exact path witness must start at the authoritative model pose.")
    if (
        type(required_contact_ids) is not tuple
        or any(
            type(model_id) is not str or model_id not in placements
            for model_id in required_contact_ids
        )
        or len(set(required_contact_ids)) != len(required_contact_ids)
    ):
        raise ExactMovementError("Required exact contacts must identify unique stationary models.")

    sweeps = witness.sweeps(mover.diameter_ticks)
    obstacles = {model_id: placement.disk for model_id, placement in placements.items()}
    for segment in sweeps:
        # A rectangle inset by the disk's radius is convex. The start is already
        # valid, so testing every segment end proves the complete board bound.
        _check_board_footprint(segment.end, state.width_ticks, state.depth_ticks)
        for obstacle in obstacles.values():
            if not segment.clears(obstacle):
                raise ExactMovementError("Exact path overlaps a stationary disk along a segment.")

    end = sweeps[-1].end
    if any(
        end.relation_to(obstacles[model_id]) is not CircleRelation.EXTERNAL_CONTACT
        for model_id in required_contact_ids
    ):
        raise ExactMovementError(
            "Exact path endpoint does not establish required external contact."
        )
    travel_ticks = exact_path_travel_ticks(sweeps)
    if travel_ticks > budget_ticks:
        raise ExactMovementError("Complete exact path exceeds its movement budget.")

    moved = replace(mover, pose=witness.waypoints[-1])
    updated = replace(
        state,
        placements=tuple(
            moved if placement is mover else placement for placement in state.placements
        ),
    )
    return ExactMovementResult(updated, witness, travel_ticks)
