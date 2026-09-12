"""Order 40: deterministic attack-modifier query workload on canonical real units."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import platform
import statistics
import subprocess
import time
from dataclasses import replace
from pathlib import Path

from tests.smokescreen_helpers import smoke_grant, smoke_scene

from warhammer40k_core.engine.attack_modifier_snapshots import attack_modifier_snapshots
from warhammer40k_core.engine.phase import BattlePhase
from warhammer40k_core.engine.runtime_modifiers import RuntimeModifierRegistry

ROOT = Path(__file__).resolve().parents[1]
CASES = ("plain", "direct", "obscured", "clear")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    rows = []
    for case in CASES:
        for sample in range(7):
            started = time.perf_counter()
            lifecycle, units, pool = smoke_scene(smoke_y=20 if case == "clear" else 10)
            state = lifecycle.state
            assert state is not None
            if case != "plain":
                state.record_persisting_effect(smoke_grant(units["smoke"].unit_instance_id))
            if case == "direct":
                pool = replace(pool, target_unit_instance_id=units["smoke"].unit_instance_id)
            registry = RuntimeModifierRegistry()
            prepared = time.perf_counter()
            for _ in range(10):
                snapshots = attack_modifier_snapshots(
                    state=state,
                    pool=pool,
                    source_phase=BattlePhase.SHOOTING,
                    runtime_modifier_registry=registry,
                )
            finished = time.perf_counter()
            rows.append(
                {
                    "case": case,
                    "sample": sample,
                    "setup_seconds": prepared - started,
                    "query_seconds": (finished - prepared) / 10,
                    "snapshot_count": len(snapshots),
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
        "workload_id": "order40-smokescreen-cover-v1",
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
        "timing_boundary": "10 attack_modifier_snapshots queries per sample; setup separate",
        "model_count": 3,
        "terrain_count": 0,
        "dice_calls": 0,
        "file_hashes": {
            name: hashlib.sha256((ROOT / name).read_bytes()).hexdigest()
            for name in (
                "scripts/measure_smokescreen_cover.py",
                "uv.lock",
                "tests/phase13b_shooting_declaration_helpers.py",
                "tests/generic_modifier_helpers.py",
                "tests/smokescreen_helpers.py",
                "src/warhammer40k_core/_engine_build_manifest.json",
            )
        },
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n")


if __name__ == "__main__":
    main()
