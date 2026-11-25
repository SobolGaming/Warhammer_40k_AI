from __future__ import annotations

from dataclasses import replace

from warhammer40k_core.engine.event_log import validate_json_value
from warhammer40k_core.engine.faction_content.bundle import RuntimeContentContribution
from warhammer40k_core.engine.faction_content.stratagem_activation import (
    source_backed_detachment_stratagem_activation_records,
)
from warhammer40k_core.engine.phase import BattlePhase, GameLifecycleError
from warhammer40k_core.engine.stratagems import (
    TARGET_BINDING_UNIT_CONTEXT_KEY,
    VISIBLE_ENEMY_RANGE_INCHES_KEY,
    VISIBLE_ENEMY_SOURCE_UNIT_CONTEXT_KEY,
    VISIBLE_ENEMY_UNIT_EFFECT_SELECTION_KIND,
    StratagemCatalogRecord,
)
from warhammer40k_core.engine.stratagems_generic_metadata import (
    EFFECT_SELECTION_KIND_KEY,
    TARGET_FORBIDDEN_IF_FELL_BACK_THIS_TURN_KEY,
    VISIBLE_ENEMY_REQUIRES_UNENGAGED_KEY,
)
from warhammer40k_core.engine.stratagems_model import CANONICAL_FRIENDLY_RULES_UNIT_TARGET_POLICY_ID
from warhammer40k_core.engine.stratagems_requests import POST_ROLL_MOVEMENT_OPPORTUNITY_KEY
from warhammer40k_core.engine.timing_windows import TimingTriggerKind
from warhammer40k_core.rules.source_packages.warhammer_40000_11th import (
    faction_blood_legion_ir_support_2026_27 as blood_legion_ir,
)

CONTRIBUTION_ID = "warhammer_40000_11th:chaos_daemons:detachment:blood_legion:stratagems:scaffold"


def runtime_contribution() -> RuntimeContentContribution:
    return RuntimeContentContribution(
        contribution_id=CONTRIBUTION_ID,
        stratagem_records=(
            *_gore_hungry_onslaught_records(),
            _skulls_beget_blood_record(),
            _wrath_undeniable_record(),
            _fools_flight_record(),
        ),
    )


def _fools_flight_record() -> StratagemCatalogRecord:
    (record,) = tuple(
        record
        for record in source_backed_detachment_stratagem_activation_records()
        if record.detachment_id == blood_legion_ir.BLOOD_LEGION_DETACHMENT_ID
        and record.definition.stratagem_id == blood_legion_ir.FOOLS_FLIGHT_STRATAGEM_ID
    )
    definition = record.definition
    rule_ir = blood_legion_ir.coverage_rule_ir_payload_by_descriptor_id(
        blood_legion_ir.FOOLS_FLIGHT_DESCRIPTOR_ID
    )
    if rule_ir is None or (
        definition.source_id != blood_legion_ir.FOOLS_FLIGHT_SOURCE_ID
        or definition.target_descriptor != blood_legion_ir.FOOLS_FLIGHT_TARGET
        or definition.effect_descriptor != blood_legion_ir.FOOLS_FLIGHT_EFFECT
    ):
        raise GameLifecycleError("Fool's Flight requires matching faction pack RuleIR.")
    return replace(
        record,
        definition=replace(
            definition,
            timing=replace(
                definition.timing, trigger_kind=TimingTriggerKind.AFTER_ENEMY_UNIT_ENDS_FALL_BACK
            ),
            target_spec=replace(
                definition.target_spec,
                target_policy_id=CANONICAL_FRIENDLY_RULES_UNIT_TARGET_POLICY_ID,
            ),
            effect_payload=validate_json_value(
                {
                    "rule_ir": rule_ir,
                    "requires_opponent_turn": True,
                    "charge_after_enemy_fall_back_trigger_range_inches": 6,
                }
            ),
        ),
    )


def _gore_hungry_onslaught_records() -> tuple[StratagemCatalogRecord, ...]:
    records = tuple(
        record
        for record in source_backed_detachment_stratagem_activation_records()
        if record.detachment_id == blood_legion_ir.BLOOD_LEGION_DETACHMENT_ID
        and record.definition.stratagem_id == blood_legion_ir.GORE_HUNGRY_ONSLAUGHT_STRATAGEM_ID
    )
    if tuple(record.definition.timing.phase for record in records) != (
        BattlePhase.MOVEMENT,
        BattlePhase.CHARGE,
    ):
        raise GameLifecycleError("Gore-Hungry Onslaught requires Movement and Charge records.")
    rule_ir = blood_legion_ir.coverage_rule_ir_payload_by_descriptor_id(
        blood_legion_ir.GORE_HUNGRY_ONSLAUGHT_DESCRIPTOR_ID
    )
    if rule_ir is None:
        raise GameLifecycleError("Gore-Hungry Onslaught requires retained faction pack RuleIR.")
    return tuple(
        replace(
            record,
            definition=replace(
                record.definition,
                source_id=blood_legion_ir.GORE_HUNGRY_ONSLAUGHT_SOURCE_ID,
                when_descriptor=blood_legion_ir.GORE_HUNGRY_ONSLAUGHT_WHEN,
                target_descriptor=blood_legion_ir.GORE_HUNGRY_ONSLAUGHT_TARGET,
                effect_descriptor=blood_legion_ir.GORE_HUNGRY_ONSLAUGHT_EFFECT,
                timing=replace(
                    record.definition.timing, trigger_kind=TimingTriggerKind.DURING_PHASE
                ),
                target_spec=replace(
                    record.definition.target_spec,
                    target_policy_id=CANONICAL_FRIENDLY_RULES_UNIT_TARGET_POLICY_ID,
                    required_keywords=(blood_legion_ir.KHORNE_KEYWORD,),
                    required_faction_keywords=(blood_legion_ir.LEGIONES_DAEMONICA_KEYWORD,),
                ),
                effect_payload=validate_json_value(
                    {
                        "rule_ir": rule_ir,
                        "requires_own_turn": True,
                        POST_ROLL_MOVEMENT_OPPORTUNITY_KEY: True,
                    }
                ),
            ),
        )
        for record in records
    )


def _wrath_undeniable_record() -> StratagemCatalogRecord:
    (record,) = tuple(
        record
        for record in source_backed_detachment_stratagem_activation_records()
        if record.detachment_id == blood_legion_ir.BLOOD_LEGION_DETACHMENT_ID
        and record.definition.stratagem_id == blood_legion_ir.WRATH_UNDENIABLE_STRATAGEM_ID
    )
    definition = record.definition
    rule_ir = blood_legion_ir.coverage_rule_ir_payload_by_descriptor_id(
        blood_legion_ir.WRATH_UNDENIABLE_DESCRIPTOR_ID
    )
    if rule_ir is None:
        raise GameLifecycleError("Wrath Undeniable requires retained faction pack RuleIR.")
    return replace(
        record,
        definition=replace(
            definition,
            source_id=blood_legion_ir.WRATH_UNDENIABLE_SOURCE_ID,
            when_descriptor=blood_legion_ir.WRATH_UNDENIABLE_WHEN,
            target_descriptor=blood_legion_ir.WRATH_UNDENIABLE_TARGET,
            effect_descriptor=blood_legion_ir.WRATH_UNDENIABLE_EFFECT,
            target_spec=replace(
                definition.target_spec,
                required_keywords=(blood_legion_ir.KHORNE_KEYWORD,),
                required_faction_keywords=(blood_legion_ir.LEGIONES_DAEMONICA_KEYWORD,),
            ),
            effect_payload=validate_json_value({"rule_ir": rule_ir}),
        ),
    )


def _skulls_beget_blood_record() -> StratagemCatalogRecord:
    (record,) = tuple(
        record
        for record in source_backed_detachment_stratagem_activation_records()
        if record.detachment_id == blood_legion_ir.BLOOD_LEGION_DETACHMENT_ID
        and record.definition.stratagem_id == blood_legion_ir.SKULLS_BEGET_BLOOD_STRATAGEM_ID
    )
    definition = record.definition
    rule_ir = blood_legion_ir.coverage_rule_ir_payload_by_descriptor_id(
        blood_legion_ir.SKULLS_BEGET_BLOOD_DESCRIPTOR_ID
    )
    if rule_ir is None:
        raise GameLifecycleError("Skulls Beget Blood requires retained faction pack RuleIR.")
    return replace(
        record,
        definition=replace(
            definition,
            source_id=blood_legion_ir.SKULLS_BEGET_BLOOD_SOURCE_ID,
            when_descriptor=blood_legion_ir.SKULLS_BEGET_BLOOD_WHEN,
            target_descriptor=blood_legion_ir.SKULLS_BEGET_BLOOD_TARGET,
            effect_descriptor=blood_legion_ir.SKULLS_BEGET_BLOOD_EFFECT,
            timing=replace(definition.timing, trigger_kind=TimingTriggerKind.DURING_PHASE),
            target_spec=replace(
                definition.target_spec,
                target_policy_id="friendly_unit",
                required_keywords=(blood_legion_ir.KHORNE_KEYWORD,),
                required_keywords_any=("INFANTRY", "MOUNTED"),
                required_faction_keywords=(blood_legion_ir.LEGIONES_DAEMONICA_KEYWORD,),
                excluded_keywords=(),
            ),
            effect_payload=validate_json_value(
                {
                    "rule_ir": rule_ir,
                    "requires_own_turn": True,
                    TARGET_FORBIDDEN_IF_FELL_BACK_THIS_TURN_KEY: True,
                    "target_forbidden_if_within_engagement_range": True,
                    EFFECT_SELECTION_KIND_KEY: VISIBLE_ENEMY_UNIT_EFFECT_SELECTION_KIND,
                    VISIBLE_ENEMY_SOURCE_UNIT_CONTEXT_KEY: TARGET_BINDING_UNIT_CONTEXT_KEY,
                    VISIBLE_ENEMY_RANGE_INCHES_KEY: blood_legion_ir.SKULLS_BEGET_BLOOD_RANGE_INCHES,
                    VISIBLE_ENEMY_REQUIRES_UNENGAGED_KEY: True,
                }
            ),
        ),
    )
