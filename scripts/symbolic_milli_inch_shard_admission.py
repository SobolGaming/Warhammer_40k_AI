"""Finite admission of the inactive symbolic milli-inch measurements and its fresh covered run."""

from __future__ import annotations

import json
from pathlib import Path

from scripts.historical_shard_snapshot import MANIFEST, fingerprint, git_bytes
from scripts.linux_authority_shard_admission import (
    archived_source_inputs,
    retained_native_inventory,
)

SCHEMA = "historical-snapshot-milli-inch-symbolic-v1"
BASE = "fc52e9166ff6380b606269ce362f4f1cbc6a2835"
RUNTIME = "c18e59cd11ababb179bb3ebf55a74b00fa1416e1d94194de6758505b0268297e"
BASELINE_FILE = "symbolic-milli-inch-covered-baseline.json"
EVIDENCE_FILE = "symbolic-milli-inch-covered-evidence.json"
ASSIGNMENT_FILE = "symbolic-milli-inch-derived-assignment.json"
MODULE = "src/warhammer40k_core/geometry/milli_inch_symbolic.py"
MODULE_SHA256 = "f83a3da2f564cf3216c71e4a2992cf7dbd4f004287e8a48ca95b1cb796feeed8"
OWNER = "tests/rules/section01/test_milli_inch_symbolic.py"
TEST_SHA256 = "7631405d44df220439cf328c8a17ccc6ba27528b3b8e630e117d7125dfadfe95"
NODES: frozenset[str] = frozenset(
    [
        "tests/rules/section01/test_milli_inch_symbolic.py::test_symbolic_length_bins_match_all_four_integer_relations",
        "tests/rules/section01/test_milli_inch_symbolic.py::test_symbolic_measurement_deadline_fails_without_approximate_result",
        "tests/rules/section01/test_milli_inch_symbolic.py::test_symbolic_measurement_rejects_invalid_sources_and_contracts",
        "tests/rules/section01/test_milli_inch_symbolic.py::test_symbolic_measurement_unknown_is_typed_and_not_a_distance",
        "tests/rules/section01/test_milli_inch_symbolic.py::test_symbolic_path_exact_ties_and_irrational_neighbors_at_any_scale",
        "tests/rules/section01/test_milli_inch_symbolic.py::test_symbolic_path_measures_complete_mixed_sum_once",
        "tests/rules/section01/test_milli_inch_symbolic.py::test_symbolic_path_subdivision_and_segment_order_preserve_total",
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
            "Symbolic milli-inch admission permits only the reviewed inactive runtime addition."
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
            "Symbolic milli-inch manifest is not the reviewed add-only runtime transition."
        )


def producer_inputs(root: Path, producer: str) -> dict[str, str]:
    """Require an exact complete current Git producer, never source exceptions."""
    from tools.performance_policy import runtime_inputs

    validate_runtime_transition(root)
    if fingerprint(root, producer) != RUNTIME:
        raise SystemExit("Unreviewed symbolic milli-inch measurement runtime.")
    inputs = archived_source_inputs(root, producer)
    if inputs != runtime_inputs(root):
        raise SystemExit("Symbolic milli-inch complete producer inputs differ from current source.")
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
        "precision-profile-covered-baseline.json",
        "precision-profile-covered-evidence.json",
        "precision-profile-derived-assignment.json",
    ):
        if (directory / name).read_bytes() != git_bytes(root, BASE, "ci/test_shards/" + name):
            raise SystemExit("Retained symbolic predecessor evidence changed.")


def require_test_sources(root: Path, sources: object) -> None:
    """Retain every old behavioral source and admit precisely the reviewed new file."""
    previous = json.loads(
        git_bytes(root, BASE, "ci/test_shards/precision-profile-covered-baseline.json")
    )
    if sources != {**previous["test_sources"], OWNER: TEST_SHA256}:
        raise SystemExit(
            "Symbolic milli-inch behavioral source inventory differs from its finite addition."
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
        raise SystemExit("Symbolic milli-inch admission requires its actual runtime checkout.")
    rebuilt = build_identity.canonical_engine_build_manifest_text(
        build_identity.build_engine_manifest_payload()
    ).encode()
    if rebuilt != (root / MANIFEST).read_bytes():
        raise SystemExit("Symbolic milli-inch live runtime source differs from its manifest.")
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
        git_bytes(root, BASE, "ci/test_shards/precision-profile-derived-assignment.json")
    )
    if len(groups) != 12:
        raise SystemExit("Symbolic milli-inch admission preserves twelve shards.")
    for index, group in enumerate(groups, 1):
        if [node for node in group if node != OWNER] != previous["shards"][str(index)]:
            raise SystemExit("Symbolic milli-inch admission cannot move a retained selector.")
    if sum(group.count(OWNER) for group in groups) != 1:
        raise SystemExit("Symbolic milli-inch selector must appear exactly once.")
