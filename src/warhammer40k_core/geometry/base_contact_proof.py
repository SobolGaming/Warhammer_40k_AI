"""Continuous endpoint certificates for overhang contact.

The search relaxes terrain, other models, coherency and pivot cost. A negative
answer therefore proves that no legal move can get closer. A positive answer
is deliberately inconclusive until the ordinary path owner supplies a witness.
"""

from __future__ import annotations

from fractions import Fraction
from functools import lru_cache
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from warhammer40k_core.geometry.movement_reachability import MovementReachabilityQuery

from warhammer40k_core.geometry.physical_model import physical_prisms
from warhammer40k_core.geometry.physical_predicates import nonoverlapping
from warhammer40k_core.geometry.placement_predicates import Footprint, PlacementPredicates, rational
from warhammer40k_core.geometry.pose import GeometryError
from warhammer40k_core.geometry.visibility_algebra import (
    Formula,
    RealTerm,
    both,
    decide,
    either,
    variable,
)
from warhammer40k_core.geometry.volume import Model


def _moving_parts(
    source: Model, x: RealTerm, y: RealTerm, c: RealTerm, s: RealTerm, z: float
) -> tuple[tuple[Footprint, float, float], ...]:
    return (
        (Footprint.moving(source.base, x, y, c, s), z, z + source.volume.height),
        *(
            (
                Footprint.moving(
                    part.base,
                    x + c * rational(part.offset_x_inches) - s * rational(part.offset_y_inches),
                    y + s * rational(part.offset_x_inches) + c * rational(part.offset_y_inches),
                    c,
                    s,
                ),
                z + part.bottom_inches,
                z + part.bottom_inches + part.height_inches,
            )
            for part in source.body_parts
        ),
    )


@lru_cache(maxsize=512)
def closer_body_endpoint_exists(
    source: Model,
    enemy: Model,
    maximum_distance: float,
    current_distance: float,
    supported_elevations: tuple[float, ...],
) -> bool:
    """SAT is a candidate, UNSAT a certificate over all positions and facings."""
    x, y, c, s = (variable(name) for name in ("contact_x", "contact_y", "contact_c", "contact_s"))
    predicates = PlacementPredicates(prefix="contact_aux")
    base = Footprint.moving(source.base, x, y, c, s)
    target = Footprint.fixed(enemy.base, enemy.pose)
    limit = rational(current_distance) - Fraction(1, 100_000_000)
    constraints = [
        (c * c + s * s).eq(1),
        (
            (x - rational(source.pose.position.x)) ** 2
            + (y - rational(source.pose.position.y)) ** 2
        ).le((rational(maximum_distance) + Fraction(1, 100_000_000)) ** 2),
    ]
    elevations: list[Formula] = []
    for z in supported_elevations:
        vertical_gap = max(
            0.0,
            enemy.pose.position.z - z - source.volume.height,
            z - enemy.pose.position.z - enemy.volume.height,
        )
        if limit < rational(vertical_gap):
            continue
        horizontal = predicates.scalar()
        rows = [
            horizontal.ge(0),
            (horizontal**2 + rational(vertical_gap) ** 2).le(limit**2),
            predicates.near(base, target, horizontal),
        ]
        for shape, bottom, top in _moving_parts(source, x, y, c, s, z):
            for target_part in physical_prisms(enemy):
                other_bottom, other_top = target_part.volume.vertical_interval(target_part.pose)
                if top < other_bottom or other_top < bottom:
                    continue
                rows.append(
                    nonoverlapping(
                        predicates, shape, Footprint.fixed(target_part.base, target_part.pose)
                    )
                )
        elevations.append(both(*rows))
    return decide(
        both(*constraints, either(*elevations)),
        ("contact_x", "contact_y", "contact_c", "contact_s", *predicates.names),
    )


def endpoint_excluded_by_bodies(
    *,
    source: Model,
    targets: tuple[Model, ...],
    range_inches: float,
    budget: float,
    supported_elevations: tuple[float, ...],
) -> bool:
    """A union goal is excluded only when every target has a body certificate."""
    return bool(targets) and all(
        target.body_parts
        and not closer_body_endpoint_exists(
            source,
            target,
            budget,
            range_inches + 2e-8,
            supported_elevations,
        )
        for target in targets
    )


def contact_constraints_exclude_endpoint(query: MovementReachabilityQuery) -> bool:
    """Negative certificate for simultaneous contact and source target obligations.

    This relaxes path, collision, support footprints and coherency. All supported
    elevations, translations and orientations remain possible. Ignoring non-model
    goals is an explicit relaxation, so only UNSAT can certify impossibility.
    """
    from warhammer40k_core.geometry.endpoint_support import endpoint_support_elevations
    from warhammer40k_core.geometry.movement_reachability import MovementGoal
    from warhammer40k_core.geometry.visibility_algebra import term

    source = query.path_context.moving_model
    budget = query.path_context.movement_distance_budget_inches
    if budget is None:
        raise GeometryError("Contact endpoint proof requires a movement budget.")
    x, y, c, s = (
        variable(name) for name in ("constraint_x", "constraint_y", "constraint_c", "constraint_s")
    )
    predicates = PlacementPredicates(prefix="constraint_aux")
    base = Footprint.moving(source.base, x, y, c, s)
    levels = endpoint_support_elevations(
        terrain=query.terrain_context.terrain, features=query.terrain_context.terrain_features
    )
    alternatives: list[Formula] = []
    for z in levels:

        def near_goal(goal: MovementGoal, elevation: float = z) -> Formula:
            if not goal.models:
                return both()
            rows: list[Formula] = []
            for target in goal.models:
                gap = max(
                    0.0,
                    target.pose.position.z - elevation - source.volume.height,
                    elevation - target.pose.position.z - target.volume.height,
                )
                if goal.range_inches is None:
                    if gap <= goal.vertical_inches + 1e-9:
                        rows.append(
                            predicates.near(
                                base,
                                Footprint.fixed(target.base, target.pose),
                                term(rational(goal.horizontal_inches + 1e-8)),
                            )
                        )
                elif gap <= goal.range_inches + 1e-8:
                    horizontal = predicates.scalar()
                    rows.append(
                        both(
                            horizontal.ge(0),
                            (horizontal**2 + rational(gap) ** 2).le(
                                rational(goal.range_inches + 1e-8) ** 2
                            ),
                            predicates.near(
                                base, Footprint.fixed(target.base, target.pose), horizontal
                            ),
                        )
                    )
            return either(*rows)

        constraints = [near_goal(query.goal), *(near_goal(g) for g in query.required_goals)]
        if query.closer_target_groups:
            constraints.append(
                either(
                    *(
                        near_goal(
                            MovementGoal(
                                models=group, range_inches=min(source.range_to(m) for m in group)
                            )
                        )
                        for group in query.closer_target_groups
                    )
                )
            )
        alternatives.append(both(*constraints))
    return not decide(
        both(
            (c * c + s * s).eq(1),
            (
                (x - rational(source.pose.position.x)) ** 2
                + (y - rational(source.pose.position.y)) ** 2
            ).le(rational(budget + 1e-8) ** 2),
            either(*alternatives),
        ),
        ("constraint_x", "constraint_y", "constraint_c", "constraint_s", *predicates.names),
    )
