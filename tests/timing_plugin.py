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


def pytest_sessionstart(session: pytest.Session) -> None:
    global _started
    _started = time.perf_counter()
    _reports.clear()


def pytest_collection_finish(session: pytest.Session) -> None:
    global _collection_seconds
    if "TEST_TIMING_DIR" in os.environ:
        _collection_seconds = time.perf_counter() - _started
        _collected[:] = [item.nodeid for item in session.items]


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
