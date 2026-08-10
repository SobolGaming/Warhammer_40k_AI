from __future__ import annotations

from typing import TYPE_CHECKING, cast

from warhammer40k_core.core.descriptor_hash import canonical_payload_sha256
from warhammer40k_core.core.validation import IdentifierValidator
from warhammer40k_core.engine.phase import GameLifecycleError
from warhammer40k_core.engine.scoring import PrimaryUnitDestructionState

if TYPE_CHECKING:
    from warhammer40k_core.engine.game_state import GameState
    from warhammer40k_core.engine.turn_cleanup import EndTurnCleanupState


def record_primary_unit_destructions_for_destroyed_models(
    *,
    state: GameState,
    destroyed_model_instance_ids: tuple[str, ...],
    destroying_player_id: str | None,
    source_id: str,
) -> tuple[PrimaryUnitDestructionState, ...]:
    """Record each physical unit completed by an authoritative destroyed-model mutation."""
    from warhammer40k_core.engine.game_state import GameState

    if type(state) is not GameState:
        raise GameLifecycleError("Primary destruction tracking requires GameState.")
    if state.mission_setup is None:
        return ()
    battlefield = state.battlefield_state
    if battlefield is None:
        raise GameLifecycleError("Primary destruction tracking requires battlefield_state.")
    destroyed_model_ids = _validate_identifier_tuple(
        "destroyed_model_instance_ids",
        destroyed_model_instance_ids,
    )
    requested_source_id = _validate_identifier("source_id", source_id)
    known_models = {
        model.model_instance_id
        for army in state.army_definitions
        for unit in army.units
        for model in unit.own_models
    }
    if any(model_id not in known_models for model_id in destroyed_model_ids):
        raise GameLifecycleError("Primary destruction tracking references an unknown model.")
    removed_model_ids = set(battlefield.removed_model_ids)
    existing_occurrences = {
        (destruction.destroyed_unit_instance_id, destruction.source_id)
        for destruction in state.primary_unit_destruction_states
    }
    records: list[PrimaryUnitDestructionState] = []
    newly_destroyed_model_ids = set(destroyed_model_ids)
    for army in state.army_definitions:
        for unit in army.units:
            unit_model_ids = {model.model_instance_id for model in unit.own_models}
            if not unit_model_ids.intersection(newly_destroyed_model_ids):
                continue
            if not all(
                not model.is_alive or model.model_instance_id in removed_model_ids
                for model in unit.own_models
            ):
                continue
            occurrence_source_id = f"{requested_source_id}:{unit.unit_instance_id}"
            occurrence = (unit.unit_instance_id, occurrence_source_id)
            if occurrence in existing_occurrences:
                continue
            record = state.record_primary_unit_destruction(
                destroying_player_id=destroying_player_id,
                destroyed_unit_instance_id=unit.unit_instance_id,
                source_id=occurrence_source_id,
            )
            existing_occurrences.add(occurrence)
            records.append(record)
    return tuple(sorted(records, key=lambda record: record.destruction_id))


def record_primary_unit_destructions_for_end_turn_cleanup(
    *,
    state: GameState,
    cleanup: EndTurnCleanupState,
) -> tuple[PrimaryUnitDestructionState, ...]:
    from warhammer40k_core.engine.turn_cleanup import EndTurnCleanupState

    if type(cleanup) is not EndTurnCleanupState:
        raise GameLifecycleError("Primary destruction cleanup tracking requires cleanup state.")
    if not cleanup.removed_model_instance_ids:
        return ()
    return record_primary_unit_destructions_for_destroyed_models(
        state=state,
        destroyed_model_instance_ids=cleanup.removed_model_instance_ids,
        destroying_player_id=None,
        source_id=cleanup.cleanup_id,
    )


def primary_unit_destruction_id(
    *,
    game_id: str,
    source_id: str,
    destroyed_unit_instance_id: str,
) -> str:
    requested_game_id = _validate_identifier("game_id", game_id)
    requested_source_id = _validate_identifier("source_id", source_id)
    requested_unit_id = _validate_identifier(
        "destroyed_unit_instance_id",
        destroyed_unit_instance_id,
    )
    occurrence_hash = canonical_payload_sha256(
        {
            "game_id": requested_game_id,
            "source_id": requested_source_id,
            "destroyed_unit_instance_id": requested_unit_id,
        }
    )
    return f"primary-unit-destruction:{occurrence_hash}"


def validate_primary_unit_destruction_states(
    states: object,
    *,
    game_id: str,
    player_ids: tuple[str, ...],
    owner_by_unit_id: dict[str, str],
) -> list[PrimaryUnitDestructionState]:
    if not isinstance(states, list):
        raise GameLifecycleError("GameState primary unit destruction states must be a list.")
    validated: list[PrimaryUnitDestructionState] = []
    seen_ids: set[str] = set()
    seen_occurrences: set[tuple[str, str]] = set()
    for state in cast(list[object], states):
        if type(state) is not PrimaryUnitDestructionState:
            raise GameLifecycleError(
                "GameState primary unit destruction states must contain state values."
            )
        if state.game_id != game_id:
            raise GameLifecycleError("PrimaryUnitDestructionState game_id drift.")
        if (
            state.destroying_player_id not in {None, *player_ids}
            or state.destroyed_player_id not in player_ids
            or state.active_player_id not in player_ids
        ):
            raise GameLifecycleError("PrimaryUnitDestructionState player_id is not in this game.")
        destroyed_unit_id = state.destroyed_unit_instance_id
        if destroyed_unit_id not in owner_by_unit_id:
            raise GameLifecycleError(
                "PrimaryUnitDestructionState references an unknown destroyed unit."
            )
        if state.destroyed_player_id != owner_by_unit_id[destroyed_unit_id]:
            raise GameLifecycleError("PrimaryUnitDestructionState destroyed player drift.")
        expected_destruction_id = primary_unit_destruction_id(
            game_id=game_id,
            source_id=state.source_id,
            destroyed_unit_instance_id=destroyed_unit_id,
        )
        if state.destruction_id != expected_destruction_id:
            raise GameLifecycleError("PrimaryUnitDestructionState destruction_id drift.")
        if state.destruction_id in seen_ids:
            raise GameLifecycleError("GameState primary unit destruction states must be unique.")
        occurrence = (destroyed_unit_id, state.source_id)
        if occurrence in seen_occurrences:
            raise GameLifecycleError(
                "GameState primary unit destruction states must be unique per occurrence."
            )
        seen_ids.add(state.destruction_id)
        seen_occurrences.add(occurrence)
        validated.append(state)
    return sorted(validated, key=lambda state: state.destruction_id)


def _validate_identifier_tuple(field_name: str, value: object) -> tuple[str, ...]:
    if type(value) is not tuple:
        raise GameLifecycleError(f"{field_name} must be a tuple.")
    identifiers = tuple(
        _validate_identifier(field_name, item) for item in cast(tuple[object, ...], value)
    )
    if not identifiers:
        raise GameLifecycleError(f"{field_name} must not be empty.")
    if len(set(identifiers)) != len(identifiers):
        raise GameLifecycleError(f"{field_name} must not contain duplicates.")
    return tuple(sorted(identifiers))


_validate_identifier = IdentifierValidator(GameLifecycleError)


__all__ = (
    "primary_unit_destruction_id",
    "record_primary_unit_destructions_for_destroyed_models",
    "record_primary_unit_destructions_for_end_turn_cleanup",
    "validate_primary_unit_destruction_states",
)
