from __future__ import annotations

from warhammer40k_core.engine.actions import MissionActionStatus
from warhammer40k_core.engine.decision_controller import DecisionController
from warhammer40k_core.engine.decision_request import DecisionRequest
from warhammer40k_core.engine.game_state import GameState
from warhammer40k_core.engine.phase import BattlePhase, GameLifecycleError
from warhammer40k_core.engine.primary_mission_choices import (
    consecrate_choice_request,
    sensor_sweep_marker_removal_choice_request,
)
from warhammer40k_core.engine.runtime_modifiers import RuntimeModifierRegistry

_SENSOR_SWEEP_ACTION_IDS = frozenset(
    {
        "sensor-sweep-extract-relic",
        "sensor-sweep-locate-and-deny",
    }
)


def next_primary_mission_turn_end_choice_request(
    *,
    state: GameState,
    decisions: DecisionController,
    completed_phase: BattlePhase,
    runtime_modifier_registry: RuntimeModifierRegistry,
    request_id: str | None = None,
) -> DecisionRequest | None:
    if type(state) is not GameState or type(decisions) is not DecisionController:
        raise GameLifecycleError("Primary turn-end choice requires engine-owned state.")
    if type(completed_phase) is not BattlePhase:
        raise GameLifecycleError("Primary turn-end choice requires BattlePhase.")
    if type(runtime_modifier_registry) is not RuntimeModifierRegistry:
        raise GameLifecycleError("Primary turn-end choice requires runtime modifiers.")
    if state.active_player_id is None:
        raise GameLifecycleError("Primary turn-end choice requires an active player.")

    for action in state.mission_action_states:
        if (
            action.status is MissionActionStatus.COMPLETED
            and action.mission_action_id in _SENSOR_SWEEP_ACTION_IDS
            and action.player_id == state.active_player_id
            and action.completed_battle_round == state.battle_round
            and action.completed_phase == completed_phase.value
        ):
            request = sensor_sweep_marker_removal_choice_request(
                state=state,
                decisions=decisions,
                action_id=action.action_id,
                request_id=request_id,
            )
            if request is not None:
                return request

    return consecrate_choice_request(
        state=state,
        decisions=decisions,
        request_id=request_id,
        runtime_modifier_registry=runtime_modifier_registry,
    )


__all__ = ("next_primary_mission_turn_end_choice_request",)
