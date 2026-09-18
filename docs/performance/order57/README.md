# Order 57 performance and validation

The matched component workload uses the same two-unit, ten-model canonical
muster on base `3384760f` and head. Each sample runs fifty ordinary closest-
distance queries and fifty still-placed Deadly Demise target enumerations.
Fixture creation is excluded. The first sample is cold. All seven samples and
host/input hashes are retained. The available Windows Threadripper 3970X host is
provisional, with Python 3.14.5 and the same locked dependencies. Timings use
one process without coverage or instrumentation.

The final matched mean is **9.91 ms base / 8.33 ms head**, with maxima
**12.49 ms / 8.38 ms**. All seven samples completed. Head also records fifty
post-removal former-footprint queries whose distance matches the pre-removal
ordinary measurement. These are component diagnostics only. Gameplay-slice and
full-game throughput remain unmeasured. The standing 60-second mean /
300-second maximum complete-game goals are not certified.

Reproduce against base and head runtime trees with the same final benchmark and
helper files:

```sh
uv run --no-sync python scripts/measure_order57.py \
  --output docs/performance/order57/base.json \
  --revision <base-commit> \
  --runtime-src <base-tree>/src
uv run --no-sync python scripts/measure_order57.py \
  --output docs/performance/order57/head.json \
  --revision <runtime-or-commit> \
  --runtime-src src
```

A timeout or failed assertion is not a completed sample. Median, nearest-rank
95th percentile, maximum, completion rate and preparation costs are retained.

## Final gates

Validated on 2026-09-18 against the runtime identity in `head.json` on Windows 11
/ AMD Ryzen Threadripper 3970X / Python 3.14.5. Both complete suites used xdist
auto work stealing. The behavioral run included Node.js 24.18.0 on `PATH`. Wheel
smoke used `UV_SYSTEM_CERTS=true` for this host's certificate trust chain. No
production code changed after the final behavioral coverage gate. No behavioral
suite was repeated without coverage as a second final gate.

- Complete behavioral suite with coverage: **8,348 passed**, **85.12%**
  coverage (85% required), 894.52 seconds. The eight-shard inventory was
  regenerated from that JUnit profile (243 behavioral files / 8,348 cases).
- Complete code-quality suite without coverage: **514 passed**, 346.48 seconds.
- Ruff check and format check, mypy (3,102 source files), Pyright (zero errors),
  all 11 import-linter contracts, and pre-commit passed.
- Reviewed source generator, engine build identity and external-contract checks
  passed, including contract compatibility against base `3384760f`.
- TypeScript generated-client/type checks and all five client unit tests passed;
  conformance passed all **342 assertions** on contract **26.0.0**.
- Installed-wheel smoke verified **2,862 runtime resources**, **27 schemas** and
  all six request families.

`validation.json` records the same totals. These are component measurements
only. Gameplay-slice and full-game throughput remain unmeasured.
