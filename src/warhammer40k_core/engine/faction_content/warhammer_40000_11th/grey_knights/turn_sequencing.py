# pyright: reportPrivateUsage=false
from __future__ import annotations

from warhammer40k_core.engine.decision_request import DecisionRequest
from warhammer40k_core.engine.faction_content.warhammer_40000_11th.grey_knights.army_rule import (
    HOOK_ID,
    SOURCE_RULE_ID,
    _active_player_id,
    _grey_knights_armies,
    eligible_gate_of_infinity_rules_units,
    gate_of_infinity_complete_option,
    gate_of_infinity_completed_this_turn,
    gate_of_infinity_max_units_for_battle_size,
    gate_of_infinity_option,
    gate_of_infinity_request_payload,
    used_rules_unit_ids_this_turn,
)
from warhammer40k_core.engine.phase import BattlePhase, GameLifecycleError
from warhammer40k_core.engine.sequencing import SequencingRequirement
from warhammer40k_core.engine.timing_request_candidates import timing_candidate_for_request
from warhammer40k_core.engine.timing_rule_candidates import TimingRuleCandidate
from warhammer40k_core.engine.turn_end_hooks import (
    SELECT_FACTION_RULE_TURN_END_OPTION_DECISION_TYPE,
    TurnEndRequestContext,
)


def candidates(context: TurnEndRequestContext) -> tuple[TimingRuleCandidate, ...]:
    candidates: list[TimingRuleCandidate] = []
    if type(context) is not TurnEndRequestContext:
        raise GameLifecycleError("Grey Knights Gate of Infinity requires request context.")
    if context.completed_phase is not BattlePhase.FIGHT:
        return tuple(candidates)
    active_player_id = _active_player_id(context.state)
    for army in _grey_knights_armies(context.state):
        if army.player_id == active_player_id:
            continue
        if gate_of_infinity_completed_this_turn(context, player_id=army.player_id):
            continue
        selected_rules_unit_ids = used_rules_unit_ids_this_turn(context, player_id=army.player_id)
        max_units = gate_of_infinity_max_units_for_battle_size(army.battle_size)
        remaining_units = max_units - len(selected_rules_unit_ids)
        if remaining_units <= 0:
            continue
        eligible_views = eligible_gate_of_infinity_rules_units(state=context.state, army=army)
        if not eligible_views:
            continue
        candidates.append(
            timing_candidate_for_request(
                template=DecisionRequest(
                    request_id="template:turn-end-rule",
                    decision_type=SELECT_FACTION_RULE_TURN_END_OPTION_DECISION_TYPE,
                    actor_id=army.player_id,
                    payload=gate_of_infinity_request_payload(
                        context=context,
                        army=army,
                        active_player_id=active_player_id,
                        max_units=max_units,
                        selected_rules_unit_ids=selected_rules_unit_ids,
                        eligible_views=eligible_views,
                    ),
                    options=(
                        *(
                            gate_of_infinity_option(
                                player_id=army.player_id, rules_unit_view=view, use_ability=True
                            )
                            for view in eligible_views
                        ),
                        gate_of_infinity_complete_option(player_id=army.player_id),
                    ),
                ),
                participant_id=f"{HOOK_ID}:{army.player_id}",
                source_rule_id=SOURCE_RULE_ID,
                requirement=SequencingRequirement.OPTIONAL,
                next_request_id=context.state.next_decision_request_id,
            )
        )
    return tuple(candidates)
