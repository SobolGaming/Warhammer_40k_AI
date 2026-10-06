"""Per-model mission facts projected from shared physical destruction history."""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, Self, TypedDict

from warhammer40k_core.engine.battlefield_state import BattlefieldRemovalKind
from warhammer40k_core.engine.phase import GameLifecycleError
from warhammer40k_core.engine.primary_battlefield_departure import (
    PrimaryBattlefieldDepartureState,
    PrimaryBattlefieldDepartureStatePayload,
)
from warhammer40k_core.engine.scoring import (
    SecondaryDestroyedModelState,
    SecondaryDestroyedModelStatePayload,
)

if TYPE_CHECKING:
    from warhammer40k_core.engine.game_state import GameState
    from warhammer40k_core.engine.objective_control import ObjectiveControlRecord


class SecondaryModelDestructionStatePayload(TypedDict):
    departure: PrimaryBattlefieldDepartureStatePayload
    destroyed_models: list[SecondaryDestroyedModelStatePayload]


@dataclass(frozen=True, slots=True)
class SecondaryModelDestructionState:
    departure: PrimaryBattlefieldDepartureState
    destroyed_models: tuple[SecondaryDestroyedModelState, ...]

    def __post_init__(self) -> None:
        if type(self.departure) is not PrimaryBattlefieldDepartureState:
            raise GameLifecycleError("Secondary model destruction requires a typed departure.")
        if self.departure.removal_kind is not BattlefieldRemovalKind.DESTROYED:
            raise GameLifecycleError("Secondary model destruction requires destroyed models.")
        if type(self.destroyed_models) is not tuple or any(
            type(model) is not SecondaryDestroyedModelState for model in self.destroyed_models
        ):
            raise GameLifecycleError("Secondary model destruction requires typed models.")
        if tuple(model.model_instance_id for model in self.destroyed_models) != (
            self.departure.removed_model_instance_ids
        ):
            raise GameLifecycleError("Secondary model destruction physical inventory drifted.")

    def to_payload(self) -> SecondaryModelDestructionStatePayload:
        return {
            "departure": self.departure.to_payload(),
            "destroyed_models": [model.to_payload() for model in self.destroyed_models],
        }

    @classmethod
    def from_payload(cls, payload: SecondaryModelDestructionStatePayload) -> Self:
        return cls(
            departure=PrimaryBattlefieldDepartureState.from_payload(payload["departure"]),
            destroyed_models=tuple(
                SecondaryDestroyedModelState.from_payload(model)
                for model in payload["destroyed_models"]
            ),
        )


def secondary_model_destructions_for_boundary(
    *, state: GameState, record: ObjectiveControlRecord
) -> tuple[SecondaryModelDestructionState, ...]:
    """Preserve occurrence turns and physical ownership without completing a unit."""
    models = {
        model.model_instance_id: model
        for army in state.army_definitions
        for unit in army.units
        for model in unit.own_models
    }
    record_key = _context_key(state, record.battle_round, record.active_player_id, record.phase)
    result: list[SecondaryModelDestructionState] = []
    for departure in state.primary_battlefield_departure_states:
        if departure.removal_kind is not BattlefieldRemovalKind.DESTROYED:
            continue
        if (
            _context_key(state, departure.battle_round, departure.active_player_id, departure.phase)
            > record_key
        ):
            continue
        if any(model_id not in models for model_id in departure.removed_model_instance_ids):
            raise GameLifecycleError("Secondary model destruction references an unknown model.")
        result.append(
            SecondaryModelDestructionState(
                departure=departure,
                destroyed_models=tuple(
                    SecondaryDestroyedModelState(
                        model_instance_id=model_id, starting_wounds=models[model_id].initial_wounds
                    )
                    for model_id in departure.removed_model_instance_ids
                ),
            )
        )
    return tuple(sorted(result, key=lambda row: row.departure.departure_id))


def validate_secondary_model_destruction_boundary_history(
    *,
    state: GameState,
    record: ObjectiveControlRecord,
    history: tuple[SecondaryModelDestructionState, ...],
) -> None:
    expected = secondary_model_destructions_for_boundary(state=state, record=record)
    by_id = {row.departure.departure_id: row for row in expected}
    if len({row.departure.departure_id for row in history}) != len(history):
        raise GameLifecycleError("Secondary model destruction history duplicates an occurrence.")
    if any(by_id.get(row.departure.departure_id) != row for row in history):
        raise GameLifecycleError("Secondary model destruction history drifted from shared history.")
    record_key = _context_key(state, record.battle_round, record.active_player_id, record.phase)
    required = {
        row.departure.departure_id
        for row in expected
        if _context_key(
            state, row.departure.battle_round, row.departure.active_player_id, row.departure.phase
        )
        < record_key
    }
    if not required <= {row.departure.departure_id for row in history}:
        raise GameLifecycleError("Secondary model destruction history lacks earlier occurrences.")
    # Same-phase mutations can follow an already committed score. The frozen
    # membership remains a prefix of authentic history, never future state.


def _context_key(
    state: GameState, battle_round: int, player_id: str, phase: str
) -> tuple[int, int, int]:
    phases = tuple(value.value for value in state.battle_phase_sequence)
    if player_id not in state.turn_order or phase not in phases:
        raise GameLifecycleError("Secondary model destruction history has unknown turn context.")
    return battle_round, state.turn_order.index(player_id), phases.index(phase)
