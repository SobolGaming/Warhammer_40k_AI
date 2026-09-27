# Order 89 performance and validation

The matched `order89-healing-v1` workload measures shared resolution to completion
or a pending placement request, with setup separate. Ordinary and attached units
have five infantry (plus an attached Character where applicable), five enemies,
no terrain, and either one recorded wound or one recorded destroyed infantry
model. Five samples per case run serially without coverage or competing test
workers on the provisional Apple M5 Pro / 64 GiB host. Both revisions run the
same current fixture, workload, environment and dependency lock. Base is
`84a1de10`; its numeric costs are a comparison, not a correctness oracle.

Reproduce with the exact committed baseline runtime extracted into a directory:

```sh
PYTHONPATH=/path/to/base/src:. .venv/bin/python scripts/benchmark_order89_healing.py --output /tmp/base.json
PYTHONPATH=src:. .venv/bin/python scripts/benchmark_order89_healing.py --output /tmp/head.json
```

`base.json` and `head.json` retain individual setup/query samples, mean, median,
maximum/nearest-rank p95, resolved-step counts, runtime identity and input hashes.
The functional work checks require exactly one resolved step per applied healing
point and no revival/other-model mutation from excess model healing. These are
correctness/work assertions, not calibrated timing budgets. The owner-deferred
component budgets are not claimed passed. Complete-game samples remain zero;
mean and maximum complete-game time are unknown.

Matched query means (milliseconds):

| Case | Base | Head |
|---|---:|---:|
| Ordinary wounded-model heal | 0.445 | 0.425 |
| Ordinary revival request | 0.505 | 0.486 |
| Attached wounded-model heal | 0.429 | 0.414 |
| Attached revival request | 0.514 | 0.504 |

All input hashes match and resolved-step counts are unchanged. These small samples
show no regression in the measured query workload; they do not measure complete
games or establish a worst-case bound.

Inherited runtime-pinned performance reports retain their historical baselines,
workloads and numeric budgets; only matching head evidence is refreshed. Exact
commands and report hashes are in `inherited-refresh.json`.

Final validation passed 9,457 behavioral tests with 85.16% coverage in 1,234.09
seconds, followed by all 691 code-quality tests without coverage in 114.74 seconds.
Both used 18 xdist work-stealing workers. The eight-shard inventory was regenerated
from the successful full JUnit profile and passed its fail-closed check. Ruff,
formatting, mypy, pyright, all eleven import contracts, source/build/contract
checks, the exact-base contract check, installed wheel smoke and pre-commit passed.
Machine-readable counts, hashes and gate outcomes are in
[validation.json](validation.json).

The first code-quality run passed 690 tests and found a stale Order 88 head report.
The inherited refresh list was extended to include that workload, producing 25
current reports. The historical baseline, fixture hashes and budgets stayed
unchanged. This evidence-only correction required no runtime/test change; the
passing behavioral coverage result remains valid. The initial quality log and
JUnit remain under `reports/order89/code-quality-attempt1.*`.

The independent reviewer initially identified two P2 gaps: short-circuiting could
skip malformed scope-flag validation, and the changed Aura producer needed a direct
model-lock regression. Both were fixed and independently rechecked. The reviewer
approved with no unresolved findings after 227 initial focused passes and 11
fix-specific passes. A final staged review independently verified aggregate counts,
coverage and report hashes, unchanged performance inputs/budgets, source generation,
and the eight-shard inventory, and approved with no findings before the first push.

The bundled runtime has Node.js but no npm executable. The package script entry
points were run directly: generated model checks, TypeScript type checking, all
five client unit tests, and the live HTTP scenario with 342 assertions on Contract
40.0.0. The installed wheel validated 27 schemas and 2,987 runtime resources.
