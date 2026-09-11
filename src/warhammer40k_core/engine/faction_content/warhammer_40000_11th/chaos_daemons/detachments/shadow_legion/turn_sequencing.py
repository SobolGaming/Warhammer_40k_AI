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
    ENHANCEMENT_ID,
    SOURCE_RULE_ID,
    TURN_END_HOOK_ID,
    _active_player_id,
    _assigned_units,
    _destroyed_enemy_unit_ids_for_fade_unit,
    _shadow_legion_armies,
    _unit_can_enter_strategic_reserves,
    decision_recorded_this_phase,
    fade_to_darkness_option,
)


def candidates(context: TurnEndRequestContext) -> tuple[TimingRuleCandidate, ...]:
    candidates: list[TimingRuleCandidate] = []
    if type(context) is not TurnEndRequestContext:
        raise GameLifecycleError("Fade to Darkness requires a turn-end request context.")
    if context.completed_phase is not BattlePhase.FIGHT:
        return tuple(candidates)
    active_player_id = _active_player_id(context.state)
    for army in _shadow_legion_armies(context.state):
        for _assignment, unit in _assigned_units(army, enhancement_id=ENHANCEMENT_ID):
            destroyed_enemy_unit_ids = _destroyed_enemy_unit_ids_for_fade_unit(
                context, player_id=army.player_id, unit_instance_id=unit.unit_instance_id
            )
            if not destroyed_enemy_unit_ids:
                continue
            if decision_recorded_this_phase(context, unit_instance_id=unit.unit_instance_id):
                continue
            if not _unit_can_enter_strategic_reserves(
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
                            "player_id": army.player_id,
                            "source_rule_id": SOURCE_RULE_ID,
                            "hook_id": TURN_END_HOOK_ID,
                            "enhancement_id": ENHANCEMENT_ID,
                            "target_unit_instance_id": unit.unit_instance_id,
                            "destroyed_enemy_unit_instance_ids": list(destroyed_enemy_unit_ids),
                        },
                        options=(
                            fade_to_darkness_option(
                                player_id=army.player_id,
                                unit_instance_id=unit.unit_instance_id,
                                use_ability=True,
                            ),
                            fade_to_darkness_option(
                                player_id=army.player_id,
                                unit_instance_id=unit.unit_instance_id,
                                use_ability=False,
                            ),
                        ),
                    ),
                    participant_id=f"{TURN_END_HOOK_ID}:{unit.unit_instance_id}",
                    source_rule_id=SOURCE_RULE_ID,
                    requirement=SequencingRequirement.OPTIONAL,
                    next_request_id=context.state.next_decision_request_id,
                )
            )
    return tuple(candidates)
