"""Physical model authority, endpoint support and unchanged dense traversal."""

# pyright: reportPrivateUsage=false
from dataclasses import replace

import pytest
from tests.d07_upper_floor_helpers import model_ownership_config, upper_floor_config

from warhammer40k_core.core.ruleset_descriptor import TerrainFeatureKind
from warhammer40k_core.engine.battlefield_state import ModelPlacement, geometry_model_for_placement
from warhammer40k_core.engine.emergency_disembark_placement import _setup_terrain
from warhammer40k_core.engine.endpoint_placement import terrain_endpoint_placement_violation
from warhammer40k_core.engine.model_movement_permission import model_movement_terrain_context
from warhammer40k_core.engine.phase import GameLifecycleError
from warhammer40k_core.engine.unit_factory import UnitFactory
from warhammer40k_core.geometry.pathing import PathWitness, TerrainPathLegalityContext
from warhammer40k_core.geometry.pose import Pose


@pytest.mark.parametrize("keyword", ["MONSTER", "INFANTRY", "VEHICLE"])
def test_upper_floor_setup_and_movement_are_model_owned(keyword: str) -> None:
    config = (
        upper_floor_config(player="player-a")
        if keyword == "MONSTER"
        else model_ownership_config(player="player-a", attached=False)
    )
    assert config.army_catalog is not None
    assert config.mission_setup is not None
    selection = config.army_muster_requests[0].unit_selections[0]
    unit = UnitFactory(catalog=config.army_catalog).instantiate_unit(
        army_id="army-alpha",
        selection=selection,
        datasheet=config.army_catalog.datasheet_by_id(selection.datasheet_id),
    )
    model = next(model for model in unit.own_models if keyword in model.keywords)
    feature = config.mission_setup.terrain_features[0]
    physical = geometry_model_for_placement(
        model=model,
        placement=ModelPlacement(
            army_id="army-alpha",
            player_id="player-a",
            unit_instance_id=unit.unit_instance_id,
            model_instance_id=model.model_instance_id,
            pose=Pose.at(13, 13, 3),
        ),
    )
    permitted = keyword != "VEHICLE"
    result = terrain_endpoint_placement_violation(
        model=physical,
        unit=unit,
        ruleset_descriptor=config.ruleset_descriptor,
        terrain_features=(feature,),
        violation_code="d07:setup",
        placement_label="D07 setup",
    )
    assert (result is None) is permitted
    assert _setup_terrain(feature, model, config.ruleset_descriptor).elevated_allowed is permitted
    context = TerrainPathLegalityContext(
        moving_model=physical,
        witness=PathWitness.for_paths(((physical.model_id, (physical.pose, Pose.at(12, 13, 3))),)),
        terrain=feature.terrain_volumes(),
        terrain_features=(feature,),
        terrain_movement_policy=config.ruleset_descriptor.terrain_movement_policy,
        movement_keywords=unit.keywords,
    )
    bound = model_movement_terrain_context(model=model, context=context)
    assert bound.validate().is_valid is permitted
    assert TerrainPathLegalityContext.from_payload(bound.to_payload()) == bound
    # Only the endpoint permission inventory changes; traversal and physical inputs remain exact.
    assert replace(bound, terrain_movement_policy=context.terrain_movement_policy) == context
    for original, narrowed in zip(
        context.terrain_movement_policy.feature_policies,
        bound.terrain_movement_policy.feature_policies,
        strict=True,
    ):
        assert (
            replace(narrowed, upper_floor_allowed_keywords=original.upper_floor_allowed_keywords)
            == original
        )
    ruins = config.ruleset_descriptor.terrain_movement_policy.policy_for_feature_kind(
        TerrainFeatureKind.RUINS
    )
    assert "MONSTER" in ruins.upper_floor_allowed_keywords
    assert "MONSTER" not in ruins.through_terrain_allowed_keywords
    assert "SWARM" in ruins.upper_floor_allowed_keywords
    if keyword == "VEHICLE":
        # An explicit all-model grant is distinct from intrinsic siblings' keywords.
        granted = model_movement_terrain_context(
            model=model,
            context=replace(context, movement_keywords=(*context.movement_keywords, "FLY")),
            granted_keywords=("FLY",),
        )
        assert granted.validate().is_valid
    with pytest.raises(GameLifecycleError, match="identity drifted"):
        model_movement_terrain_context(
            model=replace(model, model_instance_id=f"{model.model_instance_id}-other"),
            context=context,
        )
