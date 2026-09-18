# Order 58 / P05D — incoming Damage-to-0 applies after the saving throw

## Invariant and source

When a unit has a rule that changes the Damage characteristic of an incoming
attack to 0, that change applies after the allocated model's saving throw, not
before it. A successful save still prevents damage. A failed save may replace
the incoming Damage with 0 and skip infliction. Replacement Damage other than 0
fails closed. No consumer may change that incoming Damage characteristic before
the save roll.

The complete v931 FAQ question and the answer "After." were retrieved from the
Game Datamissions Core Rules Data Changelog with App-data 931 selected. The
separate `gw-11e-core-failed-save-damage-timing` source package records the
complete Q+A, reviewed obligations, immutable observation and package hashes,
typed post-save policy, execution consumers, and the historical official Core
Rules source hash. The maintained-mirror source policy and registry authorize
this Core-Rules-only observation. No second-provider agreement is asserted.

## Ownership and proof

`engine.failed_save_damage_timing` owns the source-authorized unused
replacement. Grouped allocation remains the mutation owner: it resolves the
saving throw first, consults the unused replacement only after a failed save,
emits `failed_save_damage_replaced` with the FAQ source rule ID, and skips
`_damage_value` plus allocated-attack Damage modifiers when replacement
applies. Weapon Damage modifiers and no-save Devastating Wounds mortal paths
are not this FAQ.

The real catalog consumer remains first-failed-save Damage replacement
(Channeller Stones / Aeldari Corsair Voidscarred) through
`CatalogDatasheetRuleRuntime.failed_save_damage_replacement_bindings` and
`RuntimeModifierRegistry.failed_save_damage_replacement`. Once-per-turn unused
tracking stays event-log based. No new player-facing decision, named handler,
or alternative mutation path is introduced.

## Audit and scope

The bug-class search found one mutation consumer of
`failed_save_damage_replacement()`: grouped allocation, now routed through the
timing owner. Allocated-attack Damage modifiers still run only after a failed
save that did not replace Damage. Attacker-side weapon Damage modifiers are
outside this FAQ. Synthetic test bindings do not survive
`GameLifecycle.from_payload` bundle rebuild; completed wounds and replacement
events do.

## Validation and contract

Regressions cover failed-save Damage-to-0 with unchanged wounds, successful
saves with no replacement, ordinary failed-save infliction, once-per-turn
unused tracking, allocated-modifier skip, non-zero replacement fail-closed,
owner rejection of a successful save, adapter complete-phase submission,
viewer-scoped event streams, and GameLifecycle restore. This PR adds no option
family, proposal kind, or visibility change.
See [performance and final gates](performance/order58/README.md).

Reproduce the source with
`uv run python tools/build_core_failed_save_damage_timing_source.py --check`.
