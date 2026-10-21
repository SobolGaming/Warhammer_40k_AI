"""06.01 and FAQ53: physical native geometry plus labelled millimetre contracts."""

from dataclasses import replace

import pytest

from tests.support.section02_fixtures import LORD_EXULTANT, MAULERFIEND, Section02Definitions
from tests.support.section03_fixtures import geometry
from warhammer40k_core.core.ruleset_descriptor import RulesetDescriptor, TerrainFeatureKind
from warhammer40k_core.core.terrain_display import TerrainDisplayGeometry
from warhammer40k_core.core.visibility import TerrainVisibilityContext, VisibilityQuery
from warhammer40k_core.geometry.pose import GeometryError, Point3, Pose
from warhammer40k_core.geometry.terrain import (
    ObstacleVolume,
    TerrainFeatureDefinition,
    TerrainFloorDefinition,
    TerrainWallDefinition,
)


@pytest.mark.parametrize(("edge", "clear"), [(0.49 / 25.4, False), (0.51 / 25.4, True)])
@pytest.mark.parametrize("height", [1.0, 4.0])
def test_one_millimetre_corridor_and_vertical_clearance(
    edge: float, clear: bool, height: float
) -> None:
    # Constructed submillimetre terrain, at real production segment evaluator.
    wall = ObstacleVolume(
        terrain_id="s06:edge", bottom_center=Point3(0, edge + 0.05, 0), width=1, depth=0.1, height=3
    )
    result = VisibilityQuery.from_segment(
        Point3(-3, 0, height), Point3(3, 0, height), static_terrain=(wall,)
    ).resolve()
    assert result.has_line_of_sight is (clear or height > 3)


@pytest.mark.parametrize(
    ("height", "visible", "fully"),
    [(0.0, True, True), (1.0, True, True), (3.0, True, False), (8.0, False, False)],
)
def test_any_model_part_and_every_facing_part_native_geometry(
    section06_definitions: Section02Definitions,
    height: float,
    visible: bool,
    fully: bool,
) -> None:
    d = section06_definitions
    observer_unit = d.unit(MAULERFIEND)
    target_unit = d.unit(LORD_EXULTANT, identity="target")
    observer = geometry(observer_unit, (Pose.at(10, 10),))[0]
    target = geometry(target_unit, (Pose.at(20, 10),))[0]
    walls = (
        ()
        if height == 0
        else (
            ObstacleVolume(
                terrain_id="s06:wall",
                bottom_center=Point3(15, 10, 0),
                width=0.2,
                depth=20,
                height=height,
            ),
        )
    )
    context = TerrainVisibilityContext.from_ruleset_descriptor(
        ruleset_descriptor=RulesetDescriptor.warhammer_40000_eleventh(),
        los_cache_key="s06:parts",
        observer_model=observer,
        target_models=(target,),
        target_model_keywords=((target.model_id, target_unit.own_models[0].keywords),),
        terrain_volumes=walls,
        observer_keywords=observer_unit.own_models[0].keywords,
    )
    witness = context.resolve_line_of_sight()
    assert witness.unit_visible is visible
    assert witness.unit_fully_visible is fully
    assert witness.visible_model_ids == ((target.model_id,) if visible else ())
    if height == 1:
        # Base-level sight is blocked; native upper-body origins see every facing part.
        assert (
            not VisibilityQuery.from_segment(
                Point3(10, 10, 0), Point3(20, 10, 0), static_terrain=walls
            )
            .resolve()
            .has_line_of_sight
        )
        assert witness.unit_fully_visible
    changed = replace(context, target_models=(replace(target, pose=Pose.at(22, 10)),))
    with pytest.raises(GeometryError, match=r"geometry|evidence"):
        changed.benefit_of_cover(witness)


@pytest.mark.parametrize("blocked", [0, 1, 2])
def test_unit_visible_any_and_fully_visible_all_native_members(
    section06_definitions: Section02Definitions, blocked: int
) -> None:
    d = section06_definitions
    observer = geometry(d.unit(LORD_EXULTANT), (Pose.at(10, 10),))[0]
    unit = d.unit()
    # Two surviving physical native models are a casualty-state contract.
    unit = replace(unit, own_models=unit.own_models[:2])
    targets = geometry(unit, (Pose.at(20, 10), Pose.at(20, 20)))
    walls = tuple(
        ObstacleVolume(
            terrain_id=f"s06:enclose-{i}",
            bottom_center=Point3(20, 10 + 10 * i, 0),
            width=3,
            depth=3,
            height=8,
        )
        for i in range(blocked)
    )
    context = TerrainVisibilityContext.from_ruleset_descriptor(
        ruleset_descriptor=RulesetDescriptor.warhammer_40000_eleventh(),
        los_cache_key="s06:unit",
        observer_model=observer,
        target_models=targets,
        target_model_keywords=tuple(
            (m.model_id, unit.own_models[i].keywords) for i, m in enumerate(targets)
        ),
        terrain_volumes=walls,
    )
    witness = context.resolve_line_of_sight()
    assert witness.unit_visible is (blocked < 2)
    assert witness.unit_fully_visible is (blocked == 0)
    assert set(witness.visible_model_ids) == {m.model_id for m in targets[blocked:]}


def test_ruins_rules_footprint_can_block_without_physical_wall(
    section06_definitions: Section02Definitions,
) -> None:
    d = section06_definitions
    observer = geometry(d.unit(LORD_EXULTANT), (Pose.at(10, 10),))[0]
    target = geometry(d.unit(LORD_EXULTANT, identity="target"), (Pose.at(20, 10),))[0]
    display = TerrainDisplayGeometry.axis_aligned_rectangle(
        center_x_inches=15,
        center_y_inches=10,
        width_inches=4,
        depth_inches=6,
        display_template_id="s06:ruin",
    )
    ruin = TerrainFeatureDefinition(
        feature_id="s06:ruin",
        feature_kind=TerrainFeatureKind.RUINS,
        footprint_center_x_inches=15,
        footprint_center_y_inches=10,
        footprint_width_inches=4,
        footprint_depth_inches=6,
        rules_footprint_polygon=display.footprint_polygon,
        display_geometry=display,
        source_id="constructed:s06:ruin",
        walls=(
            TerrainWallDefinition(
                wall_id="off-axis",
                center_x_inches=15,
                center_y_inches=12.8,
                bottom_z_inches=0,
                width_inches=1,
                depth_inches=0.1,
                height_inches=3,
            ),
        ),
        floors=(
            TerrainFloorDefinition(
                floor_id="floor",
                center_x_inches=15,
                center_y_inches=10,
                bottom_z_inches=0,
                width_inches=4,
                depth_inches=6,
                thickness_inches=0.1,
            ),
        ),
    )
    context = TerrainVisibilityContext.from_ruleset_descriptor(
        ruleset_descriptor=RulesetDescriptor.warhammer_40000_eleventh(),
        los_cache_key="s06:ruin",
        observer_model=observer,
        target_models=(target,),
        target_model_keywords=((target.model_id, ()),),
        terrain_features=(ruin,),
    )
    assert (
        VisibilityQuery.from_segment(
            Point3(10, 10, 1), Point3(20, 10, 1), static_terrain=ruin.terrain_volumes()
        )
        .resolve()
        .has_line_of_sight
    )
    assert not context.resolve_line_of_sight().unit_visible
    assert (
        replace(context, terrain_features=(), terrain_volumes=())
        .resolve_line_of_sight()
        .unit_fully_visible
    )
