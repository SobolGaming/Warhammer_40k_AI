"""Sufficient endpoint exclusion using every fixed-peer connectivity component.

Only plain circular measurement footprints are admitted. Height, paths, terrain
and all other endpoint duties are relaxed away. A negative result is inconclusive.
"""

from __future__ import annotations

from fractions import Fraction
from typing import TYPE_CHECKING

from warhammer40k_core.geometry.base import CircularBase
from warhammer40k_core.geometry.volume import Model

if TYPE_CHECKING:
    from warhammer40k_core.geometry.movement_reachability import MovementGoal

_SLACK = Fraction(1, 100_000_000)


def endpoint_excluded_by_connected_components(
    *, source: Model, peers: tuple[Model, ...], goal: MovementGoal, horizontal_inches: float
) -> bool:
    """Prove that no goal endpoint can connect the mover to every peer component.

    Enclosing disks and ignored height can add fixed-peer edges, never remove
    legal edges. Every connected full group must therefore attach the mover to
    each component of this relaxed graph. If one component's union of mover
    neighborhoods is disjoint from the entire goal union, no endpoint exists.
    All comparisons use exact rationals of the supplied binary dimensions, with
    outward slack. Overlap or unsupported geometry supplies no certificate.
    """
    if not peers or not goal.models:
        return False
    models = (source, *peers, *goal.models)
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
    return False


def _distance_squared(first: Model, second: Model) -> Fraction:
    a, b = first.pose.position, second.pose.position
    return (Fraction(a.x) - Fraction(b.x)) ** 2 + (Fraction(a.y) - Fraction(b.y)) ** 2
