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


__all__: list[str] = []
__all__ += ["EVENT_COMPANION_LAYOUT_INVENTORY_COUNT", "EVENT_COMPANION_LAYOUT_VARIANT_COUNT"]
__all__ += ["EVENT_COMPANION_LIFECYCLE_CERTIFICATION_COUNT", "EVENT_COMPANION_PAIRING_COUNT"]
__all__ += ["EventCompanionPairingLayoutInventoryRow", "MissionSetup"]
__all__ += ["_LIFECYCLE_CERTIFICATION_ROWS", "engine_implemented_primary_mission_ids"]
__all__ += ["event_companion_pairing_layout_inventory_rows"]
__all__ += ["event_companion_pairing_lifecycle_certification_rows"]
__all__ += ["event_primary_mission_matrix_source_rows", "phase17n_event_setup"]
