"""Complete real-algebraic visibility of physical unions with clipped origins.

Target patches are a superset of exposed surfaces. Actual eligibility is proved
with an allowed origin and a ray that meets no other target component before
its endpoint. Each target point binds the origin union inside its existential;
full visibility and cover counterfactuals never combine per-part booleans.
"""

from __future__ import annotations

from fractions import Fraction

from warhammer40k_core.geometry.visibility_algebra import (
    TRUE,
    Formula,
    RealTerm,
    both,
    decide,
    either,
    implies,
    negate,
    quantified,
    term,
    variable,
)
from warhammer40k_core.geometry.visibility_exact import (
    CORRIDOR_RADIUS,
    RationalEllipse,
    RationalPoint3,
    VisibilityPrism,
    convex_polygon_parts,
)
from warhammer40k_core.geometry.visibility_formulas import (
    ModelDomain,
    Point,
    TargetPatch,
    corridor_clear_condition,
    scaled_domain_membership,
    target_surface_faces_origin,
    target_visibility_patches,
)
from warhammer40k_core.geometry.visibility_witnesses import target_part_candidates

type Bounds = tuple[Fraction, Fraction, Fraction, Fraction] | None


def allowed_origin(domain: ModelDomain, point: Point, bounds: Bounds) -> Formula:
    return both(
        domain.member(point),
        *(
            ()
            if bounds is None
            else (
                point[0].ge(bounds[0]),
                point[1].ge(bounds[1]),
                point[0].le(bounds[2]),
                point[1].le(bounds[3]),
            )
        ),
    )


def _blocker_member(prism: VisibilityPrism, point: Point, scale: RealTerm) -> Formula:
    if isinstance(prism.footprint, RationalEllipse):
        return scaled_domain_membership(ModelDomain.from_prism(prism), point, scale)
    return both(
        point[2].ge(scale * prism.lower),
        point[2].le(scale * prism.upper),
        either(
            *(
                both(
                    *(
                        (
                            (point[1] - scale * a[1]) * (b[0] - a[0])
                            - (point[0] - scale * a[0]) * (b[1] - a[1])
                        ).ge(0)
                        for a, b in zip(part, (*part[1:], part[0]), strict=True)
                    )
                )
                for part in convex_polygon_parts(prism.footprint)
            )
        ),
    )


def physical_corridor_clear_condition(
    origin: Point,
    target: Point,
    blockers: tuple[VisibilityPrism, ...],
    scale: RealTerm,
    *,
    planar: bool,
    vertical_possible: bool = True,
) -> tuple[Formula, tuple[str, ...]]:
    if not blockers:
        return TRUE, ()
    regular, auxiliaries = corridor_clear_condition(origin, target, blockers, scale, planar=planar)
    if not vertical_possible:
        return regular, auxiliaries
    length = (origin[0] - target[0]) ** 2 + (origin[1] - target[1]) ** 2
    # A vertical corridor is a closed disk swept between the endpoints, as in
    # VisibilityPrism.intersects_corridor. Its boundary remains blocked.
    t, x, y = variable("vertical_t"), variable("vertical_x"), variable("vertical_y")
    point = (origin[0] + scale * x, origin[1] + scale * y, origin[2] + t * (target[2] - origin[2]))
    contact = both(
        t.ge(0),
        t.le(1),
        (x * x + y * y).le(CORRIDOR_RADIUS**2),
        either(*(_blocker_member(b, point, scale) for b in blockers)),
    )
    vertical = both(
        length.eq(0),
        negate(quantified("exists", ("vertical_t", "vertical_x", "vertical_y"), contact)),
    )
    return either(regular, vertical), auxiliaries


def decide_physical_any(
    observers: tuple[ModelDomain, ...],
    targets: tuple[ModelDomain, ...],
    blockers: tuple[VisibilityPrism, ...],
    bounds: Bounds,
) -> bool:
    o = (variable("ox"), variable("oy"), variable("oz"))
    q = (variable("tx"), variable("ty"), variable("tz"))
    clear, auxiliary = physical_corridor_clear_condition(
        o,
        q,
        blockers,
        term(1),
        planar=False,
        vertical_possible=not domains_strictly_separated(observers, targets),
    )
    return decide(
        both(
            either(*(allowed_origin(d, o, bounds) for d in observers)),
            either(*(d.member(q) for d in targets)),
            clear,
        ),
        ("ox", "oy", "oz", "tx", "ty", "tz", *auxiliary),
    )


def domains_strictly_separated(
    observers: tuple[ModelDomain, ...], targets: tuple[ModelDomain, ...]
) -> bool:
    """A sufficient XY disjointness proof eliminates impossible vertical rays."""

    def interval(domain: ModelDomain, axis: int) -> tuple[Fraction, Fraction]:
        values = tuple(p[axis] for p in domain.vertices())
        return min(values), max(values)

    return all(
        any(
            interval(o, a)[1] < interval(t, a)[0] or interval(t, a)[1] < interval(o, a)[0]
            for a in (0, 1)
        )
        for o in observers
        for t in targets
    )


def _self_clear(
    origin: Point, patch: TargetPatch, index: int, targets: tuple[ModelDomain, ...]
) -> Formula:
    t = variable("self_t")
    point = tuple(origin[i] + t * (patch.point[i] - origin[i]) for i in range(3))
    # Closed components, rather than their separate interiors, correctly hide
    # touching seams and nearer tangent components. The endpoint is excluded.
    earlier_contact = both(
        t.ge(0),
        t.lt(1),
        either(
            *(
                scaled_domain_membership(d, (point[0], point[1], point[2]), patch.scale)
                for j, d in enumerate(targets)
                if j != index
            )
        ),
    )
    return both(
        target_surface_faces_origin(targets[index], origin, patch),
        negate(quantified("exists", ("self_t",), earlier_contact)),
    )


def part_visibility_condition(
    observers: tuple[ModelDomain, ...],
    targets: tuple[ModelDomain, ...],
    bounds: Bounds,
    index: int,
    patch: TargetPatch,
    blockers: tuple[VisibilityPrism, ...],
) -> tuple[Formula, tuple[str, ...]]:
    names = ("ox", "oy") if patch.planar else ("ox", "oy", "oz")
    o = (
        variable("ox"),
        variable("oy"),
        term((targets[index].lower + targets[index].upper) / 2) if patch.planar else variable("oz"),
    )
    scaled = (o[0] * patch.scale, o[1] * patch.scale, o[2] * patch.scale)
    clear, auxiliaries = physical_corridor_clear_condition(
        scaled,
        patch.point,
        blockers,
        patch.scale,
        planar=patch.planar,
        vertical_possible=not domains_strictly_separated(observers, (targets[index],)),
    )
    return (
        both(
            either(*(allowed_origin(d, o, bounds) for d in observers)),
            _self_clear(scaled, patch, index, targets),
            clear,
        ),
        (*names, *auxiliaries),
    )


def part_visible(
    observers: tuple[ModelDomain, ...],
    targets: tuple[ModelDomain, ...],
    bounds: Bounds,
    index: int,
    patch: TargetPatch,
    blockers: tuple[VisibilityPrism, ...],
) -> Formula:
    condition, names = part_visibility_condition(observers, targets, bounds, index, patch, blockers)
    return quantified("exists", names, condition)


def physical_patches(
    observers: tuple[ModelDomain, ...],
    targets: tuple[ModelDomain, ...],
    blockers: tuple[VisibilityPrism, ...],
) -> tuple[tuple[int, TargetPatch], ...]:
    # Unclipped support only restricts this *superset*. F is recomputed with
    # actual allowed origins, including cap eligibility and union self-clearance.
    first = targets[0]
    planar = all(
        d.lower == first.lower and d.upper == first.upper for d in (*observers, *targets)
    ) and all(b.lower <= first.lower and b.upper >= first.upper for b in blockers)
    return tuple(
        dict.fromkeys(
            (i, p)
            for i, d in enumerate(targets)
            for o in observers
            for p in target_visibility_patches(o, d, planar=planar)
        )
    )


def decide_physical_full(
    observers: tuple[ModelDomain, ...],
    targets: tuple[ModelDomain, ...],
    blockers: tuple[VisibilityPrism, ...],
    bounds: Bounds,
) -> bool:
    if not blockers:
        return True
    if prove_full_by_fixed_origins(observers, targets, blockers, bounds):
        return True
    return all(
        decide(
            quantified(
                "forall",
                p.parameters,
                implies(
                    both(p.domain, part_visible(observers, targets, bounds, i, p, ())),
                    part_visible(observers, targets, bounds, i, p, blockers),
                ),
            )
        )
        for i, p in physical_patches(observers, targets, blockers)
    )


def prove_full_by_fixed_origins(
    observers: tuple[ModelDomain, ...],
    targets: tuple[ModelDomain, ...],
    blockers: tuple[VisibilityPrism, ...],
    bounds: Bounds,
) -> bool:
    """Sufficient continuum proof, never a sampled negative visibility answer.

    Each universally quantified patch point must have a self-valid clear ray
    from one actual allowed origin. Failure continues to complete authority.
    A single target component keeps this proof free of union exposure shortcuts.
    """
    if len(targets) != 1:
        return False
    origins = _fixed_origins(observers, bounds)
    if not origins:
        return False
    return all(
        decide(
            quantified(
                "forall",
                patch.parameters,
                implies(
                    patch.domain, _fixed_part_witnesses(origins, targets, index, patch, blockers)
                ),
            )
        )
        for index, patch in physical_patches(observers, targets, blockers)
    )


def _fixed_origins(
    observers: tuple[ModelDomain, ...], bounds: Bounds
) -> tuple[RationalPoint3, ...]:
    origins: list[RationalPoint3] = []
    for domain in observers:
        local = (
            ((-1, 0), (1, 0), (0, -1), (0, 1), (0, 0))
            if domain.curved
            else ((-1, -1), (-1, 1), (1, -1), (1, 1), (0, 0))
        )
        for u, v in local:
            for z in (domain.lower, (domain.lower + domain.upper) / 2, domain.upper):
                coordinates = (
                    domain.center[0] + domain.axes[0][0] * u + domain.axes[1][0] * v,
                    domain.center[1] + domain.axes[0][1] * u + domain.axes[1][1] * v,
                    z,
                )
                point = (term(coordinates[0]), term(coordinates[1]), term(coordinates[2]))
                if allowed_origin(domain, point, bounds) == TRUE:
                    origins.append(coordinates)
    return tuple(dict.fromkeys(origins))


def _fixed_part_witnesses(
    origins: tuple[RationalPoint3, ...],
    targets: tuple[ModelDomain, ...],
    index: int,
    patch: TargetPatch,
    blockers: tuple[VisibilityPrism, ...],
) -> Formula:
    vertices = targets[index].vertices()
    x0, x1 = min(x for x, _ in vertices), max(x for x, _ in vertices)
    y0, y1 = min(y for _, y in vertices), max(y for _, y in vertices)
    alternatives: list[Formula] = []
    for point in origins:
        scaled = tuple(term(c) * patch.scale for c in point)
        origin = (scaled[0], scaled[1], scaled[2])
        nonvertical = point[0] < x0 or point[0] > x1 or point[1] < y0 or point[1] > y1
        clear, auxiliary = physical_corridor_clear_condition(
            origin,
            patch.point,
            blockers,
            patch.scale,
            planar=patch.planar,
            vertical_possible=not nonvertical,
        )
        alternatives.append(
            quantified("exists", auxiliary, both(_self_clear(origin, patch, index, targets), clear))
        )
    return either(*alternatives)


def _point_visible(
    observers: tuple[ModelDomain, ...],
    targets: tuple[ModelDomain, ...],
    bounds: Bounds,
    index: int,
    coordinates: RationalPoint3,
    blockers: tuple[VisibilityPrism, ...],
) -> bool:
    point = (term(coordinates[0]), term(coordinates[1]), term(coordinates[2]))
    target = targets[index]
    u, v = target.local(point)
    # Keep the point's actual height; no projection is used for this certificate.
    patch = TargetPatch((), target.member(point), point, u, v, term(1), False)
    condition, names = part_visibility_condition(observers, targets, bounds, index, patch, blockers)
    return decide(both(patch.domain, condition), names)


def _prove_no_counterfactual_by_fixed_origins(
    observers: tuple[ModelDomain, ...],
    targets: tuple[ModelDomain, ...],
    blockers: tuple[VisibilityPrism, ...],
    remaining: tuple[VisibilityPrism, ...],
    bounds: Bounds,
) -> bool:
    patches = physical_patches(observers, targets, blockers)
    # This sufficient implication stays quantifier-free before existential
    # closure. Curved blockers and union self-contact retain complete authority.
    if (
        len(targets) != 1
        or not domains_strictly_separated(observers, targets)
        or any(not p.planar for _, p in patches)
        or any(b.lower > targets[0].lower or b.upper < targets[0].upper for b in remaining)
        or any(isinstance(b.footprint, RationalEllipse) for b in (*blockers, *remaining))
    ):
        return False
    origins = _fixed_origins(observers, bounds)
    if not origins:
        return False
    for index, patch in patches:
        visible_remaining, names = part_visibility_condition(
            observers, targets, bounds, index, patch, remaining
        )
        fixed_combined = _fixed_part_witnesses(origins, targets, index, patch, blockers)
        # UNSAT proves every remaining-visible point also has an actual clear
        # combined-blocker witness. A SAT result proves nothing about causality.
        if decide(
            both(patch.domain, visible_remaining, negate(fixed_combined)),
            (*patch.parameters, *names),
        ):
            return False
    return True


def decide_physical_counterfactual(
    observers: tuple[ModelDomain, ...],
    targets: tuple[ModelDomain, ...],
    blockers: tuple[VisibilityPrism, ...],
    remaining: tuple[VisibilityPrism, ...],
    bounds: Bounds,
) -> bool:
    for index, target in enumerate(targets):
        candidates = dict.fromkeys(
            point
            for observer in observers
            for point in target_part_candidates(observer, target, blockers)
        )
        for point in candidates:
            if _point_visible(
                observers, targets, bounds, index, point, remaining
            ) and not _point_visible(observers, targets, bounds, index, point, blockers):
                return True
    if _prove_no_counterfactual_by_fixed_origins(observers, targets, blockers, remaining, bounds):
        return False
    return any(
        decide(
            quantified(
                "exists",
                p.parameters,
                both(
                    p.domain,
                    part_visible(observers, targets, bounds, i, p, ()),
                    negate(part_visible(observers, targets, bounds, i, p, blockers)),
                    part_visible(observers, targets, bounds, i, p, remaining),
                ),
            )
        )
        for i, p in physical_patches(observers, targets, blockers)
    )
