from __future__ import annotations

from typing import TYPE_CHECKING

from warhammer40k_core.core.validation import IdentifierValidator
from warhammer40k_core.engine.phase import GameLifecycleError
from warhammer40k_core.engine.scoring import (
    SecondaryDestroyedModelState,
    SecondaryUnitDestructionState,
)

if TYPE_CHECKING:
    from warhammer40k_core.engine.game_state import GameState
    from warhammer40k_core.engine.unit_factory import UnitInstance

_validate_identifier = IdentifierValidator(GameLifecycleError)


def record_secondary_unit_destruction(
    state: GameState,
    *,
    destroying_player_id: str | None,
    destroyed_unit_instance_id: str,
    destroyed_model_instance_ids: tuple[str, ...],
    started_turn_objective_marker_ids: tuple[str, ...],
    source_id: str,
) -> SecondaryUnitDestructionState:
    if state.mission_setup is None:
        raise GameLifecycleError("Secondary unit destruction tracking requires MissionSetup.")
    if state.active_player_id is None:
        raise GameLifecycleError("Secondary unit destruction tracking requires an active player.")
    phase = state.current_battle_phase
    if phase is None:
        raise GameLifecycleError("Secondary unit destruction tracking requires a battle phase.")
    requested_destroyer = _optional_player_id(
        destroying_player_id,
        player_ids=state.player_ids,
        field_name="destroying_player_id",
    )
    requested_unit = _validate_identifier(
        "destroyed_unit_instance_id",
        destroyed_unit_instance_id,
    )
    destroyed_unit = _unit_by_id(state, requested_unit)
    destroyed_player_id = _owner_player_id(state, requested_unit)
    requested_model_ids = _sorted_identifiers(
        "destroyed_model_instance_ids",
        destroyed_model_instance_ids,
    )
    model_by_id = {model.model_instance_id: model for model in destroyed_unit.own_models}
    if any(model_id not in model_by_id for model_id in requested_model_ids):
        raise GameLifecycleError(
            "Secondary unit destruction references a model outside the destroyed unit."
        )
    objective_ids = _sorted_identifiers(
        "started_turn_objective_marker_ids",
        started_turn_objective_marker_ids,
    )
    known_objective_ids = {
        marker.objective_marker_id for marker in state.mission_setup.objective_markers
    }
    if any(objective_id not in known_objective_ids for objective_id in objective_ids):
        raise GameLifecycleError(
            "Secondary unit destruction references an unknown started-turn objective."
        )
    if any(
        stored.destroyed_unit_instance_id == requested_unit
        for stored in state.secondary_unit_destruction_states
    ):
        raise GameLifecycleError("Secondary unit destruction already exists for this unit.")
    recorded = SecondaryUnitDestructionState(
        destruction_id=(
            f"secondary-unit-destruction:{state.game_id}:round-{state.battle_round:02d}:"
            f"{state.active_player_id}:{requested_unit}"
        ),
        game_id=state.game_id,
        destroying_player_id=requested_destroyer,
        destroyed_player_id=destroyed_player_id,
        active_player_id=state.active_player_id,
        battle_round=state.battle_round,
        phase=phase.value,
        destroyed_unit_instance_id=requested_unit,
        destroyed_models=tuple(
            SecondaryDestroyedModelState(
                model_instance_id=model_id,
                starting_wounds=model_by_id[model_id].starting_wounds,
            )
            for model_id in requested_model_ids
        ),
        started_turn_objective_marker_ids=objective_ids,
        source_id=_validate_identifier("source_id", source_id),
    )
    state.secondary_unit_destruction_states.append(recorded)
    state.secondary_unit_destruction_states.sort(key=lambda stored: stored.destruction_id)
    return recorded


def _optional_player_id(
    value: object | None,
    *,
    player_ids: tuple[str, ...],
    field_name: str,
) -> str | None:
    if value is None:
        return None
    requested = _validate_identifier(field_name, value)
    if requested not in player_ids:
        raise GameLifecycleError(f"{field_name} is not in this game.")
    return requested


def _owner_player_id(state: GameState, unit_instance_id: str) -> str:
    for army in state.army_definitions:
        for unit in army.units:
            if unit.unit_instance_id == unit_instance_id:
                return army.player_id
    raise GameLifecycleError("Secondary unit destruction references an unknown unit.")


def _unit_by_id(state: GameState, unit_instance_id: str) -> UnitInstance:
    for army in state.army_definitions:
        for unit in army.units:
            if unit.unit_instance_id == unit_instance_id:
                return unit
    raise GameLifecycleError("Secondary unit destruction references an unknown unit.")


def _sorted_identifiers(field_name: str, values: object) -> tuple[str, ...]:
    if type(values) is not tuple:
        raise GameLifecycleError(f"{field_name} must be a tuple.")
    identifiers = tuple(_validate_identifier(f"{field_name} value", value) for value in values)
    if len(set(identifiers)) != len(identifiers):
        raise GameLifecycleError(f"{field_name} must not contain duplicates.")
    return tuple(sorted(identifiers))
