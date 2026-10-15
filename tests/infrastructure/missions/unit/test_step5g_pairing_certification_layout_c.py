from __future__ import annotations

from tests.shared.category_migration.phase17n_step5g_pairing_certification_layout_c import (
    _LAYOUT_C_CERTIFICATION_ROWS,
    SCORING_PLAYER_IDS,
    EventCompanionPairingLifecycleCertificationRow,
    assert_pairing_scores_through_lifecycle_restore_views_and_replay,
    event_companion_pairing_lifecycle_certification_rows,
    pytest,
)


@pytest.mark.parametrize(
    "row",
    _LAYOUT_C_CERTIFICATION_ROWS,
    ids=tuple(row.layout_id for row in _LAYOUT_C_CERTIFICATION_ROWS),
)
@pytest.mark.parametrize("scoring_player_id", SCORING_PLAYER_IDS)
def test_phase17n_step5g_layout_c_scores_through_lifecycle_views_and_replay(
    row: EventCompanionPairingLifecycleCertificationRow,
    scoring_player_id: str,
) -> None:
    assert_pairing_scores_through_lifecycle_restore_views_and_replay(
        row,
        scoring_player_id=scoring_player_id,
    )


__all__: list[str] = []
__all__ += ["event_companion_pairing_lifecycle_certification_rows"]
