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
        assert current_digest == hashlib.sha256((ROOT / source).read_bytes()).hexdigest()
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
    assert skulls["runtime_fingerprint"] == previous_manifest["fingerprint"]
    assert shooting_skulls["retained_runtime_fingerprint"] == skulls["runtime_fingerprint"]
    assert shooting_skulls["runtime_fingerprint"] == _record(MANIFEST)["fingerprint"]
    assert (
        shooting_skulls["retained_transition_sha256"]
        == hashlib.sha256(
            (ROOT / selection.BLOOD_BEGETS_SKULLS_TRANSITION).read_bytes()
        ).hexdigest()
    )
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
    for source, digest in (predecessor_sources | shooting_skulls["new_sources"]).items():
        assert digest == hashlib.sha256((ROOT / source).read_bytes()).hexdigest()
    shooting_skulls_owner = selection.SKULLS_BEGET_BLOOD_OWNER
    assert set(shooting_skulls["added_files"]) == {shooting_skulls_owner}
    assert shooting_skulls_owner in active_files
    assert sum(shooting_skulls_owner in group for group in groups) == 1
    assert (
        shooting_skulls["added_files"][shooting_skulls_owner]["sha256"]
        == hashlib.sha256((ROOT / shooting_skulls_owner).read_bytes()).hexdigest()
    )
    skulls_owner = selection.BLOOD_BEGETS_SKULLS_OWNER
    assert set(skulls["added_files"]) == {skulls_owner}
    assert skulls_owner in active_files
    assert sum(skulls_owner in group for group in groups) == 1
    assert (
        skulls["added_files"][skulls_owner]["sha256"]
        == hashlib.sha256((ROOT / skulls_owner).read_bytes()).hexdigest()
    )
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
    assert (
        current_classification["after"]["sha256"]
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
        assert binding["after"] == hashlib.sha256((ROOT / name).read_bytes()).hexdigest()
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
    assert (
        screen["policy_sha256"]
        == hashlib.sha256((ROOT / ground_charge.SCREEN_SOURCE).read_bytes()).hexdigest()
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
        assert (
            fight_reroll["source"][source]["after"]
            == hashlib.sha256((ROOT / source).read_bytes()).hexdigest()
        )
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
    assert (
        cover_event["source"]["after"]
        == hashlib.sha256((ROOT / cover_source).read_bytes()).hexdigest()
    )
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
    assert current.keys() == (
        retained
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
                "excludes_both_ends_of_engagement",
                "has_no_option_when_use_is_illegal[no_cp]",
                "has_no_option_when_use_is_illegal[opponent_turn]",
                "has_no_option_when_use_is_illegal[blocked]",
                "allows_advance_but_excludes_fall_back",
            )
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
