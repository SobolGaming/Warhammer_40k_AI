from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
from typing import Self, TypedDict, cast

from warhammer40k_core.core.mission_errors import MissionPackError
from warhammer40k_core.core.validation import IdentifierValidator


class MissionSourceStatus(StrEnum):
    IMPLEMENTED = "implemented"
    UNSUPPORTED = "unsupported"
    AWAITING_SOURCE = "awaiting_source"


class ForceDispositionDefinitionPayload(TypedDict):
    force_disposition_id: str
    name: str
    source_id: str


class PrimaryMissionMatrixCellPayload(TypedDict):
    player_force_disposition_id: str
    opponent_force_disposition_id: str
    primary_mission_id: str
    battlefield_layout_ids: list[str]
    source_status: str
    source_id: str


@dataclass(frozen=True, slots=True)
class ForceDispositionDefinition:
    force_disposition_id: str
    name: str
    source_id: str

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "force_disposition_id",
            _validate_unprefixed_identifier(
                "ForceDispositionDefinition force_disposition_id",
                self.force_disposition_id,
                reserved_prefix="force-disposition:",
            ),
        )
        object.__setattr__(
            self,
            "name",
            _validate_identifier("ForceDispositionDefinition name", self.name),
        )
        object.__setattr__(
            self,
            "source_id",
            _validate_identifier("ForceDispositionDefinition source_id", self.source_id),
        )

    def to_payload(self) -> ForceDispositionDefinitionPayload:
        return {
            "force_disposition_id": self.force_disposition_id,
            "name": self.name,
            "source_id": self.source_id,
        }

    @classmethod
    def from_payload(cls, payload: ForceDispositionDefinitionPayload) -> Self:
        return cls(
            force_disposition_id=payload["force_disposition_id"],
            name=payload["name"],
            source_id=payload["source_id"],
        )


@dataclass(frozen=True, slots=True)
class PrimaryMissionMatrixCell:
    player_force_disposition_id: str
    opponent_force_disposition_id: str
    primary_mission_id: str
    battlefield_layout_ids: tuple[str, ...]
    source_status: MissionSourceStatus
    source_id: str

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "player_force_disposition_id",
            _validate_identifier(
                "PrimaryMissionMatrixCell player_force_disposition_id",
                self.player_force_disposition_id,
            ),
        )
        object.__setattr__(
            self,
            "opponent_force_disposition_id",
            _validate_identifier(
                "PrimaryMissionMatrixCell opponent_force_disposition_id",
                self.opponent_force_disposition_id,
            ),
        )
        object.__setattr__(
            self,
            "primary_mission_id",
            _validate_identifier(
                "PrimaryMissionMatrixCell primary_mission_id", self.primary_mission_id
            ),
        )
        object.__setattr__(
            self,
            "battlefield_layout_ids",
            _validate_identifier_tuple(
                "PrimaryMissionMatrixCell battlefield_layout_ids",
                self.battlefield_layout_ids,
                min_length=3,
                sort_values=False,
            ),
        )
        if len(self.battlefield_layout_ids) != 3:
            raise MissionPackError("PrimaryMissionMatrixCell requires exactly three layouts.")
        object.__setattr__(
            self,
            "source_status",
            mission_source_status_from_token(self.source_status),
        )
        object.__setattr__(
            self,
            "source_id",
            _validate_identifier("PrimaryMissionMatrixCell source_id", self.source_id),
        )

    def to_payload(self) -> PrimaryMissionMatrixCellPayload:
        return {
            "player_force_disposition_id": self.player_force_disposition_id,
            "opponent_force_disposition_id": self.opponent_force_disposition_id,
            "primary_mission_id": self.primary_mission_id,
            "battlefield_layout_ids": list(self.battlefield_layout_ids),
            "source_status": self.source_status.value,
            "source_id": self.source_id,
        }

    @classmethod
    def from_payload(cls, payload: PrimaryMissionMatrixCellPayload) -> Self:
        return cls(
            player_force_disposition_id=payload["player_force_disposition_id"],
            opponent_force_disposition_id=payload["opponent_force_disposition_id"],
            primary_mission_id=payload["primary_mission_id"],
            battlefield_layout_ids=tuple(payload["battlefield_layout_ids"]),
            source_status=mission_source_status_from_token(payload["source_status"]),
            source_id=payload["source_id"],
        )


def mission_source_status_from_token(token: object) -> MissionSourceStatus:
    if type(token) is MissionSourceStatus:
        return token
    if type(token) is not str:
        raise MissionPackError("MissionSourceStatus token must be a string.")
    try:
        return MissionSourceStatus(token)
    except ValueError as exc:
        raise MissionPackError(f"Unsupported MissionSourceStatus token: {token}.") from exc


def _validate_unprefixed_identifier(
    field_name: str,
    value: object,
    *,
    reserved_prefix: str,
) -> str:
    identifier = _validate_identifier(field_name, value)
    if identifier.startswith(reserved_prefix):
        raise MissionPackError(f"{field_name} must not include the stable identity prefix.")
    return identifier


def _validate_identifier_tuple(
    field_name: str,
    values: object,
    *,
    min_length: int,
    sort_values: bool,
) -> tuple[str, ...]:
    if type(values) is not tuple:
        raise MissionPackError(f"{field_name} must be a tuple.")
    validated: list[str] = []
    seen: set[str] = set()
    for value in cast(tuple[object, ...], values):
        identifier = _validate_identifier(f"{field_name} value", value)
        if identifier in seen:
            raise MissionPackError(f"{field_name} must not contain duplicates.")
        seen.add(identifier)
        validated.append(identifier)
    if len(validated) < min_length:
        raise MissionPackError(f"{field_name} must contain at least {min_length} values.")
    if sort_values:
        return tuple(sorted(validated))
    return tuple(validated)


_validate_identifier = IdentifierValidator(MissionPackError)
