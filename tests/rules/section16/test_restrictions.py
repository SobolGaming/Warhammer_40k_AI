"""16.01 accepted-start locks survive Action completion/interruption through turn end."""

import pytest
from tests.support.section02_fixtures import Section02Definitions
from tests.support.section16_fixtures import action, checkpoint

from warhammer40k_core.engine.charge_eligibility import charge_unit_ineligibility_reason
from warhammer40k_core.engine.charge_phase_state import ChargePhaseState
from warhammer40k_core.engine.mission_action_eligibility import (
    mission_action_prevents_rules_unit_from_shooting_this_phase,
    rules_unit_started_mission_action_this_turn,
)
from warhammer40k_core.engine.phase import BattlePhase
from warhammer40k_core.engine.phases.shooting_eligibility import shooting_unit_can_select_to_shoot


@pytest.mark.parametrize("titanic", [False, True])
@pytest.mark.parametrize("terminal", ["started", "completed", "interrupted"])
def test_shooting_exception_and_charge_lock_are_independent_of_action_terminal_status(
    section16_definitions: Section02Definitions, titanic: bool, terminal: str
) -> None:
    state, unit = checkpoint(section16_definitions, supplement="TITANIC" if titanic else None)
    assert shooting_unit_can_select_to_shoot(
        state=state,
        unit=unit,
        army_catalog=section16_definitions.package.army_catalog,
        player_id="owner",
    )
    started = action(unit)
    state.record_mission_action_state(started)
    if terminal == "completed":
        state.replace_mission_action_state(
            started.complete_without_award(
                battle_round=1, phase="shooting", completion_timing="turn_end"
            )
        )
    elif terminal == "interrupted":
        state.interrupt_mission_action(action_id=started.action_id, reason="unit_moved")
    assert mission_action_prevents_rules_unit_from_shooting_this_phase(
        state=state, player_id="owner", unit_instance_id=unit.unit_instance_id
    ) is (not titanic)
    assert (
        shooting_unit_can_select_to_shoot(
            state=state,
            unit=unit,
            army_catalog=section16_definitions.package.army_catalog,
            player_id="owner",
        )
        is titanic
    )
    state.battle_phase_index = state.battle_phase_sequence.index(BattlePhase.CHARGE)
    charge = ChargePhaseState(active_player_id="owner", battle_round=1)
    assert (
        charge_unit_ineligibility_reason(
            state=state,
            unit_instance_id=unit.unit_instance_id,
            ruleset_descriptor=state.runtime_ruleset_descriptor(),
            charge_state=charge,
            ignore_already_selected=False,
        )
        == "charge_unit_started_action"
    )
    assert rules_unit_started_mission_action_this_turn(
        state=state, player_id="owner", unit_instance_id=unit.unit_instance_id
    )


@pytest.mark.parametrize("phase", [BattlePhase.SHOOTING, BattlePhase.CHARGE, BattlePhase.FIGHT])
def test_accepted_start_restriction_is_turn_scoped_not_phase_scoped(
    section16_definitions: Section02Definitions, phase: BattlePhase
) -> None:
    state, unit = checkpoint(section16_definitions)
    state.record_mission_action_state(action(unit))
    state.battle_phase_index = state.battle_phase_sequence.index(phase)
    assert mission_action_prevents_rules_unit_from_shooting_this_phase(
        state=state, player_id="owner", unit_instance_id=unit.unit_instance_id
    )
    # The next player's turn is a distinct occurrence even in the same round.
    state.active_player_id = "opponent"
    assert not mission_action_prevents_rules_unit_from_shooting_this_phase(
        state=state, player_id="owner", unit_instance_id=unit.unit_instance_id
    )
    state.active_player_id = "owner"
    state.battle_round = 2
    assert not rules_unit_started_mission_action_this_turn(
        state=state, player_id="owner", unit_instance_id=unit.unit_instance_id
    )


def test_faq62_action_lock_remains_at_turn_end_then_expires_at_own_exact_boundary(
    section16_definitions: Section02Definitions,
) -> None:
    from warhammer40k_core.engine.effects import EffectExpirationBoundary

    state, unit = checkpoint(section16_definitions)
    state.record_mission_action_state(action(unit))
    state.battle_phase_index = state.battle_phase_sequence.index(BattlePhase.FIGHT)
    before = tuple(state.persisting_effects)
    assert (
        state.expire_persisting_effects_at_boundary(
            EffectExpirationBoundary.turn_end(battle_round=1, player_id="opponent")
        )
        == ()
    )
    assert tuple(state.persisting_effects) == before
    assert rules_unit_started_mission_action_this_turn(
        state=state, player_id="owner", unit_instance_id=unit.unit_instance_id
    )
    expired = state.expire_persisting_effects_at_boundary(
        EffectExpirationBoundary.turn_end(battle_round=1, player_id="owner")
    )
    assert expired == before
    assert not rules_unit_started_mission_action_this_turn(
        state=state, player_id="owner", unit_instance_id=unit.unit_instance_id
    )
