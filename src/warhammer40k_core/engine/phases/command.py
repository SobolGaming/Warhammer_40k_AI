from __future__ import annotations

from dataclasses import dataclass

from warhammer40k_core.engine.battle_shock import (
    BattleShockResult,
    collect_battle_shock_test_requests,
)
from warhammer40k_core.engine.command_points import (
    CommandPointGainStatus,
    CommandPointSourceKind,
    CommandStepState,
)
from warhammer40k_core.engine.decision_controller import DecisionController
from warhammer40k_core.engine.decision_request import DecisionOption, DecisionRequest
from warhammer40k_core.engine.decision_result import DecisionResult
from warhammer40k_core.engine.dice import DiceRollManager
from warhammer40k_core.engine.event_log import JsonValue, validate_json_value
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

        command_state = _ensure_command_step_state(state, active_player_id=active_player_id)
        if not command_state.command_points_granted:
            _resolve_command_step_start(state=state, decisions=decisions)
            command_state = _command_step_state(state)
        if not command_state.scoring_hooks_resolved:
            _resolve_command_phase_scoring_hooks(state=state, decisions=decisions)
            command_state = _command_step_state(state)

        if (
            not command_state.tactical_secondary_resolved
            and choice.mode is SecondaryMissionMode.TACTICAL
            and not state.has_tactical_secondary_draw(
                player_id=active_player_id,
                battle_round=state.battle_round,
            )
        ):
            return _request_tactical_secondary_draw(
                state=state,
                decisions=decisions,
                active_player_id=active_player_id,
            )

        if not command_state.tactical_secondary_resolved:
            state.command_step_state = command_state.with_tactical_secondary_resolved()
            command_state = _command_step_state(state)

        if not command_state.battle_shock_step_resolved:
            _resolve_battle_shock_step(state=state, decisions=decisions)

        return LifecycleStatus.advanced(
            stage=GameLifecycleStage.BATTLE,
            payload={
                "phase": BattlePhase.COMMAND.value,
                "active_player_id": active_player_id,
                "phase_body_status": "command_phase_complete",
                "command_step": "complete",
                "battle_shock_step": "complete",
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
        card_states = state.draw_tactical_secondary_cards(
            player_id=active_player_id,
            source_result_id=result.result_id,
        )
        decisions.event_log.append(
            "tactical_secondary_missions_drawn",
            {
                "game_id": state.game_id,
                "player_id": active_player_id,
                "battle_round": battle_round,
                "draw_count": draw_count,
                "phase": BattlePhase.COMMAND.value,
                "secondary_mission_card_states": [
                    validate_json_value(card_state.to_payload()) for card_state in card_states
                ],
            },
        )
        command_state = _command_step_state(state)
        state.command_step_state = command_state.with_tactical_secondary_resolved()


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


def _ensure_command_step_state(
    state: GameState,
    *,
    active_player_id: str,
) -> CommandStepState:
    if state.command_step_state is None:
        state.command_step_state = CommandStepState.start(
            battle_round=state.battle_round,
            active_player_id=active_player_id,
        )
        return state.command_step_state
    command_state = state.command_step_state
    if command_state.active_player_id != active_player_id:
        raise GameLifecycleError("CommandStepState active player drift.")
    if command_state.battle_round != state.battle_round:
        raise GameLifecycleError("CommandStepState battle round drift.")
    return command_state


def _command_step_state(state: GameState) -> CommandStepState:
    if state.command_step_state is None:
        raise GameLifecycleError("Command phase requires CommandStepState.")
    return state.command_step_state


def _resolve_command_step_start(
    *,
    state: GameState,
    decisions: DecisionController,
) -> None:
    active_player_id = _active_player_id(state)
    cleared_battle_shocked_unit_ids = state.clear_battle_shock_for_player(active_player_id)
    gain_payloads: list[JsonValue] = []
    for player_id in state.player_ids:
        gain = state.gain_command_points(
            player_id=player_id,
            amount=1,
            source_id=(
                f"command-phase-start:round-{state.battle_round:02d}:active-{active_player_id}"
            ),
            source_kind=CommandPointSourceKind.COMMAND_PHASE_START,
            cap_exempt=True,
        )
        if gain.status is not CommandPointGainStatus.APPLIED:
            raise GameLifecycleError("Command phase CP gain must not be capped.")
        gain_payload = validate_json_value(gain.to_payload())
        gain_payloads.append(gain_payload)
        decisions.event_log.append("command_points_gained", gain_payload)
    state.command_step_state = _command_step_state(state).with_command_points_granted()
    decisions.event_log.append(
        "command_step_started",
        {
            "game_id": state.game_id,
            "battle_round": state.battle_round,
            "active_player_id": active_player_id,
            "phase": BattlePhase.COMMAND.value,
            "command_point_gains": gain_payloads,
            "cleared_battle_shocked_unit_ids": list(cleared_battle_shocked_unit_ids),
        },
    )


def _resolve_command_phase_scoring_hooks(
    *,
    state: GameState,
    decisions: DecisionController,
) -> None:
    active_player_id = _active_player_id(state)
    decisions.event_log.append(
        "command_phase_scoring_hooks_resolved",
        {
            "game_id": state.game_id,
            "battle_round": state.battle_round,
            "active_player_id": active_player_id,
            "phase": BattlePhase.COMMAND.value,
            "timing": "command_step_after_cp_before_battle_shock",
        },
    )
    state.command_step_state = _command_step_state(state).with_scoring_hooks_resolved()


def _request_tactical_secondary_draw(
    *,
    state: GameState,
    decisions: DecisionController,
    active_player_id: str,
) -> LifecycleStatus:
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
            "phase_body_status": "tactical_secondary_draw_pending",
        },
    )


def _resolve_battle_shock_step(
    *,
    state: GameState,
    decisions: DecisionController,
) -> None:
    active_player_id = _active_player_id(state)
    battlefield_state = state.battlefield_state
    if battlefield_state is None:
        raise GameLifecycleError("Battle-shock step requires battlefield_state.")
    army = state.army_definition_for_player(active_player_id)
    if army is None:
        raise GameLifecycleError("Battle-shock step requires active player's army.")

    state.command_step_state = _command_step_state(state).enter_battle_shock_step()
    requests = collect_battle_shock_test_requests(
        game_id=state.game_id,
        battle_round=state.battle_round,
        player_id=active_player_id,
        army=army,
        battlefield_state=battlefield_state,
        starting_strength_records=tuple(state.starting_strength_records),
    )
    manager = DiceRollManager(state.game_id, event_log=decisions.event_log)
    result_payloads: list[JsonValue] = []
    for request in requests:
        decisions.event_log.append(
            "battle_shock_test_requested",
            {
                "game_id": state.game_id,
                "battle_round": state.battle_round,
                "active_player_id": active_player_id,
                "phase": BattlePhase.COMMAND.value,
                "battle_shock_test_request": validate_json_value(request.to_payload()),
            },
        )
        roll_state = manager.roll(request.spec)
        result = BattleShockResult.from_roll_state(
            result_id=f"{request.request_id}:result",
            request=request,
            roll_state=roll_state,
        )
        state.record_battle_shock_result(result)
        result_payload = validate_json_value(result.to_payload())
        result_payloads.append(result_payload)
        decisions.event_log.append(
            "battle_shock_test_resolved",
            {
                "game_id": state.game_id,
                "battle_round": state.battle_round,
                "active_player_id": active_player_id,
                "phase": BattlePhase.COMMAND.value,
                "battle_shock_result": result_payload,
            },
        )
    state.command_step_state = _command_step_state(state).with_battle_shock_step_resolved()
    decisions.event_log.append(
        "battle_shock_step_completed",
        {
            "game_id": state.game_id,
            "battle_round": state.battle_round,
            "active_player_id": active_player_id,
            "phase": BattlePhase.COMMAND.value,
            "battle_shock_test_count": len(requests),
            "battle_shock_results": result_payloads,
        },
    )
