# Order 60 performance and validation

The matched component workload uses the same five-model Emergency Disembark
contact-ring placement on base `4cb16b1d` and head. Each sample resolves one
canonical Transport fixture. Fixture creation is excluded. The first sample is
cold. All seven samples and host/input hashes are retained. The available
Windows Threadripper 3970X host is provisional, with Python 3.14.5 and the same
locked dependencies. Timings use one process without coverage or
instrumentation.

The final matched mean is **4.13 ms base / 21.85 ms head**, with maxima
**8.42 ms / 109.13 ms**. All seven samples completed and were valid. Head's
added cost is the exact circular existence proof for closest-possible and
omitted-model obligations. These are component diagnostics only. Gameplay-slice
and full-game throughput remain unmeasured. The standing 60-second mean /
300-second maximum complete-game goals are not certified.

Reproduce against base and head runtime trees with the same final benchmark and
helper files:

```sh
uv run --no-sync python scripts/measure_order60.py \
  --output docs/performance/order60/base.json \
  --revision <base-commit> \
  --runtime-src <base-tree>/src
uv run --no-sync python scripts/measure_order60.py \
  --output docs/performance/order60/head.json \
  --revision <runtime-or-commit> \
  --runtime-src src
```

A timeout or failed assertion is not a completed sample. Median, nearest-rank
95th percentile, maximum, completion rate and preparation costs are retained.

## Final gates

Validated on 2026-09-18 against runtime identity
`413c41a7d28daef7af9faeb4b19c734d993d5724754e8fd93fcc06fa082ebc0e` on Windows 11
/ AMD Ryzen Threadripper 3970X / Python 3.14.5. Both complete suites used xdist
auto work stealing. The behavioral run included Node.js 24.19.0 on `PATH`. Wheel
smoke used `UV_SYSTEM_CERTS=true` for this host's certificate trust chain. No
production code changed after the final behavioral coverage gate. No behavioral
suite was repeated without coverage as a second final gate. Component timings
and helper hashes are unchanged after that coverage run.

- Complete behavioral suite with coverage: **8,373 passed**, **85.11%**
  coverage (85% required), 973.58 seconds. The eight-shard inventory lists 246
  behavioral files, including the new Order 60 unit module.
- Complete code-quality suite without coverage: **523 passed**, 316.80 seconds.
- Ruff check and format check, mypy (3,118 source files), Pyright (zero errors),
  all 11 import-linter contracts, and pre-commit passed.
- Reviewed source generator, engine build identity and external-contract checks
  passed, including contract compatibility against base `4cb16b1d`.
- TypeScript generated-client/type checks and all five client unit tests passed;
  conformance passed all **342 assertions** on contract **26.0.0**.
- Installed-wheel smoke verified **2,872 runtime resources**, **27 schemas** and
  all six request families.

`validation.json` records the same totals. These are component measurements
only. Gameplay-slice and full-game throughput remain unmeasured.
