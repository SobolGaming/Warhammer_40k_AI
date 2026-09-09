# Order 34 validation and review handoff

**Independent review repair in progress:** R34-001, R34-002 and R34-003 were
received on 2026-09-09. The evidence below records the previous runtime and is
historical; production fixes invalidate those aggregate results for the new
candidate. Repaired-head correctness, contract, performance and full CI results
will replace this status after validation. The PR remains a draft meanwhile.

PR: https://github.com/SobolGaming/Warhammer_40k_AI/pull/438

Base: `e56c1a4caf2a6915548222caed0872627f8dbf43`.
Final runtime/test candidate: `e57e8be02aa744354d8d078a78be39024ab44643`.
Later evidence-only commits preserve these tested trees:

- `src`: `2aa39af0b7af29bd00da3019c2b0f3f7022aa50b`
- `tests`: `39119009c322eee1ea31d35f1fc685108040b2dd`
- Engine build: `warhammer40k-core-v2:runtime-tree-sha256-v1:bb89e0f65e9aa2a8cd6673646296de4b42c373446b5029d2da1734fee1738322`

The source/owner/consumer/regression matrix and scoped architecture are in
[ORDER_34_SCOPE_PLAN.md](ORDER_34_SCOPE_PLAN.md). Source artifacts retain complete
operative wording, immutable observations and partial execution classifications.
Actions, Normal/Assault/Close-quarters shooting, and the retained Indirect/Snap
clauses use source-linked activity descriptors. This does not certify unrelated
source-package clauses or future Orders.

## Correctness evidence

The preceding `9558014e` behavioral suite passed 6,903 tests with 85.05% coverage
in 628.49 s. Its full code-quality run found one direct effect-list assignment
(402 passed, one failed). The helper now uses the existing
`GameState.remove_persisting_effects_by_id` method; the audit remains unchanged.
Focused mutation/source/work audits passed 12 tests, and both historical-shot
regressions passed. The repaired `e57e8be0` candidate passed the complete covered suite: **6,903 tests, 85.05% coverage**, and all **403 code-quality tests** without coverage.

| Gate | Final candidate result | Runner log under `/private/tmp/order34-evidence/` |
|---|---|---|
| Covered behavior, 18 xdist workers | 6,903 passed; 85.05% coverage | `candidate-e57-behavior-coverage.log` |
| Full code-quality, no coverage | 403 passed | `candidate-e57-code-quality.log` |
| Ruff check/format, mypy, pyright, shard inventory, import-linter, pre-commit | Passed; mypy 2,817 files; pyright zero errors; 11 import contracts kept | `candidate-e57-quality-tools.log` |
| Source generators: Actions, Indirect, core Stratagem App source | Exact checks passed | `candidate-e57-source-generation.log` |
| Build identity, base-ref contract compatibility, installed-wheel smoke | Passed against the exact base; 27 schemas and six request families | `candidate-e57-contract-client.log` |
| TypeScript generated client, typecheck, unit tests and conformance | Five unit tests and 342 conformance assertions passed | `candidate-e57-contract-client.log` |
| Focused source/static/work-count checks | 12 passed, plus two historical-shot regressions | `mutation-owner-focused-and-generation.log` |
| Comparable component and shooting timing budgets | All passed; no threshold changes | `candidate-e57-performance.log` |

The cross-language conformance replay SHA-256 is
`e1dbd328761732588a3a324778ebc78e43e93e123df5f195787ea44ab06593e4`.
[Machine-readable execution evidence](performance/order34/execution-evidence.json)
retains commands, exact outcomes, start/deadline/elapsed values and log hashes.

Focused evidence includes the source-derived Action/TITANIC matrix, actual
turn-end cleanup, all five shooting types, Snap in the opponent's Movement phase,
stale unit/type/declaration rejection before queue pop, forged payload rejection,
current retained-component keywords, unrelated-unit isolation, exact replay,
standalone restoration, JSON session persistence and both-viewer projections and
events. Historical Primary Mission start/decline/pending validation rebuilds the
activity inventory at its exact authenticated checkpoint. A regression preserves
prior completed shooting even after the live effect expires.

The final commands use xdist work stealing. The Node runtime prefix is present
for executable viewer tests. `COVERAGE_FILE` points into the task evidence
directory; this changes only the coverage output location. No uncovered second
full behavioral run is used. The behavioral shard file inventory is unchanged;
the exact eight-shard check was run before each commit and will run before the
final publication.

## Performance evidence

[The performance report](performance/order34/README.md), raw timing/work JSON,
matching workload hashes and [budget validation](performance/order34/budget-validation.json)
are committed under `docs/performance/order34/`. All 56 base/head timed samples
completed. The final Action mean is 0.1146 s versus 0.1130 s base (+1.41%).
Shooting means are 0.1181 / 0.4129 / 0.3260 s (-0.53% / +0.98% / +0.66%).
The earlier candidate's 0.4493 s unseen/no-observer mean is retained in the logs. No sample
or hard case was dropped; all timing and CI work budgets passed.

These are component and one-attack gameplay-slice results on a provisional
Apple M5 Pro host. Full-game mean below 60 s and no measured game above 300 s
remain uncertified. Order 32's deferral is not extended.

## Process evidence and recovery

The reused runner and per-command terminal JSON/logs remain at
`/private/tmp/order34-evidence/`. Each tracked command records start, PID,
deadline, exit outcome and elapsed time. Success, nonzero and timeout behavior
were verified once. The system Python lacked `datetime.UTC`; the repository
Python ran the existing mechanism. Initial ordinary source fetching returned
403; approved-mirror inspection completed through a normal browser session.

The first covered aggregate run on `f18ffe1d` ended with 19 failures and 6,882
passes after 539.6 s, then a coverage save error caused exit 3. It is failed,
incomplete coverage evidence. Failures exposed current effects leaking into
historical checkpoints, two missed exact source pins, and two obsolete fixtures.
Those were repaired as one scope, followed by focused regression and type checks.
Coverage's repository-root file rename returned `PermissionError`; a two-worker
covered preflight successfully wrote and combined data in the temporary evidence
directory before the required full rerun. No production fallback, test exclusion,
worker-mode relaxation or permission-policy change was introduced.

Discovery errors, malformed initial shell quoting, stale generated manifests,
and failed focused attempts remain in the logs. Completed process results were
consumed. Process inspection showed active pytest workers rather than an input
prompt. Only the deliberate runner timeout preflight required termination of
task-owned processes. No user intervention or independent review repair occurred
during implementation.

## Publication and outstanding review

The owner-authorized timing exception published a clearly labeled draft after
focused tests passed, before aggregate validation. The initial draft was
`71c66bab`; `f18ffe1d` fixed selection preflight and type findings; `9558014e`
fixed historical checkpoint reconstruction; `e57e8be0` uses the required GameState
mutation API. These are the author's findings,
not independent approval.

Draft CI skips behavioral shards and coverage. Once required local validation
passes, marking ready triggers those lanes. The exact final CI snapshot and
elapsed-time breakdown are recorded at handoff. Independent ChatGPT review is
owner-initiated and outstanding. This task does not merge or self-approve the PR,
and Order 34 is not represented as fully closed.

## Elapsed time

Approximately 125.5 minutes through evidence preparation at 2026-09-09T16:48:31.266435+00:00.
Phase allocation estimates: 51 minutes implementation/source work, six minutes
focused test execution, 25 minutes author review/repairs, 41.5 minutes aggregate
validation/performance/generation, and two minutes publication/handoff preparation.
Parallel command durations overlap; exact starts, deadlines and wall durations are
in the execution JSON and complete runner directory. There was no dedicated wait
for external review or CI and no user intervention. The final covered run took
598.57 s (601.181 s runner wall time); final code-quality took 118.13 s
(118.713 s runner wall time). Ten SQLite ResourceWarnings were emitted by the
behavioral suite; all tests passed.
