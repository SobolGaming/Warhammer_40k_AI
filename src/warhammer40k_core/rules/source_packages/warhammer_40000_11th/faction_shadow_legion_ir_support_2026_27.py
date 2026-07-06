from __future__ import annotations

from collections.abc import Mapping
from types import MappingProxyType
from typing import cast

from warhammer40k_core.rules.rule_ir import (
    RuleClause,
    RuleClausePayload,
    RuleConditionPayload,
    RuleDurationPayload,
    RuleEffectSpecPayload,
    RuleIR,
    RuleIRPayload,
    RuleParameterPayload,
    RuleTargetSpecPayload,
)
from warhammer40k_core.rules.rule_templates import (
    DICE_ROLL_MODIFIER_TEMPLATE_ID,
    GRANT_ABILITY_TEMPLATE_ID,
    KEYWORD_GATE_TEMPLATE_ID,
)

SOURCE_PACKAGE_ID = "gw-11e-phase17e-faction-coverage-2026-27"

SHADOW_LEGION_DETACHMENT_RULE_DESCRIPTOR_ID = "phase17e:chaos-daemons:shadow-legion:rule"
SHADOW_LEGION_KEYWORD = "SHADOW LEGION"
KHORNE_KEYWORD = "KHORNE"
TZEENTCH_KEYWORD = "TZEENTCH"
NURGLE_KEYWORD = "NURGLE"
SLAANESH_KEYWORD = "SLAANESH"
UNDIVIDED_KEYWORD = "UNDIVIDED"
CAN_ADVANCE_AND_SHOOT_AND_CHARGE_ABILITY = "can_advance_and_shoot_and_charge"
SNAP_SHOOTING_TARGET_FORBIDDEN_ABILITY = "cannot_be_targeted_by_snap_shooting"
SHADOW_LEGION_DARK_PACT_LETHAL_HITS_CHOICE_ABILITY = "dark_pact_lethal_hits_choice"
SHADOW_LEGION_DARK_PACT_SUSTAINED_HITS_1_CHOICE_ABILITY = "dark_pact_sustained_hits_1_choice"
LEAPING_SHADOWS_ENHANCEMENT_ID = "000009980002"
LEAPING_SHADOWS_SOURCE_ROW_ID = "enhancement:chaos-daemons:shadow-legion:000009980002"
LEAPING_SHADOWS_ENHANCEMENT_DESCRIPTOR_ID = f"phase17e:{LEAPING_SHADOWS_SOURCE_ROW_ID}"
LEAPING_SHADOWS_SOURCE_RULE_ID = (
    "phase17f:phase17e:enhancement:chaos-daemons:shadow-legion:000009980002"
)
LEAPING_SHADOWS_SCOUTS_ABILITY = "chaos-daemons:shadow-legion:leaping-shadows:scouts-9"
MANTLE_OF_GLOOM_ENHANCEMENT_ID = "000009980003"
MANTLE_OF_GLOOM_SOURCE_ROW_ID = "enhancement:chaos-daemons:shadow-legion:000009980003"
MANTLE_OF_GLOOM_ENHANCEMENT_DESCRIPTOR_ID = f"phase17e:{MANTLE_OF_GLOOM_SOURCE_ROW_ID}"
MANTLE_OF_GLOOM_SOURCE_RULE_ID = (
    "phase17f:phase17e:enhancement:chaos-daemons:shadow-legion:000009980003"
)
MANTLE_OF_GLOOM_OBJECTIVE_CONTROL_ABILITY = (
    "chaos-daemons:shadow-legion:mantle-of-gloom:objective-control"
)
FADE_TO_DARKNESS_ENHANCEMENT_ID = "000009980004"
FADE_TO_DARKNESS_SOURCE_ROW_ID = "enhancement:chaos-daemons:shadow-legion:000009980004"
FADE_TO_DARKNESS_ENHANCEMENT_DESCRIPTOR_ID = f"phase17e:{FADE_TO_DARKNESS_SOURCE_ROW_ID}"
FADE_TO_DARKNESS_SOURCE_RULE_ID = (
    "phase17f:phase17e:enhancement:chaos-daemons:shadow-legion:000009980004"
)
FADE_TO_DARKNESS_RESERVES_ABILITY = "chaos-daemons:shadow-legion:fade-to-darkness:reserves"
MALICE_MADE_MANIFEST_ENHANCEMENT_ID = "000009980005"
MALICE_MADE_MANIFEST_SOURCE_ROW_ID = "enhancement:chaos-daemons:shadow-legion:000009980005"
MALICE_MADE_MANIFEST_ENHANCEMENT_DESCRIPTOR_ID = f"phase17e:{MALICE_MADE_MANIFEST_SOURCE_ROW_ID}"
MALICE_MADE_MANIFEST_SOURCE_RULE_ID = (
    "phase17f:phase17e:enhancement:chaos-daemons:shadow-legion:000009980005"
)
MALICE_MADE_MANIFEST_MORTAL_WOUNDS_ABILITY = (
    "chaos-daemons:shadow-legion:malice-made-manifest:mortal-wounds"
)
MALICE_MADE_MANIFEST_MORTAL_WOUNDS_SOURCE_KIND = (
    "chaos_daemons_shadow_legion_malice_made_manifest_mortal_wounds"
)


class ShadowLegionIrSupportError(ValueError):
    """Raised when static Shadow Legion RuleIR support metadata is inconsistent."""


def coverage_rule_ir_payload_by_descriptor_id(
    coverage_descriptor_id: str,
) -> RuleIRPayload | None:
    return _COVERAGE_RULE_IR_PAYLOADS_BY_DESCRIPTOR_ID.get(coverage_descriptor_id)


def coverage_rule_ir_hash_by_descriptor_id(coverage_descriptor_id: str) -> str | None:
    payload = coverage_rule_ir_payload_by_descriptor_id(coverage_descriptor_id)
    if payload is None:
        return None
    return payload["ir_hash"]


def supported_coverage_descriptor_ids() -> tuple[str, ...]:
    return tuple(sorted(_COVERAGE_RULE_IR_PAYLOADS_BY_DESCRIPTOR_ID))


def _detachment_rule_payload() -> RuleIRPayload:
    source_row_id = "chaos-daemons:shadow-legion:rule"
    normalized_text = (
        "Shadow Legion Khorne units can shoot and declare a charge in a turn in which "
        "they Advanced. Each time an attack targets a Shadow Legion Tzeentch unit, "
        "subtract 1 from the Hit roll for Shooting phase ranged attacks. Each time an "
        "attack targets a Shadow Legion Tzeentch unit, subtract 1 from the Hit roll for "
        "melee attacks. "
        "Each time an attack targets a Shadow Legion Nurgle unit, subtract 1 from the "
        "Wound roll if the Strength characteristic of that attack is greater than the "
        "Toughness characteristic of that unit. Enemy units cannot target Shadow Legion "
        "Slaanesh units with Snap Shooting attacks. Each time a Shadow Legion Undivided unit "
        "is selected to shoot or fight, it can make a Dark Pact to gain Lethal Hits until "
        "the end of the phase. Each time a Shadow Legion Undivided unit is selected to "
        "shoot or fight, it can make a Dark Pact to gain Sustained Hits 1 until the end "
        "of the phase."
    )
    return _coverage_payload(
        source_row_id,
        normalized_text,
        (
            _ability_clause(
                clause_id=_coverage_clause_id(source_row_id, "effect:001"),
                normalized_text=normalized_text,
                source_text=(
                    "Shadow Legion Khorne units can shoot and declare a charge in a turn in "
                    "which they Advanced."
                ),
                effect_text="can shoot and declare a charge in a turn in which they Advanced",
                ability=CAN_ADVANCE_AND_SHOOT_AND_CHARGE_ABILITY,
                required_keyword_sequence=(SHADOW_LEGION_KEYWORD, KHORNE_KEYWORD),
            ),
            _dice_modifier_clause(
                clause_id=_coverage_clause_id(source_row_id, "effect:002"),
                normalized_text=normalized_text,
                source_text=(
                    "Each time an attack targets a Shadow Legion Tzeentch unit, subtract 1 "
                    "from the Hit roll for Shooting phase ranged attacks"
                ),
                effect_text="subtract 1 from the Hit roll",
                roll_type="hit",
                delta=-1,
                required_keyword_sequence=(SHADOW_LEGION_KEYWORD, TZEENTCH_KEYWORD),
                extra_parameters=(
                    _parameter("attack_role", "target"),
                    _parameter("source_phase", "shooting"),
                    _parameter("weapon_scope", "ranged"),
                ),
            ),
            _dice_modifier_clause(
                clause_id=_coverage_clause_id(source_row_id, "effect:003"),
                normalized_text=normalized_text,
                source_text=(
                    "Each time an attack targets a Shadow Legion Tzeentch unit, subtract 1 "
                    "from the Hit roll for melee attacks"
                ),
                effect_text="subtract 1 from the Hit roll",
                roll_type="hit",
                delta=-1,
                required_keyword_sequence=(SHADOW_LEGION_KEYWORD, TZEENTCH_KEYWORD),
                extra_parameters=(
                    _parameter("attack_role", "target"),
                    _parameter("weapon_scope", "melee"),
                ),
            ),
            _dice_modifier_clause(
                clause_id=_coverage_clause_id(source_row_id, "effect:004"),
                normalized_text=normalized_text,
                source_text=(
                    "Each time an attack targets a Shadow Legion Nurgle unit, subtract 1 "
                    "from the Wound roll if the Strength characteristic of that attack is "
                    "greater than the Toughness characteristic of that unit."
                ),
                effect_text="subtract 1 from the Wound roll",
                roll_type="wound",
                delta=-1,
                required_keyword_sequence=(SHADOW_LEGION_KEYWORD, NURGLE_KEYWORD),
                extra_parameters=(
                    _parameter("attack_role", "target"),
                    _parameter(
                        "target_constraint",
                        "attack_strength_greater_than_target_toughness",
                    ),
                ),
            ),
            _ability_clause(
                clause_id=_coverage_clause_id(source_row_id, "effect:005"),
                normalized_text=normalized_text,
                source_text=(
                    "Enemy units cannot target Shadow Legion Slaanesh units with Snap "
                    "Shooting attacks."
                ),
                effect_text="cannot target Shadow Legion Slaanesh units with Snap Shooting",
                ability=SNAP_SHOOTING_TARGET_FORBIDDEN_ABILITY,
                required_keyword_sequence=(SHADOW_LEGION_KEYWORD, SLAANESH_KEYWORD),
            ),
            _ability_clause(
                clause_id=_coverage_clause_id(source_row_id, "effect:006"),
                normalized_text=normalized_text,
                source_text=(
                    "Each time a Shadow Legion Undivided unit is selected to shoot or fight, "
                    "it can make a Dark Pact to gain Lethal Hits until the end of the phase."
                ),
                effect_text="make a Dark Pact to gain Lethal Hits",
                ability=SHADOW_LEGION_DARK_PACT_LETHAL_HITS_CHOICE_ABILITY,
                required_keyword_sequence=(SHADOW_LEGION_KEYWORD, UNDIVIDED_KEYWORD),
            ),
            _ability_clause(
                clause_id=_coverage_clause_id(source_row_id, "effect:007"),
                normalized_text=normalized_text,
                source_text=(
                    "Each time a Shadow Legion Undivided unit is selected to shoot or fight, "
                    "it can make a Dark Pact to gain Sustained Hits 1 until the end of the phase."
                ),
                effect_text="make a Dark Pact to gain Sustained Hits 1",
                ability=SHADOW_LEGION_DARK_PACT_SUSTAINED_HITS_1_CHOICE_ABILITY,
                required_keyword_sequence=(SHADOW_LEGION_KEYWORD, UNDIVIDED_KEYWORD),
            ),
        ),
    )


def _leaping_shadows_payload() -> RuleIRPayload:
    normalized_text = "Shadow Legion bearer grants Scouts 9 to its attached rules unit."
    effect_text = "grants Scouts 9 to its attached rules unit"
    return _enhancement_ability_payload(
        source_row_id=LEAPING_SHADOWS_SOURCE_ROW_ID,
        normalized_text=normalized_text,
        source_text=effect_text,
        effect_text=effect_text,
        ability=LEAPING_SHADOWS_SCOUTS_ABILITY,
        hook_family="enhancement_effect",
    )


def _mantle_of_gloom_payload() -> RuleIRPayload:
    normalized_text = (
        "Shadow Legion bearer reduces Objective Control by 1 for enemy units within "
        "Engagement Range of its attached rules unit."
    )
    effect_text = "reduces Objective Control by 1 for enemy units within Engagement Range"
    return _enhancement_ability_payload(
        source_row_id=MANTLE_OF_GLOOM_SOURCE_ROW_ID,
        normalized_text=normalized_text,
        source_text=effect_text,
        effect_text=effect_text,
        ability=MANTLE_OF_GLOOM_OBJECTIVE_CONTROL_ABILITY,
        hook_family="objective_control_modifier",
    )


def _fade_to_darkness_payload() -> RuleIRPayload:
    normalized_text = (
        "Shadow Legion bearer can enter Strategic Reserves at the end of the Fight phase "
        "after destroying one or more enemy units."
    )
    effect_text = "can enter Strategic Reserves at the end of the Fight phase"
    return _enhancement_ability_payload(
        source_row_id=FADE_TO_DARKNESS_SOURCE_ROW_ID,
        normalized_text=normalized_text,
        source_text=effect_text,
        effect_text=effect_text,
        ability=FADE_TO_DARKNESS_RESERVES_ABILITY,
        hook_family="turn_end",
    )


def _malice_made_manifest_payload() -> RuleIRPayload:
    normalized_text = (
        "At the start of the Fight phase, Shadow Legion bearer can select an enemy unit "
        "within Engagement Range and roll one D6 to inflict mortal wounds."
    )
    effect_text = "select an enemy unit within Engagement Range and roll one D6"
    return _enhancement_ability_payload(
        source_row_id=MALICE_MADE_MANIFEST_SOURCE_ROW_ID,
        normalized_text=normalized_text,
        source_text=effect_text,
        effect_text=effect_text,
        ability=MALICE_MADE_MANIFEST_MORTAL_WOUNDS_ABILITY,
        hook_family="fight_phase_start",
    )


def _enhancement_ability_payload(
    *,
    source_row_id: str,
    normalized_text: str,
    source_text: str,
    effect_text: str,
    ability: str,
    hook_family: str,
) -> RuleIRPayload:
    return _coverage_payload(
        source_row_id,
        normalized_text,
        (
            _keyword_gate_clause(
                clause_id=_coverage_clause_id(source_row_id, "gate:001"),
                normalized_text=normalized_text,
                source_text="Shadow Legion",
                keyword_text="Shadow Legion",
                required_keyword=SHADOW_LEGION_KEYWORD,
            ),
            _ability_clause(
                clause_id=_coverage_clause_id(source_row_id, "effect:001"),
                normalized_text=normalized_text,
                source_text=source_text,
                effect_text=effect_text,
                ability=ability,
                required_keyword_sequence=(SHADOW_LEGION_KEYWORD,),
                extra_parameters=(_parameter("hook_family", hook_family),),
            ),
        ),
    )


def _keyword_gate_clause(
    *,
    clause_id: str,
    normalized_text: str,
    source_text: str,
    keyword_text: str,
    required_keyword: str,
) -> RuleClausePayload:
    return cast(
        RuleClausePayload,
        {
            "clause_id": clause_id,
            "template_id": KEYWORD_GATE_TEMPLATE_ID,
            "source_span": _span(normalized_text, source_text),
            "trigger": None,
            "conditions": [
                _keyword_gate_condition(
                    normalized_text=normalized_text,
                    keyword_text=keyword_text,
                    required_keyword=required_keyword,
                )
            ],
            "target": None,
            "effects": [],
            "duration": None,
            "unsupported_reason": None,
            "diagnostics": [],
        },
    )


def _keyword_gate_condition(
    *,
    normalized_text: str,
    keyword_text: str,
    required_keyword: str,
) -> RuleConditionPayload:
    return cast(
        RuleConditionPayload,
        {
            "kind": "keyword_gate",
            "source_span": _span(normalized_text, keyword_text),
            "parameters": [_parameter("required_keyword", required_keyword)],
        },
    )


def _coverage_payload(
    source_row_id: str,
    normalized_text: str,
    clauses: tuple[RuleClausePayload, ...],
) -> RuleIRPayload:
    source_id = f"{SOURCE_PACKAGE_ID}:phase17e:{source_row_id}:source-text"
    return _payload(
        source_id,
        source_id,
        normalized_text,
        clauses,
        "phase17c-rule-parser-v1",
    )


def _payload(
    rule_id: str,
    source_id: str,
    normalized_text: str,
    clauses: tuple[RuleClausePayload, ...],
    parser_version: str,
) -> RuleIRPayload:
    return RuleIR(
        rule_id=rule_id,
        source_id=source_id,
        normalized_text=normalized_text,
        parser_version=parser_version,
        schema_version="phase17c-rule-ir-v1",
        clauses=tuple(RuleClause.from_payload(clause) for clause in clauses),
        diagnostics=(),
    ).to_payload()


def _ability_clause(
    *,
    clause_id: str,
    normalized_text: str,
    source_text: str,
    effect_text: str,
    ability: str,
    required_keyword_sequence: tuple[str, ...],
    extra_parameters: tuple[RuleParameterPayload, ...] = (),
) -> RuleClausePayload:
    return _effect_clause(
        clause_id=clause_id,
        template_id=GRANT_ABILITY_TEMPLATE_ID,
        normalized_text=normalized_text,
        source_text=source_text,
        target=_target("this_unit", normalized_text, source_text),
        effects=(
            _effect(
                "grant_ability",
                normalized_text,
                effect_text,
                (
                    _parameter("ability", ability),
                    _parameter("required_keyword_sequence", required_keyword_sequence),
                    *extra_parameters,
                ),
            ),
        ),
        duration=_permanent_duration(normalized_text),
    )


def _dice_modifier_clause(
    *,
    clause_id: str,
    normalized_text: str,
    source_text: str,
    effect_text: str,
    roll_type: str,
    delta: int,
    required_keyword_sequence: tuple[str, ...],
    extra_parameters: tuple[RuleParameterPayload, ...],
) -> RuleClausePayload:
    return _effect_clause(
        clause_id=clause_id,
        template_id=DICE_ROLL_MODIFIER_TEMPLATE_ID,
        normalized_text=normalized_text,
        source_text=source_text,
        target=_target("this_unit", normalized_text, source_text),
        effects=(
            _effect(
                "modify_dice_roll",
                normalized_text,
                effect_text,
                (
                    _parameter("roll_type", roll_type),
                    _parameter("delta", delta),
                    _parameter("required_keyword_sequence", required_keyword_sequence),
                    *extra_parameters,
                ),
            ),
        ),
        duration=_permanent_duration(normalized_text),
    )


def _effect_clause(
    *,
    clause_id: str,
    template_id: str,
    normalized_text: str,
    source_text: str,
    target: RuleTargetSpecPayload | None,
    effects: tuple[RuleEffectSpecPayload, ...],
    duration: RuleDurationPayload | None,
) -> RuleClausePayload:
    return cast(
        RuleClausePayload,
        {
            "clause_id": clause_id,
            "template_id": template_id,
            "source_span": _span(normalized_text, source_text),
            "trigger": None,
            "conditions": [],
            "target": target,
            "effects": list(effects),
            "duration": duration,
            "unsupported_reason": None,
            "diagnostics": [],
        },
    )


def _effect(
    kind: str,
    normalized_text: str,
    source_text: str,
    parameters: tuple[RuleParameterPayload, ...],
) -> RuleEffectSpecPayload:
    return cast(
        RuleEffectSpecPayload,
        {
            "kind": kind,
            "source_span": _span(normalized_text, source_text),
            "parameters": list(parameters),
        },
    )


def _target(
    kind: str,
    normalized_text: str,
    source_text: str,
) -> RuleTargetSpecPayload:
    return cast(
        RuleTargetSpecPayload,
        {
            "kind": kind,
            "source_span": _span(normalized_text, source_text),
            "parameters": [],
        },
    )


def _permanent_duration(normalized_text: str) -> RuleDurationPayload:
    return cast(
        RuleDurationPayload,
        {
            "kind": "permanent",
            "source_span": _span(normalized_text, normalized_text),
            "parameters": [],
        },
    )


def _parameter(key: str, value: object) -> RuleParameterPayload:
    return cast(RuleParameterPayload, {"key": key, "value": value})


def _span(normalized_text: str, source_text: str) -> dict[str, str | int]:
    start = normalized_text.index(source_text)
    return {"text": source_text, "start": start, "end": start + len(source_text)}


def _coverage_clause_id(source_row_id: str, suffix: str) -> str:
    return f"{SOURCE_PACKAGE_ID}:phase17e:{source_row_id}:source-text:{suffix}"


def _coverage_payloads() -> Mapping[str, RuleIRPayload]:
    return MappingProxyType(
        {
            SHADOW_LEGION_DETACHMENT_RULE_DESCRIPTOR_ID: _detachment_rule_payload(),
            LEAPING_SHADOWS_ENHANCEMENT_DESCRIPTOR_ID: _leaping_shadows_payload(),
            MANTLE_OF_GLOOM_ENHANCEMENT_DESCRIPTOR_ID: _mantle_of_gloom_payload(),
            FADE_TO_DARKNESS_ENHANCEMENT_DESCRIPTOR_ID: _fade_to_darkness_payload(),
            MALICE_MADE_MANIFEST_ENHANCEMENT_DESCRIPTOR_ID: _malice_made_manifest_payload(),
        }
    )


_COVERAGE_RULE_IR_PAYLOADS_BY_DESCRIPTOR_ID = _coverage_payloads()
