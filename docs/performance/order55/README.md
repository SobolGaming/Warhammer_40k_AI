# Order 55 performance and validation

The matched component workload resolves four disembarks with real canonical
armies and identical final fixtures: a five-inch base within one inch, the same
base beyond one inch, a three-inch base that could fit elsewhere, and an ordinary
two-inch base. Base `62f6e7b6` rejects the first three and accepts the last. Head
accepts only the first and last. All seven samples agree.

The provisional host, CPU, memory, interpreter, input/lock hashes, timing boundary,
cold first sample and every result are retained in `base.json` and `head.json`.
Mean time per four resolutions is **2.54 ms base / 2.75 ms head**, with maxima
**3.26 ms / 4.58 ms**. The predeclared budget (mean at most three times base plus
50 ms, maximum under one second) passes. Runs are serial without coverage or
competing tests. Fixture creation is excluded. The head runtime is
`b78a1e9eff48d0c55b1bd689011b08f30497ed9e16876bcb07018013981ee26c`.

Reproduce against base and head runtime trees with the same final benchmark and
helper files:

```sh
PYTHONPATH=src:. uv run --no-sync python scripts/measure_order55.py \
  --output docs/performance/order55/head.json --revision <runtime-or-commit>
PYTHONPATH=src:. uv run --no-sync python scripts/measure_order55_geometry.py
```

`geometry.json` retains seven cold-cache samples for six asymmetric analytic
queries, including the two exploratory quantified cases that were interrupted
without an answer before exact finite certificates were introduced. The final
workload includes both positive and negative proofs, with a one-second bound per
six-query sample. Interrupted prototypes are not counted as passed results.
The focused regressions also execute these cases and verify distinct shape and
distance cache inputs. Certificates never turn failed sampling into impossibility.

These are component measurements only. Gameplay-slice and full-game throughput
have not been measured; the standing 60-second mean / 300-second maximum
full-game targets and deferred Order 32 budgets are not certified by this PR.

## Final gates

The final runtime above passed these local gates on macOS 26.6.2 / Apple M5 Pro
with Python 3.14.5. Both complete suites used 18 xdist workers with work stealing;
the behavioral run included the desktop Node runtime on `PATH`. HTTP and client
checks ran with permission to start local test servers.

- Complete behavioral suite with coverage: **8,306 passed**, **85.12%**
  coverage (85% required), 668.82 seconds.
- Complete code-quality suite without coverage: **511 passed**, 136.36 seconds.
- Ruff check and format check, mypy (3,082 source files), Pyright (zero errors),
  all 11 import-linter contracts, and pre-commit passed.
- Reviewed source generator, engine build identity and external-contract checks
  passed, including contract compatibility against base `62f6e7b6`.
- TypeScript generated-client/type checks and all five client unit tests passed;
  conformance passed all **342 assertions** on contract **25.0.0**.
- Installed-wheel smoke verified **2,844 runtime resources**, **27 schemas** and
  all six request families.
- All eight CI shard manifests were regenerated from the successful covered
  JUnit profile (242 behavioral files / 8,306 cases); the fail-closed inventory
  check passed. `ci/test_shards/durations.json` records the profile hash and host.
