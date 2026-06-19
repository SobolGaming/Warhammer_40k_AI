from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from typing import TYPE_CHECKING, Self, TypedDict, cast

from warhammer40k_core.engine.effects import PersistingEffectPayload
from warhammer40k_core.engine.event_log import JsonValue, validate_json_value
from warhammer40k_core.engine.phase import BattlePhase, GameLifecycleError

if TYPE_CHECKING:
    from warhammer40k_core.engine.game_state import GameState


class FightUnitSelectedGrantPayload(TypedDict):
    hook_id: str
    source_id: str
    label: str
    replay_payload: JsonValue
    decision_effect_payload: JsonValue
    unit_effect_payload: JsonValue
    unit_effect_expiration: str | None


class FightUnitSelectedPersistingEffectPayload(TypedDict):
    hook_id: str
    source_id: str
    persisting_effect: PersistingEffectPayload


SELECT_FIGHT_UNIT_GRANT_DECISION_TYPE = "select_fight_unit_grant"
DECLINE_FIGHT_UNIT_GRANT_OPTION_ID = "decline_fight_unit_grant"


type FightUnitSelectedGrantHandler = Callable[
    ["FightUnitSelectedContext"],
    "FightUnitSelectedGrant | None",
]


@dataclass(frozen=True, slots=True)
class FightUnitSelectedContext:
    state: GameState
    player_id: str
    battle_round: int
    unit_instance_id: str
    fight_type: str
    ordering_band: str
    request_id: str
    result_id: str

    def __post_init__(self) -> None:
        from warhammer40k_core.engine.game_state import GameState

        if type(self.state) is not GameState:
            raise GameLifecycleError("FightUnitSelectedContext state must be a GameState.")
        if self.state.current_battle_phase is not BattlePhase.FIGHT:
            raise GameLifecycleError("FightUnitSelectedContext requires the Fight phase.")
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
        object.__setattr__(
            self,
            "fight_type",
            _validate_identifier("fight_type", self.fight_type),
        )
        object.__setattr__(
            self,
            "ordering_band",
            _validate_identifier("ordering_band", self.ordering_band),
        )
        object.__setattr__(
            self,
            "request_id",
            _validate_identifier("request_id", self.request_id),
        )
        object.__setattr__(
            self,
            "result_id",
            _validate_identifier("result_id", self.result_id),
        )


@dataclass(frozen=True, slots=True)
class FightUnitSelectedGrant:
    hook_id: str
    source_id: str
    label: str
    replay_payload: JsonValue = None
    decision_effect_payload: JsonValue = None
    unit_effect_payload: JsonValue = None
    unit_effect_expiration: str | None = None

    def __post_init__(self) -> None:
        object.__setattr__(self, "hook_id", _validate_identifier("hook_id", self.hook_id))
        object.__setattr__(self, "source_id", _validate_identifier("source_id", self.source_id))
        object.__setattr__(self, "label", _validate_identifier("label", self.label))
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
            raise GameLifecycleError("Fight-unit-selected grant expiration requires an effect.")
        if self.unit_effect_payload is not None and self.unit_effect_expiration is None:
            raise GameLifecycleError("Fight-unit-selected grant effect requires expiration.")

    def to_payload(self) -> FightUnitSelectedGrantPayload:
        return {
            "hook_id": self.hook_id,
            "source_id": self.source_id,
            "label": self.label,
            "replay_payload": self.replay_payload,
            "decision_effect_payload": self.decision_effect_payload,
            "unit_effect_payload": self.unit_effect_payload,
            "unit_effect_expiration": self.unit_effect_expiration,
        }

    @classmethod
    def from_payload(cls, payload: FightUnitSelectedGrantPayload) -> Self:
        return cls(
            hook_id=payload["hook_id"],
            source_id=payload["source_id"],
            label=payload["label"],
            replay_payload=payload["replay_payload"],
            decision_effect_payload=payload["decision_effect_payload"],
            unit_effect_payload=payload["unit_effect_payload"],
            unit_effect_expiration=payload["unit_effect_expiration"],
        )


@dataclass(frozen=True, slots=True)
class FightUnitSelectedGrantBinding:
    hook_id: str
    source_id: str
    handler: FightUnitSelectedGrantHandler

    def __post_init__(self) -> None:
        object.__setattr__(self, "hook_id", _validate_identifier("hook_id", self.hook_id))
        object.__setattr__(self, "source_id", _validate_identifier("source_id", self.source_id))
        if not callable(self.handler):
            raise GameLifecycleError("FightUnitSelectedGrantBinding handler must be callable.")


@dataclass(frozen=True, slots=True)
class FightUnitSelectedGrantRegistry:
    bindings: tuple[FightUnitSelectedGrantBinding, ...]

    def __post_init__(self) -> None:
        object.__setattr__(self, "bindings", _validate_grant_bindings(self.bindings))

    @classmethod
    def empty(cls) -> Self:
        return cls(bindings=())

    @classmethod
    def from_bindings(cls, bindings: tuple[FightUnitSelectedGrantBinding, ...]) -> Self:
        return cls(bindings=bindings)

    def all_bindings(self) -> tuple[FightUnitSelectedGrantBinding, ...]:
        return self.bindings

    def grants_for(
        self,
        context: FightUnitSelectedContext,
    ) -> tuple[FightUnitSelectedGrant, ...]:
        if type(context) is not FightUnitSelectedContext:
            raise GameLifecycleError("Fight-unit-selected grant hooks require a context.")
        grants: list[FightUnitSelectedGrant] = []
        for binding in self.bindings:
            grant = binding.handler(context)
            if grant is None:
                continue
            if type(grant) is not FightUnitSelectedGrant:
                raise GameLifecycleError(
                    "Fight-unit-selected grant handlers must return grants or None."
                )
            if grant.hook_id != binding.hook_id:
                raise GameLifecycleError(
                    "Fight-unit-selected grant handler returned hook_id drift."
                )
            if grant.source_id != binding.source_id:
                raise GameLifecycleError(
                    "Fight-unit-selected grant handler returned source_id drift."
                )
            grants.append(grant)
        return tuple(sorted(grants, key=lambda grant: grant.hook_id))


def _validate_grant_bindings(
    value: object,
) -> tuple[FightUnitSelectedGrantBinding, ...]:
    if type(value) is not tuple:
        raise GameLifecycleError("FightUnitSelectedGrantRegistry bindings must be a tuple.")
    bindings: list[FightUnitSelectedGrantBinding] = []
    seen: set[str] = set()
    for binding in cast(tuple[object, ...], value):
        if type(binding) is not FightUnitSelectedGrantBinding:
            raise GameLifecycleError(
                "FightUnitSelectedGrantRegistry bindings must contain "
                "FightUnitSelectedGrantBinding values."
            )
        if binding.hook_id in seen:
            raise GameLifecycleError("FightUnitSelectedGrantRegistry hook IDs must be unique.")
        seen.add(binding.hook_id)
        bindings.append(binding)
    return tuple(sorted(bindings, key=lambda binding: binding.hook_id))


def _validate_optional_expiration(field_name: str, value: object) -> str | None:
    if value is None:
        return None
    expiration = _validate_identifier(field_name, value)
    if expiration not in {"end_phase", "end_turn"}:
        raise GameLifecycleError(
            f"Fight-unit-selected hook {field_name} must be end_phase or end_turn."
        )
    return expiration


def _validate_identifier(field_name: str, value: object) -> str:
    if type(value) is not str:
        raise GameLifecycleError(f"Fight-unit-selected hook {field_name} must be a string.")
    stripped = value.strip()
    if not stripped:
        raise GameLifecycleError(f"Fight-unit-selected hook {field_name} must not be empty.")
    return stripped


def _validate_positive_int(field_name: str, value: object) -> int:
    if type(value) is not int:
        raise GameLifecycleError(f"Fight-unit-selected hook {field_name} must be an int.")
    if value < 1:
        raise GameLifecycleError(f"Fight-unit-selected hook {field_name} must be positive.")
    return value
