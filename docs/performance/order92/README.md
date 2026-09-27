# Order 92 performance and validation

Runtime: `warhammer40k-core-v2:runtime-tree-sha256-v1:01ced161f9bddcc59df61bea4ede7647cab4261ae044c3365364ded5650fa70d`.

Matched measurements use the same versioned fixture, script and dependency lock,
on provisional Apple M5 Pro / 64 GiB hardware, Python 3.14, serial execution,
without coverage or competing test/build workers. The archived base source is
`ad096b7f238bd623c7c1c17c0cd42d70564e87d8`; the current fixture is shared by both runs.
The fixed fixture has three one-model units and two engaged enemies, no terrain.
Each row contains five observations; setup is recorded separately.

| Declaration boundary | Base mean | Head mean | Change |
|---|---:|---:|---:|
| Fixed A | 31.453 ms | 31.976 ms | 1.66% |
| Random A | 31.860 ms | 34.957 ms | 9.72% |

The random path now includes an additional recorded finite weapon/profile decision,
physical attack generation, and immutable target facts before target declaration.
The historical base reaches target declaration before random attack generation;
the diagnostic deliberately reports that workload difference in its outcomes.
It does not establish an equivalent gameplay-slice or full-game performance bound.

`inherited-refresh.json` records commands, durations, exit codes and hashes for
runtime-bound head diagnostics. Historical baselines, budgets and hard cases are
retained. The Order 32 component-budget deferral remains in effect. No complete
head-to-head game was measured; the mean <60 s / observed maximum <=300 s
full-game targets remain unverified.

## Final validation

The complete successful behavioral run passed **9,559 tests** with **85.16%
branch-inclusive coverage**, followed by **698 code-quality tests** without
coverage. Both used 18 xdist work-stealing workers. The successful JUnit profile
regenerated all eight shard manifests and their duration inventory.

The first behavioral diagnostic found one stale API assertion expecting contract
40.0.0 instead of 40.1.0; the first quality diagnostic found the missing finite
decision catalog entry. Those test/documentation corrections passed focused
checks before the clean aggregate reruns. No production code changed after the
independent implementation approval or during aggregate validation.

Ruff, formatting, Mypy, Pyright, all 11 import contracts, source-actions generation,
runtime identity, external contracts against the exact base, installed-wheel smoke,
generated TypeScript checks, five client unit tests and all 342 HTTP conformance
assertions passed. Independent review resolved both findings and approved the
implementation. Final shard and pre-commit results are included in the
[machine-readable validation record](validation.json).
