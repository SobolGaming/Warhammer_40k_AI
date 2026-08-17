from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

from warhammer40k_core.engine.objective_control import (
    ObjectiveControlContext,
    ObjectiveControlRecord,
    ObjectiveControlTiming,
    resolve_objective_control,
)
from warhammer40k_core.engine.phase import BattlePhase, GameLifecycleError
from warhammer40k_core.engine.runtime_modifiers import RuntimeModifierRegistry
from warhammer40k_core.engine.sticky_objective_control import (
    StickyObjectiveControlState,
    apply_sticky_objective_control,
    sticky_objective_control_state_is_expired,
)

if TYPE_CHECKING:
    from warhammer40k_core.engine.game_state import GameState


@dataclass(frozen=True, slots=True)
class CanonicalObjectiveControlProposal:
    """Pure Objective Control projection for one authenticated boundary."""

    resolved_record: ObjectiveControlRecord
    retained_record: ObjectiveControlRecord
    retained_sticky_witnesses: tuple[StickyObjectiveControlState, ...]
    post_boundary_sticky_states: tuple[StickyObjectiveControlState, ...]
    reused_stored_record: bool


def propose_canonical_objective_control_boundary(
    *,
    state: GameState,
    completed_phase: BattlePhase,
    timing: ObjectiveControlTiming,
    runtime_modifier_registry: RuntimeModifierRegistry | None,
) -> CanonicalObjectiveControlProposal:
    """Project the canonical sticky-aware Objective Control record without mutation."""
    from warhammer40k_core.engine.game_state import GameState

    if type(state) is not GameState:
        raise GameLifecycleError("Canonical Objective Control proposal requires GameState.")
    if type(completed_phase) is not BattlePhase:
        raise GameLifecycleError("Canonical Objective Control proposal requires a BattlePhase.")
    if type(timing) is not ObjectiveControlTiming:
        raise GameLifecycleError(
            "Canonical Objective Control proposal requires ObjectiveControlTiming."
        )
    if state.mission_setup is None:
        raise GameLifecycleError("Objective control updates require MissionSetup.")
    if state.battlefield_state is None:
        raise GameLifecycleError("Objective control updates require battlefield_state.")
    if state.active_player_id is None:
        raise GameLifecycleError("Objective control updates require an active player.")
    resolved_record = resolve_objective_control(
        ObjectiveControlContext.from_game_state(
            state,
            timing=timing,
            phase=completed_phase,
            ruleset_descriptor=state.ruleset_descriptor_for_runtime_policy(),
            runtime_modifier_registry=runtime_modifier_registry,
        )
    )
    for stored in state.objective_control_records:
        if stored.record_id == resolved_record.record_id:
            sticky_inventory = tuple(state.sticky_objective_control_states)
            return CanonicalObjectiveControlProposal(
                resolved_record=stored,
                retained_record=stored,
                retained_sticky_witnesses=sticky_inventory,
                post_boundary_sticky_states=sticky_inventory,
                reused_stored_record=True,
            )
    sticky_witnesses = tuple(state.sticky_objective_control_states)
    retained_record = apply_sticky_objective_control(
        record=resolved_record,
        states=sticky_witnesses,
    )
    post_boundary = tuple(
        sorted(
            (
                sticky
                for sticky in sticky_witnesses
                if not sticky_objective_control_state_is_expired(
                    state=sticky,
                    record=resolved_record,
                    player_ids=tuple(state.player_ids),
                )
            ),
            key=lambda sticky: sticky.state_id,
        )
    )
    return CanonicalObjectiveControlProposal(
        resolved_record=resolved_record,
        retained_record=retained_record,
        retained_sticky_witnesses=sticky_witnesses,
        post_boundary_sticky_states=post_boundary,
        reused_stored_record=False,
    )


def commit_canonical_objective_control_proposal(
    *,
    state: GameState,
    proposal: CanonicalObjectiveControlProposal,
    runtime_modifier_registry: RuntimeModifierRegistry | None,
) -> ObjectiveControlRecord:
    """Commit a previously proven canonical Objective Control proposal."""
    from warhammer40k_core.engine.game_state import GameState

    if type(state) is not GameState:
        raise GameLifecycleError("Canonical Objective Control commit requires GameState.")
    if type(proposal) is not CanonicalObjectiveControlProposal:
        raise GameLifecycleError("Canonical Objective Control commit requires a typed proposal.")
    if proposal.reused_stored_record:
        stored = next(
            record
            for record in state.objective_control_records
            if record.record_id == proposal.retained_record.record_id
        )
        if stored != proposal.retained_record:
            raise GameLifecycleError(
                "Canonical Objective Control reuse drifted from the stored record."
            )
        return stored
    state.record_objective_control_record(
        proposal.retained_record,
        runtime_modifier_registry=runtime_modifier_registry,
    )
    state.expire_sticky_objective_control_states(proposal.resolved_record)
    if tuple(state.sticky_objective_control_states) != proposal.post_boundary_sticky_states:
        raise GameLifecycleError(
            "Canonical Objective Control sticky inventory drifted after expiry."
        )
    return proposal.retained_record


__all__ = (
    "CanonicalObjectiveControlProposal",
    "commit_canonical_objective_control_proposal",
    "propose_canonical_objective_control_boundary",
)
