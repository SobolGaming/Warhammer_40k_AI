"""Order 41: active Shooting Stratagem enumeration on canonical real units."""

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

from tests.explosives_helpers import explosives_scene

from warhammer40k_core.engine.stratagem_catalog import (
    eleventh_edition_core_stratagem_catalog_records,
)
from warhammer40k_core.engine.stratagems import (
    StratagemCatalogIndex,
    StratagemEligibilityContext,
    stratagem_use_options_from_index,
)
from warhammer40k_core.engine.timing_windows import TimingTriggerKind

ROOT = Path(__file__).resolve().parents[1]
CASES = ("grenades", "explosives", "out_of_range")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    rows = []
    for case in CASES:
        for sample in range(7):
            started = time.perf_counter()
            lifecycle, _ = explosives_scene(
                keyword="EXPLOSIVES" if case == "explosives" else "GRENADES",
                target_x=30 if case == "out_of_range" else 17,
            )
            state = lifecycle.state
            assert state is not None
            index = StratagemCatalogIndex.from_records(
                eleventh_edition_core_stratagem_catalog_records()
            )
            context = StratagemEligibilityContext.from_state(
                state=state,
                player_id="player-a",
                trigger_kind=TimingTriggerKind.DURING_PHASE,
            )
            prepared = time.perf_counter()
            for _ in range(10):
                snapshots = stratagem_use_options_from_index(
                    state=state, index=index, context=context
                )
            finished = time.perf_counter()
            rows.append(
                {
                    "case": case,
                    "sample": sample,
                    "setup_seconds": prepared - started,
                    "query_seconds": (finished - prepared) / 10,
                    "option_count": len(snapshots),
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
        "workload_id": "order41-explosives-options-v1",
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
        "timing_boundary": "10 active Shooting option queries per sample; setup separate",
        "model_count": 4,
        "terrain_count": 0,
        "dice_calls": 0,
        "file_hashes": {
            name: hashlib.sha256((ROOT / name).read_bytes()).hexdigest()
            for name in (
                "scripts/measure_explosives_options.py",
                "uv.lock",
                "tests/phase13b_shooting_declaration_helpers.py",
                "tests/explosives_helpers.py",
                "src/warhammer40k_core/_engine_build_manifest.json",
            )
        },
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n")


if __name__ == "__main__":
    main()
