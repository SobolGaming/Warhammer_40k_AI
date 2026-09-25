# Order 85 witnessed-contact diagnostic

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
| Stop at the physical body | Rejected | Accepted, witnessed contact | 0.0033 s | 0.0338 s | 0.0706 s |
| Penetrate the body | Accepted | Rejected | 0.0120 s | 0.0030 s | 0.0031 s |

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
