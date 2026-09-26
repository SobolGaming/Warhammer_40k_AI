# Order 79 / P14A boundary assessment

Order 87 refreshed the active head report for runtime `904893c1`; prior tables and
revision notes below describe historical runs. Current samples and refresh details
are recorded in [Order 87 evidence](../order87/README.md). Baselines and budgets
remain unchanged.

`base.json` measures merged main `68c6bccb7d1f44e3b03409a86565a3d285c8449d`;
`head.json` binds the repaired runtime identity. Both use the same measurement
script, canonical Aircraft fixture, dependency lock and provisional host:
Apple M5 Pro, 18 logical CPUs, 64 GiB RAM, macOS 26.7, Python 3.14.5.

Each initialized, unengaged Fight boundary advances through `LocalGameSession`
to the next decision. One friendly Aircraft with source-dash Movement and OC
starts at the first mission objective; the canonical opposing infantry and original mission terrain remain.
The two cases vary only the turn owner. The fixture's deterministic seed, roster,
model placements and setup are pinned through the helper hashes. Five separate
initialized sessions run serially per case without coverage, profiler or competing
test/build workers. Initialization and restore before each advance are excluded.
The first measured case can populate process caches; later samples retain them.

| Turn owner | Base mean / maximum (s) | Head mean / maximum (s) |
| --- | ---: | ---: |
| Opponent | 0.05238 / 0.05725 | 0.05092 / 0.05525 |
| Aircraft owner | 0.03846 / 0.03891 | 0.03847 / 0.03900 |

Opponent-turn median base/head times are 0.05095/0.04990 seconds; own-turn
medians are 0.03828/0.03853 seconds. With five samples, the nearest-rank 95th
percentile is the reported maximum. Completion is 5/5 per case. Query-only
throughput is approximately 19.6 and 26.0 advances/second on head; this excludes
scene initialization and cannot be extrapolated to games.

All ten head advances complete. Aircraft have no numerical OC contribution, so
both base and head retain no controller in these scenes. The fixture measures
boundary cost and event ordering, not a numerical-control defect. The numerical
regression uses an isolated infantry model removed for coherency, with control
and its mission award retained before removal. The declared envelope remains
2× the matching base mean/maximum plus 100 ms; no numeric limit was raised.

The original OC 4 v1 Aircraft workload was rules-invalid and is withdrawn.
Its reports are archived in `withdrawn-oc4/` and excluded from active gates.
The corrected v2 base/head pair uses the same typed source-dash fixture in both
runtimes. The Order 66 Aircraft base at its original revision is also remeasured
with this shared fixture; the original base/head samples are preserved in that
archive. All other historical baselines remain unchanged.

Reproduce with this checkout's harness and an isolated base source tree containing
its committed `src`, `contracts/schemas` and `pyproject.toml`:

```sh
PYTHONPATH=.:scripts uv run --no-sync python scripts/measure_order79.py \
  --runtime-src /path/to/base/src --revision 68c6bccb7d1f44e3b03409a86565a3d285c8449d \
  --output docs/performance/order79/base.json
PYTHONPATH=.:scripts uv run --no-sync python scripts/measure_order79.py \
  --runtime-src src --revision '<verified-runtime-id>' \
  --output docs/performance/order79/head.json
```

Inherited current-runtime measurements for Orders 64–66 and 69–78 are refreshed
serially using their existing scripts and budgets, including both Order 73 and
Order 77 workloads. All numeric limits remain unchanged; the corrected Aircraft
baseline treatment is described above.

Order 77's canonical helpers required the same boundary-history repairs as the
behavioral tests. `inherited-fixture-migration.json` pins the two old/new helper
hashes; its gate still rejects all other input drift and checks the unchanged
roster/mission initializer functions. Movement workloads are unchanged. Completed
Cleanse restores now include required final-phase history, so those inherited
cost comparisons do not use byte-identical saves. They retain all prior samples
and numeric limits; the separate Order 79 pair above uses identical harness inputs.

Complete games attempted/completed: **0/0**. The repository still lacks a
representative legal complete-game driver/recording. No per-game mean or maximum
is claimed; the mean below 60 seconds and observed maximum at most 300 seconds
remain uncertified. Order 32's broader efficiency deferral remains in force.

`preflight.json` and `validation.json` retain the pre-approval audit and its
then-current limits. `implementation-validation.json` records the approved repair's
final checks, attempts and evidence hashes.
