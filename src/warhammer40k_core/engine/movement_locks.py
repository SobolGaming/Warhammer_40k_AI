"""Shared activity restrictions for every ordinary and reactive movement owner."""

from __future__ import annotations

from typing import TYPE_CHECKING

from warhammer40k_core.engine.aircraft_rules import AIRCRAFT_INGRESS_ONLY
from warhammer40k_core.engine.ingress_lifetimes import LOCK_REASON, ingress_movement_locked
from warhammer40k_core.engine.phase_movement_history import surge_locked
from warhammer40k_core.engine.rules_units import RulesUnitView, rules_unit_view_by_id

if TYPE_CHECKING:
    from warhammer40k_core.engine.game_state import GameState


def movement_lock_reason(state: GameState, unit_instance_id: str) -> str | None:
    return rules_unit_movement_lock_reason(
        state, rules_unit_view_by_id(state=state, unit_instance_id=unit_instance_id)
    )


def rules_unit_movement_lock_reason(state: GameState, rules_unit: RulesUnitView) -> str | None:
    """Reuse an engine-owned canonical view, including retained model presence."""
    if "AIRCRAFT" in rules_unit.keywords:
        return AIRCRAFT_INGRESS_ONLY
    unit_instance_id = rules_unit.unit_instance_id
    if ingress_movement_locked(state, unit_instance_id):
        return LOCK_REASON
    return "surge_movement_locked_this_phase" if surge_locked(state, unit_instance_id) else None
