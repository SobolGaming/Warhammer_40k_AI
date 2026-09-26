# Order 87 performance evidence

`base.json` and `head.json` record five serial executions of the same fixed-profile
Charge-to-Stratagem facade workload, followed by twenty viewer queries. Measurements
ran on the same provisional Apple M5 Pro host (18 logical CPUs, 64 GiB RAM), Python
3.14 and dependency lock, without coverage or competing test workers. Setup,
accepted witnessed Charge, and subsequent views are timed separately. The base
runtime is `7f4384b8`; head is pinned by runtime manifest `904893c1`.

| Mean seconds | Base | Head |
|---|---:|---:|
| Setup | 0.88949 | 0.88330 |
| Charge slice | 0.06009 | 0.05972 |
| Twenty views | 0.07204 | 0.07168 |

Charge mean changed by -0.6% in this small sample. Medians and maxima are
retained, including cold setup; no sample was removed. With five observations,
nearest-rank p95 is the recorded maximum. Charge-only throughput is approximately
16.6 versus 16.7 slices/second, excluding setup and views. These are diagnostics,
not calibrated performance certification. Component timing budgets remain deferred
under the owner's Order 32 exception. No budget was raised or claimed to pass.

The deterministic work check confirms that twenty viewer queries consume zero
events/dice and fixed profiles introduce zero random-profile rolls. Order 87's
behavioral regressions additionally enforce shared Movement rolls, independent
weapon/model rolls, skipped-stage suppression and no projection/restore rerolls.

Run the same script against each checkout with the same interpreter/dependencies:

```sh
PYTHONPATH=.:src /path/to/shared/.venv/bin/python \
  /path/to/current/scripts/benchmark_order87_profiles.py --output /tmp/profiles.json
```

The fixture uses twenty models in four units, no terrain, the fixed game ID in
the JSON as deterministic seed, a legal witnessed Charge, and no Stratagem choice.
Full-game samples remain zero; full-game mean and maximum are unknown. Random-profile
end-to-end timing is also unmeasured. Neither standing full-game target is certified.


## Inherited current-runtime gates

The 24 inherited head reports were remeasured serially for runtime `904893c1`,
without coverage or competing test/build workers, on the same host, interpreter,
lock and workloads as the retained baselines. Their existing numeric budgets and
semantic/work-count assertions are unchanged. Commands, elapsed run times and
report hashes are retained in [the refresh record](inherited-refresh.json).
The preliminary pre-format measurements are labelled separately and do not certify
the final identity.

The historical Order 80 remeasurement attempt failed because the current setup
fixture supplies `decisions` to `record_primary_turn_start_evidence`, while the
historical runtime does not accept that keyword. It produced no replacement
baseline. The historical baselines remain unchanged. Following the existing
Order 76/77 approach, [fixture migration pins](inherited-fixture-migration.json)
and a complete-module AST comparison prove that Order 80 does not opt into the
new optional catalog parameter, and Order 86 does not invoke the two casualty
helpers whose health accessor changed. All other input hashes, environments,
result assertions, sample counts and numeric limits remain enforced.
