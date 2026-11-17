"""Finite admission of inactive polygon pair queries and their fresh covered run."""

from __future__ import annotations

import json
from pathlib import Path

from scripts.historical_shard_snapshot import MANIFEST, fingerprint, git_bytes
from scripts.linux_authority_shard_admission import (
    archived_source_inputs,
    retained_native_inventory,
)

SCHEMA = "historical-snapshot-canonical-polygon-pairs-v1"
BASE = "dd10b801673296efe1f8122a2cf0f86b4c4df7b9"
RUNTIME = "1f19514910b3cb312aa6561567af9e725f9220d872c89c2710e7df9bd14e2cfb"
BASELINE_FILE = "canonical-polygon-pairs-covered-baseline.json"
EVIDENCE_FILE = "canonical-polygon-pairs-covered-evidence.json"
ASSIGNMENT_FILE = "canonical-polygon-pairs-derived-assignment.json"
MODULE = "src/warhammer40k_core/geometry/milli_inch_polygon_pairs.py"
MODULE_SHA256 = "017deaaed1a2ccbc07888c4719de3815757164e1483275456e8fd585463d88a1"
QUERIES = "src/warhammer40k_core/geometry/milli_inch_polygon_queries.py"
QUERIES_SHA256 = "e46fe8e9738786931c565c5ea5a2dc2921132e3690b420632bfcb8a00c362cc5"
OWNER = "tests/rules/section01/test_milli_inch_polygon_pairs.py"
TEST_SHA256 = "1ba7d2c874dd479a62ac393dc5c08f35f21d589fc77f5dd1e8292ef9452b67f8"
NODES: frozenset[str] = frozenset(
    [
        "tests/rules/section01/test_milli_inch_polygon_pairs.py::test_polygon_pair_boundary_vertices_do_not_hide_interior_overlap",
        "tests/rules/section01/test_milli_inch_polygon_pairs.py::test_polygon_pair_distance_uses_exact_minimum_and_squared_rounding",
        "tests/rules/section01/test_milli_inch_polygon_pairs.py::test_polygon_pair_queries_reject_noncanonical_inputs",
        "tests/rules/section01/test_milli_inch_polygon_pairs.py::test_polygon_pair_zero_rounded_gap_does_not_establish_contact",
        "tests/rules/section01/test_milli_inch_polygon_pairs.py::test_polygon_pairs_classify_shared_edges_by_interior_side",
        "tests/rules/section01/test_milli_inch_polygon_pairs.py::test_polygon_pairs_coordinate_extremes_keep_unbounded_derived_lengths",
        "tests/rules/section01/test_milli_inch_polygon_pairs.py::test_polygon_pairs_distinguish_separation_contact_and_overlap",
        "tests/rules/section01/test_milli_inch_polygon_pairs.py::test_polygon_pairs_handle_concavity_t_junctions_and_split_boundary_edges",
        "tests/rules/section01/test_milli_inch_polygon_pairs.py::test_polygon_pairs_preserve_translation_ring_order_payload_and_hash",
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
        or current[QUERIES] != QUERIES_SHA256
        or any(current[name] != previous[name] for name in protected - {MANIFEST, QUERIES})
    ):
        raise SystemExit(
            "Polygon pair admission permits only the reviewed inactive runtime addition."
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
        != sorted(
            [
                *[
                    row
                    for row in old_manifest["resources"]
                    if row["path"] != QUERIES.removeprefix("src/")
                ],
                {
                    "path": QUERIES.removeprefix("src/"),
                    "byte_length": len((root / QUERIES).read_bytes()),
                    "sha256": QUERIES_SHA256,
                },
                added,
            ],
            key=lambda row: row["path"],
        )
    ):
        raise SystemExit(
            "Canonical polygon pairs manifest is not the reviewed finite runtime transition."
        )


def producer_inputs(root: Path, producer: str) -> dict[str, str]:
    """Require an exact complete current Git producer, never source exceptions."""
    from tools.performance_policy import runtime_inputs

    validate_runtime_transition(root)
    if fingerprint(root, producer) != RUNTIME:
        raise SystemExit("Unreviewed canonical polygon pairs measurement runtime.")
    inputs = archived_source_inputs(root, producer)
    if inputs != runtime_inputs(root):
        raise SystemExit("Polygon pair complete producer inputs differ from current source.")
    return inputs


def retained_authority_artifacts(root: Path, directory: Path) -> None:
    """Preserve all predecessor profiles as original evidence, not live timing."""
    for name in (
        "canonical-polygon-queries-covered-baseline.json",
        "canonical-polygon-queries-covered-evidence.json",
        "canonical-polygon-queries-derived-assignment.json",
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
        git_bytes(root, BASE, "ci/test_shards/canonical-polygon-queries-covered-baseline.json")
    )
    if sources != {**previous["test_sources"], OWNER: TEST_SHA256}:
        raise SystemExit(
            "Polygon pair behavioral source inventory differs from its finite addition."
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
        raise SystemExit("Polygon pair admission requires its actual runtime checkout.")
    rebuilt = build_identity.canonical_engine_build_manifest_text(
        build_identity.build_engine_manifest_payload()
    ).encode()
    if rebuilt != (root / MANIFEST).read_bytes():
        raise SystemExit("Canonical polygon pairs live runtime source differs from its manifest.")
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
        git_bytes(root, BASE, "ci/test_shards/canonical-polygon-queries-derived-assignment.json")
    )
    if len(groups) != 12:
        raise SystemExit("Canonical polygon pairs admission preserves twelve shards.")
    for index, group in enumerate(groups, 1):
        if [node for node in group if node != OWNER] != previous["shards"][str(index)]:
            raise SystemExit("Canonical polygon pairs admission cannot move a retained selector.")
    if sum(group.count(OWNER) for group in groups) != 1:
        raise SystemExit("Canonical polygon pairs selector must appear exactly once.")
