"""Catalog equipment ownership consumes authenticated current ability sources."""

from warhammer40k_core.engine.phase import GameLifecycleError
from warhammer40k_core.engine.unit_factory import UnitInstance


def current_wargear_bearer_model_ids(
    *, unit: UnitInstance, current_model_instance_ids: tuple[str, ...], wargear_id: str
) -> tuple[str, ...]:
    # The shared ability-presence owner supplies living or retained source IDs.
    # Re-testing is_alive here would erase both legitimate retention lifetimes.
    current_ids = frozenset(current_model_instance_ids)
    known_model_ids = {model.model_instance_id for model in unit.own_models}
    if current_ids - known_model_ids:
        raise GameLifecycleError("Catalog rule current model evidence contains unknown models.")
    return tuple(
        sorted(
            model.model_instance_id
            for model in unit.own_models
            if model.model_instance_id in current_ids and wargear_id in model.wargear_ids
        )
    )
