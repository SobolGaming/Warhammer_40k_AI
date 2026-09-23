# Order 77 preflight — Action interruption after returning to the starting pose

Reviewed main: `a28e84025db258825af56769eb90652d69213350`.
Review date: 2026-09-22, America/New_York.

The owner subsequently approved implementation and publication of P16B. The
preflight below remains historical evidence; implementation details follow it.
Status: **blocked before complete 25-category certification**. CAUDIT-01 remains
open. This is a bounded preflight finding, not the complete operative-clause/FAQ
inventory or a snapshot-wide compliance certificate.

Remote main matched the local checkout. Order 76, PR #496, merged at
`2026-09-22T22:36:35Z`; the remote open-PR inventory was empty. Orders 73–76
are present in the reviewed main. Their older unmerged delivery notes are
historical metadata.

## C16-03 — completed movement is confused with net displacement

Core 16.01 requires an Action to fail after its unit makes a move other than
pile-in or consolidation, or leaves the battlefield. The requirement concerns
the completed move, not whether the final pose differs from the initial pose.
Core 03.01 permits multiple straight segments and accumulates their distances.

The real-domain probe starts Maintain Control through `LocalGameSession`, then
submits an engine-enumerated reactive Normal Move. Every model in the five-model
unit follows a validated `PathWitness`. The following cases use the same legal
formation, mission layout and source descriptor:

| Case | Accepted distance per model | Net displacements | Action result |
| --- | --- | --- | --- |
| Translation control | 0.25 inches | 5 | Interrupted with `unit_moved` |
| Move 0.125 inches away, then 0.125 inches back | 0.25 inches | 0 | Remains started; the subsequent finite completion choice completes it |
| Accepted zero-distance move | 0 inches | 0 | Remains started; the subsequent finite completion choice completes it |

The positive-distance return path is the decisive counterexample. The zero-distance
case is retained as an additional observation; the prerequisite must assess it
explicitly against the completed-move semantics rather than infer movement from
distance alone. Declining a move, Remain Stationary, pile-in and consolidation
must retain their distinct meanings.

The engine's per-model movement history correctly records 0.25 inches for the
return path. It also records the reactive Normal Move for the once-per-phase
restriction. The Action checker nevertheless loses the movement cause because
the physical transition batch contains no displacements. This is not a path
validation failure or an unresolved geometric computation.

Exact replay reproduces each case. JSON session persistence restores the same
state, including the incorrect completion. Thus deterministic replay is working
but is preserving a gameplay error. These checks do not certify the rule.

The local reproducible probe and full results are
`reports/order77/probe_action_movement.py` and
`reports/order77/action-movement.json`; their hashes and compact findings are in
[preflight.json](performance/order77/preflight.json).

```sh
UV_CACHE_DIR=/private/tmp/order77-uv-cache PYTHONPATH=. \
  uv run --no-sync python reports/order77/probe_action_movement.py
```

The probe asserts reproduction of the defect, not compliance. It imports named
shared fixtures, uses real domain objects and the ordinary facade, and replaces
no decision controller, validator or service. Its replay origin is the pending
reactive-move boundary after the source-linked Action start. It is a gameplay
slice, not a complete game or an initialization-to-completion recording.

## Source evidence

The retained source owner is `gw-11e-core-actions:performing-actions`, section
16.01, in `core_actions_2026_09/artifacts/package.json`. Its complete operative
transcription hash is
`35ce80a49504a36233fd650004a26e48390cb63d4da397b371642a9094c93b91`.
The 40k.app evidence observation hash is
`efb112805af8e2e965f0b474dd0796b504d03fcc8917671062d311823949bdba`,
with maintained-mirror audit fingerprint
`8537fde17e17b00d0421761c5cf79f9aa4857bcf12a6ff26632b46cff8b426d5`.
Its provider is non-affiliated 40k.app, URL
<https://www.40k.app/rules/16-actions>, observed September 9 without an exposed
App version. The offline source generator check passed during this preflight.

The September 22 browser exposed complete 16.01 and 03.01 at
<https://www.40k.app/rules/16-actions> and
<https://www.40k.app/rules/03-moving>. Their pertinent wording corroborates the
retained Action obligation and cumulative segment distance. Direct web fetches
of 40k.app returned 403; ordinary browser navigation loaded the pages.
Game Datamissions' changelog exposed version 946, dated September 2, and its
18.04.01 addition. No co-version comparison or complete all-category snapshot
selection is claimed. No new source observation is registered with runtime, and
the existing package hashes and partial semantic-execution status are preserved.

## Owning path and same-class audit

`LocalGameSession.submit_option` routes through `GameLifecycle.submit_decision`
and the registered `TriggeredMovementHandler`. Accepted movement records its
full witness, per-model distance and completion event. `BattleRoundFlow` then
calls `reconcile_primary_mission_action_interruptions` before end-boundary
Action completion and scoring.

- `primary_mission_action_interruptions._transition_evidence` derives movement
  causes only from `transition_batch.displacements`. The restore validator
  `validate_primary_mission_action_interruption_evidence` repeats that same
  assumption. Both must consume the same authoritative completed-move evidence.
- `TriggeredMovementResolution.transition_batch` omits equal start/end poses.
  Ordinary movement, Fall Back and Charge transition builders do likewise.
  `ModelDisplacementRecord` deliberately requires different endpoint poses, and
  historical transition validation authenticates that contract. Changing only
  the triggered builder would violate physical-record semantics and leave other
  consumers inconsistent.
- Ordinary movement has a second Action-interruption path in
  `movement_fall_back_embark._interrupt_started_mission_actions_for_movement_activation`.
  It uses the chosen movement kind rather than net displacement but uses direct
  unit-ID matching. Its interaction with primary/other Action policies, attached
  lineage and interruption-history authentication requires the same focused
  owner audit; this preflight does not claim an independently executed failure
  for every such mode.
- `model_movement_history.distances_from_completion` already consumes accepted
  path results, and reactive Normal Move recording already uses the completed
  move. They are controls, not newly demonstrated Heavy or movement-limit bugs.
  The Surveil move-rule consumer likewise selects by completion event and unit
  identity rather than requiring a displacement; no Surveil defect is claimed.

The smallest complete repair belongs to the shared Action-interruption authority
and its restore evidence, with an audit of the ordinary movement caller. It does
not require weakening path validation, changing endpoint-delta representation,
adding a content-named handler, or changing source interpretation.

## Proposed prerequisite and acceptance

Canonical owner: **P16B / C16-03**, inserted as Order 77 before PFINAL, which
moves to Order 78. Implementation requires owner approval of this expansion
from certification into gameplay remediation.

1. Add failing facade regressions for positive-distance return paths and audit
   rotation/zero-distance completions, preserving decline, Remain Stationary,
   pile-in and consolidation controls.
2. Share source-linked completed-move interpretation between live Action
   interruption and historical validation. Cover ordinary/reactive movement,
   attached components and the supported Action families without duplicated
   mutation or invented displacement records.
3. Require Action non-completion, unchanged shooting/Charge restriction expiry,
   both viewer event streams, exact replay, persistence and forged-evidence
   rejection. Preserve invalid-proposal retry purity from Order 76.
4. Add a feasible static audit against deriving Action movement only from net
   displacement; confirm/update the adapter contract, regenerate required
   identities and artifacts, assess matched performance and run all final gates.
5. Publish and merge the prerequisite, then restart the complete PFINAL audit
   from merged main. This finding does not close any unexamined category.

The roadmap explicitly states: "If the audit discovers any gap, do not open or
certify PFINAL." AGENTS.md also requires a pause before materially broadening
the requested work. No gameplay repair or PR publication occurred in this
preflight.

## Complete-game assessment and validation limits

The headless adapter submits one supplied decision. Repository searches found
no representative legal complete-game driver or committed complete-game
recording. The pairing certification helper starts at a seeded Fight boundary
and drives scoring; it is not a complete game. The capability manifest still
reports `certified_full_game_evidence_missing`.

Complete games attempted/completed: **0/0**. No per-game timing samples, mean
or maximum exist. The below-60-second mean and at-most-300-second observed
maximum remain uncertified. Missing prerequisites are a versioned legal workload
or recording, rosters/terrain/seeds/policy, normal completion and replay output,
and measurements on declared reference hardware. The workload must include
Order 74's continuous terrain solver; its focused Charge budget is not a
substitute. No new driver, AI, training work or budget change is included.

Three focused existing regressions passed in 4.57 seconds without coverage:
post-start reactive Action interruption, unchanged-model transition filtering,
and reactive Normal Move history. The probe reproduces the defect, and the
Action source generator and probe Ruff checks pass. Planning/report checks are
recorded in the machine-readable preflight artifact.

No production code, runtime identity, source package, adapter schema or collected
behavioral test inventory changed. Aggregate coverage, the complete quality
suite and publishing gates were not run at this preflight pause. The complete
clause/FAQ inventory, selected snapshot, all v931/v946 and September 10 closures,
cross-category certification and CAUDIT-01 closure remain outstanding.


## Approved P16B implementation

The violated invariant is Core 16.01: making a move interrupts a pending Action
unless that move is pile-in or consolidation. Returning to the starting pose,
rotating without displacement, and electing a zero-distance Normal Move still
complete the selected move. Declining the choice and Remain Stationary do not.

`record_move_completion_event` now reconciles Actions once the authoritative
completion, distance history and move-trigger context are recorded. The shared
Action evidence parser classifies the completed movement and matches the
validated path's physical model IDs to the Action's rules-unit lineage. Both live
reconciliation and historical interruption validation consume that parser.
It does not infer movement from a positive distance or a nonempty displacement
batch. Removal/destruction evidence retains its existing ownership.

The ordinary movement helper's separate mutation path is removed, including its
import/export references. This also removes exact component-ID matching from
that caller. The module retains its historical primary-action name, but pending
Actions are selected from engine Action state, with provenance from the current
mission definition. Cleanse follows the same authority. Terraform's catalog
definition is covered by this content-neutral selection; the current supported
mission assignments do not offer Terraform, so this PR makes no new Terraform
playability claim. Immediate Actions have no pending interval to interrupt.

Restore additionally checks each recorded Action's interval for a completed
move and rejects continuation/completion after it, removed interruption events,
or drifted source references/reasons/state. It does not require invented
physical displacements. No source package, load-support classification,
semantic-execution status, player choice or payload schema changes.

### Regression scope and architecture audit

- New facade coverage uses Maintain Control and Cleanse, single and attached
  units, translation, positive-distance return, zero-distance and rotation paths.
  It asserts per-model distances, unchanged delta semantics, Action interruption,
  unavailable primary completion, both viewers, JSON persistence and exact replay.
- Decline preserves completion. The shared evidence parser covers Normal,
  Advance, Fall Back, ordinary and reactive Charge, Surge, Remain Stationary,
  pile-in and consolidation. These parser controls reuse actual validated model
  rows; they are not claims of new movement-family integration coverage.
- Restored interrupted Actions retain their shooting and Charge activity locks.
  The existing restriction expiry path is unchanged. Invalid physical proposals
  retain Order 76's existing regression coverage.
- Ordinary-movement and Charge restriction fixtures now record their previously
  missing Action start events. The Fight exception fixture supplies its completed
  move descriptor. Checkpoint-forgery fixtures explicitly isolate physical
  checkpoint authentication from the independently tested interruption guard. The reactive consumer regression expects interruption at
  the completed-move owner and checks idempotence at later reconciliation.
- A static quality guard prevents net-displacement iteration in the Action
  authority and checks the common live/restore owners. Changes stay inside the
  existing engine dependency boundaries, with no named content handler,
  speculative hook, geometry algorithm, source interpretation or new driver.

The extra Movement-module changes remove imports of the deleted helper; they
add no behavior. Source-backed start/completion eligibility, scoring and generic
movement authentication remain with their existing owners. The Cleanse fixture
pauses at another unit's legal Shooting choice: its older catalog scoring path
is outside this repair and is not newly certified. The previous preflight's
full-game and PFINAL limitations still apply.

Final gate and timing results are recorded in
[Order 77 performance evidence](performance/order77/README.md) and its validation
artifact. P16B must merge before the complete Order 78 PFINAL audit resumes.

## R77-001 — authenticate terminal history before bounding movement

Review reproduced a restore bypass in Cleanse: suppress its actual movement
interruption, restore its status to `started`, and insert a forged terminal
before the accepted return-path move. The movement validator bounded its scan
at that terminal without authenticating it. Primary-only integrity checks did
not protect secondary Actions. Completed, completion-failed and interrupted
terminal event types all reproduced the bypass.

The violated invariant is that only authenticated terminal history may end an
Action's movement-validation interval. Terminal cardinality, type/status,
persisted payload, battle/source context and ordering now live in one shared
engine validator, extracted from the existing primary authority. Both primary
integrity and the common movement scan consume it before accepting a terminal.
Primary-specific source, decision, completion and interruption evidence checks
remain in their existing owner. No payload schema or player choice changes.

The bug-class search covered all three Action terminal types and both primary
and secondary history consumers. Regressions exercise the original three
forgeries plus altered terminal state/context, missing and duplicate terminals,
and a terminal before its start. The untouched Cleanse history must round-trip
before the tampering tests run. A static guard requires shared authentication
before the movement evidence scan. PFINAL remains open as Order 78.

The broader consumer run also exposed three lower-level fixtures that completed
or interrupted Actions without recording their terminal events (11 failing
parameterized cases). Those fixtures now append the missing terminal history;
35 affected tests pass without weakening restore validation. Final aggregate
results and refreshed performance evidence are recorded in the validation artifact.
