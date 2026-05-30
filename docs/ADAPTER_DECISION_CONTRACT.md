# Adapter Decision Contract

Status: Planned Phase 11D contract. This document is authoritative for Phase 11D implementation work after Phase 11B and 11C, but the listed adapter/proposal modules are not assumed to exist before Phase 11D lands.

This document is the Phase 11D contract for teams building UI, CLI, headless, network, replay, or AI adapters around CORE V2.

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
- unit selection;
- movement action selection;
- reroll choices;
- decline/accept choices;
- triggered movement choices.

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

## Parameterized Proposals

Parameterized proposals are used when the exact physical result cannot be safely enumerated as finite options.

Phase 11D covers:

- Normal Move;
- Advance after dice/reroll resolution;
- Fall Back, including Desperate Escape follow-up behavior where applicable;
- Reinforcement placement;
- Deep Strike placement;
- Strategic Reserves placement;
- Disembark placement.

Later phases must reuse the same contract for deployment placement, redeployment, Scout moves, charge movement, pile-in, consolidate, and mission movement or placement effects where applicable.

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

Viewer-scoped event deltas must not leak hidden opponent choices. In Phase 11D this includes:

- hidden `decision_requested` payloads;
- hidden `decision_recorded` payloads;
- `secondary_mission_choice_recorded` metadata that would reveal Fixed versus Tactical selection.

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

- Owning player may see full choice details.
- Opponent sees only `{selected: true, hidden: true}` style metadata.

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
