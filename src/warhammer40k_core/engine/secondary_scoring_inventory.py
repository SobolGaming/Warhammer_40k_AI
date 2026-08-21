from __future__ import annotations

from dataclasses import dataclass
from typing import Final, Literal, cast

from warhammer40k_core.core.validation import IdentifierValidator
from warhammer40k_core.engine.phase import GameLifecycleError
from warhammer40k_core.rules.source_packages.warhammer_40000_11th.chapter_approved_2026_27 import (
    secondary_mission_rows,
)

SecondaryAvailability = Literal["tactical", "both"]
SecondaryCardMode = Literal["fixed", "tactical"]

SECONDARY_MISSION_COUNT: Final = 18
SECONDARY_CARD_MODE_CERTIFICATION_COUNT: Final = 22
SECONDARY_LIFECYCLE_CERTIFICATION_COUNT: Final = 44
_SCORING_PLAYER_IDS: Final[tuple[str, ...]] = ("player-a", "player-b")
_validate_identifier = IdentifierValidator(GameLifecycleError)

_STATE_BACKED_SECONDARY_MISSION_IDS = frozenset(
    {
        "a-grievous-blow",
        "a-tempting-target",
        "assassination",
        "beacon",
        "behind-enemy-lines",
        "bring-it-down",
        "burden-of-trust",
        "centre-ground",
        "cleanse",
        "defend-stronghold",
        "display-of-might",
        "engage-on-all-fronts",
        "forward-position",
        "no-prisoners",
        "outflank",
        "overwhelming-force",
        "plunder",
        "secure-no-mans-land",
    }
)


@dataclass(frozen=True, slots=True)
class SecondaryMissionInventoryRow:
    secondary_mission_id: str
    availability: SecondaryAvailability
    tournament_fixed_allowed: bool
    modes: tuple[SecondaryCardMode, ...]
    state_backed: bool

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "secondary_mission_id",
            _validate_identifier("secondary_mission_id", self.secondary_mission_id),
        )
        if self.availability not in {"tactical", "both"}:
            raise GameLifecycleError("Secondary inventory availability is unsupported.")
        if type(self.tournament_fixed_allowed) is not bool:
            raise GameLifecycleError("tournament_fixed_allowed must be a bool.")
        if type(self.modes) is not tuple or not self.modes:
            raise GameLifecycleError("Secondary inventory modes must be a non-empty tuple.")
        if any(mode not in {"fixed", "tactical"} for mode in self.modes):
            raise GameLifecycleError("Secondary inventory mode is unsupported.")
        if type(self.state_backed) is not bool:
            raise GameLifecycleError("state_backed must be a bool.")
        if self.availability == "tactical" and self.modes != ("tactical",):
            raise GameLifecycleError("Tactical-only secondaries must certify only tactical mode.")
        if self.availability == "both" and self.modes != ("fixed", "tactical"):
            raise GameLifecycleError("Dual-mode secondaries must certify fixed and tactical.")
        if self.secondary_mission_id not in _STATE_BACKED_SECONDARY_MISSION_IDS:
            raise GameLifecycleError("Secondary inventory row is not state-backed.")
        if not self.state_backed:
            raise GameLifecycleError("Secondary inventory requires state-backed scoring.")


@dataclass(frozen=True, slots=True)
class SecondaryMissionLifecycleCertificationRow:
    secondary_mission_id: str
    mode: SecondaryCardMode
    scoring_player_id: str
    layout_id: str

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "secondary_mission_id",
            _validate_identifier("secondary_mission_id", self.secondary_mission_id),
        )
        if self.mode not in {"fixed", "tactical"}:
            raise GameLifecycleError("Secondary certification mode is unsupported.")
        object.__setattr__(
            self,
            "scoring_player_id",
            _validate_identifier("scoring_player_id", self.scoring_player_id),
        )
        object.__setattr__(self, "layout_id", _validate_identifier("layout_id", self.layout_id))


def canonical_secondary_mission_id(mission_id: str) -> str:
    requested = _validate_identifier("secondary_mission_id", mission_id)
    aliased = requested.replace("_", "-")
    if aliased in _STATE_BACKED_SECONDARY_MISSION_IDS:
        return aliased
    return requested


def secondary_mission_inventory_rows() -> tuple[SecondaryMissionInventoryRow, ...]:
    rows = tuple(
        SecondaryMissionInventoryRow(
            secondary_mission_id=mission.secondary_mission_id,
            availability=_availability(mission.availability),
            tournament_fixed_allowed=mission.tournament_fixed_allowed,
            modes=(("fixed", "tactical") if mission.availability == "both" else ("tactical",)),
            state_backed=True,
        )
        for mission in secondary_mission_rows()
    )
    if len(rows) != SECONDARY_MISSION_COUNT:
        raise GameLifecycleError("Secondary inventory must cover all 18 cards.")
    mode_rows = sum(len(row.modes) for row in rows)
    if mode_rows != SECONDARY_CARD_MODE_CERTIFICATION_COUNT:
        raise GameLifecycleError("Secondary inventory card/mode count drifted.")
    return rows


def secondary_mission_lifecycle_certification_rows(
    *,
    layout_id: str,
) -> tuple[SecondaryMissionLifecycleCertificationRow, ...]:
    requested_layout = _validate_identifier("layout_id", layout_id)
    rows: list[SecondaryMissionLifecycleCertificationRow] = []
    for inventory in secondary_mission_inventory_rows():
        for mode in inventory.modes:
            for player_id in _SCORING_PLAYER_IDS:
                rows.append(
                    SecondaryMissionLifecycleCertificationRow(
                        secondary_mission_id=inventory.secondary_mission_id,
                        mode=mode,
                        scoring_player_id=player_id,
                        layout_id=requested_layout,
                    )
                )
    if len(rows) != SECONDARY_LIFECYCLE_CERTIFICATION_COUNT:
        raise GameLifecycleError("Secondary lifecycle certification count drifted.")
    return tuple(rows)


def _availability(value: str) -> SecondaryAvailability:
    if value not in {"tactical", "both"}:
        raise GameLifecycleError("Secondary source availability is unsupported.")
    return cast(SecondaryAvailability, value)
