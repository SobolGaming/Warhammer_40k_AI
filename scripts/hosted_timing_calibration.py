"""Historical hosted observations used only for CI scheduling, never qualification."""

from __future__ import annotations

import hashlib
import json
import math
import re
import subprocess
from pathlib import Path
from typing import cast

SCHEMA = "hosted-timing-calibration-v1"
FILENAME = "hosted-calibration.json"
ROLE = "Historical planning observations; not a complete passing profile or current performance"
FORMULA = "max(complete-baseline-case-seconds, largest-observed-passed-three-phase-total)"
PHASES = ("setup", "call", "teardown")


def _object(value: object, fields: set[str], label: str) -> dict[str, object]:
    if not isinstance(value, dict) or value.keys() != fields:
        raise SystemExit(f"Invalid calibration {label} fields.")
    return cast(dict[str, object], value)


def _pairs(pairs: list[tuple[str, object]]) -> dict[str, object]:
    result: dict[str, object] = {}
    for key, value in pairs:
        if key in result:
            raise SystemExit("Duplicate calibration field: " + key)
        result[key] = value
    return result


def read_json(path: Path) -> object:
    return json.loads(path.read_text(encoding="utf-8"), object_pairs_hook=_pairs)


def _hash(value: object, width: int = 64) -> str:
    if not isinstance(value, str) or re.fullmatch(f"[0-9a-f]{{{width}}}", value) is None:
        raise SystemExit("Invalid calibration digest.")
    return value


def _seconds(value: object) -> float:
    if type(value) not in (int, float):
        raise SystemExit("Invalid calibration seconds.")
    result = float(cast(int | float, value))
    if not math.isfinite(result) or result < 0:
        raise SystemExit("Invalid calibration seconds.")
    return result


def _positive(value: object) -> int:
    if type(value) is not int or value < 1:
        raise SystemExit("Invalid calibration positive integer.")
    return value


def _inventory(nodes: set[str]) -> str:
    return hashlib.sha256("\n".join(sorted(nodes)).encode()).hexdigest()


def _source(value: object) -> dict[str, object]:
    source = _object(
        value,
        {
            "run_id",
            "attempt",
            "pr_head",
            "checkout",
            "conclusion",
            "artifact_id",
            "runtime_fingerprint",
        },
        "source",
    )
    for field in ("run_id", "attempt", "artifact_id"):
        _positive(source[field])
    _hash(source["runtime_fingerprint"])
    for field in ("pr_head", "checkout"):
        _hash(source[field], 40)
    if source["conclusion"] not in ("success", "failure"):
        raise SystemExit("Invalid calibration enclosing run conclusion.")
    return source


def passed_phases(
    value: object, *, allowed_nodes: set[str] | None = None
) -> tuple[dict[str, list[float]], int]:
    """Reject malformed reports; explicitly count incomplete/unsuccessful cases."""
    if not isinstance(value, list):
        raise SystemExit("Calibration reports must be a list.")
    grouped: dict[str, dict[str, tuple[float, str]]] = {}
    for item in value:
        row = _object(item, {"nodeid", "phase", "seconds", "outcome"}, "phase")
        node, phase, outcome = row["nodeid"], row["phase"], row["outcome"]
        if (
            not isinstance(node, str)
            or "::" not in node
            or phase not in PHASES
            or outcome not in ("passed", "failed", "skipped")
        ):
            raise SystemExit("Invalid calibration phase identity/outcome.")
        if allowed_nodes is not None and node not in allowed_nodes:
            raise SystemExit("Calibration reports contain an uncollected case.")
        node_phases = grouped.setdefault(node, {})
        if phase in node_phases:
            raise SystemExit("Duplicate calibration case phase.")
        node_phases[phase] = (_seconds(row["seconds"]), outcome)
    passed = {
        node: [phases[phase][0] for phase in PHASES]
        for node, phases in grouped.items()
        if phases.keys() == set(PHASES) and all(row[1] == "passed" for row in phases.values())
    }
    return passed, len(grouped) - len(passed)


def build_calibration(
    *,
    inputs: tuple[tuple[Path, dict[str, object]], ...],
    baseline: dict[str, float],
    root: Path,
) -> dict[str, object]:
    """Inputs pair downloaded raw worker bytes with separately verified API metadata.

    Run attempt is NOT present in the worker JSON. The caller supplies the artifact's
    exact attempt from job/API evidence, separately from its immutable checkout SHA.
    Historical source compatibility must be reviewed before supplying these inputs.
    """
    if not inputs:
        raise SystemExit("Calibration requires raw worker evidence.")
    reports: list[dict[str, object]] = []
    observations: dict[str, list[list[int | float]]] = {}
    source_modules: dict[tuple[str, str], bytes] = {}
    build_fingerprints: dict[str, str] = {}
    raw_digests: set[str] = set()
    for path, metadata in inputs:
        source = _source(metadata)
        revision = cast(str, source["pr_head"])
        if revision not in build_fingerprints:
            manifest = subprocess.check_output(
                ["git", "show", revision + ":src/warhammer40k_core/_engine_build_manifest.json"],
                cwd=root,
            )
            build_fingerprints[revision] = json.loads(manifest)["fingerprint"]
        if build_fingerprints[revision] != source["runtime_fingerprint"]:
            raise SystemExit("Calibration recorded build identity differs from source revision.")
        raw = path.read_bytes()
        digest = hashlib.sha256(raw).hexdigest()
        if digest in raw_digests:
            raise SystemExit("Duplicate raw calibration worker report.")
        raw_digests.add(digest)
        payload = read_json(path)
        if not isinstance(payload, dict):
            raise SystemExit("Calibration worker report must be an object.")
        row = cast(dict[str, object], payload)
        if (
            row.get("github_sha") != source["checkout"]
            or row.get("github_run_id") != str(source["run_id"])
            or row.get("worker_count") not in ("1", "4")
            or not isinstance(row.get("worker"), str)
            or re.fullmatch(r"gw[0-3]", cast(str, row["worker"])) is None
            or type(row.get("exit_status")) is not int
            or row["exit_status"] != 0
        ):
            raise SystemExit("Calibration worker/source identity or successful exit differs.")
        collected = row.get("collected_nodeids")
        if (
            not isinstance(collected, list)
            or not collected
            or any(not isinstance(node, str) or node not in baseline for node in collected)
            or len(set(collected)) != len(collected)
        ):
            raise SystemExit("Calibration collected inventory differs from complete baseline.")
        for owner in {node.split("::", 1)[0] for node in collected}:
            key = (revision, owner)
            if key not in source_modules:
                source_modules[key] = subprocess.check_output(
                    ["git", "show", revision + ":" + owner], cwd=root
                )
            if source_modules[key] != (root / owner).read_bytes():
                raise SystemExit("Calibration historical test source differs: " + owner)
        phases, excluded = passed_phases(row.get("reports"), allowed_nodes=set(collected))
        if not phases.keys() <= set(collected):
            raise SystemExit("Calibration reports contain an uncollected case.")
        index = len(reports)
        reports.append(
            {
                "source": source,
                "sha256": digest,
                "worker": row["worker"],
                "worker_count": int(cast(str, row["worker_count"])),
                "elapsed_seconds": _seconds(row.get("elapsed_seconds")),
                "collected_cases": len(collected),
                "collected_sha256": _inventory(set(collected)),
                "passed_cases": len(phases),
                "incomplete_or_unsuccessful_cases": excluded,
            }
        )
        for node, values in phases.items():
            observations.setdefault(node, []).append([index, *values])
    owners = {node.split("::", 1)[0] for node in baseline}
    result: dict[str, object] = {
        "schema": SCHEMA,
        "role": ROLE,
        "formula": FORMULA,
        "inventory_sha256": _inventory(set(baseline)),
        "current_test_sources": {
            owner: hashlib.sha256((root / owner).read_bytes()).hexdigest()
            for owner in sorted(owners)
        },
        "reports": reports,
        "observation_fields": ["report_index", *PHASES],
        "observations": dict(sorted(observations.items())),
        "observed_cases": len(observations),
        "baseline_only_cases": sorted(baseline.keys() - observations.keys()),
    }
    calibrated_seconds(result, baseline=baseline, root=root)
    return result


def calibrated_seconds(
    value: object, *, baseline: dict[str, float], root: Path
) -> dict[str, float]:
    record = _object(
        value,
        {
            "schema",
            "role",
            "formula",
            "inventory_sha256",
            "current_test_sources",
            "reports",
            "observation_fields",
            "observations",
            "observed_cases",
            "baseline_only_cases",
        },
        "record",
    )
    if (
        record["schema"] != SCHEMA
        or record["role"] != ROLE
        or record["formula"] != FORMULA
        or record["observation_fields"] != ["report_index", *PHASES]
        or record["inventory_sha256"] != _inventory(set(baseline))
    ):
        raise SystemExit("Calibration schema/role/formula/inventory differs.")
    owners = {node.split("::", 1)[0] for node in baseline}
    sources = _object(record["current_test_sources"], owners, "current test sources")
    for owner, digest in sources.items():
        if _hash(digest) != hashlib.sha256((root / owner).read_bytes()).hexdigest():
            raise SystemExit("Calibration current test source changed: " + owner)
    reports = record["reports"]
    if not isinstance(reports, list) or not reports:
        raise SystemExit("Calibration requires worker receipts.")
    digests: set[str] = set()
    identities: set[tuple[object, ...]] = set()
    artifact_sources: dict[tuple[object, ...], dict[str, object]] = {}
    artifact_keys: list[tuple[object, ...]] = []
    for item in reports:
        report = _object(
            item,
            {
                "source",
                "sha256",
                "worker",
                "worker_count",
                "elapsed_seconds",
                "collected_cases",
                "collected_sha256",
                "passed_cases",
                "incomplete_or_unsuccessful_cases",
            },
            "worker receipt",
        )
        source = _source(report["source"])
        artifact = tuple(source[key] for key in ("run_id", "attempt", "artifact_id"))
        if artifact in artifact_sources and artifact_sources[artifact] != source:
            raise SystemExit("Calibration artifact source identity differs across reports.")
        artifact_sources[artifact] = source
        artifact_keys.append(artifact)
        digest = _hash(report["sha256"])
        if digest in digests:
            raise SystemExit("Duplicate calibration worker receipt.")
        digests.add(digest)
        _hash(report["collected_sha256"])
        collected = _positive(report["collected_cases"])
        passed = _positive(report["passed_cases"])
        excluded = report["incomplete_or_unsuccessful_cases"]
        if type(excluded) is not int or excluded < 0 or passed + excluded > collected:
            raise SystemExit("Calibration worker case counts differ.")
        if (
            type(report["worker_count"]) is not int
            or report["worker_count"] not in (1, 4)
            or not isinstance(report["worker"], str)
            or re.fullmatch(r"gw[0-3]", report["worker"]) is None
        ):
            raise SystemExit("Invalid calibration worker identity.")
        identity = (*artifact, report["worker_count"], report["worker"])
        if identity in identities:
            raise SystemExit("Duplicate calibration worker invocation.")
        identities.add(identity)
        _seconds(report["elapsed_seconds"])
    observations = record["observations"]
    if (
        not isinstance(observations, dict)
        or not observations
        or not observations.keys() <= baseline.keys()
    ):
        raise SystemExit("Calibration observed inventory differs.")
    if (
        type(record["observed_cases"]) is not int
        or record["observed_cases"] != len(observations)
        or record["baseline_only_cases"] != sorted(baseline.keys() - observations.keys())
    ):
        raise SystemExit("Calibration observed/baseline-only counts differ.")
    result = {node: _seconds(seconds) for node, seconds in baseline.items()}
    selected_counts: dict[int, int] = {}
    for node, samples in observations.items():
        if not isinstance(samples, list) or not samples:
            raise SystemExit("Invalid calibration observation samples.")
        seen_reports: set[int] = set()
        seen_artifacts: set[tuple[object, ...]] = set()
        for row in samples:
            if (
                not isinstance(row, list)
                or len(row) != 4
                or type(row[0]) is not int
                or not 0 <= row[0] < len(reports)
                or row[0] in seen_reports
            ):
                raise SystemExit("Invalid or duplicate calibration observation receipt.")
            if artifact_keys[row[0]] in seen_artifacts:
                raise SystemExit("Duplicate completed calibration case within artifact/attempt.")
            seen_artifacts.add(artifact_keys[row[0]])
            seen_reports.add(row[0])
            selected_counts[row[0]] = selected_counts.get(row[0], 0) + 1
            total = math.fsum(_seconds(seconds) for seconds in row[1:])
            if not math.isfinite(total):
                raise SystemExit("Invalid calibration observation total.")
            result[node] = max(result[node], total)
    if any(
        selected_counts.get(index, 0) != report["passed_cases"]
        for index, report in enumerate(reports)
    ):
        raise SystemExit("Calibration observations differ from worker passed cases.")
    return result


def load_planning_seconds(
    path: Path, *, baseline: dict[str, float], root: Path, expected_sha256: str | None = None
) -> tuple[dict[str, float], str]:
    digest = hashlib.sha256(path.read_bytes()).hexdigest()
    if expected_sha256 is not None and digest != _hash(expected_sha256):
        raise SystemExit("Calibration sidecar digest differs from shard summary.")
    return calibrated_seconds(read_json(path), baseline=baseline, root=root), digest
