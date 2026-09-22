"""Analytic convex footprint predicates for exact set-up existence proofs.

All dimensions are rational. Free auxiliary variables are existential witnesses,
never sampled orientations or polygonal approximations of curved bases. A strict
separating support line proves clearance; containment uses every footprint point.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from fractions import Fraction
from typing import Literal

from warhammer40k_core.geometry.base import BaseShape, CircularBase, OvalBase, RectangularBase
from warhammer40k_core.geometry.pose import GeometryError, Pose
from warhammer40k_core.geometry.visibility_algebra import (
    Formula,
    RealTerm,
    both,
    either,
    implies,
    negate,
    quantified,
    term,
    variable,
)
from warhammer40k_core.geometry.visibility_shapes import rational_rotation

ZERO = term(0)


def rational(value: float) -> Fraction:
    return Fraction(str(value))


@dataclass(frozen=True, slots=True)
class Footprint:
    kind: Literal["circle", "ellipse", "rectangle"]
    x: RealTerm
    y: RealTerm
    a: Fraction
    b: Fraction
    c: RealTerm
    s: RealTerm
    determinant: Fraction = Fraction(1)

    @classmethod
    def moving(
        cls, base: BaseShape, x: RealTerm, y: RealTerm, c: RealTerm, s: RealTerm
    ) -> Footprint:
        if type(base) is CircularBase:
            return cls(
                "circle", x, y, rational(base.radius), rational(base.radius), term(1), term(0)
            )
        if isinstance(base, OvalBase | RectangularBase):
            return cls(
                "ellipse" if type(base) is OvalBase else "rectangle",
                x,
                y,
                rational(base.length) / 2,
                rational(base.width) / 2,
                c,
                s,
            )
        raise GeometryError("Placement requires an analytic circle, ellipse, or rectangle.")

    @classmethod
    def fixed(cls, base: BaseShape, pose: Pose) -> Footprint:
        c, s = rational_rotation(pose.facing.degrees)
        result = cls.moving(
            base, term(rational(pose.position.x)), term(rational(pose.position.y)), term(c), term(s)
        )
        return cls(
            result.kind,
            result.x,
            result.y,
            result.a,
            result.b,
            result.c,
            result.s,
            Fraction(1) if result.kind == "circle" else c * c + s * s,
        )

    def local(self, x: RealTerm, y: RealTerm) -> tuple[RealTerm, RealTerm]:
        dx, dy = x - self.x, y - self.y
        return (
            (self.c * dx + self.s * dy) * (1 / self.determinant),
            (self.c * dy - self.s * dx) * (1 / self.determinant),
        )

    def world(self, u: RealTerm, v: RealTerm) -> tuple[RealTerm, RealTerm]:
        return (self.x + self.c * u - self.s * v, self.y + self.s * u + self.c * v)

    def member(self, x: RealTerm, y: RealTerm) -> Formula:
        u, v = self.local(x, y)
        if self.kind == "rectangle":
            return both(u.ge(-self.a), u.le(self.a), v.ge(-self.b), v.le(self.b))
        return ((u * self.b) ** 2 + (v * self.a) ** 2).le((self.a * self.b) ** 2)

    def vertices(self) -> tuple[tuple[RealTerm, RealTerm], ...]:
        return tuple(
            self.world(term(i * self.a), term(j * self.b))
            for i, j in ((-1, -1), (1, -1), (1, 1), (-1, 1))
        )

    def support_at_most(self, nx: RealTerm, ny: RealTerm, bound: RealTerm) -> Formula:
        """Centered support <= bound, without introducing a square root."""
        a = (self.c * nx + self.s * ny) * self.a
        b = (self.c * ny - self.s * nx) * self.b
        if self.kind == "rectangle":
            return both(*((a * i + b * j).le(bound) for i in (-1, 1) for j in (-1, 1)))
        return both(bound.ge(0), (a * a + b * b).le(bound * bound))


@dataclass
class PlacementPredicates:
    names: list[str] = field(default_factory=list[str])
    prefix: str = "p"

    def scalar(self) -> RealTerm:
        name = f"{self.prefix}{len(self.names)}"
        self.names.append(name)
        return variable(name)

    def point_near(self, x: RealTerm, y: RealTerm, shape: Footprint, distance: RealTerm) -> Formula:
        if shape.kind == "circle":
            return both(
                distance.ge(0),
                ((x - shape.x) ** 2 + (y - shape.y) ** 2).le((distance + shape.a) ** 2),
            )
        if shape.kind == "rectangle":
            u, v = shape.local(x, y)
            return self._point_near_rectangle(u, v, shape, distance)
        u, v = self.scalar(), self.scalar()
        px, py = shape.world(u, v)
        return both(
            distance.ge(0),
            ((u * shape.b) ** 2 + (v * shape.a) ** 2).le((shape.a * shape.b) ** 2),
            ((x - px) ** 2 + (y - py) ** 2).le(distance**2),
        )

    def _point_near_rectangle(
        self, u: RealTerm, v: RealTerm, shape: Footprint, distance: RealTerm
    ) -> Formula:
        # Exact rectangle interior, side strips and four corner disks. No buffer mesh.
        a, b, norm = shape.a, shape.b, shape.determinant
        return both(
            distance.ge(0),
            either(
                both(u.ge(-a), u.le(a), v.ge(-b), v.le(b)),
                *(
                    both(u.ge(-a), u.le(a), ((v - j * b) ** 2 * norm).le(distance**2))
                    for j in (-1, 1)
                ),
                *(
                    both(v.ge(-b), v.le(b), ((u - i * a) ** 2 * norm).le(distance**2))
                    for i in (-1, 1)
                ),
                *(
                    (((u - i * a) ** 2 + (v - j * b) ** 2) * norm).le(distance**2)
                    for i in (-1, 1)
                    for j in (-1, 1)
                ),
            ),
        )

    def near(self, first: Footprint, second: Footprint, distance: RealTerm) -> Formula:
        if first.kind == "circle":
            return both(
                distance.ge(0), self.point_near(first.x, first.y, second, distance + first.a)
            )
        if second.kind == "circle":
            return self.near(second, first, distance)
        if first.kind == second.kind == "rectangle":
            return both(
                distance.ge(0),
                either(
                    negate(self._rectangle_separated(first, second)),
                    *(self.point_near(x, y, second, distance) for x, y in first.vertices()),
                    *(self.point_near(x, y, first, distance) for x, y in second.vertices()),
                ),
            )
        u, v, q, r = (self.scalar() for _ in range(4))
        x1, y1 = first.world(u, v)
        x2, y2 = second.world(q, r)
        return both(
            distance.ge(0),
            first.member(x1, y1),
            second.member(x2, y2),
            ((x1 - x2) ** 2 + (y1 - y2) ** 2).le(distance**2),
        )

    def clear(self, first: Footprint, second: Footprint, distance: RealTerm = ZERO) -> Formula:
        if first.kind == second.kind == "circle" or {first.kind, second.kind} == {
            "circle",
            "rectangle",
        }:
            # These near predicates contain no existential witnesses.
            return negate(self.near(first, second, distance))
        if first.kind == second.kind == "rectangle" and distance.constant == 0:
            return self._rectangle_separated(first, second)
        nx, ny, a, b = (self.scalar() for _ in range(4))
        return both(
            (nx * nx + ny * ny).eq(1),
            first.support_at_most(nx, ny, a),
            second.support_at_most(nx, ny, b),
            ((second.x - first.x) * nx + (second.y - first.y) * ny).gt(a + b + distance),
        )

    @staticmethod
    def _rectangle_separated(first: Footprint, second: Footprint) -> Formula:
        return either(
            *(
                both(
                    *(
                        ((qx - px) * nx + (qy - py) * ny).gt(0)
                        for px, py in first.vertices()
                        for qx, qy in second.vertices()
                    )
                )
                for shape in (first, second)
                for nx, ny in (
                    (shape.c, shape.s),
                    (-shape.c, -shape.s),
                    (-shape.s, shape.c),
                    (shape.s, -shape.c),
                )
            )
        )

    def inside_rectangle(self, first: Footprint, second: Footprint) -> Formula:
        if second.kind != "rectangle":
            raise GeometryError("Footprint containment requires a rectangle.")
        dx, dy = first.x - second.x, first.y - second.y
        return both(
            *(
                first.support_at_most(nx, ny, term(limit) - dx * nx - dy * ny)
                for nx, ny, limit in (
                    (second.c, second.s, second.a * second.determinant),
                    (-second.c, -second.s, second.a * second.determinant),
                    (-second.s, second.c, second.b * second.determinant),
                    (second.s, -second.c, second.b * second.determinant),
                )
            )
        )

    def contained(self, first: Footprint, second: Footprint, distance: RealTerm) -> Formula:
        if distance.constant == 0 and second.kind == "rectangle":
            return self.inside_rectangle(first, second)
        if first.kind == "circle":
            # Erosion of a convex body's d-offset by a radius-r disk is the
            # (d-r)-offset when d>=r. Smaller offsets use the complete predicate.
            if distance.constant is not None and distance.constant >= first.a:
                return self.point_near(first.x, first.y, second, distance - first.a)
            if second.kind == "circle":
                limit = distance + second.a - first.a
                return both(
                    limit.ge(0),
                    ((first.x - second.x) ** 2 + (first.y - second.y) ** 2).le(limit**2),
                )
        if first.kind == "rectangle":
            return both(*(self.point_near(x, y, second, distance) for x, y in first.vertices()))
        if second.kind == "circle":
            return self._ellipse_in_disk(first, second, distance + second.a)
        # Quantifiers are necessary for an analytic ellipse in a rounded hull.
        # Bound witness names locally so a single point cannot stand in for all
        # points of the passenger. The caller still decides the complete formula.
        u, v = variable("cu"), variable("cv")
        x, y = first.world(u, v)
        point_context = PlacementPredicates(prefix="inner")
        near = point_context.point_near(x, y, second, distance)
        near = quantified("exists", tuple(point_context.names), near)
        member = ((u * first.b) ** 2 + (v * first.a) ** 2).le((first.a * first.b) ** 2)
        return quantified("forall", ("cu", "cv"), implies(member, near))

    def _ellipse_in_disk(self, first: Footprint, second: Footprint, radius: RealTerm) -> Formula:
        """Exact trust-region certificate for every point of an ellipse.

        The S-lemma makes disk containment equivalent to a positive-semidefinite
        3x3 matrix for some nonnegative multiplier. Its principal minors avoid
        universal quantifier elimination, including tangency and degenerate
        (zero minor) certificates. No polygonal enclosure is substituted.
        See Boyd/Vandenberghe, Convex Optimization, appendix B.2:
        https://stanford.edu/~boyd/cvxbook/bv_cvxbook.pdf
        """
        multiplier = self.scalar()
        dx, dy = first.x - second.x, first.y - second.y
        u = (dx * first.c + dy * first.s) * first.a
        v = (dy * first.c - dx * first.s) * first.b
        a = multiplier - first.a**2 * first.determinant
        b = multiplier - first.b**2 * first.determinant
        c = radius**2 - dx**2 - dy**2 - multiplier
        return both(
            radius.ge(0),
            multiplier.ge(0),
            a.ge(0),
            b.ge(0),
            c.ge(0),
            (a * c).ge(u**2),
            (b * c).ge(v**2),
            (a * b * c - b * u**2 - a * v**2).ge(0),
        )
