from __future__ import annotations

from copy import copy
from dataclasses import replace
from typing import NamedTuple, cast

import pytest
from tests.phase17n_primary_mission_helpers import (
    phase17n_accepted_action_opportunity_decline_fixture,
)

from warhammer40k_core.engine.decision_record import DecisionRecord
from warhammer40k_core.engine.decision_request import DecisionRequest
from warhammer40k_core.engine.decision_result import DecisionResult
from warhammer40k_core.engine.event_log import EventRecord, JsonValue, validate_json_value
from warhammer40k_core.engine.game_state import GameState
from warhammer40k_core.engine.mission_decisions import (
    DECLINE_MISSION_ACTION_START_OPTION_ID,
)
from warhammer40k_core.engine.phase import BattlePhase, GameLifecycleError
from warhammer40k_core.engine.primary_mission_action_decline_integrity import (
    MISSION_ACTION_OPPORTUNITY_DECLINE_EVIDENCE_KEY,
    MISSION_ACTION_OPPORTUNITY_DECLINED_EVENT,
    MissionActionOpportunityDeclineEvidence,
    validate_mission_action_opportunity_decline_integrity,
)
from warhammer40k_core.engine.primary_mission_boundary_checkpoint_evidence import (
    PRIMARY_MISSION_BOUNDARY_CHECKPOINT_EVENT,
)


class _DeclineGraph(NamedTuple):
    state: GameState
    events: tuple[EventRecord, ...]
    decision: DecisionRecord


@pytest.fixture(scope="module")
def authentic_decline_graph() -> _DeclineGraph:
    state, decisions, _request, result = phase17n_accepted_action_opportunity_decline_fixture()
    record = decisions.record_for_result(result)
    return _DeclineGraph(
        state=state,
        events=decisions.event_log.records,
        decision=record,
    )


def test_authentic_mission_action_opportunity_decline_has_exact_authority(
    authentic_decline_graph: _DeclineGraph,
) -> None:
    graph = authentic_decline_graph

    validate_mission_action_opportunity_decline_integrity(
        state=graph.state,
        event_records=graph.events,
        decision_records=(graph.decision,),
    )


def test_decline_authority_reconstructs_the_historical_request_boundary(
    authentic_decline_graph: _DeclineGraph,
) -> None:
    graph = authentic_decline_graph
    state = copy(graph.state)
    assert state.shooting_phase_state is not None
    action_option = next(
        option
        for option in graph.decision.request.options
        if option.option_id != DECLINE_MISSION_ACTION_START_OPTION_ID
    )
    action_payload = _payload_value(action_option.payload)
    unit_instance_id = cast(str, action_payload["unit_instance_id"])
    state.shooting_phase_state = replace(
        state.shooting_phase_state,
        shot_unit_ids=tuple(sorted({*state.shooting_phase_state.shot_unit_ids, unit_instance_id})),
    )

    validate_mission_action_opportunity_decline_integrity(
        state=state,
        event_records=graph.events,
        decision_records=(graph.decision,),
    )


def test_decline_flag_without_decision_or_mutation_event_is_rejected(
    authentic_decline_graph: _DeclineGraph,
) -> None:
    graph = authentic_decline_graph
    events = tuple(
        event
        for event in graph.events
        if event.event_type != MISSION_ACTION_OPPORTUNITY_DECLINED_EVENT
    )

    with pytest.raises(GameLifecycleError, match="flag lacks exact decision authority"):
        validate_mission_action_opportunity_decline_integrity(
            state=graph.state,
            event_records=events,
            decision_records=(),
        )


def test_decline_decision_without_mutation_event_is_rejected(
    authentic_decline_graph: _DeclineGraph,
) -> None:
    graph = authentic_decline_graph
    events = tuple(
        event
        for event in graph.events
        if event.event_type != MISSION_ACTION_OPPORTUNITY_DECLINED_EVENT
    )

    with pytest.raises(GameLifecycleError, match="requires one mutation event"):
        validate_mission_action_opportunity_decline_integrity(
            state=graph.state,
            event_records=events,
            decision_records=(graph.decision,),
        )


def test_decline_event_without_shooting_state_consequence_is_rejected(
    authentic_decline_graph: _DeclineGraph,
) -> None:
    graph = authentic_decline_graph
    state = copy(graph.state)
    assert state.shooting_phase_state is not None
    state.shooting_phase_state = replace(
        state.shooting_phase_state,
        mission_action_opportunity_declined=False,
    )

    with pytest.raises(GameLifecycleError, match="flag lacks exact decision authority"):
        validate_mission_action_opportunity_decline_integrity(
            state=state,
            event_records=graph.events,
            decision_records=(graph.decision,),
        )


@pytest.mark.parametrize("forgery_kind", ["changed_label", "omitted_action"])
def test_decline_request_with_forged_or_incomplete_option_inventory_is_rejected(
    authentic_decline_graph: _DeclineGraph,
    forgery_kind: str,
) -> None:
    graph = authentic_decline_graph
    if forgery_kind == "changed_label":
        forged_options = tuple(
            (
                replace(option, label="Forged Mission Action option")
                if option.option_id != DECLINE_MISSION_ACTION_START_OPTION_ID
                else option
            )
            for option in graph.decision.request.options
        )
    else:
        forged_options = tuple(
            option
            for option in graph.decision.request.options
            if option.option_id == DECLINE_MISSION_ACTION_START_OPTION_ID
        )
    forged_request = replace(graph.decision.request, options=forged_options)
    forged_decision = replace(graph.decision, request=forged_request)
    forged_events = _replace_decision_closure(
        events=graph.events,
        original=graph.decision,
        replacement=forged_decision,
    )

    with pytest.raises(
        GameLifecycleError, match=r"option inventory drifted|request inventory drifted"
    ):
        validate_mission_action_opportunity_decline_integrity(
            state=graph.state,
            event_records=forged_events,
            decision_records=(forged_decision,),
        )


@pytest.mark.parametrize(
    ("field_name", "value"),
    [
        ("battle_round", 2),
        ("player_id", "player-a"),
        ("phase", BattlePhase.COMMAND.value),
    ],
)
def test_decline_context_cannot_move_to_another_boundary(
    authentic_decline_graph: _DeclineGraph,
    field_name: str,
    value: JsonValue,
) -> None:
    graph = authentic_decline_graph
    moved_decision = _decision_with_context(
        decision=graph.decision,
        field_name=field_name,
        value=value,
    )
    moved_events = _replace_decision_closure(
        events=graph.events,
        original=graph.decision,
        replacement=moved_decision,
    )
    decline_event = _decline_event(moved_events)
    decline_payload = _payload(decline_event)
    moved_payload = {**decline_payload, field_name: value}
    moved_events = _replace_event(
        events=moved_events,
        replacement=replace(decline_event, payload=moved_payload),
    )

    with pytest.raises(GameLifecycleError):
        validate_mission_action_opportunity_decline_integrity(
            state=graph.state,
            event_records=moved_events,
            decision_records=(moved_decision,),
        )


def test_duplicate_declines_in_one_shooting_phase_are_rejected(
    authentic_decline_graph: _DeclineGraph,
) -> None:
    graph = authentic_decline_graph
    duplicate_request = replace(
        graph.decision.request,
        request_id=f"{graph.decision.request.request_id}:duplicate",
    )
    duplicate_result = DecisionResult.for_request(
        result_id=f"{graph.decision.result.result_id}:duplicate",
        request=duplicate_request,
        selected_option_id=DECLINE_MISSION_ACTION_START_OPTION_ID,
    )
    duplicate_decision = DecisionRecord(
        record_id=f"{graph.decision.record_id}:duplicate",
        request=duplicate_request,
        result=duplicate_result,
    )
    checkpoint_event = next(
        event
        for event in reversed(graph.events)
        if event.event_type == PRIMARY_MISSION_BOUNDARY_CHECKPOINT_EVENT
    )
    duplicate_checkpoint_event = replace(
        checkpoint_event,
        event_id="event-duplicate-decline-checkpoint",
    )
    decline_event = _decline_event(graph.events)
    decline_payload = _payload(decline_event)
    evidence = MissionActionOpportunityDeclineEvidence.from_payload(
        decline_payload[MISSION_ACTION_OPPORTUNITY_DECLINE_EVIDENCE_KEY]
    )
    duplicate_evidence = replace(
        evidence,
        checkpoint_reference=replace(
            evidence.checkpoint_reference,
            checkpoint_event_id=duplicate_checkpoint_event.event_id,
        ),
    )
    duplicate_events = (
        *graph.events,
        duplicate_checkpoint_event,
        EventRecord(
            event_id="event-duplicate-decline-requested",
            event_type="decision_requested",
            payload=validate_json_value(duplicate_request.to_payload()),
        ),
        EventRecord(
            event_id="event-duplicate-decline-recorded",
            event_type="decision_recorded",
            payload=validate_json_value(duplicate_decision.to_payload()),
        ),
        EventRecord(
            event_id="event-duplicate-decline-mutation",
            event_type=MISSION_ACTION_OPPORTUNITY_DECLINED_EVENT,
            payload={
                **decline_payload,
                "request_id": duplicate_request.request_id,
                "result_id": duplicate_result.result_id,
                MISSION_ACTION_OPPORTUNITY_DECLINE_EVIDENCE_KEY: (duplicate_evidence.to_payload()),
            },
        ),
    )

    with pytest.raises(GameLifecycleError, match="declined more than once"):
        validate_mission_action_opportunity_decline_integrity(
            state=graph.state,
            event_records=duplicate_events,
            decision_records=(graph.decision, duplicate_decision),
        )


def test_decline_decision_events_must_precede_mutation(
    authentic_decline_graph: _DeclineGraph,
) -> None:
    graph = authentic_decline_graph
    mutation_index = next(
        index
        for index, event in enumerate(graph.events)
        if event.event_type == MISSION_ACTION_OPPORTUNITY_DECLINED_EVENT
    )
    recorded_index = next(
        index
        for index, event in enumerate(graph.events)
        if event.event_type == "decision_recorded" and event.payload == graph.decision.to_payload()
    )
    events = list(graph.events)
    events[mutation_index], events[recorded_index] = (
        events[recorded_index],
        events[mutation_index],
    )

    with pytest.raises(GameLifecycleError, match="ordering drifted"):
        validate_mission_action_opportunity_decline_integrity(
            state=graph.state,
            event_records=tuple(events),
            decision_records=(graph.decision,),
        )


def test_decline_result_cannot_produce_action_start_mutation(
    authentic_decline_graph: _DeclineGraph,
) -> None:
    graph = authentic_decline_graph
    events = (
        *graph.events,
        EventRecord(
            event_id="event-forged-decline-action-start",
            event_type="mission_action_started",
            payload={
                "mission_action_state": {
                    "action_id": f"mission-action:{graph.decision.result.result_id}"
                }
            },
        ),
    )

    with pytest.raises(GameLifecycleError, match="start mutation event"):
        validate_mission_action_opportunity_decline_integrity(
            state=graph.state,
            event_records=events,
            decision_records=(graph.decision,),
        )


def _decision_with_context(
    *, decision: DecisionRecord, field_name: str, value: JsonValue
) -> DecisionRecord:
    actor_id = cast(str, value) if field_name == "player_id" else decision.request.actor_id
    request_payload = {**_payload_value(decision.request.payload), field_name: value}
    options = tuple(
        replace(
            option,
            payload={**_payload_value(option.payload), field_name: value},
        )
        for option in decision.request.options
    )
    request = DecisionRequest(
        request_id=decision.request.request_id,
        decision_type=decision.request.decision_type,
        actor_id=actor_id,
        payload=request_payload,
        options=options,
    )
    result = DecisionResult.for_request(
        result_id=decision.result.result_id,
        request=request,
        selected_option_id=DECLINE_MISSION_ACTION_START_OPTION_ID,
    )
    return replace(decision, request=request, result=result)


def _replace_decision_closure(
    *,
    events: tuple[EventRecord, ...],
    original: DecisionRecord,
    replacement: DecisionRecord,
) -> tuple[EventRecord, ...]:
    return tuple(
        (
            replace(event, payload=validate_json_value(replacement.request.to_payload()))
            if event.event_type == "decision_requested"
            and event.payload == original.request.to_payload()
            else replace(event, payload=validate_json_value(replacement.to_payload()))
            if event.event_type == "decision_recorded" and event.payload == original.to_payload()
            else event
        )
        for event in events
    )


def _replace_event(
    *, events: tuple[EventRecord, ...], replacement: EventRecord
) -> tuple[EventRecord, ...]:
    return tuple(
        replacement if event.event_id == replacement.event_id else event for event in events
    )


def _decline_event(events: tuple[EventRecord, ...]) -> EventRecord:
    matches = tuple(
        event for event in events if event.event_type == MISSION_ACTION_OPPORTUNITY_DECLINED_EVENT
    )
    assert len(matches) == 1
    return matches[0]


def _payload(event: EventRecord) -> dict[str, JsonValue]:
    return _payload_value(event.payload)


def _payload_value(value: JsonValue) -> dict[str, JsonValue]:
    assert isinstance(value, dict)
    return value
