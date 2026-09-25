"""Matched Order 85 Charge facade counterexample and component diagnostics."""

from __future__ import annotations

import argparse
import hashlib
import importlib
import json
import platform
import statistics
from dataclasses import replace
from pathlib import Path
from time import perf_counter
from typing import cast

from scripts.measure_order65 import _host_inventory, _select_runtime_src


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--runtime-src", type=Path, default=Path("src"))
    parser.add_argument("--revision", required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    _select_runtime_src(args.runtime_src)
    from tests.order85_overhang_helpers import overhang_charge_session

    from warhammer40k_core.engine.event_log import JsonValue
    from warhammer40k_core.geometry.pathing import PathWitness
    from warhammer40k_core.geometry.pose import Pose

    rows = []
    for case in ("body-touch", "body-penetration"):
        samples: list[float] = []
        setup_samples: list[float] = []
        statuses: list[str] = []
        for index in range(3):
            start = perf_counter()
            session, proposal = overhang_charge_session()
            if case == "body-penetration":
                assert proposal.witness is not None
                mid = proposal.witness.model_ids()[0]
                origin = proposal.witness.poses_for_model(mid)[0]
                proposal = replace(
                    proposal, witness=PathWitness.for_paths(((mid, (origin, Pose.at(10, 10.35))),))
                )
            setup_samples.append(perf_counter() - start)
            start = perf_counter()
            result = session.submit_parameterized_payload(
                request_id=proposal.proposal_request_id,
                result_id=f"benchmark-{index}",
                payload=cast(JsonValue, proposal.to_payload()),
            )
            samples.append(perf_counter() - start)
            statuses.append(result.status_kind.value)
        rows.append(
            {
                "case": case,
                "samples_seconds": samples,
                "setup_seconds": setup_samples,
                "mean_seconds": statistics.mean(samples),
                "maximum_seconds": max(samples),
                "median_seconds": statistics.median(samples),
                "p95_seconds_nearest_rank": max(samples),
                "submissions_per_second": len(samples) / sum(samples),
                "statuses": statuses,
            }
        )
    cpu, memory = _host_inventory()
    report = {
        "workload": "order85-witnessed-contact-v1",
        "revision": args.revision,
        "runtime_build_id": importlib.import_module(
            "warhammer40k_core.build_identity"
        ).current_engine_build_id(),
        "cpu": cpu,
        "memory_bytes": memory,
        "platform": platform.platform(),
        "python": platform.python_version(),
        "host_role": "provisional",
        "concurrency": 1,
        "timing_boundary": (
            "Separate session/config/restore/Charge-choice preparation and "
            "facade path submission through next pending decision"
        ),
        "fixture": (
            "Canonical one-model character and one-model vehicle, reviewed solid 8-inch "
            "cylinder on 120mm base; 100x100 empty board; fixed fixture seed and +10 "
            "Charge roll modifier; same body-touch and penetrating paths"
        ),
        "hashes": {
            name: hashlib.sha256(Path(name).read_bytes()).hexdigest()
            for name in (
                "scripts/measure_order85.py",
                "tests/order85_overhang_helpers.py",
                "uv.lock",
            )
        },
        "rows": rows,
        "completion_rate": 1,
        "coverage": False,
        "full_game_certified": False,
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, indent=2) + "\n")


if __name__ == "__main__":
    main()
