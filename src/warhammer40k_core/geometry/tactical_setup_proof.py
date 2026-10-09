"""Joint continuous negative certificates for Tactical Disembark.

Every passenger varies simultaneously in x/y/z and facing. In particular z is
not restricted to the ground or enumerated floors. This is a documented
relaxation of legal setup, not a positive placement validator: board edges,
objectives, coherency and terrain collision are omitted, and noncircular
collisions are relaxed. Necessary elevated support constraints may be supplied
for rectangular terrain regions. UNSAT proves impossibility; SAT requires an owner-validated
witness and otherwise remains unresolved.
"""

from __future__ import annotations

from dataclasses import dataclass
from fractions import Fraction
from itertools import combinations

from warhammer40k_core.geometry.disembark_fit import base_fits_disembark_distance
from warhammer40k_core.geometry.physical_model import physical_prisms
from warhammer40k_core.geometry.placement_predicates import Footprint, PlacementPredicates, rational
from warhammer40k_core.geometry.pose import GeometryError
from warhammer40k_core.geometry.visibility_algebra import (
    TRUE,
    Formula,
    RealTerm,
    both,
    decide,
    either,
    term,
    variable,
)
from warhammer40k_core.geometry.volume import Model

# All tests below relax the owner's floating comparisons in the permissive
# direction. This is not a changed gameplay tolerance or a positive witness.
_SLACK = Fraction(1, 10_000_000)


def _validate_numeric_domain(query: TacticalSetupProofQuery) -> None:
    """Keep the negative certificate inside its conservative rounding envelope.

    This limits certificates, not admitted gameplay: the engine returns typed
    UNRESOLVED outside this domain. With each input magnitude at most 10,000,
    the necessary proximity constraint bounds any legal translated part to
    less than 100,000. The permissive 1e-7 length margin exceeds the accumulated
    binary64 rounding of the finite rotations, sums, distances and square roots
    used by the circular owner in this domain. Noncircular boundaries are never
    used as exact exclusion boundaries here.
    """
    values = [
        query.distance_inches,
        query.oversized_distance_inches,
        query.engagement_horizontal_inches,
        query.engagement_vertical_inches,
    ]
    for model in (*query.passengers, *query.transports, *query.blockers, *query.enemies):
        values.extend((model.pose.position.x, model.pose.position.y, model.pose.position.z))
        values.extend((model.base.max_radius(), model.volume.height))
        for part in model.body_parts:
            values.extend((part.offset_x_inches, part.offset_y_inches, part.bottom_inches))
            values.extend((part.height_inches, part.base.max_radius()))
    for region in query.support_regions:
        values.extend(region.bounds)
        for surface in region.surfaces:
            values.extend((*surface.bounds, surface.z_inches))
    if any(abs(value) > 10_000 for value in values):
        raise GeometryError("Tactical negative certificate exceeds its numeric proof domain.")


@dataclass(frozen=True, slots=True)
class TacticalSupportSurface:
    bounds: tuple[float, float, float, float]
    z_inches: float


@dataclass(frozen=True, slots=True)
class TacticalSupportRegion:
    """A rectangular no-overhang region and every one of its support surfaces.

    Surface bounds may be enclosing axis-aligned rectangles. This intentionally
    admits more support than the exact owner for rotated/nonrectangular cases.
    The engine supplies only actual rectangular region interiors, never the
    bounding rectangle of a nonrectangular terrain footprint.
    """

    bounds: tuple[float, float, float, float]
    surfaces: tuple[TacticalSupportSurface, ...]


@dataclass(frozen=True, slots=True)
class TacticalSetupProofQuery:
    passengers: tuple[Model, ...]
    transports: tuple[Model, ...]
    blockers: tuple[Model, ...]
    enemies: tuple[Model, ...]
    distance_inches: float
    oversized_distance_inches: float
    engagement_horizontal_inches: float
    engagement_vertical_inches: float
    support_regions: tuple[TacticalSupportRegion, ...] = ()


@dataclass(frozen=True, slots=True)
class _Prism:
    footprint: Footprint
    bottom: RealTerm
    top: RealTerm


def _moving_parts(model: Model, names: tuple[str, ...]) -> tuple[_Prism, ...]:
    x, y, z, c, s = (variable(name) for name in names)
    return (
        _Prism(Footprint.moving(model.base, x, y, c, s), z, z + rational(model.volume.height)),
        *(
            _Prism(
                Footprint.moving(
                    part.base,
                    x + c * rational(part.offset_x_inches) - s * rational(part.offset_y_inches),
                    y + s * rational(part.offset_x_inches) + c * rational(part.offset_y_inches),
                    c,
                    s,
                ),
                z + rational(part.bottom_inches),
                z + rational(part.bottom_inches + part.height_inches),
            )
            for part in model.body_parts
        ),
    )


def _fixed_parts(model: Model, *, measuring: bool) -> tuple[_Prism, ...]:
    models = model.rules_distance_subjects() if measuring else physical_prisms(model)
    return tuple(
        _Prism(
            Footprint.fixed(part.base, part.pose),
            term(rational(part.pose.position.z)),
            term(rational(part.pose.position.z + part.volume.height)),
        )
        for part in models
    )


def _outer_radius(shape: Footprint) -> Fraction:
    # a+b encloses every analytic rectangle/ellipse and their polygonal owners.
    return shape.a if shape.kind == "circle" else shape.a + shape.b


def _near(
    predicates: PlacementPredicates,
    first: _Prism,
    second: _Prism,
    distance: Fraction,
    *,
    whole_circle: bool = False,
    point_height: RealTerm | None = None,
) -> Formula:
    """Necessary proximity using enclosing disks; exact circular XY containment."""
    horizontal, vertical = predicates.scalar(), predicates.scalar()
    bottom = first.bottom if point_height is None else point_height
    top = first.top if point_height is None else point_height
    target = first.footprint
    source = second.footprint
    # A target center is always inside its convex footprint. Only a single
    # circular source permits subtracting the target radius for whole distance;
    # union coverage is deliberately relaxed to center coverage instead.
    allowance = horizontal + _outer_radius(source)
    allowance = allowance - target.a if whole_circle else allowance + _outer_radius(target)
    return both(
        horizontal.ge(0),
        vertical.ge(0),
        vertical.ge(second.bottom - top - _SLACK),
        vertical.ge(bottom - second.top - _SLACK),
        (horizontal**2 + vertical**2).le((distance + _SLACK) ** 2),
        allowance.ge(-_SLACK),
        ((target.x - source.x) ** 2 + (target.y - source.y) ** 2).le((allowance + _SLACK) ** 2),
    )


def _not_overlapping(first: _Prism, second: _Prism) -> Formula:
    if first.footprint.kind != "circle" or second.footprint.kind != "circle":
        # The ordinary owner uses polygon footprints for these pairs, whereas
        # the physical-body owner uses analytic separation. Omitting this
        # restriction includes both domains without assuming their equivalence.
        return TRUE
    a, b = first.footprint, second.footprint
    radius = max(Fraction(0), a.a + b.a - _SLACK)
    return either(
        first.top.le(second.bottom + _SLACK),
        second.top.le(first.bottom + _SLACK),
        ((a.x - b.x) ** 2 + (a.y - b.y) ** 2).ge(radius**2),
    )


def _unengaged(first: _Prism, second: _Prism, horizontal: float, vertical: float) -> Formula:
    a, b = first.footprint, second.footprint
    # Centers belong to all accepted support footprints. For circles the exact
    # radius strengthens the exclusion; other shapes retain a zero-radius
    # necessary condition instead of overstating polygon/analytic equivalence.
    radius = rational(horizontal) + (a.a if a.kind == "circle" else 0)
    radius += b.a if b.kind == "circle" else 0
    radius = max(Fraction(0), radius - _SLACK)
    return either(
        (first.bottom - second.top).ge(rational(vertical) - _SLACK),
        (second.bottom - first.top).ge(rational(vertical) - _SLACK),
        ((a.x - b.x) ** 2 + (a.y - b.y) ** 2).ge(radius**2),
    )


def _possible_support(base: _Prism, region: TacticalSupportRegion) -> Formula:
    """Necessary subset of the owner's elevated no-overhang endpoint rule.

    A base whose center is strictly inside a rectangular region intersects it.
    At positive z the owner therefore requires a touched support surface. Every
    actual surface is retained, even if its keyword policy forbids the model.
    Full containment implies center containment in the surface's bounding box;
    for circular support bases the four exact cardinal extrema strengthen that
    necessary condition. Ground/negative z remain unconstrained. Permissive
    margins include the owner's 1e-9 support-plane tolerance and rounded bounds.
    """
    x, y, z = base.footprint.x, base.footprint.y, base.bottom
    lo_x, lo_y, hi_x, hi_y = (rational(value) for value in region.bounds)
    radius = base.footprint.a if base.footprint.kind == "circle" else Fraction(0)
    supports: list[Formula] = []
    for surface in region.surfaces:
        sx0, sy0, sx1, sy1 = (rational(value) for value in surface.bounds)
        plane = rational(surface.z_inches)
        supports.append(
            both(
                z.ge(plane - _SLACK),
                z.le(plane + _SLACK),
                (x - radius).ge(sx0 - _SLACK),
                (x + radius).le(sx1 + _SLACK),
                (y - radius).ge(sy0 - _SLACK),
                (y + radius).le(sy1 + _SLACK),
            )
        )
    return either(
        z.le(_SLACK),
        x.le(lo_x + _SLACK),
        x.ge(hi_x - _SLACK),
        y.le(lo_y + _SLACK),
        y.ge(hi_y - _SLACK),
        *supports,
    )


def tactical_setup_is_excluded(query: TacticalSetupProofQuery) -> bool:
    """Only an UNSAT result is permission to conclude Tactical is impossible."""
    if not query.passengers or not query.transports:
        raise ValueError("Tactical setup proof requires passengers and Transport models.")
    _validate_numeric_domain(query)
    names = tuple(
        tuple(f"tactical_{i}_{axis}" for axis in "xyzcs") for i in range(len(query.passengers))
    )
    moving = tuple(
        _moving_parts(model, row) for model, row in zip(query.passengers, names, strict=True)
    )
    predicates = PlacementPredicates(prefix="tactical_aux")
    constraints: list[Formula] = []
    distance = rational(query.distance_inches)
    for model, parts, row in zip(query.passengers, moving, names, strict=True):
        c, s = variable(row[3]), variable(row[4])
        # Includes the actual rounded sine/cosine pair, as well as exact rotations.
        constraints.append(both((c * c + s * s).ge(1 - _SLACK), (c * c + s * s).le(1 + _SLACK)))
        measuring = parts if model.measures_every_part else parts[:1]
        alternatives: list[Formula] = []
        for carrier in query.transports:
            sources = _fixed_parts(carrier, measuring=True)
            whole: list[Formula] = []
            for part in measuring:
                heights = (part.bottom, part.top) if model.measures_every_part else (None,)
                for height in heights:
                    whole.append(
                        either(
                            *(
                                _near(
                                    predicates,
                                    part,
                                    source,
                                    distance,
                                    whole_circle=len(sources) == 1
                                    and part.footprint.kind == source.footprint.kind == "circle",
                                    point_height=height,
                                )
                                for source in sources
                            )
                        )
                    )
            alternatives.append(both(*whole))
        if not any(
            base_fits_disembark_distance(model.base, carrier.base, query.distance_inches)
            for carrier in query.transports
        ):
            alternatives.append(
                either(
                    *(
                        _near(predicates, part, source, rational(query.oversized_distance_inches))
                        for part in measuring
                        for carrier in query.transports
                        for source in _fixed_parts(carrier, measuring=True)
                    )
                )
            )
        constraints.append(either(*alternatives))
        constraints.extend(_possible_support(parts[0], region) for region in query.support_regions)
        constraints.extend(
            _not_overlapping(part, fixed)
            for part in parts
            for blocker in query.blockers
            for fixed in _fixed_parts(blocker, measuring=False)
        )
        constraints.extend(
            _unengaged(
                part, fixed, query.engagement_horizontal_inches, query.engagement_vertical_inches
            )
            for part in measuring
            for enemy in query.enemies
            for fixed in _fixed_parts(enemy, measuring=True)
        )
    constraints.extend(
        _not_overlapping(a, b)
        for first, second in combinations(moving, 2)
        for a in first
        for b in second
    )
    return not decide(
        both(*constraints), (*(name for row in names for name in row), *predicates.names)
    )
