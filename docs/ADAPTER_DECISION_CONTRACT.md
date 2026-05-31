# Adapter Decision Contract

Status: Phase 11D contract with Phase 11E scoring projection/event-stream additions, Phase 12A reaction/sequencing decisions, Phase 12B Stratagem decision requirements, and Phase 12C supported Core Stratagem handler requirements. This document is authoritative for adapter/proposal modules shipped with Phase 11D and future decision work.

This document is the Phase 11D submission contract, extended with Phase 11E scoring visibility rules, Phase 12A timing/reaction/sequencing rules, Phase 12B Stratagem decision rules, and Phase 12C supported Core Stratagem handler rules, for teams building UI, CLI, headless, network, replay, or AI adapters around CORE V2.

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
- `MovementProposalPayload`: parameterized movement answer, including `PathWitness`.
- `PlacementProposalPayload`: parameterized placement answer, including attempted `UnitPlacement`.
- `ProposalValidationResult`: typed valid, invalid, stale, or unsupported diagnostics.
- `EventRecord`: deterministic event-log payload.
- `GameViewPayload`: read-only viewer projection for adapters.
- `EventStreamDeltaPayload`: viewer-scoped adapter event delta.
- `SecondaryMissionCardState`: reveal-gated Fixed/Tactical secondary mission card state.
- `VictoryPointLedger`: viewer-scoped scoring ledger with reveal-gated secondary source visibility and generic hidden-transaction support.
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
- `src/warhammer40k_core/engine/timing_windows.py`
- `src/warhammer40k_core/engine/reaction_queue.py`
- `src/warhammer40k_core/engine/sequencing.py`
- `src/warhammer40k_core/engine/effects.py`
- `src/warhammer40k_core/engine/command_points.py`
- `src/warhammer40k_core/engine/stratagems.py`
- `src/warhammer40k_core/engine/stratagem_catalog.py`
- `src/warhammer40k_core/rules/source_packages/warhammer_40000_10th/core_stratagems.py`
- `src/warhammer40k_core/engine/scoring.py`
- `src/warhammer40k_core/engine/lifecycle.py`

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

If the selected option is legal and the action requires exact movement input, the engine may emit a follow-up parameterized proposal request.

Phase 11E mission-scoring decisions that are player-facing are finite decisions:

- `discard_tactical_secondary_mission`: the engine emits one option for each legal active Tactical secondary card the player can discard. The selected option payload includes the game, player, battle round, phase, and `secondary_mission_id`. The lifecycle applies the discard and emits `tactical_secondary_mission_discarded`.
- `start_mission_action`: the engine emits legal source-backed Mission Action start options. Current Phase 11E support enumerates action/unit/objective-target options for source-backed objective-marker actions such as Cleanse, filters units through the source `eligible_unit_policy`, and persists the selected `target_id` in `MissionActionState`. Mission Action target policies that are not yet represented as finite options must return a typed `unsupported` status instead of exposing an adapter mutation path.

Both decision types must be submitted through `FiniteOptionSubmission -> DecisionResult -> GameLifecycle.submit_decision(...)`. Tests, replay, UI, CLI, network, and headless adapters must not call `GameState.discard_tactical_secondary(...)` or `GameState.record_mission_action_state(...)` directly for player choices; those methods are engine-owned primitives used by validated decision handlers and automatic rule hooks.

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

Source-backed records whose `handler_id` starts with `unsupported:` are catalog descriptors only. They must not emit finite options, must not emit parameterized pending requests, and stale or hand-crafted submissions for them must be rejected with `unsupported_handler` before queue pop, CP spend, or Stratagem-use record creation.

Adapters must not invent `use_stratagem` option IDs, derive new target bindings from displayed payloads, spend CP directly, apply effects directly, or bypass the lifecycle to call lower-level state mutation APIs.

Stratagem decisions may be offered to the non-active player from a reaction window. The acting player on the `DecisionRequest` is authoritative; adapters should not assume the turn player is the player answering the request.

Some Stratagems need target or placement details that are not safe to pre-enumerate. Those requests use a parameterized proposal instead of a finite bound option. The request must embed a typed proposal request payload with a Stratagem-specific proposal kind, the same source `use_stratagem` context used by finite options, the source-backed catalog record, the timing context, the CP cost, the restriction policy, the handler binding, and replay-safe target context. Examples include:

- exact reinforcement placement after a Stratagem grants a reserves placement;
- geometric, line-of-sight, model-target, or path-dependent target proposals once the owning phase has the required validators;
- any future Stratagem whose legal target binding cannot be represented as a finite option set.

Phase 12B introduces the initial parameterized Stratagem target-binding decision type `submit_stratagem_target_proposal` with proposal kind `stratagem_target_binding`. Adapters answer only with the fixed `submit_parameterized_payload` option and a payload containing the typed `proposal` object. Stale phase/round, malformed shape, schema-invalid missing target binding, wrong player/game/Stratagem/catalog context, CP drift, and illegal target binding are rejected before queue pop and before any CP transaction or Stratagem-use record is created.

Parameterized Stratagem submissions follow the Phase 11D invalid-submission rule: stale, drifted, malformed, schema-invalid, or wrong-context payloads are rejected before the queue is popped or a `DecisionRecord` is created. They must not spend CP or mutate state. Accepted parameterized submissions apply the Stratagem use atomically through `GameLifecycle.submit_decision(...)`: the engine re-checks timing, CP, restrictions, target validity, spends CP, records `StratagemUseRecord`, emits `stratagem_used`, and applies any Phase-12B-supported handler/effect payload. Rule-invalid but well-formed proposals may be recorded as rejected attempts only when the specific proposal contract explicitly allows that behavior and emits a fresh pending request for retry.

Phase 12C source-backed Core Stratagems are adapter-visible through these handler bindings:

- `core:command-reroll`: finite `use_stratagem` option at `after_dice_roll`; the option payload context includes `trigger_payload.dice_roll_state`, and the source-backed catalog definition includes `eligible_roll_types` for the edition-specific roll classes that may be re-rolled. The 10th Edition source list covers Hit, Wound, Damage, saving throw, Advance, Charge, Desperate Escape, Hazardous, and number-of-attacks rolls; the normalized number-of-attacks roll type is `number_of_attacks_roll`. It does not include Battle-shock tests. The engine rejects unlisted non-roll-off roll types and roll actor drift before option emission and before queue pop, then applies Phase 10J whole-roll reroll semantics after lifecycle submission. This can be offered in a Phase 12A reaction window, and the parent resumes only after `command_reroll_resolved` and `reaction_parent_resumed` are emitted.
- `core:insane-bravery`: parameterized `submit_stratagem_target_proposal` for a unit pending a Battle-shock test. Accepted use records a persisting auto-pass effect and the Command phase resolves the Battle-shock test as passed without adapter-owned mutation.
- `core:rapid-ingress`: parameterized target proposal for an unarrived reserves unit during the opponent Movement phase end. Accepted use spends CP and records the Stratagem use, then emits a `submit_placement_proposal` request using the existing placement proposal contract. The placement answer must also go through `GameLifecycle.submit_decision(...)`. When Rapid Ingress is offered from a Phase 12A reaction window, the reaction frame continues from the target proposal to the placement proposal and the parent resumes only after a valid placement resolves. Rule-invalid but well-formed placement proposals are recorded as rejected attempts and emit a fresh pending placement request for retry; stale, malformed, or wrong-context placement proposals are rejected before queue pop.
- `core:new-orders`: finite `use_stratagem` options for active Tactical secondary cards. The target binding uses `target_kind: "tactical_secondary_card"` and `target_secondary_mission_id`; accepted use discards that card and draws one replacement through engine-owned Tactical secondary state.

Deferred Core Stratagem descriptors for Fire Overwatch, Go to Ground, Smokescreen, Grenade, Heroic Intervention, Counter-offensive, Epic Challenge, and Tank Shock remain source-backed catalog records with `handler_id` and `target_policy_id` values prefixed by `unsupported:` until their owning Shooting, Charge, or Fight phase gate implements them. They must not emit finite options or parameterized pending requests, and hand-crafted submissions must fail explicitly with `unsupported_handler` before CP spend or state mutation.

CP totals, CP ledger transactions, and normal Stratagem-use events are public in matched play. Viewer-scoped projections expose public CP ledger data under `public_command_point_ledgers` and public Stratagem-use records under `public_stratagem_use_records`. Adapter event deltas may expose normal CP and Stratagem events to every player unless a future source-backed hidden rule explicitly marks a pending decision, record, or event hidden. Any hidden Stratagem rule must update this document before implementation and must not leak hidden information through option counts, payload fields, event metadata, or derived projection data.

Required Phase 12 adapter-contract tests:

- finite `use_stratagem` option enumeration and `FiniteOptionSubmission` round-trip;
- stale/drift/malformed/schema-invalid/wrong-context parameterized Stratagem proposal rejection;
- insufficient CP typed invalid result with no ledger underflow;
- same-Stratagem-twice-per-phase rejection separate from own Stratagem restrictions;
- reactive non-active-player Stratagem use;
- replay/payload round-trip with deterministic JSON-safe records;
- Phase 12C supported Core Stratagem handler coverage for Command Re-roll, Insane Bravery, Rapid Ingress, and New Orders;
- Phase 12C deferred Core Stratagem descriptors exist but fail explicitly with `unsupported_handler`;
- Phase 12C Rapid Ingress reaction-window target and placement proposals replay/restore without resuming the parent before valid placement;
- viewer-scoped projection/event coverage for public CP and Stratagem events, plus redaction tests for any hidden Stratagem policy.

## Parameterized Proposals

Parameterized proposals are used when the exact physical result cannot be safely enumerated as finite options.

The contract currently covers these proposal families:

- Normal Move;
- Advance after dice/reroll resolution;
- Fall Back, including Desperate Escape follow-up behavior where applicable;
- Reinforcement placement;
- Deep Strike placement;
- Strategic Reserves placement;
- Disembark placement;
- Stratagem target or placement proposals introduced by Phase 12 and later phase gates.

Later phases must reuse the same contract for deployment placement, redeployment, Scout moves, charge movement, pile-in, consolidate, Stratagem target binding, and mission movement or placement effects where applicable.

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
      "context": {}
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
              "position": {"x": 9.0, "y": 6.0, "z": 0.0},
              "facing": {"degrees": 0.0}
            }
          ]
        }
      ]
    },
    "model_movements": []
  }
}
```

Producer examples:

- local UI: user drags models and submits endpoints plus `PathWitness`;
- CLI: user enters coordinates and the adapter builds a `PathWitness`;
- AI: movement solver generates endpoints plus `PathWitness`;
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
- malformed movement witnesses return typed invalid diagnostics;
- malformed attempted placements return typed invalid diagnostics;
- unsupported proposal kinds fail explicitly;
- invalid proposals do not consume the pending request before payload-shape validation.

## Projection and Visibility

The submission contract is shared. The information available to a producer is not always identical.

Phase 11E adds scoring state to the viewer projection:

- `public_secondary_mission_card_states`: Fixed and Tactical card state payloads scoped
  through the secondary-mission reveal gate.
- `public_victory_point_ledgers`: victory point ledgers scoped to the viewer.

Chapter Approved 2025-26 secondary selection is simultaneous-secret. A player's
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
rule instead of a flat adapter default.

Adapters should consume a `GameViewPayload` for a viewer by default:

```python
view = project_game_view(
    lifecycle=lifecycle,
    viewer_player_id="player-a",
)
```

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
        "secondary_mission_id": "area-denial",
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
