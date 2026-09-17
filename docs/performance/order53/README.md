# Order 53 movement assessment

This component assessment repeats seven serial samples on identical base/head
hardware, dependency lock, fixture and driver. Each sample resolves four witnessed
five-model moves: two ordinary and two reactive, over open terrain. The source
keyword is present in both workloads; the base has no Order 53 semantics. The compact vehicle group crosses its own friendly Vehicle models: base rejects
these paths without the ability, while head accepts them. Both retain five
per-model path results each. Fixture construction
is outside the timing boundary. Coverage/profiling and competing tests are excluded.

Before measurement, retain the existing narrow movement component budgets:
head mean at most base mean times two plus 0.02 seconds, maximum 0.5 seconds.
These are regression diagnostics under the Order 32 exception. Complete-game
performance and long-history scaling remain unmeasured and are not certified.

Run the same committed driver in each isolated runtime, with that runtime's
`src` and root on `PYTHONPATH`, and record the exact revision:

```sh
PYTHONPATH=src:. uv run --no-sync python scripts/measure_order53.py --revision REVISION --output report.json
```

The final matched runs used the provisional Apple M5 Pro host, macOS 26.6.2,
Python 3.14.5, 18 allocated CPUs and 64 GiB RAM. Base mean: 12.713 ms. Head mean:
12.781 ms; head maximum: 13.981 ms. Both unchanged component budgets pass.
`base.json` pins main `53d89a28915700b8d655942c54ca6a9ff8f7f660`; `head.json`
pins the final runtime build identity. Both retain the same driver/helper/lock
hashes, all samples and exact path diagnostics. Each base rejection is a friendly
Vehicle/Monster transit restriction; every head path is accepted without a path
violation. The base ran from an isolated `git archive`, with only the identical
measurement driver supplied.

`initial-base.json` and `initial-head.json` preserve the first diagnostic samples.
Their generic correctness note incorrectly called these paths legal on both
runtimes; the recorded booleans already show the expected rejection/acceptance
split. Final reports correct that description and add per-path violation codes.
No path, sample count or budget was removed or relaxed. A later authority-only
change was followed by another head measurement for the final runtime identity.

The review correction to reactive keyword validation and completion classification
was followed by fresh base/head measurements on this unchanged workload. The
resolver workload is a component diagnostic; it does not measure selected MOBILE
completion orchestration. That path is covered by the reactive completion,
continuation, restore and replay regressions, with full-game timing still deferred.

The existing Order 35 Rapid Ingress work gate found one unnecessary canonical
unit lookup for an ingress action with no movement mode: nine against its limit
of eight. `rapid-ingress-before.json` and `rapid-ingress-after.json` retain the
profiled diagnostics. Explicit stationary/placement actions now reject any keyword
grant and otherwise return before querying unit membership. The legal ingress
path again uses eight lookups, with all other counted work unchanged. Ordinary
moving choices still validate their complete source and all-model membership.
The interrupted aggregate run was discarded, and final coverage/quality gates
were rerun after this production fix; no budget was raised.
