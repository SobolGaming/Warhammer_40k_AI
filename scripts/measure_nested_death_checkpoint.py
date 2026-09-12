"""Order 42: restore a real nested Shooting-in-Fight death-reaction checkpoint."""

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

from tests.target_replacement_reaction_helpers import fidelity_nested_death_scene

from warhammer40k_core.engine.lifecycle import GameLifecycle
from warhammer40k_core.engine.phase import GameLifecycleError

ROOT = Path(__file__).resolve().parents[1]


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--expect-rejection", action="store_true")
    parser.add_argument("--control", action="store_true")
    args = parser.parse_args()
    rows = []
    for sample in range(7):
        started = time.perf_counter()
        session = fidelity_nested_death_scene(advance_to_death=not args.control)
        checkpoint = session.lifecycle.to_payload()
        prepared = time.perf_counter()
        try:
            restored = GameLifecycle.from_payload(checkpoint)
        except GameLifecycleError as error:
            finished = time.perf_counter()
            if not args.expect_rejection or str(error) != (
                "Pending destruction cause state binding drift."
            ):
                raise
            outcome = "rejected"
        else:
            finished = time.perf_counter()
            assert not args.expect_rejection
            assert restored.to_payload() == checkpoint
            outcome = "restored"
        rows.append(
            {
                "sample": sample,
                "setup_seconds": prepared - started,
                "query_seconds": finished - prepared,
                "outcome": outcome,
            }
        )
    values = [row["query_seconds"] for row in rows]
    report = {
        "workload_id": "order42-nested-death-checkpoint-v1",
        "case": "accepted_defense" if args.control else "nested_death",
        "rows": rows,
        "summary": {
            "mean": statistics.mean(values),
            "median": statistics.median(values),
            "p95": max(values),
            "maximum": max(values),
            "samples": len(values),
            "completion_rate": sum(row["outcome"] == "restored" for row in rows) / len(rows),
            "measurement_completion_rate": 1.0,
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
        "timing_boundary": "GameLifecycle.from_payload; scene construction and payload separate",
        "model_count": 4,
        "terrain_count": 0,
        "seed": "order42-fidelity-retarget-1",
        "decision_policy": (
            "both Fidelity uses accepted; stop before resolving the fresh target's attacks"
            if args.control
            else "both Fidelity uses accepted; fresh target destroyed; reaction pending"
        ),
        "file_hashes": {
            name: hashlib.sha256((ROOT / name).read_bytes()).hexdigest()
            for name in (
                "scripts/measure_nested_death_checkpoint.py",
                "uv.lock",
                "tests/target_replacement_reaction_helpers.py",
                "tests/retained_attack_helpers.py",
                "tests/phase15c_fight_order_helpers.py",
                "src/warhammer40k_core/_engine_build_manifest.json",
            )
        },
    }
    args.output.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n")


if __name__ == "__main__":
    main()
