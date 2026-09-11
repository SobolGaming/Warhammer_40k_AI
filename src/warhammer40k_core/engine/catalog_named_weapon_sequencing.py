from __future__ import annotations

# pyright: reportPrivateUsage=false
from warhammer40k_core.engine.catalog_rule_consumption import (
    CatalogNamedWeaponAbilityChoiceGroup,
    CatalogNamedWeaponAbilityChoiceRuntime,
    _available_catalog_named_weapon_ability_choice_groups,
    _named_weapon_ability_choice_option_payload,
    _named_weapon_ability_choice_request_payload,
    named_weapon_ability_choice_option_label,
)
from warhammer40k_core.engine.decision_request import DecisionOption, DecisionRequest
from warhammer40k_core.engine.event_log import validate_json_value
from warhammer40k_core.engine.sequencing import SequencingRequirement
from warhammer40k_core.engine.shooting_phase_start_hooks import (
    SELECT_FACTION_RULE_SHOOTING_PHASE_START_OPTION_DECISION_TYPE,
    ShootingPhaseStartRequestContext,
)
from warhammer40k_core.engine.timing_request_candidates import timing_candidate_for_request
from warhammer40k_core.engine.timing_rule_candidates import TimingRuleCandidate


def candidates(
    runtime: CatalogNamedWeaponAbilityChoiceRuntime, context: ShootingPhaseStartRequestContext
) -> tuple[TimingRuleCandidate, ...]:
    return tuple(
        timing_candidate_for_request(
            template=group_request(context, group, request_id="template:named-weapon-choice"),
            participant_id=f"{group.record.record_id}:{group.unit.unit_instance_id}:{group.clause.clause_id}:{group.selection_group_id}",
            source_rule_id=group.record.definition.source_id,
            requirement=SequencingRequirement.MANDATORY,
            next_request_id=context.state.next_decision_request_id,
        )
        for group in _available_catalog_named_weapon_ability_choice_groups(
            ability_indexes_by_player_id=runtime.ability_indexes_by_player_id,
            armies=runtime.armies,
            context=context,
        )
    )


def group_request(
    context: ShootingPhaseStartRequestContext,
    group: CatalogNamedWeaponAbilityChoiceGroup,
    *,
    request_id: str,
) -> DecisionRequest:
    common_payload = _named_weapon_ability_choice_request_payload(
        state=context.state,
        group=group,
    )
    return DecisionRequest(
        request_id=request_id,
        decision_type=SELECT_FACTION_RULE_SHOOTING_PHASE_START_OPTION_DECISION_TYPE,
        actor_id=context.state.active_player_id,
        payload=validate_json_value(common_payload),
        options=tuple(
            DecisionOption(
                option_id=option.option_id,
                label=named_weapon_ability_choice_option_label(
                    group=group,
                    option=option,
                ),
                payload=validate_json_value(
                    _named_weapon_ability_choice_option_payload(
                        state=context.state,
                        group=group,
                        option=option,
                    )
                ),
            )
            for option in group.options
        ),
    )
