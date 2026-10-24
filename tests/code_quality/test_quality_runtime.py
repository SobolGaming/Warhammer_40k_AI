"""CI54 protects complete quality evidence without changing engine or behavioral gates."""

from __future__ import annotations

import ast
import copy
import errno
import json
import subprocess
import xml.etree.ElementTree as ET
from pathlib import Path
from typing import Any

import pytest
from scripts import quality_evidence as evidence
from scripts import quality_runner as runner

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
        workflow.split("  semantic-audit-macos:\n")[1]
        == (before.split("  semantic-audit-macos:\n")[1])
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
    assert set(baseline) <= set(current["all"])
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

    payload: Any = {"detail": "complete failure"}
    if failure == "serialization":
        payload = object()
    elif failure == "disk_full":

        def fail_encode(value: Any) -> bytes:
            raise OSError(errno.ENOSPC, "injected bounded payload write failure")

        monkeypatch.setattr(evidence, "encoded", fail_encode)
    else:
        monkeypatch.setattr(evidence, "sync_directory", fail_sync)
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
        journal.emit("collection", nodes=selected)
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
        "shards": {
            "4": {
                "nodes": selected,
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
    dependencies = {
        "python": "3.14.5",
        "executable": "binary",
        "physical_sha256": "physical",
        "distributions": {},
        "plugins": [],
    }
    admitted = {
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
            if event["kind"] == "session_start":
                event.update(
                    args=commands[mode][4:], plugins=[], ini=copy.deepcopy(ini), generation=0
                )
        if mode == "collect":
            header = {key: events[0][key] for key in ("schema", "binding", "role", "monotonic")}
            events += [
                {**header, "kind": "collection", "sequence": 2, "nodes": sorted(selected)},
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
    monkeypatch.setattr(evidence, "source_identity", lambda root: source)
    monkeypatch.setattr(evidence, "inventory", lambda root: inventories)
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
