"""Constructed supported-platform fixtures for source-valid Combat branches."""

from dataclasses import replace

from warhammer40k_core.core.ruleset_descriptor import TerrainFeatureKind
from warhammer40k_core.engine.game_state import GameState
from warhammer40k_core.engine.unit_factory import UnitInstance
from warhammer40k_core.geometry.pose import Pose
from warhammer40k_core.geometry.terrain import TerrainFeatureDefinition, TerrainFloorDefinition


def prepare_supported_carrier_fixture(state: GameState, transport: UnitInstance) -> None:
    """Constructed lower-level fixture: ordinary sizes on an admitted small hill top.

    No production policy, hazard roll, FNP source or existing assertion changes.
    Separate public setup/native controls prove admission and exact replay.
    """
    from warhammer40k_core.core.terrain_display import TerrainDisplayGeometry

    display = TerrainDisplayGeometry.axis_aligned_rectangle(
        center_x_inches=10,
        center_y_inches=10,
        width_inches=10,
        depth_inches=10,
        display_template_id=None,
    )
    feature = TerrainFeatureDefinition(
        feature_id="order135-protected-combat-platform",
        feature_kind=TerrainFeatureKind.HILLS,
        footprint_center_x_inches=10,
        footprint_center_y_inches=10,
        footprint_width_inches=10,
        footprint_depth_inches=10,
        rules_footprint_polygon=display.footprint_polygon,
        display_geometry=display,
        floors=(
            TerrainFloorDefinition(
                floor_id="carrier-top",
                center_x_inches=10,
                center_y_inches=10,
                bottom_z_inches=5.5,
                width_inches=4,
                depth_inches=4,
                thickness_inches=0.12,
            ),
        ),
    )
    assert state.battlefield_state is not None
    carrier = state.battlefield_state.unit_placement_by_id(transport.unit_instance_id)
    carrier = replace(
        carrier,
        model_placements=tuple(
            replace(row, pose=Pose.at(row.pose.position.x, row.pose.position.y, 5.5))
            for row in carrier.model_placements
        ),
    )
    assert state.mission_setup is not None
    state.mission_setup = replace(
        state.mission_setup,
        battlefield_layout_id=None,
        deployment_map_id="order135-custom-platform-deployment",
        terrain_layout_id="order135-custom-platform-terrain",
        terrain_features=(feature,),
        terrain_areas=(),
        objective_terrain_areas=(),
        battlefield_regions=(),
    )
    state.replace_battlefield_state(
        replace(state.battlefield_state.with_unit_placement(carrier), terrain_features=(feature,))
    )
