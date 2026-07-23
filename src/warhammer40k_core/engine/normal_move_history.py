from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
from typing import Self, TypedDict

from warhammer40k_core.core.validation import IdentifierValidator
from warhammer40k_core.engine.phase import BattlePhase, GameLifecycleError

ONE_NORMAL_MOVE_PER_PHASE_SOURCE_RULE_ID = (
    "gw-11e-rules-and-event-updates-2026-07-22:app-core-rules:09-normal-move-one-per-phase"
)

_validate_identifier = IdentifierValidator(GameLifecycleError)


class NormalMoveSourceKind(StrEnum):
    MOVEMENT_PHASE_ACTION = "movement_phase_action"
    SURGE = "surge"
    TRIGGERED = "triggered"


class NormalMoveStatePayload(TypedDict):
    player_id: str
    battle_round: int
    phase: str
    unit_instance_id: str
    source_rule_id: str
    source_kind: str
    request_id: str
    result_id: str


@dataclass(frozen=True, slots=True)
class NormalMoveState:
    player_id: str
    battle_round: int
    phase: BattlePhase
    unit_instance_id: str
    source_rule_id: str
    source_kind: NormalMoveSourceKind
    request_id: str
    result_id: str

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "player_id",
            _validate_identifier("NormalMoveState player_id", self.player_id),
        )
        if type(self.battle_round) is not int or self.battle_round < 1:
            raise GameLifecycleError("NormalMoveState battle_round must be a positive integer.")
        object.__setattr__(self, "phase", _battle_phase_from_token(self.phase))
        object.__setattr__(
            self,
            "unit_instance_id",
            _validate_identifier("NormalMoveState unit_instance_id", self.unit_instance_id),
        )
        object.__setattr__(
            self,
            "source_rule_id",
            _validate_identifier("NormalMoveState source_rule_id", self.source_rule_id),
        )
        object.__setattr__(
            self,
            "source_kind",
            normal_move_source_kind_from_token(self.source_kind),
        )
        object.__setattr__(
            self,
            "request_id",
            _validate_identifier("NormalMoveState request_id", self.request_id),
        )
        object.__setattr__(
            self,
            "result_id",
            _validate_identifier("NormalMoveState result_id", self.result_id),
        )

    def same_phase_key(self) -> tuple[int, BattlePhase, str, str]:
        return (self.battle_round, self.phase, self.player_id, self.unit_instance_id)

    def to_payload(self) -> NormalMoveStatePayload:
        return {
            "player_id": self.player_id,
            "battle_round": self.battle_round,
            "phase": self.phase.value,
            "unit_instance_id": self.unit_instance_id,
            "source_rule_id": self.source_rule_id,
            "source_kind": self.source_kind.value,
            "request_id": self.request_id,
            "result_id": self.result_id,
        }

    @classmethod
    def from_payload(cls, payload: NormalMoveStatePayload) -> Self:
        return cls(
            player_id=payload["player_id"],
            battle_round=payload["battle_round"],
            phase=_battle_phase_from_token(payload["phase"]),
            unit_instance_id=payload["unit_instance_id"],
            source_rule_id=payload["source_rule_id"],
            source_kind=normal_move_source_kind_from_token(payload["source_kind"]),
            request_id=payload["request_id"],
            result_id=payload["result_id"],
        )


def normal_move_source_kind_from_token(value: object) -> NormalMoveSourceKind:
    if type(value) is NormalMoveSourceKind:
        return value
    if type(value) is not str:
        raise GameLifecycleError("NormalMoveSourceKind token must be a string.")
    try:
        return NormalMoveSourceKind(value)
    except ValueError as exc:
        raise GameLifecycleError(f"Unsupported NormalMoveSourceKind token: {value}.") from exc


def _battle_phase_from_token(value: object) -> BattlePhase:
    if type(value) is BattlePhase:
        return value
    if type(value) is not str:
        raise GameLifecycleError("NormalMoveState phase token must be a string.")
    try:
        return BattlePhase(value)
    except ValueError as exc:
        raise GameLifecycleError(f"Unsupported NormalMoveState phase token: {value}.") from exc
