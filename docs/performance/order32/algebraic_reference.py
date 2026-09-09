"""Order 32 isolated real-algebraic reference experiment; no runtime connection.

Endpoints use real domain objects, with float inputs embedded as exact binary
rationals. Curved bases retain analytic ellipses. A shared rational pose matrix
and its actual inverse define the transformed ellipse (not an assumed transpose).
Strict external separation means closed obstacle contact blocks the flat 1mm
corridor. Facing means a strictly outward direction on at least one active face.
This experiment still needs runtime contracts, acceleration and delivery gates.
"""

from __future__ import annotations

import argparse
import hashlib
import itertools
import json
import math
from dataclasses import dataclass
from fractions import Fraction
from pathlib import Path
from time import perf_counter_ns

import z3

from warhammer40k_core.geometry.base import CircularBase, OvalBase, RectangularBase
from warhammer40k_core.geometry.terrain import TerrainVolume
from warhammer40k_core.geometry.volume import Model

RADIUS = Fraction(5, 254)


def q(value):
    fraction = Fraction(value)
    return z3.RealVal(f"{fraction.numerator}/{fraction.denominator}")


def dot(a, b):
    return sum(x * y for x, y in zip(a, b, strict=True))


def sub(a, b):
    return tuple(x - y for x, y in zip(a, b, strict=True))


def cross(a, b):
    return (a[1] * b[2] - a[2] * b[1], a[2] * b[0] - a[0] * b[2], a[0] * b[1] - a[1] * b[0])


def rotation(degrees):
    # Cardinal directions are represented exactly; non-cardinal directions use
    # the same matrix for membership, support, normal and witness operations.
    cardinals = {0: (1, 0), 90: (0, 1), 180: (-1, 0), 270: (0, -1)}
    if degrees % 360 in cardinals:
        return tuple(map(Fraction, cardinals[degrees % 360]))
    return Fraction(math.cos(math.radians(degrees))), Fraction(math.sin(math.radians(degrees)))


@dataclass(frozen=True)
class Prism:
    center: tuple[Fraction, Fraction]
    lower: Fraction
    upper: Fraction
    axes: tuple[tuple[Fraction, Fraction], tuple[Fraction, Fraction]]
    curved: bool

    @classmethod
    def model(cls, model: Model):
        shape = model.base
        if isinstance(shape, CircularBase):
            a = b = Fraction(shape.radius)
        elif isinstance(shape, OvalBase | RectangularBase):
            a, b = Fraction(shape.length) / 2, Fraction(shape.width) / 2
        else:
            raise TypeError("Unsupported reference shape")
        c, s = rotation(model.pose.facing.degrees)
        return cls(
            (Fraction(model.pose.position.x), Fraction(model.pose.position.y)),
            Fraction(model.pose.position.z),
            Fraction(model.pose.position.z + model.volume.height),
            ((a * c, a * s), (-b * s, b * c)),
            not isinstance(shape, RectangularBase),
        )

    @classmethod
    def terrain(cls, terrain: TerrainVolume):
        a, b = Fraction(terrain.width) / 2, Fraction(terrain.depth) / 2
        c, s = rotation(terrain.rotation_degrees)
        return cls(
            (Fraction(terrain.bottom_center.x), Fraction(terrain.bottom_center.y)),
            Fraction(terrain.bottom_center.z),
            Fraction(terrain.bottom_center.z + terrain.height),
            ((a * c, a * s), (-b * s, b * c)),
            False,
        )

    def local(self, point):
        x, y = point[0] - q(self.center[0]), point[1] - q(self.center[1])
        a, b = self.axes
        det = a[0] * b[1] - a[1] * b[0]
        return ((q(b[1]) * x - q(b[0]) * y) / q(det), (-q(a[1]) * x + q(a[0]) * y) / q(det))

    def member(self, point):
        u, v = self.local(point)
        footprint = u * u + v * v <= 1 if self.curved else z3.And(u >= -1, u <= 1, v >= -1, v <= 1)
        return z3.And(footprint, point[2] >= q(self.lower), point[2] <= q(self.upper))

    def vertices(self):
        a, b = self.axes
        return tuple(
            (self.center[0] + i * a[0] + j * b[0], self.center[1] + i * a[1] + j * b[1], z)
            for i, j, z in itertools.product((-1, 1), (-1, 1), (self.lower, self.upper))
        )

    def faces(self, point):
        u, v = self.local(point)
        a, b = self.axes
        det = a[0] * b[1] - a[1] * b[0]
        nu, nv = (q(b[1] / det), q(-b[0] / det), q(0)), (q(-a[1] / det), q(a[0] / det), q(0))
        sides = (
            [(u * u + v * v == 1, tuple(u * x + v * y for x, y in zip(nu, nv, strict=True)))]
            if self.curved
            else [
                (coordinate == sign, tuple(sign * n for n in normal))
                for coordinate, normal in ((u, nu), (v, nv))
                for sign in (-1, 1)
            ]
        )
        return [
            *sides,
            (point[2] == q(self.lower), (q(0), q(0), q(-1))),
            (point[2] == q(self.upper), (q(0), q(0), q(1))),
        ]

    def faces_origin(self, point, origin):
        return z3.Or(
            *(
                z3.And(active, dot(normal, sub(origin, point)) > 0)
                for active, normal in self.faces(point)
            )
        )

    def support_exceeds(self, normal, point):
        if not self.curved:
            return z3.Or(
                *(dot(normal, sub(tuple(map(q, vertex)), point)) > 0 for vertex in self.vertices())
            )
        squared_radius = sum(dot(normal[:2], tuple(map(q, axis))) ** 2 for axis in self.axes)
        return z3.Or(
            *(
                z3.Or(offset > 0, squared_radius > offset * offset)
                for z in (self.lower, self.upper)
                for offset in (dot(normal, sub(tuple(map(q, (*self.center, z))), point)),)
            )
        )

    def faces_observer(self, point, observer):
        return z3.And(
            self.member(point),
            z3.Or(
                *(
                    z3.And(active, observer.support_exceeds(normal, point))
                    for active, normal in self.faces(point)
                )
            ),
        )


def poly_clear(observer, target, prism, *, planar=False):
    """Exact SAT for a parallelogram and a nondegenerate rectangular prism.

    Axes are both shapes' face normals and cross products of edge directions.
    Algebraically squaring strictly positive distances eliminates the line-length
    radical without introducing a free length or separating-plane variable.
    """
    d = sub(target, observer)
    lateral = (-d[1], d[0], q(0))
    length2 = d[0] ** 2 + d[1] ** 2
    edges = [(*map(q, axis), q(0)) for axis in prism.axes] + [(q(0), q(0), q(1))]
    if planar:
        axes = [cross(edges[0], edges[2]), cross(edges[1], edges[2]), d, lateral]
    else:
        axes = [
            cross(edges[0], edges[1]),
            cross(edges[0], edges[2]),
            cross(edges[1], edges[2]),
            cross(d, lateral),
        ]
        axes.extend(cross(a, b) for a in (d, lateral) for b in edges)
    vertices = [tuple(map(q, vertex)) for vertex in prism.vertices()]
    alternatives = []
    for axis in axes:
        lateral2 = q(RADIUS * RADIUS) * dot(axis, lateral) ** 2
        for sign in (-1, 1):
            constraints = []
            for endpoint, vertex in itertools.product((observer, target), vertices):
                distance = sign * dot(axis, sub(vertex, endpoint))
                constraints.extend((distance > 0, distance * distance * length2 > lateral2))
            alternatives.append(z3.And(*constraints))
    return z3.Or(*alternatives)


def curve_clear(observer, target, prism, name):
    """Strict convex separation, using the analytic ellipse support function."""
    normal = z3.Reals(f"{name}_nx {name}_ny {name}_nz")
    d = sub(target, observer)
    lateral = (-d[1], d[0], q(0))
    length2 = d[0] ** 2 + d[1] ** 2
    support2 = sum(dot(normal[:2], tuple(map(q, axis))) ** 2 for axis in prism.axes)
    lateral2 = q(RADIUS * RADIUS) * dot(normal, lateral) ** 2
    constraints = []
    for endpoint, z in itertools.product((observer, target), (prism.lower, prism.upper)):
        distance = dot(normal, sub(endpoint, tuple(map(q, (*prism.center, z)))))
        difference = (distance * distance - support2) * length2 - lateral2
        constraints.extend(
            (
                distance > 0,
                difference > 0,
                difference * difference > 4 * support2 * lateral2 * length2,
            )
        )
    return z3.And(*constraints), normal


def formula(observer, target, blockers, predicate):
    planar = (
        observer.lower == target.lower
        and observer.upper == target.upper
        and all(b.lower <= observer.lower and b.upper >= observer.upper for b in blockers)
    )
    if planar:
        oz = q((observer.lower + observer.upper) / 2)
        o, t = (*z3.Reals("ox oy"), oz), (*z3.Reals("tx ty"), oz)
        observer_variables, target_variables = o[:2], t[:2]
    else:
        o, t = z3.Reals("ox oy oz"), z3.Reals("tx ty tz")
        observer_variables, target_variables = o, t
    constraints = [observer.member(o), (o[0] - t[0]) ** 2 + (o[1] - t[1]) ** 2 > 0]
    variables = list(observer_variables)
    for index, blocker in enumerate(blockers):
        if blocker.curved:
            clear, normals = curve_clear(o, t, blocker, f"blocker{index}")
            variables.extend(normals)
        else:
            clear = poly_clear(o, t, blocker, planar=planar)
        constraints.append(clear)
    if predicate == "any":
        return z3.And(target.member(t), *constraints)
    # Nonzero XY is w.l.o.g. here: a clear vertical disk permits small nonzero
    # XY perturbations within the positive-volume observer, preserving strict
    # separation and strict facing. The fixed-ray primitive still needs a disk.
    return z3.ForAll(
        target_variables,
        z3.Implies(
            target.faces_observer(t, observer),
            z3.Exists(variables, z3.And(target.faces_origin(t, o), *constraints)),
        ),
    )


def main():
    from scripts.probe_order32_visibility import contexts

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--case", required=True)
    parser.add_argument("--predicate", choices=("any", "full"), required=True)
    parser.add_argument("--timeout-ms", type=int, default=5000)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    context = contexts()[args.case]
    start = perf_counter_ns()
    query = formula(
        Prism.model(context.observer_model),
        Prism.model(context.target_models[0]),
        [
            Prism.terrain(terrain)
            for terrain in context.terrain_volumes
            if terrain.blocks_line_of_sight
        ]
        + [Prism.model(model) for model in context.dynamic_model_blockers],
        args.predicate,
    )
    query = z3.simplify(query)
    construction_ms = (perf_counter_ns() - start) / 1e6
    solver = z3.Tactic("qfnra-nlsat" if args.predicate == "any" else "nlqsat").solver()
    solver.set(timeout=args.timeout_ms)
    solver.add(query)
    start = perf_counter_ns()
    result = solver.check()
    output = {
        "case": args.case,
        "predicate": args.predicate,
        "prototype_sha256": hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
        "construction_ms": construction_ms,
        "solve_ms": (perf_counter_ns() - start) / 1e6,
        "result": str(result),
        "reason_unknown": solver.reason_unknown() if result == z3.unknown else None,
        "z3_version": z3.get_version_string(),
        "context": context.to_payload(),
    }
    args.output.write_text(json.dumps(output, indent=2, sort_keys=True) + "\n")
    print(json.dumps({key: value for key, value in output.items() if key != "context"}), flush=True)
    return 2 if result == z3.unknown else 0


if __name__ == "__main__":
    raise SystemExit(main())
