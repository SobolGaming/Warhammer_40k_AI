# Order 62 component measurements

The matched workload submits a legal Shock Disembark placement with no enemy
engagement and restores its serialized lifecycle exactly. Both revisions accept
this case, so it measures the added engagement-history validation on an identical
path. Newly engaged forced-Fight behavior is covered by facade and replay tests;
the incorrect base cannot provide an equivalent accepted timing sample for it.

Base is `31dd2cb4613a40caa97e6d5d4575b76a561fed1f`. Head is identified by the
runtime fingerprint in `head.json`. Both runs used identical script, fixture and
dependency-lock hashes, Python 3.14.5 and the same provisional Windows 11 host:
Threadripper 3970X, 137,327,259,648 bytes RAM, one process. No coverage, profiler,
or competing test workers ran during measurement. Each of seven samples creates
a real four-unit, sixteen-model fixture on an empty battlefield. Preparation and
option selection are outside the measured interval; no dice are rolled.

| Seconds per placement and restore | Base | Head |
| --- | ---: | ---: |
| Arithmetic mean | 1.004623 | 0.952924 |
| Median | 1.006021 | 0.933013 |
| Maximum / nearest-rank p95 | 1.140411 | 1.048068 |

All seven samples completed on each revision. The versioned component gate allows
twice the base mean plus 20 ms and twice the base maximum plus 50 ms. These broad
regression limits accommodate host variability while detecting a large added
cost; both pass. They are diagnostic limits, not an allocation of the full-game
budget. A complete gameplay slice and full games remain unmeasured. Neither the
60-second mean / 300-second maximum game targets nor deferred Order 32 budgets
are certified by these results.

Reproduce serially in an otherwise idle environment:

```text
uv run --no-sync python scripts/measure_order62.py --output docs/performance/order62/base.json --revision 31dd2cb4613a40caa97e6d5d4575b76a561fed1f --runtime-src <base-worktree>/src
uv run --no-sync python scripts/measure_order62.py --output docs/performance/order62/head.json --revision <engine-build-id> --runtime-src src
```

The code-quality gate checks matching inputs, complete samples, and both numeric
limits. Machine-readable final validation is recorded in `validation.json`.

## Final validation

All 8,405 behavioral tests passed with 85.11% coverage (85% required), followed
by 532 passing code-quality tests without coverage. Both used 64 xdist workers
and work stealing. The behavioral run used the bundled Node PATH prefix and
emitted 10 SQLite unclosed-connection ResourceWarnings.

Ruff, formatting, mypy, Pyright, all 11 import contracts, the exact eight-shard
inventory check and pre-commit passed. Source/runtime generation, external
contract verification against the exact base, generated TypeScript checking,
type checking, five client unit tests, 342 conformance assertions and the
installed-wheel smoke passed. npm was unavailable; the identical package-script
Node entry points were used directly.

The initial aggregate launch was cancelled while contract generation rebuilt
its outputs. The complete final behavioral run was executed once with coverage.
Four obsolete static expectations failed the first quality run; updating those
audits to the approved engagement ownership and source resolution produced the
passing rerun. No production code changed after the successful coverage gate.
