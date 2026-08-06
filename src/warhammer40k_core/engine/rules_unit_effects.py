from __future__ import annotations

from warhammer40k_core.engine.effects import PersistingEffect
from warhammer40k_core.engine.game_state import GameState
from warhammer40k_core.engine.phase import GameLifecycleError
from warhammer40k_core.engine.rules_units import rules_unit_view_by_id


def rules_unit_persisting_effects(
    state: GameState,
    unit_instance_id: str,
) -> tuple[tuple[str, PersistingEffect], ...]:
    """Return effects keyed by every current physical/rules-unit identity."""
    if type(state) is not GameState:
        raise GameLifecycleError("Rules-unit effect lookup requires GameState.")
    rules_unit = rules_unit_view_by_id(state=state, unit_instance_id=unit_instance_id)
    identity_ids = tuple(
        dict.fromkeys((rules_unit.unit_instance_id, *rules_unit.component_unit_instance_ids))
    )
    return tuple(
        (identity_id, effect)
        for identity_id in identity_ids
        for effect in state.persisting_effects_for_unit(identity_id)
    )
