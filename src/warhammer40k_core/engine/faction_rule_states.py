from __future__ import annotations

from dataclasses import dataclass
from typing import Self, TypedDict

from warhammer40k_core.core.validation import IdentifierValidator
from warhammer40k_core.engine.event_log import JsonValue, validate_json_value
from warhammer40k_core.engine.phase import GameLifecycleError, SetupStep


class FactionRuleStatePayload(TypedDict):
    state_id: str
    player_id: str
    faction_id: str
    source_rule_id: str
    state_kind: str
    setup_step: str
    request_id: str
    result_id: str
    payload: JsonValue


@dataclass(frozen=True, slots=True)
class FactionRuleState:
    state_id: str
    player_id: str
    faction_id: str
    source_rule_id: str
    state_kind: str
    setup_step: SetupStep
    request_id: str
    result_id: str
    payload: JsonValue

    def __post_init__(self) -> None:
        object.__setattr__(self, "state_id", _validate_identifier("state_id", self.state_id))
        object.__setattr__(
            self,
            "player_id",
            _validate_identifier("player_id", self.player_id),
        )
        object.__setattr__(
            self,
            "faction_id",
            _validate_identifier("faction_id", self.faction_id),
        )
        object.__setattr__(
            self,
            "source_rule_id",
            _validate_identifier("source_rule_id", self.source_rule_id),
        )
        object.__setattr__(
            self,
            "state_kind",
            _validate_identifier("state_kind", self.state_kind),
        )
        object.__setattr__(self, "setup_step", _setup_step_from_token(self.setup_step))
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
        object.__setattr__(self, "payload", validate_json_value(self.payload))

    def to_payload(self) -> FactionRuleStatePayload:
        return {
            "state_id": self.state_id,
            "player_id": self.player_id,
            "faction_id": self.faction_id,
            "source_rule_id": self.source_rule_id,
            "state_kind": self.state_kind,
            "setup_step": self.setup_step.value,
            "request_id": self.request_id,
            "result_id": self.result_id,
            "payload": self.payload,
        }

    @classmethod
    def from_payload(cls, payload: FactionRuleStatePayload) -> Self:
        return cls(
            state_id=payload["state_id"],
            player_id=payload["player_id"],
            faction_id=payload["faction_id"],
            source_rule_id=payload["source_rule_id"],
            state_kind=payload["state_kind"],
            setup_step=_setup_step_from_token(payload["setup_step"]),
            request_id=payload["request_id"],
            result_id=payload["result_id"],
            payload=payload["payload"],
        )


def _setup_step_from_token(token: object) -> SetupStep:
    if type(token) is SetupStep:
        return token
    if type(token) is not str:
        raise GameLifecycleError("FactionRuleState setup_step must be a SetupStep token.")
    try:
        return SetupStep(token)
    except ValueError as exc:
        raise GameLifecycleError(f"Unsupported FactionRuleState setup_step: {token}.") from exc


_validate_identifier = IdentifierValidator(GameLifecycleError)
