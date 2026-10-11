"""Per-model movement and upper-floor authority for witnessed movement families."""

from dataclasses import replace

from warhammer40k_core.engine.movement_budget_modifiers import model_movement_characteristic
from warhammer40k_core.engine.phase import GameLifecycleError
from warhammer40k_core.engine.unit_factory import ModelInstance
from warhammer40k_core.geometry.pathing import PathValidationContext, TerrainPathLegalityContext


def model_movement_path_context(
    *, model: ModelInstance, context: PathValidationContext
) -> PathValidationContext:
    if type(model) is not ModelInstance or type(context) is not PathValidationContext:
        raise GameLifecycleError("Movement permission requires a model and path context.")
    if model.model_instance_id != context.moving_model.model_id:
        raise GameLifecycleError("Movement permission model identity drifted.")
    if model_movement_characteristic(model).is_dash:
        return replace(context, pose_is_fixed=True, movement_distance_budget_inches=0.0)
    return context


def model_movement_terrain_context(
    *,
    model: ModelInstance,
    context: TerrainPathLegalityContext,
    granted_keywords: tuple[str, ...] = (),
) -> TerrainPathLegalityContext:
    """Bind upper-floor permission to its physical model without changing traversal.

    Explicit all-model move grants remain distinct from siblings' intrinsic keywords.
    The existing typed terrain policy carries the narrowed endpoint keyword list;
    general movement keywords and every traversal field remain unchanged.
    """
    if type(model) is not ModelInstance or type(context) is not TerrainPathLegalityContext:
        raise GameLifecycleError(
            "Terrain movement permission requires a model and terrain context."
        )
    if model.model_instance_id != context.moving_model.model_id:
        raise GameLifecycleError("Terrain movement permission model identity drifted.")
    if type(granted_keywords) is not tuple or any(type(k) is not str for k in granted_keywords):
        raise GameLifecycleError("Terrain movement granted keywords must be a tuple of tokens.")
    keywords = {*model.keywords, *granted_keywords}
    policy = context.terrain_movement_policy
    return replace(
        context,
        terrain_movement_policy=replace(
            policy,
            feature_policies=tuple(
                replace(
                    feature,
                    upper_floor_allowed_keywords=tuple(
                        keyword
                        for keyword in feature.upper_floor_allowed_keywords
                        if keyword in keywords
                    ),
                )
                for feature in policy.feature_policies
            ),
        ),
    )
