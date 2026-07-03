from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from typing import TYPE_CHECKING, NotRequired, Self, TypedDict, cast

from warhammer40k_core.core.validation import IdentifierValidator
from warhammer40k_core.engine.decision_request import DecisionOption, DecisionRequest
from warhammer40k_core.engine.event_log import JsonValue, validate_json_value
from warhammer40k_core.engine.lifecycle_hooks import LifecycleHookEvent, validate_hook_bindings
from warhammer40k_core.engine.phase import BattlePhase, GameLifecycleError

if TYPE_CHECKING:
    from warhammer40k_core.engine.fight_order import FightActivationSelection
    from warhammer40k_core.engine.game_state import GameState


FIGHT_ACTIVATION_ABILITY_DECISION_TYPE = "select_fight_activation_ability"
DECLINE_FIGHT_ACTIVATION_ABILITY_OPTION_ID = "decline_fight_activation_ability"
USE_FIGHT_ACTIVATION_ABILITY_SUBMISSION_KIND = "use_fight_activation_ability"
DECLINE_FIGHT_ACTIVATION_ABILITY_SUBMISSION_KIND = "decline_fight_activation_ability"
FIGHT_ACTIVATION_MELEE_TARGETING_EFFECT_KIND = "fight_activation_melee_targeting_distance"
FIGHT_ACTIVATION_MOVEMENT_DISTANCE_EFFECT_KIND = "fight_activation_movement_distance"
FIGHT_ACTIVATION_ABILITY_EFFECT_KINDS = frozenset(
    {
        FIGHT_ACTIVATION_MELEE_TARGETING_EFFECT_KIND,
        FIGHT_ACTIVATION_MOVEMENT_DISTANCE_EFFECT_KIND,
    }
)


class FightActivationAbilityUsePayload(TypedDict):
    submission_kind: str
    hook_id: str
    source_id: str
    ability_id: str
    enhancement_id: str
    player_id: str
    battle_round: int
    phase: str
    unit_instance_id: str
    activation_request_id: str
    activation_result_id: str
    effect_kind: str
    replay_payload: JsonValue
    decision_effect_payload: JsonValue
    model_proximity_inches: NotRequired[float]
    pile_in_distance_inches: NotRequired[float]
    consolidate_distance_inches: NotRequired[float]


class FightActivationAbilityRequestPayload(TypedDict):
    game_id: str
    battle_round: int
    phase: str
    active_player_id: str
    player_id: str
    unit_instance_id: str
    activation_selection: JsonValue
    ability_options: list[FightActivationAbilityUsePayload]
    decline_option_id: str


type FightActivationAbilityHandler = Callable[
    ["FightActivationAbilityContext"],
    "FightActivationAbilityOption | None",
]


@dataclass(frozen=True, slots=True)
class FightActivationAbilityContext:
    state: GameState
    game_id: str
    battle_round: int
    active_player_id: str
    player_id: str
    unit_instance_id: str
    activation: FightActivationSelection
    target_unit_instance_ids: tuple[str, ...]

    def __post_init__(self) -> None:
        from warhammer40k_core.engine.fight_order import FightActivationSelection
        from warhammer40k_core.engine.game_state import GameState

        if type(self.state) is not GameState:
            raise GameLifecycleError("FightActivationAbilityContext state must be a GameState.")
        object.__setattr__(self, "game_id", _validate_identifier("game_id", self.game_id))
        object.__setattr__(
            self,
            "battle_round",
            _validate_positive_int("battle_round", self.battle_round),
        )
        object.__setattr__(
            self,
            "active_player_id",
            _validate_identifier("active_player_id", self.active_player_id),
        )
        object.__setattr__(
            self,
            "player_id",
            _validate_identifier("player_id", self.player_id),
        )
        object.__setattr__(
            self,
            "unit_instance_id",
            _validate_identifier("unit_instance_id", self.unit_instance_id),
        )
        if type(self.activation) is not FightActivationSelection:
            raise GameLifecycleError(
                "FightActivationAbilityContext activation must be a FightActivationSelection."
            )
        if self.activation.player_id != self.player_id:
            raise GameLifecycleError("Fight activation ability context player drift.")
        if self.activation.unit_instance_id != self.unit_instance_id:
            raise GameLifecycleError("Fight activation ability context unit drift.")
        if self.activation.battle_round != self.battle_round:
            raise GameLifecycleError("Fight activation ability context battle round drift.")
        object.__setattr__(
            self,
            "target_unit_instance_ids",
            _validate_identifier_tuple("target_unit_instance_ids", self.target_unit_instance_ids),
        )


@dataclass(frozen=True, slots=True)
class FightActivationAbilityOption:
    hook_id: str
    source_id: str
    ability_id: str
    enhancement_id: str
    effect_kind: str = FIGHT_ACTIVATION_MELEE_TARGETING_EFFECT_KIND
    model_proximity_inches: float | None = None
    pile_in_distance_inches: float | None = None
    consolidate_distance_inches: float | None = None
    replay_payload: JsonValue = None
    decision_effect_payload: JsonValue = None

    def __post_init__(self) -> None:
        object.__setattr__(self, "hook_id", _validate_identifier("hook_id", self.hook_id))
        object.__setattr__(self, "source_id", _validate_identifier("source_id", self.source_id))
        object.__setattr__(
            self,
            "ability_id",
            _validate_identifier("ability_id", self.ability_id),
        )
        object.__setattr__(
            self,
            "enhancement_id",
            _validate_identifier("enhancement_id", self.enhancement_id),
        )
        object.__setattr__(
            self,
            "effect_kind",
            _validate_fight_activation_effect_kind(self.effect_kind),
        )
        if self.effect_kind == FIGHT_ACTIVATION_MELEE_TARGETING_EFFECT_KIND:
            if (
                self.pile_in_distance_inches is not None
                or self.consolidate_distance_inches is not None
            ):
                raise GameLifecycleError(
                    "Fight activation melee targeting options must not define movement distances."
                )
            object.__setattr__(
                self,
                "model_proximity_inches",
                _validate_positive_float("model_proximity_inches", self.model_proximity_inches),
            )
        elif self.effect_kind == FIGHT_ACTIVATION_MOVEMENT_DISTANCE_EFFECT_KIND:
            if self.model_proximity_inches is not None:
                raise GameLifecycleError(
                    "Fight activation movement distance options must not define model proximity."
                )
            object.__setattr__(
                self,
                "pile_in_distance_inches",
                _validate_positive_float("pile_in_distance_inches", self.pile_in_distance_inches),
            )
            object.__setattr__(
                self,
                "consolidate_distance_inches",
                _validate_positive_float(
                    "consolidate_distance_inches",
                    self.consolidate_distance_inches,
                ),
            )
        object.__setattr__(self, "replay_payload", validate_json_value(self.replay_payload))
        object.__setattr__(
            self,
            "decision_effect_payload",
            validate_json_value(self.decision_effect_payload),
        )

    @property
    def option_id(self) -> str:
        return f"use:{self.ability_id}"

    def to_payload(
        self,
        context: FightActivationAbilityContext,
    ) -> FightActivationAbilityUsePayload:
        if type(context) is not FightActivationAbilityContext:
            raise GameLifecycleError("Fight activation ability option payload requires context.")
        payload: dict[str, JsonValue] = {
            "submission_kind": USE_FIGHT_ACTIVATION_ABILITY_SUBMISSION_KIND,
            "hook_id": self.hook_id,
            "source_id": self.source_id,
            "ability_id": self.ability_id,
            "enhancement_id": self.enhancement_id,
            "player_id": context.player_id,
            "battle_round": context.battle_round,
            "phase": BattlePhase.FIGHT.value,
            "unit_instance_id": context.unit_instance_id,
            "activation_request_id": context.activation.request_id,
            "activation_result_id": context.activation.result_id,
            "effect_kind": self.effect_kind,
            "replay_payload": self.replay_payload,
            "decision_effect_payload": self.decision_effect_payload,
        }
        if self.model_proximity_inches is not None:
            payload["model_proximity_inches"] = self.model_proximity_inches
        if self.pile_in_distance_inches is not None:
            payload["pile_in_distance_inches"] = self.pile_in_distance_inches
        if self.consolidate_distance_inches is not None:
            payload["consolidate_distance_inches"] = self.consolidate_distance_inches
        return cast(FightActivationAbilityUsePayload, validate_json_value(payload))

    def to_decision_option(self, context: FightActivationAbilityContext) -> DecisionOption:
        return DecisionOption(
            option_id=self.option_id,
            label=f"Use {self.ability_id}",
            payload=validate_json_value(cast(JsonValue, self.to_payload(context))),
        )


@dataclass(frozen=True, slots=True)
class FightActivationAbilityHookBinding:
    hook_id: str
    source_id: str
    handler: FightActivationAbilityHandler

    def __post_init__(self) -> None:
        object.__setattr__(self, "hook_id", _validate_identifier("hook_id", self.hook_id))
        object.__setattr__(self, "source_id", _validate_identifier("source_id", self.source_id))
        if not callable(self.handler):
            raise GameLifecycleError("FightActivationAbilityHookBinding handler must be callable.")


@dataclass(frozen=True, slots=True)
class FightActivationAbilityHookRegistry:
    bindings: tuple[FightActivationAbilityHookBinding, ...]

    def __post_init__(self) -> None:
        object.__setattr__(self, "bindings", _validate_hook_bindings(self.bindings))

    @classmethod
    def empty(cls) -> Self:
        return cls(bindings=())

    @classmethod
    def from_bindings(cls, bindings: tuple[FightActivationAbilityHookBinding, ...]) -> Self:
        return cls(bindings=bindings)

    def all_bindings(self) -> tuple[FightActivationAbilityHookBinding, ...]:
        return self.bindings

    def options_for(
        self,
        context: FightActivationAbilityContext,
    ) -> tuple[FightActivationAbilityOption, ...]:
        if type(context) is not FightActivationAbilityContext:
            raise GameLifecycleError("Fight activation ability hooks require a context.")
        options: list[FightActivationAbilityOption] = []
        for binding in self.bindings:
            option = binding.handler(context)
            if option is None:
                continue
            if type(option) is not FightActivationAbilityOption:
                raise GameLifecycleError(
                    "Fight activation ability handlers must return options or None."
                )
            if option.hook_id != binding.hook_id:
                raise GameLifecycleError("Fight activation ability handler returned hook_id drift.")
            if option.source_id != binding.source_id:
                raise GameLifecycleError(
                    "Fight activation ability handler returned source_id drift."
                )
            options.append(option)
        _validate_unique_option_ids(tuple(options))
        return tuple(sorted(options, key=lambda option: option.option_id))


@dataclass(frozen=True, slots=True)
class FightActivationAbilityUse:
    request_id: str
    result_id: str
    hook_id: str
    source_id: str
    ability_id: str
    enhancement_id: str
    player_id: str
    battle_round: int
    unit_instance_id: str
    activation_request_id: str
    activation_result_id: str
    effect_kind: str
    model_proximity_inches: float | None
    pile_in_distance_inches: float | None
    consolidate_distance_inches: float | None
    replay_payload: JsonValue
    decision_effect_payload: JsonValue

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "request_id",
            _validate_identifier("request_id", self.request_id),
        )
        object.__setattr__(self, "result_id", _validate_identifier("result_id", self.result_id))
        object.__setattr__(self, "hook_id", _validate_identifier("hook_id", self.hook_id))
        object.__setattr__(self, "source_id", _validate_identifier("source_id", self.source_id))
        object.__setattr__(
            self,
            "ability_id",
            _validate_identifier("ability_id", self.ability_id),
        )
        object.__setattr__(
            self,
            "enhancement_id",
            _validate_identifier("enhancement_id", self.enhancement_id),
        )
        object.__setattr__(
            self,
            "player_id",
            _validate_identifier("player_id", self.player_id),
        )
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
            "activation_request_id",
            _validate_identifier("activation_request_id", self.activation_request_id),
        )
        object.__setattr__(
            self,
            "activation_result_id",
            _validate_identifier("activation_result_id", self.activation_result_id),
        )
        object.__setattr__(
            self,
            "effect_kind",
            _validate_fight_activation_effect_kind(self.effect_kind),
        )
        if self.effect_kind == FIGHT_ACTIVATION_MELEE_TARGETING_EFFECT_KIND:
            if (
                self.pile_in_distance_inches is not None
                or self.consolidate_distance_inches is not None
            ):
                raise GameLifecycleError(
                    "Fight activation melee targeting use must not define movement distances."
                )
            object.__setattr__(
                self,
                "model_proximity_inches",
                _validate_positive_float("model_proximity_inches", self.model_proximity_inches),
            )
        elif self.effect_kind == FIGHT_ACTIVATION_MOVEMENT_DISTANCE_EFFECT_KIND:
            if self.model_proximity_inches is not None:
                raise GameLifecycleError(
                    "Fight activation movement distance use must not define model proximity."
                )
            object.__setattr__(
                self,
                "pile_in_distance_inches",
                _validate_positive_float("pile_in_distance_inches", self.pile_in_distance_inches),
            )
            object.__setattr__(
                self,
                "consolidate_distance_inches",
                _validate_positive_float(
                    "consolidate_distance_inches",
                    self.consolidate_distance_inches,
                ),
            )
        object.__setattr__(self, "replay_payload", validate_json_value(self.replay_payload))
        object.__setattr__(
            self,
            "decision_effect_payload",
            validate_json_value(self.decision_effect_payload),
        )

    @classmethod
    def from_result_payload(
        cls,
        *,
        payload: JsonValue,
        request_id: str,
        result_id: str,
    ) -> Self:
        raw = _json_object("Fight activation ability result payload", payload)
        effect_kind = _payload_string(raw, key="effect_kind")
        return cls(
            request_id=request_id,
            result_id=result_id,
            hook_id=_payload_string(raw, key="hook_id"),
            source_id=_payload_string(raw, key="source_id"),
            ability_id=_payload_string(raw, key="ability_id"),
            enhancement_id=_payload_string(raw, key="enhancement_id"),
            player_id=_payload_string(raw, key="player_id"),
            battle_round=_payload_positive_int(raw, key="battle_round"),
            unit_instance_id=_payload_string(raw, key="unit_instance_id"),
            activation_request_id=_payload_string(raw, key="activation_request_id"),
            activation_result_id=_payload_string(raw, key="activation_result_id"),
            effect_kind=effect_kind,
            model_proximity_inches=_payload_optional_positive_float(
                raw,
                key="model_proximity_inches",
            ),
            pile_in_distance_inches=_payload_optional_positive_float(
                raw,
                key="pile_in_distance_inches",
            ),
            consolidate_distance_inches=_payload_optional_positive_float(
                raw,
                key="consolidate_distance_inches",
            ),
            replay_payload=raw.get("replay_payload"),
            decision_effect_payload=raw.get("decision_effect_payload"),
        )

    def to_payload(self) -> FightActivationAbilityUsePayload:
        payload: dict[str, JsonValue] = {
            "submission_kind": USE_FIGHT_ACTIVATION_ABILITY_SUBMISSION_KIND,
            "hook_id": self.hook_id,
            "source_id": self.source_id,
            "ability_id": self.ability_id,
            "enhancement_id": self.enhancement_id,
            "player_id": self.player_id,
            "battle_round": self.battle_round,
            "phase": BattlePhase.FIGHT.value,
            "unit_instance_id": self.unit_instance_id,
            "activation_request_id": self.activation_request_id,
            "activation_result_id": self.activation_result_id,
            "effect_kind": self.effect_kind,
            "replay_payload": self.replay_payload,
            "decision_effect_payload": self.decision_effect_payload,
        }
        if self.model_proximity_inches is not None:
            payload["model_proximity_inches"] = self.model_proximity_inches
        if self.pile_in_distance_inches is not None:
            payload["pile_in_distance_inches"] = self.pile_in_distance_inches
        if self.consolidate_distance_inches is not None:
            payload["consolidate_distance_inches"] = self.consolidate_distance_inches
        return cast(FightActivationAbilityUsePayload, validate_json_value(payload))


def build_fight_activation_ability_request(
    *,
    request_id: str,
    game_id: str,
    context: FightActivationAbilityContext,
    ability_options: tuple[FightActivationAbilityOption, ...],
) -> DecisionRequest:
    if not ability_options:
        raise GameLifecycleError("Fight activation ability request requires options.")
    options = tuple(option.to_decision_option(context) for option in ability_options)
    decline_payload = _decline_payload(context=context, options=ability_options)
    return DecisionRequest(
        request_id=request_id,
        decision_type=FIGHT_ACTIVATION_ABILITY_DECISION_TYPE,
        actor_id=context.player_id,
        payload=validate_json_value(
            {
                "game_id": game_id,
                "battle_round": context.battle_round,
                "phase": BattlePhase.FIGHT.value,
                "active_player_id": context.active_player_id,
                "player_id": context.player_id,
                "unit_instance_id": context.unit_instance_id,
                "activation_selection": context.activation.to_payload(),
                "ability_options": [option.to_payload(context) for option in ability_options],
                "decline_option_id": DECLINE_FIGHT_ACTIVATION_ABILITY_OPTION_ID,
            }
        ),
        options=(
            *options,
            DecisionOption(
                option_id=DECLINE_FIGHT_ACTIVATION_ABILITY_OPTION_ID,
                label="Decline Fight Activation Ability",
                payload=decline_payload,
            ),
        ),
    )


def fight_activation_ability_use_from_result(
    *,
    payload: JsonValue,
    request_id: str,
    result_id: str,
) -> FightActivationAbilityUse:
    return FightActivationAbilityUse.from_result_payload(
        payload=payload,
        request_id=request_id,
        result_id=result_id,
    )


def is_fight_activation_ability_decline_payload(payload: JsonValue) -> bool:
    if not isinstance(payload, dict):
        return False
    return payload.get("submission_kind") == DECLINE_FIGHT_ACTIVATION_ABILITY_SUBMISSION_KIND


def ability_request_activation_payload(request: DecisionRequest) -> dict[str, JsonValue]:
    if request.decision_type != FIGHT_ACTIVATION_ABILITY_DECISION_TYPE:
        raise GameLifecycleError("Fight activation ability request has wrong decision_type.")
    payload = _json_object("Fight activation ability request payload", request.payload)
    return _json_object(
        "Fight activation ability activation_selection",
        payload.get("activation_selection"),
    )


def ability_request_available_option_payloads(
    request: DecisionRequest,
) -> tuple[dict[str, JsonValue], ...]:
    if request.decision_type != FIGHT_ACTIVATION_ABILITY_DECISION_TYPE:
        raise GameLifecycleError("Fight activation ability request has wrong decision_type.")
    payload = _json_object("Fight activation ability request payload", request.payload)
    raw_options = payload.get("ability_options")
    if type(raw_options) is not list:
        raise GameLifecycleError("Fight activation ability request options must be a list.")
    return tuple(
        _json_object("Fight activation ability option payload", option) for option in raw_options
    )


def _decline_payload(
    *,
    context: FightActivationAbilityContext,
    options: tuple[FightActivationAbilityOption, ...],
) -> JsonValue:
    return validate_json_value(
        {
            "submission_kind": DECLINE_FIGHT_ACTIVATION_ABILITY_SUBMISSION_KIND,
            "player_id": context.player_id,
            "battle_round": context.battle_round,
            "phase": BattlePhase.FIGHT.value,
            "unit_instance_id": context.unit_instance_id,
            "activation_request_id": context.activation.request_id,
            "activation_result_id": context.activation.result_id,
            "available_ability_ids": [option.ability_id for option in options],
        }
    )


def _validate_hook_bindings(value: object) -> tuple[FightActivationAbilityHookBinding, ...]:
    return validate_hook_bindings(
        value,
        lifecycle_event=LifecycleHookEvent.FIGHT_ACTIVATION_ABILITY,
        binding_type=FightActivationAbilityHookBinding,
        registry_name="FightActivationAbilityHookRegistry",
        invalid_binding_message=(
            "FightActivationAbilityHookRegistry bindings must contain "
            "FightActivationAbilityHookBinding values."
        ),
    )


def _validate_unique_option_ids(options: tuple[FightActivationAbilityOption, ...]) -> None:
    seen: set[str] = set()
    for option in options:
        if option.option_id in seen:
            raise GameLifecycleError("Fight activation ability option IDs must be unique.")
        seen.add(option.option_id)


def _json_object(field_name: str, value: object) -> dict[str, JsonValue]:
    if not isinstance(value, dict):
        raise GameLifecycleError(f"{field_name} must be an object.")
    return cast(dict[str, JsonValue], value)


def _payload_string(payload: dict[str, JsonValue], *, key: str) -> str:
    value = payload.get(key)
    return _validate_identifier(key, value)


def _payload_positive_int(payload: dict[str, JsonValue], *, key: str) -> int:
    value = payload.get(key)
    return _validate_positive_int(key, value)


def _payload_optional_positive_float(payload: dict[str, JsonValue], *, key: str) -> float | None:
    value = payload.get(key)
    if value is None:
        return None
    return _validate_positive_float(key, value)


def _validate_fight_activation_effect_kind(value: object) -> str:
    effect_kind = _validate_identifier("effect_kind", value)
    if effect_kind not in FIGHT_ACTIVATION_ABILITY_EFFECT_KINDS:
        raise GameLifecycleError("Fight activation ability effect kind is unsupported.")
    return effect_kind


def _validate_identifier_tuple(field_name: str, value: object) -> tuple[str, ...]:
    if type(value) is not tuple:
        raise GameLifecycleError(f"Fight activation ability {field_name} must be a tuple.")
    identifiers: list[str] = []
    seen: set[str] = set()
    for item in cast(tuple[object, ...], value):
        identifier = _validate_identifier(f"{field_name} value", item)
        if identifier in seen:
            raise GameLifecycleError(
                f"Fight activation ability {field_name} must not contain duplicates."
            )
        seen.add(identifier)
        identifiers.append(identifier)
    return tuple(identifiers)


_validate_identifier = IdentifierValidator(GameLifecycleError)


def _validate_positive_int(field_name: str, value: object) -> int:
    if type(value) is not int:
        raise GameLifecycleError(f"Fight activation ability {field_name} must be an int.")
    if value <= 0:
        raise GameLifecycleError(
            f"Fight activation ability {field_name} must be greater than zero."
        )
    return value


def _validate_positive_float(field_name: str, value: object) -> float:
    if type(value) is int:
        converted = float(value)
    elif type(value) is float:
        converted = value
    else:
        raise GameLifecycleError(f"Fight activation ability {field_name} must be a number.")
    if converted <= 0.0:
        raise GameLifecycleError(
            f"Fight activation ability {field_name} must be greater than zero."
        )
    return converted
