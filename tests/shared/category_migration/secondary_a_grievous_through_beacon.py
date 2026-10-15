from __future__ import annotations

import pytest

from tests.phase17n_step6g_secondary_certification_helpers import (
    STEP6G_A_GRIEVOUS_THROUGH_BEACON_MISSION_IDS,
    assert_secondary_scores_through_lifecycle_restore_and_views,
    assert_tactical_retain_leaves_card_active_without_transaction,
    step6g_lifecycle_certification_rows,
    step6g_tactical_certification_rows,
)
from warhammer40k_core.engine.secondary_scoring_inventory import (
    SecondaryMissionLifecycleCertificationRow,
)

_LIFECYCLE_ROWS = step6g_lifecycle_certification_rows(STEP6G_A_GRIEVOUS_THROUGH_BEACON_MISSION_IDS)
_TACTICAL_ROWS = step6g_tactical_certification_rows(STEP6G_A_GRIEVOUS_THROUGH_BEACON_MISSION_IDS)


__all__: list[str] = []
__all__ += ["STEP6G_A_GRIEVOUS_THROUGH_BEACON_MISSION_IDS"]
__all__ += ["_LIFECYCLE_ROWS", "_TACTICAL_ROWS", "SecondaryMissionLifecycleCertificationRow"]
__all__ += ["assert_secondary_scores_through_lifecycle_restore_and_views"]
__all__ += ["assert_tactical_retain_leaves_card_active_without_transaction", "pytest"]
__all__ += ["step6g_lifecycle_certification_rows", "step6g_tactical_certification_rows"]
