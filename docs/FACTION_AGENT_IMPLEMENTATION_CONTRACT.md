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
- RuleIR runtime bindings;
- faction named handlers.

Semantic execution must run through registered engine paths. Leave unimplemented
rule shapes as explicit unsupported diagnostics, not no-ops, defaults, or silent
fallbacks.

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
- Return typed unsupported results with source-linked reasons for unsupported semantics.
- Add replay and audit assertions for state-changing behavior.
- Do not edit runtime loader, lifecycle, bundle, or manifest machinery.
```
