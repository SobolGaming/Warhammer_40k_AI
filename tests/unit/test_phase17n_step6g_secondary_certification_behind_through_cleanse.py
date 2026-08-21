from __future__ import annotations

import pytest
from tests.phase17n_step6g_secondary_certification_helpers import (
    STEP6G_BEHIND_THROUGH_CLEANSE_MISSION_IDS,
    assert_secondary_scores_through_lifecycle_restore_and_views,
    assert_tactical_retain_leaves_card_active_without_transaction,
    step6g_lifecycle_certification_rows,
    step6g_tactical_certification_rows,
)

from warhammer40k_core.engine.secondary_scoring_inventory import (
    SecondaryMissionLifecycleCertificationRow,
)

_LIFECYCLE_ROWS = step6g_lifecycle_certification_rows(STEP6G_BEHIND_THROUGH_CLEANSE_MISSION_IDS)
_TACTICAL_ROWS = step6g_tactical_certification_rows(STEP6G_BEHIND_THROUGH_CLEANSE_MISSION_IDS)


@pytest.mark.parametrize(
    "row",
    _LIFECYCLE_ROWS,
    ids=tuple(
        f"{row.secondary_mission_id}:{row.mode}:{row.scoring_player_id}" for row in _LIFECYCLE_ROWS
    ),
)
def test_phase17n_step6g_secondary_scores_through_lifecycle_restore_and_views(
    row: SecondaryMissionLifecycleCertificationRow,
) -> None:
    assert_secondary_scores_through_lifecycle_restore_and_views(row)


@pytest.mark.parametrize(
    "row",
    _TACTICAL_ROWS,
    ids=tuple(
        f"{row.secondary_mission_id}:retain:{row.scoring_player_id}" for row in _TACTICAL_ROWS
    ),
)
def test_phase17n_step6g_tactical_retain_leaves_card_active_without_transaction(
    row: SecondaryMissionLifecycleCertificationRow,
) -> None:
    assert_tactical_retain_leaves_card_active_without_transaction(row)
