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
        TerrainWallDefinition,
    )

from warhammer40k_core.geometry.base import RectangularBase
from warhammer40k_core.geometry.pose import Point3, Pose
from warhammer40k_core.geometry.terrain_classification import TerrainAreaClassification
from warhammer40k_core.geometry.volume import Model

type Box = tuple[float, float, float, float, float, float]


@lru_cache(maxsize=256)
def solid_opening_volumes(
    feature_id: str, walls: tuple[TerrainWallDefinition, ...]
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
            depths = sorted({v for b in oriented for v in b[2:4]})
            for lo, hi in pairwise(depths):
                active = [b for b in oriented if b[2] <= lo and b[3] >= hi]
                for left, right, bottom, top in _enclosed_cells(active):
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
        *solid_opening_volumes(feature.feature_id, feature.walls),
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
