# Native headless geometry baseline

The baseline starts at the first Command decision of the Cavalcade v995 mirror
and stops at player A’s first `select_shooting_unit` request. It retains both
2,000-point armies, all 18 units and 78 models, and all 30 terrain features of
Event Companion `purge-the-foe-vs-purge-the-foe-layout-1`. The existing setup runner uses
policy seed `19` and private RNG seed `a1` repeated 32 times. The measured route
uses the existing `ranged-sidestep` witness and the native phase-start choice
from `revised-v5`. It does not declare or resolve a shot.

Generate one checkpoint and run each arm in a fresh process from the repo root.
The preparation and restore clocks are separate from the gameplay clock.

```bash
uv sync --locked
export PYTHONHASHSEED=0 OMP_NUM_THREADS=1 OPENBLAS_NUM_THREADS=1
work=$(mktemp -d)
uv run --no-sync python -B -m scripts.profile_headless_geometry "$work/command.json" --prepare
uv run --no-sync python -B -m scripts.profile_headless_geometry "$work/command.json"
uv run --no-sync python -B -m scripts.profile_headless_geometry "$work/command.json" --profile
```

The plain arm measures the whole slice with `perf_counter`, including adapter
projection, decisions and phase advancement. The profiled arm uses `cProfile`'s
wall-clock timer on the same decisions. Inclusive time includes callees. Self
time measures the named function body alone. Nested rows overlap. The JSON
output includes the final persistence content hash, the decision count, the
endpoint, and deltas of the existing physical visibility solver caches. Compare
final content hashes across arms to check that profiling preserves the result.

## Measured slice

One plain/profiled pair on 2026-11-19 used engine revision
`0e23e96ed480086fac86cb194cfcca50ffc86007`, CPython 3.14.5, Ubuntu under WSL2
kernel `6.18.58.1-microsoft-standard-WSL2`, and an AMD Ryzen Threadripper 3970X
with 64 logical CPUs and 62.7 GiB visible memory. Each arm ran serially without
coverage, with the ordinary caches enabled. Cold mirror setup took 95.31 s,
before writing the checkpoint. Reading and validating the same checkpoint took
49.99 s in the plain arm and 50.36 s in the profiled arm. The 27-decision slice
took 29.29 s plain and 74.85 s profiled. Both runs ended at the same request
with persistence content hash
`8621306654bcba3f02f20884a479b20ccbc0e4ee8d7c13e94527d585048a634e`.

| Profiled boundary | Calls | Inclusive wall ms | Self wall ms |
| --- | ---: | ---: | ---: |
| Pathing, `PathValidationContext.validate` | 1 | 42.069 | 0.358 |
| Terrain pathing, `TerrainPathLegalityContext.validate` | 1 | 96.575 | 0.252 |
| Engagement range, `scenario_physically_engaged_enemy_rules_unit_ids` | 37 | 803.065 | 0.213 |
| Model engagement predicate, `Model.is_within_engagement_range` | 8,034 | 879.347 | 9.875 |
| Shooting range, `target_in_range_model_ids` / `Model.range_to` | 0 / 0 | 0 | 0 |
| LOS, `TerrainVisibilityContext.has_line_of_sight` / `.resolve_line_of_sight` | 0 / 0 | 0 | 0 |
| Objective control, `resolve_objective_control` | 17 | 6,526.926 | 0.321 |

The model engagement row partly runs inside the unit engagement row and also
includes callers outside it. The replayable prefix exercises one movement
witness and reaches shooting selection without exercising either measured
shooting-range or LOS entry point. Both physical visibility caches reported zero
hits and zero misses in the slice. These wall times describe the profiled slice
and include profiling overhead. One pair provides no run-to-run variance estimate.

## Supplemental LOS control

On the same host, a separate process prepared the existing Order 78
`fully-visible` fixture in 3.42 s. Ten serial calls to `shared_los` on that
fixed scene all returned true. The first call took 2.826 ms, and the other
nine took 0.441–0.507 ms each. The any-part physical solver cache reported one
miss and nine hits. The call times include query preparation and cache lookup.

```bash
uv run --no-sync python -B - <<'PY'
from time import perf_counter

from tests.order78_helpers import scene, shared_los
from warhammer40k_core.geometry.physical_visibility import resolve_physical_any_visibility

start = perf_counter()
lifecycle, units = scene(wall_y=40.0)
print("setup seconds", perf_counter() - start)
print("initial cache", resolve_physical_any_visibility.cache_info())
for _ in range(10):
    start = perf_counter()
    visible = shared_los(lifecycle, units)
    print("query seconds", perf_counter() - start)
    assert visible
print("final cache", resolve_physical_any_visibility.cache_info())
PY
```

The earlier [movement](current/oval-codec-movement.json) and
[visibility](current/oval-codec-visibility.json) reports remain bound to their
own component workloads and comparisons. The supplemental control above times
only the shared LOS query, whereas the earlier visibility comparison times
paired candidate and LOS calls.

## Where to investigate next

Start with engagement-range work among the three requested areas. Measure how
often checks revisit unchanged model pairs and placements before testing
request-local reuse of prepared geometry or conservative candidate filtering.
The profile also found a larger terrain-linked objective-control cost. Measure
that path separately before attributing whole-slice time to movement or range.

This route validates each moving model and terrain path once, so it offers
little evidence for caching complete path results across decisions. The LOS
control shows the existing solver cache can already reuse identical geometry.
Measure repeated work before the solver on a real in-range shooting route before
testing any additional LOS reuse. Cache hit rates on a moving board remain open.
