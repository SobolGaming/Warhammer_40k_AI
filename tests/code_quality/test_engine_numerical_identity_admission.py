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
    assert sum(sharding.covered_native_checkpoint_cohort() <= group for group in groups) == 1
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
    source = selection.STAGE2_MELEE_RESTORE_SOURCE
    source_before = subprocess.check_output(
        ["git", "show", selection.STAGE2_MELEE_RESTORE_BASE + ":" + source], cwd=ROOT
    )
    assert melee_restore["source"][source]["before"] == hashlib.sha256(source_before).hexdigest()
    assert melee_restore["runtime_fingerprint"] == _record(MANIFEST)["fingerprint"]
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
