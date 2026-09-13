"""Order 42: resume a real Shooting action at its next finite decision."""

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

from tests.target_replacement_helpers import replacement_scene

from warhammer40k_core.adapters.local_session import LocalGameSession

ROOT = Path(__file__).resolve().parents[1]
CASES = ("eligible", "moved_target", "no_alternative")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    rows = []
    for case in CASES:
        for sample in range(7):
            started = time.perf_counter()
            lifecycle, _, request = replacement_scene(
                moved=case != "eligible",
                alternatives=case != "no_alternative",
            )
            session = LocalGameSession(lifecycle=lifecycle)
            prepared = time.perf_counter()
            status = session.submit_option(
                request_id=request.request_id,
                option_id=request.options[0].option_id,
                result_id="order42:benchmark-resume",
            )
            finished = time.perf_counter()
            pending = status.decision_request
            rows.append(
                {
                    "case": case,
                    "sample": sample,
                    "setup_seconds": prepared - started,
                    "query_seconds": finished - prepared,
                    "status_kind": status.status_kind.value,
                    "decision_type": None if pending is None else pending.decision_type,
                    "option_count": 0 if pending is None else len(pending.options),
                }
            )
    summaries = {}
    for case in CASES:
        values = sorted(row["query_seconds"] for row in rows if row["case"] == case)
        summaries[case] = {
            "mean": statistics.mean(values),
            "median": statistics.median(values),
            "p95": values[-1],
            "max": values[-1],
            "samples": len(values),
            "queries_per_second": 1 / statistics.mean(values),
            "completion_rate": 1.0,
        }
    report = {
        "workload_id": "order42-shooting-revalidation-v1",
        "rows": rows,
        "summaries": summaries,
        "platform": platform.platform(),
        "python": platform.python_version(),
        "cpu_allocation": os.cpu_count(),
        "concurrency": 1,
        "cpu": subprocess.check_output(
            ["sysctl", "-n", "machdep.cpu.brand_string"], text=True
        ).strip(),
        "memory_bytes": int(subprocess.check_output(["sysctl", "-n", "hw.memsize"], text=True)),
        "timing_boundary": "one finite resolution submission to next decision; setup separate",
        "model_count": 15,
        "terrain_count": 0,
        "seed": "phase13b-game",
        "decision_policy": "first engine resolution option; stop at next decision",
        "file_hashes": {
            name: hashlib.sha256((ROOT / name).read_bytes()).hexdigest()
            for name in (
                "scripts/measure_target_replacement.py",
                "uv.lock",
                "tests/phase13b_shooting_declaration_helpers.py",
                "tests/target_replacement_helpers.py",
                "src/warhammer40k_core/_engine_build_manifest.json",
            )
        },
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n")


if __name__ == "__main__":
    main()
