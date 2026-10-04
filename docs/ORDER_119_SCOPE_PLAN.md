# Order119 / P20C / C20-03: Movement-phase source reposition

## Source and bounded scope

The immutable Order97 selection `rule:20:20.02:1`, block2, permits a
Movement-phase repositioning rule to act on a unit that already moved that phase.
Block1 defines battle-time removal into Strategic Reserves as repositioning;
immediate set-up is not required. This conditional Core permission does not grant
an otherwise unsupported removal or waive the granting source's restrictions.
Original Order97 observations, clause bytes and historical assertions remain unchanged.

The owner supplied the complete operative Shadow of Anarch text attributed to the
approved canonical40k.app Banishers URL, plus its1CP cost. The exact paste and
message identities are [retained separately](../data/source_audits/order119/user-supplied-shadow-of-anarch.txt).
This is user-supplied transcription provenance. No successful direct fetch,
current complete-page capture, App-data version or authoritative faction package
is claimed. The official July22 Grey Knights PDFp9 supplies the8-inch amendment
only. No new provider or source authority registry row is admitted.

Shadow of Anarch grants either a6-inch Normal move or, with Deep Strike, removal
into Strategic Reserves after an enemy Normal/Advance/Fall Back move in the
opponent's Movement phase. It cannot grant both alternatives in one use. The
prior move needed for this Core clause therefore uses a separate provider
permission in that same opponent Movement phase. An earlier own-turn move would
not establish the selected clause.

This order follows Order114's conditional Core consumer precedent. Canonical
fixtures provide explicit independent typed permissions and prove the accepted
consumer path. The existing `test:order80:reactive-normal` fixture permission is
not represented as a newly discovered Grey Knights rule. Named timing,
range/keyword/Deep Strike eligibility,CP payment,activation and the complete
playable Grey Knights two-source sequence remain deferred. Existing named
faction activation scaffolds stay load-only, including their historical metadata.

## Shared consumer and evidence

`MovementRepositionContext` binds a source rule,permission effect,occasion,
target rules unit,actual turn player,round and Movement phase. A source provider
issues the corresponding typed persisting permission after satisfying its own
granting conditions. The finite Core request offers decline or entering Strategic
Reserves. It does not manufacture that permission from Core20.02 or prior movement.

Both accepted finite and parameterized reactive movement completions may offer
the current source permission. The existing movement owner records the witnessed
Normal Move and actual opponent turn before the independent removal choice.
The source consumer revalidates its live permission,physical context and offered
options before queue pop. It consumes the occasion on acceptance or decline.

Acceptance uses the existing `GameState.reposition_unit_to_strategic_reserves`
owner,group-aware battlefield departure and reserve lifetime policy. A typed
source-permission provider binds the accepted decision,source terminal,provider
terminal and Primary departure evidence. Restore uses that same binding through
the existing reserve-source and departure audits. Prior movement records and
unexpired effects retain their existing owners; no movement history is synthesized.

## Validation and delivery

Appended regressions in `tests/unit/test_order80_normal_move.py` cover finite and
parameterized witnessed prior moves,ordinary and attached rules units,accepted
reserve removal,decline,stale permission before queue pop,checkpoint continuation
and exact replay, both viewer projections and actual Movement-end permission expiry. Original gameplay assertions and branches are preserved. The exact original movement test Git blob is retained in a bounded Order119 historical-input mapping for the immutable Order97 inventory.

Final covered behavior,complete quality,types,lint,contracts,shards,package checks,
serial current-runtime smoke,two distinct exact-head reviews,full hosted CI and
protected merge remain required. Delivery counts are recorded only after their
actual successful execution. This is an ordinary permission/consumer branch
change,not an optimization or full-game performance certification.
