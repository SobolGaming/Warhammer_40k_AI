"""Byte-bound admission of the native ranged attack-count regressions."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import TYPE_CHECKING, TypedDict, cast

from scripts.behavioral_selection_members import (
    _selection_members,  # pyright: ignore[reportPrivateUsage]
    _selection_no_links,  # pyright: ignore[reportPrivateUsage]
    _selection_object,  # pyright: ignore[reportPrivateUsage]
)

if TYPE_CHECKING:
    from scripts.stage3_ranged_profile_test_admission import RangedProfileTestAdmission

RECEIPT = "data/source_audits/ci64_provenance_v1/ranged-attack-count-reroll-test-v1.json"
RECEIPT_SHA256 = "4e8aae570f710e916c1272cb8573c51aeb26d4b07bb54ebc64f548796852c287"
BASE = "dafbcccdd31d5532c0d58aceac43901e60326d36"
SOURCE = "src/warhammer40k_core/engine/ranged_attack_count_gathering.py"
VIEWER_SOURCES = (
    "src/warhammer40k_core/adapters/redaction.py",
    "src/warhammer40k_core/adapters/viewer_identity.py",
)
OWNER = "tests/rules/section10/test_random_attack_count_reroll.py"
CASES = (
    "test_native_fixed_group_resolves_before_unselected_random_attacks",
    "test_native_group_rolls_separately_for_two_physical_weapons",
    "test_native_random_attacks_choose_then_gather_and_reroll[False]",
    "test_native_random_attacks_choose_then_gather_and_reroll[True]",
    "test_random_attack_count_window_restores_and_replays[1]",
    "test_random_attack_count_window_restores_and_replays[2]",
)


class RangedAttackCountTestAdmission(TypedDict):
    schema: str
    base: str
    retained_ranged_profile_sha256: str
    retained_manifest_sha256: str
    retained_runtime_fingerprint: str
    manifest_sha256: str
    runtime_fingerprint: str
    gathering_source_sha256: str
    viewer_sources: dict[str, dict[str, str]]
    added_files: dict[str, dict[str, object]]
    added_cases: list[str]


def ranged_attack_count_test_addition(
    root: Path,
) -> tuple[RangedAttackCountTestAdmission, dict[str, dict[str, object]], bytes] | None:
    from scripts.engine_numerical_identity_test_admission import (
        _checked_bytes,  # pyright: ignore[reportPrivateUsage]
    )

    paths = (RECEIPT, SOURCE, OWNER, *VIEWER_SOURCES)
    for name in paths:
        _selection_no_links(root, root / name)
    if not any((root / name).exists() for name in (RECEIPT, SOURCE, OWNER)):
        return None
    raw = _checked_bytes(root, RECEIPT, RECEIPT_SHA256)
    record = cast(
        RangedAttackCountTestAdmission, json.loads(raw, object_pairs_hook=_selection_object)
    )
    if (
        record.keys() != RangedAttackCountTestAdmission.__required_keys__
        or record["schema"] != "finite-ranged-attack-count-reroll-test-v1"
        or record["base"] != BASE
        or set(record["viewer_sources"]) != set(VIEWER_SOURCES)
        or record["added_files"].keys() != {OWNER}
        or record["added_cases"] != [f"{OWNER}::{case}" for case in CASES]
    ):
        raise SystemExit("Ranged attack-count test admission inventory differs.")
    _checked_bytes(root, SOURCE, record["gathering_source_sha256"])
    for name, change in record["viewer_sources"].items():
        if set(change) != {"before", "after"}:
            raise SystemExit("Ranged attack-count viewer transition requires exact source digests.")
        _checked_bytes(root, name, change["after"])
    return record, _selection_members(record["added_files"], root), raw


def ranged_attack_count_runtime(
    root: Path, *, predecessor: RangedProfileTestAdmission, predecessor_bytes: bytes
) -> tuple[str, str]:
    """Extend the admitted ranged-profile manifest and fingerprint together."""
    addition = ranged_attack_count_test_addition(root)
    if addition is None:
        return predecessor["manifest_sha256"], predecessor["runtime_fingerprint"]
    receipt, _, _ = addition
    if (
        receipt["retained_ranged_profile_sha256"] != hashlib.sha256(predecessor_bytes).hexdigest()
        or receipt["retained_manifest_sha256"] != predecessor["manifest_sha256"]
        or receipt["retained_runtime_fingerprint"] != predecessor["runtime_fingerprint"]
    ):
        raise SystemExit("Ranged attack-count tests require the exact ranged profile predecessor.")
    return receipt["manifest_sha256"], receipt["runtime_fingerprint"]
