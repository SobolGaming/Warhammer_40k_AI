from __future__ import annotations

from typing import TYPE_CHECKING

from warhammer40k_core.core.validation import IdentifierValidator
from warhammer40k_core.engine.objective_control import (
    ObjectiveControlContext,
    ObjectiveControlRecord,
    ObjectiveControlTiming,
    resolve_objective_control,
)
from warhammer40k_core.engine.phase import BattlePhase, GameLifecycleError, GameLifecycleStage
from warhammer40k_core.engine.runtime_modifiers import RuntimeModifierRegistry
from warhammer40k_core.engine.sticky_objective_control import apply_sticky_objective_control
from warhammer40k_core.engine.transports import TransportCargoState

if TYPE_CHECKING:
    from warhammer40k_core.engine.game_state import GameState

_validate_identifier = IdentifierValidator(GameLifecycleError)


def transport_cargo_state_for_embarked_unit(
    *,
    state: GameState,
    embarked_unit_instance_id: str,
) -> TransportCargoState | None:
    requested_unit_id = _validate_identifier(
        "embarked_unit_instance_id",
        embarked_unit_instance_id,
    )
    matches = tuple(
        cargo_state
        for cargo_state in state.transport_cargo_states
        if requested_unit_id in cargo_state.embarked_unit_instance_ids
    )
    if len(matches) > 1:
        raise GameLifecycleError(
            "Embarked unit cannot be present in multiple TransportCargoState records."
        )
    return None if not matches else matches[0]


def determine_current_end_objective_control(
    *,
    state: GameState,
    runtime_modifier_registry: RuntimeModifierRegistry | None,
) -> tuple[ObjectiveControlRecord, ...]:
    if state.stage is not GameLifecycleStage.BATTLE:
        raise GameLifecycleError("End-boundary objective control requires battle stage.")
    if state.battle_phase_index is None:
        raise GameLifecycleError("End-boundary objective control requires a battle phase.")
    completed_phase = state.battle_phase_sequence[state.battle_phase_index]
    records = [
        state.record_objective_control_boundary(
            completed_phase=completed_phase,
            timing=ObjectiveControlTiming.PHASE_END,
            runtime_modifier_registry=runtime_modifier_registry,
        )
    ]
    if state.battle_phase_index + 1 == len(state.battle_phase_sequence):
        records.append(
            state.record_objective_control_boundary(
                completed_phase=completed_phase,
                timing=ObjectiveControlTiming.TURN_END,
                runtime_modifier_registry=runtime_modifier_registry,
            )
        )
    return tuple(records)


def record_objective_control_boundary(
    *,
    state: GameState,
    completed_phase: BattlePhase,
    timing: ObjectiveControlTiming,
    runtime_modifier_registry: RuntimeModifierRegistry | None,
) -> ObjectiveControlRecord:
    if state.mission_setup is None:
        raise GameLifecycleError("Objective control updates require MissionSetup.")
    if state.battlefield_state is None:
        raise GameLifecycleError("Objective control updates require battlefield_state.")
    if state.active_player_id is None:
        raise GameLifecycleError("Objective control updates require an active player.")
    record = resolve_objective_control(
        ObjectiveControlContext.from_game_state(
            state,
            timing=timing,
            phase=completed_phase,
            ruleset_descriptor=state.ruleset_descriptor_for_runtime_policy(),
            runtime_modifier_registry=runtime_modifier_registry,
        )
    )
    for stored in state.objective_control_records:
        if stored.record_id == record.record_id:
            return stored
    retained_record = apply_sticky_objective_control(
        record=record,
        states=tuple(state.sticky_objective_control_states),
    )
    state.expire_sticky_objective_control_states(record)
    state.record_objective_control_record(retained_record)
    return retained_record
