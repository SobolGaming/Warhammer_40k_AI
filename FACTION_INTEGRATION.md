# Faction Integration Plan

This document defines the Phase 17 faction-content rollout. CORE V2 remains an
11th Edition-only engine. Prior-edition Wahapedia data is bridge source
material: it is normalized, patched by official 11th Edition transition
instructions, and then compiled into 11th Edition catalog records.

## Table of Contents

- [Integration Contract](#integration-contract)
- [Phase 17E Scope Boundary](#phase-17e-scope-boundary)
- [Phase 17E Completion Gate](#phase-17e-completion-gate)
- [Phase 17F Execution Gate](#phase-17f-execution-gate)
- [Phase 17G Runtime Scaffold Gate](#phase-17g-runtime-scaffold-gate)
- [Phase 17G Semantic Execution Gate](#phase-17g-semantic-execution-gate)
- [Phase 17H Datasheet, Wargear, and Weapon Execution Gate](#phase-17h-datasheet-wargear-and-weapon-execution-gate)
- [Phase 17I Coverage and Unsupported Audit Gate](#phase-17i-coverage-and-unsupported-audit-gate)
- [Phase 17I Blocked Row Classification Report](#phase-17i-blocked-row-classification-report)
- [Phase 17I Named Handler Budget](#phase-17i-named-handler-budget)
- [WS14 IR-First Content-Drop Runbook](#ws14-ir-first-content-drop-runbook)
- [Faction Execution Status Matrix](#faction-execution-status-matrix)
  - [Death Guard Execution Status](#death-guard-execution-status)
  - [Orks Execution Status](#orks-execution-status)
  - [Aeldari Execution Status](#aeldari-execution-status)
  - [Drukhari Execution Status](#drukhari-execution-status)
  - [Tyranids Execution Status](#tyranids-execution-status)
  - [Genestealer Cults Execution Status](#genestealer-cults-execution-status)
  - [Necrons Execution Status](#necrons-execution-status)
  - [Leagues of Votann Execution Status](#leagues-of-votann-execution-status)
  - [T'au Empire Execution Status](#tau-empire-execution-status)
  - [Space Marines Execution Status](#space-marines-execution-status)
  - [Dark Angels Execution Status](#dark-angels-execution-status)
  - [Blood Angels Execution Status](#blood-angels-execution-status)
  - [Space Wolves Execution Status](#space-wolves-execution-status)
  - [Black Templars Execution Status](#black-templars-execution-status)
  - [Deathwatch Execution Status](#deathwatch-execution-status)
  - [Grey Knights Execution Status](#grey-knights-execution-status)
  - [Chaos Space Marines Execution Status](#chaos-space-marines-execution-status)
  - [World Eaters Execution Status](#world-eaters-execution-status)
  - [Emperor's Children Execution Status](#emperors-children-execution-status)
  - [Thousand Sons Execution Status](#thousand-sons-execution-status)
  - [Chaos Knights Execution Status](#chaos-knights-execution-status)
  - [Chaos Daemons Execution Status](#chaos-daemons-execution-status)
  - [Adepta Sororitas Execution Status](#adepta-sororitas-execution-status)
  - [Adeptus Custodes Execution Status](#adeptus-custodes-execution-status)
  - [Adeptus Mechanicus Execution Status](#adeptus-mechanicus-execution-status)
  - [Astra Militarum Execution Status](#astra-militarum-execution-status)
  - [Imperial Agents Execution Status](#imperial-agents-execution-status)
  - [Imperial Knights Execution Status](#imperial-knights-execution-status)
- [Queue Source](#queue-source)
- [Faction Phase Shape](#faction-phase-shape)
- [Agent Implementation Contract](#agent-implementation-contract)
- [Pilot Phase: Death Guard](#pilot-phase-death-guard)
- [FAQ Classification Gate](#faq-classification-gate)
- [Faction Phase Queue](#faction-phase-queue)
- [Per-Subphase Completion Gate](#per-subphase-completion-gate)
- [Deferral Rules](#deferral-rules)

## Integration Contract

- Do not import a prior-edition catalog into runtime engine code.
- Keep the raw Wahapedia mirror immutable and source-linked.
- Represent every official 11th Edition transition instruction as an ordered
  patch operation.
- Emit explicit unsupported diagnostics for rule text, targets, or source rows
  that cannot be represented safely.
- Runtime descriptors consume structured catalog data, never raw rule text or
  HTML.
- Faction PRs must keep the same UI, headless, network, replay, and test decision
  path.
- Do not mark a faction phase complete while unapproved unsupported descriptors
  remain for matched-play content in that phase.

## Phase 17E Scope Boundary

Phase 17E is complete only when faction-level matched-play content is covered
for every faction in the current source package:

- every faction has a source-linked army rule descriptor;
- every detachment has a source-linked detachment rule descriptor;
- every detachment enhancement and detachment Stratagem has source-linked
  descriptors, target/timing/eligibility metadata, generic IR where possible, or
  approved unsupported diagnostics;
- the coverage report groups implemented, generic-supported,
  named-handler-required, and unsupported faction, detachment, enhancement, and
  Stratagem rules;
- tests prove every faction and detachment row loads from source-backed catalog
  records.

Phase 17E must also intake unit rows far enough to make faction and detachment
coverage reviewable: datasheet identity, composition, wargear-option, base-size,
geometry, representative-height, keyword, and faction-keyword rows must be
source-linked or explicitly blocked by diagnostics. Broad datasheet, wargear,
and weapon ability execution belongs to Phase 17H unless a unit rule is
inseparable from a Phase 17E army rule, detachment rule, enhancement, or
Stratagem that lands in Phase 17G semantic execution.

Do not hand-author an exhaustive unit-name list in this Markdown file. Unit
subphases must be expanded from generated source coverage reports so names,
source IDs, geometry blockers, and unsupported descriptors stay synchronized
with the patched source mirror.

## Phase 17E Completion Gate

Phase 17E is complete as source-backed coverage, not broad execution. The
coverage package is:

- package ID: `gw-11e-phase17e-faction-coverage-2026-27`
- path:
  `src/warhammer40k_core/rules/source_packages/warhammer_40000_11th/faction_coverage_2026_27.py`
- source title: `Warhammer 40,000 11th Edition Phase 17E Faction Coverage`
- source version: `2026-27`
- source date: `2026-06-11`
- upstream identity:
  `official-11th-edition-faction-packs-and-detachment-source-package`
- source edition: `11th`
- schema version: `core-v2-phase17e-faction-coverage-v2`
- source-payload SHA-256 checksum:
  `fb58c11e12dfd3379a9cb12a69db9f3169fd5c9e26917f224d58f8123ae15f55`

The package validates all 28 faction-pack PDF manifest records and emits
coverage rows for every seeded faction and detachment. Faction army rules and
detachment rules are source-linked named-handler rows: source-only rows remain
named-handler-required, while rows with existing runtime consumers are marked
implemented. Datasheet intake is fail-closed as an approved unsupported
diagnostic. Exact Enhancement and Stratagem rows are generated from the exact
subrule source package and include stable rule IDs, owner faction/detachment IDs,
timing/category metadata, source IDs, and support status. Source-only exact rows
outside generic IR are named-handler-required; 19 exact Enhancement rows in
the conditional weapon-ability grant, grant-ability, characteristic-modification,
movement-distance, and dice-roll modification template families are generic-supported with
checksum-covered RuleIR hashes. The More Dakka detachment rule and six More
Dakka Stratagem rows are also generic-supported through source-boundary static
RuleIR payloads. The Spectacle of Slaughter detachment rule, two Enhancements,
and three Stratagem rows are generic-supported the same way, for a total of 31
generic-supported rows; exact rows with existing runtime consumers are marked
implemented. No aggregate faction-pack Enhancement or Stratagem row is used to
hide missing detail, and no unapproved unsupported descriptor remains for Phase
17E matched-play coverage.
The exact subrule source package also exposes checksum-covered
`skipped_bridge_rows()` and `runtime_only_rows()` audit APIs. Current bridge
input accounting captures 601 approved skipped bridge rows: 573 rows whose
derived owner is not in the current source package and 28 Stratagem rows with
missing bridge owner fields. Runtime-only exact rows are limited to an explicit
11-row allowlist for existing named handlers without a bridge source-row match;
new runtime-only rows fail generation until their provenance is approved.

## Phase 17F Execution Gate

Phase 17F is complete as deterministic execution dispatch and status for every
Phase 17E coverage row. The execution package is:

- package ID: `gw-11e-phase17f-faction-execution-2026-27`
- path:
  `src/warhammer40k_core/rules/source_packages/warhammer_40000_11th/faction_execution_2026_27.py`
- engine path:
  `src/warhammer40k_core/engine/faction_rule_execution.py`
- source title: `Warhammer 40,000 11th Edition Phase 17F Faction Execution`
- source version: `2026-27`
- source date: `2026-06-11`
- upstream identity: `gw-11e-phase17e-faction-coverage-2026-27`
- source edition: `11th`
- schema version: `core-v2-phase17f-faction-execution-v2`
- source-payload SHA-256 checksum:
  `6b1154d6e9db45f493e7737189f83b5793c782b241e3762edba9af86437e27f4`
- upstream Phase 17E checksum:
  `fb58c11e12dfd3379a9cb12a69db9f3169fd5c9e26917f224d58f8123ae15f55`

The package emits 2145 execution records, one for every Phase 17E coverage row:
2035 rows are blocked as `structured_rule_semantics_required`, 28 rows are
blocked as `approved_phase17e_source_gap`, 31 rows are executable generic IR
rows, and 51 rows are executable
named-handler rows because they already have runtime consumers: 23 faction army
rules plus 28 exact detachment, Enhancement, and Stratagem rows.
The engine dispatcher can route every record and returns typed `unsupported`
diagnostics unless a matching executor is registered. No Phase 17E row remains a
missing handler, runtime no-op, raw-PDF parse, or silent fallback. Future
executable rows require a registered generic IR executor or named handler;
unregistered executable statuses return typed `unsupported` diagnostics and
cannot emit `applied` by status alone.
Phase 17F is an execution dispatch gate, not semantic execution. It proves that
every Phase 17E coverage row has a deterministic fail-closed engine route. It
does not implement the game effects of army rules, detachment rules,
enhancements, or Stratagems.
Generic IR execution loads checksum-covered static RuleIR payloads from the
source package and verifies the Phase 17F `rule_ir_hash`; runtime dispatch does
not compile raw source prose or read raw source snapshot JSON.

## Phase 17G Runtime Scaffold Gate

Before faction semantic implementation PRs begin, Phase 17G must provide
generated, source-backed runtime scaffold modules for every faction and
detachment in the current 11th Edition faction-detachment package. The scaffold
package is:

- generator path: `tools/generate_faction_content_scaffold.py`
- generated root:
  `src/warhammer40k_core/engine/faction_content/warhammer_40000_11th/`
- generated manifest path:
  `src/warhammer40k_core/engine/faction_content/warhammer_40000_11th/generated_manifest.py`
- source package:
  `src/warhammer40k_core/rules/source_packages/warhammer_40000_11th/faction_detachments_2026_27.py`
- execution package:
  `src/warhammer40k_core/rules/source_packages/warhammer_40000_11th/faction_execution_2026_27.py`

The generator creates this shape for every source-backed faction and
detachment:

```text
<faction_slug>/
  __init__.py
  manifest.py
  army_rule.py
  detachments/
    __init__.py
    <detachment_slug>/
      __init__.py
      manifest.py
      rule.py
      enhancements.py
      stratagems.py
```

The generator owns `generated_manifest.py`, package `__init__.py` files, and
faction/detachment `manifest.py` aggregators byte-for-byte. The agent-owned
semantic target files are `army_rule.py`, `rule.py`, `enhancements.py`, and
`stratagems.py`. Those target files start as load-safe, semantically inert
placeholders with the marker `Generated scaffold placeholder. Remove this marker
when implementing semantics.` Implementation PRs remove that marker and keep the
required `CONTRIBUTION_ID` plus `runtime_contribution()` export shape.

Generated faction `manifest.py` files aggregate the sibling `army_rule.py`
contribution. Generated detachment `manifest.py` files aggregate sibling
`rule.py`, `enhancements.py`, and `stratagems.py` contributions through
`combine_runtime_content_contributions(...)`. Runtime manifest rows point to the
generated `manifest.py` aggregators, so ordinary implementation PRs do not edit
manifest machinery. This is deliberate: `supported` in the runtime manifest
means a selected content row has an importable runtime module path. It does not
mean the faction, detachment, enhancement, or Stratagem semantics have gameplay
support.

The scaffold gate must not generate broad datasheet, wargear, or weapon-profile
files. Those modules are generated only for assigned Phase 17H vertical slices.
Existing pilot Death Guard unit and wargear modules remain as explicit pilot
content, not a template for all datasheets.

Required tests:

- every generated faction has package roots, `manifest.py`, and `army_rule.py`;
- every generated detachment has `manifest.py`, `rule.py`, `enhancements.py`,
  and `stratagems.py`;
- generated scaffold modules export `runtime_contribution()`;
- placeholder scaffold contributions are empty and use stable IDs;
- generated manifest aggregators include agent-owned sibling contributions;
- generated manifest faction and detachment module paths match scaffold files;
- runtime faction-content modules do not import raw source mirrors, parser
  tooling, compiler tooling, or HTML sanitizer tooling;
- CI fails when generator-owned files are stale;
- CI fails when agent-owned files are missing required exports;
- CI fails when an orphaned generated placeholder remains after source rows
  change.

## Phase 17G Semantic Execution Gate

Phase 17G is the first faction-content phase that implements actual engine
support for the Phase 17E faction-level items:

- army rules;
- detachment rules;
- enhancement effects;
- faction and detachment Stratagem timing, targeting, validation, and effects.

Phase 17G must replace `blocked_structured_semantics_required` rows for
faction-level content with registered generic IR executors, source-linked named
handlers, source-linked Battle-shock hook bindings for rules whose timing is
Battle-shock modifier or outcome resolution, or source-linked Fall Back
eligibility hook bindings for rules whose effect is that a completed Fall Back
move does not prevent later Shooting or Charge eligibility, or source-linked
Movement-end surge hook bindings for opponent Movement phase rules that trigger
after an enemy unit ends a move, or source-linked phase-end objective-control
hook bindings for rules that retain or adjust objective control at a phase-end
boundary, or source-linked enhancement effect bindings for selected Enhancement
or Upgrade assignments that materialize static engine-owned characteristic
modifiers, or source-linked Fight activation ability hook bindings for optional
selected-to-fight rules whose effect is a scoped melee targeting permission, or
source-linked Stratagem handler bindings for faction or detachment Stratagems
whose timing is already represented by an engine timing window. These execution
surfaces must mutate authoritative game state only through engine-owned
services, use the shared `DecisionRequest` / `DecisionResult` path for player
choices, and emit deterministic replay-safe execution results.
Implementation PRs must use the generated scaffold targets and the
[Faction Agent Implementation Contract](docs/FACTION_AGENT_IMPLEMENTATION_CONTRACT.md).

Battle-shock hook bindings map to Phase 17F through their `source_id`: the
binding must use the generated execution row ID for the rule it implements, and
the runtime manifest row selected from the mustered faction or detachment must
carry that same execution row into the `RuntimeContentBundle` audit summary.
The Phase 17F baseline execution matrix remains historical source status until
a later execution-status overlay consolidates implemented hook coverage; Phase
17G hook PRs must therefore add source-link and lifecycle tests that prove the
hook is loaded and executed through the selected runtime bundle.

Fall Back eligibility hook bindings follow the same Phase 17F mapping rule. The
binding `source_id` must be the generated execution row ID for the implemented
rule, and the selected runtime manifest must carry that ID into the
`RuntimeContentBundle` audit summary. Hook handlers return typed permission
grants only; the Movement engine records `FellBackUnitState` and emits
replay-safe grant payloads, while Shooting and Charge eligibility consume the
recorded engine state.

Movement-end surge hook bindings follow the same Phase 17F mapping rule. The
binding `source_id` must be the generated execution row ID for the implemented
rule, and the selected runtime manifest must carry that ID into the
`RuntimeContentBundle` audit summary. Hook handlers return typed eligible-unit
grants only; the Movement engine owns surge-distance dice, triggered-movement
unit selection, the `surge_move` movement proposal request, PathWitness
validation, battlefield mutation, and replay-safe movement records.

Phase-end objective-control hook bindings follow the same Phase 17F mapping
rule. The binding `source_id` must be the generated execution row ID for the
implemented rule, and the selected runtime manifest must carry that ID into the
`RuntimeContentBundle` audit summary. Hook handlers return typed
objective-control state records only; `GameState` owns retained-control overlays,
expiry checks, and phase-boundary objective-control records.

Enhancement effect bindings map to Phase 17F through the generated exact
Enhancement execution row. The binding `source_id` must be that generated row
ID, the
selected runtime manifest must expose the binding ID in the
`RuntimeContentBundle` audit summary, and the lifecycle-owned enhancement effect
service must apply the static modifier idempotently from Phase 16D
`EnhancementAssignment` records. Eligibility must be validated from structured
catalog target requirements and the selected army-construction records, not from
runtime rule-text parsing.

Fight activation ability hook bindings follow the same Phase 17F mapping rule.
The binding `source_id` must be the generated execution row ID for the
implemented rule or exact Enhancement row. The selected runtime manifest must expose the hook ID
in the `RuntimeContentBundle` audit summary. Hook handlers return typed ability
options only; the Fight engine emits the finite use/decline request, records the
engine-owned persisting melee targeting permission, and lowers accepted melee
declarations into source-linked attack pools through the shared Fight path.

Stratagem records and Stratagem handler bindings follow the same Phase 17F
mapping rule. Detachment Stratagem records must enter a player's runtime
Stratagem index only when that detachment is selected and materialized by the
runtime content bundle. Selected-to-move Movement Stratagems use trigger kind
`just_after_friendly_unit_selected_to_move` and emit a finite optional
`use_stratagem` request after `select_movement_unit` and before
`select_movement_action`. Handlers must validate timing, target ownership,
required keywords, CP cost, and repeat-use restrictions through the shared
Stratagem path; any temporary movement keywords must be stored as engine-owned
persisting effects and consumed by Movement proposal validation.

Phase 17G does not cover broad datasheet, wargear, or weapon ability execution.
Those rows move to Phase 17H unless they are inseparable from a faction army
rule, detachment rule, enhancement, or Stratagem implemented in Phase 17G.

Required tests:

- faction army rules load and execute for every faction through the registered
  engine path, including Battle-shock hooks when the rule timing is
  Battle-shock resolution;
- detachment rules load and execute for every detachment through registered
  lifecycle hooks, including Fall Back eligibility hooks when the rule modifies
  Shooting or Charge consequences of a completed Fall Back move, Movement-end
  surge hooks when the rule grants triggered movement after an enemy move ends,
  and phase-end objective-control hooks when the rule retains or adjusts
  objective control;
- enhancements validate eligibility from Phase 16D army-construction records
  and execute their effects through generic IR, named handlers, or enhancement
  effect bindings for static characteristic modifiers, including Fight
  activation ability hooks for optional selected-to-fight enhancement effects;
- faction and detachment Stratagems validate timing, targeting, CP ledgers,
  repeat-use constraints, and effects through the shared Stratagem path;
- selected-to-move Stratagem lifecycle tests prove the record is registered
  only for the materialized detachment and that the window runs before Movement
  action selection;
- registered executors and hook bindings cannot return or expose mismatched
  execution identity payloads;
- unsupported semantic behavior returns typed unsupported diagnostics with
  approved source-linked reasons.

## Phase 17H Datasheet, Wargear, and Weapon Execution Gate

Phase 17H is the broad unit-content execution phase. It expands generated
source rows and implements execution for covered datasheet abilities, selected
wargear abilities, weapon abilities, and source-coupled unit rules that are not
part of Phase 17G faction-level semantics.

Required tests:

- datasheet, wargear, and weapon ability rows are generated from source-backed
  descriptors, not hand-authored Markdown lists;
- wargear abilities apply only when that wargear is selected in the army list;
- selected wargear payload drift is rejected before runtime effects apply;
- covered datasheet, wargear, and weapon ability items execute through generic
  IR or source-linked named handlers where supported;
- unsupported covered items return typed unsupported execution results with
  approved reasons.

## Phase 17I Coverage and Unsupported Audit Gate

Phase 17I is the source-content coverage and unsupported-descriptor audit phase.
It consolidates coverage and execution-status reporting after Phase 17G and
Phase 17H have implemented their semantic execution slices.

Required outputs:

- coverage report for datasheets, abilities, wargear, detachments,
  enhancements, Stratagems, and army rules;
- execution-status report for every covered item, grouped by applied,
  generic-supported, named-handler-supported, invalid, and unsupported status;
- unsupported descriptors grouped by reason;
- static audit proving runtime code does not parse raw source text;
- package hashes and coverage totals suitable for CI artifacts.

## Phase 17I Blocked Row Classification Report

WS14 step 1 is implemented as a deterministic Phase 17I source package artifact:

- package ID: `gw-11e-phase17i-blocked-row-classification-2026-27`
- path:
  `src/warhammer40k_core/rules/source_packages/warhammer_40000_11th/faction_blocked_row_classification_2026_27.py`
- source title:
  `Warhammer 40,000 11th Edition Phase 17I Blocked Row Classification`
- source version: `2026-27`
- source date: `2026-07-02`
- upstream identity: `gw-11e-phase17f-faction-execution-2026-27`
- source edition: `11th`
- schema version: `core-v2-phase17i-blocked-row-classification-v1`
- source-payload SHA-256 checksum:
  `251ed10bddd77ece10c100f5a02d419455b3ec485f2beba5d8f08d2eb4085e2f`
- upstream Phase 17F checksum:
  `6b1154d6e9db45f493e7737189f83b5793c782b241e3762edba9af86437e27f4`
- bridge source version: `10th-edition-2026-06-14`
- bridge JSON source:
  `data/source_snapshots/wahapedia/10th-edition/2026-06-14/json`

The report emits 2035 classification rows, one for every Phase 17F row blocked
as `blocked_structured_semantics_required`. It compiles 1944 rows from Wahapedia
bridge descriptions through Phase 17C and marks 91 rows as
`source_text_not_available` metadata-only rows. Each row records the existing
Phase 17C template IDs and template families that can already express clauses,
unsupported diagnostic reason tokens, and missing capability families grouped by
frequency. The current missing-capability summary starts with
`generic_ir_execution_binding`, `unrepresented_rule_language`,
`stratagem_activation_and_targeting`, `stratagem_effect_execution`, and
`enhancement_assignment_effect`.
Stratagem-cost aura rows remain blocked under
`stratagem_cost_modifier_runtime`; they must not be promoted as generic Aura
rows until RuleIR and the runtime content bundle can express the CP-cost
modifier effect.

The payload does not emit raw rule text. It emits source IDs, template IDs,
template family tokens, diagnostic reason tokens, and capability family tokens
only, so runtime engine code remains forbidden from consuming source text or
re-parsing rule prose.

## Phase 17I Named Handler Budget

WS14 step 3 is enforced as a deterministic Phase 17I source package artifact:

- package ID: `gw-11e-phase17i-named-handler-budget-2026-27`
- path:
  `src/warhammer40k_core/rules/source_packages/warhammer_40000_11th/faction_named_handler_budget_2026_27.py`
- source title:
  `Warhammer 40,000 11th Edition Phase 17I Named Handler Budget`
- source version: `2026-27`
- source date: `2026-07-03`
- upstream identity: `gw-11e-phase17f-faction-execution-2026-27`
- source edition: `11th`
- schema version: `core-v2-phase17i-named-handler-budget-v1`
- source-payload SHA-256 checksum:
  `81ed702fc2b7a7e71df7457a088506ffd1db994e69c20cc9c087a5a1ef7b4167`
- upstream Phase 17F checksum:
  `6b1154d6e9db45f493e7737189f83b5793c782b241e3762edba9af86437e27f4`

The budget report tracks 51 executable named-handler Phase 17F rows and 51
approved entries. The current approved reason is
`pre_ws14_existing_runtime_consumer`, which is a fixed baseline for handlers
that existed before the WS14 IR-first pivot. The code-quality audit fails if a
new named handler appears without an approved entry, or if a row migrates away
from named-handler execution and leaves a stale approval behind.

## WS14 IR-First Content-Drop Runbook

Steady-state content drops follow the IR-first loop:

1. Ingest the new official PDF, dataslate, MFM, FAQ, or codex source package.
2. Apply source-linked patch operations and regenerate the normalized package.
3. Recompile RuleIR at the source boundary and refresh Phase 17E coverage.
4. Diff the Phase 17F execution report and Phase 17I classification report.
5. Flip rows to generic IR only when the compiled template family has a
   registered `RuleExecutionRegistry` executor and focused runtime tests.
6. Implement only the flagged residue: approved named handlers, approved source
   gaps, or new Phase 17C template families.
7. Run the WS15 policy-evaluation gate against the new catalog hashes before
   promotion.

The success target is that a typical monthly dataslate requires zero new Python,
and a typical codex requires only a small approved named-handler residue after
IR recompilation.

## Faction Execution Status Matrix

This matrix is generated from the Phase 17F execution package. It records
execution status, not semantic support. Rows marked `unsupported` are deliberately
blocked until native structured rule semantics land. Exact Enhancement and
Stratagem families can repeat when a faction has both source-only rows and
already engine-consumed named handlers.

### Orks Execution Status

| Covered item family | Rows | Execution status | Engine result | Source block |
|---|---:|---|---|---|
| Army rule | 1 | `executable_named_handler` | `applied` | `none` |
| Detachment rules | 11 | `blocked_structured_semantics_required` | `unsupported` | `structured_rule_semantics_required` |
| Detachment rules | 1 | `executable_generic_ir` | `applied` | `none` |
| Enhancements | 39 | `blocked_structured_semantics_required` | `unsupported` | `structured_rule_semantics_required` |
| Enhancements | 5 | `executable_generic_ir` | `applied` | `none` |
| Stratagems | 60 | `blocked_structured_semantics_required` | `unsupported` | `structured_rule_semantics_required` |
| Stratagems | 6 | `executable_generic_ir` | `applied` | `none` |
| Datasheet intake | 1 | `blocked_approved_unsupported_source_gap` | `unsupported` | `approved_phase17e_source_gap:datasheet_intake_requires_generated_source_rows` |

### Aeldari Execution Status

| Covered item family | Rows | Execution status | Engine result | Source block |
|---|---:|---|---|---|
| Army rule | 1 | `executable_named_handler` | `applied` | `none` |
| Detachment rules | 15 | `blocked_structured_semantics_required` | `unsupported` | `structured_rule_semantics_required` |
| Enhancements | 45 | `blocked_structured_semantics_required` | `unsupported` | `structured_rule_semantics_required` |
| Enhancements | 6 | `executable_named_handler` | `applied` | `none` |
| Stratagems | 66 | `blocked_structured_semantics_required` | `unsupported` | `structured_rule_semantics_required` |
| Stratagems | 9 | `executable_named_handler` | `applied` | `none` |
| Datasheet intake | 1 | `blocked_approved_unsupported_source_gap` | `unsupported` | `approved_phase17e_source_gap:datasheet_intake_requires_generated_source_rows` |

### Drukhari Execution Status

| Covered item family | Rows | Execution status | Engine result | Source block |
|---|---:|---|---|---|
| Army rule | 1 | `executable_named_handler` | `applied` | `none` |
| Detachment rules | 9 | `blocked_structured_semantics_required` | `unsupported` | `structured_rule_semantics_required` |
| Enhancements | 24 | `blocked_structured_semantics_required` | `unsupported` | `structured_rule_semantics_required` |
| Stratagems | 36 | `blocked_structured_semantics_required` | `unsupported` | `structured_rule_semantics_required` |
| Datasheet intake | 1 | `blocked_approved_unsupported_source_gap` | `unsupported` | `approved_phase17e_source_gap:datasheet_intake_requires_generated_source_rows` |

### Tyranids Execution Status

| Covered item family | Rows | Execution status | Engine result | Source block |
|---|---:|---|---|---|
| Army rule | 1 | `executable_named_handler` | `applied` | `none` |
| Detachment rules | 10 | `blocked_structured_semantics_required` | `unsupported` | `structured_rule_semantics_required` |
| Enhancements | 31 | `blocked_structured_semantics_required` | `unsupported` | `structured_rule_semantics_required` |
| Enhancements | 1 | `executable_generic_ir` | `applied` | `none` |
| Stratagems | 48 | `blocked_structured_semantics_required` | `unsupported` | `structured_rule_semantics_required` |
| Datasheet intake | 1 | `blocked_approved_unsupported_source_gap` | `unsupported` | `approved_phase17e_source_gap:datasheet_intake_requires_generated_source_rows` |

### Genestealer Cults Execution Status

| Covered item family | Rows | Execution status | Engine result | Source block |
|---|---:|---|---|---|
| Army rule | 1 | `executable_named_handler` | `applied` | `none` |
| Detachment rules | 9 | `blocked_structured_semantics_required` | `unsupported` | `structured_rule_semantics_required` |
| Enhancements | 18 | `blocked_structured_semantics_required` | `unsupported` | `structured_rule_semantics_required` |
| Enhancements | 2 | `executable_generic_ir` | `applied` | `none` |
| Stratagems | 30 | `blocked_structured_semantics_required` | `unsupported` | `structured_rule_semantics_required` |
| Datasheet intake | 1 | `blocked_approved_unsupported_source_gap` | `unsupported` | `approved_phase17e_source_gap:datasheet_intake_requires_generated_source_rows` |

### Necrons Execution Status

| Covered item family | Rows | Execution status | Engine result | Source block |
|---|---:|---|---|---|
| Army rule | 1 | `executable_named_handler` | `applied` | `none` |
| Detachment rules | 12 | `blocked_structured_semantics_required` | `unsupported` | `structured_rule_semantics_required` |
| Enhancements | 33 | `blocked_structured_semantics_required` | `unsupported` | `structured_rule_semantics_required` |
| Enhancements | 3 | `executable_generic_ir` | `applied` | `none` |
| Stratagems | 54 | `blocked_structured_semantics_required` | `unsupported` | `structured_rule_semantics_required` |
| Datasheet intake | 1 | `blocked_approved_unsupported_source_gap` | `unsupported` | `approved_phase17e_source_gap:datasheet_intake_requires_generated_source_rows` |

### Leagues of Votann Execution Status

| Covered item family | Rows | Execution status | Engine result | Source block |
|---|---:|---|---|---|
| Army rule | 1 | `executable_named_handler` | `applied` | `none` |
| Detachment rules | 10 | `blocked_structured_semantics_required` | `unsupported` | `structured_rule_semantics_required` |
| Enhancements | 27 | `blocked_structured_semantics_required` | `unsupported` | `structured_rule_semantics_required` |
| Enhancements | 1 | `executable_generic_ir` | `applied` | `none` |
| Stratagems | 42 | `blocked_structured_semantics_required` | `unsupported` | `structured_rule_semantics_required` |
| Datasheet intake | 1 | `blocked_approved_unsupported_source_gap` | `unsupported` | `approved_phase17e_source_gap:datasheet_intake_requires_generated_source_rows` |

### T'au Empire Execution Status

| Covered item family | Rows | Execution status | Engine result | Source block |
|---|---:|---|---|---|
| Army rule | 1 | `executable_named_handler` | `applied` | `none` |
| Detachment rules | 7 | `blocked_structured_semantics_required` | `unsupported` | `structured_rule_semantics_required` |
| Enhancements | 20 | `blocked_structured_semantics_required` | `unsupported` | `structured_rule_semantics_required` |
| Stratagems | 30 | `blocked_structured_semantics_required` | `unsupported` | `structured_rule_semantics_required` |
| Datasheet intake | 1 | `blocked_approved_unsupported_source_gap` | `unsupported` | `approved_phase17e_source_gap:datasheet_intake_requires_generated_source_rows` |

### Space Marines Execution Status

| Covered item family | Rows | Execution status | Engine result | Source block |
|---|---:|---|---|---|
| Army rule | 1 | `executable_named_handler` | `applied` | `none` |
| Detachment rules | 22 | `blocked_structured_semantics_required` | `unsupported` | `structured_rule_semantics_required` |
| Enhancements | 79 | `blocked_structured_semantics_required` | `unsupported` | `structured_rule_semantics_required` |
| Enhancements | 1 | `executable_generic_ir` | `applied` | `none` |
| Stratagems | 119 | `blocked_structured_semantics_required` | `unsupported` | `structured_rule_semantics_required` |
| Datasheet intake | 1 | `blocked_approved_unsupported_source_gap` | `unsupported` | `approved_phase17e_source_gap:datasheet_intake_requires_generated_source_rows` |

### Dark Angels Execution Status

| Covered item family | Rows | Execution status | Engine result | Source block |
|---|---:|---|---|---|
| Army rule | 1 | `blocked_structured_semantics_required` | `unsupported` | `structured_rule_semantics_required` |
| Detachment rules | 8 | `blocked_structured_semantics_required` | `unsupported` | `structured_rule_semantics_required` |
| Datasheet intake | 1 | `blocked_approved_unsupported_source_gap` | `unsupported` | `approved_phase17e_source_gap:datasheet_intake_requires_generated_source_rows` |

### Blood Angels Execution Status

| Covered item family | Rows | Execution status | Engine result | Source block |
|---|---:|---|---|---|
| Army rule | 1 | `blocked_structured_semantics_required` | `unsupported` | `structured_rule_semantics_required` |
| Detachment rules | 8 | `blocked_structured_semantics_required` | `unsupported` | `structured_rule_semantics_required` |
| Datasheet intake | 1 | `blocked_approved_unsupported_source_gap` | `unsupported` | `approved_phase17e_source_gap:datasheet_intake_requires_generated_source_rows` |

### Space Wolves Execution Status

| Covered item family | Rows | Execution status | Engine result | Source block |
|---|---:|---|---|---|
| Army rule | 1 | `blocked_structured_semantics_required` | `unsupported` | `structured_rule_semantics_required` |
| Detachment rules | 7 | `blocked_structured_semantics_required` | `unsupported` | `structured_rule_semantics_required` |
| Datasheet intake | 1 | `blocked_approved_unsupported_source_gap` | `unsupported` | `approved_phase17e_source_gap:datasheet_intake_requires_generated_source_rows` |

### Black Templars Execution Status

| Covered item family | Rows | Execution status | Engine result | Source block |
|---|---:|---|---|---|
| Army rule | 1 | `executable_named_handler` | `applied` | `none` |
| Detachment rules | 6 | `blocked_structured_semantics_required` | `unsupported` | `structured_rule_semantics_required` |
| Datasheet intake | 1 | `blocked_approved_unsupported_source_gap` | `unsupported` | `approved_phase17e_source_gap:datasheet_intake_requires_generated_source_rows` |

### Deathwatch Execution Status

| Covered item family | Rows | Execution status | Engine result | Source block |
|---|---:|---|---|---|
| Army rule | 1 | `blocked_structured_semantics_required` | `unsupported` | `structured_rule_semantics_required` |
| Detachment rules | 1 | `blocked_structured_semantics_required` | `unsupported` | `structured_rule_semantics_required` |
| Datasheet intake | 1 | `blocked_approved_unsupported_source_gap` | `unsupported` | `approved_phase17e_source_gap:datasheet_intake_requires_generated_source_rows` |

### Grey Knights Execution Status

| Covered item family | Rows | Execution status | Engine result | Source block |
|---|---:|---|---|---|
| Army rule | 1 | `executable_named_handler` | `applied` | `none` |
| Detachment rules | 9 | `blocked_structured_semantics_required` | `unsupported` | `structured_rule_semantics_required` |
| Enhancements | 24 | `blocked_structured_semantics_required` | `unsupported` | `structured_rule_semantics_required` |
| Stratagems | 36 | `blocked_structured_semantics_required` | `unsupported` | `structured_rule_semantics_required` |
| Datasheet intake | 1 | `blocked_approved_unsupported_source_gap` | `unsupported` | `approved_phase17e_source_gap:datasheet_intake_requires_generated_source_rows` |

### Chaos Space Marines Execution Status

| Covered item family | Rows | Execution status | Engine result | Source block |
|---|---:|---|---|---|
| Army rule | 1 | `executable_named_handler` | `applied` | `none` |
| Detachment rules | 17 | `blocked_structured_semantics_required` | `unsupported` | `structured_rule_semantics_required` |
| Enhancements | 58 | `blocked_structured_semantics_required` | `unsupported` | `structured_rule_semantics_required` |
| Enhancements | 2 | `executable_generic_ir` | `applied` | `none` |
| Stratagems | 90 | `blocked_structured_semantics_required` | `unsupported` | `structured_rule_semantics_required` |
| Datasheet intake | 1 | `blocked_approved_unsupported_source_gap` | `unsupported` | `approved_phase17e_source_gap:datasheet_intake_requires_generated_source_rows` |

### World Eaters Execution Status

| Covered item family | Rows | Execution status | Engine result | Source block |
|---|---:|---|---|---|
| Army rule | 1 | `executable_named_handler` | `applied` | `none` |
| Detachment rules | 8 | `blocked_structured_semantics_required` | `unsupported` | `structured_rule_semantics_required` |
| Enhancements | 24 | `blocked_structured_semantics_required` | `unsupported` | `structured_rule_semantics_required` |
| Stratagems | 36 | `blocked_structured_semantics_required` | `unsupported` | `structured_rule_semantics_required` |
| Datasheet intake | 1 | `blocked_approved_unsupported_source_gap` | `unsupported` | `approved_phase17e_source_gap:datasheet_intake_requires_generated_source_rows` |

### Emperor's Children Execution Status

| Covered item family | Rows | Execution status | Engine result | Source block |
|---|---:|---|---|---|
| Army rule | 1 | `executable_named_handler` | `applied` | `none` |
| Detachment rules | 9 | `blocked_structured_semantics_required` | `unsupported` | `structured_rule_semantics_required` |
| Detachment rules | 1 | `executable_generic_ir` | `applied` | `none` |
| Enhancements | 28 | `blocked_structured_semantics_required` | `unsupported` | `structured_rule_semantics_required` |
| Enhancements | 2 | `executable_generic_ir` | `applied` | `none` |
| Stratagems | 42 | `blocked_structured_semantics_required` | `unsupported` | `structured_rule_semantics_required` |
| Stratagems | 3 | `executable_generic_ir` | `applied` | `none` |
| Datasheet intake | 1 | `blocked_approved_unsupported_source_gap` | `unsupported` | `approved_phase17e_source_gap:datasheet_intake_requires_generated_source_rows` |

### Death Guard Execution Status

| Covered item family | Rows | Execution status | Engine result | Source block |
|---|---:|---|---|---|
| Army rule | 1 | `executable_named_handler` | `applied` | `none` |
| Detachment rules | 9 | `blocked_structured_semantics_required` | `unsupported` | `structured_rule_semantics_required` |
| Enhancements | 28 | `blocked_structured_semantics_required` | `unsupported` | `structured_rule_semantics_required` |
| Stratagems | 42 | `blocked_structured_semantics_required` | `unsupported` | `structured_rule_semantics_required` |
| Datasheet intake | 1 | `blocked_approved_unsupported_source_gap` | `unsupported` | `approved_phase17e_source_gap:datasheet_intake_requires_generated_source_rows` |

### Thousand Sons Execution Status

| Covered item family | Rows | Execution status | Engine result | Source block |
|---|---:|---|---|---|
| Army rule | 1 | `executable_named_handler` | `applied` | `none` |
| Detachment rules | 9 | `blocked_structured_semantics_required` | `unsupported` | `structured_rule_semantics_required` |
| Enhancements | 24 | `blocked_structured_semantics_required` | `unsupported` | `structured_rule_semantics_required` |
| Stratagems | 36 | `blocked_structured_semantics_required` | `unsupported` | `structured_rule_semantics_required` |
| Datasheet intake | 1 | `blocked_approved_unsupported_source_gap` | `unsupported` | `approved_phase17e_source_gap:datasheet_intake_requires_generated_source_rows` |

### Chaos Knights Execution Status

| Covered item family | Rows | Execution status | Engine result | Source block |
|---|---:|---|---|---|
| Army rule | 1 | `executable_named_handler` | `applied` | `none` |
| Detachment rules | 8 | `blocked_structured_semantics_required` | `unsupported` | `structured_rule_semantics_required` |
| Enhancements | 26 | `blocked_structured_semantics_required` | `unsupported` | `structured_rule_semantics_required` |
| Stratagems | 36 | `blocked_structured_semantics_required` | `unsupported` | `structured_rule_semantics_required` |
| Datasheet intake | 1 | `blocked_approved_unsupported_source_gap` | `unsupported` | `approved_phase17e_source_gap:datasheet_intake_requires_generated_source_rows` |

### Chaos Daemons Execution Status

| Covered item family | Rows | Execution status | Engine result | Source block |
|---|---:|---|---|---|
| Army rule | 1 | `executable_named_handler` | `applied` | `none` |
| Detachment rules | 5 | `blocked_structured_semantics_required` | `unsupported` | `structured_rule_semantics_required` |
| Detachment rules | 4 | `executable_named_handler` | `applied` | `none` |
| Enhancements | 22 | `blocked_structured_semantics_required` | `unsupported` | `structured_rule_semantics_required` |
| Enhancements | 6 | `executable_named_handler` | `applied` | `none` |
| Stratagems | 40 | `blocked_structured_semantics_required` | `unsupported` | `structured_rule_semantics_required` |
| Stratagems | 3 | `executable_named_handler` | `applied` | `none` |
| Datasheet intake | 1 | `blocked_approved_unsupported_source_gap` | `unsupported` | `approved_phase17e_source_gap:datasheet_intake_requires_generated_source_rows` |

### Astra Militarum Execution Status

| Covered item family | Rows | Execution status | Engine result | Source block |
|---|---:|---|---|---|
| Army rule | 1 | `executable_named_handler` | `applied` | `none` |
| Detachment rules | 11 | `blocked_structured_semantics_required` | `unsupported` | `structured_rule_semantics_required` |
| Enhancements | 36 | `blocked_structured_semantics_required` | `unsupported` | `structured_rule_semantics_required` |
| Stratagems | 54 | `blocked_structured_semantics_required` | `unsupported` | `structured_rule_semantics_required` |
| Datasheet intake | 1 | `blocked_approved_unsupported_source_gap` | `unsupported` | `approved_phase17e_source_gap:datasheet_intake_requires_generated_source_rows` |

### Adepta Sororitas Execution Status

| Covered item family | Rows | Execution status | Engine result | Source block |
|---|---:|---|---|---|
| Army rule | 1 | `executable_named_handler` | `applied` | `none` |
| Detachment rules | 8 | `blocked_structured_semantics_required` | `unsupported` | `structured_rule_semantics_required` |
| Enhancements | 20 | `blocked_structured_semantics_required` | `unsupported` | `structured_rule_semantics_required` |
| Stratagems | 30 | `blocked_structured_semantics_required` | `unsupported` | `structured_rule_semantics_required` |
| Datasheet intake | 1 | `blocked_approved_unsupported_source_gap` | `unsupported` | `approved_phase17e_source_gap:datasheet_intake_requires_generated_source_rows` |

### Adeptus Mechanicus Execution Status

| Covered item family | Rows | Execution status | Engine result | Source block |
|---|---:|---|---|---|
| Army rule | 1 | `executable_named_handler` | `applied` | `none` |
| Detachment rules | 10 | `blocked_structured_semantics_required` | `unsupported` | `structured_rule_semantics_required` |
| Enhancements | 28 | `blocked_structured_semantics_required` | `unsupported` | `structured_rule_semantics_required` |
| Stratagems | 42 | `blocked_structured_semantics_required` | `unsupported` | `structured_rule_semantics_required` |
| Datasheet intake | 1 | `blocked_approved_unsupported_source_gap` | `unsupported` | `approved_phase17e_source_gap:datasheet_intake_requires_generated_source_rows` |

### Imperial Knights Execution Status

| Covered item family | Rows | Execution status | Engine result | Source block |
|---|---:|---|---|---|
| Army rule | 1 | `executable_named_handler` | `applied` | `none` |
| Detachment rules | 8 | `blocked_structured_semantics_required` | `unsupported` | `structured_rule_semantics_required` |
| Enhancements | 23 | `blocked_structured_semantics_required` | `unsupported` | `structured_rule_semantics_required` |
| Enhancements | 1 | `executable_generic_ir` | `applied` | `none` |
| Stratagems | 36 | `blocked_structured_semantics_required` | `unsupported` | `structured_rule_semantics_required` |
| Datasheet intake | 1 | `blocked_approved_unsupported_source_gap` | `unsupported` | `approved_phase17e_source_gap:datasheet_intake_requires_generated_source_rows` |

Runtime note: Phase 17G also implements Imperial Knights Bondsman as a
source-backed Command phase handler under
`phase17g:imperial-knights:bondsman`. It uses structured datasheet ability
descriptors tagged or named `Bondsman`, emits the shared
`select_faction_rule_command_phase_start_option` decision, validates a friendly
ARMIGER model within 12" that is not already affected, and records a
model-scoped persisting effect until the start of that player's next turn.

### Adeptus Custodes Execution Status

| Covered item family | Rows | Execution status | Engine result | Source block |
|---|---:|---|---|---|
| Army rule | 1 | `executable_named_handler` | `applied` | `none` |
| Detachment rules | 9 | `blocked_structured_semantics_required` | `unsupported` | `structured_rule_semantics_required` |
| Enhancements | 22 | `blocked_structured_semantics_required` | `unsupported` | `structured_rule_semantics_required` |
| Enhancements | 2 | `executable_generic_ir` | `applied` | `none` |
| Stratagems | 36 | `blocked_structured_semantics_required` | `unsupported` | `structured_rule_semantics_required` |
| Datasheet intake | 1 | `blocked_approved_unsupported_source_gap` | `unsupported` | `approved_phase17e_source_gap:datasheet_intake_requires_generated_source_rows` |

Runtime note: Phase 17G implements Adeptus Custodes Martial Ka'tah as a
source-backed selected-to-fight grant. Eligible Custodes rules units choose
Dacatarai or Rendax through `select_fight_unit_grant`, record a replay-safe
Fight-phase persisting effect across the rules unit and attached components,
and consume that effect through the shared melee weapon profile modifier path
to grant `SUSTAINED HITS 1` or `LETHAL HITS` until the effect expires.

### Imperial Agents Execution Status

| Covered item family | Rows | Execution status | Engine result | Source block |
|---|---:|---|---|---|
| Army rule | 1 | `blocked_structured_semantics_required` | `unsupported` | `structured_rule_semantics_required` |
| Detachment rules | 5 | `blocked_structured_semantics_required` | `unsupported` | `structured_rule_semantics_required` |
| Enhancements | 20 | `blocked_structured_semantics_required` | `unsupported` | `structured_rule_semantics_required` |
| Stratagems | 30 | `blocked_structured_semantics_required` | `unsupported` | `structured_rule_semantics_required` |
| Datasheet intake | 1 | `blocked_approved_unsupported_source_gap` | `unsupported` | `approved_phase17e_source_gap:datasheet_intake_requires_generated_source_rows` |

## Queue Source

The seeded detachment queue is derived from:

- package ID: `gw-11e-faction-detachments-2026-27`
- path:
  `src/warhammer40k_core/rules/source_packages/warhammer_40000_11th/faction_detachments_2026_27.py`
- source title: `Warhammer 40,000 11th Edition Faction Detachments 2026-27`
- source version: `2026-27`
- source date: `2026-06-11`
- upstream identity: `official-11th-edition-faction-detachment-source-package`
- source edition: `11th`
- schema version: `core-v2-faction-detachment-source-v1`
- source-payload SHA-256 checksum:
  `5e48d00f5d670b60a9ef78902772e6cd6fed95f5f6ab8ad3e27bea4e5bd5ff89`

Queue refreshes must be generated from this package, not hand-edited, except for
explicitly reviewed corrections recorded in the patch package manifest. Until a
dedicated generator lands in Phase 17A, queue verification and checksum
refreshes use the package API:

```bash
uv run python - <<'PY'
from warhammer40k_core.rules.source_packages.warhammer_40000_11th import (
    faction_detachments_2026_27 as source,
)

print(source.source_package_identity_payload())
for row in source.detachment_rows():
    print(f"{row.faction_id}\t{row.name}")
PY
```

Names in this queue preserve the package's normalized source-row spelling exactly,
including any official misspellings. Corrections must be represented as
source-linked patch operations, not silent edits. The current source package
intentionally preserves
`Auxillary Cadre` and `Brood Brothers Auxillia` because those are the exact
source-row names in the seeded package at source IDs
`gw-11e-faction-detachments-2026-27:detachment:tau-empire:auxillary-cadre` and
`gw-11e-faction-detachments-2026-27:detachment:genestealer-cults:brood-brothers-auxillia`.

## Faction Phase Shape

Large phases are faction names. Lettered subphases inside a faction are named
content slices: exact detachment support, exact datasheet support, exact
enhancement/Stratagem support when tied to a detachment, or a tightly coupled
official patch batch such as a named FRAME keyword update.

All faction and detachment runtime package roots are generated before lettered
semantic implementation work. Agents must use those existing targets rather
than inventing new runtime architecture or mixing unrelated faction work into a
single PR.

Each faction has an unlettered intake gate before lettered work starts:

1. Mirror and normalize the faction's prior-edition Wahapedia source rows.
2. Add official 11th Edition transition patch records for the faction.
3. Generate a source coverage report for army rules, detachments, enhancements,
   Stratagems, datasheets, wargear, weapon profiles, base sizes, and FAQs.
4. Expand the faction's detachment, enhancement, Stratagem, and datasheet-intake
   subphases from exact source row names and source IDs.

Lettered subphases should be small enough for review. Prefer one detachment or
one datasheet per subphase unless several datasheets share one inseparable kit,
weapon profile set, or official patch operation.

## Agent Implementation Contract

Agent-authored faction implementation PRs must follow
[docs/FACTION_AGENT_IMPLEMENTATION_CONTRACT.md](docs/FACTION_AGENT_IMPLEMENTATION_CONTRACT.md).
Task packets must name the faction or detachment, list allowed scaffold files,
require source IDs from generated manifest and execution rows, remove the
generated placeholder marker from implemented files, and preserve the shared
runtime loader, lifecycle, bundle, manifest, decision, replay, and engine-owned
mutation contracts.

Preferred batching is one army rule, one detachment rule, one detachment
enhancement set, or one detachment Stratagem set per PR. A full detachment PR is
acceptable when its rules, enhancements, and Stratagems are tightly coupled. A
whole-faction semantic PR is discouraged unless the faction is tiny.

## Pilot Phase: Death Guard

Death Guard is the pilot because the available official update example exercises
army rules, detachment content, datasheet abilities, keywords, weapon
characteristics, and FAQ advisory records.

- Phase Death Guard A: Nurgle's Gift army rule transition patch, including
  Contagion Range cap and Skullsquirm Blight replacement.
- Phase Death Guard B: Tallyband Summoners detachment support, including
  Beckoning Blight enhancement replacement.
- Phase Death Guard C0: Plague Marines end-to-end catalog/mustering smoke,
  proving patched source rows generate a canonical catalog package that can
  manifest Plague Marines with selected real wargear, canonical model geometry,
  and replay-safe army/state payloads. Rules not covered by the smoke remain
  explicit unsupported descriptors or future phase work, not runtime fallbacks.
- Phase Death Guard C: Typhus datasheet support, including Eater Plague
  replacement.
- Phase Death Guard D: Deathshroud Terminators datasheet support, including
  Death Approaches replacement.
- Phase Death Guard E: Chaos Predator Destructor datasheet support, including
  Predator Autocannon Strength replacement.
- Phase Death Guard F: FRAME keyword patch batch for Chaos Land Raider, Chaos
  Predator Annihilator, Chaos Predator Destructor, Chaos Rhino, Miasmic
  Malignifier, and Plagueburst Crawler.
- Phase Death Guard G: Plagueburst Crawler FAQ advisory record for Spore-laced
  Shock Waves, classified as `advisory_only` unless source review determines it
  changes executable behavior.
- Phase Death Guard H+: Remaining Death Guard datasheets, one exact datasheet or
  source-coupled kit group per lettered subphase after source import.

## FAQ Classification Gate

Every FAQ row in a faction intake or lettered subphase must be classified before
catalog emission as exactly one of:

- `advisory_only`: source-linked note that does not change executable behavior.
- `executable_patch`: source-linked patch operation represented by supported
  descriptors or catalog records in the same phase.
- `unsupported_executable_change`: source-linked executable behavior change that
  remains blocked behind an explicit unsupported diagnostic until implemented.

FAQs that change gameplay semantics must not be stored as `advisory_only`.
Reclassification requires a source-linked patch operation or diagnostic update.

## Faction Phase Queue

The queue starts with the pilot, then proceeds through every faction seeded in
the current 11th Edition faction-detachment source package. Detachment names
below are exact normalized source-row names from that package and must be
refreshed from the package API, not hand-edited.

For every faction phase below, datasheet intake letters cover exact datasheet
identity, composition, wargear-option, base-size, geometry,
representative-height, keyword, and faction-keyword rows from the patched source
mirror, one datasheet or source-coupled kit group per letter. Datasheet,
wargear, and weapon ability execution is deferred to Phase 17H unless the rule
is inseparable from a Phase 17E army rule, detachment rule, enhancement, or
Stratagem implemented in Phase 17G.

### Phase Death Guard

Initial letters are defined in the pilot phase.

- Detachment letters: Paragons of Putrescence, Contagion Engines, Flyblown
  Host, Champions of Contagion, Death Lord's Chosen, Mortarion's Hammer,
  Shamblerot Vectorium, Tallyband Summoners, Virulent Vectorium.

### Phase Orks

- Detachment letters: More Dakka!, Rollin' Deff, Taktikal Brigade, Blitz
  Brigade, Bully Boyz, Da Big Hunt, Dread Mob, Freebooter Krew, Green Tide, Kult
  of Speed, Speedwaaagh!, War Horde.

### Phase Aeldari

- Detachment letters: Armoured Warhost, Fateful Performance, Path of the
  Outcast, Twilight Flickers, Aspect Host, Corsair Coterie, Devoted of Ynnead,
  Eldritch Raiders, Ghosts of the Webway, Guardian Battlehost, Seer Council,
  Serpent's Brood, Spirit Conclave, Warhost, Windrider Host.

### Phase Drukhari

- Detachment letters: Exhibition of Slaughter, Kabalite Agonysts, Tools of
  Torment, Covenite Coterie, Kabalite Cartel, Realspace Raiders, Reaper's Wager,
  Skysplinter Assault, Spectacle of Spite.

### Phase Tyranids

- Detachment letters: Ambush Predators, Talons of the Norn Queen, Warrior
  Bioform Onslaught, Assimilation Swarm, Crusher Stampede, Invasion Fleet,
  Subterranean Assault, Synaptic Nexus, Unending Swarm, Vanguard Onslaught.

### Phase Genestealer Cults

- Detachment letters: Heroes of the Uprising, Purestrain Broodswarm, Xenocult
  Masses, Biosanctic Broodsurge, Brood Brothers Auxillia, Final Day, Host of
  Ascension, Outlander Claw, Xenocreed Congregation.

### Phase Necrons

- Detachment letters: Hand of the Dynasty, Skyshroud Spearhead, The Phaeron's
  Armoury, Annihilation Legion, Awakened Dynasty, Canoptek Court, Cryptek
  Conclave, Cursed Legion, Hypercrypt Legion, Obeisance Phalanx, Pantheon of
  Woe, Starshatter Arsenal.

### Phase Leagues of Votann

- Detachment letters: Armoured Trailblazers, Farseekers, Hearthguard Covenant,
  Brandfast Oathband, Delve Assault Shift, Hearthband, Hearthfyre Arsenal,
  Mercenary Oathband, Needgaard Oathband, Persecution Prospect.

### Phase T'au Empire

- Detachment letters: Advanced Acquisition Cadre, Auxillary Cadre, Experimental
  Prototype Cadre, Kauyon, Kroot Hunting Pack, Mont'ka, Retaliation Cadre.

### Phase Space Marines

- Detachment letters: Fulguris Task Force, Librarius Conclave, Subversion Assets,
  1st Company Task Force, Anvil Siege Force, Armoured Speartip, Bastion Task
  Force, Blade of Ultramar, Ceramite Sentinels, Emperor's Shield, Firestorm
  Assault Force, Forgefather's Seekers, Gladius Task Force, Hammer of Avernii,
  Headhunter Task Force, Ironstorm Spearhead, Orbital Assault Force, Reclamation
  Force, Shadowmark Talon, Spearpoint Task Force, Stormlance Task Force,
  Vanguard Spearhead.

### Phase Dark Angels

- Detachment letters: Dark Age Arsenal, Darkflight Pursuit, Interrogation
  Conclave, Company of Hunters, Inner Circle Task Force, Lion's Blade Task
  Force, Unforgiven Task Force, Wrath of the Rock.

### Phase Blood Angels

- Detachment letters: Encarmine Speartip, Legacy of Grace, Wrath of the Doomed,
  Angelic Inheritors, Liberator Assault Group, Rage-cursed Onslaught, The
  Angelic Host, The Lost Brethren.

### Phase Space Wolves

- Detachment letters: Champions of Fenris, Legends of Saga and Song, Veterans of
  the Fang, Saga of the Beastslayer, Saga of the Bold, Saga of the Great Wolf,
  Saga of the Hunter.

### Phase Black Templars

- Detachment letters: Marshal's Household, The Living Miracle, Wrathful
  Procession, Companions of Vehemence, Godhammer Assault Force, Vindication Task
  Force.

### Phase Deathwatch

- Detachment letters: Black Spear Task Force.

### Phase Grey Knights

- Detachment letters: Argent Assault, Fires of Purgation, Immaterial
  Interdiction, Augurium Task Force, Banishers, Brotherhood Strike, Hallowed
  Conclave, Sanctic Spearhead, Warpbane Task Force.

### Phase Chaos Space Marines

- Detachment letters: Cabal of Chaos, Devotees of Destruction, Murdertalon
  Raiders, Chaos Cult, Creations of Bile, Cult of the Arkifane, Deceptors, Dread
  Talons, Fellhammer Siege-host, Huron's Marauders, Nightmare Hunt, Pactbound
  Zealots, Renegade Raiders, Renegade Warband, Soulforged Warpack, Veterans of
  the Long War, Warpstrike Champions.

### Phase World Eaters

- Detachment letters: Butchers of Khorne, Brazen Engines, Vessels of Wrath,
  Berzerker Warband, Cult of Blood, Goretrack Onslaught, Khorne Daemonkin,
  Possessed Slaughterband.

### Phase Emperor's Children

- Detachment letters: Elegant Brutes, Frenzied Host, Spectacle of Slaughter,
  Carnival of Excess, Coterie of the Conceited, Court of the Phoenician,
  Mercurial Host, Peerless Bladesmen, Rapid Evisceration, Slaanesh's Chosen.

### Phase Thousand Sons

- Detachment letters: Ritual of Regeneration, Sekhetar Cohort, Servants of
  Change, Changehost of Deceit, Grand Coven, Hexwarp Thrallband, Rubricae
  Phalanx, Warpforged Cabal, Warpmeld Pact.
- Army rule runtime support: Cabal of Sorcerers Shooting-start ritual
  selection, Psychic test resolution, Destiny's Ruin hit rerolls, Temporal
  Surge movement proposals plus charge lockout, Doombolt mortal wounds, and
  Twist of Fate AP modifiers. Detachment rules, enhancements, and Stratagems
  remain source-covered scaffold rows until their named handlers are
  implemented.

### Phase Chaos Knights

- Detachment letters: Bastions of Tyranny, Hunting Warpack, Iconoclast Fiefdom,
  Helhunt Lance, Houndpack Lance, Infernal Lance, Lords of Dread, Traitoris
  Lance.
- Army rule runtime support: Harbingers of Dread Dread selections/rolls,
  Deathly Terror/Despair Leadership auras, Dismay forced Battle-shock,
  Delirium D3 mortal wounds, Doom wound modifiers, and Darkness Stealth hit
  modifiers. Delirium mortal-wound Feel No Pain continuation is deferred and
  emits a typed unsupported event without applying wounds. Detachment rules,
  enhancements, and Stratagems remain source-covered scaffold rows until their
  named handlers are implemented.

### Phase Chaos Daemons

- Detachment letters: Cavalcade of Chaos, Lords of the Warp, Warptide, Blood
  Legion, Daemonic Incursion, Legion of Excess, Plague Legion, Scintillating
  Legion, Shadow Legion.

### Phase Adepta Sororitas

- Detachment letters: Chorus of Condemnation, Sacred Champions, Sanctified
  Orators, Army of Faith, Bringers of Flame, Champions of Faith, Hallowed
  Martyrs, Penitent Host.

### Phase Adeptus Custodes

- Detachment letters: Might of the Moritoi, Silent Hunters, Tharanatoi
  Hammerblow, Auric Champions, Lions of the Emperor, Null Maiden Vigil, Shield
  Host, Solar Spearhead, Talons of the Emperor.

### Phase Adeptus Mechanicus

- Detachment letters: Cohort Acquisitus, Lords of the Forge, Luminen Auto-Choir,
  Cohort Cybernetica, Data-psalm Conclave, Eradication Cohort, Explorator
  Maniple, Haloscreed Battle Clade, Rad-zone Corps, Skitarii Hunter Cohort.

### Phase Astra Militarum

- Detachment letters: Abhuman Auxiliaries, Bridgehead Strike, Designation Force,
  Armoured Infantry, Combined Arms, Grizzled Company, Hammer of the Emperor,
  Mechanised Assault, Recon Element, Siege Regiment, Steel Hammer.

### Phase Imperial Agents

- Detachment letters: Imperialis Fleet; Ordo Hereticus, Purgation Force; Ordo
  Malleus, Daemon Hunters; Ordo Xenos, Alien Hunters; Veiled Blade Elimination
  Force.

### Phase Imperial Knights

- Detachment letters: Dominus Foebreakers, Questor Forgepact, Throne-bonded
  Outriders, Freeblade Company, Gate Warden Lance, Questoris Companions,
  Spearhead-at-arms, Valourstrike Lance.

## Per-Subphase Completion Gate

Each lettered subphase must include:

- normalized source rows and official patch records for the named content;
- catalog records with stable IDs and source IDs;
- explicit unsupported descriptors for unimplemented rule shapes;
- FAQ classification as `advisory_only`, `executable_patch`, or
  `unsupported_executable_change` whenever FAQ rows are in scope;
- deterministic package or catalog hash tests when source data is generated;
- engine behavior tests for any executable rule path;
- replay-safe payload tests for any state-changing rule path;
- a coverage update showing implemented, generic-supported,
  named-handler-required, and unsupported content.

## Deferral Rules

Deferring a detachment or datasheet is allowed only by recording an unsupported
descriptor with a source-linked reason. Deferrals must not create permissive
runtime fallbacks, default datasheet values, hidden text parsing, or alternate
adapter mutation paths.
