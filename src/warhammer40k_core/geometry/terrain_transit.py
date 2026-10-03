"""Continuous witnessed climbing contact and Dense floor-crossing predicates."""

from __future__ import annotations

import math
from dataclasses import replace
from fractions import Fraction
from itertools import pairwise

from warhammer40k_core.geometry.base import CircularBase, OvalBase, RectangularBase
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
from warhammer40k_core.geometry.visibility_shapes import rational_rotation
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
    if _rotation_contact_certificate(model, start, end, terrain):
        return True
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
    if any(not _contact_at_pose(model, pose, terrain) for pose in (start, middle, end)):
        return False
    if depth >= 32:
        raise GeometryError("Continuous rotating climbing contact remains unresolved.")
    return _segment_contact(model, start, middle, terrain, depth + 1) and _segment_contact(
        model, middle, end, terrain, depth + 1
    )


def _contact_at_pose(model: Model, pose: Pose, terrain: tuple[TerrainVolume, ...]) -> bool:
    for part in replace(model, pose=pose).rules_distance_subjects():
        for wall in terrain:
            if isinstance(part.base, OvalBase):
                c, s = rational_rotation(wall.rotation_degrees)
                dx = rational(part.pose.position.x) - rational(wall.bottom_center.x)
                dy = rational(part.pose.position.y) - rational(wall.bottom_center.y)
                centers = (float(c * dx + s * dy), float(c * dy - s * dx))
                axes = tuple(
                    axis
                    for axis, extent in ((0, wall.width), (1, wall.depth))
                    if abs(centers[axis]) + part.base.max_radius() <= extent / 2
                )
                if axes:
                    if any(
                        _oval_face_contact(part.base, part.pose, wall, 1 - axis) for axis in axes
                    ):
                        return True
                    continue
            if physical_footprints_within(
                part.base,
                part.pose,
                RectangularBase(wall.width, wall.depth),
                _terrain_pose(wall),
                0.5,
            ):
                return True
    return False


def _rotation_contact_certificate(
    model: Model, start: Pose, end: Pose, terrain: tuple[TerrainVolume, ...]
) -> bool:
    # Every supported base contains this disk at every facing. Its translating
    # center follows a segment through a convex half-inch terrain offset.
    base = model.base
    if isinstance(base, CircularBase):
        radius = base.radius
    elif isinstance(base, OvalBase | RectangularBase):
        radius = min(base.length, base.width) / 2
    else:
        return False
    disk = CircularBase(radius)
    for volume in terrain:
        wall = RectangularBase(volume.width, volume.depth)
        wall_pose = _terrain_pose(volume)
        if all(physical_footprints_within(disk, p, wall, wall_pose, 0.5) for p in (start, end)):
            return True
        if not isinstance(base, OvalBase | RectangularBase):
            continue
        # Along a straight wall face, rectangular support is a*cos(theta) +
        # b*sin(theta) with nonnegative coefficients in each quadrant. It is
        # concave there, so linear center translation minus support is convex:
        # its maximum occurs at a segment/quadrant boundary. This is a complete
        # interval certificate, including equality at the start or end.
        angle = math.radians(volume.rotation_degrees)
        c, s = math.cos(angle), math.sin(angle)
        centers = tuple(
            (
                (p.position.x - volume.bottom_center.x) * c
                + (p.position.y - volume.bottom_center.y) * s,
                -(p.position.x - volume.bottom_center.x) * s
                + (p.position.y - volume.bottom_center.y) * c,
            )
            for p in (start, end)
        )
        tangent_axes = tuple(
            axis
            for axis, extent in ((0, volume.width), (1, volume.depth))
            if all(abs(center[axis]) + base.max_radius() <= extent / 2 for center in centers)
        )
        if not tangent_axes:
            continue
        first = start.facing.degrees - volume.rotation_degrees
        last = end.facing.degrees - volume.rotation_degrees
        low, high = sorted((first, last))
        times = [0.0, 1.0]
        times.extend(
            (quadrant * 90 - first) / (last - first)
            for quadrant in range(math.floor(low / 90) + 1, math.ceil(high / 90))
        )
        critical_poses = tuple(interpolate_pose(start, end, t) for t in times)
        if isinstance(base, OvalBase):
            # Elliptical support has no interior minimum within a quadrant.
            # Testing its minimum at both center endpoints proves contact for
            # every center translation and orientation in this interval.
            critical_poses = tuple(
                replace(center, facing=orientation.facing)
                for center in (start, end)
                for orientation in critical_poses
            )
            if any(
                all(
                    _oval_face_contact(base, pose, volume, 1 - tangent_axis)
                    for pose in critical_poses
                )
                for tangent_axis in tangent_axes
            ):
                return True
            continue
        if all(
            physical_footprints_within(base, pose, wall, wall_pose, 0.5) for pose in critical_poses
        ):
            return True
    return False


def _oval_face_contact(base: OvalBase, pose: Pose, wall: TerrainVolume, axis: int) -> bool:
    """Compare exact elliptical support plus half an inch to a wall face."""
    wc, ws = rational_rotation(wall.rotation_degrees)
    nx, ny = (wc, ws) if axis == 0 else (-ws, wc)
    determinant = nx * nx + ny * ny
    extent = wall.width if axis == 0 else wall.depth
    distance = (
        abs(
            (rational(pose.position.x) - rational(wall.bottom_center.x)) * nx
            + (rational(pose.position.y) - rational(wall.bottom_center.y)) * ny
        )
        - rational(extent) * determinant / 2
    )
    if distance <= 0:
        return True
    c, s = rational_rotation(pose.facing.degrees)
    support_squared = (rational(base.length) * (c * nx + s * ny) / 2) ** 2 + (
        rational(base.width) * (c * ny - s * nx) / 2
    ) ** 2
    # distance <= sqrt(support_squared) + sqrt(determinant)/2,
    # eliminating radicals with their nonnegative signs retained.
    remainder = distance * distance - support_squared - determinant / 4
    return remainder <= 0 or remainder * remainder <= determinant * support_squared


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
    if _rotation_clear_of_floor(model, start, end, floor):
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


def _rotation_clear_of_floor(model: Model, start: Pose, end: Pose, floor: TerrainVolume) -> bool:
    """Separating slab axes using the entire interval's maximum base support."""
    base = model.base
    if not isinstance(base, CircularBase | OvalBase | RectangularBase):
        return False
    fc, fs = rational_rotation(floor.rotation_degrees)
    low, high = sorted((start.facing.degrees, end.facing.degrees))
    for axis, extent in ((0, floor.width), (1, floor.depth)):
        nx, ny = (fc, fs) if axis == 0 else (-fs, fc)
        determinant = nx * nx + ny * ny
        centers = tuple(
            (rational(p.position.x) - rational(floor.bottom_center.x)) * nx
            + (rational(p.position.y) - rational(floor.bottom_center.y)) * ny
            for p in (start, end)
        )
        gap = max(min(centers), -max(centers)) - rational(extent) * determinant / 2
        if gap < 0:
            continue
        if isinstance(base, CircularBase):
            support_squared = rational(base.radius) ** 2 * determinant
        else:
            a, b = rational(base.length) / 2, rational(base.width) / 2
            supports: list[Fraction] = []
            for pose in (start, end):
                c, s = rational_rotation(pose.facing.degrees)
                u, v = a * (c * nx + s * ny), b * (c * ny - s * nx)
                supports.append(
                    (abs(u) + abs(v)) ** 2 if isinstance(base, RectangularBase) else u * u + v * v
                )
            normal = floor.rotation_degrees + axis * 90
            offsets = (
                (0.0,)
                if isinstance(base, OvalBase)
                else (
                    math.degrees(math.atan2(base.width, base.length)),
                    -math.degrees(math.atan2(base.width, base.length)),
                )
            )
            if any(
                low <= normal + offset + turn * 180 <= high
                for offset in offsets
                for turn in range(
                    math.floor((low - normal - offset) / 180),
                    math.ceil((high - normal - offset) / 180) + 1,
                )
            ):
                supports.append(
                    (a * a + b * b if isinstance(base, RectangularBase) else a * a) * determinant
                )
            support_squared = max(supports)
        if gap * gap >= support_squared:
            return True
    return False


def _rotating_floor_crossing(
    model: Model, start: Pose, end: Pose, floor: TerrainVolume, depth: int = 0
) -> bool:
    if _rotation_clear_of_floor(model, start, end, floor):
        return False
    enclosing = replace(
        model, base=CircularBase(model.base.max_radius()), measures_every_part=False
    )
    if not _crosses_floor(enclosing, start, end, floor):
        return False
    middle = interpolate_pose(start, end, 0.5)
    displacement = (
        start.distance_2d_to(end) / 2
        + model.base.max_radius() * math.radians(abs(end.facing.degrees - start.facing.degrees)) / 2
    )
    if not physical_footprints_within(
        model.base,
        middle,
        RectangularBase(floor.width, floor.depth),
        _terrain_pose(floor),
        displacement,
    ):
        # Every point of the interpolated base stays within displacement of
        # this midpoint footprint, which is farther than that from the slab.
        return False
    if floor.bottom_center.z < middle.position.z < floor.top_z_inches() and floor.intersects_model(
        replace(model, pose=middle)
    ):
        return True
    if depth >= 32:
        raise GeometryError("Continuous rotating Dense floor crossing remains unresolved.")
    return _rotating_floor_crossing(
        model, start, middle, floor, depth + 1
    ) or _rotating_floor_crossing(model, middle, end, floor, depth + 1)
