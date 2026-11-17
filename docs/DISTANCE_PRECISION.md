# Distance precision contract and rollout status

## Explicit legacy policy binding

New registered Linux executors use `linux-execution-profile-v2-numerical-policy`
and explicitly declare `legacy-binary-inch-v1`. This ID names the existing
unrounded binary-inch execution semantics; it does not claim that every internal
calculation is floating point. `NumericalPolicyConfiguration` is immutable, and
only that policy is admitted. The configured policy and registered profile are
checked before launching an authority. Missing, unknown and
`milli-inch-half-away-v1` policies fail closed. Inspection alone still does not
register an executor or authorize gameplay.

`LinuxGameSession.numerical_policy` exposes the selected authority configuration.
Its opaque persistence and replay envelopes bind the policy through the complete
execution profile, profile hash and envelope content hash. The authority-owned
checkpoint cache separately keys the policy ID, execution-profile hash and exact
inner checkpoint hash. Profiles are detached from caller-owned dictionaries so a
caller cannot relabel an existing session or cached envelope. Restoration and
replay require the exact registered profile before decoding the inner payload.

This is the outer identity slice. Inner `GameConfig`, lifecycle, decision/event
streams, replay artifacts, geometry/spatial witness hashes and the native
`LocalGameSession` persistence format retain their existing bytes and semantics.
The unprofiled native API remains the existing legacy path; it does not accept a
new numerical mode. Retained profile-v1 envelopes require their original compatible
executor. The generic envelope byte utility can preserve those original bytes,
but that preservation does not admit them on a new profile-v2 executor. Explicit
legacy enrollment retains its required provenance receipt and strict inner
validation; no loader infers a replacement profile or migrates history.

Geometry input canonicalization, policy-aware geometry/spatial hashes and geometry
cache keys remain prerequisites for admitting another numerical mode. Their
recorded legacy identities are deliberately unchanged here, including the
historical explicit reconstruction recipe. The paused Fight evidence remains
historical and unmodified. Linux remains authoritative; native Windows numerical
equivalence and project-wide milli-inch rounding are not established by this slice.

## Staged canonical circle input and topology prerequisite

`geometry.milli_inch_circle.CanonicalCircle` is an inactive input boundary for
closed circular disks. It canonicalizes signed centre coordinates and the source
full diameter once; an odd diameter deliberately derives an exact half-tick radius.
Decimal, binary-float and millimetre sources retain the arithmetic foundation's
interpretations. Centres fit signed 64-bit ticks and diameters range from one to
`2**63 - 1` ticks. Invalid, collapsed or out-of-range inputs raise typed errors.
The immutable representation has strict `milli-inch-circle-v1` payloads and a
hash covering the complete payload, including `milli-inch-half-away-v1`.

Circle queries use integer squared distances without a tolerance or backend.
`relation_to` distinguishes separated disks, external contact and interior overlap;
containment, coincident disks and internal tangency count as interior overlap.
`surface_gap_ticks` rounds the nonnegative surface gap exactly once, including
irrational centre distances and half-tick radius sums. It uses integer square root
and an exact squared midpoint comparison, never a rounded intermediate distance.
A rounded zero gap can mean separation, contact or overlap and must not replace
the topology query. Scalar rule consumers must still use their own strict or
inclusive comparison against the returned canonical length.

This representation does **not** solve contact placement. External tangency on
integer-tick centres requires `4*(dx**2 + dy**2) == (d1 + d2)**2`. For diameters of
different parity the right side is congruent to one modulo four, so no integer
centre pair can satisfy it, even diagonally. The 1.000/1.001-inch pair therefore
remains an explicit activation blocker. Same-parity exact contact is supported;
no tolerance, snapped contact or overlap allowance is substituted for real contact.

No gameplay caller imports this API. Contact-attainable authoritative placement,
ovals/rotations, backend and solver agreement, inner policy and replay identity,
geometry/spatial caches and coordinated rules remain pending. Active sessions
retain legacy semantics and original historical bytes; Linux remains authoritative.
This slice does not establish native OS equivalence or new-mode gameplay admission.

## Staged canonical simple-ring input prerequisite

`geometry.milli_inch_polygon.CanonicalPolygon` is an inactive input boundary for
simple polygon rings without holes. It validates exact rational source coordinates,
quantizes signed coordinates once to integer milli-inch ticks, then validates the
canonical ring again. Decimal text and floats keep the source interpretations of
the arithmetic foundation; millimetres use the exact conversion ratio. The legacy
epsilon-based polygon implementation and all gameplay consumers remain unchanged.

Both validations reject duplicate vertices (including an explicit closing vertex),
zero area, adjacent backtracking/overlap and nonadjacent touching/intersection.
Snapping that collapses an edge, creates invalid topology or reverses winding is
rejected with a typed error. There is no automatic repair, vertex deletion or
reordering. Straight collinear continuation remains valid and retains its vertices.
Predicates use exact arithmetic, with no distance tolerance or geometry backend.

Canonical coordinates must fit signed 64-bit integer ticks; out-of-range inputs
raise a typed error before a canonical object exists. This explicit representation
bound keeps every accepted coordinate serializable without changing interpreter
integer-string limits.

The immutable tick-ring representation has strict payload version
`milli-inch-simple-ring-v1`, explicitly binds `milli-inch-half-away-v1`, and hashes
the full canonical payload. Loading rejects missing/extra fields, other versions or
policies, noninteger coordinates and invalid topology. Payloads are detached from
caller-owned lists. Ring starting vertex and winding remain significant identity;
the hash does not claim geometric equivalence between reordered rings.

This API does not admit a new session policy, alter gameplay geometry/cache keys,
or resolve legal contact placement. Inner session/replay policy identity,
circle/oval contact representability, rotated primitives/backend and solver
agreement, geometry/spatial cache integration and coordinated rule consumers are
still required before activation. Historical payloads and evidence keep their
original bytes and runtimes. Linux remains authoritative.

## Staged canonical polygon point queries

`geometry.milli_inch_polygon_queries` adds inactive exact queries against the
closed, filled `CanonicalPolygon` representation. `polygon_point_location`
distinguishes exterior, boundary and interior using exact integer sidedness and
half-open ray crossings, including concave rings and horizontal edges. Query
points must already be immutable signed 64-bit integer tick pairs; malformed or
out-of-range points raise `CanonicalPolygonError` without implicit snapping.

`polygon_point_distance_ticks` returns zero for interior or boundary points. For
exterior points it selects the minimum exact rational squared distance to the
closed ring segments, then rounds that derived length once through the shared
squared-length arithmetic. Projection parameters, projected points and individual
edge lengths are never quantized. Irrational distances use exact squared midpoint
comparisons, without a float square root, epsilon or geometry backend. Derived
lengths may exceed the signed coordinate bound. Exterior points can also have a
rounded zero distance, so the measurement never establishes contact or containment.

These functions leave canonical polygon payloads and hashes unchanged and have no
gameplay callers. Other primitive pairs, off-grid
contact placement, rotation/backend/solver agreement, inner identity and caches,
and coordinated rules remain activation prerequisites. The legacy-only session
policy, Linux authority, historical replay evidence and paused Fight experiment
retain their existing semantics and bytes.

## Staged canonical polygon-pair queries

`geometry.milli_inch_polygon_pairs` adds inactive exact queries between closed,
filled `CanonicalPolygon` rings. `polygon_polygon_relation` separates disjoint
sets, boundary-only contact and interior overlap. Containment and coincidence are
interior overlap. Proper crossings, winding-aware shared edges and rational
midpoints of boundary intervals handle concavity, collinear continuation and rings
whose vertices all lie on the other boundary. The existing internal point locator
accepts exact rational samples; its public point API still requires integer ticks.

`polygon_polygon_distance_ticks` returns zero for contact or interior overlap.
For separated rings it selects the minimum exact rational squared endpoint-to-
segment distance across all edge pairs, then rounds the derived length once.
Projections and interval samples remain exact and off-grid. A separated pair can
have a rounded zero gap; that measurement never establishes contact. Inputs must
be canonical polygons, and derived lengths may exceed the signed coordinate bound.
Queries preserve polygon payloads and identities and use no epsilon or backend.

This is a prerequisite, with no gameplay callers or newly admitted session mode.
Other primitive pairs, contact-attainable placement, rotations/backend/solver
agreement, inner policy/replay identity, caches and coordinated rules still block
activation. Original source producers, payloads and historical evidence remain
unchanged. Linux remains authoritative; native OS equivalence is not established.

## Selected exact-coordinate contact slice

The next representation contract is `rational-quadratic-coordinate-v1`, implemented
by `geometry.exact_coordinate` and `geometry.exact_contact` as inactive geometric
APIs. Scalar measurement retains `milli-inch-half-away-v1`. This deliberately
amends the candidate integer-coordinate restriction for derived contact poses;
it does not admit a new numerical execution profile or change source-number
decoding. Existing `CanonicalCircle`, `CanonicalPolygon`, authoritative `Pose`,
legacy sessions, adapters, saves and replays keep their original contracts.

An exact coordinate in inches is either a reduced rational or `a + s*sqrt(q)`:
`a` and positive nonsquare `q` are reduced rationals and `s` is exactly -1 or +1.
The sign selects the positive or negative real root, and rational square roots
are folded into the rational form. Rational zero has numerator 0 and denominator
1, root sign 0 and radicand 0. Numerators and positive denominators are strict
integers with at most 256 bits; booleans, floats, unreduced payloads, unknown keys
and noncanonical roots fail with typed errors. The constructor absorbs a rational
root coefficient into its squared radicand, so `2*sqrt(3/5)/3` and `sqrt(4/15)`
have identical payloads. A quadratic irrational's conjugate trace fixes `a`,
after which the signed radicand is unique. Root expressions, isolating intervals
or arbitrary polynomial syntax alone would not provide this numerical identity.

This choice is smaller than general minimal-polynomial real algebraic numbers
while handling the next concrete dependency. A finer fixed grid still misses
irrational contacts; rational coordinates alone still miss `sqrt(4001)/2000`.
Floating-point poses or rational approximations cannot supply exact topology.
General real algebraic coordinates could handle repeated higher-degree derived
placements, but require minimal-polynomial normalization, certified root ordering,
resource bounds and agreement with existing solver/backend consumers. No such
generality or workload qualification is claimed here.

Exact arithmetic is closed within one quadratic field and includes rational
translations, products, reciprocals and sign comparisons. Radicand ratios with
rational square roots identify the same field without integer factorization.
Mixed fields and intermediate canonical values exceeding the 256-bit component
contract raise `UnsupportedExactCoordinateError`; no approximation or snapped
answer follows. These deterministic finite resource bounds replace an unbounded
symbolic search for this API. They are operational limits, not proof that every
ordinary contact formation is represented. Comparisons against derived rational
measurement boundaries use exact temporary fractions without imposing stored
coordinate limits on those boundaries.

`ExactDisk` retains a canonical full integer-tick diameter and derives the radius
exactly. Its strict envelope and SHA-256 identity bind the scalar policy,
coordinate representation version, exact center and diameter. Restoration
revalidates the selected witness and preserves its original exact value; it does
not pass it through source quantization. This is local primitive identity only.
Execution profiles, authoritative poses, geometry/spatial caches, decision/event
identity, persistence and full replay must bind the representation version before
integration. This slice does not create or reuse an authoritative cache.

The finite two-rational-anchor constructor returns zero, one or two selected
simultaneous-contact centers in a deterministic oriented order. Coincident or
nonrational anchors are explicitly unsupported. Returned disks establish only
the specified pair contacts; they do not establish terrain clearance, other
model clearance, mutual anchor legality or an ordinary legal placement.

Direct regressions establish the 1.0005-inch rational tangency and both documented
source-valid approach controls, off-axis irrational tangency, and simultaneous
contact with diameter-1000 anchors at `(-1,0)` and `(1,0)` by a diameter-1001 disk
at `(0,sqrt(4001)/2000)`. From `(0,2)`, the whole straight descent is nonoverlapping.
The analytic certificate minimizes squared center distance over every parameter
of the segment; an endpoint-legal path through a disk is rejected. Its immutable
result binds start/end hashes, contacts and both policy/representation IDs.
It is not an engine `PathWitness` and is not accepted by any gameplay validator.
Complete straight travel is rounded once by exact squared half-tick comparisons,
even when the travel's square root would have degree four. No intermediate point,
radius or segment is independently rounded. Arbitrary polyline sums require
their own certified measurement path and are not supplied by this API.

Activation checklist item 2 is partially discharged for these finite constructions
only. General supported primitive queries, rotated/oval and backend/solver
agreement, repeated derived placements, mandatory engine full-path witnesses,
inner profiles/hashes/caches, coordinated rules, persistence/replay and shared
adapter qualification remain open. Only `legacy-binary-inch-v1` remains executable;
Linux remains authoritative. Historical bytes, producers and paused Fight work
are preserved. No native Windows/Linux engine equivalence is established.


## Finite activation checklist and next contact decision

The implemented arithmetic, outer policy binding and canonical circle/polygon
queries remain inactive prerequisites. New-mode gameplay may be admitted only
after all of these concrete obligations are completed and independently reviewed:

1. **Primitive geometry:** complete the supported circle/polygon and oval/rotated
   shape queries, including exact contact/overlap and once-rounded derived lengths.
   Establish agreement between analytic predicates, geometry backend operations
   and exact/symbolic solver witnesses, including concave and degenerate boundaries.
2. **Attainable legal placement:** resolve the coordinate-contract conflict below
   through an explicit owner decision, then implement the chosen complete contact
   representation. Demonstrate ordinary legal contact-required moves, multi-contact
   formations and mandatory full-path witnesses without tolerances or overlap.
3. **Inner identity and retention:** carry numerical policy through GameConfig,
   lifecycle, decisions/events, replay identity, geometry/spatial hashes and all
   dependent cache keys. Reject unknown/mixed policies and stale cross-policy
   caches. Qualify engine-generated valid-state save/load/full replay while retaining
   original legacy bytes, producers, compatible runtimes and explicit enrollment.
4. **Coordinated rule consumers:** switch each owning movement, range, engagement,
   coherency, placement and contact consumer together with its strict/inclusive
   threshold contract. Quantize complete derived lengths once; keep topological
   contact, intersection and overlap separate from rounded zero measurements.
5. **Shared adapter authority:** version source-number decoding and canonical input
   boundaries, route ordinary UI/headless/network decisions to the same Linux
   authority, and prove Windows and Linux clients preserve its canonical payloads,
   witnessed decisions, checkpoints and replay. Do not infer native OS equivalence.
6. **Explicit admission and qualification:** admit the completed policy only after
   exact-final-head coding and supervisory reviews, applicable source/generated/
   contract/performance checks, complete covered behavioral qualification with 32
   local workers (meeting the at-least-twelve requirement) and 67% full-package branch coverage, all required
   hosted checks, and verified main CI. Keep 1,620-second inclusive approval,
   termination only above 1,800 seconds, and all other existing limits unchanged.

The next dependency-blocking question is the representation of exact contact
placements. The user's requirement rounds distances and distance-related values
to 0.001 inch; it does not explicitly require stored coordinates to lie on a
0.001-inch grid. The staged contract above imposes that stronger integer-coordinate
choice. Exact derived authoritative poses are a candidate amendment to that
representation contract, while retaining the same half-away rounding of measured
lengths. The selected inactive quadratic contract and finite proofs are implemented in
the preceding section. Authoritative-state integration and gameplay admission
remain incomplete.

For canonical full diameters of 1.000 and 1.001 inches, retain the exact derived
radii 0.500 and 0.5005 inches. Centres `(0, 0)` and `(2001/2000, 0)` inches are
exactly tangent: their 1.0005-inch separation equals the radius sum. The rounded
centre-separation measurement is 1.001 inches, while the exact surface gap is zero.
Centre separation illustrates the arithmetic; it is not a generic rules-range
metric. Each rule must use its specified geometric distance and comparison.

Two source-valid geometric approach controls make the movement boundary concrete.
Keep the 1.000-inch circle stationary at the origin and approach on the positive
X axis with the 1.001-inch circle:

| Moving centre initially | Exact final centre | Exact straight travel | Once-rounded travel | Inclusive 1.000-inch budget |
|---|---|---|---|---|
| `(2.000, 0)` inches | `(1.0005, 0)` inches | 0.9995 inches | 1.000 inches | Passes this distance condition |
| `(2.001, 0)` inches | `(1.0005, 0)` inches | 1.0005 inches | 1.001 inches | Fails this distance condition |

Both initial pairs are separated, and both straight approaches remain nonoverlapping
until exact endpoint tangency. These are finite geometric controls, not terrain,
phase or ordinary engine-admission proofs. Real moves still require their complete
mandatory path witnesses and every applicable legality condition. Measure the
complete path before its one rounding step, rather than summing rounded segments.

Exact topology must consume the exact poses. For scalar distances, with nonnegative
distance `d` in ticks and integer threshold `T`, preserve the distinct midpoint
boundaries: `Q(d) <= T` iff `d < T + 1/2`; `Q(d) < T` iff `d < T - 1/2`;
`Q(d) >= T` iff `d >= T - 1/2`; and `Q(d) > T` iff `d >= T + 1/2`.
The nonnegative domain remains required, including zero thresholds. These are
length comparisons, not squared-distance or topology predicates. A positive gap
below half a tick rounds to zero and still does not establish contact.

A finer fixed grid is not a general solution. A half-tick grid represents the
horizontal example, but with the same radius sum and a horizontal centre difference
constrained to exactly 1 inch, tangency requires vertical difference
`sqrt(4001)/2000` inches. That value is irrational, so no finite decimal grid or
rational-only coordinate representation captures it exactly. Arbitrary rotations, general multiple-contact formations, backend conversion and
solver agreement remain unqualified. The preceding section declares the finite
rational/quadratic domain and its simultaneous-contact controls.

The implemented inactive quadratic slice supplies strict typed rational
numerator/positive-denominator forms, validated quadratic root selection, canonical
identity, deterministic serialization and bounded typed unsupported results.
The next dependency is integration of that explicit domain with authoritative
state and mandatory engine witnesses; general algebraic representations remain
a separate unresolved scope. Preserve an accepted exact
witness on restoration; never round it again as though it were new source input.
Explicitly bind the representation version through the numerical execution profile,
pose/geometry/spatial hashes, caches, persistence and replay. Choose that versioning
design deliberately: changing the coordinate representation does not by itself
require changing the scalar rounding semantics or their policy ID, but all affected
identity boundaries must distinguish incompatible representations. The staged mode
remains unadmitted, and the current legacy-only authority/native paths cannot
silently accept it. Retain original legacy bytes, hashes, producers and compatible
runtimes. No fuzzy contact, overlap allowance, dimension inflation, independently
re-rounded radius or silent snapped fallback is permitted.

## Staged symbolic measurement prerequisite

`geometry.milli_inch_symbolic` now supplies a separate, inactive exact path
measurement API. `symbolic_squared_path_inches_to_ticks` accepts nonnegative
rational squared segment lengths, certifies every irrational square root with
exact nonnegative dyadic enclosures, and locates the complete sum's half-tick
bin with bounded exact solver checks. Integer square roots supply the enclosures;
live rational squared inequalities certify them. The solver disproves the bin's
complement over every value in those bounds using linear real arithmetic.
Individual segments are never rounded into the measured result.
Rational-only paths retain exact total-first rounding, including exact ties.
Subdivision and segment order do not change a successfully certified result.
The retained `squared_path_inches_to_ticks` API still explicitly rejects
irrational roots; callers must deliberately select the new API.

`rounded_length_constraint` encodes all four strict/inclusive scalar comparisons
against nonnegative integer-tick thresholds. It includes the nonnegative length
domain and the distinct upper/lower midpoint inclusion rules, including a zero
threshold. Its input is a length expression, never a squared distance or area.
Free-variable declarations and geometric certificates remain the caller's duty.
These scalar constraints do not establish contact, overlap or collision topology.

The path API has a shared bounded deadline (10 seconds by default); exhausted
time or an unknown solver result raises `UnresolvedDistanceMeasurementError`.
An unresolved calculation never returns an approximate measurement or legality
answer. It supports sums of square roots of rational squared lengths, not arbitrary
algebraic expressions or unbounded future gameplay workloads.

No production gameplay caller imports this module. Inner identity, canonical
geometry inputs, geometry/spatial hashes and caches, ordinary contact
representability and coordinated rule consumers remain activation prerequisites.
Only the existing legacy numerical policy remains executable. Historical saves,
replays, evidence and profiles retain their original bytes and semantics, and
Linux remains authoritative. This slice does not claim native OS equivalence.

Scheduling admits this exact symbolic module/test source tuple through a finite
successor to the precision-profile admission. The prior covered baselines,
evidence, source transitions and selector placements remain unchanged. Fresh
source-bound Linux covered evidence supplies current observations; twelve shards,
67% full-package coverage with branch measurement enabled, 1,620-second inclusive
approval and termination only above
1,800 seconds remain required. Scheduling admission does not activate a numerical
policy or qualify native OS equivalence.

## Staged milli-inch numerical policy

`milli-inch-half-away-v1` defines the new distance arithmetic foundation. It is
**not active gameplay or a replacement for `battlefield-coordinate-v1`** in this
slice. Existing sessions, proposals, legality predicates, persistence and clients
continue under their registered runtime. Importing the new pure arithmetic module
does not opt a session into new semantics. Activation requires the remaining coordinated
inner identity and geometry changes below; clients must never opt in by
rounding an existing payload themselves.

The policy quantum is exactly `1/1000 inch`. A canonical length or signed
coordinate is an integer number of ticks. Round to the nearest tick; an exact
halfway value rounds away from zero (`0.0005 -> 0.001`,
`-0.0005 -> -0.001`). Zero has one canonical representation. Arithmetic uses exact
rational comparisons, without epsilon or the ambient Decimal context. Decimal
source text is interpreted exactly; an already decoded binary floating-point
number denotes its exact binary ratio, not an inferred decimal string. Thus a
decimal-looking float need not be a mathematical tie. A future wire decoder must
choose and version its source-number interpretation before canonicalization.
Booleans and nonfinite numbers are invalid inputs.

Dimensional rules for activation:

- Canonicalize authoritative positions, local offsets, polygon vertices, board
  extents, terrain heights, model dimensions, movement budgets and rules-distance
  thresholds at their owning input boundary. Convert millimetres using the exact
  ratio `25.4 = 127/5` before the single quantization step. Keep original catalog
  source dimensions and provenance unchanged.
- Select a primitive's source dimension once. For a source diameter, canonicalize
  the full diameter and derive its radius exactly; an odd tick diameter has a
  half-tick internal radius. Do not independently round both diameter and radius.
  Internal analytic geometry, rotated vertices and algebraic witnesses may remain
  off-grid. Quantize a requested derived length at its defined measurement
  boundary, rather than repeatedly quantizing intermediate arithmetic.
- Lengths and coordinates have dimension one. Squared distances have dimension
  two and are compared exactly against squared half-tick boundaries to obtain a
  length; do not round a squared distance as though it were inches. Areas,
  volumes, angles, normals, interpolation parameters and dimensionless solver
  variables are not milli-inch lengths. Preserve their declared units and exact
  relationships.
- Measure an entire path before quantizing its total once. Never sum rounded
  segment lengths or repeatedly round a running total. The foundation supports
  exact rational segment lengths and rational square roots. The staged symbolic
  API now certifies sums of rational square roots at the final rounding bin;
  other algebraic path sums still require their own certified implementation;
  an unsupported calculation must raise an explicit error. Subdividing the same
  geometric path must not change its measured total. Continue validating every
  segment and mandatory path witness.
- Range, engagement, coherency and other scalar-distance rules will compare
  canonical measured length and canonical threshold using the rule's actual
  strict or inclusive operator. For a nonnegative raw length `d` and integer tick
  threshold `T`, `Q(d) <= T` means `d < (T + 1/2)/1000`, while
  `Q(d) >= T` means `d >= (T - 1/2)/1000`. Therefore exact midpoint inclusion
  differs between the two bounds. Exact/symbolic predicates must encode these
  same bins, including ties; keeping old exact threshold predicates while only
  rounding displayed measurements would be incorrect.
- Overlap, intersection, sidedness, connectivity, and true base contact remain
  topological predicates of the canonical input primitives. A rounded zero gap
  does not establish contact and never permits an overlap. Snapping can collapse
  an edge or change a polygon's topology; reject invalid canonical geometry with
  a typed diagnostic before mutation. Do not silently repair rings or remove
  path segments. Rotated shapes require agreement between analytic predicates,
  the geometry backend and solver certificates.

Activation must first resolve contact representability on the coordinate grid.
For example, circular diameters of 1.000 and 1.001 inches require a centre
separation of 1.0005 inches for true tangency, which no pair of integer-tick
coplanar centres can represent. The activation design must explicitly reconcile
coordinate quantization with legal contact placements and prove ordinary
contact-required moves remain attainable, without inventing a contact tolerance,
treating rounded zero as touching, or permitting overlap. Source-defined proximity
and deemed-contact rules remain separate predicates with their own thresholds and
evidence; they are not a general substitute for true contact. The selected inactive quadratic slice above resolves these finite contact
examples; authoritative-state integration and activation remain incomplete.

Activation is dependency ordered: first this tested arithmetic foundation; then
the explicit outer policy binding described above; then coordinated inner identity,
geometry input, measurement, topology and exact/symbolic rule consumers; finally Windows and
Linux client qualification against the registered Linux authority. Each slice
requires its own exact-head reviews and CI. The active policy must participate
in geometry/spatial hashes and cache keys, and be carried through events and
replay identity before new-mode sessions are admitted. Mixed or unknown policies
must fail closed. Existing cache entries cannot be reused across policies.

Historical histories, envelopes, hashes, evidence and runtime profiles retain
their original bytes and semantics. Loading one requires its explicitly retained
compatible runtime and profile, never a rewritten history or a silent migration.
Adding foundation code changes the packaged build fingerprint even though no
gameplay consumer is switched; that new fingerprint must not impersonate an old
registered executor. Preserve the old checkout and dependencies for old sessions.
Linux remains the execution authority. Windows and Linux clients must submit the
same ordinary viewer-scoped decisions and preserve the authority's canonical
payloads. Integer arithmetic portability alone does not prove native geometry,
solver or whole-game cross-platform equivalence.

Before activation, qualification must cover signed and unsigned ties, exact unit
conversion, squared and algebraic measurements, strict/inclusive thresholds,
contact versus overlap, path subdivision and accumulation, collapsed topology,
profile/hash/cache separation, valid-state persistence/full replay, and both OS
clients. Until those gates pass, this section specifies the target semantics and
the implemented pure foundation, symbolic measurement prerequisite and outer
legacy-policy binding only; it makes no
project-wide rollout claim.
