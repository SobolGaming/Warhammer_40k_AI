# Adapter Decision Contract

Status: Phase 11D contract with Phase 11E scoring projection/event-stream additions, Phase 12A reaction/sequencing decisions, Phase 12B Stratagem decision requirements, Phase 12C supported Core Stratagem handler requirements, Phase 13/14H shooting decision requirements, Phase 14B End of Opponent's Movement phase reaction timing, Phase 14J Tactical secondary score/retain decisions, Phase 14L ranged attack target/group gathering decisions, Phase 15A charge declaration decisions, Phase 15B Charge Move proposal decisions, Phase 15C fight activation/pass/interrupt decisions, Phase 16A deployment setup decisions, Phase 16B redeploy/Scout pre-battle decisions, Phase 16C reserve declaration decisions, Phase 16E setup completion gate requirements, Phase 17G fight activation ability decisions, Phase 17G Movement-end surge decisions, Phase 17G phase-end objective-control retention, and Phase 18A hybrid catalog/live unit-model display projection requirements. This document is authoritative for adapter/proposal modules shipped with Phase 11D and future decision work.

This document is the Phase 11D submission contract, extended with Phase 11E scoring visibility rules, Phase 12A timing/reaction/sequencing rules, Phase 12B Stratagem decision rules, Phase 12C supported Core Stratagem handler rules, Phase 13/14H shooting decision rules, Phase 14B End of Opponent's Movement phase reaction timing, Phase 14J Tactical secondary score/retain decisions, Phase 14L ranged attack target/group gathering decisions, Phase 15A charge declaration decisions, Phase 15B Charge Move proposal decisions, Phase 15C fight activation/pass/interrupt decisions, Phase 16A deployment setup decisions, Phase 16B redeploy/Scout pre-battle decisions, Phase 16C reserve declaration decisions, Phase 16E setup completion gate requirements, Phase 17G fight activation ability decisions, Phase 17G Movement-end surge decisions, Phase 17G phase-end objective-control retention, and Phase 18A hybrid catalog/live unit-model display projection requirements, for teams building UI, CLI, headless, network, replay, or AI adapters around CORE V2.

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

## Core Objects

The shared contract uses these objects and payloads:

- `DecisionRequest`: engine request for one player choice.
- `FiniteOptionSubmission`: adapter wrapper for selecting one finite option.
- `ParameterizedSubmission`: adapter wrapper for submitting JSON-safe proposal payloads.
- `DecisionResult`: engine-facing result created from a submission and pending request.
- `DecisionRecord`: replay-facing record of a request/result pair.
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
- `FightMovementProposal`: Fight phase Pile In or Consolidate movement answer containing proposal kind `pile_in` or `consolidate`, the selected fight movement mode/action, selected target unit or objective context, and a `PathWitness` unless the player submits the no-move choice.
- `MeleeDeclarationProposalRequest`: Fight phase parameterized request exposing current melee weapon options, model-engaged target snapshots, the source activation decision context, and ruleset descriptor hash.
- `MeleeDeclarationProposal`: Fight phase parameterized answer selecting each fighting model's primary melee weapon, optional `[EXTRA ATTACKS]` weapons, and target allocations for those melee weapons.
- `PlacementProposalPayload`: parameterized placement answer, including attempted `UnitPlacement`.
- `DeploymentPlacementRequest`: Deploy Armies parameterized request context containing source mission setup, owning deployment zone IDs, selected rules-unit/component/model IDs, ruleset hash, and setup-step context.
- `DeploymentPlacementProposal`: Deploy Armies placement answer containing the complete selected rules-unit model placement set, placement kind `deployment`, proposal request ID, ruleset hash, and replay-safe source context.
- `BattleFormationDeclarationState`: Declare Battle Formations reserve declaration state containing the next player, completed players, and per-player available reserve declaration counts.
- `ReserveDeclarationRequest`: finite setup request context for declaring Strategic Reserves or Deep Strike units during `declare_battle_formations`.
- `ReserveDeclarationSelection`: finite reserve declaration answer selecting one emitted reserve declaration option or `complete_reserve_declarations`.
- `PreBattleProposalRequest`: redeploy and Scout pre-battle parameterized request context containing setup step, source decision context, selected rules-unit/component/model IDs, owning deployment-zone payloads, source rule ID, action kind, proposal kind, and ruleset hash.
- `PreBattlePlacementProposal`: redeploy or Scout reserve setup placement answer containing the complete selected rules-unit model placement set, placement kind, action kind, source rule ID, and replay-safe source context.
- `ScoutMoveProposal`: Scout Move answer containing action kind `scout_move` or `dedicated_transport_scout_move`, source rule ID, selected Scout distance, and a per-model `PathWitness`.
- `PreBattleActionRecord`: deterministic replay-safe setup action record for redeploy completion, redeploy placement, pre-battle completion, Scout reserve setup, Scout Move, and Dedicated Transport Scout Move.
- `SetupCompletionGate`: engine-owned setup-to-battle audit invoked only by lifecycle advancement at the final setup step.
- `SetupLegalityReport`: deterministic readiness report containing typed setup completion violations, decision-drain state, and pre-battle readiness snapshot.
- `SetupReplayCheckpoint`: deterministic state checkpoint emitted before and after battle start.
- `BattleStartRecord`: deterministic battle-start payload emitted when setup completion succeeds.
- `ProposalValidationResult`: typed valid, invalid, stale, or unsupported diagnostics.
- `EventRecord`: deterministic event-log payload.
- `GameViewPayload`: read-only viewer projection for adapters.
- `RulesCatalogViewPayload`: cacheable source-hashed static catalog display
  projection for datasheets, model profiles, weapon profiles, factions,
  detachments, enhancements, wargear, wargear options, and base sizes.
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
- `SequencingDecision`: finite order choice for simultaneous rule conflicts after active-player or roll-off ownership is determined.
- `PersistingEffect`: replay-safe effect state with deterministic expiration and unit-ID ownership across Embark/Disembark and Attached-unit splits.

Relevant modules:

- `src/warhammer40k_core/adapters/contracts.py`
- `src/warhammer40k_core/adapters/decisions.py`
- `src/warhammer40k_core/adapters/projection.py`
- `src/warhammer40k_core/adapters/event_stream.py`
- `src/warhammer40k_core/adapters/local_session.py`
- `src/warhammer40k_core/engine/decision_request.py`
- `src/warhammer40k_core/engine/decision_result.py`
- `src/warhammer40k_core/engine/decision_record.py`
- `src/warhammer40k_core/engine/movement_proposals.py`
- `src/warhammer40k_core/engine/deployment.py`
- `src/warhammer40k_core/engine/prebattle.py`
- `src/warhammer40k_core/engine/prebattle_records.py`
- `src/warhammer40k_core/engine/setup_completion.py`
- `src/warhammer40k_core/engine/charge_declaration.py`
- `src/warhammer40k_core/engine/phases/charge.py`
- `src/warhammer40k_core/engine/fight_order.py`
- `src/warhammer40k_core/engine/phases/fight.py`
- `src/warhammer40k_core/engine/timing_windows.py`
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

## Finite Decisions

Finite decisions are bounded option choices already enumerated by the engine. Examples include:

- secondary mission selection;
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
    selected_option_id="normal_move",
    result_id="ui-result-000017",
)
```

Adapter helper APIs should take `request_id` explicitly even when a local wrapper can infer the current pending request. Explicit request IDs let network, replay, and UI adapters fail fast on stale-client drift before constructing a `DecisionRecord`.

Movement action option payloads include the selected `movement_mode`. Default Normal Move and Advance keep their existing option IDs, while Take to the Skies variants append the mode, for example `normal_move:fly_take_to_skies` or `advance:fly_take_to_skies`. Fall Back options are explicitly mode-scoped: `fall_back:ordered_retreat` or `fall_back:desperate_escape`, with `:fly_take_to_skies` appended when that movement mode is selected. Remain Stationary resolves as a finite action. Normal Move, Advance, and Fall Back always emit a follow-up `submit_movement_proposal` request carrying the same mode context; adapters must submit the actual `PathWitness` and model poses through that parameterized request.

Accepted Fall Back proposals may include source-backed `fall_back_eligibility_grants` in the resulting `movement_activation_completed` event. These grants are replay-safe audit payloads produced by runtime faction content and do not create a new adapter choice. The Movement engine remains the only writer of `FellBackUnitState.can_shoot` and `FellBackUnitState.can_declare_charge`; Shooting and Charge phase selection consume those recorded permissions instead of adapters inferring Fall Back exceptions locally.

Phase 17G Movement-end surge rules use the same finite/proposal split as other
physical movement. After an enemy unit completes a Normal Move, Advance, or
Fall Back in the Movement phase, the engine may emit `select_triggered_movement`
for the reacting player. Optional surge windows include
`decline_triggered_movement`; each legal reacting unit is exposed through a
deterministic `surge:<unit_instance_id>` option. The option payload identifies
the selected rules unit, source hook, source rule, triggering unit, triggering
move event, and engine-rolled maximum surge distance. Selecting a surge unit
records only that finite choice and immediately emits a parameterized
`submit_movement_proposal` request with proposal kind `surge_move`. Adapters
must not roll the D6 locally, invent candidate units, move models from the
finite option payload, or continue the Movement phase while either request is
pending.

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
- `score_tactical_secondary_mission`: when the engine records a source-backed `TacticalSecondaryAchievementContext` proving that a Tactical Secondary Mission Card's requirements have been achieved, it emits a finite choice for that context. Merely having an active Tactical card is not sufficient to emit this decision. The selected option payload includes the `achievement_id`, card identity, scoring rule ID, scoring rule condition, scoring rule source ID, scoring timing, phase/round/actor context, and JSON-safe achievement evidence. The `score:<secondary_mission_id>` option awards the source-backed VP, marks the card scored/non-active, consumes the achievement context, and emits `tactical_secondary_mission_scored` with `discarded_after_score: true`. The `retain:<secondary_mission_id>` option awards no VP, leaves the card active, consumes the finite achievement context, and emits `tactical_secondary_mission_score_declined`. Stale score/retain submissions are rejected before queue pop if the achievement context is missing, mismatched, stale, no longer source-valid, no longer matches the active card, the phase/round/actor drifted, or the source-backed scoring metadata changed.
- `start_mission_action`: the engine emits legal source-backed Mission Action start options. Current support enumerates action/unit/target options for source-backed `objective_marker` actions such as Cleanse, `trappable_terrain_area` actions such as Death Trap's Booby Trap, and `plunderable_terrain_area` actions such as Plunder. Option payloads include `target_policy` and `target_kind`; `objective_marker` targets use objective marker IDs, while terrain-area targets use terrain feature IDs. `trappable_terrain_area` targets exclude terrain already trapped by that player and terrain fully within that player's deployment zone. `plunderable_terrain_area` targets exclude terrain fully within that player's deployment zone and are limited to one plundered terrain area per player turn. Cleanse objective targets exclude the player's home objective and objectives already selected for that player's Cleanse actions this turn. The engine filters units through the source `eligible_unit_policy`, excludes battle-shocked units and units that already shot when the action starts in the Shooting phase, and persists the selected `target_id` in `MissionActionState`. Immediate zero-VP actions complete in the same decision handler without creating a VP transaction; Booby Trap records an engine-owned terrain trap state for later primary scoring and Plunder records an engine-owned terrain plunder state for later secondary scoring. Turn-end zero-VP Cleanse completion validates objective control through the engine objective-control resolver and records an engine-owned objective cleanse state instead of creating a VP transaction. Mission Action target policies that are not yet represented as finite options must return a typed `unsupported` status instead of exposing an adapter mutation path.

These mission-scoring decision types must be submitted through `FiniteOptionSubmission -> DecisionResult -> GameLifecycle.submit_decision(...)`. Tests, replay, UI, CLI, network, and headless adapters must not call `GameState.discard_tactical_secondary(...)`, `GameState.score_secondary_mission(...)`, `GameState.record_tactical_secondary_replacement_use(...)`, or `GameState.record_mission_action_state(...)` directly for player choices; those methods are engine-owned primitives used by validated decision handlers and automatic rule hooks.

## Phase 12A Reaction And Sequencing Decisions

Phase 12A adds typed timing windows, reaction windows, sequencing conflict resolution, and persisting effects. These mechanics do not create a second adapter path.

Reaction windows that require a player choice emit an interrupt-style finite `DecisionRequest`. The current finite decision type is `resolve_reaction_window`. The request payload includes:

- `reaction_window`: the typed timing window payload;
- `interrupts_parent: true`;
- parent phase, parent step, and resume token;
- handler-specific JSON-safe context under `handler_payload`.

Adapters answer only by selecting one of the emitted option IDs. The reaction queue is lifecycle-persisted state and blocks parent phase execution until the engine records the `DecisionResult` through `GameLifecycle.submit_decision(...)` and emits `reaction_parent_resumed`. Adapters must not resume or mutate the parent phase themselves.

Sequencing conflicts use the finite decision type `resolve_sequencing_order`. During battle, the acting player is the active player. Before or after the battle, or at the start or end of a battle round, the engine first resolves a Phase 10J roll-off and makes the roll-off winner the request actor. Options enumerate deterministic participant orderings. Adapters must select one emitted ordering option and must not invent participant IDs or sort rule effects locally.

Persisting effects are authoritative engine state, not adapter state. Effects target stable unit IDs, remain associated with those IDs while units Embark/Disembark, transfer to surviving unit IDs when an Attached unit splits, and expire at deterministic lifecycle boundaries. Adapter projections may display public effect payloads, but clients must not apply or expire effects directly.

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

Accepted `StratagemUseRecord` payloads include `active_player_id`, `targeted_unit_instance_ids`, `affected_unit_instance_ids`, and `effect_selection`. The active-player ID is part of the phase-instance key for matched-play same-Stratagem and same-target restrictions. `targeted_unit_instance_ids` is the sorted canonical rules-unit list used for the 11th Edition "same unit targeted" restriction and is scoped to the player using the Stratagem. `affected_unit_instance_ids` records every canonical rules unit affected by the handler, including non-target enemy units hit by an effect. Non-attached units use their own unit instance ID. Units that are part of an attached unit use the attached-unit ID, so a Leader/Support component and Bodyguard component share one phase restriction key. Targetless Stratagems record empty target lists unless their official TARGET field binds a unit.

Source-backed records whose `handler_id` starts with `unsupported:` are catalog descriptors only. They must not emit finite options, must not emit parameterized pending requests, and stale or hand-crafted submissions for them must be rejected with `unsupported_handler` before queue pop, CP spend, or Stratagem-use record creation.

Adapters must not invent `use_stratagem` option IDs, derive new target bindings from displayed payloads, spend CP directly, apply effects directly, or bypass the lifecycle to call lower-level state mutation APIs.

Stratagem decisions may be offered to the non-active player from a reaction window. The acting player on the `DecisionRequest` is authoritative; adapters should not assume the turn player is the player answering the request.

Some Stratagems need target or placement details that are not safe to pre-enumerate. Those requests use a parameterized proposal instead of a finite bound option. The request must embed a typed proposal request payload with a Stratagem-specific proposal kind, the same source `use_stratagem` context used by finite options, the source-backed catalog record, the timing context, the CP cost, the restriction policy, the handler binding, and replay-safe target context. Examples include:

- exact reinforcement placement after a Stratagem grants a reserves placement;
- geometric, line-of-sight, model-target, or path-dependent target proposals once the owning phase has the required validators;
- any future Stratagem whose legal target binding cannot be represented as a finite option set.

Phase 12B introduces the initial parameterized Stratagem target-binding decision type `submit_stratagem_target_proposal` with proposal kind `stratagem_target_binding`. The pending `payload.proposal_request` carries the same request identity envelope as other parameterized proposals: `request_id`, `decision_type`, and `actor_id`, followed by the Stratagem target-binding fields. Adapters answer only with the fixed `submit_parameterized_payload` option and a payload containing the typed `proposal` object. `proposal.effect_selection` is JSON-safe handler-owned selection context for optional sections or nested target choices, such as Heroic Intervention mode, Crushing Impact enemy/model choice, or Epic Challenge character model choice. Stale phase/round, malformed shape, schema-invalid missing target binding, wrong player/game/Stratagem/catalog context, CP drift including optional additional CP, and illegal target binding are rejected before queue pop and before any CP transaction or Stratagem-use record is created.

Phase-integrated optional Stratagem windows may also be declined through the same lifecycle path. Finite `use_stratagem` windows include the engine-emitted option ID `decline_stratagem_window` with payload `{"submission_kind": "decline_stratagem_window"}`. Parameterized `submit_stratagem_target_proposal` windows are declinable only when the engine marks the request payload with `declinable: true`; adapters decline by submitting the fixed `submit_parameterized_payload` option with the same decline payload instead of a typed `proposal`. A decline records a `DecisionRecord`, emits `stratagem_window_declined`, spends no CP, creates no `StratagemUseRecord`, applies no effect, and suppresses re-opening the same game/player/round/phase/trigger/timing-window. Phase hooks that expose multiple optional Stratagem opportunities under the same phase and trigger must assign distinct `timing_window_id` values so declining one window cannot suppress a separate later window. Reaction-window declines resolve the reaction frame and then emit `reaction_parent_resumed`.

Parameterized Stratagem submissions follow the Phase 11D invalid-submission rule: stale, drifted, malformed, schema-invalid, or wrong-context payloads are rejected before the queue is popped or a `DecisionRecord` is created. They must not spend CP or mutate state. Accepted parameterized submissions apply the Stratagem use atomically through `GameLifecycle.submit_decision(...)`: the engine re-checks timing, CP, restrictions, target validity, spends CP, records `StratagemUseRecord`, emits `stratagem_used`, and applies any Phase-12B-supported handler/effect payload. Rule-invalid but well-formed proposals may be recorded as rejected attempts only when the specific proposal contract explicitly allows that behavior and emits a fresh pending request for retry.

Phase 12C source-backed Core Stratagems are adapter-visible through these handler bindings:

- `core:command-reroll`: finite `use_stratagem` option at `after_dice_roll`; the option payload context includes `trigger_payload.dice_roll_state` and `trigger_payload.affected_unit_instance_id`, and the source-backed catalog definition includes `eligible_roll_types` for the edition-specific roll classes that may be re-rolled. The affected unit ID is canonicalized into the resulting `StratagemUseRecord.affected_unit_instance_ids` before the engine enforces the one-Stratagem-per-unit-per-phase restriction; missing, unknown, wrong-owner, stale attached-unit, or otherwise malformed affected-unit context is rejected before option emission and before queue pop. The 11th Edition source list covers Hit, Wound, Damage, saving throw, Advance, Charge, Hazardous, and number-of-attacks rolls; the normalized number-of-attacks roll type is `number_of_attacks_roll`. It does not include Leadership, Battle-shock, Desperate Escape, or no-save allocation-order roll classes. Desperate Escape uses hazard rolls in 11th Edition. Runtime attack/save roll specs can remain precise (`attack_sequence.hit`, `attack_sequence.wound`, `attack_sequence.save.*`, and random Damage roll types); Command Re-roll normalizes those to source-backed roll classes before eligibility comparison. A real armour or invulnerable saving throw remains an `attack_sequence.save.*` roll even when its target number is above 6 and cannot succeed on a D6. Synthetic ordered-allocation dice for effects that permit no saving throw use `attack_sequence.allocation_order.no_save` and are not saving throws. The engine rejects unlisted non-roll-off roll types and roll actor drift before option emission and before queue pop. Single-die rolls and Charge rolls resolve through Phase 10J whole-roll reroll semantics. Non-Charge multi-dice rolls emit a nested `select_dice_reroll` finite request with one legal reroll option per die, and lifecycle submission must select one engine-emitted option ID. This can be offered in a Phase 12A reaction window, and the parent resumes only after `command_reroll_resolved` and `reaction_parent_resumed` are emitted.
- `core:insane-bravery`: parameterized `submit_stratagem_target_proposal` for a unit pending a Battle-shock test. Accepted use records a persisting auto-pass effect and the Command phase resolves the Battle-shock test as passed without adapter-owned mutation.
- `core:rapid-ingress`: parameterized target proposal for an unarrived reserves unit during the opponent Movement phase end. Accepted use spends CP and records the Stratagem use, then emits a `submit_placement_proposal` request using the existing placement proposal contract. The placement answer must also go through `GameLifecycle.submit_decision(...)`. When Rapid Ingress is offered from a Phase 12A reaction window, the reaction frame continues from the target proposal to the placement proposal and the parent resumes only after a valid placement resolves. Rule-invalid but well-formed placement proposals are recorded as rejected attempts and emit a fresh pending placement request for retry; stale, malformed, or wrong-context placement proposals are rejected before queue pop.
- `core:new-orders`: finite `use_stratagem` options for active Tactical secondary cards. The target binding uses `target_kind: "tactical_secondary_card"` and `target_secondary_mission_id`; accepted use costs 1 CP, is once per game, discards that card, and draws one replacement through engine-owned Tactical secondary state.
- `core:heroic-intervention`: parameterized target proposal at the end of the opponent Charge phase for one friendly unengaged unit within 12" of enemy units. `proposal.effect_selection.mode` is optional and defaults to `leap_to_defend`; `into_the_fray` adds the source-backed +1 CP cost and caps the Charge roll result at 6 before emitting a Heroic Intervention `submit_movement_proposal` with proposal kind `charge_move`. That movement proposal carries the Stratagem use, mode, charge-roll state, maximum distance, and reachable target snapshot in its context and requires the normal Charge Move `PathWitness` validation path.
- `core:counteroffensive`: parameterized target proposal in the opponent Fight phase just after an enemy unit has fought. Accepted use costs 2 CP, validates that the target is eligible to fight through `FightOrderState`, records a Fights First effect until end of phase, and records the selected activation with a `counteroffensive:<stratagem_use_id>` interrupt ID before lifecycle progression resumes.
- `core:crushing-impact`: parameterized target proposal in the active player's Charge phase just after the selected friendly MONSTER/VEHICLE ends a Charge Move. `proposal.effect_selection.enemy_target_unit_instance_id` selects one engaged enemy unit and `proposal.effect_selection.model_instance_id` selects one engaged source model. Accepted use rolls D6 equal to that model's Toughness, applies self mortal wounds for each 1, enemy mortal wounds for each 5+ capped at 6, and emits `crushing_impact_resolved`.
- `core:epic-challenge`: parameterized target proposal just after a friendly CHARACTER unit is selected to fight. `proposal.effect_selection.character_model_instance_id` selects one CHARACTER model in the target unit. Accepted use records a per-phase Precision effect for that model's melee weapons and emits `epic_challenge_precision_registered`.

Phase 14G freezes the Charge/Fight ruleset contract but does not emit new player-facing decisions. `RulesetDescriptor.charge_policy` defines after-roll charge-target selection, 12" declaration/target-selection gates, rolled-distance target eligibility, charge-move endpoint constraints, and the Fights First grant. `RulesetDescriptor.fight_policy` defines the Start/Pile In/Fight/Consolidate/End step order, Fight-step-start engagement eligibility, current-engagement eligibility, charged-this-turn eligibility, Fights First and Remaining Combats ordering bands, both-player pile-in/consolidation sequencing, the more-than-5" eligible-pass rule, explicit Normal/Overrun fight types, and Ongoing/Engaging/Objective consolidation modes. Phase 15 Charge/Fight implementations must consume these source-contract payloads and then add or update this document for every finite option family, proposal kind, pending request payload, decision record, or event shape they expose.

Phase 15C emits finite Fight phase activation decisions with decision type `select_fight_activation`. Phase 15C derives activation requests from `FightOrderState`, while `FightPhaseState` remains the outer phase envelope. The pending request payload includes `game_id`, `battle_round`, `phase: "fight"`, `active_player_id`, the actor `player_id`, the exposed Fight step states (`start`, `pile_in`, `fight`, `consolidate`, `end`), the current ordering band (`fights_first` or `remaining_combats`), one replay-safe eligibility context per currently legal unit, and `eligible_pass_available`. Fight eligibility payloads preserve the source semantics: charged this turn, currently engaged, or engaged at the start of the Fight step. Activation option IDs are deterministic: `fight:<fight_type>:<unit_instance_id>`, where `fight_type` is `normal` or `overrun`, and the engine emits only fight types legal for that context. Option payloads include `submission_kind: "select_fight_activation"`, the selected unit, the explicit fight type, ordering band, and the full eligibility context. Adapters must select one emitted option ID and must not infer fight eligibility, fight type, ordering band, or step cursor locally. Stale player, ordering-band, unit-eligibility, fight-type, or eligibility-context drift is rejected before queue pop and before any activation record or event is created.

Phase 17G may emit a finite selected-to-fight ability decision with decision type `select_fight_activation_ability` after a unit is selected to fight and before its melee declaration request. The pending request payload includes the active `FightActivationSelection`, the selected unit, battle round, active/actor player IDs, one or more source-backed `ability_options`, and `decline_option_id: "decline_fight_activation_ability"`. Use options have deterministic option IDs `use:<ability_id>` and payloads containing `submission_kind: "use_fight_activation_ability"`, `hook_id`, `source_id`, `ability_id`, `enhancement_id`, selected unit, activation request/result IDs, `model_proximity_inches`, `effect_kind: "fight_activation_melee_targeting_distance"`, and replay payload. The decline option uses `decline_fight_activation_ability` and records no effect. Accepted use submissions record an engine-owned `PersistingEffect` that scopes the melee targeting permission to the current activation result; adapters must not mutate melee target lists or attack pools directly. Stale activation context, repeated window use, wrong unit/player, malformed payloads, or option drift reject before queue pop.

Phase 15C eligible-to-fight passes are finite options on `select_fight_activation` using option ID `eligible_to_fight_pass`. The pass option is emitted only when every currently eligible unit for the actor is more than the source-backed pass distance (`RulesetDescriptor.fight_policy.eligible_pass_distance_inches`, currently 5") from all enemy units. The option payload includes `submission_kind: "eligible_to_fight_pass"`, the actor, ordering band, pass distance, and the eligible unit snapshot. Adapters must not synthesize a pass option. Stale unit snapshots, player drift, ordering-band drift, or pass-distance drift reject before queue pop.

Phase 15C fight interrupts use the Phase 12A reaction queue and decision type `resolve_fight_interrupt`. The request payload includes the ordinary reaction wrapper (`reaction_window`, `interrupts_parent`, and parent resume metadata) plus a handler payload with `phase_body_status: "fight_interrupt_required"` and a `FightInterruptRequest`. The engine emits a deterministic decline option `decline_fight_interrupt` and deterministic activation options using the same `fight:<fight_type>:<unit_instance_id>` option IDs and eligibility payload shape as normal fight activations, with `submission_kind: "select_fight_interrupt"` and the interrupt payload embedded. Accepted interrupt selections record the activation through the same fight-order state, append a `ResolvedFightInterrupt` for the trigger-specific interrupt ID and underlying `source_effect_id`, and resume the parent reaction frame. Declines append the same source-scoped consumption record and resume the parent frame. Hand-crafted, repeated-source, stale, wrong-context, or ineligible interrupt submissions reject before queue pop. Repeated-source validation is keyed by the source effect ID, not only by a trigger-event-specific interrupt ID.

Phase 15D implements Pile In, melee declaration/attack resolution, and Consolidate through the same lifecycle decision path. Normal fights are still not modeled as activation-local Pile In -> attacks -> Consolidate flows: Pile In and Consolidate are separate both-player steps, while Overrun Fight has its own activation-local additional Pile In before melee attacks. Activation events no longer emit `phase15d_resolution: "deferred"`.

Phase 15D Pile In and Consolidate use `submit_movement_proposal` with proposal kinds `pile_in` and `consolidate`. The pending proposal request is actor-scoped to the unit currently selected for that Fight movement step and exposes `phase: "fight"`, `movement_phase_action` (`pile_in` or `consolidate`), `movement_mode` (`pile_in` or `consolidate`), maximum distance, legal target-unit IDs, legal consolidation modes when applicable, objective context when applicable, source fight-step timing context, and the ruleset descriptor hash. Adapters answer with `ParameterizedSubmission` and the fixed `submit_parameterized_payload` option. The payload is a `FightMovementProposal` containing `proposal_request_id`, `proposal_kind`, `unit_instance_id`, `movement_phase_action`, `movement_mode`, target-unit fields (`pile_in_target_unit_instance_ids` or `consolidate_target_unit_instance_ids`), optional `consolidation_mode`, optional `objective_id`, and `witness` when models physically move. A no-move answer has no selected target/objective context and no witness. Stale, malformed, wrong-kind, wrong-action, wrong-mode, wrong-unit, illegal target/mode/objective, no-move-with-witness, target-without-witness, or witness-start/model-ID drift submissions reject before queue pop and before a `DecisionRecord`. Rule-invalid but well-formed fight movement proposals, including degenerate repeated-endpoint paths, over-distance paths, terrain/pathing/coherency failures, or invalid engagement/objective endpoints, are recorded as rejected attempts, emit typed diagnostics, retry with a fresh request, and do not mutate battlefield state.

Phase 15D melee declarations use decision type `submit_melee_declaration` with proposal kind `melee_declaration`. The pending request contains one `submit_parameterized_payload` option and `payload.proposal_request` with `phase: "fight"`, active/actor player IDs, `unit_instance_id`, source fight activation request/result IDs, `ruleset_descriptor_hash`, `target_unit_instance_ids`, and `available_weapons`. Each available weapon payload includes `model_instance_id`, `wargear_id`, `weapon_profile_id`, full `weapon_profile`, `is_extra_attacks`, `maximum_declared_targets`, `fixed_attacks`, and `engaged_target_unit_instance_ids` for that model/weapon. Source-backed fight activation ability effects may add target unit IDs to these engine-emitted `engaged_target_unit_instance_ids` snapshots for the current activation only. Adapters must select only from these engine-emitted weapon and target payloads; they must not infer engagement, weapon ownership, attack counts, melee weapon keywords, or fight ability targeting permissions locally.

`MeleeDeclarationProposal` submissions contain `proposal_request_id`, `proposal_kind: "melee_declaration"`, player ID, battle round, `unit_instance_id`, source activation request/result IDs, and one or more `MeleeWeaponDeclaration` entries. Each declaration has `attacker_model_instance_id`, `wargear_id`, `weapon_profile_id`, and `target_allocations`; each target allocation has `target_unit_instance_id` and, when required for split attacks, `attacks`. While fighting, each fighting model with a legal engaged target and an available non-extra melee weapon must declare exactly one non-extra primary melee weapon. `[EXTRA ATTACKS]` weapons owned by that model may be added as separate declarations and do not count as the primary. Each declared target must be in that weapon payload's `engaged_target_unit_instance_ids`. A weapon cannot declare more target units than its Attacks characteristic. When more than one target is selected for one weapon, each target must receive at least one attack and the declared attacks must sum to the fixed Attacks characteristic; random-Attacks split declarations are typed invalid until a fixed count exists. A single target may omit `attacks`, in which case the engine gathers that weapon's full attack count through the shared attack-dice logic.

Accepted melee declarations lower to shared `RangedAttackPool` records with `source_phase: "fight"` and `targeting_rule_ids` including `fight_phase_melee`. The subsequent Making Attacks sequence is the same shared engine path as Shooting: `select_resolve_target_unit`, `select_attack_weapon_group`, hit, wound, allocation order, damage allocation, save, Feel No Pain, and destruction-reaction decisions use their existing option payload shapes, but their pending request/status payloads remain Fight-owned with `phase: "fight"` and attack contexts carry `source_phase: "fight"`. Stale, malformed, wrong-proposal-kind, wrong-source-activation, descriptor-hash drift, missing required primary weapons, duplicate declarations, invalid extra-attack use, invalid target allocation, invalid split counts, or model-engagement drift reject before queue pop and before any attack sequence or battlefield mutation is created.

Phase 15E adds these Stratagem-coupled Charge/Fight decisions:

- Heroic Intervention target selection uses `submit_stratagem_target_proposal`; accepted use may emit a nested `submit_movement_proposal` Charge Move request. The nested request context includes `stratagem_handler_id: "core:heroic-intervention"` so lifecycle routes it back through the Heroic Intervention charge validator. Reaction frames may carry this movement proposal and only resume after the proposal resolves.
- Counteroffensive and Epic Challenge are `submit_stratagem_target_proposal` requests emitted from Fight-step timing hooks. Counteroffensive target proposals are reaction-window requests for the opponent after an enemy unit has resolved attacks. Epic Challenge target proposals are declinable requests for the player whose CHARACTER unit has just been selected to fight.
- Crushing Impact is a Charge-phase `submit_stratagem_target_proposal` after a friendly MONSTER/VEHICLE ends a Charge Move. Its nested enemy/model selections are carried in `effect_selection`, not in adapter-owned state.

Adapters must not synthesize these timing windows, `effect_selection` keys, charge-move reachable-target snapshots, model Toughness rolls, Fights First effects, Precision effects, or mortal-wound applications. They select pending options or submit the pending proposal shape, and the engine owns validation and mutation.

Phase 14H updates Transport Disembark decisions to expose the source-backed `disembark_mode` on every pending `select_disembark_unit`, `submit_placement_proposal`, Disembark selection payload, Disembarked unit state, destroyed-Transport disembark payload, and `unit_disembarked` event. Valid mode tokens are `rapid_disembark`, `tactical_disembark`, `combat_disembark`, `destroyed_transport`, and `emergency_disembark`. Adapters must submit the pending mode token unchanged unless the pending placement proposal context exposes an explicit `allowed_disembark_modes` list containing the submitted token; stale, malformed, omitted, or wrong-mode finite and parameterized submissions reject before authoritative mutation. Tactical and Rapid Disembark placement is always submitted through `submit_placement_proposal`; adapters must not infer or synthesize model placement from finite option payloads. `rapid_disembark` is used for post-Normal/Ingress Transport movement and records no further movement or charge permission. `tactical_disembark` is used for pre-move stationary/not-yet-selected Transports, forbids choosing Remain Stationary afterward, and routes the unit back through the shared Movement action decision path. When a pre-move Tactical placement proposal advertises both `tactical_disembark` and `combat_disembark` in `allowed_disembark_modes`, a submitted Combat placement is accepted only after the engine first evaluates the same submitted placement as Tactical and records deterministic Tactical-invalid fallback evidence; if that Tactical placement is legal, the Combat submission is rejected and the placement request is re-emitted. `destroyed_transport` and `emergency_disembark` are replay/domain modes for the corresponding source-backed destroyed-Transport rule paths and must not be inferred locally from placement distance; the engine emits the required placement proposal from the actual destruction event before Transport removal and Deadly Demise resolution, and lifecycle submission routes the accepted placement back through the owning attack sequence. `combat_disembark` has a dedicated domain resolver for 6" placement, official 1-2 Hazard Rolls, shared mortal-wound/Feel No Pain routing, Battle-shock, no-charge state, and the narrow permission to set up engaged only with enemy units engaged with the Transport.

Phase 14H Healing Wounds effects resolve through the finite `select_healing_model` decision only when the next one-wound healing step has multiple legal targets. The engine iterates each healing amount separately: wounded models are healed before any revival; if the unit is below Starting Strength and every alive model is at full wounds, one destroyed removed model is returned using REVIVED placement evidence at 1 wound; if the unit is at Starting Strength and full wounds, the step records no effect. Ambiguous wounded-model choices and ambiguous destroyed-model revival choices are actor-scoped to the opposing player. Option IDs are emitted by the engine, and option payloads include `submission_kind: "select_healing_model"`, `selection_kind` (`heal_wound` or `revive_model`), `effect_id`, `target_unit_instance_id`, `step_index`, the selected `model_instance_id`, `legal_model_ids`, source rule/context, and the explicit revival placement payload when selecting a revived model. Adapters must select one pending option ID and must not invent model IDs, revive placements, or wound mutations from local state. Stale effect, step, legal-candidate, actor, source-context, malformed, wrong-option, or wrong-selection-kind submissions reject before queue pop and before battlefield or army mutation. Accepted revival placement remains engine-validated for Starting Strength, removed-model identity, coherency with phase-start battlefield models, and the rule that revived models may be set up engaged only with enemies already engaged with the unit.

Phase 14I defines the finite `select_weapon_ability_instance` request shape and helper for duplicate source-backed weapon ability instances when the PDF timing gives the controlling player a choice. Phase 13B Shooting declaration target candidates embed this request under `required_weapon_ability_selections` for duplicate matching `[ANTI]` descriptors, and adapters must copy the selected option ID into the matching `WeaponDeclarationPayload.selected_weapon_ability_ids` entry before submitting the declaration. Other attack/targeting hosts that can encounter duplicate instances must call the helper and route the selected descriptor ID before resolving that duplicate ability. The request payload includes `submission_kind: "select_weapon_ability_instance"`, `weapon_profile_id`, `ability_kind`, canonical `target_keywords`, and replay-safe `source_context`. Option IDs are the selected structured ability descriptor IDs; option payloads repeat the submission kind, weapon profile ID, ability kind, selected ability ID, and the full ability descriptor payload. Adapters must select one emitted option ID and must not synthesize ability IDs from text. If no duplicate choice exists for the current target and timing, no request is emitted. Runtime helpers reject duplicate ability use without an explicit selected ability ID.

CP totals, CP ledger transactions, and normal Stratagem-use events are public in matched play. Viewer-scoped projections expose public CP ledger data under `public_command_point_ledgers` and public Stratagem-use records under `public_stratagem_use_records`. Adapter event deltas may expose normal CP and Stratagem events to every player unless a future source-backed hidden rule explicitly marks a pending decision, record, or event hidden. Any hidden Stratagem rule must update this document before implementation and must not leak hidden information through option counts, payload fields, event metadata, or derived projection data.

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

Phase 13A terrain visibility, line of sight, and cover foundation does not create player-facing choices. Its `LineOfSightWitness` and `BenefitOfCoverResult` payloads are engine-owned evidence consumed by later shooting decisions and events. `BenefitOfCoverResult` includes deterministic `source_records` with terrain feature ID, feature kind, LoS policy kind, and cover-source reason (`wholly_within_feature` or `not_fully_visible_because_of_feature`). Phase 13C attack allocation must request cover evidence with a single allocated target model in `target_models`; multi-model target contexts are selection/debug evidence only and must not drive final save/AP modifiers.

Phase 13B and later shooting slices add player-facing attacker and defender choices. They must not introduce UI, headless, replay, or network-specific mutation paths. Every accepted choice must pass through the same lifecycle submission path and produce deterministic replay-facing records.

Attacker shooting decisions include:

- finite `select_shooting_unit` choices for the active player when more than one unit can be selected or skipped;
- finite `select_shooting_type` choices for the selected unit before any in-phase shooting declaration is submitted;
- finite or parameterized target and weapon declaration choices, depending on whether the full action space can be safely enumerated;
- Firing Deck selections that bind each selected embarked model to at most one legal non-One-Shot ranged weapon, temporarily grant those attacks to the Transport, and mark the selected embarked units ineligible to shoot for the phase.

Phase 13B implements attacker selection and declaration with these adapter-visible decisions:

- `select_shooting_unit`: finite active-player choice. Option IDs are either the selected rules-unit `unit_instance_id` or `complete_shooting_phase`; for an active attached formation, the engine emits the attached rules-unit ID once and does not expose Bodyguard, Leader, or Support component IDs as separate shooting units. Unit option payloads include the selected `unit_instance_id`. The completion option uses `submission_kind: "complete_shooting_phase"` and includes deterministic `skipped_unit_ids` for all currently legal active-player units that completion will skip.
- `select_shooting_type`: finite active-player choice emitted after `select_shooting_unit` and before in-phase `submit_shooting_declaration`. Option IDs are engine-enumerated shooting type IDs such as `normal`, `assault`, `close_quarters`, or `indirect`. The request payload includes `game_id`, `battle_round`, `phase`, `active_player_id`, `unit_instance_id`, source unit-selection request/result IDs, and `legal_shooting_types`. Option payloads include `submission_kind: "select_shooting_type"`, the same source context, and the selected `shooting_type`. Stale, drifted, wrong-actor, or wrong-option submissions reject before queue pop and before mutation.
- `submit_shooting_declaration`: parameterized active-player choice. The request contains one `submit_parameterized_payload` option and `payload.proposal_request` with `proposal_kind: "shooting_declaration"`. In-phase requests include `payload.proposal_request.selected_shooting_type`; target candidate `shooting_types` are constrained to that selected type. Out-of-phase Fire Overwatch bypasses the in-phase type decision and emits a constrained `submit_shooting_declaration` request with source-forced `snap` shooting.
- `submit_shooting_declaration.payload.proposal_request.available_weapons`: current JSON-safe weapon options, including model ID, wargear ID, full weapon-profile payload, and optional Firing Deck source unit/model IDs.
- `submit_shooting_declaration.payload.proposal_request.firing_deck_value`: the selected Transport's descriptor-sourced Firing Deck value, or `null` when the unit has no Firing Deck descriptor.
- `submit_shooting_declaration.payload.proposal_request.target_candidates`: current JSON-safe target candidates with legality, violation diagnostics, visible-and-in-range target model IDs, line-of-sight witness, visibility cache key, engine-enumerated `shooting_types`, hit modifier, targeting rule IDs, and `required_weapon_ability_selections` for adapter-visible duplicate `[ANTI]` descriptor choices when a selected weapon profile has more than one matching Anti descriptor for that target. `[HUNTER X]` is represented as target eligibility: candidates for non-matching targets use violation code `hunter_target_keyword_mismatch`, and legal matching candidates carry `weapon-ability:hunter` in `targeting_rule_ids`.

Phase 13B shooting declaration submissions must use `selected_option_id: "submit_parameterized_payload"` and a `ShootingDeclarationProposal` payload containing:

- `proposal_request_id`, `proposal_kind: "shooting_declaration"`, player ID, battle round, acting unit ID, source request/result IDs, and visibility cache key;
- one or more `WeaponDeclaration` entries with attacker model ID, wargear ID, weapon profile ID, target unit ID, engine-enumerated `shooting_type`, selected duplicate weapon ability descriptor IDs in `selected_weapon_ability_ids`, and optional Firing Deck source unit/model IDs;
- optional `FiringDeckSelection` evidence with the Transport ID, descriptor-sourced Firing Deck value, selected embarked unit/model/wargear/profile bindings, and already-shot embarked unit IDs. At most the descriptor value's number of distinct embarked models may be selected, and each selected embarked model may contribute at most one non-One-Shot ranged weapon.

Accepted Phase 13B/14F declarations emit deterministic attack-pool payloads, including the selected `shooting_type` and selected duplicate weapon ability IDs, and `shooting_declaration_accepted` events. Legal shooting types are engine-enumerated values: `normal`, `assault`, `close_quarters`, `indirect`, or source-provided values such as `snap`. Adapters must submit the pending `select_shooting_type` option before an in-phase declaration, then select one of the declaration request target candidate's current `shooting_types`; they must not invent a shooting type, infer one from weapon keywords, or synthesize duplicate weapon ability IDs. Phase 13C/14E then consumes the declared `RangedAttackPool` records through the grouped Shooting phase lifecycle and may emit attacker target/group selection, attacker Precision, defender allocation-order, save, Feel No Pain, or destruction-reaction decisions before returning to the next shooting-unit selection. Rejected stale, malformed, drifted, invalid-shooting-type, invalid-target, invalid-weapon, invalid-profile, invalid-visibility, invalid-duplicate-weapon-ability-selection, or invalid-Firing-Deck submissions return typed invalid diagnostics before the pending request is popped and before a `DecisionRecord` is created.

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

Adapters must answer both decisions by selecting one pending option ID through
`GameLifecycle.submit_decision(...)`; they must not invent target IDs, group IDs,
signature hashes, pool indices, or mutate from option payloads. The lifecycle
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
- `select_feel_no_pain`: reserved finite defending-player choice for optional or competing Feel No Pain sources. Option IDs are source IDs, plus `decline` when the rules allow declining. `payload.lost_wound_context` and `payload.sources` are replay-safe and must be submitted through the same finite decision path. Normal lost wounds use `lost_wound_context.context_kind: "lost_wound"`; deferred mortal wounds, Explosives mortal wounds, Hazardous mortal wounds, and other routed mortal-wound packets use `lost_wound_context.context_kind: "mortal_wound"` and keep the pending mortal-wound application state in that replay-safe context until the choice resolves.

Phase 13E implements this destroyed-model attack-resolution decision:

- `select_destruction_reaction`: finite controlling-player choice emitted after attack-sequence damage destroys a model with one or more optional structured destruction-reaction sources. Option IDs are optional source IDs plus `decline_destruction_reaction`. Source options carry `payload.source_id`, `payload.reaction_kind`, and `payload.optional: true`, where supported optional `reaction_kind` values include `shoot_on_death` and `fight_on_death`; the decline option uses null source and kind values. `payload.destruction_context` contains the JSON-safe attack context, damage application, `model_destroyed` event ID, damage event ID, removal record, transition batch, `destroyed_model_controller_player_id`, and a nullable engine continuation payload. Adapters must submit one pending option ID through `GameLifecycle.submit_decision(...)` and must not start shooting, fighting, explosion, continuation, or removal mutations locally from the option payload. Accepted selections are recorded as destruction-reaction resolutions for the appropriate engine action host. Mandatory sources such as `deadly_demise` resolve automatically before destroyed-model removal, including trigger rolls, eligible nearby-unit mortal-wound packets, any secondary-casualty removal/reaction host, and any routed `select_feel_no_pain` choices; they must not be presented as destruction-reaction options.

Phase 13D adds this attacker-visible attack-resolution decision:

- `select_precision_allocation`: finite attacking-player choice at the start of the Allocation Order step while resolving attacks made with one or more `[PRECISION]` weapons against a unit containing visible eligible Character allocation groups. Option IDs are visible eligible Character `group_id` values plus `decline_precision`; Character options include `payload.selected_group_id` and `payload.selected_model_ids`, and the decline option uses `selected_group_id: null` with an empty model list. Grouped-host requests include the wounded pool's `attack_contexts` in the request payload. Accepted Character-group selection is pool-scoped until those attacks resolve or that Character group is destroyed, whichever happens first. In the grouped host, the selected Character group is carried as allocation-order `priority_group_ids` and promoted ahead of ordinary defender group order; remaining failed saves return to normal ordered groups after that Character group is destroyed. Declining, having no visible Character group, having no Precision source, or destruction of the selected Character group follows the normal defender allocation path.

Phase 13C/14H attack-resolution events are typed, ordered, and JSON-safe at hit, Critical Hit, wound, Critical Wound, allocate, save, and damage. Supported grouped-host weapon abilities preserve those event boundaries, including Lethal Hits skipped wound payloads, Sustained Hits generated-hit wound contexts, Precision priority-group allocation, and Devastating Wounds deferred mortal-wound packets. Phase 14H has one pooled save/damage resolver: adapters must not expect or submit single-attack allocation decisions during shooting attack resolution. Normal damage is resolved before deferred Devastating Wounds mortal-wound packets for the same attack pool. Internal grouped-damage continuation payloads are replay-safe engine state, not adapter-submitted payloads, and must not leak hidden information through viewer-scoped projections or event deltas.

If a shooting declaration is parameterized, the request must embed a typed proposal request with replay-safe source context:

- game ID, battle round, phase, active player, and acting unit ID;
- source request/result IDs when the declaration follows a finite unit-selection decision;
- selected model IDs, weapon IDs, profile IDs, target unit IDs, and any Firing Deck source model/weapon binding;
- the ruleset descriptor hash and line-of-sight/cache evidence required by target validation;
- visible viewer payloads that do not leak hidden opponent information.

Shooting proposals must reject stale, drifted, malformed, schema-invalid, wrong-actor, wrong-unit, wrong-phase, invalid-shooting-type, invalid-target, invalid-weapon, invalid-profile, invalid-Firing-Deck, or stale-visibility submissions before queue pop unless the exact proposal contract explicitly allows a rule-invalid but well-formed rejected attempt and emits a fresh pending request for retry. Phase 13B/14F does not allow recorded rule-invalid retry attempts for attacker declarations. Accepted submissions validate the previously selected shooting type, target legality, range, visibility, Lone Operative, Locked in Combat, Big Guns Never Tire, Close-quarters/Pistol, Blast engagement bans, Assault/Advanced weapon gating, Indirect per-weapon `[INDIRECT FIRE]` eligibility, Indirect visibility and no-Hit-reroll policy, Firing Deck, one-shot, Hazardous declaration obligations, and ruleset-specific targeting restrictions before mutation.

Defender allocation/save/defensive/destruction-reaction decisions may auto-resolve only when the rules leave exactly one legal outcome and no optional player choice. Otherwise the defending or destroyed-model controlling player is the `DecisionRequest.actor_id`, even though they may not be the active player. Adapters must not infer that Shooting phase decisions always belong to the active player. Stale, drifted, wrong-actor, wrong-option, or payload-mismatched destruction-reaction submissions return typed invalid diagnostics before queue pop and before a `DecisionRecord` is created.

Shooting decision records, attack-resolution events, line-of-sight witnesses, cover results, allocation records, save records, and damage/removal records must be deterministic and JSON-safe. Phase 13B normal shooting unit/declaration requests are public because they concern table-visible units, weapons, targets, and Transport Firing Deck use. Viewer-scoped projections and event deltas must not leak hidden information through option counts, target lists, payload metadata, rejected-proposal diagnostics, or derived fields.

Phase 13D supports these shooting-coupled Core Stratagem target proposals:

- `core:smokescreen`: opponent Shooting phase `after_unit_selected_as_target` proposal for a friendly `SMOKE` unit listed in `trigger_payload.selected_target_unit_instance_ids`. Accepted use grants Benefit of Cover and the structured hit-roll modifier effect that expires at the active shooting player's end-of-phase boundary.
- `core:explosives`: active-player Shooting phase proposal for a friendly `GRENADES` unit plus `trigger_payload.enemy_target_unit_instance_id`. Submissions are rejected before queue pop and CP spend if the source unit Advanced, Fell Back, already shot, is within Engagement Range, or if the enemy target is friendly, unknown, engaged with friendly units, not visible, or not within 8". Accepted use records both the friendly `GRENADES` unit and the enemy target in `StratagemUseRecord.affected_unit_instance_ids`, canonicalizing attached-unit components to their attached-unit rules identity, and emits `explosives_resolved` with `explosives_unit_instance_id`, `target_unit_instance_id`, deterministic roll state, mortal-wound count, and any routed mortal-wound application.
- `core:fire-overwatch`: opponent Movement phase `end_phase` proposal emitted from the End of Opponent's Movement phase reaction window for one friendly non-`TITANIC` unit that is unengaged, within 24" of a triggering enemy unit, and would be eligible to shoot if it were that player's Shooting phase. The triggering enemy unit must have been set up or started/ended a Normal Move, Advance, or Fall Back during that Movement phase. The trigger payload identifies that enemy unit with `moved_unit_instance_id`, uses `trigger_window: "end_opponent_movement_phase"`, and includes the eligible trigger classes under `eligible_trigger_kinds`. Target-proposal validation rejects out-of-range friendly units, engaged friendly units, `TITANIC` friendly units, shooting-ineligible friendly units, and friendly units without a legal constrained declaration before CP spend or Stratagem-use recording. Accepted use spends CP, records the Stratagem use, creates an out-of-phase shooting state with the parent phase and trigger payload, and emits a `submit_shooting_declaration` proposal whose legal targets are constrained to the triggering enemy unit. The resulting attack pools carry `core:fire-overwatch`; non-automatic hit rolls only succeed on unmodified 6s regardless of BS or modifiers, while Torrent weapons still auto-hit. Declaration and attack-sequence decisions are submitted through `GameLifecycle.submit_decision(...)`, and the Phase 12A reaction frame resumes only after the out-of-phase shooting state completes. Phase 14B emits Fire Overwatch before Rapid Ingress when both are available in the same End of Opponent's Movement phase window.

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

Phase 15A implements Charge phase eligibility, declaration, and deterministic charge-distance rolls. Phase 15B implements the post-roll Charge Move as a parameterized physical proposal. Adapters must not synthesize target selection, placement mutation, displacement records, or Fights First state from the Phase 15A roll payload; they must answer the pending Phase 15B proposal request.

Phase 15A exposes this active-player decision:

- `select_charging_unit`: finite active-player choice. Option IDs are either the selected `unit_instance_id` or `complete_charge_phase`. Unit option payloads include `submission_kind: "select_charging_unit"`, game, round, phase, active player, selected unit ID, target candidates, and the current eligibility context. The completion option uses `submission_kind: "complete_charge_phase"` and includes deterministic `skipped_unit_ids` for all currently legal active-player charging units.

Charge eligibility target candidates are engine-enumerated from battlefield state and the active ruleset's `charge_policy`. Phase 15A rejects chargers that Advanced, Fell Back, are within Engagement Range, are off the battlefield, already declared a Charge this phase, or have no enemy unit within the descriptor-sourced declaration range, currently 12", unless a future source-backed rule explicitly marks that unit as allowed to declare a charge.

Selecting a charging unit records the finite `DecisionRecord`, emits `charging_unit_selected`, and immediately rolls 2D6 through the deterministic dice manager with `roll_type: "charge_roll"`. There is no Phase 15A adapter-visible target declaration payload. The generated charge-roll `DiceRollSpec` includes `reroll_forbidden_rule_ids` with `phase15a:charge-roll-command-reroll-forbidden`, so Phase 15A Charge rolls must not emit a Command Re-roll request even though the source-backed 11th Edition Stratagem catalog contains Charge as an eligible roll class.

The `charge_roll_resolved` payload includes:

- `unit_instance_id`;
- `maximum_distance_inches`;
- `roll_result`, including source unit-selection request/result IDs;
- `reachable_target_distances_inches` and `reachable_target_unit_instance_ids`, containing only enemy units currently within both 12" and the rolled maximum distance.

If the roll leaves no enemy unit within both 12" and the rolled maximum distance, Phase 15A emits `charge_no_move_possible`, mutates no model placement, emits no displacement payload, and continues to the next charging-unit choice. If one or more reachable targets exist, Phase 15A records a `ChargeDistanceState`, emits `charge_move_required`, and emits a `submit_movement_proposal` request with proposal kind `charge_move`.

The Phase 15B Charge Move request uses the shared parameterized proposal wrapper:

- `decision_type: "submit_movement_proposal"`;
- `proposal_kind: "charge_move"`;
- `phase: "charge"`;
- `movement_phase_action: "charge_move"`;
- `unit_instance_id`: the charging unit;
- request context includes `movement_mode: "charge"`, `maximum_distance_inches`, `reachable_target_unit_instance_ids`, `reachable_target_distances_inches`, and the source `charge_roll` payload.

Adapters answer with `ParameterizedSubmission` and the fixed `submit_parameterized_payload` option. The payload is a `ChargeMoveProposal` object with:

- `proposal_request_id`;
- `proposal_kind: "charge_move"`;
- `unit_instance_id`;
- `movement_phase_action: "charge_move"`;
- `movement_mode: "charge"`;
- `charge_target_unit_instance_ids`: zero or more target IDs from the request's reachable target list;
- `witness`: a `PathWitness` for every model in the charging unit when one or more targets are selected.

An empty `charge_target_unit_instance_ids` tuple with no witness is the active player's no-move choice. It records `charge_move_declined`, mutates no model placement, emits no displacement payload, and grants no Fights First effect.

Malformed, stale, wrong-kind, wrong-unit, wrong-mode, unreachable-target, target-without-witness, no-move-with-witness, or witness-start/model-ID drift submissions reject before the pending queue is popped and before a `DecisionRecord` is created. Rule-invalid but well-formed Charge Move proposals, such as degenerate repeated-endpoint paths, over-distance paths, terrain/pathing/coherency failures, missing required target engagement, or non-target engagement, are recorded as rejected attempts with `charge_move_invalid`; the engine emits a fresh `charge_move` proposal request for retry and does not mutate authoritative battlefield state.

Accepted Charge Move proposals consume the shared movement/pathing/terrain/coherency validators. A valid move emits `charge_move_completed`, updates authoritative model placements through engine-owned mutation only, records `BattlefieldTransitionBatch.displacements` with `displacement_kind: "charge_move"` and `source_phase: "charge"`, records endpoint witness details, and registers a `PersistingEffect` with `effect_kind: "charge_grants_fights_first"` until the end of the turn.

Charge declarations and charge rolls are public table information in the current rules scope. Viewer-scoped projections and event deltas still must not leak hidden opponent information through option counts, target candidates, invalid diagnostics, roll metadata, or derived fields if future hidden deployment, reserve, or secret objective mechanics affect Charge eligibility.

Required Phase 15A adapter-contract tests:

- valid charging-unit selection through `FiniteOptionSubmission -> DecisionResult -> GameLifecycle.submit_decision(...)`;
- deterministic JSON-safe unit-selection, roll, decision-record, event, and lifecycle payload round-trip;
- Advanced, Fell Back, engaged, off-battlefield, and no-target eligibility gating;
- no-reachable-target Charge rolls produce no movement or displacement payload;
- reachable-target Charge rolls emit a `submit_movement_proposal` request with proposal kind `charge_move` and a post-roll target snapshot;
- valid Charge Move proposals through `ParameterizedSubmission -> DecisionResult -> GameLifecycle.submit_decision(...)` mutate only after shared validators pass, emit displacement records, and register Fights First;
- stale/malformed Charge Move proposals reject before queue pop and before a `DecisionRecord`;
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

- `select_redeploy_unit`: finite player choice during setup step `redeploy_units`. The engine emits one deterministic `redeploy:<rules_unit_id>` option for each currently legal redeploy candidate and always includes `complete_redeploys`. Option payloads include submission kind, game ID, player ID, setup step, selected rules-unit ID when applicable, component/model IDs, owning deployment-zone IDs, source rule ID, action kind, proposal kind, Scout metadata when present, mission/deployment/terrain source IDs, and ruleset descriptor hash. Adapters must select one pending option ID and must not synthesize redeploy targets from visible battlefield state.
- `select_prebattle_action`: finite player choice during setup step `resolve_prebattle_actions`. The engine emits deterministic `scout_reserve_setup:<rules_unit_id>`, `scout_move:<rules_unit_id>`, and `dedicated_transport_scout_move:<transport_unit_id>` options when those branches are legal, plus `complete_prebattle_actions`. Adapters must not invent Scout options, promote an embarked unit outside the Dedicated Transport branch, or mutate cargo/reserve/battlefield state from option payloads.

When both players have unresolved effects in the same Phase 16B setup step, the engine emits the Phase 12A finite `resolve_sequencing_order` request before `select_redeploy_unit` or `select_prebattle_action`. That sequencing request uses a before-battle timing window and a deterministic roll-off to choose the deciding player. Adapters must answer by selecting one emitted ordering option; they must not sort pre-battle participants locally or skip the sequencing request.

Selecting a redeploy or Scout action records the finite `DecisionRecord`, emits the corresponding selection event, and emits one of these parameterized requests:

- `submit_redeploy_placement` with proposal kind `redeploy_placement`;
- `submit_scout_reserve_setup` with proposal kind `scout_reserve_setup`;
- `submit_scout_move` with proposal kind `scout_move`.

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

Malformed, stale, wrong-actor, wrong-step, wrong-kind, wrong-ruleset-hash, wrong-unit, wrong-source-rule, omitted-model, extra-model, wrong-owner, wrong-component, wrong-placement-kind, missing-witness, witness-model drift, witness-start drift, Scout-distance drift, or stale reserve/cargo submissions reject before the pending queue is popped and before a `DecisionRecord` is created. Rule-invalid pre-battle proposals, including out-of-zone setup, terrain/objective endpoint failures, model overlap, Engagement Range violations, coherency failures, degenerate repeated-endpoint Scout paths, pathing/terrain failures, and Scout final positions not more than 8" horizontally from every enemy unit, return typed invalid diagnostics and do not mutate authoritative state.

Accepted Scout Move proposals consume the shared movement/pathing/terrain/coherency validators. A valid Scout Move emits `prebattle_scout_move_completed`, updates authoritative model placements through engine-owned mutation only, records `BattlefieldTransitionBatch.displacements` with `displacement_kind: "scout_move"` and `source_step: "resolve_prebattle_actions"`, and records `PreBattleActionRecord(action_kind="scout_move")` or `PreBattleActionRecord(action_kind="dedicated_transport_scout_move")`. It must not mark the unit as having Advanced, Fallen Back, Remained Stationary, shot, started a Mission Action, or moved in the Movement phase. Dedicated Transport Scout Move keeps cargo state intact.

Redeploy and Scout choices are public table setup information in the current Phase 16B rules scope. If a future mission, reserve, hidden deployment, or secret pre-battle mechanic hides setup information, pending requests, option lists, proposal diagnostics, placement/movement events, action records, projections, and event deltas must be viewer-scoped and must not leak hidden opponent information through counts, model IDs, source context, reserve/cargo state, or derived fields.

Required Phase 16B adapter-contract tests:

- valid redeploy unit selection and placement through the shared lifecycle path;
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

Phase 16C adds setup reserve choices during Declare Battle Formations, after battlefield creation and before Deploy Armies. These choices decide whether units start on the battlefield, in Strategic Reserves, or in a source-backed Deep Strike reserve state. AIRCRAFT mandatory reserve declarations are engine-owned consequences in the same setup step and are recorded as ordinary `ReserveState` payloads.

Phase 16C exposes the finite decision type `select_reserve_declaration`. The pending request payload contains `payload.reserve_declaration_request` with request ID, game ID, actor/player ID, setup step `declare_battle_formations`, ruleset descriptor hash, Strategic Reserves points limit, current Strategic Reserves points, and available declaration count. Adapters answer by selecting one emitted option ID:

- `declare_strategic_reserves:<unit_instance_id>` for a legal actor-owned unit with source-backed points that does not have `FORTIFICATION` and whose unit plus embarked-unit points fit the Strategic Reserves cap;
- `declare_deep_strike:<unit_instance_id>` for a legal actor-owned unit whose current source-backed unit keywords include Deep Strike;
- `complete_reserve_declarations` to record that the player is done choosing optional reserve declarations.

Option payloads are complete `ReserveDeclarationSelection` payloads. They include submission kind, action kind, game ID, player ID, setup step, ruleset descriptor hash, reserve origin/kind, source rule ID, selected unit ID, unit points, embarked unit points, Strategic Reserves points limit, current points, points after declaration, points contribution, embarked unit IDs, and source IDs. Adapters must not invent reserve option IDs, infer points from roster display data, mutate reserve state from payloads, or silently deploy a unit whose reserve declaration is illegal.

Accepted Strategic Reserves selections create deterministic `StrategicReserveDeclaration` and `ReserveState` payloads, enforce the battle-size 50% Strategic Reserves cap including embarked units, reject FORTIFICATIONS, preserve source rule IDs and points contribution, and exclude the unit from Deploy Armies options. Accepted Deep Strike selections create a Deep Strike `ReserveState` consumed later by the existing reserve-arrival placement proposal path. Accepted completion selections emit a replay-safe completion event and do not mutate reserve state.

Malformed, stale, wrong-actor, wrong-step, wrong-ruleset-hash, wrong-current-points, wrong-option, option-payload drift, duplicate, wrong-player, unknown-unit, over-cap, missing source-points, or forbidden-unit submissions reject before the pending queue is popped and before a `DecisionRecord` or reserve mutation is created. Rule-invalid reserve declarations must not be repaired by changing reserve kind, deploying the unit, or dropping it.

Reserve declaration choices are public table setup information in the current Phase 16C rules scope. If a future mission or hidden deployment rule hides reserve or battle-formation information, pending requests, option lists, completion counts, decision records, reserve states, events, projections, and event deltas must be viewer-scoped and must not leak hidden opponent information through unit IDs, points, option counts, source context, reserve kind, or derived deployment availability.

Required Phase 16C adapter-contract tests:

- valid Strategic Reserves selection through `FiniteOptionSubmission -> DecisionResult -> GameLifecycle.submit_decision(...)`;
- valid Deep Strike selection through the same lifecycle path;
- AIRCRAFT mandatory reserve state is source-backed and serialized as ordinary reserve state;
- Strategic Reserves points cap, missing points, FORTIFICATION filtering, duplicate declarations, wrong-owner units, and unknown units reject or remain absent before battle start;
- stale, malformed, wrong-context, and drifted submissions reject before queue pop and before mutation;
- declared reserve units are absent from Deploy Armies options and later use the shared Move Units reserve-arrival path;
- deterministic JSON-safe decision, reserve-state, event, lifecycle, and replay payload round-trip;
- viewer-scoped projection/event redaction for any future hidden reserve declaration information.

## Phase 16E Setup Completion Gate

Phase 16E does not add a new adapter-submitted decision type. Setup completion is an engine-owned lifecycle gate that runs only after setup decisions and proposal requests have drained and the ruleset setup sequence reaches its final step. Adapters must not submit a synthetic "start battle" result, force `GameState.enter_battle()`, mutate `setup_step_index`, or bypass `GameLifecycle.advance(...)`.

The gate audits the pending decision queue, reaction queue, final setup-step position, mustered armies, source-backed mission setup, Secondary Mission choices, Attacker/Defender state, battle formation declarations, reserve legality, deployment completion, battlefield coherency, redeploy state, and pre-battle actions. If any check fails, lifecycle advancement returns a typed invalid status with `invalid_reason: "setup_completion_gate_failed"` and a `setup_legality_report`; the pending queue is not popped, no `DecisionRecord` is created for battle start, and authoritative state remains in setup.

When setup is legal, lifecycle advancement emits `setup_completion_gate_passed` and `battle_started` events. The `battle_started` event payload is a `BattleStartRecord` containing the completed setup step, source ID, readiness snapshot, setup legality report, pre-battle checkpoint, post-battle-start checkpoint, battle round, active player, first battle phase, turn order, and ruleset descriptor hash. These payloads are JSON-safe replay data; they must not include Python object reprs, memory addresses, or adapter-local state.

Setup completion data is public table setup information in the current Phase 16E rules scope. If a future mission, deployment, reserve, or pre-battle rule hides setup information, invalid diagnostics, event deltas, projections, setup legality reports, replay checkpoints, and battle-start records must remain viewer-scoped and must not leak hidden opponent information through counts, option lists, source context, model IDs, reserve state, or derived readiness fields.

Required Phase 16E adapter-contract tests:

- full setup-to-battle advancement occurs only through lifecycle advancement after the pending setup decisions drain;
- direct setup-step bypass, pending decision queue entries, unresolved setup work, and bridge-only placement paths return typed invalid diagnostics and leave state in setup;
- legal setup emits deterministic `setup_completion_gate_passed` and `battle_started` event payloads with JSON-safe `SetupLegalityReport`, `SetupReplayCheckpoint`, and `BattleStartRecord` data;
- lifecycle/replay payload round-trip preserves the battle-start record;
- viewer-scoped projection/event redaction for any future hidden setup completion information.

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
status = submit_payload(
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
- `disembark_placement`.

The request's `placement_kinds` field enumerates the legal physical placement methods available for that unit and state. The submitted payload must match the pending request.

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

Serialized payload helpers may omit empty optional collections such as `large_model_exceptions` or `restriction_overrides`; inbound parsing accepts omitted empty optional fields.

The engine validates placement, coherency, reserve restrictions, transport state, and any rule-specific exceptions before mutating battlefield state.

## Validation and Invalid Results

Adapters should treat invalid proposal responses as authoritative diagnostics, not as local validation suggestions.

Finite requests use the existing selected-option equality rule: `DecisionResult.selected_option_id` must name one option on the pending `DecisionRequest`, and `DecisionResult.payload` must equal that option's payload.

Parameterized proposal requests use a different validation rule. The pending request still contains the fixed `submit_parameterized_payload` option, and the submitted `DecisionResult.selected_option_id` must be `submit_parameterized_payload`. For parameterized requests, `DecisionResult.payload` is the adapter's movement or placement proposal. It is validated against the embedded `ProposalRequestPayload`; it is not required to equal the fixed option payload `{"submission_kind": "parameterized"}`.

Before the queue is popped or a `DecisionRecord` is created, Phase 11D must validate:

- request ID drift;
- actor drift;
- decision type drift;
- proposal kind drift;
- unit drift;
- movement mode and Fall Back mode drift;
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

Mission setup terrain projections expose first-class display geometry under
`GameViewPayload.mission_setup.terrain_features[*].display_geometry`.
The display geometry payload uses schema `terrain-display-v1`, coordinate space
`battlefield_inches`, footprint kind `polygon`, optional `display_template_id`,
and an unclosed `footprint_polygon` list of `{x_inches, y_inches}` vertices.
Adapters should render terrain footprints from this typed display geometry.
`source_id` remains provenance only; adapters must not parse it to recover
terrain preset, origin, rotation, or footprint details.

Phase 18A extends the viewer projection for
[Issue #145](https://github.com/SobolGaming/Warhammer_40k_AI/issues/145) with a
hybrid projection model:

1. Static catalog projection/cache. `project_rules_catalog_view(...)` returns a
   `RulesCatalogViewPayload` with `projection_schema: "rules-catalog-view-v1"`,
   catalog identity, source package identity, `source_hash`, and display records
   for datasheets, model profiles, weapon profiles, factions, detachments,
   enhancements, wargear, wargear options, and base sizes. Adapters may cache this
   payload by catalog ID/schema/hash and render catalog browsing, roster panels,
   and tooltips from it.
2. Live viewer-safe unit/model projection. `GameViewPayload` uses
   `projection_schema: "game-view-v2-phase18a"`, includes
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
  and faction keywords, model instance IDs, selected wargear IDs, visibility
  status, and redaction metadata.
- `ModelDisplayPayload` records include `model_instance_id`,
  `unit_instance_id`, `datasheet_id`, `model_profile_id`, display names,
  `base_size`, starting/current wounds, `base_characteristics`,
  `current_characteristics`, `visible_modifiers`, source metadata, visibility
  status, and redaction metadata.
- `base_characteristics` and `current_characteristics` cover the canonical
  datacard characteristics `M`, `T`, `SV`, `W`, `LD`, and `OC`.
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
viewer-scoped, read-only, and presentation-only. Own units and viewer-visible
placed opponent units may appear in `unit_display_by_id` and
`model_display_by_id`. Fully hidden or not-yet-revealed opponent records are
omitted when exposing their stable IDs, counts, or presence would leak hidden
information; field-level hidden values inside an otherwise visible record must
use explicit redactions or unknown values. `projection_state_hash` changes when
the adapter-visible live display state changes, including wound changes, so UI
caches can refresh display data without treating it as authoritative rules
state. Issue #145 is complete because a visible known model can render through
this join without placeholder unknowns:

`battlefield_state` placement -> `unit_display_by_id[unit_instance_id]` ->
`model_display_by_id[model_instance_id]` ->
`current_characteristics["M/T/SV/W/LD/OC"]`.

Phase 11E adds scoring state to the viewer projection:

- `public_secondary_mission_card_states`: Fixed and Tactical card state payloads scoped
  through the secondary-mission reveal gate.
- `public_victory_point_ledgers`: victory point ledgers scoped to the viewer.

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

## Replay and Resume

Replay-facing payloads must remain deterministic and JSON-safe:

- no Python object reprs;
- no memory addresses;
- stable IDs for entities, decisions, events, and proposals;
- stable lifecycle payloads.

Phase 11D must ensure replay/resume preserves pending parameterized proposal requests. Restoring after a finite movement-action result has been accepted but before the proposal has been submitted must reproduce the same pending proposal request and validation context.

Replay and tests may choose decisions differently from a human UI, but they must submit the same `DecisionResult` shape through the same lifecycle path.

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
        status = session.submit_payload(
            request_id=request.request_id,
            payload=payload,
            result_id=next_result_id(),
        )
    else:
        option_id = choose_finite_option_from_view(view, request)
        status = session.submit_option(
            request_id=request.request_id,
            selected_option_id=option_id,
            result_id=next_result_id(),
        )
```

The functions that render UI controls, query a human, call an AI policy, or serialize network packets can vary by adapter. The resulting `submit_option(...)` or `submit_payload(...)` call should not.

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
