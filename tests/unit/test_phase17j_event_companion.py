from __future__ import annotations

import json
from typing import cast

import pytest

from warhammer40k_core.core.missions import (
    MissionPackDefinition,
    MissionPackDefinitionPayload,
    MissionPackError,
    MissionSourcePackageDefinition,
    MissionSourceStatus,
)
from warhammer40k_core.engine.mission_setup import MissionSetup
from warhammer40k_core.engine.missions import (
    deterministic_tactical_secondary_draw,
    mission_pack_for_id,
    mission_scoring_policy_from_setup,
)
from warhammer40k_core.engine.phase import GameLifecycleError
from warhammer40k_core.engine.scoring import (
    FinalScoringResult,
    ScoringWindowKind,
    ScoringWindowState,
    VictoryPointAward,
    VictoryPointLedger,
    VictoryPointSourceKind,
)
from warhammer40k_core.rules.mission_pack_import import (
    warhammer_event_companion_2026_06_mission_pack,
)
from warhammer40k_core.rules.source_packages.warhammer_40000_11th import (
    event_companion_2026_06 as event_source,
)
from warhammer40k_core.rules.source_packages.warhammer_40000_11th import (
    event_companion_patches,
)


def test_phase17j_event_companion_package_identity_and_payload_round_trip() -> None:
    mission_pack = warhammer_event_companion_2026_06_mission_pack()
    source_package = mission_pack.source_package
    payload = mission_pack.to_payload()
    encoded = json.dumps(payload, sort_keys=True)
    decoded = cast(MissionPackDefinitionPayload, json.loads(encoded))

    assert mission_pack.mission_pack_id == "11e-warhammer-event-companion-2026-06"
    assert source_package.to_payload() == {
        "edition_id": "warhammer_40000_11th",
        "mission_pack_id": "11e-warhammer-event-companion-2026-06",
        "source_package_id": "gw-11e-warhammer-event-companion-v1-0-2026-06",
        "source_title": "Warhammer Event Companion v1.0",
        "source_version": "1.0",
        "source_commit_or_import_hash": source_package.source_commit_or_import_hash,
        "imported_at_schema_version": "core-v2-event-companion-source-v1",
    }
    assert MissionSourcePackageDefinition.from_payload(source_package.to_payload()) == (
        source_package
    )
    assert MissionPackDefinition.from_payload(decoded).to_payload() == payload
    assert "<" not in encoded
    assert "object at 0x" not in encoded

    assert event_source.package_identity().to_payload() == {
        "source_kind": "warhammer_event_companion",
        "document_version": "1.0",
        "event_mode": "warhammer_event",
        "battlefield_size": "44x60_inches",
        "excludes_deployment_cards": True,
        "excludes_twist_cards": True,
        "source_id": "gw-11e-warhammer-event-companion-v1-0-2026-06:package-identity",
    }


def test_phase17j_event_sequence_and_secondary_procedure_are_explicit() -> None:
    sequence = event_source.mission_sequence_descriptor()
    tactical = event_source.tactical_secondary_procedure()
    fixed = event_source.fixed_secondary_procedure()

    assert tuple(step.step_id for step in sequence.steps) == (
        "muster_armies",
        "determine_primary_missions",
        "determine_layout",
        "create_the_battlefield",
        "determine_attacker_and_defender",
        "select_secondary_missions",
        "declare_battle_formations",
        "deploy_armies",
        "redeploy_units",
        "determine_first_turn",
        "resolve_prebattle_rules",
        "begin_battle",
        "end_battle",
        "determine_victor",
    )
    assert sequence.steps[7].actor_policy == "defender_first_alternating"
    assert sequence.steps[8].actor_policy == "attacker_first_alternating"
    assert sequence.steps[9].actor_policy == "roll_off_winner_takes_first"
    assert sequence.steps[10].actor_policy == "first_turn_player_first"
    assert sequence.steps[12].actor_policy == "after_five_battle_rounds_continue_tabled_players"
    assert sequence.steps[13].actor_policy == "battle_ready_then_vp_total_then_draw_if_tied"

    assert tactical.draw_timing == "start_of_command_phase"
    assert tactical.draw_count == 2
    assert tactical.drawn_cards_become_active is True
    assert tactical.once_per_battle_replacement_timing == "end_of_command_phase"
    assert tactical.replacement_cost_cp == 1
    assert tactical.replacement_discard_count == 1
    assert tactical.replacement_draw_count == 1
    assert tactical.end_turn_scoring_order == "active_player_first"
    assert tactical.achieved_discard_requires_vp is True
    assert tactical.own_turn_cp_discard_minimum == 1
    assert tactical.own_turn_cp_reward == 1

    assert fixed.selected_count == 2
    assert fixed.hidden_until_reveal is True
    assert fixed.revealed_face_up is True
    assert fixed.discardable is False
    assert fixed.active_duration == "whole_battle"


def test_phase17j_matrix_layouts_and_setups_are_complete() -> None:
    mission_pack = warhammer_event_companion_2026_06_mission_pack()
    layout_ids = {layout.terrain_layout_id for layout in mission_pack.terrain_layout_templates}
    deployment_map_ids = {
        deployment.deployment_map_id for deployment in mission_pack.deployment_maps
    }
    pool_layout_ids = {entry.terrain_layout_ids[0] for entry in mission_pack.mission_pool_entries}

    assert len(mission_pack.primary_missions) == 25
    assert len(mission_pack.primary_mission_matrix_cells) == 25
    assert all(
        cell.source_status is MissionSourceStatus.IMPLEMENTED
        for cell in mission_pack.primary_mission_matrix_cells
    )
    assert len(layout_ids) == 45
    assert len(deployment_map_ids) == 45
    assert len(mission_pack.mission_pool_entries) == 45
    assert pool_layout_ids == layout_ids
    assert all(
        len(cell.battlefield_layout_ids) == 3 for cell in mission_pack.primary_mission_matrix_cells
    )
    assert all(
        layout_id in layout_ids
        for cell in mission_pack.primary_mission_matrix_cells
        for layout_id in cell.battlefield_layout_ids
    )

    for entry in mission_pack.mission_pool_entries:
        setup = MissionSetup.from_mission_pack(
            mission_pack=mission_pack,
            mission_pool_entry_id=entry.mission_pool_entry_id,
            attacker_player_id="player-alpha",
            defender_player_id="player-beta",
        )
        assert setup.battlefield_width_inches == 60.0
        assert setup.battlefield_depth_inches == 44.0
        assert len(setup.objective_markers) == 5
        assert len(setup.deployment_zones) == 2
        assert setup.terrain_features


def test_phase17j_event_matrix_uses_pdf_source_pairings_not_chapter_approved_order() -> None:
    source_rows = event_source.event_primary_mission_matrix_source_rows()
    matrix = {
        (row.player_force_disposition_id, row.opponent_force_disposition_id): row
        for row in event_source.primary_mission_matrix_rows()
    }

    assert len(source_rows) == 15
    assert len(matrix) == 25
    assert (
        source_rows[10].source_left_force_disposition_id,
        source_rows[10].source_right_force_disposition_id,
        source_rows[10].layout_source_page_start,
    ) == ("disruption", "reconnaissance", 39)
    assert (
        source_rows[11].source_left_force_disposition_id,
        source_rows[11].source_right_force_disposition_id,
        source_rows[11].layout_source_page_start,
    ) == ("disruption", "priority-assets", 42)
    assert (
        source_rows[13].source_left_force_disposition_id,
        source_rows[13].source_right_force_disposition_id,
        source_rows[13].layout_source_page_start,
    ) == ("reconnaissance", "priority-assets", 48)

    assert matrix[("take-and-hold", "disruption")].primary_mission_id == (
        "primary-determined-acquisition"
    )
    assert matrix[("disruption", "take-and-hold")].primary_mission_id == "primary-death-trap"
    assert matrix[("take-and-hold", "priority-assets")].primary_mission_id == (
        "primary-inescapable-dominion"
    )
    assert matrix[("priority-assets", "take-and-hold")].primary_mission_id == (
        "primary-secure-asset"
    )
    assert matrix[("purge-the-foe", "disruption")].primary_mission_id == "primary-punishment"
    assert matrix[("disruption", "purge-the-foe")].primary_mission_id == ("primary-delaying-action")
    assert matrix[("purge-the-foe", "priority-assets")].primary_mission_id == (
        "primary-destroyers-wrath"
    )
    assert matrix[("priority-assets", "purge-the-foe")].primary_mission_id == ("primary-vital-link")
    assert matrix[("disruption", "disruption")].primary_mission_id == "primary-outmaneuver"
    assert matrix[("disruption", "disruption")].primary_mission_name == "Outmanoeuvre"
    assert matrix[("disruption", "reconnaissance")].primary_mission_id == (
        "primary-smoke-and-mirrors"
    )
    assert matrix[("reconnaissance", "disruption")].primary_mission_id == (
        "primary-surveil-the-foe"
    )
    assert matrix[("reconnaissance", "priority-assets")].primary_mission_id == (
        "primary-search-and-scour"
    )
    assert matrix[("priority-assets", "reconnaissance")].primary_mission_id == (
        "primary-vanguard-operation"
    )
    assert matrix[("priority-assets", "priority-assets")].primary_mission_id == ("primary-sabotage")
    assert matrix[("reconnaissance", "disruption")].battlefield_layout_ids == (
        "disruption-vs-reconnaissance-layout-1",
        "disruption-vs-reconnaissance-layout-2",
        "disruption-vs-reconnaissance-layout-3",
    )
    assert matrix[("priority-assets", "disruption")].battlefield_layout_ids == (
        "disruption-vs-priority-assets-layout-1",
        "disruption-vs-priority-assets-layout-2",
        "disruption-vs-priority-assets-layout-3",
    )
    assert matrix[("priority-assets", "reconnaissance")].battlefield_layout_ids == (
        "reconnaissance-vs-priority-assets-layout-1",
        "reconnaissance-vs-priority-assets-layout-2",
        "reconnaissance-vs-priority-assets-layout-3",
    )


def test_phase17j_layout_descriptors_cover_source_pages_and_geometry_roles() -> None:
    descriptors = event_source.layout_descriptor_rows()

    assert len(descriptors) == 45
    assert {descriptor.layout_variant for descriptor in descriptors} == {"a", "b", "c"}
    assert {descriptor.source_page for descriptor in descriptors} == set(range(9, 54))
    assert all(descriptor.battlefield_width_inches == 60.0 for descriptor in descriptors)
    assert all(descriptor.battlefield_depth_inches == 44.0 for descriptor in descriptors)
    assert all(len(descriptor.deployment_zone_polygons) == 2 for descriptor in descriptors)
    assert all(len(descriptor.player_territory_polygons) == 2 for descriptor in descriptors)
    assert all(len(descriptor.objective_points) == 5 for descriptor in descriptors)
    assert all(
        {"dense", "light"} <= {feature.density for feature in descriptor.terrain_features}
        for descriptor in descriptors
    )
    assert all(
        objective.objective_kind in {"attacker_home", "defender_home", "center", "central"}
        for descriptor in descriptors
        for objective in descriptor.objective_points
    )
    assert all(
        descriptor.geometry_extraction_status
        == "layout_identity_source_page_bound_coordinates_pending"
        for descriptor in descriptors
    )
    assert _layout_descriptor("take-and-hold", "disruption", "a").source_page == 15
    assert _layout_descriptor("take-and-hold", "reconnaissance", "a").source_page == 18
    assert _layout_descriptor("take-and-hold", "priority-assets", "a").source_page == 21
    assert _layout_descriptor("disruption", "reconnaissance", "a").source_page == 39
    assert _layout_descriptor("disruption", "priority-assets", "a").source_page == 42
    assert _layout_descriptor("reconnaissance", "priority-assets", "a").source_page == 48
    assert all(
        row.source_status.endswith("layout_identity_coordinate_extraction_pending")
        for row in event_source.battlefield_layout_rows()
    )


def test_phase17j_card_amendments_are_separate_from_faq_patch_rows() -> None:
    amendment_set = event_source.card_amendment_set()
    faq_patches = event_companion_patches.faq_patch_rows()

    assert amendment_set.amendments == ()
    assert amendment_set.source_page == 4
    assert {patch.patch_id for patch in faq_patches} == {
        "faq-operation-marker-removal-requires-card-permission",
        "faq-death-trap-trapped-area-scoring-window",
        "faq-surveil-the-foe-same-turn-marker-removal",
        "faq-vital-link-multiple-central-objectives",
    }
    assert {patch.behavior_descriptor for patch in faq_patches} == {
        "operation_marker_removal_requires_primary_card_permission",
        "death_trap_trapped_area_checked_at_scoring_not_destruction_time",
        "surveil_the_foe_same_turn_marker_removal_allows_scoring",
        "vital_link_multiple_central_objectives_marker_control_allows_cumulative_vp",
    }
    assert all(patch.source_page == 4 for patch in faq_patches)
    assert all(
        patch.source_id.startswith("gw-11e-warhammer-event-companion-v1-0-2026-06:faq:")
        for patch in faq_patches
    )


def test_phase17j_base_size_source_rows_fail_closed_for_noncanonical_shapes() -> None:
    rows = event_source.base_size_source_rows()
    rows_by_kind = {row.base_source_kind: row for row in rows}

    assert len(rows) == 1083
    assert {row.source_page for row in rows} == set(range(55, 94))
    assert len({row.record_id for row in rows}) == len(rows)
    assert {
        "round",
        "oval",
        "hull",
        "small_flying_base",
        "large_flying_base",
        "unique",
    } <= set(rows_by_kind)
    assert rows_by_kind["round"].canonical_base_size is not None
    assert rows_by_kind["oval"].canonical_base_size is not None
    assert rows_by_kind["hull"].canonical_base_size is None
    assert rows_by_kind["small_flying_base"].canonical_base_size is None
    assert rows_by_kind["large_flying_base"].canonical_base_size is None
    assert rows_by_kind["unique"].canonical_base_size is None
    assert rows_by_kind["hull"].geometry_resolution_status.value == (
        "requires_project_geometry_override"
    )
    assert rows_by_kind["small_flying_base"].geometry_resolution_status.value == (
        "requires_project_geometry_override"
    )
    assert rows_by_kind["large_flying_base"].geometry_resolution_status.value == (
        "requires_project_geometry_override"
    )
    assert rows_by_kind["unique"].geometry_resolution_status.value == (
        "requires_event_organizer_override"
    )


def test_phase17j_primary_source_descriptor_rows_do_not_create_placeholder_scoring() -> None:
    descriptor_rows = tuple(
        row
        for row in event_source.primary_mission_rows()
        if row.scoring_kind == "event_companion_primary_source_descriptor_only"
    )

    assert descriptor_rows
    assert all(row.scoring_rules == () for row in descriptor_rows)
    assert "primary-battlefield-dominance" in {row.primary_mission_id for row in descriptor_rows}

    mission_pack = mission_pack_for_id("11e-warhammer-event-companion-2026-06")
    setup = MissionSetup.from_mission_pack(
        mission_pack=mission_pack,
        mission_pool_entry_id="mission-take-and-hold-vs-take-and-hold-layout-1",
        attacker_player_id="player-alpha",
        defender_player_id="player-beta",
    )
    with pytest.raises(GameLifecycleError, match="Unsupported primary mission scoring policy"):
        mission_scoring_policy_from_setup(setup)


def test_phase17j_primary_scoring_coverage_tracks_known_pending_and_missing_rows() -> None:
    primary_rows = {row.primary_mission_id: row for row in event_source.primary_mission_rows()}
    coverage_rows = {
        row.primary_mission_id: row for row in event_source.primary_mission_scoring_coverage_rows()
    }
    status_counts = {
        status: sum(1 for row in coverage_rows.values() if row.status is status)
        for status in event_source.PrimaryMissionScoringCoverageStatus
    }

    assert len(coverage_rows) == 25
    assert status_counts == {
        event_source.PrimaryMissionScoringCoverageStatus.ENGINE_IMPLEMENTED: 3,
        event_source.PrimaryMissionScoringCoverageStatus.SOURCE_KNOWN_ENGINE_PENDING: 8,
        event_source.PrimaryMissionScoringCoverageStatus.AWAITING_SOURCE: 14,
    }
    assert {
        mission_id: len(primary_rows[mission_id].scoring_rules)
        for mission_id in (
            "primary-unstoppable-force",
            "primary-meatgrinder",
            "primary-punishment",
            "primary-consecrate",
            "primary-destroyers-wrath",
            "primary-outmaneuver",
            "primary-delaying-action",
            "primary-smoke-and-mirrors",
            "primary-triangulation",
        )
    } == {
        "primary-unstoppable-force": 4,
        "primary-meatgrinder": 4,
        "primary-punishment": 4,
        "primary-consecrate": 5,
        "primary-destroyers-wrath": 4,
        "primary-outmaneuver": 4,
        "primary-delaying-action": 3,
        "primary-smoke-and-mirrors": 4,
        "primary-triangulation": 5,
    }
    assert primary_rows["primary-meatgrinder"].scoring_kind == (
        "event_companion_primary_source_known_engine_pending"
    )
    assert coverage_rows["primary-unstoppable-force"].needed_work == ()
    assert coverage_rows["primary-battlefield-dominance"].needed_work == (
        "source_primary_scoring_text",
    )
    assert coverage_rows["primary-death-trap"].mission_action_count == 1
    assert coverage_rows["primary-smoke-and-mirrors"].mission_action_count == 1
    assert "engine_primary_action:decoy-objective" in (
        coverage_rows["primary-smoke-and-mirrors"].needed_work
    )
    assert "source_objective_role:expansion_objective" in (
        coverage_rows["primary-delaying-action"].needed_work
    )


def test_phase17j_primary_source_only_actions_are_not_exposed_as_runtime_actions() -> None:
    action_sources = {
        row.mission_action_id: row for row in event_source.primary_mission_action_source_rows()
    }
    mission_pack = warhammer_event_companion_2026_06_mission_pack()

    assert set(action_sources) == {"decoy-objective", "triangulate-objective"}
    assert action_sources["decoy-objective"].to_payload() == {
        "mission_action_id": "decoy-objective",
        "primary_mission_id": "primary-smoke-and-mirrors",
        "name": "Decoy",
        "start_phase": "shooting",
        "start_timing": "shooting_phase_action_start",
        "completion_timing": "turn_end",
        "eligible_unit_policy": "active_player_unit",
        "target_policy": "objective_marker_excluding_home_not_decoy",
        "use_limit": "unlimited_different_objective_per_unit_this_phase",
        "effect_descriptor": "objective_becomes_decoy_if_action_unit_controls_target_at_turn_end",
        "engine_exposure_status": "source_known_engine_pending",
        "source_id": (
            "gw-11e-warhammer-event-companion-v1-0-2026-06:primary-action:decoy-objective"
        ),
    }
    assert action_sources["triangulate-objective"].start_timing == (
        "shooting_phase_action_start_from_battle_round_two"
    )
    with pytest.raises(MissionPackError, match="mission_action_id"):
        mission_pack.mission_action("decoy-objective")
    with pytest.raises(MissionPackError, match="mission_action_id"):
        mission_pack.mission_action("triangulate-objective")


def test_phase17j_source_known_engine_pending_primary_scoring_fails_closed() -> None:
    mission_pack = mission_pack_for_id("11e-warhammer-event-companion-2026-06")
    setup = MissionSetup.from_mission_pack(
        mission_pack=mission_pack,
        mission_pool_entry_id="mission-purge-the-foe-vs-purge-the-foe-layout-1",
        attacker_player_id="player-alpha",
        defender_player_id="player-beta",
    )

    with pytest.raises(GameLifecycleError, match="Unsupported primary scoring rule condition"):
        mission_scoring_policy_from_setup(setup)


def test_phase17j_event_pack_resolves_scoring_and_tactical_draw_by_pack_id() -> None:
    mission_pack = mission_pack_for_id("11e-warhammer-event-companion-2026-06")
    setup = MissionSetup.from_mission_pack(
        mission_pack=mission_pack,
        mission_pool_entry_id="mission-take-and-hold-vs-purge-the-foe-layout-1",
        attacker_player_id="player-alpha",
        defender_player_id="player-beta",
    )
    policy = mission_scoring_policy_from_setup(setup)
    tactical_draw = deterministic_tactical_secondary_draw(
        mission_setup=setup,
        player_id="player-alpha",
        battle_round=1,
        draw_count=2,
    )

    assert policy.mission_pack_id == mission_pack.mission_pack_id
    assert policy.game_length_battle_rounds == 5
    assert policy.primary_vp_cap == 45
    assert policy.secondary_vp_cap == 45
    assert policy.total_vp_cap == 100
    assert len(tactical_draw) == 2

    with pytest.raises(GameLifecycleError):
        mission_pack_for_id("unsupported-pack")


def test_phase17j_final_scoring_uses_event_caps_battle_ready_and_draw_rules() -> None:
    mission_pack = mission_pack_for_id("11e-warhammer-event-companion-2026-06")
    setup = MissionSetup.from_mission_pack(
        mission_pack=mission_pack,
        mission_pool_entry_id="mission-take-and-hold-vs-purge-the-foe-layout-1",
        attacker_player_id="player-alpha",
        defender_player_id="player-beta",
    )
    policy = mission_scoring_policy_from_setup(setup)
    player_alpha_ledger, _ = VictoryPointLedger.initial(player_id="player-alpha").award(
        VictoryPointAward(
            player_id="player-alpha",
            battle_round=5,
            phase="command",
            amount=55,
            source_kind=VictoryPointSourceKind.PRIMARY,
            source_id=setup.primary_mission_id,
            scoring_timing="phase_end",
            metadata={"scoring_rule_id": "phase17j-primary-cap"},
        )
    )
    player_alpha_ledger, _ = player_alpha_ledger.award(
        VictoryPointAward(
            player_id="player-alpha",
            battle_round=5,
            phase="command",
            amount=12,
            source_kind=VictoryPointSourceKind.BATTLE_READY,
            source_id="battle-ready",
            scoring_timing="game_end",
            metadata={"scoring_rule_id": "phase17j-battle-ready-cap"},
        )
    )
    player_beta_ledger, _ = VictoryPointLedger.initial(player_id="player-beta").award(
        VictoryPointAward(
            player_id="player-beta",
            battle_round=5,
            phase="command",
            amount=45,
            source_kind=VictoryPointSourceKind.PRIMARY,
            source_id=setup.primary_mission_id,
            scoring_timing="phase_end",
            metadata={"scoring_rule_id": "phase17j-opponent-primary"},
        )
    )
    player_beta_ledger, _ = player_beta_ledger.award(
        VictoryPointAward(
            player_id="player-beta",
            battle_round=5,
            phase="command",
            amount=10,
            source_kind=VictoryPointSourceKind.BATTLE_READY,
            source_id="battle-ready",
            scoring_timing="game_end",
            metadata={"scoring_rule_id": "phase17j-opponent-battle-ready"},
        )
    )
    result = FinalScoringResult.from_ledgers(
        game_id="phase17j-event-final-scoring",
        battle_round=5,
        policy=policy,
        ledgers=(player_alpha_ledger, player_beta_ledger),
        scoring_windows=_event_final_scoring_windows(
            game_id="phase17j-event-final-scoring",
            battle_round=5,
            policy_source_id=policy.source_id,
        ),
    )

    payload = result.to_payload()
    audit = cast(dict[str, object], payload["scoring_audit"])

    assert payload["winner_player_ids"] == ["player-alpha", "player-beta"]
    assert payload["is_draw"] is True
    assert payload["final_scores"] == [
        {"player_id": "player-alpha", "victory_points": 55},
        {"player_id": "player-beta", "victory_points": 55},
    ]
    assert audit["battle_ready_vp_cap"] == 10


def _layout_descriptor(
    player_force_disposition_id: str,
    opponent_force_disposition_id: str,
    layout_variant: str,
) -> event_source.WarhammerEventLayoutDescriptor:
    for descriptor in event_source.layout_descriptor_rows():
        if (
            descriptor.player_force_disposition_id == player_force_disposition_id
            and descriptor.opponent_force_disposition_id == opponent_force_disposition_id
            and descriptor.layout_variant == layout_variant
        ):
            return descriptor
    raise AssertionError("Layout descriptor was not found.")


def _event_final_scoring_windows(
    *,
    game_id: str,
    battle_round: int,
    policy_source_id: str,
) -> tuple[ScoringWindowState, ...]:
    return (
        ScoringWindowState(
            window_id="phase17j-event-final-round",
            game_id=game_id,
            battle_round=battle_round,
            window_kind=ScoringWindowKind.END_OF_ROUND,
            window="battle_round_end",
            source_id=f"{policy_source_id}:end-of-round",
        ),
        ScoringWindowState(
            window_id="phase17j-event-final-turn-end",
            game_id=game_id,
            battle_round=battle_round,
            window_kind=ScoringWindowKind.END_OF_GAME,
            window="turn_end_round_five_going_second",
            source_id=f"{policy_source_id}:turn-end-round-five",
        ),
        ScoringWindowState(
            window_id="phase17j-event-final-end-battle",
            game_id=game_id,
            battle_round=battle_round,
            window_kind=ScoringWindowKind.END_OF_GAME,
            window="end_of_battle",
            source_id=f"{policy_source_id}:end-of-battle",
        ),
    )
