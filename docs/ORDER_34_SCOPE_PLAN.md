# Order 34 / P16 / C16-01 and C16-02

Base: `e56c1a4caf2a6915548222caed0872627f8dbf43` (origin/main on
2026-09-09). PR #437 is merged; its R33-001 engagement correction and R33-002
exact source inventories are present. PR #436 contains R32-001's retained
observer correction. The initial checkout was clean. Work uses
`codex/order-34-action-restrictions`.

The subsequent R34-002 checkpoint relabelling correction and its focused
bug-class/scope audit are recorded in [the repair report](ORDER_34_RELABELLING_REPAIR.md).
It preserves this acceptance matrix and the independently closed R34-001/R34-003 findings.

## Acceptance matrix established before implementation

Complete operative 16.01, 10.02, 10.04–10.07 and 15.09 were read directly
at the approved 40k.app maintained mirror on 2026-09-09. No App version was
displayed. The initial web fetch returned 403; ordinary browser verification
completed and exposed the source pages. No co-version agreement with Game
Datamissions is claimed. Historical observations and official PDF evidence
remain immutable. The retained Order 33 10.07 wording includes the same
after-shooting Action clause.

| Source clause / invariant | State owner and consumers | Regression |
|---|---|---|
| 16.01: accepting an Action start prevents shooting until turn end, excluding TITANIC units | Existing GameState persistent effects, shared shooting eligibility and declaration preflight, reaction/Stratagem eligibility | Accepted start versus declined/invalid request; ordinary and out-of-phase shooting |
| 16.01: accepting an Action start prevents all charge declarations until turn end | Same Action effect and shared charge eligibility, including reaction charge validation | TITANIC and non-TITANIC; stale declaration; independent permissions |
| Completion, failure and cancellation do not alter the stated restriction duration | Existing exact EffectExpiration boundary service, independent of MissionActionStatus | Immediate/phase completion, interruption and turn boundary |
| 10.04–10.07 and 15.09: after shooting, Action starts are forbidden until phase end | Shared completed-attack boundary records a phase effect; Action enumeration and preflight consume it | Normal, Assault, Close-quarters, Indirect, Snap and supported reaction shooting |
| 10.02: ordinary selection/already-shot restrictions remain independent | Existing ShootingPhaseState plus shared Action restriction | TITANIC exception or Action-effect expiry cannot enable a second activation |
| Expiration is the actual round, active player and phase/turn occurrence | Existing EffectExpiration with explicit active-player identity | Wrong boundary, later same-named phase, alternating players, pending reactions |
| Current keyword authority includes retained models; restriction target lineage persists through component loss and separation | RulesUnitView model keywords and existing persistent-effect target lineage | Heterogeneous attached unit, retained TITANIC component, cleanup, separation and unrelated unit isolation |
| All producers and consumers share deterministic authority | Existing lifecycle, LocalGameSession, persisted effects and event log | Standalone lifecycle restore, JSON session persistence, exact replay and both-viewer projections/events |

Starting an Action means accepting its validated start decision, including an
immediately completed Action. Merely offering or opening a request is not a
start. "After shooting" is the shared completed-attacks boundary, before
after-shooting reactions; declaration alone is not completed shooting. The
existing declaration history remains distinct. Current TITANIC qualification
uses rules-present model keywords when eligibility is queried; a dead model
without retained authority supplies no keyword.

The implementation reuses persistent effects and exact expiry, rather than
creating a second activity ledger. Later Snap/Overwatch timing, critical-hit,
Heavy, and Firing Deck obligations remain outside this Order.

The stale-request regression additionally exposed Shooting-unit selection
rejecting a newly illegal unit only after queue pop. Shooting preflight is now
extracted from the frozen lifecycle module and validates current finite options
before recording. Type selection, declarations and charge selection already
have that preflight path. The new regression covers unit, type and declaration
checkpoints with unchanged state, queue, records and resources on rejection.
The existing Order 33 work budgets still pass without threshold changes.

Fixture updates replace manually populated ordinary shot flags with actual
LocalGameSession shooting. The Stratagem fixture's direct phase advancement now
emits its existing Objective Control boundary before its scoring checkpoint;
this is needed for strict standalone restoration and does not change runtime
scoring. Attached Action assertions now distinguish the next player's turn
when the facade automatically completes the starting player's activations.

The first aggregate run exposed a required historical consumer: Primary Mission
checkpoint reconstruction inherited current activity effects. The shared
reconstruction path now rebuilds these effects from authenticated prior Action
uses and the exact completed-attack event prefix, using the same effect builder.
Accepted-start, declined-opportunity and pending-request integrity all consume it.
An added regression restores earlier completed-shooting eligibility after the
current effect expires, and verifies that reconstruction does not mutate current
state. The existing coordinated shooting-history forgery now completes its real
attack sequence and erases the new activity effect as part of the tested forgery.
Its deterministic declaration ID gives a no-damage outcome so unrelated damage
anchors do not precede the intended historical-inventory rejection.

## Execution and publication

The Order 33 runner was reused at `/private/tmp/order34-evidence/run.py`.
Success, exit 7, and process timeout/termination were verified. The system
Python lacked datetime.UTC; the repository Python runs the unchanged mechanism.
Commands retain individual logs and terminal JSON records with PID, start,
deadline and elapsed time. Discovery failures are retained as failures.

The owner explicitly authorized early DRAFT publication after reviewable
implementation and focused regressions, before aggregate gates. This exception
changes publication timing only. Full local gates, ready-for-review CI and
independent review remain mandatory; the PR will not be merged by this task.

Performance assessment uses the current standing policy, not the Order 32
deferral. Full-game mean <60 seconds and maximum <=300 seconds remain
uncertified unless directly measured.

The full code-quality gate additionally required the reconstruction helper to
remove effects through `GameState.remove_persisting_effects_by_id`, rather than
assigning the reconstructed state's list directly. The owning API is now used;
the gate is unchanged. The resulting production edit requires a fresh covered
behavioral run and full code-quality run, despite the preceding 6,903-test pass.

## Independent review repairs

The review of `e57e8be02aa744354d8d078a78be39024ab44643` raised three stable
findings. The earlier passing aggregates do not validate the repaired runtime.

| Finding | Violated invariant and owning repair | Regression/evidence |
|---|---|---|
| R34-001 | A retained Shoot On Death choice could bypass Action restrictions until after parent-host mutation. The shared retained option producer, pre-pop validator and execution guard now use the common Action query; the strict retained payload records excluded actions. | Real Cleanse → parent shot → nested source-backed For the Chapter! shots; TITANIC and non-TITANIC, unavailable/forged and stale shoot choices, preserved fight/decline, checkpoint restoration and exact replay. |
| R34-002 | Individually valid effects could be removed, retargeted or retimed during standalone restoration. A dedicated restoration module derives the complete live inventory from accepted Action decisions, completed attack history and actual expiry boundaries, then requires exact equality. | Missing/extra/retargeted/retimed Action and completed-shot inventories, including owner/round drift; existing no-damage, out-of-phase, attached and retained consumer regressions. |
| R34-003 | The original fast work gate measured a blocked unit, missing unrestricted selection and broad live consumers. Additional comparable workloads exercise legal unit selection/preflight, 32 live effects, completed shooting, charge transitions, attached selection and retained reactions. | Versioned per-case work ceilings, base/head raw counts and separate uninstrumented timing; original component and difficult Indirect cases retained. |

The bug-class search covered both ordinary and retained shooting selection,
source alternatives, prevalidation, parent continuation, and all activity restore
consumers. No named handler, source parsing, cache, competing activity ledger,
geometry algorithm or adapter-specific mutation path was added. The frozen
lifecycle module delegates restoration to the new owner. Historical checkpoint
and live inventory reconstruction reuse the same effect builder and existing
boundary decoder. Fixtures that manually invented Action state now submit real
Action decisions; deterministic Hazardous seeds preserve their original outcome
assertions after the retained request hash changes.

The full attached target-declaration diagnostic stalls in the exact visibility
solver on both base and repaired code. Both deadline outcomes and stack traces
are retained; they are incomplete measurements, never legal/illegal answers.
The separate bounded attached-selection workload has its own workload ID and
stops at the real shooting-type request. Full-game certification remains open.

The new calibration exposed repeated all-unit target checks during finite
selection. Preflight and application now restrict the existing legality function
to the selected placed unit, preserving all current checks. Completing the phase
still enumerates the full skipped-unit inventory for payload validation. This
reduces attached-selection line-of-sight calls from 57 to nine without caching
or weakening stale-request validation; the base makes 30 such calls.


### Follow-up R34-002, reviewed head 9699f8f8

The follow-up review closed R34-001 and demonstrated that copying an undeclared
participation/completion pair plus its effect into an unactivated session still
passed inventory reconstruction. The same retimed pair reproduced locally.
The violated invariant remains provenance of the reconstructed activity, not
just consistency between two asserted events.

Every reconstructed shooting completion now retains the accepted declaration,
its exact requested/recorded decision closure, original ranged-attack record,
unit, contributing models, and round/turn/phase. The previous implicit executor
baseline exemption is removed. Real mid-executor checkpoints retain the original
declaration prefix and continue to restore; focused post-attack fixtures now
retain that canonical typed declaration ledger instead of creating incomplete
completion-only histories. Common fixture setup is shared. No alternate runtime
ledger or hot eligibility history scan is introduced.

The regression matrix retains the original inventory mutations and adds fresh
unactivated-session copied pairs, foreign games, retimed pairs, a copied but
unaccepted declaration, missing/retimed ranged activation records, and coordinated
foreign-model declaration/participation drift. Valid mid-executor, completed,
retained and exact-replay checkpoints are checked alongside those mutations.
The source change is limited to the existing model participation validator and
its restoration caller; fixture changes preserve the prior outcome assertions.
The 98 passing timing samples for 9699f8f8 are retained under
`docs/performance/order34/review-9699/`; they do not certify this later runtime.


The aggregate exposed further direct-executor fixtures missing their accepted
prefix. Three now retain the shared typed declaration ledger. The retained-target
fixture now obtains a real finite selection/type request and a legal declaration,
with an in-range, unengaged initial firing position. Its target geometry and damage
assertions are unchanged. The existing helper that deliberately pauses before
attack dice also retains the lifecycle's real pre-declaration origin. Its two
private-field accesses are confined to fixture setup and documented locally;
no production API or runtime validation exception was added. All 233 tests in
the complete affected shooting module passed after these fixture repairs.
The interrupted aggregate is explicitly incomplete; its workers exited and
process-group cleanup was verified before subsequent runs.

### Final aggregate fixture audit

The stricter restoration authority exposed additional incomplete historical test
checkpoints. Direct destruction and deferred mortal-wound fixtures now retain
accepted shooting declarations and matching phase history through the existing
shared executor helper. Turn-end fixtures call the owning expiry API. Plunder
scoring fixtures submit a real Action before their scoring checkpoint, keep its
DecisionController and preserve unrelated scoring placements. Materialization
corruption cases select the intended request/result by identity instead of
assuming it is the first decision. The adapter mortal-wound fixture explicitly
pins its initial replay checkpoint after the accepted executor prefix; its one
private test-fixture assignment is annotated, and persistence/replay assertions
are unchanged. A recalibrated fixed seed preserves the chained Ecstatic Death
Fight alternation/no-nesting outcome.

These changes repair the same invariant in canonical fixture setup; no production
API, rule, exception policy, or outcome assertion was weakened. The stopped
covered run retains 19 failures, seven fixture errors and 6,642 passes as failed,
incomplete evidence. Focused repair runs preserve the diagnostic trail. The
current source tree is unchanged from `c87d5352`; final aggregate validation uses
the new fixture tree. The measured production/runtime and executed benchmark
helper functions remain unchanged from `5b6752ff`; the performance artifact's
later-fixture audit identifies the two unmeasured helper functions that changed.

The next aggregate found two additional direct-executor call sites in the same
mission-scoring test module. The complete five-call inventory is now corrected,
including its out-of-phase Snap and attached-target cases, using the existing
shared declaration helper and explicit normal-activation phase state. The entire
scoring module passes **226 tests** in `r34-complete-scoring-module-repair`.
No production source changed; failed aggregate evidence remains separate from
the final repaired candidate's required complete covered run.

The full Secondary certification inventory also exposed Cleanse's legacy synthetic
completed-Action setup. Both Action families now share a real accepted submission
helper; Cleanse completes through the existing GameState owner. The synthetic
completed-Action constructor was removed from that shared fixture module.
All **112 Secondary certification and scoring-authority tests** pass in
`r34-all-secondary-action-fixtures`, including both players' Cleanse and Plunder
score/retain, restoration, viewer and replay cases. This closes the fixture bug
class across both Action seeders, not just the first Plunder failure.
