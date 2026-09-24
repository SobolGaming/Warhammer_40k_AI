# Order 83 preflight — revival coherency anchors

Reviewed main: `03fd10e6d859743205c0c26bb653bc0b77b4bd85` (Order 82 / PR #502),
2026-09-24, America/New_York. GitHub confirms #502 merged at
`2026-09-24T15:59:27Z`; remote main matches and no PR is open.

Status: **blocked before complete 25-category certification**. Category 01
preflight reproduced C01-06. This is a bounded diagnostic, not a complete
operative-clause inventory, selected-snapshot certificate or closure of CAUDIT-01.
The owner approved fixing the identified gaps. This PR implements P01F; it is
not a PFINAL certification.

## C01-06 / P01F: phase-start revival anchors use current membership

Core 01.02.03 requires a revived model to be coherent with models that started
the phase on the battlefield. `healing_phase_start_model_ids` instead returns
the receiving unit's **current** placements whenever an effect is constructed.
An earlier revival in the same phase therefore becomes an anchor for a later
effect. The placement validator trusts that effect's list, permitting a chain
away from the actual phase-start survivors.

This is distinct from Order 82's correctly repaired engagement condition:
enemy-unit engagement is measured immediately before each return; friendly
coherency anchors refer to the start of the phase. Those times cannot share a
current-state snapshot.

The [executable diagnostic](../scripts/probe_order83_revival_anchors.py) uses
real canonical five-model units, recorded deployment and engine-owned destruction.
Two casualties occur in Player A's Fight phase. The lifecycle advances through
Player B's Command phase and records entry into Player B's Movement phase before
either revival. Three surviving friendly centres are `(10, 10)`, `(10, 11.5)`
and `(10, 13)`. Enemies are far away; all placements are on unobstructed ground.

The first generic grant legally returns model 004 at `(10, 16)`. The next call
to the shared helper adds 004 to the supposed phase-start inventory. A second
grant proposes model 005 at `(10, 19)`. It is coherent with 004, but farther
than the coherency limit from every model that started the phase on the battlefield.
The whole unit is coherent, so the distinct phase-start restriction is decisive.

| Case | Anchor inventory | Expected | Observed |
|---|---|---|---|
| Chained return at `(10, 19)` | Shared helper, includes newly revived 004 | Reject | Accepted and mutated |
| Same endpoint, temporal control | Actual phase-start survivors 001–003 | Reject | Typed invalid, no mutation |
| Return at `(8.5, 14)` | Shared helper | Accept | Accepted |

Both accepted placements and the invalid attempt round-trip JSON checkpoints,
project for both players, and reproduce exact replay. The temporal control
retains a usable request and accepts a legal retry. Accepted healing events
appear in both viewers' event streams. [probe-results.json](performance/order83/probe-results.json)
retains distances, identities and individual results.

The two generic grants and their explicit eligible-model restrictions are fixture
inputs, not a claim that a particular faction grants those two activations. Each
grant has a separate replay root; the second includes the first's accepted
physical history. Finite movement choices and revival proposals use
LocalGameSession throughout. No controller is replaced and no engine integration
stub is used. This is not a full source-trigger-to-trigger replay certification.
The implementation combines the shared Core invariant regression with the
real Necron producer and phase-transition regression described below.

## Source evidence

The complete expanded [01.02.03 clause](https://www.40k.app/rules/01-core-concepts#01.02.03)
was inspected in the normal browser on September 24. Its controlling subclause is:

> They must be set up in coherency with models in that unit that started that phase on the battlefield.

This matches the already registered complete revival source
`gw-11e-core-revival:revival`. Its retained provider observation is
`2026-09-24T13:16:10+00:00`, transcription SHA-256
`cce4b8e3cd0c8a6efb2e36e5a2c72c569be3675493482bdf8a33570a95889b02`, and
observation fingerprint
`5214e698c41ef0abba31b49f415e6808c5c79b9718cfaf0b7246c5a796207e3c`.
See the [registered audit](../data/source_audits/maintained_app_mirrors/revival_2026_09_24.audit.json).
Historical source records and hashes are unchanged.

[preflight.json](performance/order83/preflight.json) separately fingerprints the
fresh bounded excerpt observation, with provider, URL, observation date, policy and
retained scope. The provider exposes no App-data version. Game Datamissions'
changelog selects v946 and 18.04.01; that is not a co-versioned observation of
01.02.03. No official-App divergence, ambiguous wording or same-version mirror
disagreement was observed. Neither provider is Games Workshop-affiliated.

## Owner trace and same-class search

Generic/source producer → HealingEffect → engine-created placement request →
LocalGameSession / GameLifecycle / DecisionController → endpoint, whole-unit and
phase-start coherency validation → engine mutation and healing event → shared
viewer projection, checkpoint and ReplayRunner.

| Surface | Finding and treatment |
|---|---|
| `healing_geometry.healing_phase_start_model_ids` | Reads current placements; owns no phase occurrence or historical membership evidence. Shared query must consume authenticated phase-start authority. |
| `HealingEffect.phase_start_model_ids` | Carries caller-supplied IDs without an authenticated phase occurrence. Review pending, accepted and restored evidence together. |
| `healing_revival._validate_phase_start_anchor_coherency` | Trusts the supplied inventory. Whole-unit coherency does not enforce the earlier temporal boundary. |
| `catalog_command_restoration_runtime`, `stratagems_generic_rule_ir_runtime`, existing Necrons army-rule consumer | Construct revival-capable effects with the same current-placement helper. Migrate all shared callers; these are infrastructure consumers, not new faction certification. |
| Existing Chaos Daemons army-rule and `battle_shock_outcome_authority` producers | Construct IDs from current/event-time placements independently. Audit which grants can revive and route the same invariant through the shared owner. |
| `catalog_battle_shock_runtime`, `catalog_rule_consumption` | Other HealingEffect producers use active/all model IDs. Classify wound-only versus revival-capable behavior; do not broaden unrelated semantics. |
| `revival_engagement_history` | Authenticates pre-return engagement geometry and decision closure, not phase-start coherency membership. Restoring the reproduced bad chain succeeds. |
| `fight_model_authority_history`, phase transitions and historical physical authority | Existing event reconstruction is relevant to proving membership at the actual phase boundary. Avoid a second unauthenticated local history. |
| Existing healing tests and Order 82 regressions | Supply anchor tuples/current placements directly. The named phase-start coherency test places a model far outside the unit; it does not exercise two distinct effects in one phase. |

## Scoped prerequisite and acceptance

The mandatory insertion assigns **Order 83 / P01F / C01-06** to this repair and
moves **PFINAL to Order 84**. The inventory is 82 implementation PRs, S-MIRRORS
and PFINAL (84 rows). The owner explicitly approved the shared gameplay/history repair after this finding.

1. Establish one engine-owned phase-start battlefield membership authority,
   keyed by battle round, turn owner and phase. Capture or reconstruct it before
   start-of-phase rules can change presence. Preserve canonical attached/split
   lineage and rules-present retained models according to the controlling source.
2. Route every revival-capable producer through that owner. Keep current enemy
   engagement separate. Cover two effects in one phase, multiple models in one
   effect, actual phase changes, setup/ingress during a phase, no eligible anchors,
   attached units, destruction/removal and retained presence.
3. Write the failing facade regression before repair. Reject stale/forged/missing
   historical anchor evidence before mutation; authenticate pending and accepted
   records after restore. Cover both viewers, event deltas, legal retry, exact
   replay and a real existing producer composition without manual handler injection.
4. Confirm/update the adapter decision contract; regenerate versioned source,
   runtime identity, contract and client artifacts if their identities/shapes change.
   Keep loads and semantic support separate; add no new named handler or faction scope.
5. Audit scope and architecture, measure applicable matched component costs, run
   every required local/CI-equivalent gate, then publish this prerequisite alone.
   After it merges, restart the complete all-category audit from current main.

The initial scope pause followed [AGENTS.md](../AGENTS.md): “If the required solution is
materially broader than the apparent request, pause before broadening it.”
The [roadmap](CORE_RULES_REMEDIATION_ROADMAP.md) also states: “If the audit
discovers any gap, do not open or certify PFINAL”. A local placement-only change
would leave other producers and restore trusting the wrong temporal evidence.

## Validation and complete-game limits

The failing facade regression was written and observed before the production
repair. Live and restored placement evidence now shares the existing physical
history reconstruction at the canonical phase-opening timing boundary. The
source package is unchanged; Contract 37 makes the new evidence mandatory.
Final validation results and matched component measurements are recorded below
for the stable runtime.

Complete games attempted/completed: **0/0**. The fresh driver search covered
scripts, tools, profiling, AI, integration/replay tests and the headless adapter.
`submit_headless_decision` handles one pending decision; no representative
versioned legal complete-game driver or recording was found. Missing prerequisites
are declared legal rosters, terrain, seeds, decision policy, initialization through
normal completion and replay output, including Order 74's continuous terrain solver.
No driver or AI is introduced by this audit.

There are no full-game timing samples, mean or maximum. The below-60-second
mean and at-most-300-second observed maximum remain **uncertified**. The inspected
provisional host is Apple M5 Pro, 18 logical CPUs, 64 GiB RAM, macOS 26.7 (25G229).

## Approved implementation

The engine reuses `timing_window_opened` START_PHASE boundaries and the existing
physical-model history reconstructor. No second state ledger, fallback snapshot,
new timing event or named handler is introduced. The occurrence binds game,
battle round, turn owner, phase and exact opening event/window. Presence at that
boundary determines eligible model identities; present geometry determines their
current distances. A returned model cannot count itself as a neighbour.

All four revival-capable producer families consume this authority. Daemonic
Manifestation's existing source-specific restore checker consumes the same
historical query. Other healing producers are wound-only paths: lost-wound
restoration caps the heal to missing wounds, Daemon non-Battleline healing caps
its amount, and catalog failed-Battle-shock healing rejects a pending revival.
Their current-model metadata does not authorize a battlefield revival.

The placement request and accepted event carry required source-bound evidence.
Finite revival selections validate their occurrence before submission; pending
finite selections and pending/completed placements are checked on restore.
Accepted placements are remeasured against their historical pre-return geometry.
Current enemy-unit engagement remains the separate Order 82 predicate.

The new two-grant facade regression rejects the old illegal chain without
changing state or popping the request, accepts a legal retry, projects for both
players, and reproduces persistence and replay. Forged inventories, including
matching changes to both pending request and request-event payload, are rejected.
The automatically loaded Necron producer verifies that a model returned in
Command becomes an anchor only after the real lifecycle enters Movement.
The source-backed Death Denied generic RuleIR pipeline composes wound healing
and revival with recorded pre-phase damage. Existing attached-unit, retained-presence,
Daemon, cargo and catalog restoration regressions exercise the shared consumers. These bounded regressions do not claim
that a named faction grants the diagnostic's two independent generic activations.

Contract 37, replay v31 and persistence v29 reject obsolete histories. Released
contract baselines stay immutable. No behavioral test file was added, removed or
renamed; new cases extend existing inventoried files, with named fixture helpers.

## Performance measurement scope

The historical diagnostic runs only against exported main `03fd10e6d859743205c0c26bb653bc0b77b4bd85`, as its
module docstring states. The original Order 82 benchmark fixtures lacked phase
opening events; both runtimes now receive identical explicit phase-start fixtures
for the matched measurements in `performance/order83`. The original Order 81/82
baseline artifacts and budgets remain unchanged. Current quality gates read the
new matched pair and enforce those same budgets. The new fixture helper is
included in benchmark provenance. Inherited runtime-pinned component heads are
refreshed serially, with no competing test/build workers or coverage.


## Final validation

The final behavioral run passed **9,196 tests** with no failures or errors.
Pytest exited with code 1 because its coverage reporter could not open the
collected SQLite coverage file. The collected data remained valid: standalone
`coverage json --fail-under=85` and `coverage report --fail-under=85` both passed,
with **85.22%** combined line/branch coverage. No production code changed between
collection and reporting. Ten unclosed-SQLite ResourceWarnings were retained;
this warning class is also recorded in Orders 81 and 82.

All **616 code-quality tests** passed. Ruff, formatting, mypy, Pyright, import
contracts, the exact eight-shard inventory check and all-file pre-commit passed.
The base-ref external contract check, generated TypeScript client, TypeScript
unit tests, installed-wheel smoke and 342-assertion conformance scenario passed.
All 22 serial performance measurements completed; matched revival samples stayed
within the existing budgets, with a maximum head sample of about 3.11 seconds.
No budgets were raised or difficult cases removed.

[validation.json](performance/order83/validation.json) retains exact commands,
attempts, report recovery and output fingerprints.
[inherited-refresh.json](performance/order83/inherited-refresh.json) retains
measurement commands and provenance. The earlier aggregate attempt exposed two
obsolete contract-wrapper test literals; those were updated and the complete
behavioral suite rerun with coverage. The quality rerun followed expansion of
abbreviated documentation hashes to satisfy the edition-identity audit.
PFINAL / CAUDIT-01 remains open at Order 84.
