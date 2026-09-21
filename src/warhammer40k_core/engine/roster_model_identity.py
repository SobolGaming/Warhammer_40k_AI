"""Resolve an explicit profile-local roster index against immutable source models."""

from warhammer40k_core.engine.unit_factory import ModelInstance, UnitFactoryError, UnitInstance


def selected_roster_model(
    unit: UnitInstance, *, model_profile_id: str, model_index: int
) -> ModelInstance:
    if type(model_index) is not int or model_index < 1:
        raise UnitFactoryError("Roster model index must be a positive integer.")
    models = tuple(
        sorted(
            (model for model in unit.own_models if model.model_profile_id == model_profile_id),
            key=lambda model: model.model_instance_id,
        )
    )
    if model_index > len(models):
        raise UnitFactoryError("Selected roster model is absent from its source unit.")
    return models[model_index - 1]
