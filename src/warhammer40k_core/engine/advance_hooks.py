from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from typing import TYPE_CHECKING, NotRequired, Self, TypedDict, cast

from warhammer40k_core.core.validation import IdentifierValidator
from warhammer40k_core.engine.event_log import JsonValue, validate_json_value
from warhammer40k_core.engine.lifecycle_hooks import LifecycleHookEvent, validate_hook_bindings
from warhammer40k_core.engine.phase import BattlePhase, GameLifecycleError

if TYPE_CHECKING:
    from warhammer40k_core.engine.game_state import GameState


class AdvanceMoveGrantPayload(TypedDict):
    hook_id: str
    source_id: str
    label: str
    granted_ranged_weapon_keywords: list[str]
    movement_bonus_inches: int
    fixed_advance_inches: NotRequired[int | None]
    ignores_vertical_distance: NotRequired[bool]
    automatic: NotRequired[bool]
    replay_payload: JsonValue
    decision_effect_payload: JsonValue
    unit_effect_payload: JsonValue
    unit_effect_expiration: str | None


SELECT_MOVEMENT_ACTION_GRANT_DECISION_TYPE = "select_movement_action_grant"
DECLINE_MOVEMENT_ACTION_GRANT_OPTION_ID = "decline_movement_action_grant"
SELECT_ADVANCE_MOVE_GRANT_DECISION_TYPE = SELECT_MOVEMENT_ACTION_GRANT_DECISION_TYPE
DECLINE_ADVANCE_MOVE_GRANT_OPTION_ID = DECLINE_MOVEMENT_ACTION_GRANT_OPTION_ID


type AdvanceMoveHandler = Callable[
    ["AdvanceMoveContext"],
    "AdvanceMoveGrant | None",
]


@dataclass(frozen=True, slots=True)
class AdvanceMoveContext:
    state: GameState
    player_id: str
    battle_round: int
    unit_instance_id: str
    movement_phase_action: str
    movement_request_id: str
    movement_result_id: str

    def __post_init__(self) -> None:
        from warhammer40k_core.engine.game_state import GameState

        if type(self.state) is not GameState:
            raise GameLifecycleError("AdvanceMoveContext state must be a GameState.")
        if self.state.current_battle_phase is not BattlePhase.MOVEMENT:
            raise GameLifecycleError("AdvanceMoveContext requires the Movement phase.")
        object.__setattr__(self, "player_id", _validate_identifier("player_id", self.player_id))
        object.__setattr__(
            self,
            "battle_round",
            _validate_positive_int("battle_round", self.battle_round),
        )
        object.__setattr__(
            self,
            "unit_instance_id",
            _validate_identifier("unit_instance_id", self.unit_instance_id),
        )
        action = _validate_identifier("movement_phase_action", self.movement_phase_action)
        if action not in {"normal_move", "advance", "fall_back"}:
            raise GameLifecycleError("AdvanceMoveContext movement action is unsupported.")
        object.__setattr__(self, "movement_phase_action", action)
        object.__setattr__(
            self,
            "movement_request_id",
            _validate_identifier("movement_request_id", self.movement_request_id),
        )
        object.__setattr__(
            self,
            "movement_result_id",
            _validate_identifier("movement_result_id", self.movement_result_id),
        )


@dataclass(frozen=True, slots=True)
class AdvanceMoveGrant:
    hook_id: str
    source_id: str
    label: str
    granted_ranged_weapon_keywords: tuple[str, ...]
    movement_bonus_inches: int = 0
    fixed_advance_inches: int | None = None
    ignores_vertical_distance: bool = False
    automatic: bool = False
    replay_payload: JsonValue = None
    decision_effect_payload: JsonValue = None
    unit_effect_payload: JsonValue = None
    unit_effect_expiration: str | None = None

    def __post_init__(self) -> None:
        object.__setattr__(self, "hook_id", _validate_identifier("hook_id", self.hook_id))
        object.__setattr__(self, "source_id", _validate_identifier("source_id", self.source_id))
        object.__setattr__(self, "label", _validate_identifier("label", self.label))
        object.__setattr__(
            self,
            "granted_ranged_weapon_keywords",
            _validate_identifier_tuple(
                "granted_ranged_weapon_keywords",
                self.granted_ranged_weapon_keywords,
            ),
        )
        object.__setattr__(
            self,
            "movement_bonus_inches",
            _validate_non_negative_int("movement_bonus_inches", self.movement_bonus_inches),
        )
        if self.fixed_advance_inches is not None:
            object.__setattr__(
                self,
                "fixed_advance_inches",
                _validate_positive_int("fixed_advance_inches", self.fixed_advance_inches),
            )
        object.__setattr__(
            self,
            "ignores_vertical_distance",
            _validate_bool("ignores_vertical_distance", self.ignores_vertical_distance),
        )
        object.__setattr__(self, "automatic", _validate_bool("automatic", self.automatic))
        object.__setattr__(self, "replay_payload", validate_json_value(self.replay_payload))
        object.__setattr__(
            self,
            "decision_effect_payload",
            validate_json_value(self.decision_effect_payload),
        )
        object.__setattr__(
            self,
            "unit_effect_payload",
            validate_json_value(self.unit_effect_payload),
        )
        object.__setattr__(
            self,
            "unit_effect_expiration",
            _validate_optional_expiration("unit_effect_expiration", self.unit_effect_expiration),
        )
        if self.unit_effect_payload is None and self.unit_effect_expiration is not None:
            raise GameLifecycleError("Advance grant expiration requires a unit effect payload.")
        if self.unit_effect_payload is not None and self.unit_effect_expiration is None:
            raise GameLifecycleError("Advance grant unit effect requires an expiration.")

    def to_payload(self) -> AdvanceMoveGrantPayload:
        return {
            "hook_id": self.hook_id,
            "source_id": self.source_id,
            "label": self.label,
            "granted_ranged_weapon_keywords": list(self.granted_ranged_weapon_keywords),
            "movement_bonus_inches": self.movement_bonus_inches,
            "fixed_advance_inches": self.fixed_advance_inches,
            "ignores_vertical_distance": self.ignores_vertical_distance,
            "automatic": self.automatic,
            "replay_payload": self.replay_payload,
            "decision_effect_payload": self.decision_effect_payload,
            "unit_effect_payload": self.unit_effect_payload,
            "unit_effect_expiration": self.unit_effect_expiration,
        }

    @classmethod
    def from_payload(cls, payload: AdvanceMoveGrantPayload) -> Self:
        return cls(
            hook_id=payload["hook_id"],
            source_id=payload["source_id"],
            label=payload["label"],
            granted_ranged_weapon_keywords=tuple(payload["granted_ranged_weapon_keywords"]),
            movement_bonus_inches=payload["movement_bonus_inches"],
            fixed_advance_inches=payload.get("fixed_advance_inches"),
            ignores_vertical_distance=payload.get("ignores_vertical_distance", False),
            automatic=payload.get("automatic", False),
            replay_payload=payload["replay_payload"],
            decision_effect_payload=payload["decision_effect_payload"],
            unit_effect_payload=payload["unit_effect_payload"],
            unit_effect_expiration=payload["unit_effect_expiration"],
        )


@dataclass(frozen=True, slots=True)
class AdvanceMoveHookBinding:
    hook_id: str
    source_id: str
    handler: AdvanceMoveHandler

    def __post_init__(self) -> None:
        object.__setattr__(self, "hook_id", _validate_identifier("hook_id", self.hook_id))
        object.__setattr__(self, "source_id", _validate_identifier("source_id", self.source_id))
        if not callable(self.handler):
            raise GameLifecycleError("AdvanceMoveHookBinding handler must be callable.")


@dataclass(frozen=True, slots=True)
class AdvanceMoveHookRegistry:
    bindings: tuple[AdvanceMoveHookBinding, ...]

    def __post_init__(self) -> None:
        object.__setattr__(self, "bindings", _validate_hook_bindings(self.bindings))

    @classmethod
    def empty(cls) -> Self:
        return cls(bindings=())

    @classmethod
    def from_bindings(cls, bindings: tuple[AdvanceMoveHookBinding, ...]) -> Self:
        return cls(bindings=bindings)

    def all_bindings(self) -> tuple[AdvanceMoveHookBinding, ...]:
        return self.bindings

    def grants_for(self, context: AdvanceMoveContext) -> tuple[AdvanceMoveGrant, ...]:
        if type(context) is not AdvanceMoveContext:
            raise GameLifecycleError("Advance hooks require a context.")
        grants: list[AdvanceMoveGrant] = []
        for binding in self.bindings:
            grant = binding.handler(context)
            if grant is None:
                continue
            if type(grant) is not AdvanceMoveGrant:
                raise GameLifecycleError("Advance handlers must return grants or None.")
            if grant.hook_id != binding.hook_id:
                raise GameLifecycleError("Advance handler returned hook_id drift.")
            if grant.source_id != binding.source_id:
                raise GameLifecycleError("Advance handler returned source_id drift.")
            grants.append(grant)
        return tuple(sorted(grants, key=lambda grant: grant.hook_id))


def _validate_hook_bindings(value: object) -> tuple[AdvanceMoveHookBinding, ...]:
    return validate_hook_bindings(
        value,
        lifecycle_event=LifecycleHookEvent.ADVANCE_MOVE,
        binding_type=AdvanceMoveHookBinding,
        registry_name="AdvanceMoveHookRegistry",
        invalid_binding_message=(
            "AdvanceMoveHookRegistry bindings must contain AdvanceMoveHookBinding values."
        ),
    )


def _validate_identifier_tuple(field_name: str, values: object) -> tuple[str, ...]:
    if type(values) is not tuple:
        raise GameLifecycleError(f"Advance hook {field_name} must be a tuple.")
    validated: list[str] = []
    seen: set[str] = set()
    for raw_value in cast(tuple[object, ...], values):
        value = _validate_identifier(field_name, raw_value)
        if value in seen:
            raise GameLifecycleError(f"Advance hook {field_name} must be unique.")
        seen.add(value)
        validated.append(value)
    return tuple(sorted(validated))


def _validate_positive_int(field_name: str, value: object) -> int:
    if type(value) is not int:
        raise GameLifecycleError(f"Advance hook {field_name} must be an int.")
    if value <= 0:
        raise GameLifecycleError(f"Advance hook {field_name} must be greater than zero.")
    return value


def _validate_non_negative_int(field_name: str, value: object) -> int:
    if type(value) is not int:
        raise GameLifecycleError(f"Advance hook {field_name} must be an int.")
    if value < 0:
        raise GameLifecycleError(f"Advance hook {field_name} must not be negative.")
    return value


def _validate_bool(field_name: str, value: object) -> bool:
    if type(value) is not bool:
        raise GameLifecycleError(f"Advance hook {field_name} must be a bool.")
    return value


def _validate_optional_expiration(field_name: str, value: object) -> str | None:
    if value is None:
        return None
    expiration = _validate_identifier(field_name, value)
    if expiration not in {"end_phase", "end_turn"}:
        raise GameLifecycleError(f"Advance hook {field_name} is unsupported.")
    return expiration


_validate_identifier = IdentifierValidator(GameLifecycleError)
