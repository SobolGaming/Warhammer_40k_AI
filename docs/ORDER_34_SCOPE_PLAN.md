# Order 34 / P16 / C16-01 and C16-02

Base: `e56c1a4caf2a6915548222caed0872627f8dbf43` (origin/main on
2026-09-09). PR #437 is merged; its R33-001 engagement correction and R33-002
exact source inventories are present. PR #436 contains R32-001's retained
observer correction. The initial checkout was clean. Work uses
`codex/order-34-action-restrictions`.

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
