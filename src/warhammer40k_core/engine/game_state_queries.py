from __future__ import annotations

from typing import TYPE_CHECKING

from warhammer40k_core.core.validation import IdentifierValidator
from warhammer40k_core.engine.objective_control import (
    ObjectiveControlRecord,
    ObjectiveControlTiming,
)
from warhammer40k_core.engine.objective_control_boundary_proposal import (
    commit_canonical_objective_control_proposal,
    propose_canonical_objective_control_boundary,
)
from warhammer40k_core.engine.phase import BattlePhase, GameLifecycleError, GameLifecycleStage
from warhammer40k_core.engine.runtime_modifiers import RuntimeModifierRegistry
from warhammer40k_core.engine.transports import TransportCargoState

if TYPE_CHECKING:
    from warhammer40k_core.engine.game_state import GameState

_validate_identifier = IdentifierValidator(GameLifecycleError)


def effective_opposing_player_ids(state: GameState) -> tuple[str, ...]:
    effective_active_player_id = state.effective_active_player_id()
    if effective_active_player_id is None:
        return ()
    return tuple(
        player_id for player_id in state.player_ids if player_id != effective_active_player_id
    )


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


def determine_current_phase_end_objective_control(
    *,
    state: GameState,
    runtime_modifier_registry: RuntimeModifierRegistry | None,
) -> ObjectiveControlRecord:
    if state.stage is not GameLifecycleStage.BATTLE:
        raise GameLifecycleError("End-boundary objective control requires battle stage.")
    if state.battle_phase_index is None:
        raise GameLifecycleError("End-boundary objective control requires a battle phase.")
    completed_phase = state.battle_phase_sequence[state.battle_phase_index]
    return state.record_objective_control_boundary(
        completed_phase=completed_phase,
        timing=ObjectiveControlTiming.PHASE_END,
        runtime_modifier_registry=runtime_modifier_registry,
    )


def record_objective_control_boundary(
    *,
    state: GameState,
    completed_phase: BattlePhase,
    timing: ObjectiveControlTiming,
    runtime_modifier_registry: RuntimeModifierRegistry | None,
) -> ObjectiveControlRecord:
    proposal = propose_canonical_objective_control_boundary(
        state=state,
        completed_phase=completed_phase,
        timing=timing,
        runtime_modifier_registry=runtime_modifier_registry,
    )
    return commit_canonical_objective_control_proposal(
        state=state,
        proposal=proposal,
        runtime_modifier_registry=runtime_modifier_registry,
    )
