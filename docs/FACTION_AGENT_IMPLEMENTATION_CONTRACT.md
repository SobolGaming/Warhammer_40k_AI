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
- Battle-shock hook bindings for rules whose trigger is Battle-shock modifier
  or outcome resolution;
- Fall Back eligibility hook bindings for rules whose effect is that a Fall Back
  move does not prevent later Shooting or Charge eligibility;
- enhancement effect bindings for Enhancement or Upgrade effects that are
  selected from Phase 16D army-construction records and materialize static
  engine-owned characteristic modifiers;
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

Fall Back eligibility hook bindings are an approved runtime contribution surface
only for source-backed rules that modify the consequences of a completed Fall
Back move. Each hook binding must use a `source_id` from the generated Phase 17F
execution rows for the implemented rule. Hook handlers must return typed
permission grants; the Movement engine records the authoritative
`FellBackUnitState`, emits deterministic replay-safe grant payloads, and the
Shooting and Charge phases consume that engine-owned state. Faction modules must
not mutate Fall Back, Shooting, or Charge phase state directly.

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
- Register Battle-shock hook bindings only for Battle-shock timing semantics,
  and link them to generated Phase 17F execution row IDs.
- Register Fall Back eligibility hook bindings only for source-backed rules
  that change Fall Back Shooting or Charge permissions, and link them to
  generated Phase 17F execution row IDs.
- Register enhancement effect bindings only for source-backed Enhancement or
  Upgrade effects selected through Phase 16D army-construction records, and link
  them to generated Phase 17F enhancement descriptor row IDs until exact
  enhancement subrows exist.
- Return typed unsupported results with source-linked reasons for unsupported semantics.
- Add replay and audit assertions for state-changing behavior.
- Do not edit runtime loader, lifecycle, bundle, or manifest machinery in
  ordinary content PRs. A PR that explicitly introduces a shared runtime surface
  must update this contract, lifecycle/bundle tests, and integration-plan
  documentation in the same change.
```
