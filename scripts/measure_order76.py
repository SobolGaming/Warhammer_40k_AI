"""Matched valid and malformed physical-proposal facade submission timings."""

from __future__ import annotations

import argparse
import hashlib
import importlib
import importlib.metadata
import json
import math
import os
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
    helpers = importlib.import_module("tests.physical_proposal_prevalidation_helpers")
    build = importlib.import_module("warhammer40k_core.build_identity")
    samples = []
    for family in helpers.FAMILIES:
        for malformed in (False, True):
            for repeat in range(3):
                prepared = time.perf_counter()
                session, request, payload = helpers.proposal_session(family)
                if malformed:
                    payload = {**payload, "proposal_kind": "not-a-kind"}
                preparation_seconds = time.perf_counter() - prepared
                events_before = len(session.lifecycle.decision_controller.event_log.records)
                started = time.perf_counter()
                status = session.submit_parameterized_payload(
                    request_id=request.request_id, result_id="measured-proposal", payload=payload
                )
                seconds = time.perf_counter() - started
                samples.append(
                    {
                        "family": family,
                        "malformed": malformed,
                        "repeat": repeat,
                        "preparation_seconds": preparation_seconds,
                        "seconds": seconds,
                        "status": status.status_kind.value,
                        "event_delta": len(session.lifecycle.decision_controller.event_log.records)
                        - events_before,
                    }
                )
    cpu, memory = _host_inventory()
    report = {
        "workload_id": "order76-physical-proposal-prevalidation-v1",
        "revision": args.revision,
        "runtime_build_id": build.current_engine_build_id(),
        "platform": platform.platform(),
        "python": platform.python_version(),
        "cpu": cpu,
        "memory_bytes": memory,
        "cpu_allocation": os.cpu_count(),
        "concurrency": 1,
        "host_role": "provisional",
        "library_versions": {
            name: importlib.metadata.version(name) for name in ("shapely", "z3-solver", "orjson")
        },
        "timing_boundary": (
            "one facade submission, preparation separate; first sample cold, "
            "subsequent process caches retained"
        ),
        "workload": (
            "Canonical five-model Movement/Fight, attached six-model Charge/Surge, "
            "loaded reserve Transport; fixed finite choices, typed proposal or invalid-kind "
            "token; fixture seeds and terrain retained by hash."
        ),
        "samples": samples,
        "summary": {
            label: {
                "count": len(times),
                "mean_seconds": statistics.mean(times),
                "median_seconds": statistics.median(times),
                "p95_seconds": sorted(times)[math.ceil(0.95 * len(times)) - 1],
                "maximum_seconds": max(times),
                "submissions_per_second": 1 / statistics.mean(times),
                "completion_rate": 1,
            }
            for label, times in (
                ("valid", [row["seconds"] for row in samples if not row["malformed"]]),
                ("malformed", [row["seconds"] for row in samples if row["malformed"]]),
            )
        },
        "completed_submissions": len(samples),
        "full_game_certified": False,
        "hashes": {
            name: hashlib.sha256((ROOT / name).read_bytes()).hexdigest()
            for name in (
                "uv.lock",
                "scripts/measure_order76.py",
                "tests/physical_proposal_prevalidation_helpers.py",
                "tests/surge_fixed_target_helpers.py",
                "tests/charge_endpoint_helpers.py",
                "tests/order63_reserve_transport_helpers.py",
                "tests/phase15c_fight_order_helpers.py",
            )
        },
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")


if __name__ == "__main__":
    main()
