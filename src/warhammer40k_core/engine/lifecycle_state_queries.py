from __future__ import annotations

from typing import TYPE_CHECKING

from warhammer40k_core.engine.phase import GameLifecycleError

if TYPE_CHECKING:
    from warhammer40k_core.engine.attack_sequence import AttackSequence
    from warhammer40k_core.engine.game_state import GameState


def active_attack_sequence_for_state(state: GameState) -> AttackSequence | None:
    out_of_phase_state = state.out_of_phase_shooting_state
    if out_of_phase_state is not None and out_of_phase_state.attack_sequence is not None:
        return out_of_phase_state.attack_sequence
    fight_state = state.fight_phase_state
    if fight_state is not None and fight_state.attack_sequence is not None:
        return fight_state.attack_sequence
    shooting_state = state.shooting_phase_state
    if shooting_state is not None and shooting_state.attack_sequence is not None:
        return shooting_state.attack_sequence
    return None


def embarked_unit_ids_for_player(*, state: GameState, player_id: str) -> set[str]:
    return {
        unit_id
        for cargo_state in state.transport_cargo_states
        if cargo_state.player_id == player_id
        for unit_id in cargo_state.embarked_unit_instance_ids
    }


def unarrived_reserve_unit_ids_for_player(*, state: GameState, player_id: str) -> set[str]:
    return {
        reserve_state.unit_instance_id
        for reserve_state in state.unarrived_reserve_states_for_player(player_id)
    }


def fully_removed_unit_ids_for_player(*, state: GameState, player_id: str) -> set[str]:
    if state.battlefield_state is None:
        raise GameLifecycleError("removed unit accounting requires battlefield_state.")
    removed_model_ids = set(state.battlefield_state.removed_model_ids)
    fully_removed_unit_ids: set[str] = set()
    for army_definition in state.army_definitions:
        if army_definition.player_id != player_id:
            continue
        for unit in army_definition.units:
            unit_model_ids = {model.model_instance_id for model in unit.own_models}
            if unit_model_ids and unit_model_ids <= removed_model_ids:
                fully_removed_unit_ids.add(unit.unit_instance_id)
    return fully_removed_unit_ids
