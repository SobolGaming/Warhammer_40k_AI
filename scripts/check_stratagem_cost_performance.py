"""Fail closed on Order 37 cost-workload input drift or budget regressions."""

from __future__ import annotations

import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def main() -> None:
    directory = ROOT / "docs/performance/order37"
    base = json.loads((directory / "base-cost.json").read_text())
    head = json.loads((directory / "head-cost.json").read_text())
    budget = json.loads((directory / "budgets.json").read_text())
    for key in (
        "workload_id",
        "hashes",
        "platform",
        "python",
        "cpu",
        "memory_bytes",
        "mode",
        "timing_boundary",
    ):
        if base[key] != head[key]:
            raise ValueError(f"Cost comparison input drift: {key}")
    if head["workload_id"] != budget["workload_id"] or head["mode"] != "uninstrumented_timing":
        raise ValueError("Cost workload or instrumentation mismatch")
    for case in budget["provider_calls_per_registry_call"]:
        old, new = base["summaries"][case], head["summaries"][case]
        if new["completion_rate"] != 1 or new["samples"] != old["samples"]:
            raise ValueError(f"Incomplete or mismatched cost samples: {case}")
        if (
            new["mean"]
            > old["mean"] * budget["reference_mean_ratio"]
            + budget["reference_mean_allowance_seconds"]
            or new["max"] > budget["maximum_seconds"]
        ):
            raise ValueError(f"Cost timing budget exceeded: {case}")
    print("Order 37 cost timing budgets passed; complete-game certification remains outstanding.")


if __name__ == "__main__":
    main()
