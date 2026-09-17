"""Reproduce matched, uninstrumented oversized disembark resolver costs."""

import argparse
import hashlib
import json
import os
import platform
import statistics
import subprocess
import time
from pathlib import Path

from tests.disembark_eligibility_helpers import PASSENGER_ID, TRANSPORT_ID
from tests.large_model_disembark_helpers import large_disembark_placement, large_disembark_session

from warhammer40k_core.engine.battlefield_presence import battlefield_scenario_for_state
from warhammer40k_core.engine.damage_allocation import unit_by_id
from warhammer40k_core.engine.transports import (
    DisembarkModeKind,
    DisembarkSelection,
    TransportMovementStatus,
    resolve_disembark,
)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--revision", required=True)
    args = parser.parse_args()
    cases = []
    for diameter, gap in ((5, 0.5), (5, 1.01), (3, 0.5), (2, 0.5)):
        session = large_disembark_session(diameter=diameter)
        state = session.lifecycle.state
        assert state is not None
        assert state.battlefield_state is not None
        cases.append(
            (
                state,
                DisembarkSelection(
                    player_id="player-a",
                    battle_round=1,
                    unit_instance_id=PASSENGER_ID,
                    transport_unit_instance_id=TRANSPORT_ID,
                    attempted_placement=large_disembark_placement(session, gap=gap),
                    disembark_mode=DisembarkModeKind.TACTICAL_DISEMBARK,
                    transport_movement_status=TransportMovementStatus.NOT_MOVED,
                ),
            )
        )
    first_state = cases[0][0]
    assert first_state.battlefield_state is not None
    assert first_state.mission_setup is not None
    samples = []
    for _ in range(7):
        start = time.perf_counter()
        results = tuple(
            resolve_disembark(
                scenario=battlefield_scenario_for_state(state=state),
                ruleset_descriptor=state.runtime_ruleset_descriptor(),
                cargo_state=state.transport_cargo_states[0],
                selection=selection,
                unit=unit_by_id(state=state, unit_instance_id=PASSENGER_ID),
                transport_placement=battlefield_scenario_for_state(
                    state=state
                ).battlefield_state.unit_placement_by_id(TRANSPORT_ID),
            )
            for state, selection in cases
        )
        samples.append(
            {"seconds": time.perf_counter() - start, "accepted": [r.is_valid for r in results]}
        )
    times = [r["seconds"] for r in samples]
    root = Path(__file__).resolve().parents[1]
    report = {
        "workload_id": "order55-oversized-disembark-v1",
        "revision": args.revision,
        "platform": platform.platform(),
        "python": platform.python_version(),
        "cpu": subprocess.check_output(
            ["sysctl", "-n", "machdep.cpu.brand_string"], text=True
        ).strip(),
        "memory_bytes": int(subprocess.check_output(["sysctl", "-n", "hw.memsize"], text=True)),
        "cpu_allocation": os.cpu_count(),
        "concurrency": 1,
        "timing_boundary": (
            f"{len(cases)} disembark resolutions; fixture creation excluded; first sample cold"
        ),
        "scenario": {
            "models": sum(
                len(unit.own_models) for army in first_state.army_definitions for unit in army.units
            ),
            "placed_models": len(first_state.battlefield_state.placed_model_ids()),
            "terrain_count": len(first_state.mission_setup.terrain_features),
            "diameters_inches": [5, 5, 3, 2],
            "gaps_inches": [0.5, 1.01, 0.5, 0.5],
        },
        "hashes": {
            p: hashlib.sha256((root / p).read_bytes()).hexdigest()
            for p in (
                "uv.lock",
                "scripts/measure_order55.py",
                "tests/large_model_disembark_helpers.py",
                "tests/disembark_eligibility_helpers.py",
            )
        },
        "samples": samples,
        "mean_seconds": statistics.mean(times),
        "median_seconds": statistics.median(times),
        "maximum_seconds": max(times),
        "completion_rate": 1,
        "full_game_certified": False,
        "budgets": {"mean_ratio": 3, "mean_additive_seconds": 0.05, "maximum_seconds": 1},
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, indent=2) + "\n")


if __name__ == "__main__":
    main()
