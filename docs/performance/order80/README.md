# Order 80 / P09C performance

The matched workload accepts an opponent's reactive Normal Move, advances through
the turn boundary to the moving unit's own Movement action, and exports/restores
the session checkpoint. Initial fixture and permission preparation are excluded.
Finite and parameterized submissions each have three serial samples, without
coverage or competing test/build workers, on the same provisional Apple M5 Pro
host. Both reports pin the same harness, canonical fixture and dependency hashes.

The reviewed base is `dc01911f57024ae69b565a0e965db65abf5fbdbe`. The base wrongly
omits Normal Move from the final menu; the head offers it. The same decisions
and checkpoint work are timed in both runtimes. Initial exploratory fixtures were
extended with explicit deployment history before this matched pair was measured.

| Case | Base mean / maximum | Head mean / maximum |
| --- | --- | --- |
| Finite reaction | 2.090 / 2.100 s | 2.083 / 2.102 s |
| Parameterized reaction | 2.006 / 2.021 s | 2.026 / 2.039 s |

The versioned budget permits a head mean at most 1.25 times base plus 100 ms,
and no head sample above 12 seconds. All samples completed and passed. The
behavioral regressions independently establish the repaired semantics.

```sh
PYTHONPATH=.:scripts uv run --no-sync python scripts/measure_order80.py \
  --runtime-src /path/to/reviewed-base/src \
  --revision dc01911f57024ae69b565a0e965db65abf5fbdbe \
  --output docs/performance/order80/base.json
PYTHONPATH=.:scripts uv run --no-sync python scripts/measure_order80.py \
  --runtime-src src --revision '<verified-runtime-id>' \
  --output docs/performance/order80/head.json
```

Use this checkout's harness and an isolated base containing committed `src`,
`contracts/schemas` and `pyproject.toml`. Inherited current-runtime evidence for
Orders 64–66 and 69–79 is refreshed serially using its existing scripts and
numeric budgets, including both Order 73 and both Order 77 workloads. Historical
base reports are retained unchanged. The inherited Order 77 helper hash follows
the explicit [fixture migration](inherited-fixture-migration.json): decision actors
now use moving-unit ownership, while the benchmark initializer functions and
measured operations are unchanged. Both affected head reports were remeasured. Order 76 similarly records the
[opt-in deployment fixture migration](order76-fixture-migration.json). Its guard
removes only the exact optional branch and disabled default parameter and proves
the remaining complete module AST matches the original. Order 76 does not enable
that flag; its original base samples and numeric limits remain unchanged.

Complete games attempted/completed: **0/0**. These are component and bounded
gameplay measurements. The standing complete-game mean below 60 seconds and
observed maximum at most 300 seconds remain uncertified. This prerequisite does
not provide PFINAL's 25-category compliance certificate.
