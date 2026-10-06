"""Continuous negative endpoint certificates for source-directed objective movement.

Translation, every facing and every supported elevation remain possible. Paths,
pivot costs, support footprints and engagement exclusions are relaxed. Only UNSAT
is a certificate; SAT never grants a move and still requires an ordinary witness.
"""

from __future__ import annotations

from fractions import Fraction
from itertools import combinations
from typing import TYPE_CHECKING

from warhammer40k_core.geometry.base import CircularBase, RectangularBase
from warhammer40k_core.geometry.endpoint_support import endpoint_support_elevations
from warhammer40k_core.geometry.objective_path_proof import objective_path_bounds
from warhammer40k_core.geometry.physical_model import physical_prisms
from warhammer40k_core.geometry.physical_predicates import nonoverlapping
from warhammer40k_core.geometry.placement_predicates import Footprint, PlacementPredicates, rational
from warhammer40k_core.geometry.pose import Pose
from warhammer40k_core.geometry.visibility_algebra import (
    Formula,
    RealTerm,
    both,
    decide,
    either,
    negate,
    term,
    variable,
)
from warhammer40k_core.geometry.volume import Model

if TYPE_CHECKING:
    from warhammer40k_core.geometry.movement_reachability import MovementReachabilityQuery

_SLACK = Fraction(1, 1_000_000_000)


def _parts(
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


def _gap(bottom: float, top: float, other_bottom: float, other_top: float) -> float:
    return max(0.0, other_bottom - top, bottom - other_top)


def _clear(predicates: PlacementPredicates, first: Footprint, second: Footprint) -> Formula:
    # Negating the quantifier-free circle/rectangle proximity avoids introducing
    # a separating-line search. Its two-nanoinch clearance relaxation contains
    # every endpoint accepted by the shared one-nanoinch collision tolerance.
    if first.kind == "circle" and second.kind == "rectangle" and first.a > 2 * _SLACK:
        return negate(predicates.point_near(first.x, first.y, second, term(first.a - 2 * _SLACK)))
    return nonoverlapping(predicates, first, second)


def objective_endpoint_excluded(query: MovementReachabilityQuery) -> bool:
    """Prove a marker goal impossible, without changing other reachability owners."""
    if query.goal.disk is None:
        return False
    source = query.path_context.moving_model
    budget = query.path_context.movement_distance_budget_inches
    if budget is None:
        return False
    marker_pose, marker_base = query.goal.disk
    marker = Footprint.fixed(marker_base, marker_pose)
    terrain = query.terrain_context
    # Unclassified raw volumes have no physical endpoint exclusion in this owner.
    # Matching floor/support identities also permit contact and are relaxed away.
    walls = tuple(
        wall
        for feature in terrain.terrain_features
        for wall in feature.wall_volumes()
        if wall.terrain_id
        not in {f"{feature.feature_id}:{floor.floor_id}" for floor in feature.floors}
    )
    x, y, c, s = (
        variable(name) for name in ("objective_x", "objective_y", "objective_c", "objective_s")
    )
    predicates = PlacementPredicates(prefix="objective_aux")
    alternatives: list[Formula] = []
    for z in endpoint_support_elevations(
        terrain=terrain.terrain, features=terrain.terrain_features
    ):
        parts = _parts(source, x, y, c, s, z)
        measuring_parts = parts if source.measures_every_part else parts[:1]
        targets: list[Formula] = []
        for shape, bottom, top in measuring_parts:
            vertical = _gap(bottom, top, marker_pose.position.z, marker_pose.position.z)
            spatial = query.goal.spatial_region_range_inches
            if spatial is not None:
                horizontal = predicates.scalar()
                targets.append(
                    both(
                        horizontal.ge(0),
                        (horizontal**2 + rational(vertical) ** 2).le(rational(spatial) ** 2),
                        predicates.near(shape, marker, horizontal),
                    )
                )
            elif vertical <= query.goal.vertical_inches + 1e-9:
                targets.append(
                    predicates.near(
                        shape, marker, term(rational(query.goal.horizontal_inches + 1e-9))
                    )
                )
        position = source.pose.position
        distance = (x - rational(position.x)) ** 2 + (y - rational(position.y)) ** 2
        if not query.path_context.ignores_vertical_distance:
            distance = distance + rational(z - position.z) ** 2
        constraints = [
            distance.le(rational(budget + 1e-8) ** 2),
            either(*targets),
            objective_path_bounds(query, x, y, z),
        ]
        for shape, bottom, top in parts:
            for wall in walls:
                if top <= wall.bottom_center.z + 1e-9 or bottom >= wall.top_z_inches() - 1e-9:
                    continue
                constraints.append(
                    _clear(
                        predicates,
                        shape,
                        Footprint.fixed(
                            RectangularBase(length=wall.width, width=wall.depth),
                            Pose.at(
                                wall.bottom_center.x,
                                wall.bottom_center.y,
                                facing_degrees=wall.rotation_degrees,
                            ),
                        ),
                    )
                )
        # A proposed unit endpoint fixes its peers. Original external blockers
        # stay fixed too; replace peers by identity to avoid constraining them at
        # both their original and proposed positions.
        blockers = {
            m.model_id: m
            for m in (
                *query.path_context.friendly_models,
                *query.path_context.enemy_models,
                *query.coherent_models,
            )
        }
        for blocker in blockers.values():
            for other in physical_prisms(blocker):
                other_bottom, other_top = other.volume.vertical_interval(other.pose)
                for shape, bottom, top in parts:
                    if top < other_bottom or other_top < bottom:
                        continue
                    constraints.append(
                        _clear(predicates, shape, Footprint.fixed(other.base, other.pose))
                    )
        if query.coherent_models:
            neighbors: list[Formula] = []
            for peer in query.coherent_models:
                peer_parts = (
                    peer.rules_distance_subjects()
                    if peer.measures_every_part and peer.body_parts
                    else (peer,)
                )
                near: list[Formula] = []
                for shape, bottom, top in measuring_parts:
                    for other in peer_parts:
                        ob, ot = other.volume.vertical_interval(other.pose)
                        if _gap(bottom, top, ob, ot) <= query.coherency_vertical_inches + 1e-9:
                            near.append(
                                predicates.near(
                                    shape,
                                    Footprint.fixed(other.base, other.pose),
                                    term(rational(query.coherency_horizontal_inches + 1e-9)),
                                )
                            )
                neighbors.append(either(*near))
            count = min(query.coherency_neighbor_count, len(neighbors))
            constraints.append(either(*(both(*group) for group in combinations(neighbors, count))))
        alternatives.append(both(*constraints))
    orientation = (
        both()
        if type(source.base) is CircularBase and not source.body_parts
        else (c * c + s * s).eq(1)
    )
    return not decide(
        both(orientation, either(*alternatives)),
        ("objective_x", "objective_y", "objective_c", "objective_s", *predicates.names),
    )
