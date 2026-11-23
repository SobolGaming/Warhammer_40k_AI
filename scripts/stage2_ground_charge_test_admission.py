"""Exact test-admission successors for the opt-in ground Charge Move policy."""

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
SOURCES = (
    "src/warhammer40k_core/ai/ground_charge_candidates.py",
    "src/warhammer40k_core/ai/ground_charge_policy.py",
)


def ground_charge_test_successor(
    root: Path, *, transition_path: Path, previous_runtime: str, previous_transition_sha256: str
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
