"""Matched diagnostic timings for restoring a source-backed flying Charge exemption."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import platform
import statistics
import subprocess
import time
from pathlib import Path

from tests.charge_distance_helpers import select_targets
from tests.charge_endpoint_helpers import (
    ATTACHED_TARGET,
    attached_move_payload,
    flying_attached_charge_exemption_session,
    select_attached_source,
)

from warhammer40k_core.build_identity import current_engine_build_id
from warhammer40k_core.engine.lifecycle import GameLifecycle
from warhammer40k_core.engine.phase import LifecycleStatusKind

ROOT = Path(__file__).resolve().parents[1]


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args()
    session, bundle = flying_attached_charge_exemption_session()
    request = select_targets(session, select_attached_source(session), (ATTACHED_TARGET,))
    status = session.submit_parameterized_payload(
        request_id=request.request_id,
        result_id="r47-001-benchmark-charge",
        payload=attached_move_payload(session, request),
    )
    assert status.status_kind is not LifecycleStatusKind.INVALID, status
    checkpoint = session.lifecycle.to_payload()
    assert (
        GameLifecycle.from_payload(checkpoint, runtime_content_bundle=bundle).to_payload()
        == checkpoint
    )
    samples: list[float] = []
    for _ in range(7):
        start = time.perf_counter()
        restored = GameLifecycle.from_payload(checkpoint, runtime_content_bundle=bundle)
        samples.append(time.perf_counter() - start)
        assert restored.to_payload() == checkpoint
    report = {
        "workload_id": "r47-001-charge-endpoint-restore-v1",
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
        "concurrency": 1,
        "warmup_restores": 1,
        "model_count": 16,
        "terrain_count": 0,
        "checkpoint_sha256": hashlib.sha256(
            json.dumps(checkpoint, sort_keys=True).encode()
        ).hexdigest(),
        "hashes": {
            name: hashlib.sha256((ROOT / name).read_bytes()).hexdigest()
            for name in (
                "uv.lock",
                "tests/phase15a_charge_declaration_helpers.py",
                "tests/charge_endpoint_helpers.py",
                "scripts/measure_charge_endpoint_restore.py",
            )
        },
        "timing_boundary": (
            "GameLifecycle.from_payload; setup and payload equality assertion excluded"
        ),
        "scenario": (
            "Completed attached Charge with source-backed FLY, an elevated leader and an "
            "unreachable preferred-distance proof; before any casualty"
        ),
        "samples_seconds": samples,
        "mean_seconds": statistics.mean(samples),
        "median_seconds": statistics.median(samples),
        "p95_seconds": max(samples),
        "maximum_seconds": max(samples),
        "completion_rate": 1,
        "restores_per_second": 1 / statistics.mean(samples),
        "full_game_certified": False,
        "budget_status": "diagnostic_only_order32_component_gates_deferred",
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, indent=2) + "\n")


if __name__ == "__main__":
    main()
