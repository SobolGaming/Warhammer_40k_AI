"""Core 14.02.01: freeze control before any rules at the same end boundary."""

from __future__ import annotations

import json
from typing import cast

import pytest
from tests.order79_helpers import control_session

from warhammer40k_core.adapters.event_stream import EventStreamCursor
from warhammer40k_core.adapters.local_session import LocalGameSession
from warhammer40k_core.core.attributes import Characteristic, CharacteristicValueKind
from warhammer40k_core.engine.decision_request import DecisionError
from warhammer40k_core.engine.game_state import GameState
from warhammer40k_core.engine.lifecycle import GameLifecycle, GameLifecyclePayload
from warhammer40k_core.engine.objective_control import (
    ObjectiveControlRecord,
    ObjectiveControlTiming,
)
from warhammer40k_core.engine.phase import GameLifecycleError
from warhammer40k_core.engine.replay import ReplayArtifact, ReplayRunner, ReplayRunStatus


def turn_record(state: GameState, owner: str) -> ObjectiveControlRecord:
    return next(
        record
        for record in state.objective_control_records
        if record.battle_round == 1
        and record.active_player_id == owner
        and record.timing is ObjectiveControlTiming.TURN_END
    )


@pytest.mark.parametrize(
    ("owner", "on_objective"), [("player-b", True), ("player-a", True), ("player-b", False)]
)
def test_control_precedes_aircraft_departure_and_exactly_replays(
    owner: str, on_objective: bool
) -> None:
    session = control_session(turn_owner=owner, on_objective=on_objective)
    initial_state = session.lifecycle.state
    assert initial_state is not None
    aircraft = initial_state.army_definitions[0].units[0].own_models[0]
    assert aircraft.characteristic(Characteristic.OBJECTIVE_CONTROL).value_kind is (
        CharacteristicValueKind.SOURCE_DASH
    )
    initial = session.lifecycle.to_payload()
    session.advance_until_decision_or_terminal()
    state = session.lifecycle.state
    assert state is not None
    record = turn_record(state, owner)
    assert record.results[0].controlled_by_player_id is None
    assert all(
        contribution.effective_objective_control == 0
        for contribution in record.results[0].contributors
    )
    phase_record = next(
        row
        for row in state.objective_control_records
        if row.battle_round == 1
        and row.active_player_id == owner
        and row.timing is ObjectiveControlTiming.PHASE_END
    )
    assert phase_record.results[0].controlled_by_player_id is None
    if on_objective:
        assert any(
            row.model_instance_id == aircraft.model_instance_id
            and row.effective_objective_control == 0
            for row in phase_record.results[0].contributors
        )
    events = session.lifecycle.decision_controller.event_log.records
    control_index = next(
        i
        for i, event in enumerate(events)
        if event.event_type == "end_boundary_objective_control_determined"
        and isinstance(event.payload, dict)
        and event.payload["record_ids"] == [record.record_id]
    )
    if owner == "player-b":
        departure_index = next(
            i
            for i, event in enumerate(events)
            if event.event_type == "aircraft_opponent_turn_end_departure"
        )
        assert control_index < departure_index
    persisted = session.to_persistence_payload()
    restored = LocalGameSession.from_persistence_payload(json.loads(json.dumps(persisted)))
    assert restored.to_persistence_payload() == persisted
    for viewer in state.player_ids:
        assert restored.view(viewer_player_id=viewer) == session.view(viewer_player_id=viewer)
        assert restored.events_since(
            EventStreamCursor(), viewer_player_id=viewer
        ) == session.events_since(EventStreamCursor(), viewer_player_id=viewer)
    artifact = ReplayArtifact.capture(
        artifact_id="order79:replay",
        initial_lifecycle_payload=initial,
        final_lifecycle=session.lifecycle,
    )
    assert (
        ReplayRunner.from_payload(artifact.to_payload()).run().status is ReplayRunStatus.REPRODUCED
    )


@pytest.mark.parametrize("move_before_phase_completion", [False, True])
def test_restore_rejects_turn_control_event_moved_across_boundary(
    move_before_phase_completion: bool,
) -> None:
    session = control_session()
    session.advance_until_decision_or_terminal()
    payload = cast(GameLifecyclePayload, json.loads(json.dumps(session.lifecycle.to_payload())))
    state = session.lifecycle.state
    assert state is not None
    record = turn_record(state, "player-b")
    events = payload["decisions"]["event_log"]
    boundary_index = next(
        i
        for i, event in enumerate(events)
        if event["event_type"] == "end_boundary_objective_control_determined"
        and isinstance(event["payload"], dict)
        and event["payload"]["record_ids"] == [record.record_id]
    )
    window_index = next(
        i
        for i, event in enumerate(events)
        if event["event_type"]
        == ("timing_window_resolved" if move_before_phase_completion else "timing_window_opened")
        and isinstance(event["payload"], dict)
        and (
            '"trigger_kind": "end_phase"'
            if move_before_phase_completion
            else '"trigger_kind": "end_turn"'
        )
        in json.dumps(event["payload"])
    )
    events[boundary_index]["event_type"], events[window_index]["event_type"] = (
        events[window_index]["event_type"],
        events[boundary_index]["event_type"],
    )
    events[boundary_index]["payload"], events[window_index]["payload"] = (
        events[window_index]["payload"],
        events[boundary_index]["payload"],
    )
    with pytest.raises(GameLifecycleError, match=r"turn-end.*(before|order)"):
        GameLifecycle.from_payload(payload)


@pytest.mark.parametrize("use", [False, True])
def test_turn_control_is_frozen_across_source_loaded_choice_and_restore(use: bool) -> None:
    from tests.order79_choice_helpers import reserve_choice_session

    session = reserve_choice_session()
    initial = session.lifecycle.to_payload()
    status = session.advance_until_decision_or_terminal()
    request = status.decision_request
    assert request is not None
    assert request.decision_type == "select_faction_rule_turn_end_option"
    state = session.lifecycle.state
    assert state is not None
    assert state.active_player_id is not None
    record = turn_record(state, state.active_player_id)
    assert any(result.controlled_by_player_id == request.actor_id for result in record.results)
    checkpoint = session.to_persistence_payload()
    restored = LocalGameSession.from_persistence_payload(json.loads(json.dumps(checkpoint)))
    assert not state.end_turn_cleanup_states
    for viewer in state.player_ids:
        assert restored.view(viewer_player_id=viewer) == session.view(viewer_player_id=viewer)
        assert restored.events_since(
            EventStreamCursor(), viewer_player_id=viewer
        ) == session.events_since(EventStreamCursor(), viewer_player_id=viewer)
    for current in (session, restored):
        for request_id, option_id in (
            ("stale", request.options[0].option_id),
            (request.request_id, "unknown"),
        ):
            with pytest.raises((GameLifecycleError, DecisionError)):
                current.submit_option(
                    request_id=request_id, option_id=option_id, result_id="order79:invalid"
                )
            assert current.to_persistence_payload() == checkpoint
        # Re-entry must not run cleanup or change the already frozen snapshot.
        assert current.advance_until_decision_or_terminal().decision_request == request
        assert current.to_persistence_payload() == checkpoint
        option = next(
            option
            for option in request.options
            if option.option_id.endswith(":use" if use else ":decline")
        )
        current.submit_option(
            request_id=request.request_id, option_id=option.option_id, result_id="order79:choice"
        )
        current_state = current.lifecycle.state
        assert current_state is not None
        assert record in current_state.objective_control_records
        assert len(current_state.end_turn_cleanup_states) == 1
        assert current_state.battlefield_state is not None
        assert (
            current_state.battlefield_state.is_unit_placed("army-daemons:flesh-hounds-1") is not use
        )
    assert session.lifecycle.to_payload() == restored.lifecycle.to_payload()
    persisted = session.to_persistence_payload()
    clone = LocalGameSession.from_persistence_payload(json.loads(json.dumps(persisted)))
    for viewer in state.player_ids:
        assert clone.view(viewer_player_id=viewer) == session.view(viewer_player_id=viewer)
        assert clone.events_since(
            EventStreamCursor(), viewer_player_id=viewer
        ) == session.events_since(EventStreamCursor(), viewer_player_id=viewer)
    artifact = ReplayArtifact.capture(
        artifact_id="order79:choice-replay",
        initial_lifecycle_payload=initial,
        final_lifecycle=session.lifecycle,
    )
    assert (
        ReplayRunner.from_payload(artifact.to_payload()).run().status is ReplayRunStatus.REPRODUCED
    )


@pytest.mark.parametrize("corruption", ["stage", "player", "phase", "drift", "records", "cleanup"])
def test_turn_boundary_rejects_invalid_context_and_duplicate_completion(corruption: str) -> None:
    from warhammer40k_core.engine.phase import BattlePhase, GameLifecycleStage

    state = control_session().lifecycle.state
    assert state is not None
    completed = BattlePhase.FIGHT
    if corruption == "stage":
        state.stage = GameLifecycleStage.SETUP
    elif corruption == "player":
        state.active_player_id = None
    elif corruption == "phase":
        state.battle_phase_index = 0
    elif corruption == "drift":
        completed = BattlePhase.SHOOTING
    else:
        state.prepare_current_turn_end_boundary(
            completed_phase=completed, runtime_modifier_registry=None
        )
        if corruption == "records":
            state.objective_control_records.append(state.objective_control_records[-1])
        else:
            state.end_turn_cleanup_states.append(state.end_turn_cleanup_states[-1])
    before = state.to_payload()
    with pytest.raises(GameLifecycleError, match="Turn-end preparation"):
        state.prepare_current_turn_end_boundary(
            completed_phase=completed, runtime_modifier_registry=None
        )
    assert state.to_payload() == before


def test_direct_turn_boundary_preserves_attached_contributors_and_sticky_control() -> None:
    from tests.phase11c_command_phase_helpers import (
        battle_state,
        center_marker_definition,
        unit_selection,
        with_model_offsets,
    )

    from warhammer40k_core.engine.list_validation import AttachmentDeclaration
    from warhammer40k_core.engine.phase import BattlePhase
    from warhammer40k_core.engine.sticky_objective_control import StickyObjectiveControlState
    from warhammer40k_core.engine.turn_end_boundary import determine_turn_end_control

    state = battle_state(
        player_a_units=(
            unit_selection(
                unit_selection_id="bodyguard",
                datasheet_id="core-intercessor-like-infantry",
                model_profile_id="core-intercessor-like",
                model_count=5,
            ),
            unit_selection(
                unit_selection_id="leader",
                datasheet_id="core-character-leader",
                model_profile_id="core-character-leader",
                model_count=1,
            ),
        ),
        player_a_attachment_declarations=(
            AttachmentDeclaration(
                source_unit_selection_id="leader", bodyguard_unit_selection_id="bodyguard"
            ),
        ),
    )
    state.battle_phase_index = state.battle_phase_sequence.index(BattlePhase.FIGHT)
    marker = center_marker_definition(state)
    assert state.battlefield_state is not None
    formation = state.army_definitions[0].attached_units[0]
    for index, component_id in enumerate(formation.component_unit_instance_ids):
        placement = state.battlefield_state.unit_placement_by_id(component_id)
        state.battlefield_state = state.battlefield_state.with_unit_placement(
            with_model_offsets(
                placement,
                marker,
                offsets=tuple(
                    (-2.0 + i, float(index)) for i in range(len(placement.model_placements))
                ),
            )
        )
    assert state.mission_setup is not None
    sticky_marker = next(
        m
        for m in state.mission_setup.objective_markers
        if m.objective_marker_id != marker.objective_marker_id
    )
    state.record_sticky_objective_control_state(
        StickyObjectiveControlState(
            state_id="order79-sticky",
            game_id=state.game_id,
            player_id="player-a",
            objective_id=sticky_marker.objective_marker_id,
            source_rule_id="test:retained-control",
            source_event_id="test:retained-control:event",
            battle_round=1,
            phase=BattlePhase.FIGHT.value,
            active_player_id="player-a",
            originating_unit_instance_id=formation.component_unit_instance_ids[0],
            destroyed_unit_instance_id=state.army_definitions[1].units[0].unit_instance_id,
            replay_payload={"source": "order79-canonical-sticky-fixture"},
        )
    )
    record = determine_turn_end_control(
        state=state, completed_phase=BattlePhase.FIGHT, runtime_modifier_registry=None
    )
    result = record.result_by_objective_id(marker.objective_marker_id)
    assert {c.unit_instance_id for c in result.contributors} == set(
        formation.component_unit_instance_ids
    )
    assert len(result.contributors) == 6
    assert result.controlled_by_player_id == "player-a"
    sticky = record.result_by_objective_id(sticky_marker.objective_marker_id)
    assert sticky.controlled_by_player_id == "player-a"
    assert sticky.retained_control_source_id == "test:retained-control"
    # A later physical change cannot recalculate either frozen result.
    for component_id in formation.component_unit_instance_ids:
        state.battlefield_state = state.battlefield_state.without_unit_placement(component_id)
    assert (
        state.prepare_current_turn_end_boundary(
            completed_phase=BattlePhase.FIGHT, runtime_modifier_registry=None
        )
        == record
    )


def test_action_restriction_lasts_past_control_determination_until_cleanup() -> None:
    from tests.action_movement_interruption_helpers import action_movement_session

    from warhammer40k_core.engine.activity_restriction_restore import (
        validate_activity_restriction_inventory,
    )
    from warhammer40k_core.engine.activity_restrictions import activity_restriction_payload
    from warhammer40k_core.engine.boundary_rule_flow import prepare_turn_end_control_boundary
    from warhammer40k_core.engine.phase import BattlePhase
    from warhammer40k_core.engine.runtime_modifiers import RuntimeModifierRegistry

    session, _unit = action_movement_session()
    state = session.lifecycle.state
    assert state is not None
    decisions = session.lifecycle.decision_controller
    state.battle_phase_index = state.battle_phase_sequence.index(BattlePhase.FIGHT)
    state.shooting_phase_state = None
    restrictions = tuple(e for e in state.persisting_effects if activity_restriction_payload(e))
    assert len(restrictions) == 1
    prepare_turn_end_control_boundary(
        state=state, decisions=decisions, runtime_modifier_registry=RuntimeModifierRegistry.empty()
    )
    assert not state.end_turn_cleanup_states
    assert all(e in state.persisting_effects for e in restrictions)
    validate_activity_restriction_inventory(
        state=state, event_records=decisions.event_log.records, decision_records=decisions.records
    )
    state.prepare_current_turn_end_boundary(
        completed_phase=BattlePhase.FIGHT, runtime_modifier_registry=None
    )
    assert all(e not in state.persisting_effects for e in restrictions)
    validate_activity_restriction_inventory(
        state=state, event_records=decisions.event_log.records, decision_records=decisions.records
    )
