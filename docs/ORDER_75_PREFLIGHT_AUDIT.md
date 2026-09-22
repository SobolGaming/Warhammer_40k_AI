# Order 75 / P21C — fixed-target Surge approach repair

Reviewed main: `9d8c5e2a1bb4db3c8a7f68b6da924c4ea9e23daa`.
Review date: 2026-09-22, America/New_York.
Status: **blocked before complete 25-category certification**. CAUDIT-01
remains open. This document records a reproduced execution finding, not a
complete Core Rules inventory or compliance certificate.

The fetched remote and local main agree. Order 74, PR #494, merged at
`2026-09-22T14:21:44Z`; the remote open-PR inventory was empty at preflight.
Historical descriptions of that PR as unmerged are stale delivery metadata.

## C21-03 — optimal Surge against a fixed noncircular target is rejected

Approved prerequisite owner: **P21C**. The owner authorized implementation on
2026-09-22 after the preflight pause. P21C is Order 75; PFINAL is Order 76.

The required invariant is that a legal, provably maximal Surge approach must
execute through the shared engine decision path. A conservative bound may
establish impossibility, but failing to attain that bound does not establish
that a submitted move falls short. An unresolved result protects correctness;
it does not establish complete semantic execution for PFINAL.

The problem is independent of Order 74's terrain-exclusion repair. It reproduces
on an empty battlefield with circular moving models and one fixed rectangular
enemy footprint. No difficult obstacle search, source ambiguity or timeout is
needed to demonstrate it.

### Executed facade reproduction

The preimplementation probe reproduced the rejection on the reviewed main. Its
retained result, immutable local-artifact hashes and source observation are in
[`preflight.json`](performance/order75/preflight.json). The committed canonical
fixture `tests/surge_fixed_target_helpers.py` and the Order 75 facade regressions
in `tests/unit/test_order52_surge.py` now reproduce the counterexample and require
the repaired behavior. Six facade cases failed before the runtime edit; geometry
coverage independently produced 11 failures before the edit.

The fixture uses real canonical domain objects: five 32 mm infantry models,
one canonical vehicle with a deliberately specified 8-by-2-inch rectangular
test footprint, a typed three-inch Surge grant and trigger, authenticated
placement/Command history, and `LocalGameSession`. These dimensions are test
geometry, not an assertion about a faction datasheet. No decision controller,
validator or engine service is replaced.

- The five source centers are `(10 + 1.4*i, 20, 0)`, for `i = 0..4`.
- The target center is `(12.8, 30, 0)` with zero facing. Its footprint is
  `[8.8, 16.8]` by `[29, 31]`.
- The engine offers the target, and the facade selects its finite option.
- Every submitted model path has three poses, at y = 20, 21.5 and 23.
- All five ordinary path validators and terrain validators pass. The final
  group is coherent. There is no other enemy and no forbidden engagement.
- All five models finish exactly `5.370078740157481` inches from the target.
- The engine proves engagement unreachable but records maximum approach as
  `unresolved` for every model, then rejects the facade submission with
  `surge_reachability_unresolved`.
- Battlefield placement and movement history remain unchanged. A fresh proposal
  is issued. JSON checkpoint restoration succeeds and exact replay reproduces
  the rejection.

The probe's initial diagnostic iterations included a wrong rectangle constructor
argument and a wrong evidence-key name. Those were corrected before the
successful reproduction; they are not production defects.

### Independent optimality proof

Let `r = 16/25.4` inches. Any path within the three-inch translation budget
from y = 20 has endpoint center y <= 23. Rotating a circular moving base does
not change its footprint. Every point of the stationary target footprint has
y >= 29. The horizontal separation is therefore at least
`29 - 23 - r = 5.3700787401574805` inches. A nonnegative vertical separation
cannot reduce that distance.

Every proposed endpoint has x within the target's horizontal span, y = 23,
and z = 0, so it attains the bound. The entire group attains its individual
optima simultaneously while preserving coherency. Engagement is impossible
because this exact minimum exceeds the two-inch horizontal engagement range.

The runtime instead encloses the stationary target in a circle of radius
`sqrt(4**2 + 1**2)`. Its per-model lower bounds after subtracting the move
budget range from approximately 2.247 to 2.632 inches. These are safe but
unattainable lower bounds: they allow parts of the fixed target to occupy
space outside its actual footprint. The subsequent finite search cannot find
a genuinely better path and cannot certify optimality, so the legal move is
rejected.

### Source evidence

On 2026-09-22 the browser displayed the complete current 21.02 rule at
[40k.app](https://www.40k.app/rules/21-flying-and-surging). Its maximum-approach
requirement agrees with the retained Order 52 reviewed obligations. No App-data
version was exposed, and no co-versioned mirror equivalence is asserted.

| Field | Retained implementation evidence |
| --- | --- |
| Stable source ID | `gw-11e-core-surge:surge-move` |
| Provider | 40k.app, non-affiliated maintained direct App-data mirror |
| URL | `https://www.40k.app/rules/21-flying-and-surging` |
| Observation | `2026-09-16T00:00:00+00:00`, recorded day precision |
| Short-excerpt transcription SHA-256 | `331dd613b946a475fd851ee8b6b7977d442aaf69dfae19ebd55e91320cd57716` |
| Source-observation fingerprint | `af2d7a99d05da410269168190d9e2ed646cce976426a8b9d2ef5e882e921953b` |
| Audit | `data/source_audits/maintained_app_mirrors/surge_2026_09_16.audit.json` |
| Historical official Core PDF SHA-256 | `f6a2443a44627ac5f0ef08407d29aa5ec7e97339998f05bc35f3ae37bf276833` |

The retained excerpt hash is not a hash of the complete page or this new browser
observation. Historical observations, source packages and registry bytes remain
unchanged. The local preflight metadata retains a separately timestamped short
source excerpt and its hash; that corroboration is not a new runtime authority
registration or a selected snapshot for all 25 categories.

### Owning path and same-class search

Source grant/trigger -> finite Surge unit/target selection ->
`MovementProposalRequest` -> facade parameterized submission ->
`resolve_triggered_movement` -> `validate_surge_endpoints` ->
`surge_endpoint_evidence` -> `MovementGoal.distance_lower_bound` and shared
`movement_reachability` -> rejected decision/event and fresh proposal.

The full production call-site search finds the same bound in the shared
reachability search, Charge endpoint evidence, Charge history authentication,
Surge execution and Surge history authentication. `surge_history` independently
recomputes the bound used by `optimal_bound` evidence. An execution-only change
would therefore leave restore authentication inconsistent.

The scoped invariant concerns fixed-target geometry in maximum-approach proofs.
Charge/Consolidation use the same search authority but do not thereby share this
specific optimality rejection. A prerequisite must review their bound and
evidence compatibility, without claiming a demonstrated facade failure in those
consumers. Obstacle-induced optimality, general path planning and unrelated
performance optimization are not established by this counterexample.

### Approved prerequisite acceptance

1. Add a red facade regression for this exact legal Surge before changing
   runtime code; extend the same-class coverage to fixed oval/rectangular
   targets, orientation, model/component ownership and multiple target models.
2. Supply a mathematically sound shared bound/proof that preserves the fixed
   target's actual geometry. Retain ordinary PathWitness, terrain, collision,
   coherency and engagement validation and explicit unresolved diagnostics.
3. Keep execution and historical authentication on the same proof owner.
   Cover shorter invalid moves, stale requests, both viewers, deterministic
   evidence, JSON restoration, tampering and exact accepted/rejected replay.
4. Assess matched base/head costs, preserve immutable source provenance and
   regenerate runtime identity/contract artifacts as required. The base's
   rejected move is not an equivalent-work completed-game timing baseline.
5. Run the required final gates, publish and merge that prerequisite, then
   repeat the complete PFINAL audit from current main.

This is an algorithm/evidence change beyond an audit/certification PR.
`AGENTS.md` requires a pause before materially broadening the requested solution.
The roadmap says: "If the audit discovers any gap, do not open or certify
PFINAL." The owner subsequently approved P21C, so the scoped implementation and sequence
update proceed under that authorization.

## Headless performance assessment

Repository inspection found a single-decision headless submission adapter and
test producers for fixed finite options and deployment. It did not find a
representative legal complete-game driver or a committed complete-game input
recording to measure. The mission pairing driver starts at a prepared Fight
boundary and stops after one player's turn-end scoring. Terminal-state tests
also seed late-game state; they are not initialization-to-normal-completion
game workloads. The capability manifest retains
`certified_full_game_evidence_missing`.

Thus complete games attempted/completed are 0/0, with no per-game samples,
mean, maximum or completion-rate claim. The below-60-second arithmetic mean
and at-most-300-second observed maximum targets remain **uncertified**. Missing
prerequisites are a versioned legal full-game workload/recording covering all
required decisions, declared rosters/terrain/seeds and policy, normal completion
and replay output, plus actual measurements on declared hardware.

Order 74's existing cold-cache Charge workload remains a component diagnostic;
its 12-second threshold cannot certify these full-game targets. It exercises
the continuous terrain solver, whereas the newly reproduced empty-battlefield
Surge gap exercises a different proof obligation. No new game policy/driver,
training work or budget relaxation is included in this preflight.

## Validation and limits

Nine focused tests passed without coverage in 5.36 seconds: the existing Surge
facade retry/restore/replay test, Order 74's independent maximum-approach guard,
and all Order 52 static audits. The standalone probe independently passed its
assertions while reproducing the legal-move rejection. The focused JUnit report
is `reports/order75/focused.xml`.

At the original preflight boundary no production code, source registry, runtime
identity, contract or collected test-file inventory had changed, and aggregate
gates had not run. Implementation validation is recorded separately below.
No PFINAL PR has been opened.

The complete clause/FAQ inventory, selected all-category snapshot, all v931/v946
and September 10 consumer closures, cross-category audit and CAUDIT-01 closure
remain outstanding. This preflight does not certify unexamined categories or
convert previously passing implementation tests into a compliance claim.

## Approved implementation and scope audit

The executable change is in `geometry/movement_reachability.py`, plus an updated
explanatory comment in `engine/surge_movement.py`. Model-range and engagement
bounds preserve the stationary target's measured footprint/facing. Circular
movers use the existing range owner's actual horizontal separation: their
measured footprint is rotation invariant and set distance is 1-Lipschitz under
translation. Other movers retain a containing-disk relaxation for all moving
orientations, while measuring their center against the actual fixed target.
Vertical gaps and range subtraction retain their existing semantics. A union
uses the minimum bound across all target models.

This reuses the authoritative footprint representation, including its existing
polygonal oval/circle representation for noncircular range queries. It does not
introduce a new ellipse approximation, a general path optimizer, a fallback or
an endpoint-only movement validator. Ordinary witnessed paths, collision,
terrain, coherency and engagement remain mandatory. Unattainable conservative
bounds for rotating movers and obstacle-constrained optima can remain unresolved.

Live Surge, shared reachability, Charge evidence and restore authentication all
consume the same bound. No new handler, source rule, decision type, schema,
visibility policy or package boundary is needed. The adapter contract documents
why the existing payloads cover the change. Runtime identity and generated
contract examples are refreshed. No collected behavioral test file was added,
removed or renamed; the shared helper does not alter the eight-shard inventory.

Thirty-four new focused cases pass: fixed rectangle/oval geometry and rotations,
vertical policy, conservative moving rotations, multi-target minimum, cache
invalidation, attached Leader ownership, both viewer event streams, malformed
kind/state preservation, stale requests, shorter-move rejection and retry,
authenticated JSON restore, forged bounds and exact accepted/rejected replay.
Existing Charge, Consolidation, terrain and source checks remain required in
the aggregate suite. Scope review found no need to change their mutation paths.

The performance assessment uses matched pinned base/head facade submissions.
Existing current-runtime performance guards also require remeasurement of
Orders 64–66, 69–72, R73-001 and 74. Their Windows baselines are remeasured at
their original commits on this Apple M5 Pro, using unchanged scripts, workloads
and budgets. These evidence updates do not extend production scope.
See [performance evidence](performance/order75/README.md) and
[final validation](performance/order75/validation.json).

## Additional preflight observation requiring separate adapter triage

A malformed `proposal_kind` submitted through `LocalGameSession` is rejected
before queue pop and leaves the pending request and game state unchanged, but appends a
`triggered_movement_proposal_invalid` event without a decision record. A later
exact replay of that session reports event-stream drift. An empty dictionary
also raises `KeyError('proposal_request_id')` at the typed payload loader instead
of a typed malformed result. Both paths predate the fixed-target bound and do
not call it. They require a separate adapter ingress/attempt-recording audit;
this PR neither repairs nor certifies them. The shorter well-formed rejected
Surge and its accepted retry do reproduce exactly. CAUDIT-01 must retain these
observations when the complete audit resumes.

## Final P21C validation

All required local gates passed. The complete behavioral suite ran once with
coverage: 8,825 passed in 679.31 seconds, 85.19% coverage against 85%. Ten
unclosed SQLite connection ResourceWarnings were reported; no tests failed or
were skipped. The subsequent complete code-quality suite passed all 590 tests
in 128.60 seconds without coverage. Both used 18 xdist work-stealing workers.

Ruff, mypy (3,185 files), Pyright, all 11 import contracts, the exact eight-shard
check and pre-commit passed. Source/comparison/build generators, the external
contract check against the reviewed main, installed-wheel smoke (27 schemas,
six request families), TypeScript generated/type checks, five client unit tests
and 342 HTTP conformance assertions passed. Final matched measurements accept
all nine head submissions within the unchanged 12-second gate.

No production code changed after final behavioral validation began. Later
changes only completed performance-report metadata and validation records.
PFINAL and complete-game certification remain open as described above.
