from __future__ import annotations

from warhammer40k_core.engine.event_log import JsonValue, validate_json_value
from warhammer40k_core.engine.faction_content.bundle import RuntimeContentContribution
from warhammer40k_core.engine.phase import BattlePhase
from warhammer40k_core.engine.stratagems import (
    GENERIC_RULE_IR_STRATAGEM_HANDLER_ID,
    SELECTED_TARGET_UNIT_TARGET_POLICY_ID,
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
    faction_warptide_ir_support_2026_27 as warptide_ir,
)

from .rule import BATTLELINE, LEGIONES_DAEMONICA, PINK_HORRORS, WARPTIDE_DETACHMENT_ID

CONTRIBUTION_ID = "warhammer_40000_11th:chaos_daemons:detachment:warptide:stratagems"
FRIENDLY_UNIT_TARGET_POLICY_ID = "friendly_unit"


def runtime_contribution() -> RuntimeContentContribution:
    return RuntimeContentContribution(
        contribution_id=CONTRIBUTION_ID,
        stratagem_records=(
            _daemonic_infestation_record(),
            _soulseeing_record(),
            _incorporeal_entities_record(),
        ),
    )


def _daemonic_infestation_record() -> StratagemCatalogRecord:
    return _warptide_stratagem_record(
        stratagem_id=warptide_ir.DAEMONIC_INFESTATION_STRATAGEM_ID,
        name="Daemonic Infestation",
        source_row_id=warptide_ir.DAEMONIC_INFESTATION_SOURCE_ROW_ID,
        coverage_descriptor_id=warptide_ir.DAEMONIC_INFESTATION_DESCRIPTOR_ID,
        category=StratagemCategory.STRATEGIC_PLOY,
        when_descriptor="Your Command phase.",
        target_descriptor=(
            "One friendly Legiones Daemonica Battleline unit, excluding Pink Horrors."
        ),
        effect_descriptor="Your unit heals 3 wounds.",
        timing=StratagemTimingDescriptor(
            trigger_kind=TimingTriggerKind.START_PHASE,
            phase=BattlePhase.COMMAND,
        ),
        target_policy_id=FRIENDLY_UNIT_TARGET_POLICY_ID,
        excluded_keywords=(PINK_HORRORS,),
        effect_metadata={"requires_own_turn": True},
    )


def _soulseeing_record() -> StratagemCatalogRecord:
    return _warptide_stratagem_record(
        stratagem_id=warptide_ir.SOULSEEING_STRATAGEM_ID,
        name="Soulseeing",
        source_row_id=warptide_ir.SOULSEEING_SOURCE_ROW_ID,
        coverage_descriptor_id=warptide_ir.SOULSEEING_DESCRIPTOR_ID,
        category=StratagemCategory.STRATEGIC_PLOY,
        when_descriptor="Start of your Shooting phase.",
        target_descriptor="One friendly Legiones Daemonica Battleline unit.",
        effect_descriptor='Select one visible enemy unit within 12" of your unit.',
        timing=StratagemTimingDescriptor(
            trigger_kind=TimingTriggerKind.START_PHASE,
            phase=BattlePhase.SHOOTING,
        ),
        target_policy_id=FRIENDLY_UNIT_TARGET_POLICY_ID,
        effect_metadata={
            "requires_own_turn": True,
            EFFECT_SELECTION_KIND_KEY: VISIBLE_ENEMY_UNIT_EFFECT_SELECTION_KIND,
            VISIBLE_ENEMY_SOURCE_UNIT_CONTEXT_KEY: TARGET_BINDING_UNIT_CONTEXT_KEY,
            VISIBLE_ENEMY_RANGE_INCHES_KEY: warptide_ir.SOULSEEING_RANGE_INCHES,
        },
    )


def _incorporeal_entities_record() -> StratagemCatalogRecord:
    return _warptide_stratagem_record(
        stratagem_id=warptide_ir.INCORPOREAL_ENTITIES_STRATAGEM_ID,
        name="Incorporeal Entities",
        source_row_id=warptide_ir.INCORPOREAL_ENTITIES_SOURCE_ROW_ID,
        coverage_descriptor_id=warptide_ir.INCORPOREAL_ENTITIES_DESCRIPTOR_ID,
        category=StratagemCategory.BATTLE_TACTIC,
        when_descriptor=(
            "Your opponent's Shooting phase, when an enemy unit targets a friendly "
            "Legiones Daemonica Battleline unit."
        ),
        target_descriptor="That Legiones Daemonica Battleline unit.",
        effect_descriptor=(
            "Ranged attacks that target your unit with Strength greater than its "
            "Toughness have -1 to Wound rolls."
        ),
        timing=StratagemTimingDescriptor(
            trigger_kind=TimingTriggerKind.AFTER_UNIT_SELECTED_AS_TARGET,
            phase=BattlePhase.SHOOTING,
        ),
        target_policy_id=SELECTED_TARGET_UNIT_TARGET_POLICY_ID,
        effect_metadata={"requires_opponent_turn": True},
    )


def _warptide_stratagem_record(
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
    excluded_keywords: tuple[str, ...] = (),
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
                required_keywords=(BATTLELINE,),
                required_faction_keywords=(LEGIONES_DAEMONICA,),
                excluded_keywords=excluded_keywords,
            ),
            handler_id=GENERIC_RULE_IR_STRATAGEM_HANDLER_ID,
            effect_payload=_effect_payload(
                coverage_descriptor_id=coverage_descriptor_id,
                metadata={} if effect_metadata is None else effect_metadata,
            ),
        ),
        availability_kind=StratagemAvailabilityKind.DETACHMENT,
        detachment_id=WARPTIDE_DETACHMENT_ID,
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
