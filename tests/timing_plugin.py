"""Opt-in per-worker timing evidence; never changes selection or test outcomes."""

from __future__ import annotations

import json
import os
import platform
import time
from pathlib import Path

import pytest

_started = 0.0
_collection_seconds = 0.0
_collected: list[str] = []
_reports: list[dict[str, str | float]] = []
_progress_session: str | None = None


def _optional_linux_text(path: Path) -> str | None:
    if platform.system() != "Linux" or not path.is_file():
        return None
    return path.read_text(encoding="utf-8")


def _resource_snapshot() -> dict[str, object]:
    membership = _optional_linux_text(Path("/proc/self/cgroup"))
    unified = next(
        (
            line.removeprefix("0::")
            for line in (membership or "").splitlines()
            if line.startswith("0::")
        ),
        None,
    )
    cgroup = (
        Path("/sys/fs/cgroup") / unified.lstrip("/")
        if unified is not None and ".." not in Path(unified).parts
        else None
    )
    return {
        "cpu_count": os.cpu_count(),
        "proc_self_status": _optional_linux_text(Path("/proc/self/status")),
        "proc_loadavg": _optional_linux_text(Path("/proc/loadavg")),
        "proc_meminfo": _optional_linux_text(Path("/proc/meminfo")),
        "proc_self_cgroup": membership,
        "cgroup_v2_path": str(cgroup) if cgroup is not None else None,
        "cgroup_v2_files": {
            name: _optional_linux_text(cgroup / name) if cgroup is not None else None
            for name in ("cpu.max", "cpu.stat", "memory.current", "memory.max", "memory.events")
        },
    }


def _append_progress(
    event: str, fields: dict[str, object] | None = None, *, resources: bool = False
) -> None:
    if "TEST_TIMING_DIR" not in os.environ:
        return
    worker = os.environ.get("PYTEST_XDIST_WORKER", "controller")
    payload: dict[str, object] = {
        "event": event,
        "worker": worker,
        "pid": os.getpid(),
        "session": _progress_session,
        "monotonic_seconds": time.monotonic(),
        "wall_seconds": time.time(),
        "process_cpu_seconds": time.process_time(),
        **(fields or {}),
    }
    if resources:
        payload["resources"] = _resource_snapshot()
    directory = Path(os.environ["TEST_TIMING_DIR"])
    directory.mkdir(parents=True, exist_ok=True)
    # Append and close each record so a killed session retains completed events.
    # Session/PID fields distinguish nested pytest processes sharing a worker name.
    with (directory / f"{worker}.progress.jsonl").open("a", encoding="utf-8") as stream:
        stream.write(json.dumps(payload, separators=(",", ":")) + "\n")


def pytest_sessionstart(session: pytest.Session) -> None:
    global _started, _progress_session
    _started = time.perf_counter()
    _reports.clear()
    if "TEST_TIMING_DIR" in os.environ:
        _progress_session = f"{os.getpid()}:{time.time_ns()}"
        _append_progress(
            "sessionstart",
            {
                "github_run_id": os.environ.get("GITHUB_RUN_ID"),
                "github_sha": os.environ.get("GITHUB_SHA"),
                "worker_count": os.environ.get("PYTEST_XDIST_WORKER_COUNT"),
            },
            resources=True,
        )


def pytest_collection_finish(session: pytest.Session) -> None:
    global _collection_seconds
    if "TEST_TIMING_DIR" in os.environ:
        _collection_seconds = time.perf_counter() - _started
        _collected[:] = [item.nodeid for item in session.items]
        _append_progress(
            "collection",
            {"collection_seconds": _collection_seconds, "collected_nodeids": _collected},
        )


def pytest_runtest_logstart(nodeid: str) -> None:
    _append_progress("protocolstart", {"nodeid": nodeid}, resources=True)


def pytest_runtest_logreport(report: pytest.TestReport) -> None:
    if "TEST_TIMING_DIR" in os.environ:
        _reports.append(
            {
                "nodeid": report.nodeid,
                "phase": report.when,
                "seconds": report.duration,
                "outcome": report.outcome,
            }
        )

        _append_progress(
            "report",
            {
                "nodeid": report.nodeid,
                "phase": report.when,
                "outcome": report.outcome,
                "duration_seconds": report.duration,
            },
        )


def pytest_sessionfinish(session: pytest.Session, exitstatus: int) -> None:
    if "TEST_TIMING_DIR" not in os.environ:
        return
    directory = Path(os.environ["TEST_TIMING_DIR"])
    directory.mkdir(parents=True, exist_ok=True)
    worker = os.environ.get("PYTEST_XDIST_WORKER", "controller")
    memory_path = Path("/proc/meminfo")
    payload = {
        "worker": worker,
        "platform": platform.platform(),
        "python": platform.python_version(),
        "cpu_count": os.cpu_count(),
        "linux_meminfo": memory_path.read_text() if memory_path.is_file() else None,
        "github_run_id": os.environ.get("GITHUB_RUN_ID"),
        "github_sha": os.environ.get("GITHUB_SHA"),
        "worker_count": os.environ.get("PYTEST_XDIST_WORKER_COUNT"),
        "elapsed_seconds": time.perf_counter() - _started,
        "collection_seconds": _collection_seconds,
        "exit_status": int(exitstatus),
        "collected_nodeids": _collected,
        "reports": _reports,
    }
    (directory / f"{worker}.json").write_text(
        json.dumps(payload, indent=2) + "\n", encoding="utf-8"
    )
    _append_progress("sessionfinish", {"exit_status": int(exitstatus)}, resources=True)
