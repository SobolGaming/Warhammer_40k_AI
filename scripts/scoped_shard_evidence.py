"""Explicit partial stress evidence; never supplies ordinary dispatch weights."""

from __future__ import annotations

import hashlib
import json
import math
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import cast

from scripts.hosted_timing_calibration import calibrated_seconds, read_json
from scripts.shard_execution_model import Cohort, _fixture_groups, _role_residuals

SCHEMA = "scoped-hosted-allocation-v1"
FILENAME = "allocation-scope.json"
EVIDENCE_FILE = "scoped-worker-evidence.json"
ROLE = (
    "Partial stress scenario; unknown frozen shard; not a complete cohort or dispatch calibration"
)


@dataclass(frozen=True)
class ScopedEvidence:
    cohort: Cohort
    frozen_shard: int
    frozen_selectors: tuple[str, ...]
    known_nodes: frozenset[str]
    frozen_nodes: frozenset[str]
    reference: dict[str, str]


def node_digest(nodes: set[str] | frozenset[str]) -> str:
    return hashlib.sha256(("\n".join(sorted(nodes)) + "\n").encode()).hexdigest()


def _mapping(value: object, fields: set[str], label: str) -> dict[str, object]:
    if not isinstance(value, dict) or value.keys() != fields:
        raise SystemExit("Invalid scoped allocation " + label + ".")
    return cast(dict[str, object], value)


def _nodes(value: object) -> frozenset[str]:
    if (
        not isinstance(value, list)
        or not value
        or any(not isinstance(node, str) or "::" not in node for node in value)
        or value != sorted(set(value))
    ):
        raise SystemExit("Invalid scoped allocation node inventory.")
    return frozenset(cast(list[str], value))


def validate_reference(directory: Path, value: object) -> dict[str, str]:
    reference = _mapping(value, {"file", "sha256"}, "reference")
    path = directory / FILENAME
    if (
        reference["file"] != FILENAME
        or not path.is_file()
        or hashlib.sha256(path.read_bytes()).hexdigest() != reference["sha256"]
    ):
        raise SystemExit("Scoped allocation evidence is missing or changed.")
    index = read_json(path)
    if not isinstance(index, dict):
        raise SystemExit("Invalid scoped allocation index.")
    evidence = _mapping(index.get("evidence"), {"file", "sha256"}, "worker reference")
    workers = directory / EVIDENCE_FILE
    if (
        evidence["file"] != EVIDENCE_FILE
        or not workers.is_file()
        or hashlib.sha256(workers.read_bytes()).hexdigest() != evidence["sha256"]
    ):
        raise SystemExit("Scoped allocation worker evidence is missing or changed.")
    return cast(dict[str, str], reference)


def _supervisor(value: object, *, failed: bool = False) -> dict[str, object]:
    entry = _mapping(value, {"artifact_id", "sha256", "payload"}, "supervisor")
    payload = entry["payload"]
    if not isinstance(payload, dict):
        raise SystemExit("Invalid scoped allocation supervisor payload.")
    raw = (json.dumps(payload, indent=2) + "\n").encode()
    if hashlib.sha256(raw).hexdigest() != entry["sha256"]:
        raise SystemExit("Scoped allocation supervisor bytes differ.")
    elapsed = payload.get("elapsed_seconds")
    if (
        type(entry["artifact_id"]) is not int
        or entry["artifact_id"] < 1
        or payload.get("schema") != "covered-shard-deadline-v1"
        or payload.get("approval_seconds") != 1080
        or payload.get("execution_seconds") != 1800
        or payload.get("terminated") is not False
        or payload.get("cleanup_error") is not None
        or payload.get("descendants_remained") is not False
        or isinstance(elapsed, bool)
        or not isinstance(elapsed, (int, float))
        or not math.isfinite(elapsed)
        or elapsed < 0
        or type(payload.get("workload_exit_code")) is not int
        or (payload["workload_exit_code"] == 0) is failed
        or (failed and (payload.get("reason") != "workload_failed" or payload.get("approved")))
    ):
        raise SystemExit("Scoped allocation supervisor outcome differs.")
    return {
        "artifact_id": entry["artifact_id"],
        "sha256": entry["sha256"],
        "elapsed_seconds": payload.get("elapsed_seconds"),
        "approved": payload.get("approved"),
        "reason": payload.get("reason"),
    }


def load_scope(
    directory: Path, *, root: Path, costs: dict[str, float], reference: object
) -> ScopedEvidence:
    binding = validate_reference(directory, reference)
    index = _mapping(
        read_json(directory / FILENAME),
        {
            "schema",
            "role",
            "source",
            "evidence",
            "known_nodes",
            "known_nodes_sha256",
            "frozen_nodes",
            "frozen_nodes_sha256",
            "frozen_shard",
            "frozen_selectors",
            "frozen_manifest_sha256",
            "excluded_supervisor",
            "supervisors",
            "artifacts",
        },
        "index",
    )
    known, frozen = _nodes(index["known_nodes"]), _nodes(index["frozen_nodes"])
    selectors = index["frozen_selectors"]
    if (
        index["schema"] != SCHEMA
        or index["role"] != ROLE
        or known & frozen
        or known | frozen != costs.keys()
        or node_digest(known) != index["known_nodes_sha256"]
        or node_digest(frozen) != index["frozen_nodes_sha256"]
        or type(index["frozen_shard"]) is not int
        or not 1 <= index["frozen_shard"] <= 12
        or not isinstance(selectors, list)
        or not selectors
        or any(not isinstance(selector, str) for selector in selectors)
        or selectors != sorted(set(selectors))
    ):
        raise SystemExit("Scoped allocation known/frozen inventory differs.")
    frozen_selectors = tuple(cast(list[str], selectors))
    selected = {
        node
        for node in costs
        if node in frozen_selectors or node.split("::", 1)[0] in frozen_selectors
    }
    manifest = ("\n".join(frozen_selectors) + "\n").encode()
    if (
        selected != frozen
        or hashlib.sha256(manifest).hexdigest() != index["frozen_manifest_sha256"]
    ):
        raise SystemExit("Scoped allocation frozen selection differs.")
    source = _mapping(
        index["source"],
        {"run_id", "attempt", "pr_head", "checkout", "conclusion", "runtime_fingerprint"},
        "source",
    )
    runtime = json.loads((root / "src/warhammer40k_core/_engine_build_manifest.json").read_bytes())
    if source["conclusion"] != "failure" or source["runtime_fingerprint"] != runtime["fingerprint"]:
        raise SystemExit("Scoped allocation must retain its failed run and current runtime.")
    evidence = _mapping(index["evidence"], {"file", "sha256"}, "worker evidence")
    path = directory / EVIDENCE_FILE
    if (
        evidence["file"] != EVIDENCE_FILE
        or hashlib.sha256(path.read_bytes()).hexdigest() != evidence["sha256"]
    ):
        raise SystemExit("Scoped allocation worker evidence is missing or changed.")
    data = read_json(path)
    # Reuse strict receipt, source, inventory and phase validation only. The returned
    # max-with-baseline weights are deliberately not used by dispatch or this model.
    calibrated_seconds(data, baseline={node: costs[node] for node in known}, root=root)
    record = cast(dict[str, object], data)
    reports = cast(list[dict[str, object]], record["reports"])
    observations = cast(dict[str, list[list[int | float]]], record["observations"])
    if record["baseline_only_cases"] or observations.keys() != known:
        raise SystemExit("Scoped allocation known scope is incomplete.")
    phases: dict[int, dict[str, tuple[float, float, float]]] = {}
    for node, rows in observations.items():
        if len(rows) != 1:
            raise SystemExit("Scoped allocation repeats a known case.")
        number, setup, call, teardown = rows[0]
        phases.setdefault(int(number), {})[node] = (float(setup), float(call), float(teardown))
    groups = _fixture_groups(root, set(known))
    cases: dict[str, float] = {}
    setup_costs: dict[str, float] = {}
    for number, report in enumerate(reports):
        producer = cast(dict[str, object], report["source"])
        if (
            any(producer[key] != value for key, value in source.items())
            or report["incomplete_or_unsuccessful_cases"] != 0
            or number not in phases
        ):
            raise SystemExit("Scoped allocation worker producer or outcome differs.")
        worker_setup: dict[str, float] = {}
        for node, (setup, call, teardown) in phases[number].items():
            cases[node] = call + teardown + (0 if node in groups else setup)
            if node in groups:
                group = groups[node]
                worker_setup[group] = worker_setup.get(group, 0.0) + setup
        for group, seconds in worker_setup.items():
            setup_costs[group] = max(setup_costs.get(group, 0.0), seconds)
    supervisors = index["supervisors"]
    if not isinstance(supervisors, list) or len(supervisors) != 11 or len(reports) != 45:
        raise SystemExit("Invalid scoped allocation supervisors.")
    receipts = [_supervisor(value) for value in supervisors]
    excluded = _supervisor(index["excluded_supervisor"], failed=True)
    shard_ids = [cast(dict[str, object], value["payload"])["shard_id"] for value in supervisors]
    excluded_payload = cast(
        dict[str, object], cast(dict[str, object], index["excluded_supervisor"])["payload"]
    )
    if set(shard_ids) != {
        str(number) for number in range(1, 13) if number != index["frozen_shard"]
    } or excluded_payload["shard_id"] != str(index["frozen_shard"]):
        raise SystemExit("Scoped allocation supervisor shard inventory differs.")
    if excluded["artifact_id"] in {row["artifact_id"] for row in receipts}:
        raise SystemExit("Scoped allocation includes its failed workload.")
    _validate_artifacts(index["artifacts"], reports, receipts, source)
    digests = [cast(str, report["sha256"]) for report in reports]
    parallel, mirror = _role_residuals(
        receipts,
        digests,
        reports,
        {digest: i for i, digest in enumerate(digests)},
        phases,
        requires_mirror=True,
    )
    return ScopedEvidence(
        Cohort(
            f"{source['run_id']}-partial-known-scope", cases, groups, setup_costs, parallel, mirror
        ),
        index["frozen_shard"],
        frozen_selectors,
        known,
        frozen,
        binding,
    )


def _validate_artifacts(
    value: object,
    reports: list[dict[str, object]],
    receipts: list[dict[str, object]],
    source: dict[str, object],
) -> None:
    if not isinstance(value, list):
        raise SystemExit("Invalid scoped allocation artifact provenance.")
    expected = {row["artifact_id"] for row in receipts}
    seen: set[int] = set()
    for item in value:
        row = _mapping(
            item,
            {
                "artifact_id",
                "zip_sha256",
                "run_id",
                "attempt",
                "source_head",
                "producer_job_id",
                "worker_sha256",
                "producer_started_at",
                "producer_completed_at",
                "artifact_created_at",
                "artifact_updated_at",
            },
            "artifact",
        )
        artifact = row["artifact_id"]
        digest = row["zip_sha256"]
        hashes = [
            cast(str, report["sha256"])
            for report in reports
            if cast(dict[str, object], report["source"])["artifact_id"] == artifact
        ]
        members = [
            report
            for report in reports
            if cast(dict[str, object], report["source"])["artifact_id"] == artifact
        ]
        parallel = {report["worker"] for report in members if report["worker_count"] == 4}
        serial = [report["worker"] for report in members if report["worker_count"] == 1]
        if (
            type(artifact) is not int
            or artifact not in expected
            or artifact in seen
            or not isinstance(digest, str)
            or len(digest) != 64
            or any(character not in "0123456789abcdef" for character in digest)
            or row["run_id"] != source["run_id"]
            or row["attempt"] != source["attempt"]
            or row["source_head"] != source["pr_head"]
            or type(row["producer_job_id"]) is not int
            or row["producer_job_id"] < 1
            or row["worker_sha256"] != sorted(hashes)
            or parallel != {"gw0", "gw1", "gw2", "gw3"}
            or serial not in ([], ["gw0"])
        ):
            raise SystemExit("Scoped allocation artifact producer or worker binding differs.")
        timestamps: list[datetime] = []
        for field in (
            "producer_started_at",
            "artifact_created_at",
            "artifact_updated_at",
            "producer_completed_at",
        ):
            value = row[field]
            if not isinstance(value, str):
                raise SystemExit("Scoped allocation producer timestamp is missing.")
            try:
                timestamp = datetime.fromisoformat(value)
            except ValueError as error:
                raise SystemExit("Invalid scoped allocation producer timestamp.") from error
            if timestamp.tzinfo is None:
                raise SystemExit("Scoped allocation producer timestamp lacks a timezone.")
            timestamps.append(timestamp)
        if timestamps != sorted(timestamps):
            raise SystemExit("Scoped allocation artifact predates or outlives its producer.")
        seen.add(artifact)
    if seen != expected:
        raise SystemExit("Scoped allocation artifact coverage differs.")


def load_declared_scope(
    directory: Path,
    *,
    root: Path,
    costs: dict[str, float] | None,
) -> ScopedEvidence | None:
    from scripts.shard_execution_model import PROFILE_FILE

    path = directory / PROFILE_FILE
    if not path.exists():
        return None
    index = read_json(path)
    if not isinstance(index, dict):
        raise SystemExit("Invalid allocation cohort index.")
    if "scoped_evidence" not in index:
        return None
    if costs is None:
        raise SystemExit("Scoped allocation requires complete dispatch costs.")
    return load_scope(directory, root=root, costs=costs, reference=index["scoped_evidence"])
