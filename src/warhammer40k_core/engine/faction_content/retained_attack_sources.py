"""Source-backed activation records for the reviewed retained attack Stratagem."""

from __future__ import annotations

from functools import cache

from warhammer40k_core.engine.event_log import validate_json_value
from warhammer40k_core.engine.phase import BattlePhase
from warhammer40k_core.engine.stratagems import (
    GENERIC_RULE_IR_STRATAGEM_HANDLER_ID,
    StratagemAvailabilityKind,
    StratagemCatalogRecord,
    StratagemCategory,
    StratagemDefinition,
    StratagemRestrictionPolicy,
    StratagemTargetKind,
    StratagemTargetSpec,
    StratagemTimingDescriptor,
)
from warhammer40k_core.engine.timing_windows import TimingTriggerKind
from warhammer40k_core.rules.source_packages.warhammer_40000_11th import (
    retained_attack_sources_2026_09 as source_data,
)


@cache
def retained_attack_stratagem_records() -> tuple[StratagemCatalogRecord, ...]:
    profile = source_data.stratagem_profile()
    rule_ir = source_data.rule_ir_for_source(profile.source_id)
    return tuple(
        StratagemCatalogRecord(
            record_id=f"{profile.source_id}:phase:{phase}",
            definition=StratagemDefinition(
                stratagem_id=profile.stratagem_id,
                name=profile.name,
                source_id=profile.source_id,
                command_point_cost=profile.command_point_cost,
                category=StratagemCategory(profile.category),
                when_descriptor=rule_ir.normalized_text,
                target_descriptor=rule_ir.normalized_text,
                effect_descriptor=rule_ir.normalized_text,
                restrictions_descriptor=(
                    "Selected friendly target; source-backed phase and keyword restrictions."
                ),
                timing=StratagemTimingDescriptor(
                    trigger_kind=TimingTriggerKind(profile.trigger_kind), phase=BattlePhase(phase)
                ),
                restriction_policy=StratagemRestrictionPolicy(same_unit_target_per_phase=True),
                target_spec=StratagemTargetSpec(
                    target_kind=StratagemTargetKind.FRIENDLY_UNIT,
                    enumerable=True,
                    target_policy_id=profile.target_policy_id,
                    required_keywords=profile.required_keywords,
                    required_faction_keywords=profile.required_faction_keywords,
                ),
                handler_id=GENERIC_RULE_IR_STRATAGEM_HANDLER_ID,
                effect_payload={
                    "rule_ir": validate_json_value(rule_ir.to_payload()),
                    "requires_opponent_turn": phase in profile.opponent_turn_phases,
                },
            ),
            availability_kind=StratagemAvailabilityKind.DETACHMENT,
            detachment_id=profile.detachment_id,
        )
        for phase in profile.phases
    )
