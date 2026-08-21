from __future__ import annotations

from typing import TYPE_CHECKING, cast

from warhammer40k_core.core.descriptor_hash import canonical_payload_sha256
from warhammer40k_core.core.validation import IdentifierValidator
from warhammer40k_core.engine.phase import GameLifecycleError
from warhammer40k_core.engine.scoring import (
    PrimaryUnitDestructionState,
    SecondaryDestroyedModelState,
    SecondaryUnitDestructionState,
)

if TYPE_CHECKING:
    from warhammer40k_core.engine.game_state import GameState
    from warhammer40k_core.engine.unit_factory import UnitInstance

_validate_identifier = IdentifierValidator(GameLifecycleError)


def secondary_unit_destruction_from_primary(
    *,
    state: GameState,
    primary_destruction: PrimaryUnitDestructionState,
) -> SecondaryUnitDestructionState:
    if type(primary_destruction) is not PrimaryUnitDestructionState:
        raise GameLifecycleError(
            "Secondary unit destruction requires a PrimaryUnitDestructionState."
        )
    if primary_destruction.game_id != state.game_id:
        raise GameLifecycleError("Secondary unit destruction Primary game_id drift.")
    model_by_id = {
        model.model_instance_id: model
        for army in state.army_definitions
        for unit in army.units
        for model in unit.own_models
    }
    destroyed_model_ids = _destroyed_model_ids_for_primary(
        state=state,
        primary_destruction=primary_destruction,
    )
    missing_model_ids = tuple(
        model_id for model_id in destroyed_model_ids if model_id not in model_by_id
    )
    if missing_model_ids:
        raise GameLifecycleError(
            "Secondary unit destruction Primary lineage references an unknown model."
        )
    source_primary_id = primary_destruction.destruction_id
    return SecondaryUnitDestructionState(
        destruction_id=secondary_unit_destruction_id(
            game_id=state.game_id,
            source_primary_destruction_id=source_primary_id,
        ),
        source_primary_destruction_id=source_primary_id,
        game_id=state.game_id,
        destroying_player_id=primary_destruction.destroying_player_id,
        destroyed_player_id=primary_destruction.destroyed_player_id,
        active_player_id=primary_destruction.active_player_id,
        battle_round=primary_destruction.battle_round,
        phase=primary_destruction.phase,
        destroyed_unit_instance_id=primary_destruction.destroyed_unit_instance_id,
        destroyed_models=tuple(
            SecondaryDestroyedModelState(
                model_instance_id=model_id,
                starting_wounds=model_by_id[model_id].starting_wounds,
            )
            for model_id in destroyed_model_ids
        ),
        started_turn_objective_marker_ids=(primary_destruction.started_turn_objective_marker_ids),
        source_id=primary_destruction.source_id,
    )


def secondary_unit_destruction_id(
    *,
    game_id: str,
    source_primary_destruction_id: str,
) -> str:
    requested_game_id = _validate_identifier("game_id", game_id)
    requested_primary_id = _validate_identifier(
        "source_primary_destruction_id",
        source_primary_destruction_id,
    )
    occurrence_hash = canonical_payload_sha256(
        {
            "game_id": requested_game_id,
            "source_primary_destruction_id": requested_primary_id,
        }
    )
    return f"secondary-unit-destruction:{occurrence_hash}"


def validate_secondary_unit_destruction_states(
    states: object,
    *,
    state: GameState,
) -> list[SecondaryUnitDestructionState]:
    if not isinstance(states, list):
        raise GameLifecycleError("GameState secondary unit destruction states must be a list.")
    primary_by_id = {
        destruction.destruction_id: destruction
        for destruction in state.primary_unit_destruction_states
    }
    if len(primary_by_id) != len(state.primary_unit_destruction_states):
        raise GameLifecycleError("Primary destruction occurrence identity is ambiguous.")
    validated: list[SecondaryUnitDestructionState] = []
    seen_ids: set[str] = set()
    seen_primary_ids: set[str] = set()
    for value in cast(list[object], states):
        if type(value) is not SecondaryUnitDestructionState:
            raise GameLifecycleError(
                "GameState secondary unit destruction states must contain state values."
            )
        destruction = value
        primary = primary_by_id.get(destruction.source_primary_destruction_id)
        if primary is None:
            raise GameLifecycleError(
                "Secondary unit destruction lacks its Primary destruction occurrence."
            )
        expected = secondary_unit_destruction_from_primary(
            state=state,
            primary_destruction=primary,
        )
        if destruction != expected:
            raise GameLifecycleError(
                "Secondary unit destruction drifted from its Primary destruction occurrence."
            )
        if destruction.destruction_id in seen_ids:
            raise GameLifecycleError("GameState secondary unit destruction states must be unique.")
        if destruction.source_primary_destruction_id in seen_primary_ids:
            raise GameLifecycleError(
                "GameState secondary unit destruction states must be unique per occurrence."
            )
        seen_ids.add(destruction.destruction_id)
        seen_primary_ids.add(destruction.source_primary_destruction_id)
        validated.append(destruction)
    missing_primary_ids = set(primary_by_id).difference(seen_primary_ids)
    if missing_primary_ids:
        raise GameLifecycleError(
            "GameState secondary unit destruction states require one projection "
            "per Primary destruction occurrence."
        )
    return sorted(validated, key=lambda destruction: destruction.destruction_id)


def _destroyed_model_ids_for_primary(
    *,
    state: GameState,
    primary_destruction: PrimaryUnitDestructionState,
) -> tuple[str, ...]:
    starting_model_ids = _starting_model_ids_for_primary(
        state=state,
        primary_destruction=primary_destruction,
    )
    source_departure_ids = primary_destruction.source_battlefield_departure_ids
    if not source_departure_ids:
        return starting_model_ids

    departures_by_id = {
        departure.departure_id: departure
        for departure in state.primary_battlefield_departure_states
    }
    missing_departure_ids = tuple(
        departure_id
        for departure_id in source_departure_ids
        if departure_id not in departures_by_id
    )
    if missing_departure_ids:
        raise GameLifecycleError(
            "Secondary unit destruction Primary lineage lacks departure evidence."
        )
    starting_model_id_set = set(starting_model_ids)
    destroyed_model_id_set = {
        model_id
        for departure_id in source_departure_ids
        for model_id in departures_by_id[departure_id].removed_model_instance_ids
    }
    if not destroyed_model_id_set <= starting_model_id_set:
        raise GameLifecycleError(
            "Secondary unit destruction departure evidence left its starting lineage."
        )
    destroyed_model_ids = tuple(sorted(destroyed_model_id_set))
    if not destroyed_model_ids:
        raise GameLifecycleError(
            "Secondary unit destruction Primary lineage lacks destroyed starting models."
        )
    return destroyed_model_ids


def _starting_model_ids_for_primary(
    *,
    state: GameState,
    primary_destruction: PrimaryUnitDestructionState,
) -> tuple[str, ...]:
    destroyed_unit_id = primary_destruction.destroyed_unit_instance_id
    historical = tuple(
        record
        for record in state.starting_attached_unit_records
        if record.attached_unit_instance_id == destroyed_unit_id
    )
    if len(historical) > 1:
        raise GameLifecycleError("Secondary destruction Attached Unit lineage is ambiguous.")
    if historical:
        return tuple(
            sorted(
                model_id
                for _component_id, model_ids in (
                    historical[0].starting_model_instance_ids_by_component
                )
                for model_id in model_ids
            )
        )
    return tuple(sorted(_unit_by_id(state, destroyed_unit_id).own_model_ids()))


def _unit_by_id(state: GameState, unit_instance_id: str) -> UnitInstance:
    requested_unit_id = _validate_identifier("unit_instance_id", unit_instance_id)
    for army in state.army_definitions:
        for unit in army.units:
            if unit.unit_instance_id == requested_unit_id:
                return unit
    raise GameLifecycleError("Secondary unit destruction references an unknown unit.")


__all__ = (
    "secondary_unit_destruction_from_primary",
    "secondary_unit_destruction_id",
    "validate_secondary_unit_destruction_states",
)
