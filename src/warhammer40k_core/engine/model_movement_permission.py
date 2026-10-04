"""Per-model absent-M authority for every witnessed movement family."""

from dataclasses import replace

from warhammer40k_core.engine.movement_budget_modifiers import model_movement_characteristic
from warhammer40k_core.engine.phase import GameLifecycleError
from warhammer40k_core.engine.unit_factory import ModelInstance
from warhammer40k_core.geometry.pathing import PathValidationContext


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
