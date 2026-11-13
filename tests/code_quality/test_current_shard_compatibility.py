from __future__ import annotations

import hashlib
import json
import shutil
import subprocess
import sys
import xml.etree.ElementTree as ET
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
    assert len(cases) == 6331
    assert len(additions) == 49
    assert plan.dispatch.keys() == cases.keys()
    assert all(plan.dispatch[node] >= cases[node] for node in historical.baseline)
    assert all(plan.dispatch[node] == cases[node] for node in additions)
    owner = "tests/rules/section03/test_terrain_path_preparation.py"
    assert {node.split("::", 1)[0] for node in additions} == {
        owner,
        "tests/rules/section09/test_escape_survivor_persistence.py",
        "tests/rules/section11/test_connected_endpoints.py",
        "tests/factions/chaos_daemons/integration/test_cavalcade_native_screen_prefix.py",
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
    assert len({name for group in plan.groups for name in group}) == 508


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
    with pytest.raises(SystemExit, match="forty-nine" if change == "new_node" else None):
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
    assert len(anchors) == 38
    from scripts.current_native_serial_role import PRODUCER

    assert PRODUCER in anchors
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
        "current-native-serial-role.json": {"source_head": producer},
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


def test_native_serial_role_preserves_complete_phases_and_measurement_scope() -> None:
    from scripts.current_native_serial_role import load_native_serial_role

    descriptor = json.loads((DIRECTORY / compatibility.FILENAME).read_bytes())
    nodes = frozenset(
        node
        for node in compatibility.NEW_NODES
        if node.startswith(compatibility.NATIVE_PREFIX_OWNER + "::")
    )
    role = load_native_serial_role(ROOT, DIRECTORY, descriptor["native_serial_role"], nodes)
    assert role.seconds == 444.5446871509996
    assert role.metadata["worker_count"] == 1
    assert len(cast(list[str], role.metadata["cases"])) == 6
    assert role.seconds < cast(float, role.metadata["worker_elapsed_seconds"])
    assert "not the measured global source" in str(role.metadata["source_applicability"])
    assert "not hosted observations" in str(role.metadata["role"])
    assert (
        hashlib.sha256((DIRECTORY / compatibility.BASELINE_FILE).read_bytes()).hexdigest()
        == "7acac7eb2f8986bfd8d23edb2e3a61ac19048343491fb5f8e07c9d6ae1677508"
    )


@pytest.mark.parametrize(
    "change",
    [
        "raw_hash",
        "producer",
        "source",
        "movement_helper",
        "sequential_helper",
        "worker_count",
        "phase_missing",
        "phase_duplicate",
        "phase_failure",
        "approval",
        "runner",
        "junit_skip",
    ],
)
def test_native_serial_role_rejects_incomplete_or_different_observation(
    tmp_path: Path, change: str
) -> None:
    from scripts.current_native_serial_role import FILENAME, load_native_serial_role

    record = json.loads((DIRECTORY / FILENAME).read_bytes())
    if change == "raw_hash":
        record["raw"]["worker"]["sha256"] = "0" * 64
    elif change == "producer":
        record["source_head"] = HISTORICAL_REVISION
    elif change in {"source", "movement_helper", "sequential_helper"}:
        owner = {
            "source": "tests/support/cavalcade_v995.py",
            "movement_helper": "tests/movement_submission_helpers.py",
            "sequential_helper": "tests/sequential_translation_helpers.py",
        }[change]
        record["source_files"][owner] = "0" * 64
    elif change == "junit_skip":
        raw = record["raw"]["junit"]
        junit = ET.fromstring(raw["text"])
        ET.SubElement(next(junit.iter("testcase")), "skipped")
        raw["text"] = ET.tostring(junit, encoding="unicode")
        raw["sha256"] = hashlib.sha256(raw["text"].encode()).hexdigest()
    else:
        name = (
            "supervisor" if change == "approval" else "command" if change == "runner" else "worker"
        )
        raw = record["raw"][name]
        value = json.loads(raw["text"])
        if change == "worker_count":
            value["worker_count"] = "4"
        elif change == "phase_missing":
            value["reports"].pop()
        elif change == "phase_duplicate":
            value["reports"][-1] = value["reports"][0]
        elif change == "phase_failure":
            value["reports"][0]["outcome"] = "failed"
        elif change == "approval":
            value["approved"] = False
        else:
            value["inner_runner"]["max_seconds"] = 121
        raw["text"] = json.dumps(value)
        raw["sha256"] = hashlib.sha256(raw["text"].encode()).hexdigest()
        if change.startswith("phase_"):
            controller = json.loads(record["raw"]["controller"]["text"])
            controller["reports"] = value["reports"]
            record["raw"]["controller"]["text"] = json.dumps(controller)
            record["raw"]["controller"]["sha256"] = hashlib.sha256(
                json.dumps(controller).encode()
            ).hexdigest()
    path = tmp_path / FILENAME
    path.write_text(json.dumps(record))
    reference = {"file": FILENAME, "sha256": hashlib.sha256(path.read_bytes()).hexdigest()}
    nodes = frozenset(
        node
        for node in compatibility.NEW_NODES
        if node.startswith(compatibility.NATIVE_PREFIX_OWNER + "::")
    )
    with pytest.raises(SystemExit):
        load_native_serial_role(ROOT, tmp_path, reference, nodes)


def test_native_serial_score_uses_complete_role_once_without_old_case_duplication() -> None:
    mirror = sharding.SERIAL_BEHAVIORAL_CASE
    native = compatibility.NATIVE_PREFIX_OWNER
    old = "tests/fake.py::old"
    costs = {old: 3.0, mirror: 11.0, native + "::one": 100.0, native + "::two": 200.0}
    cohort = Cohort("historical", {old: 3.0, mirror: 11.0}, {}, {}, 2.0, 9.0)
    assert (
        compatibility.derived_score(
            ("tests/fake.py", mirror, native), costs, costs, cohort, native_serial_seconds=17.0
        )
        == 40.0
    )
    with pytest.raises(SystemExit, match="complete role observation"):
        compatibility.derived_score((mirror, native), costs, costs, cohort)
    assert (
        compatibility.derived_score((native,), costs, costs, cohort, native_serial_seconds=17.0)
        == 26.0
    )
    assert costs[native + "::one"] == 100.0
    assert costs[native + "::two"] == 200.0


def test_current_execution_summary_discloses_native_serial_accounting(
    admitted: tuple[dict[str, object], compatibility.Plan],
) -> None:
    summary, plan = admitted
    execution = cast(dict[str, object], summary["execution_model"])
    native = cast(dict[str, object], plan.metadata["native_serial_role"])
    assert execution["serial_selectors"] == [
        sharding.SERIAL_BEHAVIORAL_CASE,
        compatibility.NATIVE_PREFIX_OWNER,
    ]
    assert set(cast(list[str], execution["serial_cases"])) == {
        sharding.SERIAL_BEHAVIORAL_CASE,
        *cast(list[str], native["cases"]),
    }
    assert "assignment_wall_lower_bound_seconds" not in execution
    assert "assignment_wall_planning_estimate_seconds" in execution
    assert "not a physical lower bound" in str(execution["estimate_role"])
    assert "historical worker-chunk projection" in str(plan.metadata["partial_raw_role"])


@pytest.mark.parametrize(("parallel_residual", "mirror_residual"), [(2.0, 9.0), (9.0, 2.0)])
def test_native_serial_only_lane_charges_the_larger_existing_role_residual(
    parallel_residual: float, mirror_residual: float
) -> None:
    native = compatibility.NATIVE_PREFIX_OWNER
    old = "tests/fake.py::old"
    mirror = sharding.SERIAL_BEHAVIORAL_CASE
    costs = {old: 3.0, mirror: 11.0, native + "::one": 100.0, native + "::two": 200.0}
    cohort = Cohort(
        "historical", {old: 3.0, mirror: 11.0}, {}, {}, parallel_residual, mirror_residual
    )
    assert compatibility.derived_score(
        ("tests/fake.py", native), costs, costs, cohort, native_serial_seconds=17.0
    ) == 3.0 + 17.0 + max(parallel_residual, mirror_residual)
    assert (
        compatibility.derived_score(
            ("tests/fake.py", mirror, native), costs, costs, cohort, native_serial_seconds=17.0
        )
        == 3.0 + 11.0 + 17.0 + mirror_residual
    )
    assert (
        compatibility.derived_score(("tests/fake.py",), costs, costs, cohort)
        == 3.0 + parallel_residual
    )
