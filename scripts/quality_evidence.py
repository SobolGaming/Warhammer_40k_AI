"""Exact quality inventory, durable evidence, and fail-closed fan-in (stdlib only)."""

from __future__ import annotations

import argparse
import ast
import hashlib
import importlib.metadata
import json
import os
import platform
import shlex
import subprocess
import sys
import time
import tomllib
import uuid
import xml.etree.ElementTree as ET
from pathlib import Path
from typing import Any

SCHEMA = "quality-runtime-v1"
WORKERS = [f"gw{i}" for i in range(4)]
MANIFEST = "ci/quality_shards"
CONTEXT_KEYS = {
    "mode",
    "repository",
    "repository_id",
    "workflow_ref",
    "run_id",
    "run_attempt",
    "event",
    "checkout",
    "tree",
    "pr_head",
    "base",
}


class EvidenceError(ValueError):
    """Evidence is absent, inconsistent, incomplete, or cannot be persisted."""


def require(condition: bool, message: str) -> None:
    if not condition:
        raise EvidenceError(message)


def sha(raw: bytes) -> str:
    return hashlib.sha256(raw).hexdigest()


def encoded(value: Any) -> bytes:
    return (
        json.dumps(
            value, ensure_ascii=False, sort_keys=True, allow_nan=False, separators=(",", ":")
        )
        + "\n"
    ).encode("utf-8")


def unique_object(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        require(key not in result, "Duplicate JSON member: " + key)
        result[key] = value
    return result


def read_json(path: Path) -> Any:
    return json.loads(path.read_bytes(), object_pairs_hook=unique_object)


def sync_directory(path: Path) -> None:
    descriptor = os.open(path, os.O_RDONLY | os.O_DIRECTORY)
    try:
        os.fsync(descriptor)
    finally:
        os.close(descriptor)


def atomic_json(path: Path, value: Any, *, replace: bool = False) -> None:
    """Sync payload and directory before any journal may reference this file."""
    try:
        raw = encoded(value)
        temporary = path.with_name(path.name + "." + uuid.uuid4().hex + ".tmp")
        with temporary.open("xb") as handle:
            handle.write(raw)
            handle.flush()
            os.fsync(handle.fileno())
        if replace:
            temporary.replace(path)
        else:
            os.link(temporary, path)
            temporary.unlink()
        sync_directory(path.parent)
    except (OSError, TypeError, ValueError, UnicodeError) as error:
        print(f"QUALITY EVIDENCE WRITE FAILURE {path}: {error}", file=sys.__stderr__, flush=True)
        raise EvidenceError(f"Cannot persist quality evidence: {path}") from error


class Journal:
    def __init__(self, directory: Path, role: str, binding: str) -> None:
        self.directory, self.role, self.binding = directory, role, binding
        self.sequence = 0
        self.path = directory / (role + ".jsonl")
        with self.path.open("xb") as handle:
            handle.flush()
            os.fsync(handle.fileno())
        sync_directory(directory)

    def emit(self, kind: str, **values: Any) -> int:
        self.sequence += 1
        event = dict(
            schema=SCHEMA,
            binding=self.binding,
            role=self.role,
            sequence=self.sequence,
            kind=kind,
            monotonic=time.monotonic(),
            utc_ns=time.time_ns(),
            **values,
        )
        try:
            raw = encoded(event)
            with self.path.open("ab") as handle:
                handle.write(raw)
                handle.flush()
                os.fsync(handle.fileno())
        except (OSError, TypeError, ValueError, UnicodeError) as error:
            print(
                f"QUALITY JOURNAL FAILURE {self.role} {kind}: {error}",
                file=sys.__stderr__,
                flush=True,
            )
            raise EvidenceError("Cannot persist quality journal") from error
        return self.sequence

    def active(self, node: str, phase: str) -> None:
        atomic_json(
            self.directory / (self.role + "-active.json"),
            {"binding": self.binding, "node": node, "phase": phase, "sequence": self.sequence},
            replace=True,
        )

    def failure(self, node: str, phase: str, payload: Any) -> dict[str, str]:
        name = f"{self.role}-failure-{self.sequence + 1}.json"
        path = self.directory / name
        atomic_json(path, {"node": node, "phase": phase, "payload": payload})
        return {"path": name, "sha256": sha(path.read_bytes())}


def git(root: Path, *arguments: str) -> str:
    return subprocess.check_output(["git", *arguments], cwd=root, timeout=30).decode().strip()


def source_identity(root: Path) -> dict[str, str]:
    """Fresh complete tracked bytes, membership, modes and exact checkout admission."""
    require(
        not git(root, "status", "--porcelain", "--untracked-files=all"),
        "Quality source must be a clean exact checkout",
    )
    rows = subprocess.check_output(["git", "ls-tree", "-rz", "HEAD"], cwd=root, timeout=30)
    digest = hashlib.sha256()
    tracked: set[str] = set()
    for row in rows.split(b"\0"):
        if not row:
            continue
        metadata, name_raw = row.split(b"\t", 1)
        mode, kind, oid = metadata.split()
        name = name_raw.decode("utf-8")
        tracked.add(name)
        path = root / name
        require(
            mode in {b"100644", b"100755"} and kind == b"blob" and not path.is_symlink(),
            "Unsupported source member: " + name,
        )
        raw = path.read_bytes()
        actual = hashlib.sha1(
            b"blob " + str(len(raw)).encode() + b"\0" + raw, usedforsecurity=False
        ).hexdigest()
        require(actual.encode() == oid, "Source bytes differ from HEAD: " + name)
        digest.update(encoded([name, mode.decode(), sha(raw)]))
    for prefix, pattern in (
        ("src", "*"),
        ("tests", "*"),
        ("tools", "*"),
        ("scripts", "*"),
        ("contracts", "*"),
        ("conformance/typescript/src", "*.ts"),
    ):
        for path in (root / prefix).rglob(pattern):
            if (path.is_file() or path.is_symlink()) and (
                prefix not in {"tests", "tools", "scripts"}
                or path.suffix in {".py", ".pyc", ".so", ".pyd", ".pth"}
            ):
                require(
                    path.relative_to(root).as_posix() in tracked,
                    "Unlisted source input: " + str(path),
                )
    return {
        "checkout": git(root, "rev-parse", "HEAD"),
        "tree": git(root, "rev-parse", "HEAD^{tree}"),
        "sha256": digest.hexdigest(),
        "lock": sha((root / "uv.lock").read_bytes()),
    }


def dependency_identity() -> dict[str, Any]:
    """Rehash installed distributions; do not memoize mutable dependency admission."""
    distributions: dict[str, Any] = {}
    plugins: set[tuple[str, str]] = set()
    for distribution in importlib.metadata.distributions():
        name = distribution.metadata["Name"].lower().replace("_", "-")
        require(name not in distributions, "Duplicate installed dependency: " + name)
        if any(point.group == "pytest11" for point in distribution.entry_points):
            plugins.add((name, distribution.version))
        digest = hashlib.sha256()
        members = distribution.files
        require(members is not None, "Missing dependency file inventory: " + name)
        assert members is not None
        for member in sorted(members, key=str):
            relative = str(member)
            path = Path(str(distribution.locate_file(member)))
            require(path.is_file(), "Missing installed dependency: " + relative)
            digest.update(encoded([relative, sha(path.read_bytes())]))
        distributions[name] = {"version": distribution.version, "sha256": digest.hexdigest()}
    roots = list(dict.fromkeys((Path(sys.prefix).resolve(), Path(sys.base_prefix).resolve())))
    return {
        "physical_sha256": physical_dependencies(roots),
        "python": platform.python_version(),
        "executable": sha(Path(sys.executable).read_bytes()),
        "distributions": distributions,
        "plugins": sorted(plugins),
    }


def physical_dependencies(roots: list[Path]) -> str:
    """Include cached bytecode and unlisted importable additions in each fresh scan."""
    physical = hashlib.sha256()
    for index, environment_root in enumerate(roots):
        for path in sorted(environment_root.rglob("*")):
            relative = path.relative_to(environment_root).as_posix()
            if path.is_symlink():
                target = path.resolve(strict=True)
                require(
                    any(target.is_relative_to(base) for base in roots),
                    "Dependency link escaped admitted environments: " + str(path),
                )
                physical.update(encoded([index, relative, "symlink", str(path.readlink())]))
            if path.is_file():
                physical.update(encoded([index, relative, sha(path.read_bytes())]))
    return physical.hexdigest()


def context(root: Path, local: Path | None = None) -> dict[str, str]:
    value: dict[str, str]
    if local is not None:
        require(os.environ.get("GITHUB_ACTIONS") != "true", "Local context forbidden in hosted CI")
        value = read_json(local)
        require(value.get("mode") == "local", "Explicit local context required")
    else:
        event = read_json(Path(os.environ["GITHUB_EVENT_PATH"]))
        pr = event.get("pull_request", {})
        value = {
            "mode": "hosted",
            "repository": os.environ["GITHUB_REPOSITORY"],
            "repository_id": os.environ["GITHUB_REPOSITORY_ID"],
            "workflow_ref": os.environ["GITHUB_WORKFLOW_REF"],
            "run_id": os.environ["GITHUB_RUN_ID"],
            "run_attempt": os.environ["GITHUB_RUN_ATTEMPT"],
            "event": os.environ["GITHUB_EVENT_NAME"],
            "checkout": os.environ["GITHUB_SHA"],
            "tree": git(root, "rev-parse", "HEAD^{tree}"),
            "pr_head": pr.get("head", {}).get("sha", ""),
            "base": pr.get("base", {}).get("sha")
            or event.get("merge_group", {}).get("base_sha")
            or event.get("before", ""),
        }
    require(
        isinstance(value, dict)
        and value.keys() == CONTEXT_KEYS
        and all(isinstance(v, str) for v in value.values()),
        "Malformed workflow identity",
    )
    require(all(value[k] for k in CONTEXT_KEYS - {"pr_head"}), "Missing workflow identity")
    require(
        value["checkout"] == git(root, "rev-parse", "HEAD")
        and value["tree"] == git(root, "rev-parse", "HEAD^{tree}"),
        "Wrong checkout identity",
    )
    require(value["run_attempt"].isdigit() and int(value["run_attempt"]) > 0, "Invalid run attempt")
    return value


def lines(path: Path) -> list[str]:
    raw = path.read_bytes()
    require(raw.endswith(b"\n") and b"\r" not in raw, "Noncanonical manifest: " + str(path))
    values = raw.decode("utf-8").splitlines()
    require(
        bool(values) and all(values) and len(values) == len(set(values)),
        "Empty or duplicate manifest members: " + str(path),
    )
    return values


def inventory(root: Path) -> dict[str, Any]:
    directory = root / MANIFEST
    all_nodes = lines(directory / "all.txt")
    require(all_nodes == sorted(all_nodes), "Full inventory must be sorted")
    shards: dict[str, Any] = {}
    union: list[str] = []
    modules: list[str] = []
    for index in range(1, 5):
        selected = lines(directory / f"shard-{index}.txt")
        paths = lines(directory / f"shard-{index}-modules.txt")
        require(
            {node.split("::", 1)[0] for node in selected} == set(paths),
            "Case/module inventory disagreement",
        )
        require(
            selected
            == [node for path in paths for node in selected if node.split("::", 1)[0] == path],
            "Assigned collection order must follow module argv",
        )
        union.extend(selected)
        modules.extend(paths)
        shards[str(index)] = {"nodes": selected, "modules": paths}
    discovered = sorted(
        path.relative_to(root).as_posix()
        for path in (root / "tests/code_quality").rglob("test_*.py")
    )
    require(
        len(modules) == len(set(modules)) and sorted(modules) == discovered,
        "Quality module membership drift",
    )
    require(
        len(union) == len(set(union)) and sorted(union) == all_nodes,
        "Quality partition is not an exact disjoint union",
    )
    require(
        "tests/code_quality/test_performance_policy.py" in shards["2"]["modules"],
        "Performance receipt consumer must stay on its producing lane",
    )
    return {"all": all_nodes, "shards": shards}


def pytest_arguments(
    selected: dict[str, Any], directory: Path, scratch: Path, *, collect: bool
) -> list[str]:
    selection = ["tests/code_quality"] if collect else selected["modules"]
    options = [
        "-q",
        "--no-cov",
        "-p",
        "scripts.quality_reporter",
        "--basetemp",
        str(scratch),
        "-o",
        "cache_dir=" + str(scratch.parent / "pytest-cache"),
    ]
    if collect:
        options += ["--collect-only", "-n0"]
    else:
        options += [
            "-n",
            "4",
            "--dist=worksteal",
            "--max-worker-restart=0",
            "--junitxml=" + str(directory / "junit.xml"),
        ]
    return [sys.executable, "-B", "-m", "pytest", *selection, *options]


def journal_events(directory: Path, role: str, binding: str) -> list[dict[str, Any]]:
    raw = (directory / (role + ".jsonl")).read_bytes()
    require(raw.endswith(b"\n"), "Incomplete journal tail: " + role)
    events = [json.loads(line, object_pairs_hook=unique_object) for line in raw.splitlines()]
    require(bool(events), "Empty journal: " + role)
    for sequence, event in enumerate(events, 1):
        require(
            event.get("schema") == SCHEMA
            and event.get("binding") == binding
            and event.get("role") == role
            and type(event.get("sequence")) is int
            and event["sequence"] == sequence,
            "Journal identity/sequence gap: " + role,
        )
        if "failure" in event:
            failure = event["failure"]
            name = failure["path"]
            require(
                Path(name).name == name and name.startswith(role + "-failure-"),
                "Invalid failure payload name",
            )
            require(
                sha((directory / name).read_bytes()) == failure["sha256"],
                "Missing or changed failure payload",
            )
    return events


def validate_invocations(
    directory: Path,
    admitted: dict[str, Any],
    inventories: dict[str, Any],
    shard: str,
    binding: str,
    lock_root: Path,
) -> None:
    commands = admitted["commands"]
    require(set(commands) == {"collect", "execute"}, "Unexpected pytest invocation")
    configuration = tomllib.loads((lock_root / "pyproject.toml").read_text())["tool"]["pytest"][
        "ini_options"
    ]
    require(
        admitted["config"] == sha((lock_root / "pyproject.toml").read_bytes()),
        "Wrong pytest configuration source",
    )
    selected = inventories["shards"][shard]
    output = Path(admitted["output_directory"])
    scratch = Path(admitted["scratch"])
    require(output.is_absolute() and scratch.is_absolute(), "Unbound invocation paths")
    expected_environment = {
        "PYTHONDONTWRITEBYTECODE": "1",
        "XDG_CACHE_HOME": str(scratch / "cache"),
        "HYPOTHESIS_STORAGE_DIRECTORY": str(scratch / "hypothesis"),
        "project_origin": str(output.parents[2] / "src/warhammer40k_core/__init__.py"),
    }
    require(admitted["environment"] == expected_environment, "Cache or project import origin drift")
    for mode in ("collect", "execute"):
        command = commands[mode]
        expected = pytest_arguments(selected, output, scratch / mode, collect=mode == "collect")
        require(
            isinstance(command, list) and bool(command) and isinstance(command[0], str),
            "Missing pytest executable",
        )
        expected[0] = command[0]
        require(command == expected, "Pytest command drift")
        process = read_json(directory / (mode + "-process.json"))
        require(
            process["command"] == command
            and process["exit_status"] == 0
            and 0 < process["elapsed"] < 595,
            "Pytest process did not finish within its bound",
        )
        require((directory / (mode + ".log")).is_file(), "Missing raw pytest output")
        roles = [mode + "-controller"]
        if mode == "execute":
            roles += ["execute-" + worker for worker in WORKERS]
        reference = journal_events(directory, "collect-controller", binding)[0]
        for role in roles:
            event = journal_events(directory, role, binding)[0]
            require(
                event["kind"] == "session_start"
                and event["generation"] == 0
                and event["args"] == command[4:]
                and event["plugins"] == admitted["dependencies"]["plugins"],
                "Wrong invocation/plugins/worker generation",
            )
            ini = event["ini"]
            require(
                ini["addopts"] == shlex.split(configuration["addopts"])
                and ini["testpaths"] == configuration["testpaths"]
                and all(marker in ini["markers"] for marker in configuration["markers"])
                and ini == reference["ini"],
                "Effective pytest configuration drift",
            )


def validate_lane(
    directory: Path,
    expected: dict[str, Any],
    source: dict[str, str],
    inventories: dict[str, Any],
    shard: str,
    lock_root: Path,
) -> dict[str, Any]:
    start = read_json(directory / "start.json")
    require(
        start.keys() == {"schema", "context", "shard", "shard_count", "workers", "producer"}
        and start.get("schema") == SCHEMA
        and start.get("producer") == ("quality-policy" if shard == "2" else "quality-shards")
        and start.get("context") == expected
        and start.get("shard") == shard
        and start.get("shard_count") == 4
        and start.get("workers") == WORKERS,
        "Wrong producer/run/attempt/head/shard",
    )
    binding = sha(encoded(start))
    admitted: dict[str, Any] = read_json(directory / "admitted.json")
    require(
        admitted["source"] == source
        and admitted["inventory"] == inventories
        and admitted["binding"] == binding,
        "Wrong source/config/inventory",
    )
    validate_invocations(directory, admitted, inventories, shard, binding, lock_root)
    resources = admitted["resources"]
    require(
        resources["effective_cores"] >= 4 and len(resources["affinity"]) >= 4,
        "Quality producer lacked four effective cores",
    )
    final = read_json(directory / "supervisor.json")
    require(
        final.get("binding") == binding
        and final.get("state") == "completed"
        and final.get("exit_status") == 0
        and final.get("signals") == []
        and final.get("source_after") == source
        and final.get("dependencies_after") == admitted["dependencies"]
        and final.get("children_reaped") is True,
        "Incomplete/failed supervisor or changed inputs",
    )
    lock = tomllib.loads((lock_root / "uv.lock").read_text())
    versions = {(p["name"].lower().replace("_", "-"), p["version"]) for p in lock["package"]}
    require(
        all(
            (name, row["version"]) in versions
            for name, row in admitted["dependencies"]["distributions"].items()
        ),
        "Unlocked dependencies",
    )
    require(admitted["dependencies"]["python"] == "3.14.5", "Wrong Python runtime")
    collection = journal_events(directory, "collect-controller", binding)
    require(
        [e["kind"] for e in collection] == ["session_start", "collection", "session_finish"]
        and sorted(collection[1]["nodes"]) == inventories["all"]
        and collection[-1]["exit_status"] == 0,
        "Independent full collection failed",
    )
    validate_execution(directory, binding, inventories["shards"][shard]["nodes"])
    return admitted


def validate_execution(directory: Path, binding: str, selected: list[str]) -> None:
    """Validate the actual causal execution protocol independently of transport admission."""
    executed: set[str] = set()
    origins: dict[tuple[str, int], dict[str, Any]] = {}
    for worker in WORKERS:
        role = "execute-" + worker
        events = journal_events(directory, role, binding)
        require(
            events[0]["kind"] == "session_start"
            and events[-1]["kind"] == "session_finish"
            and events[-1]["exit_status"] == 0,
            "Worker did not close cleanly: " + worker,
        )
        require(
            events[1]["kind"] == "collection" and events[1]["nodes"] == selected,
            "Worker collection differs from authoritative manifest",
        )
        active = ""
        phase = ""
        ended: list[str] = []
        for event in events[2:-1]:
            kind = event["kind"]
            node = event.get("node", "")
            if kind == "node_start":
                require(
                    not active and node in selected and node not in executed,
                    "Duplicate/unexpected node execution",
                )
                executed.add(node)
                active, ended = node, []
            elif kind == "phase_start":
                require(
                    active == node
                    and not phase
                    and len(ended) < 3
                    and event["phase"] == ["setup", "call", "teardown"][len(ended)],
                    "Noncausal phase start",
                )
                phase = event["phase"]
            elif kind == "phase_end":
                require(
                    active == node
                    and phase == event["phase"]
                    and event["outcome"] == "passed"
                    and event["wasxfail"] is False
                    and "failure" not in event,
                    "Failed/skipped/xfail/xpass/incomplete phase",
                )
                ended.append(phase)
                phase = ""
                origins[worker, event["sequence"]] = event
            elif kind == "node_end":
                require(
                    active == node and not phase and ended == ["setup", "call", "teardown"],
                    "Node ended without all passing phases",
                )
                active = ""
            else:
                raise EvidenceError("Unexpected worker event: " + kind)
        require(not active, "Worker closed with an active node")
        active_record = read_json(directory / (role + "-active.json"))
        require(
            active_record["binding"] == binding
            and active_record["node"] == ""
            and active_record["phase"] == "idle",
            "Missing or incomplete active-state record",
        )
    require(executed == set(selected), "Unstarted or missing cases")
    controller = journal_events(directory, "execute-controller", binding)
    require(
        controller[0]["kind"] == "session_start"
        and controller[-1]["kind"] == "session_finish"
        and controller[-1]["exit_status"] == 0,
        "Controller did not close cleanly",
    )
    started: list[str] = []
    collected: list[str] = []
    closed: list[str] = []
    mirrored: set[tuple[str, int]] = set()
    for event in controller[1:-1]:
        kind = event["kind"]
        worker = event.get("worker", "")
        if kind == "worker_start":
            require(worker in WORKERS and worker not in started, "Unexpected/restarted worker")
            started.append(worker)
        elif kind == "worker_collection":
            require(
                worker in started and worker not in collected and event["nodes"] == selected,
                "Missing/duplicate worker collection",
            )
            collected.append(worker)
        elif kind == "mirror":
            require(set(collected) == set(WORKERS), "Execution before all worker collections")
            key = worker, event["origin_sequence"]
            require(key in origins and key not in mirrored, "Unknown/duplicate controller mirror")
            origin = origins[key]
            require(
                all(
                    event[field] == origin[field]
                    for field in ("node", "phase", "outcome", "wasxfail")
                ),
                "Controller mirror changed",
            )
            mirrored.add(key)
        elif kind == "worker_end":
            require(
                worker in collected and worker not in closed and event["error"] is None,
                "Lost/restarted worker",
            )
            closed.append(worker)
        else:
            raise EvidenceError("Unexpected controller event: " + kind)
    require(
        set(started) == set(collected) == set(closed) == set(WORKERS)
        and mirrored == origins.keys(),
        "Missing worker generation or controller mirror",
    )
    xml = ET.fromstring((directory / "junit.xml").read_bytes())
    cases = xml.findall(".//testcase")
    junit_nodes: list[str] = []
    for case in cases:
        require(
            not any(case.find(tag) is not None for tag in ("failure", "error", "skipped")),
            "JUnit contains a nonpassing case",
        )
        ids = [
            p.attrib["value"]
            for p in case.findall("properties/property")
            if p.attrib.get("name") == "quality_nodeid"
        ]
        require(len(ids) == 1, "Unnamed or duplicate JUnit identity")
        junit_nodes.extend(ids)
    require(
        len(junit_nodes) == len(set(junit_nodes)) and set(junit_nodes) == set(selected),
        "JUnit execution inventory differs",
    )
    require(
        {path.name for path in directory.glob("*.jsonl")}
        == {"collect-controller.jsonl", "execute-controller.jsonl", "watchdog.jsonl"}
        | {"execute-" + worker + ".jsonl" for worker in WORKERS},
        "Unexpected journal generation",
    )
    guard = journal_events(directory, "watchdog", binding)
    require(
        guard[0]["kind"] == "watchdog_start"
        and guard[0]["deadlines"] == {"interrupt": 570, "terminate": 585, "kill": 590, "reap": 595}
        and guard[-1]["kind"] == "watchdog_end"
        and guard[-1]["exit_status"] == 0
        and all(e["kind"] in {"group", "closed"} for e in guard[1:-1]),
        "Watchdog missing, cancelled, timed out, or left child processes",
    )
    require(
        [e["kind"] for e in guard[1:-1]] == ["group", "closed", "group", "closed"],
        "Expected collection and execution process groups",
    )


def seal(directory: Path) -> None:
    files = {
        path.relative_to(directory).as_posix(): sha(path.read_bytes())
        for path in sorted(directory.rglob("*"))
        if path.is_file()
    }
    atomic_json(directory / "files.json", files)


def verify_seal(directory: Path) -> None:
    actual = {
        path.relative_to(directory).as_posix(): sha(path.read_bytes())
        for path in sorted(directory.rglob("*"))
        if path.is_file() and path.name != "files.json"
    }
    require(actual == read_json(directory / "files.json"), "Artifact file inventory/hash changed")


def artifact_name(expected: dict[str, str], shard: str) -> str:
    return "-".join(
        (
            "quality",
            expected["repository_id"],
            expected["run_id"],
            expected["run_attempt"],
            expected["checkout"],
            shard,
        )
    )


def validate_performance(
    directory: Path, admitted: dict[str, Any], expected: dict[str, str], root: Path
) -> None:
    """Check preserved producer evidence, never re-admit its runtime on a different host."""
    report_path = directory / "performance/performance-smoke.json"
    report = read_json(report_path)
    require(
        report.get("inputs_unchanged") is True
        and report.get("status") == "passed"
        and report.get("checkout_head") == expected["checkout"]
        and report.get("base_revision") == expected["base"]
        and report.get("pull_request_head") == (expected["pr_head"] or None),
        "Wrong or failed performance receipt identity",
    )
    require(
        sha(report_path.read_bytes()) == admitted["performance"]["sha256"],
        "Performance receipt changed after same-runner admission",
    )
    producer_root = Path(admitted["output_directory"]).parents[2]
    attempt = Path(report["attempt_receipt"])
    require(
        attempt.is_absolute()
        and attempt.is_relative_to(producer_root / "reports/performance-attempts")
        and attempt.parent.parent == producer_root / "reports/performance-attempts"
        and attempt.name == "receipt.json",
        "Missing original performance attempt provenance",
    )
    retained = directory / "performance/performance-attempts" / attempt.parent.name / attempt.name
    require(
        retained.read_bytes() == report_path.read_bytes(), "Original performance receipt differs"
    )
    constants = {}
    for node in ast.parse((root / "scripts/performance_smoke.py").read_bytes()).body:
        if (
            isinstance(node, ast.Assign)
            and len(node.targets) == 1
            and isinstance(node.targets[0], ast.Name)
        ):
            name = node.targets[0].id
            if name in {"CASES", "CASE_LIMIT_SECONDS", "PROCESS_LIMIT_SECONDS", "WORKLOAD"}:
                constants[name] = ast.literal_eval(node.value)
    require(
        constants.keys() == {"CASES", "CASE_LIMIT_SECONDS", "PROCESS_LIMIT_SECONDS", "WORKLOAD"},
        "Unrecognized smoke contract",
    )
    require(
        report.get("workload") == constants["WORKLOAD"]
        and report.get("case_limit_seconds") == constants["CASE_LIMIT_SECONDS"]
        and report.get("process_limit_seconds") == constants["PROCESS_LIMIT_SECONDS"]
        and 0 < report["total_seconds"] <= constants["PROCESS_LIMIT_SECONDS"],
        "Smoke limits changed",
    )
    require(len(report["cases"]) == len(constants["CASES"]), "Missing smoke case")
    for row, case in zip(report["cases"], constants["CASES"], strict=True):
        require(
            row["case"] == case
            and row["exit_code"] == 0
            and row["timed_out"] is False
            and row["result"]["case"] == case
            and row["result"]["complete"] is True
            and 0 < row["process_seconds"] <= constants["CASE_LIMIT_SECONDS"],
            "Smoke case failed or incomplete",
        )
    require(
        report["assessment_sha256"]
        == sha((root / "docs/performance/change-assessment.json").read_bytes()),
        "Smoke assessment does not match exact checkout",
    )
    tracked = {name for name in git(root, "ls-files", "-z").split("\0") if name}
    inputs = {
        name
        for name in tracked
        if name.startswith(("src/", "tests/", "scripts/", "tools/", "contracts/schemas/"))
        or name in {"uv.lock", "pyproject.toml", "docs/performance/policy-v3/operation-map.json"}
    }
    require(set(report["inputs"]) == inputs, "Smoke input membership differs from exact checkout")
    require(
        all(sha((root / name).read_bytes()) == digest for name, digest in report["inputs"].items()),
        "Smoke producer input bytes differ from exact checkout",
    )
    require(
        report["input_digest"]
        == sha(
            json.dumps(
                report["inputs"],
                sort_keys=True,
                separators=(",", ":"),
                allow_nan=False,
            ).encode()
        ),
        "Smoke input digest differs",
    )
    require(
        report["runtime_build_id"]
        == read_json(root / "src/warhammer40k_core/_engine_build_manifest.json")["build_id"],
        "Smoke runtime identity differs",
    )


def reconcile(
    root: Path, artifacts: Path, expected: dict[str, str], results: dict[str, str]
) -> None:
    require(
        results == {"quality-policy": "success", "quality-shards": "success"},
        "Required quality producers failed, skipped, cancelled, or are missing",
    )
    source, inventories = source_identity(root), inventory(root)
    names = {artifact_name(expected, str(i)) for i in range(1, 5)}
    require({p.name for p in artifacts.iterdir()} == names, "Missing/duplicate/stale artifacts")
    dependencies = []
    for shard in map(str, range(1, 5)):
        directory = artifacts / artifact_name(expected, shard)
        verify_seal(directory)
        admitted = validate_lane(directory, expected, source, inventories, shard, root)
        dependencies.append(admitted["dependencies"])
        if shard == "2":
            validate_performance(directory, admitted, expected, root)
    semantic = [
        {
            "python": value["python"],
            "executable": value["executable"],
            "plugins": value["plugins"],
            "versions": {name: row["version"] for name, row in value["distributions"].items()},
        }
        for value in dependencies
    ]
    require(all(value == semantic[0] for value in semantic), "Mixed locked dependency environments")
    require(source_identity(root) == source, "Reconciler source changed")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("artifacts", type=Path)
    parser.add_argument("--context", type=Path)
    parser.add_argument("--results", required=True)
    options = parser.parse_args()
    root = Path.cwd()
    reconcile(root, options.artifacts, context(root, options.context), json.loads(options.results))
    print("Complete exact-head quality evidence accepted for all four producers.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
