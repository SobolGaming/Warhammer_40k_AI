"""One authenticated current local serial-role observation for six native cases.

This is scheduling input, not a replacement complete profile or hosted timing.
The original complete baseline and historical model remain unchanged.
"""

from __future__ import annotations

import hashlib
import json
import math
import subprocess
import xml.etree.ElementTree as ET
from dataclasses import dataclass
from pathlib import Path
from typing import cast

from scripts.historical_shard_snapshot import MANIFEST, fingerprint
from scripts.hosted_timing_calibration import _hash, _object, _seconds, read_json

FILENAME = "current-native-serial-role.json"
SCHEMA = "current-native-six-case-serial-role-v1"
PRODUCER = "f900d0796b59b7859309af71e62a9e190934d10f"
ROLE = (
    "Current local six-case serial observation; historical projections are not hosted observations"
)
SOURCE_FILES = frozenset(
    {
        "scripts/run_behavioral_coverage.sh",
        "scripts/behavioral_deadline.py",
        "scripts/ci_resource_diagnostics.py",
        "tests/conftest.py",
        "tests/timing_plugin.py",
        "tests/support/cavalcade_native_prefix.py",
        "tests/support/cavalcade_v995.py",
        "tests/movement_submission_helpers.py",
        "tests/sequential_translation_helpers.py",
        "tests/factions/chaos_daemons/integration/test_cavalcade_native_screen_prefix.py",
        "tests/factions/chaos_daemons/integration/fixtures/cavalcade_v995_deployment.json",
        "data/army_lists/cavalcade-shadow-bloodthirster.json",
        "pyproject.toml",
        "uv.lock",
        MANIFEST,
    }
)
RAW_NAMES = frozenset({"worker", "controller", "supervisor", "junit", "command", "selected_index"})


def source_paths(root: Path) -> set[str]:
    from tools.ability_support_sources import ability_support_index_inputs

    source = root / "data/source_snapshots/wahapedia/10th-edition/2026-06-14/json"
    return set(SOURCE_FILES) | {
        str(path.relative_to(root)) for path in ability_support_index_inputs(source)
    }


@dataclass(frozen=True)
class NativeSerialRole:
    seconds: float
    metadata: dict[str, object]


def load_native_serial_role(
    root: Path, directory: Path, reference_value: object, expected_nodes: frozenset[str]
) -> NativeSerialRole:
    reference = _object(reference_value, {"file", "sha256"}, "native serial reference")
    path = directory / FILENAME
    if (
        reference["file"] != FILENAME
        or hashlib.sha256(path.read_bytes()).hexdigest() != reference["sha256"]
    ):
        raise SystemExit("Native serial role evidence changed.")
    record = _object(
        read_json(path),
        {
            "schema",
            "role",
            "source_head",
            "source_tree",
            "runtime_fingerprint",
            "source_files",
            "producer_input_digest",
            "producer_pre_post_identical",
            "raw",
        },
        "native serial role",
    )
    if record["schema"] != SCHEMA or record["role"] != ROLE or record["source_head"] != PRODUCER:
        raise SystemExit("Unreviewed native serial role producer.")
    _hash(record["producer_input_digest"])
    if record["producer_pre_post_identical"] is not True:
        raise SystemExit("Native serial producer changed during observation.")
    tree = (
        subprocess.check_output(["git", "rev-parse", PRODUCER + "^{tree}"], cwd=root)
        .decode()
        .strip()
    )
    runtime = json.loads((root / MANIFEST).read_bytes())["fingerprint"]
    if (
        tree != record["source_tree"]
        or fingerprint(root, PRODUCER) != runtime
        or record["runtime_fingerprint"] != runtime
    ):
        raise SystemExit("Native serial producer tree or runtime differs.")
    sources = _object(record["source_files"], source_paths(root), "native serial source closure")
    lines = (
        subprocess.check_output(["git", "ls-tree", "-r", PRODUCER], cwd=root).decode().splitlines()
    )
    blobs = {line.split("\t", 1)[1]: line.split()[2] for line in lines}
    for name, digest in sources.items():
        content = (root / name).read_bytes()
        blob = hashlib.sha1(b"blob " + str(len(content)).encode() + b"\0" + content).hexdigest()
        if hashlib.sha256(content).hexdigest() != digest or blobs.get(name) != blob:
            raise SystemExit("Native serial measured dependency changed: " + name)
    raw = _object(record["raw"], set(RAW_NAMES), "native serial raw artifacts")
    texts: dict[str, str] = {}
    hashes: dict[str, str] = {}
    for name, value in raw.items():
        artifact = _object(value, {"sha256", "text"}, "native serial raw " + name)
        if not isinstance(artifact["text"], str):
            raise SystemExit("Native serial artifact text is missing.")
        texts[name] = artifact["text"]
        hashes[name] = hashlib.sha256(texts[name].encode()).hexdigest()
        if hashes[name] != artifact["sha256"]:
            raise SystemExit("Native serial raw artifact digest differs.")
    worker = cast(dict[str, object], json.loads(texts["worker"]))
    controller = cast(dict[str, object], json.loads(texts["controller"]))
    supervisor = cast(dict[str, object], json.loads(texts["supervisor"]))
    if (
        worker.get("worker") != "gw0"
        or worker.get("worker_count") != "1"
        or worker.get("exit_status") != 0
        or controller.get("exit_status") != 0
        or worker.get("github_run_id") is not None
        or worker.get("github_sha") is not None
        or worker.get("collected_nodeids") is None
        or frozenset(cast(list[str], worker["collected_nodeids"])) != expected_nodes
        or len(cast(list[str], worker["collected_nodeids"])) != 6
    ):
        raise SystemExit("Native serial observation requires exactly six local one-worker cases.")
    reports_value = worker.get("reports")
    if not isinstance(reports_value, list):
        raise SystemExit("Native serial complete phase inventory differs.")
    reports = cast(list[object], reports_value)
    if len(reports) != 18 or reports != controller.get("reports"):
        raise SystemExit("Native serial complete phase inventory differs.")
    phases: dict[tuple[str, str], float] = {}
    for value in reports:
        row = _object(value, {"nodeid", "phase", "seconds", "outcome"}, "native serial phase")
        node, phase = row["nodeid"], row["phase"]
        if (
            not isinstance(node, str)
            or not isinstance(phase, str)
            or node not in expected_nodes
            or phase not in {"setup", "call", "teardown"}
            or row["outcome"] != "passed"
            or (node, phase) in phases
        ):
            raise SystemExit("Native serial phase is missing, repeated or unsuccessful.")
        phases[node, phase] = _seconds(row["seconds"])
    if phases.keys() != {
        (node, phase) for node in expected_nodes for phase in ("setup", "call", "teardown")
    }:
        raise SystemExit("Native serial three-phase inventory differs.")
    seconds = math.fsum(phases.values())
    if (
        supervisor.get("schema") != "covered-shard-deadline-v1"
        or supervisor.get("command") != ["bash", "scripts/run_behavioral_coverage.sh"]
        or supervisor.get("approval_seconds") != 1620
        or supervisor.get("execution_seconds") != 1800
        or supervisor.get("approved") is not True
        or supervisor.get("reason") != "passed"
        or supervisor.get("workload_exit_code") != 0
        or supervisor.get("terminated") is not False
        or supervisor.get("cleanup_error") is not None
        or supervisor.get("descendants_remained") is not False
        or _seconds(supervisor.get("elapsed_seconds")) > 1620
        or not seconds
        <= _seconds(worker.get("elapsed_seconds"))
        <= _seconds(controller.get("elapsed_seconds"))
        <= _seconds(supervisor.get("elapsed_seconds"))
    ):
        raise SystemExit("Native serial observation did not pass unchanged approval gates.")
    cases = list(ET.fromstring(texts["junit"]).iter("testcase"))
    junit_nodes = {
        case.get("classname", "").replace(".", "/") + ".py::" + case.get("name", "")
        for case in cases
    }
    if (
        len(cases) != 6
        or frozenset(junit_nodes) != expected_nodes
        or any(
            case.find(tag) is not None for case in cases for tag in ("failure", "error", "skipped")
        )
    ):
        raise SystemExit("Native serial JUnit inventory did not pass exactly six cases.")
    command = cast(dict[str, object], json.loads(texts["command"]))
    environment = cast(dict[str, object], command["environment_overrides"])
    if (
        command.get("inner_runner") != {"max_seconds": 120, "max_decisions": 42, "policy_seed": 19}
        or environment.get("SELECTED_INDEX_CACHE_HIT") != "true"
    ):
        raise SystemExit("Native serial runner or warm cache role differs.")
    index = cast(dict[str, object], json.loads(texts["selected_index"]))
    index_inputs = cast(dict[str, str], index["inputs"])
    measured_root = str(command["cwd"]).rstrip("/") + "/"
    if any(
        not name.startswith(measured_root)
        or sources.get(name.removeprefix(measured_root)) != digest
        for name, digest in index_inputs.items()
    ):
        raise SystemExit("Native serial selected-index dependencies differ.")
    return NativeSerialRole(
        seconds,
        {
            "file": FILENAME,
            "sha256": reference["sha256"],
            "role": ROLE,
            "source_head": PRODUCER,
            "source_tree": tree,
            "runtime_fingerprint": runtime,
            "producer_input_digest": record["producer_input_digest"],
            "source_applicability": (
                "Measured native/controller/config closure is unchanged; later accounting, QA "
                "and documentation are not the measured global source."
            ),
            "complete_phase_seconds": seconds,
            "worker_elapsed_seconds": worker["elapsed_seconds"],
            "controller_elapsed_seconds": controller["elapsed_seconds"],
            "supervisor_elapsed_seconds": supervisor["elapsed_seconds"],
            "cases": sorted(expected_nodes),
            "worker_count": 1,
            "cache_role": "Warm retained selected-source index; fresh worker/module fixtures",
            "raw_artifact_sha256": hashes,
        },
    )
