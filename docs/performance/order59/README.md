# Order 59 performance and validation

The matched component workload uses the same empty Dedicated Transport, reservable
infantry, and opposing infantry on base `d90da49a` and head. Each sample completes
the remaining Declare Battle Formations reserve declarations. Fixture creation is
excluded. The first sample is cold. All seven samples and host/input hashes are
retained. The available Windows Threadripper 3970X host is provisional, with
Python 3.14.5 and the same locked dependencies. Timings use one process without
coverage or instrumentation.

The final matched mean is **22.20 ms base / 230.25 ms head**, with maxima
**29.17 ms / 252.87 ms**. All seven samples completed. Head also records one
destroyed empty Dedicated Transport model and one public
`empty_dedicated_transports_destroyed` event; base records neither because that
mutation is the Order 59 work. The mean additive budget of 0.45 s covers that
new formation-boundary destruction rather than a like-for-like regression of the
reserve-declaration path. These are component diagnostics only. Gameplay-slice
and full-game throughput remain unmeasured. The standing 60-second mean /
300-second maximum complete-game goals are not certified.

Reproduce against base and head runtime trees with the same final benchmark and
helper files:

```sh
uv run --no-sync python scripts/measure_order59.py \
  --output docs/performance/order59/base.json \
  --revision <base-commit> \
  --runtime-src <base-tree>/src
uv run --no-sync python scripts/measure_order59.py \
  --output docs/performance/order59/head.json \
  --revision <runtime-or-commit> \
  --runtime-src src
```

A timeout or failed assertion is not a completed sample. Median, nearest-rank
95th percentile, maximum, completion rate and preparation costs are retained.

## Final gates

Validated on 2026-09-18 against runtime identity
`3fa238faa316cdfff0c749fa083394033143dd81a604db6a6ef563a4388a2820` on Windows 11
/ AMD Ryzen Threadripper 3970X / Python 3.14.5. Both complete suites used xdist
auto work stealing. The behavioral run included Node.js 24.19.0 on `PATH`. Wheel
smoke used `UV_SYSTEM_CERTS=true` for this host's certificate trust chain. No
production code changed after the final behavioral coverage gate. No behavioral
suite was repeated without coverage as a second final gate.

- Complete behavioral suite with coverage: **8,363 passed**, **85.13%**
  coverage (85% required), 964.36 seconds. The eight-shard inventory lists 245
  behavioral files, including the new Order 59 unit module.
- Complete code-quality suite without coverage: **520 passed**, 350.24 seconds.
- Ruff check and format check, mypy (3,112 source files), Pyright (zero errors),
  all 11 import-linter contracts, and pre-commit passed.
- Reviewed source generator, engine build identity and external-contract checks
  passed, including contract compatibility against base `d90da49a`.
- TypeScript generated-client/type checks and all five client unit tests passed;
  conformance passed all **342 assertions** on contract **26.0.0**.
- Installed-wheel smoke verified **2,868 runtime resources**, **27 schemas** and
  all six request families.

`validation.json` records the same totals. These are component measurements
only. Gameplay-slice and full-game throughput remain unmeasured.
