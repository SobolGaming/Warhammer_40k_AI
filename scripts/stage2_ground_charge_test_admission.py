"""Exact test-admission successor for the opt-in six-model Charge Move policy."""

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
    for name, digest in record["sources"].items():
        source = root / name
        _selection_no_links(root, source)
        if hashlib.sha256(source.read_bytes()).hexdigest() != digest:
            raise SystemExit("Ground charge source bytes differ: " + name)
    return record["runtime_fingerprint"], _selection_members(record["added_files"], root), raw
