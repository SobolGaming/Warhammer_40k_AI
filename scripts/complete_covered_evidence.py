"""Strict shared reader for complete, source-bound covered execution evidence."""

from __future__ import annotations

import hashlib
import json
import math
import subprocess
from pathlib import Path
from tempfile import TemporaryDirectory
from typing import cast

from scripts.hosted_timing_calibration import _object, _seconds, read_json


def artifact_text(value: object) -> str:
    item = _object(value, {"sha256", "text"}, "fresh covered artifact")
    text = item["text"]
    if not isinstance(text, str) or hashlib.sha256(text.encode()).hexdigest() != item["sha256"]:
        raise SystemExit("Fresh covered artifact digest differs.")
    return text


def verify_complete_covered_profile(
    root: Path,
    directory: Path,
    reference_value: object,
    baseline: dict[str, object],
    inputs: dict[str, str],
    native_nodes: list[str],
    *,
    filename: str,
) -> float:
    from tools.performance_policy import canonical_digest

    from scripts import build_test_shards as sharding

    reference = _object(reference_value, {"file", "sha256"}, "fresh evidence reference")
    path = directory / filename
    if (
        reference["file"] != filename
        or hashlib.sha256(path.read_bytes()).hexdigest() != reference["sha256"]
    ):
        raise SystemExit("Fresh covered evidence reference differs.")
    record = _object(
        read_json(path),
        {
            "schema",
            "preflight",
            "postflight",
            "supervisor",
            "serial_worker",
            "parallel_workers",
            "serial_junit",
            "parallel_junit",
            "coverage",
            "stages",
        },
        "fresh covered evidence",
    )
    if record["schema"] != "complete-covered-source-and-phase-evidence-v1":
        raise SystemExit("Unreviewed fresh covered evidence schema.")
    pre = cast(dict[str, object], json.loads(artifact_text(record["preflight"])))
    post = cast(dict[str, object], json.loads(artifact_text(record["postflight"])))
    tree = subprocess.check_output(
        ["git", "rev-parse", str(baseline["source_head"]) + "^{tree}"], cwd=root, text=True
    ).strip()
    if (
        pre.get("head") != baseline["source_head"]
        or post.get("head") != baseline["source_head"]
        or pre.get("tree") != tree
        or pre.get("inputs") != inputs
        or pre.get("input_digest") != canonical_digest(inputs)
        or post.get("input_digest") != pre["input_digest"]
        or post.get("inputs_unchanged") is not True
    ):
        raise SystemExit("Fresh covered source pre/post identity differs.")
    supervisor = json.loads(artifact_text(record["supervisor"]))
    if supervisor != baseline["supervisor"]:
        raise SystemExit("Fresh covered supervisor differs from the approved baseline.")
    stages = json.loads(artifact_text(record["stages"]))
    if [stage["name"] for stage in stages] != [
        "source-history",
        "cold-source-index",
        "serial-native-and-mirror",
        "parallel-behavior",
    ] or any(stage["exit_code"] != 0 for stage in stages):
        raise SystemExit("Fresh covered source/index/test stages are incomplete.")
    coverage = json.loads(artifact_text(record["coverage"]))
    if coverage["meta"]["branch_coverage"] is not True or (
        coverage["totals"]["percent_covered"] != baseline["coverage_percent"]
    ):
        raise SystemExit("Fresh covered branch coverage differs.")
    serial = cast(dict[str, object], json.loads(artifact_text(record["serial_worker"])))
    serial_nodes = [sharding.SERIAL_BEHAVIORAL_CASE, *native_nodes]
    parallel_nodes = set(cast(dict[str, float], baseline["case_seconds"])) - set(serial_nodes)
    workers_value = record["parallel_workers"]
    if not isinstance(workers_value, dict) or workers_value.keys() != {f"gw{i}" for i in range(32)}:
        raise SystemExit("Fresh covered profile requires exactly 32 parallel workers.")
    workers = {name: json.loads(artifact_text(value)) for name, value in workers_value.items()}
    phases: dict[tuple[str, str], float] = {}
    for name, worker in {"serial": serial, **workers}.items():
        is_serial = name == "serial"
        expected = set(serial_nodes) if is_serial else parallel_nodes
        collected = worker.get("collected_nodeids")
        if (
            worker.get("worker_count") != ("1" if is_serial else "32")
            or worker.get("worker") != ("gw0" if is_serial else name)
            or worker.get("exit_status") != 0
            or not isinstance(collected, list)
            or len(collected) != len(expected)
            or set(collected) != expected
            or (is_serial and collected != serial_nodes)
        ):
            raise SystemExit("Fresh covered worker or collection inventory differs.")
        for value in worker["reports"]:
            row = _object(value, {"nodeid", "phase", "seconds", "outcome"}, "fresh covered phase")
            node, phase = str(row["nodeid"]), str(row["phase"])
            if (
                node not in expected
                or phase not in {"setup", "call", "teardown"}
                or row["outcome"] != "passed"
                or (node, phase) in phases
            ):
                raise SystemExit(
                    "Fresh covered phases are repeated, unsuccessful or outside inventory."
                )
            phases[node, phase] = _seconds(row["seconds"])
    if phases.keys() != {
        (node, phase)
        for node in (*serial_nodes, *parallel_nodes)
        for phase in ("setup", "call", "teardown")
    }:
        raise SystemExit("Fresh covered phase inventory is incomplete.")
    with TemporaryDirectory(prefix="covered-profile-") as tmp:
        temporary = Path(tmp)
        for side in ("serial", "parallel"):
            (temporary / (side + ".xml")).write_text(
                artifact_text(record[side + "_junit"]), encoding="utf-8"
            )
        source = str(cast(list[dict[str, object]], baseline["profiles"])[0]["source"])
        durations, profiles = sharding._profile_medians((temporary,), (source,))
        cases = sharding._case_profile_medians((temporary,))
        files = sharding._rounded_durations(
            sharding._partitioned_durations(durations, case_seconds=cases)
        )
    if (
        cases != baseline["case_seconds"]
        or files != baseline["files"]
        or list(profiles) != baseline["profiles"]
    ):
        raise SystemExit(
            "Fresh complete JUnit differs from current scheduling weights or provenance."
        )
    return math.fsum(value for (node, _), value in phases.items() if node in native_nodes)
