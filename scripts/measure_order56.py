"""Matched source-inventory request costs; diagnostic, not a full-game benchmark."""

import argparse
import hashlib
import json
import os
import platform
import statistics
import subprocess
import time
from pathlib import Path

from tests.phase13b_shooting_declaration_helpers import _shooting_lifecycle

from warhammer40k_core.adapters.local_session import LocalGameSession
from warhammer40k_core.engine.event_log import canonical_json


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--revision", required=True)
    args = parser.parse_args()
    samples = []
    for _ in range(7):
        start = time.perf_counter()
        lifecycle, units = _shooting_lifecycle(
            alpha_unit_ids=("source",), game_id="order56-performance-v1"
        )
        session = LocalGameSession(lifecycle)
        preparation = time.perf_counter() - start
        start = time.perf_counter()
        request = session.advance_until_decision_or_terminal().decision_request
        assert request is not None
        assert request.decision_type == "select_shooting_unit"
        request = session.submit_option(
            request_id=request.request_id,
            option_id=units["source"].unit_instance_id,
            result_id="order56:select-unit",
        ).decision_request
        assert request is not None
        assert request.decision_type == "select_shooting_type"
        request = session.submit_option(
            request_id=request.request_id, option_id="normal", result_id="order56:select-type"
        ).decision_request
        elapsed = time.perf_counter() - start
        assert request is not None
        assert request.decision_type == "submit_shooting_declaration"
        samples.append(
            {
                "preparation_seconds": preparation,
                "request_seconds": elapsed,
                "request_bytes": len(canonical_json(request.to_payload()).encode()),
                "decision_count": len(lifecycle.decision_controller.records),
                "complete": True,
            }
        )
    times = [sample["request_seconds"] for sample in samples]
    root = Path(__file__).resolve().parents[1]
    report = {
        "workload_id": "order56-select-weapons-v1",
        "revision": args.revision,
        "platform": platform.platform(),
        "python": platform.python_version(),
        "cpu": subprocess.check_output(
            ["sysctl", "-n", "machdep.cpu.brand_string"], text=True
        ).strip(),
        "memory_bytes": int(subprocess.check_output(["sysctl", "-n", "hw.memsize"], text=True)),
        "cpu_allocation": os.cpu_count(),
        "concurrency": 1,
        "host_role": "provisional",
        "models": 10,
        "units": 2,
        "terrain": "canonical shooting fixture",
        "decision_policy": "select source unit, normal shooting, stop at Select Weapons",
        "timing_boundary": (
            "facade phase advancement and two finite submissions; "
            "preparation separate; first sample cold"
        ),
        "hashes": {
            p: hashlib.sha256((root / p).read_bytes()).hexdigest()
            for p in (
                "scripts/measure_order56.py",
                "tests/phase13b_shooting_declaration_helpers.py",
                "uv.lock",
            )
        },
        "samples": samples,
        "mean_seconds": statistics.mean(times),
        "median_seconds": statistics.median(times),
        "maximum_seconds": max(times),
        "p95_seconds": sorted(times)[-1],
        "completion_rate": 1.0,
        "certification": "component diagnostic only; gameplay slice and complete games unmeasured",
        "budget_status": "deferred under owner performance direction; no threshold pass claimed",
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, indent=2) + "\n")
    print(
        json.dumps(
            {key: report[key] for key in ("mean_seconds", "maximum_seconds", "completion_rate")}
        )
    )


if __name__ == "__main__":
    main()
