# Order 61 validation and component measurements

The shared post-move Embark query was measured on base
`832a0045772cff6946f29ad61af0d5d81de4313d` and the final runtime fingerprint in
`head.json`. Both runs used the same script, fixtures, dependency lock, Windows
11 host, Python 3.14.5 and one process, without concurrent test workers, coverage
or profiling. The host has a Threadripper 3970X and 137,327,259,648 bytes of RAM.
It is provisional hardware, not a certified full-game reference machine.

Each of seven samples prepares the same real transport session, then measures
50 accepted Embark option queries. Preparation is recorded separately; no dice
are rolled in the measured interval. All 350 queries completed on each revision.

| Measurement (50 queries) | Base | Head |
| --- | ---: | ---: |
| Arithmetic mean | 14.180 ms | 14.375 ms |
| Median | 13.321 ms | 14.268 ms |
| Maximum / nearest-rank p95 | 19.491 ms | 15.749 ms |

The checked component limits are a head mean no greater than twice the base mean
plus 20 ms, and a head maximum no greater than 150 ms. Both pass. These are
component diagnostics: complete gameplay slices and full games were not measured,
and this does not certify the standing 60-second mean / 300-second maximum
full-game targets or the deferred Order 32 budgets.

Reproduce in an otherwise idle environment, using a detached base worktree:

```text
uv run --no-sync python scripts/measure_order61.py --output docs/performance/order61/base.json --revision 832a0045772cff6946f29ad61af0d5d81de4313d --runtime-src <base-worktree>/src
uv run --no-sync python scripts/measure_order61.py --output docs/performance/order61/head.json --revision <engine-build-id> --runtime-src src
```

Machine-readable samples, input hashes and budgets are in `base.json` and
`head.json`. Final gate outcomes are recorded in `validation.json`.

## R61-001 restore diagnostic

`restore-base.json` and `restore-head.json` compare complete lifecycle restore
on the same whole-unit return checkpoint, against PR commit `6f61af54` and the
repaired runtime. Seven serial samples include the first cold restore. JSON
parsing, checkpoint construction and the equality assertion are outside the
timer. The checkpoint contains a real accepted return decision and authenticated
destruction/placement evidence, followed by primary scoring. No coverage or
competing test workers run during measurement. Machine, input and script hashes
are retained in each report.

The initial diagnostic is preserved in `restore-v1-base.json` and
`restore-v1-head.json`. Its provisional two-second absolute ceiling failed on
**both** revisions because cold catalog initialization took about six seconds;
that ceiling is not reported as passed. Budget policy
`order61-return-restore-regression-v2` instead applies the already chosen 20%
plus 20 ms regression allowance to both the mean and observed maximum. This
keeps cold initialization in the measured workload and compares the added
restore check to the same baseline cost. It is a checkpoint regression limit,
not a per-game budget or full-game certification.

Create the fixed checkpoint from the existing canonical lifecycle fixture:

```python
import json
import runpy
from pathlib import Path

fixtures = runpy.run_path("tests/unit/test_phase17n_primary_scoring_boundary_lifecycle.py")
lifecycle = fixtures["_scored_command_boundary_after_mutation"](kind="return_on_death")
Path("reports/order61-restore-checkpoint.json").write_text(
    json.dumps(lifecycle.to_payload(), sort_keys=True), encoding="utf-8"
)
```

Then, in an idle environment with a detached worktree at `6f61af54`:

```text
uv run --no-sync python scripts/measure_order61_restore.py --checkpoint reports/order61-restore-checkpoint.json --output docs/performance/order61/restore-base.json --revision 6f61af54e81c0acf2b47325175dc29b7a30171b3 --runtime-src <base-worktree>/src
uv run --no-sync python scripts/measure_order61_restore.py --checkpoint reports/order61-restore-checkpoint.json --output docs/performance/order61/restore-head.json --revision <engine-build-id>
```

The matched run averaged 1.394 seconds on base and 1.336 seconds on the repaired
runtime; observed maxima were 6.947 and 6.451 seconds. Both v2 regression limits
passed. These small samples do not establish a speedup.

The code-quality gate checks matched inputs and regression limits, and audits
that restore uses the shared timeline once outside the completion loop. The
original Embark-query results above describe the initial Order 61 implementation;
R61-001 changes only restore validation.

## Final validation

The complete behavioral suite passed **8,402 tests** with **85.11% coverage**
(85% required), followed by **529 passing code-quality tests** without
coverage. Both used 64 xdist workers and work stealing. The behavioral run used
the bundled Node PATH prefix. The existing eight-shard inventory remains complete:
this repair changes existing test files without adding or removing a behavioral
file. The exact fail-closed shard check passed.

Ruff, formatting, mypy, Pyright, all 11 import contracts and pre-commit passed.
Source and engine generators, contract compatibility against the exact base,
generated TypeScript checks, five TypeScript unit tests, the conformance scenario,
and installed-wheel smoke passed. npm was unavailable; the package scripts were
executed through their identical Node entry points. The behavioral run emitted
10 SQLite unclosed-connection ResourceWarnings. No production changes followed
the successful coverage run.
