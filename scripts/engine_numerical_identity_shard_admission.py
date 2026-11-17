"""Finite admission of inactive exact contact queries and their fresh covered run."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

from scripts.historical_shard_snapshot import MANIFEST, fingerprint, git_bytes
from scripts.linux_authority_shard_admission import (
    archived_source_inputs,
    retained_native_inventory,
)

SCHEMA = "historical-snapshot-engine-numerical-identity-v1"
BASE = "9747b9b0873b4f442d3cd81f72280b24810d952c"
RUNTIME = "db8c8f733112410866770bcd2d3231a9e2a348e2de0514f5fc0b5ffe95b7b9cd"
BASELINE_FILE = "engine-numerical-identity-covered-baseline.json"
EVIDENCE_FILE = "engine-numerical-identity-covered-evidence.json"
ASSIGNMENT_FILE = "engine-numerical-identity-derived-assignment.json"
MODULE = "src/warhammer40k_core/engine/numerical_identity.py"
MODULE_SHA256 = "cde0b845aec00f9e76e0b7a06394c74eb22668918cfa8c8033e8d89a1d84de0e"
COORDINATES = "src/warhammer40k_core/geometry/numerical_identity.py"
COORDINATES_SHA256 = "73b101b47264c6c2a7f1db9597247b89b6f9c3170b7c3208254ce73ebaf51462"
OWNER = "tests/rules/section01/test_engine_numerical_identity.py"
TEST_SHA256 = "98bcc81ce10207fed2af8f4dc0a75e47640e22df411047bc4134753111b33f95"
SOURCE_HASHES = {
    "contracts/schemas/create-session.schema.json": (
        "d31d970da328c065dc444a4bf92208615499c72b6fc5c7c8e18f72b4b06d1657"
    ),
    "contracts/schemas/game-view.schema.json": (
        "6de66cddb19389465e148ddeec41f07e62b5826fa6cfa42b2a1e333a7f43622a"
    ),
    "contracts/schemas/replay-metadata.schema.json": (
        "c58997bf59ab3002e165de8bf11b261d4015d7a18d6a8833f3e6b20b2f6a171b"
    ),
    "contracts/schemas/session-command-outcome.schema.json": (
        "c0daaf53e1c66aed65c491a8f80a5a5bf04f4337954629719f0891de1cb629ad"
    ),
    "contracts/schemas/session-command-result.schema.json": (
        "3fde2e244d4328f78f2c0c38fb59ff64b0dc02f4b0e1d7a20bc1047c282159a7"
    ),
    "contracts/schemas/session-create.schema.json": (
        "4c7167c56cb2771100c61e956a08040aab7dc9a2d694aeadc7c1bc4aaf5ec5be"
    ),
    "contracts/schemas/session-metadata.schema.json": (
        "49dd08a1496d1d2a52bd627daf72c930f5c0c5f15758baeea7ea2d6251c5b5a5"
    ),
    "contracts/schemas/session-persistence.schema.json": (
        "98d8b361188108cfcdefcd7b689764fc5b1cfbdd8cc0434439633732f9aa3def"
    ),
    "src/warhammer40k_core/adapters/battlefield_projection.py": (
        "632e82480b3a8d72ee5c5a503bee034779bddf7c7d102c00e1fb128d9784f8ea"
    ),
    "src/warhammer40k_core/adapters/external_contract.py": (
        "a9fd66f2f03fe8d05485c0b48f3672f548a182044ade32c191f985f490bc8eb1"
    ),
    "src/warhammer40k_core/adapters/linux_authority_transport.py": (
        "9ebd2028fe972d7614508bd1aef898fd4e6c7a33d53fb4437e976acec5bfba38"
    ),
    "src/warhammer40k_core/adapters/linux_authority_worker.py": (
        "c0904a8daec7f2fc836fdfcde6dae5e66e611bec017c96a8b97866588eb28f2c"
    ),
    "src/warhammer40k_core/adapters/local_session.py": (
        "fab4f30a4e83ba327fcecb3e23c829541a3ad337f2856634c0e17163d5f4f080"
    ),
    "src/warhammer40k_core/adapters/numerical_checkpoint_reconstruction.py": (
        "934c5d24fdff7781ffa199cbc370ea0cb970b27eed611b76afd07307e551b4ba"
    ),
    "src/warhammer40k_core/ai/canonical_deployment.py": (
        "f0ebfbed8d80011bd46d741b240fd23c096d47d4bcb81a3f222f9c2ee8fd6f1d"
    ),
    "src/warhammer40k_core/ai/deployment_reference_suite.py": (
        "abef6cdd0fbf9ed3d6e2f479a62749480828c7ce476495ab164b72b63c67b34d"
    ),
    "src/warhammer40k_core/ai/followthrough_scenario.py": (
        "ad4c440f1ea05fb4d4d5dc14590d9d1d0bfb873bcb1fc2ac2325f2ee63117c6f"
    ),
    "src/warhammer40k_core/ai/matched_attack_scenario.py": (
        "0c68725b55e3dd7f8e3b25ebcde22d3e497ab95ac1e3a862eeb8f2b33a7a1834"
    ),
    "src/warhammer40k_core/ai/normal_move_scenario.py": (
        "d2d8dffc43461eec0cc4db3db8923893b7ba59ad65e4df45c9a2cce3611692db"
    ),
    "src/warhammer40k_core/ai/opposing_shooter_scenario.py": (
        "1d31f56e93543705def0e3c700e90e77e1cfdd5bf6a793f2b6ef190d4821b6e7"
    ),
    "src/warhammer40k_core/ai/preserve_scenario.py": (
        "8b4a51aa0078c157f6f6eabc4f975a58c7a3ffffbd7199d3f99d4e32a0d92551"
    ),
    "src/warhammer40k_core/core/visibility.py": (
        "86b7f154e5c5f30f20844491a9f61a2be685bfab42bd5d2a6e1d6a051a86502a"
    ),
    "src/warhammer40k_core/engine/game_state.py": (
        "ca645341d6340ca2596fd6f0881e66e83525fd2aab5cd311273593f2f048b5e9"
    ),
    "src/warhammer40k_core/engine/game_state_payloads.py": (
        "fc66a7e43a45666048e2d6889faef0e1cdc2fd20cdf9b2e43fdbfcd31f484041"
    ),
    "src/warhammer40k_core/engine/lifecycle_payload_consistency.py": (
        "f2e3cf88dc5accb103d8f2aa244f68960034366af42e46dc31c533dbff505af6"
    ),
    "src/warhammer40k_core/engine/numerical_identity.py": (
        "cde0b845aec00f9e76e0b7a06394c74eb22668918cfa8c8033e8d89a1d84de0e"
    ),
    "src/warhammer40k_core/engine/replay.py": (
        "a47d3588f5f073347ca2096fc038c06027bbd6d1c3050e0f418aaa01825efbcc"
    ),
    "src/warhammer40k_core/geometry/numerical_identity.py": (
        "73b101b47264c6c2a7f1db9597247b89b6f9c3170b7c3208254ce73ebaf51462"
    ),
    "src/warhammer40k_core/geometry/pathing.py": (
        "f3cc92cb86a600c899000fb8d5d46b920c58ea32045137c155764822886823fd"
    ),
    "src/warhammer40k_core/geometry/pose.py": (
        "04a0e752e05f381fd7adc836a19438907cd9b2626032d434fc6d142f4579fa86"
    ),
}
UPDATED_TEST_HASHES = {
    "tests/rules/section18/test_facade.py": (
        "e57eed3325fdb9ff1e4e4e85682f7db56a012c5a77a071f3ebbfdb1609553457"
    ),
    "tests/infrastructure/adapters/unit/test_linux_authority.py": (
        "597d629a87432390b94fb91e788eeb6c5cc517f6adac98af4f0a915274aa195c"
    ),
    "tests/infrastructure/adapters/test_canonical_deployment_coverage.py": (
        "8ea704f9980ec99cbe3bcf84814d31f657eb6f969c3944c132382bd5c0b2e279"
    ),
}
NODES: frozenset[str] = frozenset(
    [
        "tests/rules/section01/test_engine_numerical_identity.py::test_current_authority_checkpoint_envelope_restores_on_same_profile",
        "tests/rules/section01/test_engine_numerical_identity.py::test_current_context_cache_binds_contract_without_changing_legacy_witness_bytes",
        "tests/rules/section01/test_engine_numerical_identity.py::test_inner_identity_survives_ordinary_move_persistence_and_replay",
        "tests/rules/section01/test_engine_numerical_identity.py::test_inner_payload_rejects_unbound_or_incompatible_identity[coordinates-config]",
        "tests/rules/section01/test_engine_numerical_identity.py::test_inner_payload_rejects_unbound_or_incompatible_identity[coordinates-state]",
        "tests/rules/section01/test_engine_numerical_identity.py::test_inner_payload_rejects_unbound_or_incompatible_identity[extra-config]",
        "tests/rules/section01/test_engine_numerical_identity.py::test_inner_payload_rejects_unbound_or_incompatible_identity[extra-state]",
        "tests/rules/section01/test_engine_numerical_identity.py::test_inner_payload_rejects_unbound_or_incompatible_identity[missing-config]",
        "tests/rules/section01/test_engine_numerical_identity.py::test_inner_payload_rejects_unbound_or_incompatible_identity[missing-state]",
        "tests/rules/section01/test_engine_numerical_identity.py::test_inner_payload_rejects_unbound_or_incompatible_identity[policy-config]",
        "tests/rules/section01/test_engine_numerical_identity.py::test_inner_payload_rejects_unbound_or_incompatible_identity[policy-state]",
        "tests/rules/section01/test_engine_numerical_identity.py::test_inner_payload_rejects_unbound_or_incompatible_identity[version-config]",
        "tests/rules/section01/test_engine_numerical_identity.py::test_inner_payload_rejects_unbound_or_incompatible_identity[version-state]",
        "tests/rules/section01/test_engine_numerical_identity.py::test_legacy_pose_and_path_do_not_drop_precision_labels[facing]",
        "tests/rules/section01/test_engine_numerical_identity.py::test_legacy_pose_and_path_do_not_drop_precision_labels[model_path]",
        "tests/rules/section01/test_engine_numerical_identity.py::test_legacy_pose_and_path_do_not_drop_precision_labels[point]",
        "tests/rules/section01/test_engine_numerical_identity.py::test_legacy_pose_and_path_do_not_drop_precision_labels[pose]",
        "tests/rules/section01/test_engine_numerical_identity.py::test_legacy_pose_and_path_do_not_drop_precision_labels[witness]",
        "tests/rules/section01/test_engine_numerical_identity.py::test_linux_dispatcher_rejects_inner_policy_without_losing_session",
        "tests/rules/section01/test_engine_numerical_identity.py::test_movement_facade_rejects_precision_labels_before_queue_or_state_mutation",
        "tests/rules/section01/test_engine_numerical_identity.py::test_numerical_reconstruction_rejects_forged_identity_bindings[missing]",
        "tests/rules/section01/test_engine_numerical_identity.py::test_numerical_reconstruction_rejects_forged_identity_bindings[nested]",
        "tests/rules/section01/test_engine_numerical_identity.py::test_numerical_reconstruction_rejects_forged_identity_bindings[provenance]",
        "tests/rules/section01/test_engine_numerical_identity.py::test_numerical_reconstruction_rejects_forged_identity_bindings[root]",
        "tests/rules/section01/test_engine_numerical_identity.py::test_retained_recipe_requires_its_original_executor_and_source_stays_unchanged",
        "tests/rules/section01/test_engine_numerical_identity.py::test_state_construction_rejects_untyped_binding",
    ]
)


def validate_runtime_transition(root: Path) -> None:
    """Admit exactly the reviewed source/schema changes and their new manifest."""
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
        actual != protected | SOURCE_HASHES.keys()
        or any(current.get(name) != value for name, value in SOURCE_HASHES.items())
        or any(
            current[name] != previous[name]
            for name in protected - SOURCE_HASHES.keys() - {MANIFEST}
        )
    ):
        raise SystemExit(
            "Numerical identity admission permits only the reviewed runtime transition."
        )
    old = json.loads(git_bytes(root, BASE, MANIFEST))
    manifest = json.loads((root / MANIFEST).read_bytes())
    expected = {row["path"]: row for row in old["resources"]}
    for name in SOURCE_HASHES:
        path = name.removeprefix("src/") if name.startswith("src/") else "warhammer40k_core/" + name
        content = (root / name).read_bytes().replace(b"\r\n", b"\n").replace(b"\r", b"\n")
        expected[path] = {
            "path": path,
            "byte_length": len(content),
            "sha256": hashlib.sha256(content).hexdigest(),
        }
    if (
        manifest["fingerprint"] != RUNTIME
        or manifest["schema_version"] != old["schema_version"]
        or manifest["algorithm"] != old["algorithm"]
        or manifest["resource_count"] != len(expected)
        or manifest["resources"] != sorted(expected.values(), key=lambda row: row["path"])
        or set(manifest) != set(old)
        or manifest["build_id"] != old["build_id"].rsplit(":", 1)[0] + ":" + RUNTIME
    ):
        raise SystemExit("Numerical identity manifest is not its finite runtime transition.")


def producer_inputs(root: Path, producer: str) -> dict[str, str]:
    """Require an exact complete current Git producer, never source exceptions."""
    from tools.performance_policy import runtime_inputs

    validate_runtime_transition(root)
    if fingerprint(root, producer) != RUNTIME:
        raise SystemExit("Unreviewed numerical identity measurement runtime.")
    inputs = archived_source_inputs(root, producer)
    if inputs != runtime_inputs(root):
        raise SystemExit("Numerical identity complete producer inputs differ from current source.")
    return inputs


def retained_authority_artifacts(root: Path, directory: Path) -> None:
    """Preserve all predecessor profiles as original evidence, not live timing."""
    for name in (
        "exact-contact-covered-baseline.json",
        "exact-contact-covered-evidence.json",
        "exact-contact-derived-assignment.json",
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
        git_bytes(root, BASE, "ci/test_shards/exact-contact-covered-baseline.json")
    )
    if sources != {**previous["test_sources"], **UPDATED_TEST_HASHES, OWNER: TEST_SHA256}:
        raise SystemExit(
            "Numerical identity behavioral source inventory differs from its finite addition."
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
        raise SystemExit("Numerical identity admission requires its actual runtime checkout.")
    rebuilt = build_identity.canonical_engine_build_manifest_text(
        build_identity.build_engine_manifest_payload()
    ).encode()
    if rebuilt != (root / MANIFEST).read_bytes():
        raise SystemExit("Numerical identity live runtime source differs from its manifest.")
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
        git_bytes(root, BASE, "ci/test_shards/exact-contact-derived-assignment.json")
    )
    if len(groups) != 12:
        raise SystemExit("Numerical identity admission preserves twelve shards.")
    for index, group in enumerate(groups, 1):
        if [node for node in group if node != OWNER] != previous["shards"][str(index)]:
            raise SystemExit("Numerical identity admission cannot move a retained selector.")
    if sum(group.count(OWNER) for group in groups) != 1:
        raise SystemExit("Numerical identity selector must appear exactly once.")


def transitioned_test(root: Path, owner: str, current: bytes, historical: bytes) -> bool:
    """One reviewed source-only recipe successor; every old case remains selected."""
    return (
        owner in UPDATED_TEST_HASHES
        and hashlib.sha256(current).hexdigest() == UPDATED_TEST_HASHES[owner]
        and historical == git_bytes(root, BASE, owner)
    )
