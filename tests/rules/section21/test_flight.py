"""Native flight: witnessed paths, all categories, physical benefits and distance."""

from dataclasses import replace
from math import isclose

import pytest

from tests.support.section02_fixtures import Section02Definitions
from tests.support.section03_fixtures import native_state, scenario
from tests.support.section21_fixtures import LORD, SERPENT
from warhammer40k_core.core.ruleset_descriptor import MovementMode, TerrainFeatureKind
from warhammer40k_core.core.terrain_display import TerrainDisplayGeometry
from warhammer40k_core.engine.movement_legality import MovementCapabilitySet
from warhammer40k_core.engine.phases.movement import resolve_normal_move
from warhammer40k_core.engine.rules_units import rules_unit_view_by_id
from warhammer40k_core.engine.take_to_the_skies import flight_choice_context
from warhammer40k_core.geometry.pathing import PathWitness
from warhammer40k_core.geometry.pose import Point3, Pose
from warhammer40k_core.geometry.terrain import (
    TerrainFeatureDefinition,
    TerrainFloorDefinition,
    TerrainVolume,
    TerrainWallDefinition,
)
from warhammer40k_core.geometry.terrain_classification import TerrainAreaClassification


@pytest.mark.parametrize("skies", [False, True])
@pytest.mark.parametrize(
    ("distance", "valid_ground", "valid_air"),
    [(12, True, True), (12.001, True, False), (14, True, False), (14.001, False, False)],
)
def test_declared_flight_subtracts_two_from_native_maximum(
    section21_definitions: Section02Definitions,
    skies: bool,
    distance: float,
    valid_ground: bool,
    valid_air: bool,
) -> None:
    unit = section21_definitions.unit(SERPENT)
    state = native_state(section21_definitions, unit, (Pose.at(10, 10),))
    board = scenario(state)
    witness = PathWitness.for_paths(
        ((unit.own_model_ids()[0], (Pose.at(10, 10), Pose.at(10 + distance, 10))),)
    )
    result = resolve_normal_move(
        scenario=board,
        ruleset_descriptor=state.runtime_ruleset_descriptor(),
        unit_placement=board.battlefield_state.unit_placement_by_id(unit.unit_instance_id),
        state=state,
        movement_mode=MovementMode.FLY_TAKE_TO_SKIES if skies else MovementMode.NORMAL,
        path_witness=witness,
    )
    assert result.is_valid is (valid_air if skies else valid_ground)
    budget = result.path_validation_results[0].movement_distance_witness
    assert budget is not None
    assert budget.budget is not None
    assert budget.budget.max_distance_inches == (12 if skies else 14)


@pytest.mark.parametrize("skies", [False, True])
@pytest.mark.parametrize("blocker", ["infantry", "vehicle", "terrain"])
def test_flight_crosses_actual_models_and_solid_volume_only_when_declared(
    section21_definitions: Section02Definitions, skies: bool, blocker: str
) -> None:
    unit = section21_definitions.unit(SERPENT)
    enemy = section21_definitions.unit(
        SERPENT if blocker == "vehicle" else LORD, identity="blocker", army_id="enemy"
    )
    state = native_state(
        section21_definitions,
        unit,
        (Pose.at(10, 10),),
        enemy=enemy,
        enemy_poses=(Pose.at(16, 30 if blocker == "terrain" else 10),),
    )
    board = scenario(state)
    wall = (
        (TerrainVolume("s21:solid", Point3(16, 10, 0), 0.5, 8, 12),) if blocker == "terrain" else ()
    )
    result = resolve_normal_move(
        scenario=board,
        ruleset_descriptor=state.runtime_ruleset_descriptor(),
        unit_placement=board.battlefield_state.unit_placement_by_id(unit.unit_instance_id),
        state=state,
        movement_mode=MovementMode.FLY_TAKE_TO_SKIES if skies else MovementMode.NORMAL,
        path_witness=PathWitness.for_paths(
            ((unit.own_model_ids()[0], (Pose.at(10, 10), Pose.at(22, 10))),)
        ),
        terrain=wall,
    )
    # Core03 independently allows a VEHICLE to transit enemy INFANTRY.
    assert result.is_valid is (skies or blocker == "infantry"), result.movement_payload
    assert result.attempted_placement.model_placements[0].pose == Pose.at(22, 10)
    assert state.battlefield_state == board.battlefield_state


@pytest.mark.parametrize("kind", list(TerrainFeatureKind))
@pytest.mark.parametrize(
    "classification",
    [
        TerrainAreaClassification.UNKNOWN,
        TerrainAreaClassification.DENSE,
        TerrainAreaClassification.MIXED,
    ],
)
def test_committed_flight_transits_walls_in_every_terrain_category(
    section21_definitions: Section02Definitions,
    kind: TerrainFeatureKind,
    classification: TerrainAreaClassification,
) -> None:
    unit = section21_definitions.unit(SERPENT)
    state = native_state(section21_definitions, unit, (Pose.at(10, 10),))
    display = TerrainDisplayGeometry.axis_aligned_rectangle(
        center_x_inches=16,
        center_y_inches=10,
        width_inches=0.5,
        depth_inches=8,
        display_template_id=None,
    )
    feature = TerrainFeatureDefinition(
        "s21:feature",
        kind,
        16,
        10,
        0.5,
        8,
        display.footprint_polygon,
        display,
        walls=(TerrainWallDefinition("wall", 16, 10, 0, 0.5, 8, 12),),
        floors=(TerrainFloorDefinition("floor", 16, 10, 12, 0.5, 8, 0.1),),
        classification=classification,
    )
    assert state.battlefield_state is not None
    state.replace_battlefield_state(replace(state.battlefield_state, terrain_features=(feature,)))
    board = scenario(state)
    result = resolve_normal_move(
        scenario=board,
        ruleset_descriptor=state.runtime_ruleset_descriptor(),
        unit_placement=board.battlefield_state.unit_placement_by_id(unit.unit_instance_id),
        state=state,
        movement_mode=MovementMode.FLY_TAKE_TO_SKIES,
        path_witness=PathWitness.for_paths(
            ((unit.own_model_ids()[0], (Pose.at(10, 10), Pose.at(22, 10))),)
        ),
    )
    assert result.is_valid, result.movement_payload
    assert all(r.is_valid for r in result.terrain_path_legality_results)


@pytest.mark.parametrize("skies", [False, True])
def test_flight_ignores_vertical_distance_but_keeps_every_horizontal_leg(
    section21_definitions: Section02Definitions, skies: bool
) -> None:
    unit = section21_definitions.unit(SERPENT)
    state = native_state(section21_definitions, unit, (Pose.at(10, 10),))
    board = scenario(state)
    path = PathWitness.for_paths(
        (
            (
                unit.own_model_ids()[0],
                (Pose.at(10, 10), Pose.at(10, 10, 8), Pose.at(12, 10, 8), Pose.at(12, 10)),
            ),
        )
    )
    result = resolve_normal_move(
        scenario=board,
        ruleset_descriptor=state.runtime_ruleset_descriptor(),
        unit_placement=board.battlefield_state.unit_placement_by_id(unit.unit_instance_id),
        state=state,
        movement_mode=MovementMode.FLY_TAKE_TO_SKIES if skies else MovementMode.NORMAL,
        path_witness=path,
    )
    assert result.is_valid is skies
    distance = result.path_validation_results[0].movement_distance_witness
    assert distance is not None
    assert isclose(distance.total_distance_inches, 2 if skies else 18)


@pytest.mark.parametrize(
    "mode", [MovementMode.NORMAL, MovementMode.ADVANCE, MovementMode.FALL_BACK, MovementMode.CHARGE]
)
@pytest.mark.parametrize("skies", [False, True])
def test_physical_flight_benefits_are_limited_to_flying_members(
    section21_definitions: Section02Definitions, mode: MovementMode, skies: bool
) -> None:
    flyer = section21_definitions.unit(SERPENT)
    grounded = section21_definitions.unit(LORD)
    state = native_state(section21_definitions, flyer)
    for unit, expected in ((flyer, skies), (grounded, False)):
        cap = MovementCapabilitySet.from_keywords(
            unit.keywords,
            ruleset_descriptor=state.runtime_ruleset_descriptor(),
            movement_mode=mode,
            take_to_the_skies=skies,
            unit=unit,
            model_instance_id=unit.own_model_ids()[0],
            current_model_instance_ids=unit.own_model_ids(),
        )
        assert cap.has_fly is (unit is flyer)
        assert cap.ignores_vertical_distance is expected
        assert cap.can_transit_all_terrain is expected
        # Infantry has its independent ruins and friendly-model permissions.
        if unit is flyer:
            assert cap.can_move_through_terrain is expected
            assert cap.can_move_through_enemy_models is expected
        else:
            assert cap.can_traverse_ruins_walls
    view = rules_unit_view_by_id(state=state, unit_instance_id=flyer.unit_instance_id)
    context = flight_choice_context(
        unit=view, ruleset=state.runtime_ruleset_descriptor(), selected=skies
    )
    assert context["flight_penalty_inches"] == (2 if skies else 0)
    assert context["flying_model_instance_ids"] == list(flyer.own_model_ids())


@pytest.mark.parametrize("endpoint", ["overlap", "engaged", "offboard"])
def test_flight_transit_permission_never_waives_endpoint_restrictions(
    section21_definitions: Section02Definitions, endpoint: str
) -> None:
    unit = section21_definitions.unit(SERPENT)
    enemy = section21_definitions.unit(LORD, army_id="enemy", identity="target")
    state = native_state(
        section21_definitions, unit, (Pose.at(10, 10),), enemy=enemy, enemy_poses=(Pose.at(18, 10),)
    )
    end = (
        Pose.at(18, 10)
        if endpoint == "overlap"
        else Pose.at(15.5, 10)
        if endpoint == "engaged"
        else Pose.at(0, 10)
    )
    board = scenario(state)
    result = resolve_normal_move(
        scenario=board,
        ruleset_descriptor=state.runtime_ruleset_descriptor(),
        unit_placement=board.battlefield_state.unit_placement_by_id(unit.unit_instance_id),
        state=state,
        movement_mode=MovementMode.FLY_TAKE_TO_SKIES,
        path_witness=PathWitness.for_paths(((unit.own_model_ids()[0], (Pose.at(10, 10), end)),)),
    )
    assert not result.is_valid
    code = {
        "overlap": "end_on_model_overlap",
        "engaged": "enemy_engagement_range_end_forbidden",
        "offboard": "battlefield_edge_crossed",
    }[endpoint]
    assert code in str(result.movement_payload)


@pytest.mark.parametrize("typed_feature", [False, True])
@pytest.mark.parametrize("end_z", [0, 5])
def test_flight_retains_terrain_endpoint_intersection_and_support_checks(
    section21_definitions: Section02Definitions, typed_feature: bool, end_z: float
) -> None:
    unit = section21_definitions.unit(SERPENT)
    state = native_state(section21_definitions, unit, (Pose.at(10, 10),))
    volumes: tuple[TerrainVolume, ...] = (
        TerrainVolume("s21:end-wall", Point3(16, 10, 0), 1, 8, 12),
    )
    if typed_feature:
        display = TerrainDisplayGeometry.axis_aligned_rectangle(
            center_x_inches=16,
            center_y_inches=10,
            width_inches=1,
            depth_inches=8,
            display_template_id=None,
        )
        feature = TerrainFeatureDefinition(
            "s21:end-feature",
            TerrainFeatureKind.SEALED_BUILDINGS,
            16,
            10,
            1,
            8,
            display.footprint_polygon,
            display,
            walls=(TerrainWallDefinition("wall", 16, 10, 0, 1, 8, 12),),
            classification=TerrainAreaClassification.DENSE,
        )
        assert state.battlefield_state is not None
        state.replace_battlefield_state(
            replace(state.battlefield_state, terrain_features=(feature,))
        )
        volumes = ()
    board = scenario(state)
    result = resolve_normal_move(
        scenario=board,
        ruleset_descriptor=state.runtime_ruleset_descriptor(),
        unit_placement=board.battlefield_state.unit_placement_by_id(unit.unit_instance_id),
        state=state,
        movement_mode=MovementMode.FLY_TAKE_TO_SKIES,
        path_witness=PathWitness.for_paths(
            ((unit.own_model_ids()[0], (Pose.at(10, 10), Pose.at(16, 10, end_z))),)
        ),
        terrain=volumes,
    )
    assert not result.is_valid
    assert "model_cannot_be_placed_at_endpoint" in str(result.movement_payload)
