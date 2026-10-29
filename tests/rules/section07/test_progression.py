"""Actual phase-transition owner, with fresh native states at each boundary."""

import pytest

from tests.support.section02_fixtures import Section02Definitions
from tests.support.section07_fixtures import boundary_state
from warhammer40k_core.engine.mission_setup import MissionSetup
from warhammer40k_core.engine.phase import BattlePhase, GameLifecycleError, GameLifecycleStage

PHASES = (
    BattlePhase.COMMAND,
    BattlePhase.MOVEMENT,
    BattlePhase.SHOOTING,
    BattlePhase.CHARGE,
    BattlePhase.FIGHT,
)


@pytest.mark.parametrize("active", ["owner", "opponent"])
@pytest.mark.parametrize("phase", PHASES[:-1])
def test_five_phases_advance_in_source_order_without_changing_turn(
    section07_definitions: Section02Definitions,
    section07_mission: MissionSetup,
    active: str,
    phase: BattlePhase,
) -> None:
    state = boundary_state(
        section07_definitions, phase=phase, active=active, mission=section07_mission
    )
    completed = state.advance_to_next_battle_phase()
    assert completed is phase
    assert state.current_battle_phase is PHASES[PHASES.index(phase) + 1]
    assert (state.battle_round, state.active_player_id) == (1, active)
    assert state.stage is GameLifecycleStage.BATTLE


@pytest.mark.parametrize("first", ["owner", "opponent"])
def test_first_turn_ends_before_opponent_and_never_ends_round(
    section07_definitions: Section02Definitions, section07_mission: MissionSetup, first: str
) -> None:
    state = boundary_state(
        section07_definitions,
        phase=BattlePhase.FIGHT,
        first=first,
        active=first,
        battle_round=5,
        mission=section07_mission,
    )
    state.advance_to_next_battle_phase()
    assert state.battle_round == 5
    assert state.active_player_id == state.turn_order[1]
    assert state.current_battle_phase is BattlePhase.COMMAND
    assert state.stage is GameLifecycleStage.BATTLE


@pytest.mark.parametrize("first", ["owner", "opponent"])
@pytest.mark.parametrize("battle_round", [1, 4, 5])
def test_second_turn_starts_same_first_player_or_ends_at_mission_limit(
    section07_definitions: Section02Definitions,
    section07_mission: MissionSetup,
    first: str,
    battle_round: int,
) -> None:
    state = boundary_state(
        section07_definitions,
        phase=BattlePhase.FIGHT,
        first=first,
        active="opponent" if first == "owner" else "owner",
        battle_round=battle_round,
        mission=section07_mission,
    )
    state.advance_to_next_battle_phase()
    if battle_round == 5:
        assert state.stage is GameLifecycleStage.COMPLETE
        assert state.battle_round == 5
        assert state.active_player_id is None
        assert state.current_battle_phase is None
    else:
        assert state.stage is GameLifecycleStage.BATTLE
        assert (state.battle_round, state.active_player_id) == (battle_round + 1, first)
        assert state.current_battle_phase is BattlePhase.COMMAND
    assert state.turn_order[0] == first


@pytest.mark.parametrize("stage", [GameLifecycleStage.SETUP, GameLifecycleStage.COMPLETE])
def test_invalid_stage_cannot_advance_and_restored_battle_can_continue(
    section07_definitions: Section02Definitions,
    section07_mission: MissionSetup,
    stage: GameLifecycleStage,
) -> None:
    state = boundary_state(section07_definitions, mission=section07_mission)
    state.stage = stage
    before = state.to_payload()
    with pytest.raises(GameLifecycleError, match="only during battle"):
        state.advance_to_next_battle_phase()
    assert state.to_payload() == before
    state.stage = GameLifecycleStage.BATTLE
    assert state.advance_to_next_battle_phase() is BattlePhase.COMMAND
    assert state.current_battle_phase is BattlePhase.MOVEMENT
