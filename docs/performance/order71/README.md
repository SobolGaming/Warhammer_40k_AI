# Order 71 engaged shooting assessment

R73-001 refreshes the head evidence for runtime `2f6bea48` with unchanged
baselines, workloads and budgets. Current qualification is recorded in
[review-fix validation](../order73/r73_001/validation.json); prior results below
remain historical.

Order 73 refreshes the head evidence for runtime `bc075ee4`
with unchanged baselines, workloads and budgets. Earlier tables and validation
records remain historical. Current qualification is recorded in
[Order 73 validation](../order73/validation.json).

Order 72 refreshed the head JSON for runtime `4fef0c52` with unchanged
workloads, baselines and budgets. The tables and prior validation below are
historical; current gate results are recorded in
[Order 72 validation](../order72/validation.json).

The versioned `order71-engaged-shooting-v1` workload measures ten uncached,
complete model-target candidates per sample, including geometry, engagement,
target legality and penalty construction. Four cases cover third-party
CLOSE-QUARTERS fire, both penalty causes, the mutual-engagement exemption and an
attached target with a VEHICLE Leader. The first three scenes contain four units
and four models; the attached scene contains five units and five models. They
use the canonical shooting fixture's seed, empty terrain and deterministic
positions; no attack dice or decision policy is timed.

Seven serial samples per case ran without coverage, profiling or competing
workers on the same provisional Windows 11 host, Python 3.14.5, AMD Ryzen
Threadripper 3970X, 64 logical CPUs and 137,327,259,648 bytes RAM. Fixture/catalog
preparation is excluded. Script, helper and dependency-lock hashes, exact runtime
identities and every sample are retained in `base.json` and `head.json`.

The exact base is `ec32e01f1c8ee9d903976f2b392b40ea0700d49c`. Its incorrect
exemption and collapsed penalty are a cost comparison, not a correctness oracle.
The regression matrix against that base produced 11 expected failures and ten
passes. Correctness is established by the current facade and replay tests.

The committed component threshold is `head <= base * 2 + 0.02 seconds` for both
the mean and maximum of each ten-candidate sample. The 2 ms additive per-query
allowance tolerates host scheduling variation while bounding this changed
component. It does not predict queries per game or certify the 60-second game
objective. The required code-quality suite verifies matched inputs, seven
completed samples, current runtime identity and all eight comparisons.

| Case | Base mean (s) | Head mean (s) | Base max (s) | Head max (s) |
| --- | ---: | ---: | ---: | ---: |
| Third-party CLOSE-QUARTERS | 0.007939 | 0.007296 | 0.009198 | 0.008228 |
| Both causes | 0.007228 | 0.008015 | 0.007798 | 0.009957 |
| Mutual CLOSE-QUARTERS | 0.007308 | 0.007350 | 0.008137 | 0.008362 |
| Attached third-party | 0.008310 | 0.008428 | 0.008959 | 0.009256 |

All 560 base/head candidate calculations completed. All eight mean/maximum
comparisons pass; current mean cost is 0.73–0.84 ms per candidate. Nearest-rank
p95 equals the maximum for seven samples. Head medians and throughput are
recorded in `summary.json`, derived directly from the retained samples.

Reproduce serially with the corresponding source trees and no competing workers:

```powershell
uv run python -m scripts.measure_order71 --output docs/performance/order71/base.json --revision ec32e01f --runtime-src reports/order71-base/src
uv run python -m scripts.measure_order71 --output docs/performance/order71/head.json --revision order71-review-final
```

The archived base must include `src`, `contracts/schemas` and `pyproject.toml` so
authenticated reconstruction can verify its schema root. Runtime identity is
checked before interpreting a saved result.

The inherited Orders 64, 65, 66, 69 and 70 guards also require the exact current
runtime. Their head reports were refreshed serially after the P2 correction with
unchanged scripts, fixtures, baselines and budgets. The Order 65 facade declaration exercises the
changed model-exclusivity validator, including borrowed-weapon source ownership.
Final gate outcomes and the historical first published validation are in
`validation.json`.

Complete gameplay-slice and head-to-head performance remain unmeasured. The
60-second mean / 300-second maximum complete-game targets and deferred Order 32
budgets remain uncertified.
