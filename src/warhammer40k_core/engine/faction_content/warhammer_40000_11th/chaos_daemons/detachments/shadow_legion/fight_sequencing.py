from __future__ import annotations

# pyright: reportPrivateUsage=false
from warhammer40k_core.engine.decision_request import DecisionRequest
from warhammer40k_core.engine.fight_phase_start_hooks import (
    SELECT_FACTION_RULE_FIGHT_PHASE_START_OPTION_DECISION_TYPE,
    FightPhaseStartRequestContext,
)
from warhammer40k_core.engine.phase import BattlePhase, GameLifecycleError
from warhammer40k_core.engine.rules_units import rules_unit_view_by_id
from warhammer40k_core.engine.sequencing import SequencingRequirement
from warhammer40k_core.engine.timing_request_candidates import timing_candidate_for_request
from warhammer40k_core.engine.timing_rule_candidates import TimingRuleCandidate

from .enhancements import (
    MALICE_MADE_MANIFEST_ENHANCEMENT_ID,
    MALICE_MADE_MANIFEST_HOOK_ID,
    MALICE_MADE_MANIFEST_SOURCE_RULE_ID,
    SHADOW_LEGION_KEYWORD,
    _active_player_id,
    _assigned_units,
    _enemy_rules_unit_ids_within_engagement_range,
    _shadow_legion_armies,
    _unit_has_keyword,
    malice_made_manifest_recorded_this_fight_start,
    malice_made_manifest_target_option,
)


def malice_made_manifest_candidates(
    context: FightPhaseStartRequestContext,
) -> tuple[TimingRuleCandidate, ...]:
    if type(context) is not FightPhaseStartRequestContext:
        raise GameLifecycleError("Malice Made Manifest requires a Fight-start context.")
    if context.state.current_battle_phase is not BattlePhase.FIGHT:
        return ()
    candidates: list[TimingRuleCandidate] = []
    active_player_id = _active_player_id(context.state)
    for army in _shadow_legion_armies(context.state):
        for _assignment, unit in _assigned_units(
            army,
            enhancement_id=MALICE_MADE_MANIFEST_ENHANCEMENT_ID,
        ):
            if not _unit_has_keyword(unit, SHADOW_LEGION_KEYWORD):
                raise GameLifecycleError("Malice Made Manifest requires a Shadow Legion model.")
            bearer_rules_unit = rules_unit_view_by_id(
                state=context.state,
                unit_instance_id=unit.unit_instance_id,
            )
            if bearer_rules_unit.owner_player_id != army.player_id:
                raise GameLifecycleError("Malice Made Manifest rules unit owner drift.")
            if malice_made_manifest_recorded_this_fight_start(
                context=context,
                bearer_rules_unit_instance_id=bearer_rules_unit.unit_instance_id,
            ):
                continue
            eligible_enemy_unit_ids = _enemy_rules_unit_ids_within_engagement_range(
                state=context.state,
                bearer_unit_instance_id=unit.unit_instance_id,
            )
            if not eligible_enemy_unit_ids:
                continue
            template = DecisionRequest(
                request_id=f"template:{MALICE_MADE_MANIFEST_HOOK_ID}:{unit.unit_instance_id}",
                decision_type=SELECT_FACTION_RULE_FIGHT_PHASE_START_OPTION_DECISION_TYPE,
                actor_id=army.player_id,
                payload={
                    "game_id": context.state.game_id,
                    "battle_round": context.state.battle_round,
                    "active_player_id": active_player_id,
                    "phase": BattlePhase.FIGHT.value,
                    "player_id": army.player_id,
                    "source_rule_id": MALICE_MADE_MANIFEST_SOURCE_RULE_ID,
                    "hook_id": MALICE_MADE_MANIFEST_HOOK_ID,
                    "enhancement_id": MALICE_MADE_MANIFEST_ENHANCEMENT_ID,
                    "bearer_unit_instance_id": unit.unit_instance_id,
                    "bearer_rules_unit_instance_id": bearer_rules_unit.unit_instance_id,
                    "eligible_enemy_unit_instance_ids": list(eligible_enemy_unit_ids),
                },
                options=tuple(
                    malice_made_manifest_target_option(
                        game_id=context.state.game_id,
                        battle_round=context.state.battle_round,
                        active_player_id=active_player_id,
                        player_id=army.player_id,
                        bearer_unit_instance_id=unit.unit_instance_id,
                        bearer_rules_unit_instance_id=bearer_rules_unit.unit_instance_id,
                        target_enemy_unit_instance_id=enemy_unit_id,
                    )
                    for enemy_unit_id in eligible_enemy_unit_ids
                ),
            )
            candidates.append(
                timing_candidate_for_request(
                    template=template,
                    participant_id=f"{MALICE_MADE_MANIFEST_HOOK_ID}:{unit.unit_instance_id}",
                    source_rule_id=MALICE_MADE_MANIFEST_SOURCE_RULE_ID,
                    requirement=SequencingRequirement.MANDATORY,
                    next_request_id=context.state.next_decision_request_id,
                )
            )
    return tuple(candidates)
