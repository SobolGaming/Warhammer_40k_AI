# Adapter Decision Contract

Status: Phase 11D contract with Phase 11E scoring projection/event-stream additions, Phase 12A reaction/sequencing decisions, Phase 12B Stratagem decision requirements, Phase 12C supported Core Stratagem handler requirements, Phase 13/14H shooting decision requirements, Phase 14B End of Opponent's Movement phase reaction timing, Phase 14J Tactical secondary score/retain decisions, Phase 14L ranged attack target/group gathering decisions, Phase 15A charge declaration decisions, Phase 15B Charge Move proposal decisions, Phase 15C fight activation/pass/interrupt decisions, Phase 16A deployment setup decisions, Phase 16B redeploy/Scout and catalog RuleIR pre-battle decisions, Phase 16C reserve declaration decisions, Phase 16E setup completion gate requirements, Phase 17G setup faction-rule decisions, Phase 17G Cult Ambush Resurgence and marker ingress decisions, Phase 17G fight activation ability decisions, Phase 17G Fight-start faction-rule and catalog RuleIR decisions, Phase 17G Shooting-start faction-rule decisions, Phase 17K catalog once-per-battle ability choices, Phase 17K catalog named-weapon and Shooting-start selected-target ability choices, Phase 17K catalog post-shoot hit-target status/effect choices, Phase 17K catalog move/setup-completed mortal-wound target choices, Phase 17K catalog setup-reactive shoot/charge choices, Phase 17G Movement-end surge decisions, Phase 17G phase-end objective-control retention, Phase 17G advance-triggered and selected-to-shoot/fight grant decisions, Phase 18A hybrid catalog/live unit-model display projection requirements including datasheet ability display, InSv display, and per-model wargear IDs, Phase 18B trigger opportunity-window and interface-intent requirements, Phase 18C shared adapter session facade requirements, Phase 18E-18H formal session, command, reconnect, and authorization semantics, Phase 18I interaction metadata, Phase 18J battlefield coordinates, Phase 18L persistence/recovery semantics, and weapon keyword gap updates for `[PSYCHIC]`, `[ONE SHOT]`, slash-separated `[ANTI]`, and `[ANTI-NON-X]`. This document is authoritative for adapter/proposal modules shipped with Phase 11D and future decision work.

This document is the Phase 11D submission contract, extended with Phase 11E scoring visibility rules, Phase 12A timing/reaction/sequencing rules, Phase 12B Stratagem decision rules, Phase 12C supported Core Stratagem handler rules, Phase 13/14H shooting decision rules, Phase 14B End of Opponent's Movement phase reaction timing, Phase 14J Tactical secondary score/retain decisions, Phase 14L ranged attack target/group gathering decisions, Phase 15A charge declaration decisions, Phase 15B Charge Move proposal decisions, Phase 15C fight activation/pass/interrupt decisions, Phase 16A deployment setup decisions, Phase 16B redeploy/Scout and catalog RuleIR pre-battle decisions, Phase 16C reserve declaration decisions, Phase 16E setup completion gate requirements, Phase 17G setup faction-rule decisions, Phase 17G Cult Ambush Resurgence and marker ingress decisions, Phase 17G fight activation ability decisions, Phase 17G Fight-start faction-rule and catalog RuleIR decisions, Phase 17G Shooting-start faction-rule decisions, Phase 17K catalog named-weapon and Shooting-start selected-target ability choices, Phase 17K catalog post-shoot hit-target status/effect choices, Phase 17K catalog move/setup-completed mortal-wound target choices, Phase 17K catalog setup-reactive shoot/charge choices, Phase 17G Movement-end surge decisions, Phase 17G phase-end objective-control retention, Phase 17G advance-triggered and selected-to-shoot/fight grant decisions, Phase 18A hybrid catalog/live unit-model display projection requirements including datasheet ability display, InSv display, and per-model wargear IDs, Phase 18B trigger opportunity-window/interface-intent requirements, Phase 18C shared adapter session facade requirements, Phase 18E-18H formal session semantics, Phase 18I interaction metadata, Phase 18J battlefield coordinates, Phase 18L persistence/recovery semantics, and weapon keyword gap updates for `[PSYCHIC]`, `[ONE SHOT]`, slash-separated `[ANTI]`, and `[ANTI-NON-X]` for teams building UI, CLI, headless, network, replay, or AI adapters around CORE V2.

Phase 17N Step 4 extends that scoring contract with public persistent Primary
Mission progress, the shared finite Primary Mission choice family, the ten
source-backed Primary Mission Actions, and deterministic turn-boundary,
event-stream, and replay requirements.

Phase 17N Step 5B adds no new adapter-facing decision types, finite option
families, proposal kinds, or payload shapes. Marker scoring consumes the
Step 5A `PrimaryScoringStateEvidence` registry; public VP rows still expose
only opaque evidence ID/hash commitments. Replay remains
`replay-artifact-v8-phase17n-step5a`.

Phase 17N Step 5C adds no new adapter-facing decision types, finite option
families, proposal kinds, or payload shapes. Completed-action scoring consumes
the same Step 5A evidence registry and replay artifact.

Phase 17N Step 5D adds no new adapter-facing decision types, finite option
families, proposal kinds, or payload shapes. Condemned-departure scoring
consumes the same Step 5A evidence registry and replay artifact.

Phase 17N Step 5E adds no new adapter-facing decision types, finite option
families, proposal kinds, or payload shapes. Operation-marker scoring consumes
the same Step 5A evidence registry and replay artifact.

Phase 17N Step 5F adds no new adapter-facing decision types, finite option
families, proposal kinds, or payload shapes. Surveil scoring consumes
the same Step 5A evidence registry and replay artifact, including persisted
battlefield-departure lineage while an Attached Unit retains one canonical
identity through component loss.

Phase 17N Step 5G adds no new adapter-facing decision types, finite option
families, proposal kinds, or payload shapes. Pairing certification drives the
existing Step 4 choice family and Step 5A evidence registry through
`LocalGameSession` for all 45 A/B/C pairing-layout rows in both ordinary scoring
directions, for 90 independent cases. Public VP rows still expose only opaque
evidence ID/hash commitments. Each case starts at an engine-owned
fight-activation decision boundary, round-trips the existing
`replay-artifact-v8-phase17n-step5a` payload, and requires exact `ReplayRunner`
reproduction of its decision and event histories through the ordinary scoring
boundary. No replay schema or adapter submission contract changes.

Phase 17N Step 6 scores all 18 Secondary Mission cards through source-backed
turn-end awards and adds four finite Command-phase setup decisions:
`resolve_tactical_secondary_when_drawn`, `select_tempting_target_objective`,
`select_beacon_unit`, and `select_burden_of_trust_guard`. When Drawn, Beacon,
and Burden of Trust requests are owner-secret. Tempting Target is a public
opponent choice. Tactical score/retain still uses
`score_tactical_secondary_mission`. Replay remains
`replay-artifact-v8-phase17n-step5a`. This does not claim Phase 17N overall
complete or Phase 20A.

The short rule:

All clients share the same authoritative submission contract. Adapters may differ only in how they render, choose, transmit, or generate submissions. No adapter gets a private mutation path, a private rules path, or a bypass around replay-facing `DecisionRecord` and `EventRecord` generation.

## Scope

This contract is used by:

- local human UI;
- networked human UI;
- CLI or terminal human adapters;
- headless AI adapters;
- networked AI clients, if supported later;
- replay and test drivers.

The engine-facing path is shared:

1. The engine emits a `DecisionRequest`.
2. An adapter chooses a finite option or creates a parameterized payload.
3. The adapter converts that choice into a `DecisionResult`.
4. The lifecycle validates the result against the pending request.
5. The engine applies rule validators and mutates authoritative state only after validation succeeds.
6. The engine records deterministic `DecisionRecord` and `EventRecord` payloads.

Adapters are producers of answers. The engine remains the owner of validation, mutation, events, and replay records.

## Phase 17O capability manifest

`LocalGameSession.support_profile()` emits the
`support-profile-v4-directed-primary` payload family and includes the versioned
`capability-manifest-v2-directed-primary` member. Its canonical
language-neutral schema is
`contracts/schemas/capability-manifest.schema.json`. Clients
may use this manifest to disable or explain UI flows, but it never grants roster
legality, accepts a proposal, or mutates authoritative state.

Every roster, unit, rule, mission, and geometry row records all eight capability
dimensions: `LOADABLE`, `DISPLAYABLE`, `MUSTERABLE`, `PHYSICALLY_PLAYABLE`,
`SEMANTICALLY_EXECUTABLE`, `FULL_GAME_SUPPORTED`, `NETWORK_SAFE`, and
`REPLAY_VERIFIED`. Load support and semantic execution remain separate fields.
A descriptor, generic IR payload, source-only module, or heuristic model height
is therefore visible as evidence without being promoted to executable or
certified gameplay support. Unsupported rule effects carry stable rule-row and
source IDs plus a reason code.

The support-profile response is viewer scoped in the shared redaction module.
Players and coaches receive only their roster, unit, rule, geometry, unsupported-
effect, count, selection-hash, and certification projection; administrators
receive the omniscient fixture. Mission, ruleset, catalog, engine, contract, and
neutral interaction identities remain common. A viewer selection hash covers
that viewer's complete canonical muster request plus a digest of the complete
public mission setup; owned roster or public mission changes therefore change
the hash, while opponent-only changes do not. Clients must not infer hidden
opponent selection from a missing row or compare viewer hashes across scopes.

Phase 20A and Phase 20D claim booleans are mechanically derived from explicit
capability and certified-scenario/replay evidence. With no such evidence, the
claims are false even if the legacy support-profile envelope says `playable` or
the setup smoke is eligible. Viewer projection never promotes either
authoritative boolean. It recomputes visible blocker detail and uses explicit
redacted-blocker reason codes when an authoritative blocker is not visible.

## Phase 18I interaction metadata

Every visible `DecisionRequestViewPayload` emitted by the shared projection path
contains an `interaction` descriptor authored by
`engine.interaction_metadata`. Hidden pending decisions contain
`interaction: null`. Projection, CLI, network, TypeScript, replay, and UI
consumers select an input renderer from `interaction_kind`; they do not branch
on `decision_type`, option labels, rule text, display names, or arbitrary
payload keys to discover what input is required.

The descriptor is versioned as `interaction-descriptor-v2-variants` and carries:

- a presentation-neutral `interaction_kind` and finite/parameterized
  `submission_kind`;
- the semantic `proposal_kind` when a parameterized answer is required;
- engine-selected entity IDs and neutral `required_inputs`; multi-variant
  interactions leave the top-level input list empty and publish the inputs on
  each variant;
- one or more `submission_variants`, each with a stable variant ID, interaction
  kind, required inputs, proposal schema reference, and neutral display label;
- typed assistive constraints, including candidate option IDs, entity kinds,
  selection cardinality, movement distance, model count, coherency and
  Engagement Range hints, placement kinds, the public finite/parameterized
  wrapper schema reference, and a separate exact proposal schema reference;
- optional presentation text under `display_hints`.

The standard kinds are finite option list, entity selection, weapon allocation
matrix, dice selection, ordered sequencing, battlefield point placement, model
pose placement, multi-model placement, path editor, roster construction,
confirmation, quantity selection, and opportunity window. They name interaction
semantics, not framework components. A frontend may map them to any local
renderer.

`constraints` and `display_hints` are assistance only. They do not grant
legality, authorize a player, replace the canonical proposal schema, or bypass
engine validation. Every answer still selects one emitted finite option ID or
submits the typed wrapper referenced by `submission_schema_ref`. Parameterized
clients validate the body against the selected variant's `proposal_schema_ref`;
stale metadata fails through the ordinary request/revision/proposal checks.
`minimum_selections` and `maximum_selections` are nullable: `null` means the
engine cannot state a safe exact cardinality from request metadata, not one.

Interaction registration is fail closed. The decision dispatch contract exposes
one or more interaction kinds for every registered decision family, the
registry-derived `family-coverage.json` artifact records exact coverage, and the
support profile publishes the same set. CI collects the renderer-kind union from
every conformance request's `submission_variants` and requires that exact set to
match the dispatch contract, family inventory, and support-profile row, in
addition to comparing the global inventory with the engine enum and JSON Schema. The documented
nested weapon-ability request carries the same descriptor inside the parent
proposal and in the typed top-level `nested_interaction_requests` projection
field. The canonical parameterized union includes distinct Cult Ambush
`place_marker` and `no_marker` variants plus return-on-death placement. A new
decision family, interaction kind, variant, or parameterized payload cannot pass
the contract gate without updating this document, the engine registry,
schemas/examples, generated TypeScript models, and viewer-redaction coverage.

The committed `interaction-conformance.json` artifact is generated from the
dispatch registry, the documented nested family, and every parameterized
proposal fixture. The TypeScript test consumes the generated request and
submission models, constructs every case, and validates the wrapper plus exact
proposal schema without importing Python or switching on decision type.
Because Contract 11 makes physical ranged-weapon identity mandatory in the
canonical shooting proposal, this wrapper is versioned as
`interaction-conformance-v3-weapon-instances`. Contract 10 consumers must not
accept it as the former v2 wrapper.

Interaction descriptors are part of viewer projection hashes and replay
checkpoints. The same pending engine request therefore selects the same renderer
and public submission schema after reconnect or replay, while an opponent-hidden
request reveals no interaction kind, entity count, constraint, or schema-ref
oracle.

## Pre-session army-list input

A player-provided army list is pre-session input, not a separate mutation or
decision path. Adapters normalize the external roster once into a versioned
`PlayerArmyList` JSON artifact and call
`army_muster_request_from_player_army_list(...)`. The resulting strict
`ArmyMusterRequest` is the only roster input passed to `GameConfig` and the
ordinary setup lifecycle.

`GameConfig.model_geometries` is an optional, sparse tuple of accepted,
source-attributed `ModelGeometryCatalogRecord` overrides. When present, every
record must reference a model profile in the accompanying `army_catalog`, but
the tuple may cover only the selected profiles for which reviewed geometry is
available. The accepted records flow unchanged through setup mustering,
support-profile evaluation, runtime content activation, and replay
serialization. A selected profile without a record retains its explicit
heuristic height provenance and remains a physical-playability blocker; it does
not prevent accepted records for other selected profiles from being used. The
create-session schema accepts the corresponding optional, non-empty
`model_geometries` array. Omission is the explicit legal state for a
configuration with no reviewed model geometry. Adapters must not invent
measurements, silently replace an absent reviewed record, or send an empty array
as a substitute for omission.

Unit-scoped resources obtained through optional wargear are selected through
the ordinary `UnitMusterSelection.wargear_selections` contract. Adapters submit
the source-backed wargear option ID, wargear ID, model profile ID, and
`selection_count`; they do not submit an authoritative resource balance.
`UnitMusterSelection` therefore has no `starting_resources` field and rejects a
payload that supplies one. The engine validates the complete selection against
the datasheet option's scaled selection limit, then derives
`UnitInstance.starting_resources` and the initial resource ledger. For Aspect
Shrine Tokens, the source row permits one selected token for every five models
in that component unit, so a 5-model unit can select at most one and a 10-model
unit at most two. This datasheet option is independent of detachment choice.
Lifecycle rehydration remusters from the roster selections and rejects any
drift between those derived allocations, unit payloads, and initialization
transactions.

The artifact must carry a selected `force_disposition_id`, Battle Size,
detachment selection, source IDs, declared points for every unit, declared
total points, and the exact MFM package identity used to price it. The engine
recalculates repeated-datasheet brackets, wargear, and Enhancement or Upgrade
costs, rejects any per-unit or total drift, and populates separate source-backed
`RosterUnitPointValue` and `RosterEnhancementPointValue` records. The artifact
`units` array order is authoritative for repeated-datasheet copy numbering; unit
identifiers do not affect price brackets. `points_source_package_id` and both
point-record families survive `ArmyMusterRequest` and `ArmyDefinition` payload
round trips, and mustering rejects catalog Enhancement price drift instead of
switching point authorities. An optional `game_result` is historical/training
metadata and is omitted for an ordinary pre-game list. During mustering, the
engine rejects a Force Disposition not granted by one of the selected
detachments. Adapters must not infer a default Force Disposition, reorder units,
accept stale point totals, or mutate an army from the artifact directly.

## Core Objects

The shared contract uses these objects and payloads:

- `AdapterGameSession`: public session facade implemented by
  `LocalGameSession` and consumed by CLI, UI, network, headless, and replay
  producer adapters. It is the adapter-facing route to lifecycle advancement,
  viewer-safe projection, source-hashed catalog projection, viewer-scoped event
  deltas, finite submissions, and parameterized payload submissions.
- `SessionPersistenceArtifact`: closed, content-addressed operator-only root
  containing the verified runtime-tree build identity, contract identities,
  authorization bindings, protected cursor state, complete authoritative
  sessions and unpruned revision commitments, the game/session index, and one
  canonical content hash. It is not adapter-visible wire state.
- `LocalGameSession` persistence checkpoint: adapter-owned recovery payload
  binding the current lifecycle, optional initial replay lifecycle, source
  identity, RNG state, latest replay artifact, and deterministic lifecycle,
  decision, event, RNG, and content hashes. Transport code does not reconstruct
  lifecycle internals itself.
- `PlayerArmyList`: versioned, fail-fast pre-session roster artifact containing
  normalized roster selections, one explicit Force Disposition, declared point
  totals, deterministic pricing order, and source/app provenance; post-game
  result metadata is optional.
- `ArmyMusterRequest`: strict engine roster request produced from a validated
  player army list and consumed by the shared setup lifecycle, including the
  authoritative MFM package and unit plus Enhancement/Upgrade point ledger.
- `DecisionRequest`: engine request for one player choice.
- `FiniteOptionSubmission`: adapter wrapper for selecting one finite option.
- `ParameterizedSubmission`: adapter wrapper for submitting JSON-safe proposal payloads.
- `DecisionResult`: engine-facing result created from a submission and pending request.
- `DecisionRecord`: replay-facing record of a request/result pair.
- `PrimaryMissionChoiceData`: strict JSON-safe finite-choice payload binding
  one Primary Mission timing, actor, source descriptor/rule, legal target set,
  selected target set, evidence set, and optional subject or source Action.
- `PrimaryMissionProgressState`: public, replay-safe Primary Mission audit state
  containing persistent/tombstoned markers, historical Punishment condemned
  selections, and active/consumed Consecrate designations.
- `ProposalRequestPayload`: neutral parameterized physical-action request embedded inside a `DecisionRequest.payload`.
- `MovementProposalPayload`: parameterized movement answer, including `PathWitness`, `movement_mode`, and the explicit `fall_back_mode` when Fall Back was selected.
- `TriggeredMovementSelection`: finite triggered-movement answer selecting one
  engine-emitted eligible unit for a source-backed movement reaction or the
  deterministic decline option.
- `SurgeMoveProposal`: Movement phase parameterized movement answer containing
  `proposal_kind: "surge_move"`, action `surge_move`, the selected reacting
  unit, source trigger context, and a `PathWitness` for every moved model.
- `ChargeRollResult`: replay-safe Charge phase roll payload containing the declared charging unit, 2D6 maximum distance, and post-roll reachable target snapshot for the later Charge Move proposal.
- `ChargeMoveProposal`: Charge phase parameterized movement answer containing the proposal request ID, `proposal_kind: "charge_move"`, charging unit ID, `movement_phase_action: "charge_move"`, `movement_mode: "charge"`, selected reachable charge target IDs, and a `PathWitness` unless the player submits the no-move choice.
- `FightPhaseState`: replay-safe outer Fight phase envelope containing battle round, active player, Start/Pile In/Fight/Consolidate/End step exposure, and the active Fight, movement, or attack sub-state reference.
- `FightOrderState`: replay-safe Fight-step ordering state nested under `FightPhaseState`, containing the Fight-step-start engagement snapshot, current ordering band, next chooser, Fights First sources, activations, passes, and resolved fight interrupt records.
- `FightActivationSelection`: finite Fight phase activation answer selecting one engine-emitted eligible unit and explicit `fight_type` (`normal` or `overrun`).
- `EligibleToFightPass`: finite Fight phase pass answer available only when all eligible units for the acting player are more than the source-backed pass distance from enemy units.
- `FightInterruptRequest`: reaction-queue fight interrupt payload emitted at legal Fight timing and answered by decline or by selecting one emitted eligible unit/fight-type option.
- `ResolvedFightInterrupt`: replay-safe fight interrupt consumption record containing the trigger-specific interrupt ID and the underlying source effect ID consumed for this Fight phase.
- `FightActivationAbilitySelection`: finite selected-to-fight ability answer selecting one engine-emitted optional ability option or the deterministic decline option before melee declaration.
- `FightUnitSelectedGrantSelection`: finite selected-to-fight grant answer selecting one engine-emitted optional grant option or the deterministic decline option before melee declaration.
- `FactionRuleFightPhaseStartSelection`: finite Fight-start faction-rule answer selecting one engine-emitted source-backed option before the normal `FightPhaseState` opens.
- `CatalogOncePerBattleAbilitySelection`: finite Fight-start catalog RuleIR answer selecting
  use or decline for one engine-emitted, source-model-scoped once-per-battle activation.
- `CatalogAnyPhaseOncePerBattleAbilitySelection`: finite start-of-phase catalog RuleIR answer
  selecting use or decline for one engine-emitted, source-model-scoped any-phase
  once-per-battle activation.
- `FactionRuleShootingPhaseStartSelection`: finite Shooting-start faction-rule answer selecting one engine-emitted source-backed option before the normal `ShootingPhaseState` opens.
- `CatalogNamedWeaponAbilityChoiceSelection`: finite Shooting-start catalog RuleIR answer selecting one engine-emitted weapon ability option for one source-backed unit/model named-weapon group before the normal `ShootingPhaseState` opens.
- `CatalogShootingStartSelectedTargetEffectSelection`: finite Shooting-start catalog RuleIR answer selecting one engine-emitted eligible friendly target, or declining an optional ability, for a source-backed selected-target effect before the normal `ShootingPhaseState` opens.
- `CatalogPostShootHitTargetStatusSelection`: finite post-attack catalog RuleIR answer selecting one engine-emitted enemy unit hit by the just-completed Shooting attack sequence for a source-backed contextual status denial.
- `CatalogPostShootHitTargetEffectSelection`: finite post-attack catalog RuleIR answer selecting one engine-emitted enemy unit hit by the just-completed Shooting attack sequence for generic source-backed phase-scoped RuleIR effects.
- `CatalogPostFightHitTargetEffectSelection`: finite post-attack catalog RuleIR answer selecting one engine-emitted enemy unit hit by the just-completed Fight attack sequence for generic source-backed persistent RuleIR effects.
- `CatalogUnitMoveCompletedMortalWoundsTargetSelection`: finite Movement or Charge phase catalog RuleIR answer selecting one engine-emitted eligible enemy rules unit, or declining an optional ability, after a source unit is set up or completes a supported move for per-model mortal-wound resolution.
- `CatalogMovementTargetPairSelection`: finite Movement phase catalog RuleIR answer selecting one engine-emitted eligible friendly/enemy rules-unit pair, or declining the current timing edge, when a source model starts or ends a move.
- `CatalogSetupReactiveShootChargeSelection`: finite opponent-Movement-end catalog RuleIR answer selecting `decline`, `shoot`, or `charge` for a source-backed setup-reactive ability after an enemy unit is set up within the source range.
- `ShootingUnitSelectedGrantSelection`: finite selected-to-shoot grant answer selecting one engine-emitted optional grant option or the deterministic decline option before shooting type selection.
- `FightMovementProposal`: Fight phase Pile In or Consolidate movement answer containing proposal kind `pile_in` or `consolidate`, the selected fight movement mode/action, selected target unit or objective context, and a `PathWitness` unless the player submits the no-move choice.
- `ModelDestructionCauseAuthority`: engine-private, producer-owned
  Fight/Shooting history persisted as a typed inventory in `GameState`.
  Cause-aware attack and rule-destruction producers reserve and finalize a cause
  before emitting `model_destroyed`; cause-aware mortal-wound producers register
  a finalized cause before that emission. A `model_destroyed` event carrying
  `model_destruction_cause_id` consumes the cause exactly once. Generic
  destruction producers outside this typed boundary remain valid without that
  field, but every Fight On Death continuation requires an exact consumed cause.
  Cause IDs and authority records are evidence, not adapter-facing choices or
  projection state.
- `ModelLogicalDeathRecord`: engine-private event evidence emitted at the exact
  transition where a living model reaches zero wounds or a direct rule destroys
  it. The closed record binds the model and physical/rules-unit identities,
  event-time placement, placement-retention policy, and either the exact
  `DamageApplication` or direct-rule source. A destruction cause must claim that
  exact boundary before its later `model_destroyed` removal event. Mortal-wound
  routing may carry the boundary inside pending Feel No Pain progress until the
  packet can register its final cause. Raw replay retains this evidence, while
  shared adapter redaction hides the event from every viewer.
- `MeleeDeclarationProposalRequest`: Fight phase parameterized request exposing current melee weapon options, model-engaged target snapshots, the source activation decision context, and ruleset descriptor hash.
- `MeleeDeclarationProposal`: Fight phase parameterized answer selecting each fighting model's primary melee weapon, optional `[EXTRA ATTACKS]` weapons, and target allocations for those melee weapons.
- `PsychicAttackModifierIgnoreSelection`: finite Shooting/Fight attack-sequence answer selecting one engine-emitted way to keep or ignore current `[PSYCHIC]` weapon skill and hit-roll modifiers for the active attack context.
- `DiceResultOverrideRequestPayload`: finite Shooting/Fight/out-of-phase
  attack-sequence request answered with `decline` or `use` for one source-backed
  unit resource after all reroll opportunities and before the Hit or Wound
  result is emitted.
- `PlacementProposalPayload`: parameterized placement answer, including either one attempted physical `UnitPlacement` or one grouped `RulesUnitPlacement` for an attached rules unit.
- `CatalogModelMaterializationPlacement`: parameterized placement answer for an
  engine-instantiated set of models being added to an existing physical owning
  unit by source-backed RuleIR.
- `CultAmbushMarker`: replay-safe Genestealer Cults marker state used by the Cult Ambush marker placement and ingress contracts.
- `DeploymentPlacementRequest`: Deploy Armies parameterized request context containing source mission setup, owning deployment zone IDs, selected rules-unit/component/model IDs, ruleset hash, and setup-step context.
- `DeploymentPlacementProposal`: Deploy Armies placement answer containing the complete selected rules-unit model placement set, placement kind `deployment`, proposal request ID, ruleset hash, and replay-safe source context.
- `BattleFormationDeclarationState`: Declare Battle Formations reserve declaration state containing the next player, completed players, and per-player available reserve declaration counts.
- `AttachedUnitFormation`: deterministic muster-time Leader/Support formation payload containing
  bodyguard, Leader, Support, and complete component unit instance IDs. Its
  `attachment_source_ids` field carries the sorted source IDs of the exact catalog
  attachment targets accepted by the engine. Adapters and replay consumers may display or
  audit this evidence but must not infer, add, or mutate attachment legality from it.
  Each catalog attachment-target payload also carries sorted `required_wargear_ids`; an empty
  list means the target has no loadout gate. List-validation and mustering compare those IDs
  with the engine-instantiated source unit before creating a formation. Adapters may render the
  requirement but must not decide that a loadout satisfies it or fabricate a formation locally.
- `FactionRuleState`: deterministic replay-safe setup state for faction-rule selections, keyed by player, faction, source rule, state kind, setup request, and setup result.
- `FactionRuleSetupSelection`: finite setup answer selecting one engine-emitted option from a faction runtime hook during `declare_battle_formations`.
- `ReserveDeclarationRequest`: finite setup request context for declaring Strategic Reserves or Deep Strike units during `declare_battle_formations`.
- `ReserveDeclarationSelection`: finite reserve declaration answer selecting one emitted reserve declaration option or `complete_reserve_declarations`.
- `PreBattleProposalRequest`: redeploy and Scout pre-battle parameterized request context containing setup step, source decision context, selected rules-unit/component/model IDs, owning deployment-zone payloads, source rule ID, action kind, proposal kind, and ruleset hash.
- `PreBattlePlacementProposal`: redeploy or Scout reserve setup placement answer containing the complete selected rules-unit model placement set, placement kind, action kind, source rule ID, and replay-safe source context.
- `ScoutMoveProposal`: Scout Move answer containing action kind `scout_move` or `dedicated_transport_scout_move`, source rule ID, selected Scout distance, and a per-model `PathWitness`.
- `PreBattleActionRecord`: deterministic replay-safe setup action record for redeploy completion, redeploy placement, pre-battle completion, Scout reserve setup, Scout Move, and Dedicated Transport Scout Move.
- `PreBattleAlternationCursor`: source-linked, lifecycle-persisted `resolve_prebattle_actions` cursor containing first-turn order, the next eligible player, resolved-action count, and last resolved action/unit identity.
- `SetupCompletionGate`: engine-owned setup-to-battle audit invoked only by lifecycle advancement at the final setup step.
- `SetupLegalityReport`: deterministic readiness report containing typed setup completion violations, decision-drain state, and pre-battle readiness snapshot.
- `SetupReplayCheckpoint`: deterministic state checkpoint emitted before and after battle start.
- `BattleStartRecord`: deterministic battle-start payload emitted when setup completion succeeds.
- `ProposalValidationResult`: typed valid, invalid, stale, or unsupported diagnostics.
- `EventRecord`: deterministic event-log payload.
- `GameViewPayload`: read-only viewer projection for adapters.
- `RulesCatalogViewPayload`: cacheable source-hashed static catalog display
  projection for datasheets, datasheet abilities, model profiles, weapon
  profiles, factions, detachments, enhancements, wargear, wargear options, and
  base sizes.
- `RulesCatalogReferencePayload`: live-game reference to the static catalog
  projection used by a `GameViewPayload`.
- `EventStreamDeltaPayload`: viewer-scoped adapter event delta.
- `SecondaryMissionCardState`: reveal-gated Fixed/Tactical secondary mission card state.
- `VictoryPointLedger`: viewer-scoped scoring ledger with reveal-gated secondary source visibility and generic hidden-transaction support.
- `StickyObjectiveControlState`: engine-owned retained-control state emitted by
  phase-end objective-control hooks. It may affect objective-control projection
  payloads through `retained_control_source_id`, but adapters must not create or
  mutate it directly.
- `ReactionWindow` and `TriggeredDecisionRequest`: interrupt-style finite decisions emitted from typed timing windows.
- `OpportunityWindow`: deterministic trigger envelope for optional Stratagems,
  abilities, rerolls, reactions, and phase side actions. It carries a timing
  window, state hash, sequence number, revision, anchor events, eligible
  players, priority order, legal actions, default pass action, close condition,
  and per-player legal-action fingerprints.
- `OpportunityLegalAction`: one engine-enumerated legal action inside an
  opportunity window, with JSON-safe source, cost, target, batching, and handler
  payloads. Adapters select these actions only through the pending
  `DecisionRequest` option IDs.
- `WindowPass`: replay-safe prompt-suppression record keyed by window ID,
  player, revision, and legal-action fingerprint. A matching pass can suppress
  another prompt only while the legal action fingerprint is unchanged.
- `InterfaceIntent`: adapter-captured proactive intent. This adapter capture
  surface is deferred to Phase 18K and is not implemented by current adapters.
  It is not a mutation and not a decision record. When Phase 18K implements the
  adapter surface, an intent may materialize into a normal `DecisionResult` only
  when the current pending request matches its window timing, state hash, source,
  action, targets, and expiration.
- `SequencingDecision`: finite order choice for simultaneous rule conflicts after active-player or roll-off ownership is determined.
- `PersistingEffect`: replay-safe effect state with deterministic expiration and stable canonical unit-ID ownership across Embark/Disembark and Attached Unit component loss.

Relevant modules:

- `src/warhammer40k_core/adapters/contracts.py`
- `src/warhammer40k_core/adapters/decisions.py`
- `src/warhammer40k_core/adapters/projection.py`
- `src/warhammer40k_core/adapters/event_stream.py`
- `src/warhammer40k_core/adapters/local_session.py`
- `src/warhammer40k_core/adapters/server.py`
- `src/warhammer40k_core/adapters/session_persistence.py`
- `src/warhammer40k_core/adapters/session_revision.py`
- `src/warhammer40k_core/adapters/session_recovery.py`
- `src/warhammer40k_core/build_identity.py`
- `src/warhammer40k_core/engine/decision_request.py`
- `src/warhammer40k_core/engine/player_army_list.py`
- `src/warhammer40k_core/engine/army_mustering.py`
- `src/warhammer40k_core/engine/decision_result.py`
- `src/warhammer40k_core/engine/decision_record.py`
- `src/warhammer40k_core/engine/movement_proposals.py`
- `src/warhammer40k_core/engine/deployment.py`
- `src/warhammer40k_core/engine/prebattle.py`
- `src/warhammer40k_core/engine/prebattle_alternation.py`
- `src/warhammer40k_core/engine/prebattle_records.py`
- `src/warhammer40k_core/engine/attached_unit_formation.py`
- `src/warhammer40k_core/core/attachment_eligibility.py`
- `src/warhammer40k_core/engine/setup_completion.py`
- `src/warhammer40k_core/engine/battle_formation_hooks.py`
- `src/warhammer40k_core/engine/faction_rule_states.py`
- `src/warhammer40k_core/engine/cult_ambush.py`
- `src/warhammer40k_core/engine/charge_declaration.py`
- `src/warhammer40k_core/engine/phases/charge.py`
- `src/warhammer40k_core/engine/fight_order.py`
- `src/warhammer40k_core/engine/fight_phase_start_hooks.py`
- `src/warhammer40k_core/engine/catalog_once_per_battle_runtime.py`
- `src/warhammer40k_core/engine/shooting_phase_start_hooks.py`
- `src/warhammer40k_core/engine/phases/fight.py`
- `src/warhammer40k_core/engine/phases/shooting.py`
- `src/warhammer40k_core/engine/timing_windows.py`
- `src/warhammer40k_core/engine/opportunity_windows.py`
- `src/warhammer40k_core/engine/reaction_queue.py`
- `src/warhammer40k_core/engine/sequencing.py`
- `src/warhammer40k_core/engine/effects.py`
- `src/warhammer40k_core/engine/command_points.py`
- `src/warhammer40k_core/engine/stratagems.py`
- `src/warhammer40k_core/engine/stratagem_catalog.py`
- `src/warhammer40k_core/rules/source_packages/warhammer_40000_11th/core_stratagems.py`
- `src/warhammer40k_core/engine/scoring.py`
- `src/warhammer40k_core/engine/lifecycle.py`
- `src/warhammer40k_core/interfaces/cli.py`

## Same Contract, Different Producers

Different adapters may create submissions differently:

- A human UI creates submissions from clicks, drag/drop, forms, and placement tools.
- A CLI creates submissions from terminal prompts.
- A network client serializes submissions over the wire.
- A headless AI creates submissions from policy, candidate generation, search, or solvers.
- A replay driver replays recorded request/result payloads.

Those producers still converge on the same engine-facing objects:

- finite choice -> `FiniteOptionSubmission` -> `DecisionResult`;
- parameterized proposal -> `ParameterizedSubmission` -> `DecisionResult`;
- `DecisionResult` -> `GameLifecycle.submit_decision(...)`;
- valid engine application -> `DecisionRecord` and `EventRecord`.

The lifecycle should not care whether a result came from a person, AI, CLI, network client, or replay driver. It should care only whether the current pending request accepts that result and whether engine validators accept the proposed rule outcome.

## Phase 18D External Contract

The canonical language-neutral contract baseline lives in `contracts/`. Its
OpenAPI 3.1 document references the canonical Draft 2020-12 schemas directly.
Its decision-family inventory is derived from the engine dispatch registry and
marks real adapter-session examples as `live_scenario`; remaining registered or
nested families are explicitly `envelope_only` and are not claimed as
executable external coverage. Parameterized proposal-kind examples remain
schema coverage. `docs/api/` and test-local fixture directories are not
alternate schema authorities.

Every external request or response declares its payload-family version. The
reference server currently requires:

- `create-session-v3` for create-session requests whose embedded mission setup
  requires exactly two public, directed `primary_mission_assignments` and
  explicit logical terrain-area identities;
- `finite-submission-v1` for finite option submissions;
- `parameterized-submission-v2-weapon-instances` for proposal submissions whose
  shooting declarations require one engine-emitted physical weapon instance ID
  per declared ranged weapon copy;
- `lifecycle-status-v4-phase17n-step4` for server lifecycle responses whose
  public Primary Mission choices and unresolved viewer-scoped Declare Battle
  Formations state use the shared redaction boundary;
- `decision-request-view-v5-phase17n-step4` for visible or redacted pending
  decisions, including public `select_primary_mission_choice` options;
- `annotated-decision-request-v2-primary-assignments` for nested interaction
  requests;
- `event-delta-v4-phase17n-step4` for the in-process integer-cursor adapter delta only;
- `event-delta-v5-phase17n-step4` for authenticated role-bound HTTP event deltas;
- `game-view-v11-phase17n-step4` for role-scoped game projections whose public
  mission state contains both directed Primary Mission assignments, complete
  group-aware turn-start position rows, and persistent Step 4 Primary Mission
  progress;
- `battlefield-view-v4-phase17n-step3` for authoritative battlefield geometry
  with explicit terrain-area logical identity and terrain area and feature
  classifications, plus viewer-scoped model formation state before reveal;
- `session-projection-v7-phase17n-step4` for full role-scoped reconnect projections;
- `session-create-v4`, `session-metadata-v11-contract`,
  `session-command-envelope-v2-weapon-instances`,
  `session-command-result-v11-contract`, and `session-command-outcome-v11-contract` for the
  authenticated formal session protocol;
- `session-persistence-v3-weapon-instances` for the closed operator-only durable server
  artifact. It is included in the Contract 11 schema bundle and examples but
  deliberately absent from OpenAPI operations and client payloads;
- `capability-manifest-v2-directed-primary` inside
  `support-profile-v4-directed-primary` for viewer-scoped capability evidence
  whose public mission identity includes both assignments;
- `physical-proposal-context-v2` for engine-owned physical proposal context;
- `replay-artifact-v8-phase17n-step5a` for replay artifacts whose required source
  identity includes `ruleset_descriptor_hash`, `rules_overlay_ids`, and the
  atomic `mission_pack_id` / `mission_source_package_hash` pair, while the
  embedded mission setup includes both directed Primary Mission assignments,
  Phase 17N group-aware turn-start position, destruction-attribution,
  battlefield-departure evidence, persistent Primary Mission progress state,
  the content-addressed Primary scoring-state evidence registry with frozen
  destruction-history membership, and explicit
  logical terrain-area identities;
- `error-envelope-v1` for typed transport errors.

Phase 18L adds no player-facing decision type, finite-option family, proposal
kind, public response field, or visibility exception. It advances the additive
bundle to Contract 10.2 because trusted deployment tooling gains a new schema
and normative recovery semantics; all existing Contract 10.1 HTTP families keep
their current shapes and discriminators.

Contract 11 advances the parameterized shooting proposal and command wrappers
because `weapon_instance_id` is now required, and advances the persistence
artifact because stored command envelopes and outcomes carry those new family
identities. No Contract 10 shooting or persistence payload is reinterpreted.

The Contract 11 replay loader accepts only `replay-artifact-v8-phase17n-step5a`;
v7 artifacts require the retained 9.x deployment. It never infers directed
Primary Mission assignments, grouped position history, destruction sources,
battlefield departures, persistent markers, condemned selections,
consecration designations, scoring-state evidence, missing logical terrain-area
grouping, or mission source identity. Mission identity fields are both non-null
when the configured or
late-bound lifecycle has a mission setup and both null otherwise; canonical
mission source-package hash drift is rejected. A mismatched
request version fails before queue consumption or engine mutation. External
error and status payloads are
viewer-scoped by the same shared redaction policy as game projections and
events.

The external replay schema requires the lifecycle state and closes the three
Step 3 evidence row families, the Step 4 Primary progress state, and each Step
5A scoring-state evidence row without duplicating every engine-private
lifecycle field. Each evidence row binds its content hash/ID, scoring boundary
kind, objective-control record identity/hash, progress, qualifying Action and
departure history, exact Primary unit-destruction history membership, current
group-aware memberships, and frozen player-scoped
table-quarter, territory, and opponent-territory-objective witnesses. Full lifecycle shape,
event linkage, source attribution, and historical cross-record consistency
remain fail-closed runtime-loader responsibilities; JSON Schema acceptance
alone does not certify a replay as reproducible.

Evidence is persisted at every assigned-Primary boundary with at least one
applicable rule, including deterministic zero-award evaluations. Restore
enforces exact inverse completeness: every required ordinary or end-of-battle
boundary has one row, every row maps back to a required boundary, and any
awarded transactions equal normal policy re-evaluation. Removing transactions
together with their evidence cannot hide an applicable historical boundary.

`primary_scoring_state_evidence_records` is authoritative replay/audit state,
not viewer projection state. It is deliberately omitted from
`game-view-v11-phase17n-step4` and
`session-projection-v7-phase17n-step4`; those family versions remain unchanged.
Adapters render public mission progress and awarded victory-point transactions
without receiving the engine-private registry.

Compatibility, coordinate, session, and redaction semantics are normative in
`contracts/compatibility-policy.md`, `contracts/coordinate-system.md`,
`contracts/session-semantics.md`, and `contracts/redaction-policy.md`. Any new
decision type, proposal kind, adapter-visible field, status, error, or visibility
behavior must update the canonical schema/examples in the same change and pass
`scripts/build_external_contract.py --check`.

## Trigger Opportunity Windows

Optional trigger-based rules use synchronous engine-owned opportunity windows,
not adapter-private polling or asynchronous mutation. The trigger host reaches a
supported timing point, enumerates legal `OpportunityLegalAction` values, opens
an `OpportunityWindow`, and emits a normal pending `DecisionRequest`. That
request may use an existing host decision type such as `resolve_reaction_window`
or `use_stratagem`; the opportunity envelope is the shared payload shape around
the legal options, not a separate rules path.

Adapters may render opportunity windows as a reaction tray, enabled Stratagem
button, CLI command list, AI candidate list, network message, or replay record.
They must still answer by selecting one pending option ID or by submitting the
host's parameterized payload. They must not apply the action, spend resources,
move models, reveal hidden data, or suppress replay events locally.

Human-facing adapter capture of proactive declarations as `InterfaceIntent`
records is deferred to Phase 18K. Current adapters must not expose an
`InterfaceIntent` capture surface. When Phase 18K implements that surface, an
intent may be queued by the adapter while no matching engine window is open, but
it remains advisory only. It materializes into a `DecisionResult` only if the
current pending request matches the intended timing, player, state hash, source,
action ID, targets, and expiration. Stale, expired, wrong-context, malformed, or
unavailable intents are rejected without consuming the pending request and
without mutating authoritative state.

Fast-rolled or repeated equivalent triggers should be batched inside one
opportunity window when the rules permit it. `TriggerBatchingMode` records
whether an action applies to one item, a subset, a quantity, the whole group, or
requires atomic non-batched timing. Fast rolling remains an optimization; if a
rule can legally interrupt between atomic events, the host must split the roll
group or open the opportunity before consuming the group result.

Prompt suppression is represented as a pass, not as a missing opportunity.
`WindowPass` records are keyed by window ID, player, revision, and
legal-action fingerprint. If nothing changed, the same player should not be
reprompted. If state changes, legal actions change, or the window revision
changes, the fingerprint changes and the player may need a fresh opportunity.

When both players can act, the opportunity window's `priority_order` is
authoritative. Network clients must submit requested action IDs for the current
window and state hash; they must never send direct "apply this Stratagem now"
commands. Replay consumes recorded `DecisionResult` payloads and verifies that
the same opportunity request and legal-action fingerprint are reproduced.

See [TRIGGER_OPPORTUNITY_WINDOWS.md](TRIGGER_OPPORTUNITY_WINDOWS.md) for the
implementation-level contract.

## Finite Decisions

Finite decisions are bounded option choices already enumerated by the engine. Examples include:

- secondary mission selection;
- Primary Mission setup, turn-start, and turn-end choices;
- Tactical secondary discard;
- Mission Action start selection;
- unit selection;
- movement action selection;
- charge unit selection;
- shooting unit selection;
- defender attack-allocation model selection;
- optional defensive ability choices;
- reroll choices;
- Stratagem use choices;
- decline/accept choices;
- triggered movement choices.
- reaction-window interrupt choices;
- sequencing order choices.

Adapters must not invent option IDs. They must select one of the pending request's option IDs.

Example: selecting Normal Move

```json
{
  "request_id": "decision-request-000004",
  "selected_option_id": "normal_move",
  "result_id": "ui-result-000017"
}
```

Producer examples:

- local UI: user clicks the Normal Move button;
- CLI: player types the listed Normal Move option number;
- AI: policy selects `normal_move`;
- network UI: client sends `selected_option_id: "normal_move"`;
- replay: recorded result selects `normal_move`.

All of those become the same engine-facing result:

```python
result = FiniteOptionSubmission(
    request_id="decision-request-000004",
    selected_option_id="normal_move",
    result_id="ui-result-000017",
).to_result(pending_request)

status = lifecycle.submit_decision(result)
```

The adapter helper equivalent is:

```python
status = submit_option(
    lifecycle=lifecycle,
    request_id="decision-request-000004",
    option_id="normal_move",
    result_id="ui-result-000017",
)
```

Adapter helper APIs should take `request_id` explicitly even when a local wrapper can infer the current pending request. Explicit request IDs let network, replay, and UI adapters fail fast on stale-client drift before constructing a `DecisionRecord`.

P06A changes the engine-owned visibility predicate but adds no decision type,
finite option family, proposal kind, adapter-visible payload shape, replay
schema, or viewer-redaction branch. Every attack, Stratagem, mission action,
and generic RuleIR ability that requires visibility continues to consume the
same `TerrainVisibilityContext` through the existing engine targeting service.
That context now evaluates each sampled source-to-target line as one
1mm-wide, height-aware corridor across physical terrain, rules footprints,
logical terrain areas, and intervening model hulls. Existing line-of-sight
witness payload field names and cache keys remain stable; only engine-derived
eligibility changes when an obstacle is within half the corridor width of a
sampled line. Model positions, terrain geometry, targeting eligibility, and
visibility-gated options are public table information in the current rules
scope, so both viewers receive the same result through the shared projection
and event-delta paths. Adapters must not reconstruct a zero-width ray test or
locally widen/narrow the corridor. This remains within Contract 11.1.0.

P09A makes Move Units one finite unit/action loop. Every currently unselected
friendly rules unit on the battlefield, embarked in a Transport, or in
Strategic Reserves is selected through `select_movement_unit`. Its engine-owned
option payload carries `unit_location`, the complete model IDs, and, for an
embarked unit, `transport_unit_instance_id`. It also carries the complete
ordered `component_unit_instance_ids`; an attached formation appears exactly
once under its canonical synthetic rules-unit ID, never once per physical
component. The selected unit then receives
one `select_movement_action` request: battlefield units use the ordinary
Remain Stationary, Normal Move, Advance, and Fall Back space; embarked units
may choose Remain Stationary or Disembark; reserve units may choose Remain
Stationary or Ingress, while a required arrival exposes only Ingress. Adapters
must select the exact pending unit and action option IDs and must not infer a
separate reserve or Transport sub-step. The retired
`select_reinforcement_unit`, `complete_reinforcements`,
`select_disembark_unit`, and `complete_disembarks` finite surfaces are not
registered adapter decisions. Both request families carry the stable
`source_rule_id: "gw-11e-core-rules:movement-phase:move-units-step"`; adapters
preserve it as engine-authored audit context and do not use it to mutate state.

Normal Move, Advance, Fall Back, and Remain Stationary retain that canonical
identity through validation, state, completion events, replay, and adapter
projection. For an attached rules unit, one movement proposal witness covers
every alive placed model in every component. The engine validates paths and
endpoint coherency across the complete flattened group and applies every
component endpoint atomically or none; adapters must not submit a component
alias or split one attached activation into component actions.

Disembark and Ingress actions emit the existing typed
`submit_placement_proposal` request. Accepted Rapid Disembark, Assault Disembark, and Ingress
placements complete the selected unit activation. An attached rules unit uses
one `attempted_rules_unit_placement` containing every component and alive model
for either action. Accepted Tactical Disembark keeps that same unit active but
does not expose its follow-up action until the exact emitted `unit_disembarked`
occurrence has closed all registered setup/move-completed hooks. Any nested
target or Feel No Pain request serializes that occurrence-bound continuation.
Only after those requests resolve does the engine return to
`select_movement_action` for the required Normal Move or Advance; if the setup
effect destroys or otherwise invalidates the disembarking rules unit, the
engine completes that canonical activation without emitting a stale action.
Malformed, stale, wrong-location, wrong-Transport, wrong-reserve-state, and
wrong-action submissions reject through the shared lifecycle validation path
before engine mutation. These unit locations and actions are public battlefield
state in the current rules scope, so the existing public request, record,
event, projection, and event-delta visibility applies symmetrically to both
players.

Movement action option payloads include the selected `movement_mode`. Default Normal Move and Advance keep their existing option IDs, while Take to the Skies variants append the mode, for example `normal_move:fly_take_to_skies` or `advance:fly_take_to_skies`. Fall Back options are explicitly mode-scoped: `fall_back:ordered_retreat` or `fall_back:desperate_escape`, with `:fly_take_to_skies` appended when that movement mode is selected. Remain Stationary resolves as a finite action. Normal Move, Advance, and Fall Back always emit a follow-up `submit_movement_proposal` request carrying the same mode context; adapters must submit the actual `PathWitness` and model poses through that parameterized request.

P09B makes those two Fall Back modes authoritative rather than merely descriptive. An unshocked
engaged rules unit receives both `fall_back:ordered_retreat` and
`fall_back:desperate_escape`; a Battle-shocked unit receives only Desperate Escape. Selecting
Desperate Escape is legal even when no overflight or content rule forces it. The accepted
`submit_movement_proposal` must preserve the emitted `fall_back_mode`, and the engine creates one
`selected_mode` Desperate Escape requirement and one Hazard Roll for every model in the complete
canonical rules unit. Overflight, Battle-shock, and source-backed forced reasons may coexist on
those same per-model requirements; they do not replace the selected-mode inventory.

The engine resolves any Hazard Roll casualties, applies the grouped `PathWitness` transition, and
then checks the unit's authoritative Battle-shock state. If at least one model survives and the
unit is not Battle-shocked after moving, the engine resolves a Battle-shock test with reason
`desperate_escape` before Embark or `movement_activation_completed`. An available reroll uses the
existing `select_dice_reroll` finite decision. The engine serializes one parent movement
continuation across both that reroll and any nested Battle-shock outcome decision. The parent pins
the continuation phase and source kind, canonical rules-unit identity, exact action result and
movement-proposal request, complete Fall Back result, applied-event identity, grouped transition,
movement payload, Battle-shock request/result, and optional reroll request/result. If the unit is
already Battle-shocked or no model survives, no follow-up test is created. Adapters must not roll
Hazard dice, choose whether the follow-up test occurs, remove models, apply Battle-shock, or
complete the movement locally.

A Battle-shock outcome provider can return a nested decision such as Feel No Pain for mortal
wounds. That provider's returned status must identify the actual and sole pending queue head; the
engine does not enqueue Embark or emit `movement_activation_completed` until the complete outcome
chain closes. Restore and replay authenticate the provider claim and every parent occurrence field
before resumption. Once the outcome closes, the engine validates the retained rules-unit identity:
a surviving placed Attached Unit may receive the ordinary Embark choice, while a destroyed or
otherwise absent unit completes its activation without a stale Embark request.

The same ordering applies when an immediate catalog selected-target effect resolves a
Battle-shock test and opens a provider-owned decision. Post-shoot, Shooting-start, and Fight-start
selections serialize `pending_catalog_selected_target_battle_shock_continuation` in authoritative
`GameState`. It retains the exact original selection request/result, phase-specific final event,
catalog/source/clause/target/effect identity, resolved prefix and remaining effects,
Battle-shock/reroll identity, and provider queue-head claim. Adapters continue to answer only the
existing provider decision: they must not reselect the target, execute later effects, or infer
completion. After the provider chain closes, the engine authenticates history, records the
resolved Battle-shock effect once, resumes the remainder, and emits one final selected-target
event. If that retained remainder reaches another immediate Battle-shock effect with an available
reroll, the parent enters `awaiting_remaining_battle_shock_reroll` and authenticates the existing
`select_dice_reroll` request against the exact retained selection, resolved prefix, current effect,
remaining suffix, and starting index. Reroll resolution either continues the suffix or replaces the
parent with the later provider-owned outcome before any following effect executes. This adds no
decision type, proposal kind, payload family, hidden-information branch, or adapter mutation path;
it is persisted engine-owned continuation state within Contract 11.1.0.

Fall Back resolution and completion payloads now carry the stable source IDs
`gw-11e-core-rules:movement-phase:selecting-modes` and
`gw-11e-core-rules:movement-phase:fall-back-move`, the selected mode, the exact per-model
requirement/roll inventory, casualty IDs, and `battle_shocked_after_move`. When the follow-up test
is required, public event `fall_back_move_applied` records the exact transition before
`battle_shock_test_resolved` and `desperate_escape_battle_shock_resolved`; the later movement
completion repeats the authenticated transition without applying it twice. These facts are public
and symmetric in the current rules scope, so existing shared event projection and redaction apply
to both viewers. This adds no decision type, proposal kind, hidden-information family, or
adapter-owned mutation and therefore remains within the existing Contract 11.1.0 families.

When source-backed runtime content lets the selected unit ignore any or all
applicable Move-characteristic or Advance-roll modifiers, the existing
`select_movement_action` finite space enumerates every legal physical-modifier
subset. The keep-all choice retains the normal action option ID. A choice that
ignores one or more modifiers appends a deterministic `:ignore:<hash>` suffix
to that action option ID. Its payload adds `modifier_ignore_context`, containing
the selected `unit_instance_id`, source/record/RuleIR/clause provenance under
`permissions`, the complete `available_modifiers` snapshot, and the selected
`ignored_modifiers` subset. Each modifier snapshot carries `kind`, stable
`modifier_id`, optional `source_id`, and a `model_instance_id` only for a
Move-characteristic modifier. Normal Move and Fall Back enumerate applicable
Move-characteristic modifiers; Advance enumerates both Move-characteristic and
Advance-roll modifiers. Remain Stationary is not expanded. Adapters must submit
one exact engine-enumerated option ID and payload, and must not classify a
modifier as beneficial or detrimental or edit the subset locally. The accepted
selection is recorded as a phase-scoped engine effect and
`modifier_ignores_selected` event before movement or the Advance roll resolves.
Duplicate, malformed, invented, no-longer-applicable, or stale modifier
contexts reject before queue pop and before a `DecisionRecord` or selection
effect is created.

Terrain classification is authoritative during movement-proposal validation.
All models can move horizontally and vertically through Light terrain.
`INFANTRY`/`BEASTS`/`SWARM` models can move horizontally and vertically through
Dense terrain, while `MOBILE` grants only horizontal Dense transit. A denied
Dense direct-transit permission cannot be promoted by a retired feature-kind
policy, although an otherwise legal vertical path may still climb over the
feature. Adapters must submit the path actually taken and must not infer
terrain traversal from feature display kind.

Accepted Fall Back proposals may include source-backed `fall_back_eligibility_grants` in the resulting `movement_activation_completed` event. These grants are replay-safe audit payloads produced by runtime faction content and do not create a new adapter choice. The Movement engine remains the only writer of `FellBackUnitState.can_shoot` and `FellBackUnitState.can_declare_charge`; Shooting and Charge phase selection consume those recorded permissions instead of adapters inferring Fall Back exceptions locally.

Movement-action optional grants use a finite/proposal split. After a Normal
Move, Advance, or Fall Back movement action is selected, the engine may emit
`select_movement_action_grant` before the movement proposal or Advance roll if
one or more source-backed optional grants are currently legal. Each grant option
ID is the deterministic hook ID emitted by runtime content;
`decline_movement_action_grant` explicitly declines the window. The option
payload includes the selected unit, movement action, source movement action
request/result IDs, movement mode, and JSON-safe selected grant payloads.
Adapters must select one pending option ID, must not invent grant IDs, and must
not spend resources, apply movement bonuses, mutate weapon abilities, or apply
defensive restrictions locally. Accepted grant choices record engine-owned
source-backed spend and unit effects before the follow-up movement resolution
and carry the selected grant payload into the later `submit_movement_proposal`
request when that action uses one. The engine still validates the movement
proposal, mutates battlefield state, and consumes structured grant effects.
Stale, malformed, wrong-context, or unavailable grant submissions are rejected
before grant/spend mutation. Drukhari `Power from Pain: Lithe Agility` uses this
same grant surface for Advance moves: accepting the engine-emitted option spends
one Pain token through the faction-resource ledger, records a phase-scoped
empowerment effect, and may then emit the normal `select_dice_reroll` request
for the Advance roll. Adapters must not decrement Pain tokens or grant the
reroll locally.

Aeldari Warp Spiders' Flickerjump uses the same
`select_movement_action_grant` surface only when the unit is selected for a
Normal Move. Accepting its engine-emitted catalog hook option records an
end-of-turn unit effect that sets the current Move characteristic to 24 inches,
forbids Charge declaration, and carries the source-backed phase-end risk.
Immediately before the Movement phase completes, the engine rolls one D6 for
each current placed model in that rules unit and applies one self-inflicted
mortal wound for each 1 through the shared mortal-wound and Feel No Pain path.
The trigger roll, current model IDs, successes, source effect, mortal-wound
application, and any pending Feel No Pain continuation are deterministic and
replay-safe. Adapters must not alter the movement budget, mark the unit unable
to Charge, roll the phase-end dice, choose damaged models, or apply wounds
locally.

Aeldari Solitaire's Blitz also uses `select_movement_action_grant` before its
Normal Move. Its grant payload carries the source-backed
`movement_bonus_dice_expression` and typed `rule_frequency_usage` metadata.
After the engine accepts the option, it consumes the once-per-battle use, rolls
2D6 through the random-characteristic service, and records the resolved roll
and Move bonus in an end-of-turn effect. That effect applies only to the source
model and adds 3 Attacks only to its named Solitaire weapons. Declining does not
consume the use. Adapters must not roll the bonus, track the frequency limit,
increase Move or Attacks, or broaden either modifier to another model or weapon.

Aeldari Spiritseer's Spirit Mark uses the finite decision type
`select_catalog_movement_target_pair` when the source model starts or ends a
move. Each use option identifies one engine-enumerated friendly non-TITANIC
WRAITH CONSTRUCT rules unit within 6 inches and one enemy rules unit currently
visible to the source model. The request and option payloads carry the source
catalog record, source rule and RuleIR hashes, clause, source rules-unit/unit/model
IDs, timing edge, movement action, and the movement action result or completion
event that opened the window. The deterministic decline option defers the
ability at the start edge and closes it at the end edge. An accepted pair creates
an engine-owned persisting RuleIR effect through the start of the selecting
player's next Movement phase; that effect grants Sustained Hits 1 only to the
selected friendly unit and only while it targets the selected enemy unit. The
lifecycle recomputes source presence, range, excluded keywords, visibility,
once-per-turn use, and movement-event context before queue pop. Stale, drifted,
malformed, or invented pairs return a typed invalid status without mutation.
Adapters must not enumerate pairs, infer visibility, grant weapon abilities, or
advance the movement action while the request is pending.

Aeldari Eldrad Ulthran's Doom uses the public finite decision type
`select_catalog_movement_end_target_effect` at the end of the active player's
Movement phase. Its interaction kind is `entity_selection` with entity kind
`target_unit`. The engine emits one deterministic option for each enemy rules
unit within 18 inches of and visible to Eldrad's current model; the request and
option payloads include `submission_kind`, hook ID
`catalog-ir:movement-end-selected-target-effect`, game/round/phase/player
context, catalog record and RuleIR identity, source unit/model identity, the
selection clause, the complete candidate target inventory, and the generic
effect records for that option. The choice is mandatory when at least one legal
target exists and is public to both viewers. An accepted option records an
engine-owned generic RuleIR effect through the start of that player's next
Command phase. The effect adds 1 to wound rolls made by friendly `AELDARI`
models only when their attack targets the selected enemy rules unit. The
lifecycle reproduces source presence, range, visibility, option inventory, and
payload identity before queue pop; stale, malformed, drifted, or invented
targets return typed invalid status without mutation. Adapters must not
enumerate Doom targets, calculate visibility, apply the wound modifier, or
advance the Movement phase while the request is pending.

Aeldari Shining Spears' Extreme Mobility does not add a separate decision. It
extends the existing Normal Move, Advance, Fall Back, and Charge Move proposal
contract. The engine-authored `PathValidationContext` and its serialized payload
contain the required boolean `ignores_vertical_distance`. When true, the
movement budget is measured from the horizontal distance of every submitted
path segment, while the `PathWitness` retains the exact three-dimensional poses
for transit, terrain, collision, endpoint, and replay validation. Adapters must
submit the real path and elevations; they must not flatten poses, omit vertical
transit, or pre-approve a move from its endpoint. The flag is derived from the
source-linked catalog movement permission and is never adapter-authored.

Phase 17G Movement-end surge and generic RuleIR reactive-movement rules use the
same finite/proposal split as other physical movement. After an enemy unit
completes a Normal Move, Advance, or Fall Back in the Movement phase, the engine
may emit `select_triggered_movement` for the reacting player. Optional windows
include `decline_triggered_movement`; each legal reacting rules unit is exposed
through a deterministic `surge:<unit_instance_id>` or
`triggered:<unit_instance_id>` option according to the source movement kind.
The option payload identifies the selected rules unit, source hook, source rule,
triggering unit, triggering move event, optional engine-owned decision effect
payload, and engine-resolved maximum movement distance. The source-linked grant
also carries a typed distance specification whose `kind` is exactly `dice` or
`fixed`. The replay event `movement_end_surge_triggered` exposes a typed
`distance_resolution` with that kind, the resolved `max_distance_inches`, the
distance specification, the applied bonus, and a nullable `roll_state`. Fixed
distance reactions have a null roll state and do not consume RNG; dice distance
reactions retain the engine-authored roll state. Independently triggering
datasheet abilities may emit a separate decision window for each eligible rules
unit and for each triggering enemy move. Selecting a unit records that finite
choice, records any source-backed decision effect, and immediately emits a
parameterized `submit_movement_proposal` request with proposal kind
`surge_move`. Aeldari Rangers' source-backed Path of the Outcast RuleIR uses
this contract after an enemy unit ends a move within 8 inches: the engine
excludes engaged Rangers rules units, rolls D6, and offers an optional Normal
Move through a PathWitness-validated proposal. Emperor's Children Chaos Spawn's
Scuttling Horrors uses the same decision and proposal path with an engine-resolved
fixed 6-inch maximum and no distance roll. Adapters must not roll or resolve the
distance locally, invent candidate units, move models from the finite option
payload, spend source resources locally, or continue the Movement phase while
either request is pending.

When a selected triggered movement carries a source-backed whole-roll reroll,
the finite selection does not proceed directly to the movement proposal. The
engine first emits the existing `select_dice_reroll` request with
`context_kind: "triggered_movement_distance_reroll"`, the original
`distance_roll_state`, the typed reroll permission, the selected eligible-unit
payload, the triggered-movement descriptor, and the source selection
request/result IDs. Accepting or declining one engine-emitted reroll option
then emits `submit_movement_proposal` with the final distance in its descriptor.
Aeldari Autarch Superlative Strategist uses this path for Opportunity Seized
and Fade Back. If an Autarch Wayleaper is currently leading the selected unit,
the Battle Focus spend payload also carries the source-backed Indomitable
Strength of Will refund descriptor; after the engine records the spend, it
rolls one D6 and records any 3+ token gain through the faction-resource ledger.
The refund roll is not an adapter choice. Adapters must not reroll movement
distance, alter the final distance, roll the refund, or mutate Battle Focus
tokens locally.

Opportunity Seized candidate units require at least one placed living model in
the physical component that would move. The engine evaluates their Engagement
Range at the triggering enemy unit's authenticated start placement through the
shared physical scenario, so a retained Fight On Death base may establish that
range for an otherwise living mixed unit without becoming movement authority.
A component represented only by retained destroyed bases is omitted; any
resulting movement witness contains only placed living models.

Shooting phase after-shot surge rules reuse `select_triggered_movement` and the
same `surge_move` proposal contract. After an enemy unit has shot, runtime
content may expose eligible hit units as deterministic `surge:<unit_instance_id>`
options for the reacting player. The engine owns the hit-unit filtering,
distance roll, source spend recording, and physical movement proposal; adapters
must not infer hit eligibility or move models from the finite option payload.

Fight-end generic RuleIR movement uses that same existing finite/proposal
contract. At the end of the Fight phase, Corsair Skyreavers' Raid and Run emits
`select_triggered_movement` only when the engine's Fight eligibility history
accepts the rules unit. The engine selects Normal Move or Fall Back from the
unit's current Engagement Range state, rolls D3 and adds 3, and carries the
source RuleIR record, clause, selected effect, roll, and movement mode in
replay-safe context. The accepted unit then emits the existing `surge_move`
`submit_movement_proposal`, so every physical move still requires a
`PathWitness`. A mixed rules unit's proposal witness contains exactly its placed
living models; the engine merges their accepted endpoints into the current unit
placement while every destroyed Fight On Death model remains fixed. Those
retained bases are carried in the physical scenario inventory and remain
collision and transit blockers, so paths cannot cross them and endpoints cannot
overlap them. A rules unit whose only battlefield presence is retained destroyed
bases is omitted from the finite unit inventory and cannot originate the
proposal. Adapters must not include retained model IDs in the witness, infer
prior Fight eligibility, choose the move mode, roll the distance, or move models
from the finite option payload.

Catalog setup-reactive shoot/charge rules use the finite decision type
`select_catalog_setup_reactive_shoot_charge` at the end of the opponent's
Movement phase after an enemy unit is set up on the battlefield within the
source-backed range. The request actor is the reacting player. The pending
request payload includes `submission_kind`, `source_kind:
"catalog_setup_reactive_shoot_charge"`, catalog record ID, ability ID, source
rule ID, RuleIR source ID/hash, clause ID, source rules-unit/component/model
IDs, target rules-unit/component/player IDs, trigger event ID, measured
distance, range limit, and `available_action_option_ids`. Option IDs are
deterministic and limited to `decline`, `shoot`, and `charge`; `shoot` is
emitted only when the selected enemy unit is currently an eligible constrained
shooting target, and `charge` is emitted only when the source RuleIR exposes the
charge action. Adapters must select one emitted option ID and must not invent a
target, recompute the action list, or mutate shooting, charge, or movement
state from the finite payload.

Selecting `shoot` records the finite choice and emits the normal out-of-phase
shooting declaration request constrained to the selected enemy unit. Selecting
`charge` records the finite choice, rolls the Charge distance through the
engine dice manager for the reacting player, snapshots only reachable selected
targets, and emits a `submit_movement_proposal` request with proposal kind
`charge_move`, phase `movement`, `source_kind:
"catalog_setup_reactive_shoot_charge"`, `movement_mode: "charge"`,
`charge_move_required_target_unit_instance_ids`, `target_unit_instance_id`,
`charge_roll`, `charge_bonus_suppressed: true`, `suppressed_charge_bonus:
"fights_first"`, and `suppressed_charge_bonus_effect_kind:
"charge_grants_fights_first"`. Adapters answer that Movement-phase Charge Move
with the ordinary `ChargeMoveProposal` payload and a `PathWitness`; the engine
validates that the selected required target is still reachable and that the
move ends engaged with it. Accepted setup-reactive Charge Moves emit the
source-specific completion event and do not register the normal Charge bonus
PersistingEffect. In CORE V2, that suppressed Charge bonus is Fights First.

Phase 17G phase-end objective-control retention hooks do not create
adapter-submitted decisions. The engine snapshots objective proximity at the
start of each phase, evaluates source-backed phase-end conditions, records any
`StickyObjectiveControlState`, and overlays retained control in the
phase-boundary objective-control event. Adapter projections may display
`retained_control_source_id` and sticky-control events, but clients must not
create, expire, score, or mutate retained objective-control state directly.

Phase 11E mission-scoring decisions that are player-facing are finite decisions:

- `replace_tactical_secondary_mission`: in Warhammer Event Companion games, after
  the active player's Battle-shock step at the end of that player's Command
  phase, the engine may emit a once-per-battle Tactical Secondary replacement
  request. The request is emitted only for the active player using Tactical
  Secondaries when that player has at least one active Tactical Secondary card,
  at least 1 CP, and no recorded replacement use. The payload includes
  `timing: "end_of_command_phase"`, `legal_secondary_mission_ids`,
  `replacement_source_id`, `replacement_cost_cp: 1`,
  `replacement_discard_count: 1`, `replacement_draw_count: 1`, and
  `replacement_used: false`. One `replace:<secondary_mission_id>` option is
  emitted for each active Tactical Secondary card, plus
  `decline_tactical_secondary_replacement`. Accepted replacement submissions
  spend 1 CP, discard exactly one selected active Tactical Secondary, draw
  exactly one replacement, record the per-player once-per-battle ledger, emit
  `command_points_spent`, and emit `tactical_secondary_mission_replaced`.
  Stale replacement submissions are rejected before queue pop if the Command
  phase, active player, battle round, source ID, CP total, active-card set, or
  once-per-battle ledger has drifted. Decline records no CP/card mutation and
  only resolves the current Command-phase replacement window.
- `discard_tactical_secondary_mission`: the engine emits one option for each non-empty set of active Tactical secondary cards the player can discard. Single-card options retain the `discard:<secondary_mission_id>` option shape, while multi-card options use `discard:<secondary_mission_id>+<secondary_mission_id>`. The request payload includes `legal_secondary_mission_ids`, `legal_secondary_mission_id_sets`, `discard_cp_reward_window_id`, and `discard_cp_reward_window_used`. The selected option payload includes the game, player, active player, battle round, phase, `secondary_mission_ids`, and `discard_cp_reward_window_id`. The lifecycle applies all selected discards and emits `tactical_secondary_missions_discarded`. Under Chapter Approved 2026-27, ordinary Tactical discard awards exactly 1 CP once for the active player's own-turn discard window, even when multiple active Tactical secondaries are discarded together. After that window is consumed, additional own-turn discard requests are unsupported until the lifecycle reaches a new source-backed discard window. Opponent-turn discards are legal but emit `command_point_reward_eligible: false` and no `command_point_gain`.
- `score_tactical_secondary_mission`: when the engine records a source-backed `TacticalSecondaryAchievementContext` proving that a Tactical Secondary Mission Card's requirements have been achieved, it emits a finite choice for that context. Merely having an active Tactical card is not sufficient to emit this decision. The selected option payload includes the `achievement_id`, card identity, scoring rule ID, scoring rule condition, scoring rule source ID, scoring timing, phase/round/actor context, and JSON-safe achievement evidence. The `score:<secondary_mission_id>` option is present only when cap resolution would apply at least 1 VP; it awards the source-backed VP, marks the card scored/non-active, consumes the achievement context, and emits `tactical_secondary_mission_scored` with `discarded_after_score: true`. A positive partial award is a legal score. The `retain:<secondary_mission_id>` option remains available at zero VP capacity, awards no VP, leaves the card active, consumes the finite achievement context, and emits `tactical_secondary_mission_score_declined`. Stale score submissions are rejected before queue pop if intervening scoring exhausts VP capacity. Score/retain submissions are also rejected before queue pop if the achievement context is missing, mismatched, stale, no longer source-valid, no longer matches the active card, the phase/round/actor drifted, or the source-backed scoring metadata changed. Ordinary Tactical discard remains a separate decision path.
- `resolve_tactical_secondary_when_drawn`: after a Tactical Secondary draw in Command, the engine may emit a keep-or-discard choice for A Grievous Blow and Bring It Down, a first-battle-round shuffle-back choice for Behind Enemy Lines and Forward Position, or a shuffle-back choice for Cleanse while Plunder is active and for Plunder while Cleanse is active. Keep/remain is the first option on those optional requests. The engine auto-keeps Grievous Blow or Bring It Down when the discard condition is already ineligible. Defend Stronghold drawn in battle round 1 is a mandatory engine shuffle-and-draw: it emits `tactical_secondary_when_drawn_shuffled` with `mandatory: true` and does not expose a keep option. Shuffle-back draws a replacement while the shuffled card is still held (so it cannot be redrawn as that replacement), then forgets the shuffled card so later draws can select it. The request is owner-secret.
- `select_tempting_target_objective`: when A Tempting Target is drawn, the opponent selects one objective in No Man's Land excluding home objectives. The request is public. Option IDs are engine-enumerated objective marker IDs.
- `select_beacon_unit`: when Beacon is drawn, the owner selects one friendly unit on the battlefield or embarked within a TRANSPORT on the battlefield. The request is owner-secret.
- `select_burden_of_trust_guard`: when Burden of Trust is drawn and at the start of each of the owner's later turns, the engine emits sequential per-objective unit-or-skip choices. Skip is the first option and still marks that objective resolved for the current round. The request is owner-secret.
- `start_mission_action`: before ordinary Shooting-unit selection, the engine
  automatically enumerates the active Primary Mission's supported Actions, the
  active player's selected Fixed Secondary Actions, and the player's currently
  active Tactical Secondary Actions. A single request contains every legal
  `start:<mission_action_id>:<unit_instance_id>:<target_id>` option plus
  `continue_to_shooting`. Each Action option has a unique human-readable label
  containing its Action, canonical rules unit, and target names and IDs, so
  generic CLI and projection clients do not need to decode the option ID or
  payload to distinguish choices. The request carries `mission_action_opportunity: true`,
  `legal_mission_action_ids`, `legal_action_option_ids`, and `legal_option_ids`;
  selecting `continue_to_shooting` closes the persisted Shooting-phase
  opportunity without mutating an Action. Starting one Action returns to the
  same opportunity step so any remaining legal unit/target Actions can be
  selected before the player continues to shooting. Direct requests for an
  unselected Secondary Action are unsupported, and submissions drift invalid if
  the held card set, active Primary, unit eligibility, geometry, target set,
  round, phase, or actor changes before queue pop. Current support enumerates
  source-backed `objective_marker` actions such as Cleanse and Terraform,
  `trappable_terrain_area` actions such as Death Trap's Booby Trap, and
  `plunderable_terrain_area` actions such as Plunder. Option payloads include
  `target_policy` and `target_kind`; `objective_marker` targets use objective
  marker IDs, while terrain-area targets use terrain feature IDs.
  `trappable_terrain_area` targets exclude terrain already trapped by that
  player and terrain fully within that player's deployment zone.
  `plunderable_terrain_area` targets exclude terrain fully within that player's
  deployment zone and are limited to one plundered terrain area per player
  turn. Cleanse objective targets exclude the player's home objective and
  objectives already selected for that player's Cleanse actions this turn. The
  engine first applies the canonical general Action eligibility query, excluding
  destroyed, embarked, reserve, `AIRCRAFT`, `FORTIFICATION`, Battle-shocked,
  Objective Control 0 or `-`, non-`TITANIC` engaged, Advanced, Fallen Back,
  already-shot, and already-Actioned rules units, and then applies the source
  `eligible_unit_policy`. Attached units are enumerated once by canonical rules-unit
  ID, combine component keywords and alive models, and use all component
  placements for target geometry and objective control. `MissionActionState`
  persists that canonical rules-unit ID and the selected `target_id`. A unit that
  started an Action cannot declare a Charge for the rest of that turn even if the
  Action completes immediately or is interrupted, and cannot shoot in that
  Shooting phase unless its rules unit is `TITANIC`. Immediate zero-VP actions complete in the same
  decision handler without creating a VP transaction; Booby Trap records an
  engine-owned terrain trap state for later primary scoring and Plunder records
  an engine-owned terrain plunder state for later secondary scoring. Turn-end
  zero-VP Cleanse completion validates objective control through the engine
  objective-control resolver and records an engine-owned objective cleanse
  state instead of creating a VP transaction. Mission Action target policies
  that are not yet represented as finite options return a typed `unsupported`
  status instead of exposing an adapter mutation path.

An accepted `continue_to_shooting` selection emits exactly one
`mission_action_opportunity_declined` mutation event containing the exact
request ID, result ID, selected option ID, and internal boundary evidence. On
restore, the engine reconstructs the complete Primary and held-Secondary
Action inventory from the referenced request checkpoint and requires exact
closure through `decision_requested`, `DecisionRecord`, `decision_recorded`,
the decline event, and the current `ShootingPhaseState` flag. A decline cannot
create `MissionActionState`; without that exact authority the flag must remain
false. Because the internal evidence contains the owning player's active
Secondary identities and complete Action inventory, shared adapter redaction
exposes the decline event only to that player and an omniscient administrator;
opponents receive no event payload through projections, deltas, responses, or
reconnects.

### Phase 17N Step 4 Primary Mission choices

Step 4 uses the public finite decision type
`select_primary_mission_choice`. The request payload is strict
`PrimaryMissionChoiceData` with `game_id`, `choice_kind`, `player_id`,
`primary_mission_id`, `source_descriptor_id`, `source_rule_id`, nullable
`battle_round`/`phase`, nullable `subject_id` and `source_action_id`, complete
`legal_target_ids`, empty `selected_target_ids`, `evidence_ids`, and
`used_fallback_candidates`. The round and phase are both null only for the
start-battle choice. Each option repeats that exact payload with its selected
target set. Adapters must select one option ID from the pending request and
must not edit the payload.

Option IDs are deterministic
`primary-mission-choice:<canonical-payload-sha256>` values. Their identity
binds the game, choice kind, player, source descriptor, subject, source Action,
and selected targets. The digest is opaque adapter data; clients must not
construct or decode it. Non-empty option labels are `Select <target IDs>` and
the empty Consecrate option is `Decline this choice`.

The supported choice kinds are:

- `locate_and_deny_setup`: at the final setup/start-battle boundary, each
  player assigned Locate and Deny receives all exact five-area combinations
  outside their own deployment zone, or the one exact all-available cardinality
  when fewer than five areas exist. Acceptance creates one public friendly
  operation marker for every selected logical terrain area. The setup
  completion gate cannot enter battle until every emitted request is resolved.
- `punishment_condemnation`: at the start of the assigned player's turn, the
  engine enumerates all one-, two-, and three-unit combinations, capped by the
  candidate count, from enemy battlefield rules units in objective range or
  identified by authoritative destruction evidence as previous-turn
  destroyers of friendly units. When that preferred candidate set is empty but
  battlefield enemies exist, options are exactly the single-unit fallbacks and
  `used_fallback_candidates` is true. When no candidate exists, the engine
  records an automatic empty condemned selection and opens no pending request.
- `consecrate_objective`: at the assigned player's turn end, one request is
  emitted for the next active consecration designation not yet resolved in
  that owner turn. Each eligible non-home objective in range of that designated
  rules unit that has never previously been consecrated is a singleton option,
  and an empty option declines. A removed/tombstoned Consecrate marker still
  proves that its objective was previously consecrated. Selection creates a
  public consecrated marker and consumes the designation. Decline retains the
  designation but records the current owner turn so it cannot prompt again
  until a later turn.
- `sensor_sweep_marker_removal`: after a qualifying Sensor Sweep Action has
  completed, every eligible active operation marker is a singleton option.
  `sensor-sweep-locate-and-deny` enumerates friendly operation markers;
  `sensor-sweep-extract-relic` enumerates opponent operation markers. The
  selected row becomes a provenance-complete `removed` tombstone and is never
  deleted.

Step 4 also completes the existing `start_mission_action` path for ten
source-backed Primary Actions: `commit-sabotage`, `decoy-objective`,
`extract-intelligence`, `maintain-control`, `secure-asset`,
`sensor-sweep-extract-relic`, `sensor-sweep-locate-and-deny`,
`surveil-enemy-unit`, `triangulate-objective`, and `vanguard-operation`.
Adapters continue to submit the emitted
`start:<mission_action_id>:<unit_instance_id>:<target_id>` option. The engine
owns target policies, use limits, Action state, immediate or turn-end
completion, marker/status effects, and follow-up Primary choices.

On lifecycle restore, a pending `start_mission_action` or
`select_primary_mission_choice` request is accepted only as the sole queue
head, with exactly one matching `decision_requested` event, no matching
`DecisionRecord`, and no later authoritative mutation. The lifecycle
regenerates the complete direct or opportunity Action inventory, or the
complete Locate and Deny, Punishment, Consecrate, or Sensor Sweep choice
inventory, from the restored boundary. Orphaned, duplicated, stale-context,
partial-option, and otherwise impossible pending sequences fail before the
request is exposed to an adapter. A pending Action request also requires its
engine-recorded boundary checkpoint immediately before `decision_requested`;
restore uses the checkpoint-backed pure option reconstruction path and does not
record a second checkpoint or request while authenticating it.

Each accepted Step 4 Action start is closed to exactly one authoritative
`DecisionRecord`. Its actor, request/result IDs, deterministic selected option,
selected option payload, complete eligible-unit inventory, mission/source
policy, unit, target, and condition target must agree with the persisted Action
and the later `mission_action_started` mutation. The exact
`decision_requested` and `decision_recorded` events precede that mutation.
Restore rejects a source-backed Action state or start event without that
decision closure.

The public `mission_action_started` event also carries typed
`mission_action_start_evidence` (`primary-mission-action-start-evidence-v1`).
This immutable bundle records the source round/phase and policy, complete legal
unit inventory, selected-unit eligibility state, objective/terrain or Surveil
range-and-visibility witnesses, relevant operation-marker inventory, and all
prior Action uses. Its typed start authority preserves the exact request and
every option plus one complete candidate row for every friendly rules-unit
membership at that boundary. It also preserves the typed battlefield identity,
dimensions, and exact terrain-feature inventory needed to reproduce historical
line-of-sight and visibility-cache inputs after later state normalization.
Candidate rows cover the stable component/model
universe, eligibility outcome, objective and Surveil witnesses, terrain-model
inventory, and derived legal Primary option IDs. Restore derives the eligible
unit and option inventories from those rows and requires exact agreement with
the full authoritative request, including every nonselected option. Live option
generation and restore consume the same generic policy evaluator. Restore
therefore enforces battle-round-two starts,
`once_per_turn`, `unlimited`, and
`unlimited_different_objective_per_unit_this_phase` across the complete ordered
Action history; Surveil's no-repeat target rule is enforced independently of
its unlimited Action count.

The engine's `primary_mission_boundary_checkpoint_recorded` events are internal
replay-authority records, not public battlefield events. Their authoritative
payload includes immutable active-Secondary card snapshots for both players,
including selection state, completed Mission Action snapshots, Primary
destruction history, Starting Strength records, and prior-use inventory. An
omniscient administrator receives that exact checkpoint. The owning player's
event view retains the earlier checkpoint shape without any internal Secondary
authority snapshot field and is re-addressed from that viewer-safe content; it
never exposes an opponent card, selection, count, completed Action witness,
destruction witness, Starting Strength witness, or a hash derived from hidden
snapshots. Opponents receive no checkpoint payload
through projections, event deltas, server responses, or reconnects.

For Secondary scoring, restore treats the objective-control checkpoint
snapshots as authority rather than as another copy of the stored scoring row.
Before transaction semantics are accepted, the engine rebuilds the active card
and selection, battlefield and deployment-zone occupancy, exact Primary-to-
Secondary destruction projections, completed Cleanse and Plunder projections,
and static Starting Strength inventory. The rebuilt rule-relevant evidence must
equal the stored `SecondaryScoringStateEvidence`; replacing that row together
with its derived ID, hash, rule metadata, transaction amount, and ledger total
does not authorize different scoring facts.

Restore authenticates every `primary_mission_boundary_checkpoint_recorded`
event in chronological order. Each checkpoint's complete physical state is
derived from already-authenticated authority plus intervening authoritative
mutations, so no checkpoint becomes a new trust root. Every `action_request`
checkpoint must be immediately paired with its exact `start_mission_action`
`decision_requested` event, and every `turn_end` checkpoint must be consumed by
exactly one matching Vanguard terminal-evidence event before the next
checkpoint. Orphaned, duplicated, or mismatched checkpoints fail closed.

Contract 10 additionally persists the engine-private
`objective_control_record_authorities` registry. Every Objective Control record
has exactly one content-addressed authority row binding its record ID/hash to a
closed `objective_control` boundary checkpoint and the exact retained
sticky-control witnesses applied to that result. Restore reconstructs
objective membership and characteristic authority from the frozen placement,
model, modifier-source, and mission-state evidence; it never derives an older
record from later battlefield positions. These rows and their embedded hidden
checkpoint state follow the same replay-only viewer boundary above and are not
adapter-visible projections or event deltas.

Turn ordering is engine-owned and blocking. Locate and Deny drains before
battle entry. Punishment drains after battle-round-start hooks and before the
ordinary Command phase start windows/body. At a player-turn end, the engine
records the authoritative turn-end objective-control boundary and resolves
started Primary Actions before emitting a Step 4 turn-end request; completed
Sensor Sweep removals have priority over Consecrate designations. Only one
request is pending at a time, and the engine recomputes the next opportunity
after each accepted result before it advances the turn. Surveil the Foe's
move-triggered removal of opponent operation markers is automatic at the
shared phase-flow boundary for each unprocessed completed-move event and is
not an adapter submission.

Destroying only a Bodyguard, Leader, or Support component does not interrupt an
Action: the original Attached Unit and its Action identity remain authoritative.
When the last model that started in that Attached Unit is destroyed, the ordinary
source-evidence-backed `mission_action_interrupted` path records
`interrupted_reason: "unit_destroyed"`. Both players consume that public event
through the ordinary viewer-scoped event stream, and replay preserves the same
payload. P19 adds no decision, submission, or event-delta schema.

These mission-scoring decision types must be submitted through `FiniteOptionSubmission -> DecisionResult -> GameLifecycle.submit_decision(...)`. Tests, replay, UI, CLI, network, and headless adapters must not call `GameState.discard_tactical_secondary(...)`, `GameState.score_secondary_mission(...)`, `GameState.record_tactical_secondary_replacement_use(...)`, or `GameState.record_mission_action_state(...)` directly for player choices; those methods are engine-owned primitives used by validated decision handlers and automatic rule hooks.

## Phase 12A Reaction And Sequencing Decisions

Phase 12A adds typed timing windows, reaction windows, sequencing conflict resolution, and persisting effects. These mechanics do not create a second adapter path.

Reaction windows that require a player choice emit an interrupt-style finite `DecisionRequest`. The current finite decision type is `resolve_reaction_window`. The request payload includes:

- `reaction_window`: the typed timing window payload;
- `interrupts_parent: true`;
- parent phase, parent step, and resume token;
- handler-specific JSON-safe context under `handler_payload`.

Adapters answer only by selecting one of the emitted option IDs. The reaction queue is lifecycle-persisted state and blocks parent phase execution until the engine records the `DecisionResult` through `GameLifecycle.submit_decision(...)` and emits `reaction_parent_resumed`. Adapters must not resume or mutate the parent phase themselves.

Sequencing conflicts use the finite decision type `resolve_sequencing_order`. During battle, the acting player is the active player. Before or after the battle, or at the start or end of a battle round, the engine first resolves a Phase 10J roll-off and makes the roll-off winner the request actor. The default request shape enumerates deterministic complete participant orderings. A during-battle conflict may instead use `payload.sequencing_model: "select_next_participant"`; that bounded shape carries the immutable previously selected prefix and only the remaining participants, with one `next:<participant_id>` option per remaining participant. Adapters must select one emitted option and must not invent participant IDs, alter either prefix, or sort rule effects locally.

Persisting effects are authoritative engine state, not adapter state. Effects target stable canonical unit IDs, remain associated with the original Attached Unit through component loss and while units Embark/Disembark, and expire at deterministic lifecycle boundaries. Adapter projections may display public effect payloads, but clients must not apply, transfer, or expire effects directly.

Required Phase 12A adapter-contract tests:

- reaction-window finite option round-trip and parent resume event;
- sequencing finite option round-trip for active-player ordering;
- sequencing roll-off ownership for start/end battle-round conflicts;
- deterministic JSON-safe payload round-trip for reaction windows, sequencing decisions, and persisting effects;
- viewer-scoped redaction tests for any future hidden reaction, sequencing, or persisting-effect payload.

## Phase 12 Stratagem Decisions

Stratagem use is a player-facing choice. Adapters must handle it through the same contract as every other choice:

- finite eligible choices use `DecisionRequest` option enumeration and `FiniteOptionSubmission`;
- non-enumerable target or placement details use `ParameterizedSubmission`;
- every accepted answer goes through `GameLifecycle.submit_decision(...)`;
- CP spend/refund/gain, target validation, event emission, and state mutation remain engine-owned.

The finite decision type is `use_stratagem`. A pending request exposes one option for each currently legal fully bound Stratagem use. Each option ID must be deterministic and stable for the pending request. Each option payload must be JSON-safe and include enough replay context for validation, including:

- game ID, player ID, battle round, phase, and timing-window ID;
- `stratagem_id`, source ID, CP cost, and availability source such as core or selected detachment;
- target-binding payload for fully enumerated targets;
- restriction context such as same-Stratagem-per-phase and any own once-per-turn/battle/per-target rule already checked by the engine.

`StratagemTargetSpec` payloads expose both all-of and any-of keyword gates.
`required_keywords` lists keywords that must all be present on the bound target.
`required_keywords_any` lists keywords where at least one must be present; an
empty list means no any-of gate. `excluded_keywords` and
`excluded_faction_keywords` list target keywords that make a unit ineligible.
Adapters may display these gates, but must not use them to invent targets or
override engine-emitted option enumeration.

WS14 source-backed faction detachment Stratagem activation records reuse this
same finite `use_stratagem` surface. The generated runtime records carry
structured timing, CP cost, target policy, target keyword gates, and a
checksum-covered `generic:rule-ir` effect payload produced at the source/data
boundary. Runtime and adapters must not read raw source JSON, compile rule
prose, or parse display text to decide whether a Stratagem is legal. Generic
target policies include `friendly_unit`, `enemy_unit`, `selected_target_unit`,
`not_selected_to_shoot_unit`, `not_selected_to_fight_unit`, and
`destroyed_target_by_just_shot_unit`; the engine filters owner,
selected-target trigger context, selected-to-shoot/fight phase state,
post-resolution destroyed-target trigger context, and excluded keywords before
emitting options or accepting parameterized target bindings.

Phase 17G adds Movement selected-to-move Stratagem windows to the same finite
`use_stratagem` contract. After `select_movement_unit` records a unit selection
and before `select_movement_action` is emitted, the Movement engine may emit an
optional `use_stratagem` request for the active player with trigger kind
`just_after_friendly_unit_selected_to_move`. The trigger payload includes
`selected_to_move_unit_instance_id`, `selection_request_id`, and
`selection_result_id`. Adapters decline with `decline_stratagem_window` or
select one engine-emitted Stratagem option; they must not infer additional
targets or skip directly to movement-action selection while a pending
`use_stratagem` request exists. Accepted selected-to-move Stratagems may create
engine-owned temporary movement keyword effects, such as `MOBILE`, that are
consumed by later movement proposal validation. Adapters must not add movement
keywords, adjust terrain traversal, spend CP, or mutate movement state directly.

Phase 17G also adds selected-unit Shooting and Fight Stratagem windows to the
same finite `use_stratagem` contract. After `select_shooting_unit` records a
unit selection and before `select_shooting_type` is emitted, the Shooting engine
may emit an optional active-player request with trigger kind
`just_after_friendly_unit_selected_to_shoot`. The trigger payload includes
`selected_to_shoot_unit_instance_id`, `selected_unit_instance_id`, and the
engine-owned shooting-unit selection payload. After `select_fight_activation`
records a unit selection and before melee declaration, the Fight engine may emit
an optional active-player request with trigger kind
`just_after_friendly_unit_selected_to_fight`. The trigger payload includes
`selected_to_fight_unit_instance_id`, `selected_unit_instance_id`, and the
engine-owned activation selection payload. Target policies
`selected_to_shoot_unit`, `selected_to_fight_unit`, and
`selected_to_fight_charged_unit` bind only the selected rules unit; the charged
variant additionally requires the engine-recorded charge-move effect for that
unit. Adapters must submit one emitted option or decline the window, and must
not infer selected units, charge history, weapon keywords, attack modifiers, or
CP spend locally.

Phase 17G also adds Shooting post-resolution Stratagem windows to the finite
`use_stratagem` contract. After a friendly shooting attack sequence completes,
the Shooting engine may emit an optional active-player request with trigger kind
`just_after_friendly_unit_has_shot`. The trigger payload includes
`shot_unit_instance_id`, `hit_target_unit_instance_ids`,
`destroyed_target_unit_instance_ids`, `destroyed_enemy_unit_instance_ids`,
`attack_sequence_id`, and `attack_sequence_completed_event_id`.
`destroyed_target_unit_instance_ids` means one or more models in that unit were
destroyed by the attacks; `destroyed_enemy_unit_instance_ids` is the narrower
all-models-destroyed unit set used by effects such as Corsair Coterie Into the
Breach. Path of the Outcast and Corsair Coterie Stratagem options use the
just-shot unit as the target binding. More Dakka options that react to an enemy
unit's completed shooting use `destroyed_target_by_just_shot_unit` and bind one
friendly unit from `destroyed_target_unit_instance_ids` while retaining the
just-shot enemy in `shot_unit_instance_id` for effect dispatch. Stratagems whose
effect chooses an enemy hit by those attacks carry `effect_selection` with
`effect_selection_kind: "hit_enemy_unit"` and
`hit_enemy_unit_instance_id`; adapters must submit one emitted option and must
not invent or substitute hit targets. Accepted `generic:rule-ir` handlers may
record Battle-shock results, detection-range persisting effects, or emit a
nested triggered-movement selection/proposal request. That follow-up movement
request remains engine-owned and must be answered through
`GameLifecycle.submit_decision(...)`.

Path of the Outcast Eldritch Suppression replay payloads report
`destroyed_model_modifier_applied` only for the Stratagem's destroyed-model
condition. Independently active selected-target Battle-shock modifiers are
audited through `selected_target_modifier_ids` and
`selected_target_modifier_source_ids`; adapters must not infer the destroyed-
model condition from the combined modified roll.

Corsair Coterie adds additional `use_stratagem` timing windows without creating
new adapter submission types. Active Shooting and Fight phase windows use trigger
kind `during_phase` and are emitted before the next ordinary unit-selection or
fight-activation request when legal options exist. Shooting payloads include
`selected_unit_instance_ids`, `shot_unit_instance_ids`, and
`skipped_unit_instance_ids`; Fight payloads include `ordering_band`,
`next_player_id`, `eligible_unit_instance_ids`, and
`selected_to_fight_unit_instance_ids`. After a friendly unit Falls Back, Movement
may emit trigger kind `just_after_friendly_unit_falls_back` with
`fell_back_unit_instance_id`, `engaged_enemy_unit_instance_ids`,
`movement_activation_completed_event_id`, source request ID, and source result
ID. Lethal Ruse options for ANHRATHE targets include `effect_selection_kind:
"engaged_enemy_unit"` and `engaged_enemy_unit_instance_id`; adapters must choose
one emitted engaged enemy option and must not infer engagement from positions.
Vengeful Sorrow's not-in-Engagement-Range condition uses that same physical
Engagement authority, including retained Fight On Death bases. Its destroyed-
model trigger preserves the narrow Stratagem exception: a target represented
only by its retained Fight On Death model may still receive the Stratagem and
its effect, but the retained model does not become ordinary living authority.

Source-backed generic RuleIR Stratagems may also include `effect_selection` with
`effect_selection_kind: "selected_friendly_companion_unit"` and
`companion_unit_instance_id` when an effect needs a second friendly rules unit
that is engine-enumerated with the primary target. If the source-backed effect
marks that companion optional, the emitted option may carry a null companion ID.
Adapters must submit one emitted option and must not invent companion unit IDs,
keyword pairings, reserve-arrival evidence, or affected-unit lists.

Shooting defensive Corsair windows use the same finite Stratagem contract. Just
after an enemy unit selects targets, the reacting player may receive trigger kind
`after_unit_selected_as_target` with `selected_target_unit_instance_ids`,
attacking unit/player IDs, and the attack sequence ID. After an enemy unit has
shot, the reacting player may receive trigger kind
`just_after_enemy_unit_has_shot` with `shot_unit_instance_id`,
`hit_target_unit_instance_ids`, `destroyed_target_unit_instance_ids`,
`destroyed_enemy_unit_instance_ids`, shooting player ID, attack sequence ID, and
completion event ID. Accepted `generic:rule-ir` handlers may record
source-backed wound-reroll permissions, phase-scoped weapon-profile effects,
charge-after-Fall-Back effects, target-range restrictions, mortal wounds, or
nested triggered movement requests.
Adapters must not apply AP, Stealth, target-range limits, charge permissions,
mortal wounds, or surge/triggered moves locally.

Accepted `StratagemUseRecord` payloads include `active_player_id`, `targeted_unit_instance_ids`, `affected_unit_instance_ids`, `effects_resolved`, `unresolved_reason`, and `effect_selection`. The active-player ID is part of the phase-instance key for matched-play same-Stratagem and same-target restrictions. `targeted_unit_instance_ids` is the sorted canonical rules-unit list used for the 11th Edition "same unit targeted" restriction and is scoped to the player using the Stratagem. `affected_unit_instance_ids` records every canonical rules unit affected by the handler, including non-target enemy units hit by an effect. Non-attached units use their own unit instance ID. Units that are part of an attached unit use the attached-unit ID, so a Leader/Support component and Bodyguard component share one phase restriction key. Targetless Stratagems record empty target lists unless their official TARGET field binds a unit. Ordinary accepted uses set `effects_resolved: true` and `unresolved_reason: null`.

Source-backed records whose `handler_id` starts with `unsupported:` are catalog descriptors only. They must not emit finite options, must not emit parameterized pending requests, and stale or hand-crafted submissions for them must be rejected with `unsupported_handler` before queue pop, CP spend, or Stratagem-use record creation.

Adapters must not invent `use_stratagem` option IDs, derive new target bindings from displayed payloads, spend CP directly, apply effects directly, or bypass the lifecycle to call lower-level state mutation APIs.

Stratagem decisions may be offered to the non-active player from a reaction window. The acting player on the `DecisionRequest` is authoritative; adapters should not assume the turn player is the player answering the request.

Some Stratagems need target or placement details that are not safe to pre-enumerate. Those requests use a parameterized proposal instead of a finite bound option. The request must embed a typed proposal request payload with a Stratagem-specific proposal kind, the same source `use_stratagem` context used by finite options, the source-backed catalog record, the timing context, the CP cost, the restriction policy, the handler binding, and replay-safe target context. Examples include:

- exact reinforcement placement after a Stratagem grants a reserves placement;
- geometric, line-of-sight, model-target, or path-dependent target proposals once the owning phase has the required validators;
- any future Stratagem whose legal target binding cannot be represented as a finite option set.

Phase 12B introduces the initial parameterized Stratagem target-binding decision type `submit_stratagem_target_proposal` with proposal kind `stratagem_target_binding`. The pending `payload.proposal_request` carries the same request identity envelope as other parameterized proposals: `request_id`, `decision_type`, and `actor_id`, followed by the Stratagem target-binding fields. Adapters answer only with the fixed `submit_parameterized_payload` option and a payload containing the typed `proposal` object. `proposal.effect_selection` is JSON-safe handler-owned selection context for optional sections or nested target choices, such as Heroic Intervention mode, Crushing Impact enemy/model choice, or Epic Challenge character model choice. Stale phase/round, malformed shape, schema-invalid missing target binding, wrong player/game/Stratagem/catalog context, CP drift including optional additional CP, and illegal target binding are rejected before queue pop and before any CP transaction or Stratagem-use record is created.

Phase-integrated optional Stratagem windows may also be declined through the same lifecycle path. Finite `use_stratagem` windows include the engine-emitted option ID `decline_stratagem_window` with payload `{"submission_kind": "decline_stratagem_window"}`. Parameterized `submit_stratagem_target_proposal` windows are declinable only when the engine marks the request payload with `declinable: true`; adapters decline by submitting the fixed `submit_parameterized_payload` option with the same decline payload instead of a typed `proposal`. A decline records a `DecisionRecord`, emits `stratagem_window_declined`, spends no CP, creates no `StratagemUseRecord`, applies no effect, and suppresses re-opening the same game/player/round/phase/trigger/timing-window. Phase hooks that expose multiple optional Stratagem opportunities under the same phase and trigger must assign distinct `timing_window_id` values so declining one window cannot suppress a separate later window. Reaction-window declines resolve the reaction frame and then emit `reaction_parent_resumed`.

Parameterized Stratagem submissions follow the Phase 11D invalid-submission rule: stale, drifted, malformed, schema-invalid, or wrong-context payloads are rejected before the queue is popped or a `DecisionRecord` is created. They must not spend CP or mutate state. Before emitting a parameterized Stratagem request, the engine evaluates its current legal target bindings and target-dependent runtime cost modifiers and requires at least one restriction-eligible, affordable candidate. This enumeration is engine-internal and does not convert the request into a finite adapter choice: adapters must still submit the target binding, and an unaffordable target remains invalid even when another target made the request available. Accepted parameterized submissions apply the Stratagem use atomically through `GameLifecycle.submit_decision(...)`: the engine re-checks timing, CP, restrictions, target validity, spends CP, records `StratagemUseRecord`, emits `stratagem_used`, and applies any Phase-12B-supported handler/effect payload. The only post-selection affordability exception is the source-backed cost-increase case documented in the Phase 17G Stratagem-cost modifier contract below. Rule-invalid but well-formed proposals may be recorded as rejected attempts only when the specific proposal contract explicitly allows that behavior and emits a fresh pending request for retry.

Phase 12C source-backed Core Stratagems are adapter-visible through these handler bindings:

- `core:command-reroll`: finite `use_stratagem` option at `after_dice_roll`; the option payload context includes `trigger_payload.dice_roll_state` and `trigger_payload.affected_unit_instance_id`, and the source-backed catalog definition includes `eligible_roll_types` for the edition-specific roll classes that may be re-rolled. The affected unit ID is canonicalized into the resulting `StratagemUseRecord.affected_unit_instance_ids` before the engine enforces the one-Stratagem-per-unit-per-phase restriction; missing, unknown, wrong-owner, stale attached-unit, or otherwise malformed affected-unit context is rejected before option emission and before queue pop. The 11th Edition source list covers Hit, Wound, Damage, saving throw, Advance, Charge, Hazardous, and number-of-attacks rolls; the normalized number-of-attacks roll type is `number_of_attacks_roll`. It does not include Leadership, Battle-shock, Desperate Escape, or no-save allocation-order roll classes. Desperate Escape uses hazard rolls in 11th Edition. Runtime attack/save roll specs can remain precise (`attack_sequence.hit`, `attack_sequence.wound`, `attack_sequence.save.*`, and random Damage roll types); Command Re-roll normalizes those to source-backed roll classes before eligibility comparison. Shooting and Fight attack-sequence hosts open the optional window after Hit rolls, Wound rolls, real armour/invulnerable saving throws, and random Damage rolls before that roll is consumed by the next attack step. Those attack-sequence `use_stratagem` requests are wrapped in the Phase 18B `OpportunityWindow` envelope: the request payload carries `submission_family: "opportunity_window"`, `opportunity_window`, `opportunity_window_id`, boundary state hash, sequence number, anchor event IDs, and the legal-action fingerprint; each use or decline option carries a matching nested `opportunity_submission`. `GameLifecycle.submit_decision(...)` validates wrong window IDs, stale state hashes, stale sequence numbers, changed legal-action fingerprints, wrong players, unavailable actions, malformed envelopes, and action drift before queue pop, CP spend, reroll mutation, or decline recording. A real armour or invulnerable saving throw remains an `attack_sequence.save.*` roll even when its target number is above 6 and cannot succeed on a D6. Synthetic ordered-allocation dice for effects that permit no saving throw use `attack_sequence.allocation_order.no_save` and are not saving throws. The engine rejects unlisted non-roll-off roll types and roll actor drift before option emission and before queue pop. Single-die rolls and Charge rolls resolve through Phase 10J whole-roll reroll semantics. Non-Charge multi-dice rolls emit a nested `select_dice_reroll` finite request with one legal reroll option per die, and lifecycle submission must select one engine-emitted option ID. For failed wound rolls with native reroll permissions such as Twin-linked, Command Re-roll is offered first at the failed wound timing; if declined, the native reroll resolves next and the same original wound roll does not immediately reopen another Command Re-roll prompt. Attack-sequence resumes reuse the recorded original or replacement roll state from the event log so replay, decline, and accepted reroll paths do not re-roll locally. This can be offered in a Phase 12A reaction window, and the parent resumes only after `command_reroll_resolved` and `reaction_parent_resumed` are emitted.
- Source-backed attack reroll permissions use the existing finite `select_dice_reroll` request at the Hit, Wound, or random Damage roll boundary before Command Re-roll is considered. Aeldari Fire Dragons' Assured Destruction is one generic catalog consumer: in the owning Shooting phase, attacks made by current Fire Dragon models against a rules unit with `MONSTER` or `VEHICLE` expose whole-roll Hit, Wound, and Damage rerolls. The request carries the original roll state, active attack/pool identity, attacker model, target rules unit, catalog record/clause/source IDs, required target keywords, and source payload. `GameLifecycle.submit_decision(...)` revalidates phase, active attack identity, source model membership/aliveness, target identity/keywords, permission identity, roll state, and source payload before queue pop or reroll mutation. Decline is scoped to that roll. Adapters must not infer keywords, reroll a value locally, replace the recorded roll state, or bypass the attack-sequence resume path.
- `select_dice_result_override`: finite `decline`/`use` options for a
  source-backed Hit or Wound result replacement. The request includes the roll
  ID/type and full roll state, attack sequence/context/pool indices, attacker
  model, target, source component unit, descriptor and source rule IDs, unit
  resource kind/cost/current count, replacement value, structured critical
  trigger markers, and a deterministic context fingerprint. The engine emits
  this request only after source-backed, Command Re-roll, and Twin-linked
  opportunities have resolved. A decline is scoped to that roll. Use spends
  the unit resource and records `unit_resource_spent` plus
  `dice_result_overridden` without consuming RNG; the resumed attack rebuilds
  its Hit/Wound result from that state. Actor, active attack identity, source
  membership/aliveness, excluded model keywords, descriptor identity, roll
  state, marker set, fingerprint, and resource balance are revalidated before
  queue pop. Visible unit projections expose starting and remaining public unit
  resource counts; hidden-unit redaction also removes those counts.
- `core:insane-bravery`: parameterized `submit_stratagem_target_proposal` for a unit pending a Battle-shock test that is not already Battle-shocked. The engine applies the shared friendly-Stratagem target restriction when deciding whether to emit the optional window and revalidates it before queue pop, CP spend, use recording, or auto-pass mutation. Accepted use records a persisting auto-pass effect and the Command phase resolves the Battle-shock test as passed without adapter-owned mutation. The source-backed once-per-battle restriction is unchanged.
- `core:rapid-ingress`: parameterized target proposal for an unarrived reserves unit during the opponent Movement phase end. Accepted use spends CP and records the Stratagem use, then emits a `submit_placement_proposal` request using the existing placement proposal contract. The placement answer must also go through `GameLifecycle.submit_decision(...)`. When Rapid Ingress is offered from a Phase 12A reaction window, the reaction frame continues from the target proposal to the placement proposal and the parent resumes only after a valid placement resolves. Rule-invalid but well-formed placement proposals are recorded as rejected attempts and emit a fresh pending placement request for retry; stale, malformed, or wrong-context placement proposals are rejected before queue pop.
- `core:new-orders`: finite `use_stratagem` options for active Tactical secondary cards. The target binding uses `target_kind: "tactical_secondary_card"` and `target_secondary_mission_id`; accepted use costs 1 CP, is once per game, discards that card, and draws one replacement through engine-owned Tactical secondary state.
- `core:heroic-intervention`: parameterized target proposal at the end of the opponent Charge phase for one friendly unengaged unit within 12" of enemy units. `proposal.effect_selection.mode` is optional and defaults to `leap_to_defend`; `into_the_fray` adds the source-backed +1 CP cost and caps the Charge roll result at 6 before emitting a Heroic Intervention `submit_movement_proposal` with proposal kind `charge_move`. That movement proposal carries the Stratagem use, mode, charge-roll state, maximum distance, and reachable target snapshot in its context and requires the normal Charge Move `PathWitness` validation path.
- `core:counteroffensive`: parameterized target proposal in the opponent Fight phase just after an enemy unit has fought. Accepted use costs 2 CP, validates that the target is eligible to fight through `FightOrderState`, records a Fights First effect until end of phase, and records the selected activation with a `counteroffensive:<stratagem_use_id>` interrupt ID before lifecycle progression resumes.
- `core:crushing-impact`: parameterized target proposal in the active player's Charge phase just after the selected friendly MONSTER/VEHICLE ends a Charge Move. `proposal.effect_selection.enemy_target_unit_instance_id` selects one engaged enemy unit and `proposal.effect_selection.model_instance_id` selects one placed living engaged source model. A destroyed model whose base is temporarily retained for Fight On Death remains physical geometry but cannot be selected as that source. Accepted use rolls D6 equal to that model's Toughness, applies self mortal wounds for each 1, enemy mortal wounds for each 5+ capped at 6, and emits `crushing_impact_resolved`.
- `core:epic-challenge`: parameterized target proposal just after a friendly CHARACTER unit is selected to fight. `proposal.effect_selection.character_model_instance_id` selects one CHARACTER model in the target unit. Accepted use records a per-phase Precision effect for that model's melee weapons and emits `epic_challenge_precision_registered`.

Phase 14G freezes the Charge/Fight ruleset contract but does not emit new player-facing decisions. `RulesetDescriptor.charge_policy` defines after-roll charge-target selection, 12" declaration/target-selection gates, rolled-distance target eligibility, charge-move endpoint constraints, and the Fights First grant. `RulesetDescriptor.fight_policy` defines the Start/Pile In/Fight/Consolidate/End step order, Fight-step-start engagement eligibility, current-engagement eligibility, charged-this-turn eligibility, Fights First and Remaining Combats ordering bands, both-player pile-in/consolidation sequencing, the more-than-5" eligible-pass rule, explicit Normal/Overrun fight types, and Ongoing/Engaging/Objective consolidation modes. Phase 15 Charge/Fight implementations must consume these source-contract payloads and then add or update this document for every finite option family, proposal kind, pending request payload, decision record, or event shape they expose.

Phase 15C emits finite Fight phase activation decisions with decision type `select_fight_activation`. Phase 15C derives activation requests from `FightOrderState`, while `FightPhaseState` remains the outer phase envelope. The pending request payload includes `game_id`, `battle_round`, `phase: "fight"`, `active_player_id`, the actor `player_id`, the exposed Fight step states (`start`, `pile_in`, `fight`, `consolidate`, `end`), the current ordering band (`fights_first` or `remaining_combats`), one replay-safe eligibility context per currently legal unit, and `eligible_pass_available`. Fight eligibility payloads preserve the source semantics: charged this turn, currently engaged, or engaged at the start of the Fight step. Activation option IDs are deterministic: `fight:<fight_type>:<unit_instance_id>`, where `fight_type` is `normal` or `overrun`, and the engine emits only fight types legal for that context. An attached formation is emitted exactly once under its canonical synthetic `RulesUnitView.unit_instance_id`; its leader, bodyguard, and support component IDs are not separate activation options. Option payloads include `submission_kind: "select_fight_activation"`, the selected canonical rules unit, the explicit fight type, ordering band, and the full eligibility context. That same canonical identity is retained by `FightActivationSelection`, selected-to-fight consumption, Fights First sources, and Fight events through component loss and until the last model that started in the Attached Unit is destroyed. Adapters must select one emitted option ID and must not infer fight eligibility, fight type, ordering band, component aliases, or step cursor locally. Stale player, ordering-band, unit-eligibility, fight-type, or eligibility-context drift is rejected before queue pop and before any activation record or event is created.

Phase 17G may emit a finite selected-to-fight ability decision with decision type `select_fight_activation_ability` after a unit is selected to fight and before its melee declaration request. The pending request payload includes the active `FightActivationSelection`, the selected unit, battle round, active/actor player IDs, one or more source-backed `ability_options`, and `decline_option_id: "decline_fight_activation_ability"`. Use options have deterministic option IDs `use:<ability_id>` and payloads containing `submission_kind: "use_fight_activation_ability"`, `hook_id`, `source_id`, `ability_id`, `enhancement_id`, selected unit, activation request/result IDs, `effect_kind`, and replay payload. `effect_kind: "fight_activation_melee_targeting_distance"` options carry `model_proximity_inches` and scope melee targeting permission to the current activation result. `effect_kind: "fight_activation_movement_distance"` options carry `pile_in_distance_inches` and `consolidate_distance_inches`; accepted use records an engine-owned `PersistingEffect` that the Fight movement proposal path consumes when exposing and validating Pile In or Consolidate `maximum_distance_inches`. The decline option uses `decline_fight_activation_ability` and records no effect. Adapters must not mutate melee target lists, attack pools, or fight movement distances directly. Stale activation context, repeated window use, wrong unit/player, malformed payloads, or option drift reject before queue pop.

Phase 17G may emit a finite selected-to-fight grant decision with decision type `select_fight_unit_grant` after a unit is selected to fight and before its melee declaration request when runtime content exposes legal selected-to-fight grants. Option IDs are deterministic source hook IDs. Optional grants also expose `decline_fight_unit_grant`. A grant payload may set `decline_allowed: false`; if any emitted grant is mandatory, the request has no global decline option. It exposes each mandatory grant by itself, plus deterministic `<mandatory_hook_id>:with:<optional_hook_id>` combinations so one existing optional grant can be accepted alongside the required choice. Accepted options may record engine-owned source spend and unit effects; adapters must not spend resources, invent grant IDs, locally add a decline option, or mutate reroll permissions locally. Drukhari `Power from Pain: Hatred Eternal` uses the optional surface to spend one Pain token and record a Fight-phase hit-reroll empowerment before the unit declares its melee attacks. Daemon Prince of Chaos with Wings `Harbinger of Death` uses the mandatory surface to select exactly one engine-emitted weapon ability for the source-backed Hellforged weapon profiles. Emperor's Children Flawless Blades `Daemonic Patrons` uses the optional surface to record source-bound RuleIR until the Fight phase ends; while active, every attack made by a model in that rules unit treats an unmodified Wound roll of 3+ as a Critical Wound. The engine, not an adapter, later evaluates the associated no-kill consequence at Fight end. Stale activation context, wrong unit/player, malformed payloads, source-resource drift, or option drift reject before queue pop.

Each selected-to-fight grant option serializes `decision_effect_payload`, an ordered `timed_effects` list whose entries contain `effect_payload` and `expiration`, and one optional `immediate_effect_payload`. At least one of those three effect surfaces must be populated. Accepted grants record every timed effect in order before the engine resolves the immediate consequence. Blood Legion `Fury's Cage` uses this existing optional decision: acceptance resolves source-backed D3+1 mortal wounds against the bearer without spillover, may yield the standard `select_feel_no_pain` continuation, and records separate bearer-scoped Hit- and Wound-reroll RuleIR effects until the end of the Fight phase. Adapters choose only the emitted use or decline option; they must not roll the mortal wounds, route damage, select a different model, create reroll effects, or skip a pending Feel No Pain continuation.

If those mortal wounds destroy the bearer, the engine routes that already-applied damage through the shared destruction-reaction owner before final removal. Mandatory Deadly Demise resolution, its nested Feel No Pain requests, and an eligible optional Fight on Death request therefore remain ordinary engine decisions and continuations. When an attached rules unit survives, the synthetic attached identity remains authoritative after the activation and its Fight-state identity remains consumed, so component loss cannot make a surviving component selectable twice. Adapters must not remove the bearer early, replace activation identities, or bypass any nested destruction request.

Adeptus Custodes `Martial Ka'tah` uses the existing `select_fight_unit_grant` surface. The engine may emit `warhammer_40000_11th:adeptus_custodes:army_rule:martial_katah:dacatarai` or `warhammer_40000_11th:adeptus_custodes:army_rule:martial_katah:rendax`, plus `decline_fight_unit_grant`, after an eligible Custodes unit with Martial Ka'tah is selected to fight. Accepted option payloads record `effect_kind: "adeptus_custodes_martial_katah"`, `unit_instance_id`, `target_unit_instance_ids`, `trigger: "selected_to_fight"`, `phase: "fight"`, `selected_martial_katah` (`dacatarai` or `rendax`), and replay-safe `source_context`. The selected stance is consumed by the shared Fight attack-resolution path: Dacatarai grants melee `SUSTAINED HITS 1`, and Rendax grants melee `LETHAL HITS`, for the selected rules unit until the Fight phase effect expires. Adapters must not locally add melee weapon keywords or infer stance effects outside the accepted engine effect.

Chaos Space Marines `Dark Pacts` and Chaos Daemons Shadow Legion `Disciples of Be'lakor` use the existing `select_shooting_unit_grant` and `select_fight_unit_grant` surfaces. The engine may emit `warhammer_40000_11th:chaos_space_marines:army_rule:dark_pacts:shooting:lethal_hits`, `warhammer_40000_11th:chaos_space_marines:army_rule:dark_pacts:shooting:sustained_hits_1`, `warhammer_40000_11th:chaos_space_marines:army_rule:dark_pacts:fight:lethal_hits`, `warhammer_40000_11th:chaos_space_marines:army_rule:dark_pacts:fight:sustained_hits_1`, `phase17f:phase17e:chaos-daemons:shadow-legion:rule:shadow-legion:shooting:lethal_hits`, `phase17f:phase17e:chaos-daemons:shadow-legion:rule:shadow-legion:shooting:sustained_hits_1`, `phase17f:phase17e:chaos-daemons:shadow-legion:rule:shadow-legion:fight:lethal_hits`, or `phase17f:phase17e:chaos-daemons:shadow-legion:rule:shadow-legion:fight:sustained_hits_1`, plus the normal decline option for that grant family. Shadow Legion option IDs are generated by the generic IR execution record for `phase17e:chaos-daemons:shadow-legion:rule`; adapters must treat them as pending option IDs and must not depend on the former named-handler IDs. Accepted option payloads record `effect_kind: "chaos_space_marines_dark_pact"`, `unit_instance_id`, `target_unit_instance_ids`, `trigger`, `phase`, `selected_dark_pact` (`lethal_hits` or `sustained_hits_1`), replay-safe `source_context`, and `leadership_test_auto_pass`. Shadow Legion sets `leadership_test_auto_pass: true` only when the selected unit is Be'lakor; other Dark Pacts sources set it to `false`.

Out-of-phase shooting such as Fire Overwatch emits the same selected-to-shoot grant request before the constrained `submit_shooting_declaration` proposal. Adapters must submit pending option IDs unchanged and must not add weapon keywords, roll Leadership tests, choose Feel No Pain sources outside the pending request, or apply mortal wounds locally. The engine applies the selected weapon keyword to the matching Shooting or Fight weapon profiles during attack resolution, then resolves the post-attack Leadership test and any resulting D3 mortal wounds through the attack-sequence-completed hook. Be'lakor automatically passes that Leadership test when the effect source is Shadow Legion. If failed-test mortal wounds require a Feel No Pain source choice, the engine emits the standard finite `select_feel_no_pain` request with `lost_wound_context.context_kind: "mortal_wound"` and `source_context.source_kind` set to either `chaos_space_marines_dark_pacts` or `chaos_daemons_shadow_legion_dark_pacts`; adapters answer it through `GameLifecycle.submit_decision(...)`, and the registered runtime content continuation hook resumes the Dark Pacts mortal-wound application.

The `chaos_space_marines_dark_pact_resolved` event preserves
`leadership_roll` as the raw `DiceRollState` payload (or `null` for an automatic
pass) and records the modifier-aware `ModifiedRollResult` separately as
`leadership_modified_roll` (also `null` for an automatic pass). Pass/fail uses
the latter final value. Consumers that need dice provenance must continue to
read the raw field and must not treat it as a modified-roll payload.

Phase 17G Cavalcade of Chaos Movement-phase Stratagems use source-backed `generic:rule-ir` records through the normal finite `use_stratagem` decision path. Warp-Riders is offered in the selected-to-move window and records an engine-owned generic RuleIR `grant_ability` effect for `MOBILE` until the phase ends. From Beyond the Veil is offered to the active player at the end of their Movement phase after ordinary reserve arrivals and optional opponent end-Movement reactions are declined or resolved. Accepted use spends CP, records the Stratagem use, then emits `submit_placement_proposal` with proposal kind `strategic_reserves_placement`, placement kind `strategic_reserves`, and context containing `stratagem_handler_id: "generic:rule-ir"`, the serialized Stratagem use, the selected `reserve_state`, `from_start_of_battle: true`, `placement_scope: "strategic_reserves_only"`, `generic_rule_execution_result`, and `generic_rule_effect`. The placement submission is validated by the same Strategic Reserves engine path as ordinary reserve arrivals; adapters must not set reserve arrival state directly.

Phase 17G also uses `generic:rule-ir` for Inescapable Manifestations during opponent Movement phase Fall Back selection. After the active player selects `select_movement_action` with Fall Back, the Movement engine may open a reaction-window `use_stratagem` request for the non-active player when an eligible friendly unit is engaged with that falling-back enemy unit. Accepted use spends CP and records an engine-owned persisting effect on the enemy unit from a generic RuleIR `force_desperate_escape_tests` effect, then the parent Movement action resumes with a `submit_movement_proposal` Fall Back request whose context preserves the declared mode under `declared_fall_back_mode` and forces `fall_back_mode: "desperate_escape"` with replay-safe `forced_desperate_escape_source_rule_ids` and `forced_desperate_escape_stratagem_use_ids`. Adapters must submit a Fall Back movement proposal using the emitted forced mode; they must not locally downgrade or bypass Desperate Escape.

Catalog ability sources at the selected-to-Fall-Back timing use the same source-enriched Fall Back proposal path even when no Stratagem or optional movement-grant decision intervenes. The request preserves the declared mode, forces `fall_back_mode: "desperate_escape"`, and carries replay-safe entries in `forced_desperate_escape_sources`.

Phase 15C eligible-to-fight passes are finite options on `select_fight_activation` using option ID `eligible_to_fight_pass`. Current Engagement and the Fight-step-start Engagement snapshot are computed by one symmetric physical query over every battlefield-present base on both sides, including a destroyed base retained for Fight On Death. Such a base can therefore establish Fight eligibility for both rules units without becoming ordinary attack, damage, Pile In, or Consolidation target authority. The pass option is emitted only when every currently eligible unit for the actor is more than the source-backed pass distance (`RulesetDescriptor.fight_policy.eligible_pass_distance_inches`, currently 5") from all physically present enemy bases. The option payload includes `submission_kind: "eligible_to_fight_pass"`, the actor, ordering band, pass distance, and the eligible unit snapshot. Adapters must not synthesize a pass option or infer physical Engagement locally. Stale unit snapshots, player drift, ordering-band drift, or pass-distance drift reject before queue pop.

Phase 15C fight interrupts use the Phase 12A reaction queue and decision type `resolve_fight_interrupt`. The request payload includes the ordinary reaction wrapper (`reaction_window`, `interrupts_parent`, and parent resume metadata) plus a handler payload with `phase_body_status: "fight_interrupt_required"` and a `FightInterruptRequest`. The engine emits a deterministic decline option `decline_fight_interrupt` and deterministic activation options using the same `fight:<fight_type>:<unit_instance_id>` option IDs and eligibility payload shape as normal fight activations, with `submission_kind: "select_fight_interrupt"` and the interrupt payload embedded. Accepted interrupt selections record the activation through the same fight-order state, append a `ResolvedFightInterrupt` for the trigger-specific interrupt ID and underlying `source_effect_id`, and resume the parent reaction frame. Declines append the same source-scoped consumption record and resume the parent frame. Hand-crafted, repeated-source, stale, wrong-context, or ineligible interrupt submissions reject before queue pop. Repeated-source validation is keyed by the source effect ID, not only by a trigger-event-specific interrupt ID.

Phase 15D implements Pile In, melee declaration/attack resolution, and Consolidate through the same lifecycle decision path. Normal fights are still not modeled as activation-local Pile In -> attacks -> Consolidate flows: Pile In and Consolidate are separate both-player steps, while Overrun Fight has its own activation-local additional Pile In before melee attacks. Activation events no longer emit `phase15d_resolution: "deferred"`.

Phase 15D Pile In and Consolidate use `submit_movement_proposal` with proposal kinds `pile_in` and `consolidate`. Normal Fight movement source enumeration emits one request for each placed `RulesUnitView` with at least one living model; an attached formation is exposed only through its canonical synthetic rules-unit ID, never as separate component options, and Overrun retains that same canonical activation identity. Legal target-unit IDs are likewise canonical and deduplicated, and each selectable enemy target must contain at least one placed living model, so a component-alias target submission is typed invalid with `fight_movement_target_identity_not_canonical` and a Fight On Death-only enemy is never selectable. Retained destroyed bases remain fixed collision geometry: paths cannot cross them, endpoints cannot overlap them, and a living model already in base contact with one cannot move in any Pile In or Consolidation mode, including Objective Consolidation. When their mixed rules unit still has a living model and is therefore selectable, those bases also remain available for source-required measurement without becoming attack, damage, or movement authority. The same symmetric physical Engagement query owns movement-mode selection, continuing-Engagement requirements, and Objective endpoint validation. If the only physically engaged enemy rules units are destroyed-only, there is no legal Pile In target and no legal Consolidation mode; the unit cannot fall through to Engaging or Objective Consolidation. A retained-only enemy outside Engagement Range does not become a target merely because it is within 3" or 5", and it does not prevent an otherwise legal Objective Consolidation. The pending proposal request is actor-scoped to the canonical unit currently selected for that Fight movement step and exposes `phase: "fight"`, `movement_phase_action` (`pile_in` or `consolidate`), `movement_mode` (`pile_in` or `consolidate`), `maximum_distance_inches`, legal target-unit IDs, legal consolidation modes when applicable, objective context when applicable, source fight-step timing context, and the ruleset descriptor hash. Adapters answer with `ParameterizedSubmission` and the fixed `submit_parameterized_payload` option. The payload is a `FightMovementProposal` containing `proposal_request_id`, `proposal_kind`, canonical `unit_instance_id`, `movement_phase_action`, `movement_mode`, canonical target-unit fields (`pile_in_target_unit_instance_ids` or `consolidate_target_unit_instance_ids`), optional `consolidation_mode`, optional `objective_id`, and `witness` when models physically move. Source-backed selected-to-fight effects such as `fight_activation_movement_distance` can raise the emitted and validated maximum above the default 3"; effects sourced to either an attached formation or one of its component lineage IDs apply to the canonical request. For an attached formation, one witness must cover every placed living model across each component that still has a living model. A destroyed model retained by Fight on Death is never included in the witness and its placement remains fixed. If an Overrun additional Pile In reaches a Fight On Death-only activation with no living movable model, the engine emits `overrun_pile_in_not_available` with reason `no_living_movable_models` and continues without a proposal. The engine validates submitted paths as one attempted rules-unit movement, checks endpoint coherency across the moving group once, and either applies every living-model endpoint and transition atomically or applies none. A successful attached `fight_movement_completed` event retains the canonical outer `unit_instance_id`, includes `active_player_id`, and carries a grouped `resolution` with `rules_unit_instance_id`, sorted `component_unit_instance_ids`, `before_rules_unit_placement`, `attempted_rules_unit_placement`, the shared `witness`, endpoint evidence, per-model path/terrain evidence, group coherency evidence, and any rollback evidence; the grouped placements preserve physical component provenance and the transition batch contains each moved living model exactly once. Standalone-unit resolution payloads retain their existing shape; the completed event now also includes `active_player_id` and additive `movement_endpoint_placement` evidence containing the authenticated event-time attempted `UnitPlacement`, which shared move-event consumers validate against the canonical outer identity, endpoint witness, and transition batch. The resolution `endpoint_witness.engaged_before_unit_ids` and `engaged_after_unit_ids` remain canonical selectable-target snapshots and therefore contain only rules units with placed living target authority; they are not the full physical Engagement inventory, and adapters must not add retained-only IDs. Both `fight_movement_completed` and recorded `fight_movement_invalid` events carry additive `target_authority_witness` rows in selected-target order. Each row contains the canonical `target_unit_instance_id` and the sorted, non-empty `placed_living_model_instance_ids` present immediately before resolution; restore and replay bind those rows to the submitted target IDs and authenticate their event-boundary lineage and liveness across later destruction, removal, return, or revival. A no-move answer has no selected target/objective context and no witness and resolves atomically for the living members of all represented components. Stale, malformed, wrong-kind, wrong-action, wrong-mode, wrong-unit, component-alias, illegal target/mode/objective, no-move-with-witness, target-without-witness, or witness-start/model-ID drift submissions reject before queue pop and before a `DecisionRecord`. Restore applies the same living-model authority checks to pending target inventories and Fight movement requests. Every relevant recorded Fight movement result must bind to its authoritative terminal event; an accepted witness must equal that completion event's exact event-time placed-living inventory and must not include a model whose Fight On Death authority already began. This preserves an earlier legal move when the model was destroyed only later. Rule-invalid but well-formed fight movement proposals, including degenerate repeated-endpoint paths, over-distance paths, terrain/pathing/coherency failures, or invalid engagement/objective endpoints, are recorded as rejected attempts, emit typed diagnostics, retry with a fresh request, and do not mutate battlefield state.

Phase 15D melee declarations use decision type `submit_melee_declaration` with proposal kind `melee_declaration`. The pending request contains one `submit_parameterized_payload` option and `payload.proposal_request` with `phase: "fight"`, active/actor player IDs, canonical rules-unit `unit_instance_id`, source fight activation request/result IDs, `ruleset_descriptor_hash`, canonical `target_unit_instance_ids`, and `available_weapons`. Every available weapon payload includes `model_instance_id`, `wargear_id`, `weapon_profile_id`, full weapon-profile payload, `is_extra_attacks`, `maximum_declared_targets`, `fixed_attacks`, and canonical `engaged_target_unit_instance_ids` for that model/weapon. For an attached formation, each row additionally includes `rules_unit_instance_id` and `component_unit_instance_id`; `available_weapons` aggregates every eligible attacking model across all physical components while preserving component and model provenance. Standalone rows retain the pre-existing payload shape so unchanged decisions remain replay-compatible. Enemy attached leader/bodyguard aliases are deduplicated to their one canonical target identity and require at least one placed living target model. A model awaiting Fight on Death can supply its own melee weapon row during its rules unit's ordinary attack selection. Its retained placement participates in symmetric physical Engagement when it is on the opposing side, but it never appears in melee target-model evidence and cannot receive attack allocation or damage; an otherwise targetable mixed rules unit still requires placed living target authority. `[ONE SHOT]` melee weapons already selected earlier in the battle are omitted from `available_weapons`; a stale proposal attempting to redeclare one rejects before queue pop. Source-backed fight activation ability effects may add target unit IDs to these engine-emitted `engaged_target_unit_instance_ids` snapshots for the current activation only, but do not override the living-target requirement. A component-alias or otherwise non-canonical target submission rejects with `melee_target_identity_not_canonical`. Adapters must select only from these engine-emitted weapon and target payloads; they must not infer engagement, component membership, weapon ownership, attack counts, melee weapon keywords, one-shot availability, or fight ability targeting permissions locally.

`MeleeDeclarationProposal` submissions contain `proposal_request_id`, `proposal_kind: "melee_declaration"`, player ID, battle round, `unit_instance_id`, source activation request/result IDs, and one or more `MeleeWeaponDeclaration` entries. Each declaration has `attacker_model_instance_id`, `wargear_id`, `weapon_profile_id`, and `target_allocations`; each target allocation has `target_unit_instance_id` and, when required for split attacks, `attacks`. While fighting, each fighting model with a legal engaged target and an available non-extra melee weapon must declare exactly one non-extra primary melee weapon. `[EXTRA ATTACKS]` weapons owned by that model may be added as separate declarations and do not count as the primary. Each declared target must be in that weapon payload's `engaged_target_unit_instance_ids`. A weapon cannot declare more target units than its Attacks characteristic. When more than one target is selected for one weapon, each target must receive at least one attack and the declared attacks must sum to the fixed Attacks characteristic; random-Attacks split declarations are typed invalid until a fixed count exists. A single target may omit `attacks`, in which case the engine gathers that weapon's full attack count through the shared attack-dice logic.

Accepted melee declarations lower to shared `RangedAttackPool` records with `source_phase: "fight"` and `targeting_rule_ids` including `fight_phase_melee`; accepted events also include any `one_shot_weapon_use_records` created for selected `[ONE SHOT]` melee weapons. The subsequent Making Attacks sequence is the same shared engine path as Shooting: `select_resolve_target_unit`, `select_attack_weapon_group`, hit, wound, allocation order, damage allocation, save, Feel No Pain, and destruction-reaction decisions use their existing option payload shapes, but their pending request/status payloads remain Fight-owned with `phase: "fight"` and attack contexts carry `source_phase: "fight"`. Stale, malformed, wrong-proposal-kind, wrong-source-activation, descriptor-hash drift, missing required primary weapons, duplicate declarations, invalid extra-attack use, invalid target allocation, invalid split counts, used `[ONE SHOT]` weapon use, or model-engagement drift reject before queue pop and before any attack sequence or battlefield mutation is created.

Phase 15E adds these Stratagem-coupled Charge/Fight decisions:

- Heroic Intervention target selection uses `submit_stratagem_target_proposal`; accepted use may emit a nested `submit_movement_proposal` Charge Move request. The nested request context includes `stratagem_handler_id: "core:heroic-intervention"` so lifecycle routes it back through the Heroic Intervention charge validator. Reaction frames may carry this movement proposal and only resume after the proposal resolves.
- Counteroffensive and Epic Challenge are `submit_stratagem_target_proposal` requests emitted from Fight-step timing hooks. Counteroffensive target proposals are reaction-window requests for the opponent after an enemy unit has resolved attacks. Epic Challenge target proposals are declinable requests for the player whose CHARACTER unit has just been selected to fight.
- Crushing Impact is a Charge-phase `submit_stratagem_target_proposal` after a friendly MONSTER/VEHICLE ends a Charge Move. Its nested enemy/model selections are carried in `effect_selection`, not in adapter-owned state.

Core Heroic Intervention timing is hosted at the end of every opponent Charge
phase whenever the reacting player has at least one concrete legal and affordable
target. The timing window is not gated by possession of a source-backed exception
unit. Source-overlaid Stratagem records retain the ordinary parameterized proposal
shape and `core:heroic-intervention` handler; target-specific validation applies
the normal once-per-phase restriction and cost to ordinary targets or the
source-backed phase-use exception and cost modifier to a qualifying target.

Source-backed per-unit exceptions to Heroic Intervention's or
Counteroffensive's same-Stratagem-per-phase restriction retain the corresponding
Core proposal shape and handler.
When such a source is active, the embedded catalog record's
`definition.effect_payload.stratagem_phase_use_exception` contains the stable
source ability ID, runtime descriptor ID, exact eligible datasheet IDs,
`frequency_scope: "phase_per_unit"`, and the two non-blocking phase-use flags.
The engine may therefore keep the parameterized opportunity available after an
earlier use when a concrete qualifying target remains legal and affordable. Adapters
must treat this payload as engine-owned availability context: they must not
infer qualifying units from display names or rule text, suppress the opportunity
because another unit used the same Stratagem, or synthesize an additional use.
Target-specific validation rejects a second use by the same qualifying unit
with `source_ability_once_per_phase_per_unit`. Accepted qualifying uses still
follow the ordinary proposal, CP transaction, `StratagemUseRecord`,
`stratagem_used`, `counteroffensive_activation_selected`, and replay paths.
Any source-backed CP discount is recorded in
`command_point_modifier_ids` and `command_point_modifier_source_ids`; no new
decision type or proposal field is introduced.

Adapters must not synthesize these timing windows, `effect_selection` keys, charge-move reachable-target snapshots, model Toughness rolls, Fights First effects, Precision effects, or mortal-wound applications. They select pending options or submit the pending proposal shape, and the engine owns validation and mutation.

Phase 14H updates Transport Disembark decisions to expose the source-backed `disembark_mode` on every pending Disembark `select_movement_action`, `submit_placement_proposal`, Disembark selection payload, Disembarked unit state, destroyed-Transport disembark payload, and `unit_disembarked` event. Valid mode tokens are `rapid_disembark`, `assault_disembark`, `shock_disembark`, `tactical_disembark`, `combat_disembark`, `destroyed_transport`, and `emergency_disembark`. Adapters must submit the pending mode token unchanged unless the pending placement proposal context exposes an explicit `allowed_disembark_modes` list containing the submitted token; stale, malformed, omitted, or wrong-mode finite and parameterized submissions reject before authoritative mutation. A Disembark proposal must also echo the pending `transport_unit_instance_id` and complete `restriction_overrides` list exactly; wrong-Transport, missing, added, or altered source permissions reject before queue pop. Tactical, Rapid, Assault, and Shock Disembark placement is always submitted through `submit_placement_proposal`; adapters must not infer or synthesize model placement from finite option payloads. `rapid_disembark` is used after a Transport's Normal/Ingress movement when no Assault permission applies and records no further movement or charge permission. `assault_disembark` is selected only after a Normal Move when authoritative persisting effect state names the canonical passenger rules unit, Transport, and permitting rule source ID. Its grouped placement remains wholly within 3", completes that passenger activation with no further move, and records `can_declare_charge: true`, the Core 18.06 source ID, and `permission_source_rule_id` through state, replay, and the public `unit_disembarked` event. `shock_disembark` is selected only after an Advance when an equivalent typed permission names that passenger, Transport, and permitting source. The proposal request additionally carries `start_engaged_enemy_unit_instance_ids`, the sorted canonical rules-unit identities physically engaged with the Transport at move start; the submission must echo that list exactly, and omission, malformed IDs, stale identity, or drift rejects before queue pop. Accepted grouped placement remains wholly within 3", may be engaged only with those enemies, and must preserve engagement with every listed enemy. The public `unit_disembarked` event and `DisembarkedUnitState` retain that snapshot and the Core 18.07 source identity. If a listed enemy has not already been selected to fight in the current phase, the engine emits the existing public `select_fight_activation` decision to that enemy's owner with `eligible_pass_available: false` and a `forced_activation_context` binding the 18.07 source ID, triggering disembark event, Movement source phase, passenger, Transport, selecting player, and eligible canonical enemy IDs. The opponent selects one ordinary Fight activation option at a time; selected-to-fight hooks, melee declaration/attack execution, `fight_activation_selected`, and `unit_has_fought` remain engine-owned canonical Fight paths. The forced context repeats on request, option, status, and events, is visible identically to both players in the current public-information scope, survives restore/replay, and is cleared only after every still-eligible listed enemy has resolved. Adapters must not reorder, omit, pass, synthesize, or directly execute those activations. Every retained `DisembarkedUnitState` also carries `turn_player_id`, the player whose turn created the restriction; `unit_disembarked.active_player_id` carries that same turn identity and can therefore differ from the passenger-owner decision actor during destroyed-Transport timing. Move-completed mortal-wound and Battle-shock hooks authenticate their `triggering_player_id` from the embedded `DisembarkedUnitState.player_id`, while retaining `active_player_id` exclusively as turn identity. Turn-end cleanup expires all such states created during the completed turn, including opponent-owned Emergency Disembark state. Restore requires the retained state to correspond exactly to one `unit_disembarked` event and its recorded `submit_placement_proposal` request/result, including mode, Transport, movement status, the complete `restriction_overrides` list, and the Shock engagement snapshot where applicable; Assault and Shock permissions are accepted only when the exact override source matches `permission_source_rule_id`. Adapters display and return those engine-authored fields but cannot grant, alter, transfer, or consume the permission. `tactical_disembark` is used when the Transport has not moved, forbids choosing Remain Stationary afterward, and keeps the unit in the shared Movement action decision path after the exact `unit_disembarked` setup-hook occurrence closes. When a Tactical placement proposal advertises both `tactical_disembark` and `combat_disembark` in `allowed_disembark_modes`, a submitted Combat placement is accepted only after the engine first evaluates the same submitted placement as Tactical and records deterministic Tactical-invalid fallback evidence; if that Tactical placement is legal, the Combat submission is rejected and the placement request is re-emitted. `destroyed_transport` and `emergency_disembark` are replay/domain modes for the corresponding source-backed destroyed-Transport rule paths and must not be inferred locally from placement distance. At Emergency Disembark timing, the engine snapshots every living embarked model, resolves all Hazard Rolls and their shared mortal-wound/Feel No Pain decisions while those models remain unplaced, then emits `submit_placement_proposal` only for the exact survivor IDs. For an attached passenger, the immutable `hazard_rolls` payload uses the canonical attached rules-unit ID, carries the complete sorted `component_unit_instance_ids`, and contains every living model's roll across those components. The one survivor-placement request keeps that canonical ID and adapters must answer with `attempted_rules_unit_placement`; its physical `UnitPlacement` components preserve model ownership, but validation, battlefield placement, cargo removal, `DisembarkedUnitState`, and `unit_disembarked` evidence commit together under the canonical rules-unit identity. No component-level request or restorable intermediate component placement exists. A placement containing any casualty rejects before queue pop with `destroyed_transport_non_survivor_placement`, and restore rejects a survivor tuple or request context that does not exactly match the completion event and authoritative living-model state. The engine enters this flow from the actual destruction event before Transport removal and Deadly Demise resolution, and lifecycle submission routes the accepted survivor placement back through the owning attack sequence. `combat_disembark` has a dedicated domain resolver for 6" placement, official 1-2 Hazard Rolls, shared mortal-wound/Feel No Pain routing, Battle-shock, no-charge state, and the narrow permission to set up engaged only with enemy units engaged with the Transport. Attached passengers use one canonical grouped resolver: all component placements, cargo transitions, per-model Hazard Rolls, damage allocation, activation completion, and serialized FNP continuation succeed atomically under the attached rules-unit ID or none do.

Phase 14H Healing Wounds effects use the finite `select_healing_model` decision when the next one-wound healing step has multiple legal targets. The engine iterates each healing amount separately: wounded models are healed before any revival; if the unit is below Starting Strength and every alive model is at full wounds, one destroyed removed model becomes the next revival candidate; if the unit is at Starting Strength and full wounds, the step records no effect. Ambiguous wounded-model choices and ambiguous destroyed-model revival choices default to the opposing player, but source-backed effects may set `selection_actor_player_id` when the source rule gives the choice to another player; Necrons Reanimation Protocols uses the owning Necrons player. Option IDs are emitted by the engine, and model-option payloads include `submission_kind: "select_healing_model"`, `selection_kind` (`heal_wound` or `revive_model`), `effect_id`, `target_unit_instance_id`, `step_index`, the selected `model_instance_id`, `legal_model_ids`, and source rule/context. A source-backed optional revival may also set `allow_revival_finish: true`; the engine then emits `select_healing_model` even for one candidate and adds a deterministic `selection_kind: "finish"` option with `model_instance_id: null` before the first revival and after every completed revival while legal candidates remain. Selecting it records a replay-safe terminal healing step without returning another model. The request payload embeds the serialized `HealingEffect`, including `selection_actor_player_id` when present. Adapters select one pending option ID and do not invent model IDs, early-completion state, or wound mutations from local state.

Every revival candidate, including a single unambiguous candidate, then emits the parameterized `submit_healing_revival_placement` decision with proposal kind `healing_revival_placement`. Its request binds the serialized `HealingEffect`, step, destroyed model ID, authoritative component-unit ID, and any preceding model-selection request/result IDs. The submission contains exactly one attempted `UnitPlacement` for that component and model. Before queue pop and mutation, the engine rejects stale or malformed context, wrong actor, army, player, rules-unit component, model, placement kind, or proposal kind; model overlap; returned-model overlap; impassable or occupied terrain; a returned base crossing the battlefield boundary; broken attached-rules-unit coherency; failure to cohere with phase-start models; or newly entering an enemy model's Engagement Range. Accepted placement restores the source-backed wound amount and records return-to-battlefield transition evidence. Adapters must not infer a default pose, component ownership, or placement legality locally.

Healing and revival placement decisions expose public battlefield state in the current rules scope, so their request and result payloads do not require viewer-dependent redaction. Any future hidden healing source must define and test viewer-scoped request, record, event, and status projection before it is registered.

Source-backed healing effects may carry engine-authored `source_context` flags
that restrict resolution to wounded models or destroyed removed models, lock a
multi-wound heal to the first selected wounded model, or return a revived model
at full Starting Wounds. A source may also bind the exact
`eligible_revival_model_ids` snapshot when its eligibility excludes some
destroyed models, or set `allow_revival_finish` when its wording permits up to
the rolled maximum. Those flags and IDs are validated as part of the serialized
`HealingEffect`; adapters answer emitted `select_healing_model` and
`submit_healing_revival_placement` requests and must not apply the wound or
revival result locally.

The July 22, 2026 Chaos Daemons `Daemonic Manifestation` candidate provider
uses this existing healing contract for its successful Battleline branch. The
engine rolls D3, excludes destroyed CHARACTER component models, binds the
remaining destroyed-model IDs, optional-finish permission, and the owning
player in `source_context`, and then emits the ordinary model-selection and
placement requests until the player finishes or D3 models have been returned.
The candidate remains opt-in until the July source
promotion; the default June provider continues to emit its typed unsupported
diagnostic. No July-specific adapter option, proposal kind, or mutation path is
introduced.

Phase 14I defines the finite `select_weapon_ability_instance` request shape and helper for duplicate source-backed weapon ability instances when the PDF timing gives the controlling player a choice. Phase 13B Shooting declaration target candidates embed this request under `required_weapon_ability_selections` for duplicate matching `[ANTI]` descriptors, and adapters must copy the selected option ID into the matching `WeaponDeclarationPayload.selected_weapon_ability_ids` entry before submitting the declaration. Structured Anti descriptors use canonical slash-separated keyword groups in the `keyword` parameter, such as `vehicle/monster`, and may use `match_mode: "missing_keyword"` for `[ANTI-NON-X]` semantics. Other attack/targeting hosts that can encounter duplicate instances must call the helper and route the selected descriptor ID before resolving that duplicate ability. The request payload includes `submission_kind: "select_weapon_ability_instance"`, `weapon_profile_id`, `ability_kind`, canonical `target_keywords`, and replay-safe `source_context`. Option IDs are the selected structured ability descriptor IDs; option payloads repeat the submission kind, weapon profile ID, ability kind, selected ability ID, and the full ability descriptor payload. Adapters must select one emitted option ID and must not synthesize ability IDs from text. If no duplicate choice exists for the current target and timing, no request is emitted. Runtime helpers reject duplicate ability use without an explicit selected ability ID.

`WEAPON_ABILITY_SELECTION_DECISION_TYPE` is intentionally not a top-level `GameLifecycle.submit_decision(...)` dispatch entry today; it is the single documented nested-decision allowlist entry for duplicate weapon-ability descriptor disambiguation in Shooting declarations, where adapters resolve `select_weapon_ability_instance` by copying the selected descriptor ID from `required_weapon_ability_selections` into the later declaration proposal. Tesseract Vault C'tan Power weapon selection is expressed inside the existing `submit_shooting_declaration` proposal: the request exposes `shooting_weapon_selection_limits` derived from `DamagedEffectKind.SHOOTING_WEAPON_SELECTION_LIMIT`, and the engine revalidates the submitted declarations against those limits before queue pop.

CP totals, CP ledger transactions, and normal Stratagem-use events are public in matched play. Viewer-scoped projections expose public CP ledger data under `public_command_point_ledgers` and public Stratagem-use records under `public_stratagem_use_records`. Adapter event deltas may expose normal CP and Stratagem events to every player unless a future source-backed hidden rule explicitly marks a pending decision, record, or event hidden. Any hidden Stratagem rule must update this document before implementation and must not leak hidden information through option counts, payload fields, event metadata, or derived projection data.

The engine-owned CP ledger enforces `gw-11e-core-rules:command-points:non-core-round-cap`: excluding the Core CP awarded to both players in each Command phase Gain CP stage, each player can gain at most 1 CP per battle round. Ability gains, Stratagem refunds, and the CP awarded for discarding active Tactical Secondary Mission cards all consume the same per-player round allowance. If a single non-Core gain exceeds the remaining allowance, the ledger applies only the remaining amount and records `status: "capped"`, the original `requested_amount`, the actual `applied_amount`, and `capped_reason: "non_command_cp_gain_cap_reached"`. A zero-applied capped result has no transaction; a partially applied capped result has a transaction for only the applied amount. The public transaction field `cap_exempt` is engine-authored: it is true for Core CP and for source-backed rules that explicitly state they are exceptions to the round cap. Adapters must not infer, add, or override an exemption.

Required Phase 12 adapter-contract tests:

- finite `use_stratagem` option enumeration and `FiniteOptionSubmission` round-trip;
- stale/drift/malformed/schema-invalid/wrong-context parameterized Stratagem proposal rejection;
- insufficient CP typed invalid result with no ledger underflow;
- optional additional CP sections rejected before CP spend when the selected section is unaffordable;
- same-Stratagem-twice-per-phase rejection separate from own Stratagem restrictions;
- different-Stratagem same-target and attached-unit same-phase rejection through canonical `targeted_unit_instance_ids`, scoped to the player and active-player phase instance;
- Movement selected-to-move finite Stratagem windows before movement-action
  selection, including decline and engine-owned temporary movement keyword
  effects;
- reactive non-active-player Stratagem use;
- optional finite and parameterized Stratagem window decline through `GameLifecycle.submit_decision(...)`, including reaction-frame resume and no CP/state mutation;
- replay/payload round-trip with deterministic JSON-safe records;
- Phase 12C supported Core Stratagem handler coverage for Command Re-roll, Insane Bravery, Rapid Ingress, and New Orders;
- Phase 15E supported Core Stratagem handler coverage for Heroic Intervention, Counteroffensive, Crushing Impact, and Epic Challenge;
- Phase 12C Rapid Ingress reaction-window target and placement proposals replay/restore without resuming the parent before valid placement;
- viewer-scoped projection/event coverage for public CP and Stratagem events, plus redaction tests for any hidden Stratagem policy.

## Phase 13 Shooting Decisions

Phase 13A terrain visibility, line of sight, and cover foundation does not create player-facing choices. Its `LineOfSightWitness` and `BenefitOfCoverResult` payloads are engine-owned evidence consumed by later shooting decisions and events. `BenefitOfCoverResult` records deterministic feature sources through `source_feature_ids` and feature `source_records`, and terrain-area sources through `source_terrain_area_ids` and typed area records containing the terrain-area ID, classification, LoS policy, and cover-source reason. The current 11th Edition producer uses `not_fully_visible_because_of_feature` for feature evidence and `within_terrain_area` or `not_fully_visible_because_of_terrain_area` for area evidence; `wholly_within_feature` remains deserializable for historical evidence but does not independently grant 11th Edition cover.

The engine converts source `PlacedTerrainArea` values into geometry-owned `TerrainVisibilityArea` descriptors. Dense, Light, and Mixed terrain areas use `LineOfSightPolicy.AREA_OBSCURING`; Dense and Mixed areas are Solid, while Light areas are not. Hidden eligibility is engine-derived per model from that model's component-unit keywords and Light, Dense, or Mixed terrain-area occupancy, together with authoritative unit-scoped current/previous-turn ranged-attack history. An Unknown classification does not establish the Light/Dense feature required by Hidden. During the first turn, the previous-turn no-ranged-attacks condition is true. Detection-range filtering is likewise model-scoped. Benefit of Cover is granted only when every alive model in the target rules unit independently qualifies: an `INFANTRY`/`BEASTS`/`SWARM` model is within any terrain area regardless of classification, or that model is not fully visible because of intervening terrain. A within-area Cover record for an Unknown area carries `WITHIN_TERRAIN_AREA` evidence without claiming that the area is Obscuring or Hidden-qualifying. Adapters must consume line-of-sight witnesses and target candidates rather than locally interpreting terrain-area polygons, classifications, openings, cover, Hidden status, or Solid detection penalties. Phase 13C attack allocation therefore evaluates cover against the entire alive target rules unit even though damage remains allocated to one model.

Phase 13B and later shooting slices add player-facing attacker and defender choices. They must not introduce UI, headless, replay, or network-specific mutation paths. Every accepted choice must pass through the same lifecycle submission path and produce deterministic replay-facing records.

Attacker shooting decisions include:

- finite `select_shooting_unit` choices for the active player when more than one unit can be selected or skipped;
- finite `select_shooting_unit_grant` choices after a unit is selected to shoot when source-backed selected-to-shoot grants are currently legal;
- finite `select_shooting_type` choices for the selected unit before any in-phase shooting declaration is submitted;
- finite or parameterized target and weapon declaration choices, depending on whether the full action space can be safely enumerated;
- Firing Deck selections that bind each selected embarked model to at most one legal non-One-Shot ranged weapon, temporarily grant those attacks to the Transport, and mark the selected embarked units ineligible to shoot for the phase.

Phase 13B implements attacker selection and declaration with these adapter-visible decisions:

- `select_shooting_unit`: finite active-player choice. Option IDs are either the selected rules-unit `unit_instance_id` or `complete_shooting_phase`; for an active attached formation, the engine emits the attached rules-unit ID once and does not expose Bodyguard, Leader, or Support component IDs as separate shooting units. Unit option payloads include the selected `unit_instance_id`. The completion option uses `submission_kind: "complete_shooting_phase"` and includes deterministic `skipped_unit_ids` for all currently legal active-player units that completion will skip.
- `select_shooting_unit_grant`: finite active-player choice emitted after `select_shooting_unit` and before `select_shooting_type` when runtime content exposes legal selected-to-shoot grants. Option IDs are deterministic source hook IDs, plus `decline_shooting_unit_grant`. Accepted options may record engine-owned source spend and unit effects; adapters must not spend resources, invent grant IDs, or mutate reroll permissions locally. Out-of-phase shooting declarations such as Fire Overwatch use the same grant surface before their constrained `submit_shooting_declaration` proposal. Drukhari `Power from Pain: Hatred Eternal` uses this surface to spend one Pain token and record a Shooting-phase hit-reroll empowerment before the unit declares its ranged attacks; Chaos Space Marines `Dark Pacts` and Chaos Daemons Shadow Legion `Disciples of Be'lakor` use it to record Lethal Hits or Sustained Hits 1 for the selected shooting unit.
- `select_shooting_type`: finite active-player choice emitted after `select_shooting_unit` and any selected-to-shoot grant window, before in-phase `submit_shooting_declaration`. Option IDs are engine-enumerated shooting type IDs such as `normal`, `assault`, `close_quarters`, or `indirect`. The request payload includes `game_id`, `battle_round`, `phase`, `active_player_id`, `unit_instance_id`, source unit-selection request/result IDs, and `legal_shooting_types`. Option payloads include `submission_kind: "select_shooting_type"`, the same source context, and the selected `shooting_type`. Stale, drifted, wrong-actor, or wrong-option submissions reject before queue pop and before mutation.
- `submit_shooting_declaration`: parameterized active-player choice. The request contains one `submit_parameterized_payload` option and `payload.proposal_request` with `proposal_kind: "shooting_declaration"`. Its weapon-allocation interaction metadata identifies `attacking_model`, `weapon_instance`, and `target_unit` entity kinds. In-phase requests include `payload.proposal_request.selected_shooting_type`; target candidate `shooting_types` are constrained to that selected type. Out-of-phase Fire Overwatch bypasses the in-phase type decision and emits a constrained `submit_shooting_declaration` request with source-forced `snap` shooting.
- `submit_shooting_declaration.payload.proposal_request.available_weapons`: current JSON-safe physical weapon-copy options, including the deterministic `weapon_instance_id`, model ID, wargear ID, full weapon-profile payload, and optional Firing Deck source unit/model IDs. Each equipped copy has a distinct ID even when every catalog field is otherwise identical. A Firing Deck row identifies the embarked source model's physical weapon copy rather than creating a transport-owned copy. `[ONE SHOT]` weapons already selected earlier in the battle are omitted from this list, and stale proposals attempting to redeclare them reject before queue pop.
- `submit_shooting_declaration.payload.proposal_request.shooting_weapon_selection_limits`: current JSON-safe per-model caps for source-backed weapon groups represented by canonical weapon keywords. Each entry includes `unit_instance_id`, `model_instance_id`, `weapon_keyword`, `max_selections`, `baseline_max_selections`, `damaged_effect_id`, `source_id`, `damaged_profile_active`, and the affected `weapon_profile_ids`. Tesseract Vault `C'tan Power` profiles are capped at the baseline limit when not damaged and at the DAMAGED limit when its active wounds profile applies. Adapters must not infer additional C'tan Power declarations beyond the emitted cap.
- `submit_shooting_declaration.payload.proposal_request.firing_deck_value`: the selected Transport's descriptor-sourced Firing Deck value, or `null` when the unit has no Firing Deck descriptor.
- `submit_shooting_declaration.payload.proposal_request.target_candidates`: current JSON-safe per-copy target candidates carrying the selected `weapon_instance_id`, legality, violation diagnostics, visible-and-in-range target model IDs, line-of-sight witness, visibility cache key, engine-enumerated `shooting_types`, hit modifier, targeting rule IDs, and `required_weapon_ability_selections` for adapter-visible duplicate `[ANTI]` descriptor choices when a selected weapon profile has more than one matching Anti descriptor for that target. Ordinary ranged targets require at least one placed living target model; a candidate without one uses violation code `target_has_no_placed_living_models` and empty visible/in-range model inventories, and a Fight On Death-only unit is omitted from declaration options. Shooter lock and target Engagement contexts use the shared symmetric physical Engagement query, so a retained-only enemy can lock a living shooter and a retained base can establish the Engagement context of an otherwise living mixed target. Neither case grants target authority: a mixed target remains legal only when otherwise eligible, and visible/in-range model IDs contain living models only. Slash-separated Anti keyword groups match if the target has any listed keyword, while `match_mode: "missing_keyword"` descriptors match only when the target has none of the listed keywords. `[HUNTER X]` is represented as target eligibility: candidates for non-matching targets use violation code `hunter_target_keyword_mismatch`, and legal matching candidates carry `weapon-ability:hunter` in `targeting_rule_ids`.

Phase 13B shooting declaration submissions must use `selected_option_id: "submit_parameterized_payload"` and a `ShootingDeclarationProposal` payload containing:

- `proposal_request_id`, `proposal_kind: "shooting_declaration"`, player ID, battle round, acting unit ID, source request/result IDs, and visibility cache key;
- one or more `WeaponDeclaration` entries with attacker model ID, the exact engine-emitted `weapon_instance_id`, wargear ID, weapon profile ID, target unit ID, engine-enumerated `shooting_type`, selected duplicate weapon ability descriptor IDs in `selected_weapon_ability_ids`, and optional Firing Deck source unit/model IDs. Distinct physical copies may select the same or different otherwise-legal targets. The same physical-copy/profile/Firing-Deck-source declaration key may appear only once. Catalog-defined independently selectable multi-profile groups such as Tesseract Vault C'tan Powers may expose distinct legal profiles that share one `weapon_instance_id`; those distinct rows remain independently declarable subject to `shooting_weapon_selection_limits`;
- optional `FiringDeckSelection` evidence with the Transport ID, descriptor-sourced Firing Deck value, and selected embarked unit/model/`weapon_instance_id`/wargear/profile bindings plus already-shot embarked unit IDs. At most the descriptor value's number of distinct embarked models may be selected, and each selected embarked model may contribute at most one non-One-Shot ranged weapon.

Accepted Phase 13B/14F declarations emit one deterministic attack-pool payload per declared physical weapon copy/profile row, preserving `weapon_instance_id`, the selected `shooting_type`, and selected duplicate weapon ability IDs. The accepted proposal, `DecisionRecord`, `shooting_declaration_accepted` event, attack-pool state, persistence payload, and replay round-trip retain that same copy identity. Accepted events also include any `one_shot_weapon_use_records` created for selected `[ONE SHOT]` ranged weapons plus a `ranged_attack_history_record` for the shooting rules unit. Legal shooting types are engine-enumerated values: `normal`, `assault`, `close_quarters`, `indirect`, or source-provided values such as `snap`. Adapters must submit the pending `select_shooting_type` option before an in-phase declaration, then select one of the declaration request target candidate's current `shooting_types`; they must not invent weapon instance IDs or reuse an exact engine-emitted physical-copy/profile/Firing-Deck-source declaration key, invent a shooting type, infer one from weapon keywords, synthesize duplicate weapon ability IDs, locally clear one-shot usage, or locally maintain ranged-attack history. Phase 13C/14E then consumes the declared `RangedAttackPool` records through the grouped Shooting phase lifecycle and may emit attacker target/group selection, attacker Precision, defender allocation-order, save, Feel No Pain, or destruction-reaction decisions before returning to the next shooting-unit selection. Rejected stale, malformed, drifted, `duplicate_weapon_declaration`, invalid-shooting-type, invalid-target, invalid-weapon, invalid-profile, invalid-visibility, invalid-duplicate-weapon-ability-selection, invalid-Firing-Deck, or used `[ONE SHOT]` submissions return typed invalid diagnostics before the pending request is popped and before a `DecisionRecord` is created.

Phase 14L implements the ranged-only rulebook Resolve Attacks layer before the
existing hit/wound/allocation/save/damage resolver. It adds these
attacker-visible attack-resolution decisions:

- `select_resolve_target_unit`: finite attacking-player choice emitted when a
  shooting unit has unresolved declared attack pools targeting two or more enemy
  units. Option IDs use `resolve-target:<target_unit_instance_id>`. The selected
  option payload includes `submission_kind: "select_resolve_target_unit"`,
  `target_unit_instance_id`, and the current `sequence_id`. If exactly one
  target unit remains, the engine records an automatic finite choice with the
  same request/result contract instead of emitting a pending request.
- `select_attack_weapon_group`: finite attacking-player choice emitted after a
  target unit is selected when that target has two or more unresolved
  identical-attack groups. Option IDs use deterministic `attack-group:<hash>`
  values derived from the selected target, the full resolver-safe
  identical-attack signature, and contributing pool indices. The selected option
  payload includes
  `submission_kind: "select_attack_weapon_group"`, `target_unit_instance_id`,
  `sequence_id`, and a JSON-safe `gathered_group` payload with the
  identical-attack signature, contributing pool indices, per-pool attack counts,
  and total gathered attacks. Multi-contribution groups resolve through a
  deterministic gathered weapon-pool identity, while each contribution preserves
  its original wargear and weapon-profile IDs in the gathered payload. The
  signature includes every provenance field the current synthetic-pool resolver
  copies for downstream Precision visibility, cover/LOS, and Firing Deck/source
  attribution, including attacker model ID, visible and in-range target model
  IDs, targeting rule IDs, shooting type, and optional Firing Deck source
  unit/model IDs. Wargear/profile IDs are intentionally omitted from the
  signature so weapons with identical resolution characteristics and structured
  rule tokens can gather into the same deterministic weapon pool. Attack-step
  event payloads include `weapon_profile_id`; this is the original profile ID
  for single-pool groups and a deterministic `gathered-profile:<attack-group>`
  ID for multi-contribution gathered groups. If exactly one group remains for the
  selected target, the engine records an automatic finite choice instead of
  emitting a pending request.
- `select_post_roll_attack_pool`: finite active-player choice emitted after
  actual Hit and Wound rolls, when source-backed post-roll profile modifiers
  split the successful attacks in the current gathered group into two or more
  resulting weapon profiles. The request payload includes
  `submission_kind: "select_post_roll_attack_pool"`, game/round/phase context,
  `sequence_id`, `active_player_id`, `attacker_player_id`, the source rule ID,
  and the unresolved `pool_ids`. Each deterministic pool option repeats the submission kind,
  sequence and pool IDs, full resulting weapon-profile payload, member
  `attack_context_ids`, and source rule ID. The selected pool remains persisted
  on `AttackSequence` while allocation, saves, and damage resolve for only those
  attacks; the active player is asked again when multiple resulting profiles
  remain. A single remaining profile is recorded as an automatic finite choice.
  Shooting and Fight use the same decision type and lifecycle dispatcher.

Adapters must answer these decisions by selecting one pending option ID through
`GameLifecycle.submit_decision(...)`; they must not invent target IDs, group IDs,
signature hashes, pool indices, post-roll profile payloads, attack-context
membership, or mutate from option payloads. The lifecycle
validates malformed, stale, drifted, wrong-target, wrong-group, wrong-option, and
payload-mismatched submissions before queue pop. Invalid submissions return
typed invalid diagnostics, preserve the pending request, create no
`DecisionRecord`, and do not mutate authoritative state. Accepted grouped
attacks feed the same Phase 13C/14E attack sequence resolver documented below;
Phase 14L does not add a second allocation, save, damage, mortal-wound,
Hazardous, Feel No Pain, or destruction-reaction path.

Ranged shooting declarations, selected target units, and gathered weapon groups
for the active shooting unit are public table information in the current rules
scope. Viewer-scoped projections and event deltas still must not leak hidden
opponent information through option counts, payload metadata, invalid diagnostics,
or derived fields. Melee attack splitting and melee identical-attack gathering
remain Phase 15 Fight-phase work and are not represented by these ranged
decision types.

Defender shooting decisions include:

- finite `select_allocation_order` choices when more than one legal allocation
  group order exists for the current grouped save/damage window;
- finite optional or competing defensive ability choices, including any optional Feel No Pain source/use choice;
- finite optional destruction-reaction choices when a destroyed model has registered optional shoot-on-death, fight-on-death, or equivalent destruction sources;
- mandatory destruction reactions such as Deadly Demise are engine-triggered resolutions, not decline-capable adapter choices;
- shooting-coupled reactive Stratagem choices such as Smokescreen through the existing `use_stratagem` or Stratagem target-proposal contract.

For a model destroyed by an attack, registered mandatory or optional destruction reactions use the
shared `05.04.04 Destroyed` end-of-attacks boundary. The engine records logical death immediately,
retains the model's fixed battlefield placement while excluding it from living-model selection and
targeting, finishes every attack from the attacking rules unit, and emits
`attack_sequence_attacks_resolved`. It then resolves mandatory reactions, removes the model and
emits `model_destroyed`, and only then emits any optional `select_destruction_reaction` request.
`AttackSequence` persists the ordered pending-destruction records, original damage event IDs,
pre-removal placements, captured reaction sources, and the attacks-resolved event ID. Restore
validation binds that state to the original damage, deferral, boundary, removal, and pending
decision records. Shooting and Fight use this same sequence owner. Adapters must not remove the
retained model, expose it as alive or targetable, advance a reaction before the boundary, reorder
queued destructions, or synthesize boundary evidence. Fight On Death's later remove/re-add behavior
remains owned by P05B and is not changed by this boundary.

Saving throw kind is not an adapter choice in the 11th Edition contract. The
engine rolls one saving throw die for the current allocation group, retains both
armour and Invulnerable Save options when both exist, and checks that die in
ordered rule order: an unmodified 1 fails; otherwise an InSv succeeds if the die
is at least the InSv characteristic; otherwise the armour Save succeeds if the
AP-modified result is at least the Sv characteristic; otherwise the save fails.
Adapters must not offer, submit, apply, or replay an armour-versus-invulnerable
choice.

Phase 13C implements these defender-visible attack-resolution decisions:

- `select_allocation_order`: finite defending-player choice. Option IDs are
  deterministic order IDs such as `allocation-order-001`; adapters must not
  invent group-order payloads. The selected option payload includes
  `submission_kind: "select_allocation_order"`, `ordered_group_ids`, and
  `ordered_groups`. The request payload includes `selection_kind:
  "allocation_group_order"`, `attack_context` for the allocation-order window,
  optional `attack_contexts` for grouped wound pools already rolled before the
  decision, `allocation_context`, `allocation_groups`, and
  `priority_group_ids`. Each group payload includes `group_id`, `model_ids`,
  `role`, W/Sv/InSv profile, wounded and already-allocated model IDs,
  Bodyguard/Character evidence, role evidence, and legality reasons. The engine
  creates allocation groups automatically: one per eligible Character model and
  one per non-Character W/Sv/InSv profile. It emits this finite decision only
  when more than one legal group order exists inside the same allocation tier;
  forced tier order is automatic. Wounded non-Character groups precede
  unwounded non-Character groups, non-Character groups precede Character
  groups, and wounded Character groups precede unwounded Character groups.
  `priority_group_ids` is normally empty; Precision may populate it with the
  attacker-selected visible Character group, which is promoted to the front of
  the legal order for the current attack pool. Phase 14H resolves every
  successful wound in the pool through this grouped path, including pool-of-one
  attacks, random Damage rolls, Feel No Pain interruptions, Deadly Demise, and
  Devastating Wounds. The engine rolls all non-Devastating saving throw dice for
  the grouped pool before applying normal damage, sorts those dice from lowest
  to highest, then walks them against the current ordered group. Real armour or
  invulnerable saving throw options are retained even when the target is above 6
  or AP makes success impossible on a D6. Effects that permit no saving throw
  may roll an internal `attack_sequence.allocation_order.no_save` die for
  deterministic ordering; that die is not a saving throw and is not Command
  Re-roll eligible. The save event for each die is emitted when that die is
  walked, so the payload reflects the model, all current save options, and the
  ordered save condition that resolved the die through `resolution_rule`. When
  a group is destroyed or exhausted, remaining failed saves advance to the next group in
  `ordered_group_ids`. Stale, drifted, wrong-actor, wrong-option, or
  payload-mismatched submissions reject before queue pop and before mutation.
- `select_damage_allocation_model`: finite defending-player choice emitted
  during Inflict Damage when the current ordered allocation group contains more
  than one currently legal model for the sorted save die being walked. Option
  IDs are current legal model IDs; adapters must select one pending option ID
  and must not invent model IDs. The selected option payload includes
  `submission_kind: "select_damage_allocation_model"` and
  `selected_model_id`. The request payload includes `selection_kind:
  "damage_allocation_model"`, the save die's `attack_context`, the current
  `allocation_context`, the current `allocation_group`, `legal_model_ids`, and
  the replay-safe `save_die`. Legal model IDs are evaluated from current state:
  if any alive model in the current group has lost one or more wounds, only
  those wounded model IDs are legal; otherwise all alive model IDs in the
  current group are legal. The engine auto-resolves this step only when exactly
  one legal model remains. Stale, drifted, wrong-actor, wrong-option,
  payload-mismatched, exhausted-pending-damage, or no-pending-grouped-damage
  submissions reject before queue pop and before mutation. Accepted selections
  resume the same grouped save/damage resolver, and the save and damage events
  for that die carry the selected model ID.
- `select_mortal_wound_model`: finite controlling-player choice emitted before
  each mortal wound is resolved when more than one living model shares the
  first applicable 06.02 priority tier. Option IDs are the sorted current legal
  model IDs. The request payload includes `selection_kind:
  "mortal_wound_model"`, `target_unit_instance_id`, `source_rule_id`,
  replay-safe `source_context`, `remaining_mortal_wounds`,
  `legal_model_ids`, `priority_tier`, and the complete
  `mortal_wound_progress`. That private progress includes a `target_lineage`
  object with policy `frozen_rules_unit_components`, the canonical packet
  target and owner, exact component-unit IDs, and the components classified as
  Character when the packet began. That Character-component set is not
  self-authenticating: restore and pre-submission validation reconstruct it
  from current attached Leader/Support roles plus authoritative Character
  keywords, or, after dissolution, from the exact matching
  `StartingAttachedUnitRecord` Leader/Support roles plus those keywords. Any
  persisted classification drift rejects before queue pop or mutation. Each
  option repeats its `selected_model_id` and `priority_tier`. The four tier
  tokens are `wounded_non_character`,
  `non_character`, `wounded_character`, and `character`, in that exact order.
  The engine auto-selects only when the active tier contains exactly one legal
  model. Accepted submissions resolve exactly one mortal wound on the selected
  model, then recompute the priority tiers before the next mortal wound; any
  resulting Feel No Pain choice remains a separate `select_feel_no_pain`
  request. Stale, drifted, malformed, wrong-actor, wrong-option,
  payload-mismatched, dead-model, or priority-tier-drift submissions return
  `invalid_mortal_wound_model_result` before queue pop or authoritative
  mutation. Shooting, Fight, Hazardous, Explosives, Deadly Demise, movement,
  Transport, and registered runtime-content continuations all resume through
  the same producer-owned mortal-wound path. Public projections expose the
  request to both viewers with `entity_selection` interaction metadata and
  `model` as the primary assignment; adapters must submit one pending option ID
  and must never select a model or apply a wound locally.
- `select_feel_no_pain`: reserved finite defending-player choice for optional or competing Feel No Pain sources. Option IDs are source IDs, plus `decline` when the rules allow declining. `payload.lost_wound_context` and `payload.sources` are replay-safe and must be submitted through the same finite decision path. Normal lost wounds use `lost_wound_context.context_kind: "lost_wound"`; deferred mortal wounds, Explosives mortal wounds, Hazardous mortal wounds, and other routed mortal-wound packets use `lost_wound_context.context_kind: "mortal_wound"` and keep the pending mortal-wound application state in that replay-safe context until the choice resolves. Sources may carry `attack_condition: "psychic_attack"`; those sources are eligible only for lost wounds whose attack context has `is_psychic_attack: true`. Sources may also carry `mortal_wounds: true`; those sources are eligible for ordinary mortal-wound routing with no attack context.

Phase 13E implements this destroyed-model attack-resolution decision:

- `select_destruction_reaction`: finite controlling-player choice emitted after attack-sequence damage destroys a model with one or more optional structured destruction-reaction sources. Option IDs are optional source IDs plus `decline_destruction_reaction`. Source options carry `payload.source_id`, `payload.reaction_kind`, and `payload.optional: true`, where supported optional `reaction_kind` values include `shoot_on_death` and `fight_on_death`; the decline option uses null source and kind values. `payload.destruction_context` contains the JSON-safe attack context, damage application, `model_destroyed` event ID, damage event ID, removal record, transition batch, `destroyed_model_controller_player_id`, a typed `destruction_provenance`, and a nullable engine continuation payload. The provenance records `destruction_source_kind` (`attack`, `deadly_demise`, `hazardous`, or `ability`), `attack_kind` (`melee`, `ranged`, or `none`), and, only for attack destructions, the full typed source weapon profile and attack-context ID. Attack kind is derived from that typed weapon profile rather than inferred from the current phase, and replay validation rejects attack-kind, weapon-profile, or attack-context drift. Adapters must submit one pending option ID through `GameLifecycle.submit_decision(...)` and must not start shooting, fighting, explosion, continuation, or removal mutations locally from the option payload. Accepted selections are recorded as destruction-reaction resolutions for the appropriate engine action host. Source rule `gw-11e-rules-and-event-updates-2026-07-22:app-core-rules:05.04.05-fight-on-death` makes an accepted `fight_on_death` source retain the destroyed model at its recorded placement, emit `fight_on_death_model_awaiting_attack`, and let that model contribute its attacks when its rules unit takes the applicable single ordinary attack selection. The fixed retained placement remains available for source-required physical measurement and deterministic replay, but is not general living-model authority: the retained model cannot use ordinary abilities, move, Pile In, Consolidate, or become ranged or melee target geometry. A target rules unit requires at least one placed living model; a mixed unit remains targetable, but target geometry and damage allocation use only its living models. Ranged rejection uses `target_has_no_placed_living_models`. The source rule's separate narrow exception remains explicit: a Stratagem that targets the retained model's unit also affects that destroyed model. Restore rejects a retained pose that differs from the authoritative destruction event. The cleanup emits `fight_on_death_models_removed` with `reason: "unit_fight_completed"` or `reason: "phase_end"`; adapters must not remove it locally. The model's zero-wound state means it does not contribute keywords while waiting. Mandatory sources such as `deadly_demise` resolve automatically before destroyed-model removal, including trigger rolls, eligible nearby-unit mortal-wound packets, any secondary-casualty removal/reaction host, and any routed `select_feel_no_pain` choices; they must not be presented as destruction-reaction options.

P00 preserves that adapter behavior and stable source ID but does not certify it
as complete rule execution. Its repository transcription remains unverified on
its own, but a separate matching observation at
`https://www.40k.app/rules/05-attack-sequence` is governed by source policy
`core-rules-source-policy:40k-app-verbatim-official-app-mirror:2026-08-26`.
Under that owner-approved policy, 40k.app is the project-authoritative verbatim
mirror of the maintained App for Core Rules, while remaining a non-affiliated
host. The current engine path is partial because of the recorded attack-sequence
timing/removal gap, not because the mirror is secondary evidence. A later
behavioral PR must close that gap against the authoritative App-mirror wording;
routine official-App capture is unnecessary. A source-policy disambiguation
exception instead requires an owner check and prefers a retained capture when
mirror equivalence is itself disputed. Adapters must not infer or patch that gap
locally, and neither adapters nor the engine may query the live website or treat
it as runtime input.

The authoritative log marks logical death before any resulting destruction
reaction or physical-removal event. `model_logical_death_recorded` is a private
engine boundary, not a player-visible timing window: it makes historical
liveness reconstructible at the exact wounds-to-zero transition and binds the
later cause authority to that transition. `model_destroyed` remains the
physical removal/completion record. A retained Fight On Death placement can
therefore remain valid geometry after logical death without making the model
living, movable, or targetable. For multi-model mortal-wound routing, an
already-recorded boundary remains in the typed pending progress if a subsequent
wound pauses for Feel No Pain; recovery requires that pending request to claim
the canonical earlier boundary exactly once.

Rule-driven destruction reuses the same finite reaction and mortal-wound decision shapes. Its replay-safe context carries the source rule/effect/result IDs, physical and canonical rules-unit identities, removal artifacts, and the engine-owned completion payload. Mandatory Deadly Demise resolves while the zero-wound source model remains placed and may pause on the standard `select_feel_no_pain` path; the originating liability remains unconsumed until that continuation completes. Fight on Death never installs a separate Fight activation. An accepted model remains present until its rules unit completes its one ordinary attack selection, or until phase-end cleanup if that unit has already fought or is never selected. The retained model attacks together with every other eligible model in that rules unit. Once cleanup finishes, one shared completion transition removes the model, consumes the originating liability, interrupts Mission Actions only when the canonical rules unit is actually destroyed, validates retained Attached Unit identity and explicit component lineage, and emits the source completion event. Adapters must not perform any of those mutations locally.

Deadly Demise target snapshots enumerate canonical rules units, so an Attached Unit appears once even when multiple physical components are in range. If a mortal-wound packet destroys one or more secondary models, the destruction context may carry a nested, JSON-safe engine continuation. That continuation serializes the remaining collateral casualties, target rules units, mandatory Deadly Demise sources, and original source-model completion; each casualty routes through the shared mandatory and optional destruction-reaction machinery before the next item resumes. Adapters submit only the pending standard `select_feel_no_pain` or `select_destruction_reaction` option and must treat the nested continuation as opaque engine state.

Phase 13D adds these attacker-visible attack-resolution decisions:

- `select_precision_allocation`: finite attacking-player choice at the start of the Allocation Order step while resolving attacks made with one or more `[PRECISION]` weapons against a unit containing visible eligible Character allocation groups. Option IDs are visible eligible Character `group_id` values plus `decline_precision`; Character options include `payload.selected_group_id` and `payload.selected_model_ids`, and the decline option uses `selected_group_id: null` with an empty model list. Grouped-host requests include the wounded pool's `attack_contexts` in the request payload. Accepted Character-group selection is pool-scoped until those attacks resolve or that Character group is destroyed, whichever happens first. In the grouped host, the selected Character group is carried as allocation-order `priority_group_ids` and promoted ahead of ordinary defender group order; remaining failed saves return to normal ordered groups after that Character group is destroyed. Declining, having no visible Character group, having no Precision source, or destruction of the selected Character group follows the normal defender allocation path.
- `select_psychic_attack_modifier_ignores`: finite attacking-player choice emitted before the Hit roll for a `[PSYCHIC]` weapon attack when the current attack context has a non-zero BS/WS modifier or hit-roll modifier. The request payload includes `submission_kind: "select_psychic_attack_modifier_ignores"`, `attack_context_id`, attacking unit/model IDs, target unit ID, `weapon_profile_id`, `source_phase`, `skill_modifier`, and `hit_roll_modifier`. Legal option IDs are engine-enumerated from `keep-all-modifiers`, `ignore-detrimental-modifiers`, `ignore-beneficial-modifiers`, and `ignore-all-modifiers`, excluding duplicate effective outcomes. Each option payload repeats the attack context and weapon profile, carries the original modifiers, and records `effective_skill_modifier`, `effective_hit_roll_modifier`, `ignored_skill_modifier`, and `ignored_hit_roll_modifier`. Adapters must submit one pending option ID through `GameLifecycle.submit_decision(...)`; stale context, wrong weapon, wrong actor, malformed payloads, or option drift reject before queue pop and before the Hit roll is made.

Phase 13C/14H attack-resolution events are typed, ordered, and JSON-safe at hit, Critical Hit, wound, Critical Wound, allocate, save, and damage. Supported grouped-host weapon abilities preserve those event boundaries, including Lethal Hits skipped wound payloads, Sustained Hits generated-hit wound contexts, Precision priority-group allocation, Psychic attack classification via `is_psychic_attack`, and Devastating Wounds deferred mortal-wound packets. Phase 14H has one pooled save/damage resolver: adapters must not expect or submit single-attack allocation decisions during shooting attack resolution. Normal damage is resolved before deferred Devastating Wounds mortal-wound packets for the same attack pool. Internal grouped-damage continuation payloads are replay-safe engine state, not adapter-submitted payloads, and must not leak hidden information through viewer-scoped projections or event deltas.

If a shooting declaration is parameterized, the request must embed a typed proposal request with replay-safe source context:

- game ID, battle round, phase, active player, and acting unit ID;
- source request/result IDs when the declaration follows a finite unit-selection decision;
- selected model IDs, weapon IDs, profile IDs, target unit IDs, and any Firing Deck source model/weapon binding;
- the ruleset descriptor hash and line-of-sight/cache evidence required by target validation;
- visible viewer payloads that do not leak hidden opponent information.

Shooting proposals must reject stale, drifted, malformed, schema-invalid, wrong-actor, wrong-unit, wrong-phase, `duplicate_weapon_declaration`, invalid-shooting-type, invalid-target, invalid-weapon, invalid-profile, invalid-Firing-Deck, or stale-visibility submissions before queue pop unless the exact proposal contract explicitly allows a rule-invalid but well-formed rejected attempt and emits a fresh pending request for retry. Phase 13B/14F does not allow recorded rule-invalid retry attempts for attacker declarations. Accepted submissions validate the engine-emitted physical weapon instance and its profile/source declaration key, previously selected shooting type, target legality, range, visibility, Lone Operative, Locked in Combat, Big Guns Never Tire, Close-quarters/Pistol, Blast engagement bans, Assault/Advanced weapon gating, Indirect per-weapon `[INDIRECT FIRE]` eligibility, Indirect visibility and no-Hit-reroll policy, Firing Deck, one-shot, Hazardous declaration obligations, and ruleset-specific targeting restrictions before mutation.

Hidden target validation is engine-owned. The 11th Edition ruleset descriptor
uses a 15" base Detection Range for Hidden and a 3" Gone to Ground detection
penalty. Shooting target candidates and proposal validation consume
engine-owned Hidden state, persisting Detection Range modifiers such as Path of
the Outcast +6" effects, terrain/line-of-sight evidence, and
`RangedAttackHistoryRecord` data from `GameState`. A Hidden model has Gone to
Ground only when it is within Dense/Solid terrain, is not fully visible
to the attacking model because of one or more intervening Dense/Solid terrain
features, and its rules unit did not make ranged attacks in the current or
previous player turn. Units that made ranged attacks in either turn cannot
benefit even if another rule lets them shoot while remaining Hidden. Adapters
must not locally add, remove, or reinterpret Hidden/detection state, terrain
Solid status, or ranged-attack history.

Detection Range is a visibility gate, not an independent Indirect Fire
targeting prohibition. An eligible `[INDIRECT FIRE]` weapon can therefore
target an in-range Hidden model outside Detection Range through the normal
not-visible Indirect path and restrictions. Lone Operative remains distinct
because its rule separately prohibits Indirect Fire outside its stated range.
The current engine allows Light as well as Dense terrain to grant Hidden. Its
supporting source row (package
`gw-11e-app-core-rules-hidden-transcription-observed-2026-08-09`) is an
uncaptured project-owner transcription attributed to the Warhammer 40,000 App;
that historical record remains unverified on its own. A separate observation at
`https://www.40k.app/rules/13-terrain` matches it. Under source policy
`core-rules-source-policy:40k-app-verbatim-official-app-mirror:2026-08-26`,
40k.app is the project-authoritative verbatim mirror of the maintained App, and
the App wording supersedes the older PDF’s Dense-only wording for this rule.
The evidence continues to identify 40k.app as a non-affiliated provider. P00
corrects provenance and certification without changing gameplay behavior. The
live website is not adapter or engine input; only reviewed, normalized,
hash-pinned source artifacts may cross the runtime data boundary.

Defender allocation/save/defensive/destruction-reaction decisions may auto-resolve only when the rules leave exactly one legal outcome and no optional player choice. Otherwise the defending or destroyed-model controlling player is the `DecisionRequest.actor_id`, even though they may not be the active player. Adapters must not infer that Shooting phase decisions always belong to the active player. Stale, drifted, wrong-actor, wrong-option, or payload-mismatched destruction-reaction submissions return typed invalid diagnostics before queue pop and before a `DecisionRecord` is created.

Shooting decision records, attack-resolution events, line-of-sight witnesses, cover results, allocation records, save records, and damage/removal records must be deterministic and JSON-safe. Physical `weapon_instance_id` values are replay-safe identifiers and must remain stable across request, decision, pool, event, persistence, and replay serialization. Phase 13B normal shooting unit/declaration requests are public because they concern table-visible units, weapons, targets, and Transport Firing Deck use. Viewer-scoped projections and event deltas must not leak hidden information through option counts, target lists, payload metadata, rejected-proposal diagnostics, or derived fields.

Phase 13D supports these shooting-coupled Core Stratagem target proposals:

- `core:smokescreen`: opponent Shooting phase `after_unit_selected_as_target` proposal for a friendly `SMOKE` unit listed in `trigger_payload.selected_target_unit_instance_ids`. Accepted use grants Benefit of Cover and the structured hit-roll modifier effect that expires at the active shooting player's end-of-phase boundary.
- `core:explosives`: active-player Shooting phase proposal for a friendly `GRENADES` unit plus `trigger_payload.enemy_target_unit_instance_id`. Submissions are rejected before queue pop and CP spend if the source unit Advanced, Fell Back, already shot, is within Engagement Range, or if the enemy target is friendly, unknown, engaged with friendly units, not visible, or not within 8". Accepted use records both the friendly `GRENADES` unit and the enemy target in `StratagemUseRecord.affected_unit_instance_ids`, canonicalizing attached-unit components to their attached-unit rules identity, and emits `explosives_resolved` with `explosives_unit_instance_id`, `target_unit_instance_id`, deterministic roll state, mortal-wound count, and any routed mortal-wound application.
- `core:fire-overwatch`: opponent Movement phase `end_phase` proposal emitted from the End of Opponent's Movement phase reaction window for one friendly non-`TITANIC` unit that is unengaged, within 24" of a triggering enemy unit, and would be eligible to shoot if it were that player's Shooting phase. The triggering enemy unit must have been set up or started/ended a Normal Move, Advance, or Fall Back during that Movement phase. The trigger payload identifies that enemy unit with `moved_unit_instance_id`, uses `trigger_window: "end_opponent_movement_phase"`, and includes the eligible trigger classes under `eligible_trigger_kinds`. Target-proposal validation rejects out-of-range friendly units, engaged friendly units, `TITANIC` friendly units, shooting-ineligible friendly units, and friendly units without a legal constrained declaration before CP spend or Stratagem-use recording. Accepted use spends CP, records the Stratagem use, creates an out-of-phase shooting state with the parent phase and trigger payload, and emits a `submit_shooting_declaration` proposal whose legal targets are constrained to the triggering enemy unit. The resulting attack pools carry `core:fire-overwatch`; non-automatic hit rolls default to succeeding only on unmodified 6s regardless of BS or modifiers, while Torrent weapons still auto-hit. Source-backed generic RuleIR can lower that unmodified hit-success threshold through an engine-owned `minimum_unmodified_hit_success` contextual status; emitted hit-roll payloads set `unmodified_success_threshold_active: true` when that threshold itself scores a hit, and adapters must read both that flag and `minimum_unmodified_success` instead of applying local Fire Overwatch exceptions. Declaration and attack-sequence decisions are submitted through `GameLifecycle.submit_decision(...)`, and the Phase 12A reaction frame resumes only after the out-of-phase shooting state completes. Phase 14B emits Fire Overwatch before Rapid Ingress when both are available in the same End of Opponent's Movement phase window.

Fire Overwatch is not emitted from the active player's normal Shooting phase and is not represented by a persisting marker. It uses a dedicated out-of-phase shooting state so adapters see the same declaration, Precision, allocation, save, Feel No Pain, and attack-resolution decisions as normal shooting without mutating the active Shooting phase state.

Required Phase 13 adapter-contract tests:

- valid attacker unit selection through `FiniteOptionSubmission -> DecisionResult -> GameLifecycle.submit_decision(...)`;
- valid shooting-type selection through `FiniteOptionSubmission -> DecisionResult -> GameLifecycle.submit_decision(...)`, including stale/drift/wrong-actor/wrong-option rejection before mutation;
- valid shooting target/weapon declaration through the chosen finite or parameterized submission path;
- valid ranged `select_resolve_target_unit` and `select_attack_weapon_group` choices through `FiniteOptionSubmission -> DecisionResult -> GameLifecycle.submit_decision(...)`, including automatic single-option recording and stale/drift/malformed invalid submission rejection before queue pop;
- stale, drifted, malformed, schema-invalid, wrong-actor, wrong-unit, wrong-phase, invalid-target, invalid-weapon, and invalid-visibility submission rejection without mutation where required;
- Firing Deck declaration validation, replay, and end-of-phase ineligible-unit state;
- defender allocation-order round-trip through finite decisions, automatic forced allocation-tier ordering, same-tier ordered-group options, current-group damage-model choice through finite decisions, wounded-model forced choice inside current groups, pooled save sorting, grouped failed-save transition to the next ordered group, pool-of-one convergence through the grouped resolver, and ordered InSv-then-armour Save resolution with no save-kind adapter choice;
- Precision allocation choice round-trip through finite attacker decisions, including decline, pool-scoped selected Character-group persistence, grouped priority-group promotion, selected-group destruction, and normal Bodyguard-protected fallback;
- optional or competing Feel No Pain decisions through finite decisions;
- Smokescreen, Fire Overwatch, and other shooting-coupled reactive Stratagem windows through `use_stratagem` or target proposals;
- replay/payload round-trip with no Python object reprs or memory addresses;
- viewer-scoped projection/event redaction for any hidden target, allocation, defensive ability, or reaction-window information.

## Phase 15 Charge Decisions

Phase 15A implements Charge phase eligibility, declaration, optional source-backed declaration grants, and deterministic charge-distance rolls. Phase 15B implements the post-roll Charge Move as a parameterized physical proposal. Adapters must not synthesize target selection, placement mutation, displacement records, source-backed declaration effects, or Fights First state from the Phase 15A roll payload; they must answer the pending Phase 15B proposal request.

Phase 15A exposes this active-player decision:

- `select_charging_unit`: finite active-player choice. Option IDs are either the selected `unit_instance_id`, a deterministic `<unit_instance_id>:ignore:<hash>` variant when the unit may ignore one or more currently applicable Charge-roll modifiers, or `complete_charge_phase`. Unit option payloads include `submission_kind: "select_charging_unit"`, game, round, phase, active player, selected unit ID, target candidates, and the current eligibility context. Modifier-ignore variants add the same source-bound `modifier_ignore_context` used by Movement actions, with `kind: "charge_roll"` snapshots and one option for every legal subset; the unsuffixed unit option keeps all modifiers. The completion option uses `submission_kind: "complete_charge_phase"` and includes deterministic `skipped_unit_ids` for all currently legal active-player charging units.
- `select_charge_declaration_grant`: finite active-player choice emitted after `select_charging_unit` and before the Charge roll when runtime content exposes legal declaration grants. Option IDs are deterministic source hook IDs, plus `decline_charge_declaration_grant`. Accepted options may record engine-owned source spend and unit effects; adapters must not spend resources, invent grant IDs, or mutate defensive restrictions locally. Drukhari `Power from Pain: Lithe Agility` uses this surface to spend one Pain token and record Charge-phase empowerment before the Charge roll. Black Templars `Abhor the Witch, Destroy the Witch` uses this surface to accept a source-backed Charge-roll reroll and a mandatory PSYKER target snapshot whose obligation remains active independently of post-roll reachability.

Charge eligibility target candidates are engine-enumerated from battlefield state and the active ruleset's `charge_policy`. Each candidate is a current canonical rules unit with at least one placed living model; an Attached Unit appears once under its synthetic rules-unit ID, and its component IDs are not separate targets. A destroyed unit whose only battlefield presence is a temporarily retained Fight On Death base is not a Charge target. When a mixed unit still has placed living models, its retained destroyed bases remain physical geometry for declaration distance, Charge Move endpoint engagement, and collision validation even though they do not grant target authority. Phase 15A rejects chargers that Advanced, Fell Back, are within Engagement Range, are off the battlefield, already declared a Charge this phase, or have no enemy unit within the descriptor-sourced declaration range, currently 12", unless a future source-backed rule explicitly marks that unit as allowed to declare a charge. An active selected-target Charge constraint is evaluated independently of that candidate list: every current surviving successor of every historical marked rules-unit identity must itself be placed and must be a legal target. If a mark is destroyed, off the battlefield, otherwise unavailable, or has any current surviving successor that is unplaced or not legal, the charging unit cannot declare a Charge while that effect remains active; another legal enemy does not satisfy the obligation.

Selecting a charging unit records the finite `DecisionRecord`, emits `charging_unit_selected`, and either emits a `select_charge_declaration_grant` request or rolls 2D6 through the deterministic dice manager with `roll_type: "charge_roll"`. There is no Phase 15A adapter-authored target declaration payload. The generated charge-roll `DiceRollSpec` includes `reroll_forbidden_rule_ids` with `phase15a:charge-roll-command-reroll-forbidden`, so Phase 15A Charge rolls must not emit a Command Re-roll request even though the source-backed 11th Edition Stratagem catalog contains Charge as an eligible roll class. Source-backed non-Command rerolls, such as Drukhari Lithe Agility after an accepted Power from Pain declaration grant, Black Templars Abhor the Witch after an accepted PSYKER charge grant, or Chaos Terminators' Lethal Obsession, may still emit `select_dice_reroll`; the request payload carries the source permission and the engine ignores only the Command Re-roll forbidden marker for that source-backed reroll. Every source-backed Charge reroll request also carries `charge_context.legal_target_unit_instance_ids` and `charge_context.charge_move_required_target_unit_instance_ids`; selected-target requests additionally carry `charge_context.selected_target_charge_constraint`. The constraint records `reroll_allowed`, every `required_target_unit_instance_id`, all contributing `source_effect_ids`, historical marked identity IDs, unavailable and destroyed identity IDs, and deterministic current/surviving/placed lineage. Repeated compatible marks coalesce into one whole-roll reroll permission. When either snapshot expresses a mandatory target, lifecycle revalidates the constraint, required-target snapshot, and legal-target snapshot before queue pop, so a reactive move, destruction, split, expiry, or other target drift returns typed invalid status without consuming the pending request.

An accepted charging-unit modifier-ignore option first records the same
phase-scoped selection effect and `modifier_ignores_selected` event used by
Movement, then resolves the Charge roll without exactly the selected physical
modifier IDs. Different legal Charge-roll modifiers remain independently
selectable even when they originate from the same rule or have equal operands.
The request, option, `DecisionRecord`, effect, event, Charge-roll request, and
replay payload preserve those identities. Duplicate, malformed, invented, or
stale contexts reject before queue pop, before the charging-unit record, and
before any Charge roll.

The `charge_roll_resolved` payload includes:

- `unit_instance_id`;
- `maximum_distance_inches`;
- `roll_result`, including source unit-selection request/result IDs;
- `reachable_target_distances_inches` and `reachable_target_unit_instance_ids`, containing only canonical enemy rules units with placed living target authority that are currently within both 12" and the rolled maximum distance. A mixed target's physical distance may be established by a retained Fight On Death base; a retained-only destroyed unit is omitted.

If the roll leaves no enemy unit within both 12" and the rolled maximum distance, Phase 15A emits `charge_no_move_possible`, mutates no model placement, emits no displacement payload, and continues to the next charging-unit choice. If one or more reachable targets exist, Phase 15A records a `ChargeDistanceState`, emits `charge_move_required`, and emits a `submit_movement_proposal` request with proposal kind `charge_move`.

The Phase 15B Charge Move request uses the shared parameterized proposal wrapper:

- `decision_type: "submit_movement_proposal"`;
- `proposal_kind: "charge_move"`;
- `phase: "charge"`;
- `movement_phase_action: "charge_move"`;
- `unit_instance_id`: the charging unit;
- request context includes `movement_mode: "charge"`, `maximum_distance_inches`, `reachable_target_unit_instance_ids`, `reachable_target_distances_inches`, optional `charge_move_required_target_unit_instance_ids`, and the source `charge_roll` payload. Selected-target requirements retain their full current identity set independently of reachability; if the roll cannot reach every required current target, Phase 15A emits `charge_no_move_possible` and does not emit this proposal.

Adapters answer with `ParameterizedSubmission` and the fixed `submit_parameterized_payload` option. The payload is a `ChargeMoveProposal` object with:

- `proposal_request_id`;
- `proposal_kind: "charge_move"`;
- `unit_instance_id`;
- `movement_phase_action: "charge_move"`;
- `movement_mode: "charge"`;
- `charge_target_unit_instance_ids`: zero or more target IDs from the request's reachable target list;
- `witness`: a `PathWitness` for every model in the charging unit when one or more targets are selected.

An empty `charge_target_unit_instance_ids` tuple with no witness is the active player's no-move choice unless `charge_move_required_target_unit_instance_ids` is non-empty. When the list is empty, no-move records `charge_move_declined`, mutates no model placement, emits no displacement payload, and grants no Fights First effect. When the list is non-empty, submissions must select every required target ID, and the endpoint witness must show the charging unit engaged with every selected target. Historical Attached Unit marks reconcile through committed starting-formation lineage: source effects transfer to every current surviving source successor, and a marked target expands to every current placed surviving target successor. Nested source/target IDs remain replay evidence for the historical identity; adapters must not rewrite or collapse that lineage.

Malformed, stale, wrong-kind, wrong-unit, wrong-mode, unreachable-target, required-target-not-selected, target-without-witness, no-move-with-witness, or witness-start/model-ID drift submissions reject before the pending queue is popped and before a `DecisionRecord` is created. Rule-invalid but well-formed Charge Move proposals, such as degenerate repeated-endpoint paths, over-distance paths, terrain/pathing/coherency failures, missing required target engagement, or non-target engagement, are recorded as rejected attempts with `charge_move_invalid`; the engine emits a fresh `charge_move` proposal request for retry and does not mutate authoritative battlefield state. Endpoint engagement and non-target diagnostics use canonical rules-unit IDs, so a selected Attached Unit's Leader, support, or Bodyguard component cannot reappear as a separate non-target enemy.

Accepted Charge Move proposals consume the shared movement/pathing/terrain/coherency validators. A valid move emits `charge_move_completed`, updates authoritative model placements through engine-owned mutation only, records `BattlefieldTransitionBatch.displacements` with `displacement_kind: "charge_move"` and `source_phase: "charge"`, records endpoint witness details, and registers a `PersistingEffect` with `effect_kind: "charge_grants_fights_first"` until the end of the turn. Source-backed out-of-phase Charge Move proposals may carry explicit `charge_bonus_suppressed` context; those proposals still use the shared Charge Move validation contract but must not register `charge_grants_fights_first`.

Charge declarations and charge rolls are public table information in the current rules scope. Viewer-scoped projections and event deltas still must not leak hidden opponent information through option counts, target candidates, invalid diagnostics, roll metadata, or derived fields if future hidden deployment, reserve, or secret objective mechanics affect Charge eligibility.

Required Phase 15A adapter-contract tests:

- valid charging-unit selection through `FiniteOptionSubmission -> DecisionResult -> GameLifecycle.submit_decision(...)`;
- deterministic JSON-safe unit-selection, roll, decision-record, event, and lifecycle payload round-trip;
- Advanced, Fell Back, engaged, off-battlefield, and no-target eligibility gating;
- no-reachable-target Charge rolls produce no movement or displacement payload;
- reachable-target Charge rolls emit a `submit_movement_proposal` request with proposal kind `charge_move` and a post-roll target snapshot;
- valid Charge Move proposals through `ParameterizedSubmission -> DecisionResult -> GameLifecycle.submit_decision(...)` mutate only after shared validators pass, emit displacement records, and register Fights First;
- stale/malformed Charge Move proposals reject before queue pop and before a `DecisionRecord`;
- mandatory-target declaration and reroll snapshots reject before queue pop when any required target becomes illegal, unavailable, destroyed, split differently, or expired;
- repeated selected-target effects preserve all source effect IDs, expose one compatible reroll permission, and require all current surviving marked successors;
- rule-invalid but well-formed Charge Move proposals record rejected attempts, emit typed diagnostics, retry with a fresh request, and do not mutate battlefield state;
- no-move Charge Move proposals record `charge_move_declined` without displacements or Fights First;
- viewer-scoped projection/event redaction for any future hidden Charge eligibility or target information.

## Phase 16A Deployment Setup Decisions

Phase 16A replaces the setup deterministic placement bridge with source-backed Deploy Armies decisions. Deployment remains a setup placement operation: adapters choose a pending unit option, then submit explicit final model poses for that selected rules unit. Adapters must not mutate battlefield state, infer deployment order, invent deployment zones, or place units from option payloads.

Phase 16A exposes this finite setup decision:

- `select_deployment_unit`: finite player choice during setup step `deploy_armies`. The engine emits one option for each currently legal undeployed rules unit owned by the actor. Option IDs are deterministic `deploy:<rules_unit_id>` tokens. Option payloads include `submission_kind: "select_deployment_unit"`, game ID, player ID, setup step, selected rules-unit ID, attached-unit/component IDs, complete model IDs, owning deployment-zone IDs, mission/deployment/terrain source IDs, and ruleset descriptor hash. Adapters must select one pending option ID and must not synthesize option IDs for reserved, embarked, already deployed, destroyed, or otherwise unavailable units.

Selecting a deployment unit records the finite `DecisionRecord`, emits `deployment_unit_selected`, and immediately emits the parameterized placement request:

- `submit_deployment_placement` with proposal kind `deployment_placement`. The request has the fixed `submit_parameterized_payload` option and embeds a `DeploymentPlacementRequest` in `payload.proposal_request`. The request context includes game ID, ruleset descriptor hash, setup step `deploy_armies`, actor/player ID, selected rules-unit ID, attached/component unit IDs, the exact model IDs that must be placed, owning deployment-zone IDs, source-backed `MissionSetup` payload, terrain/objective/deployment map IDs, and deployment placement context.

Adapters answer with `DeploymentPlacementProposal` through `ParameterizedSubmission -> DecisionResult -> GameLifecycle.submit_decision(...)`. The payload must include:

- `proposal_request_id`;
- `proposal_kind: "deployment_placement"`;
- `game_id`;
- `ruleset_descriptor_hash`;
- `setup_step: "deploy_armies"`;
- `player_id`;
- `unit_instance_id`;
- `placement_kind: "deployment"`;
- one `ModelPlacement` for every required model ID, including attached rules-unit component models when applicable;
- the replay-safe request context from the pending request.

Malformed, stale, wrong-actor, wrong-step, wrong-kind, wrong-ruleset-hash, wrong-unit, omitted-model, extra-model, wrong-owner, wrong-component, wrong-placement-kind, stale-mission-setup, or model-set drift submissions reject before the pending queue is popped and before a `DecisionRecord` is created. Rule-invalid deployment placements, including out-of-bounds endpoints, ordinary placements outside the owning deployment zone, invalid `INFILTRATORS` distance, illegal terrain endpoints, model overlap, Engagement Range violations, objective endpoint violations, Fortification unsupported paths, and coherency failures, return typed invalid diagnostics and do not mutate authoritative battlefield state.

Accepted deployment proposals mutate only through engine-owned validators. They update the authoritative battlefield state with deployment placements, emit `deployment_unit_placed`, emit `battlefield_models_placed`, and preserve deterministic replay-safe placement payloads. When all deployable model IDs are placed or explicitly accounted for by reserves, embarked state, destroyed state, or other typed setup accounting, Deploy Armies completes and battle entry proceeds through the normal lifecycle.

Deployment choices are public table setup information in the current Phase 16A rules scope. If a future mission, reserve, hidden deployment, or secret pre-battle mechanic hides setup information, pending requests, option lists, proposal diagnostics, placement events, projections, and event deltas must be viewer-scoped and must not leak hidden opponent information through counts, model IDs, source context, or derived fields.

Required Phase 16A adapter-contract tests:

- valid deployment unit selection through `FiniteOptionSubmission -> DecisionResult -> GameLifecycle.submit_decision(...)`;
- valid deployment placement through `ParameterizedSubmission -> DecisionResult -> GameLifecycle.submit_decision(...)`;
- stale, malformed, wrong-context, and drifted placement submissions reject before queue pop and before mutation;
- ordinary deployment-zone validation, `INFILTRATORS` validation, model-set completeness, attached rules-unit grouping, reserves exclusion, terrain/objective/engagement/coherency invalid diagnostics, and no deterministic placement bridge;
- deterministic JSON-safe decision/event/lifecycle replay payload round-trip;
- viewer-scoped projection/event redaction for any future hidden deployment or setup information.

## Phase 16B Redeploy And Scout Pre-Battle Decisions

Phase 16B adds setup decisions after ordinary deployment and before the first battle round. Redeploy is a remove-and-set-up operation, not movement. Scout reserve setup is setup placement from Strategic Reserves. Scout Move and Dedicated Transport Scout Move are physical movement and require path evidence, but they are not Movement phase actions.

Phase 16B exposes these finite setup decisions:

- `select_redeploy_unit`: finite player choice during setup step `redeploy_units`. The engine emits one deterministic `redeploy:<rules_unit_id>` option for each currently legal redeploy candidate and always includes `complete_redeploys`. A source-backed generic RuleIR permission may also emit `redeploy_to_strategic_reserves:<rules_unit_id>` for a permitted rules unit. Option payloads include submission kind, game ID, player ID, setup step, selected rules-unit ID when applicable, component/model IDs, owning deployment-zone IDs, source rule ID, action kind, proposal kind, Scout metadata when present, mission/deployment/terrain source IDs, ruleset descriptor hash, and `ignore_strategic_reserves_limit: true` only for an explicit cap-exempt RuleIR option. Adapters must select one pending option ID and must not synthesize redeploy targets, source permissions, or Strategic Reserves exemptions from visible battlefield state or rule display text.
- `select_prebattle_action`: finite player choice during setup step `resolve_prebattle_actions`. The engine emits deterministic `scout_reserve_setup:<rules_unit_id>`, `scout_move:<rules_unit_id>`, and `dedicated_transport_scout_move:<transport_unit_id>` options when those branches are legal, plus `complete_prebattle_actions`. Adapters must not invent Scout options, promote an embarked unit outside the Dedicated Transport branch, or mutate cargo/reserve/battlefield state from option payloads.

When both players have unresolved redeploy effects, the engine emits the Phase 12A finite `resolve_sequencing_order` request before `select_redeploy_unit`. That request uses a before-battle timing window and a deterministic roll-off to choose the deciding player. Scout and other `resolve_prebattle_actions` rules do not emit that generic sequencing request. The engine instead persists a `PreBattleAlternationCursor`, begins with the player who will take the first turn, advances after each resolved unit action, and skips only a player with no unresolved pre-battle rule. Lifecycle status exposes it at `prebattle_timing_state.alternation_cursor`, and serialized `GameState` exposes the same JSON-safe value at `prebattle_alternation_cursor`; adapters render the pending request for its engine-selected actor and must not sort, advance, reconstruct, or bypass the cursor locally.

Selecting a redeploy or Scout action records the finite `DecisionRecord`, emits the corresponding selection event, and emits one of these parameterized requests:

- `submit_redeploy_placement` with proposal kind `redeploy_placement`;
- `submit_scout_reserve_setup` with proposal kind `scout_reserve_setup`;
- `submit_scout_move` with proposal kind `scout_move`.

The `redeploy_to_strategic_reserves:<rules_unit_id>` branch is a complete finite action and does not emit a placement proposal. After the pending option is revalidated, the engine removes the selected rules unit's current grouped battlefield placements, creates a source-linked `ReserveState` with kind `strategic_reserves`, records `PreBattleActionRecord(action_kind="redeploy_to_strategic_reserves")`, and emits `prebattle_redeploy_to_strategic_reserves`. The source RuleIR permission owns the exemption from the ordinary Strategic Reserves points/unit cap. A single permission remains available for its deterministic `maximum_units` count even if its source unit is one of the units redeployed after the activation began. Adapters must not calculate points-cap availability, create reserve state, remove models, or count permission uses locally.

All three request types embed a `PreBattleProposalRequest` in `payload.proposal_request` and expose the fixed `submit_parameterized_payload` option. The request context includes game ID, actor/player ID, setup step, selected rules-unit ID, component unit IDs, exact model IDs, action kind, source rule ID, source selection request/result IDs, ruleset hash, source-backed `MissionSetup`, and owning deployment-zone payloads. Scout Move requests also include the selected `scout_distance_inches`; that value is engine-derived from structured Scouts ability instances using the official duplicate-distance rule. Current catalog ability ownership is datasheet/component-granular, so every alive model in a component receives that component's structured Scouts descriptors. A `SCOUTS` keyword without a structured Scouts descriptor is source-data invalid and fails fast rather than producing a default distance.

Adapters answer redeploy and Scout reserve setup with `PreBattlePlacementProposal` through `ParameterizedSubmission -> DecisionResult -> GameLifecycle.submit_decision(...)`. The payload must include:

- `proposal_request_id`;
- `proposal_kind: "redeploy_placement"` or `"scout_reserve_setup"`;
- `game_id`;
- `ruleset_descriptor_hash`;
- setup step `redeploy_units` or `resolve_prebattle_actions`;
- `player_id`;
- `unit_instance_id`;
- `action_kind`;
- `source_rule_id`;
- `placement_kind: "redeploy"` or `"strategic_reserves"`;
- one `ModelPlacement` for every required model ID;
- the replay-safe request context from the pending request.

Accepted redeploy proposals remove the selected rules unit temporarily and then set it up with placement records. They emit deterministic removal and placement batches, not displacement records, and record `PreBattleActionRecord(action_kind="redeploy")`. Accepted Scout reserve setup proposals place the selected Strategic Reserves unit wholly within the controlling player's deployment zone, transition its reserve state to arrived at setup timing, and record `PreBattleActionRecord(action_kind="scout_reserve_setup")`.

Adapters answer Scout Move and Dedicated Transport Scout Move with `ScoutMoveProposal` through `ParameterizedSubmission -> DecisionResult -> GameLifecycle.submit_decision(...)`. The payload must include:

- `proposal_request_id`;
- `proposal_kind: "scout_move"`;
- `game_id`;
- `ruleset_descriptor_hash`;
- setup step `resolve_prebattle_actions`;
- `player_id`;
- `unit_instance_id`;
- `action_kind: "scout_move"` or `"dedicated_transport_scout_move"`;
- `source_rule_id`;
- `scout_distance_inches` exactly matching the pending request;
- `witness`, a `PathWitness` covering every alive placed model in the selected unit or transport;
- the replay-safe request context from the pending request.

Malformed, stale, wrong-actor, wrong-step, wrong-kind, wrong-ruleset-hash, wrong-unit, wrong-source-rule, invented reserve exemption, exhausted or unavailable RuleIR permission, omitted-model, extra-model, wrong-owner, wrong-component, wrong-placement-kind, missing-witness, witness-model drift, witness-start drift, Scout-distance drift, or stale reserve/cargo submissions reject before the pending queue is popped and before a `DecisionRecord` is created. Rule-invalid pre-battle proposals, including out-of-zone setup, terrain/objective endpoint failures, model overlap, Engagement Range violations, coherency failures, degenerate repeated-endpoint Scout paths, pathing/terrain failures, and Scout final positions not more than 8" horizontally from every enemy unit, return typed invalid diagnostics and do not mutate authoritative state.

Accepted Scout Move proposals consume the shared movement/pathing/terrain/coherency validators. A valid Scout Move emits `prebattle_scout_move_completed`, updates authoritative model placements through engine-owned mutation only, records `BattlefieldTransitionBatch.displacements` with `displacement_kind: "scout_move"` and `source_step: "resolve_prebattle_actions"`, and records `PreBattleActionRecord(action_kind="scout_move")` or `PreBattleActionRecord(action_kind="dedicated_transport_scout_move")`. It must not mark the unit as having Advanced, Fallen Back, Remained Stationary, shot, started a Mission Action, or moved in the Movement phase. Dedicated Transport Scout Move keeps cargo state intact.

Every accepted Scout unit action and `complete_prebattle_actions` choice advances the persisted cursor atomically with its `PreBattleActionRecord`. Restore validates the cursor against its action/decision ledger and the pending request actor; cursor, pending-request, or provenance drift fails closed. Replay re-submits the same recorded decisions through lifecycle dispatch and therefore reproduces the same player/unit alternation without adapter-owned state.

Redeploy and Scout choices are public table setup information in the current Phase 16B rules scope. If a future mission, reserve, hidden deployment, or secret pre-battle mechanic hides setup information, pending requests, option lists, proposal diagnostics, placement/movement events, action records, projections, and event deltas must be viewer-scoped and must not leak hidden opponent information through counts, model IDs, source context, reserve/cargo state, or derived fields.

Required Phase 16B adapter-contract tests:

- valid redeploy unit selection and placement through the shared lifecycle path;
- valid source-backed `redeploy_to_strategic_reserves` finite selection, cap exemption, permission-use limit, reserve-state/action/event round-trip, and source-gate exhaustion through the shared lifecycle path;
- valid Scout reserve setup and Scout Move submissions through the shared lifecycle path;
- simultaneous pre-battle effects emit and consume a Phase 12A sequencing request before player selection;
- stale, malformed, wrong-context, drifted, degenerate repeated-endpoint, and rule-invalid pre-battle proposals reject before queue pop and before mutation;
- redeploy emits removal plus placement records and no displacement records;
- Scout duplicate-distance examples produce the official selected distance;
- Scout Move requires a per-model `PathWitness`, uses shared validators, records Scout displacements, and does not mark Movement phase action state;
- Scout Move final positions must be more than 8" horizontally from every enemy unit;
- Dedicated Transport Scout Move is available only for a `DEDICATED_TRANSPORT` wholly within its deployment zone with all embarked models having Scouts, and mixed non-Scouts cargo is ineligible;
- deterministic JSON-safe decision, action-record, event, lifecycle, and replay payload round-trip;
- viewer-scoped projection/event redaction for any future hidden redeploy or pre-battle information.

## Phase 16C Reserve Declaration Decisions

Phase 16C adds setup reserve choices during Declare Battle Formations, after battlefield creation and before Deploy Armies. These choices decide whether rules units start on the battlefield, in Strategic Reserves, or in a source-backed Deep Strike reserve state. AIRCRAFT mandatory reserve declarations are engine-owned consequences in the same setup step and are recorded as ordinary `ReserveState` payloads.

Phase 16C exposes the finite decision type `select_reserve_declaration`. The pending request payload contains `payload.reserve_declaration_request` with request ID, game ID, actor/player ID, setup step `declare_battle_formations`, ruleset descriptor hash, Strategic Reserves points limit, current Strategic Reserves points, and available declaration count. Adapters answer by selecting one emitted option ID:

- `declare_strategic_reserves:<rules_unit_instance_id>` for a legal actor-owned rules unit whose components have source-backed points, none has `FORTIFICATION`, and whose aggregate component plus embarked-unit points fit the Strategic Reserves cap;
- `declare_deep_strike:<rules_unit_instance_id>` for a legal actor-owned rules unit whose every component has Deep Strike;
- `complete_reserve_declarations` to record that the player is done choosing optional reserve declarations.

Option payloads are complete `ReserveDeclarationSelection` payloads. They include submission kind, action kind, game ID, player ID, setup step, ruleset descriptor hash, reserve origin/kind, source rule ID, selected unit ID, unit points, embarked unit points, Strategic Reserves points limit, current points, points after declaration, points contribution, embarked unit IDs, and source IDs. Adapters must not invent reserve option IDs, infer points from roster display data, mutate reserve state from payloads, or silently deploy a unit whose reserve declaration is illegal.

Accepted Strategic Reserves selections create deterministic `StrategicReserveDeclaration` and `ReserveState` payloads keyed by the canonical rules-unit ID, enforce the battle-size 50% Strategic Reserves cap across every component and embarked unit, reject FORTIFICATIONS, preserve source rule IDs and points contribution, and exclude every component from Deploy Armies options. Accepted Deep Strike selections create one canonical Deep Strike `ReserveState` consumed later by the grouped reserve-arrival placement proposal path. Accepted completion selections emit a replay-safe completion event and do not mutate reserve state.

Malformed, stale, wrong-actor, wrong-step, wrong-ruleset-hash, wrong-current-points, wrong-option, option-payload drift, duplicate, wrong-player, unknown-unit, over-cap, missing source-points, or forbidden-unit submissions reject before the pending queue is popped and before a `DecisionRecord` or reserve mutation is created. Rule-invalid reserve declarations must not be repaired by changing reserve kind, deploying the unit, or dropping it.

Reserve declarations are simultaneous-secret Declare Battle Formations choices.
Every pending request, option list, DecisionRecord, automatic AIRCRAFT
declaration, reserve mutation event, and derived reserve/cargo state is visible
only to the owning player and an omniscient administrator until both players
have completed the step. If the configured setup sequence includes Declare
Battle Formations, this secrecy window begins at game creation so that choices
pre-materialized during `muster_armies` cannot leak before the declaration step
becomes current. A sequence without that step has no battle-formation secrecy
window. Army-list unit/model identities and datacards remain public. Throughout
the unresolved interval, both `battlefield_view` and the sibling raw
`battlefield_state` neutralize opponent formation state and poses, while live
opponent modifier traces and mutable unit-resource totals remain at their public
roster baseline. Completing the step emits one deterministic public
`battle_formations_revealed` event with
the final reserve, transport-cargo, Dedicated Transport consequence, and
battle-formation faction-rule states; later deployment availability and
battlefield projections are public. Adapters must not infer a hidden declaration
from option counts, missing deployment candidates, cursor metadata, or another
projection sibling.

Leader and Support attachment declarations are resolved during Muster Armies,
not Declare Battle Formations. The public `army_mustered` event includes the
army's exact frozen `starting_attached_unit_records`, identically for both players
and administrators. Adapters must not hide those attachment bindings behind the
battle-formation reveal.

Required Phase 16C adapter-contract tests:

- valid Strategic Reserves selection through `FiniteOptionSubmission -> DecisionResult -> GameLifecycle.submit_decision(...)`;
- valid Deep Strike selection through the same lifecycle path;
- AIRCRAFT mandatory reserve state is source-backed and serialized as ordinary reserve state;
- Strategic Reserves points cap, missing points, FORTIFICATION filtering, duplicate declarations, wrong-owner units, and unknown units reject or remain absent before battle start;
- stale, malformed, wrong-context, and drifted submissions reject before queue pop and before mutation;
- declared reserve units are absent from Deploy Armies options and later use the shared Move Units reserve-arrival path;
- deterministic JSON-safe decision, reserve-state, event, lifecycle, and replay payload round-trip;
- owner/opponent/administrator differential projection and event coverage before
  reveal, plus identical public formation state after reveal.

## Phase 17G Setup Faction-Rule Decisions

Phase 17G adds opt-in setup decisions for faction runtime content and source-backed catalog RuleIR. Battle-formation choices are emitted during Declare Battle Formations when a mustered army's runtime contribution registers a battle-formation hook. Source rules whose timing is the start of the battle use the separate final setup boundary after reserve declarations, deployment, redeployments, and pre-battle actions have resolved, immediately before the setup-completion gate may emit `battle_started`. The current battle-formation hooks include Death Guard Nurgle's Gift plague selection, updated from the 11th Edition faction-pack `RULES UPDATES` section, Aeldari Corsair Coterie Archraider model selection, and Imperial Knights Code Chivalric oath selection. Aeldari Wraithlord Fated Hero uses the start-battle boundary.

Phase 17G exposes the finite decision type `select_faction_rule_setup_option`. The pending request payload contains game ID, the authoritative current setup step, faction ID when applicable, source rule ID, hook ID, state kind when applicable, and hook-specific target fields such as enhancement ID or target unit ID. Adapters answer by selecting one emitted option ID. Current Death Guard options are:

- `death_guard:nurgles_gift:skullsquirm_blight`;
- `death_guard:nurgles_gift:rattlejoint_ague`;
- `death_guard:nurgles_gift:scabrous_soulrot`.

Option payloads include `submission_kind: "death_guard_nurgles_gift_plague_selection"`, player ID, faction ID, source rule ID, hook ID, state kind, plague ID, and setup step. Adapters must not invent plague IDs, infer faction ownership from display text, mutate effect state, or apply the selected plague locally.

Current Aeldari Corsair Coterie Archraider options use the form `aeldari:corsair-coterie:archraider:<unit_instance_id>:<model_instance_id>`. Option payloads include `submission_kind: "aeldari_corsair_coterie_archraider_model_selection"`, player ID, source rule ID, hook ID, enhancement ID, assignment source ID, target unit ID, and selected model ID. Adapters must not invent model IDs or mark a Lord of Deceit bearer locally.

Current catalog start-battle keyword-choice options use the form `<source_clause_id>:keyword:<keyword>`. Wraithlord Fated Hero emits exactly `INFANTRY`, `MONSTER`, `MOUNTED`, and `VEHICLE`. Request and option payloads include `submission_kind: "catalog_start_battle_keyword_choice"`, catalog record ID, source RuleIR ID/hash, clause ID, source unit/model IDs, and the selected keyword on each option. The request is not exposed during Declare Battle Formations, reserve declaration, deployment, redeployment, or pre-battle action resolution. At the final start-battle boundary it blocks `battle_started` until resolved. Before queue pop, the engine validates the selected option through the common finite-decision contract and independently asks the start-battle hook registry to reproduce the complete pending request with its already-issued request ID. Validator selection does not depend on replay-controlled request payload fields. Stale duplicates; malformed or non-object payloads; conflicting, missing, or changed hook/submission signatures; and source, timing, or option-inventory drift return typed invalid status without changing any lifecycle payload field. Accepted selection records one engine-owned generic hit-reroll effect and one wound-reroll effect, both scoped to attacks by that source model against units with the selected canonical keyword and expiring only at battle end, then emits `catalog_start_battle_keyword_selected`. The pair is one atomic authoritative choice bundle: during battle, lifecycle reconstruction audits every live effect identified by any Fated Hero envelope, RuleIR, trigger-event, or deterministic effect-ID signature against the static mustered source population and fails closed on a missing, extra, or misrouted effect, keyword mismatch, unsupported keyword, owner/source/model drift, RuleIR hash or clause drift, roll type/value drift, or expiration drift. After the game reaches `complete`, no candidate Fated Hero effect may remain; reconstruction instead requires the exact historical `DecisionRecord` and `catalog_start_battle_keyword_selected` event, including the serialized two-effect bundle, to validate against every static mustered source. Adapters must not invent keywords, infer the selection from display text, grant rerolls locally, retain expired effects, or mutate persisting effects.

Current Imperial Knights Code Chivalric options use source hook IDs from `warhammer_40000_11th:imperial_knights:army_rule:code_chivalric`. Option payloads include `submission_kind: "imperial_knights_code_chivalric_oath"`, player ID, source rule ID, hook ID, deed selection mode, deed ID when fixed, quality selection mode, quality ID when fixed, and optional Lay Low the Tyrant target model/unit IDs. Random deed options include an engine-enumerated Lay Low target because the engine-owned D6 can produce that deed; adapters must choose one emitted option ID and must not invent target IDs, deed IDs, quality IDs, or random-roll results.

Accepted Death Guard selections create a deterministic `FactionRuleState` with state kind `death_guard_nurgles_gift_plague_selection` and emit `death_guard_nurgles_gift_plague_selected`. Later phase/query hosts consume that state with live battlefield evidence: Death Guard models project Contagion Range from live placed Death Guard models only, Contagion Range is capped at 12" after modifiers, Skullsquirm Blight applies only to melee Hit rolls, Rattlejoint Ague worsens armour-save options by 1, and Scabrous Soulrot worsens Move, Leadership, and Objective Control as the rules require. Adapters must render these as engine-derived values, not calculate them from static catalog text.

Accepted Archraider selections create a deterministic `FactionRuleState` with state kind `aeldari_corsair_coterie_archraider_model` and emit `aeldari_corsair_coterie_archraider_model_selected`. Later Stratagem-cost hosts consume that selected live model to decide whether Lord of Deceit can offer an opponent-facing +1CP cost choice. Adapters must render the selected model as engine state and must not calculate the aura or modifier locally.

Accepted Code Chivalric selections create a deterministic `FactionRuleState` with state kind `imperial_knights_code_chivalric_oath` and emit `imperial_knights_code_chivalric_oath_selected`. If either deed or quality selection mode is `roll_d6`, the engine rolls and records the replay-safe dice result before choosing the final deed or quality and raises the later CP reward to 3CP; fixed selections reward 2CP. Code Chivalric is an approved source-backed exception because its rule explicitly exempts that reward from the normal per-battle-round CP gain limit; its ledger transaction therefore records `cap_exempt: true`. Later battle-round, turn-end, movement, charge, objective-control, Leadership, Shooting, and Fight hosts consume that state. The 11th Edition rules update for `We pledge to reap a great tally` is engine-owned: at end of battle round the deed completes when enemy units destroyed that battle round are greater than the battle round number, using destruction events even if the units later return to the battlefield. Adapters must render the selected and fulfilled oath as engine state and must not award CP, mark an army Honoured, apply Martial Valour rerolls, or apply Eager/Legacy modifiers locally.

Malformed, stale, wrong-actor, wrong-step, wrong-faction, duplicate-selection, unsupported-option, and option-payload drift submissions reject before the pending queue is popped and before a `DecisionRecord`, `FactionRuleState`, `PersistingEffect`, or event is created.

Faction-rule choices made during Declare Battle Formations use the same
simultaneous-secret boundary as reserve declarations. Their pending requests,
option lists, DecisionRecords, state-changing events, dice/resource side
effects, and selected `FactionRuleState` are owner/administrator-only until the
public `battle_formations_revealed` event. Start-battle choices made after that
setup step, such as Fated Hero, are outside this secrecy window and retain their
documented timing. Adapters must not leak an unresolved battle-formation choice
through option counts, source context, selected state kind, selected payload,
derived values, or event siblings.

Required Phase 17G setup faction-rule tests:

- valid faction-rule setup selection through `FiniteOptionSubmission -> DecisionResult -> GameLifecycle.submit_decision(...)`;
- valid Corsair Archraider model selection creates replay-safe selected-model state;
- valid catalog keyword selection creates replay-safe, model-scoped generic reroll effects;
- wrong actor, wrong faction, duplicate selection, malformed payload, and stale option drift reject before mutation;
- deterministic JSON-safe decision, faction-rule-state, event, lifecycle, and replay payload round-trip;
- live placed model liveness gates later faction-rule consumers;
- viewer-scoped projection/event redaction for any future hidden faction-rule setup selections.

## Phase 17G Fight-Start Faction-Rule Decisions

Phase 17G adds opt-in Fight-start decisions for faction runtime content and generic catalog RuleIR consumers. These decisions are emitted only when the current battle phase is Fight, before the normal `FightPhaseState` opens, and only when a registered Fight-start hook has at least one legal source-backed option. Current implemented hooks include Chaos Daemons Shadow Legion Malice Made Manifest, catalog RuleIR selected-target effects such as The Masque of Slaanesh's Eternal Dance, and optional once-per-battle RuleIR activations such as Finest Hour.

Phase 17G exposes the finite decision type `select_faction_rule_fight_phase_start_option`. The pending request payload contains game ID, battle round, phase `fight`, active player ID, source rule ID, hook ID, enhancement ID, bearer unit ID, bearer rules-unit ID, and eligible enemy rules-unit IDs. Current Malice Made Manifest options use the form `chaos-daemons:shadow-legion:malice-made-manifest:<bearer_rules_unit_instance_id>:<target_enemy_unit_instance_id>`.

Malice Made Manifest requires a placed living model in the Enhancement-bearing
source component and at least one placed living model in each eligible enemy
rules unit. Engagement Range is measured through the shared physical scenario,
so a retained Fight On Death base in a mixed source or target may establish the
range, while a retained-only enemy is not an ordinary Enhancement target.

Malice option payloads include `submission_kind: "chaos_daemons_shadow_legion_malice_made_manifest"`, game ID, battle round, active player ID, phase `fight`, player ID, source rule ID, hook ID, enhancement ID, bearer unit ID, bearer rules-unit ID, and target enemy unit ID. Adapters must not invent target IDs, infer Engagement Range locally, roll dice, apply mortal wounds, or resolve Feel No Pain locally.

Accepted Malice selections validate the enhanced Shadow Legion bearer assignment, confirm the selected enemy rules unit was in the request snapshot and is still within Engagement Range of the bearer's attached rules unit, then roll the source-backed D6/D3 sequence through the deterministic dice manager. A D6 roll of 1 records no effect. A D6 roll of 6 applies 3 mortal wounds. Other D6 results roll D3 mortal wounds. If the target has multiple eligible mortal-wound Feel No Pain sources, the handler emits the standard `select_feel_no_pain` finite decision and resumes through the registered Malice continuation hook after the player chooses the FNP source.

Catalog selected-target Fight-start options use the same `select_faction_rule_fight_phase_start_option` decision type with `submission_kind: "catalog_selected_target_fight_start_effect"` and hook ID `catalog-ir:selected-target-effect`. Request payloads include game ID, battle round, phase `fight`, active player ID, player ID, catalog record ID, ability ID/name, source rule ID, RuleIR hash, source unit/model IDs, selection clause ID, the replay-safe serialized `selection_clause`, effect clause IDs, `available_target_unit_instance_ids`, and `available_catalog_selected_target_options`. Available targets are canonical rules-unit IDs: attached components are deduplicated to one attached-unit ID, keyword predicates use the complete `RulesUnitView`, and distance, Engagement Range, and visibility predicates use all placed living models in the source and target rules units. Option payloads include `selected_catalog_target_effect` and replay-safe `generic_rule_effect_records`. Accepted selections persist engine-owned generic RuleIR effects until the end of the Fight phase, with canonical rules-unit targets and a selected-target gate carried in the effect parameters. Adapters must not invent target IDs, infer Engagement Range or distance predicates locally, mutate wound modifiers, or apply generic RuleIR effects locally.

Catalog once-per-battle Fight-start options use the same decision type with
`submission_kind: "catalog_once_per_battle_fight_start_ability"` and hook ID
`catalog-ir:once-per-battle-ability`. The request and both use/decline option payloads
include game ID, battle round, phase `fight`, active player ID, player ID, catalog
record and ability IDs/names, source rule ID, scoped RuleIR hash and clause ID, source
component-unit, rules-unit, and model IDs, the deterministic battle-scoped usage key, and the current decline
window key. The option payload adds `activate: true|false`; adapters select only an
emitted option ID and must not synthesize usage keys, consume the frequency limit, or
apply effects locally.

Accepted use selections execute the scoped source-backed RuleIR through the generic
executor, append `rule_frequency_limit_consumed`, and persist its effects with the IR
duration. For Finest Hour this creates source-model-scoped melee Attacks and
`[DEVASTATING WOUNDS]` effects until the end of the Fight phase. The usage event makes
later battle-round requests for that same rule/model unavailable. Decline emits
`catalog_once_per_battle_ability_declined`, suppresses only that activation in the
current Fight-start window, and does not consume its battle use. A well-formed finite
selection whose source model becomes unavailable after request creation may be
recorded as a rejected attempt, but it returns typed invalid status before any
frequency event or authoritative effect mutation.

Malformed, stale, wrong-actor, wrong-game, wrong-round, wrong-phase, wrong-active-player, wrong-hook, unsupported-option, option-payload drift, source-record drift, bearer drift, target drift, closed Fight-start window, and no-longer-engaged submissions reject before the pending queue is popped and before a `DecisionRecord`, dice roll, mortal-wound application, or event is created.

Fight-start faction-rule choices are public table information in the current Phase 17G rules scope. If a future Fight-start faction rule hides choices, pending requests, option lists, decision records, damage events, projections, and event deltas must be viewer-scoped and must not leak hidden opponent information through option counts, target snapshots, selected payloads, damage routing, or derived engine values.

Required Phase 17G Fight-start faction-rule tests:

- valid Malice Made Manifest target selection through `FiniteOptionSubmission -> DecisionResult -> GameLifecycle.submit_decision(...)`;
- deterministic D6/D3 roll payloads and mortal-wound application events;
- multiple-source mortal-wound Feel No Pain routing through the shared FNP decision and continuation hook;
- stale, drifted, malformed, wrong-context, and ineligible submissions reject before mutation;
- deterministic JSON-safe decision, event, generic RuleIR effect, lifecycle, and replay payload round-trip;
- valid once-per-battle use and decline through `FiniteOptionSubmission -> DecisionResult -> GameLifecycle.submit_decision(...)`, including battle-use exhaustion and source-model drift without mutation;
- viewer-scoped projection/event redaction for any future hidden Fight-start faction-rule selections.

## Phase 17K Any-Phase Catalog Once-Per-Battle Decisions

Generic catalog RuleIR may emit the finite decision type
`select_catalog_any_phase_once_per_battle_ability` immediately after a
`START_PHASE` runtime event and before that phase's normal body opens. Each public
pending request is source-model scoped and contains `submission_kind`, consumer ID,
game ID, battle round, phase, active player ID, actor/player ID, catalog record and
ability IDs, stable source rule ID, RuleIR hash and payload, clause ID, source unit
and model IDs, deterministic battle usage key, runtime event ID, and the two emitted
option IDs. Use and decline option payloads repeat that context and add
`activate: true|false`. Adapters must submit one emitted option unchanged through
`FiniteOptionSubmission -> DecisionResult -> GameLifecycle.submit_decision(...)`.

Before queue pop or mutation, the engine validates finite-option integrity, game,
round, phase, active player, actor, RuleIR shape/hash, live placed source model, and
the once-per-battle ledger. Accepted use executes the scoped RuleIR through the
generic executor, records the frequency consumption, and persists only the emitted
effects for their IR duration. Accepted decline records no frequency use or effect.
Daemon Prince of Chaos `Unholy Vigour` uses this surface at the start of any phase to
set the source model's invulnerable save to 3+ until that phase ends. Adapters must
not consume the usage key or alter a save characteristic locally.

These requests and their current decision/event records are public table
information and therefore appear in both viewer-scoped projections. Any future
hidden source using this family must add shared adapter redaction and tests before
shipping. Required coverage includes valid adapter-facade submission, stale round
and source-model drift before mutation, deterministic JSON/replay round-trip,
battle-use exhaustion, and both-player projection behavior.

## Phase 17G Fight-End Faction-Rule Decisions

Phase 17G adds Fight-end decisions for faction and catalog runtime content. These decisions are emitted only when the current battle phase is Fight, the normal `FightPhaseState` is at the `end` step, and a registered Fight-end hook has at least one legal source-backed option. Current implemented hooks include Chaos Daemons Bloodthirster Relentless Carnage and Emperor's Children Flawless Blades Daemonic Patrons.

Phase 17G exposes the finite decision type `select_faction_rule_fight_phase_end_option`. The pending request payload contains game ID, battle round, phase `fight`, active player ID, player ID, source rule ID, hook ID, source unit ID, source rules-unit ID, eligible enemy rules-unit IDs, and the decline option ID. Current Relentless Carnage options use the forms `chaos-daemons:bloodthirster:relentless-carnage:<source_rules_unit_instance_id>:decline` and `chaos-daemons:bloodthirster:relentless-carnage:<source_rules_unit_instance_id>:target:<target_enemy_unit_instance_id>`.

Relentless Carnage likewise requires placed living authority in its exact
ability-bearing source component and in each ordinary enemy target. Its
Engagement Range snapshot uses shared physical geometry, so retained Fight On
Death bases can establish range for mixed rules units but retained-only enemy
units are omitted from `eligible_enemy_rules_unit_ids`.

Relentless Carnage option payloads include `submission_kind: "chaos_daemons_bloodthirster_relentless_carnage"`, game ID, battle round, active player ID, phase `fight`, player ID, source rule ID, hook ID, source unit ID, source rules-unit ID, `use_ability`, and a target enemy unit ID for use options. Adapters must not invent target IDs, infer Engagement Range locally, roll the eight D6, apply mortal wounds, or resolve Feel No Pain locally.

Accepted Relentless Carnage use selections validate the source datasheet ability, confirm the selected enemy rules unit was in the request snapshot and is still within Engagement Range of the source attached rules unit, then roll eight source-backed D6 through the deterministic dice manager. Each 4+ applies one mortal wound through the shared mortal-wound application path. If the target has multiple eligible mortal-wound Feel No Pain sources, the handler emits the standard `select_feel_no_pain` finite decision and resumes through the registered Relentless Carnage continuation hook after the player chooses the FNP source. Accepted decline selections emit a replay-safe decline event and do not mutate battlefield state.

Flawless Blades Daemonic Patrons reuses `select_faction_rule_fight_phase_end_option` only when its optional selected-to-fight grant was accepted in the current Fight phase and no enemy model was destroyed by an attack made by any model in that rules unit during that phase. Repeated accepted activations for one rules unit are one phase liability, not one liability per activation. Its request payload contains `submission_kind: "select_failed_fight_activation_model_destruction"`, game/round/phase/active-player/player context, hook and source rule IDs, the RuleIR hash, activation and destruction clause IDs, all grouped `persisting_effect_ids`, the canonical rules-unit ID, and `eligible_model_instance_ids`. It emits one deterministic `destroy-model:<model_instance_id>` option per currently alive model in the rules unit; the selected option adds `selected_model_instance_id`. There is no decline option because the consequence is mandatory once its conditions are met. Accepted selection marks exactly that model destroyed and enters the shared non-attack destruction continuation. Mandatory Deadly Demise trigger/mortal-wound/FNP work occurs before removal. Optional Fight on Death does not grant another selection to a rules unit that has already fought; the retained model is removed by Fight phase-end cleanup. Only after every continuation finishes does the engine remove the placement, consume the grouped effects for that rules unit, validate the retained Attached Unit identity, and emit replay-safe `model_destroyed` and `catalog_failed_fight_activation_model_destroyed` events. The destruction event carries the physical owning unit ID plus the canonical rules-unit ID. Adapters must not infer whether a kill qualifies, choose an unlisted model, apply damage, remove a placement, resolve a destruction reaction, schedule a Fight activation, rewrite an Attached Unit identity, or suppress destruction locally.

The Daemonic Patrons kill check requires a current-round, current-active-player Fight-phase `model_destroyed` event whose `destroying_player_id` is the Flawless Blades controller, whose attacking rules-unit/model lineage belongs to the activated rules unit, and whose target rules unit belongs to an opponent. A kill in the other player's earlier Fight phase in the same battle round does not qualify. An Attached Unit's pre- and post-component-loss attacks remain attributed to the same canonical attached-unit lineage, and its grouped liability remains one rules-unit liability. Destruction by another friendly unit, non-attack destruction, destruction of a friendly model, another phase/turn/round, or the Daemonic Patrons consequence itself does not satisfy the condition. Rule/source/hash/effect/unit/model snapshot drift or a selected model that is no longer alive returns a typed invalid status without mutation.

Malformed, stale, wrong-actor, wrong-game, wrong-round, wrong-phase, wrong-active-player, wrong-hook, unsupported-option, option-payload drift, source drift, target drift, closed Fight-end window, and no-longer-engaged submissions reject before the pending queue is popped and before a `DecisionRecord`, dice roll, mortal-wound application, or event is created.

Fight-end faction-rule choices are public table information in the current Phase 17G rules scope. If a future Fight-end faction rule hides choices, pending requests, option lists, decision records, damage events, projections, and event deltas must be viewer-scoped and must not leak hidden opponent information through option counts, target snapshots, selected payloads, damage routing, or derived engine values.

Required Phase 17G Fight-end faction-rule tests:

- valid Relentless Carnage target selection through `FiniteOptionSubmission -> DecisionResult -> GameLifecycle.submit_decision(...)`;
- deterministic eight-D6 roll payloads and mortal-wound application events;
- mortal-wound Feel No Pain routing through the shared FNP decision and continuation hook;
- Daemonic Patrons accepted-grant persistence, phase-grouped liability, 3+ Critical Wound consumption, current-Fight attack-kill attribution, retained Attached Unit identity, mandatory model selection, and shared engine-owned destruction/reaction routing;
- stale, drifted, malformed, wrong-context, and ineligible submissions reject before mutation;
- deterministic JSON-safe decision, event, lifecycle, and replay payload round-trip;
- viewer-scoped projection/event redaction for any future hidden Fight-end faction-rule selections.

## Phase 17G Shooting-Start Faction-Rule Decisions

Phase 17G adds opt-in Shooting-start decisions for faction runtime content. These decisions are emitted only when the current battle phase is Shooting, before the normal `ShootingPhaseState` opens, and only when a registered Shooting-start hook has at least one legal source-backed option. The current implemented hooks are T'au Empire For the Greater Good, Thousand Sons Cabal of Sorcerers, catalog RuleIR named-weapon ability choices, and catalog RuleIR Shooting-start selected-target effects.

Phase 17G exposes the finite decision type `select_faction_rule_shooting_phase_start_option`. The pending request payload contains game ID, battle round, phase `shooting`, active player ID, player ID, faction ID, source rule ID, hook ID, effect kind or selection kind, and source-specific eligible option IDs. Current For the Greater Good mark options use the form `tau-empire:for-the-greater-good:observer:<observer_rules_unit_instance_id>:spotted:<spotted_unit_instance_id>`, plus `tau-empire:for-the-greater-good:done`. Current Cabal of Sorcerers options use the form `thousand-sons:cabal-of-sorcerers:model:<manifesting_model_instance_id>:ritual:<ritual_id>:target:<target_rules_unit_instance_id>:channel:<true|false>`, plus `thousand-sons:cabal-of-sorcerers:done`. Cabal option payloads include manifesting rules-unit, component-unit, and model IDs, target rules-unit and component IDs, ritual ID/name, warp charge, high-result threshold, target kind, and the `channel_the_warp` flag. Catalog named-weapon ability choice requests use `submission_kind: "select_catalog_named_weapon_ability_choice"` and include `catalog_record_id`, `ability_id`, `ability_name`, `source_rule_id`, `unit_instance_id`, `clause_id`, `selection_group_id`, `target_scope`, `weapon_names`, `target_model_instance_ids`, `available_named_weapon_ability_option_ids`, and `available_named_weapon_ability_choices`. Catalog option payloads repeat the request context and include `selected_named_weapon_ability_choice` with `option_id`, `selection_option_id`, `selection_option_index`, `selected_weapon_ability`, `keyword`, `ability_descriptor`, and `weapon_ability_value` when the ability is parameterized. Adapters must select one emitted option ID and must not invent weapon names, target model IDs, ability descriptors, or option IDs.

Accepted T'au mark options create an engine-owned `PersistingEffect` until the end of the Shooting phase with the Observer rules unit, its component unit IDs, whether it has the `MARKERLIGHT` keyword, and the Spotted enemy rules unit. The weapon profile modifier later treats eligible non-Observer For the Greater Good units as Guided only while targeting a Spotted unit, improves Ballistic Skill by 1 for that attack, and adds `[IGNORES COVER]` when the marking Observer had `MARKERLIGHT`. Adapters must not infer Observer eligibility, visibility, Markerlight status, Spotted uniqueness, Guided status, Ballistic Skill changes, or weapon keywords locally.

Accepted catalog named-weapon choices create an engine-owned `PersistingEffect` until the end of the Shooting phase with `effect_kind: "catalog_named_weapon_ability_choice"`, the source catalog record/rule/clause IDs, the selected weapon ability keyword, optional parameter value, selected ability descriptor, named weapon list, and target model IDs. The weapon profile modifier consumes that effect only for the selected target model IDs, only in the Shooting phase, and only when the attacking weapon profile name matches one of the named weapons. `[SUSTAINED HITS D3]` is recorded as a structured `Sustained Hits` descriptor with value `"D3"`; the attack sequence rolls the D3 through the deterministic dice manager only when a critical hit actually triggers generated hits. Adapters must not locally add weapon keywords, roll the generated-hit D3, or infer named weapon eligibility from display text.

Catalog Shooting-start selected-target requests reuse `select_faction_rule_shooting_phase_start_option` with `submission_kind: "catalog_selected_target_shooting_start_effect"` and hook ID `catalog-ir:shooting-start-selected-target-effect`. The non-active source player is the actor for an opponent-turn ability. Request payloads carry the catalog record/ability/source RuleIR IDs and hash, source unit/model and clause IDs, the replay-safe serialized `selection_clause`, effect clause IDs, the engine-enumerated `available_target_unit_instance_ids`, and replay-safe `available_catalog_selected_target_options`. Supported source predicates include exact friendly keyword sequences, source-to-target distance, and visibility. The engine enumerates each placed `RulesUnitView` once, canonicalizes supplied target IDs, and evaluates range and visibility across the complete set of placed living component models. Optional abilities include one deterministic decline option. Target options carry `use_ability: true`, `selected_catalog_target_effect`, and engine-prepared `generic_rule_effect_records`; decline carries `use_ability: false` and no effects. Adapters must not enumerate targets, calculate visibility/range, normalize keyword requirements, or prepare effect payloads locally.

Accepted catalog Shooting-start selected-target choices persist engine-owned generic RuleIR effects with the source catalog/rule/clause identity and canonical selected rules-unit gate. The current generic grant-ability consumer can grant `stealth` through the end of the Shooting phase; the shared ranged hit-roll path resolves the attack target to its canonical rules-unit ID and consumes that one rules-unit effect as the ordinary Stealth hit modifier. Decline records resolution without creating an effect. Adapters must not grant Stealth or mutate hit rolls locally.

Accepted Cabal attempts record the model and ritual attempt before the Psychic test, roll 2D6 or 3D6 when `channel_the_warp` is true, route Channel doubles/triples through the standard mortal-wound Feel No Pain continuation path, and resolve the ritual only if the manifesting model is not destroyed and the test meets the ritual warp charge. Destiny's Ruin records source-backed hit rerolls against the target, restricted to Hit rolls of 1 unless the Psychic test result reaches 10+. Twist of Fate records a phase-scoped weapon profile AP modifier of 1, or 2 on a 12+. Doombolt routes D3 mortal wounds, or D3+3 on an 11+, while excluding non-attached Lone Operative units more than 12" from the manifesting model. Temporal Surge records a turn-scoped charge-forbidden effect and emits a `submit_movement_proposal` request with proposal kind `surge_move`; the request carries the engine-rolled maximum move distance and adapters must answer with a `PathWitness`.

Malformed, stale, wrong-actor, wrong-game, wrong-round, wrong-phase, wrong-active-player, wrong-hook, unsupported-option, option-payload drift, already-marked Spotted target, already-used Observer, Battle-shocked Observer, FORTIFICATION Observer, ineligible-to-shoot Observer, duplicate Cabal model attempt, duplicate Cabal ritual attempt, destroyed or unplaced manifesting model, ineligible Temporal target in Engagement Range, Doombolt Lone Operative exclusion, non-visible target, catalog named-weapon target-model or weapon-profile availability drift, selected-target source/complete-rules-unit death or placement drift, keyword/range/visibility drift, and closed Shooting-start window submissions reject before mutation. Selected-target stale validation reconstructs the committed `selection_clause` and re-evaluates the canonical rules unit. Movement, placement changes, or destruction of one attached component do not invalidate a choice while another living component keeps the same rules unit legal; the choice becomes invalid when the complete rules unit is no longer eligible.

Shooting-start faction-rule choices are public table information in the current Phase 17G rules scope. If a future Shooting-start faction rule hides choices, pending requests, option lists, decision records, attack modifiers, projections, and event deltas must be viewer-scoped and must not leak hidden opponent information through option counts, visibility snapshots, selected payloads, or derived weapon profile values.

Required Phase 17G Shooting-start faction-rule tests:

- valid For the Greater Good mark and done choices through `FiniteOptionSubmission -> DecisionResult -> GameLifecycle.submit_decision(...)`;
- valid Cabal of Sorcerers attempt and done choices through `FiniteOptionSubmission -> DecisionResult -> GameLifecycle.submit_decision(...)`;
- valid catalog named-weapon ability choice through `FiniteOptionSubmission -> DecisionResult -> GameLifecycle.submit_decision(...)` or the shared Shooting-start hook path, including request/result payload round-trip;
- valid and declined catalog Shooting-start selected-target choices through `FiniteOptionSubmission -> DecisionResult -> GameLifecycle.submit_decision(...)` or the shared Shooting-start hook path, including source-player actor routing and request/result payload round-trip;
- Guided weapon profile modifier applies only to eligible non-Observer units targeting Spotted units;
- selected catalog named-weapon ability modifiers apply only to the selected model IDs, Shooting phase, and matching named weapon profiles, including `[SUSTAINED HITS D3]` deterministic D3 consumption;
- catalog Shooting-start target enumeration validates friendly keyword sequence, range, visibility, optional decline, engine-owned persisting effects, and expiry; attached targets produce one canonical option, either living component can satisfy range or visibility, and granted Stealth is stored and consumed by canonical rules-unit ID;
- Destiny's Ruin hit rerolls, Twist of Fate AP modifiers, Doombolt mortal wounds, Temporal Surge `surge_move` proposals, Channel perils, and charge-forbidden effects resolve only through engine-owned paths;
- duplicate Spotted target, Battle-shocked Observer, FORTIFICATION Observer, duplicate Cabal model/ritual attempt, Lone Operative exclusion, catalog named-weapon availability drift, stale, drifted, malformed, wrong-context, and closed-window submissions reject before mutation;
- deterministic JSON-safe decision, effect, event, lifecycle, and replay payload round-trip;
- viewer-scoped projection/event redaction for any future hidden Shooting-start faction-rule selections.

## Phase 17K Post-Attack Catalog Hit-Target Status And Effect Decisions

Phase 17K adds post-attack catalog RuleIR decisions for abilities that trigger in the Shooting phase after a model or unit has shot, enumerate enemy units hit by one or more of those attacks, and apply a phase-scoped status denial or generic source-backed RuleIR effect to the selected unit. The status-denial semantic IR shape is status-generic: parser output uses `SET_CONTEXTUAL_STATUS` with `operation: "deny"`, `status`, `status_label`, `target_scope`, and `rules_context: "status_denial"`. Runtime status consumers must be effect-specific until engine semantics exist for a status. Current runtime status support consumes only `status: "benefit_of_cover"` by denying Benefit of Cover.

The finite decision type is `select_catalog_post_shoot_hit_target_status`. It is emitted from the attack-sequence-completed hook after a Shooting attack sequence, before the Shooting phase continues. If one completed attack sequence yields multiple mandatory source groups, the Shooting lifecycle keeps a deterministic pending completed-sequence continuation and emits one request per unresolved group until all groups for that completed attack-sequence event are resolved; only then may friendly/enemy "unit has shot" Stratagem windows and Shooting-end surge hooks proceed. The pending request actor is the attacking player. Request payloads include `submission_kind: "select_catalog_post_shoot_hit_target_status"`, `hook_id: "catalog-ir:post-shoot-hit-target-status"`, game ID, battle round, phase `shooting`, active player ID, player ID, catalog record ID, ability ID/name, source rule ID, RuleIR hash, source unit ID, source model ID when the source is model-scoped, clause ID, effect index, `status`, `status_label`, `operation: "deny"`, target scope, attack sequence ID, attack-sequence-completed event ID, a replay-safe attack-sequence payload, `available_target_unit_instance_ids`, and `available_post_shoot_hit_target_status_options`.

Option payloads repeat the request context and include `selected_post_shoot_hit_target_status` with the selected option ID and target unit ID. Option IDs are deterministic over the catalog record, source unit/model, clause, effect index, selected target, and status. Hit-target discovery is based on successful hit events from the just-completed attack sequence; all misses produce no request, and a successful hit remains eligible even if the attack later fails to wound. Adapters must select one emitted option ID and must not infer hit targets from display text, event-log inspection, local attack simulation, wound success, damage, destruction, or target visibility.

Accepted selections create an engine-owned `PersistingEffect` through the end of the current Shooting phase with `effect_kind: "catalog_post_shoot_hit_target_status"`, source catalog record/rule/clause/effect IDs, RuleIR hash, source unit/model IDs, selected target unit ID, attack sequence ID, attack-sequence-completed event ID, status, status label, operation, and target scope. For `benefit_of_cover`, the payload includes `benefit_of_cover_denied: true`; the attack sequence save and hit-modifier paths consume that effect so the selected unit cannot gain Benefit of Cover from terrain, Stratagem effects, Indirect Fire, or other phase-scoped cover grants while the effect remains active. Adapters must not add or remove cover locally.

The generic finite decision type is `select_catalog_post_shoot_hit_target_effect`. It is emitted from the same attack-sequence-completed hook after a Shooting attack sequence when a generic catalog RuleIR record needs the source player to select an enemy unit hit by attacks, then applies one or more supported generic effects to either the selected enemy unit or source-backed friendly units. Request payloads include `submission_kind: "select_catalog_post_shoot_hit_target_effect"`, `hook_id: "catalog-ir:post-shoot-hit-target-effect"`, game ID, battle round, phase `shooting`, active player ID, player ID, catalog record ID, ability ID/name, source rule ID, RuleIR hash, source unit/model IDs, selection clause ID, the replay-safe serialized `selection_clause`, effect clause IDs, attack sequence ID, attack-sequence-completed event ID, a replay-safe attack-sequence payload, `available_target_unit_instance_ids`, and `available_catalog_selected_target_options`. Successful-hit IDs and emitted target options are canonical rules-unit IDs, so one hit attached unit produces one option rather than one option per physical component.

When one completed attack sequence produces multiple generic post-shoot source
groups, the engine first emits the existing finite `resolve_sequencing_order`
decision. Its participants carry the complete attack-completion, attack-
sequence, catalog-record, source-unit/model, selection-clause, effect-clause,
and target-option identity. The active player selects one engine-emitted full
ordering. The resulting `sequencing_order_resolved` event fixes that order for
the completed-sequence continuation, including across nested Feel No Pain or
Battle-shock reroll requests; only the next group in that persisted order may
emit `select_catalog_post_shoot_hit_target_effect`.

Generic option payloads repeat the request context and include `selected_catalog_target_effect` with the selected option ID and canonical target rules-unit ID, plus `generic_rule_effect_records` containing the engine-prepared immediate or persisting `generic_rule_execution` effect payloads. Option IDs are deterministic over the catalog record, source unit/model, selection clause, canonical selected target, and attack-sequence-completed event. Hit-target discovery is based on successful hit events from the just-completed attack sequence. A model-scoped source may explicitly select from hits made by that model's complete attached rules unit; that scope is source-backed RuleIR and remains engine-enumerated. Adapters must select one emitted option ID and must not infer eligible targets from display text, event-log inspection, local attack simulation, wound success, damage, destruction, or target visibility.

When the source RuleIR marks a post-shoot selection as optional, the request carries
`optional: true`; target options carry `use_ability: true`, and the engine also emits one
deterministic decline option with `use_ability: false`, a null selected target, and no generic
effect records. Adapters must use that emitted decline option and must not omit or synthesize
the selection locally.

Accepted generic selections resolve immediate effects and create engine-owned `PersistingEffect` records for source-backed durations. Immediate effects may roll a source-backed dice pool, apply mortal wounds through the shared damage-allocation and Feel No Pain continuation path, and condition a later Battle-shock test on one or more mortal wounds having been inflicted. Attached targets complete the selected-target immediate-effect chain against the canonical Attached Unit. Bodyguard, Leader, or Support component loss does not replace that identity: applicable Battle-shock state, persisting effects, and other authoritative state remain on the attached rules-unit ID, and later selected-target groups continue to expose that one currently placed, alive, and otherwise eligible rules unit. If no target model survives direct damage or a Feel No Pain continuation, the engine records `catalog_selected_target_battle_shock_skipped` with `skip_reason: "no_surviving_target_models"` and creates no Battle-shocked state. Persisting effects may extend through a relative next-phase boundary and may modify Battle-shock or Leadership tests. Each persisted effect carries the original RuleIR clause/effect payload, its zero-based `effect_index` semantic slot within that clause, replay-safe execution context, canonical selected target rules-unit ID, selected-target gate parameters, catalog record IDs, source unit/model IDs, attack sequence ID, and attack-sequence-completed event ID. Reapplications receive distinct deterministic effect IDs; each semantic consumer enforces the source-backed stacking rule, including cumulative Battle-shock and Leadership modifiers from separate applications. Semantic drift within one effect slot fails closed. Attack resolution retains the exact attacking model and its physical owning component. The shared generic attack-effect matcher resolves attacker and target component IDs to canonical rules-unit identities for persisting-effect lookup, attacker/target role membership, and rules-unit conditions, while retaining the exact model identity for component ownership, wargear ownership, and model-scoped conditions. A selected-unit attacker effect, such as suppression, gates on the selected attacking rules unit; a source-unit attack effect that was selected against an enemy continues to gate on the current defending target. Adapters must not roll immediate damage, resolve Feel No Pain, force Battle-shock, apply wound rerolls, damage bonuses, status grants, test modifiers, or selected-target gates locally.

The Fight equivalent uses finite decision type and submission kind `select_catalog_post_fight_hit_target_effect` with hook ID `catalog-ir:post-fight-hit-target-effect`. It is emitted by the same attack-sequence-completed registry after a Fight attack sequence and is owned by the Fight decision dispatcher. Payload and option ownership match the generic post-Shooting contract, except `phase` is `fight`; successful-hit discovery remains tied to the exact completed attack sequence and source model. The request actor and `player_id` are derived from the attacking model's controller, which may differ from the active turn player. The engine prepares effects using the source RuleIR duration, including permanent contextual statuses, and the Fight lifecycle resolves every pending completed-sequence group before continuing activation. Adapters must select one emitted option ID and must not infer hit targets, manufacture persistent statuses, or apply later status consequences locally.

Malformed, stale, wrong-actor, wrong-game, wrong-round, wrong-phase, wrong-active-player, wrong-hook, unsupported-option, option-payload drift, attack-sequence payload drift, source-record drift, target drift, no-longer-enemy target, and closed-window submissions reject before queue pop, before a `DecisionRecord` is created, and before any `PersistingEffect` or selected event is recorded.

Post-shoot hit-target status choices are public table information in the current Phase 17K rules scope because they are based on just-resolved public attacks and visible target units. If a future post-shot status denial is hidden, pending requests, option lists, decision records, effects, attack modifiers, projections, and event deltas must be viewer-scoped and must not leak hidden information through option counts, target snapshots, selected payloads, or derived cover values.

Required Phase 17K post-attack catalog tests:

- valid hit-target status selection through `FiniteOptionSubmission -> DecisionResult -> GameLifecycle.submit_decision(...)` or the shared Shooting phase result path, including request/result payload round-trip;
- persisted `catalog_post_shoot_hit_target_status` and generic `generic_rule_execution` effects are replay-safe and expire at the current Shooting phase end;
- Benefit of Cover denial suppresses both cover hit-roll penalties and saving-throw cover options from all engine-owned cover sources;
- multi-clause catalog records use the record-scoped `runtime_clause_id` when discovering post-shoot status choices;
- hit-target discovery requires at least one successful hit and does not require a successful wound;
- multiple generic source groups from one completed attack-sequence event first emit `resolve_sequencing_order`, preserve the chosen order through nested continuations, and resolve in that order before later completed-sequence windows proceed;
- generic selected-target effect choices deduplicate attached hit targets, persist selected-target-gated generic RuleIR effects by canonical rules-unit ID, and consume attacker-role or defender-role gates only through engine-owned attack hooks;
- immediate selected-target mortal wounds, Feel No Pain continuations, conditional Battle-shock (including intact attachments, split survivors, and destroyed-target skips), relative next-phase expiry, and source-backed cumulative Battle-shock/Leadership test modifiers remain engine-owned and replay-safe;
- post-Fight selected-target effects use the Fight lifecycle and preserve permanent source-backed status duration through replay round-trip;
- stale, drifted, malformed, wrong-context, and ineligible-target submissions reject before mutation;
- deterministic JSON-safe decision, effect, event, lifecycle, and replay payload round-trip;
- viewer-scoped projection/event redaction for any future hidden post-shoot status selections.

## Phase 17K Move/Setup-Completed Catalog Mortal-Wound Target Decisions

Phase 17K exposes one generic catalog RuleIR decision family for abilities that trigger after a supported physical movement event or setup event, select an eligible enemy rules unit, and roll once per current source model for mortal wounds. Existing Charge-end support consumes a `charge_move_completed` event, Engagement Range targeting, a 4+ threshold, and D3 mortal wounds per success. Aeldari Swooping Hawks' source-backed Grenade Pack consumes Movement-phase `movement_activation_completed` events for Normal, Advance, and Fall Back moves plus `reinforcement_unit_arrived` setup events; it requires a visible enemy rules unit within 8 inches, is optional and once per turn, rolls one D6 for each current Swooping Hawks model, inflicts one mortal wound per 4+ to a shared maximum of six, and records a source-backed end-of-turn restriction that forbids targeting the source rules unit with `core:explosives`.

The finite decision type remains `select_catalog_unit_move_completed_mortal_wounds_target`. It is emitted from the shared unit-move-completed hook before the owning phase continues. The pending request actor is the source unit's player. Request payloads include `submission_kind: "select_catalog_unit_move_completed_mortal_wounds_target"`, `hook_id: "catalog-ir:unit-move-completed-mortal-wounds"`, game ID, battle round, current phase, active player ID, player ID, catalog record ID, ability ID/name, source rule ID, source rules-unit ID, source unit ID, clause ID, effect index, roll threshold, `roll_expression: "D6"`, `roll_count_scope: "each_model_in_this_unit"`, mortal-wound expression, optional maximum mortal wounds, optional target range and visibility requirement, source roll model IDs, trigger event ID, movement action, `available_target_unit_instance_ids`, and `available_unit_move_completed_mortal_wounds_target_options`.

Target option payloads repeat the request context and include `selected_unit_move_completed_mortal_wounds_target` with the selected option ID, target unit ID, and target player ID. Optional sources also emit a deterministic `Decline ability` option whose payload carries `declined_unit_move_completed_mortal_wounds: true`. Option IDs are deterministic over the catalog record, source rules unit, clause, effect index, trigger event, and target or decline action. Target discovery and submission revalidation use current group-aware model geometry, current allegiance, the source-backed range kind, and visibility when required. Adapters must select one emitted option ID and must not infer target eligibility, invent target IDs, roll dice, apply a cap, record a Stratagem restriction, apply mortal wounds, or resolve Feel No Pain locally.

Accepted target selections record an engine-owned selected-target event, then the shared resolver rolls one D6 per source roll model ID through the deterministic dice manager. Successful effects route fixed or dice-expression mortal wounds through the same shared mortal-wound and Feel No Pain path. A source-backed maximum is enforced across every successful per-model effect in the same trigger group, including pending Feel No Pain continuations. Accepted Swooping Hawks selections also record the `core:explosives` targeting restriction until end of turn; accepted declines record a decline event and create no restriction or damage. Once-per-turn frequency is derived from the selected/use event, so neither adapters nor display names own use tracking.

Malformed, stale, wrong-actor, wrong-game, wrong-round, wrong-phase, wrong-active-player, wrong-hook, unsupported-option, option-payload drift, source-record drift, trigger-event drift, movement-action drift, decline drift, target drift, no-longer-enemy target, range drift, visibility drift, and closed-window submissions reject before queue pop, before a `DecisionRecord` is created, and before any selected event, restriction, dice roll, mortal-wound event, or damage mutation is recorded.

These target choices are public table information in the current Phase 17K rules scope because movement/setup events, model positions, range, and visibility are public. If a future ability hides choices or target eligibility, pending requests, option lists, decision records, selected/declined events, restriction effects, damage events, projections, and event deltas must be viewer-scoped and must not leak hidden information through option counts, target snapshots, selected payloads, damage routing, or derived engine values.

Required Phase 17K move/setup-completed catalog mortal-wound tests:

- valid target and decline selections through `FiniteOptionSubmission -> DecisionResult -> GameLifecycle.submit_decision(...)` or the shared owning-phase result path, including request/result payload round-trip;
- deterministic per-model D6 roll events, fixed and dice-expression damage, shared mortal-wound caps, and replay-safe Feel No Pain routing;
- Movement-phase Normal/Advance/Fall Back and setup trigger coverage plus Charge-end coverage;
- group-aware Engagement Range or source-backed range/visibility target discovery for attached rules units and component units;
- source-backed once-per-turn gating and Stratagem targeting restrictions;
- stale, drifted, malformed, wrong-context, and ineligible-target submissions reject before mutation;
- deterministic JSON-safe decision, selected/declined-event, effect, roll-event, lifecycle, and replay payload round-trip;
- viewer-scoped projection/event redaction for any future hidden selections.

## Phase 17G Genestealer Cults Cult Ambush Decisions

Phase 17G implements the 11th Edition Genestealer Cults `Cult Ambush` army rule update. During `declare_battle_formations`, the setup hook grants Resurgence points through the faction-resource ledger based on battle size: Incursion 6, Strike Force 10, and Onslaught 14. This grant is automatic and emits no adapter choice.

The [2026 Warhammer Open Tacoma FAQ](source_rules/faq-warhammer-open-tacoma-2026-dtb3ingprd-cvcl2agtfd.pdf) is formally scoped to that event while the late-July rules update is pending. Its committed [source-package manifest](source_rules/tacoma-open-2026-source-package.json) records the official URLs, PDF SHA-256, event-only scope, and stable source identities. The Aeldari catalog source release records the FAQ page 3 Night Spinner `FRAME` addition as a separately hashed data overlay linked to source ID `warhammer_40000_11th:event_faq:tacoma_2026:frame_keyword_additions`; this catalog keyword correction adds no adapter choice. CORE V2 applies the Cult Ambush correction only when rules overlay `warhammer_40000_11th:event_overlay:tacoma_open_2026` is active. Under that overlay, source ID `warhammer_40000_11th:event_faq:tacoma_2026:cult_ambush_attached_character_exclusions` excludes attached `CHARACTER` models when checking Cult Ambush eligibility, calculating Starting Strength for the Resurgence cost, and constructing the identical replacement unit. A destroyed attached `CHARACTER` component alone does not create a replacement. The base/default ruleset does not record the Tacoma Cult Ambush source ID.

Rules overlay IDs are immutable session source identity. They are included in the `RulesetDescriptor` hash and serialization, copied into authoritative `GameState`, published with session metadata, and verified explicitly by replay source identity. Descriptor, lifecycle, session, and replay payload loaders reject overlay/hash drift. Contract generation also hashes the committed Tacoma PDF and audits the source-backed Genestealer Cults attachment inventory. The current source contains seven Cult Ambush bodyguards and only `CHARACTER` attaching datasheets; generation fails if a non-`CHARACTER` attaching component becomes eligible, because multi-component replacement is not yet supported by the Cult Ambush ingress path.

When an eligible Genestealer Cults unit is destroyed, the engine may emit the finite decision type `select_cult_ambush_resurgence`. The pending request payload contains source rule ID, model-destroyed event ID, destroyed unit ID, destroyed player ID, destroying player ID, battle round, phase, starting strength, Resurgence cost, and current Resurgence points. Current option IDs are:

- `genestealer_cults:cult_ambush:decline:<destroyed_unit_instance_id>`;
- `genestealer_cults:cult_ambush:spend:<destroyed_unit_instance_id>`.

Option payloads include `selection: "decline"` or `selection: "spend"`, source rule ID, destroyed unit ID, model-destroyed event ID, and the Resurgence cost for spend options. Adapters must not decide unit eligibility, calculate costs, spend Resurgence points, clone units, create reserve states, reset wounds or `[ONE SHOT]` usage, or place markers locally.

Accepted spend selections revalidate that every relevant destroyed-unit model has Cult Ambush through the unit's structured ability descriptor, re-check the starting-strength cost table, spend Resurgence points, add an identical replacement unit at Starting Strength with new deterministic model IDs and full wounds, and create a Strategic Reserves `ReserveState` source-backed by Cult Ambush. The replacement is treated as a Cult Ambush reserve unit: it cannot be selected for Rapid Ingress, may later arrive by ordinary Strategic Reserves rules, and is not destroyed by the third-battle-round reserve deadline.

If a marker can legally be placed, the engine emits the parameterized decision type `submit_cult_ambush_marker_placement`. The pending request uses the fixed `submit_parameterized_payload` option and carries source rule ID, marker ID, player ID, replacement unit ID, destroyed unit ID, marker diameter, and required enemy horizontal distance. Adapter payloads use:

```json
{
  "request_id": "decision-request-000012",
  "submission_kind": "cult_ambush_marker_placement",
  "marker_id": "cult-ambush-marker:game-1:round-01:player-a:unit-1:result-1",
  "player_id": "player-a",
  "x_inches": 12.0,
  "y_inches": 18.0
}
```

If the engine reports that no legal marker position exists, adapters may answer the same request with `submission_kind: "cult_ambush_no_marker"` and a replay-safe `no_marker_reason`; this is rejected if a legal marker position still exists. Marker placement validates battlefield bounds and more-than-9-inch horizontal enemy distance before recording a 32mm Cult Ambush marker. Enemy non-AIRCRAFT model moves that end within 8 inches remove markers automatically through engine event processing, not through an adapter choice.

The Phase 18I descriptor publishes both accepted alternatives on every such
request. Variant `place_marker` uses `battlefield_point_placement` and
`proposal-payload.schema.json#/$defs/cult_ambush_marker_point`; variant
`no_marker` uses `confirmation`, requires `no_marker_reason`, and references
`proposal-payload.schema.json#/$defs/cult_ambush_no_marker`. Top-level selection
cardinality is null because the alternatives have different input semantics.
The engine remains authoritative for whether the no-marker alternative is legal.

At the end of an opponent Movement phase, each surviving marker can emit the shared turn-end finite decision type `select_faction_rule_turn_end_option` with `selection_kind: "cult_ambush_marker_ingress"`. Current options are:

- `genestealer_cults:cult_ambush:marker:<marker_id>:decline`;
- `genestealer_cults:cult_ambush:marker:<marker_id>:unit:<unit_instance_id>`.

Accepted ingress selections emit a placement proposal request with `proposal_kind: "cult_ambush_placement"` and placement kind `cult_ambush`. The submitted `PlacementProposalPayload` must place at least one model in base contact with the marker and every other model wholly within 3 inches of that marker. The engine validates reserve state, marker activity, battlefield bounds, model/objective overlap, coherency, and marker distance before placing the unit, marking the reserve arrived, and removing the marker. Cult Ambush marker ingress can resolve in battle round 1.

Malformed, stale, wrong-actor, wrong-unit, wrong-marker, unsupported-option, option-payload drift, cost drift, insufficient-resource, ability drift, illegal marker position, missing reserve state, non-Cult-Ambush reserve state, arrived reserve state, inactive marker, placement kind drift, model overlap, objective marker overlap, battlefield-bounds, marker-distance, and coherency-invalid submissions reject before unauthorized mutation.

Cult Ambush choices and markers are public table information in the current Phase 17G rules scope. If a future update hides a marker, replacement unit, pending request, or reserve state, projections and event deltas must be viewer-scoped and must not leak hidden information through marker counts, option counts, eligible unit IDs, selected payloads, reserve state, or derived distances.

Required Phase 17G Cult Ambush tests:

- initial Resurgence grant by battle size is idempotent and replay-safe;
- valid spend and decline choices through `FiniteOptionSubmission -> DecisionResult -> GameLifecycle.submit_decision(...)`;
- replacement units are deterministic, full-wound, source-backed Cult Ambush Strategic Reserves;
- attached `CHARACTER` components are excluded from eligibility, Resurgence cost, and replacement composition;
- marker placement accepts valid parameterized payloads and rejects stale, drifted, malformed, or illegal positions;
- enemy non-AIRCRAFT marker removal and AIRCRAFT exclusion are event-driven and replay-safe;
- valid marker ingress selection emits `cult_ambush_placement` and first-round placement can arrive through the shared placement proposal contract;
- deterministic JSON-safe decision, marker, reserve, event, lifecycle, and replay payload round-trip;
- viewer-scoped projection/event redaction for any future hidden Cult Ambush state.

## Phase 17G Turn-End Faction-Rule Decisions

Phase 17G adds opt-in turn-end decisions for faction runtime content and generic catalog IR consumers. These decisions are emitted only when the mustered army's runtime contribution or catalog IR index registers a turn-end hook and the completed phase matches the hook's timing. Current implemented support includes Aeldari Corsair Coterie Webway Pathstone, Chaos Daemons Shadow Legion Fade to Darkness, Genestealer Cults Cult Ambush marker ingress, Grey Knights Gate of Infinity, and catalog IR `catalog-ir:can-be-placed-in-reserves` abilities such as Chaos Daemons Flesh Hounds' Hunters from the Warp at the end of the opponent's turn.

Phase-end objective-control hooks and phase-end cleanup resolve before turn-end faction-rule decisions are emitted. Adapters must therefore treat turn-end repositioning choices as occurring after engine-owned phase-end objective-control state has already been recorded for that phase.

Phase 17G exposes the finite decision type `select_faction_rule_turn_end_option`. The pending request payload contains game ID, battle round, active player ID, completed phase, source rule ID, and hook ID. Single-target sources include a target unit ID; Grey Knights Gate of Infinity includes `max_units`, `selected_count`, `remaining_units`, selected rules-unit IDs, eligible rules-unit IDs, and eligible component unit IDs by rules unit. Other source-specific payload fields include Webway Pathstone's enhancement ID, Fade to Darkness' enhancement ID and destroyed enemy unit IDs, or catalog IR fields such as catalog record ID, ability ID, ability name, datasheet ID, source kind, and rule IR hash. Adapters answer by selecting one emitted option ID. Current Webway Pathstone options use:

- `aeldari:corsair-coterie:webway-pathstone:<unit_instance_id>:use`;
- `aeldari:corsair-coterie:webway-pathstone:<unit_instance_id>:decline`.

Current Fade to Darkness options use:

- `chaos-daemons:shadow-legion:fade-to-darkness:<unit_instance_id>:use`;
- `chaos-daemons:shadow-legion:fade-to-darkness:<unit_instance_id>:decline`.

Current catalog IR turn-end reserve options use:

- `catalog-ir:turn-end-reserves:<catalog_record_id>:<unit_instance_id>:use`;
- `catalog-ir:turn-end-reserves:<catalog_record_id>:<unit_instance_id>:decline`.

Current Grey Knights Gate of Infinity options use:

- `grey-knights:gate-of-infinity:<rules_unit_instance_id>:use`;
- `grey-knights:gate-of-infinity:complete`.

Current Genestealer Cults Cult Ambush marker ingress options use:

- `genestealer_cults:cult_ambush:marker:<marker_id>:decline`;
- `genestealer_cults:cult_ambush:marker:<marker_id>:unit:<unit_instance_id>`.

Webway option payloads include `submission_kind: "aeldari_corsair_coterie_webway_pathstone_turn_end"`, player ID, source rule ID, hook ID, enhancement ID, target unit ID, and `use_ability`. Fade to Darkness option payloads include `submission_kind: "chaos_daemons_shadow_legion_fade_to_darkness_turn_end"`, player ID, source rule ID, hook ID, enhancement ID, target unit ID, and `use_ability`; the request payload also carries `destroyed_enemy_unit_instance_ids` captured by the engine from current Fight phase unit-destroyed evidence. Grey Knights option payloads include `submission_kind: "grey_knights_gate_of_infinity_turn_end"`, player ID, source rule ID, hook ID, ability ID, ability name, target rules-unit ID, component unit IDs, `use_ability`, and action `use` or `complete`. Genestealer Cults marker ingress option payloads include `selection: "decline"` or `selection: "ingress"`, source rule ID, marker ID, and the selected Cult Ambush unit ID for ingress selections. Catalog IR option payloads include `submission_kind: "catalog_ir_turn_end_reserves"`, player ID, source rule ID, hook ID, catalog record ID, ability ID, ability name, target unit ID, and `use_ability`. Adapters must not remove the unit from the battlefield, create a reserve state, decide reserve eligibility locally, synthesize destroyed-enemy evidence for Fade to Darkness, split an attached Grey Knights rules unit, calculate Grey Knights remaining cap locally, or move Cult Ambush units from markers locally.

Accepted use selections validate that the rules unit is still on the battlefield, not already in reserves, not within Engagement Range when required by the source rule, and, for Fade to Darkness, that the enhanced unit destroyed one or more enemy units in the current Fight phase, then remove every physical component from the battlefield and create one canonical Strategic Reserves `ReserveState` with source evidence. Grey Knights Gate of Infinity uses the same grouped mutation, with one required-arrival reserve state for the selected attached rules unit in the next Grey Knights Movement phase. Accepted decline or complete selections emit a replay-safe event and do not mutate battlefield or reserve state. Webway Pathstone records a used event once per battle for the enhanced unit and does not offer another decision after use. Fade to Darkness records a use or decline event for the current Fight phase and does not offer another decision for that unit in the same phase. Gate of Infinity records each selected rules unit and re-emits the request until the battle-size cap is exhausted, the Grey Knights player chooses `complete`, or no eligible unit remains. Catalog IR Hunters from the Warp is not once-per-battle in the source text, so it may be offered again in a later eligible opponent turn after the unit returns and becomes eligible.

Every during-battle ability or generic RuleIR Stratagem removal now carries one typed `PrimaryReserveEntryProvider`. Its public payload binds the provider kind and ID, player, executed source rule, canonical target rules-unit ID, accepted decision record/request/result IDs, optional Stratagem-use ID, and the real source terminal event type. The engine re-authenticates that provider against the live accepted `DecisionRecord` immediately before mutation. A provider payload, event-log reference, display name, or self-consistent copied evidence rows cannot authorize removal without that exact accepted decision and its source-owned evidence. The accepted source owner also binds its immutable terminal fields: catalog record and target for catalog IR, Enhancement or Datasheet ability identity for faction abilities, all component IDs for attached Gate of Infinity units, and the request-captured destroyed-enemy witness for Fade to Darkness.

The public event graph is ordered and replay-closed in both directions. Ability removals always record the accepted `decision_requested` and `decision_recorded` pair, the source owner's used event with exactly one `primary_reserve_entry_bindings` row, and finally `primary_reserve_entry_provider_resolved`. When matched-play Primary history is active, that same occurrence also records `primary_reserve_entry_mutated` and `primary_battlefield_departure_recorded`; those two Primary evidence rows are not fabricated for a lifecycle without mission-backed Primary tracking. Generic RuleIR Stratagem removals additionally require the exact accepted catalog/context/target/effect selection, persisted `StratagemUseRecord`, `stratagem_used`, one matching `rule_execution_effect_applied` event, and the generic RuleIR source terminal before provider resolution. Catalog-backed Ability and Stratagem records and their complete effect payloads must equal the owning player's active runtime catalogs; Webway Pathstone and Fade to Darkness instead bind to their Enhancement assignments, while Gate of Infinity binds to its Datasheet ability registration. Replay-carried decision and use rows cannot authenticate a coordinated rewrite of source authority. Restore rejects missing, duplicated, reordered, cloned, orphaned, or conflicting provider, mutation, derived-departure, source-terminal, and provider-terminal rows; it also rejects target-set, component-set, catalog, source, RuleIR clause/effect, arrival requirement, reserve-state, or terminal-binding drift.

All during-battle reserve origins are reverse-closed, but they do not pretend to share one provider shape. Ordinary turn-end `DURING_BATTLE_ABILITY` and `DURING_BATTLE_STRATAGEM` removals resolve through the typed provider chain above. Cult Ambush is a bespoke `DURING_BATTLE_ABILITY` occurrence that instead resolves through its accepted resurgence decision, destroyed-model and starting-strength evidence, and exact resource-spend transaction. Aircraft `DURING_BATTLE_OTHER` entries resolve through their accepted movement decision and exact battlefield transition. An unregistered `DURING_BATTLE_OTHER` state or a syntactically self-consistent state without its route-specific authority is invalid.

An existing `IN_RESERVES` or `DESTROYED` state rejects another removal. A unit whose prior state is `ARRIVED` may enter again when a new source-backed opportunity is legal; the engine replaces that terminal state with a fresh occurrence, new entry timing, and new departure evidence. Every repeated entry requires exactly one intervening accepted reinforcement-placement decision and arrival event. A current `ARRIVED` state must match its accepted placement and transition, while a current `DESTROYED` state must match its mission-owned reserve-deadline destruction. Required arrival timing and placement authority come only from the registered source provider, while the reserve destruction-deadline policy comes only from the active mission. Adapters must not preserve or copy an earlier occurrence's arrival/deadline fields into a later one.

An attached rules unit retains its one canonical `ReserveState` after arrival even when a Bodyguard, Leader, or Support component is destroyed. The original provider-backed occurrence, arrival fields, aggregate points, and embarked-cargo evidence remain bound to the attached rules-unit ID; no component ReserveState rows or transfer event are created. Restore rejects a missing canonical row, any component-row replacement, obsolete split-transfer events, or drifted entry evidence.

Malformed, stale, wrong-actor, wrong-phase, wrong-hook, unsupported-option, option-payload drift, source-record drift, already-used when the source is once-per-battle, exhausted-cap, attached component drift, missing Gate of Infinity ability on any Grey Knights component, already-in-reserves, unplaced, or Engagement Range submissions reject before unauthorized mutation.

Turn-end faction-rule choices, roster identities, battlefield positions, reserve states after Declare Battle Formations resolves, objective witnesses, destruction attribution, and the historical events described here are public table information. Some current-state facts appear directly in `GameView`; event-time witnesses and attribution appear in the public event stream. Player and administrator viewers receive the same evidence identities. The secrecy boundary is the unresolved Declare Battle Formations choice and declaration state, whose pending requests, options, records, projections, and event deltas remain viewer-scoped until revealed by normal play.

Required Phase 17G turn-end faction-rule tests:

- valid Webway Pathstone use and decline choices through `FiniteOptionSubmission -> DecisionResult -> GameLifecycle.submit_decision(...)`;
- valid Fade to Darkness use and decline choices through the shared turn-end `DecisionRequest` / `DecisionResult` hook path;
- valid Grey Knights Gate of Infinity use and complete choices through the shared turn-end `DecisionRequest` / `DecisionResult` hook path;
- valid Genestealer Cults Cult Ambush marker ingress and decline choices through the shared turn-end `DecisionRequest` / `DecisionResult` hook path;
- valid catalog IR Hunters from the Warp use choice through the shared turn-end hook path;
- once-per-battle and once-per-turn request gating;
- Grey Knights battle-size cap, required next-Movement arrival, and attached rules-unit component validation;
- Fade to Darkness destroyed-enemy marker and Engagement Range request gating;
- Strategic Reserves state and battlefield removal are replay-safe and source-backed;
- malformed, stale, wrong-context, and ineligible submissions reject before unauthorized mutation;
- viewer-scoped projection/event redaction for any future hidden turn-end faction-rule selections.

## Phase 17G Stratagem-Cost Modifier Decisions

Phase 17G exposes opt-in Stratagem-cost modifier decisions for faction runtime content and source-backed generic catalog RuleIR. These decisions are emitted only after a player submits a Stratagem use or Stratagem target proposal and before the original Stratagem spends CP or mutates game state. Current implemented hooks include Aeldari Corsair Coterie Archraider Lord of Deceit and generic own-cost reductions or opponent-cost increases represented by `MODIFY_COMMAND_POINTS` with `operation: "modify_stratagem_cost"` and `application_scope: "current_stratagem_use"`. Under `gw-11e-core-rules:stratagems:unnamed-zero-cp-cost-update`, source wording that permits targeting a friendly unit with an unnamed Stratagem for 0CP compiles to a current-use `delta: -1` modifier; wording that names the Stratagem is not reinterpreted and retains its source-specific 0CP semantics.

The finite decision type is `select_stratagem_cost_modifier_option`. All pending request payloads contain game ID, battle round, active player ID, phase, source rule ID, hook ID, modifier ID, Stratagem ID, Stratagem player ID, primary target unit ID, source decision request ID, source decision result ID, and a replay-safe copy of the source decision result. Named-content requests may add enhancement and eligible-model fields. Generic catalog requests add source record ID, source clause ID, opportunity ID, source unit ID, source model ID, and `target_unit_instance_ids`: the deterministic canonical rules-unit identities derived from the primary target binding and every supported structured `effect_selection` target. Generic option payloads and resolution events carry the same target-ID set, and restored or malformed results must match it exactly. Range- and source-unit relationships succeed when any same-army target in that set satisfies the source-backed predicate. Adapters answer by selecting one emitted option ID. Current Lord of Deceit options use:

- `aeldari:corsair-coterie:archraider:<source_decision_result_id>:<target_unit_instance_id>:use`;
- `aeldari:corsair-coterie:archraider:<source_decision_result_id>:<target_unit_instance_id>:decline`.

Option payloads include `submission_kind: "aeldari_corsair_coterie_lord_of_deceit_cost_choice"`, player ID, source rule ID, hook ID, modifier ID, enhancement ID, target unit ID, source decision request ID, source decision result ID, and `use_ability`. Adapters must not spend CP, alter a Stratagem's cost, or resolve the original Stratagem locally while this decision is pending.

Generic catalog option IDs use `catalog-ir:stratagem-cost:<source_decision_result_id>:<opportunity_id>:use` or `:decline`. Their option payloads use `submission_kind: "catalog_ir_stratagem_cost_choice"` and carry player, source rule/record/clause, hook, modifier, opportunity, source unit/model, primary target unit, canonical target-unit set, source decision request/result, and `use_ability` fields. The opportunity and modifier identities are derived from the source-backed catalog record and must not be invented by an adapter.

Accepted use selections record a source-result-scoped cost-choice event. The lifecycle emits additional eligible cost-choice requests sequentially for the same original Stratagem use until every optional source has been answered. It then reconstructs and revalidates the original Stratagem decision against the same engine validation path with the Stratagem-cost modifier registry active. If still valid, the original Stratagem spends the modified CP cost, records modifier provenance on the `StratagemUseRecord`, mutates through the normal Stratagem handler, and resumes the original reaction frame. If a selected cost increase makes the final cost unaffordable, the engine spends no CP and applies no handler or effects, but records the Stratagem as used for phase restrictions with `effects_resolved: false`, `unresolved_reason: "insufficient_command_points_after_cost_increase"`, no CP transaction ID, and the selected modifier provenance; it emits both `stratagem_used` and `stratagem_effects_not_resolved` before resuming the original reaction frame. Initial submissions that are already unaffordable before any selected cost increase remain invalid and create no use record. Accepted decline selections record a decline event and continue that sequence without applying the declined modifier. A modifier with no source duration is scoped only to that source decision result/current Stratagem use, and the registry floors the final cost at 0CP.

Malformed, stale, wrong-actor, wrong-hook, unsupported-option, source-request drift, source-result drift, source record/clause/opportunity drift, source unit/model drift, option-payload drift, exhausted frequency, unavailable source model, out-of-range source, already-used-this-turn, or wrong-target-owner submissions reject before the original Stratagem mutates.

Stratagem-cost modifier choices are public table information in the current Phase 17G rules scope. If a future cost modifier is hidden, pending requests, source decision result copies, option lists, decision records, Stratagem use records, events, projections, and event deltas must be viewer-scoped and must not leak hidden opponent information through option counts, target IDs, source context, cost provenance, selected payload, or derived engine values.

Required Phase 17G Stratagem-cost modifier tests:

- valid Lord of Deceit use and decline choices through `FiniteOptionSubmission -> DecisionResult -> GameLifecycle.submit_decision(...)`;
- valid generic catalog own-cost reduction and opponent-cost increase choices;
- unnamed 0CP friendly-unit wording reducing the current use by 1CP while named 0CP wording is not reinterpreted;
- sequential resolution of multiple optional sources for one original Stratagem use;
- source decision result round-trip and original reaction-frame resume;
- modified CP spend, 0CP floor, current-use-only scope, and `StratagemUseRecord` provenance after accepted use;
- selected cost increases that become unaffordable spend no CP, resolve no effects, and still create deterministic used-this-phase records;
- malformed, stale, wrong-context, drifted, already-used, and ineligible submissions reject before unauthorized mutation;
- viewer-scoped projection/event redaction for any future hidden Stratagem-cost modifier selections.

Catalog command-point gains do not introduce a separate adapter choice. Supported generic RuleIR currently covers a source model destroying an enemy keyword-gated unit and explicit owner-phase-start/end gains with no roll, a fixed D6-family threshold, or a Leadership test while the source model is alive and on the battlefield. The engine owns all rolls, CP cap enforcement, ledger mutation, and replay events. Every authoritative `model_destroyed` event carries `destroying_player_id`, nullable `source_rules_unit_instance_id`, nullable `attacking_unit_instance_id` and `attacking_model_instance_id`, plus the typed `destruction_provenance` described above. It also carries event-time `source_rules_unit_objective_proximity_witness` and `destroyed_rules_unit_objective_proximity_witness` values with canonical rules-unit identity, physical component IDs, and exact objective-marker/model witnesses. Attack provenance requires both attacking identities and uses the attacking rules-unit identity as the source identity. Non-attack provenance forbids attack identities; `source_rules_unit_instance_id` is populated only when the engine has an authoritative ability, Hazardous, or Deadly Demise source rules unit, and remains null otherwise. Destruction consumers must parse provenance before reading attack-only fields and must ignore unattributed non-attack destructions instead of inferring an attacker from the current phase or event family. Source and destroyed objective-proximity witnesses are public event-time battlefield facts after Declare Battle Formations is revealed, so player and administrator event streams receive identical typed evidence. This does not expose still-unrevealed Declare Battle Formations choices. Adapters must not award CP, roll a test, infer the attacker, alter the recorded proximity, or bypass the per-battle-round gain cap locally.

## Phase 17G Battle-Round Faction-Rule Decisions

Phase 17G also adds opt-in battle-round start decisions for faction runtime content. These decisions are emitted only when the mustered army's faction runtime contribution registers a battle-round start hook for the player and the game is at the start of a battle round before the first player's Command phase proceeds. Current implemented hooks include World Eaters Blessings of Khorne, updated from the 11th Edition faction-pack `RULES UPDATES` section, Black Templars Templar Vows, which replace the Space Marines army rule for Black Templars armies, Chaos Knights Harbingers of Dread, and Adepta Sororitas Triumph of Saint Katherine Relics of the Matriarchs.

Phase 17G exposes the finite decision type `select_faction_rule_battle_round_option`. The pending request payload contains game ID, battle round, phase `command`, faction ID, source rule ID, hook ID, effect kind, and target unit IDs. Source-specific payload fields include Blessings roll state, dice values, base dice count, spent Bloodshed points, and rule-update source IDs for World Eaters, active/available Dread ability IDs for Chaos Knights, source-backed Shadow Form metadata for Be'lakor, and Triumph source unit/model plus source-backed DAMAGED ability-selection cap metadata for Adepta Sororitas. Adapters answer by selecting one emitted option ID and must not reroll dice, invent blessing, vow, Dread ability IDs, Shadow Form source IDs, Triumph relic IDs, spend Bloodshed points locally, or apply effects locally.

Current World Eaters option IDs use the form `world_eaters:blessings:<blessing_id>` for one blessing, `world_eaters:blessings:<blessing_id>+<blessing_id>` for two legal blessings with disjoint dice allocations, and `world_eaters:blessings:none` when the player selects no blessing. Option payloads include `submission_kind: "select_world_eaters_blessings"`, player ID, battle round, faction ID, source rule ID, hook ID, effect kind, selected blessing IDs and labels, dice values, consumed dice indices by blessing ID, spent Bloodshed points, and rule-update source IDs.

Current Black Templars option IDs use the form `black_templars:templar_vows:<vow_id>`. Option payloads include `submission_kind: "select_black_templars_templar_vow"`, player ID, battle round, faction ID, source rule ID, hook ID, effect kind, selected vow ID and label, and a JSON-safe effect summary. Accepted choices create one end-of-battle Templar Vows `PersistingEffect` consumed by the Charge, Fight, Fall Back, and phase-end objective-control hosts.

Current Chaos Knights option IDs are `chaos_knights:harbingers_of_dread:roll` for the engine-owned 2D6 random selection and `chaos_knights:harbingers_of_dread:<dread_ability_id>` for one manually selected available Dread ability. Option payloads include `submission_kind: "select_chaos_knights_harbingers_of_dread"`, player ID, battle round, faction ID, source rule ID, hook ID, effect kind, state kind, active Dread ability IDs, available Dread ability IDs, selection mode, selected Dread ability IDs and labels for manual selections, and the Chaos Knights Darkness rules-update source. The roll option does not include dice values in the submission payload; accepted roll selections roll two D6 through the engine dice manager and record the dice in the accepted state/event.

Current generic catalog Shadow Form option IDs use the form `catalog-shadow-form:<source_id_hash>`. Request payloads include `submission_kind: "catalog_shadow_form_selection"`, hook ID, game ID, battle round, phase, player ID, active player ID, source unit instance ID, source catalog record ID, source ability ID, source RuleIR ID/hash, and available Shadow Form source IDs. Option payloads include `submission_kind: "catalog_shadow_form_selection"`, hook ID, battle round, source unit instance ID, selected Shadow Form source ID, selected RuleIR hash, selected catalog record ID, and selected ability ID. Accepted selections record one source-unit selection effect, execute the selected source-backed RuleIR through the generic runtime path, record any resulting persisting effects, and emit `catalog_shadow_form_selected`.

Current Adepta Sororitas Triumph Relics option IDs use the form `triumph-relics-none` or `triumph-relics-<relic_id>-<relic_id>`. Request payloads include `submission_kind: "adepta_sororitas_relics_of_the_matriarchs"`, hook ID, game ID, battle round, phase, player ID, active player ID, source unit/model IDs, selected source rule ID, available relic IDs, and the catalog DAMAGED selection-limit fields `damaged_effect_id`, `damaged_effect_source_id`, `damaged_profile_active`, `max_selections`, `baseline_max_selections`, and `selection_group`. Option payloads include the selected relic IDs and selected relic source rule IDs. Accepted selections record one `FactionRuleState`, one source-unit persisting selection effect through the next battle-round start, source-backed battle-shock reroll permission for Censer of the Sacred Rose, dynamic movement/Advance/charge/melee AP aura consumers for The Fiery Heart and Petals of the Bloody Rose, unit-scoped Acts of Faith phase-limit checks for Simulacrum of the Ebon Chalice, explicit Feel No Pain source sync for Icon of the Valorous Heart, and a source-backed ranged wound-reroll permission for Simulacrum of the Argent Shroud.

Accepted World Eaters selections create a deterministic `PersistingEffect` with effect kind `world_eaters_blessings_of_khorne` through the end of the current battle round and emit `world_eaters_blessings_of_khorne_selected`. Later phase/query hosts consume that effect through generic runtime surfaces: Unbridled Bloodlust grants +1 to Charge rolls per the 11th Edition update, Rage-fuelled Invigoration offers a fight-activation ability for 6" Pile-in/Consolidation moves, Martial Excellence/Warp Blades/Decapitating Strikes modify melee weapon profile keywords, and Total Carnage registers optional fight-on-death destruction reactions with the engine-owned 4+ trigger roll. Total Carnage destruction-reaction descriptors are self-invalidating: the attack-sequence trigger gate requires the descriptor battle round to match current state and requires the current active Blessings `PersistingEffect` to still contain Total Carnage.

The 11th Edition Icon of Khorne update is represented as Bloodshed points. When a World Eaters unit destroys an enemy unit, the engine grants the next Blessings roll one additional D6 only if the destroying unit had a live Icon of Khorne bearer when the enemy unit destruction completed. Bloodshed points are spent into the next Blessings request and then consumed by that request payload; adapters must render this as engine-derived state, not calculate it from static selected wargear.

Accepted Chaos Knights selections create a deterministic `FactionRuleState` with state kind `chaos_knights_harbingers_of_dread_selection` and emit `chaos_knights_harbingers_of_dread_selected`. Deathly Terror is always active; selected or rolled Dread abilities accumulate across battle rounds 1, 3, and 5. Later hosts consume the state only through shared engine hooks: Deathly Terror and Despair worsen Leadership in the live aura, Dismay adds forced below-starting Battle-shock tests in the opponent Command phase, Delirium applies engine-owned D3 mortal wounds after failed Battle-shock, Doom adds 1 to wound rolls against Battle-shocked units, and Darkness applies the 11th Edition update as a ranged hit-roll Stealth penalty against Chaos Knights models.

Malformed, stale, wrong-actor, wrong-faction, duplicate-selection, unsupported-option, active/available Dread drift, Shadow Form source/hash/record drift, Triumph source/damaged-limit drift, and option-payload drift submissions reject before the pending queue is popped and before a `DecisionRecord`, `FactionRuleState`, persisting effect, destruction-reaction source, or event is created.

Faction-rule battle-round choices are public table information in the current Phase 17G rules scope. If a future faction rule hides battle-round selections, pending requests, option lists, decision records, persisting effects, events, projections, and event deltas must be viewer-scoped and must not leak hidden opponent information through option counts, source context, selected payload, dice values, Bloodshed counts, or derived engine values.

Required Phase 17G battle-round faction-rule tests:

- valid battle-round faction-rule selection through `FiniteOptionSubmission -> DecisionResult -> GameLifecycle.submit_decision(...)`;
- no-selection choices record that the battle-round hook was resolved and are not requested again in the same round;
- deterministic JSON-safe decision, persisting-effect, event, lifecycle, and replay payload round-trip;
- live model-borne wargear evidence gates Bloodshed point awards;
- Harbingers of Dread records cumulative Dread state and reaches Leadership, Battle-shock, hit-roll, wound-roll, and mortal-wound consumers;
- Triumph Relics options honor the source-backed DAMAGED ability-selection cap and reject stale damaged-limit drift;
- at least one real consumer path proves each newly wired engine area;
- viewer-scoped projection/event redaction for any future hidden battle-round faction-rule selections.

## Phase 17G Command-Start Faction-Rule Decisions

Phase 17G also adds opt-in Command phase start decisions for faction runtime content. These decisions are emitted only when the mustered army's faction runtime contribution registers a Command phase start hook for the current Command phase window; most hooks are active-player choices, while Tyranids Shadow in the Warp and source-backed opponent-Command self-ability choices can be emitted for the non-active player. The lifecycle's generic `START_PHASE` dispatch is the outer boundary. Every synchronous Command-start hook, Command-start effect, and finite Command-start choice then resolves through one resumable engine-owned boundary before either player gains Core CP. A pending Command-start choice leaves both players' Core CP and all existing Battle-shock state unchanged. After `GameLifecycle.submit_decision(...)` accepts an engine-emitted option, the lifecycle auto-advances to the next Command-start request or to boundary completion. Only final boundary completion grants both players 1CP exactly once and then emits `command_step_started`; scoring and other Command-step work remain after that event and do not clear Battle-shock.

On first entry to the later 08.03 Battle-shock step, the engine enumerates every living canonical rules unit owned by the active player, including units with no battlefield placement, and snapshots eligibility rather than future rolls. Each candidate row pins the canonical rules-unit ID, component unit IDs, whether the unit was Battle-shocked at the boundary, its exact eligibility reasons, forced-test provider rows, and its step-start strength context. A unit that satisfies more than one predicate still receives one required test, with a forced-below-Starting-Strength reason taking precedence when applicable. The public `battle_shock_step_snapshot_created` event pins the game, round, active player, Command phase, phase-start Battle-shocked canonical unit IDs, and that complete candidate inventory; it contains no precomputed `BattleShockTestRequest`. Before the first test, the off-battlefield gate checks every required candidate. On later entries it excludes the exact completed prefix and checks only the current in-flight and other uncompleted candidates. Attached Unit component aliases continue to resolve to the original canonical ID, and living-placement checks use the living models from that retained formation. If a checked candidate is not on the battlefield, the lifecycle returns typed `unsupported` with source rule `gw-11e-core-rules:command-phase:battle-shock`, section `08.03`, canonical and component unit IDs, candidate reasons, and `unsupported_scope: "off_battlefield_battle_shock_test"`. It does not resolve the step. P01 remains responsible for implementing those off-battlefield tests, but the current partial implementation never treats them as successful omission.

When two or more candidates require tests, 08.03 reuses finite decision type `resolve_sequencing_order` with `payload.sequencing_model: "select_next_participant"`. The request actor is the active player. Each participant ID is `command-battle-shock-test:<canonical_rules_unit_id>`, its public payload is the exact candidate snapshot row, and each request emits exactly one `next:<participant_id>` option per remaining candidate. The payload pins `previously_selected_participant_ids`; every option pins that same prefix, the complete current `remaining_participant_ids`, and one selected participant. The timing descriptor is `command-battle-shock-test-order`, source rule `gw-11e-core-rules:command-phase:battle-shock`, phase `command`, source step `battle_shock`, and metadata `candidate_scope: "required_command_battle_shock_tests"`. After the selected candidate's complete result and any nested outcome continuation, the engine emits the next bounded request from current authority. The final sole remaining candidate is deterministic and needs no choice. Thus `N` candidates expose at most `N` options in one request and require `N-1` selections, never `N!` permutation options. Adapters submit one emitted next-participant option through `GameLifecycle.submit_decision(...)`; they must not sort unit IDs locally, invent an order, alter either participant prefix, or begin rolling an unselected candidate. Zero- and one-candidate cases require no sequencing choice.

After each next-participant selection, the engine materializes that candidate's `BattleShockTestRequest` from current authoritative state immediately before rolling. Dice expression, Leadership, alive model composition, attached-unit identity, and strength context are therefore recomputed after every earlier result and outcome continuation. Only that current request is stored as `battle_shock_in_flight_test_request`, including across optional reroll or nested-decision pauses; future requests are not serialized. Completion clears the in-flight request and appends its deterministic request ID to the completed prefix before another candidate can be selected. A successful required test clears carried phase-start Battle-shock; a failed test preserves or applies it through the shared Battle-shock outcome path. Public event `battle_shock_modifier_applications_recorded` pins the same source-context fields and exact live request plus an ordered `battle_shock_modifier_applications` list. Each row contains the loaded producer `hook_id`, actual modifier `source_id`, and exact ordered serialized modifiers attributed to that producer/source pair; rows sort by `(hook_id, source_id)`, and modifier IDs are globally unique for the test. Each public `battle_shock_test_resolved` payload carries `state_update` plus `cleared_battle_shocked_unit_ids`; the public `battle_shock_step_completed` event pins the exact ordered completed request IDs and results. Restore validates every bounded selection request/event/record, selected and remaining prefixes, current in-flight request, completed prefix, dice, optional reroll, modifier source, resolved result, auto-pass, state update, and Command-step anchor. Adapters must not construct or alter the snapshot, accumulated sequencing prefix, live request, Attached Unit identity, dice, result, or Battle-shock mutation.

P19 preserves the original Attached Unit ID, `StartingStrengthRecord`, `StartingAttachedUnitRecord`, Battle-shock row, ReserveState, persisting effects, Action history, and adapter-visible identity until the last model that started in that rules unit is destroyed. Dead components remain in explicit immutable component lineage but contribute no living models, keywords, abilities, or battlefield placement. The obsolete `attached_rules_unit_split_reconciled`, `battle_shock_state_transferred_after_attached_unit_split`, and `reserve_state_transferred_after_attached_unit_split` events are not emitted and are rejected by restore paths that own those histories. Adapters must not derive component survivors, invent component state rows, rewrite the canonical ID, or locally transfer state. This changes no player-facing decision type, option family, proposal kind, payload visibility rule, or replay schema.

An optional Battle-shock reroll continues to use finite decision type `select_dice_reroll` and its existing option IDs, but P08B extends `payload.battle_shock_context` with required fields `passed_state_policy` and `additional_modifier_applications`. The only policy tokens are `preserve` for forced tests whose success must not clear an existing status and `clear_if_step_start_shocked` for the required 08.03 Command-step test. `additional_modifier_applications` is a canonical sorted array of source-producer rows; each row contains exact `hook_id`, `source_id`, and a non-empty canonical `modifiers` array using the existing `RollModifier` payload. An empty array is required when the source producer contributes no modifier outside the loaded Battle-shock hook registry. The context also carries the source kind, game/round/phase/active-player identity, exact Battle-shock request and initial roll state, phase-start Battle-shocked unit IDs, resolved-event types, and base result payload. Adapters must submit one emitted reroll option without changing any context field or nested application/modifier row. Before queue pop or `DecisionRecord` creation, lifecycle validation requires the exact source occurrence, loaded provider and permission, request semantics, initial roll, base payload, resolved-event inventory, and complete modifier applications. Command additionally requires the Battle-shock step, exact persisted in-flight request, ordered candidate identity, and exact completed-result prefix. Malformed, stale, reordered, omitted, inserted, or drifted context returns a typed invalid status without consuming the pending request or mutating Battle-shock.

After a required test resolves, an outcome hook may enqueue an existing nested decision such as Healing Wounds model selection or revival placement. That queue head preempts the next ordered candidate: Command records the completed-test prefix, returns the exact nested pending request, and does not materialize or roll the next required test until the nested path finishes through its own lifecycle contract. Adapters must answer the pending queue head and must not reorder a Battle-shock reroll behind it or locally resume the Command loop.

The existing `select_faction_rule_command_phase_start_option` decision type, option IDs, payload shapes, validation path, and viewer-visibility behavior are unchanged. The current implemented hooks include Space Marines Oath of Moment, Necrons Reanimation Protocols, Orks Waaagh!, Astra Militarum Voice of Command, Imperial Knights Bondsman, Tyranids Shadow in the Warp, and the generic `catalog-ir:command-phase-ability-mode` consumer.

Phase 17G exposes the finite decision type `select_faction_rule_command_phase_start_option`. The pending request payload contains game ID, battle round, phase `command`, active player ID, player ID, faction ID when applicable, source rule ID, hook ID, effect kind or generic selection kind, any explicit `actor_may_be_non_active` flag, and the eligible target, rules-unit, source model/ability, source unit, or enemy unit IDs for that hook. Adapters answer by selecting one emitted option ID and must not invent target IDs, rules-unit IDs, source model IDs, ability IDs, source unit IDs, enemy unit IDs, mutation payloads, reroll permissions, healing choices, Battle-shock tests, or wound modifiers locally.

Catalog selectable-ability-mode requests use `submission_kind: "catalog_command_phase_ability_mode"`, hook ID `catalog-ir:command-phase-ability-mode`, and `actor_may_be_non_active: true`. The request carries the source catalog record, RuleIR source/hash, source rules-unit/component/model IDs, parent clause ID, and `available_mode_source_rule_ids`. Each deterministic option carries its source row/rule ID, display name, and semantic descriptor. Accepted selections create an engine-owned effect until the start of the same opponent's next Command phase; generic engine consumers apply the selected defensive Hit modifier, Fights First grant, or Fall Back Leadership-test aura. Adapters must not infer modes from display names, apply modifiers, run Leadership tests, deny movement, or expire mode state locally.

Command-start persistent-status damage, including `catalog-ir:poisoned-command-mortal-wounds`, creates no additional adapter selection. The engine enumerates each distinct poisoned rules unit on the battlefield, rolls its trigger and D3 mortal wounds through the deterministic dice manager, routes any Feel No Pain choices through the existing `select_feel_no_pain` contract, and records replay-safe pending/resolved events before Command scoring or later Command choices continue. Adapters must not enumerate status effects, combine duplicate status sources, roll damage, allocate mortal wounds, or bypass the existing Feel No Pain request.

Aeldari Spiritseer's Tears of Isha uses that shared Command-start finite surface
with `selection_kind: "catalog_command_restoration"`. Each option binds the
source catalog record, source rule and RuleIR hashes, clause, source
rules-unit/unit/model IDs, and one engine-enumerated friendly WRAITH CONSTRUCT
rules unit within 6 inches. The lifecycle recomputes the option before queue pop
and rejects a stale source, out-of-range target, wrong keyword, wrong player, or
target already selected for this ability during the turn. After acceptance the
engine uses the shared healing path: if the target has a destroyed model that
was removed from the battlefield, it returns one model at full wounds with an
engine-validated placement; otherwise it rolls D3 and restores lost wounds to
one wounded model. Any nested model or placement choice remains an ordinary
healing `DecisionRequest`. The selected event records the source identity, D3
result when applicable, healing effect, and pending nested request ID. Adapters
must not choose the restoration branch, roll the D3, select or place a model,
or mutate wounds locally.

Current Space Marines option IDs use the form `space_marines:oath_of_moment:<target_unit_instance_id>`. Option payloads include the common request payload plus `target_owner_player_id`, `target_unit_instance_id`, and `target_unit_name`. The target list contains eligible live enemy units only. It is public table information in the current Phase 17G rules scope.

Accepted Space Marines selections create a deterministic enemy target `PersistingEffect` through the start of the selecting player's next Command phase and emit `space_marines_oath_of_moment_target_selected`. The engine also creates target-scoped source-backed Hit-roll reroll effects for eligible ADEPTUS ASTARTES attacker units. Later attack-sequence hosts expose the Hit-roll reroll only when the attack targets the active Oath target. The Wound-roll +1 is not adapter-computed: it is supplied by the runtime wound modifier only when the attacker is an ADEPTUS ASTARTES unit, the target is the active Oath target, the army is using a Codex: Space Marines Detachment, and the army does not include BLOOD ANGELS, DARK ANGELS, DEATHWATCH, or SPACE WOLVES units.

Current Necrons option IDs use the form `necrons:reanimation_protocols:<rules_unit_instance_id>`. Option payloads include the common request payload plus `rules_unit_instance_id`, `rules_unit_owner_player_id`, `rules_unit_name`, and `component_unit_instance_ids`. Attached units are exposed by attached rules-unit identity, not by a component `unit_instance_id`. Accepted Necrons selections roll the source-backed D3, create a `HealingEffect` targeting the selected rules unit, heal wounded models before reviving destroyed removed models, and may emit `select_healing_model` when multiple wounded or removed model choices are legal. The owning Necrons player is the healing selection actor for Reanimation Protocols.

Current Orks option IDs are `orks:waaagh:call` and `orks:waaagh:decline`. Option payloads include the common request payload plus `submission_kind: "orks_waaagh_call"` and `selected_waaagh_option` set to `call` or `decline`. Accepted call selections record a once-per-battle `FactionRuleState`, create a deterministic army `PersistingEffect` through the start of the Orks player's next Command phase, and emit `orks_waaagh_called`. The active effect is consumed only by shared engine hooks: Advance eligibility grants Charge declaration after Advance, melee weapon profiles gain +1 Strength and +1 Attack, and save options gain or improve to a 5+ invulnerable save. Accepted decline selections record only a current-Command-phase decline state and emit `orks_waaagh_declined`; they do not spend the once-per-battle call or create an active effect, and the request may appear again at a later eligible Command phase.

Current Astra Militarum option IDs use the form `astra_militarum:voice_of_command:<issuing_officer_unit_instance_id>:<order_id>:<ordered_rules_unit_instance_id>`, plus `astra_militarum:voice_of_command:done`. Option payloads include the common request payload plus `submission_kind: "astra_militarum_voice_of_command_issue"`, `selected_voice_of_command_option`, the issuing OFFICER unit, the ordered rules-unit identity and component unit IDs, the selected Order ID, and the normalized Orders profile metadata used to enumerate the option. Adapters must not invent Order IDs, officer IDs, ordered rules-unit IDs, target keywords, or modifier payloads. Accepted issue selections record an officer issue `FactionRuleState`, replace any prior active Order effect on the ordered rules unit, create a deterministic `PersistingEffect` through the start of the Astra Militarum player's next Command phase, and emit `astra_militarum_voice_of_command_order_issued`. Active Order effects are consumed only by shared engine modifiers: Move! Move! Move! adds 3" to movement budgets; Fix Bayonets! improves melee Weapon Skill; Take Aim! improves ranged Ballistic Skill; First Rank, Fire! Second Rank, Fire! adds 1 Attack to Rapid Fire weapons; Take Cover! improves armour save values no better than 3+; and Duty and Honour! improves Leadership and Objective Control. Battle-shock outcome hooks remove active Order effects from units that fail Battle-shock. Accepted done selections record only a current-Command-phase completion state and emit `astra_militarum_voice_of_command_done`.

Current Imperial Knights Bondsman option IDs use the form `imperial_knights:bondsman:<source_model_instance_id>:<bondsman_ability_id>:<target_armiger_model_instance_id>`, plus `imperial_knights:bondsman:done`. Option payloads include the common request payload plus `submission_kind: "imperial_knights_bondsman_application"`, `selected_bondsman_option`, source Bondsman unit/model IDs, target ARMIGER unit/model IDs, and the selected Bondsman datasheet ability ID/name/source ID. Accepted apply selections validate live battlefield range at 12", confirm the source model still has the selected Bondsman-tagged ability, confirm the target is a friendly ARMIGER model that is not already affected by Bondsman, record the source model/ability use for the current Command phase, create a deterministic model-scoped `PersistingEffect` through the start of the Imperial Knights player's next turn, and emit `imperial_knights_bondsman_applied`. Accepted done selections record only a current-Command-phase completion state and emit `imperial_knights_bondsman_done`.

Current Tyranids option IDs are `tyranids:shadow_in_the_warp:unleash` and `tyranids:shadow_in_the_warp:decline`. Option payloads include the common request payload plus `submission_kind: "tyranids_shadow_in_the_warp"`, `selected_shadow_option`, `source_unit_instance_ids`, `target_enemy_unit_instance_ids`, `actor_may_be_non_active: true`, and the Shadow/Synapse rules-update source. Accepted unleash selections record the once-per-battle `FactionRuleState`, immediately force each current enemy battlefield unit through the engine Battle-shock request/result path, apply the Shadow in the Warp -1 Battle-shock modifier when the target is within 6" of one or more friendly SYNAPSE models, and emit `tyranids_shadow_in_the_warp_unleashed`. Accepted decline selections record only the current Command-phase decline state and emit `tyranids_shadow_in_the_warp_declined`; they do not spend the once-per-battle unleash. Synapse 3D6 Battle-shock tests and melee +1 Strength modifiers are consumed later only through shared Battle-shock dice-expression and weapon-profile modifier hosts.

Malformed, stale, wrong-actor, wrong-game, wrong-round, wrong-phase, wrong-active-player, wrong-target-owner, self-target, missing target, destroyed target, wrong-rules-unit-owner, destroyed rules unit, Battle-shocked ordered unit, off-battlefield rules unit, missing Shadow source unit, missing Shadow enemy target, non-ARMIGER target, out-of-range Bondsman target, already-affected ARMIGER target, duplicate target or activation, unsupported-option, unsupported Order, exhausted officer Order count, wrong officer, wrong ordered rules unit, wrong Bondsman source model or ability, and option-payload drift submissions reject before the pending queue is popped and before a `DecisionRecord`, persisting effect, healing effect, reroll permission, modifier state, faction-rule state, Battle-shock result, or event is created.

If a future Command-start faction rule hides target or option information, pending requests, option lists, decision records, persisting effects, events, projections, and event deltas must be viewer-scoped and must not leak hidden opponent information through option counts, target IDs, source context, selected payload, or derived engine values.

Required Phase 17G Command-start faction-rule tests:

- valid Command-start faction-rule selection through `FiniteOptionSubmission -> DecisionResult -> GameLifecycle.submit_decision(...)`;
- target-scoped Hit-roll reroll permission and Codex Space Marines Detachment Wound-roll modifier consumer;
- Necrons Reanimation Protocols D3 healing, model revival, attached rules-unit identity, and owning-player healing selection;
- Orks Waaagh! call/decline, once-per-battle state, active effect expiry, Advance eligibility, melee profile, and invulnerable save consumers;
- Astra Militarum Voice of Command issue/done choices, structured Orders profile fail-fast behavior, active Order replacement, Battle-shock cleanup, and each Order modifier consumer;
- Imperial Knights Bondsman apply/done choices, friendly ARMIGER range filtering, already-affected target filtering, source model/ability use state, model-scoped effect expiry, and drift rejection;
- Tyranids Shadow in the Warp unleash/decline choices, non-active actor validation, once-per-battle state, forced enemy Battle-shock tests, Synapse 3D6 Battle-shock tests, Shadow Synapse-range penalty, and Synapse melee Strength modifier;
- malformed, stale, wrong-context, wrong-owner, self-target, destroyed-target, destroyed-rules-unit, and drifted submissions reject before mutation;
- deterministic JSON-safe decision, persisting-effect, event, lifecycle, and replay payload round-trip;
- viewer-scoped projection/event redaction for any future hidden Command-start faction-rule selections.

## Phase 16E Setup Completion Gate

Phase 16E does not add a new adapter-submitted decision type. Setup completion is an engine-owned lifecycle gate that runs only after setup decisions and proposal requests, including registered start-battle hooks, have drained and the ruleset setup sequence reaches its final step. Start-battle hooks use their rule's ordinary registered finite decision type; adapters must not submit a synthetic "start battle" result, force `GameState.enter_battle()`, mutate `setup_step_index`, or bypass `GameLifecycle.advance(...)`.

The gate audits the pending decision queue, reaction queue, final setup-step position, mustered armies, source-backed mission setup, Secondary Mission choices, Attacker/Defender state, battle formation declarations, reserve legality, deployment completion, battlefield coherency, redeploy state, and pre-battle actions. If any check fails, lifecycle advancement returns a typed invalid status with `invalid_reason: "setup_completion_gate_failed"` and a `setup_legality_report`; the pending queue is not popped, no `DecisionRecord` is created for battle start, and authoritative state remains in setup.

When setup is legal, lifecycle advancement emits `setup_completion_gate_passed` and `battle_started` events. The `battle_started` event payload is a `BattleStartRecord` containing the completed setup step, source ID, readiness snapshot, setup legality report, pre-battle checkpoint, post-battle-start checkpoint, battle round, active player, first battle phase, turn order, and ruleset descriptor hash. These payloads are JSON-safe replay data; they must not include Python object reprs, memory addresses, or adapter-local state.

Setup completion data is public table setup information in the current Phase 16E rules scope. If a future mission, deployment, reserve, or pre-battle rule hides setup information, invalid diagnostics, event deltas, projections, setup legality reports, replay checkpoints, and battle-start records must remain viewer-scoped and must not leak hidden opponent information through counts, option lists, source context, model IDs, reserve state, or derived readiness fields.

Required Phase 16E adapter-contract tests:

- full setup-to-battle advancement occurs only through lifecycle advancement after the pending setup decisions drain;
- direct setup-step bypass, pending decision queue entries, unresolved setup work, and bridge-only placement paths return typed invalid diagnostics and leave state in setup;
- legal setup emits deterministic `setup_completion_gate_passed` and `battle_started` event payloads with JSON-safe `SetupLegalityReport`, `SetupReplayCheckpoint`, and `BattleStartRecord` data;
- lifecycle/replay payload round-trip preserves the battle-start record;
- viewer-scoped projection/event redaction for any future hidden setup completion information.

## Catalog Tracked-Target Decisions

Catalog tracked-target RuleIR uses the finite decision type `select_tracked_target`.
The engine emits this request for supported prey/quarry target-selection clauses
at the final start-battle setup boundary for start-of-battle clauses, at
battle-round start for round-start clauses, and for supported destroyed-target
replacement clauses when the active tracked target is destroyed. Adapters answer
only by selecting one pending option ID; the option ID is exactly the target unit
instance ID.

The request and option payloads include `submission_kind: "select_tracked_target"`,
source rule/ability/clause/effect identity, `owner_scope` (`this_model` or
`this_unit`), `tracked_target_role` (`prey` or `quarry`),
`supported_attack_roll_pairs` as the authoritative attack-kind/roll-type
permission list, convenience projections `supported_attack_kinds` (`melee`,
`ranged`, or both) and `supported_roll_types`, target allegiance and scope,
`replacement`, deterministic `legal_target_unit_ids`, source unit ID, and
optional source model ID. Adapters must not create tracked-target records,
expire records, infer replacement targets, or apply rerolls locally from option
payloads.

Accepted selections create a replay-safe `TrackedTargetRecord`. Replacement
selections expire the previous active record for the same source/unit/model
scope/role and record the replacement target. Attack-sequence rerolls are exposed
only through the existing source-backed reroll decision path after the engine
confirms the attacking model or unit matches the tracked-target owner scope and
the exact `(attack_kind, roll_type)` pair and target unit match the active
tracked-target record.

Malformed, stale, wrong-actor, non-option, option-payload drift, source drift,
destroyed-target, target-legality drift, duplicate-active, or unsupported-shape
submissions reject before mutation and do not pop the pending request. Current
tracked-target choices are public table information; any future hidden target
selection must add viewer-scoped pending requests, records, projections, and
event deltas before becoming adapter-visible.

Required tracked-target tests cover JSON-safe request payloads, valid selection,
invalid non-option selection, model-scope and unit-scope reroll gates, destroyed
target expiry, deterministic reselection, replay payload round-trip, and catalog
consumer/hook IDs.

## Catalog Model Materialization Decisions

Source-backed `MATERIALIZE_MODELS` RuleIR resolves model-destruction timing and
the engine-owned dice gate before exposing physical placement. A successful
gate emits the parameterized decision type
`submit_catalog_model_materialization_placement` with one fixed
`submit_parameterized_payload` option. The request is actor-scoped to the owning
player and includes `proposal_kind: "model_materialization_placement"`,
`placement_kind: "split_unit"`, the immutable Shooting or Fight `action_phase`,
the current `parent_battle_phase` (also retained as placement `source_phase`),
attack-sequence and roll-event IDs, catalog
record/clause/source-rule identity, the physical owning unit and army IDs, the
materialization descriptor ID, and the complete engine-instantiated model
payloads and model IDs.

Adapters answer with `PlacementProposalPayload`. The payload must preserve the
pending request ID, proposal kind, source physical unit ID, and `split_unit`
placement kind, and must supply exactly one `attempted_placement` containing the
engine-emitted model IDs. Materialization is explicit set-up placement, not
movement, so it requires validated model endpoints rather than `PathWitness`.
At submission the engine re-resolves the current catalog record, clause, source
rule, and materialization descriptor; validates the referenced completion and
successful roll events; deterministically regenerates the exact models; and
then validates template identity, catalog profile and wargear identity,
battlefield bounds, terrain endpoints, overlap, and final complete-rules-unit
coherency before atomically adding the models and placements. Adapters must not
construct model profiles, derive loadouts, add models, remove destroyed models,
replace a datasheet, or mutate battlefield state locally.

The engine rejects action-phase, parent-phase, source, roll, result-count, or
model-template drift before queue pop. Accepted placement records use the
parent battle phase as `source_phase`; transition evidence, materialization
events, and per-model battlefield-placement events retain both `action_phase`
and `parent_battle_phase`, so out-of-phase shooting replays preserve both the
shooting action and the Movement or Charge phase in which it occurred.

Fight, normal Shooting, and out-of-phase Shooting retain the completed attack
sequence while any materialization decision is pending. After each accepted
placement, the owning phase reruns all completion hooks from that retained
sequence, performs Attached Unit reconciliation only after the hooks drain,
then clears the retained sequence and completes exactly one Fight activation or
out-of-phase Shooting action.

`submit_catalog_model_materialization_placement` is a supported nested reaction
decision. When its source attack belongs to Fire Overwatch or a Fight interrupt,
prevalidation requires the request to own the active reaction frame. Accepted
placement continues that frame to any subsequent completion-hook decision, or
resolves it only after the out-of-phase action or interrupted activation is
complete; restored lifecycles preserve the same frame/request binding.

Each accepted model placement emits its own
`model_placed_on_battlefield` runtime-content timing event for every player so
owner and opponent reactive abilities use the shared event dispatcher. After
materialization reactions resolve, or after any other authoritative model
destruction changes the component's composition, source-backed
`REPLACE_UNIT_DATASHEET` RuleIR may hand the physical owning component to another
datasheet. This keeps
the existing Attached Unit formation and canonical rules-unit identity,
removes only the source-backed destroyed model profiles, remaps retained
materialized models through descriptor-indexed catalog variants, and preserves
the original Starting Strength record. Empty components are never replaced,
and non-attack composition handoff waits for the destruction-finalized event so
an optional Shoot on Death or Fight on Death window cannot lose its source model.
Shared mortal-wound routing records a typed, replay-safe composition transition
ledger only after the application has finished, including direct mortal wounds,
Feel No Pain continuations, and Deadly Demise collateral. The ledger carries
source attribution, physical and rules-unit identities, destroyed model IDs,
and battlefield removal evidence, allowing composition handoff to observe
generic selected-target and other mortal-wound consumers without synthesizing
destruction events.
Attached-unit reconciliation observes the composition-driven handoff before it
splits a surviving component away, while a fully destroyed component with no
successfully materialized model follows the ordinary destruction path.

Malformed, stale, wrong-actor, wrong-kind, wrong-unit, wrong-model-set,
template-drifted, descriptor-drifted, exception-bearing, transport-bearing,
out-of-bounds, terrain-invalid, overlapping, or incoherent submissions reject
before queue pop, `DecisionRecord` creation, or mutation. The current
materialization requests, placements, transition records, and datasheet
handoffs are public battlefield information. Future hidden materialization must
add viewer-scoped request, record, projection, diagnostic, and event-delta
redaction before becoming adapter-visible.

Required model-materialization tests cover both source packages sharing the
same semantics, attack and Hazardous destruction gates, non-attack exclusion,
valid and stale placement, exact catalog profile/base/loadout identity,
real Shooting/Fight Attached Unit handoff, out-of-phase action/parent phase
evidence, restored Overwatch and Fight-interrupt reaction-frame continuation,
selected-target mortal wounds with and without a Feel No Pain continuation,
Deadly Demise collateral finalization, destruction-reaction finalization,
authoritative restored-request tamper rejection, Starting Strength preservation,
deterministic JSON-safe request/state round trips, and per-model placement
reaction dispatch.

## Catalog First-Death Return Decisions

Catalog first-death return RuleIR is captured from `model_destroyed` events using
structured trigger, frequency, D6 gate, Engagement Range restriction, and
`RETURN_DESTROYED_TARGET` effect payloads. The destruction capture records a
pending `PendingReturnOnDeath` with deterministic source IDs, destroyed unit/model
IDs, destroyed-position event payload, phase, roll gate, placement anchor and
preference, restore mode, and consumed key. The engine does not set the model or
unit back up when the destruction event occurs.

At the end of the same phase, the engine rolls the configured D6 gate. Failed
rolls resolve the pending record without restoring anything. Successful rolls
emit the parameterized decision type `submit_return_on_death_placement` with one
fixed `submit_parameterized_payload` option. The request payload contains
`submission_kind: "submit_return_on_death_placement"`, pending ID, source rule,
destroyed unit/model IDs, `placement_anchor: "destroyed_position"`,
`placement_preference: "as_close_as_possible"`, semantic
`placement_kind: "battlefield_set_up"`, and
`restriction.not_within_engagement_range_of_enemy_units: true`.

The submitted payload must preserve `submission_kind` and include an
`attempted_placement` `UnitPlacement` for the destroyed model or destroyed unit.
The engine validates the pending record, actor, target unit/model set,
return-to-battlefield placement kind, destroyed-position anchor, as-close-as-possible
proof when the destroyed position is inside enemy Engagement Range, and the
not-within-enemy-Engagement-Range rule before restoring fixed remaining wounds or
full-health models/units and placing them on the battlefield. Adapters must not restore
wounds, alter removed-model state, choose dice results, or mutate battlefield placement
locally.

Malformed, stale, wrong-pending, wrong-actor, wrong-unit, wrong-model,
placement-kind drift, pending-state drift, Engagement Range violations, and
unsupported return shapes reject before mutation. Return pending records and
placement choices are public table information in the current scope; future
hidden destruction or set-back-up effects must be viewer-scoped before exposure.

Required first-death return tests cover catalog consumer classification,
destruction capture, once-only consumed-key behavior, phase-end deferral, failed
roll resolution, successful placement request, Engagement Range rejection, fixed
wounds restoration, full-health unit restoration, replay payload round-trip,
stale pending rejection, and malformed IR fail-closed cases.

## Parameterized Proposals

Parameterized proposals are used when the exact physical result cannot be safely enumerated as finite options.

The contract currently covers these proposal families:

- Normal Move;
- Advance after dice/reroll resolution;
- Fall Back, including explicit `ordered_retreat` or `desperate_escape` mode context and Desperate Escape follow-up behavior where applicable;
- Surge Move, including source-trigger context, engine-rolled maximum distance,
  and PathWitness movement evidence;
- Reinforcement placement;
- Deep Strike placement;
- Strategic Reserves placement;
- Disembark placement;
- Deployment placement;
- Redeploy placement;
- Scout reserve setup;
- Scout Move and Dedicated Transport Scout Move;
- Charge Move, including charge-target selection, no-move choice, and PathWitness movement evidence;
- Pile In and Consolidate movement, including no-move choices, fight movement target or objective context, and PathWitness movement evidence;
- catalog model materialization placement after a successful source-backed
  destruction trigger and dice gate;
- first-death return placement after a successful phase-end return roll;
- ranged shooting declaration, when target/weapon/profile binding is not safely enumerable;
- melee declaration, including one primary melee weapon per fighting model, optional `[EXTRA ATTACKS]` weapons, model-engaged target binding, and split melee attack counts;
- Stratagem target or placement proposals introduced by Phase 12 and later phase gates.

Later phases must reuse the same contract for Stratagem target binding and mission movement or placement effects where applicable.

Parameterized requests are still `DecisionRequest`s. They contain a single `submit_parameterized_payload` option and embed a neutral `ProposalRequestPayload` inside `DecisionRequest.payload`.

Example proposal request:

```json
{
  "request_id": "decision-request-000005",
  "decision_type": "submit_movement_proposal",
  "actor_id": "player-a",
  "payload": {
    "proposal_request": {
      "request_id": "decision-request-000005",
      "decision_type": "submit_movement_proposal",
      "actor_id": "player-a",
      "game_id": "phase11d-game",
      "battle_round": 1,
      "phase": "movement",
      "unit_instance_id": "army-alpha:intercessor-unit-1",
      "proposal_kind": "normal_move",
      "source_decision_request_id": "decision-request-000004",
      "source_decision_result_id": "phase11d-golden-normal-action",
      "spatial_context_hash": "03f3bc126357a70d9743ca6770ffae79e65b0845e9d6269e7d93d3f0f5883beb",
      "movement_phase_action": "normal_move",
      "placement_kinds": [],
      "context": {
        "source_selected_option_id": "normal_move",
        "movement_mode": "normal"
      }
    }
  },
  "options": [
    {
      "option_id": "submit_parameterized_payload",
      "label": "Submit Parameterized Payload",
      "payload": {"submission_kind": "parameterized"}
    }
  ]
}
```

The adapter then supplies the exact proposal payload.

Surge Move proposals use the same `submit_movement_proposal` wrapper with
`proposal_kind: "surge_move"` and `movement_phase_action: "surge_move"`. The
pending request is emitted only after a source-backed triggered-movement finite
selection, and its context includes the source rule ID, hook ID, trigger event,
triggering enemy unit, selected reacting unit, and maximum surge distance rolled
by the engine. The adapter payload must preserve the request ID, proposal kind,
unit ID, movement action, and movement mode from the request and provide
per-model movement entries with a `PathWitness` for every moved model. Malformed,
stale, wrong-kind, wrong-unit, wrong-action, wrong-source, over-distance, missing
witness, witness-start/model-ID drift, pathing/terrain, and coherency failures
are rejected through the shared movement proposal diagnostics. Accepted
`surge_move` proposals mutate battlefield placement only through the Movement
engine and emit replay-safe triggered-movement resolution events.

Example Normal Move submission:

```json
{
  "request_id": "decision-request-000005",
  "result_id": "ui-result-000018",
  "payload": {
    "proposal_request_id": "decision-request-000005",
    "proposal_kind": "normal_move",
    "unit_instance_id": "army-alpha:intercessor-unit-1",
    "movement_phase_action": "normal_move",
    "movement_mode": "normal",
    "witness": {
      "model_paths": [
        {
          "model_id": "army-alpha:intercessor-unit-1:model-1",
          "poses": [
            {
              "position": {"x": 6.0, "y": 6.0, "z": 0.0},
              "facing": {"degrees": 0.0}
            },
            {
              "position": {"x": 7.5, "y": 6.0, "z": 0.0},
              "facing": {"degrees": 0.0}
            },
            {
              "position": {"x": 9.0, "y": 6.0, "z": 0.0},
              "facing": {"degrees": 0.0}
            }
          ]
        },
        {
          "model_id": "army-alpha:intercessor-unit-1:model-2",
          "poses": [
            {
              "position": {"x": 6.0, "y": 8.0, "z": 0.0},
              "facing": {"degrees": 0.0}
            },
            {
              "position": {"x": 6.0, "y": 8.0, "z": 0.0},
              "facing": {"degrees": 0.0}
            }
          ]
        }
      ]
    },
    "model_movements": [
      {
        "model_instance_id": "army-alpha:intercessor-unit-1:model-1",
        "path": [
          {
            "position": {"x": 6.0, "y": 6.0, "z": 0.0},
            "facing": {"degrees": 0.0}
          },
          {
            "position": {"x": 7.5, "y": 6.0, "z": 0.0},
            "facing": {"degrees": 0.0}
          },
          {
            "position": {"x": 9.0, "y": 6.0, "z": 0.0},
            "facing": {"degrees": 0.0}
          }
        ],
        "final_pose": {
          "position": {"x": 9.0, "y": 6.0, "z": 0.0},
          "facing": {"degrees": 0.0}
        }
      },
      {
        "model_instance_id": "army-alpha:intercessor-unit-1:model-2",
        "path": [
          {
            "position": {"x": 6.0, "y": 8.0, "z": 0.0},
            "facing": {"degrees": 0.0}
          },
          {
            "position": {"x": 6.0, "y": 8.0, "z": 0.0},
            "facing": {"degrees": 0.0}
          }
        ],
        "final_pose": {
          "position": {"x": 6.0, "y": 8.0, "z": 0.0},
          "facing": {"degrees": 0.0}
        }
      }
    ]
  }
}
```

Every alive model in the moving unit must appear in the `PathWitness`. A model that does not
move is submitted as an explicit zero-displacement path with identical start and end poses.
Straight-line real displacement may be submitted as exactly the current/start pose followed by
the desired/end pose; the engine samples that segment internally for path validation. Repeated
endpoint-only evidence such as start/end/end or start/start/end is invalid for real displacement;
when explicit intermediate waypoints are present, at least one interior pose must be distinct
from both endpoints. `model_movements` remains an optional adapter annotation, but when
present it should be complete and 1:1 with the witness, including zero-displacement models.

Producer examples:

- local UI: user drags models and submits final poses plus `PathWitness` path evidence;
- CLI: user enters coordinates and the adapter builds a `PathWitness` with path evidence;
- AI: movement solver generates final poses plus `PathWitness` path evidence;
- network UI: client sends serialized proposal payload;
- replay: recorded proposal payload is resubmitted.

All become the same engine-facing result:

```python
result = ParameterizedSubmission(
    request_id="decision-request-000005",
    payload=movement_payload,
    result_id="ui-result-000018",
).to_result(pending_request)

status = lifecycle.submit_decision(result)
```

The adapter helper equivalent is:

```python
status = submit_parameterized_payload(
    lifecycle=lifecycle,
    request_id="decision-request-000005",
    payload=movement_payload,
    result_id="ui-result-000018",
)
```

## Placement Proposals

Placement proposals use the same `ParameterizedSubmission` path, but the proposal request has `decision_type: "submit_placement_proposal"` and a placement-oriented `proposal_kind`.

Current placement proposal kinds:

- `reinforcement_placement`;
- `deep_strike_placement`;
- `strategic_reserves_placement`;
- `disembark_placement`;
- `cult_ambush_placement`.

First-death return placement uses the same `ParameterizedSubmission` wrapper and
`UnitPlacement` shape, but its decision type is
`submit_return_on_death_placement` because the pending record and restoration
semantics are owned by the return-on-death engine path rather than reserve
arrival.

The request's `placement_kinds` field enumerates the legal physical placement methods available for that unit and state. The submitted payload must match the pending request.

Reserve-arrival and Disembark requests identify the canonical rules unit and carry deterministic `component_unit_instance_ids` and `model_instance_ids` in their source context. Those inventories contain exactly the currently living physical components and models; destroyed component IDs remain only in immutable Attached Unit lineage and are not placement authority. A non-attached unit may use `attempted_placement`. An attached rules unit must instead use `attempted_rules_unit_placement`, containing the canonical `rules_unit_instance_id` and exactly one complete `UnitPlacement` for every currently living physical component. The two attempted-placement fields are mutually exclusive. The engine rejects component or model drift before queue pop and validates battlefield legality and coherency across the flattened rules unit before adding any component.

Example Strategic Reserves submission shape:

```json
{
  "proposal_request_id": "decision-request-000041",
  "proposal_kind": "strategic_reserves_placement",
  "unit_instance_id": "army-alpha:reserve-unit-1",
  "placement_kind": "strategic_reserves",
  "attempted_placement": {
    "army_id": "army-alpha",
    "player_id": "player-a",
    "unit_instance_id": "army-alpha:reserve-unit-1",
    "model_placements": [
      {
        "army_id": "army-alpha",
        "player_id": "player-a",
        "unit_instance_id": "army-alpha:reserve-unit-1",
        "model_instance_id": "army-alpha:reserve-unit-1:model-1",
        "pose": {
          "position": {"x": 6.0, "y": 36.0, "z": 0.0},
          "facing": {"degrees": 180.0}
        }
      }
    ]
  },
  "large_model_exceptions": []
}
```

Example attached-unit Strategic Reserves submission shape:

```json
{
  "proposal_request_id": "decision-request-000042",
  "proposal_kind": "strategic_reserves_placement",
  "unit_instance_id": "attached-unit:army-alpha:leader-and-bodyguard",
  "placement_kind": "strategic_reserves",
  "attempted_rules_unit_placement": {
    "rules_unit_instance_id": "attached-unit:army-alpha:leader-and-bodyguard",
    "component_unit_placements": [
      {
        "army_id": "army-alpha",
        "player_id": "player-a",
        "unit_instance_id": "army-alpha:bodyguard",
        "model_placements": [
          {
            "army_id": "army-alpha",
            "player_id": "player-a",
            "unit_instance_id": "army-alpha:bodyguard",
            "model_instance_id": "army-alpha:bodyguard:model-1",
            "pose": {
              "position": {"x": 6.0, "y": 36.0, "z": 0.0},
              "facing": {"degrees": 180.0}
            }
          }
        ]
      },
      {
        "army_id": "army-alpha",
        "player_id": "player-a",
        "unit_instance_id": "army-alpha:leader",
        "model_placements": [
          {
            "army_id": "army-alpha",
            "player_id": "player-a",
            "unit_instance_id": "army-alpha:leader",
            "model_instance_id": "army-alpha:leader:model-1",
            "pose": {
              "position": {"x": 7.5, "y": 36.0, "z": 0.0},
              "facing": {"degrees": 180.0}
            }
          }
        ]
      }
    ]
  },
  "large_model_exceptions": []
}
```

Example Disembark submission shape:

```json
{
  "proposal_request_id": "decision-request-000052",
  "proposal_kind": "disembark_placement",
  "unit_instance_id": "army-alpha:passenger-unit",
  "placement_kind": "disembark",
  "attempted_placement": {
    "army_id": "army-alpha",
    "player_id": "player-a",
    "unit_instance_id": "army-alpha:passenger-unit",
    "model_placements": [
      {
        "army_id": "army-alpha",
        "player_id": "player-a",
        "unit_instance_id": "army-alpha:passenger-unit",
        "model_instance_id": "army-alpha:passenger-unit:model-1",
        "pose": {
          "position": {"x": 13.0, "y": 10.0, "z": 0.0},
          "facing": {"degrees": 0.0}
        }
      }
    ]
  },
  "transport_unit_instance_id": "army-alpha:transport-1",
  "disembark_mode": "tactical_disembark",
  "transport_movement_status": "not_moved",
  "restriction_overrides": []
}
```

Cult Ambush marker ingress uses the same placement payload shape with `proposal_kind: "cult_ambush_placement"` and `placement_kind: "cult_ambush"`. The proposal request context carries the Cult Ambush marker payload. The submitted placement must put at least one model in base contact with that marker and all other models wholly within 3 inches of it.

Serialized payload helpers may omit empty optional collections such as `large_model_exceptions` or `restriction_overrides`; inbound parsing accepts omitted empty optional fields.

The engine validates placement, rules-unit identity, grouped coherency, reserve restrictions, transport state, and any rule-specific exceptions before mutating battlefield state. Accepted attached-unit reserve arrivals add every physical component and transition the single canonical reserve state as one engine operation.

## Validation and Invalid Results

Adapters should treat invalid proposal responses as authoritative diagnostics, not as local validation suggestions.

Finite requests use the existing selected-option equality rule: `DecisionResult.selected_option_id` must name one option on the pending `DecisionRequest`, and `DecisionResult.payload` must equal that option's payload.

For `select_primary_mission_choice`, the lifecycle additionally regenerates
the complete authoritative request before queue pop, `DecisionRecord`
creation, or state mutation. It rechecks stage/timing, actor, choice kind,
Primary assignment, source IDs, subject or source Action, legal target and
evidence inventories, fallback state, option IDs, and option payloads. Stale or
drifted requests return `primary_mission_choice_request_drift` in
`invalid_reason` and `authoritative_request` in `field`. Malformed payloads,
unsupported choice kinds,
invented option IDs, and wrong request/result context are likewise rejected
before mutation. The pending request remains unresolved and no marker,
condemned selection, designation update, Action result, or event is committed.

Parameterized proposal requests use a different validation rule. The pending request still contains the fixed `submit_parameterized_payload` option, and the submitted `DecisionResult.selected_option_id` must be `submit_parameterized_payload`. For parameterized requests, `DecisionResult.payload` is the adapter's movement or placement proposal. It is validated against the embedded `ProposalRequestPayload`; it is not required to equal the fixed option payload `{"submission_kind": "parameterized"}`.

Every `submit_movement_proposal` and shared `submit_placement_proposal` request carries a required opaque `spatial_context_hash`. The engine computes the token from authoritative battlefield bounds and placements, terrain, mission geometry, model physical state, measurement/support dimensions, and geometry/height provenance. Adapters preserve the token only as request context; they do not compute, compare, or submit it as validation authority. Immediately before queue pop, the engine recomputes the token from current authoritative state. Any mismatch returns typed `spatial_context_drift`, leaves the pending request queued, creates no `DecisionRecord`, and mutates no battlefield state. A retry issued after a rule-invalid recorded attempt receives a fresh engine-owned token.

For accepted reserve-arrival history, lifecycle snapshot restoration cross-binds that
request-time token to the engine-emitted `placement_proposal_requested` event and
authenticates the complete decision and route-event ordering. It deliberately does
not recompute historical geometry from the final snapshot, which may contain later
movement, destruction, return-to-reserves, or Attached Unit component loss. Full historical
spatial verification belongs to `ReplayRunner`, which re-executes the recorded
decisions against the original state sequence and exercises the live stale-submission
check at each request.

Before the queue is popped or a `DecisionRecord` is created, Phase 11D must validate:

- request ID drift;
- actor drift;
- decision type drift;
- proposal kind drift;
- unit drift;
- movement mode and Fall Back mode drift;
- authoritative spatial, geometry-provenance, and source-context drift;
- required proposal context drift;
- JSON shape and required-field validity.

Malformed, stale, schema-invalid, or context-drift submissions leave the pending request unresolved. They return typed invalid diagnostics and may append adapter-visible invalid-proposal events, but they must not create a `DecisionRecord`.

Phase 11D chooses a different policy for rule-invalid but well-formed proposals. If the payload is well-formed and matches the pending request, but movement, pathing, terrain, placement, coherency, reserve, or transport validators reject it, the engine records the rejected attempt as a normal request/result pair, appends typed invalid diagnostics, and emits a fresh pending proposal request with the same authoritative validation context and a new request ID. This preserves replay of failed legal-shape attempts while still giving the actor a live request to answer.

Invalid and stale proposals return `LifecycleStatus.invalid(...)` with a `proposal_validation` payload. The engine must not mutate authoritative state for invalid proposal payloads.

Example malformed proposal response:

```json
{
  "proposal_validation": {
    "proposal_request_id": "decision-request-000005",
    "proposal_kind": "normal_move",
    "is_valid": false,
    "status": "invalid",
    "violations": [
      {
        "violation_code": "proposal_payload_missing_field",
        "message": "Proposal payload missing required field: proposal_request_id.",
        "field": "proposal_request_id"
      }
    ]
  }
}
```

Important behavior:

- stale request IDs are rejected;
- proposal-kind drift is rejected;
- unit drift is rejected;
- movement-mode and Fall Back-mode drift are rejected;
- malformed movement witnesses return typed invalid diagnostics;
- malformed attempted placements return typed invalid diagnostics;
- unsupported proposal kinds fail explicitly;
- invalid proposals do not consume the pending request before payload-shape validation.

## Projection and Visibility

The submission contract is shared. The information available to a producer is not always identical.

Phase 18J publishes `GameViewPayload.battlefield_view` as the canonical visual
play-surface contract. The member remains optional because projections can
exist before battlefield and mission state; current engine projections emit
`battlefield-view-v4-phase17n-step3` when
both battlefield and mission state exist and emit `null` before that boundary.
Its normative world frame is defined in `contracts/coordinate-system.md`:
inches, lower-left origin, positive X/Y on the board plane, positive Z above
the board, and counter-clockwise degrees from positive X.

The payload has three closed sections:

- `authoritative` contains viewer-visible model measurement geometry, poses,
  explicit physical states, terrain rules geometry and logical area identity, objectives, deployment
  zones, and battlefield regions. Its coordinate-versioned content and bounds
  produce `authoritative_geometry_hash`.
- `interaction` contains the current request ID, engine-authored
  selected-or-acting entity IDs, finite decision-option references, measurements, and
  typed line-segment path overlays. These values assist input construction but
  do not grant legality.
- `render` contains hit regions and asset hints only. Clients must not derive
  movement, range, visibility, collision, coherency, placement, or objective
  control from this section.

Model measurement shapes use local coordinates relative to their emitted pose;
terrain, objective, zone, and region geometry uses absolute world coordinates.
Accepted hull measurement geometry and physical support-base geometry remain
separate. Movement and placement still submit the typed proposal and required
`PathWitness` through `GameLifecycle.submit_decision(...)`; endpoint or overlay
geometry never bypasses engine validation.

Battlefield model inclusion consumes the same centralized viewer-scoped model
visibility map as the datacard projection. Hidden enemy models are omitted,
not represented by placeholder entities or counts. Battlefield legal-candidate
references are derived only from visible engine-emitted entity-selection option
IDs; unrelated finite choices never become battlefield candidates. The projection hash
covers the complete viewer-visible `battlefield_view`, while
`authoritative_geometry_hash` deliberately excludes interaction and render
changes.

Fight and attack history authority is not a public projection surface. The
engine-private `ModelDestructionCauseAuthority` rows and every destruction cause
ID are omitted from `GameViewPayload` and reconnect projections. The typed
`GameState.to_public_payload(...)` schema retains its required
`model_destruction_cause_authorities` field as an always-empty list, so it never
reveals a row or hidden count. Public `model_destroyed` events retain only the
viewer-safe outcome payload; the cause ID and authority evidence are removed by
the shared event redaction path. This does not add an option or any other
viewer-visible authority placeholder.

When a mortal-wound packet pauses for a Feel No Pain choice, its authoritative
request and replay record retain `logical_death_events` and
`logical_death_cause_binding` so recovery can authenticate prior wounds. The
shared adapter redaction owner removes both fields wholesale, including all
nested cause, boundary, producer, placement, and transition evidence, from
public pending-request projections, decision-requested/recorded events, and
lifecycle status payloads for every viewer role.

The private mortal-wound Feel No Pain context also retains one exact
`allocation_occurrence` for the current wound. It binds the application and
wound index, target canonical rules-unit ID, active 06.02 priority tier, exact
legal model inventory, selected model, automatic-or-player selection
disposition, parent request/result IDs when selected by a player, and the exact
selected-model Feel No Pain source inventory and decline policy. Restore and
pre-submission validation reconstruct that occurrence, its parent decision
closure, the child request, and both private events before queue pop, recording,
RNG, damage, or completion. The shared redaction owner removes the occurrence
with the rest of the private lost-wound context; adapters must not create,
modify, or interpret it.

The same private context retains the packet's frozen target lineage. If model
destruction removes an Attached Unit component while the packet is paused,
restore and pre-submission validation keep the original canonical target,
consider every placed living model represented by the exact frozen components,
and recompute the four priority tiers across that packet-wide population. They
do not terminate the packet while the retained rules unit survives or admit a
component that joined later. The frozen Character-component classification survives component loss, but its
serialized value is never trusted by itself. Before allocation authority is
accepted, the engine reconstructs the exact set from active attached
Leader/Support component roles or the canonical target's exact historical
`StartingAttachedUnitRecord`, unions any independently Character-keyworded
component, and requires equality with the retained set. Coordinated drift of
the application-started event, model request, allocation occurrence, Feel No
Pain request, parent decision closure, or their request events therefore still
rejects before queue pop, decision recording, RNG, wound mutation, destruction,
or packet completion. This lineage is engine authority and remains inside the
redacted mortal-wound context.

The engine records one private `mortal_wound_application_started` authority
event before any shared mortal-wound packet applies damage. It freezes the
game/application ID, exact source rule/context, target and defender, packet size,
spillover, destruction evidence, priority models, frozen target lineage, and
initial logical-death binding mode. Restore requires it to precede and bind exactly one pending Feel
No Pain request or supported packet terminal, and also validates terminals back
to exactly one root. Auxiliary Deadly Demise collateral-cause finalization is a
separate typed finalization kind, not a packet terminal; restore binds each such
finalization, or its pending destruction-reaction continuation, to exactly one
finalized attack-damage child cause. Replay retains this authority event; the
shared redaction owner suppresses the entire event for players and administrators
alike. This is not a player-facing decision or a new adapter submission field.

Authoritative battlefield terrain-area entities and mission setup terrain
projections expose typed geometry for current validated layout areas. Warhammer
Event Companion layout geometry is represented as
`GameViewPayload.mission_setup.terrain_areas[*]`; adapters should render those
area footprints from the typed `footprint_polygon` list of `{x_inches,
y_inches}` vertices, along with the area `classification`,
`footprint_template_id`, `center_x_inches`, `center_y_inches`, and
`rotation_degrees` metadata. Each physical placement also carries a required
`logical_terrain_area_id`; the authoritative copy participates in
`authoritative_geometry_hash`. An isolated footprint uses its own
`terrain_area_id`; multiple physical placements share a distinct logical ID
only when source data defines them as one rules terrain area. Adapters retain
the physical polygons for rendering and must not infer or alter grouping from
visual proximity. Terrain areas are layout footprints; they are distinct from
the physical terrain features placed on those areas.

Mission setup projections may also expose
`GameViewPayload.mission_setup.objective_terrain_areas[*]` when source-backed
objectives are terrain footprints rather than standalone marker disks. Each
entry links one objective marker ID and role to one or more `terrain_area_ids`.
Multiple terrain area IDs on one entry represent a single composite objective
made from bordered footprint polygons. Adapters should render those linked
terrain areas as the objective footprint and treat the objective marker as
stable objective identity/label metadata. Adapters must submit complete logical
membership: referencing any physical terrain area requires listing every
mission-setup terrain area with the same `logical_terrain_area_id`. Layout,
mission-setup, Contract 10 create, replay, and objective-control validation
reject partial logical groups. Removing a physical member, relabelling the
survivor, or clearing `battlefield_layout_id` does not bypass the canonical
source-layout reconciliation. Replay state must retain the same mission setup
as its validated config snapshot. Adapters must not infer objective terrain,
light/dense terrain traits, or terrain-feature rules from footprint colors,
terrain area IDs, template IDs, or `source_id` strings.

Terrain features, when present, expose first-class display geometry under
`GameViewPayload.mission_setup.terrain_features[*].display_geometry`. The
display geometry payload uses schema `terrain-display-v1`, coordinate space
`battlefield_inches`, footprint kind `polygon`, optional
`display_template_id`, and an unclosed `footprint_polygon` list of
`{x_inches, y_inches}` vertices. Adapters should render from these typed
payloads. Each runtime feature also exposes its source-backed `classification`
(`dense`, `light`, `mixed`, or `unknown`) independently from
`terrain_feature_kind`; clients must not infer that classification from wall
height, color, or feature kind. Exact-layout feature `source_id` values retain
the source-hashed preset provenance, including the exact artifact package hash,
through MissionSetup/GameConfig round trips and battlefield projections.
`source_id` remains provenance only; adapters must not parse it to recover
terrain preset, origin, rotation, footprint details, or terrain behavior.

`terrain_areas[*].terrain_feature_kind` identifies the semantic kind of the
layout area and does not claim that every component on a multi-component area
shares one terrain feature kind. Authoritative per-component kind and
classification live on `terrain_features[*]`.

Warhammer Event Companion layout source geometry is canonical in `44x60` portrait
orientation. UI clients that prefer wide battlefield displays may rotate the
rendered view by -90 degrees into landscape, but the adapter payload coordinates
remain portrait source coordinates and should not be reinterpreted as native
`60x44` layout data.

Phase 18A extends the viewer projection for
[Issue #145](https://github.com/SobolGaming/Warhammer_40k_AI/issues/145) with a
hybrid projection model:

1. Static catalog projection/cache. `project_rules_catalog_view(...)` returns a
   `RulesCatalogViewPayload` with `projection_schema: "rules-catalog-view-v2"`,
   catalog identity, source package identity, `source_hash`, and display records
   for datasheets, datasheet abilities, model profiles, weapon profiles,
   factions, detachments, enhancements, wargear, wargear options, and base sizes.
   Datasheet display records include structured ability display payloads with
   ability ID, display name, source ID, support status, timing tags, parameter
   tokens, and the full descriptor profile. Adapters may cache this payload by
   catalog ID/schema/hash and render catalog browsing, roster panels, and
   tooltips from it. `LocalGameSession.rules_catalog_view()` exposes the same
   static projection for local UI/CLI clients that already consume
   `LocalGameSession.view(...)`.
2. Live viewer-safe unit/model projection. Phase 18A introduced
   `projection_schema: "game-view-v3-phase18a"`; the current `GameViewPayload`
   uses `game-view-v11-phase17n-step4`, includes
   `projection_state_hash`, references the static catalog through
   `rules_catalog`, and exposes read-only `unit_display_by_id` and
   `model_display_by_id` maps keyed by stable `unit_instance_id` and
   `model_instance_id` values. These records let adapters join battlefield
   placements, selected unit/model state, roster panels, inspectors, assignment
   summaries, and datacard-style widgets without importing engine internals or
   inventing rules facts.

`RulesCatalogReferencePayload` in a live view contains
`projection_schema`, `catalog_id`, `ruleset_id`, `source_package_id`, and
`source_hash`. The full static catalog remains reference data only. The live
`GameViewPayload` remains responsible for current viewer-safe presentation
state:

- `UnitDisplayPayload` records include `unit_instance_id`, `owner_player_id`,
  `unit_display_name`, `datasheet_id`, source metadata, viewer-visible keywords
  and faction keywords, model instance IDs, selected wargear IDs, visible
  unit-resource starting and remaining counts, visibility status, and
  redaction metadata.
- `ModelDisplayPayload` records include `model_instance_id`,
  `unit_instance_id`, `datasheet_id`, `model_profile_id`, display names,
  manifested model `wargear_ids`, `base_size`, starting/current wounds,
  `base_characteristics`,
  `current_characteristics`, `visible_modifiers`, source metadata, visibility
  status, and redaction metadata.
- `base_characteristics` and `current_characteristics` cover the canonical
  datacard characteristics `M`, `T`, `SV`, `InSv`, `W`, `LD`, and `OC`. Models
  without an invulnerable save expose `InSv` as a source dash.
- `CharacteristicDisplayPayload` entries expose `characteristic`, `label`,
  `value_kind`, raw/base/final values, `display_value`, applied modifier IDs,
  and redaction metadata. Unknown values use `value_kind: "unknown"` and null
  values. Dash characteristics retain their engine numeric fields, usually zero,
  while `display_value` carries `"-"` and `value_kind` distinguishes source dash
  from replacement dash.
- `visible_modifiers` are audit/display traces with `modifier_id`,
  `source_kind`, `source_id`, `target`, `applies_status`, `public_label`, and
  `operation_text`. They explain visible engine-resolved changes but are not an
  executable instruction set that adapters must evaluate.
- Battle-shocked units project Objective Control through the same engine helper
  used by objective scoring: base `OC` remains the stored model characteristic,
  current `OC` becomes the `battle_shock` replacement dash, and
  `visible_modifiers` includes the `battle_shock` trace.

Adapters may compute purely presentational derivatives, such as catalog ID to
display label, model base diameter to pixel radius, keyword chips, source-link
tooltip text, or a "changed from base" badge by comparing `base_characteristics`
to `current_characteristics`. Adapters must not compute rules-effective
characteristics, legal weapon profiles after options, detachment or enhancement
effects, aura application, Battle-shock effects, hidden/revealed status, unit
visibility, or redaction state from static catalog data plus modifier records.

The Phase 18A unit/model display projection is deterministic, JSON-safe,
viewer-scoped, read-only, and presentation-only. Army lists and datacards are
public tabletop information, so both players receive every mustered unit and
model in `unit_display_by_id` and `model_display_by_id`, including units that
are embarked or remain unplaced in Strategic Reserves. Declare Battle
Formations secrecy applies to the declaration choices and unrevealed formation
state, not to those roster identities. `projection_state_hash` changes when
the adapter-visible live display state changes, including wound changes, so UI
caches can refresh display data without treating it as authoritative rules
state. Issue #145 is complete because a visible known model can render through
this join without placeholder unknowns:

`battlefield_state` placement -> `unit_display_by_id[unit_instance_id]` ->
`model_display_by_id[model_instance_id]` ->
`current_characteristics["M/T/SV/InSv/W/LD/OC"]`.

Phase 11E adds scoring state to the viewer projection:

- `public_secondary_mission_card_states`: Fixed and Tactical card state payloads scoped
  through the secondary-mission reveal gate.
- `public_victory_point_ledgers`: victory point ledgers scoped to the viewer.
- `primary_rules_unit_turn_start_snapshots`: deterministic, engine-owned
  evidence recording each rules unit's exact physical component
  models, logical terrain-area membership, and objective-marker/model proximity
  at each player-turn boundary.
- `primary_mission_progress_state`: deterministic, engine-owned public Primary
  Mission state containing persistent/tombstoned markers, historical
  Punishment condemned selections, and active/consumed Consecrate
  designations.

Turn-start snapshots are created only after battle entry, once Declare Battle
Formations has completed and its results are public. Both players therefore
receive every complete historical rules-unit row, including rows for units that
are now unplaced. Each outer row carries `rules_unit_instance_id` and
`component_memberships`; component rows carry `unit_instance_id`, exact
`evaluated_model_instance_ids`, `logical_terrain_area_ids`, and
`objective_marker_witnesses`, whose model lists identify exactly which models
were in range. Units that began the turn off the battlefield retain explicit
empty position sets. Adapters may display this evidence for scoring audit but
must not recalculate it from current positions.

Phase 17N Step 4 progress is public tabletop mission state. Both player views,
role-scoped event deltas, reconnect projections, and replay expose the same
rows at the same visible revision; delayed spectators receive those rows only
when their normal delayed projection reaches that revision. Primary choices do
not carry the shared `secret` request flag and are not redacted as
`hidden_decision`. Their pending request, option inventory, accepted result,
and progress effect are visible to both players.

`primary_mission_progress_state.markers` records stable marker/game/owner/
mission/source identities, marker kind, exactly one objective or terrain
anchor, optional creation battle context, source event/result/Action/
destruction/designation provenance, and `active` or `removed` status. Removed
markers remain in the collection with complete removal battle context and
source/event/result/Action provenance. Adapters must render status rather than
interpreting absence as removal.

`condemned_selections` preserves each Punishment turn's candidate policy,
complete candidate rules-unit and evidence inventories, selected rules units,
minimum/maximum selection counts, fallback flag, optional decision request and
result IDs, and source event. `consecration_designations` preserves the
designated rules-unit identity and physical components, source destruction and
creation context, last declined-resolution context, active/consumed status,
and the consumed marker plus consumption provenance. These collections are
historical audit records, not adapter mutation instructions. They participate
in `projection_state_hash` and must be replaced from a fresh projection after
resynchronization.

Chapter Approved 2026-27 secondary selection is simultaneous-secret. A player's
Fixed/Tactical mode and Fixed mission IDs are secret only until every player has
submitted their `select_secondary_missions` decision. Before that reveal point,
non-owning viewers receive a hidden placeholder for submitted opposing choices,
no opposing secondary card states, and no opposing Tactical draw records.

After every player has selected, secondary mode, Fixed mission IDs, Tactical
status, Tactical draws, secondary card states, and normal secondary scoring
transactions are public to every viewer. Adapters may display totals and public
scoring audit entries from these fields. Future hidden mission rules must mark
their data hidden explicitly and define their own reveal timing in the same
contract update that introduces them.

Hidden pending-decision redaction is centralized in `adapters.redaction` and
applies consistently to projections, event deltas, and HTTP status or mutation
responses. A hidden pending request exposed to a non-actor viewer uses
`decision_type: "hidden_decision"` and omits legal options and proposal details.
Transport status summaries also redact hidden `pending_request_id` and
`actor_id`; if a status request has no viewer identity, secret pending metadata
is treated as hidden. Actor-scoped status responses keep the real request ID,
decision type, and actor ID so the owning client can submit through the normal
`DecisionRequest -> DecisionResult` path.

Phase 11E scoring amounts and supported timing gates are source-backed. Primary
mission scoring must honor the selected mission's source scoring-rule condition,
and secondary scoring must use the selected card's Fixed or Tactical scoring
rule instead of a flat adapter default. Fixed secondary card states remain
`active` after scoring because Fixed Missions stay active throughout the battle;
Fixed secondary VP is capped at 20 VP per Fixed Mission card as well as by the
normal Secondary VP cap.

Adapters should consume a `GameViewPayload` for a viewer by default:

```python
view = project_game_view(
    lifecycle=lifecycle,
    viewer_player_id="player-a",
)
```

Local session clients may use the paired session helpers instead of importing
projection functions directly:

```python
rules_catalog = session.rules_catalog_view()
view = session.view(viewer_player_id="player-a")
```

When the visible pending request is parameterized, `GameViewPayload.pending_proposal`
is the adapter-visible proposal request object. It always includes
`request_id`, `decision_type`, and `actor_id` copied from the pending
`DecisionRequest`, followed by the family-specific proposal fields such as
`proposal_kind`, movement context, placement kinds, Stratagem catalog context,
or future shooting/charge details. This shape is intentionally consistent across
`submit_movement_proposal`, `submit_placement_proposal`,
`submit_stratagem_target_proposal`, `submit_melee_declaration`, and later parameterized decision families so
clients can perform submission and stale-request checks without special-casing
nested proposal payloads. Non-parameterized requests, hidden requests for a
non-owning viewer, and views with no pending request expose
`pending_proposal: null`.

Visibility examples:

- local hot-seat UI: viewer-scoped player projection;
- networked opponent client: public information plus that client's own hidden information;
- CLI: viewer-scoped prompt data for the acting player;
- headless AI self-play: normally the same legal viewer-scoped information boundary as a real player;
- replay inspector: may show historical records, but should clearly distinguish replay/internal views from player views;
- debug or oracle AI: may consume richer state only behind an explicit debug or training mode flag.

This distinction is intentional. The final decision or proposal still goes through the same request/result path, even if a privileged diagnostic tool has more information when choosing that result.

## Event Streams

There are two relevant event concepts:

- internal/replay event log: authoritative records used by the engine and replay;
- adapter event deltas: viewer-scoped public stream from `EventStreamCursor.events_since(...)` or `LocalGameSession.events_since(...)`.

Adapter-facing event deltas require a viewer:

```python
delta = session.events_since(
    EventStreamCursor(value=cursor),
    viewer_player_id="player-b",
)
```

Viewer-scoped event deltas must not leak hidden opponent choices before their
reveal gate. In Phase 11D and Phase 11E this includes:

- hidden `decision_requested` payloads;
- hidden `decision_recorded` payloads;
- `secondary_mission_choice_recorded` metadata that would reveal Fixed versus Tactical selection before all players have selected.

Example opponent-visible secondary-choice event:

```json
{
  "event_type": "secondary_mission_choice_recorded",
  "payload": {
    "game_id": "phase11d-game",
    "player_id": "player-a",
    "setup_step": "select_secondary_missions",
    "selected": true,
    "hidden": true
  }
}
```

The owning player or internal replay stream may retain full details. Public adapter streams must follow the same visibility model as `SecondaryMissionChoice.to_public_payload(...)`.

The same boundary applies to destruction causality. Attack, mortal-wound, and
rule-destruction producer events may carry engine-private cause references in
the authoritative event log, but shared redaction removes every cause ID and
`ModelDestructionCauseAuthority` record from projections and event deltas. The public
`model_destroyed` event is an outcome record, not a client-authored or
client-visible causal ledger. No adapter event family, decision type, or
submission payload changes for this internal evidence.

When the final secondary choice is submitted, the public event stream emits
`secondary_missions_revealed` with each player's mode and Fixed mission IDs.
This reveal event is the adapter-facing public audit record; older secret
`decision_requested` and `decision_recorded` events may remain redacted.

Example secondary reveal event:

```json
{
  "event_type": "secondary_missions_revealed",
  "payload": {
    "game_id": "phase11e-game",
    "setup_step": "select_secondary_missions",
    "choices": [
      {
        "player_id": "player-a",
        "mode": "tactical",
        "fixed_mission_ids": []
      },
      {
        "player_id": "player-b",
        "mode": "fixed",
        "fixed_mission_ids": ["assassination", "bring_it_down"]
      }
    ]
  }
}
```

Tactical secondary draws happen after the secondary reveal point in normal
Chapter Approved play, so they are public unless a future mission rule explicitly
marks a draw hidden.

Example public Tactical secondary draw event:

```json
{
  "event_type": "tactical_secondary_missions_drawn",
  "payload": {
    "game_id": "phase11e-game",
    "player_id": "player-a",
    "battle_round": 1,
    "draw_count": 2,
    "phase": "command",
    "secondary_mission_card_states": [
      {
        "player_id": "player-a",
        "secondary_mission_id": "a-tempting-target",
        "mode": "tactical",
        "battle_round": 1,
        "status": "active",
        "source_result_id": "phase11e-tactical-draw",
        "scored_transaction_id": null,
        "discarded_result_id": null
      }
    ]
  }
}
```

Public adapter streams must follow the same visibility model as
`SecondaryMissionChoice.to_public_payload(...)`,
`SecondaryMissionCardState.to_public_payload(...)`, and
`VictoryPointLedger.to_public_payload(...)`.

Phase 17N Step 4 Primary progress and choice events are public. Every pending
choice has the ordinary deterministic `decision_requested`; battle turn-start
and turn-end choices then carry `primary_mission_choice_requested`. An accepted
choice records `decision_recorded` before
`primary_mission_choice_resolved`. Every resolution payload has exactly these
semantic members: `choice`, `request_id`, `result_id`,
`selected_option_id`, `automatic`, `created_markers`,
`condemned_selection`, `updated_designation`, and `removed_marker`.
Automatic empty Punishment resolution has null request/result/option IDs and
still records the complete choice and condemned-selection row. Every
nonautomatic resolution is rebound during restore to exactly one accepted
finite `DecisionRecord`, including its deterministic complete option inventory
and requested/recorded/mutation ordering. An automatic empty Punishment must
have no attached player decision.

Accepted or automatically resolved Step 4 state is also linked through
`mission_action_completed`, `primary_consecration_unit_designated`, and
`primary_surveil_move_marker_removal_resolved` when applicable. A completed
Primary Action event includes its complete `mission_action_state` and nullable
`primary_mission_marker`. Source-backed completed and completion-failed Action
events also carry `mission_action_completion_evidence`
(`primary-mission-action-completion-evidence-v1`). Turn-end evidence cites the
exact authoritative `ObjectiveControlRecord` ID and canonical payload hash,
the target result, Action-unit lineage contributors, Battle-shock state, and,
for Vanguard Operation, one terrain-membership row for every static army model
and the exactly derived terrain-intersection and enemy-presence inventory.
Restore requires Action start before the cited objective-control boundary and
that boundary before the terminal event, reruns the same completion evaluator
used live, and rejects a terminal status that disagrees with that evidence.

Consecrate designations bind the authoritative destruction event and state
row. Restore also applies the rule in reverse: every qualifying retained
friendly-attributed destruction must have exactly one deterministic designation
unless that rules-unit lineage was already actively designated at that event.
A Consecrate request additionally cites one exact turn-end objective-control
record; its destruction/designation lineage and objective-control boundary must
precede `decision_requested`. Restore reconstructs the full legal objective set
at that historical request boundary from designation component lineage and all
prior Consecrate markers, then compares the exact legal targets and evidence
IDs before accepting its DecisionRecord and marker/designation mutation. Every
active designation requires one resolution at each applicable owner turn-end
boundary. A paused sequential queue is valid only when the exact earliest
unresolved Consecrate request remains in the persisted pending-decision queue;
an unmatched event or an unrelated Primary choice cannot mask an omitted
resolution.
Surveil move resolutions bind the processed
move-completion event and every tombstoned marker. Their public payload carries
`moving_rules_unit_objective_proximity_witness`; `objective_marker_ids` is
exactly the witness objective set, and `removed_primary_mission_markers` is the
complete set of opponent Operation markers active on those objectives at the
trigger boundary. Adapters must consume this event order and must not emit
synthetic marker, condemnation, designation, or Action events.

Sensor Sweep marker-removal restore reconstructs marker activity at the exact
`decision_requested` boundary from every marker's creation and optional removal
event. It applies the same friendly/opponent marker policy used live and
requires the complete canonical legal-marker inventory before accepting the
choice DecisionRecord and tombstone mutation.

## Replay and Resume

Replay-facing payloads must remain deterministic and JSON-safe:

- no Python object reprs;
- no memory addresses;
- stable IDs for entities, decisions, events, and proposals;
- stable lifecycle payloads.

Phase 11D must ensure replay/resume preserves pending parameterized proposal requests. Restoring after a finite movement-action result has been accepted but before the proposal has been submitted must reproduce the same pending proposal request and validation context.

Phase 18L durable recovery is distinct from exporting a `ReplayArtifact` to a
client. The operator artifact retains a verified adapter checkpoint plus any
accepted decision tail, protected command-journal idempotency results,
authorization bindings, and cursor state. The adapter-owned recovery factory
restores the checkpoint, routes the decision tail through the same facade and
lifecycle decision path, and proves exact decision, event, projection, RNG, package, and revision
agreement before the transport registers the recovered session. The transport
must not deserialize `GameLifecycle` directly or partially continue after a
failed check.

Contract 10 replay uses `replay-artifact-v8-phase17n-step5a`. It preserves a
pending `select_primary_mission_choice` request, deterministic finite option
IDs/payloads, the complete `primary_mission_progress_state`, the mandatory
`primary_scoring_state_evidence_records`, and the linked decision, Action,
destruction, marker, condemnation, designation, score, and event records.
Each scoring-state row also preserves the exact per-player spatial-condition
evidence and destruction-history membership consumed at that historical
boundary; restore never derives either from later battlefield state.
Restore validates exact DecisionRequest/DecisionResult/mutation closure,
Action start and completion evidence, historical Consecrate legal targets, and
every applicable zero- or nonzero-award boundary plus every score-to-evidence
reference fail closed; it does not infer an empty Step 5A registry for a
Contract 9 artifact.

Replay and tests may choose decisions differently from a human UI, but they must submit the same `DecisionResult` shape through the same lifecycle path.

Restored Fight/Shooting history also validates the engine-private typed
`ModelDestructionCauseAuthority` inventory persisted in `GameState`. Cause-aware
attack and rule-destruction producers reserve and finalize one cause before
`model_destroyed`; cause-aware mortal-wound producers register a finalized cause
before that event. Each `model_destroyed` event carrying
`model_destruction_cause_id` consumes exactly one cause. Generic producers
outside this typed boundary remain valid without that field, while every Fight
On Death continuation still requires an exact consumed cause. Restore binds
every cause to the exact source events and decisions required by its producer
kind, requires a parent cause to be registered before its child and a consumed
child event to precede its consumed parent event, and preserves exact
model/unit/source identity. Missing, duplicate, relocated, or cloned typed
destruction histories fail closed; the loader never reconstructs a cause from a
payload-shaped orphan. This is replay and persistence integrity evidence, not a
new adapter submission shape or player-facing decision.

Recovery also inventories every private `model_logical_death_recorded` event.
Each boundary must be claimed exactly once by either its persisted destruction
cause or the typed progress of one currently pending mortal-wound Feel No Pain
request. The boundary must precede that pending request and the eventual
`model_destroyed` event, and its closed transition, source identity, damage,
placement, model lineage, and producer kind must agree with the claimant.
Orphaned, duplicated, forged, reordered, or cross-producer boundaries fail
closed. Historical Fight movement and target validation changes liveness at
this boundary; later removal records update physical placement only.

## Adapter Responsibilities

Adapters may:

- render pending finite options;
- render pending proposal request context;
- collect user input;
- generate AI candidates;
- serialize submissions over a network;
- provide non-authoritative previews, snapping, measurement overlays, and client-side convenience checks;
- track client-side cursors for viewer-scoped event deltas;
- display typed invalid diagnostics returned by the engine.

Adapter previews and convenience checks are advisory only. They may improve UX or candidate generation, but they cannot replace engine validation and must not mutate authoritative state.

Adapters must not:

- mutate `GameState`, battlefield state, model poses, mission state, objective state, or event logs directly;
- apply private movement, placement, visibility, reserve, transport, or coherency rules;
- synthesize unrequested `DecisionResult`s;
- answer a stale request after a newer pending request exists;
- bypass `DecisionRequest -> DecisionResult -> validation -> engine mutation`;
- inspect or transmit hidden opponent data through public projection/event APIs;
- suppress `DecisionRecord` or `EventRecord` generation for accepted engine decisions.

## Shared Session Facade

Phase 18C promotes `LocalGameSession` into the shared adapter session facade.
Adapter producers may render, rank, generate, or transport choices differently,
but their engine-facing calls converge on one public protocol:

```python
class AdapterGameSession(Protocol):
    def start(self, config: GameConfig) -> LifecycleStatus: ...
    def advance_until_decision_or_terminal(self) -> LifecycleStatus: ...
    def view(self, *, viewer_player_id: str) -> GameViewPayload: ...
    def rules_catalog_view(self) -> RulesCatalogViewPayload: ...
    def events_since(
        self,
        cursor: EventStreamCursor,
        *,
        viewer_player_id: str,
    ) -> EventStreamDeltaPayload: ...
    def decision_record_count(self) -> int: ...
    def submit_option(
        self,
        *,
        request_id: str,
        option_id: str,
        result_id: str,
    ) -> LifecycleStatus: ...
    def submit_parameterized_payload(
        self,
        *,
        request_id: str,
        payload: JsonValue,
        result_id: str,
    ) -> LifecycleStatus: ...
```

The thin producers map to that protocol as follows:

- CLI renders a `DecisionRequest`, maps a human choice to an emitted option ID,
  and calls `submit_option(...)` or `submit_parameterized_payload(...)`.
- UI renders `view(...)` and `rules_catalog_view(...)`, gathers UI intent, and
  submits only through the session facade.
- Network adapters serialize `LifecycleStatus`, `GameViewPayload`,
  `RulesCatalogViewPayload`, and `EventStreamDeltaPayload`, then route client
  submissions through the same session methods.
- Headless producers may rank finite options or generate parameterized payload
  candidates from viewer-safe views, but the accepted answer is still submitted
  through the session facade.
- Replay producers submit recorded `DecisionRecord` or `DecisionResult` values
  by routing finite results to `submit_option(...)` and parameterized results to
  `submit_parameterized_payload(...)`.

Thin producers must not import `GameLifecycle`, access a session's `.lifecycle`
attribute, access `decision_controller`, or call `submit_decision(...)`
directly. Those operations belong inside the session implementation and
engine-owned replay validation, not producer or transport layers.

`LocalGameSession` is the local implementation of this facade. It owns the
`GameLifecycle` instance, validates viewer IDs for event streams, projects
viewer-safe views and source-hashed catalog data, and delegates submissions to
the adapter submission helpers that enforce pending `request_id` matching before
calling `GameLifecycle.submit_decision(...)`. Its monotonic
`decision_record_count()` checkpoint lets an authoritative transport distinguish
pre-record invalid results from recorded invalid/retry attempts without reaching
through the facade to lifecycle internals.

## Formal Session Transport

Phase 18E wraps the shared facade in an authoritative formal session protocol.
Its required operations are create, metadata, start, projection, catalog,
events, finite submission, parameterized submission, explicit advance, replay
export, and close. The transport keeps `session_id` distinct from engine
`game_id`, binds authenticated principals to server-owned roles, publishes
source/build/contract identity, and returns monotonic session revisions plus
role-scoped projection and event checkpoints. Contract 2.0 expresses start,
finite/parameterized submission, explicit advance, and close as typed variants
of the single normative command operation.

An accepted finite or parameterized command is submitted exactly once through
`AdapterGameSession`, then the session owner performs a bounded deterministic
drain to the next decision, terminal result, typed invalid/unsupported result,
or transition-budget safety boundary. One command therefore returns one
coherent post-drain `SessionCommandResult`; a client must not guess how many
internal `advance` calls are needed. Explicit advance remains an operator,
conformance, recovery, and documented idle-boundary operation.

`SessionCommandResult.committed` and `accepted` are intentionally distinct.
`committed` means the command was recorded in authoritative history and caused
exactly one session-revision increment. `accepted` means the proposed gameplay
action was rule-valid/applied. A well-formed, recorded invalid attempt that emits
a fresh retry request returns HTTP 422 with `committed: true`, `accepted: false`,
the incremented revision, and the viewer-scoped event range. Failures rejected
before the facade call return a typed error envelope. Engine pre-validator
failures returned by the facade use the command result with `committed: false`,
`accepted: false` and do not increment the revision.
The public schema and runtime require `accepted: true` to imply
`committed: true`. A valid recorded action remains accepted when its
post-application deterministic advancement reaches the typed
`transition_budget_exhausted` safety boundary: the result is `committed: true`,
`accepted: true` with lifecycle `status_kind: "unsupported"`. A directly
returned recorded `unsupported` result without that typed proof of completed
application is `committed: true`, `accepted: false` with
`outcome_code: "rule_path_unsupported"`; an unrecorded unsupported result uses
the error-envelope code `rule_path_unsupported`.

Session metadata and command results obey the same viewer redaction policy as
projections and event deltas. Every response is principal scoped, and transport
errors contain stable public text rather than caught engine exception details.
Phase 18H owns principal-to-role authentication and authorization. Phase 18F
owns command idempotency and expected-revision concurrency checks, while Phase
18G owns protected opaque cursor/reconnect/resynchronization behavior. Phase
18L owns atomic durable publication and verified recovery of that same
authority unit.

## Formal Phase 18F Commands

The normative mutation endpoint is
`POST /sessions/{session_id}/commands`. Its versioned command envelope carries
one client-generated `command_id`, the session identity, the exact expected
session revision, request/result identities where the submission answers a
decision, and a typed start, advance, close, finite-option, or parameterized
submission. The envelope must not carry `actor_id`, `viewer_player_id`, or any
other authority claim. The transport authenticates an opaque bearer credential,
and the server maps its server-owned principal binding to the pending request
actor. Administrators alone may issue lifecycle commands, but cannot impersonate
a decision actor. Players may answer only their own pending request; coaches,
delayed spectators, and replay viewers cannot mutate.

The server authorizes the submission kind before consulting a matching
journaled command. A retry returns the original status and public payload only
when the canonical envelope and complete current authorization context match
the journaled values and still permit the operation. That context includes the
principal, role, player binding, visibility/cursor policy, delay, omniscience,
route permissions, and registry authorization epoch. Any context mismatch
receives the shared redacted authorization error without command-existence
details. Reusing the ID with a different envelope is a conflict only inside the
same exact authorized context. New commands must match the current revision and
current pending request before the shared adapter facade is invoked.

Application occurs on an isolated fork of the facade-owned lifecycle. The
authoritative session reference changes only after a committed outcome can be
published together with the idempotency journal entry, one revision increment,
projection checkpoint, and event range. Rejected preconditions, unrecorded
illegal proposals, and pre-commit failures discard the fork. Recorded
rule-invalid retry decisions retain the Phase 18E distinction between
`committed` and gameplay `accepted` and are atomically committed with their
fresh request and replay record.

`advance_session` is rejected with `advance_not_required` when the authoritative
session is already waiting for a decision. This rejection occurs before facade
forking or journal insertion, so a no-op advance cannot consume a revision,
reserve its command ID, or race a valid decision solely by revision churn.

The formal Phase 18E mutation endpoints are removed from contract 2.0. Legacy
authenticated `/games` routes remain deprecated development adapters and do not
provide the Phase 18F idempotency and expected-revision guarantees; new clients
use the command endpoint.

## Formal Phase 18G Synchronization

The formal transport never exposes the in-process integer `EventStreamCursor`.
Metadata, command outcomes, and full projections issue an opaque HMAC-derived
identifier for protected server-side cursor state bound to the session ID,
authenticated principal ID, authorization epoch, role/player/delay scope,
authoritative event-log offset, viewer sequence, session revision, and
role-scoped projection hash. The wire token contains no readable cursor state;
the client treats it as an indivisible string.

`GET /sessions/{session_id}/events?cursor=...&limit=...` returns deterministic
`event-delta-v5-phase17n-step4` pages. `sequence_number` is one-based and contiguous within a
viewer scope. Hidden records are omitted while pagination advances the
protected authoritative offset; they create no projection count, placeholder,
sequence gap, extra page, or `has_more` oracle. Page size defaults to 100 and is
bounded at 500. The reference retention window is 4096 authoritative records;
retained revision snapshots also provide exact projection/hash boundaries and
the delayed spectator view.

Malformed, expired, ahead, wrong-session, wrong-principal/role, revision-
divergent, and hash-divergent cursors return `resync_required: true`, a typed
`resync_reason`, an empty event list, and no hidden event details. The canonical
client recovery is:

1. Fetch `GET /sessions/{session_id}/projection`.
2. Replace all client-derived state with its `projection`.
3. Verify the returned revision and projection hash.
4. Resume polling from its `event_cursor`.

HTTP polling is normative. Any future SSE or WebSocket adapter must carry the
same delta payloads and cursor rules.

## Formal Phase 18H Principal Roles

Every route requires an opaque bearer credential and resolves it through an
injected server-owned principal registry before dispatch. Session creation does
not accept participant assignments. A `viewer_player_id` query may only assert
the already-bound player and is omitted from OpenAPI; it never selects a view.
Command bodies accept neither viewer nor actor authority.

| Role | Visibility | Delay | Mutation | Replay |
|---|---|---:|---|---|
| player | bound player's view | 0 | own decisions | denied |
| coach | paired player's view | 0 | denied | denied |
| delayed spectator | public-only | 1 revision | denied | denied |
| administrator | omniscient | 0 | lifecycle only | allowed |
| replay viewer | catalog plus post-session replay only | n/a | denied | terminal/closed only |

Projection, pending-decision, event, lifecycle-status, error, metadata, and
command-result hidden shapes come from `adapters.redaction`. Missing and invalid
credentials share the same 401 response, and every authorization denial shares
the same 403 response. These errors never expose request/actor IDs, option or
target counts, source IDs, support status, or terminal details. Changing a
principal's role, player binding, policy, or registry authorization epoch
changes its cursor scope and invalidates old cursors. Raw active-session replay
remains available only to the omniscient administrator; a replay viewer cannot
use the replay route as a live information feed.

## Formal Phase 18L Persistence and Recovery

The reference server persists one closed
`session-persistence-v3-weapon-instances` operator artifact. The root contains
exact server/engine-build/external-contract/persistence-schema identities, the
principal binding set and authorization epoch, protected cursor secret and
token registry, retention policy, complete authoritative sessions, and the
game/session index. A canonical `content_hash` covers every preceding state
member and excludes only itself. Bearer credentials are never serialized, and
this artifact is not served by an OpenAPI operation.

The semantic package `engine_version` is not a build identity. The separate
`engine_build_id` is
`warhammer40k-core-v2:runtime-tree-sha256-v1:<sha256>` and comes from a generated
manifest of the complete authoritative packaged Python, JSON, `py.typed`, and
contract-schema resource inventory. The runtime verifies that manifest before
publishing its identity. Missing manifest data or a dirty resource tree fails
closed, and recovery rejects another build even when both builds use the same
package version.

Session persistence includes normalized game configuration and exact ruleset,
overlay, catalog, and source-package identities; deterministic RNG state;
accepted command envelopes and authorization contexts; decision and event
records; monotonic revision and cached idempotency outcomes; terminal state;
retained revision snapshots; and the adapter-owned current/initial
lifecycle/replay checkpoint with deterministic verification hashes. Every
operator wrapper object is closed and versioned. Engine-private lifecycle
content still passes its typed fail-fast runtime loader; schema acceptance
alone does not authorize recovery.

The persisted `GameState` also carries the engine-private typed
`ModelDestructionCauseAuthority` inventory. Cause-aware attack and
rule-destruction producers reserve/finalize a cause before emitting
`model_destroyed`, while cause-aware mortal-wound producers register the
finalized cause directly; a resulting event carrying
`model_destruction_cause_id` consumes it exactly once. Generic producers outside
this typed boundary remain valid without that field, but every Fight On Death
continuation requires an exact consumed cause. Recovery cross-validates every
record against the authoritative evidence required by its producer kind,
including exact one-to-one identity, causal registration/consumption order, and
original event placement. Missing, duplicate, relocated, and cloned typed
causes are rejected before the session becomes addressable. Cause IDs and
authority records are redacted from all public projections and event deltas,
and no player-facing decision or adapter submission shape is changed. These
checks protect deterministic internal consistency and replay integrity; they
are not cryptographic protection against a malicious writer who can rewrite
the complete persisted artifact and recompute its hashes.

The authoritative event log additionally carries private, closed
`model_logical_death_recorded` boundaries at each alive-to-dead transition.
They are retained in operator persistence and replay but removed wholesale by
the shared redaction path for every public viewer, so hidden event cursors may
advance without revealing a death-boundary event or payload. Recovery requires
one exact owner for every boundary: a destruction cause, or pending typed
mortal-wound progress while a later Feel No Pain choice is unresolved.

Every revision from zero through the current head has an unpruned
`session-revision-commitment-v2` row. It commits to the previous revision,
typed command or non-command origin, exact decision/event/RNG prefixes,
adapter checkpoint, viewer-independent authoritative state, explicit `started`
and `closed` flags, journal entry and response when applicable, and
authenticated before/after cursor states. Those flags keep creation, start, and
final close transition semantics verifiable after their full snapshots are
pruned.
Recovery recomputes the chain against current authoritative history, checks
retained snapshots exactly, requires each protocol-command revision to have its
one matching journal entry, validates its envelope against the resulting
`DecisionRecord`, and recomputes retained response projections and cursor
positions. Pruning a full historical snapshot does not prune the revision or
idempotency commitment.

Store creation is an explicit operation, separate from recovery. A server
constructed with a store always requires an initialized root; a missing file or
singleton row is corruption/storage loss, never an empty first boot. A new
server invokes `initialize_persistence(...)` against empty in-memory state and
an exclusively reserved database path, then transactionally installs the exact
schema and initial empty root before accepting sessions. An interrupted
initialization leaves a non-loadable path that requires deliberate operator
repair or replacement; it is not inferred as a fresh authority. Session
creation is then durably committed before the new session enters the server
registry.

For a mutation, the server stages the facade, journal outcome, revision
snapshots and commitment, and cursor registry, commits them in one durable
transaction, then replaces the in-memory authority and publishes the response.
It arms fail-stop state before calling the store and clears it only after
successful return, including normalization of custom-store `OSError` and
`RuntimeError` commit failures. A crash before the transaction therefore
exposes only the previous complete revision. A crash after it recovers the new
revision and returns the persisted byte-equivalent public outcome for an exact
command retry.

The SQLite v2 implementation holds `BEGIN IMMEDIATE` while validating WAL mode,
`user_version = 2`, the exact STRICT singleton table and constraints, and the
absence of unexpected tables, indexes, foreign keys, views, or triggers. It
validates the old row, writes, then selects and compares the exact new row before
commit. Suppressed or rewritten writes, a deleted singleton row, schema drift,
or a schema mutation racing the write cannot be reported as successful.

Recovery validates schema, root and checkpoint hashes, package/ruleset/catalog/
source identities, engine/build/contract versions, principal bindings, cursor
authentication, the full revision chain, and the game/session index before
registering anything. It
loads the latest adapter checkpoint, replays its accepted decision tail through
the adapter-owned recovery path and ultimately `GameLifecycle.submit_decision(...)`,
restores and cross-validates the command journal without reapplying command
envelopes, and compares decision records,
authoritative events and sequence, RNG state, replay artifact, viewer
projection hashes, and session revision. Any corruption or drift is a typed
fail-closed result; no partially reconstructed session is addressable.

Exactly one process or actor owns mutation for a session and serializes its
commands. Immutable viewer-scoped projections may serve reads. Failover may
transfer ownership only at a verified checkpoint/replay boundary, with exact
role, player, authorization-epoch, cursor-scope, retention, and finalization
state so recovery cannot widen visibility.

These content hashes, revision commitments, and build fingerprints are an
internal-consistency boundary. They detect accidental corruption, partial
writes, history mismatches, and runtime drift; they are not keyed storage
attestations. A malicious database writer can rewrite a complete coherent
artifact, and an older valid database can be rolled back undetectably without
state outside that database. Deployments that include either threat need a
trusted external monotonic, signed, or append-only anchor. Phase 18L does not
claim malicious-writer or rollback resistance.

## Suggested Adapter Loop

An adapter loop should look like this:

```python
status = session.start(config)

while status is not None:
    if status.decision_request is None:
        status = session.advance_until_decision_or_terminal()
        continue

    view = session.view(viewer_player_id=acting_viewer_id)
    request = status.decision_request

    if request.is_parameterized_submission_request():
        payload = build_parameterized_payload_from_view(view, request)
        status = session.submit_parameterized_payload(
            request_id=request.request_id,
            payload=payload,
            result_id=next_result_id(),
        )
    else:
        option_id = choose_finite_option_from_view(view, request)
        status = session.submit_option(
            request_id=request.request_id,
            option_id=option_id,
            result_id=next_result_id(),
        )
```

The functions that render UI controls, query a human, call an AI policy, or serialize network packets can vary by adapter. The resulting `submit_option(...)` or `submit_parameterized_payload(...)` call should not.

## Practical Examples

### Secondary Mission Selection

Human UI:

- Render Tactical and legal Fixed combinations.
- User chooses a visible option.
- Submit a finite option result.

AI:

- Score the same finite option IDs from the request.
- Submit a finite option result.

Network client:

- Receive viewer-scoped request.
- Send selected option ID to server.
- Server resolves it against the current pending request.

Public event stream:

- Before every player has selected, opponents see only `{selected: true, hidden: true}` style metadata.
- After every player has selected, `secondary_missions_revealed` exposes each player's mode and Fixed mission IDs, and projections show the revealed secondary choices to all viewers.

### Normal Move

Human UI:

- User clicks Normal Move.
- Engine emits a movement proposal request.
- User drags models.
- UI builds a `PathWitness` and submits a movement proposal payload.

AI:

- Policy selects Normal Move.
- Solver generates candidate final poses and a `PathWitness`.
- AI submits the same movement proposal payload shape.

Network client:

- Client sends `selected_option_id: "normal_move"`.
- Server returns parameterized proposal request.
- Client sends serialized proposal payload.
- Server validates and mutates through engine code only.

### Strategic Reserves

Human UI:

- User selects a reserve unit.
- Engine emits a placement proposal request with `proposal_kind: "strategic_reserves_placement"`.
- User places models on legal board edge.
- UI submits attempted placement payload.

AI:

- Reserve-placement search creates attempted placement payload.
- Engine validates Strategic Reserves restrictions, coherency, and battlefield placement before mutation.

## Summary Rule

The adapter boundary is a choice boundary, not a rules boundary.

Adapters choose, render, transmit, or generate submissions. The engine validates, mutates, records, and replays them.
