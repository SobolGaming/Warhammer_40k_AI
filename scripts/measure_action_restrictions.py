"""Measure the Order 34 Action eligibility and exact-boundary workload."""

from __future__ import annotations

import argparse
import cProfile
import hashlib
import json
import math
import platform
import statistics
import subprocess
import time
from pathlib import Path
from types import CodeType

from tests.phase17n_primary_mission_helpers import phase17n_action_opportunity_fixture

from warhammer40k_core.core.army_catalog import ArmyCatalog
from warhammer40k_core.engine.decision_result import DecisionResult
from warhammer40k_core.engine.effects import EffectExpirationBoundary
from warhammer40k_core.engine.mission_action_eligibility import (
    mission_action_unit_ineligibility_reason,
    rules_unit_started_mission_action_this_turn,
)
from warhammer40k_core.engine.mission_decisions import apply_mission_decision
from warhammer40k_core.engine.phase import BattlePhase
from warhammer40k_core.engine.phases.shooting import shooting_unit_can_select_to_shoot
from warhammer40k_core.engine.runtime_modifiers import RuntimeModifierRegistry

ROOT = Path(__file__).resolve().parents[1]
QUERY_REPETITIONS = 100


def sample(*, profile: bool) -> dict[str, object]:
    started = time.perf_counter()
    state, decisions, request = phase17n_action_opportunity_fixture()
    catalog = ArmyCatalog.phase9a_canonical_content_pack()
    registry = RuntimeModifierRegistry.empty()
    option = next(row for row in request.options if row.option_id.startswith("start:"))
    result = DecisionResult.for_request(
        request=request, result_id="order34-benchmark-action", selected_option_id=option.option_id
    )
    actor = request.actor_id
    assert actor is not None
    unit = next(
        unit for army in state.army_definitions if army.player_id == actor for unit in army.units
    )
    profiler = cProfile.Profile()
    prepared = time.perf_counter()
    if profile:
        profiler.enable()
    record = decisions.submit_result(result)
    apply_mission_decision(
        state=state,
        decisions=decisions,
        request=record.request,
        result=result,
        runtime_modifier_registry=registry,
    )
    for _ in range(QUERY_REPETITIONS):
        mission_action_unit_ineligibility_reason(
            state=state,
            player_id=actor,
            unit_instance_id=unit.unit_instance_id,
            runtime_modifier_registry=registry,
        )
        shooting_unit_can_select_to_shoot(
            state=state,
            player_id=actor,
            unit=unit,
            army_catalog=catalog,
        )
        rules_unit_started_mission_action_this_turn(
            state=state,
            player_id=actor,
            unit_instance_id=unit.unit_instance_id,
        )
    for phase in (BattlePhase.SHOOTING, BattlePhase.CHARGE, BattlePhase.FIGHT):
        state.expire_persisting_effects_at_boundary(
            EffectExpirationBoundary.phase_end(
                battle_round=state.battle_round, phase=phase, player_id=actor
            )
        )
    state.expire_persisting_effects_at_boundary(
        EffectExpirationBoundary.turn_end(battle_round=state.battle_round, player_id=actor)
    )
    if profile:
        profiler.disable()
    completed = time.perf_counter()
    counts: dict[str, int] = {}
    if profile:
        for entry in profiler.getstats():
            if isinstance(entry.code, CodeType):
                name = entry.code.co_name
                if name in {
                    "rules_unit_identity_ids",
                    "rules_unit_view_by_id",
                    "rules_unit_persisting_effects",
                    "persisting_effects_for_lineage",
                    "record_persisting_effect",
                    "expire_persisting_effects_at_boundary",
                }:
                    counts[name] = counts.get(name, 0) + entry.callcount
    return {
        "setup_seconds": prepared - started,
        "slice_seconds": completed - prepared,
        "work_counts": counts,
        "decision_count": len(decisions.records),
        "action_count": len(state.mission_action_states),
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--samples", type=int, default=7)
    parser.add_argument("--work-counts", action="store_true")
    args = parser.parse_args()
    if args.samples < 1:
        parser.error("samples must be positive")
    rows = [sample(profile=args.work_counts) for _ in range(args.samples)]
    values = sorted(float(str(row["slice_seconds"])) for row in rows)
    report = {
        "workload_id": "order34-action-restriction-slice-v1",
        "commit": subprocess.check_output(
            ["git", "rev-parse", "HEAD"], cwd=ROOT, text=True
        ).strip(),
        "runtime_diff_sha256": hashlib.sha256(
            subprocess.check_output(["git", "diff", "HEAD", "--", "src"], cwd=ROOT)
        ).hexdigest(),
        "platform": platform.platform(),
        "python": platform.python_version(),
        "hardware_status": "provisional local host; single process; no competing test workers",
        "cpu": subprocess.check_output(
            ["sysctl", "-n", "machdep.cpu.brand_string"], text=True
        ).strip(),
        "memory_bytes": int(subprocess.check_output(["sysctl", "-n", "hw.memsize"], text=True)),
        "mode": "work_counts_instrumented_not_timing_evidence"
        if args.work_counts
        else "uninstrumented_timing",
        "query_repetitions": QUERY_REPETITIONS,
        "samples": rows,
        "mean_seconds": statistics.mean(values),
        "median_seconds": statistics.median(values),
        "p95_seconds": values[math.ceil(len(values) * 0.95) - 1],
        "maximum_seconds": max(values),
        "completion_rate": 1.0,
        "slices_per_second": 1 / statistics.mean(values),
        "hashes": {
            name: hashlib.sha256((ROOT / name).read_bytes()).hexdigest()
            for name in (
                "uv.lock",
                "scripts/measure_action_restrictions.py",
                "tests/phase17n_primary_mission_helpers.py",
            )
        },
        "full_game_certified": False,
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, indent=2) + "\n")
    print(json.dumps(report))


if __name__ == "__main__":
    main()
