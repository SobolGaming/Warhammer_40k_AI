"""SF16-R001: real source-valid turn-end discovery and completion consumer."""

from dataclasses import replace

import pytest
from tests.action_battle_shock_helpers import resolve_action_battle_shock_test
from tests.action_movement_interruption_helpers import request_action_move
from tests.support.section02_fixtures import Section02Definitions
from tests.support.section16_review_fixtures import (
    add_native_control,
    finish_mission_boundary,
    native_scene,
    start_native,
)

from warhammer40k_core.engine.actions import MissionActionStatus
from warhammer40k_core.engine.phase import BattlePhase, GameLifecycleError
from warhammer40k_core.engine.secondary_mission_action_resolution import (
    resolve_secondary_mission_action_at_turn_end,
    secondary_action_completions_after_control,
)
from warhammer40k_core.engine.triggered_movement import DECLINE_TRIGGERED_MOVEMENT_OPTION_ID


@pytest.mark.parametrize("active", ["owner", "opponent"])
def test_native_cleanse_completes_at_real_turn_end_once(
    section16_definitions: Section02Definitions, active: str
) -> None:
    session, state, unit = native_scene(section16_definitions, active=active)
    identity = start_native(session, state, unit)
    action = state.mission_action_state_by_id(identity)
    assert action.status is MissionActionStatus.STARTED
    assert not state.secondary_objective_cleanse_states
    assert not any(
        e.event_type == "mission_action_completed"
        for e in session.lifecycle.decision_controller.event_log.records
    )
    finish_mission_boundary(session, state, pause_before_score=True)
    completed = state.mission_action_state_by_id(identity)
    assert completed.status is MissionActionStatus.COMPLETED
    assert completed.player_id == active
    assert completed.unit_instance_id == unit.unit_instance_id
    assert len(state.secondary_objective_cleanse_states) == 1
    effect = state.secondary_objective_cleanse_states[0]
    assert (effect.action_id, effect.player_id, effect.objective_marker_id) == (
        identity,
        active,
        action.target_id,
    )
    terminal = [
        e
        for e in session.lifecycle.decision_controller.event_log.records
        if e.event_type == "mission_action_completed"
    ]
    assert len(terminal) == 1
    assert isinstance(terminal[0].payload, dict)
    assert terminal[0].payload["mission_action_state"] == completed.to_payload()
    assert terminal[0].payload["source_id"] == effect.source_id
    before = session.lifecycle.to_payload()
    record = next(
        r
        for r in state.objective_control_records
        if r.record_id == terminal[0].payload["objective_control_record_id"]
    )
    with pytest.raises(GameLifecycleError, match="not pending"):
        resolve_secondary_mission_action_at_turn_end(
            state=state,
            decisions=session.lifecycle.decision_controller,
            action_id=identity,
            turn_end_record=record,
        )
    assert session.lifecycle.to_payload() == before
    authority = next(
        a
        for a in state.objective_control_record_authorities
        if a.objective_control_record_id == record.record_id
    )
    # A terminal state and exact projection alone cannot invent a completion:
    # the accepted use was already frozen before mission rules resolved.
    forged = replace(completed, action_id="constructed:s16:unaccepted-action")
    state.mission_action_states[:] = [forged]
    with pytest.raises(GameLifecycleError, match="frozen prior-use"):
        secondary_action_completions_after_control(
            state=state,
            record=record,
            checkpoint=authority.boundary_checkpoint,
            earlier_action_ids=frozenset(),
        )
    state.mission_action_states[:] = [completed]
    assert session.lifecycle.to_payload() == before
    finish_mission_boundary(session, state)
    transactions = [
        t
        for t in state.victory_point_ledger_for_player(active).transactions
        if t.source_id == "cleanse"
    ]
    assert len(transactions) == 1
    assert transactions[0].player_id == active
    # Adopted Cleanse tactical-one-objective rule awards exactly 2 VP.
    assert transactions[0].amount == 2
    assert len(state.secondary_objective_cleanse_states) == 1
    assert (
        len(
            [
                e
                for e in session.lifecycle.decision_controller.event_log.records
                if e.event_type == "mission_action_completed"
            ]
        )
        == 1
    )


@pytest.mark.parametrize("active", ["owner", "opponent"])
@pytest.mark.parametrize("interruption", ["move", "departure", "shock", "permitted_shock"])
def test_native_consumer_preserves_interruptions_and_faq17_continuation(
    section16_definitions: Section02Definitions, active: str, interruption: str
) -> None:
    from warhammer40k_core.engine.battlefield_state import BattlefieldRemovalKind
    from warhammer40k_core.engine.primary_battlefield_departure import (
        record_primary_battlefield_departure,
    )
    from warhammer40k_core.engine.primary_historical_events import (
        record_primary_battlefield_departure_event,
    )

    permission = interruption == "permitted_shock"
    session, state, unit = native_scene(section16_definitions, active=active, permission=permission)
    # The unshocked native companion retains target control even when the acting
    # unit is shocked or departs; failure is therefore the Action interruption.
    if interruption != "move":
        add_native_control(section16_definitions, state, identity="controller")
    identity = start_native(session, state, unit)
    if interruption == "move":
        # Explicit generic reactive permission; zero-distance witnessed movement
        # is still a completed move. No native granting provider is claimed.
        request = request_action_move(session, unit.unit_instance_id, "zero")
        selected = next(
            o for o in request.options if o.option_id != DECLINE_TRIGGERED_MOVEMENT_OPTION_ID
        )
        result = session.submit_option(
            request_id=request.request_id,
            option_id=selected.option_id,
            result_id="s16:r2:interrupt-move",
        )
        assert result.status_kind.value != "invalid", result
        # The reactive facade resumes automatically to the empty Fight phase.
        # Resolve its native optional start abilities through finite declines;
        # never replace the decision controller or discard a pending request.
        for index in range(4):
            pending = session.lifecycle.pending_decision_request()
            if (
                pending is None
                or pending.decision_type != "select_faction_rule_fight_phase_start_option"
            ):
                break
            decline = next(o for o in pending.options if o.option_id.endswith(":decline"))
            result = session.submit_option(
                request_id=pending.request_id,
                option_id=decline.option_id,
                result_id=f"s16:r2:decline-fight:{index}",
            )
            assert result.status_kind.value != "invalid", result
    elif interruption == "departure":
        assert state.battlefield_state is not None
        state.replace_battlefield_state(
            state.battlefield_state.with_removed_models(unit.own_model_ids())
        )
        # Constructed post-departure physical checkpoint, using the typed engine
        # producer; no reserves/cargo admission or prior phase play is implied.
        departure = record_primary_battlefield_departure(
            state=state,
            rules_unit_instance_id=unit.unit_instance_id,
            affected_component_unit_instance_ids=(unit.unit_instance_id,),
            departed_component_unit_instance_ids=(unit.unit_instance_id,),
            removed_model_instance_ids=unit.own_model_ids(),
            removal_kind=BattlefieldRemovalKind.INTO_RESERVES,
            occurrence_id="constructed:s16:r2:departure",
            source_id="constructed:s16:r2:departure",
        )
        assert departure is not None
        record_primary_battlefield_departure_event(
            event_log=session.lifecycle.decision_controller.event_log, departure=departure
        )
    else:
        resolve_action_battle_shock_test(session, unit.unit_instance_id)
        assert unit.unit_instance_id in state.battle_shocked_unit_ids
    assert not state.secondary_objective_cleanse_states
    if state.active_player_id == active and state.current_battle_phase in {
        BattlePhase.SHOOTING,
        BattlePhase.FIGHT,
    }:
        finish_mission_boundary(session, state)
    result_action = state.mission_action_state_by_id(identity)
    assert result_action.status is (
        MissionActionStatus.COMPLETED if permission else MissionActionStatus.INTERRUPTED
    )
    if not permission:
        assert (
            result_action.interrupted_reason
            == {
                "move": "unit_moved",
                "departure": "unit_left_battlefield",
                "shock": "unit_battle_shocked",
            }[interruption]
        )
    assert len(state.secondary_objective_cleanse_states) == int(permission)
    completed_events = [
        e
        for e in session.lifecycle.decision_controller.event_log.records
        if e.event_type == "mission_action_completed"
    ]
    assert len(completed_events) == int(permission)
    scores = [
        t
        for t in state.victory_point_ledger_for_player(active).transactions
        if t.source_id == "cleanse"
    ]
    assert [t.amount for t in scores] == ([2] if permission else [])
