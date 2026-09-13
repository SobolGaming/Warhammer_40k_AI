"""Matched Order 44 Shooting/Fight costs with the same finite choice policy."""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import platform
import statistics
import subprocess
import time
from pathlib import Path

from tests.lethal_hits_helpers import attack_steps, complete_attack, lethal_session

from warhammer40k_core.engine.phase import BattlePhase

ROOT = Path(__file__).resolve().parents[1]


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--samples", default=7, type=int)
    args = parser.parse_args()
    if args.samples < 1:
        parser.error("samples must be positive")
    results = {}
    for phase in (BattlePhase.SHOOTING, BattlePhase.FIGHT):
        rows = []
        for _ in range(args.samples):
            start = time.perf_counter()
            session = lethal_session(phase)
            prepared = time.perf_counter()
            complete_attack(session)
            end = time.perf_counter()
            rows.append(
                {
                    "setup_seconds": prepared - start,
                    "slice_seconds": end - prepared,
                    "decision_count": len(session.lifecycle.decision_controller.records),
                    "hit_count": len(attack_steps(session, "hit")),
                    "lethal_choice_count": sum(
                        record.request.decision_type == "select_lethal_hit_wound"
                        for record in session.lifecycle.decision_controller.records
                    ),
                }
            )
        times = sorted(row["slice_seconds"] for row in rows)
        results[phase.value] = {
            "samples": rows,
            "mean_seconds": statistics.mean(times),
            "median_seconds": statistics.median(times),
            "p95_seconds": times[math.ceil(len(times) * 0.95) - 1],
            "maximum_seconds": max(times),
            "completion_rate": 1,
        }
    report = {
        "workload_id": "order44-lethal-hits-slice-v1",
        "revision": subprocess.check_output(["git", "rev-parse", "HEAD"], text=True).strip(),
        "runtime_diff_sha256": hashlib.sha256(
            subprocess.check_output(["git", "diff", "HEAD", "--", "src"], cwd=ROOT)
        ).hexdigest(),
        "engine_manifest_sha256": hashlib.sha256(
            (ROOT / "src/warhammer40k_core/_engine_build_manifest.json").read_bytes()
        ).hexdigest(),
        "platform": platform.platform(),
        "python": platform.python_version(),
        "mode": "uninstrumented_timing",
        "hashes": {
            name: hashlib.sha256((ROOT / name).read_bytes()).hexdigest()
            for name in (
                "uv.lock",
                "tests/lethal_hits_helpers.py",
                "tests/phase13b_shooting_declaration_helpers.py",
                "tests/phase15c_fight_order_helpers.py",
                "tests/psychic_modifier_helpers.py",
                "scripts/measure_lethal_hits.py",
            )
        },
        "results": results,
        "full_game_certified": False,
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, indent=2) + "\n")


if __name__ == "__main__":
    main()
