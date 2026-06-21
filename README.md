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
  interfaces/
    cli.py
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

The detailed phase roadmap belongs in [ARCHITECTURE_V2.md](ARCHITECTURE_V2.md).
This README keeps only the build sequence and the current high-level status.

Build in this order:

1. Governance, quality gates, deterministic RNG, dice, attributes, modifiers,
   and source-text normalization.
2. Wargear, weapon profiles, model geometry, units, attached units, battlefield
   geometry, visibility, pathing, objectives, and mission setup.
3. Decision requests/results, event records, replay, lifecycle routing, and the
   shared adapter contract.
4. Movement, shooting, charge, fight, deployment, reserves, transports,
   reactive movement, and grouped attack/damage resolution.
5. Source packages, catalog generation, rule IR, generic rule execution,
   faction coverage, and faction-specific runtime handlers.
6. Adapters and interfaces: headless, CLI, UI, network, event streams,
   viewer-safe projection, and trigger opportunity windows.
7. AI, rankers, training, and performance work only after the deterministic
   rules core and replay records are trustworthy.

Current status:

- Core rules infrastructure through movement, shooting, charge, fight, setup,
  reserves, transports, missions, replay, source ingestion, catalog generation,
  rule IR, generic rule execution, and adapter decision submission is in place.
- Faction semantic execution is active incremental work. Current runtime
  support includes selected Chaos Daemons, Chaos Space Marines, Aeldari,
  Death Guard, and World Eaters Phase 17G slices. Chaos Space Marines Dark
  Pacts uses shared selected-to-shoot and selected-to-fight grant decisions,
  out-of-phase selected-to-shoot grant routing, attack-sequence weapon keyword
  modifiers, and post-attack Leadership-test D3 mortal-wound routing including
  Feel No Pain continuation decisions. Aeldari Path of the Outcast supports
  Far-reaching Doom,
  Camouflaged Snipers, Assassins' Eye, Eldritch Suppression, Casting Back the
  Veil, and Nomads of the Hidden Way through the shared Shooting, Stratagem,
  Battle-shock, Hidden/detection, and triggered-movement paths. Aeldari
  Corsair Coterie supports Veterans of the Void, Relentless Raiders, Void
  Thieves, Infamy, Webway Pathstone, Archraider, Voidstone, and all six named
  Stratagems through shared mustering, objective-control, movement/charge-
  completion, reserves, setup, turn-end, Stratagem-cost, attack-reroll,
  triggered-movement, targeting-restriction, and runtime-modifier paths; broad
  datasheet, wargear, weapon, and remaining faction execution remains later
  Phase 17 work.
- Matched-play mustering supports Incursion, Strike Force, and Onslaught battle
  sizes, including the Drukhari `Corsairs and Travelling Players` ally rule for
  HARLEQUINS and ANHRATHE units.
- Drukhari `Power from Pain` runtime support includes a deterministic Pain token
  ledger, token gain at the owning Command phase start, enemy Battle-shock
  failures, and enemy unit destruction, plus Lithe Agility empowerment for
  Advance and Charge rerolls and Hatred Eternal selected-to-shoot and
  selected-to-fight hit-reroll empowerment through shared grant and dice-reroll
  decision paths.
- Local CLI/human decision entry, viewer-safe catalog/live unit-model projection,
  and trigger opportunity-window intent support are documented in
  [docs/ADAPTER_DECISION_CONTRACT.md](docs/ADAPTER_DECISION_CONTRACT.md) and
  [docs/TRIGGER_OPPORTUNITY_WINDOWS.md](docs/TRIGGER_OPPORTUNITY_WINDOWS.md).
- Official source evidence lives in `docs/source_rules`,
  `data/source_manifests`, `data/raw/faction_packs`, and generated source
  package artifacts. Runtime engine code must consume structured descriptors,
  not raw PDFs, CSV rows, HTML, or prose parsing.
- README milestone anchors retained for code-quality audits: Phase 14H is complete;
  Phase 14I is complete; Phase 14K is complete; Phase 17A.1 is complete.
  Phase 14H anchors: runtime Attached Unit formation; structured army-list Leader/Support declarations; first-class attached rules-unit formation records; healing, revival, persisting effects; Movement-phase Combat Disembark fallback with engine-owned evidence; setup-time Strategic Reserve declarations; repositioned-unit Advance/Fall Back/Disembark history.
  Source-linked model geometry still requires a representative model height with provenance
  before runtime catalog use.

When a phase status changes, update the focused status document or contract
for that subsystem instead of turning this README into a changelog.

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
