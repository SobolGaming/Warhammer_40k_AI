# P21C fixed-target Surge evidence

Order 87 refreshed the active head report for runtime `904893c1`; prior tables and
revision notes below describe historical runs. Current samples and refresh details
are recorded in [Order 87 evidence](../order87/README.md). Baselines and budgets
remain unchanged.

The workload measures a cold-cache `LocalGameSession` submission after finite
target selection. Three repetitions each cover a five-model rectangular-target
approach, a six-model attached-unit approach to a rectangle facing 37 degrees,
and a five-model approach to an oval facing 90 degrees. Targets measure 8 by 2
inches. Every moving model supplies three path poses and a three-inch budget on
an empty battlefield. Fixture preparation is reported separately. No dice are
rolled in this slice.

`base.json` measures main `9d8c5e2a1bb4db3c8a7f68b6da924c4ea9e23daa`;
`head.json` binds the measured runtime identity. Identical fixture/script/lock
hashes and a single Apple M5 Pro process with no competing test or build jobs
make the boundary comparable. This provisional macOS 26.7 host has 64 GiB of
memory, 18 logical CPUs and Python 3.14.5. The accepted head performs different
work from the rejected base, so the timings do not establish a speedup over an
equivalent completed base workload.

The declared gate is acceptance of all nine head submissions, each within 12
seconds. This adopts the existing Order 74 small-facade ceiling before measuring
the base; no threshold or hard case is relaxed. Individual samples, arithmetic
mean, median, nearest-rank p95, maximum, completion/acceptance rates, measured
submission throughput, library versions and build IDs are retained in the JSON pair.
`preflight.json` retains the original legal-move rejection and source observation.

| Revision | Mean / maximum submission seconds | Accepted |
| --- | --- | --- |
| Pinned main | 0.655886 / 1.578792 | 0/9 |
| P21C runtime | 0.014734 / 0.018606 | 9/9 |

Reproduce with the current script and fixtures:

```sh
uv run --no-sync python scripts/measure_order75.py --runtime-src <base-checkout>/src --revision 9d8c5e2a1bb4db3c8a7f68b6da924c4ea9e23daa --output docs/performance/order75/base.json
uv run --no-sync python scripts/measure_order75.py --runtime-src src --revision <verified-runtime-id> --output docs/performance/order75/head.json
```

The base checkout must include its own `pyproject.toml` and `contracts/schemas`
for runtime identity verification. The component guards for Orders 64–66,
69–72, R73-001 and 74 require current-build head evidence. Both sides are
remeasured serially on this host at their original base revisions, using the
unchanged workloads and budgets. Their historical README timing tables remain
historical; current JSON identifies the qualified runtime and host. Previous
Windows reports remain in the reviewed main commit above.

Full games attempted/completed are 0/0. No representative complete-game driver
or recording was found; the below-60-second mean and at-most-300-second observed
maximum remain uncertified. Component/facade evidence cannot certify them.
PFINAL is Order 76 and requires this prerequisite to merge, then a fresh complete
audit. See `validation.json` for final correctness, package and client gates.
