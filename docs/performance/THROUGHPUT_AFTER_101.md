# Validation throughput after Order 101

This approved slice reduces repeated test and offline-generator work and trials
twelve complete behavioral CI shards. It does not change game rules, packaged
runtime code, source packages, roadmap order or acceptance requirements, or the
85% combined coverage gate with branch tracking.
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

Native validation uses process-local `PYTHONUTF8=1` before launching Python or
`uv` (`$env:PYTHONUTF8 = "1"` in PowerShell), with task-local Node 24.18.0 on
`PATH`. This preserves canonical UTF-8 source/evidence decoding without changing
the operating-system locale. The complete-gate receipts record the mode.
Two audit path identifiers use `as_posix()` so native Windows discovers the same
engine consumer and conftest identities as the committed POSIX inventory.
The full negative controls and all reviewed source/evidence pins remain intact.

An initial native covered run failed two evidence-file reads under cp1252. A
temporary explicit-encoding test edit passed complete behavior but changed five
whole-function AST receipts pinned by Order 97; full quality correctly rejected
that drift. The test was restored to its exact reviewed bytes, retaining the
existing inventory identity. Failed receipts and the successful intermediate
behavior receipt keep their actual revisions; neither substitutes for complete
validation after this final environment and portability repair.

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

## Complete Linux evidence and measured twelve-shard trial

The initial twelve assignments used all eight successful reports from
[run 36798414956](https://github.com/SobolGaming/Warhammer_40k_AI/actions/runs/36798414956).
The complete twelve-shard [trial run 36820420185](https://github.com/SobolGaming/Warhammer_40k_AI/actions/runs/36820420185)
then passed all 20 jobs at published head
`71d10b08111de11ae148103e83394035d4a9f877`. Its synthetic merge
`aaba9716eb29fc8252c51dc3bb92bfcd352e03d1` has the same tree as that head.
All twelve archive digests, complete worker collections and setup/call/teardown
records were authenticated: 10,207 unique successful behavioral cases in 287
files, four actual workers per shard, and exactly the baseline node-ID set.
The separate quality report preserves all 797 successful baseline cases.
The combined coverage gate passed with branch tracking and the unchanged 85%
threshold.

Observed hosted wall time fell from 29m17s to 22m46s, a 6m31s (22.25%) reduction.
This is one complete cross-run observation, including shared-runner variation and
queueing, rather than an isolated causal timing experiment. Raw summed job time
was 211.8 runner-minutes versus 213.9333; these are not billed minutes or monetary
cost. Not every lane improved: full quality took 872 seconds versus 672 seconds,
with controller durations of 826.1250 versus 627.4253 seconds.

Behavior setup took 33–46 seconds per job, test steps 582–1,206 seconds, and the
final coverage job 73 seconds. Shard 4 was last; its session-persistence file
accounted for 1,960.346 worker-test seconds. The longest individual trial case
took 381.585 seconds. These tails and file-weight changes motivate refreshing the
assignments while retaining every case and the existing work-stealing scheduler.
The final twelve manifests use only this complete Linux trial, with its twelve
original JUnit hashes and provenance committed in `ci/test_shards/durations.json`.
Their balanced work totals are estimates of worker work, not promised wall time;
the final hosted run measures the revised assignment. Windows writes canonical LF
manifest bytes for Bash consumers.

Twelve shards remain selected. The authenticated organization API reported the
Free plan, whose [documented standard hosted limit](https://docs.github.com/en/actions/reference/limits#job-concurrency-limits-for-github-hosted-runners)
is 20 concurrent jobs (five macOS). Twelve behavioral shards plus six initially
independent lanes total 18 jobs; sixteen shards would total 22. Custom support
limits and currently available organization-wide capacity were not exposed.
Observed peak concurrency was 18; that observation alone is not an allowance.
No sixteen-shard trial or gate removal is claimed.

The complete native Windows covered run at the same published head passed all
10,207 cases in 1,243.5366128 seconds with 85.2005226% combined coverage and branch
tracking. Full quality then passed all 797 cases in 335.2871963 seconds without
coverage. Both used 64 work-stealing workers and recorded `PYTHONUTF8=1`; all
5,297 tracked inputs stayed unchanged. The historical 884.9526-second local result
came from a different Mac with 18 workers and is not a same-host comparison.

That successful local behavioral receipt keeps its true `71d10b08` revision.
The final metadata update changes only the thirteen shard/profile files and these
two dedicated performance reports. Complete input hashes and the exact diff,
together with the behavioral consumer review, establish its applicability;
workflow, source, test bodies/helpers, configuration, lockfile and source/generated
data stay byte-identical. Any behavioral input change requires revalidation.
Full local quality and complete hosted CI run on the final publication head;
both exact-head reviews remain required. Final results are reported on
[PR525](https://github.com/SobolGaming/Warhammer_40k_AI/pull/525).

The coverage gate admits exactly twelve named artifact directories, each
containing exactly its nonempty named coverage file, before combining. Missing,
extra, misnamed, empty or non-file inputs fail closed. Both type checkers,
generated/base-ref checks, TypeScript client/conformance, wheel smoke and
pre-commit remain required. The measured trial did not reach a 16-minute hosted
target and does not authorize removing the full local covered gate.

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
