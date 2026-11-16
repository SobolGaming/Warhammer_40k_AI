"""Finite admission of the inactive milli-inch foundation and its fresh covered run."""

from __future__ import annotations

import json
from pathlib import Path

from scripts.historical_shard_snapshot import MANIFEST, fingerprint, git_bytes
from scripts.linux_authority_shard_admission import (
    archived_source_inputs,
    retained_native_inventory,
)

SCHEMA = "historical-snapshot-milli-inch-foundation-v1"
BASE = "22f3fde616758008100bdf37d87edd671ed90d9a"
RUNTIME = "ff4277b5e1024958cc9f3e5464b5e26fc578c84b7a39130bece55d3ad0cf0add"
BASELINE_FILE = "milli-inch-covered-baseline.json"
EVIDENCE_FILE = "milli-inch-covered-evidence.json"
ASSIGNMENT_FILE = "milli-inch-derived-assignment.json"
MODULE = "src/warhammer40k_core/geometry/milli_inch.py"
MODULE_SHA256 = "692a482b4be1b765ef351a249b928fdc156023086112b11266ba6b06ef8476c4"
OWNER = "tests/rules/section01/test_milli_inch.py"
TEST_SHA256 = "6fad7bf3bc123c2f217bb0ae46b96971d8591f1cda712a0d88ba4b1f0f5edb37"
NODES = frozenset(
    f"{OWNER}::{name}"
    for name in (
        "test_milli_inch_signed_rounding_ties_and_exact_neighbors",
        "test_milli_inch_exact_sources_and_binary_float_semantics_are_distinct",
        "test_milli_inch_decimal_context_cannot_change_results",
        "test_milli_inch_exact_mm_conversion_precedes_single_rounding",
        "test_milli_inch_canonical_dimensions_derive_exact_half_tick_radii",
        "test_milli_inch_squared_measurements_compare_exact_midpoints",
        "test_milli_inch_threshold_strictness_uses_rounded_length_without_epsilon",
        "test_milli_inch_zero_rounded_gap_is_not_a_topology_predicate",
        "test_milli_inch_path_rounds_total_once_and_is_partition_invariant",
        "test_milli_inch_path_rejects_negative_and_unsupported_irrational_segments",
    )
)
NODES |= frozenset(
    f"{OWNER}::test_milli_inch_rejects_invalid_sources[{parameter}]"
    for parameter in (
        "True",
        "False",
        "None",
        "source3",
        "source4",
        "nan",
        "inf",
        "-inf",
        "source8",
        "source9",
        "source10",
        "NaN",
        "Infinity",
        "1/2",
        "",
    )
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
            "Milli-inch admission permits only the reviewed inactive runtime addition."
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
        raise SystemExit("Milli-inch manifest is not the reviewed add-only runtime transition.")


def producer_inputs(root: Path, producer: str) -> dict[str, str]:
    """Require an exact complete current Git producer, never source exceptions."""
    from tools.performance_policy import runtime_inputs

    validate_runtime_transition(root)
    if fingerprint(root, producer) != RUNTIME:
        raise SystemExit("Unreviewed milli-inch measurement runtime.")
    inputs = archived_source_inputs(root, producer)
    if inputs != runtime_inputs(root):
        raise SystemExit("Milli-inch complete producer inputs differ from current source.")
    return inputs


def retained_authority_artifacts(root: Path, directory: Path) -> None:
    """Preserve the superseded Linux profile as original evidence, not live timing."""
    for name in (
        "linux-authority-covered-baseline.json",
        "linux-authority-covered-evidence.json",
        "linux-authority-derived-assignment.json",
    ):
        if (directory / name).read_bytes() != git_bytes(root, BASE, "ci/test_shards/" + name):
            raise SystemExit("Retained Linux authority evidence changed.")


def require_test_sources(root: Path, sources: object) -> None:
    """Retain every old behavioral source and admit precisely the reviewed new file."""
    previous = json.loads(
        git_bytes(root, BASE, "ci/test_shards/linux-authority-covered-baseline.json")
    )
    if sources != {**previous["test_sources"], OWNER: TEST_SHA256}:
        raise SystemExit("Milli-inch behavioral source inventory differs from its finite addition.")


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
        raise SystemExit("Milli-inch admission requires its actual runtime checkout.")
    rebuilt = build_identity.canonical_engine_build_manifest_text(
        build_identity.build_engine_manifest_payload()
    ).encode()
    if rebuilt != (root / MANIFEST).read_bytes():
        raise SystemExit("Milli-inch live runtime source differs from its manifest.")
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
        git_bytes(root, BASE, "ci/test_shards/linux-authority-derived-assignment.json")
    )
    if len(groups) != 12:
        raise SystemExit("Milli-inch admission preserves twelve shards.")
    for index, group in enumerate(groups, 1):
        if [node for node in group if node != OWNER] != previous["shards"][str(index)]:
            raise SystemExit("Milli-inch admission cannot move a retained selector.")
    if sum(group.count(OWNER) for group in groups) != 1:
        raise SystemExit("Milli-inch selector must appear exactly once.")
