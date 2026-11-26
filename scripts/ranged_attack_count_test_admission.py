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


FACTION_REPAIR_RECEIPT = (
    "data/source_audits/ci64_provenance_v1/ranged-attack-count-faction-repair-test-v1.json"
)
FACTION_REPAIR_SHA256 = "e6f609e4efb81fea31efaa37728b593febdd90f6d868f53d319f3e9213a237c5"
FACTION_REPAIR_BASE = "17efed22060afb675b2232ad6f48054f0190ebd7"
FACTION_REPAIR_LHYKHIS = "tests/factions/aeldari/unit/test_lhykhis.py"
FACTION_REPAIR_SUPPORT = (
    "tests/factions/aeldari/lhykhis_helpers.py",
    "tests/factions/aeldari/lhykhis_scripted_attacks.py",
    "tests/support/scripted_attack_rolls.py",
    "tests/support/sorcerer_native.py",
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


def ranged_attack_count_faction_successor(
    root: Path, retained_cutover_sha256: str
) -> tuple[dict[str, dict[str, object]], bytes] | None:
    """Admit only the repaired bytes of two existing faction test owners."""
    from scripts.build_test_shards import CUTOVER_PATH
    from scripts.engine_numerical_identity_test_admission import (
        GAMEPLAY_SORCERER_OWNER,
        STAGE2_FIGHT_SHA256,
        STAGE2_FIGHT_TRANSITION,
        _checked_bytes,  # pyright: ignore[reportPrivateUsage]
    )

    path = root / FACTION_REPAIR_RECEIPT
    _selection_no_links(root, path)
    if not path.exists():
        return None
    raw = _checked_bytes(root, FACTION_REPAIR_RECEIPT, FACTION_REPAIR_SHA256)
    record = json.loads(raw, object_pairs_hook=_selection_object)
    cases = (
        (
            FACTION_REPAIR_LHYKHIS,
            "test_native_attached_target_survives_bodyguard_loss_with_same_mark_identity",
        ),
        (
            FACTION_REPAIR_LHYKHIS,
            "test_native_charge_fight_critical_five_is_lethal_and_turn_expiry_replays",
        ),
        (FACTION_REPAIR_LHYKHIS, "test_native_source_death_does_not_revoke_existing_turn_grant"),
        (FACTION_REPAIR_LHYKHIS, "test_native_source_last_killed_target_has_no_selection"),
        (FACTION_REPAIR_LHYKHIS, "test_native_torrent_hits_without_damage_require_target_choice"),
        (
            GAMEPLAY_SORCERER_OWNER,
            "test_two_native_sorcerers_wrack_the_same_target_without_stacking_movement",
        ),
    )
    if (
        record.keys()
        != {
            "schema",
            "base",
            "retained_attack_count_sha256",
            "retained_cutover_sha256",
            "retained_stage2_fight_cover_sha256",
            "updated_files",
            "support_sha256",
            "repaired_cases",
        }
        or record["schema"] != "finite-ranged-attack-count-faction-repair-test-v1"
        or record["base"] != FACTION_REPAIR_BASE
        or record["retained_attack_count_sha256"] != RECEIPT_SHA256
        or record["retained_cutover_sha256"] != retained_cutover_sha256
        or record["retained_stage2_fight_cover_sha256"] != STAGE2_FIGHT_SHA256
        or record["updated_files"].keys() != {FACTION_REPAIR_LHYKHIS, GAMEPLAY_SORCERER_OWNER}
        or record["support_sha256"].keys() != set(FACTION_REPAIR_SUPPORT)
        or record["repaired_cases"] != [f"{owner}::{case}" for owner, case in cases]
    ):
        raise SystemExit("Ranged attack-count faction repair admission inventory differs.")
    _checked_bytes(root, RECEIPT, RECEIPT_SHA256)
    cutover = json.loads(
        _checked_bytes(root, CUTOVER_PATH, retained_cutover_sha256),
        object_pairs_hook=_selection_object,
    )
    fight = json.loads(
        _checked_bytes(root, STAGE2_FIGHT_TRANSITION, STAGE2_FIGHT_SHA256),
        object_pairs_hook=_selection_object,
    )
    predecessor = {
        FACTION_REPAIR_LHYKHIS: cutover["active_files"][FACTION_REPAIR_LHYKHIS],
        GAMEPLAY_SORCERER_OWNER: fight["test"][GAMEPLAY_SORCERER_OWNER]["after"],
    }
    changes = record["updated_files"]
    for name, before in predecessor.items():
        if set(changes[name]) != {"before", "after"} or changes[name]["before"] != before:
            raise SystemExit("Ranged attack-count faction repair predecessor differs: " + name)
    for name, digest in record["support_sha256"].items():
        _checked_bytes(root, name, digest)
    return _selection_members({name: row["after"] for name, row in changes.items()}, root), raw


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
