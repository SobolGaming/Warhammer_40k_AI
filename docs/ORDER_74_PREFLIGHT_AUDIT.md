# Order 74 / PFINAL preflight — mandatory movement proof gap

Reviewed base: `54284173293238ea417a1eb1cb0351843a442998` (main, Order 73).
Review date: 2026-09-22, America/New_York.
Status: **blocked before complete 25-category certification**. CAUDIT-01
remains open. This is an execution finding, not a whole-corpus compliance
certificate or a selected App-version snapshot.

The local and fetched remote main agree. PR #493 is merged and the remote
open-PR inventory was empty. Historical descriptions of Orders 72/73 as
unmerged are stale delivery metadata, not remaining dependencies.

## C03-03 — incomplete mandatory movement feasibility proofs

Approved owner: **P03C**, a shared movement-proof prerequisite to PFINAL,
covering its Charge, Consolidation and Surge consumers. On 2026-09-22 the owner
selected "Implement the P03C prerequisite PR" after reviewing this finding.
P03C becomes Order 74; PFINAL moves to Order 75. The sections below retain the
pre-implementation observations; implementation and validation follow them.

The required invariant is that supported Core movement obligations can be
resolved through the shared engine decision path. A bounded search miss must
remain unresolved, but a fail-closed diagnostic does not establish complete
semantic execution. PFINAL forbids outstanding partial in-scope semantics.

The shared `geometry.movement_reachability` implementation can prove a
distance-bound impossibility and can validate a discovered alternative path.
It cannot prove ordinary obstacle-induced impossibility after its finite
navigation search fails. Charge, Consolidation and Surge all consume that
same incomplete proof owner. The existing Order 47 and Order 52 scope
records explicitly retain this limitation.

### Executed facade reproduction

The audit constructs real canonical five-model units, a typed Dense terrain
feature with one wall, authenticated fixture placement/Command history and a
`LocalGameSession`. Finite source and target choices and the movement proposal
all go through the existing facade. Source-linked generic test modifiers set
a 3.75-inch movement budget; no validator/controller is replaced or stubbed.

- The trailing model starts at `(10, 20, 0)`; its four peers start at
  `(11.4, 21, 0)` through `(15.6, 21, 0)`.
- Five enemy models stand at `(10, 26, 0)` through `(15.6, 26, 0)`.
  All ten models have 32 mm circular bases.
- The wall has center `(10, 24, 0)`, width 0.8 inches, depth 0.4 inches
  and height 5 inches.
- The target is **actually offered and selected by the engine**, at
  3.740157480314961 inches from the charging rules unit, within its 3.75-inch
  budget. This avoids the target-eligibility limitation of the older
  low-level Order 47 test.
- Each charging model follows a complete three-pose path 3 inches forward.
  All path and terrain validators pass; the final group is coherent.
  Every model ends closer and engaged with the selected target. No other
  enemy is engaged. Four models finish within one inch of the target.
- The trailing model finishes at `(10, 23, 0)`, 1.740157480314961 inches
  from the target. Its one-inch feasibility is `unresolved`.
- Facade submission returns `invalid` / `charge_reachability_unresolved`,
  preserves placement, records the rejected attempt and issues a fresh request.

The record is in
[`reports/order74/charge-facade.json`](../reports/order74/charge-facade.json),
reproducible locally with
`uv run --no-sync python -m reports.order74.probe_charge`.
These ignored local audit files are retained for the scope decision; they
are not claimed as committed certification artifacts or a new behavioral
test file.

### Independent impossibility argument

Let `r = 16 / 25.4 = 0.6299212598425197` inches. To finish within one inch
of the first enemy, the trailing model's center must be within
`1 + 2r = 2.2598425196850394` inches of that enemy's center.

Even ignoring every path obstacle, a 3.75-inch budget restricts any such
endpoint to `23.74015748031496 <= y <= 23.75` and
`abs(x - 10) <= 0.27151799653808506`. That entire interval lies inside the
wall's horizontal width `[9.6, 10.4]`; its gap to the wall's near face at
`y = 23.8` is at most `0.059842519685041395`, less than `r`.
Every candidate endpoint therefore intersects the wall. Its bottom cannot
reach the wall's top at 5 inches with a 3.75-inch movement budget.
This argument allows transit through the wall and still rules out every
endpoint, so Infantry traversal permissions do not supply an alternative.

The nearest other enemy's center is 6.161168720299745 inches from the
trailing model's start, greater than `3.75 + 1 + 2r = 6.009842519685039`.
The triangle inequality excludes that and every more distant enemy even
without obstacles. Thus the trailing model cannot reach the one-inch
condition, while the proposed move satisfies its other obligations.
The audit's arithmetic assertions and the engine's actual rejection are
retained together in the reproduction output.

### Source authority

The browser directly displayed 40k.app 11.04 on 2026-09-22. Its per-model
one-inch clause is unchanged from the retained Order 47 reviewed obligations:

> Each model that can end its move within 1" of one or more charge targets must do so.

| Field | Retained implementation evidence |
| --- | --- |
| Stable source ID | `gw-11e-core-charge:model-endpoints` |
| Provider | 40k.app, non-affiliated maintained App-data mirror |
| URL | `https://www.40k.app/rules/11-charge-phase` |
| Observation | `2026-09-14T14:09:27.140Z`; no App-data version asserted |
| Retained short-excerpt transcription SHA-256 | `f89a63e4c03d60eb727523f3d3894a3bb550507939eaddf3cf145f6257d86191` |
| Audit source-observation fingerprint | `3c40e1d82103df43d9a12af5de9cb266954ec8e183bea83efd5bc2524fa47e8d` |
| Reviewed obligations | All five endpoint obligations recorded in `data/source_audits/maintained_app_mirrors/charge_2026_09_14.audit.json` |
| Historical official Core PDF SHA-256 | `f6a2443a44627ac5f0ef08407d29aa5ec7e97339998f05bc35f3ae37bf276833` |

The retained excerpt hash is not claimed to hash the freshly quoted clause
or the complete page. No old observation, package, registry or implementation
status was altered. No co-versioned mirror agreement or official App capture
is asserted. The web fetcher returned HTTP 403 and a direct HTTP request
returned 429; the browser rendered the relevant clauses successfully.

### Owning path and same-class search

Reviewed Charge source -> finite declaration/target decisions -> parameterized
`ChargeMoveProposal` -> `resolve_charge_move` -> per-model
`charge_model_endpoint_witness` -> `movement_reachability` ->
`charge_reachability_unresolved` -> rejected decision record and fresh proposal.
Accepted mutation/events, restore and replay cannot certify the blocked move.

The complete repository call-site search finds these production consumers:

| Consumer | Required proof | Unresolved outcome |
| --- | --- | --- |
| `engine/charge_model_endpoints.py::_reachability` | Per-model one-inch and engagement feasibility | `charge_reachability_unresolved` |
| `engine/consolidation_model_constraints.py::consolidation_model_violation` | Per-model required enemy/objective endpoint | `consolidation_reachability_unresolved` |
| `engine/surge_movement.py::surge_endpoint_evidence` | Engagement feasibility and maximal approach | `surge_reachability_unresolved` |

The engine's existing rejection protects against invented answers. It must
remain in place for computations that are genuinely unresolved. Merely
increasing the search cap, returning `unreachable` on exhaustion, or bypassing
the requirement at one consumer cannot close this finding.

The Charge failure was executed through the facade. Consolidation and Surge
are confirmed shared call sites and documented proof limitations; this
preflight does not claim to have reproduced a failing facade case for each.

### Proposed prerequisite acceptance

1. Add failing regressions for the demonstrated legal Charge and representative
   same-class Consolidation/Surge cases before changing production code.
2. Extend the shared proof owner to resolve the supported obstacle/endpoint
   cases while retaining full PathWitness validation, terrain/support,
   collision, coherency, engagement, per-model authority and typed unresolved
   outcomes. Determine the smallest complete supported geometry scope before
   implementation; do not claim universal completeness from finite tests.
3. Exercise ordinary and attached units, shared Charge hosts, facade rejection
   and acceptance, stale proposals, both viewers, checkpoint authentication,
   JSON-safe evidence and exact replay. Keep existing consumer contracts or
   update/version their changed evidence explicitly.
4. Assess matched base/head performance and bounded-cache correctness. Preserve
   source provenance and truthful partial/executable support reporting.
5. Run all required aggregate/generated/contract/client/package gates, publish
   and merge the prerequisite, then repeat PFINAL's complete audit on main.

This is a gameplay algorithm change across three phase consumers, materially
broader than an audit/certification PR. `AGENTS.md` requires: "If the required
solution is materially broader than the apparent request, pause before
broadening it." The roadmap additionally says: "If the audit discovers any
gap, do not open or certify PFINAL."

## Validation and remaining work

Two existing focused regressions passed in 24.41 seconds, with no coverage:

- `test_charge_distance_continuation.py::test_order47_obstacles_use_validated_paths_and_never_grant_an_unresolved_exemption`
- `test_visibility_pathing.py::test_mandatory_endpoint_search_never_treats_unresolved_search_as_impossible`

They intentionally assert unresolved results; their success demonstrates
fail-closed behavior and the execution gap, not Core compliance. JUnit is
retained at `reports/order74/known-unresolved.xml`. The additional facade
probe completed with the rejected outcome and unchanged placement described
above. Initial probe setup errors were corrected before that result; they
are not attributed to production defects.

At the end of the preflight, no production code, behavioral test file, generated identity, contract or
shard manifest changed. Full behavioral coverage, aggregate code-quality,
type, lint, generated-contract/client/package and performance gates have
**not** been run for this preflight. No final PR or compliance claim is made.

Categories 07/11 and source availability received partial inspection only.
The remaining all-category clause/FAQ inventory, selected snapshot,
September 10 consumer certification, all v931/v946 closures and CAUDIT-01
closure remain outstanding. Neither this finding nor merging its repair
substitutes for that complete audit.

## Approved implementation

**Invariant and scope.** C03-03 is the demonstrated obstacle-excluded endpoint
class, not a claim to complete continuous motion planning. The smallest complete
repair belongs to `geometry.movement_endpoint_proof`, called by the shared
`movement_reachability` owner after direct validated paths and before navigation.
Charge, Consolidation and Surge continue to use that owner. There is no new named
handler, source-text parsing, mutation path or dependency boundary.

The proof quantifies continuous endpoint x/y/z over a relaxed translation ball.
Circumscribed base/target disks include every facing of circles, ellipses and
rectangles; polygon goals use enclosing rectangles. Spatial range becomes a
relaxed horizontal/vertical conjunction. Small disks strictly inside the moving
base and rotated wall footprints provide sufficient collision constraints. Their
radii are half the model's analytic inradius and half the wall's inradius, so
polygonal collision footprints cannot create a false exclusion near tangencies.
Rational arithmetic and outward slack keep the candidate region conservative.
The existing exact real-arithmetic solver may prove this region empty. A nonempty
region is inconclusive, and solver errors propagate as typed geometry errors.

Only walls belonging to a terrain feature and present in the actual terrain
validation context constrain the proof. Walls sharing a floor support identity
are relaxed away, matching the endpoint authority's support permission. A red
regression exposed this edge case during scope review before aggregate gates;
the corrected regression also requires an actual validated reachable witness.
Floors, support planes, raw volumes,
other models and coherency are relaxed away. The proof allows vertical escapes,
including free vertical distance when that capability applies. It never declares
a feasible endpoint reachable: the existing full PathWitness, terrain, collision,
coherency and per-model checks still validate every accepted path.

The new `endpoint_unreachable` evidence is distinct from the existing distance
proof. Historical Charge and Surge validation recompute it against reconstructed
event-time geometry and authenticated movement context. Existing schemas already
carry these nested evidence values as JSON; the adapter contract documents the
new token without changing player choices or visibility. Source IDs, source
package bytes and the immutable observations above are unchanged.

**Limits retained explicitly.** A nonempty relaxed endpoint domain can still have
no legal path. Such a navigation miss remains `unresolved`. Surge must independently
prove maximum approach even after engagement is excluded; its new regression
verifies that exclusion alone cannot waive that obligation. The finite examples
do not certify all obstacle arrangements or full Core compliance. These limitations
remain explicit inputs to the fresh PFINAL audit; no support manifest is upgraded
by this repair.

**Regression and class search.** The new legal Charge facade regression failed
with `charge_reachability_unresolved` before production changes. It now exercises
acceptance, stale-request rejection without mutation, both viewer event streams,
JSON-safe evidence, checkpoint restoration, forged statuses and exact replay.
An actual Consolidation resolution exercises the same blocked endpoint class.
The Surge regression protects its separate maximum-approach obligation. Geometry
regressions cover all three base families, spatial/engagement/marker/polygon goals,
terrain ownership and removal, changed height/target/budget, and vertical flight.
Existing attached-unit, reactive Charge, path, unresolved and history regressions
remain applicable. A static audit requires the three consumers and both history
validators to retain shared proof ownership.

**Delivery.** The reviewed architecture changes one new geometry module and four
existing runtime modules. Behavioral regressions extend existing test files;
the named fixture helper is not a collected test file. Shard membership remains
unchanged. Runtime identity and contract examples are regenerated. Matched
base/head measurements and final gate results are retained under
`docs/performance/order74/`; complete-game performance remains unmeasured.


## Final validation

The final runtime is `warhammer40k-core-v2:runtime-tree-sha256-v1:710cdbd8455ee52cf66f3be6f52c1ed1ea4722345a2dfba283c548c74a7ebaf9`. The complete behavioral
suite passed **8,790 tests with 85.18% coverage**;
the complete code-quality suite passed **588 tests** without coverage.
Both used 64 xdist workers and work stealing. No production code changed
after these aggregate gates began. Required lint, formatting, typing, imports,
shard inventory, pre-commit, source/build/contract checks, installed-wheel smoke,
TypeScript tests and 342 live HTTP conformance assertions pass. Ten focused
performance evidence guards pass against the unchanged declared budgets.

See [machine-readable validation](performance/order74/validation.json) and
[qualified performance evidence](performance/order74/README.md). This closes the
scoped prerequisite implementation for review, not CAUDIT-01 or PFINAL.
