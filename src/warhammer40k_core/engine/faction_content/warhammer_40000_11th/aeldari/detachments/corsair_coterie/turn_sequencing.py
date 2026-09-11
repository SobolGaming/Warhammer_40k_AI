# pyright: reportPrivateUsage=false
from __future__ import annotations

from warhammer40k_core.engine.decision_request import DecisionRequest
from warhammer40k_core.engine.phase import BattlePhase, GameLifecycleError
from warhammer40k_core.engine.sequencing import SequencingRequirement
from warhammer40k_core.engine.timing_request_candidates import timing_candidate_for_request
from warhammer40k_core.engine.timing_rule_candidates import TimingRuleCandidate
from warhammer40k_core.engine.turn_end_hooks import (
    SELECT_FACTION_RULE_TURN_END_OPTION_DECISION_TYPE,
    TurnEndRequestContext,
)

from .enhancements import (
    WEBWAY_PATHSTONE_ENHANCEMENT_ID,
    WEBWAY_PATHSTONE_SOURCE_RULE_ID,
    WEBWAY_PATHSTONE_TURN_END_HOOK_ID,
    _active_player_id,
    _assigned_units,
    _corsair_coterie_armies,
    _webway_pathstone_unit_can_enter_reserves,
    webway_pathstone_decision_recorded_this_turn,
    webway_pathstone_option,
    webway_pathstone_used_this_battle,
)


def candidates(context: TurnEndRequestContext) -> tuple[TimingRuleCandidate, ...]:
    candidates: list[TimingRuleCandidate] = []
    if type(context) is not TurnEndRequestContext:
        raise GameLifecycleError("Webway Pathstone requires a turn-end request context.")
    if context.completed_phase is not BattlePhase.FIGHT:
        return tuple(candidates)
    active_player_id = _active_player_id(context.state)
    for army in _corsair_coterie_armies(context.state):
        if army.player_id == active_player_id:
            continue
        for _assignment, unit in _assigned_units(
            army, enhancement_id=WEBWAY_PATHSTONE_ENHANCEMENT_ID
        ):
            if webway_pathstone_decision_recorded_this_turn(
                context, unit_instance_id=unit.unit_instance_id
            ):
                continue
            if webway_pathstone_used_this_battle(
                context.decisions, unit_instance_id=unit.unit_instance_id
            ):
                continue
            if not _webway_pathstone_unit_can_enter_reserves(
                context.state, unit_instance_id=unit.unit_instance_id
            ):
                continue
            candidates.append(
                timing_candidate_for_request(
                    template=DecisionRequest(
                        request_id="template:turn-end-rule",
                        decision_type=SELECT_FACTION_RULE_TURN_END_OPTION_DECISION_TYPE,
                        actor_id=army.player_id,
                        payload={
                            "game_id": context.state.game_id,
                            "battle_round": context.state.battle_round,
                            "active_player_id": active_player_id,
                            "phase": context.completed_phase.value,
                            "source_rule_id": WEBWAY_PATHSTONE_SOURCE_RULE_ID,
                            "hook_id": WEBWAY_PATHSTONE_TURN_END_HOOK_ID,
                            "enhancement_id": WEBWAY_PATHSTONE_ENHANCEMENT_ID,
                            "target_unit_instance_id": unit.unit_instance_id,
                        },
                        options=(
                            webway_pathstone_option(
                                player_id=army.player_id,
                                unit_instance_id=unit.unit_instance_id,
                                use_ability=True,
                            ),
                            webway_pathstone_option(
                                player_id=army.player_id,
                                unit_instance_id=unit.unit_instance_id,
                                use_ability=False,
                            ),
                        ),
                    ),
                    participant_id=f"{WEBWAY_PATHSTONE_TURN_END_HOOK_ID}:{unit.unit_instance_id}",
                    source_rule_id=WEBWAY_PATHSTONE_SOURCE_RULE_ID,
                    requirement=SequencingRequirement.OPTIONAL,
                    next_request_id=context.state.next_decision_request_id,
                )
            )
    return tuple(candidates)
