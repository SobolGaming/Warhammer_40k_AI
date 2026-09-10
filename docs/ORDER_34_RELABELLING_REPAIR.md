# R34-002 completed-shooting relabelling repair

The subsequent R34-002 sequence-identity correction and current validation are in
[the sequence repair report](ORDER_34_SEQUENCE_REPAIR.md). This report is historical.

PR: https://github.com/SobolGaming/Warhammer_40k_AI/pull/438

Base: `e56c1a4caf2a6915548222caed0872627f8dbf43`.
Reviewed head: `29c6cdc0b3afc6c4360d8ebb9043f5c964d6afc8`.
Measured repair candidate: `bf9bd4225fd135ff59c17bbaa7d1c08b6c32b4a5`.
Final behavioral candidate: `3bcafa83a745c032355865708bda21078cd2f3f4`.
Production tree: `3a8cf3a2979f54251538cb204c2d86cca41f0726`.
Final test tree: `78d79818555076f1ddd9fb31811357c79c44c163`.
Engine runtime: `5a5378bf4bcfdc69a49e723c4a9e1fe5237a08019dbae5b0a383b1e38608ce65`.
Later evidence-only commits preserve the tested and measured trees.

The [independent review](https://github.com/SobolGaming/Warhammer_40k_AI/pull/438#issuecomment-5608799989)
left R34-002 open and closed R34-003; R34-001 remains closed. All eight behavioral
shards, combined coverage and quality lanes passed on the reviewed head in
[run 34401994629](https://github.com/SobolGaming/Warhammer_40k_AI/actions/runs/34401994629).
That CI result does not validate this subsequent repair.

## Invariant, reproduction and scope audit

A completed shot must retain its Action prohibition until the actual phase end.
Restoration must authenticate attack kind and subjects against the accepted
shooting declaration before classifying the completion. An asserted kind or
model list cannot remove that declaration from the validation inventory.

The review's coordinated mutation was reproduced through real Normal and Snap
shooting: change participation `attack_phase` to `fight`, remove the matching
completed-shooting effect, and leave the accepted declaration, decisions, ranged
activation, actual phase and ordinary shot state intact. Both regressions failed
with **DID NOT RAISE** on 29c6cdc0. Untouched JSON restoration and the original
`mission_action_unit_already_shot` eligibility were verified first. The earlier
test-ordering attempt reached the retained-effect case first and failed its
expected diagnostic; it is retained separately and is not the bypass evidence.

The production correction changes only `engine/model_attack_history.py`:

- Sequence IDs come from the union of accepted shooting declarations and asserted
  shooting participation. This preserves rejection of undeclared completion pairs.
- Model IDs come from both declarations and participation. Empty or foreign
  participation models cannot disable the existing shared history validator.
- The existing validator binds kind, subject, models, timing and declaration order;
  existing decision-ledger and ranged-activation checks remain authoritative.

The bug-class search covered every `attack_phase` classification in activity
restoration. `activity_restriction_restore.py` authenticates this complete history
before filtering or rebuilding effects. Historical Action-request reconstruction
in `activity_restriction_history.py` already validates the full prior event prefix
against all original model owners before filtering. Retained destruction uses the
same declaration-binding validator. No alternate mutation path, ledger, fallback,
cache, decision family, source package or architecture boundary was introduced.
The adapter contract now explicitly records the two-sided inventory requirement.

The new shared assertion runs both kind mutations (`fight`, `movement`), with
unchanged/empty/foreign model IDs and with/without effect removal: 12 corruptions
per real shooting route. It checks unchanged decision records, ranged activation
and ordinary shooting state. Genuine melee, accepted partial-executor checkpoints,
the original missing/extra/retimed/foreign cases, and retained Action/TITANIC
behavior remain in the focused gate. Existing persistence, exact replay and
both-viewer regressions are retained.

The final scope audit found one changed production function and its regenerated
runtime identity/contract examples. The 77-line shared assertion is test-only;
no behavioral test file was added, deleted or renamed. The exact eight-shard
inventory check passes. Existing budgets and benchmark drivers are unchanged.

## Validation and performance

The focused gate passed **40 selected tests** in 93.96 s. Ruff/format, mypy,
pyright, shard inventory, import-linter and pre-commit passed. Runtime identity
and external contract artifacts were regenerated before those focused tests.
Final results and all 50 artifact hashes are recorded in the
[machine-readable handoff evidence](performance/order34/review-relabel/handoff-evidence.json)
beside the [complete runner logs](performance/order34/review-relabel/validation/).

| Final gate | Result |
|---|---|
| Complete covered behavioral suite, 18 xdist work-stealing workers | **6,928 passed, 85.05% coverage; 764.68 s** |
| Complete code-quality suite, without coverage | **410 passed; 126.63 s** |
| Ruff/format, mypy, pyright, exact shard inventory, import-linter, pre-commit | Passed after the final test-only correction |
| Action, Indirect and core Stratagem source checks; runtime and external contract checks against e56c1a4c | Passed |
| Installed-wheel smoke | Passed: 2,636 resources, 27 schemas, six request families |
| Generated TypeScript client and type checks, five client unit tests | Passed |
| Cross-language conformance | **342 assertions passed**, replay SHA256 `e1dbd328761732588a3a324778ebc78e43e93e123df5f195787ea44ab06593e4` |
| Comparable timing and separate work profiles | **98 timings, eight profiles; all unchanged budgets passed** |

Both final aggregate suites have zero failures, errors or skipped cases. The
bounded runner exited zero after 894.025 s; the full behavioral suite was not
repeated without coverage. Complete terminal output and both JUnit reports are
retained losslessly as gzip files. The 10 existing SQLite ResourceWarnings did
not fail validation. Source, contract and package validation completed in
161.460 s, overlapping the first aggregate; it is correctness evidence, not timing.

The first covered aggregate completed all 6,928 cases with 6,927 passes and one
failure, at 85.05% coverage. A corruption test expected the later pending-destruction
boundary diagnostic, but the expanded declaration inventory now rejects its
forged completion earlier with `Model attack history is missing its completed attacks`.
An isolated reproduction confirmed that exact typed rejection. Only the expected
diagnostic string changed; the same invalid checkpoint must still fail and its
valid pre-boundary restoration remains covered. The following quality suite did
not run after that failed behavior gate. Final validation reran the covered suite
and then code quality; no uncovered full behavioral run was added. Production and
benchmark inputs are unchanged by this test-only correction.

Fresh performance evidence for this repair is in
[review-relabel](performance/order34/review-relabel/README.md). It uses the same
seven workloads, unchanged versioned budgets and 15 identical recursively
discovered driver/helper/lock inputs on the exact base and candidate. Timing runs
serially without coverage, profiling or competing task-owned validation workers;
work profiles are separate. No later helper exception is needed for these inputs.

The prior independently audited timing set remains in `review-repair` and is
historical evidence for 29c6cdc0. Its full attached-declaration timeout traces
remain incomplete diagnostics; the unchanged visibility solver was not rerun
through that known stall. Attached selection remains a distinct workload.
Full-game mean below 60 seconds and no measured game above 300 seconds remain
uncertified. This correction does not extend the Order 32 performance deferral.

## Execution and handoff

The existing bounded runner was reused without changing its implementation.
Raw logs and terminal metadata are retained under `/private/tmp/order34-evidence/`
with the `r34-round4-` prefix. Committed evidence retains the reproduction failures
separately from passing repair gates. No user intervention, process interruption
or timeout was required for the reproduction or focused repair. Timing and
correctness executions are not conflated.

The user paused the task after the final aggregate was launched. That runner
continued and exited normally at **21:50:57 UTC**. On the user's `continue`, its
terminal result was consumed successfully; no lost completion event, orphaned
runner or duplicate validation was reported by the runner. The completed suites
were not restarted. Read-only process inspection was unavailable in the default
sandbox, so the successful runner cleanup record and consumed process exit are
the completion evidence.

From the first logged review fetch at **21:12:58 UTC** through evidence collection
at **23:24:43 UTC**, elapsed wall time was 131.75 minutes. This includes **92.78
minutes inactive after validation**, before the resumed status check. The remaining
38.97 minutes allocate 9.44 to review/implementation/documentation/publication
preparation, 1.74 to focused tests/generation, and 27.79 to aggregate, static,
contract and performance gates. These non-overlapping clock allocations give
aggregate commands precedence when work overlaps; they are not exclusive effort
or CPU time. Later publication and bounded CI observation are reported in the PR
handoff separately. No indefinite background monitor was created.

Final exact-head CI status, the published SHA and the re-review request are
recorded in the PR body and R34-002 thread. A pending CI lane is not a pass.
This is an author repair and validation report, not independent approval.
No merge or Order 34 closure is claimed.
