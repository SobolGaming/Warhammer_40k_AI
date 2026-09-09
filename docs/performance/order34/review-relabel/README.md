# R34-002 relabelling repair: current-runtime performance

Base: `e56c1a4caf2a6915548222caed0872627f8dbf43`.
Measured candidate: `bf9bd4225fd135ff59c17bbaa7d1c08b6c32b4a5`.
Source tree: `3a8cf3a2979f54251538cb204c2d86cca41f0726`.
Runtime: `5a5378bf4bcfdc69a49e723c4a9e1fe5237a08019dbae5b0a383b1e38608ce65`.
Engine manifest SHA256: `6bfca3d1eeefb2472e538881452d554243168593985931efa5ef84d85bf9d686`.

All **98 uninstrumented samples** and **eight separate work profiles** completed.
All unchanged versioned absolute, relative and work budgets passed. The bounded
runner `r34-round4-performance` exited zero after **224.941 s**. Its measurements
ran before aggregate validation on the same provisional Apple M5 Pro / 64 GiB /
macOS 26.6.2 / Python 3.14.5 host and frozen lock, serially without coverage,
profiling or competing task-owned validation workers. Instrumented work profiles
ran separately. These finite component results are not full-game certification.

| Case | Base mean s | Head mean s | Head maximum s | Mean change |
|---|---:|---:|---:|---:|
| action | 0.10435 | 0.10231 | 0.10412 | -1.96% |
| unrestricted | 0.05989 | 0.05715 | 0.06261 | -4.57% |
| attached_selection | 0.00528 | 0.00319 | 0.00344 | -39.51% |
| retained | 0.17072 | 0.17000 | 0.19351 | -0.42% |
| visible-self-observer | 0.09965 | 0.10037 | 0.10327 | +0.73% |
| unseen-no-observer | 0.35507 | 0.36543 | 0.41581 | +2.92% |
| unseen-friendly-observer | 0.28125 | 0.29235 | 0.31367 | +3.94% |

The current [specification](benchmark-spec.json) retains all seven original
workloads. [Input hashes](benchmark-input-manifest.json) cover all 15 recursively
discovered local drivers/helpers and the dependency lock; identical current bytes
were installed in both checkouts. Production stayed clean at the exact measured
commits. Later evidence-only commits preserve these source and workload inputs.
[Budget validation](budget-validation.json) preserves all raw arithmetic and
work counts. Reports retain every sample, setup time, means, median, p95, maximum,
throughput, runtime identity and workload hashes. No budget, driver or hard case
was altered. Work counts match the previous reviewed runtime; timing variation
is not evidence that this restoration-only change optimizes live gameplay.

Reproduce using the [existing commands and comparison](../review-repair/README.md#reproduction),
with this measured commit's pinned driver/helper inputs on both revisions and
output directory `docs/performance/order34/review-relabel`. In the comparison
code, change only the directory to `review-relabel`; the absolute/relative limits
and work ceilings are unchanged. The raw timing and work filenames are identical.
The previous set remains historical evidence, independently accepted in R34-003
at 29c6cdc0; it is not substituted for this current-runtime measurement.

The full attached-declaration solver diagnostic was **not rerun**. Its historical
base/head timeout outcomes and traces remain in [review-repair](../review-repair/README.md#incomplete-diagnostic-and-full-game-evidence).
The visibility solver is unchanged by this repair. Those probes remain incomplete;
attached selection is a separate workload and does not replace them. Complete-game
mean below 60 s and no measured game above 300 s remain **uncertified**.
