# pyright: reportPrivateUsage=false

from __future__ import annotations

import hashlib
import json
import os
import subprocess
import sys
import tomllib
import xml.etree.ElementTree as ET
from pathlib import Path

import pytest
import scripts.build_test_shards as sharding
from scripts.check_shard_coverage import check_shard_coverage
from tools import quality_runtime_successor as ci54

ROOT = Path(__file__).resolve().parents[2]
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
    monkeypatch.setattr(
        sharding,
        "behavioral_selection",
        lambda _root: sharding.BehavioralSelection(
            ("tests/unit/test_first.py", "tests/unit/test_second.py"), (), (), (), "0" * 64
        ),
    )

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
    historical = ci54.previous(ROOT, ".github/workflows/ci.yml", workflow.encode()).decode()
    assert historical.count("pytest tests/code_quality -q -n auto --dist=worksteal --no-cov") == 1
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
    assert "uv run --no-sync coverage report --fail-under=50" in coverage
    configuration = tomllib.loads((ROOT / "pyproject.toml").read_text(encoding="utf-8"))
    coverage_config = configuration["tool"]["coverage"]
    assert coverage_config["run"] == {"branch": True, "source": ["warhammer40k_core"]}
    assert coverage_config["report"] == {
        "show_missing": True,
        "skip_covered": True,
        "fail_under": 50,
    }
    assert "scripts/build_test_shards.py --check --shard-count 12" in workflow


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


def test_finite_partition_has_real_complete_pytest_collection() -> None:
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
    assert sum(expanded.values()) == pytest.approx(237.0)
