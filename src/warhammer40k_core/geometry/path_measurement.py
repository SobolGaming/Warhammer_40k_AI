"""Pure pose-path measurements used by witnessed terrain traversal."""

from __future__ import annotations

import math
from itertools import pairwise

from warhammer40k_core.geometry.pose import Facing, Point3, Pose


def horizontal_section_transit_permitted(
    *,
    top_inches: float,
    maximum_height_inches: float | None,
    poses: tuple[Pose, ...],
) -> bool:
    return (
        maximum_height_inches is not None
        and top_inches <= maximum_height_inches
        and all(
            math.isclose(pose.position.z, poses[0].position.z, rel_tol=0, abs_tol=1e-9)
            for pose in poses[1:]
        )
    )


def path_horizontal_distance(poses: tuple[Pose, ...]) -> float:
    return sum(
        math.hypot(
            end.position.x - start.position.x,
            end.position.y - start.position.y,
        )
        for start, end in pairwise(poses)
    )


def path_without_vertical_distance(poses: tuple[Pose, ...]) -> tuple[Pose, ...]:
    measurement_z = poses[0].position.z
    return tuple(
        Pose.at(
            x=pose.position.x,
            y=pose.position.y,
            z=measurement_z,
            facing_degrees=pose.facing.degrees,
        )
        for pose in poses
    )


def path_vertical_distance(poses: tuple[Pose, ...]) -> float:
    return sum(abs(end.position.z - start.position.z) for start, end in pairwise(poses))


def path_3d_distance(poses: tuple[Pose, ...]) -> float:
    return sum(start.distance_3d_to(end) for start, end in pairwise(poses))


def interpolate_pose(start: Pose, end: Pose, t: float) -> Pose:
    return Pose(
        position=Point3(
            x=_interpolate(start.position.x, end.position.x, t),
            y=_interpolate(start.position.y, end.position.y, t),
            z=_interpolate(start.position.z, end.position.z, t),
        ),
        facing=Facing(_interpolate(start.facing.degrees, end.facing.degrees, t)),
    )


def _interpolate(start: float, end: float, t: float) -> float:
    return start + ((end - start) * t)
