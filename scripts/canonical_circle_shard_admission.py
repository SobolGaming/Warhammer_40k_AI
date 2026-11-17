"""Finite admission of the inactive canonical circle measurements and its fresh covered run."""

from __future__ import annotations

import json
from pathlib import Path

from scripts.historical_shard_snapshot import MANIFEST, fingerprint, git_bytes
from scripts.linux_authority_shard_admission import (
    archived_source_inputs,
    retained_native_inventory,
)

SCHEMA = "historical-snapshot-canonical-circle-v1"
BASE = "20fe1ac0150a46ef5bedad6d42d8dd55f0c8e989"
RUNTIME = "9155e14c9c2ebf6932f47fff50f573bb7ee02b6573d76779ae538bedc8f33137"
BASELINE_FILE = "canonical-circle-covered-baseline.json"
EVIDENCE_FILE = "canonical-circle-covered-evidence.json"
ASSIGNMENT_FILE = "canonical-circle-derived-assignment.json"
MODULE = "src/warhammer40k_core/geometry/milli_inch_circle.py"
MODULE_SHA256 = "90c753b7d8ca9fdd03f52d17b7d59a758b2257a86a2610a0e527be43485192a4"
OWNER = "tests/rules/section01/test_milli_inch_circle.py"
TEST_SHA256 = "108a7edcaff877484ed35ffa21ac685b0b848703b7f65e8ef2fb00a620594194"
NODES: frozenset[str] = frozenset(
    [
        "tests/rules/section01/test_milli_inch_circle.py::test_circle_canonicalizes_signed_centers_and_full_diameter_once",
        "tests/rules/section01/test_milli_inch_circle.py::test_circle_gap_bin_certificates_cover_even_odd_diagonal_and_contained_disks",
        "tests/rules/section01/test_milli_inch_circle.py::test_circle_identity_binds_policy_version_center_and_full_diameter",
        "tests/rules/section01/test_milli_inch_circle.py::test_circle_mixed_parity_contact_remains_unrepresentable_on_integer_grid",
        "tests/rules/section01/test_milli_inch_circle.py::test_circle_payload_is_detached_strict_and_revalidated",
        "tests/rules/section01/test_milli_inch_circle.py::test_circle_rejects_invalid_and_collapsed_sources",
        "tests/rules/section01/test_milli_inch_circle.py::test_circle_rejects_malformed_canonical_values_and_queries",
        "tests/rules/section01/test_milli_inch_circle.py::test_circle_representation_bounds_preserve_json_and_exact_large_distances",
        "tests/rules/section01/test_milli_inch_circle.py::test_circle_rounded_zero_does_not_establish_contact_or_permit_overlap",
        "tests/rules/section01/test_milli_inch_circle.py::test_circle_surface_gap_rounds_half_ticks_once_and_preserves_scalar_operators",
        "tests/rules/section01/test_milli_inch_circle.py::test_circle_topology_distinguishes_external_contact_overlap_and_containment",
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
            "Canonical circle admission permits only the reviewed inactive runtime addition."
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
            "Canonical circle manifest is not the reviewed add-only runtime transition."
        )


def producer_inputs(root: Path, producer: str) -> dict[str, str]:
    """Require an exact complete current Git producer, never source exceptions."""
    from tools.performance_policy import runtime_inputs

    validate_runtime_transition(root)
    if fingerprint(root, producer) != RUNTIME:
        raise SystemExit("Unreviewed canonical circle measurement runtime.")
    inputs = archived_source_inputs(root, producer)
    if inputs != runtime_inputs(root):
        raise SystemExit("Canonical circle complete producer inputs differ from current source.")
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
        "canonical-polygon-covered-baseline.json",
        "canonical-polygon-covered-evidence.json",
        "canonical-polygon-derived-assignment.json",
    ):
        if (directory / name).read_bytes() != git_bytes(root, BASE, "ci/test_shards/" + name):
            raise SystemExit("Retained circle predecessor evidence changed.")


def require_test_sources(root: Path, sources: object) -> None:
    """Retain every old behavioral source and admit precisely the reviewed new file."""
    previous = json.loads(
        git_bytes(root, BASE, "ci/test_shards/canonical-polygon-covered-baseline.json")
    )
    if sources != {**previous["test_sources"], OWNER: TEST_SHA256}:
        raise SystemExit(
            "Canonical circle behavioral source inventory differs from its finite addition."
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
        raise SystemExit("Canonical circle admission requires its actual runtime checkout.")
    rebuilt = build_identity.canonical_engine_build_manifest_text(
        build_identity.build_engine_manifest_payload()
    ).encode()
    if rebuilt != (root / MANIFEST).read_bytes():
        raise SystemExit("Canonical circle live runtime source differs from its manifest.")
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
        git_bytes(root, BASE, "ci/test_shards/canonical-polygon-derived-assignment.json")
    )
    if len(groups) != 12:
        raise SystemExit("Canonical circle admission preserves twelve shards.")
    for index, group in enumerate(groups, 1):
        if [node for node in group if node != OWNER] != previous["shards"][str(index)]:
            raise SystemExit("Canonical circle admission cannot move a retained selector.")
    if sum(group.count(OWNER) for group in groups) != 1:
        raise SystemExit("Canonical circle selector must appear exactly once.")
