from __future__ import annotations

from dataclasses import dataclass
from typing import Self, TypedDict, cast

from warhammer40k_core.core.ruleset_descriptor import (
    BattlePhaseKind,
    battle_phase_kind_from_token,
)
from warhammer40k_core.core.validation import IdentifierValidator
from warhammer40k_core.engine.phase import GameLifecycleError


class ForcedFightActivationContextPayload(TypedDict):
    context_id: str
    source_rule_id: str
    trigger_event_id: str
    source_phase: str
    source_unit_instance_id: str
    transport_unit_instance_id: str
    selecting_player_id: str
    eligible_unit_instance_ids: list[str]


@dataclass(frozen=True, slots=True)
class ForcedFightActivationContext:
    context_id: str
    source_rule_id: str
    trigger_event_id: str
    source_phase: BattlePhaseKind
    source_unit_instance_id: str
    transport_unit_instance_id: str
    selecting_player_id: str
    eligible_unit_instance_ids: tuple[str, ...]

    def __post_init__(self) -> None:
        object.__setattr__(self, "context_id", _validate_identifier("context_id", self.context_id))
        object.__setattr__(
            self,
            "source_rule_id",
            _validate_identifier("source_rule_id", self.source_rule_id),
        )
        object.__setattr__(
            self,
            "trigger_event_id",
            _validate_identifier("trigger_event_id", self.trigger_event_id),
        )
        object.__setattr__(
            self,
            "source_unit_instance_id",
            _validate_identifier(
                "source_unit_instance_id",
                self.source_unit_instance_id,
            ),
        )
        object.__setattr__(
            self,
            "transport_unit_instance_id",
            _validate_identifier(
                "transport_unit_instance_id",
                self.transport_unit_instance_id,
            ),
        )
        object.__setattr__(
            self,
            "selecting_player_id",
            _validate_identifier("selecting_player_id", self.selecting_player_id),
        )
        object.__setattr__(
            self,
            "source_phase",
            battle_phase_kind_from_token(self.source_phase),
        )
        object.__setattr__(
            self,
            "eligible_unit_instance_ids",
            _validate_identifier_tuple(
                "ForcedFightActivationContext eligible_unit_instance_ids",
                self.eligible_unit_instance_ids,
            ),
        )

    def to_payload(self) -> ForcedFightActivationContextPayload:
        return {
            "context_id": self.context_id,
            "source_rule_id": self.source_rule_id,
            "trigger_event_id": self.trigger_event_id,
            "source_phase": self.source_phase.value,
            "source_unit_instance_id": self.source_unit_instance_id,
            "transport_unit_instance_id": self.transport_unit_instance_id,
            "selecting_player_id": self.selecting_player_id,
            "eligible_unit_instance_ids": list(self.eligible_unit_instance_ids),
        }

    @classmethod
    def from_payload(cls, payload: ForcedFightActivationContextPayload) -> Self:
        return cls(
            context_id=payload["context_id"],
            source_rule_id=payload["source_rule_id"],
            trigger_event_id=payload["trigger_event_id"],
            source_phase=battle_phase_kind_from_token(payload["source_phase"]),
            source_unit_instance_id=payload["source_unit_instance_id"],
            transport_unit_instance_id=payload["transport_unit_instance_id"],
            selecting_player_id=payload["selecting_player_id"],
            eligible_unit_instance_ids=tuple(payload["eligible_unit_instance_ids"]),
        )


def _validate_identifier_tuple(field_name: str, values: object) -> tuple[str, ...]:
    if type(values) is not tuple:
        raise GameLifecycleError(f"{field_name} must be a tuple.")
    identifiers = tuple(
        _validate_identifier(f"{field_name} value", value)
        for value in cast(tuple[object, ...], values)
    )
    if not identifiers:
        raise GameLifecycleError(f"{field_name} must not be empty.")
    if len(set(identifiers)) != len(identifiers):
        raise GameLifecycleError(f"{field_name} must not contain duplicates.")
    return tuple(sorted(identifiers))


_validate_identifier = IdentifierValidator(GameLifecycleError)


__all__ = (
    "ForcedFightActivationContext",
    "ForcedFightActivationContextPayload",
)
