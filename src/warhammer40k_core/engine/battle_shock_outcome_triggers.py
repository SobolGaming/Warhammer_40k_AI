from __future__ import annotations

from typing import cast

from warhammer40k_core.engine.battle_shock import BattleShockResult, BattleShockResultPayload
from warhammer40k_core.engine.battle_shock_hooks import (
    BattleShockHookRegistry,
    BattleShockOutcomeContext,
)
from warhammer40k_core.engine.battle_shock_outcome_sequencing import resolve_outcome_candidates
from warhammer40k_core.engine.decision_controller import DecisionController
from warhammer40k_core.engine.dice import DiceRollManager
from warhammer40k_core.engine.event_log import validate_json_value
from warhammer40k_core.engine.game_state import GameState
from warhammer40k_core.engine.phase import (
    BattlePhase,
    GameLifecycleError,
    LifecycleStatus,
    LifecycleStatusKind,
)
from warhammer40k_core.engine.rule_trigger_state import (
    RuleTrigger,
    RuleTriggerKind,
    complete_rule_trigger,
    observe_rule_trigger,
    release_rule_trigger,
)


def observe_battle_shock_outcome(
    context: BattleShockOutcomeContext, registry: BattleShockHookRegistry
) -> LifecycleStatus | None:
    result_payload = validate_json_value(context.result.to_payload())
    source_events = tuple(
        event
        for event in context.decisions.event_log.records
        if isinstance(event.payload, dict)
        and event.payload.get("battle_shock_result") == result_payload
        and event.payload.get("auto_passed") == context.auto_passed
        and event.payload.get("phase") == context.phase.value
    )
    if not source_events:
        raise GameLifecycleError("Battle-shock outcome requires its resolved source event.")
    for binding in registry.bindings:
        if binding.outcome_state_handler is not None:
            binding.outcome_state_handler(context)
    trigger = observe_rule_trigger(
        decisions=context.decisions,
        kind=RuleTriggerKind.BATTLE_SHOCK_OUTCOME,
        context=validate_json_value(
            {
                "trigger_event_id": source_events[0].event_id,
                "battle_shock_result": result_payload,
                "active_player_id": context.active_player_id,
                "phase": context.phase.value,
                "auto_passed": context.auto_passed,
                "phase_start_battle_shocked_unit_ids": list(
                    context.phase_start_battle_shocked_unit_ids
                ),
            }
        ),
    )
    return resolve_battle_shock_trigger(
        state=context.state, decisions=context.decisions, trigger=trigger, registry=registry
    )


def battle_shock_context_for_trigger(
    *,
    state: GameState,
    decisions: DecisionController,
    trigger: RuleTrigger,
) -> BattleShockOutcomeContext:
    payload = trigger.context
    if (
        trigger.kind is not RuleTriggerKind.BATTLE_SHOCK_OUTCOME
        or not isinstance(payload, dict)
        or set(payload)
        != {
            "trigger_event_id",
            "battle_shock_result",
            "active_player_id",
            "phase",
            "auto_passed",
            "phase_start_battle_shocked_unit_ids",
        }
    ):
        raise GameLifecycleError("Battle-shock trigger context schema drift.")
    result = payload["battle_shock_result"]
    if not isinstance(result, dict):
        raise GameLifecycleError("Battle-shock trigger requires a result object.")
    parsed = BattleShockResult.from_payload(cast(BattleShockResultPayload, result))
    source_events = tuple(
        event
        for event in decisions.event_log.records
        if event.event_id == payload["trigger_event_id"]
    )
    if len(source_events) != 1 or not isinstance(source_events[0].payload, dict):
        raise GameLifecycleError("Battle-shock trigger lacks a unique source event.")
    source = source_events[0].payload
    if (
        source.get("battle_shock_result") != result
        or source.get("auto_passed") != payload["auto_passed"]
        or source.get("phase") != payload["phase"]
        or source.get("game_id") != state.game_id
        or source.get("battle_round") != parsed.request.battle_round
    ):
        raise GameLifecycleError("Battle-shock trigger source authority drift.")
    observations = tuple(
        event
        for event in decisions.event_log.records
        if event.event_type == "rule_trigger_observed" and event.payload == trigger.to_payload()
    )
    if len(observations) != 1 or source_events[0].event_id >= observations[0].event_id:
        raise GameLifecycleError("Battle-shock trigger observation precedes its source event.")
    phase_value = payload["phase"]
    active = payload["active_player_id"]
    auto_passed = payload["auto_passed"]
    phase_start = payload["phase_start_battle_shocked_unit_ids"]
    if (
        type(phase_value) is not str
        or type(active) is not str
        or type(auto_passed) is not bool
        or not isinstance(phase_start, list)
        or any(type(item) is not str for item in phase_start)
    ):
        raise GameLifecycleError("Battle-shock trigger context fields are malformed.")
    try:
        phase = BattlePhase(phase_value)
    except ValueError as error:
        raise GameLifecycleError("Battle-shock trigger phase is invalid.") from error
    return BattleShockOutcomeContext(
        state=state,
        decisions=decisions,
        dice_manager=DiceRollManager(state.game_id, event_log=decisions.event_log),
        result=parsed,
        active_player_id=active,
        phase=phase,
        auto_passed=auto_passed,
        phase_start_battle_shocked_unit_ids=tuple(cast(list[str], phase_start)),
    )


def resolve_battle_shock_trigger(
    *,
    state: GameState,
    decisions: DecisionController,
    trigger: RuleTrigger,
    registry: BattleShockHookRegistry,
) -> LifecycleStatus | None:
    context = battle_shock_context_for_trigger(state=state, decisions=decisions, trigger=trigger)
    if not release_rule_trigger(decisions=decisions, trigger=trigger):
        from warhammer40k_core.engine.rule_trigger_state import unreleased_rule_trigger_status

        return unreleased_rule_trigger_status(
            decisions=decisions, trigger=trigger, stage=state.stage
        )
    if (
        state.battle_round != context.result.request.battle_round
        or state.current_battle_phase is not context.phase
    ):
        raise GameLifecycleError("Battle-shock trigger escaped its source timing window.")
    status = resolve_outcome_candidates(context, registry)
    from warhammer40k_core.engine.battle_shock_outcome_sequencing import outcome_timing_context
    from warhammer40k_core.engine.timing_batch_runtime import timing_batches_for_context

    batches = timing_batches_for_context(decisions, outcome_timing_context(context))
    if status is None or (
        status.status_kind is LifecycleStatusKind.ADVANCED
        and batches
        and batches[-1].current_batch_complete
    ):
        complete_rule_trigger(decisions=decisions, trigger=trigger)
    return status
