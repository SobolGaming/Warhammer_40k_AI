# Order 37 performance evidence

The cost workload uses ten real infantry models with five opponent cost-increase
sources and, in the zero-price case, one source-unit reduction per army. It
starts at the canonical Overwatch target proposal and measures target submission,
all optional cost decisions, and spending or increased-cost failure. Fixture and
initial-request construction are timed separately. It does not measure attacks,
a complete phase or a complete game. No timing value enters authoritative state.

Base and head use the same lock, helper/script hashes, interpreter and provisional
host, one process, without coverage, profiling or competing test workers. The
base is `35f492b2`; its uncapped prices are a cost comparison, not a correctness
oracle. Seven samples per case preserve every completion and price in JSON.
Separate profiles count registry and source-provider calls. CI enforces bounded
registry calls and exactly one provider call per registered binding per query.

`budgets.json` permits 1.5× base mean plus 1 ms and a 100 ms observed per-use
maximum. The 1 ms allowance covers fixed host noise in these short component
samples. At 50 uses, the component maximum would contribute 5 seconds; that is
an estimate, not a full-game result or bound. Existing Order 35 Rapid Ingress
budgets remain unchanged and are checked separately. Full-game 60-second mean /
300-second observed maximum certification remains outstanding.

Reproduce with:

```sh
PYTHONPATH=. uv run python scripts/measure_stratagem_cost.py --samples 7 --output docs/performance/order37/head-cost.json
PYTHONPATH=. uv run python scripts/measure_stratagem_cost.py --samples 1 --work-counts --output docs/performance/order37/head-cost-work.json
uv run python scripts/check_stratagem_cost_performance.py
PYTHONPATH=. uv run python scripts/measure_rapid_ingress.py --samples 7 --output docs/performance/order37/head.json
```

For base measurements, export `35f492b2`, copy the versioned cost workload and
helper into that checkout, and use the same Python executable with that
checkout's `src` first on `PYTHONPATH`. The workload emits prices and commitments
without requiring the incorrect base to match the corrected semantic result.

| Cost case | Base mean (ms) | Head mean (ms) | Head maximum / nearest-rank P95 (ms) |
|---|---:|---:|---:|
| optional | 23.934 | 24.213 | 25.813 |
| automatic | 8.928 | 9.058 | 9.104 |
| unaffordable | 22.544 | 23.089 | 24.232 |
| zero | 26.796 | 26.962 | 27.463 |

All four cost timing cases pass the versioned comparison and maximum budgets.

Head throughput is 41.30, 110.40, 43.31, 37.09 uses/s respectively.
With seven samples per case, nearest-rank P95 equals the observed maximum.
CPU allocation is one process and is not pinned. Work profiles match base/head
exactly: optional 4 registry / 40 provider calls, automatic 3 / 30, unaffordable
6 / 60, and zero 4 / 48. The gate permits no more than six registry queries
per measured use and exactly one call per registered provider in each query.
All five unchanged Rapid Ingress timing budgets also pass.
