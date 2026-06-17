from __future__ import annotations

from warhammer40k_core.core.missions import ObjectiveMarkerRole
from warhammer40k_core.core.terrain_areas import TerrainAreaLocalTransform

from .common import (
    FOOTPRINT_6X2,
    FOOTPRINT_6X4,
    FOOTPRINT_7X11_5,
    FOOTPRINT_8X11_5_POLYGON,
    FOOTPRINT_10X2_5,
    EventBattlefieldLayoutSource,
    EventObjectiveRoleCountSpec,
)

TAKE_AND_HOLD_VS_TAKE_AND_HOLD_LAYOUT_A_ID = "take-and-hold-vs-take-and-hold-layout-1"
TAKE_AND_HOLD_VS_TAKE_AND_HOLD_LAYOUT_B_ID = "take-and-hold-vs-take-and-hold-layout-2"
TAKE_AND_HOLD_VS_TAKE_AND_HOLD_LAYOUT_C_ID = "take-and-hold-vs-take-and-hold-layout-3"

_OBJECTIVE_ROLE_COUNTS: tuple[EventObjectiveRoleCountSpec, ...] = (
    (ObjectiveMarkerRole.ATTACKER_HOME, 1),
    (ObjectiveMarkerRole.DEFENDER_HOME, 1),
    (ObjectiveMarkerRole.CENTRAL, 1),
    (ObjectiveMarkerRole.EXPANSION, 2),
)

LAYOUTS = (
    EventBattlefieldLayoutSource(
        layout_id=TAKE_AND_HOLD_VS_TAKE_AND_HOLD_LAYOUT_A_ID,
        name="Take and Hold vs Take and Hold - Battlefield Dominance - Layout A",
        source_layout_id=(
            "gw_event_companion_v1_take_and_hold_vs_take_and_hold_battlefield_dominance_layout_a"
        ),
        objective_role_counts=_OBJECTIVE_ROLE_COUNTS,
        terrain_area_specs=(
            ("7x11-5-upper-right", FOOTPRINT_7X11_5, 40.0, 35.5, 180.0),
            ("7x11-5-upper-left", FOOTPRINT_7X11_5, 14.0, 54.0, 0.0),
            ("10x2-5-upper-left", FOOTPRINT_10X2_5, 12.0, 43.5, 180.0),
            ("6x2-upper-center", FOOTPRINT_6X2, 27.0, 42.5, 0.0),
            ("6x2-east-midfield", FOOTPRINT_6X2, 40.0, 28.0, 180.0),
            ("6x4-lower-left", FOOTPRINT_6X4, 11.0, 13.0, 0.0),
            ("6x4-east-midfield", FOOTPRINT_6X4, 36.0, 28.0, -90.0),
            (
                "8x11-5-polygon-central-north",
                FOOTPRINT_8X11_5_POLYGON,
                16.25,
                35.0,
                0.0,
            ),
        ),
        terrain_area_mirror_pairs=(
            ("7x11-5-upper-right", "7x11-5-lower-left"),
            ("7x11-5-upper-left", "7x11-5-lower-right"),
            ("10x2-5-upper-left", "10x2-5-lower-right"),
            ("6x2-upper-center", "6x2-lower-center"),
            ("6x2-east-midfield", "6x2-west-midfield"),
            ("6x4-lower-left", "6x4-upper-right"),
            ("6x4-east-midfield", "6x4-west-midfield"),
            ("8x11-5-polygon-central-north", "8x11-5-polygon-central-south"),
        ),
        terrain_area_local_transform_specs=(
            ("6x2-upper-center", TerrainAreaLocalTransform.MIRROR_Y_AXIS),
        ),
        objective_terrain_area_specs=(
            (
                "attacker-home",
                "Attacker Home Objective",
                "attacker_home",
                16.49,
                49.82,
                ("7x11-5-upper-left",),
            ),
            (
                "defender-home",
                "Defender Home Objective",
                "defender_home",
                25.76,
                12.72,
                ("7x11-5-lower-right",),
            ),
            (
                "central",
                "Central Objective",
                "central",
                22.02,
                30.0,
                (
                    "8x11-5-polygon-central-north",
                    "8x11-5-polygon-central-south",
                ),
            ),
            (
                "expansion-west",
                "West Expansion Objective",
                "expansion",
                7.4,
                19.16,
                ("7x11-5-lower-left",),
            ),
            (
                "expansion-east",
                "East Expansion Objective",
                "expansion",
                36.72,
                41.87,
                ("7x11-5-upper-right",),
            ),
        ),
    ),
    EventBattlefieldLayoutSource(
        layout_id=TAKE_AND_HOLD_VS_TAKE_AND_HOLD_LAYOUT_B_ID,
        name="Take and Hold vs Take and Hold - Battlefield Dominance - Layout B",
        source_layout_id=(
            "gw_event_companion_v1_take_and_hold_vs_take_and_hold_battlefield_dominance_layout_b"
        ),
        objective_role_counts=_OBJECTIVE_ROLE_COUNTS,
        terrain_area_specs=(
            ("7x11-5-left-home", FOOTPRINT_7X11_5, 11.0, 24.0, 180.0),
            (
                "8x11-5-polygon-central-north",
                FOOTPRINT_8X11_5_POLYGON,
                17.0,
                35.75,
                0.0,
            ),
            (
                "8x11-5-polygon-north-expansion",
                FOOTPRINT_8X11_5_POLYGON,
                19.5,
                53.0,
                0.0,
            ),
            ("10x2-5-north-west", FOOTPRINT_10X2_5, 6.0, 40.75, 66.0),
            ("6x4-north-east", FOOTPRINT_6X4, 33.5, 50.5, 30.0),
            ("6x4-north-west", FOOTPRINT_6X4, 16.0, 46.25, 330.0),
            ("6x2-north-east", FOOTPRINT_6X2, 34.0, 42.0, 55.0),
            ("6x2-north-west", FOOTPRINT_6X2, 4.75, 51.75, 35.0),
        ),
        terrain_area_mirror_pairs=(
            ("7x11-5-left-home", "7x11-5-right-home"),
            ("8x11-5-polygon-central-north", "8x11-5-polygon-central-south"),
            ("8x11-5-polygon-north-expansion", "8x11-5-polygon-south-expansion"),
            ("10x2-5-north-west", "10x2-5-south-east"),
            ("6x4-north-east", "6x4-south-west"),
            ("6x4-north-west", "6x4-south-east"),
            ("6x2-north-east", "6x2-south-west"),
            ("6x2-north-west", "6x2-south-east"),
        ),
        objective_terrain_area_specs=(
            (
                "attacker-home",
                "Attacker Home Objective",
                "attacker_home",
                6.76,
                31.2,
                ("7x11-5-left-home",),
            ),
            (
                "defender-home",
                "Defender Home Objective",
                "defender_home",
                37.24,
                28.67,
                ("7x11-5-right-home",),
            ),
            (
                "central",
                "Central Objective",
                "central",
                22.16,
                30.04,
                (
                    "8x11-5-polygon-central-north",
                    "8x11-5-polygon-central-south",
                ),
            ),
            (
                "expansion-south",
                "South Expansion Objective",
                "expansion",
                19.2,
                10.28,
                ("8x11-5-polygon-south-expansion",),
            ),
            (
                "expansion-north",
                "North Expansion Objective",
                "expansion",
                24.92,
                50.61,
                ("8x11-5-polygon-north-expansion",),
            ),
        ),
    ),
    EventBattlefieldLayoutSource(
        layout_id=TAKE_AND_HOLD_VS_TAKE_AND_HOLD_LAYOUT_C_ID,
        name="Take and Hold vs Take and Hold - Battlefield Dominance - Layout C",
        source_layout_id=(
            "gw_event_companion_v1_take_and_hold_vs_take_and_hold_battlefield_dominance_layout_c"
        ),
        objective_role_counts=_OBJECTIVE_ROLE_COUNTS,
        terrain_area_specs=(
            ("7x11-5-north-west", FOOTPRINT_7X11_5, 11.25, 56.75, 315.0),
            ("7x11-5-south-west", FOOTPRINT_7X11_5, 6.0, 16.5, 0.0),
            (
                "8x11-5-polygon-central-north-west",
                FOOTPRINT_8X11_5_POLYGON,
                16.25,
                35.0,
                0.0,
            ),
            ("10x2-5-north-center", FOOTPRINT_10X2_5, 15.75, 44.25, 35.0),
            ("6x4-north-west", FOOTPRINT_6X4, 11.0, 37.25, 90.0),
            ("6x4-central-east", FOOTPRINT_6X4, 31.0, 30.75, 90.0),
            ("6x2-west-midfield", FOOTPRINT_6X2, 2.75, 37.25, 0.0),
            ("6x2-south-west", FOOTPRINT_6X2, 4.25, 24.5, 0.0),
        ),
        terrain_area_mirror_pairs=(
            ("7x11-5-north-west", "7x11-5-south-east"),
            ("7x11-5-south-west", "7x11-5-north-east"),
            (
                "8x11-5-polygon-central-north-west",
                "8x11-5-polygon-central-south-east",
            ),
            ("10x2-5-north-center", "10x2-5-south-center"),
            ("6x4-north-west", "6x4-south-east"),
            ("6x4-central-east", "6x4-central-west"),
            ("6x2-west-midfield", "6x2-east-midfield"),
            ("6x2-south-west", "6x2-north-east"),
        ),
        objective_terrain_area_specs=(
            (
                "attacker-home",
                "Attacker Home Objective",
                "attacker_home",
                9.45,
                50.3,
                ("7x11-5-north-west",),
            ),
            (
                "defender-home",
                "Defender Home Objective",
                "defender_home",
                34.55,
                9.7,
                ("7x11-5-south-east",),
            ),
            (
                "central",
                "Central Objective",
                "central",
                22.0,
                30.0,
                (
                    "8x11-5-polygon-central-north-west",
                    "8x11-5-polygon-central-south-east",
                ),
            ),
            (
                "expansion-south-west",
                "South-west Expansion Objective",
                "expansion",
                9.7,
                10.55,
                ("7x11-5-south-west",),
            ),
            (
                "expansion-north-east",
                "North-east Expansion Objective",
                "expansion",
                34.3,
                49.45,
                ("7x11-5-north-east",),
            ),
        ),
    ),
)
