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
    from warhammer40k_core.engine.unit_factory import UnitInstance


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
    for event_order, event_id, event_payload in model_destroyed_events_for_lifecycle_phase(
        state=state,
        event_log=event_log,
        completed_phase=phase,
    ):
        target_unit_id = _payload_identifier(event_payload, key="target_unit_instance_id")
        events_by_unit.setdefault(target_unit_id, []).append(
            (event_order, event_id, dict(event_payload))
        )
    completions_by_unit: dict[str, tuple[int, str, dict[str, JsonValue]]] = {}
    for target_unit_id, events in events_by_unit.items():
        for unit in _component_units_for_target(
            state=state,
            target_unit_instance_id=target_unit_id,
        ):
            models = tuple(unit.own_models)
            model_ids = {model.model_instance_id for model in models}
            component_events = tuple(
                event
                for event in events
                if _payload_identifier(event[2], key="model_instance_id") in model_ids
            )
            if not component_events or not models or any(model.is_alive for model in models):
                continue
            event_order, event_id, event_payload = sorted(
                component_events,
                key=lambda item: item[0],
            )[-1]
            completion_payload = dict(event_payload)
            completion_payload["target_unit_instance_id"] = unit.unit_instance_id
            existing = completions_by_unit.get(unit.unit_instance_id)
            if existing is None or event_order > existing[0]:
                completions_by_unit[unit.unit_instance_id] = (
                    event_order,
                    event_id,
                    completion_payload,
                )
    return tuple(
        (event_id, payload)
        for _order, event_id, payload in sorted(
            completions_by_unit.values(),
            key=lambda item: (item[0], _payload_identifier(item[2], key="target_unit_instance_id")),
        )
    )


def model_destroyed_events_for_lifecycle_phase(
    *,
    state: GameState,
    event_log: EventLog,
    completed_phase: BattlePhase,
) -> tuple[tuple[int, str, dict[str, JsonValue]], ...]:
    """Return destruction events that occurred inside the current lifecycle phase.

    An out-of-phase attack retains its attack phase in ``payload["phase"]``.  Event
    occurrence therefore comes from the lifecycle event boundary, not from that
    attack-semantic field.
    """
    from warhammer40k_core.engine.game_state import GameState

    if type(state) is not GameState:
        raise GameLifecycleError("Model-destruction phase lookup requires GameState.")
    if type(event_log) is not EventLog:
        raise GameLifecycleError("Model-destruction phase lookup requires EventLog.")
    phase = _battle_phase_from_token(completed_phase)
    if state.current_battle_phase is not phase:
        raise GameLifecycleError(
            "Model-destruction phase lookup must match the current lifecycle phase."
        )
    boundary_order = -1
    for event_order, record in enumerate(event_log.records):
        if record.event_type == "battle_phase_completed":
            boundary_order = event_order
    events: list[tuple[int, str, dict[str, JsonValue]]] = []
    for event_order, record in enumerate(event_log.records):
        if event_order <= boundary_order or record.event_type != "model_destroyed":
            continue
        event_payload = validate_json_value(record.payload)
        if not isinstance(event_payload, dict):
            raise GameLifecycleError("model_destroyed event payload must be an object.")
        if event_payload.get("game_id") != state.game_id:
            continue
        if event_payload.get("battle_round") != state.battle_round:
            continue
        if event_payload.get("active_player_id") != state.active_player_id:
            continue
        events.append((event_order, record.event_id, dict(event_payload)))
    return tuple(events)


def _component_units_for_target(
    *,
    state: GameState,
    target_unit_instance_id: str,
) -> tuple[UnitInstance, ...]:
    requested_unit_id = _validate_identifier(
        "target_unit_instance_id",
        target_unit_instance_id,
    )
    physical_units = {
        unit.unit_instance_id: unit for army in state.army_definitions for unit in army.units
    }
    direct = physical_units.get(requested_unit_id)
    if direct is not None:
        return (direct,)
    attached_matches = tuple(
        record
        for record in state.starting_attached_unit_records
        if record.attached_unit_instance_id == requested_unit_id
    )
    if len(attached_matches) != 1:
        raise GameLifecycleError("Model lookup failed for unit-destruction completion.")
    components: list[UnitInstance] = []
    for component_id in attached_matches[0].component_unit_instance_ids:
        component = physical_units.get(component_id)
        if component is None:
            raise GameLifecycleError(
                "Attached-unit destruction completion references an unknown component."
            )
        components.append(component)
    return tuple(sorted(components, key=lambda unit: unit.unit_instance_id))


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
