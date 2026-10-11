# Movement-witness membership prerequisite

The owner approved this separate prerequisite on 11 October 2026 at 03:57 UTC,
after independent D07 review reproduced a foreign-model witness consuming its
pending movement action, throwing an error and producing a save that cannot
reload. D07 is paused and its original source, failures and review archives remain
separate. This PR starts from actual merged main
`72475b63fa70f64a57264bc7a37e1c6fe7c7cca3`, tree
`dfc57f6f5accf2d948c9ef7540a7272b167b6b80`, sole parent
`b3e411bc415f98dae182fd96703d866f18a22ee2`. All 5,845 Git blobs and raw source
records match reviewed D06 final source.

The invariant is already required by AGENTS.md and
ADAPTER_DECISION_CONTRACT.md: wrong-context physical proposals reject before
queue pop and decision/event mutation. The complete controlling source is these
existing engine and adapter contracts; this is a supported-input boundary repair,
not a new gameplay permission or a claim that ordinary legal play causes the bug.
The baseline reproduction starts LocalGameSession from its declared Core config,
deploys through ordinary requests, reaches a native Normal Move request, restores
the engine-generated JSON checkpoint, then changes one witness model ID to an
actual enemy physical model. Its normal wrapper remains current. The original
resolver raises after committing the decision; the resulting generated checkpoint
fails replay reconstruction. No history, RNG or authoritative state is injected.

## Shared owner and scope

LocalGameSession.submit_parameterized_payload routes through adapters.decisions,
GameLifecycle.submit_decision and MovementPhaseHandler prevalidation before
DecisionController commit. The pending canonical actor is resolved by
rules_unit_placement_for_movement, which authenticates the living components,
owner and exact alive inventory against authoritative battlefield placement.
RulesUnitPlacement.matches_witness_models owns the exact physical comparison.
The ingress validator and existing strict movement resolver share that comparison
for Normal Move, Advance and Fall Back. The applier still fails fast if an internal
caller violates membership. Model IDs are neither inferred from their spelling
nor borrowed from caller-supplied expected inventories.

Bug-class inspection includes ordinary component movement, Scout, Charge, Fight
and triggered movement witness owners. Their distinct decision handlers and
existing validators are outside this reproduced movement-phase prerequisite.
There is no claim that this PR repairs or certifies every physical proposal family.
No schema, model/unit keyword policy, path geometry, terrain, coherency, movement
distance, fallback, granting source, serializer or RNG algorithm is changed.

## Acceptance and exact-final gates

- Foreign, unknown, missing and extra physical IDs reject atomically through the
  native facade, preserving the exact pending request, histories, RNG, events,
  counters and battlefield. Attached controls omit either entire component.
- Ordinary and attached canonical actors, both players, native Normal Move and
  Advance and native Fall Back preserve legal retry. Fall Back starts from a
  predeclared analytical W50 Core catalog, compact one-model bodyguard when
  attached, and adjacent legal deployment zones. Normal setup, Charge, Fight,
  dice and native Fall Back decisions establish the live state. No started state,
  RNG, history or replay anchor is injected; the fixture certifies this finite
  ownership path without claiming faction/provider support. Complete omission
  of a single-model witness retains the existing nonempty wire-schema rejection.
- Well-formed distance/geometry violations still record an attempt and issue a
  fresh proposal retry under the existing contract.
- Genuine engine JSON checkpoints restore before and after legal retry; independent
  forks remain isolated; both players and every role retain exact views/events;
  replay reproduces and ordinary native continuation remains deterministic.
- Original assertions, archived source pins, branches and performance ceilings
  remain unchanged. Failed/partial receipts earn no pass credit.
- Both type checkers, full source and generated inventories, client/contract/wheel,
  import/lint gates, quiet serial smoke, full quality and the complete covered
  behavior gate at 85% remain mandatory under the sequential review policy.
  The original 16 polygon cases run alone first with branch coverage. Only the
  parent's explicit release permits the remaining 32-worker cohort and bounded
  reviewer controls; final scheduling uses only authenticated current passing
  timings. Exactly one independent coding reviewer and one fresh rules auditor
  retain both exact-final scoped CLEAN reviews after any timing-only successor.

Every publication and strict protected squash gate remains required. Full Core,
provider and complete-game performance compliance are unclaimed. No compatibility
shim is approved or introduced. The separate D07 work resumes only after this
prerequisite is delivered and the new actual merged baseline is authenticated.

Apply `docs/SEQUENTIAL_REMEDIATION_REVIEW_POLICY.md`. Prioritize the complete
playable behavior in this order. Block on incorrect rules, normal legal-play
failures, engine-generated valid-state save/load/replay failures, and explicitly
required trust-boundary failures. For each blocker provide the reproduced entry
path, impact, normal reachability and violated acceptance requirement. Queue
coordinated hand-edited-history hardening separately when no necessary supported
input boundary or normal path is demonstrated. Keep scope within this order;
expansion requires an explicit decision. Preserve positive controls, regression
tests, source truthfulness and every required local/remote exact-head gate.
