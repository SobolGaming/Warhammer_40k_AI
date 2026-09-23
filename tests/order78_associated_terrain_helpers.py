"""Policy-only feature inside a real area, with terrain-derived Hidden."""

from __future__ import annotations

from dataclasses import replace

from tests.order78_helpers import scene
from tests.phase13b_shooting_declaration_helpers import _display_geometry, _scenario_with_unit_pose
from warhammer40k_core.core.terrain_areas import TerrainAreaClassification
from warhammer40k_core.core.visibility import TerrainVisibilityContext
from warhammer40k_core.engine.battlefield_presence import battlefield_scenario_for_state
from warhammer40k_core.engine.lifecycle import GameLifecycle
from warhammer40k_core.engine.mission_setup import MissionSetup
from warhammer40k_core.engine.shooting_terrain_visibility import (
    shooting_visibility_cache_key,
    terrain_visibility_areas_from_placements,
)
from warhammer40k_core.engine.unit_factory import UnitInstance
from warhammer40k_core.geometry.pose import Pose
from warhammer40k_core.geometry.terrain import TerrainFeatureKind
from warhammer40k_core.rules.mission_pack_import import (
    warhammer_event_companion_2026_07_mission_pack,
)


def associated_woods_scene(
    *,
    feature_classification: TerrainAreaClassification = TerrainAreaClassification.DENSE,
) -> tuple[GameLifecycle, dict[str, UnitInstance], TerrainVisibilityContext]:
    lifecycle, units = scene(hidden=False)
    state = lifecycle.state
    assert state is not None
    assert state.mission_setup is not None
    woods = replace(
        state.mission_setup.terrain_features[0],
        feature_kind=TerrainFeatureKind.WOODS,
        classification=feature_classification,
        walls=(),
        floors=(),
    )
    setup = MissionSetup.from_mission_pack(
        mission_pack=warhammer_event_companion_2026_07_mission_pack(),
        mission_pool_entry_id="mission-purge-the-foe-vs-purge-the-foe-layout-1",
        attacker_player_id="player-a",
        attacker_force_disposition_id="purge-the-foe",
        defender_player_id="player-b",
        defender_force_disposition_id="purge-the-foe",
    )
    area = next(
        area
        for area in setup.terrain_areas
        if area.classification is TerrainAreaClassification.DENSE
    )
    area = replace(
        area,
        logical_terrain_area_id=area.terrain_area_id,
        center_x_inches=23.5,
        center_y_inches=35.0,
        footprint_polygon=_display_geometry(
            center_x_inches=23.5, center_y_inches=35.0, width_inches=4.0, depth_inches=4.0
        ).footprint_polygon,
    )
    state.mission_setup = replace(
        setup, terrain_features=(woods,), terrain_areas=(area,), objective_terrain_areas=()
    )
    scenario = _scenario_with_unit_pose(
        scenario=battlefield_scenario_for_state(state=state),
        unit=units["shooter"],
        army_id="army-alpha",
        player_id="player-a",
        poses=(Pose.at(24.3 - 32 / 25.4 - 12.01, 35.0),),
    )
    state.battlefield_state = replace(scenario.battlefield_state, terrain_features=(woods,))
    scenario = battlefield_scenario_for_state(state=state)
    models = {model.model_id: model for model in scenario.placed_geometry_models()}
    target = models[units["enemy"].own_models[0].model_instance_id]
    context = TerrainVisibilityContext.from_ruleset_descriptor(
        ruleset_descriptor=lifecycle.config.ruleset_descriptor,
        los_cache_key=shooting_visibility_cache_key(
            scenario=scenario, terrain_features=(woods,), terrain_areas=(area,)
        ),
        observer_model=models[units["shooter"].own_models[0].model_instance_id],
        target_models=(target,),
        target_model_keywords=((target.model_id, units["enemy"].own_models[0].keywords),),
        observer_keywords=units["shooter"].own_models[0].keywords,
        terrain_features=(woods,),
        terrain_areas=terrain_visibility_areas_from_placements((area,)),
    )
    return lifecycle, units, context
