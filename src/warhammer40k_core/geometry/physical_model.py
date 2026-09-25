"""Shared body-aware physical queries; ordinary rules distances still use bases."""

from __future__ import annotations

import math
from dataclasses import replace
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from warhammer40k_core.geometry.terrain import TerrainVolume

from warhammer40k_core.geometry.base import RectangularBase
from warhammer40k_core.geometry.physical_predicates import (
    physical_footprints_overlap,
    physical_footprints_within,
)
from warhammer40k_core.geometry.pose import Pose
from warhammer40k_core.geometry.volume import Model, ModelVolume


def physical_prisms(model: Model) -> tuple[Model, ...]:
    if not model.body_parts:
        return (model,)
    return (
        replace(model, body_parts=()),
        *(
            Model(
                model_id=model.model_id,
                pose=part.pose_at(model.pose),
                base=part.base,
                volume=ModelVolume(part.height_inches),
            )
            for part in model.body_parts
        ),
    )


def physical_radius(model: Model) -> float:
    return (
        max(
            model.base.max_radius(),
            *(
                math.hypot(p.offset_x_inches, p.offset_y_inches) + p.base.max_radius()
                for p in model.body_parts
            ),
        )
        if model.body_parts
        else model.base.max_radius()
    )


def physical_top(model: Model) -> float:
    return (
        model.pose.position.z
        + max(
            model.volume.height,
            *(part.bottom_inches + part.height_inches for part in model.body_parts),
        )
        if model.body_parts
        else model.pose.position.z + model.volume.height
    )


def models_overlap_physically(first: Model, second: Model) -> bool:
    if first.pose.distance_2d_to(second.pose) >= physical_radius(first) + physical_radius(second):
        return False
    if not first.body_parts and not second.body_parts:
        return first.volume.vertical_gap_to(
            first.pose, second.volume, second.pose
        ) == 0.0 and first.base_overlaps(second)
    return any(
        a.volume.vertical_gap_to(a.pose, b.volume, b.pose) == 0.0
        and physical_footprints_overlap(a.base, a.pose, b.base, b.pose)
        for a in physical_prisms(first)
        for b in physical_prisms(second)
    )


def model_parts_distance(first: Model, second: Model) -> float:
    return min(a.range_to(b) for a in physical_prisms(first) for b in physical_prisms(second))


def base_crosses_physical_model(moving: Model, blocker: Model) -> bool:
    """Core movement uses the moving base in transit, and full models at the end."""
    return models_overlap_physically(replace(moving, body_parts=()), blocker)


def body_intersects_terrain_endpoint(
    model: Model, terrain: tuple[TerrainVolume, ...]
) -> str | None:
    """A support-base exception cannot permit a body part through a wall/ceiling."""
    for part in physical_prisms(model)[1:] if model.body_parts else ():
        bottom, top = part.volume.vertical_interval(part.pose)
        for volume in terrain:
            if bottom >= volume.top_z_inches() or top <= volume.bottom_center.z:
                continue
            if physical_footprints_overlap(
                part.base,
                part.pose,
                RectangularBase(volume.width, volume.depth),
                Pose.at(
                    volume.bottom_center.x,
                    volume.bottom_center.y,
                    volume.bottom_center.z,
                    facing_degrees=volume.rotation_degrees,
                ),
            ):
                return volume.terrain_id
    return None


def model_parts_within(first: Model, second: Model, distance_inches: float) -> bool:
    for a in physical_prisms(first):
        for b in physical_prisms(second):
            vertical = a.volume.vertical_gap_to(a.pose, b.volume, b.pose)
            if vertical > distance_inches:
                continue
            horizontal = math.sqrt(max(0.0, distance_inches**2 - vertical**2))
            if physical_footprints_within(a.base, a.pose, b.base, b.pose, horizontal):
                return True
    return False


def base_crosses_physical_model_footprint(moving: Model, blocker: Model) -> bool:
    """Fall Back crossing inventory retains its projection onto the battlefield."""
    return any(
        physical_footprints_overlap(moving.base, moving.pose, part.base, part.pose)
        for part in physical_prisms(blocker)
    )
