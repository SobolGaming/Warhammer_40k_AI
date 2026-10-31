"""Acts of Faith at the shared player-turn boundary."""

from __future__ import annotations

from warhammer40k_core.engine.faction_content.events import (
    RuntimeContentEventContext,
    RuntimeContentEventResult,
    RuntimeContentEventSubscription,
)
from warhammer40k_core.engine.phase import BattlePhase, GameLifecycleError, GameLifecycleStage
from warhammer40k_core.engine.runtime_event_candidates import runtime_event_candidate
from warhammer40k_core.engine.sequencing import SequencingRequirement
from warhammer40k_core.engine.timing_rule_candidates import TimingRuleCandidate
from warhammer40k_core.engine.timing_windows import TimingTriggerKind

from . import army_rule as rules

TURN_START_SUBSCRIPTION = RuntimeContentEventSubscription(
    subscription_id=rules.TURN_START_HOOK_ID,
    source_rule_id=rules.SOURCE_RULE_ID,
    trigger_kind=TimingTriggerKind.START_TURN,
    handler_id=rules.TURN_START_HOOK_ID,
)


def _source_id(context: RuntimeContentEventContext) -> str:
    if type(context) is not RuntimeContentEventContext:
        raise GameLifecycleError("Acts of Faith turn start requires runtime context.")
    state, event = context.state, context.event
    if (
        event.trigger_kind is not TimingTriggerKind.START_TURN
        or state.stage is not GameLifecycleStage.BATTLE
        or state.current_battle_phase is not BattlePhase.COMMAND
        or state.active_player_id is None
        or event.active_player_id != state.active_player_id
        or event.battle_round != state.battle_round
        or event.game_id != state.game_id
    ):
        raise GameLifecycleError("Acts of Faith turn-start boundary drift.")
    return rules.turn_start_source_id(
        player_id=event.player_id,
        battle_round=state.battle_round,
        active_player_id=state.active_player_id,
    )


def candidates(context: RuntimeContentEventContext) -> tuple[TimingRuleCandidate, ...]:
    source_id = _source_id(context)
    player_id = context.event.player_id
    if rules.adepta_sororitas_army_for_player(context.state, player_id=player_id) is None:
        return ()
    if rules.gain_source_exists(context.state, player_id=player_id, source_id=source_id):
        return ()
    candidate = runtime_event_candidate(
        context,
        TURN_START_SUBSCRIPTION,
        occurrence_id=source_id,
        requirement=SequencingRequirement.MANDATORY,
        handler=resolve_turn_start,
        source_payload={"gain_source_id": source_id},
    )
    return () if candidate is None else (candidate,)


def resolve_turn_start(context: RuntimeContentEventContext) -> RuntimeContentEventResult:
    source_id = _source_id(context)
    die = rules.gain_miracle_die(
        context.state,
        context.decisions,
        player_id=context.event.player_id,
        trigger=rules.TURN_START_TRIGGER,
        source_id=source_id,
        source_context={
            "active_player_id": context.state.active_player_id,
            "timing": "start_of_turn",
        },
    )
    return RuntimeContentEventResult.applied(
        TURN_START_SUBSCRIPTION,
        replay_payload={"source_id": source_id, "miracle_die": die.to_payload() if die else None},
    )
