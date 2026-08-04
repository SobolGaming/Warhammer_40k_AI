from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from typing import TYPE_CHECKING, Self

from warhammer40k_core.core.validation import IdentifierValidator
from warhammer40k_core.engine.decision_controller import DecisionController
from warhammer40k_core.engine.event_log import EventLog, JsonValue, validate_json_value
from warhammer40k_core.engine.lifecycle_hooks import LifecycleHookEvent, validate_hook_bindings
from warhammer40k_core.engine.phase import BattlePhase, GameLifecycleError

if TYPE_CHECKING:
    from warhammer40k_core.engine.game_state import GameState
    from warhammer40k_core.engine.unit_factory import ModelInstance


type UnitDestroyedHandler = Callable[["UnitDestroyedContext"], None]


@dataclass(frozen=True, slots=True)
class UnitDestroyedContext:
    state: GameState
    decisions: DecisionController
    completed_phase: BattlePhase
    model_destroyed_event_id: str
    model_destroyed_payload: dict[str, JsonValue]
    destroying_player_id: str
    destroyed_unit_instance_id: str
    destroyed_player_id: str

    def __post_init__(self) -> None:
        from warhammer40k_core.engine.game_state import GameState

        if type(self.state) is not GameState:
            raise GameLifecycleError("UnitDestroyedContext state must be GameState.")
        if type(self.decisions) is not DecisionController:
            raise GameLifecycleError("UnitDestroyedContext decisions must be DecisionController.")
        object.__setattr__(self, "completed_phase", _battle_phase_from_token(self.completed_phase))
        object.__setattr__(
            self,
            "model_destroyed_event_id",
            _validate_identifier("model_destroyed_event_id", self.model_destroyed_event_id),
        )
        payload = validate_json_value(self.model_destroyed_payload)
        if not isinstance(payload, dict):
            raise GameLifecycleError("UnitDestroyedContext model_destroyed_payload must be object.")
        object.__setattr__(self, "model_destroyed_payload", payload)
        object.__setattr__(
            self,
            "destroying_player_id",
            _validate_identifier("destroying_player_id", self.destroying_player_id),
        )
        object.__setattr__(
            self,
            "destroyed_unit_instance_id",
            _validate_identifier("destroyed_unit_instance_id", self.destroyed_unit_instance_id),
        )
        object.__setattr__(
            self,
            "destroyed_player_id",
            _validate_identifier("destroyed_player_id", self.destroyed_player_id),
        )
        if self.destroying_player_id == self.destroyed_player_id:
            raise GameLifecycleError("UnitDestroyedContext requires enemy destruction.")


@dataclass(frozen=True, slots=True)
class UnitDestroyedHookBinding:
    hook_id: str
    source_id: str
    handler: UnitDestroyedHandler

    def __post_init__(self) -> None:
        object.__setattr__(self, "hook_id", _validate_identifier("hook_id", self.hook_id))
        object.__setattr__(self, "source_id", _validate_identifier("source_id", self.source_id))
        if not callable(self.handler):
            raise GameLifecycleError("UnitDestroyedHookBinding handler must be callable.")


@dataclass(frozen=True, slots=True)
class UnitDestroyedHookRegistry:
    bindings: tuple[UnitDestroyedHookBinding, ...]

    def __post_init__(self) -> None:
        object.__setattr__(self, "bindings", _validate_bindings(self.bindings))

    @classmethod
    def empty(cls) -> Self:
        return cls(bindings=())

    @classmethod
    def from_bindings(cls, bindings: tuple[UnitDestroyedHookBinding, ...]) -> Self:
        return cls(bindings=bindings)

    def all_bindings(self) -> tuple[UnitDestroyedHookBinding, ...]:
        return self.bindings

    def resolve(self, context: UnitDestroyedContext) -> None:
        if type(context) is not UnitDestroyedContext:
            raise GameLifecycleError("Unit-destroyed hooks require context.")
        for binding in self.bindings:
            binding.handler(context)


def unit_destruction_completion_events_for_phase(
    *,
    state: GameState,
    event_log: EventLog,
    completed_phase: BattlePhase,
) -> tuple[tuple[str, dict[str, JsonValue]], ...]:
    from warhammer40k_core.engine.game_state import GameState

    if type(state) is not GameState:
        raise GameLifecycleError("Unit-destruction completion lookup requires GameState.")
    if type(event_log) is not EventLog:
        raise GameLifecycleError("Unit-destruction completion lookup requires EventLog.")
    phase = _battle_phase_from_token(completed_phase)
    if state.battlefield_state is None:
        return ()
    events_by_unit: dict[str, list[tuple[int, str, dict[str, JsonValue]]]] = {}
    for event_order, record in enumerate(event_log.records):
        if record.event_type != "model_destroyed":
            continue
        payload = record.payload
        if not isinstance(payload, dict):
            raise GameLifecycleError("model_destroyed event payload must be an object.")
        event_payload = validate_json_value(payload)
        if not isinstance(event_payload, dict):
            raise GameLifecycleError("model_destroyed event payload must be an object.")
        if event_payload.get("game_id") != state.game_id:
            continue
        if event_payload.get("battle_round") != state.battle_round:
            continue
        if event_payload.get("active_player_id") != state.active_player_id:
            continue
        if event_payload.get("phase") != phase.value:
            continue
        target_unit_id = _payload_identifier(event_payload, key="target_unit_instance_id")
        events_by_unit.setdefault(target_unit_id, []).append(
            (event_order, record.event_id, dict(event_payload))
        )
    completions: list[tuple[int, str, dict[str, JsonValue]]] = []
    for target_unit_id, events in events_by_unit.items():
        models = _models_for_unit(state=state, unit_instance_id=target_unit_id)
        if models and not any(model.is_alive for model in models):
            completions.append(sorted(events, key=lambda item: item[0])[-1])
    return tuple((event_id, payload) for _order, event_id, payload in sorted(completions))


def _models_for_unit(*, state: GameState, unit_instance_id: str) -> tuple[ModelInstance, ...]:
    requested_unit_id = _validate_identifier("unit_instance_id", unit_instance_id)
    for army in state.army_definitions:
        for unit in army.units:
            if unit.unit_instance_id == requested_unit_id:
                return tuple(unit.own_models)
    raise GameLifecycleError("Model lookup failed for unit-destruction completion.")


def _payload_identifier(payload: dict[str, JsonValue], *, key: str) -> str:
    if key not in payload:
        raise GameLifecycleError(f"Unit-destruction event payload missing {key}.")
    return _validate_identifier(key, payload[key])


def _validate_bindings(value: object) -> tuple[UnitDestroyedHookBinding, ...]:
    return validate_hook_bindings(
        value,
        lifecycle_event=LifecycleHookEvent.UNIT_DESTROYED,
        binding_type=UnitDestroyedHookBinding,
        registry_name="UnitDestroyedHookRegistry",
        invalid_binding_message="UnitDestroyedHookRegistry requires hook bindings.",
    )


def _battle_phase_from_token(token: object) -> BattlePhase:
    if type(token) is BattlePhase:
        return token
    if type(token) is not str:
        raise GameLifecycleError("Unit-destroyed hook phase must be BattlePhase.")
    try:
        return BattlePhase(token)
    except ValueError as exc:
        raise GameLifecycleError(f"Unsupported unit-destroyed hook phase: {token}.") from exc


_validate_identifier = IdentifierValidator(GameLifecycleError)
