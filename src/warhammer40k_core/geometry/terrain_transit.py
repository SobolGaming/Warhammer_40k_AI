"""Continuous witnessed climbing contact and Dense floor-crossing predicates."""

from __future__ import annotations

import math
from dataclasses import replace
from fractions import Fraction
from itertools import pairwise

from warhammer40k_core.geometry.base import CircularBase, RectangularBase
from warhammer40k_core.geometry.path_measurement import interpolate_pose
from warhammer40k_core.geometry.physical_predicates import (
    nonoverlapping,
    physical_footprints_within,
)
from warhammer40k_core.geometry.placement_predicates import Footprint, PlacementPredicates, rational
from warhammer40k_core.geometry.pose import GeometryError, Pose
from warhammer40k_core.geometry.terrain import TerrainFeatureDefinition, TerrainVolume
from warhammer40k_core.geometry.terrain_classification import TerrainAreaClassification
from warhammer40k_core.geometry.visibility_algebra import (
    both,
    decide,
    either,
    negate,
    quantified,
    term,
    variable,
)
from warhammer40k_core.geometry.volume import Model


def _terrain_shape(volume: TerrainVolume) -> Footprint:
    return Footprint.fixed(RectangularBase(volume.width, volume.depth), _terrain_pose(volume))


def _terrain_pose(volume: TerrainVolume) -> Pose:
    return Pose.at(
        volume.bottom_center.x, volume.bottom_center.y, facing_degrees=volume.rotation_degrees
    )


def _moving_shape(model: Model, start: Pose, end: Pose) -> Footprint:
    shape = Footprint.fixed(model.base, start)
    t = variable("terrain_t")
    return replace(
        shape,
        x=shape.x + t * rational(end.position.x - start.position.x),
        y=shape.y + t * rational(end.position.y - start.position.y),
    )


def _fixed_facing(model: Model, start: Pose, end: Pose) -> bool:
    return (
        type(model.base) is CircularBase and not model.measures_every_part
    ) or start.facing == end.facing


def path_retains_climbing_contact(
    model: Model, path: tuple[Pose, ...], terrain: tuple[TerrainVolume, ...]
) -> bool:
    for start, end in pairwise(path):
        if start.position.z == end.position.z:
            continue
        if not _segment_contact(model, start, end, terrain):
            return False
    return True


def _segment_contact(
    model: Model, start: Pose, end: Pose, terrain: tuple[TerrainVolume, ...], depth: int = 0
) -> bool:
    if not terrain:
        return False
    if _fixed_facing(model, start, end):
        if any(
            all(
                physical_footprints_within(
                    model.base,
                    pose,
                    RectangularBase(volume.width, volume.depth),
                    _terrain_pose(volume),
                    0.5,
                )
                for pose in (start, end)
            )
            for volume in terrain
        ):
            # Translation through one convex half-inch offset remains in it.
            return True
        predicates = PlacementPredicates(prefix="contact")
        subjects = replace(model, pose=start).rules_distance_subjects()
        contacts = either(
            *(
                predicates.near(
                    _moving_shape(
                        part,
                        part.pose,
                        replace(
                            end,
                            position=replace(
                                end.position,
                                x=part.pose.position.x + end.position.x - start.position.x,
                                y=part.pose.position.y + end.position.y - start.position.y,
                            ),
                        ),
                    ),
                    _terrain_shape(volume),
                    term(Fraction(1, 2)),
                )
                for part in subjects
                for volume in terrain
            )
        )
        t = variable("terrain_t")
        # There must be a physical contact at every point, not just at the
        # sampled poses. Different members of one surface union can supply it.
        return not decide(
            both(t.ge(0), t.le(1), negate(quantified("exists", tuple(predicates.names), contacts))),
            ("terrain_t",),
        )
    middle = interpolate_pose(start, end, 0.5)
    subject = replace(model, pose=middle)
    # Lipschitz certificate for actual linear-angle interpolation. A rotating
    # base's every point moves by no more than radius * angle plus translation.
    radius = max(
        part.base.max_radius() + part.pose.distance_2d_to(middle)
        for part in subject.rules_distance_subjects()
    )
    bound = (
        start.distance_2d_to(end) / 2
        + radius * math.radians(abs(end.facing.degrees - start.facing.degrees)) / 2
    )
    if bound <= 0.5 and any(
        physical_footprints_within(
            part.base, part.pose, RectangularBase(v.width, v.depth), _terrain_pose(v), 0.5 - bound
        )
        for part in subject.rules_distance_subjects()
        for v in terrain
    ):
        return True
    if any(
        not any(
            physical_footprints_within(
                part.base, part.pose, RectangularBase(v.width, v.depth), _terrain_pose(v), 0.5
            )
            for part in replace(model, pose=pose).rules_distance_subjects()
            for v in terrain
        )
        for pose in (start, middle, end)
    ):
        return False
    if depth >= 32:
        raise GeometryError("Continuous rotating climbing contact remains unresolved.")
    return _segment_contact(model, start, middle, terrain, depth + 1) and _segment_contact(
        model, middle, end, terrain, depth + 1
    )


def forbidden_dense_floor_crossing(
    model: Model,
    path: tuple[Pose, ...],
    features: tuple[TerrainFeatureDefinition, ...],
    keywords: tuple[str, ...],
) -> str | None:
    if set(keywords) & {"INFANTRY", "BEAST", "SWARM"}:
        return None
    for feature in features:
        if feature.classification not in {
            TerrainAreaClassification.DENSE,
            TerrainAreaClassification.MIXED,
        }:
            continue
        for floor in feature.floor_volumes():
            for start, end in pairwise(path):
                if start.position.z == end.position.z:
                    continue
                if _crosses_floor(model, start, end, floor):
                    return floor.terrain_id
    return None


def _crosses_floor(model: Model, start: Pose, end: Pose, floor: TerrainVolume) -> bool:
    low, high = sorted((start.position.z, end.position.z))
    if high <= floor.bottom_center.z or low >= floor.top_z_inches():
        return False
    if not _fixed_facing(model, start, end):
        # Split a rotating segment until either a conservative enclosing circle
        # proves clearance or a real base witnesses the forbidden crossing.
        return _rotating_floor_crossing(model, start, end, floor)
    t = variable("terrain_t")
    z = term(rational(start.position.z)) + t * rational(end.position.z - start.position.z)
    predicates = PlacementPredicates(prefix="floor")
    moving = _moving_shape(model, start, end)
    if moving.kind == "circle":
        intersects = predicates.point_near(
            moving.x,
            moving.y,
            _terrain_shape(floor),
            term(moving.a - Fraction(1, 1_000_000_000)),
        )
    else:
        separated = nonoverlapping(predicates, moving, _terrain_shape(floor))
        intersects = negate(quantified("exists", tuple(predicates.names), separated))
    return decide(
        both(
            t.ge(0),
            t.le(1),
            z.gt(rational(floor.bottom_center.z)),
            z.lt(rational(floor.top_z_inches())),
            intersects,
        ),
        ("terrain_t",),
    )


def _rotating_floor_crossing(
    model: Model, start: Pose, end: Pose, floor: TerrainVolume, depth: int = 0
) -> bool:
    enclosing = replace(
        model, base=CircularBase(model.base.max_radius()), measures_every_part=False
    )
    if not _crosses_floor(enclosing, start, end, floor):
        return False
    middle = interpolate_pose(start, end, 0.5)
    if floor.bottom_center.z < middle.position.z < floor.top_z_inches() and floor.intersects_model(
        replace(model, pose=middle)
    ):
        return True
    if depth >= 32:
        raise GeometryError("Continuous rotating Dense floor crossing remains unresolved.")
    return _rotating_floor_crossing(
        model, start, middle, floor, depth + 1
    ) or _rotating_floor_crossing(model, middle, end, floor, depth + 1)
