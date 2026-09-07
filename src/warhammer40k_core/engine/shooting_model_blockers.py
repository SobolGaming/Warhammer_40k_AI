from __future__ import annotations

from warhammer40k_core.core.validation import IdentifierValidator
from warhammer40k_core.engine.battlefield_state import BattlefieldScenario
from warhammer40k_core.engine.phase import GameLifecycleError
from warhammer40k_core.engine.rules_units import rules_unit_view_from_armies
from warhammer40k_core.engine.shooting_selection_range import geometry_models_for_unit_placement
from warhammer40k_core.geometry.volume import Model

_validate_identifier = IdentifierValidator(GameLifecycleError)


def shooting_dynamic_model_blockers(
    *,
    scenario: BattlefieldScenario,
    observing_unit_id: str,
    target_unit_id: str,
) -> tuple[Model, ...]:
    _validate_identifier("observing_unit_id", observing_unit_id)
    _validate_identifier("target_unit_id", target_unit_id)
    observing_rules_unit = rules_unit_view_from_armies(
        armies=scenario.armies,
        unit_instance_id=observing_unit_id,
    )
    target_rules_unit = rules_unit_view_from_armies(
        armies=scenario.armies,
        unit_instance_id=target_unit_id,
    )
    excluded_unit_ids = {
        *observing_rules_unit.component_unit_instance_ids,
        *target_rules_unit.component_unit_instance_ids,
    }
    blocker_models: list[Model] = []
    for placed_army in scenario.battlefield_state.placed_armies:
        for unit_placement in placed_army.unit_placements:
            if unit_placement.unit_instance_id in excluded_unit_ids:
                continue
            blocker_models.extend(
                geometry_models_for_unit_placement(
                    scenario=scenario,
                    unit_placement=unit_placement,
                )
            )
    return tuple(sorted(blocker_models, key=lambda model: model.model_id))
