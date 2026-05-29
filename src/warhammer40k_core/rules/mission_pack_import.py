from __future__ import annotations

from warhammer40k_core.core.deployment_zones import DeploymentZone
from warhammer40k_core.core.missions import (
    ChallengerCardDefinition,
    ChapterApprovedMissionSequence,
    DeploymentMapDefinition,
    MissionDeckDefinition,
    MissionPackDefinition,
    MissionPoolEntry,
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

CHAPTER_APPROVED_2025_26_SOURCE_ID = "chapter_approved_2025_26_mission_deck_v1_5"
CHAPTER_APPROVED_2025_26_SOURCE_VERSION = "1.5"
STRIKE_FORCE_BATTLEFIELD_WIDTH_INCHES = 60.0
STRIKE_FORCE_BATTLEFIELD_DEPTH_INCHES = 44.0


def chapter_approved_2025_26_mission_pack() -> MissionPackDefinition:
    """Build the source-linked Chapter Approved 2025-26 mission pack descriptors."""

    deployment_maps = _deployment_maps()
    terrain_layouts = _terrain_layouts()
    primary_missions = _primary_missions()
    secondary_missions = _secondary_missions()
    challenger_cards = _challenger_cards()
    return MissionPackDefinition(
        mission_pack_id="chapter-approved-2025-26",
        name="Chapter Approved 2025-26",
        source_version=CHAPTER_APPROVED_2025_26_SOURCE_VERSION,
        source_id=CHAPTER_APPROVED_2025_26_SOURCE_ID,
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
        challenger_cards=challenger_cards,
        mission_pool_entries=_mission_pool_entries(),
        scoring_caps=TournamentScoringCaps(
            primary_vp_cap=50,
            secondary_vp_cap=40,
            battle_ready_vp=10,
            total_vp_cap=100,
            source_id="chapter_approved_2025_26_tournament_scoring",
        ),
    )


def _deployment_maps() -> tuple[DeploymentMapDefinition, ...]:
    return (
        _deployment_map(
            deployment_map_id="crucible-of-battle",
            name="Crucible of Battle",
            attacker_zones=((0.0, 0.0, 24.0, 16.0),),
            defender_zones=((36.0, 28.0, 60.0, 44.0),),
        ),
        _deployment_map(
            deployment_map_id="dawn-of-war",
            name="Dawn of War",
            attacker_zones=((0.0, 0.0, 60.0, 10.0),),
            defender_zones=((0.0, 34.0, 60.0, 44.0),),
        ),
        _deployment_map(
            deployment_map_id="hammer-and-anvil",
            name="Hammer and Anvil",
            attacker_zones=((0.0, 0.0, 10.0, 44.0),),
            defender_zones=((50.0, 0.0, 60.0, 44.0),),
        ),
        _deployment_map(
            deployment_map_id="search-and-destroy",
            name="Search and Destroy",
            attacker_zones=((0.0, 0.0, 18.0, 18.0),),
            defender_zones=((42.0, 26.0, 60.0, 44.0),),
        ),
        _deployment_map(
            deployment_map_id="sweeping-engagement",
            name="Sweeping Engagement",
            attacker_zones=((0.0, 0.0, 30.0, 12.0),),
            defender_zones=((30.0, 32.0, 60.0, 44.0),),
        ),
        _deployment_map(
            deployment_map_id="tipping-point",
            name="Tipping Point",
            attacker_zones=((0.0, 0.0, 60.0, 10.0),),
            defender_zones=((0.0, 34.0, 60.0, 44.0),),
        ),
    )


def _deployment_map(
    *,
    deployment_map_id: str,
    name: str,
    attacker_zones: tuple[tuple[float, float, float, float], ...],
    defender_zones: tuple[tuple[float, float, float, float], ...],
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
        objective_markers=_standard_objective_markers(deployment_map_id),
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


def _standard_objective_markers(
    deployment_map_id: str,
) -> tuple[ObjectiveMarkerDefinition, ...]:
    positions = (
        ("home-attacker", "Attacker Objective", 30.0, 5.0),
        ("no-mans-left", "No Man's Land Left", 15.0, 22.0),
        ("center", "Centre Objective", 30.0, 22.0),
        ("no-mans-right", "No Man's Land Right", 45.0, 22.0),
        ("home-defender", "Defender Objective", 30.0, 39.0),
    )
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
    return tuple(_terrain_layout(index) for index in range(1, 9))


def _terrain_layout(index: int) -> TerrainLayoutTemplate:
    source_id = f"{CHAPTER_APPROVED_2025_26_SOURCE_ID}:layout-{index}"
    offset = float(index - 1)
    return TerrainLayoutTemplate(
        terrain_layout_id=f"layout-{index}",
        name=f"Layout {index}",
        battlefield_width_inches=STRIKE_FORCE_BATTLEFIELD_WIDTH_INCHES,
        battlefield_depth_inches=STRIKE_FORCE_BATTLEFIELD_DEPTH_INCHES,
        terrain_features=(
            _barricade_feature(
                feature_id=f"layout-{index}-south-edge-barricade",
                x=12.75 + offset,
                y=0.9,
                source_id=source_id,
            ),
            _ruins_feature(
                feature_id=f"layout-{index}-central-ruins",
                x=30.0,
                y=22.0 + ((index % 3) - 1),
                source_id=source_id,
            ),
        ),
        source_id=source_id,
    )


def _barricade_feature(
    *, feature_id: str, x: float, y: float, source_id: str
) -> TerrainFeatureTemplate:
    return TerrainFeatureTemplate(
        feature_id=feature_id,
        feature_kind=TerrainFeatureKind.BARRICADE_AND_FUEL_PIPES,
        footprint_center_x_inches=x,
        footprint_center_y_inches=y,
        footprint_width_inches=4.0,
        footprint_depth_inches=1.6,
        walls=(
            TerrainWallTemplate(
                wall_id="center-wall",
                center_x_inches=x,
                center_y_inches=y,
                bottom_z_inches=0.0,
                width_inches=1.0,
                depth_inches=1.0,
                height_inches=3.0,
            ),
        ),
        source_id=source_id,
    )


def _ruins_feature(
    *, feature_id: str, x: float, y: float, source_id: str
) -> TerrainFeatureTemplate:
    half_width = 5.0
    half_depth = 3.0
    wall_thickness = 0.12
    return TerrainFeatureTemplate(
        feature_id=feature_id,
        feature_kind=TerrainFeatureKind.RUINS,
        footprint_center_x_inches=x,
        footprint_center_y_inches=y,
        footprint_width_inches=half_width * 2.0,
        footprint_depth_inches=half_depth * 2.0,
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
                width_inches=8.0,
                depth_inches=4.0,
                thickness_inches=0.12,
            ),
        ),
        source_id=source_id,
    )


def _primary_missions() -> tuple[PrimaryMissionDefinition, ...]:
    names = (
        ("burden-of-trust", "Burden of Trust", None),
        ("hidden-supplies", "Hidden Supplies", None),
        ("linchpin", "Linchpin", 15),
        ("purge-the-foe", "Purge the Foe", None),
        ("scorched-earth", "Scorched Earth", None),
        ("supply-drop", "Supply Drop", None),
        ("take-and-hold", "Take and Hold", 15),
        ("terraform", "Terraform", None),
        ("the-ritual", "The Ritual", None),
        ("unexploded-ordnance", "Unexploded Ordnance", None),
    )
    return tuple(
        PrimaryMissionDefinition(
            primary_mission_id=mission_id,
            name=name,
            max_vp_per_turn=max_vp,
            source_id=f"{CHAPTER_APPROVED_2025_26_SOURCE_ID}:primary:{mission_id}",
        )
        for mission_id, name, max_vp in names
    )


def _secondary_missions() -> tuple[SecondaryMissionDefinition, ...]:
    missions = (
        ("area-denial", "Area Denial", SecondaryMissionAvailability.TACTICAL, False),
        ("assassination", "Assassination", SecondaryMissionAvailability.BOTH, True),
        ("behind-enemy-lines", "Behind Enemy Lines", SecondaryMissionAvailability.BOTH, True),
        ("bring-it-down", "Bring It Down", SecondaryMissionAvailability.BOTH, True),
        ("cleanse", "Cleanse", SecondaryMissionAvailability.BOTH, True),
        ("cull-the-horde", "Cull the Horde", SecondaryMissionAvailability.BOTH, True),
        ("defend-stronghold", "Defend Stronghold", SecondaryMissionAvailability.TACTICAL, False),
        ("engage-on-all-fronts", "Engage on All Fronts", SecondaryMissionAvailability.BOTH, True),
        ("marked-for-death", "Marked for Death", SecondaryMissionAvailability.TACTICAL, False),
        ("no-prisoners", "No Prisoners", SecondaryMissionAvailability.BOTH, True),
        ("overwhelming-force", "Overwhelming Force", SecondaryMissionAvailability.BOTH, True),
        ("recover-assets", "Recover Assets", SecondaryMissionAvailability.BOTH, True),
        (
            "secure-no-mans-land",
            "Secure No Man's Land",
            SecondaryMissionAvailability.TACTICAL,
            False,
        ),
        (
            "storm-hostile-objective",
            "Storm Hostile Objective",
            SecondaryMissionAvailability.TACTICAL,
            False,
        ),
    )
    return tuple(
        SecondaryMissionDefinition(
            secondary_mission_id=mission_id,
            name=name,
            availability=availability,
            tournament_fixed_allowed=tournament_fixed_allowed,
            source_id=f"{CHAPTER_APPROVED_2025_26_SOURCE_ID}:secondary:{mission_id}",
        )
        for mission_id, name, availability, tournament_fixed_allowed in missions
    )


def _challenger_cards() -> tuple[ChallengerCardDefinition, ...]:
    cards = (
        ("aggressive-push", "Aggressive Push"),
        ("counter-attack", "Counter-Attack"),
        ("desperate-reprisal", "Desperate Reprisal"),
        ("self-preservation", "Self Preservation"),
        ("strategic-retreat", "Strategic Retreat"),
        ("zone-defence", "Zone Defence"),
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
