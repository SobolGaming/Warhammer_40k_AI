from __future__ import annotations

from warhammer40k_core.core.missions import ObjectiveMarkerRole
from warhammer40k_core.core.terrain_areas import TerrainAreaClassification

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
        objective_specs=(
            ("attacker-home", "Attacker Home Objective", "attacker_home", 16.98, 49.88),
            ("defender-home", "Defender Home Objective", "defender_home", 26.31, 9.65),
            ("central-south", "South Central Objective", "central", 23.0, 25.7),
            ("central-north", "North Central Objective", "central", 20.9, 34.1),
            ("expansion-east", "East Expansion Objective", "expansion", 37.65, 41.4),
            ("expansion-west", "West Expansion Objective", "expansion", 6.21, 18.9),
        ),
        objective_role_counts=_OBJECTIVE_ROLE_COUNTS,
        terrain_area_specs=(
            (
                "dense-7x11-5-east-expansion",
                FOOTPRINT_7X11_5,
                TerrainAreaClassification.DENSE,
                37.25,
                41.28,
                0.0,
            ),
            (
                "dense-7x11-5-attacker-home",
                FOOTPRINT_7X11_5,
                TerrainAreaClassification.DENSE,
                17.07,
                48.89,
                180.0,
            ),
            (
                "light-10x2-5-attacker-midfield",
                FOOTPRINT_10X2_5,
                TerrainAreaClassification.LIGHT,
                29.02,
                48.42,
                0.0,
            ),
            (
                "light-6x4-attacker-west",
                FOOTPRINT_6X4,
                TerrainAreaClassification.LIGHT,
                6.27,
                43.7,
                0.0,
            ),
            (
                "light-6x2-east-midfield",
                FOOTPRINT_6X2,
                TerrainAreaClassification.LIGHT,
                36.02,
                29.94,
                0.0,
            ),
            (
                "light-6x4-east-midfield",
                FOOTPRINT_6X4,
                TerrainAreaClassification.LIGHT,
                32.83,
                25.71,
                90.0,
            ),
            (
                "dense-8x11-5-polygon-north-center",
                FOOTPRINT_8X11_5_POLYGON,
                TerrainAreaClassification.DENSE,
                22.57,
                35.41,
                0.0,
            ),
            (
                "light-6x2-defender-east",
                FOOTPRINT_6X2,
                TerrainAreaClassification.LIGHT,
                33.79,
                10.84,
                90.0,
            ),
        ),
        terrain_area_mirror_pairs=(
            ("dense-7x11-5-east-expansion", "dense-7x11-5-west-expansion"),
            ("dense-7x11-5-attacker-home", "dense-7x11-5-defender-home"),
            ("light-10x2-5-attacker-midfield", "light-10x2-5-defender-midfield"),
            ("light-6x4-attacker-west", "light-6x4-defender-east"),
            ("light-6x2-east-midfield", "light-6x2-west-midfield"),
            ("light-6x4-east-midfield", "light-6x4-west-midfield"),
            (
                "dense-8x11-5-polygon-north-center",
                "dense-8x11-5-polygon-south-center",
            ),
            ("light-6x2-defender-east", "light-6x2-attacker-west"),
        ),
    ),
    EventBattlefieldLayoutSource(
        layout_id=DISRUPTION_VS_RECONNAISSANCE_LAYOUT_B_ID,
        name="Disruption vs Reconnaissance - Smoke and Mirrors / Surveil the Foe - Layout B",
        source_layout_id=(
            "gw_event_companion_v1_disruption_vs_reconnaissance_"
            "smoke_and_mirrors_surveil_the_foe_layout_b"
        ),
        objective_specs=(
            ("attacker-home", "Attacker Home Objective", "attacker_home", 7.55, 44.17),
            ("defender-home", "Defender Home Objective", "defender_home", 36.53, 16.02),
            ("central-west", "West Central Objective", "central", 14.31, 28.95),
            ("central-east", "East Central Objective", "central", 29.24, 31.45),
            ("expansion-north", "North Expansion Objective", "expansion", 24.0, 51.43),
            ("expansion-south", "South Expansion Objective", "expansion", 20.05, 8.6),
        ),
        objective_role_counts=_OBJECTIVE_ROLE_COUNTS,
        terrain_area_specs=(
            (
                "dense-7x11-5-attacker-home",
                FOOTPRINT_7X11_5,
                TerrainAreaClassification.DENSE,
                7.23,
                42.21,
                0.0,
            ),
            (
                "dense-7x11-5-central-west",
                FOOTPRINT_7X11_5,
                TerrainAreaClassification.DENSE,
                16.98,
                26.55,
                330.0,
            ),
            (
                "light-6x2-north-west",
                FOOTPRINT_6X2,
                TerrainAreaClassification.LIGHT,
                12.15,
                51.12,
                90.0,
            ),
            (
                "dense-8x11-5-polygon-south-west",
                FOOTPRINT_8X11_5_POLYGON,
                TerrainAreaClassification.DENSE,
                19.34,
                9.64,
                315.0,
            ),
            (
                "light-6x2-south-west",
                FOOTPRINT_6X2,
                TerrainAreaClassification.LIGHT,
                8.1,
                16.56,
                55.0,
            ),
            (
                "light-6x4-west-midfield",
                FOOTPRINT_6X4,
                TerrainAreaClassification.LIGHT,
                8.48,
                26.38,
                45.0,
            ),
            (
                "light-10x2-5-north-west",
                FOOTPRINT_10X2_5,
                TerrainAreaClassification.LIGHT,
                17.4,
                39.11,
                60.0,
            ),
            (
                "light-6x4-north-east",
                FOOTPRINT_6X4,
                TerrainAreaClassification.LIGHT,
                36.39,
                49.89,
                30.0,
            ),
        ),
        terrain_area_mirror_pairs=(
            ("dense-7x11-5-attacker-home", "dense-7x11-5-defender-home"),
            ("dense-7x11-5-central-west", "dense-7x11-5-central-east"),
            ("light-6x2-north-west", "light-6x2-south-east"),
            (
                "dense-8x11-5-polygon-south-west",
                "dense-8x11-5-polygon-north-east",
            ),
            ("light-6x2-south-west", "light-6x2-north-east"),
            ("light-6x4-west-midfield", "light-6x4-east-midfield"),
            ("light-10x2-5-north-west", "light-10x2-5-south-east"),
            ("light-6x4-north-east", "light-6x4-south-west"),
        ),
    ),
    EventBattlefieldLayoutSource(
        layout_id=DISRUPTION_VS_RECONNAISSANCE_LAYOUT_C_ID,
        name="Disruption vs Reconnaissance - Smoke and Mirrors / Surveil the Foe - Layout C",
        source_layout_id=(
            "gw_event_companion_v1_disruption_vs_reconnaissance_"
            "smoke_and_mirrors_surveil_the_foe_layout_c"
        ),
        objective_specs=(
            ("attacker-home", "Attacker Home Objective", "attacker_home", 6.45, 45.39),
            ("defender-home", "Defender Home Objective", "defender_home", 37.4, 14.91),
            ("central-north-west", "North-west Central Objective", "central", 18.49, 33.93),
            ("central-south-east", "South-east Central Objective", "central", 25.52, 26.0),
            ("expansion-north-east", "North-east Expansion Objective", "expansion", 35.62, 50.96),
            ("expansion-south-west", "South-west Expansion Objective", "expansion", 8.75, 9.07),
        ),
        objective_role_counts=_OBJECTIVE_ROLE_COUNTS,
        terrain_area_specs=(
            (
                "dense-8x11-5-polygon-north-east",
                FOOTPRINT_8X11_5_POLYGON,
                TerrainAreaClassification.DENSE,
                35.51,
                50.39,
                315.0,
            ),
            (
                "dense-7x11-5-attacker-home",
                FOOTPRINT_7X11_5,
                TerrainAreaClassification.DENSE,
                6.85,
                44.21,
                0.0,
            ),
            (
                "light-6x2-north-west",
                FOOTPRINT_6X2,
                TerrainAreaClassification.LIGHT,
                17.03,
                44.15,
                0.0,
            ),
            (
                "light-10x2-5-north-center",
                FOOTPRINT_10X2_5,
                TerrainAreaClassification.LIGHT,
                21.35,
                50.07,
                90.0,
            ),
            (
                "light-6x4-south-west-midfield",
                FOOTPRINT_6X4,
                TerrainAreaClassification.LIGHT,
                12.69,
                18.4,
                0.0,
            ),
            (
                "dense-7x11-5-central-north-west",
                FOOTPRINT_7X11_5,
                TerrainAreaClassification.DENSE,
                20.02,
                36.05,
                90.0,
            ),
            (
                "light-6x4-east-midfield",
                FOOTPRINT_6X4,
                TerrainAreaClassification.LIGHT,
                34.71,
                29.57,
                90.0,
            ),
            (
                "light-6x2-east-midfield",
                FOOTPRINT_6X2,
                TerrainAreaClassification.LIGHT,
                37.89,
                34.1,
                0.0,
            ),
        ),
        terrain_area_mirror_pairs=(
            (
                "dense-8x11-5-polygon-north-east",
                "dense-8x11-5-polygon-south-west",
            ),
            ("dense-7x11-5-attacker-home", "dense-7x11-5-defender-home"),
            ("light-6x2-north-west", "light-6x2-south-east"),
            ("light-10x2-5-north-center", "light-10x2-5-south-center"),
            ("light-6x4-south-west-midfield", "light-6x4-north-east-midfield"),
            (
                "dense-7x11-5-central-north-west",
                "dense-7x11-5-central-south-east",
            ),
            ("light-6x4-east-midfield", "light-6x4-west-midfield"),
            ("light-6x2-east-midfield", "light-6x2-west-midfield"),
        ),
    ),
)
