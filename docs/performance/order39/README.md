# Order 39 query performance evidence

This is component evidence on provisional local hardware, not complete-game
certification. The standing mean-under-60s / observed-maximum-under-300s full-game
targets and Order 32 deferral remain unchanged.

`base.json` measures main `304d828f71e137d7cfc4f7ee9c5788b288322854` exported into an
isolated directory, using the same script, interpreter, lock and canonical
helpers as head. The incorrect base is only a cost comparison: it has no new
Stealth Cover snapshots. The four cases have ten models, no terrain, no dice
calls and no policy search. Each of seven samples separately prepares real
canonical units and measures 100 attack modifier queries without coverage or
profiling. Metadata, hashes, all samples, mean/median/P95/max, completion and
throughput are retained. Reported P95/max concern sample-average query times,
not a per-query worst-case bound. No cases or failures were discarded.

The committed budget was set before head measurement: mean at most 1.5 times
base plus 1 ms, and maximum sample average 10 ms. The additive allowance avoids
amplifying sub-millisecond host noise and accounts for constructing the newly
required source commitments. At an estimated 1,000 modifier queries per game,
the absolute ceiling would consume 10 seconds of the 60-second objective; that
call count is an estimate, not measured full-game evidence. No existing budget
was raised. No cache was introduced, and the source/model-footprint regressions
supply deterministic correctness checks alongside the retained timing gate.

Reproduce from repository root with:

```sh
PYTHONPATH=.:src uv run python scripts/measure_stealth_cover.py --output docs/performance/order39/head.json
```

Run base/head without competing test workers. Regenerate runtime identity first;
retain the matching script and fixture hashes when exporting the base. The script
uses macOS `sysctl` to record this declared host's CPU and memory. The fast required
code-quality gate verifies workload/environment comparability, retained results,
completion and unchanged thresholds. Full-game timing remains outstanding until
the supported headless workload and reference hardware can be measured.

The final head on Apple M5 Pro, 64 GiB, macOS 26.6.2 has mean times of
0.051 ms (plain), 0.080 ms (native), 0.123 ms (one grant), and 0.173 ms
(two grants); the largest sample average is 0.175 ms. All four
cases completed all seven samples and pass the unchanged component budgets.
The final measured runtime fingerprint is
`eb908777d82d4cd0512ad368b8a6a6820993ea39d6419ed61c09016264e3617a`.
