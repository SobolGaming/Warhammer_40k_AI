from __future__ import annotations

from dataclasses import replace

from warhammer40k_core.engine.event_log import validate_json_value
from warhammer40k_core.engine.faction_content.bundle import RuntimeContentContribution
from warhammer40k_core.engine.faction_content.stratagem_activation import (
    source_backed_detachment_stratagem_activation_records,
)
from warhammer40k_core.engine.phase import BattlePhase, GameLifecycleError
from warhammer40k_core.engine.stratagems import (
    StratagemCatalogRecord,
    StratagemTargetSpec,
    StratagemTimingDescriptor,
)
from warhammer40k_core.engine.stratagems_generic_metadata import (
    COMPANION_OPTIONAL_KEY,
    COMPANION_REQUIRED_KEYWORDS_BY_TARGET_KEYWORD_KEY,
    COMPANION_REQUIRED_REINFORCEMENT_ARRIVAL_THIS_TURN_KEY,
    EFFECT_SELECTION_KIND_KEY,
    REQUIRED_NON_EMPTY_TRIGGER_CONTEXT_KEYS_KEY,
    REQUIRED_TRIGGER_CONTEXT_KEYS_KEY,
    SELECTED_FRIENDLY_COMPANION_UNIT_EFFECT_SELECTION_KIND,
    TARGET_REQUIRED_REINFORCEMENT_ARRIVAL_THIS_TURN_KEY,
    TARGET_REQUIRED_TRIGGER_CONTEXT_LIST_KEY,
)
from warhammer40k_core.engine.timing_windows import TimingTriggerKind
from warhammer40k_core.rules.source_packages.warhammer_40000_11th import (
    faction_shadow_legion_ir_support_2026_27 as shadow_legion_ir,
)

CONTRIBUTION_ID = "warhammer_40000_11th:chaos_daemons:detachment:shadow_legion:stratagems"
SHADOW_LEGION_DETACHMENT_ID = "shadow-legion"
SHADOW_LEGION_PROFILE_PREFIX = "phase17s:stratagem:chaos-daemons:shadow-legion"
CHARGE_TARGET_UNIT_IDS_CONTEXT_KEY = "charge_target_unit_instance_ids"
TARGET_REQUIRED_NOT_IN_ENGAGEMENT_RANGE = "target_forbidden_if_within_engagement_range"


def runtime_contribution() -> RuntimeContentContribution:
    return RuntimeContentContribution(
        contribution_id=CONTRIBUTION_ID,
        stratagem_records=_shadow_legion_stratagem_records(),
    )


def _shadow_legion_stratagem_records() -> tuple[StratagemCatalogRecord, ...]:
    records: list[StratagemCatalogRecord] = []
    for record in source_backed_detachment_stratagem_activation_records():
        if record.detachment_id != SHADOW_LEGION_DETACHMENT_ID:
            continue
        records.append(_record_with_static_rule_ir(record))
    return tuple(sorted(records, key=lambda record: record.record_id))


def _record_with_static_rule_ir(record: StratagemCatalogRecord) -> StratagemCatalogRecord:
    if type(record) is not StratagemCatalogRecord:
        raise GameLifecycleError("Shadow Legion Stratagem override requires catalog record.")
    profile_id = f"{SHADOW_LEGION_PROFILE_PREFIX}:{record.definition.stratagem_id}"
    rule_ir_payload = shadow_legion_ir.stratagem_activation_rule_ir_payload_by_profile_id(
        profile_id
    )
    if rule_ir_payload is None:
        raise GameLifecycleError("Shadow Legion Stratagem RuleIR payload is missing.")
    return replace(
        record,
        definition=replace(
            record.definition,
            timing=_shadow_legion_timing(record),
            target_spec=_shadow_legion_target_spec(record),
            effect_payload=validate_json_value(
                {
                    "rule_ir": rule_ir_payload,
                    **_shadow_legion_effect_metadata(record.definition.stratagem_id),
                }
            ),
        ),
    )


def _shadow_legion_timing(record: StratagemCatalogRecord) -> StratagemTimingDescriptor:
    stratagem_id = record.definition.stratagem_id
    if stratagem_id == shadow_legion_ir.SPITEFUL_DEMISE_STRATAGEM_ID:
        return StratagemTimingDescriptor(trigger_kind=TimingTriggerKind.AFTER_UNIT_DESTROYED)
    if stratagem_id == shadow_legion_ir.SHADE_PATH_STRATAGEM_ID:
        return StratagemTimingDescriptor(
            trigger_kind=TimingTriggerKind.DURING_PHASE,
            phase=BattlePhase.CHARGE,
        )
    return record.definition.timing


def _shadow_legion_target_spec(record: StratagemCatalogRecord) -> StratagemTargetSpec:
    target_spec = record.definition.target_spec
    required_keywords = target_spec.required_keywords
    if shadow_legion_ir.SHADOW_LEGION_KEYWORD not in required_keywords:
        required_keywords = tuple(
            sorted((*required_keywords, shadow_legion_ir.SHADOW_LEGION_KEYWORD))
        )
    if record.definition.stratagem_id in {
        shadow_legion_ir.ENCROACHING_DARKNESS_STRATAGEM_ID,
        shadow_legion_ir.BINDING_SHADOW_STRATAGEM_ID,
    }:
        return replace(
            target_spec,
            required_keywords=required_keywords,
            required_keywords_any=(
                shadow_legion_ir.HERETIC_ASTARTES_KEYWORD,
                shadow_legion_ir.LEGIONES_DAEMONICA_KEYWORD,
            ),
        )
    return replace(target_spec, required_keywords=required_keywords)


def _shadow_legion_effect_metadata(stratagem_id: str) -> dict[str, object]:
    if stratagem_id == shadow_legion_ir.SPITEFUL_DEMISE_STRATAGEM_ID:
        return {
            REQUIRED_TRIGGER_CONTEXT_KEYS_KEY: [
                shadow_legion_ir.SHADOW_LEGION_DESTROYED_LAST_MODEL_CONTEXT_KEY,
            ],
            REQUIRED_NON_EMPTY_TRIGGER_CONTEXT_KEYS_KEY: [
                shadow_legion_ir.SHADOW_LEGION_ENGAGED_ENEMY_UNITS_CONTEXT_KEY,
            ],
        }
    if stratagem_id == shadow_legion_ir.ENCROACHING_DARKNESS_STRATAGEM_ID:
        return {
            TARGET_REQUIRED_REINFORCEMENT_ARRIVAL_THIS_TURN_KEY: True,
            EFFECT_SELECTION_KIND_KEY: SELECTED_FRIENDLY_COMPANION_UNIT_EFFECT_SELECTION_KIND,
            COMPANION_OPTIONAL_KEY: True,
            COMPANION_REQUIRED_REINFORCEMENT_ARRIVAL_THIS_TURN_KEY: True,
            COMPANION_REQUIRED_KEYWORDS_BY_TARGET_KEYWORD_KEY: {
                shadow_legion_ir.HERETIC_ASTARTES_KEYWORD: [
                    shadow_legion_ir.LEGIONES_DAEMONICA_KEYWORD,
                ],
                shadow_legion_ir.LEGIONES_DAEMONICA_KEYWORD: [
                    shadow_legion_ir.HERETIC_ASTARTES_KEYWORD,
                ],
            },
        }
    if stratagem_id == shadow_legion_ir.SHADE_PATH_STRATAGEM_ID:
        return {
            REQUIRED_TRIGGER_CONTEXT_KEYS_KEY: [
                shadow_legion_ir.SHADOW_LEGION_CHARGING_UNIT_CONTEXT_KEY,
            ],
            TARGET_REQUIRED_TRIGGER_CONTEXT_LIST_KEY: CHARGE_TARGET_UNIT_IDS_CONTEXT_KEY,
        }
    if stratagem_id == shadow_legion_ir.BINDING_SHADOW_STRATAGEM_ID:
        return {
            TARGET_REQUIRED_NOT_IN_ENGAGEMENT_RANGE: True,
            EFFECT_SELECTION_KIND_KEY: SELECTED_FRIENDLY_COMPANION_UNIT_EFFECT_SELECTION_KIND,
            COMPANION_OPTIONAL_KEY: True,
            COMPANION_REQUIRED_KEYWORDS_BY_TARGET_KEYWORD_KEY: {
                shadow_legion_ir.HERETIC_ASTARTES_KEYWORD: [
                    shadow_legion_ir.LEGIONES_DAEMONICA_KEYWORD,
                ],
                shadow_legion_ir.LEGIONES_DAEMONICA_KEYWORD: [
                    shadow_legion_ir.HERETIC_ASTARTES_KEYWORD,
                ],
            },
        }
    return {}
