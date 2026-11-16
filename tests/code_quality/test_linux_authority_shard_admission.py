"""Fresh authority admission and retained proof controls; no historical code runs."""

from __future__ import annotations

import copy
import hashlib
import json
import subprocess
from pathlib import Path
from typing import cast

import pytest
from scripts.boolean_los_admission import SOURCE_PRODUCER
from scripts.boolean_los_admission import producer_inputs as original_inputs
from scripts.complete_covered_evidence import verify_complete_covered_profile
from scripts.current_shard_compatibility import NATIVE_PREFIX_OWNER, NEW_NODES, derived_score, plan
from scripts.historical_shard_snapshot import git_bytes, historical_snapshot
from scripts.linux_authority_shard_admission import (
    BASELINE_FILE,
    EVIDENCE_FILE,
    NODES,
    OWNER,
    PREDECESSOR,
    RUNTIME,
    SCHEMA,
    current_native_role,
    producer_inputs,
    require_frozen_assignment,
    retained_native_inventory,
)
from tools.performance_policy import runtime_inputs

from tests.support.retained_authority_sources import materialize_retained_sources

ROOT = Path(__file__).resolve().parents[2]
DIRECTORY = ROOT / "ci/test_shards"
NATIVE_NODES = frozenset(node for node in NEW_NODES if node.startswith(NATIVE_PREFIX_OWNER + "::"))


def retained_order() -> list[str]:
    descriptor = json.loads(
        git_bytes(ROOT, PREDECESSOR, "ci/test_shards/current-runtime-compatibility.json")
    )
    order, _ = retained_native_inventory(
        ROOT, DIRECTORY, descriptor["native_serial_role"], NATIVE_NODES
    )
    return order


def test_current_authority_source_requires_its_complete_git_producer(tmp_path: Path) -> None:
    head = subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=ROOT, text=True).strip()
    assert producer_inputs(ROOT, head) == runtime_inputs(ROOT)
    snapshot = tmp_path / "source-data"
    snapshot.mkdir()
    materialize_retained_sources(ROOT, snapshot, revision=head)
    assert producer_inputs(snapshot, head) == runtime_inputs(snapshot)
    with pytest.raises(SystemExit, match="actual runtime checkout"):
        current_native_role(snapshot, snapshot / "ci/test_shards", {}, {}, NATIVE_NODES)
    changed = snapshot / "src/warhammer40k_core/adapters/linux_session.py"
    changed.write_bytes(changed.read_bytes() + b"\n# unmeasured source change\n")
    with pytest.raises(SystemExit, match="complete producer inputs differ"):
        producer_inputs(snapshot, head)


def test_new_runtime_does_not_fit_the_retained_four_source_exception() -> None:
    from scripts.boolean_los_admission import SUCCESSOR_FILE, validate_successor

    reviewed = json.loads(git_bytes(ROOT, PREDECESSOR, SUCCESSOR_FILE))
    with pytest.raises(SystemExit):
        validate_successor(original_inputs(ROOT, SOURCE_PRODUCER), runtime_inputs(ROOT), reviewed)


def test_shared_reader_preserves_the_complete_retained_covered_proof(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    from scripts import build_test_shards as sharding

    snapshot = tmp_path / "retained-source-data"
    snapshot.mkdir()
    materialize_retained_sources(ROOT, snapshot)
    monkeypatch.setattr(sharding, "REPOSITORY_ROOT", snapshot)
    monkeypatch.setattr(sharding, "TESTS_ROOT", snapshot / "tests")
    baseline = json.loads((DIRECTORY / "current-covered-baseline.json").read_bytes())
    reference = {
        "file": "current-covered-evidence.json",
        "sha256": hashlib.sha256(
            (DIRECTORY / "current-covered-evidence.json").read_bytes()
        ).hexdigest(),
    }
    seconds = verify_complete_covered_profile(
        ROOT,
        DIRECTORY,
        reference,
        baseline,
        original_inputs(ROOT, SOURCE_PRODUCER),
        retained_order(),
        filename="current-covered-evidence.json",
    )
    old = json.loads(git_bytes(ROOT, PREDECESSOR, "ci/test_shards/durations.json"))
    assert (
        seconds
        == old["runtime_compatibility"]["native_serial_role"]["with_mirror_native_phase_seconds"]
    )


@pytest.mark.parametrize(
    "change", ["artifact_hash", "source", "supervisor", "branch", "worker", "phase"]
)
def test_shared_complete_proof_rejects_drift(tmp_path: Path, change: str) -> None:
    baseline = json.loads((DIRECTORY / "current-covered-baseline.json").read_bytes())
    record = json.loads((DIRECTORY / "current-covered-evidence.json").read_bytes())
    if change == "artifact_hash":
        record["coverage"]["sha256"] = "0" * 64
    else:
        target = (
            record["parallel_workers"]["gw0"]
            if change in {"worker", "phase"}
            else record[
                {"source": "preflight", "supervisor": "supervisor", "branch": "coverage"}[change]
            ]
        )
        value = json.loads(target["text"])
        if change == "source":
            value["inputs"].pop(next(iter(value["inputs"])))
        elif change == "supervisor":
            value["approved"] = False
        elif change == "branch":
            value["meta"]["branch_coverage"] = False
        elif change == "worker":
            value["worker_count"] = "31"
        else:
            value["reports"][0]["outcome"] = "failed"
        target["text"] = json.dumps(value)
        target["sha256"] = hashlib.sha256(target["text"].encode()).hexdigest()
    path = tmp_path / "evidence.json"
    path.write_text(json.dumps(record), encoding="utf-8")
    reference = {"file": path.name, "sha256": hashlib.sha256(path.read_bytes()).hexdigest()}
    with pytest.raises(SystemExit):
        verify_complete_covered_profile(
            ROOT,
            tmp_path,
            reference,
            baseline,
            original_inputs(ROOT, SOURCE_PRODUCER),
            retained_order(),
            filename=path.name,
        )


def test_new_selector_cannot_relocate_retained_work() -> None:
    old = json.loads(git_bytes(ROOT, PREDECESSOR, "ci/test_shards/current-derived-assignment.json"))
    groups = [list(old["shards"][str(index)]) for index in range(1, 13)]
    groups[-1] = sorted([*groups[-1], OWNER])
    require_frozen_assignment(ROOT, tuple(tuple(group) for group in groups))
    moved = copy.deepcopy(groups)
    moved[-1].append(moved[0].pop())
    with pytest.raises(SystemExit, match="cannot move a retained selector"):
        require_frozen_assignment(ROOT, tuple(tuple(group) for group in moved))
    groups[-1].remove(OWNER)
    with pytest.raises(SystemExit, match="exactly once"):
        require_frozen_assignment(ROOT, tuple(tuple(group) for group in groups))


def test_unmeasured_native_standalone_is_not_an_invented_timing() -> None:
    baseline = json.loads((DIRECTORY / "current-covered-baseline.json").read_bytes())
    costs = cast(dict[str, float], baseline["case_seconds"])
    with (
        historical_snapshot(ROOT) as history,
        pytest.raises(SystemExit, match="complete role observation"),
    ):
        derived_score((NATIVE_PREFIX_OWNER,), costs, costs, history.cohorts[-1])


def test_live_authority_profile_has_complete_fresh_evidence_and_fixed_inventory() -> None:
    from scripts.build_test_shards import summary_case_seconds

    descriptor = json.loads((DIRECTORY / "current-runtime-compatibility.json").read_bytes())
    assert descriptor["schema"] == SCHEMA
    assert descriptor["current_runtime_fingerprint"] == RUNTIME
    assert descriptor["baseline"]["file"] == BASELINE_FILE
    assert descriptor["fresh_evidence"]["file"] == EVIDENCE_FILE
    summary = json.loads((DIRECTORY / "durations.json").read_bytes())
    cases = summary_case_seconds(summary)
    selected = plan(ROOT, DIRECTORY, cases)
    assert len(cases) == 6341
    assert cases.keys() >= NODES
    assert sum(len(group) for group in selected.groups) == 509
    require_frozen_assignment(ROOT, selected.groups)
