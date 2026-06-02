# CORE V2 Architecture Build Order

This document is the build-order roadmap for reconstructing the Warhammer 40,000 CORE V2 engine after the completed Phase 1-14D work, the Phase 14E allocation-host foundation, the Phase 14F shooting-type cutover, and the 11th Edition Core Rules source drop.

The roadmap is intentionally rules-engine first:

- engine lifecycle and state are authoritative;
- every player, AI, UI, network, and replay interaction goes through `DecisionRequest`, `DecisionResult`, and `DecisionRecord`;
- runtime code executes typed descriptors and handlers, not raw rule text;
- replay payloads are deterministic, JSON-safe, and fail-fast on drift;
- unsupported rule shapes are explicit, source-linked, and auditable.

Primary references for roadmap coverage:

- Warhammer 40,000 11th Edition Core Rules source PDF: [docs/source_rules/eng_01-06_warhammer40k_new40k_core_rules-was6fbu1ix-hfewhmxyiy.pdf](docs/source_rules/eng_01-06_warhammer40k_new40k_core_rules-was6fbu1ix-hfewhmxyiy.pdf)
- 11th Edition app/codex/mission-pack source imports as they are added to CORE V2 source packages.
- 11th Edition Digital App/community clarification supplement provided by project owner for this cutover plan.
- CORE V1 reference implementation: <https://github.com/SobolGaming/Warhammer40k_AI>
- CORE V1 generated Wahapedia data: <https://github.com/SobolGaming/Warhammer40k_AI/tree/dev/wahapedia_data>
- CORE V2 repository: <https://github.com/SobolGaming/Warhammer_40k_AI>

CORE V2 is now 11th Edition-only. Previous-edition source package names, descriptor IDs, tests, and comments are migration debt, not supported compatibility targets. Do not add edition-diff switches, compatibility shims, or dual-edition behavior unless a future repository policy explicitly reverses this decision.

## Roadmap status

Everything through **Phase 14D** is treated as implemented at the time this file was updated. **Phase 14E remains in progress**: the allocation-group foundation and grouped-host weapon-ability revalidation are implemented for supported fixed-damage attack pools, including save-before-allocation batching, defender ordered allocation decisions, current allocation group transitions, low-to-high failed-save damage resolution, normal-damage-before-routed-mortal ordering, Precision group priority, Devastating Wounds cap/order, Lethal Hits, Sustained Hits, Anti, Twin-linked, Melta, Torrent, critical timing, and no illegal Devastating Wounds spillover. Cleave is represented as a structured descriptor/helper, while full Cleave dice gathering and Lance charge-gated wound modifiers remain tied to the Phase 15 Charge/Fight host because no fight-phase attack declaration host exists yet. **Phase 14F's shooting-type cutover is implemented** for Normal, Assault, Close-quarters, Indirect, and Snap shooting, including finite shooting-type selection, supported grouped attack resolution, Indirect/Snap Hit-roll reroll bans, and the Shooting-phase action-start lock.

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
| 10K | Complete | Precise movement distance, straight-line segments, and free rotations |
| 10L | Complete | Unit coherency runtime validation and movement rollback |
| 10M | Complete | Engagement-aware Movement action options and Normal Move finalization |
| 10N | Complete | Advance action, dice, rerolls, and advanced-state restrictions |
| 10O | Complete | Fall Back action and Desperate Escape resolution |
| 10P | Complete | Ingress Moves, Strategic Reserves, Deep Strike, and reserve placement |
| 10Q | Complete | Transport Embark/Disembark, Firing Deck, and destroyed transport emergency disembark |
| 10R | Complete | Aircraft and Hover movement/reserve behavior |
| 10S | Complete | Triggered and surge movement foundation |
| 10T | Complete | Movement phase completion gate |
| 10U | Complete | Movement/pathing/terrain profiling and hotspot budget gate |
| 10V | Complete | Movement audit hardening and deferred-wiring contracts |
| 11A | Complete | Chapter Approved 2025-26 mission pack data |
| 11B | Complete | Objective control geometry and mission objective model |
| 11C | Complete | Command phase body: Command step, CP, Battle-shock, and OC updates |
| 11D | Complete | Adapter scaffold and parameterized movement/placement proposal requests |
| 11E | Complete | Mission actions, primary/secondary scoring, and end-of-turn cleanup |
| 11F | Complete | Battle-round/game-end scoring windows, VP caps, final audit, and winner determination |
| 12A | Complete | Timing windows, reaction queue, sequencing, and persisting effects |
| 12B | Complete | Command Point ledger and Stratagem framework |
| 12C | Complete | Phase-12-resolvable Core Stratagems |
| 12D | Complete | Ability handler registry and keyword-gated rule execution |
| 13A | Complete | Terrain visibility, line of sight, and cover foundation |
| 13B | Complete | Shooting phase target selection and weapon declaration |
| 13C | Complete | Attack sequence, allocation, saves, damage, and typed attack events |
| 13D | Complete | Weapon abilities, shooting/fight modifiers, and shooting Stratagems |
| 13E | Complete | Damage allocation, destroyed models, and destruction reactions |
| 13F | Complete | Shooting phase completion gate |
| 14A | Complete | Source identity and migration audit |
| 14B | Complete | Timing windows, active player, and phase skeleton cutover |
| 14C | Complete | Shared primitives cutover |
| 14D | Complete | Movement, terrain, objectives, and actions cutover |
| 14F | Complete | Shooting-type cutover with finite shooting-type selection and supported grouped attack resolution |

Next / planned sequence:

| Phase | Status | Purpose |
|---|---:|---|
| 14E | In progress | Allocation-group host and grouped-host weapon abilities are implemented for supported fixed-damage pools; melee-only Cleave/Lance execution waits on Phase 15 Charge/Fight |
| 14G-14K | Next | Remaining mandatory 11th Edition migration/revalidation for completed Phases 1-13F plus source contracts for unimplemented rules |
| 15A-15F | Planned | Charge and Fight phases implemented directly from the 11th Edition Phase 14G contract |
| 16A-16E | Planned | Setup, deployment, reserves declarations, and army construction completion |
| 17A-17G | Planned | Source ingestion, rule-language IR, generic handlers, and content coverage |
| 18A-18D | Planned | Human UI, replay inspection, local visual UI, and network play |
| 19A-19E | Planned | Profiling, AI orchestration, self-play, and training corpus generation |
| 20A-20D | Planned | Full-game coverage, regression, soak, and release gates |

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

# 11th Edition Core Rules audit coverage

This section records the source audit against the 11th Edition Core Rules PDF. It exists because missing a foundational rule, such as the attack-allocation order or the free-rotation movement rule, can corrupt every later phase that consumes dice, attacks, movement, visibility, scoring, replay, or adapter decisions.

Rules audited against the 11th Edition PDF are assigned to explicit roadmap owners below. If a phase implements a mechanic that depends on one of these rules, it must either consume the owning phase's typed service or fail explicitly until that service exists.

| Core Rules area | Required roadmap owner |
|---|---|
| D3 conversion, multi-dice expressions, roll-offs, reroll order, one-reroll-per-die, unmodified result semantics | Phase 10J |
| Distance predicates including within, wholly within, more than, horizontal-only reserve distances, closest-points measurement, base-as-part-of-model visibility, `FRAME` measurement, and objective-marker range | Phase 10J.1, 13A, 16A, 14C |
| Characteristic post-modifier caps/floors for Move, Toughness, Save, Invulnerable Save, Leadership, Objective Control, Detection Range, Range, Attacks, WS, BS, Strength, AP, and Damage, including modifier-eligible `0`, modifier-immune `-`, Battle-shocked OC replacement, and half-damage applied after other Damage modifiers | Phase 10J.1, 11C, 13C, 17B, 14C |
| Roll-offs for mission/setup/sequencing, including no rerolls or modifiers and repeat ties | Phase 10J, 12A, 16A |
| Active/opposing player state, including start/end battle-round defaults and selected unit control during move/shoot/fight resolution | Phase 9B, 12A, 14B |
| Start/end battle round, start/end turn, and start/end phase timing windows, including non-mission rules before mission rules at end-of-turn/end-of-phase/end-of-round windows | Phase 9B, 11E, 11F, 12A, 14B |
| Persisting effects through Embark/Disembark, repositioned units, transport destruction, Attached-unit source destruction, and revival | Phase 12A, 12D, 16D, 14H |
| Out-of-phase actions: perform only the specified action and do not trigger other rules normally used in that phase | Phase 12A, 12C, 12D |
| Starting Strength, Below Half-strength, At Half-strength, Battle-shock persistence/recovery, CP gain, Battle-shocked restrictions, and appendix handling for units that cannot be exactly half-strength | Phase 11C, 14C |
| Moving core: straight-line distance, free rotations, no pivot costs, per-model Move budgets when a unit has mixed Move characteristics, Set Up rollback, model overlap/surface checks, and end-of-turn coherency cleanup without destroyed-model triggers | Phase 10A-10T, 11E, 14C, 14D |
| Unit coherency and engagement: 2"/5" engagement range, one-neighbor coherency plus 9"/5" max-spread coherency across every model | Phase 10G, 10L, 10M, 10N, 10O, 15A-15D, 14C |
| Making attacks: ranged weapon selection, melee one-weapon selection plus `[EXTRA ATTACKS]`, target eligibility, identical-attack aggregation, and declared melee attack splitting across multiple engaged targets | Phase 13B, 13C, 13D, 15C, 14E |
| Attack sequence: sequential full weapon-ability host plus grouped fixed-damage hit/wound/save-before-allocation/damage host, mandatory Invulnerable Save precedence, defender ordered allocation decisions, low-to-high failed-save resolution, and current group transitions | Phase 13C, 13E, 14E |
| Attack sequence 11th Edition allocation host: save-before-allocation batching, allocation groups, defender ordered allocation decision, save resolution from lowest to highest result, current allocation group transitions, and damage allocation to wounded models first | Phase 14E |
| Mortal wounds, normal-damage-before-mortal ordering, hazard rolls as unit-level rolls that allocate through mortal-wound rules, and `[DEVASTATING WOUNDS]` mortal-wound cap of one destroyed model per critical wound | Phase 13C, 13D, 13E, 14C, 14E remaining |
| Visibility: 1 mm line of sight, visible vs fully visible model/unit states, same-unit model ignoring, and `FRAME` closest-point visibility/measurement | Phase 13A, 14C, 14D |
| Terrain: terrain areas, exposed/light/dense categories, dense movement gates, vertical movement, stable non-ground-level endpoints, Solid 3" ground-level line-of-sight blocking, Hidden using model-level terrain-area occupancy and unit Detection Range, Gone to Ground detection modifier, Obscuring terrain areas, Benefit of Cover as `-1 BS`, and Plunging Fire as `+1 BS` | Phase 10F, 10I, 13A, 13C, 14D, 14E |
| Objectives: terrain objectives as primary objective representation, marker fallback only when no terrain area coincides, objective markers can be moved through and ended on, terrain-area containment for derived terrain objectives, secured-objective persistence and timing | Phase 11A, 11B, 11C, 14D, 14E |
| Movement phase: every army unit is selected to move each Movement phase, including strategic reserves and embarked units; Ingress/reserve arrival is a move type inside Move Units, not a separate phase step; move type is a finite decision; Remain Stationary does not trigger start/end move rules | Phase 10B-10T, 14D |
| Fall Back: Ordered Retreat vs Desperate Escape modes, hazard rolls for Desperate Escape, enemy-model traversal, post-move Battle-shock roll, and shooting/charge/action restrictions | Phase 10O, 11C, 14D |
| Shooting phase: Normal, Assault, Close-quarters, Indirect, and Snap shooting-type cutover through finite shooting-type selection, declaration, grouped attacks, saves, and damage; close-quarters engaged targeting and weapon-selection restrictions; Indirect cover/no-reroll enforcement and fail ranges; engaged MONSTER/VEHICLE targeting; `[BLAST]` engaged-target bans; Assault/Advanced weapon gating; Fire Overwatch/Snap routing | Phase 13B-13F, 14F |
| Charge phase: charge eligibility, charge-target declaration after the roll, target-within-roll-distance validation, within-1" and engaged-if-possible model movement clauses, all-target engagement requirement, non-target engagement ban, and Fights First grant | Phase 15A, 15B, 14G |
| Fight phase: both-player pile-in step, Fights First alternating selection, eligible-to-fight if charged/engaged at Fight phase start/engaged at activation, eligible-to-fight pass rule when all eligible units are more than 5" from enemies, Normal Fight, Overrun Fight, both-player consolidation step, and Ongoing/Engaging/Objective consolidation modes | Phase 15C, 15D, 14G |
| Actions: start eligibility exclusions, including Battle-shocked units and units that shot earlier in the current Shooting phase; TITANIC exceptions, action-imposed shooting/charge restrictions, cancellation by moves except pile-in/consolidation, cancellation on leaving battlefield, and completion effects | Phase 11E, 17C-17D, 14D, 14F |
| Stratagem framework: same stratagem once per phase, same unit targeted by at most one stratagem per phase unless stated, optional additional CP sections, and source-backed 11th Edition Core Stratagem definitions | Phase 12B, 12C, 12D, 14I |
| Core Stratagems: Command Re-roll partial-die semantics and no Leadership/Battle-shock coverage, Epic Challenge, Insane Bravery, New Orders, Explosives, Crushing Impact, Rapid Ingress, Fire Overwatch via Snap Shooting at end of opponent's Movement phase, Smokescreen, Heroic Intervention modes, and Counteroffensive | Phase 12B, 12C, 13D, 15E, 14I |
| Monsters/Vehicles and `FRAME`: normal/advance-only movement through non-MONSTER/non-VEHICLE friendly/enemy models, frame measurement/rotation, shooting at engaged MONSTER/VEHICLE units, and close-quarters exceptions | Phase 10G, 10I, 13B, 14C, 14F |
| Transports: capacity by models, multiple embarked units, battle-formation embark, post-move Embark with setup-this-turn and datasheet-capacity gates, Rapid/Tactical/Combat Disembark modes including ingress restriction inheritance and Combat hazards/engagement permissions, Emergency Disembark closest-possible setup, and destroyed-transport timing with Deadly Demise | Phase 10Q, 13E, 16C, 14H |
| Attached units: Leader and Support components, one Leader and one Support per bodyguard unless stated, bodyguard Toughness for attacks, destroyed-unit trigger identity, keyword union without model keyword inheritance, source-scoped ability persistence, and revive into attached unit | Phase 6, 13C, 13E, 16D, 17F, 14H |
| Strategic Reserves and repositioned units: 50% points cap, no Fortifications, second-round ingress, 6" battlefield-edge setup, more-than-8" enemy distance, pre-third-round opponent-deployment-zone ban, third-round destruction exceptions, and move-history/effect persistence for repositioned units | Phase 10P, 11F, 16C, 14H |
| Flying, Surge, and Aircraft: surge target selection and no-repeat-move restriction, optional `take to the skies` declaration with `-2"` budget unless Hover, FLY through all models/terrain and ignores vertical distance, Aircraft-only ingress, end-of-opponent-turn reserve transition, Aircraft engagement exceptions, and aircraft charge/fight restrictions | Phase 10R, 10S, 15B, 15D, 14D, 14H |
| Core abilities and weapon abilities: conditional keyword gates, duplicate ability instance selection, `[ANTI]`, `[ASSAULT]`, `[BLAST]`, `[CLEAVE]`, `[CLOSE-QUARTERS]`/`[PISTOL]`, Deadly Demise, Deep Strike, `[EXTRA ATTACKS]`, Feel No Pain, Fights First, Firing Deck, `[HAZARDOUS]`, `[HEAVY]`, Hover, `[HUNTER X]`, `[IGNORES COVER]`, `[INDIRECT FIRE]`, Infiltrators, `[LANCE]`, Leader, `[LETHAL HITS]` optional auto-wound, Lone Operative X", `[MELTA]`, `[ONE SHOT]`, `[PRECISION]`, `[PSYCHIC]`, `[RAPID FIRE]`, Scouts, Stealth, Support, Super-heavy Walker, `[SUSTAINED HITS]`, `[TORRENT]`, and `[TWIN-LINKED]` | Phase 13D, 17C-17F, 14I |
| Appendix and digital rules: adding a new unit, destroyed-model timing, destroyed models unable to use abilities, different Move characteristics, eligible-to-fight pass, mixed keywords, marker fallback objectives, healing/revived models including fully destroyed Bodyguard revival in attached units, and FAQs covering no-ranged-weapon shooting eligibility, engaged `[BLAST]` bans, overrun-fight eligibility, and scout-move embark ban | Phase 9C, 10K, 11B, 13E, 15C, 16B-16D, 17F, 14H |
| Muster army restrictions: battle size, roster order, faction, detachment points, detachment rules, unit/enhancement limits, Leader/Support attachment declarations on the army list, Enhancement assignment after attached units, Warlord faction-keyword requirement, Epic Heroes, and Dedicated Transport occupancy | Phase 16D, 14J |
| Mission deck and scoring: two Secondary Missions per turn, retained Secondaries until achieved, no two-card hand-size cap, ordinary Tactical discard with once-per-round 1 CP reward and no replacement, New Orders 1 CP once-per-game discard-and-draw Stratagem, 15 VP per-round Secondary cap, and 45 VP Primary / 45 VP Secondary caps | Phase 11A, 11E, 11F, 12C, 14J |
| Mission setup order, attacker/defender, battle formations secrecy/public reveal, terrain/objective/deployment maps | Phase 11A, 16A, 16C, 16E |

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
- objective markers are 40mm markers by default, can be moved over as if not
  there, and can be ended on top of;
- characteristics depicted as `-`, or replaced by `-` by a rule such as
  Battle-shock replacing OC, are not numeric values and cannot be changed by
  numeric modifiers;
- characteristics with numeric value `0` remain numeric and can be changed by
  modifiers such as auras unless that characteristic's own cap/floor forbids the
  final value;
- Detection Range is a unit characteristic, defaults to 15", and is better when
  lower because it means the unit is detected from a shorter distance;
- post-modifier Move and Toughness cannot be less than 1;
- Save cannot become 1+ or better;
- Leadership cannot become better than 4+ or worse than 9+;
- Objective Control cannot be less than 0;
- ranged weapon Range, Attacks, Strength, and Damage cannot be less than 1 unless a rule explicitly permits Damage 0;
- halve-damage effects are applied after additive, subtractive, replacement, and
  other Damage modifiers, so the halving consumes the already-modified Damage
  value;
- WS and BS cannot become 1+ or better;
- AP cannot become worse than 0;
- all caps/floors are applied after modifier stacking and before result consumption.

Required tests:

- closest-base distance and baseless-model distance work;
- within, wholly within, more-than, and horizontal-only predicates evaluate correctly;
- objective marker range/control predicates use 3"/5";
- objective marker endpoint overlap is allowed and does not block otherwise legal
  movement or placement;
- each characteristic cap/floor is enforced after modifiers;
- numeric `0` can be modified while `-` cannot be modified;
- Battle-shocked OC becomes typed `-`, not numeric 0, and rejects OC modifier effects;
- Detection Range defaults to 15", accepts modifier stacks, and treats lower
  values as better for Hidden detection;
- halve-damage effects apply after other Damage modifiers;
- Damage can become 0 only when an explicit rule permits it;
- distance predicate payloads round-trip without object reprs.

CORE V1 relevant areas:

- `src/warhammer40k_ai/utility/calcs.py`
- distance predicate tests
- objective marker / deployment / reserve placement tests

## Phase 10K: precise movement distance, straight-line segments, and free rotations

Status: Complete.

This phase owns movement-distance accounting. Under the 11th Edition rules, distance is paid for straight-line model movement only; rotating a model any amount around the centre of its base or frame axis does not count toward the distance moved. Any existing pivot-cost policy is retired migration debt and must be removed or made unreachable by Phase 14C.

Modules:

- `geometry/pathing.py`
- `geometry/movement_envelope.py`
- `engine/phases/movement.py`
- `engine/movement_legality.py`

Objects:

- `MovementDistanceBudget`
- `MovementSegment`
- `MovementDistanceWitness`

Invariants:

- movement distance is measured across straight-line segments;
- straight-line distance is measured from the same point on the base/model at the start and end of each line;
- rotating a based model any amount around the centre of its base is legal movement bookkeeping but costs 0";
- rotating a baseless `FRAME` model any amount around its central axis costs 0";
- movement witnesses may record facing/rotation changes for replay and collision evidence, but must not debit movement distance for those rotations;
- retired pivot-cost descriptors, fixtures, and payload fields must fail static audit once the 11th Edition cutover is complete;
- movement-distance witnesses serialize without object reprs.

Required tests:

- rotating round, oval, rectangular, and baseless `FRAME` models never consumes movement distance;
- straight-line movement still consumes distance from the same point on the base/model;
- mixed straight-line-plus-rotation paths serialize rotation evidence without pivot-cost fields;
- static audit rejects retired pivot-cost policy usage after Phase 14C lands;
- straight-line distance uses same-point measurement semantics;
- movement distance witness round-trips.

CORE V1 relevant areas:

- `src/warhammer40k_ai/pathing/validation.py`
- `src/warhammer40k_ai/pathing/sweep.py`
- `src/warhammer40k_ai/pathing/types.py`
- `src/warhammer40k_ai/movement_distance.py`
- movement distance / rotation tests

## Phase 10L: unit coherency runtime validation and movement rollback

Status: Complete.

This phase applies the 11th Edition coherency policy to battlefield placements and move endpoints.

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
- every model in a multi-model unit must be within 2" horizontally and 5" vertically of at least one other model in that unit;
- every model in a multi-model unit must be within 9" horizontally and 5" vertically of every other model in that unit;
- units must be set up in coherency;
- units must end any kind of move in coherency;
- if a unit cannot end a move in coherency, that move is invalid and model poses roll back;
- end-of-turn coherency cleanup removes models until coherency is restored, destroys those models, and must not trigger destroyed-model rules;
- coherency validation returns offending model IDs.

Required tests:

- multi-model units require one neighbor per model within 2"/5";
- units fail coherency when any model is more than 9"/5" from any other model in that unit;
- broken coherency identifies offending model IDs;
- end-of-turn coherency cleanup removes the minimum required models without destroyed-rule triggers;
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
- Normal Move consumes precise distance, free-rotation, terrain, pathing, and coherency validators;
- Normal Move movement-distance witnesses must preserve straight-line segment and rotation evidence without debiting distance for rotations;
- Normal Move cannot end on another model, embedded in a wall/floor/terrain volume without an explicit legal endpoint, outside the battlefield, or out of coherency;
- Normal Move emits displacement records only after all validators pass;
- Advance, Fall Back, Charge, Pile-in, Consolidate, Scout, and triggered movement must consume the same movement-distance and terrain-legality infrastructure instead of implementing independent distance accounting.

Required tests:

- action options outside Engagement Range are Remain Stationary, Normal Move, Advance;
- action options inside Engagement Range are Remain Stationary, Fall Back;
- Normal Move validates pathing, terrain, free rotations, and coherency;
- Normal Move for round, non-round, `VEHICLE`, `MONSTER`, and baseless `FRAME` models never consumes distance for rotation;
- Normal Move replay payload rejects movement-distance witness drift if straight-line segment or rotation evidence is malformed;
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
- Advance consumes terrain, free-rotation, pathing, and coherency validators;
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
- Desperate Escape is a Fall Back mode, and uses one hazard roll for each model in the falling-back unit;
- Battle-shocked units selected to Fall Back must use Desperate Escape;
- failed Desperate Escape hazard rolls allocate mortal wounds through the shared mortal-wound service;
- post-hazard Fall Back endpoint coherency is validated before any battlefield mutation;
- if Desperate Escape destroys every model in the falling-back unit, removal records remain authoritative and no stale `FellBackUnitState` is recorded;
- unresolved Desperate Escape requirements cannot emit Fall Back transition records;
- Desperate Escape allows moved models to move through enemy models;
- units that Fall Back cannot shoot or declare a charge that turn unless a rule permits it;
- destroyed models emit removal records with correct destruction context.

Required tests:

- eligible unit can Fall Back;
- ineligible unit cannot Fall Back;
- endpoint in Engagement Range is rejected;
- Desperate Escape mode creates one hazard roll per model;
- Battle-shocked Fall Back requires Desperate Escape mode;
- failed Desperate Escape hazard rolls allocate mortal wounds;
- survivor coherency is revalidated after Desperate Escape mortal-wound resolution;
- Desperate Escape casualties can make an otherwise incoherent attempted endpoint legal;
- all-model Desperate Escape destruction round-trips through lifecycle replay without stale Fell Back state;
- unresolved Desperate Escape requirements cannot emit transition batches;
- Fall Back emits displacement and removal records where applicable.

CORE V1 relevant areas:

- `src/warhammer40k_ai/engine/decision_handlers/movement.py`
- `src/warhammer40k_ai/pathing/rules_profile.py`
- `src/warhammer40k_ai/pathing/validation.py`

## Phase 10P: Ingress Moves, Strategic Reserves, Deep Strike, and reserve placement

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

- Movement phase has a Move Units step; reserve arrivals are resolved as move types such as Ingress Move selected inside that step;
- `REINFORCEMENTS` is not a separate 11th Edition phase step and remains only a retired migration term;
- reserve placement uses placement records, not displacement records;
- all Reserves units not set up on the battlefield when the battle ends count as destroyed;
- Reserves units set up by an Ingress Move follow the Ingress Move after-moving restrictions and cannot make another type of move until the start of the next Charge phase unless a rule permits it;
- any specified enemy-distance requirement for setting up Reserves applies to horizontal distance unless the source rule says otherwise;
- Strategic Reserves are a subset of Reserves, while Deep Strike and other reserve-like abilities keep their own setup rules;
- Strategic Reserves declarations exclude `FORTIFICATIONS` and enforce the battle-size points limit, including embarked units inside transports placed into Strategic Reserves;
- Strategic Reserves cannot arrive in battle round 1;
- Strategic Reserves arriving in battle round 2 must be wholly within 6" of a battlefield edge and not within the enemy deployment zone;
- Strategic Reserves arriving from battle round 3 onward must be wholly within 6" of a battlefield edge;
- Strategic Reserves cannot be set up within 8" horizontally of enemy units, i.e. they must be more than 8" away;
- Deep Strike units may be placed in Reserves during Declare Battle Formations if every model has Deep Strike;
- Deep Strike placement uses its source setup policy and, under the 11th Edition Core Rules, is more than 8" horizontally from all enemy units;
- a unit arriving from Strategic Reserves with Deep Strike may choose either Strategic Reserves setup rules or Deep Strike setup rules;
- reserve placements validate battlefield edges, enemy distance restrictions, terrain endpoints, coherency, model overlap, and deployment restrictions;
- mandatory arrivals are requeued or fail explicitly according to rules;
- no `PathWitness` is required for placement.

Required tests:

- Movement phase offers legal Ingress Move choices during Move Units;
- Deep Strike placement uses `BattlefieldPlacementKind.DEEP_STRIKE`;
- Strategic Reserves placement uses `BattlefieldPlacementKind.STRATEGIC_RESERVES`;
- illegal reserve placement fails without mutating state;
- reserve placement validates coherency and Engagement Range setup restriction;
- reserve placement validates terrain endpoint support;
- Strategic Reserves battle-round-2 edge/enemy-deployment-zone/more-than-8" restrictions are enforced;
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

- destroyed Transport orchestration from actual damage/destruction events is owned by Phase 13E/15D;
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
- Phase 10Q's initial Movement lifecycle exposes simple pre-move and post-Transport-Normal-Move Disembark gates; Phase 14H replaces this with the source-backed 11th Edition Rapid, Tactical, Combat, destroyed-Transport, and Emergency Disembark modes;
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
- mandatory Strategic Reserves deployment during battle formation;
- end-of-opponent-turn reserve transition metadata.

Deferred setup consumers:

- Aircraft mandatory reserve declaration during Declare Battle Formations is owned by Phase 16C;
- Hover behavior is now owned by the Flying rules, not an Aircraft deployment-mode choice.

Invariants:

- all `AIRCRAFT` units must start in Strategic Reserves;
- `AIRCRAFT` units are only eligible to make ingress moves and are not eligible for other move types;
- at the end of the opponent's turn, each on-battlefield `AIRCRAFT` unit is placed into Strategic Reserves;
- aircraft reserve transitions remove the unit from the battlefield and serialize deterministic reserve metadata;
- each time any unit makes any type of move, its models can be moved through `AIRCRAFT` models;
- enemy `AIRCRAFT` engagement is tracked separately so non-Aircraft units engaged only by enemy Aircraft can still choose Normal Move or Advance while endpoint validation remains strict;
- unless the moving unit can `FLY`, pile-in, consolidation, and surge target selection ignore `AIRCRAFT` for closest-enemy and enemy-selection purposes;
- Plunging Fire has no effect on attacks made by or targeting `AIRCRAFT`;
- `AIRCRAFT` units are not eligible to declare charges, can only make melee attacks that target `FLYING` units, and only `FLYING` units/models can charge or make melee attacks into `AIRCRAFT`.

Required tests:

- Aircraft battle-formation setup places all Aircraft in Strategic Reserves;
- Aircraft ingress validates Strategic Reserves placement restrictions;
- end-of-opponent-turn Aircraft reserve transition emits removal records and deterministic reserve state;
- Aircraft cannot be selected for Normal, Advance, Fall Back, Charge, pile-in, consolidation, or surge moves unless a later source explicitly overrides the Core Rules;
- replay rejects stale Aircraft reserve-transition payloads;
- non-Aircraft units engaged only by enemy Aircraft can choose Normal Move and Advance, but cannot end within enemy Aircraft Engagement Range;
- non-`FLY` pile-in, consolidation, and surge target selection ignores Aircraft;
- Aircraft Plunging Fire exclusions are enforced;
- Aircraft charge/fight restrictions are exposed and regression-tested.

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
- triggered movement consumes pathing, terrain, free-rotation, and coherency validation.

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
- reserve arrivals are legal Move Units selections rather than a separate Reinforcements step;
- Movement phase advances only after all Move Units choices and unresolved mandatory placements are complete;
- movement phase events and replay payloads are deterministic.

Required tests:

- full Move Units step completes;
- Advance/Fall Back/Normal/Remain Stationary interact correctly;
- failed movement does not mutate state;
- reserve arrival choices occur during Move Units;
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

- Phase 11A must provide mission deployment-zone geometry to live reserve-arrival validation so battle-round-2 Strategic Reserves pass enemy deployment zones into `resolve_reserve_arrival`;
- Phase 11A/11B must provide instantiated terrain features to live reserve-arrival and deployment placement validation, not only resolver tests;
- Phase 11E/11F must call unarrived-reserve destruction at the appropriate game-end or mission-pack deadline;
- Phase 13B must consume Firing Deck selections during Shooting and validate selected weapons against the embarked model's wargear;
- Phase 13E/15D must orchestrate destroyed Transport disembark from real destruction events before removing the Transport model;
- Phase 16D must make attached-unit coherency group-aware by validating the attached rules unit, not a single `UnitPlacement`;
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
- live reserve-arrival validation receives mission deployment-zone geometry for reserve placement validation;
- live placement validators receive instantiated terrain features instead of resolver-local test fixtures;
- tournament mission pool is deterministic and replay-facing;
- Fixed/Tactical/Challenger card behavior remains hidden/public-safe.

Required tests:

- Chapter Approved mission sequence round-trips;
- deployment map geometry round-trips;
- objective marker positions round-trip;
- objective marker terrain/movement policy is flat/non-blocking for Chapter Approved;
- terrain layout template instantiates deterministic terrain features;
- live reserve-arrival validation rejects battle-round-2 Strategic Reserves in enemy deployment zones using mission data;
- live reserve-arrival validation rejects illegal terrain endpoints using instantiated terrain layout data;
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
- Battle-shocked units have OC `-`, which contributes no Objective Control and cannot be modified by numeric OC modifiers;
- objective markers use mission-defined center positions and default 40mm marker geometry unless a mission overrides it;
- models can move over objective markers and can end a move on top of them;
- objective marker range is 3" horizontally and 5" vertically unless a mission overrides it;
- objective control updates at the end of every phase and turn;
- objective marker terrain interactions are descriptor-driven;
- objective control results are replay-safe.

Required tests:

- objective control sums OC by player;
- Battle-shocked unit contributes no OC because its OC characteristic is `-`;
- contested objective has deterministic result;
- terrain objective policy is explicit unsupported until implemented;
- model can end on top of an objective marker;
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
- failed Battle-shock marks the unit and all its models Battle-shocked until it passes a later recovery roll or another rule clears the state;
- Battle-shocked units have OC `-`, not OC 0, and OC `-` cannot be increased by numeric modifiers;
- Battle-shocked units must use Desperate Escape if selected to Fall Back;
- Battle-shocked units cannot start actions and cannot complete actions already in progress;
- a player cannot use Stratagems to affect their Battle-shocked units unless a rule permits it;
- Starting Strength is recorded at army creation and updated correctly when Attached units split;
- Below Half-strength for single-model units uses remaining wounds less than half the Wounds characteristic; other units use current model count less than half Starting Strength;
- Command phase scoring hooks run at the correct timing.

Required tests:

- both players gain 1CP at the start of each Command phase;
- non-Command CP gain cap of 1CP per battle round is enforced;
- below-half-strength unit emits Battle-shock test request;
- below-Starting-Strength forced test suppresses duplicate Below Half-strength test unless overridden;
- failed Battle-shock persists and changes OC to `-`;
- passed Battle-shock avoids Battle-shocked state;
- Battle-shocked unit cannot be targeted by friendly Stratagems by default;
- Starting Strength and Below Half-strength logic works for single-model and multi-model units;
- Attached-unit split recovery restores surviving component units to their original Starting Strength records;
- Command phase stops at required decision requests and resolves non-reroll Battle-shock dice deterministically without a player-choice pause.

## Phase 11D: adapter scaffold and parameterized movement/placement proposal requests

Status: Complete.

This phase creates the engine-owned contract that allows UI work to proceed in parallel without UI-owned state mutation. It separates finite decision choices, such as selecting a movement action, from parameterized movement and placement proposals, such as per-model endpoints and path witnesses.

This phase does not build a visual UI. It creates the adapter and proposal contracts that a later CLI, local visual UI, network client, or AI policy can consume.

Design note: [Adapter Decision Contract](docs/ADAPTER_DECISION_CONTRACT.md) defines the shared submission path, producer responsibilities, viewer-scoped projections/events, and examples for UI, CLI, headless, network, AI, replay, and test adapters.

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
- movement proposal payloads include the selected unit, selected movement action, per-model movement data, path witness data, rotation/facing data where applicable, and any required source context;
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
- reserve-arrival placement proposal;
- Deep Strike placement proposal;
- Strategic Reserves placement proposal;
- Disembark placement proposal.

Reserve arrival proposal requests use distinct proposal kinds for general reserve
arrival, Deep Strike, and Strategic Reserves flows. The request's
`placement_kinds` field enumerates the legal physical placement methods
available to that reserve state and unit.

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
- a golden JSON fixture covers the parameterized Normal Move proposal request; inline JSON-shape regressions cover finite movement action selection, invalid movement and placement proposals, reserve placement, Disembark placement, and viewer-scoped projection/event deltas.

CORE V1 relevant areas:

- `src/warhammer40k_ai/engine/decision_handlers/movement.py`
- `src/warhammer40k_ai/pathing/validation.py`
- `src/warhammer40k_ai/pathing/types.py`
- `src/warhammer40k_ai/engine/game_setup_flow.py`
- movement, deployment, reserve, Disembark, replay, UI/headless, and decision-dispatch tests

## Phase 11E: mission actions, primary/secondary scoring, and end-of-turn cleanup

Status: Complete.

Modules:

- `engine/scoring.py`
- `engine/missions.py`
- `engine/mission_decisions.py`
- `engine/actions.py`
- `engine/turn_cleanup.py`
- `engine/unit_coherency.py`
- `rules/source_packages/warhammer_40000_11th/chapter_approved_2025_26.py`

Objects:

- `MissionScoringPolicy`
- `VictoryPointLedger`
- `MissionActionState`
- `MissionSourcePackageDefinition`
- `MissionActionDefinition`
- `EndTurnCleanupState`
- `CoherencyCleanupRemoval`

Invariants:

- scoring, game length, caps, reserve deadline policy, secondary deck eligibility,
  and supported mission Action timing/effects are source-backed
  `warhammer_40000_11th` mission-pack data, not hard-coded phase logic;
- primary and secondary VP awards consume source scoring-rule conditions and
  per-card Fixed/Tactical VP values; unsupported conditions fail fast instead of
  using default scoring amounts;
- player-facing Tactical discard and supported mission Action start selections use
  finite `DecisionRequest` options through `GameLifecycle.submit_decision(...)`;
- mission Actions have source-backed start timing, eligible units, target IDs,
  interruption conditions, completion timing, and scoring effects;
- the mission deck grants two Secondary Missions per player turn;
- Secondary Missions are retained until achieved or discarded, and Secondary
  Missions discarded by the ordinary Tactical discard flow are not replaced
  immediately;
- retained Secondary Missions do not have a two-card hand-size cap;
- Tactical discard can discard one or more retained Secondary Missions for the
  source-backed once-per-battle-round CP reward and records no replacement draw;
- New Orders is a separate 1 CP Stratagem path that discards one retained
  Secondary Mission, immediately draws a replacement Secondary Mission, and is
  usable only once per game;
- secondary mode, Fixed IDs, Tactical draws/card states, and normal secondary
  scoring visibility are source-backed and viewer-scoped;
- objective control feeds scoring;
- end-of-turn coherency cleanup removes models until each affected unit has one coherent group;
- coherency-cleanup removals count as destroyed but do not trigger destroyed-model rules;
- unarrived Reserves destruction resolver is invoked at the mission-defined deadline;
- game end after configured battle rounds produces winner/draw result.

Required tests:

- primary scoring at correct timing and source-backed battle-round gates;
- secondary scoring uses source-backed Fixed/Tactical card VP values;
- Secondary Mission draw, score, retain, and discard flow is public or hidden according to source-backed viewer rules;
- Tactical secondary discard emits deterministic decision/event records through the lifecycle path, can discard one or more retained Secondary Missions for the once-per-battle-round CP reward, and does not replace discarded cards;
- New Orders emits deterministic Stratagem, CP, discard, and replacement-draw
  records, rejects second use in the same game, and cannot be confused with
  ordinary Tactical discard;
- mission Action can start through the lifecycle decision path, persist its target,
  filter ineligible units, complete, be interrupted, and score;
- source package payloads round-trip and preserve 11th Edition mission/scoring/action snapshots;
- end-of-turn coherency cleanup removes models without destroyed triggers;
- unarrived Reserves are destroyed at the configured deadline through the lifecycle hook;
- victory point ledger round-trips;
- game ends after configured battle rounds.

## Phase 11F: battle-round/game-end scoring and winner determination

Status: Complete.

Implemented coverage:

- game length is consumed from mission scoring policy;
- end-of-round and end-of-game scoring windows are recorded once as replay-safe state;
- 11th Edition primary, secondary, Battle Ready, per-round secondary, and total VP caps are enforced at award time;
- final scoring result payloads include public capped scores, winner/draw determination, and scoring audit data;
- final scoring payloads round-trip without Python object reprs.

Invariants:

- game length is mission/ruleset data;
- end-of-round and end-of-game scoring windows are explicit;
- final VP ledger audit verifies winner/draw payloads;
- 11th Edition 45 VP Primary cap, 45 VP Secondary cap, 15 VP per-round Secondary cap, Battle Ready cap, total VP cap, and per-source caps are represented in scoring policy;
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

Status: Complete.

Modules:

- `engine/timing_windows.py`
- `engine/reaction_queue.py`
- `engine/effects.py`
- `engine/sequencing.py`

Objects:

- `TimingWindow`
- `ReactionWindow`
- `TimingWindowDescriptor`
- `TimingTriggerKind`
- `PersistingEffect`
- `EffectExpiration`
- `TriggeredDecisionRequest`
- `SequencingDecision`
- `OutOfPhaseActionContext`

Invariants:

- out-of-phase rules use typed timing windows;
- timing descriptors cover explicit trigger families needed by Stratagems and reactive rules, including any phase, start/end phase, start/end turn, start/end battle round, after a unit is selected as a target, after an enemy unit ends a move, after a unit is destroyed, just after an enemy unit has fought, and after dice/roll events;
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
- unsupported timing descriptor trigger families fail explicitly before any option is emitted;
- sequencing conflict creates a deterministic resolver decision when needed.

CORE V1 relevant areas:

- `engine/combat_timing.py`
- reactive decision handling;
- phase/reaction/persisting-effect tests.

## Phase 12B: Command Point ledger and Stratagem framework

Status: Complete.

Modules/documents:

- `engine/stratagems.py`
- `engine/stratagem_catalog.py`
- `engine/command_points.py`
- `engine/timing_windows.py`
- `rules/source_packages/warhammer_40000_11th/core_stratagems.py`
- `docs/ADAPTER_DECISION_CONTRACT.md`

Objects:

- `CommandPointLedger`
- `CommandPointTransaction`
- `CommandPointSpendResult`
- `CommandPointGainResult`
- `CommandPointRefundResult`
- `StratagemDefinition`
- `StratagemCatalogRecord`
- `StratagemCatalogIndex`
- `StratagemTimingDescriptor`
- `StratagemRestrictionPolicy`
- `StratagemTargetSpec`
- `StratagemUseRequest`
- `StratagemUseRecord`
- `StratagemEligibilityContext`
- `StratagemTargetBinding`
- `StratagemTargetProposal`

Invariants:

- Stratagem use is a player-facing decision and must use the Phase 11D adapter decision contract: `DecisionRequest` -> `FiniteOptionSubmission` or `ParameterizedSubmission` -> `DecisionResult` -> `GameLifecycle.submit_decision(...)` -> engine validation -> engine mutation;
- the finite decision type is `use_stratagem`; the engine enumerates deterministic, JSON-safe options only for currently eligible Stratagem, timing-window, CP, restriction, and fully validated target-binding combinations;
- adapters, UI, CLI, network clients, headless AI, replay, and tests must not invent Stratagem option IDs, bind targets from option payloads outside engine validation, spend/refund CP directly, or mutate state from Stratagem payloads;
- Stratagem target bindings that cannot be safely enumerated as finite choices use typed parameterized proposals, validate stale/drift/malformed/schema-invalid/wrong-context submissions before queue pop, and return typed invalid diagnostics without CP spend or state mutation;
- Stratagem decisions can be offered to the non-active player inside Phase 12A reaction windows, and eligibility context is computed per player for the active timing window;
- core Stratagems are source-backed `StratagemDefinition`/`StratagemCatalogRecord` descriptors and are always available unless a ruleset disables them;
- detachment Stratagems are usable only when the player's army selected the matching detachment or another explicit source grants them;
- Stratagem candidate dispatch uses a trigger-keyed `StratagemCatalogIndex`; the index is derived, deterministic, not authoritative state, and never replaces runtime timing, detachment, CP, target, restriction, or handler gates;
- core and detachment Stratagem records can be partitioned per player before indexing to avoid considering records the selected detachment can never grant, while the runtime detachment gate remains authoritative;
- every implemented phase that owns a source-backed Stratagem timing window must wire candidate discovery through the trigger-keyed index rather than scanning the whole catalog at event time;
- phase hooks that own multiple optional Stratagem windows under the same phase and trigger must assign distinct deterministic `timing_window_id` values, and decline suppression must be scoped to that exact timing window rather than the broader phase/trigger;
- Stratagem definitions include CP cost, category, source ID, normalized WHEN/TARGET/EFFECT/RESTRICTIONS descriptors, timing descriptor, target spec, restriction policy, faction/detachment gate, and handler binding;
- Stratagems spend, gain, and refund CP only through a bidirectional ledger with deterministic transaction IDs and replay-safe payloads;
- starting CP, Command-phase +1 CP gain from Phase 11C, non-Command CP gain caps, CP refunds, and CP-granting Stratagem/effect results are ledger transactions, not local counters;
- insufficient CP is a typed invalid result and must never underflow a ledger;
- matched-play same-Stratagem-once-per-phase restrictions are tracked separately from per-Stratagem once-per-turn, once-per-battle, per-target, and per-fight restrictions;
- Battle-shocked units cannot be selected for Stratagems unless rules permit;
- finite target binding is typed and validated before a finite Stratagem option appears, and parameterized target proposals carry typed validation context before adapters answer them;
- Stratagem timing is descriptor-driven and unsupported timing descriptors fail explicitly;
- Stratagem effects execute through Phase 12A persisting-effect machinery or source-linked named handlers in Phase 12B/12C; Phase 17D can replace representable named handlers with generic IR handlers without changing the decision/ledger contract;
- invalid or missing target context suppresses the option rather than emitting illegal choices;
- CP totals, CP transactions, and normal Stratagem-use events are public viewer-scoped adapter data in matched play unless a future source-backed hidden rule marks a specific pending decision or event hidden.

Required tests:

- adapter contract doc is updated for `use_stratagem` finite options, Stratagem target proposals, CP transaction visibility, and public Stratagem events;
- finite `use_stratagem` option enumeration and `FiniteOptionSubmission` round-trip through `GameLifecycle.submit_decision(...)`;
- parameterized Stratagem target proposal valid submission plus stale, drifted, malformed, schema-invalid, and wrong-context invalid diagnostics;
- insufficient CP suppresses legal options where possible and rejects attempted use with a typed invalid result;
- CP ledger cannot underflow;
- Command-phase +1 CP gain from Phase 11C is represented as a ledger transaction and Stratagem spend consumes from that ledger;
- CP-granting/refunding effects create deterministic gain/refund transactions and obey the non-Command CP gain cap unless an explicit rule overrides it;
- matched-play same-Stratagem-twice-per-phase rejection is distinct from per-Stratagem own restrictions;
- Battle-shocked unit eligibility restriction works;
- target-required Stratagem does not appear without legal target binding;
- reactive non-active-player Stratagem use is emitted and resolved inside a Phase 12A reaction window;
- phase/reaction-window progression uses `StratagemCatalogIndex` for implemented Stratagem windows and has regression coverage proving the source-backed phase hook emits the pending request through `GameLifecycle.submit_decision(...)`;
- nested reactions such as Command Re-roll during another Stratagem's dice resolution resume deterministically;
- detachment Stratagems are gated by selected detachment, while core Stratagems are available;
- viewer-scoped projection/event stream exposes public CP and Stratagem data and redacts any future hidden Stratagem data by explicit policy;
- Stratagem use round-trips in replay.

CORE V1 relevant areas:

- `src/warhammer40k_ai/engine/stratagem_ledger.py`
- stratagem tests;
- headless tool-action context audits.

## Phase 12C: Phase-12-resolvable Core Stratagems

Status: Complete.

Initial supported Core Stratagem groups at this build slice:

- Command Re-roll;
- Insane Bravery;
- New Orders;
- Rapid Ingress.

Later phase-coupled Core Stratagems:

- Smokescreen and Explosives are implemented at the Shooting-phase gate after visibility, Benefit of Cover, attack sequencing, and damage allocation exist;
- Fire Overwatch is implemented at the Phase 13D Shooting/Movement gate through a real out-of-phase Snap Shooting state that resolves shooting declaration and attack-sequence decisions from the End of Opponent's Movement phase window before resuming the parent phase;
- Heroic Intervention, Counteroffensive, Epic Challenge, and Crushing Impact are implemented at the Charge/Fight gates after charge movement, fight ordering, melee attacks, and model-target binding exist;
- deferred Core Stratagem descriptors still exist as explicit unsupported descriptors until their owning phase gate implements them.

Invariants:

- each supported Core Stratagem has a source-backed definition, timing descriptor, target spec, restriction policy, CP cost, and handler binding;
- each supported Core Stratagem has explicit finite or parameterized target-binding rules;
- each supported Core Stratagem consumes CP and records use;
- Command Re-roll uses source-backed edition-specific eligible roll classes, rejects roll actor drift, and applies Phase 10J reroll semantics while remaining valid as a nested reaction without breaking the parent timing window;
- Insane Bravery integrates with Phase 11C Battle-shock results without bypassing `DecisionRequest`/`DecisionResult`;
- New Orders costs 1 CP, can be used only once per game, discards one retained
  Secondary Mission card, and immediately draws one replacement Secondary Mission
  card through source-backed mission deck state;
- Rapid Ingress reuses reserve-arrival placement validators and, where exact placement is required, emits the existing placement proposal request after the Stratagem decision is accepted; when offered from a reaction window, the parent remains blocked until the placement proposal resolves;
- Command and Movement phase progression discover supported Core Stratagem windows through `StratagemCatalogIndex`: Command start for Insane Bravery and New Orders, and opponent Movement phase end for Rapid Ingress reaction/placement;
- supported dice/mission/reserves Stratagems use deterministic dice/replay plumbing and source IDs;
- Phase 12C reuses Phase 12A persisting-effect/reaction machinery and Phase 12B ledger/decision framework; it does not depend on the later Phase 12D ability registry or Phase 17D generic handlers;
- unsupported Core Stratagems remain explicit unsupported descriptors.

Required tests:

- one legal use per supported Phase-12 timing window;
- one phase-progression regression per supported phase-owned Stratagem window, proving the window is emitted from the trigger-keyed index and resolves through `GameLifecycle.submit_decision(...)`;
- combined-window regressions for phases with multiple optional Stratagem windows under the same phase/trigger, proving declining one timing window does not suppress a distinct later timing window;
- per-Stratagem golden replay for Command Re-roll, Insane Bravery, New Orders, and Rapid Ingress;
- New Orders consumes 1 CP, rejects second use in the same game, discards exactly
  one retained Secondary Mission, and immediately draws exactly one replacement
  card;
- decision-contract round-trip for option enumeration, submission, recording, event emission, and replay;
- CP consumption and repeat-use restriction;
- target-binding validation;
- CP-underflow rejection;
- same-Stratagem-twice-per-phase rejection;
- reactive non-active-player use where timing allows;
- nested Command Re-roll during another Stratagem's dice resolution;
- dice/mission/reserves records for relevant Stratagems;
- unsupported Core Stratagems fail explicitly.

## Phase 12D: ability handler registry and keyword-gated rule execution

Status: Complete.

Modules:

- `engine/abilities.py`
- `engine/ability_catalog.py`
- `rules/source_packages/warhammer_40000_11th/core_abilities.py`
- `rules/timing.py`
- `core/datasheet.py`
- `core/weapon_profiles.py`

Objects:

- `AbilityHandlerRegistry`
- `AbilityCatalogRecord`
- `AbilityCatalogIndex`
- `AbilityTimingDescriptor`
- `AbilityExecutionContext`
- `AbilityResolutionResult`
- `KeywordGate`

Invariants:

- core, keyword, faction, detachment, datasheet, wargear, and weapon abilities are represented as source-linked `AbilityDefinition`/`AbilityCatalogRecord` descriptors;
- ability candidate dispatch uses a trigger-keyed `AbilityCatalogIndex`; the index is derived, deterministic, not authoritative state, and never replaces runtime timing, source-owner, keyword, input, or handler gates;
- player/army ability indexes can be pre-partitioned from selected faction, detachment, datasheets, wargear, weapon profiles, and canonical unit/weapon keywords, while runtime gates remain authoritative;
- every future phase that owns an ability timing window must wire candidate discovery through `AbilityCatalogIndex` and must add regression coverage proving the phase hook does not scan the full ability catalog at event time;
- ability descriptors are inert until a registered handler executes them;
- handlers declare timing windows and input requirements;
- keyword-gated effects use canonical keywords;
- movement keyword capabilities are resolved from source-backed keyword ability gates, not ad hoc phase-local keyword scans;
- unsupported ability descriptors remain unsupported rather than fallback-parsed;
- ability execution records source IDs and replay payloads.

Required tests:

- source-backed 11th Edition ability rows cover the Phase 12D ability families and round-trip without object reprs;
- `AbilityCatalogIndex` partitions records by `TimingTriggerKind`, preserves deterministic ordering, rejects duplicate records, and produces option-equivalent context lookup to a full tuple scan;
- `AbilityHandlerRegistry` rejects duplicate and unsupported registrations, validates timing/input/keyword gates, and returns typed unsupported for missing or future handlers;
- movement keyword capabilities are derived through the ability index and fail closed when a test index omits the relevant keyword gate;
- player/army ability indexes retain only selected core/keyword, faction, detachment, datasheet, wargear, and weapon-profile records;
- ability records, execution contexts, and resolution results serialize as deterministic JSON-safe replay payloads.

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

Status: Complete.

Modules:

- `geometry/visibility.py`
- `geometry/terrain.py` for terrain feature and volume inputs consumed by visibility
- `geometry/terrain_factory.py` for canonical visibility fixtures
- `engine/battlefield_state.py` for spatial revision and cache-key state
- `core/ruleset_descriptor.py`

Objects:

- `LineOfSightPolicy`
- `TerrainVisibilityContext`
- `VisibilityBlockerRecord`
- `LineOfSightWitness`
- `CoverSourceRecord`
- `CoverPolicyDescriptor`
- `BenefitOfCoverResult`
- `HiddenDetectionResult`
- `GoneToGroundResult`

Invariants:

- true line of sight is modeled from model volume/pose;
- model visible, unit visible, model fully visible, and unit fully visible are separate results;
- terrain visibility rules are descriptor-driven through terrain areas and terrain categories;
- Exposed, Light, and Dense terrain categories are explicit descriptors;
- Obscuring terrain areas containing Light or Dense features block visibility when every line of sight crosses one or more such areas and neither model is within the crossed area;
- Dense terrain features have Solid line-of-sight blocking for enclosed gaps 3" or less from ground level;
- Hidden can apply only to `INFANTRY`, `BEASTS`, and `SWARM` models;
- a model is Hidden when it is at least partially within a terrain area
  containing a Dense or Light terrain element and its unit did not make ranged
  attacks last turn;
- Hidden units can only be visible to enemy models within the target unit's
  Detection Range characteristic, defaulting to 15";
- Gone to Ground applies to a model that is not fully visible to the attacking
  model because a terrain piece is at least partially in the way;
- Gone to Ground improves Detection Range by -3", making the default Hidden
  detection distance 12";
- rules, abilities, or Stratagems that let a Hidden unit shoot and remain Hidden
  cancel Gone to Ground for that interaction;
- Benefit of Cover is a policy result consumed by attacks, not a save-side effect;
- Benefit of Cover applies to the target unit only when every model in that unit qualifies through terrain-area membership or terrain/obscuring not-fully-visible evidence;
- Benefit of Cover worsens the attack's BS characteristic by 1 unless an ability such as `[IGNORES COVER]` removes it;
- cover eligibility is visible in attack context before hit rolls are made;
- LoS witnesses carry ruleset hash and spatial revision cache-key data;
- Hidden distance gates, last-turn shot-state loss, Gone to Ground cancellation,
  and visibility output are first-class 11th Edition terrain behavior;
- Phase 13A uses deterministic broad-phase candidate filtering and cache-key witnesses, but does not claim a persistent memoized shooting LoS cache; Phase 13B/13C must add or consume a real cache/index before high-volume shooting loops;
- model silhouette sampling is an explicit deterministic approximation, not an exact hull; downstream cover and Plunging Fire behavior must carry accuracy tests for that sampling budget;
- LoS witness/debug payloads are replay-safe.

Required tests:

- terrain visibility fixture can block LoS deterministically;
- terrain-area Obscuring blocks LoS only when all lines cross eligible areas and neither model is within the crossed area;
- Dense terrain Solid blocks LoS through enclosed gaps 3" or less from ground level;
- Hidden `INFANTRY`/`BEASTS`/`SWARM` models in Dense or Light terrain areas are
  visible only within the target unit's Detection Range while their last-turn
  shot-state condition is satisfied;
- Gone to Ground applies only when the attacking model's full-visibility failure
  is caused by intervening terrain, applies the -3" Detection Range modifier,
  and is cancelled by Hidden-shooting rules that preserve Hidden;
- target terrain-area membership and not-fully-visible terrain cover sources are represented independently of LoS blockers;
- Benefit of Cover rejects a LoS witness from a different observer/target query even when terrain cache keys match;
- Benefit of Cover worsens BS by 1 and does not modify the save roll;
- model volume participates in visibility checks;
- terrain visibility cache key changes when terrain revision changes;
- model silhouette sampling budget is explicit and regression-tested;
- Benefit of Cover policy result round-trips;
- LoS witness/debug payload round-trips.

CORE V1 relevant areas:

- `src/warhammer40k_ai/battlefield/terrain_visibility.py`
- `src/warhammer40k_ai/battlefield/terrain_cover.py`
- `src/warhammer40k_ai/battlefield/map.py`
- `tests/rules/test_line_of_sight.py`

## Phase 13B: Shooting phase target selection and weapon declaration

Status: Complete.

Modules:

- `engine/phases/shooting.py`
- `engine/shooting_targets.py`
- `engine/weapon_declaration.py`
- `engine/transports.py`
- `docs/ADAPTER_DECISION_CONTRACT.md`

Objects:

- `ShootingPhaseState`
- `ShootingUnitSelection`
- `ShootingTargetCandidate`
- `WeaponDeclaration`
- `ShootingDeclarationProposal`
- `FiringDeckWeaponSelection`
- `RangedAttackPool`

Invariants:

- all attacker shooting choices are player-facing decisions and must use `DecisionRequest` -> `FiniteOptionSubmission` or `ParameterizedSubmission` -> `DecisionResult` -> `GameLifecycle.submit_decision(...)` -> `DecisionRecord`/`EventRecord`;
- Phase 13B must update `docs/ADAPTER_DECISION_CONTRACT.md` with every new shooting unit selection, target declaration, weapon declaration, Firing Deck selection, option payload, proposal payload, and viewer-visibility rule introduced;
- finite shooting options use deterministic option IDs and JSON-safe payloads; parameterized declaration proposals reject stale, drifted, malformed, schema-invalid, or wrong-context submissions before queue pop unless the contract explicitly allows recorded rule-invalid retry attempts;
- eligible shooting units are derived from current state;
- units that Advanced/Fell Back cannot shoot unless a rule permits;
- engaged units obey Close-quarters shooting restrictions and shooting-at-engaged-`MONSTER`/`VEHICLE` target rules;
- shooting at engaged units applies the correct Hit-roll penalty unless the attack is a qualifying `[CLOSE-QUARTERS]`/`[PISTOL]` attack;
- Lone Operative prevents ranged targeting unless the attacker is within the required distance and closest-eligible-target condition when applicable;
- ranged weapons validate range and visibility at target selection time;
- targets for all of a unit's ranged weapons are declared before any attack is resolved;
- a weapon remains resolved against a target selected as visible/in range even if later attacks remove visible/in-range models before resolution;
- attack declarations group by model, weapon, profile, and target;
- Firing Deck attack-generation consumption, one-weapon-per-embarked-model validation, temporary Transport weapon attachment, and embarked-unit shot/ineligible state are resolved here from the Phase 10Q hand-off;
- Hazardous and one-shot-style requirements are explicit descriptors.

Required tests:

- shooting unit selection goes through finite `DecisionRequest`/`DecisionResult` submission and records deterministic JSON-safe `DecisionRecord`/`EventRecord` payloads;
- weapon and target declaration goes through the adapter contract, including stale/drift/malformed invalid submission coverage and replay payload round-trip;
- eligible unit selection;
- Advanced/Fell Back restriction;
- target range/visibility validation;
- Lone Operative targeting gate, including closest-eligible-target behavior;
- Close-quarters shooting, shooting at engaged `MONSTER`/`VEHICLE`, `[CLOSE-QUARTERS]`/`[PISTOL]`, and `[BLAST]` interactions;
- Firing Deck consumes selected embarked models/weapons, rejects duplicate or illegal embarked weapon use, attaches temporary Transport attacks, and marks selected embarked units ineligible to shoot;
- selected target remains valid for declared weapon resolution after casualties;
- weapon declaration payload round-trip;
- invalid target declaration fails without mutation.

## Phase 13C: attack sequence: hit, wound, allocate, save, damage

Status: Complete.

Modules:

- `engine/attack_sequence.py`
- `engine/damage_allocation.py`
- `engine/saves.py`
- `engine/dice.py` and Phase 10J dice/reroll helpers are consumed, not reimplemented

Objects:

- `AttackSequence`
- `HitRoll`
- `WoundRoll`
- `AttackAllocation`
- `AttackAllocationDecision`
- `SavingThrow`
- `FeelNoPainDecision`
- `PlungingFireModifier`
- `MortalWoundApplication`
- `DamageApplication`
- `FastDiceGroup`

Invariants:

- attack sequence follows hit, wound, allocate, saving throw, inflict damage;
- Hit rolls use BS for ranged attacks and WS for melee attacks;
- unmodified Hit roll of 6 is a Critical Hit and always succeeds;
- unmodified Hit roll of 1 always fails;
- Hit roll modifiers are capped at +1/-1;
- Wound roll modifiers are capped at +1/-1;
- Wound roll target number derives from Strength vs Toughness using integer-safe boundaries: 2+ when `S >= 2*T`, 3+ when `S > T`, 4+ when `S == T`, 6+ when `2*S <= T`, and otherwise 5+;
- unmodified Wound roll of 6 always succeeds and unmodified Wound roll of 1 always fails;
- unmodified saving throw roll of 1 always fails before any save characteristic
  is checked;
- the attack sequence emits typed, ordered attack events/timing windows at hit, Critical Hit, wound, Critical Wound, allocation-order, save, and damage; ability handlers may only mutate within their owning windows, so Phase 13D abilities can attach without reaching into attack-sequence internals;
- hit resolution supports both rolled hits and explicit skipped-roll/generated-hit paths, so later ability handlers can produce auto-hits without coupling Phase 13C to named abilities;
- Critical Wounds and wound-roll modification are explicit attack events;
- all defender allocation-order, optional Feel No Pain, and defensive reaction choices are player-facing decisions routed through `GameLifecycle.submit_decision(...)`; no defender choice may be made by direct engine helper calls, adapters, tests, or UI code;
- defender-facing requests set the defending controlling player as `actor_id`, are viewer-scoped, and produce deterministic JSON-safe `DecisionRecord`/`EventRecord` payloads;
- forced allocation-order and save paths may resolve automatically only when there is exactly one legal rules outcome and no optional player choice;
- the defender creates allocation groups for the target unit before saves are resolved: one group for each `CHARACTER` model and one group for all other models sharing W, Sv, and InSv characteristics;
- the defender declares an allocation order for those groups, with wounded non-`CHARACTER` groups first, no `CHARACTER` group before a non-`CHARACTER` group, and wounded `CHARACTER` groups before unwounded `CHARACTER` groups;
- the target's controlling player makes one save roll for each attack that wounded the target before model allocation is resolved;
- damage resolution walks save results from lowest result(s) to highest result(s), selecting models from the current allocation group and selecting a wounded model in that group where possible;
- current allocation group transitions only after all models in the prior group are destroyed;
- the allocation step accepts optional attacker-side allocation constraints, such as `[PRECISION]`, so later rules can constrain or override allocation without bypassing `submit_decision(...)`;
- when the current allocation group has an Invulnerable Save, that InSv must be
  used for the save roll and the defender cannot choose to use an armour Save
  instead;
- when the current allocation group has no Invulnerable Save but has a Save,
  armour saves apply AP modifiers against the current allocation group's Sv
  characteristic;
- if neither Invulnerable Save nor Save applies, the save fails and the attack
  inflicts damage;
- Benefit of Cover worsens the attack's BS characteristic by 1 before hit rolls and no longer modifies save rolls;
- the retired AP 0 / Save 3+ cover exception is not part of the 11th Edition ruleset and must be removed from runtime behavior;
- Plunging Fire is a descriptor-driven BS improvement that consumes Phase 13A line-of-sight, height, ground-level target, and `TOWERING` within-12" evidence; unsupported Plunging Fire shapes return typed unsupported diagnostics instead of being silently ignored;
- mortal wounds are allocated one at a time, do not allow saves, and spill over unless the source rule says remaining mortal wounds are lost;
- mortal wounds from attacks are applied after normal damage from that attacking unit, even if the normal damage was saved;
- Feel No Pain rolls are per lost wound, including mortal wounds, and only one Feel No Pain ability can be used per lost wound;
- normal attack excess damage is lost when a model is destroyed;
- WS, BS, Strength, AP, Damage, and random Attacks/Damage characteristics consume existing descriptor/modifier and Phase 10J dice semantics, including reroll windows and characteristic caps/floors;
- Fast Dice Rolling is allowed only when BS/WS, Strength, AP, Damage, abilities, and target are the same and order cannot affect the result;
- random Damage attacks cannot use fast dice in cases where allocation order can affect destroyed/damaged model outcomes;
- model destruction emits removal records and destruction timing windows.

Required tests:

- defender allocation choice is emitted as a `DecisionRequest`, resolved through `GameLifecycle.submit_decision(...)`, replayed from `DecisionRecord`, and redacted or scoped correctly for viewers;
- a save roll of 1 fails before InSv/Sv evaluation;
- Invulnerable Save precedence is mandatory when the current allocation group has
  InSv, with no armour-versus-invulnerable defender choice;
- optional or competing Feel No Pain choices are finite defender `DecisionRequest`s; forced single-source Feel No Pain paths remain engine-owned deterministic rolls;
- stale/drift/malformed defender submissions are rejected without mutation;
- full attack sequence resolves deterministically with no ability handlers installed, and a stub no-op handler proves each typed event hook fires in order;
- hit/wound/save/damage deterministic dice flow;
- Hit roll 6 critical/auto-success and 1 auto-fail;
- Hit modifier cap of +1/-1;
- Wound modifier cap of +1/-1;
- unmodified Wound roll 6/1 and unmodified Save roll 1 semantics;
- Wound roll table boundaries;
- armour save and mandatory invulnerable-save precedence against current
  allocation groups;
- Benefit of Cover worsens BS before hit rolls and never improves saves;
- allocation groups and allocation-order decisions obey wounded-model and `CHARACTER` ordering constraints;
- save rolls are resolved from lowest result(s) to highest result(s);
- a Character wounded by an earlier attacker-constrained allocation remains illegal for a later unconstrained attack while Attached-unit Bodyguard models remain;
- Plunging Fire improves BS only with the required height, `TOWERING`, visibility, and ground-level target evidence and fails explicitly when the selected ruleset does not support it;
- mortal wound spillover and no-save path;
- Devastating/Hazardous mortal-wound lost-remainder exceptions where applicable;
- Feel No Pain per-wound roll path;
- wounded-model allocation priority;
- fast dice group allowed for identical attacks;
- random damage fast dice is rejected where order matters;
- model destruction emits removal records;
- damage allocation payload round-trips.

## Phase 13D: weapon abilities, shooting/fight modifiers, and shooting Stratagems

Status: Complete.

Initial Core Rules weapon ability coverage:

- Assault;
- Rapid Fire X;
- Ignores Cover;
- Twin-linked;
- Close-quarters / Pistol alias;
- Cleave X;
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
- Hunter X;
- Anti-KEYWORD X+.

Initial shooting-coupled Core Stratagem coverage:

- Smokescreen where applicable;
- Explosives;
- Crushing Impact;
- Fire Overwatch from the end-of-opponent-Movement-phase window through Snap Shooting.

Invariants:

- weapon abilities are structured descriptors;
- ability handlers modify the attack sequence only in declared timing windows;
- shooting-coupled Core Stratagems reuse the Phase 12B Stratagem definition, decision, target-binding, CP ledger, and replay contract;
- every shooting-coupled Core Stratagem timing hook is registered through `StratagemCatalogIndex`; Shooting phase code must not scan the full catalog when a shooting event occurs;
- Assault changes shooting eligibility and restricts attacks to Assault weapons after Advance;
- Rapid Fire, Blast, Cleave, Melta, Heavy, Lance, and Indirect Fire modify characteristics/rolls through typed modifier stacks and consume Phase 10J dice/random-characteristic semantics rather than reimplementing dice;
- Twin-linked grants a Wound-roll reroll permission and consumes Phase 10J reroll semantics;
- `[CLOSE-QUARTERS]` modifies close-quarters shooting eligibility, engaged targeting, and weapon selection restrictions; `[PISTOL]` is an exact alias for all rules purposes;
- Torrent bypasses Hit rolls and interacts correctly with Indirect Fire restrictions;
- Lethal Hits and Sustained Hits consume Critical Hit events, and Lethal Hits remains an active-player choice because automatic wounds can prevent Critical Wound abilities;
- Anti modifies Critical Wound thresholds based on target keywords;
- `[HUNTER X]` weapons can only target units that match at least one listed
  keyword in X, including composite keyword lists such as `MONSTER` or
  `VEHICLE`;
- Precision lets the attacking player select one visible `CHARACTER` allocation group at the start of the Allocation Order step; if selected, that group is the current allocation group until those attacks are resolved or that group is destroyed;
- Hazardous tests occur after the unit has resolved all its attacks and make unit-level hazard rolls that allocate mortal wounds through the 11th Edition mortal-wound sequence;
- Devastating Wounds ends the attack sequence for each critical wound and inflicts mortal wounds equal to Damage after normal damage; each critical wound can damage a maximum of one model and any excess mortal wounds from that critical wound are lost;
- Extra Attacks weapons are additional melee weapons and their Attacks cannot be modified unless the modifying rule names that weapon;
- Fire Overwatch source descriptors are bound to the end-of-opponent-Movement-phase out-of-phase shooting host and resolve through Snap Shooting; marker-only effects are forbidden, and the normal Shooting phase state must not be reused as the active player's phase state;
- Smokescreen grants structured, expiring Benefit of Cover effects through Phase 12A effect machinery and expires at the active shooting player's phase endpoint;
- Fire Overwatch, Smokescreen, and other reactive shooting-coupled Stratagem choices remain non-active-player target-proposal decisions under the adapter contract, while Explosives is an active-player Shooting phase target proposal;
- Explosives uses deterministic mortal-wound/damage application records and target binding from the shooting context, rejects Advanced, Fell Back, engaged source, engaged target, out-of-range, and non-visible target contexts before CP spend;
- shooting at `AIRCRAFT` consumes the 11th Edition Aircraft and Plunging Fire exclusions rather than an edition-diff hit modifier policy;
- unsupported weapon ability shapes fail explicitly;
- source IDs are preserved in emitted events.

Required tests:

- each supported weapon ability has at least one focused attack-sequence test;
- each supported shooting-coupled Core Stratagem has decision-contract, CP, target-binding, and replay coverage;
- Fire Overwatch has end-of-opponent-Movement-phase reaction tests proving it creates an out-of-phase Snap Shooting state, rejects out-of-range, engaged, TITANIC, shooting-ineligible, and no-legal-declaration selected friendly unit bindings before CP spend, applies the unmodified-6 hit policy while preserving Torrent auto-hit behavior, emits shooting declaration and attack-sequence decisions through the lifecycle, and resumes the parent reaction frame after completion;
- Smokescreen and Explosives have decision-contract tests from their legal shooting-resolution windows;
- unsupported weapon ability descriptor does not execute;
- Hunter X rejects target declarations that lack every required keyword match and
  accepts declarations with at least one listed target keyword;
- modifier interactions are deterministic;
- random Attacks and random Damage consume Phase 10J dice/reroll semantics;
- Twin-linked cannot reroll a Wound roll twice;
- Indirect Fire applies Benefit of Cover, disables Hit-roll rerolls, and enforces unmodified 1-5 fail or stationary-plus-friendly-visibility unmodified 1-3 fail;
- Close-quarters shooting and shooting at engaged MONSTER/VEHICLE restrictions interact correctly with `[BLAST]` bans;
- Hazardous and Devastating Wounds mortal-wound allocation ordering is correct.
- Fire Overwatch rejects invalid target bindings before CP spend and does not create marker-only effects;
- Smokescreen expires at the correct timing endpoint;
- Explosives rejects invalid target bindings without mutation.

## Phase 13E: damage allocation, destroyed models, and destruction reactions

Status: Complete.

Invariants:

- defender allocation choices are emitted as `DecisionRequest`s unless allocation is forced by the rules;
- optional Feel No Pain source/use and optional destruction-reaction choices remain in the shared adapter decision path and may not be answered by UI/headless/network-specific code; mandatory save routing, including Invulnerable Save precedence, is engine-owned;
- mandatory destruction reactions, including Deadly Demise-style rules, are engine-triggered and are not adapter decline choices;
- Deadly Demise resolves before destroyed-model removal, including its trigger roll, eligible nearby-unit mortal-wound packets, and any routed Feel No Pain choices;
- models destroyed by Deadly Demise mortal-wound packets use the same destroyed-model removal record, transition batch, and destruction-reaction host as attack damage;
- defender allocation and destruction records are viewer-scoped where hidden information can differ;
- defender allocates attacks according to rules;
- wounded models must continue receiving damage where applicable;
- destroyed models are removed with removal records;
- destroyed-model pools remain typed and source-addressable for later healing or
  revival effects, including attached-unit component restoration while the
  attached rules unit still exists;
- destroyed-model reaction windows fire unless the removal cause suppresses them;
- coherency-cleanup removals count as destroyed but do not trigger destroyed rules.

Required tests:

- defender allocation and optional defensive decisions produce `DecisionRecord`/`EventRecord` payloads and replay deterministically;
- stale/drift/malformed defender allocation submissions fail without mutation;
- viewer-scoped projection/event tests cover any hidden defensive or destruction-reaction payloads;
- wounded-model allocation priority;
- destroyed-model removal event;
- destroyed-model pool round-trip supports later healing/revival without object
  reprs or component identity loss;
- destroyed-model reaction timing;
- Deadly Demise failed roll, successful mortal wounds, pre-removal measurement, and Feel No Pain pause/resume ordering;
- Deadly Demise secondary casualties emit removal records, optional reaction requests, and chained mandatory Deadly Demise resolutions deterministically;
- non-triggering coherency cleanup removal.

## Phase 13F: Shooting phase completion gate

Status: Complete.

Required tests:

- full Shooting phase can complete for both players;
- shooting consumes visibility, cover, weapon declarations, attack sequence, damage allocation, and removal records;
- shooting completion waits for all pending attacker, defender, and shooting-coupled reaction decisions to resolve through `GameLifecycle.submit_decision(...)`;
- invalid declarations do not mutate state;
- shooting phase exits only after all selected/eligible units have resolved or skipped.

---

# 11th Edition migration and completed-phase revalidation

Phase 14 is the mandatory 11th Edition revalidation pass for completed Phases 1-13F. These phases are not optional compatibility slices. They must remove or quarantine retired identifiers, assumptions, fixtures, and source-package facts before Phase 15 Charge/Fight work begins.

## Phase 14A: source identity and migration audit

Status: Complete.

Modules:

- `core/ruleset_descriptor.py`
- `core/ruleset.py`
- `rules/source_catalog.py`
- `rules/source_packages/warhammer_40000_11th/`
- `tests/code_quality/`

Invariants:

- `warhammer_40000_11th` is the sole active edition ID;
- source package IDs, source titles, descriptor hashes, fixtures, replay payloads, and docs use 11th Edition identity;
- retired edition strings are allowed only in archived source-reference notes or migration scripts that are explicitly excluded from runtime imports;
- no runtime handler branches on old-vs-new edition behavior;
- source package manifests cite the local 11th Edition Core Rules PDF and app/codex/mission sources when added.

Required tests:

- static audit rejects active runtime/test references to retired edition IDs;
- ruleset descriptor hash is deterministic and 11th Edition-only;
- source package payloads round-trip with 11th Edition IDs;
- no compatibility shim can instantiate a retired ruleset.

## Phase 14B: timing windows, active player, and phase skeleton cutover

Status: Complete.

Invariants:

- battle rounds expose Start of Battle Round, Player Turns, and End of Battle Round windows;
- each turn exposes Start of Turn, the five phases, and End of Turn;
- each phase exposes explicit Start and End windows;
- end-of-phase, end-of-turn, and end-of-battle-round windows resolve non-mission rules before mission rules;
- active/opposing player state follows the 11th Edition selection exceptions for move, shoot, and fight resolution;
- Fire Overwatch and Rapid Ingress anchor to the End of Opponent's Movement phase window.

Required tests:

- timing-window records serialize without object reprs;
- phase/turn/battle-round end ordering is deterministic;
- active player changes during selected unit move/shoot/fight scopes and restores afterward;
- end-of-opponent-Movement reactions are emitted in the correct order.

## Phase 14C: shared primitives cutover

Status: Complete.

Invariants:

- Engagement Range is 2" horizontally and 5" vertically;
- coherency is one-neighbor within 2"/5" plus every-model max spread within 9"/5";
- rotations cost 0" for every base/frame shape;
- retired pivot-cost policy, descriptors, and tests are removed or made audit failures;
- `FRAME` measurement uses closest point on the model rather than base-only measurement;
- `M "-"`, `OC "-"`, and InSv characteristics are represented as typed characteristic values;
- numeric `0` characteristics can be changed by modifiers, but characteristics
  depicted as `-` or replaced by `-` cannot be changed by numeric modifiers;
- Detection Range is a unit characteristic, defaults to 15", is lower-is-better,
  and is consumed by Hidden detection checks;
- halve-damage effects apply after all other Damage modifiers;
- Battle-shocked units use OC "-" semantics, cannot be targeted by controlling-player Stratagems, and cannot start or complete actions;
- hazard rolls are unit-level rolls that allocate mortal wounds through the 11th Edition mortal-wound sequence.

Required tests:

- static audit rejects pivot-cost policy usage;
- Engagement Range and coherency descriptors match the 11th Edition values;
- `FRAME` measurement and rotation witnesses round-trip;
- `0` modifier, `-` modifier rejection, Detection Range modifier, and
  halve-damage-after-modifiers cases are covered by shared characteristic tests;
- Battle-shock persistence and recovery use the Command phase Battle-shock step;
- hazard rolls inflict 1 mortal wound, or 3 mortal wounds when every model is a `MONSTER`/`VEHICLE`.

## Phase 14D: movement, terrain, objectives, and actions cutover

Status: Complete.

Invariants:

- Movement phase selection covers every friendly unit, including units in Strategic Reserves and embarked units;
- Ingress Moves for reserve arrivals are selected inside Move Units, with no
  separate Reinforcements step;
- move-type selection is a finite decision and Remain Stationary triggers no start/end move rules;
- Fall Back mode selection supports Ordered Retreat and Desperate Escape;
- `MONSTER` and `VEHICLE` units can move through friendly and enemy models that
  are not `MONSTER` or `VEHICLE` only when making Normal or Advance moves;
- Flying units can optionally take to the skies for Normal, Advance, and Fall Back movement-phase actions through finite option IDs and parameterized proposal payload context, subtracting 2" unless Hover applies; Charge integration remains a Phase 15 charge-move task;
- terrain areas and Exposed/Light/Dense categories replace retired terrain-feature policies;
- Dense movement, vertical movement, stable non-ground endpoints, Solid, Hidden,
  Gone to Ground, Obscuring, and Benefit of Cover are represented from
  structured terrain descriptors;
- objectives are terrain objectives by default; 40 mm markers are only the fallback when an objective point does not coincide with a terrain area;
- objective markers can be moved through and ended on;
- Secured objectives persist until the opponent's level of control is greater at the end of a phase;
- action start/cancel/complete rules are engine-owned and replay-facing.

Required tests:

- fall-back mode decisions validate battle-shocked and non-battle-shocked cases;
- adapter proposal tests reject stale, drifted, and malformed `movement_mode` and `fall_back_mode` submissions before queue pop where required by the Phase 11D contract;
- reserve-arrival Ingress choices occur during Move Units and use more-than-8"
  enemy-distance validation where applicable;
- Monster/Vehicle model traversal is legal for Normal and Advance moves only and
  remains illegal through other Monster/Vehicle models;
- FLY take-to-the-skies changes pathing and movement budget deterministically;
- terrain visibility and terrain movement consume terrain-area descriptors,
  including Light/Dense Hidden eligibility and Gone to Ground detection modifiers;
- objective-control geometry supports terrain areas and marker fallback;
- action cancellation rejects moves other than pile-in/consolidation and rejects leaving the battlefield.

## Phase 14E: attack sequence and allocation cutover

Status: In progress.

Implemented in the current cutover slice:

- attacks are gathered by target and identical attack profile;
- supported identical fixed-damage shooting pools, including timing-sensitive
  shooting-compatible weapon abilities, use the grouped allocation host:
  Hit and Wound rolls for the pool are resolved before allocation, save rolls
  are made before damage, and failed saves resolve from lowest to highest;
- melee weapon target splitting is declared in the Select Targets step;
- Benefit of Cover worsens BS by 1 before Hit rolls;
- Plunging Fire improves BS by 1 when the 3"+ terrain-height or `TOWERING` within-12" conditions are met and the visible target unit contains a model on ground level;
- unmodified save rolls of 1 fail before InSv/Sv evaluation;
- allocation groups are created from runtime attached-unit role metadata, with
  one group for each eligible Character model and profile groups for
  non-Character models sharing W, Sv, and InSv;
- defender allocation order is automatic when the 11th Edition priority tiers
  force a single order, and uses finite `select_allocation_order` requests only
  when more than one legal same-tier group ordering exists. Request payloads
  include group IDs, model IDs, group role, W/Sv/InSv profile, wounded state,
  Bodyguard/Leader/Support evidence, legality reasons, and Precision priority
  group IDs when applicable;
- if the current allocation group has an Invulnerable Save, that InSv is
  mandatory and the defender cannot choose an armour Save instead;
- armour Saves with AP modifiers are used only when the current allocation
  group has no Invulnerable Save;
- current allocation group damage handles wounded models first and changes to
  the next selected ordered group only after the current group is exhausted or
  destroyed;
- `[PRECISION]` selection is pool-scoped by visible eligible Character
  allocation group. In the grouped host, the attacker-selected Character group
  is promoted to the front of the legal allocation order until those attacks
  resolve or that Character group is destroyed, then remaining failed saves
  return to the normal ordered groups;
- grouped Lethal Hits, Sustained Hits, Anti, Twin-linked, Melta, Torrent, and
  Devastating Wounds preserve critical Hit/Wound timing through the grouped
  host;
- normal damage resolves before routed mortal wounds for mixed sequences;
- `[DEVASTATING WOUNDS]` inflicts mortal wounds equal to Damage after normal damage and cannot spill one critical wound beyond one destroyed model;
- `[CLEAVE X]` is a structured weapon ability descriptor and helper that adds
  X attacks per five target-unit models when one target was selected for all of
  that weapon's attacks. Fight-phase dice gathering will be implemented with
  the Phase 15 melee declaration host;
- derived terrain objectives use terrain-area containment for model
  contribution; the objective marker radius is not used to count models outside
  the terrain area.

Remaining work before Phase 14E can be marked complete:

- integrate melee-only Cleave dice gathering and Lance charge-gated Wound-roll
  modifiers into the Phase 15 Charge/Fight host once melee attack declarations
  and charged-unit state exist.

Implemented tests:

- identical attack grouping and melee split declarations round-trip;
- mandatory Invulnerable Save precedence is covered and emits no defender
  armour-versus-invulnerable choice;
- allocation-order decisions validate stale, wrong-actor, wrong-option, and
  JSON-safe record payloads before mutation;
- allocation-order requests emitted from grouped wound pools carry all wounded
  attack contexts before any save is rolled, and only expose defender choices
  between legal same-tier group orders;
- grouped save rolling occurs before damage, and low-to-high save-result damage
  resolution is deterministic;
- grouped failed-save damage transitions to the next ordered allocation group
  when the current group is destroyed or exhausted;
- grouped Precision promotes the attacker-selected Character allocation group
  before ordinary defender group ordering, then returns remaining failed saves
  to Bodyguard/non-Character groups after that Character group is destroyed;
- grouped Lethal Hits, Sustained Hits, and Devastating Wounds regressions prove
  critical timing, generated-hit wound resolution, post-normal deferred mortal
  wound routing, and one-destroyed-model-per-critical Devastating Wounds caps;
- cover and Plunging Fire modify BS, not AP or saves;
- Precision Character allocation-group selection persists for the current pool
  and returns to ordinary allocation after that selected Character group is
  destroyed;
- derived terrain objective tests prove models outside the terrain area do not
  contribute through the marker control radius;
- Devastating Wounds and hazard mortal wounds allocate through the shared mortal-wound service.

## Phase 14F: shooting cutover

Status: Complete.

Phase 14F completes the shooting-type cutover. The active player selects an eligible unit, then answers the finite `select_shooting_type` decision before the engine emits the parameterized shooting declaration request. The selected shooting type is preserved through declarations, attack pools, replay payloads, supported grouped attack resolution, allocation-order decisions, saves, damage, and Fire Overwatch Snap Shooting. Phase 14E supplies the grouped attack/allocation host used by this shooting cutover.

Indirect and Snap Shooting now attach deterministic no-Hit-reroll rule IDs to Hit-roll specs, and the dice/Command Re-roll paths reject reroll windows for those rolls before mutation. Units that shoot in the Shooting phase are excluded from Mission Action start options until the phase ends through the shared action decision path.

Invariants:

- Shooting type is an engine-enumerated decision: Normal, Assault, Close-quarters, Indirect, or source-provided types such as Snap Shooting;
- in-phase Shooting uses `select_shooting_type` as a finite active-player decision between unit selection and shooting declaration;
- `[CLOSE-QUARTERS]` and `[PISTOL]` are identical for all rules purposes;
- non-`MONSTER`/non-`VEHICLE` close-quarters shooting can only select `[CLOSE-QUARTERS]` weapons and engaged targets;
- `MONSTER`/`VEHICLE` close-quarters and engaged-target shooting apply the correct -1 Hit modifier except for qualifying `[CLOSE-QUARTERS]` attacks;
- `[BLAST]` weapons cannot target engaged units through close-quarters or engaged `MONSTER`/`VEHICLE` shooting;
- Indirect shooting can only declare `[INDIRECT FIRE]` weapon profiles, grants cover, forbids hit rerolls, and has the 1-5/1-3 unmodified fail policy;
- Snap Shooting targets one visible enemy unit within 24", hits only on unmodified 6, and forbids Hit-roll rerolls;
- after a unit shoots in the Shooting phase, it cannot start a Mission Action until the phase ends.

Required tests:

- shooting-type finite decisions reject stale, drifted, wrong-actor, and wrong-option submissions before mutation;
- close-quarters weapon-selection and target restrictions are enforced per model keyword;
- engaged `MONSTER`/`VEHICLE` shooting and `[BLAST]` FAQs are regression-tested;
- indirect and snap policies interact correctly with Torrent, Heavy, cover, supported grouped attacks, and reroll permissions;
- Assault/Advanced, Close-quarters/Blast, Monster/Vehicle, Indirect, Fire Overwatch/Snap, and action-start lock tests exercise the full lifecycle decision path.

## Phase 14G: charge and fight source contract

Phase 14G does not implement Charge/Fight. It freezes the 11th Edition Charge/Fight contract that Phase 15 must implement directly, so there is no temporary retired-edition Charge/Fight path to correct later.

Invariants:

- charge declaration validates within-12", unengaged, no Advance/Fall Back, and battlefield presence;
- charge-target selection happens after the charge roll and requires targets within both 12" and the rolled maximum distance;
- charge moves must end closer to targets, within 1" if possible, engaged if possible, engaged with every target, and not engaged with non-targets;
- charging grants Fights First until end of turn;
- Fight phase has Start, Pile In, Fight, Consolidate, and End steps;
- a unit is eligible to fight if it made a Charge move this turn, was engaged in
  melee at the start of the Fight phase, or is engaged in melee at activation
  time;
- both players make pile-in and consolidation moves, active player first;
- Fights First and remaining combats alternate per the PDF sequence;
- eligible-to-fight pass is available when all of a player's eligible units are more than 5" from enemy units;
- Normal Fight and Overrun Fight are explicit fight types;
- consolidation mode selection supports Ongoing, Engaging, and Objective modes, including opponent fight selection for newly engaged unfought units.

Required Phase 15 tests:

- charge-target and charge-move proposals validate path witnesses and target constraints;
- Pile-in and consolidation use group-aware movement APIs;
- fight eligibility covers charged units, units engaged at Fight phase start, and
  units engaged at activation time;
- Fight selection pass and Fights First fallback ordering are deterministic;
- Overrun Fight cannot be selected unless the unit is otherwise eligible to fight;
- Engaging Consolidation emits opponent fight decisions for newly engaged eligible units.

## Phase 14H: advanced rules cutover

Status: Not implemented. Phase 14D follow-up findings for movement-mode exposure, Fall Back mode payloads, and runtime Mission Action interruption are complete in Phase 14D; the transport, attached-unit, reserve, aircraft, revival, and destroyed-Transport items below remain Phase 14H scope.

Invariants:

- Transport capacity, multiple embarked units, battle-formation Embark, post-move Embark, Rapid/Tactical/Combat Disembark, Emergency Disembark, and destroyed-transport timing are source-backed and replay-facing;
- Embark after the first battle round has started is legal only after a Normal, Advance, or Fall Back move, only if every model is within 3" of a friendly `TRANSPORT`, the unit was not set up on the battlefield this turn, the unit is datasheet-eligible for that Transport, the Transport has sufficient remaining model capacity, and the engine removes the unit from the battlefield into that Transport's cargo state with deterministic removal records;
- Disembark is legal only for a unit embarked within a `TRANSPORT` model that is on the battlefield, only if that unit did not Embark within that Transport this phase, and only if that Transport has not Advanced or Fell Back this phase;
- Disembark uses an explicit source-backed mode enum and replay payload for `rapid_disembark`, `tactical_disembark`, `combat_disembark`, `destroyed_transport`, and `emergency_disembark`; any new adapter-visible mode, option family, proposal payload, or event shape must update `docs/ADAPTER_DECISION_CONTRACT.md` in the same implementation PR;
- Rapid Disembark uses 3" wholly-within setup, is mandatory after the Transport makes a Normal or Ingress move, prevents charges until end of turn, and if the Transport made an Ingress move this turn the disembarking models must inherit the same setup restrictions that constrained the Transport's Ingress placement;
- Tactical Disembark uses 3" wholly-within setup, is mandatory when the Transport remained stationary or has not yet been selected to move and a legal 3" setup exists, forbids Remain Stationary, and immediately routes the unit through the shared Movement phase decision path for a Normal or Advance move;
- Combat Disembark uses 6" wholly-within setup when Rapid/Tactical conditions do not apply, makes one Hazard roll for each model through the shared Hazard/mortal-wound allocation service, can set up engaged only with enemy units that the Transport is engaged with, writes through Battle-shock, and prevents charges until end of turn;
- Emergency Disembark uses 6" wholly-within setup for units embarked in a Transport that was just destroyed, makes one Hazard roll for each model before setup through the shared Hazard/mortal-wound allocation service, requires each model to be set up as close as possible to that Transport, destroys each model that cannot be placed that way, writes through Battle-shock, and prevents charges until end of turn;
- destroyed-Transport Disembark/Emergency Disembark orchestration happens from the real destruction event before Transport removal and before/alongside Deadly Demise resolution according to the source timing, with embarked units not using stale battlefield placements or endpoint-only movement shortcuts;
- Attached units support runtime-instantiated attached rules units from army-list
  Leader and Support declarations, one Leader and one Support per Bodyguard
  unless stated, Bodyguard Toughness for incoming attacks, keyword union without
  model keyword inheritance, source-scoped ability persistence, and
  attached-unit healing/revival;
- Strategic Reserves use 50% points cap, 6" edge setup, more-than-8" enemy distance, pre-third-round opponent-deployment-zone restriction, and third-round destruction exceptions;
- repositioned units preserve move history and persisting effects;
- Surge moves require the source trigger, non-Battle-shocked/unengaged/not-moved state, closest enemy target, no non-target engagement, and no further movement that phase;
- Aircraft start in Strategic Reserves, only make ingress moves, return to Strategic Reserves at the end of the opponent's turn, and follow the PDF charge/fight/Plunging Fire exclusions;
- revived models keep starting wargear/enhancements, cannot exceed starting strength, must set up in coherency with phase-start battlefield models, and can be engaged only with enemies already engaged with the unit;
- healing/revival effects can return destroyed models from a fully destroyed
  Bodyguard component while a Leader/Support component remains in the Attached
  unit, and this must not expand any component or attached rules unit above its
  starting strength.

Required tests:

- each transport mode has valid, invalid, replay, stale/drift/malformed submission, deterministic payload, and viewer-safe event/projection coverage;
- Embark tests cover Normal, Advance, and Fall Back triggers; reject Remain Stationary, units set up this turn, wrong-player or non-Transport targets, datasheet-ineligible units, insufficient capacity, same-phase Disembark-then-Embark without an explicit typed override, and every-model-within-3" failures without mutation;
- Rapid Disembark tests cover post-Normal and post-Ingress Transport movement, 3" wholly-within placement, no-charge state, and inheritance of Ingress restrictions such as enemy-distance and deployment-zone bans;
- Tactical Disembark tests prove a legal 3" setup before a stationary/not-yet-selected Transport forces the Tactical mode, excludes Remain Stationary, routes to Normal/Advance movement through the shared Movement decision path, and rejects Fall Back unless an independent rule makes Fall Back legal;
- Combat Disembark tests prove the 6" setup distance, fallback from impossible Tactical placement, one Hazard roll per model through the shared Hazard/mortal-wound service, Battle-shock/no-charge write-through, and the narrow permission to set up engaged only with enemies engaged with the Transport;
- Emergency Disembark tests prove 6" closest-possible placement, destruction of unplaceable models, Hazard/mortal-wound allocation, Battle-shock/no-charge write-through, replay serialization, and no stale endpoint-only placement acceptance;
- destroyed Transport orchestration tests prove Disembark/Emergency Disembark occurs from actual damage/destruction timing before Transport removal, does not leak through Deadly Demise ordering, and records deterministic placement/removal/damage/action-state effects;
- attached-unit formation is instantiated at runtime from valid army-list
  declarations and emits replay-safe component role metadata;
- attached-unit ability persistence ends when the relevant source model/unit is destroyed and resumes if revived;
- Strategic Reserves and Deep Strike use the more-than-8" horizontal distance policy;
- repositioned units preserve advance/fall-back/disembark history;
- Surge and Aircraft restrictions are regression-tested;
- revival placement honors attached-unit and engagement constraints;
- fully destroyed Bodyguard models can be revived by an attached Leader/Support
  source while the Attached unit still exists, without exceeding starting
  strength.

## Phase 14I: Core Stratagems and core abilities cutover

Invariants:

- Core Stratagem package contains Command Re-roll, Epic Challenge, Insane Bravery, New Orders, Explosives, Crushing Impact, Rapid Ingress, Fire Overwatch, Smokescreen, Heroic Intervention, and Counteroffensive;
- Command Re-roll excludes Leadership and Battle-shock rolls, permits one die of a multi-dice roll except Charge rolls, and consumes Phase 10J reroll semantics;
- New Orders costs 1 CP, can be used only once per game, discards one retained
  Secondary Mission card, and immediately draws one replacement Secondary Mission
  card;
- Heroic Intervention supports Leap to Defend and Into the Fray modes, including the optional +1 CP section;
- duplicate core/weapon ability instances require deterministic controlling-player selection at the timing stated by the PDF;
- keyword-gated weapon abilities apply only to target units with at least one listed keyword;
- `[HUNTER X]` is target eligibility, not an attack modifier: the weapon can
  only be declared into units matching at least one listed keyword;
- core abilities listed in the 11th Edition Core Rules are either implemented with source-backed tests or explicitly unsupported with reason.

Required tests:

- Core Stratagem catalog source IDs and CP costs round-trip;
- each Core Stratagem has target-binding, CP ledger, timing-window, and replay coverage;
- New Orders rejects second use in the same game and emits deterministic
  discard-and-replacement-draw mission deck records;
- duplicate ability selection is deterministic and adapter-visible when a player choice exists;
- Hunter X target declaration accepts at least one listed keyword match and
  rejects target units with none;
- every supported core ability has focused tests and an unsupported-descriptor audit row where not yet implemented.

## Phase 14J: mission and catalog replacement

Invariants:

- mission packs, deployment maps, terrain layouts, actions, scoring, datasheets, keywords, detachments, enhancements, and faction rules are imported as 11th Edition source packages;
- mustering source data follows the 11th Edition order: select Battle Size,
  start Army Roster, choose Faction, select Detachment Rules, select Units, then
  promote Warlord;
- Incursion is 1000 points, 2 Detachment Points, Enhancement Limit 2, and Unit
  Limit 2 doubled for `BATTLELINE`; Strike Force is 2000 points, 4 Detachment
  Points, Enhancement Limit 5, and Unit Limit 3 doubled for `BATTLELINE`;
- detachment point costs are source data, and missing values remain
  awaiting-source rows rather than defaults;
- Leader and Support Attached Units are declared on the army list, Enhancements
  are selected after Attached Units are created, no attached squad can have more
  than one Enhancement, and the Warlord must share the army Faction keyword;
- mission deck source data grants two Secondary Missions per player turn, keeps
  Secondary Missions until scored or discarded, and does not replace ordinary
  Tactical-discarded Secondary Missions immediately;
- retained Secondary Missions have no two-card hand-size cap, ordinary discard
  rewards are once-per-battle-round CP rewards, and New Orders is the explicit
  once-per-game 1 CP replacement-draw exception;
- scoring source data caps Primary at 45 VP, Secondary at 45 VP, and Secondary
  scoring at 15 VP per battle round;
- source imports reuse the existing normalization/ETL boundary but produce 11th Edition package IDs and hashes;
- old source snapshots are not selectable as active game content;
- catalog/reporting distinguishes implemented, unsupported, and awaiting-source rows without silently substituting retired data.

Required tests:

- package hashes are deterministic;
- retired source packages cannot be selected for a new game;
- representative mission/action/scoring rows load from 11th Edition source identity;
- battle-size mustering rows enforce point, Detachment Point, Enhancement Limit,
  Unit Limit, doubled `BATTLELINE`, attachment, Enhancement, and Warlord
  faction-keyword rules;
- Secondary Mission draw/retain/no-hand-size-cap/discard, New Orders
  replacement draw, and 45/45/15 VP caps load from source data and round-trip
  through mission scoring fixtures;
- coverage report groups awaiting-source rows separately from unsupported rule shapes.

## Phase 14K: cutover hardening and static audits

Invariants:

- CI fails on active retired edition IDs, pivot-cost policies, old terrain kinds, old cover save/AP exceptions, optional armour-versus-invulnerable save choice, 1" engagement, old coherency thresholds, Battle-shock auto-expiry, separate Reinforcements phase steps, 9" reserve-arrival enemy-distance policies, replacement draws outside New Orders, retired Core Stratagem names, and old Aircraft minimum-move policy;
- replay fixtures and canonical JSON payloads are regenerated for 11th Edition-only identifiers;
- no adapter, headless, UI, network, AI, or test path can choose a retired ruleset;
- `ARCHITECTURE_V2.md`, `README.md`, and source-package docs agree on 11th Edition-only scope.

Required tests:

- static audits fail on each retired rule-shape identifier;
- representative smoke game reaches the current implemented phase using 11th Edition descriptors only;
- replay determinism holds after fixture regeneration;
- import-linter and decision-contract audits still pass.

---

# Charge and Fight phases

Phase 15 implements Charge/Fight from the Phase 14G source contract. Do not introduce an interim Charge/Fight behavior that conflicts with the 11th Edition migration contract.

## Phase 15A: Charge phase declaration and charge roll

Invariants:

- eligible charging units are derived from state;
- units that Advanced/Fell Back cannot charge unless a rule permits;
- targets are selected according to ruleset descriptor;
- charge roll is deterministic and replay-facing;
- failed charges do not move models.

## Phase 15B: charge movement, terrain, FLY, and endpoint rules

Invariants:

- charge movement consumes pathing, terrain, free-rotation, and coherency validation;
- at least one charging model must satisfy the charge endpoint requirement;
- charge may end in Engagement Range according to charge policy;
- charging over terrain and charging with FLY are distinct policies;
- charge movement emits displacement records;
- charge endpoints use the 2"/5" engagement policy and the 11th Edition charge target constraints; no retired terrain-type engagement exception is retained.

## Phase 15C: fight order, Fights First, and remaining combats

Invariants:

- Fight phase has Fights First then Remaining Combats;
- a unit is eligible to fight if it made a Charge move this turn, was engaged in
  melee at the start of the Fight phase, or is engaged in melee at activation
  time;
- eligible units are selected in correct order;
- charging units and Fight First effects are represented in fight-order state;
- fight interrupts use typed decision metadata.

## Phase 15D: pile-in, melee attacks, and consolidate

Invariants:

- Pile-in and Consolidate are model displacements, not Movement phase actions;
- Pile-in/Consolidate consume movement/pathing/terrain/coherency validators;
- melee target selection follows engagement/eligibility rules;
- melee attack sequence reuses attack-sequence infrastructure;
- consolidation endpoint rules are explicit;
- fight eligibility and melee target selection use the 2"/5" engagement range and the 11th Edition terrain-area policies.

## Phase 15E: fight-phase Stratagems and melee abilities

Initial coverage:

- Heroic Intervention;
- Crushing Impact;
- Counter-offensive;
- Epic Challenge;
- Fight First;
- fight-on-death;
- melee weapon abilities;
- pile-in/consolidate modifiers.

Invariants:

- charge/fight-coupled Core Stratagems reuse the Phase 12B Stratagem definition, decision, target-binding, CP ledger, and replay contract;
- every charge/fight-coupled Core Stratagem timing hook is registered through `StratagemCatalogIndex`; Charge and Fight phase code must not scan the full catalog when a charge/fight event occurs;
- Heroic Intervention uses charge movement validators and requires a `PathWitness` or typed invalid result;
- Crushing Impact uses deterministic dice/mortal-wound records and charge-context target binding;
- Counter-offensive is a fight-order interrupt, not a duplicate private fight-order path;
- Epic Challenge binds to an eligible Character model through explicit model-target binding and records the per-fight restriction separately from matched-play same-Stratagem-per-phase restrictions;
- Fight First, fight-on-death, melee weapon abilities, and pile-in/consolidate modifiers execute through typed timing/effect machinery.

Required tests:

- each supported charge/fight-coupled Core Stratagem has decision-contract, CP, target-binding, and replay coverage;
- each supported charge/fight-coupled Core Stratagem has a phase-progression/reaction-window test proving the Charge/Fight phase emits it from the trigger-keyed index and resolves it through `GameLifecycle.submit_decision(...)`;
- Heroic Intervention rejects endpoint-only movement and accepts only validator-approved `PathWitness` movement;
- Crushing Impact records deterministic dice/mortal-wound results and rejects invalid charge-context targets;
- Counter-offensive interrupts fight order once at the legal timing and resumes the parent fight sequence;
- Epic Challenge validates eligible Character model target binding and enforces its own per-fight restriction separately from matched-play same-Stratagem-per-phase restrictions.

## Phase 15F: Charge/Fight completion gate

Required tests:

- full Charge phase can complete;
- full Fight phase can complete;
- charge movement, pile-in, and consolidate emit displacement records;
- melee attacks can destroy models;
- fight order is deterministic and replay-safe.

---

# Setup, deployment, reserves, and army construction completion

## Phase 16A: deployment rules and deployment-zone placement

Invariants:

- deployment zones come from mission map;
- Attacker/Defender and deployment order are mission/ruleset policy;
- deployed units validate terrain endpoint, coherency, Engagement Range setup restriction, and model overlap;
- deployment emits placement records.

## Phase 16B: redeployments, Scouts, Infiltrators, and pre-battle abilities

Invariants:

- redeployments occur after deployment and before first turn;
- redeploy is removal + placement, not displacement;
- Scout moves are pre-battle displacements and require the unit to start wholly
  within its controlling player's deployment zone before the Scout move is made;
- Infiltrators modify setup legality;
- all pre-battle abilities use timing windows and source IDs.

## Phase 16C: reserves declarations, Strategic Reserves limits, and Deep Strike setup

Invariants:

- Strategic Reserves limits are validated during setup;
- Deep Strike and similar abilities are setup/arrival mechanisms;
- reserve declarations are replay-facing decisions;
- illegal reserve declarations fail before battle starts.

## Phase 16D: leader attachment, enhancements, army construction, and roster legality completion

Invariants:

- mustering order is Battle Size, Army Roster, Faction, Detachment Rules, Units, then Warlord promotion;
- battle size defines points limit, detachment points, enhancement limit, unit limit, and mission-compatible battlefield expectations;
- Incursion is 1000 points, 2 Detachment Points, Enhancement Limit 2, and Unit Limit 2, doubled for `BATTLELINE` units;
- Strike Force is 2000 points, 4 Detachment Points, Enhancement Limit 5, and Unit Limit 3, doubled for `BATTLELINE` units;
- army faction is a selected Faction keyword and every included unit must be legal for that faction or an allowed exception;
- detachment selection spends Detachment Points and grants access to detachment rules, units, Stratagems, and Enhancements; missing detachment point values are explicit awaiting-source data, not defaults;
- the army must include at least one eligible `CHARACTER` model to be Warlord;
- the Warlord must have the same Faction keyword as the rest of the army;
- selected Warlord gains the `WARLORD` keyword;
- unit limits are enforced by Battle Size and doubled for `BATTLELINE` units;
- `EPIC HERO` units are unique and cannot receive Enhancements;
- only `CHARACTER` models can receive Enhancements;
- Enhancement count is capped by Battle Size;
- no unit can have more than one Enhancement;
- each Enhancement must be unique;
- Leader and Support attachments are declared on the army list, not in Declare
  Battle Formations, and mustering turns those declarations into runtime
  attached rules-unit instances rather than only retaining component units;
- Enhancements are selected after Attached Units are created, so the one-Enhancement-per-squad restriction applies across the attached rules unit;
- every Dedicated Transport must start the battle with at least one unit embarked or it cannot be deployed and counts as destroyed during the first battle round;
- Leader attachment restrictions are validated before battle;
- each Bodyguard unit can have at most one Leader and one Support attached unless a rule says otherwise;
- while attached, the runtime-instantiated Attached unit is treated as one unit
  for rules purposes except destroyed-unit triggers;
- coherency for an Attached unit is validated over the attached rules unit's alive models, not per component `UnitPlacement`;
- attacks against Attached units use Bodyguard Toughness until the attacking unit resolves all attacks;
- attacks cannot be allocated to Character models in Attached units until the Bodyguard is destroyed unless a rule such as Precision permits it;
- when Bodyguard or Leader components are destroyed, surviving units split at the correct timing and recover original Starting Strength;
- destroyed-unit triggers for Attached-unit components use only the destroyed component's own keywords.

Required tests:

- Incursion and Strike Force points, detachment points, enhancement limits, and unit limits;
- Epic Hero uniqueness and Enhancement denial;
- Enhancement count, uniqueness, Character-only, and one-per-attached-squad restrictions;
- Dedicated Transport empty-at-start consequence;
- Leader/Support/Bodyguard legal attachment, army-list attachment timing, and
  runtime instantiation of the attached rules unit with deterministic component
  role metadata;
- Warlord faction-keyword requirement;
- Attached-unit coherency uses `UnitGroup.alive_models()`/group-aware placement data across Leader and Bodyguard models;
- Attached-unit Toughness and Character allocation protection;
- Attached-unit split timing after attacks resolve;
- destroyed-unit trigger identity for Leader vs Bodyguard components.

## Phase 16E: pre-battle/setup completion gate

Required tests:

- full setup sequence can complete without deterministic placement bridge;
- deployment, redeploy, reserves, transports, leaders, and pre-battle abilities are resolved through DecisionRequests;
- battle starts only after setup legality is complete.

---

# Wahapedia data ingestion, language parsing, and content coverage

## Phase 17A: Wahapedia source mirror and CSV-to-JSON ETL

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

## Phase 17B: canonical catalog generation from Wahapedia data

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

## Phase 17C: rule language intermediate representation

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

## Phase 17D: generic rule execution handlers

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

## Phase 17E: faction, detachment, enhancement, and army-rule coverage

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

## Phase 17F: broad weapon/wargear/datasheet ability coverage

Invariants:

- wargear abilities are linked only to selected wargear;
- unselected wargear never grants rules;
- selected wargear payload drift is rejected;
- datasheet abilities and weapon abilities use source-linked descriptors and handlers;
- all imported behavior has tests or explicit unsupported status.

## Phase 17G: source-content coverage and unsupported-descriptor audit

Required outputs:

- coverage report for datasheets, abilities, wargear, detachments, enhancements, Stratagems, and army rules;
- list of unsupported descriptors grouped by reason;
- static audit that runtime code does not parse raw source text;
- CI artifact with package hashes and coverage totals.

---

# Human UI, replay, and network

## Phase 18A: local CLI/human DecisionRecord entry

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

## Phase 18B: replay inspection and deterministic replay runner

Invariants:

- replay can load snapshot + event/decision tail;
- replay can step forward deterministically;
- replay drift is detected and reported;
- replay can export human-readable decision/event traces;
- replay can export training-friendly DecisionRecord corpora.

## Phase 18C: local visual game UI

Invariants:

- UI displays battlefield, terrain, units, objectives, phase state, and pending decisions;
- UI submits only `DecisionResult`s;
- UI can visualize movement paths, LoS witnesses, attack allocation, scoring, and Stratagem windows;
- UI never owns authoritative state progression.

## Phase 18D: network/server-authoritative play

Invariants:

- server owns authoritative lifecycle and validation;
- clients render public state and submit decisions;
- hidden information remains hidden from opponent clients;
- network resync preserves replay hash/state hash.

---

# Profiling, AI orchestration, and corpus generation

## Phase 19A: full-game performance profiling, hotspot benchmarks, and throughput budgets

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

## Phase 19B: legal-candidate generation and action-space masking

Invariants:

- every AI candidate is generated from a `DecisionRequest`;
- candidate generation never bypasses authoritative validation;
- illegal candidates are masked before ranking;
- candidate payloads include enough context for training and replay diagnostics;
- bounded search budgets are deterministic and report timeout/skip reasons.

## Phase 19C: hierarchical AI policy orchestration: General, Commanders, Rankers

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

## Phase 19D: headless self-play and DecisionRecord corpus export

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

## Phase 19E: training-data, reward annotation, and evaluation pipeline

Invariants:

- reward profiles are explicit and versioned;
- generated corpora include game result, VP deltas, action context, legal mask, chosen action, and policy metadata;
- evaluation can compare policies on fixed seed/matchup batches;
- training data schema is stable and validated.

---

# Full-game gates

## Phase 20A: full-game rules-compliance matrix

Create a machine-readable coverage matrix mapping 11th Edition Core Rules sections to implementation modules and tests.

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
- Shooting phase, target declaration, Close-quarters shooting, Indirect/Snap shooting, `[CLOSE-QUARTERS]`/`[PISTOL]`, Lone Operative;
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

## Phase 20B: end-to-end full-game regression suite

Required tests:

- full two-player game completes through final scoring;
- replay round-trip at multiple battle rounds;
- no hidden information leaks;
- deterministic same-seed replay;
- multiple terrain layouts;
- multiple army archetypes;
- multiple mission packs.

## Phase 20C: balance/performance/stability soak

Required runs:

- local AI-vs-AI corpus generation;
- long-running replay validation;
- profiling hotspot report;
- unsupported descriptor report;
- crash/failure triage report.

## Phase 20D: release gate for complete 11th Edition CORE V2

Exit criteria:

- all Core Rules coverage rows are either implemented or explicitly unsupported with reason;
- all source-backed mission-pack setup/scoring/terrain/deployment layout rows are implemented or explicitly unsupported with reason;
- full-game regression suite passes;
- headless throughput budget passes;
- replay determinism passes;
- source-content coverage report is generated;
- human CLI can complete a game;
- AI self-play can complete many games;
- UI can inspect and play a local game;
- network authoritative mode can synchronize state and decisions.

---

# Rules coverage map

| Rules area | Planned phase(s) |
|---|---|
| Dice, rerolls, roll-offs | 1, 10J, 10N, 12C, 13C, 15A, 14C, 14I |
| Datasheets and keywords | 9A, 9C, 17A-17G, 14A, 14J |
| Army mustering | 9C, 16D, 17B, 14J |
| Setup sequence | 9B, 11A, 16A-16E, 14B, 14J |
| Deployment zones | 11A, 16A, 14J |
| Redeployments | 10D, 16B, 14H |
| Engagement Range | 10G, 10M, 10N, 10O, 15B, 14C, 14G |
| Unit Coherency | 10G/10H descriptors, 10L runtime, 11E cleanup, 14C |
| Terrain movement | 10F, 10H, 10I, 14D |
| Terrain visibility/cover, including Hidden, Obscuring, Solid, Benefit of Cover, and Plunging Fire | 13A, 13C, 14D, 14E |
| Movement phase Move Units | 10B-10T, 14D |
| Movement phase reserve arrivals and Ingress Moves | 10P, 14D, 14H |
| Transports | 10Q, 14H |
| Aircraft | 10R, 14H |
| Command phase | 11C, 14B, 14C |
| Battle-shock | 11C, 12B, 14C |
| Mission scoring | 11A-11C, 11E-11F, 14J |
| Stratagems | 12B, 12C, 13D, 15E, 17E, 14I |
| Shooting phase | 13A-13F, 14E, 14F |
| Weapon abilities | 8D, 13D, 17F, 14I |
| Aura abilities | 17C, 17D, 17F |
| Charge phase | 15A, 15B, 14G |
| Fight phase | 15C-15F, 14G |
| Leader/attached units | 6, 16D, 17A, 14H |
| Faction/detachment/enhancement rules | 17C-17F, 14J |
| Mission packs | 11A, 11E, 11F, 16A, 20A, 14J |
| Adapter/UI contract | 11D, 12B, 14D-14I |
| Human CLI/UI | 18A, 18C |
| Network play | 18D |
| Replay | 18B, all state-changing phases |
| AI/headless self-play | 19B-19E |
| Performance budgets | 10U, 19A |
| 11th Edition migration/revalidation | 14A-14K |
