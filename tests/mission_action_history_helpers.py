"""History for fixtures using the engine's lower-level Action state methods."""

from warhammer40k_core.engine.actions import MissionActionState, MissionActionStatus
from warhammer40k_core.engine.battle_round_flow import (
    _emit_objective_control_boundary_event_if_missing,  # pyright: ignore[reportPrivateUsage]
)
from warhammer40k_core.engine.decision_controller import DecisionController
from warhammer40k_core.engine.event_log import JsonValue, validate_json_value
from warhammer40k_core.engine.game_state import GameState
from warhammer40k_core.engine.mission_turn_end_sequencing import request_mission_turn_end_rules
from warhammer40k_core.engine.phase import BattlePhase
from warhammer40k_core.engine.runtime_modifiers import RuntimeModifierRegistry


def prepare_mission_action_turn_end_for_fixture(
    *, state: GameState, decisions: DecisionController
) -> None:
    record = state.prepare_current_turn_end_boundary(
        completed_phase=BattlePhase.FIGHT, runtime_modifier_registry=None
    )
    _emit_objective_control_boundary_event_if_missing(decisions=decisions, record=record)


def record_mission_action_terminal_for_fixture(
    *,
    state: GameState,
    decisions: DecisionController,
    action: MissionActionState,
    phase: BattlePhase,
) -> None:
    assert state.mission_action_state_by_id(action.action_id) == action
    assert action.status in {MissionActionStatus.COMPLETED, MissionActionStatus.INTERRUPTED}
    payload: dict[str, JsonValue] = {
        "game_id": state.game_id,
        "player_id": action.player_id,
        "battle_round": state.battle_round,
        "phase": phase.value,
        "mission_action_id": action.mission_action_id,
        "mission_action_state": validate_json_value(action.to_payload()),
    }
    if action.status is MissionActionStatus.COMPLETED:
        event_type = "mission_action_completed"
    else:
        event_type = "mission_action_interrupted"
        payload["interrupted_reason"] = action.interrupted_reason
    decisions.event_log.append(event_type, payload)
    if action.status is MissionActionStatus.COMPLETED and action.completion_timing == "turn_end":
        assert (
            request_mission_turn_end_rules(
                state=state,
                decisions=decisions,
                runtime_modifier_registry=RuntimeModifierRegistry.empty(),
            )
            is not None
        )
