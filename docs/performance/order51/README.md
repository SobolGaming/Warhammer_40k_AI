# Order 51 performance evidence

Provisional host: Apple M5 Pro, macOS 26.6.2 arm64, Python 3.14.5,
18 allocated CPUs and 64 GiB RAM. Seven serial samples per revision ran without
coverage, profiling or competing test workers. The reports retain setup separately,
scenario and script hashes, runtime diff, exact engine identity and all samples.
The ordinary measurements precede the Heroic measurements.

| Workload | Mean (s) | Maximum (s) | Decisions | Events |
| --- | ---: | ---: | ---: | ---: |
| Ordinary base | 0.025781 | 0.029906 | 4 | 47 |
| Ordinary head | 0.026083 | 0.028945 | 4 | 47 |
| Heroic base | 0.044001 | 0.083253 | 4 | 67 |
| Heroic head | 0.045013 | 0.082607 | 4 | 67 |

Base runtime is the detached `dc043bf27baf51c02d8db1a177190ecd77ad3254`
checkout. Only the versioned Heroic measurement driver was copied into that
checkout. Runtime modules and fixtures are unchanged. The inherited Order 50
budgets (including 0.5-second slice maximum) are unchanged and enforced by
`tests/code_quality/test_order51_flight.py`.

The original Heroic workload assumed a seeded roll would reach its fixed target.
The new decision payload changes deterministic RNG history and exposed that
assumption. `initial-heroic-base.json` and `initial-heroic-head-failure.json` retain
that attempt. The v2 workload applies a real +20 Charge-roll modifier before the
existing six-inch cap on both revisions, ensuring the same accepted four-inch
path is measured without replacing dice or validators.

Reproduce each revision with its matching runtime and the committed driver:

```sh
PYTHONPATH=src:. uv run --no-sync python scripts/measure_charge_endpoints.py --include-charge-reroll-window --samples 7 --output ordinary.json
PYTHONPATH=src:. uv run --no-sync python scripts/measure_heroic_intervention.py --samples 7 --output heroic.json
```

These slices assess the shared Charge choice, validation and completion overhead.
Selected flight, reactive movement, attached units, vertical distance and Heavy
are covered behaviorally; no timing certification is claimed for those distinct
workloads. Full-game performance remains uncertified and broader efficiency work
remains deferred under Order 32. The standing full-game targets remain unchanged.
