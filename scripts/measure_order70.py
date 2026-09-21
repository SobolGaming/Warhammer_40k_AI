"""Matched current-model Fights First registry costs, outside fixture preparation."""

from __future__ import annotations

import argparse
import hashlib
import importlib
import json
import os
import platform
import statistics
import time
from pathlib import Path

from scripts.measure_order65 import _host_inventory, _select_runtime_src


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--runtime-src", type=Path, default=Path("src"))
    parser.add_argument("--revision", required=True)
    args = parser.parse_args()
    _select_runtime_src(args.runtime_src)
    helpers = importlib.import_module("tests.firing_deck_helpers")
    effects = importlib.import_module("warhammer40k_core.engine.effects")
    fights = importlib.import_module("warhammer40k_core.engine.fights_first")
    rows = []
    for count in (0, 1, 4):
        session, _, _ = helpers.firing_deck_session(contribute=False)
        state = session.lifecycle.state
        assert state is not None
        units = [(army.player_id, unit) for army in state.army_definitions for unit in army.units]
        for player, unit in units[:count]:
            state.record_persisting_effect(
                effects.PersistingEffect(
                    effect_id=f"order70:{unit.unit_instance_id}",
                    source_rule_id="order70:benchmark-grant",
                    owner_player_id=player,
                    target_unit_instance_ids=(unit.unit_instance_id,),
                    started_battle_round=1,
                    expiration=effects.EffectExpiration.end_of_battle(),
                    effect_payload={"effect_kind": "fights_first"},
                )
            )
        samples = []
        for _ in range(7):
            start = time.perf_counter()
            for _ in range(100):
                registry = fights.FightsFirstRegistry.from_state(state)
            samples.append(time.perf_counter() - start)
        rows.append(
            {
                "grant_count": count,
                "unit_count": len(units),
                "model_count": sum(len(unit.own_models) for _, unit in units),
                "source_count": len(registry.sources),
                "samples_seconds": samples,
                "mean_seconds": statistics.mean(samples),
                "maximum_seconds": max(samples),
                "complete": True,
            }
        )
    cpu, memory = _host_inventory()
    report = {
        "workload": "order70-fights-first-v1",
        "revision": args.revision,
        "runtime_build_id": importlib.import_module(
            "warhammer40k_core.build_identity"
        ).current_engine_build_id(),
        "platform": platform.platform(),
        "python": platform.python_version(),
        "cpu": cpu,
        "memory_bytes": memory,
        "cpu_allocation": os.cpu_count(),
        "concurrency": 1,
        "host_role": "provisional",
        "timing_boundary": (
            "100 live registry queries; canonical Firing Deck fixture preparation excluded; "
            "no RNG, geometry queries or decisions in timer"
        ),
        "hashes": {
            name: hashlib.sha256(Path(name).read_bytes().replace(b"\r\n", b"\n")).hexdigest()
            for name in ("scripts/measure_order70.py", "tests/firing_deck_helpers.py", "uv.lock")
        },
        "rows": rows,
        "full_game_certified": False,
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")


if __name__ == "__main__":
    main()
