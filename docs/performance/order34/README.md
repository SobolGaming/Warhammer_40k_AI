# Order 34 Action and shooting restriction assessment

The historical 9699f8f8 repaired-runtime evidence for **R34-003** is in
[review-9699/README.md](review-9699/README.md). It preserves all original
cases and adds live selection, attached and retained-reaction work gates.
The final R34-002 follow-up runtime requires fresh measurements, recorded separately.
The e57 evidence below is historical.

The base is `e56c1a4caf2a6915548222caed0872627f8dbf43`; the measured runtime
head is `e57e8be02aa744354d8d078a78be39024ab44643`. Both ran on the same
provisional Apple M5 Pro host with 64 GiB RAM, Python 3.14.5 and the same
locked dependencies. Timing ran serially, without coverage, profiling, or
competing test workers. Driver, helper and lock hashes match between revisions.
The reports retain all seven samples per revision and case, setup time,
mean, median, p95, maximum, completion rate and throughput.

| Slice | Base mean s | Head mean s | Head max s | Mean change |
|---|---:|---:|---:|---:|
| Action start, 300 eligibility queries, four expiration boundaries | 0.1130 | 0.1146 | 0.1187 | +1.41% |
| Visible shooting, self observer | 0.1188 | 0.1181 | 0.1214 | -0.53% |
| Unseen shooting, no observer | 0.4089 | 0.4129 | 0.4680 | +0.98% |
| Unseen shooting, friendly observer | 0.3238 | 0.3260 | 0.3555 | +0.66% |

All 56 timed base/head samples completed. `budget-validation.json` checks the
raw results against the committed limits, including comparable workload hashes.
Existing Order 33 shooting budgets are unchanged. The preceding candidate's unseen/no-observer mean was 0.4493 s, close to its
0.45 s ceiling; that run is retained at
`/private/tmp/order34-evidence/checkpoint-955-head-shooting-timing.json`.
The final runtime was remeasured because the mutation-owner repair changed its
identity. Work counts are identical; the timing difference is not evidence that
this small API correction materially improved performance. These finite
measurements do not guarantee future shared-host timings. Its work-count regression
also passes with the added current-option preflight.

The Action component uses a real mission Action opportunity, submits its finite
decision through the engine decision controller, and applies the engine-owned
mission decision. It then queries Action, shooting and charge restrictions
100 times each and submits the three phase-end and one turn-end boundaries to
the existing expiry service. Setup is outside the timed interval. This measures
the shared component, not facade orchestration or a complete game. The shooting
slices reuse the Order 33 LocalGameSession workload, including accepted
declaration, completed attacks and the new activity effect. Setup, movement,
initial request generation and session restoration are reported separately.

Separate cProfile runs record work counts; their wall times are not timing
evidence. Base/head Action counts are 425/524 rules-unit view resolutions,
514/112 identity lookups and 119/523 effect-lineage lookups. Head records exactly
one persistent effect and visits exactly four expiration boundaries. Queries
scan the current effect inventory through the existing lineage service, never
the complete decision or Action history. No cache or approximate solver is added.

Initial Action CI ceilings are 540 view resolutions, 120 identity lookups,
540 lineage lookups, one effect insertion and four expiration calls. These
bound the measured work with small explicit headroom. The provisional local
timing ceilings are 0.20 s mean, 0.25 s maximum and a 1.25 head/base mean ratio;
the observed mean is 0.115 s and the comparison is 1.014. Shared CI runners
enforce work counts, not host-specific timing. This is a new Order 34 budget,
not an extension of the Order 32 deferral.

Full-game performance is **uncertified**. Neither component timings nor these
one-attack gameplay slices establish the standing arithmetic mean below 60 s
and no measured game above 300 s on a declared complete-game workload. No
full-game framework or training system was built for this task.

Reproduce on each revision with identical final driver/helper files:

```sh
uv run python -m scripts.measure_action_restrictions --samples 7 --output action-timing.json
uv run python -m scripts.measure_action_restrictions --samples 1 --work-counts --output action-work.json
uv run python -m scripts.measure_indirect_shooting --samples 7 --output shooting-timing.json
uv run pytest tests/code_quality/test_order34_action_restrictions.py tests/code_quality/test_order33_indirect_shooting.py --no-cov -q
```

The exact base was measured in `/private/tmp/order34-base` with the repository
virtual environment and `PYTHONPATH=.:src`. Its runtime source remained at the
base commit; only matching benchmark/helper inputs were copied. The final
measurement runner evidence is in
`/private/tmp/order34-evidence/candidate-e57-performance.{json,log}`. Earlier
calibration runs remain there and are not substituted for these final reports.
