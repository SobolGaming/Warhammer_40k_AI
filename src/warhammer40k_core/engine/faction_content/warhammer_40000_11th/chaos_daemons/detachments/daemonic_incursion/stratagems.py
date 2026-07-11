from __future__ import annotations

from warhammer40k_core.engine.event_log import JsonValue, validate_json_value
from warhammer40k_core.engine.faction_content.bundle import RuntimeContentContribution
from warhammer40k_core.engine.phase import BattlePhase
from warhammer40k_core.engine.stratagems import (
    CONTROLLED_OBJECTIVE_UNIT_TARGET_POLICY_ID,
    DEEP_STRIKE_ARRIVING_TARGET_POLICY_ID,
    GENERIC_RULE_IR_STRATAGEM_HANDLER_ID,
    NOT_SELECTED_TO_FIGHT_TARGET_POLICY_ID,
    NOT_SELECTED_TO_SHOOT_TARGET_POLICY_ID,
    SELECTED_TARGET_UNIT_TARGET_POLICY_ID,
    StratagemAvailabilityKind,
    StratagemCatalogRecord,
    StratagemCategory,
    StratagemDefinition,
    StratagemRestrictionPolicy,
    StratagemTargetKind,
    StratagemTargetSpec,
    StratagemTimingDescriptor,
)
from warhammer40k_core.engine.stratagems_generic_metadata import (
    COMPANION_FORBIDDEN_IF_WITHIN_ENGAGEMENT_RANGE_KEY,
    COMPANION_REQUIRED_CONTEXTUAL_STATUS_KEY,
    COMPANION_REQUIRED_KEYWORDS_BY_TARGET_KEYWORD_KEY,
    CONTROLLED_OBJECTIVE_MARKER_EFFECT_SELECTION_KIND,
    EFFECT_SELECTION_KIND_KEY,
    SELECTED_FRIENDLY_COMPANION_UNIT_EFFECT_SELECTION_KIND,
    TARGET_CONTEXTUAL_STATUS_SHADOW_OF_CHAOS,
    TARGET_REQUIRED_CONTEXTUAL_STATUS_KEY,
)
from warhammer40k_core.engine.timing_windows import TimingTriggerKind
from warhammer40k_core.rules.source_packages.warhammer_40000_11th import (
    faction_daemonic_incursion_ir_support_2026_27 as daemonic_ir,
)
from warhammer40k_core.rules.source_packages.warhammer_40000_11th import (
    faction_generic_ir_support_2026_27 as generic_ir_support,
)

from .rule import DAEMONIC_INCURSION_DETACHMENT_ID, LEGIONES_DAEMONICA

CONTRIBUTION_ID = "warhammer_40000_11th:chaos_daemons:detachment:daemonic_incursion:stratagems"
FRIENDLY_UNIT_TARGET_POLICY_ID = "friendly_unit"
TARGET_FORBIDDEN_IF_WITHIN_ENGAGEMENT_RANGE_KEY = "target_forbidden_if_within_engagement_range"


def runtime_contribution() -> RuntimeContentContribution:
    return RuntimeContentContribution(
        contribution_id=CONTRIBUTION_ID,
        stratagem_records=(
            _corrupt_realspace_record(),
            _warp_surge_record(),
            _draught_of_terror_shooting_record(),
            _draught_of_terror_fight_record(),
            _denizens_of_the_warp_record(),
            _the_realm_of_chaos_single_record(),
            _the_realm_of_chaos_shadow_pair_record(),
            _daemonic_invulnerability_record(),
        ),
    )


def _corrupt_realspace_record() -> StratagemCatalogRecord:
    return _daemonic_stratagem_record(
        stratagem_id=daemonic_ir.CORRUPT_REALSPACE_STRATAGEM_ID,
        name="Corrupt Realspace",
        source_row_id=daemonic_ir.CORRUPT_REALSPACE_SOURCE_ROW_ID,
        coverage_descriptor_id=daemonic_ir.CORRUPT_REALSPACE_DESCRIPTOR_ID,
        category=StratagemCategory.STRATEGIC_PLOY,
        when_descriptor="Start of any Command phase.",
        target_descriptor=(
            "One friendly Legiones Daemonica unit within range of an objective marker you control."
        ),
        effect_descriptor=(
            "Select one objective marker that your unit is within range of and you "
            "control. That objective marker is Corrupted."
        ),
        timing=StratagemTimingDescriptor(
            trigger_kind=TimingTriggerKind.START_PHASE,
            phase=BattlePhase.COMMAND,
        ),
        target_policy_id=CONTROLLED_OBJECTIVE_UNIT_TARGET_POLICY_ID,
        effect_metadata={
            EFFECT_SELECTION_KIND_KEY: CONTROLLED_OBJECTIVE_MARKER_EFFECT_SELECTION_KIND,
        },
    )


def _warp_surge_record() -> StratagemCatalogRecord:
    return _daemonic_stratagem_record(
        stratagem_id=daemonic_ir.WARP_SURGE_STRATAGEM_ID,
        name="Warp Surge",
        source_row_id=daemonic_ir.WARP_SURGE_SOURCE_ROW_ID,
        coverage_descriptor_id=daemonic_ir.WARP_SURGE_DESCRIPTOR_ID,
        category=StratagemCategory.STRATEGIC_PLOY,
        when_descriptor="Start of your Charge phase.",
        target_descriptor="One friendly Legiones Daemonica unit within your Shadow of Chaos.",
        effect_descriptor="Until the end of the phase, your unit can charge after Advancing.",
        timing=StratagemTimingDescriptor(
            trigger_kind=TimingTriggerKind.START_PHASE,
            phase=BattlePhase.CHARGE,
        ),
        target_policy_id=FRIENDLY_UNIT_TARGET_POLICY_ID,
        effect_metadata={
            "requires_own_turn": True,
            TARGET_REQUIRED_CONTEXTUAL_STATUS_KEY: TARGET_CONTEXTUAL_STATUS_SHADOW_OF_CHAOS,
        },
    )


def _draught_of_terror_shooting_record() -> StratagemCatalogRecord:
    return _daemonic_stratagem_record(
        stratagem_id=daemonic_ir.DRAUGHT_OF_TERROR_STRATAGEM_ID,
        name="Draught of Terror",
        source_row_id=daemonic_ir.DRAUGHT_OF_TERROR_SOURCE_ROW_ID,
        coverage_descriptor_id=daemonic_ir.DRAUGHT_OF_TERROR_DESCRIPTOR_ID,
        category=StratagemCategory.BATTLE_TACTIC,
        when_descriptor="Your Shooting phase.",
        target_descriptor=(
            "One friendly Legiones Daemonica unit that has not been selected to shoot this phase."
        ),
        effect_descriptor=(
            "Until the end of the phase, improve the AP of weapons equipped by models "
            "in your unit by 1, and those weapons can re-roll Wound rolls against "
            "Battle-shocked units."
        ),
        timing=StratagemTimingDescriptor(
            trigger_kind=TimingTriggerKind.START_PHASE,
            phase=BattlePhase.SHOOTING,
        ),
        target_policy_id=NOT_SELECTED_TO_SHOOT_TARGET_POLICY_ID,
        effect_metadata={"requires_own_turn": True},
    )


def _draught_of_terror_fight_record() -> StratagemCatalogRecord:
    return _daemonic_stratagem_record(
        stratagem_id=daemonic_ir.DRAUGHT_OF_TERROR_STRATAGEM_ID,
        name="Draught of Terror",
        source_row_id=daemonic_ir.DRAUGHT_OF_TERROR_SOURCE_ROW_ID,
        coverage_descriptor_id=daemonic_ir.DRAUGHT_OF_TERROR_DESCRIPTOR_ID,
        category=StratagemCategory.BATTLE_TACTIC,
        when_descriptor="The Fight phase.",
        target_descriptor=(
            "One friendly Legiones Daemonica unit that has not been selected to fight this phase."
        ),
        effect_descriptor=(
            "Until the end of the phase, improve the AP of weapons equipped by models "
            "in your unit by 1, and those weapons can re-roll Wound rolls against "
            "Battle-shocked units."
        ),
        timing=StratagemTimingDescriptor(
            trigger_kind=TimingTriggerKind.START_PHASE,
            phase=BattlePhase.FIGHT,
        ),
        target_policy_id=NOT_SELECTED_TO_FIGHT_TARGET_POLICY_ID,
    )


def _denizens_of_the_warp_record() -> StratagemCatalogRecord:
    return _daemonic_stratagem_record(
        stratagem_id=daemonic_ir.DENIZENS_OF_THE_WARP_STRATAGEM_ID,
        name="Denizens of the Warp",
        source_row_id=daemonic_ir.DENIZENS_OF_THE_WARP_SOURCE_ROW_ID,
        coverage_descriptor_id=daemonic_ir.DENIZENS_OF_THE_WARP_DESCRIPTOR_ID,
        category=StratagemCategory.STRATEGIC_PLOY,
        when_descriptor="Your Movement phase.",
        target_descriptor=(
            "One friendly Legiones Daemonica unit arriving using the Deep Strike "
            "ability this phase."
        ),
        effect_descriptor=(
            "Until the end of the phase, your unit can be set up more than 6 inches "
            "horizontally away from all enemy models."
        ),
        timing=StratagemTimingDescriptor(
            trigger_kind=TimingTriggerKind.START_PHASE,
            phase=BattlePhase.MOVEMENT,
        ),
        target_policy_id=DEEP_STRIKE_ARRIVING_TARGET_POLICY_ID,
        effect_metadata={"requires_own_turn": True},
    )


def _the_realm_of_chaos_single_record() -> StratagemCatalogRecord:
    return _the_realm_of_chaos_record(
        record_suffix="single",
        target_descriptor=(
            "One friendly Legiones Daemonica unit that is not within Engagement Range "
            "of one or more enemy units."
        ),
        effect_metadata={
            "requires_opponent_turn": True,
            TARGET_FORBIDDEN_IF_WITHIN_ENGAGEMENT_RANGE_KEY: True,
        },
    )


def _the_realm_of_chaos_shadow_pair_record() -> StratagemCatalogRecord:
    return _the_realm_of_chaos_record(
        record_suffix="shadow-pair",
        target_descriptor=(
            "Up to two friendly Legiones Daemonica units within your Shadow of Chaos "
            "that are not within Engagement Range of one or more enemy units."
        ),
        effect_metadata={
            "requires_opponent_turn": True,
            TARGET_FORBIDDEN_IF_WITHIN_ENGAGEMENT_RANGE_KEY: True,
            TARGET_REQUIRED_CONTEXTUAL_STATUS_KEY: TARGET_CONTEXTUAL_STATUS_SHADOW_OF_CHAOS,
            EFFECT_SELECTION_KIND_KEY: SELECTED_FRIENDLY_COMPANION_UNIT_EFFECT_SELECTION_KIND,
            COMPANION_FORBIDDEN_IF_WITHIN_ENGAGEMENT_RANGE_KEY: True,
            COMPANION_REQUIRED_CONTEXTUAL_STATUS_KEY: TARGET_CONTEXTUAL_STATUS_SHADOW_OF_CHAOS,
            COMPANION_REQUIRED_KEYWORDS_BY_TARGET_KEYWORD_KEY: {
                LEGIONES_DAEMONICA: [LEGIONES_DAEMONICA],
            },
        },
    )


def _the_realm_of_chaos_record(
    *,
    record_suffix: str,
    target_descriptor: str,
    effect_metadata: dict[str, JsonValue],
) -> StratagemCatalogRecord:
    return _daemonic_stratagem_record(
        stratagem_id=daemonic_ir.THE_REALM_OF_CHAOS_STRATAGEM_ID,
        name="The Realm of Chaos",
        source_row_id=daemonic_ir.THE_REALM_OF_CHAOS_SOURCE_ROW_ID,
        coverage_descriptor_id=daemonic_ir.THE_REALM_OF_CHAOS_DESCRIPTOR_ID,
        category=StratagemCategory.BATTLE_TACTIC,
        when_descriptor="End of your opponent's turn.",
        target_descriptor=target_descriptor,
        effect_descriptor=(
            "Remove the targeted units from the battlefield and place them into "
            "Strategic Reserves. They arrive in your next Movement phase using Deep Strike."
        ),
        timing=StratagemTimingDescriptor(trigger_kind=TimingTriggerKind.END_TURN),
        target_policy_id=FRIENDLY_UNIT_TARGET_POLICY_ID,
        effect_metadata=effect_metadata,
        record_suffix=record_suffix,
    )


def _daemonic_invulnerability_record() -> StratagemCatalogRecord:
    return _daemonic_stratagem_record(
        stratagem_id=daemonic_ir.DAEMONIC_INVULNERABILITY_STRATAGEM_ID,
        name="Daemonic Invulnerability",
        source_row_id=daemonic_ir.DAEMONIC_INVULNERABILITY_SOURCE_ROW_ID,
        coverage_descriptor_id=daemonic_ir.DAEMONIC_INVULNERABILITY_DESCRIPTOR_ID,
        category=StratagemCategory.BATTLE_TACTIC,
        when_descriptor=(
            "Your opponent's Shooting phase, just after an enemy unit has selected its targets."
        ),
        target_descriptor="One friendly Legiones Daemonica unit selected as a target.",
        effect_descriptor=(
            "Until the end of the phase, invulnerable saving throws of 1 for models "
            "in your unit can be re-rolled."
        ),
        timing=StratagemTimingDescriptor(
            trigger_kind=TimingTriggerKind.AFTER_UNIT_SELECTED_AS_TARGET,
            phase=BattlePhase.SHOOTING,
        ),
        target_policy_id=SELECTED_TARGET_UNIT_TARGET_POLICY_ID,
        effect_metadata={"requires_opponent_turn": True},
    )


def _daemonic_stratagem_record(
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
    effect_metadata: dict[str, JsonValue] | None = None,
    record_suffix: str | None = None,
) -> StratagemCatalogRecord:
    phase_suffix = "any" if timing.phase is None else timing.phase.value
    record_suffix_fragment = "" if record_suffix is None else f":{record_suffix}"
    return StratagemCatalogRecord(
        record_id=(
            f"{CONTRIBUTION_ID}:{stratagem_id}:{timing.trigger_kind.value}:"
            f"phase:{phase_suffix}{record_suffix_fragment}"
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
                required_faction_keywords=(LEGIONES_DAEMONICA,),
            ),
            handler_id=GENERIC_RULE_IR_STRATAGEM_HANDLER_ID,
            effect_payload=_effect_payload(
                coverage_descriptor_id=coverage_descriptor_id,
                metadata={} if effect_metadata is None else effect_metadata,
            ),
        ),
        availability_kind=StratagemAvailabilityKind.DETACHMENT,
        detachment_id=DAEMONIC_INCURSION_DETACHMENT_ID,
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
