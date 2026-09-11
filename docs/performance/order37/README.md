# Order 37 performance evidence

The cost workload uses ten real infantry models with five opponent cost-increase
sources and, in the zero-price and non-cumulative cases, one source-unit
reduction per army. Workload v2 adds five non-cumulative +1 sources with a -1
discount to exercise R37-001 without dropping the original four cases. It
starts at the canonical Overwatch target proposal and measures target submission,
all optional cost decisions, and spending or increased-cost failure. Fixture and
initial-request construction are timed separately. It does not measure attacks,
a complete phase or a complete game. No timing value enters authoritative state.

Base and head use the same lock, helper/script hashes, interpreter and provisional
host, one process, without coverage, profiling or competing test workers. The
cost base is `73faf584`, before R37-001. It is a timing comparison, not a
correctness oracle. Rapid Ingress retains its `35f492b2` base with a new head
measurement; that workload and its thresholds are unchanged. Seven samples per
case preserve every completion and price in JSON.
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

For base measurements, export `73faf584`, copy the versioned cost workload and
helper into that checkout, and use the same Python executable with that
checkout's `src` first on `PYTHONPATH`. The workload emits prices and commitments
without requiring the incorrect base to match the corrected semantic result.

| Cost case | Base mean (ms) | Head mean (ms) | Head maximum / nearest-rank P95 (ms) |
|---|---:|---:|---:|
| optional | 24.042 | 24.658 | 26.398 |
| automatic | 8.993 | 9.217 | 9.251 |
| unaffordable | 22.426 | 23.104 | 23.446 |
| zero | 26.902 | 27.568 | 28.093 |
| non_cumulative | 26.747 | 27.524 | 27.694 |

All five cost timing cases pass the unchanged comparison and maximum budgets.

Head throughput is 40.55, 108.49, 43.28, 36.27, 36.33 uses/s respectively.
With seven samples per case, nearest-rank P95 equals the observed maximum.
CPU allocation is one process and is not pinned. Work profiles match base/head
exactly: optional 4 registry / 40 provider calls, automatic 3 / 30, unaffordable
6 / 60, zero 4 / 48, and non-cumulative 4 / 48. The gate permits no more than six
registry queries per measured use and exactly one call per registered provider
in each query. All five unchanged Rapid Ingress timing budgets also pass.
