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
stop at the next explicit phase boundary
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
- movement, shooting, charge, and fight bodies remain explicit boundaries until
  their vertical slices are implemented; once a vertical slice lands, the smoke
  path stops at that slice's first decision or unsupported boundary.

Required tests:

- minimal two-player catalog-backed lifecycle reaches `SELECT_SECONDARY_MISSIONS`
  with both armies mustered;
- the same lifecycle reaches Battle Round 1 `COMMAND`;
- Tactical secondary selection emits a Command-phase draw decision;
- after the draw, lifecycle stops at either an explicit Phase 9B placeholder, a
  vertical-slice decision, or a typed unsupported boundary;
- replay payload round-trips after the smoke path;
- public state hides opponent Fixed secondary choices.

### Phase 10A: battlefield placement bridge

This phase is a minimal runtime bridge for movement vertical-slice tests. Phase
9C creates mustered runtime `UnitInstance` and `ModelInstance` objects, but
movement needs placed models. Phase 10A records deterministic model poses for
those runtime instances without implementing full deployment rules.

Modules:

- `engine/battlefield_state.py`
- `engine/placement.py`

Objects:

- `ModelPlacement`
- `UnitPlacement`
- `BattlefieldRuntimeState`
- `PlacedArmy`
- `BattlefieldScenario`

Invariants:

- every placed model references an existing `ModelInstance`;
- every placed unit references an existing `UnitInstance`;
- no model is placed twice;
- no placed model belongs to the wrong army or player;
- base size remains available from the referenced `ModelInstance`;
- pose payloads are deterministic and serializable;
- placement state round-trips without Python object reprs;
- placement fixtures use mustered armies from `GameState`, not ad hoc models;
- this phase does not implement full `DEPLOY_ARMIES` rules.

Required tests:

- lifecycle smoke config reaches `SELECT_SECONDARY_MISSIONS` with both armies
  mustered;
- deterministic placement state is created from both `ArmyDefinition` objects;
- every placed model maps back to a runtime `ModelInstance`;
- referenced model base sizes and characteristics remain available;
- duplicate model placements fail explicitly;
- missing unit/model placement references fail explicitly;
- wrong-player placement drift fails explicitly;
- placement and scenario payloads round-trip without Python object reprs.

### Movement taxonomy boundary

Movement work must keep these domains separate:

Movement phase action:
  A player choice made in the Move Units step: Remain Stationary, Normal Move,
  Advance, or Fall Back.

Model displacement:
  A model pose change on the battlefield. Displacement can happen during the
  Movement phase, Charge phase, Fight phase, or as a triggered rule effect.

Battlefield placement:
  A model or unit appearing on the battlefield from deployment, redeploy,
  strategic reserves, deep strike, disembark, split-unit, or
  return-to-battlefield effects.

Battlefield removal:
  A model or unit leaving the battlefield because it was destroyed, embarked,
  placed into reserves, or temporarily removed.

Movement capability / legality input:
  Structured rule data used to evaluate a displacement. Keywords such as `FLY`,
  `INFANTRY`, `BEAST`, `VEHICLE`, and `MONSTER` modify capabilities and
  constraints; they are not Movement phase action options.

`REINFORCEMENTS` is a Movement phase step, not a placement kind. During that
step, specific placement mechanisms such as strategic reserves and deep strike
place models onto the battlefield.

`REDEPLOY` is a battlefield placement kind, not a model displacement kind. A
redeploy transition may remove a model temporarily and then place it again, but
it is not represented as a path-witnessed pose change.

### Phase 10B: movement phase entry and unit selection

This phase replaces the Phase 9B Movement placeholder with a real
`MovementPhaseHandler`, but keeps the first movement vertical slice narrow. It
does not move models yet.

Modules:

- `engine/phases/movement.py`
- `engine/lifecycle.py`
- `engine/battle_round_flow.py`
- `engine/game_state.py`
- `engine/setup_flow.py`

Objects:

- `MovementPhaseHandler`
- `MovementPhaseState`
- `MovementUnitSelection`

Implement:

- register `MovementPhaseHandler` in `GameLifecycle`;
- persist Phase 10A battlefield placement state in lifecycle `GameState`;
- create the deterministic Phase 10A placement bridge at `DEPLOY_ARMIES`
  until full deployment rules exist;
- emit `SELECT_MOVEMENT_UNIT`;
- derive the legal unit set from the active player's mustered and placed units;
- allow each unit to be selected once per Movement phase;
- put the selected unit into a movement activation state;
- stop at the unit-selection `DecisionRequest`;
- record movement phase entry and unit selection in event/replay payloads.

Invariants:

- Movement phase progression remains owned by the engine lifecycle;
- player choice uses `DecisionRequest` / `DecisionResult`;
- legal movement units come from placed runtime units, not ad hoc fixtures;
- movement requires complete placement for mustered models before unit selection;
- replay payloads reject `battlefield_state` before `DEPLOY_ARMIES` completes;
- selected units are scoped to the active player;
- a unit cannot be selected twice in the same Movement phase;
- no displacement, movement action, path witness, or objective update is implemented yet.

Required tests:

- lifecycle enters Movement with a real `MovementPhaseHandler`;
- Movement emits `SELECT_MOVEMENT_UNIT` for the active player;
- decision options contain only the active player's placed units;
- selecting a unit records deterministic activation state and event/replay payloads;
- already-selected units are excluded from the legal unit set;
- incomplete placement fails explicitly before unit selection;
- no next movement action is resolved before unit selection is recorded.

### Phase 10C: movement phase action and normal move

This phase adds the first actual Movement phase action after unit selection.
`SELECT_MOVEMENT_ACTION` exposes only the standard Move Units actions:
`REMAIN_STATIONARY`, `NORMAL_MOVE`, `ADVANCE`, and `FALL_BACK`.

Modules:

- `engine/phases/movement.py`
- `engine/battlefield_state.py`
- `geometry/pathing.py`

Implement:

- emit `SELECT_MOVEMENT_ACTION`;
- support `REMAIN_STATIONARY`;
- support `NORMAL_MOVE`;
- return typed unsupported results for `ADVANCE` and `FALL_BACK`;
- consume the selected unit's datasheet Movement characteristic;
- consume base size and current pose from placed `ModelInstance` data;
- produce a `PathWitness` or typed movement witness for each moved model;
- update model placements;
- mark the selected unit as moved;
- emit a movement activation terminal event;
- queue/select the next unit only after the current activation terminal event.

Not Movement phase action options:

- `FLY`;
- embark/disembark;
- terrain traversal beyond existing explicit descriptors;
- enemy engagement constraints beyond existing explicit descriptors.

Serialized payloads use `movement_phase_action`, not generic `action`. Payloads
that actually change poses also include `displacement_kind`, such as
`normal_move`.

Required tests:

- `SELECT_MOVEMENT_ACTION` exposes exactly `remain_stationary`, `normal_move`,
  `advance`, and `fall_back`;
- `FLY`, embark, disembark, terrain traversal, and engagement-constrained moves
  are absent from Movement phase action options;
- `REINFORCEMENTS` is modeled as a Movement phase step, not a placement kind;
- `REDEPLOY` is modeled as a battlefield placement kind, not a model
  displacement kind;
- `REMAIN_STATIONARY` marks the unit complete without changing poses;
- `NORMAL_MOVE` consumes Movement, base size, and current pose;
- movement updates placement payloads deterministically;
- normal movement emits a witness and movement activation terminal event;
- the selected unit cannot be selected again that phase;
- the next `SELECT_MOVEMENT_UNIT` is not emitted before the terminal event;
- `ADVANCE` and `FALL_BACK` return typed unsupported results.

### Phase 10D: battlefield transition records

This phase makes model placement, removal, and displacement replay-facing
records. It does not implement new rules behavior.

Modules:

- `engine/battlefield_state.py`
- `engine/setup_flow.py`
- `engine/phases/movement.py`

Objects:

- `ModelPlacementRecord`
- `ModelRemovalRecord`
- `ModelDisplacementRecord`
- `BattlefieldTransitionBatch`

Invariants:

- placement records describe models appearing on the battlefield without a
  path-witnessed move;
- removal records describe models leaving the battlefield;
- displacement records describe models changing pose while already on the
  battlefield;
- `REINFORCEMENTS` remains a Movement phase step, not a placement kind;
- `REDEPLOY` remains a placement kind, not a displacement kind;
- `EMBARK` is removal;
- `DISEMBARK` is placement;
- `NORMAL_MOVE` emits displacement records;
- `REMAIN_STATIONARY` emits no placement/removal/displacement records;
- transition records serialize without Python object reprs.

Required tests:

- placement/removal/displacement records round-trip;
- invalid kind tokens fail;
- displacement rejects identical start/end pose;
- transition batch rejects duplicate and overlapping model IDs;
- deployment bridge emits deployment placement records;
- normal move emits `normal_move` displacement records;
- remain stationary emits no transition records;
- unsupported advance/fall back emit no transition records.

### Phase 10E: model geometry foundation

This phase resolves catalog/base-size data into runtime geometry used by
movement, pathing, collision, and line-of-sight systems.

Modules:

- `geometry/model_geometry.py`
- `geometry/measurement.py`
- `core/datasheet.py`
- `engine/unit_factory.py`

Objects:

- `BaseFootprintKind`
- `GeometrySourceKind`
- `HeightSourceKind`
- `FootprintPart`
- `ModelGeometry`

Invariants:

- catalog/source base sizes may remain in millimeters;
- resolved runtime geometry uses inches only;
- millimeter-to-inch conversion is centralized;
- no runtime pathing code performs ad hoc unit conversion;
- every resolved geometry has typed geometry and height provenance;
- fallback height is allowed only with explicit `HeightSourceKind`;
- hull/unique/large vehicle geometry can require manual overrides later.

Required tests:

- 32mm circular base resolves to inch radius;
- oval base resolves major/minor inch radii;
- resolved geometry stores inches only;
- missing height uses explicit keyword/fallback provenance;
- invalid source dimensions fail;
- geometry payloads round-trip without Python object reprs.

### Phase 10F: terrain factory foundation

This phase creates deterministic terrain fixtures for future movement, pathing,
and line-of-sight tests. It does not implement full terrain rules.

Modules:

- `geometry/terrain.py`
- `geometry/terrain_factory.py`
- `engine/battlefield_state.py`

Objects:

- `TerrainFeatureDefinition`
- `TerrainWallDefinition`
- `TerrainFloorDefinition`
- `TerrainFactory`
- `SpatialIndexState`

Invariants:

- terrain fixtures are deterministic and serializable;
- terrain coordinates and dimensions use inches;
- ruins walls/floors can be represented explicitly;
- terrain state has revision/cache keys suitable for pathing and LoS;
- pathing and LoS foundations are designed for spatial-index use;
- this phase does not implement full LoS, cover, or terrain traversal rules.

Required tests:

- empty battlefield terrain fixture round-trips;
- ruins fixture round-trips;
- terrain wall/floor dimensions are deterministic;
- invalid terrain geometry fails;
- terrain revision changes when terrain changes;
- spatial index state can be rebuilt deterministically.

### Phase 10G: movement legality context and capability resolver

This phase introduces structured movement legality inputs. It does not implement
a full path solver.

Modules:

- `engine/movement_legality.py`
- `engine/phases/movement.py`
- `core/ruleset_descriptor.py`

Objects:

- `MovementLegalityContext`
- `MovementCapabilitySet`
- `EngagementMovementPolicy`
- `MovementLegalityResult`

Invariants:

- `FLY`, `INFANTRY`, `BEAST`, `VEHICLE`, `MONSTER`, `WALKER`, `AIRCRAFT`, and
  similar keywords are legality/capability inputs, not Movement phase actions;
- 10e engagement policy is descriptor-driven;
- preview/alternate-edition engagement behavior requires an explicit ruleset
  descriptor;
- Movement phase action and model displacement kind are both available to
  legality checks;
- capability resolution is deterministic and serializable.

Required tests:

- `FLY` is resolved as a capability, not an action;
- `INFANTRY`/`BEAST` can receive terrain traversal permissions;
- `VEHICLE`/`MONSTER` restrictions are capability constraints;
- 10e Normal Move cannot end in enemy Engagement Range;
- unsupported/preview policy fails explicitly unless descriptor exists.

### Phase 10H: pathing smoke constraints

This phase adds first pathing-legality smoke checks using model geometry,
terrain fixtures, and movement capability data.

Modules:

- `geometry/pathing.py`
- `engine/movement_legality.py`
- `engine/phases/movement.py`

Objects:

- `PathValidationContext`
- `PathValidationResult`
- `PathConstraintViolation`

Invariants:

- battlefield edge crossing can be rejected;
- enemy model base crossing can be rejected;
- friendly model pass-through can be allowed;
- friendly `VEHICLE`/`MONSTER` pass-through can be blocked for relevant movers;
- end-on-model overlap can be rejected;
- base gap checks use base footprint geometry;
- model-volume-at-end checks use resolved model geometry;
- pivot-cost support is represented, even if not fully solved yet.

Required tests:

- circular infantry base can move through friendly infantry but cannot end
  overlapping;
- vehicle cannot pass through friendly vehicle/monster;
- model cannot cross battlefield edge;
- model cannot path through enemy base;
- model cannot end in enemy Engagement Range for 10e Normal Move;
- non-circular base movement records pivot-cost placeholder.

### Phase 10I: advance roll and reroll decision

This phase implements Advance as a Movement phase action after geometry,
transition records, and basic legality foundations exist.

Modules:

- `engine/phases/movement.py`
- `engine/dice.py`
- `engine/decision_controller.py`

Objects:

- `AdvanceRollRequest`
- `AdvanceRollResult`
- `MovementDiceRecord`

Invariants:

- `ADVANCE` is a Movement phase action;
- Advance distance is Movement characteristic plus Advance roll;
- dice results and reroll decisions are replay-facing;
- Advance emits displacement records when models move;
- Advance marks the unit as having advanced;
- no next unit selection occurs before activation terminal event.

Required tests:

- selecting Advance emits a dice roll request;
- Advance roll is recorded in replay payloads;
- reroll decision is offered only when applicable;
- Advance movement consumes Movement + roll distance;
- Advance emits displacement records and PathWitness;
- advanced unit cannot be selected again that Movement phase.

### Phase 10J: fall back action and basic Fall Back constraints

This phase implements Fall Back as a Movement phase action with explicit basic
constraints. Desperate Escape can remain typed unsupported until implemented.

Modules:

- `engine/phases/movement.py`
- `engine/movement_legality.py`

Objects:

- `FallBackActionResult`
- `DesperateEscapeRequirement`

Invariants:

- `FALL_BACK` is a Movement phase action;
- Fall Back is available only when the unit is eligible;
- Fall Back movement is recorded as model displacement;
- Desperate Escape requirements are detected and either resolved or explicitly
  unsupported;
- Fall Back marks the unit as having fallen back;
- no next unit selection occurs before activation terminal event.

Required tests:

- eligible unit can select Fall Back;
- ineligible unit cannot select Fall Back;
- Fall Back emits displacement records;
- Fall Back marks moved/fell-back state;
- Desperate Escape path returns typed unsupported until implemented.

### Phase 10K: Movement phase Reinforcements step shell

This phase adds the second Movement phase step. It does not implement full
Strategic Reserves or Deep Strike rules.

Modules:

- `engine/phases/movement.py`
- `engine/battle_round_flow.py`
- `engine/battlefield_state.py`

Objects:

- `MovementPhaseStepState`
- `ReinforcementSelection`
- `ReserveArrivalCandidate`

Invariants:

- Movement phase has `MOVE_UNITS` then `REINFORCEMENTS`;
- `REINFORCEMENTS` is a phase step, not a placement kind;
- Strategic Reserves and Deep Strike are placement kinds that may occur during
  this step;
- reserve arrival placements require placement records, not displacement records;
- no PathWitness is required for reserve placement.

Required tests:

- Movement phase enters Move Units step first;
- after all movement activations complete, phase enters Reinforcements step;
- Reinforcements step can emit a reserve-arrival decision;
- Deep Strike placement uses `BattlefieldPlacementKind.DEEP_STRIKE`;
- Strategic Reserves placement uses `BattlefieldPlacementKind.STRATEGIC_RESERVES`;
- Reinforcements itself never appears as a placement kind.

### Phase 10L: transport embark/disembark shell

This phase models transport state transitions without full transport rules.

Modules:

- `engine/transports.py`
- `engine/phases/movement.py`
- `engine/battlefield_state.py`

Objects:

- `TransportCargoState`
- `EmbarkSelection`
- `DisembarkSelection`

Invariants:

- `EMBARK` is battlefield removal;
- `DISEMBARK` is battlefield placement;
- neither Embark nor Disembark is a Movement phase action;
- embarked units are not placed units;
- embarked units cannot be selected for Normal Move as placed units;
- disembarked units are placed on the battlefield with placement records.

Required tests:

- Embark removes placed models from battlefield state;
- Embark emits removal records with `BattlefieldRemovalKind.EMBARK`;
- embarked unit is unavailable for Movement unit selection;
- Disembark places models on battlefield;
- Disembark emits placement records with `BattlefieldPlacementKind.DISEMBARK`;
- transport capacity validation is data-driven.

### Phase 10M: triggered movement foundation

This phase models movement-like displacements caused by timing-window rule
effects outside the standard Move Units action selector.

Modules:

- `engine/triggered_movement.py`
- `engine/battlefield_state.py`
- `engine/decision_controller.py`

Objects:

- `TriggeredMovementDescriptor`
- `TriggeredMovementKind`
- `TriggeredMovementRequest`

Invariants:

- triggered movement is not a Movement phase action;
- surge-like movement is a triggered model displacement;
- triggered movement can occur outside the Movement phase;
- triggered movement records source timing and source rule;
- surge movement has its own displacement kind;
- reactive movement is an umbrella/timing concept, not necessarily identical to
  every surge rule.

Required tests:

- Blood-Surge-like movement is represented as triggered movement, not Movement
  phase action;
- triggered movement can occur during opponent Shooting phase;
- triggered movement emits displacement records;
- triggered movement records source rule and trigger timing;
- triggered movement does not appear in `SELECT_MOVEMENT_ACTION`.

### Phase 11: shooting phase body vertical slice

This phase fills the shooting phase body behind the authoritative lifecycle. It
consumes placed units, weapon profiles, ballistic skill, range, line of sight,
visibility/terrain foundations, and damage allocation state.

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

## Future phase CORE V1 relevant areas index

CORE V1 is the previous implementation at
[SobolGaming/Warhammer40k_AI](https://github.com/SobolGaming/Warhammer40k_AI).
Before implementing each remaining phase, inspect only the narrow areas listed
for that phase. Use them as reference material for invariants, algorithms, edge
cases, and test ideas. Do not copy CORE V1 files wholesale.

### Phase 10E: model geometry foundation

Relevant CORE V1 areas:

- `src/warhammer40k_ai/utility/model_geometry.py`
- `src/warhammer40k_ai/utility/model_base.py`
- `src/warhammer40k_ai/utility/calcs.py`
- `src/warhammer40k_ai/utility/constants.py`
- `tests/units/test_model_geometry_resolver.py`

### Phase 10F: terrain factory foundation

Relevant CORE V1 areas:

- `src/warhammer40k_ai/battlefield/map.py`
- `src/warhammer40k_ai/battlefield/terrain_runtime.py`
- `src/warhammer40k_ai/battlefield/terrain_presets.py`
- `src/warhammer40k_ai/battlefield/terrain_elevation.py`
- `src/warhammer40k_ai/battlefield/terrain_visibility.py`
- `src/warhammer40k_ai/battlefield/terrain_cover.py`
- `tests/rules/test_line_of_sight.py`
- terrain-related battlefield tests

### Phase 10G: movement legality context and capability resolver

Relevant CORE V1 areas:

- `src/warhammer40k_ai/pathing/rules_profile.py`
- `src/warhammer40k_ai/pathing/types.py`
- `src/warhammer40k_ai/pathing/validation.py`
- `src/warhammer40k_ai/utility/calcs.py`
- `src/warhammer40k_ai/engine/decision_handlers/movement.py`

### Phase 10H: pathing smoke constraints

Relevant CORE V1 areas:

- `src/warhammer40k_ai/pathing/validation.py`
- `src/warhammer40k_ai/pathing/sweep.py`
- `src/warhammer40k_ai/pathing/types.py`
- `src/warhammer40k_ai/path_witness.py`
- `src/warhammer40k_ai/utility/calcs.py`
- `src/warhammer40k_ai/battlefield/map.py`

### Phase 10I: advance roll and reroll decision

Relevant CORE V1 areas:

- `src/warhammer40k_ai/engine/decision_handlers/movement.py`
- `src/warhammer40k_ai/movement_distance.py`
- `src/warhammer40k_ai/utility/dice.py`
- movement action/reroll tests

### Phase 10J: fall back action and basic Fall Back constraints

Relevant CORE V1 areas:

- `src/warhammer40k_ai/engine/decision_handlers/movement.py`
- `src/warhammer40k_ai/pathing/rules_profile.py`
- `src/warhammer40k_ai/pathing/validation.py`
- Fall Back / Desperate Escape tests if present

### Phase 10K: Movement phase Reinforcements step shell

Relevant CORE V1 areas:

- `src/warhammer40k_ai/engine/reserve_entry_rules.py`
- `src/warhammer40k_ai/engine/decision_handlers/movement.py`
- `src/warhammer40k_ai/engine/game_setup_flow.py`
- reserve/deep-strike tests

### Phase 10L: transport embark/disembark shell

Relevant CORE V1 areas:

- `src/warhammer40k_ai/engine/decision_handlers/movement.py`
- `tests/rules/test_core_transport_movement_phase.py`
- transport/deployment tests
- any transport assignment helpers used during setup

### Phase 10M: triggered movement foundation

Relevant CORE V1 areas:

- `src/warhammer40k_ai/engine/decision_handlers/movement.py`
- surge/reactive movement tests
- faction/rule handlers that queue reactive movement decisions

### Phase 11: shooting phase body vertical slice

Relevant CORE V1 areas:

- shooting decision handlers
- shooting commander/ranker tests
- `battlefield/terrain_visibility.py`
- `tests/rules/test_line_of_sight.py`
- damage allocation tests

### Phase 12: charge and fight phase body vertical slice

Relevant CORE V1 areas:

- charge/fight decision handlers
- `src/warhammer40k_ai/fight_move.py`
- charge diagnostics
- melee tests
- charge movement tests

### Phase 13: richer deployment, reserves, transports, and pre-battle abilities

Relevant CORE V1 areas:

- `src/warhammer40k_ai/engine/game_setup_flow.py`
- `src/warhammer40k_ai/engine/game_phase_flow.py`
- `src/warhammer40k_ai/engine/reserve_entry_rules.py`
- deployment/prebattle/transport tests

### Phase 14: broad content import and ability handler expansion

Relevant CORE V1 areas:

- faction/rule modules
- datasheet/wargear mixins
- faction-specific tests
- ability-specific movement/shooting/fight tests

## CORE V1 investigation and reuse policy by phase

CORE V1 is the previous implementation at
[SobolGaming/Warhammer40k_AI](https://github.com/SobolGaming/Warhammer40k_AI).
It is a reference implementation, not a source to copy wholesale. For each phase
below, inspect the listed CORE V1 areas before implementation, identify the
invariants and algorithms worth preserving, and then implement them in CORE V2
using strict typed data, fail-fast validation, replay-safe payloads, and current
import boundaries.

General migration rule for every phase:

1. Inspect CORE V1 only for the narrow behavior needed by the phase.
2. Name the invariant being preserved.
3. Write CORE V2 tests before porting behavior.
4. Port the smallest necessary algorithm, transform, or edge-case rule.
5. Do not copy broad files or permissive fallback behavior.
6. Replace raw object/string behavior with typed descriptors, payloads, and
   records.
7. Add replay/audit coverage for all state-changing behavior.

### Phase 10D: battlefield transition records

CORE V1 investigation:

- Inspect movement/deployment-related event payloads and decision handlers only
  to identify where models are placed, removed, or displaced.
- Inspect CORE V1 movement handling to understand where `move`, `advance`,
  `fall_back`, transport decisions, and reactive movement were historically
  separated.
- Do not port CORE V1 event shapes directly.

Relevant CORE V1 areas:

- `src/warhammer40k_ai/engine/decision_handlers/movement.py`
- `src/warhammer40k_ai/engine/decision_kinds.py`
- `src/warhammer40k_ai/engine/decision_requests.py`

Reuse guidance:

- Reuse the conceptual separation of movement action, model displacement,
  embark/disembark, and triggered movement.
- Do not reuse UI-specific or permissive event handling.
- Transition records in CORE V2 must be new typed replay-facing records.

Expected CORE V2 result:

- `ModelPlacementRecord`
- `ModelRemovalRecord`
- `ModelDisplacementRecord`
- `BattlefieldTransitionBatch`
- Deployment emits placement records.
- Normal Move emits displacement records.
- Remain Stationary emits no transition records.
- Unsupported Advance/Fall Back emit no transition records.

### Phase 10E: model geometry foundation

CORE V1 investigation:

- Inspect how CORE V1 parses base dimensions, converts millimeters to inches,
  resolves geometry overrides, handles compound/flying hull geometry, and
  estimates model height.
- Treat CORE V1 height heuristics as a starting point only; they are not assumed
  correct.
- Identify which geometry cases require explicit manual overrides.

Relevant CORE V1 areas:

- `src/warhammer40k_ai/utility/model_geometry.py`
- `src/warhammer40k_ai/utility/model_base.py`
- `src/warhammer40k_ai/utility/calcs.py`
- `src/warhammer40k_ai/utility/constants.py`
- `tests/units/test_model_geometry_resolver.py`

Reuse guidance:

- Reuse the principle that source/base-size data may start in millimeters but
  runtime geometry must be in inches.
- Reuse the idea of geometry provenance: parsed base, override, heuristic,
  fallback.
- Reuse relevant conversion tests and edge cases.
- Do not copy CORE V1's exact height heuristics without marking their source and
  adding tests.
- Do not store duplicate mm/inch fields in the resolved runtime geometry object.

Expected CORE V2 result:

- Catalog/base-size data may preserve official dimensions in millimeters.
- Runtime `ModelGeometry` stores inches only.
- Geometry source and height source are typed enums, not strings.
- Every resolved model geometry has explicit provenance.
- Large/unique/hull/flying models can require manual override later.

### Phase 10F: terrain factory foundation

CORE V1 investigation:

- Inspect map/terrain representation, ruins presets, terrain walls/floors,
  elevation helpers, visibility helpers, and cache invalidation strategy.
- Focus on deterministic fixture generation and spatial-index friendliness.
- Do not port the full CORE V1 `Map` object.

Relevant CORE V1 areas:

- `src/warhammer40k_ai/battlefield/map.py`
- `src/warhammer40k_ai/battlefield/terrain_runtime.py`
- `src/warhammer40k_ai/battlefield/terrain_presets.py`
- `src/warhammer40k_ai/battlefield/terrain_elevation.py`
- `src/warhammer40k_ai/battlefield/terrain_visibility.py`
- `src/warhammer40k_ai/battlefield/terrain_cover.py`
- `tests/rules/test_line_of_sight.py`
- terrain-related battlefield tests

Reuse guidance:

- Reuse deterministic terrain fixture ideas and common ruins dimensions where
  appropriate.
- Reuse cache/revision concepts, not mutable map internals.
- Build CORE V2 terrain as serializable immutable definitions plus explicit
  revision/index state.
- Ensure the design is suitable for efficient pathing and LoS.

Expected CORE V2 result:

- Deterministic empty battlefield fixture.
- Deterministic ruins fixture.
- Explicit terrain walls/floors/footprints.
- Revision/cache keys for terrain, model blockers, and LoS.
- No full LoS, cover, or terrain traversal behavior yet.

### Phase 10G: movement legality context and capability resolver

CORE V1 investigation:

- Inspect how CORE V1 resolves FLY, Infantry/Beast terrain traversal,
  vehicle/monster/walker constraints, vertical distance, ruins traversal, and
  engagement movement constraints.
- Inspect movement profile and pathing rule helpers.
- Do not import special-rule dictionaries directly into CORE V2 runtime logic.

Relevant CORE V1 areas:

- `src/warhammer40k_ai/pathing/rules_profile.py`
- `src/warhammer40k_ai/pathing/types.py`
- `src/warhammer40k_ai/pathing/validation.py`
- `src/warhammer40k_ai/utility/calcs.py`
- `src/warhammer40k_ai/engine/decision_handlers/movement.py`

Reuse guidance:

- Reuse the capability categories, not CORE V1's dynamic attribute/string
  probing.
- Convert keyword/rule-driven behavior into typed capability resolution.
- FLY, INFANTRY, BEAST, VEHICLE, MONSTER, WALKER, AIRCRAFT, and HOVER are
  legality inputs, not actions.
- Edition-specific engagement behavior must come from `RulesetDescriptor`, not
  hard-coded checks.
- Preview/alternate rules require explicit descriptor/source identity.

Expected CORE V2 result:

- `MovementLegalityContext`
- `MovementCapabilitySet`
- `EngagementMovementPolicy`
- `MovementLegalityResult`
- 10e policy tested.
- Preview/alternate policy explicitly unavailable unless descriptor exists.

### Phase 10H: pathing smoke constraints

CORE V1 investigation:

- Inspect CORE V1 path witness, sweep/collision validation, battlefield boundary
  handling, model blocker handling, terrain sweep, tight clearance, and
  friendly/enemy model path rules.
- Focus on simple smoke constraints first, not full pathfinding.
- Inspect performance-sensitive cache usage.

Relevant CORE V1 areas:

- `src/warhammer40k_ai/pathing/validation.py`
- `src/warhammer40k_ai/pathing/sweep.py`
- `src/warhammer40k_ai/pathing/types.py`
- `src/warhammer40k_ai/path_witness.py`
- `src/warhammer40k_ai/utility/calcs.py`
- `src/warhammer40k_ai/battlefield/map.py`

Reuse guidance:

- Reuse concepts for swept footprint, blocker caches, and witness validation.
- Do not port full shapely-heavy logic until CORE V2 geometry and terrain
  contracts are stable.
- Prefer small deterministic smoke checks with clear violation records.
- Preserve performance direction: spatial index first, brute-force only in tiny
  tests.

Expected CORE V2 result:

- battlefield edge crossing rejection;
- enemy model base crossing rejection;
- friendly model pass-through allowance;
- friendly VEHICLE/MONSTER pass-through blocking where applicable;
- end-on-model overlap rejection;
- base gap checks;
- model-volume-at-end checks;
- pivot cost placeholder for non-circular bases.

### Phase 10I: advance roll and reroll decision

CORE V1 investigation:

- Inspect how CORE V1 queues/selects movement action, rolls Advance, records
  movement status, handles reroll decisions, and applies movement distance.
- Inspect dice utilities and existing decision payload patterns.
- Do not port broad movement-handler behavior.

Relevant CORE V1 areas:

- `src/warhammer40k_ai/engine/decision_handlers/movement.py`
- `src/warhammer40k_ai/movement_distance.py`
- `src/warhammer40k_ai/utility/dice.py`
- movement action/reroll tests

Reuse guidance:

- Reuse the invariant that Advance is a Movement phase action and affects
  movement status.
- Reuse only the minimal dice/reroll flow ideas.
- CORE V2 must route rolls and rerolls through deterministic dice/replay
  machinery.
- Advance emits displacement records only after actual model movement.

Expected CORE V2 result:

- selecting Advance emits dice roll request;
- Advance roll is replayed deterministically;
- reroll decision appears only when a supported reroll source exists;
- movement distance = Movement characteristic + Advance roll;
- Advance emits `ModelDisplacementRecord` values;
- unit is marked moved/advanced and cannot be selected again that Movement
  phase.

### Phase 10J: fall back action and basic Fall Back constraints

CORE V1 investigation:

- Inspect CORE V1 Fall Back action handling, movement status flags, Desperate
  Escape detection, and engagement/path constraints.
- Do not implement all Desperate Escape behavior unless the phase explicitly
  scopes it.

Relevant CORE V1 areas:

- `src/warhammer40k_ai/engine/decision_handlers/movement.py`
- `src/warhammer40k_ai/pathing/rules_profile.py`
- `src/warhammer40k_ai/pathing/validation.py`
- Fall Back / Desperate Escape tests if present

Reuse guidance:

- Reuse the distinction between Fall Back action and general displacement.
- Reuse detection ideas for Desperate Escape requirements, but return typed
  unsupported if not fully implemented.
- Fall Back legality must depend on movement legality/capability descriptors,
  not ad hoc checks.

Expected CORE V2 result:

- eligible unit can select Fall Back;
- ineligible unit cannot select Fall Back;
- Fall Back emits displacement records;
- Fall Back marks moved/fell-back state;
- Desperate Escape is detected and either resolved or typed unsupported.

### Phase 10K: Movement phase Reinforcements step shell

CORE V1 investigation:

- Inspect how CORE V1 handles reserves, Strategic Reserves, Deep Strike, reserve
  arrival validation, and forced arrival failure.
- Treat Reinforcements as a Movement phase step, not a placement kind.

Relevant CORE V1 areas:

- `src/warhammer40k_ai/engine/reserve_entry_rules.py`
- `src/warhammer40k_ai/engine/decision_handlers/movement.py`
- `src/warhammer40k_ai/engine/game_setup_flow.py`
- reserve/deep-strike tests

Reuse guidance:

- Reuse arrival-position validation concepts.
- Reuse edge cases around forced arrival, board edges, and deployment
  restrictions only after strict tests exist.
- Placement from reserves must emit placement records, not displacement records.
- Do not require PathWitness for reserve placement.

Expected CORE V2 result:

- Movement phase has Move Units then Reinforcements.
- Strategic Reserves placement uses `BattlefieldPlacementKind.STRATEGIC_RESERVES`.
- Deep Strike placement uses `BattlefieldPlacementKind.DEEP_STRIKE`.
- Reinforcements itself is never serialized as a placement kind.

### Phase 10L: transport embark/disembark shell

CORE V1 investigation:

- Inspect transport assignment, embark, disembark, destroyed transport
  disembark, capacity validation, and movement-phase transport decisions.
- Keep transport state separate from placed battlefield state.

Relevant CORE V1 areas:

- `src/warhammer40k_ai/engine/decision_handlers/movement.py`
- `tests/rules/test_core_transport_movement_phase.py`
- transport/deployment tests
- any transport assignment helpers used during setup

Reuse guidance:

- Reuse the invariant that Embark removes models from battlefield and places
  them into transport cargo.
- Reuse the invariant that Disembark places models onto battlefield from cargo.
- Do not model Embark or Disembark as Movement phase actions.
- Transport capacity and restrictions should be data-driven.

Expected CORE V2 result:

- Embark emits `BattlefieldRemovalKind.EMBARK`.
- Disembark emits `BattlefieldPlacementKind.DISEMBARK`.
- Embarked units are not placed units and cannot be selected for Normal Move.
- Disembark places models with placement records.
- Capacity validation fails explicitly.

### Phase 10M: triggered movement foundation

CORE V1 investigation:

- Inspect Blood Surge, reactive move flags, Battle Focus-style movement,
  reactive pursuit, and surge validation.
- Do not collapse all reactive moves into one movement kind.
- Treat "reactive" as a trigger/timing category; treat "surge" as a specific
  displacement kind or rule family.

Relevant CORE V1 areas:

- `src/warhammer40k_ai/engine/decision_handlers/movement.py`
- surge/reactive movement tests
- faction/rule handlers that queue reactive movement decisions

Reuse guidance:

- Reuse trigger timing ideas and validation edge cases.
- Do not treat triggered moves as Movement phase actions.
- Triggered movement can occur in opponent phases and must record source
  timing/rule.
- Use `ModelDisplacementKind.SURGE_MOVE` for surge-style displacement.
- Use a descriptor for broader triggered movement categories.

Expected CORE V2 result:

- triggered movement descriptor exists;
- Blood-Surge-like movement is not a Movement phase action;
- triggered movement records source rule and trigger timing;
- triggered movement emits displacement records;
- triggered movement does not appear in `SELECT_MOVEMENT_ACTION`.

### Phase 11: shooting phase body vertical slice

CORE V1 investigation:

- Inspect shooting decision flow, target selection, line of sight, weapon
  declaration, attack sequence, damage allocation, and model destruction.
- Inspect LoS and terrain visibility code only after Phase 10F terrain and Phase
  10H path/geometry foundations exist.
- Do not port shooting as one large handler.

Relevant CORE V1 areas:

- shooting decision handlers;
- shooting commander/ranker tests;
- `battlefield/terrain_visibility.py`;
- `tests/rules/test_line_of_sight.py`;
- damage allocation tests.

Reuse guidance:

- Reuse decision sequencing and attack pipeline invariants.
- Reuse LoS edge cases once CORE V2 terrain/geometry are available.
- Model destruction must emit battlefield removal records.
- Weapon abilities must come from typed descriptors, not raw text.

Expected CORE V2 result:

- select shooting unit;
- target selection;
- LoS/range checks;
- declare weapons;
- hit/wound/save/damage;
- damage allocation;
- model destruction with removal records;
- event log and replay.

### Phase 12: charge and fight phase body vertical slice

CORE V1 investigation:

- Inspect charge declaration, charge roll, charge movement, pile-in, fight target
  selection, melee declaration, attack resolution, consolidate, and interrupt
  handling.
- Inspect fight movement validation for pile-in/consolidate constraints.

Relevant CORE V1 areas:

- charge/fight decision handlers;
- `src/warhammer40k_ai/fight_move.py`;
- charge diagnostics;
- melee tests;
- charge movement tests.

Reuse guidance:

- Reuse timing and validation invariants.
- Charge move, pile-in, and consolidate are model displacements, not Movement
  phase actions.
- Charge movement must emit displacement records.
- Fight movement must use movement legality/pathing primitives rather than
  duplicating geometry logic.
- Interrupts must remain typed decision metadata.

Expected CORE V2 result:

- declare charge;
- charge roll;
- charge movement with `PathWitness`;
- Heroic Intervention interrupt;
- pile-in;
- fight target selection;
- melee declaration;
- attack resolution;
- consolidate;
- displacement records for charge/pile-in/consolidate.

### Phase 13: richer deployment, reserves, transports, and pre-battle abilities

CORE V1 investigation:

- Inspect setup flow, deployment, redeploy, Scout, Infiltrate, reserves, Deep
  Strike, transports, leader attachment, and pre-battle rules.
- Prioritize behavior that now has CORE V2 lifecycle slots and
  placement/removal records.

Relevant CORE V1 areas:

- `src/warhammer40k_ai/engine/game_setup_flow.py`
- `src/warhammer40k_ai/engine/game_phase_flow.py`
- `src/warhammer40k_ai/engine/reserve_entry_rules.py`
- deployment/prebattle/transport tests

Reuse guidance:

- Reuse setup sequence invariants and reserve validation ideas.
- Deployment and redeploy must emit placement/removal records.
- Scout moves are model displacements.
- Infiltrate/Deep Strike are placement-rule mechanisms.
- Transport assignment/capacity remains data-driven.

Expected CORE V2 result:

- richer deployment;
- Scout;
- Infiltrate;
- reserves;
- Deep Strike;
- embark/disembark;
- destroyed transport disembark;
- transport capacity restrictions;
- leader attachment constraints;
- reserve restriction validation.

### Phase 14: broad content import and ability handler expansion

CORE V1 investigation:

- Inspect existing faction/detachment/codex implementations only after the
  owning CORE V2 schemas and timing windows exist.
- Use CORE V1 tests to identify edge cases, not as runtime architecture.

Relevant CORE V1 areas:

- faction/rule modules;
- datasheet/wargear mixins;
- faction-specific tests;
- ability-specific movement/shooting/fight tests.

Reuse guidance:

- Load real facts as soon as schema exists.
- Instantiate real units only through mustering.
- Execute rules only in owning phase/timing-window handler.
- Source text must remain linked to structured descriptors.
- Unsupported ability shapes remain explicit unsupported descriptors.
- Runtime engine code must not parse raw codex text.

Expected CORE V2 result:

- movement handlers for supported movement modifiers/capabilities;
- shooting handlers for supported weapon abilities;
- charge/fight handlers for supported melee/timing abilities;
- deployment/pre-battle handlers for supported setup abilities;
- replay coverage for each imported behavior.

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
