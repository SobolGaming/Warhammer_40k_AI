from __future__ import annotations

import json

import pytest
from tests.order59_empty_dedicated_transport_helpers import (
    EMPTY_DEDICATED_TRANSPORTS_DESTROYED_EVENT_TYPE,
    ORDER59_CARGO_TRANSPORT_UNIT_ID,
    ORDER59_EMPTY_TRANSPORT_UNIT_ID,
    complete_order59_declare_battle_formations,
    order59_destruction_events,
    order59_empty_transport_config,
    order59_lifecycle_after_declare_battle_formations,
    order59_lifecycle_at_reserve_request,
    order59_transport_unit,
    typed_state,
)

from warhammer40k_core.adapters.event_stream import EventStreamCursor
from warhammer40k_core.adapters.local_session import LocalGameSession
from warhammer40k_core.engine.decision_controller import DecisionController
from warhammer40k_core.engine.empty_dedicated_transport_destruction import (
    DESTRUCTION_POLICY,
    EMPTY_DEDICATED_TRANSPORT_SOURCE_ID,
    apply_empty_dedicated_transport_destruction,
)
from warhammer40k_core.engine.event_log import EventRecord
from warhammer40k_core.engine.game_state import GameState
from warhammer40k_core.engine.phase import GameLifecycleError, SetupStep


def test_empty_dedicated_transport_is_destroyed_at_declare_battle_formations() -> None:
    lifecycle, status = order59_lifecycle_at_reserve_request()
    state = typed_state(lifecycle)
    transport = order59_transport_unit(state, ORDER59_EMPTY_TRANSPORT_UNIT_ID)
    model_id = transport.own_models[0].model_instance_id
    assert transport.own_models[0].is_alive
    assert model_id in state.unavailable_model_ids()
    complete_order59_declare_battle_formations(lifecycle, status)

    state = typed_state(lifecycle)
    transport = order59_transport_unit(state, ORDER59_EMPTY_TRANSPORT_UNIT_ID)
    battlefield = state.battlefield_state
    assert battlefield is not None
    assert transport.own_models[0].is_alive is False
    assert transport.own_models[0].wounds_remaining == 0
    assert model_id in battlefield.removed_model_ids
    assert model_id not in state.unavailable_model_ids()
    events = order59_destruction_events(lifecycle)
    assert len(events) == 1
    payload = events[0].payload
    assert isinstance(payload, dict)
    assert payload["source_rule_id"] == EMPTY_DEDICATED_TRANSPORT_SOURCE_ID
    assert payload["setup_step"] == SetupStep.DECLARE_BATTLE_FORMATIONS.value
    assert payload["destroyed_model_rules_triggered"] is False
    destroyed_units = payload["destroyed_units"]
    assert isinstance(destroyed_units, list)
    assert destroyed_units == [
        {
            "player_id": "player-a",
            "transport_unit_instance_id": ORDER59_EMPTY_TRANSPORT_UNIT_ID,
            "model_instance_ids": [model_id],
        }
    ]
    assert DESTRUCTION_POLICY.destroys_at_declare_battle_formations_end is True
    assert DESTRUCTION_POLICY.triggers_destroyed_model_rules is False


def test_empty_dedicated_transport_does_not_trigger_destroyed_model_rules() -> None:
    lifecycle = order59_lifecycle_after_declare_battle_formations(game_id="order59-no-triggers")
    event_types = tuple(
        event.event_type for event in lifecycle.decision_controller.event_log.records
    )
    assert "deadly_demise_resolved" not in event_types
    assert "model_destroyed" not in event_types
    payload = order59_destruction_events(lifecycle)[0].payload
    assert isinstance(payload, dict)
    assert payload["destroyed_model_rules_triggered"] is False
    consequence = typed_state(lifecycle).dedicated_transport_setup_consequence_for_transport(
        ORDER59_EMPTY_TRANSPORT_UNIT_ID
    )
    assert consequence is not None
    assert consequence.destroyed_model_rules_triggered is False
    assert consequence.consequence_kind == "empty_starting_cargo_destroyed_without_triggers"


def test_embarked_dedicated_transport_is_not_destroyed() -> None:
    lifecycle = order59_lifecycle_after_declare_battle_formations(
        game_id="order59-cargo-kept",
        include_cargo_transport=True,
    )
    state = typed_state(lifecycle)
    cargo_transport = order59_transport_unit(state, ORDER59_CARGO_TRANSPORT_UNIT_ID)
    empty_transport = order59_transport_unit(state, ORDER59_EMPTY_TRANSPORT_UNIT_ID)
    assert cargo_transport.own_models[0].is_alive
    assert empty_transport.own_models[0].is_alive is False
    payload = order59_destruction_events(lifecycle)[0].payload
    assert isinstance(payload, dict)
    destroyed_units = payload["destroyed_units"]
    assert isinstance(destroyed_units, list)
    transport_ids: list[object] = []
    for row in destroyed_units:
        assert isinstance(row, dict)
        transport_ids.append(row["transport_unit_instance_id"])
    assert transport_ids == [ORDER59_EMPTY_TRANSPORT_UNIT_ID]


def test_empty_dedicated_transport_destruction_rejects_wrong_setup_step() -> None:
    state = GameState.from_config(order59_empty_transport_config(game_id="order59-wrong-step"))
    with pytest.raises(GameLifecycleError, match="Declare Battle Formations"):
        apply_empty_dedicated_transport_destruction(
            state=state,
            decisions=DecisionController(),
        )


def test_empty_dedicated_transport_survives_adapter_restore_and_viewer_events() -> None:
    lifecycle = order59_lifecycle_after_declare_battle_formations(game_id="order59-restore")
    session = LocalGameSession(lifecycle=lifecycle)
    restored_state = GameState.from_payload(
        json.loads(json.dumps(typed_state(lifecycle).to_payload()))
    )
    restored_events = tuple(
        EventRecord.from_payload(json.loads(json.dumps(event.to_payload())))
        for event in order59_destruction_events(lifecycle)
    )
    transport = order59_transport_unit(restored_state, ORDER59_EMPTY_TRANSPORT_UNIT_ID)
    battlefield = restored_state.battlefield_state
    assert battlefield is not None
    assert transport.own_models[0].is_alive is False
    assert transport.own_models[0].model_instance_id in battlefield.removed_model_ids
    assert restored_events[0].event_type == EMPTY_DEDICATED_TRANSPORTS_DESTROYED_EVENT_TYPE

    def viewer_count(viewer_player_id: str) -> int:
        page = session.events_since(
            cursor=EventStreamCursor(),
            viewer_player_id=viewer_player_id,
        )
        return sum(
            1
            for event in page["events"]
            if event["event_type"] == EMPTY_DEDICATED_TRANSPORTS_DESTROYED_EVENT_TYPE
        )

    assert viewer_count("player-a") == 1
    assert viewer_count("player-b") == 1
