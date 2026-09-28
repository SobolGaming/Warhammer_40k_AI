"""Matched facade declaration/completion and authenticated restore; run serially."""

from __future__ import annotations

import argparse
import hashlib
import json
import platform
import statistics
import subprocess
from pathlib import Path
from time import perf_counter

from tests.empty_shooting_helpers import empty_shooting_session
from tests.optional_shooting_helpers import (
    finish_selected_weapons,
    optional_payload,
    select_optional_shooting,
)
from tests.phase13b_shooting_declaration_helpers import _proposal_from_request

from warhammer40k_core.build_identity import verified_engine_build_identity
from warhammer40k_core.core.weapon_profiles import WeaponKeyword
from warhammer40k_core.engine.event_log import validate_json_value
from warhammer40k_core.engine.phase import LifecycleStatusKind


def measure(*, new_paths: bool) -> dict[str, object]:
    rows: list[dict[str, object]] = []
    for kind in ("targeted", "targetless", "empty") if new_paths else ("targeted",):
        setup: list[float] = []
        samples: list[float] = []
        restore: list[float] = []
        counts: list[dict[str, int]] = []
        for _ in range(5):
            start = perf_counter()
            session = empty_shooting_session(
                reachable=True, spare=True, keywords=(WeaponKeyword.ONE_SHOT,)
            )
            request = select_optional_shooting(session)
            payload = (
                validate_json_value(
                    _proposal_from_request(
                        request=request, target_unit_id="army-beta:enemy"
                    ).to_payload()
                )
                if kind == "targeted"
                else optional_payload(request)
            )
            assert isinstance(payload, dict)
            if kind == "empty":
                payload["declarations"] = []
            prepared = perf_counter()
            status = session.submit_parameterized_payload(
                request_id=request.request_id, payload=payload, result_id="order95:benchmark"
            )
            assert status.status_kind is not LifecycleStatusKind.INVALID
            finish_selected_weapons(session, "order95:benchmark")
            completed = perf_counter()
            assert session.fork().lifecycle.to_payload() == session.lifecycle.to_payload()
            restore.append(perf_counter() - completed)
            samples.append(completed - prepared)
            setup.append(prepared - start)
            state = session.lifecycle.state
            assert state is not None
            counts.append(
                {
                    "ranged_history": len(state.ranged_attack_history_records),
                    "one_shot_selections": len(state.one_shot_weapon_use_records),
                }
            )
        rows.append(
            {
                "case": kind,
                "setup_seconds": setup,
                "samples_seconds": samples,
                "restore_seconds": restore,
                "mean": statistics.mean(samples),
                "median": statistics.median(samples),
                "p95_and_maximum": max(samples),
                "restore_mean": statistics.mean(restore),
                "work_counts": counts,
            }
        )
    return {
        "workload": "order95-optional-shooting-v1",
        "runtime_build_id": verified_engine_build_identity().build_id,
        "platform": platform.platform(),
        "python": platform.python_version(),
        "cpu": subprocess.check_output(
            ["sysctl", "-n", "machdep.cpu.brand_string"], text=True
        ).strip(),
        "memory_bytes": int(subprocess.check_output(["sysctl", "-n", "hw.memsize"], text=True)),
        "hardware_status": "provisional",
        "concurrency": 1,
        "coverage": False,
        "fixture": "Two friendly single-model units; one enemy; no terrain; One Shot bolter.",
        "seeds": ["order91-empty-shooting"],
        "policy": "Engine-enumerated options and validated proposals through LocalGameSession",
        "timing_boundary": "Declaration through executor completion; setup and restore separate",
        "hashes": {
            name: hashlib.sha256(Path(name).read_bytes()).hexdigest()
            for name in (
                "scripts/benchmark_order95_shooting.py",
                "tests/empty_shooting_helpers.py",
                "tests/optional_shooting_helpers.py",
                "tests/psychic_modifier_helpers.py",
                "uv.lock",
            )
        },
        "rows": rows,
        "completion_rate": 1.0,
        "full_game_samples": 0,
        "full_game_certified": False,
        "timing_budget": "Diagnostic; component timing gates remain deferred by Order 32",
    }


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--new-paths", action="store_true")
    args = parser.parse_args()
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(measure(new_paths=args.new_paths), indent=2) + "\n")
