# Order 49 performance evidence

Matched provisional reference host: Apple M5 Pro, macOS-26.6.2-arm64-arm-64bit-Mach-O, Python 3.14.5,
18 allocated CPUs and 68719476736 bytes RAM. Seven serial,
uninstrumented samples per revision used the same lockfile, fixture, benchmark
script and permissions, without competing test workers.

The versioned `order49-charge-reroll-slice-v1` workload declares a Charge, declines
Command Re-roll if offered, selects its target and submits an accepted witnessed
move through the next decision. The fixture starts with one CP. Base completes
three decisions and 43 events; head exposes the newly legal reroll choice and
completes four decisions and 47 events. This measures the cost of the added
boundary. The declared time budgets are unchanged; the work-count budget accounts
for precisely that one additional choice.

| Revision | Mean (s) | Maximum (s) |
| --- | ---: | ---: |
| Base | 0.022170 | 0.023827 |
| Head | 0.026819 | 0.029158 |

`base-initial.json` preserves the preimplementation measurement with the previous
benchmark. `base.json` reruns the final script in an isolated checkout of
`8e569cd024ffbedab035febdc262dfc410041b48` without changing its runtime code.
Both final reports have identical script, fixture and lockfile hashes. Head's
runtime diff includes all staged extracted modules and its engine build identity.

```bash
PYTHONPATH=src:. uv run --no-sync python scripts/measure_charge_endpoints.py --include-charge-reroll-window --samples 7 --output docs/performance/order49/head.json
```

Run the same final script and flag in the isolated base checkout with the same
Python environment to reproduce base. The required code-quality audit validates
the matching inventory, complete samples and `budgets.json` limits.

Accepted Command Re-roll, natural rerolls, Heroic Intervention and checkpoint
replay are covered behaviorally, not included in this timing boundary. No new
capability-wide performance certification is claimed. Full-game performance is
**not certified**; the standing mean below 60 seconds and observed maximum below
300 seconds remain unchanged. No broader efficiency work, approximation, timeout
answer or AI driver was introduced.

## Existing action-restriction work budget

`action-restrictions-base.json` and `action-restrictions-head.json` profile the
same existing Order 34 unrestricted workload and script. Both complete six
decisions with 32 effects. Every work metric is identical except
`rules_unit_identity_ids`: 8 becomes 10. The two additional calls are the required
Battle-shock checks when enumerating and validating Command Re-roll's corrected
unit target. The source previously treated that Stratagem as targetless.

The Order 34 unrestricted work budget explicitly records version
`order49-command-reroll-unit-target-v2` and changes only that ceiling from 8 to 10.
All timing, geometry and other work limits remain unchanged. Profile wall times
are excluded from this evidence; this is a deterministic work-count comparison.
