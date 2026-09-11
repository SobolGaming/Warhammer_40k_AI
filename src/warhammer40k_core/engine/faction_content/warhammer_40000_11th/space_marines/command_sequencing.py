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
        raise GameLifecycleError("Oath of Moment target selection requires request context.")
    army = _rules.space_marines_army_for_player(context.state, player_id=context.active_player_id)
    if army is None:
        return None
    if (
        _rules.oath_of_moment_target_unit_id_for_player(context.state, player_id=army.player_id)
        is not None
    ):
        return None
    targets = _rules.eligible_oath_target_units(context.state, player_id=army.player_id)
    if not targets:
        return None
    common_payload = {
        "game_id": context.state.game_id,
        "battle_round": context.state.battle_round,
        "phase": BattlePhase.COMMAND.value,
        "active_player_id": army.player_id,
        "player_id": army.player_id,
        "faction_id": _rules.SPACE_MARINES_FACTION_ID,
        "source_rule_id": _rules.SOURCE_RULE_ID,
        "hook_id": _rules.HOOK_ID,
        "effect_kind": _rules.OATH_OF_MOMENT_EFFECT_KIND,
        "selection_kind": _rules.OATH_OF_MOMENT_SELECTION_KIND,
        "eligible_target_unit_instance_ids": [
            target.unit_instance_id for _owner_id, target in targets
        ],
        "expires_at_battle_round": _rules.next_own_turn_battle_round(context.state),
    }
    return DecisionRequest(
        request_id=context.issue_request_id(),
        decision_type=SELECT_FACTION_RULE_COMMAND_PHASE_START_OPTION_DECISION_TYPE,
        actor_id=army.player_id,
        payload=validate_json_value(common_payload),
        options=tuple(
            (
                DecisionOption(
                    option_id=f"space_marines:oath_of_moment:{target.unit_instance_id}",
                    label=f"Oath of Moment: {target.name}",
                    payload=validate_json_value(
                        {
                            **common_payload,
                            "target_owner_player_id": owner_id,
                            "target_unit_instance_id": target.unit_instance_id,
                            "target_unit_name": target.name,
                        }
                    ),
                )
                for owner_id, target in targets
            )
        ),
    )


def candidates(context: CommandPhaseStartEffectContext) -> tuple[TimingRuleCandidate, ...]:
    return command_army_rule_candidate(
        context,
        request_handler=request_for,
        source_rule_id=_rules.SOURCE_RULE_ID,
        hook_id=_rules.HOOK_ID,
        requirement=SequencingRequirement.MANDATORY,
    )
