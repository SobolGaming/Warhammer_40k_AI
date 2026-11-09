# pyright: reportPrivateUsage=false
from __future__ import annotations

import copy
import hashlib
import json
import subprocess
from pathlib import Path
from typing import cast

import pytest
import scripts.build_test_shards as sharding
from scripts.hosted_timing_calibration import (
    FILENAME,
    FORMULA,
    ROLE,
    build_calibration,
    calibrated_seconds,
    load_planning_seconds,
    passed_phases,
    read_json,
)


@pytest.fixture
def measured(tmp_path: Path) -> tuple[Path, dict[str, float], Path, dict[str, object]]:
    root = tmp_path / "repo"
    (root / "tests").mkdir(parents=True)
    (root / "tests/a.py").write_text("def test_a():\n    assert True\n")
    (root / "src/warhammer40k_core").mkdir(parents=True)
    (root / "src/warhammer40k_core/_engine_build_manifest.json").write_text(
        json.dumps({"fingerprint": "a" * 64})
    )
    for arguments in (
        ["init", "-q"],
        ["add", "."],
        [
            "-c",
            "user.name=Test",
            "-c",
            "user.email=test@example.invalid",
            "commit",
            "-qm",
            "fixture",
        ],
    ):
        subprocess.run(["git", *arguments], cwd=root, check=True, capture_output=True)
    head = subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=root, text=True).strip()
    baseline = {"tests/a.py::first": 10.0, "tests/a.py::second": 20.0}
    raw = tmp_path / "gw0.json"
    raw.write_text(
        json.dumps(
            {
                "worker": "gw0",
                "worker_count": "4",
                "github_run_id": "123",
                "github_sha": "b" * 40,
                "exit_status": 0,
                "elapsed_seconds": 40.0,
                "collected_nodeids": list(baseline),
                "reports": [
                    {
                        "nodeid": "tests/a.py::first",
                        "phase": phase,
                        "seconds": seconds,
                        "outcome": "passed",
                    }
                    for phase, seconds in (("setup", 4.0), ("call", 30.0), ("teardown", 1.0))
                ],
            }
        )
    )
    source: dict[str, object] = {
        "run_id": 123,
        "attempt": 2,
        "artifact_id": 456,
        "pr_head": head,
        "checkout": "b" * 40,
        "conclusion": "failure",
        "runtime_fingerprint": "a" * 64,
    }
    return root, baseline, raw, source


def test_calibration_keeps_failed_run_and_complete_baseline_separate(
    measured: tuple[Path, dict[str, float], Path, dict[str, object]],
) -> None:
    root, baseline, raw, source = measured
    original = dict(baseline)
    result = build_calibration(inputs=((raw, source),), baseline=baseline, root=root)
    assert baseline == original
    assert result["baseline_only_cases"] == ["tests/a.py::second"]
    assert result["observed_cases"] == 1
    assert result["observations"] == {"tests/a.py::first": [[0, 4.0, 30.0, 1.0]]}
    reports = cast(list[dict[str, object]], result["reports"])
    assert reports[0]["source"] == source
    assert reports[0]["sha256"] == hashlib.sha256(raw.read_bytes()).hexdigest()
    assert calibrated_seconds(result, baseline=baseline, root=root) == {
        "tests/a.py::first": 35.0,
        "tests/a.py::second": 20.0,
    }


def test_samples_remain_separate_and_never_combine_cross_worker_phases(
    measured: tuple[Path, dict[str, float], Path, dict[str, object]],
) -> None:
    root, baseline, raw, source = measured
    second = raw.with_name("gw1.json")
    payload = json.loads(raw.read_text())
    payload["worker"] = "gw1"
    payload["reports"][0]["seconds"] = 8.0
    payload["reports"][1]["seconds"] = 10.0
    second.write_text(json.dumps(payload))
    result = build_calibration(
        inputs=((raw, source), (second, {**source, "attempt": 3, "artifact_id": 457})),
        baseline=baseline,
        root=root,
    )
    assert result["observations"] == {
        "tests/a.py::first": [[0, 4.0, 30.0, 1.0], [1, 8.0, 10.0, 1.0]]
    }
    assert calibrated_seconds(result, baseline=baseline, root=root)["tests/a.py::first"] == 35.0
    first_phases = payload["reports"][:1]
    rest_phases = payload["reports"][1:]
    assert passed_phases(first_phases) == ({}, 1)
    assert passed_phases(rest_phases) == ({}, 1)


@pytest.mark.parametrize(
    "mutation", ["missing", "duplicate", "failed", "negative", "boolean", "nan", "unknown_phase"]
)
def test_phase_admission_is_closed(
    measured: tuple[Path, dict[str, float], Path, dict[str, object]],
    mutation: str,
) -> None:
    _, _, raw, _ = measured
    phases = json.loads(raw.read_text())["reports"]
    if mutation == "missing":
        phases.pop()
    elif mutation == "duplicate":
        phases.append(phases[0])
    elif mutation == "failed":
        phases[0]["outcome"] = "failed"
    elif mutation == "unknown_phase":
        phases[0]["phase"] = "collection"
    else:
        phases[0]["seconds"] = {"negative": -1, "boolean": True, "nan": float("nan")}[mutation]
    if mutation in ("missing", "failed"):
        assert passed_phases(phases) == ({}, 1)
    else:
        with pytest.raises(SystemExit, match="calibration"):
            passed_phases(phases)


@pytest.mark.parametrize(
    "mutation",
    [
        "checkout",
        "run",
        "exit",
        "workers",
        "uncollected",
        "unknown",
        "duplicate",
        "source",
        "build",
    ],
)
def test_raw_report_source_and_inventory_are_checked(
    measured: tuple[Path, dict[str, float], Path, dict[str, object]],
    mutation: str,
) -> None:
    root, baseline, raw, source = measured
    row = json.loads(raw.read_text())
    if mutation == "checkout":
        row["github_sha"] = "c" * 40
    elif mutation == "run":
        row["github_run_id"] = "999"
    elif mutation == "exit":
        row["exit_status"] = 1
    elif mutation == "workers":
        row["worker_count"] = "12"
    elif mutation == "uncollected":
        row["collected_nodeids"] = ["tests/a.py::second"]
    elif mutation == "unknown":
        row["collected_nodeids"].append("tests/a.py::unknown")
    elif mutation == "duplicate":
        row["collected_nodeids"].append(row["collected_nodeids"][0])
    elif mutation == "source":
        (root / "tests/a.py").write_text("changed test")
    elif mutation == "build":
        source["runtime_fingerprint"] = "c" * 64
    raw.write_text(json.dumps(row))
    with pytest.raises(SystemExit, match="Calibration"):
        build_calibration(inputs=((raw, source),), baseline=baseline, root=root)


@pytest.mark.parametrize(
    "mutation",
    [
        "count",
        "baseline_only",
        "sample_duplicate",
        "sample_index",
        "sample_missing",
        "digest",
        "source",
        "inventory",
        "extra",
    ],
)
def test_sidecar_rejects_drift(
    measured: tuple[Path, dict[str, float], Path, dict[str, object]],
    mutation: str,
) -> None:
    root, baseline, raw, source = measured
    result = build_calibration(inputs=((raw, source),), baseline=baseline, root=root)
    value = json.loads(json.dumps(result))
    if mutation == "count":
        value["observed_cases"] = 2
    elif mutation == "baseline_only":
        value["baseline_only_cases"] = []
    elif mutation == "sample_duplicate":
        value["observations"]["tests/a.py::first"] *= 2
    elif mutation == "sample_index":
        value["observations"]["tests/a.py::first"][0][0] = True
    elif mutation == "sample_missing":
        value["reports"][0]["passed_cases"] = 2
    elif mutation == "digest":
        value["reports"][0]["sha256"] = "invalid"
    elif mutation == "source":
        (root / "tests/a.py").write_text("changed")
    elif mutation == "inventory":
        baseline["tests/a.py::new"] = 3.0
    elif mutation == "extra":
        value["certified"] = True
    with pytest.raises(SystemExit, match=r"[Cc]alibration"):
        calibrated_seconds(value, baseline=baseline, root=root)


def test_same_derived_node_costs_drive_assignment_and_real_dispatch(
    measured: tuple[Path, dict[str, float], Path, dict[str, object]],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    root, baseline, raw, source = measured
    value = build_calibration(inputs=((raw, source),), baseline=baseline, root=root)
    directory = root / "ci"
    directory.mkdir()
    path = directory / FILENAME
    path.write_text(json.dumps(value))
    monkeypatch.setattr(sharding, "REPOSITORY_ROOT", root)
    selectors = {"tests/a.py::first": 15.0, "tests/a.py::second": 15.0}
    planning, cases, digest = sharding._planning_inputs(directory, selectors, baseline)
    assert planning == cases == {"tests/a.py::first": 35.0, "tests/a.py::second": 20.0}
    profile: dict[str, object] = {
        "files": selectors,
        "case_seconds": baseline,
        "profiles": [
            {
                "source": "complete baseline",
                "junit_sha256": ["a" * 64],
                "test_cases": 2,
                "test_files": 1,
            }
        ],
        "calibration": {"file": FILENAME, "sha256": digest, "role": ROLE, "formula": FORMULA},
    }
    original = copy.deepcopy(profile)
    assert sharding.dispatch_case_seconds(profile, directory / "durations.json") == planning
    assert profile == original
    path.write_text(json.dumps({**value, "role": "passing profile"}))
    with pytest.raises(SystemExit, match="digest"):
        sharding.dispatch_case_seconds(profile, directory / "durations.json")


def test_sidecar_duplicate_keys_and_changed_bytes_fail_closed(tmp_path: Path) -> None:
    path = tmp_path / FILENAME
    path.write_text('{"schema": 1, "schema": 2}')
    with pytest.raises(SystemExit, match="Duplicate"):
        read_json(path)
    with pytest.raises(SystemExit, match="digest"):
        load_planning_seconds(path, baseline={}, root=tmp_path, expected_sha256="a" * 64)


@pytest.mark.parametrize("outcome", ["passed", "failed", "skipped"])
@pytest.mark.parametrize("complete", [False, True])
def test_all_raw_case_ids_are_checked_before_outcome_filtering(
    measured: tuple[Path, dict[str, float], Path, dict[str, object]],
    outcome: str,
    complete: bool,
) -> None:
    root, baseline, raw, source = measured
    payload = json.loads(raw.read_text())
    extra = [dict(row, nodeid="tests/a.py::unknown", outcome=outcome) for row in payload["reports"]]
    payload["reports"].extend(extra if complete else extra[:1])
    raw.write_text(json.dumps(payload))
    with pytest.raises(SystemExit, match="uncollected"):
        build_calibration(inputs=((raw, source),), baseline=baseline, root=root)


def test_calibrated_selector_costs_ignore_input_dictionary_order() -> None:
    selectors = {"tests/a.py": 1.0, "tests/b.py::one": 2.0}
    cases = {
        "tests/a.py::one": 1e16,
        "tests/a.py::two": 1.0,
        "tests/a.py::three": 1.0,
        "tests/b.py::one": 2.0,
    }
    expected = {"tests/a.py": 1.0000000000000002e16, "tests/b.py::one": 2.0}
    assert sharding._calibrated_selectors(selectors, cases) == expected
    assert (
        sharding._calibrated_selectors(
            dict(reversed(tuple(selectors.items()))), dict(reversed(tuple(cases.items())))
        )
        == expected
    )


@pytest.mark.parametrize("same_worker", [False, True])
def test_repeated_report_or_completed_case_within_artifact_is_rejected(
    measured: tuple[Path, dict[str, float], Path, dict[str, object]],
    same_worker: bool,
) -> None:
    root, baseline, raw, source = measured
    second = raw.with_name("second.json")
    row = json.loads(raw.read_text())
    row["worker"] = "gw0" if same_worker else "gw1"
    second.write_text(json.dumps(row, indent=2))
    with pytest.raises(SystemExit, match="Duplicate"):
        build_calibration(inputs=((raw, source), (second, source)), baseline=baseline, root=root)


def test_isolated_and_parallel_workers_are_distinct_invocations(
    measured: tuple[Path, dict[str, float], Path, dict[str, object]],
) -> None:
    root, baseline, raw, source = measured
    second = raw.with_name("isolated.json")
    row = json.loads(raw.read_text())
    row["worker_count"] = "1"
    row["collected_nodeids"] = ["tests/a.py::second"]
    for phase in row["reports"]:
        phase["nodeid"] = "tests/a.py::second"
    second.write_text(json.dumps(row))
    result = build_calibration(
        inputs=((raw, source), (second, source)), baseline=baseline, root=root
    )
    assert result["observed_cases"] == 2
    assert calibrated_seconds(result, baseline=baseline, root=root) == dict.fromkeys(baseline, 35.0)
