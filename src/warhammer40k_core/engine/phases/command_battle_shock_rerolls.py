from __future__ import annotations

from typing import cast

from warhammer40k_core.core.dice import DiceError, DiceRollState, DiceRollStatePayload
from warhammer40k_core.engine.battle_shock import (
    BattleShockTestRequest,
    BattleShockTestRequestPayload,
)
from warhammer40k_core.engine.battle_shock_hooks import (
    BattleShockHookRegistry,
    BattleShockRerollPermissionContext,
)
from warhammer40k_core.engine.battle_shock_resolution import (
    ADDITIONAL_MODIFIER_APPLICATIONS_CONTEXT_KEY,
    BATTLE_SHOCK_REROLL_CONTEXT_KEY,
    BATTLE_SHOCK_REROLL_SOURCE_KIND_KEY,
    PASSED_STATE_POLICY_CONTEXT_KEY,
    BattleShockPassedStatePolicy,
    apply_battle_shock_reroll_resolution_decision,
)
from warhammer40k_core.engine.command_battle_shock_history import (
    COMMAND_BATTLE_SHOCK_REROLL_SOURCE_KIND,
    ordered_completed_command_battle_shock_results,
    validate_command_battle_shock_snapshot_authority,
)
from warhammer40k_core.engine.command_points import CommandPhaseStep, CommandStepState
from warhammer40k_core.engine.decision_controller import DecisionController
from warhammer40k_core.engine.decision_request import DecisionError, DecisionRequest
from warhammer40k_core.engine.decision_result import DecisionResult
from warhammer40k_core.engine.dice import DICE_REROLL_DECISION_TYPE, DiceRollManager
from warhammer40k_core.engine.event_log import JsonValue, validate_json_value
from warhammer40k_core.engine.game_state import GameState
from warhammer40k_core.engine.phase import (
    BattlePhase,
    GameLifecycleError,
    GameLifecycleStage,
    LifecycleStatus,
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
    battle_shock_request = validate_command_battle_shock_reroll_context(
        state=state,
        decisions=decisions,
        request=record.request,
        battle_shock_hooks=battle_shock_hooks,
        pending=False,
    )
    if result.actor_id != battle_shock_request.player_id:
        raise GameLifecycleError("Battle-shock reroll actor must match tested player.")
    command_state = _command_step_state(state)
    apply_battle_shock_reroll_resolution_decision(
        state=state,
        decisions=decisions,
        result=result,
        battle_shock_hooks=battle_shock_hooks,
        expected_source_kind=COMMAND_BATTLE_SHOCK_REROLL_SOURCE_KIND,
        expected_passed_state_policy=(BattleShockPassedStatePolicy.CLEAR_IF_STEP_START_SHOCKED),
    )
    state.replace_command_step_state(
        command_state.with_completed_battle_shock_test_request(battle_shock_request.request_id)
    )


def invalid_command_battle_shock_reroll_status(
    *,
    state: GameState,
    decisions: DecisionController,
    request: DecisionRequest,
    result: DecisionResult,
    battle_shock_hooks: BattleShockHookRegistry,
) -> LifecycleStatus | None:
    try:
        result.validate_for_request(request)
        validate_command_battle_shock_reroll_context(
            state=state,
            decisions=decisions,
            request=request,
            battle_shock_hooks=battle_shock_hooks,
            pending=True,
        )
    except (
        DecisionError,
        DiceError,
        GameLifecycleError,
    ):
        return LifecycleStatus.invalid(
            stage=state.stage,
            message="Command Battle-shock reroll context is no longer valid.",
            payload={"invalid_reason": "command_battle_shock_reroll_context_drift"},
        )
    return None


def validate_command_battle_shock_reroll_context(
    *,
    state: GameState,
    decisions: DecisionController,
    request: DecisionRequest,
    battle_shock_hooks: BattleShockHookRegistry,
    pending: bool,
) -> BattleShockTestRequest:
    if type(battle_shock_hooks) is not BattleShockHookRegistry:
        raise GameLifecycleError("Command Battle-shock reroll requires hook registry.")
    if type(pending) is not bool:
        raise GameLifecycleError("Command Battle-shock reroll pending flag must be a bool.")
    if state.stage is not GameLifecycleStage.BATTLE:
        raise GameLifecycleError("Battle-shock reroll can be applied only during battle.")
    if state.current_battle_phase is not BattlePhase.COMMAND:
        raise GameLifecycleError("Battle-shock reroll can be applied only in command.")
    if request.decision_type != DICE_REROLL_DECISION_TYPE:
        raise GameLifecycleError("Command Battle-shock reroll decision type drift.")
    request_payload = _payload_object(request.payload, context="Decision payload")
    context_payload = _payload_object(
        request_payload.get(BATTLE_SHOCK_REROLL_CONTEXT_KEY),
        context="Battle-shock reroll context",
    )
    if _payload_string(context_payload, key=BATTLE_SHOCK_REROLL_SOURCE_KIND_KEY) != (
        COMMAND_BATTLE_SHOCK_REROLL_SOURCE_KIND
    ):
        raise GameLifecycleError("Battle-shock reroll source kind drift.")
    if _payload_string(context_payload, key="game_id") != state.game_id:
        raise GameLifecycleError("Battle-shock reroll game_id drift.")
    if _payload_int(context_payload, key="battle_round") != state.battle_round:
        raise GameLifecycleError("Battle-shock reroll battle_round drift.")
    if _payload_string(context_payload, key="phase") != BattlePhase.COMMAND.value:
        raise GameLifecycleError("Battle-shock reroll phase payload drift.")
    active_player_id = _active_player_id(state)
    if _payload_string(context_payload, key="active_player_id") != active_player_id:
        raise GameLifecycleError("Battle-shock reroll active_player_id drift.")
    if _payload_object(
        context_payload.get("base_payload"),
        context="Battle-shock reroll base payload",
    ) != {
        "game_id": state.game_id,
        "battle_round": state.battle_round,
        "active_player_id": active_player_id,
        "phase": BattlePhase.COMMAND.value,
        "source_kind": COMMAND_BATTLE_SHOCK_REROLL_SOURCE_KIND,
    }:
        raise GameLifecycleError("Command Battle-shock reroll base payload drift.")
    if _payload_string_tuple(context_payload, key="resolved_event_types") != (
        "battle_shock_test_resolved",
    ):
        raise GameLifecycleError("Command Battle-shock reroll resolved event types drift.")
    command_state = _command_step_state(state)
    if command_state.current_step is not CommandPhaseStep.BATTLE_SHOCK:
        raise GameLifecycleError("Battle-shock reroll requires the Battle-shock step.")
    if command_state.active_player_id != active_player_id:
        raise GameLifecycleError("Battle-shock reroll command state active player drift.")
    if command_state.battle_round != state.battle_round:
        raise GameLifecycleError("Battle-shock reroll command state round drift.")
    if command_state.battle_shock_step_resolved:
        raise GameLifecycleError("Battle-shock reroll step is already resolved.")
    ordered_completed_command_battle_shock_results(
        state=state,
        event_records=decisions.event_log.records,
        decision_records=decisions.records,
    )
    phase_start_ids = _payload_string_tuple(
        context_payload,
        key="phase_start_battle_shocked_unit_ids",
    )
    if phase_start_ids != command_state.battle_shock_phase_start_unit_ids:
        raise GameLifecycleError("Battle-shock reroll phase-start unit IDs drift.")
    if _payload_string(context_payload, key=PASSED_STATE_POLICY_CONTEXT_KEY) != (
        BattleShockPassedStatePolicy.CLEAR_IF_STEP_START_SHOCKED.value
    ):
        raise GameLifecycleError("Command Battle-shock reroll passed-state policy drift.")
    battle_shock_request = BattleShockTestRequest.from_payload(
        cast(
            BattleShockTestRequestPayload,
            _payload_object(
                context_payload.get("battle_shock_test_request"),
                context="Battle-shock test request",
            ),
        )
    )
    if battle_shock_request != command_state.battle_shock_in_flight_test_request:
        raise GameLifecycleError("Battle-shock reroll request is not the in-flight test.")
    if request.actor_id != battle_shock_request.player_id:
        raise GameLifecycleError("Battle-shock reroll request actor drift.")
    initial_roll_state = DiceRollState.from_payload(
        cast(
            DiceRollStatePayload,
            _payload_object(
                context_payload.get("battle_shock_roll_state"),
                context="Battle-shock roll state",
            ),
        )
    )
    if (
        initial_roll_state != DiceRollState.from_result(initial_roll_state.original_result)
        or initial_roll_state.original_result.spec != battle_shock_request.spec
    ):
        raise GameLifecycleError("Command Battle-shock reroll initial roll state drift.")
    expected_permission = battle_shock_hooks.reroll_permission_for(
        BattleShockRerollPermissionContext(
            state=state,
            request=battle_shock_request,
            active_player_id=active_player_id,
            phase=BattlePhase.COMMAND,
            phase_start_battle_shocked_unit_ids=phase_start_ids,
        )
    )
    if expected_permission is None:
        raise GameLifecycleError("Command Battle-shock reroll permission is no longer valid.")
    expected_request = DiceRollManager(state.game_id).build_reroll_request(
        initial_roll_state,
        request_id=request.request_id,
        actor_id=battle_shock_request.player_id,
        permission=expected_permission,
        extra_payload={
            BATTLE_SHOCK_REROLL_CONTEXT_KEY: {
                BATTLE_SHOCK_REROLL_SOURCE_KIND_KEY: (COMMAND_BATTLE_SHOCK_REROLL_SOURCE_KIND),
                "game_id": state.game_id,
                "battle_round": state.battle_round,
                "phase": BattlePhase.COMMAND.value,
                "active_player_id": active_player_id,
                "battle_shock_test_request": validate_json_value(battle_shock_request.to_payload()),
                "battle_shock_roll_state": validate_json_value(initial_roll_state.to_payload()),
                "phase_start_battle_shocked_unit_ids": list(phase_start_ids),
                PASSED_STATE_POLICY_CONTEXT_KEY: (
                    BattleShockPassedStatePolicy.CLEAR_IF_STEP_START_SHOCKED.value
                ),
                "base_payload": {
                    "game_id": state.game_id,
                    "battle_round": state.battle_round,
                    "active_player_id": active_player_id,
                    "phase": BattlePhase.COMMAND.value,
                    "source_kind": COMMAND_BATTLE_SHOCK_REROLL_SOURCE_KIND,
                },
                "resolved_event_types": ["battle_shock_test_resolved"],
                ADDITIONAL_MODIFIER_APPLICATIONS_CONTEXT_KEY: [],
            }
        },
    )
    if request != expected_request:
        raise GameLifecycleError("Command Battle-shock reroll request authority drift.")
    _validate_pending_or_recorded_event_authority(
        state=state,
        decisions=decisions,
        request=request,
        battle_shock_request=battle_shock_request,
        initial_roll_state=initial_roll_state,
        pending=pending,
    )
    return battle_shock_request


def _validate_pending_or_recorded_event_authority(
    *,
    state: GameState,
    decisions: DecisionController,
    request: DecisionRequest,
    battle_shock_request: BattleShockTestRequest,
    initial_roll_state: DiceRollState,
    pending: bool,
) -> None:
    event_records = decisions.event_log.records
    snapshot_index = validate_command_battle_shock_snapshot_authority(
        state=state,
        event_records=event_records,
    )
    expected_test_request_payload = validate_json_value(
        {
            "game_id": state.game_id,
            "battle_round": state.battle_round,
            "active_player_id": battle_shock_request.player_id,
            "phase": BattlePhase.COMMAND.value,
            "source_kind": COMMAND_BATTLE_SHOCK_REROLL_SOURCE_KIND,
            "battle_shock_test_request": battle_shock_request.to_payload(),
        }
    )
    request_indices = tuple(
        index
        for index, event in enumerate(event_records)
        if event.event_type == "battle_shock_test_requested"
        and event.payload == expected_test_request_payload
    )
    dice_indices = tuple(
        index
        for index, event in enumerate(event_records)
        if event.event_type == "dice_rolled"
        and event.payload == initial_roll_state.original_result.to_payload()
    )
    decision_request_indices = tuple(
        index
        for index, event in enumerate(event_records)
        if event.event_type == "decision_requested" and event.payload == request.to_payload()
    )
    if (
        len(request_indices) != 1
        or len(dice_indices) != 1
        or len(decision_request_indices) != 1
        or not snapshot_index < request_indices[0] < dice_indices[0] < decision_request_indices[0]
    ):
        raise GameLifecycleError("Command Battle-shock pending reroll event order drift.")
    matching_records = tuple(record for record in decisions.records if record.request == request)
    if pending:
        if decisions.queue.peek_next() != request or matching_records:
            raise GameLifecycleError("Command Battle-shock pending reroll queue drift.")
        return
    if len(matching_records) != 1:
        raise GameLifecycleError("Command Battle-shock recorded reroll authority drift.")
    decision_record_indices = tuple(
        index
        for index, event in enumerate(event_records)
        if event.event_type == "decision_recorded"
        and event.payload == matching_records[0].to_payload()
    )
    if (
        len(decision_record_indices) != 1
        or decision_record_indices[0] <= decision_request_indices[0]
    ):
        raise GameLifecycleError("Command Battle-shock recorded reroll event order drift.")


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
