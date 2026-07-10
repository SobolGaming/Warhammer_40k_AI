from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from typing import TYPE_CHECKING, NotRequired, Self, TypedDict

from warhammer40k_core.core.validation import IdentifierValidator
from warhammer40k_core.engine.decision_request import DecisionOption
from warhammer40k_core.engine.effects import PersistingEffect, PersistingEffectPayload
from warhammer40k_core.engine.event_log import JsonValue, validate_json_value
from warhammer40k_core.engine.lifecycle_hooks import LifecycleHookEvent, validate_hook_bindings
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
    decline_allowed: NotRequired[bool]


class FightUnitSelectedPersistingEffectPayload(TypedDict):
    hook_id: str
    source_id: str
    unit_instance_id: str
    event_type: str
    persisting_effect: PersistingEffectPayload
    replay_payload: JsonValue


SELECT_FIGHT_UNIT_GRANT_DECISION_TYPE = "select_fight_unit_grant"
DECLINE_FIGHT_UNIT_GRANT_OPTION_ID = "decline_fight_unit_grant"


type FightUnitSelectedGrantHandler = Callable[
    ["FightUnitSelectedContext"],
    "FightUnitSelectedGrant | None",
]
type FightUnitSelectedHandler = Callable[
    ["FightUnitSelectedContext"],
    tuple["FightUnitSelectedEffectGrant", ...],
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
    decline_allowed: bool = True

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
        if type(self.decline_allowed) is not bool:
            raise GameLifecycleError("Fight-unit-selected decline_allowed must be bool.")

    def to_payload(self) -> FightUnitSelectedGrantPayload:
        payload: FightUnitSelectedGrantPayload = {
            "hook_id": self.hook_id,
            "source_id": self.source_id,
            "label": self.label,
            "replay_payload": self.replay_payload,
            "decision_effect_payload": self.decision_effect_payload,
            "unit_effect_payload": self.unit_effect_payload,
            "unit_effect_expiration": self.unit_effect_expiration,
        }
        if not self.decline_allowed:
            payload["decline_allowed"] = False
        return payload

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
            decline_allowed=payload.get("decline_allowed", True),
        )


def fight_unit_selected_grant_options(
    *,
    unit_instance_id: str,
    activation_request_id: str,
    activation_result_id: str,
    grants: tuple[FightUnitSelectedGrant, ...],
) -> tuple[DecisionOption, ...]:
    unit_id = _validate_identifier("unit_instance_id", unit_instance_id)
    request_id = _validate_identifier("activation_request_id", activation_request_id)
    result_id = _validate_identifier("activation_result_id", activation_result_id)
    mandatory_grants = tuple(grant for grant in grants if not grant.decline_allowed)
    optional_grants = tuple(grant for grant in grants if grant.decline_allowed)
    options: list[DecisionOption] = []
    if not mandatory_grants:
        options.append(
            DecisionOption(
                option_id=DECLINE_FIGHT_UNIT_GRANT_OPTION_ID,
                label="Decline fight unit grant",
                payload=_grant_option_payload(
                    unit_instance_id=unit_id,
                    activation_request_id=request_id,
                    activation_result_id=result_id,
                    grants=(),
                ),
            )
        )
    for grant in mandatory_grants or optional_grants:
        options.append(
            _grant_decision_option(
                option_id=grant.hook_id,
                label=grant.label,
                unit_instance_id=unit_id,
                activation_request_id=request_id,
                activation_result_id=result_id,
                grants=(grant,),
            )
        )
        if mandatory_grants:
            options.extend(
                _grant_decision_option(
                    option_id=f"{grant.hook_id}:with:{optional.hook_id}",
                    label=f"{grant.label} and {optional.label}",
                    unit_instance_id=unit_id,
                    activation_request_id=request_id,
                    activation_result_id=result_id,
                    grants=(grant, optional),
                )
                for optional in optional_grants
            )
    return tuple(options)


def _grant_decision_option(
    *,
    option_id: str,
    label: str,
    unit_instance_id: str,
    activation_request_id: str,
    activation_result_id: str,
    grants: tuple[FightUnitSelectedGrant, ...],
) -> DecisionOption:
    return DecisionOption(
        option_id=option_id,
        label=label,
        payload=_grant_option_payload(
            unit_instance_id=unit_instance_id,
            activation_request_id=activation_request_id,
            activation_result_id=activation_result_id,
            grants=grants,
        ),
    )


def _grant_option_payload(
    *,
    unit_instance_id: str,
    activation_request_id: str,
    activation_result_id: str,
    grants: tuple[FightUnitSelectedGrant, ...],
) -> JsonValue:
    return validate_json_value(
        {
            "submission_kind": SELECT_FIGHT_UNIT_GRANT_DECISION_TYPE,
            "unit_instance_id": unit_instance_id,
            "activation_request_id": activation_request_id,
            "activation_result_id": activation_result_id,
            "selected_fight_unit_grants": [grant.to_payload() for grant in grants],
        }
    )


@dataclass(frozen=True, slots=True)
class FightUnitSelectedEffectGrant:
    hook_id: str
    source_id: str
    unit_instance_id: str
    persisting_effect: PersistingEffect
    event_type: str = "fight_unit_selected_effect_granted"
    replay_payload: JsonValue = None

    def __post_init__(self) -> None:
        object.__setattr__(self, "hook_id", _validate_identifier("hook_id", self.hook_id))
        object.__setattr__(self, "source_id", _validate_identifier("source_id", self.source_id))
        object.__setattr__(
            self,
            "unit_instance_id",
            _validate_identifier("unit_instance_id", self.unit_instance_id),
        )
        if type(self.persisting_effect) is not PersistingEffect:
            raise GameLifecycleError(
                "FightUnitSelectedEffectGrant persisting_effect must be a PersistingEffect."
            )
        if self.persisting_effect.source_rule_id != self.source_id:
            raise GameLifecycleError(
                "FightUnitSelectedEffectGrant source_id must match persisting_effect."
            )
        object.__setattr__(
            self,
            "event_type",
            _validate_identifier("event_type", self.event_type),
        )
        object.__setattr__(self, "replay_payload", validate_json_value(self.replay_payload))

    def to_payload(self) -> FightUnitSelectedPersistingEffectPayload:
        return {
            "hook_id": self.hook_id,
            "source_id": self.source_id,
            "unit_instance_id": self.unit_instance_id,
            "event_type": self.event_type,
            "persisting_effect": self.persisting_effect.to_payload(),
            "replay_payload": self.replay_payload,
        }


@dataclass(frozen=True, slots=True)
class FightUnitSelectedHookBinding:
    hook_id: str
    source_id: str
    handler: FightUnitSelectedHandler

    def __post_init__(self) -> None:
        object.__setattr__(self, "hook_id", _validate_identifier("hook_id", self.hook_id))
        object.__setattr__(self, "source_id", _validate_identifier("source_id", self.source_id))
        if not callable(self.handler):
            raise GameLifecycleError("FightUnitSelectedHookBinding handler must be callable.")


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
class FightUnitSelectedHookRegistry:
    bindings: tuple[FightUnitSelectedHookBinding, ...]

    def __post_init__(self) -> None:
        object.__setattr__(self, "bindings", _validate_hook_bindings(self.bindings))

    @classmethod
    def empty(cls) -> Self:
        return cls(bindings=())

    @classmethod
    def from_bindings(cls, bindings: tuple[FightUnitSelectedHookBinding, ...]) -> Self:
        return cls(bindings=bindings)

    def all_bindings(self) -> tuple[FightUnitSelectedHookBinding, ...]:
        return self.bindings

    def grants_for(
        self,
        context: FightUnitSelectedContext,
    ) -> tuple[FightUnitSelectedEffectGrant, ...]:
        if type(context) is not FightUnitSelectedContext:
            raise GameLifecycleError("Fight-unit-selected hooks require a context.")
        grants: list[FightUnitSelectedEffectGrant] = []
        for binding in self.bindings:
            handler_grants = binding.handler(context)
            if type(handler_grants) is not tuple:
                raise GameLifecycleError("Fight-unit-selected handlers must return a tuple.")
            for grant in handler_grants:
                if type(grant) is not FightUnitSelectedEffectGrant:
                    raise GameLifecycleError(
                        "Fight-unit-selected handlers must return "
                        "FightUnitSelectedEffectGrant values."
                    )
                if grant.hook_id != binding.hook_id:
                    raise GameLifecycleError("Fight-unit-selected handler returned hook_id drift.")
                if grant.source_id != binding.source_id:
                    raise GameLifecycleError(
                        "Fight-unit-selected handler returned source_id drift."
                    )
                grants.append(grant)
        return tuple(
            sorted(
                grants,
                key=lambda grant: (
                    grant.hook_id,
                    grant.unit_instance_id,
                    grant.persisting_effect.effect_id,
                ),
            )
        )


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


def _validate_hook_bindings(
    value: object,
) -> tuple[FightUnitSelectedHookBinding, ...]:
    return validate_hook_bindings(
        value,
        lifecycle_event=LifecycleHookEvent.FIGHT_UNIT_SELECTED,
        binding_type=FightUnitSelectedHookBinding,
        registry_name="FightUnitSelectedHookRegistry",
        invalid_binding_message=(
            "FightUnitSelectedHookRegistry bindings must contain "
            "FightUnitSelectedHookBinding values."
        ),
    )


def _validate_grant_bindings(
    value: object,
) -> tuple[FightUnitSelectedGrantBinding, ...]:
    return validate_hook_bindings(
        value,
        lifecycle_event=LifecycleHookEvent.FIGHT_UNIT_SELECTED_GRANT,
        binding_type=FightUnitSelectedGrantBinding,
        registry_name="FightUnitSelectedGrantRegistry",
        invalid_binding_message=(
            "FightUnitSelectedGrantRegistry bindings must contain "
            "FightUnitSelectedGrantBinding values."
        ),
    )


def _validate_optional_expiration(field_name: str, value: object) -> str | None:
    if value is None:
        return None
    expiration = _validate_identifier(field_name, value)
    if expiration not in {"end_phase", "end_turn"}:
        raise GameLifecycleError(
            f"Fight-unit-selected hook {field_name} must be end_phase or end_turn."
        )
    return expiration


_validate_identifier = IdentifierValidator(GameLifecycleError)


def _validate_positive_int(field_name: str, value: object) -> int:
    if type(value) is not int:
        raise GameLifecycleError(f"Fight-unit-selected hook {field_name} must be an int.")
    if value < 1:
        raise GameLifecycleError(f"Fight-unit-selected hook {field_name} must be positive.")
    return value
