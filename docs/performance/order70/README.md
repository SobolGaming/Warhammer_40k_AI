# Order 70 Fights First query assessment

Order 71 refreshed the head JSON for runtime `1418bd17` with unchanged
workloads, baselines and budgets. The tables and prior validation below are
historical; current gate results are recorded in
[Order 71 validation](../order71/validation.json).

The versioned `order70-fights-first-v1` workload measures 100 complete live
registry queries with zero, one and four unit grants in the existing canonical
Firing Deck fixture (four units, sixteen models). Preparation is outside the
timer. Seven serial samples run without coverage, profiling or competing workers
on the same provisional Windows host and Python/dependency lock. Exact workload,
fixture and lock hashes, machine details, runtime identity, mean and maximum are
retained in `base.json` and `head.json`.

The base is `6ee55f30`; the base's incorrect model semantics are a cost comparison,
not a correctness oracle. The unchanged workload uses unit grants so its source
counts remain comparable. Intrinsic, attached, retained, split and model-only
correctness is covered by the behavioral regressions.

The committed component budget is `head <= base * 3 + 0.05 seconds` for each
100-query mean and maximum. This permits the new model/source proof while
bounding the formerly empty query at a 0.5 ms additive per-query cost. It does
not establish a complete-game budget. The required code-quality suite checks
matched inputs, completion, source counts, current runtime identity and every
threshold without dropping a workload case.

| Unit grants | Base mean (s) | Head mean (s) | Base maximum (s) | Head maximum (s) |
| --- | ---: | ---: | ---: | ---: |
| 0 | 0.000151 | 0.003850 | 0.000171 | 0.004198 |
| 1 | 0.003990 | 0.029864 | 0.004031 | 0.033669 |
| 4 | 0.014797 | 0.034356 | 0.014864 | 0.038009 |

All six mean/maximum comparisons pass. The head measures 0.04–0.34 ms per
query in this scene. This quantifies the new proof cost without implying a
complete-game result.

Reproduce with the corresponding runtime and no competing workers:

```powershell
uv run python -m scripts.measure_order70 --output docs/performance/order70/base.json --revision 6ee55f30 --runtime-src reports/order70-base/src
uv run python -m scripts.measure_order70 --output docs/performance/order70/head.json --revision order70-review
```

The exact-runtime reconstruction, Firing Deck, Aircraft and roster-validation
guards from Orders 64, 65, 66 and 69 also require refreshed head evidence for this
build; all were freshly measured with unchanged baselines, workloads and budgets.
Final validation outcomes are retained in `validation.json`.

Gameplay-slice and complete head-to-head performance remain unmeasured. The
60-second mean / 300-second maximum full-game targets and deferred Order 32
budgets are not certified.

The empty-inventory correction preserves native-source validation before avoiding
unit membership/target scans when no Fights First grant exists. It resolves the
existing Order 34 live work-guard failures without raising their limits. These
head reports were freshly measured after the scope/completeness review corrections
for runtime `fd6608be`. The first aggregate results and the superseded
reviewed-head validation remain in `validation.json`.
