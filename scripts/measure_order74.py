"""Matched cold-cache mandatory endpoint Charge facade diagnostics."""

from __future__ import annotations

import argparse
import hashlib
import importlib
import json
import platform
import statistics
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
    helpers = importlib.import_module("tests.mandatory_endpoint_helpers")
    geometry = importlib.import_module("warhammer40k_core.geometry.movement_reachability")
    phase = importlib.import_module("warhammer40k_core.engine.phase")
    samples = []
    for repeat in range(3):
        session = helpers.blocked_charge_session()
        session.advance_until_decision_or_terminal()
        request = helpers.blocked_charge_request(session)
        payload = helpers.blocked_charge_payload(session, request)
        geometry.clear_movement_reachability_cache()
        start = time.perf_counter()
        result = session.submit_parameterized_payload(
            request_id=request.request_id, result_id="measured-charge", payload=payload
        )
        samples.append(
            {
                "repeat": repeat,
                "seconds": time.perf_counter() - start,
                "valid": result.status_kind is not phase.LifecycleStatusKind.INVALID,
                "status": result.status_kind.value,
            }
        )
    cpu, memory = _host_inventory()
    times = [row["seconds"] for row in samples]
    report = {
        "workload_id": "order74-mandatory-endpoint-facade-v1",
        "revision": args.revision,
        "platform": platform.platform(),
        "python": platform.python_version(),
        "cpu": cpu,
        "memory_bytes": memory,
        "concurrency": 1,
        "host_role": "provisional",
        "timing_boundary": (
            "cold-cache Charge facade submission; five models; one wall; fixture excluded"
        ),
        "samples": samples,
        "mean_seconds": statistics.mean(times),
        "maximum_seconds": max(times),
        "full_game_certified": False,
        "hashes": {
            path: hashlib.sha256((ROOT / path).read_bytes().replace(b"\r\n", b"\n")).hexdigest()
            for path in (
                "uv.lock",
                "scripts/measure_order74.py",
                "tests/mandatory_endpoint_helpers.py",
            )
        },
        "budget": {"maximum_head_seconds": 12, "required_head_acceptance_rate": 1},
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")


if __name__ == "__main__":
    main()
