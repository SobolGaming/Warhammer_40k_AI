# Order 78 — Gone to Ground

The workload `order78-gone-to-ground-v1` measures both shared query consumers on
real canonical models and terrain. Each of seven serial samples runs ten pairs
of model-target candidate and shared LOS queries. Fixture preparation is excluded;
normal immutable geometry caches are enabled and no cached-candidate wrapper is
used. These are component measurements, not complete attacks or complete games.

Base is `f14e288cf9be9830161aa4c71e5d24d64903197e`; head runtime identity is recorded
in `head.json`. Both use the same script, helper, lockfile, Python 3.14.5 and
provisional Apple M5 Pro host (18 logical CPUs, 64 GiB). The attached-unit fixture
uses the canonical rules-unit effect identity in both revisions. The base runtime
was extracted with its own contract schemas and runtime manifest. Measurements
run serially without coverage or competing test/build workers.

| Case | Base mean / max (ms) | Head mean / max (ms) | Head target legal |
| --- | ---: | ---: | --- |
| Dense outside | 18.87 / 31.55 | 30.32 / 44.03 | No |
| Dense inside | 30.02 / 49.28 | 30.58 / 47.22 | No |
| Attached outside | 31.92 / 44.12 | 55.42 / 70.83 | No |
| Light outside | 17.33 / 18.17 | 17.80 / 18.88 | Yes |
| Not Hidden | 16.80 / 17.06 | 16.79 / 17.13 | Yes |
| Fully visible | 6.18 / 7.00 | 6.61 / 6.98 | Yes |

Outside-dense cases now perform the required causal visibility query and reject
the previously accepted target. Their cost increase reflects corrected work;
these comparisons do not claim equivalent rules results. Both consumers agree.
All samples complete and fit the pre-head diagnostic envelope in `budgets.json`
(2× base + 40 ms for each mean/maximum). No threshold was raised or case dropped.
Order 32's provisional component performance-gate deferral remains in force;
this observation does not certify deferred budgets or universal worst-case time.

Run each revision in a fresh process:

```sh
PYTHONPATH=. uv run --no-sync python scripts/measure_order78.py \
  --runtime-src <checkout>/src --revision <revision> \
  --output docs/performance/order78/<base-or-head>.json
```

The runtime identity change also requires fresh inherited head measurements for
Orders 64–66 and 69–77 (fourteen reports including both Order 73 and both
Order 77 workloads). Their
original base revisions, workload definitions, input hashes and numeric budgets
are retained. Base/head environment and workload equality are checked by the
existing quality gates. `validation.json` records the refresh and final gates.

During focused boundary-test development, moving the target into the intervening
wall made the exact solver run until explicitly interrupted; the engine raised
`VisibilityComputationError` and produced no invented rules answer. The final
range tests move the observer, retaining the non-overlapping target/wall scene.
That diagnostic is not a passed timing sample or a reason to change solver policy.

Complete games attempted/completed: **0/0**. No representative legal complete-game
driver or recording is available. Full-game mean <60 seconds / observed maximum
≤300 seconds and the final Core Rules audit remain uncertified. See the immutable
`preflight.json` and the approved implementation in `docs/ORDER_78_PREFLIGHT_AUDIT.md`.
