# Order 68 roster model-selection assessment

The pre-game workload validates 2, 4 and 20 units containing 6, 16 and 96 models.
Each request explicitly selects a Warlord and ordinary Enhancement bearer. Both
versions receive identical serialized selections; the old version ignores the
new model fields and is a cost comparison, not a correctness oracle. The selected
composition is instantiated for model-keyword validation. Runtime resolution sorts
only the selected source unit's profile models and authenticates live ownership;
no game-state cache, search algorithm or alternate adapter path is added.

Base 6c10581d and the final head use the same script, lock, provisional Windows
host and single process, without competing test/build workers or coverage. Seven
samples each time 100 complete validate_roster_legality calls, excluding catalog
and request construction. Reports preserve all samples, diagnostics, runtime and
workload identities and CPU/memory allocation. Missing-points reports deliberately
remain in both versions to measure the complete fail-closed validator.

The declared budget is base x 1.5 plus 20 ms per 100-call batch, for both mean and
maximum. It was recorded before the matched measurements. The allowance is
0.2 ms per roster. No thresholds or hard cases are removed during evaluation.

Reproduce from the repository root with an unchanged base checkout:

```powershell
uv run python -m scripts.measure_order68 --output docs/performance/order68/base.json --revision 6c10581d --runtime-src C:/path/to/base/src
uv run python -m scripts.measure_order68 --output docs/performance/order68/head.json --revision <current-engine-build-id>
```

The existing Orders 64/65/66 reconstruction, Firing Deck and Aircraft workloads
also require fresh head measurements for the exact runtime. Their inputs,
baselines and budgets remain unchanged. Their refreshed component evidence does
not certify gameplay-slice or full-game performance. The standing 60-second mean
and 300-second measured maximum full-game targets and deferred Order 32 budgets
remain uncertified.

Final outcomes and diagnostic history are retained in validation.json.

| Units / models | Base mean ms / roster | Head mean ms / roster | Head max batch mean ms / roster |
|---|---:|---:|---:|
| 2 / 6 | 0.1552 | 0.3609 | 0.3658 |
| 4 / 16 | 0.2325 | 0.4394 | 0.4414 |
| 20 / 96 | 0.8563 | 1.0821 | 1.0920 |

All mean and maximum comparisons pass. The initial unshared reconstruction exceeded
the unchanged budget for 2- and 4-unit rosters; diagnostic-unshared-head.json
preserves that result. One per-validation resolver now reuses the selected source
unit for Warlord and Enhancement checks, with no cross-request state. A real
cProfile regression enforces one reconstruction for a shared bearer and verifies
that a subsequent invalid model index is still rejected. The corrected head
adds approximately 0.21 ms per roster for explicit model validation.
