# Order 48 performance evidence

Provisional local host: Apple M5 Pro, macOS-26.6.2-arm64-arm-64bit-Mach-O, Python 3.14.5, 18 allocated CPUs, 68719476736 bytes RAM. All timed runs used one process, the same lockfile, no coverage/profiler, and no competing test workers.

## Matched Charge workload

The pre-existing `order47-charge-slice-v1` workload measures declaration, finite target selection and a two-segment accepted charge path through the next decision. Base and head both complete three decisions and 43 events. The measured means are 0.021779 s and 0.021814 s; maxima are 0.023514 s and 0.023342 s.

`base-initial.json` preserves the preimplementation run. Final `base.json` was rerun in the isolated base checkout with the final shared fixture copied over; the added optional enemy-attachment argument leaves this workload unchanged. Runtime source on base was untouched. The fixture, script and lockfile hashes match head. Head records the staged complete runtime diff and engine build identity before the final commit.

```bash
PYTHONPATH=src:. uv run --no-sync python scripts/measure_charge_endpoints.py --samples 7 --output docs/performance/order48/head.json
```

Run the identical command against base `10a3b19d09a9fdb0aa1bd393e8bc141487368d05` in a separate checkout, using the same interpreter and final shared fixture, to reproduce the comparison. The retained `budgets.json` applies the predeclared 2x plus 50 ms mean allowance, 500 ms maximum, and fixed decision/event limits. The allowance accommodates small-slice measurement variability.

## Newly enabled capability

Base skips Crushing Impact, so it cannot provide a correct end-to-end comparison for the new capability. `crushing-impact.json` separately measures the complete Charge-to-Stratagem-to-next-charger path. The named Toughness-96 workloads are cap stress cases, not representative army characteristics. Setup is reported separately.

| Scenario | Mean (s) | Maximum (s) | Decisions | Events |
| --- | ---: | ---: | ---: | ---: |
| ordinary | 0.1621 | 0.2009 | 5 | 98 |
| both_caps_and_feel_no_pain | 1.2559 | 1.2871 | 18 | 139 |
| both_attached_units_destroyed | 1.3528 | 1.3862 | 12 | 227 |

```bash
PYTHONPATH=src:. uv run --no-sync python scripts/measure_crushing_impact.py --samples 7 --output docs/performance/order48/crushing-impact.json
uv run pytest tests/code_quality/test_order48_crushing_impact.py -q --no-cov
```

All 21 new-capability samples completed within the predeclared slice and work-count limits. The required code-quality gate checks the complete scenario inventory, matched environment and hashes, per-side six-wound cap, and both budget sets. Deadly Demise, checkpoint restoration, tamper rejection and exact replay are validated by behavioral tests; they are not silently included in the timing boundary.

Full-game performance is **not certified**. The standing sub-60-second mean and 300-second observed-maximum full-game objectives and deferred efficiency work remain unchanged. No AI driver, solver approximation, cache policy change or rules timeout was introduced.
