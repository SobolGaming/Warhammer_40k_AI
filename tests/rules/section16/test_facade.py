"""Real finite Action request, facade submission, exact mutation and stale rejection."""

import json
from dataclasses import replace

import pytest
from tests.support.section02_fixtures import Section02Definitions
from tests.support.section10_fixtures import advanced
from tests.support.section16_fixtures import accept, action, facade_checkpoint, offer
from tests.unit_keyword_helpers import with_unit_keywords

from warhammer40k_core.engine.mission_decisions import request_mission_action_start
from warhammer40k_core.engine.phase import BattlePhase, LifecycleStatusKind
from warhammer40k_core.engine.phases.movement import FellBackUnitState
from warhammer40k_core.engine.runtime_modifiers import RuntimeModifierRegistry


def test_native_action_start_uses_finite_request_and_shared_facade(
    section16_definitions: Section02Definitions,
) -> None:
    session, state, unit = facade_checkpoint(section16_definitions)
    status = request_mission_action_start(
        state=state,
        decisions=session.lifecycle.decision_controller,
        player_id="owner",
        mission_action_id="cleanse-objective",
        runtime_modifier_registry=RuntimeModifierRegistry.empty(),
    )
    request = status.decision_request
    assert request is not None, status
    assert request.decision_type == "start_mission_action"
    assert not state.mission_action_states
    selected = next(o for o in request.options if unit.unit_instance_id in o.option_id)
    result = session.submit_option(
        request_id=request.request_id, option_id=selected.option_id, result_id="s16:accept"
    )
    assert result.status_kind is not LifecycleStatusKind.INVALID, result
    assert len(state.mission_action_states) == 1
    assert state.mission_action_states[0].unit_instance_id == unit.unit_instance_id
    started = state.mission_action_states[0]
    assert started.start_timing == "shooting_phase_action_start"
    assert started.completion_timing == "turn_end"
    assert started.scoring_source_id == "cleanse"
    assert started.victory_points == 0
    assert started.target_id in selected.option_id
    assert len(session.lifecycle.decision_controller.records) == 1
    recorded = session.lifecycle.decision_controller.records[0]
    assert recorded.request == request
    assert recorded.result.selected_option_id == selected.option_id
    assert json.loads(json.dumps(recorded.to_payload())) == recorded.to_payload()
    assert any(
        e.event_type == "mission_action_started"
        for e in session.lifecycle.decision_controller.event_log.records
    )


@pytest.mark.parametrize(
    "drift",
    [
        "shock",
        "AIRCRAFT",
        "FORTIFICATION",
        "advanced",
        "fell_back",
        "off_battlefield",
        "already_started",
    ],
)
def test_pending_action_revalidates_exclusions_before_queue_pop_or_mutation(
    section16_definitions: Section02Definitions, drift: str
) -> None:
    session, state, unit = facade_checkpoint(section16_definitions)
    req = offer(session, state)
    selected = next(o for o in req.options if f":{unit.unit_instance_id}:" in o.option_id)
    if drift == "shock":
        state.battle_shocked_unit_ids.append(unit.unit_instance_id)
    elif drift in {"AIRCRAFT", "FORTIFICATION"}:
        changed = with_unit_keywords(unit, keywords=tuple(sorted({*unit.keywords, drift})))
        state.army_definitions[:] = [
            replace(a, units=(changed,)) if a.player_id == "owner" else a
            for a in state.army_definitions
        ]
    elif drift == "advanced":
        advanced(state, unit)
    elif drift == "fell_back":
        state.record_fell_back_unit_state(FellBackUnitState("owner", 1, unit.unit_instance_id))
    elif drift == "off_battlefield":
        assert state.battlefield_state is not None
        state.replace_battlefield_state(
            state.battlefield_state.without_unit_placement(unit.unit_instance_id)
        )
    else:
        assert drift == "already_started"
        state.record_mission_action_state(action(unit))
    before = session.lifecycle.to_payload()
    status = session.submit_option(
        request_id=req.request_id, option_id=selected.option_id, result_id="s16:stale"
    )
    assert status.status_kind is LifecycleStatusKind.INVALID, status
    assert session.lifecycle.to_payload() == before
    assert session.lifecycle.decision_controller.queue.peek_next() == req


def test_completion_triggers_effect_once_and_does_not_allow_second_start(
    section16_definitions: Section02Definitions,
) -> None:
    session, state, unit = facade_checkpoint(section16_definitions)
    started = accept(session, state, unit)
    assert not state.secondary_objective_cleanse_states
    assert state.mission_action_state_by_id(started.action_id) == started
    completed = state.complete_mission_action(
        action_id=started.action_id, completion_phase=BattlePhase.FIGHT
    )
    assert completed.status.value == "completed"
    assert len(state.secondary_objective_cleanse_states) == 1
    effect = state.secondary_objective_cleanse_states[0]
    assert effect.action_id == started.action_id
    assert effect.objective_marker_id == started.target_id
    assert effect.player_id == "owner"
    # Accepted starts enforce the Core one-Action-per-unit-per-turn limit even
    # after the effect completes. No unrelated prior phases are replayed.
    status = request_mission_action_start(
        state=state,
        decisions=session.lifecycle.decision_controller,
        player_id="owner",
        mission_action_id="cleanse-objective",
        runtime_modifier_registry=RuntimeModifierRegistry.empty(),
    )
    assert status.status_kind is LifecycleStatusKind.UNSUPPORTED
    assert len(state.mission_action_states) == 1
    assert len(state.secondary_objective_cleanse_states) == 1


@pytest.mark.parametrize("restriction", ["wrong_phase", "not_held"])
def test_action_specific_start_and_ownership_requirements_are_enforced(
    section16_definitions: Section02Definitions, restriction: str
) -> None:
    session, state, _unit = facade_checkpoint(section16_definitions)
    if restriction == "wrong_phase":
        state.battle_phase_index = state.battle_phase_sequence.index(BattlePhase.MOVEMENT)
    else:
        state.secondary_mission_card_states[:] = [
            card
            for card in state.secondary_mission_card_states
            if card.player_id != "owner" or card.secondary_mission_id != "cleanse"
        ]
    before = session.lifecycle.to_payload()
    status = request_mission_action_start(
        state=state,
        decisions=session.lifecycle.decision_controller,
        player_id="owner",
        mission_action_id="cleanse-objective",
        runtime_modifier_registry=RuntimeModifierRegistry.empty(),
    )
    assert status.status_kind is LifecycleStatusKind.UNSUPPORTED
    assert session.lifecycle.to_payload() == before
