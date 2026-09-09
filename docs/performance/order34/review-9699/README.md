# R34-003 historical measurements of runtime 9699f8f8

Base: `e56c1a4caf2a6915548222caed0872627f8dbf43`.
Measured runtime commit: `9699f8f8aaebc1a452b11eafda9fe14f1cddd6b9`.
Source tree: `5600a32eea7d6e2632b191ac47ce8ffcfe73f133`.
Engine build: `warhammer40k-core-v2:runtime-tree-sha256-v1:9be98c85b8f070159b529fef2bf72bc9f73da1ca7bfe096fdb0fc5b6581bfc2c`.
These measurements precede the follow-up R34-002 declaration-authority repair.
They are retained as historical evidence; final runtime measurements are recorded separately.

All **98 uninstrumented samples** (seven per base/head case) completed, and all
versioned timing and CI work budgets passed. The original component and all
three Indirect cases remain; their limits were not increased. Reports retain
all samples, setup time, mean, median, p95, maximum, completion rate, throughput,
revision, source-diff hash, manifest hash and matching workload/helper/lock hashes.
An incorrect base is a cost comparison, not a correctness oracle.

| Case | Base mean s | Head mean s | Head maximum s | Mean change |
|---|---:|---:|---:|---:|
| action | 0.12299 | 0.12116 | 0.12717 | -1.49% |
| unrestricted | 0.07488 | 0.07280 | 0.07951 | -2.79% |
| attached_selection | 0.00693 | 0.00415 | 0.00493 | -40.14% |
| retained | 0.21144 | 0.21248 | 0.25242 | +0.49% |
| visible-self-observer | 0.12635 | 0.12742 | 0.13643 | +0.84% |
| unseen-no-observer | 0.42685 | 0.44885 | 0.53079 | +5.16% |
| unseen-friendly-observer | 0.33270 | 0.34616 | 0.38962 | +4.05% |

Timing ran serially on the same provisional Apple M5 Pro / 64 GiB / macOS 26.6.2
host, Python 3.14.5 and `uv.lock`, without coverage, profiling or competing test
workers. Instrumented work-count samples ran separately; their wall times are
not timing evidence. The runner `repair-final-performance` completed in 267.074 s
with exit zero; full command/log metadata is retained in the execution evidence.
The unseen/no-observer case is close to its unchanged 0.45 s mean ceiling;
these finite observations do not guarantee shared-host performance.

## Workload coverage and calibration

The original Action component still accepts one real mission Action, queries
three eligibility paths 100 times each and visits four explicit expiry boundaries.
The additional `scripts/measure_action_restriction_live.py` driver uses the same
canonical fixture files and deterministic decision policy on both revisions:

- `unrestricted`: a real legal shooter and friendly observer, 32 generic live
  effects, finite shooting-unit selection and submission preflight, Normal
  declaration, completed attacks, actual shooting completion and charge choices.
- `attached_selection`: the same legal selection with an attached opposing
  rules unit and 32 effects. It ends at the real shooting-type request, before
  target-declaration construction. It is one decision and its own workload ID.
- `retained`: a real pending Shoot On Death choice, 32 effects, accepted retention,
  that model's out-of-phase declaration and completed attack, cleanup/parent
  continuation, then actual phase/charge completion choices (five decisions).

The CI test checks exact case inventory, effect count, decision count, charge
reachability, submission-preflight count and all named work ceilings in
[`../budgets.json`](../budgets.json). Limits have roughly 4–14% headroom for the
measured view/effect work; geometry-solver and boundary multiplicities cannot
grow. Initial calibration measured 41 view / 1,504 effect / 57 line-of-sight calls
for attached selection. It exposed all-unit enumeration duplicated by preflight.
Restricting the existing legality function to the selected unit in preflight and
application gives 25 / 1,056 / nine calls; base uses 23 / 832 / 30. The extra
current-effect checks are explicit, while unrelated target work is removed.
Phase completion still validates its full skipped-unit inventory. No cache,
geometry approximation or history scan in hot eligibility was added.

New provisional time ceilings are 0.20/0.25 s mean/max for unrestricted,
0.05/0.075 s for attached selection and 0.45/0.55 s for retained; each keeps the
1.25 head/base mean-ratio limit. They bound short local slices, not total game
calls. CI enforces stable work counts instead of host-specific wall times.
Calibration and raw final counts are retained for independent review.

## Incomplete diagnostic and full-game evidence

The additional `attached` full target-declaration diagnostic exceeded a 150 s
head deadline. Subsequent bounded 30 s base/head probes both stopped in
`Z3_solver_check_assumptions` through the exact continuous-visibility formula
while constructing the Normal declaration. Their JSON outcomes and stack logs
are retained here; none is reported as a completed sample or a rules answer.
The separate attached-selection workload does not replace this diagnostic.
No existing difficult Indirect case was removed. This task does not change the
visibility solver or extend the Order 32 performance deferral to these budgets.

Complete-game mean below 60 s and no measured game above 300 s remain
**uncertified**. No full-game or training framework was built.

## Reproduction

Run on each pinned revision with identical final driver/helper files. The base
checkout is `/private/tmp/order34-base`; its production source stayed unchanged.
Use the repository virtual environment with `PYTHONPATH=.:src` in that checkout.

```sh
uv run python -m scripts.measure_action_restrictions --samples 7 --output action-timing.json
uv run python -m scripts.measure_action_restrictions --samples 1 --work-counts --output action-work.json
uv run python -m scripts.measure_action_restrictions --live-case unrestricted --samples 7 --output unrestricted-timing.json
uv run python -m scripts.measure_action_restrictions --live-case attached_selection --samples 7 --output attached-selection-timing.json
uv run python -m scripts.measure_action_restrictions --live-case retained --samples 7 --output retained-timing.json
uv run python -m scripts.measure_indirect_shooting --samples 7 --output shooting-timing.json
uv run pytest tests/code_quality/test_order34_action_restrictions.py tests/code_quality/test_order33_indirect_shooting.py -q --no-cov
```

For each live case, use `--samples 1 --work-counts` for profiling separately.
The non-terminating diagnostic remains selectable with `--live-case attached`;
use the retained bounded runner command and a process deadline when reproducing.
