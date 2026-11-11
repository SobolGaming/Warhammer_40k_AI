"""Authenticated passed triples from a failed job, separate from derived stress."""

from __future__ import annotations

import hashlib
import json
import math
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import cast

from scripts.hosted_timing_calibration import _hash, _seconds, passed_phases, read_json
from scripts.scoped_shard_evidence import ScopedEvidence, _mapping, _nodes, _supervisor, node_digest
from scripts.shard_execution_model import Cohort, _fixture_groups

STRESS_FILE = "allocation-stress.json"
EXTENSION_FILE = "scoped-worker-extension.json"
PINNED_OWNER = "tests/infrastructure/adapters/test_canonical_deployment_coverage.py"
FIXED_OWNER = "tests/infrastructure/adapters/test_matched_attack_scenario.py"
FORMULA = (
    "max(same-case actual complete-cohort setup+call+teardown totals, "
    "unchanged843-report dispatch cost)"
)


@dataclass(frozen=True)
class ExtendedScope:
    raw: Cohort
    stress: Cohort
    unknown_node: str
    pinned_selector: str
    pinned_shard: int
    fixed_selector: str
    fixed_shard: int
    reference: dict[str, str]
    reservation_seconds: float


def _reference(directory: Path, value: object, filename: str) -> dict[str, str]:
    from scripts.build_test_shards import _selection_no_links

    row = _mapping(value, {"file", "sha256"}, "extension reference")
    path = directory / filename
    _selection_no_links(directory, path)
    if (
        row["file"] != filename
        or not path.is_file()
        or hashlib.sha256(path.read_bytes()).hexdigest() != row["sha256"]
    ):
        raise SystemExit("Scoped extension evidence is missing or changed.")
    return cast(dict[str, str], row)


def validate_reference(directory: Path, value: object) -> dict[str, str]:
    reference = _reference(directory, value, STRESS_FILE)
    stress = read_json(directory / STRESS_FILE)
    if not isinstance(stress, dict):
        raise SystemExit("Invalid derived stress document.")
    _reference(directory, stress.get("extension"), EXTENSION_FILE)
    return reference


def _artifact(value: object, expected: int) -> None:
    row = _mapping(
        value,
        {
            "artifact_id",
            "zip_sha256",
            "producer_job_id",
            "producer_started_at",
            "producer_completed_at",
            "artifact_created_at",
            "artifact_updated_at",
        },
        "extension artifact",
    )
    _hash(row["zip_sha256"])
    if row["artifact_id"] != expected or type(row["producer_job_id"]) is not int:
        raise SystemExit("Extension artifact producer differs.")
    if row["producer_job_id"] <= 0:
        raise SystemExit("Extension artifact producer is invalid.")
    timestamps: list[datetime] = []
    for key in (
        "producer_started_at",
        "artifact_created_at",
        "artifact_updated_at",
        "producer_completed_at",
    ):
        value = row[key]
        if not isinstance(value, str):
            raise SystemExit("Extension producer timestamp is missing.")
        try:
            timestamp = datetime.fromisoformat(value)
        except ValueError as error:
            raise SystemExit("Extension producer timestamp is invalid.") from error
        if timestamp.tzinfo is None:
            raise SystemExit("Extension producer timestamp lacks timezone.")
        timestamps.append(timestamp)
    if timestamps != sorted(timestamps):
        raise SystemExit("Extension artifact is outside its producer window.")


def _phases(
    value: object, source: dict[str, object], collected: frozenset[str]
) -> dict[str, list[float]]:
    if not isinstance(value, list) or len(value) != 4:
        raise SystemExit("Extension requires its four final worker reports.")
    result: dict[str, list[float]] = {}
    workers: set[str] = set()
    digests: set[str] = set()
    collection_order: list[str] | None = None
    for entry in value:
        record = _mapping(entry, {"sha256", "payload"}, "extension worker")
        payload = _mapping(
            record["payload"],
            {
                "worker",
                "platform",
                "python",
                "cpu_count",
                "linux_meminfo",
                "github_run_id",
                "github_sha",
                "worker_count",
                "elapsed_seconds",
                "collection_seconds",
                "exit_status",
                "collected_nodeids",
                "reports",
            },
            "extension worker payload",
        )
        digest = hashlib.sha256((json.dumps(payload, indent=2) + "\n").encode()).hexdigest()
        worker = payload["worker"]
        nodes = payload["collected_nodeids"]
        if (
            digest != record["sha256"]
            or digest in digests
            or not isinstance(worker, str)
            or worker in workers
            or worker not in {"gw0", "gw1", "gw3", "gw4"}
            or payload["worker_count"] != "4"
            or type(payload["exit_status"]) is not int
            or payload["exit_status"] != 0
            or payload["github_run_id"] != str(source["run_id"])
            or payload["github_sha"] != source["checkout"]
            or not isinstance(nodes, list)
            or any(not isinstance(node, str) for node in nodes)
            or len(nodes) != len(collected)
            or set(nodes) != collected
        ):
            raise SystemExit("Extension final worker identity or collection differs.")
        if collection_order is not None and nodes != collection_order:
            raise SystemExit("Replacement worker collection order differs.")
        collection_order = cast(list[str], nodes)
        _seconds(payload["elapsed_seconds"])
        _seconds(payload["collection_seconds"])
        phases, excluded = passed_phases(payload["reports"], allowed_nodes=set(collected))
        if excluded or not phases or result.keys() & phases.keys():
            raise SystemExit("Extension has incomplete, failed or duplicate phases.")
        result.update(phases)
        workers.add(worker)
        digests.add(digest)
    if workers != {"gw0", "gw1", "gw3", "gw4"}:
        raise SystemExit("Extension replacement worker identity differs.")
    return result


def _reserve(
    directory: Path, stress: dict[str, object], unknown: str, costs: dict[str, float]
) -> float:
    calibration = cast(dict[str, object], read_json(directory / "hosted-calibration.json"))
    reports = cast(list[dict[str, object]], calibration["reports"])
    observations = cast(dict[str, list[list[int | float]]], calibration["observations"])
    by_hash = {
        cast(str, reports[int(row[0])]["sha256"]): tuple(row[1:]) for row in observations[unknown]
    }
    index = cast(dict[str, object], read_json(directory / "allocation-cohorts.json"))
    cohorts = cast(list[dict[str, object]], index["cohorts"])
    sources = stress["sources"]
    if not isinstance(sources, list) or len(sources) != len(cohorts):
        raise SystemExit("Unknown reserve requires every complete cohort's actual case.")
    totals: list[float] = []
    for entry, cohort in zip(sources, cohorts, strict=True):
        row = _mapping(entry, {"report_sha256", "setup", "call", "teardown"}, "reserve source")
        digest = row["report_sha256"]
        if (
            not isinstance(digest, str)
            or digest not in by_hash
            or digest not in cast(list[str], cohort["reports"])
        ):
            raise SystemExit("Unknown reserve report is outside its complete cohort.")
        phases = tuple(_seconds(row[key]) for key in ("setup", "call", "teardown"))
        if phases != by_hash[digest]:
            raise SystemExit("Unknown reserve phases differ from measured observations.")
        totals.append(math.fsum(phases))
    summary = cast(dict[str, object], read_json(directory / "durations.json"))
    baseline = cast(dict[str, float], summary["case_seconds"])[unknown]
    floor = max(baseline, *(math.fsum(row[1:]) for row in observations[unknown] if row[0] < 843))
    expected = max(costs[unknown], *totals)
    if stress["dispatch_floor"] != floor or stress["reservation_seconds"] != expected:
        raise SystemExit("Unknown reserve differs from its declared measured maximum.")
    return expected


def load_extension(
    directory: Path, *, root: Path, costs: dict[str, float], base: ScopedEvidence, reference: object
) -> ExtendedScope:
    binding = validate_reference(directory, reference)
    stress = _mapping(
        read_json(directory / STRESS_FILE),
        {
            "schema",
            "role",
            "extension",
            "unknown_node",
            "unknown_owner",
            "pinned_shard",
            "fixed_selector",
            "fixed_shard",
            "reservation_seconds",
            "formula",
            "sources",
            "dispatch_floor",
            "source_bindings",
        },
        "derived stress",
    )
    data = _mapping(
        read_json(directory / EXTENSION_FILE),
        {
            "schema",
            "role",
            "base_reference",
            "source",
            "known_nodes",
            "known_nodes_sha256",
            "unknown_nodes",
            "unknown_nodes_sha256",
            "combined_known_nodes_sha256",
            "source_files",
            "failed_supervisor",
            "artifact",
            "merge_binding",
            "reports",
        },
        "raw partial extension",
    )
    original = cast(dict[str, object], read_json(directory / "allocation-scope.json"))
    if (
        data["schema"] != "failed-workload-passed-triples-extension-v1"
        or data["role"]
        != ("Separate raw partial evidence; failed workload and missing case remain failed/unknown")
        or data["base_reference"] != base.reference
        or data["source"] != original["source"]
        or data["failed_supervisor"] != original["excluded_supervisor"]
        or stress["schema"] != "explicit-unknown-case-planning-reserve-v1"
        or stress["role"] != "Derived stress only; never a measured phase or complete cohort"
        or stress["formula"] != FORMULA
        or stress["unknown_owner"] != PINNED_OWNER
        or stress["fixed_selector"] != FIXED_OWNER
        or stress["pinned_shard"] != 4
        or stress["fixed_shard"] != 5
    ):
        raise SystemExit("Extension source, failed outcome or planning identity differs.")
    known, unknowns = _nodes(data["known_nodes"]), _nodes(data["unknown_nodes"])
    if (
        len(unknowns) != 1
        or known & base.known_nodes
        or known & unknowns
        or known | unknowns != base.frozen_nodes
        or node_digest(known) != data["known_nodes_sha256"]
        or node_digest(unknowns) != data["unknown_nodes_sha256"]
        or node_digest(known | base.known_nodes) != data["combined_known_nodes_sha256"]
    ):
        raise SystemExit("Extension known/unknown inventory differs.")
    unknown = next(iter(unknowns))
    if stress["unknown_node"] != unknown or unknown.split("::", 1)[0] != PINNED_OWNER:
        raise SystemExit("Unknown case must remain in its pinned whole file.")
    source = cast(dict[str, object], data["source"])
    merge = data["merge_binding"]
    if (
        not isinstance(merge, dict)
        or merge.get("tested_context") != source["checkout"]
        or merge.get("tested_tree") != merge.get("retained_source_tree")
        or merge.get("exact_tree_identity_verified") is not True
        or merge.get("parents") != ["e02369d8952feb91690994f4fa3071b43f9dbede", source["pr_head"]]
    ):
        raise SystemExit("Extension tested merge-tree source binding differs.")
    owners = {node.split("::", 1)[0] for node in base.frozen_nodes}
    for mapping, expected in (
        (data["source_files"], owners),
        (stress["source_bindings"], {PINNED_OWNER, FIXED_OWNER}),
    ):
        if not isinstance(mapping, dict) or mapping.keys() != expected:
            raise SystemExit("Extension source owner inventory differs.")
        for owner, digest in mapping.items():
            if hashlib.sha256((root / owner).read_bytes()).hexdigest() != digest:
                raise SystemExit("Extension source bytes changed.")
    failed = _supervisor(data["failed_supervisor"], failed=True)
    _artifact(data["artifact"], cast(int, failed["artifact_id"]))
    phases = _phases(data["reports"], source, base.frozen_nodes)
    if phases.keys() != known:
        raise SystemExit("Extension final phases do not cover exactly its known inventory.")
    if _fixture_groups(root, set(known | unknowns)):
        raise SystemExit("Extension fixture groups require a separately reviewed setup model.")
    cases = {
        **base.cohort.cases,
        **{node: call + teardown + setup for node, (setup, call, teardown) in phases.items()},
    }
    raw = Cohort(
        "43059076830-expanded6281-known-raw-partial",
        cases,
        base.cohort.groups,
        base.cohort.setup,
        base.cohort.parallel_residual,
        base.cohort.mirror_residual,
    )
    reservation = _reserve(directory, stress, unknown, costs)
    derived = Cohort(
        "derived-stress-6281-known-plus-one-reserve-not-measured-cohort",
        {**cases, unknown: reservation},
        raw.groups,
        raw.setup,
        raw.parallel_residual,
        raw.mirror_residual,
    )
    return ExtendedScope(
        raw, derived, unknown, PINNED_OWNER, 4, FIXED_OWNER, 5, binding, reservation
    )
