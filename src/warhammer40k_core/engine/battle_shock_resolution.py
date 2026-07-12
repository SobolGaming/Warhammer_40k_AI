from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, cast

from warhammer40k_core.core.dice import DiceRollState, DiceRollStatePayload
from warhammer40k_core.core.validation import IdentifierValidator
from warhammer40k_core.engine.battle_shock import (
    BattleShockResult,
    BattleShockTestRequest,
    BattleShockTestRequestPayload,
)
from warhammer40k_core.engine.battle_shock_hooks import (
    BattleShockHookRegistry,
    BattleShockModifierContext,
    BattleShockOutcomeContext,
    BattleShockRerollPermissionContext,
)
from warhammer40k_core.engine.decision_controller import DecisionController
from warhammer40k_core.engine.decision_request import DecisionRequest
from warhammer40k_core.engine.decision_result import DecisionResult
from warhammer40k_core.engine.dice import DICE_REROLL_DECISION_TYPE, DiceRollManager
from warhammer40k_core.engine.event_log import JsonValue, validate_json_value
from warhammer40k_core.engine.phase import (
    BattlePhase,
    GameLifecycleError,
    GameLifecycleStage,
    LifecycleStatus,
)

if TYPE_CHECKING:
    from warhammer40k_core.engine.game_state import GameState

BATTLE_SHOCK_REROLL_CONTEXT_KEY = "battle_shock_context"
BATTLE_SHOCK_REROLL_SOURCE_KIND_KEY = "source_kind"


@dataclass(frozen=True, slots=True)
class BattleShockResolutionResult:
    resolved_payload: dict[str, JsonValue] | None
    pending_status: LifecycleStatus | None

    def __post_init__(self) -> None:
        if (self.resolved_payload is None) == (self.pending_status is None):
            raise GameLifecycleError(
                "Battle-shock resolution must be resolved or pending, but not both."
            )
        if self.resolved_payload is not None:
            object.__setattr__(
                self,
                "resolved_payload",
                _validate_json_object("resolved_payload", self.resolved_payload),
            )
        if self.pending_status is not None and type(self.pending_status) is not LifecycleStatus:
            raise GameLifecycleError("Battle-shock pending status must be LifecycleStatus.")


def resolve_battle_shock_test_with_optional_reroll(
    *,
    state: GameState,
    decisions: DecisionController,
    manager: DiceRollManager,
    battle_shock_hooks: BattleShockHookRegistry,
    request: BattleShockTestRequest,
    roll_state: DiceRollState,
    active_player_id: str,
    phase: BattlePhase,
    phase_start_battle_shocked_unit_ids: tuple[str, ...],
    source_kind: str,
    base_payload: dict[str, JsonValue],
    resolved_event_types: tuple[str, ...],
    pending_phase_body_status: str,
) -> BattleShockResolutionResult:
    from warhammer40k_core.engine.game_state import GameState

    if type(state) is not GameState:
        raise GameLifecycleError("Battle-shock resolution requires GameState.")
    if type(decisions) is not DecisionController:
        raise GameLifecycleError("Battle-shock resolution requires DecisionController.")
    if type(manager) is not DiceRollManager:
        raise GameLifecycleError("Battle-shock resolution requires DiceRollManager.")
    if type(battle_shock_hooks) is not BattleShockHookRegistry:
        raise GameLifecycleError("Battle-shock resolution requires Battle-shock hooks.")
    if type(request) is not BattleShockTestRequest:
        raise GameLifecycleError("Battle-shock resolution requires a test request.")
    if type(roll_state) is not DiceRollState:
        raise GameLifecycleError("Battle-shock resolution requires a dice roll state.")
    requested_phase = _battle_phase_from_token(phase)
    active_player = _validate_identifier("active_player_id", active_player_id)
    source = _validate_identifier("source_kind", source_kind)
    phase_start_ids = _validate_identifier_tuple(
        "phase_start_battle_shocked_unit_ids",
        phase_start_battle_shocked_unit_ids,
    )
    payload = _validate_json_object("base_payload", base_payload)
    event_types = _validate_identifier_tuple("resolved_event_types", resolved_event_types)
    phase_body_status = _validate_identifier("pending_phase_body_status", pending_phase_body_status)
    permission = battle_shock_hooks.reroll_permission_for(
        BattleShockRerollPermissionContext(
            state=state,
            request=request,
            active_player_id=active_player,
            phase=requested_phase,
            phase_start_battle_shocked_unit_ids=phase_start_ids,
        )
    )
    if permission is None:
        resolved_payload = record_battle_shock_result_and_outcome_events(
            state=state,
            decisions=decisions,
            manager=manager,
            battle_shock_hooks=battle_shock_hooks,
            request=request,
            roll_state=roll_state,
            active_player_id=active_player,
            phase=requested_phase,
            auto_passed=False,
            phase_start_battle_shocked_unit_ids=phase_start_ids,
            base_payload=payload,
            resolved_event_types=event_types,
        )
        return BattleShockResolutionResult(
            resolved_payload=cast(dict[str, JsonValue], resolved_payload),
            pending_status=None,
        )
    reroll_request = manager.build_reroll_request(
        roll_state,
        request_id=state.next_decision_request_id(),
        actor_id=request.player_id,
        permission=permission,
        extra_payload={
            BATTLE_SHOCK_REROLL_CONTEXT_KEY: {
                BATTLE_SHOCK_REROLL_SOURCE_KIND_KEY: source,
                "game_id": state.game_id,
                "battle_round": state.battle_round,
                "phase": requested_phase.value,
                "active_player_id": active_player,
                "battle_shock_test_request": validate_json_value(request.to_payload()),
                "battle_shock_roll_state": validate_json_value(roll_state.to_payload()),
                "phase_start_battle_shocked_unit_ids": list(phase_start_ids),
                "base_payload": validate_json_value(payload),
                "resolved_event_types": list(event_types),
            }
        },
    )
    decisions.request_decision(reroll_request)
    return BattleShockResolutionResult(
        resolved_payload=None,
        pending_status=LifecycleStatus.waiting_for_decision(
            stage=GameLifecycleStage.BATTLE,
            decision_request=reroll_request,
            payload=validate_json_value(
                {
                    "phase": requested_phase.value,
                    "phase_body_status": phase_body_status,
                    "battle_round": state.battle_round,
                    "active_player_id": active_player,
                    "player_id": request.player_id,
                    "target_unit_instance_id": request.unit_instance_id,
                    "pending_request_id": reroll_request.request_id,
                    BATTLE_SHOCK_REROLL_SOURCE_KIND_KEY: source,
                }
            ),
        ),
    )


def apply_battle_shock_reroll_resolution_decision(
    *,
    state: GameState,
    decisions: DecisionController,
    result: DecisionResult,
    battle_shock_hooks: BattleShockHookRegistry,
    expected_source_kind: str,
) -> dict[str, JsonValue]:
    from warhammer40k_core.engine.game_state import GameState

    if type(state) is not GameState:
        raise GameLifecycleError("Battle-shock reroll resolution requires GameState.")
    if type(decisions) is not DecisionController:
        raise GameLifecycleError("Battle-shock reroll resolution requires DecisionController.")
    if type(result) is not DecisionResult:
        raise GameLifecycleError("Battle-shock reroll resolution requires DecisionResult.")
    if type(battle_shock_hooks) is not BattleShockHookRegistry:
        raise GameLifecycleError("Battle-shock reroll resolution requires Battle-shock hooks.")
    if state.stage is not GameLifecycleStage.BATTLE:
        raise GameLifecycleError("Battle-shock reroll can be applied only during battle.")
    phase = state.current_battle_phase
    if type(phase) is not BattlePhase:
        raise GameLifecycleError("Battle-shock reroll requires the current battle phase.")
    source = _validate_identifier("expected_source_kind", expected_source_kind)
    record = decisions.record_for_result(result)
    request_payload = _payload_object(record.request.payload, context="Decision payload")
    context_payload = _payload_object(
        request_payload.get(BATTLE_SHOCK_REROLL_CONTEXT_KEY),
        context="Battle-shock reroll context",
    )
    if _payload_string(context_payload, key=BATTLE_SHOCK_REROLL_SOURCE_KIND_KEY) != source:
        raise GameLifecycleError("Battle-shock reroll source kind drift.")
    if _payload_string(context_payload, key="game_id") != state.game_id:
        raise GameLifecycleError("Battle-shock reroll game_id drift.")
    if _payload_int(context_payload, key="battle_round") != state.battle_round:
        raise GameLifecycleError("Battle-shock reroll battle_round drift.")
    if _payload_string(context_payload, key="phase") != phase.value:
        raise GameLifecycleError("Battle-shock reroll phase payload drift.")
    active_player_id = _active_player_id(state)
    if _payload_string(context_payload, key="active_player_id") != active_player_id:
        raise GameLifecycleError("Battle-shock reroll active_player_id drift.")
    phase_start_ids = _payload_string_tuple(
        context_payload,
        key="phase_start_battle_shocked_unit_ids",
    )
    battle_shock_request = BattleShockTestRequest.from_payload(
        cast(
            BattleShockTestRequestPayload,
            _payload_object(
                context_payload.get("battle_shock_test_request"),
                context="Battle-shock test request",
            ),
        )
    )
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
    base_payload = _payload_json_object(context_payload, key="base_payload")
    resolved_event_types = _payload_string_tuple(context_payload, key="resolved_event_types")
    manager = DiceRollManager(state.game_id, event_log=decisions.event_log)
    rerolled_state = manager.resolve_reroll(
        initial_roll_state,
        request=record.request,
        result=result,
        record_decision=False,
    )
    resolved_payload = record_battle_shock_result_and_outcome_events(
        state=state,
        decisions=decisions,
        manager=manager,
        battle_shock_hooks=battle_shock_hooks,
        request=battle_shock_request,
        roll_state=rerolled_state,
        active_player_id=active_player_id,
        phase=phase,
        auto_passed=False,
        phase_start_battle_shocked_unit_ids=phase_start_ids,
        base_payload=base_payload,
        resolved_event_types=resolved_event_types,
    )
    return cast(dict[str, JsonValue], resolved_payload)


def record_battle_shock_result_and_outcome_events(
    *,
    state: GameState,
    decisions: DecisionController,
    manager: DiceRollManager,
    battle_shock_hooks: BattleShockHookRegistry,
    request: BattleShockTestRequest,
    roll_state: DiceRollState,
    active_player_id: str,
    phase: BattlePhase,
    auto_passed: bool,
    phase_start_battle_shocked_unit_ids: tuple[str, ...],
    base_payload: dict[str, JsonValue],
    resolved_event_types: tuple[str, ...],
) -> JsonValue:
    requested_phase = _battle_phase_from_token(phase)
    active_player = _validate_identifier("active_player_id", active_player_id)
    phase_start_ids = _validate_identifier_tuple(
        "phase_start_battle_shocked_unit_ids",
        phase_start_battle_shocked_unit_ids,
    )
    event_types = _validate_identifier_tuple("resolved_event_types", resolved_event_types)
    payload = _validate_json_object("base_payload", base_payload)
    result = BattleShockResult.from_roll_state(
        result_id=f"{request.request_id}:result",
        request=request,
        roll_state=roll_state,
        modifiers=battle_shock_hooks.modifiers_for(
            BattleShockModifierContext(
                state=state,
                request=request,
                active_player_id=active_player,
                phase=requested_phase,
                phase_start_battle_shocked_unit_ids=phase_start_ids,
            )
        ),
    )
    state_update = "not_required"
    if not result.passed:
        if request.unit_instance_id in phase_start_ids:
            state_update = "already_battle_shocked"
        else:
            state.record_battle_shock_result(result)
            state_update = "recorded_battle_shocked"
    result_payload = validate_json_value(result.to_payload())
    resolved_payload = validate_json_value(
        {
            **payload,
            "battle_shock_result": result_payload,
            "auto_passed": auto_passed,
            "state_update": state_update,
        }
    )
    for event_type in event_types:
        decisions.event_log.append(event_type, resolved_payload)
    battle_shock_hooks.resolve_outcomes(
        BattleShockOutcomeContext(
            state=state,
            decisions=decisions,
            dice_manager=manager,
            result=result,
            active_player_id=active_player,
            phase=requested_phase,
            auto_passed=auto_passed,
            phase_start_battle_shocked_unit_ids=phase_start_ids,
        )
    )
    return resolved_payload


def is_battle_shock_reroll_request(
    request: DecisionRequest,
    *,
    source_kind: str,
) -> bool:
    if type(request) is not DecisionRequest:
        raise GameLifecycleError("Battle-shock reroll detection requires DecisionRequest.")
    if request.decision_type != DICE_REROLL_DECISION_TYPE:
        return False
    request_payload = _payload_object(request.payload, context="Decision payload")
    context_value = request_payload.get(BATTLE_SHOCK_REROLL_CONTEXT_KEY)
    if context_value is None:
        return False
    context_payload = _payload_object(context_value, context="Battle-shock reroll context")
    return _payload_string(context_payload, key=BATTLE_SHOCK_REROLL_SOURCE_KIND_KEY) == (
        _validate_identifier("source_kind", source_kind)
    )


def _payload_object(value: JsonValue, *, context: str) -> dict[str, JsonValue]:
    if not isinstance(value, dict):
        raise GameLifecycleError(f"{context} must be an object.")
    return value


def _payload_json_object(payload: dict[str, JsonValue], *, key: str) -> dict[str, JsonValue]:
    if key not in payload:
        raise GameLifecycleError(f"Decision payload missing required key: {key}.")
    return _payload_object(payload[key], context=f"Decision payload key {key}")


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
    return _validate_identifier(key, payload[key])


def _payload_string_tuple(payload: dict[str, JsonValue], *, key: str) -> tuple[str, ...]:
    if key not in payload:
        raise GameLifecycleError(f"Decision payload missing required key: {key}.")
    value = payload[key]
    if not isinstance(value, list):
        raise GameLifecycleError(f"Decision payload key must be a list: {key}.")
    return _validate_identifier_tuple(key, tuple(value))


def _active_player_id(state: GameState) -> str:
    if state.active_player_id is None:
        raise GameLifecycleError("Battle-shock reroll requires an active player.")
    return _validate_identifier("active_player_id", state.active_player_id)


def _battle_phase_from_token(token: object) -> BattlePhase:
    if type(token) is BattlePhase:
        return token
    if type(token) is not str:
        raise GameLifecycleError("Battle-shock resolution phase must be a BattlePhase.")
    try:
        return BattlePhase(token)
    except ValueError as exc:
        raise GameLifecycleError(f"Unsupported Battle-shock resolution phase: {token}.") from exc


def _validate_json_object(field_name: str, value: object) -> dict[str, JsonValue]:
    if not isinstance(value, dict):
        raise GameLifecycleError(f"Battle-shock resolution {field_name} must be an object.")
    raw_object = cast(dict[str, object], value)
    return cast(dict[str, JsonValue], validate_json_value(raw_object))


def _validate_identifier_tuple(field_name: str, values: object) -> tuple[str, ...]:
    if type(values) is not tuple:
        raise GameLifecycleError(f"Battle-shock resolution {field_name} must be a tuple.")
    identifiers: list[str] = []
    seen: set[str] = set()
    for value in cast(tuple[object, ...], values):
        identifier = _validate_identifier(f"{field_name} value", value)
        if identifier in seen:
            raise GameLifecycleError(
                f"Battle-shock resolution {field_name} must not contain duplicates."
            )
        identifiers.append(identifier)
        seen.add(identifier)
    return tuple(identifiers)


_validate_identifier = IdentifierValidator(GameLifecycleError)
