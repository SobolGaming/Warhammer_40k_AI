"""Matched fixed and rerolled Surge grant validation through canonical sessions."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import platform
import statistics
import subprocess
import time
from dataclasses import replace
from pathlib import Path

from tests.surge_helpers import SOURCE, TARGET, surge_descriptor, surge_lifecycle

from warhammer40k_core.adapters.local_session import LocalGameSession
from warhammer40k_core.build_identity import current_engine_build_id
from warhammer40k_core.core.dice import (
    DiceExpression,
    DiceRollSpec,
    RerollComponentSelectionPolicy,
    RerollPermission,
)
from warhammer40k_core.engine.dice import DiceRollManager
from warhammer40k_core.engine.surge_authority import validate_surge_request
from warhammer40k_core.engine.triggered_movement import TriggeredMovementEligibleUnit
from warhammer40k_core.engine.triggered_movement_selection import (
    triggered_movement_unit_selection_request,
)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--revision", required=True)
    args = parser.parse_args()
    setup_start = time.perf_counter()
    cases = []
    for reroll in (False, True):
        lifecycle = surge_lifecycle()
        state = lifecycle.state
        assert state is not None
        descriptor = surge_descriptor(lifecycle=lifecycle)
        unit = TriggeredMovementEligibleUnit(SOURCE, "test:hook", descriptor.source_rule_id)
        if reroll:
            roll = DiceRollManager(
                state.game_id, event_log=lifecycle.decision_controller.event_log
            ).roll(
                DiceRollSpec(
                    expression=DiceExpression(quantity=1, sides=6),
                    reason="Source granted Surge distance",
                    roll_type="movement_end_surge.distance",
                    actor_id="player-a",
                )
            )
            descriptor = replace(descriptor, max_distance_inches=float(roll.current_total))
            unit = replace(
                unit,
                distance_roll_state=roll,
                distance_reroll_permission=RerollPermission(
                    source_id=descriptor.source_rule_id,
                    timing_window="after_surge_distance_roll",
                    owning_player_id="player-a",
                    eligible_roll_type="movement_end_surge.distance",
                    component_selection_policy=RerollComponentSelectionPolicy.WHOLE_ROLL,
                ),
            )
        request = triggered_movement_unit_selection_request(
            state=state,
            decisions=lifecycle.decision_controller,
            player_id="player-a",
            descriptor=descriptor,
            eligible_units=(unit,),
        )
        lifecycle.decision_controller.request_decision(request)
        session = LocalGameSession(lifecycle)
        session.advance_until_decision_or_terminal()
        status = session.submit_option(
            request_id=request.request_id,
            result_id="authority-select",
            option_id=f"surge:{SOURCE}:target:{TARGET}",
        )
        assert status.decision_request is not None
        if reroll:
            status = session.submit_option(
                request_id=status.decision_request.request_id,
                result_id="authority-reroll",
                option_id="reroll:0",
            )
        assert status.decision_request is not None
        cases.append((state, lifecycle.decision_controller, status.decision_request))
    setup_seconds = time.perf_counter() - setup_start
    samples = []
    for _ in range(7):
        start = time.perf_counter()
        for state, decisions, request in cases:
            validate_surge_request(state=state, decisions=decisions, request=request)
        samples.append(time.perf_counter() - start)
    root = Path.cwd()
    report = {
        "workload_id": "order52-surge-grant-authority-v1",
        "revision": args.revision,
        "engine_build_id": current_engine_build_id(),
        "platform": platform.platform(),
        "python": platform.python_version(),
        "cpu_allocation": os.cpu_count(),
        "cpu": subprocess.check_output(
            ["sysctl", "-n", "machdep.cpu.brand_string"], text=True
        ).strip(),
        "memory_bytes": int(subprocess.check_output(["sysctl", "-n", "hw.memsize"], text=True)),
        "concurrency": 1,
        "setup_seconds": setup_seconds,
        "timing_boundary": "Two Surge authority validations: fixed and rerolled; setup excluded",
        "scenario": {"models": 10, "moving_models": 5, "terrain_count": 0, "seed": state.game_id},
        "event_counts": [len(decisions.event_log.records) for _, decisions, _ in cases],
        "hashes": {
            "driver": hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
            "helper": hashlib.sha256((root / "tests/surge_helpers.py").read_bytes()).hexdigest(),
            "lock": hashlib.sha256((root / "uv.lock").read_bytes()).hexdigest(),
        },
        "samples_seconds": samples,
        "mean_seconds": statistics.mean(samples),
        "median_seconds": statistics.median(samples),
        "maximum_seconds": max(samples),
        "completion_rate": 1,
        "full_game_certified": False,
        "budgets": {"maximum_seconds": 0.5, "mean_ratio": 2.0, "mean_additive_seconds": 0.02},
    }
    args.output.write_text(json.dumps(report, indent=2) + "\n")


if __name__ == "__main__":
    main()
