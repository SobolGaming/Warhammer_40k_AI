from __future__ import annotations

from typing import TYPE_CHECKING

from warhammer40k_core.engine.command_phase_start_hooks import (
    CommandPhaseStartEffectContext,
    CommandPhaseStartHookRegistry,
)
from warhammer40k_core.engine.command_phase_start_sequencing import command_start_timing_context
from warhammer40k_core.engine.decision_controller import DecisionController
from warhammer40k_core.engine.decision_request import DecisionRequest
from warhammer40k_core.engine.phase import GameLifecycleError, LifecycleStatus
from warhammer40k_core.engine.timing_batch_runtime import timing_batches_for_context

if TYPE_CHECKING:
    from warhammer40k_core.engine.game_state import GameState


def require_selected_request(
    *, state: GameState, decisions: DecisionController, request: DecisionRequest
) -> None:
    active = state.active_player_id
    if active is None:
        raise GameLifecycleError("Command-start request requires active-player authority.")
    batches = timing_batches_for_context(
        decisions,
        command_start_timing_context(
            state, battle_round=state.battle_round, active_player_id=active
        ),
    )
    if not batches or batches[-1].selected_participant_id is None:
        raise GameLifecycleError("Command-start request lacks a selected timing participant.")
    batch = batches[-1]
    participant = next(
        item for item in batch.participants if item.participant_id == batch.selected_participant_id
    )
    if not isinstance(request.payload, dict) or (
        participant.player_id != request.actor_id
        or participant.source_rule_id != request.payload.get("source_rule_id")
    ):
        raise GameLifecycleError("Command-start request changed the selected source or owner.")


def invalid_selected_source_request(
    *,
    context: CommandPhaseStartEffectContext,
    registry: CommandPhaseStartHookRegistry,
    request: DecisionRequest,
) -> LifecycleStatus | None:
    from warhammer40k_core.engine.command_phase_start_sequencing import command_start_candidates
    from warhammer40k_core.engine.timing_request_candidates import (
        selected_timing_request_is_current,
    )

    if selected_timing_request_is_current(
        decisions=context.decisions,
        context=command_start_timing_context(
            context.state,
            battle_round=context.state.battle_round,
            active_player_id=context.active_player_id,
        ),
        request=request,
        candidates=command_start_candidates(context, registry),
    ):
        return None
    return LifecycleStatus.invalid(
        stage=context.state.stage,
        message="Command-start choice differs from its current source request.",
        payload={"invalid_reason": "command_start_source_request_drift"},
    )
