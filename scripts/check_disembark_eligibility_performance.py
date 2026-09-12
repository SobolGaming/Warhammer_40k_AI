"""Check the retained Order 38 facade timing comparison without relaxing budgets."""

from __future__ import annotations

import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
CASES = {"ordinary", "assault", "shock", "both", "restricted"}


def main() -> None:
    directory = ROOT / "docs/performance/order38"
    base = json.loads((directory / "base.json").read_text())
    head = json.loads((directory / "head.json").read_text())
    budget = json.loads((directory / "budgets.json").read_text())
    for key in (
        "workload_id",
        "hashes",
        "platform",
        "python",
        "cpu",
        "cpu_allocation",
        "memory_bytes",
        "mode",
        "timing_boundary",
        "concurrency",
    ):
        if base[key] != head[key]:
            raise ValueError(f"Disembark timing input drift: {key}")
    if head["workload_id"] != budget["workload_id"] or head["mode"] != "uninstrumented_timing":
        raise ValueError("Disembark workload or instrumentation mismatch")
    if set(base["summaries"]) != CASES or set(head["summaries"]) != CASES:
        raise ValueError("Disembark timing cases are incomplete")
    for case in sorted(CASES):
        old, new = base["summaries"][case], head["summaries"][case]
        if (
            old["completion_rate"] != 1
            or new["completion_rate"] != 1
            or new["samples"] < 7
            or new["samples"] != old["samples"]
        ):
            raise ValueError(f"Incomplete or mismatched disembark samples: {case}")
        if (
            new["mean"]
            > old["mean"] * budget["reference_mean_ratio"]
            + budget["reference_mean_allowance_seconds"]
            or new["max"] > budget["maximum_seconds"]
        ):
            raise ValueError(f"Disembark timing budget exceeded: {case}")
    print("Order 38 slice budgets passed; complete-game certification remains outstanding.")


if __name__ == "__main__":
    main()
