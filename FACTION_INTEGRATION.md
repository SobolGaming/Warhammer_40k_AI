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
and weapon ability execution belongs to Phase 17G unless a unit rule is
inseparable from a Phase 17E army rule, detachment rule, enhancement, or
Stratagem.

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
- schema version: `core-v2-phase17e-faction-coverage-v1`
- source-payload SHA-256 checksum:
  `6810281a9eacd4e4178c4ce2996a50b8bab4d184cc76dedf69c1615726de794a`

The package validates all 28 faction-pack PDF manifest records and emits
coverage rows for every seeded faction and detachment. Faction army rules and
detachment rules are source-linked named-handler-required rows. Datasheet intake,
enhancement descriptor subrows, and Stratagem descriptor subrows that are absent
from the update PDFs are fail-closed as approved unsupported diagnostics, so no
unapproved unsupported descriptor remains for Phase 17E matched-play coverage.
Those approved diagnostics are the source-row generation queue for later Phase
17 work; they are not runtime fallbacks.

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
- schema version: `core-v2-phase17f-faction-execution-v1`
- source-payload SHA-256 checksum:
  `7ec4269baff98ca2ea6b97de6a7305d502b00cf8a4fdb3ce4fb47aea4d1c90bf`
- upstream Phase 17E checksum:
  `6810281a9eacd4e4178c4ce2996a50b8bab4d184cc76dedf69c1615726de794a`

The package emits 854 execution records, one for every Phase 17E coverage row:
294 rows are blocked as `structured_rule_semantics_required`, and 560 rows are
blocked as `approved_phase17e_source_gap`. The engine dispatcher can execute
every record and returns typed `unsupported` results with those reasons. No
Phase 17E row remains a missing handler, runtime no-op, raw-PDF parse, or silent
fallback. Future executable rows require a registered generic IR executor or
named handler; unregistered executable statuses return typed `unsupported`
diagnostics and cannot emit `applied` by status alone.

## Faction Execution Status Matrix

This matrix is generated from the Phase 17F execution package. It records
execution status, not semantic support. Rows marked `unsupported` are deliberately
blocked until native structured rule semantics or generated source rows replace
the approved blocker.

### Death Guard Execution Status

| Covered item family | Rows | Execution status | Engine result | Source block |
|---|---:|---|---|---|
| Army rule | 1 | `blocked_structured_semantics_required` | `unsupported` | `structured_rule_semantics_required` |
| Detachment rules | 9 | `blocked_structured_semantics_required` | `unsupported` | `structured_rule_semantics_required` |
| Enhancement descriptors | 9 | `blocked_approved_unsupported_source_gap` | `unsupported` | `approved_phase17e_source_gap:exact_detachment_subrows_require_native_source` |
| Stratagem descriptors | 9 | `blocked_approved_unsupported_source_gap` | `unsupported` | `approved_phase17e_source_gap:exact_detachment_subrows_require_native_source` |
| Datasheet intake | 1 | `blocked_approved_unsupported_source_gap` | `unsupported` | `approved_phase17e_source_gap:datasheet_intake_requires_generated_source_rows` |

### Orks Execution Status

| Covered item family | Rows | Execution status | Engine result | Source block |
|---|---:|---|---|---|
| Army rule | 1 | `blocked_structured_semantics_required` | `unsupported` | `structured_rule_semantics_required` |
| Detachment rules | 12 | `blocked_structured_semantics_required` | `unsupported` | `structured_rule_semantics_required` |
| Enhancement descriptors | 12 | `blocked_approved_unsupported_source_gap` | `unsupported` | `approved_phase17e_source_gap:exact_detachment_subrows_require_native_source` |
| Stratagem descriptors | 12 | `blocked_approved_unsupported_source_gap` | `unsupported` | `approved_phase17e_source_gap:exact_detachment_subrows_require_native_source` |
| Datasheet intake | 1 | `blocked_approved_unsupported_source_gap` | `unsupported` | `approved_phase17e_source_gap:datasheet_intake_requires_generated_source_rows` |

### Aeldari Execution Status

| Covered item family | Rows | Execution status | Engine result | Source block |
|---|---:|---|---|---|
| Army rule | 1 | `blocked_structured_semantics_required` | `unsupported` | `structured_rule_semantics_required` |
| Detachment rules | 15 | `blocked_structured_semantics_required` | `unsupported` | `structured_rule_semantics_required` |
| Enhancement descriptors | 15 | `blocked_approved_unsupported_source_gap` | `unsupported` | `approved_phase17e_source_gap:exact_detachment_subrows_require_native_source` |
| Stratagem descriptors | 15 | `blocked_approved_unsupported_source_gap` | `unsupported` | `approved_phase17e_source_gap:exact_detachment_subrows_require_native_source` |
| Datasheet intake | 1 | `blocked_approved_unsupported_source_gap` | `unsupported` | `approved_phase17e_source_gap:datasheet_intake_requires_generated_source_rows` |

### Drukhari Execution Status

| Covered item family | Rows | Execution status | Engine result | Source block |
|---|---:|---|---|---|
| Army rule | 1 | `blocked_structured_semantics_required` | `unsupported` | `structured_rule_semantics_required` |
| Detachment rules | 9 | `blocked_structured_semantics_required` | `unsupported` | `structured_rule_semantics_required` |
| Enhancement descriptors | 9 | `blocked_approved_unsupported_source_gap` | `unsupported` | `approved_phase17e_source_gap:exact_detachment_subrows_require_native_source` |
| Stratagem descriptors | 9 | `blocked_approved_unsupported_source_gap` | `unsupported` | `approved_phase17e_source_gap:exact_detachment_subrows_require_native_source` |
| Datasheet intake | 1 | `blocked_approved_unsupported_source_gap` | `unsupported` | `approved_phase17e_source_gap:datasheet_intake_requires_generated_source_rows` |

### Tyranids Execution Status

| Covered item family | Rows | Execution status | Engine result | Source block |
|---|---:|---|---|---|
| Army rule | 1 | `blocked_structured_semantics_required` | `unsupported` | `structured_rule_semantics_required` |
| Detachment rules | 10 | `blocked_structured_semantics_required` | `unsupported` | `structured_rule_semantics_required` |
| Enhancement descriptors | 10 | `blocked_approved_unsupported_source_gap` | `unsupported` | `approved_phase17e_source_gap:exact_detachment_subrows_require_native_source` |
| Stratagem descriptors | 10 | `blocked_approved_unsupported_source_gap` | `unsupported` | `approved_phase17e_source_gap:exact_detachment_subrows_require_native_source` |
| Datasheet intake | 1 | `blocked_approved_unsupported_source_gap` | `unsupported` | `approved_phase17e_source_gap:datasheet_intake_requires_generated_source_rows` |

### Genestealer Cults Execution Status

| Covered item family | Rows | Execution status | Engine result | Source block |
|---|---:|---|---|---|
| Army rule | 1 | `blocked_structured_semantics_required` | `unsupported` | `structured_rule_semantics_required` |
| Detachment rules | 9 | `blocked_structured_semantics_required` | `unsupported` | `structured_rule_semantics_required` |
| Enhancement descriptors | 9 | `blocked_approved_unsupported_source_gap` | `unsupported` | `approved_phase17e_source_gap:exact_detachment_subrows_require_native_source` |
| Stratagem descriptors | 9 | `blocked_approved_unsupported_source_gap` | `unsupported` | `approved_phase17e_source_gap:exact_detachment_subrows_require_native_source` |
| Datasheet intake | 1 | `blocked_approved_unsupported_source_gap` | `unsupported` | `approved_phase17e_source_gap:datasheet_intake_requires_generated_source_rows` |

### Necrons Execution Status

| Covered item family | Rows | Execution status | Engine result | Source block |
|---|---:|---|---|---|
| Army rule | 1 | `blocked_structured_semantics_required` | `unsupported` | `structured_rule_semantics_required` |
| Detachment rules | 12 | `blocked_structured_semantics_required` | `unsupported` | `structured_rule_semantics_required` |
| Enhancement descriptors | 12 | `blocked_approved_unsupported_source_gap` | `unsupported` | `approved_phase17e_source_gap:exact_detachment_subrows_require_native_source` |
| Stratagem descriptors | 12 | `blocked_approved_unsupported_source_gap` | `unsupported` | `approved_phase17e_source_gap:exact_detachment_subrows_require_native_source` |
| Datasheet intake | 1 | `blocked_approved_unsupported_source_gap` | `unsupported` | `approved_phase17e_source_gap:datasheet_intake_requires_generated_source_rows` |

### Leagues of Votann Execution Status

| Covered item family | Rows | Execution status | Engine result | Source block |
|---|---:|---|---|---|
| Army rule | 1 | `blocked_structured_semantics_required` | `unsupported` | `structured_rule_semantics_required` |
| Detachment rules | 10 | `blocked_structured_semantics_required` | `unsupported` | `structured_rule_semantics_required` |
| Enhancement descriptors | 10 | `blocked_approved_unsupported_source_gap` | `unsupported` | `approved_phase17e_source_gap:exact_detachment_subrows_require_native_source` |
| Stratagem descriptors | 10 | `blocked_approved_unsupported_source_gap` | `unsupported` | `approved_phase17e_source_gap:exact_detachment_subrows_require_native_source` |
| Datasheet intake | 1 | `blocked_approved_unsupported_source_gap` | `unsupported` | `approved_phase17e_source_gap:datasheet_intake_requires_generated_source_rows` |

### T'au Empire Execution Status

| Covered item family | Rows | Execution status | Engine result | Source block |
|---|---:|---|---|---|
| Army rule | 1 | `blocked_structured_semantics_required` | `unsupported` | `structured_rule_semantics_required` |
| Detachment rules | 7 | `blocked_structured_semantics_required` | `unsupported` | `structured_rule_semantics_required` |
| Enhancement descriptors | 7 | `blocked_approved_unsupported_source_gap` | `unsupported` | `approved_phase17e_source_gap:exact_detachment_subrows_require_native_source` |
| Stratagem descriptors | 7 | `blocked_approved_unsupported_source_gap` | `unsupported` | `approved_phase17e_source_gap:exact_detachment_subrows_require_native_source` |
| Datasheet intake | 1 | `blocked_approved_unsupported_source_gap` | `unsupported` | `approved_phase17e_source_gap:datasheet_intake_requires_generated_source_rows` |

### Space Marines Execution Status

| Covered item family | Rows | Execution status | Engine result | Source block |
|---|---:|---|---|---|
| Army rule | 1 | `blocked_structured_semantics_required` | `unsupported` | `structured_rule_semantics_required` |
| Detachment rules | 22 | `blocked_structured_semantics_required` | `unsupported` | `structured_rule_semantics_required` |
| Enhancement descriptors | 22 | `blocked_approved_unsupported_source_gap` | `unsupported` | `approved_phase17e_source_gap:exact_detachment_subrows_require_native_source` |
| Stratagem descriptors | 22 | `blocked_approved_unsupported_source_gap` | `unsupported` | `approved_phase17e_source_gap:exact_detachment_subrows_require_native_source` |
| Datasheet intake | 1 | `blocked_approved_unsupported_source_gap` | `unsupported` | `approved_phase17e_source_gap:datasheet_intake_requires_generated_source_rows` |

### Dark Angels Execution Status

| Covered item family | Rows | Execution status | Engine result | Source block |
|---|---:|---|---|---|
| Army rule | 1 | `blocked_structured_semantics_required` | `unsupported` | `structured_rule_semantics_required` |
| Detachment rules | 8 | `blocked_structured_semantics_required` | `unsupported` | `structured_rule_semantics_required` |
| Enhancement descriptors | 8 | `blocked_approved_unsupported_source_gap` | `unsupported` | `approved_phase17e_source_gap:exact_detachment_subrows_require_native_source` |
| Stratagem descriptors | 8 | `blocked_approved_unsupported_source_gap` | `unsupported` | `approved_phase17e_source_gap:exact_detachment_subrows_require_native_source` |
| Datasheet intake | 1 | `blocked_approved_unsupported_source_gap` | `unsupported` | `approved_phase17e_source_gap:datasheet_intake_requires_generated_source_rows` |

### Blood Angels Execution Status

| Covered item family | Rows | Execution status | Engine result | Source block |
|---|---:|---|---|---|
| Army rule | 1 | `blocked_structured_semantics_required` | `unsupported` | `structured_rule_semantics_required` |
| Detachment rules | 8 | `blocked_structured_semantics_required` | `unsupported` | `structured_rule_semantics_required` |
| Enhancement descriptors | 8 | `blocked_approved_unsupported_source_gap` | `unsupported` | `approved_phase17e_source_gap:exact_detachment_subrows_require_native_source` |
| Stratagem descriptors | 8 | `blocked_approved_unsupported_source_gap` | `unsupported` | `approved_phase17e_source_gap:exact_detachment_subrows_require_native_source` |
| Datasheet intake | 1 | `blocked_approved_unsupported_source_gap` | `unsupported` | `approved_phase17e_source_gap:datasheet_intake_requires_generated_source_rows` |

### Space Wolves Execution Status

| Covered item family | Rows | Execution status | Engine result | Source block |
|---|---:|---|---|---|
| Army rule | 1 | `blocked_structured_semantics_required` | `unsupported` | `structured_rule_semantics_required` |
| Detachment rules | 7 | `blocked_structured_semantics_required` | `unsupported` | `structured_rule_semantics_required` |
| Enhancement descriptors | 7 | `blocked_approved_unsupported_source_gap` | `unsupported` | `approved_phase17e_source_gap:exact_detachment_subrows_require_native_source` |
| Stratagem descriptors | 7 | `blocked_approved_unsupported_source_gap` | `unsupported` | `approved_phase17e_source_gap:exact_detachment_subrows_require_native_source` |
| Datasheet intake | 1 | `blocked_approved_unsupported_source_gap` | `unsupported` | `approved_phase17e_source_gap:datasheet_intake_requires_generated_source_rows` |

### Black Templars Execution Status

| Covered item family | Rows | Execution status | Engine result | Source block |
|---|---:|---|---|---|
| Army rule | 1 | `blocked_structured_semantics_required` | `unsupported` | `structured_rule_semantics_required` |
| Detachment rules | 6 | `blocked_structured_semantics_required` | `unsupported` | `structured_rule_semantics_required` |
| Enhancement descriptors | 6 | `blocked_approved_unsupported_source_gap` | `unsupported` | `approved_phase17e_source_gap:exact_detachment_subrows_require_native_source` |
| Stratagem descriptors | 6 | `blocked_approved_unsupported_source_gap` | `unsupported` | `approved_phase17e_source_gap:exact_detachment_subrows_require_native_source` |
| Datasheet intake | 1 | `blocked_approved_unsupported_source_gap` | `unsupported` | `approved_phase17e_source_gap:datasheet_intake_requires_generated_source_rows` |

### Deathwatch Execution Status

| Covered item family | Rows | Execution status | Engine result | Source block |
|---|---:|---|---|---|
| Army rule | 1 | `blocked_structured_semantics_required` | `unsupported` | `structured_rule_semantics_required` |
| Detachment rules | 1 | `blocked_structured_semantics_required` | `unsupported` | `structured_rule_semantics_required` |
| Enhancement descriptors | 1 | `blocked_approved_unsupported_source_gap` | `unsupported` | `approved_phase17e_source_gap:exact_detachment_subrows_require_native_source` |
| Stratagem descriptors | 1 | `blocked_approved_unsupported_source_gap` | `unsupported` | `approved_phase17e_source_gap:exact_detachment_subrows_require_native_source` |
| Datasheet intake | 1 | `blocked_approved_unsupported_source_gap` | `unsupported` | `approved_phase17e_source_gap:datasheet_intake_requires_generated_source_rows` |

### Grey Knights Execution Status

| Covered item family | Rows | Execution status | Engine result | Source block |
|---|---:|---|---|---|
| Army rule | 1 | `blocked_structured_semantics_required` | `unsupported` | `structured_rule_semantics_required` |
| Detachment rules | 9 | `blocked_structured_semantics_required` | `unsupported` | `structured_rule_semantics_required` |
| Enhancement descriptors | 9 | `blocked_approved_unsupported_source_gap` | `unsupported` | `approved_phase17e_source_gap:exact_detachment_subrows_require_native_source` |
| Stratagem descriptors | 9 | `blocked_approved_unsupported_source_gap` | `unsupported` | `approved_phase17e_source_gap:exact_detachment_subrows_require_native_source` |
| Datasheet intake | 1 | `blocked_approved_unsupported_source_gap` | `unsupported` | `approved_phase17e_source_gap:datasheet_intake_requires_generated_source_rows` |

### Chaos Space Marines Execution Status

| Covered item family | Rows | Execution status | Engine result | Source block |
|---|---:|---|---|---|
| Army rule | 1 | `blocked_structured_semantics_required` | `unsupported` | `structured_rule_semantics_required` |
| Detachment rules | 17 | `blocked_structured_semantics_required` | `unsupported` | `structured_rule_semantics_required` |
| Enhancement descriptors | 17 | `blocked_approved_unsupported_source_gap` | `unsupported` | `approved_phase17e_source_gap:exact_detachment_subrows_require_native_source` |
| Stratagem descriptors | 17 | `blocked_approved_unsupported_source_gap` | `unsupported` | `approved_phase17e_source_gap:exact_detachment_subrows_require_native_source` |
| Datasheet intake | 1 | `blocked_approved_unsupported_source_gap` | `unsupported` | `approved_phase17e_source_gap:datasheet_intake_requires_generated_source_rows` |

### World Eaters Execution Status

| Covered item family | Rows | Execution status | Engine result | Source block |
|---|---:|---|---|---|
| Army rule | 1 | `blocked_structured_semantics_required` | `unsupported` | `structured_rule_semantics_required` |
| Detachment rules | 8 | `blocked_structured_semantics_required` | `unsupported` | `structured_rule_semantics_required` |
| Enhancement descriptors | 8 | `blocked_approved_unsupported_source_gap` | `unsupported` | `approved_phase17e_source_gap:exact_detachment_subrows_require_native_source` |
| Stratagem descriptors | 8 | `blocked_approved_unsupported_source_gap` | `unsupported` | `approved_phase17e_source_gap:exact_detachment_subrows_require_native_source` |
| Datasheet intake | 1 | `blocked_approved_unsupported_source_gap` | `unsupported` | `approved_phase17e_source_gap:datasheet_intake_requires_generated_source_rows` |

### Emperor's Children Execution Status

| Covered item family | Rows | Execution status | Engine result | Source block |
|---|---:|---|---|---|
| Army rule | 1 | `blocked_structured_semantics_required` | `unsupported` | `structured_rule_semantics_required` |
| Detachment rules | 10 | `blocked_structured_semantics_required` | `unsupported` | `structured_rule_semantics_required` |
| Enhancement descriptors | 10 | `blocked_approved_unsupported_source_gap` | `unsupported` | `approved_phase17e_source_gap:exact_detachment_subrows_require_native_source` |
| Stratagem descriptors | 10 | `blocked_approved_unsupported_source_gap` | `unsupported` | `approved_phase17e_source_gap:exact_detachment_subrows_require_native_source` |
| Datasheet intake | 1 | `blocked_approved_unsupported_source_gap` | `unsupported` | `approved_phase17e_source_gap:datasheet_intake_requires_generated_source_rows` |

### Thousand Sons Execution Status

| Covered item family | Rows | Execution status | Engine result | Source block |
|---|---:|---|---|---|
| Army rule | 1 | `blocked_structured_semantics_required` | `unsupported` | `structured_rule_semantics_required` |
| Detachment rules | 9 | `blocked_structured_semantics_required` | `unsupported` | `structured_rule_semantics_required` |
| Enhancement descriptors | 9 | `blocked_approved_unsupported_source_gap` | `unsupported` | `approved_phase17e_source_gap:exact_detachment_subrows_require_native_source` |
| Stratagem descriptors | 9 | `blocked_approved_unsupported_source_gap` | `unsupported` | `approved_phase17e_source_gap:exact_detachment_subrows_require_native_source` |
| Datasheet intake | 1 | `blocked_approved_unsupported_source_gap` | `unsupported` | `approved_phase17e_source_gap:datasheet_intake_requires_generated_source_rows` |

### Chaos Knights Execution Status

| Covered item family | Rows | Execution status | Engine result | Source block |
|---|---:|---|---|---|
| Army rule | 1 | `blocked_structured_semantics_required` | `unsupported` | `structured_rule_semantics_required` |
| Detachment rules | 8 | `blocked_structured_semantics_required` | `unsupported` | `structured_rule_semantics_required` |
| Enhancement descriptors | 8 | `blocked_approved_unsupported_source_gap` | `unsupported` | `approved_phase17e_source_gap:exact_detachment_subrows_require_native_source` |
| Stratagem descriptors | 8 | `blocked_approved_unsupported_source_gap` | `unsupported` | `approved_phase17e_source_gap:exact_detachment_subrows_require_native_source` |
| Datasheet intake | 1 | `blocked_approved_unsupported_source_gap` | `unsupported` | `approved_phase17e_source_gap:datasheet_intake_requires_generated_source_rows` |

### Chaos Daemons Execution Status

| Covered item family | Rows | Execution status | Engine result | Source block |
|---|---:|---|---|---|
| Army rule | 1 | `blocked_structured_semantics_required` | `unsupported` | `structured_rule_semantics_required` |
| Detachment rules | 9 | `blocked_structured_semantics_required` | `unsupported` | `structured_rule_semantics_required` |
| Enhancement descriptors | 9 | `blocked_approved_unsupported_source_gap` | `unsupported` | `approved_phase17e_source_gap:exact_detachment_subrows_require_native_source` |
| Stratagem descriptors | 9 | `blocked_approved_unsupported_source_gap` | `unsupported` | `approved_phase17e_source_gap:exact_detachment_subrows_require_native_source` |
| Datasheet intake | 1 | `blocked_approved_unsupported_source_gap` | `unsupported` | `approved_phase17e_source_gap:datasheet_intake_requires_generated_source_rows` |

### Adepta Sororitas Execution Status

| Covered item family | Rows | Execution status | Engine result | Source block |
|---|---:|---|---|---|
| Army rule | 1 | `blocked_structured_semantics_required` | `unsupported` | `structured_rule_semantics_required` |
| Detachment rules | 8 | `blocked_structured_semantics_required` | `unsupported` | `structured_rule_semantics_required` |
| Enhancement descriptors | 8 | `blocked_approved_unsupported_source_gap` | `unsupported` | `approved_phase17e_source_gap:exact_detachment_subrows_require_native_source` |
| Stratagem descriptors | 8 | `blocked_approved_unsupported_source_gap` | `unsupported` | `approved_phase17e_source_gap:exact_detachment_subrows_require_native_source` |
| Datasheet intake | 1 | `blocked_approved_unsupported_source_gap` | `unsupported` | `approved_phase17e_source_gap:datasheet_intake_requires_generated_source_rows` |

### Adeptus Custodes Execution Status

| Covered item family | Rows | Execution status | Engine result | Source block |
|---|---:|---|---|---|
| Army rule | 1 | `blocked_structured_semantics_required` | `unsupported` | `structured_rule_semantics_required` |
| Detachment rules | 9 | `blocked_structured_semantics_required` | `unsupported` | `structured_rule_semantics_required` |
| Enhancement descriptors | 9 | `blocked_approved_unsupported_source_gap` | `unsupported` | `approved_phase17e_source_gap:exact_detachment_subrows_require_native_source` |
| Stratagem descriptors | 9 | `blocked_approved_unsupported_source_gap` | `unsupported` | `approved_phase17e_source_gap:exact_detachment_subrows_require_native_source` |
| Datasheet intake | 1 | `blocked_approved_unsupported_source_gap` | `unsupported` | `approved_phase17e_source_gap:datasheet_intake_requires_generated_source_rows` |

### Adeptus Mechanicus Execution Status

| Covered item family | Rows | Execution status | Engine result | Source block |
|---|---:|---|---|---|
| Army rule | 1 | `blocked_structured_semantics_required` | `unsupported` | `structured_rule_semantics_required` |
| Detachment rules | 10 | `blocked_structured_semantics_required` | `unsupported` | `structured_rule_semantics_required` |
| Enhancement descriptors | 10 | `blocked_approved_unsupported_source_gap` | `unsupported` | `approved_phase17e_source_gap:exact_detachment_subrows_require_native_source` |
| Stratagem descriptors | 10 | `blocked_approved_unsupported_source_gap` | `unsupported` | `approved_phase17e_source_gap:exact_detachment_subrows_require_native_source` |
| Datasheet intake | 1 | `blocked_approved_unsupported_source_gap` | `unsupported` | `approved_phase17e_source_gap:datasheet_intake_requires_generated_source_rows` |

### Astra Militarum Execution Status

| Covered item family | Rows | Execution status | Engine result | Source block |
|---|---:|---|---|---|
| Army rule | 1 | `blocked_structured_semantics_required` | `unsupported` | `structured_rule_semantics_required` |
| Detachment rules | 11 | `blocked_structured_semantics_required` | `unsupported` | `structured_rule_semantics_required` |
| Enhancement descriptors | 11 | `blocked_approved_unsupported_source_gap` | `unsupported` | `approved_phase17e_source_gap:exact_detachment_subrows_require_native_source` |
| Stratagem descriptors | 11 | `blocked_approved_unsupported_source_gap` | `unsupported` | `approved_phase17e_source_gap:exact_detachment_subrows_require_native_source` |
| Datasheet intake | 1 | `blocked_approved_unsupported_source_gap` | `unsupported` | `approved_phase17e_source_gap:datasheet_intake_requires_generated_source_rows` |

### Imperial Agents Execution Status

| Covered item family | Rows | Execution status | Engine result | Source block |
|---|---:|---|---|---|
| Army rule | 1 | `blocked_structured_semantics_required` | `unsupported` | `structured_rule_semantics_required` |
| Detachment rules | 5 | `blocked_structured_semantics_required` | `unsupported` | `structured_rule_semantics_required` |
| Enhancement descriptors | 5 | `blocked_approved_unsupported_source_gap` | `unsupported` | `approved_phase17e_source_gap:exact_detachment_subrows_require_native_source` |
| Stratagem descriptors | 5 | `blocked_approved_unsupported_source_gap` | `unsupported` | `approved_phase17e_source_gap:exact_detachment_subrows_require_native_source` |
| Datasheet intake | 1 | `blocked_approved_unsupported_source_gap` | `unsupported` | `approved_phase17e_source_gap:datasheet_intake_requires_generated_source_rows` |

### Imperial Knights Execution Status

| Covered item family | Rows | Execution status | Engine result | Source block |
|---|---:|---|---|---|
| Army rule | 1 | `blocked_structured_semantics_required` | `unsupported` | `structured_rule_semantics_required` |
| Detachment rules | 8 | `blocked_structured_semantics_required` | `unsupported` | `structured_rule_semantics_required` |
| Enhancement descriptors | 8 | `blocked_approved_unsupported_source_gap` | `unsupported` | `approved_phase17e_source_gap:exact_detachment_subrows_require_native_source` |
| Stratagem descriptors | 8 | `blocked_approved_unsupported_source_gap` | `unsupported` | `approved_phase17e_source_gap:exact_detachment_subrows_require_native_source` |
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
wargear, and weapon ability execution is deferred to Phase 17G unless the rule
is inseparable from a Phase 17E army rule, detachment rule, enhancement, or
Stratagem.

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

### Phase Chaos Knights

- Detachment letters: Bastions of Tyranny, Hunting Warpack, Iconoclast Fiefdom,
  Helhunt Lance, Houndpack Lance, Infernal Lance, Lords of Dread, Traitoris
  Lance.

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
