# Order 73 / PFINAL preflight: certification blocked

Reviewed base: `77e2e46340abd8a698465e0937df6363d356925a` (main, Order 72).
Review date: 2026-09-21, America/New_York.
Status: **blocked before the complete 25-category certification audit**.
`CAUDIT-01` remains open. This record is neither a selected whole-corpus
snapshot nor evidence that categories other than the checked consumer passed.

PR #492 is merged at this base; the remote open-PR inventory was empty at
preflight. Historical Order 72 prose saying its PR is open is stale delivery
metadata, not an outstanding implementation dependency.

## Confirmed blocker: C18-10, Emergency Disembark geometry completeness

The final certification invariant forbids any partially executed or unsupported
in-scope Core Rules semantic. A typed unresolved result preserves fail-closed
correctness but does not prove that the engine can execute that rule.

Order 60's shared Emergency Disembark placement proof still cannot decide
ordinary terrain-floor cases. The limitation is explicitly documented in
[its scope record](ORDER_60_SCOPE_PLAN.md), and remains enforced by production
code and regressions on the reviewed base.

The existing regression constructs five survivors with individually legal
supported endpoints at z=6 inches and blocked ground endpoints. Both the
ordinary and grouped omission proofs raise `GameLifecycleError` instead of
resolving whether omission is allowed; even the complete elevated proposal
raises. The test independently checks terrain endpoint legality and checks
unchanged lifecycle state. It does not assert that the elevated proposal has
already satisfied every closest-position and engagement obligation: those
missing proofs are precisely the blocker.

This is an execution limitation, not a source-wording conflict. Removing the
guard or treating unresolved as a legal placement or an unplaceable casualty
would weaken the engine invariant.

### Retained source evidence

| Field | Value |
| --- | --- |
| Clause | 18.05 Emergency Disembark, complete while-moving placement text |
| Stable source ID | `gw-11e-core-emergency-disembark-placement:emergency-disembark-placement` |
| Provider | 40k.app, non-affiliated maintained App-data mirror |
| URL | `https://www.40k.app/rules/18-transports` |
| Retained observation | `2026-09-18T19:30:00+00:00`; no App-data version asserted |
| Transcription SHA-256 | `cc63b547abc5339f6c3f98530f53cd3a838800f9b5a89003715ebf19e7c39923` |
| Audit source-observation fingerprint | `c39e87327a822139e0075c5af984b48f2fecbc0c2d5a3645507473e9e2545150` |
| RuleEvidence observation fingerprint | `dd0bb827686d37fd449b038702af52ce6bcc1967cab572d9bd2f4156986cf257` |
| Package byte SHA-256 | `81fbfdb90b7d747b99d7be582ba7a4c006dadd38fea1ccf2a0dad93f85a80bb4` |

The offline source generator and typed-loader tests passed. Historical source
bytes, provider timestamps and observation fingerprints remain unchanged.
Direct web-tool checks of categories 13 and 18 returned HTTP 403 in this task;
no fresh page observation, source drift, or co-version equivalence is claimed.

### Owning path and same-class search

Reviewed source JSON -> typed `PLACEMENT_POLICY` -> destroyed-Transport
proposal -> `transports._resolve_disembark` / grouped destroyed-Transport
resolution -> shared `emergency_disembark_placement` proof -> pure
`geometry.emergency_disembark_fit` predicate -> accepted engine mutation and
existing event/replay/adapter paths.

The shared proof supplies omission, closest-position and unengaged-preference
checks. `_terrain_proof_rects` raises before the planar solver if a floor can
meet the searched passenger footprint, independent of the proposed elevation.
This includes complete proposals, not only omitted survivors.

The same-owner search also found explicit restrictions to circular bases
(`_circular_radius`) and cardinal walls (`_terrain_proof_rects`). These are
additional execution limits to address in the geometry-completeness scope;
they were inspected in code, not newly exercised by this preflight. No claim
is made about which faction models can currently reach those branches.

The existing source row's `loaded` and `executable_engine_runtime` fields do
not establish unrestricted execution. Its source row and generated support
reporting must accurately describe any remaining partial geometry coverage.

## Prerequisite P18I — authorized and implemented

Assign C18-10 to a scoped Emergency Disembark geometry remediation before
PFINAL. Categories 18 and 13 are affected through the shared placement/terrain
boundary; the owning closure key is C18-10. Preserve P18B's historical delivery
record and source identities. The owner approved remediation with "Yes, fix findings". P18I is now
Order 73 and PFINAL moves to Order 74; Orders 1–72 retain their identities.

Acceptance requires:

1. Replace the known unsupported floor/support, rotated-wall and base-shape
   cases with exact legal-placement proofs for engine-supported geometry.
   Keep terrain collision, support/overhang permissions, 3D distance,
   engagement, coherency, objectives and the oversized exception consistent
   with the authoritative endpoint validator.
2. Use the same proof owner for ordinary and attached-unit omission,
   closest-position and unengaged preference. A proof of no valid placement
   must cover supported elevations and permitted orientations; an unresolved
   calculation must still raise and never authorize destruction.
3. Add source-backed regressions before changing semantics, including both
   positive and negative placement cases. Exercise actual facade submission,
   invalid/stale input, unchanged state on rejection, both viewers, save/restore
   and deterministic replay through the existing engine mutation owner.
4. Audit source/execution support declarations, the adapter contract, runtime
   identity and generated artifacts. Measure base/head on the same declared
   geometry workloads without treating component results as full-game proof.
5. Complete the repository's final gates, publish and merge the prerequisite,
   then restart the complete PFINAL audit on current main. Further discovered
   gaps still receive their own prerequisite owners before certification.

This expanded an audit-only request into geometry implementation. The required
`AGENTS.md` scope decision was obtained before production changes. The roadmap separately
states: "If the audit discovers any gap, do not open or certify PFINAL."
No PFINAL PR is published from this preflight.

## Historical preflight checks

`uv run --no-sync pytest tests/unit/test_order60_emergency_disembark.py tests/code_quality/test_order60_emergency_disembark.py -q -n 0 --no-cov`

Result: **19 passed in 30.32 seconds**. This is a focused diagnostic run;
several passing tests require the unresolved exception and therefore establish
the limitation, not compliance. Serial focused iteration is permitted by
`AGENTS.md`; this is not an aggregate final suite.

These checks also passed:

- `uv run --no-sync python tools/build_core_emergency_disembark_placement_source.py --check`
- `uv run --no-sync python tools/core_rules_40k_app_audit.py --check`
- `uv run --no-sync python scripts/build_test_shards.py --check --shard-count 8`

The full behavioral coverage, full code-quality, lint/type/import/pre-commit,
contract-client, conformance and package-smoke PR gates were not run. They are
still required before publishing a remediation PR. No production or test files
were changed by this preflight.


## Implementation and scope audit

The violated invariant is that a negative legal-placement proof must cover all
engine-supported geometry before omission can authorize a survivor casualty.
The old floor guard, circular-base guard and cardinal-wall guard are replaced
by one analytic constraint builder in `geometry.emergency_setup_proof` backed
by `geometry.placement_predicates`. The previous planar module is removed.
Source JSON and retained source observations are unchanged; no new source
interpretation, handler, rule-text parsing or decision path is introduced.

The engine maps terrain descriptors into explicit ground/elevated support and
no-overhang permissions. The proof enumerates ground and actual floor planes,
retaining continuous translation and arbitrary orientations on each. It checks
battlefield containment, volume collisions, objective disks, support permissions,
3D range, engagement and the complete proposed group's coherency. Closest-pose
and unengaged-preference queries share those predicates with submitted endpoints.
Grouped component validation receives the complete proposed attached placement,
so other components cannot disappear from an alternative-position proof.
A candidate must reconnect every remaining coherency component and satisfy
neighbor counts and span limits. The omitted-model check uses the owning
component's canonical keyword permissions and actual survivor geometry.

The only extraction outside that owner moves the existing placement-to-model
conversion into the transport geometry module, keeping the frozen transport
module below its prior line cap. Dependency direction is unchanged; both new
modules remain pure geometry under the existing import-linter contract.

Bounds are certificates: battlefield minimum width and minimum vertical range
can prove impossibility; exact rational distance intervals can prove a closest
comparison. Checked witness poses can prove existence, never non-existence.
Ellipse enclosure is sufficient only for a positive witness; failure continues
to the complete analytic formula. General clearance uses separating support
lines; curved containment proves inclusion of every base point. No mesh or finite set
of failed candidate poses authorizes omission. Solver errors retain their cause
in `GameLifecycleError`; bounded caches include geometry and policy identity.

Regression coverage includes all nine passenger/Transport shape pairings,
rotated walls, allowed/forbidden support, overhang, out-of-range floors,
vertical coherency/engagement and supported survivor omission. Real destroyed
Transport attacks create physical and attached pending placement decisions.
Facade submission tests exercise floors and rectangular Transports, pre-pop
malformed/stale/wrong-context rejection, both viewer projections/event streams,
save/restore and exact replay. The shared disembark/destroyed-Transport focused
suite also passes. Behavioral tests extend an existing file; no shard inventory
membership changes are needed.

Support declarations retain distinct `loaded` and `executable_engine_runtime`
fields. They describe the source-backed consumer, not PFINAL certification.
The adapter contract records the additive endpoint diagnostic; runtime identity
and external contract examples are regenerated. C18-10's implementation still
requires merge before the fresh, complete 25-category PFINAL audit. Historical
Order 60 limitations above describe the reviewed base, not current behavior.


## Performance evidence

Matched measurements ran sequentially without coverage or competing test
workers on the same provisional Windows host and dependency lock. The retained
[original workload](performance/order73/base.json) and
[head](performance/order73/head.json) preserve seven samples, cold-first timing,
identical fixtures and existing budgets. Head mean is 0.0120 seconds versus
base 0.0218 seconds; head maximum is 0.0637 seconds, below the 12-second budget.

The expanded [base](performance/order73/geometry-base.json) and
[head](performance/order73/geometry-head.json) cover 12 actual facade submissions:
five/six survivors, physical/attached passengers, circular/rectangular
Transports, and an elevated floor. The base completes 0/12 because of explicit
unsupported geometry errors; head completes 12/12 valid submissions, mean
1.249 seconds, maximum 2.167 seconds. The existing 12-second Emergency Disembark
ceiling is retained for the complete submission and guarded by code-quality
regression checks. Failed base timings are attempt costs, not successful rules
latencies. No gameplay-slice or complete-game certification is claimed.

A thin-base/rotated-floor exploration stalled before a placement verdict;
[the diagnostic](performance/order73/exploratory-floor-stall.json) preserves that
incomplete result. The same geometry now completes using an exactly checked
floor witness before the impossible ground-plane query. The final regression
retains that case. This is a scoped exact-solver repair, not resumed broad
optimization or a claim of a universal solver/runtime bound.

Reproduction (use an intact base checkout, including its contract schemas):

```text
uv run --no-sync python scripts/measure_order60.py --runtime-src <base-or-head>/src --revision <revision> --output <report.json>
uv run --no-sync python scripts/measure_order73.py --runtime-src <base-or-head>/src --revision <revision> --output <report.json>
```

The original base was measured before production changes. Expanded cases were
measured afterward against an unmodified archive of the same pinned base;
they preserve the discovered unsupported outcomes rather than rewriting them
as passing baseline behavior.


### Curved-containment review correction

The supplemental review found that even constant ellipse-in-circle containment
could stall in general quantifier elimination. The final predicate uses the
[S-procedure, Boyd and Vandenberghe, appendix B.2](https://stanford.edu/~boyd/cvxbook/bv_cvxbook.pdf#page=669)
for this case. Parameterizing the ellipse by the unit disk supplies strict
feasibility; containment is equivalent to a nonnegative multiplier and a 3x3
positive-semidefinite matrix. All principal minors are checked with exact real
arithmetic, including zero minors at tangency. General curved containment keeps
the complete quantified predicate where this specialization does not apply.

The regression distinguishes a centered ellipse that fits a disk from its
bounding rectangle, which does not; translating that ellipse by 0.01 inches
also fails. Additional mixed ellipse/rotated-rectangle contact regressions check
actual base membership. These tests pass without a sampled approximation.
The interrupted exploratory calculation is retained in
[its diagnostic](performance/order73/exploratory-containment-stall.json).

The first aggregate behavioral run passed 8,754 tests with 85.17% coverage.
It is superseded by this production correction and is not the final delivery
gate. Its subsequent code-quality run had eight failures: seven pre-existing
performance guards required fresh head measurements for the new runtime, and
the engagement-boundary inventory still named the extracted helper. The latter
now records the same single proposed-model geometry call at its current owner;
no current-state rules-unit consumer is newly allowlisted. All seven inherited
head measurements are refreshed under their unchanged inputs and budgets.
Final aggregate results are recorded separately below and in validation.json.


The second aggregate coverage run reached 85.17% coverage with 8,757 passes
and one Hypothesis input-generation health-check failure in the unchanged
polygon overlap property test. Six integer inputs took 1.87 seconds under
64 workers plus concurrent contract/client validation; no geometry assertion
failed. Its exact reported seed passed unchanged in 0.38 seconds in a focused
run. Final aggregate validation uses 32 workers through
`PYTEST_XDIST_AUTO_NUM_WORKERS=32`, still `-n auto --dist=worksteal`, with no
competing validation jobs. No code, test assertion, health check or budget was
changed for this scheduling correction.


The following quality run passed 575 checks and found one documentation false
positive: the generic `.pdf` token audit treated the mathematics reference in
a function docstring as runtime Event Companion source ingestion. The audit
now distinguishes genuine docstrings from executable PDF string references.
Explicit Event Companion tokens remain forbidden even in docstrings, and PDF
parser imports remain forbidden. Nine direct regression cases cover module,
class and function citations plus rejected runtime/source references; the
complete focused file passes all ten checks. The same-bug-class search found
this token audit has one owner. Only code-quality tests changed, preserving
the successful 8,758-test behavioral run and runtime identity.


## Initial PR finding record (before R73-001)

- **Status:** P18I implemented; local validation passed; PR #493 is open for review and unmerged. PFINAL and CAUDIT-01 remain open.
- **Finding IDs:** C18-10.
- **Dependencies and evidence gate:** P18B and P18H are merged in current main, `77e2e46340abd8a698465e0937df6363d356925a`. The owner authorized the prerequisite after the certification preflight found this execution gap. Retained source evidence is unchanged.
- **Violated invariant:** omission may authorize a survivor casualty only after a complete negative placement proof over engine-supported geometry.
- **How it is currently done (reviewed base):** the shared proof rejects relevant terrain floors, non-circular bases and non-cardinal walls before resolving legal placement.
- **How it should be done:** endpoint, omission, unengaged-preference and closest-position checks use one analytic query over circles, ellipses, rectangles, all orientations and actual support planes. Alternative attached-unit positions retain the complete proposed group. Unresolved calculations remain explicit errors.
- **Specific authoritative maintained direct App-data mirror rule/statement and source ID:** complete 18.05 Emergency Disembark while-moving placement clause: wholly within the set-up distance, as close as possible, prefer unengaged placement, and destroy only survivors that cannot be placed. Stable ID `gw-11e-core-emergency-disembark-placement:emergency-disembark-placement`.
- **Provider, URL, App-data version or observation timestamp, transcription SHA-256, and source-observation fingerprint:** non-affiliated 40k.app; [Transports](https://www.40k.app/rules/18-transports); retained observation `2026-09-18T19:30:00+00:00`, no App version asserted; transcription `cc63b547abc5339f6c3f98530f53cd3a838800f9b5a89003715ebf19e7c39923`; audit observation `c39e87327a822139e0075c5af984b48f2fecbc0c2d5a3645507473e9e2545150`; RuleEvidence observation `dd0bb827686d37fd449b038702af52ce6bcc1967cab572d9bd2f4156986cf257`. No fresh source observation or co-version equivalence is claimed.
- **Scope and explicit exclusions:** the C18-10 placement proof and its physical/attached consumers, tests, identity, contracts and documentation. Source wording is unchanged. All-category certification, whole-game performance and unrelated engine features are excluded.
- **Owning state/validation/mutation/event/replay path:** source JSON and typed placement policy -> existing destroyed-Transport proposal -> shared Emergency Disembark engine validation -> pure analytic geometry -> existing accepted engine mutation, casualty events, decision records, viewer projections, persistence and replay.
- **Decision and viewer-visibility impact:** existing proposal kinds and payload fields remain authoritative. The additive `emergency_disembark_endpoint_illegal` diagnostic is documented in the adapter contract. Malformed/stale input fails before queue pop; well-formed rule-invalid attempts follow the existing retry path. Both viewer paths are covered.
- **Regression scenarios and same-bug-class search:** floor support/omission, nine passenger/Transport shape pairs, arbitrary orientation, rotated walls, overhang, objective/collision/range constraints, complete-group coherency, unengaged preference, closest placement, invalid submissions, unchanged rejected state, both viewers, restore and exact replay. The owner search found all geometry guards and all four proof consumers. The PDF-source audit also has a single owner; direct regressions distinguish documentation citations from forbidden runtime/source references.
- **Generated artifacts/documentation:** runtime manifest and external contract examples; architecture, adapter contract, roadmap/comparison and this audit; matched Order 73 reports plus required current-runtime head refreshes for Orders 64, 65, 66, 69, 70, 71 and 72. Source package bytes and support-status identities are unchanged.
- **Validation results:** 8,758 behavioral tests passed with 85.1739% coverage; 585 code-quality tests passed. Lint, formatting, mypy, pyright, import boundaries, shard inventory, source/contract generation, exact-base compatibility, installed-wheel smoke, TypeScript client checks, 342 HTTP conformance assertions and all declared matched component budgets passed. Final suites used 32 workers with work stealing.
- **PR URL and merge commit:** [PR #493](https://github.com/SobolGaming/Warhammer_40k_AI/pull/493); open for review, unmerged.


## Initial PR validation (before R73-001)

The final behavioral suite passes **8,758 tests** with **85.1739% coverage**;
the final code-quality suite passes **585 tests** without coverage. Both use
32 workers with work stealing. The behavioral run retains ten existing
SQLite resource warnings. No production code changed after that run began.

Ruff, formatting, mypy, pyright, import-linter (11 contracts), pre-commit,
the exact eight-shard inventory check, source generation and comparison-report
reproducibility pass. Runtime identity and external contract checks pass against
base `77e2e46340abd8a698465e0937df6363d356925a`. The installed wheel verifies
2,923 runtime resources, 27 schemas and all six request families outside the
repository. Clean TypeScript dependency installation, generated-client checking,
typechecking, five client unit tests and 342 live HTTP conformance assertions
also pass. All declared matched component budgets pass under unchanged limits.

[Machine-readable validation](performance/order73/validation.json) records the
final results, runtime identity, report hashes and superseded attempts. These
are local Windows results; remote CI supplies its own platform runs. They do
not certify complete games or the remaining PFINAL category audit.


## R73-001 — objective-marker contact-plane equivalence

The review found a blocking mismatch in the analytic objective exclusion:
it treated any marker elevation inside a model's vertical volume as contact.
The authoritative endpoint validator instead compares the model and marker
contact-plane elevations with absolute tolerance `1e-9`. Excluding a legal
non-contact-plane position could produce an unsound negative omission proof
and permit a placeable survivor to be destroyed. The same predicate also
feeds submitted endpoints, unengaged alternatives and closest-position checks.

The existing endpoint criterion is extracted, unchanged, into the pure
`geometry.pose.contact_planes_coincide` helper. Both
`DistanceMeasurementContext.contact_plane_footprints_overlap` and the analytic
plane builder use it. Each solver pass already has a fixed elevation; converting
that rationalized source elevation back to its original float lets the helper
apply exactly the same floating-point tolerance as endpoint placement before
adding the disk constraint. There is no model-height test for objective contact.
The same-bug-class search found ordinary endpoint and spatial-index consumers,
as well as the Cult Ambush contact consumers, already using the shared measurement
context. The Emergency Disembark volume comparison was the divergent owner.
A static audit now requires both definitions to delegate to the same helper.

Eight new regressions were added before the production fix. The reviewed PR
failed five and passed three; all eight pass after the fix. They cover marker
z=1 above a ground model's base, exact contact, positive tolerance interior and
boundary, a separation just beyond tolerance, and a marker just below the base
within tolerance. Submitted legality, unengaged existence and closest-position
queries are compared to the authoritative endpoint result. The two real-domain
omission regressions cover physical and rules-unit consumers: a non-contact-plane
marker covers the entire battlefield, so every possible placement overlaps its
horizontal footprint. Both must report `EMERGENCY_DISEMBARK_OMITTED_MODEL_PLACEABLE`
for the omitted survivor and leave authoritative state unchanged.

This correction changes three production geometry files and their existing
unit/code-quality tests. No behavioral test file was added or moved. The existing
adapter contract covers the unchanged proposals, diagnostics, records, viewer
scope and engine mutation path; no new adapter-visible shape or choice is added.
Source IDs, source package bytes and retained observations are unchanged.
Runtime identity, contract examples and required performance head evidence are
refreshed for this revision. The scope and architecture audit found no new
subsystem, dependency boundary, named handler or adjacent feature work.

R73-001 validation: **8,766 behavioral tests pass with 85.1743% coverage**,
and **586 code-quality tests pass** without coverage. Both final suites use
32 workers with work stealing and no competing build/client jobs. Required
lint, format, type, import, shard, source, exact-base contract, installed-wheel,
TypeScript and 342-assertion live HTTP conformance checks pass. The nine
performance evidence guards pass against unchanged inputs and budgets.
See [review-fix validation](performance/order73/r73_001/validation.json) for
runtime identity, report hashes and measured results.
The initial PR results above remain historical. P18I is Order 73, PFINAL remains
Order 74, and CAUDIT-01 remains open until merge and a fresh complete audit.
