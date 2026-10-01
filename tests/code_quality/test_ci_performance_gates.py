# pyright: reportPrivateUsage=false

from __future__ import annotations

import json
import xml.etree.ElementTree as ET
from pathlib import Path

import pytest
import scripts.build_test_shards as sharding
from scripts.check_shard_coverage import check_shard_coverage

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

    durations = {
        "tests/unit/test_first.py": 10.0,
        "tests/unit/test_second.py": 1.0,
    }
    shards = sharding._balanced_shards(durations=durations, shard_count=2)
    output_dir = repository_root / "ci" / "test_shards"
    sharding._write_manifests(output_dir=output_dir, shards=shards, durations=durations)
    return output_dir


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
    assert workflow.count("pytest tests/code_quality -q -n auto --dist=worksteal --no-cov") == 1
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
    assert "uv run --no-sync coverage report --fail-under=85" in coverage
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
