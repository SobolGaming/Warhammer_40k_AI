# Order 65 Firing Deck component assessment

The workload measures an accepted facade declaration through the next pending
decision, then 100 shared eligibility queries for a noncontributing passenger.
It covers zero borrowed weapons and one borrowed weapon, with two five-model
cargo units, one Transport, five enemy infantry and empty terrain. Both revisions
use the same canonical seed, first finite option, script, helper and dependency
lock. The base is `ca2eea9f`; its missing restriction is a correctness defect,
so its timing is only a cost comparison.

Both revisions were measured serially on the same provisional Windows 11 host,
Python 3.14.5, AMD Ryzen Threadripper 3970X, 64 logical CPUs and 137,327,259,648
bytes RAM, without coverage, profiling or competing test/build workers. Fixture
and unit-view preparation are outside the timers. Seven samples per scenario
retain mean, median, nearest-rank p95 (the maximum for seven samples), maximum,
completion and exact runtime/input identities. All 28 declaration samples and
2,800 query calls completed. Every head query returned the Firing Deck restriction;
base queries reproduced the missing restriction.

| Borrows a weapon | Operation | Base mean / max (s) | Head mean / max (s) |
| --- | --- | ---: | ---: |
| False | Accepted declaration | 0.106786 / 0.119503 | 0.138419 / 0.153893 |
| False | 100 eligibility queries | 0.003449 / 0.003875 | 0.000751 / 0.000845 |
| True | Accepted declaration | 0.085439 / 0.091044 | 0.096403 / 0.129335 |
| True | 100 eligibility queries | 0.003314 / 0.003454 | 0.000759 / 0.001060 |

The declared mean budget is base × 1.30 plus 50 ms per declaration or 10 ms per
100 queries; the maximum budget is base × 1.50 plus 100 ms. These allowances cover
small-sample timing variability and the newly required snapshot/effect validation.
All comparisons pass. CI checks matched evidence, current runtime identity and
input hashes; a separate live profile requires exactly one payload validation per
matching effect per query and verifies no state mutation. Shared queries read live
effects, never decision/event history.

At these measured means, ten declarations and 1,000 queries would cost under
1.4 seconds. That is a linear component estimate, not an observed phase or game;
actual calls per complete game remain unmeasured. Gameplay-slice and full-game
performance are not certified, including the standing 60-second mean / 300-second
maximum targets and deferred Order 32 budgets.

Reproduce without competing workers:

```powershell
uv run python -m scripts.measure_order65 --output docs/performance/order65/base.json --revision ca2eea9f --runtime-src <base-checkout>/src
uv run python -m scripts.measure_order65 --output docs/performance/order65/head.json --revision <current-engine-build-id>
```

Regenerate the engine manifest first. If runtime identity or workload inputs
change, retain fresh matched evidence; never relabel an old timing report. The
existing [Order 64 reconstruction guard](../order64/README.md) is also refreshed
for this engine build with its unchanged baseline and budgets.

Original Order 65 local validation passed 8,484 behavioral tests at 85.12% coverage and all 549 code-quality tests. The required lint, type, shard, import, generated-contract, TypeScript conformance and installed-wheel checks passed. Exact results and diagnostic history are retained in [validation.json](validation.json).

Order 68 refreshed the head measurements for the current runtime build on
2026-09-20, retaining the same host, workload, baseline and budgets. Every
comparison passes. Current validation is recorded in
[Order 68 validation](../order68/validation.json); the original validation record
remains unchanged.
