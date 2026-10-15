from __future__ import annotations

import pytest

from tests.phase17n_primary_mission_helpers import phase17n_event_setup
from tests.phase17n_step5g_pairing_certification_helpers import (
    SCORING_PLAYER_IDS,
    assert_pairing_scores_through_lifecycle_restore_views_and_replay,
    pairing_certification_session,
)
from warhammer40k_core.adapters.capability_manifest import CapabilityDimension
from warhammer40k_core.engine.mission_setup import MissionSetup
from warhammer40k_core.engine.missions import mission_scoring_policies_from_setup
from warhammer40k_core.engine.primary_scoring_pairing_certification import (
    EVENT_COMPANION_LAYOUT_INVENTORY_COUNT,
    EVENT_COMPANION_LAYOUT_VARIANT_COUNT,
    EVENT_COMPANION_LIFECYCLE_CERTIFICATION_COUNT,
    EVENT_COMPANION_PAIRING_COUNT,
    EventCompanionPairingLayoutInventoryRow,
    EventCompanionPairingLifecycleCertificationRow,
    event_companion_pairing_layout_inventory_rows,
    event_companion_pairing_lifecycle_certification_rows,
)
from warhammer40k_core.rules.source_packages.warhammer_40000_11th.event_companion_2026_06 import (
    event_primary_mission_matrix_source_rows,
)
from warhammer40k_core.rules.source_packages.warhammer_40000_11th.event_companion_primary_scoring_2026_06 import (  # noqa: E501 - canonical source module path
    engine_implemented_primary_mission_ids,
)

_LAYOUT_INVENTORY_ROWS = event_companion_pairing_layout_inventory_rows()
_LIFECYCLE_CERTIFICATION_ROWS = event_companion_pairing_lifecycle_certification_rows()
_LAYOUT_A_CERTIFICATION_ROWS = tuple(
    row for row in _LIFECYCLE_CERTIFICATION_ROWS if row.layout_variant == "a"
)


def _setup_for_inventory_row(row: EventCompanionPairingLayoutInventoryRow) -> MissionSetup:
    return phase17n_event_setup(
        layout_id=row.layout_id,
        attacker_force_disposition_id=row.attacker_force_disposition_id,
        defender_force_disposition_id=row.defender_force_disposition_id,
    )


__all__: list[str] = []
__all__ += ["EVENT_COMPANION_LAYOUT_INVENTORY_COUNT", "CapabilityDimension"]
__all__ += ["EVENT_COMPANION_LAYOUT_VARIANT_COUNT"]
__all__ += ["EVENT_COMPANION_LIFECYCLE_CERTIFICATION_COUNT", "EVENT_COMPANION_PAIRING_COUNT"]
__all__ += ["EventCompanionPairingLayoutInventoryRow"]
__all__ += ["EventCompanionPairingLifecycleCertificationRow", "MissionSetup"]
__all__ += ["SCORING_PLAYER_IDS", "_LAYOUT_A_CERTIFICATION_ROWS", "_LAYOUT_INVENTORY_ROWS"]
__all__ += ["_LIFECYCLE_CERTIFICATION_ROWS", "_setup_for_inventory_row"]
__all__ += ["assert_pairing_scores_through_lifecycle_restore_views_and_replay"]
__all__ += ["engine_implemented_primary_mission_ids"]
__all__ += ["event_companion_pairing_layout_inventory_rows"]
__all__ += ["event_companion_pairing_lifecycle_certification_rows"]
__all__ += ["event_primary_mission_matrix_source_rows", "mission_scoring_policies_from_setup"]
__all__ += ["pairing_certification_session", "phase17n_event_setup", "pytest"]
