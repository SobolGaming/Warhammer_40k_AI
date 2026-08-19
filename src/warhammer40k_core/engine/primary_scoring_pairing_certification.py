from __future__ import annotations

from dataclasses import dataclass
from typing import Final, Literal

from warhammer40k_core.core.validation import IdentifierValidator
from warhammer40k_core.engine.phase import GameLifecycleError
from warhammer40k_core.rules.source_packages.warhammer_40000_11th.event_companion_2026_06 import (
    event_primary_mission_matrix_source_rows,
)
from warhammer40k_core.rules.source_packages.warhammer_40000_11th.event_companion_primary_scoring_2026_06 import (  # noqa: E501
    engine_implemented_primary_mission_ids,
)

LayoutVariant = Literal["a", "b", "c"]

EVENT_COMPANION_PAIRING_COUNT: Final = 15
EVENT_COMPANION_LAYOUT_VARIANT_COUNT: Final = 3
EVENT_COMPANION_CERTIFIED_LAYOUT_COUNT: Final = (
    EVENT_COMPANION_PAIRING_COUNT * EVENT_COMPANION_LAYOUT_VARIANT_COUNT
)
_LAYOUT_VARIANTS: Final[tuple[LayoutVariant, ...]] = ("a", "b", "c")
_validate_identifier = IdentifierValidator(GameLifecycleError)


@dataclass(frozen=True, slots=True)
class EventCompanionPairingCertificationRow:
    """One Event Companion Force Disposition pairing layout that Step 5G certifies."""

    layout_id: str
    layout_pair_id: str
    layout_variant: LayoutVariant
    attacker_force_disposition_id: str
    defender_force_disposition_id: str
    attacker_primary_mission_id: str
    defender_primary_mission_id: str

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "layout_id",
            _validate_identifier(
                "EventCompanionPairingCertificationRow layout_id",
                self.layout_id,
            ),
        )
        object.__setattr__(
            self,
            "layout_pair_id",
            _validate_identifier(
                "EventCompanionPairingCertificationRow layout_pair_id",
                self.layout_pair_id,
            ),
        )
        if self.layout_variant not in _LAYOUT_VARIANTS:
            raise GameLifecycleError(
                "EventCompanionPairingCertificationRow layout_variant is unsupported."
            )
        object.__setattr__(
            self,
            "attacker_force_disposition_id",
            _validate_identifier(
                "EventCompanionPairingCertificationRow attacker_force_disposition_id",
                self.attacker_force_disposition_id,
            ),
        )
        object.__setattr__(
            self,
            "defender_force_disposition_id",
            _validate_identifier(
                "EventCompanionPairingCertificationRow defender_force_disposition_id",
                self.defender_force_disposition_id,
            ),
        )
        object.__setattr__(
            self,
            "attacker_primary_mission_id",
            _validate_identifier(
                "EventCompanionPairingCertificationRow attacker_primary_mission_id",
                self.attacker_primary_mission_id,
            ),
        )
        object.__setattr__(
            self,
            "defender_primary_mission_id",
            _validate_identifier(
                "EventCompanionPairingCertificationRow defender_primary_mission_id",
                self.defender_primary_mission_id,
            ),
        )
        expected_layout_id = (
            f"{self.layout_pair_id}-layout-{_LAYOUT_VARIANTS.index(self.layout_variant) + 1}"
        )
        if self.layout_id != expected_layout_id:
            raise GameLifecycleError(
                "EventCompanionPairingCertificationRow layout_id does not match "
                "its pairing variant."
            )


def event_companion_pairing_certification_rows() -> tuple[
    EventCompanionPairingCertificationRow, ...
]:
    """Return the complete 15-pairing / 45-layout Step 5G certification inventory."""
    implemented_primary_ids = engine_implemented_primary_mission_ids()
    source_rows = event_primary_mission_matrix_source_rows()
    if len(source_rows) != EVENT_COMPANION_PAIRING_COUNT:
        raise GameLifecycleError(
            "Event Companion pairing certification requires exactly 15 source pairings."
        )
    rows: list[EventCompanionPairingCertificationRow] = []
    seen_layout_ids: set[str] = set()
    for source_row in source_rows:
        if source_row.source_left_primary_mission_id not in implemented_primary_ids:
            raise GameLifecycleError(
                "Event Companion pairing certification requires the attacker Primary to be "
                "engine_implemented."
            )
        if source_row.source_right_primary_mission_id not in implemented_primary_ids:
            raise GameLifecycleError(
                "Event Companion pairing certification requires the defender Primary to be "
                "engine_implemented."
            )
        for layout_number, layout_variant in enumerate(_LAYOUT_VARIANTS, start=1):
            layout_id = f"{source_row.layout_pair_id}-layout-{layout_number}"
            if layout_id in seen_layout_ids:
                raise GameLifecycleError(
                    "Event Companion pairing certification layout IDs must be unique."
                )
            seen_layout_ids.add(layout_id)
            rows.append(
                EventCompanionPairingCertificationRow(
                    layout_id=layout_id,
                    layout_pair_id=source_row.layout_pair_id,
                    layout_variant=layout_variant,
                    attacker_force_disposition_id=source_row.source_left_force_disposition_id,
                    defender_force_disposition_id=source_row.source_right_force_disposition_id,
                    attacker_primary_mission_id=source_row.source_left_primary_mission_id,
                    defender_primary_mission_id=source_row.source_right_primary_mission_id,
                )
            )
    if len(rows) != EVENT_COMPANION_CERTIFIED_LAYOUT_COUNT:
        raise GameLifecycleError(
            "Event Companion pairing certification requires exactly 45 layout variants."
        )
    return tuple(rows)


__all__ = (
    "EVENT_COMPANION_CERTIFIED_LAYOUT_COUNT",
    "EVENT_COMPANION_LAYOUT_VARIANT_COUNT",
    "EVENT_COMPANION_PAIRING_COUNT",
    "EventCompanionPairingCertificationRow",
    "event_companion_pairing_certification_rows",
)
