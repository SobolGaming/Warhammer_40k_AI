# Order 79 preflight / P14A — turn-end objective control precedence

Reviewed main: `68c6bccb7d1f44e3b03409a86565a3d285c8449d`.
Review date: 2026-09-23, America/New_York.
PFINAL status: **blocked before complete 25-category certification**.
CAUDIT-01 remains open. The owner subsequently approved P14A implementation;
the preflight below is retained as historical evidence.

Remote main matched the checkout, PR #498 (Order 78) merged at
`2026-09-23T16:40:32Z`, and the open-PR inventory was empty. This is a fresh,
bounded preflight against that merged revision, not an all-category certificate.
No PFINAL PR has been opened.

## C14-03 — turn-end control is determined after coherency cleanup

Core 14.02.01 requires objective control to be determined first at both phase
and turn ends, before other rules at that boundary. The shared state owner
previously performed coherency cleanup before capturing turn-end control.

The valid numerical counterexample is a five-model infantry unit with four
models away from an objective and one isolated model controlling it. Coherency
cleanup removes that isolated model. Merged main then records no controller and
withholds the Immovable Object central-objective award. Control must instead be
captured before the removal: Player A controls the objective at that boundary
and receives the control-based award. The existing regression's post-cleanup
oracle was corrected; its pre-repair failure is retained in the validation evidence.

Aircraft departure also belongs after the control determination, but it is only
an event-order test. Aircraft cannot supply the numerical counterexample: their
Movement and OC are source dashes in 11th Edition. The corrected fixture uses
`CharacteristicValue.source_dash` and asserts zero contribution before and after
departure, including own-turn and off-objective controls.

### Withdrawn initial Aircraft claim

The initial preflight reused a synthetic vehicle profile tagged AIRCRAFT but
left its numerical OC 4 intact. That fixture was rules-invalid for the claimed
11th Edition OC result. Its observed Player A-to-uncontrolled transition does
not establish a valid gameplay defect, even though persistence and replay
reproduced it. The owner identified this error, and the numerical claim and
original benchmark workload were withdrawn before publication.

The original observations remain labelled as withdrawn historical evidence in
`performance/order79/preflight.json`; the archived OC 4 measurements are excluded
from the active performance gate. The corrected finding rests on coherency
removal and the retained scoring regression. The implementation's shared
boundary-order repair remains necessary.

## Source evidence

GW’s [June 9 faction-update article](https://www.warhammer-community.com/en-gb/articles/fchkklcq/new40k-download-new-xenos-faction-packs-today/) confirms Aircraft Movement and OC are dashes. This corrects the fixture and audit claim; it does not add a faction catalog or alter the registered control-first source.

The complete expanded [14.02.01 clause](https://www.40k.app/rules/14-objectives)
was read in the browser on September 23. Its normalized wording exactly matches
the retained stable source row
`gw-11e-rules-and-event-updates-2026-07-22:app-core-rules:14.02.01-control-first`
in `july_rules_updates_2026_07/artifacts/package.json`.
This is an implementation gap, not a new source interpretation.

The preflight JSON pins the fresh transcription, provider, URL, observation
timestamp, policy and source-observation hash, plus the existing package byte
hash. The fresh observation is not registered as runtime source data; historical
source observations and the official PDF hash remain unchanged. The fingerprint
detects retained-record changes and does not authenticate the external website.
The browser content exporter was unavailable; no network capture is claimed.

40k.app exposes no App-data version. Game Datamissions' observed changelog
selects v946, dated September 2, and exposes 18.04.01 Rapid Disembark. It supplies
no co-versioned comparison for this objective clause. No mirror disagreement or
official-App exception was observed. Category 07's body and expanded
07.02.01/07.02.02 were read, but no complete category-07 certification is claimed.
No controlling all-category snapshot has been selected.

## Authoritative path and same-class search

`LocalGameSession.advance_until_decision_or_terminal` -> `GameLifecycle` ->
`BattleRoundFlow.advance` -> boundary sequencing -> engine Aircraft departure
-> `GameState.prepare_current_turn_end_boundary` -> canonical objective-control
proposal/commit -> retained mission-scoring record, checkpoint, events and replay.

- `boundary_rule_flow.prepare_phase_end_boundary` owns the already-correct
  phase-end preparation. Preserve its distinct record and source identity.
- `BattleRoundFlow.advance` must establish turn-end control before discovering
  or executing turn-end rules, including rules that suspend for player choices.
  Moving only the Aircraft departure would leave the generic boundary wrong.
- `GameState.prepare_current_turn_end_boundary` couples control capture to
  Action clearing, coherency cleanup and effect expiration. It requires a
  shared preparation/cleanup design; moving this entire method earlier would
  move unrelated mutations and would still capture control after cleanup.
- `GameState.advance_to_next_battle_phase` is another consumer of the same
  turn-end preparation owner. Direct-state and lifecycle paths must agree.
- The existing
  `test_turn_end_control_and_primary_scoring_use_post_cleanup_battlefield`
  explicitly expects an isolated controlling model's cleanup to remove both
  control and the control-based score. That test passes on main and encodes
  another instance of the violated ordering invariant. The adjacent cleanup
  test also expects the turn-end checkpoint to show the removed model absent.
- `mission_turn_end_record`, objective-control record authority and historical
  checkpoints consume/authenticate the captured record. The repair must preserve
  one frozen control result while later mission rules can still inspect their
  appropriate current state. Scoring formulas and faction-specific rules are
  outside the prerequisite's scope.
- The adapter contract describes phase-end control preceding turn-end choices,
  but does not certify that turn-end control precedes those choices. Update its
  timing description and audit both viewers' projections and deltas.

The complete-game capability search still finds a single-decision headless
adapter and slice fixtures, not a representative legal complete-game driver or
committed recording. This is a separate evidence limitation, not C14-03's cause.

## Proposed prerequisite and acceptance

Insert **C14-03 / P14A** as Order 79 and move PFINAL to Order 80. This fulfills
the roadmap's requirement to assign newly discovered gaps before PFINAL;
implementation is paused pending owner approval because the requested
audit/certification PR would become a cross-cutting gameplay repair.

1. Retain exact source authority for 14.02.01 and its relationship to 14.02,
   turn sequencing and cleanup. Register any new implementation observation
   through the existing source boundary without rewriting historical evidence.
2. Write strict failing regressions, then establish one engine-owned,
   idempotent turn-end control determination before all turn-end rules and
   cleanup. Keep Fight-end and turn-end records distinct: legitimate Fight-end
   changes must be reflected at the subsequent turn boundary.
3. Cover automatic Aircraft departure, accepted/declined finite boundary
   choices, coherency removal, OC-effect lifetimes, sticky control and a real
   control-based scoring consumer. Audit repeated advances and suspension so
   later mutations cannot recalculate the frozen boundary.
4. Cover physical/attached ownership, direct-state and facade consumers,
   malformed/stale submissions where applicable, persistence at suspended
   boundaries, historical tamper rejection, deterministic JSON-safe records,
   both viewers and exact replay. Correct the stale post-cleanup test oracles.
5. Document adapter timing, assess whether payload semantics require a contract
   migration, refresh required generated identities, measure matched boundary
   workload costs, maintain shard inventories if files change, and run every
   required final and CI gate after scope/architecture review.

Do not add an Aircraft-specific workaround, alternate adapter path, named
handler or permissive restoration fallback. After P14A merges, restart the
complete PFINAL audit from current main, including all clauses/FAQs,
v931/v946 obligations, September 10 dispositions and cross-category consumers.

## Performance and validation at the pause

Complete games attempted/completed: **0/0**. No per-game samples, mean or maximum
exist. The standing mean below 60 seconds and observed maximum at most 300
seconds remain **uncertified**. Missing prerequisites are a versioned legal
complete-game workload with rosters, terrain, seeds and decision policy, normal
initialization-to-completion/replay evidence, and coverage of Order 74's
continuous terrain solver. Host metadata was read: provisional Apple M5 Pro,
18 logical CPUs, 64 GiB RAM, macOS 26.7 (25G229). No new driver or optimization
was introduced.

The now-withdrawn synthetic three-case probe completed and exactly replayed. Four focused existing tests
pass in 6.36 seconds without coverage; one deliberately preserves the current
incorrect post-cleanup expectation and must change with the repair. Planning
checks are recorded in [validation.json](performance/order79/validation.json).
The aggregate behavioral/coverage suite, complete code-quality suite, type
checks and publication gates have not run at this preflight pause. No runtime,
contract schema, source registry or collected behavioral file changed.

The pause is required by `AGENTS.md`: "If the required solution is materially
broader than the apparent request, pause before broadening it." The roadmap
also states: "If the audit discovers any gap, do not open or certify PFINAL."
No PR or compliance claim is delivered by this preflight.


## Approved implementation

The owner approved the prerequisite after the preflight scope pause. Order 79
now implements P14A / C14-03. The final implementation extracts turn-boundary
orchestration from the frozen `GameState` module into `turn_end_boundary`.
Final-phase rules and phase expiration finish first; one turn-end control record
and its source-linked event then precede all turn-end rule discovery. Action
clearing, coherency cleanup and turn expiration remain later operations, tracked
by their own cleanup record so a suspended choice cannot skip them. Shared final-phase
expiry skips an empty inventory, preserving the retained-attack work-count limit
while still expiring phase effects created by later turn-end rules.

Both direct-state phase advancement and lifecycle/facade advancement use this
owner. The retained snapshot supplies control-based mission scoring, checkpoint
authority, persistence and replay. Historical validation rejects control events
on either side of their legal interval: after final-phase resolution and before
the turn window opens. Activity-effect reconstruction uses that retained event
for final-phase expiry and the independent cleanup record for turn expiry, so
restoring a suspended turn rule preserves the same restrictions as live play.
No faction branch, named handler, rule-text parsing,
movement bypass or source semantics were added.

Regressions cover zero-OC automatic departure, on/off-objective and own/opponent-turn
controls, a source-loaded optional reserve choice (use/decline), stale/unknown
submissions, pending re-entry, save/restore, both viewers and exact replay.
Additional cases cover the corrected coherency/scoring oracle, separate phase
and turn effect lifetimes, Action restrictions through cleanup, sticky control,
attached contributors, direct-state
idempotence and invalid/duplicate boundaries. The optional consumer uses the
existing generic catalog fixture; it does not certify that fixture's faction
content for 11th Edition.

The existing registered 14.02.01 source row exactly matches the newly observed
text. Its package and observation history remain unchanged; the fresh preflight
observation is audit evidence rather than a replacement runtime source package.
The [adapter contract](ADAPTER_DECISION_CONTRACT.md) documents corrected timing.
Existing payload shapes and visibility rules cover it; only runtime identity
and the generated contract's build metadata change.

The scope audit found no further production consumers requiring local rules
patches. Duplicate phase/turn event emission now uses one boundary helper.
Existing static mutation guards follow the extracted owner and its explicit
state methods. PFINAL / CAUDIT-01 and complete-game performance remain open.
Final gate and matched measurement results are recorded in
[implementation-validation.json](performance/order79/implementation-validation.json).
