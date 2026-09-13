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
