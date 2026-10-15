"""Review candidate: instrument named owners without changing arguments or results."""

from __future__ import annotations

import functools
import importlib
import inspect
import json
import os
import threading
import time
from pathlib import Path

import pytest

NODE = (
    "tests/unit/test_critical_hits.py::"
    "test_critical_consumers_through_facade_restore_and_replay[fight]"
)
ENGINE = "warhammer40k_core.engine."
# Resolve the actual lifecycle call-site alias where a function was imported directly.
TARGETS = (
    ("tests.critical_hit_helpers", None, "critical_hit_session", "fixture", "fixture"),
    (
        "warhammer40k_core.adapters.local_session",
        "LocalGameSession",
        "from_persistence_payload",
        "checkpoint",
        "checkpoint",
    ),
    (ENGINE + "replay", "ReplayRunner", "run", "replay", "replay"),
    (ENGINE + "lifecycle", "GameLifecycle", "from_payload", "restore", None),
    (ENGINE + "lifecycle", "GameConfig", "from_payload", "decode.config", None),
    ("warhammer40k_core.core.army_catalog", "ArmyCatalog", "from_payload", "decode.catalog", None),
    (ENGINE + "lifecycle", "GameState", "from_payload", "decode.state", None),
    (ENGINE + "lifecycle", "DecisionController", "from_payload", "decode.decisions", None),
    (ENGINE + "lifecycle", "ReactionQueue", "from_payload", "decode.reactions", None),
    (ENGINE + "lifecycle", None, "validate_payload_consistency", "validate.consistency", None),
    (ENGINE + "lifecycle", None, "validate_reaction_queue_consistency", "validate.reactions", None),
    (
        ENGINE + "lifecycle",
        "GameLifecycle",
        "_refresh_runtime_content_bundle_if_armies_mustered",
        "bundle.refresh",
        None,
    ),
    (
        ENGINE + "lifecycle",
        None,
        "_runtime_content_activation_input_hash",
        "bundle.input_hash",
        None,
    ),
    (ENGINE + "lifecycle", None, "build_runtime_content_bundle_for_armies", "bundle.build", None),
    (ENGINE + "lifecycle_history_origins", None, "restore", "history.decode", None),
    (ENGINE + "lifecycle_history_origins", None, "validate", "history.validate", None),
    (
        ENGINE + "modifier_evaluation_history",
        None,
        "validate_modifier_origin",
        "history.modifiers",
        "historical_root",
    ),
    (
        ENGINE + "movement_failed_setup_history",
        None,
        "validate_failed_setup_origin",
        "history.failed_setup",
        "historical_root",
    ),
    (
        ENGINE + "psychic_modifier_history_origin",
        None,
        "validate_psychic_history_origin",
        "history.psychic",
        "historical_root",
    ),
    (
        ENGINE + "ingress_placement_history",
        None,
        "validate_ingress_history_origin",
        "history.ingress",
        "historical_root",
    ),
    (
        ENGINE + "healing_off_battlefield_history",
        None,
        "validate_revival_history_origin",
        "history.revival",
        "historical_root",
    ),
)

_phase = "session"
_stack = []
_rows = {}
_edges = {}
_originals = []
_targets = []
_reports = []
_output = None
_mode = None
_thread = None
_last_write = 0.0
_max_depth = 0
_phase_spans = {}
_telemetry_failures = []


def pytest_addoption(parser):
    parser.addoption("--restore-mode", choices=("control", "internal"), required=True)
    parser.addoption("--restore-output", required=True)


def write_receipt(*, complete=False, exitstatus=None):
    data = {
        "schema": "restore-internal-attribution-v1",
        "mode": _mode,
        "nodeid": NODE,
        "complete": complete and not _telemetry_failures,
        "telemetry_failures": _telemetry_failures,
        "exitstatus": exitstatus,
        "reports": _reports,
        "phase_spans": _phase_spans,
        "rows": list(_rows.values()),
        "edges": [
            {"parent": key[0], "child": key[1], "calls": value}
            for key, value in sorted(_edges.items())
        ],
        "active_depth": len(_stack),
        "max_restore_depth": _max_depth,
        "active_labels": [frame["label"] for frame in _stack],
        "targets": _targets,
        "qualification": (
            "Exclusive removes only instrumented direct children; residual includes "
            "uninstrumented work and diagnostic overhead. Inclusive rows overlap. "
            "Partial receipts are not passing samples."
        ),
    }
    temporary = _output / "attribution.partial.json"
    temporary.write_text(json.dumps(data, indent=2, allow_nan=False) + "\n", encoding="utf-8")
    temporary.replace(_output / "attribution.json")


def install(owner, name, descriptor, label, purpose_tag):
    function = (
        descriptor.__func__ if isinstance(descriptor, (classmethod, staticmethod)) else descriptor
    )

    @functools.wraps(function)
    def measured(*args, **kwargs):
        global _last_write, _max_depth
        if threading.get_ident() != _thread:
            raise RuntimeError("This reviewed diagnostic requires one execution thread")
        tags = [frame["purpose_tag"] for frame in _stack] + [purpose_tag]
        purpose = next(
            (tag for tag in ("historical_root", "fixture", "replay", "checkpoint") if tag in tags),
            "other",
        )
        depth = sum(frame["label"] == "restore" for frame in _stack) + int(label == "restore")
        _max_depth = max(_max_depth, depth)
        key = (_phase, purpose, depth, label)
        parent = _stack[-1]["label"] if _stack else "<root>"
        frame = {"label": label, "purpose_tag": purpose_tag, "child_wall": 0.0, "child_cpu": 0.0}
        _stack.append(frame)
        started, cpu_started = time.perf_counter(), time.process_time()
        returned = False
        try:
            result = function(*args, **kwargs)
            returned = True
            return result
        finally:
            elapsed, cpu = time.perf_counter() - started, time.process_time() - cpu_started
            if _stack.pop() is not frame:
                raise RuntimeError("Attribution nesting corrupted")
            if _stack:
                _stack[-1]["child_wall"] += elapsed
                _stack[-1]["child_cpu"] += cpu
            row = _rows.setdefault(
                key,
                {
                    "phase": key[0],
                    "purpose": purpose,
                    "restore_depth": depth,
                    "label": label,
                    "calls": 0,
                    "raised_calls": 0,
                    "inclusive_wall": 0.0,
                    "exclusive_wall": 0.0,
                    "inclusive_cpu": 0.0,
                    "exclusive_cpu": 0.0,
                },
            )
            row["calls"] += 1
            row["raised_calls"] += int(not returned)
            row["inclusive_wall"] += elapsed
            row["exclusive_wall"] += elapsed - frame["child_wall"]
            row["inclusive_cpu"] += cpu
            row["exclusive_cpu"] += cpu - frame["child_cpu"]
            _edges[parent, label] = _edges.get((parent, label), 0) + 1
            if time.monotonic() - _last_write >= 30:
                try:
                    write_receipt()
                except OSError as error:
                    # Telemetry cannot replace an original return or domain exception.
                    # A sticky diagnostic failure is surfaced at session completion.
                    _telemetry_failures.append(
                        {"type": type(error).__name__, "message": str(error)}
                    )
                _last_write = time.monotonic()

    replacement = (
        classmethod(measured)
        if isinstance(descriptor, classmethod)
        else staticmethod(measured)
        if isinstance(descriptor, staticmethod)
        else measured
    )
    _originals.append((owner, name, descriptor, replacement))
    setattr(owner, name, replacement)


def pytest_sessionstart(session):
    global _output, _mode, _thread, _last_write
    _mode = session.config.getoption("--restore-mode")
    _output = Path(session.config.getoption("--restore-output")).resolve()
    expected_root = Path(os.environ["RESTORE_OUTPUT_ROOT"]).resolve()
    if (
        _output.parent != expected_root
        or _output.name != _mode
        or _output.is_relative_to(Path.cwd())
    ):
        raise pytest.UsageError(
            "Invocation output does not match the external controller directory"
        )
    if not _output.is_dir() or (_output / "attribution.json").exists():
        raise pytest.UsageError("A new owned invocation directory is required")
    _thread = threading.get_ident()
    # Resolve/import the same targets in both processes. Only internal installs wrappers.
    import_started = time.perf_counter()
    resolved = []
    for module_name, class_name, name, label, purpose in TARGETS:
        module = importlib.import_module(module_name)
        owner = module if class_name is None else getattr(module, class_name)
        descriptor = inspect.getattr_static(owner, name)
        function = (
            descriptor.__func__
            if isinstance(descriptor, (classmethod, staticmethod))
            else descriptor
        )
        if not inspect.isfunction(function):
            raise pytest.UsageError(f"Unexpected instrument target: {label}")
        resolved.append((owner, name, descriptor, label, purpose))
        _targets.append(
            {
                "label": label,
                "module": module_name,
                "class": class_name,
                "attribute": name,
                "function_module": function.__module__,
                "qualname": function.__qualname__,
            }
        )
    _phase_spans["target_imports"] = time.perf_counter() - import_started
    if _mode == "internal":
        for target in resolved:
            install(*target)
    _last_write = time.monotonic()
    write_receipt()


def pytest_collection_finish(session):
    observed = [item.nodeid for item in session.items]
    if observed != [NODE]:
        raise pytest.UsageError(f"Exact original node required: {observed!r}")


def phase_span(name):
    global _phase
    previous, _phase = _phase, name
    started = time.perf_counter()
    try:
        yield
    finally:
        _phase_spans[name] = time.perf_counter() - started
        _phase = previous


@pytest.hookimpl(wrapper=True)
def pytest_collection(session):
    yield from phase_span("collection")


@pytest.hookimpl(wrapper=True)
def pytest_runtest_setup(item):
    yield from phase_span("setup")


@pytest.hookimpl(wrapper=True)
def pytest_runtest_call(item):
    yield from phase_span("call")


@pytest.hookimpl(wrapper=True)
def pytest_runtest_teardown(item, nextitem):
    yield from phase_span("teardown")


def pytest_runtest_logreport(report):
    _reports.append(
        {
            "nodeid": report.nodeid,
            "when": report.when,
            "outcome": report.outcome,
            "duration": report.duration,
        }
    )
    write_receipt()


def restore_originals():
    changed = []
    for owner, name, descriptor, replacement in reversed(_originals):
        if inspect.getattr_static(owner, name) is not replacement:
            changed.append(name)
        setattr(owner, name, descriptor)
    _originals.clear()
    if changed:
        raise RuntimeError(f"Instrumented descriptors changed during invocation: {changed}")


def pytest_sessionfinish(session, exitstatus):
    restore_originals()
    expected = [(NODE, phase, "passed") for phase in ("setup", "call", "teardown")]
    observed = [(r["nodeid"], r["when"], r["outcome"]) for r in _reports]
    complete = exitstatus == 0 and observed == expected and not _stack and not _telemetry_failures
    if _telemetry_failures:
        session.exitstatus = pytest.ExitCode.INTERNAL_ERROR
    write_receipt(complete=complete, exitstatus=int(session.exitstatus))


def pytest_unconfigure(config):
    restore_originals()
