from __future__ import annotations

import hashlib
from functools import partial

from warhammer40k_core.engine import catalog_rule_consumption as _consumption
from warhammer40k_core.engine.attack_completion_sequencing import (
    resolve_attack_completion_candidates,
)
from warhammer40k_core.engine.attack_sequence_completion_hooks import (
    AttackSequenceCompletedContext,
)
from warhammer40k_core.engine.decision_request import DecisionOption, DecisionRequest
from warhammer40k_core.engine.event_log import canonical_json, validate_json_value
from warhammer40k_core.engine.phase import (
    BattlePhase,
    GameLifecycleStage,
    LifecycleStatus,
)
from warhammer40k_core.engine.sequencing import SequencingParticipant, SequencingRequirement
from warhammer40k_core.engine.timing_rule_candidates import TimingRuleCandidate


def candidates(
    runtime: _consumption.CatalogPostShootHitTargetStatusRuntime,
    context: AttackSequenceCompletedContext,
) -> tuple[TimingRuleCandidate, ...]:
    groups = _consumption.available_catalog_post_shoot_hit_target_status_groups(
        ability_indexes_by_player_id=runtime.ability_indexes_by_player_id,
        armies=runtime.armies,
        context=context,
    )
    resolved = _consumption.resolved_post_shoot_hit_target_status_group_keys(context.decisions)
    return tuple(
        TimingRuleCandidate(
            participant=_participant(group), activate=partial(_activate, context, group)
        )
        for group in groups
        if _consumption.post_shoot_hit_target_status_group_key(group) not in resolved
    )


def _participant(group: _consumption.CatalogPostShootHitTargetStatusGroup) -> SequencingParticipant:
    identity = validate_json_value(list(_consumption.post_shoot_hit_target_status_group_key(group)))
    digest = hashlib.sha256(canonical_json(identity).encode("utf-8")).hexdigest()
    return SequencingParticipant(
        participant_id=f"catalog-post-shoot-status:{digest}",
        source_rule_id=group.record.definition.source_id,
        player_id=group.attack_sequence.attacker_player_id,
        requirement=SequencingRequirement.MANDATORY,
        payload=identity,
        label=group.record.definition.name,
    )


def resolve(
    runtime: _consumption.CatalogPostShootHitTargetStatusRuntime,
    context: AttackSequenceCompletedContext,
) -> LifecycleStatus | None:
    return resolve_attack_completion_candidates(context, partial(candidates, runtime, context))


def _activate(
    context: AttackSequenceCompletedContext,
    group: _consumption.CatalogPostShootHitTargetStatusGroup,
) -> LifecycleStatus:
    common_payload = _consumption.post_shoot_hit_target_status_request_payload(
        state=context.state, group=group
    )
    request = DecisionRequest(
        request_id=context.state.next_decision_request_id(),
        decision_type=_consumption.SELECT_CATALOG_POST_SHOOT_HIT_TARGET_STATUS_DECISION_TYPE,
        actor_id=context.attack_sequence.attacker_player_id,
        payload=validate_json_value(common_payload),
        options=tuple(
            DecisionOption(
                option_id=option.option_id,
                label=_consumption.post_shoot_hit_target_status_option_label(
                    group=group, option=option
                ),
                payload=validate_json_value(
                    _consumption.post_shoot_hit_target_status_option_payload(
                        state=context.state, group=group, option=option
                    )
                ),
            )
            for option in group.options
        ),
    )
    context.decisions.request_decision(request)
    context.decisions.event_log.append(
        "catalog_post_shoot_hit_target_status_requested",
        validate_json_value(
            {
                "game_id": context.state.game_id,
                "battle_round": context.state.battle_round,
                "phase": BattlePhase.SHOOTING.value,
                "active_player_id": context.state.active_player_id,
                "player_id": context.attack_sequence.attacker_player_id,
                "hook_id": _consumption.CATALOG_IR_POST_SHOOT_HIT_TARGET_STATUS_CONSUMER_ID,
                "request_id": request.request_id,
                "catalog_record_id": group.record.record_id,
                "source_rule_id": group.record.definition.source_id,
                "clause_id": group.clause.clause_id,
                "status": group.status,
                "source_model_instance_id": group.source_model_instance_id,
                "attack_sequence_id": group.attack_sequence.sequence_id,
                "attack_sequence_completed_event_id": group.attack_sequence_completed_event_id,
                "available_target_unit_instance_ids": [
                    option.target_unit_instance_id for option in group.options
                ],
                "phase_body_status": "catalog_post_shoot_hit_target_status_pending",
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
                "player_id": context.attack_sequence.attacker_player_id,
                "pending_request_id": request.request_id,
                "phase_body_status": "catalog_post_shoot_hit_target_status_pending",
            }
        ),
    )
