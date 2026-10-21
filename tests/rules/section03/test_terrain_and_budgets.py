"""Full-witness obstruction and heterogeneous-M contract; no source-stat certification."""

from dataclasses import replace

import pytest

from tests.support.section02_fixtures import CHAOS_SPAWN, Section02Definitions
from tests.support.section03_fixtures import geometry, native_state, paths, scenario
from warhammer40k_core.core.attributes import Characteristic, CharacteristicValue
from warhammer40k_core.core.ruleset_descriptor import TerrainFeatureKind
from warhammer40k_core.core.terrain_display import TerrainDisplayGeometry
from warhammer40k_core.engine.endpoint_placement import terrain_endpoint_placement_violation
from warhammer40k_core.engine.phases.movement import resolve_normal_move
from warhammer40k_core.geometry.pathing import (
    PathValidationContext,
    PathWitness,
)
from warhammer40k_core.geometry.pose import Point3, Pose
from warhammer40k_core.geometry.terrain import (
    TerrainFeatureDefinition,
    TerrainFloorDefinition,
    TerrainVolume,
    TerrainWallDefinition,
)


@pytest.mark.parametrize(("end_y", "valid"), [(10, False), (14, True)])
def test_actual_base_must_fit_entire_transit_space(
    section03_definitions: Section02Definitions, end_y: float, valid: bool
) -> None:
    unit = section03_definitions.unit(CHAOS_SPAWN)
    model = geometry(unit, (Pose.at(10, end_y), Pose.at(10, 18)))[0]
    wall = TerrainVolume("solid-wall", Point3(13, 10, 0), 0.5, 3, 5)
    witness = PathWitness.for_paths(((model.model_id, (model.pose, Pose.at(16, end_y))),))
    result = PathValidationContext(
        moving_model=model,
        witness=witness,
        battlefield_width_inches=60,
        battlefield_depth_inches=44,
        enemy_engagement_horizontal_inches=2,
        enemy_engagement_vertical_inches=5,
        terrain=(wall,),
    ).validate()
    assert result.is_valid is valid
    if not valid:
        assert result.violations[0].violation_code == "terrain_collision"


@pytest.mark.parametrize(("distance", "valid"), [(2, True), (2.001, False)])
def test_constructed_mixed_m_characteristics_keep_each_physical_model_budget(
    section03_definitions: Section02Definitions, distance: float, valid: bool
) -> None:
    native = section03_definitions.unit(CHAOS_SPAWN)
    models = tuple(
        replace(
            m,
            characteristics=tuple(
                CharacteristicValue.from_raw(Characteristic.MOVEMENT, value)
                if c.characteristic is Characteristic.MOVEMENT
                else c
                for c in m.characteristics
            ),
        )
        for m, value in zip(native.own_models, (2, 6), strict=True)
    )
    unit = replace(native, name="CONSTRUCTED mixed-M Core contract", own_models=models)
    starts = (Pose.at(10, 10), Pose.at(12.5, 10))
    ends = (Pose.at(10, 10 + distance), Pose.at(12.5, 14))
    state = native_state(section03_definitions, unit, starts)
    board = scenario(state)
    result = resolve_normal_move(
        scenario=board,
        ruleset_descriptor=state.runtime_ruleset_descriptor(),
        unit_placement=board.battlefield_state.unit_placement_by_id(unit.unit_instance_id),
        path_witness=paths(unit, starts, ends),
    )
    assert result.is_valid is valid
    distances = {
        r.movement_distance_witness.model_id: r.movement_distance_witness.budget
        for r in result.path_validation_results
        if r.movement_distance_witness is not None
    }
    assert distances[unit.own_model_ids()[0]] is not None
    if not valid:
        assert (
            result.path_validation_results[0].violations[0].violation_code
            == "movement_distance_exceeded"
        )


@pytest.mark.parametrize(("end_x", "valid"), [(13, False), (16, True)])
def test_native_model_cannot_end_embedded_in_terrain(
    section03_definitions: Section02Definitions, end_x: float, valid: bool
) -> None:
    unit = section03_definitions.unit(CHAOS_SPAWN)
    model = geometry(unit, (Pose.at(10, 10), Pose.at(10, 13)))[0]
    display = TerrainDisplayGeometry.axis_aligned_rectangle(
        center_x_inches=13,
        center_y_inches=10,
        width_inches=6,
        depth_inches=6,
        display_template_id=None,
    )
    feature = TerrainFeatureDefinition(
        "wall-feature",
        TerrainFeatureKind.RUINS,
        13,
        10,
        6,
        6,
        display.footprint_polygon,
        display,
        walls=(TerrainWallDefinition("wall", 13, 10, 0, 0.5, 3, 5),),
        floors=(TerrainFloorDefinition("floor", 13, 10, 4, 6, 6, 0.1),),
    )
    result = terrain_endpoint_placement_violation(
        model=replace(model, pose=Pose.at(end_x, 10)),
        unit=unit,
        ruleset_descriptor=native_state(section03_definitions, unit).runtime_ruleset_descriptor(),
        terrain_features=(feature,),
        violation_code="embedded_endpoint",
        placement_label="Core move",
    )
    assert (result is None) is valid
    if result is not None:
        assert result.blocker_id == "wall-feature:wall"
