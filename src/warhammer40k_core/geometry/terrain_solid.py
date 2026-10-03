"""Derive Solid openings from enclosed cells in physical wall surfaces.

Each aligned wall family is partitioned at its exact rectangle boundaries.
Flooding the unoccupied surface cells from the sides and top distinguishes
windows/doors from open corners. Ground closes a door's bottom. The result is
ordinary rectangular volumes, consumed by the existing continuous LOS and
physical endpoint predicates; it never fills a terrain area's interior.
"""

from __future__ import annotations

import math
from collections import deque
from functools import lru_cache
from itertools import pairwise
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from warhammer40k_core.geometry.terrain import (
        ObstacleVolume,
        TerrainFeatureDefinition,
        TerrainFloorDefinition,
        TerrainWallDefinition,
    )

from warhammer40k_core.geometry.base import RectangularBase
from warhammer40k_core.geometry.pose import Point3, Pose
from warhammer40k_core.geometry.terrain_classification import TerrainAreaClassification
from warhammer40k_core.geometry.volume import Model

type Box = tuple[float, float, float, float, float, float]


@lru_cache(maxsize=256)
def solid_opening_volumes(
    feature_id: str,
    walls: tuple[TerrainWallDefinition, ...],
    floors: tuple[TerrainFloorDefinition, ...] = (),
) -> tuple[ObstacleVolume, ...]:
    from warhammer40k_core.geometry.terrain import ObstacleVolume

    families: dict[float, list[Box]] = {}
    for wall in walls:
        angle = wall.rotation_degrees % 90
        c, s = math.cos(math.radians(angle)), math.sin(math.radians(angle))
        u = c * wall.center_x_inches + s * wall.center_y_inches
        v = c * wall.center_y_inches - s * wall.center_x_inches
        width, depth = wall.width_inches, wall.depth_inches
        if round((wall.rotation_degrees - angle) / 90) % 2:
            width, depth = depth, width
        families.setdefault(angle, []).append(
            (
                round(u - width / 2, 12),
                round(u + width / 2, 12),
                round(v - depth / 2, 12),
                round(v + depth / 2, 12),
                wall.bottom_z_inches,
                wall.bottom_z_inches + wall.height_inches,
            )
        )
    result: list[ObstacleVolume] = []
    for angle, boxes in sorted(families.items()):
        # Both vertical surface orientations are needed (walls may be stored
        # with either their long dimension in width or in depth).
        for swap in (False, True):
            oriented = [(b[2], b[3], b[0], b[1], b[4], b[5]) if swap else b for b in boxes]
            depths = sorted(
                {
                    *(v for b in oriented for v in b[2:4]),
                    *(
                        depth
                        for floor in floors
                        for depth in _floor_depth_boundaries(floor, angle, swap)
                    ),
                }
            )
            for lo, hi in pairwise(depths):
                active = [b for b in oriented if b[2] <= lo and b[3] >= hi]
                if not active:
                    continue
                # Slabs can close a wall opening, but do not create wall
                # surfaces or fill the interior between parallel walls.
                closures = [
                    box
                    for floor in floors
                    if any(b[1] - b[0] >= b[3] - b[2] for b in active)
                    if (box := _floor_strip(floor, angle, swap, lo, hi)) is not None
                ]
                for left, right, bottom, top in _enclosed_cells(active + closures):
                    top = min(3.0, top)
                    if bottom >= top:
                        continue
                    u, v = (left + right) / 2, (lo + hi) / 2
                    width, depth = right - left, hi - lo
                    if swap:
                        u, v, width, depth = v, u, depth, width
                    c, s = math.cos(math.radians(angle)), math.sin(math.radians(angle))
                    result.append(
                        ObstacleVolume(
                            terrain_id=f"{feature_id}:solid-opening-{len(result)}",
                            bottom_center=Point3(c * u - s * v, s * u + c * v, bottom),
                            width=width,
                            depth=depth,
                            height=top - bottom,
                            rotation_degrees=angle,
                        )
                    )
    return tuple(result)


def _floor_depth_boundaries(
    floor: TerrainFloorDefinition, angle: float, swap: bool
) -> tuple[float, ...]:
    c, s = math.cos(math.radians(angle)), math.sin(math.radians(angle))
    nx, ny = (c, s) if swap else (-s, c)
    fc, fs = (
        math.cos(math.radians(floor.rotation_degrees)),
        math.sin(math.radians(floor.rotation_degrees)),
    )
    center = floor.center_x_inches * nx + floor.center_y_inches * ny
    a = (fc * nx + fs * ny) * floor.width_inches / 2
    b = (-fs * nx + fc * ny) * floor.depth_inches / 2
    return tuple(round(center + i * a + j * b, 12) for i in (-1, 1) for j in (-1, 1))


def _floor_strip(
    floor: TerrainFloorDefinition, angle: float, swap: bool, lo: float, hi: float
) -> Box | None:
    """Exact covered interval across one wall strip, including rotated slabs."""
    c, s = math.cos(math.radians(angle)), math.sin(math.radians(angle))
    u, v = (c, s), (-s, c)
    if swap:
        u, v = v, u
    fc, fs = (
        math.cos(math.radians(floor.rotation_degrees)),
        math.sin(math.radians(floor.rotation_degrees)),
    )
    left, right = -math.inf, math.inf
    for axis, extent in (((fc, fs), floor.width_inches), ((-fs, fc), floor.depth_inches)):
        a = round(axis[0] * u[0] + axis[1] * u[1], 12)
        b = round(axis[0] * v[0] + axis[1] * v[1], 12)
        center = axis[0] * floor.center_x_inches + axis[1] * floor.center_y_inches
        for depth in (lo, hi):
            offset = round(b * depth - center, 12)
            if a == 0:
                if abs(offset) > extent / 2:
                    return None
            else:
                bounds = sorted(((-extent / 2 - offset) / a, (extent / 2 - offset) / a))
                left, right = max(left, bounds[0]), min(right, bounds[1])
    if left >= right:
        return None
    return (
        round(left, 12),
        round(right, 12),
        lo,
        hi,
        floor.bottom_z_inches,
        floor.bottom_z_inches + floor.thickness_inches,
    )


def solid_endpoint_intersection(model: Model, feature: TerrainFeatureDefinition) -> str | None:
    """All model parts obey Solid even when their support base sits on a floor."""
    from warhammer40k_core.geometry.physical_model import physical_prisms
    from warhammer40k_core.geometry.physical_predicates import physical_footprints_overlap

    if feature.classification not in {
        TerrainAreaClassification.DENSE,
        TerrainAreaClassification.MIXED,
    }:
        return None
    for volume in (
        *feature.wall_volumes(),
        *solid_opening_volumes(feature.feature_id, feature.walls, feature.floors),
    ):
        top = min(3.0, volume.top_z_inches())
        for part in physical_prisms(model):
            bottom, part_top = part.volume.vertical_interval(part.pose)
            if bottom >= top or part_top <= volume.bottom_center.z:
                continue
            if physical_footprints_overlap(
                part.base,
                part.pose,
                RectangularBase(volume.width, volume.depth),
                Pose.at(
                    volume.bottom_center.x,
                    volume.bottom_center.y,
                    facing_degrees=volume.rotation_degrees,
                ),
            ):
                return volume.terrain_id
    return None


def _enclosed_cells(boxes: list[Box]) -> tuple[tuple[float, float, float, float], ...]:
    if not boxes:
        return ()
    xs = sorted({v for b in boxes for v in b[:2]})
    zs = sorted({0.0, *(v for b in boxes for v in b[4:])})
    empty = {
        (i, j)
        for i in range(len(xs) - 1)
        for j in range(len(zs) - 1)
        if not any(
            b[0] <= xs[i] and b[1] >= xs[i + 1] and b[4] <= zs[j] and b[5] >= zs[j + 1]
            for b in boxes
        )
    }
    outside = {cell for cell in empty if cell[0] in (0, len(xs) - 2) or cell[1] == len(zs) - 2}
    pending = deque(outside)
    while pending:
        i, j = pending.popleft()
        for neighbor in ((i - 1, j), (i + 1, j), (i, j - 1), (i, j + 1)):
            if neighbor in empty and neighbor not in outside:
                outside.add(neighbor)
                pending.append(neighbor)
    return tuple((xs[i], xs[i + 1], zs[j], zs[j + 1]) for i, j in sorted(empty - outside))
