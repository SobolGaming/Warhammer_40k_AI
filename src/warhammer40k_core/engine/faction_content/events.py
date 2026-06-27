from __future__ import annotations

from collections.abc import Callable, Mapping
from dataclasses import dataclass, field
from enum import StrEnum
from types import MappingProxyType
from typing import Self, TypedDict, cast

from warhammer40k_core.core.army_catalog import ArmyCatalog
from warhammer40k_core.core.ruleset_descriptor import (
    BattlePhaseKind,
    RulesetDescriptor,
    battle_phase_kind_from_token,
)
from warhammer40k_core.engine.decision_controller import DecisionController
from warhammer40k_core.engine.event_log import JsonValue, validate_json_value
from warhammer40k_core.engine.game_state import GameState
from warhammer40k_core.engine.phase import GameLifecycleError
from warhammer40k_core.engine.runtime_modifiers import RuntimeModifierRegistry
from warhammer40k_core.engine.timing_windows import (
    TimingTriggerKind,
    timing_trigger_kind_from_token,
)


class RuntimeEventStatus(StrEnum):
    APPLIED = "applied"
    INVALID = "invalid"
    UNSUPPORTED = "unsupported"


class RuntimeContentEventPayload(TypedDict):
    event_id: str
    game_id: str
    player_id: str
    battle_round: int
    trigger_kind: str
    phase: str | None
    active_player_id: str | None
    source_unit_instance_id: str | None
    target_unit_instance_ids: list[str]
    event_payload: JsonValue


class RuntimeContentEventResultPayload(TypedDict):
    subscription_id: str
    source_rule_id: str
    status: str
    reason: str | None
    replay_payload: JsonValue


def _empty_filters() -> Mapping[str, JsonValue]:
    return MappingProxyType({})


@dataclass(frozen=True, slots=True)
class RuntimeContentEvent:
    event_id: str
    game_id: str
    player_id: str
    battle_round: int
    trigger_kind: TimingTriggerKind
    phase: BattlePhaseKind | None = None
    active_player_id: str | None = None
    source_unit_instance_id: str | None = None
    target_unit_instance_ids: tuple[str, ...] = ()
    event_payload: JsonValue = None

    def __post_init__(self) -> None:
        object.__setattr__(self, "event_id", _validate_identifier("event_id", self.event_id))
        object.__setattr__(self, "game_id", _validate_identifier("game_id", self.game_id))
        object.__setattr__(self, "player_id", _validate_identifier("player_id", self.player_id))
        object.__setattr__(
            self,
            "battle_round",
            _validate_positive_int("battle_round", self.battle_round),
        )
        object.__setattr__(
            self,
            "trigger_kind",
            timing_trigger_kind_from_token(self.trigger_kind),
        )
        object.__setattr__(self, "phase", _validate_optional_phase("phase", self.phase))
        object.__setattr__(
            self,
            "active_player_id",
            _validate_optional_identifier("active_player_id", self.active_player_id),
        )
        object.__setattr__(
            self,
            "source_unit_instance_id",
            _validate_optional_identifier("source_unit_instance_id", self.source_unit_instance_id),
        )
        object.__setattr__(
            self,
            "target_unit_instance_ids",
            _validate_identifier_tuple(
                "target_unit_instance_ids",
                self.target_unit_instance_ids,
                sort_values=True,
            ),
        )
        object.__setattr__(self, "event_payload", validate_json_value(self.event_payload))

    def to_payload(self) -> RuntimeContentEventPayload:
        return {
            "event_id": self.event_id,
            "game_id": self.game_id,
            "player_id": self.player_id,
            "battle_round": self.battle_round,
            "trigger_kind": self.trigger_kind.value,
            "phase": None if self.phase is None else self.phase.value,
            "active_player_id": self.active_player_id,
            "source_unit_instance_id": self.source_unit_instance_id,
            "target_unit_instance_ids": list(self.target_unit_instance_ids),
            "event_payload": self.event_payload,
        }

    @classmethod
    def from_payload(cls, payload: RuntimeContentEventPayload) -> Self:
        phase_token = payload["phase"]
        return cls(
            event_id=payload["event_id"],
            game_id=payload["game_id"],
            player_id=payload["player_id"],
            battle_round=payload["battle_round"],
            trigger_kind=timing_trigger_kind_from_token(payload["trigger_kind"]),
            phase=None if phase_token is None else battle_phase_kind_from_token(phase_token),
            active_player_id=payload["active_player_id"],
            source_unit_instance_id=payload["source_unit_instance_id"],
            target_unit_instance_ids=tuple(payload["target_unit_instance_ids"]),
            event_payload=payload["event_payload"],
        )


@dataclass(frozen=True, slots=True)
class RuntimeContentEventContext:
    event: RuntimeContentEvent
    state: GameState
    decisions: DecisionController
    ruleset_descriptor: RulesetDescriptor
    army_catalog: ArmyCatalog
    runtime_modifier_registry: RuntimeModifierRegistry

    def __post_init__(self) -> None:
        if type(self.event) is not RuntimeContentEvent:
            raise GameLifecycleError("Runtime event context requires RuntimeContentEvent.")
        if type(self.state) is not GameState:
            raise GameLifecycleError("Runtime event context requires GameState.")
        if type(self.decisions) is not DecisionController:
            raise GameLifecycleError("Runtime event context requires DecisionController.")
        if type(self.ruleset_descriptor) is not RulesetDescriptor:
            raise GameLifecycleError("Runtime event context requires RulesetDescriptor.")
        if type(self.army_catalog) is not ArmyCatalog:
            raise GameLifecycleError("Runtime event context requires ArmyCatalog.")
        if type(self.runtime_modifier_registry) is not RuntimeModifierRegistry:
            raise GameLifecycleError("Runtime event context requires RuntimeModifierRegistry.")


RuntimeEventHandler = Callable[[RuntimeContentEventContext], "RuntimeContentEventResult"]


@dataclass(frozen=True, slots=True)
class RuntimeContentEventResult:
    subscription_id: str
    source_rule_id: str
    status: RuntimeEventStatus
    reason: str | None = None
    replay_payload: JsonValue = None

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "subscription_id",
            _validate_identifier("subscription_id", self.subscription_id),
        )
        object.__setattr__(
            self,
            "source_rule_id",
            _validate_identifier("source_rule_id", self.source_rule_id),
        )
        object.__setattr__(self, "status", _runtime_event_status_from_token(self.status))
        object.__setattr__(
            self,
            "reason",
            _validate_optional_identifier("reason", self.reason),
        )
        object.__setattr__(self, "replay_payload", validate_json_value(self.replay_payload))
        if self.status is RuntimeEventStatus.APPLIED and self.reason is not None:
            raise GameLifecycleError("Applied runtime event result cannot include reason.")
        if self.status is not RuntimeEventStatus.APPLIED and self.reason is None:
            raise GameLifecycleError("Non-applied runtime event result requires reason.")

    @classmethod
    def applied(
        cls,
        subscription: RuntimeContentEventSubscription,
        *,
        replay_payload: JsonValue = None,
    ) -> Self:
        _validate_subscription(subscription)
        return cls(
            subscription_id=subscription.subscription_id,
            source_rule_id=subscription.source_rule_id,
            status=RuntimeEventStatus.APPLIED,
            replay_payload=replay_payload,
        )

    @classmethod
    def unsupported(
        cls,
        subscription: RuntimeContentEventSubscription,
        *,
        reason: str,
        replay_payload: JsonValue = None,
    ) -> Self:
        _validate_subscription(subscription)
        return cls(
            subscription_id=subscription.subscription_id,
            source_rule_id=subscription.source_rule_id,
            status=RuntimeEventStatus.UNSUPPORTED,
            reason=reason,
            replay_payload=replay_payload,
        )

    @classmethod
    def invalid(
        cls,
        subscription: RuntimeContentEventSubscription,
        *,
        reason: str,
        replay_payload: JsonValue = None,
    ) -> Self:
        _validate_subscription(subscription)
        return cls(
            subscription_id=subscription.subscription_id,
            source_rule_id=subscription.source_rule_id,
            status=RuntimeEventStatus.INVALID,
            reason=reason,
            replay_payload=replay_payload,
        )

    def to_payload(self) -> RuntimeContentEventResultPayload:
        return {
            "subscription_id": self.subscription_id,
            "source_rule_id": self.source_rule_id,
            "status": self.status.value,
            "reason": self.reason,
            "replay_payload": self.replay_payload,
        }

    @classmethod
    def from_payload(cls, payload: RuntimeContentEventResultPayload) -> Self:
        return cls(
            subscription_id=payload["subscription_id"],
            source_rule_id=payload["source_rule_id"],
            status=_runtime_event_status_from_token(payload["status"]),
            reason=payload["reason"],
            replay_payload=payload["replay_payload"],
        )


@dataclass(frozen=True, slots=True)
class RuntimeContentEventSubscription:
    subscription_id: str
    source_rule_id: str
    trigger_kind: TimingTriggerKind
    handler_id: str
    filters: Mapping[str, JsonValue] = field(default_factory=_empty_filters)

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "subscription_id",
            _validate_identifier("subscription_id", self.subscription_id),
        )
        object.__setattr__(
            self,
            "source_rule_id",
            _validate_identifier("source_rule_id", self.source_rule_id),
        )
        object.__setattr__(
            self,
            "trigger_kind",
            timing_trigger_kind_from_token(self.trigger_kind),
        )
        object.__setattr__(
            self,
            "handler_id",
            _validate_identifier("handler_id", self.handler_id),
        )
        object.__setattr__(self, "filters", _validate_filters(self.filters))

    def to_summary_payload(self) -> dict[str, JsonValue]:
        return {
            "subscription_id": self.subscription_id,
            "source_rule_id": self.source_rule_id,
            "trigger_kind": self.trigger_kind.value,
            "handler_id": self.handler_id,
            "filters": dict(self.filters),
        }


@dataclass(frozen=True, slots=True)
class RuntimeContentEventHandlerBinding:
    handler_id: str
    handler: RuntimeEventHandler

    def __post_init__(self) -> None:
        object.__setattr__(self, "handler_id", _validate_identifier("handler_id", self.handler_id))
        if not callable(self.handler):
            raise GameLifecycleError("Runtime event handler binding must be callable.")

    def to_summary_payload(self) -> dict[str, JsonValue]:
        return {"handler_id": self.handler_id}


@dataclass(frozen=True, slots=True)
class RuntimeContentEventHandlerRegistry:
    _bindings: Mapping[str, RuntimeContentEventHandlerBinding]

    @classmethod
    def from_bindings(cls, bindings: tuple[RuntimeContentEventHandlerBinding, ...]) -> Self:
        if type(bindings) is not tuple:
            raise GameLifecycleError("Runtime event handler bindings must be a tuple.")
        seen: set[str] = set()
        resolved: dict[str, RuntimeContentEventHandlerBinding] = {}
        for binding in cast(tuple[object, ...], bindings):
            if type(binding) is not RuntimeContentEventHandlerBinding:
                raise GameLifecycleError(
                    "Runtime event handler bindings must contain RuntimeContentEventHandlerBinding."
                )
            if binding.handler_id in seen:
                raise GameLifecycleError("Runtime event handler IDs must be unique.")
            seen.add(binding.handler_id)
            resolved[binding.handler_id] = binding
        return cls(_bindings=MappingProxyType(resolved))

    @classmethod
    def empty(cls) -> Self:
        return cls.from_bindings(())

    def handler_for(self, handler_id: str) -> RuntimeEventHandler:
        requested_id = _validate_identifier("handler_id", handler_id)
        binding = self._bindings.get(requested_id)
        if binding is None:
            raise GameLifecycleError("Runtime event subscription references missing handler.")
        return binding.handler

    def all_bindings(self) -> tuple[RuntimeContentEventHandlerBinding, ...]:
        return tuple(sorted(self._bindings.values(), key=lambda binding: binding.handler_id))


@dataclass(frozen=True, slots=True)
class RuntimeContentEventIndex:
    _subscriptions_by_trigger: Mapping[
        TimingTriggerKind,
        tuple[RuntimeContentEventSubscription, ...],
    ]
    _subscriptions: tuple[RuntimeContentEventSubscription, ...]
    _handler_registry: RuntimeContentEventHandlerRegistry

    @classmethod
    def from_subscriptions(
        cls,
        subscriptions: tuple[RuntimeContentEventSubscription, ...],
        *,
        handler_registry: RuntimeContentEventHandlerRegistry,
    ) -> Self:
        if type(handler_registry) is not RuntimeContentEventHandlerRegistry:
            raise GameLifecycleError("Runtime event index requires handler registry.")
        validated = _validate_subscriptions(subscriptions)
        for subscription in validated:
            handler_registry.handler_for(subscription.handler_id)
        grouped: dict[TimingTriggerKind, list[RuntimeContentEventSubscription]] = {}
        for subscription in validated:
            grouped.setdefault(subscription.trigger_kind, []).append(subscription)
        return cls(
            _subscriptions_by_trigger=MappingProxyType(
                {trigger_kind: tuple(records) for trigger_kind, records in grouped.items()}
            ),
            _subscriptions=validated,
            _handler_registry=handler_registry,
        )

    @classmethod
    def empty(cls) -> Self:
        return cls.from_subscriptions(
            (),
            handler_registry=RuntimeContentEventHandlerRegistry.empty(),
        )

    def subscriptions_for(
        self,
        trigger_kind: TimingTriggerKind,
    ) -> tuple[RuntimeContentEventSubscription, ...]:
        if type(trigger_kind) is not TimingTriggerKind:
            raise GameLifecycleError("Runtime event lookup requires a TimingTriggerKind.")
        return self._subscriptions_by_trigger.get(trigger_kind, ())

    def all_subscriptions(self) -> tuple[RuntimeContentEventSubscription, ...]:
        return self._subscriptions

    def dispatch(
        self,
        event: RuntimeContentEvent,
        *,
        state: GameState,
        decisions: DecisionController,
        ruleset_descriptor: RulesetDescriptor,
        army_catalog: ArmyCatalog,
        runtime_modifier_registry: RuntimeModifierRegistry,
    ) -> tuple[RuntimeContentEventResult, ...]:
        if type(event) is not RuntimeContentEvent:
            raise GameLifecycleError("Runtime event dispatch requires a RuntimeContentEvent.")
        context = RuntimeContentEventContext(
            event=event,
            state=state,
            decisions=decisions,
            ruleset_descriptor=ruleset_descriptor,
            army_catalog=army_catalog,
            runtime_modifier_registry=runtime_modifier_registry,
        )
        results: list[RuntimeContentEventResult] = []
        for subscription in self.subscriptions_for(event.trigger_kind):
            if not _event_matches_filters(event=event, subscription=subscription):
                continue
            handler = self._handler_registry.handler_for(subscription.handler_id)
            result = handler(context)
            _validate_result_matches_subscription(result=result, subscription=subscription)
            results.append(result)
        return tuple(results)

    def to_summary_payload(self) -> list[dict[str, JsonValue]]:
        return [subscription.to_summary_payload() for subscription in self._subscriptions]


def _validate_subscriptions(
    subscriptions: object,
) -> tuple[RuntimeContentEventSubscription, ...]:
    if type(subscriptions) is not tuple:
        raise GameLifecycleError("Runtime event subscriptions must be a tuple.")
    validated: list[RuntimeContentEventSubscription] = []
    seen: set[str] = set()
    for subscription in cast(tuple[object, ...], subscriptions):
        validated_subscription = _validate_subscription(subscription)
        if validated_subscription.subscription_id in seen:
            raise GameLifecycleError("Runtime event subscription IDs must be unique.")
        seen.add(validated_subscription.subscription_id)
        validated.append(validated_subscription)
    return tuple(sorted(validated, key=lambda value: value.subscription_id))


def _validate_subscription(value: object) -> RuntimeContentEventSubscription:
    if type(value) is not RuntimeContentEventSubscription:
        raise GameLifecycleError(
            "Runtime event subscriptions must contain RuntimeContentEventSubscription values."
        )
    return value


def _validate_result_matches_subscription(
    *,
    result: RuntimeContentEventResult,
    subscription: RuntimeContentEventSubscription,
) -> None:
    if type(result) is not RuntimeContentEventResult:
        raise GameLifecycleError("Runtime event handler must return RuntimeContentEventResult.")
    if result.subscription_id != subscription.subscription_id:
        raise GameLifecycleError("Runtime event handler returned subscription_id drift.")
    if result.source_rule_id != subscription.source_rule_id:
        raise GameLifecycleError("Runtime event handler returned source_rule_id drift.")


def _event_matches_filters(
    *,
    event: RuntimeContentEvent,
    subscription: RuntimeContentEventSubscription,
) -> bool:
    for key, value in subscription.filters.items():
        if key == "player_id" and event.player_id != value:
            return False
        if key == "active_player_id" and event.active_player_id != value:
            return False
        if key == "source_unit_instance_id" and event.source_unit_instance_id != value:
            return False
    return True


def _runtime_event_status_from_token(token: object) -> RuntimeEventStatus:
    if type(token) is RuntimeEventStatus:
        return token
    if type(token) is not str:
        raise GameLifecycleError("RuntimeEventStatus token must be a string.")
    try:
        return RuntimeEventStatus(token)
    except ValueError as exc:
        raise GameLifecycleError(f"Unsupported RuntimeEventStatus token: {token}.") from exc


def _validate_optional_phase(field_name: str, value: object | None) -> BattlePhaseKind | None:
    if value is None:
        return None
    return battle_phase_kind_from_token(value)


def _validate_identifier_tuple(
    field_name: str,
    values: object,
    *,
    sort_values: bool,
) -> tuple[str, ...]:
    if type(values) is not tuple:
        raise GameLifecycleError(f"Runtime event {field_name} must be a tuple.")
    seen: set[str] = set()
    identifiers: list[str] = []
    for value in cast(tuple[object, ...], values):
        identifier = _validate_identifier(f"{field_name} value", value)
        if identifier in seen:
            raise GameLifecycleError(f"Runtime event {field_name} must not contain duplicates.")
        seen.add(identifier)
        identifiers.append(identifier)
    if sort_values:
        return tuple(sorted(identifiers))
    return tuple(identifiers)


def _validate_identifier(field_name: str, value: object) -> str:
    if type(value) is not str:
        raise GameLifecycleError(f"Runtime event {field_name} must be a string.")
    stripped = value.strip()
    if not stripped:
        raise GameLifecycleError(f"Runtime event {field_name} must not be empty.")
    return stripped


def _validate_optional_identifier(field_name: str, value: object | None) -> str | None:
    if value is None:
        return None
    return _validate_identifier(field_name, value)


def _validate_positive_int(field_name: str, value: object) -> int:
    if type(value) is not int:
        raise GameLifecycleError(f"Runtime event {field_name} must be an integer.")
    if value < 1:
        raise GameLifecycleError(f"Runtime event {field_name} must be positive.")
    return value


def _validate_filters(value: object) -> Mapping[str, JsonValue]:
    if not isinstance(value, Mapping):
        raise GameLifecycleError("Runtime event filters must be a mapping.")
    filters: dict[str, JsonValue] = {}
    for raw_key, raw_value in cast(Mapping[object, object], value).items():
        key = _validate_identifier("filter key", raw_key)
        filters[key] = validate_json_value(raw_value)
    return MappingProxyType(dict(sorted(filters.items())))
