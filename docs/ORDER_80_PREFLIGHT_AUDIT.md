# Order 80 preflight / P09C — Normal Move phase occurrence

Reviewed main: `dc01911f57024ae69b565a0e965db65abf5fbdbe` (Order 79 / PR #499).
Review date: 2026-09-23, America/New_York.
PFINAL status: **blocked before complete 25-category certification**.
CAUDIT-01 remains open. The owner subsequently approved fixing the identified
gaps; this PR implements the bounded P09C prerequisite.

Remote main matched the checkout and the open-PR inventory was empty. This
bounded preflight checks the September 10 review's explicit 09.05.01 consumer
obligation. It is not an all-category audit, a selected-snapshot certificate or
the full PFINAL audit. This PR implements Order 80 / P09C, not PFINAL.

## C09-03 — both players' Movement phases share one Normal Move key

The once-per-phase restriction must distinguish each player's phase occurrence.
`NormalMoveState.same_phase_key()` instead contains only battle round, phase
kind, **unit owner**, and unit ID. Neither its payload nor the shared history
query contains the turn owner. The history is retained across turn boundaries.

The retained [probe](../scripts/probe_order80_normal_move.py) uses real canonical
five-model infantry units, a valid 0.25-inch PathWitness, and an explicit generic
reactive Normal Move permission as its initial fixture. It does not claim a
faction-specific permission or faction certification. After that initial fixture,
all decisions, authoritative movement and turn advancement use LocalGameSession.

1. During Player A's first Movement phase, Player B accepts the reactive move.
2. Player A remains stationary and completes Shooting. With no legal Charge or
   Fight activations, the lifecycle progresses through the turn boundary and
   Player B's Command phase to Player B's Movement phase, still in round one.
3. Player B selects that same unit. The engine offers Advance and Remain
   Stationary, but omits Normal Move. The earlier reaction was in a different
   phase occurrence, so Normal Move must be available.
4. The otherwise identical declined-reaction control offers Normal Move.

Both cases round-trip the complete session persistence payload, preserve both
viewers' projections, and reproduce exactly through ReplayRunner. Thus restore
and replay reproduce the defect, rather than repairing it. Separate pure
resolution controls confirm that a second Normal Move in the *same* phase is
correctly rejected and that a different phase kind is not blocked. Those controls
do not mutate the live fixture. This probe observes the known-bad result on the
reviewed base; its successful exit is **not** a semantic pass or regression test
for a repaired implementation.

## Source evidence

The browser exposed the complete [09.05.01 clause](https://www.40k.app/rules/09-movement-phase):
“A unit cannot make more than one Normal Move in a phase.”
The [07.02 player-turn structure](https://www.40k.app/rules/07-the-battle-round)
and expanded 07.02.02 were also inspected: each player has a separate turn with
its own Movement phase. No source ambiguity was found for this finding.

The existing stable source ID is
`gw-11e-rules-and-event-updates-2026-07-22:app-core-rules:09-normal-move-one-per-phase`.
The retained July package expresses the same limit with slightly different
capitalization and phrasing. Its historical evidence, package bytes, registry,
official PDF hash and source-observation fingerprints are preserved. The fresh
complete 09.05.01 transcription and evidence tuple, including provider, URL,
review timestamp and hashes, are in [preflight.json](performance/order80/preflight.json).
This is audit evidence, not registered runtime source data. The fingerprint
detects changes to the retained record; it does not authenticate the website.

40k.app exposes no App-data version. Game Datamissions' currently observed
[changelog](https://game-datamissions.com/11th/rules/changelog) selects v946,
dated September 2, and exposes Rapid Disembark. It supplies no co-versioned
comparison for the Normal Move clause. No mirror disagreement or official-App
exception was observed. No all-category snapshot was selected or certified.

## Authoritative path and same-class audit

Initial engine-created reactive request -> LocalGameSession submission ->
GameLifecycle / DecisionController -> TriggeredMovementHandler -> shared path
validation and battlefield mutation -> NormalMoveState recording -> lifecycle
phase/turn advancement -> ordinary Movement action enumeration and validation
-> both viewer projections, persistence and exact replay.

| Owner or consumer | Finding / required treatment |
|---|---|
| `normal_move_history.NormalMoveState` | The shared key and serialized evidence omit the turn owner. Unit ownership cannot identify a phase occurrence. |
| `GameState.record_normal_move_state`, `normal_move_states_for_unit_phase`, `_validate_normal_move_states` | Duplicate detection, querying and restoration share that incomplete key; changing only menu filtering would still reject a legal second-turn record. |
| `movement_validation._unit_already_made_normal_move_this_phase` | Ordinary action and proposal validation inherit the stale restriction. |
| `triggered_movement_selection` and `triggered_movement_resolution` | Both selection filtering and independent path resolution compare the same incomplete identity. Both finite and parameterized completion paths record it. |
| `phases/shooting_targeting._rules_unit_remained_stationary` | Reads Movement history without turn identity. Certify that prior-opponent-turn movement cannot negate current-turn stationary status. This consumer is identified statically, not separately reproduced here. |
| `phases/movement_transports` | Uses the same query to classify a Transport as having made a Normal Move, affecting Tactical/Rapid Disembark candidates. This consumer is identified statically, not separately reproduced here. |
| `phase_movement_history`, `model_movement_history`, `active_player_scopes` | Existing owners already distinguish turn owner from reacting/effective player and retain model lineage. Reuse that authority where suitable; do not introduce a second interpretation of whose phase is active. Heavy uses the separate turn-aware model-distance authority; this preflight does not demonstrate a Heavy defect. |
| Existing Normal Move tests | Cover same-phase rejection, different phase kinds/rounds and restore, but do not distinguish both players' same-named phases within one round. Their passing results do not close this finding. |

The required invariant is bounded to Normal Move occurrence identity and its
direct consumers. A wider rewrite of unrelated lifetime records, faction rules,
AI, movement geometry or performance optimization is outside P09C. No new
handler or adapter-specific behavior is needed. Historical integrity must remain
fail-closed; do not silently invent a turn owner for an ambiguous old record.

## Approved prerequisite and acceptance

The roadmap assigns **C09-03 / P09C** to Order 80 and moves PFINAL to Order 81.
The initial scope pause identified that certification required a gameplay/history
repair. The owner then explicitly approved fixing the identified gaps.

1. Pin exact 09.05.01 source authority with the 07.02 phase-occurrence context.
   Preserve all historical evidence and register any new implementation source
   observations through the existing governance boundary.
2. Write failing facade regressions for reactive-before-own-turn and
   ordinary-before-opponent-reaction paths within one battle round, then fix
   the shared occurrence owner and all Normal Move writers/readers. Preserve
   the same-phase prohibition, cross-phase/round reset and declined/invalid
   attempts. The phase belongs to the turn player, not a temporary active scope.
3. Cover physical and attached units, component/casualty/split lineage, finite
   and parameterized submissions, pending stale proposals and accepted replay
   records. Certify stationary and Transport classification consumers, with
   tests that demonstrate actual affected behavior rather than only the key.
4. Authenticate occurrence identity from retained decision/completion history
   on restore; reject tampered or ambiguous evidence. Preserve deterministic
   JSON, both viewers and exact replay. Update the adapter contract and assess
   a versioned checkpoint/contract migration if payload semantics require it;
   no compatibility fallback is authorized.
5. Refresh required runtime/contract artifacts after any production changes,
   measure a matched focused workload, maintain behavioral shard inventories,
   and run all required final and CI gates after scope/architecture review.

After P09C merges, restart PFINAL's full audit from current main, including all
25 categories, every clause/FAQ, all v931/v946 obligations, the September 10
dispositions and cross-category consumers. This preflight does not replace it.

## Complete-game performance and validation

Complete games attempted/completed: **0/0**. The capability search found the
single-decision `adapters/headless.py` interface and bounded gameplay/benchmark
fixtures, but no representative versioned legal complete-game driver or complete
recording. Missing prerequisites remain legal rosters, terrain, seeds and
decision policy; initialization-to-normal-completion/replay evidence; and an
included workload exercising Order 74's continuous terrain solver. No new game
driver is added. No per-game samples, mean or maximum exist. The standing mean
below 60 seconds and observed maximum at most 300 seconds remain **uncertified**.
Provisional host: Apple M5 Pro, 18 logical CPUs, 64 GiB RAM, macOS 26.7 (25G229).

The pre-approval evidence remains in `preflight.json` and `probe-results.json`.
The base-only diagnostic script intentionally reproduces the defect on the
reviewed commit; the collected Order 80 tests assert the repaired behavior.
Implementation validation and final gate results are recorded in
[validation.json](performance/order80/validation.json).

The original scope pause followed [AGENTS.md](../AGENTS.md): “If the required solution is
materially broader than the apparent request, pause before broadening it.”
The roadmap also states: “If the audit discovers any gap, do not open or certify
PFINAL.” P09C does not close CAUDIT-01 or certify Core Rules compliance.

## Approved implementation

`NormalMoveState` now requires the turn player separately from the unit owner.
The shared completion recorder owns ordinary and reactive Normal Move history;
Surge and other movement modes remain distinct. GameState delegates recording,
validation and queries to the existing history module, shrinking the frozen
GameState module. Triggered path resolution requires explicit turn context.
Shared queries preserve current/component/historical split identities.

Restore reconstructs the exact expected history and checks its occurrence against
accepted decisions, including the source selection behind a proposal. Triggered
completion classification must match its accepted descriptor. Missing turn owners,
duplicate records, removed history and drifted completion/ownership evidence fail
closed. No old checkpoint is assigned an inferred turn owner. Contract 35,
persistence v27 and replay v29 record this migration; retained released baselines
and source packages are unchanged.

The regressions exercise both turn directions, standalone and attached units,
finite and parameterized choices, temporary reactive player scopes, stationary
status, Transport disembark candidates, same-phase blocking, cross-phase/round
queries, historical split/component aliases, pending invalid proposals, persistence,
both viewer projections and exact replay. The split and Transport comparison
fixtures isolate existing consumers and do not grant new in-game permissions.

No faction handler, rule-name gate, geometry solver, AI behavior or adapter-only
mutation path is added. Performance evidence covers this bounded slice; inherited
current-runtime gates retain their existing workloads and numeric limits.

The historical consumer audit also corrected test fixtures that attributed a move
to the wrong player or performed two Normal Moves in one occurrence. Scoring
checkpoint tests now move the turn player’s own unit; the deferred-marker test
uses a later occurrence for its later move. Two Vanguard checkpoint tests now
anchor enemy positions in the accepted initial checkpoint instead of injecting an
ordinary enemy move during the acting player’s turn; their forged terminal
checkpoint assertions remain unchanged. No production check was relaxed.

Final local validation: **9,045 behavioral tests passed with 85.21% coverage;
608 code-quality tests passed**. The eight behavioral shards were regenerated
from the successful complete JUnit profile. Lint, formatting, both type checkers,
import boundaries, the exact-base contract check, installed-wheel smoke and
TypeScript generation/unit/conformance programs passed. Prior failed fixture and
provenance attempts are retained in the validation record. PFINAL and complete-game
performance certification remain open.
