"""Complete translated/rotated Emergency Set Up queries over supported planes.

The finite elevation inventory is ground plus the actual terrain support planes.
Each plane retains continuous translations and all orientations. A negative
answer is a real-arithmetic unsatisfiability proof, never a failed sample search.
"""

from __future__ import annotations

from dataclasses import dataclass, replace
from fractions import Fraction
from functools import lru_cache
from itertools import combinations
from math import isqrt

from warhammer40k_core.geometry.base import CircularBase, OvalBase, RectangularBase
from warhammer40k_core.geometry.placement_predicates import Footprint, PlacementPredicates, rational
from warhammer40k_core.geometry.pose import Pose
from warhammer40k_core.geometry.terrain import TerrainFeatureDefinition, TerrainFloorDefinition
from warhammer40k_core.geometry.visibility_algebra import (
    FALSE,
    TRUE,
    Formula,
    RealTerm,
    both,
    decide,
    either,
    term,
)
from warhammer40k_core.geometry.visibility_exact import convex_polygon_parts
from warhammer40k_core.geometry.volume import Model


@dataclass(frozen=True, slots=True)
class SetupTerrain:
    feature: TerrainFeatureDefinition
    ground_allowed: bool
    elevated_allowed: bool
    no_overhang: bool
    ground_containment: bool


@dataclass(frozen=True, slots=True)
class EmergencySetupQuery:
    passenger: Model
    transports: tuple[Model, ...]
    blockers: tuple[Model, ...]
    enemies: tuple[Model, ...]
    partners: tuple[Model, ...]
    terrain: tuple[SetupTerrain, ...]
    objective_disks: tuple[tuple[float, float, float, float], ...]
    width: Fraction
    depth: Fraction
    neighbor_limit: Fraction
    vertical_limit: Fraction
    span_limit: Fraction | None
    engagement: Fraction
    engagement_vertical: Fraction
    setup_distance: Fraction
    oversized_distance: Fraction
    ordinary_size_fit: bool
    require_unengaged: bool
    closer_than: Model | None
    closest_tolerance: Fraction
    required_neighbors: int = 1


def _vertical_gap(z: Fraction, height: Fraction, other: Model) -> Fraction:
    bottom = rational(other.pose.position.z)
    top = bottom + rational(other.volume.height)
    return max(Fraction(0), bottom - z - height, z - top)


def _horizontal_limit(
    context: PlacementPredicates, distance: RealTerm, gap: Fraction
) -> tuple[Formula, RealTerm]:
    if gap == 0:
        return distance.ge(0), distance
    if distance.constant is not None:
        square = distance.constant**2 - gap**2
        if square < 0:
            return FALSE, term(0)
        a, b = isqrt(square.numerator), isqrt(square.denominator)
        if a * a == square.numerator and b * b == square.denominator:
            return TRUE, term(Fraction(a, b))
    horizontal = context.scalar()
    return both(
        distance.ge(gap), horizontal.ge(0), (horizontal**2 + gap**2).eq(distance**2)
    ), horizontal


def _range_near(
    context: PlacementPredicates,
    first: Footprint,
    second: Model,
    z: Fraction,
    height: Fraction,
    distance: RealTerm,
) -> Formula:
    condition, horizontal = _horizontal_limit(context, distance, _vertical_gap(z, height, second))
    return both(
        condition, context.near(first, Footprint.fixed(second.base, second.pose), horizontal)
    )


def _range_clear(
    context: PlacementPredicates,
    first: Model,
    second: Model,
    distance: RealTerm,
) -> Formula:
    gap = _vertical_gap(rational(first.pose.position.z), rational(first.volume.height), second)
    condition, horizontal = _horizontal_limit(context, distance, gap)
    return either(
        distance.lt(gap),
        both(
            condition,
            context.clear(
                Footprint.fixed(first.base, first.pose),
                Footprint.fixed(second.base, second.pose),
                horizontal,
            ),
        ),
    )


def _floor_shape(floor: TerrainFloorDefinition) -> Footprint:
    return Footprint.fixed(
        RectangularBase(floor.width_inches, floor.depth_inches),
        Pose.at(
            floor.center_x_inches,
            floor.center_y_inches,
            floor.bottom_z_inches,
            facing_degrees=floor.rotation_degrees,
        ),
    )


def _clear_polygon(
    context: PlacementPredicates,
    shape: Footprint,
    points: tuple[tuple[float, float], ...],
) -> Formula:
    parts = convex_polygon_parts(tuple((rational(x), rational(y)) for x, y in points))
    conditions: list[Formula] = []
    for part in parts:
        nx, ny, bound = context.scalar(), context.scalar(), context.scalar()
        conditions.append(
            both(
                (nx * nx + ny * ny).eq(1),
                shape.support_at_most(nx, ny, bound),
                *(
                    (term(x) * nx + term(y) * ny - shape.x * nx - shape.y * ny).gt(bound)
                    for x, y in part
                ),
            )
        )
    return both(*conditions)


def _terrain_conditions(
    context: PlacementPredicates,
    shape: Footprint,
    z: Fraction,
    height: Fraction,
    terrain: tuple[SetupTerrain, ...],
) -> Formula:
    constraints: list[Formula] = []
    supports: list[Formula] = []
    for entry in terrain:
        feature = entry.feature
        touched: list[Formula] = []
        for floor in feature.floors:
            bottom = rational(floor.bottom_z_inches)
            footprint = _floor_shape(floor)
            if bottom == z:
                allowed = entry.elevated_allowed if z > 0 else entry.ground_allowed
                if not allowed:
                    constraints.append(context.clear(shape, footprint))
                    continue
                contact = context.near(shape, footprint, term(0))
                if entry.no_overhang and (z > 0 or entry.ground_containment):
                    contained = context.inside_rectangle(shape, footprint)
                    constraints.append(either(context.clear(shape, footprint), contained))
                    contact = both(contact, contained)
                touched.append(contact)
                supports.append(contact)
            elif bottom <= z + height and bottom + rational(floor.thickness_inches) >= z:
                constraints.append(context.clear(shape, footprint))
        for wall in feature.walls:
            bottom = rational(wall.bottom_z_inches)
            if bottom > z + height or bottom + rational(wall.height_inches) < z:
                continue
            wall_shape = Footprint.fixed(
                RectangularBase(wall.width_inches, wall.depth_inches),
                Pose.at(
                    wall.center_x_inches, wall.center_y_inches, facing_degrees=wall.rotation_degrees
                ),
            )
            constraints.append(context.clear(shape, wall_shape))
        if z > 0 and entry.no_overhang:
            constraints.append(
                either(*touched, _clear_polygon(context, shape, feature.rules_footprint_points()))
            )
    return both(*constraints, TRUE if z == 0 else either(*supports))


def _plane_formula(
    query: EmergencySetupQuery,
    z: Fraction,
    *,
    fixed_pose: Pose | None = None,
    enclose_passenger: bool = False,
    closest_limit: Fraction | None = None,
) -> tuple[Formula, tuple[str, ...]]:
    context = PlacementPredicates()
    x, y = context.scalar(), context.scalar()
    rotation: Formula = TRUE
    if type(query.passenger.base) is CircularBase:
        c, s = term(1), term(0)
    else:
        c, s = context.scalar(), context.scalar()
        rotation = (c * c + s * s).eq(1)
    shape = Footprint.moving(query.passenger.base, x, y, c, s)
    if fixed_pose is not None:
        shape = Footprint.fixed(query.passenger.base, fixed_pose)
        rotation = TRUE
    height = rational(query.passenger.volume.height)
    battlefield = Footprint(
        "rectangle",
        term(query.width / 2),
        term(query.depth / 2),
        query.width / 2,
        query.depth / 2,
        term(1),
        term(0),
    )
    constraints = [
        rotation,
        context.inside_rectangle(shape, battlefield),
        _terrain_conditions(context, shape, z, height, query.terrain),
    ]
    for other in (*query.transports, *query.blockers):
        if _vertical_gap(z, height, other) == 0:
            constraints.append(context.clear(shape, Footprint.fixed(other.base, other.pose)))
    for ox, oy, oz, radius in query.objective_disks:
        if z <= rational(oz) <= z + height:
            constraints.append(
                context.clear(shape, Footprint.fixed(CircularBase(radius), Pose.at(ox, oy)))
            )
    if query.require_unengaged:
        constraints.extend(
            context.clear(shape, Footprint.fixed(enemy.base, enemy.pose), term(query.engagement))
            for enemy in query.enemies
            if _vertical_gap(z, height, enemy) <= query.engagement_vertical
        )
    constraints.append(_coherency_conditions(context, shape, z, height, query))
    if query.span_limit is not None:
        constraints.append(
            FALSE
            if any(
                _vertical_gap(z, height, partner) > query.vertical_limit
                for partner in query.partners
            )
            else TRUE
        )
        constraints.extend(
            context.near(shape, Footprint.fixed(partner.base, partner.pose), term(query.span_limit))
            for partner in query.partners
        )
    distance_conditions: list[Formula] = []
    for transport in query.transports:
        if query.ordinary_size_fit:
            condition, distance = _horizontal_limit(
                context, term(query.setup_distance), _vertical_gap(z, height, transport)
            )
            containment_shape = (
                replace(shape, kind="rectangle")
                if enclose_passenger and shape.kind == "ellipse"
                else shape
            )
            distance_conditions.append(
                both(
                    condition,
                    context.contained(
                        containment_shape, Footprint.fixed(transport.base, transport.pose), distance
                    ),
                )
            )
        else:
            distance_conditions.append(
                _range_near(context, shape, transport, z, height, term(query.oversized_distance))
            )
    constraints.append(either(*distance_conditions))
    if closest_limit is not None:
        constraints.append(
            either(
                *(
                    _range_near(context, shape, transport, z, height, term(closest_limit))
                    for transport in query.transports
                )
            )
        )
    elif query.closer_than is not None:
        distance = context.scalar()
        constraints.extend(
            (
                distance.ge(0),
                either(
                    *(
                        _range_near(context, shape, transport, z, height, distance)
                        for transport in query.transports
                    )
                ),
                *(
                    _range_clear(
                        context, query.closer_than, transport, distance + query.closest_tolerance
                    )
                    for transport in query.transports
                ),
            )
        )
    return both(*constraints), tuple(context.names)


@lru_cache(maxsize=512)
def _partner_adjacency(
    partners: tuple[Model, ...], horizontal: Fraction, vertical: Fraction
) -> tuple[tuple[int, ...], ...]:
    adjacency: list[list[int]] = [[] for _ in partners]
    for i, first in enumerate(partners):
        for j in range(i + 1, len(partners)):
            second = partners[j]
            if (
                _vertical_gap(
                    rational(first.pose.position.z), rational(first.volume.height), second
                )
                > vertical
            ):
                continue
            context = PlacementPredicates()
            near = context.near(
                Footprint.fixed(first.base, first.pose),
                Footprint.fixed(second.base, second.pose),
                term(horizontal),
            )
            if decide(near, tuple(context.names)):
                adjacency[i].append(j)
                adjacency[j].append(i)
    return tuple(tuple(neighbors) for neighbors in adjacency)


def _coherency_conditions(
    context: PlacementPredicates,
    shape: Footprint,
    z: Fraction,
    height: Fraction,
    query: EmergencySetupQuery,
) -> Formula:
    if not query.partners:
        return TRUE
    links = tuple(
        context.near(shape, Footprint.fixed(partner.base, partner.pose), term(query.neighbor_limit))
        if _vertical_gap(z, height, partner) <= query.vertical_limit
        else FALSE
        for partner in query.partners
    )
    adjacency = _partner_adjacency(query.partners, query.neighbor_limit, query.vertical_limit)
    constraints = [
        either(*(both(*group) for group in combinations(links, query.required_neighbors)))
    ]
    for i, neighbors in enumerate(adjacency):
        if len(neighbors) < query.required_neighbors:
            constraints.append(
                links[i] if len(neighbors) + 1 == query.required_neighbors else FALSE
            )
    # Removing the candidate can split a previously coherent chain. It must
    # reconnect every remaining component, not just find one neighbor.
    remaining = set(range(len(links)))
    while remaining:
        pending = [min(remaining)]
        group: set[int] = set()
        while pending:
            i = pending.pop()
            if i in group:
                continue
            group.add(i)
            pending.extend(j for j in adjacency[i] if j not in group)
        remaining.difference_update(group)
        constraints.append(either(*(links[i] for i in sorted(group))))
    if query.span_limit is not None:
        span = _partner_adjacency(query.partners, query.span_limit, query.vertical_limit)
        if any(len(neighbors) != len(query.partners) - 1 for neighbors in span):
            return FALSE
    return both(*constraints)


@lru_cache(maxsize=512)
def emergency_setup_pose_is_legal(query: EmergencySetupQuery) -> bool:
    """Check the submitted endpoint with the same predicates as alternatives."""
    z = rational(query.passenger.pose.position.z)
    for enclosure in (True, False):
        formula, names = _plane_formula(
            query, z, fixed_pose=query.passenger.pose, enclose_passenger=enclosure
        )
        if decide(formula, names):
            return True
        if type(query.passenger.base) is not OvalBase:
            break
    return False


@lru_cache(maxsize=512)
def emergency_setup_pose_exists(query: EmergencySetupQuery) -> bool:
    base = query.passenger.base
    minimum_width = (
        rational(2 * base.radius)
        if type(base) is CircularBase
        else min(
            Footprint.fixed(base, query.passenger.pose).a,
            Footprint.fixed(base, query.passenger.pose).b,
        )
        * 2
    )
    if minimum_width > min(query.width, query.depth):
        return False
    elevations = sorted(
        {
            Fraction(0),
            *(
                rational(floor.bottom_z_inches)
                for terrain in query.terrain
                for floor in terrain.feature.floors
            ),
        }
    )
    # A supported positive witness settles existence without first solving a
    # potentially harder impossible ground plane. It cannot settle omission.
    if query.closer_than is None:
        for terrain in query.terrain:
            for floor in terrain.feature.floors:
                z = rational(floor.bottom_z_inches)
                pose = Pose.at(
                    floor.center_x_inches,
                    floor.center_y_inches,
                    float(z),
                    floor.rotation_degrees,
                )
                formula, names = _plane_formula(query, z, fixed_pose=pose, enclose_passenger=True)
                if decide(formula, names):
                    return True
    for z in elevations:
        if query.closer_than is not None:
            # Every candidate on this plane is at least this vertical distance
            # from the Transport. Prove that even this lower bound cannot beat
            # the proposal before asking the larger placement formula.
            minimum = min(
                _vertical_gap(z, rational(query.passenger.volume.height), transport)
                for transport in query.transports
            )
            reference = query.closer_than
            context = PlacementPredicates()
            cannot_improve = either(
                *(
                    _range_near(
                        context,
                        Footprint.fixed(reference.base, reference.pose),
                        transport,
                        rational(reference.pose.position.z),
                        rational(reference.volume.height),
                        term(minimum + query.closest_tolerance),
                    )
                    for transport in query.transports
                )
            )
            if decide(cannot_improve, tuple(context.names)):
                continue
        bounds = _reference_circle_bounds(query)
        if bounds is not None:
            lower, upper = bounds
            formula, names = _plane_formula(query, z, closest_limit=upper - query.closest_tolerance)
            if not decide(formula, names):
                continue
            lower -= query.closest_tolerance + Fraction(1, 10**12)
            if lower >= 0:
                formula, names = _plane_formula(query, z, closest_limit=lower)
                if decide(formula, names):
                    return True
        for pose in _witness_poses(query, z):
            formula, names = _plane_formula(query, z, fixed_pose=pose, enclose_passenger=True)
            if decide(formula, names):
                return True
        formula, names = _plane_formula(query, z)
        if decide(formula, names):
            return True
    return False


def _sqrt_bounds(value: Fraction) -> tuple[Fraction, Fraction]:
    denominator = 10**12
    root = isqrt(value.numerator * denominator**2 // value.denominator)
    lower = Fraction(root, denominator)
    return lower, lower if lower**2 == value else Fraction(root + 1, denominator)


def _reference_circle_bounds(query: EmergencySetupQuery) -> tuple[Fraction, Fraction] | None:
    reference = query.closer_than
    if (
        reference is None
        or type(reference.base) is not CircularBase
        or any(type(transport.base) is not CircularBase for transport in query.transports)
    ):
        return None
    bounds: list[tuple[Fraction, Fraction]] = []
    for transport in query.transports:
        transport_shape = Footprint.fixed(transport.base, transport.pose)
        dx = rational(reference.pose.position.x) - rational(transport.pose.position.x)
        dy = rational(reference.pose.position.y) - rational(transport.pose.position.y)
        lo, hi = _sqrt_bounds(dx * dx + dy * dy)
        radii = rational(reference.base.radius) + transport_shape.a
        lo, hi = max(Fraction(0), lo - radii), max(Fraction(0), hi - radii)
        gap = _vertical_gap(
            rational(reference.pose.position.z), rational(reference.volume.height), transport
        )
        bounds.append((_sqrt_bounds(lo * lo + gap * gap)[0], _sqrt_bounds(hi * hi + gap * gap)[1]))
    return min(lo for lo, _ in bounds), min(hi for _, hi in bounds)


def _witness_poses(query: EmergencySetupQuery, z: Fraction) -> tuple[Pose, ...]:
    source = query.passenger.pose
    poses = [Pose.at(source.position.x, source.position.y, float(z), source.facing.degrees)]
    poses.extend(
        Pose.at(floor.center_x_inches, floor.center_y_inches, float(z), floor.rotation_degrees)
        for terrain in query.terrain
        for floor in terrain.feature.floors
        if rational(floor.bottom_z_inches) == z
    )
    for transport in query.transports:
        center = transport.pose.position
        radius = transport.base.max_radius() + query.passenger.base.max_radius() + 0.01
        for x, y in (
            (center.x, center.y),
            (center.x + radius, center.y),
            (center.x - radius, center.y),
            (center.x, center.y + radius),
            (center.x, center.y - radius),
        ):
            for facing in (0.0, 90.0, transport.pose.facing.degrees):
                poses.append(Pose.at(x, y, float(z), facing))
    return tuple(dict.fromkeys(poses))
