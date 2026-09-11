from __future__ import annotations

from functools import partial

from warhammer40k_core.engine import catalog_selected_target_effects as _effects
from warhammer40k_core.engine.attack_completion_sequencing import (
    resolve_attack_completion_candidates,
)
from warhammer40k_core.engine.attack_sequence_completion_hooks import (
    AttackSequenceCompletedContext,
)
from warhammer40k_core.engine.catalog_rule_consumption import (
    CATALOG_IR_POST_SHOOT_HIT_TARGET_EFFECT_CONSUMER_ID,
)
from warhammer40k_core.engine.catalog_rule_group_sequencing import selected_target_group_participant
from warhammer40k_core.engine.catalog_selected_target_decisions import (
    SelectedTargetGroup as _SelectedTargetGroup,
)
from warhammer40k_core.engine.catalog_selected_target_decisions import (
    post_shoot_group_key as _post_shoot_group_key,
)
from warhammer40k_core.engine.catalog_selected_target_decisions import (
    resolved_post_shoot_target_effect_group_keys as _resolved_post_shoot_target_effect_group_keys,
)
from warhammer40k_core.engine.catalog_selected_target_decisions import (
    selected_target_request as _selected_target_request,
)
from warhammer40k_core.engine.event_log import validate_json_value
from warhammer40k_core.engine.phase import (
    BattlePhase,
    GameLifecycleStage,
    LifecycleStatus,
)
from warhammer40k_core.engine.timing_rule_candidates import TimingRuleCandidate


def post_shoot_candidates(
    runtime: _effects.CatalogSelectedTargetEffectRuntime, context: AttackSequenceCompletedContext
) -> tuple[TimingRuleCandidate, ...]:
    groups = _effects.post_shoot_hit_target_effect_groups(
        ability_indexes_by_player_id=runtime.ability_indexes_by_player_id,
        armies=runtime.armies,
        context=context,
    )
    resolved = _resolved_post_shoot_target_effect_group_keys(
        context.decisions,
        event_type=_effects.CATALOG_POST_SHOOT_HIT_TARGET_EFFECT_SELECTED_EVENT,
    )
    return tuple(
        TimingRuleCandidate(
            participant=selected_target_group_participant(group),
            activate=partial(_activate_post_shoot, context, group),
        )
        for group in groups
        if _post_shoot_group_key(group) not in resolved
    )


def resolve_post_shoot(
    runtime: _effects.CatalogSelectedTargetEffectRuntime, context: AttackSequenceCompletedContext
) -> LifecycleStatus | None:
    return resolve_attack_completion_candidates(
        context, partial(post_shoot_candidates, runtime, context)
    )


def _activate_post_shoot(
    context: AttackSequenceCompletedContext, group: _SelectedTargetGroup
) -> LifecycleStatus:
    request = _selected_target_request(
        state=context.state,
        group=group,
        decision_type=_effects.SELECT_CATALOG_POST_SHOOT_HIT_TARGET_EFFECT_DECISION_TYPE,
    )
    context.decisions.request_decision(request)
    context.decisions.event_log.append(
        "catalog_post_shoot_hit_target_effect_requested",
        validate_json_value(
            {
                "game_id": context.state.game_id,
                "battle_round": context.state.battle_round,
                "phase": BattlePhase.SHOOTING.value,
                "active_player_id": context.state.active_player_id,
                "player_id": group.player_id,
                "hook_id": CATALOG_IR_POST_SHOOT_HIT_TARGET_EFFECT_CONSUMER_ID,
                "request_id": request.request_id,
                "catalog_record_id": group.record.record_id,
                "source_rule_id": group.record.definition.source_id,
                "unit_instance_id": group.unit.unit_instance_id,
                "source_model_instance_id": group.source_model_instance_id,
                "selection_clause_id": group.selection_clause.clause_id,
                "attack_sequence_id": None
                if group.attack_sequence is None
                else group.attack_sequence.sequence_id,
                "attack_sequence_completed_event_id": group.attack_sequence_completed_event_id,
                "available_target_unit_instance_ids": [
                    option.target_unit_instance_id for option in group.options
                ],
                "phase_body_status": "catalog_post_shoot_hit_target_effect_pending",
            }
        ),
    )
    return LifecycleStatus.waiting_for_decision(
        stage=GameLifecycleStage.BATTLE,
        decision_request=request,
        payload=validate_json_value(
            {
                "phase": BattlePhase.SHOOTING.value,
                "battle_round": context.state.battle_round,
                "active_player_id": context.state.active_player_id,
                "player_id": group.player_id,
                "pending_request_id": request.request_id,
                "phase_body_status": "catalog_post_shoot_hit_target_effect_pending",
            }
        ),
    )
