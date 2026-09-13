# Order 44 shared Lethal Hits choice performance

The matched baseline is main `0a54e432aa9517e79ef60ea129a14c747aef7ff1`.
All measurements use the provisional Apple M5 Pro host (18 logical CPUs,
64 GiB RAM, macOS 26.6.2, Python 3.14.5), the same dependency lock, one process,
and no coverage, profiling or competing test workers. Every case retains seven
fresh samples; setup time is separate from the attack slice.

`base.json` and `head.json` retain the unchanged Order 33 five-model visible,
unseen without observer, and unseen with observer workloads. Reproduce using
`uv run python -m scripts.measure_indirect_shooting --samples 7 --output docs/performance/order44/head.json`.

`lethal-base.json` and `lethal-head.json` use compact canonical Shooting and Fight
rosters, eighteen attacks, Strength 1, Lethal Hits and Sustained Hits 1. The fixed
seed, roster, terrain and finite decision policy live in
`tests/lethal_hits_helpers.py`. Each emitted choice selects `auto-wound` through
the facade. Base does not emit this choice; head must emit it for original
critical hits. Reproduce using `uv run python -m scripts.measure_lethal_hits --samples 7 --output docs/performance/order44/lethal-head.json`. The base worktree
received the identical driver and shared test helpers, with no runtime changes.
Reports retain fixture/driver/lock hashes, runtime-manifest and source-diff hashes,
interpreter, platform, setup and slice timings, decision/hit/choice counts,
completion, mean, median, p95 and maximum. No samples are dropped.

The committed budgets were fixed before measuring head: ordinary mean at most
2 times base plus 100 ms, with a one-second observed maximum; Lethal Hits mean
at most 3 times base plus 150 ms, with a two-second observed maximum. The extra
finite decisions intentionally add work. At an assumed twenty such attack slices
per game, the larger additive allowance totals three seconds against the
60-second mean objective. This estimate is not a complete-game measurement.

These component/gameplay-slice measurements do not certify full head-to-head
games or a universal worst-case bound. The full-game 60-second arithmetic mean
and 300-second observed maximum targets and deferred Order 32 budgets remain
uncertified. No threshold was raised after observing head.

## Results

| Workload | Base mean (ms) | Head mean (ms) | Head maximum (ms) |
| --- | ---: | ---: | ---: |
| visible-self-observer | 122.4 | 121.2 | 156.4 |
| unseen-no-observer | 400.6 | 398.3 | 451.4 |
| unseen-friendly-observer | 323.3 | 321.8 | 346.0 |
| lethal-shooting | 153.2 | 126.7 | 135.4 |
| lethal-fight | 114.5 | 125.9 | 129.3 |

Every sample completed. The retained head measurements pass the fixed budgets.
Lethal Hits adds 3 choices in shooting, 1 choices in fight per slice. Ordinary workload hit and decision counts are unchanged.
The measured runtime tree SHA-256 is `29f3f0ce86f4b093d94c0d90b161414bd0329bbcd0a2f85d4a50e946853d1652`.
