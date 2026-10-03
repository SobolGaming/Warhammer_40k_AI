"""Diff-bound performance applicability; measurements never enter engine state."""

from __future__ import annotations

import ast
import fnmatch
import hashlib
import json
import math
import statistics
import subprocess
from pathlib import Path
from typing import cast

from tools.performance_order103_exception import RECOGNITION, validate_owner_recognition

POLICY = "rules-engine-performance-v3"
ASSESSMENT = "docs/performance/change-assessment.json"
MAP = "docs/performance/policy-v3/operation-map.json"
ORDER108_SCOPE = "docs/performance/policy-v3/order108-rule-semantics.json"
CATEGORIES = frozenset(
    {
        "governance",
        "rule_semantics",
        "algorithm_or_search",
        "cache_policy",
        "serialization_or_replay_work",
        "hot_query_or_data_structure",
        "measured_workload",
        "dependency_environment",
    }
)
DETAILED = CATEGORIES - {"governance", "rule_semantics", "dependency_environment"}


def digest(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest()


def canonical_digest(value: object) -> str:
    return digest(
        json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False).encode()
    )


def git(root: Path, *args: str) -> bytes:
    return subprocess.check_output(
        ["git", "-c", f"safe.directory={root.as_posix()}", *args], cwd=root
    )


def object_value(value: object) -> dict[str, object]:
    if not isinstance(value, dict) or not all(isinstance(key, str) for key in value):
        raise ValueError("Expected a JSON object with string keys.")
    return cast(dict[str, object], value)


def read_object(path: Path) -> dict[str, object]:
    return object_value(json.loads(path.read_text(encoding="utf-8")))


def _keys(value: dict[str, object], expected: set[str]) -> None:
    if value.keys() != expected:
        raise ValueError(f"Unexpected or missing performance fields: {value.keys() ^ expected}")


def _strings(value: object) -> list[str]:
    if not isinstance(value, list) or not all(isinstance(item, str) for item in value):
        raise ValueError("Expected a list of strings.")
    result = cast(list[str], value)
    if len(set(result)) != len(result):
        raise ValueError("Duplicate performance obligation.")
    return result


def owner_hashes(path: str, content: bytes | None) -> dict[str, str]:
    if content is None:
        return {}
    if not path.endswith(".py"):
        return {"@document": digest(content)}
    tree = ast.parse(content)
    owners: dict[str, str] = {}
    module = []
    for node in tree.body:
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            owners[node.name] = digest(ast.dump(node, include_attributes=False).encode())
        elif isinstance(node, ast.ClassDef):
            # Class metadata and methods remain separately reviewable owners.
            methods = [
                n for n in node.body if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef))
            ]
            for method in methods:
                owners[f"{node.name}.{method.name}"] = digest(ast.dump(method).encode())
            node.body = [n for n in node.body if n not in methods]
            owners[node.name] = digest(ast.dump(node).encode())
        else:
            module.append(node)
    owners["@module"] = digest(ast.dump(ast.Module(body=module, type_ignores=[])).encode())
    return owners


def changed_inputs(root: Path, base_ref: str) -> tuple[str, dict[str, object]]:
    """Use explicit reachable base and actual tracked/untracked working bytes.

    Exactly one self-describing artifact is omitted from its own input hash. Its
    contents, base, coverage, and policy/map identity are still validated below.
    """
    base = git(root, "rev-parse", "--verify", f"{base_ref}^{{commit}}").decode().strip()
    git(root, "merge-base", "--is-ancestor", base, "HEAD")
    old_names = set(git(root, "ls-tree", "-r", "--name-only", "-z", base).decode().split("\0")) - {
        ""
    }
    current_names = set(
        git(root, "ls-files", "--cached", "--others", "--exclude-standard", "-z")
        .decode()
        .split("\0")
    ) - {""}
    changed: dict[str, object] = {}
    # Git's path diff is only an optimization; untracked additions are included.
    names = set(git(root, "diff", "--name-only", "-z", base).decode().split("\0")) - {""}
    names |= current_names - old_names
    for name in sorted(names - {ASSESSMENT}):
        before = git(root, "show", f"{base}:{name}") if name in old_names else None
        path = root / name
        after = path.read_bytes() if path.is_file() else None
        # Git checkout line-ending conversion is not a semantic input change.
        if (
            before is not None
            and after is not None
            and before.replace(b"\r\n", b"\n") == after.replace(b"\r\n", b"\n")
        ):
            continue
        old_owners, new_owners = owner_hashes(name, before), owner_hashes(name, after)
        changed[name] = {
            "before_sha256": digest(before) if before is not None else None,
            "after_sha256": digest(after) if after is not None else None,
            "owners": {
                key: {"before": old_owners.get(key), "after": new_owners.get(key)}
                for key in sorted(old_owners.keys() | new_owners.keys())
                if old_owners.get(key) != new_owners.get(key)
            },
        }
    return base, changed


def runtime_inputs(root: Path) -> dict[str, str]:
    """Bind measurement code, all fixture dependencies and runtime/dependency data."""
    names = (
        git(root, "ls-files", "--cached", "--others", "--exclude-standard", "-z")
        .decode()
        .split("\0")
    )
    return {
        name: digest((root / name).read_bytes())
        for name in sorted(set(names))
        if name
        and (root / name).is_file()
        and (
            name.startswith(("src/", "tests/", "scripts/", "tools/", "contracts/schemas/"))
            or name in {"uv.lock", "pyproject.toml", MAP}
        )
    }


def _governance(path: str) -> bool:
    return path in {
        "AGENTS.md",
        "README.md",
        ".pre-commit-config.yaml",
        ".gitignore",
    } or path.startswith(
        (
            "docs/",
            ".github/",
            "tests/code_quality/",
            "tools/performance_",
            "tests/performance_evidence_helpers.py",
            "tests/performance_fixture_migration_helpers.py",
            "scripts/check_performance_policy.py",
            "scripts/performance_smoke.py",
        )
    )


def _order108_smoke_operations(
    *, base: str, path: str, category: str, change: object
) -> frozenset[str]:
    """Recognize only the owner's exact Order108 terrain-rule repair.

    File and owner hashes authenticate the whole changed row. This affects only
    detailed-family selection; mandatory mappings and live gates still apply.
    """
    if base != "eebdaa2ccadef14b6115aea7caea3cb1c89eb564" or category != "rule_semantics":
        return frozenset()
    scope = read_object(Path(__file__).resolve().parents[1] / ORDER108_SCOPE)
    if scope["base"] != base or object_value(scope["changes"]).get(path) != change:
        return frozenset()
    return frozenset({"geometry-search", "visibility-query"})


def validate_assessment(
    assessment: dict[str, object],
    *,
    base: str,
    changes: dict[str, object],
    runtime_id: str,
    operation_map: dict[str, object],
) -> set[str]:
    _keys(
        assessment,
        {
            "policy",
            "base",
            "runtime_build_id",
            "operation_map_sha256",
            "changes",
            "rows",
            "milestone",
            "comparisons",
            "full_game",
        },
    )
    if assessment["policy"] != POLICY or assessment["base"] != base:
        raise ValueError("Missing/stale policy assessment or exact base.")
    if assessment["runtime_build_id"] != runtime_id or assessment["changes"] != changes:
        raise ValueError("Assessment does not describe the actual current inputs/runtime.")
    if assessment["operation_map_sha256"] != canonical_digest(operation_map):
        raise ValueError("Assessment operation map drifted.")
    operations = object_value(operation_map["operations"])
    families = object_value(operation_map["families"])
    rows = object_value(assessment["rows"])
    if rows.keys() != changes.keys():
        raise ValueError("Every changed input needs exactly one reviewed assessment.")
    selected: set[str] = set()
    for path, raw in rows.items():
        row = object_value(raw)
        _keys(
            row,
            {
                "category",
                "operations",
                "selected_families",
                "rationale",
                "source_obligation",
                "unchanged_work",
            },
        )
        category = row["category"]
        if not isinstance(category, str) or category not in CATEGORIES:
            raise ValueError(f"Unknown category: {path}")
        if not isinstance(row["rationale"], str) or len(row["rationale"].strip()) < 30:
            raise ValueError(f"Missing bounded assessment rationale: {path}")
        owner_names = object_value(object_value(changes[path])["owners"])
        matching = {
            key: object_value(value)
            for key, value in operations.items()
            if any(
                fnmatch.fnmatchcase(path, pattern)
                for pattern in _strings(object_value(value)["paths"])
            )
            and any(
                fnmatch.fnmatchcase(owner, pattern)
                for owner in owner_names or {"@text": None}
                for pattern in _strings(object_value(value)["owners"])
            )
        }
        chosen_operations = _strings(row["operations"])
        chosen_families = set(_strings(row["selected_families"]))
        if category == "governance":
            if not _governance(path) or chosen_operations or chosen_families:
                raise ValueError(f"Runtime/workload change cannot be governance: {path}")
        elif not chosen_operations or not set(chosen_operations) <= matching.keys():
            raise ValueError(f"Unknown/missing owner operation mapping: {path}")
        if category != "governance":
            for owner in owner_names or {"@text": None}:
                if not any(
                    fnmatch.fnmatchcase(owner, pattern)
                    for key in chosen_operations
                    for pattern in _strings(matching[key]["owners"])
                ):
                    raise ValueError(f"Changed owner lacks an explicit operation: {path}:{owner}")
        mandatory = {key for key, value in matching.items() if value["mandatory"] is True}
        if not mandatory <= set(chosen_operations):
            raise ValueError(f"Sensitive owner operation omitted: {path}")
        candidates = {
            family for key in chosen_operations for family in _strings(matching[key]["families"])
        }
        if not chosen_families <= candidates or not chosen_families <= families.keys():
            raise ValueError(f"Unmapped detailed family: {path}")
        smoke_operations = _order108_smoke_operations(
            base=base, path=path, category=category, change=changes[path]
        )
        required = {
            family
            for key in chosen_operations
            if category in DETAILED
            or (matching[key]["sensitive"] is True and key not in smoke_operations)
            for family in _strings(matching[key]["families"])
        }
        if not required <= chosen_families:
            raise ValueError(f"Missing required detailed comparisons: {path}")
        if category == "rule_semantics":
            for field in ("source_obligation", "unchanged_work"):
                explanation = row[field]
                if not isinstance(explanation, str) or len(explanation.strip()) < 30:
                    raise ValueError(f"Rule assessment lacks {field}: {path}")
        # Runtime libraries are sensitive; development-only tools still run smoke.
        if category == "dependency_environment" and (
            not isinstance(row["unchanged_work"], str) or len(row["unchanged_work"].strip()) < 30
        ):
            raise ValueError("Dependency role/impact explanation required.")
        selected |= chosen_families
    if assessment["milestone"] not in {"ordinary", "rules_complete"}:
        raise ValueError("Unknown performance milestone.")
    if assessment["milestone"] == "rules_complete":
        selected |= families.keys()
        if not isinstance(assessment["full_game"], str):
            raise ValueError("Rules-complete profiling is missing.")
    elif assessment["full_game"] is not None:
        raise ValueError("Full-game certification must be explicitly assessed as a milestone.")
    if object_value(assessment["comparisons"]).keys() != selected:
        raise ValueError("Missing or extraneous current detailed comparison evidence.")
    referenced = set(object_value(assessment["comparisons"]).values())
    if assessment["full_game"] is not None:
        referenced.add(assessment["full_game"])
    for path, change in changes.items():
        if path.startswith("docs/performance/current/"):
            if object_value(change)["before_sha256"] is not None:
                raise ValueError("Existing measurement records are immutable; use a new path.")
            if path not in referenced:
                raise ValueError("New current evidence is not an assessed obligation.")
    return selected


def validate_comparison(
    report: dict[str, object],
    *,
    base: str,
    runtime_id: str,
    input_digest: str,
    family: str,
    specification: dict[str, object],
    base_runtime_id: str,
    expected_inputs: dict[str, str],
) -> list[dict[str, object]]:
    _keys(
        report,
        {
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
        }
        | ({"owner_exception"} if "owner_exception" in report else set()),
    )
    if (
        report["policy"],
        report["family"],
        report["base_revision"],
        report["head_runtime_build_id"],
        report["head_input_digest"],
    ) != (POLICY, family, base, runtime_id, input_digest):
        raise ValueError("Current comparison has stale or unrelated identities.")
    if report["budget_profile"] != specification["budget_profile"]:
        raise ValueError("Comparison does not use its declared family budget profile.")
    if report["budget_profile"] != "current-change-relative-v1":
        raise ValueError("Unknown current budget profile.")
    if report["workload_id"] != specification["workload_id"]:
        raise ValueError("Current comparison workload version drifted.")
    before, after = object_value(report["base"]), object_value(report["head"])
    for side in (before, after):
        _keys(
            side,
            {
                "runtime_build_id",
                "host",
                "lock_sha256",
                "workload_sha256",
                "fixture_sha256",
                "samples",
                "completed",
                "concurrency",
                "coverage",
            },
        )
        if (
            side["completed"] is not True
            or side["concurrency"] != 1
            or side["coverage"] is not False
        ):
            raise ValueError("Incomplete or contended performance comparison.")
        if not isinstance(side["runtime_build_id"], str) or not side["runtime_build_id"].startswith(
            "warhammer40k-core-v2:runtime-tree-sha256-v1:"
        ):
            raise ValueError("Missing measured runtime identity.")
        _validate_host(side["host"])
    if after["runtime_build_id"] != runtime_id:
        raise ValueError("Comparison head runtime does not match actual runtime.")
    if before["runtime_build_id"] != base_runtime_id:
        raise ValueError("Comparison baseline is not the actual PR base runtime.")
    for key in ("host", "lock_sha256", "workload_sha256", "fixture_sha256"):
        if not before[key] or before[key] != after[key]:
            raise ValueError(f"Unmatched comparison {key}.")
    if expected_inputs.keys() != {"lock_sha256", "workload_sha256", "fixture_sha256"}:
        raise ValueError("Expected actual measurement input inventory is incomplete.")
    for key, expected in expected_inputs.items():
        if after[key] != expected:
            raise ValueError(f"Measured {key} does not describe the actual selected workload.")
    cases = _strings(specification["cases"])
    base_samples, head_samples = object_value(before["samples"]), object_value(after["samples"])
    if set(cases) != base_samples.keys() or set(cases) != head_samples.keys():
        raise ValueError("Hard comparison cases were omitted or changed.")
    count = specification["samples_per_case"]
    recognized = validate_owner_recognition(report)
    approved_failures: list[dict[str, object]] = []
    for case in cases:
        measurements = []
        for side in (base_samples, head_samples):
            values = side[case]
            if not isinstance(values, list) or len(values) != count:
                raise ValueError("Required samples missing.")
            if not all(
                type(value) in (int, float) and math.isfinite(value) and value > 0
                for value in values
            ):
                raise ValueError("Invalid measured duration.")
            measurements.append(cast(list[float], values))
        old, new = measurements
        mean_limit = 1.25 * statistics.mean(old) + 0.05
        if max(new) > 1.5 * max(old) + 0.10:
            raise ValueError(f"Current relative budget exceeded: {family}/{case}")
        if statistics.mean(new) > mean_limit:
            if not recognized or case != RECOGNITION["case"]:
                raise ValueError(f"Current relative budget exceeded: {family}/{case}")
            approved_failures.append(
                {
                    **RECOGNITION,
                    "family": family,
                    "numerical_budget_passed": False,
                    "measured_seconds": statistics.mean(new),
                    "budget_seconds": mean_limit,
                }
            )
    if recognized and len(approved_failures) != 1:
        raise ValueError("Unused owner performance exception.")
    if not isinstance(report["historical_failures"], list):
        raise TypeError("Historical failure qualification must remain explicit.")
    return approved_failures


def _validate_host(value: object) -> None:
    host = object_value(value)
    _keys(host, {"cpu", "memory_bytes", "logical_cpus", "platform", "python", "role"})
    for key in ("cpu", "platform", "python"):
        description = host[key]
        if not isinstance(description, str) or not description.strip():
            raise ValueError(f"Measured host qualification is missing: {key}")
    for key in ("memory_bytes", "logical_cpus"):
        count = host[key]
        if type(count) is not int or count <= 0:
            raise ValueError(f"Measured host qualification is invalid: {key}")
    if host["role"] not in {"provisional", "reference"}:
        raise ValueError("Measured host role is missing.")


def validate_full_game(
    report: dict[str, object],
    *,
    base: str,
    runtime_id: str,
    input_digest: str,
    workload_sha256: str,
) -> None:
    if report.get("base_revision") != base or report.get("runtime_build_id") != runtime_id:
        raise ValueError("Full-game evidence is stale.")
    if report.get("normal_completion") is not True or report.get("supported_driver") is not True:
        raise ValueError("Supported complete-game profiling is unavailable/incomplete.")
    if (
        report.get("head_input_digest") != input_digest
        or report.get("workload_sha256") != workload_sha256
    ):
        raise ValueError("Full-game measured workload/input identity is stale.")
    _validate_host(report.get("host"))
    samples = report.get("initialization_through_completion_seconds")
    if (
        not isinstance(samples, list)
        or len(samples) < 3
        or not all(type(v) in (float, int) and math.isfinite(v) and v > 0 for v in samples)
    ):
        raise ValueError("Full-game samples are missing or invalid.")
    if statistics.mean(samples) >= 60 or max(samples) > 300:
        raise ValueError("Full-game performance objective not met.")
    policy = report.get("decision_policy")
    if not isinstance(policy, str) or not policy.strip() or report.get("policy") != POLICY:
        raise ValueError("Full-game decision policy/version is missing.")
    seeds = report.get("seeds")
    if (
        not isinstance(seeds, list)
        or len(seeds) != len(samples)
        or not all(type(v) is int for v in seeds)
    ):
        raise ValueError("Full-game sample seeds are missing or invalid.")
    for key in ("rosters", "terrain"):
        settings = report.get(key)
        if (
            not isinstance(settings, list)
            or len(settings) != len(samples)
            or not all(isinstance(v, dict) and v for v in settings)
        ):
            raise ValueError(f"Full-game per-sample scene qualification is missing: {key}")
    startup = report.get("startup_seconds")
    if (
        not isinstance(startup, list)
        or len(startup) != len(samples)
        or not all(type(v) in (float, int) and math.isfinite(v) and v >= 0 for v in startup)
    ):
        raise ValueError("Full-game startup timings are missing or invalid.")
