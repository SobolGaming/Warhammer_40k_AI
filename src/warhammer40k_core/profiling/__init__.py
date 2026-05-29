"""Profiling helpers for CORE V2 smoke and manual performance gates."""

from warhammer40k_core.profiling.movement_pathing import (
    HotspotReport,
    PathingBenchmarkResult,
    PerformanceBudget,
    PerformanceScenario,
    PerformanceScenarioKind,
    phase10u_nightly_scenarios,
    phase10u_smoke_scenarios,
    run_hotspot_profile,
    run_performance_scenario,
)

__all__ = [
    "HotspotReport",
    "PathingBenchmarkResult",
    "PerformanceBudget",
    "PerformanceScenario",
    "PerformanceScenarioKind",
    "phase10u_nightly_scenarios",
    "phase10u_smoke_scenarios",
    "run_hotspot_profile",
    "run_performance_scenario",
]
