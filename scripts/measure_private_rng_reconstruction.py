"""Matched native restore/fork with one shared explicit configuration payload."""

from __future__ import annotations

import argparse
import json
import os
import platform
from pathlib import Path
from typing import cast

from scripts.measure_ingress_reconstruction import CHECKPOINTS, OPERATIONS, sample
from scripts.measure_order63 import _host_inventory, _select_runtime_src

ROOT = Path(__file__).resolve().parents[1]
WORKLOAD_ID = "loaded-ingress-private-rng-reconstruction-v2"
FIXTURE = ROOT / "tests/support/fixtures/private_rng_reconstruction_config.json"


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--runtime-src", type=Path, default=ROOT / "src")
    parser.add_argument("--revision", required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    _select_runtime_src(args.runtime_src)
    from tests.order63_reserve_transport_helpers import (
        rapid_disembark,
        reserve_transport_session,
        submit_ingress,
    )
    from tests.psychic_modifier_helpers import pending_request

    from warhammer40k_core.build_identity import verified_engine_build_identity
    from warhammer40k_core.engine.game_state import GameConfig
    from warhammer40k_core.engine.game_state_payloads import GameConfigPayload
    from warhammer40k_core.engine.phase import LifecycleStatusKind

    rows = []
    for checkpoint in CHECKPOINTS:
        # Each arm decodes exactly these bytes using its own native loader.
        # V45 ignores the new seed field; V46 consumes it. This workload rolls no dice.
        config = GameConfig.from_payload(cast(GameConfigPayload, json.loads(FIXTURE.read_bytes())))
        session = reserve_transport_session(config=config)
        submit_ingress(session)
        if checkpoint != "ingress":
            outcome = rapid_disembark(session, y=5)
            assert outcome.status_kind is not LifecycleStatusKind.INVALID, outcome
        if checkpoint == "later_decision":
            request = pending_request(session)
            outcome = session.submit_option(
                request_id=request.request_id,
                result_id="reconstruction:later-selection",
                option_id="army-alpha:remaining-unit",
            )
            assert outcome.status_kind is not LifecycleStatusKind.INVALID, outcome
        state = session.lifecycle.state
        assert state is not None
        saved = session.lifecycle.to_payload()
        for operation in OPERATIONS:
            rows.append(
                {
                    "checkpoint": checkpoint,
                    "operation": operation,
                    "samples": [sample(session, operation) for _ in range(7)],
                    "profile": sample(session, operation, profile=True),
                    "unit_count": sum(len(a.units) for a in state.army_definitions),
                    "model_count": sum(
                        len(u.own_models) for a in state.army_definitions for u in a.units
                    ),
                    "decision_records": len(saved["decisions"]["records"]),
                    "event_records": len(saved["decisions"]["event_log"]),
                }
            )
            print(f"Completed {checkpoint}/{operation}", flush=True)
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
        "concurrency": 1,
        "coverage": False,
        "completed": True,
        "rows": rows,
        "full_game_certified": False,
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")


if __name__ == "__main__":
    main()
