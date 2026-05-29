# CORE V2 Architecture Build Order

This document is the build-order roadmap for reconstructing the Warhammer 40,000 CORE V2 engine after the completed Phase 1-10V work.

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

Everything through **Phase 11C** is treated as implemented at the time this file was updated. Phase 11D is the next build slice.

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
| 10K | Complete | Precise movement distance, straight-line segments, and pivot costs |
| 10L | Complete | Unit coherency runtime validation and movement rollback |
| 10M | Complete | Engagement-aware Movement action options and Normal Move finalization |
| 10N | Complete | Advance action, dice, rerolls, and advanced-state restrictions |
| 10O | Complete | Fall Back action and Desperate Escape resolution |
| 10P | Complete | Reinforcements, Strategic Reserves, Deep Strike, and reserve placement |
| 10Q | Complete | Transport Embark/Disembark, Firing Deck, and destroyed transport emergency disembark |
| 10R | Complete | Aircraft and Hover movement/reserve behavior |
| 10S | Complete | Triggered and surge movement foundation |
| 10T | Complete | Movement phase completion gate |
| 10U | Complete | Movement/pathing/terrain profiling and hotspot budget gate |
| 10V | Complete | Movement audit hardening and deferred-wiring contracts |
| 11A | Complete | Chapter Approved 2025-26 mission pack data |
| 11B | Complete | Objective control geometry and mission objective model |
| 11C | Complete | Command phase body: Command step, CP, Battle-shock, and OC updates |

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

# Core Rules audit coverage additions

This section records the post-reroll Core Rules audit. It exists because missing a foundational rule, such as the reroll order and one-reroll-per-die restriction, can corrupt every later phase that consumes dice, attacks, movement, or scoring.

Rules audited against the 10e Core Rules page are assigned to explicit future phases below. If a phase implements a mechanic that depends on one of these rules, it must either consume the owning phase's typed service or fail explicitly until that service exists.

| Core Rules area | Required roadmap owner |
|---|---|
| D3 conversion, multi-dice expressions, roll-offs, reroll order, one-reroll-per-die, unmodified result semantics | Phase 10J |
| Distance predicates including within, wholly within, more than, horizontal-only reserve distances, closest-points measurement, base-as-part-of-model visibility | Phase 10J.1, 13A, 15A |
| Characteristic post-modifier caps/floors for Move, Toughness, Save, Leadership, Objective Control, Range, Attacks, WS, BS, Strength, AP, and Damage | Phase 10J.1, 13C, 16B |
| Roll-offs for mission/setup/sequencing, including no rerolls or modifiers and repeat ties | Phase 10J, 12A, 15A |
| Sequencing conflicts: active player chooses during battle, roll-off decides before/after battle or start/end battle round | Phase 12A |
| Persisting effects through Embark/Disembark and Attached-unit splits | Phase 12A, 12D, 15D |
| Out-of-phase actions: perform only the specified action and do not trigger other rules normally used in that phase | Phase 12A, 12C, 12D |
| Starting Strength, Below Half-strength, Battle-shock, CP gain cap, and Battle-shocked restrictions | Phase 11C |
| Attached-unit Toughness, allocation protection for Characters, split timing, destroyed-unit triggers and keywords | Phase 13E, 15D |
| Objective marker placement, movement over objective markers, no endpoint on objective markers, 3"/5" range, control timing | Phase 11A, 11B, 11C |
| Fast dice rolling constraints, including no fast dice for random damage where order matters | Phase 13C, 18A |
| Full common weapon ability list from Core Rules | Phase 13D |
| Transports: Firing Deck, Embark, Disembark, Destroyed Transport, Emergency Disembarkation | Phase 10Q, 13B, 13E |
| Strategic Reserves limits, turn restrictions, horizontal setup distances, edge/deployment-zone restrictions, end-of-battle destroyed | Phase 10P, 11F, 15C |
| Aircraft movement, minimum move, pivot, reserve transition, movement of other models, charge/fight restrictions | Phase 10R, 14B, 14D |
| Terrain engagement exceptions for Barricades/Fuel Pipes in Charge and Fight phases | Phase 14B, 14D |
| Terrain visibility/cover including Woods, Ruins, Plunging Fire, Benefit of Cover non-stacking and AP 0 / 3+ save exception | Phase 13A, 13C |
| Muster army restrictions: battle size, faction, detachment restrictions, rule of three/six, Enhancements, Epic Heroes, Warlord, Dedicated Transport occupancy | Phase 15D |
| Mission setup order, attacker/defender, battle formations secrecy/public reveal, terrain/objective/deployment maps | Phase 11A, 15A, 15C, 15E |

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
- objective markers are 40mm markers by default, can be moved over as if not there, and cannot be ended on top of;
- post-modifier Move and Toughness cannot be less than 1;
- Save cannot become 1+ or better;
- Leadership cannot become better than 4+ or worse than 9+;
- Objective Control cannot be less than 0;
- ranged weapon Range, Attacks, Strength, and Damage cannot be less than 1 unless a rule explicitly permits Damage 0;
- WS and BS cannot become 1+ or better;
- AP cannot become worse than 0;
- all caps/floors are applied after modifier stacking and before result consumption.

Required tests:

- closest-base distance and baseless-model distance work;
- within, wholly within, more-than, and horizontal-only predicates evaluate correctly;
- objective marker range/control predicates use 3"/5";
- objective marker endpoint overlap is rejected;
- each characteristic cap/floor is enforced after modifiers;
- Damage can become 0 only when an explicit rule permits it;
- distance predicate payloads round-trip without object reprs.

CORE V1 relevant areas:

- `src/warhammer40k_ai/utility/calcs.py`
- distance predicate tests
- objective marker / deployment / reserve placement tests

## Phase 10K: precise movement distance, straight-line segments, and pivot costs

Status: Complete.

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
- `AIRCRAFT` pivot cost is 0" in generic pivot accounting, with aircraft-specific movement owned by Phase 10R;
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

## Phase 10L: unit coherency runtime validation and movement rollback

Status: Complete.

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
- Normal Move consumes precise distance, pivot, terrain, pathing, and coherency validators;
- Normal Move movement-distance witnesses must use a model/rules-aware `PivotCostPolicy` derived from `MovementLegalityContext`, not a default policy;
- Normal Move cannot end on another model, embedded in a wall/floor/terrain volume without an explicit legal endpoint, outside the battlefield, or out of coherency;
- Normal Move emits displacement records only after all validators pass;
- Advance, Fall Back, Charge, Pile-in, Consolidate, Scout, and triggered movement must consume the same movement-distance and terrain-legality infrastructure instead of implementing independent distance accounting.

Required tests:

- action options outside Engagement Range are Remain Stationary, Normal Move, Advance;
- action options inside Engagement Range are Remain Stationary, Fall Back;
- Normal Move validates pathing, terrain, pivot cost, and coherency;
- Normal Move for a non-round `VEHICLE`/`MONSTER` consumes the 2" pivot cost when its path pivots;
- Normal Move for a round-base large flying-stem/hover-stand `VEHICLE` consumes the 2" pivot cost when its path pivots;
- Normal Move for `AIRCRAFT` uses the aircraft pivot policy;
- Normal Move replay payload rejects movement-distance witness drift if pivot policy classification is wrong;
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
- moving over enemy models during Fall Back requires Desperate Escape tests unless the model is `TITANIC` or can `FLY`;
- Battle-shocked units selected to Fall Back require Desperate Escape tests for every model;
- Desperate Escape rolls of 1-2 destroy one model from the falling-back unit, selected by the controlling player;
- post-destruction Fall Back endpoint coherency is validated against the surviving models before any battlefield mutation;
- if Desperate Escape destroys every model in the falling-back unit, removal records remain authoritative and no stale `FellBackUnitState` is recorded;
- unresolved Desperate Escape requirements cannot emit Fall Back transition records;
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
- survivor coherency is revalidated after Desperate Escape destruction selection;
- Desperate Escape destruction can make an otherwise incoherent attempted endpoint legal;
- all-model Desperate Escape destruction round-trips through lifecycle replay without stale Fell Back state;
- unresolved Desperate Escape requirements cannot emit transition batches;
- Fall Back emits displacement and removal records where applicable.

CORE V1 relevant areas:

- `src/warhammer40k_ai/engine/decision_handlers/movement.py`
- `src/warhammer40k_ai/pathing/rules_profile.py`
- `src/warhammer40k_ai/pathing/validation.py`

## Phase 10P: Reinforcements, Strategic Reserves, Deep Strike, and reserve placement

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

- Movement phase has Move Units then Reinforcements;
- `REINFORCEMENTS` is a phase step, not a placement kind;
- reserve placement uses placement records, not displacement records;
- all Reserves units not set up on the battlefield when the battle ends count as destroyed;
- Reserves units set up in the Reinforcements step count as having made a Normal move that turn and cannot move further in that phase;
- any specified enemy-distance requirement for setting up Reserves applies to horizontal distance unless the source rule says otherwise;
- Strategic Reserves are a subset of Reserves, while Deep Strike and other reserve-like abilities keep their own setup rules;
- Strategic Reserves declarations exclude `FORTIFICATIONS` and enforce the battle-size points limit, including embarked units inside transports placed into Strategic Reserves;
- Strategic Reserves cannot arrive in battle round 1;
- Strategic Reserves arriving in battle round 2 must be wholly within 6" of a battlefield edge and not within the enemy deployment zone;
- Strategic Reserves arriving from battle round 3 onward must be wholly within 6" of a battlefield edge;
- Strategic Reserves cannot be set up within 9" horizontally of enemy models;
- Deep Strike units may be placed in Reserves during Declare Battle Formations if every model has Deep Strike;
- Deep Strike placement in the Reinforcements step is more than 9" horizontally from all enemy models;
- a unit arriving from Strategic Reserves with Deep Strike may choose either Strategic Reserves setup rules or Deep Strike setup rules;
- reserve placements validate battlefield edges, enemy distance restrictions, terrain endpoints, coherency, model overlap, and deployment restrictions;
- mandatory arrivals are requeued or fail explicitly according to rules;
- no `PathWitness` is required for placement.

Required tests:

- Movement phase enters Reinforcements after Move Units;
- Deep Strike placement uses `BattlefieldPlacementKind.DEEP_STRIKE`;
- Strategic Reserves placement uses `BattlefieldPlacementKind.STRATEGIC_RESERVES`;
- illegal reserve placement fails without mutating state;
- reserve placement validates coherency and Engagement Range setup restriction;
- reserve placement validates terrain endpoint support;
- Strategic Reserves battle-round-2 edge/enemy-deployment-zone restrictions are enforced;
- Strategic Reserves battle-round-3 edge restrictions are enforced;
- Deep Strike and Strategic Reserves choose the correct placement policy;
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

- destroyed Transport orchestration from actual damage/destruction events is owned by Phase 13E/14D;
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
- Disembark is available only to units that started the Movement phase embarked;
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

This phase adds typed `AIRCRAFT` movement policy, persisted Hover-mode policy switching, lifecycle aircraft reserve transitions, aircraft-aware pathing for other models, and reserve arrival validation through the same placement legality path used by Phase 10P.

Modules:

- `engine/aircraft.py`
- `engine/game_state.py`
- `engine/phases/movement.py`
- `engine/reserves.py`
- `geometry/pathing.py`

Objects:

- `AircraftMovementPolicy`
- `AircraftMinimumMoveResult`
- `AircraftBaseMovementWitness`
- `BasePointDistanceWitness`
- `AircraftReserveTransition`
- `HoverModeState`

Complete foundation scope:

- Aircraft/Hover movement policy;
- aircraft reserve transitions;
- mandatory next-turn reserve arrival metadata;
- aircraft base-geometry minimum-move witness.

Deferred setup consumers:

- Aircraft mandatory reserve declaration during Declare Battle Formations is owned by Phase 15C;
- Hover declaration decisions during Declare Battle Formations are owned by Phase 15C/15E.

Invariants:

- `AIRCRAFT` have special pivot and movement behavior;
- non-Hover `AIRCRAFT` use aircraft-policy movement distance resolution, with no upper Normal Move budget and a default 20" straight-forward witness instead of datasheet `M`;
- non-Hover `AIRCRAFT` minimum-move validation is base-geometry aware: circular bases may use the center-distance shortcut, while oval, rectangular, and other non-circular bases serialize deterministic point-distance witnesses for the pre-pivot movement endpoint;
- non-Hover `AIRCRAFT` that cross a battlefield edge or cannot satisfy minimum move during a Movement phase Normal Move transition into Strategic Reserves through the lifecycle path, while short submitted witnesses remain invalid when a legal 20" move is available;
- aircraft reserve transitions remove the unit from the battlefield, record mandatory next-controller-turn arrival metadata, and complete the movement activation without ordinary displacement records or post-move Embark;
- `HOVER` mode is stored in `GameState`, round-trips through replay payloads, changes movement policy, and uses a Hover-derived 20" Move characteristic for Normal Move and Advance budgets;
- other models' movement around `AIRCRAFT` follows the aircraft movement policy;
- enemy `AIRCRAFT` engagement is tracked separately so non-Aircraft units engaged only by enemy Aircraft can still choose Normal Move or Advance while endpoint validation remains strict;
- aircraft restrictions in Charge/Fight are exposed for later phases.

Required tests:

- aircraft pivot policy uses 0" in generic pivot accounting;
- circular and non-circular Aircraft bases validate the 20" minimum with deterministic base-movement witnesses, and pivot-after-move never contributes to the minimum;
- aircraft reserve transition emits removal/placement records as appropriate;
- Movement phase Normal Move lifecycle transitions edge/minimum-move-unavailable Aircraft into Strategic Reserves;
- central non-Hover Aircraft get a default 20" straight-forward Normal Move witness with no movement-distance budget, and short submitted witnesses are invalid rather than reserve transitions when 20" fits;
- Aircraft transition ReserveState is eligible and required in the controller's next Movement phase only;
- persisted hover state changes movement availability, uses 20"/20"+D6 movement budgets, and disables Aircraft minimum-move/pivot restrictions;
- replay rejects HoverModeState owner/unit/source drift, stale selected Aircraft policy payloads, and stale Aircraft minimum-move witness payloads;
- non-Aircraft units engaged only by enemy Aircraft can choose Normal Move and Advance, but cannot end within enemy Aircraft Engagement Range;
- aircraft setup/arrival validates battlefield and terrain restrictions.

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
- triggered movement consumes pathing, terrain, pivot, and coherency validation.

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
- Reinforcements step starts only after Move Units completion;
- Movement phase advances only after Reinforcements and unresolved mandatory placements are complete;
- movement phase events and replay payloads are deterministic.

Required tests:

- full Move Units step completes;
- Advance/Fall Back/Normal/Remain Stationary interact correctly;
- failed movement does not mutate state;
- Reinforcements occurs after Move Units;
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

- Phase 11A must provide mission deployment-zone geometry to live Reinforcements so battle-round-2 Strategic Reserves pass enemy deployment zones into `resolve_reserve_arrival`;
- Phase 11A/11B must provide instantiated terrain features to live Reinforcements and deployment placement validation, not only resolver tests;
- Phase 11E/11F must call unarrived-reserve destruction at the appropriate game-end or mission-pack deadline;
- Phase 13B must consume Firing Deck selections during Shooting and validate selected weapons against the embarked model's wargear;
- Phase 13E/14D must orchestrate destroyed Transport disembark from real destruction events before removing the Transport model;
- Phase 15D must make attached-unit coherency group-aware by validating the attached rules unit, not a single `UnitPlacement`;
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

## Phase 11A: Chapter Approved 2025-26 mission pack data

Status: Complete.

This phase brings in Chapter Approved 2025-26 mission data: mission sequence, deployment maps, objective marker positions, mission pool, mission decks, secondary mission cards, Challenger cards, terrain layout templates, and tournament scoring caps.

Phase 11A terrain layout import preserves source slot rotations in terrain feature `source_id` metadata for audit/replay provenance. Runtime `TerrainFeatureTemplate` geometry intentionally instantiates the conservative axis-aligned bounding footprint of each rotated slot, with axis-aligned ruins walls/floors inside that footprint. Exact rotated ruin walls, floor polygons, and visibility/pathing polygons are deferred to the terrain/visibility geometry slices rather than treated as complete in Phase 11A.

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
- terrain layout templates are data and can instantiate pregenerated terrain pieces with conservative axis-aligned occupancy footprints;
- live Reinforcements receives mission deployment-zone geometry for reserve placement validation;
- live placement validators receive instantiated terrain features instead of resolver-local test fixtures;
- tournament mission pool is deterministic and replay-facing;
- Fixed/Tactical/Challenger card behavior remains hidden/public-safe.

Required tests:

- Chapter Approved mission sequence round-trips;
- deployment map geometry round-trips;
- objective marker positions round-trip;
- objective marker terrain/movement policy is flat/non-blocking for Chapter Approved;
- terrain layout template instantiates deterministic terrain features;
- live Reinforcements rejects battle-round-2 Strategic Reserves in enemy deployment zones using mission data;
- live Reinforcements rejects illegal terrain endpoints using instantiated terrain layout data;
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
- Battle-shocked units have OC 0;
- objective markers use mission-defined center positions and default 40mm marker geometry unless a mission overrides it;
- models can move over objective markers as if they were not there but cannot end a move on top of them;
- objective marker range is 3" horizontally and 5" vertically unless a mission overrides it;
- objective control updates at the end of every phase and turn;
- objective marker terrain interactions are descriptor-driven;
- objective control results are replay-safe.

Required tests:

- objective control sums OC by player;
- Battle-shocked unit contributes OC 0;
- contested objective has deterministic result;
- terrain objective policy is explicit unsupported until implemented;
- model cannot end on top of objective marker;
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
- failed Battle-shock marks the unit and all its models Battle-shocked until the start of the controlling player's next Command phase;
- Battle-shocked units have OC 0;
- Battle-shocked units require Desperate Escape tests for every model if selected to Fall Back;
- a player cannot use Stratagems to affect their Battle-shocked units unless a rule permits it;
- Starting Strength is recorded at army creation and updated correctly when Attached units split;
- Below Half-strength for single-model units uses remaining wounds less than half the Wounds characteristic; other units use current model count less than half Starting Strength;
- Command phase scoring hooks run at the correct timing.

Required tests:

- both players gain 1CP at the start of each Command phase;
- non-Command CP gain cap of 1CP per battle round is enforced;
- below-half-strength unit emits Battle-shock test request;
- below-Starting-Strength forced test suppresses duplicate Below Half-strength test unless overridden;
- failed Battle-shock persists and changes OC to 0;
- passed Battle-shock avoids Battle-shocked state;
- Battle-shocked unit cannot be targeted by friendly Stratagems by default;
- Starting Strength and Below Half-strength logic works for single-model and multi-model units;
- Attached-unit split recovery restores surviving component units to their original Starting Strength records;
- Command phase stops at required decision requests and resolves non-reroll Battle-shock dice deterministically without a player-choice pause.

## Phase 11D: adapter scaffold and parameterized movement/placement proposal requests

This phase creates the engine-owned contract that allows UI work to proceed in parallel without UI-owned state mutation. It separates finite decision choices, such as selecting a movement action, from parameterized movement and placement proposals, such as per-model endpoints and path witnesses.

This phase does not build a visual UI. It creates the adapter and proposal contracts that a later CLI, local visual UI, network client, or AI policy can consume.

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
- movement proposal payloads include the selected unit, selected movement action, per-model movement data, path witness data, pivot/facing data where applicable, and any required source context;
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
- Reinforcement placement proposal;
- Deep Strike placement proposal;
- Strategic Reserves placement proposal;
- Disembark placement proposal.

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
- golden JSON fixtures cover finite movement action selection, parameterized Normal Move proposal, invalid movement proposal, reserve placement proposal, Disembark placement proposal, and viewer-scoped projection.

CORE V1 relevant areas:

- `src/warhammer40k_ai/engine/decision_handlers/movement.py`
- `src/warhammer40k_ai/pathing/validation.py`
- `src/warhammer40k_ai/pathing/types.py`
- `src/warhammer40k_ai/engine/game_setup_flow.py`
- movement, deployment, reserve, Disembark, replay, UI/headless, and decision-dispatch tests

## Phase 11E: mission actions, primary/secondary scoring, and end-of-turn cleanup

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
- unarrived Reserves destruction resolver is invoked at the mission-defined deadline;
- game end after configured battle rounds produces winner/draw result.

Required tests:

- primary scoring at correct timing;
- Fixed secondary scoring preserves hidden/public boundaries;
- Tactical secondary draw/score/discard flow works;
- mission Action can start, complete, be interrupted, and score;
- end-of-turn coherency cleanup removes models without destroyed triggers;
- unarrived Reserves are destroyed at the configured deadline through the lifecycle hook;
- victory point ledger round-trips;
- game ends after configured battle rounds.

## Phase 11F: battle-round/game-end scoring and winner determination

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
- `engine/sequencing.py`

Objects:

- `TimingWindow`
- `ReactionWindow`
- `PersistingEffect`
- `EffectExpiration`
- `TriggeredDecisionRequest`
- `SequencingDecision`
- `OutOfPhaseActionContext`

Invariants:

- out-of-phase rules use typed timing windows;
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
- sequencing conflict creates a deterministic resolver decision when needed.

CORE V1 relevant areas:

- `engine/combat_timing.py`
- reactive decision handling;
- phase/reaction/persisting-effect tests.

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
- `AIRCRAFT` and `TOWERING` visibility exceptions for Woods/Ruins are explicit;
- Benefit of Cover is a policy result, not a shooting side effect;
- cover eligibility is visible in attack allocation context;
- LoS and cover checks use spatial index/cache revision data;
- LoS witness/debug payloads are replay-safe.

Required tests:

- terrain visibility fixture can block LoS deterministically;
- Ruins wall/floor interactions are represented in LoS context;
- Woods visibility behavior is represented;
- `TOWERING` and `AIRCRAFT` terrain visibility exceptions are represented;
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
- units locked in combat obey Locked in Combat / Big Guns Never Tire / Pistol restrictions;
- Big Guns Never Tire applies the correct Hit-roll penalty unless the attack is made with a Pistol;
- Lone Operative prevents ranged targeting outside its distance gate when applicable;
- ranged weapons validate range and visibility at target selection time;
- a weapon remains resolved against a target selected as visible/in range even if later attacks remove visible/in-range models before resolution;
- attack declarations group by model, weapon, profile, and target;
- Hazardous and one-shot-style requirements are explicit descriptors.

Required tests:

- eligible unit selection;
- Advanced/Fell Back restriction;
- target range/visibility validation;
- Lone Operative targeting gate;
- Locked in Combat, Big Guns Never Tire, and Pistol interactions;
- selected target remains valid for declared weapon resolution after casualties;
- weapon declaration payload round-trip;
- invalid target declaration fails without mutation.

## Phase 13C: attack sequence: hit, wound, allocate, save, damage

Modules:

- `engine/attack_sequence.py`
- `engine/damage_allocation.py`
- `engine/saves.py`
- `engine/dice.py`

Objects:

- `AttackSequence`
- `HitRoll`
- `WoundRoll`
- `AttackAllocation`
- `SavingThrow`
- `MortalWoundApplication`
- `DamageApplication`
- `FastDiceGroup`

Invariants:

- attack sequence follows hit, wound, allocate, saving throw, inflict damage;
- Hit rolls use BS for ranged attacks and WS for melee attacks;
- unmodified Hit roll of 6 is a Critical Hit and always succeeds;
- unmodified Hit roll of 1 always fails;
- Hit roll modifiers are capped at +1/-1;
- Wound roll target number derives from Strength vs Toughness using the 2+/3+/4+/5+/6+ table;
- Critical Wounds and wound-roll modification are explicit attack events;
- the defender allocates attacks one at a time unless fast dice conditions are satisfied;
- wounded models or models already allocated attacks this phase must continue receiving allocations until destroyed or all attacks are resolved/saved;
- armour saves apply AP modifiers and Benefit of Cover where eligible;
- invulnerable saves ignore AP but otherwise follow saving throw rules; the controlling player may choose armour or invulnerable save where both are available;
- mortal wounds are allocated one at a time, do not allow saves, and spill over unless the source rule says remaining mortal wounds are lost;
- mortal wounds from attacks are applied after normal damage from that attacking unit, even if the normal damage was saved;
- Feel No Pain rolls are per lost wound, including mortal wounds, and only one Feel No Pain ability can be used per lost wound;
- normal attack excess damage is lost when a model is destroyed;
- Fast Dice Rolling is allowed only when BS/WS, Strength, AP, Damage, abilities, and target are the same and order cannot affect the result;
- random Damage attacks cannot use fast dice in cases where allocation order can affect destroyed/damaged model outcomes;
- model destruction emits removal records and destruction timing windows.

Required tests:

- hit/wound/save/damage deterministic dice flow;
- Hit roll 6 critical/auto-success and 1 auto-fail;
- Hit modifier cap of +1/-1;
- Wound roll table boundaries;
- armour save, invulnerable save, and cover interaction;
- mortal wound spillover and no-save path;
- Devastating/Hazardous mortal-wound lost-remainder exceptions where applicable;
- Feel No Pain per-wound roll path;
- wounded-model allocation priority;
- fast dice group allowed for identical attacks;
- random damage fast dice is rejected where order matters;
- model destruction emits removal records;
- damage allocation payload round-trips.

## Phase 13D: weapon abilities and shooting/fight modifiers

Initial Core Rules weapon ability coverage:

- Assault;
- Rapid Fire X;
- Ignores Cover;
- Twin-linked;
- Pistol;
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
- Anti-KEYWORD X+.

Invariants:

- weapon abilities are structured descriptors;
- ability handlers modify the attack sequence only in declared timing windows;
- Assault changes shooting eligibility and restricts attacks to Assault weapons after Advance;
- Rapid Fire, Blast, Melta, Heavy, Lance, and Indirect Fire modify characteristics/rolls through typed modifier stacks;
- Twin-linked grants a Wound-roll reroll permission and consumes Phase 10J reroll semantics;
- Pistol modifies Locked-in-Combat targeting and weapon selection restrictions;
- Torrent bypasses Hit rolls and interacts correctly with Indirect Fire restrictions;
- Lethal Hits and Sustained Hits consume Critical Hit events;
- Anti modifies Critical Wound thresholds based on target keywords;
- Precision modifies allocation to visible Character models in Attached units;
- Hazardous tests occur after the unit has resolved all its attacks and allocate mortal wounds to eligible Hazardous-equipped models;
- Devastating Wounds converts damage to mortal wounds and handles allocation timing;
- Extra Attacks weapons are additional melee weapons and their Attacks cannot be modified unless the modifying rule names that weapon;
- unsupported weapon ability shapes fail explicitly;
- source IDs are preserved in emitted events.

Required tests:

- each supported weapon ability has at least one focused attack-sequence test;
- unsupported weapon ability descriptor does not execute;
- modifier interactions are deterministic;
- Twin-linked cannot reroll a Wound roll twice;
- Indirect Fire applies no-visibility hit penalty, unmodified 1-3 fail, and Benefit of Cover;
- Pistol and Big Guns Never Tire restrictions interact correctly;
- Hazardous and Devastating Wounds mortal-wound allocation ordering is correct.

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
- charge movement emits displacement records;
- Barricades/Fuel Pipes opposite-side 2" charge exception is represented as a terrain engagement policy.

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
- consolidation endpoint rules are explicit;
- Barricades/Fuel Pipes opposite-side 2" fight eligibility/attack exception is represented as a terrain engagement policy.

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

## Phase 15D: leader attachment, enhancements, army construction, and roster legality completion

Invariants:

- battle size defines points limit and mission-compatible battlefield expectations;
- army faction is a selected Faction keyword and every included unit must be legal for that faction or an allowed exception;
- detachment selection can impose required/prohibited units and grants detachment rules, Stratagems, and Enhancements;
- the army must include at least one eligible `CHARACTER` model to be Warlord;
- selected Warlord gains the `WARLORD` keyword;
- Rule of Three is enforced for datasheets by name, except BATTLELINE and DEDICATED TRANSPORT allow up to six;
- `EPIC HERO` units are unique and cannot receive Enhancements;
- only `CHARACTER` models can receive Enhancements;
- the army can include at most three Enhancements;
- no unit can have more than one Enhancement;
- each Enhancement must be unique;
- every Dedicated Transport must start the battle with at least one unit embarked or it cannot be deployed and counts as destroyed during the first battle round;
- Leader attachment restrictions are validated before battle;
- each Bodyguard unit can have at most one Leader attached;
- while attached, the Attached unit is treated as one unit for rules purposes except destroyed-unit triggers;
- coherency for an Attached unit is validated over the attached rules unit's alive models, not per component `UnitPlacement`;
- attacks against Attached units use Bodyguard Toughness until the attacking unit resolves all attacks;
- attacks cannot be allocated to Character models in Attached units until the Bodyguard is destroyed unless a rule such as Precision permits it;
- when Bodyguard or Leader components are destroyed, surviving units split at the correct timing and recover original Starting Strength;
- destroyed-unit triggers for Attached-unit components use only the destroyed component's own keywords.

Required tests:

- Rule of Three and BATTLELINE/Dedicated Transport exceptions;
- Epic Hero uniqueness and Enhancement denial;
- Enhancement count, uniqueness, Character-only, and one-per-unit restrictions;
- Dedicated Transport empty-at-start consequence;
- Leader/Bodyguard legal attachment and one-Leader-per-Bodyguard enforcement;
- Attached-unit coherency uses `UnitGroup.alive_models()`/group-aware placement data across Leader and Bodyguard models;
- Attached-unit Toughness and Character allocation protection;
- Attached-unit split timing after attacks resolve;
- destroyed-unit trigger identity for Leader vs Bodyguard components.

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
- Aura source, range, eligible-target, and effect clauses;
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
- dice, D3, roll-offs, random characteristics, rerolls, and modifiers;
- sequencing;
- Command phase;
- Battle-shock;
- Movement phase;
- terrain movement;
- transports;
- Strategic Reserves;
- Aircraft;
- Shooting phase, target declaration, locked in combat, Big Guns Never Tire, Pistol, Lone Operative;
- attack sequence, fast dice, mortal wounds, Feel No Pain, Deadly Demise, and damage allocation;
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
| Dice, rerolls, roll-offs | 1, 10J, 10N, 12C, 13C, 14A |
| Datasheets and keywords | 9A, 9C, 16A-16G |
| Army mustering | 9C, 15D, 16B |
| Setup sequence | 9B, 11A, 15A-15E |
| Deployment zones | 11A, 15A |
| Redeployments | 10D, 15B |
| Engagement Range | 10G, 10M, 10N, 10O, 14B |
| Unit Coherency | 10G/10H descriptors, 10L runtime, 11E cleanup |
| Terrain movement | 10F, 10H, 10I |
| Terrain visibility/cover, including TOWERING/AIRCRAFT terrain exceptions | 13A |
| Movement phase Move Units | 10B-10T |
| Movement phase Reinforcements | 10P |
| Transports | 10Q |
| Aircraft | 10R |
| Command phase | 11C |
| Battle-shock | 11C, 12B |
| Mission scoring | 11A-11C, 11E-11F |
| Stratagems | 12B, 12C, 16E |
| Shooting phase | 13A-13F |
| Weapon abilities | 8D, 13D, 16F |
| Aura abilities | 16C, 16D, 16F |
| Charge phase | 14A, 14B |
| Fight phase | 14C-14F |
| Leader/attached units | 6, 15D, 16A |
| Faction/detachment/enhancement rules | 16C-16F |
| Chapter Approved 2025-26 | 11A, 11E, 11F, 15A, 19A |
| Adapter/UI contract | 11D |
| Human CLI/UI | 17A, 17C |
| Network play | 17D |
| Replay | 17B, all state-changing phases |
| AI/headless self-play | 18B-18E |
| Performance budgets | 10U, 18A |
| 11e preparation | 20A-20D |
