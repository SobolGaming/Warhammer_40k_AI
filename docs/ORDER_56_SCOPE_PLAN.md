# Order 56 / P24C2 implementation and scope audit

Status: implementation and all required local validation complete; ready for PR review.
Base: `6a5e84f1f402a9aa0f0839d31c2fabec37f5f06e` (Order 55).
Branch: `codex/order-56-duplicate-ability-selection`.
Finding: `C24-03B`, building on C24-03A source occurrence identity.

The owner approved the prerequisite expansion: canonical Core family identity at
catalog ingress, a complete weapon inventory before Select Weapons, and native
and granted Core ability consumption. A local Anti-only change could not satisfy
24.02 because materialization discarded/rejected other duplicates and modifiers
could add sources after the decision inventory was emitted.

## Invariant and ownership

The controlling player selects one source occurrence of a duplicated Core or
weapon family. Different numbers, keywords and identical definitions do not
create independent stacking families. Sources retain their physical ownership,
source IDs and provenance. Weapon choices are made for each attack occasion at
Select Weapons and remain fixed through target replacement.

`core.core_ability_family` normalizes Core family identity once at the data
boundary. Engine consumers use that typed family. `core.weapon_ability_sources`
owns the shared descriptor/keyword mapping and source-preserving grants.
`engine.ability_instance_selection` owns exact-one-per-family validation and
profile projection. `weapon_selection_context` freezes native and applicable
granted sources across targets before Shooting and Fight requests are emitted.
The existing adapter proposals commit the selection; validation, pools, execution,
events, persistence and replay use the shared engine path.

Persistent Core selections use `select_core_ability_instance`. Native and live
grant inventories cover numeric and boolean families. Feel No Pain reuses its
source choice. Mandatory Deadly Demise chooses exactly one source without a
decline option, including attack and rule-destruction continuations. Source
materialization preserves every native occurrence. Repeated Deep Strike grants
retain source records even when the keyword is already present. Unit splitting
retires the old active choice and lets each successor select its own occurrence.

Scouts keeps all universally shared values and the lowest unshared value. Both
mixed 6/8-inch and universally shared 6/8-inch cases are covered. Dedicated
Transport cargo uses the same calculation without a minimum-value shortcut.

Restore binds selected Core state, pending choices, weapon pools and Deadly
Demise events to the recorded decisions and sources. Setup Core decisions and
events use the existing shared secret-payload redaction path. Contract 26 records
the source-instance ID change, melee selection field, new finite decision and
persistence/replay versions; older deployments remain required for older saves.

## Scope and architecture audit

The affected responsibilities were extracted from frozen datasheet, lifecycle,
Fight, prebattle and catalog-consumption modules before extension. New modules
remain below the 1,500-line cap. No dependency boundary, named-handler budget,
faction support, excluded content, AI, or compatibility fallback is introduced.
Conditional Lone Operative continues through its existing source-backed generic
hook. Source-family normalization includes Core grants whose catalog origin is a
datasheet. Melee retains the complete offered inventory after target selection.
Request-scoped target inventories and reuse of authenticated rules-unit views
inside generic effect queries avoid repeated identity work without persistent
caches or changed work budgets. Physical model/component evidence and attached rules-unit identity remain
separate.

Bug-class searches covered native damage materialization, numeric Core helpers,
keyword grants, conditional model grants, weapon modifiers, split melee,
Firing Deck, reaction attacks, target replacement, grouped attacks and destruction
continuations. The scope remains the approved duplicate-selection invariant.
Existing fixtures changed deterministic seeds where request/event payloads changed
the history-dependent RNG stream; required casualty and continuation assertions
were preserved.

## Evidence

The complete operative 24.02 observation remains unchanged:
`gw-11e-core-duplicated-abilities:duplicated-abilities`, retained observation hash
`4a37e2adbecc617bc913a16d9548f68f895393887bdc9f6e33fcea33fa11da49`.
The offline source builder updates execution consumers and semantic status while
preserving source text, transcription hashes and historical official provenance.

Focused checks cover native/granted and equal-value choices, conditional source
applicability, malformed and stale choices, finite adapter submission, source
round trips, restored state, replay, mandatory destruction continuation and
Scouts movement. See [performance and final validation](performance/order56/README.md)
for measured results and the final gate record. Performance evidence is a matched
component diagnostic; complete-game targets and deferred budgets are not certified.
