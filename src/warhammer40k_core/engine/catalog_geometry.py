from __future__ import annotations

from warhammer40k_core.engine.battlefield_state import (
    BattlefieldScenario,
    UnitPlacement,
    geometry_model_for_placement,
)
from warhammer40k_core.geometry.volume import Model


def alive_geometry_models_for_placement(
    *,
    scenario: BattlefieldScenario,
    unit_placement: UnitPlacement,
    model_instance_id: str | None = None,
) -> tuple[Model, ...]:
    models: list[Model] = []
    for placement in unit_placement.model_placements:
        if model_instance_id is not None and placement.model_instance_id != model_instance_id:
            continue
        model = scenario.model_instance_for_placement(placement)
        if not model.is_alive:
            continue
        models.append(geometry_model_for_placement(model=model, placement=placement))
    return tuple(models)
