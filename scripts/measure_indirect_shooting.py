"""Measure the versioned Order 33 facade slice; timing and cProfile are separate runs."""

from __future__ import annotations

import argparse
import cProfile
import hashlib
import json
import math
import platform
import pstats
import statistics
import subprocess
import time
from pathlib import Path

from tests.indirect_shooting_helpers import (
    complete_indirect_attack,
    indirect_session,
    select_indirect_declaration,
    shooting_event_payloads,
    submit_indirect_declaration,
)

ROOT = Path(__file__).resolve().parents[1]


def sample(*, visible: bool, observer: bool, profile: bool) -> dict[str, object]:
    started = time.perf_counter()
    session = indirect_session(visible=visible, observer=observer, model_count=5)
    prepared = time.perf_counter()
    profiler = cProfile.Profile()
    if profile:
        profiler.enable()
    request = select_indirect_declaration(session)
    submit_indirect_declaration(session, request)
    complete_indirect_attack(session)
    if profile:
        profiler.disable()
    completed = time.perf_counter()
    assert len(shooting_event_payloads(session, "attack_sequence_completed")) == 1

    counts = {}
    if profile:
        for (_filename, _line, name), (_primitive, calls, _own, _total, _callers) in pstats.Stats(
            profiler
        ).stats.items():
            if name in {
                "resolve_line_of_sight",
                "resolve_visibility_pair",
                "_target_visible_to_friendly_unit",
                "_apply_phase13d_weapon_modifiers",
            }:
                counts[name] = counts.get(name, 0) + calls
    return {
        "setup_seconds": prepared - started,
        "slice_seconds": completed - prepared,
        "work_counts": counts,
        "decision_count": len(session.lifecycle.decision_controller.records),
        "hit_count": sum(
            row["step"] == "hit" for row in shooting_event_payloads(session, "attack_sequence_step")
        ),
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--samples", type=int, default=7)
    parser.add_argument("--work-counts", action="store_true")
    args = parser.parse_args()
    if args.samples < 1:
        parser.error("samples must be positive")
    results = {}
    for name, visible, observer in (
        ("visible-self-observer", True, False),
        ("unseen-no-observer", False, False),
        ("unseen-friendly-observer", False, True),
    ):
        rows = [
            sample(visible=visible, observer=observer, profile=args.work_counts)
            for _ in range(args.samples)
        ]
        values = sorted(float(row["slice_seconds"]) for row in rows)
        results[name] = {
            "samples": rows,
            "mean_seconds": statistics.mean(values),
            "median_seconds": statistics.median(values),
            "p95_seconds": values[math.ceil(len(values) * 0.95) - 1],
            "maximum_seconds": max(values),
            "completion_rate": 1.0,
            "slices_per_second": 1 / statistics.mean(values),
        }
    report = {
        "workload_id": "order33-indirect-shooting-slice-v1",
        "commit": subprocess.check_output(
            ["git", "rev-parse", "HEAD"], cwd=ROOT, text=True
        ).strip(),
        "runtime_diff_sha256": hashlib.sha256(
            subprocess.check_output(["git", "diff", "HEAD", "--", "src"], cwd=ROOT)
        ).hexdigest(),
        "engine_manifest_sha256": hashlib.sha256(
            (ROOT / "src/warhammer40k_core/_engine_build_manifest.json").read_bytes()
        ).hexdigest(),
        "platform": platform.platform(),
        "python": platform.python_version(),
        "mode": "work_counts_instrumented_not_timing_evidence"
        if args.work_counts
        else "uninstrumented_timing",
        "hashes": {
            name: hashlib.sha256((ROOT / name).read_bytes()).hexdigest()
            for name in (
                "uv.lock",
                "scripts/measure_indirect_shooting.py",
                "tests/indirect_shooting_helpers.py",
            )
        },
        "results": results,
        "full_game_certified": False,
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, indent=2) + "\n")
    print(json.dumps({"output": str(args.output), "results": results}))


if __name__ == "__main__":
    main()
