from __future__ import annotations

from typing import cast

from warhammer40k_core.core.dice import DiceRollState, DiceRollStatePayload, RerollPermission
from warhammer40k_core.engine.battle_shock import (
    BattleShockResult,
    BattleShockTestRequest,
    BattleShockTestRequestPayload,
)
from warhammer40k_core.engine.battle_shock_hooks import (
    BattleShockHookRegistry,
    BattleShockModifierContext,
    BattleShockOutcomeContext,
)
from warhammer40k_core.engine.command_points import CommandStepState
from warhammer40k_core.engine.decision_controller import DecisionController
from warhammer40k_core.engine.decision_request import DecisionRequest
from warhammer40k_core.engine.decision_result import DecisionResult
from warhammer40k_core.engine.dice import DiceRollManager
from warhammer40k_core.engine.event_log import JsonValue, validate_json_value
from warhammer40k_core.engine.game_state import GameState
from warhammer40k_core.engine.phase import BattlePhase, GameLifecycleError, GameLifecycleStage


def build_battle_shock_reroll_request(
    *,
    state: GameState,
    decisions: DecisionController,
    request: BattleShockTestRequest,
    roll_state: DiceRollState,
    permission: RerollPermission,
    active_player_id: str,
    phase_start_battle_shocked_unit_ids: tuple[str, ...],
) -> DecisionRequest:
    manager = DiceRollManager(state.game_id, event_log=decisions.event_log)
    return manager.build_reroll_request(
        roll_state,
        request_id=state.next_decision_request_id(),
        actor_id=request.player_id,
        permission=permission,
        extra_payload={
            "battle_shock_context": {
                "game_id": state.game_id,
                "battle_round": state.battle_round,
                "phase": BattlePhase.COMMAND.value,
                "active_player_id": active_player_id,
                "battle_shock_test_request": validate_json_value(request.to_payload()),
                "battle_shock_roll_state": validate_json_value(roll_state.to_payload()),
                "phase_start_battle_shocked_unit_ids": list(phase_start_battle_shocked_unit_ids),
            }
        },
    )


def apply_battle_shock_reroll_decision(
    *,
    state: GameState,
    result: DecisionResult,
    decisions: DecisionController,
    battle_shock_hooks: BattleShockHookRegistry,
) -> None:
    if state.stage is not GameLifecycleStage.BATTLE:
        raise GameLifecycleError("Battle-shock reroll can be applied only during battle.")
    if state.current_battle_phase is not BattlePhase.COMMAND:
        raise GameLifecycleError("Battle-shock reroll can be applied only in command.")
    record = decisions.record_for_result(result)
    request_payload = _payload_object(record.request.payload, context="Decision payload")
    context_payload = _payload_object(
        request_payload.get("battle_shock_context"),
        context="Battle-shock reroll context",
    )
    if _payload_string(context_payload, key="game_id") != state.game_id:
        raise GameLifecycleError("Battle-shock reroll game_id drift.")
    if _payload_int(context_payload, key="battle_round") != state.battle_round:
        raise GameLifecycleError("Battle-shock reroll battle_round drift.")
    if _payload_string(context_payload, key="phase") != BattlePhase.COMMAND.value:
        raise GameLifecycleError("Battle-shock reroll phase payload drift.")
    active_player_id = _active_player_id(state)
    if _payload_string(context_payload, key="active_player_id") != active_player_id:
        raise GameLifecycleError("Battle-shock reroll active_player_id drift.")
    command_state = _command_step_state(state)
    if command_state.active_player_id != active_player_id:
        raise GameLifecycleError("Battle-shock reroll command state active player drift.")
    if command_state.battle_round != state.battle_round:
        raise GameLifecycleError("Battle-shock reroll command state round drift.")
    if command_state.battle_shock_step_resolved:
        raise GameLifecycleError("Battle-shock reroll step is already resolved.")
    phase_start_ids = _payload_string_tuple(
        context_payload,
        key="phase_start_battle_shocked_unit_ids",
    )
    if phase_start_ids != command_state.battle_shock_phase_start_unit_ids:
        raise GameLifecycleError("Battle-shock reroll phase-start unit IDs drift.")
    battle_shock_request = BattleShockTestRequest.from_payload(
        cast(
            BattleShockTestRequestPayload,
            _payload_object(
                context_payload.get("battle_shock_test_request"),
                context="Battle-shock test request",
            ),
        )
    )
    if battle_shock_request.request_id in command_state.completed_battle_shock_test_request_ids:
        raise GameLifecycleError("Battle-shock reroll request is already completed.")
    if result.actor_id != battle_shock_request.player_id:
        raise GameLifecycleError("Battle-shock reroll actor must match tested player.")
    initial_roll_state = DiceRollState.from_payload(
        cast(
            DiceRollStatePayload,
            _payload_object(
                context_payload.get("battle_shock_roll_state"),
                context="Battle-shock roll state",
            ),
        )
    )
    manager = DiceRollManager(state.game_id, event_log=decisions.event_log)
    rerolled_state = manager.resolve_reroll(
        initial_roll_state,
        request=record.request,
        result=result,
        record_decision=False,
    )
    record_battle_shock_result_and_outcomes(
        state=state,
        decisions=decisions,
        manager=manager,
        battle_shock_hooks=battle_shock_hooks,
        request=battle_shock_request,
        roll_state=rerolled_state,
        active_player_id=active_player_id,
        auto_passed=False,
        phase_start_battle_shocked_unit_ids=phase_start_ids,
    )
    state.replace_command_step_state(
        command_state.with_completed_battle_shock_test_request(battle_shock_request.request_id)
    )


def record_battle_shock_result_and_outcomes(
    *,
    state: GameState,
    decisions: DecisionController,
    manager: DiceRollManager,
    battle_shock_hooks: BattleShockHookRegistry,
    request: BattleShockTestRequest,
    roll_state: DiceRollState,
    active_player_id: str,
    auto_passed: bool,
    phase_start_battle_shocked_unit_ids: tuple[str, ...],
) -> JsonValue:
    result = BattleShockResult.from_roll_state(
        result_id=f"{request.request_id}:result",
        request=request,
        roll_state=roll_state,
        modifiers=battle_shock_hooks.modifiers_for(
            BattleShockModifierContext(
                state=state,
                request=request,
                active_player_id=active_player_id,
                phase=BattlePhase.COMMAND,
                phase_start_battle_shocked_unit_ids=phase_start_battle_shocked_unit_ids,
            )
        ),
    )
    state.record_battle_shock_result(result)
    result_payload = validate_json_value(result.to_payload())
    decisions.event_log.append(
        "battle_shock_test_resolved",
        {
            "game_id": state.game_id,
            "battle_round": state.battle_round,
            "active_player_id": active_player_id,
            "phase": BattlePhase.COMMAND.value,
            "battle_shock_result": result_payload,
            "auto_passed": auto_passed,
        },
    )
    battle_shock_hooks.resolve_outcomes(
        BattleShockOutcomeContext(
            state=state,
            decisions=decisions,
            dice_manager=manager,
            result=result,
            active_player_id=active_player_id,
            phase=BattlePhase.COMMAND,
            auto_passed=auto_passed,
            phase_start_battle_shocked_unit_ids=phase_start_battle_shocked_unit_ids,
        )
    )
    return result_payload


def _payload_object(value: JsonValue, *, context: str) -> dict[str, JsonValue]:
    if not isinstance(value, dict):
        raise GameLifecycleError(f"{context} must be an object.")
    return value


def _payload_int(payload: dict[str, JsonValue], *, key: str) -> int:
    if key not in payload:
        raise GameLifecycleError(f"Decision payload missing required key: {key}.")
    value = payload[key]
    if type(value) is not int:
        raise GameLifecycleError(f"Decision payload key must be an integer: {key}.")
    return value


def _payload_string(payload: dict[str, JsonValue], *, key: str) -> str:
    if key not in payload:
        raise GameLifecycleError(f"Decision payload missing required key: {key}.")
    value = payload[key]
    if type(value) is not str:
        raise GameLifecycleError(f"Decision payload key must be a string: {key}.")
    stripped = value.strip()
    if not stripped:
        raise GameLifecycleError(f"Decision payload string key cannot be empty: {key}.")
    return stripped


def _payload_string_tuple(payload: dict[str, JsonValue], *, key: str) -> tuple[str, ...]:
    if key not in payload:
        raise GameLifecycleError(f"Decision payload missing required key: {key}.")
    value = payload[key]
    if not isinstance(value, list):
        raise GameLifecycleError(f"Decision payload key must be a list: {key}.")
    strings: list[str] = []
    seen: set[str] = set()
    for item in value:
        if type(item) is not str:
            raise GameLifecycleError(f"Decision payload list must contain strings: {key}.")
        stripped = item.strip()
        if not stripped:
            raise GameLifecycleError(f"Decision payload string list item is empty: {key}.")
        if stripped in seen:
            raise GameLifecycleError(f"Decision payload string list contains duplicates: {key}.")
        strings.append(stripped)
        seen.add(stripped)
    return tuple(strings)


def _active_player_id(state: GameState) -> str:
    if state.active_player_id is None:
        raise GameLifecycleError("Battle-shock reroll requires an active player.")
    return state.active_player_id


def _command_step_state(state: GameState) -> CommandStepState:
    if state.command_step_state is None:
        raise GameLifecycleError("Battle-shock reroll requires command step state.")
    return state.command_step_state
