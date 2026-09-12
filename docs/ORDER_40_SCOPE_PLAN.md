# Order 40 — Smokescreen timing and source-attributed Cover

Finding P15A / C15-01. Base: main `506dad94` (Order 39).
Status: implemented; final local validation complete.

## Invariant and source

At the start of the opponent's Shooting phase, a player may spend 1 CP to select
one friendly SMOKE rules unit. Until that phase ends, Cover applies to attacks
against the selected unit and against units whose incomplete visibility from the
individual attacker is caused by models in the selected unit. There is no extra
Hit-roll modifier. Existing ranged Cover, denial and Ignores Cover rules apply.

The source is [Core 15.10 on 40k.app](https://www.40k.app/rules/15-stratagems),
observed through its search-index representation on 2026-09-12. Direct retrieval
returned HTTP 403. The package retains the complete operative WHEN, TARGET and
EFFECT transcription with layout whitespace normalized, checked against the
retained GW Core Rules PDF (printed/PDF page 57); both sources specify 1 CP.
It does not claim a page capture or an App-data version. The existing maintained
App-data mirror policy admits the non-affiliated provider. The original GW PDF
and its hash remain historical primary evidence; no new official GW observation,
co-version mirror comparison, or excluded content is claimed.

`core_smokescreen_2026_09/artifacts/package.json` and its audit pin the operative
text, provider URL, observation time, evidence, stable source ID and generated RuleIR.
The source authority registry authorizes the exact package, source inventory,
audit tuple and catalog hash. Load and semantic-execution statuses are separate.
The typed eager loader rejects artifact, schema, source and execution drift.
Regenerate and verify offline with `tools/build_core_smokescreen_source.py` and
its `--check` flag.

## Authoritative path and scope

Reviewed JSON -> Core Stratagem catalog -> generic Shooting-start hook ->
owner-tiered timing batch -> finite DecisionRequest -> shared validation/CP
spend -> generic RuleIR persistence -> model-group causal visibility -> shared
Cover skill modifier and save metadata -> phase-end expiry, adapters and replay.

The stable rule/catalog identity is `gw-11e-core-stratagems:core:smokescreen`.
Its executor is now `generic:rule-ir`. The old named executor, selected-target
policy and Hit modifier are retired. No named handler is added, and the existing
faction named-handler budget is unchanged. `cover_from_obscuring_models` is a
structured grant consumed by the shared attack owner; this source is its real
consumer. No faction/display-name branch or speculative registry is introduced.
The existing generic Stratagem timing candidate service supplies finite choices;
source timing and eligibility determine availability. Existing Movement-end
registry composition was extracted before composing the Shooting-start provider.

`obscuring_model_cover_sources` uses current canonical rules units, persisted
effect lineage and the shared retained-presence battlefield scenario. It invokes
`TerrainVisibilityContext.not_fully_visible_because_of` for the selected source
model group. This preserves Order 32's continuous geometry and its accepted
independent/same-part counterfactual causality. Unrelated blockers do not become
Smoke evidence. Current positions and source identities enter opaque commitments;
no new cache, sampled visibility, timeout answer or endpoint approximation exists.

The bug-class audit covered all effect producers and consumers, source rows,
finite/parameterized choices, phase hooks, Hit/save paths, adapter records, replay,
and generated reports. An existing Aeldari restriction used the old Smoke tag
for its explicit Hit/range effect. It now has a separate generic restriction tag;
its numeric behavior remains covered by existing faction regressions. Cover-only
fixtures now use the real generic Cover grant. Remaining faction source/Stealth
interpretation is outside this Core finding.

The adapter contract records the switch to the existing finite family and its
public viewer scope. No schema/version migration is required; runtime identity
and generated contract examples change. Module/import boundaries, source policy
and geometry semantics are preserved. One behavioral test file is added; the eight-shard inventory is regenerated
from the complete successful local JUnit profile.

## Acceptance and delivery

Focused evidence covers direct and obscured targets, a moved source/observer,
removed and retained models, attached Leader blockers, Ignores Cover, Cover denial,
terrain/Indirect Fire non-stacking, ranged/melee separation, same-total source
replacement, source artifact pins, automatically offered finite choices, decline,
CP/keyword drift rejection before pop, both player projections, persistence,
phase-end expiry and exact replay through activation and an actual attack.

The component base/head assessment passes all four versioned budgets, with
0.073–1.908 ms mean query times and a maximum sample average of 2.120 ms. No
complete-game timing is certified. See
[performance/order40/README.md](performance/order40/README.md).

Ruff check/format, mypy (2,956 files), Pyright and all 11 import contracts pass.
The exact source generator and runtime identity checks pass. Generated reports
were refreshed using `tools/generate_ability_support_matrix.py`; the complete
code-quality gate verifies their reproducibility. External contract compatibility
passes against main `506dad94de11c6607ecfa3a6c631c4ccb9e74d85`. Installed-wheel
smoke validates 27 schemas and six request families. TypeScript generated-client
verification, typecheck, all five unit tests and the live HTTP conformance scenario
pass (342 assertions, exact replay).

The host has Node but no npm executable, so `npm ci` could not run locally. The
package script entrypoints were executed directly with bundled Node against the
existing dependencies. CI performs the clean npm installation. The active macOS
semantic audit is included in the complete local code-quality suite.

Final runtime fingerprint:
`acc633bc13cf28001d90a1e99a2553e210ec574e79684703979aacc4fba0b908`.
The first aggregate run reached the 85% coverage gate but found two older Aeldari
fixtures that expected shooting to begin without an optional phase-start decision.
Their shared setup now declines the real Stratagem request through the existing
engine submission helper. The production implementation is unchanged; focused
regressions pass and the complete behavioral coverage gate is rerun for the final
successful JUnit/shard profile.

Final behavioral validation passes all 7,431 tests with 85.04% branch coverage
(85% required), using 18 xdist work-stealing workers and the required Node PATH.
Ten existing SQLite ResourceWarnings were reported. The complete successful
JUnit profile supplies all eight regenerated shards and their retained duration
and report-hash evidence. There was no second no-coverage behavioral gate.

The first code-quality run found its parallel source-inventory assertion still
expected 24 packages. It now expects the exact 25-package inventory, including
this reviewed Core source package; the existing 33 immutable historical
observations remain unchanged. The complete code-quality gate is rerun after
this test-only correction.

Final code-quality validation passes all 435 tests without coverage, with
18 xdist work-stealing workers. The exact eight-shard check, all-files pre-commit
checks and staged diff audit pass. No runtime change followed the successful
aggregate behavioral run.

Publication branch: `codex/order-40-smokescreen`; target: `origin/main` at
`506dad94de11c6607ecfa3a6c631c4ccb9e74d85`. Hosted CI results are reported on the PR.
