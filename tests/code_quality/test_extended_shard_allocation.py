from __future__ import annotations

import copy
import hashlib
import json
import math
import os
import shutil
import subprocess
import sys
from pathlib import Path

import pytest
from scripts import build_test_shards as sharding
from scripts.extended_shard_allocation import allocate_extended, partial_projection
from scripts.finite_case_partitions import FILENAME, OWNERS, partitions, validate_cases
from scripts.scoped_shard_evidence import ScopedEvidence, load_declared_scope, load_scope
from scripts.scoped_shard_extension import (
    EXTENSION_FILE,
    FIXED_OWNER,
    PINNED_OWNER,
    STRESS_FILE,
    ExtendedScope,
    load_extension,
)
from scripts.shard_execution_model import Cohort, load_cohorts

ROOT = Path(__file__).resolve().parents[2]
DIRECTORY = ROOT / "ci/test_shards"
PRIOR = "b9b1c97a6a2da6fca624c7f30c471d6cfab56320"
CALIBRATION_FETCH = "git fetch --no-tags --no-recurse-submodules origin " + PRIOR


def test_quality_producers_fetch_exact_pre_squash_calibration_before_validation() -> None:
    workflow = (ROOT / ".github/workflows/ci.yml").read_text(encoding="utf-8")
    step = (
        "      - name: Fetch pre-squash calibration validation input\n"
        "        run: " + CALIBRATION_FETCH + "\n\n"
    )
    assert workflow.count(step) == 2
    for name, following in (
        ("quality-policy", "quality-shards"),
        ("quality-shards", "semantic-audit-macos"),
    ):
        lane = workflow.split("  " + name + ":\n", 1)[1].split("  " + following + ":\n", 1)[0]
        assert lane.count(step) == 1
        assert lane.index("name: Checkout repository") < lane.index(step)
        assert lane.index(step) < lane.index("scripts.quality_runner run")
        assert "continue-on-error" not in lane
        if name == "quality-policy":
            assert lane.index(step) < lane.index("scripts.check_performance_policy")


def test_exact_fetch_restores_squashed_away_calibration_in_main_only_checkout(
    tmp_path: Path,
) -> None:
    """Exercise the workflow command on real, small main/topic/squash Git history."""

    def git(root: Path, *args: str) -> bytes:
        return subprocess.check_output(
            [
                "git",
                "-c",
                "user.name=CI history test",
                "-c",
                "user.email=ci@example.invalid",
                *args,
            ],
            cwd=root,
            stderr=subprocess.PIPE,
            timeout=30,
        )

    origin = tmp_path / "origin"
    origin.mkdir()
    git(origin, "init", "--initial-branch=main", "--quiet")
    git(origin, "config", "core.autocrlf", "false")
    directory = origin / "ci/test_shards"
    directory.mkdir(parents=True)
    files = (
        "hosted-calibration.json",
        "durations.json",
        "allocation-scope.json",
        "scoped-worker-evidence.json",
        "case-partitions.json",
        "preflight-case-partition.json",
    )
    for name in files:
        (directory / name).write_bytes(b'{"observation":"original"}\n')
    git(origin, "add", ".")
    git(origin, "commit", "--quiet", "-m", "Original history")
    anchor = git(origin, "rev-parse", "HEAD").decode().strip()
    git(origin, "checkout", "--quiet", "-b", "topic")
    for name in files:
        (directory / name).write_bytes(b'{"observation":"prior calibration"}\n')
    git(origin, "commit", "--quiet", "-am", "Pre-append calibration")
    prior = git(origin, "rev-parse", "HEAD").decode().strip()
    original = {name: git(origin, "show", prior + ":ci/test_shards/" + name) for name in files}
    (directory / files[0]).write_bytes(b'{"observation":"appended calibration"}\n')
    git(origin, "commit", "--quiet", "-am", "Append observations")
    git(origin, "checkout", "--quiet", "main")
    git(origin, "merge", "--squash", "topic")
    git(origin, "commit", "--quiet", "-m", "Squashed calibration repair")
    checkout = tmp_path / "checkout"
    git(
        tmp_path,
        "clone",
        "--quiet",
        "--no-local",
        "--single-branch",
        "--branch",
        "main",
        str(origin),
        str(checkout),
    )
    head = git(checkout, "rev-parse", "HEAD")
    assert not (checkout / ".git/objects/info/alternates").exists()
    # Full main history and the older anchor do not include the squashed topic commit.
    command = CALIBRATION_FETCH.split()
    git(checkout, *command[1:-1], anchor)
    for name in files:
        missing = subprocess.run(
            ["git", "show", prior + ":ci/test_shards/" + name],
            cwd=checkout,
            capture_output=True,
            check=False,
            timeout=30,
        )
        assert missing.returncode == 128
        assert missing.stdout == b""
    # Substitute only the fixture's exact commit identity in the production command.
    assert command[-1] == PRIOR
    git(checkout, *command[1:-1], prior)
    assert git(checkout, "rev-parse", "FETCH_HEAD").decode().strip() == prior
    assert git(checkout, "rev-parse", "HEAD") == head
    assert git(checkout, "status", "--porcelain") == b""
    for name in files:
        assert git(checkout, "show", prior + ":ci/test_shards/" + name) == original[name]


@pytest.fixture(scope="module")
def inputs() -> tuple[dict[str, float], ScopedEvidence]:
    summary = json.loads((DIRECTORY / "durations.json").read_bytes())
    costs = sharding.dispatch_case_seconds(summary, DIRECTORY / "durations.json")
    scope = load_declared_scope(DIRECTORY, root=ROOT, costs=costs)
    assert scope is not None
    assert scope.extension is not None
    return costs, scope


def test_complete_append_preserves_every_prior_observation_and_baseline() -> None:
    old = json.loads(
        subprocess.check_output(
            ["git", "show", PRIOR + ":ci/test_shards/hosted-calibration.json"], cwd=ROOT
        )
    )
    current = json.loads((DIRECTORY / "hosted-calibration.json").read_bytes())
    assert current["reports"][:843] == old["reports"]
    assert len(current["reports"]) == 892
    assert sum(map(len, current["observations"].values())) == 113105
    for node, observations in old["observations"].items():
        assert current["observations"][node][: len(observations)] == observations
    before = json.loads(
        subprocess.check_output(["git", "show", PRIOR + ":ci/test_shards/durations.json"], cwd=ROOT)
    )
    after = json.loads((DIRECTORY / "durations.json").read_bytes())
    assert before["profiles"] == after["profiles"]
    assert before["case_seconds"] == after["case_seconds"]
    for filename in (
        "allocation-scope.json",
        "scoped-worker-evidence.json",
        "case-partitions.json",
        "preflight-case-partition.json",
    ):
        assert (DIRECTORY / filename).read_bytes() == subprocess.check_output(
            ["git", "show", PRIOR + ":ci/test_shards/" + filename], cwd=ROOT
        )
    for owner, ratios in partitions(ROOT, set(OWNERS)).items():
        assert math.fsum(after["files"][node] for node in ratios) == before["files"][owner]
    assert all(row["source"]["conclusion"] == "failure" for row in current["reports"][843:])


def test_extension_retains_unknown_and_failed_job_without_changing_original_scope(
    inputs: tuple[dict[str, float], ScopedEvidence],
) -> None:
    costs, base = inputs
    extension = base.extension
    assert extension is not None
    assert len(base.known_nodes) == 6014
    assert len(base.frozen_nodes) == 268
    assert len(extension.raw.cases) == 6281
    assert extension.unknown_node not in extension.raw.cases
    assert extension.raw.setup == base.cohort.setup
    assert extension.raw.parallel_residual == base.cohort.parallel_residual
    assert extension.raw.mirror_residual == base.cohort.mirror_residual
    assert extension.stress.cases[extension.unknown_node] == extension.reservation_seconds
    assert extension.reservation_seconds == 465.533262819
    assert all(extension.stress.cases[node] == value for node, value in extension.raw.cases.items())
    raw = json.loads((DIRECTORY / EXTENSION_FILE).read_bytes())
    workers = {r["payload"]["worker"]: r["payload"] for r in raw["reports"]}
    assert set(workers) == {"gw0", "gw1", "gw3", "gw4"}
    assert len(workers["gw4"]["reports"]) == 61 * 3
    assert all(r["worker_count"] == "4" and r["exit_status"] == 0 for r in workers.values())
    assert raw["failed_supervisor"]["payload"]["workload_exit_code"] == 1
    assert raw["source"]["conclusion"] == "failure"
    assert extension.raw.cases.keys() | {extension.unknown_node} == costs.keys()


def test_current_allocation_matches_reviewed_candidate_and_preserves_raw_null(
    inputs: tuple[dict[str, float], ScopedEvidence],
) -> None:
    costs, base = inputs
    extension = base.extension
    assert extension is not None
    groups = [tuple((DIRECTORY / f"shard-{i}.txt").read_text().splitlines()) for i in range(1, 13)]
    digest = hashlib.sha256((json.dumps(groups, separators=(",", ":")) + "\n").encode()).hexdigest()
    assert digest == "04070c21fbcb5a0f968e619bd6176de4761e27bc81def1b40ab3eda529978ea0"
    assert PINNED_OWNER in groups[3]
    assert len(groups[3]) > 1
    assert groups[4] == (FIXED_OWNER,)
    assert sharding.SERIAL_BEHAVIORAL_CASE in groups[1]
    assert sharding.SERIAL_BEHAVIORAL_CASE not in groups[0]
    assert sum(map(len, groups)) == 504
    for i, group in enumerate(groups):
        row = partial_projection(group, costs, extension.raw)
        assert (row["full_raw_role_score"] is None) == (i == 3)
    cohorts = load_cohorts(DIRECTORY, root=ROOT, nodes=set(costs))
    assert len(cohorts) == 9
    summary = json.loads((DIRECTORY / "durations.json").read_bytes())
    rows = summary["scoped_allocation"]["shards"].values()
    assert max(max(row["historical"]) for row in rows) <= 1076
    assert max(row["derived_stress"] for row in rows) <= 1054
    assert max(row["latest_complete"] for row in rows) <= 1050


@pytest.mark.parametrize(
    "change",
    [
        "missing_phase",
        "duplicate_phase",
        "nan",
        "worker",
        "exit",
        "collection_order",
        "source",
        "unknown",
        "producer_window",
        "reserve",
        "reserve_source",
        "missing_file",
    ],
)
def test_extension_and_planning_reserve_fail_closed(
    tmp_path: Path,
    inputs: tuple[dict[str, float], ScopedEvidence],
    change: str,
) -> None:
    costs, current = inputs
    index = json.loads((DIRECTORY / "allocation-cohorts.json").read_bytes())
    base = load_scope(DIRECTORY, root=ROOT, costs=costs, reference=index["scoped_evidence"])
    assert base.extension is None
    assert current.extension is not None
    for filename in (
        "allocation-cohorts.json",
        "allocation-scope.json",
        "hosted-calibration.json",
        "durations.json",
    ):
        shutil.copyfile(DIRECTORY / filename, tmp_path / filename)
    raw = json.loads((DIRECTORY / EXTENSION_FILE).read_bytes())
    stress = json.loads((DIRECTORY / STRESS_FILE).read_bytes())
    payload = raw["reports"][0]["payload"]
    if change == "missing_phase":
        payload["reports"].pop()
    elif change == "duplicate_phase":
        payload["reports"].append(payload["reports"][0])
    elif change == "nan":
        payload["reports"][0]["seconds"] = float("nan")
    elif change == "worker":
        payload["worker"] = "gw2"
    elif change == "exit":
        payload["exit_status"] = 1
    elif change == "collection_order":
        payload["collected_nodeids"].reverse()
    elif change == "source":
        payload["github_sha"] = "0" * 40
    elif change == "unknown":
        raw["unknown_nodes"] = []
    elif change == "producer_window":
        raw["artifact"]["artifact_created_at"] = "2000-01-01T00:00:00Z"
    elif change == "reserve":
        stress["reservation_seconds"] += 1
    elif change == "reserve_source":
        stress["sources"][0]["call"] += 1
    raw["reports"][0]["sha256"] = hashlib.sha256(
        (json.dumps(payload, indent=2) + "\n").encode()
    ).hexdigest()
    raw_path = tmp_path / EXTENSION_FILE
    raw_path.write_text(json.dumps(raw), encoding="utf-8")
    stress["extension"]["sha256"] = hashlib.sha256(raw_path.read_bytes()).hexdigest()
    stress_path = tmp_path / STRESS_FILE
    stress_path.write_text(json.dumps(stress), encoding="utf-8")
    reference = {
        "file": STRESS_FILE,
        "sha256": hashlib.sha256(stress_path.read_bytes()).hexdigest(),
    }
    if change == "missing_file":
        raw_path.unlink()
    with pytest.raises(SystemExit):
        load_extension(tmp_path, root=ROOT, costs=costs, base=base, reference=reference)


def test_step5g_partitions_match_real_collection_and_original_git_bytes(tmp_path: Path) -> None:
    before = {owner: (ROOT / owner).read_bytes() for owner in OWNERS}
    result = subprocess.run(
        [
            sys.executable,
            "-m",
            "pytest",
            *OWNERS,
            "--collect-only",
            "-q",
            "-n0",
            "--no-cov",
            "--basetemp",
            str(tmp_path / "collection"),
        ],
        cwd=ROOT,
        env={**os.environ, "PYTHONDONTWRITEBYTECODE": "1"},
        capture_output=True,
        text=True,
        check=True,
    )
    collected = {
        line
        for line in result.stdout.splitlines()
        if any(line.startswith(owner + "::") for owner in OWNERS)
    }
    declared = partitions(ROOT, set(OWNERS))
    assert len(collected) == 62
    assert collected == {node for ratios in declared.values() for node in ratios}
    assert all((ROOT / owner).read_bytes() == value for owner, value in before.items())
    assert before[next(iter(OWNERS))].count(b"\r\n") == 84
    validate_cases(ROOT, dict.fromkeys(collected, 1.0))
    with pytest.raises(SystemExit, match="complete case inventory"):
        validate_cases(ROOT, dict.fromkeys(sorted(collected)[1:], 1.0))


@pytest.mark.parametrize("change", ["source", "drop", "nan", "extra"])
def test_step5g_partition_source_and_inventory_fail_closed(tmp_path: Path, change: str) -> None:
    for owner in OWNERS:
        target = tmp_path / owner
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes((ROOT / owner).read_bytes())
    value = json.loads((DIRECTORY / FILENAME).read_bytes())
    owner = next(iter(OWNERS))
    row = value["partitions"][owner]
    if change == "source":
        (tmp_path / owner).write_bytes(b"changed")
    elif change == "drop":
        row["nodes"].pop()
    elif change == "nan":
        row["weights"][row["nodes"][0]] = float("nan")
    else:
        value["unreviewed"] = True
    path = tmp_path / "ci/test_shards" / FILENAME
    path.parent.mkdir(parents=True)
    path.write_text(json.dumps(value), encoding="utf-8")
    with pytest.raises(SystemExit):
        partitions(tmp_path, set(OWNERS))


def test_extended_allocator_keeps_pins_roles_and_measurements() -> None:
    serial = sharding.SERIAL_BEHAVIORAL_CASE
    nodes = {f"tests/{module}.py::test_{i}": 2.0 for module in "abcdefghijk" for i in range(4)}
    nodes.update(
        {PINNED_OWNER + "::test_unknown": 3.0, FIXED_OWNER + "::test_fixed": 4.0, serial: 3.0}
    )
    unknown = PINNED_OWNER + "::test_unknown"
    raw = Cohort("raw", {n: v for n, v in nodes.items() if n != unknown}, {}, {}, 1.0, 4.0)
    stress = Cohort("derived", nodes.copy(), {}, {}, 1.0, 4.0)
    scope = ExtendedScope(raw, stress, unknown, PINNED_OWNER, 4, FIXED_OWNER, 5, {}, 3.0)
    cohorts = (
        *(Cohort(str(i), nodes.copy(), {}, {}, 1.0, 4.0) for i in range(8)),
        Cohort("43081418293-effective-attempt-1", nodes.copy(), {}, {}, 1.0, 4.0),
    )
    owners = {n.split("::", 1)[0] for n in nodes} - {serial.split("::", 1)[0]}
    weights = {
        owner: math.fsum(v for n, v in nodes.items() if n.startswith(owner + "::"))
        for owner in owners
    }
    weights[serial] = nodes[serial] * 4
    before = copy.deepcopy((weights, nodes, cohorts, scope))
    result = allocate_extended(weights, nodes, cohorts, 12, scope)
    assert PINNED_OWNER in result[3]
    assert result[4] == (FIXED_OWNER,)
    assert serial not in result[0]
    assert all(result)
    assert sorted(s for group in result for s in group) == sorted(weights)
    assert (weights, nodes, cohorts, scope) == before
    assert (
        allocate_extended(dict(reversed(tuple(weights.items()))), nodes, cohorts, 12, scope)
        == result
    )
    assert partial_projection(result[3], nodes, raw)["full_raw_role_score"] is None
