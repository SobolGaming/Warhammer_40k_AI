# R34-002 sequence-origin repair

PR: https://github.com/SobolGaming/Warhammer_40k_AI/pull/438
Base: `e56c1a4caf2a6915548222caed0872627f8dbf43`.
Reviewed head: `1ea77b9697e0edc94a0edb4d7d694ea904c0af19`.
[Independent finding](https://github.com/SobolGaming/Warhammer_40k_AI/pull/438#discussion_r3974026147).
R34-001 and R34-003 remain independently closed. R34-002 requires exact-head
independent re-review after this correction. No merge or Order 34 closure is claimed.

## Invariant and reproduction

A completed shot retains its Action prohibition until its actual phase ends.
An asserted attack kind, sequence ID or model list cannot exclude a completion
from authentication. The prior implementation filtered history before binding
its origin; changing both kind and sequence hid a completion while leaving the
accepted shooting declaration looking like an unfinished executor prefix.

The new Normal and Snap regressions reproduced this defect on 1ea77b96: both
failed with DID NOT RAISE after renaming participation/completion together,
labelling them fight, and removing the matching completed-shooting effect.
All accepted declarations, decision records, ranged activations, model ownership,
actual timing and ordinary shot state were unchanged. Untouched JSON restoration
still reported `mission_action_unit_already_shot` before each mutation.

## Repair and scope audit

The existing model-attack history owner now authenticates the complete event
inventory before classification. Every participation matches its preceding
accepted shooting, out-of-phase shooting or melee declaration. Every executor
completion/resolved boundary needs that declaration and participation; orphan
and duplicate completion identities fail closed. No asserted kind, model list
or sequence ID selects which events reach this validation.

Melee classification additionally binds to its original typed request/result,
exact preceding decision ledger closure, proposal, game, round and deterministic
sequence identity. A fabricated melee declaration cannot establish a different
origin for completed shooting. Genuine melee and accepted unfinished executors
remain valid. Ordinary already-shot state stays independently enforced.

The bug-class search covered all `MODELS_ATTACKED_EVENT_TYPE` and completion
consumers. Historical Action-request reconstruction had a related subject filter
and now validates its whole prior event prefix through the same shared owner.
Retained-subject history validation reuses the same implementation and preserves
its specific subject query; complete lifecycle restoration always authenticates
the unfiltered inventory before accepting the state. Live eligibility reads the
existing indexed effects and does not scan history.

Only two production modules change: `model_attack_history.py` and
`activity_restriction_history.py`. No new ledger, decision, public payload shape,
source package, runtime hook, cache or architecture boundary is added. Generated
runtime/contract identities are refreshed and the existing adapter contract
explicitly states the provenance requirement. No behavioral test file is added,
deleted or renamed; shard membership is unchanged.

The Normal/Snap matrix covers 30 corruptions per route: fight/movement labels
with original or renamed sequences, a renamed shooting-kind control,
unchanged/empty/foreign models, and removed/retained effects. The real retained
melee path restores every partial checkpoint and rejects coordinated declaration/
participation changes to sequence, models, active player, game, round, phase and
request authority. Orphan and duplicate completions are tested from real events.
The static audit requires unfiltered history validation before classification
and shared use by historical Action reconstruction.

## Validation status

Final tested candidate: `1a549efec35a36454efd2bf091f88059623b8bf2`.
Measured production candidate: `909bced7d5d053282f3887821cb6ce0fcbaa5252`.
Shared production tree: `bb239fac9970d7a9a0ba46f94ff23ad87dfe62f2`.
Final test tree: `8903414e18094e23680e95b9d01647788c0558bc`.
Runtime: `warhammer40k-core-v2:runtime-tree-sha256-v1:ac34d042332ffbf63e8b2b1d666767a62c2f2763f7aa573b57c1a240ef643cc3`.
The later evidence-only publication commit preserves these trees and benchmark inputs.

| Gate | Result |
|---|---|
| Original focused repair matrix | 41 passed; 104.70 s |
| Broader Fight/retained regression gate | 157 passed; 25.19 s |
| Final Normal/Snap controls | 2 passed; 8.09 s; 30 corruptions per route |
| Three corrected fixture modules | 148 passed; 37.47 s |
| Complete behavioral suite with coverage | **6,928 passed; 85.05% coverage; 504.88 s** |
| Complete code-quality suite, without coverage | **410 passed; 110.40 s** |
| Ruff check/format, mypy, pyright, exact eight-shard inventory, import-linter, pre-commit | Passed on the final fixture tree |
| Action, Indirect and core Stratagem source checks; runtime identity and external contract compatibility against the exact base | Passed |
| Installed-wheel smoke | Passed: 2,636 resources, 27 schemas, six request families |
| Generated TypeScript client/typecheck and client unit tests | Passed; five tests |
| Cross-language conformance | **342 assertions passed**; replay SHA256 `e1dbd328761732588a3a324778ebc78e43e93e123df5f195787ea44ab06593e4` |
| Current-runtime performance | **98 timings and eight separate work profiles; all unchanged budgets passed** |

Both final aggregate suites have zero failures, errors or skipped cases. Behavioral
execution uses 18 xdist work-stealing workers with the required Node PATH and branch
coverage gate. It is followed by code quality without coverage. No second uncovered
full behavioral run was added. The existing SQLite ResourceWarnings do not fail
the suites. Source/contract/client/package validation passed before the test-only
fixture correction; its production and contract trees are identical to the final
candidate. The exact static and aggregate commands and outcomes are preserved.

[Machine-readable outcomes and 70 artifact hashes](performance/order34/review-sequence/handoff-evidence.json)
and [complete runner logs/JUnit](performance/order34/review-sequence/validation/) identify
every tested tree and terminal result. Aggregate logs and JUnit are retained
losslessly as gzip files. [Performance evidence and reproduction](performance/order34/review-sequence/README.md)
retain all seven workloads, 15 pinned input hashes, raw samples and unchanged budgets.
The largest head/base mean ratio is 1.05798. Full attached-declaration historical
timeouts remain incomplete diagnostics; the unchanged solver was not rerun.
Full-game mean below 60 seconds and no measured game above 300 seconds remain
uncertified. No Order 32 exception is extended.

The first covered aggregate completed all 6,928 tests: 6,922 passed and six
existing Fight fixture cases failed with `Model attack history lacks its declaration`.
Coverage was 85.05%; the subsequent code-quality command did not run after the
failed behavioral gate. The failure log and JUnit remain separate evidence.

Those three test modules constructed post-attack melee executors without the
accepted declaration prefix now required by restoration. The shared canonical
executor fixture helper now builds and records the typed melee request, proposal,
result and matching declaration before execution. The fixtures use the engine's
deterministic sequence identity; the deferred mortal context and existing
sequence assertion follow that identity. The adapter fixture explicitly retains
its initial replay snapshot, as required when setup includes a recorded decision.
Real facade-driven Normal, Snap, retained shooting and retained-melee corruption
regressions remain the repair's behavioral authority. No production check was
weakened to accommodate these fixture histories.

These corrections are test-only. They do not alter the measured runtime,
contracts, source packages or any of the 15 pinned benchmark inputs. The final
covered gate is rerun on the corrected test tree; the first failure is not
presented as a passing aggregate.

## Execution and handoff

The existing bounded task runner was reused. No command timed out, no task-owned
process required forced termination, and no user intervention was needed. Two
shell-quoting invocations were rejected by argument parsing before command launch;
they caused no mutations. Focused iteration corrected a regex literal and formatting.
All nonzero outcomes, including the first full aggregate and fixture iterations,
remain separately recorded. Passing gates are not inferred from printed progress:
the runner's terminal exit was consumed for each completed execution.

At evidence collection the follow-up elapsed **40.98 minutes**:
11.65 review/repair/documentation,
3.73 focused tests/generation, and
25.61 aggregate/static/contract/performance gates.
There was no dedicated external-review wait or user pause. These are non-overlapping
wall-clock allocations, with aggregate commands taking precedence over overlapping
work, rather than CPU or exclusive effort measurements. Publication and bounded CI
observation happen afterward and are reported in the PR handoff.

The PR body and R34-002 thread record the exact published head, current CI snapshot
and independent re-review request. The prior reviewed head's full CI finished green
in run 34416966519; that does not certify this new head. A pending CI lane remains
pending. R34-001/R34-003 remain independently closed; this author repair does not
independently close R34-002. No merge or Order 34 completion is claimed.
