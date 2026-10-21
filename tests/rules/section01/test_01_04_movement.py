"""Constructed movement contracts always carry valid paths and solver evidence."""

from dataclasses import replace
from math import isclose

import pytest

from tests.support.section01_geometry import witnessed_query
from warhammer40k_core.core.objectives import ObjectiveMarker
from warhammer40k_core.engine.objective_geometry import ObjectiveGeometry
from warhammer40k_core.engine.objective_movement_constraint import (
    objective_endpoint_evidence,
    objective_goal,
)
from warhammer40k_core.geometry.base import CircularBase
from warhammer40k_core.geometry.base_contact import establish_deemed_base_contact
from warhammer40k_core.geometry.model_body import ModelBodyPart
from warhammer40k_core.geometry.movement_reachability import (
    MovementGoal,
    MovementReachabilityStatus,
    movement_reachability,
)
from warhammer40k_core.geometry.pose import Pose
from warhammer40k_core.geometry.volume import Model, ModelVolume


@pytest.mark.parametrize(("endpoint_x", "valid"), [(8, True), (7.5, False)])
def test_01_04_03_unreachable_target_requires_maximum_approach(
    endpoint_x: float, valid: bool
) -> None:
    from warhammer40k_core.core.ruleset_descriptor import RulesetDescriptor
    from warhammer40k_core.engine.surge_movement import surge_endpoint_evidence

    source = Model("mover", Pose.at(5, 10), CircularBase(0.5), ModelVolume(1))
    target = replace(source, model_id="enemy", pose=Pose.at(10, 10))
    endpoint = replace(source, pose=Pose.at(endpoint_x, 10))
    query = witnessed_query(
        source,
        endpoint.pose,
        3,
        MovementGoal(models=(target,), range_inches=0),
        (target,),
    )
    assert query.path_context.validate().is_valid
    evidence, code = surge_endpoint_evidence(
        query=query,
        endpoint=endpoint,
        target_id="enemy-unit",
        component_unit_instance_id="moving-unit",
        ruleset=RulesetDescriptor.warhammer_40000_eleventh(),
    )
    assert (code is None) is valid, evidence
    if not valid:
        assert code == "surge_maximum_approach_not_reached"


@pytest.mark.parametrize(
    ("start", "end", "budget", "valid"),
    [
        (5, 8, 3, True),
        (5, 7.5, 3, False),
        (15, 16, 1, True),
        (17, 16, 1, True),
        (17, 12, 5, False),
    ],
)
def test_01_04_03_objective_optimal_endpoint_or_stay_in_range(
    start: float, end: float, budget: float, valid: bool
) -> None:
    source = Model("mover", Pose.at(start, 10), CircularBase(0.5), ModelVolume(1))
    objective = ObjectiveGeometry.from_marker(ObjectiveMarker("marker", "Core objective", 20, 10))
    endpoint = replace(source, pose=Pose.at(end, 10))
    query = witnessed_query(source, endpoint.pose, budget, objective_goal(objective))
    assert query.path_context.validate().is_valid
    assert query.terrain_context.validate().is_valid
    evidence, code = objective_endpoint_evidence(
        query=query, endpoint=endpoint, objective=objective
    )
    assert (code is None) is valid, evidence
    if not valid:
        assert code in {
            "objective_approach_closest_endpoint_not_reached",
            "objective_approach_range_not_reached",
        }


@pytest.mark.parametrize("budget", [3, 4])
def test_01_04_03_contact_goal_requires_sufficient_legal_move(budget: float) -> None:
    source = Model("mover", Pose.at(5, 10), CircularBase(0.5), ModelVolume(1))
    target = replace(source, model_id="target", pose=Pose.at(10, 10))
    query = witnessed_query(
        source,
        Pose.at(5 + budget, 10),
        budget,
        MovementGoal(models=(target,), range_inches=1e-9),
        (target,),
    )
    assert query.path_context.validate().is_valid
    result = movement_reachability(query)
    if budget == 4:
        assert result.status is MovementReachabilityStatus.REACHABLE
        assert result.witness is not None
        endpoint = replace(source, pose=result.witness.final_pose_for_model(source.model_id))
        assert endpoint.range_to(target) <= 1e-8
    else:
        assert result.status in {
            MovementReachabilityStatus.UNREACHABLE,
            MovementReachabilityStatus.ENDPOINT_UNREACHABLE,
        }
        assert result.witness is None


@pytest.mark.parametrize(
    ("end", "budget", "valid"),
    [(8, 4, True), (8, 3, False), (7.8, 4, False), (6.9, 4, False)],
)
def test_01_04_04_overhang_requires_all_three_conditions(
    end: float, budget: float, valid: bool
) -> None:
    source = Model("mover", Pose.at(5, 10), CircularBase(0.5), ModelVolume(1))
    target = Model(
        "overhang",
        Pose.at(10, 10),
        CircularBase(0.5),
        ModelVolume(1),
        body_parts=(ModelBodyPart("body", CircularBase(1.5), 0, 0, 0, 1, "constructed:overhang"),),
    )
    query = witnessed_query(
        source,
        Pose.at(end, 10),
        budget,
        MovementGoal(models=(target,), range_inches=1e-9),
        (target,),
    )
    assert query.path_context.validate().is_valid
    assert query.terrain_context.validate().is_valid
    contact = establish_deemed_base_contact(
        query=query,
        enemy_model_id=target.model_id,
        source_rule_id="constructed:01.04.04",
    )
    assert (contact is not None) is valid
    if contact:
        assert isclose(
            contact.without_overhang_witness.final_pose_for_model(source.model_id).position.x,
            9,
            abs_tol=1e-9,
        )
