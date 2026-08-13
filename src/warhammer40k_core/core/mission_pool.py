from __future__ import annotations

from dataclasses import dataclass
from typing import Self, TypedDict, cast

from warhammer40k_core.core.mission_errors import MissionPackError
from warhammer40k_core.core.validation import IdentifierValidator


class MissionPoolEntryPayload(TypedDict):
    mission_pool_entry_id: str
    player_force_disposition_id: str
    opponent_force_disposition_id: str
    player_primary_mission_id: str
    opponent_primary_mission_id: str
    deployment_map_id: str
    terrain_layout_ids: list[str]
    source_id: str


@dataclass(frozen=True, slots=True)
class MissionPoolEntry:
    mission_pool_entry_id: str
    player_force_disposition_id: str
    opponent_force_disposition_id: str
    player_primary_mission_id: str
    opponent_primary_mission_id: str
    deployment_map_id: str
    terrain_layout_ids: tuple[str, ...]
    source_id: str

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "mission_pool_entry_id",
            _validate_unprefixed_identifier(
                "MissionPoolEntry mission_pool_entry_id",
                self.mission_pool_entry_id,
                reserved_prefix="mission-pool-entry:",
            ),
        )
        object.__setattr__(
            self,
            "player_force_disposition_id",
            _validate_identifier(
                "MissionPoolEntry player_force_disposition_id",
                self.player_force_disposition_id,
            ),
        )
        object.__setattr__(
            self,
            "opponent_force_disposition_id",
            _validate_identifier(
                "MissionPoolEntry opponent_force_disposition_id",
                self.opponent_force_disposition_id,
            ),
        )
        object.__setattr__(
            self,
            "player_primary_mission_id",
            _validate_identifier(
                "MissionPoolEntry player_primary_mission_id",
                self.player_primary_mission_id,
            ),
        )
        object.__setattr__(
            self,
            "opponent_primary_mission_id",
            _validate_identifier(
                "MissionPoolEntry opponent_primary_mission_id",
                self.opponent_primary_mission_id,
            ),
        )
        object.__setattr__(
            self,
            "deployment_map_id",
            _validate_identifier("MissionPoolEntry deployment_map_id", self.deployment_map_id),
        )
        object.__setattr__(
            self,
            "terrain_layout_ids",
            _validate_identifier_tuple(
                "MissionPoolEntry terrain_layout_ids",
                self.terrain_layout_ids,
                min_length=1,
                sort_values=False,
            ),
        )
        object.__setattr__(
            self,
            "source_id",
            _validate_identifier("MissionPoolEntry source_id", self.source_id),
        )

    def to_payload(self) -> MissionPoolEntryPayload:
        return {
            "mission_pool_entry_id": self.mission_pool_entry_id,
            "player_force_disposition_id": self.player_force_disposition_id,
            "opponent_force_disposition_id": self.opponent_force_disposition_id,
            "player_primary_mission_id": self.player_primary_mission_id,
            "opponent_primary_mission_id": self.opponent_primary_mission_id,
            "deployment_map_id": self.deployment_map_id,
            "terrain_layout_ids": list(self.terrain_layout_ids),
            "source_id": self.source_id,
        }

    @classmethod
    def from_payload(cls, payload: MissionPoolEntryPayload) -> Self:
        return cls(
            mission_pool_entry_id=payload["mission_pool_entry_id"],
            player_force_disposition_id=payload["player_force_disposition_id"],
            opponent_force_disposition_id=payload["opponent_force_disposition_id"],
            player_primary_mission_id=payload["player_primary_mission_id"],
            opponent_primary_mission_id=payload["opponent_primary_mission_id"],
            deployment_map_id=payload["deployment_map_id"],
            terrain_layout_ids=tuple(payload["terrain_layout_ids"]),
            source_id=payload["source_id"],
        )


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
