"""Exact test-admission successors for opt-in Stage 2 policies."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

from scripts.behavioral_selection_members import (
    _selection_members,
    _selection_no_links,
    _selection_object,
)

TRANSITION_SHA256 = "0b1591280543a9952a3da9590a64dde5f6d6d5ebe1412ad333edac4234293001"
BASE = "2addab80a74e9369b8b0b653954318bf58eec0e5"
OWNER = "tests/infrastructure/adapters/test_ground_charge_policy.py"
GROUP_BASE = "ffd62f1b1cdcf81c2fbd4b99457482c1018d2eb8"
GROUP_TRANSITION = "data/source_audits/ci64_provenance_v1/stage2-group-ground-charge-test-v1.json"
GROUP_TRANSITION_SHA256 = "f32f75b6d38120e8663fde79612493ff40922c5eff7459d3d7197787791ea601"
GROUP_OWNER = "tests/infrastructure/adapters/test_group_ground_charge_policy.py"
RIGID_BASE = "5aca97bfaf4b3f1a753d65ed6b7dfc2482aa77f0"
RIGID_TRANSITION = "data/source_audits/ci64_provenance_v1/stage2-rigid-ground-charge-test-v1.json"
RIGID_TRANSITION_SHA256 = "2345dd760e0b9786c2420a024beb30aa7b734e6ab7ef1c0a9cedd33b0e0b72f2"
RIGID_OWNER = "tests/infrastructure/adapters/test_rigid_group_ground_charge_policy.py"
RIGID_SOURCE = "src/warhammer40k_core/ai/ground_charge_candidates.py"
SOURCES = (
    RIGID_SOURCE,
    "src/warhammer40k_core/ai/ground_charge_policy.py",
)


def ground_charge_test_successor(
    root: Path,
    *,
    transition_path: Path,
    previous_runtime: str,
    previous_transition_sha256: str,
    rigid_source: dict[str, str] | None = None,
) -> tuple[str, dict[str, dict[str, object]], bytes]:
    raw = transition_path.read_bytes()
    if hashlib.sha256(raw).hexdigest() != TRANSITION_SHA256:
        raise SystemExit("Ground charge test transition bytes differ.")
    record = json.loads(raw, object_pairs_hook=_selection_object)
    if (
        record.keys()
        != {
            "schema",
            "base",
            "retained_transition_sha256",
            "retained_runtime_fingerprint",
            "runtime_fingerprint",
            "sources",
            "added_files",
        }
        or record["schema"] != "finite-stage2-ground-charge-test-addition-v1"
        or record["base"] != BASE
        or record["retained_transition_sha256"] != previous_transition_sha256
        or record["retained_runtime_fingerprint"] != previous_runtime
        or set(record["sources"]) != set(SOURCES)
        or set(record["added_files"]) != {OWNER}
    ):
        raise SystemExit("Ground charge test transition membership differs.")
    group_path = root / GROUP_TRANSITION
    _selection_no_links(root, group_path)
    current_sources = record["sources"]
    group = None
    group_raw = b""
    if group_path.exists():
        group_raw = group_path.read_bytes()
        if hashlib.sha256(group_raw).hexdigest() != GROUP_TRANSITION_SHA256:
            raise SystemExit("Group ground charge test transition bytes differ.")
        group = json.loads(group_raw, object_pairs_hook=_selection_object)
        if (
            group.keys()
            != {
                "schema",
                "base",
                "retained_transition_sha256",
                "retained_runtime_fingerprint",
                "runtime_fingerprint",
                "sources",
                "added_files",
            }
            or group["schema"] != "finite-stage2-group-ground-charge-test-v1"
            or group["base"] != GROUP_BASE
            or group["retained_transition_sha256"] != TRANSITION_SHA256
            or group["retained_runtime_fingerprint"] != record["runtime_fingerprint"]
            or set(group["sources"]) != set(SOURCES)
            or set(group["added_files"]) != {GROUP_OWNER}
            or {name: row["before"] for name, row in group["sources"].items()} != record["sources"]
        ):
            raise SystemExit("Group ground charge test transition membership differs.")
        current_sources = {name: row["after"] for name, row in group["sources"].items()}
    if rigid_source is not None:
        if group is None or rigid_source["before"] != current_sources[RIGID_SOURCE]:
            raise SystemExit("Rigid ground charge source preimage differs.")
        current_sources = {**current_sources, RIGID_SOURCE: rigid_source["after"]}
    for name, digest in current_sources.items():
        source = root / name
        _selection_no_links(root, source)
        if hashlib.sha256(source.read_bytes()).hexdigest() != digest:
            raise SystemExit("Ground charge source bytes differ: " + name)
    tests = _selection_members(record["added_files"], root)
    if group is not None:
        tests.update(_selection_members(group["added_files"], root))
        return group["runtime_fingerprint"], tests, raw + b"\0" + group_raw
    return record["runtime_fingerprint"], tests, raw


def rigid_ground_charge_test_successor(
    root: Path, *, previous_runtime: str | None
) -> tuple[str, dict[str, str], dict[str, dict[str, object]], bytes] | None:
    from scripts.engine_numerical_identity_test_admission import _checked_bytes

    path = root / RIGID_TRANSITION
    _selection_no_links(root, path)
    if not path.exists():
        return None
    raw = _checked_bytes(root, RIGID_TRANSITION, RIGID_TRANSITION_SHA256)
    record = json.loads(raw, object_pairs_hook=_selection_object)
    if (
        record.keys()
        != {
            "schema",
            "base",
            "retained_group_charge_sha256",
            "retained_runtime_fingerprint",
            "runtime_fingerprint",
            "source",
            "added_files",
        }
        or record["schema"] != "finite-stage2-rigid-ground-charge-test-v1"
        or record["base"] != RIGID_BASE
        or record["retained_group_charge_sha256"] != GROUP_TRANSITION_SHA256
        or record["retained_runtime_fingerprint"] != previous_runtime
        or record["source"].keys() != {"before", "after"}
        or set(record["added_files"]) != {RIGID_OWNER}
    ):
        raise SystemExit("Rigid ground charge test transition differs.")
    return (
        record["runtime_fingerprint"],
        record["source"],
        _selection_members(record["added_files"], root),
        raw,
    )


SHOOTING_BASE = "153bb57bfd03a6b8bc8ca137dcd2f33e8648a9f8"
SHOOTING_TRANSITION = "data/source_audits/ci64_provenance_v1/stage2-normal-shooting-test-v1.json"
SHOOTING_TRANSITION_SHA256 = "e52c9197bb04d1cd64c595f960d39f9cf6964971dc90f650575429d83fcf2862"
SHOOTING_OWNER = "tests/infrastructure/adapters/test_opposing_shooter_scenario.py"
SHOOTING_SOURCE = "src/warhammer40k_core/ai/normal_shooting_policy.py"


def normal_shooting_test_successor(
    root: Path, *, previous_runtime: str, retained_cutover_sha256: str
) -> tuple[str, dict[str, dict[str, object]], bytes]:
    from scripts.build_test_shards import CUTOVER_PATH
    from scripts.engine_numerical_identity_test_admission import _checked_bytes

    raw = _checked_bytes(root, SHOOTING_TRANSITION, SHOOTING_TRANSITION_SHA256)
    record = json.loads(raw, object_pairs_hook=_selection_object)
    retained = json.loads(
        _checked_bytes(root, CUTOVER_PATH, retained_cutover_sha256),
        object_pairs_hook=_selection_object,
    )
    if (
        record.keys()
        != {
            "schema",
            "base",
            "retained_group_charge_sha256",
            "retained_runtime_fingerprint",
            "runtime_fingerprint",
            "policy_sha256",
            "test",
        }
        or record["schema"] != "finite-stage2-normal-shooting-test-v1"
        or record["base"] != SHOOTING_BASE
        or record["retained_group_charge_sha256"] != GROUP_TRANSITION_SHA256
        or record["retained_runtime_fingerprint"] != previous_runtime
        or record["test"]["before"] != retained["active_files"][SHOOTING_OWNER]
    ):
        raise SystemExit("Normal Shooting test transition membership differs.")
    _checked_bytes(root, GROUP_TRANSITION, GROUP_TRANSITION_SHA256)
    _checked_bytes(root, SHOOTING_SOURCE, record["policy_sha256"])
    tests = _selection_members({SHOOTING_OWNER: record["test"]["after"]}, root)
    return record["runtime_fingerprint"], tests, raw


SCREEN_BASE = "a194e8f10d198f5560119cd1450aa597cae723c1"
SCREEN_TRANSITION = "data/source_audits/ci64_provenance_v1/stage2-screen-movement-test-v1.json"
SCREEN_TRANSITION_SHA256 = "7e0b32cb0f7a0ef8e7d05f9b0a4aa7bb965cb6644e5d42ffd035897a536deb94"
SCREEN_OWNER = "tests/rules/section09/test_screen_movement_candidates.py"
SCREEN_SOURCE = "src/warhammer40k_core/ai/screen_movement_candidates.py"


def screen_movement_test_successor(
    root: Path, *, previous_runtime: str
) -> tuple[str, dict[str, dict[str, object]], bytes]:
    from scripts.engine_numerical_identity_test_admission import _checked_bytes

    raw = _checked_bytes(root, SCREEN_TRANSITION, SCREEN_TRANSITION_SHA256)
    record = json.loads(raw, object_pairs_hook=_selection_object)
    if (
        record.keys()
        != {
            "schema",
            "base",
            "retained_normal_shooting_sha256",
            "retained_runtime_fingerprint",
            "runtime_fingerprint",
            "policy_sha256",
            "added_files",
        }
        or record["schema"] != "finite-stage2-screen-movement-test-v1"
        or record["base"] != SCREEN_BASE
        or record["retained_normal_shooting_sha256"] != SHOOTING_TRANSITION_SHA256
        or record["retained_runtime_fingerprint"] != previous_runtime
        or set(record["added_files"]) != {SCREEN_OWNER}
    ):
        raise SystemExit("Screen movement test transition membership differs.")
    _checked_bytes(root, SCREEN_SOURCE, record["policy_sha256"])
    return record["runtime_fingerprint"], _selection_members(record["added_files"], root), raw
