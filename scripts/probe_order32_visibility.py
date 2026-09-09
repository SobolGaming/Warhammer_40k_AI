"""Preimplementation Order 32 evidence; deliberately reports baseline defects.

Run as a module from the repository root. This is not a gameplay implementation
or a substitute for the final correctness/performance gates.
"""

from __future__ import annotations

import argparse
import cProfile
import hashlib
import json
import math
import platform
import resource
import statistics
import subprocess
import sys
from collections.abc import Callable
from dataclasses import replace
from pathlib import Path
from time import perf_counter_ns

import numpy
import shapely

from warhammer40k_core.core.ruleset_descriptor import RulesetDescriptor
from warhammer40k_core.core.visibility import TerrainVisibilityContext, VisibilityQuery
from warhammer40k_core.geometry.base import CircularBase, OvalBase, RectangularBase
from warhammer40k_core.geometry.pose import Point3, Pose
from warhammer40k_core.geometry.terrain import ObstacleVolume
from warhammer40k_core.geometry.visibility_corridor import (
    line_of_sight_corridor_intersects_terrain_volume,
)
from warhammer40k_core.geometry.volume import Model, ModelVolume

ROOT = Path(__file__).resolve().parents[1]
SPEC_ID = "order32-preimplementation-probe-v2"


def model(model_id: str, x: float, radius: float = 0.5) -> Model:
    return Model(model_id, Pose.at(x, 0), CircularBase(radius), ModelVolume(2))


def wall(name: str, lo: float, hi: float, *, x: float = 0.0) -> ObstacleVolume:
    return ObstacleVolume(name, Point3(x, (lo + hi) / 2, 0), 0.1, hi - lo, 3)


def contexts() -> dict[str, TerrainVisibilityContext]:
    base = TerrainVisibilityContext.from_ruleset_descriptor(
        ruleset_descriptor=RulesetDescriptor.warhammer_40000_eleventh(),
        los_cache_key="order32:probe:immutable",
        observer_model=model("observer", -3),
        target_models=(model("target", 3),),
        target_model_keywords=(("target", ()),),
    )
    aperture = replace(
        base,
        terrain_volumes=(wall("lower", -4, 0.1), wall("upper", 0.2, 4)),
    )
    partial = replace(
        base,
        observer_model=model("observer", -3, 0.001),
        terrain_volumes=(wall("near-target-occluder", 0.1, 0.2, x=2.4),),
    )
    phantom_aperture = (wall("lower", -4, 0.45), wall("upper", 0.55, 4))
    result = {
        "clear": base,
        "blocked": replace(base, terrain_volumes=(wall("solid", -4, 4),)),
        "narrow-opening": aperture,
        "partial-occlusion": partial,
        "alternative-observer-origin": replace(
            base,
            observer_model=replace(base.observer_model, volume=ModelVolume(4)),
            target_models=(replace(base.target_models[0], volume=ModelVolume(4)),),
            terrain_volumes=(ObstacleVolume("low-wall", Point3(0, 0, 0), 0.5, 4, 1),),
        ),
    }
    for shape_name, shape in (
        ("oval", OvalBase(1, 0.01)),
        ("rectangle", RectangularBase(1, 0.01)),
    ):
        result[f"outside-{shape_name}-samples"] = replace(
            base,
            observer_model=replace(base.observer_model, base=shape),
            target_models=(replace(base.target_models[0], base=shape),),
            terrain_volumes=phantom_aperture,
        )
    for count in (5, 100):
        targets = tuple(
            replace(model(f"target-{i:03d}", 3), pose=Pose.at(3 + i % 10, i // 10))
            for i in range(count)
        )
        for density, blockers in (
            ("sparse", ()),
            (
                "dense",
                tuple(
                    replace(model(f"blocker-{i:03d}", 0), pose=Pose.at(0, -2 + i * 0.6))
                    for i in range(30)
                ),
            ),
        ):
            result[f"{count}-targets-{density}"] = replace(
                base,
                target_models=targets,
                target_model_keywords=tuple((target.model_id, ()) for target in targets),
                dynamic_model_blockers=blockers,
            )
            legal_targets = tuple(
                replace(target, pose=Pose.at(3 + i % 10 * 1.25, i // 10 * 1.25))
                for i, target in enumerate(targets)
            )
            result[f"{count}-targets-{density}-nonoverlapping"] = replace(
                result[f"{count}-targets-{density}"],
                target_models=legal_targets,
                dynamic_model_blockers=tuple(
                    replace(blocker, pose=Pose.at(0, -2 + i * 1.25))
                    for i, blocker in enumerate(blockers)
                ),
            )
    return result


def counterexamples() -> dict[str, object]:
    cases = contexts()
    results: dict[str, object] = {}
    for name, visible, full in (
        ("narrow-opening", True, False),
        ("partial-occlusion", True, False),
        ("outside-oval-samples", False, False),
        ("outside-rectangle-samples", False, False),
        ("alternative-observer-origin", True, True),
    ):
        context = cases[name]
        witness = context.resolve_line_of_sight()
        results[name] = {
            "expected": {"visible": visible, "fully_visible": full},
            "observed": {
                "visible": witness.unit_visible,
                "fully_visible": witness.unit_fully_visible,
            },
            "context": context.to_payload(),
        }
    opening = cases["narrow-opening"]
    # Both endpoints belong to the actual circular model volumes. The 0.1in
    # opening leaves 0.05in clearance on each side, exceeding 0.5mm.
    opening_ray = (Point3(-3, 0.15, 1), Point3(3, 0.15, 1))
    opening_clear = (
        VisibilityQuery.from_segment(*opening_ray, static_terrain=opening.terrain_volumes)
        .resolve()
        .has_line_of_sight
    )
    assert opening_clear
    results["narrow-opening-independent-witness"] = [p.to_payload() for p in opening_ray]
    # This is on the circular target's near surface. At either side of the
    # occluder (x=2.35..2.45), every observer origin projects to y in (0.1,0.2)
    # and z in (0,3). The full origin bounding box is a conservative superset.
    target_x = 3 - math.sqrt(0.5**2 - 0.15**2)
    projected = []
    for x in (2.35, 2.45):
        for ox in (-3.001, -2.999):
            for oy in (-0.001, 0.001):
                for oz in (0, 2):
                    t = (x - ox) / (target_x - ox)
                    y, z = oy + t * (0.15 - oy), oz + t * (1 - oz)
                    assert 0.1 < y < 0.2
                    assert 0 < z < 3
                    projected.append((y, z))
    results["partial-occlusion-independent-bound"] = {
        "hidden_facing_point": [target_x, 0.15, 1],
        "projected_y_bounds": [min(p[0] for p in projected), max(p[0] for p in projected)],
        "projected_z_bounds": [min(p[1] for p in projected), max(p[1] for p in projected)],
    }
    slope_obstacle = ObstacleVolume("slope", Point3(5, 0.015, 0), 2, 0.01, 3.99)
    results["sloped-corridor"] = {
        "expected_blocked": False,
        "observed_blocked": line_of_sight_corridor_intersects_terrain_volume(
            Point3(0, 0, 0), Point3(10, 0, 10), slope_obstacle
        ),
        "proof": "Corridor z=x; all obstacle points have x>=4 but z<=3.99.",
    }
    return results


def timings(operation: Callable[[], object], repeats: int) -> dict[str, object]:
    samples = []
    for _ in range(repeats):
        started = perf_counter_ns()
        operation()
        samples.append((perf_counter_ns() - started) / 1e6)
    ordered = sorted(samples)
    return {
        "sample_count": repeats,
        "samples_ms": samples,
        "mean_ms": statistics.mean(samples),
        "median_ms": statistics.median(samples),
        "p95_nearest_rank_ms": ordered[math.ceil(0.95 * repeats) - 1],
        "max_ms": max(samples),
    }


def work_counts(operation: Callable[[], object]) -> dict[str, int]:
    # Separate instrumented execution; never mixed into timing samples or state.
    profiler = cProfile.Profile()
    profiler.runcall(operation)
    names = {
        "resolve_line_of_sight",
        "_resolve_model_line_of_sight",
        "_blockers_for_ray",
        "_terrain_broad_phase_intersects",
        "_model_broad_phase_intersects",
        "line_of_sight_corridor_intersects_terrain_volume",
        "line_of_sight_corridor_intersects_model",
        "_target_candidate",
    }
    totals: dict[str, int] = {}
    for entry in profiler.getstats():
        if not isinstance(entry.code, str) and entry.code.co_name in names:
            name = entry.code.co_name
            totals[name] = totals.get(name, 0) + entry.callcount
    return totals


def geometry_probe(name: str, repeats: int) -> dict[str, object]:
    started = perf_counter_ns()
    context = contexts()[name]
    preparation_ms = (perf_counter_ns() - started) / 1e6
    first = timings(context.resolve_line_of_sight, 1)
    return {
        "workload_status": (
            "nonoverlapping geometry diagnostic; no roster/lifecycle legality claim"
            if "nonoverlapping" in name
            else "synthetic geometry diagnostic; dense stress includes overlapping blockers"
        ),
        "context_construction_ms_including_all_case_definitions": preparation_ms,
        "first_authoritative_query": first,
        "repeated_authoritative_query": timings(context.resolve_line_of_sight, repeats),
        "instrumented_work_counts": work_counts(context.resolve_line_of_sight),
        "context_sha256": hashlib.sha256(
            json.dumps(context.to_payload(), sort_keys=True).encode()
        ).hexdigest(),
    }


def shooting_probe(count: int, repeats: int) -> dict[str, object]:
    from tests.phase13b_shooting_declaration_helpers import (
        _decision_request,
        shooting_lifecycle,
    )

    from warhammer40k_core.adapters.local_session import LocalGameSession
    from warhammer40k_core.engine.shooting_types import ShootingType

    setup_samples, construction_samples, payload_lengths = [], [], []
    candidate_counts, weapon_counts = [], []

    def run() -> None:
        started = perf_counter_ns()
        lifecycle, units = shooting_lifecycle(
            alpha_unit_ids=("attacker",),
            alpha_unit_specs=(
                ("attacker", "core-intercessor-like-infantry", "core-intercessor-like", count),
            ),
            enemy_datasheet=("core-intercessor-like-infantry", "core-intercessor-like", count),
        )
        session = LocalGameSession(lifecycle=lifecycle)
        setup_samples.append((perf_counter_ns() - started) / 1e6)
        started = perf_counter_ns()
        selection = _decision_request(session.advance_until_decision_or_terminal())
        kind = _decision_request(
            session.submit_option(
                request_id=selection.request_id,
                option_id=units["attacker"].unit_instance_id,
                result_id="order32:select",
            )
        )
        declaration = _decision_request(
            session.submit_option(
                request_id=kind.request_id,
                option_id=ShootingType.NORMAL.value,
                result_id="order32:normal",
            )
        )
        construction_samples.append((perf_counter_ns() - started) / 1e6)
        payload = declaration.payload
        assert isinstance(payload, dict)
        proposal = payload["proposal_request"]
        assert isinstance(proposal, dict)
        candidates, weapons = proposal["target_candidates"], proposal["available_weapons"]
        assert isinstance(candidates, list)
        assert isinstance(weapons, list)
        candidate_counts.append(len(candidates))
        weapon_counts.append(len(weapons))
        payload_lengths.append(len(json.dumps(payload)))

    run()
    first_setup, first_construction = setup_samples.pop(), construction_samples.pop()
    measurements = timings(run, repeats)
    counts = work_counts(run)
    # The final run was instrumented. Remove its wall times.
    setup_samples.pop()
    construction_samples.pop()
    return {
        "models_per_side": count,
        "fixture": "canonical phase13b shooting slice; not a complete game",
        "first_setup_ms": first_setup,
        "first_selection_to_declaration_ms": first_construction,
        "repeated_setup_ms": setup_samples,
        "repeated_selection_to_declaration_ms": construction_samples,
        "repeated_setup_and_construction": measurements,
        "declaration_payload_json_lengths": payload_lengths,
        "target_candidate_counts": candidate_counts,
        "available_weapon_counts": weapon_counts,
        "instrumented_work_counts": counts,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path)
    parser.add_argument("--repeats", type=int, default=7)
    parser.add_argument("--case", choices=(*contexts(), "shooting-5", "shooting-10"))
    args = parser.parse_args()
    if args.repeats < 2:
        parser.error("At least two repeated measurements are required.")
    if args.case is not None:
        result = (
            shooting_probe(int(args.case.removeprefix("shooting-")), args.repeats)
            if args.case.startswith("shooting-")
            else geometry_probe(args.case, args.repeats)
        )
        result["peak_process_rss_bytes"] = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss * (
            1 if sys.platform == "darwin" else 1024
        )
    else:
        result = {
            "spec_id": SPEC_ID,
            "runtime_commit": subprocess.check_output(
                ["git", "rev-parse", "HEAD"], cwd=ROOT, text=True
            ).strip(),
            "probe_sha256": hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
            "lock_sha256": hashlib.sha256((ROOT / "uv.lock").read_bytes()).hexdigest(),
            "python": sys.version,
            "platform": platform.platform(),
            "shapely": shapely.__version__,
            "numpy": numpy.__version__,
            "process_concurrency": 1,
            "timings_have_coverage_or_profiler": False,
            "full_game_certified": False,
            "counterexamples": counterexamples(),
            "measurements": {
                name: json.loads(
                    subprocess.check_output(
                        [
                            sys.executable,
                            "-m",
                            "scripts.probe_order32_visibility",
                            "--case",
                            name,
                            "--repeats",
                            str(args.repeats),
                        ],
                        cwd=ROOT,
                        text=True,
                    )
                )
                for name in (*contexts(), "shooting-5", "shooting-10")
            },
        }
    rendered = json.dumps(result, indent=2, sort_keys=True) + "\n"
    if args.output is None:
        print(rendered, end="")
    else:
        args.output.write_text(rendered, encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
