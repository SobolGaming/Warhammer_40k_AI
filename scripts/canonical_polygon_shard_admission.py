"""Finite admission of the inactive canonical polygon measurements and its fresh covered run."""

from __future__ import annotations

import json
from pathlib import Path

from scripts.historical_shard_snapshot import MANIFEST, fingerprint, git_bytes
from scripts.linux_authority_shard_admission import (
    archived_source_inputs,
    retained_native_inventory,
)

SCHEMA = "historical-snapshot-canonical-polygon-v1"
BASE = "99dcf4adb983a0f968c536b16e9d960182e63afe"
RUNTIME = "1741e3c9547f667ce281f6ad970a8c064bfcf1c49d992cff34219e03c8f30c1d"
BASELINE_FILE = "canonical-polygon-covered-baseline.json"
EVIDENCE_FILE = "canonical-polygon-covered-evidence.json"
ASSIGNMENT_FILE = "canonical-polygon-derived-assignment.json"
MODULE = "src/warhammer40k_core/geometry/milli_inch_polygon.py"
MODULE_SHA256 = "049b1f46183933069dc27ce14db4e84e910ebdb13dcfbbdf945dcd64fb8ac80d"
OWNER = "tests/rules/section01/test_milli_inch_polygon.py"
TEST_SHA256 = "b36418144aa411b9a39797d191058430d9c8bba3e4e3d5a6dd3ce6f093ea6ee0"
NODES: frozenset[str] = frozenset(
    [
        "tests/rules/section01/test_milli_inch_polygon.py::test_canonical_ring_coordinate_bounds_guarantee_json_identity",
        "tests/rules/section01/test_milli_inch_polygon.py::test_canonical_ring_exact_units_decimal_context_and_float_interpretation",
        "tests/rules/section01/test_milli_inch_polygon.py::test_canonical_ring_identity_binds_policy_version_winding_and_start",
        "tests/rules/section01/test_milli_inch_polygon.py::test_canonical_ring_payload_is_detached_strict_and_revalidates_topology",
        "tests/rules/section01/test_milli_inch_polygon.py::test_canonical_ring_rejects_invalid_sources_before_snapping_can_repair_them",
        "tests/rules/section01/test_milli_inch_polygon.py::test_canonical_ring_rejects_quantization_collapse_and_new_edge_contacts",
        "tests/rules/section01/test_milli_inch_polygon.py::test_canonical_ring_rounds_signed_sources_once_and_preserves_order",
        "tests/rules/section01/test_milli_inch_polygon.py::test_canonical_ring_topology_has_no_distance_or_coordinate_tolerance",
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
            "Canonical polygon admission permits only the reviewed inactive runtime addition."
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
            "Canonical polygon manifest is not the reviewed add-only runtime transition."
        )


def producer_inputs(root: Path, producer: str) -> dict[str, str]:
    """Require an exact complete current Git producer, never source exceptions."""
    from tools.performance_policy import runtime_inputs

    validate_runtime_transition(root)
    if fingerprint(root, producer) != RUNTIME:
        raise SystemExit("Unreviewed canonical polygon measurement runtime.")
    inputs = archived_source_inputs(root, producer)
    if inputs != runtime_inputs(root):
        raise SystemExit("Canonical polygon complete producer inputs differ from current source.")
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
    ):
        if (directory / name).read_bytes() != git_bytes(root, BASE, "ci/test_shards/" + name):
            raise SystemExit("Retained symbolic predecessor evidence changed.")


def require_test_sources(root: Path, sources: object) -> None:
    """Retain every old behavioral source and admit precisely the reviewed new file."""
    previous = json.loads(
        git_bytes(root, BASE, "ci/test_shards/symbolic-milli-inch-covered-baseline.json")
    )
    if sources != {**previous["test_sources"], OWNER: TEST_SHA256}:
        raise SystemExit(
            "Canonical polygon behavioral source inventory differs from its finite addition."
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
        raise SystemExit("Canonical polygon admission requires its actual runtime checkout.")
    rebuilt = build_identity.canonical_engine_build_manifest_text(
        build_identity.build_engine_manifest_payload()
    ).encode()
    if rebuilt != (root / MANIFEST).read_bytes():
        raise SystemExit("Canonical polygon live runtime source differs from its manifest.")
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
        git_bytes(root, BASE, "ci/test_shards/symbolic-milli-inch-derived-assignment.json")
    )
    if len(groups) != 12:
        raise SystemExit("Canonical polygon admission preserves twelve shards.")
    for index, group in enumerate(groups, 1):
        if [node for node in group if node != OWNER] != previous["shards"][str(index)]:
            raise SystemExit("Canonical polygon admission cannot move a retained selector.")
    if sum(group.count(OWNER) for group in groups) != 1:
        raise SystemExit("Canonical polygon selector must appear exactly once.")
