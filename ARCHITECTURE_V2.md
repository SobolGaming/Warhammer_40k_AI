# CORE V2 Architecture Build Order

This document is the build-order roadmap for reconstructing the Warhammer 40,000 CORE V2 engine after the completed Phase 1-14D work, the completed Phase 14E attack sequence/allocation cutover, the Phase 14F shooting-type cutover, the Phase 14G Charge/Fight source contract, the Phase 14I Core Stratagem and ability source-contract closeout, the Phase 14J mission/catalog replacement slice, the Phase 14K cutover hardening audits, the Phase 14L ranged attack grouping layer, the Phase 15A charge declaration/roll implementation, the Phase 15B charge movement implementation, the Phase 15C fight activation/pass/interrupt implementation, the Phase 15D Pile In/melee/Consolidate implementation, the Phase 15E Charge/Fight Core Stratagem implementation, the Phase 15F Charge/Fight completion gate hardening, the Phase 16A deployment setup implementation, the Phase 16B pre-battle abilities implementation, the Phase 16C reserve declaration implementation, the Phase 16D army construction completion, the Phase 16E setup completion gate implementation, the Phase 17A bridge source mirror implementation, the Phase 17A.1 transition patch package implementation, the Phase 17B canonical catalog generation implementation, the Phase 17C rule-language IR implementation, the Phase 17D generic rule execution implementation, the Phase 17E faction coverage implementation, the Phase 17F faction execution dispatch implementation, the Phase 17J Warhammer Event Companion mission-pack implementation, the 11th Edition Core Rules source drop, and the Warhammer Event Companion v1.0 source drop.

The roadmap is intentionally rules-engine first:

- engine lifecycle and state are authoritative;
- every player, AI, UI, network, and replay interaction goes through `DecisionRequest`, `DecisionResult`, and `DecisionRecord`;
- runtime code executes typed descriptors and handlers, not raw rule text;
- replay payloads are deterministic, JSON-safe, and fail-fast on drift;
- unsupported rule shapes are explicit, source-linked, and auditable.

Primary references for roadmap coverage:

- Warhammer 40,000 11th Edition Core Rules source PDF: [docs/source_rules/eng_01-06_warhammer40k_new40k_core_rules-was6fbu1ix-hfewhmxyiy.pdf](docs/source_rules/eng_01-06_warhammer40k_new40k_core_rules-was6fbu1ix-hfewhmxyiy.pdf)
- Warhammer Event Companion v1.0 source PDF, used as a local-only validation input for Phase 17J source-package planning; do not commit raw event PDFs.
- 11th Edition app/codex/mission-pack source imports as they are added to CORE V2 source packages.
- 11th Edition Digital App/community clarification supplement provided by project owner for this cutover plan.
- CORE V1 reference implementation: <https://github.com/SobolGaming/Warhammer40k_AI>
- CORE V1 generated Wahapedia data: <https://github.com/SobolGaming/Warhammer40k_AI/tree/dev/wahapedia_data>
- CORE V2 repository: <https://github.com/SobolGaming/Warhammer_40k_AI>

CORE V2 is now 11th Edition-only. Previous-edition source package names, descriptor IDs, tests, and comments are migration debt, not supported compatibility targets. Do not add edition-diff switches, compatibility shims, or dual-edition behavior unless a future repository policy explicitly reverses this decision.

## Roadmap status

Everything through **Phase 14H** is treated as implemented at the time this file
was updated. **Phase 14E is complete**: the allocation-group foundation and
grouped-host weapon-ability revalidation are implemented for supported
fixed-damage attack pools, including save-before-allocation batching, defender
ordered allocation decisions, current allocation group transitions,
low-to-high failed-save damage resolution, normal-damage-before-routed-mortal
ordering, Precision group priority, Devastating Wounds cap/order, Lethal Hits,
Sustained Hits, Anti, Twin-linked, Melta, Torrent, critical timing, no illegal
Devastating Wounds spillover, melee Cleave dice gathering, and Lance
charge-gated Wound-roll modifiers. **Phase 14F's shooting-type cutover is
implemented** for Normal, Assault, Close-quarters, Indirect, and Snap shooting,
including finite shooting-type selection, supported grouped attack resolution,
Indirect/Snap Hit-roll reroll bans, and the Shooting-phase action-start lock.
**Phase 14G's Charge/Fight source contract is implemented** as typed ruleset
descriptor payloads and deferred unsupported Core Stratagem hooks. **Phase 14H
is complete for the current transport/reserve plus attached-unit attack/healing
projection slice**: runtime Attached Unit formation now uses structured army-list Leader/Support declarations
against catalog attachment eligibility,
emits first-class attached rules-unit formation records, derives attached-unit
Starting Strength until split, and feeds source-backed Bodyguard/Leader/Support
evidence used by Shooting acting-unit selection, mixed-Toughness attacks,
healing, revival, persisting effects, and stratagem target canonicalization.
Phase 16D now supplies the strict army-construction records consumed by those
runtime hosts: Warlord, Enhancement, roster-legality, Dedicated Transport
manifest provenance, and the source army-definition data from which `GameState`
derives `StartingStrengthRecord` entries. Phase 14H also
covers Combat/Emergency Hazard Roll routing through shared mortal wounds and
Feel No Pain, destroyed-Transport Emergency Disembark orchestration from actual
destruction timing before Transport removal and Deadly Demise, setup-time
Strategic Reserve declarations and battle-formation Transport embarkation,
repositioned-unit move-history/effect persistence, exact At Half-strength
payload state, and runtime added-unit Starting Strength records. **Phase 14I is
complete** for the current Core Stratagem and core-ability source cutover: all
11th Edition Core Stratagem source rows have supported handlers, implemented
duplicate weapon ability selection is adapter-visible and replay-safe, and
unimplemented Core ability families are fail-closed as explicit unsupported
descriptors with future owning phase IDs. **Phase 14J's mission/catalog
replacement slice is implemented** for source-tracked 11th Edition Force
Dispositions, the named 25-cell Primary Mission matrix, three layout identifiers
per matrix cell, and finite Tactical Secondary score/retain decisions.
Exact 11th Edition Secondary card identities beyond current source rows,
Primary Mission scoring text, Event Companion terrain/deployment layout
geometry, and Base Size Guide source-row status are now represented by the
Phase 17J Warhammer Event Companion source package rather than deferred to
Phase 20.
**Phase 14K is complete**:
cutover hardening now rejects retired save/allocation choice
surfaces, old aircraft minimum-move and pivot-limit runtime paths, 9" reserve
arrival enemy-distance policy, separate Reinforcements-step placement records,
retired Core Stratagem source names, and stale grouped Inflict Damage model
selections before queue pop. **Phase 14L is complete for ranged attacks**:
Shooting attack resolution now follows Select Enemy Unit, Gather Attack Dice by
deterministic identical-attack signature, the existing Resolve Attack Dice
subgraph, and the Other Attacks loop. **Phase 15A is complete** for charge
eligibility, charging-unit selection, deterministic Charge rolls, and
reachable-target snapshots. **Phase 15B is complete** for post-roll Charge Move
proposals, PathWitness validation, shared pathing/terrain/coherency checks,
endpoint constraints, displacements, and Fights First effects. **Phase 15C is
complete** for the Fight phase envelope, first-class `FightOrderState`, Fights
First/Remaining Combats ordering loop, finite activation/pass decisions, legal
Normal/Overrun fight-type filtering, and reaction-queue fight interrupts with
source-scoped consumption. **Phase 15D is complete** for Pile In and Consolidate
proposal routing, PathWitness-based fight movement validation, Overrun's
additional Pile In hook, melee declaration requests, one-primary-melee-weapon
selection with optional `[EXTRA ATTACKS]`, model-engaged target validation, split
melee attack counts, and reuse of the shared attack sequence. **Phase 15E is
complete** for source-backed Heroic Intervention, Counteroffensive, Crushing
Impact, and Epic Challenge through the shared Stratagem/Charge/Fight decision
path. **Phase 15F is complete** for Charge/Fight completion gates, full
both-player phase completion coverage, Fight damage/removal draining before
completion, and deterministic replay-safe fight-order hardening. **Phase 17J is
complete** for the Warhammer Event Companion mission-pack source package:
Event Mission Sequence descriptors, Tactical/Fixed Secondary procedure
descriptors, all 25 implemented Primary Mission matrix cells, all 45
source-page layout identities with pending coordinate-extraction status, Event
Companion mission-pack import, scoring/draw pack resolution, separate empty
card-amendment and FAQ patch records, Base Size Guide source rows with
geometry-resolution statuses, deployment remainder-drain coverage, and a static
audit preventing runtime Event Companion PDF parsing.
**Phase 16A is
complete** for source-backed Deploy Armies: lifecycle setup now creates an empty
source-backed battlefield at Create Battlefield, deploys units through
`select_deployment_unit` and `submit_deployment_placement`, validates deployment
zones, `INFILTRATORS`, terrain/objective/engagement/coherency endpoints,
attached rules-unit model sets, reserves exclusion, stale/malformed submissions,
and deterministic replay-safe placement events without using the Phase 10A
deterministic bridge.

**Phase 16B is complete** for redeployments, Scouts, and Resolve Pre-battle
Abilities: redeploy finite selections and placement proposals resolve as
temporary removal plus setup placement, simultaneous pre-battle effects use the
Phase 12A sequencing path, Scout reserve setup resolves as setup placement from
Strategic Reserves, Scout Moves require per-model `PathWitness` evidence and
shared movement validators, Dedicated Transport Scout Move eligibility is
cargo-aware, structured datasheet ability descriptors provide `Scouts X"`
distances, and deterministic `PreBattleActionRecord` payloads preserve
replay-safe setup action history. Current source catalog ability ownership is
datasheet/component-granular; future per-model catalog ownership can refine
mixed-model Scouts eligibility without changing the adapter proposal path.

**Phase 16C is complete** for reserve declarations during Declare Battle
Formations: setup now emits `select_reserve_declaration` finite requests for
Strategic Reserves and Deep Strike choices, enforces the source-backed
Strategic Reserves points cap and FORTIFICATION exclusion, records AIRCRAFT
mandatory reserves as ordinary `ReserveState` payloads, preserves source rule
IDs and points contribution, rejects stale submissions before queue pop, and
excludes declared reserves from Deploy Armies options.

**Phase 16D is complete** for source-backed army construction and runtime
instantiation: strict roster requests validate Strike Force unit points plus
selected Enhancement points, unit limits, Warlord selection, Enhancement
assignment rules, attached-squad Enhancement limits, Epic Hero restrictions,
required Dedicated Transport manifest source data, and provided Dedicated
Transport cargo legality through deterministic `RosterLegalityReport`
diagnostics. Production `GameConfig` values require strict mustering requests
by default; legacy smoke fixtures must opt into
`allow_legacy_non_strict_rosters`. Mustered armies preserve Warlord,
Enhancement, unit-point, Dedicated Transport, and legality provenance in
JSON-safe payloads, promote the selected Warlord with a `WARLORD` keyword, and
setup records source-backed starting embarked cargo before Deploy Armies while
explicit empty Dedicated Transport manifests become deterministic setup
consequences that exclude the transport from deployment and mark it destroyed
in battle round 1. `GameState.record_army_definition(...)` derives the
`StartingStrengthRecord` set consumed by later phases.

**Phase 16E is complete** for the engine-owned setup completion gate:
setup-to-battle transition now requires a drained decision queue, drained
reaction queue, final setup step, mustered armies, source-backed mission setup,
secondary mission choices, attacker/defender assignments, declared reserves,
completed deployment, battlefield coherency, and resolved redeploy/pre-battle
actions. Legal completion emits deterministic `SetupLegalityReport`,
`SetupReplayCheckpoint`, and `BattleStartRecord` payloads, records
`setup_completion_gate_passed` and `battle_started` events, and enters battle
round one without the Phase 10A deterministic placement bridge. Invalid setup
returns typed `setup_completion_gate_failed` diagnostics and leaves the game in
setup.

**Phase 17A is complete** for the bridge Wahapedia source mirror and CSV-to-JSON
ETL. The source mirror now records source snapshots and package manifests with
checksums, upstream identity, source date, source-edition identity, deterministic
artifact hashes, HTML sanitization reports, structured source-text
normalization, source-row provenance, runtime-field HTML exclusion, grouped
malformed-row diagnostics, and a static boundary check that prevents engine
runtime from importing raw source mirror or sanitizer modules.

**Phase 17A.1 is complete** for official 11th Edition transition patch
packages. The patch layer now models source-linked operations, exact and
explicit multi-row targets, deterministic ordering, target-drift diagnostics,
FAQ classifications, unsupported executable-change diagnostics, patched source
artifact hashes, and CLI tooling for canonicalizing and applying transition
patches. Text replacement and append operations rerun HTML sanitization,
structured source-text normalization, and parsed-token generation before later
catalog work consumes patched artifacts, and engine runtime is statically
blocked from importing the patch tooling module.

**Phase 17B is complete** for canonical 11th Edition catalog generation from
patched source data. The catalog builder consumes normalized source artifacts,
emits deterministic `CanonicalCatalogPackage` payloads, preserves stable
datasheet/model/wargear/faction/detachment/enhancement/stratagem records,
requires accepted physical model geometry and representative height evidence for
every unique model profile, blocks physical geometry consumption for `Use
model`, blank, `No official base size`, bare `Hull`, Base Size Guide
`hull`/`unique`, and unresolved non-circular or non-oval rows without explicit
overrides, and records canonical geometry units, source units, coordinate
frames, origins, support bases, z-offsets, and evidence inside package hashes.
Phase 17J adds Event Companion Base Size Guide source import so these rows are
available for roster/event legality while remaining unresolved for movement,
line of sight, engagement, deployment, and collision until accepted project
geometry evidence exists.

**Phase 17C is complete** for the rule-language intermediate representation.
Normalized `RuleSourceText` now compiles through deterministic source/tooling
entrypoints into versioned `RuleIR` payloads with source spans, reusable language
template IDs, typed trigger/condition/target/effect/duration components, stable
IR hashes, explicit unsupported diagnostics, and a static runtime boundary that
blocks engine imports of the parser/compiler/template tooling. The initial
language templates cover keyword gates, timing windows, distance predicates,
selected targets, dice-roll modifiers, rerolls, characteristic and movement
modifiers, CP/VP changes, ability and weapon-ability grants, placement
permission/restriction clauses, Aura clauses, destruction triggers, and
once-per-scope restrictions.

**Phase 17D is complete** for generic rule execution handlers. Compiled
`RuleIR` clauses now execute through `RuleExecutionRegistry` bindings for
generic modifiers, reroll permissions, VP and CP resource changes, Stratagem
target binding, and Aura evaluation. Runtime execution is fail-closed for
unsupported IR, emits deterministic source-linked events, mutates VP/CP ledgers
through existing engine-owned primitives, records representable persisting
effects through the Phase 12A effect model, and provides generic compiled-IR
bridges for ability and Stratagem handlers without importing Phase 17C
parser/compiler/template tooling.

**Phase 17E is complete** for source-backed faction, detachment, enhancement,
Stratagem, army-rule, and unit-intake coverage. The
`gw-11e-phase17e-faction-coverage-2026-27` package validates all 28 official
faction-pack PDF manifest records, source-links every seeded faction and
detachment row, emits deterministic JSON-safe coverage rows, and groups the
report into implemented, generic-supported, named-handler-required, and
unsupported buckets. Army and detachment rules are represented as source-linked
named-handler-required rows; exact datasheet-intake rows, enhancement subrows,
and Stratagem subrows missing from the update PDFs are blocked as approved
unsupported diagnostics until native generated source rows land in later Phase
17 work. Runtime code does not parse raw PDFs or raw rule text.

**Phase 17F is complete** for faction execution dispatch and status across all
Phase 17E coverage rows. The
`gw-11e-phase17f-faction-execution-2026-27` package maps every coverage
descriptor to an execution record, and `engine/faction_rule_execution.py`
provides one deterministic engine dispatcher for those records. Current rows
without native structured semantics return typed unsupported results with
approved reasons instead of missing handlers, silent no-ops, or runtime PDF/text
parsing; future native descriptors can replace those blocked execution statuses
with generic IR or named handlers without changing the dispatch contract.
Executable statuses still fail closed unless a registered generic IR executor or
named handler actually runs, so APPLIED is never produced by status alone.
Phase 17F is not semantic execution for those faction rules; that engine support
is planned explicitly in Phase 17G.

Completed / implemented foundation:

| Phase | Status | Purpose |
|---|---:|---|
| 0 | Complete | Governance, linting, tests, import boundaries |
| 1 | Complete | Dice and deterministic randomness |
| 2 | Complete | Attributes and modifiers |
| 3 | Complete | Rule-text normalization boundary |
| 4 | Complete | Wargear and weapon profile foundations |
| 5 | Complete | Model pose/base/volume geometry foundations |
| 6 | Complete | Units and attached-unit terminology |
| 7 | Complete | Initial 2.5D visibility/pathing core |
| 8 | Complete | Battlefield/objective descriptors |
| 8B | Complete | Ruleset compatibility descriptors |
| 8C | Complete | Distance predicate tokens |
| 8D | Complete | Weapon ability descriptors |
| 9 | Complete | Decision system |
| 9A | Complete | Catalog, provenance, sequence descriptors |
| 9B | Complete | Authoritative lifecycle |
| 9C | Complete | Army mustering and runtime instantiation |
| 9D | Complete | Pre-Phase-10 smoke gate |
| 10A | Complete | Battlefield placement bridge |
| 10B | Complete | Movement phase entry and unit selection |
| 10C | Complete | Movement phase action and Normal Move vertical slice |
| 10D | Complete | Battlefield transition records |
| 10E | Complete | Model geometry foundation |
| 10F | Complete | Terrain factory foundation |
| 10G | Complete | Movement legality context and capability resolver |
| 10H | Complete | Pathing smoke constraints and coherency descriptor correction |
| 10I | Complete | Terrain movement semantics and endpoint support |
| 10J | Complete | Core dice, roll-off, reroll, random-characteristic, and modifier order semantics |
| 10J.1 | Complete | Measurement predicates and characteristic modifier bounds |
| 10K | Complete | Precise movement distance, straight-line segments, and free rotations |
| 10L | Complete | Unit coherency runtime validation and movement rollback |
| 10M | Complete | Engagement-aware Movement action options and Normal Move finalization |
| 10N | Complete | Advance action, dice, rerolls, and advanced-state restrictions |
| 10O | Complete | Fall Back action and Desperate Escape resolution |
| 10P | Complete | Ingress Moves, Strategic Reserves, Deep Strike, and reserve placement |
| 10Q | Complete | Transport Embark/Disembark, Firing Deck, and destroyed transport emergency disembark |
| 10R | Complete | Aircraft and Hover movement/reserve behavior |
| 10S | Complete | Triggered and surge movement foundation |
| 10T | Complete | Movement phase completion gate |
| 10U | Complete | Movement/pathing/terrain profiling and hotspot budget gate |
| 10V | Complete | Movement audit hardening and deferred-wiring contracts |
| 11A | Complete | Chapter Approved 2026-27 mission pack data |
| 11B | Complete | Objective control geometry and mission objective model |
| 11C | Complete | Command phase body: Command step, CP, Battle-shock, and OC updates |
| 11D | Complete | Adapter scaffold and parameterized movement/placement proposal requests |
| 11E | Complete | Mission actions, primary/secondary scoring, and end-of-turn cleanup |
| 11F | Complete | Battle-round/game-end scoring windows, VP caps, final audit, and winner determination |
| 12A | Complete | Timing windows, reaction queue, sequencing, and persisting effects |
| 12B | Complete | Command Point ledger and Stratagem framework |
| 12C | Complete | Phase-12-resolvable Core Stratagems |
| 12D | Complete | Ability handler registry and keyword-gated rule execution |
| 13A | Complete | Terrain visibility, line of sight, and cover foundation |
| 13B | Complete | Shooting phase target selection and weapon declaration |
| 13C | Complete | Attack sequence, allocation, saves, damage, and typed attack events |
| 13D | Complete | Weapon abilities, shooting/fight modifiers, and shooting Stratagems |
| 13E | Complete | Damage allocation, destroyed models, and destruction reactions |
| 13F | Complete | Shooting phase completion gate |
| 14A | Complete | Source identity and migration audit |
| 14B | Complete | Timing windows, active player, and phase skeleton cutover |
| 14C | Complete | Shared primitives cutover |
| 14D | Complete | Movement, terrain, objectives, and actions cutover |
| 14E | Complete | Attack sequence and allocation cutover, including grouped-host weapon abilities plus melee Cleave/Lance execution |
| 14F | Complete | Shooting-type cutover with finite shooting-type selection and supported grouped attack resolution |
| 14G | Complete | Charge/Fight source contract for Phase 15 implementation |
| 14H | Complete | Advanced transport, attached-unit attack/healing projection, reserve/repositioning, and aircraft cutover |
| 14I | Complete | Core Stratagem and core ability source-contract closeout with explicit unsupported descriptors |
| 14J | Complete | Mission/catalog replacement slice with Force Dispositions, Primary Mission matrix source tracking, and Tactical Secondary score/retain decisions |
| 14K | Complete | Cutover hardening/static audits, damage model allocation choice hardening, aircraft minimum-move retirement, and reserve-arrival policy cutover |
| 14L | Complete | Ranged Select Enemy Unit and Gather Attack Dice layer with identical-attack grouping |
| 15A | Complete | Charge phase declaration, deterministic Charge roll, and reachable-target snapshot |
| 15B | Complete | Charge Move proposal, terrain/pathing/coherency validation, endpoint rules, displacements, and Fights First |
| 15C | Complete | Fight phase skeleton, first-class `FightOrderState`, Fights First/Remaining Combats loop, activation/pass/interrupt decisions, and Normal/Overrun fight-type filtering |
| 15D | Complete | Pile In/Consolidate proposals, fight movement validation, melee declarations, split melee attack pools, and shared attack-sequence reuse |
| 15E | Complete | Source-backed Heroic Intervention, Counteroffensive, Crushing Impact, and Epic Challenge through shared Stratagem/Charge/Fight decisions |
| 15F | Complete | Charge/Fight completion gates, full phase completion coverage, Fight damage/removal draining, and deterministic fight-order hardening |
| 16A | Complete | Source-backed Deploy Armies, deployment-zone placement proposals, `INFILTRATORS`, attached rules-unit deployment, reserves exclusion, and replay-safe setup placement |
| 16B | Complete | Redeployments, Scouts duplicate-distance resolution, Scout reserve setup, Scout Move proposals, Dedicated Transport Scout Move eligibility, and replay-safe pre-battle action records |
| 16C | Complete | Reserve declaration decisions, Strategic Reserves cap enforcement, Deep Strike setup declarations, AIRCRAFT mandatory reserves, and source-backed reserve payloads |
| 16D | Complete | Army construction completion and runtime instantiation |
| 16E | Complete | Setup completion gate, readiness diagnostics, battle-start checkpoints, and bridge-free battle entry |
| 17A | Complete | Bridge Wahapedia source mirror, HTML sanitization, deterministic CSV-to-JSON ETL, source manifests, and grouped import diagnostics |
| 17A.1 | Complete | Official 11th Edition transition patch packages, deterministic patched artifacts, target diagnostics, and FAQ classification |
| 17B | Complete | Canonical 11th Edition catalog generation, geometry evidence, model-height records, and deterministic package hashes |
| 17C | Complete | Rule-language IR, reusable templates, source-spanned unsupported diagnostics, and runtime parser/compiler boundary |
| 17D | Complete | Generic RuleIR execution handlers, source-linked events, Aura recomputation, and ability/Stratagem IR bridges |
| 17E | Complete | All-faction PDF manifest validation, faction/detachment coverage rows, named-handler gates, and approved unsupported diagnostics |
| 17F | Complete | Faction execution dispatch and typed execution status for every Phase 17E coverage row |
| 17J | Complete | Warhammer Event Companion v1.0 source package, mission sequence, Tactical/Fixed Secondary procedure, all 45 layout source-page identities with pending coordinate extraction, FAQ patches, Base Size Guide source rows, and setup/scoring compliance hardening |

Next / planned sequence:

| Phase | Status | Purpose |
|---|---:|---|
| 17G | Planned | Faction army-rule, detachment-rule, enhancement-effect, and faction/detachment Stratagem semantic execution |
| 17H | Planned | Datasheet, wargear, weapon ability, generated source-row coverage, and execution for covered ability items |
| 17I | Planned | Source-content coverage, execution-status audit, and unsupported-descriptor audit |
| 18A-18D | Planned | Human UI, replay inspection, local visual UI, and network play |
| 19A-19E | Planned | Profiling, AI orchestration, self-play, and training corpus generation |
| 20A-20D | Planned | Full-game coverage, regression, soak, and release gates |

## Cross-cutting architectural rules

1. **No runtime raw text parsing.** Raw rule text is normalized, parsed, and compiled at ingest/authoring time into typed descriptors or explicit unsupported descriptors.
2. **No silent fallbacks.** If a rule, terrain shape, ability, or decision cannot be represented safely, emit typed unsupported state.
3. **No UI-owned state mutation.** CLI, local UI, network UI, and AI policies answer `DecisionRequest`s; the engine validates and mutates authoritative state.
4. **No ad hoc content facts.** Datasheet stats, keywords, wargear, base sizes, model footprint geometry, representative model heights, factions, detachments, enhancements, Stratagems, missions, deployment maps, and terrain layouts come from catalog/source packages.
5. **No broad imports from CORE V1.** CORE V1 is a reference for invariants, algorithms, edge cases, and tests. Port only the smallest needed behavior.
6. **Every state change is replay-facing.** Dice, decisions, placement/removal/displacement, scoring, CP changes, Battle-shock, Stratagem use, attack resolution, model destruction, and mission actions must serialize deterministically.
7. **Headless performance is a product requirement.** The engine must support fast large-corpus self-play for hierarchical AI orchestration.

## CORE V1 investigation and reuse policy

CORE V1 is the previous implementation at <https://github.com/SobolGaming/Warhammer40k_AI>. For every future phase:

1. Inspect only the CORE V1 areas named in that phase.
2. Name the invariant being preserved.
3. Write CORE V2 tests before porting behavior.
4. Port the smallest necessary algorithm, transform, or edge-case rule.
5. Replace raw object/string behavior with typed descriptors, payloads, and records.
6. Remove permissive fallbacks.
7. Add replay/audit coverage for state-changing behavior.

---

# 11th Edition Core Rules audit coverage

This section records the source audit against the 11th Edition Core Rules PDF. It exists because missing a foundational rule, such as the attack-allocation order or the free-rotation movement rule, can corrupt every later phase that consumes dice, attacks, movement, visibility, scoring, replay, or adapter decisions.

Rules audited against the 11th Edition PDF are assigned to explicit roadmap owners below. If a phase implements a mechanic that depends on one of these rules, it must either consume the owning phase's typed service or fail explicitly until that service exists.

| Core Rules area | Required roadmap owner |
|---|---|
| D3 conversion, multi-dice expressions, roll-offs, reroll order, one-reroll-per-die, unmodified result semantics | Phase 10J |
| Distance predicates including within, wholly within, more than, horizontal-only reserve distances, closest-points measurement, base-as-part-of-model visibility, `FRAME` measurement, and objective-marker range | Phase 10J.1, 13A, 16A, 14C |
| Characteristic post-modifier caps/floors for Move, Toughness, Save, Invulnerable Save, Leadership, Objective Control, Detection Range, Range, Attacks, WS, BS, Strength, AP, and Damage, including modifier-eligible `0`, modifier-immune `-`, Battle-shocked OC replacement, and half-damage applied after other Damage modifiers | Phase 10J.1, 11C, 13C, 17B, 14C |
| Roll-offs for mission/setup/sequencing, including no rerolls or modifiers and repeat ties | Phase 10J, 12A, 16A |
| Active/opposing player state, including start/end battle-round defaults and selected unit control during move/shoot/fight resolution | Phase 9B, 12A, 14B |
| Start/end battle round, start/end turn, and start/end phase timing windows, including non-mission rules before mission rules at end-of-turn/end-of-phase/end-of-round windows | Phase 9B, 11E, 11F, 12A, 14B |
| Persisting effects through Embark/Disembark, repositioned units, transport destruction, Attached-unit source destruction, and revival | Phase 12A, 12D, 16D, 14H |
| Out-of-phase actions: perform only the specified action and do not trigger other rules normally used in that phase | Phase 12A, 12C, 12D |
| Starting Strength, Below Half-strength, At Half-strength, Battle-shock persistence/recovery, CP gain, Battle-shocked restrictions, and appendix handling for units that cannot be exactly half-strength | Phase 11C, 14C |
| Moving core: straight-line distance, free rotations, no pivot costs, per-model Move budgets when a unit has mixed Move characteristics, Set Up rollback, model overlap/surface checks, and end-of-turn coherency cleanup without destroyed-model triggers | Phase 10A-10T, 11E, 14C, 14D |
| Unit coherency and engagement: 2"/5" engagement range, one-neighbor coherency plus 9"/5" max-spread coherency across every model | Phase 10G, 10L, 10M, 10N, 10O, 15A-15D, 14C |
| Making attacks: ranged weapon selection, ranged Select Enemy Unit, ranged identical-attack aggregation, melee one-weapon selection plus `[EXTRA ATTACKS]`, target eligibility, and declared melee attack splitting across multiple engaged targets | Phase 13B, 13C, 13D, 14E, 14L, 15D |
| Attack sequence: sequential full weapon-ability host plus grouped fixed-damage hit/wound/save-before-allocation/damage host, mandatory Invulnerable Save precedence, defender ordered allocation decisions, low-to-high failed-save resolution, and current group transitions | Phase 13C, 13E, 14E |
| Attack sequence 11th Edition allocation host: save-before-allocation batching, allocation groups, defender ordered allocation decision, save resolution from lowest to highest result, current allocation group transitions, and damage allocation to wounded models first | Phase 14E |
| Mortal wounds, normal-damage-before-mortal ordering, hazard rolls as unit-level rolls that allocate through mortal-wound rules, and `[DEVASTATING WOUNDS]` mortal-wound cap of one destroyed model per critical wound | Phase 13C, 13D, 13E, 14C, 14E |
| Visibility: 1 mm line of sight, visible vs fully visible model/unit states, same-unit model ignoring, and `FRAME` closest-point visibility/measurement | Phase 13A, 14C, 14D |
| Terrain: terrain areas, exposed/light/dense categories, dense movement gates, vertical movement, stable non-ground-level endpoints, Solid 3" ground-level line-of-sight blocking, Hidden using model-level terrain-area occupancy and unit Detection Range, Gone to Ground detection modifier, Obscuring terrain areas, Benefit of Cover as `-1 BS`, and Plunging Fire as `+1 BS` | Phase 10F, 10I, 13A, 13C, 14D, 14E |
| Objectives: terrain objectives as primary objective representation, marker fallback only when no terrain area coincides, objective markers can be moved through and ended on, terrain-area containment for derived terrain objectives, secured-objective persistence and timing | Phase 11A, 11B, 11C, 14D, 14E |
| Movement phase: every army unit is selected to move each Movement phase, including strategic reserves and embarked units; Ingress/reserve arrival is a move type inside Move Units, not a separate phase step; move type is a finite decision; Remain Stationary does not trigger start/end move rules | Phase 10B-10T, 14D |
| Fall Back: Ordered Retreat vs Desperate Escape modes, hazard rolls for Desperate Escape, enemy-model traversal, post-move Battle-shock roll, and shooting/charge/action restrictions | Phase 10O, 11C, 14D |
| Shooting phase: Normal, Assault, Close-quarters, Indirect, and Snap shooting-type cutover through finite shooting-type selection, declaration, grouped attacks, saves, and damage; close-quarters engaged targeting and weapon-selection restrictions; Indirect cover/no-reroll enforcement and fail ranges; engaged MONSTER/VEHICLE targeting; `[BLAST]` engaged-target bans; Assault/Advanced weapon gating; Fire Overwatch/Snap routing | Phase 13B-13F, 14F |
| Charge phase: charge eligibility, charge-target declaration after the roll, target-within-roll-distance validation, within-1" and engaged-if-possible model movement clauses, all-target engagement requirement, non-target engagement ban, and Fights First grant | Phase 15A, 15B, 14G |
| Fight phase: Start, Pile In, Fight, Consolidate, and End steps; both-player pile-in step; Fights First and Remaining Combats alternating selection; eligible-to-fight if not already selected and charged this turn, engaged now, or engaged at the start of the Fight step; explicit Normal Fight and Overrun Fight selection; eligible-to-fight pass rule when all eligible units are more than 5" from enemies; both-player consolidation step; and Ongoing/Engaging/Objective consolidation modes | Phase 15C, 15D, 14G |
| Actions: start eligibility exclusions, including Battle-shocked units and units that shot earlier in the current Shooting phase; TITANIC exceptions, action-imposed shooting/charge restrictions, cancellation by moves except pile-in/consolidation, cancellation on leaving battlefield, and completion effects | Phase 11E, 17C-17D, 14D, 14F |
| Stratagem framework: same stratagem once per phase, same unit targeted by at most one stratagem per phase unless stated, optional additional CP sections, and source-backed 11th Edition Core Stratagem definitions | Phase 12B, 12C, 12D, 14I |
| Core Stratagems: Command Re-roll partial-die semantics and no Leadership/Battle-shock coverage, Epic Challenge, Insane Bravery, New Orders, Explosives, Crushing Impact, Rapid Ingress, Fire Overwatch via Snap Shooting at end of opponent's Movement phase, Smokescreen, Heroic Intervention modes, and Counteroffensive | Phase 12B, 12C, 13D, 15E, 14I |
| Monsters/Vehicles and `FRAME`: normal/advance-only movement through non-MONSTER/non-VEHICLE friendly/enemy models, frame measurement/rotation, shooting at engaged MONSTER/VEHICLE units, and close-quarters exceptions | Phase 10G, 10I, 13B, 14C, 14F |
| Transports: capacity by models, multiple embarked units, battle-formation embark, post-move Embark with setup-this-turn and datasheet-capacity gates, Rapid/Tactical/Combat Disembark modes including ingress restriction inheritance and Combat hazards/engagement permissions, Emergency Disembark closest-possible setup, and destroyed-transport timing with Deadly Demise | Phase 10Q, 13E, 16C, 14H |
| Attached units: Leader and Support components, one Leader and one Support per bodyguard unless stated, bodyguard Toughness for attacks, destroyed-unit trigger identity, keyword union without model keyword inheritance, source-scoped ability persistence, and revive into attached unit | Phase 6, 13C, 13E, 16D, 17H, 14H |
| Strategic Reserves and repositioned units: 50% points cap, no Fortifications, second-round ingress, 6" battlefield-edge setup, more-than-8" enemy distance, pre-third-round opponent-deployment-zone ban, third-round destruction exceptions, and move-history/effect persistence for repositioned units | Phase 10P, 11F, 16C, 14H |
| Flying, Surge, and Aircraft: surge target selection and no-repeat-move restriction, optional `take to the skies` declaration with `-2"` budget unless Hover, FLY through all models/terrain and ignores vertical distance, Aircraft-only ingress, end-of-opponent-turn reserve transition, Aircraft engagement exceptions, and aircraft charge/fight restrictions | Phase 10R, 10S, 15B, 15D, 14D, 14H |
| Core abilities and weapon abilities: conditional keyword gates, duplicate ability instance selection for implemented families, `[ANTI]` including duplicate Shooting selection, `[ASSAULT]`, `[BLAST]`, `[CLEAVE]`, `[CLOSE-QUARTERS]`/`[PISTOL]`, Deadly Demise, Deep Strike, `[EXTRA ATTACKS]`, Feel No Pain, Fights First, Firing Deck, `[HAZARDOUS]`, `[HEAVY]` movement-evidence slice, Hover, `[HUNTER X]`, `[IGNORES COVER]`, `[INDIRECT FIRE]`, Infiltrators, `[LANCE]`, Leader, `[LETHAL HITS]` optional auto-wound, Lone Operative default 12" targeting gate, `[MELTA]`, `[ONE SHOT]`, `[PRECISION]`, `[PSYCHIC]`, `[RAPID FIRE]`, Scouts, Stealth, Support, Super-heavy Walker, `[SUSTAINED HITS]`, `[TORRENT]`, and `[TWIN-LINKED]` | Phase 13D, 17C-17H, 14I |
| Appendix and digital rules: adding a new unit, destroyed-model timing, destroyed models unable to use abilities, different Move characteristics, eligible-to-fight pass, mixed keywords, marker fallback objectives, healing/revived models including fully destroyed Bodyguard revival in attached units, and FAQs covering no-ranged-weapon shooting eligibility, engaged `[BLAST]` bans, overrun-fight eligibility, and scout-move embark ban | Phase 9C, 10K, 11B, 13E, 15C, 16B-16D, 17H, 14H |
| Muster army restrictions: battle size, roster order, faction, detachment points, detachment rules, unit/enhancement limits, Leader/Support attachment declarations on the army list, Enhancement assignment after attached units, Warlord faction-keyword requirement, Epic Heroes, and Dedicated Transport occupancy | Phase 16D, 14J |
| Mission deck and scoring: Event Companion Secondary mode selection, Fixed card binding, Tactical draw/discard/CP procedure, mission-card scoring grammar, Primary/Secondary/Battle Ready VP caps, five-round game end, tabled-player continuation, and final victor audit | Phase 11A, 11E, 11F, 12C, 14J, 17J |
| Mission setup order, attacker/defender, battle formations secrecy/public reveal, terrain/objective/deployment maps, first-turn-conditioned pre-battle rules, and Event Companion A/B/C layout selection | Phase 11A, 16A, 16C, 16E, 17J |

# Build order details

## Phase 10J: core dice, roll-off, reroll, random-characteristic, and modifier order semantics

Status: Complete.

This phase makes the Core Rules dice semantics explicit before Advance, Battle-shock, attacks, charges, Stratagems, faction abilities, or mission setup consume dice. Phase 1 established deterministic dice plumbing; this phase adds rules-compliant reroll, roll-off, D3, random-characteristic, and modifier-order state.

Modules:

- `engine/dice.py`
- `core/rng.py`
- `core/modifiers.py`
- `engine/decision_controller.py`
- `engine/decision_record.py`

Objects:

- `DiceRollExpression`
- `DiceRollInstance`
- `DiceRollComponent`
- `D3RollResult`
- `RollOffRequest`
- `RollOffResult`
- `RerollPermission`
- `RerollDecisionRequest`
- `RerollSelection`
- `RerollRecord`
- `ModifiedRollResult`
- `UnmodifiedRollResult`
- `RandomCharacteristicRoll`

Invariants:

- D3 rolls are represented as D6 rolls halved and rounded up, with both source D6 and final D3 result recorded;
- roll-offs roll one D6 per player, repeat on ties, and can never be rerolled or modified;
- roll-off records are replay-facing and identify the decision they resolve, such as mission choice, attacker/defender, sequencing, or battlefield/objective setup;
- a reroll is a replay-facing decision or deterministic auto-decision, never a hidden mutation of a prior roll;
- each physical/logical die component can be rerolled at most once;
- if a rule allows rerolling a dice roll made by adding several dice together, such as 2D6 or 3D6, all dice in that roll must be rerolled unless the rule explicitly permits partial rerolls;
- rules that permit rerolling some dice must identify exactly which die components may be rerolled;
- rerolls happen before modifiers are applied;
- an unmodified roll value means the post-reroll result before modifiers;
- modifier application consumes `UnmodifiedRollResult` and produces `ModifiedRollResult`;
- random Move characteristics are rolled once for the whole unit when selected to move;
- other random characteristics are rolled per model, per weapon, or per use when required by the rule/characteristic descriptor;
- reroll permissions carry source IDs, timing window, owning player, eligible roll type, and legal component-selection policy;
- replay payloads preserve original dice, selected reroll components, rerolled dice, final unmodified value, modifiers, and final modified value;
- attempts to reroll a die twice fail explicitly;
- attempts to partially reroll a multi-dice roll without explicit partial permission fail explicitly.

Required tests:

- D3 records source D6 and rounded-up result;
- roll-off ties repeat until there is a winner;
- roll-offs reject reroll and modifier attempts;
- single D6 reroll records original die, rerolled die, and final unmodified value;
- 2D6 charge-style reroll rerolls both dice by default;
- partial reroll of a multi-dice roll fails unless the permission explicitly allows component selection;
- no die can be rerolled twice;
- modifiers apply after rerolls;
- unmodified result equals post-reroll, pre-modifier value;
- random Move characteristic is rolled once for the whole moving unit;
- random Attacks/Damage characteristics can be rolled at the required per-weapon/per-attack timing;
- reroll permission source IDs round-trip;
- replay load rejects reroll record drift;
- same seed and same reroll decisions reproduce identical final results.

CORE V1 relevant areas:

- `src/warhammer40k_ai/utility/dice.py`
- `src/warhammer40k_ai/engine/dice_rolls.py`
- `src/warhammer40k_ai/engine/roll_handlers.py`
- reroll, command reroll, charge roll, Battle-shock, random characteristic, and attack-sequence tests

## Phase 10J.1: measurement predicates and characteristic modifier bounds

Status: Complete.

This phase completes the core numeric rules that many later phases rely on: distance predicate interpretation, closest-point measurement, horizontal-only reserve distances, wholly-within placement checks, and post-modifier characteristic caps/floors.

Modules:

- `rules/parsed_tokens.py`
- `geometry/measurement.py`
- `core/attributes.py`
- `core/modifiers.py`

Objects:

- `DistanceMeasurementContext`
- `DistancePredicateEvaluator`
- `WithinPredicate`
- `WhollyWithinPredicate`
- `HorizontalDistancePredicate`
- `CharacteristicBoundPolicy`
- `BoundedCharacteristicValue`

Invariants:

- distance between models measures closest points of bases, or closest part of a baseless model where required;
- bases are part of models for visibility and measurement unless a more specific rule says otherwise;
- `within` means not more than the specified distance;
- `wholly within` requires the entire base/contact footprint to satisfy the predicate;
- reserve and set-up rules that specify distance from enemy models use horizontal distance where the Core Rules say so;
- objective marker range is 3" horizontal and 5" vertical unless mission policy overrides it;
- objective markers are 40mm markers by default, can be moved over as if not
  there, and can be ended on top of;
- characteristics depicted as `-`, or replaced by `-` by a rule such as
  Battle-shock replacing OC, are not numeric values and cannot be changed by
  numeric modifiers;
- characteristics with numeric value `0` remain numeric and can be changed by
  modifiers such as auras unless that characteristic's own cap/floor forbids the
  final value;
- Detection Range is a unit characteristic, defaults to 15", and is better when
  lower because it means the unit is detected from a shorter distance;
- post-modifier Move and Toughness cannot be less than 1;
- Save cannot become 1+ or better;
- Leadership cannot become better than 4+ or worse than 9+;
- Objective Control cannot be less than 0;
- ranged weapon Range, Attacks, Strength, and Damage cannot be less than 1 unless a rule explicitly permits Damage 0;
- halve-damage effects are applied after additive, subtractive, replacement, and
  other Damage modifiers, so the halving consumes the already-modified Damage
  value;
- WS and BS cannot become 1+ or better;
- AP cannot become worse than 0;
- all caps/floors are applied after modifier stacking and before result consumption.

Required tests:

- closest-base distance and baseless-model distance work;
- within, wholly within, more-than, and horizontal-only predicates evaluate correctly;
- objective marker range/control predicates use 3"/5";
- objective marker endpoint overlap is allowed and does not block otherwise legal
  movement or placement;
- each characteristic cap/floor is enforced after modifiers;
- numeric `0` can be modified while `-` cannot be modified;
- Battle-shocked OC becomes typed `-`, not numeric 0, and rejects OC modifier effects;
- Detection Range defaults to 15", accepts modifier stacks, and treats lower
  values as better for Hidden detection;
- halve-damage effects apply after other Damage modifiers;
- Damage can become 0 only when an explicit rule permits it;
- distance predicate payloads round-trip without object reprs.

CORE V1 relevant areas:

- `src/warhammer40k_ai/utility/calcs.py`
- distance predicate tests
- objective marker / deployment / reserve placement tests

## Phase 10K: precise movement distance, straight-line segments, and free rotations

Status: Complete.

This phase owns movement-distance accounting. Under the 11th Edition rules, distance is paid for straight-line model movement only; rotating a model any amount around the centre of its base or frame axis does not count toward the distance moved. Any existing pivot-cost policy is retired migration debt and must be removed or made unreachable by Phase 14C.

Modules:

- `geometry/pathing.py`
- `geometry/movement_envelope.py`
- `engine/phases/movement.py`
- `engine/movement_legality.py`

Objects:

- `MovementDistanceBudget`
- `MovementSegment`
- `MovementDistanceWitness`

Invariants:

- movement distance is measured across straight-line segments;
- straight-line distance is measured from the same point on the base/model at the start and end of each line;
- rotating a based model any amount around the centre of its base is legal movement bookkeeping but costs 0";
- rotating a baseless `FRAME` model any amount around its central axis costs 0";
- movement witnesses may record facing/rotation changes for replay and collision evidence, but must not debit movement distance for those rotations;
- retired pivot-cost descriptors, fixtures, and payload fields must fail static audit once the 11th Edition cutover is complete;
- movement-distance witnesses serialize without object reprs.

Required tests:

- rotating round, oval, rectangular, and baseless `FRAME` models never consumes movement distance;
- straight-line movement still consumes distance from the same point on the base/model;
- mixed straight-line-plus-rotation paths serialize rotation evidence without pivot-cost fields;
- static audit rejects retired pivot-cost policy usage after Phase 14C lands;
- straight-line distance uses same-point measurement semantics;
- movement distance witness round-trips.

CORE V1 relevant areas:

- `src/warhammer40k_ai/pathing/validation.py`
- `src/warhammer40k_ai/pathing/sweep.py`
- `src/warhammer40k_ai/pathing/types.py`
- `src/warhammer40k_ai/movement_distance.py`
- movement distance / rotation tests

## Phase 10L: unit coherency runtime validation and movement rollback

Status: Complete.

This phase applies the 11th Edition coherency policy to battlefield placements and move endpoints.

Modules:

- `engine/unit_coherency.py`
- `engine/battlefield_state.py`
- `engine/phases/movement.py`
- `geometry/pathing.py`

Objects:

- `UnitCoherencyContext`
- `UnitCoherencyResult`
- `UnitCoherencyViolation`
- `MovementRollbackRecord`

Invariants:

- single-model units are coherent;
- every model in a multi-model unit must be within 2" horizontally and 5" vertically of at least one other model in that unit;
- every model in a multi-model unit must be within 9" horizontally and 5" vertically of every other model in that unit;
- units must be set up in coherency;
- units must end any kind of move in coherency;
- if a unit cannot end a move in coherency, that move is invalid and model poses roll back;
- end-of-turn coherency cleanup removes models until coherency is restored, destroys those models, and must not trigger destroyed-model rules;
- coherency validation returns offending model IDs.

Required tests:

- multi-model units require one neighbor per model within 2"/5";
- units fail coherency when any model is more than 9"/5" from any other model in that unit;
- broken coherency identifies offending model IDs;
- end-of-turn coherency cleanup removes the minimum required models without destroyed-rule triggers;
- invalid Normal Move rolls back to previous placement;
- deployment placement outside coherency is rejected;
- coherency result payload round-trips.

CORE V1 relevant areas:

- movement validation/pathing tests;
- setup/deployment placement validation tests;
- coherency-related movement tests.

## Phase 10M: engagement-aware Movement action options and Normal Move finalization

This phase makes `SELECT_MOVEMENT_ACTION` legally conditional and upgrades Normal Move from a vertical slice into a rules-valid Move Units action.

Modules:

- `engine/phases/movement.py`
- `engine/movement_legality.py`
- `geometry/pathing.py`
- `geometry/terrain.py`

Objects:

- `MovementActionAvailabilityContext`
- `MovementActionAvailabilityResult`
- `NormalMoveResolution`

Invariants:

- units outside enemy Engagement Range can be offered Remain Stationary, Normal Move, and Advance;
- units within enemy Engagement Range can be offered Remain Stationary and Fall Back;
- Normal Move cannot be selected by a unit within enemy Engagement Range;
- Normal Move cannot move within enemy Engagement Range unless an explicit rule permits it;
- Normal Move cannot transit enemy model bases unless `FLY` or another explicit capability permits it;
- Normal Move consumes precise distance, free-rotation, terrain, pathing, and coherency validators;
- Normal Move movement-distance witnesses must preserve straight-line segment and rotation evidence without debiting distance for rotations;
- Normal Move cannot end on another model, embedded in a wall/floor/terrain volume without an explicit legal endpoint, outside the battlefield, or out of coherency;
- Normal Move emits displacement records only after all validators pass;
- Advance, Fall Back, Charge, Pile-in, Consolidate, Scout, and triggered movement must consume the same movement-distance and terrain-legality infrastructure instead of implementing independent distance accounting.

Required tests:

- action options outside Engagement Range are Remain Stationary, Normal Move, Advance;
- action options inside Engagement Range are Remain Stationary, Fall Back;
- Normal Move validates pathing, terrain, free rotations, and coherency;
- Normal Move for round, non-round, `VEHICLE`, `MONSTER`, and baseless `FRAME` models never consumes distance for rotation;
- Normal Move replay payload rejects movement-distance witness drift if straight-line segment or rotation evidence is malformed;
- failed Normal Move does not mutate battlefield state;
- successful Normal Move emits displacement records and terminal activation event.

CORE V1 relevant areas:

- `src/warhammer40k_ai/engine/decision_handlers/movement.py`
- `src/warhammer40k_ai/pathing/validation.py`
- `src/warhammer40k_ai/pathing/rules_profile.py`

## Phase 10N: Advance action, dice, rerolls, and advanced-state restrictions

Status: Complete.

Modules:

- `engine/phases/movement.py`
- `engine/dice.py`
- `engine/decision_controller.py`
- `engine/movement_legality.py`

Objects:

- `AdvanceRollRequest`
- `AdvanceRollResult`
- `MovementDiceRecord`
- `AdvancedUnitState`

Invariants:

- Advance is available only to eligible units outside enemy Engagement Range;
- selecting Advance emits a deterministic D6 roll request;
- rerolls are explicit `DecisionRequest`s when a legal reroll source exists;
- each model may move up to Movement + Advance roll;
- no model can be moved within enemy Engagement Range unless an explicit rule permits it;
- `FLY` rules apply to enemy model and Engagement Range transit;
- Advance consumes terrain, free-rotation, pathing, and coherency validators;
- a unit that Advanced cannot shoot or declare a charge that turn unless a rule permits it;
- advanced state persists until the correct cleanup point.

Required tests:

- Advance roll is deterministic and replay-facing;
- Advance movement consumes Movement + D6;
- reroll appears only with a legal reroll source;
- Advance emits displacement records;
- advanced unit cannot be selected again that Movement phase;
- advanced unit is marked unable to shoot/charge by default.

CORE V1 relevant areas:

- `src/warhammer40k_ai/engine/decision_handlers/movement.py`
- `src/warhammer40k_ai/movement_distance.py`
- `src/warhammer40k_ai/utility/dice.py`

## Phase 10O: Fall Back action and Desperate Escape resolution

Status: Complete.

Modules:

- `engine/phases/movement.py`
- `engine/movement_legality.py`
- `engine/dice.py`
- `engine/battlefield_state.py`

Objects:

- `FallBackActionResult`
- `DesperateEscapeRequirement`
- `DesperateEscapeRoll`
- `FellBackUnitState`

Invariants:

- Fall Back is available only to eligible units within enemy Engagement Range;
- Fall Back models move up to M";
- Fall Back can move within enemy Engagement Range but cannot end there;
- if no legal endpoint exists, the unit cannot Fall Back;
- Desperate Escape is a Fall Back mode, and uses one hazard roll for each model in the falling-back unit;
- Battle-shocked units selected to Fall Back must use Desperate Escape;
- failed Desperate Escape hazard rolls allocate mortal wounds through the shared mortal-wound service;
- post-hazard Fall Back endpoint coherency is validated before any battlefield mutation;
- if Desperate Escape destroys every model in the falling-back unit, removal records remain authoritative and no stale `FellBackUnitState` is recorded;
- unresolved Desperate Escape requirements cannot emit Fall Back transition records;
- Desperate Escape allows moved models to move through enemy models;
- units that Fall Back cannot shoot or declare a charge that turn unless a rule permits it;
- destroyed models emit removal records with correct destruction context.

Required tests:

- eligible unit can Fall Back;
- ineligible unit cannot Fall Back;
- endpoint in Engagement Range is rejected;
- Desperate Escape mode creates one hazard roll per model;
- Battle-shocked Fall Back requires Desperate Escape mode;
- failed Desperate Escape hazard rolls allocate mortal wounds;
- survivor coherency is revalidated after Desperate Escape mortal-wound resolution;
- Desperate Escape casualties can make an otherwise incoherent attempted endpoint legal;
- all-model Desperate Escape destruction round-trips through lifecycle replay without stale Fell Back state;
- unresolved Desperate Escape requirements cannot emit transition batches;
- Fall Back emits displacement and removal records where applicable.

CORE V1 relevant areas:

- `src/warhammer40k_ai/engine/decision_handlers/movement.py`
- `src/warhammer40k_ai/pathing/rules_profile.py`
- `src/warhammer40k_ai/pathing/validation.py`

## Phase 10P: Ingress Moves, Strategic Reserves, Deep Strike, and reserve placement

Status: Complete.

Modules:

- `engine/phases/movement.py`
- `engine/reserves.py`
- `engine/battlefield_state.py`
- `engine/placement.py`

Objects:

- `MovementPhaseStepState`
- `ReserveState`
- `StrategicReserveDeclaration`
- `ReserveArrivalCandidate`
- `ReinforcementPlacement`
- `StrategicReserveRule`

Invariants:

- Movement phase has a Move Units step; reserve arrivals are resolved as move types such as Ingress Move selected inside that step;
- `REINFORCEMENTS` is not a separate 11th Edition phase step and remains only a retired migration term;
- reserve placement uses placement records, not displacement records;
- all Reserves units not set up on the battlefield when the battle ends count as destroyed;
- Reserves units set up by an Ingress Move follow the Ingress Move after-moving restrictions and cannot make another type of move until the start of the next Charge phase unless a rule permits it;
- any specified enemy-distance requirement for setting up Reserves applies to horizontal distance unless the source rule says otherwise;
- Strategic Reserves are a subset of Reserves, while Deep Strike and other reserve-like abilities keep their own setup rules;
- Strategic Reserves declarations exclude `FORTIFICATIONS` and enforce the battle-size points limit, including embarked units inside transports placed into Strategic Reserves;
- Strategic Reserves cannot arrive in battle round 1;
- Strategic Reserves arriving in battle round 2 must be wholly within 6" of a battlefield edge and not within the enemy deployment zone;
- Strategic Reserves arriving from battle round 3 onward must be wholly within 6" of a battlefield edge;
- Strategic Reserves cannot be set up within 8" horizontally of enemy units, i.e. they must be more than 8" away;
- Deep Strike units may be placed in Reserves during Declare Battle Formations if every model has Deep Strike;
- each time a Deep Strike unit makes an Ingress Move, if every model in that
  unit has Deep Strike, it can be set up anywhere on the battlefield that is
  more than 8" horizontally from all enemy units, even within the opponent's
  deployment zone;
- a unit arriving from Strategic Reserves with Deep Strike may choose either Strategic Reserves setup rules or Deep Strike setup rules;
- reserve placements validate battlefield edges, enemy distance restrictions, terrain endpoints, coherency, model overlap, and deployment restrictions;
- mandatory arrivals are requeued or fail explicitly according to rules;
- no `PathWitness` is required for placement.

Required tests:

- Movement phase offers legal Ingress Move choices during Move Units;
- Deep Strike Ingress placement uses `BattlefieldPlacementKind.DEEP_STRIKE`;
- Strategic Reserves placement uses `BattlefieldPlacementKind.STRATEGIC_RESERVES`;
- illegal reserve placement fails without mutating state;
- reserve placement validates coherency and Engagement Range setup restriction;
- reserve placement validates terrain endpoint support;
- Strategic Reserves battle-round-2 edge/enemy-deployment-zone/more-than-8" restrictions are enforced;
- Strategic Reserves battle-round-3 edge restrictions are enforced;
- Deep Strike and Strategic Reserves choose the correct placement policy,
  including Deep Strike's permission to ignore opponent-deployment-zone bans
  while preserving the more-than-8" horizontal enemy-distance restriction;
- unarrived Reserves count as destroyed at game end.

CORE V1 relevant areas:

- `src/warhammer40k_ai/engine/reserve_entry_rules.py`
- `src/warhammer40k_ai/engine/decision_handlers/movement.py`
- `src/warhammer40k_ai/engine/game_setup_flow.py`
- reserve, Deep Strike, Strategic Reserves, and battlefield-edge placement tests

## Phase 10Q: transport embark/disembark, Firing Deck, and destroyed transport emergency disembark

Status: Complete foundation; later consumers are explicitly deferred.

Modules:

- `engine/transports.py`
- `engine/phases/movement.py`
- `engine/battlefield_state.py`
- `engine/phases/shooting.py`

Objects:

- `TransportCargoState`
- `EmbarkSelection`
- `DisembarkSelection`
- `FiringDeckSelection`
- `DestroyedTransportDisembark`
- `EmergencyDisembarkationResolution`

Complete foundation scope:

- voluntary Embark/Disembark lifecycle;
- post-Transport-Normal-Move Disembark;
- cargo accounting;
- Firing Deck selection validator;
- destroyed Transport and Emergency Disembarkation resolver.

Deferred consumers:

- destroyed Transport orchestration from actual damage/destruction events is owned by Phase 13E/15D;
- destroyed Transport Battle-shock write-through to `GameState.battle_shocked_unit_ids` is owned by Phase 11C/13E;
- Deadly Demise ordering and the destroyed-Transport ignore interaction are owned by Phase 13E;
- Firing Deck attack-generation consumption, one-weapon-per-embarked-model validation, and transport temporary weapon attachment are owned by Phase 13B.

Invariants:

- Transport capacity is data-driven by datasheet restrictions;
- units can start the battle embarked within a Transport and must declare that before setup;
- Embark is battlefield removal into transport cargo;
- by default, Embark is available only after a unit makes a Normal, Advance, or Fall Back move and every model in that unit ends that move within 3" of a friendly `TRANSPORT` with sufficient capacity;
- Remain Stationary does not satisfy the Core Rules Embark trigger; a zero-distance Normal Move is still represented as a Normal Move;
- by default, a unit that Disembarked from a `TRANSPORT` in the current phase cannot Embark in that same phase; explicit rule overrides must be represented as typed permissions;
- embarked units normally cannot do anything or be affected unless a rule says otherwise;
- Disembark is battlefield placement from transport cargo;
- Phase 10Q's initial Movement lifecycle exposes simple pre-move and post-Transport-Normal-Move Disembark gates; Phase 14H replaces this with the source-backed 11th Edition Rapid, Tactical, Combat, destroyed-Transport, and Emergency Disembark modes;
- Disembark placement must be wholly within 3" of the Transport and not within enemy Engagement Range;
- units disembarking before a stationary/not-yet-moved Transport moves can act normally but cannot choose Remain Stationary;
- units disembarking after a Transport made a Normal move count as having made a Normal move, cannot move further this phase, and cannot declare a charge that turn;
- by default, units cannot Disembark from a `TRANSPORT` that Advanced or Fell Back this turn; explicit rule overrides must be represented as typed permissions;
- destroyed Transport disembark occurs before the Transport model is removed;
- destroyed Transport disembark ignores that Transport's Deadly Demise effect for embarked units;
- destroyed Transport disembark rolls one D6 per disembarking model, inflicting mortal wounds on 1s;
- destroyed Transport disembarking units become Battle-shocked until the start of their controller's next Command phase and count as having made a Normal move/cannot charge that turn;
- Emergency Disembarkation uses 6" instead of 3" and mortal wounds on 1-3 when normal destroyed-transport disembark is impossible;
- any model that still cannot be set up during Emergency Disembarkation is destroyed;
- Firing Deck selects up to X embarked models whose units have not shot, selects one non-One-Shot ranged weapon from each, temporarily equips the Transport with those weapons, and makes those embarked units ineligible to shoot until end of phase.
- Movement lifecycle exposes voluntary pre-move Disembark, post-Transport-Normal-Move Disembark, and post-move Embark through `DecisionRequest` / `DecisionResult`.

Required tests:

- Embark removes placed models and emits removal records;
- embarked unit is unavailable for Movement unit selection;
- Disembark places models and emits placement records;
- post-Transport-Normal-Move Disembark records the passenger as having moved and prevents later Movement activation;
- illegal Disembark fails without mutation;
- disembark-before-move, disembark-after-Normal-move, Advanced/Fell-Back Transport restrictions are enforced;
- destroyed Transport disembark occurs before Transport removal and applies Battle-shock/Normal-move/no-charge state;
- Emergency Disembarkation uses 6" and 1-3 mortal-wound threshold;
- Firing Deck grants temporary weapon profiles to the Transport and marks selected embarked units as having shot/ineligible;
- capacity validation fails explicitly.

CORE V1 relevant areas:

- `src/warhammer40k_ai/engine/decision_handlers/movement.py`
- `tests/rules/test_core_transport_movement_phase.py`
- transport, Firing Deck, destroyed Transport, and emergency disembark tests

## Phase 10R: Aircraft and Hover movement/reserve behavior

Status: Complete foundation; setup-phase declarations are explicitly deferred.

This phase adds typed `AIRCRAFT` movement policy, lifecycle aircraft reserve
transitions, aircraft-aware pathing for other models, and reserve arrival
validation through the same placement legality path used by Phase 10P. The
source-backed `HOVER` ability itself is not a deployment-mode switch; Phase 14I
owns the rule that a `HOVER` unit taking to the skies does not subtract 2" from
its movement budget.

Modules:

- `engine/aircraft.py`
- `engine/game_state.py`
- `engine/phases/movement.py`
- `engine/reserves.py`
- `geometry/pathing.py`

Objects:

- `AircraftMovementPolicy`
- `AircraftReserveTransition`
- `AircraftReserveTransitionReason`
- `HoverModeState`

Complete foundation scope:

- Aircraft movement policy and deferred Hover rule wiring;
- aircraft reserve transitions;
- mandatory Strategic Reserves deployment during battle formation;
- end-of-opponent-turn reserve transition metadata.

Deferred setup consumers:

- Aircraft mandatory reserve declaration during Declare Battle Formations is owned by Phase 16C;
- Hover behavior is now owned by the Flying rules, not an Aircraft deployment-mode choice.

Invariants:

- all `AIRCRAFT` units must start in Strategic Reserves;
- `AIRCRAFT` units are only eligible to make ingress moves and are not eligible for other move types;
- at the end of the opponent's turn, each on-battlefield `AIRCRAFT` unit is placed into Strategic Reserves;
- aircraft reserve transitions remove the unit from the battlefield and serialize deterministic reserve metadata;
- each time any unit makes any type of move, its models can be moved through `AIRCRAFT` models;
- enemy `AIRCRAFT` engagement is tracked separately so non-Aircraft units engaged only by enemy Aircraft can still choose Normal Move or Advance while endpoint validation remains strict;
- unless the moving unit can `FLY`, pile-in, consolidation, and surge target selection ignore `AIRCRAFT` for closest-enemy and enemy-selection purposes;
- Plunging Fire has no effect on attacks made by or targeting `AIRCRAFT`;
- `AIRCRAFT` units are not eligible to declare charges, can only make melee attacks that target `FLYING` units, and only `FLYING` units/models can charge or make melee attacks into `AIRCRAFT`.

Required tests:

- Aircraft battle-formation setup places all Aircraft in Strategic Reserves;
- Aircraft ingress validates Strategic Reserves placement restrictions;
- end-of-opponent-turn Aircraft reserve transition emits removal records and deterministic reserve state;
- Aircraft cannot be selected for Normal, Advance, Fall Back, Charge, pile-in, consolidation, or surge moves unless a later source explicitly overrides the Core Rules;
- replay rejects stale Aircraft reserve-transition payloads;
- non-Aircraft units engaged only by enemy Aircraft can choose Normal Move and Advance, but cannot end within enemy Aircraft Engagement Range;
- non-`FLY` pile-in, consolidation, and surge target selection ignores Aircraft;
- Aircraft Plunging Fire exclusions are enforced;
- Aircraft charge/fight restrictions are exposed and regression-tested.

CORE V1 relevant areas:

- aircraft movement/reserve handling;
- reserve-entry tests;
- movement pathing tests.

## Phase 10S: triggered and surge movement foundation

Status: Complete.

Modules:

- `engine/triggered_movement.py`
- `engine/reaction_windows.py`
- `engine/battlefield_state.py`

Objects:

- `TriggeredMovementDescriptor`
- `TriggeredMovementKind`
- `TriggeredMovementRequest`
- `SurgeMoveState`

Invariants:

- triggered movement is not a Movement phase action;
- surge-like movement is a triggered displacement;
- optional triggered movement can be declined through the same decision path;
- mandatory triggered movement omits decline choices;
- each unit can only make one surge move per phase unless a rule says otherwise;
- Battle-shocked units cannot make surge moves unless a rule says otherwise;
- units within Engagement Range cannot make surge moves unless a rule says otherwise;
- triggered movement records trigger timing and source rule;
- triggered movement consumes pathing, terrain, free-rotation, and coherency validation.

Required tests:

- Blood-Surge-like movement is represented as triggered movement;
- surge movement cannot occur if Battle-shocked;
- surge movement cannot occur while within Engagement Range;
- one surge move per phase is enforced;
- triggered movement emits displacement records;
- declined triggered movement emits a deterministic event without battlefield mutation;
- triggered movement records source rule and trigger timing;
- triggered movement does not appear in `SELECT_MOVEMENT_ACTION`.

CORE V1 relevant areas:

- `src/warhammer40k_ai/engine/decision_handlers/movement.py`
- surge/reactive movement tests.

## Phase 10T: Movement phase completion gate

Status: Complete.

This phase is a compliance gate for the full Movement phase.

Invariants:

- Move Units step completes with all eligible units either moved or remaining stationary;
- action options are Engagement Range-aware;
- failed movement rolls back state;
- all successful movement emits transition records;
- coherency is enforced at the end of every move;
- reserve arrivals are legal Move Units selections rather than a separate Reinforcements step;
- Movement phase advances only after all Move Units choices and unresolved mandatory placements are complete;
- movement phase events and replay payloads are deterministic.

Required tests:

- full Move Units step completes;
- Advance/Fall Back/Normal/Remain Stationary interact correctly;
- failed movement does not mutate state;
- reserve arrival choices occur during Move Units;
- Movement phase exits to Shooting only when all movement-step work is complete.

## Phase 10U: movement/pathing/terrain profiling and hotspot budget gate

Status: Complete.

This phase introduces performance profiling before Shooting/Charge/Fight multiply pathing and LoS costs.

Modules:

- `profiling/`
- `scripts/profile_movement_pathing.py`
- `tests/performance/`

Objects:

- `PerformanceScenario`
- `PerformanceBudget`
- `HotspotReport`
- `PathingBenchmarkResult`

Invariants:

- movement/pathing/terrain benchmark scenarios are deterministic;
- pathing and terrain validation hotspots are profiled before AI self-play scaling;
- benchmarks include crowded infantry, vehicle blockers, ruins, reserve-like placement, and FLY paths;
- performance reports are machine-readable;
- CI can run a small smoke benchmark;
- larger profiling runs are manual or nightly;
- no performance optimization may change deterministic replay payloads.

Required tests / scripts:

- smoke benchmark for pathing validation;
- smoke benchmark for terrain legality;
- hotspot report JSON round-trip;
- same seed and same scenario produce same benchmark result;
- profiling script exits non-zero if a configured budget is exceeded.

CORE V1 relevant areas:

- `docs/PROFILING.md`
- `docs/HEADLESS_SELF_PLAY_RUNBOOK.md`
- `scripts/run_headless_self_play.py`
- `src/warhammer40k_ai/engine/time_manager.py`
- `src/warhammer40k_ai/engine/tier2_orchestrator.py`
- `src/warhammer40k_ai/engine/movement_solver.py`

## Phase 10V: movement audit hardening and deferred-wiring contracts

Status: Complete.

This phase closes immediate movement-audit correctness findings and records explicit owners for rules paths whose resolver foundations exist before their lifecycle consumers.

Modules:

- `engine/movement_legality.py`
- `engine/reserves.py`
- `engine/phases/movement.py`
- `geometry/pathing.py`
- `engine/unit_coherency.py`

Implemented hardening:

- friendly `VEHICLE`/`MONSTER` transit blockers apply only when the moving model is itself a `VEHICLE` or `MONSTER`;
- `FLY` `VEHICLE`/`MONSTER` movers keep their transit exemption when the ruleset permits moving through models;
- endpoint model-overlap prohibition remains universal;
- reserve setup rejects placements within enemy Engagement Range, separately from reserve horizontal-distance restrictions.

Deferred wiring contracts:

- Phase 11A must provide mission deployment-zone geometry to live reserve-arrival validation so battle-round-2 Strategic Reserves pass enemy deployment zones into `resolve_reserve_arrival`;
- Phase 11A/11B must provide instantiated terrain features to live reserve-arrival and deployment placement validation, not only resolver tests;
- Phase 11E/11F must call unarrived-reserve destruction at the appropriate game-end or mission-pack deadline;
- Phase 13B must consume Firing Deck selections during Shooting and validate selected weapons against the embarked model's wargear;
- Phase 13E/15D must orchestrate destroyed Transport disembark from real destruction events before removing the Transport model;
- setup placement validates attached-unit coherency over the attached rules
  unit's model set, and future movement-host broadening must preserve that
  group-aware contract;
- before Charge/Fight movement consumes terrain pathing broadly, FLY air-path distance budgeting and climb counted-distance budgeting must either feed the movement budget or return typed unsupported/invalid results;
- non-`WALKER` `VEHICLE` gap/squeeze restrictions must be represented explicitly before vehicle movement coverage is claimed complete.

Required tests:

- `INFANTRY` can transit through a friendly `VEHICLE`;
- non-`FLY` `VEHICLE` cannot transit through a friendly `VEHICLE`/`MONSTER`;
- `FLY` `VEHICLE` can transit over friendly `VEHICLE`/`MONSTER` blockers when permitted;
- no model can end overlapping another model;
- reserve setup within enemy Engagement Range is invalid even when a separate reserve-distance rule would not reject it;
- code-quality audit keeps friendly `VEHICLE`/`MONSTER` transit gating in movement legality.

---

# Mission pack, objectives, Command phase, and scoring

## Phase 11A: Chapter Approved 2026-27 mission pack data

Status: Complete.

This phase brings in Chapter Approved 2026-27 mission data: mission sequence,
deployment maps, objective marker positions, mission pool, mission decks,
secondary mission cards, Challenger cards, terrain layout templates, and
tournament scoring caps.

Phase 11A terrain layout import has two layers. `core/terrain_layouts.py`
defines pure geometry domain templates, while `rules/mission_pack_import.py`
transcribes the Chapter Approved 2026-27 layout slot table into `layout-1`
through `layout-8`. Each slot preserves the source preset, rotation, and world
origin in terrain feature `source_id` metadata for audit/replay provenance.
Runtime `TerrainFeatureTemplate` geometry intentionally instantiates the
conservative axis-aligned bounding footprint of each rotated slot, with
axis-aligned ruins walls/floors inside that footprint. Exact rotated ruin walls,
floor polygons, and visibility/pathing polygons are deferred to the
terrain/visibility geometry slices rather than treated as complete in Phase 11A.

The UI may map `layout-1` through `layout-8` to thematic `Layout1.png` through
`Layout8.png` artwork, but those PNGs are not authoritative geometry. Engine
visibility, movement, collision, objective, deployment, and reserve-placement
legality must run from the instantiated terrain feature payloads in
`MissionSetup`. Until exact rotated terrain geometry is implemented, any UI
overlay must either visualize those conservative runtime footprints or clearly
avoid presenting the PNG as the engine collision/LoS ground truth.

Modules:

- `rules/mission_pack_import.py`
- `core/missions.py`
- `core/deployment_zones.py`
- `core/terrain_layouts.py`
- `engine/mission_setup.py`

Objects:

- `MissionPackDefinition`
- `ChapterApprovedMissionSequence`
- `DeploymentMapDefinition`
- `ObjectiveMarkerDefinition`
- `TerrainLayoutTemplate`
- `MissionDeckDefinition`
- `PrimaryMissionDefinition`
- `SecondaryMissionDefinition`
- `ChallengerCardDefinition`

Invariants:

- Chapter Approved 2026-27 is source-linked and versioned;
- mission setup order is data, not driver-local enum arithmetic;
- deployment zones are geometry objects tied to deployment maps;
- objective marker positions are source-defined and use center-point measurement;
- Chapter Approved objective markers are flat 40mm markers and do not impede movement/placement;
- terrain layout templates are data and can instantiate pregenerated terrain
  pieces with conservative axis-aligned occupancy footprints;
- Chapter Approved `layout-1` through `layout-8` runtime terrain geometry is the
  instantiated `TerrainLayoutTemplate` data, not the `Layout*.png` artwork used
  by UI presentation;
- source slot rotation/origin provenance is preserved in `source_id`, but until
  exact rotated geometry exists, runtime occupancy/LoS/collision must not infer
  angled footprints from that provenance or from UI images;
- live reserve-arrival validation receives mission deployment-zone geometry for reserve placement validation;
- live placement validators receive instantiated terrain features instead of resolver-local test fixtures;
- tournament mission pool is deterministic and replay-facing;
- Fixed/Tactical/Challenger card behavior remains hidden/public-safe.

Required tests:

- Chapter Approved mission sequence round-trips;
- deployment map geometry round-trips;
- objective marker positions round-trip;
- objective marker terrain/movement policy is flat/non-blocking for Chapter Approved;
- terrain layout template instantiates deterministic terrain features;
- all eight Chapter Approved terrain layouts preserve slot rotation/origin
  provenance in feature `source_id` values while producing deterministic
  conservative runtime footprint payloads;
- UI-facing layout IDs can resolve to artwork, but engine legality tests prove
  pathing, visibility, collision, deployment, reserve placement, and objective
  queries consume `MissionSetup.terrain_features` rather than `Layout*.png`
  dimensions or image-derived polygons;
- live reserve-arrival validation rejects battle-round-2 Strategic Reserves in enemy deployment zones using mission data;
- live reserve-arrival validation rejects illegal terrain endpoints using instantiated terrain layout data;
- mission pool selection is deterministic;
- hidden Tactical/Fixed state does not leak to opponent public payload.

CORE V1 relevant areas:

- mission/deployment map data;
- setup/deployment tests;
- scoring tests;
- terrain layout fixtures.

## Phase 11B: objective control geometry and mission objective model

Status: Complete.

Modules:

- `core/objectives.py`
- `engine/objective_control.py`
- `engine/battlefield_state.py`
- `geometry/spatial_index.py`

Objects:

- `ObjectiveMarker`
- `ObjectiveControlContext`
- `ObjectiveControlResult`
- `ObjectiveControlRecord`

Invariants:

- objective control derives from current placed models and OC values;
- Battle-shocked units have OC `-`, which contributes no Objective Control and cannot be modified by numeric OC modifiers;
- objective markers use mission-defined center positions and default 40mm marker geometry unless a mission overrides it;
- models can move over objective markers and can end a move on top of them;
- objective marker range is 3" horizontally and 5" vertically unless a mission overrides it;
- objective control updates at the end of every phase and turn;
- objective marker terrain interactions are descriptor-driven;
- objective control results are replay-safe.

Required tests:

- objective control sums OC by player;
- Battle-shocked unit contributes no OC because its OC characteristic is `-`;
- contested objective has deterministic result;
- terrain objective policy is explicit unsupported until implemented;
- model can end on top of an objective marker;
- objective control updates at phase and turn end;
- objective control payloads round-trip.

## Phase 11C: Command phase body: Command step, CP, Battle-shock, and OC updates

Status: Complete.

Modules:

- `engine/phases/command.py`
- `engine/battle_shock.py`
- `engine/command_points.py`
- `engine/objective_control.py`
- `engine/unit_state.py`

Objects:

- `CommandStepState`
- `CommandPointLedger`
- `BattleShockTestRequest`
- `BattleShockResult`
- `BelowHalfStrengthContext`
- `StartingStrengthRecord`

Invariants:

- Command phase has Command step then Battle-shock step;
- at the start of each player's Command phase, before other Command rules, both players gain 1CP;
- outside the normal Command-phase CP gain, each player can gain only 1CP per battle round, regardless of source, unless a rule explicitly overrides this;
- below-half-strength units on the battlefield create Battle-shock test requests during the Battle-shock step;
- a Battle-shock test rolls 2D6 and passes if the total is greater than or equal to the best Leadership in that unit;
- non-reroll Battle-shock dice are deterministic engine-internal dice; future reroll or choice hooks must pause through `DecisionRequest` before mutation;
- if a unit is forced to test for being below Starting Strength, it does not also test for being Below Half-strength unless a rule says otherwise;
- failed Battle-shock marks the unit and all its models Battle-shocked until it passes a later recovery roll or another rule clears the state;
- Battle-shocked units have OC `-`, not OC 0, and OC `-` cannot be increased by numeric modifiers;
- Battle-shocked units must use Desperate Escape if selected to Fall Back;
- Battle-shocked units cannot start actions and cannot complete actions already in progress;
- a player cannot use Stratagems to affect their Battle-shocked units unless a rule permits it;
- Starting Strength is recorded at army creation and updated correctly when Attached units split;
- Below Half-strength for single-model units uses remaining wounds less than half the Wounds characteristic; other units use current model count less than half Starting Strength;
- Command phase scoring hooks run at the correct timing.

Required tests:

- both players gain 1CP at the start of each Command phase;
- non-Command CP gain cap of 1CP per battle round is enforced;
- below-half-strength unit emits Battle-shock test request;
- below-Starting-Strength forced test suppresses duplicate Below Half-strength test unless overridden;
- failed Battle-shock persists and changes OC to `-`;
- passed Battle-shock avoids Battle-shocked state;
- Battle-shocked unit cannot be targeted by friendly Stratagems by default;
- Starting Strength and Below Half-strength logic works for single-model and multi-model units;
- Attached-unit split recovery restores surviving component units to their original Starting Strength records;
- Command phase stops at required decision requests and resolves non-reroll Battle-shock dice deterministically without a player-choice pause.

## Phase 11D: adapter scaffold and parameterized movement/placement proposal requests

Status: Complete.

This phase creates the engine-owned contract that allows UI work to proceed in parallel without UI-owned state mutation. It separates finite decision choices, such as selecting a movement action, from parameterized movement and placement proposals, such as per-model endpoints and path witnesses.

This phase does not build a visual UI. It creates the adapter and proposal contracts that a later CLI, local visual UI, network client, or AI policy can consume.

Design note: [Adapter Decision Contract](docs/ADAPTER_DECISION_CONTRACT.md) defines the shared submission path, producer responsibilities, viewer-scoped projections/events, and examples for UI, CLI, headless, network, AI, replay, and test adapters.

Modules:

- `adapters/contracts.py`
- `adapters/projection.py`
- `adapters/decisions.py`
- `adapters/local_session.py`
- `adapters/event_stream.py`
- `engine/decision_request.py`
- `engine/decision_result.py`
- `engine/decision_record.py`
- `engine/lifecycle.py`
- `engine/movement_proposals.py`
- `engine/phases/movement.py`

Objects:

- `GameViewPayload`
- `DecisionRequestViewPayload`
- `DecisionSubmission`
- `FiniteOptionSubmission`
- `ParameterizedSubmission`
- `MovementProposalRequest`
- `MovementProposalPayload`
- `ModelMovementProposalPayload`
- `PlacementProposalPayload`
- `ProposalValidationResult`
- `ProposalViolation`
- `LocalGameSession`
- `EventStreamCursor`

Invariants:

- adapters are leaf modules: `adapters` may import engine/core/geometry/rules payload types, but core, geometry, rules, and engine modules must not import adapters;
- UI, CLI, network, and AI clients submit decisions through engine-owned request/result contracts and never mutate `GameState`, `BattlefieldRuntimeState`, `UnitPlacement`, model poses, objective state, mission state, or event logs directly;
- finite decisions remain finite: unit selection, movement action selection, secondary mission selection, reroll choices, and similar bounded choices continue to use finite `DecisionRequest` options;
- exact movement and placement realization is parameterized, not finite-option enumerated;
- after a finite movement action selection such as `NORMAL_MOVE`, `ADVANCE`, or `FALL_BACK`, the engine can emit a follow-up parameterized proposal request for the selected unit/action;
- parameterized proposal requests carry JSON-safe input contracts rather than precomputed option payloads;
- movement proposal payloads include the selected unit, selected movement action, per-model movement data, path witness data, rotation/facing data where applicable, and any required source context;
- placement proposal payloads include unit/model placement data and placement kind, with enough context for deployment, reserve arrival, Deep Strike, Disembark, redeploy, or later setup/mission placement flows;
- proposal payloads are validated by engine-owned movement, pathing, terrain, placement, coherency, reserve, and transport validators before any state mutation;
- invalid proposals return typed invalid status and diagnostics without mutating authoritative state;
- valid proposals emit ordinary placement, displacement, removal, event, and decision records;
- proposal requests and proposal results are replay-facing and JSON-safe, with no Python object reprs or memory-address payloads;
- existing deterministic bridge behavior may remain available for headless tests or smoke flows, but it must not be the only contract for human movement/placement input;
- unknown or unsupported proposal kinds fail explicitly;
- adapter projections are viewer-scoped and must not leak hidden information;
- adapter projections expose read-only game state, pending decision/proposal views, event-stream deltas, and lifecycle status;
- adapter submission helpers support both finite option submissions and parameterized proposal submissions.

Initial parameterized request coverage:

- Normal Move proposal;
- Advance move proposal after Advance action and dice/reroll resolution;
- Fall Back proposal, including Desperate Escape follow-up decisions where applicable;
- reserve-arrival placement proposal;
- Deep Strike placement proposal;
- Strategic Reserves placement proposal;
- Disembark placement proposal.

Reserve arrival proposal requests use distinct proposal kinds for general reserve
arrival, Deep Strike, and Strategic Reserves flows. The request's
`placement_kinds` field enumerates the legal physical placement methods
available to that reserve state and unit.

Later phases must reuse the same proposal contract for:

- deployment placement;
- redeployment;
- Scout moves;
- charge movement;
- pile-in;
- consolidate;
- mission action placement or movement-like effects where applicable.

Required tests:

- finite `SELECT_MOVEMENT_ACTION` still presents only finite movement action choices;
- selecting `NORMAL_MOVE` can produce a follow-up parameterized movement proposal request;
- selecting `ADVANCE` resolves required dice/reroll flow and then can produce a parameterized movement proposal request;
- selecting `FALL_BACK` can produce a parameterized movement proposal request and preserves Desperate Escape follow-up behavior;
- valid Normal Move proposal mutates battlefield state only through engine validation and emits normal displacement records;
- invalid movement proposal returns typed invalid status and does not mutate battlefield state;
- invalid placement proposal returns typed invalid status and does not mutate battlefield state;
- valid reserve/Deep Strike/Strategic Reserves placement proposal emits placement records;
- valid Disembark placement proposal emits placement records and transport/cargo state updates;
- proposal result payloads round-trip without Python object reprs;
- parameterized proposal decisions produce normal replay-facing records;
- stale proposal submission is rejected if it does not match the current pending request;
- adapter projection exposes public game state for a viewer without leaking hidden opponent information;
- adapter projection exposes pending finite decisions and pending parameterized proposal requests in a UI-readable shape;
- `LocalGameSession.submit_option(...)` handles finite decisions;
- `LocalGameSession.submit_payload(...)` or equivalent handles parameterized proposal decisions;
- event cursor returns deterministic event payloads since a supplied cursor;
- import-boundary tests confirm core, geometry, rules, and engine modules do not import adapters;
- a golden JSON fixture covers the parameterized Normal Move proposal request; inline JSON-shape regressions cover finite movement action selection, invalid movement and placement proposals, reserve placement, Disembark placement, and viewer-scoped projection/event deltas.

CORE V1 relevant areas:

- `src/warhammer40k_ai/engine/decision_handlers/movement.py`
- `src/warhammer40k_ai/pathing/validation.py`
- `src/warhammer40k_ai/pathing/types.py`
- `src/warhammer40k_ai/engine/game_setup_flow.py`
- movement, deployment, reserve, Disembark, replay, UI/headless, and decision-dispatch tests

## Phase 11E: mission actions, primary/secondary scoring, and end-of-turn cleanup

Status: Complete.

Modules:

- `engine/scoring.py`
- `engine/missions.py`
- `engine/mission_decisions.py`
- `engine/actions.py`
- `engine/turn_cleanup.py`
- `engine/unit_coherency.py`
- `rules/source_packages/warhammer_40000_11th/chapter_approved_2026_27.py`

Objects:

- `MissionScoringPolicy`
- `VictoryPointLedger`
- `MissionActionState`
- `MissionSourcePackageDefinition`
- `MissionActionDefinition`
- `EndTurnCleanupState`
- `CoherencyCleanupRemoval`

Invariants:

- scoring, game length, caps, reserve deadline policy, secondary deck eligibility,
  and supported mission Action timing/effects are source-backed
  `warhammer_40000_11th` mission-pack data, not hard-coded phase logic;
- primary and secondary VP awards consume source scoring-rule conditions and
  per-card Fixed/Tactical VP values; unsupported conditions fail fast instead of
  using default scoring amounts;
- player-facing Tactical discard and supported mission Action start selections use
  finite `DecisionRequest` options through `GameLifecycle.submit_decision(...)`;
- mission Actions have source-backed start timing, eligible units, target IDs,
  interruption conditions, completion timing, and scoring effects;
- the mission deck grants two Secondary Missions per player turn;
- Secondary Missions are retained until achieved or discarded, and Secondary
  Missions discarded by the ordinary Tactical discard flow are not replaced
  immediately;
- retained Secondary Missions do not have a two-card hand-size cap;
- Tactical discard can discard one or more retained Secondary Missions, records
  no replacement draw, and grants the Chapter Approved 2026-27 1 CP ordinary
  discard reward only when the discarding player is the active player;
- New Orders is a separate 1 CP Stratagem path that discards one retained
  Secondary Mission, immediately draws a replacement Secondary Mission, and is
  usable only once per game;
- secondary mode, Fixed IDs, Tactical draws/card states, and normal secondary
  scoring visibility are source-backed and viewer-scoped;
- objective control feeds scoring;
- end-of-turn coherency cleanup removes models until each affected unit has one coherent group;
- coherency-cleanup removals count as destroyed but do not trigger destroyed-model rules;
- unarrived Reserves destruction resolver is invoked at the mission-defined deadline;
- game end after configured battle rounds produces winner/draw result.

Required tests:

- primary scoring at correct timing and source-backed battle-round gates;
- secondary scoring uses source-backed Fixed/Tactical card VP values;
- Secondary Mission draw, score, retain, and discard flow is public or hidden according to source-backed viewer rules;
- Tactical secondary discard emits deterministic decision/event records through the lifecycle path, can discard one or more retained Secondary Missions, grants the Chapter Approved 2026-27 1 CP ordinary discard reward only on the discarding player's own turn, and does not replace discarded cards;
- New Orders emits deterministic Stratagem, CP, discard, and replacement-draw
  records, rejects second use in the same game, and cannot be confused with
  ordinary Tactical discard;
- mission Action can start through the lifecycle decision path, persist its target,
  filter ineligible units, complete, be interrupted, and score;
- source package payloads round-trip and preserve 11th Edition mission/scoring/action snapshots;
- end-of-turn coherency cleanup removes models without destroyed triggers;
- unarrived Reserves are destroyed at the configured deadline through the lifecycle hook;
- victory point ledger round-trips;
- game ends after configured battle rounds.

## Phase 11F: battle-round/game-end scoring and winner determination

Status: Complete.

Implemented coverage:

- game length is consumed from mission scoring policy;
- end-of-round and end-of-game scoring windows are recorded once as replay-safe state;
- 11th Edition primary, secondary, Battle Ready, per-round Primary, per-round Secondary, and total VP caps are enforced at award time;
- final scoring result payloads include public capped scores, winner/draw determination, and scoring audit data;
- final scoring payloads round-trip without Python object reprs.

Invariants:

- game length is mission/ruleset data;
- end-of-round and end-of-game scoring windows are explicit;
- final VP ledger audit verifies winner/draw payloads;
- 11th Edition 45 VP Primary cap, 45 VP Secondary cap, 10 VP Battle Ready cap, 15 VP per-round Primary and Secondary caps, 100 VP total cap, and per-source caps are represented in scoring policy;
- game-end payload includes public final score and replay-safe scoring audit.

Required tests:

- game ends after configured number of battle rounds;
- winner/draw determination is deterministic;
- end-of-game scoring windows fire once;
- VP caps are enforced;
- final scoring payload round-trips.

---

# Timing windows, Stratagems, and abilities

## Phase 12A: timing windows, reaction queue, sequencing, and persisting effects

Status: Complete.

Modules:

- `engine/timing_windows.py`
- `engine/reaction_queue.py`
- `engine/effects.py`
- `engine/sequencing.py`

Objects:

- `TimingWindow`
- `ReactionWindow`
- `TimingWindowDescriptor`
- `TimingTriggerKind`
- `PersistingEffect`
- `EffectExpiration`
- `TriggeredDecisionRequest`
- `SequencingDecision`
- `OutOfPhaseActionContext`

Invariants:

- out-of-phase rules use typed timing windows;
- timing descriptors cover explicit trigger families needed by Stratagems and reactive rules, including any phase, start/end phase, start/end turn, start/end battle round, after a unit is selected as a target, after an enemy unit ends a move, after a unit is destroyed, just after an enemy unit has fought, and after dice/roll events;
- out-of-phase actions perform only the specified action and do not trigger other rules normally used in that phase unless the rule explicitly says so;
- reaction windows can block and resume parent phase execution;
- sequencing conflicts during battle are ordered by the player whose turn it is;
- sequencing conflicts before or after the battle, or at the start or end of a battle round, are ordered by a roll-off winner;
- roll-offs for sequencing use Phase 10J roll-off semantics and cannot be rerolled or modified;
- persisting effects expire at deterministic lifecycle points;
- persisting effects continue to apply while a unit Embarks and still apply after it Disembarks for their remaining duration;
- if a persisting effect applies to an Attached unit and the Attached unit splits because Bodyguard or Leader models are destroyed, the effect continues on the surviving unit(s) for its remaining duration;
- effect payloads are replay-safe;
- no rule handler mutates state outside its owning timing window.

Required tests:

- reaction window emits interrupt-style decision request;
- parent phase resumes after reaction resolution;
- out-of-phase shooting does not trigger unrelated Shooting-phase abilities;
- active player chooses order for simultaneous during-battle rules;
- roll-off decides simultaneous start/end battle round rules;
- persisting effect survives Embark/Disembark;
- persisting effect survives Attached-unit split;
- unsupported timing windows fail explicitly;
- unsupported timing descriptor trigger families fail explicitly before any option is emitted;
- sequencing conflict creates a deterministic resolver decision when needed.

CORE V1 relevant areas:

- `engine/combat_timing.py`
- reactive decision handling;
- phase/reaction/persisting-effect tests.

## Phase 12B: Command Point ledger and Stratagem framework

Status: Complete.

Modules/documents:

- `engine/stratagems.py`
- `engine/stratagem_catalog.py`
- `engine/command_points.py`
- `engine/timing_windows.py`
- `rules/source_packages/warhammer_40000_11th/core_stratagems.py`
- `docs/ADAPTER_DECISION_CONTRACT.md`

Objects:

- `CommandPointLedger`
- `CommandPointTransaction`
- `CommandPointSpendResult`
- `CommandPointGainResult`
- `CommandPointRefundResult`
- `StratagemDefinition`
- `StratagemCatalogRecord`
- `StratagemCatalogIndex`
- `StratagemTimingDescriptor`
- `StratagemRestrictionPolicy`
- `StratagemTargetSpec`
- `StratagemUseRequest`
- `StratagemUseRecord`
- `StratagemEligibilityContext`
- `StratagemTargetBinding`
- `StratagemTargetProposal`

Invariants:

- Stratagem use is a player-facing decision and must use the Phase 11D adapter decision contract: `DecisionRequest` -> `FiniteOptionSubmission` or `ParameterizedSubmission` -> `DecisionResult` -> `GameLifecycle.submit_decision(...)` -> engine validation -> engine mutation;
- the finite decision type is `use_stratagem`; the engine enumerates deterministic, JSON-safe options only for currently eligible Stratagem, timing-window, CP, restriction, and fully validated target-binding combinations;
- adapters, UI, CLI, network clients, headless AI, replay, and tests must not invent Stratagem option IDs, bind targets from option payloads outside engine validation, spend/refund CP directly, or mutate state from Stratagem payloads;
- Stratagem target bindings that cannot be safely enumerated as finite choices use typed parameterized proposals, validate stale/drift/malformed/schema-invalid/wrong-context submissions before queue pop, and return typed invalid diagnostics without CP spend or state mutation;
- Stratagem decisions can be offered to the non-active player inside Phase 12A reaction windows, and eligibility context is computed per player for the active timing window;
- core Stratagems are source-backed `StratagemDefinition`/`StratagemCatalogRecord` descriptors and are always available unless a ruleset disables them;
- detachment Stratagems are usable only when the player's army selected the matching detachment or another explicit source grants them;
- Stratagem candidate dispatch uses a trigger-keyed `StratagemCatalogIndex`; the index is derived, deterministic, not authoritative state, and never replaces runtime timing, detachment, CP, target, restriction, or handler gates;
- core and detachment Stratagem records can be partitioned per player before indexing to avoid considering records the selected detachment can never grant, while the runtime detachment gate remains authoritative;
- every implemented phase that owns a source-backed Stratagem timing window must wire candidate discovery through the trigger-keyed index rather than scanning the whole catalog at event time;
- phase hooks that own multiple optional Stratagem windows under the same phase and trigger must assign distinct deterministic `timing_window_id` values, and decline suppression must be scoped to that exact timing window rather than the broader phase/trigger;
- Stratagem definitions include CP cost, category, source ID, normalized WHEN/TARGET/EFFECT/RESTRICTIONS descriptors, timing descriptor, target spec, restriction policy, faction/detachment gate, and handler binding;
- Stratagems spend, gain, and refund CP only through a bidirectional ledger with deterministic transaction IDs and replay-safe payloads;
- starting CP, Command-phase +1 CP gain from Phase 11C, non-Command CP gain caps, CP refunds, and CP-granting Stratagem/effect results are ledger transactions, not local counters;
- insufficient CP is a typed invalid result and must never underflow a ledger;
- matched-play same-Stratagem-once-per-phase restrictions are tracked separately from per-Stratagem once-per-turn, once-per-battle, per-target, and per-fight restrictions;
- Battle-shocked units cannot be selected for Stratagems unless rules permit;
- finite target binding is typed and validated before a finite Stratagem option appears, and parameterized target proposals carry typed validation context before adapters answer them;
- Stratagem timing is descriptor-driven and unsupported timing descriptors fail explicitly;
- Stratagem effects execute through Phase 12A persisting-effect machinery or source-linked named handlers in Phase 12B/12C; Phase 17D can replace representable named handlers with generic IR handlers without changing the decision/ledger contract;
- invalid or missing target context suppresses the option rather than emitting illegal choices;
- CP totals, CP transactions, and normal Stratagem-use events are public viewer-scoped adapter data in matched play unless a future source-backed hidden rule marks a specific pending decision or event hidden.

Required tests:

- adapter contract doc is updated for `use_stratagem` finite options, Stratagem target proposals, CP transaction visibility, and public Stratagem events;
- finite `use_stratagem` option enumeration and `FiniteOptionSubmission` round-trip through `GameLifecycle.submit_decision(...)`;
- parameterized Stratagem target proposal valid submission plus stale, drifted, malformed, schema-invalid, and wrong-context invalid diagnostics;
- insufficient CP suppresses legal options where possible and rejects attempted use with a typed invalid result;
- CP ledger cannot underflow;
- Command-phase +1 CP gain from Phase 11C is represented as a ledger transaction and Stratagem spend consumes from that ledger;
- CP-granting/refunding effects create deterministic gain/refund transactions and obey the non-Command CP gain cap unless an explicit rule overrides it;
- matched-play same-Stratagem-twice-per-phase rejection is distinct from per-Stratagem own restrictions;
- Battle-shocked unit eligibility restriction works;
- target-required Stratagem does not appear without legal target binding;
- reactive non-active-player Stratagem use is emitted and resolved inside a Phase 12A reaction window;
- phase/reaction-window progression uses `StratagemCatalogIndex` for implemented Stratagem windows and has regression coverage proving the source-backed phase hook emits the pending request through `GameLifecycle.submit_decision(...)`;
- nested reactions such as Command Re-roll during another Stratagem's dice resolution resume deterministically;
- detachment Stratagems are gated by selected detachment, while core Stratagems are available;
- viewer-scoped projection/event stream exposes public CP and Stratagem data and redacts any future hidden Stratagem data by explicit policy;
- Stratagem use round-trips in replay.

CORE V1 relevant areas:

- `src/warhammer40k_ai/engine/stratagem_ledger.py`
- stratagem tests;
- headless tool-action context audits.

## Phase 12C: Phase-12-resolvable Core Stratagems

Status: Complete.

Initial supported Core Stratagem groups at this build slice:

- Command Re-roll;
- Insane Bravery;
- New Orders;
- Rapid Ingress.

Later phase-coupled Core Stratagems:

- Smokescreen and Explosives are implemented at the Shooting-phase gate after visibility, Benefit of Cover, attack sequencing, and damage allocation exist;
- Fire Overwatch is implemented at the Phase 13D Shooting/Movement gate through a real out-of-phase Snap Shooting state that resolves shooting declaration and attack-sequence decisions from the End of Opponent's Movement phase window before resuming the parent phase;
- Heroic Intervention, Counteroffensive, Epic Challenge, and Crushing Impact are implemented at the Charge/Fight gates after charge movement, fight ordering, melee attacks, and model-target binding exist;
- deferred Core Stratagem descriptors still exist as explicit unsupported descriptors until their owning phase gate implements them.

Invariants:

- each supported Core Stratagem has a source-backed definition, timing descriptor, target spec, restriction policy, CP cost, and handler binding;
- each supported Core Stratagem has explicit finite or parameterized target-binding rules;
- each supported Core Stratagem consumes CP and records use;
- Command Re-roll uses source-backed edition-specific eligible roll classes, rejects roll actor drift, and applies Phase 10J reroll semantics while remaining valid as a nested reaction without breaking the parent timing window;
- Insane Bravery integrates with Phase 11C Battle-shock results without bypassing `DecisionRequest`/`DecisionResult`;
- New Orders costs 1 CP, can be used only once per game, discards one retained
  Secondary Mission card, and immediately draws one replacement Secondary Mission
  card through source-backed mission deck state;
- Rapid Ingress reuses reserve-arrival placement validators and, where exact placement is required, emits the existing placement proposal request after the Stratagem decision is accepted; when offered from a reaction window, the parent remains blocked until the placement proposal resolves;
- Command and Movement phase progression discover supported Core Stratagem windows through `StratagemCatalogIndex`: Command start for Insane Bravery and New Orders, and opponent Movement phase end for Rapid Ingress reaction/placement;
- supported dice/mission/reserves Stratagems use deterministic dice/replay plumbing and source IDs;
- Phase 12C reuses Phase 12A persisting-effect/reaction machinery and Phase 12B ledger/decision framework; it does not depend on the later Phase 12D ability registry or Phase 17D generic handlers;
- unsupported Core Stratagems remain explicit unsupported descriptors.

Required tests:

- one legal use per supported Phase-12 timing window;
- one phase-progression regression per supported phase-owned Stratagem window, proving the window is emitted from the trigger-keyed index and resolves through `GameLifecycle.submit_decision(...)`;
- combined-window regressions for phases with multiple optional Stratagem windows under the same phase/trigger, proving declining one timing window does not suppress a distinct later timing window;
- per-Stratagem golden replay for Command Re-roll, Insane Bravery, New Orders, and Rapid Ingress;
- New Orders consumes 1 CP, rejects second use in the same game, discards exactly
  one retained Secondary Mission, and immediately draws exactly one replacement
  card;
- decision-contract round-trip for option enumeration, submission, recording, event emission, and replay;
- CP consumption and repeat-use restriction;
- target-binding validation;
- CP-underflow rejection;
- same-Stratagem-twice-per-phase rejection;
- reactive non-active-player use where timing allows;
- nested Command Re-roll during another Stratagem's dice resolution;
- dice/mission/reserves records for relevant Stratagems;
- unsupported Core Stratagems fail explicitly.

## Phase 12D: ability handler registry and keyword-gated rule execution

Status: Complete.

Modules:

- `engine/abilities.py`
- `engine/ability_catalog.py`
- `rules/source_packages/warhammer_40000_11th/core_abilities.py`
- `rules/timing.py`
- `core/datasheet.py`
- `core/weapon_profiles.py`

Objects:

- `AbilityHandlerRegistry`
- `AbilityCatalogRecord`
- `AbilityCatalogIndex`
- `AbilityTimingDescriptor`
- `AbilityExecutionContext`
- `AbilityResolutionResult`
- `KeywordGate`

Invariants:

- core, keyword, faction, detachment, datasheet, wargear, and weapon abilities are represented as source-linked `AbilityDefinition`/`AbilityCatalogRecord` descriptors;
- ability candidate dispatch uses a trigger-keyed `AbilityCatalogIndex`; the index is derived, deterministic, not authoritative state, and never replaces runtime timing, source-owner, keyword, input, or handler gates;
- player/army ability indexes can be pre-partitioned from selected faction, detachment, datasheets, wargear, weapon profiles, and canonical unit/weapon keywords, while runtime gates remain authoritative;
- every future phase that owns an ability timing window must wire candidate discovery through `AbilityCatalogIndex` and must add regression coverage proving the phase hook does not scan the full ability catalog at event time;
- ability descriptors are inert until a registered handler executes them;
- handlers declare timing windows and input requirements;
- keyword-gated effects use canonical keywords;
- movement keyword capabilities are resolved from source-backed keyword ability gates, not ad hoc phase-local keyword scans;
- unsupported ability descriptors remain unsupported rather than fallback-parsed;
- ability execution records source IDs and replay payloads.

Required tests:

- source-backed 11th Edition ability rows cover the Phase 12D ability families and round-trip without object reprs;
- `AbilityCatalogIndex` partitions records by `TimingTriggerKind`, preserves deterministic ordering, rejects duplicate records, and produces option-equivalent context lookup to a full tuple scan;
- `AbilityHandlerRegistry` rejects duplicate and unsupported registrations, validates timing/input/keyword gates, and returns typed unsupported for missing or future handlers;
- movement keyword capabilities are derived through the ability index and fail closed when a test index omits the relevant keyword gate;
- player/army ability indexes retain only selected core/keyword, faction, detachment, datasheet, wargear, and weapon-profile records;
- ability records, execution contexts, and resolution results serialize as deterministic JSON-safe replay payloads.

Initial ability families:

- Deep Strike;
- Scouts;
- Infiltrators;
- Leader;
- Stealth;
- Lone Operative;
- Feel No Pain;
- Deadly Demise;
- Firing Deck;
- Hazardous;
- weapon abilities wired through Phase 13D.

---

# Shooting phase

## Phase 13A: terrain visibility, line of sight, and cover foundation

Status: Complete.

Modules:

- `geometry/visibility.py`
- `geometry/terrain.py` for terrain feature and volume inputs consumed by visibility
- `geometry/terrain_factory.py` for canonical visibility fixtures
- `engine/battlefield_state.py` for spatial revision and cache-key state
- `core/ruleset_descriptor.py`

Objects:

- `LineOfSightPolicy`
- `TerrainVisibilityContext`
- `VisibilityBlockerRecord`
- `LineOfSightWitness`
- `CoverSourceRecord`
- `CoverPolicyDescriptor`
- `BenefitOfCoverResult`
- `HiddenDetectionResult`
- `GoneToGroundResult`

Invariants:

- true line of sight is modeled from model volume/pose;
- model visible, unit visible, model fully visible, and unit fully visible are separate results;
- terrain visibility rules are descriptor-driven through terrain areas and terrain categories;
- Exposed, Light, and Dense terrain categories are explicit descriptors;
- Obscuring terrain areas containing Light or Dense features block visibility when every line of sight crosses one or more such areas and neither model is within the crossed area;
- Dense terrain features have Solid line-of-sight blocking for enclosed gaps 3" or less from ground level;
- Hidden can apply only to `INFANTRY`, `BEASTS`, and `SWARM` models;
- a model is Hidden when it is at least partially within a terrain area
  containing a Dense or Light terrain element and its unit did not make ranged
  attacks last turn;
- Hidden units can only be visible to enemy models within the target unit's
  Detection Range characteristic, defaulting to 15";
- Gone to Ground applies to a model that is not fully visible to the attacking
  model because a terrain piece is at least partially in the way;
- Gone to Ground improves Detection Range by -3", making the default Hidden
  detection distance 12";
- rules, abilities, or Stratagems that let a Hidden unit shoot and remain Hidden
  cancel Gone to Ground for that interaction;
- Benefit of Cover is a policy result consumed by attacks, not a save-side effect;
- Benefit of Cover applies to the target unit only when every model in that unit qualifies through terrain-area membership or terrain/obscuring not-fully-visible evidence;
- Benefit of Cover worsens the attack's BS characteristic by 1 unless an ability such as `[IGNORES COVER]` removes it;
- cover eligibility is visible in attack context before hit rolls are made;
- LoS witnesses carry ruleset hash and spatial revision cache-key data;
- Hidden distance gates, last-turn shot-state loss, Gone to Ground cancellation,
  and visibility output are first-class 11th Edition terrain behavior;
- Phase 13A uses deterministic broad-phase candidate filtering and cache-key witnesses, but does not claim a persistent memoized shooting LoS cache; Phase 13B/13C must add or consume a real cache/index before high-volume shooting loops;
- model silhouette sampling is an explicit deterministic approximation, not an exact hull; downstream cover and Plunging Fire behavior must carry accuracy tests for that sampling budget;
- LoS witness/debug payloads are replay-safe.

Required tests:

- terrain visibility fixture can block LoS deterministically;
- terrain-area Obscuring blocks LoS only when all lines cross eligible areas and neither model is within the crossed area;
- Dense terrain Solid blocks LoS through enclosed gaps 3" or less from ground level;
- Hidden `INFANTRY`/`BEASTS`/`SWARM` models in Dense or Light terrain areas are
  visible only within the target unit's Detection Range while their last-turn
  shot-state condition is satisfied;
- Gone to Ground applies only when the attacking model's full-visibility failure
  is caused by intervening terrain, applies the -3" Detection Range modifier,
  and is cancelled by Hidden-shooting rules that preserve Hidden;
- target terrain-area membership and not-fully-visible terrain cover sources are represented independently of LoS blockers;
- Benefit of Cover rejects a LoS witness from a different observer/target query even when terrain cache keys match;
- Benefit of Cover worsens BS by 1 and does not modify the save roll;
- model volume participates in visibility checks;
- terrain visibility cache key changes when terrain revision changes;
- model silhouette sampling budget is explicit and regression-tested;
- Benefit of Cover policy result round-trips;
- LoS witness/debug payload round-trips.

CORE V1 relevant areas:

- `src/warhammer40k_ai/battlefield/terrain_visibility.py`
- `src/warhammer40k_ai/battlefield/terrain_cover.py`
- `src/warhammer40k_ai/battlefield/map.py`
- `tests/rules/test_line_of_sight.py`

## Phase 13B: Shooting phase target selection and weapon declaration

Status: Complete.

Modules:

- `engine/phases/shooting.py`
- `engine/shooting_targets.py`
- `engine/weapon_declaration.py`
- `engine/transports.py`
- `docs/ADAPTER_DECISION_CONTRACT.md`

Objects:

- `ShootingPhaseState`
- `ShootingUnitSelection`
- `ShootingTargetCandidate`
- `WeaponDeclaration`
- `ShootingDeclarationProposal`
- `FiringDeckWeaponSelection`
- `RangedAttackPool`

Invariants:

- all attacker shooting choices are player-facing decisions and must use `DecisionRequest` -> `FiniteOptionSubmission` or `ParameterizedSubmission` -> `DecisionResult` -> `GameLifecycle.submit_decision(...)` -> `DecisionRecord`/`EventRecord`;
- Phase 13B must update `docs/ADAPTER_DECISION_CONTRACT.md` with every new shooting unit selection, target declaration, weapon declaration, Firing Deck selection, option payload, proposal payload, and viewer-visibility rule introduced;
- finite shooting options use deterministic option IDs and JSON-safe payloads; parameterized declaration proposals reject stale, drifted, malformed, schema-invalid, or wrong-context submissions before queue pop unless the contract explicitly allows recorded rule-invalid retry attempts;
- eligible shooting units are derived from current state;
- units that Advanced/Fell Back cannot shoot unless a rule permits;
- engaged units obey Close-quarters shooting restrictions and shooting-at-engaged-`MONSTER`/`VEHICLE` target rules;
- shooting at engaged units applies the correct Hit-roll penalty unless the attack is a qualifying `[CLOSE-QUARTERS]`/`[PISTOL]` attack;
- a unit containing one or more models with a `[CLOSE-QUARTERS]` weapon can use
  Close-quarters Shooting;
- when a unit uses another shooting type, each non-`MONSTER`/non-`VEHICLE` model
  in that unit can select either one or more of its `[CLOSE-QUARTERS]` weapons
  or one or more of its other ranged weapons, but not both groups for that
  model in the same declaration;
- the completed Lone Operative targeting slice enforces the default 12" gate
  for units with the canonical `LONE_OPERATIVE` keyword and does not require
  the Lone Operative target to be the closest eligible target;
- attached-unit suppression, `Lone Operative X"` distance overrides,
  model-distance measurement, and the `[INDIRECT FIRE]` within-distance
  exception remain future source-backed work until implemented with regressions;
- ranged weapons validate range and visibility at target selection time;
- targets for all of a unit's ranged weapons are declared before any attack is resolved;
- a weapon remains resolved against a target selected as visible/in range even if later attacks remove visible/in-range models before resolution;
- attack declarations group by model, weapon, profile, and target;
- Firing Deck attack-generation consumption, one-weapon-per-embarked-model validation, temporary Transport weapon attachment, and embarked-unit shot/ineligible state are resolved here from the Phase 10Q hand-off;
- Hazardous and one-shot-style requirements are explicit descriptors.

Required tests:

- shooting unit selection goes through finite `DecisionRequest`/`DecisionResult` submission and records deterministic JSON-safe `DecisionRecord`/`EventRecord` payloads;
- weapon and target declaration goes through the adapter contract, including stale/drift/malformed invalid submission coverage and replay payload round-trip;
- eligible unit selection;
- Advanced/Fell Back restriction;
- target range/visibility validation;
- Lone Operative tests cover the default 12" gate for canonical
  `LONE_OPERATIVE` units and prove no closest-target requirement; attached-unit
  suppression, `Lone Operative X"` distance overrides, model-distance
  measurement, and the `[INDIRECT FIRE]` within-distance exception must be
  added before the full official Lone Operative rule is marked complete;
- Close-quarters Shooting availability, shooting at engaged `MONSTER`/`VEHICLE`,
  `[CLOSE-QUARTERS]`/`[PISTOL]`, per-model close-quarters-versus-other-ranged
  weapon declaration exclusivity, and `[BLAST]` interactions;
- Firing Deck consumes selected embarked models/weapons, rejects duplicate or illegal embarked weapon use, attaches temporary Transport attacks, and marks selected embarked units ineligible to shoot;
- selected target remains valid for declared weapon resolution after casualties;
- weapon declaration payload round-trip;
- invalid target declaration fails without mutation.

## Phase 13C: attack sequence: hit, wound, allocate, save, damage

Status: Complete.

Modules:

- `engine/attack_sequence.py`
- `engine/damage_allocation.py`
- `engine/saves.py`
- `engine/dice.py` and Phase 10J dice/reroll helpers are consumed, not reimplemented

Objects:

- `AttackSequence`
- `HitRoll`
- `WoundRoll`
- `AttackAllocation`
- `AttackAllocationDecision`
- `SavingThrow`
- `FeelNoPainDecision`
- `PlungingFireModifier`
- `MortalWoundApplication`
- `DamageApplication`
- `FastDiceGroup`

Invariants:

- attack sequence follows hit, wound, allocate, saving throw, inflict damage;
- Hit rolls use BS for ranged attacks and WS for melee attacks;
- unmodified Hit roll of 6 is a Critical Hit and always succeeds;
- unmodified Hit roll of 1 always fails;
- Hit roll modifiers are capped at +1/-1;
- Wound roll modifiers are capped at +1/-1;
- Wound roll target number derives from Strength vs Toughness using integer-safe boundaries: 2+ when `S >= 2*T`, 3+ when `S > T`, 4+ when `S == T`, 6+ when `2*S <= T`, and otherwise 5+;
- unmodified Wound roll of 6 always succeeds and unmodified Wound roll of 1 always fails;
- unmodified saving throw roll of 1 always fails before any save characteristic
  is checked;
- the attack sequence emits typed, ordered attack events/timing windows at hit, Critical Hit, wound, Critical Wound, allocation-order, save, and damage; ability handlers may only mutate within their owning windows, so Phase 13D abilities can attach without reaching into attack-sequence internals;
- hit resolution supports both rolled hits and explicit skipped-roll/generated-hit paths, so later ability handlers can produce auto-hits without coupling Phase 13C to named abilities;
- Critical Wounds and wound-roll modification are explicit attack events;
- all defender allocation-order, optional Feel No Pain, and defensive reaction choices are player-facing decisions routed through `GameLifecycle.submit_decision(...)`; no defender choice may be made by direct engine helper calls, adapters, tests, or UI code;
- defender-facing requests set the defending controlling player as `actor_id`, are viewer-scoped, and produce deterministic JSON-safe `DecisionRecord`/`EventRecord` payloads;
- forced allocation-order and save paths may resolve automatically only when there is exactly one legal rules outcome and no optional player choice;
- the defender creates allocation groups for the target unit before saves are resolved: one group for each `CHARACTER` model and one group for all other models sharing W, Sv, and InSv characteristics;
- the defender declares an allocation order for those groups, with wounded non-`CHARACTER` groups first, no `CHARACTER` group before a non-`CHARACTER` group, and wounded `CHARACTER` groups before unwounded `CHARACTER` groups;
- the target's controlling player makes one save roll for each attack that wounded the target before model allocation is resolved;
- damage resolution walks save results from lowest result(s) to highest result(s), selecting models from the current allocation group and selecting a wounded model in that group where possible;
- current allocation group transitions only after all models in the prior group are destroyed;
- the allocation step accepts optional attacker-side allocation constraints, such as `[PRECISION]`, so later rules can constrain or override allocation without bypassing `submit_decision(...)`;
- when the current allocation group has an Invulnerable Save, that InSv must be
  used for the save roll and the defender cannot choose to use an armour Save
  instead;
- when the current allocation group has no Invulnerable Save but has a Save,
  armour saves apply AP modifiers against the current allocation group's Sv
  characteristic;
- if neither Invulnerable Save nor Save applies, the save fails and the attack
  inflicts damage;
- Benefit of Cover worsens the attack's BS characteristic by 1 before hit rolls and no longer modifies save rolls;
- the retired AP 0 / Save 3+ cover exception is not part of the 11th Edition ruleset and must be removed from runtime behavior;
- Plunging Fire is a descriptor-driven BS improvement that consumes Phase 13A line-of-sight, height, ground-level target, and `TOWERING` within-12" evidence; unsupported Plunging Fire shapes return typed unsupported diagnostics instead of being silently ignored;
- mortal wounds are allocated one at a time, do not allow saves, and spill over unless the source rule says remaining mortal wounds are lost;
- mortal wounds from attacks are applied after normal damage from that attacking unit, even if the normal damage was saved;
- Feel No Pain rolls are per lost wound, including mortal wounds, and only one Feel No Pain ability can be used per lost wound;
- normal attack excess damage is lost when a model is destroyed;
- WS, BS, Strength, AP, Damage, and random Attacks/Damage characteristics consume existing descriptor/modifier and Phase 10J dice semantics, including reroll windows and characteristic caps/floors;
- Fast Dice Rolling is allowed only when BS/WS, Strength, AP, Damage, abilities, and target are the same and order cannot affect the result;
- random Damage attacks cannot use fast dice in cases where allocation order can affect destroyed/damaged model outcomes;
- model destruction emits removal records and destruction timing windows.

Required tests:

- defender allocation choice is emitted as a `DecisionRequest`, resolved through `GameLifecycle.submit_decision(...)`, replayed from `DecisionRecord`, and redacted or scoped correctly for viewers;
- a save roll of 1 fails before InSv/Sv evaluation;
- Invulnerable Save precedence is mandatory when the current allocation group has
  InSv, with no armour-versus-invulnerable defender choice;
- optional or competing Feel No Pain choices are finite defender `DecisionRequest`s; forced single-source Feel No Pain paths remain engine-owned deterministic rolls;
- stale/drift/malformed defender submissions are rejected without mutation;
- full attack sequence resolves deterministically with no ability handlers installed, and a stub no-op handler proves each typed event hook fires in order;
- hit/wound/save/damage deterministic dice flow;
- Hit roll 6 critical/auto-success and 1 auto-fail;
- Hit modifier cap of +1/-1;
- Wound modifier cap of +1/-1;
- unmodified Wound roll 6/1 and unmodified Save roll 1 semantics;
- Wound roll table boundaries;
- armour save and mandatory invulnerable-save precedence against current
  allocation groups;
- Benefit of Cover worsens BS before hit rolls and never improves saves;
- allocation groups and allocation-order decisions obey wounded-model and `CHARACTER` ordering constraints;
- save rolls are resolved from lowest result(s) to highest result(s);
- a Character wounded by an earlier attacker-constrained allocation remains illegal for a later unconstrained attack while Attached-unit Bodyguard models remain;
- Plunging Fire improves BS only with the required height, `TOWERING`, visibility, and ground-level target evidence and fails explicitly when the selected ruleset does not support it;
- mortal wound spillover and no-save path;
- Devastating/Hazardous mortal-wound lost-remainder exceptions where applicable;
- Feel No Pain per-wound roll path;
- wounded-model allocation priority;
- fast dice group allowed for identical attacks;
- random damage fast dice is rejected where order matters;
- model destruction emits removal records;
- damage allocation payload round-trips.

## Phase 13D: weapon abilities, shooting/fight modifiers, and shooting Stratagems

Status: Complete.

Initial Core Rules weapon ability coverage:

- Assault;
- Rapid Fire X;
- Ignores Cover;
- Twin-linked;
- Close-quarters / Pistol alias;
- Cleave X;
- Torrent;
- Lethal Hits;
- Lance;
- Indirect Fire;
- Precision;
- Blast;
- Melta X;
- Heavy;
- Hazardous;
- Devastating Wounds;
- Sustained Hits X;
- Extra Attacks;
- Hunter X;
- Anti-KEYWORD X+.

Initial shooting-coupled Core Stratagem coverage:

- Smokescreen where applicable;
- Explosives;
- Crushing Impact;
- Fire Overwatch from the end-of-opponent-Movement-phase window through Snap Shooting.

Invariants:

- weapon abilities are structured descriptors;
- ability handlers modify the attack sequence only in declared timing windows;
- shooting-coupled Core Stratagems reuse the Phase 12B Stratagem definition, decision, target-binding, CP ledger, and replay contract;
- every shooting-coupled Core Stratagem timing hook is registered through `StratagemCatalogIndex`; Shooting phase code must not scan the full catalog when a shooting event occurs;
- duplicated weapon abilities are never cumulative, including duplicate
  instances whose numbers or target keywords differ;
- the implemented duplicate weapon ability lifecycle slice covers duplicate
  `[ANTI]` descriptors in Shooting declarations: the controlling player's
  Select-Weapons-step source-instance choice is adapter-visible on the target
  candidate, stored on `WeaponDeclaration`/`RangedAttackPool`, and carried into
  attack events/context before the Anti Critical Wound threshold is read;
- numbered weapon abilities such as `[SUSTAINED HITS 1]` and `[SUSTAINED HITS
  2]`, and non-Anti keyworded duplicate families, remain future lifecycle
  threading work; they must fail explicitly or stay unsupported rather than
  stack unselected duplicate effects;
- Assault changes shooting eligibility and restricts attacks to Assault weapons after Advance;
- Rapid Fire, Blast, Cleave, Melta, Heavy, Lance, and Indirect Fire modify characteristics/rolls through typed modifier stacks and consume Phase 10J dice/random-characteristic semantics rather than reimplementing dice;
- Twin-linked grants a Wound-roll reroll permission and consumes Phase 10J reroll semantics;
- `[CLOSE-QUARTERS]` modifies Close-quarters Shooting eligibility, engaged
  targeting, and per-model ranged weapon-selection exclusivity for other
  shooting types; `[PISTOL]` is an exact alias for all rules purposes;
- Torrent bypasses Hit rolls and interacts correctly with Indirect Fire restrictions;
- `[IGNORES COVER]` removes Benefit of Cover from the target for each attack
  made with that weapon, including Benefit of Cover from terrain, Stealth,
  Smokescreen, Indirect Fire, or any other rule that gives a model or unit
  Benefit of Cover;
- the completed `[HEAVY]` slice applies the typed +1 Hit-roll modifier only
  when movement evidence shows the attacking unit did not Advance/Fall Back and
  no model in that unit moved more than 3" this turn; own-Shooting-phase
  timing, unengaged, and set-up-this-turn denial gates remain future work before
  the full official Heavy rule is marked complete;
- `[LETHAL HITS]` consumes Critical Hit events and is an active-player choice:
  for each Critical Hit, the attacker can choose for that attack to
  automatically wound and skip the Wound roll, or decline so the attack can make
  a Wound roll and potentially become a Critical Wound;
- Sustained Hits consumes Critical Hit events and preserves generated-hit wound
  context;
- `[LANCE]` adds 1 to the Wound roll for each attack made with that weapon only
  if the attacking model's unit made a Charge move this turn;
- Anti modifies Critical Wound thresholds based on target keywords;
- `[HUNTER X]` weapons can only target units that match at least one listed
  keyword in X, including composite keyword lists such as `MONSTER` or
  `VEHICLE`;
- Precision lets the attacking player select one visible `CHARACTER` allocation group at the start of the Allocation Order step; if selected, that group is the current allocation group until those attacks are resolved or that group is destroyed;
- Hazardous tests occur after the unit has resolved all its attacks and make unit-level hazard rolls that allocate mortal wounds through the 11th Edition mortal-wound sequence;
- Devastating Wounds ends the attack sequence for each critical wound and inflicts mortal wounds equal to Damage after normal damage; each critical wound can damage a maximum of one model and any excess mortal wounds from that critical wound are lost;
- Extra Attacks weapons are additional melee weapons and their Attacks cannot be modified unless the modifying rule names that weapon;
- Fire Overwatch source descriptors are bound to the end-of-opponent-Movement-phase out-of-phase shooting host and resolve through Snap Shooting; marker-only effects are forbidden, and the normal Shooting phase state must not be reused as the active player's phase state;
- Smokescreen grants structured, expiring Benefit of Cover effects through Phase 12A effect machinery and expires at the active shooting player's phase endpoint;
- Fire Overwatch, Smokescreen, and other reactive shooting-coupled Stratagem choices remain non-active-player target-proposal decisions under the adapter contract, while Explosives is an active-player Shooting phase target proposal;
- Explosives uses deterministic mortal-wound/damage application records and target binding from the shooting context, rejects Advanced, Fell Back, engaged source, engaged target, out-of-range, and non-visible target contexts before CP spend;
- shooting at `AIRCRAFT` consumes the 11th Edition Aircraft and Plunging Fire exclusions rather than an edition-diff hit modifier policy;
- unsupported weapon ability shapes fail explicitly;
- source IDs are preserved in emitted events.

Required tests:

- each supported weapon ability has at least one focused attack-sequence test;
- each supported shooting-coupled Core Stratagem has decision-contract, CP, target-binding, and replay coverage;
- Fire Overwatch has end-of-opponent-Movement-phase reaction tests proving it creates an out-of-phase Snap Shooting state, rejects out-of-range, engaged, TITANIC, shooting-ineligible, and no-legal-declaration selected friendly unit bindings before CP spend, applies the unmodified-6 hit policy while preserving Torrent auto-hit behavior, emits shooting declaration and attack-sequence decisions through the lifecycle, and resumes the parent reaction frame after completion;
- Smokescreen and Explosives have decision-contract tests from their legal shooting-resolution windows;
- unsupported weapon ability descriptor does not execute;
- duplicate `[ANTI]` weapon ability declarations are non-cumulative, require a
  Select-Weapons-step source-instance selection in Shooting declarations, carry
  the selected descriptor into attack-pool and attack-step payloads, and use
  only the selected keyword gate/Critical Wound threshold;
- duplicate numbered weapon abilities such as `[SUSTAINED HITS 1]` versus
  `[SUSTAINED HITS 2]` and non-Anti keyworded duplicate families require future
  lifecycle tests before those families are marked complete;
- Hunter X rejects target declarations that lack every required keyword match and
  accepts declarations with at least one listed target keyword;
- modifier interactions are deterministic;
- random Attacks and random Damage consume Phase 10J dice/reroll semantics;
- Twin-linked cannot reroll a Wound roll twice;
- `[IGNORES COVER]` strips Benefit of Cover from terrain, Stealth, Smokescreen,
  Indirect Fire, and other source-backed cover sources for attacks made with
  that weapon;
- `[HEAVY]` tests cover typed movement evidence, per-model moved-more-than-3"
  denial, and +1 Hit-roll modifier application for the current shooting
  declaration path; own-Shooting-phase-only timing, unengaged requirement, and
  set-up-this-turn denial require future regressions before full official
  coverage is claimed;
- `[LETHAL HITS]` Critical Hit choices cover accept-to-auto-wound/skip-Wound-roll
  and decline-to-roll-wound paths, including interactions with Critical Wound
  abilities such as `[DEVASTATING WOUNDS]`;
- `[LANCE]` adds +1 to Wound rolls only when the attacking model's unit made a
  Charge move this turn and is absent for non-charged, out-of-phase, and
  non-Lance attacks;
- Indirect Fire applies Benefit of Cover, disables Hit-roll rerolls, and enforces unmodified 1-5 fail or stationary-plus-friendly-visibility unmodified 1-3 fail;
- Close-quarters Shooting and shooting at engaged MONSTER/VEHICLE restrictions interact correctly with `[BLAST]` bans and per-model `[CLOSE-QUARTERS]` versus other-ranged weapon exclusivity;
- Hazardous and Devastating Wounds mortal-wound allocation ordering is correct.
- Fire Overwatch rejects invalid target bindings before CP spend and does not create marker-only effects;
- Smokescreen expires at the correct timing endpoint;
- Explosives rejects invalid target bindings without mutation.

## Phase 13E: damage allocation, destroyed models, and destruction reactions

Status: Complete.

Invariants:

- defender allocation choices are emitted as `DecisionRequest`s unless allocation is forced by the rules;
- optional Feel No Pain source/use and optional destruction-reaction choices remain in the shared adapter decision path and may not be answered by UI/headless/network-specific code; mandatory save routing, including Invulnerable Save precedence, is engine-owned;
- mandatory destruction reactions, including Deadly Demise-style rules, are engine-triggered and are not adapter decline choices;
- `DEADLY DEMISE X` rolls one deterministic D6 each time a model in that unit is
  destroyed, after any units embarked within it have made Emergency Disembark
  moves and before the destroyed model is removed from the battlefield;
- if the Deadly Demise roll is a 6, that model suffers Deadly Demise and each
  unit within 6" of that model suffers X mortal wounds;
- if X is random, the engine rolls the random mortal-wound amount separately
  for each unit within 6";
- when a Transport model with embarked units is destroyed by attacks, unresolved
  attacks from the attacking unit resolve first, then Emergency Disembark
  resolves, then Deadly Demise rolls and mortal wounds resolve, and finally the
  destroyed Transport model is removed;
- Deadly Demise resolves before destroyed-model removal, including its trigger roll, eligible nearby-unit mortal-wound packets, and any routed Feel No Pain choices;
- models destroyed by Deadly Demise mortal-wound packets use the same destroyed-model removal record, transition batch, and destruction-reaction host as attack damage;
- defender allocation and destruction records are viewer-scoped where hidden information can differ;
- defender allocates attacks according to rules;
- wounded models must continue receiving damage where applicable;
- destroyed models are removed with removal records;
- destroyed-model pools remain typed and source-addressable for later healing or
  revival effects, including attached-unit component restoration while the
  attached rules unit still exists;
- destroyed-model reaction windows fire unless the removal cause suppresses them;
- coherency-cleanup removals count as destroyed but do not trigger destroyed rules.

Required tests:

- defender allocation and optional defensive decisions produce `DecisionRecord`/`EventRecord` payloads and replay deterministically;
- stale/drift/malformed defender allocation submissions fail without mutation;
- viewer-scoped projection/event tests cover any hidden defensive or destruction-reaction payloads;
- wounded-model allocation priority;
- destroyed-model removal event;
- destroyed-model pool round-trip supports later healing/revival without object
  reprs or component identity loss;
- destroyed-model reaction timing;
- Deadly Demise failed roll, successful 6 trigger, fixed and random X mortal
  wounds, one random X roll per affected unit, pre-removal 6" measurement, and
  Feel No Pain pause/resume ordering;
- destroyed Transport ordering covers unresolved attacking-unit attacks,
  Emergency Disembark before Deadly Demise, Deadly Demise before removal, and
  deterministic event ordering matching the source example;
- Deadly Demise secondary casualties emit removal records, optional reaction requests, and chained mandatory Deadly Demise resolutions deterministically;
- non-triggering coherency cleanup removal.

## Phase 13F: Shooting phase completion gate

Status: Complete.

Required tests:

- full Shooting phase can complete for both players;
- shooting consumes visibility, cover, weapon declarations, attack sequence, damage allocation, and removal records;
- shooting completion waits for all pending attacker, defender, and shooting-coupled reaction decisions to resolve through `GameLifecycle.submit_decision(...)`;
- invalid declarations do not mutate state;
- shooting phase exits only after all selected/eligible units have resolved or skipped.

---

# 11th Edition migration and completed-phase revalidation

Phase 14 is the mandatory 11th Edition revalidation pass for completed Phases 1-13F. These phases are not optional compatibility slices. They must remove or quarantine retired identifiers, assumptions, fixtures, and source-package facts before Phase 15 Charge/Fight work begins.

## Phase 14A: source identity and migration audit

Status: Complete.

Modules:

- `core/ruleset_descriptor.py`
- `core/ruleset.py`
- `rules/source_catalog.py`
- `rules/source_packages/warhammer_40000_11th/`
- `tests/code_quality/`

Invariants:

- `warhammer_40000_11th` is the sole active edition ID;
- source package IDs, source titles, descriptor hashes, fixtures, replay payloads, and docs use 11th Edition identity;
- retired edition strings are allowed only in archived source-reference notes or migration scripts that are explicitly excluded from runtime imports;
- no runtime handler branches on old-vs-new edition behavior;
- source package manifests cite the local 11th Edition Core Rules PDF and app/codex/mission sources when added.

Required tests:

- static audit rejects active runtime/test references to retired edition IDs;
- ruleset descriptor hash is deterministic and 11th Edition-only;
- source package payloads round-trip with 11th Edition IDs;
- no compatibility shim can instantiate a retired ruleset.

## Phase 14B: timing windows, active player, and phase skeleton cutover

Status: Complete.

Invariants:

- battle rounds expose Start of Battle Round, Player Turns, and End of Battle Round windows;
- each turn exposes Start of Turn, the five phases, and End of Turn;
- each phase exposes explicit Start and End windows;
- end-of-phase, end-of-turn, and end-of-battle-round windows resolve non-mission rules before mission rules;
- active/opposing player state follows the 11th Edition selection exceptions for move, shoot, and fight resolution;
- Fire Overwatch and Rapid Ingress anchor to the End of Opponent's Movement phase window.

Required tests:

- timing-window records serialize without object reprs;
- phase/turn/battle-round end ordering is deterministic;
- active player changes during selected unit move/shoot/fight scopes and restores afterward;
- end-of-opponent-Movement reactions are emitted in the correct order.

## Phase 14C: shared primitives cutover

Status: Complete.

Invariants:

- Engagement Range is 2" horizontally and 5" vertically;
- coherency is one-neighbor within 2"/5" plus every-model max spread within 9"/5";
- rotations cost 0" for every base/frame shape;
- retired pivot-cost policy, descriptors, and tests are removed or made audit failures;
- `FRAME` measurement uses closest point on the model rather than base-only measurement;
- `M "-"`, `OC "-"`, and InSv characteristics are represented as typed characteristic values;
- numeric `0` characteristics can be changed by modifiers, but characteristics
  depicted as `-` or replaced by `-` cannot be changed by numeric modifiers;
- Detection Range is a unit characteristic, defaults to 15", is lower-is-better,
  and is consumed by Hidden detection checks;
- halve-damage effects apply after all other Damage modifiers;
- Battle-shocked units use OC "-" semantics, cannot be targeted by controlling-player Stratagems, and cannot start or complete actions;
- hazard rolls are unit-level rolls that allocate mortal wounds through the 11th Edition mortal-wound sequence.

Required tests:

- static audit rejects pivot-cost policy usage;
- Engagement Range and coherency descriptors match the 11th Edition values;
- `FRAME` measurement and rotation witnesses round-trip;
- `0` modifier, `-` modifier rejection, Detection Range modifier, and
  halve-damage-after-modifiers cases are covered by shared characteristic tests;
- Battle-shock persistence and recovery use the Command phase Battle-shock step;
- hazard rolls inflict 1 mortal wound, or 3 mortal wounds when every model is a `MONSTER`/`VEHICLE`.

## Phase 14D: movement, terrain, objectives, and actions cutover

Status: Complete.

Invariants:

- Movement phase selection covers every friendly unit, including units in Strategic Reserves and embarked units;
- Ingress Moves for reserve arrivals are selected inside Move Units, with no
  separate Reinforcements step;
- move-type selection is a finite decision and Remain Stationary triggers no start/end move rules;
- Fall Back mode selection supports Ordered Retreat and Desperate Escape;
- `MONSTER` and `VEHICLE` units can move through friendly and enemy models that
  are not `MONSTER` or `VEHICLE` only when making Normal or Advance moves;
- Flying units can optionally take to the skies for Normal, Advance, and Fall
  Back movement-phase actions through finite option IDs and parameterized
  proposal payload context, subtracting 2" unless `HOVER` applies; when a
  `HOVER` unit takes to the skies, the 2" subtraction is not applied. Charge
  integration remains a Phase 15 charge-move task;
- terrain areas and Exposed/Light/Dense categories replace retired terrain-feature policies;
- Dense movement, vertical movement, stable non-ground endpoints, Solid, Hidden,
  Gone to Ground, Obscuring, and Benefit of Cover are represented from
  structured terrain descriptors;
- objectives are terrain objectives by default; 40 mm markers are only the fallback when an objective point does not coincide with a terrain area;
- objective markers can be moved through and ended on;
- Secured objectives persist until the opponent's level of control is greater at the end of a phase;
- action start/cancel/complete rules are engine-owned and replay-facing.

Required tests:

- fall-back mode decisions validate battle-shocked and non-battle-shocked cases;
- adapter proposal tests reject stale, drifted, and malformed `movement_mode` and `fall_back_mode` submissions before queue pop where required by the Phase 11D contract;
- reserve-arrival Ingress choices occur during Move Units and use more-than-8"
  enemy-distance validation where applicable;
- Monster/Vehicle model traversal is legal for Normal and Advance moves only and
  remains illegal through other Monster/Vehicle models;
- FLY take-to-the-skies changes pathing and movement budget deterministically,
  including the no-2" subtraction rule for `HOVER` units;
- terrain visibility and terrain movement consume terrain-area descriptors,
  including Light/Dense Hidden eligibility and Gone to Ground detection modifiers;
- objective-control geometry supports terrain areas and marker fallback;
- action cancellation rejects moves other than pile-in/consolidation and rejects leaving the battlefield.

## Phase 14E: attack sequence and allocation cutover

Status: Complete.

Implemented in the current cutover slice:

- attacks are gathered by target and identical attack profile;
- supported identical fixed-damage shooting pools, including timing-sensitive
  shooting-compatible weapon abilities, use the grouped allocation host:
  Hit and Wound rolls for the pool are resolved before allocation, save rolls
  are made before damage, and failed saves resolve from lowest to highest;
- melee weapon target splitting is declared in the Select Targets step;
- Benefit of Cover worsens BS by 1 before Hit rolls;
- Plunging Fire improves BS by 1 when the 3"+ terrain-height or `TOWERING` within-12" conditions are met and the visible target unit contains a model on ground level;
- unmodified save rolls of 1 fail before InSv/Sv evaluation;
- allocation groups are created from runtime attached-unit role metadata, with
  one group for each eligible Character model and profile groups for
  non-Character models sharing W, Sv, and InSv;
- defender allocation order is automatic when the 11th Edition priority tiers
  force a single order, and uses finite `select_allocation_order` requests only
  when more than one legal same-tier group ordering exists. Request payloads
  include group IDs, model IDs, group role, W/Sv/InSv profile, wounded state,
  Bodyguard/Leader/Support evidence, legality reasons, and Precision priority
  group IDs when applicable;
- if the current allocation group has an Invulnerable Save, that InSv is
  mandatory and the defender cannot choose an armour Save instead;
- armour Saves with AP modifiers are used only when the current allocation
  group has no Invulnerable Save;
- current allocation group damage handles wounded models first and changes to
  the next selected ordered group only after the current group is exhausted or
  destroyed;
- `[PRECISION]` selection is pool-scoped by visible eligible Character
  allocation group. In the grouped host, the attacker-selected Character group
  is promoted to the front of the legal allocation order until those attacks
  resolve or that Character group is destroyed, then remaining failed saves
  return to the normal ordered groups;
- grouped Lethal Hits, Sustained Hits, Anti, Twin-linked, Melta, Torrent, and
  Devastating Wounds preserve critical Hit/Wound timing through the grouped
  host;
- normal damage resolves before routed mortal wounds for mixed sequences;
- `[DEVASTATING WOUNDS]` inflicts mortal wounds equal to Damage after normal damage and cannot spill one critical wound beyond one destroyed model;
- `[CLEAVE X]` is a structured weapon ability descriptor and helper that adds
  X attacks per five target-unit models when one target was selected for all of
  that weapon's attacks, and the Phase 15 melee declaration host gathers those
  additional attacks into the shared attack sequence;
- `[LANCE]` records a charge-gated melee targeting rule ID when the attacking
  unit made a Charge move this turn, and the shared attack sequence applies the
  capped +1 Wound-roll modifier from that rule ID;
- derived terrain objectives use terrain-area containment for model
  contribution; the objective marker radius is not used to count models outside
  the terrain area.

Implemented tests:

- identical attack grouping and melee split declarations round-trip;
- mandatory Invulnerable Save precedence is covered and emits no defender
  armour-versus-invulnerable choice;
- allocation-order decisions validate stale, wrong-actor, wrong-option, and
  JSON-safe record payloads before mutation;
- allocation-order requests emitted from grouped wound pools carry all wounded
  attack contexts before any save is rolled, and only expose defender choices
  between legal same-tier group orders;
- grouped save rolling occurs before damage, and low-to-high save-result damage
  resolution is deterministic;
- grouped failed-save damage transitions to the next ordered allocation group
  when the current group is destroyed or exhausted;
- grouped Precision promotes the attacker-selected Character allocation group
  before ordinary defender group ordering, then returns remaining failed saves
  to Bodyguard/non-Character groups after that Character group is destroyed;
- grouped Lethal Hits, Sustained Hits, and Devastating Wounds regressions prove
  critical timing, generated-hit wound resolution, post-normal deferred mortal
  wound routing, and one-destroyed-model-per-critical Devastating Wounds caps;
- cover and Plunging Fire modify BS, not AP or saves;
- Precision Character allocation-group selection persists for the current pool
  and returns to ordinary allocation after that selected Character group is
  destroyed;
- derived terrain objective tests prove models outside the terrain area do not
  contribute through the marker control radius;
- Devastating Wounds and hazard mortal wounds allocate through the shared mortal-wound service.

## Phase 14F: shooting cutover

Status: Complete.

Phase 14F completes the shooting-type cutover. The active player selects an eligible unit, then answers the finite `select_shooting_type` decision before the engine emits the parameterized shooting declaration request. The selected shooting type is preserved through declarations, attack pools, replay payloads, supported grouped attack resolution, allocation-order decisions, saves, damage, and Fire Overwatch Snap Shooting. Phase 14E supplies the grouped attack/allocation host used by this shooting cutover.

Indirect and Snap Shooting now attach deterministic no-Hit-reroll rule IDs to Hit-roll specs, and the dice/Command Re-roll paths reject reroll windows for those rolls before mutation. Units that shoot in the Shooting phase are excluded from Mission Action start options until the phase ends through the shared action decision path.

Invariants:

- Shooting type is an engine-enumerated decision: Normal, Assault, Close-quarters, Indirect, or source-provided types such as Snap Shooting;
- in-phase Shooting uses `select_shooting_type` as a finite active-player decision between unit selection and shooting declaration;
- `[CLOSE-QUARTERS]` and `[PISTOL]` are identical for all rules purposes;
- non-`MONSTER`/non-`VEHICLE` close-quarters shooting can only select `[CLOSE-QUARTERS]` weapons and engaged targets;
- `MONSTER`/`VEHICLE` close-quarters and engaged-target shooting apply the correct -1 Hit modifier except for qualifying `[CLOSE-QUARTERS]` attacks;
- `[BLAST]` weapons cannot target engaged units through close-quarters or engaged `MONSTER`/`VEHICLE` shooting;
- Indirect shooting can only declare `[INDIRECT FIRE]` weapon profiles, grants cover, forbids hit rerolls, and has the 1-5/1-3 unmodified fail policy;
- Snap Shooting targets one visible enemy unit within 24", hits only on unmodified 6, and forbids Hit-roll rerolls;
- after a unit shoots in the Shooting phase, it cannot start a Mission Action until the phase ends.

Required tests:

- shooting-type finite decisions reject stale, drifted, wrong-actor, and wrong-option submissions before mutation;
- close-quarters weapon-selection and target restrictions are enforced per model keyword;
- engaged `MONSTER`/`VEHICLE` shooting and `[BLAST]` FAQs are regression-tested;
- indirect and snap policies interact correctly with Torrent, Heavy, cover, supported grouped attacks, and reroll permissions;
- Assault/Advanced, Close-quarters/Blast, Monster/Vehicle, Indirect, Fire Overwatch/Snap, and action-start lock tests exercise the full lifecycle decision path.

## Phase 14G: charge and fight source contract

Status: Implemented. This phase freezes the typed `RulesetDescriptor.charge_policy` and `RulesetDescriptor.fight_policy` payloads, plus deferred unsupported Core Stratagem hooks for Charge/Fight-owned Core Stratagems.

Phase 14G does not implement Charge/Fight. It freezes the 11th Edition Charge/Fight contract that Phase 15 must implement directly, so there is no temporary retired-edition Charge/Fight path to correct later.

Invariants:

- charge declaration validates within-12", unengaged, no Advance/Fall Back, and battlefield presence;
- charge-target selection happens after the charge roll and requires targets within both 12" and the rolled maximum distance;
- charge moves must end closer to targets, within 1" if possible, engaged if possible, engaged with every target, and not engaged with non-targets;
- charging grants Fights First until end of turn;
- Fight phase has Start, Pile In, Fight, Consolidate, and End steps;
- a unit is eligible to fight if it has not already been selected to fight this
  phase and it made a Charge move this turn, is currently engaged, or was
  engaged at the start of the Fight step;
- both players make pile-in and consolidation moves, active player first;
- Fights First and remaining combats alternate per the PDF sequence;
- eligible-to-fight pass is available when all of a player's eligible units are more than 5" from enemy units;
- Normal Fight and Overrun Fight are explicit fight types;
- consolidation mode selection supports Ongoing, Engaging, and Objective modes, including opponent fight selection for newly engaged unfought units.

Required Phase 15 tests:

- charge-target and charge-move proposals validate path witnesses and target constraints;
- Pile-in and consolidation use group-aware movement APIs;
- fight eligibility covers units that charged this turn, units currently
  engaged, and units engaged at the start of the Fight step;
- Fight selection pass and Fights First fallback ordering are deterministic;
- Overrun Fight cannot be selected unless the unit is otherwise eligible to fight;
- Engaging Consolidation emits opponent fight decisions for newly engaged eligible units.

## Phase 14H: advanced rules cutover

Status: Complete. Phase 14H is complete for the current source-backed advanced
rules cutover. Runtime army-list Attached Unit formation is implemented from
structured army-list Leader/Support declarations and catalog attachment eligibility; it
emits first-class attached rules-unit formation records, derives attached-unit
Starting Strength until split, restores component Starting Strength records when
the formation splits, and feeds the existing Bodyguard/Leader/Support role
evidence used by Shooting acting-unit selection, attacks, healing, revival,
persisting effects, and stratagem target canonicalization. Phase 16D now
supplies the strict roster/runtime provenance layer for Warlord, Enhancement,
legality, Dedicated Transport manifest records, and army definitions that
`GameState` reconciles into Starting Strength records for attached-unit and
transport hosts.
Broader real-faction Leader/Support eligibility data ingestion remains future
source/catalog work, not a Phase 14H runtime blocker.
Completed source-backed slices from Phases 10P-10S, 11C, 13E, 14D, 14K, 15B,
and 15D cover Strategic Reserves arrival, Deep Strike placement, Tactical/Rapid
and destroyed-Transport Disembark payloads, Emergency Disembark resolver
behavior, Combat Disembark's direct 6" Hazard Roll resolver,
destroyed-Transport Emergency Disembark orchestration from actual destruction
timing before Transport removal and Deadly Demise resolution, surge movement
restrictions, Aircraft/Hover movement and reserve transitions, reserve-arrival
policy hardening, Aircraft charge/fight exclusions, exact At Half-strength
payload state, runtime added-unit Starting Strength records, setup-time Strategic Reserve declarations,
battle-formation Transport embarkation,
repositioned-unit Advance/Fall Back/Disembark history preservation, and attack
destruction timing. Attached-unit mixed-Toughness attack handling now uses the
source-backed Bodyguard/Leader/Support rule: attacks use the highest alive
Bodyguard Toughness while any Bodyguard models remain, otherwise the highest
alive Leader/Support/character Toughness. Direct Combat/Emergency transport
hazard damage now routes through the shared mortal-wound and Feel No Pain
service. Movement-phase Combat Disembark fallback now accepts Combat mode only
when the pending placement proposal advertises that fallback and the engine
first proves the same submitted placement is invalid as Tactical Disembark.
Healing Wounds primitive now iterates each healing amount in order, heals
wounded models before REVIVED returns, uses opposing-player finite model
selection for ambiguous attached-unit wounded/revival choices, and validates
REVIVED placement against Starting Strength, phase-start coherency, removed
model identity, and engagement restrictions.

Phase 14D follow-up findings for movement-mode exposure, Fall Back mode
payloads, and runtime Mission Action interruption are complete in Phase 14D.

Invariants:

- Transport capacity, multiple embarked units, battle-formation Embark, post-move Embark, Rapid/Tactical/Combat Disembark, Emergency Disembark, and destroyed-transport timing are source-backed and replay-facing;
- Embark after the first battle round has started is legal only after a Normal, Advance, or Fall Back move, only if every model is within 3" of a friendly `TRANSPORT`, the unit was not set up on the battlefield this turn, the unit is datasheet-eligible for that Transport, the Transport has sufficient remaining model capacity, and the engine removes the unit from the battlefield into that Transport's cargo state with deterministic removal records;
- Disembark is legal only for a unit embarked within a `TRANSPORT` model that is on the battlefield, only if that unit did not Embark within that Transport this phase, and only if that Transport has not Advanced or Fell Back this phase;
- Disembark uses an explicit source-backed mode enum and replay payload for `rapid_disembark`, `tactical_disembark`, `combat_disembark`, `destroyed_transport`, and `emergency_disembark`; any new adapter-visible mode, option family, proposal payload, or event shape must update `docs/ADAPTER_DECISION_CONTRACT.md` in the same implementation PR;
- Rapid Disembark uses 3" wholly-within setup, is mandatory after the Transport makes a Normal or Ingress move, prevents charges until end of turn, and if the Transport made an Ingress move this turn the disembarking models must inherit the same setup restrictions that constrained the Transport's Ingress placement;
- Tactical Disembark uses 3" wholly-within setup, is mandatory when the Transport remained stationary or has not yet been selected to move and a legal 3" setup exists, forbids Remain Stationary, and immediately routes the unit through the shared Movement phase decision path for a Normal or Advance move;
- Combat Disembark uses 6" wholly-within setup when Rapid/Tactical conditions do not apply, makes one Hazard roll for each model through the shared Hazard/mortal-wound allocation service, can set up engaged only with enemy units that the Transport is engaged with, writes through Battle-shock, and prevents charges until end of turn;
- Emergency Disembark uses 6" wholly-within setup for units embarked in a Transport that was just destroyed, makes one Hazard roll for each model before setup through the shared Hazard/mortal-wound allocation service, requires each model to be set up as close as possible to that Transport, destroys each model that cannot be placed that way, writes through Battle-shock, and prevents charges until end of turn;
- destroyed-Transport Disembark/Emergency Disembark orchestration happens from the real destruction event before Transport removal and before Deadly Demise resolution according to the source timing, with embarked units not using stale battlefield placements or endpoint-only movement shortcuts;
- Attached units support runtime-instantiated attached rules units from army-list
  Leader and Support declarations, one Leader and one Support per Bodyguard
  unless stated, Bodyguard Toughness for incoming attacks, keyword union without
  model keyword inheritance, and source-scoped ability persistence;
- Strategic Reserves use 50% points cap, 6" edge setup, more-than-8" enemy distance, pre-third-round opponent-deployment-zone restriction, and third-round destruction exceptions;
- repositioned units preserve move history and persisting effects;
- Surge moves require the source trigger, non-Battle-shocked/unengaged/not-moved state, closest enemy target, no non-target engagement, and no further movement that phase;
- Aircraft start in Strategic Reserves, only make ingress moves, return to Strategic Reserves at the end of the opponent's turn, and follow the PDF charge/fight/Plunging Fire exclusions;
- revived models keep starting wargear/enhancements, cannot exceed starting strength, must set up in coherency with phase-start battlefield models, and can be engaged only with enemies already engaged with the unit;
- healing/revival effects can return destroyed models from a fully destroyed
  Bodyguard component while a Leader/Support component remains in the Attached
  unit, and this must not expand any component or attached rules unit above its
  starting strength.

Required tests:

- each transport mode has valid, invalid, replay, stale/drift/malformed submission, deterministic payload, and viewer-safe event/projection coverage;
- Embark tests cover Normal, Advance, and Fall Back triggers; reject Remain Stationary, units set up this turn, wrong-player or non-Transport targets, datasheet-ineligible units, insufficient capacity, same-phase Disembark-then-Embark without an explicit typed override, and every-model-within-3" failures without mutation;
- Rapid Disembark tests cover post-Normal and post-Ingress Transport movement, 3" wholly-within placement, no-charge state, and inheritance of Ingress restrictions such as enemy-distance and deployment-zone bans;
- Tactical Disembark tests prove a legal 3" setup before a stationary/not-yet-selected Transport forces the Tactical mode, excludes Remain Stationary, routes to Normal/Advance movement through the shared Movement decision path, and rejects Fall Back unless an independent rule makes Fall Back legal;
- Combat Disembark tests prove the 6" setup distance, fallback from impossible Tactical placement, one Hazard roll per model through the shared Hazard/mortal-wound service, Battle-shock/no-charge write-through, and the narrow permission to set up engaged only with enemies engaged with the Transport;
- Emergency Disembark tests prove 6" closest-possible placement, destruction of unplaceable models, Hazard/mortal-wound allocation, Battle-shock/no-charge write-through, replay serialization, and no stale endpoint-only placement acceptance;
- destroyed Transport orchestration tests prove Disembark/Emergency Disembark occurs from actual damage/destruction timing before Transport removal, does not leak through Deadly Demise ordering, and records deterministic placement/removal/damage/action-state effects;
- attached-unit mixed-Toughness attack tests prove Bodyguard Toughness is used
  while any Bodyguard model remains, and Leader/Support Toughness is used once
  no Bodyguard model remains;
- attached-unit Shooting selection tests prove a mustered formation is offered
  once under the attached rules-unit ID, cannot shoot again through Leader or
  Support component IDs, and range checks ignore fully destroyed unplaced
  components;
- attached-unit formation is instantiated at runtime from valid army-list
  declarations and emits replay-safe component role metadata;
- attached-unit ability persistence ends when the relevant source model/unit is destroyed and resumes if revived;
- Healing Wounds tests prove wound-first iteration, no-effect drain, finite
  opposing-player selection for ambiguous wounded and revival candidates,
  stale-candidate rejection before queue pop, replay-safe payload round-trip,
  and REVIVED placement validation without mutation on invalid placement;
- Strategic Reserves and Deep Strike use their distinct source policies: Deep
  Strike Ingress requires every model in the unit to have Deep Strike, permits
  setup within the opponent's deployment zone, and still requires more-than-8"
  horizontal distance from all enemy units;
- repositioned units preserve advance/fall-back/disembark history;
- Surge and Aircraft restrictions are regression-tested;
- revival placement honors attached-unit and engagement constraints;
- fully destroyed Bodyguard models can be revived by an attached Leader/Support
  source while the Attached unit still exists, without exceeding starting
  strength.

## Phase 14I: Core Stratagems and core abilities cutover

Status: Complete. Phase 14I is complete for the current source-backed Core
Stratagem and core ability cutover. All current 11th Edition Core Stratagem
source rows use supported handlers; Command Re-roll, Insane Bravery, New
Orders, Rapid Ingress, Fire Overwatch, Smokescreen, Explosives, Heroic
Intervention, Counteroffensive, Crushing Impact, and Epic Challenge resolve
through the shared Stratagem decision, CP ledger, timing-window, proposal, and
replay paths. The ability catalog keeps core abilities as typed source rows:
implemented handlers execute through the ability registry or phase-owned
runtime hosts, while future ability families remain explicit unsupported
descriptors with owning phase IDs instead of fallback parsing. The implemented
duplicate weapon ability lifecycle slice is the Shooting declaration `[ANTI]`
path; other duplicate families still require future host-specific threading
before their gameplay effects can be marked complete.

Invariants:

- Core Stratagem package contains Command Re-roll, Epic Challenge, Insane Bravery, New Orders, Explosives, Crushing Impact, Rapid Ingress, Fire Overwatch, Smokescreen, Heroic Intervention, and Counteroffensive;
- Command Re-roll excludes Leadership and Battle-shock rolls, permits one die of a multi-dice roll except Charge rolls, and consumes Phase 10J reroll semantics;
- New Orders costs 1 CP, can be used only once per game, discards one retained
  Secondary Mission card, and immediately draws one replacement Secondary Mission
  card;
- Heroic Intervention supports Leap to Defend and Into the Fray modes, including the optional +1 CP section;
- duplicate core/weapon ability instances are not cumulative, regardless of
  included numbers or keywords;
- duplicate core ability instances require deterministic controlling-player
  selection at the timing the source ability applies, unless the source rule
  forces a unique instance;
- duplicate weapon ability instances require deterministic controlling-player
  selection each time the unit makes attacks in the Select Weapons step before
  their effects can resolve; the implemented lifecycle wiring currently covers
  Shooting declarations with duplicate `[ANTI]` descriptors, and other weapon
  duplicate families remain future/unsupported until their hosts carry the
  selected descriptor ID into attack resolution;
- duplicate selection requests and forced duplicate-resolution records preserve
  ability family, source IDs, selected source instance, timing window, affected
  unit/weapon context, and JSON-safe replay metadata;
- multiple instances of a numbered core ability are duplicates even when the
  number varies;
- multiple instances of a numbered weapon ability are duplicates even when the
  number varies; lifecycle completion for numbered weapon families requires
  future Select-Weapons threading and regressions;
- multiple instances of a keyworded weapon ability are duplicates even when the
  keyword varies; the completed lifecycle slice covers duplicate `[ANTI]`
  descriptors in Shooting declarations and does not mark other keyworded
  families complete;
- keyword-gated weapon abilities apply only to target units with at least one listed keyword;
- `[HUNTER X]` is target eligibility, not an attack modifier: the weapon can
  only be declared into units matching at least one listed keyword;
- future ability-runtime families such as `STEALTH`, `[PSYCHIC]`,
  `[ONE SHOT]`, `HOVER`, Super-heavy Walker, and `MOBILE` remain future
  runtime work until an owning phase adds source-backed hosts, adapter-contract
  updates for player-facing choices, and focused regressions; Phase 14I records
  their source-backed contracts or explicit unsupported descriptors, but does
  not mark those runtime effects complete;
- core abilities listed in the 11th Edition Core Rules are either implemented with source-backed tests or explicitly unsupported with reason.

Required tests:

- Core Stratagem catalog source IDs and CP costs round-trip;
- each Core Stratagem has target-binding, CP ledger, timing-window, and replay coverage;
- New Orders rejects second use in the same game and emits deterministic
  discard-and-replacement-draw mission deck records;
- duplicate ability selection tests prove implemented duplicate core/weapon
  paths are non-cumulative, source-linked, deterministic, and adapter-visible
  when a player choice exists;
- duplicate selection replay tests cover implemented duplicate paths with
  stale/drifted submissions and no Python object reprs or memory addresses;
  numbered weapon families and non-Anti keyworded weapon families require
  additional tests before lifecycle completion is claimed;
- duplicate `[ANTI]` weapon tests prove selection happens in Select Weapons for
  Shooting declarations and that unselected matching Anti descriptors do not
  affect Wound resolution; other duplicate weapon families remain required
  future coverage;
- Hunter X target declaration accepts at least one listed keyword match and
  rejects target units with none;
- future ability-runtime families such as `STEALTH`, `[PSYCHIC]`,
  `[ONE SHOT]`, `HOVER`, Super-heavy Walker, and `MOBILE` require focused
  implementation tests, replay coverage, and adapter-contract updates in their
  owning phases before runtime completion can be claimed;
- every supported core ability has focused tests and an unsupported-descriptor audit row where not yet implemented.

## Phase 14J: mission and catalog replacement

Status: Complete for the current source-backed slice. The engine now records the
five 11th Edition Force Dispositions, the 25-cell player-vs-opponent Primary
Mission matrix with source-tracked mission names, three layout identifiers per
cell, and engine-achievement-gated Tactical Secondary score/retain as an
adapter-visible finite decision. Phase 17J now layers the Warhammer Event
Companion package over this slice with implemented matrix rows, concrete layout
descriptors, and explicit Tactical/Fixed Secondary procedure descriptors rather
than guessed runtime prose.

Invariants:

- mission packs, deployment maps, terrain layouts, actions, scoring, datasheets, keywords, detachments, enhancements, and faction rules are imported as 11th Edition source packages;
- 11th Edition Primary Mission source data records the five Force Dispositions
  (`Purge The Foe`, `Take And Hold`, `Disruption`, `Reconnaissance`, and
  `Priority Assets`), the deterministic 5x5 player-vs-opponent matrix, the
  source-tracked Primary Mission name for each matrix cell, and three
  source-tracked battlefield layout identifiers per matrix cell;
- Chapter Approved matrix cells whose Primary Mission rules or layout geometry
  are not yet known remain `awaiting_source`, while the Phase 17J Event
  Companion package carries implemented source descriptors for all 25 matrix
  cells and all 45 source-page layout identities;
- mustering source data follows the 11th Edition order: select Battle Size,
  start Army Roster, choose Faction, select Detachment Rules, select Units, then
  promote Warlord;
- CORE V2 currently supports only Strike Force army construction: 2000 points,
  a 60" x 44" battlefield expectation, 3 Detachment Points, Enhancement Limit
  4, and Unit Limit 3 doubled for `BATTLELINE`; smaller battle sizes are
  explicit unsupported inputs, not fallback modes;
- active army catalogs must exclude Combat Patrol, Legends, Forge World, Kill
  Team, and other non-matched-play content scopes instead of filtering them by
  names or tolerating them during mustering;
- detachment point costs are source data, and missing values remain
  awaiting-source rows rather than defaults;
- Leader and Support Attached Units are declared on the army list, Enhancements
  are selected after Attached Units are created, no attached squad can have more
  than one Enhancement, and the Warlord must share the army Faction keyword;
- current Phase 14J mission deck source data grants two Secondary Missions per
  player turn, keeps Secondary Missions until scored or discarded, and does not
  replace ordinary Tactical-discarded Secondary Missions immediately outside
  Warhammer Event mode;
- Warhammer Event mode Tactical Secondary start-of-Command draw-two,
  end-of-Command once-per-battle 1CP discard-and-replacement draw,
  end-of-turn achievement discard only when VP is gained, and own-turn
  discard-one-or-more-for-1CP behavior are owned by Phase 17J as part of the
  Tactical Secondary procedure itself;
- when a Tactical Secondary Mission Card's requirements are achieved, the engine
  records a source-backed achievement context before emitting the finite scoring
  decision: scoring awards the source-backed VP, consumes the context, and
  discards the card, while declining to score consumes that finite context,
  awards no VP, and keeps the card retained;
- Phase 17J records the Event Companion Tactical discard, replacement draw, and
  CP reward timing as source descriptors; future runtime expansion must consume
  those descriptors through the existing decision path rather than adding a
  parallel Secondary Mission adapter route;
- scoring source data caps Primary at 45 VP, Secondary at 45 VP, Battle Ready at
  10 VP, total score at 100 VP, and Primary and Secondary scoring at 15 VP per
  battle round;
- source imports reuse the existing normalization/ETL boundary but produce 11th Edition package IDs and hashes;
- old source snapshots are not selectable as active game content;
- catalog/reporting distinguishes implemented, unsupported, and awaiting-source rows without silently substituting retired data.

Required tests:

- package hashes are deterministic;
- retired source packages cannot be selected for a new game;
- representative mission/action/scoring rows load from 11th Edition source identity;
- Force Disposition rows and all 25 Primary Mission matrix cells load,
  round-trip, preserve source names, preserve `awaiting_source` status, and
  expose exactly three layout identifiers per cell;
- Strike Force mustering policy enforces point, Detachment Point, Enhancement
  Limit, Unit Limit, doubled `BATTLELINE`, attachment, Enhancement, and Warlord
  faction-keyword rules, and rejects unsupported battle-size inputs;
- Secondary Mission draw/retain/no-hand-size-cap/discard for the Phase 14J
  source slice, plus 45/45/10/100 and 15-per-round VP caps, load from source
  data and round-trip through mission scoring fixtures; Event Companion Tactical
  replacement-draw procedure coverage is owned by Phase 17J;
- Tactical Secondary score/retain decisions require a recorded engine-owned
  achievement context, use deterministic option IDs, reject drift before queue
  pop, award/discard only when the player chooses to score, and keep the card
  active when the player declines to score;
- coverage report groups awaiting-source rows separately from unsupported rule shapes.

## Phase 14K: cutover hardening and static audits

Status: Complete.

Invariants:

- CI fails on active retired edition IDs, pivot-cost policies, old terrain kinds, old cover save/AP exceptions, optional armour-versus-invulnerable save choice, 1" engagement, old coherency thresholds, Battle-shock auto-expiry, separate Reinforcements phase steps, 9" reserve-arrival enemy-distance policies, replacement draws outside authorized source-backed procedures, retired Core Stratagem names, and old Aircraft minimum-move policy;
- grouped Inflict Damage never auto-selects among multiple legal models inside the current allocation group; the defending player selects a legal model through `select_damage_allocation_model`, while wounded-model priority and single-model forced choices remain engine-owned validation;
- replay fixtures and canonical JSON payloads are regenerated for 11th Edition-only identifiers;
- no adapter, headless, UI, network, AI, or test path can choose a retired ruleset;
- `ARCHITECTURE_V2.md`, `README.md`, and source-package docs agree on 11th Edition-only scope.

Implemented tests:

- static audits fail on active retired rule-shape identifiers for edition identity,
  pivot-cost policy, attack/save choice surfaces, old aircraft minimum-move and
  pivot-limit policy, reserve-arrival source-step and enemy-distance policy,
  descriptor primitive drift, and retired Core Stratagem names;
- attack/save cutover audit rejects retired save-kind and attack-allocation decision surfaces and confirms the current-group damage model decision plus pre-pop selected-model legality validation are registered in runtime and the adapter contract;
- grouped Inflict Damage tests cover valid defender model selection, wounded-model forced auto-selection, selected-model death drift, wounded-model-priority drift, stale and malformed submission rejection before queue pop, and JSON-safe request/result/decision round-trip;
- representative smoke game reaches the current implemented phase using 11th Edition descriptors only;
- replay determinism holds after fixture regeneration;
- import-linter and decision-contract audits still pass.

---

# Charge and Fight phases

Phase 15 implements Charge/Fight from the Phase 14G source contract. Do not introduce an interim Charge/Fight behavior that conflicts with the 11th Edition migration contract.

## Phase 15A: Charge phase declaration and charge roll

Status: Complete.

Phase 15A makes charge eligibility, charging-unit declaration, and the deterministic 2D6 Charge roll use the shared adapter/lifecycle path. It does not select charge targets and does not move models; Charge Move target selection, "if you still want to" choice, path proposal, and endpoint validation are Phase 15B.

Modules:

- `engine/phases/charge.py`
- `engine/charge_declaration.py`
- `engine/movement_legality.py`
- `engine/dice.py` and Phase 10J dice/reroll helpers are consumed, not reimplemented
- `engine/decision_controller.py`
- `docs/ADAPTER_DECISION_CONTRACT.md`

Objects:

- `ChargePhaseState`
- `ChargeEligibilityContext`
- `ChargingUnitSelection`
- `ChargeTargetCandidate`
- `ChargeRollRequest`
- `ChargeRollResult`
- `ChargeDistanceState`

Invariants:

- all charging-unit declaration choices are player-facing decisions and must use `DecisionRequest` -> `FiniteOptionSubmission` -> `DecisionResult` -> `GameLifecycle.submit_decision(...)` -> `DecisionRecord`/`EventRecord`;
- Phase 15A must update `docs/ADAPTER_DECISION_CONTRACT.md` with every new charging-unit selection, charge-roll request, option payload, roll payload, and viewer-visibility rule introduced;
- finite charge options use deterministic option IDs and JSON-safe payloads;
- eligible charging units are derived from current state;
- charge declaration validates within-12" of a target, unengaged, no Advance/Fall Back this turn, and battlefield presence per the Phase 14G charge contract;
- units that Advanced/Fell Back cannot charge unless a rule permits;
- charge targets are not selected before the roll; the Charge Move step selects one or more targets after the roll from enemy units within both 12" and the rolled maximum distance;
- the charge roll is a deterministic, replay-facing 2D6 roll resolved immediately after the charging-unit declaration;
- charge-roll rerolls are explicit `DecisionRequest`s only when a legal reroll source exists, and Command Re-roll cannot reroll a Charge roll per the Phase 14I Core Stratagem contract;
- if no enemy unit is within both 12" and the rolled maximum distance, the charge resolves with no move, no model placement mutation, and no displacement records;
- if one or more enemy units are within both 12" and the rolled maximum distance, Phase 15A records `ChargeDistanceState`, emits `charge_move_required`, and requests the Phase 15B `submit_movement_proposal` Charge Move decision.

Required tests:

- charging-unit selection goes through finite `DecisionRequest`/`DecisionResult` submission and records deterministic JSON-safe `DecisionRecord`/`EventRecord` payloads;
- eligible charging-unit derivation rejects Advanced/Fell Back/engaged/off-battlefield units;
- the 2D6 charge roll is deterministic and replay-facing;
- a reroll request appears only with a legal reroll source and Command Re-roll cannot be applied to the Charge roll;
- a charge roll that reaches no enemy unit within both 12" and the rolled maximum distance resolves with no move;
- no-move Charge roll emits no displacement record and leaves charger placement unmutated;
- a reachable-target Charge roll emits a Phase 15B `submit_movement_proposal` request with the maximum distance and reachable-target snapshot.

CORE V1 relevant areas:

- `src/warhammer40k_ai/engine/decision_handlers/movement.py`
- `src/warhammer40k_ai/movement_distance.py`
- `src/warhammer40k_ai/utility/dice.py`

## Phase 15B: charge movement, terrain, FLY, and endpoint rules

Status: Complete.

Phase 15B resolves the post-roll Charge Move as a parameterized movement proposal that first selects one or more charge targets from enemy units within both 12" and the rolled maximum distance, then consumes the shared movement/pathing/terrain/coherency validators and enforces the Phase 14G charge-endpoint constraints. Charge moves require a `PathWitness` or a typed invalid/no-move result; endpoint-only validation is forbidden.

Modules:

- `engine/phases/charge.py`
- `engine/movement_proposals.py`
- `engine/movement_legality.py`
- `geometry/pathing.py`
- `geometry/terrain.py`
- `docs/ADAPTER_DECISION_CONTRACT.md`

Objects:

- `ChargeMoveProposal`
- `ChargeMoveResolution`
- `ChargeEndpointWitness`
- `ProposalValidationResult`
- `BattlefieldTransitionBatch`
- `PersistingEffect`

Invariants:

- charge moves are parameterized movement proposals submitted through `GameLifecycle.submit_decision(...)` and require a `PathWitness` or a typed invalid result; endpoint-only charge validation is forbidden;
- before moving, Phase 15B selects one or more charge targets from enemy units within both 12" and the rolled maximum distance, or records the active player's no-move choice when allowed;
- charge movement consumes the shared precise-distance, free-rotation, terrain, pathing, and coherency validators rather than reimplementing distance accounting;
- no model may move farther than the rolled charge distance;
- the resolved charge must end closer to one or more declared targets, end within Engagement Range of every declared target if possible, end within 1" if possible, and end not in Engagement Range of any non-target unit, per the Phase 14G charge-move contract;
- at least one charging model must satisfy the charge endpoint requirement or the charge is invalid and moves no models;
- charge endpoints use the 2"/5" engagement policy and the 11th Edition charge-target constraints; no retired terrain-type engagement exception is retained;
- charging over terrain and charging with `FLY` are distinct, descriptor-driven policies;
- charge movement emits displacement records only after all validators pass;
- charging grants Fights First until the end of the turn (recorded for Phase 15C fight-order state).

Required tests:

- charge-move proposal validates a `PathWitness` and rejects endpoint-only movement;
- charge move consumes precise-distance, free-rotation, terrain, pathing, and coherency validators;
- a charge that cannot place at least one model within Engagement Range of every declared target is invalid and moves no models;
- charge endpoint rejection when it would leave a non-target unit in Engagement Range;
- `FLY` charge and over-terrain charge follow distinct policies and produce distinct witnesses;
- charge move over the rolled distance for round, non-round, `VEHICLE`, `MONSTER`, and baseless `FRAME` models never debits distance for rotation;
- successful charge emits displacement records and records Fights-First status until end of turn;
- failed/invalid charge move does not mutate battlefield state.

CORE V1 relevant areas:

- `src/warhammer40k_ai/engine/decision_handlers/movement.py`
- `src/warhammer40k_ai/pathing/validation.py`
- `src/warhammer40k_ai/pathing/rules_profile.py`

## Phase 15C: fight order, Fights First, and remaining combats

Status: Complete.

Phase 15C owns the Fight-step ordering state inside the 11th Edition Fight phase. The outer Fight phase still exposes the Start, Pile In, Fight, Consolidate, and End steps, but the Fights First/Remaining Combats cursor, chooser alternation, Fight-step engagement snapshot, selected-to-fight set, pass state, activation records, and fight-interrupt source consumption belong to `FightOrderState`.

Pile In and Consolidate are separate both-player steps before and after the Fight step. Phase 15C exposes their step boundaries and the Fight-step snapshots needed by Phase 15D; it does not collapse normal fights into a per-activation Pile In -> attacks -> Consolidate flow.

Modules:

- `engine/phases/fight.py`
- `engine/fight_order.py`
- `engine/sequencing.py`
- `engine/timing_windows.py`
- `engine/reaction_queue.py`
- `docs/ADAPTER_DECISION_CONTRACT.md`
- `docs/DECISION_SUBMISSION_CATALOG.md`

Objects:

- `FightPhaseState`
- `FightStepState`
- `FightOrderState`
- `FightEligibilityContext`
- `FightActivationSelection`
- `FightsFirstRegistry`
- `EligibleToFightPass`
- `ResolvedFightInterrupt`
- `FightInterruptRequest`

Invariants:

- `FightPhaseState` is the outer phase envelope: battle round, active player, Start/Pile In/Fight/Consolidate/End step exposure, and references to the active Fight, movement, or attack sub-state;
- `FightPhaseState` does not directly own Fight-step ordering internals such as ordering band, chooser cursor, selected-to-fight units, pass state, activation sequence, or consumed interrupt sources except through nested `FightOrderState`;
- `FightOrderState` is replay-safe and owns the Fight-step-start engagement snapshot, current ordering band (`fights_first` or `remaining_combats`), next chooser, selected-to-fight unit IDs, activation selections, eligible-to-fight passes, and resolved fight-interrupt source records;
- the Fight phase has the Start, Pile In, Fight, Consolidate, and End steps per the 11th Edition source text;
- Start and End of Fight phase timing windows resolve phase-start and phase-end rules; they do not substitute for the Fight-step-start engagement snapshot;
- a unit is eligible to fight only if it has not already been selected to fight this phase and it made a Charge move this turn, is currently engaged, or was engaged at the start of the Fight step;
- Fight-step-start engagement is a distinct snapshot; current engagement is evaluated from current battlefield state rather than stored as a phase-start snapshot;
- `FightEligibilityKind` names and serialized payload tokens match source semantics: charged this turn, currently engaged, and engaged at the start of the Fight step;
- when a unit is selected to fight, the engine selects one legal fight type for that unit through the same lifecycle path;
- Normal Fight is legal only for an engaged unit;
- Overrun Fight is legal only when the unit is otherwise eligible to fight and is unengaged, or was unengaged at the start of the Fight step but became engaged during the Fight phase;
- Fights First Combats starts with the player whose turn it is;
- if the current Fights First chooser has no legal Fights First unit and no Fights First units are eligible, the sequence moves to Remaining Combats and that same player selects next;
- if the current Fights First chooser has no legal Fights First unit but at least one Fights First unit remains eligible for the other player, the other player selects next;
- Remaining Combats starts with the player who moved the sequence onto that step;
- if the current Remaining Combats chooser has no legal unit and no units are eligible, the Fight step ends;
- if the current Remaining Combats chooser has no legal unit but at least one unit remains eligible for the other player, the other player selects next;
- after resolving a Remaining Combats fight, if one or more Fights First units are now eligible, the sequence returns to Fights First Combats;
- charging units and Fights First effects are represented in fight-order state and Fights First is sourced from a structured registry, not ad hoc flags;
- fight activation selection is a player-facing `DecisionRequest` resolved through `GameLifecycle.submit_decision(...)` with deterministic option IDs and JSON-safe payloads;
- an eligible-to-fight pass is available to a player only when all of that player's eligible units are more than 5" from all enemy units;
- fight interrupts, such as Counter-offensive, use typed decision metadata and reuse the Phase 12A reaction queue rather than a private fight-order path;
- fight-interrupt resolution is source-scoped for the Fight phase: accepted and declined interrupt answers consume the underlying source effect ID, and later enemy activations cannot re-offer the same source with a new trigger event ID;
- stale, repeated-source, wrong-context, malformed, or ineligible fight-interrupt submissions reject before queue pop and before activation/decline records are created;
- fight-order resolution is deterministic and replay-safe;
- Phase 15C updates `docs/ADAPTER_DECISION_CONTRACT.md` with each new fight activation, eligible-to-fight pass, fight-type, and fight-interrupt decision payload.

Implemented test coverage:

- Fight phase exposes Start, Pile In, Fight, Consolidate, and End steps;
- `FightPhaseState` serializes only the outer phase envelope while `FightOrderState` serializes ordering internals and round-trips deterministically;
- fight eligibility covers units that charged this turn, units currently engaged, units engaged at the start of the Fight step, and the already-selected exclusion;
- Fights First combats resolve before Remaining Combats with the exact no-unit fallback, other-player fallback, and return-to-Fights-First behavior from the source text;
- fight activation selection goes through `GameLifecycle.submit_decision(...)` and round-trips deterministic JSON-safe `DecisionRecord`/`EventRecord` payloads;
- the eligible-to-fight pass is offered only when every eligible unit is more than 5" from all enemy units;
- Normal Fight and Overrun Fight enforce their distinct eligibility rules;
- a fight interrupt fires once at legal timing through the reaction queue and resumes the parent fight sequence;
- a declined fight interrupt consumes its source effect ID for the Fight phase and is not re-offered after a later enemy activation;
- an accepted fight interrupt consumes its source effect ID for the Fight phase and is not re-offered after a later enemy activation;
- a hand-crafted repeated-source fight-interrupt submission returns a typed invalid lifecycle status before queue pop, keeps the pending request clean, and records no new activation or decline event;
- fight order is deterministic and replay-safe across re-runs from `DecisionRecord`.

## Phase 15D: Pile In step, melee attacks, and Consolidate step

Status: Complete.

Phase 15D implements the physical movement and attack bodies around the Phase 15C fight-order decisions. Pile In is a separate both-player step before the Fight step. Melee attacks resolve when Phase 15C selects a unit to fight. Consolidate is a separate both-player step after the Fight step. Only Overrun Fight includes an activation-local additional pile-in move before attacks.

Pile In and Consolidate are fight movement displacements that require a `PathWitness` for physical movement, reject endpoint-only witnesses, and use the shared movement/pathing/terrain/coherency validators. Melee attacks reuse the Phase 13C attack-sequence infrastructure: fight declarations lower to ordinary attack pools, then Select Enemy Unit, Gather Attack Dice, hit, wound, allocation, save, damage, and reaction handling continue through the same engine path used by Shooting.

Modules:

- `engine/phases/fight.py`
- `engine/movement_proposals.py`
- `engine/movement_legality.py`
- `engine/attack_sequence.py`
- `engine/damage_allocation.py`
- `geometry/pathing.py`
- `docs/ADAPTER_DECISION_CONTRACT.md`

Objects:

- `FightMovementProposal`
- `FightMovementResolution`
- `MeleeDeclarationProposalRequest`
- `MeleeDeclarationProposal`
- `MeleeWeaponDeclaration`
- `MeleeTargetAllocation`
- `RangedAttackPool` reused as the shared attack-sequence pool type
- `FightDisplacementRecord`

Invariants:

- Pile In and Consolidate are model displacements, not Movement phase actions, and are submitted through `GameLifecycle.submit_decision(...)`;
- Pile In and Consolidate consume the shared movement/pathing/terrain/coherency validators and require a `PathWitness` or a typed invalid result; endpoint-only validation is forbidden;
- Pile In and Consolidate use the group-aware model APIs (`UnitGroup.alive_models()` / group-aware placement) when the rules operate on the attached rules unit as a whole;
- during the Pile In step, both players may make Pile In moves with eligible units they choose, active player resolving all such moves first, followed by the opponent;
- each unit can make no more than one Pile In move during the Pile In step;
- a Pile In move has a maximum distance of 3";
- a unit is eligible to Pile In during the Fight phase if it is engaged, made a Charge move this turn, or was selected to make an Overrun Fight this phase;
- before a Pile In move, an engaged unit selects every enemy unit it is engaged with as pile-in targets;
- before a Pile In move, an unengaged unit selects one or more enemy units within 5" as pile-in targets;
- models in base contact with one or more enemy models cannot be moved by a Pile In move;
- each model moved by a Pile In move must end closer to the closest pile-in target and engaged with that target if possible;
- after a Pile In move, the moving unit must be engaged;
- after a Pile In move, each model that started the move engaged with an enemy unit must still be engaged with that enemy unit;
- melee target selection follows engagement/eligibility rules and uses the 2"/5" engagement range with the 11th Edition terrain-area policies;
- while fighting, each fighting model must select one available non-extra melee weapon; `[EXTRA ATTACKS]` weapons can be added without counting as that primary selection;
- melee target declarations are scoped to the attacking model: each target unit must be engaged with the model that has the selected melee weapon;
- a melee weapon cannot declare more targets than its Attacks characteristic;
- when a melee weapon targets more than one unit, the declaration must allocate at least one attack to each target and exactly the fixed Attacks characteristic across all targets; random-Attacks split declarations return a typed invalid result until a fixed attack count is available;
- Normal Fight resolves Making Attacks for an engaged selected unit;
- Overrun Fight grants one additional Pile In move for that selected unit, then resolves Making Attacks;
- the melee attack sequence reuses the Phase 13C attack-sequence and damage-allocation infrastructure (Hit uses WS, then wound, allocate, save, damage) and the Phase 13D melee weapon-ability machinery, not a private melee resolver;
- during the Consolidate step, both players may make Consolidation moves with eligible units they choose, active player resolving all such moves first, followed by the opponent;
- each unit can make no more than one Consolidation move during the Consolidate step;
- a Consolidation move has a maximum distance of 3";
- a unit is eligible to Consolidate if it was eligible to fight this phase;
- before a Consolidation move, an engaged unit must choose Ongoing Consolidation and select every enemy unit it is engaged with;
- before a Consolidation move, an unengaged unit within 3" of one or more enemy units must choose Engaging Consolidation and select one or more of those enemy units;
- before a Consolidation move, an unengaged unit not within 3" of an enemy but within 3" of one or more objectives must choose Objective Consolidation and select one objective;
- Ongoing Consolidation cannot move models in base contact with enemy models, and each moved model must end closer to the closest selected enemy unit and engaged with it if possible;
- Engaging Consolidation requires each moved model to end closer to the closest selected enemy unit and engaged with it if possible;
- Objective Consolidation requires each moved model to end within range of the selected objective if possible, or closer to it if not;
- after Ongoing Consolidation, each model that started the move engaged with an enemy unit must still be engaged with that enemy unit;
- after Engaging Consolidation, the moving unit must be engaged with every selected enemy unit;
- after Objective Consolidation, the moving unit must be within range of the selected objective;
- Engaging Consolidation that engages enemy units not already selected to fight this phase requires the opponent to select those units one at a time; when each is selected, it becomes eligible to fight and is selected to fight;
- melee target declaration, Pile In/Consolidate proposals, and consolidation-mode selection are player-facing parameterized decisions with deterministic request/source context and JSON-safe payloads, and Phase 15D updates `docs/ADAPTER_DECISION_CONTRACT.md` for each.

Required tests:

- Pile In step offers active-player units before opponent units and never allows a unit to Pile In more than once during that step;
- Pile In and Consolidate proposals validate a `PathWitness` and reject endpoint-only movement;
- Pile In and Consolidation use group-aware movement APIs for attached rules units;
- Pile In target selection follows engaged-target and unengaged-within-5" branches;
- Pile In movement enforces base-contact immobility, closer-to-target movement, engage-if-possible, post-move engagement, and continuing engagement for models already engaged at move start;
- Overrun Fight's additional Pile In move is separate from the normal Pile In step and still enforces the Pile In movement constraints;
- melee target selection obeys engagement/eligibility rules and the 2"/5" engagement range;
- melee attacks resolve through the shared attack sequence and can destroy models, emitting removal records;
- melee weapon abilities resolve through the Phase 13D ability machinery in the melee context;
- Consolidate step offers active-player units before opponent units and never allows a unit to Consolidate more than once during that step;
- consolidation Ongoing, Engaging, and Objective modes each enforce their explicit endpoint rules;
- Engaging Consolidation emits opponent fight decisions for newly engaged eligible units;
- Pile In/Consolidate/melee declarations round-trip deterministic JSON-safe `DecisionRecord`/`EventRecord` payloads and reject stale/drift/malformed submissions without mutation.

## Phase 15E: fight-phase Stratagems and melee abilities

Status: Complete for the source-backed 11th Edition Core Stratagems listed in this phase: Heroic Intervention, Crushing Impact, Counteroffensive, and Epic Challenge. Generic fight-on-death, pile-in/consolidate modifier abilities, and broader melee weapon ability source coverage remain future source/generic-handler work unless a source-backed rule enters the catalog with a typed contract.

Modules:

- `engine/phases/charge.py`
- `engine/phases/fight.py`
- `engine/stratagems.py`
- `engine/stratagem_catalog.py`
- `engine/core_stratagem_effects.py`
- `engine/weapon_abilities.py`
- `engine/timing_windows.py`
- `engine/reaction_queue.py`
- `docs/ADAPTER_DECISION_CONTRACT.md`

Objects:

- `HeroicInterventionProposal`
- `CounterOffensiveInterrupt`
- `EpicChallengeBinding`
- `CrushingImpactResult`
- `FightFirstEffect`
- `FightOnDeathEffect`
- `MeleeWeaponAbilityEffect`

Initial coverage:

- Heroic Intervention;
- Crushing Impact;
- Counter-offensive;
- Epic Challenge;
- Fights First effects required by Heroic Intervention and Counteroffensive;
- Epic Challenge Precision effect for the selected Character model.

Invariants:

- charge/fight-coupled Core Stratagems reuse the Phase 12B Stratagem definition, decision, target-binding, CP ledger, and replay contract;
- every charge/fight-coupled Core Stratagem timing hook is registered through `StratagemCatalogIndex`; Charge and Fight phase code must not scan the full catalog when a charge/fight event occurs;
- Heroic Intervention uses charge movement validators and requires a `PathWitness` or typed invalid result;
- Crushing Impact uses deterministic dice/mortal-wound records and charge-context target binding;
- Counter-offensive is a fight-order interrupt, not a duplicate private fight-order path;
- Epic Challenge binds to an eligible Character model through explicit model-target binding and records the per-fight restriction separately from matched-play same-Stratagem-per-phase restrictions;
- Fights First and Epic Challenge Precision effects execute through typed timing/effect machinery.

Required tests:

- each supported charge/fight-coupled Core Stratagem has decision-contract, CP, target-binding, and replay coverage;
- each supported charge/fight-coupled Core Stratagem has a phase-progression/reaction-window test proving the Charge/Fight phase emits it from the trigger-keyed index and resolves it through `GameLifecycle.submit_decision(...)`;
- Heroic Intervention emits a `charge_move` proposal that reuses the Phase 15B endpoint-only and validator-approved `PathWitness` movement coverage;
- Crushing Impact records deterministic dice/mortal-wound results and rejects invalid charge-context targets;
- Counter-offensive interrupts fight order once at the legal timing and resumes the parent fight sequence;
- Epic Challenge validates eligible Character model target binding and enforces its own per-fight restriction separately from matched-play same-Stratagem-per-phase restrictions.

## Phase 15F: Charge/Fight completion gate

Status: Complete.

Phase 15F hardens the Charge and Fight phase completion gates so both players can complete full Charge/Fight phase bodies through the shared lifecycle decision path, and Fight damage/removal work drains before the phase emits completion.

Required tests:

- full Charge phase can complete for both players;
- full Fight phase can complete for both players;
- charge consumes declaration, charge roll, charge movement, and endpoint validation through the shared decision path;
- the Fight phase consumes fight order, Pile In, melee attack sequence, damage allocation, removal records, and Consolidate;
- charge movement, Pile In, and Consolidate emit displacement records;
- melee attacks can destroy models and emit removal records;
- Charge/Fight completion waits for all pending charger, defender, and charge/fight-coupled reaction decisions to resolve through `GameLifecycle.submit_decision(...)`;
- invalid declarations and invalid charge/fight moves do not mutate state;
- fight order is deterministic and replay-safe.

---

# Setup, deployment, reserves, and army construction completion

## Phase 16A: deployment rules and deployment-zone placement

Status: Complete.

Phase 16A replaces the Phase 10A deterministic placement bridge with real
source-backed Deploy Armies setup. Deployment is a setup placement operation:
the engine may validate final set-up poses directly for deployment placement
proposals, but any movement-like pre-battle displacement remains owned by Phase
16B and must use movement witnesses.

Modules:

- `engine/setup_flow.py`
- `engine/deployment.py`
- `engine/movement_proposals.py`
- `engine/battlefield_state.py`
- `engine/endpoint_placement.py`
- `engine/mission_setup.py`
- `core/deployment_zones.py`
- `core/missions.py`
- `docs/ADAPTER_DECISION_CONTRACT.md`

Objects:

- `DeploymentSetupState`
- `DeploymentOrderPolicy`
- `DeploymentUnitSelection`
- `DeploymentPlacementProposal`
- `DeploymentLegalityContext`
- `DeploymentPlacementResolution`
- `DeploymentZoneAssignment`
- `BattlefieldTransitionBatch`

Invariants:

- deployment zones come from the selected source-backed mission map and
  deployment layout; deployment-zone geometry must not be invented from player
  IDs, default board halves, or test-only coordinates;
- Attacker/Defender, deployment order, and any first-deploying-player policy are
  mission/ruleset setup policy, not adapter behavior;
- deployment choices are player-facing and must flow through
  `DecisionRequest` -> `DecisionResult` -> validation ->
  `GameLifecycle.submit_decision(...)` -> engine mutation;
- deployment unit options include only units that are not declared in Reserves,
  not starting embarked, not already deployed, and not otherwise removed by a
  setup legality consequence;
- deployment placement proposals must include every alive model in the selected
  rules unit, including attached rules-unit models when applicable;
- ordinary deployment must set up the unit wholly within the owning player's
  legal deployment zone unless a source-backed rule modifies that setup
  permission;
- `INFILTRATORS` modifies deployment setup only when every model in the unit has
  that ability, allowing that unit to be set up anywhere on the battlefield more
  than 8" horizontally from the opponent's deployment zone and all enemy units;
- deployment endpoint validation checks battlefield bounds, terrain endpoint
  legality, model overlap, base/volume occupancy, unit coherency, Engagement
  Range setup restrictions, objective-marker endpoint permissions, and any
  source-backed Fortification or large-model restrictions;
- deployment terrain legality consumes the selected `MissionSetup` terrain
  feature payloads exactly as the engine will use them for movement,
  visibility, collision, objective, and reserve-placement legality; UI layout
  artwork and image-derived polygons are not gameplay inputs;
- endpoint-style placement evidence is legal only for explicit set-up placement
  operations such as deployment; it must not be reused for redeployments that
  move models, Scout moves, or later movement actions;
- deployment emits deterministic placement records with deployment setup-step
  identity, source mission/deployment-map identity, placement kind, model IDs,
  poses, and event IDs;
- deployed attached units are represented as one rules unit for physical
  operations, with component metadata preserved for destroyed-unit triggers;
- hidden or secret pre-battle information must remain viewer-scoped in pending
  requests, placement diagnostics, projections, and event deltas.

Required tests:

- Deploy Armies no longer creates a battlefield through the deterministic
  placement bridge;
- deployment unit selection and placement submission use the shared lifecycle
  decision path and produce deterministic JSON-safe `DecisionRecord` and
  `EventRecord` payloads;
- deployment zones load from `MissionSetup` and reject unknown, stale, or
  wrong-player zone IDs before queue pop;
- valid deployment places every model wholly within the correct deployment zone
  and records one placement per model;
- valid `INFILTRATORS` deployment can place a qualifying unit outside its
  deployment zone when every model has the ability and every model is more than
  8" horizontally from the opponent's deployment zone and all enemy units;
- deployment rejects out-of-bounds poses, illegal terrain endpoints, model
  overlap, broken coherency, Engagement Range violations, omitted models, extra
  models, and wrong-unit model IDs without mutating state;
- deployment legality for `layout-1` through `layout-8` uses the conservative
  runtime terrain footprints from `MissionSetup` and cannot be satisfied by
  `Layout*.png` artwork bounds, rotated-image silhouettes, or adapter-local
  terrain overlays;
- `INFILTRATORS` deployment rejects mixed-ability units, omitted/extra models,
  positions within 8" horizontally of the opponent's deployment zone, and
  positions within 8" horizontally of any enemy unit;
- attached rules-unit deployment validates over group-aware model sets rather
  than component-only `UnitPlacement` data;
- units declared as Reserves, starting embarked, already deployed, or destroyed
  by a setup legality consequence are absent from deployment options;
- stale, drifted, malformed, wrong-actor, wrong-step, wrong-placement-kind, or
  wrong-ruleset-hash submissions reject before queue pop and before a
  `DecisionRecord`;
- replay restore during Deploy Armies reproduces the same pending deployment
  request and validation context.

## Phase 16B: redeployments, Scouts, Infiltrators, and pre-battle abilities

Status: Complete.

Phase 16B owns source-backed setup rules that occur after ordinary deployment
or otherwise modify setup legality before the first battle round. Infiltrators
is a deployment-time setup permission, not a pre-battle move. Redeploy is a
remove-and-set-up operation. Scout moves and similar pre-battle moves are real
physical movement and require movement evidence. Scouts are resolved from the
official `Scouts X"` shape during Resolve Pre-battle Abilities, including the
Strategic Reserves set-up branch and the Dedicated Transport branch.

Implementation notes: `SetupFlow` now runs `redeploy_units` and
`resolve_prebattle_actions` decision windows after Deploy Armies. Redeploy uses
`select_redeploy_unit -> submit_redeploy_placement`; Scouts use
`select_prebattle_action` followed by either `submit_scout_reserve_setup` or
`submit_scout_move`. Lifecycle validation rejects stale, malformed, drifted, or
rule-invalid pre-battle proposal payloads before queue pop and before mutation.
Accepted actions emit deterministic `PreBattleActionRecord` payloads.
When more than one player has unresolved effects in the same pre-battle setup
step, `SetupFlow` first emits the Phase 12A `resolve_sequencing_order` decision
using a before-battle timing window and a deterministic roll-off; the resolved
participant order then controls which player receives the next redeploy or
pre-battle action selection request.

Modules:

- `engine/setup_flow.py`
- `engine/lifecycle.py`
- `engine/prebattle.py`
- `engine/prebattle_records.py`
- `engine/timing_windows.py`
- `engine/reaction_queue.py`
- `engine/movement_proposals.py`
- `engine/triggered_movement.py`
- `engine/reserves.py`
- `engine/transports.py`
- `engine/battlefield_state.py`
- `geometry/pathing.py`
- `docs/ADAPTER_DECISION_CONTRACT.md`

Objects:

- `PreBattleTimingWindowState`
- `PreBattleProposalRequest`
- `PreBattlePlacementProposal`
- `PreBattleResolution`
- `ScoutAbilityInstance`
- `ScoutMoveProposal`
- `InfiltratorSetupPermission`
- `InfiltratorDeploymentLegalityContext`
- `PreBattleActionRecord`

Invariants:

- redeployments occur at their source-backed setup timing after deployment and
  before battle begins; ordering among multiple redeploy/pre-battle effects uses
  timing windows and the Phase 12A sequencing path where needed;
- redeploy is removal plus set-up placement, not a displacement, movement-phase
  action, destroyed-model trigger, or silent battlefield rewrite;
- redeploy records deterministic removal and placement events with source IDs,
  setup step, model IDs, before/after poses, and no movement-distance payload;
- redeploy placement validates the same endpoint, terrain, coherency, overlap,
  deployment-zone, and Engagement Range setup restrictions as deployment, plus
  any source-specific distance or target restrictions;
- Scouts always takes the source-backed form `Scouts X"`; X is the maximum
  Scout Move distance and must come from the structured ability descriptor, not
  parsed at runtime from raw text;
- current catalog data attaches Scouts descriptors at datasheet/component
  granularity; every alive model in a component receives the component's
  structured Scouts descriptors, and a `SCOUTS` keyword without a structured
  descriptor fails fast instead of falling back to a default distance;
- duplicated `Scouts X"` instances use the official numbered-core-ability
  duplicate rule with the Scouts exception: if every model shares a Scouts
  value, that shared value is a legal selected instance, but when Scouts values
  vary across models the selected X must be the lowest legal Scouts distance
  needed to satisfy the all-model unit requirement; for example, a unit where
  every model has both `Scouts 6"` and `Scouts 8"` can select `Scouts 8"`, while
  a unit with one `Scouts 6"` model and five `Scouts 8"` models must use
  `Scouts 6"`;
- Scouts choices are available only during Resolve Pre-battle Abilities and only
  when every model in the source Scouts unit has the Scouts ability; the
  Dedicated Transport branch separately requires every embarked model in that
  transport to have Scouts;
- if a Scouts unit is in Strategic Reserves, the controlling player can set up
  that unit anywhere wholly within their deployment zone; this is setup
  placement, not a Move Units reserve arrival or a Scout Move displacement;
- if a Scouts unit is wholly within its controlling player's deployment zone,
  it can make one Scout Move;
- if a Scouts unit is embarked within a `DEDICATED TRANSPORT` that is wholly
  within its controlling player's deployment zone, and every model embarked
  within that `DEDICATED TRANSPORT` has Scouts, that `DEDICATED TRANSPORT` can
  make one Scout Move with its cargo state intact;
- Scout moves consume shared movement/pathing/terrain/coherency validators and
  require a `PathWitness` for every alive model; endpoint-only Scout movement is
  invalid;
- after a Scout Move, the moved unit or `DEDICATED TRANSPORT` must be more than
  8" horizontally from all enemy units; this is a horizontal-distance predicate
  and equality at 8" is not legal;
- Scout moves are not Movement phase actions and must not mark a unit as having
  Advanced, Fallen Back, Remained Stationary, shot, or started a Mission Action;
- units without Scouts, units whose models do not all have Scouts, destroyed
  units, non-Strategic-Reserves reserve units, and embarked units outside the
  Dedicated Transport branch are never legal Scout candidates;
- a Dedicated Transport carrying any model without Scouts cannot make a Scout
  Move through the embarked-unit branch, even if another embarked unit has
  Scouts;
- Infiltrators is resolved during deployment: if every model in the unit has
  `INFILTRATORS`, that unit can be set up anywhere on the battlefield that is
  more than 8" horizontally from the opponent's deployment zone and all enemy
  units;
- Infiltrators does not create a late private placement path, pre-battle
  movement, redeploy effect, or reserve-arrival shortcut; it is an alternate
  deployment setup permission consumed by the ordinary deployment placement
  validator;
- Infiltrators placement still validates terrain endpoint legality, coherency,
  model overlap, battlefield bounds, and any source-backed setup restrictions;
- all pre-battle abilities use typed timing windows, source IDs, deterministic
  option/proposal payloads, and replay-safe records;
- any Phase 16B decision type, proposal kind, option family, or viewer-visible
  payload newly exposed to adapters must update
  `docs/ADAPTER_DECISION_CONTRACT.md` in the same implementation PR.

Required tests:

- redeploy decisions occur only at legal pre-battle timing and after initial
  deployment state exists;
- valid redeploy emits deterministic removal and placement records rather than
  displacement records;
- redeploy rejects stale unit state, wrong actor, wrong setup step, illegal
  zone, illegal terrain endpoint, broken coherency, overlap, and Engagement
  Range violations without mutation;
- Scouts option emission covers all three official branches: Strategic Reserves
  set-up wholly within deployment zone, unit Scout Move from wholly within
  deployment zone, and Dedicated Transport Scout Move from wholly within
  deployment zone with all embarked models having Scouts;
- Scouts Strategic Reserves setup records deterministic setup placement, removes
  or transitions the reserve state, does not use Move Units arrival timing, and
  rejects placement outside the controlling player's deployment zone;
- Scout proposals validate `PathWitness` start poses against current battlefield
  state, use X from `Scouts X"` as the maximum distance, and reject
  endpoint-only movement;
- duplicated Scouts tests cover the official examples: every model with both
  `Scouts 6"` and `Scouts 8"` can select `Scouts 8"`, while one model with
  `Scouts 6"` and five models with `Scouts 8"` must use `Scouts 6"` and reject
  an 8" Scout Move;
- Scout movement rejects any final state that is not more than 8" horizontally
  from all enemy units;
- unit Scout Move eligibility requires every model in the moving unit to have
  Scouts and the unit to start wholly within its controlling player's deployment
  zone; it rejects embarked, destroyed, already Scout-moved, no-ability, and
  mixed-ability units;
- Dedicated Transport Scout Move eligibility requires the transport to be a
  `DEDICATED TRANSPORT`, start wholly within its controlling player's deployment
  zone, carry at least one embarked unit, and have every embarked model possess
  Scouts; it rejects mixed cargo where any embarked model lacks Scouts;
- Scout movement uses shared terrain/pathing/coherency validators and does not
  write Movement phase action state;
- Infiltrators modify deployment placement legality only during deployment and
  only for units where every model has `INFILTRATORS`;
- Infiltrators placement rejects positions that are not more than 8"
  horizontally from the opponent's deployment zone or are not more than 8"
  horizontally from every enemy unit; equality at 8" is not legal;
- Infiltrators placement rejects mixed-ability units and must not be offered as
  a Scout, redeploy, reserve-arrival, or post-deployment pre-battle action;
- multiple pre-battle abilities resolve in deterministic source/timing order,
  including sequencing decisions when both players have simultaneous effects;
- replay restore inside a pre-battle timing window reproduces pending
  redeploy/Scout requests and validation context;
- viewer-scoped projections and event deltas do not leak hidden pre-battle
  choices or secret setup information.

## Phase 16C: reserves declarations, Strategic Reserves limits, and Deep Strike setup

Status: Complete.

Phase 16C completes Declare Battle Formations for reserves-related setup. Phase
10P/14D/14K already own supported arrival validation during Move Units; this
phase owns the pre-battle declaration state that decides which units start on
the battlefield, in Strategic Reserves, in another source-backed reserves state,
or embarked.

Modules:

- `engine/setup_flow.py`
- `engine/reserve_declarations.py`
- `engine/reserves.py`
- `engine/transports.py`
- `engine/aircraft.py`
- `engine/army_mustering.py`
- `engine/mission_setup.py`
- `core/ruleset_descriptor.py`
- `docs/ADAPTER_DECISION_CONTRACT.md`

Objects:

- `BattleFormationDeclarationState`
- `ReserveDeclarationRequest`
- `ReserveDeclarationSelection`
- `StrategicReserveDeclaration`
- `ReserveLegalityContext`
- `DeepStrikeSetupDeclaration`
- `AircraftReserveDeclaration`
- `ReserveState`
- `ReserveLegalityReport`

Invariants:

- reserve declarations are setup player choices and must be replay-facing
  `DecisionRequest`/`DecisionResult` submissions or source-backed engine
  consequences recorded before battle begins;
- each mustered runtime rules unit has exactly one initial formation state:
  deployed, declared in Reserves, starting embarked, destroyed by a setup
  legality consequence, or explicitly unsupported with reason;
- Strategic Reserves limits are validated during setup from source-backed battle
  size, points, unit, and mission policy; missing points or limit data is an
  import blocker or awaiting-source row, not a default;
- Strategic Reserves cannot include source-forbidden units such as
  `FORTIFICATIONS` unless a later source-backed exception states otherwise;
- Deep Strike and similar abilities are explicit setup/arrival mechanisms with
  source-linked permission; they must not be represented as generic teleport
  fallback behavior;
- Deep Strike declaration/arrival requires every model in the unit to have Deep
  Strike; each Deep Strike Ingress Move can set up anywhere on the battlefield
  more than 8" horizontally from all enemy units, including inside the
  opponent's deployment zone;
- Aircraft mandatory reserve behavior is declared during Declare Battle
  Formations and creates normal `ReserveState` records consumed by later
  aircraft/arrival policies;
- reserve declarations preserve `declared_during_step`, reserve kind, origin,
  source rule IDs, owning player, unit IDs, points contribution, and later
  arrival restrictions in deterministic payloads;
- units declared in Reserves are absent from Deploy Armies placement options and
  can arrive only through the shared Move Units/reserve-arrival decision path;
- Reserve destruction timing is the active ruleset/mission-pack policy and must
  remain replay-safe;
- illegal reserve declarations fail before battle starts and cannot be repaired
  by silently deploying the unit, dropping the unit, or changing reserve kind.

Required tests:

- valid Strategic Reserves declaration records deterministic JSON-safe
  `ReserveState` and `DecisionRecord` payloads;
- Strategic Reserves points/percentage limits, battle-size limits, forbidden
  unit kinds, duplicate declarations, wrong-player units, and unknown unit IDs
  are rejected before battle starts;
- units with Deep Strike or similar setup permissions can be declared in the
  correct reserve kind and later expose only source-backed arrival proposal
  kinds;
- Deep Strike arrival rejects mixed-ability units, placements within or equal to
  8" horizontally from enemy units, and any accidental Strategic Reserves
  opponent-deployment-zone ban applied to Deep Strike placements;
- units without a source-backed Deep Strike/reserve permission cannot use that
  reserve kind;
- Aircraft reserve declarations are mandatory where the active ruleset requires
  them and are serialized as ordinary reserve state, not a private aircraft
  list;
- declared reserve units are excluded from deployment options and included in
  Move Units reserve-arrival options at legal timing only;
- stale, malformed, wrong-step, wrong-actor, duplicate, and ruleset-drifted
  reserve declaration submissions reject before queue pop;
- replay restore before and after Declare Battle Formations preserves identical
  reserve declarations, source context, and arrival restrictions;
- setup completion fails if any mustered unit has no legal initial formation
  state.

## Phase 16D: leader attachment, enhancements, army construction, and roster legality completion

Status: Complete.

Phase 16D finishes source-backed army construction and runtime instantiation.
The mustering output is not a loose list of component units: it is a
deterministic `ArmyDefinition` containing runtime unit instances, attached
rules units, enhancement records, Dedicated Transport manifests, and legality
reports that later phases consume without guessing. Setup consumes those
manifests to record `TransportCargoState` values or
`DedicatedTransportSetupConsequence` values on `GameState`.
`StartingStrengthRecord` remains the authoritative game-state artifact owned by
`GameState`; setup calls `GameState.record_army_definition(...)`, which derives
records from the mustered units and attached formations before later command,
damage, healing, and split logic can consume them.

Implemented coverage:

- `ArmyMusterRequest` accepts strict roster metadata for source-backed unit
  points, Warlord selection, Enhancement assignment, and Dedicated Transport
  starting-cargo manifests;
- `validate_roster_legality(...)` emits deterministic JSON-safe
  `RosterLegalityReport` diagnostics for Strike Force unit points plus selected
  Enhancement points, unit limits, missing source data, Warlord legality,
  Enhancement legality, Epic Hero restrictions, attached-squad Enhancement
  limits, missing Dedicated Transport manifests, and Dedicated Transport
  capacity/cargo restrictions when cargo is provided;
- strict roster requests fail before mutation, while `GameConfig` rejects
  non-strict mustering requests by default; legacy smoke fixtures must opt into
  `allow_legacy_non_strict_rosters` explicitly;
- mustered `ArmyDefinition` payloads preserve Warlord, Enhancement, unit-point,
  Dedicated Transport, and legality provenance and promote the selected
  Warlord with the `WARLORD` keyword;
- setup records Dedicated Transport manifest cargo as first-class
  `TransportCargoState` before Deploy Armies and emits deterministic setup
  events.
- setup records explicit empty Dedicated Transport manifests as
  `DedicatedTransportSetupConsequence` values instead of roster-legality
  failures; those transports cannot be selected in Deploy Armies and are
  accounted as destroyed in battle round 1.
- setup records `StartingStrengthRecord` entries from `ArmyDefinition` through
  `GameState.record_army_definition(...)`; attached formations receive one
  attached-unit starting-strength record until split, and component records are
  restored only by split recovery.

Modules:

- `engine/army_mustering.py`
- `engine/unit_factory.py`
- `engine/setup_flow.py`
- `engine/transports.py`
- `engine/unit_state.py`
- `engine/attack_sequence.py`
- `engine/damage_allocation.py`
- `core/army_catalog.py`
- `core/attached_unit.py`
- `core/unit_group.py`
- `core/faction.py`
- `core/detachment.py`

Objects:

- `ArmyMusterRequest`
- `ArmyDefinition`
- `BattleSizeMusteringPolicy`
- `FactionSelection`
- `DetachmentSelection`
- `RosterUnitSelection`
- `AttachmentDeclaration`
- `AttachedUnitRuntimeBinding`
- `EnhancementAssignment`
- `WarlordSelection`
- `DedicatedTransportManifest`
- `DedicatedTransportSetupConsequence`
- `RosterLegalityReport`
- `StartingStrengthRecord`

Invariants:

- mustering order is Battle Size, Army Roster, Faction, Detachment Rules, Units, then Warlord promotion;
- battle size defines points limit, detachment points, enhancement limit, unit limit, and mission-compatible battlefield expectations;
- CORE V2 currently supports only Strike Force: 2000 points, 60" x 44" battlefield expectations, 3 Detachment Points, Enhancement Limit 4, and Unit Limit 3, doubled for `BATTLELINE` units;
- Incursion, Combat Patrol, Onslaught, and other battle sizes are explicit unsupported inputs until repository policy adds them;
- active army catalogs reject Combat Patrol, Legends, Forge World, Kill Team,
  and other non-matched-play content scopes instead of letting those units,
  rules, Enhancements, Stratagems, or detachments reach mustering;
- army faction is a selected Faction keyword and every included unit must be legal for that faction or an allowed exception;
- detachment selection spends Detachment Points and grants access to detachment
  rules, units, Stratagems, Enhancements, and Force Dispositions; missing
  detachment point values, unit grants, or Force Disposition grants are explicit
  awaiting-source data, not defaults;
- the army must include at least one eligible `CHARACTER` model to be Warlord;
- the Warlord must have the same Faction keyword as the rest of the army;
- selected Warlord gains the `WARLORD` keyword;
- unit limits are enforced by Battle Size and doubled for `BATTLELINE` units;
- `EPIC HERO` units are unique and cannot receive Enhancements;
- only `CHARACTER` models can receive Enhancements;
- Enhancement count is capped by Battle Size;
- no unit can have more than one Enhancement;
- each Enhancement must be unique;
- selected units, wargear, enhancements, faction, detachment, Warlord, and
  attachment declarations come from catalog/source records and preserve source
  IDs in deterministic payloads;
- source-awaiting army construction data blocks the affected roster path instead
  of substituting a point cost, attachment rule, base size, transport capacity,
  or enhancement eligibility default;
- runtime unit instance IDs, model instance IDs, attached-unit IDs, action IDs,
  and setup event IDs are deterministic from the source roster and game seed;
- Leader and Support attachments are declared on the army list, not in Declare
  Battle Formations, and mustering turns those declarations into runtime
  attached rules-unit instances rather than only retaining component units;
- Enhancements are selected after Attached Units are created, so the one-Enhancement-per-squad restriction applies across the attached rules unit;
- every Dedicated Transport must start the battle with at least one unit embarked or it cannot be deployed and counts as destroyed during the first battle round;
- Dedicated Transport starting cargo is a source-backed setup manifest and must
  be consistent with transport capacity, datasheet restrictions, component
  attached-unit state, and Deploy Armies option filtering;
- missing Dedicated Transport manifest source data is a strict construction
  violation; an explicit empty manifest is a setup consequence, not a roster
  legality failure;
- Leader attachment restrictions are validated before battle;
- each Bodyguard unit can have at most one Leader and one Support attached unless a rule says otherwise;
- while attached, the runtime-instantiated Attached unit is treated as one unit
  for rules purposes except destroyed-unit triggers;
- coherency for an Attached unit is validated over the attached rules unit's alive models, not per component `UnitPlacement`;
- attacks against Attached units use Bodyguard Toughness until the attacking unit resolves all attacks;
- attacks cannot be allocated to Character models in Attached units until the Bodyguard is destroyed unless a rule such as Precision permits it;
- when Bodyguard or Leader components are destroyed, surviving units split at the correct timing and recover original Starting Strength;
- destroyed-unit triggers for Attached-unit components use only the destroyed component's own keywords;
- persisting effects, Battle-shock state, transport cargo, reserve state,
  action state, objective control, attack allocation, visibility, movement, and
  replay payloads refer to attached rules units through explicit group-aware
  APIs and stable component-role metadata;
- roster validation cannot use broad exception handling, partial test objects,
  `getattr(..., default)` fallbacks, or duck-typed unit/model fields.

Required tests:

- Strike Force unit points plus selected Enhancement points, battlefield
  dimensions, detachment points, enhancement limits, unit limits, and
  unsupported battle-size rejection;
- active catalog rejection for Combat Patrol, Legends, Forge World, Kill Team,
  and other non-matched-play content scopes;
- multi-detachment Strike Force combinations whose total Detachment Point cost
  is less than or equal to 3, plus rejection above 3;
- selected detachment Force Disposition union and selected-detachment unit
  grants;
- Epic Hero uniqueness and Enhancement denial;
- Enhancement count, uniqueness, Character-only, and one-per-attached-squad restrictions;
- source-awaiting detachment point, enhancement eligibility, base-size,
  transport-capacity, or attachment-rule data blocks the affected roster path
  with typed diagnostics;
- Dedicated Transport starting cargo legality, missing-manifest roster
  diagnostics, and explicit empty-manifest setup consequences;
- Leader/Support/Bodyguard legal attachment, army-list attachment timing, and
  runtime instantiation of the attached rules unit with deterministic component
  role metadata;
- Warlord faction-keyword requirement;
- deterministic runtime IDs and source provenance for unit instances, model
  instances, attached units, Warlord, Enhancement, Dedicated Transport, and
  starting cargo records;
- production `GameConfig` values reject non-strict mustering requests unless a
  legacy smoke fixture explicitly opts out;
- setup-derived `StartingStrengthRecord` values cover mustered attached units
  and single-model transports before later phases consume them;
- empty Dedicated Transport setup consequences are replay-safe, account their
  transport models for deployment completion, and exclude those transports from
  Deploy Armies choices;
- Attached-unit coherency uses `UnitGroup.alive_models()`/group-aware placement data across Leader and Bodyguard models;
- Attached-unit Toughness and Character allocation protection;
- Attached-unit split timing after attacks resolve;
- destroyed-unit trigger identity for Leader vs Bodyguard components;
- transport, reserve, damage allocation, movement, visibility, event logging,
  and replay tests consume the attached rules-unit identity rather than
  ambiguous `unit.models` semantics;
- canonical army construction fixtures use real domain objects and fail if a
  required field is omitted.

## Phase 16E: pre-battle/setup completion gate

Status: Complete.

Phase 16E is the hard gate between setup and battle. It drains setup decisions,
pre-battle timing windows, pending placement/redeploy/reserve/transport work,
and legality audits before battle round one can start. It also removes the
temporary assumption that a deterministic placement bridge can stand in for
real setup.

Implemented coverage:

- `SetupCompletionGate` audits readiness at the final setup step and returns a
  typed invalid lifecycle status instead of mutating when setup is incomplete;
- legal setup completion emits deterministic `SetupLegalityReport`,
  `SetupReplayCheckpoint`, and `BattleStartRecord` payloads, records
  `setup_completion_gate_passed` and `battle_started` events, and enters battle
  round one through engine-owned mutation;
- reserve-declaration auditing can run at the final gate without reopening
  Declare Battle Formations, and already deployed units are not treated as
  undeclared reserves;
- regression tests cover full setup-to-battle entry, direct setup-step bypass
  rejection, pending decision queue rejection without queue pop, lifecycle
  payload round-trip, and a static audit that the gate path does not call the
  Phase 10A deterministic placement bridge.

Modules:

- `engine/setup_completion.py`
- `engine/setup_flow.py`
- `engine/lifecycle.py`
- `engine/game_state.py`
- `engine/replay.py`
- `engine/battlefield_state.py`
- `adapters/projection.py`
- `docs/ADAPTER_DECISION_CONTRACT.md`

Objects:

- `SetupCompletionGate`
- `SetupDecisionDrainState`
- `SetupLegalityReport`
- `PreBattleReadinessSnapshot`
- `BattleStartRecord`
- `SetupReplayCheckpoint`

Invariants:

- setup completion is engine-owned and cannot be forced by an adapter, UI,
  network client, replay driver, or test helper;
- battle starts only after the ruleset setup sequence is complete, the decision
  queue is empty, reaction/timing windows are drained, and no setup proposal is
  pending;
- setup completion validates mustered armies, source-backed mission setup,
  Attacker/Defender state, secondary mission choices, battle formation
  declarations, deployment placements, redeployments, reserves declarations,
  starting transport cargo, Leader/Support attachments, Enhancements, Warlord,
  pre-battle abilities, first-turn state, and Dedicated Transport consequences;
- every alive non-reserve, non-embarked, non-destroyed model that should start
  on the battlefield has exactly one legal placement record;
- every deployed rules unit, including attached rules units, passes group-aware
  coherency, terrain endpoint, overlap, and Engagement Range setup validation;
- all setup-created records are deterministic, JSON-safe, source-linked, and
  replay-restorable without Python object reprs or memory addresses;
- no deterministic placement bridge, silent fallback deployment, or local-only
  test placement path can satisfy the setup gate;
- invalid setup produces typed diagnostics and leaves the game in setup rather
  than partially entering battle;
- viewer-scoped setup information remains redacted in projections, event deltas,
  replay traces, and invalid-submission diagnostics when visibility can differ.

Required tests:

- full setup sequence can complete without deterministic placement bridge;
- deployment, redeploy, reserves, transports, leaders, enhancements, Warlord
  selection, first-turn determination, and pre-battle abilities are resolved
  through `DecisionRequest`/`DecisionResult` or deterministic source-backed
  setup records;
- battle starts only after setup legality is complete;
- setup completion rejects missing army, missing mission setup, unresolved
  secondary mission choice, unresolved Attacker/Defender, unresolved battle
  formation declaration, undeployed required unit, illegal reserve declaration,
  empty Dedicated Transport consequence not applied, unresolved redeploy/Scout
  request, illegal attached-unit placement, or pending decision queue entries;
- battle start emits deterministic `BattleStartRecord`/event payloads and enters
  battle round one at the source-backed first battle phase with the correct
  active player;
- replay from a setup checkpoint through battle start produces the same logical
  state hash, event log, and pending-decision state;
- setup completion payloads contain no Python object reprs or memory addresses;
- viewer-scoped setup projections and event deltas do not leak hidden reserves,
  secret secondary choices, or other hidden pre-battle information;
- code-quality audits reject any remaining setup gate path that calls the
  deterministic placement bridge after Phase 16A-16E are implemented.

---

# Wahapedia bridge data ingestion, language parsing, and content coverage

Phase 17 imports faction content before Wahapedia publishes native 11th Edition
tables. The active engine remains 11th Edition-only: prior-edition Wahapedia
rows are treated as upstream bridge source material, not as a runtime
compatibility mode. Official 11th Edition faction update instructions are
modeled as ordered, source-linked transition patches over the normalized bridge
source rows. The only catalog emitted for play is the patched 11th Edition
catalog.

The faction rollout order, per-faction phase structure, and naming convention for
detachment and datasheet subphases are tracked in
[FACTION_INTEGRATION.md](FACTION_INTEGRATION.md).

## Phase 17A: bridge Wahapedia source mirror and CSV-to-JSON ETL

Status: Complete.

Phase 17A provides the bridge source mirror only. It does not make prior-edition
Wahapedia rows an active runtime catalog. CSV/source inputs are represented by
`WahapediaSourceSnapshot`, `WahapediaCsvTable`, `NormalizedSourceRow`,
`SourceHtmlSanitizationReport`, `WahapediaJsonArtifact`, and
`SourcePackageManifest`; `tools/wahapedia_fetch.py` records fetched source
checksums, and `tools/wahapedia_csv_to_json.py` emits deterministic JSON source
artifacts plus package manifests. Runtime engine modules remain blocked from
importing raw source-normalization or source-mirror modules.

Official GW faction-pack PDFs and extracted whole-source text/page files are
local-only validation inputs, not repository artifacts. Do not commit
`data/raw/faction_packs/*.pdf`, `data/raw/faction_packs/*.txt`,
`data/raw/faction_packs/extracted_pages/*.md`, `data/raw/gw/**/*.pdf`,
`data/raw/gw/**/*.txt`, or `data/raw/gw/**/extracted_pages/*.md`, and do not
put them in Git LFS. Phase 17 should commit source manifests, official URLs,
retrieval metadata, SHA-256 hashes, byte counts, page/section references,
structured patch operations, diagnostics, and generated catalog artifacts. CI,
packaging, Docker images, wheels, npm packages, and release artifacts must not
redistribute the PDFs unless a future explicit policy grants that right.
The current faction-pack source manifest uses the official Warhammer 40,000
downloads page as its shared source page:
`https://www.warhammer-community.com/en-gb/downloads/warhammer-40000/`.

CORE V1 already has generated `wahapedia_data` JSON such as `Abilities.json`, `Datasheets.json`, `Datasheets_models.json`, `Datasheets_wargear.json`, `Factions.json`, `Detachments.json`, `Enhancements.json`, and `Stratagems.json`. CORE V2 must rebuild this pipeline from the downloaded CSV/source exports, but with stricter normalization and provenance.

Modules:

- `tools/wahapedia_fetch.py`
- `tools/wahapedia_csv_to_json.py`
- `rules/source_catalog.py`
- `rules/text_normalization.py`
- `rules/html_sanitizer.py`
- `rules/wahapedia_schema.py`

Objects:

- `WahapediaSourceSnapshot`
- `WahapediaCsvTable`
- `NormalizedSourceRow`
- `SourceHtmlSanitizationReport`
- `WahapediaJsonArtifact`
- `SourcePackageManifest`

Invariants:

- downloaded CSV/source files are stored with checksum, source date, upstream
  identity, and source edition identity;
- generated JSON is deterministic from source inputs;
- HTML tags are stripped or converted to explicit structured markup before catalog ingestion;
- normalized text preserves source spans, paragraph/list boundaries, dice expressions, keywords, and distance expressions;
- smart quotes, dashes, non-breaking spaces, HTML entities, and embedded links are normalized once;
- raw HTML is never consumed by runtime engine code;
- generated JSON includes `raw_text`, `normalized_text`, and source-row provenance where needed;
- generated JSON is a source mirror only and must not be imported directly by
  runtime engine code as an active prior-edition catalog;
- invalid rows fail with actionable diagnostics rather than being silently skipped.

Required tests:

- CSV row normalization strips HTML tags and preserves meaningful text;
- normalized output is stable across runs;
- source checksum drift changes package manifest hash;
- generated JSON contains no raw HTML tags in runtime fields;
- every catalog-bound row has source table, source row ID, and source package ID;
- failure report groups unsupported/malformed rows by reason.

CORE V1 relevant areas:

- `wahapedia_data/`
- `wahapedia_data/*.json`
- content import scripts, if present;
- datasheet/wargear/faction/stratagem tests.

## Phase 17A.1: official 11th Edition transition patch packages

Status: Complete.

This is an inserted bridge subphase between the source mirror and canonical
catalog generation. It exists to avoid renumbering the later Phase 17 work while
making the pre-native-Wahapedia transition patch layer explicit.

Until native 11th Edition faction source rows are available, official faction
update instructions are represented as structured patch packages applied to the
normalized bridge source mirror. These packages preserve official source text,
target selectors, ordering, diagnostics, and generated payload hashes.
The implemented layer emits `PatchedSourceArtifact` payloads with the source
artifact hash, transition package hash, deterministic row payloads, and typed
target-drift diagnostics for unresolved, ambiguous, stale, malformed,
advisory-only, and unsupported executable FAQ paths.

Modules:

- `tools/build_transition_patch.py`
- `tools/apply_transition_patches.py`
- `rules/source_patch.py`
- `rules/source_catalog.py`
- `rules/text_normalization.py`

Objects:

- `SourceTransitionPatchPackage`
- `SourceTransitionPatchOperation`
- `SourcePatchTarget`
- `SourcePatchDiagnostic`
- `SourceFaqClassification`
- `PatchedSourceArtifact`

Initial operation families:

- `append_rule_text`
- `replace_rule_text`
- `add_keyword`
- `remove_keyword`
- `replace_profile_characteristic`
- `replace_weapon_characteristic`
- `replace_datasheet_ability`
- `replace_enhancement_text`
- `replace_stratagem_text`
- `record_faq_answer`
- `mark_unsupported`

FAQ classifications:

- `advisory_only`
- `executable_patch`
- `unsupported_executable_change`

Invariants:

- transition patches cite official source package ID, source date, faction ID,
  normalized instruction text, and stable source IDs;
- patch application is deterministic and ordered;
- every patch target resolves to exactly one source row or to an explicit
  multi-row target set declared by the operation;
- target drift is a hard import error unless the operation is explicitly marked
  as an unsupported diagnostic;
- text replacement and append operations re-run the normalization and parsed-token
  boundary before catalog generation;
- official 11th Edition patches produce 11th Edition package IDs and hashes;
- patch packages do not introduce runtime old-vs-new edition switches;
- every FAQ answer is classified before catalog emission;
- FAQs classified as `advisory_only` are stored as source-linked advisory
  records until a later rule descriptor consumes them;
- FAQs that change executable behavior must be represented as
  `executable_patch` operations or `unsupported_executable_change` diagnostics,
  never as advisory-only records.

Required tests:

- Death Guard transition examples apply in a stable order;
- keyword-add patches update all declared datasheet targets and reject missing targets;
- profile-characteristic replacement changes only the named source profile field
  and records provenance;
- weapon-characteristic replacement changes only the named profile and records provenance;
- rule-text replacement and append operations normalize Unicode, quotes, dashes,
  distances, and HTML-free text;
- package hash changes on either upstream source drift or transition patch drift;
- unresolved, ambiguous, stale, or malformed patch targets produce actionable diagnostics;
- FAQ classification rejects executable changes stored as advisory-only records;
- patched source artifacts contain no raw HTML in runtime-bound fields.

## Phase 17B: canonical 11th Edition catalog generation from patched source data

Modules:

- `tools/build_catalog.py`
- `tools/apply_transition_patches.py`
- `tools/build_model_geometry_overrides.py`
- `core/datasheet.py`
- `core/army_catalog.py`
- `core/model_geometry_catalog.py`
- `core/faction.py`
- `core/detachment.py`
- `core/enhancement.py`
- `core/stratagem.py`
- `geometry/model_geometry.py`

Objects:

- `CanonicalCatalogPackage`
- `DatasheetCatalogRecord`
- `ModelGeometryCatalogRecord`
- `ModelFootprintDefinition`
- `ModelFootprintPartDefinition`
- `ModelHeightDefinition`
- `ModelGeometrySourceEvidence`
- `ModelGeometryImportDiagnostic`
- `WargearCatalogRecord`
- `WeaponProfileCatalogRecord`
- `FactionCatalogRecord`
- `DetachmentCatalogRecord`
- `EnhancementCatalogRecord`
- `StratagemCatalogRecord`

Invariants:

- all datasheets, model profiles, unit composition, wargear options, base sizes, model footprint geometry, representative model heights, keywords, and faction keywords come from source-linked catalog records;
- all factions and detachments are catalog records, not hand-authored fixture-only data;
- all stratagems and enhancements are source-linked descriptors;
- the catalog consumes patched 11th Edition source artifacts, never raw
  prior-edition mirror rows directly;
- generated catalog package hash is deterministic;
- catalog generation is idempotent and diffable;
- missing geometry/height/base overrides are explicit import blockers or unsupported descriptors, not silent defaults;
- CORE V1's `data/model_geometry_overrides.json` and
  `docs/MODEL_GEOMETRY_OVERRIDES.md` are reference material for the override
  data shape, but the Phase 17B implementation must not port V1's runtime
  fallback resolver wholesale;
- datasheet/model rows with `Use model`, blank base size, `No official base
  size`, bare `Hull`, Base Size Guide `hull`/`unique` classifications, or any
  non-circular/non-oval footprint that cannot be derived from source data require
  source-linked geometry override records before physical geometry package
  emission; Phase 17J Event Companion imports may still preserve the source row
  for roster/event legality with an unresolved geometry status;
- manual and crowd-sourced measurements must be represented as source evidence
  records with URL or document/page reference, measurement kind, dimensions,
  reviewer status, and deterministic source IDs; changing measurement evidence
  changes the catalog package hash;
- footprint, support-base, z-offset, and height records must declare source
  units and emit canonical runtime units plus coordinate frame/origin metadata;
  unit conversion changes must affect package hashes;
- flying-base models preserve the published support base separately from the
  model or hull footprint used for rules measurement/collision. A flying-base
  override must record support-base shape, body/hull footprint, optional
  stem/z-offset, representative height, rules-footprint policy, and provenance;
- automatic flying-hull proxy generation is tooling-only and may emit review
  diagnostics, but runtime engine code consumes only accepted catalog geometry
  records and must not infer hull dimensions from base size at instantiation;
- every unique model profile has a representative model height in catalog data,
  with provenance. Runtime LoS, vertical engagement/distance, and multi-floor
  terrain collision consume this height through `ModelGeometry`; keyword or
  base-minor-diameter height heuristics are migration diagnostics, not accepted
  Phase 17B runtime defaults.

Required tests:

- representative datasheets generate deterministic catalog records;
- model profiles preserve base-size, geometry-source, and height-source information;
- `Use model`, blank, `No official base size`, bare `Hull`, Base Size Guide
  `hull`/`unique`, and unresolved non-circular/non-oval rows fail physical
  geometry generation without explicit geometry override records, while source
  import can preserve them as unresolved event/base-size facts;
- flying-base overrides round-trip as support-base plus hull/body footprint,
  preserve z-offset provenance, and never derive z-offset from an overridden
  hull footprint instead of the support base;
- representative model heights round-trip for every unique model profile and
  missing heights are reported as import blockers or unsupported descriptors;
- manual/crowd-sourced measurement evidence is deterministic, reviewable, and
  included in package hash drift;
- wargear options and weapon profiles preserve stable IDs;
- faction/detachment/enhancement/stratagem records round-trip;
- package hash changes on source-data drift;
- unsupported rows are reported and cannot be instantiated accidentally.

CORE V1 relevant areas:

- `data/model_geometry_overrides.json`
- `docs/MODEL_GEOMETRY_OVERRIDES.md`
- `src/warhammer40k_ai/utility/model_geometry.py`
- `src/warhammer40k_ai/utility/model_base.py`
- `src/warhammer40k_ai/units/unit_mixins/datasheet_wargear_mixin.py`
- `tests/units/test_model_geometry_resolver.py`

## Phase 17C: rule language intermediate representation

Status: Complete.

This is the foundation for handling army rules, detachment rules, stratagems, enhancements, datasheet abilities, and wargear abilities via language parsing rather than hard-coding named items.

Phase 17C implements the source/tooling side of that foundation. Runtime
execution remains Phase 17D: unsupported IR cannot execute because no generic
execution host is introduced here.

Modules:

- `rules/rule_ir.py`
- `rules/rule_parser.py`
- `rules/rule_templates.py`
- `rules/rule_compiler.py`

Objects:

- `RuleIR`
- `RuleClause`
- `RuleTrigger`
- `RuleCondition`
- `RuleTargetSpec`
- `RuleEffectSpec`
- `RuleDuration`
- `RuleUnsupportedReason`
- `RuleParseDiagnostic`

Invariants:

- rule text compiles to a typed intermediate representation before runtime;
- IR is source-linked and keeps normalized-text spans;
- common language patterns compile into reusable rule templates;
- rules that cannot be represented produce explicit unsupported IR with diagnostics;
- parser output is deterministic and versioned;
- optional LLM-assisted parsing is offline/tooling-only and must emit reviewable deterministic IR; engine runtime never calls an LLM;
- named handlers are a fallback only for rules too specific for generic templates.

Initial supported language families:

- keyword gates;
- timing windows;
- within/outside distance predicates;
- selected unit/target constraints;
- dice roll modification;
- reroll permission;
- characteristic modifier;
- add/remove CP;
- add VP;
- grant ability until timing endpoint;
- conditional weapon ability grant;
- movement distance modification;
- placement permission/restriction;
- Aura source, range, eligible-target, and effect clauses;
- model/unit destruction trigger;
- once per phase/turn/battle restriction.

Required tests:

- normalized source text compiles to stable IR;
- unsupported clauses preserve source span and reason;
- grammar/parser changes are snapshot tested;
- multiple equivalent textual forms normalize to same IR where intended;
- runtime cannot execute uncompiled raw text.

## Phase 17D: generic rule execution handlers

Status: Complete.

Phase 17D provides the runtime execution host for compiled Phase 17C `RuleIR`.
`RuleExecutionContext`, `RuleRuntimeBinding`, `RuleExecutionRegistry`, and
`RuleExecutionResult` execute supported clauses through registered generic
handlers while preserving source IDs, IR hashes, deterministic event payloads,
and typed unsupported/invalid results. The default registry supports generic
modifier effects, reroll permissions, VP and CP resource changes, Stratagem
target binding, and Aura recomputation from current battlefield positions.
Abilities and Stratagems can bind `handler_id="generic:rule-ir"` to a replay-safe
compiled `rule_ir` payload; normal ability timing/keyword gates and Stratagem
target/CP/use-record paths still run before generic execution.

Modules:

- `engine/rule_execution.py`
- `engine/abilities.py`
- `engine/stratagems.py`
- `engine/effects.py`

Objects:

- `RuleExecutionHandler`
- `RuleExecutionContext`
- `RuleExecutionResult`
- `RuleTemplateHandler`
- `RuleRuntimeBinding`

Invariants:

- IR clauses execute through registered generic handlers;
- handlers declare required timing, state inputs, and target bindings;
- Aura abilities have a defined evaluation model that recomputes affected units from current positions, range, visibility/coherency gates, and source state as required by the descriptor;
- execution emits source-linked events;
- unsupported IR cannot execute;
- specific named handlers are allowed only when backed by source-linked tests and an unsupported generic shape is documented.

Required tests:

- generic modifier rule executes;
- generic reroll permission executes;
- generic VP scoring rule executes;
- generic Stratagem target binding executes;
- Aura evaluation updates affected units when movement-derived positions change;
- unsupported IR produces typed unsupported status.

## Phase 17E: faction, detachment, enhancement, and army-rule coverage

Status: complete.

Invariants:

- every faction has a source-linked army rule descriptor;
- every detachment has source-linked detachment rule, enhancement, and Stratagem descriptors;
- language parser produces generic IR where possible;
- unique imperative rules are isolated behind source-linked named handlers;
- coverage report groups implemented, generic-supported, named-handler-required, and unsupported rules.

Phase 17E is implemented by
`src/warhammer40k_core/rules/source_packages/warhammer_40000_11th/faction_coverage_2026_27.py`.
That package links every seeded faction and detachment row from
`faction_detachments_2026_27.py` to the official faction-pack PDF manifest,
validates the PDF filenames, byte counts, and SHA-256 digests, and emits
deterministic coverage rows. Army rules and detachment rules are
source-linked named-handler-required descriptors. Datasheet intake,
enhancement descriptor subrows, and Stratagem descriptor subrows that are not
present in the update PDFs are represented as approved unsupported diagnostics;
they cannot execute by fallback and must be replaced by native generated source
rows in later Phase 17 work.

Required tests:

- faction army-rule coverage descriptors load for every faction;
- detachment-rule coverage descriptors load for every detachment;
- enhancement and detachment Stratagem descriptors are source-linked or blocked
  by approved diagnostics;
- unsupported rule report is generated and non-empty only with approved reasons.

## Phase 17F: faction coverage execution dispatch and status

Status: complete.

Invariants:

- every Phase 17E coverage row has exactly one execution record;
- every execution record dispatches through a single engine path;
- execution attempts return deterministic JSON-safe applied, invalid, or unsupported results;
- blocked execution uses approved source-linked reasons, never missing handlers or silent no-ops;
- executable execution statuses require a registered generic IR executor or
  named handler before they can return applied;
- runtime execution consumes structured descriptors and never parses PDFs or raw rule text.

Phase 17F is implemented by
`src/warhammer40k_core/rules/source_packages/warhammer_40000_11th/faction_execution_2026_27.py`
and `src/warhammer40k_core/engine/faction_rule_execution.py`. The source package
maps all Phase 17E faction army-rule, detachment-rule, enhancement descriptor,
Stratagem descriptor, and datasheet-intake coverage rows into execution records.
The engine dispatcher resolves every record through a typed execution result.
Rows that still lack native structured semantics are explicitly unsupported with
approved reasons; they do not execute by fallback and do not disappear as
missing handlers. Executable statuses without registered executors return typed
unsupported diagnostics instead of APPLIED.
Phase 17F does not implement faction-rule semantics. Its completion means every
Phase 17E row is routable through one fail-closed engine dispatch path, not that
army rules, detachment rules, enhancements, or Stratagems have executable game
effects.

Required tests:

- execution records cover every Phase 17E coverage row;
- execution package payloads are deterministic, JSON-safe, and checksum-guarded;
- execution status counts match Phase 17E coverage status counts;
- execution registry dispatches every record without missing handlers;
- executable records without registered executors return typed unsupported results;
- blocked execution records reject unapproved or inconsistent block shapes.

## Phase 17G: faction army/detachment/enhancement/Stratagem semantic execution

Phase 17G implements actual engine support for the Phase 17E faction-level
items. It does not cover broad datasheet, wargear, or weapon ability execution;
that moves to Phase 17H. Faction and detachment rules with pre-battle timing
must bind to the Event Companion setup sequence from Phase 17J when Warhammer
Event mode is active. They may not introduce ad hoc pre-battle ordering.

Invariants:

- faction army rules execute through structured descriptors, generic IR, or
  source-linked named handlers;
- detachment rules execute through lifecycle hooks at their official timing
  points;
- enhancements validate eligibility from the Phase 16D army-construction
  provenance and apply their effects through engine-owned mutation;
- faction and detachment Stratagems validate CP cost, timing, target legality,
  repeat-use limits, and effect application through the shared Stratagem
  decision/ledger path;
- all semantic handlers consume structured descriptors and never parse PDFs or
  raw rule text at runtime;
- unsupported faction-level behavior returns typed unsupported execution results
  with approved source-linked reasons.

Required tests:

- faction army rules load and execute for every faction through the registered
  engine path;
- detachment rules load and execute for every detachment through registered
  lifecycle hooks;
- enhancements validate eligibility and execute generic or named effects where
  supported;
- faction and detachment Stratagems validate timing, targeting, CP ledgers,
  repeat-use constraints, and effects;
- UI, headless, network, replay, and tests use the same execution dispatch and
  decision path.

## Phase 17H: datasheet, wargear, and weapon ability execution

Invariants:

- wargear abilities are linked only to selected wargear;
- unselected wargear never grants rules;
- selected wargear payload drift is rejected;
- datasheet abilities and weapon abilities use source-linked descriptors and handlers;
- datasheet abilities with setup, redeploy, Scout, or pre-battle timing declare
  an exact Event Companion timing hook: `declare_battle_formations`,
  `deploy_armies`, `redeploy_units`, `resolve_pre_battle_rules`, or
  `begin_battle`;
- covered datasheet, wargear, and weapon ability items execute through generic IR
  or source-linked named handlers when supported;
- unsupported covered items return typed unsupported execution results with
  approved reasons;
- all imported behavior has tests or explicit unsupported status.

## Phase 17I: source-content coverage and unsupported-descriptor audit

Required outputs:

- coverage report for datasheets, abilities, wargear, detachments, enhancements, Stratagems, and army rules;
- Event Companion mission-sequence coverage report;
- Primary Mission matrix and scoring coverage report;
- Secondary Mission procedure and card coverage report;
- FAQ/errata patch coverage report;
- terrain, deployment, objective, and layout coverage report;
- Base Size Guide coverage report, including unresolved `Hull`, Small Flying
  Base, Large Flying Base, and `Unique` geometry counts;
- execution-status report for every covered item, grouped by applied,
  generic-supported, named-handler-supported, invalid, and unsupported status;
- list of unsupported descriptors grouped by reason;
- static audit that runtime code does not parse raw source text;
- static audit that runtime code does not parse Event Companion PDF text,
  layout images, or raw mission-card prose;
- CI artifact with package hashes and coverage totals.

## Phase 17J: Warhammer Event Companion mission-pack and geometry source inventory

Status: Complete.

Phase 17J turns the Warhammer Event Companion v1.0 into a source-backed CORE V2
package. It owns Event Mission Sequence ordering, Force Disposition roster
binding, per-player Primary Mission selection, layout A/B/C source-page
identity, deterministic battlefield creation from layout descriptors,
Attacker/Defender assignment, Secondary Mission mode selection, Tactical/Fixed
Secondary lifecycle, Primary/Secondary/Battle Ready VP caps, mission-card
scoring grammar, Event Companion FAQs, terrain/deployment/objective layout
coordinate-extraction status, and Base Size Guide import.

Implemented modules:

- `rules/source_packages/warhammer_40000_11th/event_companion_2026_06.py`
- `rules/source_packages/warhammer_40000_11th/event_companion_patches.py`
- `rules/mission_pack_import.py`
- `engine/missions.py`
- `engine/mission_decisions.py`
- `engine/deployment.py`

Implemented coverage:

- Event Companion package identity, source package hash, no Deployment/Twist
  card invariant, Event Mission Sequence descriptor, Tactical/Fixed Secondary
  procedure descriptors, and mission-card scoring grammar are source-backed
  deterministic payloads.
- Event Companion mission-pack import builds 25 Primary Mission descriptors, 25
  implemented matrix cells, 45 deployment maps, 45 terrain layout templates, and
  45 mission-pool entries.
- All 45 source-page layout identities instantiate as 44" x 60" mission setups
  with deterministic layout descriptors while exact per-page coordinate
  extraction remains explicitly marked pending.
- Event Companion v1.0 card amendments are explicitly empty and distinct from
  source-linked FAQ patch records.
- Base Size Guide source rows record round, oval, Hull, Small Flying Base, Large
  Flying Base, and Unique source kinds with geometry-resolution statuses.
- Mission scoring and deterministic Tactical Secondary draw resolve through a
  strict mission-pack lookup for both Chapter Approved and Event Companion pack
  IDs.
- Deployment queue behavior has regression coverage for the Event Companion
  remainder-drain rule after one player has no undeployed non-reserve units.
- Runtime core, engine, and geometry modules are statically audited to prevent
  raw Event Companion PDF text/image parsing.

Package identity:

- `source_kind = "warhammer_event_companion"`
- `document_version = "1.0"`
- `event_mode = "warhammer_event"`
- `battlefield_size = "44x60_inches"`
- `excludes_deployment_cards = true`
- `excludes_twist_cards = true`

Objects:

- `WarhammerEventMissionSequenceDescriptor`
- `WarhammerEventLayoutDescriptor`
- `SecondaryMissionModeState`
- `FixedSecondarySelection`
- `TacticalSecondaryState`
- `MissionScoringDescriptor`
- `MissionCardScoringGrammar`
- `EventCompanionFaqPatch`
- `BaseSizeSourceRecord`
- `GeometryResolutionStatus`

Invariants:

- Warhammer Event mode does not consume Deployment or Twist cards.
- Force Disposition is selected during mustering and recorded on the roster.
- Each player's Primary Mission is derived from that player's Force Disposition
  card using the opponent's Force Disposition symbol.
- Layout selection is source-backed and resolves to one of the three A/B/C
  layout variants for the Primary Mission combination.
- Layout selection records whether the event organizer specified the variant or
  the players randomly determined it.
- Create Battlefield instantiates a 44" x 60" battlefield with deterministic
  terrain areas, terrain features, objective points, deployment zones,
  territories, and Attacker/Defender battlefield edges from layout descriptors
  whose Event Companion coordinate extraction status remains explicit.
- Attacker/Defender is determined after battlefield orientation and before
  Secondary Mission selection.
- Secondary Mission mode selection is hidden until reveal.
- Fixed Secondaries are selected secretly, revealed, face-up, non-discardable,
  and active for the whole battle.
- Tactical Secondary draw-two occurs at the start of the controlling player's
  Command phase and makes the drawn cards active.
- Once per battle, at the end of that player's Command phase, that player may
  spend 1CP to discard exactly one active Tactical Secondary Mission and draw
  exactly one replacement.
- At the end of each player's turn, both players resolve Secondary achievement
  checks starting with the active player; achieved Tactical Secondaries are
  discarded only when VP is gained.
- Then, if it is the active player's own turn and that player uses Tactical
  Secondaries, that player may discard one or more active Tactical Secondaries
  to gain 1CP.
- Declare Battle Formations records embarked units before Strategic Reserves,
  then reveals both players' battle formations.
- Deploy Armies alternates from the Defender and enforces the TITANIC
  skip-next-deployment-turn rule.
- Once a player has finished setting up all non-Strategic-Reserve units, if the
  opponent still has undeployed units, the opponent drains and sets up those
  remaining units through source-backed deployment decisions.
- Redeploy alternates from the Attacker and records redeploy-to-reserves cap
  exemption.
- Determine First Turn is a roll-off whose winner takes the first turn.
- Resolve Pre-battle Rules alternates from the first-turn player.
- The battle lasts five battle rounds, including games where one player has no
  models remaining.
- Primary, Secondary, Fixed-card, Battle Ready, and total VP caps are
  source-backed and enforced by the scoring ledger.
- Mission-card scoring supports `cumulative_condition`,
  `exclusive_or_condition`, `exactly_one_condition`, `vp_up_to_limit`,
  `when_drawn_tactical_only`, and `leaves_battlefield_event`.
- Event Companion v1.0 has an empty Chapter Approved Mission Deck
  card-amendment set; FAQ behavior is represented as source-linked patch
  operations separately.
- Event Companion FAQ behavior for operation marker removal, Death Trap,
  Surveil the Foe, and Vital Link is represented as source-linked patch
  operations, not runtime string checks.
- `WarhammerEventLayoutDescriptor` records layout ID, Force Disposition pair,
  player Primary Missions, layout variant, 44" x 60" battlefield size,
  Attacker/Defender edges, deployment-zone polygons, No Man's Land polygon,
  player territory polygons, typed objective points, terrain areas, dense/light
  terrain features, source page, and coordinate-extraction status.
- All Event Companion layout records bind to source pages and expose pending
  coordinate-extraction status rather than consuming screenshots at runtime.
- Base Size Guide rows import with `base_source_kind` values for round, oval,
  Small Flying Base, Large Flying Base, Hull, Unique, and unresolved source
  shapes.
- Base Size Guide rows carry `geometry_resolution_status` values for canonical
  geometry available, requires project geometry override, requires event
  organizer override, or unsupported for physical geometry.
- Hull, Small Flying Base, Large Flying Base, and Unique base-size rows are
  imported as source facts but require explicit geometry overrides before
  movement, line of sight, engagement, deployment, or collision consumers may
  use them.
- Any new Event Companion decision type, option family, proposal shape, or
  viewer-visibility behavior updates `docs/ADAPTER_DECISION_CONTRACT.md` in the
  same implementation PR.
- No runtime path parses raw PDF text, layout images, or mission-card prose.

Required tests:

- complete Event Mission Sequence replay from mustering through battle start;
- hidden Tactical/Fixed and Fixed-card choices reveal correctly;
- Tactical start-of-Command draw-two, end-of-Command once-per-battle
  discard/draw, achieved-discard-only-when-VP-is-gained, and own-turn
  discard-one-or-more-for-CP behavior;
- both-player end-of-turn Secondary scoring starts with the active player;
- Primary, Secondary, Battle Ready, and total caps reject excess VP;
- pre-battle abilities cannot resolve before first-turn determination;
- Defender-first deployment and TITANIC skip;
- deployment queue drains opponent remaining units after one player has finished
  deploying;
- Attacker-first redeploy and redeploy-reserve cap exemption;
- all Event Companion layout descriptors load and instantiate;
- all objective-point types and deployment-zone polygons validate;
- all terrain areas/features validate dense/light status and footprint
  inventory;
- all Base Size Guide rows import with geometry resolution status;
- Hull, Flying Base, and Unique rows fail closed for movement/LoS without a
  geometry override;
- replay hashes are stable for setup, layout selection, scoring, and game end.

Tournament pairings and rankings from the Event Companion are event-operations
guidance, not battle-engine rules. Future support belongs outside
`engine/game_state.py`, for example in `event_ops/pairings.py` and
`event_ops/rankings.py`, consuming completed game results and VP ledgers without
affecting in-game legality, scoring, or replay state.

---

# Human UI, replay, and network

## Phase 18A: local CLI/human DecisionRecord entry

Modules:

- `interfaces/cli.py`
- `engine/decision_controller.py`
- `engine/decision_record.py`

Invariants:

- every pending `DecisionRequest` can be displayed in a human-readable CLI form;
- CLI responses become normal `DecisionResult`s;
- CLI never mutates state directly;
- CLI-entered decisions produce `DecisionRecord`s identical in shape to headless decisions;
- hidden information display is scoped to the acting player.

Required tests:

- CLI adapter renders finite options;
- invalid CLI choice is rejected;
- valid CLI choice submits normal `DecisionResult`;
- DecisionRecord round-trips.

## Phase 18B: replay inspection and deterministic replay runner

Invariants:

- replay can load snapshot + event/decision tail;
- replay can step forward deterministically;
- replay drift is detected and reported;
- replay can export human-readable decision/event traces;
- replay can export training-friendly DecisionRecord corpora.

## Phase 18C: local visual game UI

Invariants:

- UI displays battlefield, terrain, units, objectives, phase state, and pending decisions;
- UI submits only `DecisionResult`s;
- UI can visualize movement paths, LoS witnesses, attack allocation, scoring, and Stratagem windows;
- UI never owns authoritative state progression.

## Phase 18D: network/server-authoritative play

Invariants:

- server owns authoritative lifecycle and validation;
- clients render public state and submit decisions;
- hidden information remains hidden from opponent clients;
- network resync preserves replay hash/state hash.

Event Companion adapter/replay/UI requirements:

- hidden Tactical/Fixed selection and Fixed Mission choices remain viewer-scoped
  until reveal;
- hidden battle formation declarations remain viewer-scoped before reveal;
- TO-specified and randomly selected layout variants are both represented as
  source-page-bound decisions/events;
- Attacker/Defender assignment preserves physical edge orientation;
- Tactical Secondary active cards, discards, achieved cards, and
  end-of-Command once-per-battle 1CP discard-and-draw usage are inspectable
  from replay-safe state;
- VP source caps and final scoring audit are displayed without adapter-side
  recalculation;
- layout visualizers consume source descriptors, not page images.

---

# Profiling, AI orchestration, and corpus generation

## Phase 19A: full-game performance profiling, hotspot benchmarks, and throughput budgets

Modules:

- `profiling/`
- `scripts/run_headless_self_play.py`
- `scripts/profile_full_game.py`
- `tests/performance/`

Objects:

- `FullGamePerformanceScenario`
- `HeadlessThroughputReport`
- `HotspotReport`
- `PerformanceBudget`

Invariants:

- headless games are fast enough for large DecisionRecord corpora;
- profiling reports identify pathing, LoS, candidate generation, scoring, serialization, attack resolution, and language-rule execution hotspots;
- same seed and same scenario produce deterministic results modulo timing values;
- CI runs small smoke benchmarks;
- nightly/manual profiling runs larger battlefield and full-game workloads;
- performance optimization cannot change authoritative replay output.

Required tests / scripts:

- full-game smoke benchmark;
- movement/pathing benchmark;
- LoS/shooting benchmark;
- candidate-generation benchmark;
- serialization/replay benchmark;
- language-rule execution benchmark;
- hotspot report JSON schema validation;
- budget failure exits non-zero.

CORE V1 relevant areas:

- `docs/HEADLESS_SELF_PLAY_RUNBOOK.md`
- `docs/PROFILING.md`
- `scripts/run_headless_self_play.py`
- `src/warhammer40k_ai/engine/time_manager.py`
- `src/warhammer40k_ai/engine/tier2_orchestrator.py`
- `src/warhammer40k_ai/engine/movement_solver.py`

## Phase 19B: legal-candidate generation and action-space masking

Invariants:

- every AI candidate is generated from a `DecisionRequest`;
- candidate generation never bypasses authoritative validation;
- illegal candidates are masked before ranking;
- candidate payloads include enough context for training and replay diagnostics;
- bounded search budgets are deterministic and report timeout/skip reasons.

## Phase 19C: hierarchical AI policy orchestration: General, Commanders, Rankers

Modules:

- `ai/orchestrator.py`
- `ai/general.py`
- `ai/commanders/`
- `ai/rankers/`

Objects:

- `AIPolicyOrchestrator`
- `GeneralPolicy`
- `PhaseCommander`
- `ActionRanker`
- `PolicyBundle`
- `CandidateScore`

Invariants:

- General chooses strategic posture/goals;
- Commanders own phase/domain-specific candidate interpretation;
- Rankers score already-legal candidates;
- AI never mutates engine state directly;
- AI decisions submit ordinary `DecisionResult`s;
- AI-selected decisions produce normal `DecisionRecord`s;
- policy latency, candidate counts, legal masks, and fallback modes are recorded for profiling and training.

Required tests:

- orchestrator routes movement/shooting/charge/fight/dice decisions to correct component;
- ranker sees only legal candidates;
- AI decision produces ordinary DecisionRecord;
- same seed/policy produces deterministic choices.

## Phase 19D: headless self-play and DecisionRecord corpus export

Invariants:

- AI-vs-AI self-play can run without UI;
- games produce DecisionRecord corpora;
- replay artifacts can be saved for each game;
- failed games produce structured diagnostics;
- parallel workers preserve deterministic per-game seeds;
- hidden information is not leaked into public DecisionRecords.

Required outputs:

- JSONL/SQLite DecisionRecord export;
- replay manifest;
- self-play summary report;
- failure triage report.

## Phase 19E: training-data, reward annotation, and evaluation pipeline

Invariants:

- reward profiles are explicit and versioned;
- generated corpora include game result, VP deltas, action context, legal mask, chosen action, and policy metadata;
- evaluation can compare policies on fixed seed/matchup batches;
- training data schema is stable and validated.

Event Companion scenario coverage:

- candidate generation includes setup decisions for Force Disposition,
  Tactical/Fixed choice, Fixed cards, deployment order, redeploy, and
  first-turn-conditioned pre-battle rules;
- AI policies account for per-player Primary Missions derived from Force
  Disposition pairing;
- self-play corpora record layout ID, mission pair, Secondary mode, active
  Secondaries, scoring opportunities, VP caps, and final win/draw/loss;
- reward annotation must not treat tournament VP as the primary event-ranking
  proxy, because Event Companion event rankings prioritize record and opponent
  win records before total VP.

---

# Full-game gates

## Phase 20A: full-game rules-compliance matrix

Create a machine-readable coverage matrix mapping 11th Edition Core Rules sections to implementation modules and tests.

Required coverage areas:

- core concepts;
- datasheets and keywords;
- dice, D3, roll-offs, random characteristics, rerolls, and modifiers;
- sequencing;
- Command phase;
- Battle-shock;
- Movement phase;
- terrain movement;
- transports;
- Strategic Reserves;
- Aircraft;
- Shooting phase, target declaration, Close-quarters shooting, Indirect/Snap shooting, `[CLOSE-QUARTERS]`/`[PISTOL]`, Lone Operative;
- attack sequence, fast dice, mortal wounds, Feel No Pain, Deadly Demise, and damage allocation;
- weapon abilities;
- Charge phase;
- Fight phase;
- Stratagems;
- full Warhammer Event Mission Sequence;
- Force Disposition roster binding and per-player Primary Mission resolution;
- Event Companion Secondary procedure;
- Primary, Secondary, Battle Ready, and total VP caps;
- five-round game end and tabled-player continuation;
- all Event Companion FAQ entries;
- all Event Companion layout descriptors from the source pages;
- terrain footprint inventory and dense/light feature status;
- Base Size Guide import, including Hull/Flying Base/Unique unresolved-geometry
  accounting;
- no Deployment/Twist cards in Warhammer Event mode;
- objective control;
- terrain visibility and cover;
- deployment and pre-battle abilities;
- faction/detachment/enhancement rules.

## Phase 20B: end-to-end full-game regression suite

Required tests:

- full two-player game completes through final scoring;
- replay round-trip at multiple battle rounds;
- no hidden information leaks;
- deterministic same-seed replay;
- all source-page Event Companion layout identities and coordinate-extraction
  coverage for each Force Disposition/Primary Mission combination;
- multiple army archetypes;
- multiple mission packs.

## Phase 20C: balance/performance/stability soak

Required runs:

- local AI-vs-AI corpus generation;
- long-running replay validation;
- profiling hotspot report;
- unsupported descriptor report;
- crash/failure triage report.

## Phase 20D: release gate for complete 11th Edition CORE V2

Exit criteria:

- all Core Rules coverage rows are either implemented or explicitly unsupported with reason;
- zero unresolved Warhammer Event Mission Sequence, scoring, and layout rows;
- Hull, Flying Base, and Unique geometry rows may remain explicitly unsupported
  only when the unsupported reason is source-linked and the row is blocked from
  physical geometry consumers;
- full-game regression suite passes;
- headless throughput budget passes;
- replay determinism passes;
- source-content coverage report is generated;
- human CLI can complete a game;
- AI self-play can complete many games;
- UI can inspect and play a local game;
- network authoritative mode can synchronize state and decisions.

---

# Rules coverage map

| Rules area | Planned phase(s) |
|---|---|
| Dice, rerolls, roll-offs | 1, 10J, 10N, 12C, 13C, 15A, 14C, 14I |
| Datasheets and keywords | 9A, 9C, 17A-17J, 14A, 14J |
| Army mustering | 9C, 16D, 17B, 14J |
| Setup sequence | 9B, 11A, 16A-16E, 14B, 14J, 17J |
| Deployment zones | 11A, 16A, 14J, 17J |
| Redeployments | 10D, 16B, 14H |
| Engagement Range | 10G, 10M, 10N, 10O, 15B, 14C, 14G |
| Unit Coherency | 10G/10H descriptors, 10L runtime, 11E cleanup, 14C |
| Terrain movement | 10F, 10H, 10I, 14D |
| Terrain visibility/cover, including Hidden, Obscuring, Solid, Benefit of Cover, Plunging Fire, and Event Companion layout identity/geometry coverage | 13A, 13C, 14D, 14E, 17J |
| Movement phase Move Units | 10B-10T, 14D |
| Movement phase reserve arrivals and Ingress Moves | 10P, 14D, 14H |
| Transports | 10Q, 14H |
| Aircraft | 10R, 14H |
| Command phase | 11C, 14B, 14C |
| Battle-shock | 11C, 12B, 14C |
| Mission scoring | 11A-11C, 11E-11F, 14J, 17J |
| Stratagems | 12B, 12C, 13D, 15E, 17E-17G, 14I |
| Shooting phase | 13A-13F, 14E, 14F |
| Weapon abilities | 8D, 13D, 17H, 14I |
| Aura abilities | 17C, 17D, 17G-17H |
| Charge phase | 15A, 15B, 14G |
| Fight phase | 15C, 15D, 15E, 15F, 14G |
| Leader/attached units | 6, 16D, 17A, 14H |
| Faction/detachment/enhancement rules | 17C-17G, 14J |
| Mission packs | 11A, 11E, 11F, 16A, 17J, 20A, 14J |
| Adapter/UI contract | 11D, 12B, 14D-14I, 17J |
| Human CLI/UI | 18A, 18C |
| Network play | 18D |
| Replay | 18B, all state-changing phases |
| AI/headless self-play | 19B-19E |
| Performance budgets | 10U, 19A |
| 11th Edition migration/revalidation | 14A-14K, 17J |
