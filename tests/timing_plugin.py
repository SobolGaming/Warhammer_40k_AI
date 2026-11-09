"""Opt-in per-worker timing evidence; never changes selection or test outcomes."""

from __future__ import annotations

import json
import os
import platform
import time
from datetime import UTC, datetime
from pathlib import Path

import pytest

_started = 0.0
_collection_seconds = 0.0
_collected: list[str] = []
_reports: list[dict[str, str | float]] = []
_progress_path: Path | None = None


def pytest_sessionstart(session: pytest.Session) -> None:
    global _started, _progress_path
    _started = time.perf_counter()
    _reports.clear()
    _progress_path = None
    progress = os.environ.get("TEST_TIMING_PROGRESS")
    if progress is None:
        return
    if progress != "1" or not os.environ.get("TEST_TIMING_DIR"):
        raise pytest.UsageError("TEST_TIMING_PROGRESS requires value 1 and TEST_TIMING_DIR.")
    worker = os.environ.get("PYTEST_XDIST_WORKER")
    if worker is None:
        return  # Controller receives forwarded reports; only workers journal execution.
    directory = Path(os.environ["TEST_TIMING_DIR"])
    directory.mkdir(parents=True, exist_ok=True)
    _progress_path = directory / f"{worker}.progress.jsonl"
    _append_progress(
        "session_start",
        schema="pytest-worker-progress-v1",
        worker=worker,
        pid=os.getpid(),
        started_utc=datetime.now(UTC).isoformat(),
        monotonic_origin_seconds=_started,
        github_run_id=os.environ.get("GITHUB_RUN_ID"),
        github_run_attempt=os.environ.get("GITHUB_RUN_ATTEMPT"),
        github_sha=os.environ.get("GITHUB_SHA"),
        worker_count=os.environ.get("PYTEST_XDIST_WORKER_COUNT"),
    )


def pytest_collection_finish(session: pytest.Session) -> None:
    global _collection_seconds
    if "TEST_TIMING_DIR" in os.environ:
        _collection_seconds = time.perf_counter() - _started
        _collected[:] = [item.nodeid for item in session.items]
        _append_progress(
            "collection", seconds=_collection_seconds, count=len(_collected), nodeids=_collected
        )


def _append_progress(event: str, **fields: object) -> None:
    """Close each complete line; a process kill can still leave a partial last line.

    This diagnostic journal is not a durable or authenticated timing receipt.
    Its .jsonl suffix keeps incomplete progress outside final .json calibration.
    """
    if _progress_path is not None:
        payload = {"event": event, "elapsed_seconds": time.perf_counter() - _started, **fields}
        with _progress_path.open("a", encoding="utf-8") as output:
            output.write(json.dumps(payload, separators=(",", ":")) + "\n")


def pytest_runtest_logstart(nodeid: str, location: tuple[str, int | None, str]) -> None:
    _append_progress("test_start", nodeid=nodeid)


def pytest_runtest_logreport(report: pytest.TestReport) -> None:
    if "TEST_TIMING_DIR" in os.environ:
        phase: dict[str, str | float] = {
            "nodeid": report.nodeid,
            "phase": report.when,
            "seconds": report.duration,
            "outcome": report.outcome,
        }
        _reports.append(phase)
        _append_progress("phase", **phase)


def pytest_sessionfinish(session: pytest.Session, exitstatus: int) -> None:
    if "TEST_TIMING_DIR" not in os.environ:
        return
    _append_progress("session_finish", exit_status=int(exitstatus))
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
