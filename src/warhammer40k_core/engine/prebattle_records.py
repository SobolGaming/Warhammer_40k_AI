from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
from typing import Self, TypedDict

from warhammer40k_core.engine.event_log import JsonValue, validate_json_value
from warhammer40k_core.engine.phase import GameLifecycleError, SetupStep


class PreBattleActionKind(StrEnum):
    COMPLETE_REDEPLOYS = "complete_redeploys"
    REDEPLOY = "redeploy"
    COMPLETE_PREBATTLE_ACTIONS = "complete_prebattle_actions"
    SCOUT_MOVE = "scout_move"
    SCOUT_RESERVE_SETUP = "scout_reserve_setup"
    DEDICATED_TRANSPORT_SCOUT_MOVE = "dedicated_transport_scout_move"


class PreBattleActionRecordPayload(TypedDict):
    action_id: str
    game_id: str
    player_id: str
    setup_step: str
    action_kind: str
    unit_instance_id: str | None
    source_rule_id: str
    request_id: str
    result_id: str
    payload: JsonValue


@dataclass(frozen=True, slots=True)
class PreBattleActionRecord:
    action_id: str
    game_id: str
    player_id: str
    setup_step: SetupStep
    action_kind: PreBattleActionKind
    source_rule_id: str
    request_id: str
    result_id: str
    unit_instance_id: str | None = None
    payload: JsonValue = None

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "action_id",
            _validate_identifier("PreBattleActionRecord action_id", self.action_id),
        )
        object.__setattr__(
            self,
            "game_id",
            _validate_identifier("PreBattleActionRecord game_id", self.game_id),
        )
        object.__setattr__(
            self,
            "player_id",
            _validate_identifier("PreBattleActionRecord player_id", self.player_id),
        )
        object.__setattr__(self, "setup_step", _setup_step_from_token(self.setup_step))
        object.__setattr__(
            self,
            "action_kind",
            prebattle_action_kind_from_token(self.action_kind),
        )
        object.__setattr__(
            self,
            "source_rule_id",
            _validate_identifier("PreBattleActionRecord source_rule_id", self.source_rule_id),
        )
        object.__setattr__(
            self,
            "request_id",
            _validate_identifier("PreBattleActionRecord request_id", self.request_id),
        )
        object.__setattr__(
            self,
            "result_id",
            _validate_identifier("PreBattleActionRecord result_id", self.result_id),
        )
        object.__setattr__(
            self,
            "unit_instance_id",
            _validate_optional_identifier(
                "PreBattleActionRecord unit_instance_id",
                self.unit_instance_id,
            ),
        )
        object.__setattr__(self, "payload", validate_json_value(self.payload))

    def to_payload(self) -> PreBattleActionRecordPayload:
        return {
            "action_id": self.action_id,
            "game_id": self.game_id,
            "player_id": self.player_id,
            "setup_step": self.setup_step.value,
            "action_kind": self.action_kind.value,
            "unit_instance_id": self.unit_instance_id,
            "source_rule_id": self.source_rule_id,
            "request_id": self.request_id,
            "result_id": self.result_id,
            "payload": self.payload,
        }

    @classmethod
    def from_payload(cls, payload: PreBattleActionRecordPayload) -> Self:
        return cls(
            action_id=payload["action_id"],
            game_id=payload["game_id"],
            player_id=payload["player_id"],
            setup_step=_setup_step_from_token(payload["setup_step"]),
            action_kind=prebattle_action_kind_from_token(payload["action_kind"]),
            unit_instance_id=payload["unit_instance_id"],
            source_rule_id=payload["source_rule_id"],
            request_id=payload["request_id"],
            result_id=payload["result_id"],
            payload=payload["payload"],
        )


def prebattle_action_kind_from_token(token: object) -> PreBattleActionKind:
    if type(token) is PreBattleActionKind:
        return token
    if type(token) is not str:
        raise GameLifecycleError("PreBattleActionKind token must be a string.")
    try:
        return PreBattleActionKind(token)
    except ValueError as exc:
        raise GameLifecycleError(f"Unsupported PreBattleActionKind token: {token}.") from exc


def _setup_step_from_token(token: object) -> SetupStep:
    if type(token) is SetupStep:
        return token
    if type(token) is not str:
        raise GameLifecycleError("PreBattleActionRecord setup_step token must be a string.")
    try:
        return SetupStep(token)
    except ValueError as exc:
        raise GameLifecycleError(f"Unsupported setup step token: {token}.") from exc


def _validate_identifier(field_name: str, value: object) -> str:
    if type(value) is not str:
        raise GameLifecycleError(f"{field_name} must be a string.")
    stripped = value.strip()
    if not stripped:
        raise GameLifecycleError(f"{field_name} must not be empty.")
    return stripped


def _validate_optional_identifier(field_name: str, value: object | None) -> str | None:
    if value is None:
        return None
    return _validate_identifier(field_name, value)
