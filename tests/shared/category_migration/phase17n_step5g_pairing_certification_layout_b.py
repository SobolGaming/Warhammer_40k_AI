from __future__ import annotations

import pytest

from tests.phase17n_step5g_pairing_certification_helpers import (
    SCORING_PLAYER_IDS,
    assert_pairing_scores_through_lifecycle_restore_views_and_replay,
)
from warhammer40k_core.engine.primary_scoring_pairing_certification import (
    EventCompanionPairingLifecycleCertificationRow,
    event_companion_pairing_lifecycle_certification_rows,
)

_LAYOUT_B_CERTIFICATION_ROWS = tuple(
    row
    for row in event_companion_pairing_lifecycle_certification_rows()
    if row.layout_variant == "b"
)


__all__: list[str] = []
__all__ += ["SCORING_PLAYER_IDS", "EventCompanionPairingLifecycleCertificationRow"]
__all__ += ["_LAYOUT_B_CERTIFICATION_ROWS"]
__all__ += ["assert_pairing_scores_through_lifecycle_restore_views_and_replay"]
__all__ += ["event_companion_pairing_lifecycle_certification_rows", "pytest"]
