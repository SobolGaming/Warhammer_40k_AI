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
from pathlib import Path, PurePosixPath
from typing import cast

from tools.performance_category_migration import applies as migration_applies
from tools.performance_order103_exception import retained_comparison_inputs
from tools.performance_policy import (
    ASSESSMENT,
    MAP,
    POLICY,
    canonical_digest,
    changed_inputs,
    digest,
    git,
    object_value,
    prototype_comparison_deferral,
    read_object,
    runtime_inputs,
    validate_assessment,
    validate_comparison,
    validate_full_game,
)
from tools.performance_preflight import ci60_repository_identity, invocation, source_hashes
from tools.performance_tool_inputs import (
    SCHEMA as HISTORICAL_TOOL_SCHEMA,
)
from tools.performance_tool_inputs import (
    binding_enabled,
    comparison_inputs,
    retained_tool_comparison_inputs,
)

from scripts.performance_smoke import CASE_LIMIT_SECONDS, CASES, PROCESS_LIMIT_SECONDS, WORKLOAD

ROOT = Path(__file__).resolve().parents[1]


def _fresh_comparison_metadata(
    assessment: dict[str, object],
    reports: dict[str, dict[str, object]],
    *,
    base: str,
    runtime_id: str,
    input_digest: str,
    base_paths: set[str],
    input_bound_families: set[str],
) -> bool:
    """Classify generic fresh evidence; never reinterpret a retained input role."""
    if (assessment.get("base"), assessment.get("runtime_build_id")) != (base, runtime_id):
        raise ValueError("Fresh comparison assessment has stale base/runtime identities.")
    comparisons = object_value(assessment["comparisons"])
    if not comparisons or comparisons.keys() != reports.keys():
        raise ValueError("Fresh comparison selection is empty or incomplete.")
    from tools import performance_tool_inputs_v4 as exact

    routes: set[str] = set()
    for family, report in reports.items():
        binding = report.get("input_binding")
        exact_binding = (
            family in input_bound_families
            and family == "external_contract_source_reuse"
            and isinstance(binding, dict)
            and binding.get("schema") == exact.SCHEMA
        )
        if exact_binding and base != exact.BASE:
            raise ValueError("V4 current admission requires the exact PR600 base.")
        if not exact_binding and (
            family in input_bound_families
            or {"owner_exception", "input_binding", "ordered_pairs"} & report.keys()
            or report.get("schema") == "matched-reconstruction-abba-v1"
        ):
            routes.add("retained")
            continue
        if report.keys() != {
            "policy",
            "family",
            "workload_id",
            "base_revision",
            "head_runtime_build_id",
            "head_input_digest",
            "budget_profile",
            "base",
            "head",
            "historical_failures",
        } | ({"input_binding", "generated_output_binding"} if exact_binding else set()):
            raise ValueError("Fresh comparisons require the closed generic report format.")
        if comparisons[family] in base_paths:
            raise ValueError(
                "Fresh comparison evidence must be newly added against the actual base."
            )
        if (
            report["policy"],
            report["family"],
            report["base_revision"],
            report["head_runtime_build_id"],
            report["head_input_digest"],
        ) != (POLICY, family, base, runtime_id, input_digest):
            raise ValueError("Fresh comparison has stale or unrelated identities.")
        routes.add("current")
    if len(routes) != 1:
        raise ValueError("Fresh and retained comparison routes cannot be mixed.")
    return routes == {"current"}


def _uses_fresh_current_comparisons(
    root: Path, assessment: dict[str, object], base_ref: str
) -> bool:
    from tools import performance_ci60_qualification as ci60
    from tools import performance_order103_exception as order103
    from tools import performance_reconstruction_campaign as reconstruction

    from warhammer40k_core.build_identity import verified_engine_build_identity

    if assessment.get("milestone") != "ordinary":
        return False
    base = git(root, "rev-parse", "--verify", f"{base_ref}^{{commit}}").decode().strip()
    # These retained cohorts keep their original phase admission and input bridges.
    if base in {ci60.PR_BASE, order103.BASE, reconstruction.BASE}:
        return False
    comparisons = object_value(assessment["comparisons"])
    reports: dict[str, dict[str, object]] = {}
    for family, path in comparisons.items():
        if (
            not isinstance(path, str)
            or not path.startswith("docs/performance/current/")
            or PurePosixPath(path).as_posix() != path
            or PurePosixPath(path).suffix != ".json"
            or ".." in PurePosixPath(path).parts
            or "\\" in path
            or ":" in path
        ):
            raise ValueError("Fresh comparisons need a canonical current JSON evidence path.")
        member = root
        for part in PurePosixPath(path).parts:
            member /= part
            if member.is_symlink():
                raise ValueError("Fresh comparison evidence cannot contain symlink aliases.")
        reports[family] = read_object(member)
    families = object_value(read_object(root / MAP)["families"])
    return _fresh_comparison_metadata(
        assessment,
        reports,
        base=base,
        runtime_id=verified_engine_build_identity().build_id,
        input_digest=canonical_digest(runtime_inputs(root)),
        base_paths=set(git(root, "ls-tree", "-r", "--name-only", "-z", base).decode().split("\0")),
        input_bound_families={
            family
            for family, specification in families.items()
            if binding_enabled(family, object_value(specification))
        },
    )


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


def _base_manifest(root: Path, base: str) -> bytes:
    from tools.performance_history_snapshot import historical

    args = ("show", f"{base}:src/warhammer40k_core/_engine_build_manifest.json")
    return historical(root, "safe60", args, lambda: git(root, *args))


@invocation
def validate_current(root: Path, base_ref: str, *, pr_head: str | None) -> dict[str, object]:
    assessment = read_object(root / ASSESSMENT)
    deferred = assessment.get("comparison_disposition") == "deferred"
    ordinary_without_comparisons = (
        assessment.get("milestone") == "ordinary" and assessment.get("comparisons") == {}
    )
    if (
        deferred
        or ordinary_without_comparisons
        or _uses_fresh_current_comparisons(root, assessment, base_ref)
    ):
        from scripts.quality_evidence import dependency_identity, source_identity

        base = git(root, "rev-parse", "--verify", f"{base_ref}^{{commit}}").decode().strip()
        if deferred and prototype_comparison_deferral(root, base=base) is None:
            raise ValueError("Missing explicit finite prototype disposition.")
        if any(
            name in os.environ
            for name in (
                "GIT_DIR",
                "GIT_WORK_TREE",
                "GIT_COMMON_DIR",
                "GIT_INDEX_FILE",
                "GIT_OBJECT_DIRECTORY",
                "GIT_ALTERNATE_OBJECT_DIRECTORIES",
                "GIT_NAMESPACE",
            )
        ):
            raise ValueError("Inherited Git repository role override is unsupported.")
        if (
            root != root.resolve()
            or Path(git(root, "rev-parse", "--show-toplevel").decode().strip()).resolve() != root
        ):
            raise ValueError("Current verification requires its canonical checkout root.")
        transaction_identity = ci60_repository_identity(root)
        repository = {
            key: str((root / git(root, "rev-parse", flag).decode().strip()).resolve(strict=True))
            for key, flag in (("git_dir", "--git-dir"), ("common_dir", "--git-common-dir"))
        }
        names = set(git(root, "ls-files", "-z").decode().split("\0")) - {""}
        before = source_identity(root)
        owned = canonical_digest(source_hashes(root, names))
        dependencies = dependency_identity()
        binding = _validate_current(root, base_ref, pr_head=pr_head)
        after_names = set(git(root, "ls-files", "-z").decode().split("\0")) - {""}
        after_repository = {
            key: str((root / git(root, "rev-parse", flag).decode().strip()).resolve(strict=True))
            for key, flag in (("git_dir", "--git-dir"), ("common_dir", "--git-common-dir"))
        }
        if (
            transaction_identity != ci60_repository_identity(root)
            or before != source_identity(root)
            or names != after_names
            or owned != canonical_digest(source_hashes(root, after_names))
            or repository != after_repository
            or dependencies != dependency_identity()
        ):
            raise ValueError("Current source/repository/dependencies changed during validation.")
        disposition = (
            {
                "comparison_disposition": "deferred",
                "historical_comparison_qualification": "deferred",
            }
            if deferred
            else {}
        )
        return (
            binding
            | disposition
            | {
                "repository_identity": repository,
                "current_source_identity": before,
                "stable_current_source_digest": owned,
                "dependency_identity": json.loads(
                    json.dumps(dependencies, sort_keys=True, separators=(",", ":"), allow_nan=False)
                ),
            }
        )

    from tools.performance_history_snapshot import phase

    with phase(root, base_ref, pr_head) as snapshot:
        binding = _validate_current(root, base_ref, pr_head=pr_head)
        return binding | {"history_snapshot_digest": snapshot.semantic_digest}


def _validate_current(root: Path, base_ref: str, *, pr_head: str | None) -> dict[str, object]:
    from warhammer40k_core.build_identity import verified_engine_build_identity

    base, changes = changed_inputs(root, base_ref)
    head = git(root, "rev-parse", "HEAD").decode().strip()
    if pr_head:
        git(root, "merge-base", "--is-ancestor", pr_head, head)
    runtime_id = verified_engine_build_identity().build_id
    assessment = read_object(root / ASSESSMENT)
    operation_map = read_object(root / MAP)
    deferred = assessment.get("comparison_disposition") == "deferred"
    if deferred and prototype_comparison_deferral(root, base=base) is None:
        raise ValueError("Missing finite prototype comparison disposition.")
    selected = validate_assessment(
        assessment, base=base, changes=changes, runtime_id=runtime_id, operation_map=operation_map
    )
    inputs = runtime_inputs(root)
    input_digest = canonical_digest(inputs)
    comparisons = object_value(assessment["comparisons"])
    families = object_value(operation_map["families"])
    base_identity = object_value(json.loads(_base_manifest(root, base)))["build_id"]
    if not isinstance(base_identity, str):
        raise TypeError("Base runtime identity missing.")
    approved_failures: list[dict[str, object]] = []
    retained_applicability: dict[str, str] = {}
    for family in sorted(set() if deferred else selected):
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
        comparison = read_object(root / path)
        migration_binding: dict[str, object] | None = None
        applicability_sha: str | None
        migration = (
            migration_applies(base=base, runtime_id=runtime_id, family=family)
            and (root / "docs/performance/policy-v3/category-migration-20261015").exists()
        )
        from tools import performance_ci60_qualification as ci60
        from tools import performance_qualification_measurements as qualification

        successor_current = ci60.applies(root, base=base, family=family, path=path)
        qualified_current = successor_current or qualification.applies(base=base, path=path)
        comparison_runtime = runtime_id
        current_binding: dict[str, object] | None = None
        if successor_current:
            measured_inputs, current_binding, applicability_sha, comparison_runtime = (
                ci60.measurement(root, current=inputs, report=comparison, family=family)
            )
        elif qualified_current:
            measured_inputs, current_binding, applicability_sha = qualification.retained_inputs(
                root, current=inputs, report=comparison, family=family
            )
        elif migration:
            from tools.performance_category_migration import retained_inputs as migration_inputs

            measured_inputs, migration_binding, applicability_sha = migration_inputs(
                root, current=inputs, report=comparison, base=base, runtime_id=runtime_id
            )
        elif binding_enabled(family, specification):
            tool_schema = str(object_value(specification["input_binding"])["schema"])
            if tool_schema == HISTORICAL_TOOL_SCHEMA:
                measured_inputs, applicability_sha = retained_tool_comparison_inputs(
                    root, current=inputs, report=comparison, base=base
                )
            else:
                # Fresh v2/v4 records bind current inputs; no historical applicability bridge.
                measured_inputs, applicability_sha = inputs, None
        elif (
            family == "reconstruction"
            and comparison.get("schema") == "matched-reconstruction-abba-v1"
        ):
            from tools.performance_reconstruction_campaign import retained_inputs

            measured_inputs, applicability_sha = retained_inputs(
                root, current=inputs, report=comparison, base=base, runtime_id=runtime_id
            )
        else:
            measured_inputs, applicability_sha = retained_comparison_inputs(
                root, current=inputs, report=comparison, base=base, runtime_id=runtime_id
            )
        if applicability_sha is not None:
            retained_applicability[family] = applicability_sha
        tool_inputs = (
            current_binding
            if qualified_current
            else migration_binding
            if migration
            else (
                comparison_inputs(
                    root,
                    base=base,
                    family=family,
                    head_input_digest=canonical_digest(measured_inputs),
                    schema=str(object_value(specification["input_binding"])["schema"]),
                    measured_head=str(
                        object_value(
                            object_value(object_value(comparison["input_binding"])["sides"])["head"]
                        )["revision"]
                    ),
                )
                if binding_enabled(family, specification)
                else None
            )
        )
        fixture_digest = canonical_digest(
            {
                name: value
                for name, value in measured_inputs.items()
                if name.startswith(("tests/", "scripts/"))
                and not name.startswith("tests/code_quality/")
            }
        )
        if tool_inputs is not None:
            fixture_digest = str(tool_inputs["common_sha256"])
        approved_failures.extend(
            validate_comparison(
                comparison,
                base=base,
                runtime_id=comparison_runtime,
                input_digest=canonical_digest(measured_inputs),
                family=family,
                specification=specification,
                base_runtime_id=base_identity,
                expected_inputs={
                    "lock_sha256": measured_inputs["uv.lock"],
                    "workload_sha256": measured_inputs[driver],
                    "fixture_sha256": fixture_digest,
                },
                expected_binding=tool_inputs,
            )
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
        "approved_failures": approved_failures,
        "retained_measurement_applicability": retained_applicability,
    }


def _check_and_run(base_ref: str, pr_head: str | None, output: Path) -> dict[str, object]:
    from tools.performance_history_snapshot import witnesses

    records: list[dict[str, object]] = []
    with witnesses(records):
        binding = validate_current(ROOT, base_ref, pr_head=pr_head)
    report = run_smoke(ROOT, output, binding=binding)
    # An edit during measurements cannot inherit the completed receipt.
    try:
        with witnesses(records):
            after = validate_current(ROOT, base_ref, pr_head=pr_head)
    except (
        ValueError,
        TypeError,
        OSError,
        subprocess.CalledProcessError,
        subprocess.TimeoutExpired,
        KeyboardInterrupt,
    ):
        report["status"] = "failed"
        report["inputs_unchanged"] = False
        if records:
            report["history_phase_witnesses"] = records
        _write_receipt(output, report)
        raise
    if records:
        report["history_phase_witnesses"] = records
    if binding != after or (
        records
        and (
            len(records) != 2
            or records[0]["domain_identity"] != records[1]["domain_identity"]
            or any(record["status"] != "completed" for record in records)
        )
    ):
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
    except (
        ValueError,
        TypeError,
        OSError,
        subprocess.CalledProcessError,
        subprocess.TimeoutExpired,
    ) as error:
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
