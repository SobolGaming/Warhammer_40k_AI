"""Closed source transition with a fresh complete covered profile; no allocation search."""

from __future__ import annotations

import hashlib
import io
import json
import math
import subprocess
import tarfile
from pathlib import Path
from tempfile import TemporaryDirectory
from typing import cast

from scripts.historical_shard_snapshot import MANIFEST, fingerprint, git_bytes
from scripts.hosted_timing_calibration import _object, _seconds, read_json

BASE = "70b1d6ad4b5265fddae30aaf869e4f91471269af"
RUNTIME = "d637f1649b7c3bfee1683c0112ac0ba37233afbf1f9640e6b4f2bbf47fa46c55"
PREVIOUS_RUNTIME = "8d7e3355d9db2c9477ba63b752dc1dfa054b5c00583ea467e3fbbc0e21d5638d"
SCHEMA = "historical-snapshot-fresh-boolean-los-profile-v1"
FILENAME = "current-covered-evidence.json"
MANIFEST_SHA256 = "5d3b31896c265ba5cd152a79d147b8d48cbbecdc1898e8aa593791a7c8eb9312"
RUNTIME_SOURCES = frozenset(
    {
        "src/warhammer40k_core/core/visibility.py",
        "src/warhammer40k_core/engine/shooting_targets.py",
        "src/warhammer40k_core/engine/faction_content/warhammer_40000_11th/thousand_sons/army_rule.py",
        "src/warhammer40k_core/geometry/continuous_visibility.py",
        "src/warhammer40k_core/geometry/physical_visibility.py",
    }
)
VISIBILITY_TEST_SHA256 = "5ae3fa685a0d75855d550b78107b4fe6b810e61d518b880b69ffbe8ed1c935ee"
OWNERSHIP_TEST_SHA256 = "7863b5747eb63c3f6d26562da55d93a6b05f1a41e5f7285eaa54448550430f08"
TEST_SOURCES = {
    "tests/rules/section06/test_visibility.py": VISIBILITY_TEST_SHA256,
    "tests/rules/section06/test_visibility_ownership.py": OWNERSHIP_TEST_SHA256,
}
SOURCE_PRODUCER = "33d199058f2e65f544bcc535e41862e2c09207eb"
SUCCESSOR_FILE = "ci/test_shards/native-charge-source-successor.json"
SUCCESSOR_PATHS = frozenset(
    {
        "tests/support/cavalcade_native_charge.py",
        "docs/performance/policy-v3/operation-map.json",
        "scripts/boolean_los_admission.py",
        "tests/code_quality/test_current_shard_compatibility.py",
    }
)


def producer_inputs(root: Path, producer: str) -> dict[str, str]:
    """Hash the complete original measurement inputs without running old code."""
    from tools.performance_policy import MAP

    if producer != SOURCE_PRODUCER:
        raise SystemExit("Unreviewed covered source producer.")
    archive = subprocess.check_output(
        [
            "git",
            "archive",
            producer,
            "src",
            "tests",
            "scripts",
            "tools",
            "contracts/schemas",
            "uv.lock",
            "pyproject.toml",
            MAP,
        ],
        cwd=root,
        stderr=subprocess.PIPE,
        timeout=30,
    )
    inputs = {}
    with tarfile.open(fileobj=io.BytesIO(archive)) as stream:
        for member in stream:
            if member.isfile():
                source = stream.extractfile(member)
                assert source is not None
                inputs[member.name] = hashlib.sha256(source.read()).hexdigest()
    return dict(sorted(inputs.items()))


def validate_successor(historical: dict[str, str], live: dict[str, str], record: object) -> None:
    """Admit only this finite reviewed delta; reject every other source change."""
    scope = _object(record, {"schema", "producer", "changes"}, "covered source successor")
    if (scope["schema"], scope["producer"]) != (
        "native-charge-source-successor-v1",
        SOURCE_PRODUCER,
    ):
        raise SystemExit("Unreviewed covered source successor.")
    changes = _object(scope["changes"], set(SUCCESSOR_PATHS), "successor changes")
    expected = historical.copy()
    for name, value in changes.items():
        row = _object(value, {"before", "after"}, "successor source hashes")
        after = row["after"]
        if (
            row["before"] != historical.get(name)
            or not isinstance(after, str)
            or len(after) != 64
            or any(c not in "0123456789abcdef" for c in after)
            or after == row["before"]
        ):
            raise SystemExit("Covered source successor hashes differ: " + name)
        expected[name] = after
    # The original producer remains valid for its own evidence. A successor must
    # include every declared new/changed file, with no unlisted source drift.
    if live != historical and live != expected:
        raise SystemExit("Live covered sources differ from the exact reviewed successor.")


def validate_manifest(raw: bytes) -> None:
    if hashlib.sha256(raw).hexdigest() != MANIFEST_SHA256:
        raise SystemExit("Unreviewed Boolean LOS manifest bytes.")


def validate_transition(root: Path) -> None:
    from warhammer40k_core import build_identity

    validate_manifest((root / MANIFEST).read_bytes())
    package_checkout = Path(build_identity.__file__).resolve().parents[2]
    if package_checkout != root.resolve():
        raise SystemExit("Boolean LOS admission requires its actual runtime checkout.")
    # Rebuild from live resource bytes on every admission. The ordinary cached
    # runtime identity cannot authenticate a supplied root or same-process drift.
    expected = build_identity.canonical_engine_build_manifest_text(
        build_identity.build_engine_manifest_payload()
    ).encode()
    if expected != (root / MANIFEST).read_bytes():
        raise SystemExit("Boolean LOS live runtime source differs from the reviewed manifest.")
    if (
        fingerprint(root, BASE) != PREVIOUS_RUNTIME
        or json.loads((root / MANIFEST).read_bytes())["fingerprint"] != RUNTIME
    ):
        raise SystemExit("Unreviewed Boolean LOS runtime transition.")
    for name, digest in TEST_SOURCES.items():
        if hashlib.sha256((root / name).read_bytes()).hexdigest() != digest:
            raise SystemExit("Unreviewed Boolean LOS test source: " + name)


def transitioned_test(root: Path, owner: str, current: bytes, historical: bytes) -> bool:
    if owner not in TEST_SOURCES:
        return False
    validate_transition(root)
    if hashlib.sha256(current).hexdigest() != TEST_SOURCES[owner] or historical != git_bytes(
        root, BASE, owner
    ):
        raise SystemExit("Boolean LOS test transition differs from its exact reviewed sources.")
    return True


def _text(value: object) -> str:
    item = _object(value, {"sha256", "text"}, "fresh covered artifact")
    text = item["text"]
    if not isinstance(text, str) or hashlib.sha256(text.encode()).hexdigest() != item["sha256"]:
        raise SystemExit("Fresh covered artifact digest differs.")
    return text


def fresh_native_role(
    root: Path,
    directory: Path,
    descriptor: dict[str, object],
    baseline: dict[str, object],
    previous: dict[str, object],
) -> tuple[float, dict[str, object]]:
    """Join complete current JUnit, phases, source maps and approval receipt."""
    from tools.performance_policy import canonical_digest, runtime_inputs

    from scripts import build_test_shards as sharding

    validate_transition(root)
    reference = _object(
        descriptor["fresh_evidence"], {"file", "sha256"}, "fresh evidence reference"
    )
    path = directory / FILENAME
    if (
        reference["file"] != FILENAME
        or hashlib.sha256(path.read_bytes()).hexdigest() != reference["sha256"]
    ):
        raise SystemExit("Fresh covered evidence reference differs.")
    record = _object(
        read_json(path),
        {
            "schema",
            "preflight",
            "postflight",
            "supervisor",
            "serial_worker",
            "parallel_workers",
            "serial_junit",
            "parallel_junit",
            "coverage",
            "stages",
        },
        "fresh covered evidence",
    )
    if record["schema"] != "complete-covered-source-and-phase-evidence-v1":
        raise SystemExit("Unreviewed fresh covered evidence schema.")
    pre = cast(dict[str, object], json.loads(_text(record["preflight"])))
    post = cast(dict[str, object], json.loads(_text(record["postflight"])))
    inputs = producer_inputs(root, str(baseline["source_head"]))
    tree = subprocess.check_output(
        ["git", "rev-parse", str(baseline["source_head"]) + "^{tree}"], cwd=root, text=True
    ).strip()
    if (
        pre.get("head") != baseline["source_head"]
        or post.get("head") != baseline["source_head"]
        or pre.get("tree") != tree
        or pre.get("inputs") != inputs
        or pre.get("input_digest") != canonical_digest(inputs)
        or post.get("input_digest") != pre["input_digest"]
        or post.get("inputs_unchanged") is not True
    ):
        raise SystemExit("Fresh covered source pre/post identity differs.")
    validate_successor(inputs, runtime_inputs(root), read_json(root / SUCCESSOR_FILE))
    supervisor = json.loads(_text(record["supervisor"]))
    if supervisor != baseline["supervisor"]:
        raise SystemExit("Fresh covered supervisor differs from the approved baseline.")
    stages = json.loads(_text(record["stages"]))
    if [stage["name"] for stage in stages] != [
        "source-history",
        "cold-source-index",
        "serial-native-and-mirror",
        "parallel-behavior",
    ] or any(stage["exit_code"] != 0 for stage in stages):
        raise SystemExit("Fresh covered source/index/test stages are incomplete.")
    coverage = json.loads(_text(record["coverage"]))
    if coverage["meta"]["branch_coverage"] is not True or (
        coverage["totals"]["percent_covered"] != baseline["coverage_percent"]
    ):
        raise SystemExit("Fresh covered branch coverage differs.")
    serial = cast(dict[str, object], json.loads(_text(record["serial_worker"])))
    native_nodes = cast(list[str], previous["cases"])
    serial_nodes = [sharding.SERIAL_BEHAVIORAL_CASE, *native_nodes]
    parallel_nodes = set(cast(dict[str, float], baseline["case_seconds"])) - set(serial_nodes)
    workers_value = record["parallel_workers"]
    if not isinstance(workers_value, dict) or workers_value.keys() != {f"gw{i}" for i in range(32)}:
        raise SystemExit("Fresh covered profile requires exactly 32 parallel workers.")
    workers = {name: json.loads(_text(value)) for name, value in workers_value.items()}
    phases: dict[tuple[str, str], float] = {}
    for name, worker in {"serial": serial, **workers}.items():
        is_serial = name == "serial"
        expected = set(serial_nodes) if is_serial else parallel_nodes
        collected = worker.get("collected_nodeids")
        if (
            worker.get("worker_count") != ("1" if is_serial else "32")
            or worker.get("worker") != ("gw0" if is_serial else name)
            or worker.get("exit_status") != 0
            or not isinstance(collected, list)
            or len(collected) != len(expected)
            or set(collected) != expected
            or (is_serial and collected != serial_nodes)
        ):
            raise SystemExit("Fresh covered worker or collection inventory differs.")
        for value in worker["reports"]:
            row = _object(value, {"nodeid", "phase", "seconds", "outcome"}, "fresh covered phase")
            node, phase = str(row["nodeid"]), str(row["phase"])
            if (
                node not in expected
                or phase not in {"setup", "call", "teardown"}
                or row["outcome"] != "passed"
                or (node, phase) in phases
            ):
                raise SystemExit(
                    "Fresh covered phases are repeated, unsuccessful or outside inventory."
                )
            phases[node, phase] = _seconds(row["seconds"])
    if phases.keys() != {
        (node, phase)
        for node in (*serial_nodes, *parallel_nodes)
        for phase in ("setup", "call", "teardown")
    }:
        raise SystemExit("Fresh covered phase inventory is incomplete.")
    with TemporaryDirectory(prefix="boolean-los-profile-") as tmp:
        temporary = Path(tmp)
        for side in ("serial", "parallel"):
            (temporary / (side + ".xml")).write_text(
                _text(record[side + "_junit"]), encoding="utf-8"
            )
        source = str(cast(list[dict[str, object]], baseline["profiles"])[0]["source"])
        durations, profiles = sharding._profile_medians((temporary,), (source,))
        cases = sharding._case_profile_medians((temporary,))
        files = sharding._rounded_durations(
            sharding._partitioned_durations(durations, case_seconds=cases)
        )
    if (
        cases != baseline["case_seconds"]
        or files != baseline["files"]
        or list(profiles) != baseline["profiles"]
    ):
        raise SystemExit(
            "Fresh complete JUnit differs from current scheduling weights or provenance."
        )
    native_seconds = math.fsum(value for (node, _), value in phases.items() if node in native_nodes)
    metadata = dict(previous)
    metadata.update(
        {
            "role": "Fresh combined native phases; historical standalone is inactive",
            "fresh_evidence": reference,
            "with_mirror_native_phase_seconds": native_seconds,
            "selected_current_context": "with_mirror",
            "standalone_role": "Historical only; forbidden for current allocation",
            "selection_rule": "Frozen combined allocation uses fresh with_mirror only",
            "historical_observations": previous["observations"],
            "fresh_source_head": baseline["source_head"],
            "fresh_runtime_fingerprint": RUNTIME,
        }
    )
    return native_seconds, metadata
