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
evidence; they are not a general substitute for true contact. This foundation does
not choose or activate that representation.

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
