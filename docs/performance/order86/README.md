# Order 86 quarter-query diagnostic

The workload measures one primary quarter witness for a real five-model squad,
including geometry materialization and the mission's six-inch centre exclusion.
Ten batches of 100 calls cover overlapping, nominally tangent, clear and distant bases.
Fixture setup is outside the timing boundary. Each sample is a per-query mean.
Base and head run serially without coverage on the same provisional Apple M5 Pro
host and locked dependencies. The base is `c727a6ad08ff9204d5338dabc736bbf767812a1e`.
The incorrect base is a cost comparison, not the correctness oracle.

The fixed budget permits 1.5 times the base mean plus 20 microseconds and requires
every batch's per-query cost below one millisecond. This tolerates host variance
while checking a bounded four-rectangle, five-model operation. It does not
extrapolate a full-game budget or certify gameplay-slice or full-game performance.
The code-quality gate checks matched inputs, script/lock hashes, query counts,
corrected results, runtime identity and these unchanged limits.

The retained run measured the following per-query means on that host:

| Base edge distance from centre line | Base | Head | Head qualifying queries per batch |
| --- | ---: | ---: | ---: |
| 0.01 inches, inside divider | 56.78 µs | 14.14 µs | 0/100 |
| Half a millimetre, nominal tangency with positive overlap | 56.14 µs | 14.22 µs | 0/100 |
| 0.02 inches, clear | 56.08 µs | 53.16 µs | 100/100 |
| 4 inches, distant | 56.19 µs | 52.99 µs | 100/100 |

The maximum head batch mean was 55.54 µs, below the fixed one-millisecond
component ceiling. These finite measurements establish only this workload's cost.
The [R86-001 review repair](r86_001/README.md) replaces rounded supports and
quarter edges with exact rational predicates. Its additional comparison against
the reviewed PR revision and rotated-boundary diagnostic preserve the original
budgets. The nominal tangency pose actually overlaps the exact divider by about
`9.23e-16` inches and is correctly rejected.

Inherited current-runtime diagnostics are rerun rather than relabelled with a
new identity. Their historical baselines and budgets remain unchanged.
The active revival and shared-projection reports live under `order83`; their
historical Order 81/82 reports remain byte-for-byte unchanged. Current-runtime
Order 73 reports use the existing `r73_001` workload directory.
`inherited-fixture-migration.json` pins the two changed secondary helpers:
literal expected quarter IDs decouple the fixture from runtime module ownership,
and an optional position initializer defaults to no action in existing workloads.
`completion-base.json` reruns the unchanged Cleanse workload with the current
helpers against the untouched PR base, providing a fresh matched comparison.

Reproduce against a checkout of each runtime with the same current script:

```sh
uv run python -m scripts.measure_order86 --runtime-src /path/to/base/src \
  --revision c727a6ad08ff9204d5338dabc736bbf767812a1e --output /tmp/order86-base.json
uv run python -m scripts.measure_order86 --runtime-src src \
  --revision order86-reviewed-head --output docs/performance/order86/head.json
```

Full-game samples remain zero, with mean and maximum unknown. Neither standing
full-game target is claimed to pass.
