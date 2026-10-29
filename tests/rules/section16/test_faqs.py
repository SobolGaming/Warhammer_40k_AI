"""FAQs 16/17 alongside 16.01: actual failed-test producer and explicit RuleIR permission."""

import pytest
from tests.action_battle_shock_helpers import resolve_action_battle_shock_test
from tests.support.section02_fixtures import Section02Definitions
from tests.support.section16_fixtures import accept, checkpoint, facade_checkpoint, offer

from warhammer40k_core.engine.actions import MissionActionStatus
from warhammer40k_core.engine.mission_action_battle_shock import (
    ACTION_BATTLE_SHOCK_PERMISSION_SOURCE_ID,
    action_battle_shock_permission_sources,
)
from warhammer40k_core.engine.mission_action_eligibility import (
    mission_action_unit_ineligibility_reason,
)
from warhammer40k_core.engine.phase import BattlePhase, GameLifecycleError
from warhammer40k_core.engine.runtime_modifiers import RuntimeModifierRegistry


@pytest.mark.parametrize("permission", [False, True])
def test_faq16_17_failed_battle_shock_immediately_interrupts_except_explicit_permission(
    section16_definitions: Section02Definitions, permission: bool
) -> None:
    session, state, unit = facade_checkpoint(
        section16_definitions, permission=permission, supporting=True
    )
    started = accept(session, state, unit)
    assert started.status is MissionActionStatus.STARTED
    assert action_battle_shock_permission_sources(
        state=state, unit_instance_id=unit.unit_instance_id
    ) == ((ACTION_BATTLE_SHOCK_PERMISSION_SOURCE_ID,) if permission else ())
    resolve_action_battle_shock_test(session, unit.unit_instance_id)
    assert unit.unit_instance_id in state.battle_shocked_unit_ids
    current = state.mission_action_state_by_id(started.action_id)
    assert current.status is (
        MissionActionStatus.STARTED if permission else MissionActionStatus.INTERRUPTED
    )
    assert current.interrupted_reason == (None if permission else "unit_battle_shocked")
    events = session.lifecycle.decision_controller.event_log.records
    assert events[-1].event_type == "battle_shock_test_resolved"
    if permission:
        completed = state.complete_mission_action(
            action_id=started.action_id, completion_phase=BattlePhase.FIGHT
        )
        assert completed.status is MissionActionStatus.COMPLETED
        assert any(
            c.action_id == started.action_id for c in state.secondary_objective_cleanse_states
        )
    else:
        assert events[-2].event_type == "mission_action_interrupted"
        with pytest.raises(GameLifecycleError, match="Only started"):
            state.complete_mission_action(
                action_id=started.action_id, completion_phase=BattlePhase.FIGHT
            )
        # Later removal of shock does not restart the interrupted Action.
        state.battle_shocked_unit_ids.clear()
        assert state.mission_action_state_by_id(started.action_id) == current


@pytest.mark.parametrize("permission", [False, True])
def test_faq17_permission_allows_shocked_start_without_erasing_other_eligibility_rules(
    section16_definitions: Section02Definitions, permission: bool
) -> None:
    state, unit = checkpoint(section16_definitions, permission=permission)
    state.battle_shocked_unit_ids.append(unit.unit_instance_id)
    reason = mission_action_unit_ineligibility_reason(
        state=state,
        player_id="owner",
        unit_instance_id=unit.unit_instance_id,
        runtime_modifier_registry=RuntimeModifierRegistry.empty(),
    )
    assert reason == (None if permission else "mission_action_unit_battle_shocked")
    blocked, same_unit = checkpoint(
        section16_definitions, permission=permission, supplement="AIRCRAFT"
    )
    blocked.battle_shocked_unit_ids.append(same_unit.unit_instance_id)
    assert (
        mission_action_unit_ineligibility_reason(
            state=blocked,
            player_id="owner",
            unit_instance_id=same_unit.unit_instance_id,
            runtime_modifier_registry=RuntimeModifierRegistry.empty(),
        )
        == "mission_action_unit_aircraft"
    )


def test_faq17_shocked_start_is_accepted_through_real_finite_facade(
    section16_definitions: Section02Definitions,
) -> None:
    session, state, unit = facade_checkpoint(
        section16_definitions, permission=True, supporting=True
    )
    resolve_action_battle_shock_test(session, unit.unit_instance_id)
    assert unit.unit_instance_id in state.battle_shocked_unit_ids
    pending = offer(session, state)
    assert pending.decision_type == "start_mission_action"
    # Use the pending engine option; do not create a second request.
    assert session.lifecycle.decision_controller.queue.peek_next() == pending
    selected = next(o for o in pending.options if f":{unit.unit_instance_id}:" in o.option_id)
    status = session.submit_option(
        request_id=pending.request_id, option_id=selected.option_id, result_id="s16:shocked-start"
    )
    assert status.status_kind.value != "invalid", status
    assert state.mission_action_states[0].unit_instance_id == unit.unit_instance_id
