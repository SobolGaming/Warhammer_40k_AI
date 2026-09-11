from __future__ import annotations

from dataclasses import replace

from warhammer40k_core.engine.command_phase_start_candidates import command_request_context
from warhammer40k_core.engine.command_phase_start_hooks import (
    SELECT_FACTION_RULE_COMMAND_PHASE_START_OPTION_DECISION_TYPE,
    CommandPhaseStartEffectContext,
    CommandPhaseStartRequestContext,
)
from warhammer40k_core.engine.decision_request import DecisionOption, DecisionRequest
from warhammer40k_core.engine.event_log import validate_json_value
from warhammer40k_core.engine.phase import GameLifecycleError
from warhammer40k_core.engine.sequencing import SequencingRequirement
from warhammer40k_core.engine.timing_request_candidates import timing_candidate_for_request
from warhammer40k_core.engine.timing_rule_candidates import TimingRuleCandidate

from . import army_rule as _rules


def _request_templates(context: CommandPhaseStartRequestContext) -> tuple[DecisionRequest, ...]:
    requests: list[DecisionRequest] = []
    if type(context) is not CommandPhaseStartRequestContext:
        raise GameLifecycleError("Shadow in the Warp requires request context.")
    for army in _rules.tyranids_armies(context.state):
        if _rules.shadow_in_the_warp_unleashed_for_player(context.state, player_id=army.player_id):
            continue
        if _rules.shadow_declined_this_command_phase(context.state, player_id=army.player_id):
            continue
        source_unit_ids = _rules.eligible_shadow_source_unit_ids(state=context.state, army=army)
        if not source_unit_ids:
            continue
        target_unit_ids = _rules.enemy_unit_ids_on_battlefield(context.state, tyranids_army=army)
        if not target_unit_ids:
            continue
        common_payload = _rules.shadow_common_payload(
            state=context.state,
            active_player_id=context.active_player_id,
            player_id=army.player_id,
            source_unit_ids=source_unit_ids,
            target_unit_ids=target_unit_ids,
        )
        requests.append(
            DecisionRequest(
                request_id="timing-request-template",
                decision_type=SELECT_FACTION_RULE_COMMAND_PHASE_START_OPTION_DECISION_TYPE,
                actor_id=army.player_id,
                payload=validate_json_value(common_payload),
                options=(
                    DecisionOption(
                        option_id=_rules.SHADOW_UNLEASH_OPTION_ID,
                        label="Unleash Shadow in the Warp",
                        payload=validate_json_value(
                            {
                                **common_payload,
                                "submission_kind": _rules.SHADOW_SELECTION_KIND,
                                "selected_shadow_option": "unleash",
                            }
                        ),
                    ),
                    DecisionOption(
                        option_id=_rules.SHADOW_DECLINE_OPTION_ID,
                        label="Do not unleash Shadow in the Warp",
                        payload=validate_json_value(
                            {
                                **common_payload,
                                "submission_kind": _rules.SHADOW_SELECTION_KIND,
                                "selected_shadow_option": "decline",
                            }
                        ),
                    ),
                ),
            )
        )
    return tuple(requests)


def candidates(context: CommandPhaseStartEffectContext) -> tuple[TimingRuleCandidate, ...]:
    return tuple(
        timing_candidate_for_request(
            template=request,
            participant_id=f"{_rules.HOOK_ID}:{request.actor_id}",
            source_rule_id=_rules.SOURCE_RULE_ID,
            requirement=SequencingRequirement.OPTIONAL,
            next_request_id=context.state.next_decision_request_id,
        )
        for request in _request_templates(command_request_context(context))
    )


def request_for(context: CommandPhaseStartRequestContext) -> DecisionRequest | None:
    requests = _request_templates(context)
    if not requests:
        return None
    return replace(requests[0], request_id=context.issue_request_id())
