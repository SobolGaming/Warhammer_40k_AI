from __future__ import annotations

import json
from typing import cast

import pytest

from warhammer40k_core.core.missions import (
    MissionPackDefinition,
    MissionPackDefinitionPayload,
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
    )
    assert sequence.steps[7].actor_policy == "defender_first_alternating"
    assert sequence.steps[8].actor_policy == "attacker_first_alternating"
    assert sequence.steps[9].actor_policy == "roll_off_winner_takes_first"
    assert sequence.steps[10].actor_policy == "first_turn_player_first"

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


def test_phase17j_card_amendments_are_separate_from_faq_patch_rows() -> None:
    amendment_set = event_source.card_amendment_set()
    faq_patches = event_companion_patches.faq_patch_rows()

    assert amendment_set.amendments == ()
    assert amendment_set.source_page == 4
    assert {patch.patch_id for patch in faq_patches} == {
        "faq-operation-markers-removed-when-action-interrupted",
        "faq-death-trap-booby-trap-marker-removal",
        "faq-surveil-the-foe-marker-control-window",
        "faq-vital-link-vp-limit",
    }
    assert all(patch.source_page == 4 for patch in faq_patches)
    assert all(
        patch.source_id.startswith("gw-11e-warhammer-event-companion-v1-0-2026-06:faq:")
        for patch in faq_patches
    )


def test_phase17j_base_size_source_rows_fail_closed_for_noncanonical_shapes() -> None:
    rows = event_source.base_size_source_rows()
    rows_by_kind = {row.base_source_kind: row for row in rows}

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
