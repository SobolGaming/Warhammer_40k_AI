from __future__ import annotations

import json
import os
import signal
import subprocess
import sys
import time
import xml.etree.ElementTree as ET
from pathlib import Path

import pytest
from scripts.behavioral_deadline import approved, supervise, termination_due
from scripts.check_shard_coverage import check_shard_coverage


@pytest.mark.parametrize(
    ("elapsed", "passes", "terminate"),
    [
        (1079.999, True, False),
        (1080.0, True, False),
        (1080.001, False, False),
        (1799.999, False, False),
        (1800.0, False, False),
        (1800.001, False, True),
    ],
)
def test_approval_and_execution_boundaries_are_independent(
    elapsed: float, passes: bool, terminate: bool
) -> None:
    assert approved(elapsed, exit_code=0, terminated=False, approval_seconds=1080) is passes
    assert termination_due(elapsed, running=True, execution_seconds=1800) is terminate
    assert not termination_due(elapsed, running=False, execution_seconds=1800)
    assert not approved(elapsed, exit_code=1, terminated=False, approval_seconds=1080)
    assert not approved(elapsed, exit_code=0, terminated=True, approval_seconds=1080)


@pytest.mark.skipif(os.name != "posix", reason="Hosted supervisor owns POSIX process groups.")
def test_late_passing_pytest_keeps_complete_reports_and_coverage_but_fails_approval(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("PYTEST_DISABLE_PLUGIN_AUTOLOAD", "1")
    monkeypatch.delenv("PYTEST_ADDOPTS", raising=False)
    coverage = tmp_path / ".coverage.1"
    monkeypatch.setenv("COVERAGE_FILE", str(coverage))
    (tmp_path / "pytest.ini").write_text("[pytest]\n")
    (tmp_path / "subject.py").write_text("def answer():\n    return 42\n")
    (tmp_path / "test_slow.py").write_text(
        "import time\nfrom subject import answer\n"
        "def test_deliberately_slow_pass():\n"
        "    time.sleep(0.25)\n    assert answer() == 42\n"
    )
    reports = tmp_path / "reports"
    result = supervise(
        [
            sys.executable,
            "-m",
            "pytest",
            "-c",
            "pytest.ini",
            "-p",
            "pytest_cov.plugin",
            "test_slow.py",
            "--cov=subject",
            "--cov-report=",
            "--junitxml=reports/complete.xml",
        ],
        report_dir=reports,
        approval_seconds=0.05,
        execution_seconds=20,
    )
    receipt = json.loads((reports / "covered-shard-status.json").read_text())
    assert result == 1
    assert receipt["workload_exit_code"] == 0
    assert receipt["reason"] == "approval_limit_exceeded"
    assert receipt["terminated"] is False
    assert 0.25 < receipt["elapsed_seconds"] < 20
    suite = ET.parse(reports / "complete.xml").getroot().find("testsuite")
    assert suite is not None
    assert suite.attrib["tests"] == "1"
    assert suite.attrib["failures"] == suite.attrib["errors"] == "0"
    assert coverage.is_file()
    assert coverage.stat().st_size > 0
    assert "1 passed" in (reports / "covered-shard.log").read_text()


@pytest.mark.skipif(
    sys.platform != "linux", reason="Checks actual descendant state through procfs."
)
@pytest.mark.parametrize("mode", ["timeout", "failure", "orphan"])
def test_execution_timeout_stops_descendants_and_preserves_only_available_partial_results(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, mode: str
) -> None:
    monkeypatch.chdir(tmp_path)
    coverage = tmp_path / ".coverage.1"
    monkeypatch.setenv("COVERAGE_FILE", str(coverage))
    reports = tmp_path / "reports"
    reports.mkdir()
    (tmp_path / "subject.py").write_text("value = 42\n")
    child = tmp_path / "unfinished.py"
    child.write_text(
        "import coverage, pathlib, signal, subprocess, sys, time\n"
        "cov=coverage.Coverage(data_file='.coverage.1.worker')\n"
        "cov.start()\nimport subject\ncov.stop()\ncov.save()\n"
        "pathlib.Path('reports/partial.xml').write_text('<testsuite>')\n"
        "pathlib.Path('reports/gw0.progress.jsonl').write_text('started'+chr(10))\n"
        + ("sys.exit(7)\n" if mode == "failure" else "")
        + "descendant=subprocess.Popen([sys.executable, '-c', "
        "'import signal,time; signal.signal(signal.SIGTERM,signal.SIG_IGN); time.sleep(60)'])\n"
        "pathlib.Path('descendant.pid').write_text(str(descendant.pid))\n"
        "signal.signal(signal.SIGTERM,signal.SIG_IGN)\n"
        "print('partial work remains',flush=True)\n"
        + ("sys.exit(0)\n" if mode == "orphan" else "")
        + "while True: time.sleep(0.05)\n"
    )
    assert (
        supervise(
            [sys.executable, str(child)],
            report_dir=reports,
            approval_seconds=0.05,
            execution_seconds=2,
            termination_grace=0.1,
        )
        == 1
    )
    receipt = json.loads((reports / "covered-shard-status.json").read_text())
    if mode == "orphan":
        assert receipt["reason"] in {"descendants_remained", "cleanup_failed"}
        assert not receipt["approved"]
    else:
        assert receipt["reason"] == (
            "execution_limit_exceeded" if mode == "timeout" else "workload_failed"
        )
    assert receipt["terminated"] is (mode == "timeout")
    if mode == "timeout":
        assert receipt["termination_elapsed_seconds"] > 2
    else:
        assert receipt["termination_elapsed_seconds"] is None
        assert receipt["workload_exit_code"] == (0 if mode == "orphan" else 7)
    assert (reports / "gw0.progress.jsonl").read_text() == "started\n"
    assert (reports / "partial.xml").read_text() == "<testsuite>"
    assert not coverage.exists()
    assert (reports / "partial-coverage/.coverage.1.worker").read_bytes() == (
        tmp_path / ".coverage.1.worker"
    ).read_bytes()
    with pytest.raises(SystemExit, match="inventory"):
        check_shard_coverage(reports / "partial-coverage", shard_count=1)
    if mode != "failure":
        pid = int((tmp_path / "descendant.pid").read_text())
        state = Path(f"/proc/{pid}/stat")
        assert not state.exists() or state.read_text().split()[2] == "Z"
    else:
        assert not (tmp_path / "descendant.pid").exists()


def test_successful_short_workload_is_approved(tmp_path: Path) -> None:
    assert (
        supervise(
            [sys.executable, "-c", "print('completed')"],
            report_dir=tmp_path,
            approval_seconds=10,
            execution_seconds=20,
        )
        == 0
    )
    receipt = json.loads((tmp_path / "covered-shard-status.json").read_text())
    assert receipt["approved"]
    assert receipt["reason"] == "passed"
    assert receipt["workload_exit_code"] == 0


def test_hosted_workload_uses_supervisor_and_preserves_diagnostics() -> None:
    root = Path(__file__).resolve().parents[2]
    workflow = (root / ".github/workflows/ci.yml").read_text()
    step = workflow.split("- name: Run behavioral coverage shard", 1)[1].split(
        "- name: Save completed selected-source index", 1
    )[0]
    assert "timeout-minutes: 32" in step
    assert "scripts.behavioral_deadline" in step
    assert "--approval-seconds 1080 --execution-seconds 1800" in step
    assert "-- bash scripts/run_behavioral_coverage.sh" in step
    upload = workflow.split("- name: Upload shard test report", 1)[1].split(
        "- name: Upload shard coverage", 1
    )[0]
    assert "if: always()" in upload
    assert "include-hidden-files: true" in upload
    gate = workflow.split("  coverage-gate:", 1)[1]
    assert "if: needs.behavior-tests.result != 'success'" in gate
    assert "coverage report --fail-under=67" in gate
    workload = (root / "scripts/run_behavioral_coverage.sh").read_text()
    assert "BEHAVIOR_EXECUTION_DEADLINE" in workload
    assert workload.index("scripts.validate_source_history") < workload.index(
        "scripts.ci_source_index"
    )
    assert workload.count("--cov=warhammer40k_core") == 2
    assert "-n 1" in workload
    assert "-n auto" in workload


def test_source_index_barrier_consumes_the_shared_monotonic_deadline(tmp_path: Path) -> None:
    from scripts.ci_source_index import SCHEMA, BuildGate

    result = tmp_path / "completion.json"
    index = tmp_path / "index"
    key = "selected-source-index-v1-" + "a" * 64
    result.write_text(
        json.dumps(
            {"schema": SCHEMA, "index": str(index.resolve()), "input_key": key, "exit_code": 0}
        )
    )
    BuildGate(result, index, key, time.monotonic() + 10, monotonic=True).wait()
    with pytest.raises(pytest.UsageError, match="exceeded"):
        BuildGate(result, index, key, time.monotonic() - 1, monotonic=True).wait()
    root = Path(__file__).resolve().parents[2]
    workload = (root / "scripts/run_behavioral_coverage.sh").read_text()
    assert "--ci-source-index-monotonic" in workload


def test_cancellation_after_workload_exit_fails_approval(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from scripts import behavioral_deadline

    original_cleanup = behavioral_deadline.cleanup

    def cancel_after_cleanup(
        process: subprocess.Popen[bytes] | subprocess.Popen[str],
        *,
        grace: float,
        kill_grace: float,
    ) -> bool:
        descendants = original_cleanup(process, grace=grace, kill_grace=kill_grace)
        os.kill(os.getpid(), signal.SIGTERM)
        return descendants

    monkeypatch.setattr(behavioral_deadline, "cleanup", cancel_after_cleanup)
    assert (
        supervise(
            [sys.executable, "-c", "print(42)"],
            report_dir=tmp_path,
            approval_seconds=10,
            execution_seconds=20,
        )
        == 1
    )
    receipt = json.loads((tmp_path / "covered-shard-status.json").read_text())
    assert receipt["workload_exit_code"] == 0
    assert receipt["terminated"] is False
    assert receipt["interrupt_signal"] == signal.SIGTERM
    assert receipt["reason"] == "interrupted"
    assert receipt["approved"] is False
