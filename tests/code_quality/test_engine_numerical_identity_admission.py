"""Finite numerical source admission and current LPT inventory controls."""

from __future__ import annotations

import hashlib
import json
import subprocess
from pathlib import Path
from typing import Any, cast

import pytest
from scripts import build_test_shards as sharding
from scripts import engine_numerical_identity_test_admission as selection
from scripts import fools_flight_test_admission as fools
from scripts import stage2_ground_charge_test_admission as ground_charge
from scripts.canonical_circle_test_admission import ADDITION as CIRCLE_ADDITION
from scripts.canonical_polygon_pairs_test_admission import ADDITION as PAIRS_ADDITION
from scripts.canonical_polygon_queries_test_admission import ADDITION as QUERIES_ADDITION
from scripts.canonical_polygon_test_admission import ADDITION as POLYGON_ADDITION
from scripts.exact_contact_test_admission import ADDITION as CONTACT_ADDITION
from scripts.milli_inch_test_admission import ADDITION as FOUNDATION_ADDITION
from scripts.milli_inch_test_admission import MANIFEST
from scripts.milli_inch_test_admission import SOURCE as FOUNDATION_SOURCE
from scripts.precision_profile_test_admission import ADDITION as PROFILE_ADDITION
from scripts.symbolic_milli_inch_test_admission import ADDITION as SYMBOLIC_ADDITION

ROOT = Path(__file__).resolve().parents[2]
BASE = "b231d7cedea54e123a9211fd775e2910c87d2f18"
EXACT_MOVEMENT_REVISION = "250c5f655851f523a8932a1233e72ab4eace56ce"
IDENTITY_REVISION = "d81dc3fd9fd9625205dcc91282fd89f588a75bfb"


def _record(name: str) -> dict[str, Any]:
    return cast(dict[str, Any], json.loads((ROOT / name).read_bytes()))


def _transition(
    root: Path,
) -> tuple[dict[str, dict[str, object]], dict[str, dict[str, object]], bytes]:
    raw = (ROOT / sharding.CUTOVER_PATH).read_bytes()
    result = selection.engine_numerical_identity_test_transition(
        root, hashlib.sha256(raw).hexdigest()
    )
    assert result is not None
    return result


@pytest.fixture
def transition_snapshot(tmp_path: Path) -> Path:
    records = (
        selection.ADDITION,
        CONTACT_ADDITION,
        PAIRS_ADDITION,
        QUERIES_ADDITION,
        FOUNDATION_ADDITION,
        PROFILE_ADDITION,
        SYMBOLIC_ADDITION,
        POLYGON_ADDITION,
        CIRCLE_ADDITION,
        "data/source_audits/ci64_provenance_v1/speedup-test-transition-v1.json",
    )
    names = {MANIFEST, FOUNDATION_SOURCE, *records}
    for name in records:
        record = _record(name)
        for key in ("sources", "updated_files", "added_files"):
            names.update(record.get(key, {}))
    for name in names:
        destination = tmp_path / name
        destination.parent.mkdir(parents=True, exist_ok=True)
        contents = subprocess.check_output(
            ["git", "show", IDENTITY_REVISION + ":" + name], cwd=ROOT
        )
        destination.write_bytes(contents)
    _transition(tmp_path)
    return tmp_path


def test_identity_transition_rejects_every_changed_runtime_source(
    transition_snapshot: Path,
) -> None:
    for name in _record(selection.ADDITION)["sources"]:
        target = transition_snapshot / name
        original = target.read_bytes()
        target.write_bytes(original + b"\n")
        with pytest.raises(SystemExit, match="source bytes differ"):
            _transition(transition_snapshot)
        target.write_bytes(original)
    target = transition_snapshot / MANIFEST
    manifest = json.loads(target.read_bytes())
    manifest["fingerprint"] = "0" * 64
    target.write_text(json.dumps(manifest))
    with pytest.raises(SystemExit, match="retained cutover and runtime"):
        _transition(transition_snapshot)

    record = _record(selection.EXACT_MOVEMENT_ADDITION)
    for name in (
        MANIFEST,
        selection.EXACT_MOVEMENT_ADDITION,
        selection.EXACT_MOVEMENT_OWNER,
        *record["sources"],
    ):
        destination = transition_snapshot / name
        destination.parent.mkdir(parents=True, exist_ok=True)
        contents = (
            subprocess.check_output(["git", "show", EXACT_MOVEMENT_REVISION + ":" + name], cwd=ROOT)
            if name == MANIFEST
            else (ROOT / name).read_bytes()
        )
        destination.write_bytes(contents)
    cutover_digest = hashlib.sha256((ROOT / sharding.CUTOVER_PATH).read_bytes()).hexdigest()
    accepted = selection.exact_movement_test_transition(transition_snapshot, cutover_digest)
    assert accepted is not None
    assert selection.EXACT_MOVEMENT_OWNER in accepted[1]
    for name in record["sources"]:
        target = transition_snapshot / name
        original = target.read_bytes()
        target.write_bytes(original + b"\n")
        with pytest.raises(SystemExit, match="source bytes differ"):
            selection.exact_movement_test_transition(transition_snapshot, cutover_digest)
        target.write_bytes(original)


def test_identity_transition_preserves_original_recipe_and_speedup_evidence(
    transition_snapshot: Path,
) -> None:
    for name in (
        "src/warhammer40k_core/adapters/checkpoint_reconstruction.py",
        "data/source_audits/ci64_provenance_v1/speedup-test-transition-v1.json",
    ):
        original = subprocess.check_output(["git", "show", BASE + ":" + name], cwd=ROOT)
        assert (ROOT / name).read_bytes() == original
    updated, added, _ = _transition(transition_snapshot)
    speedup = _record("data/source_audits/ci64_provenance_v1/speedup-test-transition-v1.json")
    assert set(speedup["updated_files"]) <= set(updated)
    assert selection.OWNER in added


def test_identity_inventory_uses_current_twelve_shards_and_native_cohort() -> None:
    active_files = sharding.behavioral_selection(ROOT).active_files
    assert selection.OWNER in active_files
    assert selection.STAGE2_FIGHT_OWNER in active_files
    groups = [
        set((ROOT / f"ci/test_shards/shard-{index}.txt").read_text().splitlines())
        for index in range(1, 13)
    ]
    assert sum(selection.OWNER in group for group in groups) == 1
    cohort = sharding.covered_native_checkpoint_cohort()
    assert {
        sharding.SERIAL_BEHAVIORAL_CASE,
        selection.OPENING_SHADOW_FORM_OWNER,
        selection.OPENING_MOVEMENT_UNIT_OWNER,
    } <= cohort
    assert sum(cohort <= group for group in groups) == 1
    summary = _record("ci/test_shards/durations.json")
    current = sharding.summary_case_seconds(summary)
    fight = _record(selection.STAGE2_FIGHT_TRANSITION)
    base_manifest = json.loads(
        subprocess.check_output(
            ["git", "show", selection.STAGE2_MELEE_RESTORE_BASE + ":" + MANIFEST], cwd=ROOT
        )
    )
    assert fight["runtime_fingerprint"] == base_manifest["fingerprint"]
    source_before = subprocess.check_output(
        ["git", "show", selection.STAGE2_FIGHT_BASE + ":" + selection.STAGE2_FIGHT_SOURCE],
        cwd=ROOT,
    )
    assert (
        fight["source"][selection.STAGE2_FIGHT_SOURCE]["before"]
        == hashlib.sha256(source_before).hexdigest()
    )
    assert (
        fight["test"][selection.STAGE2_FIGHT_OWNER]["before"]
        == _record(sharding.CUTOVER_PATH)["active_files"][selection.STAGE2_FIGHT_OWNER]
    )
    assert (
        fight["test"][selection.GAMEPLAY_SORCERER_OWNER]["before"]
        == _record(selection.GAMEPLAY_BUDGET_TRANSITION)["tests"][selection.GAMEPLAY_SORCERER_OWNER]
    )
    assert sum(selection.STAGE2_FIGHT_OWNER in group for group in groups) == 1
    counteroffensive = _record(selection.COUNTEROFFENSIVE_TRANSITION)
    assert counteroffensive["runtime_fingerprint"] == fight["runtime_fingerprint"]
    assert (
        counteroffensive["retained_stage2_fight_cover_sha256"]
        == hashlib.sha256((ROOT / selection.STAGE2_FIGHT_TRANSITION).read_bytes()).hexdigest()
    )
    owner = selection.COUNTEROFFENSIVE_OWNER
    preimage = subprocess.check_output(
        ["git", "show", selection.COUNTEROFFENSIVE_BASE + ":" + owner], cwd=ROOT
    )
    assert (
        counteroffensive["test"][owner]["before"]
        == _record(sharding.CUTOVER_PATH)["active_files"][owner]
    )
    assert (
        counteroffensive["test"][owner]["before"]["sha256"] == hashlib.sha256(preimage).hexdigest()
    )
    assert owner in active_files
    assert sum(owner in group for group in groups) == 1
    melee_restore = _record(selection.STAGE2_MELEE_RESTORE_TRANSITION)
    assert melee_restore["test"][owner]["before"] == counteroffensive["test"][owner]["after"]
    for source in (
        selection.STAGE2_MELEE_RESTORE_SOURCE,
        selection.STAGE2_MELEE_HISTORY_SOURCE,
        selection.STAGE2_MELEE_FRAME_SOURCE,
    ):
        source_before = subprocess.check_output(
            ["git", "show", selection.STAGE2_MELEE_RESTORE_BASE + ":" + source], cwd=ROOT
        )
        assert (
            melee_restore["source"][source]["before"] == hashlib.sha256(source_before).hexdigest()
        )
    reroll = _record(selection.STAGE2_FIGHT_REROLL_TRANSITION)
    reroll_base_manifest = json.loads(
        subprocess.check_output(
            ["git", "show", selection.STAGE2_FIGHT_REROLL_BASE + ":" + MANIFEST], cwd=ROOT
        )
    )
    assert melee_restore["runtime_fingerprint"] == reroll_base_manifest["fingerprint"]
    terminal = _record(selection.TERMINAL_RESTORE_TRANSITION)
    terminal_base_manifest = json.loads(
        subprocess.check_output(
            ["git", "show", selection.TERMINAL_RESTORE_BASE + ":" + MANIFEST], cwd=ROOT
        )
    )
    assert reroll["runtime_fingerprint"] == terminal_base_manifest["fingerprint"]
    cavalcade_base_manifest = json.loads(
        subprocess.check_output(
            ["git", "show", "77b6f8f6fdcd88bb5eaff21495b28a2972213cbf:" + MANIFEST],
            cwd=ROOT,
        )
    )
    assert terminal["runtime_fingerprint"] == cavalcade_base_manifest["fingerprint"]
    shadow = _record(selection.ROUND_FIVE_SHADOW_TRANSITION)
    shadow_manifest = json.loads(
        subprocess.check_output(
            ["git", "show", selection.ROUND_FIVE_SHADOW_BASE + ":" + MANIFEST], cwd=ROOT
        )
    )
    assert shadow_manifest["fingerprint"] == selection.CAVALCADE_AUTHORITY_RUNTIME
    assert shadow["retained_runtime_fingerprint"] == selection.CAVALCADE_AUTHORITY_RUNTIME
    close_quarters = _record(selection.CLOSE_QUARTERS_TRANSITION)
    close_quarters_base = json.loads(
        subprocess.check_output(
            ["git", "show", selection.CLOSE_QUARTERS_BASE + ":" + MANIFEST], cwd=ROOT
        )
    )
    assert close_quarters_base["fingerprint"] == shadow["runtime_fingerprint"]
    assert close_quarters["retained_runtime_fingerprint"] == shadow["runtime_fingerprint"]
    strict_replay = _record(selection.STRICT_REPLAY_TRANSITION)
    strict_replay_base_manifest = json.loads(
        subprocess.check_output(
            ["git", "show", selection.STRICT_REPLAY_BASE + ":" + MANIFEST], cwd=ROOT
        )
    )
    assert strict_replay_base_manifest["fingerprint"] == close_quarters["runtime_fingerprint"]
    assert strict_replay["retained_runtime_fingerprint"] == close_quarters["runtime_fingerprint"]
    allocation = _record(selection.ALLOCATION_COHERENCY_ADDITION)
    assert allocation["retained_runtime_fingerprint"] == strict_replay["runtime_fingerprint"]
    cover_event = _record(selection.COVER_EVENT_IDENTITY_ADDITION)
    assert cover_event["retained_runtime_fingerprint"] == allocation["runtime_fingerprint"]
    opening = _record(selection.OPENING_SHADOW_FORM_TRANSITION)
    opening_base_manifest = json.loads(
        subprocess.check_output(
            ["git", "show", selection.OPENING_SHADOW_FORM_BASE + ":" + MANIFEST], cwd=ROOT
        )
    )
    assert cover_event["runtime_fingerprint"] == opening_base_manifest["fingerprint"]
    assert opening["retained_runtime_fingerprint"] == cover_event["runtime_fingerprint"]
    movement = _record(selection.OPENING_MOVEMENT_UNIT_ADDITION)
    assert movement["retained_runtime_fingerprint"] == opening["runtime_fingerprint"]
    monster_mash = _record(selection.MONSTER_MASH_ADDITION)
    assert monster_mash["retained_runtime_fingerprint"] == movement["runtime_fingerprint"]
    shooting_visibility = _record(selection.SHOOTING_VISIBILITY_TRANSITION)
    shooting_base = json.loads(
        subprocess.check_output(
            ["git", "show", selection.SHOOTING_VISIBILITY_BASE + ":" + MANIFEST], cwd=ROOT
        )
    )
    assert shooting_base["fingerprint"] == monster_mash["runtime_fingerprint"]
    assert (
        shooting_visibility["retained_runtime_fingerprint"] == monster_mash["runtime_fingerprint"]
    )
    fight_reroll = _record(selection.MONSTER_MASH_ATTACK_REROLL_TRANSITION)
    fight_reroll_base = json.loads(
        subprocess.check_output(
            ["git", "show", selection.MONSTER_MASH_ATTACK_REROLL_BASE + ":" + MANIFEST], cwd=ROOT
        )
    )
    assert fight_reroll_base["fingerprint"] == shooting_visibility["runtime_fingerprint"]
    assert fight_reroll["retained_runtime_fingerprint"] == fight_reroll_base["fingerprint"]
    round4 = _record(selection.ROUND4_BATTLE_SHOCK_TRANSITION)
    round4_base = json.loads(
        subprocess.check_output(
            ["git", "show", selection.ROUND4_BATTLE_SHOCK_BASE + ":" + MANIFEST], cwd=ROOT
        )
    )
    assert round4_base["fingerprint"] == fight_reroll["runtime_fingerprint"]
    assert round4["retained_runtime_fingerprint"] == round4_base["fingerprint"]
    malice = _record(selection.ROUND4_MALICE_BEARER_TRANSITION)
    malice_base = selection.ROUND4_MALICE_BEARER_BASE
    malice_base_manifest = json.loads(
        subprocess.check_output(["git", "show", malice_base + ":" + MANIFEST], cwd=ROOT)
    )
    assert malice_base_manifest["fingerprint"] == round4["runtime_fingerprint"]
    assert malice["retained_runtime_fingerprint"] == malice_base_manifest["fingerprint"]
    shalaxi = _record(selection.ROUND3_SHALAXI_TRANSITION)
    shalaxi_base = selection.ROUND3_SHALAXI_BASE
    shalaxi_base_manifest = json.loads(
        subprocess.check_output(["git", "show", shalaxi_base + ":" + MANIFEST], cwd=ROOT)
    )
    assert shalaxi_base_manifest["fingerprint"] == malice["runtime_fingerprint"]
    assert shalaxi["retained_runtime_fingerprint"] == malice["runtime_fingerprint"]
    charge = _record(selection.GROUND_CHARGE_TEST_TRANSITION)
    assert charge["retained_runtime_fingerprint"] == shalaxi["runtime_fingerprint"]
    group_charge = _record(ground_charge.GROUP_TRANSITION)
    assert group_charge["retained_runtime_fingerprint"] == charge["runtime_fingerprint"]
    shooting = _record(ground_charge.SHOOTING_TRANSITION)
    assert shooting["retained_runtime_fingerprint"] == group_charge["runtime_fingerprint"]
    shooting_base_test = subprocess.check_output(
        ["git", "show", ground_charge.SHOOTING_BASE + ":" + ground_charge.SHOOTING_OWNER],
        cwd=ROOT,
    )
    assert shooting["test"]["before"]["sha256"] == hashlib.sha256(shooting_base_test).hexdigest()
    assert sum(ground_charge.SHOOTING_OWNER in group for group in groups) == 1
    shooting_cases = {
        ground_charge.SHOOTING_OWNER
        + f"::test_normal_shooting_policy_uses_the_projected_offer_and_native_submission[{fire}]"
        for fire in (False, True)
    }
    shooting_cases.update(
        ground_charge.SHOOTING_OWNER + "::" + name
        for name in (
            "test_normal_shooting_ranks_equal_legal_volleys_by_target_id_in_reverse_order",
            "test_normal_shooting_rejects_one_over_each_candidate_limit[rows]",
            "test_normal_shooting_rejects_one_over_each_candidate_limit[targets]",
            "test_normal_shooting_binds_all_candidates_after_one_observation_decode",
        )
    )
    assert sum(ground_charge.GROUP_OWNER in group for group in groups) == 1
    rigid_charge = _record(ground_charge.RIGID_TRANSITION)
    assert rigid_charge["base"] == ground_charge.RIGID_BASE
    assert rigid_charge["retained_group_charge_sha256"] == ground_charge.GROUP_TRANSITION_SHA256
    assert set(rigid_charge["added_files"]) == {ground_charge.RIGID_OWNER}
    assert ground_charge.RIGID_OWNER in active_files
    assert sum(ground_charge.RIGID_OWNER in group for group in groups) == 1
    retry = _record(ground_charge.RETRY_TRANSITION)
    assert retry["base"] == ground_charge.RETRY_BASE
    assert retry["reviewed_runtime_commit"] == ground_charge.RETRY_REVIEWED_RUNTIME
    assert set(retry["sources"]) == set(ground_charge.SOURCES)
    assert set(retry["added_files"]) == {ground_charge.RETRY_OWNER}
    assert retry["added_cases"] == [
        f"{ground_charge.RETRY_OWNER}::{name}" for name in ground_charge.RETRY_CASES
    ]
    assert sum(ground_charge.RETRY_OWNER in group for group in groups) == 1
    for source, row in group_charge["sources"].items():
        assert row["before"] == charge["sources"][source]
        current_digest = row["after"]
        if source == ground_charge.RIGID_SOURCE:
            predecessor = subprocess.check_output(
                ["git", "show", ground_charge.RIGID_BASE + ":" + source], cwd=ROOT
            )
            assert row["after"] == hashlib.sha256(predecessor).hexdigest()
            assert rigid_charge["source"]["before"] == row["after"]
            current_digest = rigid_charge["source"]["after"]
        assert retry["sources"][source]["before"] == current_digest
        assert (
            retry["sources"][source]["after"]
            == hashlib.sha256((ROOT / source).read_bytes()).hexdigest()
        )
    assert sum(ground_charge.OWNER in group for group in groups) == 1
    charge_cases = {
        ground_charge.OWNER + "::" + name
        for name in (
            "test_ground_charge_generation_is_stable_and_limits_are_typed",
            "test_ground_charge_ranks_only_native_accepts_and_checks_binding",
            "test_ground_charge_receipt_deadline_preserves_live_session[receipt-before-exit]",
            "test_ground_charge_receipt_deadline_preserves_live_session[unresolved-after-accept]",
        )
    }
    charge_cases.update(
        ground_charge.GROUP_OWNER + "::" + name
        for name in (
            "test_group_charge_generates_distinct_complete_witnesses",
            "test_group_charge_commits_a_native_accept",
            "test_group_charge_accepts_attached_target_with_four_surviving_bodyguards",
            "test_group_charge_objective_preprocessing_exhausts_before_geometry[0]",
            "test_group_charge_objective_preprocessing_exhausts_before_geometry[1]",
            "test_group_charge_objective_preprocessing_exhausts_before_geometry[1000]",
            "test_group_charge_objective_inventory_limits[areas]",
            "test_group_charge_objective_inventory_limits[vertices]",
            "test_group_charge_objective_inventory_limits[linked-vertices]",
            "test_group_charge_ranks_objective_reach_ahead_of_shorter_accepted_travel",
        )
    )
    charge_cases.update(
        ground_charge.RIGID_OWNER + "::" + name
        for name in (
            "test_rigid_group_charge_certifies_the_exact_mixed_endpoint_witness",
            "test_rigid_group_charge_native_rejects_a_column_that_stops_outside_engagement",
            "test_group_charge_keeps_grid_at_rounded_reachability_bound",
        )
    )
    screen = _record(ground_charge.SCREEN_TRANSITION)
    pending_path = (
        "data/source_audits/ci64_provenance_v1/stage2-pending-battle-shock-transition-v1.json"
    )
    pending = _record(pending_path)
    terror = _record(selection.DAEMONIC_TERROR_TRANSITION)
    pending_base = "161378a16c4557228b2af45db0d311a522eb3f8f"
    assert pending["base"] == pending_base
    pending_base_manifest = json.loads(
        subprocess.check_output(["git", "show", pending_base + ":" + MANIFEST], cwd=ROOT)
    )
    assert screen["runtime_fingerprint"] == pending_base_manifest["fingerprint"]
    assert pending["retained_runtime_fingerprint"] == screen["runtime_fingerprint"]
    assert (
        pending["retained_screen_movement_sha256"]
        == hashlib.sha256((ROOT / ground_charge.SCREEN_TRANSITION).read_bytes()).hexdigest()
    )
    regeneration = _record(
        "data/source_audits/ci64_provenance_v1/grotesque-regeneration-transition-v1.json"
    )
    regeneration_base = "d9185cf53a2816ab666f3c1b16410b960a3d1cc7"
    assert regeneration["base"] == regeneration_base
    regeneration_base_manifest = json.loads(
        subprocess.check_output(["git", "show", regeneration_base + ":" + MANIFEST], cwd=ROOT)
    )
    assert pending["runtime_fingerprint"] == regeneration_base_manifest["fingerprint"]
    assert regeneration["retained_runtime_fingerprint"] == pending["runtime_fingerprint"]
    assert (
        regeneration["retained_transition_sha256"]
        == hashlib.sha256((ROOT / pending_path).read_bytes()).hexdigest()
    )
    rigid_base_manifest = json.loads(
        subprocess.check_output(
            ["git", "show", ground_charge.RIGID_BASE + ":" + MANIFEST], cwd=ROOT
        )
    )
    assert rigid_base_manifest["fingerprint"] == regeneration["runtime_fingerprint"]
    healing_owner = "tests/rules/section02/test_02_02_04_healing.py"
    assert sum(healing_owner in group for group in groups) == 1
    assert (
        regeneration["test"]["before"]
        == _record(sharding.CUTOVER_PATH)["active_files"][healing_owner]
    )
    assert (
        regeneration["test"]["after"]["sha256"]
        == hashlib.sha256((ROOT / healing_owner).read_bytes()).hexdigest()
    )
    assert rigid_charge["retained_runtime_fingerprint"] == regeneration["runtime_fingerprint"]
    brass = _record("data/source_audits/ci64_provenance_v1/sheathed-in-brass-transition-v1.json")
    rigid_manifest = json.loads(
        subprocess.check_output(["git", "show", brass["base"] + ":" + MANIFEST], cwd=ROOT)
    )
    assert rigid_manifest["fingerprint"] == rigid_charge["runtime_fingerprint"]
    assert (
        brass["retained_transition_sha256"]
        == hashlib.sha256((ROOT / ground_charge.RIGID_TRANSITION).read_bytes()).hexdigest()
    )
    assert brass["retained_runtime_fingerprint"] == rigid_charge["runtime_fingerprint"]
    skulls = _record(selection.BLOOD_BEGETS_SKULLS_TRANSITION)
    assert skulls["retained_runtime_fingerprint"] == brass["runtime_fingerprint"]
    shooting_skulls = _record(selection.SKULLS_BEGET_BLOOD_TRANSITION)
    previous_manifest = json.loads(
        subprocess.check_output(["git", "show", shooting_skulls["base"] + ":" + MANIFEST], cwd=ROOT)
    )
    flight_path = "data/source_audits/ci64_provenance_v1/stage3-flight-normal-move-test-v1.json"
    flight = _record(flight_path)
    flight_base_manifest = json.loads(
        subprocess.check_output(["git", "show", flight["base"] + ":" + MANIFEST], cwd=ROOT)
    )
    assert shooting_skulls["runtime_fingerprint"] == flight_base_manifest["fingerprint"]
    assert flight["retained_runtime_fingerprint"] == shooting_skulls["runtime_fingerprint"]
    audit_root = ROOT / "data/source_audits/ci64_provenance_v1"
    flight_predecessors = (
        audit_root / "sheathed-in-brass-transition-v1.json",
        ROOT / selection.BLOOD_BEGETS_SKULLS_TRANSITION,
        audit_root / "stage3-melee-profile-test-v1.json",
        ROOT / selection.SKULLS_BEGET_BLOOD_TRANSITION,
    )
    assert (
        flight["retained_transition_sha256"]
        == hashlib.sha256(b"\0".join(path.read_bytes() for path in flight_predecessors)).hexdigest()
    )
    wrath = _record(selection.WRATH_UNDENIABLE_TRANSITION)
    assert wrath["base"] == "bdc1b2111530576a71bf3391564d5a9e9c356be0"
    wrath_base_manifest = json.loads(
        subprocess.check_output(["git", "show", wrath["base"] + ":" + MANIFEST], cwd=ROOT)
    )
    assert (
        wrath["retained_runtime_fingerprint"]
        == flight["runtime_fingerprint"]
        == wrath_base_manifest["fingerprint"]
    )
    assert (
        wrath["retained_transition_sha256"]
        == hashlib.sha256(
            b"\0".join(path.read_bytes() for path in (*flight_predecessors, ROOT / flight_path))
        ).hexdigest()
    )
    charge_flight = _record(
        "data/source_audits/ci64_provenance_v1/pre-roll-charge-flight-test-v1.json"
    )
    charge_flight_base_manifest = json.loads(
        subprocess.check_output(["git", "show", charge_flight["base"] + ":" + MANIFEST], cwd=ROOT)
    )
    assert (
        wrath["runtime_fingerprint"]
        == charge_flight_base_manifest["fingerprint"]
        == charge_flight["retained_runtime_fingerprint"]
    )
    assert (
        charge_flight["retained_transition_sha256"]
        == hashlib.sha256((ROOT / selection.WRATH_UNDENIABLE_TRANSITION).read_bytes()).hexdigest()
    )
    gore = _record(selection.GORE_HUNGRY_ONSLAUGHT_TRANSITION)
    gore_base_manifest = json.loads(
        subprocess.check_output(["git", "show", gore["base"] + ":" + MANIFEST], cwd=ROOT)
    )
    assert gore["base"] == "f69eda2040ab55db4dd18686eee69edafcca9dd2"
    assert gore["retained_runtime_fingerprint"] == (charge_flight["runtime_fingerprint"])
    assert charge_flight["runtime_fingerprint"] == gore_base_manifest["fingerprint"]
    assert (
        gore["retained_transition_sha256"]
        == hashlib.sha256(
            (
                ROOT / "data/source_audits/ci64_provenance_v1/pre-roll-charge-flight-test-v1.json"
            ).read_bytes()
        ).hexdigest()
    )
    gore_owner = selection.GORE_HUNGRY_ONSLAUGHT_OWNER
    assert set(gore["added_files"]) == {gore_owner}
    assert gore_owner in active_files
    assert sum(gore_owner in group for group in groups) == 1
    assert (
        gore["added_files"][gore_owner]["sha256"]
        == hashlib.sha256((ROOT / gore_owner).read_bytes()).hexdigest()
    )
    gore_cases = {
        gore_owner + "::test_gore_hungry_onslaught_" + case
        for case in (
            "movement_path_and_replay",
            "later_movement_window",
            "charge_path_and_replay",
            "ineligible_window[movement-0-owner]",
            "ineligible_window[movement-1-opponent]",
            "ineligible_window[charge-1-opponent]",
            "ineligible_window[shooting-1-owner]",
        )
    }
    wall = _record(selection.CHARGE_FLIGHT_WALL_TRANSITION)
    assert wall["base"] == selection.CHARGE_FLIGHT_WALL_BASE
    wall_base_manifest = json.loads(
        subprocess.check_output(["git", "show", wall["base"] + ":" + MANIFEST], cwd=ROOT)
    )
    assert wall["retained_runtime_fingerprint"] == gore["runtime_fingerprint"]
    assert wall["retained_runtime_fingerprint"] == wall_base_manifest["fingerprint"]
    from scripts import dark_pact_test_admission as dark_pact

    pact = _record(dark_pact.RECEIPT)
    assert pact["base"] == dark_pact.BASE
    assert pact["retained_runtime_fingerprint"] == wall["runtime_fingerprint"]
    assert (
        pact["retained_transition_sha256"]
        == hashlib.sha256((ROOT / selection.CHARGE_FLIGHT_WALL_TRANSITION).read_bytes()).hexdigest()
    )
    assert retry["retained_runtime_fingerprint"] == pact["runtime_fingerprint"]
    assert (
        retry["retained_transition_sha256"]
        == hashlib.sha256((ROOT / dark_pact.RECEIPT).read_bytes()).hexdigest()
    )
    combined = _record(selection.COMBINED_CHARGE_TRANSITION)
    assert combined["base"] == selection.COMBINED_CHARGE_BASE
    assert retry["runtime_fingerprint"] == combined["ground_charge_runtime_fingerprint"]
    assert (
        combined["dark_pact_receipt_sha256"]
        == hashlib.sha256((ROOT / dark_pact.RECEIPT).read_bytes()).hexdigest()
    )
    assert sum(dark_pact.NEW_TEST in group for group in groups) == 1
    assert len([node for node in current if node.startswith(dark_pact.NEW_TEST + "::")]) == 21
    base_weights = json.loads(
        subprocess.check_output(
            ["git", "show", dark_pact.BASE + ":ci/test_shards/durations.json"], cwd=ROOT
        )
    )["case_seconds"]
    assert all(current[node] == seconds for node, seconds in base_weights.items())
    fools_record = _record(fools.TRANSITION)
    flight_base_manifest = json.loads(
        subprocess.check_output(["git", "show", fools.BASE + ":" + MANIFEST], cwd=ROOT)
    )
    assert pact["runtime_fingerprint"] == flight_base_manifest["fingerprint"]
    assert pact["runtime_fingerprint"] == fools_record["retained_runtime_fingerprint"]
    landed_manifest = subprocess.check_output(
        ["git", "show", selection.COMBINED_CHARGE_BASE + ":" + MANIFEST], cwd=ROOT
    )
    assert combined["landed_manifest_sha256"] == hashlib.sha256(landed_manifest).hexdigest()
    assert combined["landed_runtime_fingerprint"] == json.loads(landed_manifest)["fingerprint"]
    assert fools_record["runtime_fingerprint"] == combined["landed_runtime_fingerprint"]
    flight_raw = (ROOT / fools.TRANSITION).read_bytes()
    retry_raw = (ROOT / ground_charge.RETRY_TRANSITION).read_bytes()
    assert _record(MANIFEST)["fingerprint"] == selection.combined_charge_runtime(
        ROOT, flight_raw, retry_raw
    )
    with pytest.raises(SystemExit, match="Combined Charge admission predecessor differs"):
        selection.combined_charge_runtime(ROOT, flight_raw, retry_raw + b" ")
    assert (
        fools_record["retained_transition_sha256"]
        == hashlib.sha256((ROOT / dark_pact.RECEIPT).read_bytes()).hexdigest()
    )
    assert (ROOT / dark_pact.RECEIPT).read_bytes() == subprocess.check_output(
        ["git", "show", fools.BASE + ":" + dark_pact.RECEIPT], cwd=ROOT
    )
    flight_base_weights = json.loads(
        subprocess.check_output(
            ["git", "show", fools.BASE + ":ci/test_shards/durations.json"], cwd=ROOT
        )
    )
    current_weights = _record("ci/test_shards/durations.json")
    for weights in ("files", "case_seconds"):
        assert all(
            current_weights[weights][node] == seconds
            for node, seconds in flight_base_weights[weights].items()
        )
    assert set(fools_record["replaced_sources"]) == fools.REPLACED_SOURCES
    for name, binding in fools_record["replaced_sources"].items():
        assert (
            binding["before"]
            == hashlib.sha256(
                subprocess.check_output(["git", "show", fools.BASE + ":" + name], cwd=ROOT)
            ).hexdigest()
        )
        assert binding["after"] == hashlib.sha256((ROOT / name).read_bytes()).hexdigest()
    assert fools_record["new_sources"] == {
        fools.NEW_SOURCE: hashlib.sha256((ROOT / fools.NEW_SOURCE).read_bytes()).hexdigest(),
    }
    assert fools.OWNER in active_files
    assert sum(fools.OWNER in group for group in groups) == 1
    assert set(fools_record["added_files"]) == {fools.OWNER}
    assert (
        fools_record["added_files"][fools.OWNER]["sha256"]
        == hashlib.sha256((ROOT / fools.OWNER).read_bytes()).hexdigest()
    )
    fools_cases = {
        fools.OWNER + "::" + name
        for name in (
            "test_fools_flight_native_fall_back_charge_resume_and_replay",
            "test_fools_flight_unavailable_at_one_cp",
            "test_fools_flight_short_roll_resumes_opponent_movement",
            "test_fools_flight_stampede_resolves_before_murdercall_and_replays",
        )
    }
    predecessor_path = selection.GORE_HUNGRY_ONSLAUGHT_TRANSITION
    assert (
        wall["retained_transition_sha256"]
        == hashlib.sha256((ROOT / predecessor_path).read_bytes()).hexdigest()
    )
    for name, binding in wall["sources"].items():
        base_bytes = subprocess.check_output(
            ["git", "show", selection.CHARGE_FLIGHT_WALL_BASE + ":" + name], cwd=ROOT
        )
        assert binding["before"] == hashlib.sha256(base_bytes).hexdigest()
        assert binding["after"] == hashlib.sha256((ROOT / name).read_bytes()).hexdigest()
    wall_owner = selection.CHARGE_FLIGHT_WALL_OWNER
    onslaught_owner = selection.CHARGE_FLIGHT_ONSLAUGHT_OWNER
    assert set(wall["added_files"]) == {wall_owner, onslaught_owner}
    for admitted_owner in (wall_owner, onslaught_owner):
        assert admitted_owner in active_files
        assert sum(admitted_owner in group for group in groups) == 1
        assert (
            wall["added_files"][admitted_owner]["sha256"]
            == hashlib.sha256((ROOT / admitted_owner).read_bytes()).hexdigest()
        )
    wall_cases = {
        wall_owner + "::test_dense_wall_native_flight_advantage_replays",
        wall_owner + "::test_barrier_flight_preserves_open_board_ground_choice",
        *(
            wall_owner + "::test_wall_charge_abstains_without_a_separated_bound[" + case + "]"
            for case in ("low", "short", "rotated", "uncertified-endpoints", "bad-witness")
        ),
    }
    onslaught_cases = {
        onslaught_owner + "::" + name
        for name in (
            "test_no_cp_keeps_the_wall_proof",
            "test_early_offer_distinguishes_held_cp_from_a_live_grant[active-grant]",
            "test_early_offer_distinguishes_held_cp_from_a_live_grant[held-cp]",
            "test_other_unit_spend_is_not_a_mover_grant",
            "test_flight_does_not_gain_distance_or_refund_penalty",
            "test_real_late_spend_changes_ground_only_if_authorized[absent]",
            "test_real_late_spend_changes_ground_only_if_authorized[decline]",
            "test_real_late_spend_changes_ground_only_if_authorized[spend]",
            "test_native_late_grant_leaves_declared_flight_unchanged[decline]",
            "test_native_late_grant_leaves_declared_flight_unchanged[spend]",
        )
    }
    charge_flight_owner = "tests/infrastructure/adapters/test_charge_flight_admission.py"
    assert set(charge_flight["added_files"]) == {charge_flight_owner}
    assert charge_flight_owner in active_files
    assert sum(charge_flight_owner in group for group in groups) == 1
    assert (
        charge_flight["added_files"][charge_flight_owner]["sha256"]
        == hashlib.sha256((ROOT / charge_flight_owner).read_bytes()).hexdigest()
    )
    charge_flight_cases = {
        charge_flight_owner + "::" + name
        for name in (
            "test_charge_flight_admits_native_offer_without_claiming_a_minimum",
            "test_unmodified_charge_probability_synthetic_controls[7-7-expected0]",
            "test_unmodified_charge_probability_synthetic_controls[10-6-expected1]",
            "test_unmodified_charge_probability_synthetic_controls[9-7-expected2]",
        )
    }
    flight_owner = "tests/infrastructure/adapters/test_flight_normal_move_policy.py"
    assert set(flight["added_files"]) == {flight_owner}
    assert flight_owner in active_files
    assert sum(flight_owner in group for group in groups) == 1
    assert (
        flight["added_files"][flight_owner]["sha256"]
        == hashlib.sha256((ROOT / flight_owner).read_bytes()).hexdigest()
    )
    flight_cases = {
        flight_owner + "::test_fixed_destination_flight_policy_and_native_comparison" + f"[{scene}]"
        for scene in ("open", "roof")
    }
    assert (
        skulls["retained_transition_sha256"]
        == hashlib.sha256(
            (
                ROOT / "data/source_audits/ci64_provenance_v1/sheathed-in-brass-transition-v1.json"
            ).read_bytes()
        ).hexdigest()
    )
    predecessor_sources = {**brass["sources"], **skulls["new_sources"]}
    for source, binding in skulls["replaced_sources"].items():
        assert binding["before"] == brass["sources"][source]
        assert (
            binding["after"]
            == hashlib.sha256(
                subprocess.check_output(
                    ["git", "show", shooting_skulls["base"] + ":" + source], cwd=ROOT
                )
            ).hexdigest()
        )
        predecessor_sources[source] = binding["after"]
    for source, binding in shooting_skulls["replaced_sources"].items():
        assert binding["before"] == predecessor_sources[source]
        predecessor_sources[source] = binding["after"]
    assert shooting_skulls["new_sources"].keys().isdisjoint(predecessor_sources)
    predecessor_sources.update(shooting_skulls["new_sources"])
    for source, binding in wrath["replaced_sources"].items():
        assert binding["before"] == predecessor_sources[source]
        predecessor_sources[source] = binding["after"]
    assert wrath["new_sources"].keys().isdisjoint(predecessor_sources)
    predecessor_sources.update(wrath["new_sources"])
    for source, binding in gore["replaced_sources"].items():
        assert binding["before"] == predecessor_sources[source]
        assert (
            binding["before"]
            == hashlib.sha256(
                subprocess.check_output(["git", "show", gore["base"] + ":" + source], cwd=ROOT)
            ).hexdigest()
        )
        predecessor_sources[source] = binding["after"]
    assert gore["new_sources"].keys().isdisjoint(predecessor_sources)
    predecessor_sources.update(gore["new_sources"])
    for source, binding in fools_record["replaced_sources"].items():
        assert binding["before"] == predecessor_sources[source]
        predecessor_sources[source] = binding["after"]
    assert fools_record["new_sources"].keys().isdisjoint(predecessor_sources)
    for source, digest in (predecessor_sources | fools_record["new_sources"]).items():
        assert digest == hashlib.sha256((ROOT / source).read_bytes()).hexdigest()
    wrath_owner = selection.WRATH_UNDENIABLE_OWNER
    assert set(wrath["added_files"]) == {wrath_owner}
    assert wrath_owner in active_files
    assert sum(wrath_owner in group for group in groups) == 1
    assert (
        wrath["added_files"][wrath_owner]["sha256"]
        == hashlib.sha256((ROOT / wrath_owner).read_bytes()).hexdigest()
    )
    shooting_skulls_owner = selection.SKULLS_BEGET_BLOOD_OWNER
    assert set(shooting_skulls["added_files"]) == {shooting_skulls_owner}
    assert shooting_skulls_owner in active_files
    assert sum(shooting_skulls_owner in group for group in groups) == 1
    assert (
        gore["updated_files"][shooting_skulls_owner]["before"]
        == shooting_skulls["added_files"][shooting_skulls_owner]
    )
    assert (
        gore["updated_files"][shooting_skulls_owner]["after"]["sha256"]
        == hashlib.sha256((ROOT / shooting_skulls_owner).read_bytes()).hexdigest()
    )
    skulls_owner = selection.BLOOD_BEGETS_SKULLS_OWNER
    assert set(skulls["added_files"]) == {skulls_owner}
    assert skulls_owner in active_files
    assert sum(skulls_owner in group for group in groups) == 1
    assert gore["updated_files"][skulls_owner]["before"] == skulls["added_files"][skulls_owner]
    assert (
        gore["updated_files"][skulls_owner]["after"]["sha256"]
        == hashlib.sha256((ROOT / skulls_owner).read_bytes()).hexdigest()
    )
    stage3 = _record("data/source_audits/ci64_provenance_v1/stage3-melee-profile-test-v1.json")
    stage3_base_manifest = json.loads(
        subprocess.check_output(["git", "show", stage3["base"] + ":" + MANIFEST], cwd=ROOT)
    )
    assert skulls["runtime_fingerprint"] == stage3_base_manifest["fingerprint"]
    assert stage3["retained_runtime_fingerprint"] == skulls["runtime_fingerprint"]
    assert (
        stage3["retained_transition_sha256"]
        == hashlib.sha256(
            (
                ROOT / "data/source_audits/ci64_provenance_v1/sheathed-in-brass-transition-v1.json"
            ).read_bytes()
            + b"\0"
            + (ROOT / selection.BLOOD_BEGETS_SKULLS_TRANSITION).read_bytes()
        ).hexdigest()
    )
    assert shooting_skulls["retained_runtime_fingerprint"] == stage3["runtime_fingerprint"]
    assert stage3["runtime_fingerprint"] == previous_manifest["fingerprint"]
    assert (
        shooting_skulls["retained_transition_sha256"]
        == hashlib.sha256(
            (
                ROOT / "data/source_audits/ci64_provenance_v1/sheathed-in-brass-transition-v1.json"
            ).read_bytes()
            + b"\0"
            + (ROOT / selection.BLOOD_BEGETS_SKULLS_TRANSITION).read_bytes()
            + b"\0"
            + (
                ROOT / "data/source_audits/ci64_provenance_v1/stage3-melee-profile-test-v1.json"
            ).read_bytes()
        ).hexdigest()
    )
    stage3_owner = "tests/infrastructure/adapters/test_ordinary_melee_profile_policy.py"
    assert set(stage3["added_files"]) == {stage3_owner}
    assert stage3_owner in active_files
    assert sum(stage3_owner in group for group in groups) == 1
    assert (
        stage3["added_files"][stage3_owner]["sha256"]
        == hashlib.sha256((ROOT / stage3_owner).read_bytes()).hexdigest()
    )
    stage3_cases = {
        stage3_owner + "::" + name
        for name in (
            "test_great_axe_actor_offer_selects_applied_wounds_and_replays[seekers]",
            "test_great_axe_actor_offer_selects_applied_wounds_and_replays[bloodthirster]",
            "test_great_axe_dispatch_rejects_identical_view_at_unadmitted_checkpoint",
            "test_wounded_seeker_first_changes_applied_wound_expectation",
        )
    }
    brass_owner = "tests/factions/chaos_daemons/integration/test_sheathed_in_brass.py"
    assert set(brass["added_files"]) == {brass_owner}
    assert brass_owner in active_files
    assert sum(brass_owner in group for group in groups) == 1
    assert (
        brass["added_files"][brass_owner]["sha256"]
        == hashlib.sha256((ROOT / brass_owner).read_bytes()).hexdigest()
    )
    classification_owner = (
        "tests/infrastructure/source_governance/unit/test_blocked_row_classification.py"
    )
    assert set(brass["updated_files"]) == {classification_owner}
    classification_change = brass["updated_files"][classification_owner]
    assert (
        classification_change["before"]
        == _record(sharding.CUTOVER_PATH)["active_files"][classification_owner]
    )
    classification_preimage = subprocess.check_output(
        ["git", "show", brass["base"] + ":" + classification_owner], cwd=ROOT
    )
    assert (
        classification_change["before"]["sha256"]
        == hashlib.sha256(classification_preimage).hexdigest()
    )
    assert set(skulls["updated_files"]) == {classification_owner}
    classification_successor = skulls["updated_files"][classification_owner]
    assert classification_successor["before"] == classification_change["after"]
    assert (
        classification_successor["after"]["sha256"]
        == hashlib.sha256(
            subprocess.check_output(
                ["git", "show", shooting_skulls["base"] + ":" + classification_owner], cwd=ROOT
            )
        ).hexdigest()
    )
    assert set(shooting_skulls["updated_files"]) == {classification_owner}
    current_classification = shooting_skulls["updated_files"][classification_owner]
    assert current_classification["before"] == classification_successor["after"]
    assert set(wrath["updated_files"]) == {classification_owner}
    wrath_classification = wrath["updated_files"][classification_owner]
    assert wrath_classification["before"] == current_classification["after"]
    gore_classification = gore["updated_files"][classification_owner]
    assert gore_classification["before"] == wrath_classification["after"]
    assert (
        wrath_classification["after"]["sha256"]
        == hashlib.sha256(
            subprocess.check_output(
                ["git", "show", gore["base"] + ":" + classification_owner], cwd=ROOT
            )
        ).hexdigest()
    )
    assert (
        gore_classification["after"]["sha256"]
        == hashlib.sha256(
            subprocess.check_output(
                ["git", "show", fools.BASE + ":" + classification_owner], cwd=ROOT
            )
        ).hexdigest()
    )
    flight_classification = fools_record["updated_files"][classification_owner]
    assert flight_classification["before"] == gore_classification["after"]
    assert (
        flight_classification["after"]["sha256"]
        == hashlib.sha256((ROOT / classification_owner).read_bytes()).hexdigest()
    )
    assert classification_owner in active_files
    assert sum(classification_owner in group for group in groups) == 1
    pending_before: dict[str, str] = {}
    for name, binding in pending["sources"].items():
        present = subprocess.check_output(["git", "ls-tree", pending_base, "--", name], cwd=ROOT)
        predecessor = (
            subprocess.check_output(["git", "show", pending_base + ":" + name], cwd=ROOT)
            if present
            else b""
        )
        pending_before[name] = hashlib.sha256(predecessor).hexdigest()
        assert binding["before"] == pending_before[name]
        expected = binding["after"]
        if name in terror["source"]:
            assert terror["source"][name]["before"] == expected
            expected = terror["source"][name]["after"]
        assert expected == hashlib.sha256((ROOT / name).read_bytes()).hexdigest()
    screen_base_manifest = json.loads(
        subprocess.check_output(
            ["git", "show", ground_charge.SCREEN_BASE + ":" + MANIFEST], cwd=ROOT
        )
    )
    assert screen["retained_runtime_fingerprint"] == screen_base_manifest["fingerprint"]
    assert screen["retained_runtime_fingerprint"] == shooting["runtime_fingerprint"]
    assert screen["retained_normal_shooting_sha256"] == ground_charge.SHOOTING_TRANSITION_SHA256
    assert set(screen["added_files"]) == {ground_charge.SCREEN_OWNER}
    assert ground_charge.SCREEN_OWNER in active_files
    assert sum(ground_charge.SCREEN_OWNER in group for group in groups) == 1
    normal_move = _record(ground_charge.NORMAL_MOVE_TRANSITION)
    assert normal_move["base"] == ground_charge.NORMAL_MOVE_BASE
    assert normal_move["screen_source"]["before"] == screen["policy_sha256"]
    charge_cp = _record(selection.CHARGE_CP_TEST_ADDITION)
    normal_move_manifest = subprocess.check_output(
        ["git", "show", charge_cp["base"] + ":" + MANIFEST], cwd=ROOT
    )
    for path, key in (
        (ground_charge.SCREEN_SOURCE, "screen_source"),
        (MANIFEST, "runtime_manifest"),
    ):
        before = subprocess.check_output(
            ["git", "show", normal_move["base"] + ":" + path], cwd=ROOT
        )
        after = normal_move_manifest if path == MANIFEST else (ROOT / path).read_bytes()
        assert normal_move[key]["before"] == hashlib.sha256(before).hexdigest()
        assert normal_move[key]["after"] == hashlib.sha256(after).hexdigest()
    assert normal_move["runtime_manifest"]["before"] == combined["combined_manifest_sha256"]
    assert normal_move["retained_runtime_fingerprint"] == combined["combined_runtime_fingerprint"]
    assert normal_move["runtime_fingerprint"] == json.loads(normal_move_manifest)["fingerprint"]
    assert charge_cp["retained_manifest_sha256"] == normal_move["runtime_manifest"]["after"]
    cp_manifest = subprocess.check_output(
        ["git", "show", terror["base"] + ":" + MANIFEST], cwd=ROOT
    )
    assert charge_cp["manifest_sha256"] == hashlib.sha256(cp_manifest).hexdigest()
    assert charge_cp["runtime_fingerprint"] == json.loads(cp_manifest)["fingerprint"]
    assert (
        terror["retained_charge_cp_sha256"]
        == hashlib.sha256((ROOT / selection.CHARGE_CP_TEST_ADDITION).read_bytes()).hexdigest()
    )
    assert terror["retained_runtime_fingerprint"] == charge_cp["runtime_fingerprint"]
    assert terror["runtime_manifest"]["before"] == charge_cp["manifest_sha256"]
    manifest_after = terror["runtime_manifest"]["after"]
    runtime_after = terror["runtime_fingerprint"]
    origin_after = charge_cp["origin_test"]["after"]
    receipt_path = ROOT / selection.COUNTEROFFENSIVE_FIGHT_TYPE_TRANSITION
    counter = (
        _record(selection.COUNTEROFFENSIVE_FIGHT_TYPE_TRANSITION)
        if receipt_path.is_file()
        else None
    )
    if counter is not None:
        assert counter["runtime_manifest"]["before"] == manifest_after
        assert counter["retained_runtime_fingerprint"] == runtime_after
        assert counter["origin_test"]["before"] == origin_after
        manifest_after = counter["runtime_manifest"]["after"]
        runtime_after = counter["runtime_fingerprint"]
        origin_after = counter["origin_test"]["after"]
        counter_owner = selection.COUNTEROFFENSIVE_FIGHT_TYPE_OWNER
        assert counter_owner in active_files
        assert sum(counter_owner in group for group in groups) == 1
        for name, source in counter["sources"].items():
            before = subprocess.check_output(
                ["git", "show", counter["base"] + ":" + name], cwd=ROOT
            )
            assert source["before"] == hashlib.sha256(before).hexdigest()
            assert source["after"] == hashlib.sha256((ROOT / name).read_bytes()).hexdigest()
    from scripts import stage3_ranged_profile_test_admission as ranged

    ranged_record = _record(ranged.RECEIPT)
    assert ranged_record["base"] == ranged.BASE
    assert receipt_path.is_file()
    ranged_base_manifest = subprocess.check_output(
        ["git", "show", ranged.BASE + ":" + MANIFEST], cwd=ROOT
    )
    assert hashlib.sha256(ranged_base_manifest).hexdigest() == manifest_after
    assert json.loads(ranged_base_manifest)["fingerprint"] == runtime_after
    assert ranged_record["retained_manifest_sha256"] == manifest_after
    assert ranged_record["retained_runtime_fingerprint"] == runtime_after
    assert (
        ranged_record["retained_counteroffensive_sha256"]
        == hashlib.sha256(receipt_path.read_bytes()).hexdigest()
    )
    from scripts import ranged_attack_count_test_admission as attack_count

    attack_record = _record(attack_count.RECEIPT)
    assert attack_record["base"] == attack_count.BASE
    attack_base_manifest = subprocess.check_output(
        ["git", "show", attack_count.BASE + ":" + MANIFEST], cwd=ROOT
    )
    assert ranged_record["manifest_sha256"] == hashlib.sha256(attack_base_manifest).hexdigest()
    assert ranged_record["runtime_fingerprint"] == json.loads(attack_base_manifest)["fingerprint"]
    assert (
        attack_record["retained_ranged_profile_sha256"]
        == hashlib.sha256((ROOT / ranged.RECEIPT).read_bytes()).hexdigest()
    )
    assert attack_record["retained_manifest_sha256"] == ranged_record["manifest_sha256"]
    assert attack_record["retained_runtime_fingerprint"] == ranged_record["runtime_fingerprint"]
    assert (
        attack_record["manifest_sha256"]
        == hashlib.sha256((ROOT / MANIFEST).read_bytes()).hexdigest()
    )
    assert attack_record["runtime_fingerprint"] == _record(MANIFEST)["fingerprint"]
    assert (
        attack_record["gathering_source_sha256"]
        == hashlib.sha256((ROOT / attack_count.SOURCE).read_bytes()).hexdigest()
    )
    assert set(attack_record["viewer_sources"]) == set(attack_count.VIEWER_SOURCES)
    for name in attack_count.VIEWER_SOURCES:
        before = subprocess.check_output(["git", "show", attack_count.BASE + ":" + name], cwd=ROOT)
        assert attack_record["viewer_sources"][name] == {
            "before": hashlib.sha256(before).hexdigest(),
            "after": hashlib.sha256((ROOT / name).read_bytes()).hexdigest(),
        }
    assert attack_count.OWNER in active_files
    assert sum(attack_count.OWNER in group for group in groups) == 1
    assert attack_record["added_cases"] == [
        f"{attack_count.OWNER}::{case}" for case in attack_count.CASES
    ]
    attack_base_durations = json.loads(
        subprocess.check_output(
            ["git", "show", attack_count.BASE + ":ci/test_shards/durations.json"], cwd=ROOT
        )
    )
    assert len(attack_base_durations["case_seconds"]) == 6819
    assert all(
        current[node] == seconds for node, seconds in attack_base_durations["case_seconds"].items()
    )
    assert all(
        summary["files"][node] == seconds
        for node, seconds in attack_base_durations["files"].items()
    )
    assert ranged.OWNER in active_files
    assert sum(ranged.OWNER in group for group in groups) == 1
    ranged_cases = {
        f"{ranged.OWNER}::{case}"
        for case in (
            "test_bolt_profile_comparison_commits_and_replays[full]",
            "test_bolt_profile_comparison_commits_and_replays[one-left]",
            "test_bolt_profile_admission_blocks_unreviewed_contextual_modifier",
            "test_unsupported_native_bolt_context_declines[damaged]",
            "test_unsupported_native_bolt_context_declines[lethal]",
            "test_unsupported_native_bolt_context_declines[sustained]",
        )
    }
    ranged_base_durations = json.loads(
        subprocess.check_output(
            ["git", "show", ranged.BASE + ":ci/test_shards/durations.json"], cwd=ROOT
        )
    )
    assert len(ranged_base_durations["case_seconds"]) == 6813
    assert all(
        current[node] == seconds for node, seconds in ranged_base_durations["case_seconds"].items()
    )
    assert all(
        summary["files"][node] == seconds
        for node, seconds in ranged_base_durations["files"].items()
    )
    assert (
        charge_cp["policy_sha256"]
        == hashlib.sha256((ROOT / selection.CHARGE_CP_POLICY_SOURCE).read_bytes()).hexdigest()
    )
    for cp_owner in charge_cp["added_files"]:
        assert cp_owner in active_files
        assert sum(cp_owner in group for group in groups) == 1
    for name, change in terror["source"].items():
        original = subprocess.check_output(["git", "show", terror["base"] + ":" + name], cwd=ROOT)
        assert change["before"] == hashlib.sha256(original).hexdigest()
        assert change["after"] == hashlib.sha256((ROOT / name).read_bytes()).hexdigest()
    assert selection.DAEMONIC_TERROR_OWNER in active_files
    assert sum(selection.DAEMONIC_TERROR_OWNER in group for group in groups) == 1
    assert ground_charge.NORMAL_MOVE_OWNER in active_files
    assert sum(ground_charge.NORMAL_MOVE_OWNER in group for group in groups) == 1
    assert normal_move["added_cases"] == [
        f"{ground_charge.NORMAL_MOVE_OWNER}::{name}" for name in ground_charge.NORMAL_MOVE_CASES
    ]
    admission = ground_charge.load_normal_move_admission(ROOT)
    assert admission is not None
    origin = _record(ground_charge.NORMAL_MOVE_ORIGIN_TRANSITION)
    assert origin["retained_normal_move_sha256"] == hashlib.sha256(admission.raw).hexdigest()
    assert origin["runtime_fingerprint"] == normal_move["runtime_fingerprint"]
    origin_owner = ground_charge.NORMAL_MOVE_ORIGIN_OWNER
    assert charge_cp["origin_test"]["before"] == origin["added_files"][origin_owner]
    assert origin_after["sha256"] == hashlib.sha256((ROOT / origin_owner).read_bytes()).hexdigest()
    assert origin["added_cases"] == [
        f"{ground_charge.NORMAL_MOVE_ORIGIN_OWNER}::{ground_charge.NORMAL_MOVE_ORIGIN_CASE}"
    ]
    assert ground_charge.NORMAL_MOVE_ORIGIN_OWNER in active_files
    assert sum(ground_charge.NORMAL_MOVE_ORIGIN_OWNER in group for group in groups) == 1
    with pytest.raises(SystemExit, match="exact Normal Move lineage"):
        ground_charge.normal_move_origin_test_addition(
            ROOT, predecessor=None, runtime=origin["runtime_fingerprint"]
        )
    with pytest.raises(SystemExit, match="exact Screen source predecessor"):
        admission.validate_screen_source(ROOT, "0" * 64)
    with pytest.raises(SystemExit, match="exact combined Charge predecessor"):
        admission.admit_runtime(
            ROOT,
            predecessor=b"unbound",
            fingerprint=combined["combined_runtime_fingerprint"],
            manifest_sha256=combined["combined_manifest_sha256"],
        )
    assert shalaxi["test"]["before"] == shooting_visibility["test"]["after"]
    for source in selection.ROUND3_SHALAXI_SOURCES:
        present = subprocess.check_output(["git", "ls-tree", shalaxi_base, "--", source], cwd=ROOT)
        before = (
            subprocess.check_output(["git", "show", shalaxi_base + ":" + source], cwd=ROOT)
            if present
            else b""
        )
        assert shalaxi["sources"][source]["before"] == hashlib.sha256(before).hexdigest()
        assert (
            shalaxi["sources"][source]["after"]
            == hashlib.sha256((ROOT / source).read_bytes()).hexdigest()
        )
    visibility_owner = selection.CLOSE_QUARTERS_OWNER
    assert sum(visibility_owner in group for group in groups) == 1
    timing_cases = _record("ci/test_shards/durations.json")["case_seconds"]
    shalaxi_cases = {
        visibility_owner + "::" + name
        for name in (
            "test_axis_shadow_matches_exact_visibility_at_closed_corridor_boundary",
            "test_axis_shadow_joins_touching_heights_but_leaves_vertical_openings",
            "test_rotated_wall_shadow_agrees_with_fixed_part_visibility",
            "test_polygon_gap_suggests_checked_ray_between_unequal_ellipses",
        )
    }
    assert shalaxi_cases <= timing_cases.keys()
    malice_source = selection.ROUND4_MALICE_BEARER_SOURCE
    malice_source_before = subprocess.check_output(
        ["git", "show", malice_base + ":" + malice_source], cwd=ROOT
    )
    assert malice["source"]["before"] == hashlib.sha256(malice_source_before).hexdigest()
    assert (
        malice["source"]["after"] == hashlib.sha256((ROOT / malice_source).read_bytes()).hexdigest()
    )
    malice_owner = selection.ROUND4_MALICE_BEARER_OWNER
    assert malice_owner in active_files
    malice_selector = (
        malice_owner
        + "::test_default_generic_rule_ability_registry_maps_shadow_legion_enhancement_grants"
    )
    assert sum(malice_owner in group for group in groups) == 1
    assert malice_selector in _record("ci/test_shards/durations.json")["case_seconds"]
    for source in selection.ROUND4_BATTLE_SHOCK_SOURCES:
        if source == selection.ROUND4_BATTLE_SHOCK_TERRITORY_SOURCE:
            assert not subprocess.check_output(
                ["git", "ls-tree", selection.ROUND4_BATTLE_SHOCK_BASE, "--", source], cwd=ROOT
            )
            base_source = b""
        else:
            base_source = subprocess.check_output(
                ["git", "show", selection.ROUND4_BATTLE_SHOCK_BASE + ":" + source], cwd=ROOT
            )
        assert round4["source"][source]["before"] == hashlib.sha256(base_source).hexdigest()
        if source in pending_before:
            round4_after = pending_before[source]
        elif source in terror["source"]:
            round4_after = terror["source"][source]["before"]
        else:
            round4_after = hashlib.sha256((ROOT / source).read_bytes()).hexdigest()
        assert round4["source"][source]["after"] == round4_after
    round4_owner = selection.ROUND4_BATTLE_SHOCK_OWNER
    assert round4_owner in active_files
    assert sum(round4_owner in group for group in groups) == 1
    assert (
        round4["test"]["after"]["sha256"]
        == hashlib.sha256((ROOT / round4_owner).read_bytes()).hexdigest()
    )
    for source in selection.MONSTER_MASH_ATTACK_REROLL_SOURCES:
        source_before = subprocess.check_output(
            ["git", "show", selection.MONSTER_MASH_ATTACK_REROLL_BASE + ":" + source], cwd=ROOT
        )
        assert fight_reroll["source"][source]["before"] == hashlib.sha256(source_before).hexdigest()
        expected = fight_reroll["source"][source]["after"]
        if source == dark_pact.LIFECYCLE_SOURCE:
            assert pact["retained_lifecycle"]["before"] == expected
            expected = pact["retained_lifecycle"]["after"]
        successor = None if counter is None else counter["sources"].get(source)
        if successor is not None:
            assert successor["before"] == expected
            expected = successor["after"]
        assert expected == hashlib.sha256((ROOT / source).read_bytes()).hexdigest()
    shooting_reroll_owner, fight_reroll_owner = selection.MONSTER_MASH_ATTACK_REROLL_OWNERS
    for attack_reroll_owner in selection.MONSTER_MASH_ATTACK_REROLL_OWNERS:
        assert attack_reroll_owner in active_files
        assert sum(attack_reroll_owner in group for group in groups) == 1
    monster_mash_owner = selection.MONSTER_MASH_OWNER
    assert monster_mash_owner in active_files
    assert sum(monster_mash_owner in group for group in groups) == 1
    movement_owner = selection.OPENING_MOVEMENT_UNIT_OWNER
    assert movement_owner in active_files
    assert sum(movement_owner in group for group in groups) == 1
    opening_owner = selection.OPENING_SHADOW_FORM_OWNER
    assert opening_owner in active_files
    assert sum(opening_owner in group for group in groups) == 1
    cover_source = selection.COVER_EVENT_IDENTITY_SOURCE
    base_cover_source = subprocess.check_output(
        ["git", "show", selection.COVER_EVENT_IDENTITY_BASE + ":" + cover_source], cwd=ROOT
    )
    assert cover_event["source"]["before"] == hashlib.sha256(base_cover_source).hexdigest()
    assert cover_event["source"]["after"] == attack_record["viewer_sources"][cover_source]["before"]
    cover_owner = selection.COVER_EVENT_IDENTITY_OWNER
    assert cover_owner in active_files
    assert sum(cover_owner in group for group in groups) == 1
    allocation_owner = selection.ALLOCATION_COHERENCY_OWNER
    assert allocation_owner in active_files
    assert sum(allocation_owner in group for group in groups) == 1
    strict_replay_owner = selection.STRICT_REPLAY_OWNER
    assert (
        strict_replay["test"][strict_replay_owner]["before"]
        == _record(sharding.CUTOVER_PATH)["active_files"][strict_replay_owner]
    )
    assert sum(strict_replay_owner in group for group in groups) == 1
    for name in selection.STRICT_REPLAY_SOURCES:
        source_before = subprocess.check_output(
            ["git", "show", selection.STRICT_REPLAY_BASE + ":" + name], cwd=ROOT
        )
        assert strict_replay["sources"][name]["before"] == hashlib.sha256(source_before).hexdigest()
        assert (
            strict_replay["sources"][name]["after"]
            == hashlib.sha256((ROOT / name).read_bytes()).hexdigest()
        )
    close_quarters_owner = selection.CLOSE_QUARTERS_OWNER
    assert (
        close_quarters["test"][close_quarters_owner]["before"]
        == _record(sharding.CUTOVER_PATH)["active_files"][close_quarters_owner]
    )
    assert close_quarters_owner in active_files
    assert sum(close_quarters_owner in group for group in groups) == 1
    for name in selection.CLOSE_QUARTERS_SOURCES:
        source_before = subprocess.check_output(
            ["git", "show", selection.CLOSE_QUARTERS_BASE + ":" + name], cwd=ROOT
        )
        assert (
            close_quarters["sources"][name]["before"] == hashlib.sha256(source_before).hexdigest()
        )
        close_quarters_after = subprocess.check_output(
            ["git", "show", selection.SHOOTING_VISIBILITY_BASE + ":" + name], cwd=ROOT
        )
        assert (
            close_quarters["sources"][name]["after"]
            == hashlib.sha256(close_quarters_after).hexdigest()
        )
        successor = shalaxi["sources"].get(name)
        prior_source_digest = (
            hashlib.sha256((ROOT / name).read_bytes()).hexdigest()
            if successor is None
            else successor["before"]
        )
        if name == selection.SHOOTING_VISIBILITY_SOURCE:
            assert (
                shooting_visibility["source"]["before"] == close_quarters["sources"][name]["after"]
            )
            assert shooting_visibility["source"]["after"] == prior_source_digest
        else:
            assert close_quarters["sources"][name]["after"] == prior_source_digest
    assert (
        shooting_visibility["test"]["before"]
        == close_quarters["test"][close_quarters_owner]["after"]
    )
    shooting_test_bytes = subprocess.check_output(
        ["git", "show", shalaxi_base + ":" + close_quarters_owner], cwd=ROOT
    )
    assert shooting_visibility["test"]["after"]["bytes"] == len(shooting_test_bytes)
    assert (
        shooting_visibility["test"]["after"]["sha256"]
        == hashlib.sha256(shooting_test_bytes).hexdigest()
    )
    shadow_owner = selection.ROUND_FIVE_SHADOW_OWNER
    assert (
        shadow["test"][shadow_owner]["before"]
        == _record(sharding.CUTOVER_PATH)["active_files"][shadow_owner]
    )
    assert shadow_owner in active_files
    assert sum(shadow_owner in group for group in groups) == 1
    for name in selection.ROUND_FIVE_SHADOW_SOURCES:
        source_before = subprocess.check_output(
            ["git", "show", selection.ROUND_FIVE_SHADOW_BASE + ":" + name], cwd=ROOT
        )
        assert shadow["sources"][name]["before"] == hashlib.sha256(source_before).hexdigest()
        if name in round4["source"]:
            assert shadow["sources"][name]["after"] == round4["source"][name]["before"]
        else:
            assert (
                shadow["sources"][name]["after"]
                == hashlib.sha256((ROOT / name).read_bytes()).hexdigest()
            )
    for name, digest in selection.CAVALCADE_AUTHORITY_SOURCES.items():
        if name in pending_before:
            assert pending_before[name] == digest
        else:
            assert hashlib.sha256((ROOT / name).read_bytes()).hexdigest() == digest
    for terminal_owner in selection.TERMINAL_RESTORE_OWNERS:
        assert (
            terminal["test"][terminal_owner]["before"]
            == _record(sharding.CUTOVER_PATH)["active_files"][terminal_owner]
        )
        assert terminal_owner in active_files
        assert sum(terminal_owner in group for group in groups) == 1
    for terminal_source in selection.TERMINAL_RESTORE_SOURCES:
        terminal_source_before = subprocess.check_output(
            ["git", "show", selection.TERMINAL_RESTORE_BASE + ":" + terminal_source], cwd=ROOT
        )
        assert (
            terminal["source"][terminal_source]["before"]
            == hashlib.sha256(terminal_source_before).hexdigest()
        )
    assert reroll["test"][owner]["before"] == melee_restore["test"][owner]["after"]
    for source in (selection.STAGE2_FIGHT_REROLL_SOURCE, selection.STAGE2_FIGHT_REROLL_FIXTURE):
        source_before = subprocess.check_output(
            ["git", "show", selection.STAGE2_FIGHT_REROLL_BASE + ":" + source], cwd=ROOT
        )
        assert reroll["source"][source]["before"] == hashlib.sha256(source_before).hexdigest()
    prior = json.loads(
        subprocess.check_output(["git", "show", BASE + ":ci/test_shards/durations.json"], cwd=ROOT)
    )
    previous = sharding.summary_case_seconds(prior)
    added = {node for node in current if node.startswith(selection.OWNER + "::")}
    assert len(added) == 28
    successors = _record(selection.ADDITION)["case_id_successors"]
    retained = {successors.get(node, node) for node in previous}
    assert len(retained) == len(previous)
    staged = {node for node in current if node.startswith(selection.EXACT_MOVEMENT_OWNER + "::")}
    assert staged
    assert sum(selection.EXACT_MOVEMENT_OWNER in group for group in groups) == 1
    mixed = {node for node in current if node.startswith(selection.CIRCLE_POLYGON_OWNER + "::")}
    assert mixed
    assert sum(selection.CIRCLE_POLYGON_OWNER in group for group in groups) == 1
    oval = {node for node in current if node.startswith(selection.OVAL_POINT_OWNER + "::")}
    assert oval
    assert sum(selection.OVAL_POINT_OWNER in group for group in groups) == 1
    oval_polygon = {
        node for node in current if node.startswith(selection.OVAL_POLYGON_OWNER + "::")
    }
    assert oval_polygon
    assert sum(selection.OVAL_POLYGON_OWNER in group for group in groups) == 1
    oval_polygon_gap = {
        node for node in current if node.startswith(selection.OVAL_POLYGON_GAP_OWNER + "::")
    }
    assert oval_polygon_gap
    assert sum(selection.OVAL_POLYGON_GAP_OWNER in group for group in groups) == 1
    circle_oval = {node for node in current if node.startswith(selection.CIRCLE_OVAL_OWNER + "::")}
    assert circle_oval
    assert sum(selection.CIRCLE_OVAL_OWNER in group for group in groups) == 1
    oval_oval = {
        node for node in current if node.startswith(selection.OVAL_OVAL_TOPOLOGY_OWNER + "::")
    }
    assert len(oval_oval) == 24
    assert sum(selection.OVAL_OVAL_TOPOLOGY_OWNER in group for group in groups) == 1
    oval_oval_gap = {
        node for node in current if node.startswith(selection.OVAL_OVAL_GAP_OWNER + "::")
    }
    assert len(oval_oval_gap) == 27
    assert sum(selection.OVAL_OVAL_GAP_OWNER in group for group in groups) == 1
    oval_oval_witnesses = {
        node for node in current if node.startswith(selection.OVAL_OVAL_WITNESS_OWNER + "::")
    }
    assert len(oval_oval_witnesses) == 7
    assert sum(selection.OVAL_OVAL_WITNESS_OWNER in group for group in groups) == 1
    oval_codec = {node for node in current if node.startswith(selection.OVAL_CODEC_OWNER + "::")}
    assert len(oval_codec) == 32
    assert sum(selection.OVAL_CODEC_OWNER in group for group in groups) == 1
    gameplay_prefix = (
        selection.GAMEPLAY_BUDGET_OWNER
        + "::test_normal_move_facade_budgets_once_rounded_complete_paths"
    )
    gameplay = {
        gameplay_prefix + "[" + case + "]"
        for case in (
            "below-budget-midpoint",
            "exact-midpoint",
            "above-budget-midpoint",
            "blocked",
            "timeout-then-retry",
        )
    }
    gameplay.add(
        selection.GAMEPLAY_CHARGE_OWNER
        + "::test_native_charge_certification_timeout_leaves_the_same_proposal_retryable"
    )
    gameplay.update(
        selection.GAMEPLAY_ESCAPE_OWNER
        + "::test_native_escape_battle_shock_reroll_reuses_certified_path"
        + f"[{choice}]"
        for choice in ("decline", "reroll:0,1")
    )
    shadow_cases = {
        shadow_owner
        + "::test_v995_contextual_shadow_aura_applies_only_to_friendly_khorne_units_in_range",
        shadow_owner
        + "::test_v995_opposing_command_battle_shock_resolves_with_qualified_terror[False]",
        shadow_owner
        + "::test_v995_opposing_command_battle_shock_resolves_with_qualified_terror[True]",
    }
    close_quarters_cases = {
        close_quarters_owner + "::" + name
        for name in (
            "test_ellipse_facing_search_proves_hidden_part_from_narrow_origin_cap",
            "test_ellipse_facing_search_leaves_unsupported_domains_to_existing_authority",
            "test_ellipse_facing_search_checks_base_edge_behind_low_models",
            "test_ellipse_facing_search_checks_base_edge_with_multiple_terrain_walls",
        )
    }
    allocation_cases = {
        allocation_owner + "::" + name
        for name in (
            "test_screen_rod_allocation_ranks_issued_choices_by_survivor_coherency",
            "test_allocation_honors_only_option_and_retains_issued_order_on_tie[indices0-False]",
            "test_allocation_honors_only_option_and_retains_issued_order_on_tie[indices1-True]",
            "test_allocation_requires_defender_visible_formation",
        )
    }
    round4_cases = {
        round4_owner + "::" + name
        for name in (
            "test_manifestation_history_survives_the_tested_units_later_destruction",
            "test_later_daemon_casualty_still_requires_historical_territorial_terror[False-False]",
            "test_later_daemon_casualty_still_requires_historical_territorial_terror[True-False]",
            "test_later_daemon_casualty_still_requires_historical_territorial_terror[True-True]",
        )
    }
    regeneration_cases = {
        healing_owner
        + f"::test_grotesque_regeneration_native_phase_end_and_replay[{phase}-{source}]"
        for phase in ("shooting", "fight")
        for source in ("chaos-daemons", "death-guard")
    }
    brass_cases = {
        brass_owner + "::" + name
        for name in (
            "test_sheathed_in_brass_native_accept_later_shooting_expiry_and_replay",
            "test_sheathed_in_brass_native_decline_or_unaffordable[unaffordable]",
            "test_sheathed_in_brass_native_decline_or_unaffordable[decline]",
            "test_sheathed_in_brass_native_gathering_and_save_ignore[fight-only]",
            "test_sheathed_in_brass_native_gathering_and_save_ignore[sheathed-ignore]",
        )
    }
    pact_cases = {
        f"{dark_pact.NEW_TEST}::test_dark_pact_selection_resolves_before_attacks[{case}-{phase}]"
        for case in ("decline", "pass", "survive", "casualty", "wipe", "fnp")
        for phase in ("shooting", "fight")
    } | {
        f"{dark_pact.NEW_TEST}::test_only_shadow_legion_offers_belakor_the_no_roll_pact"
        f"[{detachment}-{phase}]"
        for detachment in ("shadow-legion", "blood-legion")
        for phase in ("shooting", "fight")
    }
    pact_cases.add(
        f"{dark_pact.NEW_TEST}::"
        "test_dark_pact_survivor_without_a_legal_gun_ends_shooting_without_an_attack"
    )
    pact_cases.update(
        f"{dark_pact.NEW_TEST}::test_attached_fight_dark_pact_targets_formation_through_attack_and_replay[{case}]"
        for case in ("pass", "survive")
    )
    pact_cases.update(
        f"{dark_pact.NEW_TEST}::test_native_overwatch_grant_expires_at_its_own_boundary[{phase_scoped}]"
        for phase_scoped in (True, False)
    )
    assert current.keys() == (
        retained
        | pact_cases
        | added
        | staged
        | mixed
        | oval
        | oval_polygon
        | oval_polygon_gap
        | circle_oval
        | oval_oval
        | oval_oval_gap
        | oval_oval_witnesses
        | oval_codec
        | gameplay
        | shadow_cases
        | close_quarters_cases
        | shalaxi_cases
        | charge_cases
        | set(retry["added_cases"])
        | set(normal_move["added_cases"])
        | set(origin["added_cases"])
        | set(charge_cp["added_cases"])
        | set(terror["added_cases"])
        | (set() if counter is None else set(counter["added_cases"]))
        | ranged_cases
        | set(attack_record["added_cases"])
        | shooting_cases
        | {
            ground_charge.SCREEN_OWNER
            + "::test_screen_options_and_retreat_paths_use_native_requests"
            + f"[{mode}]"
            for mode in ("ordered_retreat", "desperate_escape")
        }
        | {
            ground_charge.SCREEN_OWNER
            + "::test_screen_options_require_an_issued_fall_back_alternative"
        }
        | allocation_cases
        | round4_cases
        | regeneration_cases
        | brass_cases
        | stage3_cases
        | flight_cases
        | charge_flight_cases
        | gore_cases
        | wall_cases
        | onslaught_cases
        | fools_cases
        | {
            selection.BLOOD_BEGETS_SKULLS_OWNER + "::" + case
            for case in (
                "test_blood_begets_skulls_offers_when_advance_prevents_all_charges",
                "test_blood_begets_skulls_decline_then_offer_after_earlier_charge",
                "test_blood_begets_skulls_unavailable_without_cp_or_outside_own_charge",
            )
        }
        | {
            owner + "::" + test + f"[{reroll}]"
            for owner, test in (
                (
                    fight_reroll_owner,
                    "test_fight_damage_reroll_stays_fresh_after_previous_attack_destroys_model",
                ),
                (
                    shooting_reroll_owner,
                    "test_shooting_damage_window_stays_fresh_after_previous_attack_casualty",
                ),
            )
            for reroll in (False, True)
        }
        | {
            selection.SKULLS_BEGET_BLOOD_OWNER + "::test_skulls_beget_blood_" + case
            for case in (
                "ordinary_choice_damage_attribution_and_replay",
                "attached_leader_range_defender_allocation_and_replay",
                "excludes_both_ends_of_engagement",
                "has_no_option_when_use_is_illegal[no_cp]",
                "has_no_option_when_use_is_illegal[opponent_turn]",
                "has_no_option_when_use_is_illegal[blocked]",
                "allows_advance_but_excludes_fall_back",
            )
        }
        | {
            wrath_owner + "::test_wrath_undeniable_native_retention_and_replay[" + case + "]"
            for case in ("four", "three", "already-fought")
        }
        | {cover_owner + "::test_save_cover_cache_key_projects_embedded_request_reference"}
        | {opening_owner + "::test_opening_shadow_form_policy_reaches_native_movement"}
        | {movement_owner + "::test_opening_movement_selects_an_issued_unit_before_any_action"}
        | {monster_mash_owner + "::test_exact_monster_mash_admission_deployment_and_replay"}
        | {
            strict_replay_owner
            + "::test_strict_persistence_rejects_valid_artifact_with_mismatched_metadata_or_tails"
        }
    )


def test_identity_selection_rejects_drift_in_each_updated_test(transition_snapshot: Path) -> None:
    updated, _, _ = _transition(transition_snapshot)
    changed = _record(selection.ADDITION)["updated_files"]
    assert set(changed) <= set(updated)
    for name in changed:
        target = transition_snapshot / name
        original = target.read_bytes()
        target.write_bytes(original + b"\n")
        with pytest.raises(SystemExit):
            _transition(transition_snapshot)
        target.write_bytes(original)


def test_identity_transition_requires_its_exact_record(transition_snapshot: Path) -> None:
    cutover_digest = hashlib.sha256((ROOT / sharding.CUTOVER_PATH).read_bytes()).hexdigest()
    assert selection.exact_movement_test_transition(transition_snapshot, cutover_digest) is None
    reroll = transition_snapshot / selection.STAGE2_FIGHT_REROLL_TRANSITION
    reroll.write_bytes((ROOT / selection.STAGE2_FIGHT_REROLL_TRANSITION).read_bytes())
    with pytest.raises(SystemExit, match="Fight reroll tests require the melee restore"):
        selection.exact_movement_test_transition(transition_snapshot, cutover_digest)
    reroll.unlink()
    melee_restore = transition_snapshot / selection.STAGE2_MELEE_RESTORE_TRANSITION
    melee_restore.write_bytes((ROOT / selection.STAGE2_MELEE_RESTORE_TRANSITION).read_bytes())
    with pytest.raises(SystemExit, match="melee restore tests require the Counteroffensive"):
        selection.exact_movement_test_transition(transition_snapshot, cutover_digest)
    melee_restore.unlink()
    counteroffensive = transition_snapshot / selection.COUNTEROFFENSIVE_TRANSITION
    counteroffensive.write_bytes((ROOT / selection.COUNTEROFFENSIVE_TRANSITION).read_bytes())
    with pytest.raises(SystemExit, match="Counteroffensive tests require the Fight Cover"):
        selection.exact_movement_test_transition(transition_snapshot, cutover_digest)
    counteroffensive.unlink()
    fight_record = transition_snapshot / selection.STAGE2_FIGHT_TRANSITION
    fight_record.write_bytes((ROOT / selection.STAGE2_FIGHT_TRANSITION).read_bytes())
    with pytest.raises(SystemExit, match="Stage 2 Fight Cover tests require the gameplay"):
        selection.exact_movement_test_transition(transition_snapshot, cutover_digest)

    target = transition_snapshot / selection.ADDITION
    target.write_bytes(target.read_bytes() + b"\n")
    with pytest.raises(SystemExit, match="source bytes differ"):
        _transition(transition_snapshot)
