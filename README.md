# warhammer40k-core-v2

Strict bottom-up Warhammer 40k engine reconstruction.

Start here:

```bash
uv python install 3.14.5
uv lock
uv sync
uv run pytest
```

# CORE V2 Architecture

## 1. Purpose

CORE V2 is a clean bottom-up reconstruction of the Warhammer 40,000 engine using selected concepts and vetted code from the legacy repository, but not inheriting its permissive fallback behavior, stub-heavy testing style, or divergent UI/headless/network execution paths.

The legacy repository remains valuable as:

- a reference implementation;
- a replay and audit corpus;
- a source of known bugs and invariants;
- a source of selected algorithms that may be ported only after review;
- a comparison harness for deterministic replay and behavior.

CORE V2 is not a blank rewrite. It is a strict reconstruction with enforced invariants.

## 2. Non-negotiable invariants

These rules are enforced from the first commit.

1. Engine core is fail-fast.
2. No broad exception handling: no bare `except`, no `except Exception`, no `except BaseException` in engine/core/rules/geometry without an explicit allowlist entry.
3. No silent fallback behavior. Unsupported rule paths must return typed invalid/unsupported results or raise explicit domain errors.
4. No player choice outside `DecisionRequest` / `DecisionResult`.
5. UI, headless, network, replay, and test drivers all use the same decision and command path.
6. Engine alone mutates authoritative game state.
7. Movement, charge, pile-in, consolidate, disembark, reserves, and reactive movement require `PathWitness` or an explicit typed invalid result.
8. Endpoint-only movement validation is invalid unless the rule explicitly models teleport/set-up placement.
9. Raw rule text is normalized once at the data boundary; runtime engine code consumes structured descriptors.
10. Physical battlefield operations must operate on explicit model groups, not ambiguous `unit.models` semantics.
11. Attached units are first-class rules units, not an afterthought.
12. All entity IDs, action IDs, event IDs, and replay payloads are deterministic and serializable.
13. Decision records must never contain Python object reprs or memory addresses.
14. Tests for movement, shooting, charge, fight, transport, attached unit, replay, UI, and network behavior use real domain objects or canonical fixtures, not partial `SimpleNamespace` stand-ins.
15. Stubs are allowed only for pure functions and must be marked `stubbed`.

## 3. Repository layout

```text
warhammer40k_core/
  core/
    ids.py
    rng.py
    dice.py
    attributes.py
    modifiers.py
    wargear.py
    weapon_profiles.py
    model.py
    unit.py
    attached_unit.py
    unit_group.py
    battlefield.py
    objectives.py
    deployment_zones.py
    datasheet.py
    army_catalog.py
    faction.py
    detachment.py
    ruleset_descriptor.py
  geometry/
    pose.py
    base.py
    volume.py
    spatial_index.py
    visibility.py
    pathing.py
  rules/
    text_normalization.py
    parsed_tokens.py
    source_data.py
    source_catalog.py
    data_package.py
    descriptors.py
    timing.py
    effects.py
    registry.py
  engine/
    decision_request.py
    decision_result.py
    decision_queue.py
    decision_controller.py
    decision_record.py
    event_log.py
    replay.py
    validation.py
    lifecycle.py
    game_state.py
    setup_flow.py
    battle_round_flow.py
    phase.py
    army_mustering.py
    unit_factory.py
    list_validation.py
    battlefield_state.py
    placement.py
    phases/
      command.py
      movement.py
      shooting.py
      charge.py
      fight.py
  adapters/
    headless.py
    ui.py
    network.py
  tests/
    fixtures/
    unit/
    integration/
    replay/
    code_quality/
```

Dependency direction:

```text
core     -> no project-layer imports
geometry -> may import core, not engine/adapters
rules    -> may import core and descriptors, not adapters
engine   -> may import core, geometry, rules
adapters -> may import engine, never the reverse
```

## 4. Build order

The CORE V2 build order roadmap now lives in [ARCHITECTURE_V2.md](ARCHITECTURE_V2.md).

Current roadmap implementation status: phases 1-14G are complete. Phase 14E is complete: its allocation-group host includes Benefit of Cover and Plunging Fire BS modifiers, ordered InSv-then-armour Save resolution with no save-kind adapter choice, automatic allocation groups, defender ordered allocation decisions only for legal same-tier group choices, grouped fixed-damage save-before-damage resolution, current group transitions, low-to-high failed-save damage ordering, normal-damage-before-routed-mortal ordering, grouped-host Precision/Lethal Hits/Sustained Hits/Devastating Wounds revalidation, derived terrain objectives that require terrain-area containment rather than marker-radius contribution, melee Cleave dice gathering, and Lance charge-gated Wound-roll modifiers through the Phase 15 Charge/Fight host. Phase 14F completes the shooting-type cutover with finite shooting-type selection, supported grouped attack resolution, Normal/Assault/Close-quarters/Indirect/Snap routing, Indirect and Snap Hit-roll reroll bans, and the Shooting-phase Mission Action start lock. Phase 14G completes the Charge/Fight source contract as typed ruleset descriptor payloads and deferred unsupported Core Stratagem hooks. Phase 14H remains deferred for runtime attached-unit formation; attached-unit mixed-Toughness attack handling now uses source-backed Bodyguard/Leader/Support role evidence, Healing Wounds iterates wound healing before REVIVED model return with opposing-player model selection for ambiguous attached-unit cases, Movement-phase Combat Disembark fallback now requires engine-owned Tactical-invalid evidence, Combat/Emergency hazard rolls share the official 1-2 Hazard Roll threshold, direct transport hazard damage routes through the shared mortal-wound and Feel No Pain service, destroyed-Transport Emergency Disembark is orchestrated from actual destruction timing before Transport removal and Deadly Demise, setup-time Strategic Reserve declarations and battle-formation Transport embarkation are source-backed, repositioned units preserve Advance/Fall Back/Disembark history and persisting effects, exact At Half-strength is replay payload state, and runtime added units record Starting Strength when added to the army. Phase 14I is complete for the current Core Stratagem and core ability source cutover: all 11th Edition Core Stratagem source rows have supported handlers, implemented duplicate weapon ability selection is adapter-visible and replay-safe, and unimplemented Core ability families are fail-closed as explicit unsupported descriptors. Phase 14J completes the current mission/catalog replacement slice with source-tracked 11th Edition Force Dispositions, the 25-cell Primary Mission matrix, three layout identifiers per matrix cell, and engine-achievement-gated finite Tactical Secondary score/retain decisions; exact 11th Edition Secondary card identities beyond current source rows, Primary Mission scoring text, and layout geometry remain pending source work. Phase 14K is complete: attack/save cutover hardening rejects retired save/allocation decision surfaces, grouped Inflict Damage uses defender `select_damage_allocation_model` decisions with pre-pop stale-legality rejection, old Aircraft minimum-move/pivot runtime policy is removed, reserve arrivals use Move Units records and more-than-8" enemy spacing, and source/audit coverage rejects retired Core Stratagem names.

Phase 14L and Phase 15A-F are complete for ranged attack grouping, charge declaration/roll/movement, Fight phase activation/pass/interrupt ordering, Pile In/Consolidate proposal routing, melee declarations that reuse the shared Making Attacks sequence, source-backed Heroic Intervention, Counteroffensive, Crushing Impact, and Epic Challenge Stratagem handling, and Charge/Fight completion gates that drain pending phase work before completion.

Adapter, UI, CLI, headless, network, AI, replay, and test-driver teams should use [docs/ADAPTER_DECISION_CONTRACT.md](docs/ADAPTER_DECISION_CONTRACT.md) for the shared Phase 11D decision/proposal submission contract plus Phase 11E viewer-scoped scoring projection/event rules.

## 5. Test policy

### Pure tests

May use stubs only for pure functions. Must be marked `stubbed`.

### Engine contract tests

Use canonical real fixtures. Required for:

- movement;
- shooting;
- charge;
- fight;
- deployment;
- transports;
- attached units;
- damage allocation;
- replay;
- decision dispatch;
- network serialization.

### Replay tests

Use real games and real replay logs.

Every replay bug must add:

- a narrow regression test;
- a bug-class or invariant test;
- a replay/audit fixture if reproducible.

## 6. Static code-quality gates

Add scripts/tests for:

- no broad exceptions;
- no unparenthesized multi-exception handlers;
- no silent fallback code;
- no forbidden raw model access in physical engine paths;
- no non-serializable decision payloads;
- no Python memory-address reprs in records;
- no generic dice labels;
- no UI mutation of engine state;
- strict import boundaries.

## 7. Legacy migration rule

No legacy file is copied wholesale.

Allowed migration path:

1. Name the invariant.
2. Write strict tests in CORE V2.
3. Port the smallest necessary algorithm or data transform.
4. Remove fallback behavior.
5. Add serialization/replay coverage.
6. Add static audit if the bug class is likely to recur.

## 8. First implementation milestone

Milestone A is complete only when these commands pass:

```bash
uv run ruff check .
uv run mypy src tests
uv run pyright
uv run pytest
uv run lint-imports
uv run pre-commit run --all-files
```

and these invariants are enforced by tests:

- broad exceptions fail the gate;
- raw model access in physical modules fails the gate;
- dice rolls require labels;
- dice replay round-trips;
- event/decision serialization contains no memory-address reprs.
