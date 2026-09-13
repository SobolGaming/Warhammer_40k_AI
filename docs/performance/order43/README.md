# Order 43 shared hit threshold performance

The unchanged Order 33 driver measures ordinary visible fire, unseen fire without
an observer, and unseen fire with a friendly observer. Each scene uses five
models per participating unit, the committed fixed terrain/seed/decision policy,
and seven fresh samples. Setup timing is recorded separately from declaration
through completed attack. All samples are retained. The baseline was captured
before implementation on commit `15856aca9550bf9296ebfbf74e165e889301e705`.

Reproduce with `uv run python -m scripts.measure_indirect_shooting --samples 7
--output docs/performance/order43/head.json`. Use the same dependency lock and
provisional macOS host, one process, without coverage, profiling or competing
test workers. Reports retain workload/script/fixture/lock hashes, interpreter,
OS, runtime identity, setup/query timings, completion, hit/decision counts,
mean, median, p95, maximum and throughput.

The budgets were fixed from the retained baseline before measuring head: mean
at most twice base plus 50 ms, and a one-second observed maximum per small slice.
The relative allowance accommodates local scheduling variability. At an assumed
20 such attack slices per game, the additive allowance totals one second; that
is an estimate against the 60-second full-game objective, not a measured game.
The stable work gate requires a single shared effect-matching pass per hit and
preserves the existing Order 33 geometry work budgets. No thresholds or hard
cases are removed after measuring.

Component and gameplay-slice evidence do not certify full head-to-head games,
universal worst-case performance, or the deferred Order 32 budgets. Full-game
60-second mean / 300-second observed maximum targets remain outstanding.

The final contract 16 head passes the fixed budgets. Mean times are 115.2 ms
visible, 383.0 ms unseen without an observer, and 310.7 ms unseen with an observer,
compared with 109.9, 369.8 and 303.1 ms on base. The greatest observed head
sample is 437.1 ms. Every case retains identical decision and hit counts.
The measured runtime identity is
`b1a8d5d1e8216f4842d66af0de630b512c6c437f757454566ab7769523624ffc`.
The earlier gameplay measurement remains in `pre-contract-head.json`.

## R43-001 checkpoint authority

`restore-base.json` and `restore-head.json` measure the identical
`r43-hit-authority-fnp-v1` workload on commit `76da5f2d` and the corrected runtime
`f85d25f40e110567bbc17150cd3971be423cb2de0784eda7ccc8c9fcc009728d`.
The base checkout received only the same benchmark driver and fixture. Both
reports retain identical script, fixture and lock hashes. Seven uninstrumented
samples per phase run in one process without competing workers on the provisional
Apple M5 Pro, 18 logical CPUs, 64 GiB RAM, macOS 26.6.2, Python 3.14.5 host.

Reproduce with `uv run python -m scripts.measure_hit_checkpoint_restore --samples 7
--output docs/performance/order43/restore-head.json`. Canonical compact rosters,
terrain, twelve-attack profiles, fixed Shooting/Fight seeds and finite decision
policy live in `tests/critical_hit_helpers.py::hit_authority_checkpoint`.
Fixture construction and initial checkpoint capture are outside the measured
restore interval. The second interval submits a Feel No Pain decline through
the facade and stops at the next decision. All samples and setup times are retained.

The fixed `restore-budgets.json` limits pass. Mean Shooting restore is 1.293 s
versus 1.290 s on base; Fight is 1.301 s versus 1.308 s. Mean continuation is
60.3 ms versus 65.0 ms for Shooting and 59.1 ms versus 58.2 ms for Fight.
Every sample completes with identical decision/event counts. The largest restore
is 1.327 s and largest continuation is 61.7 ms. These checkpoint/component
measurements do not certify complete-game performance.
Earlier head measurements remain in `restore-before-post-roll-fix.json` and
`restore-before-gathered-fix.json`. Those revisions compared against later or
ungathered profile identities; the final implementation authenticates the
recorded hit's weapon/dice specification across both legitimate transformations.
