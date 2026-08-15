from __future__ import annotations

from dataclasses import dataclass, replace
from typing import Final, Self, TypedDict, cast

from warhammer40k_core.core.validation import IdentifierValidator
from warhammer40k_core.engine.phase import GameLifecycleError

LOCATE_AND_DENY_CHOICE_KIND: Final = "locate_and_deny_setup"
PUNISHMENT_CHOICE_KIND: Final = "punishment_condemnation"
CONSECRATE_CHOICE_KIND: Final = "consecrate_objective"
SENSOR_SWEEP_CHOICE_KIND: Final = "sensor_sweep_marker_removal"

_SUPPORTED_CHOICE_KINDS: Final = frozenset(
    {
        LOCATE_AND_DENY_CHOICE_KIND,
        PUNISHMENT_CHOICE_KIND,
        CONSECRATE_CHOICE_KIND,
        SENSOR_SWEEP_CHOICE_KIND,
    }
)


class PrimaryMissionChoicePayload(TypedDict):
    game_id: str
    choice_kind: str
    player_id: str
    primary_mission_id: str
    source_descriptor_id: str
    source_rule_id: str
    battle_round: int | None
    phase: str | None
    subject_id: str | None
    source_action_id: str | None
    legal_target_ids: list[str]
    selected_target_ids: list[str]
    evidence_ids: list[str]
    used_fallback_candidates: bool


@dataclass(frozen=True, slots=True)
class PrimaryMissionChoiceData:
    game_id: str
    choice_kind: str
    player_id: str
    primary_mission_id: str
    source_descriptor_id: str
    source_rule_id: str
    battle_round: int | None
    phase: str | None
    subject_id: str | None
    source_action_id: str | None
    legal_target_ids: tuple[str, ...]
    selected_target_ids: tuple[str, ...]
    evidence_ids: tuple[str, ...]
    used_fallback_candidates: bool

    def __post_init__(self) -> None:
        for field_name in (
            "game_id",
            "choice_kind",
            "player_id",
            "primary_mission_id",
            "source_descriptor_id",
            "source_rule_id",
        ):
            object.__setattr__(
                self,
                field_name,
                _identifier(f"Primary mission choice {field_name}", getattr(self, field_name)),
            )
        if self.choice_kind not in _SUPPORTED_CHOICE_KINDS:
            raise GameLifecycleError("Primary mission choice kind is unsupported.")
        battle_round = _optional_positive_int(
            "Primary mission choice battle_round",
            self.battle_round,
        )
        phase = _optional_identifier("Primary mission choice phase", self.phase)
        if (battle_round is None) != (phase is None):
            raise GameLifecycleError(
                "Primary mission choice battle round and phase must be recorded together."
            )
        object.__setattr__(self, "battle_round", battle_round)
        object.__setattr__(self, "phase", phase)
        object.__setattr__(
            self,
            "subject_id",
            _optional_identifier("Primary mission choice subject_id", self.subject_id),
        )
        object.__setattr__(
            self,
            "source_action_id",
            _optional_identifier(
                "Primary mission choice source_action_id",
                self.source_action_id,
            ),
        )
        legal_ids = _identifier_tuple(
            "Primary mission choice legal_target_ids",
            self.legal_target_ids,
        )
        selected_ids = _identifier_tuple(
            "Primary mission choice selected_target_ids",
            self.selected_target_ids,
        )
        if not set(selected_ids) <= set(legal_ids):
            raise GameLifecycleError("Primary mission choice targets are not legal.")
        object.__setattr__(self, "legal_target_ids", legal_ids)
        object.__setattr__(self, "selected_target_ids", selected_ids)
        object.__setattr__(
            self,
            "evidence_ids",
            _identifier_tuple("Primary mission choice evidence_ids", self.evidence_ids),
        )
        if type(self.used_fallback_candidates) is not bool:
            raise GameLifecycleError(
                "Primary mission choice used_fallback_candidates must be a bool."
            )

    def with_selected_targets(self, target_ids: tuple[str, ...]) -> Self:
        return replace(self, selected_target_ids=target_ids)

    def to_payload(self) -> PrimaryMissionChoicePayload:
        return {
            "game_id": self.game_id,
            "choice_kind": self.choice_kind,
            "player_id": self.player_id,
            "primary_mission_id": self.primary_mission_id,
            "source_descriptor_id": self.source_descriptor_id,
            "source_rule_id": self.source_rule_id,
            "battle_round": self.battle_round,
            "phase": self.phase,
            "subject_id": self.subject_id,
            "source_action_id": self.source_action_id,
            "legal_target_ids": list(self.legal_target_ids),
            "selected_target_ids": list(self.selected_target_ids),
            "evidence_ids": list(self.evidence_ids),
            "used_fallback_candidates": self.used_fallback_candidates,
        }

    @classmethod
    def from_payload(cls, payload: object) -> Self:
        raw = _payload_mapping(
            payload,
            label="Primary mission choice",
            keys=tuple(PrimaryMissionChoicePayload.__annotations__),
        )
        return cls(
            game_id=cast(str, raw["game_id"]),
            choice_kind=cast(str, raw["choice_kind"]),
            player_id=cast(str, raw["player_id"]),
            primary_mission_id=cast(str, raw["primary_mission_id"]),
            source_descriptor_id=cast(str, raw["source_descriptor_id"]),
            source_rule_id=cast(str, raw["source_rule_id"]),
            battle_round=cast(int | None, raw["battle_round"]),
            phase=cast(str | None, raw["phase"]),
            subject_id=cast(str | None, raw["subject_id"]),
            source_action_id=cast(str | None, raw["source_action_id"]),
            legal_target_ids=_payload_identifier_tuple(
                raw["legal_target_ids"],
                "Primary mission choice legal_target_ids",
            ),
            selected_target_ids=_payload_identifier_tuple(
                raw["selected_target_ids"],
                "Primary mission choice selected_target_ids",
            ),
            evidence_ids=_payload_identifier_tuple(
                raw["evidence_ids"],
                "Primary mission choice evidence_ids",
            ),
            used_fallback_candidates=cast(bool, raw["used_fallback_candidates"]),
        )


def _payload_mapping(
    payload: object,
    *,
    label: str,
    keys: tuple[str, ...],
) -> dict[str, object]:
    if type(payload) is not dict:
        raise GameLifecycleError(f"{label} payload must be an object.")
    raw = cast(dict[str, object], payload)
    missing = tuple(key for key in keys if key not in raw)
    if missing:
        raise GameLifecycleError(f"{label} payload is missing field: {missing[0]}.")
    unexpected = tuple(sorted(set(raw).difference(keys)))
    if unexpected:
        raise GameLifecycleError(f"{label} payload has unexpected field: {unexpected[0]}.")
    return raw


def _payload_identifier_tuple(value: object, label: str) -> tuple[str, ...]:
    if type(value) is not list:
        raise GameLifecycleError(f"{label} must be a list.")
    return tuple(cast(list[str], value))


def _identifier_tuple(label: str, value: object) -> tuple[str, ...]:
    if type(value) is not tuple:
        raise GameLifecycleError(f"{label} must be a tuple.")
    identifiers = tuple(
        _identifier(f"{label} value", item) for item in cast(tuple[object, ...], value)
    )
    if len(identifiers) != len(set(identifiers)):
        raise GameLifecycleError(f"{label} must not contain duplicates.")
    return tuple(sorted(identifiers))


def _optional_identifier(label: str, value: object) -> str | None:
    if value is None:
        return None
    return _identifier(label, value)


def _optional_positive_int(label: str, value: object) -> int | None:
    if value is None:
        return None
    if type(value) is not int or value < 1:
        raise GameLifecycleError(f"{label} must be a positive integer.")
    return value


_identifier = IdentifierValidator(GameLifecycleError)


__all__ = (
    "CONSECRATE_CHOICE_KIND",
    "LOCATE_AND_DENY_CHOICE_KIND",
    "PUNISHMENT_CHOICE_KIND",
    "SENSOR_SWEEP_CHOICE_KIND",
    "PrimaryMissionChoiceData",
    "PrimaryMissionChoicePayload",
)
