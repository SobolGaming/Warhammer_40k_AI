# Order 85 witnessed-contact diagnostic

Order 87 refreshed the active head report for runtime `904893c1`; prior tables and
revision notes below describe historical runs. Current samples and refresh details
are recorded in [Order 87 evidence](../order87/README.md). Baselines and budgets
remain unchanged.

The identical Charge facade workload is measured against
`19a5b863e8bd3b15541facb73fd4c0f78a835ce1` and the recorded head runtime.
Both runs use the same current fixture, dependency lock, Python 3.14.5 and
provisional Apple M5 Pro host with 64 GiB memory. One process runs three samples
per case without coverage or competing test/build workers; caches remain warm
between samples. Preparation and submission are timed separately. Input hashes,
all samples, median, nearest-rank p95, maximum and throughput are retained in
`base.json` and `head.json`.

| Case | Base result | Head result | Base mean | Head mean | Head maximum |
|---|---|---|---:|---:|---:|
| Stop at the physical body | Rejected | Accepted, witnessed contact | 0.0032 s | 0.0346 s | 0.0718 s |
| Penetrate the body | Accepted | Rejected | 0.0128 s | 0.0031 s | 0.0033 s |

The incorrect base is a cost comparison, not a rules oracle. These matched timing
runs were collected from an exported base after implementation; the earlier
preflight demonstrated the correctness counterexample but did not supply a
matched timing profile. `budget.json` was versioned in the working tree before
timing samples: mean at most twice base plus 0.5 seconds, maximum submission five
seconds, preparation ten seconds. The additive allowance covers the new exact
proof and cold initialization on this provisional host. These generous slice
limits do not derive or certify the 60-second full-game target.

Reproduce with the base checkout's `src`, `contracts` and `pyproject.toml` intact:

```bash
PYTHONPATH=.:src uv run python scripts/measure_order85.py \
  --runtime-src /path/to/base/src \
  --revision 19a5b863e8bd3b15541facb73fd4c0f78a835ce1 \
  --output /tmp/order85-base.json
PYTHONPATH=.:src uv run python scripts/measure_order85.py \
  --runtime-src src --revision HEAD --output /tmp/order85-head.json
```

The code-quality gate verifies runtime/input identity, matching host/workload,
correct head outcomes, sample count and unchanged budgets. `inherited-refresh.json`
records the serial refresh of existing runtime-pinned diagnostics; inherited
baselines and thresholds remain unchanged. Full-game performance certification
is outstanding and is not claimed by these component/gameplay-slice measurements.


## R85-002 rotation search

`rotation-base.json` and `rotation-head.json` measure the same counterfactual
contact query against the prior PR commit
`4f3877be7797f2124c400f47efd5fc884ef70a2a` and this reviewed runtime. A circular
rules base carries a rectangular body; the layout uses bearings of zero and
seven degrees, with a supplied ninety-degree rotation relative to each bearing.
The old search returns unresolved for both cases. The revised search returns
reachable, with each witness checked by the ordinary path and terrain validators.

Three calls per case preserve cold and cached costs. Mean head times are
0.163 seconds in both cases, with a 0.489-second maximum across them. The existing
Order 85 mean ratio/additive and maximum budgets also gate this diagnostic;
no thresholds were raised. Run `scripts/measure_order85_rotation.py` with the
same `--runtime-src`, `--revision` and `--output` arguments as the Charge diagnostic.
These measurements cover the changed search, not full-game performance.


An additional exploratory full-contact trial at the seven-degree bearing was
interrupted in the existing exact closest-endpoint solver. Its incomplete result,
fixture and log hash are retained in `incomplete-diagnostics.json`; it was not an
isolated timing measurement and establishes no budget verdict. The completed
rotation diagnostic isolates counterfactual path search. Full-contact latency for
that rotated stress layout, and full-game certification, remain unestablished
under the existing Order 32 efficiency deferral. The interruption produced an
explicit computation error, never an invented reachability answer.
