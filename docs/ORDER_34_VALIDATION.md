# Order 34 validation and independent-review handoff

PR: https://github.com/SobolGaming/Warhammer_40k_AI/pull/438

Base: `e56c1a4caf2a6915548222caed0872627f8dbf43`.
Final behavioral candidate: `533300706bbe3e8d850d41cbfe1d2c1013fe0196`.
Performance commit: `5b6752ff07bc5b86e91054a7822ee7ea7dadf7cb`; the production
source tree is identical to the final behavioral candidate.
Later evidence-only commits preserve these trees and measurement inputs:

- Source tree: `7342088900a27801964819690229b8471b59bbc7`.
- Test tree: `a53d1cda2ba060a3b5f099d2154f6f07d8c34887`.
- Engine build: `warhammer40k-core-v2:runtime-tree-sha256-v1:ab699c69e39310e5c158976bdf3169b5ca282c8e3a65163681b59a201e20196e`.
- Manifest SHA256: `35277d8c1634d8924bc8b722b54d7b94b512e67f07b8ba766c1156ca1c992200`.

The source-clause, owner, consumer and regression matrix is in
[ORDER_34_SCOPE_PLAN.md](ORDER_34_SCOPE_PLAN.md). Complete operative source
wording, historical observations and partial execution classifications remain
versioned. This work implements the scoped Action restrictions, not unrelated
source-package clauses or future Orders.

## Independent findings and repair

The independent follow-up reviewed `9699f8f8aaebc1a452b11eafda9fe14f1cddd6b9`
against the base above and requested changes. Its stable IDs are preserved:

- **R34-001:** independently closed on that revision. Retained shooting option
  generation, pre-pop validation and execution consult the shared Action/TITANIC
  authority before changing the parent continuation. Nested real mission Action
  and For the Chapter! regressions retain legal alternatives, persistence and replay.
- **R34-002:** repaired in `c87d5352fbaace2e077dcd754d1030c95d7b1644`, with
  canonical fixture repairs in the tested commit. Every asserted completed
  shooting participation must retain an accepted declaration, exact request and
  decision-ledger closure, original ranged activation, subject models and timing.
  A copied participation/completion pair cannot establish an executor origin in
  a fresh unactivated session. Valid mid-executor checkpoints retain their
  accepted declaration prefix. The original effect-inventory mutations and new
  undeclared, foreign, retimed and unaccepted pairs are covered. The existing
  declaration/decision authority is reused outside hot eligibility queries.
- **R34-003:** fresh timing and work evidence now measures the final repaired
  runtime. All 98 uninstrumented samples and versioned budgets pass. The original
  difficult Indirect cases and separate incomplete attached diagnostic are retained.

These are author repair results, not independent approval. Re-review must target
exactly the published evidence head; Order 34 is not represented as fully closed.

## Required local validation

Logs and terminal metadata are committed under
[followup-validation](performance/order34/followup-validation/). Large complete
logs use lossless gzip; `gzip -dc <log>.txt.gz` exposes the original terminal text.

| Gate | Result | Evidence name |
|---|---|---|
| Full covered behavioral suite, 18 xdist work-stealing workers | **6,927 passed, 85.05% coverage; 691.01 s** | `r34-followup-final-04` |
| Full code-quality suite, no coverage | **410 passed; 117.51 s** | `r34-followup-final-04` |
| Ruff check and format; mypy; pyright; exact eight-shard check; import-linter; pre-commit | Passed | `r34-complete-activity-fixture-quality` |
| Action, Indirect and core Stratagem source checks; runtime manifest and generated contract artifacts | Passed | `r34-final-runtime-artifacts` |
| Base-ref contract compatibility; installed-wheel smoke; TypeScript generated client/typecheck/unit tests; cross-language conformance | Passed: 2,636 wheel resources, 27 schemas, six request families, five client tests and 342 conformance assertions | `r34-followup-final-contract-client` |
| Focused final restoration and fixture regressions | 15 passed | `r34-final-focused-freeze` |
| Entire affected shooting declaration module | 233 passed; subsequent private-access type comments separately verified | `r34-shooting-module-final-freeze`, `r34-complete-activity-fixture-quality` |
| Whole scoring fixture module; all Secondary certification and authority consumers | 226 and 112 passed, respectively | `r34-complete-scoring-module-repair`, `r34-all-secondary-action-fixtures` |
| Source, static and live work-count checks | 12 passed | `r34-final-runtime-artifacts` |
| Comparable base/head component and live timing | 98 samples, all required limits passed | `review-repair/budget-validation.json` |

The 233-test runner subsequently exited nonzero on two fixture private-access
Pyright diagnostics; the table does not call that combined runner a pass. Both
narrowly scoped fixture annotations and the complete typing/quality commands
passed in `r34-fixture-final-quality`. No behavioral assertions were relaxed.

Cross-language conformance replay SHA256:
`e1dbd328761732588a3a324778ebc78e43e93e123df5f195787ea44ab06593e4`.
The contract/client run took 307.065 s while an earlier aggregate was running;
this is correctness evidence, not a performance measurement.

Final aggregate commands use the prescribed Node PATH prefix, coverage output
in the task temporary evidence directory, and xdist work stealing. The final complete behavioral suite passed once with coverage, followed by
all code-quality tests without coverage. The bounded combined runner exited zero
in 812.092 s; there were no skipped tests in either suite. `-vv --tb=short` retains named diagnostics; it excludes no test.
The behavior-file inventory is unchanged:
the new shared fixture helper is not a behavioral test module. The exact
`uv run --no-sync python scripts/build_test_shards.py --check --shard-count 8`
check passes and runs again before final publication.

## Performance and limits

[Current repaired-runtime performance](performance/order34/review-repair/README.md)
contains all raw base/head samples, work counts, budgets, calibration, bounded
runner outcomes, traces and a 15-file matching recursive workload-input manifest.
Measurements ran serially on the same provisional Apple M5 Pro / 64 GiB /
macOS 26.6.2 host, Python 3.14.5 and frozen lock, without coverage, profiling or
competing task-owned test workers. Work profiling ran separately. All original
ceilings remain unchanged. The full measurement runner completed in 267.439 s.

Action mean: 0.12001 s versus 0.12494 s base. Added unrestricted, attached-selection
and retained live means: 0.07277 / 0.00422 / 0.21272 s. Original Indirect case
means: 0.12768 / 0.43541 / 0.34639 s. The slowest-case mean remains close to its
unchanged 0.45 s limit; local finite measurements are not a universal guarantee.
The expanded fast CI gate checks live effects, preflight, decision and charge
coverage and bounded named work counts. No speculative cache was introduced.

The separate full attached target-declaration diagnostic exceeded its calibration
150 s deadline. Fresh 30 s probes on final head and base both stopped in the exact
visibility solver; their logs and timeout outcomes are committed. This remains
incomplete evidence, not a completed sample or an invented rules answer. The
attached-selection workload does not replace this diagnostic. The later fixture
audit records two changed turn-end helper functions outside
the measured call paths; all benchmark production and executed helper code is
unchanged, and both checkouts used the same pinned 5b inputs. No solver changes
or extension of the Order 32 deferral were made.

Full-game mean below 60 s and no measured game above 300 s remain **uncertified**.
Historical e57 and 9699 timing/aggregate results do not certify the final runtime.

## Execution, failures and recovery

The existing small runner retains command, checkout, start, deadline, PID, elapsed
time and terminal outcome. Raw local logs remain in
`/private/tmp/order34-evidence/`; relevant review evidence is also committed.
No general orchestration framework was added.

The first follow-up covered aggregate was interrupted after 330.134 s with
failures and incomplete coverage; it did not run the following quality suite.
Signalling its process group also stopped the controller before it could emit a
complete failure summary. Read-only inspection confirmed the owned workers had
exited. The interruption and cleanup records are retained, and no passing result
is claimed. Focused diagnosis found incomplete direct-executor fixtures: their
completed shooting lacked the accepted declaration now required for restoration.
Shared canonical declaration helpers preserve real domain state, actual ledger
records and original combat assertions. Fixed deterministic seeds preserve the
same requested outcomes. A paused declaration helper captures the same historical
origin as the lifecycle before recording its first declaration.

The second covered attempt stopped after 916.988 s with 19 failures, seven
fixture setup errors and 6,642 passes; it is incomplete, failed evidence. Its
`--maxfail=8` stop left two workers draining queued scenarios while sixteen
workers waited. After process inspection, only its verified pytest controller
received SIGINT, retaining the full failure summary and JUnit report. All owned
workers exited. The final run uses normal work stealing without that early-stop
flag and executes without competing local heavy validation processes.

The second fixture audit corrected turn-end expiry, remaining direct executors,
identity-based corruption targets, replay checkpoint setup and a fixed Fight
seed. Plunder scoring now uses an accepted Action through the lifecycle and
keeps its decision history and unrelated unit placements. The final focused
secondary/restoration run passed 53 tests; earlier passing corruption and adapter
persistence cases remain in the 74 passes of the preceding repair run, whose
nine then-failures are explicitly retained. The complete static command chain
subsequently passed in 44.548 s. Production source did not change.

The third covered attempt completed all 6,927 tests: 6,921 passed and six failed
in 989.28 s, with 85.04% coverage (992.436 s runner wall time). The following
quality suite was not run because behavior failed. Its two remaining direct
executor fixtures and four Cleanse cases were repaired as complete fixture
families, with 226 scoring-module tests and all 112 Secondary certification and
authority tests passing. The shared Action fixture now submits both Cleanse and
Plunder through the lifecycle; the old synthetic completed-Action builder was
removed. Complete static validation passed in 50.765 s. No production change
occurred after the original R34-002 repair.

Earlier focused failures and subsequent passing repairs are retained by name.
There are no broad exception fallbacks, integration mocks, omitted tests or
weakened restoration checks. The initial implementation's failed historical
aggregates remain in prior Git history and the raw runner directory.

Automatic approval review initially rejected one scoped publication attempt
because authorization and destination were not recognized. The original explicit
PR publishing instruction and configured SobolGaming remote were re-verified;
the same scoped retry was approved and published. This is resolved, with no
remaining permission blocker or request for user intervention.

## Publication and CI

The owner explicitly authorized draft publication after focused checks, before
aggregate validation. Required local gates now pass on the final candidate.
Draft CI on `53330070` passed lint, both type checkers, source semantics, code
quality and contract conformance, but skipped behavioral shards and coverage.
The [draft snapshot](performance/order34/followup-validation/r34-final-draft-ci.json)
retains that distinction. Marking the final evidence head ready triggers full CI.
Its exact-head CI status is recorded in the PR body and the stable review replies
at handoff; a pending or skipped lane is never described as passed. No merge or
self-approval occurs.

## Elapsed time

Task work began approximately 2026-09-09 14:43 UTC. Review repair began around
16:49 UTC. The initial implementation handoff recorded approximately 125.5 minutes
through 16:48:31 UTC: 51 minutes implementation/source work, six focused tests,
25 author review/repair, 41.5 aggregate validation/performance/generation and two
publication preparation. Those allocations are estimates, not stopwatch data.

The follow-up repair interval includes diagnosis, canonical fixture corrections,
focused tests, generation, typing, performance, publication and final aggregates.
Per-command metadata supplies exact durations; overlapping command durations
must not be added as elapsed time. Final handoff records total elapsed time and
separates any bounded CI wait. There was no dedicated wait for independent review
and no additional user intervention was required to execute the repairs.

Through local evidence preparation at **2026-09-09 20:32:49 UTC**, total elapsed
wall time was approximately **5 h 50 min**. The follow-up interval was 223.6 min.
Its non-overlapping clock allocation is 129.7 min review/repair/documentation/
publication, 8.9 min focused test execution and 85.0 min aggregate validation,
generation, quality and performance. There was zero dedicated external wait in
that interval. Running aggregate commands take precedence when activities overlap;
these are wall-clock allocations, not exclusive effort or CPU time. The initial
125.5-minute estimate above is separate, with about 40 seconds between handoffs.
Any later bounded CI wait is reported separately in the final PR handoff.

[Machine-readable final evidence](performance/order34/review-handoff-evidence.json)
records exact command intervals, result counts, coverage, source/test identities,
all final artifact hashes and the allocation method. Large final logs and both
JUnit reports are retained losslessly beside their terminal metadata.
