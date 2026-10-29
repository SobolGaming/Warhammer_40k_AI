"""Bounded real pytest/OS controls for the production reporter and process supervisor."""

from __future__ import annotations

import json
import os
import signal
import sys
import threading
import time
from pathlib import Path

from scripts import quality_evidence as evidence
from scripts import quality_runner as runner

ROOT = Path(__file__).resolve().parents[2]
NORMAL = """import pytest
@pytest.mark.parametrize('number', range(12))
def test_sample(number):
    assert number >= 0
"""
NODES = [f"test_probe.py::test_sample[{number}]" for number in range(12)]


def transport(
    directory: Path,
    source: str,
    nodes: list[str],
    *,
    restart: int = 0,
    extra: tuple[str, ...] = (),
    collect: bool = True,
    deadlines: runner.Deadlines = runner.DEFAULT_DEADLINES,
) -> tuple[int, int, Path]:
    """Use the real CLI and hooks; no embedded pytest or manufactured reports."""
    directory.mkdir()
    (directory / "test_probe.py").write_text(source)
    (directory / "pytest.ini").write_text("[pytest]\n")
    reports = directory / "evidence"
    reports.mkdir()
    binding = "bounded-real-transport"
    evidence.atomic_json(reports / "start.json", {"shard": "4"})
    evidence.atomic_json(
        reports / "admitted.json",
        {
            "binding": binding,
            "inventory": {
                "all": sorted(nodes),
                "full_all": sorted(nodes),
                "deferred": [],
                "shards": {"4": {"nodes": nodes, "deferred": []}},
            },
        },
    )
    environment = dict(os.environ)
    for name in ("PYTEST_XDIST_WORKER", "PYTEST_XDIST_WORKER_COUNT", "PYTEST_XDIST_TESTRUNUID"):
        environment.pop(name, None)
    environment.update(
        PYTHONPATH=str(ROOT),
        PYTHONDONTWRITEBYTECODE="1",
        QUALITY_EVIDENCE_DIR=str(reports),
        QUALITY_EVIDENCE_BINDING=binding,
    )
    supervisor = runner.Supervisor(reports, binding, deadlines)
    status = 0
    try:
        if collect:
            environment["QUALITY_EVIDENCE_MODE"] = "collect"
            status = supervisor.run(
                [
                    sys.executable,
                    "-B",
                    "-m",
                    "pytest",
                    "test_probe.py",
                    "-q",
                    "--no-cov",
                    "-p",
                    "scripts.quality_reporter",
                    "-n0",
                    "--collect-only",
                    *extra,
                ],
                directory,
                environment,
                "collect",
            )
        if not status:
            environment["QUALITY_EVIDENCE_MODE"] = "execute"
            status = supervisor.run(
                [
                    sys.executable,
                    "-B",
                    "-m",
                    "pytest",
                    "test_probe.py",
                    "-q",
                    "--no-cov",
                    "-p",
                    "scripts.quality_reporter",
                    "-n",
                    "4",
                    "--dist=worksteal",
                    f"--max-worker-restart={restart}",
                    f"--junitxml={reports / 'junit.xml'}",
                    *extra,
                ],
                directory,
                environment,
                "execute",
            )
    finally:
        guard_status = supervisor.close()
    return status, guard_status, reports


def test_real_reporter_preserves_failures_and_rejects_incomplete_transport(tmp_path: Path) -> None:
    """One serial group prevents four outer workers launching four copies of this control."""
    status, guard, reports = transport(tmp_path / "normal", NORMAL, NODES)
    assert (status, guard) == (0, 0)
    evidence.validate_execution(reports, "bounded-real-transport", NODES)

    phases = """import pytest
@pytest.fixture
def bad_setup():
    pytest.fail('full setup diagnostic')
@pytest.fixture
def bad_teardown():
    yield
    pytest.fail('full teardown diagnostic')
def test_setup(bad_setup):
    assert True
def test_call():
    print('full captured output')
    pytest.fail('full call diagnostic')
def test_teardown(bad_teardown):
    assert True
@pytest.mark.skip(reason='mandatory skip rejected')
def test_skip():
    assert True
@pytest.mark.xfail(reason='mandatory xfail rejected')
def test_xfail():
    assert False
@pytest.mark.xfail(reason='mandatory xpass rejected', strict=False)
def test_xpass():
    assert True
@pytest.mark.xfail(reason='mandatory strict xpass rejected', strict=True)
def test_strict_xpass():
    assert True
def test_positive():
    assert True
"""
    names = ["setup", "call", "teardown", "skip", "xfail", "xpass", "strict_xpass", "positive"]
    phase_nodes = ["test_probe.py::test_" + name for name in names]
    status, guard, reports = transport(tmp_path / "phases", phases, phase_nodes)
    assert status != 0
    assert guard == 0
    failures = [evidence.read_json(path) for path in reports.glob("*-failure-*.json")]
    for phase in ("setup", "call", "teardown"):
        assert any(
            row["phase"] == phase and "full " + phase + " diagnostic" in json.dumps(row["payload"])
            for row in failures
        )
    assert any(row["payload"].get("wasxfail") == "mandatory xfail rejected" for row in failures)
    assert any(row["payload"].get("wasxfail") == "mandatory xpass rejected" for row in failures)
    assert any("XPASS(strict)" in row["payload"]["traceback"] for row in failures)
    assert any("full captured output" in json.dumps(row["payload"]) for row in failures)

    status, _, reports = transport(tmp_path / "collection", "def broken(:\n", [])
    assert status != 0
    assert list(reports.glob("*-failure-*.json"))
    status, _, _ = transport(tmp_path / "deselection", NORMAL, NODES, extra=("-k", "[0]"))
    assert status != 0

    crashed = NORMAL.replace(
        "    assert number >= 0",
        "    if number == 0:\n        import os\n        os._exit(17)\n    assert number >= 0",
    )
    for restart in (0, 1):
        status, _, reports = transport(
            tmp_path / f"worker-death-{restart}",
            crashed,
            NODES,
            restart=restart,
        )
        assert status != 0
        events = evidence.journal_events(reports, "execute-controller", "bounded-real-transport")
        assert any(event["kind"] == "worker_end" and event["error"] is not None for event in events)

    hanging = NORMAL.replace(
        "    assert number >= 0",
        """    if number == 0:
        pytest.fail('original failure before hang')
    if number == 1:
        import signal, time
        signal.signal(signal.SIGINT, signal.SIG_IGN)
        signal.signal(signal.SIGTERM, signal.SIG_IGN)
        time.sleep(60)
    assert number >= 0""",
    )
    status, guard, reports = transport(
        tmp_path / "failure-then-hang",
        hanging,
        NODES,
        collect=False,
        deadlines=runner.Deadlines(6, 7, 8, 9),
    )
    assert status != 0 or guard != 0
    failures = [evidence.read_json(path) for path in reports.glob("*-failure-*.json")]
    assert any("original failure before hang" in json.dumps(row) for row in failures)


def test_real_supervisor_bounds_soft_hard_timeout_and_cancellation(tmp_path: Path) -> None:
    """Serial plain children exercise actual signals, process groups, logs and reap."""
    scenarios = {
        "soft": "import time; time.sleep(30)",
        "hard": (
            "import signal,time; signal.signal(signal.SIGINT, signal.SIG_IGN); "
            "signal.signal(signal.SIGTERM, signal.SIG_IGN); time.sleep(30)"
        ),
        "cancel": "import time; time.sleep(30)",
    }
    for name, code in scenarios.items():
        directory = tmp_path / name
        directory.mkdir()
        limits = runner.Deadlines(1, 1.5, 2, 3)
        supervisor = runner.Supervisor(directory, "bounded-supervisor", limits)
        timer = threading.Timer(0.15, os.kill, args=(os.getpid(), signal.SIGTERM))
        if name == "cancel":
            timer.start()
        started = time.monotonic()
        try:
            status = supervisor.run(
                [sys.executable, "-B", "-c", code],
                tmp_path,
                dict(os.environ, PYTHONPATH=str(ROOT)),
                "child",
            )
        finally:
            timer.cancel()
            guard = supervisor.close()
        assert status != 0
        assert guard != 0
        assert time.monotonic() - started < 4
        events = evidence.journal_events(directory, "watchdog", "bounded-supervisor")
        signals = [event["signal"] for event in events if event["kind"] == "signal"]
        assert int(signal.SIGINT) in signals
        if name == "hard":
            assert int(signal.SIGTERM) in signals
            assert int(signal.SIGKILL) in signals
        if name == "cancel":
            assert supervisor.signals == [signal.SIGTERM]


def test_real_outer_group_cancel_and_parent_loss_cannot_release_unowned_work(
    tmp_path: Path,
) -> None:
    """Kill only fresh isolated caller groups; the external test owns final cleanup."""
    import subprocess

    code = """import os, signal, subprocess, sys
from pathlib import Path
from scripts import quality_runner as runner
folder = Path(sys.argv[1])
scenario = sys.argv[2]
folder.mkdir()
original = subprocess.Popen
def observed(*args, **kwargs):
    process = original(*args, **kwargs)
    (folder / 'gated-pid.txt').write_text(str(process.pid))
    if scenario == 'before_registration':
        os.kill(os.getpid(), signal.SIGKILL)
    return process
runner.subprocess.Popen = observed
supervisor = runner.Supervisor(folder, 'isolated-caller', runner.Deadlines(5, 6, 7, 8))
work = (
    "import os,signal,subprocess,sys,time; from pathlib import Path; "
    "signal.signal(signal.SIGINT, signal.SIG_IGN); signal.signal(signal.SIGTERM, signal.SIG_IGN); "
    "child=subprocess.Popen([sys.executable,'-B','-c',"
    "'import signal,time; signal.signal(signal.SIGINT,signal.SIG_IGN); "
    "signal.signal(signal.SIGTERM,signal.SIG_IGN); time.sleep(60)']); "
    "Path(sys.argv[1]).write_text(str(os.getpid())+' '+str(child.pid)); time.sleep(60)"
)
try:
    supervisor.run([sys.executable, '-B', '-c', work, str(folder / 'work-started.txt')],
                   folder, dict(os.environ), 'child')
finally:
    supervisor.close()
"""

    def running(pid: int) -> bool:
        result = subprocess.run(
            ["ps", "-o", "stat=", "-p", str(pid)], capture_output=True, check=False, text=True
        )
        return bool(result.stdout.strip()) and not result.stdout.strip().startswith("Z")

    for scenario in ("outer_group", "before_registration"):
        directory = tmp_path / scenario
        process = subprocess.Popen(
            [sys.executable, "-B", "-c", code, str(directory), scenario],
            cwd=tmp_path,
            env=dict(os.environ, PYTHONPATH=str(ROOT)),
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            start_new_session=True,
        )
        child_pid: int | None = None
        try:
            deadline = time.monotonic() + 5
            marker = directory / (
                "work-started.txt" if scenario == "outer_group" else "gated-pid.txt"
            )
            while not marker.is_file() and time.monotonic() < deadline and process.poll() is None:
                time.sleep(0.01)
            assert marker.is_file()
            child_pid = int((directory / "gated-pid.txt").read_text())
            descendants = [child_pid]
            if scenario == "outer_group":
                descendants = [int(value) for value in marker.read_text().split()]
                os.killpg(process.pid, signal.SIGTERM)
                time.sleep(0.1)
                if process.poll() is None:
                    os.killpg(process.pid, signal.SIGKILL)
            stdout, _ = process.communicate(timeout=3)
            (directory / "caller-output.txt").write_bytes(stdout)
            deadline = time.monotonic() + 3
            while any(running(pid) for pid in descendants) and time.monotonic() < deadline:
                time.sleep(0.02)
            assert all(not running(pid) for pid in descendants)
            if scenario == "before_registration":
                assert not (directory / "work-started.txt").exists()
            events = evidence.journal_events(directory, "watchdog", "isolated-caller")
            assert events[-1]["kind"] == "watchdog_end"
            assert events[-1]["exit_status"] != 0
        finally:
            if process.poll() is None:
                runner.signal_group(process.pid, signal.SIGKILL)
                process.wait(timeout=2)
            if child_pid is not None and running(child_pid):
                runner.signal_group(child_pid, signal.SIGKILL)
            if process.stdout is not None:
                process.stdout.close()
