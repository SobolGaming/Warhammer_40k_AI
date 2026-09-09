# Order 32 / P06C / C06-03 review record

Status: implementation locally validated, with two sandbox-blocked HTTP tests
passed on a covered retry. Publication/CI status is reported in the PR. Earlier
failures and stalls remain documented below. This document does not assert
independent approval.
Performance certification is deferred by the owner's later direction.

## Starting point and scope

Base: `a1e66ec7d7c1ca05398e30d51ca61d1b62cd7332`.
Branch: `codex/order-32-certified-visibility`.
PR #435 is merged, including corrections from its final head
`dfdca891b011ed3583f54bba3db32acb2fa5058b`.
[Main CI attempt 2 succeeded](https://github.com/SobolGaming/Warhammer_40k_AI/actions/runs/34252154591).
Attempt 1 encountered HTTP 403 while listing coverage artifacts, before coverage
calculation. P06A (`dab7d128`, PR #410) and S-MIRRORS (`6b115220`, PR #416) are
verified ancestors. AGENTS, README, pyproject, the remediation roadmap, source
policies, relevant contracts/tests/generator documentation and active CI were read;
there are no nested AGENTS instructions.

The violated invariant is continuous any-part/every-facing-part visibility over
actual supported model geometry, preserving the flat 1mm corridor. The owner
approved the expanded analytic geometry, exact arithmetic, native solver and
versioned evidence scope after the baseline exposed deficiencies beyond endpoint
sampling. Geometry remains below rules/engine/adapters. The frozen visibility
module was extracted; every new module is below 1,500 lines. Movement/pathing,
new player choices, faction handlers and Order 33 rule changes are excluded.

## Approved source evidence

Policy: `core-rules-source-policy:maintained-direct-app-data-mirrors:2026-09-02`.
[40k.app 06 Other Concepts](https://www.40k.app/rules/06-other-concepts) was observed
at `2026-09-08T17:17:05Z`, including the model/unit definitions. The any-part FAQ
was observed with App-data **931** selected in
[Game Datamissions](https://game-datamissions.com/11th/rules/changelog?v=931).
The browser selection was checked because the initial web fetch displayed a
newer version despite that query string. Neither provider is GW-owned. The
40k.app page exposed no App-data version, so no co-version agreement is claimed.

`order32/source-observations.json` preserves the exact transcriptions and
observation hashes. The committed maintained-mirror audit is
`data/source_audits/maintained_app_mirrors/visibility_2026_09_08.audit.json`.
The source-authority registry authorizes the updated package and both supplemental
clauses. The original P06A visibility and P06B mortal-wound clauses and their four
evidence rows retain their original identities and metadata. The new clauses
have separate stable IDs; runtime consumer bindings follow the new core policy
owner without changing observation hashes. The two provider observations are not treated as
conflicting editions of a single transcription.

| Artifact / source ID | SHA-256 |
| --- | --- |
| `gw-11e-core-rules:other-concepts:visibility-classifications` transcription | `7bcd8275af066324fa6d6944e4683d632fe0b552a003fdc94190159a76fc89f4` |
| Its retained observation | `3d9aa5162350fa10f181ef8e49850ec7e606f1fb3cca576b93df60f117e229d4` |
| `gw-11e-core-rules:other-concepts:visibility-any-part-faq` transcription | `7ad46ec389adfa76cc3d0e3d763f6237835ae60a4264fbca52d48a97b79911ed` |
| Its v931 observation | `bc5eec60fa0cf2776b3c8cf50a86b7b3303acc47d4a1091adbce3b4c6907cae7` |
| Source package semantic hash, version `maintained-app-mirrors-observed-2026-09-08` | `d8b159dafe25df81c5a6caa0528e5a6814e6e335df85ae2014268b5e8331991c` |
| `core_other_concepts_2026_08/artifacts/package.json` bytes | `1c9c948d244a5709db7262907f3cba55edd390662873d3ac8b8ff088e207ee89` |
| Preserved historical official Core Rules PDF | `f6a2443a44627ac5f0ef08407d29aa5ec7e97339998f05bc35f3ae37bf276833` |

The source generator consumes these committed observations offline. Typed loaders
validate the exact artifact, package, clause and evidence identities, and resolve
recorded runtime consumers. Load support and executable semantics remain distinct.

### Quantifier derivation and Cover ruling

Let O and T be the supported observer and target volumes. Let C(o,t,B) mean that
the closed 1mm corridor from o to t misses every applicable blocker in B. Let
S(o,t) mean that the origin views the target part without passing through the
target's own interior, and F(O,T) be the surface parts with such an origin in O.
Applying the any-part rule to each part in the full-visibility definition gives:

- Model visible: `exists o in O, t in T: C(o,t,B)`.
- Model fully visible: `forall t in F(O,T), exists o in O: S(o,t) and C(o,t,B)`.
- Unit visible: at least one target model is visible to this observer model.
- Unit fully visible: every target model is fully visible to this observer model.

The observer may change between target parts. A blocked alternative origin does
not disprove full visibility. The observer and target rules units are excluded
from third-model blockers through group-aware engine presence APIs.

**COV32-01:** the owner answered, “Yes: terrain independently hiding the part is
enough.” The complete question, answer and limits are retained in
`order32/cover-disambiguation.json`. This is a project-owner interpretation, not
an official App observation. For selected sources A and remaining sources B,
terrain-caused incompleteness holds if A independently hides a facing part, or
if one and the same facing part is hidden by A+B and becomes visible after A is
removed. The latter existential observer choices are independently scoped.
Merely blocking another view of a still-visible part is insufficient. Every
model must independently satisfy an enabled Cover source/occupancy gate; disabled
area evidence cannot suppress or substitute for another model's valid evidence.

## Acceptance matrix

| Requirement / source | Observable behavior and boundary | Owner / consumers | Regression evidence |
| --- | --- | --- | --- |
| Any part; 06.01 + v931 FAQ | Unsampled valid opening permits targeting and a completed shot | Continuous geometry; shooting eligibility and declaration | `test_p06c_continuous_predicates_and_evidence_round_trip`; facade counterexamples |
| Every facing part; 06.01 classifications | Between-sample hidden part prevents full visibility and applies Cover | Target surface / self-valid origins; allocation Cover | Same geometry cases; facade Hit target number is 4 instead of BS 3 |
| Existential origin per part | A low wall does not defeat full visibility from higher origins | Cap and side domains; witnesses/Cover | Alternative-observer-origin and self-valid/tangent tests |
| Actual supported shapes | No phantom aperture for thin oval or rectangle; rotation retained | Analytic ellipse and polygon model domains | Phantom-aperture, oblique planar, curved blocker, transformed oval cases |
| P06A fixed corridor | Exact 1mm width, closed contact, flat caps, actual sloped height | Shared fixed-corridor kernel | Existing P06A regressions plus sloped strip, arc, vertical disk and cap cases |
| Terrain rules and 13.08 / COV32-01 | Enabled source group causes incompleteness; unit gate is per model | Context, exact area/feature policy, Cover and Hidden | Independent/joint/incidental sources, linked polygons, disabled-area regression |
| Orders 30/31 | Retained models keep physical presence, including retained-only observer components; observer/target keyword gates remain model-owned | Group presence, targeting, Cover, Hidden, cache identity | R32-001 facade regression for retained-only and attached observers, cleanup and ordinary casualties; heterogeneous firing-model allocation regression |
| Determinism and stale state | Cached/uncached answers and fingerprints agree; stale/forged evidence rejected | Bounded preparation/query caches and typed evidence | Geometry/keyword/policy replacements, eviction/reset, malformed exact evidence tests |
| Shared adapter/replay path | Legal shots, stale/malformed rejection without mutation, exact restored state and both viewers | LocalGameSession and unchanged shared adapters | `test_p06c_continuous_counterexamples_complete_shooting_and_exact_session_replay` |
| Performance | Preserve evidence; defer further optimization and provisional gates | Owner direction / versioned policy | Baseline and pre-deferral diagnostics retained; no full-game certification |

Tests above live in the existing `test_visibility_pathing.py`,
`test_phase13a_visibility_cover.py`, `test_phase18c_adapter_session_facade.py`,
`test_skull_altar_runtime_regressions.py`, shooting declaration files and source
identity tests. `tests/order32_visibility_helpers.py` contains canonical shared
setup, not a new behavioral test file. The eight-shard inventory check remains
mandatory; no test-file inventory change was needed.

## Counterexamples independently justified

Exact input payloads and baseline failures are retained in
`order32/base-a1e66ec7.json`; `scripts/probe_order32_visibility.py` is reproducible.

1. **Narrow opening:** radius-.5 models at (-3,0) and (3,0), height 2. Tall wall
   pieces occupy x=[-.05,.05], y=[-4,.1] and [.2,4]. The opening is .1in (2.54mm).
   The horizontal corridor y=.15,z=1 has .05in clearance on each side, exceeding
   the exact half-width 5/254in; its endpoints belong to both models. Baseline
   samples miss it and return invisible. The continuous result is visible.
2. **Partial occlusion:** radius-.001 observer (-3,0), radius-.5 target (3,0),
   height 2. Tall post x=[2.35,2.45], y=[.1,.2]. The facing point
   `(3-sqrt(.5²-.15²), .15, 1)` is hidden from the entire observer. Projecting the
   observer box through a post face stays within y=[.14526848,.14803015] and
   z=[.96866544,1.03133456], strictly inside the post. This proves obstruction
   even before adding corridor width. All 49 baseline samples are clear; the
   continuous result is visible but not fully visible.
3. **Invented parts:** length-1, width-.01 oval/rectangle models have Y extents
   only ±.005 and cannot reach an aperture y=[.45,.55]. The baseline max-radius
   samples nevertheless report visibility. For OvalBase(2,.2) at 45 degrees,
   sampled world point (1,0) has ellipse equation value 50.5, outside the model.
4. **Sloped height:** segment (0,0,0) to (10,0,10), obstacle x=[4,6], y=[.01,.02],
   z=[0,3.99]. The strip's plane has z=x, so every possible contact lies above
   the obstacle. The old longitudinally rounded height interval invents a hit.
5. **Alternative origins:** height-4 models can see all facing target parts over
   a low wall from suitable upper origins. Baseline full visibility incorrectly
   requires every sampled alternative origin to be clear.

The facade fixtures translate the first two geometries into a canonical real
battlefield, use catalog-bound model geometry, select the firing unit and Normal
Shooting, reject stale/malformed proposals, submit the legal declaration and
complete attack resolution. They inspect the Hit result and restore/replay the
whole session, comparing authoritative payloads and both viewers' projections
and event deltas. Geometry fixtures are not engine stubs.

## Geometry correctness argument

### Domains, arithmetic and boundaries

Supported footprints remain circles, analytic ellipses and oriented rectangles,
extruded over finite height intervals. Terrain/policy footprints are validated
simple polygons, including concave polygons and linked unions. Exact ear
triangulation retains their closed boundaries; union membership does not fill
holes. Visibility no longer uses inscribed Shapely circles or max-radius model
samples. Shapely remains available to its existing non-visibility consumers.

Finite input floats become their exact binary rational values. Cardinal rotations
are exact. Other rotations use the existing platform trigonometric values once,
then freeze those values as rationals; ellipse membership uses the actual inverse
axes rather than assuming their rounded columns are orthonormal. This specifies
exact assessment of the prepared geometry, not symbolic transcendental rotation
or universal bit identity across different libm implementations. Same code,
runtime, configuration and inputs produce the same logical result. No epsilon
changes an intersection answer. Bounds used for rejection are outward enclosures;
rational square-root bounds never redefine a shape.

The corridor half-width is exactly **5/254 inches**. For nonzero horizontal
length, its XY section is the finite perpendicular rectangle with flat endpoint
caps; height at each longitudinal parameter is linearly interpolated. Height is
clipped before XY intersection. A zero-horizontal-length corridor is a disk over
its height interval. Contact with a closed obstacle blocks, including tangency.

The fixed-corridor primitive evaluates polygon intersections in the quadratic
field generated by the segment's squared XY length. Ellipse contact reduces to
exact conic/segment predicates; the vertical disk/ellipse case uses a quartic
Sturm calculation that retains repeated roots, tangency and the omitted rational
chart point. Invalid axes, polygons, bounds and height intervals fail eagerly.

### Complete decision path

The authority first tries sufficient proofs: disjoint conservative enclosures,
clear observer caps, reflected parallel corridors for equal circles, or complete
blocking cross sections. Each returning proof establishes the whole asserted
predicate. A failed sufficient proof is unresolved, never the opposite answer.
Explicit endpoint candidates may prove existence only after exact membership and
corridor checks. A hidden target candidate disproves full visibility only after
covering **all** its self-valid observer domains, including applicable caps.
Failure to find either witness proceeds to the complete formula.

General endpoint formulas express model membership, self-facing target patches,
flat strip separation and analytic ellipse support with real polynomial
constraints. Convex polygon pieces and compact ellipses admit strict separation
exactly when disjoint. The side/cap partition covers the self-visible boundary;
rational ellipse charts include their end/omitted points. Curved tangent support
requires a displaced XY origin, so vertical-only tangency is not incorrectly
classified as a visible side. Caps require an origin strictly beyond their plane.

Existential formulas restrict to positive XY length. This loses no clear witness:
a clear vertical disk is compact and disjoint from finitely many closed blockers,
so it has positive clearance and admits a sufficiently small XY perturbation in
the positive-area observer footprint. A self-valid vertical view is through a
strict cap, whose validity survives that perturbation. The explicit primitive
still handles vertical queries directly.

For equal-height separated circular observer/target models and full-height
blockers satisfying checked projection bounds, the **planar line formula** is
complete. It uses line normal `(1-p², 2p)`, length `1+p²`, p in [-1,1], and an
offset. These parameters cover all unoriented lines. The line must meet both
actual disks; blocker support must be strictly outside the strip. Projection
preconditions make infinite-strip clearance equivalent to finite-strip clearance.
For full visibility, each target boundary patch quantifies a line whose observer
chord includes a displaced self-valid outward origin. Nonconforming geometry
uses the general endpoint formula. A separate finite-strip circle formula retains
its middle, flat-cap and corner distance cases when the planar reduction does
not apply; it does not extend the endpoints longitudinally.

Z3 `4.15.4.0` is pinned as a native runtime dependency. Quantifier-free nonlinear
real arithmetic uses `qfnra-nlsat`; quantified real formulas use `nlqsat`, with a
separate context per query. Solver unknown raises `VisibilityComputationError`;
there is no runtime timeout mapped to a Boolean answer or approximate fallback.
The mathematical formulas decide the supported domain, but no practical runtime
bound is certified. Difficult quantified queries can be slow. This limitation
is retained under the owner's performance deferral.

### Identity, caches and provenance

`continuous_visibility.py` fingerprints the exact original observer, target and
both blocker groups, plus the algorithm identity. Evidence stores deterministic
predicates, proof kinds and optional canonical rational witnesses. These are
reproducible algorithm evidence, not a portable independently checkable Z3 proof
object. The context fingerprint additionally binds IDs, keyword ownership,
terrain/rules policy and the caller's spatial key. Reusing that key after changing
geometry or keywords cannot authenticate stale evidence; Cover validates the
witness against the current authoritative resolution.

Result caches are bounded (128 contexts, 4,096 model pairs). Geometry preparation,
proof and source-group caches also have explicit finite capacities. The uncached
context API bypasses both context and pair-result caches; pure immutable
preparation memoization may still be shared. Cached/uncached and eviction/reset
regressions compare complete evidence, not just Boolean flags. Physical presence
and cleanup change input inventories through the existing group-aware services.
Timing values never enter authoritative records.

## Actual consumer audit

| Consumer | Status | Evidence |
| --- | --- | --- |
| `core/visibility.py` and `core/visibility_records.py` | Migrated | Domain policy/records above pure geometry; continuous pair predicates, per-model Cover sources and complete witness validation |
| `visibility_query.py`, `visibility_corridor.py` | Migrated | Explicit rays delegate to exact analytic fixed-corridor primitive |
| `terrain_area_visibility.py` | Migrated | Exact analytic intersection and polygon/union containment for policy association |
| `engine/shooting_targets.py` | Already correct | Group presence and model-owned keywords feed shared context for eligibility/range evidence |
| `engine/phases/shooting_requests.py`, `shooting_declaration_validation.py` | Already correct | Candidate creation and revalidation consume shared shooting services; facade counterexamples exercise both |
| `engine/attack_sequence_hazardous.py` | Migrated | Normal/Fortification Cover use source-group causation and firing-model keywords; destroyed blocker guards retained |
| `engine/hidden_detection.py` | Migrated | Solid-terrain causation uses the same full-visibility authority and per-model keywords |
| `engine/shooting_terrain_visibility.py` | Migrated | Model/area occupancy is analytic; group-aware blocker and retention inventory retained |
| `engine/rule_target_resolution.py`, `stratagems_geometry.py`, faction ability consumers | Already correct | Shared unit targeting services; direct Thousand Sons observer context uses the manifesting model's keywords |
| `engine/catalog_selected_target_effects_support.py` | Corrected (R32-001) | Unit-scoped visibility enumerates authenticated `rules_present_components`; a retained-only component can supply LOS while a surviving attached component is blocked |
| `engine/spatial_index_state.py` / battlefield spatial state | Already correct | Spatial revisions remain inputs; complete context hash additionally protects against same-key drift |
| `engine/model_destruction_cause_authority.py` | Corrected | Preserve Order 30 restoration for delayed unrelated Hazardous casualty registration; parent/child causality remains required |
| Local session, UI/headless/network, projections/events and replay | Already correct routing | Same submissions/decisions/mutation; Contract 14 documents nested evidence; exact replay and both-viewer regressions |
| Order 33 Indirect Shooting semantics | Not applicable | No source-mode rule change in this PR |

The static unit/model semantics audit now requires the continuous context owner
and prevents engine imports of primitive/formula/certificate modules or local
ray authority. Runtime inputs use catalog canonical keyword tokens without
locally replacing spaces or otherwise inventing tokens.

## Independent review and validation

A read-only reviewer checked source quantifiers, exact geometry, planar/general
formulas, sufficient proofs and the integration boundaries. Reproduced findings
were fixed and retained as regressions: VEX-01 eager polygon validation, VEX-02
outward float bounds, VCF-01 vertical-only tangent support, VCI-01 firing-model
keywords in allocation Cover, VCI-02 disabled area Cover evidence, and VCI-03
versioned schema IDs/references for the four changed Contract 14 wrappers. COV32-01
was resolved by the owner. The final bounded integration pass independently ran
20 focused tests and found no further defect in its scope. Earlier checks included
144 finite-circle formula/primitive comparisons and 1,660 reflected facing
corridors. These checks supplement the mathematical argument; they are not a
finite sampling claim of universal equivalence or independent approval.

The first covered behavioral aggregate was interrupted after 849.67 seconds:
6,789 passed, 13 failed and 14 did not complete. Seven remaining workers were
inside Z3 quantified nonlinear solving for ordinary gameplay queries, independently
of the deferred 100-target timing diagnostics. This is an incomplete validation
gate, not a coverage pass. The owner subsequently approved narrowly scoped solver
repairs because stalls would prevent CI completion. No timeout became a visibility
answer. All 14 unfinished cases now pass in **17.77 seconds** without coverage.

Three sufficient proofs resolve the observed stalls, retaining the existing
planar and general formulas for unresolved cases:

- **VST-01, shorter intervening blockers:** raise the equal-circle parallel
  family to the observer top. Before the centre midpoint, its height is at least
  `H-(H-z0)*s/L`. Exact whole-blocker support proves strict separation below that
  plane. The midpoint guard, contact, and elevation have direct regressions.
- **VST-02, endpoint containment:** an identical footprint with covering heights
  contains every observer or target endpoint, so every closed corridor intersects
  the blocker. Negative height/footprint and all-supported-shape regressions
  protect the containment guard.
- **VST-03, collinear rear blockers:** for equal circles use translated origins
  `o=t-D` at the target part's height, valid even when observer and target overlap.
  For a blocker at distance `d>=0` beyond the target, all selected flat corridors
  stay at least `sqrt(d²+max(R-r,0)²)` from its centre. The strict rational support
  comparison protects tangency; noncollinearity, wrong-side placement, different
  endpoint shapes/heights and zero displacement remain inconclusive. Rotated
  exact contact and solver-avoidance regressions cover the captured cases.

  For the rear-circle proof's clamped lateral case, write `w=-n·D/L`. If `r<R`
  and lateral clearance is zero, then `w²>=1-(r/R)²`, giving squared distance at
  least `d²+R²-r² >= d²+(R-r)²`. If `r>=R`, axial distance alone gives `d²`.
  Thus the same bound covers every positive supported model radius.

The independent reviewer checked all three derivations and guards, including the
lateral-clamping case `R<r`. Structural tests fail if the reproduced decisive
cases enter quantified solving; these are correctness/work-path regressions,
not reinstated broad performance benchmarks.

**VRI-01:** the aggregate exposed a real Order 30 restoration defect. Hazardous
records several casualties before routing their reactions; the first casualty's
retained attack can register another death before the next casualty receives its
authority. The independently reproduced authority-order logical-event indices
were `[42, 77, 106, 80]`, all without parent causes. The validator incorrectly
required total chronological order for unrelated causes. Removing that extra
restriction preserves canonical authority numbering, exact source/event ownership,
parent registration before child, parent logical death before child, logical death
before consumption, child consumption before parent and complete pending-Hazardous
ownership. The same-bug-class search found one global chronology assertion.

A new deterministic ledger regression failed before this repair and passes after
it; the original multi-casualty facade regression and parent-order negative test
also pass independently. The combined fight-resolution, Hazardous facade,
feature-association and contract-ID subset passed **134 tests in 9.57 seconds**.
The old feature-association test now instruments the actual exact footprint
authority. Ten fixed game-ID literals were recalibrated because visibility
evidence participates in RNG history; the reviewer confirmed by AST comparison
that their gameplay assertions and all other logic remain unchanged, with no
production RNG edit. All 13 previously failing cases plus three related cases
passed in a focused run: **16 passed in 74.81 seconds**.

The first complete code-quality suite reported **393 passed, one failed in 106.88
seconds**. The failure identifies two forbidden geometry-to-core imports in the
extracted records module. **VAR-01** moved domain policy and records together into
`core/visibility.py` and `core/visibility_records.py`, leaving pure geometry below
them. Engine/test/source-consumer imports migrated; the old domain module and its
two legacy allowlist entries were removed. Independent static review found no
cycles or forbidden imports. The focused ownership/source group passed **136
tests in 12.12 seconds**. Ruff check/format, mypy (2,809 files), pyright, all 11 import-linter
contracts, exact eight-shard inventory check, pre-commit, the generated Contract
14 base-ref check and generated TypeScript/type checks passed after the restore
repair. Import-linter passing did not erase the stricter audit failure in that
earlier attempt; the final complete code-quality result below supersedes it after
the ownership repair.

Final local results are recorded in `order32/validation-results.json`, tied to
runtime build `6b3a9365d32360c5f7492cf0ae22e7c5935fc0e4e537b9cfead318a9e7c6fe0d`.
The complete covered run finished in **489.86 seconds**: **6,840 passed**, and
two HTTP tests failed only because the sandbox prohibited socket binding. Both
passed with socket permission and `--cov-append` (**43.97 seconds**). All **6,842
unique behavioral tests** therefore passed across that full run and focused
environment retry; combined branch coverage is **85.04%**, above the 85% gate.
The initial local full command's exit code remains recorded as 1, not rewritten
as a clean pass. No production code changed between these executions and no
second uncovered behavioral aggregate was run.

The final code-quality run passed **394 tests in 109.35 seconds**. Ruff, mypy,
pyright, all import contracts, exact shard inventory, pre-commit, generated
source/build/contract checks, TypeScript checks and five unit tests, **342**
conformance assertions and the isolated installed-wheel smoke all passed. The
wheel validated 27 schemas and 2,628 engine resources. The tested commit and CI
link are provided with the PR; no CI outcome is inferred from these local checks.

## PR review repair: R32-001

Review of head `fb82249f4840b3ebdd73e9b515209f7359e05e9b` found a pre-existing
visibility-consumer gap: `selection_visibility_conditions_apply` excluded an
observer component unless it contained a living model. That contradicted the
Order 30/P05B retained-presence invariant before the continuous authority was
called. The original consumer inventory and mixed living/retained test did not
certify this boundary; this entry corrects that completeness claim.

The consumer now uses the existing `RulesUnitView.rules_present_components`
owner. Its view is resolved from current authenticated retention and fixed
placement authority. Explicit model scope, ability availability, off-battlefield
restrictions and the shared visibility query remain unchanged. Ordinary dead
models are excluded, and cleanup removes their retained authority from fresh
views. No geometry formula, solver, cache field or persistence shape changes.

The bug-class audit inspected all eight shared LOS callers. No second equivalent
prefilter was found. Primary Mission Action callers explicitly require living
models; those restrictions remain. The static LOS policy audit now rejects local
living-only filtering in this selected-target consumer and requires the shared
rules-present component owner.

`test_r32_retained_only_observer_eligibility_restores_replays_and_cleans_up` uses
a real lethal shot, finite retention choice and cleanup through `LocalGameSession`.
Both standalone and attached retained-only sources must expose the target through
actual generic eligibility; the attached Leader survives but cannot see it.
Explicit model scope, declined retention, cleanup, standalone lifecycle restore,
JSON session persistence, exact replay and both viewers' projections/events are
checked. Before the fix, both retained variants failed with an empty target tuple;
both ordinary-casualty controls passed (11.57 seconds).

The repair keeps the existing adapter decision contract and source interpretation.
The earlier aggregate results above belong to the original head. Repair validation
is recorded separately in `order32/r32-001-validation.json`; its tested commit and
CI result accompany the PR reply. Independent re-review of that head is required;
the finding is not dismissed or self-approved.

The repair's final covered behavioral run passed **6,846 tests** with **85.04%**
coverage in **451.98 seconds**, with local socket permission and no retries.
The full code-quality suite passed **394 tests in 105.80 seconds**. All four
new regression cases and 81 focused related cases pass. Ruff, mypy, pyright,
import boundaries, shard inventory, generated source/build/contract checks,
TypeScript checks and unit tests, 342 conformance assertions, and the installed
wheel smoke passed. The tested runtime build is
`2aff0715427fe404d6495347eb3a074168c7cc1eeb5be0e9e0df0cda108c0309`.

## Performance: preserved evidence and explicit deferral

The owner's later direction was to retain the correct planar formula and revisit
efficiency when a full head-to-head headless game can be measured. It supersedes
Order 32's proposed component budget, repeated head comparison and CI timing gate
as delivery requirements. See `PERFORMANCE_POLICY.md` (v2) and
`order32/benchmark-spec.json` (diagnostics v3). No threshold was silently raised,
no hard workload removed, and no deferred gate is reported as passed.

Reference diagnostics used Apple M5 Pro, 18 CPUs, 64GiB, macOS 26.6.2, Python
3.14.5, Shapely 2.1.2 and NumPy 2.4.6. The immutable baseline retained separate
setup, uninstrumented repeated timing, profiling and peak memory evidence.

| Baseline workload | Mean | Maximum, n=7 |
| --- | ---: | ---: |
| 100 targets / 30 overlapping blockers | 1532.61ms | 1560.33ms |
| 100 targets / 30 nonoverlapping blockers | 909.65ms | 916.98ms |
| Canonical 5-vs-5 setup + selection/declaration | 41.27ms | 41.82ms |
| Canonical 10-vs-10 setup + selection/declaration | 134.79ms | 136.97ms |

The last pre-deferral implementation diagnostic measured **296.87ms** and
**1083.29ms** for the two 100-target workloads, respectively, in one run each.
`order32/diagnostic-before-owner-deferral.json` retains those raw results.
These are not repeated final-head benchmarks. The overlapping diagnostic is
explicitly not a legal dense-game scenario. Earlier prototype timeouts and
integration stalls remain in `prototype-results.json` and
`integration-probe-before-ellipse-cap.json`; their experimental deadlines never
became runtime visibility answers. The subsequent correctness integration fixes
are not accompanied by a new performance claim.

The standing objectives remain a complete-game arithmetic mean below 60 seconds
and no measured game above 300 seconds on the agreed workload/hardware. The
existing capability evidence does not certify a complete legal headless game;
a supported complete-game driver, representative scenarios and completion/replay
validation remain prerequisites. No full-game duration was measured here. The
10-vs-10 baseline's 42 contexts / 420 model pairs / 20,580 old sampled rays are
component observations, not measured per-game counts or a full-game extrapolation.

Reproduction commands (timing is diagnostic, not a required Order 32 gate):

```bash
uv run python tools/build_core_other_concepts_source.py --check
uv run python -m scripts.probe_order32_visibility --output /tmp/order32-diagnostic.json
uv run python docs/performance/order32/prototype_solver.py --case partial-occlusion --predicate full --output /tmp/order32-prototype.json
```

The prototype is retained historical experimental code, not a runtime authority.
Its exit code 2 preserves an unresolved/incorrect result. It must not be represented
as a completed correctness or performance gate.
