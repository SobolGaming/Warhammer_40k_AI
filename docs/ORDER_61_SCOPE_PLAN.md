# Order 61 / P18H — same-turn setup and Embark

## Invariant and source

18.02 forbids Embark after a unit was set up on the battlefield during the
current turn. The rule applies to every Transport, every setup route, both
players, and later phases of the same turn. A source exception changes only
the restriction it explicitly names. The maintained 40k.app 18.02 text and its
18.02.01 clarification were read on 2026-09-19. The complete operative 18.02 row,
provider, URL, observation time, transcription and observation hashes are retained
in `core_embark_setup_turn_2026_09` and its maintained-mirror audit. The package
has a typed, eagerly validated policy and source-authority registration. No
second-provider agreement or official ownership of the mirror is asserted.

## Ownership and bug-class audit

`PhaseMovementRecord` already owns accepted Disembark and reinforcement setup,
including the arrivals used by repositioning. Its required `setup_kind` now
distinguishes those placements from ordinary and reactive witnessed movement.
The round and actual turn player determine expiry; the moving unit's owner is
not the turn clock. Restore reconstructs records from completion events after
independently authenticating return-on-death setup classification.

`transport_embark_validation` is extracted from the over-budget `transports`
module. Its required typed history and turn arguments are supplied by both
post-move option enumeration and acceptance. Canonical unit identity and living
physical model IDs preserve the restriction through attached-component changes
and identity reconciliation. `transport_embark_prevalidation` invokes the same
predicate before a finite choice leaves the queue. The mutation owner remains
the ordinary movement service. Reactive movement has no separate Embark mutation
path; its completion cannot erase earlier setup authority. Return-on-death also
records setup when the canonical rules unit had no living models before return.
Its completion carries the actual turn owner and a derived setup flag. Restore
checks that flag against the shared model-authority timeline, whose accepted
decisions, pending occurrences, destruction causes and reversible model
mutations establish whether any member of the rules unit was alive immediately
before the return. The accepted pending target selects the canonical rules unit;
the completion's unit ID must agree. Historical model lineage includes attached
components and catalog model history. Returning one model to a surviving unit
does not create unit setup history, even if that survivor dies later.

R61-001 exposed coordinated edits to the completion flag and stored phase
history. Regressions now reject both erasing whole-unit setup and inventing
setup for a model returned to a surviving unit, including later destruction and
completion target substitution. No new event snapshot or boolean supplies the
independent authority. The bug-class search found this flag's only history
consumer in `completion_phase_record`; lifecycle restore authenticates it before
reconstructing phase history. Other setup routes retain their typed placement
transition evidence.

The same bug-class search traced all `resolve_embark`, `with_embarked_unit` and
`apply_embark_to_battlefield` consumers. Pregame formation embarkation is before
the first battle round and remains a distinct setup operation. Model revival
within an already present unit is not a unit set-up. No new named handler,
generic hook family, faction content or alternative adapter path is added.

## Contract and validation

Contract 27 versions the required private history field and the new typed
`embark_after_setup_forbidden` diagnostic. The ordinary finite/parameterized
submission envelopes and viewer redaction remain shared. R61-001 strengthens
restore validation within that existing contract and adds no payload field,
decision family or viewer-visible behavior. See
[the migration](../contracts/migrations/26-to-27.md) and
[performance evidence](performance/order61/README.md).

Reproduce source data with
`uv run python tools/build_core_embark_setup_turn_source.py --check`.
