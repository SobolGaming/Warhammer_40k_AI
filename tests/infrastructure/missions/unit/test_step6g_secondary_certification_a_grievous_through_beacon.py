from __future__ import annotations

from tests.shared.category_migration.secondary_a_grievous_through_beacon import (
    _LIFECYCLE_ROWS,
    _TACTICAL_ROWS,
    STEP6G_A_GRIEVOUS_THROUGH_BEACON_MISSION_IDS,
    SecondaryMissionLifecycleCertificationRow,
    assert_secondary_scores_through_lifecycle_restore_and_views,
    assert_tactical_retain_leaves_card_active_without_transaction,
    pytest,
    step6g_lifecycle_certification_rows,
    step6g_tactical_certification_rows,
)


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


__all__: list[str] = []
__all__ += ["STEP6G_A_GRIEVOUS_THROUGH_BEACON_MISSION_IDS", "step6g_lifecycle_certification_rows"]
__all__ += ["step6g_tactical_certification_rows"]
