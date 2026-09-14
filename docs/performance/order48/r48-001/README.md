# R48-001 retained-checkpoint restoration

This revision changes restore ownership checks and the retained casualty receipt
ledger. It reuses the existing retention-history authentication once. The
original Order 48 gameplay timings remain historical; this workload measures the
affected restore boundary directly.

`base.json` uses reviewed commit `a6ab86f764527c59bcd1039b27b4221f931ce8e6`.
`head.json` identifies the final working-tree runtime by its verified engine hash.
Both use the same script, fixtures, lockfile and provisional local Mac host,
recorded in the reports. All samples run serially without coverage, profiling or
competing test workers. Preparation and exact payload comparisons are outside the
timing boundary. Every successful restore must round-trip identically.

For both Crushing Impact and Explosives, the workload exercises source-backed
For the Chapter! and saves offered, accepted and completed checkpoints. Completed
checkpoints decline all reactions and supply a valid matched base/head cost
comparison. The base rejects both offered checkpoints and the accepted Crushing
Impact checkpoint with the reported missing-continuation error. The accepted
Explosives checkpoint already restores in this fixture because its packet has
closed; its subsequent retained completion is covered by the receipt fix.
Rejected samples remain explicit correctness failures, not comparative timing
passes. Behavioral regressions separately finish accepted shooting, restore the
completed state and reproduce exact replay.

Run from either checkout using the same Python environment, with the final script
and `tests/stratagem_retention_helpers.py`, `tests/crushing_impact_helpers.py` and
`tests/explosives_helpers.py` copied into the isolated base checkout:

```bash
PYTHONPATH=src:. .venv/bin/python scripts/measure_stratagem_retention_restore.py --samples 7 --output docs/performance/order48/r48-001/head.json
```

The predeclared `budgets.json` permits a 2x plus 50 ms matched completed-restore
mean and a 10-second maximum for any successful head restore. The static gate
requires all six scenarios, all seven samples, matching work counts and fixture
hashes, exact base success/failure outcomes, and successful head restoration
throughout. The same mean bound also covers the already-valid accepted Explosives
checkpoint.
These local component budgets accommodate measurement noise; they do not certify
the standing 60-second mean / 300-second maximum full-game objectives.

| Stratagem / checkpoint | Base outcome / mean | Head mean | Head maximum |
| --- | ---: | ---: | ---: |
| Crushing Impact / offered | Rejected | 2.0135 s | 2.0226 s |
| Crushing Impact / accepted | Rejected | 2.0481 s | 2.0556 s |
| Crushing Impact / completed | 2.9238 s | 2.9684 s | 3.0607 s |
| Explosives / offered | Rejected | 1.3459 s | 1.3785 s |
| Explosives / accepted | 1.3625 s | 1.3823 s | 1.4187 s |
| Explosives / completed | 1.5387 s | 1.5512 s | 1.5682 s |

All 42 head samples restored exactly and all declared bounds passed. Reports
identify Apple M5 Pro, macOS 26.6.2, Python 3.14.5, 18 allocated CPUs and
68,719,476,736 bytes RAM. The fixed runtime is
`warhammer40k-core-v2:runtime-tree-sha256-v1:fed68d40c0b0c5a06e7ee8875c55b28c778438776a0ef5ff00feb13d165542dc`.
