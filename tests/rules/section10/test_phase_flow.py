"""10.00/01/03 nonempty compiled timing effects around the Shooting body."""

import pytest

from tests.support.section02_fixtures import Section02Definitions
from tests.support.section03_fixtures import native_state
from tests.support.section09_fixtures import attach_mission, events
from tests.support.section09_timing import timing_session
from tests.support.section10_fixtures import LORD, SPAWN, shooting_mission
from warhammer40k_core.engine.decision_result import DecisionResult
from warhammer40k_core.engine.game_state import SecondaryMissionChoice, SecondaryMissionMode
from warhammer40k_core.engine.phase import BattlePhase
from warhammer40k_core.engine.phases.shooting import ShootingPhaseHandler


@pytest.mark.parametrize("active", ["owner", "opponent"])
@pytest.mark.parametrize("position", ["start", "end"])
def test_nonempty_compiled_rules_surround_shooting_once(
    section10_definitions: Section02Definitions, active: str, position: str
) -> None:
    d = section10_definitions
    state = native_state(d, d.unit(LORD), enemy=d.unit(SPAWN, army_id="enemy", identity="target"))
    state.active_player_id = active
    state.battle_phase_index = state.battle_phase_sequence.index(BattlePhase.SHOOTING)
    attach_mission(state)
    state.mission_setup = shooting_mission()
    from dataclasses import replace

    state.army_definitions[:] = [
        replace(
            a,
            force_disposition_id=state.mission_setup.primary_mission_assignment_for_player(
                a.player_id
            ).force_disposition_id,
        )
        for a in state.army_definitions
    ]
    for player in state.player_ids:
        state.record_secondary_mission_choice(
            SecondaryMissionChoice(
                player, SecondaryMissionMode.FIXED, ("assassination", "bring-it-down")
            )
        )
    # Reuse the generic compiled CP timing kernel; text is a constructed
    # Shooting boundary rule, not evidence of any named faction admission.
    session = timing_session(d, state, f"At the {position} of your Shooting phase")
    # Explicit boundary kernel reuses the compiled runtime index, then composes
    # the same start/end bindings as RuntimeContentBundle.
    index = session.lifecycle._require_battle_round_flow()._runtime_event_index  # pyright: ignore[reportPrivateUsage]
    from warhammer40k_core.engine.battle_round_flow import BattleRoundFlow
    from warhammer40k_core.engine.runtime_event_phase_hooks import (
        end_bindings,
        shooting_start_bindings,
    )
    from warhammer40k_core.engine.shooting_phase_start_hooks import ShootingPhaseStartHookRegistry
    from warhammer40k_core.engine.turn_end_hooks import TurnEndHookRegistry

    decisions = session.lifecycle.decision_controller
    handler = ShootingPhaseHandler(
        ruleset_descriptor=state.runtime_ruleset_descriptor(),
        army_catalog=session.lifecycle.config.army_catalog,
        shooting_phase_start_hooks=ShootingPhaseStartHookRegistry.from_bindings(
            shooting_start_bindings(index)
        ),
    )
    flow = BattleRoundFlow(
        phase_handlers={BattlePhase.SHOOTING: handler},
        ruleset_descriptor=state.runtime_ruleset_descriptor(),
        army_catalog=session.lifecycle.config.army_catalog,
        runtime_event_index=index,
        turn_end_hooks=TurnEndHookRegistry.from_bindings(end_bindings(index)),
    )
    seen: list[str] = []
    for i in range(12):
        status = flow.advance(state=state, decisions=decisions)
        if state.current_battle_phase is BattlePhase.CHARGE:
            break
        request = status.decision_request
        assert request is not None
        assert request.actor_id == active
        seen.append(request.decision_type)
        if request.decision_type == "select_shooting_unit":
            option = next(
                o.option_id for o in request.options if o.option_id != "complete_shooting_phase"
            )
        else:
            assert request.decision_type == "select_shooting_type"
            option = "normal"
        result = DecisionResult.for_request(
            result_id=f"flow:{i}", request=request, selected_option_id=option
        )
        decisions.submit_result(result)
        handler.apply_decision(state=state, result=result, decisions=decisions)
    else:
        pytest.fail("Shooting boundary did not complete")
    assert seen == ["select_shooting_unit", "select_shooting_type"]
    gains = events(session, "catalog_ir_command_point_phase_gain_resolved")
    assert len(gains) == int(active == "owner")
    types = [e.event_type for e in session.lifecycle.decision_controller.event_log.records]
    assert types.index("shooting_unit_selected") < types.index("shooting_without_attacks_completed")
    assert (
        types.index("shooting_without_attacks_completed")
        < types.index("shooting_phase_completed")
        < types.index("battle_phase_completed")
    )
    if gains:
        assert gains[0]["passed"] is True
        assert state.command_point_total("owner") == 1
        effect = types.index("catalog_ir_command_point_phase_gain_resolved")
        assert (
            (effect < types.index("shooting_unit_selected"))
            if position == "start"
            else (
                types.index("shooting_phase_completed")
                < effect
                < types.index("battle_phase_completed")
            )
        )
    assert len(events(session, "shooting_phase_completed")) == 1
