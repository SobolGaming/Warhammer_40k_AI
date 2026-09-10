# R34-002 sequence-origin repair: current-runtime performance

Base: `e56c1a4caf2a6915548222caed0872627f8dbf43`.
Measured candidate: `909bced7d5d053282f3887821cb6ce0fcbaa5252`.
Source tree: `bb239fac9970d7a9a0ba46f94ff23ad87dfe62f2`.
Runtime: `ac34d042332ffbf63e8b2b1d666767a62c2f2763f7aa573b57c1a240ef643cc3`.
Engine manifest SHA256: `7e817c961c4ce9ab4bc45d4b66acc83d34eb4a3f7eb4a4c30110c83585e0fa00`.

All **98 uninstrumented timings** and **eight separate work profiles** completed.
All unchanged absolute, relative and work budgets passed. The existing bounded
runner exited zero after **233.498 s**. Measurements ran serially on
the same provisional Apple M5 Pro / 64 GiB / macOS 26.6.2 / Python 3.14.5 host,
without coverage, profiling or competing task-owned validation workers. Work
profiles ran separately. No threshold or workload was changed.

| Case | Base mean s | Head mean s | Head maximum s | Mean change |
|---|---:|---:|---:|---:|
| action | 0.10598 | 0.10678 | 0.11722 | +0.75% |
| unrestricted | 0.06365 | 0.05946 | 0.06637 | -6.59% |
| attached_selection | 0.00546 | 0.00339 | 0.00381 | -37.99% |
| retained | 0.17522 | 0.17408 | 0.19853 | -0.65% |
| visible-self-observer | 0.10379 | 0.10894 | 0.11153 | +4.96% |
| unseen-no-observer | 0.36462 | 0.38576 | 0.43010 | +5.80% |
| unseen-friendly-observer | 0.28687 | 0.29858 | 0.32675 | +4.08% |

The [specification](benchmark-spec.json) retains all seven workloads.
[Input hashes](benchmark-input-manifest.json) cover all 15 recursive local
drivers/helpers and the dependency lock; identical bytes were installed in both
checkouts. The production trees were clean at their exact measured commits.
[Budget validation](budget-validation.json) contains arithmetic and work counts;
raw reports preserve every sample, setup interval, percentiles and runtime hashes.
Head work counts match the earlier independently accepted repair. Timing variation
does not establish a live-gameplay speedup from this restoration-only correction.

Reproduce with the [existing commands](../review-repair/README.md#reproduction),
using this candidate's pinned benchmark inputs on both revisions and output
directory `docs/performance/order34/review-sequence`. Change only the report
directory in the comparison script; retain the versioned budgets. Prior evidence
in `review-repair` and `review-relabel` remains historical, separately attributable
to its measured revisions.

The full attached-declaration solver diagnostic was **not rerun**. Historical
base/head timeout outcomes and traces remain in
[review-repair](../review-repair/README.md#incomplete-diagnostic-and-full-game-evidence).
The solver is unchanged by this repair. Those probes remain incomplete; the
attached-selection workload does not replace the full declaration diagnostic.
Full-game mean below 60 s and no measured game above 300 s remain **uncertified**.
No Order 32 performance exception is extended.
