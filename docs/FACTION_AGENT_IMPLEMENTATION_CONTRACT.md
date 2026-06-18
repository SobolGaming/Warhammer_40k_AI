# Faction Agent Implementation Contract

This contract applies to agent-authored faction-content PRs after the generated
Phase 17G runtime scaffold exists.

## Scope

Each agent PR must modify only the assigned faction or detachment scaffold files
unless a shared helper is explicitly required and justified in the PR. Runtime
loader, lifecycle, bundle, and manifest machinery are out of scope for ordinary
faction implementation PRs.

Allowed detachment implementation files follow this shape:

```text
src/warhammer40k_core/engine/faction_content/warhammer_40000_11th/
  <faction_slug>/
    army_rule.py
    detachments/
      <detachment_slug>/
        rule.py
        enhancements.py
        stratagems.py
```

Generated `manifest.py` files are stable aggregators. Faction manifests import
the sibling `army_rule.py`; detachment manifests import sibling `rule.py`,
`enhancements.py`, and `stratagems.py`. Do not edit manifest files in ordinary
implementation PRs.

Agent-owned scaffold files start with this marker:

```text
# Generated scaffold placeholder. Remove this marker when implementing semantics.
```

Remove the marker when the file implements source-backed semantics. The file
must keep a stable `CONTRIBUTION_ID` and `runtime_contribution()` export.

Do not parse raw rule text or import source-mirror, HTML sanitizer, parser, or
compiler tooling from runtime faction-content modules.

## Runtime Surfaces

Use existing `RuntimeContentContribution` surfaces:

- ability records;
- Stratagem records;
- ability handler bindings;
- Stratagem handler bindings;
- event subscriptions and event handler bindings;
- Battle-formation hook bindings for source-backed setup-time faction or army
  rule choices;
- Battle-round start hook bindings for source-backed faction or army rules that
  require a player choice at the start of a battle round;
- Battle-shock hook bindings for rules whose trigger is Battle-shock modifier
  or outcome resolution;
- Fall Back eligibility hook bindings for rules whose effect is that a Fall Back
  move does not prevent later Shooting or Charge eligibility;
- Movement-end surge hook bindings for opponent Movement phase rules that
  trigger after an enemy unit ends a move and may grant source-bounded
  triggered movement;
- phase-end objective-control hook bindings for detachment rules that retain or
  alter objective control at phase-end scoring boundaries;
- enhancement effect bindings for Enhancement or Upgrade effects that are
  selected from Phase 16D army-construction records and materialize static
  engine-owned characteristic modifiers;
- Fight activation ability hook bindings for optional rules whose timing is
  when a unit is selected to fight and whose immediate effect is a scoped
  engine-owned melee targeting permission;
- unit characteristic modifier bindings for source-backed modifiers to model or
  unit characteristics consumed by engine queries;
- Hit roll modifier bindings for source-backed modifiers consumed by the attack
  sequence hit-roll step;
- save option modifier bindings for source-backed changes to available save
  options consumed by the attack sequence save step;
- movement budget modifier bindings for source-backed Move characteristic or
  movement budget modifiers consumed by Movement phase path validation;
- objective-control modifier bindings for source-backed Objective Control
  characteristic modifiers consumed by objective-control scoring;
- charge roll modifier bindings for source-backed modifiers consumed by Charge
  phase roll resolution;
- weapon profile modifier bindings for source-backed keyword or ability changes
  consumed by attack declaration/resolution hosts;
- RuleIR runtime bindings;
- faction named handlers.

Semantic execution must run through registered engine paths. Leave unimplemented
rule shapes as explicit unsupported diagnostics, not no-ops, defaults, or silent
fallbacks.

Battle-shock hook bindings are an approved runtime contribution surface only for
source-backed rules that execute inside Battle-shock resolution. Each hook
binding must use a `source_id` from the generated Phase 17F execution rows for
the implemented rule, and tests must prove that the selected runtime manifest
row loads the hook through `GameLifecycle` without manual handler injection.
Hook handlers must mutate authoritative state only through engine-owned
services and must emit deterministic replay-safe events or explicit unsupported
diagnostics.

Battle-formation hook bindings are an approved runtime contribution surface
only for source-backed setup-time choices whose result creates later
engine-consumed faction state. Each hook binding must use a `source_id` from the
generated Phase 17F execution rows for the implemented rule, and tests must
prove that the selected runtime manifest row loads the hook through
`GameLifecycle` without manual handler injection. Accepted choices must be
recorded through engine-owned `DecisionRequest` / `DecisionResult` handling,
must emit deterministic replay-safe payloads, and must not mutate downstream
phase state directly.

Battle-round start hook bindings are an approved runtime contribution surface
only for source-backed choices made at the start of a battle round before the
first player's Command phase proceeds. Each hook binding must use a `source_id`
from the generated Phase 17F execution rows for the implemented rule, and tests
must prove that the selected runtime manifest row loads the hook through
`GameLifecycle` without manual handler injection. Hook request handlers may use
engine-owned dice services when the source rule requires a roll, but accepted
choices must still be recorded through engine-owned `DecisionRequest` /
`DecisionResult` handling, emit deterministic replay-safe payloads, and avoid
mutating downstream phase state directly.

Runtime modifier bindings are approved runtime contribution surfaces only for
source-backed modifiers that can be expressed as a typed value adjustment at an
existing engine query point. Each modifier binding must use a source-linked
`modifier_id` and `source_id`, and tests must prove both bundle/lifecycle
loading and at least one real consumer path for the modified engine area.
Handlers must return typed values only: unit characteristic modifiers return the
modified characteristic value, Hit roll modifiers return an integer roll
modifier, save option modifiers return the modified save-option tuple, movement
budget modifiers return the modified movement budget in inches, and
objective-control modifiers return the modified OC value. Charge roll modifiers
return the modified roll-modifier tuple, and weapon profile modifiers return the
modified `WeaponProfile`. Faction modules must not roll dice, move models,
mutate battlefield/objective state, spend CP, or rewrite attack sequence state
from these handlers; the engine-owned consumer continues to perform validation,
mutation, event emission, and replay-safe payload generation.

Fall Back eligibility hook bindings are an approved runtime contribution surface
only for source-backed rules that modify the consequences of a completed Fall
Back move. Each hook binding must use a `source_id` from the generated Phase 17F
execution rows for the implemented rule. Hook handlers must return typed
permission grants; the Movement engine records the authoritative
`FellBackUnitState`, emits deterministic replay-safe grant payloads, and the
Shooting and Charge phases consume that engine-owned state. Faction modules must
not mutate Fall Back, Shooting, or Charge phase state directly.

Movement-end surge hook bindings are an approved runtime contribution surface
only for source-backed rules whose trigger is an enemy unit ending a move during
the Movement phase. Each hook binding must use a `source_id` from the generated
Phase 17F execution rows for the implemented rule. Hook handlers return typed
eligible-unit grants only; the Movement engine owns the D6 surge distance roll,
the finite triggered-movement unit-selection request, the follow-up
`submit_movement_proposal` request with proposal kind `surge_move`, PathWitness
validation, authoritative battlefield mutation, and deterministic replay-safe
`SurgeMoveState` records. Faction modules must not roll dice, move models,
write battlefield placements, or bypass the shared decision path.

Phase-end objective-control hook bindings are an approved runtime contribution
surface only for source-backed rules whose timing is the end of a phase and
whose effect is retained or adjusted objective control. Each hook binding must
use a `source_id` from the generated Phase 17F execution rows for the
implemented rule. Hook handlers return typed objective-control state records
derived from engine snapshots and objective-control records; `GameState` owns
the retained-control overlay, expiry checks, and phase-boundary
objective-control event records. Faction modules must not mutate scoring,
objective-control history, or battlefield state directly.

Stratagem handler bindings are an approved runtime contribution surface for
source-backed faction or detachment Stratagems whose timing is represented by an
engine timing window. Selected-to-move Stratagems use the finite
`use_stratagem` decision surface with trigger kind
`just_after_friendly_unit_selected_to_move`, after Movement unit selection and
before Movement action selection. End-of-Movement ingress Stratagems may use the
generic `generic:ingress-move` handler when they target a source-backed friendly
Strategic Reserves unit and then emit the normal `submit_placement_proposal`
Strategic Reserves path. Selected-Fall-Back reaction Stratagems may use the
generic `generic:force-desperate-escape` handler when the opponent selects a
Fall Back move and a friendly source-backed target unit is engaged with that
enemy unit; the handler records engine-owned `PersistingEffect` state and the
Movement engine emits the resulting Fall Back proposal with
`fall_back_mode: "desperate_escape"`. Detachment Stratagem records must enter
the player Stratagem index only when the owning detachment is selected and
materialized by the runtime content bundle. Handlers must validate timing,
target ownership, required keywords, CP cost, and repeat-use restrictions
through the shared Stratagem path, then apply effects through engine-owned state
such as `PersistingEffect` records or placement proposal requests. Faction
modules must not spend CP, add movement keywords, mutate movement state, set
reserve arrivals, or adjust terrain legality outside the engine
Stratagem/movement services.

Enhancement effect bindings are an approved runtime contribution surface for
source-backed Enhancement or Upgrade effects whose selected army-construction
assignment creates a static engine-owned characteristic modifier. Each binding
must use the generated Phase 17F execution row ID for the implemented
enhancement descriptor family until exact enhancement subrows exist. Eligibility
must be validated from Phase 16D `ArmyMusterRequest` / `ArmyDefinition` records
and structured catalog target requirements. Binding handlers return typed
modifier descriptors only; the lifecycle-owned enhancement effect service
applies them to authoritative army definitions, keeps application idempotent,
and emits deterministic replay-safe payloads. Faction modules must not mutate
army definitions, model characteristics, movement budgets, or battlefield state
directly.

Fight activation ability hook bindings are an approved runtime contribution
surface only for source-backed optional rules whose trigger is a unit being
selected to fight. Each hook binding must use a `source_id` from the generated
Phase 17F execution rows for the implemented rule or enhancement descriptor
family until exact subrows exist, and tests must prove that the selected runtime
manifest row loads the hook through `GameLifecycle` without manual handler
injection. Hook handlers return typed ability options only; the Fight engine
owns the finite use/decline `DecisionRequest`, records the authoritative
`PersistingEffect`, and emits deterministic replay-safe payloads. Faction
modules must not mutate Fight phase state, melee declarations, attack pools, or
battlefield state directly.

## Decision And Mutation

Preserve engine-owned mutation and the shared `DecisionRequest` /
`DecisionResult` path. UI, CLI, headless, network, AI, replay, and tests may
choose decisions differently, but they must not validate or mutate through a
separate path.

## Required Tests

Each implementation PR must add focused tests for the assigned content:

- timing and lifecycle hook behavior;
- targeting and eligibility;
- invalid and unsupported cases;
- CP, repeat-use, or pre-spend validation for Stratagems when applicable;
- replay and audit payloads for state-changing behavior;
- handler identity drift and source-link mismatches.

Tests must use real domain objects or canonical fixtures for engine behavior.
Pure-function stubs are allowed only when marked `stubbed`.

## Task Packet Format

Use generated task packets with explicit source-owned scope:

```text
Task: Implement Orks / War Horde detachment

Allowed files:
- src/warhammer40k_core/engine/faction_content/warhammer_40000_11th/orks/detachments/war_horde/rule.py
- src/warhammer40k_core/engine/faction_content/warhammer_40000_11th/orks/detachments/war_horde/enhancements.py
- src/warhammer40k_core/engine/faction_content/warhammer_40000_11th/orks/detachments/war_horde/stratagems.py
- tests/unit/faction_content/warhammer_40000_11th/orks/test_war_horde.py

Required:
- Use source IDs from generated manifest and execution rows.
- Remove the generated placeholder marker from implemented files.
- Register named handlers or RuleIR bindings only where semantics are supported.
- Register Battle-formation hook bindings only for source-backed setup-time
  choices, and link them to generated Phase 17F execution row IDs.
- Register Battle-shock hook bindings only for Battle-shock timing semantics,
  and link them to generated Phase 17F execution row IDs.
- Register Fall Back eligibility hook bindings only for source-backed rules
  that change Fall Back Shooting or Charge permissions, and link them to
  generated Phase 17F execution row IDs.
- Register Movement-end surge hook bindings only for source-backed rules that
  trigger after enemy Movement phase move completion, and link them to generated
  Phase 17F execution row IDs.
- Register phase-end objective-control hook bindings only for source-backed
  rules that retain or adjust control at phase-end objective-control boundaries,
  and link them to generated Phase 17F execution row IDs.
- Register faction or detachment Stratagems through source-backed Stratagem
  records and named or approved generic handlers only when an engine timing
  window exists. End-Movement ingress Stratagems may use
  `generic:ingress-move`; selected-Fall-Back reaction Stratagems may use
  `generic:force-desperate-escape`. Prove runtime detachment materialization
  registers them before `use_stratagem` options are emitted.
- Register enhancement effect bindings only for source-backed Enhancement or
  Upgrade effects selected through Phase 16D army-construction records, and link
  them to generated Phase 17F enhancement descriptor row IDs until exact
  enhancement subrows exist.
- Register Fight activation ability hook bindings only for optional
  selected-to-fight rules, and link them to generated Phase 17F execution row
  IDs or enhancement descriptor row IDs until exact enhancement subrows exist.
- Register runtime modifier bindings only for source-backed modifiers consumed
  by existing engine query points: unit characteristics, Hit rolls, save
  options, movement budgets, or Objective Control. Link each binding to a
  generated Phase 17F execution row ID, prove lifecycle bundle loading, and add
  at least one real consumer-path regression for every modified engine area.
- Return typed unsupported results with source-linked reasons for unsupported semantics.
- Add replay and audit assertions for state-changing behavior.
- Do not edit runtime loader, lifecycle, bundle, or manifest machinery in
  ordinary content PRs. A PR that explicitly introduces a shared runtime surface
  must update this contract, lifecycle/bundle tests, and integration-plan
  documentation in the same change.
```
