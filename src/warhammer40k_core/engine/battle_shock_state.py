from __future__ import annotations

from typing import TYPE_CHECKING

from warhammer40k_core.engine.battle_shock import (
    BattleShockedUnitState,
    BattleShockResult,
)
from warhammer40k_core.engine.phase import GameLifecycleError
from warhammer40k_core.engine.rules_units import (
    current_rules_unit_views_for_canonical_identity,
    rules_unit_identity_ids,
)

if TYPE_CHECKING:
    from warhammer40k_core.engine.game_state import GameState

BATTLE_SHOCK_STATE_ALREADY = "already_battle_shocked"
BATTLE_SHOCK_STATE_RECORDED = "recorded_battle_shocked"
BATTLE_SHOCK_STATE_NOT_REQUIRED = "not_required"


def record_battle_shock_result(*, state: GameState, result: BattleShockResult) -> None:
    state_update = apply_battle_shock_result_state(state=state, result=result)
    if state_update == BATTLE_SHOCK_STATE_ALREADY:
        raise GameLifecycleError("Battle-shocked unit is already marked.")


def apply_battle_shock_result_state(*, state: GameState, result: BattleShockResult) -> str:
    """Apply one result to its canonical current rules-unit identity."""
    if type(result) is not BattleShockResult:
        raise GameLifecycleError("GameState battle_shock_result must be a BattleShockResult.")
    if result.request.game_id != state.game_id:
        raise GameLifecycleError("BattleShockResult game_id drift.")
    if result.request.battle_round != state.battle_round:
        raise GameLifecycleError("BattleShockResult battle_round drift.")
    if result.request.player_id not in state.player_ids:
        raise GameLifecycleError("BattleShockResult player_id is not in this game.")
    current_rules_units = current_rules_unit_views_for_canonical_identity(
        state=state,
        unit_instance_id=result.request.unit_instance_id,
    )
    if any(
        rules_unit.owner_player_id != result.request.player_id for rules_unit in current_rules_units
    ):
        raise GameLifecycleError("BattleShockResult unit owner drift.")
    if result.passed:
        return BATTLE_SHOCK_STATE_NOT_REQUIRED
    surviving_rules_units = tuple(
        rules_unit
        for rules_unit in current_rules_units
        if any(model.is_alive for model in rules_unit.own_models)
    )
    if not surviving_rules_units:
        raise GameLifecycleError("BattleShockResult target has no surviving rules unit.")
    target_ids = tuple(rules_unit.unit_instance_id for rules_unit in surviving_rules_units)
    already_ids = set(target_ids).intersection(state.battle_shocked_unit_ids)
    missing_rules_units = tuple(
        rules_unit
        for rules_unit in surviving_rules_units
        if rules_unit.unit_instance_id not in already_ids
    )
    if not missing_rules_units:
        return BATTLE_SHOCK_STATE_ALREADY
    shocked_states = tuple(
        BattleShockedUnitState(
            player_id=result.request.player_id,
            unit_instance_id=rules_unit.unit_instance_id,
            model_instance_ids=tuple(model.model_instance_id for model in rules_unit.own_models),
            source_result_id=result.result_id,
            battle_round_started=result.request.battle_round,
        )
        for rules_unit in missing_rules_units
    )
    shocked_unit_ids = sorted(
        (*state.battle_shocked_unit_ids, *(value.unit_instance_id for value in shocked_states))
    )
    shocked_unit_states = sorted(
        (*state.battle_shocked_unit_states, *shocked_states),
        key=lambda value: value.unit_instance_id,
    )
    state.replace_battle_shock_state((shocked_unit_ids, shocked_unit_states))
    if already_ids:
        raise GameLifecycleError("Battle-shock state is partially duplicated.")
    return BATTLE_SHOCK_STATE_RECORDED


def clear_battle_shock_for_rules_unit(
    *,
    state: GameState,
    unit_instance_id: str,
) -> tuple[str, ...]:
    identity_ids = set(
        rules_unit_identity_ids(
            state=state,
            unit_instance_id=unit_instance_id,
        )
    )
    cleared_ids = tuple(
        sorted(unit_id for unit_id in state.battle_shocked_unit_ids if unit_id in identity_ids)
    )
    if not cleared_ids:
        raise GameLifecycleError("Rules unit is not Battle-shocked.")
    cleared_set = set(cleared_ids)
    state.replace_battle_shock_state(
        (
            [unit_id for unit_id in state.battle_shocked_unit_ids if unit_id not in cleared_set],
            [
                shocked_state
                for shocked_state in state.battle_shocked_unit_states
                if shocked_state.unit_instance_id not in cleared_set
            ],
        )
    )
    return cleared_ids
