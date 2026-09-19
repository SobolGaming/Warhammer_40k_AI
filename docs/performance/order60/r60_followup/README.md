# R60-001 floor and R60-003 elevation follow-up

The invariant is that omitted-casualty, closest, and unengaged verdicts must not
use a planar result that omits relevant floor collision or supported elevations.
The shared proof now raises unresolved for floors reaching its horizontal
search region, before filtering by the passenger's synthetic/current elevation.
It does not implement support-aware placement search. Both complete elevated
placements and partial placements near floors remain unresolved.

The matched existing v1 workload retains all seven samples, identical inputs,
the dependency lock, and unchanged budgets. Base `51c64970` and runtime
`da58b26c34f363cd525cd1ab4afca9b1723db7471e509431788698d2f11e1724` were measured
on the same provisional Windows 11 / Threadripper 3970X / Python 3.14.5 host,
one process without coverage, profiling, or competing test workers. Preparation
is excluded and the first sample is cold. The mean was **19.61 ms base /
19.76 ms head**, maximum **95.90 ms / 96.87 ms**; all samples completed validly.
These component measurements pass the existing budgets. They are not a timing
certification of unresolved floor cases or complete games. Gameplay-slice and
full-game measurements remain outstanding.

Reproduce using the parent directory's `scripts/measure_order60.py` commands,
substituting this directory's output paths and the indicated base revision.
The benchmark script and shared fixture are unchanged. Regression tests in
`tests/unit/test_order60_emergency_disembark.py` verify the rejected floor cases
against the real terrain endpoint validator and check unchanged lifecycle state.
The existing wall, elevated-enemy, and ground-contact tests continue to pass.

Final validation on 2026-09-19, with no later production-code changes:

- Full behavioral suite once with coverage, xdist auto/work stealing:
  **8,382 passed**, **85.11%** coverage against 85%, **970.29 seconds**.
  Ten SQLite unclosed-database `ResourceWarning` messages were emitted.
- Full code-quality suite once without coverage, xdist auto/work stealing:
  **524 passed**, **332.06 seconds**.
- Focused Order 60 behavioral tests: **15 passed**; transport regressions:
  **195 passed**; focused Order 60 source/architecture/performance checks:
  **4 passed**. Before the fix, the slab case and both omission entry-point
  regressions failed by returning a verdict instead of raising unresolved.
- Ruff check/format, mypy (3,118 files), Pyright, all 11 import contracts,
  eight-shard inventory, and pre-commit passed.
- Source generator, runtime identity, and regenerated external contract passed,
  including compatibility against `51c64970`. Installed-wheel smoke verified
  2,872 runtime resources, 27 schemas, and all six request families.
- Generated TypeScript client/type checks, five client unit tests, and all
  **342 HTTP conformance assertions** passed on contract **26.0.0**.

Node.js 24.19.0 was on PATH for the coverage suite. The desktop runtime has no
`npm` command, so client checks used the package scripts' exact Node entry
points: `scripts/check-generated.mjs`, `node_modules/typescript/bin/tsc --noEmit`,
and `node_modules/tsx/dist/cli.mjs` for unit tests and conformance. The generated
client initially differed only by CRLF/LF; normalization restored exact generated
bytes without changing tracked content. These are local checks; no new remote CI
run or publication is claimed. Machine-readable totals are in `validation.json`.
