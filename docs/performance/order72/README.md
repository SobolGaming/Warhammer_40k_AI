# Order 72 consolidation response assessment

Order 87 refreshed the active head report for runtime `904893c1`; prior tables and
revision notes below describe historical runs. Current samples and refresh details
are recorded in [Order 87 evidence](../order87/README.md). Baselines and budgets
remain unchanged.

R73-001 refreshes the head evidence for runtime `2f6bea48` with unchanged
baselines, workloads and budgets. Current qualification is recorded in
[review-fix validation](../order73/r73_001/validation.json); prior results below
remain historical.

Order 73 refreshes the head evidence for runtime `bc075ee4`
with unchanged baselines, workloads and budgets. Earlier tables and validation
records remain historical. Current qualification is recorded in
[Order 73 validation](../order73/validation.json).

The matched workload runs the existing full-Fight Engaging regression in a fresh
serial pytest process, without coverage or profiling. Two single-model Character
units use an empty battlefield and the fixed `p12-full-fight-continuation` game
seed. The fixed decision script covers ordinary Fight completion, witnessed
Engaging movement, the opponent's Overrun response, authenticated checkpoints,
rejected forged history, suspension/resumption and exact replay. Setup, test
assertions and process startup are included in the timer; this is a regression
workload cost, not an isolated engine-kernel or whole-game benchmark.

The selected test function is unchanged between base and head. The script and
dependency-lock hashes, host, runtime identity, timing boundary, scenario ID and
three successful elapsed samples are retained in `base.json` and `head.json`.
The provisional host is Windows 11, Python 3.14.5, an AMD Threadripper 3970X with
64 logical CPUs and 137,327,259,648 bytes of memory. Measurements use one process
at a time, without competing test/build workers. Median, arithmetic mean and
observed maximum are retained; the nearest-rank p95 is the maximum for three
samples. Fixture setup and assertions are deliberately the same on both builds.

`budgets.json` was declared before the first baseline and production edits.
Mean and maximum must each remain at or below base × 2 + 0.1 seconds. This broad
small-sample regression bound accommodates the work of a new inverse response
inventory and host/process variability; it is not derived from measured calls
per game. CI validates the unchanged workload identity, current runtime ID,
completion counts and budget. Static guards also require live and historical
consumers to use the same source query and prohibit the retired Ongoing source
ID in engine code.

Reproduce in the repository root, with the same Python environment:

```powershell
uv run python -m scripts.measure_order72 --runtime-src <base-checkout>/src --revision 5befbb928fb938c4faa2bef8cd52ffc677e6294f --output docs/performance/order72/base.json
uv run python -m scripts.measure_order72 --revision <head-runtime-identity> --output docs/performance/order72/head.json
```

The base source snapshot must include its `pyproject.toml` and canonical
`contracts/schemas` so the ordinary runtime identity check remains enabled.
The initial measurement preceded production edits. The qualified comparison
remeasures the archived base using the final runner, including its explicit
runtime selection and formatting corrections. No baseline or head sample
substitutes a timeout or unresolved calculation with a rules answer.

Orders 64, 65, 66, 69, 70 and 71 require head evidence to match every current
runtime identity. Their existing head reports are refreshed serially under their
unchanged scripts, workloads, baselines and budgets. Their original validation
records remain historical; this task's gate outcomes belong in `validation.json`.

Complete gameplay-slice throughput, complete head-to-head games, the 60-second
mean/300-second observed-maximum goals and deferred Order 32 budgets remain
unmeasured or uncertified. The component reports do not establish those claims.

## Results

| Metric | Base (seconds) | Head (seconds) | Limit (seconds) |
| --- | ---: | ---: | ---: |
| Arithmetic mean | 18.878578 | 17.896200 | 37.857156 |
| Observed maximum | 19.092074 | 18.192830 | 38.284148 |

All three samples per build completed. Base/head medians are 19.004308 / 17.804429 seconds.
Both declared comparisons pass. Final test counts, coverage, contract/client
checks and the npm installation limitation are retained in `validation.json`.
