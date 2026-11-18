"""Finite numerical source admission and current LPT inventory controls."""

from __future__ import annotations

import hashlib
import json
import subprocess
from pathlib import Path
from typing import Any

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


def _record(name: str) -> dict[str, Any]:
    return json.loads((ROOT / name).read_bytes())  # type: ignore[no-any-return]


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
        destination.write_bytes((ROOT / name).read_bytes())
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


def test_identity_transition_preserves_original_recipe_and_speedup_evidence() -> None:
    for name in (
        "src/warhammer40k_core/adapters/checkpoint_reconstruction.py",
        "data/source_audits/ci64_provenance_v1/speedup-test-transition-v1.json",
    ):
        original = subprocess.check_output(["git", "show", BASE + ":" + name], cwd=ROOT)
        assert (ROOT / name).read_bytes() == original
    updated, added, _ = _transition(ROOT)
    speedup = _record("data/source_audits/ci64_provenance_v1/speedup-test-transition-v1.json")
    assert set(speedup["updated_files"]) <= set(updated)
    assert selection.OWNER in added


def test_identity_inventory_uses_current_twelve_shards_and_native_cohort() -> None:
    assert selection.OWNER in sharding.behavioral_selection(ROOT).active_files
    groups = [
        set((ROOT / f"ci/test_shards/shard-{index}.txt").read_text().splitlines())
        for index in range(1, 13)
    ]
    assert sum(selection.OWNER in group for group in groups) == 1
    assert sum(sharding.covered_native_checkpoint_cohort() <= group for group in groups) == 1
    summary = _record("ci/test_shards/durations.json")
    current = sharding.summary_case_seconds(summary)
    prior = json.loads(
        subprocess.check_output(["git", "show", BASE + ":ci/test_shards/durations.json"], cwd=ROOT)
    )
    previous = sharding.summary_case_seconds(prior)
    added = {node for node in current if node.startswith(selection.OWNER + "::")}
    assert len(added) == 26
    successors = _record(selection.ADDITION)["case_id_successors"]
    retained = {successors.get(node, node) for node in previous}
    assert len(retained) == len(previous)
    assert current.keys() == retained | added


def test_identity_selection_rejects_drift_in_each_updated_test(transition_snapshot: Path) -> None:
    updated, _, _ = _transition(ROOT)
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
    target = transition_snapshot / selection.ADDITION
    target.write_bytes(target.read_bytes() + b"\n")
    with pytest.raises(SystemExit, match="source bytes differ"):
        _transition(transition_snapshot)
