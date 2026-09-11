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
from warhammer40k_core.engine.phase import BattlePhase, GameLifecycleError
from warhammer40k_core.engine.sequencing import SequencingRequirement
from warhammer40k_core.engine.timing_request_candidates import timing_candidate_for_request
from warhammer40k_core.engine.timing_rule_candidates import TimingRuleCandidate

from . import army_rule as _rules


def request_for(context: CommandPhaseStartRequestContext) -> DecisionRequest | None:
    if type(context) is not CommandPhaseStartRequestContext:
        raise GameLifecycleError("Reanimation Protocols requires request context.")
    army = _rules.necrons_army_for_player(context.state, player_id=context.active_player_id)
    if army is None:
        return None
    unresolved_rules_units = tuple(
        rules_unit
        for rules_unit in _rules.eligible_reanimation_rules_units(context.state, army=army)
        if not _rules.reanimation_resolved_for_rules_unit(
            records=context.decisions.event_log.records,
            state=context.state,
            player_id=army.player_id,
            rules_unit_instance_id=rules_unit.unit_instance_id,
        )
    )
    if not unresolved_rules_units:
        return None
    common_payload = {
        "game_id": context.state.game_id,
        "battle_round": context.state.battle_round,
        "phase": BattlePhase.COMMAND.value,
        "active_player_id": army.player_id,
        "player_id": army.player_id,
        "faction_id": _rules.NECRONS_FACTION_ID,
        "source_rule_id": _rules.SOURCE_RULE_ID,
        "hook_id": _rules.HOOK_ID,
        "effect_kind": _rules.REANIMATION_EFFECT_KIND,
        "selection_kind": _rules.REANIMATION_SELECTION_KIND,
        "eligible_rules_unit_instance_ids": [
            rules_unit.unit_instance_id for rules_unit in unresolved_rules_units
        ],
    }
    return DecisionRequest(
        request_id=context.issue_request_id(),
        decision_type=SELECT_FACTION_RULE_COMMAND_PHASE_START_OPTION_DECISION_TYPE,
        actor_id=army.player_id,
        payload=validate_json_value(common_payload),
        options=tuple(
            DecisionOption(
                option_id=_rules.reanimation_option_id(rules_unit.unit_instance_id),
                label=f"Reanimation Protocols: {_rules.rules_unit_label(rules_unit)}",
                payload=validate_json_value(
                    {
                        **common_payload,
                        "rules_unit_instance_id": rules_unit.unit_instance_id,
                        "rules_unit_owner_player_id": army.player_id,
                        "rules_unit_name": _rules.rules_unit_label(rules_unit),
                        "component_unit_instance_ids": list(rules_unit.component_unit_instance_ids),
                    }
                ),
            )
            for rules_unit in unresolved_rules_units
        ),
    )


def candidates(context: CommandPhaseStartEffectContext) -> tuple[TimingRuleCandidate, ...]:
    request = request_for(command_request_context(context))
    if request is None:
        return ()
    if not isinstance(request.payload, dict):
        raise GameLifecycleError("Reanimation occurrence requires its source request object.")
    candidates: list[TimingRuleCandidate] = []
    for option in request.options:
        if not isinstance(option.payload, dict):
            raise GameLifecycleError("Reanimation occurrence requires its source option object.")
        unit_id = option.payload["rules_unit_instance_id"]
        if type(unit_id) is not str:
            raise GameLifecycleError("Reanimation occurrence requires a rules-unit identity.")
        inventory = {"eligible_rules_unit_instance_ids": [unit_id]}
        template = replace(
            request,
            payload=validate_json_value({**request.payload, **inventory}),
            options=(
                replace(option, payload=validate_json_value({**option.payload, **inventory})),
            ),
        )
        candidates.append(
            timing_candidate_for_request(
                template=template,
                participant_id=f"{_rules.HOOK_ID}:{request.actor_id}:{unit_id}",
                source_rule_id=_rules.SOURCE_RULE_ID,
                requirement=SequencingRequirement.MANDATORY,
                next_request_id=context.state.next_decision_request_id,
            )
        )
    return tuple(candidates)
