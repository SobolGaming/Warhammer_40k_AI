"""Pinned whole files and explicitly derived stress; actual timing gates are separate."""

from __future__ import annotations

import math
from functools import cache

from scripts.scoped_shard_evidence import ScopedEvidence, node_digest
from scripts.scoped_shard_extension import ExtendedScope
from scripts.shard_execution_model import Cohort, worker_chunks

HISTORICAL_CEILING = 1076.0
STRESS_CEILING = 1054.0
LATEST_CEILING = 1050.0


def planning_profiles(cohorts: tuple[Cohort, ...], scope: ExtendedScope) -> tuple[Cohort, ...]:
    if len(cohorts) != 9 or cohorts[-1].label != "43081418293-effective-attempt-1":
        raise SystemExit("Extended allocation requires its nine declared complete cohorts.")
    return (*cohorts[:-1], scope.stress, cohorts[-1])


def _peak(values: tuple[float, ...]) -> int:
    return math.ceil(max(*values[:-2], values[-2] + 22, values[-1] + 26))


def _retained(values: tuple[float, ...]) -> float:
    return max(*values[:-2], values[-2] + 22)


def allocate_extended(
    weights: dict[str, float],
    costs: dict[str, float],
    cohorts: tuple[Cohort, ...],
    count: int,
    scope: ExtendedScope,
) -> tuple[tuple[str, ...], ...]:
    from scripts.build_test_shards import SERIAL_BEHAVIORAL_CASE
    from scripts.scoped_shard_allocation import role_scores

    profiles = planning_profiles(cohorts, scope)
    pinned, fixed = scope.pinned_shard - 1, scope.fixed_shard - 1
    if (
        count != 12
        or (pinned, fixed) != (3, 4)
        or not {scope.pinned_selector, scope.fixed_selector, SERIAL_BEHAVIORAL_CASE}
        <= weights.keys()
        or scope.raw.cases.keys() | {scope.unknown_node} != costs.keys()
        or scope.unknown_node in scope.raw.cases
        or scope.stress.cases.keys() != costs.keys()
    ):
        raise SystemExit("Extended allocation fixed selection or known scope differs.")

    @cache
    def scores(selectors: tuple[str, ...]) -> tuple[float, ...]:
        return role_scores(selectors, costs, profiles)

    for selector in (scope.pinned_selector, scope.fixed_selector):
        if _peak(scores((selector,))) > HISTORICAL_CEILING:
            raise SystemExit("A pinned whole file exceeds the declared planning bounds.")
    assignments: list[tuple[str, ...]] = [() for _ in range(count)]
    assignments[pinned] = (scope.pinned_selector,)
    assignments[fixed] = (scope.fixed_selector,)
    active = tuple(index for index in range(count) if index != fixed)
    assignments[0] = (SERIAL_BEHAVIORAL_CASE,)
    remaining = weights.keys() - {
        scope.pinned_selector,
        scope.fixed_selector,
        SERIAL_BEHAVIORAL_CASE,
    }
    for selector in sorted(remaining, key=lambda name: (-weights[name], name)):
        target = min(
            active,
            key=lambda index: (
                _peak(scores(tuple(sorted((*assignments[index], selector))))),
                len(assignments[index]),
                index,
            ),
        )
        assignments[target] = tuple(sorted((*assignments[target], selector)))
    while True:
        values = {index: scores(assignments[index]) for index in active}
        peaks = {index: _peak(value) for index, value in values.items()}
        baseline = tuple(sorted(peaks.values(), reverse=True))
        if baseline[0] <= HISTORICAL_CEILING:
            break
        found: tuple[int, int, str] | None = None
        for source in sorted(active, key=lambda index: (-peaks[index], index)):
            if len(assignments[source]) <= 1:
                continue
            best = baseline
            move: tuple[int, str] | None = None
            for selector in assignments[source]:
                if selector == scope.pinned_selector:
                    continue
                removed = scores(tuple(name for name in assignments[source] if name != selector))
                if removed[-1] > max(LATEST_CEILING, values[source][-1]) or _retained(
                    removed
                ) > max(HISTORICAL_CEILING, _retained(values[source])):
                    continue
                for target in active:
                    if target == source:
                        continue
                    added = scores(tuple(sorted((*assignments[target], selector))))
                    if added[-1] > max(LATEST_CEILING, values[target][-1]) or _retained(
                        added
                    ) > max(HISTORICAL_CEILING, _retained(values[target])):
                        continue
                    objective = tuple(
                        sorted(
                            (
                                _peak(removed)
                                if index == source
                                else _peak(added)
                                if index == target
                                else peaks[index]
                                for index in active
                            ),
                            reverse=True,
                        )
                    )
                    if objective < best:
                        best, move = objective, (target, selector)
            if move is not None:
                found = (source, *move)
                break
        if found is None:
            raise SystemExit("Extended allocation cannot satisfy its declared planning bounds.")
        source, target, selector = found
        assignments[source] = tuple(name for name in assignments[source] if name != selector)
        assignments[target] = tuple(sorted((*assignments[target], selector)))
    mirror = next(
        index for index, group in enumerate(assignments) if SERIAL_BEHAVIORAL_CASE in group
    )
    eligible = tuple(index for index in active if index not in (pinned, fixed, mirror))
    cold = min(eligible, key=lambda index: (_peak(scores(assignments[index])), index))
    assignments[0], assignments[cold] = assignments[cold], assignments[0]
    if (
        scope.pinned_selector not in assignments[pinned]
        or assignments[fixed] != (scope.fixed_selector,)
        or SERIAL_BEHAVIORAL_CASE in assignments[0]
        or any(not group for group in assignments)
    ):
        raise SystemExit("Extended allocation changed a pinned file or controller role.")
    return tuple(assignments)


def partial_projection(
    selectors: tuple[str, ...], costs: dict[str, float], cohort: Cohort
) -> dict[str, object]:
    from scripts.build_test_shards import SERIAL_BEHAVIORAL_CASE

    selected = set(selectors)
    nodes = {
        node
        for node in costs
        if node in selected
        or (node.split("::", 1)[0] in selected and node != SERIAL_BEHAVIORAL_CASE)
    }
    workers: list[float] = []
    for chunk in worker_chunks(selectors, costs):
        known = [node for node in chunk if node in cohort.cases]
        workers.append(
            math.fsum(cohort.cases[node] for node in known)
            + math.fsum(
                cohort.setup[group]
                for group in {cohort.groups[node] for node in known if node in cohort.groups}
            )
        )
    mirror = SERIAL_BEHAVIORAL_CASE in selectors
    serial = cohort.cases[SERIAL_BEHAVIORAL_CASE] if mirror else 0.0
    phase = max(workers, default=0.0) + serial
    missing = nodes - cohort.cases.keys()
    residual = cohort.mirror_residual if mirror else cohort.parallel_residual
    return {
        "full_raw_role_score": None if missing else phase + residual,
        "known_only_conditional_phase": phase,
        "known_only_worker_phases": workers,
        "known_serial_phase": serial,
        "missing_nodes": sorted(missing),
        "known_cases": len(nodes & cohort.cases.keys()),
        "role_residual_from_original_complete11": residual,
        "known_only_phase_plus_role_NOT_full_if_missing": phase + residual,
    }


def extended_metadata(
    shards: tuple[tuple[str, ...], ...],
    costs: dict[str, float],
    cohorts: tuple[Cohort, ...],
    base: ScopedEvidence,
) -> dict[str, object]:
    from scripts.scoped_shard_allocation import role_scores

    scope = base.extension
    if scope is None:
        raise SystemExit("Extended allocation metadata requires explicit extension evidence.")
    profiles = planning_profiles(cohorts, scope)
    rows: dict[str, object] = {}
    for index, group in enumerate(shards, 1):
        values = role_scores(group, costs, profiles)
        rows[str(index)] = {
            "historical": list(values[:-2]),
            "derived_stress": values[-2],
            "latest_complete": values[-1],
            "planning_score": _peak(values),
            "original_6014_partial_raw": partial_projection(group, costs, base.cohort),
            "expanded_6281_partial_raw": partial_projection(group, costs, scope.raw),
        }
    return {
        "schema": "extended-partial-with-separate-derived-stress-v1",
        "original_reference": base.reference,
        "extension_reference": scope.reference,
        "known_cases": len(scope.raw.cases),
        "known_nodes_sha256": node_digest(set(scope.raw.cases)),
        "unknown_nodes": [scope.unknown_node],
        "unknown_actual_seconds": None,
        "pinned_shard": scope.pinned_shard,
        "pinned_selector": scope.pinned_selector,
        "fixed_shard": scope.fixed_shard,
        "fixed_selector": scope.fixed_selector,
        "planning_bounds": {
            "historical": HISTORICAL_CEILING,
            "derived_stress": STRESS_CEILING,
            "latest": LATEST_CEILING,
        },
        "planning_offsets": [0] * (len(cohorts) - 1) + [22, 26],
        "derived_reservation_seconds": scope.reservation_seconds,
        "parallel_role_residual_seconds": scope.raw.parallel_residual,
        "mirror_role_residual_seconds": scope.raw.mirror_residual,
        "shards": rows,
        "meaning": "Raw partial scores stay null where observations are missing. The separate "
        "derived stress reserves one unknown case using other complete observations and dispatch "
        "maxima; it is not a measured complete cohort or timing qualification. Offsets align "
        "planning budgets only. Planning offsets do not set actual coverage or timing thresholds, "
        "worker counts or test outcomes; required CI policy enforces them independently.",
    }
