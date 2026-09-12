"""Order 39: deterministic attack-modifier query workload on canonical real units."""

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

from tests.generic_modifier_helpers import generic_effect
from tests.phase13b_shooting_declaration_helpers import (
    _attack_pool_for_test,
    _catalog_with_stealth_datasheet,
    _first_weapon_profile,
    _shooting_lifecycle,
)

from warhammer40k_core.engine.attack_modifier_snapshots import attack_modifier_snapshots
from warhammer40k_core.engine.phase import BattlePhase
from warhammer40k_core.engine.runtime_modifiers import RuntimeModifierRegistry

ROOT = Path(__file__).resolve().parents[1]
CASES = ("plain", "native", "grant", "duplicate_grants")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    rows = []
    for case in CASES:
        for sample in range(7):
            started = time.perf_counter()
            lifecycle, units = _shooting_lifecycle(
                alpha_unit_ids=("intercessor-1",),
                catalog=_catalog_with_stealth_datasheet() if case == "native" else None,
            )
            state = lifecycle.state
            assert state is not None
            attacker, target = units["intercessor-1"], units["enemy"]
            for index in range(2 if case == "duplicate_grants" else int(case == "grant")):
                state.record_persisting_effect(
                    generic_effect(
                        effect_id=f"order39:grant:{index}",
                        owner_player_id="player-b",
                        target_unit_instance_ids=(target.unit_instance_id,),
                        target_kind="this_unit",
                        effect_kind="grant_ability",
                        parameters={"ability": "stealth"},
                    )
                )
            pool = _attack_pool_for_test(
                attacker=attacker,
                defender=target,
                weapon_profile=_first_weapon_profile(lifecycle, attacker),
                attacks=1,
            )
            registry = RuntimeModifierRegistry()
            prepared = time.perf_counter()
            for _ in range(100):
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
                    "query_seconds": (finished - prepared) / 100,
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
        "workload_id": "order39-stealth-cover-v1",
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
        "timing_boundary": "100 attack_modifier_snapshots queries per sample; setup separate",
        "model_count": 10,
        "terrain_count": 0,
        "dice_calls": 0,
        "file_hashes": {
            name: hashlib.sha256((ROOT / name).read_bytes()).hexdigest()
            for name in (
                "scripts/measure_stealth_cover.py",
                "uv.lock",
                "tests/phase13b_shooting_declaration_helpers.py",
                "tests/generic_modifier_helpers.py",
                "src/warhammer40k_core/_engine_build_manifest.json",
            )
        },
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n")


if __name__ == "__main__":
    main()
