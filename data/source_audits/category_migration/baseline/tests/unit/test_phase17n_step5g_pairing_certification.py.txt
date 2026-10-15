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
from warhammer40k_core.rules.source_packages.warhammer_40000_11th.event_companion_primary_scoring_2026_06 import (  # noqa: E501
    engine_implemented_primary_mission_ids,
)

_LAYOUT_INVENTORY_ROWS = event_companion_pairing_layout_inventory_rows()
_LIFECYCLE_CERTIFICATION_ROWS = event_companion_pairing_lifecycle_certification_rows()
_LAYOUT_A_CERTIFICATION_ROWS = tuple(
    row for row in _LIFECYCLE_CERTIFICATION_ROWS if row.layout_variant == "a"
)


def test_phase17n_step5g_inventory_covers_every_source_pairing_and_layout() -> None:
    rows = _LAYOUT_INVENTORY_ROWS
    source_rows = event_primary_mission_matrix_source_rows()
    implemented_ids = engine_implemented_primary_mission_ids()

    assert len(source_rows) == EVENT_COMPANION_PAIRING_COUNT
    assert len(rows) == EVENT_COMPANION_LAYOUT_INVENTORY_COUNT
    assert {row.layout_pair_id for row in rows} == {source.layout_pair_id for source in source_rows}
    assert {row.layout_variant for row in rows} == {"a", "b", "c"}
    assert len({row.layout_id for row in rows}) == EVENT_COMPANION_LAYOUT_INVENTORY_COUNT
    assert all(
        row.attacker_primary_mission_id in implemented_ids
        and row.defender_primary_mission_id in implemented_ids
        for row in rows
    )
    pair_counts = {
        source.layout_pair_id: sum(1 for row in rows if row.layout_pair_id == source.layout_pair_id)
        for source in source_rows
    }
    assert set(pair_counts.values()) == {EVENT_COMPANION_LAYOUT_VARIANT_COUNT}
    source_by_pair = {source.layout_pair_id: source for source in source_rows}
    for row in rows:
        source = source_by_pair[row.layout_pair_id]
        assert row.attacker_force_disposition_id == source.source_left_force_disposition_id
        assert row.defender_force_disposition_id == source.source_right_force_disposition_id
        assert row.attacker_primary_mission_id == source.source_left_primary_mission_id
        assert row.defender_primary_mission_id == source.source_right_primary_mission_id
        assert row.layout_id == (
            f"{row.layout_pair_id}-layout-{('a', 'b', 'c').index(row.layout_variant) + 1}"
        )


def test_phase17n_step5g_lifecycle_rows_cover_every_inventory_layout() -> None:
    lifecycle_rows = _LIFECYCLE_CERTIFICATION_ROWS

    assert len(lifecycle_rows) == EVENT_COMPANION_LIFECYCLE_CERTIFICATION_COUNT
    assert EVENT_COMPANION_LIFECYCLE_CERTIFICATION_COUNT == EVENT_COMPANION_LAYOUT_INVENTORY_COUNT
    assert tuple(row.layout_id for row in lifecycle_rows) == tuple(
        row.layout_id for row in _LAYOUT_INVENTORY_ROWS
    )
    assert tuple(row.layout_variant for row in lifecycle_rows) == tuple(
        row.layout_variant for row in _LAYOUT_INVENTORY_ROWS
    )
    assert {
        (
            row.layout_id,
            row.layout_pair_id,
            row.layout_variant,
            row.attacker_force_disposition_id,
            row.defender_force_disposition_id,
            row.attacker_primary_mission_id,
            row.defender_primary_mission_id,
        )
        for row in lifecycle_rows
    } == {
        (
            row.layout_id,
            row.layout_pair_id,
            row.layout_variant,
            row.attacker_force_disposition_id,
            row.defender_force_disposition_id,
            row.attacker_primary_mission_id,
            row.defender_primary_mission_id,
        )
        for row in _LAYOUT_INVENTORY_ROWS
    }
    scored_mission_ids = {
        mission_id
        for row in lifecycle_rows
        for mission_id in (
            row.attacker_primary_mission_id,
            row.defender_primary_mission_id,
        )
    }
    assert scored_mission_ids == engine_implemented_primary_mission_ids()


def test_phase17n_step5g_every_layout_instantiates_two_sided_scoring_policies() -> None:
    for row in _LAYOUT_INVENTORY_ROWS:
        setup = _setup_for_inventory_row(row)
        policies = mission_scoring_policies_from_setup(setup)
        assert policies.policy_for_player("player-a").primary_scoring_supported, row.layout_id
        assert policies.policy_for_player("player-b").primary_scoring_supported, row.layout_id
        assert setup.primary_mission_id_for_player("player-a") == row.attacker_primary_mission_id
        assert setup.primary_mission_id_for_player("player-b") == row.defender_primary_mission_id


@pytest.mark.parametrize(
    "row",
    _LAYOUT_A_CERTIFICATION_ROWS,
    ids=tuple(row.layout_id for row in _LAYOUT_A_CERTIFICATION_ROWS),
)
@pytest.mark.parametrize("scoring_player_id", SCORING_PLAYER_IDS)
def test_phase17n_step5g_layout_a_scores_through_lifecycle_views_and_replay(
    row: EventCompanionPairingLifecycleCertificationRow,
    scoring_player_id: str,
) -> None:
    assert_pairing_scores_through_lifecycle_restore_views_and_replay(
        row,
        scoring_player_id=scoring_player_id,
    )


def _setup_for_inventory_row(row: EventCompanionPairingLayoutInventoryRow) -> MissionSetup:
    return phase17n_event_setup(
        layout_id=row.layout_id,
        attacker_force_disposition_id=row.attacker_force_disposition_id,
        defender_force_disposition_id=row.defender_force_disposition_id,
    )


def test_phase17n_step5g_capability_rows_are_semantically_executable() -> None:
    row = _LAYOUT_A_CERTIFICATION_ROWS[0]
    session, _initial = pairing_certification_session(row, scoring_player_id="player-a")
    profile = session.support_profile()
    mission_rows = [
        mission_row
        for mission_row in profile["capability_manifest"]["mission_rows"]
        if mission_row["row_kind"] == "mission"
        and mission_row["metadata"].get("primary_mission_id")
        in {row.attacker_primary_mission_id, row.defender_primary_mission_id}
    ]
    assert len(mission_rows) == 2
    for mission_row in mission_rows:
        semantic = next(
            capability
            for capability in mission_row["capabilities"]
            if capability["dimension"] == CapabilityDimension.SEMANTICALLY_EXECUTABLE.value
        )
        assert semantic["status"] == "supported"
        assert mission_row["semantic_execution"] == "executable"
