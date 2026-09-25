"""Matched physical/assigned dice construction and serialization component costs."""

from __future__ import annotations

import argparse
import hashlib
import importlib
import json
import platform
import statistics
from pathlib import Path
from time import perf_counter

from scripts.measure_order65 import _host_inventory, _select_runtime_src


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--runtime-src", type=Path, default=Path("src"))
    parser.add_argument("--revision", required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    _select_runtime_src(args.runtime_src)
    dice = importlib.import_module("warhammer40k_core.core.dice")
    modified = importlib.import_module("warhammer40k_core.core.modified_dice")
    rows = []
    for quantity, assigned in ((1, False), (2, False), (1, True)):
        spec = dice.DiceRollSpec(
            dice.DiceExpression(quantity, 6), reason="Order 84 diagnostic", roll_type="hit_roll"
        )
        result = dice.DiceRollResult.from_values(
            roll_id="order84-benchmark", spec=spec, values=(3,) * quantity, source="fixed"
        )
        samples = []
        for _ in range(7):
            start = perf_counter()
            for _ in range(1000):
                state = dice.DiceRollState.from_result(result)
                if assigned:
                    state = state.with_result_override(
                        decision_id="result",
                        request_id="request",
                        source_rule_id="core:source",
                        replacement_value=6,
                    )
                restored = dice.DiceRollState.from_payload(state.to_payload())
                instance = dice.DiceRollInstance.from_state(restored)
                final = modified.ModifiedRollResult.from_unmodified(
                    modified.UnmodifiedRollResult.from_state(restored)
                )
                assert instance.total == final.final_value == (6 if assigned else 3 * quantity)
            samples.append(perf_counter() - start)
        rows.append(
            {
                "case": f"{quantity}d6-{'assigned' if assigned else 'physical'}",
                "samples_seconds": samples,
                "mean_seconds": statistics.mean(samples),
                "median_seconds": statistics.median(samples),
                "p95_seconds": max(samples),
                "maximum_seconds": max(samples),
                "operations_per_second": 1000 / statistics.mean(samples),
            }
        )
    cpu, memory = _host_inventory()
    report = {
        "workload": "order84-dice-results-v1",
        "revision": args.revision,
        "runtime_build_id": importlib.import_module(
            "warhammer40k_core.build_identity"
        ).current_engine_build_id(),
        "cpu": cpu,
        "memory_bytes": memory,
        "platform": platform.platform(),
        "python": platform.python_version(),
        "host_role": "provisional",
        "concurrency": 1,
        "timing_boundary": (
            "1000 state constructions, optional assignment, restore, instance and modifier "
            "interpretation; physical input setup excluded"
        ),
        "fixture": (
            "Fixed physical threes, assigned six; no units, geometry, RNG draws or policy search"
        ),
        "hashes": {
            name: hashlib.sha256(Path(name).read_bytes()).hexdigest()
            for name in ("scripts/measure_order84.py", "uv.lock")
        },
        "rows": rows,
        "completion_rate": 1,
        "coverage": False,
        "full_game_certified": False,
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, indent=2) + "\n")


if __name__ == "__main__":
    main()
