from __future__ import annotations

from dataclasses import replace
from functools import partial

from warhammer40k_core.engine.battle_round_hooks import (
    SELECT_FACTION_RULE_BATTLE_ROUND_OPTION_DECISION_TYPE,
    BattleRoundStartRequestContext,
)
from warhammer40k_core.engine.decision_request import DecisionRequest
from warhammer40k_core.engine.event_log import validate_json_value
from warhammer40k_core.engine.faction_content.common import payload_object as _payload_object
from warhammer40k_core.engine.faction_content.common import payload_string as _payload_string
from warhammer40k_core.engine.phase import GameLifecycleError
from warhammer40k_core.engine.sequencing import SequencingParticipant, SequencingRequirement
from warhammer40k_core.engine.timing_request_candidates import timing_candidate_for_request
from warhammer40k_core.engine.timing_rule_candidates import TimingRuleCandidate

from . import army_rule as _rules


def miracle_candidates(context: BattleRoundStartRequestContext) -> tuple[TimingRuleCandidate, ...]:
    return tuple(
        TimingRuleCandidate(
            participant=SequencingParticipant(
                participant_id=_rules.battle_round_start_source_id(
                    player_id=army.player_id, battle_round=context.state.battle_round
                ),
                player_id=army.player_id,
                source_rule_id=_rules.SOURCE_RULE_ID,
                requirement=SequencingRequirement.MANDATORY,
            ),
            activate=partial(_gain_miracle_die, context, player_id=army.player_id),
        )
        for army in context.state.army_definitions
        if army.detachment_selection.faction_id == _rules.ADEPTA_SORORITAS_FACTION_ID
        and not _rules.gain_source_exists(
            context.state,
            player_id=army.player_id,
            source_id=_rules.battle_round_start_source_id(
                player_id=army.player_id, battle_round=context.state.battle_round
            ),
        )
    )


def _gain_miracle_die(context: BattleRoundStartRequestContext, *, player_id: str) -> None:
    _rules.gain_miracle_die(
        context.state,
        context.decisions,
        player_id=player_id,
        trigger=_rules.BATTLE_ROUND_START_TRIGGER,
        source_id=_rules.battle_round_start_source_id(
            player_id=player_id, battle_round=context.state.battle_round
        ),
        source_context={
            "active_player_id": context.state.turn_order[0],
            "timing": "start_of_battle_round",
        },
    )


def relic_candidates(context: BattleRoundStartRequestContext) -> tuple[TimingRuleCandidate, ...]:
    candidates: list[TimingRuleCandidate] = []
    for request in _relic_templates(context):
        unit_id = _payload_string(_payload_object(request.payload), key="source_unit_instance_id")
        candidates.append(
            timing_candidate_for_request(
                template=request,
                participant_id=f"{_rules.TRIUMPH_RELICS_BATTLE_ROUND_START_HOOK_ID}:{unit_id}",
                source_rule_id=_rules.TRIUMPH_RELICS_SOURCE_RULE_ID,
                requirement=SequencingRequirement.OPTIONAL,
                next_request_id=context.state.next_decision_request_id,
            )
        )
    return tuple(candidates)


def relic_request_for(context: BattleRoundStartRequestContext) -> DecisionRequest | None:
    requests = _relic_templates(context)
    if not requests:
        return None
    return replace(requests[0], request_id=context.state.next_decision_request_id())


def _relic_templates(context: BattleRoundStartRequestContext) -> tuple[DecisionRequest, ...]:
    requests: list[DecisionRequest] = []
    if type(context) is not BattleRoundStartRequestContext:
        raise GameLifecycleError("Relics of the Matriarchs requires request context.")
    for source in _rules.eligible_triumph_relic_sources(context.state):
        if (
            _rules.triumph_relic_selection_state_for_unit(
                context.state,
                player_id=source.army.player_id,
                unit_instance_id=source.unit.unit_instance_id,
                battle_round=context.state.battle_round,
            )
            is not None
        ):
            continue
        common_payload = _rules.triumph_relics_common_payload(context=context, source=source)
        options = _rules.triumph_relics_selection_options(
            common_payload=common_payload, max_selections=source.selection_limit.max_selections
        )
        requests.append(
            DecisionRequest(
                request_id="timing-request-template",
                decision_type=SELECT_FACTION_RULE_BATTLE_ROUND_OPTION_DECISION_TYPE,
                actor_id=source.army.player_id,
                payload=validate_json_value(common_payload),
                options=options,
            )
        )
    return tuple(requests)
