from __future__ import annotations

from functools import partial

from warhammer40k_core.engine.boundary_sequencing import boundary_context
from warhammer40k_core.engine.command_phase_start_hooks import (
    CommandPhaseStartEffectContext,
    CommandPhaseStartHookBinding,
)
from warhammer40k_core.engine.command_phase_start_sequencing import command_start_timing_context
from warhammer40k_core.engine.event_log import validate_json_value
from warhammer40k_core.engine.faction_content.events import (
    RuntimeContentEvent,
    RuntimeContentEventContext,
    RuntimeContentEventIndex,
    RuntimeContentEventSubscription,
)
from warhammer40k_core.engine.fight_phase_start_hooks import (
    FightPhaseStartHookBinding,
    FightPhaseStartRequestContext,
)
from warhammer40k_core.engine.phase import BattlePhase, GameLifecycleError
from warhammer40k_core.engine.phase_start_sequencing import phase_start_context
from warhammer40k_core.engine.shooting_phase_start_hooks import (
    ShootingPhaseStartHookBinding,
    ShootingPhaseStartRequestContext,
)
from warhammer40k_core.engine.timing_rule_candidates import TimingRuleCandidate
from warhammer40k_core.engine.timing_windows import TimingTriggerKind, TimingWindow
from warhammer40k_core.engine.turn_end_hooks import TurnEndHookBinding, TurnEndRequestContext


def command_start_bindings(
    index: RuntimeContentEventIndex,
) -> tuple[CommandPhaseStartHookBinding, ...]:
    return tuple(
        CommandPhaseStartHookBinding(
            hook_id=f"runtime-command-start:{subscription.subscription_id}",
            source_id=subscription.source_rule_id,
            candidate_handler=partial(_candidates, index, subscription),
        )
        for subscription in index.subscriptions_for(TimingTriggerKind.START_PHASE)
        if "phase" not in subscription.filters
        or subscription.filters["phase"] == BattlePhase.COMMAND.value
    )


def _candidates(
    index: RuntimeContentEventIndex,
    subscription: RuntimeContentEventSubscription,
    context: CommandPhaseStartEffectContext,
) -> tuple[TimingRuleCandidate, ...]:
    if context.ruleset_descriptor is None or context.army_catalog is None:
        raise GameLifecycleError(
            "Command-start runtime rules require the configured ruleset and catalog."
        )
    window = command_start_timing_context(
        context.state,
        battle_round=context.state.battle_round,
        active_player_id=context.active_player_id,
    ).timing_window
    return _phase_candidates(index, subscription, context, window)


def fight_start_bindings(index: RuntimeContentEventIndex) -> tuple[FightPhaseStartHookBinding, ...]:
    return tuple(
        FightPhaseStartHookBinding(
            hook_id=f"runtime-fight-start:{subscription.subscription_id}",
            source_id=subscription.source_rule_id,
            candidate_handler=partial(_fight_candidates, index, subscription),
        )
        for subscription in index.subscriptions_for(TimingTriggerKind.START_PHASE)
        if "phase" not in subscription.filters
        or subscription.filters["phase"] == BattlePhase.FIGHT.value
    )


def _fight_candidates(
    index: RuntimeContentEventIndex,
    subscription: RuntimeContentEventSubscription,
    context: FightPhaseStartRequestContext,
) -> tuple[TimingRuleCandidate, ...]:
    return _phase_candidates(
        index, subscription, context, phase_start_context(context.state).timing_window
    )


def shooting_start_bindings(
    index: RuntimeContentEventIndex,
) -> tuple[ShootingPhaseStartHookBinding, ...]:
    return tuple(
        ShootingPhaseStartHookBinding(
            hook_id=f"runtime-shooting-start:{subscription.subscription_id}",
            source_id=subscription.source_rule_id,
            candidate_handler=partial(_shooting_candidates, index, subscription),
        )
        for subscription in index.subscriptions_for(TimingTriggerKind.START_PHASE)
        if "phase" not in subscription.filters
        or subscription.filters["phase"] == BattlePhase.SHOOTING.value
    )


def _shooting_candidates(
    index: RuntimeContentEventIndex,
    subscription: RuntimeContentEventSubscription,
    context: ShootingPhaseStartRequestContext,
) -> tuple[TimingRuleCandidate, ...]:
    return _phase_candidates(
        index, subscription, context, phase_start_context(context.state).timing_window
    )


def end_bindings(index: RuntimeContentEventIndex) -> tuple[TurnEndHookBinding, ...]:
    return tuple(
        TurnEndHookBinding(
            hook_id=f"runtime-end:{subscription.subscription_id}",
            source_id=subscription.source_rule_id,
            trigger_kind=trigger_kind,
            candidate_handler=partial(_end_candidates, index, subscription),
        )
        for trigger_kind in (TimingTriggerKind.END_PHASE, TimingTriggerKind.END_TURN)
        for subscription in index.subscriptions_for(trigger_kind)
    )


def _end_candidates(
    index: RuntimeContentEventIndex,
    subscription: RuntimeContentEventSubscription,
    context: TurnEndRequestContext,
) -> tuple[TimingRuleCandidate, ...]:
    return _phase_candidates(
        index,
        subscription,
        context,
        boundary_context(context.state, context.trigger_kind).timing_window,
    )


def _phase_candidates(
    index: RuntimeContentEventIndex,
    subscription: RuntimeContentEventSubscription,
    context: CommandPhaseStartEffectContext
    | FightPhaseStartRequestContext
    | ShootingPhaseStartRequestContext
    | TurnEndRequestContext,
    window: TimingWindow,
) -> tuple[TimingRuleCandidate, ...]:
    if context.ruleset_descriptor is None or context.army_catalog is None:
        raise GameLifecycleError(
            "Phase-start runtime rules require the configured ruleset and catalog."
        )
    payload = validate_json_value({"timing_window": window.to_payload(), "resolution_order": []})
    return tuple(
        candidate
        for player_id in context.state.player_ids
        for candidate in index.candidates_for(
            RuntimeContentEventContext(
                event=RuntimeContentEvent(
                    event_id=f"{window.window_id}:runtime:{player_id}",
                    game_id=context.state.game_id,
                    player_id=player_id,
                    battle_round=context.state.battle_round,
                    trigger_kind=window.descriptor.trigger_kind,
                    phase=window.phase,
                    active_player_id=window.active_player_id,
                    event_payload=payload,
                ),
                state=context.state,
                decisions=context.decisions,
                ruleset_descriptor=context.ruleset_descriptor,
                army_catalog=context.army_catalog,
                runtime_modifier_registry=context.runtime_modifier_registry,
            ),
            subscription_id=subscription.subscription_id,
        )
    )
