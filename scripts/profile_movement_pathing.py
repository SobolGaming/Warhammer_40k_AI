from __future__ import annotations

import argparse
from collections.abc import Sequence
from pathlib import Path

from warhammer40k_core.profiling.movement_pathing import (
    PerformanceBudget,
    PerformanceScenario,
    PerformanceScenarioKind,
    phase10u_nightly_scenarios,
    phase10u_smoke_scenarios,
    run_hotspot_profile,
)


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Run deterministic Phase 10U movement/pathing profiling scenarios.",
    )
    parser.add_argument(
        "--scenario",
        choices=("all", *(kind.value for kind in PerformanceScenarioKind)),
        default="all",
    )
    parser.add_argument("--profile-size", choices=("smoke", "nightly"), default="smoke")
    parser.add_argument("--seed", type=int, default=10_001)
    parser.add_argument("--iterations", type=int, default=1)
    parser.add_argument("--max-elapsed-ms", type=float, default=None)
    parser.add_argument("--output", type=Path, default=None)
    args = parser.parse_args(argv)

    scenarios = _scenarios(
        scenario_token=args.scenario,
        profile_size=args.profile_size,
        seed=args.seed,
        iteration_count=args.iterations,
    )
    budget = (
        None
        if args.max_elapsed_ms is None
        else PerformanceBudget(
            budget_id="phase10u-cli-budget",
            max_elapsed_ns=int(args.max_elapsed_ms * 1_000_000),
        )
    )
    report = run_hotspot_profile(scenarios, budget=budget)
    report_json = report.to_json()

    if args.output is not None:
        args.output.write_text(report_json + "\n", encoding="utf-8")
    print(report_json)
    return 2 if report.budget_violations else 0


def _scenarios(
    *,
    scenario_token: str,
    profile_size: str,
    seed: int,
    iteration_count: int,
) -> tuple[PerformanceScenario, ...]:
    if scenario_token == "all":
        if profile_size == "nightly":
            return phase10u_nightly_scenarios(seed=seed, iteration_count=iteration_count)
        return phase10u_smoke_scenarios(seed=seed, iteration_count=iteration_count)
    return (
        PerformanceScenario.for_kind(
            scenario_token,
            seed=seed,
            iteration_count=iteration_count,
            profile_size=profile_size,
        ),
    )


if __name__ == "__main__":
    raise SystemExit(main())
