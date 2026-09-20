# Order 66 Aircraft component assessment

The matched workload measures 100 unchanged battlefield submissions through the
shared mutation guard and one opponent turn boundary through the next decision.
It uses one or two Aircraft plus five enemy infantry, empty terrain, canonical
seed and the same helper, script and dependency lock on base and head. Fixture
construction and catalog preparation are excluded. The base is `48b69113`; its
failure to return Aircraft is a correctness defect, so it is only a cost comparison.
The frozen base worktree was measured after initial implementation, before final
aggregate validation. The workload and numeric budgets were defined in the
working tree before measurement; no thresholds were raised after seeing results.

Both revisions ran serially without coverage, profiling or competing test/build
workers on the same provisional Windows 11 host: Python 3.14.5, AMD Ryzen
Threadripper 3970X, 64 logical CPUs and 137,327,259,648 bytes RAM. Seven samples
per case retain preparation time, mean, median, nearest-rank p95 (maximum for
seven samples), maximum, throughput and exact input/runtime hashes. All samples
completed. Every head boundary returned its full Aircraft fleet; the base returned
none.

| Aircraft | Operation | Base mean / max (s) | Head mean / max (s) |
| --- | --- | ---: | ---: |
| 1 | 100 mutation guards | 0.008290 / 0.010731 | 0.014437 / 0.017496 |
| 1 | Opponent turn boundary | 0.160629 / 0.170822 | 0.159915 / 0.174638 |
| 2 | 100 mutation guards | 0.009367 / 0.012321 | 0.016538 / 0.016918 |
| 2 | Opponent turn boundary | 0.170526 / 0.174009 | 0.177616 / 0.183950 |

The mean budget is base x 1.5 plus 50 ms per 100 guards or 200 ms per boundary;
the maximum budget is base x 2 plus 300 ms. These provisional allowances cover
small-sample variability and newly required canonical presence/source evidence.
All Aircraft comparisons pass. CI verifies identical input/environment fields,
current runtime and input hashes, completion, full-fleet return and numeric limits.

The existing Order 35 Rapid Ingress work guard also passes without changing its
limits. Movement candidate enumeration reuses its canonical unit view for the
shared Aircraft lock instead of rebuilding that view four additional times.

At the measured means, 1,000 guards plus ten boundaries would cost under two
seconds. This is a component extrapolation: actual calls, complete gameplay slices
and full head-to-head games remain unmeasured. The standing 60-second mean and
300-second observed maximum game targets, and deferred Order 32 budgets, are not
certified by this evidence. Reconstruction and Firing Deck evidence retain their
existing workloads and budgets in the Order 64 and Order 65 directories.

Reproduce with no competing test/build workers after regenerating engine identity:

```powershell
uv run python -m scripts.measure_order66 --output docs/performance/order66/base.json --revision 48b69113 --runtime-src <base-checkout>/src
uv run python -m scripts.measure_order66 --output docs/performance/order66/head.json --revision <current-engine-build-id>
uv run python -m scripts.measure_ingress_reconstruction --output docs/performance/order64/head-reconstruction.json --revision <current-engine-build-id>
uv run python -m scripts.measure_order65 --output docs/performance/order65/head.json --revision <current-engine-build-id>
```

Final required gate results are retained in `validation.json`.
