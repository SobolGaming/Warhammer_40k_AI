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
EVENT_COMPANION_LAYOUT_INVENTORY_COUNT: Final = (
    EVENT_COMPANION_PAIRING_COUNT * EVENT_COMPANION_LAYOUT_VARIANT_COUNT
)
EVENT_COMPANION_LIFECYCLE_CERTIFICATION_COUNT: Final = EVENT_COMPANION_LAYOUT_INVENTORY_COUNT
_LAYOUT_VARIANTS: Final[tuple[LayoutVariant, ...]] = ("a", "b", "c")
_validate_identifier = IdentifierValidator(GameLifecycleError)


def _validated_pairing_identifiers(
    *,
    type_name: str,
    layout_id: str,
    layout_pair_id: str,
    attacker_force_disposition_id: str,
    defender_force_disposition_id: str,
    attacker_primary_mission_id: str,
    defender_primary_mission_id: str,
) -> tuple[str, str, str, str, str, str]:
    return (
        _validate_identifier(f"{type_name} layout_id", layout_id),
        _validate_identifier(f"{type_name} layout_pair_id", layout_pair_id),
        _validate_identifier(
            f"{type_name} attacker_force_disposition_id",
            attacker_force_disposition_id,
        ),
        _validate_identifier(
            f"{type_name} defender_force_disposition_id",
            defender_force_disposition_id,
        ),
        _validate_identifier(
            f"{type_name} attacker_primary_mission_id",
            attacker_primary_mission_id,
        ),
        _validate_identifier(
            f"{type_name} defender_primary_mission_id",
            defender_primary_mission_id,
        ),
    )


def _layout_id_for_variant(layout_pair_id: str, layout_variant: LayoutVariant) -> str:
    return f"{layout_pair_id}-layout-{_LAYOUT_VARIANTS.index(layout_variant) + 1}"


@dataclass(frozen=True, slots=True)
class EventCompanionPairingLayoutInventoryRow:
    """One Event Companion pairing layout in the fail-closed inventory.

    Every A/B/C row is also certified through lifecycle, restore, replay, and
    viewer-scoped adapter coverage.
    """

    layout_id: str
    layout_pair_id: str
    layout_variant: LayoutVariant
    attacker_force_disposition_id: str
    defender_force_disposition_id: str
    attacker_primary_mission_id: str
    defender_primary_mission_id: str

    def __post_init__(self) -> None:
        (
            layout_id,
            layout_pair_id,
            attacker_force_disposition_id,
            defender_force_disposition_id,
            attacker_primary_mission_id,
            defender_primary_mission_id,
        ) = _validated_pairing_identifiers(
            type_name="EventCompanionPairingLayoutInventoryRow",
            layout_id=self.layout_id,
            layout_pair_id=self.layout_pair_id,
            attacker_force_disposition_id=self.attacker_force_disposition_id,
            defender_force_disposition_id=self.defender_force_disposition_id,
            attacker_primary_mission_id=self.attacker_primary_mission_id,
            defender_primary_mission_id=self.defender_primary_mission_id,
        )
        object.__setattr__(self, "layout_id", layout_id)
        object.__setattr__(self, "layout_pair_id", layout_pair_id)
        object.__setattr__(
            self,
            "attacker_force_disposition_id",
            attacker_force_disposition_id,
        )
        object.__setattr__(
            self,
            "defender_force_disposition_id",
            defender_force_disposition_id,
        )
        object.__setattr__(self, "attacker_primary_mission_id", attacker_primary_mission_id)
        object.__setattr__(self, "defender_primary_mission_id", defender_primary_mission_id)
        if self.layout_variant not in _LAYOUT_VARIANTS:
            raise GameLifecycleError(
                "EventCompanionPairingLayoutInventoryRow layout_variant is unsupported."
            )
        expected_layout_id = _layout_id_for_variant(self.layout_pair_id, self.layout_variant)
        if self.layout_id != expected_layout_id:
            raise GameLifecycleError(
                "EventCompanionPairingLayoutInventoryRow layout_id does not match "
                "its pairing variant."
            )


@dataclass(frozen=True, slots=True)
class EventCompanionPairingLifecycleCertificationRow:
    """One A/B/C layout certified through both players' ordinary scoring boundaries."""

    layout_id: str
    layout_pair_id: str
    layout_variant: LayoutVariant
    attacker_force_disposition_id: str
    defender_force_disposition_id: str
    attacker_primary_mission_id: str
    defender_primary_mission_id: str

    def __post_init__(self) -> None:
        (
            layout_id,
            layout_pair_id,
            attacker_force_disposition_id,
            defender_force_disposition_id,
            attacker_primary_mission_id,
            defender_primary_mission_id,
        ) = _validated_pairing_identifiers(
            type_name="EventCompanionPairingLifecycleCertificationRow",
            layout_id=self.layout_id,
            layout_pair_id=self.layout_pair_id,
            attacker_force_disposition_id=self.attacker_force_disposition_id,
            defender_force_disposition_id=self.defender_force_disposition_id,
            attacker_primary_mission_id=self.attacker_primary_mission_id,
            defender_primary_mission_id=self.defender_primary_mission_id,
        )
        object.__setattr__(self, "layout_id", layout_id)
        object.__setattr__(self, "layout_pair_id", layout_pair_id)
        object.__setattr__(
            self,
            "attacker_force_disposition_id",
            attacker_force_disposition_id,
        )
        object.__setattr__(
            self,
            "defender_force_disposition_id",
            defender_force_disposition_id,
        )
        object.__setattr__(self, "attacker_primary_mission_id", attacker_primary_mission_id)
        object.__setattr__(self, "defender_primary_mission_id", defender_primary_mission_id)
        if self.layout_variant not in _LAYOUT_VARIANTS:
            raise GameLifecycleError(
                "EventCompanionPairingLifecycleCertificationRow layout_variant is unsupported."
            )
        expected_layout_id = _layout_id_for_variant(self.layout_pair_id, self.layout_variant)
        if self.layout_id != expected_layout_id:
            raise GameLifecycleError(
                "EventCompanionPairingLifecycleCertificationRow layout_id does not match "
                "its pairing variant."
            )


def event_companion_pairing_layout_inventory_rows() -> tuple[
    EventCompanionPairingLayoutInventoryRow, ...
]:
    """Return the complete 15-pairing / 45-layout fail-closed inventory."""
    implemented_primary_ids = engine_implemented_primary_mission_ids()
    source_rows = event_primary_mission_matrix_source_rows()
    if len(source_rows) != EVENT_COMPANION_PAIRING_COUNT:
        raise GameLifecycleError(
            "Event Companion pairing inventory requires exactly 15 source pairings."
        )
    rows: list[EventCompanionPairingLayoutInventoryRow] = []
    seen_layout_ids: set[str] = set()
    for source_row in source_rows:
        if source_row.source_left_primary_mission_id not in implemented_primary_ids:
            raise GameLifecycleError(
                "Event Companion pairing inventory requires the attacker Primary to be "
                "engine_implemented."
            )
        if source_row.source_right_primary_mission_id not in implemented_primary_ids:
            raise GameLifecycleError(
                "Event Companion pairing inventory requires the defender Primary to be "
                "engine_implemented."
            )
        for layout_variant in _LAYOUT_VARIANTS:
            layout_id = _layout_id_for_variant(source_row.layout_pair_id, layout_variant)
            if layout_id in seen_layout_ids:
                raise GameLifecycleError(
                    "Event Companion pairing inventory layout IDs must be unique."
                )
            seen_layout_ids.add(layout_id)
            rows.append(
                EventCompanionPairingLayoutInventoryRow(
                    layout_id=layout_id,
                    layout_pair_id=source_row.layout_pair_id,
                    layout_variant=layout_variant,
                    attacker_force_disposition_id=source_row.source_left_force_disposition_id,
                    defender_force_disposition_id=source_row.source_right_force_disposition_id,
                    attacker_primary_mission_id=source_row.source_left_primary_mission_id,
                    defender_primary_mission_id=source_row.source_right_primary_mission_id,
                )
            )
    if len(rows) != EVENT_COMPANION_LAYOUT_INVENTORY_COUNT:
        raise GameLifecycleError(
            "Event Companion pairing inventory requires exactly 45 layout variants."
        )
    return tuple(rows)


def event_companion_pairing_lifecycle_certification_rows() -> tuple[
    EventCompanionPairingLifecycleCertificationRow, ...
]:
    """Return all A/B/C rows certified through both ordinary scoring directions."""
    rows = tuple(
        EventCompanionPairingLifecycleCertificationRow(
            layout_id=inventory_row.layout_id,
            layout_pair_id=inventory_row.layout_pair_id,
            layout_variant=inventory_row.layout_variant,
            attacker_force_disposition_id=inventory_row.attacker_force_disposition_id,
            defender_force_disposition_id=inventory_row.defender_force_disposition_id,
            attacker_primary_mission_id=inventory_row.attacker_primary_mission_id,
            defender_primary_mission_id=inventory_row.defender_primary_mission_id,
        )
        for inventory_row in event_companion_pairing_layout_inventory_rows()
    )
    if len(rows) != EVENT_COMPANION_LIFECYCLE_CERTIFICATION_COUNT:
        raise GameLifecycleError(
            "Event Companion pairing lifecycle certification requires exactly 45 A/B/C rows."
        )
    return rows


__all__ = (
    "EVENT_COMPANION_LAYOUT_INVENTORY_COUNT",
    "EVENT_COMPANION_LAYOUT_VARIANT_COUNT",
    "EVENT_COMPANION_LIFECYCLE_CERTIFICATION_COUNT",
    "EVENT_COMPANION_PAIRING_COUNT",
    "EventCompanionPairingLayoutInventoryRow",
    "EventCompanionPairingLifecycleCertificationRow",
    "event_companion_pairing_layout_inventory_rows",
    "event_companion_pairing_lifecycle_certification_rows",
)
