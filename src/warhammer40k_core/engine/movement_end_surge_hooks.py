from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from typing import TYPE_CHECKING, Self, TypedDict, cast

from warhammer40k_core.core.validation import IdentifierValidator
from warhammer40k_core.engine.event_log import JsonValue, validate_json_value
from warhammer40k_core.engine.phase import BattlePhase, GameLifecycleError

if TYPE_CHECKING:
    from warhammer40k_core.core.ruleset_descriptor import RulesetDescriptor
    from warhammer40k_core.engine.game_state import GameState


class MovementEndSurgeGrantPayload(TypedDict):
    hook_id: str
    source_id: str
    unit_instance_id: str
    max_distance_bonus_inches: int
    replay_payload: JsonValue
    decision_effect_payload: JsonValue


type MovementEndSurgeHandler = Callable[
    ["MovementEndSurgeContext"],
    tuple["MovementEndSurgeGrant", ...],
]


@dataclass(frozen=True, slots=True)
class MovementEndSurgeContext:
    state: GameState
    ruleset_descriptor: RulesetDescriptor
    triggering_unit_instance_id: str
    triggering_player_id: str
    reacting_player_id: str
    trigger_event_id: str
    movement_phase_action: str
    trigger_event_payload: JsonValue

    def __post_init__(self) -> None:
        from warhammer40k_core.engine.game_state import GameState

        if type(self.state) is not GameState:
            raise GameLifecycleError("MovementEndSurgeContext state must be a GameState.")
        if self.state.current_battle_phase is not BattlePhase.MOVEMENT:
            raise GameLifecycleError("MovementEndSurgeContext requires the Movement phase.")
        from warhammer40k_core.core.ruleset_descriptor import RulesetDescriptor

        if type(self.ruleset_descriptor) is not RulesetDescriptor:
            raise GameLifecycleError(
                "MovementEndSurgeContext ruleset_descriptor must be a RulesetDescriptor."
            )
        object.__setattr__(
            self,
            "triggering_unit_instance_id",
            _validate_identifier(
                "triggering_unit_instance_id",
                self.triggering_unit_instance_id,
            ),
        )
        object.__setattr__(
            self,
            "triggering_player_id",
            _validate_identifier("triggering_player_id", self.triggering_player_id),
        )
        object.__setattr__(
            self,
            "reacting_player_id",
            _validate_identifier("reacting_player_id", self.reacting_player_id),
        )
        if self.triggering_player_id == self.reacting_player_id:
            raise GameLifecycleError("MovementEndSurgeContext requires an opposing player.")
        object.__setattr__(
            self,
            "trigger_event_id",
            _validate_identifier("trigger_event_id", self.trigger_event_id),
        )
        object.__setattr__(
            self,
            "movement_phase_action",
            _validate_identifier("movement_phase_action", self.movement_phase_action),
        )
        object.__setattr__(
            self,
            "trigger_event_payload",
            validate_json_value(self.trigger_event_payload),
        )


@dataclass(frozen=True, slots=True)
class MovementEndSurgeGrant:
    hook_id: str
    source_id: str
    unit_instance_id: str
    max_distance_bonus_inches: int = 0
    replay_payload: JsonValue = None
    decision_effect_payload: JsonValue = None

    def __post_init__(self) -> None:
        object.__setattr__(self, "hook_id", _validate_identifier("hook_id", self.hook_id))
        object.__setattr__(self, "source_id", _validate_identifier("source_id", self.source_id))
        object.__setattr__(
            self,
            "unit_instance_id",
            _validate_identifier("unit_instance_id", self.unit_instance_id),
        )
        object.__setattr__(
            self,
            "max_distance_bonus_inches",
            _validate_non_negative_int(
                "max_distance_bonus_inches",
                self.max_distance_bonus_inches,
            ),
        )
        object.__setattr__(self, "replay_payload", validate_json_value(self.replay_payload))
        object.__setattr__(
            self,
            "decision_effect_payload",
            validate_json_value(self.decision_effect_payload),
        )

    def to_payload(self) -> MovementEndSurgeGrantPayload:
        return {
            "hook_id": self.hook_id,
            "source_id": self.source_id,
            "unit_instance_id": self.unit_instance_id,
            "max_distance_bonus_inches": self.max_distance_bonus_inches,
            "replay_payload": self.replay_payload,
            "decision_effect_payload": self.decision_effect_payload,
        }


@dataclass(frozen=True, slots=True)
class MovementEndSurgeHookBinding:
    hook_id: str
    source_id: str
    handler: MovementEndSurgeHandler

    def __post_init__(self) -> None:
        object.__setattr__(self, "hook_id", _validate_identifier("hook_id", self.hook_id))
        object.__setattr__(self, "source_id", _validate_identifier("source_id", self.source_id))
        if not callable(self.handler):
            raise GameLifecycleError("MovementEndSurgeHookBinding handler must be callable.")


@dataclass(frozen=True, slots=True)
class MovementEndSurgeHookRegistry:
    bindings: tuple[MovementEndSurgeHookBinding, ...]

    def __post_init__(self) -> None:
        object.__setattr__(self, "bindings", _validate_hook_bindings(self.bindings))

    @classmethod
    def empty(cls) -> Self:
        return cls(bindings=())

    @classmethod
    def from_bindings(cls, bindings: tuple[MovementEndSurgeHookBinding, ...]) -> Self:
        return cls(bindings=bindings)

    def all_bindings(self) -> tuple[MovementEndSurgeHookBinding, ...]:
        return self.bindings

    def grants_for(self, context: MovementEndSurgeContext) -> tuple[MovementEndSurgeGrant, ...]:
        if type(context) is not MovementEndSurgeContext:
            raise GameLifecycleError("Movement-end surge hooks require a context.")
        grants: list[MovementEndSurgeGrant] = []
        for binding in self.bindings:
            handler_grants = binding.handler(context)
            if type(handler_grants) is not tuple:
                raise GameLifecycleError("Movement-end surge handlers must return a tuple.")
            for grant in handler_grants:
                if type(grant) is not MovementEndSurgeGrant:
                    raise GameLifecycleError(
                        "Movement-end surge handlers must return MovementEndSurgeGrant values."
                    )
                if grant.hook_id != binding.hook_id:
                    raise GameLifecycleError("Movement-end surge handler returned hook_id drift.")
                if grant.source_id != binding.source_id:
                    raise GameLifecycleError("Movement-end surge handler returned source_id drift.")
                grants.append(grant)
        return tuple(sorted(grants, key=lambda grant: (grant.hook_id, grant.unit_instance_id)))


def _validate_hook_bindings(value: object) -> tuple[MovementEndSurgeHookBinding, ...]:
    if type(value) is not tuple:
        raise GameLifecycleError("MovementEndSurgeHookRegistry bindings must be a tuple.")
    bindings: list[MovementEndSurgeHookBinding] = []
    seen: set[str] = set()
    for binding in cast(tuple[object, ...], value):
        if type(binding) is not MovementEndSurgeHookBinding:
            raise GameLifecycleError(
                "MovementEndSurgeHookRegistry bindings must contain "
                "MovementEndSurgeHookBinding values."
            )
        if binding.hook_id in seen:
            raise GameLifecycleError("MovementEndSurgeHookRegistry hook IDs must be unique.")
        seen.add(binding.hook_id)
        bindings.append(binding)
    return tuple(sorted(bindings, key=lambda binding: binding.hook_id))


_validate_identifier = IdentifierValidator(GameLifecycleError)


def _validate_non_negative_int(field_name: str, value: object) -> int:
    if type(value) is not int:
        raise GameLifecycleError(f"Movement-end surge hook {field_name} must be an int.")
    if value < 0:
        raise GameLifecycleError(f"Movement-end surge hook {field_name} must not be negative.")
    return value
