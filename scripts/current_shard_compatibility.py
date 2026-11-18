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
SCHEMA = "historical-snapshot-current-baseline-v2"
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
        "test_named_ruleset_charge_completion_survives_persistence",
    )
)


ESCAPE_OWNER = "tests/rules/section09/test_escape_survivor_persistence.py"
NEW_NODES |= frozenset(
    f"{ESCAPE_OWNER}::{case}"
    for case in (
        "test_natural_escape_survivor_checkpoint_roundtrips[partial]",
        "test_natural_escape_survivor_checkpoint_roundtrips[complete]",
        "test_survivor_authority_rejects_missing_survivor",
        "test_survivor_authority_rejects_unrelated_hazard",
        "test_completed_hazard_survivor_retry_roundtrips_without_rerolls",
        "test_pre_hazard_rejected_proposal_then_survivor_retry_roundtrips",
    )
)


NATIVE_PREFIX_OWNER = (
    "tests/factions/chaos_daemons/integration/test_cavalcade_native_screen_prefix.py"
)
NEW_NODES |= frozenset(
    f"{NATIVE_PREFIX_OWNER}::{case}"
    for case in (
        "test_native_roles_keep_complete_equipment_in_full_legal_rosters[cavalcade-a:nurglings-3-weapons0]",
        "test_native_roles_keep_complete_equipment_in_full_legal_rosters[cavalcade-b:bloodcrushers-1-6-weapons1]",
        "test_native_roles_keep_complete_equipment_in_full_legal_rosters[cavalcade-a:lord-of-change-1-1-weapons2]",
        "test_native_prefix_preserves_real_rules_terrain_and_exact_history[ranged-sidestep]",
        "test_native_prefix_preserves_real_rules_terrain_and_exact_history[blocked-screen]",
        "test_native_prefix_preserves_real_rules_terrain_and_exact_history[blocked-ranged]",
    )
)


def enabled(directory: Path, summary: dict[str, object] | None = None) -> bool:
    from scripts.canonical_circle_shard_admission import BASELINE_FILE as CIRCLE_BASELINE_FILE
    from scripts.canonical_polygon_pairs_shard_admission import BASELINE_FILE as PAIRS_BASELINE_FILE
    from scripts.canonical_polygon_queries_shard_admission import (
        BASELINE_FILE as QUERIES_BASELINE_FILE,
    )
    from scripts.canonical_polygon_shard_admission import BASELINE_FILE as POLYGON_BASELINE_FILE
    from scripts.exact_contact_shard_admission import BASELINE_FILE as CONTACT_BASELINE_FILE
    from scripts.linux_authority_shard_admission import BASELINE_FILE as AUTHORITY_BASELINE_FILE
    from scripts.milli_inch_shard_admission import BASELINE_FILE as MILLI_BASELINE_FILE
    from scripts.precision_profile_shard_admission import BASELINE_FILE as PROFILE_BASELINE_FILE
    from scripts.symbolic_milli_inch_shard_admission import BASELINE_FILE as SYMBOLIC_BASELINE_FILE

    declared = (directory / FILENAME).is_file()
    if not declared and (
        (directory / BASELINE_FILE).is_file()
        or (directory / AUTHORITY_BASELINE_FILE).is_file()
        or (directory / MILLI_BASELINE_FILE).is_file()
        or (directory / PROFILE_BASELINE_FILE).is_file()
        or (directory / SYMBOLIC_BASELINE_FILE).is_file()
        or (directory / POLYGON_BASELINE_FILE).is_file()
        or (directory / CIRCLE_BASELINE_FILE).is_file()
        or (directory / QUERIES_BASELINE_FILE).is_file()
        or (directory / PAIRS_BASELINE_FILE).is_file()
        or (directory / CONTACT_BASELINE_FILE).is_file()
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
    from scripts.canonical_circle_shard_admission import BASELINE_FILE as CIRCLE_BASELINE_FILE
    from scripts.canonical_circle_shard_admission import NODES as CIRCLE_NODES
    from scripts.canonical_circle_shard_admission import OWNER as CIRCLE_OWNER
    from scripts.canonical_circle_shard_admission import SCHEMA as CIRCLE_SCHEMA
    from scripts.canonical_polygon_pairs_shard_admission import BASELINE_FILE as PAIRS_BASELINE_FILE
    from scripts.canonical_polygon_pairs_shard_admission import NODES as PAIRS_NODES
    from scripts.canonical_polygon_pairs_shard_admission import OWNER as PAIRS_OWNER
    from scripts.canonical_polygon_pairs_shard_admission import SCHEMA as PAIRS_SCHEMA
    from scripts.canonical_polygon_queries_shard_admission import (
        BASELINE_FILE as QUERIES_BASELINE_FILE,
    )
    from scripts.canonical_polygon_queries_shard_admission import NODES as QUERIES_NODES
    from scripts.canonical_polygon_queries_shard_admission import OWNER as QUERIES_OWNER
    from scripts.canonical_polygon_queries_shard_admission import SCHEMA as QUERIES_SCHEMA
    from scripts.canonical_polygon_shard_admission import BASELINE_FILE as POLYGON_BASELINE_FILE
    from scripts.canonical_polygon_shard_admission import NODES as POLYGON_NODES
    from scripts.canonical_polygon_shard_admission import OWNER as POLYGON_OWNER
    from scripts.canonical_polygon_shard_admission import SCHEMA as POLYGON_SCHEMA
    from scripts.exact_contact_shard_admission import BASELINE_FILE as CONTACT_BASELINE_FILE
    from scripts.exact_contact_shard_admission import NODES as CONTACT_NODES
    from scripts.exact_contact_shard_admission import OWNER as CONTACT_OWNER
    from scripts.exact_contact_shard_admission import SCHEMA as CONTACT_SCHEMA
    from scripts.linux_authority_shard_admission import (
        BASELINE_FILE as AUTHORITY_BASELINE_FILE,
    )
    from scripts.linux_authority_shard_admission import (
        NODES as AUTHORITY_NODES,
    )
    from scripts.linux_authority_shard_admission import (
        OWNER as AUTHORITY_OWNER,
    )
    from scripts.linux_authority_shard_admission import (
        SCHEMA as AUTHORITY_SCHEMA,
    )
    from scripts.linux_authority_shard_admission import (
        retained_test_transition,
    )
    from scripts.milli_inch_shard_admission import BASELINE_FILE as MILLI_BASELINE_FILE
    from scripts.milli_inch_shard_admission import NODES as MILLI_NODES
    from scripts.milli_inch_shard_admission import OWNER as MILLI_OWNER
    from scripts.milli_inch_shard_admission import SCHEMA as MILLI_SCHEMA
    from scripts.precision_profile_shard_admission import BASELINE_FILE as PROFILE_BASELINE_FILE
    from scripts.precision_profile_shard_admission import NODES as PROFILE_NODES
    from scripts.precision_profile_shard_admission import OWNER as PROFILE_OWNER
    from scripts.precision_profile_shard_admission import SCHEMA as PROFILE_SCHEMA
    from scripts.symbolic_milli_inch_shard_admission import BASELINE_FILE as SYMBOLIC_BASELINE_FILE
    from scripts.symbolic_milli_inch_shard_admission import NODES as SYMBOLIC_NODES
    from scripts.symbolic_milli_inch_shard_admission import OWNER as SYMBOLIC_OWNER
    from scripts.symbolic_milli_inch_shard_admission import SCHEMA as SYMBOLIC_SCHEMA

    contact = descriptor["schema"] == CONTACT_SCHEMA
    pairs = descriptor["schema"] in {PAIRS_SCHEMA, CONTACT_SCHEMA}
    queries = descriptor["schema"] in {QUERIES_SCHEMA, PAIRS_SCHEMA, CONTACT_SCHEMA}
    circle = descriptor["schema"] in {CIRCLE_SCHEMA, QUERIES_SCHEMA, PAIRS_SCHEMA, CONTACT_SCHEMA}
    polygon = descriptor["schema"] in {
        POLYGON_SCHEMA,
        CIRCLE_SCHEMA,
        QUERIES_SCHEMA,
        PAIRS_SCHEMA,
        CONTACT_SCHEMA,
    }
    symbolic = descriptor["schema"] in {
        SYMBOLIC_SCHEMA,
        POLYGON_SCHEMA,
        CIRCLE_SCHEMA,
        QUERIES_SCHEMA,
        PAIRS_SCHEMA,
        CONTACT_SCHEMA,
    }
    profile = descriptor["schema"] in {
        PROFILE_SCHEMA,
        SYMBOLIC_SCHEMA,
        POLYGON_SCHEMA,
        CIRCLE_SCHEMA,
        QUERIES_SCHEMA,
        PAIRS_SCHEMA,
        CONTACT_SCHEMA,
    }
    milli = descriptor["schema"] in {
        MILLI_SCHEMA,
        PROFILE_SCHEMA,
        SYMBOLIC_SCHEMA,
        POLYGON_SCHEMA,
        CIRCLE_SCHEMA,
        QUERIES_SCHEMA,
        PAIRS_SCHEMA,
        CONTACT_SCHEMA,
    }
    authority = descriptor["schema"] in {
        AUTHORITY_SCHEMA,
        MILLI_SCHEMA,
        PROFILE_SCHEMA,
        SYMBOLIC_SCHEMA,
        POLYGON_SCHEMA,
        CIRCLE_SCHEMA,
        QUERIES_SCHEMA,
        PAIRS_SCHEMA,
        CONTACT_SCHEMA,
    }
    filename = (
        CONTACT_BASELINE_FILE
        if contact
        else PAIRS_BASELINE_FILE
        if pairs
        else QUERIES_BASELINE_FILE
        if queries
        else CIRCLE_BASELINE_FILE
        if circle
        else POLYGON_BASELINE_FILE
        if polygon
        else SYMBOLIC_BASELINE_FILE
        if symbolic
        else PROFILE_BASELINE_FILE
        if profile
        else MILLI_BASELINE_FILE
        if milli
        else (AUTHORITY_BASELINE_FILE if authority else BASELINE_FILE)
    )
    reference = _object(descriptor["baseline"], {"file", "sha256"}, "current baseline reference")
    path = directory / filename
    if (
        reference["file"] != filename
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
    expected_additions = NEW_NODES | (AUTHORITY_NODES if authority else frozenset())
    expected_owners = {NEW_OWNER, CONNECTED_OWNER, ESCAPE_OWNER, NATIVE_PREFIX_OWNER}
    if authority:
        expected_owners.add(AUTHORITY_OWNER)
    if milli:
        expected_additions |= MILLI_NODES
        expected_owners.add(MILLI_OWNER)
    if profile:
        expected_additions |= PROFILE_NODES
        expected_owners.add(PROFILE_OWNER)
    if symbolic:
        expected_additions |= SYMBOLIC_NODES
        expected_owners.add(SYMBOLIC_OWNER)
    if circle:
        expected_additions |= CIRCLE_NODES
        expected_owners.add(CIRCLE_OWNER)
    if contact:
        expected_additions |= CONTACT_NODES
        expected_owners.add(CONTACT_OWNER)
    if pairs:
        expected_additions |= PAIRS_NODES
        expected_owners.add(PAIRS_OWNER)
    if queries:
        expected_additions |= QUERIES_NODES
        expected_owners.add(QUERIES_OWNER)
    if polygon:
        expected_additions |= POLYGON_NODES
        expected_owners.add(POLYGON_OWNER)
    if (
        cases.keys() != history.baseline.keys() | expected_additions
        or not history.baseline.keys() < cases.keys()
        or len(cases) - len(history.baseline) != len(expected_additions)
        or set(additions) != expected_owners
        or set(additions) & {node.split("::", 1)[0] for node in history.baseline}
    ):
        raise SystemExit("Compatibility requires exactly the reviewed added cases for its profile.")
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
            from scripts.boolean_los_admission import SCHEMA as BOOLEAN_SCHEMA
            from scripts.boolean_los_admission import transitioned_test
            from scripts.precision_profile_shard_admission import (
                transitioned_test as profile_transitioned_test,
            )

            accepted = profile and profile_transitioned_test(
                root, owner, current, (history.root / owner).read_bytes()
            )
            accepted = accepted or (
                retained_test_transition(root, owner, current, (history.root / owner).read_bytes())
                if authority
                else descriptor["schema"] == BOOLEAN_SCHEMA
                and transitioned_test(root, owner, current, (history.root / owner).read_bytes())
            )
            if not accepted:
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
    native_serial_seconds: float | None = None,
    native_with_mirror_seconds: float | None = None,
) -> float:
    from scripts.build_test_shards import SERIAL_BEHAVIORAL_CASE

    native = NATIVE_PREFIX_OWNER in group
    chunks = worker_chunks(tuple(name for name in group if name != NATIVE_PREFIX_OWNER), dispatch)
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
    if native:
        selected_seconds = native_with_mirror_seconds if mirror else native_serial_seconds
        if selected_seconds is None:
            raise SystemExit(
                "Native serial scheduling requires its complete role observation for this context."
            )
        serial += _seconds(selected_seconds)
    if mirror and SERIAL_BEHAVIORAL_CASE in historical.groups:
        serial += historical.setup[historical.groups[SERIAL_BEHAVIORAL_CASE]]
    residual = historical.mirror_residual if mirror else historical.parallel_residual
    if native and not mirror:
        residual = max(historical.parallel_residual, historical.mirror_residual)
    return max(workers) + serial + residual


@dataclass(frozen=True)
class Plan:
    groups: tuple[tuple[str, ...], ...]
    dispatch: dict[str, float]
    metadata: dict[str, object]
    files: dict[str, float]
    profiles: list[ProfileEvidence]


def plan(root: Path, directory: Path, cases: dict[str, float]) -> Plan:
    from scripts.boolean_los_admission import SCHEMA as BOOLEAN_SCHEMA
    from scripts.canonical_circle_shard_admission import SCHEMA as CIRCLE_SCHEMA
    from scripts.canonical_polygon_pairs_shard_admission import SCHEMA as PAIRS_SCHEMA
    from scripts.canonical_polygon_queries_shard_admission import SCHEMA as QUERIES_SCHEMA
    from scripts.canonical_polygon_shard_admission import SCHEMA as POLYGON_SCHEMA
    from scripts.exact_contact_shard_admission import SCHEMA as CONTACT_SCHEMA
    from scripts.extended_shard_allocation import partial_projection
    from scripts.linux_authority_shard_admission import SCHEMA as AUTHORITY_SCHEMA
    from scripts.milli_inch_shard_admission import SCHEMA as MILLI_SCHEMA
    from scripts.precision_profile_shard_admission import SCHEMA as PROFILE_SCHEMA
    from scripts.symbolic_milli_inch_shard_admission import SCHEMA as SYMBOLIC_SCHEMA

    declared = read_json(directory / FILENAME)
    fresh = isinstance(declared, dict) and declared.get("schema") == BOOLEAN_SCHEMA
    authority = isinstance(declared, dict) and declared.get("schema") == AUTHORITY_SCHEMA
    milli = isinstance(declared, dict) and declared.get("schema") == MILLI_SCHEMA
    profile = isinstance(declared, dict) and declared.get("schema") == PROFILE_SCHEMA
    symbolic = isinstance(declared, dict) and declared.get("schema") == SYMBOLIC_SCHEMA
    circle = isinstance(declared, dict) and declared.get("schema") == CIRCLE_SCHEMA
    contact = isinstance(declared, dict) and declared.get("schema") == CONTACT_SCHEMA
    pairs = isinstance(declared, dict) and declared.get("schema") == PAIRS_SCHEMA
    queries = isinstance(declared, dict) and declared.get("schema") == QUERIES_SCHEMA
    polygon = isinstance(declared, dict) and declared.get("schema") == POLYGON_SCHEMA

    descriptor = _object(
        declared,
        {
            "schema",
            "historical_revision",
            "current_runtime_fingerprint",
            "baseline",
            "new_test_sources",
            "assignment",
            "native_serial_role",
            "planning_policy",
        }
        | (
            {"fresh_evidence"}
            if fresh
            or authority
            or milli
            or profile
            or symbolic
            or polygon
            or circle
            or queries
            or pairs
            or contact
            else set()
        ),
        "runtime compatibility",
    )
    from scripts.current_shard_assignment import current_planning_policy

    if (
        descriptor["schema"]
        not in {
            SCHEMA,
            BOOLEAN_SCHEMA,
            AUTHORITY_SCHEMA,
            MILLI_SCHEMA,
            PROFILE_SCHEMA,
            SYMBOLIC_SCHEMA,
            POLYGON_SCHEMA,
            CIRCLE_SCHEMA,
            QUERIES_SCHEMA,
            PAIRS_SCHEMA,
            CONTACT_SCHEMA,
        }
        or descriptor["historical_revision"] != HISTORICAL_REVISION
    ):
        raise SystemExit("Unreviewed scheduling compatibility boundary.")
    if descriptor["planning_policy"] != current_planning_policy():
        raise SystemExit("Unreviewed current planning policy.")
    with historical_snapshot(root) as history:
        unchanged_historical_files(directory, history)
        data = _baseline(root, directory, descriptor, history)
        if data["case_seconds"] != cases:
            raise SystemExit(
                "Current scheduling baseline differs from the complete covered evidence."
            )
        from scripts.current_native_serial_role import load_native_serial_role

        expected_native = frozenset(
            node for node in NEW_NODES if node.startswith(NATIVE_PREFIX_OWNER + "::")
        )
        if contact:
            from scripts.current_native_serial_role import NativeSerialRole
            from scripts.exact_contact_shard_admission import current_native_role as contact_role

            seconds, native_metadata = contact_role(
                root, directory, descriptor, data, expected_native
            )
            native_role = NativeSerialRole(None, seconds, native_metadata)
        elif pairs:
            from scripts.canonical_polygon_pairs_shard_admission import (
                current_native_role as pairs_role,
            )
            from scripts.current_native_serial_role import NativeSerialRole

            seconds, native_metadata = pairs_role(
                root, directory, descriptor, data, expected_native
            )
            native_role = NativeSerialRole(None, seconds, native_metadata)
        elif queries:
            from scripts.canonical_polygon_queries_shard_admission import (
                current_native_role as queries_role,
            )
            from scripts.current_native_serial_role import NativeSerialRole

            seconds, native_metadata = queries_role(
                root, directory, descriptor, data, expected_native
            )
            native_role = NativeSerialRole(None, seconds, native_metadata)
        elif circle:
            from scripts.canonical_circle_shard_admission import (
                current_native_role as circle_role,
            )
            from scripts.current_native_serial_role import NativeSerialRole

            seconds, native_metadata = circle_role(
                root, directory, descriptor, data, expected_native
            )
            native_role = NativeSerialRole(None, seconds, native_metadata)
        elif polygon:
            from scripts.canonical_polygon_shard_admission import (
                current_native_role as polygon_role,
            )
            from scripts.current_native_serial_role import NativeSerialRole

            seconds, native_metadata = polygon_role(
                root, directory, descriptor, data, expected_native
            )
            native_role = NativeSerialRole(None, seconds, native_metadata)
        elif symbolic:
            from scripts.current_native_serial_role import NativeSerialRole
            from scripts.symbolic_milli_inch_shard_admission import (
                current_native_role as symbolic_role,
            )

            seconds, native_metadata = symbolic_role(
                root, directory, descriptor, data, expected_native
            )
            native_role = NativeSerialRole(None, seconds, native_metadata)
        elif profile:
            from scripts.current_native_serial_role import NativeSerialRole
            from scripts.precision_profile_shard_admission import (
                current_native_role as profile_role,
            )

            seconds, native_metadata = profile_role(
                root, directory, descriptor, data, expected_native
            )
            native_role = NativeSerialRole(None, seconds, native_metadata)
        elif milli:
            from scripts.current_native_serial_role import NativeSerialRole
            from scripts.milli_inch_shard_admission import current_native_role as milli_native_role

            seconds, native_metadata = milli_native_role(
                root, directory, descriptor, data, expected_native
            )
            native_role = NativeSerialRole(None, seconds, native_metadata)
        elif authority:
            from scripts.current_native_serial_role import NativeSerialRole
            from scripts.linux_authority_shard_admission import current_native_role

            seconds, native_metadata = current_native_role(
                root, directory, descriptor, data, expected_native
            )
            native_role = NativeSerialRole(None, seconds, native_metadata)
        else:
            native_role = load_native_serial_role(
                root, directory, descriptor["native_serial_role"], expected_native
            )
        if fresh:
            from scripts.boolean_los_admission import fresh_native_role
            from scripts.current_native_serial_role import NativeSerialRole

            seconds, native_metadata = fresh_native_role(
                root, directory, descriptor, data, native_role.metadata
            )
            native_role = NativeSerialRole(native_role.seconds, seconds, native_metadata)
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
                    derived_score(
                        group,
                        dispatch,
                        current,
                        cohort,
                        native_serial_seconds=native_role.seconds,
                        native_with_mirror_seconds=native_role.with_mirror_seconds,
                    )
                    for cohort in history.cohorts[:-1]
                ),
                derived_score(
                    group,
                    dispatch,
                    current,
                    extension.stress,
                    unknown=extension.unknown_node,
                    native_serial_seconds=native_role.seconds,
                    native_with_mirror_seconds=native_role.with_mirror_seconds,
                ),
                derived_score(
                    group,
                    dispatch,
                    current,
                    history.cohorts[-1],
                    native_serial_seconds=native_role.seconds,
                    native_with_mirror_seconds=native_role.with_mirror_seconds,
                ),
            )

        from scripts.current_shard_assignment import load_assignment, require_planning_limits

        groups, assignment = load_assignment(directory, descriptor, history)
        if contact:
            from scripts.exact_contact_shard_admission import (
                require_frozen_assignment as require_contact_assignment,
            )

            require_contact_assignment(root, groups)
        if pairs:
            from scripts.canonical_polygon_pairs_shard_admission import (
                require_frozen_assignment as require_pairs_assignment,
            )

            require_pairs_assignment(root, groups)
        if queries:
            from scripts.canonical_polygon_queries_shard_admission import (
                require_frozen_assignment as require_queries_assignment,
            )

            require_queries_assignment(root, groups)
        if circle:
            from scripts.canonical_circle_shard_admission import (
                require_frozen_assignment as require_circle_assignment,
            )

            require_circle_assignment(root, groups)
        if polygon:
            from scripts.canonical_polygon_shard_admission import (
                require_frozen_assignment as require_polygon_assignment,
            )

            require_polygon_assignment(root, groups)
        if symbolic:
            from scripts.symbolic_milli_inch_shard_admission import (
                require_frozen_assignment as require_symbolic_assignment,
            )

            require_symbolic_assignment(root, groups)
        if profile:
            from scripts.precision_profile_shard_admission import (
                require_frozen_assignment as require_profile_assignment,
            )

            require_profile_assignment(root, groups)
        if milli:
            from scripts.milli_inch_shard_admission import (
                require_frozen_assignment as require_milli_assignment,
            )

            require_milli_assignment(root, groups)
        if authority:
            from scripts.linux_authority_shard_admission import require_frozen_assignment

            require_frozen_assignment(root, groups)
        if fresh:
            from scripts.boolean_los_admission import BASE
            from scripts.build_test_shards import SERIAL_BEHAVIORAL_CASE
            from scripts.historical_shard_snapshot import git_bytes

            original = json.loads(
                git_bytes(root, BASE, "ci/test_shards/current-derived-assignment.json")
            )
            if assignment["shards"] != original["shards"] or not any(
                NATIVE_PREFIX_OWNER in group and SERIAL_BEHAVIORAL_CASE in group for group in groups
            ):
                raise SystemExit("Boolean LOS admission preserves the frozen combined allocation.")
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
            "schema": descriptor["schema"],
            "role": ROLE,
            "historical_revision": HISTORICAL_REVISION,
            "current_runtime_fingerprint": descriptor["current_runtime_fingerprint"],
            "baseline": descriptor["baseline"],
            "native_serial_role": native_role.metadata,
            "current_planning_policy": current_planning_policy(),
            "derived_score_role": (
                "Historical cohort projection plus unchanged current additions and separately "
                "measured local native serial role; not observed hosted execution"
            ),
            "partial_raw_role": (
                "Retained historical worker-chunk projection; not the current native "
                "serial controller topology"
            ),
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
            "retained_historical_planning_ceilings_seconds": [1076] * 8 + [1054, 1050],
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
    execution = cast(dict[str, object], payload["execution_model"])
    native = cast(dict[str, object], result.metadata["native_serial_role"])
    serial_case = sharding.SERIAL_BEHAVIORAL_CASE
    native_group = next(group for group in result.groups if NATIVE_PREFIX_OWNER in group)
    native_context = "with_mirror" if serial_case in native_group else "standalone"
    native_seconds = cast(float, native[native_context + "_native_phase_seconds"])
    selector_costs = cast(dict[str, float], payload["planning_selector_seconds"])
    peaks = sharding._selector_case_peaks(selector_costs, result.dispatch)
    serial_costs = {serial_case: result.dispatch[serial_case], NATIVE_PREFIX_OWNER: native_seconds}
    execution["serial_cases"] = [serial_case, *cast(list[str], native["cases"])]
    execution["serial_selectors"] = [serial_case, NATIVE_PREFIX_OWNER]
    execution["native_serial_role"] = native
    execution["native_selected_context"] = native_context
    execution["native_selected_phase_seconds"] = native_seconds
    execution["shard_worker_seconds"] = {
        str(index): round(
            math.fsum(
                4 * serial_costs[name] if name in serial_costs else selector_costs[name]
                for name in group
            ),
            3,
        )
        for index, group in enumerate(result.groups, 1)
    }
    del execution["assignment_wall_lower_bound_seconds"]
    execution["assignment_wall_planning_estimate_seconds"] = {
        str(index): round(
            math.fsum(serial_costs[name] for name in group if name in serial_costs)
            + max(
                math.fsum(selector_costs[name] for name in group if name not in serial_costs) / 4,
                max((peaks[name] for name in group if name not in serial_costs), default=0.0),
            ),
            3,
        )
        for index, group in enumerate(result.groups, 1)
    }
    execution["estimate_role"] = (
        "Hybrid scheduling estimate, not a physical lower bound, hosted observation "
        "or timing qualification"
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
