"""Current exact-base canonical receipt operations; historical driver stays intact."""

from __future__ import annotations

import argparse
import json
import os
import platform
import time
from pathlib import Path

from scripts.measure_order63 import _host_inventory, _select_runtime_src

WORKLOAD_ID = "numerical-identity-canonical-preflight-v2"


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--runtime-src", type=Path, required=True)
    parser.add_argument("--revision", required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    _select_runtime_src(args.runtime_src)
    from warhammer40k_core.ai.canonical_deployment import reproduce_canonical_deployment
    from warhammer40k_core.ai.canonical_deployment_coverage import CanonicalDeploymentCoverage
    from warhammer40k_core.ai.training_admission import TrainingAdmissionError
    from warhammer40k_core.build_identity import verified_engine_build_identity
    from warhammer40k_core.engine.event_log import canonical_json

    session, _ = reproduce_canonical_deployment()
    report = CanonicalDeploymentCoverage.measure(session=session)
    payload = report.to_payload()
    assert payload["totals"]["finite"]["accepted_count"] == 18
    assert payload["totals"]["placement"]["accepted_count"] == 46
    assert payload["totals"]["placement"]["legal_reference_count"] == 32
    assert payload["totals"]["placement"]["invalid_reference_probe_count"] == 8
    checkpoint = canonical_json(session.to_persistence_payload())
    original = CanonicalDeploymentCoverage.measure
    calls = []

    def delegated(cls, *, session):
        assert cls is CanonicalDeploymentCoverage
        calls.append(1)
        return original(session=session)

    CanonicalDeploymentCoverage.measure = classmethod(delegated)
    rows = []
    started = time.perf_counter()
    loaded = CanonicalDeploymentCoverage.from_payload(
        json.loads(canonical_json(payload)), session=session
    )
    elapsed = time.perf_counter() - started
    assert loaded.content_hash == report.content_hash
    assert len(calls) == 1
    rows.append(
        {
            "case": "valid_reload",
            "samples_seconds": [elapsed],
            "complete": True,
            "accepted": True,
            "fresh_measure_calls": len(calls),
        }
    )
    calls.clear()
    invalid = json.loads(canonical_json(payload))
    invalid["totals"]["placement"]["legal_reference_count"] += 1
    started = time.perf_counter()
    reason = None
    try:
        CanonicalDeploymentCoverage.from_payload(invalid, session=session)
    except TrainingAdmissionError as exc:
        reason = str(exc)
    elapsed = time.perf_counter() - started
    assert reason is not None
    assert "payload drifted" in reason
    assert not calls
    rows.append(
        {
            "case": "inconsistent_totals_rejection",
            "samples_seconds": [elapsed],
            "complete": True,
            "accepted": False,
            "fresh_measure_calls": len(calls),
        }
    )
    assert canonical_json(session.to_persistence_payload()) == checkpoint
    cpu, memory = _host_inventory()
    result = {
        "workload_id": WORKLOAD_ID,
        "revision": args.revision,
        "runtime_build_id": verified_engine_build_identity().build_id,
        "cpu": cpu,
        "memory_bytes": memory,
        "cpu_allocation": os.cpu_count(),
        "platform": platform.platform(),
        "python": platform.python_version(),
        "concurrency": 1,
        "coverage": False,
        "completed": True,
        "rows": rows,
        "full_game_certified": False,
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")


if __name__ == "__main__":
    main()
