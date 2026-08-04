from __future__ import annotations

from dataclasses import replace
from typing import TYPE_CHECKING

from warhammer40k_core.engine.battle_shock import (
    BattleShockedUnitState,
    BattleShockResult,
)
from warhammer40k_core.engine.phase import GameLifecycleError
from warhammer40k_core.engine.rules_units import rules_unit_view_by_id

if TYPE_CHECKING:
    from warhammer40k_core.engine.game_state import GameState


def record_battle_shock_result(*, state: GameState, result: BattleShockResult) -> None:
    if type(result) is not BattleShockResult:
        raise GameLifecycleError("GameState battle_shock_result must be a BattleShockResult.")
    if result.request.game_id != state.game_id:
        raise GameLifecycleError("BattleShockResult game_id drift.")
    if result.request.battle_round != state.battle_round:
        raise GameLifecycleError("BattleShockResult battle_round drift.")
    if result.request.player_id not in state.player_ids:
        raise GameLifecycleError("BattleShockResult player_id is not in this game.")
    rules_unit = rules_unit_view_by_id(
        state=state,
        unit_instance_id=result.request.unit_instance_id,
    )
    if rules_unit.owner_player_id != result.request.player_id:
        raise GameLifecycleError("BattleShockResult unit owner drift.")
    if result.passed:
        return
    if result.request.unit_instance_id in state.battle_shocked_unit_ids:
        raise GameLifecycleError("Battle-shocked unit is already marked.")
    shocked_state = BattleShockedUnitState.from_rules_unit(
        result=result,
        rules_unit=rules_unit,
    )
    shocked_unit_ids = sorted((*state.battle_shocked_unit_ids, result.request.unit_instance_id))
    shocked_unit_states = sorted(
        (*state.battle_shocked_unit_states, shocked_state),
        key=lambda value: value.unit_instance_id,
    )
    state.replace_battle_shock_state((shocked_unit_ids, shocked_unit_states))


def transfer_battle_shock_after_attached_unit_split(
    *,
    state: GameState,
    attached_unit_instance_id: str,
    surviving_unit_instance_ids: tuple[str, ...],
) -> None:
    if attached_unit_instance_id not in state.battle_shocked_unit_ids:
        return
    matching_states = tuple(
        value
        for value in state.battle_shocked_unit_states
        if value.unit_instance_id == attached_unit_instance_id
    )
    if len(matching_states) != 1:
        raise GameLifecycleError("Attached-unit Battle-shock state is inconsistent.")
    if any(unit_id in state.battle_shocked_unit_ids for unit_id in surviving_unit_instance_ids):
        raise GameLifecycleError("Attached-unit Battle-shock survivor is already marked.")
    source_state = matching_states[0]
    shocked_unit_ids = sorted(
        unit_id for unit_id in state.battle_shocked_unit_ids if unit_id != attached_unit_instance_id
    )
    shocked_unit_ids = sorted((*shocked_unit_ids, *surviving_unit_instance_ids))
    shocked_unit_states = [
        value
        for value in state.battle_shocked_unit_states
        if value.unit_instance_id != attached_unit_instance_id
    ]
    shocked_unit_states = sorted(
        (
            *shocked_unit_states,
            *(
                replace(
                    source_state,
                    unit_instance_id=unit_id,
                    model_instance_ids=_physical_unit_model_ids(
                        state=state,
                        unit_instance_id=unit_id,
                    ),
                )
                for unit_id in surviving_unit_instance_ids
            ),
        ),
        key=lambda value: value.unit_instance_id,
    )
    state.replace_battle_shock_state((shocked_unit_ids, shocked_unit_states))


def _physical_unit_model_ids(*, state: GameState, unit_instance_id: str) -> tuple[str, ...]:
    matching_units = tuple(
        unit
        for army in state.army_definitions
        for unit in army.units
        if unit.unit_instance_id == unit_instance_id
    )
    if len(matching_units) != 1:
        raise GameLifecycleError("Attached-unit Battle-shock survivor unit is unknown.")
    return tuple(model.model_instance_id for model in matching_units[0].own_models)
