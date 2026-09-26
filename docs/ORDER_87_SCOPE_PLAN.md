# Order 87 / P02F — random profile characteristics

Status: implemented; all required local gates and independent publication review passed.
Baseline: `7f4384b8` (Order 86 / PR #508).
This implements C02-06; PFINAL roadmap-wide certification remains separate.

## Required invariant

Random profile characteristics must retain a typed, source-linked expression
through catalog loading and runtime materialization. Only an engine-owned rule
evaluation may roll that expression. Read-only projection, validation, retry,
restore and replay must consume the same authenticated result for that evaluation.
An unresolved expression must never be treated as a numeric zero or a dash.

The requested scope includes the once-per-unit Movement timing and the individual
model/weapon timing for other random characteristics. Existing random Attacks and
Damage behavior must be preserved. Order 92 separately owns random melee attack
allocation; Order 88 owns source-dash Strength. Neither is folded into this change.

## Source investigation and owner interpretation

The expanded [Game Datamissions Core Rules page](https://game-datamissions.com/11th/rules/core-rules)
was inspected on September 25, 2026. Its live body did not expose an App-data
version. This is an independent browser observation corroborating the historical
Order 84 finding, not an assertion that the body belongs to a changelog version.
No official-App observation or co-versioned mirror comparison is claimed.

The inspected statements have these effects:

- 02.02.03: evaluate random Movement when selecting the unit to move, using a
  roll for the unit. Generate random Attacks separately for each weapon during
  attack generation. Determine random Damage for the allocated attack; an
  expression's intrinsic offset belongs to the characteristic. Evaluate other
  random characteristics individually for each model or weapon when needed.
- 03.01.03: refers to 02.02.03.
- 03.01.01: models with different Movement values retain different maximum
  distances for a move that uses Movement. Its example contains fixed values.

Searching the site's Core text for `random` returned Random Characteristics,
Random Movement and Deadly Demise; it exposed no mixed-profile clarification.

The unresolved case is one attached rules unit containing different random
Movement expressions, potentially alongside fixed-Movement models. The complete
observed text does not specify how its whole-unit roll requirement combines with
the per-model distance rule in that case. In particular, a single physical roll
cannot directly evaluate both D6 and 2D6 without a further interpretation.

On September 25 the owner supplied a provisional convention for mixed Movement:
fixed values remain fixed; all models with one random expression share one roll;
different expressions use independent rolls, without reusing component dice.
For example, fixed 6, D6 rolling 4 and 2D6 rolling 3+5 yield per-model limits of
6, 4 and 8 inches. These remain maximum allowances and do not relax coherency.
This convention resolves an underspecified hypothetical, not a contradiction
between the quoted rules. It is recorded as an owner interpretation, not as
additional official-App or maintained-mirror wording. The supplied Wahapedia
reference does not replace the project's maintained-mirror source authority.

The complete 02.02.03 statement was observed again in the expanded Game
Datamissions browser UI at 2026-09-25T19:21:58+00:00. Section 03.01.03 explicitly
cross-refers to it. The offline generator, hash-pinned package, source-authority
registry and audit preserve this observation separately from the owner convention.

The owner explicitly approved completing the expanded Wounds initialization/healing,
save grouping, Leadership, weapon Range and Objective Control/scoring scope in
this single PR. Separate engine evaluation boundaries remain required; projection
and validation must never roll. This approval supersedes the earlier scope question.

## Authoritative path and owners

| Boundary | Existing owner | Required treatment |
|---|---|---|
| Typed catalog values | `core/attributes.py`, `core/datasheet.py`, `core/weapon_profiles.py` | Represent an unresolved expression separately from resolved numeric and sentinel values; serialize source identity and reject invalid shapes. |
| Runtime model construction | `engine/unit_factory.py` | Preserve descriptors through materialization and copies; audit starting-Wounds initialization, which currently consumes a numeric value. |
| Ordinary move selection | `engine/phases/movement_handler.py`, `movement_action_decisions.py` | Bind the roll to the canonical rules unit and the actual accepted selection, before consumers publish numeric movement budgets. |
| Movement budgets | `engine/movement_budget_modifiers.py`, `engine/phases/movement_validation.py`, `movement_resolvers.py`, `movement_options_dice.py` | Consume the recorded value, apply existing modifiers, preserve individual model ownership and witnessed-path validation. |
| Reactive movement | `engine/triggered_movement.py` and its runtime helpers | Use the same selection/evaluation authority; distinguish each accepted move from retries and separate phase occurrences. |
| Dice and events | `engine/decision.py`, `core/dice.py` | Reuse deterministic physical dice and event records; authenticate descriptor, scope, owner, selection and expression. The current manager's local M cache alone does not provide this lifecycle authority. |
| Random Attacks | `engine/weapon_declaration.py` | Preserve physical per-weapon roll identity and existing attack-generation consumers. |
| Random Damage | `engine/attack_sequence_geometry_targets.py` | Preserve allocated-attack timing, intrinsic offsets, reroll continuation and saved-attack behavior. |
| Other attack characteristics | `engine/attack_sequence_hit_wound.py`, `attack_sequence_damage_resolution.py`, `attack_sequence_selection.py`, `saves.py`, `damage_allocation.py` | Resolve values at the owning rule evaluation, then reuse them through grouping, choices and continuation; avoid RNG during candidate inspection. |
| Leadership | `engine/battle_shock.py` and catalog characteristic consumers | Resolve individual model values before the unit-level comparison, preserving source modifiers and the test continuation. |
| Objective Control | `engine/objective_control.py`, Action eligibility, objective-control and scoring authorities | Distinguish engine evaluation from read-only queries, and bind historical scoring evidence to the exact resolved values. |
| Adapters and restore | catalog/live projection, shared redaction, lifecycle and replay loaders | Project expressions and authorized results without rolling; reject tampered or orphan evaluation evidence and preserve viewer scope. |

This is a consumer inventory, not a claim that every listed module must change.
The implementation should centralize evaluation and result lookup in a small,
content-neutral engine owner. Avoid faction-specific handlers and mutation in
numeric getters. Existing fixed-profile paths should retain their behavior.

## Acceptance and delivery gates

1. Load typed random profiles from actual catalog payloads and round-trip them;
   reject invalid expressions, missing source identity and descriptor drift.
2. Exercise ordinary and reactive selections through `LocalGameSession` or
   `AdapterGameSession`, including attached components, repeated moves in
   different phase occurrences, modifiers, retries and witnessed proposals.
3. Show the once-per-unit/group result and independent model/weapon results at
   their required evaluation boundaries. Confirm that views and validation do
   not consume dice, and that later uses receive fresh results.
4. Preserve existing random Attacks/Damage regressions, including no Damage roll
   for saved attacks and expression offsets before modifier arithmetic.
5. Cover invalid/stale submissions, both viewers, JSON-safe evidence, checkpoint
   restore, tampered history rejection and exact replay using real domain objects.
6. Add a feasible static audit against unresolved numeric consumption. Inspect
   the final scope and architecture before aggregate validation.
7. Update the adapter decision contract and applicable schemas/compatibility
   version, regenerate runtime identity and external artifacts, and refresh the
   eight-shard inventory if behavioral test files are added or moved.
8. Retain matched base/head component or gameplay-slice performance evidence;
   do not claim complete-game budgets from those measurements.
9. Run the complete required gates from `AGENTS.md`, the exact-base contract
   check, generated-client checks, conformance and installed-wheel smoke.
10. After implementation, have an independent subagent review the complete
    change. Address findings and repeat until approval. Only then commit the
    intended final changes, push and create the requested pull request.

Implementation review approved runtime manifest `904893c1` after five findings were
fixed and rechecked: non-attack Toughness, Dark Pacts Leadership, OC after physical
placement, Action occurrence authentication, and normalized source-row generation.
A subsequent malformed-descriptor boundary failure was fixed with an explicit typed
rejection and independently approved. The reviewer also approved the final test-only
contract metadata and automatic-hit expectation corrections. Final aggregate
validation and independent publication review passed.

## Final scope and architecture audit

The owner-approved expanded invariant requires changes across setup, attacks,
movement, healing, tests, scoring and persistence. The broadest diff is mechanical:
physical-health consumers now use explicit initialized `initial_wounds` /
`current_wounds` accessors, while catalog descriptors may retain unresolved Wounds.
This prevents model liveness, damage and healing from rolling a characteristic or
silently accepting uninitialized health. Existing phase choices and witnessed
movement continue through the shared adapter/lifecycle path.

Source normalization owns text-to-descriptor conversion; core owns immutable typed
values; engine boundaries own dice and state replacement; restore authenticates
source, physical owner and occurrence. The same evaluator covers ordinary/reactive
Movement, attack and non-attack characteristics, model creation, Leadership and
Objective Control. Physical placement completion refreshes current OC for later
pure rule queries, including reserves, disembarkation, materialization and returns.
A no-options Action evaluation retains an explicit engine outcome. No new faction
handler, architecture exception, fallback, player-choice bypass or out-of-scope
content is introduced. Contract 40 records the necessary descriptor/nullability
changes and rejects old runtime history rather than inferring missing evidence.

Focused acceptance: 163 tests across Order 87, Crushing Impact, Dark Pacts and
Horror materialization; 51 normalized catalog tests; 41 module/source artifact
quality tests. The reviewer independently reproduced and rechecked the OC move,
forged Action scope and normalized-source ingestion cases. Matched performance
measurements and their limitations are retained in
[performance evidence](performance/order87/README.md).

Baseline diagnostic check on September 25:

```sh
uv run --no-sync pytest tests/unit/test_phase10j_dice_semantics.py \
  tests/unit/test_phase13b_shooting_declarations.py -k random -q --no-cov
```

Result: 5 passed, 294 deselected. This focused check establishes existing random
Attacks/Damage and dice-manager behavior only; it is not Order 87 acceptance or
an aggregate final gate.

## Initial publication validation — September 26, 2026

Final runtime manifest:
`904893c11619a82868f043182ee2c96023cbaaa1b686a3875d3c77028bc27726`.
The complete behavioral suite passed with **9,413 tests and 85.16% coverage**, in
738.60 seconds, using 18 xdist work-stealing workers. Ten unclosed-SQLite-connection
ResourceWarnings were reported. At initial publication, no runtime edits followed
that successful run.
The eight-shard inventory was regenerated from its complete successful local
JUnit profile; the report SHA and host details are retained in
`ci/test_shards/durations.json`. The exact inventory check passed.

Ruff check and format, mypy (3,275 files), Pyright, all eleven import-boundary
contracts, source generation, runtime identity and pre-commit checks passed.
External contract compatibility passed against exact PR base
`7f4384b89ff9f91c1c69f0f39377d71ccd574f4c`. The generated TypeScript client/type checks
and five TypeScript unit tests passed; live HTTP conformance passed 342 assertions
on Contract 40.0.0. The installed wheel validated 27 schemas, 2,984 runtime resources
and every published request family under the final runtime manifest.

The final code-quality suite passed **684 tests** in 108.30 seconds. All required
local gates passed. The independent reviewer issued final **APPROVED**, with no
outstanding findings, after verifying both successful JUnit reports and all 24
refreshed performance report hashes against the final runtime. Approval preceded
the first push.

Earlier unsuccessful gates are not passing evidence. They exposed a malformed
profile payload boundary, stale contract/test expectations, and collection errors
caused by overlapping generation with collection. Those were repaired before the
clean run. The first quality run also required refreshing inherited runtime-pinned
performance reports and exposed two fixed-profile work-count regressions. Shared
source-descriptor guards now avoid unused Movement, OC and Range work; the existing
limits were preserved. All 45 focused regressions passed, the independent reviewer
approved the guards, and all 44 previously failing behavioral/quality cases passed
against the final formatted runtime before aggregate validation resumed.

Twenty-four inherited head reports were remeasured serially for the final runtime,
with historical baselines and numeric budgets retained. Exact AST checks prove
that the two fixture-only changes do not alter their measured workloads. The
reviewer approved this evidence treatment. The failed attempt to run current
fixtures against a historical engine is explicitly retained in the
[refresh record](performance/order87/inherited-refresh.json). See
[performance evidence](performance/order87/README.md) for sample counts, matched
conditions, current results, and unmeasured full-game/random-profile limitations.


## R87-001 — gathered defensive-profile restoration

The violated invariant was that a state produced by a legal engine decision must
pass persistence validation. The initial restore validator bounded a random
Toughness occurrence by the primary physical weapon's attack count, although the
live executor numbers every contribution in its selected gathered group through
that primary pool. A facade regression reproduced the reported two-weapon,
four-attack restoration failure before the repair.

The owning authority is the recorded finite weapon-group selection plus its
accepted declaration (and subsequent retargeting inventory). Restore now matches
the prior selection event to its DecisionRecord, authenticates the selected
contributions and signature with the live engine's group validators, and checks
the occurrence's primary index, target, and combined count. Merely offered groups,
secondary contribution indices, and attacks from another group aimed at the same
target cannot extend that authority. Retired and forgone pool indices remain
excluded after retargeting.

The bug-class audit includes Save and invulnerable Save occurrences, which share
this defensive boundary, and random weapon Skill/Strength/AP. The latter retain
physical-weapon isolation in the identical-attack signature, so their existing
physical-pool bound remains appropriate. No live resolution procedure, source
rule, player decision, or adapter payload shape changes; the existing Contract 40
covers the correction. Generated examples change only with the runtime identity.
A static quality audit protects the shared defensive/group validation boundary.

The new tests drive real two-weapon declarations through LocalGameSession, prove
that the group contains both contributions, retain Toughness evaluations for
attacks three/four across JSON persistence, and complete the restored attack with
no additional profile dice. A third incompatible weapon verifies that another
offered group cannot expand the selected group's bound. Save and Toughness,
missing selection authority, substituted pool/target, and forged persisted attack
indices are covered. The change stays within Order 87's authorized restore and
random-characteristic scope; it adds no adjacent gameplay behavior.

Final post-review aggregate validation and matched performance evidence are
recorded in `docs/performance/order87/validation.json` after the final gates.


### R87-001 final validation — September 26, 2026

Runtime `d687c193f560a9c1cdbbc32ab3566440a5994c5c7ec6515ded0b7448b7a8310f`
passed all **9,418 behavioral tests with 85.16% coverage** in 756.25 seconds
(18 work-stealing workers; ten non-failing SQLite ResourceWarnings), followed by
**685 code-quality tests** in 117.67 seconds without coverage. No production
changes followed either run. The complete successful behavioral JUnit report
supplies the regenerated eight-shard inventory; the exact inventory check passed.

Ruff check/format, mypy (3,279 files), Pyright, all eleven import contracts,
pre-commit, source/runtime generation checks, exact-base contract compatibility,
TypeScript generation/type checks and five unit tests, all 342 HTTP conformance
assertions, and installed-wheel smoke (27 schemas, 2,985 runtime resources) passed.
All 24 inherited performance reports were refreshed under unchanged budgets;
the matched restore diagnostic preserves checkpoint and dice identity on both
revisions. Current results, JUnit hashes and prior-publication evidence are
retained under `docs/performance/order87/`.

Independent code, artifact/performance, and final evidence review all approved
R87-001 with no outstanding findings before the PR update was pushed.
