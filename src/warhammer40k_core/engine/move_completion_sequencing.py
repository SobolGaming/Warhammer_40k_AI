from __future__ import annotations

from collections.abc import Callable
from functools import partial

from warhammer40k_core.engine.battle_shock_hooks import BattleShockHookRegistry
from warhammer40k_core.engine.decision_request import DecisionRequest
from warhammer40k_core.engine.move_completion_candidates import move_completion_candidates
from warhammer40k_core.engine.phase import GameLifecycleError, LifecycleStatus
from warhammer40k_core.engine.sequencing import SequencingConflictContext
from warhammer40k_core.engine.timing_rule_candidates import (
    TimingRuleCandidate,
    resolve_timing_rule_candidates,
)
from warhammer40k_core.engine.timing_windows import (
    TimingTriggerKind,
    TimingWindow,
    TimingWindowDescriptor,
)
from warhammer40k_core.engine.unit_move_completed_hooks import (
    UnitMoveCompletedBattleShockHookRegistry,
    UnitMoveCompletedContext,
    UnitMoveCompletedMortalWoundHookRegistry,
)
from warhammer40k_core.rules.source_packages.warhammer_40000_11th.core_sequencing_2026_09 import (
    RULES_SEQUENCING_SOURCE_ID,
)


def move_completion_timing_context(context: UnitMoveCompletedContext) -> SequencingConflictContext:
    identifier = f"move-completion:{context.trigger_event_id}"
    active = context.state.effective_active_player_id()
    return SequencingConflictContext(
        conflict_id=identifier,
        game_id=context.state.game_id,
        player_ids=context.state.player_ids,
        active_player_id=active,
        timing_window=TimingWindow(
            window_id=identifier,
            game_id=context.state.game_id,
            battle_round=context.state.battle_round,
            active_player_id=active,
            phase=context.completed_phase,
            trigger_event_id=context.trigger_event_id,
            descriptor=TimingWindowDescriptor(
                descriptor_id=f"{identifier}:descriptor",
                source_rule_id=RULES_SEQUENCING_SOURCE_ID,
                trigger_kind=TimingTriggerKind.AFTER_UNIT_ENDS_CHARGE_MOVE
                if context.movement_action == "charge_move"
                else (
                    TimingTriggerKind.MODEL_PLACED_ON_BATTLEFIELD
                    if context.movement_action == "set_up"
                    else TimingTriggerKind.AFTER_UNIT_ENDS_MOVE
                ),
                phase=context.completed_phase,
                source_step="unit_move_completed",
            ),
        ),
    )


def resolve_move_completion_now(
    *,
    context: UnitMoveCompletedContext,
    mortal_wound_hooks: UnitMoveCompletedMortalWoundHookRegistry,
    battle_shock_move_hooks: UnitMoveCompletedBattleShockHookRegistry | None = None,
    battle_shock_hooks: BattleShockHookRegistry | None = None,
    additional_candidates: Callable[[UnitMoveCompletedContext], tuple[TimingRuleCandidate, ...]]
    | None = None,
) -> LifecycleStatus | None:
    decisions = context.decisions
    if decisions is None:
        raise GameLifecycleError("Move-completion sequencing requires decisions.")
    if battle_shock_move_hooks is not None and battle_shock_hooks is None:
        raise GameLifecycleError("Move-completion Battle-shock requires outcome services.")
    outcome = resolve_timing_rule_candidates(
        decisions=decisions,
        context=move_completion_timing_context(context),
        discover=partial(
            move_completion_candidates,
            additional_candidates=additional_candidates,
            context=context,
            mortal_wound_hooks=mortal_wound_hooks,
            battle_shock_move_hooks=UnitMoveCompletedBattleShockHookRegistry.empty()
            if battle_shock_move_hooks is None
            else battle_shock_move_hooks,
            battle_shock_hooks=BattleShockHookRegistry.empty()
            if battle_shock_hooks is None
            else battle_shock_hooks,
        ),
        next_request_id=context.state.next_decision_request_id,
    )
    if isinstance(outcome, DecisionRequest):
        decisions.request_decision(outcome)
        return LifecycleStatus.waiting_for_decision(
            stage=context.state.stage,
            decision_request=outcome,
            payload={
                "phase": context.completed_phase.value,
                "phase_body_status": "move_completion_order_pending",
            },
        )
    return outcome


def resolve_move_completion(
    *,
    context: UnitMoveCompletedContext,
    mortal_wound_hooks: UnitMoveCompletedMortalWoundHookRegistry,
    battle_shock_move_hooks: UnitMoveCompletedBattleShockHookRegistry | None = None,
    battle_shock_hooks: BattleShockHookRegistry | None = None,
    additional_candidates: Callable[[UnitMoveCompletedContext], tuple[TimingRuleCandidate, ...]]
    | None = None,
) -> LifecycleStatus | None:
    from warhammer40k_core.engine.move_completion_triggers import (
        observe_move_completion,
        resolve_move_trigger,
    )

    trigger = observe_move_completion(context)
    return resolve_move_trigger(
        additional_candidates=additional_candidates,
        context=context,
        trigger=trigger,
        mortal_wound_hooks=mortal_wound_hooks,
        battle_shock_move_hooks=battle_shock_move_hooks,
        battle_shock_hooks=battle_shock_hooks,
    )
