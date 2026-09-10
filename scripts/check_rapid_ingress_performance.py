"""Validate identical-input Order 35 timing evidence against its reference budget."""

from __future__ import annotations

import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def main() -> None:
    directory = ROOT / "docs/performance/order35"
    base = json.loads((directory / "base.json").read_text())
    head = json.loads((directory / "head.json").read_text())
    budget = json.loads((directory / "budgets.json").read_text())
    for key in (
        "workload_id",
        "hashes",
        "platform",
        "python",
        "cpu",
        "memory_bytes",
        "timing_boundary",
        "mode",
    ):
        if base[key] != head[key]:
            raise ValueError(f"Comparison input drift: {key}")
    if head["workload_id"] != budget["workload_id"] or head["mode"] != "uninstrumented_timing":
        raise ValueError("Incorrect timing workload or instrumentation")
    ratios = {}
    for case, maximum in budget["max_seconds"].items():
        old, new = base["summaries"][case], head["summaries"][case]
        if new["completion_rate"] != 1 or new["samples"] != old["samples"]:
            raise ValueError(f"Incomplete or mismatched samples: {case}")
        allowed_mean = (
            old["mean"] * budget["reference_mean_ratio"]
            + budget["reference_mean_allowance_seconds"]
        )
        if new["mean"] > allowed_mean or new["max"] > maximum:
            raise ValueError(f"Reference timing budget exceeded: {case}: {new}")
        ratios[case] = new["mean"] / old["mean"]
    print(json.dumps({"status": "passed", "mean_ratios": ratios, "full_game_certified": False}))


if __name__ == "__main__":
    main()
