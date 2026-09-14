# Order 47 Charge performance evidence

This matched component/gameplay-slice measurement compares main
`46e2a9b5` with the working-tree engine build recorded in `head.json`.
Both use the same final benchmark script, fixture, dependency lock, fixed game
seed, roster, 15 models, zero terrain, two-segment paths and concurrency one.
The isolated base checkout receives only the final test fixture and benchmark;
its production code and runtime identity remain unchanged. Hardware, interpreter,
script/fixture/lock hashes and every sample are retained in the JSON reports.

| Measurement | Base | Head |
| --- | ---: | ---: |
| Mean Charge slice | 0.019900 s | 0.019838 s |
| Maximum measured slice | 0.022157 s | 0.021409 s |
| Decisions | 3 | 3 |
| Events | 43 | 43 |

All seven samples complete on both revisions. The unchanged predeclared limits
in `budgets.json` pass: head mean at most twice base plus 0.05 seconds, maximum
0.5 seconds, at most three decisions and 75 events. The timed boundary starts
with charging-unit selection and ends after an accepted path and the next
pending decision. Setup is measured separately. Every charging model finishes
within one inch, so this common path requires no alternative endpoint search.

The fixture now records its actual initial placement history. This intentionally
changes the deterministic RNG history. The old benchmark seed no longer selected
a reachable target and failed before completing the intended Charge slice on
both revisions; it produced no valid timing report. The final versioned workload
uses `order47-charge-benchmark-1` on both base and head. No runtime dice injection,
production-code change on base, relaxed budget or discarded measured sample is
used. The nontrivial obstacle, alternative-path, distance-exemption and unresolved
cases retain separate correctness/cache regression coverage.

Reproduce in each checkout, with the identical final script and
`tests/phase15a_charge_declaration_helpers.py` copied to base:

```bash
PYTHONPATH=src:. uv run --no-sync python scripts/measure_charge_endpoints.py \
  --samples 7 --output docs/performance/order47/head.json
```

This is not complete-game certification or a worst-case solver measurement.
Complex-terrain and many-target performance budgets remain unmeasured here;
Order 32's deferred component/full-game certification is not claimed. The
standing full-game mean below 60 seconds and observed maximum below 300 seconds
remain unmeasured. Search exhaustion always remains an explicit unresolved
rules result.
