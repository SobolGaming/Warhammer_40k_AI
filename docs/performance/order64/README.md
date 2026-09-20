# Order 64 authenticated reconstruction guard

The workload isolates `GameLifecycle.from_payload()` and `LocalGameSession.fork()`
after a loaded Transport's Ingress, after its cargo's Rapid Disembark, and after
the next accepted unit-selection decision. Each reconstruction starts from the
same fixed checkpoint. It must exactly reproduce the saved payload, leave the
original unchanged, and create independent lifecycle and state objects.

Restore timing excludes input copying. Fork timing includes its actual
serialization, deep copy and authenticated restore. Fixture construction,
Ingress/Disembark preparation and equality assertions are outside both timers.
Seven unprofiled serial samples per operation retain mean, median, nearest-rank
p95 (the maximum for seven samples), maximum and operations per second. Separate
profiled samples measure work; profiler timings are never used for timing gates.

`budgets.json` was declared before the qualified matched measurements. The mean
limit is base × 1.30 + 50 ms; the maximum limit is base × 1.40 + 100 ms. These are
component regression limits on the recorded provisional host, not full-game
budgets. CI validates the retained comparison and executes all six profiled
operations against the current engine. It requires one authentication replay,
four lifecycle reconstructions, one arrival resolution, and exactly the accepted
suffix's 1/4/5 replayed decisions. Total profiled calls may not exceed 125% of the
matching baseline, catching growth inside those entry points as well as duplicate
replay. Exact authentication is never skipped or replaced by a cached answer.

The baseline is Order 63 at `d3a9d3b4`. Both revisions use the same measurement
script, canonical fixtures, dependency lock, host and single-process workload.
Reports retain their hashes, runtime identity, payload sizes, record counts and
all samples. Input text hashes normalize line endings so the same workload is
verified on Windows and Linux; CI checks these against the current files.

Retained head timing evidence must describe the current verified engine build:
CI requires `head-reconstruction.json["runtime_build_id"]` to equal
`verified_engine_build_identity().build_id`. Any runtime identity change requires
fresh qualified head measurements before this guard can pass, even when all live
work counts remain unchanged. Regenerate the runtime manifest before measuring;
never update only the report's identity to relabel old samples. Changes outside
the runtime fingerprint and workload inputs do not require new measurements.
Preserve the declared budgets and all replay/work-count assertions when refreshing
evidence. Use the same baseline revision, host, dependency lock, workload inputs
and timing boundaries; if those measurement conditions change, remeasure both
base and head under matching conditions. Commit the qualified reports and update
their results below.

Run without coverage or competing test/build workers:

```powershell
uv run python -m scripts.measure_ingress_reconstruction --output docs/performance/order64/base-reconstruction.json --revision d3a9d3b4 --runtime-src <base-checkout>/src
uv run python -m scripts.measure_ingress_reconstruction --output docs/performance/order64/head-reconstruction.json --revision <head-runtime-identity>
```

The provisional host is Windows 11 (10.0.26200), Python 3.14.5, an AMD Ryzen
Threadripper 3970X (32 cores / 64 logical processors), and 137,327,259,648 bytes
of physical memory. The canonical scene has four units and sixteen models,
empty terrain and no dice in the measured workload.

| Checkpoint | Operation | Base mean / max (s) | Head mean / max (s) |
| --- | --- | ---: | ---: |
| Loaded ingress | Restore | 3.847 / 4.064 | 3.869 / 4.137 |
| Loaded ingress | Fork | 3.862 / 3.916 | 3.877 / 4.039 |
| Rapid Disembark | Restore | 3.889 / 3.982 | 3.893 / 3.967 |
| Rapid Disembark | Fork | 3.921 / 3.986 | 3.936 / 4.130 |
| Later accepted decision | Restore | 3.905 / 4.019 | 3.867 / 3.949 |
| Later accepted decision | Fork | 3.930 / 3.995 | 3.927 / 4.018 |

Order 68 refreshed the 42 head timings and six independent profile samples for
the current runtime build on 2026-09-20, retaining the qualified baseline and
unchanged workload and budgets. Every reconstruction completed with exact
reproduction and parent isolation. All six comparisons pass, with authentication
and suffix counts preserved. These measurements do not establish a speedup.
See [Order 68 validation](../order68/validation.json).

At the measured checkpoint cost, ten sequential forks would consume about
39 seconds. This is a linear estimate, not an observed planning workload;
actual forks per phase/game remain unmeasured.

The guard deliberately leaves the independently rooted replay authentication
intact. It supplies a measured boundary for future changes; it does not implement
search/planning or claim a constant-time fork. Longer histories outside these
three checkpoints, gameplay slices, and complete head-to-head games remain
unmeasured. The 60-second mean / 300-second maximum full-game targets and deferred
Order 32 budgets are not certified by these component results.

Final correctness and publishing-gate outcomes are retained in `validation.json`.
The original Order 64 suite passed 8,467 behavioral tests at 85.12% coverage and all 545
quality tests, including the live reconstruction work guards. Required lint,
type, import, shard, generator, compatibility, client/conformance, wheel and
pre-commit checks passed. No production code changed after that coverage run began. Current Order 67
validation is recorded separately.

The Order 65 validation exposed suite-context-dependent cProfile call accounting
in Windows xdist workers. The live reconstruction guard now runs each single
profile in a fresh subprocess, matching standalone evidence execution. It retains
the same real fixtures, exact replay/equality checks and every existing work
limit; no performance budget was raised. See the Order 65 validation record for
the failed attempts and focused diagnostic results.
