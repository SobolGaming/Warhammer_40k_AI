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

## Final validation

The complete behavioral suite passed **8,398 tests** with **85.11% coverage**
(85% required), followed by **527 passing code-quality tests** without
coverage. Both used 64 xdist workers and work stealing. The behavioral run used
the bundled Node PATH prefix and produced the complete successful JUnit profile
used to regenerate all eight shards. The exact fail-closed shard check passed.

Ruff, formatting, mypy, Pyright, all 11 import contracts and pre-commit passed.
Source and engine generators, contract compatibility against the exact base,
generated TypeScript checks, five TypeScript unit tests, the conformance scenario,
and installed-wheel smoke passed. npm was unavailable; the package scripts were
executed through their identical Node entry points. The behavioral run emitted
10 SQLite unclosed-connection ResourceWarnings. No production changes followed
the successful coverage run.
