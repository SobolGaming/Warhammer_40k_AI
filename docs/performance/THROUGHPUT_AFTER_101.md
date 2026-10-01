# Validation throughput after Order 101

This approved slice reduces repeated test and offline-generator work and trials
twelve complete behavioral CI shards. It does not change game rules, packaged
runtime code, source packages, the roadmap, or the 85% branch-coverage gate.
Full-game performance certification remains outside this validation workload.

## Preserved behavior and bounded reuse

The Aeldari datasheet tests pass their already constructed catalog to every
weapon lookup. The weapon inventory, Harassment Fire and Piratical Hero tests
retain their assertions and build fresh mutable armies, states and controllers.
The reused wargear/profile graph contains frozen dataclasses and immutable
containers; this is not a claim that every catalog field is deeply immutable.
In particular, ability descriptors can carry mutable JSON payloads. No session
fixture or production catalog cache is introduced.

The offline battlefield builder repeatedly visits the same frozen area poses and
immutable Shapely polygons. Its pose-to-polygon and outside-board calculations
retain at most 4,096 entries each; ordered polygon-pair overlap/contact-gap
calculations retain at most 65,536. Pair keys include the contact requirement.
The search inventory, score accumulation order, tolerances, tie-breaking,
rounding, all 45 layouts, source-byte authentication and complete output
comparison remain unchanged. Existing builder tests also compare uncached
geometry, altered poses/contact sets and invalid inputs with the cached path.

Native Windows contract validation initially failed because its two JSON writers
emitted CRLF. A retained full regeneration proved all 93 changed files, including
the manifest, were identical after only CRLF-to-LF conversion, with no missing or
extra files. The bounded repair makes those two writers explicitly emit LF and
adds byte-level checks to the existing exporter regression. No committed contract
artifact or runtime code changes; the complete base-ref gate remains required.

## Workloads and measurement boundaries

The baseline is merged main `38ce2265b81f2c0b2c9c668dae7536c239095193`, tree
`915a13a5c485ae9b1766360ace96883037a76daf`, identical to the complete Order 101
Linux run's head `6404fb05eed862fc3dd969a23c8b5511d61711bb`.

Same-host comparisons use native Windows on DESKTOP-E9A8G46, an AMD Ryzen
Threadripper 3970X with 32 physical/64 logical processors and approximately
128 GiB RAM, Python 3.14.5, the unchanged `uv.lock`, and canonical LF checkout
bytes. Each timing launches a fresh process, without coverage, profiling or
competing test workers. Wall time includes command startup and complete work.
This host is provisional, not a production reference machine.

- Focused workload: the exact existing weapon-inventory and Harassment Fire
  pytest node IDs, serial (`-n 0 --no-cov`), with all assertions retained.
- Generator workload: `uv run --no-sync python
  tools/build_event_companion_battlefields.py --check`, all 45 layouts.
- Diagnostics: separate catalog-construction counting and a complete generator
  cProfile run. Instrumented durations are not performance samples.

The two uncontended baseline focused samples are 229.0858933 and 226.0803902
seconds. Full generator samples are 312.1402916 and 316.7182585 seconds.
An earlier overlapping warm-up is retained and excluded with that reason.
The separate baseline diagnostic measured catalog construction counts of
3/6/3 for weapon inventory/Harassment Fire/Piratical Hero. The complete baseline
profile measured 1,638,510 area-polygon constructions and 115,933 geometry-score
calls.

Measured head `a835a65b5017c30adb7ecfda4a952bbbd808e0f7` completed focused samples
in 57.2138798 and 57.1577422 seconds, and generator samples in 148.7646463 and
147.6513555 seconds. Mean reductions are 74.87% and 52.86% respectively, for
these workloads only. Every invocation succeeded. Two samples do not establish
a population tail; the machine-readable nearest-rank p95 equals the observed
maximum. [Numeric results](throughput_after_101.json) retain UTC sample times,
receipt hashes, commands' input hashes, machine metadata and scope limitations.

The workload-driver hash is identical across base/head. Earlier base-focused
launcher receipts predate the added launcher hash/environment metadata and
dedicated pytest temp root; no authenticated identical launcher-hash claim is
made. The subprocess workloads are unchanged, and neither selected test uses a
temporary-path fixture. All raw receipts, including failed setup/type/lint and
contract-portability iterations, remain separate from successful timing samples.

Separate head diagnostics measured one catalog construction per affected test
and four distinct mutable states, matching the base state count. The complete
generator still performed 115,933 geometry-score evaluations across all 45 layouts. Area-polygon
construction fell to 67,097; actual cache hits/misses/current capacities are
recorded in the numeric evidence. Windows measured a 105,111,552-byte peak working
set for that cProfile-instrumented process, including native Shapely allocations.
This is not a baseline memory comparison or an unprofiled timing sample.

Later CLI/default, manifest and explanatory-document changes retain this true
measured revision; they must not relabel its timing receipts as a later head.
Complete local/hosted validation and both final-head reviews remain separate
delivery requirements.

## Complete Linux evidence and twelve-shard trial

Initial weights come from [run 36798414956](https://github.com/SobolGaming/Warhammer_40k_AI/actions/runs/36798414956),
with all eight successful Linux shards, four actual workers per shard, 10,207
unique successful cases and 287 behavioral files. The raw reports and timing
inventories are authenticated; committed duration metadata preserves report
hashes and provenance. Windows generation writes LF manifests for Bash consumers.
No test file or node is removed.

The historical hosted wall time is 29 minutes 17 seconds. The historical local
covered run is 884.9526 seconds on a different Mac with 18 workers; it is not a
same-host comparison with Windows. Idealized shard-weight estimates do not
establish hosted wall time or runner allowance. Sixteen shards are not selected.

The ready-PR trial must execute all twelve shards and authenticate their complete
case inventories, actual workers, timings and combined branch coverage. The
coverage gate admits exactly twelve named artifact directories, each containing
exactly its nonempty named coverage file, before combining. Missing, extra,
misnamed, empty or non-file inputs fail closed. Full local covered behavior,
quality without coverage, both type checkers, generated/base-ref checks,
TypeScript client/conformance, wheel smoke and pre-commit remain required.

Apply `docs/SEQUENTIAL_REMEDIATION_REVIEW_POLICY.md`: prioritize complete playable
behavior, normal legal-play failures, engine-generated valid-state persistence
and required trust boundaries. Any blocker must identify its reproduced entry
path, impact, normal reachability and violated requirement. Coordinated
hand-edited-history hardening remains separately queued without a demonstrated
supported input boundary. Preserve positive controls and source truthfulness.

Implementation, separate coding review and the additional fresh parent audit use
the owner's explicit Astra Extra High selection. Both reviews must cover the
final published head; preliminary review or a timing improvement is not a merge
authorization.
