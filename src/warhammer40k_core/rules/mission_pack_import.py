from __future__ import annotations

import math

from warhammer40k_core.core.deployment_zones import DeploymentZone
from warhammer40k_core.core.missions import (
    ChallengerCardDefinition,
    ChapterApprovedMissionSequence,
    DeploymentMapDefinition,
    MissionActionDefinition,
    MissionDeckDefinition,
    MissionPackDefinition,
    MissionPackError,
    MissionPackScoringDefinition,
    MissionPoolEntry,
    MissionScoringRuleDefinition,
    ObjectiveMarkerDefinition,
    PrimaryMissionDefinition,
    SecondaryMissionAvailability,
    SecondaryMissionDefinition,
    TournamentScoringCaps,
)
from warhammer40k_core.core.ruleset_descriptor import TerrainFeatureKind
from warhammer40k_core.core.terrain_layouts import (
    TerrainFeatureTemplate,
    TerrainFloorTemplate,
    TerrainLayoutTemplate,
    TerrainWallTemplate,
)
from warhammer40k_core.rules.source_packages.warhammer_40000_11th import (
    chapter_approved_2025_26 as source_data,
)

CHAPTER_APPROVED_2025_26_SOURCE_ID = source_data.SOURCE_PACKAGE_ID
CHAPTER_APPROVED_2025_26_SOURCE_VERSION = source_data.SOURCE_VERSION
STRIKE_FORCE_BATTLEFIELD_WIDTH_INCHES = 60.0
STRIKE_FORCE_BATTLEFIELD_DEPTH_INCHES = 44.0


def chapter_approved_2025_26_mission_pack() -> MissionPackDefinition:
    """Build the source-linked Chapter Approved 2025-26 mission pack descriptors."""

    deployment_maps = _deployment_maps()
    terrain_layouts = _terrain_layouts()
    primary_missions = _primary_missions()
    secondary_missions = _secondary_missions()
    mission_actions = _mission_actions()
    challenger_cards = _challenger_cards()
    scoring = source_data.mission_pack_scoring_row()
    return MissionPackDefinition(
        mission_pack_id=source_data.MISSION_PACK_ID,
        name="Chapter Approved 2025-26",
        source_version=CHAPTER_APPROVED_2025_26_SOURCE_VERSION,
        source_id=CHAPTER_APPROVED_2025_26_SOURCE_ID,
        source_package=source_data.source_package_definition(),
        sequence=ChapterApprovedMissionSequence(
            sequence_id="chapter-approved-tournament-sequence",
            steps=(
                "muster_armies",
                "determine_mission",
                "read_mission",
                "place_objective_markers",
                "create_the_battlefield",
                "determine_attacker_and_defender",
                "select_secondary_missions",
                "declare_battle_formations",
                "deploy_armies",
                "determine_first_turn",
                "resolve_prebattle_rules",
                "begin_battle",
            ),
            source_id=CHAPTER_APPROVED_2025_26_SOURCE_ID,
        ),
        deployment_maps=deployment_maps,
        terrain_layout_templates=terrain_layouts,
        mission_deck=MissionDeckDefinition(
            mission_deck_id="chapter-approved-2025-26-strike-force",
            primary_mission_ids=tuple(mission.primary_mission_id for mission in primary_missions),
            secondary_mission_ids=tuple(
                mission.secondary_mission_id for mission in secondary_missions
            ),
            challenger_card_ids=tuple(card.challenger_card_id for card in challenger_cards),
            deployment_map_ids=tuple(
                deployment_map.deployment_map_id for deployment_map in deployment_maps
            ),
            source_id=CHAPTER_APPROVED_2025_26_SOURCE_ID,
        ),
        primary_missions=primary_missions,
        secondary_missions=secondary_missions,
        mission_actions=mission_actions,
        challenger_cards=challenger_cards,
        mission_pool_entries=_mission_pool_entries(),
        scoring_caps=TournamentScoringCaps(
            primary_vp_cap=scoring.primary_vp_cap,
            secondary_vp_cap=scoring.secondary_vp_cap,
            battle_ready_vp=10,
            total_vp_cap=scoring.total_vp_cap,
            source_id=f"{CHAPTER_APPROVED_2025_26_SOURCE_ID}:tournament-scoring",
        ),
        scoring=MissionPackScoringDefinition(
            game_length_battle_rounds=scoring.game_length_battle_rounds,
            primary_scoring_phase=scoring.primary_scoring_phase,
            primary_scoring_timing=scoring.primary_scoring_timing,
            secondary_vp_per_score=scoring.secondary_vp_per_score,
            mission_action_vp=scoring.mission_action_vp,
            primary_vp_cap=scoring.primary_vp_cap,
            secondary_vp_cap=scoring.secondary_vp_cap,
            total_vp_cap=scoring.total_vp_cap,
            end_of_round_scoring_windows=scoring.end_of_round_scoring_windows,
            end_of_game_scoring_windows=scoring.end_of_game_scoring_windows,
            reserve_destruction_timing=scoring.reserve_destruction_timing,
            reserve_destruction_battle_round=scoring.reserve_destruction_battle_round,
            reserve_destruction_excludes_during_battle_strategic_reserves=(
                scoring.reserve_destruction_excludes_during_battle_strategic_reserves
            ),
            reserve_destruction_only_declare_battle_formations=(
                scoring.reserve_destruction_only_declare_battle_formations
            ),
            source_id=f"{CHAPTER_APPROVED_2025_26_SOURCE_ID}:scoring",
        ),
    )


def _deployment_maps() -> tuple[DeploymentMapDefinition, ...]:
    return (
        _deployment_map(
            deployment_map_id="crucible-of-battle",
            name="Crucible of Battle",
            attacker_zones=((30.0, 0.0, 60.0, 44.0),),
            defender_zones=((0.0, 0.0, 30.0, 44.0),),
            objective_positions=(
                ("center", "Center Objective", 30.0, 22.0),
                ("southwest", "Southwest Objective", 14.0, 34.0),
                ("northeast", "Northeast Objective", 46.0, 10.0),
                ("northwest", "Northwest Objective", 20.0, 8.0),
                ("southeast", "Southeast Objective", 40.0, 36.0),
            ),
        ),
        _deployment_map(
            deployment_map_id="dawn-of-war",
            name="Dawn of War",
            attacker_zones=((0.0, 0.0, 60.0, 12.0),),
            defender_zones=((0.0, 32.0, 60.0, 44.0),),
            objective_positions=(
                ("center", "Center Objective", 30.0, 22.0),
                ("west", "West Objective", 10.0, 22.0),
                ("east", "East Objective", 50.0, 22.0),
                ("north", "North Objective", 30.0, 6.0),
                ("south", "South Objective", 30.0, 38.0),
            ),
        ),
        _deployment_map(
            deployment_map_id="hammer-and-anvil",
            name="Hammer and Anvil",
            attacker_zones=((42.0, 0.0, 60.0, 44.0),),
            defender_zones=((0.0, 0.0, 18.0, 44.0),),
            objective_positions=(
                ("center", "Center Objective", 30.0, 22.0),
                ("north", "North Objective", 30.0, 6.0),
                ("south", "South Objective", 30.0, 38.0),
                ("west", "West Objective", 10.0, 22.0),
                ("east", "East Objective", 50.0, 22.0),
            ),
        ),
        _deployment_map(
            deployment_map_id="search-and-destroy",
            name="Search and Destroy",
            attacker_zones=((30.0, 0.0, 60.0, 22.0),),
            defender_zones=((0.0, 22.0, 30.0, 44.0),),
            objective_positions=(
                ("center", "Center Objective", 30.0, 22.0),
                ("northwest", "Northwest Objective", 14.0, 10.0),
                ("northeast", "Northeast Objective", 46.0, 10.0),
                ("southwest", "Southwest Objective", 14.0, 34.0),
                ("southeast", "Southeast Objective", 46.0, 34.0),
            ),
        ),
        _deployment_map(
            deployment_map_id="sweeping-engagement",
            name="Sweeping Engagement",
            attacker_zones=((0.0, 0.0, 60.0, 14.0),),
            defender_zones=((0.0, 30.0, 60.0, 44.0),),
            objective_positions=(
                ("center", "Center Objective", 30.0, 22.0),
                ("northwest", "Northwest Objective", 10.0, 18.0),
                ("northeast", "Northeast Objective", 42.0, 6.0),
                ("southwest", "Southwest Objective", 18.0, 38.0),
                ("southeast", "Southeast Objective", 50.0, 26.0),
            ),
        ),
        _deployment_map(
            deployment_map_id="tipping-point",
            name="Tipping Point",
            attacker_zones=((40.0, 0.0, 60.0, 44.0),),
            defender_zones=((0.0, 0.0, 20.0, 44.0),),
            objective_positions=(
                ("center", "Center Objective", 30.0, 22.0),
                ("northwest", "Northwest Objective", 22.0, 8.0),
                ("northeast", "Northeast Objective", 46.0, 10.0),
                ("southwest", "Southwest Objective", 14.0, 34.0),
                ("southeast", "Southeast Objective", 38.0, 36.0),
            ),
        ),
    )


def _deployment_map(
    *,
    deployment_map_id: str,
    name: str,
    attacker_zones: tuple[tuple[float, float, float, float], ...],
    defender_zones: tuple[tuple[float, float, float, float], ...],
    objective_positions: tuple[tuple[str, str, float, float], ...],
) -> DeploymentMapDefinition:
    zones: list[DeploymentZone] = []
    for index, bounds in enumerate(attacker_zones, start=1):
        zones.append(_zone(deployment_map_id, "attacker", index, bounds))
    for index, bounds in enumerate(defender_zones, start=1):
        zones.append(_zone(deployment_map_id, "defender", index, bounds))
    return DeploymentMapDefinition(
        deployment_map_id=deployment_map_id,
        name=name,
        battlefield_width_inches=STRIKE_FORCE_BATTLEFIELD_WIDTH_INCHES,
        battlefield_depth_inches=STRIKE_FORCE_BATTLEFIELD_DEPTH_INCHES,
        objective_markers=_objective_markers(deployment_map_id, objective_positions),
        deployment_zones=tuple(zones),
        source_id=f"{CHAPTER_APPROVED_2025_26_SOURCE_ID}:{deployment_map_id}",
    )


def _zone(
    deployment_map_id: str,
    player_role: str,
    index: int,
    bounds: tuple[float, float, float, float],
) -> DeploymentZone:
    min_x, min_y, max_x, max_y = bounds
    return DeploymentZone(
        deployment_zone_id=f"{deployment_map_id}-{player_role}-{index}",
        player_id=player_role,
        min_x=min_x,
        min_y=min_y,
        max_x=max_x,
        max_y=max_y,
    )


def _objective_markers(
    deployment_map_id: str,
    positions: tuple[tuple[str, str, float, float], ...],
) -> tuple[ObjectiveMarkerDefinition, ...]:
    return tuple(
        ObjectiveMarkerDefinition(
            objective_marker_id=f"{deployment_map_id}-{marker_id}",
            name=name,
            x_inches=x,
            y_inches=y,
            source_id=f"{CHAPTER_APPROVED_2025_26_SOURCE_ID}:{deployment_map_id}",
        )
        for marker_id, name, x, y in positions
    )


def _terrain_layouts() -> tuple[TerrainLayoutTemplate, ...]:
    return tuple(_terrain_layout(index, slots) for index, slots in _TERRAIN_LAYOUT_SLOTS)


_TERRAIN_LAYOUT_SLOTS: tuple[
    tuple[int, tuple[tuple[str, float, tuple[float, float]], ...]],
    ...,
] = (
    (
        1,
        (
            ("ruin_rect_12x6_variant1", 90.0, (22.0, 28.0)),
            ("ruin_rect_12x6_variant1", 270.0, (38.0, 16.0)),
            ("ruin_rect_12x6_variant2", 270.0, (6.0, 17.0)),
            ("ruin_rect_12x6_variant2", 90.0, (54.0, 27.0)),
            ("ruin_rect_6x4_variant1", 90.0, (32.0, 0.0)),
            ("ruin_rect_6x4_variant1", 270.0, (28.0, 44.0)),
            ("ruin_rect_12x6_variant5", 0.0, (4.0, 22.0)),
            ("ruin_rect_12x6_variant5", 180.0, (56.0, 22.0)),
            ("ruin_rect_6x4_variant1", 135.0, (26.6, 20.6)),
            ("ruin_rect_6x4_variant1", 315.0, (33.4, 23.4)),
            ("ruin_rect_10x5_variant3", 45.0, (23.0, 10.0)),
            ("ruin_rect_10x5_variant3", 225.0, (37.0, 34.0)),
        ),
    ),
    (
        2,
        (
            ("ruin_rect_12x6_variant1", math.degrees(math.atan2(4.0, 4.5)), (17.0, 15.5)),
            (
                "ruin_rect_12x6_variant1",
                math.degrees(math.atan2(4.0, 4.5)) + 180.0,
                (43.0, 28.5),
            ),
            ("ruin_rect_12x6_variant2", 270.0, (8.0, 40.0)),
            ("ruin_rect_12x6_variant2", 90.0, (52.0, 4.0)),
            ("ruin_rect_12x6_variant4", 270.0, (5.0, 16.0)),
            ("ruin_rect_12x6_variant4", 90.0, (55.0, 28.0)),
            ("ruin_rect_10x5_variant1", 0.0, (20.0, 4.0)),
            ("ruin_rect_10x5_variant1", 180.0, (40.0, 40.0)),
            ("ruin_rect_6x4_variant1", 0.0, (30.0, 9.0)),
            ("ruin_rect_6x4_variant1", 180.0, (30.0, 35.0)),
            ("ruin_rect_6x4_variant1", 0.0, (52.0, 16.0)),
            ("ruin_rect_6x4_variant1", 180.0, (8.0, 28.0)),
        ),
    ),
    (
        3,
        (
            ("ruin_rect_12x6_variant1", 180.0, (34.0, 10.0)),
            ("ruin_rect_12x6_variant1", 0.0, (26.0, 34.0)),
            (
                "ruin_rect_12x6_variant3",
                math.degrees(math.atan2(6.0, 10.4)) + 180.0,
                (14.2, 38.0),
            ),
            (
                "ruin_rect_12x6_variant3",
                math.degrees(math.atan2(6.0, 10.4)),
                (45.8, 6.0),
            ),
            (
                "ruin_rect_12x6_variant4",
                270.0 + math.degrees(math.atan2(8.0, 9.0)),
                (2.0, 19.0),
            ),
            (
                "ruin_rect_12x6_variant4",
                90.0 + math.degrees(math.atan2(8.0, 9.0)),
                (58.0, 25.0),
            ),
            (
                "ruin_rect_10x5_variant3",
                math.degrees(math.atan2(7.8, 6.0)),
                (21.0, 14.0),
            ),
            (
                "ruin_rect_10x5_variant3",
                180.0 + math.degrees(math.atan2(7.8, 6.0)),
                (39.0, 30.0),
            ),
            ("ruin_rect_6x4_variant1", 0.0, (10.0, 4.0)),
            ("ruin_rect_6x4_variant1", 180.0, (50.0, 40.0)),
            (
                "ruin_rect_6x4_variant1",
                math.degrees(math.atan2(7.8, 6.0)) + 180.0,
                (22.8, 31.0),
            ),
            (
                "ruin_rect_6x4_variant1",
                math.degrees(math.atan2(7.8, 6.0)),
                (37.2, 13.0),
            ),
        ),
    ),
    (
        4,
        (
            ("ruin_rect_12x6_variant1", math.degrees(math.atan2(4.0, 4.5)), (8.0, 27.5)),
            (
                "ruin_rect_12x6_variant1",
                math.degrees(math.atan2(4.0, 4.5)) + 180.0,
                (52.0, 16.5),
            ),
            ("ruin_rect_12x6_variant2", 0.0, (12.0, 4.0)),
            ("ruin_rect_12x6_variant2", 180.0, (48.0, 40.0)),
            (
                "ruin_rect_12x6_variant4",
                math.degrees(math.atan2(9.5, 7.0)),
                (35.0, 2.5),
            ),
            (
                "ruin_rect_12x6_variant4",
                180.0 + math.degrees(math.atan2(9.5, 7.0)),
                (25.0, 41.5),
            ),
            (
                "ruin_rect_10x5_variant2",
                180.0 + math.degrees(math.atan2(7.6, 6.6)),
                (21.0, 27.0),
            ),
            (
                "ruin_rect_10x5_variant2",
                math.degrees(math.atan2(7.6, 6.6)),
                (39.0, 17.0),
            ),
            ("ruin_rect_6x4_variant1", 90.0, (8.0, 19.0)),
            ("ruin_rect_6x4_variant1", 270.0, (52.0, 25.0)),
            ("ruin_rect_6x4_variant1", 90.0, (12.0, 10.0)),
            ("ruin_rect_6x4_variant1", 270.0, (48.0, 34.0)),
        ),
    ),
    (
        5,
        (
            ("ruin_rect_12x6_variant1", 180.0, (36.0, 10.0)),
            ("ruin_rect_12x6_variant1", 0.0, (24.0, 34.0)),
            (
                "ruin_rect_12x6_variant2",
                math.degrees(math.atan2(11.0, 5.0)) - 90.0,
                (5.0, 16.0),
            ),
            (
                "ruin_rect_12x6_variant2",
                math.degrees(math.atan2(11.0, 5.0)) + 90.0,
                (55.0, 28.0),
            ),
            (
                "ruin_rect_12x6_variant4",
                math.degrees(math.atan2(6.0, 10.4)),
                (46.5, 2.0),
            ),
            (
                "ruin_rect_12x6_variant4",
                180.0 + math.degrees(math.atan2(6.0, 10.4)),
                (13.5, 42.0),
            ),
            ("ruin_rect_10x5_variant3", 0.0, (16.0, 24.0)),
            ("ruin_rect_10x5_variant3", 180.0, (44.0, 20.0)),
            ("ruin_rect_6x4_variant1", 0.0, (12.0, 4.0)),
            ("ruin_rect_6x4_variant1", 180.0, (48.0, 40.0)),
            ("ruin_rect_6x4_variant1", 0.0, (0.0, 24.0)),
            ("ruin_rect_6x4_variant1", 180.0, (60.0, 20.0)),
        ),
    ),
    (
        6,
        (
            ("ruin_rect_12x6_variant1", math.degrees(math.atan2(4.5, 4.0)), (8.5, 27.0)),
            (
                "ruin_rect_12x6_variant1",
                math.degrees(math.atan2(4.5, 4.0)) + 180.0,
                (51.5, 17.0),
            ),
            ("ruin_rect_12x6_variant2", 270.0, (20.0, 40.0)),
            ("ruin_rect_12x6_variant2", 90.0, (40.0, 4.0)),
            ("ruin_rect_12x6_variant4", 0.0, (10.0, 4.0)),
            ("ruin_rect_12x6_variant4", 180.0, (50.0, 40.0)),
            (
                "ruin_rect_10x5_variant2",
                math.degrees(math.atan2(7.4, 6.6)),
                (40.4, 18.6),
            ),
            (
                "ruin_rect_10x5_variant2",
                180.0 + math.degrees(math.atan2(7.4, 6.6)),
                (19.6, 25.4),
            ),
            ("ruin_rect_6x4_variant1", 0.0, (24.0, 12.0)),
            ("ruin_rect_6x4_variant1", 180.0, (36.0, 32.0)),
            ("ruin_rect_6x4_variant1", 90.0, (10.0, 10.0)),
            ("ruin_rect_6x4_variant1", 270.0, (50.0, 34.0)),
        ),
    ),
    (
        7,
        (
            ("ruin_rect_12x6_variant1", 90.0, (29.0, 3.0)),
            ("ruin_rect_12x6_variant1", 270.0, (31.0, 41.0)),
            ("ruin_rect_6x4_variant1", 0.0, (48.0, 0.0)),
            ("ruin_rect_6x4_variant1", 180.0, (12.0, 44.0)),
            ("ruin_rect_12x6_variant5", 90.0, (12.0, 28.0)),
            ("ruin_rect_12x6_variant5", 270.0, (48.0, 16.0)),
            ("ruin_rect_10x5_variant3", 270.0, (37.0, 18.0)),
            ("ruin_rect_10x5_variant3", 90.0, (23.0, 26.0)),
            ("ruin_rect_6x4_variant2", 90.0, (23.0, 20.0)),
            ("ruin_rect_6x4_variant2", 270.0, (37.0, 24.0)),
            ("ruin_rect_12x6_variant6", 90.0, (14.0, 8.0)),
            ("ruin_rect_12x6_variant6", 270.0, (46.0, 36.0)),
        ),
    ),
    (
        8,
        (
            ("ruin_rect_12x6_variant1", 90.0, (28.0, 0.0)),
            ("ruin_rect_12x6_variant1", 270.0, (32.0, 44.0)),
            (
                "ruin_rect_12x6_variant3",
                math.degrees(math.atan2(4.0, 4.5)) + 180.0,
                (15.0, 40.0),
            ),
            (
                "ruin_rect_12x6_variant3",
                math.degrees(math.atan2(4.0, 4.5)),
                (45.0, 4.0),
            ),
            ("ruin_rect_6x4_variant1", 90.0, (37.0, 10.0)),
            ("ruin_rect_6x4_variant1", 90.0, (37.0, 16.0)),
            ("ruin_rect_6x4_variant1", 270.0, (23.0, 34.0)),
            ("ruin_rect_6x4_variant1", 270.0, (23.0, 28.0)),
            ("ruin_rect_12x6_variant5", 90.0, (19.0, 13.0)),
            ("ruin_rect_12x6_variant5", 270.0, (41.0, 31.0)),
            (
                "ruin_rect_10x5_variant2",
                270.0 + math.degrees(math.atan2(8.0, 6.0)),
                (4.0, 10.0),
            ),
            (
                "ruin_rect_10x5_variant2",
                90.0 + math.degrees(math.atan2(8.0, 6.0)),
                (56.0, 34.0),
            ),
        ),
    ),
)


def _terrain_layout(
    index: int,
    slots: tuple[tuple[str, float, tuple[float, float]], ...],
) -> TerrainLayoutTemplate:
    source_id = f"{CHAPTER_APPROVED_2025_26_SOURCE_ID}:layout-{index}"
    return TerrainLayoutTemplate(
        terrain_layout_id=f"layout-{index}",
        name=f"Layout {index}",
        battlefield_width_inches=STRIKE_FORCE_BATTLEFIELD_WIDTH_INCHES,
        battlefield_depth_inches=STRIKE_FORCE_BATTLEFIELD_DEPTH_INCHES,
        terrain_features=tuple(
            _ruins_feature_from_slot(
                layout_index=index,
                slot_index=slot_index,
                preset=preset,
                rotation_degrees=rotation_degrees,
                world_origin=world_origin,
                source_id=source_id,
            )
            for slot_index, (preset, rotation_degrees, world_origin) in enumerate(slots, start=1)
        ),
        source_id=source_id,
    )


def _ruins_feature_from_slot(
    *,
    layout_index: int,
    slot_index: int,
    preset: str,
    rotation_degrees: float,
    world_origin: tuple[float, float],
    source_id: str,
) -> TerrainFeatureTemplate:
    # Phase 11A preserves source rotation provenance, but runtime occupancy is
    # intentionally conservative until exact rotated terrain geometry is built.
    min_x, min_y, max_x, max_y = _rotated_rect_bounds(
        width=_preset_width(preset),
        depth=_preset_depth(preset),
        rotation_degrees=rotation_degrees,
        world_origin=world_origin,
    )
    return _ruins_feature(
        feature_id=f"layout-{layout_index}-slot-{slot_index:02d}-{_terrain_slot_id(preset)}",
        x=(min_x + max_x) / 2.0,
        y=(min_y + max_y) / 2.0,
        width=max_x - min_x,
        depth=max_y - min_y,
        source_id=(
            f"{source_id}:slot-{slot_index:02d}:{preset}:"
            f"rotation-{rotation_degrees:.6f}:origin-{world_origin[0]:.3f}-{world_origin[1]:.3f}"
        ),
    )


def _ruins_feature(
    *,
    feature_id: str,
    x: float,
    y: float,
    width: float,
    depth: float,
    source_id: str,
) -> TerrainFeatureTemplate:
    half_width = width / 2.0
    half_depth = depth / 2.0
    wall_thickness = 0.12
    return TerrainFeatureTemplate(
        feature_id=feature_id,
        feature_kind=TerrainFeatureKind.RUINS,
        footprint_center_x_inches=x,
        footprint_center_y_inches=y,
        footprint_width_inches=width,
        footprint_depth_inches=depth,
        walls=(
            TerrainWallTemplate(
                wall_id="east-wall",
                center_x_inches=x + half_width - (wall_thickness / 2.0),
                center_y_inches=y,
                bottom_z_inches=0.0,
                width_inches=wall_thickness,
                depth_inches=half_depth * 2.0,
                height_inches=3.0,
            ),
            TerrainWallTemplate(
                wall_id="north-wall",
                center_x_inches=x,
                center_y_inches=y + half_depth - (wall_thickness / 2.0),
                bottom_z_inches=0.0,
                width_inches=half_width * 2.0,
                depth_inches=wall_thickness,
                height_inches=3.0,
            ),
        ),
        floors=(
            TerrainFloorTemplate(
                floor_id="ground-floor",
                center_x_inches=x,
                center_y_inches=y,
                bottom_z_inches=0.0,
                width_inches=half_width * 2.0,
                depth_inches=half_depth * 2.0,
                thickness_inches=0.12,
            ),
            TerrainFloorTemplate(
                floor_id="upper-floor",
                center_x_inches=x,
                center_y_inches=y,
                bottom_z_inches=3.0,
                width_inches=max(0.12, width - 2.0),
                depth_inches=max(0.12, depth - 2.0),
                thickness_inches=0.12,
            ),
        ),
        source_id=source_id,
    )


def _rotated_rect_bounds(
    *,
    width: float,
    depth: float,
    rotation_degrees: float,
    world_origin: tuple[float, float],
) -> tuple[float, float, float, float]:
    radians = math.radians(rotation_degrees)
    cos_r = math.cos(radians)
    sin_r = math.sin(radians)
    origin_x, origin_y = world_origin
    points = tuple(
        (
            origin_x + (corner_x * cos_r) - (corner_y * sin_r),
            origin_y + (corner_x * sin_r) + (corner_y * cos_r),
        )
        for corner_x, corner_y in (
            (0.0, 0.0),
            (width, 0.0),
            (width, depth),
            (0.0, depth),
        )
    )
    return (
        round(min(point[0] for point in points), 6),
        round(min(point[1] for point in points), 6),
        round(max(point[0] for point in points), 6),
        round(max(point[1] for point in points), 6),
    )


def _preset_width(preset: str) -> float:
    if "_12x6_" in preset:
        return 12.0
    if "_10x5_" in preset:
        return 10.0
    if "_6x4_" in preset:
        return 6.0
    raise MissionPackError(f"Unsupported terrain preset width: {preset}.")


def _preset_depth(preset: str) -> float:
    if "_12x6_" in preset:
        return 6.0
    if "_10x5_" in preset:
        return 5.0
    if "_6x4_" in preset:
        return 4.0
    raise MissionPackError(f"Unsupported terrain preset depth: {preset}.")


def _terrain_slot_id(preset: str) -> str:
    return preset.replace("_", "-")


def _primary_missions() -> tuple[PrimaryMissionDefinition, ...]:
    return tuple(
        PrimaryMissionDefinition(
            primary_mission_id=row.primary_mission_id,
            name=row.name,
            max_vp_per_turn=row.max_vp_per_turn,
            scoring_kind=row.scoring_kind,
            vp_per_controlled_objective=row.vp_per_controlled_objective,
            scoring_rules=_scoring_rules(
                row.scoring_rules,
                source_prefix=f"{CHAPTER_APPROVED_2025_26_SOURCE_ID}:primary:{row.primary_mission_id}",
            ),
            source_id=f"{CHAPTER_APPROVED_2025_26_SOURCE_ID}:primary:{row.primary_mission_id}",
        )
        for row in source_data.primary_mission_rows()
    )


def _secondary_missions() -> tuple[SecondaryMissionDefinition, ...]:
    return tuple(
        SecondaryMissionDefinition(
            secondary_mission_id=row.secondary_mission_id,
            name=row.name,
            availability=SecondaryMissionAvailability(row.availability),
            tournament_fixed_allowed=row.tournament_fixed_allowed,
            scoring_rules=_scoring_rules(
                row.scoring_rules,
                source_prefix=(
                    f"{CHAPTER_APPROVED_2025_26_SOURCE_ID}:secondary:{row.secondary_mission_id}"
                ),
            ),
            source_id=f"{CHAPTER_APPROVED_2025_26_SOURCE_ID}:secondary:{row.secondary_mission_id}",
        )
        for row in source_data.secondary_mission_rows()
    )


def _mission_actions() -> tuple[MissionActionDefinition, ...]:
    return tuple(
        MissionActionDefinition(
            mission_action_id=row.mission_action_id,
            mission_id=row.mission_id,
            mission_kind=row.mission_kind,
            name=row.name,
            start_phase=row.start_phase,
            start_timing=row.start_timing,
            completion_timing=row.completion_timing,
            eligible_unit_policy=row.eligible_unit_policy,
            target_policy=row.target_policy,
            interruption_conditions=row.interruption_conditions,
            victory_points=row.victory_points,
            scoring_source_id=row.scoring_source_id,
            source_id=f"{CHAPTER_APPROVED_2025_26_SOURCE_ID}:action:{row.mission_action_id}",
        )
        for row in source_data.mission_action_rows()
    )


def _scoring_rules(
    rows: tuple[source_data.SourceScoringRuleRow, ...],
    *,
    source_prefix: str,
) -> tuple[MissionScoringRuleDefinition, ...]:
    return tuple(
        MissionScoringRuleDefinition(
            rule_id=row.rule_id,
            timing=row.timing,
            source_kind=row.source_kind,
            victory_points=row.victory_points,
            cap=row.cap,
            condition=row.condition,
            source_id=f"{source_prefix}:scoring-rule:{row.rule_id}",
        )
        for row in rows
    )


def _challenger_cards() -> tuple[ChallengerCardDefinition, ...]:
    cards = (
        ("all-in", "All In"),
        ("burst-of-speed", "Burst of Speed"),
        ("force-a-breach", "Force a Breach"),
        ("great-haste", "Great Haste"),
        ("harboured-power", "Harboured Power"),
        ("opportunistic-strike", "Opportunistic Strike"),
        ("pivotal-moment", "Pivotal Moment"),
        ("renewed-focus", "Renewed Focus"),
        ("strategic-retreat", "Strategic Retreat"),
    )
    return tuple(
        ChallengerCardDefinition(
            challenger_card_id=card_id,
            name=name,
            source_id=f"{CHAPTER_APPROVED_2025_26_SOURCE_ID}:challenger:{card_id}",
        )
        for card_id, name in cards
    )


def _mission_pool_entries() -> tuple[MissionPoolEntry, ...]:
    rows = (
        ("a", "take-and-hold", "tipping-point", (1, 2, 4, 6, 7, 8)),
        ("b", "supply-drop", "tipping-point", (1, 2, 4, 6, 7, 8)),
        ("c", "linchpin", "tipping-point", (1, 2, 4, 6, 7, 8)),
        ("d", "scorched-earth", "tipping-point", (1, 2, 4, 6, 7, 8)),
        ("e", "take-and-hold", "hammer-and-anvil", (1, 7, 8)),
        ("f", "hidden-supplies", "hammer-and-anvil", (1, 7, 8)),
        ("g", "purge-the-foe", "hammer-and-anvil", (1, 7, 8)),
        ("h", "supply-drop", "hammer-and-anvil", (1, 7, 8)),
        ("i", "hidden-supplies", "search-and-destroy", (1, 2, 3, 4, 6)),
        ("j", "linchpin", "search-and-destroy", (1, 2, 3, 4, 6)),
        ("k", "scorched-earth", "search-and-destroy", (1, 2, 3, 4, 6)),
        ("l", "take-and-hold", "search-and-destroy", (1, 2, 3, 4, 6)),
        ("m", "purge-the-foe", "crucible-of-battle", (1, 2, 4, 6, 8)),
        ("n", "hidden-supplies", "crucible-of-battle", (1, 2, 4, 6, 8)),
        ("o", "terraform", "crucible-of-battle", (1, 2, 4, 6, 8)),
        ("p", "scorched-earth", "crucible-of-battle", (1, 2, 4, 6, 8)),
        ("q", "supply-drop", "sweeping-engagement", (3, 5)),
        ("r", "terraform", "sweeping-engagement", (3, 5)),
        ("s", "linchpin", "dawn-of-war", (5,)),
        ("t", "purge-the-foe", "dawn-of-war", (5,)),
    )
    return tuple(
        MissionPoolEntry(
            mission_pool_entry_id=f"mission-{entry_id}",
            primary_mission_id=primary_id,
            deployment_map_id=deployment_map_id,
            terrain_layout_ids=tuple(f"layout-{layout_id}" for layout_id in layout_ids),
            source_id=f"{CHAPTER_APPROVED_2025_26_SOURCE_ID}:mission-pool:{entry_id}",
        )
        for entry_id, primary_id, deployment_map_id, layout_ids in rows
    )
