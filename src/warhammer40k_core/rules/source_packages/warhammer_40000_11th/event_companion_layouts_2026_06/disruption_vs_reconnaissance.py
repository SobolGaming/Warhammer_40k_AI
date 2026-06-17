from __future__ import annotations

from warhammer40k_core.core.missions import ObjectiveMarkerRole

from .common import (
    FOOTPRINT_6X2,
    FOOTPRINT_6X4,
    FOOTPRINT_7X11_5,
    FOOTPRINT_8X11_5_POLYGON,
    FOOTPRINT_10X2_5,
    EventBattlefieldLayoutSource,
    EventObjectiveRoleCountSpec,
)

DISRUPTION_VS_RECONNAISSANCE_LAYOUT_A_ID = "disruption-vs-reconnaissance-layout-1"
DISRUPTION_VS_RECONNAISSANCE_LAYOUT_B_ID = "disruption-vs-reconnaissance-layout-2"
DISRUPTION_VS_RECONNAISSANCE_LAYOUT_C_ID = "disruption-vs-reconnaissance-layout-3"

_OBJECTIVE_ROLE_COUNTS: tuple[EventObjectiveRoleCountSpec, ...] = (
    (ObjectiveMarkerRole.ATTACKER_HOME, 1),
    (ObjectiveMarkerRole.DEFENDER_HOME, 1),
    (ObjectiveMarkerRole.CENTRAL, 2),
    (ObjectiveMarkerRole.EXPANSION, 2),
)

LAYOUTS = (
    EventBattlefieldLayoutSource(
        layout_id=DISRUPTION_VS_RECONNAISSANCE_LAYOUT_A_ID,
        name="Disruption vs Reconnaissance - Smoke and Mirrors / Surveil the Foe - Layout A",
        source_layout_id=(
            "gw_event_companion_v1_disruption_vs_reconnaissance_"
            "smoke_and_mirrors_surveil_the_foe_layout_a"
        ),
        objective_role_counts=_OBJECTIVE_ROLE_COUNTS,
        terrain_area_specs=(
            ("7x11-5-east-expansion", FOOTPRINT_7X11_5, 33.45, 47.03, 0.0),
            ("7x11-5-attacker-home", FOOTPRINT_7X11_5, 20.87, 43.14, 180.0),
            ("10x2-5-attacker-midfield", FOOTPRINT_10X2_5, 24.02, 49.62, 0.0),
            ("6x4-attacker-west", FOOTPRINT_6X4, 3.02, 45.95, 0.0),
            ("6x2-east-midfield", FOOTPRINT_6X2, 32.97, 31.09, 0.0),
            ("6x4-east-midfield", FOOTPRINT_6X4, 30.58, 22.46, 90.0),
            (
                "8x11-5-polygon-north-center",
                FOOTPRINT_8X11_5_POLYGON,
                17.07,
                39.41,
                0.0,
            ),
            ("6x2-defender-east", FOOTPRINT_6X2, 32.64, 7.79, 90.0),
        ),
        terrain_area_mirror_pairs=(
            ("7x11-5-east-expansion", "7x11-5-west-expansion"),
            ("7x11-5-attacker-home", "7x11-5-defender-home"),
            ("10x2-5-attacker-midfield", "10x2-5-defender-midfield"),
            ("6x4-attacker-west", "6x4-defender-east"),
            ("6x2-east-midfield", "6x2-west-midfield"),
            ("6x4-east-midfield", "6x4-west-midfield"),
            ("8x11-5-polygon-north-center", "8x11-5-polygon-south-center"),
            ("6x2-defender-east", "6x2-attacker-west"),
        ),
        objective_terrain_area_specs=(
            ("attacker-home", "Attacker Home Objective", "attacker_home", 16.98, 49.88, ()),
            ("defender-home", "Defender Home Objective", "defender_home", 26.31, 9.65, ()),
            ("central-south", "South Central Objective", "central", 23.0, 25.7, ()),
            ("central-north", "North Central Objective", "central", 20.9, 34.1, ()),
            ("expansion-east", "East Expansion Objective", "expansion", 37.65, 41.4, ()),
            ("expansion-west", "West Expansion Objective", "expansion", 6.21, 18.9, ()),
        ),
    ),
    EventBattlefieldLayoutSource(
        layout_id=DISRUPTION_VS_RECONNAISSANCE_LAYOUT_B_ID,
        name="Disruption vs Reconnaissance - Smoke and Mirrors / Surveil the Foe - Layout B",
        source_layout_id=(
            "gw_event_companion_v1_disruption_vs_reconnaissance_"
            "smoke_and_mirrors_surveil_the_foe_layout_b"
        ),
        objective_role_counts=_OBJECTIVE_ROLE_COUNTS,
        terrain_area_specs=(
            ("7x11-5-attacker-home", FOOTPRINT_7X11_5, 3.43, 47.96, 0.0),
            ("7x11-5-central-west", FOOTPRINT_7X11_5, 16.564103, 33.429646, 330.0),
            ("6x2-north-west", FOOTPRINT_6X2, 11.0, 48.07, 90.0),
            (
                "8x11-5-polygon-south-west",
                FOOTPRINT_8X11_5_POLYGON,
                18.27934,
                16.357514,
                315.0,
            ),
            ("6x2-south-west", FOOTPRINT_6X2, 5.408567, 14.721199, 55.0),
            ("6x4-west-midfield", FOOTPRINT_6X4, 4.590913, 25.672893, 45.0),
            ("10x2-5-north-west", FOOTPRINT_10X2_5, 13.86077, 35.379873, 60.0),
            ("6x4-north-east", FOOTPRINT_6X4, 32.450417, 50.213557, 30.0),
        ),
        terrain_area_mirror_pairs=(
            ("7x11-5-attacker-home", "7x11-5-defender-home"),
            ("7x11-5-central-west", "7x11-5-central-east"),
            ("6x2-north-west", "6x2-south-east"),
            ("8x11-5-polygon-south-west", "8x11-5-polygon-north-east"),
            ("6x2-south-west", "6x2-north-east"),
            ("6x4-west-midfield", "6x4-east-midfield"),
            ("10x2-5-north-west", "10x2-5-south-east"),
            ("6x4-north-east", "6x4-south-west"),
        ),
        objective_terrain_area_specs=(
            ("attacker-home", "Attacker Home Objective", "attacker_home", 7.55, 44.17, ()),
            ("defender-home", "Defender Home Objective", "defender_home", 36.53, 16.02, ()),
            ("central-west", "West Central Objective", "central", 14.31, 28.95, ()),
            ("central-east", "East Central Objective", "central", 29.24, 31.45, ()),
            ("expansion-north", "North Expansion Objective", "expansion", 24.0, 51.43, ()),
            ("expansion-south", "South Expansion Objective", "expansion", 20.05, 8.6, ()),
        ),
    ),
    EventBattlefieldLayoutSource(
        layout_id=DISRUPTION_VS_RECONNAISSANCE_LAYOUT_C_ID,
        name="Disruption vs Reconnaissance - Smoke and Mirrors / Surveil the Foe - Layout C",
        source_layout_id=(
            "gw_event_companion_v1_disruption_vs_reconnaissance_"
            "smoke_and_mirrors_surveil_the_foe_layout_c"
        ),
        objective_role_counts=_OBJECTIVE_ROLE_COUNTS,
        terrain_area_specs=(
            (
                "8x11-5-polygon-north-east",
                FOOTPRINT_8X11_5_POLYGON,
                34.44934,
                57.107514,
                315.0,
            ),
            ("7x11-5-attacker-home", FOOTPRINT_7X11_5, 3.05, 49.96, 0.0),
            ("6x2-north-west", FOOTPRINT_6X2, 13.98, 45.3, 0.0),
            ("10x2-5-north-center", FOOTPRINT_10X2_5, 20.15, 45.07, 90.0),
            ("6x4-south-west-midfield", FOOTPRINT_6X4, 9.44, 20.65, 0.0),
            ("7x11-5-central-north-west", FOOTPRINT_7X11_5, 14.27, 32.25, 90.0),
            ("6x4-east-midfield", FOOTPRINT_6X4, 32.46, 26.32, 90.0),
            ("6x2-east-midfield", FOOTPRINT_6X2, 34.84, 35.25, 0.0),
        ),
        terrain_area_mirror_pairs=(
            ("8x11-5-polygon-north-east", "8x11-5-polygon-south-west"),
            ("7x11-5-attacker-home", "7x11-5-defender-home"),
            ("6x2-north-west", "6x2-south-east"),
            ("10x2-5-north-center", "10x2-5-south-center"),
            ("6x4-south-west-midfield", "6x4-north-east-midfield"),
            ("7x11-5-central-north-west", "7x11-5-central-south-east"),
            ("6x4-east-midfield", "6x4-west-midfield"),
            ("6x2-east-midfield", "6x2-west-midfield"),
        ),
        objective_terrain_area_specs=(
            ("attacker-home", "Attacker Home Objective", "attacker_home", 6.45, 45.39, ()),
            ("defender-home", "Defender Home Objective", "defender_home", 37.4, 14.91, ()),
            (
                "central-north-west",
                "North-west Central Objective",
                "central",
                18.49,
                33.93,
                (),
            ),
            (
                "central-south-east",
                "South-east Central Objective",
                "central",
                25.52,
                26.0,
                (),
            ),
            (
                "expansion-north-east",
                "North-east Expansion Objective",
                "expansion",
                35.62,
                50.96,
                (),
            ),
            (
                "expansion-south-west",
                "South-west Expansion Objective",
                "expansion",
                8.75,
                9.07,
                (),
            ),
        ),
    ),
)
