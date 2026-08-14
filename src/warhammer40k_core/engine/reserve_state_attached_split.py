from __future__ import annotations

from dataclasses import replace
from typing import TYPE_CHECKING, cast

from warhammer40k_core.core.validation import IdentifierValidator
from warhammer40k_core.engine.event_log import EventLog
from warhammer40k_core.engine.phase import GameLifecycleError
from warhammer40k_core.engine.reserves import ReserveState, ReserveStatus

if TYPE_CHECKING:
    from warhammer40k_core.engine.game_state import GameState

RESERVE_STATE_ATTACHED_SPLIT_EVENT = "reserve_state_transferred_after_attached_unit_split"


def arrived_reserve_state_split_successors(
    *,
    source_state: ReserveState,
    component_unit_instance_ids: tuple[str, ...],
) -> tuple[ReserveState, ...]:
    """Derive one deterministic ARRIVED row for every former physical component."""
    if type(source_state) is not ReserveState:
        raise GameLifecycleError("Attached split reserve source must be a ReserveState.")
    component_ids = _validate_component_ids(component_unit_instance_ids)
    if source_state.status is not ReserveStatus.ARRIVED:
        raise GameLifecycleError(
            "Only an ARRIVED ReserveState can transfer across an attached-unit split."
        )
    if source_state.unit_instance_id in component_ids:
        raise GameLifecycleError(
            "Attached split reserve successors cannot retain the historical attached identity."
        )
    aggregate_component_id = component_ids[0]
    return tuple(
        replace(
            source_state,
            unit_instance_id=component_id,
            points_contribution=(
                source_state.points_contribution if component_id == aggregate_component_id else 0
            ),
            embarked_unit_instance_ids=(
                source_state.embarked_unit_instance_ids
                if component_id == aggregate_component_id
                else ()
            ),
        )
        for component_id in component_ids
    )


def transfer_arrived_reserve_state_after_attached_unit_split(
    *,
    state: GameState,
    event_log: EventLog,
    attached_unit_instance_id: str,
    component_unit_instance_ids: tuple[str, ...],
) -> tuple[ReserveState, ...]:
    """Replace one historical attached ReserveState with every former component."""
    from warhammer40k_core.engine.game_state import GameState

    if type(state) is not GameState:
        raise GameLifecycleError("Attached split reserve transfer requires GameState.")
    if type(event_log) is not EventLog:
        raise GameLifecycleError("Attached split reserve transfer requires EventLog.")
    attached_id = _validate_identifier(
        "attached_unit_instance_id",
        attached_unit_instance_id,
    )
    component_ids = _validate_component_ids(component_unit_instance_ids)
    matches = tuple(
        reserve_state
        for reserve_state in state.reserve_states
        if reserve_state.unit_instance_id == attached_id
    )
    if len(matches) > 1:
        raise GameLifecycleError("Attached split ReserveState source is duplicated.")
    conflicting_ids = {
        reserve_state.unit_instance_id
        for reserve_state in state.reserve_states
        if reserve_state.unit_instance_id in component_ids
    }
    if conflicting_ids:
        raise GameLifecycleError("Attached split ReserveState successor already exists.")
    if not matches:
        return ()
    source_state = matches[0]
    if source_state.player_id not in state.player_ids:
        raise GameLifecycleError("Attached split ReserveState player is not in this game.")
    owner_by_unit_id = {
        unit.unit_instance_id: army.player_id
        for army in state.army_definitions
        for unit in army.units
    }
    if any(owner_by_unit_id.get(unit_id) != source_state.player_id for unit_id in component_ids):
        raise GameLifecycleError("Attached split ReserveState successor owner drift.")
    successors = arrived_reserve_state_split_successors(
        source_state=source_state,
        component_unit_instance_ids=component_ids,
    )
    state.replace_arrived_reserve_state_after_attached_unit_split(
        source_reserve_state=source_state,
        successor_reserve_states=successors,
    )
    event_log.append(
        RESERVE_STATE_ATTACHED_SPLIT_EVENT,
        {
            "game_id": state.game_id,
            "battle_round": state.battle_round,
            "active_player_id": state.active_player_id,
            "phase": (
                None if state.current_battle_phase is None else state.current_battle_phase.value
            ),
            "player_id": source_state.player_id,
            "historical_unit_instance_id": attached_id,
            "source_reserve_state": source_state.to_payload(),
            "successor_reserve_states": [successor.to_payload() for successor in successors],
        },
    )
    return successors


def _validate_component_ids(values: object) -> tuple[str, ...]:
    if type(values) is not tuple or not values:
        raise GameLifecycleError("Attached split reserve components must be a non-empty tuple.")
    tuple_values = cast(tuple[object, ...], values)
    validated = tuple(
        _validate_identifier("component_unit_instance_id", value) for value in tuple_values
    )
    if validated != tuple(sorted(validated)) or len(set(validated)) != len(validated):
        raise GameLifecycleError("Attached split reserve components must be sorted and unique.")
    return validated


_validate_identifier = IdentifierValidator(GameLifecycleError)


__all__ = (
    "RESERVE_STATE_ATTACHED_SPLIT_EVENT",
    "arrived_reserve_state_split_successors",
    "transfer_arrived_reserve_state_after_attached_unit_split",
)
