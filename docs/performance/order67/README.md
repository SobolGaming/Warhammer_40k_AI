# Order 67 roster validation assessment

This change affects pre-game roster validation, not a per-move geometry hot path.
The predicate remains constant work per distinct datasheet and reads canonical
keywords directly. No cache, search algorithm, RNG, terrain or gameplay orchestration
is added. The existing aggregation stays linear in roster size.

Base `7cc632e8` and head were measured on the same provisional Windows host,
Python 3.14.5 and uv lock, with one process and no coverage or test workers.
`base.json` and `head.json` retain CPU, memory, allocation, script/lock hashes,
all seven samples and diagnostic outcomes. Each sample times 100 complete
`validate_roster_legality` calls after catalog/request construction. The 2/4/20-unit
cases include 10/20/100 models; they deliberately retain missing-points/Warlord
reports to measure fail-closed validation as well as copy-limit reporting. The
old engine is a cost comparison, not a correctness oracle.

| Units / models | Base mean ms / roster | Head mean ms / roster | Head max batch mean ms / roster |
|---|---:|---:|---:|
| 2 / 10 | 0.1370 | 0.1357 | 0.1378 |
| 4 / 20 | 0.2127 | 0.2127 | 0.2138 |
| 20 / 100 | 0.8313 | 0.8350 | 0.8362 |

The versioned budget is 1.5 times base plus 20 ms per 100-call batch for both
mean and maximum. The additive allowance is 0.2 ms per roster, allowing host timer
variation in this sub-millisecond setup operation while catching large regressions.
The static quality gate separately forbids calls/parsing in the shared predicate.
All matched comparisons pass. No gameplay-slice or full-game performance claim
follows from these component measurements; those evidence classes remain incomplete.

Reproduce from the repository root, using an unchanged checkout of the base:

```powershell
uv run python -m scripts.measure_order67 --output docs/performance/order67/base.json --revision 7cc632e8 --runtime-src C:/path/to/base/src
uv run python -m scripts.measure_order67 --output docs/performance/order67/head.json --revision HEAD
```

Orders 64, 65 and 66 require component head evidence for the exact current runtime
identity. Their reconstruction, Firing Deck and Aircraft workloads are also rerun
serially for this build, with unchanged inputs, baselines and thresholds. Their
head reports and README results are refreshed; historical validation records
remain intact. These required evidence refreshes do not expand gameplay scope or
certify full-game performance.
