from __future__ import annotations

import copy
import hashlib
import json
import math
import os
import subprocess
import sys
from pathlib import Path
from typing import cast

import pytest
import scripts.build_test_shards as sharding
from scripts.preflight_case_partition import (
    FILENAME as PARTITION_FILE,
)
from scripts.preflight_case_partition import NODES, OWNER, partition, validate_case_inventory
from scripts.scoped_shard_allocation import allocate_scoped, role_scores, scoped_metadata
from scripts.scoped_shard_evidence import (
    EVIDENCE_FILE,
    FILENAME,
    ScopedEvidence,
    load_declared_scope,
    load_scope,
)
from scripts.shard_execution_model import Cohort, load_cohorts, worker_chunks

ROOT = Path(__file__).resolve().parents[2]
DIRECTORY = ROOT / "ci/test_shards"


@pytest.fixture(scope="module")
def inputs() -> tuple[dict[str, float], dict[str, object], ScopedEvidence]:
    summary = json.loads((DIRECTORY / "durations.json").read_bytes())
    costs = sharding.dispatch_case_seconds(summary, DIRECTORY / "durations.json")
    index = json.loads((DIRECTORY / "allocation-cohorts.json").read_bytes())
    scope = load_scope(DIRECTORY, root=ROOT, costs=costs, reference=index["scoped_evidence"])
    return costs, summary, scope


def test_partial_scope_is_complete_only_within_its_declared_known_inventory(
    inputs: tuple[dict[str, float], dict[str, object], ScopedEvidence],
) -> None:
    costs, summary, scope = inputs
    before = (DIRECTORY / "hosted-calibration.json").read_bytes()
    ordinary = json.loads(before)
    assert len(ordinary["reports"]) == 892
    assert sum(len(rows) for rows in ordinary["observations"].values()) == 113105
    assert (
        sum(sum(row[0] < 843 for row in rows) for rows in ordinary["observations"].values())
        == 106823
    )
    assert len(scope.known_nodes) == 6014
    assert len(scope.frozen_nodes) == 268
    assert scope.known_nodes | scope.frozen_nodes == costs.keys()
    assert not scope.known_nodes & scope.frozen_nodes
    assert scope.cohort.cases.keys() == scope.known_nodes
    assert len(scope.frozen_selectors) == 28
    shards = tuple(
        tuple((DIRECTORY / f"shard-{number}.txt").read_text().splitlines())
        for number in range(1, 13)
    )
    historical = json.loads((DIRECTORY / FILENAME).read_bytes())
    assert list(scope.frozen_selectors) == historical["frozen_selectors"]
    assert (
        hashlib.sha256(("\n".join(scope.frozen_selectors) + "\n").encode()).hexdigest()
        == (historical["frozen_manifest_sha256"])
    )
    assert sum(map(len, worker_chunks(scope.frozen_selectors, costs))) == 268
    cohorts = load_cohorts(DIRECTORY, root=ROOT, nodes=set(costs))
    assert len(cohorts) == 9
    current = load_declared_scope(DIRECTORY, root=ROOT, costs=costs)
    assert current is not None
    assert current.extension is not None
    actual = scoped_metadata(shards, costs, cohorts, current)
    assert actual == summary["scoped_allocation"]
    row = cast(dict[str, dict[str, object]], actual["shards"])["4"]
    assert cast(dict[str, object], row["expanded_6281_partial_raw"])["full_raw_role_score"] is None
    assert (DIRECTORY / "hosted-calibration.json").read_bytes() == before


@pytest.mark.parametrize(
    "change",
    [
        "missing_phase",
        "nan",
        "duplicate",
        "source",
        "unknown",
        "frozen",
        "missing_worker",
        "supervisor",
        "producer_window",
        "artifact_worker",
        "missing_data",
    ],
)
def test_scoped_evidence_rejects_missing_invalid_or_misattributed_inputs(
    tmp_path: Path,
    inputs: tuple[dict[str, float], dict[str, object], ScopedEvidence],
    change: str,
) -> None:
    costs, _, _ = inputs
    index = json.loads((DIRECTORY / FILENAME).read_bytes())
    evidence = json.loads((DIRECTORY / EVIDENCE_FILE).read_bytes())
    node = next(iter(evidence["observations"]))
    if change == "missing_phase":
        evidence["observations"][node][0].pop()
    elif change == "nan":
        evidence["observations"][node][0][2] = float("nan")
    elif change == "duplicate":
        evidence["observations"][node].append(evidence["observations"][node][0])
    elif change == "source":
        evidence["reports"][0]["source"]["checkout"] = "0" * 40
    elif change == "unknown":
        evidence["observations"]["tests/unknown.py::test_unknown"] = evidence["observations"].pop(
            node
        )
    elif change == "frozen":
        index["known_nodes"].append(index["frozen_nodes"][0])
    elif change == "missing_worker":
        evidence["reports"].pop()
    elif change == "supervisor":
        receipt = index["supervisors"][0]
        receipt["payload"]["elapsed_seconds"] = 0.0
        receipt["sha256"] = hashlib.sha256(
            (json.dumps(receipt["payload"], indent=2) + "\n").encode()
        ).hexdigest()
    elif change == "producer_window":
        index["artifacts"][0]["artifact_created_at"] = "2000-01-01T00:00:00Z"
    elif change == "artifact_worker":
        index["artifacts"][0]["worker_sha256"].pop()
    data = tmp_path / EVIDENCE_FILE
    data.write_text(json.dumps(evidence) + "\n", encoding="utf-8")
    index["evidence"]["sha256"] = hashlib.sha256(data.read_bytes()).hexdigest()
    path = tmp_path / FILENAME
    path.write_text(json.dumps(index) + "\n", encoding="utf-8")
    reference = {"file": FILENAME, "sha256": hashlib.sha256(path.read_bytes()).hexdigest()}
    if change == "missing_data":
        data.unlink()
    with pytest.raises(SystemExit, match=r"[Ss]coped|[Cc]alibration|[Aa]llocation"):
        load_scope(tmp_path, root=ROOT, costs=costs, reference=reference)


def test_preflight_partition_matches_real_collection_and_preserves_source(tmp_path: Path) -> None:
    before = (ROOT / OWNER).read_bytes()
    result = subprocess.run(
        [
            sys.executable,
            "-m",
            "pytest",
            OWNER,
            "--collect-only",
            "-q",
            "--basetemp",
            str(tmp_path / "collection"),
        ],
        cwd=ROOT,
        env={**os.environ, "PYTHONDONTWRITEBYTECODE": "1"},
        text=True,
        capture_output=True,
        check=True,
    )
    collected = sorted(line for line in result.stdout.splitlines() if line.startswith(OWNER + "::"))
    assert collected == list(NODES)
    assert set(partition(ROOT, frozenset({OWNER}))) == set(NODES)
    assert (ROOT / OWNER).read_bytes() == before


def test_preflight_inventory_and_partition_changes_fail_closed(tmp_path: Path) -> None:
    with pytest.raises(SystemExit, match="complete measured case inventory"):
        validate_case_inventory(dict.fromkeys(NODES[:-1], 1.0))
    source = tmp_path / OWNER
    source.parent.mkdir(parents=True)
    source.write_bytes((ROOT / OWNER).read_bytes())
    data = tmp_path / "ci/test_shards" / PARTITION_FILE
    data.parent.mkdir(parents=True)
    value = json.loads((DIRECTORY / PARTITION_FILE).read_bytes())
    value["nodes"].pop()
    data.write_text(json.dumps(value), encoding="utf-8")
    with pytest.raises(SystemExit, match="exact inventory"):
        partition(tmp_path, frozenset({OWNER}))
    data.write_bytes((DIRECTORY / PARTITION_FILE).read_bytes())
    source.write_bytes(source.read_bytes() + b"\n")
    with pytest.raises(SystemExit, match="source"):
        partition(tmp_path, frozenset({OWNER}))


def test_scoped_allocator_never_estimates_frozen_cases_or_changes_costs() -> None:
    serial = sharding.SERIAL_BEHAVIORAL_CASE
    costs = {
        f"tests/{module}.py::test_{case}": 2.0 for module in "abcdefghijkz" for case in range(4)
    }
    costs[serial] = 3.0
    frozen = frozenset(node for node in costs if node.startswith("tests/z.py::"))
    known = frozenset(costs) - frozen
    complete = Cohort("complete", costs.copy(), {}, {}, 1.0, 6.0)
    partial = Cohort("partial", {node: costs[node] for node in known}, {}, {}, 2.0, 8.0)
    scope = ScopedEvidence(partial, 4, ("tests/z.py",), known, frozen, {})
    weights = {
        **dict.fromkeys((f"tests/{module}.py" for module in "abcdefghijkz"), 8.0),
        serial: 12.0,
    }
    before = copy.deepcopy((weights, costs, complete, scope))
    result = allocate_scoped(weights, costs, (complete,), 12, scope)
    assert result[3] == scope.frozen_selectors
    assert sorted(selector for group in result for selector in group) == sorted(weights)
    assert all(result)
    active = [group for index, group in enumerate(result) if index != 3]
    assert math.ceil(max(role_scores(result[0], costs, (complete, partial)))) == min(
        math.ceil(max(role_scores(group, costs, (complete, partial)))) for group in active
    )
    assert (
        cast(dict[str, object], scoped_metadata(result, costs, (complete,), scope)["shards"])["4"]
        is None
    )
    assert (weights, costs, complete, scope) == before
