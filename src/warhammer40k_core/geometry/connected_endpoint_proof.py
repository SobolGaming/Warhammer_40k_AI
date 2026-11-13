"""Sufficient endpoint exclusion using every fixed-peer connectivity component.

Only plain circular geometry is admitted. Connectivity, occupied blockers and
support bounds form a superset of legal endpoints. A negative result is inconclusive.
"""

from __future__ import annotations

from fractions import Fraction
from typing import TYPE_CHECKING

from warhammer40k_core.geometry.base import CircularBase
from warhammer40k_core.geometry.endpoint_support import endpoint_support_elevations
from warhammer40k_core.geometry.terrain import TerrainFeatureDefinition, TerrainVolume
from warhammer40k_core.geometry.visibility_algebra import Formula, both, decide, either, variable
from warhammer40k_core.geometry.volume import Model

if TYPE_CHECKING:
    from warhammer40k_core.geometry.movement_reachability import MovementGoal

_SLACK = Fraction(1, 100_000_000)


def endpoint_excluded_by_connected_components(
    *,
    source: Model,
    peers: tuple[Model, ...],
    goal: MovementGoal,
    horizontal_inches: float,
    blockers: tuple[Model, ...] = (),
    terrain: tuple[TerrainVolume, ...] = (),
    terrain_features: tuple[TerrainFeatureDefinition, ...] = (),
) -> bool:
    """Prove that no goal endpoint can connect the mover to every peer component.

    Enclosing disks and ignored height can add fixed-peer edges, never remove
    legal edges. Every connected full group must therefore attach the mover to
    each component of this relaxed graph. If one component's union of mover
    neighborhoods is disjoint from the entire goal union, no endpoint exists.
    Overlapping regions additionally admit a continuous exclusion against fixed
    path blockers and relaxed support bounds. These blockers must be occupied at
    this model's physical execution boundary, not merely submitted final peers.
    All comparisons use exact rationals with outward slack. SAT is inconclusive.
    """
    if not peers or not goal.models:
        return False
    models = (source, *peers, *goal.models, *blockers)
    if any(
        type(model.base) is not CircularBase or model.body_parts or model.measures_every_part
        for model in models
    ):
        return False
    radii = tuple(Fraction(model.base.max_radius()) for model in models)
    mover_radius = radii[0]
    coherent = Fraction(horizontal_inches) + _SLACK
    goal_range = Fraction(
        goal.horizontal_inches if goal.range_inches is None else goal.range_inches
    )
    remaining = set(range(len(peers)))
    components: list[tuple[Model, ...]] = []
    while remaining:
        pending = [min(remaining)]
        component: set[int] = set()
        while pending:
            index = pending.pop()
            if index in component:
                continue
            component.add(index)
            pending.extend(
                other
                for other in remaining - component
                if _distance_squared(peers[index], peers[other])
                <= (radii[index + 1] + radii[other + 1] + coherent) ** 2
            )
        remaining -= component
        components.append(tuple(peers[index] for index in sorted(component)))
        if all(
            _distance_squared(peers[index], target)
            > (
                2 * mover_radius
                + radii[index + 1]
                + Fraction(target.base.max_radius())
                + coherent
                + goal_range
                + _SLACK
            )
            ** 2
            for index in component
            for target in goal.models
        ):
            return True
    # Keep the additional solver bounded to disconnected fixed-peer layouts.
    # A single relaxed component, absent blockers or unsupported geometry remains
    # ordinary search; this proof is deliberately sufficient, not complete.
    return (
        len(components) > 1
        and bool(blockers)
        and _blocked_overlap_excluded(
            source, tuple(components), blockers, goal, coherent, terrain, terrain_features
        )
    )


def _blocked_overlap_excluded(
    source: Model,
    components: tuple[tuple[Model, ...], ...],
    blockers: tuple[Model, ...],
    goal: MovementGoal,
    coherent: Fraction,
    terrain: tuple[TerrainVolume, ...],
    features: tuple[TerrainFeatureDefinition, ...],
) -> bool:
    x, y = variable("connected_x"), variable("connected_y")
    radius = Fraction(source.base.max_radius())

    def disk(model: Model, reach: Fraction) -> Formula:
        p = model.pose.position
        return ((x - Fraction(p.x)) ** 2 + (y - Fraction(p.y)) ** 2).le(reach**2)

    neighborhoods = tuple(
        either(*(disk(m, radius + Fraction(m.base.max_radius()) + coherent) for m in group))
        for group in components
    )
    horizontal = (
        Fraction(goal.horizontal_inches if goal.range_inches is None else goal.range_inches)
        + _SLACK
    )
    vertical = (
        Fraction(goal.vertical_inches if goal.range_inches is None else goal.range_inches) + _SLACK
    )
    height = Fraction(source.volume.height)
    for elevation in endpoint_support_elevations(terrain=terrain, features=features):
        z = Fraction(elevation)
        goals = tuple(
            disk(m, radius + Fraction(m.base.max_radius()) + horizontal)
            for m in goal.models
            if z <= Fraction(m.pose.position.z) + Fraction(m.volume.height) + vertical
            and z + height >= Fraction(m.pose.position.z) - vertical
        )
        if not goals:
            continue
        constraints = [either(*goals), *neighborhoods]
        for blocker in blockers:
            p = blocker.pose.position
            if z > Fraction(p.z) + Fraction(blocker.volume.height) or z + height < Fraction(p.z):
                continue
            separation = max(Fraction(0), radius + Fraction(blocker.base.max_radius()) - _SLACK)
            constraints.append(
                ((x - Fraction(p.x)) ** 2 + (y - Fraction(p.y)) ** 2).ge(separation**2)
            )
        if elevation != 0:
            # Intersection with physical support is necessary. Expanded bounding
            # boxes include every such contact, ignoring containment/terrain rules.
            bounds = [
                (
                    min(p[0] for p in polygon),
                    min(p[1] for p in polygon),
                    max(p[0] for p in polygon),
                    max(p[1] for p in polygon),
                )
                for feature in features
                for surface in feature.support_surfaces(no_overhang_required=False)
                if surface.z_inches == elevation
                for polygon in (surface.footprint_polygon(),)
            ]
            bounds.extend(
                (
                    v.bottom_center.x - v.width - v.depth,
                    v.bottom_center.y - v.width - v.depth,
                    v.bottom_center.x + v.width + v.depth,
                    v.bottom_center.y + v.width + v.depth,
                )
                for v in terrain
                if v.top_z_inches() == elevation
            )
            constraints.append(
                either(
                    *(
                        both(
                            x.ge(Fraction(a) - radius - _SLACK),
                            y.ge(Fraction(b) - radius - _SLACK),
                            x.le(Fraction(c) + radius + _SLACK),
                            y.le(Fraction(d) + radius + _SLACK),
                        )
                        for a, b, c, d in bounds
                    )
                )
            )
        if decide(both(*constraints), ("connected_x", "connected_y")):
            return False
    return True


def _distance_squared(first: Model, second: Model) -> Fraction:
    a, b = first.pose.position, second.pose.position
    return (Fraction(a.x) - Fraction(b.x)) ** 2 + (Fraction(a.y) - Fraction(b.y)) ** 2
