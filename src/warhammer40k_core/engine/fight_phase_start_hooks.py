from __future__ import annotations

from collections.abc import Callable, Mapping
from dataclasses import dataclass, field
from types import MappingProxyType
from typing import TYPE_CHECKING, Self

from warhammer40k_core.core.validation import IdentifierValidator
from warhammer40k_core.engine.abilities import AbilityCatalogIndex
from warhammer40k_core.engine.battle_shock_hooks import BattleShockHookRegistry
from warhammer40k_core.engine.decision_controller import DecisionController
from warhammer40k_core.engine.decision_request import DecisionRequest
from warhammer40k_core.engine.decision_result import DecisionResult
from warhammer40k_core.engine.event_log import JsonValue, validate_json_value
from warhammer40k_core.engine.lifecycle_hooks import LifecycleHookEvent, validate_hook_bindings
from warhammer40k_core.engine.phase import (
    BattlePhase,
    GameLifecycleError,
    GameLifecycleStage,
    LifecycleStatus,
)
from warhammer40k_core.engine.runtime_modifiers import RuntimeModifierRegistry

if TYPE_CHECKING:
    from warhammer40k_core.engine.game_state import GameState


SELECT_FACTION_RULE_FIGHT_PHASE_START_OPTION_DECISION_TYPE = (
    "select_faction_rule_fight_phase_start_option"
)

type FightPhaseStartRequestHandler = Callable[
    ["FightPhaseStartRequestContext"],
    DecisionRequest | None,
]
type FightPhaseStartResultHandler = Callable[
    ["FightPhaseStartResultContext"],
    bool | LifecycleStatus,
]


@dataclass(frozen=True, slots=True)
class FightPhaseStartRequestContext:
    state: GameState
    decisions: DecisionController

    def __post_init__(self) -> None:
        from warhammer40k_core.engine.game_state import GameState

        if type(self.state) is not GameState:
            raise GameLifecycleError("FightPhaseStartRequestContext state must be GameState.")
        if type(self.decisions) is not DecisionController:
            raise GameLifecycleError(
                "FightPhaseStartRequestContext decisions must be DecisionController."
            )
        _validate_fight_phase_start_state(self.state)


@dataclass(frozen=True, slots=True)
class FightPhaseStartResultContext:
    state: GameState
    decisions: DecisionController
    request: DecisionRequest
    result: DecisionResult
    battle_shock_hooks: BattleShockHookRegistry = field(
        default_factory=BattleShockHookRegistry.empty
    )
    runtime_modifier_registry: RuntimeModifierRegistry = field(
        default_factory=RuntimeModifierRegistry.empty
    )
    ability_indexes_by_player_id: Mapping[str, AbilityCatalogIndex] = field(
        default_factory=lambda: MappingProxyType({})
    )

    def __post_init__(self) -> None:
        from warhammer40k_core.engine.game_state import GameState

        if type(self.state) is not GameState:
            raise GameLifecycleError("FightPhaseStartResultContext state must be GameState.")
        if type(self.decisions) is not DecisionController:
            raise GameLifecycleError(
                "FightPhaseStartResultContext decisions must be DecisionController."
            )
        if type(self.request) is not DecisionRequest:
            raise GameLifecycleError(
                "FightPhaseStartResultContext request must be DecisionRequest."
            )
        if type(self.result) is not DecisionResult:
            raise GameLifecycleError("FightPhaseStartResultContext result must be DecisionResult.")
        if type(self.battle_shock_hooks) is not BattleShockHookRegistry:
            raise GameLifecycleError(
                "FightPhaseStartResultContext Battle-shock hooks must be a registry."
            )
        if type(self.runtime_modifier_registry) is not RuntimeModifierRegistry:
            raise GameLifecycleError(
                "FightPhaseStartResultContext runtime modifiers must be a registry."
            )
        indexes = dict(self.ability_indexes_by_player_id)
        if any(type(player_id) is not str for player_id in indexes) or any(
            type(index) is not AbilityCatalogIndex for index in indexes.values()
        ):
            raise GameLifecycleError("FightPhaseStartResultContext ability indexes are invalid.")
        object.__setattr__(self, "ability_indexes_by_player_id", MappingProxyType(indexes))
        if self.request.decision_type != SELECT_FACTION_RULE_FIGHT_PHASE_START_OPTION_DECISION_TYPE:
            raise GameLifecycleError("FightPhaseStartResultContext request decision_type drift.")
        _validate_fight_phase_start_state(self.state)


@dataclass(frozen=True, slots=True)
class FightPhaseStartHookBinding:
    hook_id: str
    source_id: str
    request_handler: FightPhaseStartRequestHandler | None = None
    result_handler: FightPhaseStartResultHandler | None = None

    def __post_init__(self) -> None:
        object.__setattr__(self, "hook_id", _validate_identifier("hook_id", self.hook_id))
        object.__setattr__(self, "source_id", _validate_identifier("source_id", self.source_id))
        if self.request_handler is None and self.result_handler is None:
            raise GameLifecycleError("FightPhaseStartHookBinding requires a handler.")
        if self.request_handler is not None and not callable(self.request_handler):
            raise GameLifecycleError("FightPhaseStartHookBinding request_handler must be callable.")
        if self.result_handler is not None and not callable(self.result_handler):
            raise GameLifecycleError("FightPhaseStartHookBinding result_handler must be callable.")


@dataclass(frozen=True, slots=True)
class FightPhaseStartHookRegistry:
    bindings: tuple[FightPhaseStartHookBinding, ...]

    def __post_init__(self) -> None:
        object.__setattr__(self, "bindings", _validate_hook_bindings(self.bindings))

    @classmethod
    def empty(cls) -> Self:
        return cls(bindings=())

    @classmethod
    def from_bindings(cls, bindings: tuple[FightPhaseStartHookBinding, ...]) -> Self:
        return cls(bindings=bindings)

    def all_bindings(self) -> tuple[FightPhaseStartHookBinding, ...]:
        return self.bindings

    def next_request_for(
        self,
        context: FightPhaseStartRequestContext,
    ) -> DecisionRequest | None:
        if type(context) is not FightPhaseStartRequestContext:
            raise GameLifecycleError("Fight-phase start request hooks require context.")
        requests: list[DecisionRequest] = []
        for binding in self.bindings:
            if binding.request_handler is None:
                continue
            request = binding.request_handler(context)
            if request is None:
                continue
            if type(request) is not DecisionRequest:
                raise GameLifecycleError(
                    "Fight-phase start request handlers must return DecisionRequest or None."
                )
            requests.append(request)
        if len(requests) > 1:
            raise GameLifecycleError(
                "Fight-phase start hooks produced multiple simultaneous requests."
            )
        if not requests:
            return None
        return requests[0]

    def apply_result(self, context: FightPhaseStartResultContext) -> bool | LifecycleStatus:
        if type(context) is not FightPhaseStartResultContext:
            raise GameLifecycleError("Fight-phase start result hooks require context.")
        handled_results: list[bool | LifecycleStatus] = []
        for binding in self.bindings:
            if binding.result_handler is None:
                continue
            handled = binding.result_handler(context)
            if type(handled) is not bool and type(handled) is not LifecycleStatus:
                raise GameLifecycleError(
                    "Fight-phase start result handlers must return bool or status."
                )
            if handled:
                handled_results.append(handled)
        if len(handled_results) > 1:
            raise GameLifecycleError("Fight-phase start result was handled by multiple hooks.")
        if not handled_results:
            return False
        return handled_results[0]


def apply_fight_phase_start_result(
    *,
    registry: FightPhaseStartHookRegistry,
    state: GameState,
    decisions: DecisionController,
    result: DecisionResult,
    battle_shock_hooks: BattleShockHookRegistry,
    runtime_modifier_registry: RuntimeModifierRegistry,
    ability_indexes_by_player_id: Mapping[str, AbilityCatalogIndex],
) -> LifecycleStatus | None:
    phase_start_result = registry.apply_result(
        FightPhaseStartResultContext(
            state=state,
            decisions=decisions,
            request=decisions.record_for_result(result).request,
            result=result,
            battle_shock_hooks=battle_shock_hooks,
            runtime_modifier_registry=runtime_modifier_registry,
            ability_indexes_by_player_id=ability_indexes_by_player_id,
        )
    )
    if type(phase_start_result) is LifecycleStatus:
        return phase_start_result
    if phase_start_result:
        return None
    raise GameLifecycleError("Faction rule Fight-phase start decision was not handled.")


def request_fight_phase_start_rule_if_available(
    *,
    registry: FightPhaseStartHookRegistry,
    state: GameState,
    decisions: DecisionController,
) -> LifecycleStatus | None:
    request = registry.next_request_for(
        FightPhaseStartRequestContext(
            state=state,
            decisions=decisions,
        )
    )
    if request is None:
        return None
    decisions.request_decision(request)
    decisions.event_log.append(
        "fight_phase_start_faction_rule_requested",
        validate_json_value(
            {
                "game_id": state.game_id,
                "battle_round": state.battle_round,
                "active_player_id": _active_player_id(state),
                "phase": BattlePhase.FIGHT.value,
                "decision_type": request.decision_type,
                "request_id": request.request_id,
                "actor_id": request.actor_id,
            }
        ),
    )
    return LifecycleStatus.waiting_for_decision(
        stage=GameLifecycleStage.BATTLE,
        decision_request=request,
        payload=validate_json_value(
            {
                "phase": BattlePhase.FIGHT.value,
                "active_player_id": _active_player_id(state),
                "phase_body_status": "fight_phase_start_faction_rule_pending",
                "request_id": request.request_id,
            }
        ),
    )


def invalid_fight_phase_start_faction_rule_status(
    *,
    state: GameState,
    request: DecisionRequest,
    result: DecisionResult,
) -> LifecycleStatus | None:
    invalid_status = _invalid_finite_decision_status(
        state=state,
        request=request,
        result=result,
        invalid_reason="invalid_fight_phase_start_faction_rule_result",
    )
    if invalid_status is not None:
        return invalid_status
    payload = _decision_payload_object(result.payload)
    request_payload = _decision_payload_object(request.payload)
    drift_reason = _fight_phase_start_faction_rule_drift_reason(
        state=state,
        request=request,
        result=result,
        payload=payload,
        request_payload=request_payload,
    )
    if drift_reason is None:
        return None
    return LifecycleStatus.invalid(
        stage=state.stage,
        message="Fight phase start faction rule option drifted.",
        payload=validate_json_value(
            {
                "game_id": state.game_id,
                "player_id": result.actor_id,
                "battle_round": state.battle_round,
                "phase": (
                    None if state.current_battle_phase is None else state.current_battle_phase.value
                ),
                "invalid_reason": drift_reason,
            }
        ),
    )


def _fight_phase_start_faction_rule_drift_reason(
    *,
    state: GameState,
    request: DecisionRequest,
    result: DecisionResult,
    payload: dict[str, JsonValue],
    request_payload: dict[str, JsonValue],
) -> str | None:
    if result.actor_id is None:
        return "actor_missing"
    if request.actor_id != result.actor_id:
        return "actor_player_drift"
    if _payload_string(payload, key="game_id") != state.game_id:
        return "game_id_drift"
    if _payload_int(payload, key="battle_round") != state.battle_round:
        return "battle_round_drift"
    if _payload_string(payload, key="phase") != BattlePhase.FIGHT.value:
        return "payload_phase_drift"
    if _payload_string(payload, key="active_player_id") != _active_player_id(state):
        return "active_player_drift"
    if _payload_string(request_payload, key="game_id") != state.game_id:
        return "request_game_id_drift"
    if _payload_int(request_payload, key="battle_round") != state.battle_round:
        return "request_battle_round_drift"
    if _payload_string(request_payload, key="phase") != BattlePhase.FIGHT.value:
        return "request_phase_drift"
    if _payload_string(request_payload, key="active_player_id") != _active_player_id(state):
        return "request_active_player_drift"
    if state.current_battle_phase is not BattlePhase.FIGHT:
        return "phase_drift"
    if state.fight_phase_state is not None:
        return "fight_phase_start_window_closed"
    return None


def _validate_hook_bindings(value: object) -> tuple[FightPhaseStartHookBinding, ...]:
    return validate_hook_bindings(
        value,
        lifecycle_event=LifecycleHookEvent.FIGHT_PHASE_START,
        binding_type=FightPhaseStartHookBinding,
        registry_name="FightPhaseStartHookRegistry",
        invalid_binding_message="FightPhaseStartHookRegistry requires hook bindings.",
    )


def _validate_fight_phase_start_state(state: GameState) -> None:
    if state.stage is not GameLifecycleStage.BATTLE:
        raise GameLifecycleError("Fight-phase start hooks require battle stage.")
    if state.current_battle_phase is not BattlePhase.FIGHT:
        raise GameLifecycleError("Fight-phase start hooks require Fight phase.")


def _decision_payload_object(payload: JsonValue) -> dict[str, JsonValue]:
    if not isinstance(payload, dict):
        raise GameLifecycleError("Fight decision payload must be an object.")
    return payload


def _invalid_finite_decision_status(
    *,
    state: GameState,
    request: DecisionRequest,
    result: DecisionResult,
    invalid_reason: str,
) -> LifecycleStatus | None:
    if result.request_id != request.request_id:
        return LifecycleStatus.invalid(
            stage=state.stage,
            message="Decision result does not match the pending request.",
            payload={"invalid_reason": invalid_reason, "field": "request_id"},
        )
    if result.decision_type != request.decision_type:
        return LifecycleStatus.invalid(
            stage=state.stage,
            message="Decision result type does not match the pending request.",
            payload={"invalid_reason": invalid_reason, "field": "decision_type"},
        )
    if result.actor_id != request.actor_id:
        return LifecycleStatus.invalid(
            stage=state.stage,
            message="Decision result actor does not match the pending request.",
            payload={"invalid_reason": invalid_reason, "field": "actor_id"},
        )
    if result.selected_option_id not in {option.option_id for option in request.options}:
        return LifecycleStatus.invalid(
            stage=state.stage,
            message="Decision result selected option is not pending.",
            payload={"invalid_reason": invalid_reason, "field": "selected_option_id"},
        )
    selected_payload = next(
        option.payload
        for option in request.options
        if option.option_id == result.selected_option_id
    )
    if result.payload != selected_payload:
        return LifecycleStatus.invalid(
            stage=state.stage,
            message="Decision result payload does not match the selected option.",
            payload={"invalid_reason": invalid_reason, "field": "payload"},
        )
    return None


def _payload_string(payload: dict[str, JsonValue], *, key: str) -> str:
    value = payload.get(key)
    if type(value) is not str:
        raise GameLifecycleError(f"{key} must be a string.")
    return value


def _payload_int(payload: dict[str, JsonValue], *, key: str) -> int:
    value = payload.get(key)
    if type(value) is not int:
        raise GameLifecycleError(f"{key} must be an integer.")
    return value


def _active_player_id(state: GameState) -> str:
    if state.active_player_id is None:
        raise GameLifecycleError("Fight phase requires an active player.")
    return state.active_player_id


_validate_identifier = IdentifierValidator(GameLifecycleError)
