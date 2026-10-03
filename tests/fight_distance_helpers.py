"""Explicit phase-step context for direct Fight distance query fixtures."""

from warhammer40k_core.core.ruleset_descriptor import FightPhaseStepKind, FightPolicyDescriptor
from warhammer40k_core.engine.fight_order import FightPhaseState, FightsFirstRegistry
from warhammer40k_core.engine.game_state import GameState


def set_fight_distance_step(
    state: GameState, *, policy: FightPolicyDescriptor, step: FightPhaseStepKind
) -> None:
    state.fight_phase_state = FightPhaseState.start(
        battle_round=state.battle_round,
        active_player_id="player-a",
        policy=policy,
        engaged_at_fight_step_start_unit_ids=(),
        fights_first_registry=FightsFirstRegistry(),
    ).with_current_step(current_step=step, policy=policy)
