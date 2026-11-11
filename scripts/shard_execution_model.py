"""Conditional, coherent-cohort scheduling model; never a timing approval gate.

Recorded phases remain measurements. A module fixture group's setup estimate is
the largest complete setup sum observed for that group on one cohort worker.
Charging it once per new worker models reuse without assigning cold setup to the
historical first test forever. Different fixture multiplicity, host conditions,
work stealing and controller overhead still require real covered qualification.
Function-scoped setup can grow with relocated case counts, and overlapping module
fixture groups can charge shared dependencies twice. This estimate is not an
upper bound and must not be presented as one.
"""

from __future__ import annotations

import ast
import hashlib
import json
import math
from dataclasses import dataclass
from functools import cache
from pathlib import Path
from typing import cast

from scripts.hosted_timing_calibration import FILENAME, read_json

PROFILE_FILE = "allocation-cohorts.json"
MODEL = "coherent-worker-chunks-module-setup-v1"


@dataclass(frozen=True)
class Cohort:
    label: str
    cases: dict[str, float]
    groups: dict[str, str]
    setup: dict[str, float]


def _fixture_groups(root: Path, nodes: set[str]) -> dict[str, str]:
    """Recognize direct, literal, non-parametrized module fixtures only."""
    groups: dict[str, str] = {}
    for owner in sorted({node.split("::", 1)[0] for node in nodes}):
        functions = [
            node
            for node in ast.parse((root / owner).read_text(encoding="utf-8")).body
            if isinstance(node, ast.FunctionDef)
        ]
        fixtures = {
            function.name
            for function in functions
            for decorator in function.decorator_list
            if isinstance(decorator, ast.Call)
            and isinstance(decorator.func, ast.Attribute)
            and isinstance(decorator.func.value, ast.Name)
            and decorator.func.value.id == "pytest"
            and decorator.func.attr == "fixture"
            and any(
                keyword.arg == "scope"
                and isinstance(keyword.value, ast.Constant)
                and keyword.value.value == "module"
                for keyword in decorator.keywords
            )
            and not any(keyword.arg in {"params", "autouse"} for keyword in decorator.keywords)
        }
        dependencies = {
            function.name: tuple(
                sorted(arg.arg for arg in function.args.args if arg.arg in fixtures)
            )
            for function in functions
        }
        for node in sorted(nodes):
            if node.split("::", 1)[0] != owner:
                continue
            names = dependencies.get(node.split("::", 1)[1].split("[", 1)[0], ())
            if names:
                groups[node] = owner + "::fixtures::" + ",".join(names)
    return groups


def load_cohorts(directory: Path, *, root: Path, nodes: set[str]) -> tuple[Cohort, ...]:
    """Resolve explicit effective cohorts into already authenticated phase tuples.

    Each worker retains its original producing attempt and enclosing outcome.
    An inherited successful job may participate in an effective cohort, but is
    never appended or relabeled as a new worker observation.
    """
    path = directory / PROFILE_FILE
    if not path.exists():
        return ()
    value = read_json(path)
    if (
        not isinstance(value, dict)
        or value.keys() != {"schema", "cohorts"}
        or value["schema"] != MODEL
        or not isinstance(value["cohorts"], list)
        or not value["cohorts"]
    ):
        raise SystemExit("Invalid allocation cohort index.")
    calibration = cast(dict[str, object], read_json(directory / FILENAME))
    reports = cast(list[dict[str, object]], calibration["reports"])
    observations = cast(dict[str, list[list[int | float]]], calibration["observations"])
    by_hash = {report["sha256"]: index for index, report in enumerate(reports)}
    phases: dict[int, dict[str, tuple[float, float, float]]] = {}
    for node, rows in observations.items():
        for index, setup, call, teardown in rows:
            phases.setdefault(int(index), {})[node] = (float(setup), float(call), float(teardown))
    groups = _fixture_groups(root, nodes)
    cohorts: list[Cohort] = []
    labels: set[tuple[int, int]] = set()
    runtime = json.loads((root / "src/warhammer40k_core/_engine_build_manifest.json").read_bytes())[
        "fingerprint"
    ]
    for row in value["cohorts"]:
        if (
            not isinstance(row, dict)
            or row.keys() != {"run_id", "effective_attempt", "reports"}
            or any(
                type(row[key]) is not int or row[key] < 1 for key in ("run_id", "effective_attempt")
            )
            or not isinstance(row["reports"], list)
            or not row["reports"]
            or any(
                not isinstance(digest, str) or digest not in by_hash for digest in row["reports"]
            )
            or len(set(row["reports"])) != len(row["reports"])
        ):
            raise SystemExit("Invalid allocation cohort identity or reports.")
        identity = (row["run_id"], row["effective_attempt"])
        if identity in labels:
            raise SystemExit("Duplicate allocation cohort identity.")
        labels.add(identity)
        cases: dict[str, float] = {}
        setup_costs: dict[str, float] = {}
        for digest in row["reports"]:
            index = by_hash[digest]
            report = reports[index]
            source = cast(dict[str, object], report["source"])
            if (
                source["run_id"] != identity[0]
                or cast(int, source["attempt"]) > identity[1]
                or source["runtime_fingerprint"] != runtime
                or report["incomplete_or_unsuccessful_cases"] != 0
                or index not in phases
            ):
                raise SystemExit("Allocation cohort producer or current runtime differs.")
            worker_setup: dict[str, float] = {}
            for node, (setup, call, teardown) in phases[index].items():
                if node in cases or node not in nodes:
                    raise SystemExit("Allocation cohort case inventory is not exact.")
                if any(
                    not math.isfinite(seconds) or seconds < 0 for seconds in (setup, call, teardown)
                ):
                    raise SystemExit("Invalid allocation phase duration.")
                cases[node] = call + teardown + (0 if node in groups else setup)
                if node in groups:
                    group = groups[node]
                    worker_setup[group] = worker_setup.get(group, 0.0) + setup
            for group, seconds in worker_setup.items():
                setup_costs[group] = max(setup_costs.get(group, 0.0), seconds)
        if cases.keys() != nodes:
            raise SystemExit("Allocation cohort case inventory is not exact.")
        cohorts.append(
            Cohort(f"{identity[0]}-effective-attempt-{identity[1]}", cases, groups, setup_costs)
        )
    return tuple(cohorts)


def worker_chunks(
    selectors: tuple[str, ...], costs: dict[str, float]
) -> tuple[tuple[str, ...], ...]:
    from scripts.build_test_shards import (
        BEHAVIORAL_CI_WORKERS,
        SERIAL_BEHAVIORAL_CASE,
        duration_worksteal_order,
    )

    selected = set(selectors)
    nodes = tuple(
        sorted(
            node
            for node in costs
            if node != SERIAL_BEHAVIORAL_CASE
            and (node in selected or node.split("::", 1)[0] in selected)
        )
    )
    order = duration_worksteal_order(nodes, workers=BEHAVIORAL_CI_WORKERS, selector_seconds=costs)
    chunks: list[tuple[str, ...]] = []
    offset = 0
    for worker in range(BEHAVIORAL_CI_WORKERS):
        count = (len(nodes) - offset) // (BEHAVIORAL_CI_WORKERS - worker)
        chunks.append(tuple(nodes[index] for index in order[offset : offset + count]))
        offset += count
    return tuple(chunks)


def cohort_seconds(
    selectors: tuple[str, ...], costs: dict[str, float], cohorts: tuple[Cohort, ...]
) -> tuple[float, ...]:
    from scripts.build_test_shards import SERIAL_BEHAVIORAL_CASE

    chunks = worker_chunks(selectors, costs)
    values: list[float] = []
    for cohort in cohorts:
        workers = [
            math.fsum(cohort.cases[node] for node in chunk)
            + math.fsum(
                cohort.setup[group]
                for group in {cohort.groups[node] for node in chunk if node in cohort.groups}
            )
            for chunk in chunks
        ]
        serial = 0.0
        if SERIAL_BEHAVIORAL_CASE in selectors:
            serial = cohort.cases[SERIAL_BEHAVIORAL_CASE]
            if SERIAL_BEHAVIORAL_CASE in cohort.groups:
                serial += cohort.setup[cohort.groups[SERIAL_BEHAVIORAL_CASE]]
        values.append(max(workers) + serial)
    return tuple(values)


def allocate(
    weights: dict[str, float], costs: dict[str, float], cohorts: tuple[Cohort, ...], count: int
) -> tuple[tuple[str, ...], ...]:
    """Greedy real-chunk scoring, then strictly improving whole-selector moves."""
    assignments: list[tuple[str, ...]] = [() for _ in range(count)]

    @cache
    def score(selectors: tuple[str, ...]) -> float:
        return max(cohort_seconds(selectors, costs, cohorts))

    for selector in sorted(weights, key=lambda name: (-weights[name], name)):
        target = min(
            range(count),
            key=lambda index: (
                score((*assignments[index], selector)),
                len(assignments[index]),
                index,
            ),
        )
        assignments[target] = (*assignments[target], selector)
    if any(not group for group in assignments):
        raise SystemExit("Every behavioral shard must be nonempty.")
    while True:
        peaks = [score(group) for group in assignments]
        worst = max(range(count), key=lambda index: (peaks[index], -index))
        best = tuple(sorted(peaks, reverse=True))
        move: tuple[str, int] | None = None
        if len(assignments[worst]) == 1:
            break  # An indivisible selector owns the peak; do not hide it.
        for selector in sorted(assignments[worst]):
            removed = score(tuple(name for name in assignments[worst] if name != selector))
            for target in range(count):
                if target == worst:
                    continue
                candidate = peaks.copy()
                candidate[worst] = removed
                candidate[target] = score((*assignments[target], selector))
                objective = tuple(sorted(candidate, reverse=True))
                if objective < best:
                    best, move = objective, (selector, target)
        if move is None:
            break
        selector, target = move
        assignments[worst] = tuple(name for name in assignments[worst] if name != selector)
        assignments[target] = (*assignments[target], selector)
    cold = min(range(count), key=lambda index: (score(assignments[index]), index))
    assignments[0], assignments[cold] = assignments[cold], assignments[0]
    return tuple(tuple(sorted(group)) for group in assignments)


def metadata(
    directory: Path,
    shards: tuple[tuple[str, ...], ...],
    costs: dict[str, float],
    cohorts: tuple[Cohort, ...],
) -> dict[str, object]:
    return {
        "model": MODEL,
        "index": PROFILE_FILE,
        "index_sha256": hashlib.sha256((directory / PROFILE_FILE).read_bytes()).hexdigest(),
        "meaning": "Conditional initial chunks and module setup reuse; "
        "excludes controller overhead, work stealing and future variance; not timing qualification",
        "cohort_worker_path_seconds": {
            cohort.label: {
                str(index + 1): round(cohort_seconds(group, costs, (cohort,))[0], 3)
                for index, group in enumerate(shards)
            }
            for cohort in cohorts
        },
    }
