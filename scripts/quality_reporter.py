"""Durable pytest phase evidence; bootstrap imports only stdlib and pytest."""

from __future__ import annotations

import os
import sys
from collections.abc import Generator
from pathlib import Path
from typing import Any

import pytest

from scripts.quality_evidence import WORKERS, Journal, read_json, require

_reporter: Reporter | None = None


class Reporter:
    def __init__(self, config: pytest.Config) -> None:
        self.directory = Path(os.environ["QUALITY_EVIDENCE_DIR"])
        self.mode = os.environ["QUALITY_EVIDENCE_MODE"]
        self.worker = os.environ.get("PYTEST_XDIST_WORKER", "controller")
        self.binding = os.environ["QUALITY_EVIDENCE_BINDING"]
        self.admitted = read_json(self.directory / "admitted.json")
        self.shard = read_json(self.directory / "start.json")["shard"]
        require(self.binding == self.admitted["binding"], "Reporter binding changed")
        require(self.mode in {"collect", "execute"}, "Unknown reporter mode")
        require(
            self.worker == "controller" or self.worker in WORKERS, "Unexpected worker generation"
        )
        if self.worker != "controller":
            require(os.environ["PYTEST_XDIST_WORKER_COUNT"] == "4", "Worker count drift")
        self.journal = Journal(self.directory, self.mode + "-" + self.worker, self.binding)
        self.bad = False
        self.deferred: list[str] = []
        self.started: set[str] = set()
        self.config = config

    def problem(self, kind: str, **payload: Any) -> None:
        self.bad = True
        self.journal.emit(kind, **payload)


def reporter() -> Reporter:
    require(_reporter is not None, "Quality reporter was not configured")
    assert _reporter is not None
    return _reporter


def pytest_configure(config: pytest.Config) -> None:
    global _reporter
    _reporter = Reporter(config)


def pytest_sessionstart(session: pytest.Session) -> None:
    state = reporter()
    state.journal.emit(
        "session_start",
        pid=os.getpid(),
        generation=0,
        plugins=sorted(
            {
                (dist.project_name.lower().replace("_", "-"), dist.version)
                for _, dist in session.config.pluginmanager.list_plugin_distinfo()
            }
        ),
        args=list(session.config.invocation_params.args),
        ini={name: session.config.getini(name) for name in ("addopts", "markers", "testpaths")},
    )


def pytest_collection_finish(session: pytest.Session) -> None:
    state = reporter()
    if state.mode == "execute" and state.worker == "controller":
        return
    nodes = [item.nodeid for item in session.items]
    expected = (
        state.admitted["inventory"]["full_all"]
        if state.mode == "collect"
        else state.admitted["inventory"]["shards"][state.shard]["nodes"]
    )
    declared = (
        []
        if state.mode == "collect"
        else state.admitted["inventory"]["shards"][state.shard]["deferred"]
    )
    require(state.deferred == declared, "Missing or changed declared comparison deselection")
    state.journal.emit("collection", nodes=nodes, deferred=state.deferred)
    actual = sorted(nodes) if state.mode == "collect" else nodes
    require(
        len(nodes) == len(set(nodes)) and actual == expected,
        "Fresh collection differs from exact-head inventory",
    )


def pytest_deselected(items: list[pytest.Item]) -> None:
    state = reporter()
    nodes = [item.nodeid for item in items]
    expected = state.admitted["inventory"]["shards"][state.shard]["deferred"]
    require(
        state.mode == "execute"
        and state.worker in WORKERS
        and bool(expected)
        and not state.deferred
        and nodes == expected
        and len(nodes) == len(set(nodes)),
        "Unexpected quality deselection",
    )
    state.deferred = nodes


def pytest_collectreport(report: pytest.CollectReport) -> None:
    if report.failed or report.skipped:
        state = reporter()
        payload = state.journal.failure(report.nodeid, "collection", str(report.longrepr))
        state.problem("collection_error", node=report.nodeid, failure=payload)
        print(str(report.longrepr), file=sys.__stderr__, flush=True)


@pytest.hookimpl(optionalhook=True)
def pytest_configure_node(node: Any) -> None:
    state = reporter()
    worker = node.gateway.id
    require(worker in WORKERS and worker not in state.started, "Unexpected/restarted worker")
    state.started.add(worker)
    state.journal.emit("worker_start", worker=worker, generation=0)


@pytest.hookimpl(optionalhook=True)
def pytest_xdist_node_collection_finished(node: Any, ids: list[str]) -> None:
    state = reporter()
    state.journal.emit("worker_collection", worker=node.gateway.id, nodes=ids, generation=0)
    require(
        ids == state.admitted["inventory"]["shards"][state.shard]["nodes"],
        "Controller observed invalid worker collection",
    )


@pytest.hookimpl(optionalhook=True)
def pytest_testnodedown(node: Any, error: Any) -> None:
    state = reporter()
    if error is not None:
        state.bad = True
    state.journal.emit(
        "worker_end",
        worker=node.gateway.id,
        error=None if error is None else str(error),
        generation=0,
    )


@pytest.hookimpl(wrapper=True, tryfirst=True)
def pytest_runtest_protocol(
    item: pytest.Item, nextitem: pytest.Item | None
) -> Generator[None, Any, Any]:
    state = reporter()
    state.journal.emit("node_start", node=item.nodeid)
    state.journal.active(item.nodeid, "before_setup")
    item.user_properties.append(("quality_nodeid", item.nodeid))
    result = yield
    state.journal.emit("node_end", node=item.nodeid)
    state.journal.active("", "idle")
    return result


def phase_start(item: pytest.Item, phase: str) -> None:
    state = reporter()
    state.journal.emit("phase_start", node=item.nodeid, phase=phase)
    state.journal.active(item.nodeid, phase)


@pytest.hookimpl(wrapper=True, tryfirst=True)
def pytest_runtest_setup(item: pytest.Item) -> Generator[None, Any, Any]:
    phase_start(item, "setup")
    return (yield)


@pytest.hookimpl(wrapper=True, tryfirst=True)
def pytest_runtest_call(item: pytest.Item) -> Generator[None, Any, Any]:
    phase_start(item, "call")
    return (yield)


@pytest.hookimpl(wrapper=True, tryfirst=True)
def pytest_runtest_teardown(
    item: pytest.Item, nextitem: pytest.Item | None
) -> Generator[None, Any, Any]:
    phase_start(item, "teardown")
    return (yield)


@pytest.hookimpl(wrapper=True, tryfirst=True)
def pytest_runtest_makereport(
    item: pytest.Item, call: pytest.CallInfo[None]
) -> Generator[None, Any, Any]:
    report = yield
    state = reporter()
    wasxfail = hasattr(report, "wasxfail")
    payload: dict[str, Any] = {
        "node": report.nodeid,
        "phase": report.when,
        "outcome": report.outcome,
        "wasxfail": wasxfail,
        "duration": report.duration,
    }
    if report.outcome != "passed" or wasxfail:
        state.bad = True
        detail = {
            "traceback": str(report.longrepr),
            "sections": list(report.sections),
            "wasxfail": str(report.wasxfail) if wasxfail else None,
            "outcome": report.outcome,
        }
        payload["failure"] = state.journal.failure(report.nodeid, report.when, detail)
    sequence = state.journal.emit("phase_end", **payload)
    if "failure" in payload:
        print(f"QUALITY {report.nodeid} {report.when}: {detail}", file=sys.__stderr__, flush=True)
    report.quality_origin = {"worker": state.worker, "sequence": sequence, "generation": 0}
    return report


def pytest_runtest_logreport(report: pytest.TestReport) -> None:
    state = reporter()
    if state.worker != "controller":
        return
    origin = report.__dict__["quality_origin"]
    require(origin["worker"] in WORKERS and origin["generation"] == 0, "Unknown report origin")
    state.journal.emit(
        "mirror",
        worker=origin["worker"],
        origin_sequence=origin["sequence"],
        node=report.nodeid,
        phase=report.when,
        outcome=report.outcome,
        wasxfail=hasattr(report, "wasxfail"),
    )
    if report.outcome != "passed" or hasattr(report, "wasxfail"):
        state.bad = True
        print(
            f"QUALITY FAILURE {report.nodeid} [{report.when}]\n{report.longrepr}",
            file=sys.__stderr__,
            flush=True,
        )
        for name, content in report.sections:
            print(f"{name}\n{content}", file=sys.__stderr__, flush=True)


@pytest.hookimpl(trylast=True)
def pytest_sessionfinish(session: pytest.Session, exitstatus: int) -> None:
    state = reporter()
    if state.bad:
        session.exitstatus = pytest.ExitCode.TESTS_FAILED
    state.journal.emit("session_finish", exit_status=int(session.exitstatus))
