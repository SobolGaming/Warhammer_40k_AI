"""Byte-bound admission of the opt-in Stage 3 defender-coherency tests."""

from __future__ import annotations

import json
from pathlib import Path
from typing import TypedDict, cast

from scripts.behavioral_selection_members import (
    _selection_members,  # pyright: ignore[reportPrivateUsage]
    _selection_no_links,  # pyright: ignore[reportPrivateUsage]
    _selection_object,  # pyright: ignore[reportPrivateUsage]
)
from scripts.ranged_attack_count_test_admission import RECEIPT as ATTACK_COUNT_RECEIPT
from scripts.ranged_attack_count_test_admission import RECEIPT_SHA256 as ATTACK_COUNT_SHA256

RECEIPT = "data/source_audits/ci64_provenance_v1/stage3-defender-coherency-test-v1.json"
RECEIPT_SHA256 = "f1165ef04248316b694d625044c05656cfb640d1e38577579a0c9b011681cffe"
BASE = "be568f9188e7ddf0d08c0cee0f1540fa0fd09bbb"
SOURCE = "src/warhammer40k_core/ai/allocation_coherency.py"
RETAINED_OWNER = "tests/infrastructure/adapters/test_allocation_coherency.py"
OWNER = "tests/infrastructure/adapters/test_allocation_coherency_tie_break.py"
SUPPORT = "tests/support/screen_rod_allocation.py"
RETAINED_CASES = (
    "test_allocation_honors_only_option_and_retains_issued_order_on_tie[indices0-False]",
    "test_allocation_honors_only_option_and_retains_issued_order_on_tie[indices1-True]",
    "test_allocation_requires_defender_visible_formation",
    "test_screen_rod_allocation_ranks_issued_choices_by_survivor_coherency",
)
CASES = (
    "test_bounded_validator_calls_and_first_coherent_short_circuit",
    "test_native_defender_tie_break_saves_one_model_with_exact_fork_and_replay",
    "test_native_mixed_ovals_keep_v1_issued_order_without_repair_search",
    "test_tied_ranks_and_constrained_candidates_keep_issued_order[indices0-7]",
    "test_tied_ranks_and_constrained_candidates_keep_issued_order[indices1-12]",
    "test_tied_ranks_and_constrained_candidates_keep_issued_order[indices2-1]",
    "test_unsupported_scope_keeps_the_original_choice_and_skips_hypothetical_cleanup[milli-inch-disagreement]",
    "test_unsupported_scope_keeps_the_original_choice_and_skips_hypothetical_cleanup[missing-unit]",
    "test_unsupported_scope_keeps_the_original_choice_and_skips_hypothetical_cleanup[missing-wounds]",
    "test_unsupported_scope_keeps_the_original_choice_and_skips_hypothetical_cleanup[off-elevation]",
    "test_unsupported_scope_keeps_the_original_choice_and_skips_hypothetical_cleanup[six-models]",
)


class DefenderCoherencyReceipt(TypedDict):
    schema: str
    base: str
    retained_allocation_sha256: str
    retained_attack_count_sha256: str
    retained_manifest_sha256: str
    retained_runtime_fingerprint: str
    manifest_sha256: str
    runtime_fingerprint: str
    policy: dict[str, str]
    retained_test: dict[str, dict[str, object]]
    support_sha256: str
    added_files: dict[str, dict[str, object]]
    retained_cases: list[str]
    added_cases: list[str]


def defender_coherency_test_successor(
    root: Path,
) -> tuple[DefenderCoherencyReceipt, dict[str, dict[str, object]], bytes] | None:
    from scripts.engine_numerical_identity_test_admission import (
        ALLOCATION_COHERENCY_ADDITION,
        ALLOCATION_COHERENCY_SHA256,
        _checked_bytes,  # pyright: ignore[reportPrivateUsage]
    )

    paths = (RECEIPT, OWNER, SUPPORT)
    for name in paths:
        _selection_no_links(root, root / name)
    if not any((root / name).exists() for name in paths):
        return None

    raw = _checked_bytes(root, RECEIPT, RECEIPT_SHA256)
    receipt = cast(DefenderCoherencyReceipt, json.loads(raw, object_pairs_hook=_selection_object))
    historical = json.loads(
        _checked_bytes(root, ALLOCATION_COHERENCY_ADDITION, ALLOCATION_COHERENCY_SHA256),
        object_pairs_hook=_selection_object,
    )
    attack_count = json.loads(
        _checked_bytes(root, ATTACK_COUNT_RECEIPT, ATTACK_COUNT_SHA256),
        object_pairs_hook=_selection_object,
    )
    policy = receipt["policy"]
    test = receipt["retained_test"]
    if (
        receipt.keys() != DefenderCoherencyReceipt.__required_keys__
        or receipt["schema"] != "finite-stage3-defender-coherency-test-v1"
        or receipt["base"] != BASE
        or receipt["retained_allocation_sha256"] != ALLOCATION_COHERENCY_SHA256
        or receipt["retained_attack_count_sha256"] != ATTACK_COUNT_SHA256
        or receipt["retained_manifest_sha256"] != attack_count["manifest_sha256"]
        or receipt["retained_runtime_fingerprint"] != attack_count["runtime_fingerprint"]
        or receipt["manifest_sha256"] == receipt["retained_manifest_sha256"]
        or receipt["runtime_fingerprint"] == receipt["retained_runtime_fingerprint"]
        or policy.keys() != {"before", "after"}
        or policy["before"] != historical["policy_sha256"]
        or policy["before"] == policy["after"]
        or test.keys() != {"before", "after"}
        or test["before"] != historical["added_files"][RETAINED_OWNER]
        or test["before"] == test["after"]
        or receipt["added_files"].keys() != {OWNER}
        or receipt["retained_cases"] != [f"{RETAINED_OWNER}::{case}" for case in RETAINED_CASES]
        or receipt["added_cases"] != [f"{OWNER}::{case}" for case in CASES]
    ):
        raise SystemExit("Defender coherency test successor inventory differs.")
    _checked_bytes(root, SOURCE, policy["after"])
    _checked_bytes(root, SUPPORT, receipt["support_sha256"])
    members = _selection_members({RETAINED_OWNER: test["after"], **receipt["added_files"]}, root)
    return receipt, members, raw


def defender_coherency_runtime(
    root: Path, manifest_sha256: str, runtime_fingerprint: str
) -> tuple[str, str]:
    successor = defender_coherency_test_successor(root)
    if successor is None:
        return manifest_sha256, runtime_fingerprint
    receipt, _, _ = successor
    if (
        receipt["retained_manifest_sha256"] != manifest_sha256
        or receipt["retained_runtime_fingerprint"] != runtime_fingerprint
    ):
        raise SystemExit("Defender coherency tests require the exact ranged attack-count runtime.")
    return receipt["manifest_sha256"], receipt["runtime_fingerprint"]
