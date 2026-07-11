from __future__ import annotations

from warhammer40k_core.engine.event_log import JsonValue, validate_json_value
from warhammer40k_core.engine.faction_content.bundle import RuntimeContentContribution
from warhammer40k_core.engine.phase import BattlePhase
from warhammer40k_core.engine.stratagems import (
    CORE_COUNTEROFFENSIVE_HANDLER_ID,
    COUNTEROFFENSIVE_TARGET_POLICY_ID,
    GENERIC_RULE_IR_STRATAGEM_HANDLER_ID,
    SELECTED_TO_FIGHT_CHARGED_TARGET_POLICY_ID,
    SELECTED_TO_SHOOT_TARGET_POLICY_ID,
    TARGET_BINDING_UNIT_CONTEXT_KEY,
    VISIBLE_ENEMY_RANGE_INCHES_KEY,
    VISIBLE_ENEMY_SOURCE_UNIT_CONTEXT_KEY,
    VISIBLE_ENEMY_UNIT_EFFECT_SELECTION_KIND,
    StratagemAvailabilityKind,
    StratagemCatalogRecord,
    StratagemCategory,
    StratagemDefinition,
    StratagemRestrictionPolicy,
    StratagemTargetKind,
    StratagemTargetSpec,
    StratagemTimingDescriptor,
)
from warhammer40k_core.engine.stratagems_generic_metadata import EFFECT_SELECTION_KIND_KEY
from warhammer40k_core.engine.timing_windows import TimingTriggerKind
from warhammer40k_core.rules.source_packages.warhammer_40000_11th import (
    faction_generic_ir_support_2026_27 as generic_ir_support,
)
from warhammer40k_core.rules.source_packages.warhammer_40000_11th import (
    faction_lords_of_the_warp_ir_support_2026_27 as lords_ir,
)

from .rule import (
    CHARACTER,
    KHORNE,
    LEGIONES_DAEMONICA,
    LORDS_OF_THE_WARP_DETACHMENT_ID,
    MONSTER,
    NURGLE,
    SLAANESH,
    TZEENTCH,
)

CONTRIBUTION_ID = "warhammer_40000_11th:chaos_daemons:detachment:lords_of_the_warp:stratagems"
FRIENDLY_UNIT_TARGET_POLICY_ID = "friendly_unit"


def runtime_contribution() -> RuntimeContentContribution:
    return RuntimeContentContribution(
        contribution_id=CONTRIBUTION_ID,
        stratagem_records=(
            _carnival_of_excess_record(),
            _call_to_murder_record(),
            _bilious_blessing_record(),
            _skirling_magicks_record(),
        ),
    )


def _carnival_of_excess_record() -> StratagemCatalogRecord:
    return _lords_stratagem_record(
        stratagem_id=lords_ir.CARNIVAL_OF_EXCESS_STRATAGEM_ID,
        name="Carnival of Excess",
        source_row_id=lords_ir.CARNIVAL_OF_EXCESS_SOURCE_ROW_ID,
        coverage_descriptor_id=lords_ir.CARNIVAL_OF_EXCESS_DESCRIPTOR_ID,
        category=StratagemCategory.EPIC_DEED,
        when_descriptor="Fight phase, when an enemy unit has fought.",
        target_descriptor=(
            "One friendly Legiones Daemonica Character Slaanesh unit, excluding Monster units, "
            "that has not been selected to fight this phase."
        ),
        effect_descriptor=(
            "Your unit has Fights First and must be the next unit you select to fight."
        ),
        timing=StratagemTimingDescriptor(
            trigger_kind=TimingTriggerKind.JUST_AFTER_ENEMY_UNIT_HAS_FOUGHT,
            phase=BattlePhase.FIGHT,
        ),
        target_policy_id=COUNTEROFFENSIVE_TARGET_POLICY_ID,
        handler_id=CORE_COUNTEROFFENSIVE_HANDLER_ID,
        required_keywords=(CHARACTER, SLAANESH),
    )


def _call_to_murder_record() -> StratagemCatalogRecord:
    return _lords_stratagem_record(
        stratagem_id=lords_ir.CALL_TO_MURDER_STRATAGEM_ID,
        name="Call to Murder",
        source_row_id=lords_ir.CALL_TO_MURDER_SOURCE_ROW_ID,
        coverage_descriptor_id=lords_ir.CALL_TO_MURDER_DESCRIPTOR_ID,
        category=StratagemCategory.EPIC_DEED,
        when_descriptor=(
            "Fight phase, when a friendly Legiones Daemonica Khorne Character unit, "
            "excluding Monster units, that made a charge move this turn is selected to fight."
        ),
        target_descriptor="That Legiones Daemonica Character Khorne unit.",
        effect_descriptor="Your unit's melee attacks have +1 Attacks.",
        timing=StratagemTimingDescriptor(
            trigger_kind=TimingTriggerKind.JUST_AFTER_FRIENDLY_UNIT_SELECTED_TO_FIGHT,
            phase=BattlePhase.FIGHT,
        ),
        target_policy_id=SELECTED_TO_FIGHT_CHARGED_TARGET_POLICY_ID,
        handler_id=GENERIC_RULE_IR_STRATAGEM_HANDLER_ID,
        required_keywords=(CHARACTER, KHORNE),
    )


def _bilious_blessing_record() -> StratagemCatalogRecord:
    return _lords_stratagem_record(
        stratagem_id=lords_ir.BILIOUS_BLESSING_STRATAGEM_ID,
        name="Bilious Blessing",
        source_row_id=lords_ir.BILIOUS_BLESSING_SOURCE_ROW_ID,
        coverage_descriptor_id=lords_ir.BILIOUS_BLESSING_DESCRIPTOR_ID,
        category=StratagemCategory.EPIC_DEED,
        when_descriptor="Start of your Shooting phase.",
        target_descriptor=(
            "One friendly Legiones Daemonica Character Nurgle unit, excluding Monster units."
        ),
        effect_descriptor='Select one visible enemy unit within 8" of your unit and roll seven D6.',
        timing=StratagemTimingDescriptor(
            trigger_kind=TimingTriggerKind.START_PHASE,
            phase=BattlePhase.SHOOTING,
        ),
        target_policy_id=FRIENDLY_UNIT_TARGET_POLICY_ID,
        handler_id=GENERIC_RULE_IR_STRATAGEM_HANDLER_ID,
        required_keywords=(CHARACTER, NURGLE),
        effect_metadata={
            "requires_own_turn": True,
            EFFECT_SELECTION_KIND_KEY: VISIBLE_ENEMY_UNIT_EFFECT_SELECTION_KIND,
            VISIBLE_ENEMY_SOURCE_UNIT_CONTEXT_KEY: TARGET_BINDING_UNIT_CONTEXT_KEY,
            VISIBLE_ENEMY_RANGE_INCHES_KEY: lords_ir.BILIOUS_BLESSING_RANGE_INCHES,
        },
    )


def _skirling_magicks_record() -> StratagemCatalogRecord:
    return _lords_stratagem_record(
        stratagem_id=lords_ir.SKIRLING_MAGICKS_STRATAGEM_ID,
        name="Skirling Magicks",
        source_row_id=lords_ir.SKIRLING_MAGICKS_SOURCE_ROW_ID,
        coverage_descriptor_id=lords_ir.SKIRLING_MAGICKS_DESCRIPTOR_ID,
        category=StratagemCategory.EPIC_DEED,
        when_descriptor=(
            "Your Shooting phase, when a friendly Legiones Daemonica Character Tzeentch unit, "
            "excluding Monster units, is selected to shoot."
        ),
        target_descriptor="That Legiones Daemonica Character Tzeentch unit.",
        effect_descriptor="Your unit's ranged attacks have Lethal Hits.",
        timing=StratagemTimingDescriptor(
            trigger_kind=TimingTriggerKind.JUST_AFTER_FRIENDLY_UNIT_SELECTED_TO_SHOOT,
            phase=BattlePhase.SHOOTING,
        ),
        target_policy_id=SELECTED_TO_SHOOT_TARGET_POLICY_ID,
        handler_id=GENERIC_RULE_IR_STRATAGEM_HANDLER_ID,
        required_keywords=(CHARACTER, TZEENTCH),
        effect_metadata={"requires_own_turn": True},
    )


def _lords_stratagem_record(
    *,
    stratagem_id: str,
    name: str,
    source_row_id: str,
    coverage_descriptor_id: str,
    category: StratagemCategory,
    when_descriptor: str,
    target_descriptor: str,
    effect_descriptor: str,
    timing: StratagemTimingDescriptor,
    target_policy_id: str,
    handler_id: str,
    required_keywords: tuple[str, ...],
    effect_metadata: dict[str, JsonValue] | None = None,
) -> StratagemCatalogRecord:
    phase_suffix = "any" if timing.phase is None else timing.phase.value
    return StratagemCatalogRecord(
        record_id=(
            f"{CONTRIBUTION_ID}:{stratagem_id}:{timing.trigger_kind.value}:phase:{phase_suffix}"
        ),
        definition=StratagemDefinition(
            stratagem_id=stratagem_id,
            name=name,
            source_id=_stratagem_source_rule_id(source_row_id),
            command_point_cost=1,
            category=category,
            when_descriptor=when_descriptor,
            target_descriptor=target_descriptor,
            effect_descriptor=effect_descriptor,
            restrictions_descriptor="matched play same stratagem per phase",
            timing=timing,
            restriction_policy=StratagemRestrictionPolicy(same_unit_target_per_phase=True),
            target_spec=StratagemTargetSpec(
                target_kind=StratagemTargetKind.FRIENDLY_UNIT,
                enumerable=True,
                target_policy_id=target_policy_id,
                required_keywords=required_keywords,
                required_faction_keywords=(LEGIONES_DAEMONICA,),
                excluded_keywords=(MONSTER,),
            ),
            handler_id=handler_id,
            effect_payload=_effect_payload(
                coverage_descriptor_id=coverage_descriptor_id,
                metadata={} if effect_metadata is None else effect_metadata,
            ),
        ),
        availability_kind=StratagemAvailabilityKind.DETACHMENT,
        detachment_id=LORDS_OF_THE_WARP_DETACHMENT_ID,
        disabled=False,
    )


def _effect_payload(
    *,
    coverage_descriptor_id: str,
    metadata: dict[str, JsonValue],
) -> JsonValue:
    rule_ir = generic_ir_support.generic_rule_ir_by_coverage_descriptor_id(coverage_descriptor_id)
    return validate_json_value(
        {
            "rule_ir": rule_ir.to_payload(),
            **metadata,
        }
    )


def _stratagem_source_rule_id(source_row_id: str) -> str:
    return f"phase17f:phase17e:{source_row_id}"
