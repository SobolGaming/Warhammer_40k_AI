# Phase 7 Geometry Benchmark Baseline

Baseline captured on 2026-05-26 from `codex/phase-7-geometry-benchmarks` on Windows,
Python 3.14.5, with `pytest-benchmark` 5.2.3.

Benchmarks are opt-in and excluded from normal CI by the `benchmark` marker.

Manual command:

```bash
uv run pytest tests/benchmarks -m benchmark --benchmark-only --no-cov
```

`--no-cov` keeps the repo-wide coverage gate from affecting the isolated benchmark run.

## Timings

| Benchmark | Mean |
| --- | ---: |
| Shapely terrain footprint | 21.5179 us |
| PathQuery, 1 model, no blockers | 57.0033 us |
| Shapely circular base footprint | 73.1192 us |
| Shapely rectangular base footprint | 73.8577 us |
| Shapely oval base footprint | 166.6714 us |
| CollisionSet terrain query | 3,985.0793 us |
| CollisionSet model query | 5,404.6100 us |
| VisibilityQuery, early clear ray | 5,894.8600 us |
| VisibilityQuery, all blocked | 5,971.4853 us |
| PathQuery, 5-model group, no blockers | 6,906.6907 us |
| PathQuery, attached group validation | 6,927.1375 us |
| CollisionSet engagement query | 14,091.6606 us |
| PathQuery, 5-model group, terrain blockers | 104,512.2300 us |
| PathQuery, 5-model group, model blockers | 138,981.5000 us |

## Counters

| Workload | Counter | Value |
| --- | --- | ---: |
| VisibilityQuery, early clear ray | checked rays | 2 |
| VisibilityQuery, early clear ray | terrain candidates | 40 |
| VisibilityQuery, early clear ray | model candidates | 40 |
| VisibilityQuery, all blocked | checked rays | 3 |
| VisibilityQuery, all blocked | terrain candidates | 120 |
| VisibilityQuery, all blocked | model candidates | 40 |
| PathQuery, 1 model, no blockers | sampled poses | 5 |
| PathQuery, 5-model group, no blockers | sampled poses | 25 |
| PathQuery, attached group validation | sampled poses | 25 |
| PathQuery, 5-model group, terrain blockers | terrain collision checks | 1,000 |
| PathQuery, 5-model group, model blockers | model collision checks | 1,000 |

## Initial Signal

The blocker-heavy pathing cases scale with sampled poses multiplied by blocker count.
That is acceptable for Phase 7 correctness, but it confirms the likely Phase 8/9 optimization path:

- cache static terrain footprints by terrain ID and generation;
- cache dynamic model footprints by model ID, pose, base, and generation;
- add a real broad-phase index before exact Shapely checks;
- keep static terrain and dynamic model indexes separate.
