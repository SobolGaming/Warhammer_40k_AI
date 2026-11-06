"""Matched native tactical draw operations through the unchanged state API."""

from __future__ import annotations

import argparse
import json
import os
import platform
from pathlib import Path
from time import perf_counter
from typing import cast

from scripts.measure_order63 import _host_inventory, _select_runtime_src
from scripts.measure_private_rng_reconstruction import FIXTURE

ROOT = Path(__file__).resolve().parents[1]
WORKLOAD_ID = "native-private-tactical-draw-v1"


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--runtime-src", type=Path, default=ROOT / "src")
    parser.add_argument("--revision", required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    _select_runtime_src(args.runtime_src)
    from warhammer40k_core.build_identity import verified_engine_build_identity
    from warhammer40k_core.engine.game_state import GameConfig, GameState
    from warhammer40k_core.engine.game_state_payloads import GameConfigPayload
    from warhammer40k_core.engine.missions import mission_pack_for_id

    config = GameConfig.from_payload(cast(GameConfigPayload, json.loads(FIXTURE.read_bytes())))
    assert config.mission_setup is not None
    pack = mission_pack_for_id(config.mission_setup.mission_pack_id)
    deck = {
        mission.secondary_mission_id
        for mission in pack.secondary_missions
        if mission.availability.value in {"tactical", "both"}
    }
    rows = []
    for case, count in (("1", 1), ("2", 2), ("deck", len(deck))):
        state = GameState.from_config(config)
        while state.current_setup_step is not state.setup_sequence[-1]:
            state.complete_current_setup_step()
        state.complete_final_setup_step_before_battle()
        state.enter_battle()
        times = []
        for _ in range(7):
            started = perf_counter()
            for _ in range(500):
                cards = state.draw_tactical_secondary_cards(
                    player_id=config.player_ids[0],
                    source_result_id="benchmark-reused-provenance",
                    draw_count=count,
                )
                assert len(cards) == count
                assert len({card.secondary_mission_id for card in cards}) == count
                assert {card.secondary_mission_id for card in cards} <= deck
                for card in cards:
                    state.forget_secondary_mission_card_state(card)
                assert not state.secondary_mission_card_states
            times.append(perf_counter() - started)
        rows.append({"case": case, "samples_seconds": times, "operations": 500})
        print(f"Completed tactical draw case {case}", flush=True)
    cpu, memory = _host_inventory()
    report = {
        "workload_id": WORKLOAD_ID,
        "revision": args.revision,
        "runtime_build_id": verified_engine_build_identity().build_id,
        "cpu": cpu,
        "memory_bytes": memory,
        "cpu_allocation": os.cpu_count(),
        "platform": platform.platform(),
        "python": platform.python_version(),
        "completed": True,
        "concurrency": 1,
        "coverage": False,
        "rows": rows,
        "full_game_certified": False,
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")


if __name__ == "__main__":
    main()
