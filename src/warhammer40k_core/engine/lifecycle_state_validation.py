from __future__ import annotations

from warhammer40k_core.engine.game_state import GameState
from warhammer40k_core.engine.phase import GameLifecycleError, GameLifecycleStage


def validate_disembarked_unit_state_consistency(*, state: GameState) -> None:
    if type(state) is not GameState:
        raise GameLifecycleError("Disembarked unit state validation requires GameState.")
    if not state.disembarked_unit_states:
        return
    if state.stage is not GameLifecycleStage.BATTLE:
        raise GameLifecycleError("disembarked_unit_states require battle stage.")
    unit_owner_by_id = {
        unit.unit_instance_id: army.player_id
        for army in state.army_definitions
        for unit in army.units
    }
    for disembarked_state in state.disembarked_unit_states:
        owner = unit_owner_by_id.get(disembarked_state.unit_instance_id)
        if owner is None:
            raise GameLifecycleError("disembarked_unit_states unit is unknown.")
        if owner != disembarked_state.player_id:
            raise GameLifecycleError("disembarked_unit_states player drift.")
        transport_owner = unit_owner_by_id.get(disembarked_state.transport_unit_instance_id)
        if transport_owner is None:
            raise GameLifecycleError("disembarked_unit_states transport unit is unknown.")
        if transport_owner != disembarked_state.player_id:
            raise GameLifecycleError("disembarked_unit_states transport owner drift.")
