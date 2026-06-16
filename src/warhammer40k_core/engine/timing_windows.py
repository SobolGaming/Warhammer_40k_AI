from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
from typing import Self, TypedDict, cast

from warhammer40k_core.core.ruleset_descriptor import (
    BattlePhaseKind,
    battle_phase_kind_from_token,
)
from warhammer40k_core.engine.event_log import JsonValue, validate_json_value


class TimingWindowError(ValueError):
    """Raised when a timing window cannot be represented safely."""


class TimingTriggerKind(StrEnum):
    ANY_PHASE = "any_phase"
    START_PHASE = "start_phase"
    END_PHASE = "end_phase"
    START_TURN = "start_turn"
    END_TURN = "end_turn"
    START_BATTLE_ROUND = "start_battle_round"
    END_BATTLE_ROUND = "end_battle_round"
    BEFORE_BATTLE = "before_battle"
    AFTER_BATTLE = "after_battle"
    AFTER_UNIT_SELECTED_AS_TARGET = "after_unit_selected_as_target"
    JUST_AFTER_FRIENDLY_UNIT_SELECTED_TO_MOVE = "just_after_friendly_unit_selected_to_move"
    JUST_AFTER_ENEMY_UNIT_SELECTED_TO_FALL_BACK = "just_after_enemy_unit_selected_to_fall_back"
    JUST_AFTER_FRIENDLY_UNIT_HAS_SHOT = "just_after_friendly_unit_has_shot"
    AFTER_ENEMY_UNIT_ENDS_MOVE = "after_enemy_unit_ends_move"
    AFTER_UNIT_ENDS_CHARGE_MOVE = "after_unit_ends_charge_move"
    AFTER_UNIT_DESTROYED = "after_unit_destroyed"
    JUST_AFTER_ENEMY_UNIT_HAS_FOUGHT = "just_after_enemy_unit_has_fought"
    JUST_AFTER_FRIENDLY_UNIT_SELECTED_TO_FIGHT = "just_after_friendly_unit_selected_to_fight"
    AFTER_DICE_ROLL = "after_dice_roll"


class TimingWindowDescriptorPayload(TypedDict):
    descriptor_id: str
    trigger_kind: str
    source_rule_id: str
    phase: str | None
    source_step: str | None
    metadata: JsonValue


class TimingWindowPayload(TypedDict):
    window_id: str
    descriptor: TimingWindowDescriptorPayload
    game_id: str
    battle_round: int
    active_player_id: str | None
    phase: str | None
    trigger_event_id: str | None


class ReactionWindowPayload(TypedDict):
    timing_window: TimingWindowPayload
    eligible_player_ids: list[str]
    blocks_parent: bool


class OutOfPhaseActionContextPayload(TypedDict):
    context_id: str
    parent_window: TimingWindowPayload
    action_phase: str
    action_kind: str
    source_rule_id: str
    allow_normal_phase_triggers: bool


_PHASE_REQUIRED_TRIGGERS = frozenset(
    (
        TimingTriggerKind.START_PHASE,
        TimingTriggerKind.END_PHASE,
    )
)


@dataclass(frozen=True, slots=True)
class TimingWindowDescriptor:
    descriptor_id: str
    trigger_kind: TimingTriggerKind
    source_rule_id: str
    phase: BattlePhaseKind | None = None
    source_step: str | None = None
    metadata: JsonValue = None

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "descriptor_id",
            _validate_identifier("TimingWindowDescriptor descriptor_id", self.descriptor_id),
        )
        object.__setattr__(
            self,
            "trigger_kind",
            timing_trigger_kind_from_token(self.trigger_kind),
        )
        object.__setattr__(
            self,
            "source_rule_id",
            _validate_identifier("TimingWindowDescriptor source_rule_id", self.source_rule_id),
        )
        object.__setattr__(
            self,
            "phase",
            _validate_optional_phase("TimingWindowDescriptor phase", self.phase),
        )
        object.__setattr__(
            self,
            "source_step",
            _validate_optional_identifier(
                "TimingWindowDescriptor source_step",
                self.source_step,
            ),
        )
        object.__setattr__(self, "metadata", validate_json_value(self.metadata))
        if self.trigger_kind in _PHASE_REQUIRED_TRIGGERS and self.phase is None:
            raise TimingWindowError("TimingWindowDescriptor trigger requires a phase.")

    def to_payload(self) -> TimingWindowDescriptorPayload:
        return {
            "descriptor_id": self.descriptor_id,
            "trigger_kind": self.trigger_kind.value,
            "source_rule_id": self.source_rule_id,
            "phase": None if self.phase is None else self.phase.value,
            "source_step": self.source_step,
            "metadata": self.metadata,
        }

    @classmethod
    def from_payload(cls, payload: TimingWindowDescriptorPayload) -> Self:
        phase_token = payload["phase"]
        return cls(
            descriptor_id=payload["descriptor_id"],
            trigger_kind=timing_trigger_kind_from_token(payload["trigger_kind"]),
            source_rule_id=payload["source_rule_id"],
            phase=None if phase_token is None else battle_phase_kind_from_token(phase_token),
            source_step=payload["source_step"],
            metadata=payload["metadata"],
        )


@dataclass(frozen=True, slots=True)
class TimingWindow:
    window_id: str
    descriptor: TimingWindowDescriptor
    game_id: str
    battle_round: int
    active_player_id: str | None
    phase: BattlePhaseKind | None = None
    trigger_event_id: str | None = None

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "window_id",
            _validate_identifier("TimingWindow window_id", self.window_id),
        )
        if type(self.descriptor) is not TimingWindowDescriptor:
            raise TimingWindowError("TimingWindow descriptor must be a TimingWindowDescriptor.")
        object.__setattr__(
            self,
            "game_id",
            _validate_identifier("TimingWindow game_id", self.game_id),
        )
        object.__setattr__(
            self,
            "battle_round",
            _validate_non_negative_int("TimingWindow battle_round", self.battle_round),
        )
        object.__setattr__(
            self,
            "active_player_id",
            _validate_optional_identifier(
                "TimingWindow active_player_id",
                self.active_player_id,
            ),
        )
        object.__setattr__(
            self,
            "phase",
            _validate_optional_phase("TimingWindow phase", self.phase),
        )
        object.__setattr__(
            self,
            "trigger_event_id",
            _validate_optional_identifier(
                "TimingWindow trigger_event_id",
                self.trigger_event_id,
            ),
        )
        if (
            self.descriptor.phase is not None
            and self.phase is not None
            and self.descriptor.phase is not self.phase
        ):
            raise TimingWindowError("TimingWindow phase does not match descriptor phase.")

    def to_payload(self) -> TimingWindowPayload:
        return {
            "window_id": self.window_id,
            "descriptor": self.descriptor.to_payload(),
            "game_id": self.game_id,
            "battle_round": self.battle_round,
            "active_player_id": self.active_player_id,
            "phase": None if self.phase is None else self.phase.value,
            "trigger_event_id": self.trigger_event_id,
        }

    @classmethod
    def from_payload(cls, payload: TimingWindowPayload) -> Self:
        phase_token = payload["phase"]
        return cls(
            window_id=payload["window_id"],
            descriptor=TimingWindowDescriptor.from_payload(payload["descriptor"]),
            game_id=payload["game_id"],
            battle_round=payload["battle_round"],
            active_player_id=payload["active_player_id"],
            phase=None if phase_token is None else battle_phase_kind_from_token(phase_token),
            trigger_event_id=payload["trigger_event_id"],
        )


@dataclass(frozen=True, slots=True)
class ReactionWindow:
    timing_window: TimingWindow
    eligible_player_ids: tuple[str, ...]
    blocks_parent: bool = True

    def __post_init__(self) -> None:
        if type(self.timing_window) is not TimingWindow:
            raise TimingWindowError("ReactionWindow timing_window must be a TimingWindow.")
        object.__setattr__(
            self,
            "eligible_player_ids",
            _validate_identifier_tuple(
                "ReactionWindow eligible_player_ids",
                self.eligible_player_ids,
                min_length=1,
                sort_values=True,
            ),
        )
        if type(self.blocks_parent) is not bool:
            raise TimingWindowError("ReactionWindow blocks_parent must be a bool.")

    def to_payload(self) -> ReactionWindowPayload:
        return {
            "timing_window": self.timing_window.to_payload(),
            "eligible_player_ids": list(self.eligible_player_ids),
            "blocks_parent": self.blocks_parent,
        }

    @classmethod
    def from_payload(cls, payload: ReactionWindowPayload) -> Self:
        return cls(
            timing_window=TimingWindow.from_payload(payload["timing_window"]),
            eligible_player_ids=tuple(payload["eligible_player_ids"]),
            blocks_parent=payload["blocks_parent"],
        )


@dataclass(frozen=True, slots=True)
class OutOfPhaseActionContext:
    context_id: str
    parent_window: TimingWindow
    action_phase: BattlePhaseKind
    action_kind: str
    source_rule_id: str
    allow_normal_phase_triggers: bool = False

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "context_id",
            _validate_identifier("OutOfPhaseActionContext context_id", self.context_id),
        )
        if type(self.parent_window) is not TimingWindow:
            raise TimingWindowError("OutOfPhaseActionContext parent_window must be a TimingWindow.")
        object.__setattr__(
            self,
            "action_phase",
            battle_phase_kind_from_token(self.action_phase),
        )
        object.__setattr__(
            self,
            "action_kind",
            _validate_identifier("OutOfPhaseActionContext action_kind", self.action_kind),
        )
        object.__setattr__(
            self,
            "source_rule_id",
            _validate_identifier("OutOfPhaseActionContext source_rule_id", self.source_rule_id),
        )
        if type(self.allow_normal_phase_triggers) is not bool:
            raise TimingWindowError(
                "OutOfPhaseActionContext allow_normal_phase_triggers must be a bool."
            )

    def allows_action(self, action_kind: str) -> bool:
        return _validate_identifier("action_kind", action_kind) == self.action_kind

    def allows_normal_phase_trigger(self, phase: BattlePhaseKind) -> bool:
        requested_phase = battle_phase_kind_from_token(phase)
        if requested_phase is not self.action_phase:
            return True
        return self.allow_normal_phase_triggers

    def to_payload(self) -> OutOfPhaseActionContextPayload:
        return {
            "context_id": self.context_id,
            "parent_window": self.parent_window.to_payload(),
            "action_phase": self.action_phase.value,
            "action_kind": self.action_kind,
            "source_rule_id": self.source_rule_id,
            "allow_normal_phase_triggers": self.allow_normal_phase_triggers,
        }

    @classmethod
    def from_payload(cls, payload: OutOfPhaseActionContextPayload) -> Self:
        return cls(
            context_id=payload["context_id"],
            parent_window=TimingWindow.from_payload(payload["parent_window"]),
            action_phase=battle_phase_kind_from_token(payload["action_phase"]),
            action_kind=payload["action_kind"],
            source_rule_id=payload["source_rule_id"],
            allow_normal_phase_triggers=payload["allow_normal_phase_triggers"],
        )


def timing_trigger_kind_from_token(token: object) -> TimingTriggerKind:
    if type(token) is TimingTriggerKind:
        return token
    if type(token) is not str:
        raise TimingWindowError("TimingTriggerKind token must be a string.")
    try:
        return TimingTriggerKind(token)
    except ValueError as exc:
        raise TimingWindowError(f"Unsupported TimingTriggerKind token: {token}.") from exc


def _validate_optional_phase(field_name: str, value: object | None) -> BattlePhaseKind | None:
    if value is None:
        return None
    try:
        return battle_phase_kind_from_token(value)
    except ValueError as exc:
        raise TimingWindowError(f"{field_name} must be a supported BattlePhaseKind.") from exc


def _validate_identifier(field_name: str, value: object) -> str:
    if type(value) is not str:
        raise TimingWindowError(f"{field_name} must be a string.")
    stripped = value.strip()
    if not stripped:
        raise TimingWindowError(f"{field_name} must not be empty.")
    return stripped


def _validate_optional_identifier(field_name: str, value: object | None) -> str | None:
    if value is None:
        return None
    return _validate_identifier(field_name, value)


def _validate_identifier_tuple(
    field_name: str,
    values: object,
    *,
    min_length: int,
    sort_values: bool,
) -> tuple[str, ...]:
    if type(values) is not tuple:
        raise TimingWindowError(f"{field_name} must be a tuple.")
    raw_values = cast(tuple[object, ...], values)
    identifiers: list[str] = []
    seen: set[str] = set()
    for value in raw_values:
        identifier = _validate_identifier(f"{field_name} value", value)
        if identifier in seen:
            raise TimingWindowError(f"{field_name} must not contain duplicates.")
        seen.add(identifier)
        identifiers.append(identifier)
    if len(identifiers) < min_length:
        raise TimingWindowError(f"{field_name} must contain at least {min_length} value.")
    if sort_values:
        return tuple(sorted(identifiers))
    return tuple(identifiers)


def _validate_non_negative_int(field_name: str, value: object) -> int:
    if type(value) is not int:
        raise TimingWindowError(f"{field_name} must be an integer.")
    if value < 0:
        raise TimingWindowError(f"{field_name} must not be negative.")
    return value
