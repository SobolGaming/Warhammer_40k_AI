from __future__ import annotations

import hashlib
import json
import shutil
import subprocess
import sys
from collections.abc import Iterator
from pathlib import Path
from typing import cast

import pytest
from scripts import build_test_shards as sharding
from scripts import current_shard_compatibility as compatibility
from scripts.historical_shard_snapshot import (
    HISTORICAL_REVISION,
    MANIFEST,
    HistoricalSnapshot,
    fingerprint,
    historical_snapshot,
)
from scripts.shard_execution_model import Cohort, load_cohorts

ROOT = Path(__file__).resolve().parents[2]
DIRECTORY = ROOT / "ci/test_shards"


@pytest.fixture(scope="module")
def admitted() -> tuple[dict[str, object], compatibility.Plan]:
    summary = json.loads((DIRECTORY / "durations.json").read_bytes())
    return summary, compatibility.plan(ROOT, DIRECTORY, sharding.summary_case_seconds(summary))


@pytest.fixture(scope="module")
def historical() -> Iterator[HistoricalSnapshot]:
    with historical_snapshot(ROOT) as snapshot:
        yield snapshot


def test_current_dispatch_has_exact_inventory_and_disclosed_selector_moves(
    admitted: tuple[dict[str, object], compatibility.Plan], historical: HistoricalSnapshot
) -> None:
    summary, plan = admitted
    cases = sharding.summary_case_seconds(summary)
    additions = cases.keys() - historical.baseline.keys()
    assert len(cases) == 6319
    assert len(additions) == 37
    assert plan.dispatch.keys() == cases.keys()
    assert all(plan.dispatch[node] >= cases[node] for node in historical.baseline)
    assert all(plan.dispatch[node] == cases[node] for node in additions)
    owner = "tests/rules/section03/test_terrain_path_preparation.py"
    assert {node.split("::", 1)[0] for node in additions} == {
        owner,
        "tests/rules/section11/test_connected_endpoints.py",
    }
    original = {
        selector: index for index, group in enumerate(historical.groups, 1) for selector in group
    }
    current = {selector: index for index, group in enumerate(plan.groups, 1) for selector in group}
    expected_moves = [
        {"selector": selector, "from": original[selector], "to": current[selector]}
        for selector in sorted(original)
        if original[selector] != current[selector]
    ]
    assert plan.metadata["retained_selector_moves"] == expected_moves
    assert sum(name == owner for group in plan.groups for name in group) == 1
    assert sharding.SERIAL_BEHAVIORAL_CASE in plan.groups[1]
    assert sharding.SERIAL_BEHAVIORAL_CASE not in plan.groups[0]
    assert plan.groups[4] == historical.groups[4]
    assert len({name for group in plan.groups for name in group}) == 506


def test_current_raw_projections_keep_missing_observations_null(
    admitted: tuple[dict[str, object], compatibility.Plan], historical: HistoricalSnapshot
) -> None:
    _, plan = admitted
    rows = cast(dict[str, dict[str, object]], plan.metadata["shards"])
    assert plan.metadata["historical_reservation_seconds_unchanged"] == 465.533262819
    assert historical.scope.extension is not None
    assert len(historical.scope.extension.raw.cases) == 6281
    for row in rows.values():
        for key in ("original_6014_partial_raw", "expanded_6281_partial_raw"):
            raw = cast(dict[str, object], row[key])
            assert (raw["full_raw_role_score"] is None) == bool(raw["missing_nodes"])
        scores = cast(list[float], row["derived_historical_plus_current_additions"])
        assert max(scores[:-2]) <= 1076
        assert scores[-2] <= 1054
        assert scores[-1] <= 1050
    assert (
        plan.metadata["historical_scoped_allocation"]
        == json.loads((historical.directory / "durations.json").read_bytes())["scoped_allocation"]
    )


def test_generator_checker_and_live_dispatch_use_same_current_costs(
    admitted: tuple[dict[str, object], compatibility.Plan],
) -> None:
    summary, plan = admitted
    assert sharding.dispatch_case_seconds(summary, DIRECTORY / "durations.json") == plan.dispatch
    subprocess.run(
        [sys.executable, "-B", "scripts/build_test_shards.py", "--check", "--shard-count", "12"],
        cwd=ROOT,
        check=True,
        timeout=180,
    )
    files = plan.files.copy()
    expected, repeated = compatibility.derive_summary(
        ROOT,
        DIRECTORY,
        dict(reversed(tuple(files.items()))),
        dict(reversed(tuple(sharding.summary_case_seconds(summary).items()))),
        tuple(plan.profiles),
        12,
    )
    assert expected == summary
    assert repeated.groups == plan.groups


def test_absent_descriptor_preserves_strict_legacy_runtime_guard(
    admitted: tuple[dict[str, object], compatibility.Plan], tmp_path: Path
) -> None:
    summary, _ = admitted
    with pytest.raises(SystemExit, match="runtime differs"):
        load_cohorts(DIRECTORY, root=ROOT, nodes=set(sharding.summary_case_seconds(summary)))
    (tmp_path / compatibility.BASELINE_FILE).write_text("{}")
    with pytest.raises(SystemExit, match="descriptor is missing"):
        compatibility.enabled(tmp_path)


@pytest.mark.parametrize(
    "change",
    [
        "schema",
        "history",
        "runtime",
        "hash",
        "receipt",
        "workers",
        "mirror",
        "coverage",
        "source",
        "node",
        "new_node",
        "test_hash",
        "historical_receipt",
    ],
)
def test_compatibility_boundary_rejects_stale_or_forged_inputs(
    tmp_path: Path, change: str, admitted: tuple[dict[str, object], compatibility.Plan]
) -> None:
    summary, _ = admitted
    shutil.copytree(DIRECTORY, tmp_path, dirs_exist_ok=True)
    path = tmp_path / compatibility.FILENAME
    descriptor = json.loads(path.read_bytes())
    baseline_path = tmp_path / compatibility.BASELINE_FILE
    baseline = json.loads(baseline_path.read_bytes())
    if change == "schema":
        descriptor["schema"] += "-forged"
    elif change == "history":
        descriptor["historical_revision"] = "0" * 40
    elif change == "runtime":
        descriptor["current_runtime_fingerprint"] = "0" * 64
    elif change == "hash":
        descriptor["baseline"]["sha256"] = "0" * 64
    elif change == "receipt":
        baseline["supervisor"]["approved"] = False
    elif change == "workers":
        baseline["workers"] = 12
    elif change == "mirror":
        baseline["mirror_workers"] = 4
    elif change == "coverage":
        baseline["coverage_percent"] = 66.99
    elif change == "source":
        baseline["source_head"] = HISTORICAL_REVISION
    elif change == "node":
        baseline["case_seconds"].pop(next(iter(baseline["case_seconds"])))
    elif change == "new_node":
        node = next(node for node in baseline["case_seconds"] if node in compatibility.NEW_NODES)
        baseline["case_seconds"][node + "-forged"] = baseline["case_seconds"].pop(node)
    elif change == "test_hash":
        descriptor["new_test_sources"][next(iter(descriptor["new_test_sources"]))] = "0" * 64
    else:
        evidence = tmp_path / "hosted-calibration.json"
        evidence.write_bytes(evidence.read_bytes() + b"\n")
    if change in {"receipt", "workers", "mirror", "coverage", "source", "node", "new_node"}:
        baseline_path.write_text(json.dumps(baseline) + "\n")
        descriptor["baseline"]["sha256"] = hashlib.sha256(baseline_path.read_bytes()).hexdigest()
    path.write_text(json.dumps(descriptor) + "\n")
    costs = (
        baseline["case_seconds"]
        if change in {"node", "new_node"}
        else sharding.summary_case_seconds(summary)
    )
    with pytest.raises(SystemExit, match="twenty-seven" if change == "new_node" else None):
        compatibility.plan(ROOT, tmp_path, costs)


@pytest.mark.parametrize("change", ["files", "profiles"])
def test_current_summary_cannot_change_baseline_file_costs_or_provenance(
    admitted: tuple[dict[str, object], compatibility.Plan], change: str
) -> None:
    summary, plan = admitted
    files = plan.files.copy()
    profiles = json.loads(json.dumps(summary["profiles"]))
    if change == "files":
        files[next(iter(files))] += 1
    else:
        profiles[0]["source"] += "-forged"
    with pytest.raises(SystemExit, match="differ from covered baseline"):
        compatibility.derive_summary(
            ROOT, DIRECTORY, files, sharding.summary_case_seconds(summary), tuple(profiles), 12
        )


def test_source_authentication_fails_for_missing_or_wrong_git_manifest(
    historical: HistoricalSnapshot, tmp_path: Path
) -> None:
    from scripts import historical_shard_snapshot as snapshots

    with pytest.raises(SystemExit, match="source object is unavailable"):
        fingerprint(ROOT, "0" * 40)
    repository = tmp_path / "repository"
    subprocess.run(["git", "init", "--quiet", str(repository)], check=True)
    manifest = repository / MANIFEST
    manifest.parent.mkdir(parents=True)
    manifest.write_text(json.dumps({"fingerprint": "0" * 64}))
    subprocess.run(["git", "add", "."], cwd=repository, check=True)
    subprocess.run(
        [
            "git",
            "-c",
            "user.name=fixture",
            "-c",
            "user.email=fixture@example.invalid",
            "commit",
            "--quiet",
            "-m",
            "adversarial manifest",
        ],
        cwd=repository,
        check=True,
    )
    revision = (
        subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=repository).decode().strip()
    )
    evidence = tmp_path / "evidence"
    evidence.mkdir()
    record = json.loads((historical.directory / "hosted-calibration.json").read_bytes())
    for report in record["reports"]:
        report["source"]["pr_head"] = revision
        report["source"]["checkout"] = revision
    (evidence / "hosted-calibration.json").write_text(json.dumps(record))
    shutil.copyfile(
        historical.directory / "allocation-scope.json", evidence / "allocation-scope.json"
    )
    with pytest.raises(SystemExit, match="producer runtime fingerprint differs from Git"):
        snapshots.authenticate_producers(repository, evidence)


def test_tested_checkout_tree_is_authenticated_against_git(tmp_path: Path) -> None:
    from scripts import historical_shard_snapshot as snapshots

    shutil.copytree(DIRECTORY, tmp_path, dirs_exist_ok=True)
    path = tmp_path / "scoped-worker-extension.json"
    value = json.loads(path.read_bytes())
    value["merge_binding"]["tested_tree"] = "0" * 40
    path.write_text(json.dumps(value))
    with pytest.raises(SystemExit, match="tested merge tree or parents differ"):
        snapshots.authenticate_producers(ROOT, tmp_path)


def test_ci_fetches_only_exact_declared_source_objects() -> None:
    from scripts.fetch_scheduling_sources import revisions

    anchors = revisions(DIRECTORY)
    assert anchors == tuple(sorted(set(anchors)))
    assert len(anchors) == 37
    workflow = (ROOT / ".github/workflows/ci.yml").read_text()
    assert workflow.count("run: python3 -B scripts/fetch_scheduling_sources.py") == 4


def test_derived_current_chunks_charge_full_addition_cost_and_reuse_setup_once() -> None:
    old = "tests/fake.py::old"
    new = "tests/fake.py::new"
    group = "tests/fake.py::fixtures::catalog"
    cohort = Cohort("historical", {old: 3.0}, {old: group}, {group: 7.0}, 2.0, 9.0)
    costs = {old: 3.0, new: 5.0}
    assert compatibility.derived_score(("tests/fake.py",), costs, costs, cohort) == 12.0
    assert cohort.cases == {old: 3.0}
    assert cohort.setup == {group: 7.0}


def test_derived_mirror_remains_a_separate_serial_fixture_lane() -> None:
    serial = sharding.SERIAL_BEHAVIORAL_CASE
    old = "tests/fake.py::old"
    new = "tests/fake.py::new"
    group = "catalog"
    cohort = Cohort(
        "historical", {old: 3.0, serial: 11.0}, {old: group, serial: group}, {group: 7.0}, 2.0, 9.0
    )
    costs = {old: 3.0, new: 5.0, serial: 11.0}
    assert compatibility.derived_score(("tests/fake.py", serial), costs, costs, cohort) == 37.0


@pytest.mark.parametrize(
    "change",
    [
        "schema",
        "baseline",
        "missing",
        "duplicate",
        "fixed",
        "pin",
        "mirror",
        "disclosure",
        "scores",
    ],
)
def test_current_assignment_rejects_tampered_data(
    tmp_path: Path, change: str, admitted: tuple[dict[str, object], compatibility.Plan]
) -> None:
    summary, _ = admitted
    shutil.copytree(DIRECTORY, tmp_path, dirs_exist_ok=True)
    path = tmp_path / "current-derived-assignment.json"
    record = json.loads(path.read_bytes())
    if change == "schema":
        record["schema"] += "-forged"
    elif change == "baseline":
        record["baseline_sha256"] = "0" * 64
    elif change == "missing":
        record["shards"]["1"].pop()
    elif change == "duplicate":
        record["shards"]["1"].append(record["shards"]["2"][0])
        record["shards"]["1"].sort()
    elif change in {"fixed", "pin", "mirror"}:
        from scripts.scoped_shard_extension import FIXED_OWNER, PINNED_OWNER

        shard, selector = {
            "fixed": ("5", FIXED_OWNER),
            "pin": ("4", PINNED_OWNER),
            "mirror": ("2", sharding.SERIAL_BEHAVIORAL_CASE),
        }[change]
        record["shards"][shard].remove(selector)
        replacement = record["shards"]["1"].pop()
        record["shards"][shard].append(replacement)
        record["shards"][shard].sort()
        record["shards"]["1"].append(selector)
        record["shards"]["1"].sort()
    elif change == "disclosure":
        record["retained_selector_moves"] = []
    else:
        record["scores"] = [0.0] * 12
    path.write_text(json.dumps(record) + "\n")
    descriptor_path = tmp_path / compatibility.FILENAME
    descriptor = json.loads(descriptor_path.read_bytes())
    descriptor["assignment"]["sha256"] = hashlib.sha256(path.read_bytes()).hexdigest()
    descriptor_path.write_text(json.dumps(descriptor) + "\n")
    with pytest.raises(SystemExit):
        compatibility.plan(ROOT, tmp_path, sharding.summary_case_seconds(summary))


@pytest.mark.parametrize(
    ("index", "seconds"), [(0, 1076.001), (8, 1054.001), (9, 1050.001), (0, float("nan"))]
)
def test_each_original_planning_ceiling_remains_mandatory(index: int, seconds: float) -> None:
    from scripts.current_shard_assignment import require_planning_limits

    values = [0.0] * 10
    values[index] = seconds
    with pytest.raises(SystemExit, match="unchanged planning ceilings"):
        require_planning_limits(tuple(values))


def test_source_bootstrap_preserves_history_for_shared_historical_clones(tmp_path: Path) -> None:
    def git(directory: Path, *arguments: str) -> str:
        return (
            subprocess.check_output(
                [
                    "git",
                    "-c",
                    "user.name=history fixture",
                    "-c",
                    "user.email=fixture@example.invalid",
                    *arguments,
                ],
                cwd=directory,
                stderr=subprocess.PIPE,
                timeout=30,
            )
            .decode()
            .strip()
        )

    origin = tmp_path / "origin"
    origin.mkdir()
    git(origin, "init", "--quiet")
    git(origin, "symbolic-ref", "HEAD", "refs/heads/main")
    (origin / "initial.txt").write_text("shared initial history")
    git(origin, "add", ".")
    git(origin, "commit", "--quiet", "-m", "initial")
    initial = git(origin, "rev-parse", "HEAD")
    git(origin, "checkout", "--quiet", "-b", "historical")
    (origin / "anchor.txt").write_text("required immutable historical anchor")
    git(origin, "add", ".")
    git(origin, "commit", "--quiet", "-m", "anchor")
    anchor = git(origin, "rev-parse", "HEAD")
    (origin / "historical-tip.txt").write_text("historical source tip")
    git(origin, "add", ".")
    git(origin, "commit", "--quiet", "-m", "historical tip")
    historical_tip = git(origin, "rev-parse", "HEAD")
    git(origin, "checkout", "--quiet", "-b", "producer", initial)
    (origin / "producer.txt").write_text("newly required producer")
    git(origin, "add", ".")
    git(origin, "commit", "--quiet", "-m", "producer")
    producer = git(origin, "rev-parse", "HEAD")
    git(origin, "checkout", "--quiet", "main")
    (origin / "current.txt").write_text("current source")
    git(origin, "add", ".")
    git(origin, "commit", "--quiet", "-m", "main source")
    current = git(origin, "rev-parse", "HEAD")

    checkout = tmp_path / "checkout"
    subprocess.run(
        [
            "git",
            "clone",
            "--quiet",
            "--no-local",
            "--single-branch",
            "--branch",
            "main",
            str(origin),
            str(checkout),
        ],
        check=True,
        timeout=30,
    )
    git(checkout, "fetch", "--quiet", "origin", historical_tip)
    assert git(checkout, "rev-parse", "--is-shallow-repository") == "false"
    assert git(checkout, "cat-file", "-t", anchor) == "commit"
    scripts = checkout / "scripts"
    scripts.mkdir()
    shutil.copyfile(
        ROOT / "scripts/fetch_scheduling_sources.py", scripts / "fetch_scheduling_sources.py"
    )
    directory = checkout / "ci/test_shards"
    directory.mkdir(parents=True)
    source = {"pr_head": producer, "checkout": producer}
    for name, record in {
        "hosted-calibration.json": {"reports": [{"source": source}]},
        "allocation-scope.json": {"source": source},
        "current-runtime-compatibility.json": {"historical_revision": current},
        "current-covered-baseline.json": {"source_head": current},
    }.items():
        (directory / name).write_text(json.dumps(record))
    subprocess.run(
        [sys.executable, "-B", str(scripts / "fetch_scheduling_sources.py")],
        cwd=checkout,
        check=True,
        timeout=120,
    )

    borrowed = tmp_path / "borrowed"
    subprocess.run(
        ["git", "clone", "--shared", "--no-checkout", "--quiet", str(checkout), str(borrowed)],
        check=True,
        timeout=30,
    )
    git(borrowed, "update-ref", "--no-deref", "HEAD", anchor)
    assert git(borrowed, "rev-parse", "HEAD") == anchor
    assert git(checkout, "rev-parse", "--is-shallow-repository") == "false"
    assert git(checkout, "cat-file", "-t", producer) == "commit"
