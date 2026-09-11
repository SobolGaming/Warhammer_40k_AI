from __future__ import annotations

# pyright: reportPrivateUsage=false
from warhammer40k_core.engine.faction_content.events import RuntimeContentEventContext
from warhammer40k_core.engine.runtime_event_candidates import runtime_event_candidate
from warhammer40k_core.engine.sequencing import SequencingRequirement
from warhammer40k_core.engine.timing_rule_candidates import TimingRuleCandidate
from warhammer40k_core.engine.timing_windows import TimingTriggerKind

from . import army_rule as rules


def candidates(context: RuntimeContentEventContext) -> tuple[TimingRuleCandidate, ...]:
    player_id = context.event.player_id
    if rules._imperial_knights_army_for_player(context.state, player_id=player_id) is None:
        return ()
    if rules.army_is_honoured(context.state, player_id=player_id):
        return ()
    oath = rules.selected_oath_state_for_player(context.state, player_id=player_id)
    if oath is None:
        return ()
    deed = rules._deed_from_token(
        rules._payload_string(rules._payload_object(oath.payload), key="selected_deed_id")
    )
    if (
        rules._deed_completion_evidence(
            context=context,
            player_id=player_id,
            deed=deed,
            trigger_kind=context.event.trigger_kind,
        )
        is None
    ):
        return ()
    is_turn = context.event.trigger_kind is TimingTriggerKind.END_TURN
    subscription = rules._END_TURN_SUBSCRIPTION if is_turn else rules._END_BATTLE_ROUND_SUBSCRIPTION
    handler = (
        rules.resolve_code_chivalric_end_turn
        if is_turn
        else rules.resolve_code_chivalric_end_battle_round
    )
    candidate = runtime_event_candidate(
        context,
        subscription,
        occurrence_id=oath.state_id,
        requirement=SequencingRequirement.MANDATORY,
        handler=handler,
        source_payload={"oath_state_id": oath.state_id, "deed_id": deed.value},
    )
    return () if candidate is None else (candidate,)
