from __future__ import annotations

from collections.abc import Callable
from typing import TYPE_CHECKING, cast

from warhammer40k_core.engine.active_player import effective_active_player_id
from warhammer40k_core.engine.command_battle_shock_history_helpers import (
    sequencing_request_conflict_id,
    validate_pending_order_restore_authority,
)
from warhammer40k_core.engine.command_points import CommandPhaseStep
from warhammer40k_core.engine.decision_controller import DecisionController
from warhammer40k_core.engine.decision_request import DecisionRequest
from warhammer40k_core.engine.phase import GameLifecycleError
from warhammer40k_core.engine.timing_batch_decisions import request_for_timing_batch
from warhammer40k_core.engine.timing_batch_runtime import (
    TIMING_BATCH_EVENT_TYPE,
    timing_batches_for_context,
)
from warhammer40k_core.engine.timing_batch_state import TimingBatch, TimingBatchPayload

if TYPE_CHECKING:
    from warhammer40k_core.engine.faction_content.bundle import RuntimeContentBundle
    from warhammer40k_core.engine.game_state import GameConfig, GameState
    from warhammer40k_core.engine.phases.shooting_handler import ShootingPhaseHandler
    from warhammer40k_core.engine.reaction_queue import ReactionQueue


def validate_loaded_sequencing_authority(
    *,
    state: GameState,
    decisions: DecisionController,
    request: DecisionRequest,
    config: GameConfig,
    reaction_queue: ReactionQueue,
    runtime_bundle_provider: Callable[[], RuntimeContentBundle],
    shooting_handler_provider: Callable[[], ShootingPhaseHandler],
) -> None:
    batch = validate_sequencing_submission_authority(
        state=state, decisions=decisions, request=request
    )
    if batch is not None:
        validate_loaded_timing_batch_authority(
            state=state,
            decisions=decisions,
            batch=batch,
            config=config,
            reaction_queue=reaction_queue,
            runtime_bundle_provider=runtime_bundle_provider,
            shooting_handler_provider=shooting_handler_provider,
        )


def validate_loaded_timing_batch_authority(
    *,
    state: GameState,
    decisions: DecisionController,
    batch: TimingBatch,
    config: GameConfig,
    reaction_queue: ReactionQueue,
    runtime_bundle_provider: Callable[[], RuntimeContentBundle],
    shooting_handler_provider: Callable[[], ShootingPhaseHandler],
) -> None:
    from warhammer40k_core.engine.boundary_rule_authority import (
        BOUNDARY_ORDER_TRIGGERS,
        validate_boundary_order_candidates,
    )
    from warhammer40k_core.engine.movement_start_sequencing import (
        validate_move_start_order_candidates,
    )
    from warhammer40k_core.engine.rule_trigger_runtime import validate_trigger_order_candidates
    from warhammer40k_core.engine.timing_windows import TimingTriggerKind

    if batch.context.timing_window.descriptor.trigger_kind in BOUNDARY_ORDER_TRIGGERS:
        validate_boundary_order_candidates(
            state=state,
            decisions=decisions,
            batch=batch,
            bundle=runtime_bundle_provider(),
            config=config,
            reaction_queue=reaction_queue,
        )
    elif (
        batch.context.timing_window.descriptor.trigger_kind
        is TimingTriggerKind.BEFORE_UNIT_STARTS_MOVE
    ):
        validate_move_start_order_candidates(
            state=state,
            decisions=decisions,
            batch=batch,
            bundle=runtime_bundle_provider(),
            stratagem_index=shooting_handler_provider().stratagem_index,
        )
    else:
        validate_trigger_order_candidates(
            state=state,
            decisions=decisions,
            batch=batch,
            runtime_bundle_provider=runtime_bundle_provider,
            shooting_handler_provider=shooting_handler_provider,
        )


def validate_sequencing_submission_authority(
    *, state: GameState, decisions: DecisionController, request: DecisionRequest
) -> TimingBatch | None:
    """Rebuild the pending order from its engine owner before accepting a result."""
    if decisions.queue.pending_requests != (request,):
        raise GameLifecycleError("Sequencing submission requires the unique pending request.")
    command = state.command_step_state
    if command is not None and sequencing_request_conflict_id(request) == (
        f"timing-batch:command-battle-shock-order:{state.game_id}:"
        f"round-{command.battle_round:02d}:{command.active_player_id}:generation-0:tier-0"
    ):
        if (
            command.current_step is not CommandPhaseStep.BATTLE_SHOCK
            or command.battle_shock_step_resolved
        ):
            raise GameLifecycleError("Sequencing request escaped the Command Battle-shock step.")
        validate_pending_order_restore_authority(state=state, pending_decision_requests=(request,))
    latest: dict[str, TimingBatch] = {}
    for event in decisions.event_log.records:
        if event.event_type != TIMING_BATCH_EVENT_TYPE:
            continue
        if not isinstance(event.payload, dict) or not isinstance(event.payload.get("batch"), dict):
            raise GameLifecycleError("Sequencing batch authority requires a typed batch event.")
        batch = TimingBatch.from_payload(cast(TimingBatchPayload, event.payload["batch"]))
        latest[batch.context.conflict_id] = batch
    matching = tuple(
        batch
        for batch in latest.values()
        if not batch.current_batch_complete
        and batch.selected_participant_id is None
        and len(batch.eligible_participants()) > 1
        and request_for_timing_batch(batch, request_id=request.request_id) == request
    )
    if len(matching) != 1:
        raise GameLifecycleError("Sequencing request differs from its current timing batch.")
    batch = matching[0]
    history = timing_batches_for_context(decisions, batch.context)
    if not history or history[-1] != batch:
        raise GameLifecycleError("Sequencing request timing history drifted.")
    window = batch.context.timing_window
    if (
        window.game_id != state.game_id
        or window.battle_round != state.battle_round
        or (window.phase is not None and window.phase is not state.current_battle_phase)
        or batch.context.active_player_id
        != effective_active_player_id(state, trigger_kind=window.descriptor.trigger_kind)
    ):
        raise GameLifecycleError("Sequencing request trigger or active-player authority drifted.")
    return batch
