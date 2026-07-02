from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from enum import StrEnum
from typing import Self, TypedDict, cast

from warhammer40k_core.core.validation import IdentifierValidator
from warhammer40k_core.engine.event_log import validate_json_value
from warhammer40k_core.engine.phase import GameLifecycleError


class LifecycleHookEvent(StrEnum):
    BATTLE_FORMATION = "battle_formation"
    BATTLE_ROUND_START = "battle_round_start"
    TURN_END = "turn_end"
    COMMAND_PHASE_START = "command_phase_start"
    FIGHT_PHASE_START = "fight_phase_start"
    SHOOTING_PHASE_START = "shooting_phase_start"
    UNIT_DESTROYED = "unit_destroyed"
    BATTLE_SHOCK = "battle_shock"
    ADVANCE_ELIGIBILITY = "advance_eligibility"
    ADVANCE_MOVE = "advance_move"
    FALL_BACK_ELIGIBILITY = "fall_back_eligibility"
    MOVEMENT_END_SURGE = "movement_end_surge"
    RESERVE_ARRIVAL_DISTANCE = "reserve_arrival_distance"
    UNIT_MOVE_COMPLETED_MORTAL_WOUND = "unit_move_completed_mortal_wound"
    MORTAL_WOUND_FEEL_NO_PAIN_CONTINUATION = "mortal_wound_feel_no_pain_continuation"
    CHARGE_DECLARATION = "charge_declaration"
    SHOOTING_TARGET_RESTRICTION = "shooting_target_restriction"
    CHARGE_TARGET_RESTRICTION = "charge_target_restriction"
    SHOOTING_UNIT_SELECTED = "shooting_unit_selected"
    SHOOTING_UNIT_SELECTED_GRANT = "shooting_unit_selected_grant"
    ATTACK_SEQUENCE_COMPLETED = "attack_sequence_completed"
    SHOOTING_END_SURGE = "shooting_end_surge"
    FIGHT_ACTIVATION_ABILITY = "fight_activation_ability"
    FIGHT_UNIT_SELECTED = "fight_unit_selected"
    FIGHT_UNIT_SELECTED_GRANT = "fight_unit_selected_grant"
    PHASE_END_OBJECTIVE_CONTROL = "phase_end_objective_control"
    STRATAGEM_COST_CHOICE = "stratagem_cost_choice"


class HookBindingPayload(TypedDict):
    hook_id: str
    source_id: str


class HookRegistryPayload(TypedDict):
    lifecycle_event: str
    bindings: list[HookBindingPayload]


@dataclass(frozen=True, slots=True)
class HookBinding[
    EventT: LifecycleHookEvent,
    HandlerT: Callable[..., object],
]:
    hook_id: str
    source_id: str
    handler: HandlerT

    def __post_init__(self) -> None:
        object.__setattr__(self, "hook_id", _validate_identifier("hook_id", self.hook_id))
        object.__setattr__(self, "source_id", _validate_identifier("source_id", self.source_id))
        if not callable(self.handler):
            raise GameLifecycleError("HookBinding handler must be callable.")

    def to_payload(self) -> HookBindingPayload:
        return {
            "hook_id": self.hook_id,
            "source_id": self.source_id,
        }


@dataclass(frozen=True, slots=True)
class HookRegistry[
    EventT: LifecycleHookEvent,
    HandlerT: Callable[..., object],
]:
    lifecycle_event: EventT
    bindings: tuple[HookBinding[EventT, HandlerT], ...]

    def __post_init__(self) -> None:
        if type(self.lifecycle_event) is not LifecycleHookEvent:
            raise GameLifecycleError("HookRegistry lifecycle_event must be LifecycleHookEvent.")
        object.__setattr__(
            self,
            "bindings",
            cast(tuple[HookBinding[EventT, HandlerT], ...], _validate_hook_bindings(self.bindings)),
        )

    @classmethod
    def empty(cls, lifecycle_event: EventT) -> Self:
        return cls(lifecycle_event=lifecycle_event, bindings=())

    @classmethod
    def from_bindings(
        cls,
        lifecycle_event: EventT,
        bindings: tuple[HookBinding[EventT, HandlerT], ...],
    ) -> Self:
        return cls(lifecycle_event=lifecycle_event, bindings=bindings)

    def all_bindings(self) -> tuple[HookBinding[EventT, HandlerT], ...]:
        return self.bindings

    def binding_for_hook_id(self, hook_id: str) -> HookBinding[EventT, HandlerT] | None:
        validated_hook_id = _validate_identifier("hook_id", hook_id)
        for binding in self.bindings:
            if binding.hook_id == validated_hook_id:
                return binding
        return None

    def to_payload(self) -> HookRegistryPayload:
        payload = {
            "lifecycle_event": self.lifecycle_event.value,
            "bindings": [binding.to_payload() for binding in self.bindings],
        }
        return cast(HookRegistryPayload, validate_json_value(payload))


def _validate_hook_bindings(
    value: object,
) -> tuple[HookBinding[LifecycleHookEvent, Callable[..., object]], ...]:
    if type(value) is not tuple:
        raise GameLifecycleError("HookRegistry bindings must be a tuple.")
    bindings: list[HookBinding[LifecycleHookEvent, Callable[..., object]]] = []
    seen: set[str] = set()
    for binding in cast(tuple[object, ...], value):
        if type(binding) is not HookBinding:
            raise GameLifecycleError("HookRegistry bindings must contain HookBinding values.")
        if binding.hook_id in seen:
            raise GameLifecycleError("HookRegistry hook IDs must be unique.")
        seen.add(binding.hook_id)
        bindings.append(cast(HookBinding[LifecycleHookEvent, Callable[..., object]], binding))
    return tuple(sorted(bindings, key=lambda binding: binding.hook_id))


_validate_identifier = IdentifierValidator(GameLifecycleError)
