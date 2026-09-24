"""Matched, serial projection microbenchmark; run with PYTHONPATH=.:src (no coverage)."""

# pyright: reportPrivateUsage=false
from __future__ import annotations

import argparse
import hashlib
import json
import platform
import statistics
from pathlib import Path
from time import perf_counter

from tests.order81_projection_helpers import revival_projection_session

from warhammer40k_core.adapters.access_control import ViewerContext
from warhammer40k_core.adapters.projection import _proposal_view, public_decision_request_view
from warhammer40k_core.engine.decision_request import DecisionRequest, parameterized_decision_option
from warhammer40k_core.engine.phase import GameLifecycleError

ROOT = Path(__file__).resolve().parents[1]
WORKLOAD = "order81-shared-parameterized-projection-v1"


def measure() -> dict[str, object]:
    session, _ = revival_projection_session()
    flat = session.lifecycle.pending_decision_request()
    assert flat is not None
    # Presentation-only nested context; no synthetic gameplay or submission is executed.
    nested = DecisionRequest(
        request_id="benchmark-movement",
        decision_type="submit_movement_proposal",
        actor_id="player-a",
        payload={
            "proposal_request": {
                "proposal_kind": "normal_move",
                "unit_instance_id": "army-alpha:recipient",
                "model_instance_ids": [f"model-{i}" for i in range(5)],
                "maximum_distance_inches": 6,
            }
        },
        options=(parameterized_decision_option(),),
    )
    viewer = ViewerContext.for_player("player-a")
    rows: list[dict[str, object]] = []
    for name, request in (("nested_request", nested), ("flat_request", flat)):
        samples: list[float] = []
        for _sample in range(9):
            started = perf_counter()
            for _iteration in range(2000):
                public_decision_request_view(request, viewer=viewer)
            samples.append((perf_counter() - started) / 2000)
        rows.append(
            {
                "case": name,
                "iterations_per_sample": 2000,
                "samples_seconds": samples,
                "mean_seconds": statistics.mean(samples),
                "median_seconds": statistics.median(samples),
                "maximum_seconds": max(samples),
            }
        )
    projections: dict[str, object] = {}
    for name, request in (("nested_request", nested), ("flat_request", flat)):
        try:
            result = _proposal_view(request, viewer=viewer)
        except GameLifecycleError as exc:
            projections[name] = {"status": "projection_error", "message": str(exc)}
        else:
            projections[name] = {
                "status": "projected",
                "payload_sha256": hashlib.sha256(
                    json.dumps(result, sort_keys=True).encode()
                ).hexdigest(),
            }
    return {
        "workload": WORKLOAD,
        "python": platform.python_version(),
        "platform": platform.platform(),
        "cpu": "Apple M5 Pro",
        "logical_cpus": 18,
        "memory_bytes": 68719476736,
        "hardware_status": "provisional",
        "workers": 1,
        "coverage": False,
        "scope": "Request projection only; setup excluded. No full-game timing claim.",
        "fixture": "5-model recipient/enemy; one destroyed recipient; no terrain or random draws.",
        "script_sha256": hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
        "fixture_sha256": hashlib.sha256(
            (ROOT / "tests/order81_projection_helpers.py").read_bytes()
        ).hexdigest(),
        "lock_sha256": hashlib.sha256((ROOT / "uv.lock").read_bytes()).hexdigest(),
        "rows": rows,
        "proposal_projections": projections,
    }


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    args.output.write_text(json.dumps(measure(), indent=2) + "\n")
