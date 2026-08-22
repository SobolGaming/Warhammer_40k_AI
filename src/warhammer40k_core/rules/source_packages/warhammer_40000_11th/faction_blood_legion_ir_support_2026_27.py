from __future__ import annotations

from collections.abc import Mapping
from types import MappingProxyType
from typing import cast

from warhammer40k_core.rules.rule_ir import (
    RuleClause,
    RuleClausePayload,
    RuleConditionPayload,
    RuleDurationKind,
    RuleDurationPayload,
    RuleEffectKind,
    RuleEffectSpecPayload,
    RuleIR,
    RuleIRPayload,
    RuleParameterPayload,
    RuleTargetKind,
    RuleTargetSpecPayload,
    RuleTriggerKind,
    RuleTriggerPayload,
    parameter_payload,
)
from warhammer40k_core.rules.rule_templates import (
    AURA_TEMPLATE_ID,
    DICE_ROLL_MODIFIER_TEMPLATE_ID,
    GRANT_ABILITY_TEMPLATE_ID,
    KEYWORD_GATE_TEMPLATE_ID,
    REROLL_PERMISSION_TEMPLATE_ID,
    TIMING_WINDOW_TEMPLATE_ID,
)

SOURCE_PACKAGE_ID = "gw-11e-phase17e-faction-coverage-2026-27"

BLOOD_LEGION_DETACHMENT_RULE_DESCRIPTOR_ID = "phase17e:chaos-daemons:blood-legion:rule"
BLOOD_LEGION_SOURCE_RULE_ID = "phase17f:phase17e:chaos-daemons:blood-legion:rule"
BLOOD_LEGION_DETACHMENT_ID = "blood-legion"
CHAOS_DAEMONS_FACTION_ID = "chaos-daemons"
BRAZENMAW_ENHANCEMENT_ID = "000009815004"
BRAZENMAW_SOURCE_ROW_ID = (
    f"enhancement:{CHAOS_DAEMONS_FACTION_ID}:{BLOOD_LEGION_DETACHMENT_ID}:"
    f"{BRAZENMAW_ENHANCEMENT_ID}"
)
BRAZENMAW_DESCRIPTOR_ID = f"phase17e:{BRAZENMAW_SOURCE_ROW_ID}"
BRAZENMAW_SOURCE_RULE_ID = f"phase17f:{BRAZENMAW_DESCRIPTOR_ID}"
FURYS_CAGE_ENHANCEMENT_ID = "000009815003"
FURYS_CAGE_SOURCE_ROW_ID = (
    f"enhancement:{CHAOS_DAEMONS_FACTION_ID}:{BLOOD_LEGION_DETACHMENT_ID}:"
    f"{FURYS_CAGE_ENHANCEMENT_ID}"
)
FURYS_CAGE_DESCRIPTOR_ID = f"phase17e:{FURYS_CAGE_SOURCE_ROW_ID}"
FURYS_CAGE_SOURCE_RULE_ID = f"phase17f:{FURYS_CAGE_DESCRIPTOR_ID}"
SLAUGHTERTHIRST_ENHANCEMENT_ID = "000009815002"
SLAUGHTERTHIRST_SOURCE_ROW_ID = (
    f"enhancement:{CHAOS_DAEMONS_FACTION_ID}:{BLOOD_LEGION_DETACHMENT_ID}:"
    f"{SLAUGHTERTHIRST_ENHANCEMENT_ID}"
)
SLAUGHTERTHIRST_DESCRIPTOR_ID = f"phase17e:{SLAUGHTERTHIRST_SOURCE_ROW_ID}"
SLAUGHTERTHIRST_SOURCE_RULE_ID = f"phase17f:{SLAUGHTERTHIRST_DESCRIPTOR_ID}"
GATEWAY_UNTO_DAMNATION_ENHANCEMENT_ID = "000009815005"
GATEWAY_UNTO_DAMNATION_SOURCE_ROW_ID = (
    f"enhancement:{CHAOS_DAEMONS_FACTION_ID}:{BLOOD_LEGION_DETACHMENT_ID}:"
    f"{GATEWAY_UNTO_DAMNATION_ENHANCEMENT_ID}"
)
GATEWAY_UNTO_DAMNATION_DESCRIPTOR_ID = f"phase17e:{GATEWAY_UNTO_DAMNATION_SOURCE_ROW_ID}"
GATEWAY_UNTO_DAMNATION_SOURCE_RULE_ID = f"phase17f:{GATEWAY_UNTO_DAMNATION_DESCRIPTOR_ID}"
MURDERCALL_HOOK_ID = "warhammer_40000_11th:chaos_daemons:detachment:blood_legion:murdercall"
BLOOD_TAINTED_HOOK_ID = "warhammer_40000_11th:chaos_daemons:detachment:blood_legion:blood_tainted"
LEGIONES_DAEMONICA_KEYWORD = "LEGIONES DAEMONICA"
KHORNE_KEYWORD = "KHORNE"
MONSTER_KEYWORD = "MONSTER"
AIRCRAFT_KEYWORD = "AIRCRAFT"
MURDERCALL_RANGE_INCHES = 8.0
MURDERCALL_SURGE_ABILITY = "blood_legion_murdercall_surge"
BLOOD_TAINTED_STICKY_OBJECTIVE_ABILITY = "blood_legion_blood_tainted_sticky_objective"
DEADLY_DEMISE_MODIFIER_ABILITY = "deadly_demise_modifier"
DEADLY_DEMISE_DESTROYED_ENEMY_UNIT_CONDITION = "source_model_destroyed_enemy_unit_this_battle"
FURYS_CAGE_SELECTED_TO_FIGHT_ABILITY = "blood_legion_furys_cage_selected_to_fight"
FURYS_CAGE_SELECTED_TO_FIGHT_CONSUMER_ID = (
    "warhammer_40000_11th:chaos_daemons:detachment:blood_legion:enhancement:"
    "furys_cage:selected-to-fight"
)
FURYS_CAGE_MORTAL_WOUND_FNP_CONSUMER_ID = (
    "warhammer_40000_11th:chaos_daemons:detachment:blood_legion:enhancement:"
    "furys_cage:mortal-wound-fnp"
)
FURYS_CAGE_RUNTIME_CONSUMER_IDS = (
    FURYS_CAGE_MORTAL_WOUND_FNP_CONSUMER_ID,
    FURYS_CAGE_SELECTED_TO_FIGHT_CONSUMER_ID,
)


class BloodLegionIrSupportError(ValueError):
    """Raised when static Blood Legion RuleIR support metadata is inconsistent."""


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


def validate_furys_cage_rule_ir(rule_ir: RuleIR) -> None:
    if type(rule_ir) is not RuleIR:
        raise BloodLegionIrSupportError("Fury's Cage validation requires RuleIR.")
    expected_source_id = f"{SOURCE_PACKAGE_ID}:{FURYS_CAGE_DESCRIPTOR_ID}:source-text"
    if (
        not rule_ir.is_supported
        or rule_ir.diagnostics
        or rule_ir.rule_id != expected_source_id
        or rule_ir.source_id != expected_source_id
        or len(rule_ir.clauses) != 4
    ):
        raise BloodLegionIrSupportError("Fury's Cage RuleIR identity or support drifted.")
    gate_clause, marker_clause, mortal_clause, reroll_clause = rule_ir.clauses
    if any(
        clause.unsupported_reason is not None or clause.diagnostics for clause in rule_ir.clauses
    ):
        raise BloodLegionIrSupportError("Fury's Cage RuleIR contains unsupported diagnostics.")
    if (
        gate_clause.template_id != KEYWORD_GATE_TEMPLATE_ID
        or gate_clause.trigger is not None
        or gate_clause.target is not None
        or gate_clause.effects
        or gate_clause.duration is not None
        or tuple(parameter_payload(condition.parameters) for condition in gate_clause.conditions)
        != (
            {"required_keyword_sequence": (LEGIONES_DAEMONICA_KEYWORD,)},
            {"required_keyword": KHORNE_KEYWORD},
            {"required_keyword": MONSTER_KEYWORD},
        )
    ):
        raise BloodLegionIrSupportError("Fury's Cage eligibility gate drifted.")

    marker_target = marker_clause.target
    marker_duration = marker_clause.duration
    if (
        marker_clause.template_id != GRANT_ABILITY_TEMPLATE_ID
        or marker_clause.trigger is not None
        or marker_clause.conditions
        or marker_target is None
        or marker_target.kind is not RuleTargetKind.THIS_MODEL
        or marker_duration is None
        or marker_duration.kind is not RuleDurationKind.PERMANENT
        or parameter_payload(marker_duration.parameters)
        or len(marker_clause.effects) != 1
        or marker_clause.effects[0].kind is not RuleEffectKind.GRANT_ABILITY
        or parameter_payload(marker_clause.effects[0].parameters)
        != {
            "ability": FURYS_CAGE_SELECTED_TO_FIGHT_ABILITY,
            "hook_family": "fight_unit_selected_grant",
            "phase": "fight",
            "timing_window": "selected_to_fight",
            "optional": True,
        }
    ):
        raise BloodLegionIrSupportError("Fury's Cage discovery marker drifted.")

    _validate_furys_cage_triggered_clause(mortal_clause)
    mortal_duration = mortal_clause.duration
    if (
        mortal_clause.template_id != TIMING_WINDOW_TEMPLATE_ID
        or mortal_duration is None
        or mortal_duration.kind is not RuleDurationKind.IMMEDIATE
        or parameter_payload(mortal_duration.parameters)
        or len(mortal_clause.effects) != 1
        or mortal_clause.effects[0].kind is not RuleEffectKind.INFLICT_MORTAL_WOUNDS
        or parameter_payload(mortal_clause.effects[0].parameters)
        != {
            "damage_kind": "mortal_wounds",
            "mortal_wounds_expression": "D3+1",
            "mortal_wounds_dice_quantity": 1,
            "mortal_wounds_dice_sides": 3,
            "mortal_wounds_modifier": 1,
            "target_scope": "this_model",
        }
    ):
        raise BloodLegionIrSupportError("Fury's Cage mortal-wound effect drifted.")

    _validate_furys_cage_triggered_clause(reroll_clause)
    reroll_duration = reroll_clause.duration
    if (
        reroll_clause.template_id != REROLL_PERMISSION_TEMPLATE_ID
        or reroll_duration is None
        or reroll_duration.kind is not RuleDurationKind.UNTIL_TIMING_ENDPOINT
        or parameter_payload(reroll_duration.parameters) != {"endpoint": "phase"}
        or tuple(effect.kind for effect in reroll_clause.effects)
        != (RuleEffectKind.REROLL_PERMISSION, RuleEffectKind.REROLL_PERMISSION)
        or tuple(parameter_payload(effect.parameters) for effect in reroll_clause.effects)
        != (
            {"roll_type": "hit", "attack_role": "attacker", "target_scope": "this_model"},
            {
                "roll_type": "wound",
                "attack_role": "attacker",
                "target_scope": "this_model",
            },
        )
    ):
        raise BloodLegionIrSupportError("Fury's Cage reroll permissions drifted.")


def _validate_furys_cage_triggered_clause(clause: RuleClause) -> None:
    trigger = clause.trigger
    target = clause.target
    if (
        trigger is None
        or trigger.kind is not RuleTriggerKind.UNIT_SELECTED
        or parameter_payload(trigger.parameters)
        != {
            "phase": "fight",
            "timing_window": "selected_to_fight",
            "optional": True,
        }
        or clause.conditions
        or target is None
        or target.kind is not RuleTargetKind.THIS_MODEL
    ):
        raise BloodLegionIrSupportError("Fury's Cage selected-to-fight trigger drifted.")


def _detachment_rule_payload() -> RuleIRPayload:
    source_row_id = "chaos-daemons:blood-legion:rule"
    murdercall_text = (
        "Legiones Daemonica Khorne units have the Murdercall surge ability after enemy "
        "movement within 8 inches."
    )
    blood_tainted_text = (
        "Legiones Daemonica Khorne units have the Blood Tainted sticky objective control "
        "ability after destroying enemy units on objectives."
    )
    normalized_text = f"{murdercall_text} {blood_tainted_text}"
    return _coverage_payload(
        source_row_id,
        normalized_text,
        (
            _ability_clause(
                clause_id=_coverage_clause_id(source_row_id, "effect:001"),
                normalized_text=normalized_text,
                source_text=murdercall_text,
                effect_text="have the Murdercall surge ability",
                ability=MURDERCALL_SURGE_ABILITY,
                extra_parameters=(
                    _parameter("hook_family", "movement_end_surge"),
                    _parameter("range_inches", MURDERCALL_RANGE_INCHES),
                ),
            ),
            _ability_clause(
                clause_id=_coverage_clause_id(source_row_id, "effect:002"),
                normalized_text=normalized_text,
                source_text=blood_tainted_text,
                effect_text="have the Blood Tainted sticky objective control ability",
                ability=BLOOD_TAINTED_STICKY_OBJECTIVE_ABILITY,
                extra_parameters=(_parameter("hook_family", "phase_end_objective_control"),),
            ),
        ),
    )


def _brazenmaw_payload() -> RuleIRPayload:
    normalized_text = (
        "Legiones Daemonica Khorne model only. Add 2 to Charge rolls made for the bearer's unit."
    )
    eligibility_text = "Legiones Daemonica Khorne model only"
    charge_text = "Add 2 to Charge rolls made for the bearer's unit."
    return _coverage_payload(
        BRAZENMAW_SOURCE_ROW_ID,
        normalized_text,
        (
            _keyword_gate_clause(
                clause_id=_coverage_clause_id(BRAZENMAW_SOURCE_ROW_ID, "gate:001"),
                normalized_text=normalized_text,
                source_text=eligibility_text,
                conditions=(
                    _keyword_condition(
                        normalized_text=normalized_text,
                        source_text="Legiones Daemonica",
                        parameter_key="required_keyword_sequence",
                        parameter_value=(LEGIONES_DAEMONICA_KEYWORD,),
                    ),
                    _keyword_condition(
                        normalized_text=normalized_text,
                        source_text="Khorne",
                        parameter_key="required_keyword",
                        parameter_value=KHORNE_KEYWORD,
                    ),
                ),
            ),
            _effect_clause(
                clause_id=_coverage_clause_id(BRAZENMAW_SOURCE_ROW_ID, "effect:001"),
                template_id=DICE_ROLL_MODIFIER_TEMPLATE_ID,
                normalized_text=normalized_text,
                source_text=charge_text,
                target=_target("this_unit", normalized_text, "the bearer's unit"),
                effects=(
                    _effect(
                        "modify_dice_roll",
                        normalized_text,
                        "Add 2 to Charge rolls",
                        (
                            _parameter("delta", 2),
                            _parameter("roll_type", "charge"),
                        ),
                    ),
                ),
                duration=None,
            ),
        ),
    )


def _slaughterthirst_payload() -> RuleIRPayload:
    normalized_text = (
        "Legiones Daemonica Khorne model only. While a friendly LEGIONES DAEMONICA "
        'KHORNE unit (excluding Monsters) is within 6" of the bearer, weapons equipped '
        "by models in that unit have the [LANCE] ability."
    )
    eligibility_text = "Legiones Daemonica Khorne model only"
    aura_text = (
        'While a friendly LEGIONES DAEMONICA KHORNE unit (excluding Monsters) is within 6" '
        "of the bearer, weapons equipped by models in that unit have the [LANCE] ability."
    )
    return _coverage_payload(
        SLAUGHTERTHIRST_SOURCE_ROW_ID,
        normalized_text,
        (
            _keyword_gate_clause(
                clause_id=_coverage_clause_id(SLAUGHTERTHIRST_SOURCE_ROW_ID, "gate:001"),
                normalized_text=normalized_text,
                source_text=eligibility_text,
                conditions=(
                    _keyword_condition(
                        normalized_text=normalized_text,
                        source_text="Legiones Daemonica",
                        parameter_key="required_keyword_sequence",
                        parameter_value=(LEGIONES_DAEMONICA_KEYWORD,),
                    ),
                    _keyword_condition(
                        normalized_text=normalized_text,
                        source_text="Khorne",
                        parameter_key="required_keyword",
                        parameter_value=KHORNE_KEYWORD,
                    ),
                ),
            ),
            _effect_clause(
                clause_id=_coverage_clause_id(SLAUGHTERTHIRST_SOURCE_ROW_ID, "effect:001"),
                template_id=AURA_TEMPLATE_ID,
                normalized_text=normalized_text,
                source_text=aura_text,
                conditions=(
                    _condition(
                        kind="aura",
                        normalized_text=normalized_text,
                        source_text=aura_text,
                    ),
                    _condition(
                        kind="distance_predicate",
                        normalized_text=normalized_text,
                        source_text='within 6" of the bearer',
                        parameters=(
                            _parameter("predicate", "within"),
                            _parameter("object_kind", "unit"),
                            _parameter("object_reference", "this_model"),
                            _parameter("distance_inches", 6),
                        ),
                    ),
                    _condition(
                        kind="keyword_gate",
                        normalized_text=normalized_text,
                        source_text="LEGIONES DAEMONICA",
                        parameters=(_parameter("required_keyword", LEGIONES_DAEMONICA_KEYWORD),),
                    ),
                    _condition(
                        kind="keyword_gate",
                        normalized_text=normalized_text,
                        source_text="KHORNE",
                        parameters=(_parameter("required_keyword", KHORNE_KEYWORD),),
                    ),
                    _condition(
                        kind="keyword_gate",
                        normalized_text=normalized_text,
                        source_text="Monsters",
                        parameters=(_parameter("excluded_keyword", MONSTER_KEYWORD),),
                    ),
                ),
                target=_target(
                    "aura_units",
                    normalized_text,
                    "friendly LEGIONES DAEMONICA KHORNE unit (excluding Monsters)",
                    parameters=(
                        _parameter("allegiance", "friendly"),
                        _parameter("include_source_unit", True),
                    ),
                ),
                effects=(
                    _effect(
                        "grant_weapon_ability",
                        normalized_text,
                        "weapons equipped by models in that unit have the [LANCE] ability",
                        (
                            _parameter("weapon_ability", "Lance"),
                            _parameter("weapon_scope", "all"),
                        ),
                    ),
                ),
                duration=None,
            ),
        ),
    )


def _furys_cage_payload() -> RuleIRPayload:
    normalized_text = (
        "Legiones Daemonica Khorne Monster model only. Each time the bearer is selected "
        "to fight, it can use this Enhancement. If it does, the bearer suffers D3+1 "
        "mortal wounds, and until the end of the phase, each time it makes an attack, "
        "you can re-roll the Hit roll and you can re-roll the Wound roll."
    )
    eligibility_text = "Legiones Daemonica Khorne Monster model only"
    activation_text = "Each time the bearer is selected to fight, it can use this Enhancement."
    mortal_wounds_text = "If it does, the bearer suffers D3+1 mortal wounds"
    reroll_text = (
        "until the end of the phase, each time it makes an attack, you can re-roll the "
        "Hit roll and you can re-roll the Wound roll"
    )
    return _coverage_payload(
        FURYS_CAGE_SOURCE_ROW_ID,
        normalized_text,
        (
            _keyword_gate_clause(
                clause_id=_coverage_clause_id(FURYS_CAGE_SOURCE_ROW_ID, "gate:001"),
                normalized_text=normalized_text,
                source_text=eligibility_text,
                conditions=(
                    _keyword_condition(
                        normalized_text=normalized_text,
                        source_text="Legiones Daemonica",
                        parameter_key="required_keyword_sequence",
                        parameter_value=(LEGIONES_DAEMONICA_KEYWORD,),
                    ),
                    _keyword_condition(
                        normalized_text=normalized_text,
                        source_text="Khorne",
                        parameter_key="required_keyword",
                        parameter_value=KHORNE_KEYWORD,
                    ),
                    _keyword_condition(
                        normalized_text=normalized_text,
                        source_text="Monster",
                        parameter_key="required_keyword",
                        parameter_value=MONSTER_KEYWORD,
                    ),
                ),
            ),
            _effect_clause(
                clause_id=_coverage_clause_id(FURYS_CAGE_SOURCE_ROW_ID, "effect:001"),
                template_id=GRANT_ABILITY_TEMPLATE_ID,
                normalized_text=normalized_text,
                source_text=activation_text,
                target=_target("this_model", normalized_text, "the bearer"),
                effects=(
                    _effect(
                        "grant_ability",
                        normalized_text,
                        "use this Enhancement",
                        (
                            _parameter("ability", FURYS_CAGE_SELECTED_TO_FIGHT_ABILITY),
                            _parameter("hook_family", "fight_unit_selected_grant"),
                            _parameter("phase", "fight"),
                            _parameter("timing_window", "selected_to_fight"),
                            _parameter("optional", True),
                        ),
                    ),
                ),
                duration=_permanent_duration(normalized_text),
            ),
            _effect_clause(
                clause_id=_coverage_clause_id(FURYS_CAGE_SOURCE_ROW_ID, "effect:002"),
                template_id=TIMING_WINDOW_TEMPLATE_ID,
                normalized_text=normalized_text,
                source_text=mortal_wounds_text,
                trigger=_selected_to_fight_trigger(normalized_text, activation_text),
                target=_target("this_model", normalized_text, mortal_wounds_text),
                effects=(
                    _effect(
                        "inflict_mortal_wounds",
                        normalized_text,
                        "the bearer suffers D3+1 mortal wounds",
                        (
                            _parameter("damage_kind", "mortal_wounds"),
                            _parameter("mortal_wounds_expression", "D3+1"),
                            _parameter("mortal_wounds_dice_quantity", 1),
                            _parameter("mortal_wounds_dice_sides", 3),
                            _parameter("mortal_wounds_modifier", 1),
                            _parameter("target_scope", "this_model"),
                        ),
                    ),
                ),
                duration=_immediate_duration(normalized_text, mortal_wounds_text),
            ),
            _effect_clause(
                clause_id=_coverage_clause_id(FURYS_CAGE_SOURCE_ROW_ID, "effect:003"),
                template_id=REROLL_PERMISSION_TEMPLATE_ID,
                normalized_text=normalized_text,
                source_text=reroll_text,
                trigger=_selected_to_fight_trigger(normalized_text, activation_text),
                target=_target("this_model", normalized_text, "it makes an attack"),
                effects=(
                    _effect(
                        "reroll_permission",
                        normalized_text,
                        "you can re-roll the Hit roll",
                        (
                            _parameter("roll_type", "hit"),
                            _parameter("attack_role", "attacker"),
                            _parameter("target_scope", "this_model"),
                        ),
                    ),
                    _effect(
                        "reroll_permission",
                        normalized_text,
                        "you can re-roll the Wound roll",
                        (
                            _parameter("roll_type", "wound"),
                            _parameter("attack_role", "attacker"),
                            _parameter("target_scope", "this_model"),
                        ),
                    ),
                ),
                duration=_end_phase_duration(normalized_text),
            ),
        ),
    )


def _gateway_unto_damnation_payload() -> RuleIRPayload:
    normalized_text = (
        "Legiones Daemonica Khorne Monster model only. The bearer's Deadly Demise ability "
        "inflicts mortal wounds on a D6 roll of 2+ instead of on a 6. In addition, if the "
        "bearer has destroyed one or more enemy units this battle, the bearer has the Deadly "
        "Demise D3+3 ability, instead of any other Deadly Demise ability on its datasheet."
    )
    eligibility_text = "Legiones Daemonica Khorne Monster model only"
    effect_text = (
        "The bearer's Deadly Demise ability inflicts mortal wounds on a D6 roll of 2+ instead "
        "of on a 6. In addition, if the bearer has destroyed one or more enemy units this "
        "battle, the bearer has the Deadly Demise D3+3 ability, instead of any other Deadly "
        "Demise ability on its datasheet."
    )
    return _coverage_payload(
        GATEWAY_UNTO_DAMNATION_SOURCE_ROW_ID,
        normalized_text,
        (
            _keyword_gate_clause(
                clause_id=_coverage_clause_id(
                    GATEWAY_UNTO_DAMNATION_SOURCE_ROW_ID,
                    "gate:001",
                ),
                normalized_text=normalized_text,
                source_text=eligibility_text,
                conditions=(
                    _keyword_condition(
                        normalized_text=normalized_text,
                        source_text="Legiones Daemonica",
                        parameter_key="required_keyword_sequence",
                        parameter_value=(LEGIONES_DAEMONICA_KEYWORD,),
                    ),
                    _keyword_condition(
                        normalized_text=normalized_text,
                        source_text="Khorne",
                        parameter_key="required_keyword",
                        parameter_value=KHORNE_KEYWORD,
                    ),
                    _keyword_condition(
                        normalized_text=normalized_text,
                        source_text="Monster",
                        parameter_key="required_keyword",
                        parameter_value=MONSTER_KEYWORD,
                    ),
                ),
            ),
            _effect_clause(
                clause_id=_coverage_clause_id(
                    GATEWAY_UNTO_DAMNATION_SOURCE_ROW_ID,
                    "effect:001",
                ),
                template_id=GRANT_ABILITY_TEMPLATE_ID,
                normalized_text=normalized_text,
                source_text=effect_text,
                conditions=(
                    _condition(
                        kind="target_constraint",
                        normalized_text=normalized_text,
                        source_text="the bearer",
                        parameters=(
                            _parameter("relationship", "this_model_destroyed_unit"),
                            _parameter("target_allegiance", "enemy"),
                            _parameter("time_scope", "this_battle"),
                        ),
                    ),
                ),
                target=_target("this_model", normalized_text, "the bearer"),
                effects=(
                    _effect(
                        "grant_ability",
                        normalized_text,
                        effect_text,
                        (
                            _parameter("ability", DEADLY_DEMISE_MODIFIER_ABILITY),
                            _parameter("trigger_roll_threshold", 2),
                            _parameter(
                                "conditional_mortal_wounds_kind",
                                "d3",
                            ),
                            _parameter("conditional_mortal_wounds_modifier", 3),
                            _parameter(
                                "condition",
                                DEADLY_DEMISE_DESTROYED_ENEMY_UNIT_CONDITION,
                            ),
                            _parameter("replaces_existing_deadly_demise", True),
                        ),
                    ),
                ),
                duration=None,
            ),
        ),
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


def _keyword_gate_clause(
    *,
    clause_id: str,
    normalized_text: str,
    source_text: str,
    conditions: tuple[RuleConditionPayload, ...],
) -> RuleClausePayload:
    return cast(
        RuleClausePayload,
        {
            "clause_id": clause_id,
            "template_id": KEYWORD_GATE_TEMPLATE_ID,
            "source_span": _span(normalized_text, source_text),
            "trigger": None,
            "conditions": list(conditions),
            "target": None,
            "effects": [],
            "duration": None,
            "unsupported_reason": None,
            "diagnostics": [],
        },
    )


def _keyword_condition(
    *,
    normalized_text: str,
    source_text: str,
    parameter_key: str,
    parameter_value: object,
) -> RuleConditionPayload:
    return cast(
        RuleConditionPayload,
        {
            "kind": "keyword_gate",
            "source_span": _span(normalized_text, source_text),
            "parameters": [_parameter(parameter_key, parameter_value)],
        },
    )


def _ability_clause(
    *,
    clause_id: str,
    normalized_text: str,
    source_text: str,
    effect_text: str,
    ability: str,
    extra_parameters: tuple[RuleParameterPayload, ...],
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
                    _parameter(
                        "required_faction_keyword_sequence",
                        (LEGIONES_DAEMONICA_KEYWORD,),
                    ),
                    _parameter("required_keyword_sequence", (KHORNE_KEYWORD,)),
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
    conditions: tuple[RuleConditionPayload, ...] = (),
    trigger: RuleTriggerPayload | None = None,
) -> RuleClausePayload:
    return cast(
        RuleClausePayload,
        {
            "clause_id": clause_id,
            "template_id": template_id,
            "source_span": _span(normalized_text, source_text),
            "trigger": trigger,
            "conditions": list(conditions),
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


def _condition(
    *,
    kind: str,
    normalized_text: str,
    source_text: str,
    parameters: tuple[RuleParameterPayload, ...] = (),
) -> RuleConditionPayload:
    return cast(
        RuleConditionPayload,
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
    *,
    parameters: tuple[RuleParameterPayload, ...] = (),
) -> RuleTargetSpecPayload:
    return cast(
        RuleTargetSpecPayload,
        {
            "kind": kind,
            "source_span": _span(normalized_text, source_text),
            "parameters": list(parameters),
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


def _selected_to_fight_trigger(
    normalized_text: str,
    source_text: str,
) -> RuleTriggerPayload:
    return cast(
        RuleTriggerPayload,
        {
            "kind": "unit_selected",
            "source_span": _span(normalized_text, source_text),
            "parameters": [
                _parameter("phase", "fight"),
                _parameter("timing_window", "selected_to_fight"),
                _parameter("optional", True),
            ],
        },
    )


def _immediate_duration(
    normalized_text: str,
    source_text: str,
) -> RuleDurationPayload:
    return cast(
        RuleDurationPayload,
        {
            "kind": "immediate",
            "source_span": _span(normalized_text, source_text),
            "parameters": [],
        },
    )


def _end_phase_duration(normalized_text: str) -> RuleDurationPayload:
    source_text = "until the end of the phase"
    return cast(
        RuleDurationPayload,
        {
            "kind": "until_timing_endpoint",
            "source_span": _span(normalized_text, source_text),
            "parameters": [
                _parameter("endpoint", "phase"),
            ],
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
            BLOOD_LEGION_DETACHMENT_RULE_DESCRIPTOR_ID: _detachment_rule_payload(),
            BRAZENMAW_DESCRIPTOR_ID: _brazenmaw_payload(),
            FURYS_CAGE_DESCRIPTOR_ID: _furys_cage_payload(),
            GATEWAY_UNTO_DAMNATION_DESCRIPTOR_ID: _gateway_unto_damnation_payload(),
            SLAUGHTERTHIRST_DESCRIPTOR_ID: _slaughterthirst_payload(),
        }
    )


_COVERAGE_RULE_IR_PAYLOADS_BY_DESCRIPTOR_ID = _coverage_payloads()
