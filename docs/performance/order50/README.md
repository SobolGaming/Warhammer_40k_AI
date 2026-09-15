# Order 50 performance evidence

Matched provisional reference host: Apple M5 Pro, macOS 26.6.2 arm64, Python
3.14.5, 18 allocated CPUs and 64 GiB RAM. Seven serial uninstrumented samples
per revision used the same lockfile, script, fixture and permissions, without
competing test workers. Both reports identify their exact engine build and
runtime diff; head includes the new engine modules in that fingerprint.

| Workload/revision | Mean (s) | Maximum (s) | Decisions | Events |
| --- | ---: | ---: | ---: | ---: |
| Ordinary base | 0.025738 | 0.028300 | 4 | 47 |
| Ordinary head | 0.024558 | 0.026765 | 4 | 47 |
| Heroic base | 0.026082 | 0.029071 | 2 | 52 |
| Heroic head | 0.036074 | 0.039532 | 4 | 66 |

The ordinary workload is the unchanged Order 49 declaration, target selection
and accepted witnessed Charge. Its work counts remain unchanged. The Heroic
workload starts at the end-of-Charge opportunity, selects Into the Fray and
completes the same accepted two-segment model paths through the next decision.
Head adds ordinary declaration and target selection, plus source and active-player
scope events. Setup is recorded separately from the timed boundary.

Base is an isolated checkout of `a4a31b381f9bec6bce0812b8aa0645b5a3297a54`.
Only the final benchmark driver and canonical fixture were copied into that
checkout; its runtime code was unchanged. Both revisions use identical hashes
for each matched workload. `ordinary-base.json` was captured before production
changes. The versioned budgets were set before the final measurements and are
enforced by the Order 50 code-quality audit.

```bash
PYTHONPATH=src:. uv run --no-sync python scripts/measure_heroic_intervention.py --samples 7 --output docs/performance/order50/heroic-head.json
PYTHONPATH=src:. uv run --no-sync python scripts/measure_charge_endpoints.py --include-charge-reroll-window --samples 7 --output docs/performance/order50/ordinary-head.json
```

Natural rerolls, source-loaded grants, modifier-ignore choices, target replacement,
attached actors, replay and restoration are validated behaviorally and are not
included in these timing boundaries. Full-game performance is **not certified**.
The standing mean below 60 seconds and observed maximum below 300 seconds are
unchanged; broader efficiency work remains deferred under Order 32.
