"""Finite admission of the explicit precision-profile binding and its fresh covered run."""

from __future__ import annotations

import json
from pathlib import Path

from scripts.historical_shard_snapshot import MANIFEST, fingerprint, git_bytes
from scripts.linux_authority_shard_admission import (
    archived_source_inputs,
    retained_native_inventory,
)

SCHEMA = "historical-snapshot-precision-profile-binding-v1"
BASE = "13a8cad365b00fd9a96157dd029ee4db8121210f"
RUNTIME = "ae914a56833e43a3bbf086730b354c7a18673ccc15ca93e4b474347b95380f19"
BASELINE_FILE = "precision-profile-covered-baseline.json"
EVIDENCE_FILE = "precision-profile-covered-evidence.json"
ASSIGNMENT_FILE = "precision-profile-derived-assignment.json"
OWNER = "tests/infrastructure/adapters/unit/test_numerical_policy.py"
# Exact reviewed source and added-case inventory; no open-ended exceptions.
RUNTIME_SOURCES: dict[str, str] = {
    "src/warhammer40k_core/adapters/numerical_policy.py": (
        "80bac8cc2264149cc8aba613df2c3db785810173e37435c09c369df118d86c5f"
    ),
    "src/warhammer40k_core/adapters/execution_profile.py": (
        "4effd97d70a8d71719380cbd6c47f59c3ed0ffb1e1d755875f760ecb9b33f00a"
    ),
    "src/warhammer40k_core/adapters/linux_authority_transport.py": (
        "ba509b5a63c48cc31af44e70a2bd9e8e86567b5e367e2734fa3ddadb224e71dc"
    ),
    "src/warhammer40k_core/adapters/linux_authority_worker.py": (
        "a999288f018d96a772917d2653cc6ae82bd3180ec32a4e82ab2f837005c432d7"
    ),
    "src/warhammer40k_core/adapters/linux_session.py": (
        "78ac218396507ef11f95a9b423739ac76c92e2f7801c0401ebd319e9323af212"
    ),
}
TEST_SOURCES: dict[str, str] = {
    "tests/infrastructure/adapters/unit/test_linux_authority.py": (
        "9d8abade332100121766655881547a6e0bf1813fe416414a022127605b988ec7"
    ),
    "tests/infrastructure/adapters/unit/test_numerical_policy.py": (
        "73c17636cf2fb3b2977d0bf050990199095aa4c4597c5c5b03bcf2f2dccf115e"
    ),
}
NODES: frozenset[str] = frozenset(
    [
        "tests/infrastructure/adapters/unit/test_numerical_policy.py::test_missing_policy_and_retained_profile_require_their_original_executor",
        "tests/infrastructure/adapters/unit/test_numerical_policy.py::test_policy_configuration_and_checkpoint_cache_identity_are_explicit",
        "tests/infrastructure/adapters/unit/test_numerical_policy.py::test_unknown_or_inactive_numerical_policy_is_never_executed[1]",
        "tests/infrastructure/adapters/unit/test_numerical_policy.py::test_unknown_or_inactive_numerical_policy_is_never_executed[None]",
        "tests/infrastructure/adapters/unit/test_numerical_policy.py::test_unknown_or_inactive_numerical_policy_is_never_executed[True]",
        "tests/infrastructure/adapters/unit/test_numerical_policy.py::test_unknown_or_inactive_numerical_policy_is_never_executed[]",
        "tests/infrastructure/adapters/unit/test_numerical_policy.py::test_unknown_or_inactive_numerical_policy_is_never_executed[milli-inch-half-away-v1]",
        "tests/infrastructure/adapters/unit/test_numerical_policy.py::test_unknown_or_inactive_numerical_policy_is_never_executed[unknown]",
    ]
)


def validate_runtime_transition(root: Path) -> None:
    """Admit precisely the reviewed source replacements and additions from the base."""
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
        not RUNTIME_SOURCES
        or MANIFEST in RUNTIME_SOURCES
        or actual != protected | RUNTIME_SOURCES.keys()
        or any(current[name] != digest for name, digest in RUNTIME_SOURCES.items())
        or any(
            current[name] != previous[name]
            for name in protected - RUNTIME_SOURCES.keys() - {MANIFEST}
        )
    ):
        raise SystemExit("Precision-profile runtime differs from its finite source transition.")
    old_manifest = json.loads(git_bytes(root, BASE, MANIFEST))
    manifest = json.loads((root / MANIFEST).read_bytes())
    resources = {row["path"]: row for row in old_manifest["resources"]}
    for name, digest in RUNTIME_SOURCES.items():
        if name.startswith("src/warhammer40k_core/"):
            path = name.removeprefix("src/")
            resources[path] = {
                "path": path,
                "byte_length": len((root / name).read_bytes()),
                "sha256": digest,
            }
        elif name.startswith("contracts/schemas/"):
            path = "warhammer40k_core/" + name
            resources[path] = {
                "path": path,
                "byte_length": len((root / name).read_bytes()),
                "sha256": digest,
            }
    if (
        manifest["fingerprint"] != RUNTIME
        or manifest["schema_version"] != old_manifest["schema_version"]
        or manifest["algorithm"] != old_manifest["algorithm"]
        or manifest["resource_count"] != len(resources)
        or manifest["resources"] != sorted(resources.values(), key=lambda row: row["path"])
    ):
        raise SystemExit("Precision-profile manifest differs from its finite source transition.")


def producer_inputs(root: Path, producer: str) -> dict[str, str]:
    """Require an exact complete current Git producer, never source exceptions."""
    from tools.performance_policy import runtime_inputs

    validate_runtime_transition(root)
    if fingerprint(root, producer) != RUNTIME:
        raise SystemExit("Unreviewed precision-profile measurement runtime.")
    inputs = archived_source_inputs(root, producer)
    if inputs != runtime_inputs(root):
        raise SystemExit("Precision-profile complete producer inputs differ from current source.")
    return inputs


def retained_authority_artifacts(root: Path, directory: Path) -> None:
    """Preserve the Linux and milli-inch profiles as original evidence, not live timing."""
    for name in (
        "linux-authority-covered-baseline.json",
        "linux-authority-covered-evidence.json",
        "linux-authority-derived-assignment.json",
        "milli-inch-covered-baseline.json",
        "milli-inch-covered-evidence.json",
        "milli-inch-derived-assignment.json",
    ):
        if (directory / name).read_bytes() != git_bytes(root, BASE, "ci/test_shards/" + name):
            raise SystemExit("Retained precision predecessor evidence changed.")


def require_test_sources(root: Path, sources: object) -> None:
    """Retain every source outside the explicitly reviewed behavioral transition."""
    previous = json.loads(git_bytes(root, BASE, "ci/test_shards/milli-inch-covered-baseline.json"))
    if sources != {**previous["test_sources"], **TEST_SOURCES}:
        raise SystemExit(
            "Precision-profile behavioral source inventory differs from its finite addition."
        )


def transitioned_test(root: Path, owner: str, current: bytes, historical: bytes) -> bool:
    """Admit only explicit frozen replacements, retaining each original source preimage."""
    import hashlib

    from scripts.historical_shard_snapshot import HISTORICAL_REVISION

    if owner not in TEST_SOURCES or owner == OWNER:
        return False
    if hashlib.sha256(current).hexdigest() != TEST_SOURCES[owner] or historical != git_bytes(
        root, HISTORICAL_REVISION, owner
    ):
        raise SystemExit("Precision-profile test source differs from its reviewed transition.")
    return True


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
        raise SystemExit("Precision-profile admission requires its actual runtime checkout.")
    rebuilt = build_identity.canonical_engine_build_manifest_text(
        build_identity.build_engine_manifest_payload()
    ).encode()
    if rebuilt != (root / MANIFEST).read_bytes():
        raise SystemExit("Precision-profile live runtime source differs from its manifest.")
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
        git_bytes(root, BASE, "ci/test_shards/milli-inch-derived-assignment.json")
    )
    if len(groups) != 12:
        raise SystemExit("Precision-profile admission preserves twelve shards.")
    for index, group in enumerate(groups, 1):
        if [node for node in group if node != OWNER] != previous["shards"][str(index)]:
            raise SystemExit("Precision-profile admission cannot move a retained selector.")
    if sum(group.count(OWNER) for group in groups) != 1:
        raise SystemExit("Precision-profile selector must appear exactly once.")
