# Section14 objective range repair

Core14.02 says terrain objective range is terrain-area membership. FAQ34 retains
membership above ground. The shared objective query incorrectly applied a
five-inch marker limit to terrain and ignored a declared based FRAME body.
Enabled native scoring and linked-area regressions failed before repair. A
separately labelled typed FRAME geometry contract also failed before repair.

The same cap existed in both mandatory objective movement goal builders. They
now share `objective_goal`. `MovementGoal.ignore_polygon_height` represents only
polygon membership, is strictly boolean, and is rejected for model/disk and
spatial-distance goals. Contains/lower-bound and conservative endpoint proofs
honour it. Exact query evidence serializes the required field without a fallback.
The nearest-physical-point search explicitly keeps finite height/distance semantics.
Marker range, path legality, collision, support, coherency and all existing
rejections remain independently enforced.

The change stays within existing engine-to-geometry dependencies. It adds no
decision, proposal kind, source permission or faction admission. The existing
adapter contract covers the same shared submissions and validation; internal
typed feasibility evidence has one additional mandatory field. See the contract
note appended in ADAPTER_DECISION_CONTRACT.md.

Validation is bounded to Section14 and relevant dependencies/contracts on Windows
and a separate verified WSL official CPython3.14.5 copy. No full legacy aggregate,
repository coverage threshold or hosted CI pass is claimed. Timings, same-runtime
serial smokes and matched local query measurements are diagnostic slice evidence.
No full-game or formal Git-base performance certification is inferred.

Original source/tests and all earlier evidence are preserved. The historical S18
ambiguity was resolved by the explicit user convention recorded below.

## SF14-004: physical scalar distance

The diagnostic horizontal and vertical minima can come from different declared
FRAME parts. Their hypotenuse is not a physical closest distance. The shared
objective query now requires actual scalar evidence: the existing marker context
measures paired parts, and terrain minimizes each subject/polygon 3D separation.
The scalar repair itself does not choose range membership. The subsequent R3
marker convention is separate. The old constructor fixture gains its required field, with its
original module archived and every original assertion/guard retained. No adapter
proposal or payload schema changes are introduced by this scalar-only revision.

## R3: user-resolved marker convention and current test reconciliation

The user explicitly chose one physical point satisfying both marker limits.
This is recorded as a human convention in the source audit, not invented official
wording. Body-measured markers use DistanceMeasurementContext.within_axis_limits;
ordinary single-base checks and terrain occupancy remain unchanged. Scalar closest
distance is unchanged and need not select the point witnessing cylinder membership.
Terrain Objectives remain the primary Event Companion game/training scenarios.

The current four-height test now separates marker and terrain expectations, with
every original assertion node intact. Historical modules and failures are retained.
No adapter schema, source permission, faction admission or compatibility shim is
added. Native compound-FRAME roster/body admission remains unproved.
