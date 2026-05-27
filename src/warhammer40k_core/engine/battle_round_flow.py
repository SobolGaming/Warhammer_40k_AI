from __future__ import annotations

from collections.abc import Mapping

from warhammer40k_core.engine.decision_controller import DecisionController
from warhammer40k_core.engine.game_state import GameState
from warhammer40k_core.engine.phase import (
    BattlePhase,
    GameLifecycleError,
    GameLifecycleStage,
    LifecycleStatus,
    LifecycleStatusKind,
    PhaseHandler,
)


class BattleRoundFlow:
    def __init__(self, *, phase_handlers: Mapping[BattlePhase, PhaseHandler]) -> None:
        self._phase_handlers = dict(phase_handlers)

    def advance(
        self,
        *,
        state: GameState,
        decisions: DecisionController,
    ) -> LifecycleStatus:
        if state.stage is not GameLifecycleStage.BATTLE:
            raise GameLifecycleError("BattleRoundFlow can advance only during battle.")
        current_phase = state.current_battle_phase
        if current_phase is None:
            raise GameLifecycleError("BattleRoundFlow requires a current battle phase.")

        handler = self._phase_handlers.get(current_phase)
        if handler is not None:
            status = handler.begin_phase(state=state, decisions=decisions)
            if status.status_kind is LifecycleStatusKind.WAITING_FOR_DECISION:
                return status
            if status.status_kind is LifecycleStatusKind.TERMINAL:
                return status
            if status.status_kind is LifecycleStatusKind.UNSUPPORTED:
                return status

        completed_phase = state.advance_to_next_battle_phase()
        decisions.event_log.append(
            "battle_phase_completed",
            {
                "game_id": state.game_id,
                "completed_phase": completed_phase.value,
                "battle_round": state.battle_round,
                "active_player_id": state.active_player_id,
                "next_phase": _current_battle_phase_payload(state),
            },
        )
        return LifecycleStatus.advanced(
            stage=GameLifecycleStage.BATTLE,
            payload={
                "completed_phase": completed_phase.value,
                "battle_round": state.battle_round,
                "active_player_id": state.active_player_id,
                "current_phase": _current_battle_phase_payload(state),
            },
        )


def _current_battle_phase_payload(state: GameState) -> str | None:
    current_phase = state.current_battle_phase
    if current_phase is None:
        return None
    return current_phase.value
