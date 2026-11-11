"""Measure two canonical receipt-loader operations against explicitly selected source.

Usage: python measure_canonical_coverage_preflight.py ROOT OUTPUT ARM REVISION

Run base and head serially with identical current tests/scripts and dependency lock.
Outputs stay outside either checkout. One sample is descriptive, not tail or hosted
qualification. The baseline source remains the exact PR base; the overlay supplies
only the common workload and fixtures, never replacement engine behavior.
"""

from __future__ import annotations

import hashlib
import json
import os
import platform
import subprocess
import sys
import time
from datetime import UTC, datetime
from pathlib import Path


def main() -> None:
    root = Path(sys.argv[1]).resolve()
    output = Path(sys.argv[2]).resolve()
    arm = sys.argv[3]
    assert arm in ("base", "head")
    assert not output.is_relative_to(root), "Measurement output must be outside the checkout."
    output.mkdir(parents=True, exist_ok=True)
    assert not (output / "result.json").exists()
    os.chdir(root)
    sys.path.insert(0, str(root))
    sys.path.insert(0, str(root / "src"))
    started = time.perf_counter()

    def digest(data):
        return hashlib.sha256(data).hexdigest()

    def journal(event, **data):
        value = {
            "event": event,
            "utc": datetime.now(UTC).isoformat(),
            "elapsed_seconds": time.perf_counter() - started,
            **data,
        }
        with (output / "attempts.jsonl").open("a") as f:
            f.write(json.dumps(value, sort_keys=True) + "\n")
        print(json.dumps(value, sort_keys=True), flush=True)

    def input_hashes():
        return {
            str(p.relative_to(root)): digest(p.read_bytes())
            for p in sorted((root / "src").rglob("*"))
            if p.is_file() and p.suffix in (".py", ".json")
        }

    head = subprocess.check_output(["git", "rev-parse", "HEAD"], text=True).strip()
    assert head == sys.argv[4]
    if arm == "base":
        assert head == "efb3172c4ce1b3a912c3f6fc2c26ebaa465ad9c4"
        subprocess.run(
            ["git", "diff", "--exit-code", head, "--", "src"], check=True, capture_output=True
        )
    from tools.performance_policy import canonical_digest, runtime_inputs

    measured_inputs = runtime_inputs(root)
    fixture_inputs = {
        name: value
        for name, value in measured_inputs.items()
        if name.startswith(("tests/", "scripts/")) and not name.startswith("tests/code_quality/")
    }
    inputs = input_hashes()
    manifest = json.loads((root / "src/warhammer40k_core/_engine_build_manifest.json").read_text())
    identity = {
        "arm": arm,
        "root": str(root),
        "repository_head": head,
        "source_inputs": inputs,
        "source_inputs_sha256": digest(
            json.dumps(inputs, sort_keys=True, separators=(",", ":")).encode()
        ),
        "uv_lock_sha256": digest((root / "uv.lock").read_bytes()),
        "runtime_build_id": manifest["build_id"],
        "runtime_fingerprint": manifest["fingerprint"],
        "workload_sha256": digest(Path(__file__).read_bytes()),
        "python": sys.version,
        "executable": sys.executable,
        "platform": platform.platform(),
        "cpu_count": os.cpu_count(),
        "host": platform.node(),
        "cpu_model": next(
            line.split(":", 1)[1].strip()
            for line in Path("/proc/cpuinfo").read_text().splitlines()
            if line.startswith("model name")
        ),
        "affinity": sorted(os.sched_getaffinity(0)),
        "cpuinfo_sha256": digest(Path("/proc/cpuinfo").read_bytes()),
        "pid": os.getpid(),
        "sample": 1,
        "sample_count": 1,
        "coverage": False,
        "profiled": False,
    }
    identity["measurement_inputs"] = measured_inputs
    identity["measurement_input_digest"] = canonical_digest(measured_inputs)
    identity["fixture_inputs"] = fixture_inputs
    identity["fixture_sha256"] = canonical_digest(fixture_inputs)
    identity["host_record"] = {
        "cpu": identity["cpu_model"],
        "memory_bytes": int(
            next(
                line.split()[1]
                for line in Path("/proc/meminfo").read_text().splitlines()
                if line.startswith("MemTotal:")
            )
        )
        * 1024,
        "logical_cpus": os.cpu_count(),
        "platform": platform.platform(),
        "python": platform.python_version(),
        "role": "provisional",
    }
    identity["workload_overlay"] = (
        "Identical current tests/scripts, including this driver, supplied to both arms; "
        "base src remains exact efb3172c; head src is bound by full input hashes."
    )
    (output / "identity.json").write_text(json.dumps(identity, indent=2, sort_keys=True) + "\n")
    journal("start", arm=arm, pid=os.getpid(), head=head)
    from warhammer40k_core.ai import canonical_deployment_coverage as owner
    from warhammer40k_core.ai.canonical_deployment import (
        canonical_deployment_config,
        reproduce_canonical_deployment,
    )
    from warhammer40k_core.ai.training_admission import TrainingAdmissionError
    from warhammer40k_core.engine.event_log import canonical_json

    assert (
        Path(owner.__file__).resolve()
        == root / "src/warhammer40k_core/ai/canonical_deployment_coverage.py"
    )
    for name, module in tuple(sys.modules.items()):
        if name.startswith("warhammer40k_core") and getattr(module, "__file__", None):
            assert Path(module.__file__).resolve().is_relative_to(root / "src"), (
                name,
                module.__file__,
            )
    identity["configuration"] = canonical_deployment_config().to_payload()
    identity["configuration_sha256"] = digest(canonical_json(identity["configuration"]).encode())
    (output / "identity.json").write_text(json.dumps(identity, indent=2, sort_keys=True) + "\n")
    journal("preparation_start")
    prep = time.perf_counter()
    prep_cpu = time.process_time()
    session, _ = reproduce_canonical_deployment()
    report = owner.CanonicalDeploymentCoverage.measure(session=session)
    payload = report.to_payload()
    preparation = {
        "wall_seconds": time.perf_counter() - prep,
        "cpu_seconds": time.process_time() - prep_cpu,
    }
    assert payload["totals"]["finite"]["accepted_count"] == 18
    assert payload["totals"]["placement"]["accepted_count"] == 46
    assert payload["totals"]["placement"]["legal_reference_count"] == 32
    assert payload["totals"]["placement"]["invalid_reference_probe_count"] == 8
    semantics = {
        "totals": payload["totals"],
        "rows": [
            {"index": r["index"], "kind": r["kind"], "route": r["route"], "counts": r["counts"]}
            for r in payload["rows"]
        ],
    }
    checkpoint = canonical_json(session.to_persistence_payload())
    journal("preparation_finish", **preparation)
    original = owner.CanonicalDeploymentCoverage.measure
    measure_calls = []

    def delegated(cls, *, session):
        assert cls is owner.CanonicalDeploymentCoverage
        measure_calls.append(1)
        return original(session=session)

    owner.CanonicalDeploymentCoverage.measure = classmethod(delegated)
    operations = []
    valid = json.loads(canonical_json(payload))
    journal("operation_start", operation="valid_reload")
    wall = time.perf_counter()
    cpu = time.process_time()
    loaded = owner.CanonicalDeploymentCoverage.from_payload(valid, session=session)
    valid_times = {
        "operation": "valid_reload",
        "wall_seconds": time.perf_counter() - wall,
        "cpu_seconds": time.process_time() - cpu,
        "fresh_measure_calls": len(measure_calls),
        "outcome": "accepted",
    }
    assert len(measure_calls) == 1
    assert loaded.content_hash == report.content_hash
    assert canonical_json(session.to_persistence_payload()) == checkpoint
    operations.append(valid_times)
    journal("operation_finish", **valid_times)
    invalid = json.loads(canonical_json(payload))
    invalid["totals"]["placement"]["legal_reference_count"] += 1
    measure_calls.clear()
    journal("operation_start", operation="inconsistent_totals_rejection")
    wall = time.perf_counter()
    cpu = time.process_time()
    reason = None
    try:
        owner.CanonicalDeploymentCoverage.from_payload(invalid, session=session)
    except TrainingAdmissionError as exc:
        reason = str(exc)
    invalid_times = {
        "operation": "inconsistent_totals_rejection",
        "wall_seconds": time.perf_counter() - wall,
        "cpu_seconds": time.process_time() - cpu,
        "fresh_measure_calls": len(measure_calls),
        "outcome": "rejected",
        "diagnostic": reason,
    }
    assert reason is not None
    assert "payload drifted" in reason
    assert len(measure_calls) == (1 if arm == "base" else 0)
    assert canonical_json(session.to_persistence_payload()) == checkpoint
    operations.append(invalid_times)
    journal("operation_finish", **invalid_times)
    assert input_hashes() == inputs
    assert runtime_inputs(root) == measured_inputs
    result = {
        "schema": "canonical-coverage-preflight-operation-sample-v1",
        "identity": identity,
        "preparation": preparation,
        "operations": operations,
        "semantics": semantics,
        "semantics_sha256": digest(canonical_json(semantics).encode()),
        "checkpoint_unchanged": True,
        "fresh_valid_reproduction": True,
        "elapsed_seconds": time.perf_counter() - started,
        "limitations": [
            "one sample per arm; no variance/tail qualification",
            "serial without coverage on one WSL host; no hosted approval claim",
            "operation timers exclude shared preparation and post-operation assertions",
            "measure wrapper records and delegates the real implementation; "
            "no engine behavior replacement",
        ],
    }
    (output / "result.json").write_text(json.dumps(result, indent=2, sort_keys=True) + "\n")
    journal("finish", outcome="passed", elapsed_seconds=result["elapsed_seconds"])


if __name__ == "__main__":
    main()
