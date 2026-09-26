# Order 88 performance and validation

The matched workload resolves twelve numeric-S1 Torrent/Twin-linked attacks
against T1 through the real Shooting and Fight facades. Each scene contains two
one-model units and no terrain. The same game IDs, legal decision policy,
interpreter, dependency lock and fixture bytes run on base `1fe279fe` (runtime
`d687c193`) and head runtime `9cc51543`, serially without coverage or competing
test workers. Hardware is the provisional Apple M5 Pro, 64 GiB host; exact OS,
Python, CPU and input hashes are in [base](base.json) and [head](head.json).

| Attack slice mean seconds | Base | Head |
|---|---:|---:|
| Shooting | 0.264300 | 0.264324 |
| Fight | 0.152317 | 0.151311 |

Five samples per phase retain setup separately, median, maximum/nearest-rank
p95, throughput and all wound counts. Shooting changed by about +0.01%, Fight
by -0.66%; this small diagnostic establishes no calibrated performance budget.
Each sample resolves twelve wound interactions. The behavioral work gate also
requires one wound die per attack without extra profile rolls for fixed or dash
Strength. Different profile descriptors retain their different deterministic
identities, so numeric/dash scenes are not required to have identical dice faces.

The base extraction contains the exact committed `src`, `contracts` and
`pyproject.toml`, and runs the same current benchmark fixture. Reproduce with:

```sh
PYTHONPATH=/path/to/base/src:. .venv/bin/python scripts/benchmark_order88_strength.py --output /tmp/base.json
PYTHONPATH=src:. .venv/bin/python scripts/benchmark_order88_strength.py --output /tmp/head.json
```

An initial attempt could not read hardware metadata under the sandbox and wrote
no report. A preliminary fixture used the wrong generic-condition key; its
baseline was superseded by this matched pair after correcting the fixture.
No failed timing sample is included as passing evidence. The performance policy's
deferred component timing budgets are not claimed to pass. Completed full-game
samples remain zero; mean and maximum full-game timing remain unknown.

The inherited runtime-pinned head reports are refreshed serially under unchanged
workloads, historical baselines and budgets. Their commands, exit codes and
report/log hashes are recorded in [the refresh record](inherited-refresh.json).
The unchanged Order 87 fixture-migration proofs still apply to those historical
baselines. The required quality gates enforce their existing assertions.

The first aggregate coverage attempt reached 85.16% with 9,431 passes and one
failure: the existing source-artifact test still expected six rows instead of
seven. Only that count assertion changed. The corrected source/artifact checks
passed 42 tests; the independent reviewer passed 18 focused checks and verified
all performance report hashes. This initial attempt is not passing aggregate
evidence; its original log and JUnit report are retained under
`reports/order88/behavior-attempt1.*`.

The clean final aggregate passed 9,432 behavioral tests with 85.16% coverage
in 702.16 seconds, followed by all 688 code-quality tests without coverage in
106.63 seconds. Both used 18 xdist work-stealing workers. The eight-shard
inventory was regenerated from that successful JUnit profile and passed its
fail-closed check. Ruff, formatting, mypy, pyright, all eleven import contracts,
source/build/contract generation checks, the exact-base contract check, installed
wheel smoke and pre-commit passed. Machine-readable counts, report hashes and
gate outcomes are recorded in [validation.json](validation.json). The independent
reviewer explicitly approved the completed staged diff before the first push,
with no actionable findings. In addition to eighteen focused tests, the reviewer
independently checked the shard inventory, source generation, exact-base contract
and retained aggregate evidence hashes.

The bundled runtime provides Node.js but no `npm` executable. The attempted
`npm test` command therefore exited before running tests. The exact package
script entry points were subsequently executed directly with Node: generated
model checking, `tsc --noEmit`, the five `tsx --test` tests, and the live
conformance entry point. All passed, including 342 HTTP assertions on Contract
40.0.0. Logs retain both the unavailable-command result and the successful
direct invocation; `npm test` itself is not reported as passed.
