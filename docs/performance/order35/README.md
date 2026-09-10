# Order 35 performance evidence

Workload `order35-rapid-ingress-v2`, provisional Apple M5 Pro / 64 GiB,
macOS 26.6.2, Python 3.14.5, identical `uv.lock`, script and fixture hashes.
One process, no competing test workers during either uninstrumented run.
Seven samples per case; setup is recorded separately. One independently
profiled sample per case records work counts. All cases completed.

| Timed slice | Base mean ms | Head mean ms | Head max / p95 ms | Mean change |
|---|---:|---:|---:|---:|
| Legal availability, selection and target submission | 10.720 | 10.699 | 11.317 | -0.2% |
| First-round query and target preflight | 0.099 | 0.029 | 0.034 | -71.0% |
| AIRCRAFT query and target preflight | 0.100 | 0.086 | 0.099 | -14.0% |
| Mixed 16-unit inventory and legal submission | 68.098 | 72.278 | 91.247 | +6.1% |
| Legal submission, placement and parent resume | 120.402 | 117.119 | 118.584 | -2.7% |

The mixed median changes from 58.13 to 60.36 ms; both seven-sample distributions
include occasional 90 ms samples. The base's invalid eligibility answers are
cost evidence only. Its first-round and AIRCRAFT answers are deliberately not
correctness oracles. Every sample, including setup time and variability, is
retained in `base.json` and `head.json`.

The numeric reference budget is mean <= 1.5 * base + 1 ms, plus the absolute
per-case maxima in `budgets.json`. The allowance avoids making sub-millisecond
noise the gate. The legal/mixed/placement ceilings leave host variability room
while the independent work gate prevents reserve enumeration from growing once
per target. No previous budgets were raised or difficult cases removed.

`tests/code_quality/test_order35_rapid_ingress_work.py` runs in the required
code-quality aggregate. It enforces <=12 reserve-list queries for both 1- and
16-unit selection/submission workloads (observed 10 each, base 12 and 27),
bounded rules-unit keyword queries (observed 7 and 59), the actual legal target
counts, and zero geometry calls for excluded requests. Placement is bounded
separately and performs one reserve-arrival resolution. The static audit prevents
reintroducing full Rapid Ingress target enumeration inside single-target binding
validation. Existing generic restriction checks and submission/application
revalidation remain necessary; no new cache is introduced.

Reproduce from the repository root:

```sh
PYTHONPATH=. uv run python scripts/measure_rapid_ingress.py --samples 7 --output docs/performance/order35/head.json
PYTHONPATH=. uv run python scripts/measure_rapid_ingress.py --samples 1 --work-counts --output docs/performance/order35/head-work.json
uv run python scripts/check_rapid_ingress_performance.py
uv run pytest tests/code_quality/test_order35_rapid_ingress_work.py -q --no-cov
```

For the base, use an isolated checkout of
`42760e107d361f30bdf19b5d9fa6c2cc67fb9c7a`, copy the three new benchmark/shared
fixture files listed in the reports, and run the same environment with
`PYTHONPATH=src:.`. The comparison gate checks all recorded fixture/script/lock
hashes and timing boundaries. The preimplementation v1 reports are retained
separately; v2 adds placement/continuation and explicit rejected target preflight
without dropping any original case.

Ten measured placement windows would be approximately 1.17 seconds at the head
mean (an estimate, not a measured game). Even the 0.5-second component ceiling
would reserve at most 5 seconds for ten such windows. Other phases, terrain,
rosters, and decision policies remain unmeasured here. This component assessment
does **not** certify the standing full-game mean <60 seconds / maximum <=300
seconds targets. A complete supported legal head-to-head driver and declared
full-game workload remain outstanding; no AI/training driver is added.
