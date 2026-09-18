# Order 56 performance and validation

The matched component workload uses the same canonical two-unit, ten-model
Shooting fixture on base `6a5e84f1f402a9aa0f0839d31c2fabec37f5f06e` and head.
Each sample advances through the shared facade, selects a unit and Normal
Shooting, and stops at Select Weapons. Preparation is measured separately.
The first sample is cold. All seven samples and host/input hashes are retained.
The available Apple M5 Pro host is provisional, with Python 3.14.5 and the same
locked dependencies. Timings use one process without coverage or instrumentation.

The final matched mean is **10.92 ms base / 17.66 ms head**,
with maxima **16.29 ms / 24.63 ms**. All seven samples
completed. The final measurements are in `base.json` and `head.json`. They assess
request generation and lifecycle overhead only. The larger request carries
complete source inventories, including target-dependent grants. No sources or
hard cases were discarded to improve the result. This is a diagnostic under the
owner's deferred component-budget direction; no deferred budget pass is claimed.
Gameplay-slice and full-game throughput remain unmeasured. The standing
60-second mean / 300-second maximum complete-game goals are not certified.

Reproduce with the same benchmark and fixture helper, changing only the imported
runtime tree and recording its identity:

```sh
PYTHONPATH=<runtime-tree>/src:<runtime-tree> uv run --no-sync python \
  scripts/measure_order56.py --output <report.json> --revision <runtime-or-commit>
```

The base worktree was isolated from the implementation checkout. Every sample
must finish the two finite submissions and expose `submit_shooting_declaration`;
a timeout or failed assertion is not a completed sample. Median, nearest-rank
95th percentile, maximum, completion rate and preparation costs are retained.

## Final validation

Validated on 2026-09-17 against the runtime identity in `head.json`:

- Complete behavioral suite: **8,339 passed**, **85.13% coverage** (minimum 85%),
  18 workers with work stealing; 612.49 seconds.
- Complete code-quality suite without coverage: **511 passed**; 115.30 seconds.
- Ruff check/format, mypy (`src tests`), Pyright, all 11 import contracts,
  exact eight-shard inventory check and pre-commit all passed.
- Offline source generator and runtime identity checks, external contract check
  against the exact base commit, installed-wheel smoke, generated TypeScript
  client check, five TypeScript tests and 342 conformance assertions passed.
- Existing Order 34/35 operation-count budgets passed unchanged. Request-scoped
  target inventories and query-local reuse of authenticated rules-unit views
  remove repeated work introduced by complete source discovery.

`validation.json` records the aggregate totals and scope of certification. The
wheel smoke required `UV_SYSTEM_CERTS=true` for this host's certificate trust
chain. The first aggregate run exposed fixture/version expectations and the
Core-family, melee-inventory and redundant-query issues described in the scope
audit; all were resolved before the final run. No production code changed after
the final behavioral coverage gate. No behavioral suite was repeated without
coverage as a second final gate.
