from __future__ import annotations

import json
from typing import cast

import pytest
from tests.order59_empty_dedicated_transport_helpers import (
    COMPLETE_RESERVE_DECLARATIONS_OPTION_ID,
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
from warhammer40k_core.adapters.session_protocol import AuthoritativeSession
from warhammer40k_core.engine.decision_controller import DecisionController
from warhammer40k_core.engine.decision_result import DecisionResult
from warhammer40k_core.engine.deployment import SELECT_DEPLOYMENT_UNIT_DECISION_TYPE
from warhammer40k_core.engine.empty_dedicated_transport_destruction import (
    DESTRUCTION_POLICY,
    EMPTY_DEDICATED_TRANSPORT_SOURCE_ID,
    apply_empty_dedicated_transport_destruction,
)
from warhammer40k_core.engine.event_log import EventRecord
from warhammer40k_core.engine.game_state import GameState
from warhammer40k_core.engine.lifecycle import GameLifecycle, GameLifecyclePayload
from warhammer40k_core.engine.phase import GameLifecycleError, LifecycleStatus, SetupStep
from warhammer40k_core.engine.reserve_declarations import SELECT_RESERVE_DECLARATION_DECISION_TYPE
from warhammer40k_core.engine.setup_flow import SECONDARY_MISSION_DECISION_TYPE


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
    assert transport.own_models[0].current_wounds == 0
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


def test_empty_dedicated_transport_lifecycle_restore_before_destruction_continues() -> None:
    lifecycle, status = order59_lifecycle_at_reserve_request(game_id="order59-restore-before")
    restored = GameLifecycle.from_payload(_lifecycle_payload(lifecycle))
    restored_status = restored.advance_until_decision_or_terminal()
    request = restored_status.decision_request
    original_request = status.decision_request
    assert original_request is not None
    assert request is not None
    assert request.decision_type == original_request.decision_type
    assert request.decision_type == SELECT_RESERVE_DECLARATION_DECISION_TYPE
    complete_order59_declare_battle_formations(restored, restored_status)
    transport = order59_transport_unit(typed_state(restored), ORDER59_EMPTY_TRANSPORT_UNIT_ID)
    assert transport.own_models[0].is_alive is False


def test_empty_dedicated_transport_lifecycle_restore_continues_deployment() -> None:
    lifecycle = order59_lifecycle_after_declare_battle_formations(
        game_id="order59-lifecycle-restore"
    )
    original_status = lifecycle.advance_until_decision_or_terminal()
    original_request = original_status.decision_request
    assert original_request is not None
    restored = GameLifecycle.from_payload(_lifecycle_payload(lifecycle))
    transport = order59_transport_unit(typed_state(restored), ORDER59_EMPTY_TRANSPORT_UNIT_ID)
    assert transport.own_models[0].is_alive is False
    restored_status = restored.advance_until_decision_or_terminal()
    restored_request = restored_status.decision_request
    assert restored_request is not None
    assert restored_request.decision_type == original_request.decision_type
    assert restored_request.decision_type == SELECT_DEPLOYMENT_UNIT_DECISION_TYPE
    option_ids = tuple(option.option_id for option in restored_request.options)
    assert option_ids
    assert all(ORDER59_EMPTY_TRANSPORT_UNIT_ID not in option_id for option_id in option_ids)
    continued = restored.submit_decision(
        DecisionResult.for_request(
            result_id="order59-lifecycle-restore-continue",
            request=restored_request,
            selected_option_id=option_ids[0],
        )
    )
    assert continued.decision_request is not None


def test_empty_dedicated_transport_restore_rejects_unrelated_wound_drift() -> None:
    lifecycle = order59_lifecycle_after_declare_battle_formations(game_id="order59-wound-drift")
    payload = _lifecycle_payload(lifecycle)
    _set_unit_model_wounds(
        payload, unit_instance_id="army-alpha:bodyguard-unit", wounds_remaining=0
    )
    with pytest.raises(GameLifecycleError, match="army definitions do not match config"):
        GameLifecycle.from_payload(payload)


def test_empty_dedicated_transport_session_fork_persistence_and_server_continue() -> None:
    session, status = _order59_session_after_declare_battle_formations(
        game_id="order59-adapter-restore"
    )
    forked = session.fork()
    persisted = LocalGameSession.from_persistence_payload(
        json.loads(json.dumps(session.to_persistence_payload()))
    )
    config = session.lifecycle.config
    assert config is not None
    record = AuthoritativeSession.create(
        session_id="session:order59-empty-dt",
        adapter_session=session,
        config=config,
        lifecycle_status=status,
        created_at="2026-09-18T16:45:00Z",
        started=True,
    )
    command_fork = record.fork_for_command()
    for index, restored_session in enumerate((forked, persisted, command_fork.adapter_session)):
        restored_status = restored_session.advance_until_decision_or_terminal()
        request = restored_status.decision_request
        assert request is not None
        assert request.decision_type == SELECT_DEPLOYMENT_UNIT_DECISION_TYPE
        option_ids = tuple(option.option_id for option in request.options)
        assert option_ids
        assert all(ORDER59_EMPTY_TRANSPORT_UNIT_ID not in option_id for option_id in option_ids)
        continued = restored_session.submit_option(
            request_id=request.request_id,
            option_id=option_ids[0],
            result_id=f"order59-adapter-continue-{index:02d}",
        )
        assert continued.decision_request is not None


def _order59_session_after_declare_battle_formations(
    *,
    game_id: str,
) -> tuple[LocalGameSession, LifecycleStatus]:
    session = LocalGameSession()
    session.start(order59_empty_transport_config(game_id=game_id))
    status = session.advance_until_decision_or_terminal()
    result_index = 1
    while status.decision_request is not None:
        request = status.decision_request
        if request.decision_type == SECONDARY_MISSION_DECISION_TYPE:
            option_id = "tactical"
        elif request.decision_type == SELECT_RESERVE_DECLARATION_DECISION_TYPE:
            option_id = COMPLETE_RESERVE_DECLARATIONS_OPTION_ID
        else:
            break
        status = session.submit_option(
            request_id=request.request_id,
            option_id=option_id,
            result_id=f"{game_id}-drive-{result_index:02d}",
        )
        result_index += 1
    state = session.lifecycle.state
    assert state is not None
    assert state.current_setup_step is SetupStep.DEPLOY_ARMIES
    return session, status


def _lifecycle_payload(lifecycle: GameLifecycle) -> GameLifecyclePayload:
    return cast(GameLifecyclePayload, json.loads(json.dumps(lifecycle.to_payload())))


def _set_unit_model_wounds(
    payload: GameLifecyclePayload,
    *,
    unit_instance_id: str,
    wounds_remaining: int,
) -> None:
    state_payload = payload["state"]
    assert isinstance(state_payload, dict)
    armies = state_payload["army_definitions"]
    assert isinstance(armies, list)
    for army in armies:
        assert isinstance(army, dict)
        units = army["units"]
        assert isinstance(units, list)
        for unit in units:
            assert isinstance(unit, dict)
            if unit["unit_instance_id"] != unit_instance_id:
                continue
            models = unit["own_models"]
            assert isinstance(models, list)
            first = models[0]
            assert isinstance(first, dict)
            first["wounds_remaining"] = wounds_remaining
            return
    raise AssertionError(f"missing unit {unit_instance_id}")
