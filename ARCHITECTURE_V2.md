# CORE V2 Architecture Build Order

This document is the build-order roadmap for reconstructing the Warhammer 40,000 CORE V2 engine after the completed Phase 1-10I work.

The roadmap is intentionally rules-engine first:

- engine lifecycle and state are authoritative;
- every player, AI, UI, network, and replay interaction goes through `DecisionRequest`, `DecisionResult`, and `DecisionRecord`;
- runtime code executes typed descriptors and handlers, not raw rule text;
- replay payloads are deterministic, JSON-safe, and fail-fast on drift;
- unsupported rule shapes are explicit, source-linked, and auditable.

Primary references for roadmap coverage:

- Warhammer 40,000 10th Edition Core Rules: <https://wahapedia.ru/wh40k10ed/the-rules/core-rules/>
- Chapter Approved 2025-26: <https://wahapedia.ru/wh40k10ed/the-rules/chapter-approved-2025-26/>
- CORE V1 reference implementation: <https://github.com/SobolGaming/Warhammer40k_AI>
- CORE V1 generated Wahapedia data: <https://github.com/SobolGaming/Warhammer40k_AI/tree/dev/wahapedia_data>
- CORE V2 repository: <https://github.com/SobolGaming/Warhammer_40k_AI>

## Roadmap status

Everything through **Phase 10I** is treated as implemented or in final review at the time this file was generated. Do not insert new work before Phase 10J unless a merged implementation invalidates the phase boundary.

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

## Cross-cutting architectural rules

1. **No runtime raw text parsing.** Raw rule text is normalized, parsed, and compiled at ingest/authoring time into typed descriptors or explicit unsupported descriptors.
2. **No silent fallbacks.** If a rule, terrain shape, ability, or decision cannot be represented safely, emit typed unsupported state.
3. **No UI-owned state mutation.** CLI, local UI, network UI, and AI policies answer `DecisionRequest`s; the engine validates and mutates authoritative state.
4. **No ad hoc content facts.** Datasheet stats, keywords, wargear, base sizes, factions, detachments, enhancements, Stratagems, missions, deployment maps, and terrain layouts come from catalog/source packages.
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

# Remaining build order

## Phase 10J: precise movement distance, straight-line segments, and pivot costs

This phase replaces pivot-cost placeholders with real 10e movement-distance accounting. It must land before Advance, Fall Back, Charge movement, Pile-in, Consolidate, or triggered movement become authoritative.

Modules:

- `geometry/pathing.py`
- `geometry/movement_envelope.py`
- `engine/phases/movement.py`
- `engine/movement_legality.py`

Objects:

- `MovementDistanceBudget`
- `MovementSegment`
- `PivotCostPolicy`
- `PivotEvent`
- `MovementDistanceWitness`

Invariants:

- movement distance is measured across straight-line segments and pivots;
- straight-line distance is measured from the same point on the base/model at the start and end of each line;
- each model pays its pivot value only the first time it pivots during that move;
- round-base models normally have pivot cost 0";
- non-round-base non-`MONSTER`/non-`VEHICLE` models pay 1";
- non-round-base `MONSTER`/`VEHICLE` models pay 2";
- round-base `VEHICLE` models wider than 32mm with a flying stem or hover stand pay 2";
- `AIRCRAFT` pivot cost is 0" in generic pivot accounting, with aircraft-specific movement deferred to Phase 10Q;
- if insufficient movement remains to pay a required pivot cost, the move is invalid;
- pivot-cost and movement-distance witnesses serialize without object reprs.

Required tests:

- circular base with no facing change has 0" pivot cost;
- non-round infantry base pays 1" once even if it pivots multiple times;
- non-round `VEHICLE`/`MONSTER` pays 2";
- round-base large flying-stem/hover-stand `VEHICLE` pays 2";
- `AIRCRAFT` pays 0" in generic pivot policy;
- insufficient remaining movement after pivot cost rejects the move;
- straight-line distance uses same-point measurement semantics;
- movement distance witness round-trips.

CORE V1 relevant areas:

- `src/warhammer40k_ai/pathing/validation.py`
- `src/warhammer40k_ai/pathing/sweep.py`
- `src/warhammer40k_ai/pathing/types.py`
- `src/warhammer40k_ai/movement_distance.py`
- movement distance / pivot tests

## Phase 10K: unit coherency runtime validation and movement rollback

Descriptor data already represents 10e and preview coherency policies; this phase applies those policies to battlefield placements and move endpoints.

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
- 10e units of 2-6 models require each model to be within 2" horizontally and 5" vertically of at least one other model in that unit;
- 10e units of 7+ models require each model to be within 2" horizontally and 5" vertically of at least two other models in that unit;
- preview all-models-within-distance policy is supported by descriptor;
- units must be set up in coherency;
- units must end any kind of move in coherency;
- if a unit cannot end a move in coherency, that move is invalid and model poses roll back;
- end-of-turn coherency cleanup is detected here but model-removal resolution lands in Phase 11C;
- coherency validation returns offending model IDs.

Required tests:

- 10e 5-model unit requires one neighbor per model;
- 10e 7-model unit requires two neighbors per model;
- 10e broken coherency identifies offending model IDs;
- preview all-models-within-distance policy validates pairwise distance;
- invalid Normal Move rolls back to previous placement;
- deployment placement outside coherency is rejected;
- coherency result payload round-trips.

CORE V1 relevant areas:

- movement validation/pathing tests;
- setup/deployment placement validation tests;
- coherency-related movement tests.

## Phase 10L: engagement-aware Movement action options and Normal Move finalization

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
- Normal Move consumes precise distance, pivot, terrain, pathing, and coherency validators;
- Normal Move cannot end on another model, inside terrain, outside the battlefield, or out of coherency;
- Normal Move emits displacement records only after all validators pass.

Required tests:

- action options outside Engagement Range are Remain Stationary, Normal Move, Advance;
- action options inside Engagement Range are Remain Stationary, Fall Back;
- Normal Move validates pathing, terrain, pivot cost, and coherency;
- failed Normal Move does not mutate battlefield state;
- successful Normal Move emits displacement records and terminal activation event.

CORE V1 relevant areas:

- `src/warhammer40k_ai/engine/decision_handlers/movement.py`
- `src/warhammer40k_ai/pathing/validation.py`
- `src/warhammer40k_ai/pathing/rules_profile.py`

## Phase 10M: Advance action, dice, rerolls, and advanced-state restrictions

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
- Advance consumes terrain, pivot, pathing, and coherency validators;
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

## Phase 10N: Fall Back action and Desperate Escape resolution

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
- moving over enemy models during Fall Back requires Desperate Escape tests unless the model is `TITANIC` or can `FLY`;
- Battle-shocked units selected to Fall Back require Desperate Escape tests for every model;
- Desperate Escape rolls of 1-2 destroy one model from the falling-back unit, selected by the controlling player;
- the same model can trigger only one Desperate Escape test per phase;
- units that Fall Back cannot shoot or declare a charge that turn unless a rule permits it;
- destroyed models emit removal records with correct destruction context.

Required tests:

- eligible unit can Fall Back;
- ineligible unit cannot Fall Back;
- endpoint in Engagement Range is rejected;
- enemy-model overflight creates Desperate Escape requirements;
- `FLY`/`TITANIC` exceptions avoid Desperate Escape for crossing enemy models;
- Battle-shocked Fall Back requires tests for every model;
- failed Desperate Escape destroys a selected model;
- Fall Back emits displacement and removal records where applicable.

CORE V1 relevant areas:

- `src/warhammer40k_ai/engine/decision_handlers/movement.py`
- `src/warhammer40k_ai/pathing/rules_profile.py`
- `src/warhammer40k_ai/pathing/validation.py`

## Phase 10O: Reinforcements, Strategic Reserves, Deep Strike, and reserve placement

Modules:

- `engine/phases/movement.py`
- `engine/reserves.py`
- `engine/battlefield_state.py`
- `engine/placement.py`

Objects:

- `MovementPhaseStepState`
- `ReserveState`
- `ReserveArrivalCandidate`
- `ReinforcementPlacement`
- `StrategicReserveRule`

Invariants:

- Movement phase has Move Units then Reinforcements;
- `REINFORCEMENTS` is a phase step, not a placement kind;
- reserve placement uses placement records, not displacement records;
- Strategic Reserves and Deep Strike are distinct placement mechanisms;
- reserve placements validate battlefield edges, enemy distance restrictions, terrain endpoints, coherency, model overlap, and deployment restrictions;
- mandatory arrivals are requeued or fail explicitly according to rules;
- no `PathWitness` is required for placement.

Required tests:

- Movement phase enters Reinforcements after Move Units;
- Deep Strike placement uses `BattlefieldPlacementKind.DEEP_STRIKE`;
- Strategic Reserves placement uses `BattlefieldPlacementKind.STRATEGIC_RESERVES`;
- illegal reserve placement fails without mutating state;
- reserve placement validates coherency and Engagement Range setup restriction;
- reserve placement validates terrain endpoint support.

CORE V1 relevant areas:

- `src/warhammer40k_ai/engine/reserve_entry_rules.py`
- `src/warhammer40k_ai/engine/decision_handlers/movement.py`
- `src/warhammer40k_ai/engine/game_setup_flow.py`

## Phase 10P: transport embark/disembark and destroyed transport emergency disembark

Modules:

- `engine/transports.py`
- `engine/phases/movement.py`
- `engine/battlefield_state.py`

Objects:

- `TransportCargoState`
- `EmbarkSelection`
- `DisembarkSelection`
- `DestroyedTransportDisembark`

Invariants:

- Embark is battlefield removal into transport cargo;
- Disembark is battlefield placement from transport cargo;
- neither Embark nor Disembark is a Movement phase action;
- embarked units are not placed units and cannot be selected for Normal Move;
- Disembark validates placement, terrain endpoint, Engagement Range setup restriction, and coherency;
- transport capacity and model/unit restrictions are data-driven;
- destroyed transports force emergency disembark or destruction according to rules.

Required tests:

- Embark removes placed models and emits removal records;
- embarked unit is unavailable for Movement unit selection;
- Disembark places models and emits placement records;
- illegal Disembark fails without mutation;
- destroyed transport disembark handles illegal placement consequences;
- capacity validation fails explicitly.

CORE V1 relevant areas:

- `src/warhammer40k_ai/engine/decision_handlers/movement.py`
- `tests/rules/test_core_transport_movement_phase.py`

## Phase 10Q: Aircraft and Hover movement/reserve behavior

Modules:

- `engine/aircraft.py`
- `engine/phases/movement.py`
- `engine/reserves.py`
- `geometry/pathing.py`

Objects:

- `AircraftMovementPolicy`
- `AircraftReserveTransition`
- `HoverModeState`

Invariants:

- `AIRCRAFT` have special pivot and movement behavior;
- `AIRCRAFT` that leave the battlefield transition into reserves where rules permit;
- `HOVER` mode changes movement policy;
- other models' movement around `AIRCRAFT` follows the aircraft movement policy;
- aircraft restrictions in Charge/Fight are exposed for later phases.

Required tests:

- aircraft pivot policy uses 0" in generic pivot accounting;
- aircraft reserve transition emits removal/placement records as appropriate;
- hover state changes movement policy;
- aircraft setup/arrival validates battlefield and terrain restrictions.

CORE V1 relevant areas:

- aircraft movement/reserve handling;
- reserve-entry tests;
- movement pathing tests.

## Phase 10R: triggered and surge movement foundation

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
- each unit can only make one surge move per phase unless a rule says otherwise;
- Battle-shocked units cannot make surge moves unless a rule says otherwise;
- units within Engagement Range cannot make surge moves unless a rule says otherwise;
- triggered movement records trigger timing and source rule;
- triggered movement consumes pathing, terrain, pivot, and coherency validation.

Required tests:

- Blood-Surge-like movement is represented as triggered movement;
- surge movement cannot occur if Battle-shocked;
- surge movement cannot occur while within Engagement Range;
- one surge move per phase is enforced;
- triggered movement emits displacement records;
- triggered movement records source rule and trigger timing;
- triggered movement does not appear in `SELECT_MOVEMENT_ACTION`.

CORE V1 relevant areas:

- `src/warhammer40k_ai/engine/decision_handlers/movement.py`
- surge/reactive movement tests.

## Phase 10S: Movement phase completion gate

This phase is a compliance gate for the full Movement phase.

Invariants:

- Move Units step completes with all eligible units either moved or remaining stationary;
- action options are Engagement Range-aware;
- failed movement rolls back state;
- all successful movement emits transition records;
- coherency is enforced at the end of every move;
- Reinforcements step starts only after Move Units completion;
- Movement phase advances only after Reinforcements and unresolved mandatory placements are complete;
- movement phase events and replay payloads are deterministic.

Required tests:

- full Move Units step completes;
- Advance/Fall Back/Normal/Remain Stationary interact correctly;
- failed movement does not mutate state;
- Reinforcements occurs after Move Units;
- Movement phase exits to Shooting only when all movement-step work is complete.

## Phase 10T: movement/pathing/terrain profiling and hotspot budget gate

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

---

# Mission pack, objectives, Command phase, and scoring

## Phase 11A: Chapter Approved 2025-26 mission pack data

This phase brings in Chapter Approved 2025-26 mission data: mission sequence, deployment maps, objective marker positions, mission pool, mission decks, secondary mission cards, Challenger cards, terrain layout templates, and tournament scoring caps.

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

- Chapter Approved 2025-26 is source-linked and versioned;
- mission setup order is data, not driver-local enum arithmetic;
- deployment zones are geometry objects tied to deployment maps;
- objective marker positions are source-defined and use center-point measurement;
- Chapter Approved objective markers are flat 40mm markers and do not impede movement/placement;
- terrain layout templates are data and can instantiate pregenerated terrain pieces;
- tournament mission pool is deterministic and replay-facing;
- Fixed/Tactical/Challenger card behavior remains hidden/public-safe.

Required tests:

- Chapter Approved mission sequence round-trips;
- deployment map geometry round-trips;
- objective marker positions round-trip;
- objective marker terrain/movement policy is flat/non-blocking for Chapter Approved;
- terrain layout template instantiates deterministic terrain features;
- mission pool selection is deterministic;
- hidden Tactical/Fixed state does not leak to opponent public payload.

CORE V1 relevant areas:

- mission/deployment map data;
- setup/deployment tests;
- scoring tests;
- terrain layout fixtures.

## Phase 11B: objective control geometry and mission objective model

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
- Battle-shocked units have OC 0;
- objective markers use mission-defined positions and control radius;
- objective marker terrain interactions are descriptor-driven;
- objective control results are replay-safe.

Required tests:

- objective control sums OC by player;
- Battle-shocked unit contributes OC 0;
- contested objective has deterministic result;
- terrain objective policy is explicit unsupported until implemented;
- objective control payloads round-trip.

## Phase 11C: Command phase body: Command step, CP, Battle-shock, and OC updates

Modules:

- `engine/phases/command.py`
- `engine/battle_shock.py`
- `engine/command_points.py`
- `engine/objective_control.py`

Objects:

- `CommandStepState`
- `CommandPointLedger`
- `BattleShockTestRequest`
- `BattleShockResult`
- `BelowHalfStrengthContext`

Invariants:

- Command phase has Command step then Battle-shock step;
- active player gains CP according to rules/mission policy;
- below-half-strength units create Battle-shock test requests;
- Battle-shock tests are deterministic dice decisions;
- failed Battle-shock marks unit Battle-shocked until the correct cleanup point;
- Battle-shocked units have OC 0 and cannot be selected for Stratagems unless rules permit;
- Command phase scoring hooks run at the correct timing.

Required tests:

- active player gains CP;
- below-half-strength unit emits Battle-shock test request;
- failed Battle-shock persists and changes OC to 0;
- passed Battle-shock avoids Battle-shocked state;
- Command phase stops at required dice/decision requests.

## Phase 11D: mission actions, primary/secondary scoring, and end-of-turn cleanup

Modules:

- `engine/scoring.py`
- `engine/missions.py`
- `engine/actions.py`
- `engine/turn_cleanup.py`
- `engine/unit_coherency.py`

Objects:

- `MissionScoringPolicy`
- `VictoryPointLedger`
- `MissionActionState`
- `EndTurnCleanupState`
- `CoherencyCleanupRemoval`

Invariants:

- scoring is mission-pack data, not hard-coded phase logic;
- mission Actions have start timing, eligible units, interruption conditions, completion timing, and scoring effects;
- Fixed and Tactical secondary scoring use hidden/public payload boundaries;
- objective control feeds scoring;
- end-of-turn coherency cleanup removes models until each affected unit has one coherent group;
- coherency-cleanup removals count as destroyed but do not trigger destroyed-model rules;
- game end after configured battle rounds produces winner/draw result.

Required tests:

- primary scoring at correct timing;
- Fixed secondary scoring preserves hidden/public boundaries;
- Tactical secondary draw/score/discard flow works;
- mission Action can start, complete, be interrupted, and score;
- end-of-turn coherency cleanup removes models without destroyed triggers;
- victory point ledger round-trips;
- game ends after configured battle rounds.

## Phase 11E: battle-round/game-end scoring and winner determination

Invariants:

- game length is mission/ruleset data;
- end-of-round and end-of-game scoring windows are explicit;
- final VP ledger determines winner/draw;
- Chapter Approved 100VP cap and per-source caps are represented in scoring policy;
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

Modules:

- `engine/timing_windows.py`
- `engine/reaction_queue.py`
- `engine/effects.py`

Objects:

- `TimingWindow`
- `ReactionWindow`
- `PersistingEffect`
- `EffectExpiration`
- `TriggeredDecisionRequest`
- `SequencingDecision`

Invariants:

- out-of-phase rules use typed timing windows;
- reaction windows can block and resume parent phase execution;
- persisting effects expire at deterministic lifecycle points;
- sequencing conflicts are represented explicitly;
- effect payloads are replay-safe;
- no rule handler mutates state outside its owning timing window.

Required tests:

- reaction window emits interrupt-style decision request;
- parent phase resumes after reaction resolution;
- persisting effect expires at correct phase/turn/battle-round point;
- unsupported timing windows fail explicitly;
- sequencing conflict creates a deterministic resolver decision when needed.

CORE V1 relevant areas:

- `engine/combat_timing.py`
- reactive decision handling;
- phase/reaction tests.

## Phase 12B: Command Point ledger and Stratagem framework

Modules:

- `engine/stratagems.py`
- `engine/command_points.py`
- `engine/timing_windows.py`

Objects:

- `CommandPointLedger`
- `StratagemUseRequest`
- `StratagemUseRecord`
- `StratagemEligibilityContext`
- `StratagemTargetBinding`

Invariants:

- Stratagems consume CP through a ledger;
- once-per-phase/turn/battle restrictions are enforced;
- Battle-shocked units cannot be selected for Stratagems unless rules permit;
- target binding is typed and validated before a Stratagem option appears;
- Stratagem timing is descriptor-driven;
- Stratagem effects execute only through registered handlers;
- invalid or missing target context suppresses the option rather than emitting illegal choices.

Required tests:

- insufficient CP hides/rejects Stratagem;
- repeated-use restriction works;
- Battle-shocked unit eligibility restriction works;
- target-required Stratagem does not appear without legal target binding;
- Stratagem use round-trips in replay.

CORE V1 relevant areas:

- `src/warhammer40k_ai/engine/stratagem_ledger.py`
- stratagem tests;
- headless tool-action context audits.

## Phase 12C: Core Stratagems

Initial supported Core Stratagem groups:

- Command Re-roll;
- Insane Bravery;
- Fire Overwatch;
- Go to Ground;
- Smokescreen where applicable;
- Heroic Intervention;
- Counter-offensive;
- Epic Challenge;
- Grenade;
- Tank Shock;
- Rapid Ingress;
- New Orders from Chapter Approved Tactical missions.

Invariants:

- each Core Stratagem has a timing descriptor;
- each Core Stratagem has explicit target-binding rules;
- each Core Stratagem consumes CP and records use;
- damage/dice Stratagems use deterministic dice/replay plumbing;
- unsupported Core Stratagems remain explicit unsupported descriptors.

Required tests:

- one legal use per supported timing window;
- CP consumption and repeat-use restriction;
- target-binding validation;
- dice/damage records for relevant Stratagems;
- unsupported Core Stratagems fail explicitly.

## Phase 12D: ability handler registry and keyword-gated rule execution

Modules:

- `engine/abilities.py`
- `rules/timing.py`
- `core/datasheet.py`
- `core/weapon_profiles.py`

Objects:

- `AbilityHandlerRegistry`
- `AbilityExecutionContext`
- `AbilityResolutionResult`
- `KeywordGate`

Invariants:

- ability descriptors are inert until a registered handler executes them;
- handlers declare timing windows and input requirements;
- keyword-gated effects use canonical keywords;
- unsupported ability descriptors remain unsupported rather than fallback-parsed;
- ability execution records source IDs and replay payloads.

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
- `BenefitOfCoverResult`

Invariants:

- true line of sight is modeled from model volume/pose;
- model visible, unit visible, model fully visible, and unit fully visible are separate results;
- terrain visibility rules are descriptor-driven;
- Ruins and Woods visibility policies are explicit;
- Benefit of Cover is a policy result, not a shooting side effect;
- cover eligibility is visible in attack allocation context;
- LoS and cover checks use spatial index/cache revision data;
- LoS witness/debug payloads are replay-safe.

Required tests:

- terrain visibility fixture can block LoS deterministically;
- Ruins wall/floor interactions are represented in LoS context;
- Woods visibility behavior is represented;
- model volume participates in visibility checks;
- terrain visibility cache key changes when terrain revision changes;
- Benefit of Cover policy result round-trips;
- LoS witness/debug payload round-trips.

CORE V1 relevant areas:

- `src/warhammer40k_ai/battlefield/terrain_visibility.py`
- `src/warhammer40k_ai/battlefield/terrain_cover.py`
- `src/warhammer40k_ai/battlefield/map.py`
- `tests/rules/test_line_of_sight.py`

## Phase 13B: Shooting phase target selection and weapon declaration

Modules:

- `engine/phases/shooting.py`
- `engine/shooting_targets.py`
- `engine/weapon_declaration.py`

Objects:

- `ShootingPhaseState`
- `ShootingUnitSelection`
- `ShootingTargetCandidate`
- `WeaponDeclaration`
- `RangedAttackPool`

Invariants:

- eligible shooting units are derived from current state;
- units that Advanced/Fell Back cannot shoot unless a rule permits;
- units locked in combat obey Locked in Combat / Big Guns Never Tire restrictions;
- ranged weapons validate range and visibility;
- attack declarations group by model, weapon, profile, and target;
- Hazardous and one-shot-style requirements are explicit descriptors.

Required tests:

- eligible unit selection;
- Advanced/Fell Back restriction;
- target range/visibility validation;
- weapon declaration payload round-trip;
- invalid target declaration fails without mutation.

## Phase 13C: attack sequence: hit, wound, allocate, save, damage

Modules:

- `engine/attack_sequence.py`
- `engine/damage_allocation.py`
- `engine/saves.py`

Objects:

- `AttackSequence`
- `HitRoll`
- `WoundRoll`
- `AttackAllocation`
- `SavingThrow`
- `DamageApplication`

Invariants:

- attack sequence follows hit, wound, allocate, saving throw, inflict damage;
- modifiers apply through typed modifier stacks;
- invulnerable saves and mortal wounds are distinct;
- damage spillover and excess damage rules are explicit;
- model destruction emits removal records.

Required tests:

- hit/wound/save/damage deterministic dice flow;
- invulnerable save path;
- mortal wound path;
- model destruction emits removal records;
- damage allocation payload round-trips.

## Phase 13D: weapon abilities and shooting modifiers

Initial coverage:

- Assault;
- Heavy;
- Rapid Fire X;
- Sustained Hits X;
- Lethal Hits;
- Devastating Wounds;
- Melta X;
- Torrent;
- Blast;
- Pistol;
- Hazardous;
- Ignores Cover;
- Precision.

Invariants:

- weapon abilities are structured descriptors;
- ability handlers modify the attack sequence only in declared timing windows;
- unsupported weapon ability shapes fail explicitly;
- source IDs are preserved in emitted events.

Required tests:

- each supported weapon ability has at least one focused attack-sequence test;
- unsupported weapon ability descriptor does not execute;
- modifier interactions are deterministic.

## Phase 13E: damage allocation, destroyed models, and destruction reactions

Invariants:

- defender allocates attacks according to rules;
- wounded models must continue receiving damage where applicable;
- destroyed models are removed with removal records;
- destroyed-model reaction windows fire unless the removal cause suppresses them;
- coherency-cleanup removals count as destroyed but do not trigger destroyed rules.

Required tests:

- wounded-model allocation priority;
- destroyed-model removal event;
- destroyed-model reaction timing;
- non-triggering coherency cleanup removal.

## Phase 13F: Shooting phase completion gate

Required tests:

- full Shooting phase can complete for both players;
- shooting consumes visibility, cover, weapon declarations, attack sequence, damage allocation, and removal records;
- invalid declarations do not mutate state;
- shooting phase exits only after all selected/eligible units have resolved or skipped.

---

# Charge and Fight phases

## Phase 14A: Charge phase declaration and charge roll

Invariants:

- eligible charging units are derived from state;
- units that Advanced/Fell Back cannot charge unless a rule permits;
- targets are selected according to ruleset descriptor;
- charge roll is deterministic and replay-facing;
- failed charges do not move models.

## Phase 14B: charge movement, terrain, FLY, and endpoint rules

Invariants:

- charge movement consumes pathing, terrain, pivot, and coherency validation;
- at least one charging model must satisfy the charge endpoint requirement;
- charge may end in Engagement Range according to charge policy;
- charging over terrain and charging with FLY are distinct policies;
- charge movement emits displacement records.

## Phase 14C: fight order, Fights First, and remaining combats

Invariants:

- Fight phase has Fights First then Remaining Combats;
- eligible units are selected in correct order;
- charging units and Fight First effects are represented in fight-order state;
- fight interrupts use typed decision metadata.

## Phase 14D: pile-in, melee attacks, and consolidate

Invariants:

- Pile-in and Consolidate are model displacements, not Movement phase actions;
- Pile-in/Consolidate consume movement/pathing/terrain/coherency validators;
- melee target selection follows engagement/eligibility rules;
- melee attack sequence reuses attack-sequence infrastructure;
- consolidation endpoint rules are explicit.

## Phase 14E: fight-phase Stratagems and melee abilities

Initial coverage:

- Counter-offensive;
- Epic Challenge;
- Fight First;
- fight-on-death;
- melee weapon abilities;
- pile-in/consolidate modifiers.

## Phase 14F: Charge/Fight completion gate

Required tests:

- full Charge phase can complete;
- full Fight phase can complete;
- charge movement, pile-in, and consolidate emit displacement records;
- melee attacks can destroy models;
- fight order is deterministic and replay-safe.

---

# Setup, deployment, reserves, and army construction completion

## Phase 15A: deployment rules and deployment-zone placement

Invariants:

- deployment zones come from mission map;
- Attacker/Defender and deployment order are mission/ruleset policy;
- deployed units validate terrain endpoint, coherency, Engagement Range setup restriction, and model overlap;
- deployment emits placement records.

## Phase 15B: redeployments, Scouts, Infiltrators, and pre-battle abilities

Invariants:

- redeployments occur after deployment and before first turn;
- redeploy is removal + placement, not displacement;
- Scout moves are pre-battle displacements;
- Infiltrators modify setup legality;
- all pre-battle abilities use timing windows and source IDs.

## Phase 15C: reserves declarations, Strategic Reserves limits, and Deep Strike setup

Invariants:

- Strategic Reserves limits are validated during setup;
- Deep Strike and similar abilities are setup/arrival mechanisms;
- reserve declarations are replay-facing decisions;
- illegal reserve declarations fail before battle starts.

## Phase 15D: leader attachment, enhancements, and army construction completion

Invariants:

- Leader attachment restrictions are validated before battle;
- enhancements are validated against character/faction/detachment restrictions;
- faction/detachment army rules become active after mustering;
- invalid list construction fails before lifecycle enters setup play.

## Phase 15E: pre-battle/setup completion gate

Required tests:

- full setup sequence can complete without deterministic placement bridge;
- deployment, redeploy, reserves, transports, leaders, and pre-battle abilities are resolved through DecisionRequests;
- battle starts only after setup legality is complete.

---

# Wahapedia data ingestion, language parsing, and content coverage

## Phase 16A: Wahapedia source mirror and CSV-to-JSON ETL

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

- downloaded CSV/source files are stored with checksum, source date, and upstream identity;
- generated JSON is deterministic from source inputs;
- HTML tags are stripped or converted to explicit structured markup before catalog ingestion;
- normalized text preserves source spans, paragraph/list boundaries, dice expressions, keywords, and distance expressions;
- smart quotes, dashes, non-breaking spaces, HTML entities, and embedded links are normalized once;
- raw HTML is never consumed by runtime engine code;
- generated JSON includes `raw_text`, `normalized_text`, and source-row provenance where needed;
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

## Phase 16B: canonical catalog generation from Wahapedia data

Modules:

- `tools/build_catalog.py`
- `core/datasheet.py`
- `core/army_catalog.py`
- `core/faction.py`
- `core/detachment.py`
- `core/enhancement.py`
- `core/stratagem.py`

Objects:

- `CanonicalCatalogPackage`
- `DatasheetCatalogRecord`
- `WargearCatalogRecord`
- `WeaponProfileCatalogRecord`
- `FactionCatalogRecord`
- `DetachmentCatalogRecord`
- `EnhancementCatalogRecord`
- `StratagemCatalogRecord`

Invariants:

- all datasheets, model profiles, unit composition, wargear options, base sizes, keywords, and faction keywords come from source-linked catalog records;
- all factions and detachments are catalog records, not hand-authored fixture-only data;
- all stratagems and enhancements are source-linked descriptors;
- generated catalog package hash is deterministic;
- catalog generation is idempotent and diffable;
- missing geometry/height/base overrides are explicit import blockers or unsupported descriptors, not silent defaults.

Required tests:

- representative datasheets generate deterministic catalog records;
- model profiles preserve base-size/source information;
- wargear options and weapon profiles preserve stable IDs;
- faction/detachment/enhancement/stratagem records round-trip;
- package hash changes on source-data drift;
- unsupported rows are reported and cannot be instantiated accidentally.

## Phase 16C: rule language intermediate representation

This is the foundation for handling army rules, detachment rules, stratagems, enhancements, datasheet abilities, and wargear abilities via language parsing rather than hard-coding named items.

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
- model/unit destruction trigger;
- once per phase/turn/battle restriction.

Required tests:

- normalized source text compiles to stable IR;
- unsupported clauses preserve source span and reason;
- grammar/parser changes are snapshot tested;
- multiple equivalent textual forms normalize to same IR where intended;
- runtime cannot execute uncompiled raw text.

## Phase 16D: generic rule execution handlers

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
- execution emits source-linked events;
- unsupported IR cannot execute;
- specific named handlers are allowed only when backed by source-linked tests and an unsupported generic shape is documented.

Required tests:

- generic modifier rule executes;
- generic reroll permission executes;
- generic VP scoring rule executes;
- generic Stratagem target binding executes;
- unsupported IR produces typed unsupported status.

## Phase 16E: faction, detachment, enhancement, and army-rule coverage

Invariants:

- every faction has a source-linked army rule descriptor;
- every detachment has source-linked detachment rule, enhancement, and Stratagem descriptors;
- language parser produces generic IR where possible;
- unique imperative rules are isolated behind source-linked named handlers;
- coverage report groups implemented, generic-supported, named-handler-required, and unsupported rules.

Required tests:

- faction army rules load for every faction;
- detachment rules load for every detachment;
- enhancements validate eligibility and execute generic effects where supported;
- detachment Stratagems validate timing and target bindings;
- unsupported rule report is generated and non-empty only with approved reasons.

## Phase 16F: broad weapon/wargear/datasheet ability coverage

Invariants:

- wargear abilities are linked only to selected wargear;
- unselected wargear never grants rules;
- selected wargear payload drift is rejected;
- datasheet abilities and weapon abilities use source-linked descriptors and handlers;
- all imported behavior has tests or explicit unsupported status.

## Phase 16G: source-content coverage and unsupported-descriptor audit

Required outputs:

- coverage report for datasheets, abilities, wargear, detachments, enhancements, Stratagems, and army rules;
- list of unsupported descriptors grouped by reason;
- static audit that runtime code does not parse raw source text;
- CI artifact with package hashes and coverage totals.

---

# Human UI, replay, and network

## Phase 17A: local CLI/human DecisionRecord entry

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

## Phase 17B: replay inspection and deterministic replay runner

Invariants:

- replay can load snapshot + event/decision tail;
- replay can step forward deterministically;
- replay drift is detected and reported;
- replay can export human-readable decision/event traces;
- replay can export training-friendly DecisionRecord corpora.

## Phase 17C: local visual game UI

Invariants:

- UI displays battlefield, terrain, units, objectives, phase state, and pending decisions;
- UI submits only `DecisionResult`s;
- UI can visualize movement paths, LoS witnesses, attack allocation, scoring, and Stratagem windows;
- UI never owns authoritative state progression.

## Phase 17D: network/server-authoritative play

Invariants:

- server owns authoritative lifecycle and validation;
- clients render public state and submit decisions;
- hidden information remains hidden from opponent clients;
- network resync preserves replay hash/state hash.

---

# Profiling, AI orchestration, and corpus generation

## Phase 18A: full-game performance profiling, hotspot benchmarks, and throughput budgets

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

## Phase 18B: legal-candidate generation and action-space masking

Invariants:

- every AI candidate is generated from a `DecisionRequest`;
- candidate generation never bypasses authoritative validation;
- illegal candidates are masked before ranking;
- candidate payloads include enough context for training and replay diagnostics;
- bounded search budgets are deterministic and report timeout/skip reasons.

## Phase 18C: hierarchical AI policy orchestration: General, Commanders, Rankers

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

## Phase 18D: headless self-play and DecisionRecord corpus export

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

## Phase 18E: training-data, reward annotation, and evaluation pipeline

Invariants:

- reward profiles are explicit and versioned;
- generated corpora include game result, VP deltas, action context, legal mask, chosen action, and policy metadata;
- evaluation can compare policies on fixed seed/matchup batches;
- training data schema is stable and validated.

---

# Full-game gates

## Phase 19A: full-game rules-compliance matrix

Create a machine-readable coverage matrix mapping 10e Core Rules sections to implementation modules and tests.

Required coverage areas:

- core concepts;
- datasheets and keywords;
- dice and rerolls;
- sequencing;
- Command phase;
- Battle-shock;
- Movement phase;
- terrain movement;
- transports;
- Strategic Reserves;
- Aircraft;
- Shooting phase;
- attack sequence;
- weapon abilities;
- Charge phase;
- Fight phase;
- Stratagems;
- missions;
- objective control;
- scoring;
- terrain visibility and cover;
- deployment and pre-battle abilities;
- faction/detachment/enhancement rules;
- Chapter Approved mission pack.

## Phase 19B: end-to-end full-game regression suite

Required tests:

- full two-player game completes through final scoring;
- replay round-trip at multiple battle rounds;
- no hidden information leaks;
- deterministic same-seed replay;
- multiple terrain layouts;
- multiple army archetypes;
- multiple mission packs.

## Phase 19C: balance/performance/stability soak

Required runs:

- local AI-vs-AI corpus generation;
- long-running replay validation;
- profiling hotspot report;
- unsupported descriptor report;
- crash/failure triage report.

## Phase 19D: release gate for complete 10e-compatible CORE V2

Exit criteria:

- all Core Rules coverage rows are either implemented or explicitly unsupported with reason;
- all Chapter Approved 2025-26 setup/scoring/terrain/deployment layout rows are implemented or explicitly unsupported with reason;
- full-game regression suite passes;
- headless throughput budget passes;
- replay determinism passes;
- source-content coverage report is generated;
- human CLI can complete a game;
- AI self-play can complete many games;
- UI can inspect and play a local game;
- network authoritative mode can synchronize state and decisions.

---

# 11th Edition preparation

## Phase 20A: edition-diff descriptor registry

Modules:

- `core/ruleset_descriptor.py`
- `rules/edition_diff.py`
- `rules/source_catalog.py`

Objects:

- `EditionDiff`
- `RulesetCompatibilityReport`
- `RulesetDescriptorRegistry`

Invariants:

- 10e and 11e preview/official rulesets are separate descriptors;
- preview rules are marked preview/unstable and source-linked;
- no 11e behavior is hard-coded into 10e handlers;
- edition differences live in descriptors, policy tables, and explicit handler switches.

Required tests:

- 10e and 11e descriptors hash differently;
- edition-specific Engagement Range/coherency/movement policies do not drift into each other;
- unsupported 11e preview behavior fails explicitly.

## Phase 20B: 11e data import and migration harness

Invariants:

- 11e source data imports through the same ETL pipeline;
- 11e catalog can coexist with 10e catalog;
- migration reports changed datasheets, keywords, weapon profiles, Stratagems, missions, terrain, and core rules;
- handlers declare which editions they support.

## Phase 20C: 11e gameplay compatibility slices

Implement 11e-specific behavior only after descriptors/source data are pinned.

Candidate areas:

- revised Engagement Range;
- revised Unit Coherency;
- revised movement/terrain/FLY behavior;
- revised charge/fight flow;
- revised mission pack;
- revised datasheets and faction rules.

## Phase 20D: dual-edition test matrix

Required tests:

- representative 10e game still passes after 11e support lands;
- representative 11e preview/official game can run where implemented;
- edition-incompatible rule paths fail explicitly;
- content packages cannot be mixed across editions accidentally.

---

# Rules coverage map

| Rules area | Planned phase(s) |
|---|---|
| Dice, rerolls, roll-offs | 1, 10M, 12C, 13C, 14A |
| Datasheets and keywords | 9A, 9C, 16A-16G |
| Army mustering | 9C, 15D, 16B |
| Setup sequence | 9B, 11A, 15A-15E |
| Deployment zones | 11A, 15A |
| Redeployments | 10D, 15B |
| Engagement Range | 10G, 10L, 10M, 10N, 14B |
| Unit Coherency | 10G/10H descriptors, 10K runtime, 11D cleanup |
| Terrain movement | 10F, 10H, 10I |
| Terrain visibility/cover | 13A |
| Movement phase Move Units | 10B-10S |
| Movement phase Reinforcements | 10O |
| Transports | 10P |
| Aircraft | 10Q |
| Command phase | 11C |
| Battle-shock | 11C, 12B |
| Mission scoring | 11A-11E |
| Stratagems | 12B, 12C, 16E |
| Shooting phase | 13A-13F |
| Weapon abilities | 8D, 13D, 16F |
| Charge phase | 14A, 14B |
| Fight phase | 14C-14F |
| Leader/attached units | 6, 15D, 16A |
| Faction/detachment/enhancement rules | 16C-16F |
| Chapter Approved 2025-26 | 11A, 11D, 11E, 15A, 19A |
| Human CLI/UI | 17A, 17C |
| Network play | 17D |
| Replay | 17B, all state-changing phases |
| AI/headless self-play | 18B-18E |
| Performance budgets | 10T, 18A |
| 11e preparation | 20A-20D |
