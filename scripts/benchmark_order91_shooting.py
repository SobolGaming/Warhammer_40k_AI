"""Matched unit/type eligibility diagnostic, serial and without coverage."""

from __future__ import annotations

import argparse
import hashlib
import json
import platform
import statistics
from pathlib import Path
from time import perf_counter

from tests.empty_shooting_helpers import SHOOTER, empty_shooting_session

from warhammer40k_core.build_identity import verified_engine_build_identity
from warhammer40k_core.engine.phases.shooting_eligibility import (
    _legal_shooting_types_for_rules_unit,
    _legal_shooting_unit_ids,
)
from warhammer40k_core.engine.phases.shooting_model import ShootingPhaseState
from warhammer40k_core.engine.rules_units import rules_unit_view_by_id


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    rows = []
    for no_weapons, reachable in ((True, False), (False, False), (False, True)):
        setup, samples, counts = [], [], []
        for _ in range(5):
            start = perf_counter()
            session = empty_shooting_session(no_weapons=no_weapons, reachable=reachable)
            state, config = session.lifecycle.state, session.lifecycle.config
            assert state is not None
            assert config is not None
            unit = rules_unit_view_by_id(state=state, unit_instance_id=SHOOTER)
            shooting = ShootingPhaseState(
                battle_round=state.battle_round, active_player_id="player-a"
            )
            prepared = perf_counter()
            units = _legal_shooting_unit_ids(
                state=state,
                shooting_state=shooting,
                ruleset_descriptor=config.ruleset_descriptor,
                army_catalog=config.army_catalog,
            )
            types = _legal_shooting_types_for_rules_unit(
                state=state,
                rules_unit=unit,
                ruleset_descriptor=config.ruleset_descriptor,
                army_catalog=config.army_catalog,
            )
            setup.append(prepared - start)
            samples.append(perf_counter() - prepared)
            counts.append([len(units), len(types)])
        rows.append(
            {
                "no_weapons": no_weapons,
                "reachable": reachable,
                "setup_seconds": setup,
                "samples_seconds": samples,
                "mean": statistics.mean(samples),
                "median": statistics.median(samples),
                "p95_and_maximum": max(samples),
                "counts": counts,
            }
        )
    report = {
        "workload": "order91-shooting-selection-v1",
        "runtime_build_id": verified_engine_build_identity().build_id,
        "platform": platform.platform(),
        "python": platform.python_version(),
        "concurrency": 1,
        "coverage": False,
        "hardware": "provisional Apple M5 Pro, 64 GiB",
        "full_game_samples": 0,
        "timing_boundary": (
            "shared unit and type eligibility queries; catalog/facade restore setup separate"
        ),
        "fixture": (
            "one friendly and one enemy infantry, no terrain, "
            "20 inch separation, game_id order91-empty-shooting"
        ),
        "hashes": {
            name: hashlib.sha256(Path(name).read_bytes()).hexdigest()
            for name in (
                "scripts/benchmark_order91_shooting.py",
                "tests/empty_shooting_helpers.py",
                "uv.lock",
            )
        },
        "rows": rows,
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, indent=2) + "\n")


if __name__ == "__main__":
    main()
