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


def test_phase17j_v1_1_layout_revisions_preserve_deployment_zone_templates() -> None:
    rows = july_rules_updates_2026_07.changed_event_layouts()

    assert {
        row.layout_id: (row.source_page, row.deployment_zone_template_number) for row in rows
    } == {
        "take-and-hold-vs-purge-the-foe-layout-1": (12, 4),
        "take-and-hold-vs-purge-the-foe-layout-2": (13, 3),
        "take-and-hold-vs-purge-the-foe-layout-3": (14, 5),
        "purge-the-foe-vs-disruption-layout-1": (27, 3),
        "purge-the-foe-vs-disruption-layout-2": (28, 1),
        "purge-the-foe-vs-disruption-layout-3": (29, 4),
        "disruption-vs-reconnaissance-layout-1": (39, 1),
        "disruption-vs-reconnaissance-layout-3": (41, 3),
    }
    assert all(row.terrain_changed for row in rows)
    assert all(not row.deployment_zones_changed for row in rows)


def test_phase17n_event_layout_rejects_missing_component_placements() -> None:
    with pytest.raises(MissionPackError, match="requires explicit terrain component placements"):
        terrain_feature_placements_from_specs(
            layout_id="event-layout",
            source_layout_id="source-layout",
            source_package_id="source-package",
            terrain_areas=(),
            specs=(),
        )
    with pytest.raises(MissionPackError, match="requires polygons"):
        event_no_mans_land_shape(explicit_polygons=())
    with pytest.raises(MissionPackError, match="require source polygons"):
        event_territory_vertices(explicit_specs=())
    with pytest.raises(MissionPackError, match="must cover every explicit area"):
        terrain_area_classifications_by_suffix(
            explicit_specs=(("terrain-area", "FOOTPRINT_6X4", 0.0, 0.0, 0.0),),
            classification_specs=(),
        )


def test_phase17n_all_layout_geometry_closes_declared_seams_and_region_holes() -> None:
    artifact = event_layouts.battlefield_artifact()
    mission_pack = warhammer_event_companion_2026_07_mission_pack()
    board = shapely_backend.footprint_for_polygon(
        ((0.0, 0.0), (44.0, 0.0), (44.0, 60.0), (0.0, 60.0))
    )
    checked_area_contacts = 0
    checked_component_contacts = 0
    checked_component_containment = 0
    checked_objective_bindings = 0
    area_contact_kinds: Counter[str] = Counter()
    logical_terrain_area_ids: set[str] = set()

    def shape_footprint(shape: DeploymentZoneShape) -> Any:
        polygons = tuple(
            shapely_backend.footprint_for_polygon(polygon) for polygon in _shape_polygons(shape)
        )
        result = polygons[0]
        for polygon in polygons[1:]:
            result = result.union(polygon)
        return result

    for source_layout in artifact.layouts:
        setup = MissionSetup.from_mission_pack(
            mission_pack=mission_pack,
            mission_pool_entry_id=f"mission-{source_layout.layout_id}",
            attacker_player_id="player-alpha",
            attacker_force_disposition_id=source_layout.force_disposition_pair[0],
            defender_player_id="player-beta",
            defender_force_disposition_id=source_layout.force_disposition_pair[1],
        )
        areas_by_id = {area.terrain_area_id: area for area in setup.terrain_areas}
        features_by_id = {feature.feature_id: feature for feature in setup.terrain_features}
        objectives_by_id = {
            objective.objective_marker_id: objective for objective in setup.objective_markers
        }

        for contact in source_layout.terrain_area_contacts:
            first_id, second_id = contact.terrain_area_ids
            first_points = _terrain_display_points(areas_by_id[first_id].footprint_polygon)
            second_points = _terrain_display_points(areas_by_id[second_id].footprint_polygon)
            first = shapely_backend.footprint_for_polygon(first_points)
            second = shapely_backend.footprint_for_polygon(second_points)
            runtime_overlap = first.intersection(second).area
            runtime_gap = first.distance(second)
            assert runtime_overlap <= 1e-6
            assert runtime_gap <= 0.05 + 1e-6
            assert math.isclose(
                contact.runtime_pair_overlap_square_inches,
                runtime_overlap,
                rel_tol=0.0,
                abs_tol=1e-6,
            )
            assert math.isclose(
                contact.runtime_pair_gap_inches,
                runtime_gap,
                rel_tol=0.0,
                abs_tol=1e-6,
            )
            first_group_id = areas_by_id[first_id].logical_terrain_area_id
            second_group_id = areas_by_id[second_id].logical_terrain_area_id
            assert (first_group_id == second_group_id) is (contact.kind == "single")
            checked_area_contacts += 1
            area_contact_kinds[contact.kind] += 1

        for first_id, second_id in source_layout.terrain_component_contact_pairs:
            first_points = _terrain_display_points(features_by_id[first_id].rules_footprint_polygon)
            second_points = _terrain_display_points(
                features_by_id[second_id].rules_footprint_polygon
            )
            first = shapely_backend.footprint_for_polygon(first_points)
            second = shapely_backend.footprint_for_polygon(second_points)
            assert first.distance(second) <= 1e-9
            checked_component_contacts += 1

        areas_by_logical_id: dict[str, list[Any]] = {}
        for area in setup.terrain_areas:
            areas_by_logical_id.setdefault(area.logical_terrain_area_id, []).append(area)
        for component in source_layout.terrain_components:
            parent = areas_by_id[component.terrain_area_id]
            logical_members = areas_by_logical_id[parent.logical_terrain_area_id]
            logical_footprint = shapely_backend.footprint_for_polygon(
                _terrain_display_points(logical_members[0].footprint_polygon)
            )
            for member in logical_members[1:]:
                logical_footprint = logical_footprint.union(
                    shapely_backend.footprint_for_polygon(
                        _terrain_display_points(member.footprint_polygon)
                    )
                )
            component_footprint = shapely_backend.footprint_for_polygon(
                _terrain_display_points(
                    features_by_id[component.component_id].rules_footprint_polygon
                )
            )
            assert component_footprint.difference(logical_footprint).area <= 1e-6
            checked_component_containment += 1

        layout_logical_ids = {area.logical_terrain_area_id for area in setup.terrain_areas}
        assert len(layout_logical_ids) == 16 - sum(
            contact.kind == "single" for contact in source_layout.terrain_area_contacts
        )
        logical_terrain_area_ids.update(layout_logical_ids)

        assert {binding.objective_marker_id for binding in setup.objective_terrain_areas} == {
            objective.objective_id
            for objective in source_layout.objectives
            if objective.terrain_area_ids
        }
        source_objectives_by_id = {
            objective.objective_id: objective for objective in source_layout.objectives
        }
        for binding in setup.objective_terrain_areas:
            objective = objectives_by_id[binding.objective_marker_id]
            source_objective = source_objectives_by_id[binding.objective_marker_id]
            expected_logical_ids = {
                areas_by_id[area_id].logical_terrain_area_id
                for area_id in source_objective.terrain_area_ids
            }
            assert binding.terrain_area_ids == tuple(
                sorted(
                    area.terrain_area_id
                    for logical_area_id in expected_logical_ids
                    for area in areas_by_logical_id[logical_area_id]
                )
            )
            assert binding.terrain_area_ids
            checked_objective_bindings += len(binding.terrain_area_ids)
            for area_id in source_objective.terrain_area_ids:
                area_polygon = tuple(
                    (point.x_inches, point.y_inches)
                    for point in areas_by_id[area_id].footprint_polygon
                )
                assert (
                    shapely_backend.point_distance_to_polygon(
                        objective.x_inches,
                        objective.y_inches,
                        area_polygon,
                    )
                    <= 0.05 + 1e-9
                )

        regions_by_suffix = {
            region.region_id.removeprefix(f"{source_layout.layout_id}-"): region
            for region in setup.battlefield_regions
        }
        attacker_zone = shape_footprint(regions_by_suffix["attacker-deployment-region"].shape)
        defender_zone = shape_footprint(regions_by_suffix["defender-deployment-region"].shape)
        no_mans_land = shape_footprint(regions_by_suffix["no-mans-land"].shape)
        attacker_territory = shape_footprint(regions_by_suffix["attacker-territory"].shape)
        defender_territory = shape_footprint(regions_by_suffix["defender-territory"].shape)

        assert attacker_zone.intersection(defender_zone).area <= 1e-6
        assert attacker_zone.intersection(no_mans_land).area <= 1e-6
        assert defender_zone.intersection(no_mans_land).area <= 1e-6
        assert (
            board.symmetric_difference(attacker_zone.union(defender_zone).union(no_mans_land)).area
            <= 1e-6
        )
        assert attacker_territory.intersection(defender_territory).area <= 1e-6
        assert board.symmetric_difference(attacker_territory.union(defender_territory)).area <= 1e-6
        assert attacker_territory.covers(attacker_zone)
        assert defender_territory.covers(defender_zone)

    assert checked_area_contacts == 224
    assert area_contact_kinds == Counter({"single": 112, "separate": 112})
    assert checked_component_contacts == 269
    assert checked_component_containment == 1_349
    assert checked_objective_bindings == 264
    assert len(logical_terrain_area_ids) == 608


def test_phase17n_runtime_layout_names_preserve_canonical_source_metadata() -> None:
    repository_root = REPOSITORY_ROOT
    extraction = json.loads(
        (
            repository_root
            / "data/source_audits/event_companion_2026_06"
            / "phase17n_event_companion_battlefields_pages_9_53_extraction.json"
        ).read_text(encoding="utf-8")
    )
    artifact_layouts = {
        layout.layout_id: layout for layout in event_layouts.battlefield_artifact().layouts
    }
    runtime_layouts = event_layouts.BATTLEFIELD_LAYOUTS_BY_ID
    mission_pack = warhammer_event_companion_2026_07_mission_pack()
    expected_names_by_id: dict[str, str] = {}

    for source_layout in extraction["layouts"]:
        layout_id = source_layout["layout_id"]
        variant = source_layout["variant"].upper()
        force_names = tuple(source_layout["force_disposition_pair"])
        mission_names = tuple(source_layout["primary_missions"])
        printed_metadata = source_layout["source_printed_left_to_right"]
        printed_force_names = tuple(printed_metadata["force_dispositions"])
        printed_mission_names = tuple(printed_metadata["primary_missions"])
        printed_label = printed_metadata["layout_label"]

        assert printed_force_names == force_names
        assert printed_mission_names == mission_names
        assert printed_label == f"Layout {variant}"
        assert source_layout["printed_title"] == (
            f"{printed_force_names[0]} vs {printed_force_names[1]} | "
            f"{printed_mission_names[0]} / {printed_mission_names[1]} | "
            f"{printed_label}"
        )

        expected_name = (
            f"{force_names[0]} vs {force_names[1]} - "
            f"{mission_names[0]} / {mission_names[1]} - "
            f"Layout {variant}"
        )
        expected_names_by_id[layout_id] = expected_name
        assert artifact_layouts[layout_id].name == expected_name
        assert runtime_layouts[layout_id].name == expected_name
        assert mission_pack.battlefield_layout(layout_id).name == expected_name

    assert expected_names_by_id["purge-the-foe-vs-priority-assets-layout-1"] == (
        "Purge the Foe vs Priority Assets - Destroyer's Wrath / Vital Link - Layout A"
    )
    assert expected_names_by_id["disruption-vs-disruption-layout-1"] == (
        "Disruption vs Disruption - Outmanoeuvre / Outmanoeuvre - Layout A"
    )


def test_phase17n_full_artifact_preserves_all_source_extraction_records() -> None:
    repository_root = REPOSITORY_ROOT
    extraction_path = (
        repository_root
        / "data/source_audits/event_companion_2026_06"
        / "phase17n_event_companion_battlefields_pages_9_53_extraction.json"
    )
    extraction_raw = extraction_path.read_bytes()
    extraction = json.loads(extraction_raw)
    stable_identity_map = json.loads(
        (
            repository_root
            / "data/source_audits/event_companion_2026_06"
            / "phase17n_event_companion_stable_runtime_identity_map.json"
        ).read_text(encoding="utf-8")
    )
    terrain_area_id_map = stable_identity_map["terrain_area_id_map"]
    objective_id_map = stable_identity_map["objective_id_map"]
    source_layout_id_map = stable_identity_map["source_layout_id_map"]
    artifact = event_layouts.battlefield_artifact()
    artifact_layouts = {layout.layout_id: layout for layout in artifact.layouts}

    assert hashlib.sha256(extraction_raw).hexdigest() == (artifact.source_extraction_payload_sha256)
    assert (
        json.loads(msgspec.json.encode(artifact.feature_archetypes))
        == extraction["reviewed_feature_archetypes"]
    )
    assert len(extraction["layouts"]) == 45
    checked_area_count = 0
    checked_component_count = 0
    checked_objective_count = 0
    reviewed_alternate_candidate_count = 0
    reviewed_area_pose_witnesses: dict[str, tuple[int, float, float]] = {}
    extended_area_adjustments: dict[str, tuple[float, float]] = {}
    exact_seam_adjustments: dict[str, tuple[float, float]] = {}
    component_containment_adjustments: dict[str, tuple[float, float]] = {}
    parent_centered_pipe_count = 0
    expected_component_containment_adjustments = {
        "purge-the-foe-vs-disruption-layout-3-terrain-area-04-component-01": (-0.1, 0.0),
        "purge-the-foe-vs-disruption-layout-3-terrain-area-07-component-01": (0.0, 0.05),
        "purge-the-foe-vs-disruption-layout-3-terrain-area-13-component-01": (0.05, -0.05),
        "disruption-vs-disruption-layout-3-terrain-area-02-component-01": (0.0, -0.05),
        "reconnaissance-vs-reconnaissance-layout-1-terrain-area-02-component-01": (0.0, -0.05),
        "take-and-hold-vs-priority-assets-layout-3-terrain-area-08-component-03": (
            0.0,
            -0.05,
        ),
        "take-and-hold-vs-priority-assets-layout-3-terrain-area-09-component-02": (
            0.0,
            0.05,
        ),
    }
    expected_reviewed_area_pose_witnesses = {
        "disruption-vs-disruption-layout-1-terrain-area-07": (2, 0.15, -0.1),
        "disruption-vs-disruption-layout-1-terrain-area-10": (
            2,
            -0.194559638906,
            0.110510105572,
        ),
        "purge-the-foe-vs-disruption-layout-3-terrain-area-02": (1, 0.1, -0.35),
        "purge-the-foe-vs-disruption-layout-3-terrain-area-04": (2, -0.1, 0.3),
        "purge-the-foe-vs-disruption-layout-3-terrain-area-13": (2, 0.05, -0.35),
        "purge-the-foe-vs-disruption-layout-3-terrain-area-15": (1, -0.05, 0.3),
        "purge-the-foe-vs-reconnaissance-layout-1-terrain-area-13": (0, 0.0, 0.05),
        "reconnaissance-vs-reconnaissance-layout-2-terrain-area-07": (2, 0.15, -0.1),
        "reconnaissance-vs-reconnaissance-layout-2-terrain-area-10": (
            2,
            -0.194559638906,
            0.110510105572,
        ),
        "disruption-vs-disruption-layout-2-terrain-area-06": (2, 0.0, 0.1),
        "disruption-vs-disruption-layout-2-terrain-area-11": (2, -0.2, 0.05),
        "reconnaissance-vs-reconnaissance-layout-3-terrain-area-06": (2, 0.0, 0.1),
        "reconnaissance-vs-reconnaissance-layout-3-terrain-area-11": (2, -0.2, 0.05),
        "take-and-hold-vs-purge-the-foe-layout-1-terrain-area-02": (1, 0.2, -0.05),
        "take-and-hold-vs-purge-the-foe-layout-1-terrain-area-04": (2, -0.2, 0.0),
        "take-and-hold-vs-purge-the-foe-layout-1-terrain-area-13": (2, 0.2, -0.05),
        "take-and-hold-vs-purge-the-foe-layout-1-terrain-area-15": (1, -0.2, 0.05),
        "take-and-hold-vs-take-and-hold-layout-3-terrain-area-08": (2, 0.1, 0.0),
        "take-and-hold-vs-take-and-hold-layout-3-terrain-area-09": (2, -0.15, 0.0),
        "take-and-hold-vs-take-and-hold-layout-3-terrain-area-11": (1, 0.0, -0.05),
    }

    for source_layout in extraction["layouts"]:
        layout = artifact_layouts[source_layout["layout_id"]]
        areas_by_source_id = {area.source_area_id: area for area in layout.terrain_areas}
        components_by_source_id = {
            component.source_component_id: component for component in layout.terrain_components
        }
        objectives_by_source_id = {
            objective.source_objective_id: objective for objective in layout.objectives
        }
        assert layout.source_page == source_layout["source_pdf_page_number"]
        if source_layout["layout_id"] in source_layout_id_map:
            assert layout.source_layout_id == source_layout_id_map[source_layout["layout_id"]]
        elif source_layout["layout_id"].startswith("purge-the-foe-vs-purge-the-foe"):
            assert layout.source_layout_id == (
                "gw_event_companion_v1_purge_the_foe_vs_purge_the_foe_meatgrinder_"
                f"layout_{'abc'[int(source_layout['layout_id'][-1]) - 1]}"
            )
        else:
            assert layout.source_layout_id == (
                f"gw_event_companion_v1_{source_layout['layout_id'].replace('-', '_')}"
            )
        icons_by_id = {icon["icon_id"]: icon for icon in source_layout["eye_contact_icons"]}
        assert len(layout.terrain_area_contacts) == len(source_layout["source_contact_pairs"])
        for contact, source_pair in zip(
            layout.terrain_area_contacts,
            source_layout["source_contact_pairs"],
            strict=True,
        ):
            assert contact.source_terrain_area_ids == tuple(source_pair["area_ids"])
            assert contact.terrain_area_ids == tuple(
                terrain_area_id_map.get(area_id, area_id) for area_id in source_pair["area_ids"]
            )
            assert contact.kind == source_pair["kinds"][0]
            assert contact.source_icon_ids == tuple(source_pair["icon_ids"])
            assert contact.source_pair_gap_inches == source_pair["source_pair_gap_inches"]
            source_icon = icons_by_id[contact.source_icon_ids[0]]
            assert contact.source_pdf_drawing_indices_zero_based == tuple(
                source_icon["source_drawing_indices_zero_based"]
            )
            assert contact.source_pdf_seqnos == tuple(source_icon["source_seqnos"])
            assert (
                contact.source_icon_x_inches,
                contact.source_icon_y_inches,
            ) == tuple(source_icon["battlefield_center_quantized_0_05_inches"])

        for source_area in source_layout["terrain_areas"]:
            area = areas_by_source_id[source_area["area_id"]]
            vector_path = source_area["source_vector_path"]
            source_image = source_area["source_area_image"]
            source_pose = source_area["pose_recipe"]
            assert area.area_id == terrain_area_id_map.get(
                source_area["area_id"], source_area["area_id"]
            )
            assert area.source_area_id == source_area["area_id"]
            assert area.footprint_template_id == source_area["footprint_template_id"]
            assert area.classification == source_area["classification"]
            assert (
                area.local_transform == source_area["runtime_orientation_review"]["local_transform"]
            )
            assert (
                area.local_transform_basis
                == source_area["runtime_orientation_review"]["local_transform_basis"]
            )
            assert area.source_mirror_area_id == source_area["point_symmetry_partner_area_id"]
            assert area.mirror_area_id == terrain_area_id_map.get(
                source_area["point_symmetry_partner_area_id"],
                source_area["point_symmetry_partner_area_id"],
            )
            source_candidate = next(
                candidate
                for candidate in source_pose["candidates"]
                if candidate["candidate_index"] == area.source_pose_candidate_index
            )
            assert (
                area.source_anchor_x_inches,
                area.source_anchor_y_inches,
                area.source_rotation_degrees,
                area.source_pose_fit_residual_inches,
            ) == (
                source_candidate["anchor_x_inches"],
                source_candidate["anchor_y_inches"],
                source_candidate["rotation_degrees"],
                source_candidate["fit_residual_inches"],
            )
            if area.source_pose_candidate_index != source_pose["selected_candidate_index"]:
                reviewed_alternate_candidate_count += 1
                assert area.pose_basis in {
                    "reviewed_source_pose_candidate_with_bounded_seam_adjustment",
                    "reviewed_source_pose_with_exact_seam_closure",
                }
            assert math.isclose(
                area.anchor_x_inches,
                area.source_anchor_x_inches + area.runtime_adjustment_x_inches,
                rel_tol=0.0,
                abs_tol=1e-9,
            )
            assert math.isclose(
                area.anchor_y_inches,
                area.source_anchor_y_inches + area.runtime_adjustment_y_inches,
                rel_tol=0.0,
                abs_tol=1e-9,
            )
            assert math.isclose(
                (area.rotation_degrees - area.source_rotation_degrees + 180.0) % 360.0 - 180.0,
                area.runtime_rotation_adjustment_degrees,
                rel_tol=0.0,
                abs_tol=1e-9,
            )
            if (
                abs(area.runtime_adjustment_x_inches) > 0.2
                or abs(area.runtime_adjustment_y_inches) > 0.2
            ):
                extended_area_adjustments[area.source_area_id] = (
                    area.runtime_adjustment_x_inches,
                    area.runtime_adjustment_y_inches,
                )
            if area.pose_basis == "reviewed_source_pose_with_exact_seam_closure":
                exact_seam_adjustments[area.source_area_id] = (
                    area.runtime_adjustment_x_inches,
                    area.runtime_adjustment_y_inches,
                )
            if area.source_area_id in expected_reviewed_area_pose_witnesses:
                reviewed_area_pose_witnesses[area.source_area_id] = (
                    area.source_pose_candidate_index,
                    area.runtime_adjustment_x_inches,
                    area.runtime_adjustment_y_inches,
                )
            assert (
                area.source_pdf_extended_drawing_index_zero_based
                == (vector_path["extended_drawing_index_zero_based"])
            )
            assert area.source_pdf_seqno == vector_path["seqno"]
            assert area.source_pdf_vector_item_count == vector_path["item_count"]
            assert area.source_pdf_image_xref == source_image["xref"]
            assert area.source_image_sha256 == source_image["source_image_sha256"]
            assert area.source_soft_mask_sha256 == source_image["source_soft_mask_sha256"]
            assert (
                area.source_pdf_bounds.x0_points,
                area.source_pdf_bounds.y0_points,
                area.source_pdf_bounds.x1_points,
                area.source_pdf_bounds.y1_points,
            ) == tuple(source_image["bbox_points"])
            assert (
                area.source_pdf_affine.a,
                area.source_pdf_affine.b,
                area.source_pdf_affine.c,
                area.source_pdf_affine.d,
                area.source_pdf_affine.e,
                area.source_pdf_affine.f,
            ) == tuple(source_image["affine_normalized_image_to_points"])
            checked_area_count += 1

        for source_component in source_layout["terrain_components"]:
            component = components_by_source_id[source_component["component_id"]]
            assert not source_component["inferred"]
            expected_parent_id = terrain_area_id_map.get(
                source_component["parent_area_id"], source_component["parent_area_id"]
            )
            component_ordinal = source_component["component_id"].rsplit("-component-", 1)[1]
            assert component.component_id == f"{expected_parent_id}-component-{component_ordinal}"
            assert component.source_component_id == source_component["component_id"]
            assert component.terrain_area_id == expected_parent_id
            assert component.archetype_id == source_component["archetype_id"]
            assert (
                component.source_mirror_component_id
                == source_component["point_symmetry_partner_component_id"]
            )
            expected_mirror_source_id = source_component["point_symmetry_partner_component_id"]
            if expected_mirror_source_id is None:
                assert component.mirror_component_id is None
            else:
                expected_mirror_parent = terrain_area_id_map.get(
                    expected_mirror_source_id.rsplit("-component-", 1)[0],
                    expected_mirror_source_id.rsplit("-component-", 1)[0],
                )
                expected_mirror_ordinal = expected_mirror_source_id.rsplit("-component-", 1)[1]
                assert component.mirror_component_id == (
                    f"{expected_mirror_parent}-component-{expected_mirror_ordinal}"
                )
            assert (
                component.local_transform
                == source_component["local_orientation_relative_to_parent"]["local_transform"]
            )
            assert (
                component.local_transform_basis
                == source_component["local_orientation_relative_to_parent"]["local_transform_basis"]
            )
            assert component.source_pdf_image_xref == source_component["source_xref"]
            assert (
                component.source_battlefield_center_x_inches,
                component.source_battlefield_center_y_inches,
            ) == tuple(source_component["battlefield_center_quantized_0_05_inches"])
            assert (
                component.source_battlefield_rotation_degrees
                == source_component["battlefield_image_x_axis_rotation_degrees"]
            )
            assert math.isclose(
                component.battlefield_center_x_inches,
                component.source_battlefield_center_x_inches
                + component.runtime_adjustment_x_inches,
                rel_tol=0.0,
                abs_tol=1e-9,
            )
            assert math.isclose(
                component.battlefield_center_y_inches,
                component.source_battlefield_center_y_inches
                + component.runtime_adjustment_y_inches,
                rel_tol=0.0,
                abs_tol=1e-9,
            )
            assert math.isclose(
                (
                    component.battlefield_rotation_degrees
                    - component.source_battlefield_rotation_degrees
                    + 180.0
                )
                % 360.0
                - 180.0,
                component.runtime_rotation_adjustment_degrees,
                rel_tol=0.0,
                abs_tol=1e-9,
            )
            if layout.source_page not in {24, 25, 26}:
                if component.archetype_id == "dense-long-pipes":
                    assert component.pose_basis == "reviewed_parent_footprint_centered_pipe_pose"
                    assert math.isclose(
                        component.runtime_rotation_adjustment_degrees,
                        (
                            component.battlefield_rotation_degrees
                            - component.source_battlefield_rotation_degrees
                            + 180.0
                        )
                        % 360.0
                        - 180.0,
                        rel_tol=0.0,
                        abs_tol=1e-9,
                    )
                    parent_centered_pipe_count += 1
                elif component.source_component_id in expected_component_containment_adjustments:
                    assert (
                        component.pose_basis
                        == "reviewed_source_quantization_containment_adjustment"
                    )
                    component_containment_adjustments[component.source_component_id] = (
                        component.runtime_adjustment_x_inches,
                        component.runtime_adjustment_y_inches,
                    )
                    assert component.runtime_rotation_adjustment_degrees == 0.0
                else:
                    assert (
                        component.battlefield_center_x_inches,
                        component.battlefield_center_y_inches,
                        component.battlefield_rotation_degrees,
                    ) == (
                        component.source_battlefield_center_x_inches,
                        component.source_battlefield_center_y_inches,
                        component.source_battlefield_rotation_degrees,
                    )
                    assert (
                        component.runtime_adjustment_x_inches,
                        component.runtime_adjustment_y_inches,
                        component.runtime_rotation_adjustment_degrees,
                    ) == (0.0, 0.0, 0.0)
            assert (
                component.source_pdf_bounds.x0_points,
                component.source_pdf_bounds.y0_points,
                component.source_pdf_bounds.x1_points,
                component.source_pdf_bounds.y1_points,
            ) == tuple(source_component["source_bbox_points"])
            assert (
                component.source_pdf_affine.a,
                component.source_pdf_affine.b,
                component.source_pdf_affine.c,
                component.source_pdf_affine.d,
                component.source_pdf_affine.e,
                component.source_pdf_affine.f,
            ) == tuple(source_component["source_affine_normalized_image_to_points"])
            checked_component_count += 1

        for source_objective in source_layout["objectives"]:
            objective = objectives_by_source_id[source_objective["objective_id"]]
            assert objective.objective_id == objective_id_map.get(
                source_objective["objective_id"], source_objective["objective_id"]
            )
            assert objective.source_objective_id == source_objective["objective_id"]
            assert objective.role == source_objective["role"]
            assert (objective.x_inches, objective.y_inches) == tuple(
                source_objective["battlefield_center_quantized_0_01_inches"]
            )
            source_distances = source_objective["distances_to_area_polygons_inches"]
            source_nearby_area_ids = (
                set(source_objective["nearest_area_ids"])
                if not source_distances
                else {
                    area_id
                    for area_id, distance in zip(
                        source_objective["nearest_area_ids"],
                        source_distances,
                        strict=True,
                    )
                    if distance <= 0.05
                }
            )
            assert set(objective.terrain_area_ids) == {
                terrain_area_id_map.get(area_id, area_id) for area_id in source_nearby_area_ids
            }
            checked_objective_count += 1

    assert checked_area_count == 720
    assert checked_component_count == 1_349
    assert checked_objective_count == 246
    assert reviewed_alternate_candidate_count > 0
    assert reviewed_area_pose_witnesses == expected_reviewed_area_pose_witnesses
    assert parent_centered_pipe_count == 84
    assert component_containment_adjustments == expected_component_containment_adjustments
    assert exact_seam_adjustments == {
        "disruption-vs-disruption-layout-1-terrain-area-07": (0.15, -0.1),
        "disruption-vs-disruption-layout-1-terrain-area-10": (
            -0.194559638906,
            0.110510105572,
        ),
        "reconnaissance-vs-reconnaissance-layout-2-terrain-area-07": (0.15, -0.1),
        "reconnaissance-vs-reconnaissance-layout-2-terrain-area-10": (
            -0.194559638906,
            0.110510105572,
        ),
    }
    assert extended_area_adjustments == {
        "purge-the-foe-vs-disruption-layout-3-terrain-area-02": (0.1, -0.35),
        "purge-the-foe-vs-disruption-layout-3-terrain-area-04": (-0.1, 0.3),
        "purge-the-foe-vs-disruption-layout-3-terrain-area-13": (0.05, -0.35),
        "purge-the-foe-vs-disruption-layout-3-terrain-area-15": (-0.05, 0.3),
    }


def test_phase17n_ruin_floors_preserve_source_visible_wall_only_tails() -> None:
    artifact = event_layouts.battlefield_artifact()
    expected_geometry = {
        "ruins-cd": (3.5, 2.96, 2.48, 0.02),
        "ruins-gh": (2.96, 3.5, 0.02, 2.48),
        "ruins-ef": (3.5, 3.5, 2.48, 0.98),
        "ruins-ab": (3.5, 3.5, 0.48, 0.98),
    }

    for archetype in artifact.feature_archetypes:
        if archetype.archetype_id not in expected_geometry:
            continue
        minimum_x = min(point.x_inches for point in archetype.rules_footprint_polygon)
        maximum_x = max(point.x_inches for point in archetype.rules_footprint_polygon)
        minimum_y = min(point.y_inches for point in archetype.rules_footprint_polygon)
        maximum_y = max(point.y_inches for point in archetype.rules_footprint_polygon)
        expected_width, expected_depth, expected_x_tail, expected_y_tail = expected_geometry[
            archetype.archetype_id
        ]
        for floor in archetype.floors:
            assert (floor.width_inches, floor.depth_inches) == (
                expected_width,
                expected_depth,
            )
            assert math.isclose(
                floor.center_x_inches - (floor.width_inches / 2.0),
                minimum_x + 0.02,
                rel_tol=0.0,
                abs_tol=1e-9,
            )
            assert math.isclose(
                floor.center_y_inches - (floor.depth_inches / 2.0),
                minimum_y + 0.02,
                rel_tol=0.0,
                abs_tol=1e-9,
            )
            assert math.isclose(
                maximum_x - (floor.center_x_inches + (floor.width_inches / 2.0)),
                expected_x_tail,
                rel_tol=0.0,
                abs_tol=1e-9,
            )
            assert math.isclose(
                maximum_y - (floor.center_y_inches + (floor.depth_inches / 2.0)),
                expected_y_tail,
                rel_tol=0.0,
                abs_tol=1e-9,
            )


def test_phase17n_exact_terrain_area_reflections_follow_source_affine_orientation() -> None:
    repository_root = REPOSITORY_ROOT
    extraction_payload = json.loads(
        (
            repository_root
            / "data/source_audits/event_companion_2026_06"
            / "phase17n_purge_the_foe_meatgrinder_pages_24_26_extraction.json"
        ).read_text(encoding="utf-8")
    )
    source_orientation_reversing_ids = {
        area["terrain_area_id"]
        for layout in extraction_payload["layouts"]
        for area in layout["terrain_areas"]
        if (
            area["source_image"]["pdf_page_affine_normalized_image_to_points"][0]
            * area["source_image"]["pdf_page_affine_normalized_image_to_points"][3]
        )
        - (
            area["source_image"]["pdf_page_affine_normalized_image_to_points"][1]
            * area["source_image"]["pdf_page_affine_normalized_image_to_points"][2]
        )
        < 0.0
    }
    artifact_mirrored_ids = {
        area.area_id
        for layout in _meatgrinder_artifact_layouts()
        for area in layout.terrain_areas
        if area.local_transform == "mirror_y_axis"
    }

    assert len(source_orientation_reversing_ids) == 12
    assert artifact_mirrored_ids == source_orientation_reversing_ids
    assert Counter(
        area.pose_basis
        for layout in _meatgrinder_artifact_layouts()
        for area in layout.terrain_areas
    ) == Counter(
        {
            "accepted_meatgrinder_exemplar_source_pose": 24,
            "accepted_meatgrinder_exemplar_exact_point_symmetry": 24,
        }
    )

    mission_pack = warhammer_event_companion_2026_07_mission_pack()
    setup = MissionSetup.from_mission_pack(
        mission_pack=mission_pack,
        mission_pool_entry_id="mission-purge-the-foe-vs-purge-the-foe-layout-1",
        attacker_player_id="player-alpha",
        attacker_force_disposition_id="purge-the-foe",
        defender_player_id="player-beta",
        defender_force_disposition_id="purge-the-foe",
    )
    layout_a_area_04 = next(
        area
        for area in setup.terrain_areas
        if area.terrain_area_id == "purge-the-foe-vs-purge-the-foe-layout-1-terrain-area-04"
    )

    assert layout_a_area_04.local_transform is TerrainAreaLocalTransform.MIRROR_Y_AXIS
    assert tuple(
        (round(point.x_inches, 9), round(point.y_inches, 9))
        for point in layout_a_area_04.footprint_polygon
    ) == (
        (34.0, 41.1),
        (40.0, 41.1),
        (40.0, 42.4),
        (40.5, 43.1),
        (40.1, 43.8),
        (40.3, 44.1),
        (40.0, 44.3),
        (40.0, 45.1),
        (37.3, 45.1),
        (37.2, 45.3),
        (36.8, 45.2),
        (36.0, 45.6),
        (35.2, 45.1),
        (34.0, 45.1),
    )


def test_phase17n_terrain_placements_use_reviewed_grid_symmetry_and_contacts() -> None:
    artifact = event_layouts.battlefield_artifact()
    meatgrinder_layouts = _meatgrinder_artifact_layouts()
    increment = artifact.source_coordinate_frame.terrain_placement_increment_inches

    assert increment == 0.05
    for layout in meatgrinder_layouts:
        areas_by_id = {area.area_id: area for area in layout.terrain_areas}
        components_by_id = {
            component.component_id: component for component in layout.terrain_components
        }
        for area in layout.terrain_areas:
            assert math.isclose(
                area.anchor_x_inches / increment,
                round(area.anchor_x_inches / increment),
                rel_tol=0.0,
                abs_tol=1e-9,
            )
            assert math.isclose(
                area.anchor_y_inches / increment,
                round(area.anchor_y_inches / increment),
                rel_tol=0.0,
                abs_tol=1e-9,
            )
            area_index = int(area.area_id.rsplit("-", maxsplit=1)[-1])
            if area_index > 8:
                continue
            mirror_area = areas_by_id[area.mirror_area_id]
            assert area.anchor_x_inches + mirror_area.anchor_x_inches == 44.0
            assert area.anchor_y_inches + mirror_area.anchor_y_inches == 60.0
            assert (mirror_area.rotation_degrees - area.rotation_degrees) % 360.0 == 180.0
            assert mirror_area.local_transform == area.local_transform
        for component in layout.terrain_components:
            assert math.isclose(
                component.battlefield_center_x_inches / increment,
                round(component.battlefield_center_x_inches / increment),
                rel_tol=0.0,
                abs_tol=1e-9,
            )
            assert math.isclose(
                component.battlefield_center_y_inches / increment,
                round(component.battlefield_center_y_inches / increment),
                rel_tol=0.0,
                abs_tol=1e-9,
            )
            area_index_text, _component_ordinal = component.component_id.rsplit(
                "-terrain-area-",
                maxsplit=1,
            )[1].split("-component-", maxsplit=1)
            area_index = int(area_index_text)
            if area_index > 8:
                continue
            expected_mirror_center = (
                44.0 - component.battlefield_center_x_inches,
                60.0 - component.battlefield_center_y_inches,
            )
            mirror_components = tuple(
                candidate
                for candidate in components_by_id.values()
                if candidate.terrain_area_id.endswith(f"area-{17 - area_index:02d}")
                and candidate.archetype_id == component.archetype_id
                and math.isclose(
                    candidate.battlefield_center_x_inches,
                    expected_mirror_center[0],
                    rel_tol=0.0,
                    abs_tol=1e-9,
                )
                and math.isclose(
                    candidate.battlefield_center_y_inches,
                    expected_mirror_center[1],
                    rel_tol=0.0,
                    abs_tol=1e-9,
                )
            )
            assert len(mirror_components) == 1
            mirror_component = mirror_components[0]
            assert math.isclose(
                (
                    mirror_component.battlefield_rotation_degrees
                    - component.battlefield_rotation_degrees
                )
                % 360.0,
                180.0,
                rel_tol=0.0,
                abs_tol=1e-9,
            )

    reviewed_anchors_by_layout = {
        1: {
            "04": (34.0, 41.1),
            "06": (16.85, 41.0),
            "07": (23.0, 42.5),
            "08": (4.85, 35.55),
        },
        2: {"02": (31.0, 50.0), "07": (17.55, 39.05)},
        3: {"02": (22.8, 50.05), "06": (9.5, 39.6)},
    }
    contact_pairs_by_layout = {
        1: (("04", "05"), ("06", "08"), ("09", "11"), ("12", "13")),
        2: (("01", "02"), ("05", "07"), ("10", "12"), ("15", "16")),
        3: (("02", "04"), ("06", "09"), ("08", "11"), ("13", "15")),
    }
    mission_pack = warhammer_event_companion_2026_07_mission_pack()
    for layout_number, reviewed_anchors in reviewed_anchors_by_layout.items():
        source_layout = meatgrinder_layouts[layout_number - 1]
        artifact_areas = {
            area.area_id.rsplit("-", maxsplit=1)[-1]: area for area in source_layout.terrain_areas
        }
        assert {
            area_suffix: (
                artifact_areas[area_suffix].anchor_x_inches,
                artifact_areas[area_suffix].anchor_y_inches,
            )
            for area_suffix in reviewed_anchors
        } == reviewed_anchors
        assert {
            frozenset(area_id.rsplit("-", maxsplit=1)[-1] for area_id in contact.terrain_area_ids)
            for contact in source_layout.terrain_area_contacts
        } == {frozenset(contact_pair) for contact_pair in contact_pairs_by_layout[layout_number]}

        setup = MissionSetup.from_mission_pack(
            mission_pack=mission_pack,
            mission_pool_entry_id=(
                f"mission-purge-the-foe-vs-purge-the-foe-layout-{layout_number}"
            ),
            attacker_player_id="player-alpha",
            attacker_force_disposition_id="purge-the-foe",
            defender_player_id="player-beta",
            defender_force_disposition_id="purge-the-foe",
        )
        runtime_areas = {
            area.terrain_area_id.rsplit("-", maxsplit=1)[-1]: area for area in setup.terrain_areas
        }
        for first_suffix, second_suffix in contact_pairs_by_layout[layout_number]:
            first = tuple(
                (point.x_inches, point.y_inches)
                for point in runtime_areas[first_suffix].footprint_polygon
            )
            second = tuple(
                (point.x_inches, point.y_inches)
                for point in runtime_areas[second_suffix].footprint_polygon
            )
            assert polygon_overlap_area(first, second) <= 1e-6
            assert (
                shapely_backend.footprint_for_polygon(first).distance(
                    shapely_backend.footprint_for_polygon(second)
                )
                <= increment
            )

        if layout_number == 1:
            light_pipe = shapely_backend.footprint_for_polygon(
                tuple(
                    (point.x_inches, point.y_inches)
                    for point in runtime_areas["08"].footprint_polygon
                )
            )
            mirrored_light_pipe = shapely_backend.footprint_for_polygon(
                tuple(
                    (point.x_inches, point.y_inches)
                    for point in runtime_areas["09"].footprint_polygon
                )
            )
            mixed = shapely_backend.footprint_for_polygon(
                tuple(
                    (point.x_inches, point.y_inches)
                    for point in runtime_areas["06"].footprint_polygon
                )
            )
            assert math.isclose(light_pipe.bounds[0], 4.0, rel_tol=0.0, abs_tol=0.05)
            assert math.isclose(
                44.0 - mirrored_light_pipe.bounds[2],
                4.0,
                rel_tol=0.0,
                abs_tol=0.05,
            )
            assert light_pipe.distance(mixed) <= 0.01
            assert light_pipe.intersection(mixed).is_empty


def test_phase17n_component_source_instances_bind_to_nearest_generated_placement() -> None:
    repository_root = REPOSITORY_ROOT
    extraction_payload = json.loads(
        (
            repository_root
            / "data/source_audits/event_companion_2026_06"
            / "phase17n_purge_the_foe_meatgrinder_pages_24_26_extraction.json"
        ).read_text(encoding="utf-8")
    )
    artifact_layouts = {layout.layout_id: layout for layout in _meatgrinder_artifact_layouts()}
    duplicate_source_group_count = 0
    source_instance_count = 0

    for source_layout in extraction_payload["layouts"]:
        artifact_components_by_id = {
            component.component_id: component
            for component in artifact_layouts[source_layout["layout_id"]].terrain_components
        }
        source_groups: dict[tuple[str, int], list[dict[str, Any]]] = {}
        for source_component in source_layout["terrain_components"]:
            source_instance_count += 1
            source_image = source_component["source_image"]
            artifact_component = artifact_components_by_id[source_component["component_id"]]
            source_bounds = source_image["pdf_page_bbox_points"]
            source_affine = source_image["pdf_page_affine_normalized_image_to_points"]
            assert artifact_component.source_pdf_image_xref == source_image["xref"]
            assert (
                artifact_component.source_pdf_bounds.x0_points,
                artifact_component.source_pdf_bounds.y0_points,
                artifact_component.source_pdf_bounds.x1_points,
                artifact_component.source_pdf_bounds.y1_points,
            ) == tuple(source_bounds)
            assert (
                artifact_component.source_pdf_affine.a,
                artifact_component.source_pdf_affine.b,
                artifact_component.source_pdf_affine.c,
                artifact_component.source_pdf_affine.d,
                artifact_component.source_pdf_affine.e,
                artifact_component.source_pdf_affine.f,
            ) == tuple(source_affine)
            source_groups.setdefault(
                (
                    source_component["terrain_area_id"],
                    source_component["source_image"]["xref"],
                ),
                [],
            ).append(source_component)

        for source_components in source_groups.values():
            if len(source_components) == 1:
                continue
            duplicate_source_group_count += 1
            ordered_source_components = sorted(
                source_components,
                key=lambda component: component["component_id"],
            )
            artifact_candidates = tuple(
                artifact_components_by_id[source_component["component_id"]]
                for source_component in ordered_source_components
            )
            scored_assignments: list[tuple[float, tuple[str, ...]]] = []
            for assignment in permutations(artifact_candidates):
                score = sum(
                    math.dist(
                        tuple(source_component["source_image"]["battlefield_image_center_inches"]),
                        (
                            artifact_component.battlefield_center_x_inches,
                            artifact_component.battlefield_center_y_inches,
                        ),
                    )
                    ** 2
                    for source_component, artifact_component in zip(
                        ordered_source_components,
                        assignment,
                        strict=True,
                    )
                )
                scored_assignments.append(
                    (score, tuple(component.component_id for component in assignment))
                )
            scored_assignments.sort()
            assert scored_assignments[0][1] == tuple(
                component["component_id"] for component in ordered_source_components
            )
            assert not math.isclose(
                scored_assignments[0][0],
                scored_assignments[1][0],
                rel_tol=0.0,
                abs_tol=1e-9,
            )

    assert duplicate_source_group_count == 6
    assert source_instance_count == 90


def test_phase17n_exact_terrain_areas_drive_visibility_cover_and_typed_evidence() -> None:
    mission_pack = warhammer_event_companion_2026_07_mission_pack()
    setup = MissionSetup.from_mission_pack(
        mission_pack=mission_pack,
        mission_pool_entry_id="mission-purge-the-foe-vs-purge-the-foe-layout-1",
        attacker_player_id="player-alpha",
        attacker_force_disposition_id="purge-the-foe",
        defender_player_id="player-beta",
        defender_force_disposition_id="purge-the-foe",
    )
    ruleset = RulesetDescriptor.warhammer_40000_eleventh(
        descriptor_version="phase17n-exact-terrain-visibility",
    )
    areas = {area.terrain_area_id: area for area in setup.terrain_areas}
    dense_area = areas["purge-the-foe-vs-purge-the-foe-layout-1-terrain-area-01"]
    mixed_area = areas["purge-the-foe-vs-purge-the-foe-layout-1-terrain-area-02"]
    light_area = areas["purge-the-foe-vs-purge-the-foe-layout-1-terrain-area-08"]
    visibility_areas = {
        area.terrain_area_id: area
        for area in terrain_visibility_areas_from_placements(setup.terrain_areas)
    }
    dense_visibility_area = visibility_areas[dense_area.logical_terrain_area_id]
    mixed_visibility_area = visibility_areas[mixed_area.logical_terrain_area_id]
    light_visibility_area = visibility_areas[light_area.logical_terrain_area_id]

    def model(model_id: str, x: float, y: float) -> Model:
        return Model(
            model_id=model_id,
            pose=Pose.at(x=x, y=y),
            base=CircularBase(radius=0.35),
            volume=ModelVolume(height=2.0),
        )

    target_in_dense_gap = TerrainVisibilityContext.from_ruleset_descriptor(
        ruleset_descriptor=ruleset,
        los_cache_key="los:phase17n-dense-gap",
        observer_model=model("observer", 29.0, 51.6),
        target_models=(model("target", 31.5, 51.6),),
        target_model_keywords=(("target", ("INFANTRY",)),),
        terrain_features=setup.terrain_features,
        terrain_areas=tuple(visibility_areas.values()),
    )
    round_tripped = TerrainVisibilityContext.from_payload(target_in_dense_gap.to_payload())
    dense_witness = round_tripped.resolve_line_of_sight()
    dense_cover = round_tripped.benefit_of_cover(dense_witness)

    assert round_tripped == target_in_dense_gap
    assert dense_witness.unit_visible
    assert dense_witness.unit_fully_visible
    assert dense_cover.has_benefit
    assert dense_cover.source_feature_ids == ()
    assert dense_cover.source_terrain_area_ids == (dense_area.terrain_area_id,)
    assert any(
        record.blocker_kind is VisibilityBlockerKind.TERRAIN_AREA
        and record.terrain_area_id == dense_area.terrain_area_id
        and record.exception_applied == "target_intersects_area"
        for record in dense_witness.all_blocker_records()
    )

    blocked_through_dense = TerrainVisibilityContext.from_ruleset_descriptor(
        ruleset_descriptor=ruleset,
        los_cache_key="los:phase17n-through-dense",
        observer_model=model("observer", 28.0, 53.0),
        target_models=(model("target", 39.0, 53.0),),
        target_model_keywords=(("target", ("INFANTRY",)),),
        terrain_areas=(dense_visibility_area,),
    ).resolve_line_of_sight()
    assert not blocked_through_dense.unit_visible
    assert any(
        record.blocker_kind is VisibilityBlockerKind.TERRAIN_AREA
        and record.terrain_area_classification is TerrainAreaClassification.DENSE
        and record.blocks_model_visibility
        for record in blocked_through_dense.all_blocker_records()
    )

    for observer_xy, target_xy, expected_exception in (
        ((31.5, 51.6), (29.0, 51.6), "observer_intersects_area"),
        ((29.0, 51.6), (31.5, 51.6), "target_intersects_area"),
    ):
        exception_witness = TerrainVisibilityContext.from_ruleset_descriptor(
            ruleset_descriptor=ruleset,
            los_cache_key=f"los:phase17n-{expected_exception}",
            observer_model=model("observer", *observer_xy),
            target_models=(model("target", *target_xy),),
            target_model_keywords=(("target", ("INFANTRY",)),),
            terrain_areas=(dense_visibility_area,),
        ).resolve_line_of_sight()
        assert exception_witness.unit_visible
        assert any(
            record.exception_applied == expected_exception
            for record in exception_witness.all_blocker_records()
        )

    mixed_context = TerrainVisibilityContext.from_ruleset_descriptor(
        ruleset_descriptor=ruleset,
        los_cache_key="los:phase17n-mixed",
        observer_model=model("observer", 17.5, 45.3),
        target_models=(model("target", 18.1, 45.3),),
        target_model_keywords=(("target", ("INFANTRY",)),),
        terrain_areas=(mixed_visibility_area,),
    )
    mixed_witness = mixed_context.resolve_line_of_sight()
    mixed_cover = mixed_context.benefit_of_cover(mixed_witness)
    assert mixed_witness.unit_visible
    assert mixed_cover.has_benefit
    assert mixed_cover.source_terrain_area_ids == (mixed_area.terrain_area_id,)
    assert any(
        record.terrain_area_classification is TerrainAreaClassification.MIXED
        for record in mixed_witness.all_blocker_records()
    )

    light_context = TerrainVisibilityContext.from_ruleset_descriptor(
        ruleset_descriptor=ruleset,
        los_cache_key="los:phase17n-light",
        observer_model=model("observer", 2.0, 33.0),
        target_models=(model("target", 7.0, 33.0),),
        target_model_keywords=(("target", ("INFANTRY",)),),
        terrain_areas=(light_visibility_area,),
    )
    light_witness = light_context.resolve_line_of_sight()
    light_cover = light_context.benefit_of_cover(light_witness)
    assert light_witness.unit_visible
    assert light_cover.has_benefit
    assert light_cover.source_terrain_area_ids == (light_area.terrain_area_id,)
    assert any(
        record.terrain_area_classification is TerrainAreaClassification.LIGHT
        and record.exception_applied == "target_intersects_area"
        for record in light_witness.all_blocker_records()
    )

    blocked_through_light = TerrainVisibilityContext.from_ruleset_descriptor(
        ruleset_descriptor=ruleset,
        los_cache_key="los:phase17n-through-light",
        observer_model=model("observer", 2.0, 33.0),
        target_models=(model("target", 13.0, 33.0),),
        target_model_keywords=(("target", ("INFANTRY",)),),
        terrain_areas=(light_visibility_area,),
    ).resolve_line_of_sight()
    assert not blocked_through_light.unit_visible
    assert any(
        record.terrain_area_classification is TerrainAreaClassification.LIGHT
        and record.blocks_model_visibility
        for record in blocked_through_light.all_blocker_records()
    )

    assert model_within_solid_terrain(
        ruleset_descriptor=ruleset,
        model=model("dense-model", 31.5, 51.6),
        terrain_features=(),
        terrain_areas=(dense_area,),
    )
    assert model_within_solid_terrain(
        ruleset_descriptor=ruleset,
        model=model("mixed-model", 18.1, 45.3),
        terrain_features=(),
        terrain_areas=(mixed_area,),
    )
    assert not model_within_solid_terrain(
        ruleset_descriptor=ruleset,
        model=model("light-model", 7.0, 33.0),
        terrain_features=(),
        terrain_areas=(light_area,),
    )


def test_phase17n_unknown_terrain_area_classification_does_not_gate_membership_cover() -> None:
    mission_pack = warhammer_event_companion_2026_07_mission_pack()
    setup = MissionSetup.from_mission_pack(
        mission_pack=mission_pack,
        mission_pool_entry_id="mission-purge-the-foe-vs-purge-the-foe-layout-1",
        attacker_player_id="player-alpha",
        attacker_force_disposition_id="purge-the-foe",
        defender_player_id="player-beta",
        defender_force_disposition_id="purge-the-foe",
    )
    physical_light_area = next(
        area
        for area in setup.terrain_areas
        if area.terrain_area_id == "purge-the-foe-vs-purge-the-foe-layout-1-terrain-area-08"
    )
    exact_light_area = next(
        area
        for area in terrain_visibility_areas_from_placements(setup.terrain_areas)
        if area.terrain_area_id == physical_light_area.logical_terrain_area_id
    )
    unknown_area = replace(
        exact_light_area,
        classification=TerrainAreaClassification.UNKNOWN,
    )
    context = TerrainVisibilityContext.from_ruleset_descriptor(
        ruleset_descriptor=RulesetDescriptor.warhammer_40000_eleventh(
            descriptor_version="phase17n-unknown-area-membership-cover",
        ),
        los_cache_key="los:phase17n-unknown-area-membership-cover",
        observer_model=Model(
            model_id="observer",
            pose=Pose.at(x=2.0, y=33.0),
            base=CircularBase(radius=0.35),
            volume=ModelVolume(height=2.0),
        ),
        target_models=(
            Model(
                model_id="target",
                pose=Pose.at(x=7.0, y=33.0),
                base=CircularBase(radius=0.35),
                volume=ModelVolume(height=2.0),
            ),
        ),
        target_model_keywords=(("target", ("INFANTRY",)),),
        terrain_areas=(unknown_area,),
    )

    witness = context.resolve_line_of_sight()
    cover = context.benefit_of_cover(witness)

    assert witness.unit_visible
    assert witness.unit_fully_visible
    assert witness.all_blocker_records() == ()
    assert cover.has_benefit
    assert cover.source_terrain_area_ids == (unknown_area.terrain_area_id,)
    assert len(cover.source_records) == 1
    source_record = cover.source_records[0]
    assert type(source_record) is TerrainAreaCoverSourceRecord
    assert source_record.classification is TerrainAreaClassification.UNKNOWN
    assert source_record.policy_kind is LineOfSightPolicy.TRUE_LINE_OF_SIGHT
    assert source_record.reason is CoverSourceReason.WITHIN_TERRAIN_AREA
    disabled_cover_policy = replace(
        context.terrain_visibility_policy,
        cover_policy=replace(
            context.terrain_visibility_policy.cover_policy,
            grants_benefit_of_cover=False,
        ),
    )
    assert not BenefitOfCoverResult.from_cover_sources(
        witness=witness,
        terrain_visibility_policy=disabled_cover_policy,
        source_records=cover.source_records,
    ).has_benefit


def test_phase17n_visibility_resolves_feature_area_associations_once_per_query(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    mission_pack = warhammer_event_companion_2026_07_mission_pack()
    setup = MissionSetup.from_mission_pack(
        mission_pack=mission_pack,
        mission_pool_entry_id="mission-purge-the-foe-vs-purge-the-foe-layout-1",
        attacker_player_id="player-alpha",
        attacker_force_disposition_id="purge-the-foe",
        defender_player_id="player-beta",
        defender_force_disposition_id="purge-the-foe",
    )
    visibility_areas = terrain_visibility_areas_from_placements(setup.terrain_areas)
    terrain_features = setup.terrain_features[:2]
    association_check_count = 0

    def counting_polygon_within_union(
        inner: tuple[tuple[float, float], ...],
        outers: tuple[tuple[tuple[float, float], ...], ...],
    ) -> bool:
        nonlocal association_check_count
        association_check_count += 1
        return visibility_polygon_within_union(inner, outers)

    monkeypatch.setattr(
        terrain_area_visibility,
        "visibility_polygon_within_union",
        counting_polygon_within_union,
    )

    witness = TerrainVisibilityContext.from_ruleset_descriptor(
        ruleset_descriptor=RulesetDescriptor.warhammer_40000_eleventh(
            descriptor_version="phase17n-feature-area-association-cache",
        ),
        los_cache_key="los:phase17n-feature-area-association-cache",
        observer_model=Model(
            model_id="observer",
            pose=Pose.at(x=2.0, y=2.0),
            base=CircularBase(radius=0.35),
            volume=ModelVolume(height=2.0),
        ),
        target_models=(
            Model(
                model_id="target-a",
                pose=Pose.at(x=42.0, y=58.0),
                base=CircularBase(radius=0.35),
                volume=ModelVolume(height=2.0),
            ),
            Model(
                model_id="target-b",
                pose=Pose.at(x=40.0, y=56.0),
                base=CircularBase(radius=0.35),
                volume=ModelVolume(height=2.0),
            ),
        ),
        target_model_keywords=(
            ("target-a", ("INFANTRY",)),
            ("target-b", ("INFANTRY",)),
        ),
        terrain_features=terrain_features,
        terrain_areas=visibility_areas,
    ).resolve_line_of_sight()

    assert witness.target_model_ids == ("target-a", "target-b")
    assert 0 < association_check_count <= (len(terrain_features) * len(visibility_areas))


def test_phase17j_terrain_area_footprint_templates_match_source_polygons() -> None:
    templates = {
        template.footprint_template_id: template
        for template in event_source.terrain_area_footprint_templates()
    }
    expected_templates = {
        "FOOTPRINT_6X2": (
            6.1,
            2.7,
            (
                (-3.05, 1.15),
                (-2.05, 1.15),
                (-2.05, 1.35),
                (-1.05, 1.35),
                (-1.05, 1.15),
                (3.05, 1.15),
                (3.05, -0.85),
                (2.15, -0.85),
                (1.3, -1.35),
                (0.45, -0.85),
                (-3.05, -0.85),
            ),
        ),
        "FOOTPRINT_6X4": (
            6.5,
            4.5,
            (
                (-3.25, 2.25),
                (2.75, 2.25),
                (2.75, 0.95),
                (3.25, 0.25),
                (2.85, -0.45),
                (3.05, -0.75),
                (2.75, -0.95),
                (2.75, -1.75),
                (0.05, -1.75),
                (-0.05, -1.95),
                (-0.45, -1.85),
                (-1.25, -2.25),
                (-2.05, -1.75),
                (-3.25, -1.75),
            ),
        ),
        "FOOTPRINT_10X2_5": (
            10.0,
            3.6,
            (
                (-5.0, 1.2),
                (-4.5, 1.2),
                (-4.5, 1.3),
                (-3.0, 1.8),
                (-2.5, 1.2),
                (2.4, 1.2),
                (2.6, 1.45),
                (3.3, 1.2),
                (5.0, 1.2),
                (5.0, -1.3),
                (2.15, -1.3),
                (1.85, -1.6),
                (0.85, -1.8),
                (0.5, -1.3),
                (-5.0, -1.3),
            ),
        ),
        "FOOTPRINT_7X11_5": (
            7.6,
            11.5,
            (
                (-3.8, 5.75),
                (3.2, 5.75),
                (3.2, 4.65),
                (3.5, 4.05),
                (3.45, 3.75),
                (3.8, 2.75),
                (3.2, 2.25),
                (3.2, 1.45),
                (3.3, 0.75),
                (3.2, 0.05),
                (3.7, -1.15),
                (3.2, -2.25),
                (3.2, -5.75),
                (-3.8, -5.75),
            ),
        ),
        "FOOTPRINT_8X11_5_POLYGON": (
            12.0,
            8.0,
            (
                (-5.5, 4.0),
                (6.0, 4.0),
                (6.0, 2.0),
                (5.5, 2.0),
                (-5.0, -4.0),
                (-5.5, -4.0),
                (-5.5, -1.8),
                (-6.0, -0.6),
                (-5.5, 0.0),
            ),
        ),
    }

    assert set(templates) == set(expected_templates)
    for template_id, (width, depth, expected_vertices) in expected_templates.items():
        template = templates[template_id]
        assert template.bounding_width_inches == width
        assert template.bounding_depth_inches == depth
        assert _terrain_display_points(template.polygon_vertices_inches) == expected_vertices


def test_phase17j_layout_descriptors_cover_all_source_hashed_battlefields() -> None:
    descriptors = event_source.layout_descriptor_rows()
    artifact_layouts_by_id = {
        layout.layout_id: layout for layout in event_layouts.battlefield_artifact().layouts
    }

    assert len(descriptors) == 45
    assert {descriptor.layout_variant for descriptor in descriptors} == {"a", "b", "c"}
    assert {descriptor.source_page for descriptor in descriptors} == set(range(9, 54))
    assert all(
        descriptor.geometry_extraction_status == "source_hashed_battlefield_artifact_geometry"
        for descriptor in descriptors
    )
    for descriptor in descriptors:
        source_layout = artifact_layouts_by_id[descriptor.layout_id]
        assert descriptor.source_page == source_layout.source_page
        assert descriptor.battlefield_width_inches == 44.0
        assert descriptor.battlefield_depth_inches == 60.0
        assert descriptor.attacker_edge == source_layout.attacker_edge
        assert descriptor.defender_edge == source_layout.defender_edge
        assert len(descriptor.terrain_features) == len(source_layout.terrain_components)
        assert len(descriptor.objective_points) == len(source_layout.objectives)


def test_phase17j_quarter_circle_cutout_vertices_cover_supported_corners() -> None:
    lower_right = _source_rectangle_with_quarter_circle_cutout_vertices(
        min_x=0.0,
        min_y=0.0,
        max_x=22.0,
        max_y=30.0,
        corner="lower_right",
        radius=event_source.LAYOUT_C_DEPLOYMENT_CUTOUT_RADIUS_INCHES,
    )
    upper_left = _source_rectangle_with_quarter_circle_cutout_vertices(
        min_x=0.0,
        min_y=0.0,
        max_x=22.0,
        max_y=30.0,
        corner="upper_left",
        radius=event_source.LAYOUT_C_DEPLOYMENT_CUTOUT_RADIUS_INCHES,
    )

    assert lower_right[0] == (0.0, 0.0)
    assert lower_right[-2:] == ((22.0, 30.0), (0.0, 30.0))
    assert upper_left[:3] == ((0.0, 0.0), (22.0, 0.0), (22.0, 30.0))
    assert upper_left[-1] == (0.0, 21.0)

    with pytest.raises(MissionPackError, match="Unsupported quarter-circle cutout corner"):
        _source_rectangle_with_quarter_circle_cutout_vertices(
            min_x=0.0,
            min_y=0.0,
            max_x=22.0,
            max_y=30.0,
            corner="upper_center",
            radius=event_source.LAYOUT_C_DEPLOYMENT_CUTOUT_RADIUS_INCHES,
        )


def test_phase17j_base_size_source_kinds_cover_noncanonical_entries() -> None:
    assert _source_base_source_kind_and_geometry("Use model") == (
        "use_model",
        event_source.GeometryResolutionStatus.REQUIRES_PROJECT_GEOMETRY_OVERRIDE,
        None,
    )
    assert _source_base_source_kind_and_geometry("No official base size") == (
        "no_official_base_size",
        event_source.GeometryResolutionStatus.UNSUPPORTED_FOR_PHYSICAL_GEOMETRY,
        None,
    )
    assert _source_base_source_kind_and_geometry("Tactical Rock") == (
        "unresolved_source_shape",
        event_source.GeometryResolutionStatus.UNSUPPORTED_FOR_PHYSICAL_GEOMETRY,
        None,
    )


def test_phase17n_objective_bindings_require_complete_logical_terrain_areas() -> None:
    mission_pack = warhammer_event_companion_2026_07_mission_pack()
    layout_id = "take-and-hold-vs-take-and-hold-layout-2"
    layout = mission_pack.battlefield_layout(layout_id)
    complete_binding = next(
        binding for binding in layout.objective_terrain_areas if len(binding.terrain_area_ids) > 1
    )
    partial_binding = replace(
        complete_binding,
        terrain_area_ids=complete_binding.terrain_area_ids[1:],
    )
    partial_layout_bindings = tuple(
        partial_binding if binding == complete_binding else binding
        for binding in layout.objective_terrain_areas
    )

    with pytest.raises(MissionPackError, match="every physical member"):
        replace(layout, objective_terrain_areas=partial_layout_bindings)

    setup = MissionSetup.from_mission_pack(
        mission_pack=mission_pack,
        mission_pool_entry_id=f"mission-{layout_id}",
        attacker_player_id="player-alpha",
        attacker_force_disposition_id="take-and-hold",
        defender_player_id="player-beta",
        defender_force_disposition_id="take-and-hold",
    )
    with pytest.raises(MissionSetupError, match="every physical member"):
        replace(
            setup,
            objective_terrain_areas=tuple(
                partial_binding if binding == complete_binding else binding
                for binding in setup.objective_terrain_areas
            ),
        )

    retained_area_id = complete_binding.terrain_area_ids[-1]
    relabelled_setup = replace(
        setup,
        terrain_areas=tuple(
            replace(area, logical_terrain_area_id=retained_area_id)
            if area.terrain_area_id == retained_area_id
            else area
            for area in setup.terrain_areas
            if area.terrain_area_id not in complete_binding.terrain_area_ids[:-1]
        ),
        objective_terrain_areas=tuple(
            replace(binding, terrain_area_ids=(retained_area_id,))
            if binding.objective_marker_id == complete_binding.objective_marker_id
            else binding
            for binding in setup.objective_terrain_areas
        ),
    )
    with pytest.raises(MissionSetupError, match="battlefield geometry drifted from source"):
        validate_mission_setup_source_layout(relabelled_setup)

    with pytest.raises(MissionSetupError, match="requires battlefield_layout_id"):
        replace(setup, battlefield_layout_id=None)

    layoutless_source_components = replace(
        setup,
        battlefield_layout_id=None,
        battlefield_regions=(),
        terrain_areas=(),
        terrain_features=(),
        objective_terrain_areas=(),
    )
    with pytest.raises(GameLifecycleError, match="component identities require"):
        validate_mission_setup_source_layout(layoutless_source_components)

    drifted_assignments = tuple(
        replace(assignment, primary_mission_id="primary-meatgrinder")
        if assignment.player_id == setup.attacker_player_id
        else assignment
        for assignment in setup.primary_mission_assignments
    )
    with pytest.raises(GameLifecycleError, match="Primary mission assignment drifted"):
        validate_mission_setup_source_layout(
            replace(setup, primary_mission_assignments=drifted_assignments)
        )

    bound_area_ids = {
        terrain_area_id
        for binding in setup.objective_terrain_areas
        for terrain_area_id in binding.terrain_area_ids
    }
    unbound_area = next(
        area for area in setup.terrain_areas if area.terrain_area_id not in bound_area_ids
    )
    x_shift = 0.05 if unbound_area.center_x_inches < 22.0 else -0.05
    shifted_area = replace(
        unbound_area,
        center_x_inches=unbound_area.center_x_inches + x_shift,
        footprint_polygon=tuple(
            replace(point, x_inches=point.x_inches + x_shift)
            for point in unbound_area.footprint_polygon
        ),
    )
    shifted_setup = replace(
        setup,
        terrain_areas=tuple(
            shifted_area if area == unbound_area else area for area in setup.terrain_areas
        ),
    )
    with pytest.raises(MissionSetupError, match="battlefield geometry drifted from source"):
        validate_mission_setup_source_layout(shifted_setup)

    with pytest.raises(MissionSetupError, match="battlefield geometry drifted from source"):
        validate_mission_setup_source_layout(replace(setup, terrain_features=()))

    canonical_feature = setup.terrain_features[0]
    custom_setup = replace(
        setup,
        battlefield_layout_id=None,
        deployment_map_id="custom-event-companion-deployment-map",
        terrain_layout_id="custom-event-companion-terrain-layout",
        terrain_areas=(),
        objective_terrain_areas=(),
        terrain_features=(canonical_feature,),
    )
    validate_mission_setup_source_layout(custom_setup)
    with pytest.raises(GameLifecycleError, match="Primary mission assignment drifted"):
        validate_mission_setup_source_layout(
            replace(
                custom_setup,
                primary_mission_assignments=tuple(
                    replace(assignment, primary_mission_id="primary-death-trap")
                    for assignment in custom_setup.primary_mission_assignments
                ),
            )
        )
    with pytest.raises(GameLifecycleError, match="source package identity drifted"):
        validate_mission_setup_source_layout(replace(custom_setup, source_version="drifted"))
    custom_meatgrinder_setup = replace(
        custom_setup,
        mission_pool_entry_id="mission-purge-the-foe-vs-purge-the-foe-layout-2",
        primary_mission_assignments=tuple(
            replace(
                assignment,
                force_disposition_id="purge-the-foe",
                primary_mission_id="primary-meatgrinder",
            )
            for assignment in custom_setup.primary_mission_assignments
        ),
    )
    validate_mission_setup_source_layout(custom_meatgrinder_setup)

    with pytest.raises(GameLifecycleError, match="canonical battlefield region identity drifted"):
        validate_mission_setup_source_layout(
            replace(
                custom_setup,
                battlefield_regions=(
                    replace(
                        custom_setup.battlefield_regions[0],
                        source_id="test:drifted-event-companion-region",
                    ),
                    *custom_setup.battlefield_regions[1:],
                ),
            )
        )

    with pytest.raises(GameLifecycleError, match="canonical terrain feature identity drifted"):
        validate_mission_setup_source_layout(
            replace(
                custom_setup,
                terrain_features=(
                    replace(
                        canonical_feature,
                        classification=TerrainAreaClassification.UNKNOWN,
                    ),
                ),
            )
        )

    with pytest.raises(GameLifecycleError, match="must not reuse source-backed provenance"):
        validate_mission_setup_source_layout(
            replace(
                custom_setup,
                terrain_features=(
                    replace(
                        canonical_feature,
                        feature_id="custom-event-companion-feature",
                        classification=TerrainAreaClassification.UNKNOWN,
                        source_id=mission_pack.terrain_feature_presets[0].source_id,
                    ),
                ),
            )
        )


def test_phase17j_objective_role_payload_is_required() -> None:
    marker = (
        warhammer_event_companion_2026_07_mission_pack()
        .battlefield_layout("take-and-hold-vs-take-and-hold-layout-1")
        .objective_markers[0]
    )
    payload = dict(marker.to_payload())
    payload.pop("objective_role")

    with pytest.raises(MissionPackError, match="objective_role"):
        type(marker).from_payload(cast(ObjectiveMarkerDefinitionPayload, payload))


def test_phase17j_centre_and_center_objective_roles_normalize_to_central() -> None:
    assert objective_marker_role_from_token("center") is ObjectiveMarkerRole.CENTRAL
    assert objective_marker_role_from_token("centre") is ObjectiveMarkerRole.CENTRAL


def test_phase17j_placed_terrain_area_payload_must_match_template_transform() -> None:
    mission_pack = warhammer_event_companion_2026_07_mission_pack()
    layout = mission_pack.battlefield_layout("take-and-hold-vs-take-and-hold-layout-1")
    first_area, second_area, *remaining_areas = layout.terrain_areas
    drifted_area = replace(
        first_area,
        footprint_polygon=second_area.footprint_polygon,
    )
    drifted_layout = replace(
        layout,
        terrain_areas=(drifted_area, second_area, *remaining_areas),
    )

    with pytest.raises(MissionPackError, match="template transform"):
        replace(
            mission_pack,
            battlefield_layouts=tuple(
                drifted_layout
                if candidate.battlefield_layout_id == drifted_layout.battlefield_layout_id
                else candidate
                for candidate in mission_pack.battlefield_layouts
            ),
        )


def test_phase17j_layout_must_match_deployment_map_objective_geometry() -> None:
    mission_pack = warhammer_event_companion_2026_07_mission_pack()
    layout = mission_pack.battlefield_layout("take-and-hold-vs-take-and-hold-layout-1")
    deployment_map = mission_pack.deployment_map(layout.deployment_map_id)
    first_marker, *remaining_markers = deployment_map.objective_markers
    drifted_marker = replace(
        first_marker,
        x_inches=first_marker.x_inches + 0.25,
    )
    drifted_map = replace(
        deployment_map,
        objective_markers=(drifted_marker, *remaining_markers),
    )

    with pytest.raises(MissionPackError, match="objective markers"):
        replace(
            mission_pack,
            deployment_maps=tuple(
                drifted_map
                if candidate.deployment_map_id == drifted_map.deployment_map_id
                else candidate
                for candidate in mission_pack.deployment_maps
            ),
        )


def test_phase17j_layout_must_match_deployment_map_zone_geometry() -> None:
    mission_pack = warhammer_event_companion_2026_07_mission_pack()
    layout = mission_pack.battlefield_layout("take-and-hold-vs-take-and-hold-layout-2")
    deployment_map = mission_pack.deployment_map(layout.deployment_map_id)
    defender_zone = next(
        zone for zone in deployment_map.deployment_zones if zone.player_id == "defender"
    )
    drifted_zone = replace(
        defender_zone,
        shape=DeploymentZoneShape.rectangle(
            min_x=31.0,
            min_y=0.0,
            max_x=44.0,
            max_y=60.0,
        ),
    )
    drifted_map = replace(
        deployment_map,
        deployment_zones=tuple(
            drifted_zone if zone.deployment_zone_id == drifted_zone.deployment_zone_id else zone
            for zone in deployment_map.deployment_zones
        ),
    )

    with pytest.raises(MissionPackError, match="deployment zones"):
        replace(
            mission_pack,
            deployment_maps=tuple(
                drifted_map
                if candidate.deployment_map_id == drifted_map.deployment_map_id
                else candidate
                for candidate in mission_pack.deployment_maps
            ),
        )


def test_phase17j_card_amendments_are_separate_from_faq_patch_rows() -> None:
    amendment_set = event_source.card_amendment_set()
    faq_patches = event_companion_patches.faq_patch_rows()

    assert amendment_set.amendments == ()
    assert amendment_set.source_page == 4
    assert {patch.patch_id for patch in faq_patches} == {
        "faq-end-of-battle-vp-round-cap-exemption",
        "faq-operation-marker-removal-clears-status",
        "faq-operation-marker-removal-requires-card-permission",
        "faq-death-trap-trapped-area-scoring-window",
        "faq-surveil-the-foe-same-turn-marker-removal",
        "faq-vital-link-multiple-central-objectives",
    }
    assert {patch.behavior_descriptor for patch in faq_patches} == {
        "end_of_battle_vp_exempt_from_battle_round_cap",
        "operation_marker_removal_clears_applied_status",
        "operation_marker_removal_requires_primary_card_permission",
        "death_trap_trapped_area_checked_at_scoring_not_destruction_time",
        "surveil_the_foe_same_turn_marker_removal_allows_scoring",
        "vital_link_multiple_central_objectives_marker_control_allows_cumulative_vp",
    }
    assert all(patch.source_page == 4 for patch in faq_patches)
    assert all(
        patch.source_id.startswith("gw-11e-warhammer-event-companion-v1-1-2026-07:faq:")
        for patch in faq_patches
    )


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
        event_source.PrimaryMissionScoringCoverageStatus.ENGINE_IMPLEMENTED: 25,
        event_source.PrimaryMissionScoringCoverageStatus.SOURCE_KNOWN_ENGINE_PENDING: 0,
        event_source.PrimaryMissionScoringCoverageStatus.AWAITING_SOURCE: 0,
    }
    assert {
        row.primary_mission_id
        for row in coverage_rows.values()
        if row.status is event_source.PrimaryMissionScoringCoverageStatus.AWAITING_SOURCE
    } == set()
    assert {
        row.primary_mission_id
        for row in coverage_rows.values()
        if row.status
        is event_source.PrimaryMissionScoringCoverageStatus.SOURCE_KNOWN_ENGINE_PENDING
    } == set()
    assert {
        mission_id: len(primary_rows[mission_id].scoring_rules)
        for mission_id in (
            "primary-unstoppable-force",
            "primary-battlefield-dominance",
            "primary-meatgrinder",
            "primary-punishment",
            "primary-consecrate",
            "primary-destroyers-wrath",
            "primary-determined-acquisition",
            "primary-outmaneuver",
            "primary-delaying-action",
            "primary-locate-and-deny",
            "primary-smoke-and-mirrors",
            "primary-reconnaissance-sweep",
            "primary-surveil-the-foe",
            "primary-triangulation",
            "primary-gather-intel",
            "primary-search-and-scour",
            "primary-purge-and-secure",
            "primary-inescapable-dominion",
            "primary-extract-relic",
            "primary-sabotage",
            "primary-secure-asset",
            "primary-vanguard-operation",
            "primary-vital-link",
        )
    } == {
        "primary-unstoppable-force": 4,
        "primary-battlefield-dominance": 3,
        "primary-meatgrinder": 4,
        "primary-punishment": 4,
        "primary-consecrate": 5,
        "primary-destroyers-wrath": 4,
        "primary-determined-acquisition": 3,
        "primary-outmaneuver": 4,
        "primary-delaying-action": 3,
        "primary-locate-and-deny": 4,
        "primary-smoke-and-mirrors": 4,
        "primary-reconnaissance-sweep": 4,
        "primary-surveil-the-foe": 4,
        "primary-triangulation": 5,
        "primary-gather-intel": 5,
        "primary-search-and-scour": 4,
        "primary-purge-and-secure": 4,
        "primary-inescapable-dominion": 4,
        "primary-extract-relic": 5,
        "primary-sabotage": 3,
        "primary-secure-asset": 4,
        "primary-vanguard-operation": 4,
        "primary-vital-link": 5,
    }
    assert primary_rows["primary-meatgrinder"].scoring_kind == ("meatgrinder")
    assert primary_rows["primary-battlefield-dominance"].scoring_kind == ("battlefield_dominance")
    assert primary_rows["primary-purge-and-secure"].scoring_kind == ("purge_and_secure")
    assert primary_rows["primary-consecrate"].scoring_kind == "consecrate"
    assert primary_rows["primary-smoke-and-mirrors"].scoring_kind == "smoke_and_mirrors"
    assert primary_rows["primary-triangulation"].scoring_kind == "triangulation"
    assert primary_rows["primary-sabotage"].scoring_kind == "sabotage"
    assert primary_rows["primary-secure-asset"].scoring_kind == "secure_asset"
    assert primary_rows["primary-vanguard-operation"].scoring_kind == "vanguard_operation"
    assert primary_rows["primary-punishment"].scoring_kind == "punishment"
    assert primary_rows["primary-extract-relic"].scoring_kind == "extract_relic"
    assert primary_rows["primary-gather-intel"].scoring_kind == "gather_intel"
    assert primary_rows["primary-locate-and-deny"].scoring_kind == "locate_and_deny"
    assert primary_rows["primary-vital-link"].scoring_kind == "vital_link"
    assert primary_rows["primary-surveil-the-foe"].scoring_kind == "surveil_the_foe"
    assert coverage_rows["primary-unstoppable-force"].needed_work == ()
    assert coverage_rows["primary-meatgrinder"].needed_work == ()
    assert coverage_rows["primary-death-trap"].mission_action_count == 1
    assert coverage_rows["primary-smoke-and-mirrors"].mission_action_count == 1
    assert coverage_rows["primary-gather-intel"].mission_action_count == 1
    assert coverage_rows["primary-surveil-the-foe"].mission_action_count == 1
    assert coverage_rows["primary-locate-and-deny"].mission_action_count == 1
    assert coverage_rows["primary-extract-relic"].mission_action_count == 1
    assert coverage_rows["primary-sabotage"].mission_action_count == 1
    assert coverage_rows["primary-secure-asset"].mission_action_count == 1
    assert coverage_rows["primary-vanguard-operation"].mission_action_count == 1
    assert coverage_rows["primary-vital-link"].mission_action_count == 1
    for implemented_mission_id in (
        "primary-battlefield-dominance",
        "primary-consecrate",
        "primary-delaying-action",
        "primary-destroyers-wrath",
        "primary-determined-acquisition",
        "primary-inescapable-dominion",
        "primary-outmaneuver",
        "primary-purge-and-secure",
        "primary-reconnaissance-sweep",
        "primary-search-and-scour",
        "primary-smoke-and-mirrors",
        "primary-triangulation",
        "primary-sabotage",
        "primary-secure-asset",
        "primary-vanguard-operation",
        "primary-punishment",
        "primary-extract-relic",
        "primary-gather-intel",
        "primary-locate-and-deny",
        "primary-vital-link",
        "primary-surveil-the-foe",
    ):
        assert coverage_rows[implemented_mission_id].needed_work == ()
    assert {
        mission_id: row.needed_work
        for mission_id, row in coverage_rows.items()
        if row.status
        is event_source.PrimaryMissionScoringCoverageStatus.SOURCE_KNOWN_ENGINE_PENDING
    } == {}


__all__: list[str] = []
__all__ += ["BattlefieldLayoutDefinition", "Callable", "DeploymentZonePoint"]
__all__ += ["DeploymentZonePolygon", "FinalScoringResult", "MissionPackDefinition"]
__all__ += ["MissionPackDefinitionPayload", "MissionSourcePackageDefinition"]
__all__ += ["MissionSourceStatus", "Path", "ScoringWindowKind", "ScoringWindowState"]
__all__ += ["TerrainDisplayPoint", "VictoryPointAward", "VictoryPointLedger"]
__all__ += ["VictoryPointSourceKind", "_event_final_scoring_windows", "_layout_descriptor"]
__all__ += ["_source_deployment_zone_layout_edges", "_source_deployment_zone_layout_template_id"]
__all__ += ["_source_deployment_zone_layout_template_id_from_number"]
__all__ += ["_source_deployment_zone_template_base_shape", "_source_layout_number_from_layout_id"]
__all__ += ["_source_matrix_row", "deterministic_tactical_secondary_draw"]
__all__ += ["event_companion_base_size_rows", "event_primary_scoring", "importlib"]
__all__ += ["mission_action_policies", "mission_pack_for_id"]
__all__ += ["mission_scoring_policies_from_setup", "pairwise", "subprocess", "sys"]
