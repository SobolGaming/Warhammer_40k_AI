"""Explicit derived scheduling across one authenticated historical boundary.

Historical phases remain historical. New cases have only a complete current local
baseline, never invented hosted observations. Neither estimate qualifies timing.
"""

from __future__ import annotations

import hashlib
import json
import math
import subprocess
from dataclasses import dataclass
from functools import cache
from pathlib import Path
from typing import TYPE_CHECKING, cast

from scripts.historical_shard_snapshot import (
    HISTORICAL_REVISION,
    MANIFEST,
    HistoricalSnapshot,
    fingerprint,
    historical_snapshot,
    unchanged_historical_files,
)
from scripts.hosted_timing_calibration import (
    _hash,
    _object,
    _seconds,
    calibrated_seconds,
    read_json,
)
from scripts.shard_execution_model import Cohort, worker_chunks

if TYPE_CHECKING:
    from scripts.build_test_shards import ProfileEvidence

FILENAME = "current-runtime-compatibility.json"
BASELINE_FILE = "current-covered-baseline.json"
SCHEMA = "historical-snapshot-current-baseline-v1"
ROLE = "Derived scheduling only; historical phases and current local observations stay separate"

# Closed inventory for this explicitly reviewed compatibility version.
NEW_OWNER = "tests/rules/section03/test_terrain_path_preparation.py"
NEW_NODES: frozenset[str] = frozenset(
    f"{NEW_OWNER}::{case}"
    for case in (
        "test_immutable_terrain_caches_are_bounded_and_eviction_preserves_values",
        "test_prepared_terrain_builds_each_sample_once_and_keeps_boundary_contact",
        "test_prepared_terrain_samples_match_direct_intersections[0-base0]",
        "test_prepared_terrain_samples_match_direct_intersections[0-base1]",
        "test_prepared_terrain_samples_match_direct_intersections[0-base2]",
        "test_prepared_terrain_samples_match_direct_intersections[15-base0]",
        "test_prepared_terrain_samples_match_direct_intersections[15-base1]",
        "test_prepared_terrain_samples_match_direct_intersections[15-base2]",
        "test_prepared_terrain_samples_match_direct_intersections[179-base0]",
        "test_prepared_terrain_samples_match_direct_intersections[179-base1]",
        "test_prepared_terrain_samples_match_direct_intersections[179-base2]",
        "test_prepared_terrain_samples_match_direct_intersections[90-base0]",
        "test_prepared_terrain_samples_match_direct_intersections[90-base1]",
        "test_prepared_terrain_samples_match_direct_intersections[90-base2]",
        "test_terrain_preparation_preserves_complete_results_and_context_isolation",
        "test_terrain_footprint_cache_uses_exact_horizontal_geometry",
        "test_terrain_volume_cache_preserves_definition_identity_and_validation[False]",
        "test_terrain_volume_cache_preserves_definition_identity_and_validation[True]",
    )
)
CONNECTED_OWNER = "tests/rules/section11/test_connected_endpoints.py"
NEW_NODES |= frozenset(
    f"{CONNECTED_OWNER}::{case}"
    for case in (
        "test_connected_endpoint_exclusion_requires_every_fixed_component[None]",
        "test_connected_endpoint_exclusion_requires_every_fixed_component[1.0]",
        "test_connected_endpoint_proof_relaxes_the_entire_goal_and_peer_graph[empty]",
        "test_connected_endpoint_proof_relaxes_the_entire_goal_and_peer_graph[bridge]",
        "test_connected_endpoint_proof_relaxes_the_entire_goal_and_peer_graph[union]",
        "test_connected_endpoint_proof_relaxes_the_entire_goal_and_peer_graph[tangent]",
        "test_connected_endpoint_proof_relaxes_the_entire_goal_and_peer_graph[shape]",
        "test_connected_endpoint_proof_relaxes_the_entire_goal_and_peer_graph[body]",
        "test_connected_endpoint_certificate_survives_charge_history_reconstruction[disjoint]",
        "test_connected_endpoint_certificate_survives_charge_history_reconstruction[blocked]",
        "test_connected_endpoint_overlap_requires_collision_and_support_proof[blocked]",
        "test_connected_endpoint_overlap_requires_collision_and_support_proof[clear]",
        "test_connected_endpoint_overlap_requires_collision_and_support_proof[raised]",
        "test_connected_endpoint_overlap_requires_collision_and_support_proof[remote-support]",
        "test_connected_endpoint_overlap_requires_collision_and_support_proof[tangent]",
        "test_connected_endpoint_overlap_requires_collision_and_support_proof[shape]",
        "test_connected_endpoint_overlap_requires_collision_and_support_proof[reachable]",
        "test_shared_ordered_history_reader_preserves_existing_fight_witness",
    )
)


def enabled(directory: Path, summary: dict[str, object] | None = None) -> bool:
    declared = (directory / FILENAME).is_file()
    if not declared and (
        (directory / BASELINE_FILE).is_file()
        or (
            summary is not None
            and (
                "runtime_compatibility" in summary
                or summary.get("strategy")
                == "reviewed-current-assignment-with-authenticated-historical-projection-v1"
            )
        )
    ):
        raise SystemExit("Current scheduling compatibility descriptor is missing.")
    return declared


def _baseline(
    root: Path, directory: Path, descriptor: dict[str, object], history: HistoricalSnapshot
) -> dict[str, object]:
    reference = _object(descriptor["baseline"], {"file", "sha256"}, "current baseline reference")
    path = directory / BASELINE_FILE
    if (
        reference["file"] != BASELINE_FILE
        or hashlib.sha256(path.read_bytes()).hexdigest() != reference["sha256"]
    ):
        raise SystemExit("Current baseline evidence changed.")
    data = _object(
        read_json(path),
        {
            "schema",
            "source_head",
            "runtime_fingerprint",
            "test_sources",
            "case_seconds",
            "files",
            "profiles",
            "supervisor",
            "workers",
            "mirror_workers",
            "coverage_percent",
        },
        "current covered baseline",
    )
    _hash(data["source_head"], 40)
    runtime = json.loads((root / MANIFEST).read_bytes())["fingerprint"]
    if (
        data["schema"] != "complete-current-covered-baseline-v1"
        or data["runtime_fingerprint"] != runtime
        or descriptor["current_runtime_fingerprint"] != runtime
        or fingerprint(root, cast(str, data["source_head"])) != runtime
        or type(data["workers"]) is not int
        or data["workers"] != 32
        or type(data["mirror_workers"]) is not int
        or data["mirror_workers"] != 1
        or _seconds(data["coverage_percent"]) < 67
    ):
        raise SystemExit("Current baseline runtime, worker count or coverage differs.")
    receipt = data["supervisor"]
    if (
        not isinstance(receipt, dict)
        or receipt.get("schema") != "covered-shard-deadline-v1"
        or receipt.get("approval_seconds") != 1620
        or receipt.get("execution_seconds") != 1800
        or receipt.get("approved") is not True
        or receipt.get("reason") != "passed"
        or type(receipt.get("workload_exit_code")) is not int
        or receipt.get("workload_exit_code") != 0
        or receipt.get("terminated") is not False
        or receipt.get("cleanup_error") is not None
        or receipt.get("descendants_remained") is not False
        or _seconds(receipt.get("elapsed_seconds")) > 1620
    ):
        raise SystemExit("Current covered baseline did not pass its unchanged approval gate.")
    cases = cast(dict[str, float], data["case_seconds"])
    additions = _object(
        descriptor["new_test_sources"],
        {node.split("::", 1)[0] for node in cases.keys() - history.baseline.keys()},
        "new test source inventory",
    )
    if (
        cases.keys() != history.baseline.keys() | NEW_NODES
        or not history.baseline.keys() < cases.keys()
        or len(cases) - len(history.baseline) != 36
        or set(additions) != {NEW_OWNER, CONNECTED_OWNER}
        or set(additions) & {node.split("::", 1)[0] for node in history.baseline}
    ):
        raise SystemExit("Compatibility requires exactly the reviewed twenty-seven added cases.")
    owners = {node.split("::", 1)[0] for node in cases}
    sources = _object(data["test_sources"], owners, "current test source inventory")
    try:
        tree = (
            subprocess.check_output(
                ["git", "ls-tree", "-r", cast(str, data["source_head"]), "--", "tests"], cwd=root
            )
            .decode()
            .splitlines()
        )
    except subprocess.CalledProcessError as error:
        raise SystemExit("Current covered baseline source tree is unavailable.") from error
    blobs = {line.split("\t", 1)[1]: line.split()[2] for line in tree}
    for owner, digest in sources.items():
        current = (root / owner).read_bytes()
        blob = hashlib.sha1(b"blob " + str(len(current)).encode() + b"\0" + current).hexdigest()
        if hashlib.sha256(current).hexdigest() != digest or blobs.get(owner) != blob:
            raise SystemExit("Current baseline test source changed: " + owner)
        if owner in additions:
            if digest != additions[owner]:
                raise SystemExit("Added test source digest differs.")
        elif current != (history.root / owner).read_bytes():
            raise SystemExit("Historical test source changed across compatibility boundary.")
    from scripts.build_test_shards import summary_case_seconds

    # Keep the existing complete-profile case/file accounting, including finite selectors.
    summary_case_seconds(
        {"case_seconds": cases, "profiles": data["profiles"], "files": data["files"]}
    )
    return data


def derived_score(
    group: tuple[str, ...],
    dispatch: dict[str, float],
    current: dict[str, float],
    historical: Cohort,
    *,
    unknown: str | None = None,
) -> float:
    from scripts.build_test_shards import SERIAL_BEHAVIORAL_CASE

    chunks = worker_chunks(group, dispatch)
    additions = current.keys() - historical.cases.keys()

    def cost(node: str) -> float:
        if node in additions:
            return current[node]
        if node == unknown:
            return max(historical.cases[node], dispatch[node])
        return historical.cases[node]

    workers = [
        math.fsum(cost(node) for node in chunk)
        + math.fsum(
            historical.setup[key]
            for key in {historical.groups[node] for node in chunk if node in historical.groups}
        )
        for chunk in chunks
    ]
    mirror = SERIAL_BEHAVIORAL_CASE in group
    serial = cost(SERIAL_BEHAVIORAL_CASE) if mirror else 0.0
    if mirror and SERIAL_BEHAVIORAL_CASE in historical.groups:
        serial += historical.setup[historical.groups[SERIAL_BEHAVIORAL_CASE]]
    return (
        max(workers)
        + serial
        + (historical.mirror_residual if mirror else historical.parallel_residual)
    )


@dataclass(frozen=True)
class Plan:
    groups: tuple[tuple[str, ...], ...]
    dispatch: dict[str, float]
    metadata: dict[str, object]
    files: dict[str, float]
    profiles: list[ProfileEvidence]


def plan(root: Path, directory: Path, cases: dict[str, float]) -> Plan:
    from scripts.extended_shard_allocation import partial_projection

    descriptor = _object(
        read_json(directory / FILENAME),
        {
            "schema",
            "historical_revision",
            "current_runtime_fingerprint",
            "baseline",
            "new_test_sources",
            "assignment",
        },
        "runtime compatibility",
    )
    if descriptor["schema"] != SCHEMA or descriptor["historical_revision"] != HISTORICAL_REVISION:
        raise SystemExit("Unreviewed scheduling compatibility boundary.")
    with historical_snapshot(root) as history:
        unchanged_historical_files(directory, history)
        data = _baseline(root, directory, descriptor, history)
        if data["case_seconds"] != cases:
            raise SystemExit(
                "Current scheduling baseline differs from the complete covered evidence."
            )
        current = {node: _seconds(value) for node, value in cases.items()}
        old_dispatch = calibrated_seconds(
            read_json(history.directory / "hosted-calibration.json"),
            baseline={node: current[node] for node in history.baseline},
            root=history.root,
        )
        dispatch = {**current, **old_dispatch}
        extension = history.scope.extension
        assert extension is not None

        @cache
        def scores(group: tuple[str, ...]) -> tuple[float, ...]:
            return (
                *tuple(
                    derived_score(group, dispatch, current, cohort)
                    for cohort in history.cohorts[:-1]
                ),
                derived_score(
                    group, dispatch, current, extension.stress, unknown=extension.unknown_node
                ),
                derived_score(group, dispatch, current, history.cohorts[-1]),
            )

        from scripts.current_shard_assignment import load_assignment, require_planning_limits

        groups, assignment = load_assignment(directory, descriptor, history)
        for group in groups:
            require_planning_limits(scores(group))
        rows = {
            str(index): {
                "derived_historical_plus_current_additions": list(scores(group)),
                "original_6014_partial_raw": partial_projection(
                    group, dispatch, history.scope.cohort
                ),
                "expanded_6281_partial_raw": partial_projection(group, dispatch, extension.raw),
            }
            for index, group in enumerate(groups, 1)
        }
        metadata: dict[str, object] = {
            "file": FILENAME,
            "sha256": hashlib.sha256((directory / FILENAME).read_bytes()).hexdigest(),
            "schema": SCHEMA,
            "role": ROLE,
            "historical_revision": HISTORICAL_REVISION,
            "current_runtime_fingerprint": descriptor["current_runtime_fingerprint"],
            "baseline": descriptor["baseline"],
            "assignment": descriptor["assignment"],
            "retained_selector_moves": assignment["retained_selector_moves"],
            "new_selector_placement": assignment["new_selector_placement"],
            "historical_cases": len(history.baseline),
            "current_cases": len(cases),
            "new_cases_without_hosted_observations": sorted(cases.keys() - history.baseline.keys()),
            "historical_reservation_seconds_unchanged": extension.reservation_seconds,
            "derived_unknown_reservation_seconds": max(
                extension.reservation_seconds, dispatch[extension.unknown_node]
            ),
            "historical_summary_sha256": hashlib.sha256(
                (history.directory / "durations.json").read_bytes()
            ).hexdigest(),
            "historical_allocation_model": cast(
                dict[str, object], read_json(history.directory / "durations.json")
            )["allocation_model"],
            "historical_scoped_allocation": cast(
                dict[str, object], read_json(history.directory / "durations.json")
            )["scoped_allocation"],
            "historical_ceiling_seconds": 1076,
            "derived_stress_ceiling_seconds": 1054,
            "latest_historical_ceiling_seconds": 1050,
            "shards": rows,
        }
        return Plan(
            groups,
            dispatch,
            metadata,
            cast(dict[str, float], data["files"]),
            cast("list[ProfileEvidence]", data["profiles"]),
        )


def derive_summary(
    root: Path,
    directory: Path,
    durations: dict[str, float],
    cases: dict[str, float],
    profiles: tuple[ProfileEvidence, ...],
    count: int,
) -> tuple[dict[str, object], Plan]:
    from scripts import build_test_shards as sharding

    if count != 12:
        raise SystemExit("Runtime compatibility preserves twelve behavioral shards.")
    result = plan(root, directory, cases)
    if durations != result.files or list(profiles) != result.profiles:
        raise SystemExit("Current summary file costs or profiles differ from covered baseline.")
    shards = tuple(
        sharding.Shard(index, math.fsum(durations[name] for name in group), group)
        for index, group in enumerate(result.groups, 1)
    )
    payload = sharding._summary_payload(
        shards=shards,
        durations=durations,
        case_seconds=cases,
        profiles=profiles,
        planning_seconds=result.dispatch,
        calibration_sha256=hashlib.sha256((directory / FILENAME).read_bytes()).hexdigest(),
    )
    del payload["calibration"]
    payload["strategy"] = "reviewed-current-assignment-with-authenticated-historical-projection-v1"
    cast(dict[str, object], payload["execution_model"])["cold_shard_assignment"] = (
        "preserved-cold1-mirror2-pinned4-fixed5"
    )
    payload["runtime_compatibility"] = result.metadata
    return payload, result


def dispatch(root: Path, directory: Path, summary: dict[str, object]) -> dict[str, float]:
    from scripts import build_test_shards as sharding

    cases = sharding.summary_case_seconds(summary)
    expected, result = derive_summary(
        root,
        directory,
        sharding._summary_durations(
            summary=summary, expected=set(sharding._behavioral_shard_selectors())
        ),
        cases,
        sharding._summary_profiles(summary),
        12,
    )
    if summary != expected:
        raise SystemExit("Current scheduling compatibility summary is stale or altered.")
    return result.dispatch
