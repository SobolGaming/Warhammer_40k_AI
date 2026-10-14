"""Diagnostic-only collection guard and opt-in profiling of the real quality children."""

from __future__ import annotations

import functools
import inspect
import json
import os
import subprocess
import sys
import time
from pathlib import Path

import pytest

_native_run = subprocess.run
_children: list[dict[str, object]] = []
_spans: dict[str, dict[str, float | int]] = {}
_stack: list[dict[str, float]] = []
_originals: list[tuple[type, str, object]] = []
_last_write = 0.0


def write_boundaries() -> None:
    output = Path(os.environ["ATTRIBUTION_RUN_OUTPUT"])
    (output / "boundaries.json").write_text(
        json.dumps(
            {
                "spans": _spans,
                "active_depth": len(_stack),
                "qualification": (
                    "Inclusive spans overlap; exclusive removes only wrapped descendants. "
                    "Partial until the original test and all phases pass."
                ),
            },
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )


def boundary(owner: type, name: str, label: str) -> None:
    descriptor = inspect.getattr_static(owner, name)
    function = (
        descriptor.__func__ if isinstance(descriptor, (classmethod, staticmethod)) else descriptor
    )
    _originals.append((owner, name, descriptor))

    @functools.wraps(function)
    def timed(*args, **kwargs):
        global _last_write
        frame = {"start": time.perf_counter(), "child": 0.0}
        _stack.append(frame)
        try:
            return function(*args, **kwargs)
        finally:
            elapsed = time.perf_counter() - frame["start"]
            _stack.pop()
            row = _spans.setdefault(
                label, {"calls": 0, "inclusive_seconds": 0.0, "boundary_exclusive_seconds": 0.0}
            )
            row["calls"] += 1
            row["inclusive_seconds"] += elapsed
            row["boundary_exclusive_seconds"] += elapsed - frame["child"]
            if _stack:
                _stack[-1]["child"] += elapsed
            if time.monotonic() - _last_write >= 30:
                write_boundaries()
                _last_write = time.monotonic()

    replacement = (
        classmethod(timed)
        if isinstance(descriptor, classmethod)
        else staticmethod(timed)
        if isinstance(descriptor, staticmethod)
        else timed
    )
    setattr(owner, name, replacement)


def install_boundaries() -> None:
    from warhammer40k_core.adapters.local_session import LocalGameSession
    from warhammer40k_core.core.army_catalog import ArmyCatalog
    from warhammer40k_core.engine.lifecycle import GameLifecycle
    from warhammer40k_core.engine.mission_setup import MissionSetup
    from warhammer40k_core.engine.replay import ReplayRunner

    for owner, name, label in (
        (ArmyCatalog, "phase9a_canonical_content_pack", "catalog.construct"),
        (ArmyCatalog, "from_payload", "catalog.restore"),
        (MissionSetup, "from_mission_pack", "mission.construct"),
        (GameLifecycle, "start", "lifecycle.start"),
        (GameLifecycle, "from_payload", "lifecycle.restore"),
        (GameLifecycle, "submit_decision", "native.submit"),
        (GameLifecycle, "advance_until_decision_or_terminal", "native.advance"),
        (LocalGameSession, "to_persistence_payload", "session.export"),
        (LocalGameSession, "from_persistence_payload", "session.restore"),
        (LocalGameSession, "fork", "session.fork"),
        (LocalGameSession, "view", "view.project"),
        (LocalGameSession, "view_for_context", "view.context_project"),
        (LocalGameSession, "events_since", "view.events"),
        (LocalGameSession, "events_since_for_context", "view.context_events"),
        (ReplayRunner, "run", "replay.run"),
    ):
        boundary(owner, name, label)


def pytest_collection_finish(session: pytest.Session) -> None:
    expected = os.environ["ATTRIBUTION_NODEID"]
    observed = [item.nodeid for item in session.items]
    if observed != [expected]:
        raise pytest.UsageError(f"Exact diagnostic node mismatch: {observed!r} != {[expected]!r}")


def pytest_sessionstart(session: pytest.Session) -> None:
    if os.environ["ATTRIBUTION_BOUNDARIES"] == "1":
        install_boundaries()
    if os.environ["ATTRIBUTION_CHILD_PROFILES"] != "1":
        return
    root = Path.cwd()
    output = Path(os.environ["ATTRIBUTION_RUN_OUTPUT"])
    generator = root / "scripts/build_external_contract.py"

    def profiled_run(command, *args, **kwargs):
        # Only the exact two original generator commands are instrumented.
        if not isinstance(command, (list, tuple)):
            return _native_run(command, *args, **kwargs)
        actual = list(command)
        if actual not in (
            [sys.executable, str(generator)],
            [sys.executable, str(generator), "--check"],
        ):
            return _native_run(command, *args, **kwargs)
        sequence = len(_children) + 1
        profile = output / f"generator-{sequence}.prof"
        wrapped = [
            sys.executable,
            str(root / "scripts/ci_attribution_profile.py"),
            str(profile),
            *actual[1:],
        ]
        record = {"original": actual, "instrumented": wrapped, "profile": str(profile)}
        _children.append(record)
        started = time.perf_counter()
        try:
            return _native_run(wrapped, *args, **kwargs)
        finally:
            record["seconds"] = time.perf_counter() - started
            (output / "generator-commands.json").write_text(
                json.dumps(_children, indent=2) + "\n", encoding="utf-8"
            )

    subprocess.run = profiled_run


def pytest_sessionfinish(session: pytest.Session, exitstatus: int) -> None:
    subprocess.run = _native_run
    for owner, name, descriptor in reversed(_originals):
        setattr(owner, name, descriptor)
    if os.environ["ATTRIBUTION_BOUNDARIES"] == "1":
        write_boundaries()
    if os.environ["ATTRIBUTION_CHILD_PROFILES"] == "1" and exitstatus == 0:
        commands = [row["original"] for row in _children]
        generator = str(Path.cwd() / "scripts/build_external_contract.py")
        if commands != [[sys.executable, generator], [sys.executable, generator, "--check"]]:
            raise pytest.UsageError("Both real quality generator and independent checker must run")
