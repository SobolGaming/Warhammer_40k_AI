"""Matched Charge declaration, target selection and path submission costs."""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import os
import platform
import statistics
import subprocess
import time
from pathlib import Path
from typing import cast

from tests.phase15a_charge_declaration_helpers import charge_lifecycle, compact_test_unit_poses

from warhammer40k_core.adapters.local_session import LocalGameSession
from warhammer40k_core.build_identity import current_engine_build_id
from warhammer40k_core.core.ruleset_descriptor import MovementMode
from warhammer40k_core.engine.event_log import JsonValue
from warhammer40k_core.engine.movement_proposals import ProposalKind
from warhammer40k_core.engine.phases.charge import ChargeMoveProposal
from warhammer40k_core.geometry.pathing import PathWitness
from warhammer40k_core.geometry.pose import Pose

ROOT = Path(__file__).resolve().parents[1]


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--samples", type=int, default=7)
    parser.add_argument("--include-charge-reroll-window", action="store_true")
    args = parser.parse_args()
    if args.samples < 1:
        parser.error("samples must be positive")
    rows = []
    for _ in range(args.samples):
        start = time.perf_counter()
        lifecycle, units = charge_lifecycle(
            alpha_unit_ids=("source", "next"),
            game_id="order47-charge-benchmark-1",
            enemy_model_poses=compact_test_unit_poses(origin=Pose.at(10, 26), model_count=5),
        )
        session = LocalGameSession(lifecycle)
        state = lifecycle.state
        assert state is not None
        assert state.battlefield_state is not None
        unit_id = units["source"].unit_instance_id
        enemy_id = units["enemy"].unit_instance_id
        ready = time.perf_counter()
        request = session.advance_until_decision_or_terminal().decision_request
        assert request is not None
        status = session.submit_option(
            request_id=request.request_id, option_id=unit_id, result_id="benchmark-select"
        )
        request = status.decision_request
        assert request is not None
        if args.include_charge_reroll_window and request.decision_type == "use_stratagem":
            status = session.submit_option(
                request_id=request.request_id,
                option_id="decline_stratagem_window",
                result_id="benchmark-decline-reroll",
            )
            request = status.decision_request
            assert request is not None
        assert request.decision_type == "select_charge_targets"
        option = next(
            o
            for o in request.options
            if isinstance(o.payload, dict) and o.payload.get("target_ids") == [enemy_id]
        )
        status = session.submit_option(
            request_id=request.request_id,
            option_id=option.option_id,
            result_id="benchmark-targets",
        )
        request = status.decision_request
        assert request is not None
        selected = time.perf_counter()
        placement = state.battlefield_state.unit_placement_by_id(unit_id)
        paths = tuple(
            (
                m.model_instance_id,
                (
                    m.pose,
                    Pose.at(m.pose.position.x, m.pose.position.y + 2),
                    Pose.at(m.pose.position.x, m.pose.position.y + 4),
                ),
            )
            for m in placement.model_placements
        )
        proposal = ChargeMoveProposal(
            proposal_request_id=request.request_id,
            unit_instance_id=unit_id,
            proposal_kind=ProposalKind.CHARGE_MOVE,
            movement_phase_action="charge_move",
            movement_mode=MovementMode.CHARGE,
            charge_target_unit_instance_ids=(enemy_id,),
            witness=PathWitness.for_paths(paths),
        )
        status = session.submit_parameterized_payload(
            request_id=request.request_id,
            result_id="benchmark-move",
            payload=cast(JsonValue, proposal.to_payload()),
        )
        end = time.perf_counter()
        assert any(
            e.event_type == "charge_move_completed"
            for e in lifecycle.decision_controller.event_log.records
        ), status
        rows.append(
            {
                "setup_seconds": ready - start,
                "selection_seconds": selected - ready,
                "movement_seconds": end - selected,
                "slice_seconds": end - ready,
                "decision_count": len(lifecycle.decision_controller.records),
                "event_count": len(lifecycle.decision_controller.event_log.records),
            }
        )
    times = sorted(row["slice_seconds"] for row in rows)
    report = {
        "workload_id": (
            "order49-charge-reroll-slice-v1"
            if args.include_charge_reroll_window
            else "order47-charge-slice-v1"
        ),
        "revision": subprocess.check_output(["git", "rev-parse", "HEAD"], text=True).strip(),
        "engine_build_id": current_engine_build_id(),
        "runtime_diff_sha256": hashlib.sha256(
            subprocess.check_output(["git", "diff", "HEAD", "--", "src"])
        ).hexdigest(),
        "platform": platform.platform(),
        "python": platform.python_version(),
        "cpu_allocation": os.cpu_count(),
        "cpu": subprocess.check_output(
            ["sysctl", "-n", "machdep.cpu.brand_string"], text=True
        ).strip(),
        "memory_bytes": int(subprocess.check_output(["sysctl", "-n", "hw.memsize"], text=True)),
        "model_count": 15,
        "terrain_count": 0,
        "timing_boundary": (
            "Charge declaration through accepted path and next decision; setup separate"
        ),
        "scenario": {
            "game_id": "order47-charge-benchmark-1",
            "models_per_unit": 5,
            "charging_units": 2,
            "enemy_units": 1,
            "path_segments": 2,
            "concurrency": 1,
        },
        "mode": "uninstrumented_timing",
        "concurrency": 1,
        "hashes": {
            name: hashlib.sha256((ROOT / name).read_bytes()).hexdigest()
            for name in (
                "uv.lock",
                "tests/phase15a_charge_declaration_helpers.py",
                "scripts/measure_charge_endpoints.py",
            )
        },
        "samples": rows,
        "mean_seconds": statistics.mean(times),
        "median_seconds": statistics.median(times),
        "p95_seconds": times[math.ceil(len(times) * 0.95) - 1],
        "maximum_seconds": max(times),
        "completion_rate": 1,
        "full_game_certified": False,
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, indent=2) + "\n")


if __name__ == "__main__":
    main()
