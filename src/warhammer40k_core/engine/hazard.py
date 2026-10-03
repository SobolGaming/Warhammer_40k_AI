from __future__ import annotations

from warhammer40k_core.core.dice import DiceExpression, DiceRollSpec, DiceRollState
from warhammer40k_core.engine.phase import GameLifecycleError
from warhammer40k_core.engine.rules_units import RulesUnitView
from warhammer40k_core.engine.unit_factory import UnitInstance

CORE_HAZARD_ROLLS_RULE_ID = "core_rules_hazard_rolls"
HAZARD_ROLL_FAILURE_THRESHOLD = 2


def hazard_roll_spec(
    *,
    reason: str,
    roll_type: str,
    actor_id: str,
    quantity: int = 1,
) -> DiceRollSpec:
    return DiceRollSpec(
        expression=DiceExpression(quantity=quantity, sides=6),
        reason=reason,
        roll_type=roll_type,
        actor_id=actor_id,
    )


def hazard_roll_failed(roll_state: DiceRollState) -> bool:
    if type(roll_state) is not DiceRollState:
        raise GameLifecycleError("Hazard roll failure check requires DiceRollState.")
    return roll_state.current_total <= HAZARD_ROLL_FAILURE_THRESHOLD


def failed_hazard_roll_indices(roll_state: DiceRollState) -> tuple[int, ...]:
    if type(roll_state) is not DiceRollState:
        raise GameLifecycleError("Hazard roll failure check requires DiceRollState.")
    expression = roll_state.original_result.spec.expression
    if expression.sides != 6 or expression.modifier != 0:
        raise GameLifecycleError("Hazard rolls require unmodified D6 values.")
    return tuple(
        index
        for index, value in enumerate(roll_state.current_values)
        if value <= HAZARD_ROLL_FAILURE_THRESHOLD
    )


def hazard_mortal_wounds_per_failed_roll(unit: UnitInstance | RulesUnitView) -> int:
    """06.03: every rules-present model, not the unit keyword union, must qualify."""
    if type(unit) is UnitInstance:
        models = unit.alive_own_models()
    elif type(unit) is RulesUnitView:
        models = tuple(
            model
            for model in unit.own_models
            if model.is_alive or model.model_instance_id in unit.retained_model_ids
        )
    else:
        raise GameLifecycleError("Hazard mortal wounds require a UnitInstance or RulesUnitView.")
    return (
        3
        if models
        and all("MONSTER" in model.keywords or "VEHICLE" in model.keywords for model in models)
        else 1
    )
