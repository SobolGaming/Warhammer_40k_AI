"""Finite admission of inactive polygon point queries and their fresh covered run."""

from __future__ import annotations

import json
from pathlib import Path

from scripts.historical_shard_snapshot import MANIFEST, fingerprint, git_bytes
from scripts.linux_authority_shard_admission import (
    archived_source_inputs,
    retained_native_inventory,
)

SCHEMA = "historical-snapshot-canonical-polygon-queries-v1"
BASE = "b7ca731c69ee702de1a726f661cc404177827835"
RUNTIME = "5ae984fe33c70e708ed920a2e06b228edbe9e042e79c322bdd9c84b196313d86"
BASELINE_FILE = "canonical-polygon-queries-covered-baseline.json"
EVIDENCE_FILE = "canonical-polygon-queries-covered-evidence.json"
ASSIGNMENT_FILE = "canonical-polygon-queries-derived-assignment.json"
MODULE = "src/warhammer40k_core/geometry/milli_inch_polygon_queries.py"
MODULE_SHA256 = "768c92d7942f430c6be5a1d820a45302b6f1f802ac02150da850f758c9f1126a"
OWNER = "tests/rules/section01/test_milli_inch_polygon_queries.py"
TEST_SHA256 = "2d3a04000d6c2c02e471d95fe97da22ef23ef58ee40fc7b6d50f7a10ec7dfe34"
NODES: frozenset[str] = frozenset(
    [
        "tests/rules/section01/test_milli_inch_polygon_queries.py::test_closed_filled_polygon_point_queries_cover_edges_vertices_and_interior",
        "tests/rules/section01/test_milli_inch_polygon_queries.py::test_concave_polygon_queries_count_vertex_crossings_once",
        "tests/rules/section01/test_milli_inch_polygon_queries.py::test_polygon_queries_preserve_translation_winding_start_and_collinear_vertices",
        "tests/rules/section01/test_milli_inch_polygon_queries.py::test_exterior_zero_distance_is_not_contact_and_projection_is_not_snapped",
        "tests/rules/section01/test_milli_inch_polygon_queries.py::test_polygon_distance_rounds_exact_squared_minimum_without_float_intermediate",
        "tests/rules/section01/test_milli_inch_polygon_queries.py::test_polygon_query_coordinate_extremes_use_unbounded_intermediate_arithmetic",
        "tests/rules/section01/test_milli_inch_polygon_queries.py::test_polygon_queries_reject_noncanonical_points_and_objects_with_typed_errors",
        "tests/rules/section01/test_milli_inch_polygon_queries.py::test_polygon_queries_preserve_payload_and_identity",
    ]
)


def validate_runtime_transition(root: Path) -> None:
    """Only the reviewed unimported helper may extend the authoritative runtime."""
    from tools.performance_policy import runtime_inputs

    previous = archived_source_inputs(root, BASE)
    current = runtime_inputs(root)
    protected = {
        name
        for name in previous
        if name.startswith(("src/", "contracts/schemas/")) or name in {"uv.lock", "pyproject.toml"}
    }
    actual = {
        name
        for name in current
        if name.startswith(("src/", "contracts/schemas/")) or name in {"uv.lock", "pyproject.toml"}
    }
    if (
        actual != protected | {MODULE}
        or MODULE in previous
        or current[MODULE] != MODULE_SHA256
        or any(current[name] != previous[name] for name in protected - {MANIFEST})
    ):
        raise SystemExit(
            "Polygon query admission permits only the reviewed inactive runtime addition."
        )
    old_manifest = json.loads(git_bytes(root, BASE, MANIFEST))
    manifest = json.loads((root / MANIFEST).read_bytes())
    added = {
        "path": MODULE.removeprefix("src/"),
        "byte_length": len((root / MODULE).read_bytes()),
        "sha256": MODULE_SHA256,
    }
    if (
        manifest["fingerprint"] != RUNTIME
        or manifest["schema_version"] != old_manifest["schema_version"]
        or manifest["algorithm"] != old_manifest["algorithm"]
        or manifest["resource_count"] != old_manifest["resource_count"] + 1
        or manifest["resources"]
        != sorted([*old_manifest["resources"], added], key=lambda row: row["path"])
    ):
        raise SystemExit(
            "Canonical polygon queries manifest is not the reviewed add-only runtime transition."
        )


def producer_inputs(root: Path, producer: str) -> dict[str, str]:
    """Require an exact complete current Git producer, never source exceptions."""
    from tools.performance_policy import runtime_inputs

    validate_runtime_transition(root)
    if fingerprint(root, producer) != RUNTIME:
        raise SystemExit("Unreviewed canonical polygon queries measurement runtime.")
    inputs = archived_source_inputs(root, producer)
    if inputs != runtime_inputs(root):
        raise SystemExit("Polygon query complete producer inputs differ from current source.")
    return inputs


def retained_authority_artifacts(root: Path, directory: Path) -> None:
    """Preserve all predecessor profiles as original evidence, not live timing."""
    for name in (
        "linux-authority-covered-baseline.json",
        "linux-authority-covered-evidence.json",
        "linux-authority-derived-assignment.json",
        "milli-inch-covered-baseline.json",
        "milli-inch-covered-evidence.json",
        "milli-inch-derived-assignment.json",
        "symbolic-milli-inch-covered-baseline.json",
        "precision-profile-covered-evidence.json",
        "precision-profile-covered-baseline.json",
        "precision-profile-derived-assignment.json",
        "symbolic-milli-inch-covered-evidence.json",
        "symbolic-milli-inch-derived-assignment.json",
        "canonical-circle-covered-baseline.json",
        "canonical-polygon-covered-evidence.json",
        "canonical-polygon-covered-baseline.json",
        "canonical-polygon-derived-assignment.json",
        "canonical-circle-covered-evidence.json",
        "canonical-circle-derived-assignment.json",
    ):
        if (directory / name).read_bytes() != git_bytes(root, BASE, "ci/test_shards/" + name):
            raise SystemExit("Retained circle predecessor evidence changed.")


def require_test_sources(root: Path, sources: object) -> None:
    """Retain every old behavioral source and admit precisely the reviewed new file."""
    previous = json.loads(
        git_bytes(root, BASE, "ci/test_shards/canonical-circle-covered-baseline.json")
    )
    if sources != {**previous["test_sources"], OWNER: TEST_SHA256}:
        raise SystemExit(
            "Polygon query behavioral source inventory differs from its finite addition."
        )


def current_native_role(
    root: Path,
    directory: Path,
    descriptor: dict[str, object],
    baseline: dict[str, object],
    expected_nodes: frozenset[str],
) -> tuple[float, dict[str, object]]:
    from scripts.complete_covered_evidence import verify_complete_covered_profile
    from warhammer40k_core import build_identity

    if Path(build_identity.__file__).resolve().parents[2] != root.resolve():
        raise SystemExit("Polygon query admission requires its actual runtime checkout.")
    rebuilt = build_identity.canonical_engine_build_manifest_text(
        build_identity.build_engine_manifest_payload()
    ).encode()
    if rebuilt != (root / MANIFEST).read_bytes():
        raise SystemExit("Canonical polygon queries live runtime source differs from its manifest.")
    retained_authority_artifacts(root, directory)
    require_test_sources(root, baseline["test_sources"])
    order, retained = retained_native_inventory(
        root, directory, descriptor["native_serial_role"], expected_nodes
    )
    inputs = producer_inputs(root, str(baseline["source_head"]))
    seconds = verify_complete_covered_profile(
        root,
        directory,
        descriptor["fresh_evidence"],
        baseline,
        inputs,
        order,
        filename=EVIDENCE_FILE,
    )
    return seconds, {
        "role": (
            "Fresh source-bound native phases after the mirror in the same covered serial worker"
        ),
        "cases": order,
        "worker_count": 1,
        "with_mirror_native_phase_seconds": seconds,
        "selected_current_context": "with_mirror",
        "standalone_role": "Not measured on this runtime; forbidden for current allocation",
        "retained_prior_observations": retained,
        "fresh_evidence": descriptor["fresh_evidence"],
        "fresh_source_head": baseline["source_head"],
        "fresh_runtime_fingerprint": RUNTIME,
    }


def require_frozen_assignment(root: Path, groups: tuple[tuple[str, ...], ...]) -> None:
    previous = json.loads(
        git_bytes(root, BASE, "ci/test_shards/canonical-circle-derived-assignment.json")
    )
    if len(groups) != 12:
        raise SystemExit("Canonical polygon queries admission preserves twelve shards.")
    for index, group in enumerate(groups, 1):
        if [node for node in group if node != OWNER] != previous["shards"][str(index)]:
            raise SystemExit("Canonical polygon queries admission cannot move a retained selector.")
    if sum(group.count(OWNER) for group in groups) != 1:
        raise SystemExit("Canonical polygon queries selector must appear exactly once.")
