"""History for fixtures using the engine's lower-level Action state methods."""

from warhammer40k_core.engine.actions import MissionActionState, MissionActionStatus
from warhammer40k_core.engine.decision_controller import DecisionController
from warhammer40k_core.engine.event_log import JsonValue, validate_json_value
from warhammer40k_core.engine.game_state import GameState
from warhammer40k_core.engine.phase import BattlePhase


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
