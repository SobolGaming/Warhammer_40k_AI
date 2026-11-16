"""Finite inactive-foundation admission with fresh proof and retained source data."""

from __future__ import annotations

import copy
import json
from pathlib import Path

import pytest
from scripts.complete_covered_evidence import verify_complete_covered_profile
from scripts.current_shard_compatibility import NATIVE_PREFIX_OWNER, NEW_NODES
from scripts.historical_shard_snapshot import MANIFEST, git_bytes
from scripts.linux_authority_shard_admission import retained_native_inventory
from scripts.milli_inch_shard_admission import (
    ASSIGNMENT_FILE,
    BASE,
    BASELINE_FILE,
    EVIDENCE_FILE,
    MODULE,
    NODES,
    OWNER,
    RUNTIME,
    SCHEMA,
    TEST_SHA256,
    current_native_role,
    producer_inputs,
    require_frozen_assignment,
    require_test_sources,
    retained_authority_artifacts,
    validate_runtime_transition,
)
from scripts.precision_profile_shard_admission import BASE as SUCCESSOR_BASE
from tools.performance_policy import runtime_inputs

from tests.support.retained_authority_sources import materialize_retained_sources

ROOT = Path(__file__).resolve().parents[2]
DIRECTORY = ROOT / "ci/test_shards"


def test_milli_inch_runtime_is_only_the_exact_inactive_addition(tmp_path: Path) -> None:
    snapshot = tmp_path / "retained-source-data"
    snapshot.mkdir()
    materialize_retained_sources(ROOT, snapshot, revision=BASE)
    for name in (MODULE, MANIFEST):
        (snapshot / name).write_bytes(git_bytes(ROOT, SUCCESSOR_BASE, name))
    validate_runtime_transition(snapshot)
    with pytest.raises(SystemExit, match="actual runtime checkout"):
        current_native_role(snapshot, snapshot / "ci/test_shards", {}, {}, frozenset())
    for name in (MODULE, "src/warhammer40k_core/geometry/pose.py"):
        path = snapshot / name
        original = path.read_bytes()
        path.write_bytes(original + b"\n# changed runtime\n")
        with pytest.raises(SystemExit, match="inactive runtime addition"):
            validate_runtime_transition(snapshot)
        path.write_bytes(original)
    added = snapshot / "src/warhammer40k_core/geometry/unreviewed.py"
    added.write_text("# unreviewed addition\n", encoding="utf-8")
    with pytest.raises(SystemExit, match="inactive runtime addition"):
        validate_runtime_transition(snapshot)
    added.unlink()
    manifest = json.loads((snapshot / MANIFEST).read_bytes())
    manifest["resources"][0]["sha256"] = "0" * 64
    (snapshot / MANIFEST).write_text(json.dumps(manifest), encoding="utf-8")
    with pytest.raises(SystemExit, match="add-only runtime transition"):
        validate_runtime_transition(snapshot)


def test_milli_inch_complete_producer_is_current_source(tmp_path: Path) -> None:
    head = SUCCESSOR_BASE
    snapshot = tmp_path / "current-producer-data"
    snapshot.mkdir()
    materialize_retained_sources(ROOT, snapshot, revision=head)
    assert producer_inputs(snapshot, head) == runtime_inputs(snapshot)
    path = snapshot / "scripts/milli_inch_shard_admission.py"
    path.write_bytes(path.read_bytes() + b"\n# unmeasured tooling\n")
    with pytest.raises(SystemExit, match="complete producer inputs differ"):
        producer_inputs(snapshot, head)


def test_milli_inch_preserves_original_behavior_sources_and_authority_evidence(
    tmp_path: Path,
) -> None:
    prior = json.loads(
        git_bytes(ROOT, BASE, "ci/test_shards/linux-authority-covered-baseline.json")
    )
    sources = {**prior["test_sources"], OWNER: TEST_SHA256}
    require_test_sources(ROOT, sources)
    for changed in (
        {**sources, OWNER: "0" * 64},
        prior["test_sources"],
        {**sources, "extra": "0" * 64},
    ):
        with pytest.raises(SystemExit, match="behavioral source inventory"):
            require_test_sources(ROOT, changed)
    changed = dict(sources)
    changed[next(iter(prior["test_sources"]))] = "0" * 64
    with pytest.raises(SystemExit, match="behavioral source inventory"):
        require_test_sources(ROOT, changed)
    retained_authority_artifacts(ROOT, DIRECTORY)
    (tmp_path / "linux-authority-covered-baseline.json").write_text("{}", encoding="utf-8")
    with pytest.raises(SystemExit, match="Retained Linux authority evidence changed"):
        retained_authority_artifacts(ROOT, tmp_path)


def test_milli_inch_new_selector_cannot_move_or_duplicate_retained_work() -> None:
    old = json.loads(
        git_bytes(ROOT, BASE, "ci/test_shards/linux-authority-derived-assignment.json")
    )
    groups = [list(old["shards"][str(index)]) for index in range(1, 13)]
    groups[-1] = sorted([*groups[-1], OWNER])
    require_frozen_assignment(ROOT, tuple(tuple(group) for group in groups))
    moved = copy.deepcopy(groups)
    moved[-1].append(moved[0].pop())
    with pytest.raises(SystemExit, match="cannot move a retained selector"):
        require_frozen_assignment(ROOT, tuple(tuple(group) for group in moved))
    with pytest.raises(SystemExit, match="twelve shards"):
        require_frozen_assignment(ROOT, tuple(tuple(group) for group in groups[:-1]))
    for copies in (0, 2):
        changed = copy.deepcopy(groups)
        changed[-1] = [node for node in changed[-1] if node != OWNER] + [OWNER] * copies
        with pytest.raises(SystemExit, match="exactly once"):
            require_frozen_assignment(ROOT, tuple(tuple(group) for group in changed))


def test_milli_inch_fetches_current_and_retained_producers() -> None:
    from scripts.fetch_scheduling_sources import revisions

    sources = revisions(DIRECTORY)
    baseline = json.loads((DIRECTORY / BASELINE_FILE).read_bytes())
    previous = json.loads((DIRECTORY / "linux-authority-covered-baseline.json").read_bytes())
    assert {BASE, baseline["source_head"], previous["source_head"]} <= set(sources)


def test_retained_milli_inch_profile_has_complete_original_evidence_and_fixed_inventory(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    from scripts import build_test_shards as sharding
    from scripts.build_test_shards import summary_case_seconds

    snapshot = tmp_path / "retained-foundation-source"
    snapshot.mkdir()
    materialize_retained_sources(ROOT, snapshot, revision=SUCCESSOR_BASE)
    monkeypatch.setattr(sharding, "REPOSITORY_ROOT", snapshot)
    monkeypatch.setattr(sharding, "TESTS_ROOT", snapshot / "tests")
    descriptor = json.loads(
        git_bytes(ROOT, SUCCESSOR_BASE, "ci/test_shards/current-runtime-compatibility.json")
    )
    assert descriptor["schema"] == SCHEMA
    assert descriptor["current_runtime_fingerprint"] == RUNTIME
    assert descriptor["baseline"]["file"] == BASELINE_FILE
    assert descriptor["fresh_evidence"]["file"] == EVIDENCE_FILE
    assert descriptor["assignment"]["file"] == ASSIGNMENT_FILE
    summary = json.loads(git_bytes(ROOT, SUCCESSOR_BASE, "ci/test_shards/durations.json"))
    cases = summary_case_seconds(summary)
    baseline = json.loads((DIRECTORY / BASELINE_FILE).read_bytes())
    native_nodes = frozenset(
        node for node in NEW_NODES if node.startswith(NATIVE_PREFIX_OWNER + "::")
    )
    order, _ = retained_native_inventory(
        ROOT, DIRECTORY, descriptor["native_serial_role"], native_nodes
    )
    seconds = verify_complete_covered_profile(
        ROOT,
        DIRECTORY,
        descriptor["fresh_evidence"],
        baseline,
        producer_inputs(snapshot, baseline["source_head"]),
        order,
        filename=EVIDENCE_FILE,
    )
    assert (
        seconds
        == summary["runtime_compatibility"]["native_serial_role"][
            "with_mirror_native_phase_seconds"
        ]
    )
    assignment = json.loads(git_bytes(ROOT, SUCCESSOR_BASE, "ci/test_shards/" + ASSIGNMENT_FILE))
    groups = tuple(tuple(assignment["shards"][str(index)]) for index in range(1, 13))
    previous = json.loads((DIRECTORY / "linux-authority-covered-baseline.json").read_bytes())
    assert len(NODES) == 25
    assert len(cases) == 6366
    assert cases.keys() == previous["case_seconds"].keys() | NODES
    assert sum(len(group) for group in groups) == 510
    require_frozen_assignment(ROOT, groups)
