"""Shared physical visibility inputs, cache, proofs and source-group causality."""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, replace
from fractions import Fraction
from functools import lru_cache
from typing import TypedDict, cast

from warhammer40k_core.geometry.continuous_visibility import (
    VISIBILITY_ALGORITHM_ID,
    ContinuousVisibilityEvidence,
    prism_fingerprint_payload,
    resolve_visibility_pair_uncached,
)
from warhammer40k_core.geometry.physical_model import physical_prisms
from warhammer40k_core.geometry.physical_visibility_formulas import (
    decide_physical_any,
    decide_physical_counterfactual,
    decide_physical_full,
)
from warhammer40k_core.geometry.pose import GeometryError
from warhammer40k_core.geometry.visibility_certificates import (
    all_corridors_blocked_by_circle,
    all_corridors_blocked_by_endpoint_containment,
    all_corridors_blocked_by_plane,
)
from warhammer40k_core.geometry.visibility_exact import RationalPoint3, VisibilityPrism
from warhammer40k_core.geometry.visibility_formulas import ModelDomain
from warhammer40k_core.geometry.visibility_occlusion import source_group_obscures
from warhammer40k_core.geometry.visibility_shapes import model_visibility_prism
from warhammer40k_core.geometry.visibility_witnesses import positive_ray_candidates
from warhammer40k_core.geometry.volume import Model


class BattlefieldVisibilityBoundsPayload(TypedDict):
    min_x: str
    min_y: str
    max_x: str
    max_y: str


@dataclass(frozen=True, slots=True)
class BattlefieldVisibilityBounds:
    min_x: Fraction
    min_y: Fraction
    max_x: Fraction
    max_y: Fraction

    def __post_init__(self) -> None:
        if any(type(v) is not Fraction for v in self.values):
            raise GeometryError("Visibility battlefield bounds require exact rational coordinates.")
        if self.min_x >= self.max_x or self.min_y >= self.max_y:
            raise GeometryError("Visibility battlefield bounds require positive width and depth.")

    @property
    def values(self) -> tuple[Fraction, Fraction, Fraction, Fraction]:
        return (self.min_x, self.min_y, self.max_x, self.max_y)

    def contains(self, point: RationalPoint3) -> bool:
        return self.min_x <= point[0] <= self.max_x and self.min_y <= point[1] <= self.max_y

    def encloses(self, prism: VisibilityPrism) -> bool:
        a, b, c, d = prism.bounds
        return self.min_x <= a and self.min_y <= b and c <= self.max_x and d <= self.max_y

    def to_payload(self) -> BattlefieldVisibilityBoundsPayload:
        return {
            "min_x": str(self.min_x),
            "min_y": str(self.min_y),
            "max_x": str(self.max_x),
            "max_y": str(self.max_y),
        }

    @classmethod
    def from_payload(
        cls, payload: BattlefieldVisibilityBoundsPayload
    ) -> BattlefieldVisibilityBounds:
        if type(cast(object, payload)) is not dict or set(payload) != set(
            BattlefieldVisibilityBoundsPayload.__required_keys__
        ):
            raise GeometryError("Visibility battlefield bounds payload fields are invalid.")
        parsed: list[Fraction] = []
        for value in (payload["min_x"], payload["min_y"], payload["max_x"], payload["max_y"]):
            if type(value) is not str:
                raise GeometryError(
                    "Visibility battlefield bounds require canonical rational strings."
                )
            try:
                number = Fraction(value)
            except (ValueError, ZeroDivisionError) as exc:
                raise GeometryError("Invalid visibility battlefield bound.") from exc
            if str(number) != value:
                raise GeometryError(
                    "Visibility battlefield bounds require canonical rational strings."
                )
            parsed.append(number)
        return cls(*parsed)


@lru_cache(maxsize=4096)
def physical_model_visibility_prisms(model: Model) -> tuple[VisibilityPrism, ...]:
    return tuple(model_visibility_prism(part) for part in physical_prisms(model))


def _reduce(prisms: tuple[VisibilityPrism, ...]) -> tuple[VisibilityPrism, ...]:
    unique = tuple(dict.fromkeys(prisms))

    def contained(inner: VisibilityPrism, outer: VisibilityPrism) -> bool:
        if inner.lower < outer.lower or inner.upper > outer.upper:
            return False
        if inner.footprint == outer.footprint:
            return True
        # Affine box vertices enclose the entire ellipse/rectangle. A convex
        # outer domain containing every vertex contains that whole component.
        return all(
            outer.contains_point((x, y, z))
            for x, y in ModelDomain.from_prism(inner).vertices()
            for z in (inner.lower, inner.upper)
        )

    return tuple(
        p
        for i, p in enumerate(unique)
        if not any(
            i != j and contained(p, q) and (j < i or not contained(q, p))
            for j, q in enumerate(unique)
        )
    )


def _fingerprint(
    observers: tuple[VisibilityPrism, ...],
    targets: tuple[VisibilityPrism, ...],
    any_blockers: tuple[VisibilityPrism, ...],
    full_blockers: tuple[VisibilityPrism, ...],
    bounds: BattlefieldVisibilityBounds | None,
) -> str:
    # Include unreduced physical inputs with the same canonical rational shape
    # encoding used by the scalar authority. No Python object representations.
    payload = [
        VISIBILITY_ALGORITHM_ID,
        "physical-union",
        [prism_fingerprint_payload(p) for p in observers],
        [prism_fingerprint_payload(p) for p in targets],
        [prism_fingerprint_payload(p) for p in any_blockers],
        [prism_fingerprint_payload(p) for p in full_blockers],
        None if bounds is None else bounds.to_payload(),
    ]
    return hashlib.sha256(
        json.dumps(payload, separators=(",", ":"), sort_keys=True).encode()
    ).hexdigest()


def _enclosure(
    prism: VisibilityPrism, bounds: BattlefieldVisibilityBounds | None
) -> VisibilityPrism | None:
    a, b, c, d = prism.bounds
    if bounds is not None:
        a, b, c, d = (
            max(a, bounds.min_x),
            max(b, bounds.min_y),
            min(c, bounds.max_x),
            min(d, bounds.max_y),
        )
    if a > c or b > d:
        return None
    if a == c or b == d:
        # A closed line/point intersection is legal. Retain the original prism
        # as a conservative enclosure; exact origin membership still clips it.
        return prism
    return VisibilityPrism(((a, b), (c, b), (c, d), (a, d)), prism.lower, prism.upper, (a, b, c, d))


def _candidate_points(prism: VisibilityPrism) -> tuple[RationalPoint3, ...]:
    domain = ModelDomain.from_prism(prism)
    return tuple(
        (x, y, z)
        for x, y in (*domain.vertices(), domain.center)
        for z in (domain.lower, (domain.lower + domain.upper) / 2, domain.upper)
        if prism.contains_point((x, y, z))
    )


def _supplemental_ray(
    origins: tuple[VisibilityPrism, ...],
    destinations: tuple[VisibilityPrism, ...],
    blockers: tuple[VisibilityPrism, ...],
    bounds: BattlefieldVisibilityBounds | None,
) -> tuple[tuple[RationalPoint3, RationalPoint3] | None, int]:
    checked = 0
    for origin in origins:
        for first in _candidate_points(origin):
            if bounds is not None and not bounds.contains(first):
                continue
            for target in destinations:
                for last in _candidate_points(target):
                    checked += 1
                    if all(not blocker.intersects_corridor(first, last) for blocker in blockers):
                        return (first, last), checked
    return None, checked


@lru_cache(maxsize=4096)
def resolve_physical_visibility(
    observers: tuple[VisibilityPrism, ...],
    targets: tuple[VisibilityPrism, ...],
    any_blockers: tuple[VisibilityPrism, ...],
    full_blockers: tuple[VisibilityPrism, ...],
    bounds: BattlefieldVisibilityBounds | None,
) -> ContinuousVisibilityEvidence:
    return resolve_physical_visibility_uncached(
        observers, targets, any_blockers, full_blockers, bounds
    )


def resolve_physical_visibility_uncached(
    observers: tuple[VisibilityPrism, ...],
    targets: tuple[VisibilityPrism, ...],
    any_blockers: tuple[VisibilityPrism, ...],
    full_blockers: tuple[VisibilityPrism, ...],
    bounds: BattlefieldVisibilityBounds | None,
) -> ContinuousVisibilityEvidence:
    if not observers or not targets:
        raise GeometryError("Physical visibility requires nonempty observer and target unions.")
    fingerprint = _fingerprint(observers, targets, any_blockers, full_blockers, bounds)
    origins, destinations = _reduce(observers), _reduce(targets)
    if len(origins) == len(destinations) == 1 and (bounds is None or bounds.encloses(origins[0])):
        return replace(
            resolve_visibility_pair_uncached(
                origins[0], destinations[0], any_blockers, full_blockers
            ),
            input_fingerprint=fingerprint,
        )
    boxes = tuple(p for o in origins if (p := _enclosure(o, bounds)) is not None)
    if not boxes or all(
        all_corridors_blocked_by_plane(o, t, any_blockers)
        or all_corridors_blocked_by_circle(o, t, any_blockers)
        or all_corridors_blocked_by_endpoint_containment(o, t, any_blockers)
        for o in boxes
        for t in destinations
    ):
        return ContinuousVisibilityEvidence(
            fingerprint, False, False, "blocked_cross_section", "not_visible"
        )
    checked = 0
    ray: tuple[RationalPoint3, RationalPoint3] | None = None
    for o in origins:
        for t in destinations:
            for first, last in positive_ray_candidates(
                ModelDomain.from_prism(o), ModelDomain.from_prism(t), any_blockers
            ):
                checked += 1
                if (
                    o.contains_point(first)
                    and t.contains_point(last)
                    and (bounds is None or bounds.contains(first))
                    and all(not b.intersects_corridor(first, last) for b in any_blockers)
                ):
                    ray = (first, last)
                    break
            if ray is not None:
                break
        if ray is not None:
            break
    # Rectangle corners include exact clipped point domains that the scalar
    # ray search need not enumerate. These remain positive proofs only.
    if ray is None:
        ray, supplemental_checked = _supplemental_ray(origins, destinations, any_blockers, bounds)
        checked += supplemental_checked
    origin_domains, target_domains = (
        tuple(map(ModelDomain.from_prism, origins)),
        tuple(map(ModelDomain.from_prism, destinations)),
    )
    clipped = None if bounds is None else bounds.values
    visible = ray is not None or decide_physical_any(
        origin_domains, target_domains, any_blockers, clipped
    )
    proof = "clear_corridor" if ray is not None else "real_algebraic_exists"
    if not visible:
        return ContinuousVisibilityEvidence(
            fingerprint, False, False, proof, "not_visible", checked
        )
    full = decide_physical_full(origin_domains, target_domains, full_blockers, clipped)
    return ContinuousVisibilityEvidence(
        fingerprint, True, full, proof, "real_algebraic_target_parts", checked, ray
    )


@lru_cache(maxsize=4096)
def physical_source_group_obscures(
    observers: tuple[VisibilityPrism, ...],
    targets: tuple[VisibilityPrism, ...],
    selected: tuple[VisibilityPrism, ...],
    remaining: tuple[VisibilityPrism, ...],
    bounds: BattlefieldVisibilityBounds | None,
) -> bool:
    if not selected:
        return False
    origins, destinations = _reduce(observers), _reduce(targets)
    if len(origins) == len(destinations) == 1 and (bounds is None or bounds.encloses(origins[0])):
        return source_group_obscures(origins[0], destinations[0], selected, remaining)
    alone = resolve_physical_visibility(observers, targets, selected, selected, bounds)
    if not alone.model_fully_visible:
        return True
    if not remaining:
        return False
    combined = (*selected, *remaining)
    if resolve_physical_visibility(
        observers, targets, combined, combined, bounds
    ).model_fully_visible:
        return False
    return decide_physical_counterfactual(
        tuple(map(ModelDomain.from_prism, origins)),
        tuple(map(ModelDomain.from_prism, destinations)),
        combined,
        remaining,
        None if bounds is None else bounds.values,
    )
