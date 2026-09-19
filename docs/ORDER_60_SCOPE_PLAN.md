# Order 60 / P18B — Emergency Disembark maximal closest placement

## Invariant and source

Emergency Disembark is a Set Up. Each surviving model must be set up wholly
within 6 inches of the destroyed Transport and as close as possible to that
Transport. An unengaged set-up is required when one exists. An engaged endpoint
is legal only when no unengaged 6-inch set-up exists. A model is destroyed only
when it still cannot be set up after that engaged fallback.

The complete 18.05 while-moving placement text was retrieved from the 40k.app
Transports page. The separate `gw-11e-core-emergency-disembark-placement`
source package records the complete wording, reviewed obligations, immutable
observation and package hashes, typed placement policy, execution consumers,
and the historical official Core Rules source hash. The official 18.05 rule ID
`gw-11e-core-rules:transports:emergency-disembark-move` remains the
corroborating identity in the Core Transports package. The maintained-mirror
source policy and registry authorize this Core-Rules-only observation. No
second-provider agreement is asserted.

Contact counts as overlap, so legal set-up is an open set. Closest-possible
proof uses the pinned 0.04-inch tolerance instead of an open-set strictly-closer
query. Exact circular existence uses `visibility_algebra.decide`; unresolved
geometry raises rather than inventing a rules answer. Non-circular bases raise
rather than approximating. Endpoint-only set-up is allowed because this is Set
Up, not a path move. Existence proofs include axis-aligned wall legality and
keep 3D engagement, overlap, and coherency authority. A terrain-free SAT
result is not a legal alternative. Non-cardinal walls that can meet the search
region raise unresolved geometry rather than declaring the proposal illegal.

R60-003 and the remaining R60-001 floor case fail closed: any floor whose
horizontal bounds can meet the searched passenger footprint raises unresolved
geometry before the planar solver returns a verdict. This check deliberately
does not filter by the passenger's elevation. An omitted model's synthetic
ground pose cannot rule out survival on a supported upper floor. The current
solver does not certify floor collision, support permissions, or overhang;
complete elevated placements and closest/unengaged queries near floors also
remain unresolved. Floors wholly outside the search region do not block proof.

## Ownership and proof

`geometry.emergency_disembark_fit` owns the exact circular existence query.
`engine.emergency_disembark_placement` owns source-authorized omitted-model,
closest-possible, and unengaged-preference proofs for both a single unit and an
attached rules unit. `transport_disembark_geometry` skips shared Engagement
Range rejection for ordinary Emergency models so the engaged fallback can be
proven, and keeps Order 55's unengaged-only oversized 1-inch exception.
`destroyed_transport_rules_unit_disembark` proves omitted attached survivors
before filtering the view used for grouped coherency. `transports._resolve_disembark`
remains the public mutation owner and still destroys only models omitted from a
valid placement. No new player-facing decision, named handler, or alternative
mutation path is introduced.

## Audit and scope

The bug-class search found the same arbitrary-subset destruction on the attached
rules-unit Emergency path: the grouped resolver filtered to placed models before
validation. That path now proves omitted living survivors against the complete
attempted set. Ordinary, Rapid, Tactical, Combat, Assault, and Shock Disembark
are unchanged except that Emergency no longer inherits a blanket Engagement
Range reject for ordinary bases. P18C still owns hazard-before-placement.

## Validation and contract

Regressions cover closest-ring set-up, rejection of a placeable omission,
rejection of a non-closest pose, rejection of engaged set-up when unengaged
exists, destruction of a genuinely unplaceable oversized model, attached
rules-unit complete placement, GameLifecycle restore, rejection of a
terrain-free closer pose that lies inside solid walls, and acceptance of
contact-ring set-up beside vertically separated enemies. This PR adds no option
family, proposal kind, or visibility change.

The follow-up regressions establish endpoint legality independently for all
five survivors at z=6 inches, reject omission certification through both proof
entry points, and prevent floor-slab interiors from proving closer placement.
They check unchanged lifecycle payloads after unresolved results and retain
passing wall, elevated-enemy, and distant-floor cases. The bug-class search
traced all `_pose_exists` calls: omission, closest, and unengaged preference
share the guard. The existing adapter contract covers this domain error; no
proposal shape, source identity, or mutation owner changes.
See [performance and final gates](performance/order60/README.md).

Reproduce the source with
`uv run python tools/build_core_emergency_disembark_placement_source.py --check`.
