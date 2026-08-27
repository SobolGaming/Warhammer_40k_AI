from __future__ import annotations

from typing import TYPE_CHECKING

from warhammer40k_core.engine.event_log import EventLog
from warhammer40k_core.engine.phase import GameLifecycleError
from warhammer40k_core.engine.starting_attached_units import StartingAttachedUnitRecord

if TYPE_CHECKING:
    from warhammer40k_core.engine.game_state import GameState


ATTACHED_RULES_UNIT_SPLIT_EVENT = "attached_rules_unit_split_reconciled"


def alive_attached_component_unit_ids(
    *,
    state: GameState,
    starting_record: StartingAttachedUnitRecord,
) -> tuple[str, ...]:
    """Return the exact physical component units with at least one living model."""
    from warhammer40k_core.engine.game_state import GameState

    if type(state) is not GameState:
        raise GameLifecycleError("Attached rules-unit survivor query requires GameState.")
    if type(starting_record) is not StartingAttachedUnitRecord:
        raise GameLifecycleError("Attached rules-unit survivor query requires a starting record.")
    units_by_id = {
        unit.unit_instance_id: (army.player_id, unit)
        for army in state.army_definitions
        for unit in army.units
    }
    survivors: list[str] = []
    for unit_id in starting_record.component_unit_instance_ids:
        row = units_by_id.get(unit_id)
        if row is None or row[0] != starting_record.player_id:
            raise GameLifecycleError("Attached rules-unit component identity drifted.")
        if any(model.is_alive for model in row[1].own_models):
            survivors.append(unit_id)
    return tuple(survivors)


def record_attached_rules_unit_split(
    *,
    state: GameState,
    event_log: EventLog,
    starting_record: StartingAttachedUnitRecord,
    surviving_unit_instance_ids: tuple[str, ...],
) -> None:
    """Record the engine-owned identity transition shared by split state owners."""
    from warhammer40k_core.engine.game_state import GameState

    if type(state) is not GameState:
        raise GameLifecycleError("Attached rules-unit split requires GameState.")
    if type(event_log) is not EventLog:
        raise GameLifecycleError("Attached rules-unit split requires EventLog.")
    if type(starting_record) is not StartingAttachedUnitRecord:
        raise GameLifecycleError("Attached rules-unit split requires its starting record.")
    survivor_ids = tuple(sorted(set(surviving_unit_instance_ids)))
    if (
        survivor_ids != surviving_unit_instance_ids
        or not survivor_ids
        or survivor_ids
        != alive_attached_component_unit_ids(state=state, starting_record=starting_record)
    ):
        raise GameLifecycleError("Attached rules-unit split survivor identities drifted.")
    event_log.append(
        ATTACHED_RULES_UNIT_SPLIT_EVENT,
        {
            "game_id": state.game_id,
            "battle_round": state.battle_round,
            "active_player_id": state.active_player_id,
            "phase": (
                None if state.current_battle_phase is None else state.current_battle_phase.value
            ),
            "player_id": starting_record.player_id,
            "attached_unit_instance_id": starting_record.attached_unit_instance_id,
            "component_unit_instance_ids": list(starting_record.component_unit_instance_ids),
            "surviving_unit_instance_ids": list(survivor_ids),
            "starting_attached_unit_record": starting_record.to_payload(),
        },
    )


__all__ = (
    "ATTACHED_RULES_UNIT_SPLIT_EVENT",
    "alive_attached_component_unit_ids",
    "record_attached_rules_unit_split",
)
