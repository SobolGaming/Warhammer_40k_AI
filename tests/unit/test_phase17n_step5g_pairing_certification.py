from __future__ import annotations

from tests.shared.category_migration.phase17n_step5g_pairing_certification import (
    _LAYOUT_A_CERTIFICATION_ROWS,
    _LAYOUT_INVENTORY_ROWS,
    _LIFECYCLE_CERTIFICATION_ROWS,
    EVENT_COMPANION_LAYOUT_INVENTORY_COUNT,
    EVENT_COMPANION_LAYOUT_VARIANT_COUNT,
    EVENT_COMPANION_LIFECYCLE_CERTIFICATION_COUNT,
    EVENT_COMPANION_PAIRING_COUNT,
    SCORING_PLAYER_IDS,
    CapabilityDimension,
    EventCompanionPairingLayoutInventoryRow,
    EventCompanionPairingLifecycleCertificationRow,
    MissionSetup,
    _setup_for_inventory_row,
    assert_pairing_scores_through_lifecycle_restore_views_and_replay,
    engine_implemented_primary_mission_ids,
    event_companion_pairing_layout_inventory_rows,
    event_companion_pairing_lifecycle_certification_rows,
    event_primary_mission_matrix_source_rows,
    mission_scoring_policies_from_setup,
    pairing_certification_session,
    phase17n_event_setup,
    pytest,
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


__all__: list[str] = []
__all__ += ["CapabilityDimension", "EventCompanionPairingLayoutInventoryRow"]
__all__ += ["EventCompanionPairingLifecycleCertificationRow", "MissionSetup"]
__all__ += ["SCORING_PLAYER_IDS", "_LAYOUT_A_CERTIFICATION_ROWS", "_setup_for_inventory_row"]
__all__ += ["assert_pairing_scores_through_lifecycle_restore_views_and_replay"]
__all__ += ["event_companion_pairing_layout_inventory_rows"]
__all__ += ["event_companion_pairing_lifecycle_certification_rows"]
__all__ += ["mission_scoring_policies_from_setup", "pairing_certification_session"]
__all__ += ["phase17n_event_setup", "pytest"]
