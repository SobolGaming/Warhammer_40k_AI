"""Validate exact-base applicability and execute the mandatory serial live smoke."""

from __future__ import annotations

import argparse
import datetime as dt
import importlib
import json
import os
import platform
import subprocess
import sys
import time
from collections.abc import Callable
from pathlib import Path
from typing import cast

from scripts.performance_smoke import CASE_LIMIT_SECONDS, CASES, PROCESS_LIMIT_SECONDS, WORKLOAD
from tools.performance_policy import (
    ASSESSMENT,
    MAP,
    POLICY,
    canonical_digest,
    changed_inputs,
    digest,
    git,
    object_value,
    read_object,
    runtime_inputs,
    validate_assessment,
    validate_comparison,
    validate_full_game,
)

ROOT = Path(__file__).resolve().parents[1]


def run_smoke(root: Path, output: Path, *, binding: dict[str, object]) -> dict[str, object]:
    started = dt.datetime.now(dt.UTC)
    attempt = output.parent / "performance-attempts" / started.strftime("%Y%m%dT%H%M%S%fZ")
    attempt.mkdir(parents=True, exist_ok=False)
    # Load the retained platform-specific metadata utility at execution time;
    # historical driver code and its measurement loops remain unchanged.
    host_inventory = cast(
        Callable[[], tuple[str, int]],
        importlib.import_module("scripts.measure_order65")._host_inventory,
    )
    cpu, memory = host_inventory()
    report: dict[str, object] = {
        **binding,
        "policy": POLICY,
        "workload": WORKLOAD,
        "started_at": started.isoformat(),
        "status": "running",
        "attempt_receipt": str(attempt / "receipt.json"),
        "host": {
            "cpu": cpu,
            "memory_bytes": memory,
            "logical_cpus": os.cpu_count(),
            "platform": platform.platform(),
            "python": platform.python_version(),
            "role": "provisional",
            "concurrency": 1,
            "coverage": False,
        },
        "case_limit_seconds": CASE_LIMIT_SECONDS,
        "process_limit_seconds": PROCESS_LIMIT_SECONDS,
        "cases": [],
    }
    rows: list[dict[str, object]] = []
    start = time.perf_counter()
    for case in CASES:
        result_path = attempt / f"{case}.json"
        command = [
            sys.executable,
            "-m",
            "scripts.performance_smoke",
            "--case",
            case,
            "--output",
            str(result_path),
        ]
        elapsed = time.perf_counter() - start
        timeout = min(CASE_LIMIT_SECONDS, PROCESS_LIMIT_SECONDS - elapsed)
        if timeout <= 0:
            report["status"] = "timeout"
            break
        case_start = time.perf_counter()
        with (attempt / f"{case}.log").open("wb") as log:
            child = subprocess.Popen(command, cwd=root, stdout=log, stderr=subprocess.STDOUT)
            timed_out = False
            try:
                code = child.wait(timeout=timeout)
            except subprocess.TimeoutExpired:
                child.kill()
                child.wait(timeout=10)
                timed_out, code = True, 124
        row: dict[str, object] = {
            "case": case,
            "command": command,
            "pid": child.pid,
            "exit_code": code,
            "timed_out": timed_out,
            "process_seconds": time.perf_counter() - case_start,
            "result": read_object(result_path) if result_path.is_file() else None,
        }
        rows.append(row)
        if code != 0 or timed_out or row["result"] is None:
            report["status"] = "failed"
            break
    report["cases"] = rows
    report["total_seconds"] = time.perf_counter() - start
    report["finished_at"] = dt.datetime.now(dt.UTC).isoformat()
    if report["status"] == "running":
        report["status"] = "passed"
    try:
        validate_smoke_report(report, binding=binding)
    except ValueError as error:
        report["status"] = "failed"
        report["error"] = str(error)
        _write_receipt(output, report)
        raise
    _write_receipt(output, report)
    return report


def _write_receipt(output: Path, report: dict[str, object]) -> None:
    text = json.dumps(report, indent=2) + "\n"
    Path(str(report["attempt_receipt"])).write_text(text, encoding="utf-8")
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(text, encoding="utf-8")


def validate_smoke_report(report: dict[str, object], *, binding: dict[str, object]) -> None:
    if any(report.get(key) != value for key, value in binding.items()):
        raise ValueError("Current smoke receipt is stale for the actual inputs/base/head.")
    if report.get("status") != "passed" or report.get("workload") != WORKLOAD:
        raise ValueError("Required live performance smoke did not pass.")
    if (
        report.get("case_limit_seconds") != CASE_LIMIT_SECONDS
        or report.get("process_limit_seconds") != PROCESS_LIMIT_SECONDS
    ):
        raise ValueError("Smoke limits drifted.")
    total = report.get("total_seconds")
    if not isinstance(total, (float, int)) or not 0 < total <= PROCESS_LIMIT_SECONDS:
        raise ValueError("Smoke process limit exceeded.")
    rows = report.get("cases")
    if not isinstance(rows, list) or len(rows) != len(CASES):
        raise ValueError("Required smoke cases missing.")
    for raw, case in zip(rows, CASES, strict=True):
        row = object_value(raw)
        result = object_value(row["result"])
        seconds = row["process_seconds"]
        if (
            row["case"] != case
            or row["exit_code"] != 0
            or row["timed_out"] is not False
            or result.get("case") != case
            or result.get("complete") is not True
        ):
            raise ValueError("A required smoke case failed or is incomplete.")
        if not isinstance(seconds, (float, int)) or not 0 < seconds <= CASE_LIMIT_SECONDS:
            raise ValueError("Smoke case limit exceeded.")


def validate_current(root: Path, base_ref: str, *, pr_head: str | None) -> dict[str, object]:
    from warhammer40k_core.build_identity import verified_engine_build_identity

    base, changes = changed_inputs(root, base_ref)
    head = git(root, "rev-parse", "HEAD").decode().strip()
    if pr_head:
        git(root, "merge-base", "--is-ancestor", pr_head, head)
    runtime_id = verified_engine_build_identity().build_id
    assessment = read_object(root / ASSESSMENT)
    operation_map = read_object(root / MAP)
    selected = validate_assessment(
        assessment, base=base, changes=changes, runtime_id=runtime_id, operation_map=operation_map
    )
    inputs = runtime_inputs(root)
    input_digest = canonical_digest(inputs)
    comparisons = object_value(assessment["comparisons"])
    families = object_value(operation_map["families"])
    base_identity = object_value(
        json.loads(git(root, "show", f"{base}:src/warhammer40k_core/_engine_build_manifest.json"))
    )["build_id"]
    if not isinstance(base_identity, str):
        raise TypeError("Base runtime identity missing.")
    for family in sorted(selected):
        path = comparisons[family]
        if (
            not isinstance(path, str)
            or not path.startswith("docs/performance/current/")
            or ".." in Path(path).parts
        ):
            raise ValueError("Current comparisons need their own committed evidence path.")
        specification = object_value(families[family])
        driver = specification["driver"]
        if not isinstance(driver, str) or driver not in inputs:
            raise ValueError("Selected measurement driver is missing.")
        validate_comparison(
            read_object(root / path),
            base=base,
            runtime_id=runtime_id,
            input_digest=input_digest,
            family=family,
            specification=specification,
            base_runtime_id=base_identity,
            expected_inputs={
                "lock_sha256": inputs["uv.lock"],
                "workload_sha256": inputs[driver],
                "fixture_sha256": canonical_digest(
                    {
                        name: value
                        for name, value in inputs.items()
                        if name.startswith(("tests/", "scripts/"))
                        and not name.startswith("tests/code_quality/")
                    }
                ),
            },
        )
    if assessment["milestone"] == "rules_complete":
        path = assessment["full_game"]
        if not isinstance(path, str) or not path.startswith("docs/performance/current/"):
            raise ValueError("Missing current full-game evidence path.")
        full_game = read_object(root / path)
        driver = full_game.get("driver")
        registered = object_value(operation_map["full_game_profiles"])
        if not isinstance(driver, str) or driver not in registered or driver not in inputs:
            raise ValueError("Supported full-game workload is not registered/available.")
        validate_full_game(
            full_game,
            base=base,
            runtime_id=runtime_id,
            input_digest=input_digest,
            workload_sha256=inputs[driver],
        )
    return {
        "base_revision": base,
        "checkout_head": head,
        "pull_request_head": pr_head,
        "runtime_build_id": runtime_id,
        "input_digest": input_digest,
        "inputs": inputs,
        "changed_input_digest": canonical_digest(changes),
        "assessment_sha256": digest((root / ASSESSMENT).read_bytes()),
        "selected_families": sorted(selected),
    }


def _check_and_run(base_ref: str, pr_head: str | None, output: Path) -> dict[str, object]:
    binding = validate_current(ROOT, base_ref, pr_head=pr_head)
    report = run_smoke(ROOT, output, binding=binding)
    # An edit during measurements cannot inherit the completed receipt.
    if binding != validate_current(ROOT, base_ref, pr_head=pr_head):
        report["status"] = "failed"
        report["inputs_unchanged"] = False
        _write_receipt(output, report)
        raise ValueError("Performance inputs changed during the required smoke.")
    report["inputs_unchanged"] = True
    _write_receipt(output, report)
    return binding


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--base-ref", required=True)
    parser.add_argument("--pr-head")
    parser.add_argument("--output", type=Path, default=ROOT / "reports/performance-smoke.json")
    args = parser.parse_args()
    output = args.output.resolve()
    try:
        binding = _check_and_run(args.base_ref, args.pr_head, output)
    except (ValueError, TypeError, OSError, subprocess.CalledProcessError) as error:
        stamp = dt.datetime.now(dt.UTC).strftime("%Y%m%dT%H%M%S%fZ")
        failure_path = output.parent / "performance-attempts" / f"{stamp}-gate-failure.json"
        failure_path.parent.mkdir(parents=True, exist_ok=True)
        failure = {
            "policy": POLICY,
            "status": "failed",
            "base_ref": args.base_ref,
            "pull_request_head": args.pr_head,
            "error_type": type(error).__name__,
            "error": str(error),
            "attempt_receipt": str(failure_path),
        }
        _write_receipt(output, failure)
        raise
    print(
        json.dumps(
            {
                "status": "passed",
                "report": str(args.output),
                "base": binding["base_revision"],
                "head": binding["checkout_head"],
                "input_digest": binding["input_digest"],
            }
        )
    )


if __name__ == "__main__":
    main()
