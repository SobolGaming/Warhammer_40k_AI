from __future__ import annotations

from dataclasses import replace

from warhammer40k_core.engine.battle_round_hooks import (
    SELECT_FACTION_RULE_BATTLE_ROUND_OPTION_DECISION_TYPE,
    BattleRoundStartRequestContext,
)
from warhammer40k_core.engine.decision_request import DecisionRequest
from warhammer40k_core.engine.event_log import validate_json_value
from warhammer40k_core.engine.phase import GameLifecycleError
from warhammer40k_core.engine.sequencing import SequencingRequirement
from warhammer40k_core.engine.timing_request_candidates import timing_candidate_for_request
from warhammer40k_core.engine.timing_rule_candidates import TimingRuleCandidate

from . import army_rule as _rules


def _request_templates(
    context: BattleRoundStartRequestContext,
) -> tuple[DecisionRequest, ...]:
    requests: list[DecisionRequest] = []
    if type(context) is not BattleRoundStartRequestContext:
        raise GameLifecycleError("Doctrina Imperatives requires request context.")
    for army in _rules.adeptus_mechanicus_armies(context.state):
        if _rules.doctrina_selection_recorded_for_round(
            context.state, player_id=army.player_id, battle_round=context.state.battle_round
        ):
            continue
        target_unit_ids = _rules.eligible_doctrina_rules_unit_ids_for_army(
            state=context.state, army=army
        )
        if not target_unit_ids:
            continue
        common_payload = _rules.doctrina_common_payload(
            state=context.state, player_id=army.player_id, target_unit_ids=target_unit_ids
        )
        requests.append(
            DecisionRequest(
                request_id="timing-request-template",
                decision_type=SELECT_FACTION_RULE_BATTLE_ROUND_OPTION_DECISION_TYPE,
                actor_id=army.player_id,
                payload=validate_json_value(common_payload),
                options=_rules.doctrina_selection_options(common_payload=common_payload),
            )
        )
    return tuple(requests)


def candidates(context: BattleRoundStartRequestContext) -> tuple[TimingRuleCandidate, ...]:
    return tuple(
        timing_candidate_for_request(
            template=request,
            participant_id=f"{_rules.HOOK_ID}:{request.actor_id}",
            source_rule_id=_rules.SOURCE_RULE_ID,
            requirement=SequencingRequirement.OPTIONAL,
            next_request_id=context.state.next_decision_request_id,
        )
        for request in _request_templates(context)
    )


def request_for(context: BattleRoundStartRequestContext) -> DecisionRequest | None:
    requests = _request_templates(context)
    if not requests:
        return None
    return replace(requests[0], request_id=context.state.next_decision_request_id())
