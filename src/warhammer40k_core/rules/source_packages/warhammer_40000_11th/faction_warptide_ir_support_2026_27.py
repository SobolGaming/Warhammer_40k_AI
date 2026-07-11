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
    CHARACTERISTIC_MODIFIER_TEMPLATE_ID,
    CONTEXTUAL_STATUS_TEMPLATE_ID,
    DICE_ROLL_MODIFIER_TEMPLATE_ID,
    GRANT_ABILITY_TEMPLATE_ID,
    KEYWORD_GATE_TEMPLATE_ID,
)

SOURCE_PACKAGE_ID = "gw-11e-phase17e-faction-coverage-2026-27"
STRATAGEM_TARGET_BINDING_TEMPLATE_ID = "phase17s:stratagem-activation-target-binding"

CHAOS_DAEMONS_FACTION_ID = "chaos-daemons"
WARPTIDE_DETACHMENT_ID = "warptide"
WARPTIDE_DETACHMENT_RULE_DESCRIPTOR_ID = "phase17e:chaos-daemons:warptide:rule"
WARPTIDE_SOURCE_RULE_ID = "phase17f:phase17e:chaos-daemons:warptide:rule"

LEGIONES_DAEMONICA_KEYWORD = "LEGIONES DAEMONICA"
BATTLELINE_KEYWORD = "BATTLELINE"
PINK_HORRORS_KEYWORD = "PINK HORRORS"
ASSAULT_WEAPON_KEYWORD = "Assault"

SHUDDERBLINK_ASSAULT_AFTER_ADVANCE_ABILITY = (
    "chaos-daemons:warptide:shudderblink:assault-after-advance"
)
SHUDDERBLINK_CHARGE_AFTER_ADVANCE_ABILITY = (
    "chaos-daemons:warptide:shudderblink:charge-after-advance"
)
SHUDDERBLINK_ADVANCE_MOVE_HOOK_ID = (
    "warhammer_40000_11th:chaos_daemons:detachment:warptide:shudderblink:advance-move"
)
SHUDDERBLINK_ADVANCE_ELIGIBILITY_HOOK_ID = (
    "warhammer_40000_11th:chaos_daemons:detachment:warptide:shudderblink:advance-eligibility"
)

BANE_FORGED_WEAPONS_ENHANCEMENT_ID = "chaos-daemons:warptide:bane-forged-weapons"
BANE_FORGED_WEAPONS_SOURCE_ROW_ID = (
    "enhancement:chaos-daemons:warptide:chaos-daemons:warptide:bane-forged-weapons"
)
BANE_FORGED_WEAPONS_DESCRIPTOR_ID = f"phase17e:{BANE_FORGED_WEAPONS_SOURCE_ROW_ID}"
BANE_FORGED_WEAPONS_SOURCE_RULE_ID = f"phase17f:phase17e:{BANE_FORGED_WEAPONS_SOURCE_ROW_ID}"

SOUL_HUNGRY_SLAUGHTERERS_ENHANCEMENT_ID = "chaos-daemons:warptide:soul-hungry-slaughterers"
SOUL_HUNGRY_SLAUGHTERERS_SOURCE_ROW_ID = (
    "enhancement:chaos-daemons:warptide:chaos-daemons:warptide:soul-hungry-slaughterers"
)
SOUL_HUNGRY_SLAUGHTERERS_DESCRIPTOR_ID = f"phase17e:{SOUL_HUNGRY_SLAUGHTERERS_SOURCE_ROW_ID}"
SOUL_HUNGRY_SLAUGHTERERS_SOURCE_RULE_ID = (
    f"phase17f:phase17e:{SOUL_HUNGRY_SLAUGHTERERS_SOURCE_ROW_ID}"
)
SOUL_HUNGRY_SLAUGHTERERS_COST_ABILITY = (
    "chaos-daemons:warptide:soul-hungry-slaughterers:stratagem-cost"
)
SOUL_HUNGRY_SLAUGHTERERS_COST_MODIFIER_ID = (
    "warhammer_40000_11th:chaos_daemons:detachment:warptide:soul_hungry_slaughterers:cost_modifier"
)

DAEMONIC_INFESTATION_STRATAGEM_ID = "chaos-daemons:warptide:daemonic-infestation"
SOULSEEING_STRATAGEM_ID = "chaos-daemons:warptide:soulseeing"
INCORPOREAL_ENTITIES_STRATAGEM_ID = "chaos-daemons:warptide:incorporeal-entities"
DAEMONIC_INFESTATION_SOURCE_ROW_ID = (
    f"stratagem:chaos-daemons:warptide:{DAEMONIC_INFESTATION_STRATAGEM_ID}"
)
SOULSEEING_SOURCE_ROW_ID = f"stratagem:chaos-daemons:warptide:{SOULSEEING_STRATAGEM_ID}"
INCORPOREAL_ENTITIES_SOURCE_ROW_ID = (
    f"stratagem:chaos-daemons:warptide:{INCORPOREAL_ENTITIES_STRATAGEM_ID}"
)
WARPTIDE_STRATAGEM_SOURCE_ROW_IDS = (
    DAEMONIC_INFESTATION_SOURCE_ROW_ID,
    SOULSEEING_SOURCE_ROW_ID,
    INCORPOREAL_ENTITIES_SOURCE_ROW_ID,
)
DAEMONIC_INFESTATION_DESCRIPTOR_ID = f"phase17e:{DAEMONIC_INFESTATION_SOURCE_ROW_ID}"
SOULSEEING_DESCRIPTOR_ID = f"phase17e:{SOULSEEING_SOURCE_ROW_ID}"
INCORPOREAL_ENTITIES_DESCRIPTOR_ID = f"phase17e:{INCORPOREAL_ENTITIES_SOURCE_ROW_ID}"

VISIBLE_ENEMY_UNIT_EFFECT_SELECTION_KIND = "visible_enemy_unit"
VISIBLE_ENEMY_UNIT_CONTEXT_KEY = "visible_enemy_unit_instance_id"
VISIBLE_ENEMY_UNIT_SOURCE_CONTEXT_TARGET_BINDING = "target_binding_unit"
SOULSEEING_RANGE_INCHES = 12
SOULSEEING_DETECTION_RANGE_BONUS_INCHES = 6
SOULSEEING_DETECTION_EFFECT_KIND = "chaos_daemons_warptide_soulseeing"
INCORPOREAL_ENTITIES_WOUND_MODIFIER_SOURCE_KIND = "chaos_daemons_warptide_incorporeal_entities"


class WarptideIrSupportError(ValueError):
    """Raised when static Warptide RuleIR support metadata is inconsistent."""


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
    source_row_id = "chaos-daemons:warptide:rule"
    normalized_text = (
        "When a friendly Legiones Daemonica Battleline unit is selected to make an "
        "Advance move, that unit's ranged attacks have Assault until the end of the "
        "turn and that move does not prevent it from declaring a charge."
    )
    return _coverage_payload(
        source_row_id,
        normalized_text,
        (
            _ability_clause(
                clause_id=_coverage_clause_id(source_row_id, "effect:001"),
                normalized_text=normalized_text,
                source_text="that unit's ranged attacks have Assault until the end of the turn",
                effect_text="ranged attacks have Assault",
                ability=SHUDDERBLINK_ASSAULT_AFTER_ADVANCE_ABILITY,
                extra_parameters=(
                    _parameter("hook_family", "advance_move"),
                    _parameter("granted_ranged_weapon_keyword", ASSAULT_WEAPON_KEYWORD),
                    *_battleline_daemon_parameters(),
                ),
                duration=_permanent_duration(normalized_text),
            ),
            _ability_clause(
                clause_id=_coverage_clause_id(source_row_id, "effect:002"),
                normalized_text=normalized_text,
                source_text="that move does not prevent it from declaring a charge",
                effect_text="does not prevent it from declaring a charge",
                ability=SHUDDERBLINK_CHARGE_AFTER_ADVANCE_ABILITY,
                extra_parameters=(
                    _parameter("hook_family", "advance_eligibility"),
                    _parameter("can_declare_charge", True),
                    *_battleline_daemon_parameters(),
                ),
                duration=_permanent_duration(normalized_text),
            ),
        ),
    )


def _bane_forged_weapons_payload() -> RuleIRPayload:
    normalized_text = (
        "Legiones Daemonica Battleline unit only. This unit's attacks have +1 Strength."
    )
    return _coverage_payload(
        BANE_FORGED_WEAPONS_SOURCE_ROW_ID,
        normalized_text,
        (
            _battleline_daemon_keyword_gate_clause(
                clause_id=_coverage_clause_id(BANE_FORGED_WEAPONS_SOURCE_ROW_ID, "gate:001"),
                normalized_text=normalized_text,
                source_text="Legiones Daemonica Battleline",
            ),
            _characteristic_modifier_clause(
                clause_id=_coverage_clause_id(BANE_FORGED_WEAPONS_SOURCE_ROW_ID, "effect:001"),
                normalized_text=normalized_text,
                source_text="This unit's attacks have +1 Strength",
                effect_text="+1 Strength",
                characteristic="strength",
                delta=1,
                extra_parameters=(
                    _parameter("attack_role", "attacker"),
                    _parameter("weapon_scope", "all"),
                    *_battleline_daemon_parameters(),
                ),
                duration=_permanent_duration(normalized_text),
            ),
        ),
    )


def _soul_hungry_slaughterers_payload() -> RuleIRPayload:
    normalized_text = (
        "Legiones Daemonica Battleline unit only. When this unit is targeted with the "
        "Heroic Intervention or Fire Overwatch Stratagem, that use is -1 Command Point."
    )
    return _coverage_payload(
        SOUL_HUNGRY_SLAUGHTERERS_SOURCE_ROW_ID,
        normalized_text,
        (
            _battleline_daemon_keyword_gate_clause(
                clause_id=_coverage_clause_id(
                    SOUL_HUNGRY_SLAUGHTERERS_SOURCE_ROW_ID,
                    "gate:001",
                ),
                normalized_text=normalized_text,
                source_text="Legiones Daemonica Battleline",
            ),
            _ability_clause(
                clause_id=_coverage_clause_id(
                    SOUL_HUNGRY_SLAUGHTERERS_SOURCE_ROW_ID,
                    "effect:001",
                ),
                normalized_text=normalized_text,
                source_text="that use is -1 Command Point",
                effect_text="-1 Command Point",
                ability=SOUL_HUNGRY_SLAUGHTERERS_COST_ABILITY,
                extra_parameters=(
                    _parameter("discount_command_points", 1),
                    _parameter("stratagem_ids", ("fire-overwatch", "heroic-intervention")),
                    *_battleline_daemon_parameters(),
                ),
                duration=_permanent_duration(normalized_text),
            ),
        ),
    )


def _daemonic_infestation_payload() -> RuleIRPayload:
    rule_id = _coverage_rule_id(DAEMONIC_INFESTATION_SOURCE_ROW_ID)
    normalized_text = (
        "stratagem_activation_target_binding\n"
        "Your Legiones Daemonica Battleline unit, excluding Pink Horrors, heals 3 wounds."
    )
    return _payload(
        rule_id,
        rule_id,
        normalized_text,
        (
            _stratagem_target_binding_clause(rule_id, normalized_text),
            _effect_clause(
                clause_id=f"{rule_id}:effect:001",
                template_id=None,
                normalized_text=normalized_text,
                source_text="heals 3 wounds",
                target=None,
                effects=(
                    _effect(
                        "restore_lost_wounds",
                        normalized_text,
                        "heals 3 wounds",
                        (
                            _parameter("amount", 3),
                            _parameter("cap", "lost_wounds"),
                            _parameter("target", "one_model_in_target_unit"),
                            _parameter("selection_actor", "owner"),
                        ),
                    ),
                ),
                duration=None,
            ),
        ),
        _stratagem_parser_version(),
    )


def _soulseeing_payload() -> RuleIRPayload:
    rule_id = _coverage_rule_id(SOULSEEING_SOURCE_ROW_ID)
    normalized_text = (
        "stratagem_activation_target_binding\n"
        "Select one visible enemy unit within 12 inches of your Legiones Daemonica "
        "Battleline unit. That enemy unit has +6 inches detection range until the end "
        "of the Shooting phase."
    )
    return _payload(
        rule_id,
        rule_id,
        normalized_text,
        (
            _stratagem_target_binding_clause(rule_id, normalized_text),
            _effect_clause(
                clause_id=f"{rule_id}:effect:001",
                template_id=CONTEXTUAL_STATUS_TEMPLATE_ID,
                normalized_text=normalized_text,
                source_text="+6 inches detection range until the end of the Shooting phase",
                target=None,
                effects=(
                    _effect(
                        "set_contextual_status",
                        normalized_text,
                        "+6 inches detection range",
                        (
                            _parameter("status", "detection_range_bonus"),
                            _parameter(
                                "effect_selection_kind",
                                VISIBLE_ENEMY_UNIT_EFFECT_SELECTION_KIND,
                            ),
                            _parameter("bonus_inches", SOULSEEING_DETECTION_RANGE_BONUS_INCHES),
                            _parameter("source_rule_kind", SOULSEEING_DETECTION_EFFECT_KIND),
                            _parameter(
                                "source_unit_context_key",
                                VISIBLE_ENEMY_UNIT_SOURCE_CONTEXT_TARGET_BINDING,
                            ),
                        ),
                    ),
                ),
                duration=_end_phase_duration(normalized_text),
            ),
        ),
        _stratagem_parser_version(),
    )


def _incorporeal_entities_payload() -> RuleIRPayload:
    rule_id = _coverage_rule_id(INCORPOREAL_ENTITIES_SOURCE_ROW_ID)
    normalized_text = (
        "stratagem_activation_target_binding\n"
        "Until the end of the phase, ranged attacks that target your Legiones Daemonica "
        "Battleline unit with a Strength greater than that unit's Toughness have -1 to "
        "Wound rolls."
    )
    return _payload(
        rule_id,
        rule_id,
        normalized_text,
        (
            _stratagem_target_binding_clause(rule_id, normalized_text),
            _dice_modifier_clause(
                clause_id=f"{rule_id}:effect:001",
                normalized_text=normalized_text,
                source_text=normalized_text.split("\n", maxsplit=1)[1],
                effect_text="-1 to Wound rolls",
                roll_type="wound",
                delta=-1,
                extra_parameters=(
                    _parameter("attack_role", "target"),
                    _parameter("source_phase", "shooting"),
                    _parameter("weapon_scope", "ranged"),
                    _parameter(
                        "target_constraint",
                        "attack_strength_greater_than_target_toughness",
                    ),
                    _parameter("source_kind", INCORPOREAL_ENTITIES_WOUND_MODIFIER_SOURCE_KIND),
                    *_battleline_daemon_parameters(),
                ),
                duration=_end_phase_duration(normalized_text),
            ),
        ),
        _stratagem_parser_version(),
    )


def _ability_clause(
    *,
    clause_id: str,
    normalized_text: str,
    source_text: str,
    effect_text: str,
    ability: str,
    extra_parameters: tuple[RuleParameterPayload, ...],
    duration: RuleDurationPayload,
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
                    *extra_parameters,
                ),
            ),
        ),
        duration=duration,
    )


def _characteristic_modifier_clause(
    *,
    clause_id: str,
    normalized_text: str,
    source_text: str,
    effect_text: str,
    characteristic: str,
    delta: int,
    extra_parameters: tuple[RuleParameterPayload, ...],
    duration: RuleDurationPayload,
) -> RuleClausePayload:
    return _effect_clause(
        clause_id=clause_id,
        template_id=CHARACTERISTIC_MODIFIER_TEMPLATE_ID,
        normalized_text=normalized_text,
        source_text=source_text,
        target=_target("this_unit", normalized_text, source_text),
        effects=(
            _effect(
                "modify_characteristic",
                normalized_text,
                effect_text,
                (
                    _parameter("characteristic", characteristic),
                    _parameter("delta", delta),
                    *extra_parameters,
                ),
            ),
        ),
        duration=duration,
    )


def _dice_modifier_clause(
    *,
    clause_id: str,
    normalized_text: str,
    source_text: str,
    effect_text: str,
    roll_type: str,
    delta: int,
    extra_parameters: tuple[RuleParameterPayload, ...],
    duration: RuleDurationPayload,
) -> RuleClausePayload:
    return _effect_clause(
        clause_id=clause_id,
        template_id=DICE_ROLL_MODIFIER_TEMPLATE_ID,
        normalized_text=normalized_text,
        source_text=source_text,
        target=None,
        effects=(
            _effect(
                "modify_dice_roll",
                normalized_text,
                effect_text,
                (
                    _parameter("roll_type", roll_type),
                    _parameter("delta", delta),
                    *extra_parameters,
                ),
            ),
        ),
        duration=duration,
    )


def _stratagem_target_binding_clause(rule_id: str, normalized_text: str) -> RuleClausePayload:
    return cast(
        RuleClausePayload,
        {
            "clause_id": f"{rule_id}:target-binding",
            "template_id": STRATAGEM_TARGET_BINDING_TEMPLATE_ID,
            "source_span": _span(normalized_text, "stratagem_activation_target_binding"),
            "trigger": None,
            "conditions": [],
            "target": _target(
                "friendly_unit",
                normalized_text,
                "stratagem_activation_target_binding",
            ),
            "effects": [],
            "duration": None,
            "unsupported_reason": None,
            "diagnostics": [],
        },
    )


def _battleline_daemon_keyword_gate_clause(
    *,
    clause_id: str,
    normalized_text: str,
    source_text: str,
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
                    source_text=source_text,
                    parameters=_battleline_daemon_parameters(),
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
    source_text: str,
    parameters: tuple[RuleParameterPayload, ...],
) -> RuleConditionPayload:
    return cast(
        RuleConditionPayload,
        {
            "kind": "keyword_gate",
            "source_span": _span(normalized_text, source_text),
            "parameters": list(parameters),
        },
    )


def _effect_clause(
    *,
    clause_id: str,
    template_id: str | None,
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


def _target(kind: str, normalized_text: str, source_text: str) -> RuleTargetSpecPayload:
    return cast(
        RuleTargetSpecPayload,
        {
            "kind": kind,
            "source_span": _span(normalized_text, source_text),
            "parameters": [],
        },
    )


def _battleline_daemon_parameters() -> tuple[RuleParameterPayload, ...]:
    return (
        _parameter("required_faction_keyword_sequence", (LEGIONES_DAEMONICA_KEYWORD,)),
        _parameter("required_keyword_sequence", (BATTLELINE_KEYWORD,)),
    )


def _coverage_payload(
    source_row_id: str,
    normalized_text: str,
    clauses: tuple[RuleClausePayload, ...],
) -> RuleIRPayload:
    source_id = _coverage_rule_id(source_row_id)
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


def _coverage_rule_id(source_row_id: str) -> str:
    return f"{SOURCE_PACKAGE_ID}:phase17e:{source_row_id}:source-text"


def _coverage_clause_id(source_row_id: str, suffix: str) -> str:
    return f"{_coverage_rule_id(source_row_id)}:{suffix}"


def _permanent_duration(normalized_text: str) -> RuleDurationPayload:
    return cast(
        RuleDurationPayload,
        {
            "kind": "permanent",
            "source_span": _span(normalized_text, normalized_text),
            "parameters": [],
        },
    )


def _end_phase_duration(normalized_text: str) -> RuleDurationPayload:
    return cast(
        RuleDurationPayload,
        {
            "kind": "until_timing_endpoint",
            "source_span": _span(normalized_text, "end of the"),
            "parameters": [_parameter("endpoint", "phase")],
        },
    )


def _parameter(key: str, value: object) -> RuleParameterPayload:
    return cast(RuleParameterPayload, {"key": key, "value": value})


def _span(normalized_text: str, source_text: str) -> dict[str, str | int]:
    start = normalized_text.index(source_text)
    return {"text": source_text, "start": start, "end": start + len(source_text)}


def _stratagem_parser_version() -> str:
    return "phase17s-stratagem-activation-template-v2"


def _coverage_payloads() -> Mapping[str, RuleIRPayload]:
    return MappingProxyType(
        {
            WARPTIDE_DETACHMENT_RULE_DESCRIPTOR_ID: _detachment_rule_payload(),
            BANE_FORGED_WEAPONS_DESCRIPTOR_ID: _bane_forged_weapons_payload(),
            SOUL_HUNGRY_SLAUGHTERERS_DESCRIPTOR_ID: _soul_hungry_slaughterers_payload(),
            DAEMONIC_INFESTATION_DESCRIPTOR_ID: _daemonic_infestation_payload(),
            SOULSEEING_DESCRIPTOR_ID: _soulseeing_payload(),
            INCORPOREAL_ENTITIES_DESCRIPTOR_ID: _incorporeal_entities_payload(),
        }
    )


_COVERAGE_RULE_IR_PAYLOADS_BY_DESCRIPTOR_ID = _coverage_payloads()
