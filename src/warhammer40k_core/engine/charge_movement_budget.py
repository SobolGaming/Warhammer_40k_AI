"""Current Charge arithmetic; immutable rolled dice remain the source of every revision."""

from __future__ import annotations

from dataclasses import replace
from typing import TYPE_CHECKING

from warhammer40k_core.core.dice import DiceRollState
from warhammer40k_core.core.modifiers import resolve_distance_deltas
from warhammer40k_core.engine.abilities import AbilityCatalogIndex
from warhammer40k_core.engine.charge_budget_value import (
    ChargeMoveDistanceModifier,
    ChargeMovementBudget,
)
from warhammer40k_core.engine.charge_declaration import ChargeRollRequest

if TYPE_CHECKING:
    from warhammer40k_core.engine.game_state import GameState
from warhammer40k_core.engine.movement_budget_modifiers import move_distance_modifiers
from warhammer40k_core.engine.phases.charge_modifier_ignore import charge_roll_modifiers_for_unit
from warhammer40k_core.engine.rules_units import rules_unit_view_by_id
from warhammer40k_core.engine.runtime_modifiers import RuntimeModifierRegistry


def current_charge_movement_budget(
    *,
    state: GameState,
    request: ChargeRollRequest,
    roll_state: DiceRollState,
    ability_index: AbilityCatalogIndex,
    runtime_modifier_registry: RuntimeModifierRegistry,
) -> ChargeMovementBudget:
    view = rules_unit_view_by_id(state=state, unit_instance_id=request.unit_instance_id)
    modifiers = charge_roll_modifiers_for_unit(
        state=state,
        ability_index=ability_index,
        unit=view,
        runtime_modifier_registry=runtime_modifier_registry,
    )
    modified = replace(request, roll_modifiers=modifiers).resolve_roll(roll_state)
    applications = move_distance_modifiers(state=state, unit_instance_id=view.unit_instance_id)
    rows = tuple(
        ChargeMoveDistanceModifier(row.modifier_id, row.source_id, row.delta_inches)
        for row in applications
    )
    maximum, _ = resolve_distance_deltas(
        float(modified.final_value), tuple((row.modifier_id, row.delta_inches) for row in rows)
    )
    return ChargeMovementBudget(modified, rows, maximum)
