"""Isolated exact-algebraic feasibility experiment, NOT runtime implementation.

Optional dependency: z3-solver==4.15.4.0, installed outside the project. This
experiment only covers separated axis-aligned unit-box model prisms and box
occluders. Full visibility checks the target's strictly observer-facing X face.
It does not certify all supported engine geometry, terrain policy or witnesses.
Unknown/timeouts are retained as failures, never converted to visibility answers.
"""

from __future__ import annotations

import argparse
import hashlib
import itertools
import json
import resource
import sys
from pathlib import Path
from time import perf_counter_ns

import z3


def real(value: str) -> z3.RatNumRef:
    return z3.RealVal(value)


def membership(point: list[z3.ArithRef], bounds: tuple[str, ...]) -> z3.BoolRef:
    return z3.And(
        *(
            constraint
            for value, lower, upper in zip(point, bounds[::2], bounds[1::2], strict=True)
            for constraint in (value >= real(lower), value <= real(upper))
        )
    )


def formula(case: str, predicate: str) -> z3.BoolRef:
    observer = z3.Reals("ox oy oz")
    target = z3.Reals("tx ty tz")
    sx, sy = z3.Reals("sx sy")
    dx, dy = target[0] - observer[0], target[1] - observer[1]
    radius = real("5/254")
    constraints = [
        membership(observer, ("-3.5", "-2.5", "-.5", ".5", "0", "2")),
        sx * sx + sy * sy == radius * radius,
        sx * dx + sy * dy == 0,
    ]
    existential = [*observer, sx, sy]
    corners = [
        (p[0] + sign * sx, p[1] + sign * sy, p[2]) for p in (observer, target) for sign in (-1, 1)
    ]
    boxes = {
        "clear": (),
        "blocked": (("-.05", ".05", "-4", "4", "0", "3"),),
        "narrow-opening": (
            ("-.05", ".05", "-4", ".1", "0", "3"),
            ("-.05", ".05", ".2", "4", "0", "3"),
        ),
        "partial-occlusion": (("2.35", "2.45", ".1", ".2", "0", "3"),),
    }[case]
    for index, bounds in enumerate(boxes):
        nx, ny, nz, d = z3.Reals(f"nx{index} ny{index} nz{index} d{index}")
        existential.extend((nx, ny, nz, d))
        # Disjoint compact convex sets admit strict separating planes. Scaling
        # the plane gives a unit gap without restricting the geometric distance.
        for x, y, zz in itertools.product(
            (real(bounds[0]), real(bounds[1])),
            (real(bounds[2]), real(bounds[3])),
            (real(bounds[4]), real(bounds[5])),
        ):
            constraints.append(nx * x + ny * y + nz * zz <= d)
        for x, y, zz in corners:
            constraints.append(nx * x + ny * y + nz * zz >= d + 1)
    clear = z3.And(*constraints)
    target_bounds = membership(target, ("2.5", "3.5", "-.5", ".5", "0", "2"))
    if predicate == "any":
        return z3.Exists([*target, *existential], z3.And(target_bounds, clear))
    facing = z3.And(target_bounds, target[0] == real("2.5"))
    return z3.ForAll(target, z3.Implies(facing, z3.Exists(existential, clear)))


def planar_formula(case: str, predicate: str) -> z3.BoolRef:
    """Exact SAT specialization for this prototype's full-height box blockers.

    All observer/target heights are in [0,2], and every blocker covers [0,3],
    so projection to XY is equivalent for this workload only. The separating
    axes are the box's X/Y axes and the strip's longitudinal/lateral axes.
    """
    ox, oy, tx, ty, length = z3.Reals("ox oy tx ty length")
    dx, dy = tx - ox, ty - oy
    radius = real("5/254")
    observer = z3.And(ox >= real("-3.5"), ox <= real("-2.5"), oy >= real("-.5"), oy <= real(".5"))
    target = z3.And(tx >= real("2.5"), tx <= real("3.5"), ty >= real("-.5"), ty <= real(".5"))
    constraints = [observer, length > 0, length * length == dx * dx + dy * dy]
    boxes = {
        "clear": (),
        "blocked": (("-.05", ".05", "-4", "4"),),
        "narrow-opening": (("-.05", ".05", "-4", ".1"), ("-.05", ".05", ".2", "4")),
        "partial-occlusion": (("2.35", "2.45", ".1", ".2"),),
    }[case]
    for bounds in boxes:
        min_x, max_x, min_y, max_y = map(real, bounds)
        vertices = tuple(itertools.product((min_x, max_x), (min_y, max_y)))
        # Multiplication by positive length avoids division. All four strip
        # corners must lie strictly on the same side for each box-axis test.
        scaled_corners = [
            (x * length + sign * radius * dy, y * length - sign * radius * dx)
            for x, y in ((ox, oy), (tx, ty))
            for sign in (-1, 1)
        ]
        separations = [
            z3.And(*(x < min_x * length for x, y in scaled_corners)),
            z3.And(*(x > max_x * length for x, y in scaled_corners)),
            z3.And(*(y < min_y * length for x, y in scaled_corners)),
            z3.And(*(y > max_y * length for x, y in scaled_corners)),
            z3.And(*(dx * (x - ox) + dy * (y - oy) < 0 for x, y in vertices)),
            z3.And(*(dx * (x - tx) + dy * (y - ty) > 0 for x, y in vertices)),
            z3.And(*(dy * (x - ox) - dx * (y - oy) < -radius * length for x, y in vertices)),
            z3.And(*(dy * (x - ox) - dx * (y - oy) > radius * length for x, y in vertices)),
        ]
        constraints.append(z3.Or(*separations))
    clear = z3.And(*constraints)
    if predicate == "any":
        return z3.Exists([ox, oy, tx, ty, length], z3.And(target, clear))
    return z3.ForAll(
        [tx, ty], z3.Implies(z3.And(target, tx == real("2.5")), z3.Exists([ox, oy, length], clear))
    )


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--case", choices=("clear", "blocked", "narrow-opening", "partial-occlusion"), required=True
    )
    parser.add_argument("--predicate", choices=("any", "full"), required=True)
    parser.add_argument("--tactic", choices=("nlqsat", "qsat", "smt"), default="nlqsat")
    parser.add_argument("--timeout-ms", type=int, default=10000)
    parser.add_argument("--planar", action="store_true")
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    started = perf_counter_ns()
    query = (planar_formula if args.planar else formula)(args.case, args.predicate)
    construction_ms = (perf_counter_ns() - started) / 1e6
    solver = z3.Tactic(args.tactic).solver()
    solver.set(timeout=args.timeout_ms)
    solver.add(query)
    started = perf_counter_ns()
    outcome = solver.check()
    elapsed_ms = (perf_counter_ns() - started) / 1e6
    expected = args.case != "blocked" if args.predicate == "any" else args.case == "clear"
    result = {
        "prototype": (
            "planar-sat-full-height-boxes-v1" if args.planar else "convex-separation-box-prisms-v1"
        ),
        "prototype_sha256": hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
        "z3_version": z3.get_version_string(),
        "case": args.case,
        "predicate": args.predicate,
        "tactic": args.tactic,
        "timeout_ms": args.timeout_ms,
        "expected_predicate": expected,
        "solver_result": str(outcome),
        "reason_unknown": solver.reason_unknown() if outcome == z3.unknown else None,
        "correct_complete_result": outcome == (z3.sat if expected else z3.unsat),
        "formula_construction_ms": construction_ms,
        "solve_ms": elapsed_ms,
        "peak_rss_bytes": resource.getrusage(resource.RUSAGE_SELF).ru_maxrss
        * (1 if sys.platform == "darwin" else 1024),
    }
    args.output.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n")
    print(json.dumps(result, sort_keys=True), flush=True)
    return 0 if result["correct_complete_result"] else 2


if __name__ == "__main__":
    raise SystemExit(main())
