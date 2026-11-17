"""Finite current-source transition and preserved historical source controls."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pytest
from scripts import engine_numerical_identity_shard_admission as admission
from scripts import engine_numerical_identity_test_admission as selection
from scripts.historical_shard_snapshot import MANIFEST, git_bytes

from tests.support.retained_authority_sources import materialize_retained_sources

ROOT = Path(__file__).resolve().parents[2]


def test_identity_runtime_transition_rejects_every_unreviewed_source(tmp_path: Path) -> None:
    admission.validate_runtime_transition(ROOT)
    materialize_retained_sources(ROOT, tmp_path, revision=admission.BASE)
    for name in (*admission.SOURCE_HASHES, MANIFEST):
        target = tmp_path / name
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes((ROOT / name).read_bytes())
    admission.validate_runtime_transition(tmp_path)
    for name in admission.SOURCE_HASHES:
        target = tmp_path / name
        original = target.read_bytes()
        target.write_bytes(original + b"\n")
        with pytest.raises(SystemExit, match="reviewed runtime transition"):
            admission.validate_runtime_transition(tmp_path)
        target.write_bytes(original)
    extra = tmp_path / "src/warhammer40k_core/geometry/unreviewed.py"
    extra.write_text("# no admission\n")
    with pytest.raises(SystemExit, match="reviewed runtime transition"):
        admission.validate_runtime_transition(tmp_path)


def test_identity_transition_preserves_original_recipe_bytes_and_all_prior_sources() -> None:
    original = "src/warhammer40k_core/adapters/checkpoint_reconstruction.py"
    assert (ROOT / original).read_bytes() == git_bytes(ROOT, admission.BASE, original)
    prior = json.loads(
        git_bytes(ROOT, admission.BASE, "ci/test_shards/exact-contact-covered-baseline.json")
    )
    sources = {
        **prior["test_sources"],
        **admission.UPDATED_TEST_HASHES,
        admission.OWNER: admission.TEST_SHA256,
    }
    admission.require_test_sources(ROOT, sources)
    assert len(prior["case_seconds"]) == 6427
    assert len(admission.NODES) == 26
    with pytest.raises(SystemExit, match="source inventory"):
        admission.require_test_sources(ROOT, prior["test_sources"])
    admission.retained_authority_artifacts(ROOT, ROOT / "ci/test_shards")


def test_identity_assignment_retains_all_517_prior_selector_locations() -> None:
    old = json.loads(
        git_bytes(ROOT, admission.BASE, "ci/test_shards/exact-contact-derived-assignment.json")
    )
    groups = [list(old["shards"][str(index)]) for index in range(1, 13)]
    assert sum(map(len, groups)) == 517
    groups[-1] = sorted([*groups[-1], admission.OWNER])
    admission.require_frozen_assignment(ROOT, tuple(tuple(group) for group in groups))
    groups[0].append(groups[-1].pop())
    with pytest.raises(SystemExit, match="retained selector"):
        admission.require_frozen_assignment(ROOT, tuple(tuple(group) for group in groups))


def test_identity_selection_binds_exact_test_and_updated_recipe_assertions() -> None:
    raw = (ROOT / "data/source_audits/ci64_provenance_v1/test-cutover.json").read_bytes()
    transition = selection.engine_numerical_identity_test_transition(
        ROOT, hashlib.sha256(raw).hexdigest()
    )
    assert transition is not None
    updated, added, _ = transition
    assert admission.OWNER in added
    assert "tests/rules/section18/test_facade.py" in updated
    previous = git_bytes(ROOT, admission.BASE, "tests/rules/section18/test_facade.py")
    current = (ROOT / "tests/rules/section18/test_facade.py").read_bytes()
    assert admission.transitioned_test(
        ROOT, "tests/rules/section18/test_facade.py", current, previous
    )
    assert not admission.transitioned_test(
        ROOT, "tests/rules/section18/test_facade.py", current + b"\n", previous
    )


def test_identity_current_profile_requires_complete_actual_source_bound_evidence() -> None:
    from scripts.build_test_shards import summary_case_seconds
    from scripts.current_shard_compatibility import plan
    from tools.performance_policy import runtime_inputs

    directory = ROOT / "ci/test_shards"
    descriptor = json.loads((directory / "current-runtime-compatibility.json").read_bytes())
    assert descriptor["schema"] == admission.SCHEMA
    assert descriptor["current_runtime_fingerprint"] == admission.RUNTIME
    assert descriptor["baseline"]["file"] == admission.BASELINE_FILE
    assert descriptor["fresh_evidence"]["file"] == admission.EVIDENCE_FILE
    assert descriptor["assignment"]["file"] == admission.ASSIGNMENT_FILE
    baseline = json.loads((directory / admission.BASELINE_FILE).read_bytes())
    previous = json.loads((directory / "exact-contact-covered-baseline.json").read_bytes())
    assert baseline["case_seconds"].keys() == previous["case_seconds"].keys() | admission.NODES
    assert admission.producer_inputs(ROOT, baseline["source_head"]) == runtime_inputs(ROOT)
    summary = json.loads((directory / "durations.json").read_bytes())
    selected = plan(ROOT, directory, summary_case_seconds(summary))
    assert sum(map(len, selected.groups)) == 518
    admission.require_frozen_assignment(ROOT, selected.groups)
