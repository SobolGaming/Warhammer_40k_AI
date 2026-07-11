from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from warhammer40k_core.engine.game_state import GameState

CHARGE_AFTER_ADVANCE_EFFECT_KIND = "charge_after_advance_allowed"


def charge_after_advance_allowed_by_effects(
    *,
    state: GameState,
    unit_instance_id: str,
) -> bool:
    for effect in state.persisting_effects_for_unit(unit_instance_id):
        payload = effect.effect_payload
        if not isinstance(payload, dict):
            continue
        if payload.get("effect_kind") == CHARGE_AFTER_ADVANCE_EFFECT_KIND:
            return True
    return False
