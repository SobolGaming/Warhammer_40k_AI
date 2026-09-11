"""Order 37: real catalog cost choices, target validation, spending and failure."""

from __future__ import annotations

import argparse
import cProfile
import hashlib
import json
import platform
import statistics
import subprocess
import time
from pathlib import Path
from types import CodeType

from tests.rapid_ingress_helpers import reach_ingress_window, submit_ingress_target
from tests.stratagem_cost_helpers import cost_session

from warhammer40k_core.engine.phase import LifecycleStatusKind

ROOT = Path(__file__).resolve().parents[1]
CASES = ("optional", "automatic", "unaffordable", "zero")


def sample(case: str, *, profile: bool = False) -> dict[str, object]:
    started = time.perf_counter()
    session = cost_session(
        available_cp=1 if case in {"zero", "unaffordable"} else 20,
        optional_increases=case != "automatic",
        discount=9 if case == "zero" else 0,
    )
    request = reach_ingress_window(session)
    prepared = time.perf_counter()
    profiler = cProfile.Profile()
    if profile:
        profiler.enable()
    status = submit_ingress_target(session, request)
    accepted = 0
    while status.decision_request is not None and status.decision_request.decision_type == (
        "select_stratagem_cost_modifier_option"
    ):
        request = status.decision_request
        option = next(
            o
            for o in request.options
            if isinstance(o.payload, dict) and o.payload.get("use_ability") is True
        )
        status = session.submit_option(
            request_id=request.request_id,
            result_id=f"order37:measure-{accepted}",
            option_id=option.option_id,
        )
        accepted += 1
        assert accepted <= 5
    if profile:
        profiler.disable()
    finished = time.perf_counter()
    assert status.status_kind is not LifecycleStatusKind.INVALID, status
    state = session.lifecycle.state
    assert state is not None
    record = state.stratagem_use_records[-1]
    counts: dict[str, int] = {}
    if profile:
        for entry in profiler.getstats():
            if isinstance(entry.code, CodeType):
                code = entry.code
                if code.co_name == "modified_command_point_cost_with_sources" or (
                    code.co_name == "handler"
                    and code.co_filename.endswith("catalog_command_point_runtime.py")
                ):
                    counts[code.co_name] = counts.get(code.co_name, 0) + entry.callcount
    return {
        "case": case,
        "setup_seconds": prepared - started,
        "slice_seconds": finished - prepared,
        "accepted": accepted,
        "cost": record.command_point_cost,
        "effects_resolved": record.effects_resolved,
        "commitments": len(record.command_point_modifier_ids),
        "work_counts": counts,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--samples", type=int, default=7)
    parser.add_argument("--work-counts", action="store_true")
    args = parser.parse_args()
    if args.samples < 1:
        parser.error("samples must be positive")
    rows = [sample(case, profile=args.work_counts) for case in CASES for _ in range(args.samples)]
    summaries = {}
    for case in CASES:
        values = sorted(float(str(r["slice_seconds"])) for r in rows if r["case"] == case)
        summaries[case] = {
            "mean": statistics.mean(values),
            "median": statistics.median(values),
            "max": max(values),
            "samples": len(values),
            "completion_rate": 1.0,
        }
    report = {
        "workload_id": "order37-stratagem-cost-v1",
        "commit": subprocess.check_output(["git", "rev-parse", "HEAD"], text=True).strip(),
        "platform": platform.platform(),
        "python": platform.python_version(),
        "cpu": subprocess.check_output(
            ["sysctl", "-n", "machdep.cpu.brand_string"], text=True
        ).strip(),
        "memory_bytes": int(subprocess.check_output(["sysctl", "-n", "hw.memsize"], text=True)),
        "mode": "profile" if args.work_counts else "uninstrumented_timing",
        "hardware_status": "provisional; one process, no competing test workers",
        "models": 10,
        "terrain_shapes": 0,
        "rng": "none in measured cost slice",
        "timing_boundary": (
            "fixture and initial pending request separate; "
            "target submission through cost choices to spend/failure"
        ),
        "hashes": {
            p: hashlib.sha256((ROOT / p).read_bytes()).hexdigest()
            for p in (
                "uv.lock",
                "scripts/measure_stratagem_cost.py",
                "tests/stratagem_cost_helpers.py",
                "tests/rapid_ingress_helpers.py",
                "tests/core_stratagem_helpers.py",
            )
        },
        "summaries": summaries,
        "samples": rows,
        "full_game_certified": False,
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, indent=2) + "\n")
    print(json.dumps(summaries))


if __name__ == "__main__":
    main()
