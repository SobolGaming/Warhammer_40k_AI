"""Mirror-first allocation over complete cohorts and an explicitly known scope."""

from __future__ import annotations

import math
from functools import cache

from scripts.scoped_shard_evidence import ScopedEvidence, node_digest
from scripts.shard_execution_model import Cohort, cohort_seconds

HISTORICAL_PLANNING_CEILING = 1076.0


def role_scores(
    selectors: tuple[str, ...], costs: dict[str, float], cohorts: tuple[Cohort, ...]
) -> tuple[float, ...]:
    from scripts.build_test_shards import SERIAL_BEHAVIORAL_CASE

    mirror = SERIAL_BEHAVIORAL_CASE in selectors
    return tuple(
        phase + (cohort.mirror_residual if mirror else cohort.parallel_residual)
        for phase, cohort in zip(cohort_seconds(selectors, costs, cohorts), cohorts, strict=True)
    )


def allocate_scoped(
    weights: dict[str, float],
    costs: dict[str, float],
    cohorts: tuple[Cohort, ...],
    count: int,
    scope: ScopedEvidence,
) -> tuple[tuple[str, ...], ...]:
    from scripts.build_test_shards import SERIAL_BEHAVIORAL_CASE

    frozen = scope.frozen_shard - 1
    if (
        not cohorts
        or not 0 <= frozen < count
        or frozen == 0
        or not set(scope.frozen_selectors) <= weights.keys()
        or SERIAL_BEHAVIORAL_CASE not in weights
        or SERIAL_BEHAVIORAL_CASE in scope.frozen_selectors
    ):
        raise SystemExit("Invalid scoped allocation fixed selection or mirror.")
    assignments: list[tuple[str, ...]] = [() for _ in range(count)]
    assignments[frozen] = scope.frozen_selectors
    active = tuple(index for index in range(count) if index != frozen)
    admissible = dict.fromkeys(weights, True)
    matched: set[str] = set()
    for node in costs:
        for selector in (node, node.split("::", 1)[0]):
            if selector in admissible:
                matched.add(selector)
                if node not in scope.known_nodes:
                    admissible[selector] = False
    if matched != weights.keys():
        raise SystemExit("Scoped allocation selector has no measured cases.")

    @cache
    def scores(selectors: tuple[str, ...]) -> tuple[float, ...]:
        if any(not admissible[selector] for selector in selectors):
            raise SystemExit("Scoped allocation cannot estimate unknown cases.")
        return role_scores(selectors, costs, (*cohorts, scope.cohort))

    # Reserve the sequential one-worker lane before aggregate module weights fill
    # the parallel slots. The caller retains the existing serial x4 execution weight.
    assignments[active[0]] = (SERIAL_BEHAVIORAL_CASE,)
    remaining = weights.keys() - set(scope.frozen_selectors) - {SERIAL_BEHAVIORAL_CASE}
    for selector in sorted(remaining, key=lambda name: (-weights[name], name)):
        target = min(
            active,
            key=lambda index: (
                math.ceil(max(scores(tuple(sorted((*assignments[index], selector)))))),
                len(assignments[index]),
                index,
            ),
        )
        assignments[target] = tuple(sorted((*assignments[target], selector)))
    if any(not group for group in assignments):
        raise SystemExit("Every scoped behavioral shard must be nonempty.")
    while True:
        values = {index: scores(assignments[index]) for index in active}
        peaks = {index: math.ceil(max(values[index])) for index in active}
        baseline = tuple(sorted(peaks.values(), reverse=True))
        found: tuple[int, int, str] | None = None
        for source in sorted(active, key=lambda index: (-peaks[index], index)):
            if len(assignments[source]) <= 1:
                continue
            best = baseline
            move: tuple[int, str] | None = None
            for selector in assignments[source]:
                removed = scores(tuple(name for name in assignments[source] if name != selector))
                if max(removed[:-1]) > max(HISTORICAL_PLANNING_CEILING, max(values[source][:-1])):
                    continue
                for target in active:
                    if target == source:
                        continue
                    added = scores(tuple(sorted((*assignments[target], selector))))
                    if max(added[:-1]) > max(HISTORICAL_PLANNING_CEILING, max(values[target][:-1])):
                        continue
                    objective = tuple(
                        sorted(
                            (
                                math.ceil(max(removed))
                                if index == source
                                else math.ceil(max(added))
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
            break
        source, target, selector = found
        assignments[source] = tuple(name for name in assignments[source] if name != selector)
        assignments[target] = tuple(sorted((*assignments[target], selector)))
    if any(max(scores(assignments[index])[:-1]) > HISTORICAL_PLANNING_CEILING for index in active):
        raise SystemExit("Scoped allocation exceeds its historical planning ceiling.")
    cold = min(active, key=lambda index: (math.ceil(max(scores(assignments[index]))), index))
    assignments[0], assignments[cold] = assignments[cold], assignments[0]
    if assignments[frozen] != scope.frozen_selectors:
        raise SystemExit("Scoped allocation changed its frozen selection.")
    return tuple(assignments)


def scoped_metadata(
    shards: tuple[tuple[str, ...], ...],
    costs: dict[str, float],
    cohorts: tuple[Cohort, ...],
    scope: ScopedEvidence,
) -> dict[str, object]:
    known: dict[str, object] = {}
    for index, group in enumerate(shards, 1):
        if index == scope.frozen_shard:
            if group != scope.frozen_selectors:
                raise SystemExit("Scoped allocation metadata changed its frozen selection.")
            known[str(index)] = None
        else:
            phase = cohort_seconds(group, costs, (scope.cohort,))[0]
            known[str(index)] = {
                "phase_seconds": phase,
                "phase_plus_observed_role_seconds": role_scores(group, costs, (scope.cohort,))[0],
                "planning_score_seconds": math.ceil(
                    max(role_scores(group, costs, (*cohorts, scope.cohort)))
                ),
            }
    return {
        "reference": scope.reference,
        "role": "Partial known-scope stress only; null means unknown, never zero or imputed",
        "cohort": scope.cohort.label,
        "known_cases": len(scope.known_nodes),
        "known_nodes_sha256": node_digest(scope.known_nodes),
        "frozen_shard": scope.frozen_shard,
        "frozen_cases": len(scope.frozen_nodes),
        "frozen_nodes_sha256": node_digest(scope.frozen_nodes),
        "historical_planning_ceiling_seconds": HISTORICAL_PLANNING_CEILING,
        "parallel_role_residual_seconds": scope.cohort.parallel_residual,
        "mirror_role_residual_seconds": scope.cohort.mirror_residual,
        "shards": known,
        "meaning": "Mirror first, then descending execution weights and strictly improving "
        "whole-selector moves; all eight complete cohorts still cover the frozen shard. "
        "The partial observations never alter ordinary dispatch costs or approval limits.",
    }
