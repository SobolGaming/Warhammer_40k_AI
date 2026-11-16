"""Finite admission for the Linux authority and its fresh complete covered run.

No historical measurements or source exceptions are extended. All current
measurement inputs must equal their Git producer, with the original allocation
retained and exactly one new ordinary parallel test-file selector.
"""

from __future__ import annotations

import hashlib
import io
import json
import subprocess
import tarfile
from pathlib import Path
from typing import cast

from scripts.historical_shard_snapshot import MANIFEST, fingerprint, git_bytes
from scripts.hosted_timing_calibration import _object, read_json

SCHEMA = "historical-snapshot-linux-authority-profile-v1"
RUNTIME = "e2094d9cc44578f56a4998fe6b4a8d1ff248a30a31127bbd4c15f629a7ae11b7"
PREDECESSOR = "e2d7a899d162cc1972d8a158fc02978e54301cc2"
BASELINE_FILE = "linux-authority-covered-baseline.json"
EVIDENCE_FILE = "linux-authority-covered-evidence.json"
ASSIGNMENT_FILE = "linux-authority-derived-assignment.json"
OWNER = "tests/infrastructure/adapters/unit/test_linux_authority.py"
NODES = frozenset(
    f"{OWNER}::{name}"
    for name in (
        "test_profile_envelope_keeps_original_bytes_and_explicit_provenance",
        "test_profile_envelope_rejects_binding_drift[payload_base64]",
        "test_profile_envelope_rejects_binding_drift[payload_sha256]",
        "test_profile_envelope_rejects_binding_drift[profile_hash]",
        "test_profile_envelope_rejects_binding_drift[provenance]",
        "test_profile_enrollment_requires_a_receipt_and_checks_inner_bytes",
        "test_executor_registration_requires_the_registered_profile_and_same_engine",
        "test_authority_framing_distinguishes_clean_close_from_truncated_json",
        "test_dispatcher_real_native_roster_restore_fork_viewers_and_exact_replay",
        "test_selected_linux_process_implements_adapter_session_and_roundtrips",
    )
)


def archived_source_inputs(root: Path, producer: str) -> dict[str, str]:
    """Read a complete source closure as data, without a runtime applicability claim."""
    from tools.performance_policy import MAP

    archive = subprocess.check_output(
        [
            "git",
            "archive",
            producer,
            "src",
            "tests",
            "scripts",
            "tools",
            "contracts/schemas",
            "uv.lock",
            "pyproject.toml",
            MAP,
        ],
        cwd=root,
    )
    inputs: dict[str, str] = {}
    with tarfile.open(fileobj=io.BytesIO(archive)) as stream:
        for member in stream:
            if member.isdir():
                continue
            if not member.isfile():
                raise SystemExit("Linux authority producer inputs require regular files.")
            resource = stream.extractfile(member)
            if resource is None:
                raise SystemExit("Linux authority producer input bytes are unavailable.")
            inputs[member.name] = hashlib.sha256(resource.read()).hexdigest()
    return inputs


def producer_inputs(root: Path, producer: str) -> dict[str, str]:
    """Authenticate the entire current producer closure without executing old Python."""
    from tools.performance_policy import runtime_inputs

    if fingerprint(root, producer) != RUNTIME:
        raise SystemExit("Unreviewed Linux authority measurement runtime.")
    inputs = archived_source_inputs(root, producer)
    if inputs != runtime_inputs(root):
        raise SystemExit("Linux authority complete producer inputs differ from current source.")
    return inputs


def validate_retained_boolean_sources(root: Path) -> None:
    """Validate only the reviewed source snapshot; never certify a live runtime."""
    from tools.performance_policy import runtime_inputs

    from scripts import boolean_los_admission as transition

    transition.validate_manifest((root / MANIFEST).read_bytes())
    if (
        fingerprint(root, transition.BASE) != transition.PREVIOUS_RUNTIME
        or json.loads((root / MANIFEST).read_bytes())["fingerprint"] != transition.RUNTIME
    ):
        raise SystemExit("Unreviewed Boolean LOS runtime transition.")
    if runtime_inputs(root) != archived_source_inputs(root, PREDECESSOR):
        raise SystemExit("Retained Boolean LOS source snapshot changed.")


def retained_test_transition(root: Path, owner: str, current: bytes, historical: bytes) -> bool:
    """Retain the two approved test transitions, without promoting their old runtime."""
    from scripts.boolean_los_admission import BASE, TEST_SOURCES
    from scripts.boolean_los_admission import RUNTIME as PREVIOUS_RUNTIME

    if owner not in TEST_SOURCES:
        return False
    if (
        fingerprint(root, PREDECESSOR) != PREVIOUS_RUNTIME
        or hashlib.sha256(current).hexdigest() != TEST_SOURCES[owner]
        or current != git_bytes(root, PREDECESSOR, owner)
        or historical != git_bytes(root, BASE, owner)
    ):
        raise SystemExit("Retained Boolean LOS test sources differ from their reviewed transition.")
    return True


def retained_native_inventory(
    root: Path, directory: Path, reference: object, expected_nodes: frozenset[str]
) -> tuple[list[str], dict[str, object]]:
    """Read only the frozen case order; old timings are not current observations."""
    value = _object(reference, {"file", "sha256"}, "retained native inventory reference")
    filename = "current-native-serial-role.json"
    original = git_bytes(root, PREDECESSOR, "ci/test_shards/" + filename)
    if (
        value["file"] != filename
        or value["sha256"] != hashlib.sha256(original).hexdigest()
        or (directory / filename).read_bytes() != original
    ):
        raise SystemExit("Retained native observation or its source reference changed.")
    # Preserve the complete prior covered artifacts independently of the new run.
    for name in ("current-covered-baseline.json", "current-covered-evidence.json"):
        if (directory / name).read_bytes() != git_bytes(
            root, PREDECESSOR, "ci/test_shards/" + name
        ):
            raise SystemExit("Retained pre-authority covered evidence changed.")
    old = cast(dict[str, object], read_json(directory / filename))
    standalone = cast(dict[str, object], cast(dict[str, object], old["observations"])["standalone"])
    raw = cast(dict[str, object], standalone["raw"])
    worker = json.loads(cast(str, cast(dict[str, object], raw["worker"])["text"]))
    order = worker["collected_nodeids"]
    if not isinstance(order, list) or len(order) != 6 or set(order) != expected_nodes:
        raise SystemExit("Retained native case order differs from the six approved cases.")
    return cast(list[str], order), {
        "source_head": PREDECESSOR,
        "file": filename,
        "sha256": value["sha256"],
        "role": (
            "Retained prior-runtime observations and frozen case order; no current timing claim"
        ),
    }


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
        raise SystemExit("Linux authority admission requires its actual runtime checkout.")
    rebuilt = build_identity.canonical_engine_build_manifest_text(
        build_identity.build_engine_manifest_payload()
    ).encode()
    if rebuilt != (root / MANIFEST).read_bytes():
        raise SystemExit("Linux authority live runtime source differs from its manifest.")
    if json.loads((root / MANIFEST).read_bytes())["fingerprint"] != RUNTIME:
        raise SystemExit("Linux authority profile runtime differs from its reviewed build.")
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
        git_bytes(root, PREDECESSOR, "ci/test_shards/current-derived-assignment.json")
    )
    for index, group in enumerate(groups, 1):
        if [node for node in group if node != OWNER] != previous["shards"][str(index)]:
            raise SystemExit("Linux authority admission cannot move a retained selector.")
    if sum(OWNER in group for group in groups) != 1:
        raise SystemExit("Linux authority selector must appear exactly once.")
