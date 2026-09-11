from __future__ import annotations

from dataclasses import replace
from functools import partial

from warhammer40k_core.engine.catalog_rule_group_sequencing import selected_target_group_participant
from warhammer40k_core.engine.catalog_selected_target_decisions import (
    resolved_shooting_start_group_keys as _resolved_shooting_start_group_keys,
)
from warhammer40k_core.engine.catalog_selected_target_decisions import selected_target_request
from warhammer40k_core.engine.catalog_selected_target_effects import (
    CATALOG_SELECTED_TARGET_EFFECT_SELECTED_EVENT,
    CATALOG_SHOOTING_START_SELECTED_TARGET_EFFECT_SELECTED_EVENT,
    CatalogSelectedTargetEffectRuntime,
    _fight_start_selected_target_groups,
    _shooting_start_selected_target_groups,
)

# pyright: reportPrivateUsage=false
from warhammer40k_core.engine.decision_request import DecisionRequest
from warhammer40k_core.engine.fight_phase_start_hooks import (
    SELECT_FACTION_RULE_FIGHT_PHASE_START_OPTION_DECISION_TYPE,
    FightPhaseStartRequestContext,
)
from warhammer40k_core.engine.shooting_phase_start_hooks import (
    SELECT_FACTION_RULE_SHOOTING_PHASE_START_OPTION_DECISION_TYPE,
    ShootingPhaseStartRequestContext,
)
from warhammer40k_core.engine.timing_rule_candidates import TimingRuleCandidate


def fight_start_candidates(
    runtime: CatalogSelectedTargetEffectRuntime,
    context: FightPhaseStartRequestContext,
) -> tuple[TimingRuleCandidate, ...]:
    resolved = _resolved_shooting_start_group_keys(
        context.decisions,
        state=context.state,
        event_type=CATALOG_SELECTED_TARGET_EFFECT_SELECTED_EVENT,
    )
    candidates: list[TimingRuleCandidate] = []
    for group in _fight_start_selected_target_groups(
        ability_indexes_by_player_id=runtime.ability_indexes_by_player_id,
        armies=runtime.armies,
        context=context,
    ):
        if group.sort_key in resolved:
            continue
        participant = selected_target_group_participant(group)
        template = selected_target_request(
            state=context.state,
            group=group,
            decision_type=SELECT_FACTION_RULE_FIGHT_PHASE_START_OPTION_DECISION_TYPE,
            request_id=f"template:{participant.participant_id}",
        )
        candidates.append(
            TimingRuleCandidate(
                participant=participant,
                activate=partial(_materialize, context, template),
                request_template=template,
            )
        )
    return tuple(candidates)


def shooting_start_candidates(
    runtime: CatalogSelectedTargetEffectRuntime,
    context: ShootingPhaseStartRequestContext,
) -> tuple[TimingRuleCandidate, ...]:
    resolved = _resolved_shooting_start_group_keys(
        context.decisions,
        state=context.state,
        event_type=CATALOG_SHOOTING_START_SELECTED_TARGET_EFFECT_SELECTED_EVENT,
    )
    candidates: list[TimingRuleCandidate] = []
    for group in _shooting_start_selected_target_groups(
        ability_indexes_by_player_id=runtime.ability_indexes_by_player_id,
        armies=runtime.armies,
        context=context,
    ):
        if group.sort_key in resolved:
            continue
        participant = selected_target_group_participant(group)
        template = selected_target_request(
            state=context.state,
            group=group,
            decision_type=SELECT_FACTION_RULE_SHOOTING_PHASE_START_OPTION_DECISION_TYPE,
            request_id=f"template:{participant.participant_id}",
        )
        candidates.append(
            TimingRuleCandidate(
                participant=participant,
                activate=partial(_materialize, context, template),
                request_template=template,
            )
        )
    return tuple(candidates)


def _materialize(
    context: ShootingPhaseStartRequestContext | FightPhaseStartRequestContext,
    template: DecisionRequest,
) -> DecisionRequest:
    return replace(template, request_id=context.state.next_decision_request_id())
