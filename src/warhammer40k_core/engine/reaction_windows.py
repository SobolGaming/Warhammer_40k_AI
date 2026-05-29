from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
from typing import Self, TypedDict

from warhammer40k_core.core.ruleset_descriptor import (
    BattlePhaseKind,
    battle_phase_kind_from_token,
)


class ReactionWindowError(ValueError):
    """Raised when a reaction timing window violates CORE V2 invariants."""


class ReactionWindowKind(StrEnum):
    AFTER_UNIT_LOSES_WOUNDS = "after_unit_loses_wounds"
    AFTER_ATTACKS_RESOLVED = "after_attacks_resolved"
    RULE_TRIGGER = "rule_trigger"


class ReactionWindowPayload(TypedDict):
    phase: str
    window_kind: str
    source_step: str | None
    source_event_id: str | None


@dataclass(frozen=True, slots=True)
class ReactionWindow:
    phase: BattlePhaseKind
    window_kind: ReactionWindowKind
    source_step: str | None = None
    source_event_id: str | None = None

    def __post_init__(self) -> None:
        object.__setattr__(self, "phase", battle_phase_kind_from_token(self.phase))
        object.__setattr__(self, "window_kind", reaction_window_kind_from_token(self.window_kind))
        object.__setattr__(
            self,
            "source_step",
            _validate_optional_identifier("ReactionWindow source_step", self.source_step),
        )
        object.__setattr__(
            self,
            "source_event_id",
            _validate_optional_identifier("ReactionWindow source_event_id", self.source_event_id),
        )

    def to_payload(self) -> ReactionWindowPayload:
        return {
            "phase": self.phase.value,
            "window_kind": self.window_kind.value,
            "source_step": self.source_step,
            "source_event_id": self.source_event_id,
        }

    @classmethod
    def from_payload(cls, payload: ReactionWindowPayload) -> Self:
        return cls(
            phase=battle_phase_kind_from_token(payload["phase"]),
            window_kind=reaction_window_kind_from_token(payload["window_kind"]),
            source_step=payload["source_step"],
            source_event_id=payload["source_event_id"],
        )


def reaction_window_kind_from_token(token: object) -> ReactionWindowKind:
    if type(token) is ReactionWindowKind:
        return token
    if type(token) is not str:
        raise ReactionWindowError("ReactionWindowKind token must be a string.")
    try:
        return ReactionWindowKind(token)
    except ValueError as exc:
        raise ReactionWindowError(f"Unsupported ReactionWindowKind token: {token}.") from exc


def _validate_optional_identifier(field_name: str, value: object | None) -> str | None:
    if value is None:
        return None
    if type(value) is not str:
        raise ReactionWindowError(f"{field_name} must be a string.")
    stripped = value.strip()
    if not stripped:
        raise ReactionWindowError(f"{field_name} must not be empty.")
    return stripped
