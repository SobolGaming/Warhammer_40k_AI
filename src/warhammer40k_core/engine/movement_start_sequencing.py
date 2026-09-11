from __future__ import annotations

from collections.abc import Callable
from typing import TYPE_CHECKING

from warhammer40k_core.engine.decision_controller import DecisionController
from warhammer40k_core.engine.decision_request import DecisionRequest
from warhammer40k_core.engine.event_log import validate_json_value
from warhammer40k_core.engine.game_state import GameState
from warhammer40k_core.engine.phase import BattlePhase, GameLifecycleError, LifecycleStatus
from warhammer40k_core.engine.phases.movement_model import PendingMovementActionSelection
from warhammer40k_core.engine.sequencing import SequencingConflictContext
from warhammer40k_core.engine.stratagems import StratagemCatalogIndex
from warhammer40k_core.engine.timing_batch_state import TimingBatch
from warhammer40k_core.engine.timing_rule_candidates import (
    TimingRuleCandidate,
    resolve_timing_rule_candidates,
)
from warhammer40k_core.engine.timing_windows import (
    TimingTriggerKind,
    TimingWindow,
    TimingWindowDescriptor,
)
from warhammer40k_core.rules.source_packages.warhammer_40000_11th.core_sequencing_2026_09 import (
    RULES_SEQUENCING_SOURCE_ID,
)

if TYPE_CHECKING:
    from warhammer40k_core.engine.faction_content.bundle import RuntimeContentBundle


def move_start_context(
    state: GameState, pending_action: PendingMovementActionSelection
) -> SequencingConflictContext:
    movement = state.movement_phase_state
    if (
        state.current_battle_phase is not BattlePhase.MOVEMENT
        or movement is None
        or movement.pending_action != pending_action
        or pending_action.battle_round != state.battle_round
        or pending_action.player_id != state.effective_active_player_id()
    ):
        raise GameLifecycleError("Move-start sequencing requires its selected pending action.")
    identity = f"move-start:{pending_action.result_id}"
    return SequencingConflictContext(
        conflict_id=identity,
        game_id=state.game_id,
        player_ids=state.player_ids,
        active_player_id=pending_action.player_id,
        timing_window=TimingWindow(
            window_id=identity,
            game_id=state.game_id,
            battle_round=state.battle_round,
            active_player_id=pending_action.player_id,
            phase=BattlePhase.MOVEMENT,
            descriptor=TimingWindowDescriptor(
                descriptor_id=f"{identity}:descriptor",
                source_rule_id=RULES_SEQUENCING_SOURCE_ID,
                trigger_kind=TimingTriggerKind.BEFORE_UNIT_STARTS_MOVE,
                phase=BattlePhase.MOVEMENT,
                source_step="movement_action_selected",
                metadata=validate_json_value(pending_action.to_payload()),
            ),
        ),
    )


def resolve_move_start_rules(
    *,
    state: GameState,
    decisions: DecisionController,
    pending_action: PendingMovementActionSelection,
    discover: Callable[[], tuple[TimingRuleCandidate, ...]],
) -> LifecycleStatus | None:
    def pure_discovery() -> tuple[TimingRuleCandidate, ...]:
        before = (state.to_payload(), decisions.to_payload())
        candidates = discover()
        if before != (state.to_payload(), decisions.to_payload()):
            raise GameLifecycleError("Move-start rule discovery mutated authoritative state.")
        return candidates

    outcome = resolve_timing_rule_candidates(
        decisions=decisions,
        context=move_start_context(state, pending_action),
        discover=pure_discovery,
        next_request_id=state.next_decision_request_id,
    )
    if isinstance(outcome, DecisionRequest):
        decisions.request_decision(outcome)
        return LifecycleStatus.waiting_for_decision(
            stage=state.stage,
            decision_request=outcome,
            payload={"phase_body_status": "move_start_rule_order_pending"},
        )
    return outcome


def validate_move_start_order_candidates(
    *,
    state: GameState,
    decisions: DecisionController,
    batch: TimingBatch,
    bundle: RuntimeContentBundle,
    stratagem_index: StratagemCatalogIndex,
) -> None:
    from warhammer40k_core.engine.phases.movement_start_candidates import movement_start_candidates

    movement = state.movement_phase_state
    if movement is None or movement.pending_action is None:
        raise GameLifecycleError("Move-start order lost its selected action.")
    pending = movement.pending_action
    if batch.context != move_start_context(state, pending):
        raise GameLifecycleError("Move-start order source context drift.")
    records = tuple(
        record for record in decisions.records if record.result.result_id == pending.result_id
    )
    expected = pending.to_decision_result()
    if len(records) != 1:
        raise GameLifecycleError("Move-start order requires its recorded action selection.")
    recorded = records[0].result
    if (
        recorded.request_id != expected.request_id
        or recorded.decision_type != expected.decision_type
        or recorded.actor_id != expected.actor_id
        or recorded.selected_option_id != expected.selected_option_id
        or not isinstance(recorded.payload, dict)
        or not isinstance(expected.payload, dict)
        or any(recorded.payload.get(key) != value for key, value in expected.payload.items())
    ):
        raise GameLifecycleError("Move-start order selected action authority drift.")
    candidates = movement_start_candidates(
        state=state,
        decisions=decisions,
        pending=pending,
        grant_registry=bundle.advance_move_hook_registry,
        ability_indexes=bundle.ability_indexes_by_player_id,
        modifiers=bundle.runtime_modifier_registry,
        stratagem_index=stratagem_index,
        cost_modifiers=bundle.stratagem_cost_modifier_registry,
    )
    current = {
        candidate.participant.participant_id: candidate.participant for candidate in candidates
    }
    if len(current) != len(candidates) or any(
        current.get(participant.participant_id) != participant
        for participant in batch.eligible_participants()
    ):
        raise GameLifecycleError("Move-start order source population drift.")
    if (
        batch.generation == 0
        and not batch.completed_participant_ids
        and set(current) != {participant.participant_id for participant in batch.participants}
    ):
        raise GameLifecycleError("Move-start order original population drift.")
