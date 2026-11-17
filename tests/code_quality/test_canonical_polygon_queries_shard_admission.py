"""Exact-source admission for canonical polygon queries and retained predecessor evidence."""

from __future__ import annotations

import copy
import hashlib
import json
from pathlib import Path

import pytest
from scripts.canonical_circle_test_admission import ADDITION as CIRCLE_ADDITION
from scripts.canonical_circle_test_admission import OWNER as CIRCLE_OWNER
from scripts.canonical_polygon_pairs_shard_admission import BASE as SUCCESSOR_BASE
from scripts.canonical_polygon_queries_shard_admission import (
    ASSIGNMENT_FILE,
    BASE,
    BASELINE_FILE,
    EVIDENCE_FILE,
    MODULE,
    MODULE_SHA256,
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
from scripts.canonical_polygon_test_admission import ADDITION as POLYGON_ADDITION
from scripts.canonical_polygon_test_admission import OWNER as POLYGON_OWNER
from scripts.historical_shard_snapshot import git_bytes
from scripts.milli_inch_test_admission import (
    ADDITION as FOUNDATION_ADDITION,
)
from scripts.milli_inch_test_admission import (
    MANIFEST,
    RETAINED_CUTOVER_SHA256,
)
from scripts.milli_inch_test_admission import (
    OWNER as FOUNDATION_OWNER,
)
from scripts.milli_inch_test_admission import (
    SOURCE as FOUNDATION_SOURCE,
)
from scripts.precision_profile_test_admission import ADDITION as PROFILE_ADDITION
from scripts.symbolic_milli_inch_test_admission import ADDITION as SYMBOLIC_ADDITION
from scripts.symbolic_milli_inch_test_admission import OWNER as SYMBOLIC_OWNER
from tools.performance_policy import runtime_inputs

from tests.support.retained_authority_sources import materialize_retained_sources

ROOT = Path(__file__).resolve().parents[2]
DIRECTORY = ROOT / "ci/test_shards"
RUNTIME_SOURCES = {MODULE: MODULE_SHA256}
TEST_SOURCES = {OWNER: TEST_SHA256}


def test_polygon_queries_binding_admits_only_its_exact_runtime_transition(tmp_path: Path) -> None:
    snapshot = tmp_path / "source-data"
    snapshot.mkdir()
    materialize_retained_sources(ROOT, snapshot, revision=BASE)
    for name in (*RUNTIME_SOURCES, MANIFEST):
        target = snapshot / name
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(git_bytes(ROOT, SUCCESSOR_BASE, name))
    validate_runtime_transition(snapshot)
    with pytest.raises(SystemExit, match="actual runtime checkout"):
        current_native_role(snapshot, snapshot / "ci/test_shards", {}, {}, frozenset())
    for name in (*RUNTIME_SOURCES, "src/warhammer40k_core/geometry/milli_inch.py"):
        target = snapshot / name
        raw = target.read_bytes()
        target.write_bytes(raw + b"\n# unreviewed source\n")
        with pytest.raises(SystemExit, match="inactive runtime addition"):
            validate_runtime_transition(snapshot)
        target.write_bytes(raw)
    target = snapshot / "src/warhammer40k_core/geometry/unreviewed.py"
    target.write_text("# unreviewed runtime addition\n", encoding="utf-8")
    with pytest.raises(SystemExit, match="inactive runtime addition"):
        validate_runtime_transition(snapshot)
    target.unlink()
    manifest = json.loads((snapshot / MANIFEST).read_bytes())
    manifest["resources"][0]["sha256"] = "0" * 64
    (snapshot / MANIFEST).write_text(json.dumps(manifest), encoding="utf-8")
    with pytest.raises(SystemExit, match="add-only runtime transition"):
        validate_runtime_transition(snapshot)


def test_polygon_queries_binding_requires_its_complete_measured_producer(tmp_path: Path) -> None:
    head = SUCCESSOR_BASE
    snapshot = tmp_path / "producer-data"
    snapshot.mkdir()
    materialize_retained_sources(ROOT, snapshot, revision=head)
    assert producer_inputs(snapshot, head) == runtime_inputs(snapshot)
    target = snapshot / "scripts/canonical_polygon_queries_shard_admission.py"
    target.write_bytes(target.read_bytes() + b"\n# unmeasured tooling\n")
    with pytest.raises(SystemExit, match="complete producer inputs differ"):
        producer_inputs(snapshot, head)


def test_polygon_queries_binding_preserves_retained_sources_and_evidence(tmp_path: Path) -> None:
    prior = json.loads(
        git_bytes(ROOT, BASE, "ci/test_shards/canonical-circle-covered-baseline.json")
    )
    sources = {**prior["test_sources"], **TEST_SOURCES}
    require_test_sources(ROOT, sources)
    for changed in (
        prior["test_sources"],
        {**sources, OWNER: "0" * 64},
        {**sources, "extra": "0" * 64},
    ):
        with pytest.raises(SystemExit, match="behavioral source inventory"):
            require_test_sources(ROOT, changed)
    changed = dict(sources)
    unchanged = next(name for name in sources if name not in TEST_SOURCES)
    changed[unchanged] = "0" * 64
    with pytest.raises(SystemExit, match="behavioral source inventory"):
        require_test_sources(ROOT, changed)
    retained_authority_artifacts(ROOT, DIRECTORY)
    names = (
        "linux-authority-covered-baseline.json",
        "linux-authority-covered-evidence.json",
        "linux-authority-derived-assignment.json",
        "symbolic-milli-inch-covered-baseline.json",
        "milli-inch-covered-baseline.json",
        "milli-inch-covered-evidence.json",
        "milli-inch-derived-assignment.json",
        "precision-profile-covered-evidence.json",
        "precision-profile-covered-baseline.json",
        "precision-profile-derived-assignment.json",
        "symbolic-milli-inch-covered-evidence.json",
        "symbolic-milli-inch-derived-assignment.json",
        "canonical-circle-covered-baseline.json",
        "canonical-polygon-covered-evidence.json",
        "canonical-polygon-covered-baseline.json",
        "canonical-polygon-derived-assignment.json",
        "canonical-circle-covered-evidence.json",
        "canonical-circle-derived-assignment.json",
    )
    for name in names:
        (tmp_path / name).write_bytes((DIRECTORY / name).read_bytes())
    for name in names:
        raw = (tmp_path / name).read_bytes()
        (tmp_path / name).write_bytes(raw + b"\n")
        with pytest.raises(SystemExit, match="predecessor evidence changed"):
            retained_authority_artifacts(ROOT, tmp_path)
        (tmp_path / name).write_bytes(raw)


def test_polygon_queries_binding_retains_twelve_shards_and_every_prior_selector() -> None:
    old = json.loads(
        git_bytes(ROOT, BASE, "ci/test_shards/canonical-circle-derived-assignment.json")
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


def test_polygon_queries_binding_fetches_both_current_and_retained_producers() -> None:
    from scripts.fetch_scheduling_sources import revisions

    producers = revisions(DIRECTORY)
    current = json.loads((DIRECTORY / BASELINE_FILE).read_bytes())
    previous = json.loads((DIRECTORY / "canonical-circle-covered-baseline.json").read_bytes())
    assert {BASE, current["source_head"], previous["source_head"]} <= set(producers)


def test_polygon_queries_binding_requires_complete_fresh_evidence_and_fixed_inventory(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    from scripts import build_test_shards as sharding
    from scripts.build_test_shards import summary_case_seconds
    from scripts.complete_covered_evidence import verify_complete_covered_profile
    from scripts.current_shard_compatibility import NATIVE_PREFIX_OWNER, NEW_NODES
    from scripts.linux_authority_shard_admission import retained_native_inventory

    snapshot = tmp_path / "retained-polygon-queries-source"
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
    previous = json.loads((DIRECTORY / "canonical-circle-covered-baseline.json").read_bytes())
    assert cases.keys() == previous["case_seconds"].keys() | NODES
    assert len(cases) == 6408
    assert sum(len(group) for group in groups) == 515
    require_frozen_assignment(ROOT, groups)


def test_polygon_queries_test_transition_preserves_original_selection_bytes(tmp_path: Path) -> None:
    from scripts import build_test_shards as sharding
    from scripts import canonical_polygon_queries_test_admission as admission

    snapshot = tmp_path / "retained-queries-selection"
    snapshot.mkdir()
    materialize_retained_sources(ROOT, snapshot, revision=SUCCESSOR_BASE)
    raw = (snapshot / sharding.CUTOVER_PATH).read_bytes()
    transition = admission.polygon_queries_test_transition(
        snapshot, hashlib.sha256(raw).hexdigest()
    )
    assert transition is not None
    updated, added, provenance = transition
    retained = json.loads(raw)
    assert updated.keys() <= retained["active_files"].keys()
    from scripts.precision_profile_test_admission import OWNER as PROFILE_OWNER

    assert set(added) == {
        FOUNDATION_OWNER,
        PROFILE_OWNER,
        SYMBOLIC_OWNER,
        POLYGON_OWNER,
        CIRCLE_OWNER,
        OWNER,
    }
    selected = sharding.behavioral_selection(snapshot)
    assert set(selected.active_files) == set(retained["active_files"]) | set(added)
    assert selected.manifest_sha256 == hashlib.sha256(raw + b"\0" + provenance).hexdigest()


@pytest.mark.parametrize(
    "change",
    [
        "none",
        "source",
        "test",
        "record",
        "missing_record",
        "runtime",
        "cutover",
        "foundation",
        "profile",
        "symbolic",
        "polygon",
        "circle",
    ],
)
def test_polygon_queries_test_transition_rejects_source_record_and_identity_drift(
    tmp_path: Path, change: str
) -> None:
    from scripts import canonical_polygon_queries_test_admission as admission

    record = json.loads((ROOT / admission.ADDITION).read_bytes())
    profile = json.loads((ROOT / PROFILE_ADDITION).read_bytes())
    symbolic = json.loads((ROOT / SYMBOLIC_ADDITION).read_bytes())
    polygon = json.loads((ROOT / POLYGON_ADDITION).read_bytes())
    circle = json.loads((ROOT / CIRCLE_ADDITION).read_bytes())
    names = {
        PROFILE_ADDITION,
        SYMBOLIC_ADDITION,
        POLYGON_ADDITION,
        CIRCLE_ADDITION,
        *circle["sources"],
        *circle["added_files"],
        *polygon["sources"],
        *polygon["added_files"],
        *symbolic["sources"],
        *symbolic["added_files"],
        *profile["sources"],
        *profile["updated_files"],
        *profile["added_files"],
        admission.ADDITION,
        MANIFEST,
        FOUNDATION_ADDITION,
        FOUNDATION_SOURCE,
        FOUNDATION_OWNER,
        *record["sources"],
        *record["added_files"],
    }
    for name in names:
        target = tmp_path / name
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(git_bytes(ROOT, SUCCESSOR_BASE, name))
    retained = RETAINED_CUTOVER_SHA256
    if change in {
        "source",
        "test",
        "record",
        "foundation",
        "profile",
        "symbolic",
        "polygon",
        "circle",
    }:
        name = {
            "source": admission.SOURCE,
            "test": OWNER,
            "record": admission.ADDITION,
            "foundation": FOUNDATION_ADDITION,
            "profile": PROFILE_ADDITION,
            "symbolic": SYMBOLIC_ADDITION,
            "polygon": POLYGON_ADDITION,
            "circle": CIRCLE_ADDITION,
        }[change]
        target = tmp_path / name
        target.write_bytes(target.read_bytes() + b"\n")
    elif change == "missing_record":
        (tmp_path / admission.ADDITION).unlink()
    elif change == "runtime":
        target = tmp_path / MANIFEST
        manifest = json.loads(target.read_bytes())
        manifest["fingerprint"] = "0" * 64
        target.write_text(json.dumps(manifest), encoding="utf-8")
    elif change == "cutover":
        retained = "0" * 64
    if change == "none":
        assert admission.polygon_queries_test_transition(tmp_path, retained) is not None
    else:
        with pytest.raises(SystemExit):
            admission.polygon_queries_test_transition(tmp_path, retained)


def test_polygon_queries_test_transition_leaves_historical_source_selection_closed(
    tmp_path: Path,
) -> None:
    from scripts import canonical_polygon_queries_test_admission as admission

    assert admission.polygon_queries_test_transition(tmp_path, "historical") is None
    target = tmp_path / MANIFEST
    target.parent.mkdir(parents=True)
    target.write_text(json.dumps({"fingerprint": "historical"}), encoding="utf-8")
    assert admission.polygon_queries_test_transition(tmp_path, "historical") is None


def test_polygon_queries_binding_preserves_all_existing_performance_obligations() -> None:
    name = "docs/performance/policy-v3/operation-map.json"
    previous = json.loads(git_bytes(ROOT, BASE, name))["operations"]
    operations = json.loads((ROOT / name).read_bytes())["operations"]
    for operation, prior in previous.items():
        if prior["sensitive"] or prior["mandatory"]:
            current = operations[operation]
            for field in ("paths", "owners", "families"):
                assert set(prior[field]) <= set(current[field])
            assert not prior["sensitive"] or current["sensitive"]
            assert not prior["mandatory"] or current["mandatory"]
    assert (
        "src/warhammer40k_core/adapters/numerical_policy.py"
        in operations["selected-linux-session-authority"]["paths"]
    )
    assert {
        "scripts/canonical_polygon_queries_shard_admission.py",
        "tests/code_quality/test_canonical_polygon_queries_shard_admission.py",
        "ci/test_shards/canonical-polygon-queries-covered-baseline.json",
        "ci/test_shards/canonical-polygon-queries-covered-evidence.json",
        "ci/test_shards/canonical-polygon-queries-derived-assignment.json",
    } <= set(operations["canonical-polygon-queries-admission"]["paths"])
