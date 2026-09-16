# Order 52 — Surge moves (P21B / C21-02)

## Required invariant

A source-triggered Surge is offered only to an unengaged, non-Battle-shocked
rules unit that has not moved in the current phase occurrence. The controlling
player selects a closest enemy, including a finite choice between tied enemies.
Every surviving model must engage that target if possible, otherwise finish as
close as possible. No model may finish engaged with another enemy. Completing
Surge prohibits every further move in that phase occurrence.

## Ownership and planned acceptance

The shared triggered-movement service owns source eligibility and the finite
unit/target commitment. Ordinary path and terrain validators remain authoritative.
Mandatory endpoint queries must produce a validated alternative, a mathematical
impossibility bound, or an explicit unresolved diagnostic. Search exhaustion is
never evidence that a closer endpoint is impossible. Movement completion owns
phase history, including attached model identity and the actual turn owner.

The consumer trace covers movement-end hooks, shooting-end hooks, generic RuleIR
Stratagem movement, finite paths, parameterized paths, ordinary Movement, Charge,
Fight and setup proposals, persistence, replay and viewer-scoped projections.
Surge cannot use Flying Models, which only permits Normal, Advance, Fall Back
and Charge moves. Other triggered Normal moves retain their existing semantics.

The current roadmap row is authoritative. The historical P24C1 note describing
duplicate-instance selection as Order 52 is stale; that work is now Order 56.

## Evidence

Reviewed 21.02 in the retained official Core Rules PDF, page 70, and the complete
40k.app search-index observation on 2026-09-16. Direct page retrieval returned
403; no successful direct fetch or second-provider comparison is asserted.

## Implementation and scope audit

`surge_movement`, `surge_endpoints` and `surge_choices` implement source eligibility,
canonical closest targets (including the AIRCRAFT/FLY exception), finite ties,
target-only Engagement and per-living-model endpoint obligations. The shared
triggered-movement resolver applies ordinary path, terrain and group coherency
validation. Extracting resolution and selection removes the old module from the
size-policy allowlist; no new named handler or faction branch is introduced.

`phase_movement_history` derives accepted movement from existing completion
witnesses and setup transitions, keyed by battle round, actual turn owner and
phase. Model IDs preserve the lock after attachment changes. Shared candidate,
proposal and battlefield-mutation boundaries enforce the lock across Movement,
Charge, Fight, reactive movement and setup. Stationary choices and skipped Fight
steps are distinguished from witnessed moves, including zero-distance moves.

`surge_authority` revalidates the source occurrence and original finite commitment
before selection, rerolls and proposal queue pop. Restored pending and completed
decisions authenticate target, source, event-time geometry and movement history.
Recorded rule-invalid proposals now replay through their rejection and retry;
pre-pop invalid submissions still fail. Contract 23 / persistence 15 / replay 17
make the required authority fields explicit incompatibilities with old records.

The bug-class search covered all Surge constructors, generic RuleIR Stratagem
movement, movement/shooting reaction hooks, every movement completion family,
normal-move history, physical mutation and restore. Older fixtures that used
Surge as a synonym for an ordinary Normal reaction now request ordinary triggered
movement. The generated Blood Legion Murdercall consumer selects a target and
completes its source-granted Surge through the shared implementation. Corsair
Vengeful Sorrow supplies its real decision/event history to the same trigger
validator and exposes the committed enemy target.

The pre-merge grant review found a violated authority invariant: changing a
pending proposal's distance from 3 to 6 inches, together with its matching request
event, survived restore because only the target was bound to the original finite
selection. The shared selection-chain validator now compares the entire
descriptor and selected-unit record with that grant. Changed distances require
the original reroll permission, matching decision IDs, ordered recorded events,
and an isolated reconstruction through `DiceRollManager.resolve_reroll`; only
the original source bonus is added. The copied proposal roll state must match.
Live submission, pending rerolls, retries and completed-movement history consume
this same validator. A changed movement-kind token cannot bypass it.

The focused bug-class search followed descriptor replacement and distance-roll
copies in triggered-movement selection, reroll resolution, proposal retries and
Surge completion history, and checked the existing Charge/Battle-shock historical
dice validation patterns. The fix stays within Surge grant authentication and
reuses the dice owner; unrelated reaction families and geometric solvers are
unchanged. Regression cases reject descriptor, bonus, reroll-reference and dice
evidence tampering, including the reported checkpoint edit, while accepted and
declined rerolls with source bonuses complete, restore and replay exactly.

## Geometric proof boundary

An endpoint already engaging the selected target satisfies that model's required
approach. Otherwise the shared path solver must prove Engagement unreachable;
a legal endpoint attaining the global distance lower bound proves maximum
approach. Validated alternative paths disprove incomplete approaches. Obstructed
or noncircular cases for which neither proof is available return the typed
`surge_reachability_unresolved` diagnostic, without movement mutation. Bounded
search exhaustion never becomes permission to stop short or a claim of
impossibility. This does not claim a complete optimizer for arbitrary geometry.

Focused tests cover facade selection, ties, every-model approach, Engagement,
non-target exclusion, prior movement, Battle-shock drift, rerolls, attachment,
phase/turn scoping, player projections, rejection/retry, exact replay and checkpoint
tampering. Source and static audits pin the reviewed artifact and shared owners.
Initial aggregate validation is recorded in `performance/order52/validation.json`;
the grant-review fix's final gates are in `performance/order52/grant-validation.json`.
Performance evidence and its limits are in [the diagnostic report](performance/order52/README.md).
