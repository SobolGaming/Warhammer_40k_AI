from __future__ import annotations

from dataclasses import replace

from warhammer40k_core.engine.battle_round_hooks import (
    SELECT_FACTION_RULE_BATTLE_ROUND_OPTION_DECISION_TYPE,
    BattleRoundStartRequestContext,
)
from warhammer40k_core.engine.decision_request import DecisionRequest
from warhammer40k_core.engine.event_log import validate_json_value
from warhammer40k_core.engine.phase import BattlePhase, GameLifecycleError
from warhammer40k_core.engine.sequencing import SequencingRequirement
from warhammer40k_core.engine.timing_request_candidates import timing_candidate_for_request
from warhammer40k_core.engine.timing_rule_candidates import TimingRuleCandidate

from . import army_rule as _rules


def _request_templates(
    context: BattleRoundStartRequestContext,
) -> tuple[DecisionRequest, ...]:
    requests: list[DecisionRequest] = []
    if type(context) is not BattleRoundStartRequestContext:
        raise GameLifecycleError("Templar Vows requires request context.")
    for army in _rules.black_templars_armies(context.state):
        if _rules.vow_selection_recorded_for_player(context.state, player_id=army.player_id):
            continue
        target_unit_ids = _rules.eligible_templar_vow_unit_ids_for_army(army)
        if not target_unit_ids:
            continue
        requests.append(
            DecisionRequest(
                request_id="timing-request-template",
                decision_type=SELECT_FACTION_RULE_BATTLE_ROUND_OPTION_DECISION_TYPE,
                actor_id=army.player_id,
                payload=validate_json_value(
                    {
                        "game_id": context.state.game_id,
                        "battle_round": context.state.battle_round,
                        "phase": BattlePhase.COMMAND.value,
                        "faction_id": _rules.BLACK_TEMPLARS_FACTION_ID,
                        "source_rule_id": _rules.SOURCE_RULE_ID,
                        "hook_id": _rules.HOOK_ID,
                        "effect_kind": _rules.TEMPLAR_VOWS_EFFECT_KIND,
                        "target_unit_instance_ids": list(target_unit_ids),
                    }
                ),
                options=_rules.templar_vow_selection_options(
                    player_id=army.player_id, battle_round=context.state.battle_round
                ),
            )
        )
    return tuple(requests)


def candidates(context: BattleRoundStartRequestContext) -> tuple[TimingRuleCandidate, ...]:
    return tuple(
        timing_candidate_for_request(
            template=request,
            participant_id=f"{_rules.HOOK_ID}:{request.actor_id}",
            source_rule_id=_rules.SOURCE_RULE_ID,
            requirement=SequencingRequirement.MANDATORY,
            next_request_id=context.state.next_decision_request_id,
        )
        for request in _request_templates(context)
    )


def request_for(context: BattleRoundStartRequestContext) -> DecisionRequest | None:
    requests = _request_templates(context)
    if not requests:
        return None
    return replace(requests[0], request_id=context.state.next_decision_request_id())
