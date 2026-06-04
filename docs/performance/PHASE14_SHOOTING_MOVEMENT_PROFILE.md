# Phase 14 Shooting and Movement Performance Profile

Profile captured on 2026-06-04 from the local workspace on macOS, Python 3.14.5,
with `pytest-benchmark` 5.2.3.

This run refreshes the Phase 7 geometry baseline after the current shooting implementation
and recent movement work. The Phase 7 numbers were captured on Windows, so direct ratios are
directional only.

## Commands

```bash
uv run pytest tests/benchmarks -m benchmark --benchmark-only --no-cov
uv run python scripts/profile_movement_pathing.py --profile-size smoke --seed 10001 --iterations 3
uv run python scripts/profile_movement_pathing.py --profile-size nightly --seed 10001 --iterations 1
```

Supplemental shooting declaration timing was run with the Phase 13B shooting lifecycle fixture,
measuring selection through declaration request construction for one shooting unit and one target.

## Implemented Optimizations

- Added analytic `CircularBase` distance and overlap fast paths.
- Cached Shapely module handles and bounded rectangular box footprints.
- Added x-axis candidate indexes for model, terrain, and engagement `CollisionSet` blockers.
- Added vertical/max-radius early rejection for model overlap helpers in pathing, reserves, and
  transports.
- Reworked movement coherency validation to process unordered pairs once, with early exits.
- Memoized shooting target candidates during legal shooting type checks and declaration request
  construction with cache keys that include weapon source identity and canonical profile payload.

## Geometry Microbenchmarks

| Benchmark | Current Mean | Phase 7 Mean | Directional Change |
| --- | ---: | ---: | ---: |
| Shapely terrain footprint | 0.4294 us | 21.5179 us | 50.11x faster |
| CollisionSet model query | 5.2231 us | 5,404.6100 us | 1,034.75x faster |
| CollisionSet engagement query | 7.9213 us | 14,091.6606 us | 1,779.00x faster |
| Shapely rectangular base footprint | 28.0780 us | 73.8577 us | 2.63x faster |
| Shapely circular base footprint | 32.4933 us | 73.1192 us | 2.25x faster |
| CollisionSet terrain query | 33.8531 us | 3,985.0793 us | 117.72x faster |
| PathQuery, 1 model, no blockers | 70.1155 us | 57.0033 us | 0.81x |
| Shapely oval base footprint | 72.3869 us | 166.6714 us | 2.30x faster |
| PathQuery, 5-model group, no blockers | 323.2467 us | 6,906.6907 us | 21.37x faster |
| PathQuery, attached group validation | 326.4511 us | 6,927.1375 us | 21.22x faster |
| VisibilityQuery, early clear ray | 2,420.4404 us | 5,894.8600 us | 2.44x faster |
| VisibilityQuery, all blocked | 2,441.9828 us | 5,971.4853 us | 2.45x faster |
| PathQuery, 5-model group, terrain blockers | 347.6081 us | 104,512.2300 us | 300.66x faster |
| PathQuery, 5-model group, model blockers | 322.1090 us | 138,981.5000 us | 431.47x faster |

## Movement Hotspot Profile

Smoke profile:

| Scenario | Iterations | Elapsed | Per Run | Dominant Counter | Count |
| --- | ---: | ---: | ---: | --- | ---: |
| crowded infantry | 3 | 3.02 ms | 1.01 ms | path_sampled_pose_count | 270 |
| vehicle blockers | 3 | 1.77 ms | 0.59 ms | path_sampled_pose_count | 135 |
| ruins terrain | 3 | 167.85 ms | 55.95 ms | path_sampled_pose_count | 81 |
| reserve-like placement | 3 | 0.38 ms | 0.13 ms | path_sampled_pose_count | 36 |
| fly paths | 3 | 7.95 ms | 2.65 ms | terrain_sampled_pose_count | 51 |

Nightly profile:

| Scenario | Iterations | Elapsed | Per Run | Dominant Counter | Count |
| --- | ---: | ---: | ---: | --- | ---: |
| crowded infantry | 4 | 18.28 ms | 4.57 ms | path_sampled_pose_count | 1,440 |
| vehicle blockers | 4 | 8.25 ms | 2.06 ms | path_sampled_pose_count | 720 |
| ruins terrain | 4 | 121.05 ms | 30.26 ms | path_sampled_pose_count | 432 |
| reserve-like placement | 4 | 0.51 ms | 0.13 ms | path_sampled_pose_count | 48 |
| fly paths | 4 | 36.47 ms | 9.12 ms | terrain_sampled_pose_count | 68 |

Indexed blocker workloads now report zero model/terrain/engagement broadphase checks when all
blockers are x-disjoint from sampled poses. Their dominant counters moved to sampled pose counts.

## Shooting Supplemental Timing

| Workload | Setup | Select to Declaration Request | Available Weapons | Target Candidates |
| --- | ---: | ---: | ---: | ---: |
| 5 attackers / 1 target | 7.85 ms | 49.94 ms | 5 | 5 |
| 10 attackers / 1 target | 9.00 ms | 102.14 ms | 10 | 10 |

The original pre-optimization 10-model declaration probe took about 578 ms. The optimized path
keeps the same adapter-visible weapon/candidate counts while avoiding repeated target candidate
work for identical weapon sources with identical profile payloads and repeated legal-type candidate
construction.

## Remaining Signal

The ruins terrain movement scenario is now the main remaining hotspot. Its cost comes from terrain
path legality and endpoint support checks rather than model blocker collision. A later terrain slice
should consider generation-keyed terrain feature/support-surface caches, but that should be done
with dedicated terrain legality tests because it touches movement rule evidence.
