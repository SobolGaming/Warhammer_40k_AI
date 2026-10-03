# Order 111 / P09D: friendly Monster and Vehicle transit

This order implements C09-04 in the shared witnessed collision policy. A Monster
or Vehicle's ordinary restriction on moving through friendly Monster/Vehicle
models applies to Normal and Advance moves. Other move types retain ordinary
friendly-model transit. This permission never allows an overlapping endpoint,
changes enemy transit or Engagement Range rules, supplies extra move distance,
or removes a separately supplied source-specific model exclusion.

## Selected authority

The retained Order97 observation is
`faq:9b1c81f5-2ea0-40eb-9015-6a005367cd75`, source SHA-256
`f3c9e8b3182c4e2071fac4e28a5f24038296b51c1e9815e075078612dfa184ee`,
in `data/source_audits/order97/selected-sources.json`. Its literal question is:

> While making a move type other than a normal/advance move, can my
> MONSTER/VEHICLE unit move through friendly units?

Its answer is **Yes.** The question block SHA-256 is
`3b8e37cd0c10fc27da63249a4f4af11fd314d49b8695cb561ee54d6a7fcd229c`;
the answer block SHA-256 is
`cf87b23d0f70cff8f9ce62b411ad616fd9be0b93edeba67c70f647e5a4b848e1`.
This is the existing selected Game Datamissions mirror observation, not a new
official publication or an invented App version. Historical Order97 source rows,
negative observations, assertion receipts and the open CAUDIT-01 remain intact.
The roadmap's shorthand “unqualified friendly-VEHICLE permission” must be read
with this literal move-type condition and its MONSTER subject.

## Owner and consumer trace

`MovementLegalityContext.to_path_validation_context` owns conversion of
source-backed movement capabilities and the declared movement mode into the
geometry layer's collision policy. Previously its friendly Monster/Vehicle
blocker list survived for every mode when no special transit ability applied.
It now clears that ordinary blocker list outside Normal/Advance. Existing
capability exceptions, source-specific blocker lists, enemy flags, distance
budgets and endpoint geometry remain on the same shared path.

The bug-class search traced all consumers: Movement-phase Normal/Advance/Fall
Back (`movement_resolvers`), Charge (`charge_path_contexts`), Fight paths and
source-component validation (`fight_movement_paths`, `fight_movement_source`),
Consolidation feasibility (`consolidation_model_constraints`), Scout's Normal
move (`scout_movement_paths`), reactive movement's declared mode
(`triggered_movement_resolution`), and reconstructed contact authority
(`base_contact_fight_history`). The geometry validator independently rejects
endpoint overlap. Set-up placements do not acquire a movement permission.
Take to the Skies retains its own selected flight permissions.

The retained default-core-index probe and new shared-context matrix reproduce
eight source-invalid rejections: Fall Back, Charge, Pile In and Consolidate,
for both Monster and Vehicle movers. This is not evidence that all corresponding
facade paths rejected: Fight consumers already omitted that blocker list, and
the canonical fixture's Movement-phase runtime ability index already allowed
its Fall Back. The facade regressions are positive controls for legal movement,
invalid overlapping endpoints, deterministic records and reconstruction; they
are not relabeled historical failures. No adjacent runtime-index policy is
changed in this order.

## Acceptance and delivery

`tests/unit/test_order111_friendly_transit.py` exercises all six ground move modes
for Monster, Vehicle and Infantry. Normal/Advance restrictions remain effective,
and the matrix separately checks enemy transit, forbidden endpoints, explicit
model exclusions and serialized path-context reconstruction. Real catalog and
model objects drive the session tests. Fall Back tests use ordinary parameterized
submissions, reject an overlapping endpoint without movement, then submit the
legal witness through an isolated fork and the original session. JSON persistence,
both viewer projections/event streams and exact replay retain the accepted state.
Pile In's facade path remains a legal-play control.

The existing adapter contract covers these finite selections, witnessed proposals,
invalid retries, movement events and viewer scope. No decision type, option family,
payload field or visibility behavior is added. Contract 44.2 remains current;
the runtime build manifest and generated external examples must be regenerated
for the changed engine identity. Existing saves/replays require their exact build.

The exact-base performance assessment uses the existing `movement-rule-branch`
operation and the mandatory serial current-runtime smoke. This is a source-backed
Boolean rule repair, with unchanged collision algorithms, sampling, caches and
serialization work. No deliberate performance optimization or full-game timing
certification is claimed. Complete local/remote gates and both independent
exact-head reviews remain delivery requirements, recorded in external evidence.

After this order merges, stop. Order112 begins from verified merged main in a new
session. Its own roadmap **How it is currently done** cell must describe its
actual implementation while retaining unrelated rows and historical evidence.
