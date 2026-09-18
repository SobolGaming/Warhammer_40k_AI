# Order 57 / P05C — measuring to a destroyed model or unit

## Invariant and source

When a player must measure to a destroyed model, the measurement uses the exact
former base, or any part of the model if it has no base or is a Vehicle
excluding Walker models that have a base. A destroyed-unit reference resolves
to the last model destroyed in that unit. The query grants no living
battlefield authority: occupancy, targeting, Objective Control, Engagement,
movement, and ability use remain independent of former-footprint measurement.

The complete 05.04.06 text was retrieved from the indexed
[40k.app Attack Sequence page](https://www.40k.app/rules/05-attack-sequence)
at `2026-09-18T12:05:00+00:00`. The separate `gw-11e-core-measuring-to-destroyed`
source package records the complete operative wording, reviewed obligations,
immutable observation and package hashes, typed policy, execution consumers and
the historical official Core Rules source hash. The maintained-mirror source
policy and registry authorize this Core-Rules-only observation. No App build
number or second-provider agreement is asserted.

## Ownership and proof

`engine.destroyed_referent_measurement` owns the source-authorized query.
Authenticated former placements remain recorded by P05B
`ModelLogicalDeathRecord.destroyed_model_placement`. The query reconstructs
closest-volume geometry through `geometry_model_for_placement`, which already
applies catalog `ModelGeometry` base or hull shapes. Vehicle/Walker wording is
not a runtime keyword branch.

A destroyed-unit lookup uses the canonical `RulesUnitView`, requires a logical-
death record for every destroyed model in that rules unit, and selects the last
chronological record. Living models, unknown IDs, missing or duplicate death
records, and unplaced source models fail closed.

Deadly Demise is the real 05.04.06 consumer: it measures from the destroyed
model to living units. `deadly_demise_target_unit_ids` now consumes event
records and uses current geometry while the model remains placed, or the
authenticated former footprint after removal. Attack-sequence and rule-
destruction continuations pass the same event log. Return-on-death continues to
use former placement as a placement anchor, not as range measurement.

No new player-facing decision, named handler, or alternative mutation path is
introduced. Adapter, UI, headless and replay paths keep the existing Deadly
Demise destruction-reaction contract.

## Audit and scope

The bug-class search found one shared Deadly Demise range enumeration that
previously required the exploding model to remain placed. Both attack-sequence
and rule-destruction owners now share the former-footprint query. Center-point
shortcuts, Vehicle/Walker keyword gates and living occupancy from a destroyed
referent were not introduced. P05B retained models remain present for ordinary
measurement; P05C former-footprint measurement is the post-removal path and
agrees with current geometry while the model is still placed.

Return-on-death synthetic tests destroy models without logical-death events, so
that consumer remains unwired. P05D Damage-to-0 timing remains separately
scheduled.

## Validation and contract

Regressions cover former-footprint equality with pre-removal closest distance,
last-destroyed-model unit resolution, hull catalog geometry versus a circular
base, fail-closed living/unknown/missing-death/unplaced-source paths, retained
still-placed agreement, Deadly Demise after removal, and GameState/EventRecord
payload restore. The existing Deadly Demise finite reaction remains the adapter
path; this PR adds no option family, proposal kind, or visibility change.
See [performance and final gates](performance/order57/README.md). Local
validation on 2026-09-18 recorded 8,348 behavioral tests at 85.12% coverage and
514 code-quality tests against runtime identity
`d320f72cceeb1dfaf39e200ebb3f3aa8775ba73fe49a9b794a8350a3ec088d8b`.

Reproduce the source with
`uv run python tools/build_core_measuring_to_destroyed_source.py --check`.
