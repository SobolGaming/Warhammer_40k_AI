# R86-001 numerical-boundary repair

The reviewed runtime `79d76f8bd6c174b65f2ab17754beb39f07b6f918` rounded
rotated supports and final coordinates. Exact binary-rational half-plane
containment repairs both false rejection and false acceptance. The source-pinned
one-millimetre divider and six-inch centre exclusion are unchanged.

`quarter-base.json` measures that reviewed revision with the unchanged five-model
quarter-witness workload. Its matching corrected head is `../head.json`.
The original Order 86 baseline and fixed ratio/additive/one-millisecond budgets
remain unchanged; reviewed-revision measurements are an additional comparison.
The nominal half-millimetre pose has a small positive overlap, so corrected head
counts are zero for that row as well as the 0.01-inch row.

`boundary-base.json` and `boundary-head.json` run the same current
`scripts/measure_order86_boundaries.py` against the untouched reviewed runtime and
corrected runtime, respectively. They retain the actual results for both reported
rectangles, two adjacent ellipse border positions and exact rotated ellipse
contact. Every sample is the mean of 100 queries; nine samples per case exclude
fixture setup. The additional workload retains the existing one-millisecond
maximum batch-mean ceiling in `boundary-budget.json`. It does not assert a
ratio against incorrect floating-point decisions.

The corrected five-model witness means are 14.14, 14.22, 53.16 and 52.99
microseconds (reviewed revision: 9.65, 34.87, 34.85 and 34.88). The maximum
head batch mean is 55.54 microseconds, passing every original fixed budget.
Rotated-boundary query means range from 9.38 to 12.14 microseconds, with a
maximum batch mean of 12.81 microseconds. The retained reviewed baseline
misclassifies both reported rectangles; all corrected counts match the exact
expected answers.

Measurements use the same Apple M5 Pro host, locked dependencies, one process,
no coverage and no competing test workers. Reports retain runtime, workload and
script identities. All inherited current-runtime reports are actually rerun;
their historical baselines and budgets are preserved.

Reproduce the added diagnostic with the same current script for both runtimes:

```sh
uv run python -m scripts.measure_order86_boundaries \
  --runtime-src /path/to/reviewed/src \
  --revision 79d76f8bd6c174b65f2ab17754beb39f07b6f918 --output /tmp/boundary-base.json
uv run python -m scripts.measure_order86_boundaries --runtime-src src \
  --revision r86-001-exact-half-planes --output /tmp/boundary-head.json
```

These are component diagnostics only. Full-game samples remain zero; mean and
maximum are unknown. No gameplay-slice or full-game certification is claimed.

## Inherited projection measurement recovery

The initial quality run passed 683 checks and failed the inherited flat-request
projection budget: 51.313 microseconds versus its unchanged 51.260-microsecond
limit. `projection-head-initial.json` retains that failed measurement. A single
fresh serial matched run measured 50.066 microseconds on the reviewed revision
(`projection-base.json`) and 50.586 on the corrected runtime
(`../../order83/projection-head.json`). Every nine-sample, 2,000-call row is
retained, and the corrected head passes the original limits. Historical baseline,
workload, fixtures, dependencies and budgets are unchanged. The timed request
projection path does not consume quarter geometry and its modules are unchanged;
the paired results support measurement variation without proving its cause.

The rerun selected each runtime using `scripts.measure_order65._select_runtime_src`,
printed `current_engine_build_id()` for provenance, then executed the unchanged
`scripts/benchmark_order81_projection.py` via `runpy.run_path(..., run_name="__main__")`
with its usual `--output` argument. The exact wrapper is retained in the validation
record, along with the initial nonzero quality exit and both matched run logs'
hashes. The behavioral coverage result needs no rerun because no production or
behavioral test code changed during this evidence repair.

## Final validation

All 9,382 behavioral tests passed in one coverage run, with 85.2031% branch-inclusive
coverage and a successful process exit. All 684 code-quality tests passed after
the retained projection measurement recovery. The 89 focused Order 86 tests,
Ruff, format, Mypy, Pyright, all 11 import contracts, source/runtime generation
checks, exact-base external-contract check, installed-wheel smoke, generated
TypeScript client/types, five TypeScript unit tests and 342 conformance assertions
passed. The eight-shard profile was regenerated from this complete successful
local JUnit run (Apple M5 Pro, macOS, 18 work-stealing workers with coverage).
The required shard inventory check and pre-commit hooks passed. npm is unavailable
on this host; the equivalent installed Node entry points executed the TypeScript
checks. [validation.json](validation.json) retains command results, log/JUnit
hashes, coverage totals and review status, including the initial quality failure.

Independent final review approved publication with no outstanding findings after
verifying the unchanged implementation, all aggregate results and hashes, generated
artifacts, shard inventory, and retained performance failure and matched recovery.
