from __future__ import annotations

# pyright: reportPrivateUsage=false
from warhammer40k_core.engine.decision_request import DecisionRequest
from warhammer40k_core.engine.fight_phase_end_hooks import (
    SELECT_FACTION_RULE_FIGHT_PHASE_END_OPTION_DECISION_TYPE,
    FightPhaseEndRequestContext,
)
from warhammer40k_core.engine.phase import BattlePhase, GameLifecycleError
from warhammer40k_core.engine.rules_units import rules_unit_view_by_id
from warhammer40k_core.engine.sequencing import SequencingRequirement
from warhammer40k_core.engine.timing_request_candidates import timing_candidate_for_request
from warhammer40k_core.engine.timing_rule_candidates import TimingRuleCandidate

from .datasheets import (
    BLOODTHIRSTER_RELENTLESS_CARNAGE_ABILITY_ID,
    RELENTLESS_CARNAGE_HOOK_ID,
    _active_player_id,
    _chaos_daemons_armies,
    _enemy_rules_unit_ids_within_source_engagement_range,
    _unit_has_datasheet_ability,
    relentless_carnage_decline_option,
    relentless_carnage_recorded_this_fight_end,
    relentless_carnage_target_option,
)


def relentless_carnage_candidates(
    context: FightPhaseEndRequestContext,
) -> tuple[TimingRuleCandidate, ...]:
    if type(context) is not FightPhaseEndRequestContext:
        raise GameLifecycleError("Relentless Carnage requires a Fight-end request context.")
    candidates: list[TimingRuleCandidate] = []
    active_player_id = _active_player_id(context.state)
    for army in _chaos_daemons_armies(context.state):
        for source_unit in army.units:
            if not _unit_has_datasheet_ability(
                source_unit,
                BLOODTHIRSTER_RELENTLESS_CARNAGE_ABILITY_ID,
            ):
                continue
            if not source_unit.alive_own_models():
                continue
            source_rules_unit = rules_unit_view_by_id(
                state=context.state,
                unit_instance_id=source_unit.unit_instance_id,
            )
            if source_rules_unit.owner_player_id != army.player_id:
                raise GameLifecycleError("Relentless Carnage rules-unit owner drift.")
            if relentless_carnage_recorded_this_fight_end(
                context=context,
                source_unit_instance_id=source_unit.unit_instance_id,
            ):
                continue
            eligible_enemy_unit_ids = _enemy_rules_unit_ids_within_source_engagement_range(
                state=context.state,
                source_unit_instance_id=source_unit.unit_instance_id,
            )
            if not eligible_enemy_unit_ids:
                continue
            template = DecisionRequest(
                request_id=f"template:{RELENTLESS_CARNAGE_HOOK_ID}:{source_unit.unit_instance_id}",
                decision_type=SELECT_FACTION_RULE_FIGHT_PHASE_END_OPTION_DECISION_TYPE,
                actor_id=army.player_id,
                payload={
                    "game_id": context.state.game_id,
                    "battle_round": context.state.battle_round,
                    "active_player_id": active_player_id,
                    "phase": BattlePhase.FIGHT.value,
                    "player_id": army.player_id,
                    "source_rule_id": BLOODTHIRSTER_RELENTLESS_CARNAGE_ABILITY_ID,
                    "hook_id": RELENTLESS_CARNAGE_HOOK_ID,
                    "source_unit_instance_id": source_unit.unit_instance_id,
                    "source_rules_unit_instance_id": source_rules_unit.unit_instance_id,
                    "eligible_enemy_unit_instance_ids": list(eligible_enemy_unit_ids),
                },
                options=(
                    relentless_carnage_decline_option(
                        game_id=context.state.game_id,
                        battle_round=context.state.battle_round,
                        active_player_id=active_player_id,
                        player_id=army.player_id,
                        source_unit_instance_id=source_unit.unit_instance_id,
                        source_rules_unit_instance_id=source_rules_unit.unit_instance_id,
                    ),
                    *(
                        relentless_carnage_target_option(
                            game_id=context.state.game_id,
                            battle_round=context.state.battle_round,
                            active_player_id=active_player_id,
                            player_id=army.player_id,
                            source_unit_instance_id=source_unit.unit_instance_id,
                            source_rules_unit_instance_id=source_rules_unit.unit_instance_id,
                            target_enemy_unit_instance_id=enemy_unit_id,
                        )
                        for enemy_unit_id in eligible_enemy_unit_ids
                    ),
                ),
            )
            candidates.append(
                timing_candidate_for_request(
                    template=template,
                    participant_id=f"{RELENTLESS_CARNAGE_HOOK_ID}:{source_unit.unit_instance_id}",
                    source_rule_id=BLOODTHIRSTER_RELENTLESS_CARNAGE_ABILITY_ID,
                    requirement=SequencingRequirement.OPTIONAL,
                    next_request_id=context.state.next_decision_request_id,
                )
            )
    return tuple(candidates)
