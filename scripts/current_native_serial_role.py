"""Two authenticated current local serial contexts for six native cases.

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

from scripts.historical_shard_snapshot import MANIFEST, fingerprint, git_bytes
from scripts.hosted_timing_calibration import _hash, _object, _seconds, read_json

FILENAME = "current-native-serial-role.json"
SCHEMA = "current-native-two-context-serial-role-v2"
STANDALONE_SCHEMA = "current-native-six-case-serial-role-v1"
COMBINED_SCHEMA = "current-native-after-mirror-serial-role-v1"
PRODUCER = "f900d0796b59b7859309af71e62a9e190934d10f"
COMBINED_PRODUCER = "f8c44d8492ae48b8db53267252ef4ea6f276cf1a"
INPUT_DIGESTS = {
    "standalone": "c2a39d742eb1c425ab003f11715c146a71810713b18c66c35f6aae81cdc09de5",
    "with_mirror": "60f874b99b707ea9544acf01a86f3694f7a35d4c540243d06df68ab884aa0c51",
}
ROLE = (
    "Two current local native serial contexts; historical projections are not hosted observations"
)
COMBINED_ROLE = (
    "Current local native observation after legacy mirror in the same ordered "
    "one-worker process; not hosted timing"
)
STANDALONE_ROLE = (
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
COMBINED_IMPORT_FILES = frozenset(
    {
        "tests/support/section02_fixtures.py",
        "tools/aeldari_ability_semantic_descriptions.py",
        "tests/disembark_eligibility_helpers.py",
        "tests/support/viewer_identity_fixtures.py",
        "tools/emperors_children_39k_pro_audit.py",
        "tools/core_deadly_demise_catalog_overlay.py",
        "tools/aeldari_datasheet_semantic_snapshot.py",
        "tools/faction_pack_datasheet_review.py",
        "tests/phase13b_shooting_declaration_helpers.py",
        "tools/aeldari_datasheet_semantic_evidence.py",
        "tools/emperors_children_support_report.py",
        "tests/support/faction_batch01.py",
        "tests/core_stratagem_helpers.py",
        "tests/factions/chaos_daemons/integration/test_cavalcade_v995_roster.py",
        "tests/unit_keyword_helpers.py",
        "tests/measurement_native_api.py",
        "tools/aeldari_39k_pro_audit.py",
        "tools/maulerfiend_cross_faction_support.py",
        "tests/setup_completion_helpers.py",
        "tools/core_deep_strike_catalog_overlay.py",
        "tools/generate_ability_support_matrix.py",
        "tests/support/private_randomness.py",
        "tools/cross_source_semantic_equivalence.py",
        "tools/canonical_json_hash.py",
        "tests/order60_emergency_disembark_helpers.py",
        "tools/aeldari_support_report.py",
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
    with_mirror_seconds: float
    metadata: dict[str, object]


def _observation(
    root: Path,
    value: object,
    native_nodes: frozenset[str],
    *,
    context: str,
    expected_order: list[str] | None = None,
) -> tuple[float, dict[str, object], list[str]]:
    combined = context == "with_mirror"
    producer = COMBINED_PRODUCER if combined else PRODUCER
    schema = COMBINED_SCHEMA if combined else STANDALONE_SCHEMA
    role = COMBINED_ROLE if combined else STANDALONE_ROLE
    from scripts.build_test_shards import SERIAL_BEHAVIORAL_CASE

    expected_nodes = native_nodes | ({SERIAL_BEHAVIORAL_CASE} if combined else set())
    count = 7 if combined else 6
    record = _object(
        value,
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
    if record["schema"] != schema or record["role"] != role or record["source_head"] != producer:
        raise SystemExit("Unreviewed native serial role producer.")
    _hash(record["producer_input_digest"])
    if record["producer_input_digest"] != INPUT_DIGESTS[context]:
        raise SystemExit("Native serial producer input map differs.")
    if record["producer_pre_post_identical"] is not True:
        raise SystemExit("Native serial producer changed during observation.")
    tree = (
        subprocess.check_output(["git", "rev-parse", producer + "^{tree}"], cwd=root)
        .decode()
        .strip()
    )
    runtime = json.loads((root / MANIFEST).read_bytes())["fingerprint"]
    if (
        tree != record["source_tree"]
        or fingerprint(root, producer) != runtime
        or record["runtime_fingerprint"] != runtime
    ):
        raise SystemExit("Native serial producer tree or runtime differs.")
    sources = _object(
        record["source_files"],
        source_paths(root) | (set(COMBINED_IMPORT_FILES) if combined else set()),
        "native serial source closure",
    )
    lines = (
        subprocess.check_output(["git", "ls-tree", "-r", producer], cwd=root).decode().splitlines()
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
        or len(cast(list[str], worker["collected_nodeids"])) != count
    ):
        raise SystemExit("Native serial observation requires its exact local one-worker cases.")
    order = cast(list[str], worker["collected_nodeids"])
    if expected_order is not None and order != expected_order:
        raise SystemExit("Native serial combined order must be legacy first then native six.")
    reports_value = worker.get("reports")
    if not isinstance(reports_value, list):
        raise SystemExit("Native serial complete phase inventory differs.")
    reports = cast(list[object], reports_value)
    if len(reports) != 3 * count or reports != controller.get("reports"):
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
    stage_seconds = math.fsum(phases.values())
    seconds = math.fsum(value for (node, _), value in phases.items() if node in native_nodes)
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
        or not stage_seconds
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
        len(cases) != count
        or frozenset(junit_nodes) != expected_nodes
        or any(
            case.find(tag) is not None for case in cases for tag in ("failure", "error", "skipped")
        )
    ):
        raise SystemExit("Native serial JUnit inventory did not pass its exact case inventory.")
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
    return (
        seconds,
        {
            "role": role,
            "source_head": producer,
            "source_tree": tree,
            "runtime_fingerprint": runtime,
            "producer_input_digest": record["producer_input_digest"],
            "source_applicability": (
                "Measured native/controller/config closure is unchanged; later accounting, QA "
                "and documentation are not the measured global source."
            ),
            "complete_phase_seconds": seconds,
            "stage_complete_phase_seconds": stage_seconds,
            "worker_elapsed_seconds": worker["elapsed_seconds"],
            "controller_elapsed_seconds": controller["elapsed_seconds"],
            "supervisor_elapsed_seconds": supervisor["elapsed_seconds"],
            "cases": order,
            "worker_count": 1,
            "cache_role": "Warm retained selected-source index; fresh worker/module fixtures",
            "source_binding_count": len(sources),
            "additional_binding_role": (
                "Conservative legacy module import context; no claim that unrelated "
                "helper functions execute"
            )
            if combined
            else "Native setup and movement helpers",
            "raw_artifact_sha256": hashes,
        },
        order,
    )


def _source_evidence(
    value: object,
    observation: dict[str, object],
    metadata: dict[str, object],
    order: list[str],
    *,
    context: str,
) -> dict[str, str]:
    from tools.performance_policy import canonical_digest

    names = {"source_preflight", "source_postflight", "progress", "receipt"}
    if context == "with_mirror":
        names.add("admission")
    raw = _object(value, names, "native serial source evidence")
    texts: dict[str, str] = {}
    hashes: dict[str, str] = {}
    for name, value in raw.items():
        artifact = _object(value, {"sha256", "text"}, "native serial source artifact")
        if not isinstance(artifact["text"], str):
            raise SystemExit("Native serial source artifact text is missing.")
        texts[name] = artifact["text"]
        hashes[name] = hashlib.sha256(texts[name].encode()).hexdigest()
        if hashes[name] != artifact["sha256"]:
            raise SystemExit("Native serial source artifact digest differs.")
    pre = cast(dict[str, object], json.loads(texts["source_preflight"]))
    post = cast(dict[str, object], json.loads(texts["source_postflight"]))
    inputs = cast(dict[str, str], pre.get("inputs"))
    if (
        pre.get("head") != metadata["source_head"]
        or post.get("head") != metadata["source_head"]
        or pre.get("tree") != metadata["source_tree"]
        or post.get("tree") != metadata["source_tree"]
        or pre.get("input_digest") != INPUT_DIGESTS[context]
        or post.get("input_digest") != INPUT_DIGESTS[context]
        or canonical_digest(inputs) != INPUT_DIGESTS[context]
        or inputs != post.get("inputs")
        or post.get("identical") is not True
    ):
        raise SystemExit("Native serial original full producer maps differ.")
    for name, digest in cast(dict[str, str], observation["source_files"]).items():
        if name in inputs and inputs[name] != digest:
            raise SystemExit("Native serial closure differs from original producer map.")
    receipt = cast(dict[str, object], json.loads(texts["receipt"]))
    combined = context == "with_mirror"
    inventory_key = "junit_exact_inventory" if combined else "exact_native_inventory"
    if (
        receipt.get("exit_code") != 0
        or receipt.get("source_pre_post_identical") is not True
        or receipt.get("producer_head") != metadata["source_head"]
        or receipt.get("producer_tree") != metadata["source_tree"]
        or receipt.get("input_digest") != INPUT_DIGESTS[context]
        or receipt.get("junit_cases") != len(order)
        or receipt.get(inventory_key) is not True
        or receipt.get("junit_success") is not True
        or receipt.get("complete_suite") is not False
        or receipt.get("coverage_floor_claim") is not False
    ):
        raise SystemExit("Native serial original completion receipt differs.")
    original = cast(dict[str, dict[str, object]], observation["raw"])
    worker = cast(dict[str, object], json.loads(cast(str, original["worker"]["text"])))
    events = cast(
        list[dict[str, object]], [json.loads(line) for line in texts["progress"].splitlines()]
    )
    progress_phases = [
        {key: event[key] for key in ("nodeid", "phase", "seconds", "outcome")}
        for event in events
        if event.get("event") == "phase"
    ]
    collections = [event for event in events if event.get("event") == "collection"]
    starts = [event for event in events if event.get("event") == "session_start"]
    finishes = [event for event in events if event.get("event") == "session_finish"]
    if (
        progress_phases != worker["reports"]
        or len(collections) != 1
        or collections[0].get("nodeids") != order
        or collections[0].get("count") != len(order)
        or [event.get("nodeid") for event in events if event.get("event") == "test_start"] != order
        or len(starts) != 1
        or starts[0].get("worker_count") != "1"
        or len(finishes) != 1
        or finishes[0].get("exit_status") != 0
    ):
        raise SystemExit("Native serial raw progress does not reproduce complete ordered phases.")
    if combined:
        admission = cast(dict[str, object], json.loads(texts["admission"]))
        if (
            admission.get("producer_head") != metadata["source_head"]
            or admission.get("producer_tree") != metadata["source_tree"]
            or admission.get("input_digest") != INPUT_DIGESTS[context]
            or admission.get("case_order") != order
            or admission.get("native_case_order") != order[1:]
            or admission.get("case_count") != 7
            or admission.get("phase_count") != 21
            or admission.get("worker_count") != 1
            or admission.get("automatic_retries") != 0
            or admission.get("inner_runner")
            != {"max_seconds": 120, "max_decisions": 42, "policy_seed": 19}
            or admission.get("supervisor") != {"approval_seconds": 1620, "execution_seconds": 1800}
            or admission.get("source_preflight_sha256") != hashes["source_preflight"]
            or admission.get("command_sha256") != original["command"]["sha256"]
            or admission.get("selected_index_sha256") != original["selected_index"]["sha256"]
            or receipt.get("admission_sha256") != hashes["admission"]
            or receipt.get("native_complete_phase_seconds") != metadata["complete_phase_seconds"]
            or receipt.get("combined_complete_phase_seconds")
            != metadata["stage_complete_phase_seconds"]
        ):
            raise SystemExit("Native serial combined admission or complete phase sum differs.")
    return hashes


def load_native_serial_role(
    root: Path, directory: Path, reference_value: object, expected_nodes: frozenset[str]
) -> NativeSerialRole:
    from scripts.build_test_shards import SERIAL_BEHAVIORAL_CASE

    reference = _object(reference_value, {"file", "sha256"}, "native serial reference")
    path = directory / FILENAME
    if (
        reference["file"] != FILENAME
        or hashlib.sha256(path.read_bytes()).hexdigest() != reference["sha256"]
    ):
        raise SystemExit("Native serial role evidence changed.")
    record = _object(
        read_json(path),
        {"schema", "role", "predecessor", "observations", "source_evidence"},
        "two-context native serial role",
    )
    if record["schema"] != SCHEMA or record["role"] != ROLE:
        raise SystemExit("Unreviewed native serial role contexts.")
    predecessor = _object(
        record["predecessor"], {"source_head", "file", "sha256"}, "native role predecessor"
    )
    if predecessor != {
        "source_head": COMBINED_PRODUCER,
        "file": "ci/test_shards/current-native-serial-role.json",
        "sha256": "a59dbda60a3b695ebb159b973799b2782ad48a00c7f861289e67f8ed3543e2fa",
    }:
        raise SystemExit("Native standalone predecessor binding differs.")
    previous = git_bytes(root, COMBINED_PRODUCER, "ci/test_shards/" + FILENAME)
    if hashlib.sha256(previous).hexdigest() != predecessor["sha256"]:
        raise SystemExit("Native standalone predecessor bytes differ.")
    observations = _object(
        record["observations"], {"standalone", "with_mirror"}, "native observations"
    )
    evidence = _object(
        record["source_evidence"], {"standalone", "with_mirror"}, "native source evidence"
    )
    if observations["standalone"] != json.loads(previous):
        raise SystemExit("Original standalone native observation changed.")
    standalone, standalone_metadata, order = _observation(
        root, observations["standalone"], expected_nodes, context="standalone"
    )
    combined, combined_metadata, combined_order = _observation(
        root,
        observations["with_mirror"],
        expected_nodes,
        context="with_mirror",
        expected_order=[SERIAL_BEHAVIORAL_CASE, *order],
    )
    for context, metadata, observed_order in (
        ("standalone", standalone_metadata, order),
        ("with_mirror", combined_metadata, combined_order),
    ):
        metadata["source_evidence_sha256"] = _source_evidence(
            evidence[context],
            cast(dict[str, object], observations[context]),
            metadata,
            observed_order,
            context=context,
        )
    return NativeSerialRole(
        standalone,
        combined,
        {
            "file": FILENAME,
            "sha256": reference["sha256"],
            "role": ROLE,
            "worker_count": 1,
            "cases": order,
            "standalone_native_phase_seconds": standalone,
            "with_mirror_native_phase_seconds": combined,
            "selection_rule": (
                "Use with_mirror only after legacy mirror in the same ordered serial process; "
                "otherwise standalone. Never select the smaller observation."
            ),
            "observations": {"standalone": standalone_metadata, "with_mirror": combined_metadata},
        },
    )
