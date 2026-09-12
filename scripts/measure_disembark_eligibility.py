"""Measure transport action enumeration through the canonical facade (Order 38)."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import platform
import statistics
import subprocess
import time
from pathlib import Path

from tests.disembark_eligibility_helpers import PASSENGER_ID, disembark_session
from tests.psychic_modifier_helpers import pending_request

from warhammer40k_core.engine.transports import DisembarkModeKind

ROOT = Path(__file__).resolve().parents[1]
CASES = {
    "ordinary": (),
    "assault": (DisembarkModeKind.ASSAULT_DISEMBARK,),
    "shock": (DisembarkModeKind.SHOCK_DISEMBARK,),
    "both": (DisembarkModeKind.ASSAULT_DISEMBARK, DisembarkModeKind.SHOCK_DISEMBARK),
    "restricted": (DisembarkModeKind.ASSAULT_DISEMBARK,),
}


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--samples", type=int, default=7)
    args = parser.parse_args()
    if args.samples < 1:
        parser.error("samples must be positive")
    rows = []
    for case, modes in CASES.items():
        for _ in range(args.samples):
            started = time.perf_counter()
            session = disembark_session(modes, eligible=case != "restricted")
            request = pending_request(session)
            prepared = time.perf_counter()
            status = session.submit_option(
                request_id=request.request_id,
                result_id="order38:select-passenger",
                option_id=PASSENGER_ID,
            )
            finished = time.perf_counter()
            assert status.decision_request is not None
            assert status.decision_request.decision_type == "select_movement_action"
            rows.append(
                {
                    "case": case,
                    "setup_seconds": prepared - started,
                    "slice_seconds": finished - prepared,
                    "option_count": len(status.decision_request.options),
                }
            )
    summaries = {}
    for case in CASES:
        values = sorted(r["slice_seconds"] for r in rows if r["case"] == case)
        summaries[case] = {
            "mean": statistics.mean(values),
            "median": statistics.median(values),
            "max": max(values),
            "p95": values[-1],
            "samples": len(values),
            "completion_rate": 1.0,
            "queries_per_second": 1 / statistics.mean(values),
        }
    report = {
        "workload_id": "order38-disembark-options-v1",
        "rows": rows,
        "summaries": summaries,
        "commit": subprocess.check_output(["git", "rev-parse", "HEAD"], text=True).strip(),
        "platform": platform.platform(),
        "python": platform.python_version(),
        "cpu": subprocess.check_output(
            ["sysctl", "-n", "machdep.cpu.brand_string"], text=True
        ).strip(),
        "memory_bytes": int(subprocess.check_output(["sysctl", "-n", "hw.memsize"], text=True)),
        "timing_boundary": (
            "Facade select passenger submission through returned action request; setup separate"
        ),
        "mode": "uninstrumented_timing",
        "concurrency": 1,
        "cpu_allocation": os.cpu_count(),
        "runtime_manifest_sha256": hashlib.sha256(
            (ROOT / "src/warhammer40k_core/_engine_build_manifest.json").read_bytes()
        ).hexdigest(),
        "hashes": {
            p: hashlib.sha256((ROOT / p).read_bytes()).hexdigest()
            for p in (
                "scripts/measure_disembark_eligibility.py",
                "tests/disembark_eligibility_helpers.py",
                "uv.lock",
            )
        },
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n")
    print(json.dumps(summaries))


if __name__ == "__main__":
    main()
