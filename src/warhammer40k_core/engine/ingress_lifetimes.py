"""Core ingress history and next-Charge movement lifetime, independent of actor."""

from __future__ import annotations

from typing import TYPE_CHECKING

from warhammer40k_core.engine.phase import BattlePhase, GameLifecycleError
from warhammer40k_core.engine.rules_units import rules_unit_view_by_id

if TYPE_CHECKING:
    from warhammer40k_core.engine.battlefield_state import BattlefieldRuntimeState
    from warhammer40k_core.engine.game_state import GameState
    from warhammer40k_core.engine.phase_movement_history import PhaseMovementRecord

LOCK_REASON = "ingress_movement_locked_until_next_charge"


def ingress_lock_applies(
    state: GameState,
    arrival: PhaseMovementRecord,
    *,
    battle_round: int,
    turn_player_id: str,
    phase: BattlePhase,
) -> bool:
    if not arrival.is_ingress:
        return False
    phases = state.battle_phase_sequence
    charge_index = phases.index(BattlePhase.CHARGE)
    turn_count = len(state.turn_order)
    arrival_turn = (arrival.battle_round - 1) * turn_count + state.turn_order.index(
        arrival.turn_player_id
    )
    current_turn = (battle_round - 1) * turn_count + state.turn_order.index(turn_player_id)
    next_charge_turn = arrival_turn + int(phases.index(arrival.phase) >= charge_index)
    current = (current_turn, phases.index(phase))
    return (
        (arrival_turn, phases.index(arrival.phase))
        <= current
        < (
            next_charge_turn,
            charge_index,
        )
    )


def locked_ingress_records(state: GameState) -> tuple[PhaseMovementRecord, ...]:
    if state.active_player_id is None or state.current_battle_phase is None:
        return ()
    return tuple(
        row
        for row in state.phase_movement_history
        if ingress_lock_applies(
            state,
            row,
            battle_round=state.battle_round,
            turn_player_id=state.active_player_id,
            phase=state.current_battle_phase,
        )
    )


def ingress_movement_locked(state: GameState, unit_instance_id: str) -> bool:
    rows = locked_ingress_records(state)
    if not rows:
        return False
    view = rules_unit_view_by_id(state=state, unit_instance_id=unit_instance_id)
    model_ids = {model.model_instance_id for model in view.alive_models()}
    return any(
        row.unit_instance_id == view.unit_instance_id
        or model_ids.intersection(row.model_instance_ids)
        for row in rows
    )


def validate_ingress_movement_mutation(
    *, state: GameState, updated: BattlefieldRuntimeState
) -> None:
    locked = {mid for row in locked_ingress_records(state) for mid in row.model_instance_ids}
    from warhammer40k_core.engine.rules_units import placed_alive_rules_unit_views

    aircraft_models = {
        model.model_instance_id
        for unit in (
            placed_alive_rules_unit_views(state=state)
            if state.battlefield_state is not None
            else ()
        )
        if "AIRCRAFT" in unit.keywords
        for model in unit.alive_models()
    }
    locked.update(aircraft_models)
    if not locked:
        return
    current = state.battlefield_state
    if current is None:
        raise GameLifecycleError("Ingress lock requires battlefield authority.")
    before = {
        model.model_instance_id: model.pose
        for army in current.placed_armies
        for unit in army.unit_placements
        for model in unit.model_placements
        if model.model_instance_id in locked
    }
    for army in updated.placed_armies:
        for unit in army.unit_placements:
            for model in unit.model_placements:
                # Removal and subsequent Ingress remain legal. Only previously
                # present models can be making another kind of battlefield move.
                if (
                    model.model_instance_id in before
                    and before[model.model_instance_id] != model.pose
                ):
                    from warhammer40k_core.engine.aircraft_rules import AIRCRAFT_INGRESS_ONLY

                    raise GameLifecycleError(
                        AIRCRAFT_INGRESS_ONLY
                        if model.model_instance_id in aircraft_models
                        else LOCK_REASON
                    )


def validate_ingress_movement_history(
    state: GameState, prior: list[PhaseMovementRecord], current: PhaseMovementRecord
) -> None:
    if current.is_ingress:
        return
    if (
        "AIRCRAFT"
        in rules_unit_view_by_id(state=state, unit_instance_id=current.unit_instance_id).keywords
    ):
        raise GameLifecycleError("AIRCRAFT movement history contains a non-ingress move.")
    models = set(current.model_instance_ids)
    if any(
        ingress_lock_applies(
            state,
            row,
            battle_round=current.battle_round,
            turn_player_id=current.turn_player_id,
            phase=current.phase,
        )
        and (
            row.unit_instance_id == current.unit_instance_id
            or models.intersection(row.model_instance_ids)
        )
        for row in prior
    ):
        raise GameLifecycleError("Ingress movement history violates the next-Charge lock.")
