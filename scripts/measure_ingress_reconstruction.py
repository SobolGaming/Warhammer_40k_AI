"""Measure authenticated post-ingress restore and session fork independently.

Preparation and correctness assertions are outside the timing boundary. Work
counts use a separate profiled sample; timings never run under the profiler.
"""

from __future__ import annotations

import argparse
import copy
import cProfile
import hashlib
import json
import math
import os
import platform
import statistics
import time
from pathlib import Path
from types import CodeType
from typing import TYPE_CHECKING, Literal

from scripts.measure_order63 import _host_inventory, _select_runtime_src

if TYPE_CHECKING:
    from warhammer40k_core.adapters.local_session import LocalGameSession

ROOT = Path(__file__).resolve().parents[1]
WORKLOAD_ID = "loaded-ingress-reconstruction-v1"
CHECKPOINTS = ("ingress", "rapid_disembark", "later_decision")
OPERATIONS: tuple[Literal["restore", "fork"], ...] = ("restore", "fork")


def prepare(checkpoint: str) -> LocalGameSession:
    from tests.order63_reserve_transport_helpers import (
        rapid_disembark,
        reserve_transport_session,
        submit_ingress,
    )
    from tests.psychic_modifier_helpers import pending_request

    from warhammer40k_core.engine.phase import LifecycleStatusKind

    if checkpoint not in CHECKPOINTS:
        raise ValueError(f"Unknown reconstruction checkpoint: {checkpoint}")
    session = reserve_transport_session()
    submit_ingress(session)
    if checkpoint != "ingress":
        result = rapid_disembark(session, y=5)
        assert result.status_kind is not LifecycleStatusKind.INVALID, result
    if checkpoint == "later_decision":
        request = pending_request(session)
        result = session.submit_option(
            request_id=request.request_id,
            result_id="reconstruction:later-selection",
            option_id="army-alpha:remaining-unit",
        )
        assert result.status_kind is not LifecycleStatusKind.INVALID, result
    return session


def sample(
    session: LocalGameSession,
    operation: Literal["restore", "fork"],
    *,
    profile: bool = False,
) -> dict[str, object]:
    from warhammer40k_core.engine.lifecycle import GameLifecycle

    saved = session.lifecycle.to_payload()
    isolated = copy.deepcopy(saved)
    profiler = cProfile.Profile()
    if profile:
        profiler.enable()
    started = time.perf_counter()
    if operation == "restore":
        restored = GameLifecycle.from_payload(isolated)
    elif operation == "fork":
        restored = session.fork().lifecycle
    else:
        raise ValueError(f"Unknown reconstruction operation: {operation}")
    elapsed = time.perf_counter() - started
    if profile:
        profiler.disable()
    assert restored.to_payload() == saved
    assert session.lifecycle.to_payload() == saved
    assert restored is not session.lifecycle
    assert restored.state is not session.lifecycle.state
    counts: dict[str, int] = {}
    if profile:
        entries = profiler.getstats()
        counts["total_profiled_calls"] = sum(entry.callcount for entry in entries)
        for entry in entries:
            code = entry.code
            if not isinstance(code, CodeType):
                continue
            key = f"{Path(code.co_filename).name}:{code.co_name}"
            if key in {
                "replay.py:run",
                "lifecycle.py:from_payload",
                "lifecycle.py:submit_decision",
                "reserve_arrival_resolution.py:resolve_reserve_arrival",
                "ingress_placement_history.py:validate_ingress_history_origin",
            }:
                counts[key] = counts.get(key, 0) + entry.callcount
    return {"seconds": elapsed, "complete": True, "work_counts": counts}


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--revision", required=True)
    parser.add_argument("--runtime-src", type=Path, default=ROOT / "src")
    parser.add_argument("--samples", type=int, default=7)
    args = parser.parse_args()
    if args.samples < 3:
        parser.error("At least three samples are required.")
    _select_runtime_src(args.runtime_src)
    from warhammer40k_core.build_identity import verified_engine_build_identity

    runtime_identity = verified_engine_build_identity().build_id
    rows = []
    for checkpoint in CHECKPOINTS:
        prepared_at = time.perf_counter()
        session = prepare(checkpoint)
        preparation_seconds = time.perf_counter() - prepared_at
        state = session.lifecycle.state
        assert state is not None
        payload = session.lifecycle.to_payload()
        for operation in OPERATIONS:
            samples = [sample(session, operation) for _ in range(args.samples)]
            times = [float(str(row["seconds"])) for row in samples]
            rows.append(
                {
                    "checkpoint": checkpoint,
                    "operation": operation,
                    "game_id": state.game_id,
                    "unit_count": sum(len(army.units) for army in state.army_definitions),
                    "model_count": sum(
                        len(unit.own_models)
                        for army in state.army_definitions
                        for unit in army.units
                    ),
                    "preparation_seconds": preparation_seconds,
                    "payload_bytes": len(json.dumps(payload, sort_keys=True).encode()),
                    "decision_records": len(payload["decisions"]["records"]),
                    "event_records": len(payload["decisions"]["event_log"]),
                    "samples": samples,
                    "mean_seconds": statistics.mean(times),
                    "median_seconds": statistics.median(times),
                    "p95_seconds": sorted(times)[math.ceil(0.95 * len(times)) - 1],
                    "maximum_seconds": max(times),
                    "operations_per_second": 1 / statistics.mean(times),
                    "completion_rate": 1,
                    "profile": sample(session, operation, profile=True),
                }
            )
            print(
                json.dumps(
                    {
                        "checkpoint": checkpoint,
                        "operation": operation,
                        "mean_seconds": statistics.mean(times),
                        "maximum_seconds": max(times),
                    }
                ),
                flush=True,
            )
    cpu, memory = _host_inventory()
    report = {
        "workload_id": WORKLOAD_ID,
        "revision": args.revision,
        "runtime_build_id": runtime_identity,
        "platform": platform.platform(),
        "python": platform.python_version(),
        "cpu": cpu,
        "cpu_allocation": os.cpu_count(),
        "memory_bytes": memory,
        "host_role": "provisional",
        "concurrency": 1,
        "scenario": "Order 63 canonical loaded Transport; empty terrain; no dice",
        "timing_boundary": (
            "restore: from_payload only; fork: LocalGameSession.fork including serialize/deepcopy; "
            "fixture, ingress, Disembark, input copy and equality assertions excluded; "
            f"{args.samples} repeated independent reconstructions from each fixed checkpoint"
        ),
        "input_hash_algorithm": "sha256-normalized-text-lf",
        "hashes": {
            name: hashlib.sha256(
                (ROOT / name).read_bytes().replace(b"\r\n", b"\n").replace(b"\r", b"\n")
            ).hexdigest()
            for name in (
                "uv.lock",
                "scripts/measure_ingress_reconstruction.py",
                "scripts/measure_order63.py",
                "tests/order63_reserve_transport_helpers.py",
                "tests/disembark_eligibility_helpers.py",
            )
        },
        "rows": rows,
        "full_game_certified": False,
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")


if __name__ == "__main__":
    main()
