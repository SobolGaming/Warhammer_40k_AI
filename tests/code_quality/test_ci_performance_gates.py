# pyright: reportPrivateUsage=false

from __future__ import annotations

import hashlib
import json
import os
import subprocess
import sys
import tomllib
import xml.etree.ElementTree as ET
from collections.abc import Callable
from pathlib import Path
from types import SimpleNamespace
from typing import cast

import pytest
import scripts.build_test_shards as sharding
from scripts.check_shard_coverage import check_shard_coverage

ROOT = Path(__file__).resolve().parents[2]


def test_duration_dispatch_balances_actual_initial_worksteal_chunks() -> None:
    assert sharding.duration_worksteal_order(
        ("tests/rounded.py::case",), workers=4, selector_seconds={"tests/rounded.py": 0.0}
    ) == (0,)
    weights: dict[str, float] = {
        f"tests/{name}.py": value for name, value in (("a", 240), ("b", 8), ("c", 8), ("d", 8))
    }
    all_nodes = tuple(f"tests/{name}.py::case_{index}" for name in "abcd" for index in range(8))
    for nodes in (all_nodes, all_nodes[:-1]):
        order = sharding.duration_worksteal_order(nodes, workers=4, selector_seconds=weights)
        assert sorted(order) == list(range(len(nodes)))
        counts = {file: sum(node.startswith(file + "::") for node in nodes) for file in weights}
        totals: list[float] = []
        offset = 0
        for worker in range(4):
            width = (len(nodes) - offset) // (4 - worker)
            chunk = [nodes[index] for index in order[offset : offset + width]]
            costs = [weights[node.split("::")[0]] / counts[node.split("::")[0]] for node in chunk]
            assert costs == sorted(costs, reverse=True)
            totals.append(sum(costs))
            offset += width
        assert offset == len(nodes)
        assert max(totals) - min(totals) < 2
        assert max(totals) < 70  # Alphabetic initial dispatch strands 240 seconds on one worker.


@pytest.mark.parametrize("bad_weight", [None, -1, float("nan"), True])
def test_duration_dispatch_rejects_missing_or_invalid_measurements(bad_weight: object) -> None:
    weights = {} if bad_weight is None else {"tests/a.py": bad_weight}
    with pytest.raises(SystemExit, match="scheduling weight"):
        sharding.duration_worksteal_order(
            ("tests/a.py::case",), workers=4, selector_seconds=cast(dict[str, float], weights)
        )


def test_duration_dispatch_profile_controls_the_real_worker_hook(
    tmp_path: Path, pytestconfig: pytest.Config, monkeypatch: pytest.MonkeyPatch
) -> None:
    from tests import conftest as root_hooks

    implementations = pytestconfig.hook.pytest_collection_modifyitems.get_hookimpls()
    execution = [
        implementation.function
        for implementation in reversed(implementations)
        if not implementation.hookwrapper and not implementation.wrapper
    ]
    builtin = next(
        implementation.function
        for implementation in implementations
        if implementation.plugin_name == "main"
    )
    assert execution.index(builtin) < execution.index(root_hooks.pytest_collection_modifyitems)
    weights: dict[str, float] = {
        f"tests/{name}.py": value for name, value in (("a", 240), ("b", 8), ("c", 8), ("d", 8))
    }
    names = tuple(f"tests/{name}.py::case_{index}" for name in "abcd" for index in range(8))
    profile = tmp_path / "durations.json"
    case_seconds = {name: weights[name.split("::", 1)[0]] / 8 for name in names}
    case_seconds[names[8]] = 100.0
    weights["tests/b.py"] = 107.0
    profile.write_text(
        json.dumps(
            {
                "files": weights,
                "case_seconds": case_seconds,
                "profiles": [
                    {
                        "source": "complete dispatch fixture",
                        "junit_sha256": ["a" * 64],
                        "test_cases": len(names),
                        "test_files": len(weights),
                    }
                ],
            }
        )
    )
    items = [cast(pytest.Item, SimpleNamespace(nodeid=name)) for name in names]
    expected = sharding.duration_worksteal_order(names, workers=4, selector_seconds=case_seconds)
    monkeypatch.setattr(pytestconfig, "workerinput", {"s25_scheduler": "worksteal"}, raising=False)
    monkeypatch.setenv("SHARD_ID", "duration-dispatch-control")
    monkeypatch.setenv("PYTEST_XDIST_WORKER_COUNT", "4")
    monkeypatch.setenv("BEHAVIORAL_DISPATCH_PROFILE", str(profile))
    root_hooks.pytest_collection_modifyitems(pytestconfig, items)
    assert [item.nodeid for item in items] == [names[index] for index in expected]
    profile.write_text(json.dumps({"case_seconds": {}}))
    with pytest.raises(SystemExit, match="scheduling weight"):
        root_hooks.pytest_collection_modifyitems(pytestconfig, items)


def test_serial_mirror_balancing_preserves_measurements_and_accounts_for_execution() -> None:
    mirror = sharding.SERIAL_BEHAVIORAL_CASE.split("::", 1)[0]
    durations = {
        mirror: 20.0,
        sharding.SERIAL_BEHAVIORAL_CASE: 180.0,
        "tests/second.py": 350.0,
        "tests/third.py": 340.0,
        "tests/fourth.py": 100.0,
    }
    case_seconds = {
        sharding.SERIAL_BEHAVIORAL_CASE: 180.0,
        mirror + "::remainder": 20.0,
        "tests/second.py::one": 175.0,
        "tests/second.py::two": 175.0,
        "tests/third.py::one": 170.0,
        "tests/third.py::two": 170.0,
        "tests/fourth.py::one": 50.0,
        "tests/fourth.py::two": 50.0,
    }
    shards = sharding._balanced_shards(
        durations=durations, shard_count=2, case_seconds=case_seconds
    )
    isolated = next(shard for shard in shards if mirror in shard.test_files)
    assert isolated.test_files == (mirror, sharding.SERIAL_BEHAVIORAL_CASE)
    assert isolated.duration_seconds == 200.0
    assert sum(shard.duration_seconds for shard in shards) == sum(durations.values())
    assert (
        sharding._execution_weights(durations, {sharding.SERIAL_BEHAVIORAL_CASE: 180.0})[
            sharding.SERIAL_BEHAVIORAL_CASE
        ]
        == 720.0
    )
    with pytest.raises(SystemExit, match="serial mirror"):
        sharding._balanced_shards(durations=durations, shard_count=2, case_seconds={})
    with pytest.raises(SystemExit, match="serial mirror"):
        sharding._balanced_shards(durations=durations, shard_count=2)
    # A two-case file must not sit behind the serial node merely because its
    # average parallel share looks smaller than its longest indivisible case.
    uneven = {
        mirror: 0.0,
        sharding.SERIAL_BEHAVIORAL_CASE: 180.0,
        "tests/a.py": 900.0,
        "tests/b.py": 800.0,
        "tests/heavy.py": 200.0,
        "tests/light.py": 100.0,
    }
    node_costs = {sharding.SERIAL_BEHAVIORAL_CASE: 180.0}
    for file, count, seconds in (
        ("a", 9, 100.0),
        ("b", 8, 100.0),
        ("heavy", 2, 100.0),
        ("light", 4, 25.0),
    ):
        node_costs.update({f"tests/{file}.py::case_{index}": seconds for index in range(count)})
    planned = sharding._balanced_shards(durations=uneven, shard_count=3, case_seconds=node_costs)
    serial_shard = next(
        shard for shard in planned if sharding.SERIAL_BEHAVIORAL_CASE in shard.test_files
    )
    assert "tests/heavy.py" not in serial_shard.test_files
    assert "tests/light.py" in serial_shard.test_files


@pytest.mark.stubbed
def test_junit_case_profiles_preserve_class_parameters_and_complete_nodes(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _write_sample_shards(tmp_path=tmp_path, monkeypatch=monkeypatch)
    profile = tmp_path / "cases.xml"
    profile.write_text(
        '<testsuite tests="3"><testcase classname="tests.unit.test_first.TestGroup" '
        'name="test_first[slow]" time="9" /><testcase classname="tests.unit.test_first" '
        'name="test_first[fast]" time="1" /><testcase classname="tests.unit.test_second" '
        'name="test_second" time="2" /></testsuite>'
    )
    assert sharding._case_profile_medians((profile,)) == {
        "tests/unit/test_first.py::TestGroup::test_first[slow]": 9.0,
        "tests/unit/test_first.py::test_first[fast]": 1.0,
        "tests/unit/test_second.py::test_second": 2.0,
    }
    profile.write_text(profile.read_text().replace("TestGroup", "OtherGroup"))
    changed = tmp_path / "changed.xml"
    changed.write_text(profile.read_text().replace("[slow]", "[new]"))
    with pytest.raises(SystemExit, match="case inventories"):
        sharding._case_profile_medians((profile, changed))


WORKFLOW_PATH = ROOT / ".github" / "workflows" / "ci.yml"


def test_ready_pull_requests_and_merge_groups_trigger_ci() -> None:
    trigger_block = WORKFLOW_PATH.read_text(encoding="utf-8").partition("\njobs:")[0]

    assert "      - ready_for_review" in trigger_block
    assert "  merge_group:\n    types: [checks_requested]" in trigger_block


def test_coverage_gate_is_a_fail_closed_behavior_aggregate(tmp_path: Path) -> None:
    workflow = WORKFLOW_PATH.read_text(encoding="utf-8")
    separator = "\n  coverage-gate:\n"
    assert separator in workflow
    coverage_gate = workflow.partition(separator)[2]

    assert "always() &&" in coverage_gate
    assert "needs: behavior-tests" in coverage_gate
    assert "if: needs.behavior-tests.result != 'success'" in coverage_gate
    assert 'echo "One or more behavioral shards did not succeed."' in coverage_gate
    assert "exit 1" in coverage_gate
    assert "merge-multiple: true" not in coverage_gate
    validator = "python scripts/check_shard_coverage.py coverage-data --shard-count 12"
    combine = "coverage combine coverage-data/behavior-coverage-*"
    assert coverage_gate.index(validator) < coverage_gate.index(combine)

    for invalid in (None, "missing", "extra", "wrong-name", "empty", "extra-file", "directory"):
        root = tmp_path / str(invalid)
        expected = tuple(
            root / f"behavior-coverage-{shard}" / f".coverage.{shard}" for shard in range(1, 13)
        )
        for path in expected:
            path.parent.mkdir(parents=True)
            path.write_bytes(b"coverage input admission fixture")
        if invalid is None:
            assert check_shard_coverage(root, shard_count=12) == expected
            continue
        if invalid == "missing":
            expected[-1].unlink()
            expected[-1].parent.rmdir()
        elif invalid == "extra":
            (root / "behavior-coverage-13").mkdir()
        elif invalid == "wrong-name":
            expected[0].rename(expected[0].with_name(".coverage.2"))
        elif invalid == "empty":
            expected[0].write_bytes(b"")
        elif invalid == "extra-file":
            expected[0].with_name(".coverage.extra").write_bytes(b"unexpected input")
        elif invalid == "directory":
            expected[0].unlink()
            expected[0].mkdir()
        with pytest.raises(SystemExit):
            check_shard_coverage(root, shard_count=12)


def test_junit_file_attribute_wins_over_classname() -> None:
    expected = frozenset(
        {
            "tests/unit/test_actual.py",
            "tests/unit/test_misleading.py",
        }
    )
    testcase = ET.fromstring(
        '<testcase file="tests/unit/test_actual.py" '
        'classname="tests.unit.test_misleading.TestRules" time="1.0" />'
    )

    assert sharding._test_file_from_testcase(testcase, expected=expected) == (
        "tests/unit/test_actual.py"
    )


def test_junit_classname_fallback_discards_test_class_segments() -> None:
    expected = frozenset({"tests/unit/test_rules.py"})
    testcase = ET.fromstring('<testcase classname="tests.unit.test_rules.TestRules" time="1.0" />')

    assert sharding._test_file_from_testcase(testcase, expected=expected) == (
        "tests/unit/test_rules.py"
    )


def test_junit_file_attribute_rejects_paths_outside_behavioral_inventory() -> None:
    expected = frozenset({"tests/unit/test_rules.py"})
    testcase = ET.fromstring(
        '<testcase file="../tests/unit/test_rules.py" '
        'classname="tests.unit.test_rules" time="1.0" />'
    )

    with pytest.raises(SystemExit, match="not repository-relative"):
        sharding._test_file_from_testcase(testcase, expected=expected)


@pytest.mark.stubbed
def test_manifest_check_rejects_assignment_drift(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    output_dir = _write_sample_shards(tmp_path=tmp_path, monkeypatch=monkeypatch)
    shard_one = output_dir / "shard-1.txt"
    shard_two = output_dir / "shard-2.txt"
    assert all(b"\r" not in path.read_bytes() for path in output_dir.iterdir())
    first_entry = shard_one.read_text(encoding="utf-8")
    second_entry = shard_two.read_text(encoding="utf-8")
    shard_one.write_text(second_entry, encoding="utf-8")
    shard_two.write_text(first_entry, encoding="utf-8")

    with pytest.raises(SystemExit, match="duration-balanced assignment"):
        sharding._check_manifests(output_dir=output_dir, shard_count=2)


@pytest.mark.stubbed
def test_manifest_check_rejects_stale_duration_totals(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    output_dir = _write_sample_shards(tmp_path=tmp_path, monkeypatch=monkeypatch)
    summary_path = output_dir / "durations.json"
    summary = json.loads(summary_path.read_text(encoding="utf-8"))
    summary["total_test_duration_seconds"] = 999.0
    summary_path.write_text(json.dumps(summary), encoding="utf-8")

    with pytest.raises(SystemExit, match="does not match the committed manifests"):
        sharding._check_manifests(output_dir=output_dir, shard_count=2)


@pytest.mark.stubbed
def test_manifest_check_rejects_stale_duration_file_inventory(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    output_dir = _write_sample_shards(tmp_path=tmp_path, monkeypatch=monkeypatch)
    summary_path = output_dir / "durations.json"
    summary = json.loads(summary_path.read_text(encoding="utf-8"))
    del summary["files"]["tests/unit/test_second.py"]
    summary_path.write_text(json.dumps(summary), encoding="utf-8")

    with pytest.raises(SystemExit, match="Behavioral test shard coverage is not exact"):
        sharding._check_manifests(output_dir=output_dir, shard_count=2)


def _write_sample_shards(
    *,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> Path:
    repository_root = tmp_path / "repository"
    tests_root = repository_root / "tests"
    unit_root = tests_root / "unit"
    unit_root.mkdir(parents=True)
    first_test = unit_root / "test_first.py"
    second_test = unit_root / "test_second.py"
    first_test.write_text("def test_first(): pass\n", encoding="utf-8")
    second_test.write_text("def test_second(): pass\n", encoding="utf-8")
    monkeypatch.setattr(sharding, "REPOSITORY_ROOT", repository_root)
    monkeypatch.setattr(sharding, "TESTS_ROOT", tests_root)

    # Pure two-file shard/profile fixture; real cutover admission is tested below.
    def selection(_root: Path) -> sharding.BehavioralSelection:
        return sharding.BehavioralSelection(
            ("tests/unit/test_first.py", "tests/unit/test_second.py"), (), (), (), "0" * 64
        )

    monkeypatch.setattr(sharding, "behavioral_selection", selection)

    durations = {
        "tests/unit/test_first.py": 10.0,
        "tests/unit/test_second.py": 1.0,
    }
    shards = sharding._balanced_shards(durations=durations, shard_count=2)
    output_dir = repository_root / "ci" / "test_shards"
    sharding._write_manifests(output_dir=output_dir, shards=shards, durations=durations)
    return output_dir


@pytest.mark.stubbed
def test_junit_profiles_use_file_medians_and_preserve_evidence(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _write_sample_shards(tmp_path=tmp_path, monkeypatch=monkeypatch)
    profiles: list[Path] = []
    for index, duration in enumerate((1, 9, 2)):
        profile = tmp_path / f"run-{index}"
        profile.mkdir()
        for name in ("first", "second"):
            (profile / f"{name}.xml").write_text(
                f'<testsuite tests="1"><testcase classname="tests.unit.test_{name}" '
                f'name="test_{name}" time="{duration}" /></testsuite>',
                encoding="utf-8",
            )
        profiles.append(profile)
    durations, evidence = sharding._profile_medians(tuple(profiles), ("run-0", "run-1", "run-2"))
    assert set(durations.values()) == {2.0}
    assert len(evidence) == 3
    assert all(len(item["junit_sha256"]) == 2 for item in evidence)
    assert evidence[0]["source"] == "run-0"


@pytest.mark.stubbed
@pytest.mark.parametrize(
    "invalid", ["duplicate", "missing", "failed", "skipped", "truncated", "nan"]
)
def test_junit_profiles_reject_incomplete_or_invalid_runs(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    invalid: str,
) -> None:
    _write_sample_shards(tmp_path=tmp_path, monkeypatch=monkeypatch)
    cases = [
        f'<testcase classname="tests.unit.test_{name}" name="test_{name}" time="1" />'
        for name in ("first", "second")
    ]
    if invalid == "duplicate":
        cases.append(cases[0])
    elif invalid == "missing":
        cases.pop()
    elif invalid in ("failed", "skipped"):
        tag = "failure" if invalid == "failed" else "skipped"
        cases[0] = cases[0].replace(" />", f"><{tag} /></testcase>")
    elif invalid == "nan":
        cases[0] = cases[0].replace('time="1"', 'time="nan"')
    declared = len(cases) + (1 if invalid == "truncated" else 0)
    report = tmp_path / "profile.xml"
    report.write_text(
        f'<testsuite tests="{declared}">{"".join(cases)}</testsuite>', encoding="utf-8"
    )
    with pytest.raises(SystemExit):
        sharding._durations_from_junit(report)


def test_quality_gate_requires_every_independent_lane_even_when_skipped(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    monkeypatch.setattr("sys.argv", ["build_test_shards.py", "--check"])
    assert sharding.main() == 0
    workflow = WORKFLOW_PATH.read_text(encoding="utf-8")
    aggregate = workflow.partition("\n  quality-fast:\n")[2].partition("\n  lint:\n")[0]
    assert "if: always()" in aggregate
    assert "needs: [lint, contract-conformance, code-quality, semantic-audit-macos]" in aggregate
    for lane in ("lint", "contract-conformance", "code-quality", "semantic-audit-macos"):
        assert f"needs.{lane}.result != 'success'" in aggregate
    assert "exit 1" in aggregate
    assert "run: npm run test:unit" in workflow
    assert "python -B -m scripts.quality_runner run --shard 2" in workflow
    assert 'shard: ["1", "3", "4"]' in workflow
    assert "needs: [quality-policy, quality-shards]" in workflow
    behavior = workflow.partition("\n  behavior-tests:\n")[2].partition("\n  coverage-gate:\n")[0]
    assert "fail-fast: false" in behavior
    matrix = behavior.partition("      matrix:\n")[2].partition("    steps:\n")[0]
    assert matrix == "        include:\n" + "".join(
        f'          - shard_id: "{shard}"\n            manifest: ci/test_shards/shard-{shard}.txt\n'
        for shard in range(1, 13)
    )
    for shard in range(1, 13):
        assert workflow.count(f"manifest: ci/test_shards/shard-{shard}.txt") == 1
    coverage = workflow.partition("\n  coverage-gate:\n")[2]
    assert "scripts/check_shard_coverage.py coverage-data --shard-count 12" in coverage
    assert "uv run --no-sync coverage report --fail-under=66.5" in coverage
    configuration = tomllib.loads((ROOT / "pyproject.toml").read_text(encoding="utf-8"))
    coverage_config = configuration["tool"]["coverage"]
    assert coverage_config["run"] == {"branch": True, "source": ["warhammer40k_core"]}
    assert coverage_config["report"] == {
        "show_missing": True,
        "skip_covered": True,
        "fail_under": 66.5,
        "precision": 2,
    }
    assert "scripts/build_test_shards.py --check --shard-count 12" in workflow

    # The cutover is immutable historical authority, independent of today's gate.
    cutover = json.loads((ROOT / sharding.CUTOVER_PATH).read_text(encoding="utf-8"))
    assert cutover["coverage"]["current_floor"] == 64
    assert len(sharding.deferred_comparison_cases(cutover)) == 260

    source = tmp_path / "coverage_boundary.py"
    source.write_text("\n".join(f"value_{line} = {line}" for line in range(1, 201)) + "\n")
    driver = tmp_path / "coverage_driver.py"
    driver.write_text(
        "import sys\n"
        "from pathlib import Path\n"
        "source = Path(sys.argv[1])\n"
        "prefix = ''.join(source.read_text().splitlines(keepends=True)[:int(sys.argv[2])])\n"
        "exec(compile(prefix, str(source), 'exec'))\n"
    )
    for covered, expected_status in ((132, 2), (133, 0)):
        data_file = tmp_path / f".coverage.{covered}"
        executed = subprocess.run(
            [
                sys.executable,
                "-m",
                "coverage",
                "run",
                "--rcfile=" + str(ROOT / "pyproject.toml"),
                "--branch",
                "--source=" + str(tmp_path),
                "--data-file=" + str(data_file),
                str(driver),
                str(source),
                str(covered),
            ],
            cwd=tmp_path,
            capture_output=True,
            text=True,
            check=False,
        )
        assert executed.returncode == 0, executed.stdout + executed.stderr
        # Exercise both config-default local reporting and CI's explicit override.
        for override in ([], ["--fail-under=66.5"]):
            result = subprocess.run(
                [
                    sys.executable,
                    "-m",
                    "coverage",
                    "report",
                    "--rcfile=" + str(ROOT / "pyproject.toml"),
                    "--data-file=" + str(data_file),
                    *override,
                    str(source),
                ],
                cwd=tmp_path,
                capture_output=True,
                text=True,
                check=False,
            )
            assert result.returncode == expected_status, result.stdout + result.stderr
            assert f"{covered / 2:.2f}%" in result.stdout


@pytest.mark.parametrize("newline", ["\n", "\r\n", "\r"])
def test_cached_function_spans_match_python_ast_with_unicode(newline: str, tmp_path: Path) -> None:
    import ast

    from tests.code_quality.source_index import ast_for, function_sources_for, source_for

    source = newline.join(
        (
            "@decorator",
            'def first(): return "é" # trailing comment',
            "",
            "def second():",
            '    """λ\fretained"""',
            '    return "好"',
            "",
        )
    )
    path = tmp_path / "source.py"
    path.write_bytes(source.encode("utf-8"))
    expected = {
        node.name: ast.get_source_segment(source_for(path), node)
        for node in ast_for(path).body
        if isinstance(node, ast.FunctionDef)
    }
    assert function_sources_for((path,)) == expected


@pytest.fixture
def cutover_root(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """Small declared source fixture for the pure selection and collection policy."""
    payload = json.loads((ROOT / sharding.CUTOVER_PATH).read_text())
    active_name = "tests/rules/test_active.py"
    inactive_name = "tests/unit/test_inactive.py"
    benchmark_name = "tests/benchmarks/test_measurement.py"
    names = [active_name, *sharding.RETAINED_ACTIVE_FILES, inactive_name, benchmark_name]
    rows: dict[str, dict[str, object]] = {}
    for name in names:
        raw = b"def test_example():\n    assert True\n"
        path = tmp_path / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(raw)
        rows[name] = {
            "mode": "100644",
            "bytes": len(raw),
            "sha256": hashlib.sha256(raw).hexdigest(),
            "blob_sha1": hashlib.sha1(
                b"blob " + str(len(raw)).encode() + b"\0" + raw, usedforsecurity=False
            ).hexdigest(),
        }
    for name in sharding.ACTIVE_TEST_ROOTS:
        (tmp_path / name).mkdir(parents=True, exist_ok=True)
    (tmp_path / "tests/code_quality").mkdir()
    payload["active_files"] = {
        name: rows[name] for name in [active_name, *sharding.RETAINED_ACTIVE_FILES]
    }
    payload["native_active_files"] = dict(payload["active_files"])
    payload["retained_active_files"] = {name: rows[name] for name in sharding.RETAINED_ACTIVE_FILES}
    payload["inactive_legacy_files"] = {inactive_name: rows[inactive_name]}
    payload["inactive_updates"] = {}
    payload["retirements"] = []
    native_retirement_pins = {
        "RETIRED_TEST_COUNT": sharding.RETIRED_TEST_COUNT,
        "RETIRED_TEST_PATHS_SHA256": sharding.RETIRED_TEST_PATHS_SHA256,
        "RETIRED_TEST_ROWS_SHA256": sharding.RETIRED_TEST_ROWS_SHA256,
    }
    (tmp_path / "original-retirement-pins.json").write_text(json.dumps(native_retirement_pins))
    monkeypatch.setattr(sharding, "RETIRED_TEST_COUNT", 0)
    monkeypatch.setattr(sharding, "RETIRED_TEST_PATHS_SHA256", hashlib.sha256(b"[]").hexdigest())
    monkeypatch.setattr(sharding, "RETIRED_TEST_ROWS_SHA256", hashlib.sha256(b"{}").hexdigest())
    payload["benchmark_files"] = {benchmark_name: rows[benchmark_name]}
    # The pure policy fixture has its own pinned six-file source authority;
    # repository-native 5734 authentication remains independently verified.
    (tmp_path / "original-cutover-pin.txt").write_text(sharding.CUTOVER_LEDGER_SHA256)
    fields = (
        "source_base",
        "active_roots",
        "native_active_files",
        "retained_active_files",
        "inactive_legacy_files",
        "benchmark_files",
    )
    fixture_ledger = {name: payload[name] for name in fields}
    fixture_pin = hashlib.sha256(
        json.dumps(fixture_ledger, sort_keys=True, separators=(",", ":")).encode()
    ).hexdigest()
    monkeypatch.setattr(sharding, "CUTOVER_LEDGER_SHA256", fixture_pin)
    target = tmp_path / sharding.CUTOVER_PATH
    target.parent.mkdir(parents=True)
    target.write_text(json.dumps(payload))
    return tmp_path


@pytest.mark.stubbed
def test_cutover_exact_inventory_and_explicit_inactive_rejection(cutover_root: Path) -> None:
    selection = sharding.behavioral_selection(cutover_root)
    assert selection.active_files == tuple(
        sorted(("tests/rules/test_active.py", *sharding.RETAINED_ACTIVE_FILES))
    )
    assert selection.inactive_files == ("tests/unit/test_inactive.py",)
    assert selection.benchmark_files == ("tests/benchmarks/test_measurement.py",)
    selection.check_explicit(cutover_root, ("tests/rules/test_active.py::test_example",))
    with pytest.raises(SystemExit, match="Explicit inactive legacy test"):
        selection.check_explicit(cutover_root, ("tests/unit/test_inactive.py::test_example",))
    with pytest.raises(SystemExit, match="parent aliases"):
        selection.check_explicit(cutover_root, ("tests/rules/../unit/test_dice.py",))


@pytest.mark.stubbed
@pytest.mark.parametrize(
    "mutation",
    [
        "missing_active",
        "changed_active",
        "unknown_active",
        "unknown_legacy",
        "active_suffix",
        "legacy_suffix",
        "status_overlap",
        "wrong_source",
        "wrong_roots",
        "wrong_coverage",
        "extra_field",
        "undeclared_retirement",
        "path_alias",
    ],
)
def test_cutover_rejects_incomplete_malformed_and_changed_members(
    cutover_root: Path, mutation: str
) -> None:
    target = cutover_root / sharding.CUTOVER_PATH
    payload = json.loads(target.read_text())
    active = cutover_root / "tests/rules/test_active.py"
    if mutation == "missing_active":
        active.unlink()
    elif mutation == "changed_active":
        active.write_text("def test_changed():\n    assert False\n")
    elif mutation in {"unknown_active", "unknown_legacy"}:
        parent = "tests/rules" if mutation == "unknown_active" else "tests/unit"
        (cutover_root / parent / "test_undeclared.py").write_text("def test_new(): pass\n")
    elif mutation in {"active_suffix", "legacy_suffix"}:
        parent = "tests/rules" if mutation == "active_suffix" else "tests/unit"
        (cutover_root / parent / "extra_test.py").write_text("def test_new(): pass\n")
    elif mutation == "status_overlap":
        payload["inactive_legacy_files"]["tests/unit/test_dice.py"] = payload["active_files"][
            "tests/unit/test_dice.py"
        ]
    elif mutation == "wrong_source":
        payload["source_base"]["commit"] = "0" * 40
    elif mutation == "wrong_roots":
        payload["active_roots"] = ["tests/unit"]
    elif mutation == "wrong_coverage":
        payload["coverage"]["current_floor"] = 49
    elif mutation == "extra_field":
        payload["unreviewed"] = True
    elif mutation == "undeclared_retirement":
        payload["retirements"] = ["tests/unit/test_inactive.py"]
    elif mutation == "path_alias":
        payload["active_files"]["tests/rules/../rules/test_active.py"] = payload[
            "active_files"
        ].pop("tests/rules/test_active.py")
    else:
        raise AssertionError("Unknown cutover mutation")
    target.write_text(json.dumps(payload))
    with pytest.raises(SystemExit):
        sharding.behavioral_selection(cutover_root)


@pytest.mark.stubbed
def test_cutover_rejects_duplicate_json_keys(cutover_root: Path) -> None:
    target = cutover_root / sharding.CUTOVER_PATH
    raw = target.read_text()
    target.write_text('{"schema":"wrong",' + raw[1:])
    with pytest.raises(SystemExit, match="Duplicate cutover field"):
        sharding.behavioral_selection(cutover_root)


@pytest.mark.stubbed
@pytest.mark.parametrize("explicit", ["tests/unit/test_inactive.py", "tests/rules/test_active.py"])
def test_cutover_real_pytest_cli_does_not_bypass_explicit_file_guard(
    cutover_root: Path, explicit: str
) -> None:
    for name in (
        "scripts/__init__.py",
        "scripts/build_test_shards.py",
        "tests/conftest.py",
        "tests/timing_plugin.py",
        "tests/__init__.py",
    ):
        target = cutover_root / name
        target.parent.mkdir(parents=True, exist_ok=True)
        raw = (ROOT / name).read_text()
        if name == "scripts/build_test_shards.py":
            native_pin = (cutover_root / "original-cutover-pin.txt").read_text()
            before = 'CUTOVER_LEDGER_SHA256 = "' + native_pin + '"'
            after = 'CUTOVER_LEDGER_SHA256 = "' + sharding.CUTOVER_LEDGER_SHA256 + '"'
            assert raw.count(before) == 1
            raw = raw.replace(before, after, 1)
            native_pins = json.loads((cutover_root / "original-retirement-pins.json").read_text())
            for key in (
                "RETIRED_TEST_COUNT",
                "RETIRED_TEST_PATHS_SHA256",
                "RETIRED_TEST_ROWS_SHA256",
            ):
                old_pin = key + " = " + json.dumps(native_pins[key])
                new_pin = key + " = " + json.dumps(getattr(sharding, key))
                assert raw.count(old_pin) == 1
                raw = raw.replace(old_pin, new_pin, 1)
        target.write_text(raw)
    (cutover_root / "pyproject.toml").write_text(
        '[tool.pytest.ini_options]\npython_files = ["test_*.py"]\n'
    )
    result = subprocess.run(
        [sys.executable, "-B", "-m", "pytest", "--collect-only", "-q", explicit],
        cwd=cutover_root,
        env=_collection_environment(cutover_root),
        capture_output=True,
        text=True,
        timeout=30,
    )
    if explicit.startswith("tests/unit/"):
        assert result.returncode == 4
        assert "Explicit inactive legacy test is quarantined" in result.stderr
    else:
        assert result.returncode == 0, result.stdout + result.stderr
        assert "test_example" in result.stdout


@pytest.mark.stubbed
def test_cutover_real_cli_rejects_naming_override(cutover_root: Path) -> None:
    for name in (
        "scripts/__init__.py",
        "scripts/build_test_shards.py",
        "tests/conftest.py",
        "tests/timing_plugin.py",
        "tests/__init__.py",
    ):
        target = cutover_root / name
        target.parent.mkdir(parents=True, exist_ok=True)
        raw = (ROOT / name).read_text()
        if name == "scripts/build_test_shards.py":
            native_pin = (cutover_root / "original-cutover-pin.txt").read_text()
            before = 'CUTOVER_LEDGER_SHA256 = "' + native_pin + '"'
            after = 'CUTOVER_LEDGER_SHA256 = "' + sharding.CUTOVER_LEDGER_SHA256 + '"'
            assert raw.count(before) == 1
            raw = raw.replace(before, after, 1)
            native_pins = json.loads((cutover_root / "original-retirement-pins.json").read_text())
            for key in (
                "RETIRED_TEST_COUNT",
                "RETIRED_TEST_PATHS_SHA256",
                "RETIRED_TEST_ROWS_SHA256",
            ):
                old_pin = key + " = " + json.dumps(native_pins[key])
                new_pin = key + " = " + json.dumps(getattr(sharding, key))
                assert raw.count(old_pin) == 1
                raw = raw.replace(old_pin, new_pin, 1)
        target.write_text(raw)
    (cutover_root / "pyproject.toml").write_text(
        '[tool.pytest.ini_options]\npython_files = ["test_*.py"]\n'
    )
    result = subprocess.run(
        [
            sys.executable,
            "-B",
            "-m",
            "pytest",
            "--collect-only",
            "-q",
            "tests/rules/test_active.py",
            "-o",
            "python_files=*_test.py",
        ],
        cwd=cutover_root,
        env=_collection_environment(cutover_root),
        capture_output=True,
        text=True,
        timeout=30,
    )
    assert result.returncode == 4
    assert "Effective pytest python_files" in result.stderr


def _collection_environment(root: Path) -> dict[str, str]:
    environment = dict(os.environ)
    environment["PYTHONPATH"] = os.pathsep.join((str(root), str(root / "src")))
    environment["PYTHONDONTWRITEBYTECODE"] = "1"
    plugins = environment.get("PYTEST_PLUGINS", "").split(",")
    plugins = [name for name in plugins if name.strip() and name.strip() != "source_observer"]
    if plugins:
        environment["PYTEST_PLUGINS"] = ",".join(plugins)
    else:
        environment.pop("PYTEST_PLUGINS", None)
    environment.pop("TEST_TIMING_DIR", None)
    return environment


def test_finite_partition_has_real_complete_pytest_collection(
    pytestconfig: pytest.Config, monkeypatch: pytest.MonkeyPatch
) -> None:
    expected = sharding._literal_partition_nodes(ROOT)
    result = subprocess.run(
        [
            sys.executable,
            "-B",
            "-m",
            "pytest",
            sharding.CASE_PARTITION_FILE,
            "--collect-only",
            "-q",
            "-n0",
            "--no-cov",
            "--color=no",
        ],
        cwd=ROOT,
        env=_collection_environment(ROOT),
        capture_output=True,
        text=True,
        timeout=60,
    )
    assert result.returncode == 0, result.stdout + result.stderr
    observed = tuple(
        line.strip()
        for line in result.stdout.splitlines()
        if line.startswith(sharding.CASE_PARTITION_FILE + "::")
    )
    assert len(observed) == len(set(observed)) == 20
    assert observed == expected
    assert (
        tuple(sharding._case_partition(ROOT, frozenset(sharding._behavioral_test_files())))
        == expected
    )

    # The actual failed 335-item layout queued both expensive cases on worker 1.
    # Retain this and the four-heavy case without adding or selecting test cases.
    for count, positions in ((335, (128, 129)), (398, (244, 245)), (248, (70, 71, 72, 73))):
        nodes = [f"ordinary:{index}" for index in range(count)]
        for position, node in zip(positions, expected, strict=False):
            nodes[position] = node
        ordered = sharding.worksteal_relevance_order(tuple(nodes), workers=4)
        assert sorted(ordered) == list(range(count))
        assert [index for index in ordered if index in positions] == list(positions)
        assert [index for index in ordered if index not in positions] == [
            index for index in range(count) if index not in positions
        ]
        start = 0
        for worker in range(4):
            width = (count - start) // (4 - worker)
            chunk = ordered[start : start + width]
            assert len(set(chunk) & set(positions)) <= 1
            if worker < len(positions):
                assert chunk[0] == positions[worker]
            start += width
        assert start == count
        assert sharding.worksteal_relevance_order(tuple(nodes), workers=1) == tuple(range(count))
    assert sharding.worksteal_relevance_order(
        tuple("ordinary" for _ in range(8)), workers=4
    ) == tuple(range(8))
    assert sharding.worksteal_relevance_order(expected, workers=4) == tuple(range(20))
    assert sharding.worksteal_relevance_order(expected[:2], workers=4) == (0, 1)

    # Exercise the real controller hook with xdist's actual worker reset value.

    from tests import conftest as root_hooks

    worker_input: dict[str, object] = {}

    class Controller:
        def __init__(self, config: pytest.Config, workerinput: dict[str, object]) -> None:
            self.config = config
            self.workerinput = workerinput

    controller = Controller(pytestconfig, worker_input)
    with monkeypatch.context() as patch:
        patch.setattr(pytestconfig.option, "dist", "worksteal")
        root_hooks.pytest_configure_node(controller)
        assert worker_input["s25_scheduler"] == "worksteal"
        patch.setattr(pytestconfig.option, "dist", "no")
        patch.setattr(pytestconfig, "workerinput", worker_input, raising=False)
        patch.setenv("SHARD_ID", "controller-handoff-control")
        patch.setenv("PYTEST_XDIST_WORKER_COUNT", "4")
        names = tuple(f"ordinary:{index}" for index in range(6)) + expected[:2]
        items = [cast(pytest.Item, SimpleNamespace(nodeid=name)) for name in names]
        original = tuple(items)
        root_hooks.pytest_collection_modifyitems(pytestconfig, items)
        assert items[0] is original[6]
        assert items[2] is original[7]
        assert {id(item) for item in items} == {id(item) for item in original}
        worker_input["s25_scheduler"] = "load"
        items[:] = original
        root_hooks.pytest_collection_modifyitems(pytestconfig, items)
        assert tuple(items) == original


@pytest.fixture
def partition_root(tmp_path: Path) -> Path:
    for name in (sharding.CASE_PARTITION_FILE, sharding.CASE_PARTITION_PATH):
        target = tmp_path / name
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes((ROOT / name).read_bytes())
    return tmp_path


@pytest.mark.parametrize(
    "mutation", ["drop", "extra", "duplicate", "reorder", "source", "body", "weight", "field"]
)
def test_finite_partition_rejects_missing_extra_and_malformed_cases(
    partition_root: Path, mutation: str
) -> None:
    target = partition_root / sharding.CASE_PARTITION_PATH
    value = json.loads(target.read_text())
    if mutation == "drop":
        value["nodes"].pop()
    elif mutation == "extra":
        value["nodes"].append(sharding.CASE_PARTITION_FILE + "::invented")
    elif mutation == "duplicate":
        value["nodes"][1] = value["nodes"][0]
    elif mutation == "reorder":
        value["nodes"].reverse()
    elif mutation == "source":
        value["source_sha256"] = "0" * 64
    elif mutation == "body":
        with (partition_root / sharding.CASE_PARTITION_FILE).open("a") as stream:
            stream.write("\n# undeclared source change\n")
    elif mutation == "weight":
        value["weights"][value["nodes"][0]] = float("nan")
    elif mutation == "field":
        value["unreviewed"] = True
    else:
        raise AssertionError("Unknown partition mutation")
    target.write_text(json.dumps(value))
    with pytest.raises(SystemExit):
        sharding._case_partition(partition_root, frozenset({sharding.CASE_PARTITION_FILE}))


def test_finite_partition_preserves_total_weight_and_other_file_weights() -> None:
    durations = {sharding.CASE_PARTITION_FILE: 200.0, "tests/example.py": 37.0}
    expanded = sharding._partitioned_durations(durations)
    assert durations == {sharding.CASE_PARTITION_FILE: 200.0, "tests/example.py": 37.0}
    assert expanded["tests/example.py"] == 37.0
    assert sharding.CASE_PARTITION_FILE not in expanded
    assert len(expanded) == 21
    approx = cast(Callable[[float], object], vars(pytest)["approx"])
    assert sum(expanded.values()) == approx(237.0)


@pytest.fixture
def retired_cutover_root(cutover_root: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    name = "tests/unit/test_inactive.py"
    target = cutover_root / sharding.CUTOVER_PATH
    value = json.loads(target.read_text())
    native = value["inactive_legacy_files"][name]
    # Match the real retirement contract: retired legacy plus remaining live inactive.
    remaining = "tests/unit/test_remaining.py"
    (cutover_root / remaining).write_bytes((cutover_root / name).read_bytes())
    value["inactive_legacy_files"][remaining] = dict(native)
    fields = (
        "source_base",
        "active_roots",
        "native_active_files",
        "retained_active_files",
        "inactive_legacy_files",
        "benchmark_files",
    )
    ledger = {key: value[key] for key in fields}
    monkeypatch.setattr(
        sharding,
        "CUTOVER_LEDGER_SHA256",
        hashlib.sha256(
            json.dumps(ledger, sort_keys=True, separators=(",", ":")).encode()
        ).hexdigest(),
    )
    archive = "data/source_audits/ci64_provenance_v1/retired-tests/" + name + ".txt"
    path = cutover_root / archive
    path.parent.mkdir(parents=True)
    path.write_bytes((cutover_root / name).read_bytes())
    (cutover_root / name).unlink()
    value["retirements"] = [{"path": name, "archive": archive, "native": native}]
    target.write_text(json.dumps(value))
    monkeypatch.setattr(sharding, "RETIRED_TEST_COUNT", 1)
    monkeypatch.setattr(
        sharding,
        "RETIRED_TEST_PATHS_SHA256",
        hashlib.sha256(json.dumps([name], separators=(",", ":")).encode()).hexdigest(),
    )
    monkeypatch.setattr(
        sharding,
        "RETIRED_TEST_ROWS_SHA256",
        hashlib.sha256(
            json.dumps({name: native}, sort_keys=True, separators=(",", ":")).encode()
        ).hexdigest(),
    )
    return cutover_root


@pytest.mark.stubbed
def test_retired_selection_keeps_current_cases_and_quarantine(retired_cutover_root: Path) -> None:
    selected = sharding.behavioral_selection(retired_cutover_root)
    assert selected.inactive_files == (
        "tests/unit/test_inactive.py",
        "tests/unit/test_remaining.py",
    )
    assert len(selected.active_files) == 3
    assert not (retired_cutover_root / "tests/unit/test_inactive.py").exists()
    with pytest.raises(SystemExit, match="Explicit inactive legacy test"):
        selected.check_explicit(retired_cutover_root, ("tests/unit/test_inactive.py",))


@pytest.mark.stubbed
@pytest.mark.parametrize(
    "mutation",
    [
        "reappear",
        "broken_symlink",
        "archive_hardlink",
        "archive_changed",
        "archive_missing",
        "native_drift",
        "archive_alias",
        "extra_row",
    ],
)
def test_retired_selection_rejects_reappearance_and_archive_drift(
    retired_cutover_root: Path, mutation: str
) -> None:
    target = retired_cutover_root / sharding.CUTOVER_PATH
    value = json.loads(target.read_text())
    row = value["retirements"][0]
    original = retired_cutover_root / row["path"]
    archive = retired_cutover_root / row["archive"]
    if mutation == "reappear":
        original.write_bytes(archive.read_bytes())
    elif mutation == "broken_symlink":
        original.symlink_to(retired_cutover_root / "missing-target")
    elif mutation == "archive_hardlink":
        os.link(archive, archive.with_suffix(".hardlink"))
    elif mutation == "archive_changed":
        archive.write_bytes(b"changed archive")
    elif mutation == "archive_missing":
        archive.unlink()
    elif mutation == "native_drift":
        row["native"] = dict(row["native"], sha256="0" * 64)
    elif mutation == "archive_alias":
        row["archive"] = row["archive"].replace(
            "/retired-tests/", "/retired-tests/../retired-tests/"
        )
    elif mutation == "extra_row":
        value["retirements"].append(row)
    else:
        raise AssertionError("Unknown retirement mutation")
    target.write_text(json.dumps(value))
    with pytest.raises(SystemExit):
        sharding.behavioral_selection(retired_cutover_root)


@pytest.mark.parametrize(
    "invalid",
    [None, "schema", "index", "key", "exit", "boolean", "extra", "missing", "array", "json"],
)
def test_source_index_completion_is_bound_to_successful_current_construction(
    tmp_path: Path, invalid: str | None
) -> None:
    import time

    from scripts.ci_source_index import SCHEMA, BuildGate

    index = tmp_path / "index"
    result = tmp_path / "completion.json"
    key = "selected-source-index-v1-" + "a" * 64
    payload: dict[str, object] = {
        "schema": SCHEMA,
        "index": str(index.resolve()),
        "input_key": key,
        "exit_code": 0,
    }
    if invalid == "schema":
        payload["schema"] = "old"
    elif invalid == "index":
        payload["index"] = str(tmp_path / "other")
    elif invalid == "key":
        payload["input_key"] = "selected-source-index-v1-" + "b" * 64
    elif invalid == "exit":
        payload["exit_code"] = 7
    elif invalid == "boolean":
        payload["exit_code"] = False
    elif invalid == "extra":
        payload["unexpected"] = True
    elif invalid == "missing":
        del payload["exit_code"]
    encoded = "[]" if invalid == "array" else json.dumps(payload)
    result.write_text("{" if invalid == "json" else encoded, encoding="utf-8")
    gate = BuildGate(result, index, key, time.time() + 30)
    if invalid is None:
        gate.wait()
    else:
        with pytest.raises(pytest.UsageError):
            gate.wait()


def test_source_index_gate_rejects_missing_completion_and_expired_deadline(tmp_path: Path) -> None:
    import time

    from scripts.ci_source_index import BuildGate

    gate = BuildGate(
        tmp_path / "missing.json",
        tmp_path / "index",
        "selected-source-index-v1-" + "a" * 64,
        time.time() - 1,
    )
    with pytest.raises(pytest.UsageError, match="did not complete"):
        gate.wait()
    with pytest.raises(pytest.UsageError, match="finite"):
        BuildGate(gate.result, gate.index, gate.input_key, float("nan")).wait()


@pytest.mark.parametrize("workers", [0, 2])
def test_failed_real_source_builder_stops_pytest_before_dispatch(
    tmp_path: Path, workers: int
) -> None:
    import time

    # This is a real public-builder failure and real pytest dispatch, not an engine stub.
    result = tmp_path / "completion.json"
    index = tmp_path / "index"
    key = "selected-source-index-v1-" + "a" * 64
    environment = _collection_environment(ROOT)
    environment.pop("PYTHONPATH", None)
    environment["GITHUB_OUTPUT"] = str(tmp_path / "github-output")
    built = subprocess.run(
        [
            sys.executable,
            "-B",
            "-m",
            "scripts.ci_source_index",
            str(tmp_path / "missing-sources"),
            str(index),
            str(result),
            key,
        ],
        cwd=ROOT,
        env=environment,
        capture_output=True,
        text=True,
        check=False,
        timeout=30,
    )
    assert built.returncode != 0
    assert json.loads(result.read_text(encoding="utf-8"))["exit_code"] != 0
    assert not (tmp_path / "github-output").exists()
    probe = tmp_path / "test_probe.py"
    ran = tmp_path / "ran"
    probe.write_text(
        "from pathlib import Path\ndef test_probe():\n"
        f"    Path({str(ran)!r}).write_text('must not run')\n",
        encoding="utf-8",
    )
    config = tmp_path / "pytest.ini"
    config.write_text("[pytest]\n", encoding="utf-8")
    stopped = subprocess.run(
        [
            sys.executable,
            "-m",
            "pytest",
            "-c",
            str(config),
            str(probe),
            "-p",
            "scripts.ci_source_index",
            "-n",
            str(workers),
            "--dist=worksteal",
            "--ci-source-index-result",
            str(result),
            "--ci-source-index-target",
            str(index),
            "--ci-source-index-key",
            key,
            "--ci-source-index-deadline",
            str(time.time() + 30),
        ],
        cwd=ROOT,
        env=environment,
        capture_output=True,
        text=True,
        check=False,
        timeout=40,
    )
    assert stopped.returncode != 0
    assert "Source-index construction failed" in stopped.stdout + stopped.stderr
    assert not ran.exists()


def test_cold_source_index_overlaps_startup_inside_the_unchanged_deadline() -> None:
    workflow = WORKFLOW_PATH.read_text(encoding="utf-8")
    restore = workflow.split("- name: Restore exact selected-source index", 1)[1].split(
        "- name: Run behavioral coverage shard", 1
    )[0]
    assert "if: ${{ matrix.shard_id != '1' }}" in restore
    step = workflow.split("- name: Run behavioral coverage shard", 1)[1].split(
        "- name: Save completed selected-source index", 1
    )[0]
    assert "timeout-minutes: 14" in step
    assert "source_index_deadline=$(( $(date +%s) + 14 * 60 ))" in step
    assert step.index("scripts.validate_source_history") < step.index("scripts.ci_source_index")
    assert '"$SELECTED_INDEX_INPUT_KEY" &' in step
    assert "completion_dir=$(mktemp -d " in step
    assert step.count('"${source_index_args[@]}"') == 2
    assert step.index("source_index_pid=$!") < step.index("uv run --no-sync python -m pytest")
    assert "finish_source_index_build" in step
    assert "coverage report --fail-under=66.5" in workflow
