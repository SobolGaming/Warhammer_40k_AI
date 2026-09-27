# Order 90 / P01J — off-battlefield revival

Violated invariant: Core 01.02.03 preserves the source's returned wounds and the
model's starting equipment. A returned model belongs to its receiving unit's
location: embarked returns consume Transport capacity, and reserve returns remain
unplaced until legal ingress. Neither return invents battlefield geometry.

## Source and ownership

The committed `core_revival_2026_09` package retains the complete reviewed
01.02.03 clause, including full Wounds and starting wargear/Enhancements by default,
and the no-destruction-trigger exception when an embarked return exceeds capacity.
The `core_embarked_abilities_2026_09` package supplies 01.02.04 ability availability
and the self-range exception. Existing immutable official provenance and maintained
App-mirror observations are preserved. These are the existing selected source
observations, not a new claim about the latest official App version. Reproduce:

```sh
uv run python tools/build_core_revival_source.py --check
uv run python tools/build_core_embarked_abilities_source.py --check
```

`healing` owns the existing finite model choice and dispatch. Its new extracted
`healing_off_battlefield` owner reads explicit canonical reserve/cargo state,
checks every living attached component, and validates army, battlefield and cargo replacements
before mutation. It uses the same `revival_wounds_remaining` source query as
battlefield placement: ordinary healing returns one wound, explicit full-health
sources return Starting Wounds. Wound replacement retains the existing model's
wargear IDs, keyword assignment, source IDs and component/Enhancement ownership.
No model is recreated and no equipment selection is repeated.

The return request privately commits the actual phase/turn, cargo or reserve
state, and occupied cargo count. Stale location, capacity or phase changes reject
before queue pop. A successful return removes only the casualty's removal marker;
it creates no pose, path, setup record or battlefield transition. Cargo aboard a
reserve Transport retains cargo ownership. Capacity failure leaves zero wounds
and the removal marker, consumes the healing step and emits no destruction trigger.
A destroyed Transport cannot authorize a fresh embarked return. Returning a wholly
destroyed attached Leader restores its physical cargo membership and, for an
unarrived carrier, its reserve-route membership through the same checked route
replacement used by destruction reconciliation. Immutable attached lineage and
phase-start cargo history are retained. Initial reserve declarations bind canonical
cargo rules-unit lineage; current cargo lists continue to bind exact living physical
components. The shared disembark eligibility query uses the receiving rules unit's
phase-start cargo history, so a returned Leader can leave with its unit without
inventing historical model presence.

The same-class search covered all return mutations and every consumer of
`revive_model_embarked`: destruction/restoration history, Fight physical authority,
Primary physical history and Daemonic Manifestation source/continuation validation.
They now distinguish `revive_model_in_reserves` and preserve living-but-unplaced
history. Restore binds successful return wounds to the accepted source; capacity
failure binds the recorded selection, zero wounds and capacity outcome. The shared
phase-start helper bypasses battlefield anchor collection only for authenticated
off-battlefield units. Orders 82/83 battlefield coherency and engagement checks
remain on the ordinary placement branch.

## Adapter and acceptance

The existing `select_healing_model` finite family handles every non-spatial return,
including a single candidate. The new reserve step token and private location
snapshot fit Contract 40's opaque payload schemas; no schema or submission-envelope
change is required. Shared adapter redaction removes `revival_location` recursively
from public requests, decisions, status and events. Exact runtime identity rejects
old saves; no compatibility shim or migration of existing histories is introduced.
The adapter contract documents the changed payload semantics. A private
`off_battlefield_revival_history_origin` retains the independently validated
pre-return lifecycle before the first accepted non-spatial choice. Restore replays
from that root, binding completed location, phase, capacity, source and later ingress
claims to actual state. Missing roots and jointly forged request/event mirrors fail
closed. This follows the existing lifecycle history-origin owner; no transport or
reserve history is inferred from the final model pose.

The regression matrix covers one-wound/full-health embarked and reserve returns,
attached cargo capacity, no destruction triggers on failure, source-loaded Command
restoration, stale/invalid finite submissions, restored source-wound tampering,
viewer redaction, persistence, exact replay, and later ordinary/attached reserve
ingress and Tactical Disembark. Canonical checkpoint fixtures retain real recorded casualties and explicit
cargo/reserve state. Their off-battlefield location is fixture setup, not a claim
that the preceding embark/reserve journey was replayed. The Command consumer uses
the existing source-backed Tears of Isha IR bound to canonical attached fixture
models and loaded through the catalog/lifecycle path; it does not inject a handler.

Performance and final checks are recorded in [the validation record](performance/order90/README.md).
Core Rules and complete-game performance certification remain separate work.
