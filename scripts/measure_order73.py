"""Matched floor/shape/attached Emergency Disembark facade diagnostics.

Includes unresolved base cases; never treats an error as a placement verdict.
"""

from __future__ import annotations

import argparse
import hashlib
import importlib
import json
import os
import platform
import statistics
import sys
import time
from pathlib import Path

from measure_order60 import ROOT, _host_inventory, _select_runtime_src


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--runtime-src", type=Path, required=True)
    parser.add_argument("--revision", required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    _select_runtime_src(args.runtime_src)
    helpers = importlib.import_module("tests.emergency_geometry_helpers")
    phase = importlib.import_module("warhammer40k_core.engine.phase")
    pose = importlib.import_module("warhammer40k_core.geometry.pose")
    event_log = importlib.import_module("warhammer40k_core.engine.event_log")
    samples = []
    for rectangular in (False, True):
        for attached in (False, True):
            for repeat in range(3):
                start = time.perf_counter()
                session, proposal = helpers.emergency_geometry_session(
                    attached=attached, rectangular=rectangular
                )
                preparation = time.perf_counter() - start
                request = session.lifecycle.pending_decision_request()
                assert request is not None
                sample: dict[str, object] = {
                    "rectangular": rectangular,
                    "attached": attached,
                    "repeat": repeat,
                    "preparation_seconds": preparation,
                }
                start = time.perf_counter()
                try:
                    result = session.submit_parameterized_payload(
                        request_id=request.request_id,
                        result_id="timed-placement",
                        payload=event_log.validate_json_value(proposal.to_payload()),
                    )
                except (phase.GameLifecycleError, pose.GeometryError) as exc:
                    sample.update(complete=False, valid=None, error=str(exc))
                else:
                    sample.update(
                        complete=True,
                        valid=result.status_kind is not phase.LifecycleStatusKind.INVALID,
                        error=None,
                    )
                sample["seconds"] = time.perf_counter() - start
                samples.append(sample)
    cpu, memory = _host_inventory()
    times = [float(row["seconds"]) for row in samples]
    complete = sum(row["complete"] is True for row in samples)
    payload = {
        "workload_id": "order73-emergency-geometry-facade-v1",
        "revision": args.revision,
        "platform": platform.platform(),
        "python": platform.python_version(),
        "cpu": cpu,
        "cpu_allocation": os.cpu_count(),
        "memory_bytes": memory,
        "concurrency": 1,
        "host_role": "provisional",
        "timing_boundary": (
            "one actual pending Emergency Disembark facade submission; five or six survivors; "
            "circular or rectangular Transport; one elevated floor; "
            "fixture/attack preparation excluded"
        ),
        "samples": samples,
        "completion_rate": complete / len(samples),
        "mean_attempt_seconds": statistics.mean(times),
        "maximum_attempt_seconds": max(times),
        "full_game_certified": False,
        "hashes": {
            path: hashlib.sha256((ROOT / path).read_bytes()).hexdigest()
            for path in (
                "uv.lock",
                "scripts/measure_order73.py",
                "tests/emergency_geometry_helpers.py",
            )
        },
        "budget": {"head_maximum_submission_seconds": 12, "required_head_completion_rate": 1},
        "certification": (
            "bounded facade workload only; base unresolved outcomes are failures, "
            "not rules answers; complete games unmeasured"
        ),
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    if complete and any(row["complete"] and not row["valid"] for row in samples):
        sys.exit("Completed invalid placement in the declared legal workload")


if __name__ == "__main__":
    main()
