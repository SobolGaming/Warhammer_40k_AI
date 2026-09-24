# Order 81 preflight — revival and parameterized placement

**Current status:** the owner approved the shared-projection prerequisite.
This PR implements Order 81 / P03E / C03-05. The preflight observations below
remain historical evidence from main `45561d864c3634ce1d0e00d2b6599091ef43ed58`.
Order 82 / P01E remains a separate semantic prerequisite; PFINAL is Order 83.


Reviewed main: `45561d864c3634ce1d0e00d2b6599091ef43ed58` (Order 80 / PR #500).
Review date: 2026-09-23, America/New_York (2026-09-24 UTC).
Status: **blocked before complete 25-category certification**. CAUDIT-01 remains open.

GitHub confirms PR #500 merged, remote main matches the checkout, and no PR is
open. This bounded preflight found two reproducible defects. It is not the
complete operative-clause/FAQ inventory, a selected-snapshot certificate, or a
replacement for the required fresh audit after every prerequisite merges.

## C01-05: revival restricts enemy models instead of enemy units

Core 01.02.03 permits revived models to engage an enemy unit already engaged
with the receiving unit. The engine instead compares individual enemy model
IDs. Engagement with another model of that same enemy rules unit is rejected.

The [diagnostic](../scripts/probe_order81_revival.py) uses canonical five-model
infantry units, an engine-recorded casualty with authenticated destruction and
deployment history, and an explicit generic full-wound revival fixture. It
makes no claim about a faction ability. Fixture construction precedes the
session's replay root; the placement is submitted through LocalGameSession.
A separate read-only validation call exposes the precise underlying diagnostic
without mutating state or bypassing the facade submission.

All models are on ground level, with no terrain. The receiving unit's four
survivors have centres at `(10, 10)`, `(10, 11.5)`, `(10, 13)`, `(10, 14.5)`.
The enemy's five models have centres at `(13 + 1.5*i, 10)` for `i = 0..4`.
Only enemy model 001 initially engages the receiving unit. Both units are
coherent. The removed fifth friendly model is the revival candidate.

| Proposed centre | Enemy models engaged by returned model | Source result | Observed result |
|---|---|---|---|
| `(12, 12)` | 001 and 002, both in the already-engaged enemy unit | Legal | Invalid: `Revived model engages a new enemy model.` |
| `(11.5, 12.5)` | Only previously engaged model 001 | Legal | Accepted, returned model restored |
| `(8.5, 15)` | None | Legal | Accepted, returned model restored |

The rejected proposal leaves the entire lifecycle payload unchanged. Both
accepted controls proceed through the lifecycle. All three cases round-trip
session persistence exactly and reproduce through ReplayRunner. These are
reproductions of current behavior, not passing regressions for repaired rules.
The unsuccessful early probe used a casualty without destruction history;
that fixture was corrected to use the real destruction owner before retaining
the results. No production validation was weakened.

## C03-05: pending placement cannot be projected

For all three cases, calling `LocalGameSession.view` for either player while
`submit_healing_revival_placement` is pending raises:

`GameLifecycleError: Parameterized DecisionRequest payload missing proposal_request.`

The engine creates a flat typed `HealingRevivalRequestPayload`. The shared
`adapters.projection._proposal_view` unconditionally expects a nested
`proposal_request` for any parameterized decision. The engine submission path
still accepts valid control placements, but ordinary clients and the headless
adapter need the viewer projection to present or generate a proposal.

Both accepted controls project successfully after the revival request is
consumed. The rejected legal placement leaves that request pending, so both
viewers remain broken. Checkpoint and replay success does not certify viewer
support. Retained [probe-results.json](performance/order81/probe-results.json)
records initial and final viewer outcomes separately.

## Source evidence and limitations

The normal browser exposed the complete expanded
[01.02.03 clause](https://www.40k.app/rules/01-core-concepts#01.02.03).
Its operative engagement condition includes:

> but only if those enemy units were already engaged with the unit that model is being returned to.

The enclosing sentence permits engagement with one or more enemy units; it does
not restrict the particular enemy model. Other requirements include existing
unit membership, Starting Strength, applicable wounds/wargear, coherency with
phase-start models, attached membership, and embarked capacity. This preflight
does not certify every one of those requirements.

The browser observation exposes no App-data version. The Game Datamissions
[changelog](https://game-datamissions.com/11th/rules/changelog) currently selects
v946 and its Rapid Disembark entry; this does not establish a co-versioned
observation of 01.02.03. No co-versioned mirror disagreement or official-App
exception was observed. No new official-App comparison is claimed.

[preflight.json](performance/order81/preflight.json) pins provider, URL,
observation timestamp, the quoted operative subclause's SHA-256 and its
observation fingerprint. This is a deliberately bounded excerpt observation,
not a registered runtime source package or a complete category transcription.
The fingerprint detects changes to the retained record, not website authenticity.
The semantic prerequisite must retain/register its complete controlling source
under the existing source policy before changing runtime semantics. Historical
PDFs, source packages, registry entries and fingerprints remain unchanged.

## Authoritative paths and same-class search

Generic revival producer -> HealingEffect -> engine-created placement request
-> LocalGameSession / GameLifecycle / DecisionController -> shared proposal
validation -> engine restoration and events -> checkpoint / ReplayRunner.
The pending request also flows through shared viewer projection before clients
or `submit_headless_decision` can construct the submission.

| Owner or consumer | Evidence and required treatment |
|---|---|
| `healing_geometry.healing_phase_start_enemy_engagement_model_ids` | Enumerates individually engaged enemy models, not canonical enemy rules units. |
| `HealingEffect` in `healing.py` | Serializes those model IDs as the revival restriction evidence. Any migration must preserve authenticated historical ownership. |
| `healing_revival._validate_revived_model_engagement` | Rejects the set difference of proposed enemy model IDs against saved IDs. The reproduced legal endpoint passes prior endpoint and coherency checks. |
| `catalog_command_restoration_runtime`, `stratagems_generic_rule_ir_runtime`, existing Necrons army-rule consumer | All construct the same HealingEffect using the shared geometry helper. Audit their evidence creation and time boundaries; do not certify faction semantics from this Core fixture. |
| `healing_revival.request_healing_revival_placement` | Emits a parameterized request with a flat payload, inconsistent with the shared projection assumption. |
| `adapters.projection._proposal_view`, `adapters.headless.submit_headless_decision` | Projection is a shared prerequisite, including for headless payload generation. Fixing only a UI or suppressing this error would leave authority divergent. |
| `return_on_death.build_return_on_death_placement_request` | Static search found another flat parameterized placement payload; its restriction is source-specific and must not be conflated with 01.02.03. Not separately reproduced here. |
| `catalog_model_materialization_runtime` and existing `cult_ambush` placement builder | Also emit flat parameterized payloads. These are same-shape adapter consumers found statically, not new faction-support claims. Include their existing request families in the shared contract audit. |
| `movement_proposals`, `prebattle`, `stratagems_requests` | Existing nested proposal producers are comparison controls; preserve their validation and viewer behavior. |
| `docs/ADAPTER_DECISION_CONTRACT.md`, Phase 14H | Currently documents the stricter enemy-model restriction and public revival visibility. The owning fixes must update the contract and its executable facade evidence. |

The existing 29 Healing tests pass. They cover invalid placement, retained
presence, stale input and lifecycle submission, but do not detect this
same-enemy-unit/new-model case or full viewer projection of the pending request.
Passing those tests does not close either finding.

## Required prerequisite sequence

The roadmap's fail-closed insertion rule assigns two separate owners. No
production implementation was included in the original preflight. P03E was
subsequently approved and is implemented below.

1. **Order 81 / P03E / C03-05 — shared parameterized projection.** Inventory all
   existing parameterized request producers and reconcile them through one
   explicit typed projection/interaction contract. Use real engine-produced
   requests through LocalGameSession, both viewers, event deltas, headless and
   network consumers, restore and exact replay. Cover malformed/stale requests
   and source visibility. Preserve strict unsupported diagnostics; do not add a
   generic dictionary fallback. Update the adapter contract and versioned
   artifacts if required. Existing faction consumers are regression coverage
   of shared infrastructure, not broader faction certification.
2. **Order 82 / P01E / C01-05 — revival engagement authority.** Pin/register the
   controlling 01.02.03 source. Write failing facade regressions for the
   demonstrated legal placement, and preserve rejection of a genuinely new
   enemy rules unit. Use canonical attached rules-unit identity and rules-present
   models, including retained Fight On Death presence; preserve phase-start
   anchors, source restrictions, atomicity, invalid retry and restoration
   history. Audit all HealingEffect producers, consumers and restore paths.
   Authenticate any changed evidence from retained source/decision/history;
   ambiguous old records must not receive an invented unit identity.

Each prerequisite needs scope/architecture review, focused regressions,
applicable matched performance evidence, required generators and contract
checks, and the complete final validation gates before its PR. Publish, review
and merge one at a time. After both merge, **PFINAL is Order 83** and requires a
fresh complete audit of all 25 categories, clauses/FAQs, v931/v946 obligations,
September 10 dispositions and cross-category consumers. CAUDIT-01 stays open.

The scope pause follows [AGENTS.md](../AGENTS.md): “If the required solution is
materially broader than the apparent request, pause before broadening it.”
The [roadmap](CORE_RULES_REMEDIATION_ROADMAP.md) also states: “If the audit
discovers any gap, do not open or certify PFINAL”. A certification PR cannot
substitute for these adapter and gameplay repairs.

## Complete-game performance and validation

Complete games attempted/completed: **0/0**. The fresh search of scripts, tools,
profiling, AI, integration/replay tests and the headless adapter found bounded
slices and a single-decision adapter, but no representative versioned legal
complete-game driver or complete recording. Missing prerequisites remain legal
rosters, terrain, seeds, decision policy, initialization-to-normal-completion
and replay output, including a workload exercising Order 74's continuous
terrain solver. No new driver or AI is introduced.

There are no per-game timing samples, mean or maximum. The below-60-second mean
and at-most-300-second observed maximum remain **uncertified**. The inspected
provisional host is Apple M5 Pro, 18 logical CPUs, 64 GiB RAM, macOS 26.7
(25G229). The original preflight made no runtime or performance-improvement claim.

Focused validation and evidence hashes are in
[preflight.json](performance/order81/preflight.json). The original preflight did not run final aggregate gates or add behavioral
test files. The implementation and its separate validation evidence follow.


## Approved P03E implementation

The violated invariant is that every registered parameterized decision can be
projected through the same engine-authored request context used by interaction
metadata. The owning abstraction is `engine.interaction_metadata`: its existing
13-family registry now requires a typed layout for every parameterized entry.
Four families use flat payloads (healing revival, return on death, materialization
and Cult Ambush marker placement); nine use nested `proposal_request` objects.
`parameterized_proposal_request_payload` extracts only the registered layout,
authenticates any embedded request/decision/actor identity, and adds the existing
identity envelope without modifying the original DecisionRequest.

Both interaction metadata and `adapters.projection` consume this reader. Unknown
families, malformed contexts, wrong layouts and drifted identity fail closed.
The shared redaction owner runs before proposal extraction. Existing domain
submission validators remain authoritative. No gameplay semantics, source
package, rule handler, mutation route, schema family or visibility policy changes.
The existing adapter contract already promises this proposal envelope for all
parameterized families; contract 35 therefore keeps its shapes and version.
The runtime identity and generated renderer examples are refreshed. Previously
the conformance generator incorrectly nested all families, masking the defect;
it now uses the same explicit layout inventory.

The base reproduction failed all seven real producer cases for the three sibling
families, with the exact missing-proposal error. An earlier exploratory assertion
tried full game projections from those subsystem fixtures without their required
GameConfig; it was corrected to test real producer requests through the shared
adapter request/proposal projection functions. Revival has a complete configured
session and exercises LocalGameSession, UI, network and headless submission,
both players, event deltas, exact checkpoint recovery and replay. Invalid stale,
wrong-kind, malformed, wrong-unit and malformed-placement submissions preserve
state and a usable pending projection. All published parameterized kinds,
identity/layout corruption and hidden requests have direct regression coverage.
These source-specific producer checks certify shared projection behavior only.

Architecture/scope audit: two existing runtime modules change. A typed registry
entry and one common reader replace the two competing readers; no new runtime
module, dependency boundary, cache or named handler is introduced. C01-05 remains
open and is deliberately not presented as fixed by these valid revival controls.

`projection-base.json`, `projection-head.json` and `projection-budgets.json`
retain matched serial component measurements and a required quality-gate budget.
The base is measured using the exact base runtime with the same workload and
fixture files as head. Fixture construction is outside the microbenchmark;
there are no full-game samples. Run with `PYTHONPATH=.:src uv run --no-sync python
scripts/benchmark_order81_projection.py --output <path>`. On the base, the flat
proposal cannot be projected; this failure is retained separately from timing
and is not a correctness oracle. Historical `probe_order81_revival.py` deliberately
expects the old defects and must be run against the named base runtime.

Final commands, counts, hashes and limitations are recorded separately in
[implementation-validation.json](performance/order81/implementation-validation.json).

## PR #501 field-redaction review correction

Review of `c37ae4b17449106abee1f90a2039adfc0a6bc8be` found that the proposal
projection enforced whole-request secrecy but extracted raw field values. A
protected authority key inside arbitrary `HealingEffect.source_context` could
therefore survive in `pending_proposal` after being removed from
`pending_decision.payload`. This was a latent viewer-boundary defect; no current
producer was observed inserting such a protected key into a flat request.

The fix reconstructs a presentation-only typed request from
`public_decision_request_payload` before the existing engine layout/identity
reader extracts proposal context. The same-class audit found raw nested
interaction projection; it now consumes the same scrubbed request path.
Interaction metadata also derives from the already-redacted pending request.
All protected-key policy remains in `adapters.redaction`; authoritative payloads,
engine validators, layout registrations, and revival eligibility are unchanged.
The correction changes only `adapters/projection.py` in runtime code.

Regressions first reproduced the defect in an engine-produced revival request
and all 24 parameterized conformance examples spanning the 13 registered
families. They cover recursively protected destruction, psychic, ingress, and
target-replacement fields, preserved public siblings and identity, both players,
nested interactions, unchanged authoritative state, checkpoint restoration,
event redaction, successful submission, and exact replay. A static audit guards
shared redaction before every derived request projection.

Matched diagnostics compare the reviewed runtime with the fix using
`scripts/benchmark_order81_redaction.py`. The original request-view budget remains
unchanged and is remeasured against the original main runtime with the same
current fixture. Run the review diagnostic with `PYTHONPATH=.:src uv run --no-sync
python scripts/benchmark_order81_redaction.py --output <path>`; for the reviewed
base, substitute the archived commit's `src` path and retain its `pyproject.toml`
and `contracts/` alongside it. Both runs use the current benchmark and fixture.
Fresh inherited workload measurements, validation commands and
results are recorded in [review-validation.json](performance/order81/review-validation.json).
Original validation records remain historical evidence for the reviewed commit.
No full-game performance or final Core Rules certification is claimed.


The first quality aggregate detected 22 stale-evidence guards: Orders 64–80
require fresh head measurements whenever the verified runtime identity changes.
The required 18 head reports are remeasured serially without coverage or competing
test/build workers. Baselines, workload scripts, fixtures and numeric budgets
remain unchanged. [inherited-refresh.json](performance/order81/inherited-refresh.json)
records each command, duration, exit status and output hash. These are mandatory
validation artifacts for the same two-module repair, not additional rule changes.
