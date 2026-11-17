"""Finite admission of inactive exact contact queries and their fresh covered run."""

from __future__ import annotations

import json
from pathlib import Path

from scripts.historical_shard_snapshot import MANIFEST, fingerprint, git_bytes
from scripts.linux_authority_shard_admission import (
    archived_source_inputs,
    retained_native_inventory,
)

SCHEMA = "historical-snapshot-exact-contact-v1"
BASE = "4ad0a8e653959a8597f958286e1c5483fc058d87"
RUNTIME = "f0392def5f2e2935d26f026628b439e90f0f6303fb282ac41a27d1b575a7024e"
BASELINE_FILE = "exact-contact-covered-baseline.json"
EVIDENCE_FILE = "exact-contact-covered-evidence.json"
ASSIGNMENT_FILE = "exact-contact-derived-assignment.json"
MODULE = "src/warhammer40k_core/geometry/exact_contact.py"
MODULE_SHA256 = "b34603e9ba1a1a253b029e87c049bd8dfb182d93c39b89a5ce33813d2205647a"
COORDINATES = "src/warhammer40k_core/geometry/exact_coordinate.py"
COORDINATES_SHA256 = "b055e39a1dd733a17f3de952203b2163dff630bf26b2170d515aa0418a4277c0"
OWNER = "tests/rules/section01/test_exact_contact.py"
TEST_SHA256 = "c78a6eec8d4669b6b358a1230e6c5835e765c5b312060ebd5a631b5eb42b2d74"
NODES: frozenset[str] = frozenset(
    [
        "tests/rules/section01/test_exact_contact.py::test_exact_contact_irrational_and_simultaneous_contacts_have_full_segment_proofs",
        "tests/rules/section01/test_exact_contact.py::test_exact_contact_rational_tangency_and_once_rounded_approach_controls",
        "tests/rules/section01/test_exact_contact.py::test_exact_contact_rejects_endpoint_only_path_and_illegal_endpoint",
        "tests/rules/section01/test_exact_contact.py::test_exact_coordinate_mixed_fields_fail_closed_without_approximation",
        "tests/rules/section01/test_exact_contact.py::test_exact_coordinate_normalizes_equivalent_constructions_and_exact_arithmetic",
        "tests/rules/section01/test_exact_contact.py::test_exact_coordinate_rejects_noncanonical_malformed_and_unbounded_inputs",
        "tests/rules/section01/test_exact_contact.py::test_exact_coordinate_root_selection_sign_and_midpoint_measurement_are_exact",
        "tests/rules/section01/test_exact_contact.py::test_exact_disk_queries_validate_types_and_keep_topology_separate_from_rounding",
        "tests/rules/section01/test_exact_contact.py::test_exact_disk_restore_preserves_witness_identity_and_rejects_cross_profiles",
        "tests/rules/section01/test_exact_contact.py::test_rational_contact_constructor_handles_rational_roots_degeneracy_and_rotation",
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
        actual != protected | {MODULE, COORDINATES}
        or MODULE in previous
        or COORDINATES in previous
        or current[MODULE] != MODULE_SHA256
        or current[COORDINATES] != COORDINATES_SHA256
        or any(current[name] != previous[name] for name in protected - {MANIFEST})
    ):
        raise SystemExit(
            "Exact contact admission permits only the reviewed inactive runtime addition."
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
        or manifest["resource_count"] != old_manifest["resource_count"] + 2
        or manifest["resources"]
        != sorted(
            [
                *[
                    row
                    for row in old_manifest["resources"]
                    if row["path"] != COORDINATES.removeprefix("src/")
                ],
                {
                    "path": COORDINATES.removeprefix("src/"),
                    "byte_length": len((root / COORDINATES).read_bytes()),
                    "sha256": COORDINATES_SHA256,
                },
                added,
            ],
            key=lambda row: row["path"],
        )
    ):
        raise SystemExit(
            "Canonical exact contacts manifest is not the reviewed finite runtime transition."
        )


def producer_inputs(root: Path, producer: str) -> dict[str, str]:
    """Require an exact complete current Git producer, never source exceptions."""
    from tools.performance_policy import runtime_inputs

    validate_runtime_transition(root)
    if fingerprint(root, producer) != RUNTIME:
        raise SystemExit("Unreviewed canonical exact contacts measurement runtime.")
    inputs = archived_source_inputs(root, producer)
    if inputs != runtime_inputs(root):
        raise SystemExit("Exact contact complete producer inputs differ from current source.")
    return inputs


def retained_authority_artifacts(root: Path, directory: Path) -> None:
    """Preserve all predecessor profiles as original evidence, not live timing."""
    for name in (
        "canonical-polygon-pairs-covered-baseline.json",
        "canonical-polygon-pairs-covered-evidence.json",
        "canonical-polygon-pairs-derived-assignment.json",
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
            "Exact contact behavioral source inventory differs from its finite addition."
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
        raise SystemExit("Exact contact admission requires its actual runtime checkout.")
    rebuilt = build_identity.canonical_engine_build_manifest_text(
        build_identity.build_engine_manifest_payload()
    ).encode()
    if rebuilt != (root / MANIFEST).read_bytes():
        raise SystemExit("Canonical exact contacts live runtime source differs from its manifest.")
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
        raise SystemExit("Canonical exact contacts admission preserves twelve shards.")
    for index, group in enumerate(groups, 1):
        if [node for node in group if node != OWNER] != previous["shards"][str(index)]:
            raise SystemExit("Canonical exact contacts admission cannot move a retained selector.")
    if sum(group.count(OWNER) for group in groups) != 1:
        raise SystemExit("Canonical exact contacts selector must appear exactly once.")
