"""Order 42: accept a replacement during real Fight-phase retained Shooting."""

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

from tests.target_replacement_reaction_helpers import fidelity_retained_replacement_scene

from warhammer40k_core.adapters.local_session import LocalGameSession

ROOT = Path(__file__).resolve().parents[1]


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    rows = []
    for sample in range(7):
        started = time.perf_counter()
        lifecycle, units, request = fidelity_retained_replacement_scene()
        session = LocalGameSession(lifecycle=lifecycle)
        status = session.submit_option(
            request_id=request.request_id,
            option_id=request.options[0].option_id,
            result_id="order42:benchmark-resolution",
        )
        request = status.decision_request
        assert request is not None
        assert request.decision_type == "select_target_replacement"
        prepared = time.perf_counter()
        status = session.submit_option(
            request_id=request.request_id,
            option_id=f"target:{units['new'].unit_instance_id}",
            result_id="order42:benchmark-replacement",
        )
        finished = time.perf_counter()
        pending = status.decision_request
        assert pending is not None
        rows.append(
            {
                "sample": sample,
                "setup_seconds": prepared - started,
                "query_seconds": finished - prepared,
                "decision_type": pending.decision_type,
                "option_ids": [option.option_id for option in pending.options],
            }
        )
    values = [row["query_seconds"] for row in rows]
    report = {
        "workload_id": "order42-out-of-phase-replacement-v1",
        "rows": rows,
        "summary": {
            "mean": statistics.mean(values),
            "median": statistics.median(values),
            "p95": max(values),
            "maximum": max(values),
            "samples": len(values),
            "completion_rate": 1.0,
            "queries_per_second": 1 / statistics.mean(values),
        },
        "platform": platform.platform(),
        "python": platform.python_version(),
        "cpu_allocation": os.cpu_count(),
        "concurrency": 1,
        "cpu": subprocess.check_output(
            ["sysctl", "-n", "machdep.cpu.brand_string"], text=True
        ).strip(),
        "memory_bytes": int(subprocess.check_output(["sysctl", "-n", "hw.memsize"], text=True)),
        "timing_boundary": "replacement selection submission to next decision; setup separate",
        "model_count": 4,
        "terrain_count": 0,
        "seed": "order42-fidelity-retarget-1",
        "decision_policy": "decline original defense; accept fresh target; stop at next decision",
        "file_hashes": {
            name: hashlib.sha256((ROOT / name).read_bytes()).hexdigest()
            for name in (
                "scripts/measure_out_of_phase_target_replacement.py",
                "uv.lock",
                "tests/target_replacement_reaction_helpers.py",
                "tests/retained_attack_helpers.py",
                "tests/phase15c_fight_order_helpers.py",
                "src/warhammer40k_core/_engine_build_manifest.json",
            )
        },
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n")


if __name__ == "__main__":
    main()
