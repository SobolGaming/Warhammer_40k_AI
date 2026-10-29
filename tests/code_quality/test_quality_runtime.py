"""CI54 protects complete quality evidence without changing engine or behavioral gates."""

from __future__ import annotations

import ast
import copy
import errno
import json
import os
import subprocess
import sys
import xml.etree.ElementTree as ET
from collections.abc import Callable
from contextvars import ContextVar
from pathlib import Path
from typing import Any, Protocol, cast

import pytest
from scripts import quality_evidence as evidence
from scripts import quality_runner as runner
from tools.performance_history_snapshot import Domain, Snapshot

ROOT = Path(__file__).resolve().parents[2]


def test_live_workflow_preserves_required_names_and_all_four_producer_controls() -> None:
    workflow = (ROOT / ".github/workflows/ci.yml").read_text()
    before = subprocess.check_output(
        ["git", "show", "5396b557fd90a67e0c097da1020959b58724a7ec:.github/workflows/ci.yml"],
        cwd=ROOT,
    ).decode()
    assert (
        workflow.split("  quality-fast:\n")[1].split("  lint:\n")[0]
        == (before.split("  quality-fast:\n")[1].split("  lint:\n")[0])
    )
    assert (
        workflow.split("  semantic-audit-macos:\n")[1].split("  mypy:\n")[0]
        == (before.split("  semantic-audit-macos:\n")[1].split("  mypy:\n")[0])
    )
    aggregate = workflow.split("  code-quality:\n")[1].split("  quality-policy:\n")[0]
    assert "if: always()" in aggregate
    assert "needs: [quality-policy, quality-shards]" in aggregate
    for value in (
        "needs.quality-policy.result",
        "needs.quality-shards.result",
        "steps.reconcile.outcome",
    ):
        assert value + " != 'success'" in aggregate
    assert "python -B -m scripts.quality_evidence" in aggregate
    assert "github.run_attempt" in aggregate
    assert "github.sha" in aggregate
    policy = workflow.split("  quality-policy:\n")[1].split("  quality-shards:\n")[0]
    assert policy.index("scripts.check_performance_policy") < policy.index(
        "scripts.quality_runner run --shard 2"
    )
    assert policy.index("git fetch --no-tags --no-recurse-submodules") < policy.index(
        "scripts.check_performance_policy"
    )
    assert 'uv run --no-sync python -B -m scripts.check_performance_policy "${args[@]}"' in policy
    assert "timeout-minutes: 3" in policy
    assert "timeout-minutes: 10" in policy
    matrix = workflow.split("  quality-shards:\n")[1].split("  semantic-audit-macos:\n")[0]
    assert 'shard: ["1", "3", "4"]' in matrix
    assert "fail-fast: false" in matrix
    for lane in (policy, matrix):
        assert "continue-on-error" not in lane
        assert "fetch-depth: 0" in lane
        assert "4a8fb3c10cbf9c6ce1766f048508b8a16f8f24e8" in lane
        assert "uv sync --locked --no-default-groups --group test" in lane
        assert (
            lane.index("name: Checkout repository")
            < lane.index("name: Set up Python")
            < lane.index("scripts.quality_runner prepare")
            < lane.index("git fetch --no-tags --no-recurse-submodules")
            < lane.index("name: Set up uv")
            < lane.index("uv sync --locked --no-default-groups --group test")
            < lane.index("scripts.quality_runner run")
        )
        assert "retention-days: 30" in lane
        assert "overwrite: false" in lane
        assert "if-no-files-found: error" in lane
        assert "github.run_attempt" in lane
        assert "github.sha" in lane


def test_complete_inventory_preserves_every_ci53_case_and_whole_module() -> None:
    current = evidence.inventory(ROOT)
    baseline = evidence.lines(ROOT / "ci/quality_shards/baseline-ci53.txt")
    assert len(baseline) == 1696
    assert set(baseline) <= set(current["full_all"])
    assert len(current["deferred"]) == 260
    assert set(current["all"]).isdisjoint(current["deferred"])
    assert sorted(current["all"] + current["deferred"]) == current["full_all"]
    modules = current["shards"]["2"]["modules"]
    assert "tests/code_quality/test_performance_policy.py" in modules
    assert runner.Deadlines(570, 585, 590, 595) == runner.DEFAULT_DEADLINES


def test_bootstrap_imports_no_engine_or_performance_admission_helpers() -> None:
    allowed = {
        "__future__",
        "argparse",
        "ast",
        "hashlib",
        "importlib",
        "json",
        "os",
        "platform",
        "shlex",
        "subprocess",
        "sys",
        "time",
        "tomllib",
        "uuid",
        "xml",
        "pathlib",
        "typing",
        "pytest",
        "collections",
        "selectors",
        "shutil",
        "signal",
        "dataclasses",
        "types",
        "scripts",
    }
    for name in ("quality_evidence.py", "quality_reporter.py", "quality_runner.py"):
        tree = ast.parse((ROOT / "scripts" / name).read_bytes())
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                assert all(alias.name.split(".")[0] in allowed for alias in node.names)
            elif isinstance(node, ast.ImportFrom):
                assert node.module is not None
                assert node.module.split(".")[0] in allowed
                assert "performance" not in node.module
                assert "warhammer40k_core" not in node.module


def test_failure_payload_is_synced_before_the_reference(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    journal = evidence.Journal(tmp_path, "execute-gw0", "binding")
    synced: list[Path] = []
    original = evidence.sync_directory

    def sync(path: Path) -> None:
        synced.append(path)
        original(path)

    monkeypatch.setattr(evidence, "sync_directory", sync)
    failure = journal.failure("test", "call", {"traceback": "complete traceback"})
    assert synced == [tmp_path]
    assert (
        evidence.read_json(tmp_path / failure["path"])["payload"]["traceback"]
        == "complete traceback"
    )
    assert journal.path.read_bytes() == b""
    journal.emit("phase_end", node="test", phase="call", failure=failure)
    assert evidence.journal_events(tmp_path, "execute-gw0", "binding")[0]["failure"] == failure


@pytest.mark.parametrize("failure", ["serialization", "disk_full", "directory_sync"])
def test_evidence_write_failure_never_creates_a_referencing_event(
    failure: str,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    journal = evidence.Journal(tmp_path, "execute-gw0", "binding")

    def fail_sync(path: Path) -> None:
        raise OSError(errno.ENOSPC, "injected bounded disk-full control")

    with monkeypatch.context() as scoped:
        payload: Any = {"detail": "complete failure"}
        if failure == "serialization":
            payload = object()
        elif failure == "disk_full":

            def fail_encode(value: Any) -> bytes:
                raise OSError(errno.ENOSPC, "injected bounded payload write failure")

            scoped.setattr(evidence, "encoded", fail_encode)
        else:
            scoped.setattr(evidence, "sync_directory", fail_sync)
        with pytest.raises(evidence.EvidenceError, match="Cannot persist"):
            journal.failure("test", "call", payload)
        assert journal.path.read_bytes() == b""


def test_payload_names_are_exclusive_and_never_overwrite_earlier_failure(tmp_path: Path) -> None:
    target = tmp_path / "failure.json"
    evidence.atomic_json(target, {"first": "original failure"})
    original = target.read_bytes()
    with pytest.raises(evidence.EvidenceError, match="Cannot persist"):
        evidence.atomic_json(target, {"second": "later failure"})
    assert target.read_bytes() == original


def test_complete_dependency_hash_detects_cached_bytecode_and_unlisted_inputs(
    tmp_path: Path,
) -> None:
    package = tmp_path / "site-packages/example"
    package.mkdir(parents=True)
    cached = package / "cached.pyc"
    cached.write_bytes(b"original executable cache")
    original = evidence.physical_dependencies([tmp_path])
    cached.write_bytes(b"changed executable cache")
    assert evidence.physical_dependencies([tmp_path]) != original
    cached.write_bytes(b"original executable cache")
    assert evidence.physical_dependencies([tmp_path]) == original
    (package / "unlisted.py").write_text("VALUE = 1\n")
    assert evidence.physical_dependencies([tmp_path]) != original


def test_ignored_source_and_bytecode_cannot_escape_exact_checkout_admission(tmp_path: Path) -> None:
    (tmp_path / "tests").mkdir()
    (tmp_path / ".gitignore").write_text("tests/ignored*\n")
    (tmp_path / "uv.lock").write_text("version = 1\n")
    (tmp_path / "tests/known.py").write_text("VALUE = 1\n")
    for args in (
        ("init", "-q"),
        ("add", "."),
        (
            "-c",
            "user.name=quality-control",
            "-c",
            "user.email=quality-control@example.invalid",
            "commit",
            "-qm",
            "fixture",
        ),
    ):
        subprocess.run(["git", *args], cwd=tmp_path, check=True, capture_output=True)
    original = evidence.source_identity(tmp_path)
    for name in ("ignored.py", "ignored.pyc"):
        path = tmp_path / "tests" / name
        path.write_bytes(b"unlisted executable input")
        with pytest.raises(evidence.EvidenceError, match="Unlisted source"):
            evidence.source_identity(tmp_path)
        path.unlink()
        assert evidence.source_identity(tmp_path) == original


def test_raw_crlf_checkout_accepts_only_exact_head_bytes_index_modes_and_members(
    tmp_path: Path,
) -> None:
    def git(*arguments: str) -> bytes:
        return subprocess.check_output(
            ["git", "-c", "gc.auto=0", *arguments], cwd=tmp_path, stderr=subprocess.PIPE
        )

    git("init", "-q")
    (tmp_path / ".gitattributes").write_text("*.json text eol=lf\n")
    (tmp_path / "uv.lock").write_text("version = 1\n")
    member = tmp_path / "historical.json"
    original = b'{\r\n  "retained": true\r\n}\r\n'
    member.write_bytes(original)
    git("add", ".gitattributes", "uv.lock")
    oid = git("hash-object", "-w", "--no-filters", "historical.json").decode().strip()
    git("update-index", "--add", "--cacheinfo", "100644", oid, "historical.json")
    git(
        "-c",
        "user.name=quality-control",
        "-c",
        "user.email=quality-control@example.invalid",
        "commit",
        "-qm",
        "raw historical CRLF fixture",
    )
    assert git("status", "--porcelain") == b" M historical.json\n"
    assert git("show", "HEAD:historical.json") == member.read_bytes() == original
    baseline = evidence.source_identity(tmp_path)

    member.write_bytes(original.replace(b"true", b"false"))
    with pytest.raises(evidence.EvidenceError, match="Source bytes differ from HEAD"):
        evidence.source_identity(tmp_path)
    member.write_bytes(original)
    assert evidence.source_identity(tmp_path) == baseline

    member.write_bytes(original.replace(b"true", b"false"))
    git("add", "historical.json")
    member.write_bytes(original)
    with pytest.raises(evidence.EvidenceError, match="Source index differs from HEAD"):
        evidence.source_identity(tmp_path)
    git("update-index", "--cacheinfo", "100644", oid, "historical.json")
    assert evidence.source_identity(tmp_path) == baseline

    mode = member.stat().st_mode
    member.chmod(mode | 0o100)
    with pytest.raises(evidence.EvidenceError, match="Source executable mode differs"):
        evidence.source_identity(tmp_path)
    member.chmod(mode)
    git("update-index", "--chmod=+x", "historical.json")
    with pytest.raises(evidence.EvidenceError, match="Source index differs from HEAD"):
        evidence.source_identity(tmp_path)
    git("update-index", "--cacheinfo", "100644", oid, "historical.json")
    assert evidence.source_identity(tmp_path) == baseline

    extra = tmp_path / "untracked.txt"
    extra.write_text("ordinary untracked source\n")
    with pytest.raises(evidence.EvidenceError, match="untracked members"):
        evidence.source_identity(tmp_path)
    extra.unlink()
    assert evidence.source_identity(tmp_path) == baseline


@pytest.fixture
def execution(tmp_path: Path) -> tuple[Path, list[str]]:
    """A complete causal trace; actual pytest transport is qualified separately."""
    selected = [f"tests/code_quality/test_sample.py::test_{i}" for i in range(4)]
    binding = "expected-binding"
    evidence.Journal(tmp_path, "collect-controller", binding).emit("session_start")
    controller = evidence.Journal(tmp_path, "execute-controller", binding)
    controller.emit("session_start")
    for worker in evidence.WORKERS:
        controller.emit("worker_start", worker=worker, generation=0)
        controller.emit("worker_collection", worker=worker, generation=0, nodes=selected)
    xml = ET.Element("testsuite")
    for worker, node in zip(evidence.WORKERS, selected, strict=True):
        journal = evidence.Journal(tmp_path, "execute-" + worker, binding)
        journal.emit("session_start")
        journal.emit("collection", nodes=selected, deferred=[])
        journal.emit("node_start", node=node)
        for phase in ("setup", "call", "teardown"):
            journal.emit("phase_start", node=node, phase=phase)
            sequence = journal.emit(
                "phase_end", node=node, phase=phase, outcome="passed", wasxfail=False
            )
            controller.emit(
                "mirror",
                worker=worker,
                origin_sequence=sequence,
                node=node,
                phase=phase,
                outcome="passed",
                wasxfail=False,
            )
        journal.emit("node_end", node=node)
        journal.active("", "idle")
        journal.emit("session_finish", exit_status=0)
        controller.emit("worker_end", worker=worker, error=None, generation=0)
        case = ET.SubElement(xml, "testcase")
        properties = ET.SubElement(case, "properties")
        ET.SubElement(properties, "property", name="quality_nodeid", value=node)
    controller.emit("session_finish", exit_status=0)
    guard = evidence.Journal(tmp_path, "watchdog", binding)
    guard.emit(
        "watchdog_start", deadlines={"interrupt": 570, "terminate": 585, "kill": 590, "reap": 595}
    )
    for group in (100, 101):
        guard.emit("group", pgid=group)
        guard.emit("closed", pgid=group)
    guard.emit("watchdog_end", exit_status=0)
    (tmp_path / "junit.xml").write_bytes(ET.tostring(xml))
    return tmp_path, selected


def test_complete_execution_requires_teardown_and_exact_controller_mirrors(
    execution: tuple[Path, list[str]],
) -> None:
    directory, selected = execution
    evidence.validate_execution(directory, "expected-binding", selected)


@pytest.mark.parametrize(
    "mutation",
    [
        "setup_failure",
        "call_failure",
        "teardown_failure",
        "skip",
        "xfail",
        "xpass",
        "missing_teardown",
        "duplicate_phase",
        "unstarted",
        "wrong_binding",
        "tail",
        "sequence_gap",
        "missing_worker",
        "worker_restart",
        "wrong_mirror",
        "watchdog_timeout",
        "missing_active",
        "missing_case",
        "wrong_junit",
    ],
)
def test_incomplete_failed_or_mixed_execution_never_passes(
    mutation: str,
    execution: tuple[Path, list[str]],
) -> None:
    directory, selected = execution
    path = directory / "execute-gw0.jsonl"
    events = [json.loads(line) for line in path.read_bytes().splitlines()]
    if mutation == "missing_worker":
        path.unlink()
    elif mutation == "missing_active":
        (directory / "execute-gw0-active.json").unlink()
    elif mutation == "missing_case":
        selected = [*selected, "tests/code_quality/test_sample.py::unstarted"]
    elif mutation == "wrong_junit":
        (directory / "junit.xml").write_text("<testsuite><testcase/></testsuite>")
    else:
        if mutation in {"worker_restart", "wrong_mirror"}:
            path = directory / "execute-controller.jsonl"
            events = [json.loads(line) for line in path.read_bytes().splitlines()]
            if mutation == "worker_restart":
                events.insert(-1, copy.deepcopy(events[1]))
            else:
                next(e for e in events if e["kind"] == "mirror")["origin_sequence"] += 1
        elif mutation == "watchdog_timeout":
            path = directory / "watchdog.jsonl"
            events = [json.loads(line) for line in path.read_bytes().splitlines()]
            events[-1]["exit_status"] = 1
        elif mutation.endswith("_failure"):
            phase = mutation.removesuffix("_failure")
            next(e for e in events if e["kind"] == "phase_end" and e["phase"] == phase)[
                "outcome"
            ] = "failed"
        elif mutation in {"skip", "xfail", "xpass"}:
            event = next(e for e in events if e["kind"] == "phase_end" and e["phase"] == "call")
            event["outcome"] = "passed" if mutation == "xpass" else "skipped"
            event["wasxfail"] = mutation != "skip"
        elif mutation == "missing_teardown":
            events = [e for e in events if e.get("phase") != "teardown"]
        elif mutation == "duplicate_phase":
            events.insert(4, copy.deepcopy(events[3]))
        elif mutation == "unstarted":
            events = [*events[:2], events[-1]]
        elif mutation == "wrong_binding":
            events[0]["binding"] = "stale-attempt"
        for sequence, event in enumerate(events, 1):
            event["sequence"] = sequence
        if mutation == "sequence_gap":
            events[-1]["sequence"] += 1
        raw = b"".join(evidence.encoded(e) for e in events)
        path.write_bytes(raw[:-1] if mutation == "tail" else raw)
    with pytest.raises((evidence.EvidenceError, FileNotFoundError)):
        evidence.validate_execution(directory, "expected-binding", selected)


@pytest.fixture
def lane(
    execution: tuple[Path, list[str]],
) -> tuple[Path, dict[str, Any], dict[str, str], dict[str, Any]]:
    """A valid transport admission fixture, separate from real CLI process controls."""
    import tomllib

    directory, selected = execution
    expected = {
        "mode": "local",
        "repository": "owner/repository",
        "repository_id": "1",
        "workflow_ref": "owner/repository/.github/workflows/ci.yml@refs/heads/main",
        "run_id": "1",
        "run_attempt": "1",
        "event": "push",
        "checkout": "a" * 40,
        "tree": "b" * 40,
        "pr_head": "",
        "base": "c" * 40,
    }
    start = {
        "schema": evidence.SCHEMA,
        "context": expected,
        "shard": "4",
        "shard_count": 4,
        "workers": evidence.WORKERS,
        "producer": "quality-shards",
    }
    binding = evidence.sha(evidence.encoded(start))
    configuration = tomllib.loads((ROOT / "pyproject.toml").read_text())["tool"]["pytest"][
        "ini_options"
    ]
    import shlex

    ini = {
        "addopts": shlex.split(configuration["addopts"]),
        "markers": configuration["markers"],
        "testpaths": configuration["testpaths"],
    }
    inventories: dict[str, Any] = {
        "all": sorted(selected),
        "full_all": sorted(selected),
        "deferred": [],
        "shards": {
            "4": {
                "nodes": selected,
                "deferred": [],
                "modules": ["tests/code_quality/test_sample.py"],
            }
        },
    }
    source = {
        "checkout": expected["checkout"],
        "tree": expected["tree"],
        "sha256": "source",
        "lock": "lock",
    }
    scratch = directory / "scratch"
    output_directory = ROOT / "reports/quality-timing/fixture-producer"
    commands = {
        mode: evidence.pytest_arguments(
            inventories["shards"]["4"], output_directory, scratch / mode, collect=mode == "collect"
        )
        for mode in ("collect", "execute")
    }
    dependencies: dict[str, Any] = {
        "python": "3.14.5",
        "executable": "binary",
        "physical_sha256": "physical",
        "distributions": {},
        "plugins": [],
    }
    admitted: dict[str, Any] = {
        "binding": binding,
        "source": source,
        "dependencies": dependencies,
        "inventory": inventories,
        "commands": commands,
        "output_directory": str(output_directory),
        "environment": {
            "PYTHONDONTWRITEBYTECODE": "1",
            "XDG_CACHE_HOME": str(scratch / "cache"),
            "HYPOTHESIS_STORAGE_DIRECTORY": str(scratch / "hypothesis"),
            "project_origin": str(ROOT / "src/warhammer40k_core/__init__.py"),
        },
        "scratch": str(scratch),
        "config": evidence.sha((ROOT / "pyproject.toml").read_bytes()),
        "resources": {"effective_cores": 4, "affinity": [0, 1, 2, 3]},
        "performance": None,
    }
    evidence.atomic_json(directory / "start.json", start)
    evidence.atomic_json(directory / "admitted.json", admitted)
    evidence.atomic_json(
        directory / "supervisor.json",
        {
            "binding": binding,
            "state": "completed",
            "exit_status": 0,
            "signals": [],
            "source_after": source,
            "dependencies_after": dependencies,
            "children_reaped": True,
        },
    )
    for path in directory.glob("*.jsonl"):
        events = [json.loads(line) for line in path.read_bytes().splitlines()]
        mode = "collect" if path.name.startswith("collect-") else "execute"
        for event in events:
            event["binding"] = binding
            if event["kind"] == "collection":
                event["deferred"] = []
            if event["kind"] == "session_start":
                event.update(
                    args=commands[mode][4:], plugins=[], ini=copy.deepcopy(ini), generation=0
                )
        if mode == "collect":
            header = {key: events[0][key] for key in ("schema", "binding", "role", "monotonic")}
            events += [
                {
                    **header,
                    "kind": "collection",
                    "sequence": 2,
                    "nodes": sorted(selected),
                    "deferred": [],
                },
                {**header, "kind": "session_finish", "sequence": 3, "exit_status": 0},
            ]
        path.write_bytes(b"".join(evidence.encoded(event) for event in events))
    for path in directory.glob("*-active.json"):
        value = evidence.read_json(path)
        value["binding"] = binding
        evidence.atomic_json(path, value, replace=True)
    for mode, command in commands.items():
        (directory / (mode + ".log")).write_text("complete original raw output\n")
        evidence.atomic_json(
            directory / (mode + "-process.json"),
            {"command": command, "exit_status": 0, "elapsed": 1.0},
        )
    return directory, expected, source, inventories


def test_complete_lane_admission_requires_authoritative_context_and_invocation(
    lane: tuple[Path, dict[str, Any], dict[str, str], dict[str, Any]],
) -> None:
    directory, expected, source, inventories = lane
    assert (
        evidence.validate_lane(directory, expected, source, inventories, "4", ROOT)["source"]
        == source
    )
    wrong_base = copy.deepcopy(expected)
    wrong_base["base"] = "d" * 40
    with pytest.raises(evidence.EvidenceError, match="Wrong producer/run/attempt/head/shard"):
        evidence.validate_lane(directory, wrong_base, source, inventories, "4", ROOT)


@pytest.mark.parametrize(
    "mutation",
    [
        "argv",
        "config",
        "plugins",
        "generation",
        "markers",
        "head",
        "attempt",
        "producer",
        "source",
        "dependency_drift",
        "missing_log",
        "insufficient_cpu",
    ],
)
def test_lane_admission_rejects_wrong_identity_configuration_and_missing_evidence(
    mutation: str,
    lane: tuple[Path, dict[str, Any], dict[str, str], dict[str, Any]],
) -> None:
    directory, expected, source, inventories = lane
    name = "admitted.json"
    if mutation in {"head", "attempt", "producer"}:
        name = "start.json"
    elif mutation == "dependency_drift":
        name = "supervisor.json"
    if mutation in {"plugins", "generation", "markers"}:
        path = directory / "execute-gw0.jsonl"
        rows = [json.loads(line) for line in path.read_bytes().splitlines()]
        if mutation == "plugins":
            rows[0]["plugins"] = [["unapproved-plugin", "1"]]
        elif mutation == "generation":
            rows[0]["generation"] = 1
        else:
            rows[0]["ini"]["markers"].append("unapproved: marker drift")
        path.write_bytes(b"".join(evidence.encoded(row) for row in rows))
    elif mutation == "missing_log":
        (directory / "execute.log").unlink()
    else:
        value = evidence.read_json(directory / name)
        if mutation == "argv":
            value["commands"]["execute"].append("--runxfail")
        elif mutation == "config":
            value["config"] = "wrong configuration"
        elif mutation == "head":
            value["context"]["checkout"] = "d" * 40
        elif mutation == "attempt":
            value["context"]["run_attempt"] = "2"
        elif mutation == "producer":
            value["producer"] = "quality-policy"
        elif mutation == "source":
            value["source"]["sha256"] = "wrong source"
        elif mutation == "dependency_drift":
            value["dependencies_after"]["physical_sha256"] = "changed bytecode"
        else:
            value["resources"]["effective_cores"] = 2
        evidence.atomic_json(directory / name, value, replace=True)
    with pytest.raises((evidence.EvidenceError, FileNotFoundError)):
        evidence.validate_lane(directory, expected, source, inventories, "4", ROOT)


@pytest.mark.parametrize("result", ["failure", "cancelled", "skipped", ""])
def test_aggregate_rejects_every_unsuccessful_upstream_result(result: str, tmp_path: Path) -> None:
    for producer in ("quality-policy", "quality-shards"):
        results = {"quality-policy": "success", "quality-shards": "success"}
        results[producer] = result
        with pytest.raises(evidence.EvidenceError, match="Required quality producers"):
            evidence.reconcile(ROOT, tmp_path, {}, results)


def test_missing_or_stale_upload_cannot_be_accepted(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    lane: tuple[Path, dict[str, Any], dict[str, str], dict[str, Any]],
) -> None:
    _, expected, source, inventories = lane

    def fixed_source(root: Path) -> dict[str, str]:
        return source

    def fixed_inventory(root: Path) -> dict[str, Any]:
        return inventories

    monkeypatch.setattr(evidence, "source_identity", fixed_source)
    monkeypatch.setattr(evidence, "inventory", fixed_inventory)
    for shard in ("1", "2", "3"):
        (tmp_path / evidence.artifact_name(expected, shard)).mkdir()
    with pytest.raises(evidence.EvidenceError, match="Missing/duplicate/stale artifacts"):
        evidence.reconcile(
            ROOT, tmp_path, expected, {"quality-policy": "success", "quality-shards": "success"}
        )
    (tmp_path / "quality-from-previous-attempt").mkdir()
    with pytest.raises(evidence.EvidenceError, match="Missing/duplicate/stale artifacts"):
        evidence.reconcile(
            ROOT, tmp_path, expected, {"quality-policy": "success", "quality-shards": "success"}
        )


def test_missing_files_cannot_disappear_from_the_uploaded_seal(tmp_path: Path) -> None:
    (tmp_path / "original.log").write_text("full failure")
    evidence.seal(tmp_path)
    evidence.verify_seal(tmp_path)
    (tmp_path / "original.log").unlink()
    with pytest.raises(evidence.EvidenceError, match="Artifact file inventory/hash"):
        evidence.verify_seal(tmp_path)


@pytest.fixture
def performance_receipt(tmp_path: Path) -> tuple[Path, dict[str, Any], dict[str, str], Path]:
    """Small real Git inputs and a typed receipt fixture for fan-in admission."""
    root = tmp_path / "checkout"
    files = {
        "scripts/performance_smoke.py": (ROOT / "scripts/performance_smoke.py").read_bytes(),
        "docs/performance/change-assessment.json": b"{}\n",
        "docs/performance/policy-v3/operation-map.json": b"{}\n",
        "src/warhammer40k_core/_engine_build_manifest.json": b'{"build_id":"fixture-runtime"}\n',
        "uv.lock": b"version = 1\n",
        "pyproject.toml": b"",
    }
    for name, raw in files.items():
        target = root / name
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(raw)
    for args in (
        ("init", "-q"),
        ("add", "."),
        (
            "-c",
            "user.name=quality-control",
            "-c",
            "user.email=quality-control@example.invalid",
            "commit",
            "-qm",
            "fixture",
        ),
    ):
        subprocess.run(["git", *args], cwd=root, check=True, capture_output=True)
    expected = {
        "checkout": evidence.git(root, "rev-parse", "HEAD"),
        "base": "c" * 40,
        "pr_head": "",
    }
    inputs = {
        name: evidence.sha(raw)
        for name, raw in files.items()
        if name != "docs/performance/change-assessment.json"
    }
    report = {
        "inputs_unchanged": True,
        "status": "passed",
        "checkout_head": expected["checkout"],
        "base_revision": expected["base"],
        "pull_request_head": None,
        "attempt_receipt": str(root / "reports/performance-attempts/attempt-1/receipt.json"),
        "workload": "current-runtime-smoke-v1",
        "case_limit_seconds": 60.0,
        "process_limit_seconds": 180.0,
        "total_seconds": 1.0,
        "cases": [
            {
                "case": case,
                "exit_code": 0,
                "timed_out": False,
                "process_seconds": 0.4,
                "result": {"case": case, "complete": True},
            }
            for case in ("associated-woods-queries", "ingress-facade-restore-view-fork-replay")
        ],
        "assessment_sha256": evidence.sha(files["docs/performance/change-assessment.json"]),
        "inputs": inputs,
        "runtime_build_id": "fixture-runtime",
        "input_digest": evidence.sha(
            json.dumps(inputs, sort_keys=True, separators=(",", ":")).encode()
        ),
    }
    directory = tmp_path / "download"
    attempt = directory / "performance/performance-attempts/attempt-1"
    attempt.mkdir(parents=True)
    evidence.atomic_json(directory / "performance/performance-smoke.json", report)
    evidence.atomic_json(attempt / "receipt.json", report)
    admitted = {
        "output_directory": str(root / "reports/quality-timing/producer"),
        "performance": {"sha256": evidence.sha(evidence.encoded(report))},
    }
    return directory, admitted, expected, root


def test_preserved_performance_receipt_is_validated_without_running_engine_admission(
    performance_receipt: tuple[Path, dict[str, Any], dict[str, str], Path],
) -> None:
    evidence.validate_performance(*performance_receipt)


@pytest.mark.parametrize(
    "mutation",
    [
        "status",
        "head",
        "base",
        "attempt_path",
        "attempt_bytes",
        "receipt_hash",
        "limit",
        "case_missing",
        "case_incomplete",
        "source_membership",
        "input_digest",
    ],
)
def test_performance_receipt_rejects_stale_failed_missing_and_relabelled_attempts(
    mutation: str,
    performance_receipt: tuple[Path, dict[str, Any], dict[str, str], Path],
) -> None:
    directory, admitted, expected, root = performance_receipt
    path = directory / "performance/performance-smoke.json"
    report = evidence.read_json(path)
    if mutation == "status":
        report["status"] = "failed"
    elif mutation == "head":
        report["checkout_head"] = "d" * 40
    elif mutation == "base":
        report["base_revision"] = "d" * 40
    elif mutation == "attempt_path":
        report["attempt_receipt"] = "/unrelated/attempt/receipt.json"
    elif mutation == "attempt_bytes":
        (directory / "performance/performance-attempts/attempt-1/receipt.json").write_text("{}")
    elif mutation == "receipt_hash":
        admitted["performance"]["sha256"] = "wrong receipt bytes"
    elif mutation == "limit":
        report["process_limit_seconds"] = 181
    elif mutation == "case_missing":
        report["cases"].pop()
    elif mutation == "case_incomplete":
        report["cases"][0]["result"]["complete"] = False
    elif mutation == "source_membership":
        report["inputs"].pop("pyproject.toml")
    else:
        report["input_digest"] = "wrong input digest"
    if mutation not in {"attempt_bytes", "receipt_hash"}:
        evidence.atomic_json(path, report, replace=True)
        evidence.atomic_json(
            directory / "performance/performance-attempts/attempt-1/receipt.json",
            report,
            replace=True,
        )
        admitted["performance"]["sha256"] = evidence.sha(path.read_bytes())
    with pytest.raises(evidence.EvidenceError):
        evidence.validate_performance(directory, admitted, expected, root)


class _PreflightBatchProbe(Protocol):
    def _git(self, root: Path, *args: str, payload: bytes | None = None) -> bytes: ...

    def _blobs(self, root: Path, revision: str, names: list[str]) -> dict[str, bytes]: ...

    def _freeze(self, root: Path) -> str: ...

    def git_function(self) -> Callable[..., bytes]:
        return self._git

    def blobs_function(self) -> Callable[[Path, str, list[str]], dict[str, bytes]]:
        return self._blobs

    def freeze(self, root: Path) -> str:
        return self._freeze(root)


def test_predecessor_borrowing_matches_five_real_fallbacks_and_rejects_wrong_roles(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from tools import performance_preflight_successor as stage
    from tools import quality_runtime_successor as successor

    names = sorted(successor.BORROWED_PREDECESSORS)
    expected = {
        ".github/workflows/ci.yml",
        "docs/CORE_RULES_REMEDIATION_ROADMAP.md",
        "tests/code_quality/test_ci_history_input.py",
        "tests/code_quality/test_ci_runtime_successor.py",
        "tools/performance_policy.py",
    }
    fixture = "tests/code_quality/test_performance_preflight.py"
    assert set(names) == expected
    assert stage.PINS.keys() & successor.BEFORE.keys() == expected | {fixture}
    assert fixture not in successor.BORROWED_PREDECESSORS
    assert len(names) == 5
    assert stage.FREEZE_COMMIT is not None
    frozen = stage.read_frozen_blobs(ROOT, stage.FREEZE_COMMIT, names)
    original_git = successor.git
    calls: list[tuple[str, ...]] = []

    def counted(root: Path, *args: str) -> bytes:
        calls.append(args)
        return original_git(root, *args)

    monkeypatch.setattr(successor, "git", counted)
    current = {name: successor.owned(ROOT, name) for name in names}
    fallback = {name: successor.previous(ROOT, name, current[name]) for name in names}
    assert calls == [("show", successor.BASE + ":" + name) for name in names]
    assert fallback == frozen
    calls.clear()
    for name in names:
        assert successor.digest(frozen[name]) == stage.PINS[name] == successor.BEFORE[name]
        assert (
            successor.previous(ROOT, name, current[name], predecessor=frozen[name])
            == fallback[name]
        )
        for wrong in (b"", frozen[name] + b" ", frozen[names[(names.index(name) + 1) % 5]]):
            with pytest.raises(ValueError, match="immutable predecessor changed"):
                successor.previous(ROOT, name, current[name], predecessor=wrong)
        with pytest.raises(ValueError, match="caller supplied unrelated bytes"):
            successor.previous(ROOT, name, current[name] + b" ", predecessor=frozen[name])
    for role in (successor.SELF, successor.ASSESSMENT, stage.SELF, "unsupported/path"):
        with pytest.raises(ValueError, match="borrowing is not admitted"):
            successor.previous(ROOT, role, b"caller", predecessor=frozen[names[0]])
    assert successor.previous(ROOT, "unsupported/path", b"caller") == b"caller"
    with monkeypatch.context() as changed:
        changed.setitem(stage.PINS, names[0], "0" * 64)
        with pytest.raises(ValueError, match="borrowing is not admitted"):
            successor.previous(ROOT, names[0], current[names[0]], predecessor=frozen[names[0]])
    assert calls == []
    print("CI54 borrowed predecessor retrieval: five fallback Git shows; zero borrowed Git shows.")
    print("The caller's existing authenticated frozen-member batch is outside this count.")


def test_predecessor_borrowing_revalidates_distinct_roots_and_warm_same_size_mutation(
    tmp_path: Path,
) -> None:
    from tools import performance_preflight as preflight
    from tools import quality_runtime_successor as successor

    name = "tests/code_quality/test_ci_history_input.py"
    current = successor.owned(ROOT, name)
    predecessor = successor.git(ROOT, "show", successor.BASE + ":" + name)
    roots = [tmp_path / "first", tmp_path / "second"]
    for root in roots:
        target = root / name
        target.parent.mkdir(parents=True)
        target.write_bytes(current)
        for args in (
            ("init", "-q"),
            ("add", "."),
            (
                "-c",
                "user.name=quality-control",
                "-c",
                "user.email=quality-control@example.invalid",
                "commit",
                "-qm",
                "owned current member fixture",
            ),
        ):
            subprocess.run(
                ["git", "-c", "gc.auto=0", *args], cwd=root, check=True, capture_output=True
            )

    @preflight.invocation
    def admitted(root: Path, supplied: bytes, old: bytes) -> bytes:
        return successor.previous(root, name, supplied, predecessor=old)

    for root in roots:
        assert admitted(root, current, predecessor) == predecessor
        target = root / name
        metadata = target.stat()
        changed = bytes([current[0] ^ 1]) + current[1:]
        assert len(changed) == len(current)
        assert changed != current
        target.write_bytes(changed)
        os.utime(target, ns=(metadata.st_atime_ns, metadata.st_mtime_ns))
        for supplied in (current, changed):
            with pytest.raises(ValueError, match="Preflight source changed"):
                admitted(root, supplied, predecessor)
        target.write_bytes(current)
        os.utime(target, ns=(metadata.st_atime_ns, metadata.st_mtime_ns))
        assert admitted(root, current, predecessor) == predecessor
        with pytest.raises(ValueError, match="immutable predecessor changed"):
            admitted(root, current, predecessor + b" ")
        assert admitted(root, current, predecessor) == predecessor
    alias = tmp_path / "alias"
    alias.symlink_to(roots[0], target_is_directory=True)
    with pytest.raises(ValueError, match="owned regular file"):
        admitted(alias, current, predecessor)
    with pytest.raises(FileNotFoundError):
        admitted(tmp_path / "absent", current, predecessor)
    assert admitted(roots[1], current, predecessor) == predecessor


def test_measurement_batch_matches_literal_projection_and_reads_each_invocation(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from tools import performance_policy as policy
    from tools import performance_preflight as preflight
    from tools import performance_preflight_successor as stage
    from tools import quality_runtime_successor as successor
    from tools import thousand_sons_perils_preservation as perils

    probe = cast(_PreflightBatchProbe, stage)
    direct_git = _PreflightBatchProbe.git_function(probe)
    direct_blobs = _PreflightBatchProbe.blobs_function(probe)
    current = policy.runtime_inputs(ROOT)
    projected_current = successor.measurement_inputs(ROOT, current)
    controls = (
        (
            stage.PINS.keys()
            - {
                stage.INVENTORY,
                stage.STATIC_RECORD,
                stage.CI_RECORD,
                stage.CI_FORMAT_RECORD,
                stage.CI_COMPAT_RECORD,
                stage.CI_TRANSPORT_RECORD,
                stage.CI_RUNTIME_RECORD,
                stage.CI_ROADMAP,
                stage.CI_WORKFLOW,
            }
        )
        | stage.ANCHORS.keys()
        | {stage.SELF}
    )
    prior = set(direct_git(ROOT, "ls-tree", "-r", "--name-only", stage.BASE).decode().splitlines())
    requested = [name for name in sorted(controls) if name in prior] + sorted(perils.CHANGED)
    assert len(requested) == 24
    literal = {name: direct_git(ROOT, "show", stage.BASE + ":" + name) for name in requested}
    expected = dict(projected_current)
    for name in controls:
        actual = successor.previous(ROOT, name, successor.owned(ROOT, name))
        assert projected_current[name] == evidence.sha(actual)
        if name in prior:
            expected[name] = evidence.sha(literal[name])
        else:
            del expected[name]
    for name in perils.CHANGED:
        assert expected.get(name) == evidence.sha(literal[name])
        if name in {perils.SELF, perils.GUARD}:
            del expected[name]
        elif name == perils.TEST:
            expected[name] = evidence.sha(
                perils.preceding_test(ROOT, name, successor.owned(ROOT, name))
            )
        else:
            expected[name] = evidence.sha(
                perils.preceding_control(ROOT, name, successor.owned(ROOT, name))
            )

    selected = sorted(set(requested))
    batches: list[tuple[Path, str, list[str]]] = []
    retrievals: list[tuple[str, ...]] = []
    in_measurement_batch = False

    def counted_git(root: Path, *args: str, payload: bytes | None = None) -> bytes:
        if in_measurement_batch:
            retrievals.append(args)
        return direct_git(root, *args, payload=payload)

    def counted_blobs(root: Path, revision: str, names: list[str]) -> dict[str, bytes]:
        nonlocal in_measurement_batch
        targeted = revision == stage.BASE and names == selected
        if targeted:
            batches.append((root, revision, list(names)))
        previous = in_measurement_batch
        in_measurement_batch = targeted
        try:
            result = direct_blobs(root, revision, names)
        finally:
            in_measurement_batch = previous
        if targeted:
            assert result == literal
        return result

    monkeypatch.setattr(stage, "_git", counted_git)
    monkeypatch.setattr(stage, "_blobs", counted_blobs)

    @preflight.invocation
    def project(inputs: dict[str, str]) -> dict[str, str]:
        return stage.measurement_inputs(ROOT, inputs)

    assert project(current) == expected
    assert project(dict(reversed(list(current.items())))) == expected
    assert batches == [(ROOT, stage.BASE, selected), (ROOT, stage.BASE, selected)]
    assert len(retrievals) == 4
    assert retrievals[0] == retrievals[2]
    assert retrievals[1] == retrievals[3] == ("cat-file", "--batch")
    bad = dict(current)
    bad[stage.SELF] = "0" * 64
    with pytest.raises(ValueError, match="actual input collector"):
        project(bad)
    assert len(retrievals) == 4
    assert project(current) == expected
    assert len(retrievals) == 6
    print(
        "CI54 measurement historical projection: 24 literal Git shows versus two batch Git calls."
    )
    print("Three successful independent invocations each reread the exact canonical member union.")
    print("Counts exclude unchanged ancestry, source admission, prior ls-tree and Perils checks.")


def test_complete_preflight_freeze_forwards_only_five_authenticated_members(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from tools import performance_preflight_successor as stage
    from tools import quality_runtime_successor as successor

    assert stage.FREEZE_COMMIT is not None
    names = sorted(successor.BORROWED_PREDECESSORS)
    frozen = stage.read_frozen_blobs(ROOT, stage.FREEZE_COMMIT, names)
    actual = {name: successor.owned(ROOT, name) for name in names}
    original_previous = successor.previous
    original_git = successor.git
    original_admit = successor.admit
    admissions: list[Path] = []

    def counted_admit(root: Path) -> None:
        admissions.append(root)
        original_admit(root)

    borrowed: list[str] = []
    fallback_shows: list[tuple[str, ...]] = []

    def counted_previous(
        root: Path, name: str, supplied: bytes, *, predecessor: bytes | None = None
    ) -> bytes:
        if predecessor is not None:
            assert root == ROOT
            assert name in names
            assert supplied == actual[name]
            assert predecessor == frozen[name]
            borrowed.append(name)
        return original_previous(root, name, supplied, predecessor=predecessor)

    def counted_git(root: Path, *args: str) -> bytes:
        if (
            len(args) == 2
            and args[0] == "show"
            and args[1] in {successor.BASE + ":" + name for name in names}
        ):
            fallback_shows.append(args)
        return original_git(root, *args)

    monkeypatch.setattr(successor, "admit", counted_admit)
    monkeypatch.setattr(successor, "previous", counted_previous)
    monkeypatch.setattr(successor, "git", counted_git)
    probe = cast(_PreflightBatchProbe, stage)
    assert _PreflightBatchProbe.freeze(probe, ROOT) == stage.FREEZE_COMMIT
    assert admissions == [ROOT]
    assert sorted(borrowed) == names
    assert fallback_shows == []
    assert {name: successor.owned(ROOT, name) for name in names} == actual
    print(
        "CI54 complete preflight freeze: five authenticated borrowed members; zero redundant shows."
    )


def test_fixture_compatibility_view_requires_fresh_authentic_module_owned_checkout(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from tools import performance_ci60_qualification as ci60
    from tools import performance_preflight_successor as stage
    from tools import quality_runtime_successor as successor

    original_admit = ci60.historical_ci54_admission(ROOT)
    historical_members = ci60.control_projection(ROOT)
    read = successor.owned

    def historical_owned(r: Path, n: str) -> bytes:
        return historical_members.get(n, read(r, n)) if r == ROOT else read(r, n)

    monkeypatch.setattr(successor, "owned", historical_owned)
    original_previous = successor.previous
    admissions: list[Path] = []
    projections: list[tuple[Path, str, bytes | None]] = []

    def counted_admit(root: Path) -> None:
        admissions.append(root)
        original_admit(root)

    def counted_previous(
        root: Path, name: str, supplied: bytes, *, predecessor: bytes | None = None
    ) -> bytes:
        projections.append((root, name, predecessor))
        return original_previous(root, name, supplied, predecessor=predecessor)

    monkeypatch.setattr(successor, "admit", counted_admit)
    monkeypatch.setattr(successor, "previous", counted_previous)
    name = "tests/code_quality/test_performance_preflight.py"
    record = json.loads((ROOT / stage.CI_COMPAT_RECORD).read_bytes())
    row = record["changes"][name]
    before = subprocess.check_output(["git", "show", stage.CI_COMPAT_BASE + ":" + name], cwd=ROOT)
    historical = subprocess.check_output(["git", "show", successor.BASE + ":" + name], cwd=ROOT)
    current = successor.owned(ROOT, name)
    assert evidence.sha(historical) == row["after_sha256"] == successor.BEFORE[name]
    assert evidence.sha(current) == successor.PINS[name]
    assert current != historical
    stage.assert_ci_compatibility_transition(name, before, historical, row)
    assert admissions == []
    assert projections == []
    stage.assert_ci_compatibility_transition(name, before, current, row)
    assert admissions == [ROOT]
    assert projections == [(ROOT, name, None)]

    owned_root = tmp_path / "owned"
    for member in successor.PINS.keys() | {successor.SELF, successor.ASSESSMENT}:
        target = owned_root / member
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(historical_members.get(member, successor.owned(ROOT, member)))
    git_directory = (
        subprocess.check_output(["git", "rev-parse", "--absolute-git-dir"], cwd=ROOT)
        .decode()
        .strip()
    )
    (owned_root / ".git").write_text("gitdir: " + git_directory + "\n")
    monkeypatch.setattr(stage, "__file__", str(owned_root / stage.SELF))
    stage.assert_ci_compatibility_transition(name, before, current, row)
    assert admissions == [ROOT, owned_root]
    assert projections == [(ROOT, name, None), (owned_root, name, None)]

    bad_rows = [copy.deepcopy(row) for _ in range(3)]
    bad_rows[0]["before_sha256"] = "0" * 64
    bad_rows[1]["after_sha256"] = evidence.sha(current)
    bad_rows[2]["edits"][0]["after"] += "\n# unrelated edit\n"
    for bad_row in bad_rows:
        with pytest.raises(ValueError, match="CI transition"):
            stage.assert_ci_compatibility_transition(name, before, current, bad_row)
    with pytest.raises(ValueError, match="CI transition"):
        stage.assert_ci_compatibility_transition(name, before + b" ", current, row)
    for unrelated in (b"unrelated", current + b" "):
        with pytest.raises(ValueError, match="CI transition"):
            stage.assert_ci_compatibility_transition(name, before, unrelated, row)
    with pytest.raises(ValueError, match="CI transition"):
        stage.assert_ci_compatibility_transition(
            "tests/code_quality/__init__.py", before, current, row
        )

    target = owned_root / name
    metadata = target.stat()
    changed = bytes([current[0] ^ 1]) + current[1:]
    assert len(changed) == len(current)
    assert changed != current
    target.write_bytes(changed)
    os.utime(target, ns=(metadata.st_atime_ns, metadata.st_mtime_ns))
    with pytest.raises(ValueError, match="Preflight source changed"):
        stage.assert_ci_compatibility_transition(name, before, current, row)
    with pytest.raises(ValueError, match="CI transition"):
        stage.assert_ci_compatibility_transition(name, before, changed, row)
    changed_row = copy.deepcopy(row)
    changed_row["after_sha256"] = evidence.sha(changed)
    with pytest.raises(ValueError, match="outside the exact reviewed edits"):
        stage.assert_ci_compatibility_transition(name, before, changed, changed_row)
    target.write_bytes(current)
    os.utime(target, ns=(metadata.st_atime_ns, metadata.st_mtime_ns))
    stage.assert_ci_compatibility_transition(name, before, current, row)

    monkeypatch.setattr(stage, "__file__", str(tmp_path / "absent/tools/module.py"))
    admission_count, projection_count = len(admissions), len(projections)
    stage.assert_ci_compatibility_transition(name, before, historical, row)
    assert len(admissions) == admission_count
    assert len(projections) == projection_count
    with pytest.raises(FileNotFoundError):
        stage.assert_ci_compatibility_transition(name, before, current, row)
    assert len(admissions) == admission_count + 1
    assert len(projections) == projection_count
    print("CI54 current fixture view: one fresh admission and one native projection per positive.")
    print("Historical raw view: zero current admissions; failed current admission never projects.")


def test_history_snapshot_preimages_extend_only_existing_native_bridge(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from tools import performance_ci60_qualification as ci60
    from tools import quality_runtime_successor as ci54

    projection = ci60.control_projection(ROOT)
    current_read = ci54.owned

    def historical_read(root: Path, name: str) -> bytes:
        assert root == ROOT
        return projection[name] if name in projection else current_read(root, name)

    # Original assertion bodies run on the authenticated CI54 control context.
    # The actual current source is independently admitted before this view exists.
    with monkeypatch.context() as historical_context:
        historical_context.setattr(ci54, "owned", historical_read)
        from tools import performance_preflight_successor as stage
        from tools import quality_runtime_successor as successor

        assert not successor.BEFORE.keys() & successor.SNAPSHOT_BEFORE.keys()
        assert successor.SNAPSHOT_BEFORE.keys() <= successor.PINS.keys()
        assert not successor.SNAPSHOT_BEFORE.keys() & successor.BORROWED_PREDECESSORS
        assert stage.PINS.keys() & successor.BEFORE.keys() == successor.BORROWED_PREDECESSORS | {
            "tests/code_quality/test_performance_preflight.py"
        }
        for name, pin in successor.SNAPSHOT_BEFORE.items():
            old = subprocess.check_output(["git", "show", successor.BASE + ":" + name], cwd=ROOT)
            assert evidence.sha(old) == pin
            actual = successor.owned(ROOT, name)
            assert evidence.sha(actual) == successor.PINS[name]
            assert successor.previous(ROOT, name, actual) == old
            with pytest.raises(ValueError, match="borrowing is not admitted"):
                successor.previous(ROOT, name, actual, predecessor=old)
            with pytest.raises(ValueError, match="unrelated bytes"):
                successor.previous(ROOT, name, actual + b" ")
        successor.admit(ROOT)

    ci54.admit(ROOT)
    for name in ci54.SNAPSHOT_BEFORE:
        live = current_read(ROOT, name)
        assert ci54.previous(ROOT, name, live) == ci54.git(ROOT, "show", ci54.BASE + ":" + name)


def test_history_complete_current_protocol_resolves_every_actual_consumer(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from scripts import check_performance_policy as gate
    from tools import performance_history_snapshot
    from tools import quality_runtime_successor as successor

    history = performance_history_snapshot
    original = history.historical
    original_blobs = history.eligible_blobs
    queries: set[tuple[str, tuple[str, ...]]] = set()
    blob_queries: set[tuple[str, str]] = set()
    bootstrap_queries: set[tuple[str, tuple[str, ...]]] = set()
    bootstrap_blobs: set[tuple[str, str]] = set()
    seen_active = False

    def historical(
        root: Path, domain: Domain, args: tuple[str, ...], fresh: Callable[[], bytes]
    ) -> bytes:
        nonlocal seen_active
        if _HistoryActivity.active(cast(_HistoryActivity, history)) is None:
            if seen_active:
                raise AssertionError("A historical consumer ran after phase deactivation.")
            bootstrap_queries.add((domain, args))
            return original(root, domain, args, fresh)
        seen_active = True

        def unexpected() -> bytes:
            raise AssertionError("An active immutable consumer escaped the complete catalog.")

        queries.add((domain, args))
        return original(root, domain, args, unexpected)

    def blobs(root: Path, revision: str, names: list[str]) -> dict[str, bytes] | None:
        nonlocal seen_active
        if _HistoryActivity.active(cast(_HistoryActivity, history)) is None:
            if seen_active:
                raise AssertionError("A historical blob consumer ran after phase deactivation.")
            bootstrap_blobs.update((revision, name) for name in names)
            return original_blobs(root, revision, names)
        seen_active = True
        blob_queries.update((revision, name) for name in names)
        result = original_blobs(root, revision, names)
        assert result is not None
        return result

    monkeypatch.setattr(history, "historical", historical)
    monkeypatch.setattr(history, "eligible_blobs", blobs)
    witnesses: list[dict[str, object]] = []
    with history.witnesses(witnesses):
        binding = gate.validate_current(
            ROOT, "5f509724da25a2f6ded0c2739a8e7c84bdf59c91", pr_head=None
        )
    assert bootstrap_queries
    assert bootstrap_blobs
    assert seen_active
    assert queries
    assert blob_queries
    assert len(witnesses) == 1
    witness = witnesses[0]
    assert witness["status"] == "completed"
    assert witness["role"] == "preflight"
    assert binding["history_snapshot_digest"] == witness["semantic_digest"]
    catalog = cast(dict[str, Any], witness["catalog"])
    assert catalog["declared_count"] == catalog["acquired_count"] == len(catalog["members"])
    members = {(row["domain"], row["commit"], row["path"]) for row in catalog["members"]}
    assert all(("plain60", commit, name) in members for commit, name in blob_queries)
    assert ("plain60", successor.FREEZE, "tools/performance_history_snapshot.py") in members
    assert catalog["commit_trees"]
    assert catalog["tree_edges"]
    assert _HistoryActivity.active(cast(_HistoryActivity, history)) is None
    print(
        json.dumps(
            {
                "actual_historical_requests": len(queries),
                "actual_blob_requests": len(blob_queries),
                "declared_members": catalog["declared_count"],
                "semantic_digest": witness["semantic_digest"],
            },
            sort_keys=True,
        )
    )


class _HistoryActivity(Protocol):
    _ACTIVE: ContextVar[Snapshot | None]

    def active(self) -> Snapshot | None:
        return self._ACTIVE.get()


def test_real_lane_creates_absent_scratch_before_four_worker_pytest(tmp_path: Path) -> None:
    root = tmp_path / "checkout"
    root.mkdir()
    for name in (
        "scripts/quality_runner.py",
        "scripts/quality_reporter.py",
        "scripts/quality_evidence.py",
        "scripts/build_test_shards.py",
        "pyproject.toml",
        "uv.lock",
    ):
        target = root / name
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes((ROOT / name).read_bytes())
    package = root / "src/warhammer40k_core"
    package.mkdir(parents=True)
    (package / "__init__.py").write_text("")
    (root / ".gitignore").write_text("reports/\n.pytest_cache/\n__pycache__/\n")
    manifest = root / "ci/quality_shards"
    manifest.mkdir(parents=True)
    tests = root / "tests/code_quality"
    tests.mkdir(parents=True)
    all_nodes: list[str] = []
    source = (
        "import pytest\n"
        "@pytest.mark.parametrize('number', range(12))\n"
        "def test_sample(number, tmp_path):\n"
        "    target = tmp_path / 'result.txt'\n"
        "    target.write_text(str(number))\n"
        "    assert target.read_text() == str(number)\n"
    )
    for shard in range(1, 5):
        module = (
            "tests/code_quality/test_performance_policy.py"
            if shard == 2
            else f"tests/code_quality/test_probe_{shard}.py"
        )
        (root / module).write_text(source)
        nodes = [f"{module}::test_sample[{number}]" for number in range(12)]
        all_nodes.extend(nodes)
        (manifest / f"shard-{shard}.txt").write_text("\n".join(nodes) + "\n")
        (manifest / f"shard-{shard}-modules.txt").write_text(module + "\n")
    (manifest / "all.txt").write_text("\n".join(sorted(all_nodes)) + "\n")
    for arguments in (
        ("init", "-q"),
        ("add", "."),
        (
            "-c",
            "user.name=quality-control",
            "-c",
            "user.email=control@example.invalid",
            "commit",
            "-qm",
            "native cold scratch control",
        ),
    ):
        subprocess.run(["git", *arguments], cwd=root, check=True, capture_output=True)
    head = evidence.git(root, "rev-parse", "HEAD")
    expected = {
        "mode": "local",
        "repository": "control/quality",
        "repository_id": "cold-scratch",
        "workflow_ref": "control/quality/local",
        "run_id": "cold-scratch",
        "run_attempt": "1",
        "event": "local-control",
        "checkout": head,
        "tree": evidence.git(root, "rev-parse", "HEAD^{tree}"),
        "pr_head": head,
        "base": head,
    }
    context_path = tmp_path / "context.json"
    context_path.write_text(json.dumps(expected))
    scratch = tmp_path / "missing-parent" / "scratch"
    environment = dict(
        os.environ,
        PYTHONPATH=str(root / "src") + os.pathsep + str(root),
        PYTHONDONTWRITEBYTECODE="1",
    )
    # This nested native fixture has its own explicit local context.
    environment.pop("GITHUB_ACTIONS", None)
    for name in ("PYTEST_XDIST_WORKER", "PYTEST_XDIST_WORKER_COUNT", "PYTEST_XDIST_TESTRUNUID"):
        environment.pop(name, None)
    command = [sys.executable, "-B", "-m", "scripts.quality_runner"]
    common = ["--shard", "4", "--context", str(context_path)]
    subprocess.run(
        [*command, "prepare", *common],
        cwd=root,
        env=environment,
        check=True,
        capture_output=True,
        timeout=30,
    )
    assert not scratch.parent.exists()
    result = subprocess.run(
        [*command, "run", *common, "--scratch", str(scratch)],
        cwd=root,
        env=environment,
        check=False,
        capture_output=True,
        text=True,
        timeout=120,
    )
    assert result.returncode == 0, result.stdout + result.stderr
    directory = root / "reports/quality-timing" / evidence.artifact_name(expected, "4")
    admitted = evidence.validate_lane(
        directory, expected, evidence.source_identity(root), evidence.inventory(root), "4", root
    )
    evidence.verify_seal(directory)
    assert scratch.is_dir()
    assert (scratch / "execute").is_dir()
    assert admitted["scratch"] == str(scratch)
    assert admitted["commands"]["execute"].count("-n") == 1
    assert admitted["commands"]["execute"][admitted["commands"]["execute"].index("-n") + 1] == "4"
    assert admitted["inventory"]["shards"]["4"]["nodes"] == [
        f"tests/code_quality/test_probe_4.py::test_sample[{number}]" for number in range(12)
    ]


def test_d07_dispatch_preserves_both_exact_ci54_predecessors() -> None:
    import hashlib

    from tools import cumulative_preservation as cumulative
    from tools import quality_runtime_successor as ci54

    names = {
        "tests/code_quality/test_ci_performance_gates.py",
        "tests/code_quality/test_performance_policy.py",
    }
    originals: dict[str, str] = json.loads(
        (ROOT / "data/source_audits/d07/original-tests.json").read_bytes()
    )
    assert names == ci54.BEFORE.keys() & originals.keys()
    actual = cumulative.d07_predecessors(ROOT)
    for name in sorted(names):
        native = subprocess.check_output(["git", "show", ci54.BASE + ":" + name], cwd=ROOT)
        assert hashlib.sha256(native).hexdigest() == ci54.BEFORE[name] == originals[name]
        assert actual[name] == native
        with pytest.raises(ValueError, match="caller supplied unrelated bytes"):
            ci54.previous(ROOT, name, (ROOT / name).read_bytes() + b" ")
