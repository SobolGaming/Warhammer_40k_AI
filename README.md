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

### Phase 0: governance and gates

Before gameplay code, add:

- `ruff` linting;
- strict type checking with `mypy` and/or `pyright`;
- `pytest` test framework;
- `coverage` reporting;
- `pre-commit` hooks;
- code-quality tests;
- import-boundary checks;
- broad-exception audit;
- fallback-code audit;
- raw-model-access audit for physical engine paths.

Exit criteria:

- `uv run ruff check .` passes;
- `uv run mypy src tests` passes once typed modules exist;
- `uv run pytest` passes;
- code-quality tests fail on broad exception or forbidden fallback patterns.

### Phase 1: dice and deterministic randomness

Modules:

- `core/rng.py`
- `core/dice.py`
- `engine/decision.py`
- `engine/event_log.py`

Objects:

- `RandomSource`
- `DiceExpression`
- `DiceRollSpec`
- `DiceRollResult`
- `DiceRollState`
- `DiceRollManager`

Invariants:

- same seed + same event/decision history produces same rolls;
- every dice roll has `reason` and `roll_type`;
- no generic `get_roll(D6)` replay-facing labels;
- rerolls are explicit decisions;
- fixed/replay-injected dice are supported;
- serialization round-trips exactly.

Required tests:

- same-seed determinism;
- branch history affects dice deterministically;
- reroll selection is explicit;
- replay-injected dice reproduce original results;
- unlabeled dice request is invalid.

### Phase 2: attributes and modifiers

Modules:

- `core/attributes.py`
- `core/modifiers.py`
- `rules/timing.py`

Objects:

- `Characteristic`
- `CharacteristicValue`
- `Modifier`
- `ModifierScope`
- `ModifierTiming`
- `ModifierStack`

Invariants:

- modifiers are typed, not raw string-parsed at runtime;
- modifier order is deterministic;
- raw/base/final values are inspectable;
- unsupported stacking interactions fail explicitly.

Initial supported characteristics:

- movement;
- toughness;
- save;
- invulnerable save;
- wounds;
- leadership;
- objective control;
- weapon skill;
- ballistic skill;
- strength;
- attacks;
- armor penetration;
- damage;
- range.

### Phase 3: rule text normalization boundary

Modules:

- `rules/text_normalization.py`
- `rules/parsed_tokens.py`
- `rules/source_data.py`

Raw source text enters here and is normalized once. Engine runtime code must not scatter `.lower()`, `.replace()`, unicode punctuation cleanup, or dice-expression parsing across rule handlers.

Normalize at least:

- smart quotes and apostrophes;
- en/em dashes;
- unicode minus signs;
- non-breaking spaces;
- multiplication signs;
- full-width punctuation where observed;
- keyword casing;
- dice expressions;
- range expressions.

### Phase 4: wargear and weapon profiles

Modules:

- `core/wargear.py`
- `core/weapon_profiles.py`

Objects:

- `Wargear`
- `WeaponProfile`
- `WeaponKeyword`
- `RangeProfile`
- `AttackProfile`
- `DamageProfile`

Invariants:

- weapon profile identity is stable;
- serialization never uses object reprs;
- profile expressions are parsed at ingest time;
- keywords are canonical tokens.

### Phase 5: model geometry

As soon as `Model` exists, geometry begins.

Modules:

- `geometry/pose.py`
- `geometry/base.py`
- `geometry/volume.py`
- `geometry/terrain.py`
- `geometry/spatial_index.py`

Objects:

- `Point3`
- `Pose`
- `Facing`
- `BaseShape`
- `CircularBase`
- `OvalBase`
- `ModelVolume`
- `TerrainVolume`
- `ObstacleVolume`
- `Model`

Model invariants:

- every battlefield model has a stable `model_id`;
- every battlefield model has a pose;
- every battlefield model has a base shape;
- every battlefield model has a 2.5D volume;
- no model without geometry can enter battlefield state.

Required tests:

- base overlap;
- base distance;
- 3D range;
- engagement range;
- terrain intersection;
- simple line-of-sight segment blocking.

### Phase 6: units and attached units

Modules:

- `core/unit.py`
- `core/attached_unit.py`
- `core/unit_group.py`

Objects:

- `Unit`
- `UnitMember`
- `AttachedUnit`
- `UnitGroup`

Terminology is explicit:

```text
unit.own_models            -> models physically owned by that unit object
unit_group.all_models()    -> all models in the attached rules unit
unit_group.alive_models()  -> alive models in the attached rules unit
```

Do not use ambiguous `unit.models` semantics.

Required tests:

- leader joins bodyguard;
- joined support included;
- attached unit moves as one rules unit;
- damage allocation sees the attached group;
- event logging includes attached group;
- line-of-sight and targeting see attached group;
- movement status applies to the whole attached group.

### Phase 7: 2.5D visibility and pathing core

Modules:

- `geometry/visibility.py`
- `geometry/pathing.py`
- `geometry/movement_envelope.py`
- `geometry/collision.py`

Objects:

- `VisibilityQuery`
- `VisibilityResult`
- `PathQuery`
- `PathResult`
- `PathWitness`
- `PathFailure`
- `CollisionSet`
- `MovementEnvelope`

Visibility design:

- static terrain index;
- dynamic model-blocker index;
- segment bounding-box query;
- deterministic candidate ordering;
- exact geometry only after broad phase;
- staged sampled rays;
- early exit on first legal clear line.

Pathing invariants:

- no endpoint-only movement validation;
- collision checked along path;
- terrain checked along path;
- engagement range checked along path;
- coherency checked after movement;
- attached-unit groups checked together;
- impossible path returns typed failure, not fallback movement.

### Phase 8: battlefield and objectives

Modules:

- `core/battlefield.py`
- `core/objectives.py`
- `core/deployment_zones.py`

Objects:

- `Battlefield`
- `TerrainLayout`
- `Objective`
- `DeploymentZone`
- `SpatialState`

Invariants:

- every battlefield model is indexed by stable ID;
- spatial index uses generation counters;
- objective control derives from current spatial state;
- no hidden mutation bypasses generation counters.

### Phase 8B: ruleset compatibility descriptors

Module:

- `core/ruleset_descriptor.py`

Objects:

- `RulesetDescriptor`
- `EngagementPolicyDescriptor`
- `MovementPolicyDescriptor`
- `MovementModePolicy`
- `ChargePolicyDescriptor`
- `ChargeEndpointRequirement`
- `TerrainVisibilityPolicyDescriptor`
- `ObjectivePolicyDescriptor`
- `CoherencyPolicyDescriptor`
- `FlyPolicyDescriptor`
- `MissionPolicyDescriptor`

Invariants:

- descriptor data does not execute rules;
- descriptor payloads include deterministic `ruleset_id` and `descriptor_hash`;
- movement, engagement, objective, coherency, terrain, FLY, charge, and mission assumptions are explicit data;
- charge endpoint requirements are typed descriptors, not coarse boolean fallbacks;
- unsupported preview rule paths remain explicit policy descriptors, not fallback behavior.

### Phase 8C: distance predicate tokens

Module:

- `rules/parsed_tokens.py`

Objects:

- `DistancePredicateKind`
- `DistancePredicateToken`

Invariants:

- rule text that states a distance predicate is parsed as a structured predicate, not a bare range;
- bare `RangeExpressionToken` remains for profile-like distances such as weapon range text;
- predicate spans are tied to `normalized_text` and payload round-trips;
- unsupported distance interval semantics fail explicitly.

Initial supported predicates:

- within N inches;
- more than N inches;
- at least N inches;
- at most N inches;
- exactly N inches;
- within Engagement Range;
- outside Detection Range;
- Half Range.

### Phase 8D: weapon ability descriptors

Module:

- `core/weapon_profiles.py`

Objects:

- `AbilityDescriptor`
- `AbilityKind`
- `AbilityParameter`
- `AbilityTiming`
- `AbilityCondition`

Invariants:

- weapon abilities are typed ingest-time descriptors, not executable rule handlers;
- ability payloads are JSON-safe and never use object reprs;
- parameterized abilities validate their parameters before weapon profiles can use them;
- unsupported ability shapes fail explicitly.

Initial supported descriptors:

- Sustained Hits X;
- Melta X;
- Rapid Fire X;
- Heavy with stationary-or-policy-defined condition.

### Phase 9: decision system

Modules:

- `engine/decision_request.py`
- `engine/decision_result.py`
- `engine/decision_queue.py`
- `engine/decision_controller.py`
- `engine/decision_record.py`

Objects:

- `DecisionOption`
- `DecisionRequest`
- `DecisionResult`
- `DecisionQueue`
- `DecisionController`
- `DecisionRecord`

Invariants:

- every player choice emits a `DecisionRequest`;
- every response is a `DecisionResult`;
- action spaces are finite and serializable;
- UI/headless/network choose decisions differently but use the same engine path;
- engine validates every result;
- engine alone mutates authoritative state.

### Phase 9A: catalog, content provenance, and sequence descriptors

This phase exists after the completed Phase 1-9 foundation. It adds the source
catalog, datasheet/faction catalog definitions, canonical content fixtures, and
setup/battle sequence descriptors needed before lifecycle and mustering are
implemented.

Modules:

- `rules/source_catalog.py`
- `rules/data_package.py`
- `rules/source_data.py`
- `core/datasheet.py`
- `core/army_catalog.py`
- `core/faction.py`
- `core/detachment.py`
- `core/ruleset_descriptor.py`

Objects:

- `DataPackageId`
- `SourceDocumentId`
- `RuleSourceText`
- `RulesetBundle`
- `CatalogVersion`
- `DatasheetDefinition`
- `ModelProfileDefinition`
- `UnitCompositionDefinition`
- `DatasheetKeywordSet`
- `DatasheetWargearOption`
- `DatasheetAbilityDescriptor`
- `FactionDefinition`
- `DetachmentDefinition`
- `ArmyRuleDefinition`
- `EnhancementDefinition`
- `StratagemDefinition`
- `SetupSequenceDescriptor`
- `BattlePhaseSequenceDescriptor`

Catalog definitions may include real source facts as soon as the schema exists:

- movement, toughness, save, wounds, leadership, objective control;
- weapon skill and ballistic skill;
- base size and model profile composition;
- keywords and faction keywords;
- default wargear and legal wargear options;
- source-linked ability text and inert ability descriptors.

Invariants:

- all source data has deterministic source IDs;
- source package identity is explicit;
- raw rule text is normalized once at the data boundary;
- no runtime rule handler consumes unnormalized text;
- unsupported source shapes fail during ingest;
- datasheet facts are immutable catalog definitions;
- catalog definitions do not mutate battlefield state;
- runtime unit instances are not source data;
- ability descriptors are not executable handlers;
- unsupported abilities remain explicit unsupported descriptors;
- faction and detachment selection is data, not behavior;
- setup and battle phase order are explicit policy data, not driver-local enum arithmetic;
- setup and battle phase sequence descriptors are carried by `RulesetDescriptor` and included in
  descriptor hashing.

Add a tiny canonical content pack before broad content import. It should include
infantry, a character leader, a transport, a vehicle or monster, and a deep-strike
unit so engine contract tests use real fixtures instead of ad hoc objects.

### Phase 9B: authoritative game lifecycle

Modules:

- `engine/lifecycle.py`
- `engine/game_state.py`
- `engine/setup_flow.py`
- `engine/battle_round_flow.py`
- `engine/phase.py`
- `engine/phases/command.py`

Objects:

- `GameLifecycle`
- `GameState`
- `GameLifecycleStage`
- `SetupStep`
- `BattlePhase`
- `LifecycleStatus`
- `PhaseHandler`

Top-level setup order is explicit:

```text
MUSTER_ARMIES
SELECT_MISSION
CREATE_BATTLEFIELD
DETERMINE_ATTACKER_DEFENDER
SELECT_SECONDARY_MISSIONS
DECLARE_BATTLE_FORMATIONS
DEPLOY_ARMIES
REDEPLOY_UNITS
DETERMINE_FIRST_TURN
RESOLVE_PREBATTLE_ACTIONS
```

`SELECT_SECONDARY_MISSIONS` covers each player's secret Fixed or Tactical
Secondary Mission choice. Fixed choices also include selecting the two Fixed
Missions; Tactical choices are deferred to Command phase draws.

Battle round order is explicit:

```text
COMMAND
MOVEMENT
SHOOTING
CHARGE
FIGHT
```

`GameLifecycle` owns the single authoritative clock:

```text
start(config)
advance_until_decision_or_terminal()
submit_decision(result)
```

Invariants:

- one engine-owned setup-to-battle state machine;
- setup sequence comes from `RulesetDescriptor.setup_sequence`, not duplicated driver code;
- battle phase order comes from `RulesetDescriptor.battle_phase_sequence`;
- `RulesetDescriptor.descriptor_hash` is recorded in lifecycle state and replay-facing payloads;
- `advance_until_decision_or_terminal()` advances deterministic lifecycle transitions until a
  decision, terminal status, unsupported status, or deterministic transition guard is reached;
- phase wrap switches the active player;
- battle round increments only after every player has completed the fight phase;
- lifecycle advances only through engine commands and decision results;
- UI, headless, replay, and network do not own phase progression;
- phase handlers are explicit for every phase in the configured battle sequence;
- Phase 9B placeholder phase bodies emit explicit no-op events and typed unsupported statuses;
- all lifecycle state is deterministic and serializable.

Required tests:

- new game starts at `MUSTER_ARMIES`;
- setup steps advance in order;
- lifecycle reads setup order from `RulesetDescriptor.setup_sequence`, not local constants;
- lifecycle reads battle phase order from `RulesetDescriptor.battle_phase_sequence`, not local constants;
- one call to `advance_until_decision_or_terminal()` reaches the first setup decision from a new
  game;
- setup completion enters battle round 1 command phase;
- battle phases advance command, movement, shooting, charge, fight;
- phase wrap switches the active player;
- battle round increments after all players complete fight phase;
- lifecycle stops at a `DecisionRequest`;
- missing battle phase handlers are not silently skipped;
- malformed setup sequences missing `SELECT_SECONDARY_MISSIONS` fail at config construction;
- battle phase sequences that do not start with `COMMAND` fail at config construction;
- `SELECT_SECONDARY_MISSIONS` emits secret decision requests for both players;
- Fixed and Tactical secondary choices serialize without leaking hidden opponent choices;
- Tactical secondary draws occur in Command phase, not setup;
- descriptor hash is recorded in lifecycle state and replay-facing payloads;
- lifecycle payload hash, sequence, and config-derived state mismatches fail during
  `from_payload()`;
- no UI or headless-specific phase path exists.

### Phase 9C: army mustering and runtime instantiation

Modules:

- `engine/army_mustering.py`
- `engine/unit_factory.py`
- `engine/list_validation.py`

Objects:

- `ArmyMusterRequest`
- `ArmyDefinition`
- `UnitInstance`
- `ModelInstance`
- `WargearSelection`
- `DetachmentSelection`

Invariants:

- mustering consumes catalog definitions and produces runtime instances;
- lifecycle `MUSTER_ARMIES` consumes per-player `ArmyMusterRequest` data;
- runtime units keep stable links back to datasheet and source IDs;
- all selected wargear is legal for the datasheet;
- all model profiles and base sizes are resolved before battlefield placement;
- faction, detachment, enhancement, and stratagem selections are validated as data;
- invalid or unsupported list content fails explicitly.

Required tests:

- canonical army mustering produces deterministic `ArmyDefinition` payloads;
- lifecycle `MUSTER_ARMIES` consumes requests for every player and stores runtime armies;
- invalid mustering prevents setup advancement past `MUSTER_ARMIES`;
- lifecycle replay payloads preserve mustered army definitions;
- runtime `UnitInstance` and `ModelInstance` objects preserve datasheet/source links;
- runtime payloads reject army/unit/model hierarchy drift;
- runtime units use explicit `own_models`, not ambiguous `models`;
- selected wargear outside a datasheet option fails during mustering;
- model counts outside datasheet composition bounds fail during mustering;
- faction, detachment, enhancement, and stratagem selection drift fails during mustering;
- request/catalog identity drift fails during mustering;
- mustering payloads round-trip without Python object reprs.

### Phase 9D: pre-Phase-10 smoke gate

This is a hardening gate, not a broad content phase. It proves that the
catalog, mustering, authoritative lifecycle, decision path, and replay payloads
work together end-to-end before the movement phase body starts consuming
runtime units.

Use the existing canonical content pack or a tiny Phase 10 smoke pack. Do not
import broad official datasheets, detachments, stratagems, enhancements, or
codex abilities in this phase.

Required smoke path:

```text
GameLifecycle.start(config)
advance_until_decision_or_terminal()
  -> MUSTER_ARMIES runs
  -> ArmyDefinition exists for every player
  -> SELECT_SECONDARY_MISSIONS decision appears
submit secondary mission choices
advance through setup
enter Battle Round 1 COMMAND phase
draw Tactical secondary missions when required
stop at explicit Phase 9B placeholder or unsupported phase body
replay payload round-trips
```

Invariants:

- lifecycle smoke tests use real catalog definitions and real mustering, not stubs;
- mustered armies exist before secondary mission decisions are requested;
- runtime units preserve datasheet IDs, source IDs, own models, base sizes, wounds,
  characteristics, and resolved wargear selections;
- Tactical secondary draws occur in Command phase, not setup;
- public payloads do not leak hidden opponent secondary choices;
- replay-facing payloads contain no Python object reprs;
- placeholder movement, shooting, charge, and fight bodies remain explicit boundaries
  until their vertical slices are implemented.

Required tests:

- minimal two-player catalog-backed lifecycle reaches `SELECT_SECONDARY_MISSIONS`
  with both armies mustered;
- the same lifecycle reaches Battle Round 1 `COMMAND`;
- Tactical secondary selection emits a Command-phase draw decision;
- after the draw, lifecycle stops at an explicit Phase 9B placeholder or unsupported
  phase body;
- replay payload round-trips after the smoke path;
- public state hides opponent Fixed secondary choices.

### Phase 10: movement phase body vertical slice

This phase fills the movement phase body behind the Phase 9B lifecycle. It does
not own turn or phase progression.

Implement:

- select unit;
- select movement action;
- advance roll;
- reroll decision;
- move models;
- path witness;
- datasheet Movement and keyword consumption;
- movement ability descriptors for supported timing windows;
- unit status update;
- objective update;
- event log;
- decision record;
- replay.

Acceptance sequence:

```text
SELECT_UNIT
SELECT_MOVEMENT_ACTION
REQUEST_DICE_ROLL if Advance
SELECT_DICE_REROLL if applicable
MOVE_UNIT
```

No next `SELECT_UNIT` may be queued before the movement activation terminal event.

### Phase 11: shooting phase body vertical slice

This phase fills the shooting phase body behind the Phase 9B lifecycle. It
consumes datasheet ballistic skill, weapon profiles, ranged keywords, and
shooting ability descriptors only through structured catalog data.

Implement:

- select shooting unit;
- target selection;
- line of sight;
- range;
- declare weapons;
- hit/wound/save/damage;
- damage allocation;
- model destruction;
- event log;
- replay.

### Phase 12: charge and fight phase body vertical slice

This phase fills the charge and fight phase bodies behind the Phase 9B lifecycle.
It consumes melee profiles, weapon skill, charge policy descriptors, and
charge/fight ability descriptors only through structured catalog data.

Implement:

- declare charge;
- charge roll;
- charge movement with `PathWitness`;
- Heroic Intervention interrupt;
- pile-in;
- fight target selection;
- melee declaration;
- attack resolution;
- consolidate.

Interrupts use typed decision metadata:

```text
dispatch_mode = "interrupt"
interrupt_window = "after_enemy_charge_move"
blocking_parent = true
resume_parent_after_resolution = true
```

### Phase 13: richer deployment, reserves, transports, and pre-battle abilities

The lifecycle slots for deployment, redeploy, pre-battle actions, and battle
round entry exist in Phase 9B. This phase fills the advanced behavior in those
slots after movement/pathing and unit instantiation exist.

- deployment;
- Scout;
- Infiltrate;
- reserves;
- deep strike;
- embark;
- disembark;
- destroyed transport disembark;
- transport capacity restrictions;
- leader attachment constraints;
- reserve restriction validation.

### Phase 14: broad content import and ability handler expansion

Bring in wider faction, detachment, codex, and core-rules content only after the
owning schema, lifecycle slot, and phase pipeline exist.

Invariants:

- load real facts as soon as the schema exists;
- instantiate real units only through mustering;
- execute rules only in the owning phase or timing-window handler;
- source text remains linked to structured descriptors;
- unsupported ability shapes remain explicit unsupported descriptors;
- no raw codex text is parsed by runtime engine code.

Handler examples:

- movement handlers for Advance, Fall Back, FLY, and movement modifiers;
- shooting handlers for Sustained Hits, Melta, Rapid Fire, Heavy, Blast, Torrent,
  Lethal Hits, Devastating Wounds, and Pistol;
- charge and fight handlers for charge bonuses, Fight First, fight-on-death,
  pile-in, consolidate, and melee weapon abilities;
- deployment and pre-battle handlers for Deep Strike, Infiltrators, Scouts,
  reserves, transports, and redeploy effects.

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
