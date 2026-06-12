from __future__ import annotations

from warhammer40k_core.core.deployment_zones import DeploymentZone
from warhammer40k_core.core.missions import (
    ChallengerCardDefinition,
    ChapterApprovedMissionSequence,
    DeploymentMapDefinition,
    ForceDispositionDefinition,
    MissionActionDefinition,
    MissionDeckDefinition,
    MissionPackDefinition,
    MissionPackScoringDefinition,
    MissionPoolEntry,
    MissionScoringRuleDefinition,
    MissionSourceStatus,
    ObjectiveMarkerDefinition,
    PrimaryMissionDefinition,
    PrimaryMissionMatrixCell,
    SecondaryMissionAvailability,
    SecondaryMissionDefinition,
    TournamentScoringCaps,
)
from warhammer40k_core.core.ruleset_descriptor import TerrainFeatureKind
from warhammer40k_core.core.terrain_display import TerrainDisplayGeometry
from warhammer40k_core.core.terrain_layouts import (
    TerrainFeatureTemplate,
    TerrainFloorTemplate,
    TerrainLayoutTemplate,
    TerrainWallTemplate,
)
from warhammer40k_core.rules.source_packages.warhammer_40000_11th import (
    chapter_approved_2026_27 as source_data,
)
from warhammer40k_core.rules.source_packages.warhammer_40000_11th import (
    event_companion_2026_06 as event_source_data,
)

CHAPTER_APPROVED_2026_27_SOURCE_ID = source_data.SOURCE_PACKAGE_ID
CHAPTER_APPROVED_2026_27_SOURCE_VERSION = source_data.SOURCE_VERSION
EVENT_COMPANION_2026_06_SOURCE_ID = event_source_data.SOURCE_PACKAGE_ID
EVENT_COMPANION_2026_06_SOURCE_VERSION = event_source_data.SOURCE_VERSION


def chapter_approved_2026_27_mission_pack() -> MissionPackDefinition:
    """Build the source-linked Chapter Approved 2026-27 mission pack descriptors."""

    deployment_maps = _deployment_maps(
        rows=source_data.battlefield_layout_rows(),
        source_id=CHAPTER_APPROVED_2026_27_SOURCE_ID,
    )
    terrain_layouts = _terrain_layouts(
        rows=source_data.battlefield_layout_rows(),
        source_id=CHAPTER_APPROVED_2026_27_SOURCE_ID,
    )
    primary_missions = _primary_missions(
        rows=source_data.primary_mission_rows(),
        source_id=CHAPTER_APPROVED_2026_27_SOURCE_ID,
    )
    secondary_missions = _secondary_missions(
        rows=source_data.secondary_mission_rows(),
        source_id=CHAPTER_APPROVED_2026_27_SOURCE_ID,
    )
    mission_actions = _mission_actions(
        rows=source_data.mission_action_rows(),
        source_id=CHAPTER_APPROVED_2026_27_SOURCE_ID,
    )
    challenger_cards = _challenger_cards(source_id=CHAPTER_APPROVED_2026_27_SOURCE_ID)
    force_dispositions = _force_dispositions(
        rows=source_data.force_disposition_rows(),
        source_id=CHAPTER_APPROVED_2026_27_SOURCE_ID,
    )
    scoring = source_data.mission_pack_scoring_row()
    return MissionPackDefinition(
        mission_pack_id=source_data.MISSION_PACK_ID,
        name="Chapter Approved 2026-27",
        source_version=CHAPTER_APPROVED_2026_27_SOURCE_VERSION,
        source_id=CHAPTER_APPROVED_2026_27_SOURCE_ID,
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
            source_id=CHAPTER_APPROVED_2026_27_SOURCE_ID,
        ),
        deployment_maps=deployment_maps,
        terrain_layout_templates=terrain_layouts,
        mission_deck=MissionDeckDefinition(
            mission_deck_id="chapter-approved-2026-27-strike-force",
            primary_mission_ids=tuple(mission.primary_mission_id for mission in primary_missions),
            secondary_mission_ids=tuple(
                mission.secondary_mission_id for mission in secondary_missions
            ),
            challenger_card_ids=tuple(card.challenger_card_id for card in challenger_cards),
            deployment_map_ids=tuple(
                deployment_map.deployment_map_id for deployment_map in deployment_maps
            ),
            source_id=CHAPTER_APPROVED_2026_27_SOURCE_ID,
        ),
        primary_missions=primary_missions,
        secondary_missions=secondary_missions,
        mission_actions=mission_actions,
        challenger_cards=challenger_cards,
        force_dispositions=force_dispositions,
        primary_mission_matrix_cells=_primary_mission_matrix_cells(
            rows=source_data.primary_mission_matrix_rows(),
            source_id=CHAPTER_APPROVED_2026_27_SOURCE_ID,
        ),
        mission_pool_entries=_mission_pool_entries(
            rows=source_data.battlefield_layout_rows(),
            source_id=CHAPTER_APPROVED_2026_27_SOURCE_ID,
        ),
        scoring_caps=TournamentScoringCaps(
            primary_vp_cap=scoring.primary_vp_cap,
            secondary_vp_cap=scoring.secondary_vp_cap,
            battle_ready_vp=10,
            total_vp_cap=scoring.total_vp_cap,
            source_id=f"{CHAPTER_APPROVED_2026_27_SOURCE_ID}:tournament-scoring",
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
            source_id=f"{CHAPTER_APPROVED_2026_27_SOURCE_ID}:scoring",
        ),
    )


def warhammer_event_companion_2026_06_mission_pack() -> MissionPackDefinition:
    """Build the source-linked Warhammer Event Companion v1.0 mission pack descriptors."""

    deployment_maps = _deployment_maps(
        rows=event_source_data.battlefield_layout_rows(),
        source_id=EVENT_COMPANION_2026_06_SOURCE_ID,
    )
    terrain_layouts = _terrain_layouts(
        rows=event_source_data.battlefield_layout_rows(),
        source_id=EVENT_COMPANION_2026_06_SOURCE_ID,
    )
    primary_missions = _primary_missions(
        rows=event_source_data.primary_mission_rows(),
        source_id=EVENT_COMPANION_2026_06_SOURCE_ID,
    )
    secondary_missions = _secondary_missions(
        rows=event_source_data.secondary_mission_rows(),
        source_id=EVENT_COMPANION_2026_06_SOURCE_ID,
    )
    mission_actions = _mission_actions(
        rows=event_source_data.mission_action_rows(),
        source_id=EVENT_COMPANION_2026_06_SOURCE_ID,
    )
    challenger_cards = _challenger_cards(source_id=EVENT_COMPANION_2026_06_SOURCE_ID)
    force_dispositions = _force_dispositions(
        rows=event_source_data.force_disposition_rows(),
        source_id=EVENT_COMPANION_2026_06_SOURCE_ID,
    )
    scoring = event_source_data.mission_pack_scoring_row()
    return MissionPackDefinition(
        mission_pack_id=event_source_data.MISSION_PACK_ID,
        name="Warhammer Event Companion v1.0",
        source_version=EVENT_COMPANION_2026_06_SOURCE_VERSION,
        source_id=EVENT_COMPANION_2026_06_SOURCE_ID,
        source_package=event_source_data.source_package_definition(),
        sequence=ChapterApprovedMissionSequence(
            sequence_id="warhammer-event-mission-sequence",
            steps=tuple(
                step.step_id for step in event_source_data.mission_sequence_descriptor().steps
            ),
            source_id=EVENT_COMPANION_2026_06_SOURCE_ID,
        ),
        deployment_maps=deployment_maps,
        terrain_layout_templates=terrain_layouts,
        mission_deck=MissionDeckDefinition(
            mission_deck_id="warhammer-event-companion-v1-strike-force",
            primary_mission_ids=tuple(mission.primary_mission_id for mission in primary_missions),
            secondary_mission_ids=tuple(
                mission.secondary_mission_id for mission in secondary_missions
            ),
            challenger_card_ids=tuple(card.challenger_card_id for card in challenger_cards),
            deployment_map_ids=tuple(
                deployment_map.deployment_map_id for deployment_map in deployment_maps
            ),
            source_id=EVENT_COMPANION_2026_06_SOURCE_ID,
        ),
        primary_missions=primary_missions,
        secondary_missions=secondary_missions,
        mission_actions=mission_actions,
        challenger_cards=challenger_cards,
        force_dispositions=force_dispositions,
        primary_mission_matrix_cells=_primary_mission_matrix_cells(
            rows=event_source_data.primary_mission_matrix_rows(),
            source_id=EVENT_COMPANION_2026_06_SOURCE_ID,
        ),
        mission_pool_entries=_mission_pool_entries(
            rows=event_source_data.battlefield_layout_rows(),
            source_id=EVENT_COMPANION_2026_06_SOURCE_ID,
        ),
        scoring_caps=TournamentScoringCaps(
            primary_vp_cap=scoring.primary_vp_cap,
            secondary_vp_cap=scoring.secondary_vp_cap,
            battle_ready_vp=10,
            total_vp_cap=scoring.total_vp_cap,
            source_id=f"{EVENT_COMPANION_2026_06_SOURCE_ID}:tournament-scoring",
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
            source_id=f"{EVENT_COMPANION_2026_06_SOURCE_ID}:scoring",
        ),
    )


def _deployment_maps(
    *,
    rows: tuple[source_data.SourceBattlefieldLayoutRow, ...],
    source_id: str,
) -> tuple[DeploymentMapDefinition, ...]:
    return tuple(_deployment_map_from_battlefield_layout(row, source_id=source_id) for row in rows)


def _deployment_map_from_battlefield_layout(
    row: source_data.SourceBattlefieldLayoutRow,
    *,
    source_id: str,
) -> DeploymentMapDefinition:
    return DeploymentMapDefinition(
        deployment_map_id=row.deployment_map_id,
        name=row.name,
        battlefield_width_inches=row.battlefield_width_inches,
        battlefield_depth_inches=row.battlefield_depth_inches,
        objective_markers=tuple(
            ObjectiveMarkerDefinition(
                objective_marker_id=objective.objective_marker_id,
                name=objective.name,
                x_inches=objective.x_inches,
                y_inches=objective.y_inches,
                source_id=(
                    f"{source_id}:battlefield-layout:"
                    f"{row.battlefield_layout_id}:objective:{objective.objective_marker_id}"
                ),
            )
            for objective in row.objective_markers
        ),
        deployment_zones=tuple(
            DeploymentZone(
                deployment_zone_id=zone.deployment_zone_id,
                player_id=zone.player_role,
                shape=zone.shape,
            )
            for zone in row.deployment_zones
        ),
        source_id=(f"{source_id}:battlefield-layout:{row.battlefield_layout_id}:deployment-map"),
    )


def _terrain_layouts(
    *,
    rows: tuple[source_data.SourceBattlefieldLayoutRow, ...],
    source_id: str,
) -> tuple[TerrainLayoutTemplate, ...]:
    return tuple(_terrain_layout_from_battlefield_layout(row, source_id=source_id) for row in rows)


def _terrain_layout_from_battlefield_layout(
    row: source_data.SourceBattlefieldLayoutRow,
    *,
    source_id: str,
) -> TerrainLayoutTemplate:
    layout_source_id = f"{source_id}:battlefield-layout:{row.battlefield_layout_id}:terrain-layout"
    return TerrainLayoutTemplate(
        terrain_layout_id=row.terrain_layout_id,
        name=row.name,
        battlefield_width_inches=row.battlefield_width_inches,
        battlefield_depth_inches=row.battlefield_depth_inches,
        terrain_features=tuple(
            _terrain_feature_from_battlefield_layout(
                layout=row,
                feature=feature,
                source_id=source_id,
            )
            for feature in row.terrain_features
        ),
        source_id=layout_source_id,
    )


def _terrain_feature_from_battlefield_layout(
    *,
    layout: source_data.SourceBattlefieldLayoutRow,
    feature: source_data.SourceBattlefieldTerrainFeatureRow,
    source_id: str,
) -> TerrainFeatureTemplate:
    feature_source_id = (
        f"{source_id}:battlefield-layout:"
        f"{layout.battlefield_layout_id}:terrain:{feature.feature_id}"
    )
    if feature.feature_kind == TerrainFeatureKind.RUINS.value:
        return _ruins_feature(
            feature_id=feature.feature_id,
            x=feature.footprint_center_x_inches,
            y=feature.footprint_center_y_inches,
            width=feature.footprint_width_inches,
            depth=feature.footprint_depth_inches,
            display_geometry=feature.display_geometry,
            source_id=feature_source_id,
        )
    return TerrainFeatureTemplate(
        feature_id=feature.feature_id,
        feature_kind=TerrainFeatureKind(feature.feature_kind),
        footprint_center_x_inches=feature.footprint_center_x_inches,
        footprint_center_y_inches=feature.footprint_center_y_inches,
        footprint_width_inches=feature.footprint_width_inches,
        footprint_depth_inches=feature.footprint_depth_inches,
        display_geometry=feature.display_geometry,
        walls=(),
        floors=(),
        source_id=feature_source_id,
    )


def _ruins_feature(
    *,
    feature_id: str,
    x: float,
    y: float,
    width: float,
    depth: float,
    display_geometry: TerrainDisplayGeometry,
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
        display_geometry=display_geometry,
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


def _primary_missions(
    *,
    rows: tuple[source_data.SourcePrimaryMissionRow, ...],
    source_id: str,
) -> tuple[PrimaryMissionDefinition, ...]:
    return tuple(
        PrimaryMissionDefinition(
            primary_mission_id=row.primary_mission_id,
            name=row.name,
            max_vp_per_turn=row.max_vp_per_turn,
            scoring_kind=row.scoring_kind,
            vp_per_controlled_objective=row.vp_per_controlled_objective,
            scoring_rules=_scoring_rules(
                row.scoring_rules,
                source_prefix=f"{source_id}:primary:{row.primary_mission_id}",
            ),
            source_id=f"{source_id}:primary:{row.primary_mission_id}",
        )
        for row in rows
    )


def _secondary_missions(
    *,
    rows: tuple[source_data.SourceSecondaryMissionRow, ...],
    source_id: str,
) -> tuple[SecondaryMissionDefinition, ...]:
    return tuple(
        SecondaryMissionDefinition(
            secondary_mission_id=row.secondary_mission_id,
            name=row.name,
            availability=SecondaryMissionAvailability(row.availability),
            tournament_fixed_allowed=row.tournament_fixed_allowed,
            scoring_rules=_scoring_rules(
                row.scoring_rules,
                source_prefix=f"{source_id}:secondary:{row.secondary_mission_id}",
            ),
            source_id=f"{source_id}:secondary:{row.secondary_mission_id}",
        )
        for row in rows
    )


def _force_dispositions(
    *,
    rows: tuple[source_data.SourceForceDispositionRow, ...],
    source_id: str,
) -> tuple[ForceDispositionDefinition, ...]:
    return tuple(
        ForceDispositionDefinition(
            force_disposition_id=row.force_disposition_id,
            name=row.name,
            source_id=f"{source_id}:force-disposition:{row.force_disposition_id}",
        )
        for row in rows
    )


def _primary_mission_matrix_cells(
    *,
    rows: tuple[source_data.SourcePrimaryMissionMatrixCellRow, ...],
    source_id: str,
) -> tuple[PrimaryMissionMatrixCell, ...]:
    return tuple(
        PrimaryMissionMatrixCell(
            player_force_disposition_id=row.player_force_disposition_id,
            opponent_force_disposition_id=row.opponent_force_disposition_id,
            primary_mission_id=row.primary_mission_id,
            battlefield_layout_ids=row.battlefield_layout_ids,
            source_status=MissionSourceStatus(row.source_status),
            source_id=(
                f"{source_id}:primary-mission-matrix:"
                f"{row.player_force_disposition_id}:"
                f"{row.opponent_force_disposition_id}"
            ),
        )
        for row in rows
    )


def _mission_actions(
    *,
    rows: tuple[source_data.SourceMissionActionRow, ...],
    source_id: str,
) -> tuple[MissionActionDefinition, ...]:
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
            source_id=f"{source_id}:action:{row.mission_action_id}",
        )
        for row in rows
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


def _challenger_cards(*, source_id: str) -> tuple[ChallengerCardDefinition, ...]:
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
            source_id=f"{source_id}:challenger:{card_id}",
        )
        for card_id, name in cards
    )


def _mission_pool_entries(
    *,
    rows: tuple[source_data.SourceBattlefieldLayoutRow, ...],
    source_id: str,
) -> tuple[MissionPoolEntry, ...]:
    return tuple(
        MissionPoolEntry(
            mission_pool_entry_id=f"mission-{row.battlefield_layout_id}",
            primary_mission_id=row.primary_mission_id,
            deployment_map_id=row.deployment_map_id,
            terrain_layout_ids=(row.terrain_layout_id,),
            source_id=(f"{source_id}:battlefield-layout:{row.battlefield_layout_id}:mission-pool"),
        )
        for row in rows
    )
