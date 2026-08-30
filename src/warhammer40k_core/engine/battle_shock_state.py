from __future__ import annotations

from dataclasses import replace
from typing import TYPE_CHECKING

from warhammer40k_core.engine.battle_shock import (
    BattleShockedUnitState,
    BattleShockResult,
)
from warhammer40k_core.engine.event_log import EventLog
from warhammer40k_core.engine.phase import GameLifecycleError
from warhammer40k_core.engine.rules_units import (
    current_rules_unit_views_for_canonical_identity,
    rules_unit_identity_ids,
)

if TYPE_CHECKING:
    from warhammer40k_core.engine.game_state import GameState

BATTLE_SHOCK_ATTACHED_SPLIT_TRANSFER_EVENT = (
    "battle_shock_state_transferred_after_attached_unit_split"
)
BATTLE_SHOCK_STATE_ALREADY = "already_battle_shocked"
BATTLE_SHOCK_STATE_RECORDED = "recorded_battle_shocked"
BATTLE_SHOCK_STATE_RECORDED_MISSING_DESCENDANTS = "recorded_missing_battle_shocked_descendants"
BATTLE_SHOCK_STATE_NOT_REQUIRED = "not_required"


def record_battle_shock_result(*, state: GameState, result: BattleShockResult) -> None:
    state_update = apply_battle_shock_result_state(state=state, result=result)
    if state_update == BATTLE_SHOCK_STATE_ALREADY:
        raise GameLifecycleError("Battle-shocked unit is already marked.")


def apply_battle_shock_result_state(*, state: GameState, result: BattleShockResult) -> str:
    """Apply one result across every current successor of its canonical target."""
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
        return BATTLE_SHOCK_STATE_RECORDED_MISSING_DESCENDANTS
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


def transfer_battle_shock_after_attached_unit_split(
    *,
    state: GameState,
    event_log: EventLog,
    attached_unit_instance_id: str,
    surviving_unit_instance_ids: tuple[str, ...],
) -> None:
    if type(event_log) is not EventLog:
        raise GameLifecycleError("Attached-unit Battle-shock transfer requires EventLog.")
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
    successor_states = tuple(
        replace(
            source_state,
            unit_instance_id=unit_id,
            model_instance_ids=_physical_unit_model_ids(
                state=state,
                unit_instance_id=unit_id,
            ),
        )
        for unit_id in surviving_unit_instance_ids
    )
    shocked_unit_states = sorted(
        (*shocked_unit_states, *successor_states),
        key=lambda value: value.unit_instance_id,
    )
    state.replace_battle_shock_state((shocked_unit_ids, shocked_unit_states))
    event_log.append(
        BATTLE_SHOCK_ATTACHED_SPLIT_TRANSFER_EVENT,
        {
            "game_id": state.game_id,
            "battle_round": state.battle_round,
            "active_player_id": state.active_player_id,
            "phase": (
                None if state.current_battle_phase is None else state.current_battle_phase.value
            ),
            "player_id": source_state.player_id,
            "attached_unit_instance_id": attached_unit_instance_id,
            "surviving_unit_instance_ids": list(surviving_unit_instance_ids),
            "source_battle_shocked_unit_state": source_state.to_payload(),
            "successor_battle_shocked_unit_states": [
                successor.to_payload() for successor in successor_states
            ],
        },
    )


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
