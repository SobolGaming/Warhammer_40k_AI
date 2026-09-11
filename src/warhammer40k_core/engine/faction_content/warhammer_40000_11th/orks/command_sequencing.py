from __future__ import annotations

from warhammer40k_core.engine.command_phase_start_candidates import command_army_rule_candidate
from warhammer40k_core.engine.command_phase_start_hooks import (
    SELECT_FACTION_RULE_COMMAND_PHASE_START_OPTION_DECISION_TYPE,
    CommandPhaseStartEffectContext,
    CommandPhaseStartRequestContext,
)
from warhammer40k_core.engine.decision_request import DecisionOption, DecisionRequest
from warhammer40k_core.engine.event_log import validate_json_value
from warhammer40k_core.engine.phase import BattlePhase, GameLifecycleError
from warhammer40k_core.engine.sequencing import SequencingRequirement
from warhammer40k_core.engine.timing_rule_candidates import TimingRuleCandidate

from . import army_rule as _rules


def request_for(context: CommandPhaseStartRequestContext) -> DecisionRequest | None:
    if type(context) is not CommandPhaseStartRequestContext:
        raise GameLifecycleError("Waaagh! call requires request context.")
    army = _rules.orks_army_for_player(context.state, player_id=context.active_player_id)
    if army is None:
        return None
    if _rules.waaagh_called_for_player(context.state, player_id=army.player_id):
        return None
    if _rules.waaagh_declined_this_command_phase(context.state, player_id=army.player_id):
        return None
    target_unit_ids = _rules.eligible_waaagh_unit_ids_for_army(army)
    if not target_unit_ids:
        return None
    common_payload = {
        "game_id": context.state.game_id,
        "battle_round": context.state.battle_round,
        "phase": BattlePhase.COMMAND.value,
        "active_player_id": army.player_id,
        "player_id": army.player_id,
        "faction_id": _rules.ORKS_FACTION_ID,
        "source_rule_id": _rules.SOURCE_RULE_ID,
        "hook_id": _rules.HOOK_ID,
        "effect_kind": _rules.WAAAGH_EFFECT_KIND,
        "selection_kind": _rules.WAAAGH_SELECTION_KIND,
        "eligible_target_unit_instance_ids": list(target_unit_ids),
        "expires_at_battle_round": _rules.next_own_turn_battle_round(context.state),
        "rules_update_source": _rules.WAAAGH_RULE_UPDATE_SOURCE,
    }
    return DecisionRequest(
        request_id=context.issue_request_id(),
        decision_type=SELECT_FACTION_RULE_COMMAND_PHASE_START_OPTION_DECISION_TYPE,
        actor_id=army.player_id,
        payload=validate_json_value(common_payload),
        options=(
            DecisionOption(
                option_id=_rules.WAAAGH_CALL_OPTION_ID,
                label="Call Waaagh!",
                payload=validate_json_value(
                    {
                        **common_payload,
                        "submission_kind": _rules.WAAAGH_SELECTION_KIND,
                        "selected_waaagh_option": "call",
                    }
                ),
            ),
            DecisionOption(
                option_id=_rules.WAAAGH_DECLINE_OPTION_ID,
                label="Do not call Waaagh!",
                payload=validate_json_value(
                    {
                        **common_payload,
                        "submission_kind": _rules.WAAAGH_SELECTION_KIND,
                        "selected_waaagh_option": "decline",
                    }
                ),
            ),
        ),
    )


def candidates(context: CommandPhaseStartEffectContext) -> tuple[TimingRuleCandidate, ...]:
    return command_army_rule_candidate(
        context,
        request_handler=request_for,
        source_rule_id=_rules.SOURCE_RULE_ID,
        hook_id=_rules.HOOK_ID,
        requirement=SequencingRequirement.OPTIONAL,
    )
