# Order 58 performance and validation

The matched component workload uses the same compact shooting attacker plus
isolated defender model on base `e693fd01` and head. Each sample resolves one
grouped failed-save Damage-to-0 attack sequence. Fixture creation is excluded.
The first sample is cold. All seven samples and host/input hashes are retained.
The available Windows Threadripper 3970X host is provisional, with Python 3.14.5
and the same locked dependencies. Timings use one process without coverage or
instrumentation.

The final matched mean is **27.63 ms base / 17.35 ms head**, with maxima
**86.80 ms / 30.31 ms**. All seven samples completed. Head also records one
`failed_save_damage_replaced` event and unchanged defender wounds. These are
component diagnostics only. Gameplay-slice and full-game throughput remain
unmeasured. The standing 60-second mean / 300-second maximum complete-game goals
are not certified.

Reproduce against base and head runtime trees with the same final benchmark and
helper files:

```sh
uv run --no-sync python scripts/measure_order58.py \
  --output docs/performance/order58/base.json \
  --revision <base-commit> \
  --runtime-src <base-tree>/src
uv run --no-sync python scripts/measure_order58.py \
  --output docs/performance/order58/head.json \
  --revision <runtime-or-commit> \
  --runtime-src src
```

A timeout or failed assertion is not a completed sample. Median, nearest-rank
95th percentile, maximum, completion rate and preparation costs are retained.

## Final gates

Validated on 2026-09-18 against runtime identity
`3c90bd4a5b1d19c036ad549ccc2932ec262d125835217023dc18740a2d96c9d5` on Windows 11
/ AMD Ryzen Threadripper 3970X / Python 3.14.5. Both complete suites used xdist
auto work stealing. The behavioral run included Node.js 24.18.0 on `PATH`. Wheel
smoke used `UV_SYSTEM_CERTS=true` for this host's certificate trust chain. No
production code changed after the final behavioral coverage gate. No behavioral
suite was repeated without coverage as a second final gate.

- Complete behavioral suite with coverage: **8,358 passed**, **85.13%**
  coverage (85% required), 979.30 seconds. The eight-shard inventory lists 244
  behavioral files, including the new Order 58 unit module.
- Complete code-quality suite without coverage: **517 passed**, 295.32 seconds.
- Ruff check and format check, mypy (3,107 source files), Pyright (zero errors),
  all 11 import-linter contracts, and pre-commit passed.
- Reviewed source generator, engine build identity and external-contract checks
  passed, including contract compatibility against base `e693fd01`.
- TypeScript generated-client/type checks and all five client unit tests passed;
  conformance passed all **342 assertions** on contract **26.0.0**.
- Installed-wheel smoke verified **2,865 runtime resources**, **27 schemas** and
  all six request families.

`validation.json` records the same totals. These are component measurements
only. Gameplay-slice and full-game throughput remain unmeasured.
