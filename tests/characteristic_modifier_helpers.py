from __future__ import annotations

from warhammer40k_core.core.attributes import Characteristic
from warhammer40k_core.core.modifiers import ModifierStack
from warhammer40k_core.engine.battle_shock_historical_authority import (
    HistoricalBattleShockAuthorityContext,
)
from warhammer40k_core.engine.runtime_characteristic_modifiers import bind_characteristic_terms
from warhammer40k_core.engine.runtime_modifiers import (
    HistoricalLeadershipModifierHandler,
    MovementBudgetModifierBinding,
    MovementBudgetModifierContext,
    MovementBudgetModifierHandler,
    ObjectiveControlModifierBinding,
    ObjectiveControlModifierContext,
    ObjectiveControlModifierHandler,
    RuntimeModifierRegistry,
    UnitCharacteristicModifierBinding,
    UnitCharacteristicModifierContext,
    UnitCharacteristicModifierHandler,
)


def resolve_movement_handler(
    handler: MovementBudgetModifierHandler,
    context: MovementBudgetModifierContext,
) -> float:
    return RuntimeModifierRegistry.from_bindings(
        movement_budget_modifier_bindings=(
            MovementBudgetModifierBinding("test:movement", "test:source", handler),
        )
    ).modified_movement_inches(context)


def resolve_characteristic_handler(
    handler: UnitCharacteristicModifierHandler,
    context: UnitCharacteristicModifierContext,
) -> int:
    return RuntimeModifierRegistry.from_bindings(
        unit_characteristic_modifier_bindings=(
            UnitCharacteristicModifierBinding("test:characteristic", "test:source", handler),
        )
    ).modified_unit_characteristic(context)


def resolve_objective_control_handler(
    handler: ObjectiveControlModifierHandler,
    context: ObjectiveControlModifierContext,
) -> int:
    return RuntimeModifierRegistry.from_bindings(
        objective_control_modifier_bindings=(
            ObjectiveControlModifierBinding("test:objective-control", "test:source", handler),
        )
    ).modified_objective_control(context)


def resolve_historical_handler(
    handler: HistoricalLeadershipModifierHandler,
    context: HistoricalBattleShockAuthorityContext,
    current: int,
) -> int:
    return (
        ModifierStack(
            characteristic=Characteristic.LEADERSHIP,
            raw_value=current,
            modifiers=bind_characteristic_terms(
                modifier_id="test:leadership",
                source_id="test:source",
                characteristic=Characteristic.LEADERSHIP,
                terms=handler(context, current),
            ),
        )
        .resolve()
        .final
    )
