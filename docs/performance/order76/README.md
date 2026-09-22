# P03D physical proposal prevalidation evidence

`base.json` measures main `f96d235db3de236531a089fa2d95b8c20baaa418`;
`head.json` identifies the measured P03D runtime. The workload submits one valid
or invalid-kind proposal through `LocalGameSession`, three times for each of
ordinary Movement, Fight, attached Charge, attached Surge and reserve Transport
placement. Preparation is measured separately. Fixture seeds, models, terrain,
finite choices, script and dependency hashes are retained in both reports.

Both revisions run on the same provisional Apple M5 Pro macOS 26.7 host with
64 GiB of memory, 18 logical CPUs and Python 3.14.5. Measurements use one
process, with no competing test or build jobs. The first sample is cold and
later samples retain process caches. This is a component submission workload;
replay/recovery correctness is checked by the separate regression suite.

The versioned budget was declared before measuring head: every submission must
complete within 12 seconds and within three times its paired base duration plus
50 ms of scheduling tolerance. All 30 submissions must return the expected
status. Each of the 15 malformed head submissions must append zero events.
Malformed base submissions demonstrate the old event-history defect; the
unchanged Fight control already appends zero events.

| Revision / submissions | Mean seconds | Median seconds | p95 / maximum seconds | Completed |
| --- | --- | --- | --- | --- |
| Pinned main / valid | 0.014524 | 0.012867 | 0.026309 | 15/15 |
| P03D / valid | 0.014334 | 0.011211 | 0.026928 | 15/15 |
| Pinned main / malformed | 0.000935 | 0.000667 | 0.001679 | 15/15 |
| P03D / malformed | 0.000962 | 0.000688 | 0.001743 | 15/15 |

All head samples pass both declared ceilings. Malformed submissions append
12 events on base and zero on head. These measurements establish bounded
component cost and the intended event policy, not a significant speedup claim.

Reproduce with the current script and fixtures:

```sh
uv run --no-sync python scripts/measure_order76.py --runtime-src <base-checkout>/src --revision f96d235db3de236531a089fa2d95b8c20baaa418 --output docs/performance/order76/base.json
uv run --no-sync python scripts/measure_order76.py --runtime-src src --revision <verified-runtime-id> --output docs/performance/order76/head.json
```

The base checkout needs its own `pyproject.toml` and `contracts/schemas` for
runtime identity verification. Existing component guards also require current
head identities: Orders 64–66, 69–72, R73-001, 74 and 75 are remeasured on both
sides at their original base revisions, with their unchanged workloads and
budgets. Their current JSON pairs identify the qualified runtime; older README
timing tables describe historical runs.

Full games attempted/completed remain 0/0. The standing below-60-second mean
and at-most-300-second observed maximum remain uncertified. PFINAL is Order 77
and requires this prerequisite to merge before a fresh complete audit.
`preflight.json` retains the original C03-04 failures; `validation.json` records
the initial PR gates at `e47170e4`. `review-validation.json` records the current
R76-001/R76-002 corrections and their fresh correctness, package and client gates.
