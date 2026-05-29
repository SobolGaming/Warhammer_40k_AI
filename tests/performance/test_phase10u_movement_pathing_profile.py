from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path
from typing import cast

from warhammer40k_core.profiling.movement_pathing import (
    HotspotReport,
    HotspotReportPayload,
    PerformanceBudget,
    PerformanceScenario,
    PerformanceScenarioKind,
    phase10u_smoke_scenarios,
    run_hotspot_profile,
    run_performance_scenario,
)

ROOT = Path(__file__).resolve().parents[2]


def test_phase10u_pathing_smoke_profiles_crowded_infantry_validation() -> None:
    scenario = PerformanceScenario.for_kind(
        PerformanceScenarioKind.CROWDED_INFANTRY,
        seed=10_010,
        iteration_count=1,
    )

    result = run_performance_scenario(scenario, timer=_StepTimer())

    assert result.path_validation_runs == 1
    assert result.valid_path_count == 1
    assert result.invalid_path_count == 0
    assert result.path_sampled_pose_count > 0
    assert result.model_collision_check_count > 0


def test_phase10u_terrain_legality_smoke_profiles_ruins_validation() -> None:
    scenario = PerformanceScenario.for_kind(
        PerformanceScenarioKind.RUINS_TERRAIN,
        seed=10_011,
        iteration_count=1,
    )

    result = run_performance_scenario(scenario, timer=_StepTimer())

    assert result.terrain_legality_runs == 1
    assert result.terrain_sampled_pose_count > 0
    assert result.terrain_segment_count > 0
    assert result.terrain_violation_count == 0


def test_phase10u_hotspot_report_round_trips_and_covers_required_scenarios() -> None:
    scenarios = phase10u_smoke_scenarios(seed=10_012, iteration_count=1)
    budget = PerformanceBudget(
        budget_id="phase10u-test-budget",
        max_elapsed_ns=1_000,
    )

    report = run_hotspot_profile(scenarios, budget=budget, timer=_StepTimer(step_ns=100))
    payload = cast(HotspotReportPayload, json.loads(report.to_json()))
    blob = json.dumps(payload, sort_keys=True)

    assert {scenario.scenario_kind for scenario in scenarios} == set(PerformanceScenarioKind)
    assert "<" not in blob
    assert "object at 0x" not in blob
    assert HotspotReport.from_payload(payload).to_payload() == payload
    assert report.budget_violations == ()


def test_phase10u_same_seed_and_scenario_produce_same_benchmark_result() -> None:
    scenario = PerformanceScenario.for_kind(
        PerformanceScenarioKind.FLY_PATHS,
        seed=10_013,
        iteration_count=2,
    )

    first = run_performance_scenario(scenario, timer=_StepTimer(start_ns=50, step_ns=25))
    second = run_performance_scenario(scenario, timer=_StepTimer(start_ns=50, step_ns=25))

    assert first.to_payload() == second.to_payload()


def test_phase10u_report_id_is_execution_artifact_not_workload_identity() -> None:
    scenario = PerformanceScenario.for_kind(
        PerformanceScenarioKind.CROWDED_INFANTRY,
        seed=10_014,
        iteration_count=1,
    )

    first = run_hotspot_profile((scenario,), timer=_StepTimer(start_ns=50, step_ns=25))
    second = run_hotspot_profile((scenario,), timer=_StepTimer(start_ns=50, step_ns=50))

    assert first.results[0].elapsed_ns != second.results[0].elapsed_ns
    assert first.report_id != second.report_id
    assert first.results[0].scenario_hash == second.results[0].scenario_hash
    assert first.results[0].workload_digest == second.results[0].workload_digest


def test_phase10u_cli_exits_nonzero_when_configured_budget_is_exceeded() -> None:
    env = os.environ.copy()
    src_path = str(ROOT / "src")
    existing_pythonpath = env.get("PYTHONPATH")
    env["PYTHONPATH"] = (
        src_path if existing_pythonpath is None else f"{src_path}{os.pathsep}{existing_pythonpath}"
    )

    completed: subprocess.CompletedProcess[str] = subprocess.run(
        [
            sys.executable,
            str(ROOT / "scripts" / "profile_movement_pathing.py"),
            "--scenario",
            PerformanceScenarioKind.CROWDED_INFANTRY.value,
            "--iterations",
            "1",
            "--max-elapsed-ms",
            "0",
        ],
        cwd=ROOT,
        env=env,
        text=True,
        capture_output=True,
        check=False,
    )
    payload = cast(HotspotReportPayload, json.loads(completed.stdout))

    assert completed.returncode == 2
    assert payload["budget_violations"]


class _StepTimer:
    def __init__(self, *, start_ns: int = 1_000, step_ns: int = 100) -> None:
        self._current_ns = start_ns
        self._step_ns = step_ns

    def __call__(self) -> int:
        value = self._current_ns
        self._current_ns += self._step_ns
        return value
