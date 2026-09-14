# Order 47 — per-model Charge endpoints

## Required invariant

C11-04 requires every charging model to finish closer to at least one selected
target, within one inch of a selected target when possible, and engaged with a
selected target when possible. A leading model cannot satisfy another model's
obligation. The rules unit must still engage every selected target and no other
enemy unit. Physical feasibility requires a validated complete path, coherency,
collision and terrain legality; an unresolved search is not an exemption.

The three per-model clauses and the two unit-level endpoint clauses were checked
against the maintained [40k.app Charge page](https://www.40k.app/rules/11-charge-phase)
on 2026-09-14. This is a secondary maintained App-data observation under the
repository's source-authority policy, not new official GW evidence. Existing
official source provenance remains authoritative historical evidence.

## Trace and scope decision

Ordinary Charge uses charging-unit selection, original roll and movement budget,
finite target commitment, parameterized path submission, `resolve_charge_move`,
engine-owned placement mutation, completion events and historical authority
validation. Setup-reactive Charge and Heroic Intervention also call the shared
resolver. The resolver currently records target-unit minimum distances, so one
model can mask another model's failure. Its preferred-distance feasibility check
subtracts a range from a unit minimum without validating a path.

`geometry.movement_reachability` already supplies immutable geometry/policy
queries, a bounded cache, validated witness paths, conservative impossibility
proofs and an explicit unresolved result. Consolidation is its existing consumer.
Charge should reuse this owner with Charge-specific endpoint requirements.

The ownership trace also found that charging actors are enumerated directly from
physical `UnitPlacement` rows. Proposal validation, movement resolution and
mutation accept one physical component, while enemy targets already use canonical
rules-unit identity. Therefore complete attached-charger coverage requires a
prerequisite migration: one canonical actor, all living component models in one
path, group coherency, atomic component placement mutation and corresponding
declaration/state/restore authority. An endpoint-only patch cannot establish that
invariant. The owner explicitly approved including this prerequisite in the Order 47 PR
on 2026-09-14.

## Acceptance work

- Per-model closer, preferred-distance and engagement obligations, including a
  leading model masking a trailing failure and a stationary charging model.
- Path-valid alternative witnesses, proven distance impossibility, obstacles,
  coherency, non-target constraints and explicit unresolved diagnostics.
- Canonical attached actors and targets, living/retained presence and atomic
  group movement after the prerequisite scope is resolved.
- Stale path/model/target context rejected before queue consumption; rejected
  rules proposals leave placement unchanged and issue a fresh request.
- Deterministic JSON-safe per-model evidence, facade submissions, viewer-scoped
  projections, checkpoint integrity and exact replay.
- Shared-consumer/static audit, matched base/head performance evidence, source
  and runtime artifact checks, external-contract checks and all final gates.

The completed implementation and validation boundaries are recorded below.

## Architecture and scope audit

The implementation extracts Charge endpoint values, geometric helpers and the
move resolver from the oversized phase module before extending them. Every new
runtime module is below 1,500 lines; the Charge phase size allowance shrinks.
`charge_movement_source` owns canonical living-model placement and construction
of an atomic replacement battlefield. The ordinary, setup-reactive and Heroic
consumers use the same resolver, mutation helper and pre-consumption path guard.
No named content handler, speculative hook registry, import-boundary change or
adapter mutation path is introduced.

`geometry.movement_reachability` gains only a spatial model-range goal and
per-target-group strict progress. Charge composes its existing path, terrain,
coherency and endpoint constraints into that immutable query. Other submitted
model endpoints remain fixed during an alternative search. A finite search may
return unresolved; it never establishes impossibility. Successful exemptions
require conservative distance bounds. No global optimization completeness claim
is made.

Each model records stable source `gw-11e-core-charge:model-endpoints`, physical
component identity, per-target distances and typed feasibility evidence. The
reviewed source package preserves the 11.04 browser observation at
2026-09-14T14:09:27.140Z, a short excerpt, reviewed obligations, non-affiliation and
historical official PDF provenance. Its JSON artifact, loader pin and source
registry are updated together. Contract 19 records the changed actor identities
and required model evidence; earlier released compatibility baselines remain
immutable. Orders 48–51 retain their separately scheduled semantics.

## Validation record

Focused tests cover leading-model masking, stationary models, mandatory engagement,
within-one-inch alternatives, conservative impossibility, obstacle detours,
unresolved reachability, attached actor selection and atomic movement, component
Advance restrictions, stale paths and aliases, modified/replaced targets,
serialized evidence tampering, checkpoints and exact replay. Accepted distance
exemptions are checked against historical component ownership, geometry and the
source-backed movement metric; a flying model cannot claim a ground-distance
bound. An attached-model checkpoint exercises an accepted exemption. Shared geometric
coverage includes circular, oval and rectangular bases, vertical distance and
cache invalidation. Existing success fixtures now use legal per-model endpoints
and authenticated initial placement histories; their deterministic seeds were
updated where the added history changed the roll.

The shared Charge run passed 129 tests; the added Heroic stale-path guard passed
two facade tests. The geometry subset passed 55 tests. Matched seven-sample
base/head performance evidence passes the unchanged Charge slice limits in
[the performance record](performance/order47/README.md). Final aggregate,
contract-client and packaging results are recorded with the PR.

Final validation on 2026-09-14 passed 7,907 behavioral tests with 85.10%
coverage, followed by 471 code-quality tests without coverage. Both suites used
18 xdist workers with work stealing; the behavioral run included the required
Node runtime on PATH. Ruff, formatting, mypy (3,010 source files), pyright,
11 import-boundary contracts, the exact eight-shard inventory check and
pre-commit passed. The source generator and runtime identity checks, external
contract check against base `46e2a9b5`, generated TypeScript client and five unit
tests, 342 TypeScript conformance assertions, and installed-wheel smoke all
passed. The wheel validated 2,793 engine resources, 27 schemas and six request
families. The final matched Charge slice averaged 0.019838 seconds on head and
0.019900 seconds on base; all seven samples satisfied the versioned limits.

## R47-001 historical movement capability correction

Invariant: an accepted Charge proof must use the source assignments, model existence
and living component inventory at the Charge event. A later casualty or revival
cannot change its earlier movement metric. The regression reproduces the reviewed
failure after a source-backed FLY leader is destroyed and retained; the equivalent
bodyguard casualty is a passing control.

The shared Charge history validator now reconstructs an immutable component using
exact wounds and model existence from `physical_model_authority_before_event` before
both Aircraft policy and catalog movement-capability evaluation. It never installs
that snapshot in game state. The bug-class search found this was the only movement
capability constructor in historical/restore authority modules; live movement calls
correctly use current components. All three Charge completion families already use
this history validator. Tests also exclude later keywords/model existence and a
static audit binds both constructors to the event-bound component.

Scope audit: one runtime module changes, using the existing physical history owner;
no boundary, decision type, adapter payload or source semantics change is introduced.
Contract 19 already specifies the historical proof authority, so its envelopes and
migration schema remain unchanged. Runtime identity and dependent contract examples
are regenerated. Restore performance diagnostics are retained in
[the R47-001 report](performance/r47-001/README.md); existing budgets are preserved.

R47-001 final validation passed 7,910 behavioral tests with 85.10% coverage and
472 code-quality tests (18 workers, work stealing). Ruff, formatting, mypy,
pyright, all 11 import boundaries, shard inventory and pre-commit passed.
The regenerated contract passed the base-ref check, five TypeScript unit tests,
342 conformance assertions and the installed-wheel smoke. The source-backed
retained-leader regression failed with the reviewed error on `cd46c143`, while
its bodyguard control passed; both pass with the historical component snapshot.
