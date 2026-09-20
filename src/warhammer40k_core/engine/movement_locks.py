"""Shared activity restrictions for every ordinary and reactive movement owner."""

from __future__ import annotations

from typing import TYPE_CHECKING

from warhammer40k_core.engine.ingress_lifetimes import LOCK_REASON, ingress_movement_locked
from warhammer40k_core.engine.phase_movement_history import surge_locked

if TYPE_CHECKING:
    from warhammer40k_core.engine.game_state import GameState


def movement_lock_reason(state: GameState, unit_instance_id: str) -> str | None:
    if ingress_movement_locked(state, unit_instance_id):
        return LOCK_REASON
    return "surge_movement_locked_this_phase" if surge_locked(state, unit_instance_id) else None
