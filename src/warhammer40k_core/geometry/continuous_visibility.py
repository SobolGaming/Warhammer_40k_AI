"""Shared continuous model predicates with exact, one-way proof accelerators.

The cache key is the complete immutable input geometry for BOTH predicates.
Proof search never substitutes a sampled or timed-out answer: unresolved queries
use the complete real-algebraic authority. Timing is not part of evidence/state.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from fractions import Fraction
from functools import lru_cache
from typing import TypedDict, cast

from warhammer40k_core.geometry.pose import GeometryError
from warhammer40k_core.geometry.visibility_certificates import (
    all_corridors_blocked_by_circle,
    all_corridors_blocked_by_endpoint_containment,
    all_corridors_blocked_by_plane,
    full_visibility_by_observer_caps,
    full_visibility_by_parallel_circle_corridors,
    full_visibility_by_rear_circle_separation,
)
from warhammer40k_core.geometry.visibility_exact import (
    CORRIDOR_RADIUS,
    RationalEllipse,
    RationalPoint3,
    VisibilityPrism,
)
from warhammer40k_core.geometry.visibility_formulas import ModelDomain, decide_any, decide_full
from warhammer40k_core.geometry.visibility_planar import (
    decide_planar_any,
    decide_planar_full,
    planar_line_reduction_applies,
)
from warhammer40k_core.geometry.visibility_witnesses import (
    point_has_self_visible_origin,
    positive_ray_candidates,
    self_visible_corridors_blocked,
    target_part_candidates,
)

VISIBILITY_ALGORITHM_ID = "continuous-analytic-prism-visibility:1"


class ContinuousVisibilityPayload(TypedDict):
    algorithm_id: str
    input_fingerprint: str
    model_visible: bool
    model_fully_visible: bool
    visibility_proof: str
    full_visibility_proof: str
    checked_witness_count: int
    clear_corridor: list[list[str]] | None
    hidden_target_part: list[str] | None


def _rational_text(value: Fraction) -> str:
    return f"{value.numerator}/{value.denominator}"


def _point_payload(point: RationalPoint3) -> list[str]:
    return [_rational_text(value) for value in point]


def _valid_evidence_payload_fields(payload: object) -> bool:
    return type(payload) is dict and set(cast(dict[object, object], payload)) == set(
        ContinuousVisibilityPayload.__required_keys__
    )


def _validate_evidence_point(value: object) -> None:
    if type(value) is not tuple:
        raise GeometryError("Visibility evidence points must be immutable exact rational triples.")
    values = cast(tuple[object, ...], value)
    if len(values) != 3 or any(type(v) is not Fraction for v in values):
        raise GeometryError("Visibility evidence points must be immutable exact rational triples.")


def _point_from_payload(values: list[str]) -> RationalPoint3:
    if (
        type(values) is not list
        or len(values) != 3
        or any(type(value) is not str for value in values)
    ):
        raise GeometryError("Visibility evidence requires three canonical rational coordinates.")
    parsed: list[Fraction] = []
    for value in values:
        try:
            number = Fraction(value)
        except (ValueError, ZeroDivisionError) as exc:
            raise GeometryError(
                "Visibility evidence contains an invalid rational coordinate."
            ) from exc
        if _rational_text(number) != value:
            raise GeometryError("Visibility evidence coordinates must be canonical rationals.")
        parsed.append(number)
    return (parsed[0], parsed[1], parsed[2])


@dataclass(frozen=True, slots=True)
class ContinuousVisibilityEvidence:
    input_fingerprint: str
    model_visible: bool
    model_fully_visible: bool
    visibility_proof: str
    full_visibility_proof: str
    checked_witness_count: int = 0
    clear_corridor: tuple[RationalPoint3, RationalPoint3] | None = None
    hidden_target_part: RationalPoint3 | None = None

    def __post_init__(self) -> None:
        if (
            type(self.input_fingerprint) is not str
            or len(self.input_fingerprint) != 64
            or any(c not in "0123456789abcdef" for c in self.input_fingerprint)
        ):
            raise GeometryError("Visibility evidence requires its complete input fingerprint.")
        if type(self.model_visible) is not bool or type(self.model_fully_visible) is not bool:
            raise GeometryError("Visibility evidence predicates must be bools.")
        if self.model_fully_visible and not self.model_visible:
            raise GeometryError("Full visibility requires any-part visibility.")
        if type(self.checked_witness_count) is not int or self.checked_witness_count < 0:
            raise GeometryError("Visibility witness count must be a non-negative integer.")
        if type(self.visibility_proof) is not str or self.visibility_proof not in {
            "clear_enclosure",
            "blocked_cross_section",
            "blocked_circular_enclosure",
            "blocked_endpoint_containment",
            "clear_corridor",
            "real_algebraic_exists",
            "real_algebraic_planar_lines",
        }:
            raise GeometryError("Unsupported any-part visibility proof.")
        if type(self.full_visibility_proof) is not str or self.full_visibility_proof not in {
            "clear_enclosure",
            "not_visible",
            "hidden_target_part",
            "real_algebraic_target_parts",
        }:
            raise GeometryError("Unsupported full-visibility proof.")
        if (self.visibility_proof == "clear_corridor") != (self.clear_corridor is not None):
            raise GeometryError("A corridor proof requires its exact endpoints.")
        if self.clear_corridor is not None and not self.model_visible:
            raise GeometryError("A clear-corridor proof requires visible geometry.")
        if self.clear_corridor is not None:
            if type(self.clear_corridor) is not tuple or len(self.clear_corridor) != 2:
                raise GeometryError("A corridor proof requires two immutable endpoints.")
            for point in self.clear_corridor:
                _validate_evidence_point(point)
        if (self.full_visibility_proof == "hidden_target_part") != (
            self.hidden_target_part is not None
        ):
            raise GeometryError("A hidden-part proof requires its exact target point.")
        if self.hidden_target_part is not None and self.model_fully_visible:
            raise GeometryError("A hidden-part proof cannot report full visibility.")
        if self.hidden_target_part is not None:
            _validate_evidence_point(self.hidden_target_part)
        if self.visibility_proof == "clear_enclosure" and not self.model_visible:
            raise GeometryError("A clear enclosure proves visibility.")
        if (
            self.visibility_proof
            in {
                "blocked_cross_section",
                "blocked_circular_enclosure",
                "blocked_endpoint_containment",
            }
            and self.model_visible
        ):
            raise GeometryError("A complete blocking enclosure prevents visibility.")
        if self.full_visibility_proof == "clear_enclosure" and not self.model_fully_visible:
            raise GeometryError("A full clear enclosure proves full visibility.")
        if self.full_visibility_proof == "not_visible" and self.model_visible:
            raise GeometryError("A not-visible proof must match the model predicate.")

    def to_payload(self) -> ContinuousVisibilityPayload:
        return {
            "algorithm_id": VISIBILITY_ALGORITHM_ID,
            "input_fingerprint": self.input_fingerprint,
            "model_visible": self.model_visible,
            "model_fully_visible": self.model_fully_visible,
            "visibility_proof": self.visibility_proof,
            "full_visibility_proof": self.full_visibility_proof,
            "checked_witness_count": self.checked_witness_count,
            "clear_corridor": None
            if self.clear_corridor is None
            else [_point_payload(p) for p in self.clear_corridor],
            "hidden_target_part": None
            if self.hidden_target_part is None
            else _point_payload(self.hidden_target_part),
        }

    @classmethod
    def from_payload(cls, payload: ContinuousVisibilityPayload) -> ContinuousVisibilityEvidence:
        if not _valid_evidence_payload_fields(payload):
            raise GeometryError("Continuous visibility evidence payload fields are invalid.")
        if payload["algorithm_id"] != VISIBILITY_ALGORITHM_ID:
            raise GeometryError("Unsupported continuous visibility algorithm identity.")
        corridor = payload["clear_corridor"]
        if corridor is not None and (type(corridor) is not list or len(corridor) != 2):
            raise GeometryError("Visibility corridor evidence requires two endpoints.")
        hidden = payload["hidden_target_part"]
        return cls(
            input_fingerprint=payload["input_fingerprint"],
            model_visible=payload["model_visible"],
            model_fully_visible=payload["model_fully_visible"],
            visibility_proof=payload["visibility_proof"],
            full_visibility_proof=payload["full_visibility_proof"],
            checked_witness_count=payload["checked_witness_count"],
            clear_corridor=None
            if corridor is None
            else (_point_from_payload(corridor[0]), _point_from_payload(corridor[1])),
            hidden_target_part=None if hidden is None else _point_from_payload(hidden),
        )


def _prism_payload(prism: VisibilityPrism) -> list[object]:
    footprint = prism.footprint
    points = (
        (footprint.center, footprint.first_axis, footprint.second_axis)
        if isinstance(footprint, RationalEllipse)
        else footprint
    )
    return [
        "ellipse" if isinstance(footprint, RationalEllipse) else "polygon",
        [[_rational_text(x), _rational_text(y)] for x, y in points],
        _rational_text(prism.lower),
        _rational_text(prism.upper),
    ]


def input_fingerprint(
    observer: VisibilityPrism,
    target: VisibilityPrism,
    visibility_blockers: tuple[VisibilityPrism, ...],
    full_blockers: tuple[VisibilityPrism, ...],
) -> str:
    payload = [
        VISIBILITY_ALGORITHM_ID,
        _prism_payload(observer),
        _prism_payload(target),
        [_prism_payload(b) for b in visibility_blockers],
        [_prism_payload(b) for b in full_blockers],
    ]
    return hashlib.sha256(
        json.dumps(payload, separators=(",", ":"), ensure_ascii=True).encode("ascii")
    ).hexdigest()


def _relevant(
    observer: VisibilityPrism, target: VisibilityPrism, blockers: tuple[VisibilityPrism, ...]
) -> tuple[VisibilityPrism, ...]:
    x0, y0 = (
        min(observer.bounds[0], target.bounds[0]) - CORRIDOR_RADIUS,
        min(observer.bounds[1], target.bounds[1]) - CORRIDOR_RADIUS,
    )
    x1, y1 = (
        max(observer.bounds[2], target.bounds[2]) + CORRIDOR_RADIUS,
        max(observer.bounds[3], target.bounds[3]) + CORRIDOR_RADIUS,
    )
    z0, z1 = min(observer.lower, target.lower), max(observer.upper, target.upper)
    return tuple(
        b
        for b in blockers
        if b.bounds[0] <= x1
        and b.bounds[2] >= x0
        and b.bounds[1] <= y1
        and b.bounds[3] >= y0
        and b.lower <= z1
        and b.upper >= z0
    )


@lru_cache(maxsize=4096)
def resolve_visibility_pair(
    observer: VisibilityPrism,
    target: VisibilityPrism,
    visibility_blockers: tuple[VisibilityPrism, ...],
    full_blockers: tuple[VisibilityPrism, ...],
) -> ContinuousVisibilityEvidence:
    return resolve_visibility_pair_uncached(observer, target, visibility_blockers, full_blockers)


def resolve_visibility_pair_uncached(
    observer: VisibilityPrism,
    target: VisibilityPrism,
    visibility_blockers: tuple[VisibilityPrism, ...],
    full_blockers: tuple[VisibilityPrism, ...],
) -> ContinuousVisibilityEvidence:
    fingerprint = input_fingerprint(observer, target, visibility_blockers, full_blockers)
    any_blockers = _relevant(observer, target, visibility_blockers)
    every_blockers = _relevant(observer, target, full_blockers)
    origin, destination = ModelDomain.from_prism(observer), ModelDomain.from_prism(target)
    full_proved = (
        full_visibility_by_observer_caps(observer, target, every_blockers)
        or full_visibility_by_parallel_circle_corridors(observer, target, every_blockers)
        or full_visibility_by_rear_circle_separation(observer, target, every_blockers)
    )
    if full_proved and set(any_blockers).issubset(every_blockers):
        return ContinuousVisibilityEvidence(
            fingerprint, True, True, "clear_enclosure", "clear_enclosure"
        )
    circular_blocked = all_corridors_blocked_by_circle(observer, target, any_blockers)
    if circular_blocked or all_corridors_blocked_by_plane(observer, target, any_blockers):
        return ContinuousVisibilityEvidence(
            fingerprint,
            False,
            False,
            "blocked_circular_enclosure" if circular_blocked else "blocked_cross_section",
            "not_visible",
        )
    if all_corridors_blocked_by_endpoint_containment(observer, target, any_blockers):
        return ContinuousVisibilityEvidence(
            fingerprint, False, False, "blocked_endpoint_containment", "not_visible"
        )
    checked = 0
    clear_ray: tuple[RationalPoint3, RationalPoint3] | None = None
    for first, last in positive_ray_candidates(origin, destination, any_blockers):
        checked += 1
        if all(not blocker.intersects_corridor(first, last) for blocker in any_blockers):
            clear_ray = (first, last)
            break
    any_proof = "clear_corridor" if clear_ray is not None else "real_algebraic_exists"
    if clear_ray is not None:
        visible = True
    elif planar_line_reduction_applies(observer, target, any_blockers):
        any_proof = "real_algebraic_planar_lines"
        visible = decide_planar_any(observer, target, any_blockers)
    else:
        visible = decide_any(origin, destination, any_blockers)
    if not visible:
        return ContinuousVisibilityEvidence(
            fingerprint, False, False, any_proof, "not_visible", checked
        )
    if full_proved:
        return ContinuousVisibilityEvidence(
            fingerprint, True, True, any_proof, "clear_enclosure", checked, clear_ray
        )
    for point in target_part_candidates(origin, destination, every_blockers):
        if point_has_self_visible_origin(
            origin, destination, point
        ) and self_visible_corridors_blocked(observer, destination, point, every_blockers):
            return ContinuousVisibilityEvidence(
                fingerprint, True, False, any_proof, "hidden_target_part", checked, clear_ray, point
            )
    fully_visible = (
        decide_planar_full(observer, target, every_blockers)
        if planar_line_reduction_applies(observer, target, every_blockers)
        else decide_full(origin, destination, every_blockers)
    )
    return ContinuousVisibilityEvidence(
        fingerprint,
        True,
        fully_visible,
        any_proof,
        "real_algebraic_target_parts",
        checked,
        clear_ray,
    )
