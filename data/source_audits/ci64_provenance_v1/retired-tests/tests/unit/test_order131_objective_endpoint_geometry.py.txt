"""Legal witnesses distinguish closest endpoints from mere search exhaustion."""

from __future__ import annotations

import math
from dataclasses import replace

import pytest
from tests.phase13b_shooting_declaration_helpers import _display_geometry

from warhammer40k_core.core.objectives import ObjectiveMarker
from warhammer40k_core.core.ruleset_descriptor import (
    MovementMode,
    RulesetDescriptor,
    TerrainFeatureKind,
)
from warhammer40k_core.engine.battlefield_state import ModelDisplacementKind
from warhammer40k_core.engine.movement_legality import MovementLegalityContext
from warhammer40k_core.engine.objective_geometry import ObjectiveGeometry
from warhammer40k_core.engine.objective_movement_constraint import (
    objective_endpoint_evidence,
    objective_goal,
)
from warhammer40k_core.geometry.base import CircularBase
from warhammer40k_core.geometry.movement_reachability import MovementReachabilityQuery
from warhammer40k_core.geometry.pathing import PathWitness
from warhammer40k_core.geometry.pose import Pose
from warhammer40k_core.geometry.terrain import TerrainFeatureDefinition, TerrainWallDefinition
from warhammer40k_core.geometry.volume import Model, ModelVolume


@pytest.mark.parametrize("wall", [False, True], ids=["open", "wall"])
@pytest.mark.parametrize("rotation", [0.0, 45.0], ids=["cardinal", "rotated"])
@pytest.mark.parametrize("budget", [5.0, 6.0], ids=["endpoint-exclusion", "path-detour-exclusion"])
@pytest.mark.parametrize("distance", [3.0, 4.0], ids=["insufficient", "closest-wall"])
def test_continuous_wall_endpoint_proof_requires_a_legal_full_witness(
    wall: bool, rotation: float, budget: float, distance: float
) -> None:
    angle = math.radians(rotation)

    def pose(x: float) -> Pose:
        return Pose.at(15 + (x - 15) * math.cos(angle), 20 + (x - 15) * math.sin(angle))

    source = Model("objective:mover", pose(10), CircularBase(0.5), ModelVolume(1))
    endpoint = replace(source, pose=pose(10 + distance - (1e-9 if wall else 0)))
    witness = PathWitness.for_paths(((source.model_id, (source.pose, pose(12), endpoint.pose)),))
    display = _display_geometry(
        center_x_inches=15, center_y_inches=20, width_inches=40, depth_inches=40
    )
    feature = TerrainFeatureDefinition(
        feature_id="objective:wall",
        feature_kind=TerrainFeatureKind.HILLS,
        footprint_center_x_inches=15,
        footprint_center_y_inches=20,
        footprint_width_inches=40,
        footprint_depth_inches=40,
        rules_footprint_polygon=display.footprint_polygon,
        display_geometry=display,
        walls=(TerrainWallDefinition("wall", 15, 20, 0, 1, 40, 10, rotation),),
    )
    features = (feature,) if wall else ()
    # Public movement carries typed terrain features without requiring duplicate
    # raw volumes. The shared terrain owner still validates the complete wall.
    volumes = ()
    legality = MovementLegalityContext.from_keywords(
        keywords=("INFANTRY",),
        ruleset_descriptor=RulesetDescriptor.warhammer_40000_eleventh(),
        movement_mode=MovementMode.NORMAL,
        movement_phase_action=None,
        displacement_kind=ModelDisplacementKind.NORMAL_MOVE,
    )
    marker_pose = pose(30)
    marker = ObjectiveMarker(
        "objective", "Objective", marker_pose.position.x, marker_pose.position.y
    )
    objective = ObjectiveGeometry.from_marker(marker)
    query = MovementReachabilityQuery(
        path_context=legality.to_path_validation_context(
            moving_model=source,
            witness=witness,
            battlefield_width_inches=100,
            battlefield_depth_inches=100,
            friendly_models=(),
            enemy_models=(),
            terrain=volumes,
            movement_distance_budget_inches=budget,
        ),
        terrain_context=legality.to_terrain_path_legality_context(
            moving_model=source,
            witness=witness,
            terrain=volumes,
            terrain_features=features,
        ),
        goal=objective_goal(objective),
        prove_coherent_endpoint_exclusion=True,
    )
    assert query.path_context.validate().is_valid
    assert query.terrain_context.validate().is_valid
    evidence, code = objective_endpoint_evidence(
        query=query, endpoint=endpoint, objective=objective
    )
    if wall and distance == 4:
        assert code is None, evidence
        assert evidence["approach_status"] == "endpoint_unreachable"
    else:
        assert code == "objective_approach_closest_endpoint_not_reached", evidence
        assert evidence["alternative_witness"] is not None
