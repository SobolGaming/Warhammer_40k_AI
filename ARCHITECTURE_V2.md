# CORE V2 Architecture Build Order

This document contains the build order roadmap split out from README Section 4.

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

CORE V1 relevant areas:

- `src/warhammer40k_ai/utility/model_geometry.py`
- `src/warhammer40k_ai/utility/model_base.py`
- `src/warhammer40k_ai/utility/calcs.py`
- `src/warhammer40k_ai/utility/constants.py`
- `tests/units/test_model_geometry_resolver.py`

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

CORE V1 relevant areas:

- `src/warhammer40k_ai/battlefield/map.py`
- `src/warhammer40k_ai/battlefield/terrain_runtime.py`
- `src/warhammer40k_ai/battlefield/terrain_presets.py`
- `src/warhammer40k_ai/battlefield/terrain_elevation.py`
- `src/warhammer40k_ai/battlefield/terrain_visibility.py`
- `src/warhammer40k_ai/battlefield/terrain_cover.py`
- `tests/rules/test_line_of_sight.py`
- terrain-related battlefield tests

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
- 10e Normal Move cannot transit enemy Engagement Range;
- 10e Fall Back can transit but cannot end in enemy Engagement Range;
- preview Normal Move can transit but cannot end in enemy Engagement Range;
- unsupported/preview policy fails explicitly unless descriptor exists.

CORE V1 relevant areas:

- `src/warhammer40k_ai/pathing/rules_profile.py`
- `src/warhammer40k_ai/pathing/types.py`
- `src/warhammer40k_ai/pathing/validation.py`
- `src/warhammer40k_ai/utility/calcs.py`
- `src/warhammer40k_ai/engine/decision_handlers/movement.py`

### Phase 10H: pathing smoke constraints

This phase adds first pathing-legality smoke checks using model geometry,
terrain fixtures, and movement capability data.

Modules:

- `geometry/pathing.py`
- `engine/movement_legality.py`
- `engine/phases/movement.py`
- `core/ruleset_descriptor.py`

Objects:

- `PathValidationContext`
- `PathValidationResult`
- `PathConstraintViolation`
- `CoherencyPolicyKind`

Invariants:

- battlefield edge crossing can be rejected;
- non-FLY Normal/Advance movement cannot path through enemy model bases;
- Fall Back movement can move over enemy models only through the Desperate
  Escape flow;
- FLY Normal/Advance/Fall Back movement can move over enemy models without
  Desperate Escape;
- Desperate Escape resolution is deferred to the Fall Back phase
  implementation;
- enemy Engagement Range transit can be rejected independently from ending in
  enemy Engagement Range;
- friendly model pass-through can be allowed;
- friendly `VEHICLE`/`MONSTER` pass-through can be blocked for relevant movers;
- end-on-model overlap can be rejected;
- base gap checks use base footprint geometry;
- model-volume-at-end checks use resolved model geometry;
- pivot-cost support is represented, even if not fully solved yet;
- coherency policy is descriptor data only in this phase;
- runtime coherency validation remains future work;
- future coherency enforcement sites are setup/placement, end of any move, and
  end of every turn cleanup.

Required tests:

- circular infantry base can move through friendly infantry but cannot end
  overlapping;
- non-FLY vehicle cannot pass through friendly vehicle/monster;
- model cannot cross battlefield edge;
- non-FLY Normal/Advance movement cannot path through enemy model bases;
- FLY Normal Move can transit enemy model bases and enemy Engagement Range;
- FLY Normal Move cannot end within enemy Engagement Range or on another model;
- FLY VEHICLE can transit friendly VEHICLE/MONSTER blockers;
- model cannot move through enemy Engagement Range for 10e Normal Move;
- model cannot move through enemy Engagement Range for 10e Advance;
- model can move through enemy Engagement Range for 10e Fall Back when policy
  allows, but cannot end there;
- model cannot end in enemy Engagement Range for 10e Normal Move;
- charge movement uses the charge policy and is the exception path for ending
  in Engagement Range;
- non-circular base movement records pivot-cost placeholder;
- 10e coherency descriptor uses a seven-model large-unit threshold;
- 11e preview coherency descriptor uses all-models-within-distance policy.

CORE V1 relevant areas:

- `src/warhammer40k_ai/pathing/validation.py`
- `src/warhammer40k_ai/pathing/sweep.py`
- `src/warhammer40k_ai/pathing/types.py`
- `src/warhammer40k_ai/path_witness.py`
- `src/warhammer40k_ai/utility/calcs.py`
- `src/warhammer40k_ai/battlefield/map.py`

### Phase 10I: terrain movement semantics and endpoint support

This phase implements movement-relevant terrain behavior. It does not implement
visibility, Benefit of Cover, Plunging Fire, or shooting interactions.

Modules:

- `geometry/pathing.py`
- `geometry/terrain.py`
- `engine/movement_legality.py`
- `core/ruleset_descriptor.py`

Objects:

- `TerrainMovementPolicy`
- `TerrainTraversalMode`
- `TerrainPathLegalityContext`
- `TerrainPathSegment`
- `TerrainTraversalViolation`
- `TerrainFeatureMovementPolicy`
- `TerrainEndpointSupportPolicy`
- `TerrainSupportSurface`

Invariants:

- terrain movement behavior is descriptor-driven by terrain feature kind;
- models may move up, over, and down terrain unless terrain-specific policy says
  otherwise;
- terrain features 2" or less in height can be moved over as if not there;
- taller terrain requires vertical distance to climb up/down;
- models cannot end a move mid-climb;
- some terrain can be moved over but not ended on;
- support surfaces can require the model base/contact footprint to be fully
  contained;
- no-overhang endpoint checks apply to elevated hills/structures and upper
  ruin floors;
- Ruins upper-floor endpoint eligibility is keyword-gated;
- Ruins through-wall/floor traversal is keyword-gated;
- baseless/hull models require explicit contact-footprint geometry before
  no-overhang checks can be final;
- visibility, cover, Plunging Fire, and shooting effects are deferred to
  11A/11B.

Required tests:

- model can move freely over terrain <= 2";
- model pays vertical distance to climb terrain > 2";
- model cannot end mid-climb;
- model cannot end on barricade/fuel pipes;
- model cannot end on battlefield debris/statuary;
- model can end on hill/structure top when base is fully contained;
- model cannot end on hill/structure top when base overhangs;
- `INFANTRY` can move through Ruins walls/floors by policy;
- `INFANTRY` can move through Ruins walls/floors but cannot end inside them;
- non-eligible `VEHICLE` cannot move through Ruins walls/floors;
- `INFANTRY`/`BEAST`/`FLY` can end on upper Ruins floor if no overhang;
- non-eligible model cannot end on upper Ruins floor;
- upper Ruins floor endpoint fails if base overhangs;
- elevated terrain endpoint fails if there is no valid support surface;
- baseless/hull no-overhang check returns typed unsupported/manual-geometry-required
  when contact geometry is missing;
- terrain traversal result serializes without Python object reprs.

CORE V1 relevant areas:

- `src/warhammer40k_ai/pathing/rules_profile.py`
- `src/warhammer40k_ai/pathing/types.py`
- `src/warhammer40k_ai/pathing/validation.py`
- `src/warhammer40k_ai/pathing/sweep.py`
- `src/warhammer40k_ai/battlefield/terrain_runtime.py`
- `src/warhammer40k_ai/battlefield/terrain_elevation.py`
- `src/warhammer40k_ai/battlefield/terrain_presets.py`
- `src/warhammer40k_ai/utility/calcs.py`

### Phase 10J: advance roll and reroll decision

This phase implements Advance as a Movement phase action after geometry,
transition records, terrain movement semantics, and basic legality foundations
exist.

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
- movement action option generation must be enemy Engagement Range-aware before
  Advance and Fall Back are fully implemented;
- units outside enemy Engagement Range can be offered Remain Stationary, Normal
  Move, and Advance;
- units within enemy Engagement Range can be offered Remain Stationary and Fall
  Back;
- Advance distance is Movement characteristic plus Advance roll;
- dice results and reroll decisions are replay-facing;
- Advance consumes `PathValidationContext` and terrain movement policy instead
  of duplicating pathing assumptions;
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

CORE V1 relevant areas:

- `src/warhammer40k_ai/engine/decision_handlers/movement.py`
- `src/warhammer40k_ai/movement_distance.py`
- `src/warhammer40k_ai/utility/dice.py`
- movement action/reroll tests

### Phase 10K: fall back action and Desperate Escape shell

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

CORE V1 relevant areas:

- `src/warhammer40k_ai/engine/decision_handlers/movement.py`
- `src/warhammer40k_ai/pathing/rules_profile.py`
- `src/warhammer40k_ai/pathing/validation.py`
- Fall Back / Desperate Escape tests if present

### Phase 10L: Movement phase Reinforcements step shell

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

CORE V1 relevant areas:

- `src/warhammer40k_ai/engine/reserve_entry_rules.py`
- `src/warhammer40k_ai/engine/decision_handlers/movement.py`
- `src/warhammer40k_ai/engine/game_setup_flow.py`
- reserve/deep-strike tests

### Phase 10M: transport embark/disembark shell

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

CORE V1 relevant areas:

- `src/warhammer40k_ai/engine/decision_handlers/movement.py`
- `tests/rules/test_core_transport_movement_phase.py`
- transport/deployment tests
- any transport assignment helpers used during setup

### Phase 10N: triggered movement foundation

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

CORE V1 relevant areas:

- `src/warhammer40k_ai/engine/decision_handlers/movement.py`
- surge/reactive movement tests
- faction/rule handlers that queue reactive movement decisions

### Phase 11A: line-of-sight terrain visibility foundation

This phase adds terrain visibility and LoS foundations after movement terrain
semantics are stable. It does not implement the full shooting attack sequence.

Modules:

- `geometry/visibility.py`
- `geometry/terrain.py`
- `engine/battlefield_state.py`
- `core/ruleset_descriptor.py`

Objects:

- `LineOfSightPolicy`
- `TerrainVisibilityContext`
- `VisibilityBlockerRecord`
- `LineOfSightWitness`
- `CoverPolicyDescriptor`

Invariants:

- ruins visibility is explicit terrain policy, not ad hoc shooting logic;
- visibility blockers use model volume and terrain wall/floor interactions;
- cover policy descriptors are data and do not execute shooting behavior;
- LoS and cover checks use spatial index/cache revision data;
- LoS witness/debug payloads are replay-safe;
- this phase does not implement hit/wound/save/damage or damage allocation.

Required tests:

- terrain visibility fixture can block LoS deterministically;
- ruins wall/floor interactions are represented in LoS context;
- model volume participates in visibility checks;
- terrain visibility cache key changes when terrain revision changes;
- cover policy descriptor round-trips without object reprs;
- LoS witness/debug payload round-trips without object reprs.

CORE V1 relevant areas:

- `src/warhammer40k_ai/battlefield/terrain_visibility.py`
- `src/warhammer40k_ai/battlefield/terrain_cover.py`
- `src/warhammer40k_ai/battlefield/map.py`
- `tests/rules/test_line_of_sight.py`
- LoS and cover-related terrain tests

### Phase 11B: shooting phase body vertical slice

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

CORE V1 relevant areas:

- shooting decision handlers
- shooting commander/ranker tests
- `battlefield/terrain_visibility.py`
- `tests/rules/test_line_of_sight.py`
- damage allocation tests

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

CORE V1 relevant areas:

- charge/fight decision handlers
- `src/warhammer40k_ai/fight_move.py`
- charge diagnostics
- melee tests
- charge movement tests

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

CORE V1 relevant areas:

- `src/warhammer40k_ai/engine/game_setup_flow.py`
- `src/warhammer40k_ai/engine/game_phase_flow.py`
- `src/warhammer40k_ai/engine/reserve_entry_rules.py`
- deployment/prebattle/transport tests

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

CORE V1 relevant areas:

- faction/rule modules
- datasheet/wargear mixins
- faction-specific tests
- ability-specific movement/shooting/fight tests

## CORE V1 investigation and reuse policy

CORE V1 is the previous implementation at
[SobolGaming/Warhammer40k_AI](https://github.com/SobolGaming/Warhammer40k_AI).
It is a reference implementation, not a source to copy wholesale. For each
future phase, inspect the listed CORE V1 areas embedded in that phase's roadmap
entry before implementation, identify the invariants and algorithms worth
preserving, and then implement them in CORE V2 using strict typed data, fail-fast
validation, replay-safe payloads, and current import boundaries.

General migration rule for every phase:

1. Inspect CORE V1 only for the narrow behavior needed by the phase.
2. Name the invariant being preserved.
3. Write CORE V2 tests before porting behavior.
4. Port the smallest necessary algorithm, transform, or edge-case rule.
5. Do not copy broad files or permissive fallback behavior.
6. Replace raw object/string behavior with typed descriptors, payloads, and
   records.
7. Add replay/audit coverage for all state-changing behavior.
