from __future__ import annotations

from warhammer40k_core.core.missions import ObjectiveMarkerRole
from warhammer40k_core.core.terrain_areas import (
    TerrainAreaClassification,
    TerrainAreaLocalTransform,
)

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
        objective_specs=(
            ("attacker-home", "Attacker Home Objective", "attacker_home", 16.49, 49.82),
            ("defender-home", "Defender Home Objective", "defender_home", 25.76, 12.72),
            ("central", "Central Objective", "central", 22.02, 30.0),
            ("expansion-west", "West Expansion Objective", "expansion", 7.4, 19.16),
            ("expansion-east", "East Expansion Objective", "expansion", 36.72, 41.87),
        ),
        objective_role_counts=_OBJECTIVE_ROLE_COUNTS,
        terrain_area_specs=(
            (
                "dense-7x11-5-upper-right",
                FOOTPRINT_7X11_5,
                TerrainAreaClassification.DENSE,
                40.0,
                35.5,
                180.0,
            ),
            (
                "dense-7x11-5-upper-left",
                FOOTPRINT_7X11_5,
                TerrainAreaClassification.DENSE,
                14.0,
                54.0,
                0.0,
            ),
            (
                "light-10x2-5-upper-left",
                FOOTPRINT_10X2_5,
                TerrainAreaClassification.LIGHT,
                12.0,
                43.5,
                180.0,
            ),
            (
                "light-6x2-upper-center",
                FOOTPRINT_6X2,
                TerrainAreaClassification.LIGHT,
                27.0,
                42.5,
                0.0,
            ),
            (
                "light-6x2-east-midfield",
                FOOTPRINT_6X2,
                TerrainAreaClassification.LIGHT,
                40.0,
                28.0,
                180.0,
            ),
            (
                "light-6x4-lower-left",
                FOOTPRINT_6X4,
                TerrainAreaClassification.LIGHT,
                11.0,
                13.0,
                0.0,
            ),
            (
                "light-6x4-east-midfield",
                FOOTPRINT_6X4,
                TerrainAreaClassification.LIGHT,
                36.0,
                28.0,
                -90.0,
            ),
            (
                "dense-8x11-5-polygon-central-north",
                FOOTPRINT_8X11_5_POLYGON,
                TerrainAreaClassification.DENSE,
                16.25,
                35.0,
                0.0,
            ),
        ),
        terrain_area_mirror_pairs=(
            ("dense-7x11-5-upper-right", "dense-7x11-5-lower-left"),
            ("dense-7x11-5-upper-left", "dense-7x11-5-lower-right"),
            ("light-10x2-5-upper-left", "light-10x2-5-lower-right"),
            ("light-6x2-upper-center", "light-6x2-lower-center"),
            ("light-6x2-east-midfield", "light-6x2-west-midfield"),
            ("light-6x4-lower-left", "light-6x4-upper-right"),
            ("light-6x4-east-midfield", "light-6x4-west-midfield"),
            ("dense-8x11-5-polygon-central-north", "dense-8x11-5-polygon-central-south"),
        ),
        terrain_area_local_transform_specs=(
            ("light-6x2-upper-center", TerrainAreaLocalTransform.MIRROR_Y_AXIS),
        ),
        objective_terrain_area_specs=(
            ("attacker-home", ("dense-7x11-5-upper-left",)),
            ("defender-home", ("dense-7x11-5-lower-right",)),
            (
                "central",
                (
                    "dense-8x11-5-polygon-central-north",
                    "dense-8x11-5-polygon-central-south",
                ),
            ),
            ("expansion-west", ("dense-7x11-5-lower-left",)),
            ("expansion-east", ("dense-7x11-5-upper-right",)),
        ),
    ),
    EventBattlefieldLayoutSource(
        layout_id=TAKE_AND_HOLD_VS_TAKE_AND_HOLD_LAYOUT_B_ID,
        name="Take and Hold vs Take and Hold - Battlefield Dominance - Layout B",
        source_layout_id=(
            "gw_event_companion_v1_take_and_hold_vs_take_and_hold_battlefield_dominance_layout_b"
        ),
        objective_specs=(
            ("attacker-home", "Attacker Home Objective", "attacker_home", 6.76, 31.2),
            ("defender-home", "Defender Home Objective", "defender_home", 37.24, 28.67),
            ("central", "Central Objective", "central", 22.16, 30.04),
            ("expansion-south", "South Expansion Objective", "expansion", 19.2, 10.28),
            ("expansion-north", "North Expansion Objective", "expansion", 24.92, 50.61),
        ),
        objective_role_counts=_OBJECTIVE_ROLE_COUNTS,
        terrain_area_specs=(
            (
                "dense-7x11-5-left-home",
                FOOTPRINT_7X11_5,
                TerrainAreaClassification.DENSE,
                4.0,
                35.5,
                0.0,
            ),
            (
                "dense-7x11-5-central-west",
                FOOTPRINT_7X11_5,
                TerrainAreaClassification.DENSE,
                17.0,
                35.75,
                0.0,
            ),
            (
                "dense-8x11-5-polygon-north",
                FOOTPRINT_8X11_5_POLYGON,
                TerrainAreaClassification.DENSE,
                19.5,
                53.0,
                0.0,
            ),
            (
                "light-10x2-5-north-west",
                FOOTPRINT_10X2_5,
                TerrainAreaClassification.LIGHT,
                6.0,
                40.75,
                66.0,
            ),
            (
                "light-6x4-north-east",
                FOOTPRINT_6X4,
                TerrainAreaClassification.LIGHT,
                33.5,
                50.5,
                30.0,
            ),
            (
                "light-6x4-north-west",
                FOOTPRINT_6X4,
                TerrainAreaClassification.LIGHT,
                16.0,
                46.25,
                330.0,
            ),
            (
                "light-6x2-north-east",
                FOOTPRINT_6X2,
                TerrainAreaClassification.LIGHT,
                34.0,
                42.0,
                55.0,
            ),
            (
                "light-6x2-north-west",
                FOOTPRINT_6X2,
                TerrainAreaClassification.LIGHT,
                4.75,
                51.75,
                35.0,
            ),
        ),
        terrain_area_mirror_pairs=(
            ("dense-7x11-5-left-home", "dense-7x11-5-right-home"),
            ("dense-7x11-5-central-west", "dense-7x11-5-central-east"),
            ("dense-8x11-5-polygon-north", "dense-8x11-5-polygon-south"),
            ("light-10x2-5-north-west", "light-10x2-5-south-east"),
            ("light-6x4-north-east", "light-6x4-south-west"),
            ("light-6x4-north-west", "light-6x4-south-east"),
            ("light-6x2-north-east", "light-6x2-south-west"),
            ("light-6x2-north-west", "light-6x2-south-east"),
        ),
        objective_terrain_area_specs=(
            ("attacker-home", ("dense-7x11-5-left-home",)),
            ("defender-home", ("dense-7x11-5-right-home",)),
            (
                "central",
                (
                    "dense-7x11-5-central-west",
                    "dense-7x11-5-central-east",
                ),
            ),
            ("expansion-south", ("dense-8x11-5-polygon-south",)),
            ("expansion-north", ("dense-8x11-5-polygon-north",)),
        ),
    ),
    EventBattlefieldLayoutSource(
        layout_id=TAKE_AND_HOLD_VS_TAKE_AND_HOLD_LAYOUT_C_ID,
        name="Take and Hold vs Take and Hold - Battlefield Dominance - Layout C",
        source_layout_id=(
            "gw_event_companion_v1_take_and_hold_vs_take_and_hold_battlefield_dominance_layout_c"
        ),
        objective_specs=(
            ("attacker-home", "Attacker Home Objective", "attacker_home", 9.45, 50.3),
            ("defender-home", "Defender Home Objective", "defender_home", 34.55, 9.7),
            ("central", "Central Objective", "central", 22.0, 30.0),
            (
                "expansion-south-west",
                "South-west Expansion Objective",
                "expansion",
                9.7,
                10.55,
            ),
            (
                "expansion-north-east",
                "North-east Expansion Objective",
                "expansion",
                34.3,
                49.45,
            ),
        ),
        objective_role_counts=_OBJECTIVE_ROLE_COUNTS,
        terrain_area_specs=(
            (
                "dense-7x11-5-north-west",
                FOOTPRINT_7X11_5,
                TerrainAreaClassification.DENSE,
                11.25,
                56.75,
                315.0,
            ),
            (
                "dense-7x11-5-south-west",
                FOOTPRINT_7X11_5,
                TerrainAreaClassification.DENSE,
                6.0,
                16.5,
                0.0,
            ),
            (
                "dense-8x11-5-polygon-central-north-west",
                FOOTPRINT_8X11_5_POLYGON,
                TerrainAreaClassification.DENSE,
                16.25,
                35.0,
                0.0,
            ),
            (
                "light-10x2-5-north-center",
                FOOTPRINT_10X2_5,
                TerrainAreaClassification.LIGHT,
                15.75,
                44.25,
                35.0,
            ),
            (
                "light-6x4-north-west",
                FOOTPRINT_6X4,
                TerrainAreaClassification.LIGHT,
                11.0,
                37.25,
                90.0,
            ),
            (
                "light-6x4-central-east",
                FOOTPRINT_6X4,
                TerrainAreaClassification.LIGHT,
                31.0,
                30.75,
                90.0,
            ),
            (
                "light-6x2-west-midfield",
                FOOTPRINT_6X2,
                TerrainAreaClassification.LIGHT,
                2.75,
                37.25,
                0.0,
            ),
            (
                "light-6x2-south-west",
                FOOTPRINT_6X2,
                TerrainAreaClassification.LIGHT,
                4.25,
                24.5,
                0.0,
            ),
        ),
        terrain_area_mirror_pairs=(
            ("dense-7x11-5-north-west", "dense-7x11-5-south-east"),
            ("dense-7x11-5-south-west", "dense-7x11-5-north-east"),
            (
                "dense-8x11-5-polygon-central-north-west",
                "dense-8x11-5-polygon-central-south-east",
            ),
            ("light-10x2-5-north-center", "light-10x2-5-south-center"),
            ("light-6x4-north-west", "light-6x4-south-east"),
            ("light-6x4-central-east", "light-6x4-central-west"),
            ("light-6x2-west-midfield", "light-6x2-east-midfield"),
            ("light-6x2-south-west", "light-6x2-north-east"),
        ),
        objective_terrain_area_specs=(
            ("attacker-home", ("dense-7x11-5-north-west",)),
            ("defender-home", ("dense-7x11-5-south-east",)),
            (
                "central",
                (
                    "dense-8x11-5-polygon-central-north-west",
                    "dense-8x11-5-polygon-central-south-east",
                ),
            ),
            ("expansion-south-west", ("dense-7x11-5-south-west",)),
            ("expansion-north-east", ("dense-7x11-5-north-east",)),
        ),
    ),
)
