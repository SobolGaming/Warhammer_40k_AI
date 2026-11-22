"""One cold complete local profile, supervised at the unchanged 1620/1800 limits.

This measures all selected behavior once with coverage: one cold mirror producer,
then 32 work-stealing workers sharing its source-bound command checkpoint.
It does not search or change allocations.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import subprocess
import sys
import time
import uuid
from pathlib import Path

from scripts.behavioral_deadline import supervise

ROOT = Path(__file__).resolve().parents[1]


def _write(path: Path, value: object) -> None:
    path.write_text(
        json.dumps(value, indent=2, sort_keys=True) + "\n", encoding="utf-8", newline="\n"
    )


def _source() -> dict[str, object]:
    from tools.performance_policy import canonical_digest, runtime_inputs

    head = subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=ROOT, text=True).strip()
    tree = subprocess.check_output(["git", "rev-parse", "HEAD^{tree}"], cwd=ROOT, text=True).strip()
    inputs = runtime_inputs(ROOT)
    return {"head": head, "tree": tree, "inputs": inputs, "input_digest": canonical_digest(inputs)}


def _stage(
    name: str,
    commands: list[list[str]],
    *,
    output: Path,
    environment: dict[str, str],
    stages: list[dict[str, object]],
) -> int:
    started = time.monotonic()
    entry: dict[str, object] = {
        "name": name,
        "commands": commands,
        "started_monotonic": started,
        "exit_code": None,
    }
    stages.append(entry)
    _write(output / "stages.json", stages)
    print(json.dumps({"stage": name, "event": "started"}), flush=True)
    status = 0
    with (output / f"{name}.log").open("wb") as log:
        for command in commands:
            status = subprocess.run(
                command,
                cwd=ROOT,
                env=environment,
                stdout=log,
                stderr=subprocess.STDOUT,
                check=False,
            ).returncode
            if status != 0:
                break
    entry.update({"exit_code": status, "elapsed_seconds": time.monotonic() - started})
    _write(output / "stages.json", stages)
    print(json.dumps(entry), flush=True)
    return status


def coverage_report_command(output: Path) -> list[str]:
    """Generate complete JSON and enforce the unchanged floor in one analysis."""
    return [
        sys.executable,
        "-B",
        "-m",
        "coverage",
        "json",
        "--fail-under=68",
        "-o",
        str(output / "coverage.json"),
    ]


def run_worker(output: Path) -> int:
    from tools.ability_support_sources import ability_support_index_inputs

    from scripts.build_test_shards import SERIAL_BEHAVIORAL_CASE, behavioral_selection
    from warhammer40k_core.rules.selected_source_index import source_input_hashes

    with (output / "run-started.json").open("x", encoding="utf-8") as marker:
        json.dump({"workers": 32, "mirror_workers": 1, "coverage_floor": 68}, marker)
    environment = dict(os.environ)
    environment["PYTHONDONTWRITEBYTECODE"] = "1"
    environment["PYTEST_XDIST_AUTO_NUM_WORKERS"] = "32"
    environment["TEST_TIMING_PROGRESS"] = "1"
    # A fresh baseline precedes its new dispatch profile. No old-runtime profile
    # can be promoted as current or used to invent costs for the new cases.
    environment.pop("BEHAVIORAL_DISPATCH_PROFILE", None)
    environment["COVERAGE_FILE"] = str(output / ".coverage")
    environment["WH40K_COVERED_FIXTURE_CACHE"] = str(output / "fixture-checkpoints")
    environment["WH40K_COVERED_FIXTURE_RUN_ID"] = uuid.uuid4().hex
    pre = _source()
    _write(output / "source-preflight.json", pre)
    stages: list[dict[str, object]] = []
    python = [sys.executable, "-B"]
    status = _stage(
        "source-history",
        [
            [*python, "scripts/fetch_scheduling_sources.py"],
            [*python, "-m", "scripts.validate_source_history"],
        ],
        output=output,
        environment=environment,
        stages=stages,
    )
    if status != 0:
        return status
    source = ROOT / "data/source_snapshots/wahapedia/10th-edition/2026-06-14/json"
    identity = {
        "python": sys.version,
        "inputs": source_input_hashes(ability_support_index_inputs(source)),
    }
    digest = hashlib.sha256(
        json.dumps(identity, sort_keys=True, separators=(",", ":")).encode()
    ).hexdigest()
    input_key = "selected-source-index-v1-" + digest
    index = output / "selected-source-index"
    if index.exists():
        raise ValueError(
            "Complete current profile requires a genuinely cold selected-source index."
        )
    _write(output / "source-index-inputs.json", {"key": input_key, "identity": identity})
    status = _stage(
        "cold-source-index",
        [
            [
                *python,
                "-m",
                "scripts.ci_source_index",
                str(source),
                str(index),
                str(output / "source-index-result.json"),
                input_key,
            ]
        ],
        output=output,
        environment=environment,
        stages=stages,
    )
    if status != 0:
        return status
    common = [
        *python,
        "-m",
        "pytest",
        "--dist=worksteal",
        "-o",
        "faulthandler_timeout=180",
        "-o",
        "faulthandler_exit_on_timeout=false",
        "--selected-army-source-index=" + str(index),
        "--cov=warhammer40k_core",
        "--cov-report=",
        "--cov-fail-under=0",
        "--durations=100",
        "--durations-min=0.1",
    ]
    serial_environment = {**environment, "TEST_TIMING_DIR": str(output / "serial-timing")}
    status = _stage(
        "serial-native-and-mirror",
        [
            [
                *common,
                SERIAL_BEHAVIORAL_CASE,
                "-n",
                "1",
                "--junitxml=" + str(output / "serial.xml"),
            ]
        ],
        output=output,
        environment=serial_environment,
        stages=stages,
    )
    if status != 0:
        return status
    parallel = list(behavioral_selection(ROOT).active_files)
    _write(
        output / "selected-files.json",
        {
            "serial": [SERIAL_BEHAVIORAL_CASE],
            "parallel": parallel,
            "parallel_deselect": [SERIAL_BEHAVIORAL_CASE],
        },
    )
    parallel_environment = {**environment, "TEST_TIMING_DIR": str(output / "parallel-timing")}
    status = _stage(
        "parallel-behavior",
        [
            [
                *common,
                *parallel,
                "--deselect=" + SERIAL_BEHAVIORAL_CASE,
                "--cov-append",
                "-n",
                "32",
                "--junitxml=" + str(output / "parallel.xml"),
            ],
            coverage_report_command(output),
        ],
        output=output,
        environment=parallel_environment,
        stages=stages,
    )
    if status == 0:
        totals = json.loads((output / "coverage.json").read_bytes())["totals"]
        print(json.dumps({"coverage_totals": totals}), flush=True)
    post = _source()
    post["inputs_unchanged"] = (
        post["head"] == pre["head"]
        and post["tree"] == pre["tree"]
        and post["inputs"] == pre["inputs"]
    )
    _write(output / "source-postflight.json", post)
    if post["inputs_unchanged"] is not True:
        raise ValueError("Complete current profile source changed during execution.")
    return status


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--worker", action="store_true", help=argparse.SUPPRESS)
    arguments = parser.parse_args()
    output = arguments.output.resolve()
    if arguments.worker:
        return run_worker(output)
    if output.exists():
        raise ValueError("Refusing to overwrite a prior complete-profile attempt.")
    return supervise(
        [
            sys.executable,
            "-B",
            "-m",
            "scripts.run_complete_covered_profile",
            "--worker",
            "--output",
            str(output),
        ],
        report_dir=output / "supervisor",
        approval_seconds=1620,
        execution_seconds=1800,
    )


if __name__ == "__main__":
    raise SystemExit(main())
