"""Finite native Dark Pact admission extending the exact #745 selection."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

from scripts.behavioral_selection_members import (
    _selection_members,
    _selection_no_links,
    _selection_object,
)

RECEIPT = "data/source_audits/ci64_provenance_v1/dark-pact-test-v1.json"
PREDECESSOR = "data/source_audits/ci64_provenance_v1/charge-flight-wall-test-v1.json"
BASE = "ab3a4ac03854964649f74efe5b8cebd528d3e25a"
RECEIPT_SHA256 = "a12562dd774086af360aca74bda457ebf0f6e10ae3e533ae4af6e021f3110031"
NEW_TEST = "tests/infrastructure/adapters/test_dark_pact_timing.py"
UPDATED_TEST = "tests/factions/chaos_daemons/unit/test_generic_rule_ability_registry.py"
LIFECYCLE_SOURCE = "src/warhammer40k_core/engine/lifecycle.py"
INACTIVE_TESTS = (
    "tests/unit/test_phase17g_chaos_daemons_shadow_legion.py",
    "tests/unit/test_phase17g_chaos_space_marines_army_rule.py",
)

type Members = dict[str, dict[str, object]]


def _read_receipt(root: Path) -> tuple[dict[str, object], bytes] | None:
    path = root / RECEIPT
    _selection_no_links(root, path)
    if not path.exists():
        return None
    raw = path.read_bytes()
    if hashlib.sha256(raw).hexdigest() != RECEIPT_SHA256:
        raise SystemExit("Dark Pact test admission receipt changed.")
    record = json.loads(raw, object_pairs_hook=_selection_object)
    predecessor = root / PREDECESSOR
    _selection_no_links(root, predecessor)
    if (
        record.keys()
        != {
            "schema",
            "base",
            "retained_transition_sha256",
            "retained_runtime_fingerprint",
            "runtime_fingerprint",
            "added_files",
            "updated_files",
            "inactive_fixtures",
            "retained_lifecycle",
        }
        or record["schema"] != "finite-dark-pact-test-v1"
        or record["base"] != BASE
        or record["retained_transition_sha256"]
        != hashlib.sha256(predecessor.read_bytes()).hexdigest()
        or set(record["added_files"]) != {NEW_TEST}
        or set(record["updated_files"]) != {UPDATED_TEST}
        or set(record["inactive_fixtures"]) != set(INACTIVE_TESTS)
    ):
        raise SystemExit("Dark Pact test admission differs from its approved finite scope.")
    return record, raw


def dark_pact_source_successors(
    root: Path, *, current_sources: dict[str, dict[str, str]] | None = None
) -> dict[str, dict[str, str]]:
    read = _read_receipt(root)
    if read is None:
        return {}
    record, _ = read
    row = record["retained_lifecycle"]
    path = root / LIFECYCLE_SOURCE
    _selection_no_links(root, path)
    successor = None if current_sources is None else current_sources.get(LIFECYCLE_SOURCE)
    current_digest = hashlib.sha256(path.read_bytes()).hexdigest()
    if (
        not isinstance(row, dict)
        or row.keys() != {"before", "after"}
        or not isinstance(row["before"], str)
        or (
            row["after"] != current_digest
            if successor is None
            else row["after"] != successor["before"] or current_digest != successor["after"]
        )
    ):
        raise SystemExit("Dark Pact lifecycle successor differs.")
    return {LIFECYCLE_SOURCE: row}


def dark_pact_inactive_successors(root: Path, retained: Members) -> Members:
    read = _read_receipt(root)
    if read is None:
        return {}
    record, _ = read
    fixtures = record["inactive_fixtures"]
    if not isinstance(fixtures, dict):
        raise SystemExit("Dark Pact inactive fixture inventory is malformed.")
    after: dict[str, object] = {}
    for name in INACTIVE_TESTS:
        row = fixtures[name]
        if (
            not isinstance(row, dict)
            or row.keys() != {"before", "after"}
            or row["before"] != retained.get(name)
        ):
            raise SystemExit("Dark Pact fixture preimage does not match retained membership.")
        after[name] = row["after"]
    return _selection_members(after, root)


def dark_pact_active_successors(root: Path, retained: Members) -> Members:
    read = _read_receipt(root)
    if read is None:
        return {}
    record, _ = read
    inventory = record["updated_files"]
    if not isinstance(inventory, dict):
        raise SystemExit("Dark Pact active fixture inventory is malformed.")
    row = inventory[UPDATED_TEST]
    if (
        not isinstance(row, dict)
        or row.keys() != {"before", "after"}
        or row["before"] != retained.get(UPDATED_TEST)
    ):
        raise SystemExit("Dark Pact active fixture preimage differs.")
    return _selection_members({UPDATED_TEST: row["after"]}, root)


def dark_pact_test_transition(
    root: Path, *, runtime: str, active_successors: Members
) -> tuple[str, Members, Members, bytes] | None:
    read = _read_receipt(root)
    if read is None:
        return None
    record, raw = read
    fingerprint = record["runtime_fingerprint"]
    if record["retained_runtime_fingerprint"] != runtime or not isinstance(fingerprint, str):
        raise SystemExit("Dark Pact tests require the exact retained runtime predecessor.")
    return (
        fingerprint,
        active_successors,
        _selection_members(record["added_files"], root),
        raw,
    )
