from __future__ import annotations

from warhammer40k_core.engine.command_phase_start_candidates import command_request_context
from warhammer40k_core.engine.command_phase_start_hooks import (
    SELECT_FACTION_RULE_COMMAND_PHASE_START_OPTION_DECISION_TYPE,
    CommandPhaseStartEffectContext,
    CommandPhaseStartRequestContext,
)
from warhammer40k_core.engine.decision_request import DecisionOption, DecisionRequest
from warhammer40k_core.engine.event_log import validate_json_value
from warhammer40k_core.engine.faction_content.common import payload_object as _payload_object
from warhammer40k_core.engine.phase import BattlePhase, GameLifecycleError
from warhammer40k_core.engine.sequencing import SequencingRequirement
from warhammer40k_core.engine.timing_request_candidates import timing_candidate_for_request
from warhammer40k_core.engine.timing_rule_candidates import TimingRuleCandidate

from . import army_rule as _rules


def request_for(
    context: CommandPhaseStartRequestContext, *, officer_unit_instance_id: str
) -> DecisionRequest | None:
    if type(context) is not CommandPhaseStartRequestContext:
        raise GameLifecycleError("Voice of Command requires request context.")
    army = _rules.astra_militarum_army_for_player(context.state, player_id=context.active_player_id)
    if army is None:
        return None
    issues = tuple(
        issue
        for issue in _rules.eligible_voice_of_command_issues(context.state, army=army)
        if issue.officer_unit.unit_instance_id == officer_unit_instance_id
    )
    if not issues:
        return None
    common_payload = _payload_object(
        validate_json_value(
            {
                "game_id": context.state.game_id,
                "battle_round": context.state.battle_round,
                "phase": BattlePhase.COMMAND.value,
                "active_player_id": army.player_id,
                "player_id": army.player_id,
                "issuing_officer_unit_instance_id": officer_unit_instance_id,
                "faction_id": _rules.ASTRA_MILITARUM_FACTION_ID,
                "source_rule_id": _rules.SOURCE_RULE_ID,
                "hook_id": _rules.HOOK_ID,
                "effect_kind": _rules.VOICE_OF_COMMAND_EFFECT_KIND,
                "selection_kind": _rules.VOICE_OF_COMMAND_SELECTION_KIND,
                "order_range_inches": _rules.ORDER_RANGE_INCHES,
                "eligible_issue_option_ids": [
                    _rules.voice_issue_option_id(issue) for issue in issues
                ],
                "expires_at_battle_round": _rules.next_own_turn_battle_round(context.state),
            }
        )
    )
    options = tuple(_rules.voice_issue_decision_option(issue, common_payload) for issue in issues)
    return DecisionRequest(
        request_id=context.issue_request_id(),
        decision_type=SELECT_FACTION_RULE_COMMAND_PHASE_START_OPTION_DECISION_TYPE,
        actor_id=army.player_id,
        payload=validate_json_value(common_payload),
        options=(
            *options,
            DecisionOption(
                option_id=_rules.VOICE_OF_COMMAND_DONE_OPTION_ID,
                label="No more Orders from this Officer",
                payload=validate_json_value(
                    {
                        **common_payload,
                        "submission_kind": _rules.VOICE_OF_COMMAND_SELECTION_KIND,
                        "selected_voice_of_command_option": "done",
                    }
                ),
            ),
        ),
    )


def candidates(context: CommandPhaseStartEffectContext) -> tuple[TimingRuleCandidate, ...]:
    army = _rules.astra_militarum_army_for_player(context.state, player_id=context.active_player_id)
    if army is None:
        return ()
    officer_ids = sorted(
        {
            issue.officer_unit.unit_instance_id
            for issue in _rules.eligible_voice_of_command_issues(context.state, army=army)
        }
    )
    candidates: list[TimingRuleCandidate] = []
    for officer_id in officer_ids:
        template = request_for(
            command_request_context(context), officer_unit_instance_id=officer_id
        )
        if template is None:
            raise GameLifecycleError("Voice of Command source occurrence lost its request.")
        candidates.append(
            timing_candidate_for_request(
                template=template,
                participant_id=f"{_rules.HOOK_ID}:{army.player_id}:{officer_id}",
                source_rule_id=_rules.SOURCE_RULE_ID,
                requirement=SequencingRequirement.OPTIONAL,
                next_request_id=context.state.next_decision_request_id,
            )
        )
    return tuple(candidates)
