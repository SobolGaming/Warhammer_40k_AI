"""Head-only off-battlefield dispatch/restore diagnostic, without timing budgets."""

from __future__ import annotations

import argparse
import hashlib
import json
import platform
from pathlib import Path
from time import perf_counter

from tests.order90_revival_helpers import offboard_scene

from warhammer40k_core.adapters.local_session import LocalGameSession
from warhammer40k_core.build_identity import verified_engine_build_identity
from warhammer40k_core.engine.damage_allocation import model_by_id
from warhammer40k_core.engine.healing import resolve_healing_until_blocked
from warhammer40k_core.engine.lifecycle import GameLifecycle
from warhammer40k_core.engine.phase import LifecycleStatusKind


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    rows = []
    for reserves in (False, True):
        for full_health in (False, True):
            samples = []
            for index in range(3):
                start = perf_counter()
                lifecycle, effect, model_id = offboard_scene(
                    reserves=reserves, full_health=full_health
                )
                state = lifecycle.state
                assert state is not None
                _, request = resolve_healing_until_blocked(
                    state=state,
                    decisions=lifecycle.decision_controller,
                    ruleset_descriptor=state.runtime_ruleset_descriptor(),
                    effect=effect,
                )
                assert request is not None
                session = LocalGameSession(lifecycle)
                session.advance_until_decision_or_terminal()
                prepared = perf_counter()
                status = session.submit_option(
                    request_id=request.request_id,
                    option_id=request.options[0].option_id,
                    result_id=f"diagnostic-{index}",
                )
                submitted = perf_counter()
                assert status.status_kind is not LifecycleStatusKind.INVALID
                model = model_by_id(state=state, model_instance_id=model_id)
                assert model.current_wounds == (model.initial_wounds if full_health else 1)
                payload = lifecycle.to_payload()
                restored = GameLifecycle.from_payload(payload)
                assert restored.to_payload() == payload
                samples.append(
                    {
                        "setup_seconds": prepared - start,
                        "submit_seconds": submitted - prepared,
                        "restore_seconds": perf_counter() - submitted,
                        "returned_wounds": model.current_wounds,
                    }
                )
            rows.append({"reserves": reserves, "full_health": full_health, "samples": samples})
    report = {
        "workload": "order90-offboard-dispatch-restore-v1",
        "runtime_build_id": verified_engine_build_identity().build_id,
        "platform": platform.platform(),
        "python": platform.python_version(),
        "concurrency": 1,
        "coverage": False,
        "full_game_samples": 0,
        "hardware": "provisional Apple M5 Pro, 64 GiB",
        "baseline_limitation": "Base cannot correctly execute full-health cargo/reserve returns.",
        "timing_boundary": "finite submission and independently authenticated lifecycle restore",
        "hashes": {
            name: hashlib.sha256(Path(name).read_bytes()).hexdigest()
            for name in (
                "scripts/benchmark_order90_revival.py",
                "tests/order90_revival_helpers.py",
                "uv.lock",
            )
        },
        "rows": rows,
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, indent=2) + "\n")


if __name__ == "__main__":
    main()
