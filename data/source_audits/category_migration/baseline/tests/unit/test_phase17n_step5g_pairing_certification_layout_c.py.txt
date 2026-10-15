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

_LAYOUT_C_CERTIFICATION_ROWS = tuple(
    row
    for row in event_companion_pairing_lifecycle_certification_rows()
    if row.layout_variant == "c"
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
