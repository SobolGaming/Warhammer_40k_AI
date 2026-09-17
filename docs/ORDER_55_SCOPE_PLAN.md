# Order 55 / P03B — oversized disembark placement

## Invariant and source

A disembarking model may use the one-inch base/hull placement exception only
when its base is too large to fit wholly within the applicable ordinary setup
distance beside its Transport, at any translation or rotation. The exceptional
model must remain unengaged. Other models do not inherit its exception, and
coherency, battlefield edges, overlap, terrain and objective restrictions remain
mandatory.

The complete 03.02.02 text was reviewed through the indexed
[40k.app Moving page](https://www.40k.app/rules/03-moving) on 2026-09-17;
direct retrieval returned HTTP 403. The separate `gw-11e-core-large-model-disembark`
source package records a short excerpt, the reviewed obligations, immutable
observation and package hashes, typed policy, execution consumers and the
historical official Core Rules source hash. The maintained-mirror source policy
and registry authorize this Core-Rules-only observation. No App build number or
second-provider agreement is asserted. The mode's ordinary distance remains
three or six inches; a five-inch base can qualify for the three-inch exception
while fitting the ordinary six-inch band.

## Ownership and proof

`transports._resolve_disembark` remains the physical validation and result owner.
Its existing endpoint responsibility was extracted from the frozen oversized
module into `transport_disembark_geometry`. Ordinary, Assault, Shock, Combat,
destroyed-Transport and Emergency modes, and each attached component, all reach
this same function. The rules-unit resolver still checks aggregate coherency and
commits every component atomically. Hazard rolls, casualties, permissions and
movement histories remain owned by their existing services.

The pure `geometry.disembark_fit` query asks whether a convex analytic base can
be translated and rotated into the Transport's closed distance band without
interior overlap. It ignores congestion deliberately: blockage does not prove
oversize. Minimum-width and diameter bounds prove impossible cases; explicit
tangent placements and conservative rational polygons prove possible cases.
Cargo polygons enclose the analytic base, and Transport chords lie inside the
analytic hull; failed certificates never become negative answers. Ellipse/circle
cases use the S-lemma to express both containment and separation as positive
semidefinite constraints. Remaining cases quantify over every cargo point and
pose through the existing exact real-arithmetic authority. Unknown/interrupted
calculations raise a domain error and never authorize placement. Contact counts
as an ordinary fit, including at exact size thresholds.

The 512-entry cache contains only immutable base, Transport footprint and distance
inputs. Position, facing, terrain, casualties and other units cannot affect this
size-only question. Every proposed endpoint still recomputes distance, engagement
and all other physical checks from current state. No cached endpoint permission,
new player choice, named handler or alternative mutation path is introduced.

The one-inch endpoint limit uses `Model.range_to`, the shared closest-volume
measurement combining horizontal base/hull distance and vertical separation.
The review regression places the canonical five-inch passenger on a supported
five-inch ruins floor: its 0.5-inch horizontal gap is insufficient because its
3D distance is about 1.92 inches. Just-below, exact and just-above one-inch
boundaries cover both vertical-only and diagonal separation. Terrain support and
coherency pass independently; rejected endpoints carry only the distance error.

## Audit and scope

The bug-class search found one unconditional whole-footprint distance check shared
by all physical/component paths. The repair is there, including suppression of
Combat/Shock's ordinary engagement permissions for the exceptional model. The
ordinary three/six-inch policy is preserved. The extracted canonical enemy rules-
unit lookup remains covered by the existing static physical-identity audit.

The vertical-distance bug-class search found one shared consumer of the oversized
one-inch policy. All its callers receive the same 3D correction, with a static
audit against reintroducing horizontal-only measurement there. Separate ordinary
whole-footprint and Embark distance policies are outside this exception's scope.

Order 60's maximum-survivor/closest-placement Emergency policy, Order 62's Shock
engagement-owner source resolution and Order 63's ingress propagation remain
separately scheduled work. Order 55 does not certify or alter those policies.

## Validation and contract

Regressions cover exact size and one-inch boundaries, alternative orientations,
rectangular hulls and ellipses, actual transport size, three/six-inch cache keys,
all seven disembark modes, prohibited engagement despite mode permissions, mixed
attached components, invalid endpoints, malformed/wrong-context rejection, pending
and completed restore, both players' views/event deltas and exact replay.
Pre-pop invalid-submission diagnostics are retained as checkpoint history;
DecisionRecord replay separately covers selection, rejected placement, retry and
successful setup.

The existing placement proposal, finite mode, violation and event payload shapes
cover this engine-derived exception. No client-supplied exception assertion is
accepted. The adapter contract documents the semantics; the runtime build identity
and generated contract examples are refreshed without a public schema change.
See [performance and final gates](performance/order55/README.md).

Reproduce the source with
`uv run python tools/build_core_large_model_disembark_source.py --check`.
