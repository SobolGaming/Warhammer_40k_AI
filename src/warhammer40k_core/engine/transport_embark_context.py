"""Source-owned occasions for embarking without making a movement action."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Self, TypedDict, cast

from warhammer40k_core.core.validation import IdentifierValidator
from warhammer40k_core.engine.phase import BattlePhase, GameLifecycleError


class NoMovementEmbarkContextPayload(TypedDict):
    source_rule_id: str
    permission_effect_id: str
    occasion_id: str
    battle_round: int
    turn_player_id: str
    phase: str
    unit_instance_id: str


@dataclass(frozen=True, slots=True)
class NoMovementEmbarkContext:
    source_rule_id: str
    permission_effect_id: str
    occasion_id: str
    battle_round: int
    turn_player_id: str
    phase: BattlePhase
    unit_instance_id: str

    def __post_init__(self) -> None:
        validate = IdentifierValidator(GameLifecycleError)
        for name in (
            "source_rule_id",
            "permission_effect_id",
            "occasion_id",
            "turn_player_id",
            "unit_instance_id",
        ):
            object.__setattr__(self, name, validate(name, getattr(self, name)))
        if type(self.battle_round) is not int or self.battle_round < 1:
            raise GameLifecycleError("No-movement Embark battle_round must be positive.")
        if type(self.phase) is not BattlePhase:
            raise GameLifecycleError("No-movement Embark requires a typed phase.")

    def to_payload(self) -> NoMovementEmbarkContextPayload:
        return {
            "source_rule_id": self.source_rule_id,
            "permission_effect_id": self.permission_effect_id,
            "occasion_id": self.occasion_id,
            "battle_round": self.battle_round,
            "turn_player_id": self.turn_player_id,
            "phase": self.phase.value,
            "unit_instance_id": self.unit_instance_id,
        }

    @classmethod
    def from_payload(cls, payload: NoMovementEmbarkContextPayload) -> Self:
        raw = cast(object, payload)
        if type(raw) is not dict or set(payload) != set(cls.__dataclass_fields__):
            raise GameLifecycleError("No-movement Embark context schema drift.")
        try:
            phase = BattlePhase(payload["phase"])
        except ValueError as error:
            raise GameLifecycleError("No-movement Embark phase is invalid.") from error
        return cls(
            source_rule_id=payload["source_rule_id"],
            permission_effect_id=payload["permission_effect_id"],
            occasion_id=payload["occasion_id"],
            battle_round=payload["battle_round"],
            turn_player_id=payload["turn_player_id"],
            phase=phase,
            unit_instance_id=payload["unit_instance_id"],
        )
