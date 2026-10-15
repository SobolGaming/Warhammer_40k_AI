from __future__ import annotations

from typing import Any, cast

from tests.shared.category_migration.phase17j_event_companion import (
    BattlefieldLayoutDefinition,
    BenefitOfCoverResult,
    Callable,
    CircularBase,
    Counter,
    CoverSourceReason,
    DeploymentZonePoint,
    DeploymentZonePolygon,
    DeploymentZoneShape,
    FinalScoringResult,
    GameLifecycleError,
    LineOfSightPolicy,
    MissionPackDefinition,
    MissionPackDefinitionPayload,
    MissionPackError,
    MissionSetup,
    MissionSetupError,
    MissionSourcePackageDefinition,
    MissionSourceStatus,
    Model,
    ModelVolume,
    ObjectiveMarkerDefinitionPayload,
    ObjectiveMarkerRole,
    Path,
    Pose,
    RulesetDescriptor,
    ScoringWindowKind,
    ScoringWindowState,
    TerrainAreaClassification,
    TerrainAreaCoverSourceRecord,
    TerrainAreaLocalTransform,
    TerrainDisplayPoint,
    TerrainVisibilityContext,
    VictoryPointAward,
    VictoryPointLedger,
    VictoryPointSourceKind,
    VisibilityBlockerKind,
    _event_final_scoring_windows,
    _layout_descriptor,
    _meatgrinder_artifact_layouts,
    _shape_polygons,
    _source_base_source_kind_and_geometry,
    _source_deployment_zone_layout_edges,
    _source_deployment_zone_layout_template_id,
    _source_deployment_zone_layout_template_id_from_number,
    _source_deployment_zone_template_base_shape,
    _source_layout_number_from_layout_id,
    _source_matrix_row,
    _source_rectangle_with_quarter_circle_cutout_vertices,
    _terrain_display_points,
    deterministic_tactical_secondary_draw,
    event_companion_base_size_rows,
    event_companion_patches,
    event_layouts,
    event_no_mans_land_shape,
    event_primary_scoring,
    event_source,
    event_territory_vertices,
    hashlib,
    importlib,
    json,
    july_rules_updates_2026_07,
    math,
    mission_action_policies,
    mission_pack_for_id,
    mission_scoring_policies_from_setup,
    model_within_solid_terrain,
    msgspec,
    objective_marker_role_from_token,
    pairwise,
    permutations,
    polygon_overlap_area,
    pytest,
    replace,
    shapely_backend,
    subprocess,
    sys,
    terrain_area_classifications_by_suffix,
    terrain_area_visibility,
    terrain_feature_placements_from_specs,
    terrain_visibility_areas_from_placements,
    validate_mission_setup_source_layout,
    visibility_polygon_within_union,
    warhammer_event_companion_2026_07_mission_pack,
)
from tests.shared.repository_root import REPOSITORY_ROOT


def test_phase17n_light_corner_wall_joints_follow_source_image_registration() -> None:
    repository_root = REPOSITORY_ROOT
    extraction_payload = json.loads(
        (
            repository_root
            / "data/source_audits/event_companion_2026_06"
            / "phase17n_purge_the_foe_meatgrinder_pages_24_26_extraction.json"
        ).read_text(encoding="utf-8")
    )
    artifact = event_layouts.battlefield_artifact()
    archetypes_by_xref = {
        archetype.source_assets[0].source_pdf_image_xref: archetype
        for archetype in artifact.feature_archetypes
        if archetype.archetype_id.startswith("light-corner-")
    }

    assert set(archetypes_by_xref) == {5478, 5480, 5482, 5484}
    for archetype in archetypes_by_xref.values():
        minimum_x = min(point.x_inches for point in archetype.rules_footprint_polygon)
        maximum_x = max(point.x_inches for point in archetype.rules_footprint_polygon)
        minimum_y = min(point.y_inches for point in archetype.rules_footprint_polygon)
        maximum_y = max(point.y_inches for point in archetype.rules_footprint_polygon)
        arm_thickness = min(maximum_x - minimum_x, maximum_y - minimum_y) * 0.35
        walls = {wall.wall_id: wall for wall in archetype.walls}
        assert math.isclose(
            walls["long-solid-arm"].center_y_inches,
            minimum_y + (arm_thickness / 2.0),
            rel_tol=0.0,
            abs_tol=1e-9,
        )
        assert math.isclose(
            walls["short-solid-arm"].center_x_inches,
            minimum_x + (arm_thickness / 2.0),
            rel_tol=0.0,
            abs_tol=1e-9,
        )

    mission_pack = warhammer_event_companion_2026_07_mission_pack()
    checked_component_ids: set[str] = set()
    for source_layout in extraction_payload["layouts"]:
        layout_id = source_layout["layout_id"]
        mission_pool_entry = next(
            entry
            for entry in mission_pack.mission_pool_entries
            if layout_id in entry.terrain_layout_ids
        )
        setup = MissionSetup.from_mission_pack(
            mission_pack=mission_pack,
            mission_pool_entry_id=mission_pool_entry.mission_pool_entry_id,
            attacker_player_id="player-alpha",
            attacker_force_disposition_id=mission_pool_entry.player_force_disposition_id,
            defender_player_id="player-beta",
            defender_force_disposition_id=mission_pool_entry.opponent_force_disposition_id,
        )
        features_by_id = {feature.feature_id: feature for feature in setup.terrain_features}
        for source_component in source_layout["terrain_components"]:
            area_index = int(source_component["terrain_area_id"].rsplit("-", maxsplit=1)[-1])
            if area_index > 8:
                continue
            source_image = source_component["source_image"]
            if source_image["xref"] not in archetypes_by_xref:
                continue
            modeled_joint = features_by_id[
                source_component["component_id"]
            ].rules_footprint_polygon[0]
            source_joint_x, source_joint_y = source_image[
                "battlefield_quad_inches_top_left_top_right_bottom_right_bottom_left"
            ][3]
            assert (
                math.dist(
                    (modeled_joint.x_inches, modeled_joint.y_inches),
                    (source_joint_x, source_joint_y),
                )
                <= 0.85
            )
            checked_component_ids.add(source_component["component_id"])

    assert len(checked_component_ids) == 12


def test_phase17n_battlefield_builder_reproduces_committed_artifact() -> None:
    builder_geometry = importlib.import_module("tools.event_companion_battlefield_builder_geometry")
    vertices = ((0.0, 0.0), (2.0, 0.0), (2.0, 1.0), (0.0, 1.0))
    pose = builder_geometry.AreaPose(1.0, 1.0, 0.0, "identity", 0.0, 0)
    polygon_for_pose = builder_geometry.area_polygon
    polygon_for_pose.cache_clear()
    first = polygon_for_pose(vertices, pose)
    assert polygon_for_pose(vertices, pose) is first
    assert polygon_for_pose.cache_info().hits == 1
    assert polygon_for_pose.cache_info().maxsize == 4096
    for candidate in (
        pose,
        replace(pose, anchor_x=2.5),
        replace(pose, anchor_x=4.0),
        replace(pose, anchor_x=-0.5),
        replace(pose, rotation=90.0),
        replace(pose, local_transform="mirror_y_axis"),
    ):
        cached = polygon_for_pose(vertices, candidate)
        assert cached.wkb == polygon_for_pose.__wrapped__(vertices, candidate).wkb
    with pytest.raises(ValueError, match="Unsupported terrain-area local transform"):
        polygon_for_pose(vertices, replace(pose, local_transform="unsupported"))
    with pytest.raises(ValueError, match="invalid polygon"):
        polygon_for_pose(((0.0, 0.0), (0.0, 0.0), (0.0, 0.0)), pose)

    # Exercise overlaps, contact gaps, board violations, changed contact sets,
    # and a changed pose against the original uncached calculation.
    for second_pose in (replace(pose, anchor_x=2.5), replace(pose, anchor_x=4.0)):
        second = polygon_for_pose(vertices, second_pose)
        outside = polygon_for_pose(vertices, replace(pose, anchor_x=-0.5))
        polygons = {"a": first, "b": second, "c": outside}
        for contacts in (frozenset[frozenset[str]](), frozenset({frozenset({"a", "b"})})):
            overlaps: list[float] = []
            gaps: list[float] = []
            for first_id, second_id in (("a", "b"), ("a", "c"), ("b", "c")):
                left, right = polygons[first_id], polygons[second_id]
                overlap = left.intersection(right).area
                if overlap > 1e-6:
                    overlaps.append(overlap)
                if frozenset((first_id, second_id)) in contacts:
                    gap = max(0.0, left.distance(right) - 0.05)
                    if gap > 1e-6:
                        gaps.append(gap)
            board = builder_geometry.box(0.0, 0.0, 44.0, 60.0)
            outside_areas = [polygon.difference(board).area for polygon in polygons.values()]
            outside_areas = [area for area in outside_areas if area > 1e-6]
            expected = (
                len(overlaps),
                round(sum(overlaps), 9),
                len(gaps),
                round(sum(gaps), 9),
                len(outside_areas),
                round(sum(outside_areas), 9),
            )
            assert builder_geometry._geometry_score(polygons, contact_pairs=contacts) == expected
            assert builder_geometry._geometry_score(polygons, contact_pairs=contacts) == expected
    assert builder_geometry._pair_geometry.cache_info().maxsize == 65536
    assert builder_geometry._outside_area.cache_info().maxsize == 4096

    repository_root = REPOSITORY_ROOT
    builder_path = repository_root / "tools/build_event_companion_battlefields.py"
    artifact_path = (
        repository_root
        / "src/warhammer40k_core/rules/source_packages/warhammer_40000_11th"
        / "event_companion_layouts_2026_06/artifacts"
        / "event-companion-battlefields.json"
    )
    modified_at_before_check = artifact_path.stat().st_mtime_ns
    result = subprocess.run(
        [
            sys.executable,
            str(builder_path),
            "--check",
        ],
        cwd=repository_root,
        check=False,
        capture_output=True,
        text=True,
    )

    assert result.returncode == 0, result.stdout + result.stderr
    assert artifact_path.stat().st_mtime_ns == modified_at_before_check


def test_phase17n_battlefield_builder_rejects_stale_output_without_writing(tmp_path: Path) -> None:
    repository_root = REPOSITORY_ROOT
    builder_path = repository_root / "tools/build_event_companion_battlefields.py"
    extraction_path = (
        repository_root
        / "data/source_audits/event_companion_2026_06"
        / "phase17n_event_companion_battlefields_pages_9_53_extraction.json"
    )
    artifact_path = (
        repository_root
        / "src/warhammer40k_core/rules/source_packages/warhammer_40000_11th"
        / "event_companion_layouts_2026_06/artifacts"
        / "event-companion-battlefields.json"
    )
    stale_output = tmp_path / "stale-battlefields.json"
    stale_output.write_bytes(artifact_path.read_bytes() + b"\n")
    stale_bytes = stale_output.read_bytes()
    stale_result = subprocess.run(
        [
            sys.executable,
            str(builder_path),
            str(extraction_path),
            str(stale_output),
            "--check",
        ],
        cwd=repository_root,
        check=False,
        capture_output=True,
        text=True,
    )
    assert stale_result.returncode != 0
    assert "battlefield artifact is stale" in stale_result.stderr
    assert stale_output.read_bytes() == stale_bytes


def test_phase17n_battlefield_builder_rejects_source_drift_without_writing(tmp_path: Path) -> None:
    repository_root = REPOSITORY_ROOT
    builder_path = repository_root / "tools/build_event_companion_battlefields.py"
    extraction_path = (
        repository_root
        / "data/source_audits/event_companion_2026_06"
        / "phase17n_event_companion_battlefields_pages_9_53_extraction.json"
    )
    modified_extraction = tmp_path / "modified-extraction.json"
    modified_extraction.write_bytes(extraction_path.read_bytes() + b"\n")
    guarded_output = tmp_path / "must-not-be-written.json"
    extraction_result = subprocess.run(
        [
            sys.executable,
            str(builder_path),
            str(modified_extraction),
            str(guarded_output),
        ],
        cwd=repository_root,
        check=False,
        capture_output=True,
        text=True,
    )
    assert extraction_result.returncode != 0
    assert "source extraction bytes drifted" in extraction_result.stderr
    assert not guarded_output.exists()


def test_phase17n_meatgrinder_exact_layouts_build_all_source_components() -> None:
    mission_pack = warhammer_event_companion_2026_07_mission_pack()
    artifact = event_layouts.battlefield_artifact()
    artifact_layouts = {layout.layout_id: layout for layout in _meatgrinder_artifact_layouts()}
    archetypes_by_id = {
        archetype.archetype_id: archetype for archetype in artifact.feature_archetypes
    }
    terrain_area_templates = {
        template.footprint_template_id: template
        for template in mission_pack.terrain_area_footprint_templates
    }
    expected_objective_coordinates = {
        1: (
            (8.58, 50.32),
            (36.08, 9.01),
            (26.51, 37.47),
            (17.82, 22.31),
            (32.15, 52.67),
            (12.36, 8.33),
        ),
        2: (
            (9.90, 47.73),
            (33.63, 12.05),
            (11.39, 29.61),
            (32.92, 30.55),
            (37.23, 42.98),
            (6.86, 17.11),
        ),
        3: (
            (9.08, 51.19),
            (34.81, 9.01),
            (22.33, 35.93),
            (21.23, 23.67),
            (29.28, 51.31),
            (15.25, 8.98),
        ),
    }

    for layout_number in (1, 2, 3):
        layout_id = f"purge-the-foe-vs-purge-the-foe-layout-{layout_number}"
        setup = MissionSetup.from_mission_pack(
            mission_pack=mission_pack,
            mission_pool_entry_id=f"mission-{layout_id}",
            attacker_player_id="player-alpha",
            attacker_force_disposition_id="purge-the-foe",
            defender_player_id="player-beta",
            defender_force_disposition_id="purge-the-foe",
        )
        source_layout = artifact_layouts[layout_id]
        battlefield_layout = mission_pack.battlefield_layout(layout_id)
        areas_by_id = {area.terrain_area_id: area for area in setup.terrain_areas}
        placements_by_id = {
            placement.feature_id: placement
            for placement in battlefield_layout.terrain_feature_placements
        }
        features_by_id = {feature.feature_id: feature for feature in setup.terrain_features}
        objective_markers_by_id = {
            marker.objective_marker_id: marker for marker in setup.objective_markers
        }
        ruins = tuple(
            feature for feature in setup.terrain_features if feature.feature_kind.value == "ruins"
        )
        light = tuple(
            feature
            for feature in setup.terrain_features
            if feature.classification is TerrainAreaClassification.LIGHT
        )
        dense = tuple(
            feature
            for feature in setup.terrain_features
            if feature.classification is TerrainAreaClassification.DENSE
        )

        assert len(setup.terrain_areas) == 16
        assert {area.terrain_feature_kind for area in setup.terrain_areas} == {
            "terrain_layout_area"
        }
        assert Counter(area.classification.value for area in setup.terrain_areas) == Counter(
            {"dense": 6, "mixed": 6, "light": 4}
        )
        assert len(setup.terrain_features) == 30
        assert (len(ruins), len(dense), len(light)) == (8, 16, 14)
        assert Counter(len(ruin.floors) for ruin in ruins) == Counter({2: 4, 3: 4})
        assert all(
            tuple(sorted(floor.bottom_z_inches for floor in ruin.floors))
            in {(0.0, 3.0), (0.0, 3.0, 6.0)}
            for ruin in ruins
        )
        for ruin in ruins:
            floor_levels = tuple(sorted(floor.bottom_z_inches for floor in ruin.floors))
            top_floor_level = floor_levels[-1]
            assert all(
                wall.height_inches == (2.0 if wall.bottom_z_inches == top_floor_level else 3.0)
                for wall in ruin.walls
            )
            assert all(
                any(
                    wall.bottom_z_inches == floor_level
                    and wall.bottom_z_inches + wall.height_inches == next_floor_level
                    for wall in ruin.walls
                )
                for floor_level, next_floor_level in pairwise(floor_levels)
            )
        assert {(marker.x_inches, marker.y_inches) for marker in setup.objective_markers} == set(
            expected_objective_coordinates[layout_number]
        )
        for objective_terrain_area in setup.objective_terrain_areas:
            objective = objective_markers_by_id[objective_terrain_area.objective_marker_id]
            for terrain_area_id in objective_terrain_area.terrain_area_ids:
                terrain_area = areas_by_id[terrain_area_id]
                terrain_polygon = DeploymentZonePolygon(
                    vertices=tuple(
                        DeploymentZonePoint(x=point.x_inches, y=point.y_inches)
                        for point in terrain_area.footprint_polygon
                    )
                )
                assert terrain_polygon.contains_point(
                    objective.x_inches,
                    objective.y_inches,
                    include_boundary=True,
                )
        for source_component in source_layout.terrain_components:
            area = areas_by_id[source_component.terrain_area_id]
            placement = placements_by_id[source_component.component_id]
            feature = features_by_id[source_component.component_id]
            template = terrain_area_templates[area.footprint_template_id]
            local_x = placement.local_offset_x_inches
            if area.local_transform is TerrainAreaLocalTransform.MIRROR_Y_AXIS:
                local_x = (2.0 * template.polygon_vertices_inches[0].x_inches) - local_x
            radians = math.radians(area.rotation_degrees)
            battlefield_x = (
                area.center_x_inches
                + (local_x * math.cos(radians))
                - (placement.local_offset_y_inches * math.sin(radians))
            )
            battlefield_y = (
                area.center_y_inches
                + (local_x * math.sin(radians))
                + (placement.local_offset_y_inches * math.cos(radians))
            )
            assert math.isclose(
                battlefield_x,
                source_component.battlefield_center_x_inches,
                rel_tol=0.0,
                abs_tol=1e-6,
            )
            assert math.isclose(
                battlefield_y,
                source_component.battlefield_center_y_inches,
                rel_tol=0.0,
                abs_tol=1e-6,
            )
            component_rotation = placement.local_rotation_degrees
            if placement.local_transform.value == "mirror_y_axis":
                component_rotation += 180.0
            battlefield_rotation = (
                area.rotation_degrees + 180.0 - component_rotation
                if area.local_transform is TerrainAreaLocalTransform.MIRROR_Y_AXIS
                else area.rotation_degrees + component_rotation
            ) % 360.0
            rotation_delta = (
                battlefield_rotation - source_component.battlefield_rotation_degrees + 180.0
            ) % 360.0 - 180.0
            assert math.isclose(rotation_delta, 0.0, rel_tol=0.0, abs_tol=1e-6)
            assert feature.classification.value == (
                archetypes_by_id[source_component.archetype_id].classification
            )
            assert feature.to_rules_geometry_payload()["classification"] == (
                feature.classification.value
            )
            assert feature.source_id is not None
            assert (
                f"terrain-feature-placement:"
                f"{source_component.component_id.removeprefix(f'{layout_id}-')}"
            ) in feature.source_id
            assert event_layouts.BATTLEFIELD_PACKAGE_HASH in feature.source_id
            assert feature.source_id.endswith(f":{event_layouts.BATTLEFIELD_PACKAGE_HASH}")


def test_phase17j_event_matrix_uses_pdf_source_pairings_not_chapter_approved_order() -> None:
    source_rows = event_source.event_primary_mission_matrix_source_rows()
    executable_primary_ids = event_primary_scoring.engine_implemented_primary_mission_ids()
    matrix = {
        (row.player_force_disposition_id, row.opponent_force_disposition_id): row
        for row in event_source.primary_mission_matrix_rows()
    }

    assert len(source_rows) == 15
    assert len(matrix) == 25
    complete_pair_ids = {
        row.layout_pair_id
        for row in source_rows
        if row.source_left_primary_mission_id in executable_primary_ids
        and row.source_right_primary_mission_id in executable_primary_ids
    }
    assert complete_pair_ids == {
        "disruption-vs-disruption",
        "disruption-vs-priority-assets",
        "disruption-vs-reconnaissance",
        "priority-assets-vs-priority-assets",
        "purge-the-foe-vs-disruption",
        "purge-the-foe-vs-priority-assets",
        "purge-the-foe-vs-purge-the-foe",
        "purge-the-foe-vs-reconnaissance",
        "reconnaissance-vs-priority-assets",
        "reconnaissance-vs-reconnaissance",
        "take-and-hold-vs-disruption",
        "take-and-hold-vs-priority-assets",
        "take-and-hold-vs-purge-the-foe",
        "take-and-hold-vs-reconnaissance",
        "take-and-hold-vs-take-and-hold",
    }
    assert (
        sum(
            len(row.battlefield_layout_ids)
            for row in event_source.primary_mission_matrix_rows()
            if row.player_force_disposition_id <= row.opponent_force_disposition_id
            and row.primary_mission_id in executable_primary_ids
            and matrix[
                (row.opponent_force_disposition_id, row.player_force_disposition_id)
            ].primary_mission_id
            in executable_primary_ids
        )
        == 45
    )
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

    source_row_payload = source_rows[0].to_payload()
    assert source_row_payload == {
        "source_left_force_disposition_id": "take-and-hold",
        "source_right_force_disposition_id": "take-and-hold",
        "source_left_primary_mission_id": "primary-battlefield-dominance",
        "source_left_primary_mission_name": "Battlefield Dominance",
        "source_right_primary_mission_id": "primary-battlefield-dominance",
        "source_right_primary_mission_name": "Battlefield Dominance",
        "layout_pair_id": "take-and-hold-vs-take-and-hold",
        "layout_source_page_start": 9,
        "source_id": (
            "gw-11e-warhammer-event-companion-v1-1-2026-07:"
            "primary-mission-matrix-source:take-and-hold-vs-take-and-hold"
        ),
    }
    assert "<" not in json.dumps(source_row_payload, sort_keys=True)


def test_phase17j_deployment_zone_layout_matrix_matches_event_companion_source() -> None:
    expected_template_numbers: dict[tuple[str, str], tuple[int, int, int]] = {
        ("take-and-hold", "take-and-hold"): (1, 2, 3),
        ("take-and-hold", "purge-the-foe"): (4, 3, 5),
        ("take-and-hold", "disruption"): (4, 6, 5),
        ("take-and-hold", "reconnaissance"): (1, 2, 3),
        ("take-and-hold", "priority-assets"): (6, 5, 2),
        ("purge-the-foe", "purge-the-foe"): (3, 1, 4),
        ("purge-the-foe", "disruption"): (3, 1, 4),
        ("purge-the-foe", "reconnaissance"): (5, 2, 6),
        ("purge-the-foe", "priority-assets"): (2, 3, 5),
        ("disruption", "disruption"): (6, 1, 4),
        ("disruption", "reconnaissance"): (1, 2, 3),
        ("disruption", "priority-assets"): (4, 1, 3),
        ("reconnaissance", "reconnaissance"): (4, 6, 1),
        ("reconnaissance", "priority-assets"): (6, 1, 4),
        ("priority-assets", "priority-assets"): (4, 6, 1),
    }
    source_pairs = tuple(
        (row.source_left_force_disposition_id, row.source_right_force_disposition_id)
        for row in event_source.event_primary_mission_matrix_source_rows()
    )
    primary_matrix = {
        (row.player_force_disposition_id, row.opponent_force_disposition_id): row
        for row in event_source.primary_mission_matrix_rows()
    }

    assert source_pairs == tuple(expected_template_numbers)
    for (left_id, right_id), template_numbers in expected_template_numbers.items():
        expected_layout_ids = tuple(
            f"{left_id}-vs-{right_id}-layout-{layout_number}" for layout_number in (1, 2, 3)
        )
        assert primary_matrix[(left_id, right_id)].battlefield_layout_ids == expected_layout_ids
        assert primary_matrix[(right_id, left_id)].battlefield_layout_ids == expected_layout_ids
        for layout_number, template_number in enumerate(template_numbers, start=1):
            assert _source_deployment_zone_layout_template_id(
                layout_id=f"{left_id}-vs-{right_id}-layout-{layout_number}",
                layout_number=layout_number,
            ) == _source_deployment_zone_layout_template_id_from_number(template_number)


def test_phase17j_known_layouts_use_canonical_deployment_zone_helpers() -> None:
    rows = {row.battlefield_layout_id: row for row in event_source.battlefield_layout_rows()}
    layout_a = rows["take-and-hold-vs-take-and-hold-layout-1"]
    layout_b = rows["take-and-hold-vs-take-and-hold-layout-2"]
    layout_c = rows["take-and-hold-vs-take-and-hold-layout-3"]
    take_vs_purge_a = rows["take-and-hold-vs-purge-the-foe-layout-1"]
    take_vs_purge_c = rows["take-and-hold-vs-purge-the-foe-layout-3"]
    take_vs_priority_a = rows["take-and-hold-vs-priority-assets-layout-1"]

    assert _shape_polygons(layout_a.deployment_zones[0].shape) == (
        ((0.0, 60.0), (44.0, 60.0), (44.0, 48.0), (22.0, 48.0), (22.0, 40.0), (0.0, 40.0)),
    )
    assert _shape_polygons(layout_a.deployment_zones[1].shape) == (
        ((44.0, 0.0), (0.0, 0.0), (0.0, 12.0), (22.0, 12.0), (22.0, 20.0), (44.0, 20.0)),
    )
    assert _shape_polygons(layout_b.deployment_zones[0].shape) == (
        ((0.0, 0.0), (12.0, 0.0), (12.0, 60.0), (0.0, 60.0)),
    )
    assert _shape_polygons(layout_b.deployment_zones[1].shape) == (
        ((32.0, 0.0), (44.0, 0.0), (44.0, 60.0), (32.0, 60.0)),
    )
    assert not layout_c.deployment_zones[0].shape.contains_point(22.0, 30.0)
    assert not layout_c.deployment_zones[1].shape.contains_point(22.0, 30.0)
    assert _shape_polygons(take_vs_purge_a.deployment_zones[0].shape) == (
        ((0.0, 0.0), (8.0, 0.0), (8.0, 30.0), (14.0, 30.0), (14.0, 60.0), (0.0, 60.0)),
    )
    assert _shape_polygons(take_vs_purge_a.deployment_zones[1].shape) == (
        ((44.0, 60.0), (36.0, 60.0), (36.0, 30.0), (30.0, 30.0), (30.0, 0.0), (44.0, 0.0)),
    )
    assert _shape_polygons(take_vs_purge_c.deployment_zones[0].shape) == (
        ((0.0, 42.0), (44.0, 42.0), (44.0, 60.0), (0.0, 60.0)),
    )
    assert _shape_polygons(take_vs_purge_c.deployment_zones[1].shape) == (
        ((0.0, 0.0), (44.0, 0.0), (44.0, 18.0), (0.0, 18.0)),
    )
    assert _shape_polygons(take_vs_priority_a.deployment_zones[0].shape) == (
        ((0.0, 60.0), (44.0, 60.0), (0.0, 30.0)),
    )
    assert _shape_polygons(take_vs_priority_a.deployment_zones[1].shape) == (
        ((44.0, 0.0), (0.0, 0.0), (44.0, 30.0)),
    )
    descriptor = _layout_descriptor("take-and-hold", "purge-the-foe", "c")
    assert descriptor.attacker_edge == "north"
    assert descriptor.defender_edge == "south"


def test_phase17j_deployment_zone_helpers_fail_closed_for_unknown_shapes() -> None:
    unsupported_template = cast(
        event_source.DeploymentZoneLayoutTemplateId,
        "deployment-zone-layout-unsupported",
    )

    with pytest.raises(MissionPackError, match="Unsupported battlefield layout number"):
        _source_deployment_zone_layout_template_id(
            layout_id="take-and-hold-vs-purge-the-foe-layout-9",
            layout_number=9,
        )
    with pytest.raises(
        MissionPackError,
        match="Battlefield layout number does not match layout ID",
    ):
        _source_deployment_zone_layout_template_id(
            layout_id="take-and-hold-vs-purge-the-foe-layout-2",
            layout_number=1,
        )
    with pytest.raises(
        MissionPackError,
        match="Battlefield layout ID must include force disposition pair",
    ):
        _source_deployment_zone_layout_template_id(
            layout_id="take-and-hold-layout-1",
            layout_number=1,
        )
    with pytest.raises(MissionPackError, match="Unsupported deployment-zone layout matchup"):
        _source_deployment_zone_layout_template_id(
            layout_id="take-and-hold-vs-unknown-layout-1",
            layout_number=1,
        )
    with pytest.raises(MissionPackError, match="Unsupported deployment-zone layout template"):
        _source_deployment_zone_template_base_shape(unsupported_template)
    with pytest.raises(MissionPackError, match="Unsupported deployment-zone layout template"):
        _source_deployment_zone_layout_edges(unsupported_template)
    with pytest.raises(MissionPackError, match="Battlefield layout ID must end in layout number"):
        _source_layout_number_from_layout_id("take-and-hold-vs-purge-the-foe-layout-z")


def test_phase17j_primary_matrix_inventory_drift_fails_closed(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def unknown_primary_names() -> tuple[tuple[str, str], ...]:
        return (("primary-source-pending", "Source Pending"),)

    monkeypatch.setattr(event_source, "_event_primary_mission_names", unknown_primary_names)

    with pytest.raises(MissionPackError, match="artifact inventory drifted from the matrix"):
        event_source.primary_mission_rows()


def test_phase17j_source_lookup_helpers_fail_closed_for_unknown_ids() -> None:
    with pytest.raises(MissionPackError, match="Event Companion matrix row was not found"):
        _source_matrix_row(
            player_force_disposition_id="unknown-force",
            opponent_force_disposition_id="take-and-hold",
        )
    with pytest.raises(
        MissionPackError,
        match="MissionPackDefinition does not contain force_disposition_id",
    ):
        warhammer_event_companion_2026_07_mission_pack().force_disposition("unknown-force")


@pytest.mark.parametrize(
    ("layout_number", "expected_feature_count", "expects_multi_polygon_region"),
    [(1, 29, False), (3, 30, True)],
)
def test_phase17j_mission_setup_components_resolve_matching_battlefield_layout(
    layout_number: int,
    expected_feature_count: int,
    expects_multi_polygon_region: bool,
) -> None:
    mission_pack = warhammer_event_companion_2026_07_mission_pack()
    layout_id = f"take-and-hold-vs-take-and-hold-layout-{layout_number}"
    layout = mission_pack.battlefield_layout(layout_id)
    setup = MissionSetup.from_components(
        mission_pack=mission_pack,
        mission_pool_entry_id=f"mission-{layout_id}",
        deployment_map=mission_pack.deployment_map(layout.deployment_map_id),
        terrain_layout=mission_pack.terrain_layout_template(layout.terrain_layout_id),
        attacker_player_id="player-alpha",
        attacker_force_disposition_id="take-and-hold",
        defender_player_id="player-beta",
        defender_force_disposition_id="take-and-hold",
    )

    assert setup.battlefield_layout_id == layout.battlefield_layout_id
    assert len(setup.terrain_features) == expected_feature_count
    assert len(setup.terrain_areas) == 16
    assert len(setup.battlefield_regions) == 5
    assert any(len(region.shape.polygons) > 1 for region in setup.battlefield_regions) is (
        expects_multi_polygon_region
    )
    assert {
        (binding.objective_marker_id, binding.terrain_area_ids)
        for binding in setup.objective_terrain_areas
    } == {
        (binding.objective_marker_id, binding.terrain_area_ids)
        for binding in layout.objective_terrain_areas
    }


def test_phase17j_layout_region_invariants_fail_closed() -> None:
    layout = warhammer_event_companion_2026_07_mission_pack().battlefield_layout(
        "take-and-hold-vs-take-and-hold-layout-2"
    )
    attacker_zone = next(zone for zone in layout.deployment_zones if zone.player_id == "attacker")
    no_mans_land = next(
        region for region in layout.battlefield_regions if region.region_id.endswith("no-mans-land")
    )
    drifted_no_mans_land = replace(no_mans_land, shape=attacker_zone.shape)

    with pytest.raises(MissionPackError, match="no-man's-land"):
        BattlefieldLayoutDefinition(
            battlefield_layout_id=layout.battlefield_layout_id,
            name=layout.name,
            deployment_map_id=layout.deployment_map_id,
            terrain_layout_id=layout.terrain_layout_id,
            battlefield_width_inches=layout.battlefield_width_inches,
            battlefield_depth_inches=layout.battlefield_depth_inches,
            coordinate_origin=layout.coordinate_origin,
            coordinate_orientation=layout.coordinate_orientation,
            attacker_edge=layout.attacker_edge,
            defender_edge=layout.defender_edge,
            objective_markers=layout.objective_markers,
            deployment_zones=layout.deployment_zones,
            battlefield_regions=tuple(
                drifted_no_mans_land
                if region.region_id == drifted_no_mans_land.region_id
                else region
                for region in layout.battlefield_regions
            ),
            terrain_areas=layout.terrain_areas,
            terrain_feature_placements=layout.terrain_feature_placements,
            objective_role_counts=layout.objective_role_counts,
            source_id=layout.source_id,
        )


def test_phase17j_territories_must_contain_their_deployment_zones() -> None:
    layout = warhammer_event_companion_2026_07_mission_pack().battlefield_layout(
        "take-and-hold-vs-take-and-hold-layout-1"
    )
    attacker_territory = next(
        region
        for region in layout.battlefield_regions
        if region.region_id.endswith("attacker-territory")
    )
    defender_territory = next(
        region
        for region in layout.battlefield_regions
        if region.region_id.endswith("defender-territory")
    )
    swapped_attacker_territory = replace(
        attacker_territory,
        shape=defender_territory.shape,
    )
    swapped_defender_territory = replace(
        defender_territory,
        shape=attacker_territory.shape,
    )

    with pytest.raises(MissionPackError, match="Attacker territory"):
        BattlefieldLayoutDefinition(
            battlefield_layout_id=layout.battlefield_layout_id,
            name=layout.name,
            deployment_map_id=layout.deployment_map_id,
            terrain_layout_id=layout.terrain_layout_id,
            battlefield_width_inches=layout.battlefield_width_inches,
            battlefield_depth_inches=layout.battlefield_depth_inches,
            coordinate_origin=layout.coordinate_origin,
            coordinate_orientation=layout.coordinate_orientation,
            attacker_edge=layout.attacker_edge,
            defender_edge=layout.defender_edge,
            objective_markers=layout.objective_markers,
            deployment_zones=layout.deployment_zones,
            battlefield_regions=tuple(
                swapped_attacker_territory
                if region.region_id == swapped_attacker_territory.region_id
                else swapped_defender_territory
                if region.region_id == swapped_defender_territory.region_id
                else region
                for region in layout.battlefield_regions
            ),
            terrain_areas=layout.terrain_areas,
            terrain_feature_placements=layout.terrain_feature_placements,
            objective_role_counts=layout.objective_role_counts,
            source_id=layout.source_id,
        )


def test_phase17j_base_size_source_rows_fail_closed_for_noncanonical_shapes() -> None:
    rows = event_source.base_size_source_rows()
    rows_by_kind = {row.base_source_kind: row for row in rows}

    assert len(event_companion_base_size_rows.BASE_SIZE_SOURCE_ROWS) == len(rows)
    assert event_companion_base_size_rows.BASE_SIZE_SOURCE_ROWS[0] == (
        "page-55-adepta-sororitas-aestred-thurga-and-agathae-dolan-aestred-thurga",
        55,
        "Adepta Sororitas",
        None,
        "Aestred Thurga and Agathae Dolan: Aestred Thurga",
        "32mm",
    )
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

    assert descriptor_rows == ()


def test_phase17n_primary_actions_are_exposed_with_source_backed_policies() -> None:
    action_sources = {
        row.mission_action_id: row for row in event_source.primary_mission_action_source_rows()
    }
    mission_pack = warhammer_event_companion_2026_07_mission_pack()

    assert set(action_sources) == {
        "commit-sabotage",
        "decoy-objective",
        "extract-intelligence",
        "maintain-control",
        "sensor-sweep-extract-relic",
        "sensor-sweep-locate-and-deny",
        "secure-asset",
        "surveil-enemy-unit",
        "triangulate-objective",
        "vanguard-operation",
    }
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
        "engine_exposure_status": "engine_implemented",
        "source_id": (
            "gw-11e-warhammer-event-companion-v1-1-2026-07:primary-action:decoy-objective"
        ),
    }
    assert action_sources["triangulate-objective"].start_timing == (
        "shooting_phase_action_start_from_battle_round_two"
    )
    assert action_sources["extract-intelligence"].to_payload() == {
        "mission_action_id": "extract-intelligence",
        "primary_mission_id": "primary-gather-intel",
        "name": "Extract Intelligence",
        "start_phase": "shooting",
        "start_timing": "shooting_phase_action_start_from_battle_round_two",
        "completion_timing": "turn_end",
        "eligible_unit_policy": "active_player_unit",
        "target_policy": "objective_marker_excluding_home_without_friendly_operation_marker",
        "use_limit": "unlimited_different_objective_per_unit_this_phase",
        "effect_descriptor": (
            "objective_gains_operation_marker_if_action_unit_controls_target_at_turn_end"
        ),
        "engine_exposure_status": "engine_implemented",
        "source_id": (
            "gw-11e-warhammer-event-companion-v1-1-2026-07:primary-action:extract-intelligence"
        ),
    }
    assert action_sources["surveil-enemy-unit"].to_payload() == {
        "mission_action_id": "surveil-enemy-unit",
        "primary_mission_id": "primary-surveil-the-foe",
        "name": "Surveil the Foe",
        "start_phase": "shooting",
        "start_timing": "shooting_phase_action_start",
        "completion_timing": "immediate",
        "eligible_unit_policy": "active_player_unit",
        "target_policy": "visible_enemy_unit_within_18_not_surveilled_this_turn",
        "use_limit": "unlimited",
        "effect_descriptor": "enemy_unit_becomes_surveilled_until_turn_end",
        "engine_exposure_status": "engine_implemented",
        "source_id": (
            "gw-11e-warhammer-event-companion-v1-1-2026-07:primary-action:surveil-enemy-unit"
        ),
    }
    assert action_sources["sensor-sweep-locate-and-deny"].target_policy == (
        "central_objective_and_friendly_operation_marker_requires_more_than_one_"
        "friendly_marker_remaining"
    )
    assert action_sources["sensor-sweep-extract-relic"].effect_descriptor == (
        "remove_one_opponent_operation_marker_if_action_unit_controls_selected_central_"
        "objective_at_turn_end"
    )
    assert action_sources["commit-sabotage"].use_limit == (
        "unlimited_different_objective_per_unit_this_phase"
    )
    assert action_sources["secure-asset"].to_payload() == {
        "mission_action_id": "secure-asset",
        "primary_mission_id": "primary-secure-asset",
        "name": "Secure Asset",
        "start_phase": "shooting",
        "start_timing": "shooting_phase_action_start",
        "completion_timing": "turn_end",
        "eligible_unit_policy": "active_player_unit_within_range_of_non_home_objective",
        "target_policy": "objective_marker_excluding_home",
        "use_limit": "once_per_turn",
        "effect_descriptor": "unit_secures_asset_if_action_unit_controls_target_at_turn_end",
        "engine_exposure_status": "engine_implemented",
        "source_id": ("gw-11e-warhammer-event-companion-v1-1-2026-07:primary-action:secure-asset"),
    }
    assert action_sources["vanguard-operation"].eligible_unit_policy == (
        "active_player_unit_within_terrain_area_in_enemy_territory"
    )
    assert action_sources["maintain-control"].effect_descriptor == (
        "central_objective_gains_operation_marker_if_action_unit_controls_target_at_turn_end"
    )
    assert len(mission_pack.mission_actions) == 14
    for action_id, source_row in action_sources.items():
        runtime_action = mission_pack.mission_action(action_id)
        policy = mission_action_policies.mission_action_policy_for_identity(
            mission_action_id=action_id,
            source_id=source_row.source_id,
        )
        assert runtime_action.mission_id == source_row.primary_mission_id
        assert runtime_action.mission_kind == "primary"
        assert runtime_action.source_id == (
            f"gw-11e-warhammer-event-companion-v1-1-2026-07:action:{action_id}"
        )
        assert policy.source_id == source_row.source_id
        assert runtime_action.victory_points == 0
        assert policy.primary_mission_id == runtime_action.mission_id
        assert policy.use_limit == source_row.use_limit
        assert policy.effect_descriptor == source_row.effect_descriptor
        assert policy.target_policy == runtime_action.target_policy
        assert policy.interruption_conditions == runtime_action.interruption_conditions


def test_phase17n_primary_state_and_choice_rules_have_strict_runtime_lookups() -> None:
    consecrate_state = mission_action_policies.primary_mission_state_rule_for_id(
        "consecrate-destroyer-becomes-consecration-unit"
    )
    surveil_state = mission_action_policies.primary_mission_state_rule_for_id(
        "surveil-remove-operation-markers-after-move"
    )
    punishment_choice = mission_action_policies.primary_mission_choice_rule_for_id(
        "punishment-condemn-enemy-units"
    )
    locate_choice = mission_action_policies.primary_mission_choice_rule_for_id(
        "locate-and-deny-operation-marker-setup"
    )

    assert consecrate_state.effect_descriptor == "unit_becomes_consecration_unit"
    assert consecrate_state.effect_duration == "until_consumed"
    assert surveil_state.trigger_timing == "friendly_rules_unit_move_end"
    assert surveil_state.effect_descriptor == (
        "remove_all_opponent_operation_markers_from_each_in_range_objective"
    )
    assert punishment_choice.selection_policy == (
        "one_to_three_or_exactly_one_fallback_when_no_primary_targets"
    )
    assert punishment_choice.fallback_target_policy == "enemy_battlefield_unit"
    assert locate_choice.selection_policy == "exactly_five_or_all_available_when_fewer"
    assert locate_choice.maximum_selections == 5
    assert tuple(
        rule.choice_rule_id
        for rule in mission_action_policies.primary_mission_choice_rules_for_mission(
            "primary-consecrate"
        )
    ) == ("consecrate-objective-at-turn-end",)
    assert tuple(
        rule.state_rule_id
        for rule in mission_action_policies.primary_mission_state_rules_for_mission(
            "primary-surveil-the-foe"
        )
    ) == ("surveil-remove-operation-markers-after-move",)
    with pytest.raises(
        mission_action_policies.MissionActionPolicyError,
        match="policy is not registered",
    ):
        mission_action_policies.mission_action_policy_for_id("forged-action")
    with pytest.raises(
        mission_action_policies.MissionActionPolicyError,
        match="identify different rules",
    ):
        mission_action_policies.mission_action_policy_for_identity(
            mission_action_id="commit-sabotage",
            source_id=(
                "gw-11e-warhammer-event-companion-v1-1-2026-07:primary-action:decoy-objective"
            ),
        )


def test_phase17j_surveil_primary_scoring_is_supported_on_primary_path() -> None:
    mission_pack = mission_pack_for_id("11e-warhammer-event-companion-2026-07")
    setup = MissionSetup.from_mission_pack(
        mission_pack=mission_pack,
        mission_pool_entry_id="mission-disruption-vs-reconnaissance-layout-1",
        attacker_player_id="player-alpha",
        attacker_force_disposition_id="reconnaissance",
        defender_player_id="player-beta",
        defender_force_disposition_id="disruption",
    )

    policies = mission_scoring_policies_from_setup(setup)

    attacker_policy = policies.policy_for_player("player-alpha")
    defender_policy = policies.policy_for_player("player-beta")

    assert attacker_policy.primary_mission_id == "primary-surveil-the-foe"
    assert attacker_policy.primary_scoring_supported
    assert defender_policy.primary_mission_id == "primary-smoke-and-mirrors"
    assert defender_policy.primary_scoring_supported
    assert (
        attacker_policy.cap_bucket_for_victory_point_source(
            source_kind=VictoryPointSourceKind.PRIMARY,
            source_id=attacker_policy.primary_mission_id,
        ).value
        == "primary"
    )


def test_phase17j_event_pack_resolves_scoring_and_tactical_draw_by_pack_id() -> None:
    mission_pack = mission_pack_for_id("11e-warhammer-event-companion-2026-07")
    setup = MissionSetup.from_mission_pack(
        mission_pack=mission_pack,
        mission_pool_entry_id="mission-take-and-hold-vs-purge-the-foe-layout-1",
        attacker_player_id="player-alpha",
        attacker_force_disposition_id="take-and-hold",
        defender_player_id="player-beta",
        defender_force_disposition_id="purge-the-foe",
    )
    policies = mission_scoring_policies_from_setup(setup)
    policy = policies.common_policy
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
    mission_pack = mission_pack_for_id("11e-warhammer-event-companion-2026-07")
    setup = MissionSetup.from_mission_pack(
        mission_pack=mission_pack,
        mission_pool_entry_id="mission-take-and-hold-vs-purge-the-foe-layout-1",
        attacker_player_id="player-alpha",
        attacker_force_disposition_id="take-and-hold",
        defender_player_id="player-beta",
        defender_force_disposition_id="purge-the-foe",
    )
    policies = mission_scoring_policies_from_setup(setup)
    player_alpha_ledger, _ = VictoryPointLedger.initial(player_id="player-alpha").award(
        VictoryPointAward(
            player_id="player-alpha",
            battle_round=5,
            phase="command",
            amount=55,
            source_kind=VictoryPointSourceKind.PRIMARY,
            source_id=setup.primary_mission_id_for_player("player-alpha"),
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
            source_id=setup.primary_mission_id_for_player("player-beta"),
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
        policies=policies,
        ledgers=(player_alpha_ledger, player_beta_ledger),
        scoring_windows=_event_final_scoring_windows(
            game_id="phase17j-event-final-scoring",
            battle_round=5,
            policy_source_id=policies.source_id,
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


__all__: list[str] = []
__all__ += ["Any", "BenefitOfCoverResult", "Callable", "CircularBase", "CoverSourceReason"]
__all__ += ["DeploymentZoneShape", "LineOfSightPolicy", "MissionPackDefinition"]
__all__ += ["MissionPackDefinitionPayload", "MissionSetupError", "MissionSourcePackageDefinition"]
__all__ += ["MissionSourceStatus", "Model", "ModelVolume", "ObjectiveMarkerDefinitionPayload"]
__all__ += ["ObjectiveMarkerRole", "Pose", "RulesetDescriptor", "ScoringWindowKind"]
__all__ += ["ScoringWindowState", "TerrainAreaCoverSourceRecord", "TerrainDisplayPoint"]
__all__ += ["TerrainVisibilityContext", "VisibilityBlockerKind"]
__all__ += ["_source_base_source_kind_and_geometry"]
__all__ += ["_source_rectangle_with_quarter_circle_cutout_vertices", "_terrain_display_points"]
__all__ += ["event_companion_patches", "event_no_mans_land_shape", "event_territory_vertices"]
__all__ += ["hashlib", "july_rules_updates_2026_07", "model_within_solid_terrain", "msgspec"]
__all__ += ["objective_marker_role_from_token", "permutations", "polygon_overlap_area"]
__all__ += ["shapely_backend", "terrain_area_classifications_by_suffix"]
__all__ += ["terrain_area_visibility", "terrain_feature_placements_from_specs"]
__all__ += ["terrain_visibility_areas_from_placements", "validate_mission_setup_source_layout"]
__all__ += ["visibility_polygon_within_union"]
