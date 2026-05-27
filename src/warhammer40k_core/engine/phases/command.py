from __future__ import annotations

from dataclasses import dataclass

from warhammer40k_core.engine.decision_controller import DecisionController
from warhammer40k_core.engine.decision_request import DecisionOption, DecisionRequest
from warhammer40k_core.engine.decision_result import DecisionResult
from warhammer40k_core.engine.event_log import JsonValue
from warhammer40k_core.engine.game_state import (
    GameState,
    SecondaryMissionMode,
    TacticalSecondaryDraw,
)
from warhammer40k_core.engine.phase import (
    BattlePhase,
    GameLifecycleError,
    GameLifecycleStage,
    LifecycleStatus,
)

TACTICAL_SECONDARY_DRAW_DECISION_TYPE = "draw_tactical_secondary_missions"


@dataclass(frozen=True, slots=True)
class CommandPhaseHandler:
    @property
    def phase(self) -> BattlePhase:
        return BattlePhase.COMMAND

    def begin_phase(
        self,
        *,
        state: GameState,
        decisions: DecisionController,
    ) -> LifecycleStatus:
        if state.stage is not GameLifecycleStage.BATTLE:
            raise GameLifecycleError("CommandPhaseHandler can run only during battle.")
        if state.current_battle_phase is not BattlePhase.COMMAND:
            raise GameLifecycleError("CommandPhaseHandler can run only in the COMMAND phase.")
        active_player_id = _active_player_id(state)
        choice = state.secondary_mission_choice_for_player(active_player_id)
        if choice is None:
            raise GameLifecycleError("Command phase requires secondary mission choices.")
        if choice.mode is not SecondaryMissionMode.TACTICAL:
            return LifecycleStatus.advanced(
                stage=GameLifecycleStage.BATTLE,
                payload={
                    "phase": BattlePhase.COMMAND.value,
                    "active_player_id": active_player_id,
                    "tactical_secondary_draw_required": False,
                },
            )
        if state.has_tactical_secondary_draw(
            player_id=active_player_id,
            battle_round=state.battle_round,
        ):
            return LifecycleStatus.advanced(
                stage=GameLifecycleStage.BATTLE,
                payload={
                    "phase": BattlePhase.COMMAND.value,
                    "active_player_id": active_player_id,
                    "tactical_secondary_draw_required": False,
                },
            )

        request = DecisionRequest(
            request_id=state.next_decision_request_id(),
            decision_type=TACTICAL_SECONDARY_DRAW_DECISION_TYPE,
            actor_id=active_player_id,
            payload={
                "game_id": state.game_id,
                "battle_round": state.battle_round,
                "phase": BattlePhase.COMMAND.value,
                "draw_count": state.tactical_secondary_draw_count,
            },
            options=(
                DecisionOption(
                    option_id="draw",
                    label="Draw tactical secondary missions",
                    payload={
                        "battle_round": state.battle_round,
                        "draw_count": state.tactical_secondary_draw_count,
                    },
                ),
            ),
        )
        decisions.request_decision(request)
        return LifecycleStatus.waiting_for_decision(
            stage=GameLifecycleStage.BATTLE,
            decision_request=request,
            payload={
                "phase": BattlePhase.COMMAND.value,
                "active_player_id": active_player_id,
            },
        )

    def apply_decision(
        self,
        *,
        state: GameState,
        result: DecisionResult,
        decisions: DecisionController,
    ) -> None:
        if result.decision_type != TACTICAL_SECONDARY_DRAW_DECISION_TYPE:
            raise GameLifecycleError("CommandPhaseHandler received an unsupported decision_type.")
        if state.stage is not GameLifecycleStage.BATTLE:
            raise GameLifecycleError("Tactical secondary draws can be applied only during battle.")
        if state.current_battle_phase is not BattlePhase.COMMAND:
            raise GameLifecycleError("Tactical secondary draws can be applied only in command.")
        active_player_id = _active_player_id(state)
        if result.actor_id != active_player_id:
            raise GameLifecycleError("Tactical secondary draw actor must be the active player.")
        payload = _decision_payload_object(result.payload)
        battle_round = _payload_int(payload, key="battle_round")
        draw_count = _payload_int(payload, key="draw_count")
        if battle_round != state.battle_round:
            raise GameLifecycleError("Tactical secondary draw battle_round does not match state.")
        if draw_count != state.tactical_secondary_draw_count:
            raise GameLifecycleError("Tactical secondary draw_count does not match state.")
        state.record_tactical_secondary_draw(
            TacticalSecondaryDraw(
                player_id=active_player_id,
                battle_round=battle_round,
                request_id=result.request_id,
                result_id=result.result_id,
                draw_count=draw_count,
            )
        )
        decisions.event_log.append(
            "tactical_secondary_missions_drawn",
            {
                "game_id": state.game_id,
                "player_id": active_player_id,
                "battle_round": battle_round,
                "draw_count": draw_count,
                "phase": BattlePhase.COMMAND.value,
            },
        )


def _active_player_id(state: GameState) -> str:
    if state.active_player_id is None:
        raise GameLifecycleError("Battle state requires an active player.")
    return state.active_player_id


def _decision_payload_object(payload: JsonValue) -> dict[str, JsonValue]:
    if not isinstance(payload, dict):
        raise GameLifecycleError("Decision payload must be an object.")
    return payload


def _payload_int(payload: dict[str, JsonValue], *, key: str) -> int:
    if key not in payload:
        raise GameLifecycleError(f"Decision payload missing required key: {key}.")
    value = payload[key]
    if type(value) is not int:
        raise GameLifecycleError(f"Decision payload key must be an integer: {key}.")
    return value
