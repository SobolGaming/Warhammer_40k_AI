# Order 96 optional wound reroll evidence

Base `52e001dd` and the implementation use the same script, fixtures, dependency
lock, seeds and host: provisional Apple M5 Pro, 64 GiB, macOS 26.7, Python 3.14.5.
Each row contains five serial samples without coverage or competing test/build
workers. Setup and checkpoint restoration are measured separately. The workload
contains two one-model units, no terrain and twelve Torrent/Twin-linked attacks
with absent Strength against Toughness 1. It uses the existing canonical Shooting
and Fight sessions and submits choices through `LocalGameSession`.

| Phase / policy | Base mean (s) | Head mean (s) | Head maximum (s) | Head restore mean (s) |
|---|---:|---:|---:|---:|
| Shooting / decline | 0.2695 | 0.4728 | 0.4851 | 0.3116 |
| Shooting / accept | 0.2595 | 0.4724 | 0.4979 | 0.3208 |
| Fight / decline | 0.1608 | 0.3435 | 0.3454 | 0.2984 |
| Fight / accept | 0.1471 | 0.3584 | 0.3601 | 0.3002 |

The base is a cost comparison, not a correctness oracle: it ignores the selected
policy and automatically rerolls eight failures without presenting any choice.
Every head sample completes twelve wounds and twelve submitted optional choices,
with zero or twelve physical rerolls according to policy and no automatic weapon
reroll events. The extra decisions, source validation, event records and repeated
resumption increase the measured slice cost. All twenty head slices completed;
their mean times remain below 0.48 seconds. No full-game samples were collected.

A second matched workload uses twelve Twin-linked/Sustained Hits D3 attacks. It
measures the event-backed D3 reuse required when wound choices resume the same
hit calculation. Each row again contains five serial samples.

| Phase / policy | Base mean (s) | Head mean (s) | Head maximum (s) | Head restore mean (s) |
|---|---:|---:|---:|---:|
| Shooting / decline | 0.3137 | 0.7399 | 0.7791 | 0.3316 |
| Shooting / accept | 0.3007 | 0.5481 | 0.5766 | 0.3253 |
| Fight / decline | 0.1778 | 0.4617 | 0.4668 | 0.2949 |
| Fight / accept | 0.1872 | 0.9894 | 1.0049 | 0.3114 |

All twenty additional head slices finish with twelve unique hit contexts, exactly
one D3 per critical hit, one submitted choice per wound, and the selected number
of physical rerolls. Counts range from ten to twenty-two wounds because chosen
rerolls change subsequent deterministic dice consumption. The baseline has no
optional pauses and ignores the player's selected policy; its outcomes are not
an oracle for the corrected engine.

The required stable-work gate lives in
`tests/code_quality/test_order96_reroll_authority.py`. It binds reports to the
current runtime and exact script/fixture hashes, requires matched environments
and all four policies. The Torrent workload enforces twelve wounds and submitted
choices; both workloads enforce exactly the requested rerolls and no synthetic
weapon decisions. The D3 workload also enforces unique hit contexts and one D3
per critical hit. The behavioral
tests separately require once-per-die authorization, unchanged pending state for
invalid submissions, checkpoint equality and exact replay. Existing numeric
budgets and historical baselines are unchanged; owner-deferred provisional
component timing gates and the standing full-game targets are not claimed passed.

Reproduce with a read-only archive of the base source and the current workload:

```sh
PYTHONPATH=/path/to/base/src:. .venv/bin/python scripts/benchmark_order96_rerolls.py --output /tmp/base.json
PYTHONPATH=src:. .venv/bin/python scripts/benchmark_order96_rerolls.py --output /tmp/head.json
PYTHONPATH=/path/to/base/src:. .venv/bin/python scripts/benchmark_order96_rerolls.py --sustained --output /tmp/base-sustained.json
PYTHONPATH=src:. .venv/bin/python scripts/benchmark_order96_rerolls.py --sustained --output /tmp/head-sustained.json
```

`base.json`, `head.json` and their `-sustained` counterparts retain all samples, preparation/restoration timings,
work counts, runtime IDs, environment and script/fixture hashes. Runtime-bound
inherited head reports are remeasured serially using the exact commands in
`inherited-refresh.json`; historical baseline samples, fixture migration proofs
and budgets remain intact. The inherited Order 88 driver now reaches the first
legal optional choice (decline) while retaining its twelve-wound workload; the
new paired workload above records that decision-cost change explicitly.

The pre-gate scope audit and source trace are in
[ORDER_96_SCOPE_PLAN.md](../../ORDER_96_SCOPE_PLAN.md). Final check commands,
results, timings and log hashes are recorded in `validation.json`.

The first aggregate behavioral run passed all 9,842 tests at 85.21% coverage.
Its subsequent quality run found three failures because the immutable Order 95
audit still required the removed automatic helper. The audit checker now records
that explicit retirement and requires both successor owners, while preserving
the original negative report and pinned observations. It also rejects a
reintroduced automatic owner. All 22 focused audit tests and both type checkers
passed after this repair. Independent review then identified repeated Sustained
Hits D3 rolls on wound resumption and stale Fight reaction frames. Repair also
closed correlated request reclassification against physical wound evidence.
All 57 focused Order 96 tests pass, including an independent rerun, and the
reviewer approved the code without remaining findings. The next aggregate run
reached 85.21% coverage with 9,855 passing tests and two failing Drukhari fixtures
that pre-recorded future wound events before pending hit choices. Independent
review confirmed that runtime ordering was correct. The fixtures now use normal
engine wound rolls with all original assertions retained; their full 33-test
module passes. The final complete behavioral rerun passes all 9,857 tests at
85.21% coverage. Ten SQLite resource warnings remain diagnostic output. Earlier
failed/intermediate results remain recorded separately from the final gate.
All 770 code-quality tests pass without coverage, the eight-shard inventory check
passes, and all eleven import-boundary contracts are kept. Contract compatibility,
installed-wheel smoke, generated TypeScript models, six TypeScript unit tests and
342 HTTP conformance assertions also pass on the final runtime identity.

The independent reviewer approved PR publication after verifying final runtime,
validation-log and performance-report hashes, with no remaining findings.
